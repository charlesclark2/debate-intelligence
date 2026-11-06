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
   the removal suppression list stops, or discloses only at a path a removal holds (`v1-e31-t26`,
   :func:`~debate_core.application.caselist.parse_sources.live_disclosures`). The same file
   disclosed in fourteen weeks is one parse.
4. **Parses the rest** in a bounded pool with a per-file time limit
   (:mod:`debate_core.application.caselist.parse_workers`), writing each source's file as its
   result arrives, so a run stopped part-way keeps what it finished.
5. **Rebuilds the three aggregates** from every per-source file in the directory: the index, the
   failures file and the occurrence table, with fingerprints and clusters from the `v1-e31-t04`
   service (:class:`~debate_core.application.caselist_card_stats.CardPlacer`), placing the cards
   from the placement state where it may be used (below), and writes a new placement state.

## The placement state (`v1-e31-t10`)

Every rebuild places every card of the directory again, because a new card can move an older one to
another cluster, join two, split one, or take an abbreviated card's link away. What it no longer does
every week is read every document and sign every distinct full body with MinHash: about 30% and 50
to 80% of a rebuild. Beside the aggregates it keeps the placement state
(:mod:`debate_core.application.ports.placement_state`): what placing a card reads of it, each
distinct full body's words as numbers in one vocabulary, and each body's MinHash signature. A run
places the cards of the sources the state holds from it, reads the documents of the others, and signs
only bodies it has not signed; the cards, words and signatures are the same, so the table is the
full rebuild's, byte for byte.

It is used only when it is readable, its parser, profile and fingerprint versions and its rules are
this run's, and its sources are exactly the ones the rebuild places less the ones this run added
(:class:`FullRebuildReason` names each other case). Anything else is a full rebuild, which writes a
new state, so deleting the state is always safe: a removal does (`caselist remove`), and a new
version directory starts without one. `parse.incremental_rebuild` off makes every rebuild a full one.
The run logs which way it placed the cards and why, in counts.

## The rebuild reads cards source by source (`v1-e40-t36`)

Until `v1-e40-t36` the rebuild read every card of the caselist into one list before placing any:
about 1.3 GB in the main process for 250 `hspolicy26` sources, growing with every card
(`docs/data/caselist-parse-memory.md`). It now reads one source's document at a time, gives each
card to a :class:`~debate_core.application.caselist_card_stats.CardPlacer` and keeps of it only its
place in the table: its source, its paragraph range and its completeness. What must stay whole is
what a cluster spanning sources needs, which the placer holds: a fingerprint per card, and the words of
each distinct full body for the clusterer, as numbers (`v1-e31-t10`). The rows are then ordered by a key per row and built one
at a time as the store writes them, so no list of rows is held either. The aggregates are the same
bytes as before for the same store: cards are given in the order the one list was sorted into, by
source and then first paragraph, and the rows are written in the same order.

## A failing source is an outcome

Nothing one file does stops the run. A PDF, a legacy `.doc`, a CardMirror `.cmir` or another format
V1 does not read is recorded as `UNSUPPORTED`, under the format the parser found when that is not
the one its name gives (`v1-e31-t15`); a malformed, oversized or macro-enabled package, a parse past
the time limit, a crashed worker or a parser that raised is recorded as `FAILED`, with its typed
reason. The
command's exit code is decided by :attr:`ParseRunReport.exceeds_threshold`: the share of the sources
this run tried to read that `FAILED`. Unsupported formats count on neither side of that fraction,
because PF alone discloses hundreds of PDFs and a threshold that counted them would fail every run.

**The rate is judged only in a run large enough for it to mean something** (`v1-e34-t17`): one that
tried at least `parse.failure_rate_minimum_sources` sources. Below that the failures are counted
and reported like any others, and the run is not a failure because of them
(:attr:`ParseRunReport.rate_is_judged`). A weekly pull tries only that week's new sources, which
out of season is a handful, and one unreadable file among five is 20% of nothing in particular.
The setting's description gives the measured reasons for its default.

## Removal: rebuilt, never carried forward

The aggregates are rebuilt from scratch on every run and never read back, and each of them consults
the suppression list itself, which is a required constructor argument with no default. A source the
list stops, or a disclosure of it, is in none of them after the next run, whether the removal was
made on this machine or on another. The placement state is not an aggregate read back either: it
holds only the sources the rebuild places, so a stopped source is in no state written after the stop,
and a state built before it no longer matches the sources placed, which makes the run a full one. A
removal rewrites the aggregates it reaches without the removed rows (`v1-e30-t33`) and deletes their
directories' placement states (`v1-e31-t10`). The session report of `v1-e31-t06` gives the reasons for
rebuilding rather than filtering on read.

## A table a newer build stamped

The occurrence table is rebuilt under this build's fingerprint version, so a build older than the
table's stamp would put its own clusters back. Before it writes anything, a run reads the stamps of
the table it would replace, its own directory's or the one a new directory supersedes, and is
refused with both versions named when one is newer than this build's (`v1-e34-t29`,
:mod:`debate_core.application.caselist.occurrence_table_guard`). An equal or older table is rebuilt.

## What is logged

Counts, the caselist, the version and sha256 values. Never a path, a school, a team code or a word
of a card (`docs/policies/caselist-data-use.md`, personal-data rule 4). The disclosure paths this
module handles are kept off every object's `repr`.
"""

from __future__ import annotations

import hashlib
import logging
import time
from array import array
from collections import Counter
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final, Protocol

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.occurrence_table_guard import (
    THIS_MACHINES_PARSED_STORE,
    refuse_newer_table,
)
from debate_core.application.caselist.parse_sources import (
    DisclosureKey,
    EnumeratedSource,
    camp_path_digests,
    disclosure_key,
    enumerate_sources,
    is_aggregated,
    live_disclosures,
)
from debate_core.application.caselist.parse_workers import (
    LoadableJob,
    ParseJob,
    ParseResult,
    ParseRunner,
    SourceLoadError,
    WorkerFailure,
)
from debate_core.application.caselist.parsed_publish_only import (
    refuse_unpublishable,
    refuse_what_the_list_stops,
)
from debate_core.application.caselist.publish_plan import local_blob_key, validate_publish_target
from debate_core.application.caselist.suppression import load_suppression_state
from debate_core.application.caselist_card_stats import ClusterPlacement
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
from debate_core.application.ports.placement_state import (
    PlacedBody,
    PlacedCard,
    PlacementState,
    UnreadablePlacementState,
)
from debate_core.application.ports.suppression import SuppressionList, SuppressionState
from debate_core.domain.debate_files import CardCompleteness, ParsedCard, ParsedDocument, ParseFailure
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION

__all__ = [
    "PARSE_FAILURE_RATE_EXCEEDED",
    "CaselistParseService",
    "FailureListing",
    "FullRebuildReason",
    "FailureRow",
    "ParsePlan",
    "ParseRunReport",
    "StoreTotals",
]

logger = logging.getLogger(__name__)

#: How many characters of a SHA-256 a failure listing shows.
SHA256_PREFIX_LENGTH: Final = 12

PARSE_FAILURE_RATE_EXCEEDED: Final = "PARSE_FAILURE_RATE_EXCEEDED"
"""The error code of a run whose failure rate is over the threshold: the one `caselist parse` has
always reported, and the one the parse stage of `caselist pull` records for the same thing
(`v1-e34-t17`). A verdict, on nobody's list of failures a retry may cure: the same sources fail the
same way next time."""


class PlacesCards(Protocol):
    """Places a caselist's cards given one at a time (`v1-e40-t36`), as
    :class:`~debate_core.application.caselist_card_stats.CardPlacer` does, from their documents or
    from a placement state (`v1-e31-t10`)."""

    signatures: dict[str, array[int]]

    @property
    def rules(self) -> str:
        """The digest a placement state made by this placer is stamped with."""
        ...

    @property
    def vocabulary(self) -> tuple[str, ...]: ...

    @property
    def body_words(self) -> Mapping[str, array[int]]: ...

    def adopt(self, vocabulary: Sequence[str], signatures: Mapping[str, array[int]]) -> None:
        """Begin from a placement state, before any card."""
        ...

    def add(self, card: ParsedCard) -> PlacedCard:
        """Take the next card; what placing it reads of it."""
        ...

    def add_placed(self, card: PlacedCard, words: array[int] | None) -> None:
        """Take the next card as a placement state holds it."""
        ...

    def placements(self) -> Sequence[ClusterPlacement]:
        """One placement per card given, in the order given."""
        ...


class FullRebuildReason(StrEnum):
    """Why a rebuild read every source's document rather than the placement state (`v1-e31-t10`)."""

    TURNED_OFF = "TURNED_OFF"
    """`parse.incremental_rebuild` is off."""
    NO_STATE = "NO_STATE"
    """The directory has none: its first rebuild, a new version directory, or a removal deleted it."""
    UNREADABLE = "UNREADABLE"
    VERSIONS_DIFFER = "VERSIONS_DIFFER"
    """Its parser, profile or fingerprint version is not this run's."""
    RULES_DIFFER = "RULES_DIFFER"
    """What decides its contents (markers, shingles, MinHash) is not this build's."""
    SOURCES_DIFFER = "SOURCES_DIFFER"
    """Its sources are not the ones placed less the ones this run added: a source stopped, reinstated,
    removed, or parsed by another run since it was written."""


_CardPosition = tuple[EnumeratedSource, PlacedCard]
"""What the occurrence rows need of a card besides its placement: its source, and its paragraph range
and completeness, which the placed card carries."""

_RowKey = tuple[str, str, int, str, str, int, int]
"""An occurrence row's place in the table: cluster, source, first paragraph, snapshot and disclosure,
then the card's position and the disclosure's, which keep the order the rows were made in."""


# ------------------------------------------------------------------------------------------------
# What the service returns
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ParsePlan:
    """What a run would do, decided before anything is parsed. A `--dry-run` stops here."""

    caselist: str
    version: str
    """The version directory this run writes."""
    new_version: bool
    """Whether this run starts `version`: a first parse, a parser version bump, or a new generation."""
    superseded: str | None
    """The directory a new one supersedes, left as it was: the newest the store holds below `version`.

    `None` when the run writes into the current directory, and when the store holds nothing older:
    a caselist's first parse. A parser version bump supersedes the newest generation of the parser
    before it, which before `v1-e31-t16` this said nothing about.
    """
    parser_version: str
    profile_version: str
    snapshot: str | None
    reparse: bool
    sources: tuple[EnumeratedSource, ...] = field(repr=False)
    """Every source the manifests store, whatever the snapshot asked for: the aggregates' input."""
    in_scope: int
    """Sources disclosed in the requested snapshot, or every source when none was asked for."""
    suppressed: int
    """In-scope sources the suppression list stops, wholly or in every disclosure, counting a
    disclosure at a path a removal holds as stopped (`v1-e31-t26`): no live disclosure is left."""
    to_parse: tuple[EnumeratedSource, ...] = field(repr=False)
    suppression: SuppressionState = field(repr=False)

    @property
    def skipped(self) -> int:
        """In-scope sources already parsed under this run's skip key, which are not parsed again."""
        return self.in_scope - self.suppressed - len(self.to_parse)


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
    minimum_sources: int = 1
    """How many sources a run must have tried before its failure rate is judged
    (`parse.failure_rate_minimum_sources`). One, here, judges every run that tried anything."""
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
    def tried(self) -> int:
        """Sources this run tried to read: those handed to the parser, less the unsupported formats."""
        return self.attempted - sum(self.unsupported.values())

    @property
    def failure_rate(self) -> float:
        """Failed sources over the sources this run tried to read; unsupported formats in neither."""
        return sum(self.failed.values()) / self.tried if self.tried else 0.0

    @property
    def rate_is_judged(self) -> bool:
        """Whether this run tried enough sources for its failure rate to decide anything.

        At least :attr:`minimum_sources`. Below that the rate is still reported, and
        :attr:`exceeds_threshold` is false whatever it is (`v1-e34-t17`).
        """
        return self.tried >= self.minimum_sources

    @property
    def exceeds_threshold(self) -> bool:
        return self.rate_is_judged and self.failure_rate > self.threshold


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
    """False when there is no failures file: never parsed, or deleted by a removal made by a build from
    before `v1-e30-t33`, which deleted the aggregates until the next run instead of rewriting them."""
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
        card_placer: Makes a new placer for each rebuild: the `v1-e31-t04` fingerprinting and
            clustering, given the cards one at a time,
            :meth:`~debate_core.application.caselist_card_stats.CaselistCardStatsService.placer`.
        failure_rate_threshold: The `parse.failure_rate_threshold` setting.
        failure_rate_minimum_sources: The `parse.failure_rate_minimum_sources` setting: how many
            sources a run must have tried before its failure rate is judged. Required, with no
            default here, so that the one default is the setting's.
        fetch_missing: In bucket mode (`v1-e40-t04`), fetches from the bucket's `raw/` the sources a
            run is about to parse and this machine does not hold, before any is parsed: none in an
            ordinary week, all of them in a full re-parse on a restored copy. `None` reads this
            machine's blob store alone, as every parse before it did.
        incremental_rebuild: The `parse.incremental_rebuild` setting (`v1-e31-t10`): whether the
            rebuild may place from the placement state. Off, every rebuild reads every document, and
            still writes a new state.
    """

    def __init__(
        self,
        *,
        local: LocalEvidence,
        store: ParsedStore,
        parser: DebateFileParser,
        runner: ParseRunner,
        suppression: SuppressionList,
        card_placer: Callable[[], PlacesCards],
        failure_rate_threshold: float,
        failure_rate_minimum_sources: int,
        clock: Callable[[], float] = time.monotonic,
        fetch_missing: Callable[[str, Sequence[EnumeratedSource]], Awaitable[object]] | None = None,
        incremental_rebuild: bool = True,
    ) -> None:
        if failure_rate_minimum_sources < 1:
            raise ValueError("failure_rate_minimum_sources must be at least 1")
        if local.blob_path_for is None:
            raise ValueError(
                "the parse pipeline reads sources from files: give LocalEvidence a blob_path_for"
            )
        self._local = local
        self._fetch_missing = fetch_missing
        self._store = store
        self._parser = parser
        self._runner = runner
        self._suppression = suppression
        self._card_placer = card_placer
        self._threshold = failure_rate_threshold
        self._minimum_sources = failure_rate_minimum_sources
        self._clock = clock
        self._incremental = incremental_rebuild

    # -- planning -----------------------------------------------------------------------------

    async def plan(self, caselist: str, *, snapshot: str | None = None, reparse: bool = False) -> ParsePlan:
        """Work out what a run would parse and where it would write, writing nothing."""
        validate_publish_target(caselist, snapshot)
        state = await load_suppression_state(self._suppression)
        sources = await enumerate_sources(self._local, caselist)
        parser_version, profile_version = self._parser.parser_version, self._parser.profile_version
        version, new_version, superseded, recorded = await self._choose_version(
            caselist, parser_version, profile_version, reparse=reparse
        )
        done = {entry.skip_key for entry in recorded if not entry.retried_next_run}
        in_scope = [
            source
            for source in sources
            if snapshot is None or any(disclosed.snapshot == snapshot for disclosed in source.disclosures)
        ]
        live = [source for source in in_scope if live_disclosures(source, state)]
        to_parse = tuple(
            source for source in live if skip_key(source.sha256, parser_version, profile_version) not in done
        )
        return ParsePlan(
            caselist=caselist,
            version=version,
            new_version=new_version,
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

    async def full_parse_owed(self, caselist: str) -> str | None:
        """The running parser version, when `caselist` has sources and the store has no directory of it.

        What the weekly run asks of every caselist it follows (`v1-e40-t08`): the first run on a new
        parser version parses each in full before its index stage, rather than leaving it for the
        next import into the caselist. A caselist with no source owes nothing.
        """
        parser_version = self._parser.parser_version
        names = await self._store.version_directories(caselist)
        if any(parse_version_directory(name)[0] == parser_version for name in names):
            return None
        return parser_version if await enumerate_sources(self._local, caselist) else None

    async def _choose_version(
        self, caselist: str, parser_version: str, profile_version: str, *, reparse: bool
    ) -> tuple[str, bool, str | None, tuple[SourceEntry, ...]]:
        """The directory to write, whether it is new, what it supersedes, and what it already holds.

        The newest generation of this parser version is reused when every entry in it has this
        run's skip key. A forced re-parse, or an entry parsed under another profile, starts a new
        generation instead, so the old directory is never written to. A parser version the store
        has no directory for starts its first, superseding the newest directory that sorts below it
        (`v1-e31-t16`): never one a newer build wrote.
        """
        names = await self._store.version_directories(caselist)
        generations = sorted(
            generation
            for name in names
            for named, generation in [parse_version_directory(name)]
            if named == parser_version
        )
        if not generations:
            first = version_directory_name(parser_version)
            earlier = [name for name in names if parse_version_directory(name) < (parser_version, 1)]
            return first, True, (max(earlier, key=parse_version_directory) if earlier else None), ()
        newest = version_directory_name(parser_version, generations[-1])
        recorded = await self._store.read_entries(caselist, newest)
        current = all(
            entry.skip_key == skip_key(entry.source_sha256, parser_version, profile_version)
            for entry in recorded
        )
        if reparse or not current:
            return version_directory_name(parser_version, generations[-1] + 1), True, newest, ()
        return newest, False, None, recorded

    # -- running ------------------------------------------------------------------------------

    def dry_run(self, plan: ParsePlan) -> ParseRunReport:
        """The report a `--dry-run` prints: the plan's counts, nothing parsed or written."""
        return ParseRunReport(
            plan=plan,
            applied=False,
            threshold=self._threshold,
            workers=self._runner.workers,
            minimum_sources=self._minimum_sources,
        )

    async def run(self, plan: ParsePlan, *, progress: Callable[[int], None] | None = None) -> ParseRunReport:
        """Parse what `plan` names, then rebuild the version directory's aggregates.

        `progress`, if given, is called with how many of `plan.to_parse` are done after each one is
        written (`v1-e40-t32`): a count, never which source.

        Raises :class:`~debate_core.application.caselist.occurrence_table_guard.NewerFingerprintTable`,
        having written nothing, when the table this run would replace is stamped with a newer
        fingerprint version than this build's (`v1-e34-t29`).
        """
        await self._refuse_a_newer_table(plan)
        if self._fetch_missing is not None:
            await self._fetch_missing(plan.caselist, plan.to_parse)
        started = self._clock()
        by_digest = {source.sha256: source for source in plan.sources}
        added: set[str] = set()
        parsed = cards = 0
        unsupported: Counter[str] = Counter()
        failed: Counter[str] = Counter()
        for done, (job, result) in enumerate(self._runner.run(self._parser, self._jobs(plan)), start=1):
            source = by_digest[job.source.sha256]
            entry, document = self._record(plan, source, result)
            await self._store.write_source(plan.caselist, plan.version, entry, document)
            added.add(source.sha256)
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
            if progress is not None:
                progress(done)
        totals = await self._rebuild(plan, frozenset(added))
        report = ParseRunReport(
            plan=plan,
            applied=True,
            threshold=self._threshold,
            workers=self._runner.workers,
            minimum_sources=self._minimum_sources,
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
            live = live_disclosures(source, plan.suppression)
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
        first = live_disclosures(source, plan.suppression)[0]
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
            if result.source_format is not None:
                # The bytes are another format than the manifest's extension says: a `.cmir`
                # uploaded as `.docx` is counted as CMIR, not DOCX (`v1-e31-t15`).
                common["source_format"] = result.source_format
            return SourceEntry.for_failure(reason=str(result.reason), detail=result.detail, **common), None
        assert isinstance(result, WorkerFailure)
        return SourceEntry.for_failure(reason=str(result.reason), detail=result.detail, **common), None

    # -- the aggregates -----------------------------------------------------------------------

    async def _refuse_a_newer_table(self, plan: ParsePlan) -> None:
        """Ask :func:`~debate_core.application.caselist.occurrence_table_guard.refuse_newer_table`
        of the table this run would replace as the caselist's current one: its own directory's, or,
        for a new directory, the one it supersedes."""
        for version in (plan.version, plan.superseded):
            if version is None:
                continue
            stamps = await self._store.read_occurrence_stamps(plan.caselist, version)
            refuse_newer_table(
                stamps or (), caselist=plan.caselist, version=version, store=THIS_MACHINES_PARSED_STORE
            )

    async def _rebuild(self, plan: ParsePlan, added: frozenset[str] = frozenset()) -> StoreTotals:
        """Rewrite the index, failures and occurrence files from the per-source files and manifests,
        then the placement state.

        Nothing is read back from the aggregates being replaced, and each aggregate consults the
        suppression list for itself. The cards are placed from the placement state where it may be
        used (:meth:`_usable_state`), and from each source's document otherwise; `added` are the
        sources this run wrote, whose documents are read in any case.
        """
        state = plan.suppression
        held = {source.sha256: source for source in plan.sources}
        entries = await self._store.read_entries(plan.caselist, plan.version)
        index = _index_rows(entries, held, state)
        failures = _failure_rows(entries, held, state)
        placed_sources = _placed_sources(entries, held, state)
        placer = self._card_placer()
        stored, reason = await self._usable_state(plan, placer, placed_sources, added)
        if stored is not None:
            placer.adopt(stored.vocabulary, _signatures(stored))
        occurrences, rows, clusters, kept = await self._occurrence_rows(
            plan, placed_sources, state, placer, stored
        )
        await self._store.write_aggregates(
            plan.caselist, plan.version, index=index, failures=failures, occurrences=occurrences
        )
        await self._store.write_placement_state(
            plan.caselist,
            plan.version,
            PlacementState(
                parser_version=plan.parser_version,
                profile_version=plan.profile_version,
                fingerprint_version=FINGERPRINT_VERSION,
                rules=placer.rules,
                vocabulary=placer.vocabulary,
                sources=kept,
                bodies={
                    fingerprint: PlacedBody(words, placer.signatures.get(fingerprint))
                    for fingerprint, words in placer.body_words.items()
                },
            ),
        )
        read = sum(1 for source in placed_sources if stored is None or source.sha256 not in stored.sources)
        if reason is None:
            logger.info(
                "caselist parse %s %s: placed from the placement state, %d of %d placed sources read",
                plan.caselist,
                plan.version,
                read,
                len(placed_sources),
            )
        else:
            logger.info(
                "caselist parse %s %s: rebuilt in full (%s), %d placed sources read",
                plan.caselist,
                plan.version,
                reason,
                read,
            )
        return StoreTotals(
            sources=len(index),
            parsed=sum(entry.outcome is SourceOutcome.PARSED for entry in index),
            unsupported=sum(entry.outcome is SourceOutcome.UNSUPPORTED for entry in index),
            failed=sum(entry.outcome is SourceOutcome.FAILED for entry in index),
            cards=sum(entry.cards for entry in index),
            occurrences=rows,
            clusters=clusters,
        )

    async def _usable_state(
        self,
        plan: ParsePlan,
        placer: PlacesCards,
        placed_sources: Sequence[EnumeratedSource],
        added: frozenset[str],
    ) -> tuple[PlacementState | None, FullRebuildReason | None]:
        """The directory's placement state when it may be used, or why it may not (the PM's ruling of
        2026-11-06, item 2): it is used only when it is readable, its stamps are this run's, and its
        sources are exactly the ones placed less the ones this run added."""
        if not self._incremental:
            return None, FullRebuildReason.TURNED_OFF
        try:
            stored = await self._store.read_placement_state(plan.caselist, plan.version)
        except UnreadablePlacementState:
            return None, FullRebuildReason.UNREADABLE
        if stored is None:
            return None, FullRebuildReason.NO_STATE
        if (stored.parser_version, stored.profile_version, stored.fingerprint_version) != (
            plan.parser_version,
            plan.profile_version,
            FINGERPRINT_VERSION,
        ):
            return None, FullRebuildReason.VERSIONS_DIFFER
        if stored.rules != placer.rules:
            return None, FullRebuildReason.RULES_DIFFER
        if set(stored.sources) != {source.sha256 for source in placed_sources} - added:
            return None, FullRebuildReason.SOURCES_DIFFER
        return stored, None

    async def _occurrence_rows(
        self,
        plan: ParsePlan,
        placed_sources: Sequence[EnumeratedSource],
        state: SuppressionState,
        placer: PlacesCards,
        stored: PlacementState | None,
    ) -> tuple[Iterator[OccurrenceRecord], int, int, dict[str, tuple[PlacedCard, ...]]]:
        """One row per card per disclosure the list does not stop, made as the store writes them; how
        many rows; how many clusters; and each placed source's cards as the placement state keeps them.

        A disclosure is one row however many snapshots list it, spanning the first to the latest.
        Each source's cards are given to the placer in turn, in the order of one list of every card
        sorted by source and first paragraph: from the placement state when it holds the source, and
        from its document otherwise, which is then let go (this module's docstring).
        """
        cards: list[_CardPosition] = []
        kept: dict[str, tuple[PlacedCard, ...]] = {}
        for source in placed_sources:
            from_state = stored.sources.get(source.sha256) if stored is not None else None
            if from_state is not None and stored is not None:
                for card in from_state:
                    body = (
                        stored.bodies.get(card.fingerprint)
                        if card.completeness is CardCompleteness.FULL
                        else None
                    )
                    placer.add_placed(card, None if body is None else body.words)
                placed = from_state
            else:
                live = live_disclosures(source, state)
                placed = tuple(placer.add(card) for card in await self._cards_of(plan, source, live[0].path))
            kept[source.sha256] = placed
            cards.extend((source, card) for card in placed)
        placements = placer.placements()
        spans: dict[str, list[tuple[str | None, str, str, tuple[str, ...]]]] = {}
        order: list[_RowKey] = []
        for position, ((source, card), placement) in enumerate(zip(cards, placements, strict=True)):
            if source.sha256 not in spans:
                spans[source.sha256] = _disclosure_spans(source, state)
            for span, (disclosure, first, _, _) in enumerate(spans[source.sha256]):
                order.append(
                    (
                        placement.cluster_id,
                        source.sha256,
                        card.first_element,
                        first,
                        disclosure or "",
                        position,
                        span,
                    )
                )
        order.sort()

        def rows() -> Iterator[OccurrenceRecord]:
            for *_, position, span in order:
                source, card = cards[position]
                placement = placements[position]
                disclosure, first, last, camp_paths = spans[source.sha256][span]
                yield OccurrenceRecord(
                    caselist=plan.caselist,
                    snapshot=first,
                    last_snapshot=last,
                    source_sha256=source.sha256,
                    parser_version=plan.parser_version,
                    profile_version=plan.profile_version,
                    fingerprint_version=FINGERPRINT_VERSION,
                    disclosure=disclosure,
                    camp=source.camp,
                    first_element_index=card.first_element,
                    last_element_index=card.last_element,
                    exact_fingerprint=placement.fingerprint,
                    cluster_id=placement.cluster_id,
                    membership=placement.membership,
                    completeness=card.completeness,
                    camp_path_disclosures=camp_paths,
                )

        return rows(), len(order), len({placement.cluster_id for placement in placements}), kept

    async def _cards_of(self, plan: ParsePlan, source: EnumeratedSource, path: str) -> list[ParsedCard]:
        """One parsed source's cards by first paragraph, its document let go once they are read."""
        record = await self._store.read_document(plan.caselist, plan.version, source.sha256)
        if record is None:
            raise ValueError(f"parsed source {source.sha256} has no document in {plan.version}")
        document = record.to_parsed_document(path)
        if document.source_sha256 != source.sha256:
            raise ValueError(f"parsed source {source.sha256}'s document names another source")
        return sorted(document.cards, key=lambda card: card.provenance.first_element_index)

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
            live = live_disclosures(source, state) if source is not None else ()
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

    # -- publishing without a rebuild ---------------------------------------------------------

    async def publishable_version(self, caselist: str) -> str:
        """The current version directory, for `caselist parse --publish-only` to publish as it is.

        The newest generation of the running parser version, which is what `--publish` publishes
        once it has rebuilt (`v1-e31-t30`). Raises a
        :class:`~debate_core.application.caselist.parsed_publish_only.PublishOnlyRefused`, having
        written nothing, when there is none, when it is incomplete, when it is not what this
        build's rebuild would publish
        (:func:`~debate_core.application.caselist.parsed_publish_only.refuse_unpublishable`), or
        when its aggregates name something this service's suppression list now stops or holds
        (:func:`~debate_core.application.caselist.parsed_publish_only.refuse_what_the_list_stops`).
        Build the service over the list the publisher is given, so that the list asked is the
        target environment's.
        """
        validate_publish_target(caselist)
        version = await refuse_unpublishable(
            self._store,
            caselist,
            await self._current_version(caselist),
            parser_version=self._parser.parser_version,
            profile_version=self._parser.profile_version,
        )
        await refuse_what_the_list_stops(
            self._store,
            caselist,
            version,
            sources=await enumerate_sources(self._local, caselist),
            state=await load_suppression_state(self._suppression),
        )
        return version

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


def _disclosure_spans(
    source: EnumeratedSource, state: SuppressionState
) -> list[tuple[str | None, str, str, tuple[str, ...]]]:
    """`(disclosure, first snapshot, latest snapshot, camp paths)` for each live disclosure of `source`.

    A caselist disclosure is a path, named by its digest: listed in fourteen weekly manifests, it
    is still one disclosure. A camp file has no disclosure, so each release is its own, and carries
    the camp path digest of each live path of the file in that release (`v1-e33-t07`).
    """
    spans: dict[DisclosureKey, tuple[str, str]] = {}
    for disclosed in live_disclosures(source, state):
        key = disclosure_key(source, disclosed)
        first, last = spans.get(key, (disclosed.snapshot, disclosed.snapshot))
        spans[key] = (min(first, disclosed.snapshot), max(last, disclosed.snapshot))
    return [
        (disclosure, first, last, camp_path_digests(source, state, first))
        for (disclosure, _), (first, last) in spans.items()
    ]


def _placed_sources(
    entries: Sequence[SourceEntry], held: dict[str, EnumeratedSource], state: SuppressionState
) -> list[EnumeratedSource]:
    """The sources whose cards are placed, by SHA-256: parsed, stored by the manifests, and disclosed
    at a path the list neither stops nor holds. The sources a placement state is built from."""
    placed: list[EnumeratedSource] = []
    for entry in sorted(entries, key=lambda entry: entry.source_sha256):
        source = held.get(entry.source_sha256)
        if entry.outcome is SourceOutcome.PARSED and source is not None and live_disclosures(source, state):
            placed.append(source)
    return placed


def _signatures(stored: PlacementState) -> dict[str, array[int]]:
    return {
        fingerprint: body.signature
        for fingerprint, body in stored.bodies.items()
        if body.signature is not None
    }


def _index_rows(
    entries: Sequence[SourceEntry], held: dict[str, EnumeratedSource], state: SuppressionState
) -> list[SourceEntry]:
    """Every recorded source the manifests still store and the suppression list does not stop."""
    return [entry for entry in entries if is_aggregated(held.get(entry.source_sha256), state)]


def _failure_rows(
    entries: Sequence[SourceEntry], held: dict[str, EnumeratedSource], state: SuppressionState
) -> list[SourceEntry]:
    """The recorded sources with no document, on the same two conditions as the index."""
    return [
        entry
        for entry in entries
        if entry.outcome is not SourceOutcome.PARSED and is_aggregated(held.get(entry.source_sha256), state)
    ]


def _log_run(report: ParseRunReport) -> None:
    """One line of counts. Nothing from inside a manifest or a document."""
    plan = report.plan
    totals = report.store
    logger.info(
        "caselist parse %s %s: %d in scope, %d skipped, %d suppressed, %d parsed, %d unsupported, "
        "%d failed (rate %.4f, threshold %.4f, %s); store %d sources, %d cards, %d clusters, "
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
        "judged" if report.rate_is_judged else f"not judged under {report.minimum_sources} tried",
        totals.sources if totals else 0,
        totals.cards if totals else 0,
        totals.clusters if totals else 0,
        totals.occurrences if totals else 0,
        report.elapsed_seconds,
    )
