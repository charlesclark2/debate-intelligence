"""Turning one weekly archive into records, and saying exactly what changed since last week.

OpenCaselist republishes **everything** every week. The 15 September archive contains almost all
of the 8 September archive, which contains almost all of the 1 September archive, and a naive
importer would therefore store the same file three times and report three times as much evidence
as the circuit actually disclosed. Deduplication is not a refinement here; it is the job.

So every member of an archive is classified against the archive imported for the week before, and
the answer is one of six things:

`NEW`
    These bytes are not present in the preceding snapshot, under this path or any other, nor
    earlier in this archive. Stored. It is a week-over-week count and **not** "new to the
    corpus": a file from an earlier, non-adjacent week that is back in this one is `NEW` again,
    and so are bytes another caselist or a camp file already brought into the store. What is new
    to the caselist is the first-seen count, below.
`UNCHANGED`
    The previous archive had this same path holding these same bytes. Carried forward: the source
    document's `last_seen_snapshot` moves to this week and nothing else happens.
`CHANGED`
    The previous archive had this path holding *different* bytes. The team revised the file. Both
    versions are kept — they are different evidence — and the new one is stored.
`DUPLICATE`
    These bytes are already stored, but this path is new: a re-upload under a browser's `(1)`
    name, or another team disclosing the same file. One source document, a second disclosure.
`REMOVED`
    The previous archive had this path and this one does not. The team took it down. Reported so
    an operator can see it; the bytes are not deleted, because the file was disclosed and a card
    may already be cut from it. Deleting is :mod:`v1-e30-t07`'s deliberate act.
`SUPPRESSED`
    The file's SHA-256 is on the removal suppression list — or this one disclosure of it is — so it
    is not stored, not disclosed and given no manifest row, however many more times the cumulative
    archives republish it. Only the count survives. The list is a required constructor argument,
    not a per-call option: an import cannot be run without it (`v1-e30-t07`).

## What the previous archive is

**The latest snapshot strictly earlier than the one being imported** — not simply the latest.
That is what makes re-importing an archive a no-op (ac3): importing 09-15 when 09-15 is already
the newest compares against 09-08 both times and therefore classifies every member identically,
which is what "identical manifest bytes, zero NEW" means. Comparing against the latest would make
the second run see its own first run and report everything UNCHANGED.

## First seen: what is new to the caselist

A weekly archive is a window of roughly a week's edits, not the whole caselist, so a file a team
edits again weeks later is `NEW` against the window before it. Summed across weeks, `NEW` therefore
overstates new evidence: the v1-e30-t06 backfill's three August windows reported 25 `NEW` and held
16 files the caselist had never held before (`v1-e30-t08`).

:attr:`ImportReport.first_seen` is that second number: the distinct digests this archive stores
(`NEW`, `UNCHANGED`, `CHANGED`, `DUPLICATE`) that no earlier snapshot of the same caselist held,
counted from that caselist's own earlier manifests
(:func:`~debate_core.application.caselist.evidence_listing.digests_in_earlier_manifests`). It is
not "a blob the store lacks" — that is :attr:`ImportReport.newly_stored_blobs` — because another
caselist or a camp file can hold the same bytes. "Earlier" is strictly before, as the previous
snapshot is, so re-importing an archive reports the same count. It is `None` when the service was
built without a way to read the manifests, which the composition root always provides.

## A complete archive

`<slug>-all-<date>.zip` goes through :meth:`CaselistImportService.import_full_archive`: the same
pipeline, classified against the complete archive before it rather than against a week, and filed
as its own snapshot beside the weekly series (`v1-e34-t04`). Its `NEW` therefore means "not present
in the preceding complete archive". It reports no first-seen count, because first-seen measures new
evidence over time, which the weeklies record; it reports **withdrawals** instead, what earlier
snapshots held and it does not. The two divide the work: first-seen reads the weekly series alone,
withdrawals read every earlier snapshot, weekly and complete.

## Ordering

A cumulative archive older than one already imported would mark this week's files as removed and
last week's as new — the deduplication run backwards. So it is refused unless the caller passes
`allow_out_of_order`, which exists for the real case it happens in: an operator who downloaded
three weeks and imported them in the order the Finder listed them.

## What is shared with the OpenEv importer

The per-member work — hash, store, classify, count — is
:class:`~debate_core.application.caselist.pipeline.SourceImportPipeline`'s, which the OpenEv
importer (`v1-e30-t04`) runs too. :class:`Classification`, :data:`STORED_CLASSIFICATIONS` and
:class:`ImportedEntry` are defined there and re-exported here. What this module keeps is what is
particular to a weekly archive: the previous snapshot as the baseline, disclosures as the records,
and the snapshot row.

## What is written, and when

Nothing at all under `dry_run`. Otherwise, per member: the bytes to the
:class:`~debate_core.application.ports.persistence.SnapshotStore` (content-addressed, so storing
the same bytes twice writes once), the source document through
:meth:`~debate_core.application.ports.caselist.CaselistRepository.put_source` (which widens its
seen range), and the disclosure. The snapshot record is written last, because it is what a later
import reads to decide what "the previous archive" was: an interrupted run leaves no snapshot
record, and re-running it redoes the same work against the same baseline.

## What is logged

Counts, and the caselist and snapshot they belong to. Never a path, a school, a team code or a
filename — `docs/policies/caselist-data-use.md` rule 4 forbids all four in a log line, in any
environment. Those fields exist in exactly two places: the records in the local store, and the
manifest under `manifests/`, both of which the policy names as somewhere they may live.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date

from debate_core.application.caselist.path_parser import (
    ParsedDisclosurePath,
    parse_disclosure_path,
)
from debate_core.application.caselist.pipeline import (
    STORED_CLASSIFICATIONS,
    Classification,
    ImportedEntry,
    SourceImportPipeline,
    file_source,
)
from debate_core.application.caselist.withdrawals import EarlierSnapshots, WithdrawalCount, count_withdrawals
from debate_core.application.errors import DomainError
from debate_core.application.ports.archive import ArchiveEntry, ArchiveMember, SkipReason
from debate_core.application.ports.caselist import CaselistRepository
from debate_core.application.ports.persistence import SnapshotStore
from debate_core.application.ports.suppression import SuppressionList, SuppressionState
from debate_core.domain import Sha256Hex
from debate_core.domain.caselist import (
    Acquisition,
    ArchiveSnapshot,
    CaselistSlug,
    Disclosure,
    Event,
    SnapshotDate,
    SourceDocument,
    SourceOrigin,
)

__all__ = [
    "STORED_CLASSIFICATIONS",
    "CaselistImportService",
    "Classification",
    "EarlierManifestDigests",
    "FullArchiveBaseline",
    "ImportReport",
    "ImportedEntry",
    "SnapshotOutOfOrder",
]

logger = logging.getLogger(__name__)

type EarlierManifestDigests = Callable[[CaselistSlug, SnapshotDate], Awaitable[frozenset[Sha256Hex]]]
"""Every digest a stored row names in a caselist's manifests for snapshots strictly before a date.

What the first-seen count is measured against;
:func:`~debate_core.application.caselist.evidence_listing.digests_in_earlier_manifests` over the
local evidence store is the one the composition root passes.
"""


class SnapshotOutOfOrder(DomainError):
    """A cumulative archive older than one already imported was refused.

    Applying it would run the deduplication backwards: this week's files would be marked removed
    and last week's new. Re-run with `allow_out_of_order` when that really is what you meant —
    importing three weeks in the order the Finder happened to list them, for instance.
    """

    def __init__(self, *, caselist: str, snapshot: date, latest: date) -> None:
        self.caselist = caselist
        self.snapshot = snapshot
        self.latest = latest
        super().__init__(
            f"{caselist} already has the {latest.isoformat()} archive imported, so importing the "
            f"older {snapshot.isoformat()} one would mark current files as removed; pass "
            "--allow-out-of-order if that is what you mean"
        )


@dataclass(frozen=True, slots=True)
class ImportReport:
    """Everything one import did, in the shape both the manifest and the summary table read."""

    caselist: CaselistSlug
    snapshot: SnapshotDate
    event: Event
    archive_sha256: str
    applied: bool
    """False for a dry run, which classifies everything and writes nothing."""

    entries: tuple[ImportedEntry[ParsedDisclosurePath], ...]
    """Every member and every removed path, in path order."""

    counts: Mapping[Classification, int] = field(default_factory=lambda: {})
    skipped: Mapping[SkipReason, int] = field(default_factory=lambda: {})
    distinct_digests: int = 0
    """How many distinct files this archive holds, once its duplicates are collapsed.

    A property of the archive, so it is the same on every import of it.
    """

    newly_stored_blobs: int = 0
    """How many of those digests the snapshot store did not already have.

    This is the number that is zero when a re-import really was a no-op (ac3). The
    classification counts cannot be: they describe this archive against the week before it, which
    does not change just because somebody ran the import twice — and their not changing is exactly
    what makes the manifest byte-identical. A dry run reports what it *would* have written.
    """

    previous_snapshot: SnapshotDate | None = None
    """The archive this one was classified against, or `None` for the first import."""

    first_seen: int | None = None
    """Distinct digests this archive stores that no earlier snapshot of this caselist held.

    New to the caselist, where `NEW` is only new against the week before (see the module
    docstring). `None` when the service was built without :data:`EarlierManifestDigests`, and
    always `None` for a complete archive, which reports :attr:`withdrawals` instead.
    """

    full_archive: bool = False
    """True for a complete archive (`<slug>-all-<date>.zip`, :meth:`CaselistImportService.import_full_archive`)."""

    withdrawals: WithdrawalCount | None = None
    """For a complete archive: what earlier snapshots held and it does not. `None` for a weekly."""

    suppression: SuppressionState = field(default_factory=SuppressionState)
    """The suppression list this import read, which the manifest writer checks every row against."""

    @property
    def member_count(self) -> int:
        """Members this archive actually contained, skipped ones included."""
        return sum(1 for entry in self.entries if entry.classification is not Classification.REMOVED)

    @property
    def warning_count(self) -> int:
        """How many members the path parser could not fully read."""
        return sum(1 for entry in self.entries if entry.parsed is not None and entry.parsed.warnings)

    def count(self, classification: Classification) -> int:
        return self.counts.get(classification, 0)


@dataclass(frozen=True, slots=True)
class FullArchiveBaseline:
    """The complete archive a new one is classified against: its date, and what it held where."""

    snapshot: SnapshotDate
    paths: Mapping[str, str]
    """`{path: sha256}` of its stored rows, as its manifest records them."""


class CaselistImportService:
    """Imports one weekly archive into the evidence store, deduplicated against the earlier ones.

    Takes its ports rather than building them, like every other service in this package::

        service = CaselistImportService(
            caselists=SqliteCaselistRepository(database),
            blobs=FsSnapshotStore(settings.storage.data_dir),
            suppression=RecordedSuppressionList(local_suppression_list_file(data_dir)),
            earlier_manifest_digests=functools.partial(digests_in_earlier_manifests, local),
        )

    Without `earlier_manifest_digests` it imports exactly the same and reports no first-seen count.

    It never opens an archive. The members are read by an adapter
    (:func:`debate_core.integrations.local.archive_reader.read_archive`) and handed in, which is
    what lets the same service run over a zip on a laptop and, in V2, over an object in a bucket.
    """

    def __init__(
        self,
        *,
        caselists: CaselistRepository,
        blobs: SnapshotStore,
        suppression: SuppressionList,
        earlier_manifest_digests: EarlierManifestDigests | None = None,
    ) -> None:
        self._caselists = caselists
        self._pipeline = SourceImportPipeline(blobs=blobs, suppression=suppression)
        self._earlier_manifest_digests = earlier_manifest_digests

    async def import_archive(
        self,
        entries: Iterable[ArchiveEntry],
        *,
        caselist: CaselistSlug,
        snapshot: SnapshotDate,
        event: Event,
        archive_sha256: str,
        acquisition: Acquisition = Acquisition.MANUAL_DOWNLOAD,
        allow_out_of_order: bool = False,
        dry_run: bool = False,
    ) -> ImportReport:
        """Classify every member of one archive, store what is new, and report what changed.

        `entries` is consumed once, in the order it yields, which the reader guarantees is path
        order. Members the suppression list stops — the whole file, or this team's disclosure of
        it — are counted as `SUPPRESSED` and never stored.

        Raises :class:`SnapshotOutOfOrder` unless `allow_out_of_order` is set and a newer archive
        is already imported. Writes nothing when `dry_run` is set.
        """
        previous = await self._previous_snapshot(caselist, snapshot, allow_out_of_order=allow_out_of_order)
        baseline = await self._disclosures_in(caselist, previous)

        async def write(
            member: ArchiveMember,
            parsed: ParsedDisclosurePath,
            _classification: Classification,
            _existing: SourceDocument | None,
        ) -> None:
            await self._store(member, parsed, caselist=caselist, snapshot=snapshot, event=event)

        run = await self._pipeline.run(
            entries,
            extract=lambda path: parse_disclosure_path(path, event=event),
            write=write,
            baseline=baseline,
            disclosure_scope=caselist,
            dry_run=dry_run,
        )

        if not dry_run:
            await self._caselists.upsert_snapshot(
                ArchiveSnapshot(
                    caselist=caselist,
                    snapshot=snapshot,
                    archive_sha256=archive_sha256,
                    acquisition=acquisition,
                    file_count=run.member_count,
                )
            )

        report = ImportReport(
            caselist=caselist,
            snapshot=snapshot,
            event=event,
            archive_sha256=archive_sha256,
            applied=not dry_run,
            entries=run.entries,
            counts=run.counts,
            skipped=run.skipped,
            distinct_digests=run.distinct_digests,
            newly_stored_blobs=run.newly_stored_blobs,
            previous_snapshot=previous,
            suppression=run.suppression,
            first_seen=await self._first_seen(caselist, snapshot, run.entries),
        )
        _log_counts(report)
        return report

    async def import_full_archive(
        self,
        entries: Iterable[ArchiveEntry],
        *,
        caselist: CaselistSlug,
        archive_date: SnapshotDate,
        event: Event,
        archive_sha256: str,
        previous: FullArchiveBaseline | None,
        earlier: EarlierSnapshots,
        dry_run: bool = False,
    ) -> ImportReport:
        """Import a complete archive as its own snapshot, beside the weekly series (`v1-e34-t04`).

        The same pipeline as a weekly: every member hashed, checked against the suppression list
        (whole sources and this caselist's disclosures alike), stored by digest, classified. Three
        things differ, and each is what keeps the weekly series as it was:

        * **The baseline is the complete archive before it**, `previous`, which the caller reads
          from that archive's manifest; `None` for the first. Never a weekly, so this archive's
          `REMOVED` rows are paths the previous complete archive had, and never this method's
          business to compute against the week.
        * **No snapshot or disclosure record.** The repository keys both by `(caselist, date)`, the
          weekly series' own key, and a complete archive shares its date with that week's weekly.
          A row there is what :meth:`_previous_snapshot` and :meth:`_disclosures_in` read, so
          writing one would change every later weekly's baseline. The manifest the caller files at
          `manifests/<slug>/full/<date>.jsonl` is this snapshot's record.
        * **Withdrawals, not first-seen.** `earlier` is every snapshot of the caselist dated before
          this one, weekly and complete; the report counts what they held and this archive does not
          (:func:`~debate_core.application.caselist.withdrawals.count_withdrawals`). First-seen is
          left `None`: it measures new evidence over time, which is the weeklies' question.

        Each stored member's source document is still filed, by digest, through
        :func:`~debate_core.application.caselist.pipeline.file_source`: a digest names the same
        bytes in every series, and a file only the complete archive holds needs its record for the
        corpus and for a removal to delete. Its seen range widens to this date, which is true: the
        site served it then.
        """
        baseline = dict(previous.paths) if previous is not None else {}

        async def write(
            member: ArchiveMember,
            parsed: ParsedDisclosurePath,
            _classification: Classification,
            _existing: SourceDocument | None,
        ) -> None:
            await file_source(
                self._caselists,
                SourceDocument(
                    sha256=member.sha256,
                    byte_size=member.byte_size,
                    source_format=parsed.source_format,
                    origin=SourceOrigin.CASELIST_ARCHIVE,
                    caselist=caselist,
                    first_seen_snapshot=archive_date,
                    last_seen_snapshot=archive_date,
                ),
            )

        run = await self._pipeline.run(
            entries,
            extract=lambda path: parse_disclosure_path(path, event=event),
            write=write,
            baseline=baseline,
            disclosure_scope=caselist,
            dry_run=dry_run,
        )
        report = ImportReport(
            caselist=caselist,
            snapshot=archive_date,
            event=event,
            archive_sha256=archive_sha256,
            applied=not dry_run,
            entries=run.entries,
            counts=run.counts,
            skipped=run.skipped,
            distinct_digests=run.distinct_digests,
            newly_stored_blobs=run.newly_stored_blobs,
            previous_snapshot=previous.snapshot if previous is not None else None,
            suppression=run.suppression,
            full_archive=True,
            withdrawals=count_withdrawals(
                earlier,
                (
                    (entry.sha256, entry.path)
                    for entry in run.entries
                    if entry.sha256 is not None and entry.classification is not Classification.REMOVED
                ),
            ),
        )
        _log_counts(report)
        return report

    # ------------------------------------------------------------------------------------
    # The baseline
    # ------------------------------------------------------------------------------------

    async def _previous_snapshot(
        self, caselist: CaselistSlug, snapshot: SnapshotDate, *, allow_out_of_order: bool
    ) -> SnapshotDate | None:
        """The latest archive *strictly before* this one, refusing an out-of-order import.

        Of the weekly series only, by construction: :meth:`import_full_archive` writes no snapshot
        record, so a complete archive is never a row this reads (`v1-e34-t04` ac0).

        Strictly before is the whole of ac3's idempotence: re-importing an archive compares it
        against the same earlier week it was compared against the first time, so it classifies
        every member identically and writes the same manifest.
        """
        latest = await self._caselists.latest_snapshot(caselist)
        if latest is not None and latest.snapshot > snapshot and not allow_out_of_order:
            raise SnapshotOutOfOrder(caselist=caselist, snapshot=snapshot, latest=latest.snapshot)
        earlier = [
            stored.snapshot
            for stored in await self._caselists.list_snapshots(caselist)
            if stored.snapshot < snapshot
        ]
        return max(earlier) if earlier else None

    async def _first_seen(
        self,
        caselist: CaselistSlug,
        snapshot: SnapshotDate,
        entries: Iterable[ImportedEntry[ParsedDisclosurePath]],
    ) -> int | None:
        """How many of the digests this archive stores no earlier snapshot of `caselist` held."""
        if self._earlier_manifest_digests is None:
            return None
        stored = {
            entry.sha256
            for entry in entries
            if entry.classification in STORED_CLASSIFICATIONS and entry.sha256 is not None
        }
        return len(stored - await self._earlier_manifest_digests(caselist, snapshot))

    async def _disclosures_in(self, caselist: CaselistSlug, snapshot: SnapshotDate | None) -> dict[str, str]:
        """What the previous archive said, as `{source path: sha256}`.

        The whole snapshot is read: it is one dictionary of short strings per archive — a few
        thousand entries for a weekly HS LD archive — and holding it makes the classification of
        each member a lookup rather than a query.
        """
        if snapshot is None:
            return {}
        baseline: dict[str, str] = {}
        cursor: str | None = None
        while True:
            page = await self._caselists.list_disclosures(
                caselist=caselist, snapshot=snapshot, limit=500, cursor=cursor
            )
            baseline.update({disclosure.source_path: disclosure.source_sha256 for disclosure in page.items})
            if not page.has_more:
                return baseline
            cursor = page.next_cursor

    # ------------------------------------------------------------------------------------
    # Storing
    # ------------------------------------------------------------------------------------

    async def _store(
        self,
        member: ArchiveMember,
        parsed: ParsedDisclosurePath,
        *,
        caselist: CaselistSlug,
        snapshot: SnapshotDate,
        event: Event,
    ) -> None:
        """Write one stored member's source document and what this archive said about it.

        The pipeline has already put the bytes in the content-addressed blob store, so a
        `DUPLICATE` or an `UNCHANGED` member wrote none. `put_source` widens the seen range rather
        than replacing it, and a file an OpenEv import brought in first keeps that record
        (:func:`~debate_core.application.caselist.pipeline.file_source`). The disclosure is
        recorded for every stored member, because two paths holding one file are two things the
        archive said about it.
        """
        await file_source(
            self._caselists,
            SourceDocument(
                sha256=member.sha256,
                byte_size=member.byte_size,
                source_format=parsed.source_format,
                origin=SourceOrigin.CASELIST_ARCHIVE,
                caselist=caselist,
                first_seen_snapshot=snapshot,
                last_seen_snapshot=snapshot,
            ),
        )
        await self._caselists.record_disclosure(
            Disclosure(
                source_sha256=member.sha256,
                caselist=caselist,
                snapshot=snapshot,
                event=event,
                school=parsed.school,
                team_code=parsed.team_code,
                side=parsed.side,
                tournament=parsed.tournament,
                round_label=parsed.round_label,
                source_path=member.path,
                parse_warnings=parsed.warnings,
            )
        )


def _log_counts(report: ImportReport) -> None:
    """Log what the run did: counts, and the archive they belong to. Never a path.

    `docs/policies/caselist-data-use.md` rule 4 — no school, team code, filename or disclosure
    path in an application log, in any environment. Everything here is a number, a caselist slug
    or a date.
    """
    logger.info(
        "imported caselist archive",
        extra={
            "caselist": report.caselist,
            "snapshot": report.snapshot.isoformat(),
            "previous_snapshot": (report.previous_snapshot.isoformat() if report.previous_snapshot else None),
            "applied": report.applied,
            "members": report.member_count,
            "distinct_digests": report.distinct_digests,
            "newly_stored_blobs": report.newly_stored_blobs,
            "first_seen": report.first_seen,
            "full_archive": report.full_archive,
            "withdrawn": report.withdrawals.withdrawn if report.withdrawals is not None else None,
            "superseded": report.withdrawals.superseded if report.withdrawals is not None else None,
            "counts": {str(name): count for name, count in report.counts.items()},
            "skipped": {str(reason): count for reason, count in report.skipped.items()},
            "warnings": report.warning_count,
        },
    )
