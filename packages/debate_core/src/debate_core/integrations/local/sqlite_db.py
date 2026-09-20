"""The SQLite file behind V1's repositories: one connection, its pragmas, and its schema.

The four local repositories share one :class:`SqliteDatabase` rather than each opening the file
for itself. That is what makes the pragmas, the migration run and the transaction boundary
singular: a write that spans two tables — replacing a search's ranking, say — is one transaction,
and the schema is brought up to date exactly once, when the file is opened.

## Opening a database

::

    database = SqliteDatabase.open(settings.storage.data_dir)
    articles = SqliteArticleRepository(database)

:meth:`SqliteDatabase.open` creates the data directory if it is missing, connects to
`<data_dir>/debate.sqlite3`, applies the pragmas below and migrates the schema. Opening an
existing, current database applies no migration and is the ordinary case: every CLI command does
it.

## The pragmas, and why each one

* **`journal_mode=WAL`** — a reader never blocks the writer. The CLI reads while a background
  reprocessing job writes, and under the default rollback journal that is a locked database.
  WAL is a property of the *file*, so it is set once and persists.
* **`foreign_keys=ON`** — SQLite defaults this off, per connection, for backwards compatibility.
  It is the only foreign key in the schema (`search_results` → `searches`) that needs it, and a
  connection that forgot it would silently leave orphaned rankings behind.
* **`synchronous=FULL`** — the default in WAL mode is `NORMAL`, which can lose the last committed
  transactions if the machine loses power. This is a student's evidence on a laptop that gets
  closed mid-write; a few milliseconds per commit is the right trade.
* **`busy_timeout`** — wait for a concurrent writer rather than failing instantly with
  `database is locked`, which is what a second `debate-research` process in another terminal
  otherwise produces.

## Migrations

Each `.sql` file in :mod:`debate_core.integrations.local.migrations` is one numbered migration.
:func:`apply_migrations` reads the `schema_version` table, runs the ones the database has not seen,
in order, each in its own transaction, and records it. Opening a database is therefore idempotent:
the first open creates the schema, every later open with no new migration files does nothing.

A database whose recorded version is *higher* than any migration this build ships raises
:class:`MigrationError` rather than being used. That is the case where an older build opens a file
a newer one wrote, and reading it under the old schema would be worse than refusing.

:class:`MigrationError` is not a :class:`~debate_core.application.errors.DomainError`, on purpose.
It cannot reach a use case: it is raised while the composition root is opening the database, before
any port exists to raise it across, and a service catching `DomainError` should not be catching
"this build cannot read this file".
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from types import TracebackType
from typing import Final, Self

__all__ = [
    "DATABASE_FILENAME",
    "MINIMUM_SQLITE_VERSION",
    "SCHEMA_VERSION_TABLE",
    "Migration",
    "MigrationError",
    "SqliteDatabase",
    "apply_migrations",
    "build_migrations",
    "load_migrations",
    "pragma_values",
    "read_schema_version",
]

DATABASE_FILENAME: Final = "debate.sqlite3"
"""Name of the database inside the data directory."""

SCHEMA_VERSION_TABLE: Final = "schema_version"
"""Table recording which migrations a database has had applied."""

MINIMUM_SQLITE_VERSION: Final = (3, 37, 0)
"""Oldest SQLite the schema runs on: 3.37 is where `STRICT` tables arrived (2021-11)."""

BUSY_TIMEOUT_MILLISECONDS: Final = 5_000
"""How long a statement waits for another process's write lock before giving up."""

#: The package holding the `.sql` files. Read through `importlib.resources`, so it works the same
#: from a source checkout and from an installed wheel.
MIGRATIONS_PACKAGE: Final = "debate_core.integrations.local.migrations"

#: `0001_initial_schema.sql` → version 1, name `initial schema`.
_MIGRATION_FILENAME = re.compile(r"^(?P<version>\d+)_(?P<name>[a-z0-9_]+)\.sql$")

#: A `--` comment to the end of its line. Stripped before statements are split on semicolons.
_SQL_LINE_COMMENT = re.compile(r"--[^\n]*")

#: Transaction control inside a migration file, which would break the runner's own transaction.
_TRANSACTION_CONTROL = re.compile(r"^\s*(BEGIN|COMMIT|ROLLBACK|END)\b", re.IGNORECASE)


class MigrationError(RuntimeError):
    """A database's schema cannot be brought to the version this build expects.

    Raised while opening the file — a broken migration file, a gap in the numbering, a database
    written by a newer build, or a SQLite too old for the schema. Deliberately outside the
    :class:`~debate_core.application.errors.DomainError` hierarchy: nothing has a port yet when
    this is raised, so no use case can be expected to handle it.
    """


@dataclass(frozen=True, slots=True)
class Migration:
    """One numbered migration, already split into the statements it is made of."""

    version: int
    """Its position in the sequence, from the filename. Contiguous from 1."""

    name: str
    """What it does, from the filename, with underscores as spaces: `initial schema`."""

    statements: tuple[str, ...]
    """Its statements in order, comments stripped, each without its terminating semicolon."""

    @property
    def filename(self) -> str:
        """The file this migration was read from."""
        return f"{self.version:04d}_{self.name.replace(' ', '_')}.sql"


def load_migrations() -> tuple[Migration, ...]:
    """Read every migration file shipped in this build, in version order.

    Reads through `importlib.resources`, so it behaves the same in a source checkout and in an
    installed wheel. The validation itself is :func:`build_migrations`.
    """
    files = {
        entry.name: entry.read_text(encoding="utf-8")
        for entry in resources.files(MIGRATIONS_PACKAGE).iterdir()
        if entry.name.endswith(".sql")
    }
    return build_migrations(files)


def build_migrations(files: Mapping[str, str]) -> tuple[Migration, ...]:
    """Parse and check a set of migration files, keyed by filename, into an ordered sequence.

    Separate from :func:`load_migrations` because this is where every rule the migrations package
    documents is enforced, and a rule is only worth stating if a test can watch it fire.

    Raises :class:`MigrationError` when a filename does not parse, two files claim one version, the
    numbering does not run contiguously from 1, a file manages its own transaction, or a file is
    empty.
    """
    found: dict[int, Migration] = {}
    for filename in sorted(files):
        matched = _MIGRATION_FILENAME.match(filename)
        if matched is None:
            raise MigrationError(
                f"migration file {filename!r} is not named <version>_<description>.sql, "
                "for example 0002_add_card_tag_index.sql"
            )
        version = int(matched.group("version"))
        if version in found:
            raise MigrationError(
                f"two migration files claim version {version}: {found[version].filename} and {filename}"
            )
        found[version] = Migration(
            version=version,
            name=matched.group("name").replace("_", " "),
            statements=_split_statements(files[filename], filename),
        )

    ordered = tuple(found[version] for version in sorted(found))
    expected = tuple(range(1, len(ordered) + 1))
    if tuple(migration.version for migration in ordered) != expected:
        raise MigrationError(
            "migration versions must run contiguously from 1; found "
            f"{[migration.version for migration in ordered]}"
        )
    return ordered


def _split_statements(sql: str, filename: str) -> tuple[str, ...]:
    """Strip `--` comments and split a migration file into its individual statements.

    Splitting on semicolons is only safe because a migration file holds plain DDL — no trigger
    bodies, no semicolons inside string literals — which is the rule the migrations package
    documents. `sqlite3.Connection.executescript` would avoid the split but commits any open
    transaction before it runs, which would defeat the point of running a migration inside one.
    """
    statements = tuple(
        statement
        for statement in (part.strip() for part in _SQL_LINE_COMMENT.sub("", sql).split(";"))
        if statement
    )
    for statement in statements:
        if _TRANSACTION_CONTROL.match(statement):
            raise MigrationError(
                f"{filename} manages its own transaction ({statement.split()[0].upper()}); "
                "the migration runner owns the transaction, so remove it"
            )
    if not statements:
        raise MigrationError(f"{filename} contains no statements")
    return statements


def apply_migrations(
    connection: sqlite3.Connection, *, database_label: str = "this database"
) -> tuple[Migration, ...]:
    """Bring a database up to the newest migration and return the ones that were applied.

    Idempotent: applies only migrations whose version is above the recorded one, each inside its
    own transaction with its `schema_version` row, so an interrupted run leaves the database at the
    last migration that fully succeeded and the next open resumes from there.

    Raises :class:`MigrationError` if the database records a version this build does not ship.
    """
    connection.execute(
        f"CREATE TABLE IF NOT EXISTS {SCHEMA_VERSION_TABLE} ("
        "    version INTEGER PRIMARY KEY NOT NULL,"
        "    name TEXT NOT NULL,"
        "    applied_at TEXT NOT NULL"
        ") STRICT"
    )
    current = read_schema_version(connection)
    known = load_migrations()
    newest = known[-1].version if known else 0
    if current > newest:
        raise MigrationError(
            f"{database_label} holds schema version {current}, but this build ships migrations up "
            f"to {newest}. It was written by a newer build of debate_core; upgrade rather than "
            "downgrade, because an older schema cannot read a newer database safely."
        )

    applied: list[Migration] = []
    for migration in known:
        if migration.version <= current:
            continue
        _apply_one(connection, migration)
        applied.append(migration)
    return tuple(applied)


def _apply_one(connection: sqlite3.Connection, migration: Migration) -> None:
    """Run one migration and record it, both or neither."""
    connection.execute("BEGIN IMMEDIATE")
    try:
        for statement in migration.statements:
            connection.execute(statement)
        connection.execute(
            f"INSERT INTO {SCHEMA_VERSION_TABLE} (version, name, applied_at) VALUES (?, ?, ?)",
            (migration.version, migration.name, datetime.now(UTC).isoformat()),
        )
    except BaseException as failure:
        connection.execute("ROLLBACK")
        if isinstance(failure, sqlite3.Error):
            raise MigrationError(
                f"migration {migration.filename} failed and was rolled back: {failure}"
            ) from failure
        raise
    connection.execute("COMMIT")


def read_schema_version(connection: sqlite3.Connection) -> int:
    """Return the highest migration version recorded, or 0 for a database with no schema yet."""
    row = connection.execute(f"SELECT MAX(version) FROM {SCHEMA_VERSION_TABLE}").fetchone()
    return 0 if row is None or row[0] is None else int(row[0])


class SqliteDatabase:
    """One open SQLite file: the connection the local repositories share.

    Built by :meth:`open` from a data directory and handed to each repository's constructor. It
    owns the connection's lifetime, so closing it closes the database for all four of them.

    Not thread-safe, by construction rather than by omission: the connection keeps sqlite3's
    `check_same_thread` guard, and the adapters do their work synchronously without awaiting, so
    calls cannot interleave. A surface that needs a database per thread opens one per thread.
    """

    def __init__(self, connection: sqlite3.Connection, *, path: Path) -> None:
        self._connection = connection
        self._path = path

    @classmethod
    def open(cls, data_dir: Path, *, filename: str = DATABASE_FILENAME) -> Self:
        """Open (creating if needed) the database under `data_dir` and migrate it.

        The data directory is created if it does not exist, because the first command a new user
        runs should work rather than report a missing directory they were never told to make.
        """
        if sqlite3.sqlite_version_info < MINIMUM_SQLITE_VERSION:
            expected = ".".join(str(part) for part in MINIMUM_SQLITE_VERSION)
            raise MigrationError(
                f"the local schema needs SQLite {expected} or newer for STRICT tables; "
                f"this Python is linked against {sqlite3.sqlite_version}"
            )
        directory = Path(data_dir)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / filename
        # isolation_level=None turns off sqlite3's implicit transaction handling, which starts and
        # commits transactions on its own reading of the SQL. Every transaction here is explicit.
        connection = sqlite3.connect(path, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            _apply_pragmas(connection)
            apply_migrations(connection, database_label=str(path))
        except BaseException:
            connection.close()
            raise
        return cls(connection, path=path)

    @property
    def path(self) -> Path:
        """The database file."""
        return self._path

    @property
    def connection(self) -> sqlite3.Connection:
        """The shared connection, for a repository's own reads.

        A read needs no transaction — SQLite gives a single statement a consistent view by itself —
        so reads go straight to the connection and writes go through :meth:`transaction`.
        """
        return self._connection

    def schema_version(self) -> int:
        """The migration version this database is currently at."""
        return read_schema_version(self._connection)

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection]:
        """Run a block inside one `BEGIN IMMEDIATE` transaction, committing or rolling back.

        `IMMEDIATE` takes the write lock up front rather than on the first write. A read-then-write
        — every revision check in this package is one — would otherwise start as a reader and have
        to upgrade, which SQLite can refuse with `SQLITE_BUSY` once another writer has started, and
        an optimistic-concurrency check that fails for that reason would report the wrong thing.

        Transactions do not nest: SQLite has one per connection, and nesting would make an inner
        block's commit silently publish the outer block's half-finished work.
        """
        if self._connection.in_transaction:
            raise RuntimeError(
                "a transaction is already open on this connection; SQLite has one transaction per "
                "connection, so repository methods must not nest them"
            )
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            yield self._connection
        except BaseException:
            self._connection.execute("ROLLBACK")
            raise
        self._connection.execute("COMMIT")

    def close(self) -> None:
        """Close the connection. Further use of any repository built on it will fail."""
        self._connection.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def _apply_pragmas(connection: sqlite3.Connection) -> None:
    """Put the connection into the mode the schema and the repositories assume."""
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA synchronous = FULL")
    connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MILLISECONDS}")


def pragma_values(connection: sqlite3.Connection, names: Sequence[str]) -> dict[str, object]:
    """Read named pragmas back, for a test or a `doctor` command that checks how a file is open."""
    values: dict[str, object] = {}
    for name in names:
        row = connection.execute(f"PRAGMA {name}").fetchone()
        values[name] = None if row is None else row[0]
    return values
