"""In-memory fakes of the persistence ports: articles, snapshot blobs, cards and searches.

Each really does the job its port in :mod:`debate_core.application.ports.persistence` describes:
`InMemoryCardRepository` really refuses a stale write, `InMemorySnapshotStore` really deduplicates
identical bytes and really detects a corrupted blob. The shared contract suites hold these and the
SQLite adapters to the same behaviour, down to which cursors are rejected.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from datetime import datetime

from debate_core.application.errors import (
    AlreadyExists,
    BlobIntegrityError,
    InvalidCursor,
    NotFound,
    RevisionMismatch,
)
from debate_core.application.ports.persistence import DEFAULT_PAGE_SIZE, BlobKey, Page
from debate_core.domain import Article, Card, Search, SearchResult, SourceSnapshot
from debate_core.domain.discovery import ProviderStatus

__all__ = [
    "InMemoryArticleRepository",
    "InMemoryCardRepository",
    "InMemorySearchRepository",
    "InMemorySnapshotStore",
    "paginate",
]


def _newest_first[ItemT](rows: Iterable[tuple[str, datetime, ItemT]]) -> list[tuple[str, ItemT]]:
    """Order rows by `created_at` descending, breaking ties by id descending.

    The tie-break is what makes the order total, and therefore what makes pagination reproducible:
    two records created in the same millisecond must not be able to swap places between pages.
    """
    ordered = sorted(rows, key=lambda row: (row[1], row[0]), reverse=True)
    return [(row[0], row[2]) for row in ordered]


def paginate[ItemT](
    rows: Sequence[tuple[str, ItemT]], *, kind: str, limit: int, cursor: str | None
) -> Page[ItemT]:
    """Cut one page out of an already-ordered sequence of (id, item) rows.

    The cursor is `"<kind>:<id of the last item on the previous page>"`. It is opaque to callers
    by contract, and a cursor minted by a different listing is rejected rather than silently
    treated as "start from the beginning".
    """
    if limit < 1:
        raise ValueError(f"limit must be at least 1, got {limit}")
    start = 0
    if cursor is not None:
        prefix = f"{kind}:"
        if not cursor.startswith(prefix):
            raise InvalidCursor(cursor)
        last_id = cursor[len(prefix) :]
        positions = [index for index, (row_id, _) in enumerate(rows) if row_id == last_id]
        if not positions:
            raise InvalidCursor(cursor)
        start = positions[0] + 1
    window = rows[start : start + limit]
    exhausted = start + limit >= len(rows)
    next_cursor = None if exhausted or not window else f"{kind}:{window[-1][0]}"
    return Page(items=tuple(item for _, item in window), next_cursor=next_cursor)


class InMemoryArticleRepository:
    """Articles and snapshot metadata in two dictionaries.

    Saving an article is an upsert that bumps its revision; saving a snapshot refuses to overwrite
    one, because snapshots are immutable and re-retrieving a source is a new snapshot.
    """

    def __init__(self) -> None:
        self._articles: dict[str, Article] = {}
        self._snapshots: dict[str, SourceSnapshot] = {}

    async def get(self, article_id: str) -> Article:
        stored = self._articles.get(article_id)
        if stored is None:
            raise NotFound("Article", article_id)
        return stored

    async def find_by_canonical_url(self, canonical_url: str) -> Article | None:
        """The most recently created match, breaking a tie on the id, exactly as the port says.

        Returning the first article the dictionary happened to yield would make the answer depend
        on insertion order, which is precisely the non-answer the port rules out.
        """
        matching = [article for article in self._articles.values() if article.canonical_url == canonical_url]
        if not matching:
            return None
        return max(matching, key=lambda article: (article.created_at, article.article_id))

    async def save(self, article: Article) -> Article:
        stored = self._articles.get(article.article_id)
        revision = 1 if stored is None else stored.revision + 1
        saved = article.evolve(revision=revision)
        self._articles[saved.article_id] = saved
        return saved

    async def delete(self, article_id: str) -> None:
        if article_id not in self._articles:
            raise NotFound("Article", article_id)
        del self._articles[article_id]

    async def list_by_owner(
        self, owner_id: str, *, limit: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> Page[Article]:
        rows = _newest_first(
            (article.article_id, article.created_at, article)
            for article in self._articles.values()
            if article.owner_id == owner_id
        )
        return paginate(rows, kind="article", limit=limit, cursor=cursor)

    async def save_snapshot(self, snapshot: SourceSnapshot) -> SourceSnapshot:
        if snapshot.snapshot_id in self._snapshots:
            raise AlreadyExists("SourceSnapshot", snapshot.snapshot_id)
        self._snapshots[snapshot.snapshot_id] = snapshot
        return snapshot

    async def get_snapshot(self, snapshot_id: str) -> SourceSnapshot:
        stored = self._snapshots.get(snapshot_id)
        if stored is None:
            raise NotFound("SourceSnapshot", snapshot_id)
        return stored

    async def list_snapshots(self, article_id: str) -> tuple[SourceSnapshot, ...]:
        matching = [snapshot for snapshot in self._snapshots.values() if snapshot.article_id == article_id]
        matching.sort(key=lambda snapshot: (snapshot.retrieved_at, snapshot.snapshot_id), reverse=True)
        return tuple(matching)


class InMemorySnapshotStore:
    """Content-addressed blobs in a dictionary, integrity check included.

    `get` re-hashes what it holds, exactly as the filesystem and S3 stores do, so a test can prove
    that a tampered snapshot is caught rather than served — see :meth:`corrupt`.
    """

    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}

    async def put(self, data: bytes) -> BlobKey:
        key = hashlib.sha256(data).hexdigest()
        self._blobs.setdefault(key, data)
        return key

    async def get(self, key: BlobKey) -> bytes:
        stored = self._blobs.get(key)
        if stored is None:
            raise NotFound("snapshot blob", key)
        actual = hashlib.sha256(stored).hexdigest()
        if actual != key:
            raise BlobIntegrityError(key, actual)
        return stored

    async def exists(self, key: BlobKey) -> bool:
        return key in self._blobs

    def stored_keys(self) -> frozenset[BlobKey]:
        """Every key a blob is held under: one entry per stored copy.

        Test-only, like :meth:`corrupt`: it is how a test counts copies to show that storing the same
        bytes twice stored them once. The port has no listing, on purpose.
        """
        return frozenset(self._blobs)

    def corrupt(self, key: BlobKey, replacement: bytes) -> None:
        """Replace a blob's bytes without changing its key, to test tamper detection.

        Test-only, and deliberately not part of the :class:`~debate_core.application.ports.
        persistence.SnapshotStore` port: no production code can rewrite a stored blob.
        """
        if key not in self._blobs:
            raise NotFound("snapshot blob", key)
        self._blobs[key] = replacement


class InMemoryCardRepository:
    """Cards in a dictionary, with the same optimistic-concurrency rules as SQLite and DynamoDB.

    The revision check is the whole point of the fake: a test that a reprocessing job cannot
    overwrite a student's edit must fail here for the same reason it would fail in production.
    """

    def __init__(self) -> None:
        self._cards: dict[str, Card] = {}

    async def get(self, card_id: str) -> Card:
        stored = self._cards.get(card_id)
        if stored is None:
            raise NotFound("Card", card_id)
        return stored

    async def find(self, card_id: str) -> Card | None:
        return self._cards.get(card_id)

    async def create(self, card: Card) -> Card:
        if card.card_id in self._cards:
            raise AlreadyExists("Card", card.card_id)
        saved = card.evolve(revision=1)
        self._cards[saved.card_id] = saved
        return saved

    async def save(self, card: Card, *, expected_revision: int) -> Card:
        stored = self._cards.get(card.card_id)
        if stored is None:
            raise NotFound("Card", card.card_id)
        if stored.revision != expected_revision:
            raise RevisionMismatch("Card", card.card_id, expected_revision, stored.revision)
        saved = card.evolve(revision=stored.revision + 1)
        self._cards[saved.card_id] = saved
        return saved

    async def delete(self, card_id: str, *, expected_revision: int) -> None:
        stored = self._cards.get(card_id)
        if stored is None:
            raise NotFound("Card", card_id)
        if stored.revision != expected_revision:
            raise RevisionMismatch("Card", card_id, expected_revision, stored.revision)
        del self._cards[card_id]

    async def list_by_owner(
        self, owner_id: str, *, limit: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> Page[Card]:
        rows = _newest_first(
            (card.card_id, card.created_at, card)
            for card in self._cards.values()
            if card.owner_id == owner_id
        )
        return paginate(rows, kind="card", limit=limit, cursor=cursor)

    async def list_by_article(
        self, article_id: str, *, limit: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> Page[Card]:
        rows = _newest_first(
            (card.card_id, card.created_at, card)
            for card in self._cards.values()
            if card.article_id == article_id
        )
        return paginate(rows, kind="card", limit=limit, cursor=cursor)


class InMemorySearchRepository:
    """Searches, their per-provider records and their rankings, each set replaced as a whole."""

    def __init__(self) -> None:
        self._searches: dict[str, Search] = {}
        self._results: dict[str, tuple[SearchResult, ...]] = {}
        self._provider_statuses: dict[str, tuple[ProviderStatus, ...]] = {}

    async def get(self, search_id: str) -> Search:
        stored = self._searches.get(search_id)
        if stored is None:
            raise NotFound("Search", search_id)
        return stored

    async def save(self, search: Search) -> Search:
        stored = self._searches.get(search.search_id)
        revision = 1 if stored is None else stored.revision + 1
        saved = search.evolve(revision=revision)
        self._searches[saved.search_id] = saved
        return saved

    async def save_results(self, search_id: str, results: Sequence[SearchResult]) -> None:
        if search_id not in self._searches:
            raise NotFound("Search", search_id)
        foreign = [result.article_id for result in results if result.search_id != search_id]
        if foreign:
            raise ValueError(f"results for another search were given for {search_id}: {foreign}")
        ranks = [result.rank for result in results]
        if len(set(ranks)) != len(ranks):
            raise ValueError(f"two results share a rank in search {search_id}: {sorted(ranks)}")
        articles = [result.article_id for result in results]
        if len(set(articles)) != len(articles):
            # A ranking is a total order over distinct articles. SQLite's primary key refuses this
            # too; the fake has to refuse it in the same words, or a caller's bug survives every
            # fake-backed test and only appears against real storage.
            raise ValueError(f"two results name the same article in search {search_id}: {sorted(articles)}")
        self._results[search_id] = tuple(sorted(results, key=lambda result: result.rank))

    async def list_results(self, search_id: str) -> tuple[SearchResult, ...]:
        if search_id not in self._searches:
            raise NotFound("Search", search_id)
        return self._results.get(search_id, ())

    async def save_provider_statuses(self, search_id: str, statuses: Sequence[ProviderStatus]) -> None:
        if search_id not in self._searches:
            raise NotFound("Search", search_id)
        self._provider_statuses[search_id] = tuple(statuses)

    async def list_provider_statuses(self, search_id: str) -> tuple[ProviderStatus, ...]:
        if search_id not in self._searches:
            raise NotFound("Search", search_id)
        return self._provider_statuses.get(search_id, ())

    async def list_by_owner(
        self, owner_id: str, *, limit: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> Page[Search]:
        rows = _newest_first(
            (search.search_id, search.created_at, search)
            for search in self._searches.values()
            if search.owner_id == owner_id
        )
        return paginate(rows, kind="search", limit=limit, cursor=cursor)
