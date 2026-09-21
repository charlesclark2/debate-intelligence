"""Turning one weekly archive into records, and saying exactly what changed since last week.

OpenCaselist republishes **everything** every week. The 15 September archive contains almost all
of the 8 September archive, which contains almost all of the 1 September archive, and a naive
importer would therefore store the same file three times and report three times as much evidence
as the circuit actually disclosed. Deduplication is not a refinement here; it is the job.

So every member of an archive is classified against the archives already imported, and the answer
is one of six things:

`NEW`
    These bytes have not been seen before, under this path or any other. Stored.
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
    The file's SHA-256 is on the removal suppression list, so it is not stored and not disclosed,
    however many more times the cumulative archives republish it. The list itself is t07's; this
    task takes it as an argument, defaults it to empty, and counts what it excludes.

## What the previous archive is

**The latest snapshot strictly earlier than the one being imported** — not simply the latest.
That is what makes re-importing an archive a no-op (ac3): importing 09-15 when 09-15 is already
the newest compares against 09-08 both times and therefore classifies every member identically,
which is what "identical manifest bytes, zero NEW" means. Comparing against the latest would make
the second run see its own first run and report everything UNCHANGED.

## Ordering

A cumulative archive older than one already imported would mark this week's files as removed and
last week's as new — the deduplication run backwards. So it is refused unless the caller passes
`allow_out_of_order`, which exists for the real case it happens in: an operator who downloaded
three weeks and imported them in the order the Finder listed them.

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
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from debate_core.application.caselist.path_parser import (
    ParsedDisclosurePath,
    parse_disclosure_path,
)
from debate_core.application.errors import DomainError
from debate_core.application.ports.archive import ArchiveEntry, ArchiveMember, SkipReason
from debate_core.application.ports.caselist import CaselistRepository
from debate_core.application.ports.persistence import SnapshotStore
from debate_core.domain.caselist import (
    Acquisition,
    ArchiveSnapshot,
    CaselistSlug,
    Disclosure,
    Event,
    SnapshotDate,
    SourceDocument,
    SourceFormat,
    SourceOrigin,
)

__all__ = [
    "CaselistImportService",
    "Classification",
    "ImportReport",
    "ImportedEntry",
    "SnapshotOutOfOrder",
]

logger = logging.getLogger(__name__)


class Classification(StrEnum):
    """What one member of an archive turned out to be, relative to the archives already imported.

    The six outcomes the importer reports counts for. `REMOVED` is the one that describes a member
    that is *not* in this archive — the path the previous one had and this one does not.
    """

    NEW = "NEW"
    UNCHANGED = "UNCHANGED"
    CHANGED = "CHANGED"
    DUPLICATE = "DUPLICATE"
    REMOVED = "REMOVED"
    SUPPRESSED = "SUPPRESSED"


#: The classifications that describe a file present in the archive being imported. `REMOVED` is
#: not one of them, and `SUPPRESSED` is present but deliberately not stored.
STORED_CLASSIFICATIONS = frozenset(
    {
        Classification.NEW,
        Classification.UNCHANGED,
        Classification.CHANGED,
        Classification.DUPLICATE,
    }
)


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
class ImportedEntry:
    """One row of what an import saw: a member, or a path that has gone.

    Carries everything the manifest records and everything a summary counts, so the manifest
    writer does no parsing of its own and the two cannot disagree about what happened.
    """

    path: str
    """The member's path relative to the archive root."""

    classification: Classification | None
    """What it was, or `None` for a member that was skipped before it was ever classified."""

    skip_reason: SkipReason | None = None
    """Why it was skipped, or `None` for a member that was not."""

    sha256: str | None = None
    """The digest of its bytes; `None` for a skipped member, which was never read."""

    byte_size: int | None = None
    source_format: SourceFormat | None = None
    parsed: ParsedDisclosurePath | None = None
    """What the path parser read, or `None` for a skipped member."""

    @property
    def is_skipped(self) -> bool:
        return self.skip_reason is not None


@dataclass(frozen=True, slots=True)
class ImportReport:
    """Everything one import did, in the shape both the manifest and the summary table read."""

    caselist: CaselistSlug
    snapshot: SnapshotDate
    event: Event
    archive_sha256: str
    applied: bool
    """False for a dry run, which classifies everything and writes nothing."""

    entries: tuple[ImportedEntry, ...]
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


class CaselistImportService:
    """Imports one weekly archive into the evidence store, deduplicated against the earlier ones.

    Takes its ports rather than building them, like every other service in this package::

        service = CaselistImportService(
            caselists=SqliteCaselistRepository(database),
            blobs=FsSnapshotStore(settings.storage.data_dir),
        )

    It never opens an archive. The members are read by an adapter
    (:func:`debate_core.integrations.local.archive_reader.read_archive`) and handed in, which is
    what lets the same service run over a zip on a laptop and, in V2, over an object in a bucket.
    """

    def __init__(self, *, caselists: CaselistRepository, blobs: SnapshotStore) -> None:
        self._caselists = caselists
        self._blobs = blobs

    async def import_archive(
        self,
        entries: Iterable[ArchiveEntry],
        *,
        caselist: CaselistSlug,
        snapshot: SnapshotDate,
        event: Event,
        archive_sha256: str,
        acquisition: Acquisition = Acquisition.MANUAL_DOWNLOAD,
        suppressed_hashes: frozenset[str] = frozenset(),
        allow_out_of_order: bool = False,
        dry_run: bool = False,
    ) -> ImportReport:
        """Classify every member of one archive, store what is new, and report what changed.

        `entries` is consumed once, in the order it yields, which the reader guarantees is path
        order. `suppressed_hashes` is the removal suppression list (v1-e30-t07); it defaults to
        empty and its members are counted as `SUPPRESSED` and never stored.

        Raises :class:`SnapshotOutOfOrder` unless `allow_out_of_order` is set and a newer archive
        is already imported. Writes nothing when `dry_run` is set.
        """
        previous = await self._previous_snapshot(caselist, snapshot, allow_out_of_order=allow_out_of_order)
        baseline = await self._disclosures_in(caselist, previous)

        imported: list[ImportedEntry] = []
        skipped: dict[SkipReason, int] = {}
        counts: dict[Classification, int] = {}
        stored_digests: set[str] = set()
        newly_stored: set[str] = set()
        seen_paths: set[str] = set()
        member_count = 0

        for entry in entries:
            if not isinstance(entry, ArchiveMember):
                skipped[entry.reason] = skipped.get(entry.reason, 0) + 1
                # Counted as a member: `ArchiveSnapshot.file_count` is how many members the
                # archive held, which is the number an operator can check against `unzip -l`.
                member_count += 1
                imported.append(ImportedEntry(path=entry.path, classification=None, skip_reason=entry.reason))
                continue

            member_count += 1
            seen_paths.add(entry.path)
            parsed = parse_disclosure_path(entry.path, event=event)
            classification = self._classify(
                entry, baseline=baseline, known=stored_digests, suppressed=suppressed_hashes
            )
            counts[classification] = counts.get(classification, 0) + 1
            if classification is not Classification.SUPPRESSED:
                if entry.sha256 not in stored_digests and not await self._blobs.exists(entry.sha256):
                    newly_stored.add(entry.sha256)
                stored_digests.add(entry.sha256)
            imported.append(
                ImportedEntry(
                    path=entry.path,
                    classification=classification,
                    sha256=entry.sha256,
                    byte_size=entry.byte_size,
                    source_format=parsed.source_format,
                    parsed=parsed,
                )
            )
            if not dry_run and classification in STORED_CLASSIFICATIONS:
                await self._store(entry, parsed, caselist=caselist, snapshot=snapshot, event=event)

        for gone in sorted(baseline.keys() - seen_paths):
            counts[Classification.REMOVED] = counts.get(Classification.REMOVED, 0) + 1
            imported.append(ImportedEntry(path=gone, classification=Classification.REMOVED))

        if not dry_run:
            await self._caselists.upsert_snapshot(
                ArchiveSnapshot(
                    caselist=caselist,
                    snapshot=snapshot,
                    archive_sha256=archive_sha256,
                    acquisition=acquisition,
                    file_count=member_count,
                )
            )

        report = ImportReport(
            caselist=caselist,
            snapshot=snapshot,
            event=event,
            archive_sha256=archive_sha256,
            applied=not dry_run,
            entries=tuple(sorted(imported, key=lambda one: one.path)),
            counts=counts,
            skipped=skipped,
            distinct_digests=len(stored_digests),
            newly_stored_blobs=len(newly_stored),
            previous_snapshot=previous,
        )
        _log_counts(report)
        return report

    # ------------------------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------------------------

    def _classify(
        self,
        member: ArchiveMember,
        *,
        baseline: Mapping[str, str],
        known: set[str],
        suppressed: frozenset[str],
    ) -> Classification:
        """Decide what one member is, against last week's archive and what this run has stored.

        `known` is the set of digests this run has already stored, which is what makes the second
        of two identical members in one archive a `DUPLICATE` rather than a second `NEW`.
        """
        if member.sha256 in suppressed:
            return Classification.SUPPRESSED
        previously = baseline.get(member.path)
        if previously == member.sha256:
            return Classification.UNCHANGED
        if previously is not None:
            return Classification.CHANGED
        if member.sha256 in known or member.sha256 in baseline.values():
            return Classification.DUPLICATE
        return Classification.NEW

    async def _previous_snapshot(
        self, caselist: CaselistSlug, snapshot: SnapshotDate, *, allow_out_of_order: bool
    ) -> SnapshotDate | None:
        """The latest archive *strictly before* this one, refusing an out-of-order import.

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
        """Write one member's bytes, its source document and what this archive said about it.

        The blob store is content-addressed, so a `DUPLICATE` or an `UNCHANGED` member writes no
        bytes; `put_source` widens the seen range rather than replacing it; and the disclosure is
        recorded for every stored member, because two paths holding one file are two things the
        archive said about it.
        """
        await self._blobs.put(member.data)
        await self._caselists.put_source(
            SourceDocument(
                sha256=member.sha256,
                byte_size=member.byte_size,
                source_format=parsed.source_format,
                origin=SourceOrigin.CASELIST_ARCHIVE,
                caselist=caselist,
                first_seen_snapshot=snapshot,
                last_seen_snapshot=snapshot,
            )
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
            "counts": {str(name): count for name, count in report.counts.items()},
            "skipped": {str(reason): count for reason, count in report.skipped.items()},
            "warnings": report.warning_count,
        },
    )
