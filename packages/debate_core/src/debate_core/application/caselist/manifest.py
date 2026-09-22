"""The per-snapshot JSONL record of what one import saw, and where it is filed.

A manifest is the provenance document for one weekly archive: one row per member, saying what the
file was, what the archive said about it, what the parser could and could not read, and what the
importer decided it was relative to the week before. It is what an operator reads when the counts
look wrong, what `v1-e30-t05` publishes to the evidence bucket, and what a removal request
(`v1-e30-t07`) is answered from.

## Where it goes

Under the object key `manifests/<caselist>/<snapshot>.jsonl`, which is the key the evidence
bucket uses and therefore the key the local evidence object store uses — so
`debate-research store sync` publishes it with no further arrangement. On disk that resolves to
`<data_dir>/objects/manifests/<caselist>/<snapshot>.jsonl`, because
:class:`~debate_core.integrations.local.FsEvidenceObjectStore` roots named objects under
`objects/` to keep them out of the content-addressed `blobs/` tree. The session report records
the difference from ac4's literal path.

## It describes the archive, never the run

Every field in a manifest is a fact about the archive and the week before it, so two imports of
one archive produce identical bytes (ac3). That rules out three things a manifest might otherwise
carry, and the ruling is the reason they are absent:

* **No timestamp.** When the import ran is a property of the run.
* **No "newly stored" count.** The first import of an archive writes blobs and the second writes
  none; both describe the same archive. `ImportReport.newly_stored_blobs` carries that, for the
  console.
* **No dry-run flag.** A planned import and an applied one see the same archive.

Determinism is otherwise mechanical: rows are sorted by path, keys within a row are sorted, and
the separators are fixed.

## The shape

Every line is one JSON object carrying `schema_version` and `kind`. `kind` is `member` for the
rows and `summary` for the single trailing one, so a consumer can read the file in one pass
without counting lines or seeking to the end.

A member row is flat — `school`, `side`, `round`, `round_normalized` rather than nested objects —
because the thing that reads it is usually `jq` or a dataframe, and a flat row is one column each.
Fields that do not apply to a row are `null` rather than absent, so every row has the same keys
and a table built from the file has no ragged columns.

## What is in it that is not in a log

School, team code, tournament, round and the archive path. That is deliberate and it is the
reason manifests are filed where they are: `docs/policies/caselist-data-use.md` names the local
evidence store and the private buckets' `manifests/` prefix as two of the four places this
information may live, and forbids it in application logs anywhere.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

from debate_core.application.caselist.import_service import Classification, ImportedEntry, ImportReport
from debate_core.application.ports.evidence_store import ObjectKey, validate_object_key

__all__ = [
    "DISCLOSURE_FIELDS",
    "MANIFEST_DIRECTORY",
    "MANIFEST_SCHEMA_VERSION",
    "common_member_fields",
    "counted",
    "manifest_key",
    "manifest_lines",
    "name_of",
    "read_manifest_lines",
    "render_manifest",
    "render_rows",
    "write_manifest",
    "write_manifest_lines",
    "write_manifest_text",
]

MANIFEST_SCHEMA_VERSION: Final = 1
"""Version of a manifest row. Bumped only by a change that breaks an existing reader.

On every row rather than once at the top of the file, because rows are read one at a time —
`jq`, a streaming loader, a `grep` for one path — and a version that only the first line carried
would not reach any of them.
"""

MANIFEST_DIRECTORY: Final = "manifests"
"""The object-key prefix manifests live under, in the bucket and in the local store alike."""

#: Fixed separators, so two renderings of one report are byte-identical.
_COMPACT_SEPARATORS: Final = (",", ":")

#: Prefix of the temp file a manifest is written to before it is renamed into place.
_TEMPORARY_FILE_PREFIX: Final = ".incoming-manifest-"


def manifest_key(caselist: str, snapshot: date) -> ObjectKey:
    """The object key one snapshot's manifest is filed under.

    `manifests/hsld26/2026-09-15.jsonl`. Validated through the evidence store's own key rules, so
    a caselist slug that somehow contained a `/` or a `..` is refused here rather than writing
    outside the evidence directory.
    """
    return validate_object_key(f"{MANIFEST_DIRECTORY}/{caselist}/{snapshot.isoformat()}.jsonl")


def manifest_lines(report: ImportReport) -> list[str]:
    """Every line of the manifest for one import, in order, without their newlines."""
    rows = [_member_row(report, index) for index in range(len(report.entries))]
    rows.append(_summary_row(report))
    return render_rows(rows)


def render_rows(rows: Iterable[Mapping[str, object]]) -> list[str]:
    """Manifest rows as lines: sorted keys, fixed separators, so one row always renders one way.

    Shared by every manifest, which is what makes an OpenEv manifest's rows the same layout as a
    caselist manifest's, and a row read back and rendered again the same bytes it was read from.
    """
    return [
        json.dumps(row, sort_keys=True, separators=_COMPACT_SEPARATORS, ensure_ascii=False) for row in rows
    ]


def render_manifest(report: ImportReport) -> str:
    """The whole manifest as text: one JSON object per line, newline-terminated."""
    return "".join(f"{line}\n" for line in manifest_lines(report))


def read_manifest_lines(path: Path) -> list[str]:
    """The lines of the manifest already at `path`, or none when nothing has been written there."""
    location = Path(path)
    if not location.is_file():
        return []
    return location.read_text(encoding="utf-8").splitlines()


def write_manifest(report: ImportReport, destination: Path) -> Path:
    """Write the manifest to `destination`, atomically, and return the path.

    Atomic for the same reason a blob is: a sync running against a half-written manifest would
    publish a truncated provenance record, and a truncated JSONL file is one a reader cannot tell
    from a complete one. The temp file is created in the destination's own directory so the
    rename stays within one filesystem.

    The caller chooses the path — normally
    `FsEvidenceObjectStore(data_dir).path_for(manifest_key(...))` — because where the evidence
    store puts an object is the store's decision, not this module's.
    """
    return write_manifest_text(render_manifest(report), destination)


def write_manifest_lines(lines: Iterable[str], destination: Path) -> Path:
    """Write manifest lines, each newline-terminated, to `destination`, atomically."""
    return write_manifest_text("".join(f"{line}\n" for line in lines), destination)


def write_manifest_text(text: str, destination: Path) -> Path:
    """Write already-rendered manifest text to `destination`, atomically, and return the path."""
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=_TEMPORARY_FILE_PREFIX, suffix=".tmp")
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    return path


# ------------------------------------------------------------------------------------------------
# Rows
# ------------------------------------------------------------------------------------------------


DISCLOSURE_FIELDS: Final = (
    "school",
    "team_code",
    "side",
    "tournament",
    "round",
    "round_normalized",
    "copy_index",
)
"""The member-row fields a caselist disclosure fills. Every other import writes them as `null`."""


def common_member_fields(entry: ImportedEntry[Any], warnings: Sequence[str]) -> dict[str, object]:
    """The member-row fields every manifest has, whatever kind of import wrote it."""
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "kind": "member",
        "path": entry.path,
        "classification": name_of(entry.classification),
        "skip_reason": name_of(entry.skip_reason),
        "sha256": entry.sha256,
        "byte_size": entry.byte_size,
        "format": name_of(entry.source_format),
        "warnings": list(warnings),
    }


def _member_row(report: ImportReport, index: int) -> dict[str, object]:
    """One archive member, or one path the previous archive had and this one does not."""
    entry = report.entries[index]
    parsed = entry.parsed
    round_label = parsed.round_label if parsed is not None else None
    return {
        **common_member_fields(entry, parsed.warnings if parsed is not None else ()),
        "school": parsed.school if parsed is not None else None,
        "team_code": parsed.team_code if parsed is not None else None,
        "side": name_of(parsed.side) if parsed is not None else None,
        "tournament": parsed.tournament if parsed is not None else None,
        "round": round_label.raw if round_label is not None else None,
        "round_normalized": (name_of(round_label.normalized) if round_label is not None else None),
        "copy_index": parsed.copy_index if parsed is not None else None,
    }


def _summary_row(report: ImportReport) -> dict[str, object]:
    """The trailing row: what this archive is, and what it was classified against.

    Nothing here is a property of the run — see this module's docstring for why `applied` and
    `newly_stored_blobs` are deliberately absent.
    """
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "kind": "summary",
        "caselist": report.caselist,
        "snapshot": report.snapshot.isoformat(),
        "event": str(report.event),
        "archive_sha256": report.archive_sha256,
        "previous_snapshot": (
            report.previous_snapshot.isoformat() if report.previous_snapshot is not None else None
        ),
        "members": report.member_count,
        "distinct_sha256": report.distinct_digests,
        "warnings": report.warning_count,
        "classifications": counted(report.counts),
        "skipped": counted(report.skipped),
    }


def counted[KeyT: StrEnum](counts: Mapping[KeyT, int]) -> dict[str, int]:
    """A count mapping with enum keys rendered as their names, in sorted order."""
    return {str(key): counts[key] for key in sorted(counts, key=str)}


def name_of(value: object) -> str | None:
    """An enum member's value, or `None`. Keeps `Classification.NEW` out of the JSON."""
    if value is None:
        return None
    return str(value)


#: Re-exported so a reader of this module sees what a `classification` field can hold.
MANIFEST_CLASSIFICATIONS: Final = tuple(str(name) for name in Classification)
