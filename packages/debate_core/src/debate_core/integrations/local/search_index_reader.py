"""The student search pilot's index read with the standard library's `sqlite3`, read-only (`v1-e39-t03`).

:class:`SqliteSearchIndexReader` is the :class:`~debate_core.application.ports.search_index_reader.
SearchIndexReader` the function's composition root wires (`v1-e39-t06`). It opens one `v1-e39-t02`
index file read-only and immutable, refuses a file whose application id or format version it does not
know, and runs three statements and nothing else: :data:`MATCH_STATEMENT`, :data:`DOCUMENT_STATEMENT`
and :data:`OCCURRENCES_STATEMENT`. What they mean is decided by
:class:`~debate_core.application.evidence_search.EvidenceSearchService`; every value a student typed
reaches them as a bound parameter.

## SQLite 3.40.0's features and no newer

The function's Lambda image runs SQLite 3.40.0 (ADR-0019 (c) 1), so the reader uses only what that
version has: a read-only, immutable URI open (3.11.0), `PRAGMA application_id` and `user_version`
reads, FTS5's `MATCH`, its per-query `rank MATCH 'bm25(...)'` with column weights, `snippet()`, and
`instr()`. No JSON function: a document's sides are decoded in Python. The time budget is
`sqlite3_progress_handler`, in SQLite since 3.0: the handler asks the search whether its budget is
spent every :data:`PROGRESS_INSTRUCTIONS` virtual-machine instructions and stops the statement when it
is. :data:`READER_STATEMENTS` lists every statement the reader sends; a test in every run traces the
reader against a hand-written list of their shapes, and a slow test replays the traced statements in
the Lambda image's own SQLite.

## Nothing to match a person by

The statements match words against the FTS5 table `search` alone, whose columns are the tag, cite,
read-aloud text and text. The `occurrences` table, where school, team code, tournament and round are,
is read only by a document's id, never by a value a student gave.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Final, Self, cast

from debate_core.application.ports.search_index_reader import (
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
)
from debate_core.domain.search_index import (
    SEARCH_INDEX_FORMAT_VERSION,
    decode_font_size_spans,
    decode_formatting_spans,
)
from debate_core.integrations.local.search_index import APPLICATION_ID

__all__ = [
    "DOCUMENT_STATEMENT",
    "MATCH_STATEMENT",
    "OCCURRENCES_STATEMENT",
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

MATCH_STATEMENT: Final = (
    "SELECT d.doc_id, d.caselist, d.cluster_id, d.event, d.camp, d.tag, d.short_cite, "
    "snippet(search, 3, :open, :close, :ellipsis, :tokens), d.file_count, d.team_count, "
    + ", ".join(f"o.{column}" for column in _OCCURRENCE_COLUMNS)
    + " FROM search"
    " JOIN documents AS d ON d.doc_id = search.rowid"
    " JOIN occurrences AS o ON o.doc_id = d.doc_id AND o.ordinal = 0"
    " WHERE search MATCH :expression AND rank MATCH :rank"
    " AND (:event IS NULL OR d.event = :event)"
    " AND (:caselist IS NULL OR d.caselist = :caselist)"
    " AND (:camp IS NULL OR d.camp = :camp)"
    " AND (:side IS NULL OR instr(d.sides, :side) > 0)"
    " AND (:first_seen IS NULL OR d.first_seen >= :first_seen)"
    " ORDER BY rank LIMIT :limit OFFSET :offset"
)
"""One window of a query's ranking, best first: the documents, their snippets and representatives.

Every filter is a parameter that is either `NULL` (no filter) or the value, so the statement is one
shape whatever is asked. A side is matched in `sides`, a JSON array of quoted side names, by `instr`
of the quoted name: the names are a closed set, none inside another. A camp document's `first_seen`
is `NULL`, which no date is on or after."""

DOCUMENT_STATEMENT: Final = (
    "SELECT doc_id, caselist, cluster_id, event, camp, tag, cite, short_cite, read_aloud, text, "
    "completeness, formatting_spans, font_size_spans, sides, first_seen, last_seen, file_count, "
    "team_count FROM documents WHERE caselist = ? AND cluster_id = ?"
)
"""One cluster's document, by the `(caselist, cluster_id)` key the index holds unique."""

OCCURRENCES_STATEMENT: Final = (
    "SELECT " + ", ".join(_OCCURRENCE_COLUMNS) + " FROM occurrences WHERE doc_id = ? ORDER BY ordinal"
)
"""Every occurrence of one document, by its primary key."""

_OPEN_CHECKS: Final = ("PRAGMA application_id", "PRAGMA user_version")

READER_STATEMENTS: Final = (*_OPEN_CHECKS, MATCH_STATEMENT, DOCUMENT_STATEMENT, OCCURRENCES_STATEMENT)
"""Every statement the reader sends."""


def _occurrence(row: tuple[Any, ...]) -> StoredOccurrence:
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
    ) = row
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
    )


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
        if format_version != SEARCH_INDEX_FORMAT_VERSION:
            self._connection.close()
            raise UnreadableSearchIndex(
                f"index format version {format_version}; this build reads {SEARCH_INDEX_FORMAT_VERSION}"
            )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    @property
    def index_id(self) -> str:
        return self._index_id

    def match(self, request: MatchRequest) -> MatchBatch:
        filters = request.filters
        parameters: dict[str, object] = {
            "open": SNIPPET_OPEN,
            "close": SNIPPET_CLOSE,
            "ellipsis": SNIPPET_ELLIPSIS,
            "tokens": SNIPPET_TOKENS,
            "expression": request.expression,
            "rank": request.rank,
            "event": filters.event.value if filters.event is not None else None,
            "caselist": filters.caselist,
            "camp": filters.camp,
            "side": f'"{filters.side.value}"' if filters.side is not None else None,
            "first_seen": (
                filters.first_seen_on_or_after.isoformat() if filters.first_seen_on_or_after else None
            ),
            "limit": request.limit,
            "offset": request.offset,
        }
        rows: list[tuple[Any, ...]] = []
        interrupted = False
        with self._lock:
            self._expired = False

            def progress() -> int:
                if request.expired():
                    self._expired = True
                    return 1
                return 0

            self._connection.set_progress_handler(progress, PROGRESS_INSTRUCTIONS)
            try:
                for row in self._connection.execute(MATCH_STATEMENT, parameters):
                    rows.append(row)
            except sqlite3.OperationalError:
                if not self._expired:
                    raise
                interrupted = True
            finally:
                self._connection.set_progress_handler(None, 0)
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
        return MatchBatch(hits=hits, exhausted=not interrupted and len(hits) < request.limit, interrupted=interrupted)

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
