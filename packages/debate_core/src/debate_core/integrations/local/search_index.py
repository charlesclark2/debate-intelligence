"""The student search pilot's index as one SQLite file with FTS5, by the standard library (`v1-e39-t02`).

:class:`SqliteSearchIndexWriter` is the :class:`~debate_core.application.ports.search_index.
SearchIndexWriter` the composition root wires. What goes in a row is decided by
:class:`~debate_core.application.search_index_build.SearchIndexBuildService`; this module only lays the
rows out, in the schema `docs/data/search-index.md` describes, and compresses the result.

## The schema

* `index_info`: the format version and the SQLite feature ceiling, as text, for a reader that opens
  the file without its manifest. `PRAGMA user_version` holds the format version too.
* `documents`: one row per card cluster, `doc_id` its rank in (caselist, cluster id) order. The
  representative's tag, cite, read-aloud text and evidence text, and the stored fields a page shows
  and filters by: event, caselist, camp, completeness, the formatting and font-size spans as JSON,
  the sides, first and last seen, the counts of files, teams and occurrences.
* `occurrences`: every surviving occurrence of every document, `ordinal` 0 the representative. The
  source SHA-256 and disclosure digest of each, and the provenance of the first few: for a camp
  occurrence, its camp release and, since format 3 (`v1-e39-t16`), its file's OpenEv id. **Nothing in
  this table is searchable.**
* `search`: an FTS5 table over `documents`' four searchable columns, `tag`, `cite`, `read_aloud` and
  `text`, as an external-content table, so the text is stored once. School, team code, tournament
  and round are in no FTS5 table and cannot be matched (the data-use policy's E39 gate item 8).

## The same rows give the same bytes

The rows may arrive in any order. Documents go in by `doc_id`, the occurrence table is keyed on
`(doc_id, ordinal)`, and the full-text index is built at the end by FTS5's `rebuild`, which reads
the content table in `doc_id` order, then merged into one b-tree by `optimize`. `VACUUM` then writes
every table out in key order into a file with no free pages. So the file depends on the rows and on
the SQLite library, and on nothing else. The gzip object is written with level 6, `mtime` 0 and no
file name in its header, so it depends on the file and on zlib.

## SQLite 3.40.0's features and no newer

The function's Lambda image runs SQLite 3.40.0 (ADR-0019 (c) 1), so every statement here uses only
what 3.40.0 has: plain tables, a `WITHOUT ROWID` table (in SQLite since 2013), FTS5 with an external
content table, the `porter` tokenizer in front of `unicode61` with `remove_diacritics 2` (3.27.0),
and the `rebuild` and `optimize` commands. No `STRICT` table, no JSON function, no
`contentless_delete`, no `locale`, no trigram tokenizer. :data:`WRITER_PRAGMAS` lists every pragma the
writer sets, and the tests trace every statement it runs against that list.
"""

from __future__ import annotations

import gzip
import json
import shutil
import sqlite3
from pathlib import Path
from typing import Final

from debate_core.application.ports.search_index import IndexedOccurrence, SearchDocument
from debate_core.domain.search_index import (
    SEARCH_INDEX_FORMAT_VERSION,
    SQLITE_FEATURE_CEILING,
    encode_font_size_spans,
    encode_formatting_spans,
)

__all__ = [
    "APPLICATION_ID",
    "FTS5_TOKENIZER",
    "GZIP_LEVEL",
    "SCHEMA_STATEMENTS",
    "SEARCHABLE_COLUMNS",
    "WRITER_PRAGMAS",
    "SqliteSearchIndexWriter",
]

APPLICATION_ID: Final = 0x54554253
"""`PRAGMA application_id`: `TUBS` in ASCII, so `file(1)` and a reader can tell this file from others."""

SEARCHABLE_COLUMNS: Final = ("tag", "cite", "read_aloud", "text")
"""The FTS5 table's columns, in order: the only text a query is matched against."""

FTS5_TOKENIZER: Final = "porter unicode61 remove_diacritics 2"
"""Case- and accent-folding word tokens, each stemmed: `growing`, `grows` and `grow` are one token.
`porter` is in FTS5 since FTS5 was added, in 2015; `remove_diacritics 2` since 3.27.0. Format 2
(`v1-e39-t13`); format 1 had `unicode61 remove_diacritics 2` alone."""

GZIP_LEVEL: Final = 6
"""The gzip object's compression level (ADR-0019 (c) 2)."""

_COPY_CHUNK: Final = 1024 * 1024

WRITER_PRAGMAS: Final = (
    "PRAGMA page_size = 4096",
    "PRAGMA journal_mode = OFF",
    "PRAGMA synchronous = OFF",
    f"PRAGMA application_id = {APPLICATION_ID}",
    f"PRAGMA user_version = {SEARCH_INDEX_FORMAT_VERSION}",
)
"""Every pragma the writer sets, in order. The page size is SQLite's default, stated so a library
built with another default writes the same file. No journal: a build that stops part-way leaves a
file the build service deletes, never one a reader opens."""

SCHEMA_STATEMENTS: Final = (
    """CREATE TABLE index_info (
  key TEXT PRIMARY KEY NOT NULL,
  value TEXT NOT NULL
)""",
    """CREATE TABLE documents (
  doc_id INTEGER PRIMARY KEY,
  caselist TEXT NOT NULL,
  cluster_id TEXT NOT NULL,
  event TEXT NOT NULL,
  camp TEXT,
  tag TEXT,
  cite TEXT NOT NULL,
  short_cite TEXT,
  read_aloud TEXT NOT NULL,
  text TEXT NOT NULL,
  completeness TEXT NOT NULL,
  formatting_spans TEXT NOT NULL,
  font_size_spans TEXT NOT NULL,
  sides TEXT NOT NULL,
  first_seen TEXT,
  last_seen TEXT,
  file_count INTEGER NOT NULL,
  team_count INTEGER NOT NULL,
  occurrence_count INTEGER NOT NULL,
  UNIQUE (caselist, cluster_id)
)""",
    """CREATE TABLE occurrences (
  doc_id INTEGER NOT NULL REFERENCES documents (doc_id),
  ordinal INTEGER NOT NULL,
  caselist TEXT NOT NULL,
  source_sha256 TEXT NOT NULL,
  disclosure TEXT,
  first_element_index INTEGER NOT NULL,
  last_element_index INTEGER NOT NULL,
  snapshot TEXT NOT NULL,
  last_snapshot TEXT NOT NULL,
  completeness TEXT NOT NULL,
  attributed INTEGER NOT NULL,
  provenance INTEGER NOT NULL,
  side TEXT,
  school TEXT,
  team_code TEXT,
  tournament TEXT,
  round TEXT,
  camp TEXT,
  camp_year INTEGER,
  camp_event TEXT,
  camp_file_title TEXT,
  openev_id INTEGER,
  PRIMARY KEY (doc_id, ordinal)
) WITHOUT ROWID""",
    "CREATE INDEX occurrences_by_source ON occurrences (source_sha256)",
    "CREATE VIRTUAL TABLE search USING fts5("
    + ", ".join(SEARCHABLE_COLUMNS)
    + f", content='documents', content_rowid='doc_id', tokenize='{FTS5_TOKENIZER}')",
)
"""The whole schema, as written. `docs/data/search-index.md` describes it column by column."""

_INSERT_DOCUMENT: Final = (
    "INSERT INTO documents (doc_id, caselist, cluster_id, event, camp, tag, cite, short_cite, read_aloud, "
    "text, completeness, formatting_spans, font_size_spans, sides, first_seen, last_seen, file_count, "
    "team_count, occurrence_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

_INSERT_OCCURRENCE: Final = (
    "INSERT INTO occurrences (doc_id, ordinal, caselist, source_sha256, disclosure, first_element_index, "
    "last_element_index, snapshot, last_snapshot, completeness, attributed, provenance, side, school, "
    "team_code, tournament, round, camp, camp_year, camp_event, camp_file_title, openev_id) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

_FINISH: Final = (
    "INSERT INTO search (search) VALUES ('rebuild')",
    "INSERT INTO search (search) VALUES ('optimize')",
)


def _occurrence_row(doc_id: int, one: IndexedOccurrence) -> tuple[object, ...]:
    return (
        doc_id,
        one.ordinal,
        one.caselist,
        one.source_sha256,
        one.disclosure,
        one.first_element_index,
        one.last_element_index,
        one.snapshot,
        one.last_snapshot,
        one.completeness,
        int(one.attributed),
        int(one.provenance),
        one.side,
        one.school,
        one.team_code,
        one.tournament,
        one.round,
        one.camp,
        one.camp_year,
        one.camp_event,
        one.camp_file_title,
        one.openev_id,
    )


class _SqliteSink:
    """One index file being written: rows in any order, the full-text index built at the end."""

    def __init__(self, destination: Path) -> None:
        if destination.exists():
            raise FileExistsError(f"an index is already at {destination.name}")
        self._connection = sqlite3.connect(destination, isolation_level=None)
        for statement in (*WRITER_PRAGMAS, "BEGIN", *SCHEMA_STATEMENTS):
            self._connection.execute(statement)
        self._connection.executemany(
            "INSERT INTO index_info (key, value) VALUES (?, ?)",
            (
                ("format_version", str(SEARCH_INDEX_FORMAT_VERSION)),
                ("sqlite_feature_ceiling", SQLITE_FEATURE_CEILING),
            ),
        )

    def add(self, document: SearchDocument) -> None:
        self._connection.execute(
            _INSERT_DOCUMENT,
            (
                document.doc_id,
                document.caselist,
                document.cluster_id,
                document.event,
                document.camp,
                document.tag,
                document.cite,
                document.short_cite,
                document.read_aloud,
                document.text,
                document.completeness,
                encode_formatting_spans(document.formatting_spans),
                encode_font_size_spans(document.font_size_spans),
                json.dumps(list(document.sides), separators=(",", ":")),
                document.first_seen,
                document.last_seen,
                document.file_count,
                document.team_count,
                len(document.occurrences),
            ),
        )
        self._connection.executemany(
            _INSERT_OCCURRENCE, (_occurrence_row(document.doc_id, one) for one in document.occurrences)
        )

    def finish(self) -> None:
        try:
            for statement in (*_FINISH, "COMMIT", "VACUUM"):
                self._connection.execute(statement)
        finally:
            self._connection.close()

    def abandon(self) -> None:
        self._connection.close()


class SqliteSearchIndexWriter:
    """Writes the index with the `sqlite3` module this Python was built with."""

    @property
    def sqlite_version(self) -> str:
        return sqlite3.sqlite_version

    def create(self, destination: Path) -> _SqliteSink:
        return _SqliteSink(destination)

    def compress(self, source: Path, destination: Path) -> None:
        with (
            source.open("rb") as raw,
            destination.open("xb") as out,
            gzip.GzipFile(filename="", mode="wb", compresslevel=GZIP_LEVEL, fileobj=out, mtime=0) as zipped,
        ):
            shutil.copyfileobj(raw, zipped, _COPY_CHUNK)
