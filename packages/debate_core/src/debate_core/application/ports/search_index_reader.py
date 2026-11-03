"""The port the student search pilot reads its index through (`v1-e39-t03`).

:class:`~debate_core.application.evidence_search.EvidenceSearchService` decides what a query means,
which rows a student may see and what a page holds. A :class:`SearchIndexReader` only runs the
statements that fetch rows from one `v1-e39-t02` index file, and
:class:`~debate_core.integrations.local.search_index_reader.SqliteSearchIndexReader` is the one that
does, read-only, with the standard library's `sqlite3`.

The rows carry what the index stores (`docs/data/search-index.md`), typed. A row's provenance fields
are as disclosed and kept off every `repr`; the evidence text is too.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from debate_core.domain.evidence_search import SearchFilters
from debate_core.domain.search_index import IndexedFontSizeSpan, IndexedFormattingSpan

__all__ = [
    "CountBatch",
    "CountRequest",
    "CountedRepresentative",
    "MatchBatch",
    "MatchRequest",
    "SearchIndexReader",
    "StoredDocument",
    "StoredHit",
    "StoredOccurrence",
    "UnreadableSearchIndex",
]


class UnreadableSearchIndex(Exception):
    """An index file this build cannot read: not an index, or a format version it does not read."""


@dataclass(frozen=True, slots=True)
class StoredOccurrence:
    """One row of the index's `occurrences` table. `ordinal` 0 is the document's representative.

    `first_element_index` and `last_element_index`, where the card is in its source, are read by a
    card's lookup and not by a search, whose rows leave them `None`: a download builds the card from
    its source through them (`v1-e39-t08`).
    """

    doc_id: int
    ordinal: int
    caselist: str
    source_sha256: str
    disclosure: str | None
    snapshot: str
    last_snapshot: str
    completeness: str
    attributed: bool
    provenance: bool
    side: str | None = None
    school: str | None = field(default=None, repr=False)
    team_code: str | None = field(default=None, repr=False)
    tournament: str | None = field(default=None, repr=False)
    round_label: str | None = field(default=None, repr=False)
    camp: str | None = None
    camp_year: int | None = None
    camp_event: str | None = None
    camp_file_title: str | None = None
    first_element_index: int | None = None
    last_element_index: int | None = None
    openev_id: int | None = None
    """A camp occurrence's OpenEv id, read by a card's lookup on a format 3 index and not by a search;
    `None` on formats 1 and 2, which have no such column (`v1-e39-t16`)."""


@dataclass(frozen=True, slots=True)
class StoredHit:
    """One matching document at `position` in its query's ranking, with its representative occurrence.

    `snippet` is FTS5's, its matched words between the domain's snippet markers.
    """

    position: int
    doc_id: int
    caselist: str
    cluster_id: str
    event: str
    camp: str | None
    tag: str | None
    short_cite: str | None
    snippet: str = field(repr=False)
    file_count: int
    team_count: int
    representative: StoredOccurrence


@dataclass(frozen=True, slots=True)
class StoredDocument:
    """One row of the index's `documents` table, its spans decoded."""

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
    formatting_spans: tuple[IndexedFormattingSpan, ...] = field(repr=False)
    font_size_spans: tuple[IndexedFontSizeSpan, ...] = field(repr=False)
    sides: tuple[str, ...]
    first_seen: str | None
    last_seen: str | None
    file_count: int
    team_count: int


@dataclass(frozen=True, slots=True)
class MatchRequest:
    """One batch of a ranking: the FTS5 expression, the rank function, the filters and the window.

    `expired` says whether the search's time budget is spent; the reader asks it while a statement
    runs, and stops the statement when it says so.

    A passage search (`v1-e39-t13`) also names its words, each an FTS5 phrase, and how many of them a
    document must match: the ranking is then of the documents matching at least `minimum_shared`.
    `passage_words` is empty for every other search.
    """

    expression: str
    rank: str
    filters: SearchFilters
    offset: int
    limit: int
    expired: Callable[[], bool] = field(repr=False)
    passage_words: tuple[str, ...] = field(default=(), repr=False)
    minimum_shared: int = 0


@dataclass(frozen=True, slots=True)
class MatchBatch:
    """What one batch fetched, in ranking order.

    `exhausted` when the ranking has no row after these; `interrupted` when the time budget stopped
    the statement, and `hits` is what it had fetched by then.
    """

    hits: tuple[StoredHit, ...]
    exhausted: bool
    interrupted: bool = False


@dataclass(frozen=True, slots=True)
class CountRequest:
    """One batch of a count: the documents the expression matches under the filters, after a doc id.

    The same expression, filters and passage words as a :class:`MatchRequest`, in doc id order rather
    than ranked, because a count needs no ranking and FTS5 gives rowid order without sorting.
    """

    expression: str
    filters: SearchFilters
    after: int
    limit: int
    expired: Callable[[], bool] = field(repr=False)
    passage_words: tuple[str, ...] = field(default=(), repr=False)
    minimum_shared: int = 0


@dataclass(frozen=True, slots=True)
class CountedRepresentative:
    """A matching document's id and its representative's digests: what the suppression list is asked."""

    doc_id: int
    source_sha256: str
    disclosure: str | None


@dataclass(frozen=True, slots=True)
class CountBatch:
    """What one batch of a count fetched, in doc id order; `exhausted` and `interrupted` as for a match."""

    rows: tuple[CountedRepresentative, ...]
    exhausted: bool
    interrupted: bool = False


@runtime_checkable
class SearchIndexReader(Protocol):
    """Reads one index file. Never writes it."""

    @property
    def index_id(self) -> str:
        """The index's id, as its manifest and pointer name it: cursors are bound to it."""
        ...

    @property
    def format_version(self) -> int:
        """The index file's format version: one of `READABLE_SEARCH_INDEX_FORMAT_VERSIONS`."""
        ...

    def match(self, request: MatchRequest) -> MatchBatch:
        """One batch of the documents the expression matches, best first, filtered."""
        ...

    def count(self, request: CountRequest) -> CountBatch:
        """One batch of the documents the same expression and filters match, by doc id, for counting."""
        ...

    def document(self, caselist: str, cluster_id: str) -> StoredDocument | None:
        """The document for one cluster, or `None` when the index has none."""
        ...

    def occurrences(self, doc_id: int) -> tuple[StoredOccurrence, ...]:
        """Every occurrence of one document, by ordinal."""
        ...
