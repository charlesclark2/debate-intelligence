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
`openev_id`, `upstream_path_sha256`
    The row's upstream identity (`v1-e30-t14`): the OpenEv id it was downloaded as, and the SHA-256
    of that id's upstream path (`OpenEvFile.path`), never the path itself. A camp file changed
    upstream is uploaded again under a new id at the same path, so two rows whose digests agree are
    one camp path, whichever camp's folder each sat in. It is what lets a removal planned in prod,
    which never pulls and so has no delivery record, match a later upload as dev does. The pull
    knows both; a hand import knows the id only when the file is named `openev-<id>-…`, and never
    the path, so its row carries `null` for what it does not know. A row of a camp release that is
    a zip carries the zip's id and path. Rows written before `v1-e30-t14` have neither key until
    `caselist reimport-openev-metadata` re-derives them from this machine's delivery record
    (:func:`~debate_core.application.caselist.openev_metadata_reimport.rederive_release`). Both are
    additive keys, so `schema_version` stays `1`: every reader of a release manifest reads a row as
    a mapping and ignores, or keeps byte for byte, a key it does not know.

The summary row keeps the caselist summary's keys, adds `year` and `archives` (every download
digest the rows name, sorted), and leaves `archive_sha256` and `previous_snapshot` `null`, because
a camp release is not one download and has no previous week. It has no `first_seen`, the weekly
summary's count of files new to the caselist (`v1-e30-t08`): a release has no earlier snapshots to
be first seen against, and the key is additive, so a reader of both kinds already handles its
absence — while adding it here would change the bytes of every release manifest already written on
its next re-import.

## It accumulates

A caselist manifest describes one archive, because each caselist archive is a dated snapshot of
its own: a weekly is the window of a week's editing, and a complete archive the whole caselist on
its date. An OpenEv download is neither: it is whichever files the operator fetched, and the scheduled sync
(`v1-e34-t02`) fetches only the ones that are new. So each import is *merged into* the release's
existing manifest rather than replacing it, and the existing manifest's `{path: sha256}` is the
baseline the import classifies against:

* A path this import classifies exactly as before — `UNCHANGED`, or skipped for the same reason —
  keeps its existing row, byte for byte. The manifest records what each file was
  when it entered the store; a re-import saw nothing new and writes nothing new.
* A path that is new, or `CHANGED`, gets this import's row.
* A path this import did not contain keeps its row. A camp file absent from one download has not
  been withdrawn; it just was not fetched, so `REMOVED` never appears here.

That is what makes re-importing a release a no-op (ac3) — identical manifest bytes, whatever date
it runs on — and what keeps a one-file weekly import from erasing the other hundred.

## Suppressed files

A member the removal suppression list stops has no row (`v1-e30-t07`), and a recorded row whose
file has since been suppressed is dropped rather than carried forward. "Stops" is the whole file,
or the file at this row's camp path (:func:`~debate_core.application.ports.suppression.
camp_path_disclosure`, `v1-e30-t14`): a removal that withdrew one camp path of a file another
release or a team keeps. The summary's
`classifications` counts `SUPPRESSED` as the number of members of the import that last wrote the
manifest which the list stopped, plus recorded rows it dropped: a release manifest accumulates
across downloads, but a suppressed file leaves no row to accumulate from, so the count describes
the latest import and is the same on every re-import of it.
"""

from __future__ import annotations

import json
import re
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
from debate_core.application.ports.caselist_source import openev_id_of_inbox_name
from debate_core.application.ports.evidence_store import ObjectKey
from debate_core.application.ports.suppression import SuppressionState, camp_path_disclosure, camp_path_scope
from debate_core.domain.caselist import Event

__all__ = [
    "CAMP_FIELDS",
    "OpenEvUpstream",
    "RecordedRelease",
    "merged_manifest_lines",
    "openev_manifest_key",
    "openev_ids_by_source",
    "openev_release_name",
    "read_recorded_release",
    "row_upstream_identity",
    "summary_row",
    "upstream_fields",
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
    "openev_id",
    "upstream_path_sha256",
)
"""The member-row fields an OpenEv manifest adds to a caselist manifest's."""

_SHA256_HEX: Final = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class OpenEvUpstream:
    """Which OpenEv file a download was: its id, and the SHA-256 of its upstream path if known.

    What the pull hands an import so that every row of the download carries it (`v1-e30-t14`).
    Digests and an id only: the upstream path names the camp and the file.
    """

    openev_id: int
    path_sha256: str | None


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
    suppression: SuppressionState,
    upstream: OpenEvUpstream | None = None,
) -> tuple[str, ...]:
    """The release's manifest once this import is merged in: member rows by path, then the summary.

    `suppression` is the list the import read: suppressed members get no row, and recorded rows
    naming a file the list now stops, whole or at that row's camp path, are dropped (see the module
    docstring). `upstream` is which OpenEv file the download was, when the pull says so: each row
    this import writes carries it.
    """
    release = openev_release_name(year, event)
    rows = {
        path: row
        for path, row in recorded.rows.items()
        if not (
            isinstance(row.get("sha256"), str)
            and suppression.suppresses(str(row["sha256"]), disclosure=camp_path_disclosure(release, path))
        )
    }
    suppressed = len(recorded.rows) - len(rows)
    for entry in entries:
        if entry.classification is Classification.REMOVED:
            continue
        if entry.classification is Classification.SUPPRESSED:
            suppressed += 1
            rows.pop(entry.path, None)
            continue
        if entry.withheld:
            rows.pop(entry.path, None)
            continue
        existing = rows.get(entry.path)
        if existing is not None and _same_outcome(entry, existing):
            continue
        rows[entry.path] = _member_row(
            entry, year=year, imported_on=imported_on, archive_sha256=archive_sha256, upstream=upstream
        )
    members = [rows[path] for path in sorted(rows)]
    summary = summary_row(members, year=year, event=event, suppressed=suppressed)
    return tuple(
        render_rows([*members, summary], suppression=suppression, disclosure_scope=camp_path_scope(release))
    )


def _same_outcome(entry: ImportedEntry[ParsedCampPath], row: Mapping[str, object]) -> bool:
    """Whether this import saw the path exactly as the recorded row did, so the row stands."""
    if entry.classification is Classification.UNCHANGED:
        return True
    if entry.skip_reason is not None:
        return row.get("skip_reason") == str(entry.skip_reason)
    return False


def _member_row(
    entry: ImportedEntry[ParsedCampPath],
    *,
    year: int,
    imported_on: date,
    archive_sha256: str,
    upstream: OpenEvUpstream | None,
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
        **upstream_fields(entry.path, upstream),
    }


def upstream_fields(path: str, upstream: OpenEvUpstream | None) -> dict[str, object]:
    """The two identity keys of a row at `path`: from the pull's `upstream`, or what the name says."""
    if upstream is not None:
        return {"openev_id": upstream.openev_id, "upstream_path_sha256": upstream.path_sha256}
    return {"openev_id": openev_id_of_inbox_name(path.rsplit("/", 1)[-1]), "upstream_path_sha256": None}


def row_upstream_identity(row: Mapping[str, object]) -> tuple[int, str] | None:
    """`(openev_id, upstream_path_sha256)` of a release-manifest row that carries both, else `None`.

    A row from before `v1-e30-t14`, a hand import, or one whose keys are not an id and a digest,
    carries none: the reader then has only the delivery record, or the row's name, to go by.
    """
    openev_id, digest = row.get("openev_id"), row.get("upstream_path_sha256")
    if not isinstance(openev_id, int):
        return None
    if not isinstance(digest, str) or _SHA256_HEX.match(digest) is None:
        return None
    return openev_id, digest


def openev_ids_by_source(recorded: RecordedRelease) -> dict[str, int]:
    """Each stored camp file's OpenEv id, by its SHA-256: what the search index links a camp card to.

    From every stored member row whose `openev_id` is a positive whole number (`v1-e30-t14`), whether
    or not it also carries the path's digest: a hand import named `openev-<id>-…` knows the id alone.
    A row from before `v1-e30-t14`, or one with no id, gives none. A file at two paths of the release
    has the smaller of its ids, the first upload of those bytes, so the answer is the same whatever
    order the rows are in (`v1-e39-t16`).
    """
    ids: dict[str, int] = {}
    for row in recorded.rows.values():
        sha256, openev_id = row.get("sha256"), row.get("openev_id")
        if row.get("classification") not in _STORED or not isinstance(sha256, str):
            continue
        if isinstance(openev_id, bool) or not isinstance(openev_id, int) or openev_id < 1:
            continue
        ids[sha256] = min(openev_id, ids.get(sha256, openev_id))
    return ids


def summary_row(
    members: Sequence[Mapping[str, object]], *, year: int, event: Event, suppressed: int
) -> dict[str, object]:
    """The trailing row, counted from the merged member rows, plus `suppressed` (see above)."""
    classifications: dict[str, int] = {}
    if suppressed:
        classifications[str(Classification.SUPPRESSED)] = suppressed
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
        "members": len(members) + suppressed,
        "distinct_sha256": len(digests),
        "warnings": warnings,
        "classifications": dict(sorted(classifications.items())),
        "skipped": dict(sorted(skipped.items())),
    }
