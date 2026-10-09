"""The incremental parse pipeline: imported caselist and camp sources into the parsed card store.

`debate-research caselist parse` is a thin command over :class:`CaselistParseService`
(`v1-e31-t06-parse-pipeline`). One run of it:

1. **Enumerates** the sources the caselist's local manifests store, weekly series and camp releases
   only (:mod:`debate_core.application.caselist.parse_sources`).
2. **Chooses the version directory**: the newest generation of the running parser version, or a new
   generation when `--reparse` is asked or the style profile has changed under the same parser
   version. An older directory is never written to again.
3. **Skips** every source whose :class:`~debate_core.application.ports.parsed_store.SkipKey` (its
   SHA-256, the parser version and the profile version) is already recorded there, and every source
   the removal suppression list stops. The same file disclosed in fourteen weeks is one parse.
4. **Parses the rest** in a bounded pool with a per-file time limit
   (:mod:`debate_core.application.caselist.parse_workers`), writing each source's file as its
   result arrives, so a run stopped part-way keeps what it finished.
5. **Rebuilds the three aggregates** from every per-source file in the directory: the index, the
   failures file and the occurrence table, with fingerprints and clusters from the `v1-e31-t04`
   service (:meth:`~debate_core.application.caselist_card_stats.CaselistCardStatsService.place`).

## A failing source is an outcome

Nothing one file does stops the run. A PDF, a legacy `.doc` or another format V1 does not read is
recorded as `UNSUPPORTED`; a malformed, oversized or macro-enabled package, a parse past the time
limit, a crashed worker or a parser that raised is recorded as `FAILED`, with its typed reason. The
command's exit code is decided by :attr:`ParseRunReport.exceeds_threshold`: the share of the sources
this run tried to read that `FAILED`. Unsupported formats count on neither side of that fraction,
because PF alone discloses hundreds of PDFs and a threshold that counted them would fail every run.

## Removal: rebuilt, never carried forward

The aggregates are rebuilt from scratch on every run and never read back, and each of them consults
the suppression list itself, which is a required constructor argument with no default. A source the
list stops, or a disclosure of it, is in none of them after the next run, whether the removal was
made on this machine or on another. `caselist remove` deletes the removed source's per-source files
and every aggregate of the caselists it touches (`v1-e30-t07`, extended by this task), so between a
removal and the next run there is no aggregate holding the source either; the runbook's next step
is this command. The session report for this task gives the reasons for rebuilding rather than
filtering on read.

## What is logged

Counts, the caselist, the version and sha256 values. Never a path, a school, a team code or a word
of a card (`docs/policies/caselist-data-use.md`, personal-data rule 4). The disclosure paths this
module handles are kept off every object's `repr`.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Final

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.parse_sources import Disclosed, EnumeratedSource, enumerate_sources
from debate_core.application.caselist.parse_workers import (
    LoadableJob,
    ParseJob,
    ParseResult,
    ParseRunner,
    SourceLoadError,
    WorkerFailure,
)
from debate_core.application.caselist.publish_plan import OPENEV, local_blob_key, validate_publish_target
from debate_core.application.caselist.suppression import load_suppression_state
from debate_core.application.caselist_card_stats import CardPlacement
from debate_core.application.ports.debate_files import DebateFileParser
from debate_core.application.ports.parsed_store import (
    DocumentRecord,
    OccurrenceRecord,
    ParsedStore,
    PipelineFailureReason,
    SourceEntry,
    SourceOutcome,
    parse_version_directory,
    skip_key,
    version_directory_name,
)
from debate_core.application.ports.suppression import SuppressionList, SuppressionState, disclosure_digest
from debate_core.domain.debate_files import ParsedCard, ParsedDocument, ParseFailure
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION

__all__ = [
    "CaselistParseService",
    "FailureListing",
    "FailureRow",
    "ParsePlan",
    "ParseRunReport",
    "StoreTotals",
]

logger = logging.getLogger(__name__)

#: How many characters of a SHA-256 a failure listing shows.
SHA256_PREFIX_LENGTH: Final = 12

PlaceCards = Callable[[Sequence[ParsedCard]], Sequence[CardPlacement]]


# ------------------------------------------------------------------------------------------------
# What the service returns
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ParsePlan:
    """What a run would do, decided before anything is parsed. A `--dry-run` stops here."""

    caselist: str
    version: str
    """The version directory this run writes."""
    superseded: str | None
    """The generation a new version directory supersedes, left as it was; `None` when not new."""
    parser_version: str
    profile_version: str
    snapshot: str | None
    reparse: bool
    sources: tuple[EnumeratedSource, ...] = field(repr=False)
    """Every source the manifests store, whatever the snapshot asked for: the aggregates' input."""
    in_scope: int
    """Sources disclosed in the requested snapshot, or every source when none was asked for."""
    suppressed: int
    """In-scope sources the suppression list stops, wholly or in every disclosure."""
    to_parse: tuple[EnumeratedSource, ...] = field(repr=False)
    suppression: SuppressionState = field(repr=False)

    @property
    def skipped(self) -> int:
        """In-scope sources already parsed under this run's skip key, which are not parsed again."""
        return self.in_scope - self.suppressed - len(self.to_parse)

    @property
    def new_version(self) -> bool:
        return self.superseded is not None


@dataclass(frozen=True, slots=True)
class StoreTotals:
    """What the version directory holds after the aggregates were rebuilt. Counts only."""

    sources: int
    parsed: int
    unsupported: int
    failed: int
    cards: int
    occurrences: int
    clusters: int


@dataclass(frozen=True, slots=True)
class ParseRunReport:
    """What a run did, or for a dry run, what it would do."""

    plan: ParsePlan
    applied: bool
    threshold: float
    workers: int
    parsed: int = 0
    cards: int = 0
    unsupported: dict[str, int] = field(default_factory=dict[str, int])
    """Sources this run found in a format V1 does not read, by format: `PDF`, `DOC`, `OTHER`."""
    failed: dict[str, int] = field(default_factory=dict[str, int])
    """Sources this run failed to read, by reason."""
    store: StoreTotals | None = None
    elapsed_seconds: float = 0.0

    @property
    def attempted(self) -> int:
        """Sources this run handed to the parser (all of `to_parse`, or none for a dry run)."""
        return len(self.plan.to_parse) if self.applied else 0

    @property
    def failure_rate(self) -> float:
        """Failed sources over the sources this run tried to read; unsupported formats in neither."""
        tried = self.attempted - sum(self.unsupported.values())
        return sum(self.failed.values()) / tried if tried else 0.0

    @property
    def exceeds_threshold(self) -> bool:
        return self.failure_rate > self.threshold


@dataclass(frozen=True, slots=True)
class FailureRow:
    """One source that did not parse, for `caselist parse --failures`. The path is for the terminal."""

    sha256: str
    path: str | None = field(repr=False)
    """Where the manifests say it was disclosed, which names a school and a team. Never logged."""
    snapshot: str
    source_format: str
    reason: str
    detail: str
    counts_toward_failure_rate: bool

    @property
    def sha256_prefix(self) -> str:
        return self.sha256[:SHA256_PREFIX_LENGTH]


@dataclass(frozen=True, slots=True)
class FailureListing:
    """The failures file of a caselist's current version directory, with paths from the manifests."""

    caselist: str
    version: str | None
    present: bool
    """False when there is no failures file: never parsed, or deleted by a removal until the next run."""
    rows: tuple[FailureRow, ...] = ()


# ------------------------------------------------------------------------------------------------
# The service
# ------------------------------------------------------------------------------------------------


class CaselistParseService:
    """Parses a caselist's stored sources into the parsed card store, incrementally.

    Args:
        local: This machine's manifests and blobs. Its blob store must be able to name a file for a
            key (`blob_path_for`), because sources are read from disk one at a time as workers free.
        store: The parsed card store.
        parser: The `.docx` parser, with its parser and profile versions.
        runner: In this process, or the bounded pool.
        suppression: The removal suppression list. Required, no default: nothing is parsed, and no
            aggregate is written, without it (`v1-e30-t07`).
        place_cards: The `v1-e31-t04` fingerprinting and clustering,
            :meth:`~debate_core.application.caselist_card_stats.CaselistCardStatsService.place`.
        failure_rate_threshold: The `parse.failure_rate_threshold` setting.
    """

    def __init__(
        self,
        *,
        local: LocalEvidence,
        store: ParsedStore,
        parser: DebateFileParser,
        runner: ParseRunner,
        suppression: SuppressionList,
        place_cards: PlaceCards,
        failure_rate_threshold: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if local.blob_path_for is None:
            raise ValueError(
                "the parse pipeline reads sources from files: give LocalEvidence a blob_path_for"
            )
        self._local = local
        self._store = store
        self._parser = parser
        self._runner = runner
        self._suppression = suppression
        self._place_cards = place_cards
        self._threshold = failure_rate_threshold
        self._clock = clock

    # -- planning -----------------------------------------------------------------------------

    async def plan(self, caselist: str, *, snapshot: str | None = None, reparse: bool = False) -> ParsePlan:
        """Work out what a run would parse and where it would write, writing nothing."""
        validate_publish_target(caselist, snapshot)
        state = await load_suppression_state(self._suppression)
        sources = await enumerate_sources(self._local, caselist)
        parser_version, profile_version = self._parser.parser_version, self._parser.profile_version
        version, superseded, recorded = await self._choose_version(
            caselist, parser_version, profile_version, reparse=reparse
        )
        done = {entry.skip_key for entry in recorded if not entry.retried_next_run}
        in_scope = [
            source
            for source in sources
            if snapshot is None or any(disclosed.snapshot == snapshot for disclosed in source.disclosures)
        ]
        live = [source for source in in_scope if _live_disclosures(source, state)]
        to_parse = tuple(
            source for source in live if skip_key(source.sha256, parser_version, profile_version) not in done
        )
        return ParsePlan(
            caselist=caselist,
            version=version,
            superseded=superseded,
            parser_version=parser_version,
            profile_version=profile_version,
            snapshot=snapshot,
            reparse=reparse,
            sources=sources,
            in_scope=len(in_scope),
            suppressed=len(in_scope) - len(live),
            to_parse=to_parse,
            suppression=state,
        )

    async def _choose_version(
        self, caselist: str, parser_version: str, profile_version: str, *, reparse: bool
    ) -> tuple[str, str | None, tuple[SourceEntry, ...]]:
        """The directory to write, the generation it supersedes (if new), and what it already holds.

        The newest generation of this parser version is reused when every entry in it has this
        run's skip key. A forced re-parse, or an entry parsed under another profile, starts a new
        generation instead, so the old directory is never written to.
        """
        generations = sorted(
            generation
            for name in await self._store.version_directories(caselist)
            for named, generation in [parse_version_directory(name)]
            if named == parser_version
        )
        if not generations:
            return version_directory_name(parser_version), None, ()
        newest = version_directory_name(parser_version, generations[-1])
        recorded = await self._store.read_entries(caselist, newest)
        current = all(
            entry.skip_key == skip_key(entry.source_sha256, parser_version, profile_version)
            for entry in recorded
        )
        if reparse or not current:
            return version_directory_name(parser_version, generations[-1] + 1), newest, ()
        return newest, None, recorded

    # -- running ------------------------------------------------------------------------------

    def dry_run(self, plan: ParsePlan) -> ParseRunReport:
        """The report a `--dry-run` prints: the plan's counts, nothing parsed or written."""
        return ParseRunReport(
            plan=plan, applied=False, threshold=self._threshold, workers=self._runner.workers
        )

    async def run(self, plan: ParsePlan) -> ParseRunReport:
        """Parse what `plan` names, then rebuild the version directory's aggregates."""
        started = self._clock()
        by_digest = {source.sha256: source for source in plan.sources}
        parsed = cards = 0
        unsupported: Counter[str] = Counter()
        failed: Counter[str] = Counter()
        for job, result in self._runner.run(self._parser, self._jobs(plan)):
            source = by_digest[job.source.sha256]
            entry, document = self._record(plan, source, result)
            await self._store.put_source(plan.caselist, plan.version, entry, document)
            if entry.outcome is SourceOutcome.PARSED:
                parsed += 1
                cards += entry.cards
            elif entry.outcome is SourceOutcome.UNSUPPORTED:
                unsupported[str(entry.source_format)] += 1
            else:
                failed[str(entry.reason)] += 1
                logger.debug(
                    "caselist parse %s: %s failed, %s", plan.caselist, source.sha256[:12], entry.reason
                )
        totals = await self._rebuild(plan)
        report = ParseRunReport(
            plan=plan,
            applied=True,
            threshold=self._threshold,
            workers=self._runner.workers,
            parsed=parsed,
            cards=cards,
            unsupported=dict(sorted(unsupported.items())),
            failed=dict(sorted(failed.items())),
            store=totals,
            elapsed_seconds=self._clock() - started,
        )
        _log_run(report)
        return report

    def _jobs(self, plan: ParsePlan) -> Iterator[LoadableJob]:
        for source in plan.to_parse:
            live = _live_disclosures(source, plan.suppression)
            first = live[0]
            job = ParseJob(
                source=source.source_document(live),
                source_path=first.path,
                snapshot=first.provenance_date,
                camp=source.camp,
            )
            yield job, self._loader(source)

    def _loader(self, source: EnumeratedSource) -> Callable[[], bytes]:
        def load() -> bytes:
            if not source.source_document().is_parsable:
                return b""  # refused by format; the parser never reads the bytes
            path_for = self._local.blob_path_for
            assert path_for is not None
            path = path_for(local_blob_key(source.sha256))
            try:
                content = path.read_bytes()
            except FileNotFoundError:
                raise SourceLoadError(
                    PipelineFailureReason.SOURCE_MISSING, "not in this machine's blob store"
                ) from None
            if hashlib.sha256(content).hexdigest() != source.sha256:
                raise SourceLoadError(
                    PipelineFailureReason.SOURCE_INTEGRITY, "the blob does not hash to its name"
                )
            return content

        return load

    def _record(
        self, plan: ParsePlan, source: EnumeratedSource, result: ParseResult
    ) -> tuple[SourceEntry, DocumentRecord | None]:
        first = _live_disclosures(source, plan.suppression)[0]
        common: dict[str, object] = {
            "caselist": plan.caselist,
            "snapshot": first.snapshot,
            "source_sha256": source.sha256,
            "parser_version": plan.parser_version,
            "profile_version": plan.profile_version,
            "fingerprint_version": FINGERPRINT_VERSION,
            "source_format": source.source_format,
            "byte_size": source.byte_size,
        }
        if isinstance(result, ParsedDocument):
            document = DocumentRecord.from_parsed_document(
                result,
                caselist=plan.caselist,
                snapshot=first.snapshot,
                fingerprint_version=FINGERPRINT_VERSION,
                camp=source.camp,
            )
            entry = SourceEntry.model_validate(
                {**common, "outcome": SourceOutcome.PARSED, "cards": len(result.cards)}
            )
            return entry, document
        if isinstance(result, ParseFailure):
            return SourceEntry.for_failure(reason=str(result.reason), detail=result.detail, **common), None
        assert isinstance(result, WorkerFailure)
        return SourceEntry.for_failure(reason=str(result.reason), detail=result.detail, **common), None

    # -- the aggregates -----------------------------------------------------------------------

    async def _rebuild(self, plan: ParsePlan) -> StoreTotals:
        """Rewrite the index, failures and occurrence files from the per-source files and manifests.

        Built from scratch: nothing is read back from the aggregates being replaced. Each aggregate
        consults the suppression list for itself.
        """
        state = plan.suppression
        held = {source.sha256: source for source in plan.sources}
        entries = await self._store.read_entries(plan.caselist, plan.version)
        index = _index_rows(entries, held, state)
        failures = _failure_rows(entries, held, state)
        occurrences, clusters = await self._occurrence_rows(plan, entries, held, state)
        await self._store.write_aggregates(
            plan.caselist, plan.version, index=index, failures=failures, occurrences=occurrences
        )
        return StoreTotals(
            sources=len(index),
            parsed=sum(entry.outcome is SourceOutcome.PARSED for entry in index),
            unsupported=sum(entry.outcome is SourceOutcome.UNSUPPORTED for entry in index),
            failed=sum(entry.outcome is SourceOutcome.FAILED for entry in index),
            cards=sum(entry.cards for entry in index),
            occurrences=len(occurrences),
            clusters=clusters,
        )

    async def _occurrence_rows(
        self,
        plan: ParsePlan,
        entries: Sequence[SourceEntry],
        held: dict[str, EnumeratedSource],
        state: SuppressionState,
    ) -> tuple[list[OccurrenceRecord], int]:
        """One row per card per disclosure the list does not stop, and the number of clusters."""
        cards: list[ParsedCard] = []
        for entry in entries:
            source = held.get(entry.source_sha256)
            if entry.outcome is not SourceOutcome.PARSED or source is None:
                continue
            live = _live_disclosures(source, state)
            if not live:
                continue
            record = await self._store.read_document(plan.caselist, plan.version, entry.source_sha256)
            if record is None:
                raise ValueError(f"parsed source {entry.source_sha256} has no document in {plan.version}")
            document = record.to_parsed_document(live[0].path)
            cards.extend(
                card.model_copy(update={"formatting_spans": (), "font_size_spans": ()})
                for card in document.cards
            )
        cards.sort(key=lambda card: (card.provenance.source_sha256, card.provenance.first_element_index))
        placements = self._place_cards(cards)
        rows: dict[tuple[str, int, str, str | None], OccurrenceRecord] = {}
        for placement in placements:
            provenance = placement.card.provenance
            source = held[provenance.source_sha256]
            for disclosed in _live_disclosures(source, state):
                disclosure = None if source.is_camp_file else disclosure_digest(plan.caselist, disclosed.path)
                key = (
                    provenance.source_sha256,
                    provenance.first_element_index,
                    disclosed.snapshot,
                    disclosure,
                )
                rows.setdefault(
                    key,
                    OccurrenceRecord(
                        caselist=plan.caselist,
                        snapshot=disclosed.snapshot,
                        source_sha256=provenance.source_sha256,
                        parser_version=plan.parser_version,
                        profile_version=plan.profile_version,
                        fingerprint_version=FINGERPRINT_VERSION,
                        disclosure=disclosure,
                        camp=source.camp,
                        first_element_index=provenance.first_element_index,
                        last_element_index=provenance.last_element_index,
                        exact_fingerprint=placement.fingerprint,
                        cluster_id=placement.cluster_id,
                        membership=placement.membership,
                        completeness=placement.card.completeness,
                    ),
                )
        ordered = sorted(
            rows.values(),
            key=lambda row: (
                row.cluster_id,
                row.source_sha256,
                row.first_element_index,
                row.snapshot,
                row.disclosure or "",
            ),
        )
        return ordered, len({placement.cluster_id for placement in placements})

    # -- failures -----------------------------------------------------------------------------

    async def failures(self, caselist: str) -> FailureListing:
        """The current version directory's failures file, each row with a path from the manifests.

        Rows whose source the suppression list now stops are left out, so a listing made between a
        removal elsewhere and the next run does not show it.
        """
        validate_publish_target(caselist)
        version = await self._current_version(caselist)
        if version is None:
            return FailureListing(caselist=caselist, version=None, present=False)
        recorded = await self._store.read_failures(caselist, version)
        if recorded is None:
            return FailureListing(caselist=caselist, version=version, present=False)
        state = await load_suppression_state(self._suppression)
        held = {source.sha256: source for source in await enumerate_sources(self._local, caselist)}
        rows: list[FailureRow] = []
        for entry in recorded:
            source = held.get(entry.source_sha256)
            live = _live_disclosures(source, state) if source is not None else ()
            if source is not None and not live:
                continue
            rows.append(
                FailureRow(
                    sha256=entry.source_sha256,
                    path=live[0].path if live else None,
                    snapshot=entry.snapshot,
                    source_format=str(entry.source_format),
                    reason=str(entry.reason),
                    detail=entry.detail,
                    counts_toward_failure_rate=entry.outcome is SourceOutcome.FAILED,
                )
            )
        return FailureListing(caselist=caselist, version=version, present=True, rows=tuple(rows))

    async def _current_version(self, caselist: str) -> str | None:
        parser_version = self._parser.parser_version
        generations = [
            generation
            for name in await self._store.version_directories(caselist)
            for named, generation in [parse_version_directory(name)]
            if named == parser_version
        ]
        return version_directory_name(parser_version, max(generations)) if generations else None


# ------------------------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------------------------


def _live_disclosures(source: EnumeratedSource, state: SuppressionState) -> tuple[Disclosed, ...]:
    """The disclosures of `source` the suppression list does not stop, by the source or by its path.

    A camp file is checked by its digest alone, as the publisher checks a camp manifest's rows.
    """
    return tuple(
        disclosed
        for disclosed in source.disclosures
        if not state.suppresses(
            source.sha256,
            disclosure=None
            if source.caselist == OPENEV
            else disclosure_digest(source.caselist, disclosed.path),
        )
    )


def _index_rows(
    entries: Sequence[SourceEntry], held: dict[str, EnumeratedSource], state: SuppressionState
) -> list[SourceEntry]:
    """Every recorded source the manifests still store and the suppression list does not stop."""
    return [
        entry
        for entry in entries
        if (source := held.get(entry.source_sha256)) is not None and _live_disclosures(source, state)
    ]


def _failure_rows(
    entries: Sequence[SourceEntry], held: dict[str, EnumeratedSource], state: SuppressionState
) -> list[SourceEntry]:
    """The recorded sources with no document, on the same two conditions as the index."""
    return [
        entry
        for entry in entries
        if entry.outcome is not SourceOutcome.PARSED
        and (source := held.get(entry.source_sha256)) is not None
        and _live_disclosures(source, state)
    ]


def _log_run(report: ParseRunReport) -> None:
    """One line of counts. Nothing from inside a manifest or a document."""
    plan = report.plan
    totals = report.store
    logger.info(
        "caselist parse %s %s: %d in scope, %d skipped, %d suppressed, %d parsed, %d unsupported, "
        "%d failed (rate %.4f, threshold %.4f); store %d sources, %d cards, %d clusters, "
        "%d occurrences; %.1f s",
        plan.caselist,
        plan.version,
        plan.in_scope,
        plan.skipped,
        plan.suppressed,
        report.parsed,
        sum(report.unsupported.values()),
        sum(report.failed.values()),
        report.failure_rate,
        report.threshold,
        totals.sources if totals else 0,
        totals.cards if totals else 0,
        totals.clusters if totals else 0,
        totals.occurrences if totals else 0,
        report.elapsed_seconds,
    )
