"""The contract every persistence adapter must pass, wherever it stores things.

`debate_core.application.ports` says in prose what an `ArticleRepository`, a `SnapshotStore`, a
`CardRepository`, a `SearchRepository` and an `EvidenceObjectStore` do. This package says it in tests.
A V1 adapter built on SQLite and the local filesystem and a V2 adapter built on DynamoDB and S3
are interchangeable only if both are held to the same rules, and the way to make that true is for
both to run the same suite (architecture proposal §16, §17).

Five contract classes, one per port::

    from debate_core.testing.contracts import CardRepositoryContract

    class TestSqliteCardRepository(CardRepositoryContract):
        @pytest.fixture
        def make_adapter(self, database: SqliteDatabase) -> CardRepositoryFactory:
            return lambda: SqliteCardRepository(database)

That is the whole opt-in: subclass, override one fixture. `README.md` in this directory has the
full walkthrough, including what the factory must guarantee and which behaviour the contracts
deliberately leave to the adapter.

**This package imports pytest**, so it is importable in a test environment and not in a running
CLI or API. That is why `debate_core.testing` does not re-export it: `from debate_core.testing
import build_fake_ports` keeps working in production code paths, and only a test ever reaches
`debate_core.testing.contracts`.
"""

from debate_core.testing.contracts.evidence_object_store import (
    EvidenceObjectStoreContract,
    EvidenceObjectStoreFactory,
)
from debate_core.testing.contracts.harness import (
    ASYNC_BACKEND,
    AdapterContract,
    ArticleRepositoryFactory,
    BlobCorruptor,
    CardRepositoryFactory,
    SearchRepositoryFactory,
    SnapshotStoreFactory,
    walk_all_pages,
)
from debate_core.testing.contracts.repositories import (
    ArticleRepositoryContract,
    CardRepositoryContract,
    SearchRepositoryContract,
)
from debate_core.testing.contracts.snapshot_store import SnapshotStoreContract

__all__ = [
    "ASYNC_BACKEND",
    "AdapterContract",
    "ArticleRepositoryContract",
    "ArticleRepositoryFactory",
    "BlobCorruptor",
    "CardRepositoryContract",
    "CardRepositoryFactory",
    "EvidenceObjectStoreContract",
    "EvidenceObjectStoreFactory",
    "SearchRepositoryContract",
    "SearchRepositoryFactory",
    "SnapshotStoreContract",
    "SnapshotStoreFactory",
    "walk_all_pages",
]
