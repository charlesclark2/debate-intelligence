"""The port the search index build writes through (`v1-e39-t02`), and what it is handed to write.

:class:`~debate_core.application.search_index_build.SearchIndexBuildService` decides every row: which
clusters, which representative, which text, which provenance. A :class:`SearchIndexWriter` only puts
those rows into a file, and :class:`~debate_core.integrations.local.search_index.SqliteSearchIndexWriter`
is the one that does, with the standard library's `sqlite3` and `gzip`. The SQLite schema is the
writer's, documented in `docs/data/search-index.md` and versioned by
:data:`~debate_core.domain.search_index.SEARCH_INDEX_FORMAT_VERSION`.

## Searchable, stored, and never stored

A :class:`SearchDocument` carries four searchable fields, the tag, the cite, the read-aloud text and
the evidence text, and everything else as stored fields a reader shows or filters by and never
matches words against. An :class:`IndexedOccurrence` is all stored: the school, team code, side,
tournament and round of a disclosure are provenance, never searchable (the data-use policy's E39
gate item 8). Nothing here has a field for a cutter mark, a file name, a disclosure path, or a name
from a document body, so no writer can store one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from debate_core.domain.debate_files import FontSizeSpan, FormattingSpan

__all__ = [
    "IndexedOccurrence",
    "SearchDocument",
    "SearchIndexSink",
    "SearchIndexWriter",
]


@dataclass(frozen=True, slots=True)
class IndexedOccurrence:
    """One surviving occurrence of a document's cluster, in the representative order.

    `ordinal` 0 is the representative. Every occurrence keeps the source SHA-256 and the disclosure
    digest, which the function checks against a newer suppression list (`v1-e39-t07`); only the first
    `provenance_limit` keep who disclosed them, and the rest have `provenance` False and every
    disclosure field `None`. The school, team code, tournament and round are kept off the `repr`.
    """

    ordinal: int
    caselist: str
    source_sha256: str
    disclosure: str | None
    first_element_index: int
    last_element_index: int
    snapshot: str
    last_snapshot: str
    completeness: str
    attributed: bool
    provenance: bool
    side: str | None = None
    school: str | None = field(default=None, repr=False)
    team_code: str | None = field(default=None, repr=False)
    tournament: str | None = field(default=None, repr=False)
    round: str | None = field(default=None, repr=False)
    camp: str | None = None
    camp_year: int | None = None
    camp_event: str | None = None
    camp_file_title: str | None = None


@dataclass(frozen=True, slots=True)
class SearchDocument:
    """One card cluster: its representative's text and formatting, and every surviving occurrence.

    `doc_id` is the document's rank in (caselist, cluster id) order, from 1, so a document's id
    depends on the store's content and never on the order anything was read in. The text fields are
    the representative card's, exactly as its document record holds them, but for `cite`, which is
    its full cite without the cutter mark the convention puts at its end. Its evidence text is kept
    off the `repr`. `first_seen` and `last_seen` are the earliest and latest snapshot dates of a
    caselist document's occurrences, and `None` for a camp document, whose releases have no date.
    """

    doc_id: int
    caselist: str
    cluster_id: str
    event: str
    camp: str | None
    tag: str | None
    cite: str
    short_cite: str | None
    read_aloud: str = field(repr=False)
    text: str = field(repr=False)
    completeness: str
    formatting_spans: tuple[FormattingSpan, ...] = field(repr=False)
    font_size_spans: tuple[FontSizeSpan, ...] = field(repr=False)
    sides: tuple[str, ...]
    first_seen: str | None
    last_seen: str | None
    file_count: int
    team_count: int
    occurrences: tuple[IndexedOccurrence, ...] = field(repr=False)


@runtime_checkable
class SearchIndexSink(Protocol):
    """One index being written. Documents may arrive in any order; the file does not depend on it."""

    def add(self, document: SearchDocument) -> None:
        """Write one document and its occurrences."""
        ...

    def finish(self) -> None:
        """Build the full-text index over every document, compact the file and close it."""
        ...

    def abandon(self) -> None:
        """Close without finishing. The caller removes the file."""
        ...


@runtime_checkable
class SearchIndexWriter(Protocol):
    """Writes the pilot's index file, and its gzip object, deterministically."""

    @property
    def sqlite_version(self) -> str:
        """The SQLite library version this writer writes with, for the manifest."""
        ...

    def create(self, destination: Path) -> SearchIndexSink:
        """Start a new index at `destination`, which must not exist yet."""
        ...

    def compress(self, source: Path, destination: Path) -> None:
        """Write `source` gzipped to `destination`: level 6, mtime 0, no file name in the header."""
        ...
