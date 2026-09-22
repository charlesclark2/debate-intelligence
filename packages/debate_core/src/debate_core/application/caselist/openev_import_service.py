"""Importing OpenEv camp files into the same evidence store as caselist disclosures.

The coach downloads camp files from OpenEv by hand — about 106 Policy files are on hand — and the
scheduled sync (`v1-e34-t02`) will fetch the new ones each week. Either way they arrive as a zip
or a directory, and each file becomes:

* a :class:`~debate_core.domain.caselist.SourceDocument` with origin `OPENEV`, unless its bytes
  are already filed — see below;
* a :class:`~debate_core.domain.caselist.CampFile` saying which camp released it, for which year
  and event, under what title (:mod:`debate_core.application.caselist.camp_metadata`); and
* a row of `manifests/openev/<year>-<event>.jsonl`
  (:mod:`debate_core.application.caselist.openev_manifest`).

It runs on the same :class:`~debate_core.application.caselist.pipeline.SourceImportPipeline` as
the weekly archive importer, so hashing, the content-addressed blob store, the six
classifications and the suppression list behave exactly as they do there. What differs:

**The baseline is the release's own manifest**, not a previous weekly snapshot: an OpenEv release
has no weeks, and a later download of it is compared against what the earlier ones recorded.

**Bytes already filed by any import are a `DUPLICATE` of that source** (ac2). A camp file whose
bytes a team already disclosed writes no second blob and no second source document; its
`CampFile` is recorded against the existing source, and its manifest row names the source's
origin and caselist. That shared digest is how E31 and E32 see that a disclosed card came from a
camp file. It works in the other direction too: a caselist archive that later discloses a camp
file's bytes links to the OpenEv source rather than conflicting with it
(:func:`~debate_core.application.caselist.pipeline.file_source`).

**Nothing is ever `REMOVED`.** A file missing from one download was not withdrawn; it was not
fetched.

**An `UNCHANGED` file writes nothing at all**, not even a widened seen range, so re-importing a
release on a later day leaves every record and the manifest exactly as they were (ac3).

A camp file is recorded once per (digest, year, event), the repository's key for it. Two files
with identical bytes in one release are two manifest rows — each with its own path and title —
and one `CampFile`, the first in path order.

## What is logged

Counts, the year and the event. Never a path, a filename or a file title
(`docs/policies/caselist-data-use.md` rule 4); those live in the records and the manifest.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date

from debate_core.application.caselist.camp_metadata import (
    CampAliases,
    ParsedCampPath,
    load_camp_aliases,
    parse_camp_path,
)
from debate_core.application.caselist.openev_manifest import (
    merged_manifest_lines,
    openev_manifest_key,
    openev_release_name,
    read_recorded_release,
)
from debate_core.application.caselist.pipeline import (
    Classification,
    ImportedEntry,
    SourceImportPipeline,
    file_source,
)
from debate_core.application.ports.archive import ArchiveEntry, ArchiveMember, SkipReason
from debate_core.application.ports.caselist import CaselistRepository
from debate_core.application.ports.evidence_store import ObjectKey
from debate_core.application.ports.persistence import SnapshotStore
from debate_core.domain.caselist import (
    CampFile,
    Event,
    SnapshotDate,
    SourceDocument,
    SourceOrigin,
)

__all__ = ["OpenEvImportReport", "OpenEvImportService"]

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OpenEvImportReport:
    """Everything one OpenEv import did, and the release manifest it leaves behind."""

    year: int
    event: Event
    imported_on: SnapshotDate
    archive_sha256: str
    applied: bool
    """False for a dry run, which classifies everything and writes nothing."""

    entries: tuple[ImportedEntry[ParsedCampPath], ...]
    """Every member of this download, in path order."""

    manifest_key: ObjectKey
    manifest_lines: tuple[str, ...]
    """The release's whole manifest with this import merged in — what a real run writes."""

    counts: Mapping[Classification, int] = field(default_factory=lambda: {})
    skipped: Mapping[SkipReason, int] = field(default_factory=lambda: {})
    member_count: int = 0
    distinct_digests: int = 0
    newly_stored_blobs: int = 0
    """Blobs this import stored (or, dry, would store). Zero on a re-import."""

    @property
    def release(self) -> str:
        """`2026-policy`, as `caselist publish --caselist openev --snapshot` takes it."""
        return openev_release_name(self.year, self.event)

    @property
    def warning_count(self) -> int:
        """Members whose camp or title could not be fully read."""
        return sum(1 for entry in self.entries if entry.parsed is not None and entry.parsed.warnings)

    @property
    def unknown_camp_count(self) -> int:
        return sum(1 for entry in self.entries if entry.parsed is not None and not entry.parsed.camp_resolved)

    @property
    def caselist_duplicate_count(self) -> int:
        """Members whose bytes a caselist archive had already brought in."""
        return sum(
            1
            for entry in self.entries
            if entry.existing_source is not None
            and entry.existing_source.origin is SourceOrigin.CASELIST_ARCHIVE
        )

    def count(self, classification: Classification) -> int:
        return self.counts.get(classification, 0)


class OpenEvImportService:
    """Imports one OpenEv download into the evidence store, merged into its release's manifest.

    Built over the same ports as the archive importer::

        service = OpenEvImportService(
            caselists=SqliteCaselistRepository(database),
            blobs=FsSnapshotStore(settings.storage.data_dir),
        )
    """

    def __init__(self, *, caselists: CaselistRepository, blobs: SnapshotStore) -> None:
        self._caselists = caselists
        self._pipeline = SourceImportPipeline(blobs=blobs)

    async def import_release(
        self,
        entries: Iterable[ArchiveEntry],
        *,
        year: int,
        event: Event,
        imported_on: SnapshotDate,
        archive_sha256: str,
        recorded_manifest: Iterable[str] = (),
        aliases: CampAliases | None = None,
        suppressed_hashes: frozenset[str] = frozenset(),
        dry_run: bool = False,
    ) -> OpenEvImportReport:
        """Classify and store every member of one download, and merge it into the release manifest.

        `recorded_manifest` is the lines of the release's existing manifest (none for a first
        import); the caller reads it from where it keeps manifests and writes
        :attr:`OpenEvImportReport.manifest_lines` back there. `aliases` defaults to the packaged
        `camp_aliases.yaml`. `suppressed_hashes` is the removal suppression list (v1-e30-t07).

        Writes nothing — no blob, no record — when `dry_run` is set; the report still carries the
        manifest a real run would write.
        """
        key = openev_manifest_key(year, event)
        recorded = read_recorded_release(key, recorded_manifest)
        table = aliases if aliases is not None else load_camp_aliases()

        async def write(
            member: ArchiveMember,
            parsed: ParsedCampPath,
            classification: Classification,
            _existing: SourceDocument | None,
        ) -> None:
            if classification is Classification.UNCHANGED:
                return
            await self._store(member, parsed, year=year, event=event, imported_on=imported_on)

        run = await self._pipeline.run(
            entries,
            extract=lambda path: parse_camp_path(path, aliases=table),
            write=write,
            baseline=recorded.baseline,
            suppressed=suppressed_hashes,
            dry_run=dry_run,
            report_removed=False,
            find_existing=self._caselists.find_source,
        )

        report = OpenEvImportReport(
            year=year,
            event=event,
            imported_on=imported_on,
            archive_sha256=archive_sha256,
            applied=not dry_run,
            entries=run.entries,
            manifest_key=key,
            manifest_lines=merged_manifest_lines(
                run.entries,
                recorded,
                year=year,
                event=event,
                imported_on=imported_on,
                archive_sha256=archive_sha256,
            ),
            counts=run.counts,
            skipped=run.skipped,
            member_count=run.member_count,
            distinct_digests=run.distinct_digests,
            newly_stored_blobs=run.newly_stored_blobs,
        )
        _log_counts(report)
        return report

    async def _store(
        self,
        member: ArchiveMember,
        parsed: ParsedCampPath,
        *,
        year: int,
        event: Event,
        imported_on: date,
    ) -> None:
        """File the source document (or keep the one already filed) and the camp-file record."""
        await file_source(
            self._caselists,
            SourceDocument(
                sha256=member.sha256,
                byte_size=member.byte_size,
                source_format=parsed.source_format,
                origin=SourceOrigin.OPENEV,
                first_seen_snapshot=imported_on,
                last_seen_snapshot=imported_on,
            ),
        )
        already = await self._caselists.list_camp_files(
            source_sha256=member.sha256, year=year, event=event, limit=1
        )
        if already.items:
            return
        await self._caselists.record_camp_file(
            CampFile(
                source_sha256=member.sha256,
                camp=parsed.camp,
                year=year,
                event=event,
                file_title=parsed.file_title,
                snapshot=imported_on,
                parse_warnings=parsed.warnings,
            )
        )


def _log_counts(report: OpenEvImportReport) -> None:
    """Counts, the year and the event. Never a path, a filename, a title or a camp's file."""
    logger.info(
        "imported OpenEv release",
        extra={
            "release": report.release,
            "imported_on": report.imported_on.isoformat(),
            "applied": report.applied,
            "members": report.member_count,
            "distinct_digests": report.distinct_digests,
            "newly_stored_blobs": report.newly_stored_blobs,
            "counts": {str(name): count for name, count in report.counts.items()},
            "skipped": {str(reason): count for reason, count in report.skipped.items()},
            "warnings": report.warning_count,
            "unknown_camps": report.unknown_camp_count,
            "caselist_duplicates": report.caselist_duplicate_count,
        },
    )
