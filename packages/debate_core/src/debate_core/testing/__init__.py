"""Test doubles that ship with the library.

They live in `debate_core` rather than under a `tests/` directory for two reasons: every package's
tests need them — `debate_cli`, `debate_api` and `debate_workers` each wire a service to fakes —
and the reusable repository contract suite (v1-e02-t04-repo-contract-tests) will live here too, so
that a V2 DynamoDB adapter is held to the same contract as the V1 SQLite one.

Everything here is deterministic and offline. Nothing reads the clock, the filesystem or the
network.
"""

from debate_core.testing.fakes import (
    FAKE_EPOCH,
    FakeArticleFetcher,
    FakeContentExtractor,
    FakeModelRouter,
    FakePorts,
    FakeSearchProvider,
    FixedClock,
    InMemoryArticleRepository,
    InMemoryCardRepository,
    InMemoryCaselistRepository,
    InMemorySearchRepository,
    InMemorySnapshotStore,
    RecordedModelCall,
    SequentialIdGenerator,
    build_fake_caselist_repository,
    build_fake_ports,
)

__all__ = [
    "FAKE_EPOCH",
    "FakeArticleFetcher",
    "FakeContentExtractor",
    "FakeModelRouter",
    "FakePorts",
    "FakeSearchProvider",
    "FixedClock",
    "InMemoryArticleRepository",
    "InMemoryCardRepository",
    "InMemoryCaselistRepository",
    "InMemorySearchRepository",
    "InMemorySnapshotStore",
    "RecordedModelCall",
    "SequentialIdGenerator",
    "build_fake_caselist_repository",
    "build_fake_ports",
]
