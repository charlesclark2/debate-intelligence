"""The student search pilot's index read with the standard library's `sqlite3`, read-only (`v1-e39-t03`).

:class:`SqliteSearchIndexReader` is the :class:`~debate_core.application.ports.search_index_reader.
SearchIndexReader` the function's composition root wires (`v1-e39-t06`). It opens one `v1-e39-t02`
index file read-only and immutable, refuses a file whose application id or format version it
does not read, and runs six statements and nothing else: :data:`MATCH_STATEMENT`,
:data:`COUNT_STATEMENT`, their passage forms :data:`PASSAGE_MATCH_STATEMENT` and
:data:`PASSAGE_COUNT_STATEMENT`, :data:`DOCUMENT_STATEMENT` and :data:`OCCURRENCES_STATEMENT`. What
they mean is decided by :class:`~debate_core.application.evidence_search.EvidenceSearchService`; every
value a student typed reaches them as a bound parameter.

## SQLite 3.40.0's features and no newer

The function's Lambda image runs SQLite 3.40.0 (ADR-0019 (c) 1), so the reader uses only what that
version has: a read-only, immutable URI open (`mode=ro&immutable=1`, years older than 3.40.0),
`PRAGMA application_id` and `user_version` reads, FTS5's `MATCH`, its per-query
`rank MATCH 'bm25(...)'` with column weights, `snippet()`, and `instr()`; for a passage, a recursive
common table expression (in SQLite since 2014) with `substr()`, `GROUP BY` and `HAVING`. No JSON function: a
document's sides are decoded in Python. The time budget is `sqlite3_progress_handler`, in SQLite
since 3.0: the handler asks the search whether its budget is
spent every :data:`PROGRESS_INSTRUCTIONS` virtual-machine instructions and stops the statement when it
is. :data:`READER_STATEMENTS` lists every statement the reader sends; a test in every run traces the
reader against a hand-written list of their shapes, and a slow test replays the traced statements in
the Lambda image's own SQLite.

## A passage: the documents holding enough of its words (`v1-e39-t13`)

A passage is an OR of its words, ranked by the same weighted BM25, kept to the documents that match
at least :attr:`~debate_core.application.ports.search_index_reader.MatchRequest.minimum_shared` of
them. FTS5 has no such operator, so :data:`_SHARED_WORDS` counts it: it splits the bound `:words`
(each word an FTS5 phrase the parser wrote, each ended by :data:`_PASSAGE_WORD_SEPARATOR`) into rows,
matches each against `search`, and keeps the doc ids found by enough of them. The ranked statement
then lets FTS5 sort every OR match itself and keeps those ids, with `+d.doc_id IN shared`: the `+`
stops SQLite from driving FTS5 one candidate rowid at a time, which recomputes BM25's statistics for
each candidate and took 1.2 s against 35 ms on the dev store's measurement index (the `v1-e39-t13`
session report has the plans and times). Two words with one stem (`grow`, `growing`) each count.

## Nothing to match a person by

The statements match words against the FTS5 table `search` alone, whose columns are the tag, cite,
read-aloud text and text. The `occurrences` table, where school, team code, tournament and round are,
is read only by a document's id, never by a value a student gave.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final, Self, cast

from debate_core.application.ports.search_index_reader import (
    CountBatch,
    CountedRepresentative,
    CountRequest,
    MatchBatch,
    MatchRequest,
    StoredDocument,
    StoredHit,
    StoredOccurrence,
    UnreadableSearchIndex,
)
from debate_core.domain.evidence_search import (
    SNIPPET_CLOSE,
    SNIPPET_ELLIPSIS,
    SNIPPET_OPEN,
    SNIPPET_TOKENS,
    SearchFilters,
)
from debate_core.domain.search_index import (
    READABLE_SEARCH_INDEX_FORMAT_VERSIONS,
    decode_font_size_spans,
    decode_formatting_spans,
)
from debate_core.integrations.local.search_index import APPLICATION_ID

__all__ = [
    "COUNT_STATEMENT",
    "DOCUMENT_STATEMENT",
    "MATCH_STATEMENT",
    "OCCURRENCES_STATEMENT",
    "PASSAGE_COUNT_STATEMENT",
    "PASSAGE_MATCH_STATEMENT",
    "PROGRESS_INSTRUCTIONS",
    "READER_STATEMENTS",
    "SqliteSearchIndexReader",
]

PROGRESS_INSTRUCTIONS: Final = 1000
"""How many SQLite virtual-machine instructions run between two looks at the time budget."""

_OCCURRENCE_COLUMNS: Final = (
    "doc_id",
    "ordinal",
    "caselist",
    "source_sha256",
    "disclosure",
    "snapshot",
    "last_snapshot",
    "completeness",
    "attributed",
    "provenance",
    "side",
    "school",
    "team_code",
    "tournament",
    "round",
    "camp",
    "camp_year",
    "camp_event",
    "camp_file_title",
)

_FILTERS: Final = (
    " AND (:event IS NULL OR d.event = :event)"
    " AND (:caselist IS NULL OR d.caselist = :caselist)"
    " AND (:camp IS NULL OR d.camp = :camp)"
    " AND (:side IS NULL OR instr(d.sides, :side) > 0)"
    " AND (:first_seen IS NULL OR d.first_seen >= :first_seen)"
)
"""The filters, written once for :data:`MATCH_STATEMENT` and :data:`COUNT_STATEMENT` alike, so a count
can never filter differently from the results it counts (`v1-e39-t11`)."""

_REPRESENTATIVE_JOIN: Final = (
    " FROM search"
    " JOIN documents AS d ON d.doc_id = search.rowid"
    " JOIN occurrences AS o ON o.doc_id = d.doc_id AND o.ordinal = 0"
)

_MATCH_COLUMNS: Final = (
    "SELECT d.doc_id, d.caselist, d.cluster_id, d.event, d.camp, d.tag, d.short_cite, "
    "snippet(search, 3, :open, :close, :ellipsis, :tokens), d.file_count, d.team_count, "
    + ", ".join(f"o.{column}" for column in _OCCURRENCE_COLUMNS)
)

MATCH_STATEMENT: Final = (
    _MATCH_COLUMNS
    + _REPRESENTATIVE_JOIN
    + " WHERE search MATCH :expression AND rank MATCH :rank"
    + _FILTERS
    + " ORDER BY rank LIMIT :limit OFFSET :offset"
)
"""One window of a query's ranking, best first: the documents, their snippets and representatives.

Every filter is a parameter that is either `NULL` (no filter) or the value, so the statement is one
shape whatever is asked. A side is matched in `sides`, a JSON array of quoted side names, by `instr`
of the quoted name: the names are a closed set, none inside another. A camp document's `first_seen`
is `NULL`, which no date is on or after."""

COUNT_STATEMENT: Final = (
    "SELECT d.doc_id, o.source_sha256, o.disclosure"
    + _REPRESENTATIVE_JOIN
    + " WHERE search MATCH :expression AND search.rowid > :after"
    + _FILTERS
    + " ORDER BY search.rowid LIMIT :limit"
)
"""One batch of the documents a query matches under its filters, by doc id: each one's id and its
representative's digests, which is all a count needs to ask the suppression list. No rank is asked
for, so FTS5 neither scores nor sorts: it walks its matches in rowid order and the statement stops
at the limit."""

_PASSAGE_WORD_SEPARATOR: Final = "\x1f"
"""What ends each of a passage's words in `:words`. The parser turns every control character a student
typed into a space, so no word holds one."""

_SHARED_WORDS: Final = (
    "WITH RECURSIVE words (word, rest) AS ("
    "SELECT NULL, :words"
    " UNION ALL "
    "SELECT substr(rest, 1, instr(rest, :separator) - 1), substr(rest, instr(rest, :separator) + 1)"
    " FROM words WHERE rest <> ''"
    "), shared (doc_id) AS ("
    "SELECT search.rowid FROM words JOIN search ON search MATCH words.word"
    " WHERE words.word IS NOT NULL GROUP BY search.rowid HAVING count(*) >= :minimum"
    ") "
)
"""The doc ids matched by at least `:minimum` of a passage's words, as the table `shared`."""

PASSAGE_MATCH_STATEMENT: Final = (
    _SHARED_WORDS
    + _MATCH_COLUMNS
    + _REPRESENTATIVE_JOIN
    + " WHERE search MATCH :expression AND rank MATCH :rank AND +d.doc_id IN shared"
    + _FILTERS
    + " ORDER BY rank LIMIT :limit OFFSET :offset"
)
"""One window of a passage's ranking: :data:`MATCH_STATEMENT` kept to the documents in `shared`."""

PASSAGE_COUNT_STATEMENT: Final = (
    _SHARED_WORDS
    + "SELECT d.doc_id, o.source_sha256, o.disclosure"
    + _REPRESENTATIVE_JOIN
    + " WHERE search MATCH :expression AND search.rowid > :after AND +d.doc_id IN shared"
    + _FILTERS
    + " ORDER BY search.rowid LIMIT :limit"
)
"""One batch of a passage's count: :data:`COUNT_STATEMENT` kept to the documents in `shared`."""

DOCUMENT_STATEMENT: Final = (
    "SELECT doc_id, caselist, cluster_id, event, camp, tag, cite, short_cite, read_aloud, text, "
    "completeness, formatting_spans, font_size_spans, sides, first_seen, last_seen, file_count, "
    "team_count FROM documents WHERE caselist = ? AND cluster_id = ?"
)
"""One cluster's document, by the `(caselist, cluster_id)` key the index holds unique."""

_LOCATION_COLUMNS: Final = ("first_element_index", "last_element_index")

OCCURRENCES_STATEMENT: Final = (
    "SELECT "
    + ", ".join((*_OCCURRENCE_COLUMNS, *_LOCATION_COLUMNS))
    + " FROM occurrences WHERE doc_id = ? ORDER BY ordinal"
)
"""Every occurrence of one document, by its primary key, with where each is in its source: what a
download reads its card from (`v1-e39-t08`). A search's rows leave the location out."""

_OPEN_CHECKS: Final = ("PRAGMA application_id", "PRAGMA user_version")

READER_STATEMENTS: Final = (
    *_OPEN_CHECKS,
    MATCH_STATEMENT,
    COUNT_STATEMENT,
    PASSAGE_MATCH_STATEMENT,
    PASSAGE_COUNT_STATEMENT,
    DOCUMENT_STATEMENT,
    OCCURRENCES_STATEMENT,
)
"""Every statement the reader sends."""


def _occurrence(row: tuple[Any, ...]) -> StoredOccurrence:
    """One occurrence from :data:`_OCCURRENCE_COLUMNS`, and its location when the row has
    :data:`_LOCATION_COLUMNS` after them."""
    location: tuple[Any, ...] = row[len(_OCCURRENCE_COLUMNS) :] or (None, None)
    first_element_index, last_element_index = location
    (
        doc_id,
        ordinal,
        caselist,
        source_sha256,
        disclosure,
        snapshot,
        last_snapshot,
        completeness,
        attributed,
        provenance,
        side,
        school,
        team_code,
        tournament,
        round_label,
        camp,
        camp_year,
        camp_event,
        camp_file_title,
    ) = row[: len(_OCCURRENCE_COLUMNS)]
    return StoredOccurrence(
        doc_id=doc_id,
        ordinal=ordinal,
        caselist=caselist,
        source_sha256=source_sha256,
        disclosure=disclosure,
        snapshot=snapshot,
        last_snapshot=last_snapshot,
        completeness=completeness,
        attributed=bool(attributed),
        provenance=bool(provenance),
        side=side,
        school=school,
        team_code=team_code,
        tournament=tournament,
        round_label=round_label,
        camp=camp,
        camp_year=camp_year,
        camp_event=camp_event,
        camp_file_title=camp_file_title,
        first_element_index=first_element_index,
        last_element_index=last_element_index,
    )


def _filter_parameters(filters: SearchFilters) -> dict[str, object]:
    """The filters' parameters of :data:`_FILTERS`: each `NULL`, or the value it narrows to."""
    return {
        "event": filters.event.value if filters.event is not None else None,
        "caselist": filters.caselist,
        "camp": filters.camp,
        "side": f'"{filters.side.value}"' if filters.side is not None else None,
        "first_seen": filters.first_seen_on_or_after.isoformat() if filters.first_seen_on_or_after else None,
    }


def _passage_parameters(words: tuple[str, ...], minimum: int) -> dict[str, object]:
    """:data:`_SHARED_WORDS`' parameters: the words, each ended by the separator, and the minimum."""
    if any(_PASSAGE_WORD_SEPARATOR in word for word in words):
        raise ValueError("a passage's word holds the separator, which the parser never writes")
    return {
        "words": "".join(word + _PASSAGE_WORD_SEPARATOR for word in words),
        "separator": _PASSAGE_WORD_SEPARATOR,
        "minimum": minimum,
    }


def _sides(stored: str) -> tuple[str, ...]:
    parsed: object = json.loads(stored)
    if not isinstance(parsed, list) or not all(isinstance(one, str) for one in cast(list[object], parsed)):
        raise UnreadableSearchIndex("a document's sides are a JSON array of side names")
    return tuple(cast(list[str], parsed))


class SqliteSearchIndexReader:
    """One index file, open read-only. Safe to share between threads: one statement runs at a time."""

    def __init__(self, path: Path, *, index_id: str) -> None:
        self._index_id = index_id
        self._lock = threading.Lock()
        self._expired = False
        uri = f"{path.resolve().as_uri()}?mode=ro&immutable=1"
        try:
            self._connection = sqlite3.connect(uri, uri=True, check_same_thread=False)
            application_id = self._connection.execute(_OPEN_CHECKS[0]).fetchone()[0]
            format_version = self._connection.execute(_OPEN_CHECKS[1]).fetchone()[0]
        except sqlite3.DatabaseError as error:
            raise UnreadableSearchIndex(f"not a readable SQLite file: {error}") from None
        if application_id != APPLICATION_ID:
            self._connection.close()
            raise UnreadableSearchIndex("not a search index: its application id is not TUBS")
        if format_version not in READABLE_SEARCH_INDEX_FORMAT_VERSIONS:
            self._connection.close()
            readable = " and ".join(str(one) for one in sorted(READABLE_SEARCH_INDEX_FORMAT_VERSIONS))
            raise UnreadableSearchIndex(f"index format version {format_version}; this build reads {readable}")
        self._format_version: int = format_version

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    @property
    def index_id(self) -> str:
        return self._index_id

    @property
    def format_version(self) -> int:
        return self._format_version

    def match(self, request: MatchRequest) -> MatchBatch:
        parameters: dict[str, object] = {
            "open": SNIPPET_OPEN,
            "close": SNIPPET_CLOSE,
            "ellipsis": SNIPPET_ELLIPSIS,
            "tokens": SNIPPET_TOKENS,
            "expression": request.expression,
            "rank": request.rank,
            **_filter_parameters(request.filters),
            "limit": request.limit,
            "offset": request.offset,
        }
        statement = MATCH_STATEMENT
        if request.passage_words:
            statement = PASSAGE_MATCH_STATEMENT
            parameters.update(_passage_parameters(request.passage_words, request.minimum_shared))
        rows, interrupted = self._run_under_budget(statement, parameters, request.expired)
        hits = tuple(
            StoredHit(
                position=request.offset + index,
                doc_id=row[0],
                caselist=row[1],
                cluster_id=row[2],
                event=row[3],
                camp=row[4],
                tag=row[5],
                short_cite=row[6],
                snippet=row[7] or "",
                file_count=row[8],
                team_count=row[9],
                representative=_occurrence(row[10:]),
            )
            for index, row in enumerate(rows)
        )
        return MatchBatch(
            hits=hits, exhausted=not interrupted and len(hits) < request.limit, interrupted=interrupted
        )

    def count(self, request: CountRequest) -> CountBatch:
        parameters: dict[str, object] = {
            "expression": request.expression,
            "after": request.after,
            **_filter_parameters(request.filters),
            "limit": request.limit,
        }
        statement = COUNT_STATEMENT
        if request.passage_words:
            statement = PASSAGE_COUNT_STATEMENT
            parameters.update(_passage_parameters(request.passage_words, request.minimum_shared))
        rows, interrupted = self._run_under_budget(statement, parameters, request.expired)
        counted = tuple(
            CountedRepresentative(doc_id=row[0], source_sha256=row[1], disclosure=row[2]) for row in rows
        )
        return CountBatch(
            rows=counted, exhausted=not interrupted and len(counted) < request.limit, interrupted=interrupted
        )

    def _run_under_budget(
        self, statement: str, parameters: dict[str, object], expired: Callable[[], bool]
    ) -> tuple[list[tuple[Any, ...]], bool]:
        """The rows `statement` gives, and whether the time budget stopped it before the last."""
        rows: list[tuple[Any, ...]] = []
        interrupted = False
        with self._lock:
            self._expired = False

            def progress() -> int:
                if expired():
                    self._expired = True
                    return 1
                return 0

            self._connection.set_progress_handler(progress, PROGRESS_INSTRUCTIONS)
            try:
                for row in self._connection.execute(statement, parameters):
                    rows.append(row)
            except sqlite3.OperationalError:
                if not self._expired:
                    raise
                interrupted = True
            finally:
                self._connection.set_progress_handler(None, 0)
        return rows, interrupted

    def document(self, caselist: str, cluster_id: str) -> StoredDocument | None:
        with self._lock:
            row = self._connection.execute(DOCUMENT_STATEMENT, (caselist, cluster_id)).fetchone()
        if row is None:
            return None
        return StoredDocument(
            doc_id=row[0],
            caselist=row[1],
            cluster_id=row[2],
            event=row[3],
            camp=row[4],
            tag=row[5],
            cite=row[6],
            short_cite=row[7],
            read_aloud=row[8],
            text=row[9],
            completeness=row[10],
            formatting_spans=decode_formatting_spans(row[11]),
            font_size_spans=decode_font_size_spans(row[12]),
            sides=_sides(row[13]),
            first_seen=row[14],
            last_seen=row[15],
            file_count=row[16],
            team_count=row[17],
        )

    def occurrences(self, doc_id: int) -> tuple[StoredOccurrence, ...]:
        with self._lock:
            rows = self._connection.execute(OCCURRENCES_STATEMENT, (doc_id,)).fetchall()
        return tuple(_occurrence(row) for row in rows)
