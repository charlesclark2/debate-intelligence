"""The in-memory and SQLite article repositories are both held to the `ArticleRepository` contract.

Articles, and the snapshot metadata stored beside them. The adapter-specific half — that a row
survives closing and reopening the file, that a corrupted JSON column is reported as
`CorruptRecordError` — is in `packages/debate_core/tests/integrations/local/test_sqlite_repos.py`.
"""

from __future__ import annotations

import pytest

from debate_core.integrations.local import SqliteArticleRepository, SqliteDatabase
from debate_core.testing.contracts import ArticleRepositoryContract, ArticleRepositoryFactory
from debate_core.testing.fakes import InMemoryArticleRepository


class TestInMemoryArticleRepository(ArticleRepositoryContract):
    """The fake other packages' tests wire in really is an `ArticleRepository`."""

    @pytest.fixture
    def make_adapter(self) -> ArticleRepositoryFactory:
        """Two dictionaries, handed out as many times as the contract asks for a handle."""
        repository = InMemoryArticleRepository()
        return lambda: repository


class TestSqliteArticleRepository(ArticleRepositoryContract):
    """V1's real article repository, over a database file under `tmp_path`."""

    @pytest.fixture
    def make_adapter(self, sqlite_database: SqliteDatabase) -> ArticleRepositoryFactory:
        """A new repository object per call, all of them over one database — two real writers."""
        return lambda: SqliteArticleRepository(sqlite_database)
