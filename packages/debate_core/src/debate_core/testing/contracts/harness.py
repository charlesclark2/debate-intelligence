"""The pieces every contract class is built from: the adapter factory, the async mode, paging.

Read `README.md` in this directory first; it explains how an adapter opts in. This module holds
the machinery those contracts share, in one place, so the four contract classes contain assertions
and nothing else.

## The adapter factory

Every contract asks its binding for one fixture, `make_adapter`, and that fixture is a *factory*
rather than a single adapter. Calling it twice must hand back two handles onto **the same**
storage — two `SqliteCardRepository` objects over one database file, two `S3SnapshotStore` clients
over one bucket — because that is the only way a contract can stage the situation the platform
actually has to survive: two writers racing for one card (architecture proposal §7). Returning the
same object twice is a valid answer for an implementation where one handle is all there is.

Storage must be **empty at the start of each test**, which follows from `make_adapter` being a
function-scoped fixture and is why no contract cleans up after itself.

## Why the contracts are `async def`

The persistence ports are `async` because their cloud implementations are I/O-bound over a
network. V1's local adapters do their work synchronously and never suspend, so the adapter-level
tests in `packages/debate_core/tests/integrations/` drive them with a bare `coroutine.send(None)`
and assert that they never await. A shared contract cannot do that: it has to hold a genuinely
asynchronous DynamoDB adapter to the same rules, and such an adapter really does suspend.

So the contracts run on a real event loop, through the pytest plugin that ships with `anyio`
(:data:`ASYNC_BACKEND`). `--disable-socket` would refuse to let the loop build its self-pipe, so
the workspace's pytest configuration passes `--allow-unix-socket`; `AF_INET` sockets stay blocked
and the suite stays offline.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest

from debate_core.application.ports import (
    ArticleRepository,
    BlobKey,
    CardRepository,
    Page,
    SearchRepository,
    SnapshotStore,
)

__all__ = [
    "ASYNC_BACKEND",
    "MAX_PAGES_WALKED",
    "AdapterContract",
    "ArticleRepositoryFactory",
    "BlobCorruptor",
    "CardRepositoryFactory",
    "SearchRepositoryFactory",
    "SnapshotStoreFactory",
    "walk_all_pages",
]

#: The anyio backend the contracts run on. asyncio, because that is what the CLI, the API and the
#: workers run on; an adapter that only worked under Trio would pass a test nothing else matches.
ASYNC_BACKEND = "asyncio"

#: Safety stop for :func:`walk_all_pages`. A repository that keeps minting cursors for a listing
#: this small has a paging bug, and the contract should say so rather than hang the suite.
MAX_PAGES_WALKED = 50


type SnapshotStoreFactory = Callable[[], SnapshotStore]
"""Returns another handle onto the same blob store."""

type ArticleRepositoryFactory = Callable[[], ArticleRepository]
"""Returns another handle onto the same article storage."""

type CardRepositoryFactory = Callable[[], CardRepository]
"""Returns another handle onto the same card storage."""

type SearchRepositoryFactory = Callable[[], SearchRepository]
"""Returns another handle onto the same search storage."""

type BlobCorruptor = Callable[[BlobKey, bytes], None]
"""Replaces a stored blob's bytes without changing the key it is filed under.

Only a test double for damage: it is how a contract stages the corruption that
:class:`~debate_core.application.errors.BlobIntegrityError` exists to report. No production code
path can do this, which is why it is supplied by the binding rather than by the port.
"""


class AdapterContract:
    """Base class for the four port contracts: async mode, and nothing else.

    It deliberately declares no `make_adapter`. Each contract declares its own, typed to its own
    port, so that a binding which returns the wrong kind of adapter fails type checking rather
    than failing an assertion halfway through a test.
    """

    pytestmark = pytest.mark.anyio

    @pytest.fixture
    def anyio_backend(self) -> str:
        """Run every contract test on asyncio. Override in a binding only to add a backend."""
        return ASYNC_BACKEND


async def walk_all_pages[ItemT](
    fetch_page: Callable[[str | None], Awaitable[Page[ItemT]]],
    *,
    expected_pages: int,
) -> tuple[ItemT, ...]:
    """Follow `next_cursor` from the first page to the last and return every item, in order.

    Checks the three things that make pagination usable and that are easy to get subtly wrong in a
    new adapter: the walk ends (`next_cursor` is eventually `None`), it takes exactly
    `expected_pages` requests, and no item is served twice. What it does *not* check is the order —
    that is the caller's assertion, because it differs between listings.

    `fetch_page` takes the cursor and nothing else, so a caller binds the owner, the limit and the
    repository itself::

        items = await walk_all_pages(
            lambda cursor: repository.list_by_owner(owner_id, limit=2, cursor=cursor),
            expected_pages=3,
        )
    """
    collected: list[ItemT] = []
    cursor: str | None = None
    pages = 0
    while pages < MAX_PAGES_WALKED:
        page = await fetch_page(cursor)
        pages += 1
        for item in page.items:
            assert item not in collected, f"page {pages} served a record the walk had already seen"
            collected.append(item)
        if page.next_cursor is None:
            assert not page.has_more, "a page with no next_cursor must not report has_more"
            break
        assert page.has_more, "a page with a next_cursor must report has_more"
        assert page.items, "a page that promises more must not be empty"
        cursor = page.next_cursor
    else:  # pragma: no cover - only reachable from a repository that never stops paging
        raise AssertionError(f"listing never reached its last page in {MAX_PAGES_WALKED} requests")
    assert pages == expected_pages, f"expected {expected_pages} pages, the listing took {pages}"
    return tuple(collected)
