"""Re-deriving camp and title for camp files already imported, from the paths already recorded.

The v1-e30-t06 backfill imported a real OpenEv release whose 105 camp files all came out camp
`UNKNOWN`, because :mod:`~debate_core.application.caselist.camp_metadata` looked for the camp only
in a folder or at the start of a filename (`v1-e30-t08`). The bytes, the digests and the manifest's
key were right; the camp, the title and the warnings derived from each path were not. Importing the
release again would not fix them: an `UNCHANGED` file keeps its manifest row byte for byte and
writes no record (:mod:`~debate_core.application.caselist.openev_manifest`), which is exactly what
makes a re-import a no-op. So this is the other operation, `debate-research caselist
reimport-openev-metadata`: read what the release manifest recorded, and re-derive only what the
path determines.

This module is the pure part: the manifest in, the re-derived manifest and the corrected rows out.
The camp-file records are written by
:meth:`~debate_core.application.caselist.openev_import_service.OpenEvImportService.reimport_metadata`,
because the importers are the only modules that write caselist records and each consults the
removal suppression list at the write
(`packages/debate_core/tests/application/caselist/test_import_paths_consult_suppression.py`).

## What it changes, and what it cannot

For every member row the importer derived metadata for (`NEW`, `UNCHANGED`, `CHANGED`,
`DUPLICATE`), the four fields :func:`~debate_core.application.caselist.camp_metadata.parse_camp_path`
produces — `camp`, `lab`, `file_title`, `warnings` — are derived again from the row's own `path`
with the current alias table. Every other field of every row stays as it was, and the summary row is
recounted the way the importer counts it, which changes its `warnings` count and nothing else. The
release's :class:`~debate_core.domain.caselist.CampFile` records are corrected the same way: one per
digest, the one the importer recorded, from that digest's first row in path order; its digest,
year, event and import date are left alone.

What it never touches: the bytes (no blob is read or written; the blob store is only asked
whether each digest is held), a `sha256`, a `byte_size`, a path, a classification, or the
manifest's key, which is the release's key and is returned unchanged for the caller to write back
to. It downloads nothing: it reads one local manifest and the local records, and has no network
port.

The manifest's bytes do change, so the bucket's copy differs until it is published again, and
`caselist status` reports the release as drifted until then: one checksum mismatch, on the
manifest's own key, with every source present and verified. `caselist publish --caselist openev
--snapshot <year>-<event>` re-uploads a manifest whose bucket digest differs
(:mod:`~debate_core.application.caselist.publish_service`: a manifest is not content-addressed, and
a listed manifest is uploaded unless the bucket already holds the same bytes); the bucket's
versioning keeps the old manifest as a noncurrent version for the environment's retention window.

## Running it twice

A second run with the same table finds every field already derived and returns the same lines, so
the manifest is byte-identical and no record is written. After a camp is added to the alias table,
running it again corrects the files that name it.

## Refused

A release this machine has no manifest for (:class:`NoRecordedRelease`); a manifest that is not one
the importer writes (:class:`~debate_core.application.caselist.publish_plan.UnreadableManifest`); and
a row naming a file the removal suppression list stops, which
:func:`~debate_core.application.caselist.manifest.render_rows` refuses before anything is written —
the fix for that is to finish the removal on this machine.

## What is logged

Counts, the year and the event. Never a path, a title or a camp's file
(`docs/policies/caselist-data-use.md`, rule 4).
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import cast

from debate_core.application.caselist.camp_metadata import (
    UNKNOWN_CAMP,
    CampAliases,
    parse_camp_path,
)
from debate_core.application.caselist.manifest import render_rows
from debate_core.application.caselist.openev_manifest import (
    openev_manifest_key,
    openev_release_name,
    read_recorded_release,
    summary_row,
)
from debate_core.application.caselist.pipeline import STORED_CLASSIFICATIONS, Classification
from debate_core.application.errors import DomainError
from debate_core.application.ports.evidence_store import ObjectKey
from debate_core.application.ports.suppression import SuppressionState
from debate_core.domain.caselist import CampFile, Event

__all__ = [
    "DERIVED_FIELDS",
    "NoRecordedRelease",
    "OpenEvMetadataReimport",
    "RederivedRelease",
    "corrected_camp_file",
    "log_reimport",
    "rederive_release",
]

logger = logging.getLogger(__name__)

DERIVED_FIELDS = ("camp", "lab", "file_title", "warnings")
"""The member-row fields a path determines, and so the only ones a metadata re-import rewrites."""

_STORED = frozenset(str(classification) for classification in STORED_CLASSIFICATIONS)


class NoRecordedRelease(DomainError):
    """This machine holds no manifest for the release, so there is nothing to re-derive."""

    def __init__(self, key: ObjectKey) -> None:
        self.key = key
        super().__init__(f"no local manifest at {key}; import the release before re-deriving its metadata")


@dataclass(frozen=True, slots=True)
class OpenEvMetadataReimport:
    """What one metadata re-import changed, or under a dry run would change."""

    year: int
    event: Event
    applied: bool
    """False for a dry run, which reads everything and writes no record."""

    manifest_key: ObjectKey
    """The release's own key: the one the manifest was read from and is written back to."""

    manifest_lines: tuple[str, ...]
    recorded_lines: tuple[str, ...]
    """The manifest as it was read, for the caller to compare with :attr:`manifest_lines`."""

    rows: int = 0
    """Member rows whose metadata was re-derived: every row the importer derived metadata for."""

    camps_before: Mapping[str, int] = field(default_factory=lambda: {})
    camps_after: Mapping[str, int] = field(default_factory=lambda: {})
    rows_changed: int = 0
    titles_changed: int = 0
    warnings_changed: int = 0
    camp_files_updated: int = 0
    """Camp-file records rewritten (dry: that would be), one per digest whose fields changed."""

    camp_files_missing: int = 0
    """Digests with a manifest row but no camp-file record, which this does not create."""

    blobs_missing: int = 0
    """Digests the manifest names that the local blob store does not hold. Reported, not fetched."""

    @property
    def release(self) -> str:
        return openev_release_name(self.year, self.event)

    @property
    def manifest_changed(self) -> bool:
        return self.manifest_lines != self.recorded_lines

    @property
    def unknown_before(self) -> int:
        return self.camps_before.get(UNKNOWN_CAMP, 0)

    @property
    def unknown_after(self) -> int:
        return self.camps_after.get(UNKNOWN_CAMP, 0)


@dataclass(frozen=True, slots=True)
class RederivedRelease:
    """The release manifest with every row's metadata derived again, before any record is touched."""

    year: int
    event: Event
    manifest_key: ObjectKey
    manifest_lines: tuple[str, ...]
    recorded_lines: tuple[str, ...]
    camp_file_rows: Mapping[str, Mapping[str, object]]
    """Each stored digest's first row in path order: the row its camp-file record was made from."""

    rows: int
    camps_before: Mapping[str, int]
    camps_after: Mapping[str, int]
    rows_changed: int
    titles_changed: int
    warnings_changed: int

    def report(
        self, *, applied: bool, camp_files_updated: int, camp_files_missing: int, blobs_missing: int
    ) -> OpenEvMetadataReimport:
        return OpenEvMetadataReimport(
            year=self.year,
            event=self.event,
            applied=applied,
            manifest_key=self.manifest_key,
            manifest_lines=self.manifest_lines,
            recorded_lines=self.recorded_lines,
            rows=self.rows,
            camps_before=self.camps_before,
            camps_after=self.camps_after,
            rows_changed=self.rows_changed,
            titles_changed=self.titles_changed,
            warnings_changed=self.warnings_changed,
            camp_files_updated=camp_files_updated,
            camp_files_missing=camp_files_missing,
            blobs_missing=blobs_missing,
        )


def rederive_release(
    *,
    year: int,
    event: Event,
    recorded_manifest: Iterable[str],
    aliases: CampAliases,
    suppression: SuppressionState,
) -> RederivedRelease:
    """Derive every stored row's camp, lab, title and warnings again from its path; keep the rest.

    Raises :class:`NoRecordedRelease` for no lines,
    :class:`~debate_core.application.caselist.publish_plan.UnreadableManifest` for a manifest the
    importer did not write, and
    :class:`~debate_core.application.caselist.manifest.SuppressedRowRefused` for a row naming a
    file `suppression` stops — all before anything is written.
    """
    key = openev_manifest_key(year, event)
    recorded_lines = tuple(line for line in recorded_manifest if line.strip())
    if not recorded_lines:
        raise NoRecordedRelease(key)
    recorded = read_recorded_release(key, recorded_lines)

    before: Counter[str] = Counter()
    after: Counter[str] = Counter()
    rows: list[dict[str, object]] = []
    firsts: dict[str, dict[str, object]] = {}
    derived = rows_changed = titles_changed = warnings_changed = 0
    for path in sorted(recorded.rows):
        row = dict(recorded.rows[path])
        if row.get("classification") in _STORED:
            parsed = parse_camp_path(path, aliases=aliases)
            fresh: dict[str, object] = {
                "camp": parsed.camp,
                "lab": parsed.lab,
                "file_title": parsed.file_title,
                "warnings": list(parsed.warnings),
            }
            derived += 1
            before[str(row.get("camp"))] += 1
            after[parsed.camp] += 1
            rows_changed += any(row.get(name) != value for name, value in fresh.items())
            titles_changed += row.get("file_title") != parsed.file_title
            warnings_changed += row.get("warnings") != fresh["warnings"]
            row.update(fresh)
            digest = row.get("sha256")
            if isinstance(digest, str):
                firsts.setdefault(digest, row)
        rows.append(row)

    summary = summary_row(rows, year=year, event=event, suppressed=_recorded_suppressed(recorded_lines))
    return RederivedRelease(
        year=year,
        event=event,
        manifest_key=key,
        manifest_lines=tuple(render_rows([*rows, summary], suppression=suppression, disclosure_scope=None)),
        recorded_lines=recorded_lines,
        camp_file_rows=firsts,
        rows=derived,
        camps_before=dict(sorted(before.items())),
        camps_after=dict(sorted(after.items())),
        rows_changed=rows_changed,
        titles_changed=titles_changed,
        warnings_changed=warnings_changed,
    )


def corrected_camp_file(existing: CampFile, row: Mapping[str, object]) -> CampFile:
    """`existing` with the camp, title and warnings `row` now carries; its identity and date kept."""
    return CampFile.model_validate(
        {
            **existing.model_dump(),
            "camp": row["camp"],
            "file_title": row["file_title"],
            "parse_warnings": tuple(_texts(row["warnings"])),
        }
    )


def _recorded_suppressed(lines: Iterable[str]) -> int:
    """The `SUPPRESSED` count the recorded summary carries, which no member row can recount."""
    for line in lines:
        row = _mapping(json.loads(line))
        if row is not None and row.get("kind") == "summary":
            value = (_mapping(row.get("classifications")) or {}).get(str(Classification.SUPPRESSED), 0)
            return value if isinstance(value, int) else 0
    return 0


def _mapping(value: object) -> dict[str, object] | None:
    """`value` as a JSON object, or `None` when it is not one."""
    return cast("dict[str, object]", value) if isinstance(value, dict) else None


def _texts(value: object) -> list[str]:
    """A row's `warnings`, which the manifest holds as a list of strings."""
    return [str(item) for item in cast("list[object]", value)] if isinstance(value, list) else []


def log_reimport(report: OpenEvMetadataReimport) -> None:
    """Counts, the year and the event. Never a path, a title or a camp's file."""
    logger.info(
        "re-derived OpenEv release metadata",
        extra={
            "release": report.release,
            "applied": report.applied,
            "rows": report.rows,
            "rows_changed": report.rows_changed,
            "titles_changed": report.titles_changed,
            "unknown_before": report.unknown_before,
            "unknown_after": report.unknown_after,
            "camp_files_updated": report.camp_files_updated,
            "camp_files_missing": report.camp_files_missing,
            "blobs_missing": report.blobs_missing,
            "manifest_changed": report.manifest_changed,
        },
    )
