"""LandscapeRunService: one caselist's landscape report, from the store to the bucket (`v1-e32-t05`).

`debate-research landscape report` is a thin adapter over this, so the weekly sync (E34) can run the
same use case. One run, for one caselist at one weekly snapshot (the newest unless one is named):

1. **Resolves** the caselist among those this machine holds weekly manifests of, the snapshot among
   that caselist's weekly snapshots, and the topic and taxonomy `topics.yaml` puts it on. A name the
   store or the topic map does not have is a :class:`LandscapeRequestRefused`, which the command
   exits 2 on, naming the known values or the file to edit.
2. **Reads** the caselist's parsed sources on the topic as the store stood at the snapshot
   (:func:`~debate_core.application.landscape_seeding.read_seed_sources`).
3. **Classifies** them incrementally with `v1-e32-t02`'s cache
   (:class:`~debate_core.application.position_classification.PositionClassificationService`), which
   writes the cache and the review queue. Until `v1-e32-t07` the stage is deterministic and the only
   model mode is :attr:`LandscapeModelMode.NONE`, so the run's model budget is 0 items; a stage that
   sent more is refused with :class:`ModelBudgetExceeded` after the queue is written and before the
   report is, so nothing is written or published from it.
4. **Builds** `v1-e32-t03`'s bundle, with `v1-e32-t11`'s CP texts, alternatives, roles of the ballot and
   overview counts when a source of them is wired (the run's reading of each source's own paragraphs,
   cached as derived fields; a dry run writes no cache), with `v1-e32-t04`'s trends and per-school view
   (given each of the caselist's weekly snapshots and the topic `topics.yaml` puts it on, so a trend
   stops at a topic change, and the topic's range, so the report can say whether its history is a full
   topic cycle), with `v1-e32-t09`'s per-round aff assignments when a source of them is wired (until
   then the report shows the affirmative side's unidentified share), and `v1-e34-t03`'s staleness hook
   given the sync run log, so a run the daily download cap held back makes the report stale whatever its
   snapshot's age (the PM's ruling of 2026-10-24).
5. **Scans** the bundle (:mod:`debate_core.application.landscape_scan`) and returns every hit: the
   per-school view, which names schools and team codes by design, for paths only.
6. **Writes** the bundle to `<data dir>/reports/landscape/<caselist>/<snapshot>/`, or `--out`.
7. **Publishes**, when asked, to `reports/landscape/<caselist>/<snapshot>/` in the environment's
   bucket through the E29 blob-store port, uploading only the files whose SHA-256 differs from the
   one the bucket recorded. A publish goes ahead only when every scan hit has been accepted, now or
   in an earlier run (:class:`PublishRefusal`); the run's result says which, and the bundle is still
   written locally for the operator to read.

A **dry run** writes nothing anywhere: not the cache, not the queue, not the bundle, not the
acceptance log, not the bucket. It reads all of them and says what a run would do, with each
planned key and whether it would be uploaded.

## What it never does

It never presigns a URL, never writes outside the `reports/landscape/` prefix, and never deletes.
The bucket is the one :class:`~debate_core.application.ports.evidence_store.EvidenceObjectStore`
the composition root builds for `DEBATE_ENV`, which is private and encrypted by its Terraform.
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Final, Protocol

from debate_core.application.aff_assignment import AffAssignmentsForReport
from debate_core.application.analytic_texts import AnalyticTextsForReport
from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.publish_plan import manifest_prefix, snapshot_of_manifest_key
from debate_core.application.errors import DomainError, NotFound
from debate_core.application.landscape_bundle_files import REPORTS_PREFIX
from debate_core.application.landscape_report import (
    SCHOOL_VIEW_FILES,
    LandscapeReportInputs,
    LandscapeReportService,
    landscape_cards,
    overrides_digest,
)
from debate_core.application.landscape_scan import (
    ScanAcceptance,
    ScanAcceptanceLog,
    ScanHit,
    hits_digest,
    pending_hits,
    scan_report,
)
from debate_core.application.landscape_seeding import SeedReading, read_seed_sources
from debate_core.application.landscape_staleness import (
    DEFAULT_STALE_AFTER_DAYS,
    LandscapeStaleness,
    LandscapeStalenessCheck,
)
from debate_core.application.ports.classification_store import CachedClassification, ClassificationStore
from debate_core.application.ports.evidence_store import EvidenceObjectStore, validate_object_key
from debate_core.application.ports.parsed_store import ParsedStore, parse_version_directory
from debate_core.application.ports.suppression import SuppressionList
from debate_core.application.ports.taxonomy_repository import TaxonomyRepository
from debate_core.application.position_classification import ClassificationRun, PositionClassificationService
from debate_core.application.sync_runs import SyncRunLog
from debate_core.arguments.landscape.analytic_texts import CounterplanActors
from debate_core.arguments.landscape.review_queue import DEFAULT_REVIEW_THRESHOLD, ReviewRow
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import OverrideRules, PositionClassification
from debate_core.domain.landscape_report import LandscapeCard, LandscapeReport
from debate_core.domain.landscape_schools import SchoolView
from debate_core.domain.landscape_trends import LandscapeTrends

__all__ = [
    "BUNDLE_FILES",
    "DEFAULT_MAX_MODEL_ITEMS",
    "REPORTS_PREFIX",
    "AffAssignmentsFromReading",
    "AnalyticTextsFromReading",
    "LandscapeModelMode",
    "LandscapeRequestRefused",
    "LandscapeRunRequest",
    "LandscapeRunResult",
    "LandscapeRunService",
    "ModelBudgetExceeded",
    "NoTopicMapping",
    "NothingToReport",
    "PlannedUpload",
    "PositionClassifier",
    "PublishAction",
    "PublishOutcome",
    "PublishRefusal",
    "PublishedObjectMismatch",
    "ScanResult",
    "UnknownCaselist",
    "UnknownSnapshot",
    "report_key",
]

BUNDLE_FILES: Final = (
    "positions.csv",
    "top_cards.csv",
    "impact_cards.csv",
    "trends.csv",
    "schools.csv",
    "schools.md",
    "report.md",
)
"""The bundle's files, in the order they are uploaded: the page a person opens goes last.

`schools.csv` and `schools.md` are `v1-e32-t04`'s per-school view, the only files naming schools and
team codes: like the rest, they go to the local `reports/` directory and the private bucket only."""

DEFAULT_MAX_MODEL_ITEMS: Final = 0
"""With no model stage, a run may send no item to a model. `v1-e32-t07` sets the real bound."""

DRY_RUN_QUEUE_LOCATION: Final = "(not written: dry run)"


class LandscapeModelMode(StrEnum):
    """`--model-mode` for a landscape run. `v1-e32-t07` adds `replay` and `live`."""

    NONE = "none"
    """Deterministic classification only: no model is called, and no Bedrock access is needed."""


class LandscapeRequestRefused(DomainError):
    """The run named a caselist, snapshot or topic the store or the topic map does not have.

    The command exits 2 on one of these, as on any other wrong command line, with
    :attr:`known` or :attr:`file_to_edit` in its details.
    """

    def __init__(self, message: str, *, known: Sequence[str] = (), file_to_edit: str | None = None) -> None:
        super().__init__(message)
        self.known: tuple[str, ...] = tuple(known)
        self.file_to_edit = file_to_edit


class UnknownCaselist(LandscapeRequestRefused):
    """No weekly manifest of this caselist is on this machine."""


class UnknownSnapshot(LandscapeRequestRefused):
    """The caselist has no weekly snapshot of this date on this machine."""


class NoTopicMapping(LandscapeRequestRefused):
    """`topics.yaml` puts the snapshot on no topic, or on a topic with no taxonomy yet."""


class NothingToReport(DomainError):
    """The store holds no parsed source on the topic through the snapshot: an empty store is no report."""


class ModelBudgetExceeded(DomainError):
    """The classification stage sent more items to the model than the run allows."""

    def __init__(self, sent: int, allowed: int) -> None:
        super().__init__(
            f"the classification stage sent {sent} item(s) to the model, over the run's limit of {allowed}; "
            "the review queue is written, and no report was written or published"
        )
        self.sent = sent
        self.allowed = allowed


class PublishedObjectMismatch(DomainError):
    """The bucket recorded a digest for an upload that is not the digest of the file sent."""


class PositionClassifier(Protocol):
    """What classifies a reading: `v1-e32-t02`'s service, and `v1-e32-t07`'s with a model stage."""

    async def classify(self, reading: SeedReading) -> ClassificationRun: ...


class AffAssignmentsFromReading(Protocol):
    """`v1-e32-t09`'s per-round affs, built from the same reading and classifications as the report.

    :class:`~debate_core.application.aff_assignment.AffAssignmentService` is the one there is. `writes`
    is False in a dry run, which writes no cache of its own either.
    """

    async def assignments(
        self,
        *,
        reading: SeedReading,
        through: date,
        classifications: Sequence[PositionClassification],
        taxonomy: Taxonomy,
        writes: bool,
    ) -> AffAssignmentsForReport: ...


class AnalyticTextsFromReading(Protocol):
    """`v1-e32-t11`'s CP texts, alternatives, roles of the ballot and overviews, read for the run's reading.

    :class:`~debate_core.application.analytic_texts.AnalyticTextService` is the one there is. `writes` is
    False in a dry run, which writes no cache of its own either.
    """

    async def report_inputs(
        self,
        *,
        reading: SeedReading,
        taxonomy: Taxonomy,
        overrides: OverrideRules,
        actors: CounterplanActors | None,
        writes: bool,
    ) -> AnalyticTextsForReport: ...


class PublishAction(StrEnum):
    UPLOAD = "UPLOAD"
    """Not in the bucket, or there with a different or unrecorded digest."""
    UNCHANGED = "UNCHANGED"
    """In the bucket with this file's digest: skipped."""


class PublishRefusal(StrEnum):
    """Why a publish did not go ahead. The bundle is written locally either way."""

    SCAN_HITS_NOT_ACCEPTED = "SCAN_HITS_NOT_ACCEPTED"
    """The scan found hits no acceptance covers, and no digest was given."""
    SCAN_DIGEST_STALE = "SCAN_DIGEST_STALE"
    """A digest was given, but it is not the digest of the hits this run found."""


@dataclass(frozen=True, slots=True)
class LandscapeRunRequest:
    caselist: str
    snapshot: date | None = None
    """None for the newest weekly snapshot."""
    out: Path | None = None
    """Where to write the bundle; None for `<data dir>/reports/landscape/<caselist>/<snapshot>/`."""
    publish: bool = False
    dry_run: bool = False
    accept_scan_hits: str | None = None
    """The digest the operator read the hits under, from an earlier run's refusal."""
    model_mode: LandscapeModelMode = LandscapeModelMode.NONE
    top_cards: int | None = None
    """Most-read cards per position; None for the report's default. `files suggest` asks for its `--top`."""


@dataclass(frozen=True, slots=True)
class ScanResult:
    hits: tuple[ScanHit, ...] = field(repr=False)
    pending: tuple[ScanHit, ...] = field(repr=False)
    """The hits no earlier acceptance covered when the run started."""
    digest: str
    """:func:`~debate_core.application.landscape_scan.hits_digest` of :attr:`pending`."""
    accepted_now: bool = False
    """This run recorded the operator's acceptance of :attr:`pending`."""
    acceptance_log: str | None = None
    """Where an acceptance was recorded, when this run recorded one."""


@dataclass(frozen=True, slots=True)
class PlannedUpload:
    name: str
    key: str
    sha256: str
    size: int
    action: PublishAction | None
    """None when the bucket was not asked: a dry run with no publish."""


@dataclass(frozen=True, slots=True)
class PublishOutcome:
    planned: tuple[PlannedUpload, ...]
    refused: PublishRefusal | None = None
    uploaded: tuple[str, ...] = ()
    """The keys this run put in the bucket."""

    @property
    def unchanged(self) -> tuple[str, ...]:
        return tuple(one.key for one in self.planned if one.action is PublishAction.UNCHANGED)


@dataclass(frozen=True, slots=True)
class LandscapeRunResult:
    caselist: str
    snapshot: date
    report_date: date
    topic_id: str
    taxonomy_version: str
    overrides_digest: str
    parsed_version: str
    model_mode: LandscapeModelMode
    dry_run: bool
    classification: ClassificationRun = field(repr=False)
    report: LandscapeReport = field(repr=False)
    trends: LandscapeTrends = field(repr=False)
    schools: SchoolView = field(repr=False)
    staleness: LandscapeStaleness
    aff_assignments: int
    directory: Path
    files: tuple[Path, ...]
    written: bool
    scan: ScanResult
    publish: PublishOutcome | None = None
    """None when no publish was asked for: `--no-publish`, and a dry run without `--publish`."""
    analytic_texts: AnalyticTextsForReport | None = field(default=None, repr=False)
    """`v1-e32-t11`'s reading of the analytic texts and its counts; None when no source of them is wired."""
    taxonomy: Taxonomy | None = field(default=None, repr=False)
    """The taxonomy the report counted under, for a reader of :attr:`report` (`files suggest`)."""
    cards: tuple[LandscapeCard, ...] = field(default=(), repr=False)
    """Every card the report ranked from, with its cluster and its headings as the matcher reads them."""
    bundle_files: Mapping[str, str] = field(default_factory=dict[str, str], repr=False)
    """The bundle's files as rendered, by name: what the scan read, in memory, written or not. A dry run's
    scan is counted by section from them (`v1-e32-t16`); they are never logged."""

    @property
    def model_calls(self) -> int:
        return self.classification.counts.model_calls


def report_key(caselist: str, snapshot: date, name: str) -> str:
    """`reports/landscape/<caselist>/<snapshot>/<name>`: the bundle file's key in the bucket."""
    return validate_object_key(f"{REPORTS_PREFIX}/{caselist}/{snapshot.isoformat()}/{name}")


ClassifierFactory = Callable[[ClassificationStore], PositionClassifier]
"""Builds the classifier over the store a run may write: the cache, or a dry run's read-only view."""


class LandscapeRunService:
    """One caselist's landscape report: resolve, classify, build, scan, write and publish."""

    def __init__(
        self,
        *,
        taxonomies: TaxonomyRepository,
        config_dir: Path,
        parsed_store: ParsedStore,
        local: LocalEvidence,
        suppression: SuppressionList,
        classifications: ClassificationStore,
        objects: EvidenceObjectStore,
        run_log: SyncRunLog | None,
        reports_dir: Path,
        acceptances: ScanAcceptanceLog,
        today: Callable[[], date],
        bucket: Callable[[], EvidenceObjectStore] | None = None,
        aff_assignments: AffAssignmentsFromReading | None = None,
        analytic_texts: AnalyticTextsFromReading | None = None,
        classifier: ClassifierFactory | None = None,
        stale_after_days: int = DEFAULT_STALE_AFTER_DAYS,
        review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
        max_model_items: int = DEFAULT_MAX_MODEL_ITEMS,
    ) -> None:
        self._taxonomies = taxonomies
        self._config_dir = config_dir
        self._parsed = parsed_store
        self._local = local
        self._suppression = suppression
        self._classifications = classifications
        self._objects = objects
        self._run_log = run_log
        self._reports_dir = reports_dir
        self._acceptances = acceptances
        self._today = today
        self._bucket = bucket
        self._aff = aff_assignments
        self._texts = analytic_texts
        self._classifier: ClassifierFactory = classifier or self._deterministic
        self._stale_after_days = stale_after_days
        self._threshold = review_threshold
        self._max_model_items = max_model_items

    def _deterministic(self, store: ClassificationStore) -> PositionClassifier:
        """`v1-e32-t02`'s classifier, the only one until `v1-e32-t07`."""
        return PositionClassificationService(
            taxonomies=self._taxonomies, store=store, review_threshold=self._threshold
        )

    async def run(self, request: LandscapeRunRequest) -> LandscapeRunResult:
        snapshot = await self._snapshot(request.caselist, request.snapshot)
        resolved = self._taxonomies.resolve(request.caselist, snapshot)
        topics_file = str(self._config_dir / "topics.yaml")
        if resolved is None:
            raise NoTopicMapping(
                f"{topics_file} puts {request.caselist} on {snapshot.isoformat()} on no topic; add a range "
                "for it to a topic's caselists",
                file_to_edit=topics_file,
            )
        if resolved.taxonomy is None:
            raise NoTopicMapping(
                f"{request.caselist} on {snapshot.isoformat()} is on {resolved.topic.id}, which has no "
                f"taxonomy yet; give it a taxonomy_version in {topics_file} and a file in "
                f"{self._config_dir / 'taxonomies'}",
                file_to_edit=topics_file,
            )
        taxonomy = resolved.taxonomy
        reading = await read_seed_sources(
            store=self._parsed,
            local=self._local,
            suppression=self._suppression,
            topic=resolved.topic,
            caselist=request.caselist,
            through=snapshot,
        )
        if not reading.sources:
            raise NothingToReport(
                f"the parsed store holds no source of {request.caselist} on {resolved.topic.id} through "
                f"{snapshot.isoformat()}; parse the caselist first (`caselist parse`)"
            )
        store = _ReadOnlyClassifications(self._classifications) if request.dry_run else self._classifications
        classified = await self._classifier(store).classify(reading)
        if request.dry_run:
            # The read-only view dropped the cache write, so the counts must not report one.
            classified = dataclasses.replace(
                classified, counts=dataclasses.replace(classified.counts, cache_written=False)
            )
        if classified.counts.model_items > self._max_model_items:
            raise ModelBudgetExceeded(classified.counts.model_items, self._max_model_items)
        affs = (
            await self._aff.assignments(
                reading=reading,
                through=snapshot,
                classifications=classified.classifications,
                taxonomy=taxonomy,
                writes=not request.dry_run,
            )
            if self._aff is not None
            else AffAssignmentsForReport(assignments=())
        )
        assignments = affs.assignments
        overrides = self._taxonomies.overrides(resolved.topic.id)
        texts = (
            await self._texts.report_inputs(
                reading=reading,
                taxonomy=taxonomy,
                overrides=overrides,
                actors=self._taxonomies.cp_text_actors(resolved.topic.id),
                writes=not request.dry_run,
            )
            if self._texts is not None
            else None
        )
        staleness = await LandscapeStalenessCheck(
            objects=self._objects, run_log=self._run_log, stale_after_days=self._stale_after_days
        ).check(request.caselist, report_date=self._today())
        snapshot_topics = await self._snapshot_topics(request.caselist, snapshot)
        topic_range = next(
            (
                (one.effective_from, one.effective_to)
                for one in resolved.topic.caselists
                if one.covers(request.caselist, snapshot)
            ),
            None,
        )
        cards = landscape_cards(
            reading.sources,
            await self._parsed.read_occurrences(request.caselist, reading.version) or (),
            reading.caselist_names,
        )
        counting = (
            LandscapeReportService(review_threshold=self._threshold)
            if request.top_cards is None
            else LandscapeReportService(review_threshold=self._threshold, top_cards=request.top_cards)
        )
        bundle = counting.bundle(
            LandscapeReportInputs(
                caselist=request.caselist,
                through=snapshot,
                taxonomy=taxonomy,
                overrides=overrides,
                parser_version=parse_version_directory(reading.version)[0],
                classifications=classified.classifications,
                disclosures=reading.disclosures,
                cards=cards,
                aff_assignments=assignments,
                analytic_texts=texts.inputs if texts is not None else None,
                kritikal_affs=affs.kritikal,
                snapshot_topics=snapshot_topics,
                topic_range=topic_range,
            ),
            staleness,
        )
        hits = scan_report(bundle.files, reading.disclosures, school_view_files=SCHOOL_VIEW_FILES)
        pending = pending_hits(hits, self._acceptances.accepted(request.caselist))
        scan = ScanResult(hits=hits, pending=pending, digest=hits_digest(pending))
        directory = request.out or self._reports_dir / request.caselist / snapshot.isoformat()
        contents = {name: bundle.files[name].encode("utf-8") for name in BUNDLE_FILES}
        if not request.dry_run:
            _write_bundle(directory, contents)
        publish: PublishOutcome | None = None
        if request.publish:
            publish, scan = await self._publish(request, snapshot, directory, contents, scan)
        elif request.dry_run:
            publish = PublishOutcome(planned=_plan(request.caselist, snapshot, contents, None))
        return LandscapeRunResult(
            caselist=request.caselist,
            snapshot=snapshot,
            report_date=staleness.report_date,
            topic_id=resolved.topic.id,
            taxonomy_version=taxonomy.taxonomy_version,
            overrides_digest=overrides_digest(overrides),
            parsed_version=reading.version,
            model_mode=request.model_mode,
            dry_run=request.dry_run,
            classification=classified,
            report=bundle.report,
            trends=bundle.trends,
            schools=bundle.schools,
            staleness=staleness,
            aff_assignments=len(assignments),
            directory=directory,
            files=tuple(directory / name for name in BUNDLE_FILES),
            written=not request.dry_run,
            scan=scan,
            publish=publish,
            analytic_texts=texts,
            taxonomy=taxonomy,
            cards=cards,
            bundle_files={name: bundle.files[name] for name in BUNDLE_FILES},
        )

    async def _snapshot(self, caselist: str, asked: date | None) -> date:
        known = await self._known_caselists()
        if caselist not in known:
            raise UnknownCaselist(
                f"no weekly manifest of {caselist!r} is in this machine's evidence store; known caselists: "
                f"{', '.join(known) or 'none'}",
                known=known,
            )
        snapshots = await self._weekly_snapshots(caselist)
        if asked is None:
            return snapshots[-1]
        if asked not in snapshots:
            shown = [one.isoformat() for one in snapshots]
            raise UnknownSnapshot(
                f"{caselist} has no weekly snapshot of {asked.isoformat()}; "
                f"known snapshots: {', '.join(shown)}",
                known=shown,
            )
        return asked

    async def _snapshot_topics(self, caselist: str, through: date) -> dict[date, str]:
        """Each weekly snapshot of `caselist` through `through`, with the topic `topics.yaml` puts it on.

        A snapshot no range covers is left out: it holds no disclosure the report counts.
        """
        topics: dict[date, str] = {}
        for snapshot in await self._weekly_snapshots(caselist):
            if snapshot > through:
                continue
            resolved = self._taxonomies.resolve(caselist, snapshot)
            if resolved is not None:
                topics[snapshot] = resolved.topic.id
        return topics

    async def _known_caselists(self) -> tuple[str, ...]:
        """The caselists with at least one weekly manifest on this machine, by name."""
        candidates = {
            parts[1]
            for info in await self._objects.list_objects("manifests/")
            if len(parts := info.key.split("/")) == 3 and not parts[1].startswith("_")
        }
        known: list[str] = []
        for name in sorted(candidates):
            try:
                prefix = manifest_prefix(name)
            except ValueError:
                continue
            listed = await self._objects.list_objects(prefix)
            if any(snapshot_of_manifest_key(name, info.key) is not None for info in listed):
                known.append(name)
        return tuple(known)

    async def _weekly_snapshots(self, caselist: str) -> list[date]:
        found: set[date] = set()
        for info in await self._objects.list_objects(manifest_prefix(caselist)):
            named = snapshot_of_manifest_key(caselist, info.key)
            if named is None:
                continue
            try:
                found.add(date.fromisoformat(named))
            except ValueError:
                continue
        return sorted(found)

    async def _publish(
        self,
        request: LandscapeRunRequest,
        snapshot: date,
        directory: Path,
        contents: dict[str, bytes],
        scan: ScanResult,
    ) -> tuple[PublishOutcome, ScanResult]:
        if self._bucket is None:
            raise DomainError("this run was given no bucket to publish to")
        bucket = self._bucket()
        recorded: dict[str, str | None] = {}
        for name in BUNDLE_FILES:
            key = report_key(request.caselist, snapshot, name)
            try:
                recorded[key] = (await bucket.head(key)).sha256
            except NotFound:
                continue
        planned = _plan(request.caselist, snapshot, contents, recorded)
        refused = _refusal(scan, request.accept_scan_hits)
        if refused is not None or request.dry_run:
            return PublishOutcome(planned=planned, refused=refused), scan
        if scan.pending:
            log = self._acceptances.record(
                ScanAcceptance(
                    caselist=request.caselist,
                    snapshot=snapshot,
                    accepted_on=self._today(),
                    digest=scan.digest,
                    hits=scan.pending,
                )
            )
            scan = ScanResult(
                hits=scan.hits,
                pending=scan.pending,
                digest=scan.digest,
                accepted_now=True,
                acceptance_log=str(log),
            )
        uploaded: list[str] = []
        for one in planned:
            if one.action is not PublishAction.UPLOAD:
                continue
            stored = await bucket.put_file(one.key, directory / one.name)
            if stored.sha256 is not None and stored.sha256 != one.sha256:
                raise PublishedObjectMismatch(
                    f"the bucket recorded {stored.sha256[:12]} for {one.key}, not {one.sha256[:12]}"
                )
            uploaded.append(one.key)
        return PublishOutcome(planned=planned, uploaded=tuple(uploaded)), scan


def _refusal(scan: ScanResult, accepted: str | None) -> PublishRefusal | None:
    """Whether the scan lets a publish go ahead: every hit accepted before, or now by this digest."""
    if not scan.pending:
        return None
    if accepted is None:
        return PublishRefusal.SCAN_HITS_NOT_ACCEPTED
    if accepted.strip().lower() != scan.digest:
        return PublishRefusal.SCAN_DIGEST_STALE
    return None


def _plan(
    caselist: str, snapshot: date, contents: dict[str, bytes], recorded: dict[str, str | None] | None
) -> tuple[PlannedUpload, ...]:
    """Each bundle file's key and digest, and whether it must go up; None `recorded`: bucket not asked.

    A file goes up unless the bucket recorded this very digest for its key: an object with no
    recorded digest is read as changed, as `store sync` reads one.
    """
    planned: list[PlannedUpload] = []
    for name in BUNDLE_FILES:
        key = report_key(caselist, snapshot, name)
        digest = hashlib.sha256(contents[name]).hexdigest()
        action: PublishAction | None = None
        if recorded is not None:
            action = PublishAction.UNCHANGED if recorded.get(key) == digest else PublishAction.UPLOAD
        planned.append(
            PlannedUpload(name=name, key=key, sha256=digest, size=len(contents[name]), action=action)
        )
    return tuple(planned)


def _write_bundle(directory: Path, contents: dict[str, bytes]) -> None:
    """Each file to a second name beside it, then renamed over it, so no reader sees half a file."""
    directory.mkdir(parents=True, exist_ok=True)
    for name, body in contents.items():
        target = directory / name
        incoming = directory / f".{name}.incoming"
        with incoming.open("wb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(incoming, target)


class _ReadOnlyClassifications:
    """A dry run's view of the cache: read as it is, and nothing written to it or to the queue."""

    def __init__(self, inner: ClassificationStore) -> None:
        self._inner = inner

    async def read(self, caselist: str) -> tuple[CachedClassification, ...]:
        return await self._inner.read(caselist)

    async def replace(self, caselist: str, entries: Sequence[CachedClassification]) -> None:
        return None

    async def write_review_queue(self, caselist: str, topic_id: str, rows: Sequence[ReviewRow]) -> str:
        return DRY_RUN_QUEUE_LOCATION
