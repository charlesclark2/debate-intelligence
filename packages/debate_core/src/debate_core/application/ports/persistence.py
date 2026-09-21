"""Ports for everything the platform stores: entity records and content-addressed blobs.

Four ports live here, and together they are the only way a use case reaches storage:

* :class:`ArticleRepository` — articles and the metadata of the snapshots taken of them.
* :class:`SnapshotStore` — the snapshot *bytes*, addressed by their SHA-256.
* :class:`CardRepository` — cards, with the optimistic-concurrency check that protects edits.
* :class:`SearchRepository` — searches and their ranked results.

They are :class:`~typing.Protocol` classes, not base classes, so an adapter conforms by having the
right methods and never imports this module at runtime. V1 satisfies them with SQLite and the
local filesystem (v1-e02-t03-local-repositories); V2 satisfies them with DynamoDB and S3 without a
use case changing (architecture proposal §7, §17).

**Conventions every implementation follows.**

*Async.* Every method is `async` because every implementation is I/O-bound. An in-memory
implementation still declares `async def`; the cost is one already-finished coroutine.

*Errors.* Implementations raise only from :mod:`debate_core.application.errors`. A `get_*` method
raises :class:`~debate_core.application.errors.NotFound`; a `find_*` method returns `None`.

*Revisions.* The repository owns `revision`: a successful write returns the stored entity with
`revision` incremented, and callers must keep the returned instance rather than the one they
passed in. The repository does **not** touch `created_at` or `updated_at` — those are provenance,
and the calling service sets them from the :class:`~debate_core.application.ports.providers.Clock`
port so that time stays injectable and tests stay deterministic.

*Listing order.* Every `list_*` method that paginates returns newest first: `created_at`
descending, and for identical timestamps the entity id descending. Because ids are ULIDs, that is
a total order, which is what makes pagination reproducible across implementations.

*Cursors.* A cursor is an opaque string minted by the repository that produced the previous page.
`next_cursor` is `None` on the last page. A cursor from a different repository is rejected with
:class:`~debate_core.application.errors.InvalidCursor` rather than ignored.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from debate_core.domain import (
    Article,
    Card,
    HttpUrlStr,
    Search,
    SearchResult,
    Sha256Hex,
    SourceSnapshot,
    Ulid,
)

__all__ = [
    "DEFAULT_PAGE_SIZE",
    "ArticleRepository",
    "BlobKey",
    "CardRepository",
    "Page",
    "SearchRepository",
    "SnapshotStore",
]

#: Page size a repository uses when a caller does not ask for one.
DEFAULT_PAGE_SIZE = 50

BlobKey = Sha256Hex
"""The key a blob is stored under: the lowercase hex SHA-256 of its own bytes.

Content addressing is what makes :class:`SnapshotStore` implementations interchangeable and makes
a second write of identical bytes a no-op rather than a decision. `SourceSnapshot.raw_blob_key`
holds this value as ordinary text, so a future store with a different key scheme does not force an
entity migration.
"""


@dataclass(frozen=True, slots=True)
class Page[ItemT]:
    """One page of a listing, plus the cursor that continues it.

    Generic over the item type so `Page[Card]` and `Page[Search]` stay distinct to the type
    checker. It is a plain frozen dataclass rather than a Pydantic model: it carries already
    validated domain objects, so re-validating them on every page would cost without adding an
    invariant.
    """

    items: tuple[ItemT, ...]
    """The page's items, in the listing's documented order."""

    next_cursor: str | None = None
    """Opaque cursor for the next page, or `None` when this is the last page."""

    @property
    def has_more(self) -> bool:
        """True when another page can be fetched with :attr:`next_cursor`."""
        return self.next_cursor is not None


@runtime_checkable
class ArticleRepository(Protocol):
    """Stores articles, and the metadata of every snapshot taken of them.

    Snapshot *bytes* live in :class:`SnapshotStore`; a :class:`~debate_core.domain.SourceSnapshot`
    record is article-side metadata (which article, when retrieved, under which extractor and
    normalizer versions, and the blob keys), so it is stored here beside the article it describes.

    `save` is an upsert and is last-writer-wins: an article is a shared description of a public
    source that any retrieval may refresh, so it carries no `expected_revision` check. Cards are
    the records a student edits, and those are protected — see :class:`CardRepository`.
    """

    async def get(self, article_id: Ulid) -> Article:
        """Return the article with this id, or raise `NotFound`."""
        ...

    async def find_by_canonical_url(self, canonical_url: HttpUrlStr) -> Article | None:
        """Return the article stored under this canonical URL, or `None`.

        The canonical URL is the platform's deduplication key for a source, so this lookup is how
        a service decides whether a search result or a fetch is a source it already knows. The URL
        is matched byte for byte: canonicalization happens before the call (E04-t01), never here.

        Nothing makes the URL unique, so several articles may match. When they do, **the most
        recently created one wins** — `created_at` descending, `article_id` descending to break a
        tie — which is the same total order every `list_*` method uses. The rule is here rather
        than left to each implementation because "whichever row the database visited first" is not
        an answer a caller can depend on, and a deduplication key whose lookup is not reproducible
        deduplicates nothing. Whether a canonical URL *should* be unique per owner is an
        article-service question and belongs to v1-e04-t05; this port only promises that the
        answer is deterministic and the same everywhere.
        """
        ...

    async def save(self, article: Article) -> Article:
        """Insert or update the article and return it with `revision` incremented.

        Idempotent in the sense that saving the same article twice leaves one record; it is not a
        no-op, because the second save still bumps the revision.
        """
        ...

    async def delete(self, article_id: Ulid) -> None:
        """Delete the article, or raise `NotFound` if there is nothing to delete.

        Deleting is a rare, deliberate act — a source-removal request under
        `docs/policies/caselist-data-use.md` — so an unmatched delete is reported rather than
        silently accepted, and the caller can say what was and was not removed.
        """
        ...

    async def list_by_owner(
        self,
        owner_id: Ulid,
        *,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
    ) -> Page[Article]:
        """List one owner's articles, newest first. `limit` must be at least 1."""
        ...

    async def save_snapshot(self, snapshot: SourceSnapshot) -> SourceSnapshot:
        """Store the metadata of one retrieval and return it.

        Snapshots are immutable: saving one whose id is already stored raises `AlreadyExists`.
        Re-retrieving a source produces a new snapshot instead, which is what lets an old card
        stay verifiable against exactly the text it was cut from.
        """
        ...

    async def get_snapshot(self, snapshot_id: Ulid) -> SourceSnapshot:
        """Return the snapshot with this id, or raise `NotFound`."""
        ...

    async def list_snapshots(self, article_id: Ulid) -> tuple[SourceSnapshot, ...]:
        """Return every snapshot of one article, newest retrieval first.

        Unpaginated on purpose: one article accumulates a handful of snapshots, not a feed.
        """
        ...


@runtime_checkable
class SnapshotStore(Protocol):
    """Stores immutable blobs under the SHA-256 of their own content.

    This is the evidence system of record. The raw bytes of a retrieval and the normalized text
    derived from them are written here once and never rewritten, so a card's quotation can be
    reproduced and re-checked at any later date (architecture proposal §8).

    Content addressing gives three properties for free, and every implementation must keep them:

    * **Deduplication.** Identical bytes always produce the same key, so storing a source twice
      stores one blob.
    * **Idempotent writes.** A second `put` of bytes already stored is a no-op that returns the
      same key.
    * **Detectable corruption.** A read whose bytes do not hash to the key they are filed under
      raises :class:`~debate_core.application.errors.BlobIntegrityError` rather than returning
      text that a card would then be "verified" against.

    There is no `delete` and no overwrite. Removing a source under the removal runbook is an
    operator procedure against the store's backing bucket or directory, not something a use case
    can reach through this port.
    """

    async def put(self, data: bytes) -> BlobKey:
        """Store `data` and return its content-addressed key.

        Storing the same bytes again returns the same key and writes nothing.
        """
        ...

    async def get(self, key: BlobKey) -> bytes:
        """Return the bytes stored under `key`.

        Raises `NotFound` if the key was never written, and `BlobIntegrityError` if the stored
        bytes no longer hash to it.
        """
        ...

    async def exists(self, key: BlobKey) -> bool:
        """True when a blob is stored under `key`. Does not verify its integrity."""
        ...


@runtime_checkable
class CardRepository(Protocol):
    """Stores cards under optimistic concurrency.

    A card is the one entity two writers really do race for: a student edits a tag or moves an
    underline while a reprocessing job writes a model's suggestion back to the same card. Every
    update therefore states the `revision` it read, and the repository applies the write only if
    that revision is still the stored one (architecture proposal §7).

    Creating and updating are separate methods so neither can happen by accident: `create` refuses
    to overwrite, and `save` refuses to create.
    """

    async def get(self, card_id: Ulid) -> Card:
        """Return the card with this id, or raise `NotFound`."""
        ...

    async def find(self, card_id: Ulid) -> Card | None:
        """Return the card with this id, or `None` when it does not exist."""
        ...

    async def create(self, card: Card) -> Card:
        """Store a new card and return it at `revision` 1.

        Raises `AlreadyExists` if a card with that id is already stored.
        """
        ...

    async def save(self, card: Card, *, expected_revision: int) -> Card:
        """Update an existing card and return it with `revision` incremented.

        `expected_revision` is required and is the revision the caller read. If the stored
        revision differs, nothing is written and
        :class:`~debate_core.application.errors.RevisionMismatch` is raised carrying both
        revisions; the caller re-reads, re-applies and retries, or tells the user their copy is
        stale. Raises `NotFound` when no card with that id exists.
        """
        ...

    async def delete(self, card_id: Ulid, *, expected_revision: int) -> None:
        """Delete a card whose stored revision is `expected_revision`.

        Guarded like `save`, so deleting a card someone has edited since it was read fails with
        `RevisionMismatch` instead of discarding the edit.
        """
        ...

    async def list_by_owner(
        self,
        owner_id: Ulid,
        *,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
    ) -> Page[Card]:
        """List one student's cards, newest first."""
        ...

    async def list_by_article(
        self,
        article_id: Ulid,
        *,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
    ) -> Page[Card]:
        """List every card cut from one article, newest first."""
        ...


@runtime_checkable
class SearchRepository(Protocol):
    """Stores searches and their ranked results.

    Searches are kept rather than discarded once rendered, so a piece of research can be replayed
    and audited: which query, which filters, which providers answered, and what order the results
    came back in.

    Results are stored as a set per search rather than one at a time. A ranking is only meaningful
    as a whole, so `save_results` replaces the whole ranking and re-running it cannot leave a
    half-updated order behind.
    """

    async def get(self, search_id: Ulid) -> Search:
        """Return the search with this id, or raise `NotFound`."""
        ...

    async def save(self, search: Search) -> Search:
        """Insert or update the search record and return it with `revision` incremented."""
        ...

    async def save_results(self, search_id: Ulid, results: Sequence[SearchResult]) -> None:
        """Replace the stored ranking for one search.

        Raises `NotFound` when the search does not exist, and `ValueError` when a result's
        `search_id` does not match `search_id`, when two results claim the same rank, or when two
        results name the same article. All three are caller bugs, not storage conditions: a
        ranking is a total order over *distinct* articles, so one article holding two places is as
        meaningless as one rank holding two articles.

        A rejected call writes nothing. The checks run before the replacement starts, so a caller
        that hands over a malformed ranking still has the previous one stored.
        """
        ...

    async def list_results(self, search_id: Ulid) -> tuple[SearchResult, ...]:
        """Return one search's results ordered by `rank`, ascending.

        Returns an empty tuple for a search that stored no results; raises `NotFound` only when
        the search itself does not exist.
        """
        ...

    async def list_by_owner(
        self,
        owner_id: Ulid,
        *,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
    ) -> Page[Search]:
        """List one owner's searches, newest first."""
        ...
