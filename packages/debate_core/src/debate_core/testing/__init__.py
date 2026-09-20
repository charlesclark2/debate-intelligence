"""Test doubles that ship with the library.

They live in `debate_core` rather than under a `tests/` directory for two reasons: every package's
tests need them — `debate_cli`, `debate_api` and `debate_workers` each wire a service to fakes —
and the reusable repository contract suite lives here too, so that a V2 DynamoDB adapter is held
to the same contract as the V1 SQLite one.

Two things are exported from here:

* :mod:`debate_core.testing.fakes` — an in-memory implementation of every port.
* :mod:`debate_core.testing.builders` — builders that produce complete, valid domain entities
  from a handful of keyword arguments.

The third, :mod:`debate_core.testing.contracts`, is deliberately *not* re-exported. It imports
pytest, so it is importable in a test environment and not in a running CLI or API; a test that
wants it imports `debate_core.testing.contracts` directly.

Everything here is deterministic and offline. Nothing reads the clock, the filesystem or the
network.
"""

from debate_core.testing.builders import (
    build_article,
    build_card,
    build_card_span,
    build_citation,
    build_search,
    build_search_result,
    build_source_snapshot,
    readable_id,
    sha256_of,
)
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
    "build_article",
    "build_card",
    "build_card_span",
    "build_citation",
    "build_fake_caselist_repository",
    "build_fake_ports",
    "build_search",
    "build_search_result",
    "build_source_snapshot",
    "readable_id",
    "sha256_of",
]
