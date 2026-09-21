"""The in-memory and SQLite search repositories are both held to the `SearchRepository` contract.

Searches and their rankings. The adapter-specific half — the schema's own refusal of two results
naming one article, and the JSON column's revalidation on the way out — is in
`packages/debate_core/tests/integrations/local/test_sqlite_repos.py`.
"""

from __future__ import annotations

import pytest

from debate_core.integrations.local import SqliteDatabase, SqliteSearchRepository
from debate_core.testing.contracts import SearchRepositoryContract, SearchRepositoryFactory
from debate_core.testing.fakes import InMemorySearchRepository


class TestInMemorySearchRepository(SearchRepositoryContract):
    """The fake other packages' tests wire in really is a `SearchRepository`."""

    @pytest.fixture
    def make_adapter(self) -> SearchRepositoryFactory:
        """Two dictionaries, handed out as many times as the contract asks for a handle."""
        repository = InMemorySearchRepository()
        return lambda: repository


class TestSqliteSearchRepository(SearchRepositoryContract):
    """V1's real search repository, over a database file under `tmp_path`."""

    @pytest.fixture
    def make_adapter(self, sqlite_database: SqliteDatabase) -> SearchRepositoryFactory:
        """A new repository object per call, all of them over one database."""
        return lambda: SqliteSearchRepository(sqlite_database)
