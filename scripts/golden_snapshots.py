"""The golden corpus's source snapshots: copied out of a local store, recorded, and checked.

`v1-e09-t01-golden-card-fixtures`, under the PM's ruling of 2026-11-14 (Q2 B): the repository is
public, so **no source page or snapshot enters it**. Each case's `case.json` records what identifies
its snapshot instead (`snapshot`, :class:`SnapshotRecord`): the raw bytes' SHA-256 and size, the
normalized text's SHA-256 and the stored document's, the URL, the fetch date and the access status.
The snapshots themselves sit in a local folder outside the repository and outside every worktree,
one folder per case:

    <snapshot folder>/<case_id>/raw              the response body exactly as stored
    <snapshot folder>/<case_id>/normalized.json  the stored `debate-snapshot-text/1` document

`import_golden_card.py record` writes them from the store `debate-research fetch` filled, and
`import_golden_card.py check --snapshots` verifies them. This module is what both run on, and what
`label_golden_card.py` reads a snapshot through.

## Reading the store

A snapshot is read the way the platform reads one: its record through
:class:`~debate_core.integrations.local.SqliteArticleRepository` and its blobs through
:meth:`~debate_core.application.snapshot_service.SnapshotService.load`, which checks every hash
before it returns. The SQLite file is opened read-only, and as immutable when it has no `-wal`
file, so copying a snapshot out of the store neither migrates it nor writes anything into it.

## Verifying a copy

:func:`load_recorded_snapshot` reads one case's copy back and fails outright, by
:class:`SnapshotProblemCode`, when it is missing, when the raw bytes do not hash to the recorded
digest or are not the recorded size, when the document does not hash to the recorded digest or is
malformed, when its text does not hash to the recorded digest, or when its text is not what the
current normalizer makes of it: the recorded version must be the current one, and normalizing the
text again must give the same text (the normalizer is idempotent, `docs/evidence/normalization.md`).

## Reproducing a card's evidence

A case's evidence is its segments, `[start, end)` ranges of the snapshot's normalized text in
source order, as a card quotes them (`EvidenceSelection.of_offsets`). :func:`reproduces` says whether
they give the team card's evidence. Both sides are compared in one form (:func:`comparison_form`):

* the team card's body as the parser copied it, put through the evidence normalizer, then each of
  the format profile's omission markers (`…`, `...`, `[…]`, `[...]`, `***`) read as a word break;
* the snapshot's segments, each read as written, with a word break between two segments (a card
  stores no joiner; its render shows an omission marker there);
* in both, every whitespace gap, a space or a paragraph break, read as one space, and nothing else
  changed: no case folding, no quote or dash folding.

Paragraph breaks are not compared because a cutter routinely runs a source's paragraphs together,
and the parser joins a card's own paragraphs with a line break, which the normalizer reads as a
space. Every other character must be the same.

Owned by `v1-e09-t01-golden-card-fixtures`.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sqlite3
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

from debate_core.application.snapshot_service import LoadedSnapshot, SnapshotService
from debate_core.domain import AccessStatus, ProvenanceMode, SpanPurpose, SpanStyle
from debate_core.evidence.hashing import sha256_text
from debate_core.evidence.normalization import NORMALIZER_VERSION, normalize
from debate_core.evidence.snapshot_text import (
    MalformedSnapshotText,
    SnapshotText,
    SnapshotTextKeyMismatch,
    decode_snapshot_text,
    encode_snapshot_text,
)
from debate_core.integrations.local import (
    DATABASE_FILENAME,
    FsSnapshotStore,
    SqliteArticleRepository,
    SqliteDatabase,
)

__all__ = [
    "ACCESS_STATUSES_DROPPED",
    "DEFAULT_SNAPSHOT_FOLDER",
    "EXPECTED_FORMAT",
    "NORMALIZED_NAME",
    "RAW_NAME",
    "FetchOutcome",
    "FetchReading",
    "SnapshotProblem",
    "SnapshotProblemCode",
    "SnapshotRecord",
    "StoreError",
    "case_structure_problems",
    "comparison_form",
    "expected_structure_problems",
    "load_from_store",
    "load_recorded_snapshot",
    "outside_every_checkout",
    "read_fetch_report",
    "reproduced_text",
    "reproduces",
    "team_comparison_text",
    "team_segments",
    "write_snapshot_copy",
]

#: The PM's default for the local snapshot folder (2026-11-14): outside the repository and every
#: worktree, beside the operator's other local platform files.
DEFAULT_SNAPSHOT_FOLDER: Final = Path("~/.debate-intelligence/golden-snapshots")

RAW_NAME: Final = "raw"
NORMALIZED_NAME: Final = "normalized.json"

#: The format identifier of a case's `expected.json`.
EXPECTED_FORMAT: Final = "golden-card-expected/1"

#: Statuses that drop a case from the corpus: the source is no longer lawfully readable in full.
#: A metered, truncated or registration-walled page is PAYWALLED, never ACCESSIBLE (`AccessStatus`),
#: which covers a login-gated page and one cut short. ERROR (a transport or server failure) and
#: UNKNOWN (not fetched) drop nothing: the case is fetched again.
ACCESS_STATUSES_DROPPED: Final = frozenset(
    {
        AccessStatus.PAYWALLED,
        AccessStatus.BLOCKED,
        AccessStatus.ROBOTS_DISALLOWED,
        AccessStatus.NOT_FOUND,
        AccessStatus.UNSUPPORTED_TYPE,
    }
)

_SHA256: Final = re.compile(r"[0-9a-f]{64}")
_ISO_DATE: Final = re.compile(r"\d{4}-\d{2}-\d{2}")
_HTTP_URL: Final = re.compile(r"https?://\S+")
_CASE_ID: Final = re.compile(r"(policy|ld|pf)-\d{3}")


# --------------------------------------------------------------------------------------------
# Where the copies may live
# --------------------------------------------------------------------------------------------


def _checkouts(repository: Path) -> list[Path]:
    """The repository and every worktree of it, as `git worktree list` names them."""
    found = [repository.resolve()]
    try:
        listing = subprocess.run(
            ["git", "-C", str(repository), "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return found
    found += [
        Path(line.removeprefix("worktree ")).resolve()
        for line in listing.splitlines()
        if line.startswith("worktree ")
    ]
    return found


def outside_every_checkout(folder: Path, repository: Path) -> bool:
    """Whether `folder` lies outside the repository and outside every worktree of it."""
    resolved = folder.expanduser().resolve()
    return not any(
        resolved == checkout or checkout in resolved.parents for checkout in _checkouts(repository)
    )


# --------------------------------------------------------------------------------------------
# What case.json records
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SnapshotRecord:
    """A case's snapshot, as `case.json` records it: digests, URL, date and status, never text."""

    url: str
    canonical_url: str
    final_url: str | None
    fetched_on: str
    access_status: str
    provenance_mode: str
    raw_sha256: str
    raw_byte_size: int
    normalized_text_sha256: str
    normalized_document_sha256: str
    normalizer_version: str
    extractor_version: str
    content_type: str | None
    paragraph_count: int

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> SnapshotRecord:
        return cls(**{name: data[name] for name in cls.__dataclass_fields__})

    @classmethod
    def of(cls, loaded: LoadedSnapshot, *, url: str, final_url: str | None) -> SnapshotRecord:
        snapshot = loaded.snapshot
        return cls(
            url=url,
            canonical_url=snapshot.canonical_url,
            final_url=final_url,
            fetched_on=snapshot.retrieved_at.date().isoformat(),
            access_status=snapshot.access_status.value,
            provenance_mode=snapshot.provenance_mode.value,
            raw_sha256=snapshot.sha256,
            raw_byte_size=len(loaded.raw_bytes),
            normalized_text_sha256=snapshot.normalized_text_hash,
            normalized_document_sha256=snapshot.normalized_blob_key,
            normalizer_version=snapshot.normalizer_version,
            extractor_version=snapshot.extractor_version,
            content_type=snapshot.content_type,
            paragraph_count=len(loaded.normalized.paragraphs),
        )


# --------------------------------------------------------------------------------------------
# The fetch reports `debate-research fetch --json` wrote
# --------------------------------------------------------------------------------------------


class FetchOutcome(StrEnum):
    """What one case's fetch report says to do with the case."""

    RECORD = "record"
    DROP = "drop"
    FETCH_AGAIN = "fetch again"
    NO_REPORT = "no fetch report"
    ANOTHER_LINK = "the report is for another link"
    NOT_RETRIEVED = "the snapshot was not retrieved from the publisher"


@dataclass(frozen=True)
class FetchReading:
    """One case's fetch report, read: the outcome and what recording needs. No page text."""

    outcome: FetchOutcome
    access_status: str | None = None
    snapshot_id: str | None = None
    final_url: str | None = None


def read_fetch_report(path: Path, source_link: str) -> FetchReading:
    """Read the `--json` envelope `debate-research fetch` wrote for one case's source link.

    An ACCESSIBLE report is under `data`, every other status's under `error.details`. A missing or
    unreadable file, or a report with no access status, is :attr:`FetchOutcome.NO_REPORT`.
    """
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return FetchReading(FetchOutcome.NO_REPORT)
    report: Any = None
    if isinstance(envelope, dict):
        report = envelope.get("data")
        if report is None and isinstance(envelope.get("error"), dict):
            report = envelope["error"].get("details")
    if not isinstance(report, dict) or report.get("access_status") not in AccessStatus.__members__:
        return FetchReading(FetchOutcome.NO_REPORT)
    status = AccessStatus(report["access_status"])
    if report.get("requested_url") != source_link:
        return FetchReading(FetchOutcome.ANOTHER_LINK, status.value)
    if status in ACCESS_STATUSES_DROPPED:
        return FetchReading(FetchOutcome.DROP, status.value)
    snapshot = report.get("snapshot")
    if status is not AccessStatus.ACCESSIBLE or not isinstance(snapshot, dict):
        return FetchReading(FetchOutcome.FETCH_AGAIN, status.value)
    if report.get("provenance_mode") != ProvenanceMode.PUBLISHER_RETRIEVED.value:
        return FetchReading(FetchOutcome.NOT_RETRIEVED, status.value)
    return FetchReading(
        FetchOutcome.RECORD,
        status.value,
        snapshot_id=str(snapshot.get("snapshot_id")),
        final_url=report.get("final_url"),
    )


# --------------------------------------------------------------------------------------------
# Reading the store, read-only
# --------------------------------------------------------------------------------------------


class StoreError(RuntimeError):
    """The store holds no database, or not the snapshot a report names, or a damaged one."""


class _NoClock:
    """`SnapshotService.load` reads no clock; the port is required all the same."""

    def now(self) -> datetime:
        raise AssertionError("loading a snapshot never reads the clock")


class _NoIds:
    """`SnapshotService.load` mints no id; the port is required all the same."""

    def new_id(self) -> str:
        raise AssertionError("loading a snapshot never mints an id")


def load_from_store(store_dir: Path, snapshot_id: str) -> LoadedSnapshot:
    """The snapshot `snapshot_id` in the store at `store_dir`, every hash checked, read-only."""
    database_path = store_dir.expanduser() / DATABASE_FILENAME
    if not database_path.is_file():
        raise StoreError("the store has no database; is it the data folder `debate-research fetch` used?")
    # Read-only, and without the -wal and -shm files a read-only connection to a WAL database
    # otherwise leaves behind: with no -wal file, every committed write is in the database file
    # itself, so it can be read as immutable. A -wal file means a writer is open or ended without a
    # checkpoint; then the read goes through SQLite's locking, still read-only.
    wal = database_path.with_name(f"{database_path.name}-wal")
    flags = "mode=ro" if wal.exists() else "mode=ro&immutable=1"
    connection = sqlite3.connect(
        f"{database_path.resolve().as_uri()}?{flags}", uri=True, isolation_level=None
    )
    connection.row_factory = sqlite3.Row
    try:
        database = SqliteDatabase(connection, path=database_path)
        service = SnapshotService(
            blobs=FsSnapshotStore(store_dir.expanduser()), clock=_NoClock(), id_generator=_NoIds()
        )

        async def load() -> LoadedSnapshot:
            snapshot = await SqliteArticleRepository(database).get_snapshot(snapshot_id)
            return await service.load(snapshot)

        try:
            return asyncio.run(load())
        except Exception as error:  # noqa: BLE001 - every failure is one refusal, named by its type
            raise StoreError(f"snapshot {snapshot_id} cannot be loaded: {type(error).__name__}") from error
    finally:
        connection.close()


def _write_atomically(path: Path, data: bytes) -> None:
    temporary = path.with_name(f".{path.name}.partial")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def write_snapshot_copy(loaded: LoadedSnapshot, folder: Path) -> None:
    """Write one case's copy, `raw` and `normalized.json`, into `folder` (created if needed)."""
    document = encode_snapshot_text(loaded.normalized)
    if hashlib.sha256(document).hexdigest() != loaded.snapshot.normalized_blob_key:
        raise StoreError("the normalized document does not encode to the bytes the store holds")
    folder.mkdir(parents=True, exist_ok=True)
    _write_atomically(folder / RAW_NAME, loaded.raw_bytes)
    _write_atomically(folder / NORMALIZED_NAME, document)


# --------------------------------------------------------------------------------------------
# Verifying a copy
# --------------------------------------------------------------------------------------------


class SnapshotProblemCode(StrEnum):
    MISSING = "the snapshot copy is missing"
    RAW_DIGEST = "the raw bytes do not hash to the recorded SHA-256"
    RAW_SIZE = "the raw bytes are not the recorded size"
    DOCUMENT_DIGEST = "the normalized document does not hash to the recorded SHA-256"
    DOCUMENT_MALFORMED = "the normalized document is malformed"
    TEXT_DIGEST = "the normalized text does not hash to the recorded SHA-256"
    NORMALIZER = "the text is not what the current normalizer makes of it"


class SnapshotProblem(Exception):
    def __init__(self, code: SnapshotProblemCode) -> None:
        super().__init__(code.value)
        self.code = code


def load_recorded_snapshot(folder: Path, record: SnapshotRecord) -> SnapshotText:
    """Read one case's copy back, checked against `record`; raise :class:`SnapshotProblem`."""
    raw_path, document_path = folder / RAW_NAME, folder / NORMALIZED_NAME
    if not raw_path.is_file() or not document_path.is_file():
        raise SnapshotProblem(SnapshotProblemCode.MISSING)
    raw = raw_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != record.raw_sha256:
        raise SnapshotProblem(SnapshotProblemCode.RAW_DIGEST)
    if len(raw) != record.raw_byte_size:
        raise SnapshotProblem(SnapshotProblemCode.RAW_SIZE)
    try:
        text = decode_snapshot_text(
            document_path.read_bytes(), expected_key=record.normalized_document_sha256
        )
    except SnapshotTextKeyMismatch as error:
        raise SnapshotProblem(SnapshotProblemCode.DOCUMENT_DIGEST) from error
    except MalformedSnapshotText as error:
        raise SnapshotProblem(SnapshotProblemCode.DOCUMENT_MALFORMED) from error
    if sha256_text(text.text) != record.normalized_text_sha256:
        raise SnapshotProblem(SnapshotProblemCode.TEXT_DIGEST)
    if (
        text.normalizer_version != NORMALIZER_VERSION
        or record.normalizer_version != NORMALIZER_VERSION
        or normalize(text.text, NORMALIZER_VERSION).text != text.text
    ):
        raise SnapshotProblem(SnapshotProblemCode.NORMALIZER)
    return text


# --------------------------------------------------------------------------------------------
# Reproducing the evidence
# --------------------------------------------------------------------------------------------

#: The only whitespace normalized text holds (rule 6 of `evidence-normalizer-v1`).
_GAP: Final = re.compile(r"[ \n]+")


def comparison_form(text: str) -> str:
    """Normalized text with every whitespace gap, a space or a paragraph break, read as one space."""
    return _GAP.sub(" ", text).strip(" ")


def team_segments(evidence_text: str, omission_markers: Iterable[str]) -> list[str]:
    """The team card's body, normalized, in comparison form, split at its omission markers."""
    normalized = normalize(evidence_text, NORMALIZER_VERSION).text
    markers = sorted({marker for marker in omission_markers if marker}, key=len, reverse=True)
    if markers:
        normalized = re.sub("|".join(re.escape(marker) for marker in markers), "\0", normalized)
    return [segment for segment in (comparison_form(part) for part in normalized.split("\0")) if segment]


def team_comparison_text(evidence_text: str, omission_markers: Iterable[str]) -> str:
    """The team card's body in comparison form: each omission marker read as a word break."""
    return " ".join(team_segments(evidence_text, omission_markers))


def reproduced_text(snapshot_text: str, segments: Sequence[Sequence[int]]) -> str:
    """The case's segments of the snapshot, in comparison form, a word break between two."""
    return " ".join(comparison_form(snapshot_text[start:end]) for start, end in segments)


def reproduces(
    snapshot_text: str, segments: Sequence[Sequence[int]], evidence_text: str, omission_markers: Iterable[str]
) -> bool:
    """Whether the segments give the team card's evidence exactly, in comparison form."""
    return bool(segments) and reproduced_text(snapshot_text, segments) == team_comparison_text(
        evidence_text, omission_markers
    )


# --------------------------------------------------------------------------------------------
# The structure CI checks: what a committed case must record, and nothing it may not
# --------------------------------------------------------------------------------------------

_CASE_KEYS: Final = frozenset(
    {
        "case_id",
        "candidate_id",
        "event",
        "season",
        "source_type",
        "length_band",
        "omission_cut",
        "coach_cut_and_reviewed_for_names",
        "research_need",
        "source_link",
        "parser_version",
        "imported_on",
        "snapshot",
    }
)


def case_structure_problems(case: Mapping[str, Any], folder_name: str) -> list[str]:
    """What a committed `case.json` lacks or holds that it may not. Empty when it is whole."""
    problems: list[str] = []
    if case.get("case_id") != folder_name or not _CASE_ID.fullmatch(folder_name):
        problems.append("case_id is not the folder's name, or not <event>-<three digits>")
    if case.get("coach_cut_and_reviewed_for_names") is not True:
        problems.append("the coach's attestation is missing")
    extra = sorted(set(case) - _CASE_KEYS)
    if extra:
        problems.append(f"unexpected keys: {', '.join(extra)}")
    snapshot = case.get("snapshot")
    if not isinstance(snapshot, dict):
        return [*problems, "no snapshot record"]
    missing = sorted(set(SnapshotRecord.__dataclass_fields__) - set(snapshot))
    if missing:
        return [*problems, f"snapshot record lacks: {', '.join(missing)}"]
    extra = sorted(set(snapshot) - set(SnapshotRecord.__dataclass_fields__))
    if extra:
        problems.append(f"snapshot record has unexpected keys: {', '.join(extra)}")
    for name in ("raw_sha256", "normalized_text_sha256", "normalized_document_sha256"):
        if not isinstance(snapshot[name], str) or not _SHA256.fullmatch(snapshot[name]):
            problems.append(f"snapshot {name} is not a SHA-256")
    for name in ("url", "canonical_url"):
        if not isinstance(snapshot[name], str) or not _HTTP_URL.fullmatch(snapshot[name]):
            problems.append(f"snapshot {name} is not an http(s) URL")
    if snapshot["url"] != case.get("source_link"):
        problems.append("snapshot url is not the case's source link")
    if not isinstance(snapshot["fetched_on"], str) or not _ISO_DATE.fullmatch(snapshot["fetched_on"]):
        problems.append("snapshot fetched_on is not a date")
    if snapshot["access_status"] != AccessStatus.ACCESSIBLE.value:
        problems.append("snapshot access_status is not ACCESSIBLE")
    if snapshot["provenance_mode"] != ProvenanceMode.PUBLISHER_RETRIEVED.value:
        problems.append("snapshot provenance_mode is not PUBLISHER_RETRIEVED")
    for name in ("raw_byte_size", "paragraph_count"):
        if type(snapshot[name]) is not int or snapshot[name] <= 0:
            problems.append(f"snapshot {name} is not a positive count")
    return problems


_EXPECTED_KEYS: Final = frozenset({"format", "case_id", "tag", "cite", "research_need", "segments", "spans"})
_SPAN_KEYS: Final = frozenset({"start", "end", "style", "purpose"})
#: Words that would name evidence text in `expected.json`, which holds offsets only.
_TEXT_KEYS: Final = frozenset({"text", "evidence", "evidence_text", "body", "quote", "quotation"})


def _is_offset(value: Any) -> bool:
    return type(value) is int and value >= 0


def _segment_problems(segments: Any) -> list[str]:
    if not isinstance(segments, list) or not segments:
        return ["segments is not a non-empty list"]
    previous_end = -1
    for segment in segments:
        if not (isinstance(segment, list) and len(segment) == 2 and all(_is_offset(v) for v in segment)):
            return ["a segment is not a [start, end] pair of offsets"]
        start, end = segment
        if start >= end:
            return ["a segment is empty or reversed"]
        if start <= previous_end:
            return ["segments are not in order, separated by omitted text"]
        previous_end = end
    return []


def _span_problems(spans: Any, segments: list[list[int]]) -> list[str]:
    if not isinstance(spans, list):
        return ["spans is not a list"]
    problems: list[str] = []
    by_style: dict[str, list[tuple[int, int]]] = {style.value: [] for style in SpanStyle}
    for span in spans:
        if not isinstance(span, dict) or set(span) != _SPAN_KEYS:
            return ["a span is not {start, end, style, purpose}"]
        start, end, style, purpose = span["start"], span["end"], span["style"], span["purpose"]
        if not (_is_offset(start) and _is_offset(end) and start < end):
            return ["a span's offsets are not a non-empty range"]
        if style not in by_style:
            return [f"a span's style is not one of {', '.join(sorted(by_style))}"]
        if purpose is not None and purpose not in {p.value for p in SpanPurpose}:
            return ["a span's purpose is not a SpanPurpose or null"]
        if not any(a <= start and end <= b for a, b in segments):
            problems.append("a span is not inside one segment")
        by_style[style].append((start, end))
    for style, ranges in by_style.items():
        ordered = sorted(ranges)
        if any(later[0] < earlier[1] for earlier, later in zip(ordered, ordered[1:], strict=False)):
            problems.append(f"{style} spans overlap")
    underlined = by_style[SpanStyle.UNDERLINE.value]
    for start, end in by_style[SpanStyle.HIGHLIGHT.value]:
        covered = sum(max(0, min(end, b) - max(start, a)) for a, b in underlined)
        if covered != end - start:
            problems.append("a highlight is not inside the underlining")
    return sorted(set(problems))


def _has_text_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(key in _TEXT_KEYS or _has_text_key(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_has_text_key(item) for item in value)
    return False


def expected_structure_problems(expected: Mapping[str, Any], folder_name: str) -> list[str]:
    """What a committed `expected.json` lacks or holds that it may not. Empty when it is whole.

    It holds offsets into the recorded snapshot and the team's own tag, cite and research need,
    never evidence text (the spec's forbidden list): any key naming text is refused.
    """
    problems: list[str] = []
    if expected.get("format") != EXPECTED_FORMAT:
        problems.append(f"format is not {EXPECTED_FORMAT}")
    if expected.get("case_id") != folder_name:
        problems.append("case_id is not the folder's name")
    if set(expected) != _EXPECTED_KEYS:
        problems.append(f"keys are not exactly {', '.join(sorted(_EXPECTED_KEYS))}")
    if _has_text_key(dict(expected)):
        problems.append("a key names evidence text; expected.json holds offsets only")
    for name in ("tag", "research_need"):
        if not isinstance(expected.get(name), str) or not expected[name].strip():
            problems.append(f"{name} is not a non-empty string")
    if not isinstance(expected.get("cite"), dict):
        problems.append("cite is not an object")
    segment_problems = _segment_problems(expected.get("segments"))
    if segment_problems:
        return problems + segment_problems
    return problems + _span_problems(expected.get("spans"), expected["segments"])
