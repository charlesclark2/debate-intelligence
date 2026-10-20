"""The search index uses no SQLite or FTS5 feature newer than 3.40.0, the Lambda image's (`v1-e39-t02` ac7).

Two checks, and the report names both:

* **In every run** (`test_search_index_writer_runs_only_statements_sqlite_3_40_has` and
  `test_search_index_file_is_the_schema_written_by_hand`): every statement the writer sends is traced
  and must be one of the statements this file lists, each a feature SQLite 3.40.0 has; and the file's
  schema and header are compared with a hand-written list. The machine running them has a newer SQLite
  (3.50.4 on the operator's Mac), so this is a check of what the writer asks for, not of what an old
  library accepts.
* **Marked slow** (`test_search_index_opens_in_the_lambda_image_sqlite`): a built index is opened by the
  SQLite inside the function's base image itself, which is 3.40.0, by `docker run` with no network. It
  runs `integrity_check`, FTS5's own `integrity-check`, and a `MATCH` with `bm25`, `highlight` and
  `snippet`. It skips when Docker or the image is not on the machine, and never pulls one.
"""

from __future__ import annotations

import gzip
import re
import shutil
import sqlite3
import subprocess
import tomllib
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Final

import pytest

from debate_core.application.ports.search_index import IndexedOccurrence, SearchDocument
from debate_core.domain.search_index import SEARCH_INDEX_FORMAT_VERSION
from debate_core.integrations.local.search_index import (
    APPLICATION_ID,
    SCHEMA_STATEMENTS,
    SqliteSearchIndexWriter,
)

REPO_ROOT: Final = Path(__file__).resolve().parents[5]

#: Every statement the writer may send, each a feature SQLite 3.40.0 has. Written by hand, never read
#: from the writer: a pragma or an option added there fails here until it is added here on purpose.
ALLOWED_STATEMENTS: Final = (
    r"PRAGMA page_size = 4096",
    r"PRAGMA journal_mode = OFF",
    r"PRAGMA synchronous = OFF",
    rf"PRAGMA application_id = {0x54554253}",
    rf"PRAGMA user_version = {SEARCH_INDEX_FORMAT_VERSION}",
    r"BEGIN",
    r"COMMIT",
    r"VACUUM",
    r"CREATE TABLE (index_info|documents) \((\n  [a-z_0-9]+ (TEXT|INTEGER)[A-Z ]*,)+\n  [^\n]+\n\)",
    r"CREATE TABLE occurrences \((\n  [a-z_0-9]+ (TEXT|INTEGER)[A-Z ()_a-z]*,)+"
    r"\n  PRIMARY KEY \(doc_id, ordinal\)\n\) WITHOUT ROWID",
    r"CREATE INDEX occurrences_by_source ON occurrences \(source_sha256\)",
    r"CREATE VIRTUAL TABLE search USING fts5\(tag, cite, read_aloud, text, content='documents', "
    r"content_rowid='doc_id', tokenize='unicode61 remove_diacritics 2'\)",
    r"INSERT INTO index_info \(key, value\) VALUES \(.*\)",
    r"INSERT INTO documents \(doc_id, .*\) VALUES \(.*\)",
    r"INSERT INTO occurrences \(doc_id, .*\) VALUES \(.*\)",
    r"INSERT INTO search \(search\) VALUES \('rebuild'\)",
    r"INSERT INTO search \(search\) VALUES \('optimize'\)",
)

#: Words for features SQLite added after 3.40.0, or that the index has no business using.
NEWER_FEATURES: Final = (
    "STRICT",
    "json",
    "GENERATED",
    "contentless_delete",
    "locale",
    "trigram",
    "unixepoch",
)

#: The FTS5 options the index's table is created with, each in FTS5 well before 3.40.0.
ALLOWED_FTS5_OPTIONS: Final = {
    "content='documents'",
    "content_rowid='doc_id'",
    "tokenize='unicode61 remove_diacritics 2'",
}

#: `sqlite_master` of a built index, written by hand from the schema in `docs/data/search-index.md`.
EXPECTED_SCHEMA: Final = [
    ("index", "occurrences_by_source", "occurrences"),
    ("index", "sqlite_autoindex_documents_1", "documents"),
    ("index", "sqlite_autoindex_index_info_1", "index_info"),
    ("table", "documents", "documents"),
    ("table", "index_info", "index_info"),
    ("table", "occurrences", "occurrences"),
    ("table", "search", "search"),
    ("table", "search_config", "search_config"),
    ("table", "search_data", "search_data"),
    ("table", "search_docsize", "search_docsize"),
    ("table", "search_idx", "search_idx"),
]


def documents() -> Iterator[SearchDocument]:
    for doc_id in (3, 1, 2):
        yield SearchDocument(
            doc_id=doc_id,
            caselist="hsld26",
            cluster_id=f"{doc_id:064x}",
            event="LD",
            camp=None,
            tag=f"Invented growth claim {doc_id}",
            cite="Okonkwo 26, Invented Journal",
            short_cite="Okonkwo 26",
            read_aloud="invented growth",
            text=f"Invented growth always ends badly, case {doc_id}",
            completeness="FULL",
            formatting_spans=(),
            font_size_spans=(),
            sides=("NEG",),
            first_seen="2026-09-01",
            last_seen="2026-09-08",
            file_count=1,
            team_count=1,
            occurrences=(
                IndexedOccurrence(
                    ordinal=0,
                    caselist="hsld26",
                    source_sha256=f"{doc_id}" * 64,
                    disclosure="a" * 64,
                    first_element_index=0,
                    last_element_index=2,
                    snapshot="2026-09-01",
                    last_snapshot="2026-09-08",
                    completeness="FULL",
                    attributed=True,
                    provenance=True,
                    side="NEG",
                    school="Maple Grove",
                    team_code="QX",
                ),
            ),
        )


def write(path: Path) -> Path:
    sink = SqliteSearchIndexWriter().create(path)
    for document in documents():
        sink.add(document)
    sink.finish()
    return path


def test_search_index_writer_runs_only_statements_sqlite_3_40_has(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    traced: list[str] = []
    connect = sqlite3.connect

    def tracing_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        connection = connect(*args, **kwargs)
        connection.set_trace_callback(traced.append)
        return connection

    monkeypatch.setattr(sqlite3, "connect", tracing_connect)
    write(tmp_path / "index.sqlite")

    sent = [statement for statement in traced if not statement.startswith("--")]
    allowed = [re.compile(rf"^{shape}$", re.DOTALL) for shape in ALLOWED_STATEMENTS]
    refused = [statement for statement in sent if not any(shape.match(statement) for shape in allowed)]
    assert sent, "the trace saw the writer's statements"
    assert refused == []
    assert [word for word in NEWER_FEATURES if any(word in statement for statement in sent)] == []
    assert any("fts5" in statement for statement in sent)


def test_search_index_fts5_table_takes_only_options_3_40_has() -> None:
    created = next(statement for statement in SCHEMA_STATEMENTS if "fts5(" in statement)
    arguments = created.split("fts5(", 1)[1].rstrip(")")
    options = {part.strip() for part in arguments.split(", ") if "=" in part}
    assert options == ALLOWED_FTS5_OPTIONS


def test_search_index_file_is_the_schema_written_by_hand(tmp_path: Path) -> None:
    path = write(tmp_path / "index.sqlite")
    with sqlite3.connect(path) as connection:
        schema = connection.execute(
            "SELECT type, name, tbl_name FROM sqlite_master ORDER BY type, name"
        ).fetchall()
        assert schema == EXPECTED_SCHEMA
        assert connection.execute("PRAGMA user_version").fetchone() == (SEARCH_INDEX_FORMAT_VERSION,)
        assert connection.execute("PRAGMA application_id").fetchone() == (APPLICATION_ID,)
        assert connection.execute("PRAGMA freelist_count").fetchone() == (0,)
    header = path.read_bytes()[:100]
    assert header[:16] == b"SQLite format 3\x00"
    assert int.from_bytes(header[16:18], "big") == 4096, "page size"
    assert (header[18], header[19]) == (1, 1), "rollback journal file format, never WAL"
    assert int.from_bytes(header[44:48], "big") == 4, "schema format 4, read by every SQLite since 3.3.0"
    assert int.from_bytes(header[56:60], "big") == 1, "UTF-8"


def _lambda_image() -> str:
    """The base image `scripts/tub_deploy.sh` builds from: the one Python `requires-python` allows."""
    declared = tomllib.loads((REPO_ROOT / "packages" / "debate_core" / "pyproject.toml").read_text())
    match = re.fullmatch(r">=(\d+\.\d+),<\d+\.\d+", declared["project"]["requires-python"])
    assert match is not None
    return f"public.ecr.aws/lambda/python:{match.group(1)}"


_CHECK_IN_THE_IMAGE: Final = """
import shutil
import sqlite3
connection = sqlite3.connect("file:/index/index.sqlite?mode=ro", uri=True)
print("sqlite", sqlite3.sqlite_version)
print("integrity", connection.execute("PRAGMA integrity_check").fetchone()[0])
shutil.copy("/index/index.sqlite", "/tmp/writable.sqlite")
with sqlite3.connect("/tmp/writable.sqlite") as writable:
    writable.execute("INSERT INTO search (search) VALUES ('integrity-check')")
print("fts5", "ok")
rows = connection.execute(
    "SELECT rowid, bm25(search, 4.0, 2.0, 2.0, 1.0), highlight(search, 3, '[', ']'), "
    "snippet(search, 3, '[', ']', '...', 4) FROM search WHERE search MATCH 'growth' ORDER BY rank"
).fetchall()
print("matches", len(rows), rows[0][2])
school = connection.execute("SELECT count(*) FROM search WHERE search MATCH '\\"Maple Grove\\"'")
print("school", school.fetchone()[0])
"""


@pytest.mark.slow
def test_search_index_opens_in_the_lambda_image_sqlite(tmp_path: Path) -> None:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker is not installed on this machine")
    image = _lambda_image()
    present = subprocess.run(
        [docker, "image", "inspect", image], capture_output=True, check=False, timeout=30
    )
    if present.returncode != 0:
        pytest.skip(f"{image} is not on this machine; `scripts/tub_deploy.sh dev --dry-run` pulls it")
    mounted = tmp_path / "mounted"
    mounted.mkdir()
    write(mounted / "index.sqlite")
    # The function opens the decompressed object, so the check opens what the gzip round trip gives.
    (mounted / "index.sqlite").write_bytes(
        gzip.decompress(gzip.compress((mounted / "index.sqlite").read_bytes()))
    )
    (mounted / "check.py").write_text(_CHECK_IN_THE_IMAGE, encoding="utf-8")
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
            "/index/check.py",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    assert run.returncode == 0, run.stderr
    lines = dict(line.split(" ", 1) for line in run.stdout.strip().splitlines())
    assert lines["sqlite"] == "3.40.0"
    assert lines["integrity"] == "ok"
    assert lines["fts5"] == "ok"
    assert lines["matches"].startswith("3 ")
    assert "[growth]" in lines["matches"]
    assert lines["school"] == "0"
