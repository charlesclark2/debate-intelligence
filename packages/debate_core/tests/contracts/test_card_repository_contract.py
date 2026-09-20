"""The in-memory and SQLite card repositories are both held to the `CardRepository` contract.

This is the binding that matters most. A fake that did not really refuse a stale write would let
every other package's tests pass while the protection a student's edit depends on was broken, so
the fake is held to the same optimistic-concurrency rules as the SQLite repository — including
the two-writers race in
`CardRepositoryContract.test_two_writers_at_the_same_revision_produce_one_success_and_one_mismatch`.

The adapter-specific half — that the revision check is one conditional `UPDATE` rather than a read
followed by a hopeful write — is in
`packages/debate_core/tests/integrations/local/test_sqlite_repos.py`.
"""

from __future__ import annotations

import pytest

from debate_core.integrations.local import SqliteCardRepository, SqliteDatabase
from debate_core.testing.contracts import CardRepositoryContract, CardRepositoryFactory
from debate_core.testing.fakes import InMemoryCardRepository


class TestInMemoryCardRepository(CardRepositoryContract):
    """The fake other packages' tests wire in really is a `CardRepository`."""

    @pytest.fixture
    def make_adapter(self) -> CardRepositoryFactory:
        """One dictionary, handed out as many times as the contract asks for a handle."""
        repository = InMemoryCardRepository()
        return lambda: repository


class TestSqliteCardRepository(CardRepositoryContract):
    """V1's real card repository, over a database file under `tmp_path`."""

    @pytest.fixture
    def make_adapter(self, sqlite_database: SqliteDatabase) -> CardRepositoryFactory:
        """A new repository object per call, all of them over one database — two real writers."""
        return lambda: SqliteCardRepository(sqlite_database)
