"""The student search pilot's index: what one build is, as its manifest and its pointer say (`v1-e39-t02`).

`debate-research tub index build` turns the operator's parsed store into one SQLite file with FTS5,
one document per card cluster, and this module's :class:`SearchIndexManifest` beside it.
`tub index publish` uploads the file gzipped and the manifest under `reports/tub/search/<index id>/`
and writes :class:`SearchIndexPointer` to `reports/tub/search/current.json` last, so the pilot's
function (ADR-0019 (c)) never meets half an index.

## The same store gives the same bytes

Nothing here records a time, a host or a path. The manifest holds what the index was built from
(each store's version directory and a digest of its occurrence rows, the suppression list's digest),
the versions of everything that shaped it, its counts, and the sha256 of the SQLite file and of the
gzip object. Built twice from one store, by one SQLite and one zlib, every byte is the same, and so
is the index id, which is the start of the SQLite file's digest.

## What a reader may rely on

:data:`SEARCH_INDEX_FORMAT_VERSION` names the SQLite schema the writer creates
(`docs/data/search-index.md`). A reader refuses an index whose format version it does not know,
and the publisher refuses one whose parser or fingerprint version is not the running build's.
The index uses no SQLite or FTS5 feature newer than :data:`SQLITE_FEATURE_CEILING`, the version
the function's Lambda image is built against; the manifest says which SQLite built it.

## No person in it

The manifest holds counts, versions, digests and caselist slugs, nothing else: no school, team
code, tournament, round, path or text (data-use policy, "What a report may show").
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from typing import Any, Final, Literal, NamedTuple, Self, cast

from pydantic import Field, model_validator

from debate_core.domain.base import DomainModel, NonEmptyText, Sha256Hex
from debate_core.domain.debate_files import FontSizeSpan, FormattingSpan
from debate_core.domain.schema_export import JSON_SCHEMA_DIALECT
from debate_core.domain.style_profile import RunEmphasis

__all__ = [
    "DEFAULT_PROVENANCE_LIMIT",
    "INDEX_ID_LENGTH",
    "SEARCH_INDEX_FORMAT_VERSION",
    "SEARCH_INDEX_GZIP_NAME",
    "SEARCH_INDEX_MANIFEST_NAME",
    "SEARCH_INDEX_MANIFEST_SCHEMA_FILENAME",
    "SEARCH_INDEX_POINTER_KEY",
    "SEARCH_INDEX_PREFIX",
    "SEARCH_INDEX_SQLITE_NAME",
    "SQLITE_FEATURE_CEILING",
    "IndexCounts",
    "IndexFile",
    "IndexedFontSizeSpan",
    "IndexedFormattingSpan",
    "SearchIndexManifest",
    "SearchIndexPointer",
    "StoreState",
    "SuppressionListState",
    "decode_font_size_spans",
    "decode_formatting_spans",
    "encode_font_size_spans",
    "encode_formatting_spans",
    "index_object_key",
    "read_aloud_text",
    "render_search_index_manifest_schema",
]

SEARCH_INDEX_FORMAT_VERSION: Final = 1
"""The SQLite schema the writer creates. Bumped by any change a reader would break on."""

SQLITE_FEATURE_CEILING: Final = "3.40.0"
"""The newest SQLite whose features the index may use: the Lambda image's (ADR-0019 (c) 1)."""

DEFAULT_PROVENANCE_LIMIT: Final = 5
"""How many occurrences of a cluster keep their provenance, unless the build is told otherwise."""

INDEX_ID_LENGTH: Final = 16
"""Hex characters of the SQLite file's sha256 that name an index: its directory in the bucket."""

SEARCH_INDEX_PREFIX: Final = "reports/tub/search/"
"""Where published indexes live in an evidence bucket (`docs/architecture/evidence-store-layout.md`)."""

SEARCH_INDEX_POINTER_KEY: Final = f"{SEARCH_INDEX_PREFIX}current.json"
"""The pointer the function reads: written last, after the object and the manifest."""

SEARCH_INDEX_SQLITE_NAME: Final = "search-index.sqlite"
SEARCH_INDEX_GZIP_NAME: Final = f"{SEARCH_INDEX_SQLITE_NAME}.gz"
SEARCH_INDEX_MANIFEST_NAME: Final = "manifest.json"

SEARCH_INDEX_MANIFEST_SCHEMA_FILENAME: Final = "search-index-manifest.schema.json"
"""The published schema's file name, under `docs/data/`."""

_INDEX_ID = re.compile(rf"^[0-9a-f]{{{INDEX_ID_LENGTH}}}$")


def index_object_key(index_id: str, name: str) -> str:
    """`reports/tub/search/<index id>/<name>`: where one published index's file lives."""
    if _INDEX_ID.match(index_id) is None:
        raise ValueError(f"an index id is {INDEX_ID_LENGTH} lowercase hex characters; got {index_id!r}")
    return f"{SEARCH_INDEX_PREFIX}{index_id}/{name}"


class StoreState(DomainModel):
    """One store an index was built from: which directory, and a digest of the rows read in it."""

    caselist: NonEmptyText = Field(description="Caselist slug, or `openev` for camp files.")
    version_directory: NonEmptyText = Field(description="The parsed store's version directory read.")
    latest_snapshot: NonEmptyText = Field(
        description="The latest `last_snapshot` among its rows: a date, or a release for `openev`."
    )
    occurrence_rows: int = Field(ge=0, description="How many occurrence rows the directory held.")
    occurrences_sha256: Sha256Hex = Field(
        description="SHA-256 of the rows as sorted canonical JSON lines, whatever order they are listed in."
    )


class SuppressionListState(DomainModel):
    """The suppression list the build applied, as a digest: its entries are not repeated here."""

    entries: int = Field(ge=0, description="Suppression entries read, every action included.")
    path_holds: int = Field(ge=0, description="Path-hold entries read, lifted or not.")
    sha256: Sha256Hex = Field(description="SHA-256 of the entries and holds as canonical lines, sorted.")


class IndexCounts(DomainModel):
    """What the build read, kept and left out. Counts only."""

    documents: int = Field(
        ge=0, description="Documents in the index: one per cluster with a surviving occurrence."
    )
    documents_by_store: dict[str, int] = Field(description="Documents per caselist slug or `openev`.")
    occurrences: int = Field(ge=0, description="Occurrences indexed: every surviving row of every document.")
    provenance_rows: int = Field(ge=0, description="Occurrences whose provenance the index keeps.")
    occurrence_rows_read: int = Field(ge=0, description="Occurrence rows read from the stores.")
    suppressed_occurrences: int = Field(
        ge=0, description="Rows the suppression list or a path hold stops, left out."
    )
    clusters_left_out: int = Field(ge=0, description="Clusters with no surviving occurrence, left out.")
    unattributed_representatives: int = Field(
        ge=0, description="Documents whose representative has no disclosure or release record on record."
    )


class IndexFile(DomainModel):
    """One file of a built index: its name, size and sha256."""

    name: NonEmptyText = Field(description="File name, the same locally and in the bucket.")
    bytes: int = Field(ge=0, description="Size in bytes.")
    sha256: Sha256Hex = Field(description="SHA-256 of the file's bytes.")


class SearchIndexManifest(DomainModel):
    """`manifest.json`: what one index is, what built it and what it was built from."""

    manifest_version: Literal[1] = Field(default=1, description="This manifest's own shape: 1.")
    format_version: int = Field(
        ge=1, description="The SQLite schema's version (`docs/data/search-index.md`)."
    )
    index_id: NonEmptyText = Field(description="The first 16 hex characters of the SQLite file's sha256.")
    parser_version: NonEmptyText = Field(description="The parser version every store read was parsed by.")
    fingerprint_version: NonEmptyText = Field(
        description="The fingerprint version every cluster id is under."
    )
    sqlite_version: NonEmptyText = Field(description="The SQLite library that wrote the file.")
    sqlite_feature_ceiling: NonEmptyText = Field(
        description="The newest SQLite whose features the file may use: the function's image's."
    )
    gzip_level: Literal[6] = Field(default=6, description="The gzip object's compression level.")
    provenance_limit: int = Field(
        ge=1, description="How many occurrences of a document keep their provenance."
    )
    stores: tuple[StoreState, ...] = Field(description="Every store read, by caselist slug.")
    snapshot: NonEmptyText = Field(
        description="The latest caselist snapshot among the stores read; a release when only `openev` is."
    )
    suppression: SuppressionListState = Field(description="The suppression list the build applied.")
    counts: IndexCounts
    sqlite_file: IndexFile = Field(description="The SQLite file, as built.")
    gzip_object: IndexFile = Field(description="The gzip object: what is published and downloaded.")

    @model_validator(mode="after")
    def _check_manifest(self) -> Self:
        if self.index_id != self.sqlite_file.sha256[:INDEX_ID_LENGTH]:
            raise ValueError("an index id is the start of its SQLite file's sha256")
        caselists = [store.caselist for store in self.stores]
        if not caselists or caselists != sorted(set(caselists)):
            raise ValueError("an index names each store it read once, in order")
        if sum(self.counts.documents_by_store.values()) != self.counts.documents:
            raise ValueError("the documents of each store add up to the documents of the index")
        return self

    def to_json_bytes(self) -> bytes:
        """The manifest's bytes: two-space indented JSON, keys in model order, UTF-8, a final newline."""
        return (json.dumps(self.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n").encode("utf-8")


class SearchIndexPointer(DomainModel):
    """`reports/tub/search/current.json`: which index is current, and how to check what was fetched."""

    pointer_version: Literal[1] = Field(default=1, description="This pointer's own shape: 1.")
    format_version: int = Field(ge=1, description="The current index's SQLite schema version.")
    index_id: NonEmptyText = Field(description="The current index's id.")
    manifest_key: NonEmptyText = Field(description="The current index's manifest, by bucket key.")
    manifest_sha256: Sha256Hex = Field(description="SHA-256 of that manifest's bytes.")
    object_key: NonEmptyText = Field(description="The current index's gzip object, by bucket key.")
    object_sha256: Sha256Hex = Field(description="SHA-256 of the gzip object's bytes.")
    sqlite_sha256: Sha256Hex = Field(description="SHA-256 of the SQLite file the object holds.")

    def to_json_bytes(self) -> bytes:
        """The pointer's bytes, written the way the manifest's are."""
        return (json.dumps(self.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n").encode("utf-8")


class IndexedFormattingSpan(NamedTuple):
    """A formatting span as the index stores it: a parser span without its rule id and match source."""

    emphasis: RunEmphasis
    start_offset: int
    end_offset: int
    highlight_color: str | None = None


class IndexedFontSizeSpan(NamedTuple):
    """A font-size span as the index stores it."""

    start_offset: int
    end_offset: int
    half_points: int


def encode_formatting_spans(spans: Sequence[FormattingSpan]) -> str:
    """`documents.formatting_spans`: each span as `[emphasis, start, end]`, and a colour after a highlight's.

    In the parser's order, as compact JSON: `[["UNDERLINE",0,15],["HIGHLIGHT",9,22,"cyan"]]`. The
    parser's `rule_id` and `match_source` say how a span was found, not what it looks like, so they
    are left out: neither the card page nor `formatting_sha256`'s coverage reads them, and they were
    more than half the index (PM review 2026-10-20, question 4).
    """
    return _compact(
        [span.emphasis.value, span.start_offset, span.end_offset]
        + ([span.highlight_color] if span.highlight_color is not None else [])
        for span in spans
    )


def decode_formatting_spans(stored: str) -> tuple[IndexedFormattingSpan, ...]:
    """The spans :func:`encode_formatting_spans` wrote, in order. `ValueError` for anything else."""
    decoded: list[IndexedFormattingSpan] = []
    for item in _items(stored):
        if len(item) not in (3, 4) or not isinstance(item[0], str):
            raise ValueError(
                "a stored formatting span is [emphasis, start, end] or [emphasis, start, end, colour]"
            )
        try:
            emphasis = RunEmphasis(item[0])
        except ValueError:
            raise ValueError(f"not an emphasis: {item[0]!r}") from None
        start, end = _offsets(item[1], item[2])
        colour = item[3] if len(item) == 4 else None
        if not isinstance(colour, str | None) or (emphasis is RunEmphasis.HIGHLIGHT) != (colour is not None):
            raise ValueError("a highlight span names its colour, and only a highlight span does")
        decoded.append(IndexedFormattingSpan(emphasis, start, end, colour))
    return tuple(decoded)


def encode_font_size_spans(spans: Sequence[FontSizeSpan]) -> str:
    """`documents.font_size_spans`: each span as `[start, end, half_points]`, in order, as compact JSON."""
    return _compact([span.start_offset, span.end_offset, span.half_points] for span in spans)


def decode_font_size_spans(stored: str) -> tuple[IndexedFontSizeSpan, ...]:
    """The spans :func:`encode_font_size_spans` wrote, in order. `ValueError` for anything else."""
    decoded: list[IndexedFontSizeSpan] = []
    for item in _items(stored):
        if len(item) != 3:
            raise ValueError("a stored font-size span is [start, end, half_points]")
        start, end = _offsets(item[0], item[1])
        half_points = _integer(item[2])
        if half_points <= 0:
            raise ValueError("a stored font size is a positive number of half-points")
        decoded.append(IndexedFontSizeSpan(start, end, half_points))
    return tuple(decoded)


def _compact(items: Iterable[list[Any]]) -> str:
    return json.dumps(list(items), separators=(",", ":"), ensure_ascii=False)


def _items(stored: str) -> list[list[object]]:
    try:
        parsed: object = json.loads(stored)
    except json.JSONDecodeError:
        raise ValueError("stored spans are not JSON") from None
    if not isinstance(parsed, list):
        raise ValueError("stored spans are a JSON array of arrays")
    items: list[list[object]] = []
    for item in cast(list[object], parsed):
        if not isinstance(item, list):
            raise ValueError("stored spans are a JSON array of arrays")
        items.append(cast(list[object], item))
    return items


def _integer(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("a stored span's offsets and sizes are integers")
    return value


def _offsets(start: object, end: object) -> tuple[int, int]:
    first, last = _integer(start), _integer(end)
    if not 0 <= first < last:
        raise ValueError("a stored span starts before it ends, at an offset of 0 or more")
    return first, last


def read_aloud_text(text: str, spans: Iterable[FormattingSpan | IndexedFormattingSpan]) -> str:
    """The stretches of `text` that are underlined or highlighted, in order, joined by a space.

    Touching or overlapping spans are one stretch, so an underline and the highlight inside it give
    the words once. Takes the parser's spans or the index's, which read the same here.
    """
    intervals = sorted((span.start_offset, span.end_offset) for span in spans if span.emphasis in _READ_ALOUD)
    merged: list[list[int]] = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    stretches = (text[start:end].strip() for start, end in merged)
    return " ".join(stretch for stretch in stretches if stretch)


_READ_ALOUD: Final = frozenset({RunEmphasis.UNDERLINE, RunEmphasis.HIGHLIGHT})


def render_search_index_manifest_schema() -> dict[str, Any]:
    """The manifest's JSON Schema, for `docs/data/search-index-manifest.schema.json`."""
    return {"$schema": JSON_SCHEMA_DIALECT, **SearchIndexManifest.model_json_schema(mode="serialization")}
