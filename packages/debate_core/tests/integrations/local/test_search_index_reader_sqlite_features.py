"""The search reader: safe on any query, SQLite 3.40.0's features only, read-only (`v1-e39-t03`).

* **ac1, in every run** (`test_search_index_reader_never_raises_a_syntax_error_on_any_query`): arbitrary
  strings, and strings built from FTS5's own operators, quotes, `NEAR`, `*`, column filters and
  unbalanced parentheses, go through the real reader against a real FTS5 index, and none raises.
* **The 3.40.0 ceiling, in every run** (`test_search_index_reader_runs_only_statements_sqlite_3_40_has`):
  every statement the reader sends is traced, with its parameters as SQLite expands them, and must
  match one of the shapes this file writes out by hand, each a feature SQLite 3.40.0 has: the URI
  open's checks, FTS5 `MATCH` with a per-query `rank MATCH 'bm25(...)'`, `snippet()` and `instr()`,
  and since `v1-e39-t11` the result count's `MATCH` with a rowid range in rowid order.
  The time budget is the progress handler, which is a C API call and no statement; it is in SQLite
  since 3.0. The machine running this has a newer SQLite, so this checks what the reader asks for.
* **Marked slow** (`test_search_index_reader_statements_run_in_the_lambda_image_sqlite`): the traced
  statements are replayed by the SQLite inside the function's base image, 3.40.0, with no network,
  and must give the same rows; a progress handler there must stop a statement. It skips when Docker
  or the image is not on the machine, and never pulls one.

The documents are invented (data-use policy, rule 5).
"""

from __future__ import annotations

import gzip
import json
import re
import shutil
import sqlite3
import subprocess
import tomllib
from collections.abc import Iterator
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any, Final

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from debate_core.application.evidence_search import EvidenceSearchService
from debate_core.application.ports.search_index import IndexedOccurrence, SearchDocument
from debate_core.application.ports.search_index_reader import MatchRequest, UnreadableSearchIndex
from debate_core.domain.caselist import Event, Side
from debate_core.domain.evidence_search import SearchFilters, parse_query
from debate_core.integrations.local.search_index import SqliteSearchIndexWriter
from debate_core.integrations.local.search_index_reader import SqliteSearchIndexReader

REPO_ROOT: Final = Path(__file__).resolve().parents[5]
INDEX_ID: Final = "0123456789abcdef"

_LITERAL: Final = r"(?:'(?:[^']|'')*'|NULL|-?[0-9]+(?:\.[0-9]+)?)"

#: Every statement the reader may send, written by hand with `{}` where SQLite's expanded trace puts a
#: bound value. Never read from the reader: a statement changed there fails here until changed here.
ALLOWED_STATEMENTS: Final = (
    "PRAGMA application_id",
    "PRAGMA user_version",
    "SELECT d.doc_id, d.caselist, d.cluster_id, d.event, d.camp, d.tag, d.short_cite, "
    "snippet(search, 3, {}, {}, {}, {}), d.file_count, d.team_count, "
    "o.doc_id, o.ordinal, o.caselist, o.source_sha256, o.disclosure, o.snapshot, o.last_snapshot, "
    "o.completeness, o.attributed, o.provenance, o.side, o.school, o.team_code, o.tournament, o.round, "
    "o.camp, o.camp_year, o.camp_event, o.camp_file_title "
    "FROM search JOIN documents AS d ON d.doc_id = search.rowid "
    "JOIN occurrences AS o ON o.doc_id = d.doc_id AND o.ordinal = 0 "
    "WHERE search MATCH {} AND rank MATCH {} "
    "AND ({} IS NULL OR d.event = {}) AND ({} IS NULL OR d.caselist = {}) AND ({} IS NULL OR d.camp = {}) "
    "AND ({} IS NULL OR instr(d.sides, {}) > 0) AND ({} IS NULL OR d.first_seen >= {}) "
    "ORDER BY rank LIMIT {} OFFSET {}",
    "SELECT d.doc_id, o.source_sha256, o.disclosure "
    "FROM search JOIN documents AS d ON d.doc_id = search.rowid "
    "JOIN occurrences AS o ON o.doc_id = d.doc_id AND o.ordinal = 0 "
    "WHERE search MATCH {} AND search.rowid > {} "
    "AND ({} IS NULL OR d.event = {}) AND ({} IS NULL OR d.caselist = {}) AND ({} IS NULL OR d.camp = {}) "
    "AND ({} IS NULL OR instr(d.sides, {}) > 0) AND ({} IS NULL OR d.first_seen >= {}) "
    "ORDER BY search.rowid LIMIT {}",
    "SELECT doc_id, caselist, cluster_id, event, camp, tag, cite, short_cite, read_aloud, text, "
    "completeness, formatting_spans, font_size_spans, sides, first_seen, last_seen, file_count, "
    "team_count FROM documents WHERE caselist = {} AND cluster_id = {}",
    "SELECT doc_id, ordinal, caselist, source_sha256, disclosure, snapshot, last_snapshot, completeness, "
    "attributed, provenance, side, school, team_code, tournament, round, camp, camp_year, camp_event, "
    "camp_file_title, first_element_index, last_element_index FROM occurrences WHERE doc_id = {} "
    "ORDER BY ordinal",
    # v1-e39-t13: a passage's ranking and its count, each kept to the documents sharing enough words.
    "WITH RECURSIVE words (word, rest) AS (SELECT NULL, {} UNION ALL "
    "SELECT substr(rest, 1, instr(rest, {}) - 1), substr(rest, instr(rest, {}) + 1) FROM words "
    "WHERE rest <> ''), shared (doc_id) AS (SELECT search.rowid FROM words JOIN search "
    "ON search MATCH words.word WHERE words.word IS NOT NULL GROUP BY search.rowid HAVING count(*) >= {}) "
    "SELECT d.doc_id, d.caselist, d.cluster_id, d.event, d.camp, d.tag, d.short_cite, "
    "snippet(search, 3, {}, {}, {}, {}), d.file_count, d.team_count, "
    "o.doc_id, o.ordinal, o.caselist, o.source_sha256, o.disclosure, o.snapshot, o.last_snapshot, "
    "o.completeness, o.attributed, o.provenance, o.side, o.school, o.team_code, o.tournament, o.round, "
    "o.camp, o.camp_year, o.camp_event, o.camp_file_title "
    "FROM search JOIN documents AS d ON d.doc_id = search.rowid "
    "JOIN occurrences AS o ON o.doc_id = d.doc_id AND o.ordinal = 0 "
    "WHERE search MATCH {} AND rank MATCH {} AND +d.doc_id IN shared "
    "AND ({} IS NULL OR d.event = {}) AND ({} IS NULL OR d.caselist = {}) AND ({} IS NULL OR d.camp = {}) "
    "AND ({} IS NULL OR instr(d.sides, {}) > 0) AND ({} IS NULL OR d.first_seen >= {}) "
    "ORDER BY rank LIMIT {} OFFSET {}",
    "WITH RECURSIVE words (word, rest) AS (SELECT NULL, {} UNION ALL "
    "SELECT substr(rest, 1, instr(rest, {}) - 1), substr(rest, instr(rest, {}) + 1) FROM words "
    "WHERE rest <> ''), shared (doc_id) AS (SELECT search.rowid FROM words JOIN search "
    "ON search MATCH words.word WHERE words.word IS NOT NULL GROUP BY search.rowid HAVING count(*) >= {}) "
    "SELECT d.doc_id, o.source_sha256, o.disclosure "
    "FROM search JOIN documents AS d ON d.doc_id = search.rowid "
    "JOIN occurrences AS o ON o.doc_id = d.doc_id AND o.ordinal = 0 "
    "WHERE search MATCH {} AND search.rowid > {} AND +d.doc_id IN shared "
    "AND ({} IS NULL OR d.event = {}) AND ({} IS NULL OR d.caselist = {}) AND ({} IS NULL OR d.camp = {}) "
    "AND ({} IS NULL OR instr(d.sides, {}) > 0) AND ({} IS NULL OR d.first_seen >= {}) "
    "ORDER BY search.rowid LIMIT {}",
)

#: What FTS5 itself prepares outside a statement's step, so SQLite traces it unnested: its config read
#: when the reader's first `MATCH` connects the table. Every other FTS5 statement is traced nested
#: (`-- ...`) inside the reader's own and left out, as `v1-e39-t02`'s writer check leaves them out.
FTS5_OWN_STATEMENTS: Final = ("SELECT k, v FROM 'main'.'search_config'",)

#: Words for SQLite features newer than 3.40.0, or that a read-only reader has no business using.
NEWER_OR_FORBIDDEN: Final = (
    "json",
    "unixepoch",
    "STRICT",
    "RETURNING",
    "INSERT",
    "UPDATE",
    "DELETE",
    "CREATE",
    "DROP",
    "ATTACH",
    "trigram",
    "locale",
)


def _shape(statement: str) -> re.Pattern[str]:
    return re.compile("^" + re.escape(statement).replace(r"\{\}", _LITERAL) + "$", re.DOTALL)


def documents() -> Iterator[SearchDocument]:
    for doc_id in range(1, 31):
        camp = doc_id % 5 == 0
        yield SearchDocument(
            doc_id=doc_id,
            caselist="openev" if camp else "hsld26",
            cluster_id=f"{doc_id:064x}",
            event="POLICY" if camp else "LD",
            camp="Cascade Institute" if camp else None,
            tag=f"Invented growth claim {doc_id}" if doc_id % 2 else "Invented recession claim",
            cite=f"Okonkwo {doc_id}, Invented Journal" if doc_id % 3 else "Lindqvist 26, Invented Quarterly",
            short_cite="Okonkwo 26",
            read_aloud="growth always",
            text=(
                f"Invented growth always ends badly near the {'recession' if doc_id % 4 else 'boom'}, "
                f"case {doc_id}"
            ),
            completeness="FULL",
            formatting_spans=(),
            font_size_spans=(),
            sides=() if camp else (("AFF",) if doc_id % 2 else ("NEG",)),
            first_seen=None if camp else f"2026-09-{doc_id:02d}",
            last_seen=None if camp else f"2026-09-{doc_id:02d}",
            file_count=1,
            team_count=1,
            occurrences=(
                IndexedOccurrence(
                    ordinal=0,
                    caselist="openev" if camp else "hsld26",
                    source_sha256=f"{doc_id}".rjust(64, "a"),
                    disclosure=None if camp else "b" * 64,
                    first_element_index=0,
                    last_element_index=2,
                    snapshot="2026-policy" if camp else "2026-09-01",
                    last_snapshot="2026-policy" if camp else "2026-09-08",
                    completeness="FULL",
                    attributed=True,
                    provenance=True,
                    side=None if camp else "NEG",
                    school=None if camp else "Maple Grove",
                    team_code=None if camp else "QX",
                    camp="Cascade Institute" if camp else None,
                    camp_year=2026 if camp else None,
                    camp_event="POLICY" if camp else None,
                    camp_file_title="Invented Adv CP" if camp else None,
                ),
            ),
        )


def write(path: Path) -> Path:
    sink = SqliteSearchIndexWriter().create(path)
    for document in documents():
        sink.add(document)
    sink.finish()
    return path


@pytest.fixture(scope="module")
def index_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return write(tmp_path_factory.mktemp("reader") / "search-index.sqlite")


#: The core queries: what the slow test replays in the Lambda image. Each a different path through
#: the parser and the filters.
CORE_QUERIES: Final = (
    ("growth", SearchFilters()),
    ('"growth always" -boom', SearchFilters()),
    ("tag:recession author:lindqvist", SearchFilters()),
    ("growth", SearchFilters(event=Event.LD, side=Side.AFF, first_seen_on_or_after=date(2026, 9, 10))),
    ("growth", SearchFilters(caselist="openev", camp="Cascade Institute")),
    ('NEAR(growth "badly) * ^ AND OR', SearchFilters()),
    ("grow* tag:recess*", SearchFilters()),
)

#: Passages, after the core queries: each a path through the passage statements (`v1-e39-t13`).
PASSAGE_QUERIES: Final = (
    ("Invented growth always ends badly, near the boom", SearchFilters()),
    ("growth ends near the recession, case 7", SearchFilters(event=Event.LD, side=Side.AFF)),
)


def run_core_queries(path: Path) -> list[Any]:
    """Every core query's first page, and one card with its occurrences, as plain values."""
    searched = EvidenceSearchService(SqliteSearchIndexReader(path, index_id=INDEX_ID), page_size=5)
    results: list[Any] = []
    for query, filters, passage in [
        *((query, filters, False) for query, filters in CORE_QUERIES),
        *((query, filters, True) for query, filters in PASSAGE_QUERIES),
    ]:
        page = searched.search(query, filters, passage=passage)
        results.append(
            [[hit.cluster_id, hit.provenance_line, [s.text for s in hit.snippet]] for hit in page.hits]
        )
        results.append([page.count.matches if page.count else None, [str(one) for one in page.notices]])
    card = searched.card("hsld26", f"{1:064x}")
    assert card is not None
    results.append([card.cite, [one.provenance_line for one in card.occurrences]])
    return results


def traced_statements(path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[list[str], list[Any]]:
    traced: list[str] = []
    connect = sqlite3.connect

    def tracing_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connection = connect(*args, **kwargs)
        connection.set_trace_callback(traced.append)
        return connection

    with monkeypatch.context() as patched:
        patched.setattr(sqlite3, "connect", tracing_connect)
        results = run_core_queries(path)
    return traced, results


def test_search_index_reader_runs_only_statements_sqlite_3_40_has(
    index_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    traced, _ = traced_statements(index_path, monkeypatch)
    sent = [
        statement
        for statement in traced
        if not statement.startswith("--") and statement not in FTS5_OWN_STATEMENTS
    ]
    shapes = [_shape(statement) for statement in ALLOWED_STATEMENTS]
    refused = [statement for statement in sent if not any(shape.match(statement) for shape in shapes)]
    assert sent, "the trace saw the reader's statements"
    assert refused == []
    used = {index for statement in sent for index, shape in enumerate(shapes) if shape.match(statement)}
    assert used == set(range(len(ALLOWED_STATEMENTS))), "every allowed statement was exercised"
    syntax = [re.sub(_LITERAL, "?", statement) for statement in sent]
    assert [word for word in NEWER_OR_FORBIDDEN if any(word.lower() in one.lower() for one in syntax)] == []


def test_search_index_reader_plan_ranks_inside_fts5_and_joins_by_key(index_path: Path) -> None:
    """The ranking is FTS5's own sort, and the joins are key lookups: no temporary sort, no scan."""
    with sqlite3.connect(index_path) as connection:
        plan = connection.execute(
            "EXPLAIN QUERY PLAN "
            + ALLOWED_STATEMENTS[2]
            .replace("{}", "NULL")
            .replace(
                "search MATCH NULL AND rank MATCH NULL",
                "search MATCH 'growth' AND rank MATCH 'bm25(8.0, 3.0, 2.0, 1.0)'",
            )
        ).fetchall()
    details = [row[3] for row in plan]
    assert details[0].startswith("SCAN search VIRTUAL TABLE INDEX"), details
    assert all("TEMP B-TREE" not in detail for detail in details), details
    assert any(detail.startswith("SEARCH d USING INTEGER PRIMARY KEY") for detail in details), details
    assert any(detail.startswith("SEARCH o USING PRIMARY KEY") for detail in details), details


_PASSAGE_WORDS: Final = (
    '\'"growth"\x1f"badly"\x1f"boom"\x1f\'',
    "'\x1f'",
    "'\x1f'",
    "2",
)


def _passage_plan(path: Path, statement: str) -> list[str]:
    """`EXPLAIN QUERY PLAN` of a passage statement, its words and filters bound as in a search."""
    for value in _PASSAGE_WORDS:
        statement = statement.replace("{}", value, 1)
    statement = (
        statement.replace("search MATCH {}", 'search MATCH \'"growth" OR "badly" OR "boom"\'', 1)
        .replace("rank MATCH {}", "rank MATCH 'bm25(10.0, 6.0, 3.0, 1.0)'", 1)
        .replace("search.rowid > {}", "search.rowid > 0", 1)
        .replace("{}", "NULL")
    )
    with sqlite3.connect(path) as connection:
        return [row[3] for row in connection.execute("EXPLAIN QUERY PLAN " + statement).fetchall()]


def test_search_index_reader_passage_lets_fts5_sort_and_filters_after(index_path: Path) -> None:
    """The passage's ranking is FTS5's own sort over the OR, kept to `shared` afterwards: no temporary
    sort of the results, and FTS5 is not driven one candidate rowid at a time (`v1-e39-t13`)."""
    details = _passage_plan(index_path, ALLOWED_STATEMENTS[6])
    assert details[0].startswith("SCAN search VIRTUAL TABLE INDEX"), details
    assert ":=" not in details[0] and "=r" not in details[0], "no rowid lookup into FTS5"
    assert all("TEMP B-TREE FOR ORDER BY" not in detail for detail in details), details
    assert any(detail.startswith("SEARCH d USING INTEGER PRIMARY KEY") for detail in details), details
    count = _passage_plan(index_path, ALLOWED_STATEMENTS[7])
    assert count[0].startswith("SCAN search VIRTUAL TABLE INDEX"), count
    assert all("TEMP B-TREE FOR ORDER BY" not in detail for detail in count), count


def test_search_index_reader_count_walks_fts5_in_rowid_order_and_joins_by_key(index_path: Path) -> None:
    """The count asks for no rank, so FTS5 neither scores nor sorts: no temporary sort (`v1-e39-t11`)."""
    with sqlite3.connect(index_path) as connection:
        plan = connection.execute(
            "EXPLAIN QUERY PLAN "
            + ALLOWED_STATEMENTS[3]
            .replace("{}", "NULL")
            .replace(
                "search MATCH NULL AND search.rowid > NULL", "search MATCH 'growth' AND search.rowid > 0"
            )
        ).fetchall()
    details = [row[3] for row in plan]
    assert details[0].startswith("SCAN search VIRTUAL TABLE INDEX"), details
    assert all("TEMP B-TREE" not in detail for detail in details), details
    assert any(detail.startswith("SEARCH d USING INTEGER PRIMARY KEY") for detail in details), details
    assert any(detail.startswith("SEARCH o USING PRIMARY KEY") for detail in details), details


QUERY_PIECES: Final = st.sampled_from(
    [
        "AND",
        "OR",
        "NOT",
        "NEAR",
        "NEAR(",
        "NEAR/2",
        "*",
        "^",
        "(",
        ")",
        '"',
        '""',
        ":",
        "{",
        "}",
        "-",
        "+",
        "tag:",
        "author:",
        "cite:",
        "text:",
        "read_aloud:",
        "{tag cite}:",
        "search:",
        "rank:",
        "rowid:",
        "\x00",
        "'",
        ",",
        "growth",
        "recession",
        "Okonkwo",
        "\U0001f600",
        "́",
        "é",
    ]
)
QUERIES: Final = st.one_of(
    st.text(max_size=80),
    st.lists(st.one_of(QUERY_PIECES, st.text(max_size=6)), max_size=14).map(" ".join),
    st.lists(st.one_of(QUERY_PIECES, st.text(max_size=4)), max_size=14).map("".join),
)


@settings(max_examples=500, deadline=None)
@given(QUERIES)
def test_search_index_reader_never_raises_a_syntax_error_on_any_query(index_path: Path, raw: str) -> None:
    """ac1: whatever a student types, the real FTS5 index answers it, maybe with nothing."""
    searched = EvidenceSearchService(SqliteSearchIndexReader(index_path, index_id=INDEX_ID))
    page = searched.search(raw)
    assert len(page.hits) <= 20
    assert len(searched.search(raw, passage=True).hits) <= 20
    expression = parse_query(raw).fts5_expression()
    if expression is not None:
        with sqlite3.connect(index_path) as connection:
            connection.execute("SELECT count(*) FROM search WHERE search MATCH ?", (expression,)).fetchone()


def test_search_index_reader_refuses_a_file_that_is_not_this_index(tmp_path: Path, index_path: Path) -> None:
    text = tmp_path / "not-sqlite.sqlite"
    text.write_bytes(b"not a database at all, just some bytes" * 200)
    with pytest.raises(UnreadableSearchIndex):
        SqliteSearchIndexReader(text, index_id=INDEX_ID)
    other = tmp_path / "other.sqlite"
    with sqlite3.connect(other) as connection:
        connection.execute("CREATE TABLE anything (x)")
    with pytest.raises(UnreadableSearchIndex, match="application id"):
        SqliteSearchIndexReader(other, index_id=INDEX_ID)
    newer = tmp_path / "newer.sqlite"
    shutil.copy(index_path, newer)
    with sqlite3.connect(newer) as connection:
        connection.execute("PRAGMA user_version = 3")
    with pytest.raises(UnreadableSearchIndex, match="format version 3; this build reads 1 and 2"):
        SqliteSearchIndexReader(newer, index_id=INDEX_ID)


def test_search_index_reader_stopped_by_the_budget_is_interrupted_and_not_exhausted(index_path: Path) -> None:
    """A stopped statement keeps the rows it fetched, and says the ranking may go on past them."""
    with SqliteSearchIndexReader(index_path, index_id=INDEX_ID) as reader:
        request = MatchRequest(
            expression='"invented"',
            rank="bm25(10.0, 6.0, 3.0, 1.0)",
            filters=SearchFilters(),
            offset=0,
            limit=100,
            expired=lambda: True,
        )
        stopped = reader.match(request)
        whole = reader.match(replace(request, expired=lambda: False))
    assert stopped.interrupted
    assert not stopped.exhausted
    assert len(stopped.hits) < len(whole.hits) == 30
    assert [hit.doc_id for hit in stopped.hits] == [hit.doc_id for hit in whole.hits][: len(stopped.hits)]
    assert whole.exhausted and not whole.interrupted


def test_search_index_reader_opens_read_only(index_path: Path) -> None:
    with (
        SqliteSearchIndexReader(index_path, index_id=INDEX_ID) as reader,
        pytest.raises(sqlite3.OperationalError, match="readonly"),
    ):
        reader._connection.execute("DELETE FROM documents")  # pyright: ignore[reportPrivateUsage]


# ------------------------------------------------------------------------------------------------
# Marked slow: the traced statements in the Lambda image's SQLite
# ------------------------------------------------------------------------------------------------


def _lambda_image() -> str:
    """The base image `scripts/tub_deploy.sh` builds from: the one Python `requires-python` allows."""
    declared = tomllib.loads((REPO_ROOT / "packages" / "debate_core" / "pyproject.toml").read_text())
    match = re.fullmatch(r">=(\d+\.\d+),<\d+\.\d+", declared["project"]["requires-python"])
    assert match is not None
    return f"public.ecr.aws/lambda/python:{match.group(1)}"


_REPLAY_IN_THE_IMAGE: Final = """
import json
import sqlite3
connection = sqlite3.connect("file:/index/index.sqlite?mode=ro&immutable=1", uri=True)
statements = json.load(open("/index/statements.json", encoding="utf-8"))
rows = [[list(row) for row in connection.execute(statement).fetchall()] for statement in statements]
plan = [row[3] for row in connection.execute("EXPLAIN QUERY PLAN " + statements[2]).fetchall()]
connection.set_progress_handler(lambda: 1, 10)
try:
    connection.execute(statements[2]).fetchall()
    stopped = "no"
except sqlite3.OperationalError as error:
    stopped = str(error)
connection.set_progress_handler(None, 0)
print(json.dumps({"sqlite": sqlite3.sqlite_version, "rows": rows, "plan": plan, "stopped": stopped}))
"""


@pytest.mark.slow
def test_search_index_reader_statements_run_in_the_lambda_image_sqlite(
    tmp_path: Path, index_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker is not installed on this machine")
    image = _lambda_image()
    present = subprocess.run(
        [docker, "image", "inspect", image], capture_output=True, check=False, timeout=30
    )
    if present.returncode != 0:
        pytest.skip(f"{image} is not on this machine; `scripts/tub_deploy.sh dev --dry-run` pulls it")
    traced, _ = traced_statements(index_path, monkeypatch)
    statements = [
        one for one in traced if one.startswith(("SELECT d.doc_id", "SELECT doc_id", "WITH RECURSIVE words"))
    ]
    with sqlite3.connect(f"{index_path.resolve().as_uri()}?mode=ro&immutable=1", uri=True) as local:
        expected = [[list(row) for row in local.execute(statement).fetchall()] for statement in statements]
    mounted = tmp_path / "mounted"
    mounted.mkdir()
    # The function opens the decompressed object, so the replay opens what the gzip round trip gives.
    (mounted / "index.sqlite").write_bytes(gzip.decompress(gzip.compress(index_path.read_bytes())))
    (mounted / "statements.json").write_text(json.dumps(statements), encoding="utf-8")
    (mounted / "replay.py").write_text(_REPLAY_IN_THE_IMAGE, encoding="utf-8")
    run = subprocess.run(
        [
            docker,
            "run",
            "--rm",
            "--pull",
            "never",
            "--network",
            "none",
            "--platform",
            "linux/arm64",
            "--entrypoint",
            "python3",
            "-v",
            f"{mounted}:/index:ro",
            image,
            "/index/replay.py",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    assert run.returncode == 0, run.stderr
    replayed = json.loads(run.stdout)
    assert replayed["sqlite"] == "3.40.0"
    assert replayed["rows"] == expected
    assert sum(len(rows) for rows in expected) > 20, "the core queries found something to compare"
    assert replayed["plan"][0].startswith("SCAN search VIRTUAL TABLE INDEX")
    assert all("TEMP B-TREE" not in detail for detail in replayed["plan"])
    assert replayed["stopped"] == "interrupted"
