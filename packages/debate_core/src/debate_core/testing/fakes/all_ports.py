"""One fake for each of the ten ports every service takes, assembled as `FakePorts`.

The one fakes module that imports more than one port, because its job is to assign every fake to
its Protocol, where pyright strict checks it. A test that needs one fake imports that fake's own
module instead, and reaches only that port.
"""

from __future__ import annotations

from dataclasses import dataclass

from debate_core.application.ports.model_router import ModelRouter
from debate_core.application.ports.persistence import (
    ArticleRepository,
    CardRepository,
    SearchRepository,
    SnapshotStore,
)
from debate_core.application.ports.providers import (
    ArticleFetcher,
    Clock,
    ContentExtractor,
    IdGenerator,
    SearchProvider,
)
from debate_core.testing.fakes.clock_and_ids import FixedClock, SequentialIdGenerator
from debate_core.testing.fakes.model_router import ScriptedModelRouter
from debate_core.testing.fakes.persistence import (
    InMemoryArticleRepository,
    InMemoryCardRepository,
    InMemorySearchRepository,
    InMemorySnapshotStore,
)
from debate_core.testing.fakes.providers import (
    FakeArticleFetcher,
    FakeContentExtractor,
    FakeSearchProvider,
)

__all__ = ["FakePorts", "build_fake_ports"]


@dataclass(frozen=True, slots=True)
class FakePorts:
    """One of every port, wired to its fake.

    The fields are annotated with the *Protocols*, not with the fake classes. That is deliberate,
    and it is what checks acceptance criterion ac4 of this task: if a fake drifts from its port —
    a renamed argument, a dropped method, a changed return type — pyright fails on the
    corresponding line of :func:`build_fake_ports`, in this package, rather than somewhere in a
    test months later.

    A test that needs a fake's own helpers (`FakeArticleFetcher.add`,
    `InMemorySnapshotStore.corrupt`) builds that fake directly instead of reaching through here.
    """

    article_repository: ArticleRepository
    snapshot_store: SnapshotStore
    card_repository: CardRepository
    search_repository: SearchRepository
    search_provider: SearchProvider
    article_fetcher: ArticleFetcher
    content_extractor: ContentExtractor
    model_router: ModelRouter
    clock: Clock
    id_generator: IdGenerator


def build_fake_ports(
    *,
    clock: FixedClock | None = None,
    id_generator: SequentialIdGenerator | None = None,
) -> FakePorts:
    """Build one fake for every port, sharing one clock so timestamps line up across them."""
    shared_clock = clock if clock is not None else FixedClock()
    return FakePorts(
        article_repository=InMemoryArticleRepository(),
        snapshot_store=InMemorySnapshotStore(),
        card_repository=InMemoryCardRepository(),
        search_repository=InMemorySearchRepository(),
        search_provider=FakeSearchProvider(),
        article_fetcher=FakeArticleFetcher(clock=shared_clock),
        content_extractor=FakeContentExtractor(),
        model_router=ScriptedModelRouter(clock=shared_clock),
        clock=shared_clock,
        id_generator=id_generator if id_generator is not None else SequentialIdGenerator(),
    )
