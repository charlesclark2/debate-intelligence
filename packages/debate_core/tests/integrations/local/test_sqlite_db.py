"""Opening a database creates or upgrades its schema, once, and refuses what it cannot read.

The adapter-specific half of the local persistence layer: the pragmas the repositories assume, the
migration runner's idempotence, and the four ways a migration set can be wrong. What the
repositories built on top of it do with the schema is `test_sqlite_repos.py`; what every
repository implementation must do regardless of technology is v1-e02-t04-repo-contract-tests.

Every database here is created under `tmp_path`.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from debate_core.integrations.local import sqlite_db
from debate_core.integrations.local.sqlite_db import (
    DATABASE_FILENAME,
    MINIMUM_SQLITE_VERSION,
    SCHEMA_VERSION_TABLE,
    Migration,
    MigrationError,
    SqliteDatabase,
    apply_migrations,
    build_migrations,
    load_migrations,
    pragma_values,
    read_schema_version,
)

EXPECTED_TABLES = {
    "articles",
    "cards",
    "search_results",
    "searches",
    "source_snapshots",
    SCHEMA_VERSION_TABLE,
}


def table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {str(row["name"]) for row in rows}


def index_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {str(row["name"]) for row in rows}


# --------------------------------------------------------------------------------------------
# Opening a database
# --------------------------------------------------------------------------------------------


def test_open_creates_the_data_directory_and_the_database_file(tmp_path: Path) -> None:
    data_dir = tmp_path / "environments" / "dev"

    with SqliteDatabase.open(data_dir) as database:
        assert database.path == data_dir / DATABASE_FILENAME
        assert database.path.is_file()


def test_open_applies_the_pragmas_the_repositories_assume(tmp_path: Path) -> None:
    with SqliteDatabase.open(tmp_path) as database:
        values = pragma_values(database.connection, ["journal_mode", "foreign_keys", "synchronous"])

    assert str(values["journal_mode"]).lower() == "wal"
    assert values["foreign_keys"] == 1
    assert values["synchronous"] == 2  # FULL


def test_the_schema_is_created_on_first_open(tmp_path: Path) -> None:
    with SqliteDatabase.open(tmp_path) as database:
        assert table_names(database.connection) == EXPECTED_TABLES
        assert database.schema_version() == load_migrations()[-1].version


def test_every_lookup_and_sort_key_is_indexed(tmp_path: Path) -> None:
    with SqliteDatabase.open(tmp_path) as database:
        assert index_names(database.connection) == {
            "articles_by_canonical_url",
            "articles_by_owner",
            "cards_by_article",
            "cards_by_owner",
            "cards_by_snapshot",
            "search_results_by_rank",
            "searches_by_owner",
            "source_snapshots_by_article",
            "source_snapshots_by_raw_blob_key",
        }


def test_reopening_applies_nothing_and_keeps_the_data(tmp_path: Path) -> None:
    with SqliteDatabase.open(tmp_path) as first:
        first.connection.execute(
            "INSERT INTO articles (article_id, canonical_url, created_at, revision, document) "
            "VALUES ('01J000000000000000000001', 'https://example.org/a', '2024-01-01', 1, '{}')"
        )
        version = first.schema_version()

    with SqliteDatabase.open(tmp_path) as second:
        assert apply_migrations(second.connection) == ()
        assert second.schema_version() == version
        stored = second.connection.execute("SELECT COUNT(*) AS total FROM articles").fetchone()
        assert stored["total"] == 1


def test_applying_migrations_repeatedly_is_a_no_op(tmp_path: Path) -> None:
    with SqliteDatabase.open(tmp_path) as database:
        applied_again = apply_migrations(database.connection)
        applied_a_third_time = apply_migrations(database.connection)

        assert applied_again == ()
        assert applied_a_third_time == ()
        assert table_names(database.connection) == EXPECTED_TABLES


def test_a_fresh_database_records_every_migration_it_ran(tmp_path: Path) -> None:
    database_path = tmp_path / DATABASE_FILENAME
    connection = sqlite3.connect(database_path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    try:
        applied = apply_migrations(connection)

        assert [migration.version for migration in applied] == [
            migration.version for migration in load_migrations()
        ]
        recorded = connection.execute(
            f"SELECT version, name, applied_at FROM {SCHEMA_VERSION_TABLE} ORDER BY version"
        ).fetchall()
        assert [row["version"] for row in recorded] == [m.version for m in applied]
        assert [row["name"] for row in recorded] == [m.name for m in applied]
        assert all(str(row["applied_at"]).startswith("20") for row in recorded)
    finally:
        connection.close()


def test_a_database_from_a_newer_build_is_refused(tmp_path: Path) -> None:
    with SqliteDatabase.open(tmp_path) as database:
        database.connection.execute(
            f"INSERT INTO {SCHEMA_VERSION_TABLE} (version, name, applied_at) "
            "VALUES (9999, 'something this build has never heard of', '2030-01-01T00:00:00+00:00')"
        )

    with pytest.raises(MigrationError, match="written by a newer build"):
        SqliteDatabase.open(tmp_path)


# --------------------------------------------------------------------------------------------
# Transactions
# --------------------------------------------------------------------------------------------


def test_a_failed_transaction_leaves_nothing_behind(tmp_path: Path) -> None:
    with SqliteDatabase.open(tmp_path) as database:
        with pytest.raises(RuntimeError, match="deliberate"), database.transaction() as connection:
            connection.execute(
                "INSERT INTO articles (article_id, canonical_url, created_at, revision, document) "
                "VALUES ('01J000000000000000000001', 'https://example.org/a', '2024-01-01', 1, '{}')"
            )
            raise RuntimeError("deliberate")

        total = database.connection.execute("SELECT COUNT(*) AS total FROM articles").fetchone()
        assert total["total"] == 0
        assert database.connection.in_transaction is False


def test_a_completed_transaction_commits(tmp_path: Path) -> None:
    with SqliteDatabase.open(tmp_path) as database:
        with database.transaction() as connection:
            connection.execute(
                "INSERT INTO articles (article_id, canonical_url, created_at, revision, document) "
                "VALUES ('01J000000000000000000001', 'https://example.org/a', '2024-01-01', 1, '{}')"
            )

        total = database.connection.execute("SELECT COUNT(*) AS total FROM articles").fetchone()
        assert total["total"] == 1


def test_transactions_may_not_nest(tmp_path: Path) -> None:
    with (
        SqliteDatabase.open(tmp_path) as database,
        database.transaction(),
        pytest.raises(RuntimeError, match="one transaction per connection"),
        database.transaction(),
    ):
        pass


# --------------------------------------------------------------------------------------------
# The schema the database enforces
# --------------------------------------------------------------------------------------------


def test_tables_are_strict_about_column_types(tmp_path: Path) -> None:
    """A revision stored as text would compare and order wrongly, so STRICT refuses it outright."""
    with SqliteDatabase.open(tmp_path) as database, pytest.raises(sqlite3.IntegrityError):
        database.connection.execute(
            "INSERT INTO articles (article_id, canonical_url, created_at, revision, document) "
            "VALUES ('01J000000000000000000001', 'https://example.org/a', '2024-01-01', "
            "'not a number', '{}')"
        )


def test_deleting_a_search_takes_its_ranking_with_it(tmp_path: Path) -> None:
    with SqliteDatabase.open(tmp_path) as database:
        database.connection.execute(
            "INSERT INTO searches (search_id, created_at, revision, document) "
            "VALUES ('01J000000000000000000001', '2024-01-01', 1, '{}')"
        )
        database.connection.execute(
            'INSERT INTO search_results (search_id, article_id, "rank", document) '
            "VALUES ('01J000000000000000000001', '01J00000000000000000000A', 1, '{}')"
        )

        database.connection.execute("DELETE FROM searches")

        orphaned = database.connection.execute("SELECT COUNT(*) AS total FROM search_results").fetchone()
        assert orphaned["total"] == 0


def test_a_ranking_may_not_reference_an_unknown_search(tmp_path: Path) -> None:
    with SqliteDatabase.open(tmp_path) as database, pytest.raises(sqlite3.IntegrityError):
        database.connection.execute(
            'INSERT INTO search_results (search_id, article_id, "rank", document) '
            "VALUES ('01J000000000000000000001', '01J00000000000000000000A', 1, '{}')"
        )


# --------------------------------------------------------------------------------------------
# The migration set itself
# --------------------------------------------------------------------------------------------


def test_migrations_are_numbered_contiguously_from_one() -> None:
    migrations = load_migrations()

    assert migrations
    assert [migration.version for migration in migrations] == list(range(1, len(migrations) + 1))
    assert all(migration.statements for migration in migrations)


def test_migration_comments_are_stripped_and_statements_split() -> None:
    initial = load_migrations()[0]

    assert initial.name == "initial schema"
    assert initial.filename == "0001_initial_schema.sql"
    assert not any(statement.startswith("--") for statement in initial.statements)
    assert any(statement.startswith("CREATE TABLE articles") for statement in initial.statements)


def test_a_migration_that_fails_halfway_is_rolled_back_and_the_run_resumes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A half-applied migration would be unrepeatable: the next open would fail on what it made.

    Two migrations, the second broken. The first must commit and be recorded, the second must
    leave nothing, and the recorded version must be the first — which is what lets a fixed build
    pick the run up where it stopped.
    """
    good = Migration(
        version=1,
        name="good",
        statements=("CREATE TABLE good (id TEXT PRIMARY KEY NOT NULL) STRICT",),
    )
    broken = Migration(
        version=2,
        name="broken",
        statements=("CREATE TABLE half (id TEXT PRIMARY KEY NOT NULL) STRICT", "NOT VALID SQL"),
    )
    monkeypatch.setattr(sqlite_db, "load_migrations", lambda: (good, broken))

    with pytest.raises(MigrationError, match="0002_broken.sql failed and was rolled back"):
        SqliteDatabase.open(tmp_path)

    connection = sqlite3.connect(tmp_path / DATABASE_FILENAME, isolation_level=None)
    connection.row_factory = sqlite3.Row
    try:
        assert "good" in table_names(connection)
        assert "half" not in table_names(connection)
        assert read_schema_version(connection) == 1
    finally:
        connection.close()


def test_a_migration_filename_must_say_its_version_and_what_it_does() -> None:
    with pytest.raises(MigrationError, match="is not named"):
        build_migrations({"add_an_index.sql": "CREATE INDEX i ON articles (owner_id)"})


def test_two_migrations_may_not_claim_one_version() -> None:
    with pytest.raises(MigrationError, match="claim version 1"):
        build_migrations(
            {
                "0001_initial_schema.sql": "CREATE TABLE a (id TEXT PRIMARY KEY NOT NULL) STRICT",
                "1_initial_schema.sql": "CREATE TABLE b (id TEXT PRIMARY KEY NOT NULL) STRICT",
            }
        )


def test_a_gap_in_the_numbering_means_a_migration_was_lost() -> None:
    with pytest.raises(MigrationError, match="contiguously from 1"):
        build_migrations(
            {
                "0001_initial_schema.sql": "CREATE TABLE a (id TEXT PRIMARY KEY NOT NULL) STRICT",
                "0003_much_later.sql": "CREATE TABLE c (id TEXT PRIMARY KEY NOT NULL) STRICT",
            }
        )


def test_a_migration_may_not_manage_its_own_transaction() -> None:
    """The runner wraps each migration, so an inner COMMIT would publish half of one."""
    with pytest.raises(MigrationError, match="manages its own transaction"):
        build_migrations(
            {
                "0001_initial_schema.sql": (
                    "BEGIN;\nCREATE TABLE a (id TEXT PRIMARY KEY NOT NULL) STRICT;\nCOMMIT;"
                )
            }
        )


def test_a_migration_that_is_only_comments_is_rejected() -> None:
    with pytest.raises(MigrationError, match="contains no statements"):
        build_migrations({"0001_initial_schema.sql": "-- planned, but never written\n"})


def test_the_shipped_migrations_are_what_build_migrations_makes_of_them() -> None:
    assert load_migrations() == build_migrations(
        {
            "0001_initial_schema.sql": (
                Path(sqlite_db.__file__).parent / "migrations" / "0001_initial_schema.sql"
            ).read_text(encoding="utf-8")
        }
    )


def test_a_sqlite_too_old_for_the_schema_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """STRICT tables arrived in 3.37; on anything older the schema would not even be created."""
    too_old = (MINIMUM_SQLITE_VERSION[0], MINIMUM_SQLITE_VERSION[1] - 1, 0)
    monkeypatch.setattr(sqlite3, "sqlite_version_info", too_old)
    monkeypatch.setattr(sqlite3, "sqlite_version", ".".join(str(part) for part in too_old))

    with pytest.raises(MigrationError, match="needs SQLite"):
        SqliteDatabase.open(tmp_path)
