"""The OpenEv manifest: one camp release's files, for one year and event, however many downloads.

Filed under `manifests/openev/<year>-<event>.jsonl` — `manifests/openev/2026-policy.jsonl` — which
is the key :mod:`debate_core.application.caselist.publish_plan` already publishes and checks, and
which resolves to `<data_dir>/objects/manifests/openev/…` in the local evidence object store for
the same reason a caselist manifest does (see :mod:`debate_core.application.caselist.manifest`).

## The same rows, plus camp fields

Every row has every key a caselist manifest row has, with the same schema version, so one reader
handles both: `jq`, a dataframe, and the publisher's
:func:`~debate_core.application.caselist.publish_plan.sources_in_manifest`, which reads only
`kind`, `classification`, `sha256` and `byte_size`. The disclosure fields (`school`, `team_code`,
`side`, …) are `null`, and :data:`CAMP_FIELDS` are added:

`camp`, `lab`, `file_title`
    What :func:`~debate_core.application.caselist.camp_metadata.parse_camp_path` read.
`year`
    The release's topic year, which is also the `raw/openev/<year>/` prefix its sources publish to.
`imported_on`
    The date given to the import that recorded this row (`--snapshot`, default today).
`archive_sha256`
    The download this row came from — a camp release accumulates across several.
`existing_origin`, `existing_caselist`
    The source document the bytes were already filed as before this import, if any:
    `CASELIST_ARCHIVE` and the caselist slug when a team had disclosed the same file, which is the
    link E31 and E32 read. `null` for new bytes and for a second copy within one download.

The summary row keeps the caselist summary's keys, adds `year` and `archives` (every download
digest the rows name, sorted), and leaves `archive_sha256` and `previous_snapshot` `null`, because
a camp release is not one download and has no previous week.

## It accumulates

A caselist manifest describes one archive, because a weekly archive is cumulative. An OpenEv
download is not: it is whichever files the operator fetched, and the scheduled sync
(`v1-e34-t02`) fetches only the ones that are new. So each import is *merged into* the release's
existing manifest rather than replacing it, and the existing manifest's `{path: sha256}` is the
baseline the import classifies against:

* A path this import classifies exactly as before — `UNCHANGED`, or skipped or suppressed for the
  same reason — keeps its existing row, byte for byte. The manifest records what each file was
  when it entered the store; a re-import saw nothing new and writes nothing new.
* A path that is new, or `CHANGED`, gets this import's row.
* A path this import did not contain keeps its row. A camp file absent from one download has not
  been withdrawn; it just was not fetched, so `REMOVED` never appears here.

That is what makes re-importing a release a no-op (ac3) — identical manifest bytes, whatever date
it runs on — and what keeps a one-file weekly import from erasing the other hundred.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Final

from debate_core.application.caselist.camp_metadata import ParsedCampPath
from debate_core.application.caselist.manifest import (
    DISCLOSURE_FIELDS,
    MANIFEST_SCHEMA_VERSION,
    common_member_fields,
    name_of,
    render_rows,
)
from debate_core.application.caselist.pipeline import (
    STORED_CLASSIFICATIONS,
    Classification,
    ImportedEntry,
)
from debate_core.application.caselist.publish_plan import (
    OPENEV,
    UnreadableManifest,
    snapshot_manifest_key,
)
from debate_core.application.ports.evidence_store import ObjectKey
from debate_core.domain.caselist import Event

__all__ = [
    "CAMP_FIELDS",
    "RecordedRelease",
    "merged_manifest_lines",
    "openev_manifest_key",
    "openev_release_name",
    "read_recorded_release",
]

CAMP_FIELDS: Final = (
    "camp",
    "lab",
    "file_title",
    "year",
    "imported_on",
    "archive_sha256",
    "existing_origin",
    "existing_caselist",
)
"""The member-row fields an OpenEv manifest adds to a caselist manifest's."""

_STORED: Final = frozenset(str(classification) for classification in STORED_CLASSIFICATIONS)


def openev_release_name(year: int, event: Event) -> str:
    """`2026-policy`: how `manifests/openev/` and `caselist publish --snapshot` name a release."""
    return f"{year:04d}-{event.value.lower()}"


def openev_manifest_key(year: int, event: Event) -> ObjectKey:
    """`manifests/openev/2026-policy.jsonl`, through the publisher's own key rules."""
    return snapshot_manifest_key(OPENEV, openev_release_name(year, event))


@dataclass(frozen=True, slots=True)
class RecordedRelease:
    """What the release's existing manifest already records, read back as rows."""

    rows: Mapping[str, dict[str, object]]
    """Every member row, by path."""

    @property
    def baseline(self) -> dict[str, str]:
        """`{path: sha256}` for every stored row: what the pipeline classifies against."""
        return {
            path: str(row["sha256"])
            for path, row in self.rows.items()
            if row.get("classification") in _STORED and isinstance(row.get("sha256"), str)
        }


def read_recorded_release(key: ObjectKey, lines: Iterable[str]) -> RecordedRelease:
    """Read the release's existing manifest; no lines is a release nothing has been recorded for.

    Raises :class:`~debate_core.application.caselist.publish_plan.UnreadableManifest`, naming the
    line number and never the line, for anything that is not a row this module writes — merging
    into a manifest it cannot read would silently drop what that manifest recorded.
    """
    rows: dict[str, dict[str, object]] = {}
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            parsed: object = json.loads(line)
        except json.JSONDecodeError:
            raise UnreadableManifest(key, number, "not JSON") from None
        if not isinstance(parsed, dict):
            raise UnreadableManifest(key, number, "not a JSON object")
        row: dict[str, object] = parsed  # pyright: ignore[reportUnknownVariableType]
        if row.get("schema_version") != MANIFEST_SCHEMA_VERSION:
            raise UnreadableManifest(key, number, f"schema_version is not {MANIFEST_SCHEMA_VERSION}")
        if row.get("kind") == "summary":
            continue
        path = row.get("path")
        if row.get("kind") != "member" or not isinstance(path, str) or not path:
            raise UnreadableManifest(key, number, "neither a member row with a path nor the summary")
        rows[path] = row
    return RecordedRelease(rows=rows)


def merged_manifest_lines(
    entries: Sequence[ImportedEntry[ParsedCampPath]],
    recorded: RecordedRelease,
    *,
    year: int,
    event: Event,
    imported_on: date,
    archive_sha256: str,
) -> tuple[str, ...]:
    """The release's manifest once this import is merged in: member rows by path, then the summary."""
    rows = dict(recorded.rows)
    for entry in entries:
        if entry.classification is Classification.REMOVED:
            continue
        existing = rows.get(entry.path)
        if existing is not None and _same_outcome(entry, existing):
            continue
        rows[entry.path] = _member_row(
            entry, year=year, imported_on=imported_on, archive_sha256=archive_sha256
        )
    members = [rows[path] for path in sorted(rows)]
    return tuple(render_rows([*members, _summary_row(members, year=year, event=event)]))


def _same_outcome(entry: ImportedEntry[ParsedCampPath], row: Mapping[str, object]) -> bool:
    """Whether this import saw the path exactly as the recorded row did, so the row stands."""
    if entry.classification is Classification.UNCHANGED:
        return True
    if entry.skip_reason is not None:
        return row.get("skip_reason") == str(entry.skip_reason)
    if entry.classification is Classification.SUPPRESSED:
        return (
            row.get("classification") == str(Classification.SUPPRESSED) and row.get("sha256") == entry.sha256
        )
    return False


def _member_row(
    entry: ImportedEntry[ParsedCampPath], *, year: int, imported_on: date, archive_sha256: str
) -> dict[str, object]:
    parsed = entry.parsed
    existing = entry.existing_source
    return {
        **common_member_fields(entry, parsed.warnings if parsed is not None else ()),
        **dict.fromkeys(DISCLOSURE_FIELDS),
        "camp": parsed.camp if parsed is not None else None,
        "lab": parsed.lab if parsed is not None else None,
        "file_title": parsed.file_title if parsed is not None else None,
        "year": year,
        "imported_on": imported_on.isoformat(),
        "archive_sha256": archive_sha256,
        "existing_origin": name_of(existing.origin) if existing is not None else None,
        "existing_caselist": existing.caselist if existing is not None else None,
    }


def _summary_row(members: Sequence[Mapping[str, object]], *, year: int, event: Event) -> dict[str, object]:
    """The trailing row, counted from the merged member rows rather than from this one import."""
    classifications: dict[str, int] = {}
    skipped: dict[str, int] = {}
    digests: set[object] = set()
    archives: set[str] = set()
    warnings = 0
    for row in members:
        classification = row.get("classification")
        skip_reason = row.get("skip_reason")
        if isinstance(classification, str):
            classifications[classification] = classifications.get(classification, 0) + 1
        if isinstance(skip_reason, str):
            skipped[skip_reason] = skipped.get(skip_reason, 0) + 1
        if classification in _STORED:
            digests.add(row.get("sha256"))
        if row.get("warnings"):
            warnings += 1
        archive = row.get("archive_sha256")
        if isinstance(archive, str):
            archives.add(archive)
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "kind": "summary",
        "caselist": OPENEV,
        "snapshot": openev_release_name(year, event),
        "event": str(event),
        "year": year,
        "archive_sha256": None,
        "archives": sorted(archives),
        "previous_snapshot": None,
        "members": len(members),
        "distinct_sha256": len(digests),
        "warnings": warnings,
        "classifications": dict(sorted(classifications.items())),
        "skipped": dict(sorted(skipped.items())),
    }
