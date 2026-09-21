"""What every `ArticleRepository`, `CardRepository` and `SearchRepository` must do.

Three contracts, one per record-storing port. Between them they state the rules a use case is
entitled to rely on no matter which adapter is wired in behind it (architecture proposal §7, §17):

* **Round-trip.** A stored entity comes back field for field, nested models and all. A repository
  that dropped a `CitationField`'s provenance, or re-encoded a timestamp, would be storing
  something that is not the entity it was handed.
* **Absence.** `get_*` raises :class:`~debate_core.application.errors.NotFound`; `find_*` returns
  `None`. Nothing returns a half-built entity.
* **Revisions.** The repository owns `revision`. A write returns the stored entity with the
  counter advanced, and the caller's own instance is untouched.
* **Optimistic concurrency.** A card is written only if the revision the caller read is still the
  stored one, so a reprocessing job cannot silently overwrite a student's edit.
* **Listing order and paging.** Newest first — `created_at` descending, entity id descending for
  ties — and a cursor walk that visits every record exactly once and then stops.

What is *not* here is anything an adapter is free to decide: how a cursor is spelled, which table
or key a row lands in, what a SQLite file looks like on disk. The spec for this task forbids
reaching into adapter internals, and those belong to the adapter's own test module.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest

from debate_core.application.errors import (
    AlreadyExists,
    InvalidCursor,
    NotFound,
    RevisionMismatch,
)
from debate_core.application.ports import ArticleRepository, CardRepository, SearchRepository
from debate_core.domain import Article, Card, Search, SearchStatus, Ulid
from debate_core.testing.builders import (
    DEFAULT_ARTICLE_ID,
    DEFAULT_CANONICAL_URL,
    DEFAULT_OWNER_ID,
    build_article,
    build_card,
    build_search,
    build_search_result,
    build_source_snapshot,
    readable_id,
)
from debate_core.testing.contracts.harness import (
    AdapterContract,
    ArticleRepositoryFactory,
    CardRepositoryFactory,
    SearchRepositoryFactory,
    walk_all_pages,
)
from debate_core.testing.fakes import FAKE_EPOCH

__all__ = [
    "ArticleRepositoryContract",
    "CardRepositoryContract",
    "SearchRepositoryContract",
]

#: A second owner, so every listing contract can prove it filters rather than returning everything.
OTHER_OWNER_ID = readable_id("WNER", 2)

#: A cursor no repository can have minted, for the `InvalidCursor` contracts.
FOREIGN_CURSOR = "not-a-cursor-this-repository-issued"

#: How many records the paging contracts store, and the page size they walk them at. Five at two
#: to a page is the smallest set that produces a short last page, which is where an off-by-one in
#: a new adapter shows up.
PAGED_RECORD_COUNT = 5
PAGE_SIZE = 2
EXPECTED_PAGE_COUNT = 3


def _minutes_after_epoch(minute: int) -> datetime:
    """A timestamp `minute` minutes after the fake epoch, so record order is stated, not guessed."""
    return FAKE_EPOCH + timedelta(minutes=minute)


# ================================================================================================
# Articles and their snapshots
# ================================================================================================


class ArticleRepositoryContract(AdapterContract):
    """Subclass this in a `Test…` class and override `make_adapter`."""

    @pytest.fixture
    def make_adapter(self) -> ArticleRepositoryFactory:
        """Return a factory handing out handles onto one empty article store.

        A binding must override this. See `README.md` in this directory.
        """
        raise NotImplementedError(
            "an ArticleRepositoryContract binding must override the `make_adapter` fixture "
            "with a factory returning handles onto one empty article store"
        )

    @pytest.fixture
    def repository(self, make_adapter: ArticleRepositoryFactory) -> ArticleRepository:
        """The repository under test."""
        return make_adapter()

    # ----------------------------------------------------------------------------------------
    # Reading back what was written
    # ----------------------------------------------------------------------------------------

    async def test_getting_an_unknown_article_raises_not_found(self, repository: ArticleRepository) -> None:
        with pytest.raises(NotFound) as refused:
            await repository.get(readable_id("ART", 99))

        assert refused.value.key == readable_id("ART", 99)

    async def test_a_saved_article_comes_back_field_for_field(self, repository: ArticleRepository) -> None:
        """Including the nested identifiers: a repository that flattened them would lose the DOI."""
        saved = await repository.save(build_article())

        assert await repository.get(saved.article_id) == saved

    async def test_the_first_save_stores_revision_one(self, repository: ArticleRepository) -> None:
        saved = await repository.save(build_article(revision=1))

        assert saved.revision == 1
        assert (await repository.get(saved.article_id)).revision == 1

    async def test_saving_again_updates_in_place_and_advances_the_revision(
        self, repository: ArticleRepository
    ) -> None:
        """An article is a shared description of a public source: any retrieval may refresh it."""
        first = await repository.save(build_article())

        second = await repository.save(first.evolve(title="Arctic methane release, revisited"))

        assert second.revision == 2
        stored = await repository.get(second.article_id)
        assert stored.title == "Arctic methane release, revisited"
        assert stored.revision == 2
        page = await repository.list_by_owner(DEFAULT_OWNER_ID)
        assert len(page.items) == 1, "an upsert must leave one record, not two"

    async def test_save_returns_the_stored_article_and_leaves_the_callers_copy_alone(
        self, repository: ArticleRepository
    ) -> None:
        """The revision belongs to the repository, so callers keep what `save` returned."""
        first = await repository.save(build_article())

        second = await repository.save(first)

        assert first.revision == 1, "the caller's instance must not be mutated"
        assert second.revision == 2

    async def test_a_second_handle_reads_what_the_first_stored(
        self, repository: ArticleRepository, make_adapter: ArticleRepositoryFactory
    ) -> None:
        saved = await repository.save(build_article())

        assert await make_adapter().get(saved.article_id) == saved

    # ----------------------------------------------------------------------------------------
    # Finding by canonical URL
    # ----------------------------------------------------------------------------------------

    async def test_find_by_canonical_url_returns_the_stored_article(
        self, repository: ArticleRepository
    ) -> None:
        saved = await repository.save(build_article())

        assert await repository.find_by_canonical_url(DEFAULT_CANONICAL_URL) == saved

    async def test_find_by_canonical_url_returns_none_when_no_article_has_that_url(
        self, repository: ArticleRepository
    ) -> None:
        """Absence is an ordinary answer here: it is how a service decides to fetch a new source."""
        await repository.save(build_article())

        assert await repository.find_by_canonical_url("https://example.org/ocean-heat") is None

    async def test_find_by_canonical_url_matches_byte_for_byte(self, repository: ArticleRepository) -> None:
        """Canonicalization happens before the call (E04-t01); a repository must not normalize."""
        await repository.save(build_article())

        assert await repository.find_by_canonical_url(f"{DEFAULT_CANONICAL_URL}/") is None

    async def test_find_by_canonical_url_returns_the_most_recently_created_match(
        self, repository: ArticleRepository
    ) -> None:
        """Nothing makes the URL unique, so the port names the winner rather than leaving it open.

        An implementation that returned whichever row it reached first would make the platform's
        deduplication key answer differently on SQLite and on DynamoDB, which is exactly the drift
        this suite exists to catch.
        """
        await repository.save(
            build_article(article_id=readable_id("ART", 1), created_at=_minutes_after_epoch(1))
        )
        newest = await repository.save(
            build_article(article_id=readable_id("ART", 2), created_at=_minutes_after_epoch(2))
        )

        assert await repository.find_by_canonical_url(DEFAULT_CANONICAL_URL) == newest

    async def test_find_by_canonical_url_breaks_ties_on_the_id_descending(
        self, repository: ArticleRepository
    ) -> None:
        """Same tie-break as every listing, so two articles stored in one millisecond still order."""
        await repository.save(build_article(article_id=readable_id("ART", 1), created_at=FAKE_EPOCH))
        highest_id = await repository.save(
            build_article(article_id=readable_id("ART", 2), created_at=FAKE_EPOCH)
        )

        assert await repository.find_by_canonical_url(DEFAULT_CANONICAL_URL) == highest_id

    # ----------------------------------------------------------------------------------------
    # Deleting
    # ----------------------------------------------------------------------------------------

    async def test_deleting_removes_the_article(self, repository: ArticleRepository) -> None:
        saved = await repository.save(build_article())

        await repository.delete(saved.article_id)

        with pytest.raises(NotFound):
            await repository.get(saved.article_id)

    async def test_deleting_an_article_that_is_not_there_raises_not_found(
        self, repository: ArticleRepository
    ) -> None:
        """A removal request has to be able to report what it did and did not remove."""
        with pytest.raises(NotFound):
            await repository.delete(readable_id("ART", 99))

    async def test_deleting_the_same_article_twice_raises_not_found_the_second_time(
        self, repository: ArticleRepository
    ) -> None:
        saved = await repository.save(build_article())
        await repository.delete(saved.article_id)

        with pytest.raises(NotFound):
            await repository.delete(saved.article_id)

    # ----------------------------------------------------------------------------------------
    # Listing one owner's articles
    # ----------------------------------------------------------------------------------------

    async def _store_articles(
        self, repository: ArticleRepository, count: int, *, owner_id: Ulid = DEFAULT_OWNER_ID
    ) -> tuple[Article, ...]:
        """Store `count` articles a minute apart and return them newest first, as a listing must."""
        stored = [
            await repository.save(
                build_article(
                    article_id=readable_id("ART", number),
                    owner_id=owner_id,
                    canonical_url=f"https://example.org/source-{number}",
                    created_at=_minutes_after_epoch(number),
                )
            )
            for number in range(1, count + 1)
        ]
        return tuple(reversed(stored))

    async def test_list_by_owner_returns_newest_first(self, repository: ArticleRepository) -> None:
        newest_first = await self._store_articles(repository, 3)

        page = await repository.list_by_owner(DEFAULT_OWNER_ID)

        assert page.items == newest_first
        assert page.next_cursor is None

    async def test_list_by_owner_breaks_ties_on_the_id_descending(
        self, repository: ArticleRepository
    ) -> None:
        """Identical timestamps must not let two records swap places between pages."""
        for number in (1, 2, 3):
            await repository.save(
                build_article(
                    article_id=readable_id("ART", number),
                    canonical_url=f"https://example.org/source-{number}",
                    created_at=FAKE_EPOCH,
                )
            )

        page = await repository.list_by_owner(DEFAULT_OWNER_ID)

        assert [article.article_id for article in page.items] == [
            readable_id("ART", 3),
            readable_id("ART", 2),
            readable_id("ART", 1),
        ]

    async def test_list_by_owner_returns_only_that_owners_articles(
        self, repository: ArticleRepository
    ) -> None:
        mine = await repository.save(build_article())
        await repository.save(
            build_article(
                article_id=readable_id("ART", 2),
                owner_id=OTHER_OWNER_ID,
                canonical_url="https://example.org/someone-elses-source",
            )
        )

        page = await repository.list_by_owner(DEFAULT_OWNER_ID)

        assert page.items == (mine,)

    async def test_list_by_owner_is_empty_for_an_owner_with_no_articles(
        self, repository: ArticleRepository
    ) -> None:
        await repository.save(build_article())

        page = await repository.list_by_owner(OTHER_OWNER_ID)

        assert page.items == ()
        assert page.next_cursor is None
        assert page.has_more is False

    async def test_list_by_owner_pages_through_every_article_exactly_once(
        self, repository: ArticleRepository
    ) -> None:
        newest_first = await self._store_articles(repository, PAGED_RECORD_COUNT)

        walked = await walk_all_pages(
            lambda cursor: repository.list_by_owner(DEFAULT_OWNER_ID, limit=PAGE_SIZE, cursor=cursor),
            expected_pages=EXPECTED_PAGE_COUNT,
        )

        assert walked == newest_first

    async def test_list_by_owner_ends_the_walk_when_the_last_page_is_full(
        self, repository: ArticleRepository
    ) -> None:
        """The off-by-one case: as many records as fit the pages exactly, so nothing follows."""
        newest_first = await self._store_articles(repository, PAGE_SIZE * 2)

        walked = await walk_all_pages(
            lambda cursor: repository.list_by_owner(DEFAULT_OWNER_ID, limit=PAGE_SIZE, cursor=cursor),
            expected_pages=2,
        )

        assert walked == newest_first

    async def test_list_by_owner_rejects_a_limit_below_one(self, repository: ArticleRepository) -> None:
        with pytest.raises(ValueError):
            await repository.list_by_owner(DEFAULT_OWNER_ID, limit=0)

    async def test_list_by_owner_rejects_a_cursor_it_did_not_mint(
        self, repository: ArticleRepository
    ) -> None:
        """A cursor from another repository is a bug, not a request to start from the beginning."""
        await self._store_articles(repository, 2)

        with pytest.raises(InvalidCursor):
            await repository.list_by_owner(DEFAULT_OWNER_ID, cursor=FOREIGN_CURSOR)

    # ----------------------------------------------------------------------------------------
    # Snapshots: article-side metadata, stored beside the article they describe
    # ----------------------------------------------------------------------------------------

    async def test_a_saved_snapshot_comes_back_field_for_field(self, repository: ArticleRepository) -> None:
        snapshot = build_source_snapshot()

        await repository.save_snapshot(snapshot)

        assert await repository.get_snapshot(snapshot.snapshot_id) == snapshot

    async def test_getting_an_unknown_snapshot_raises_not_found(self, repository: ArticleRepository) -> None:
        with pytest.raises(NotFound) as refused:
            await repository.get_snapshot(readable_id("SNAP", 99))

        assert refused.value.key == readable_id("SNAP", 99)

    async def test_saving_a_snapshot_id_twice_raises_already_exists(
        self, repository: ArticleRepository
    ) -> None:
        """Snapshots are immutable: re-retrieving a source is a new snapshot, never an update."""
        snapshot = build_source_snapshot()
        await repository.save_snapshot(snapshot)

        with pytest.raises(AlreadyExists) as refused:
            await repository.save_snapshot(snapshot.evolve(canonical_url="https://example.org/moved"))

        assert refused.value.key == snapshot.snapshot_id

    async def test_a_refused_snapshot_save_leaves_the_stored_snapshot_alone(
        self, repository: ArticleRepository
    ) -> None:
        snapshot = build_source_snapshot()
        await repository.save_snapshot(snapshot)

        with pytest.raises(AlreadyExists):
            await repository.save_snapshot(snapshot.evolve(canonical_url="https://example.org/moved"))

        assert await repository.get_snapshot(snapshot.snapshot_id) == snapshot

    async def test_list_snapshots_returns_the_newest_retrieval_first(
        self, repository: ArticleRepository
    ) -> None:
        for number in (1, 2, 3):
            await repository.save_snapshot(
                build_source_snapshot(
                    snapshot_id=readable_id("SNAP", number),
                    retrieved_at=_minutes_after_epoch(number),
                    raw_bytes=f"<html><body><p>retrieval {number}</p></body></html>".encode(),
                )
            )

        snapshots = await repository.list_snapshots(DEFAULT_ARTICLE_ID)

        assert [snapshot.snapshot_id for snapshot in snapshots] == [
            readable_id("SNAP", 3),
            readable_id("SNAP", 2),
            readable_id("SNAP", 1),
        ]

    async def test_list_snapshots_returns_only_that_articles_snapshots(
        self, repository: ArticleRepository
    ) -> None:
        mine = build_source_snapshot()
        await repository.save_snapshot(mine)
        await repository.save_snapshot(
            build_source_snapshot(
                snapshot_id=readable_id("SNAP", 2),
                article_id=readable_id("ART", 2),
                raw_bytes=b"<html><body><p>another source entirely</p></body></html>",
            )
        )

        assert await repository.list_snapshots(DEFAULT_ARTICLE_ID) == (mine,)

    async def test_list_snapshots_is_empty_for_an_article_with_none(
        self, repository: ArticleRepository
    ) -> None:
        """Empty rather than `NotFound`: an article that has never been fetched is a normal state."""
        assert await repository.list_snapshots(readable_id("ART", 99)) == ()


# ================================================================================================
# Cards
# ================================================================================================


class CardRepositoryContract(AdapterContract):
    """Subclass this in a `Test…` class and override `make_adapter`.

    The optimistic-concurrency rules are the reason this contract exists. Every implementation has
    to refuse a write whose `expected_revision` has moved, and has to refuse it *without writing
    anything*, because the write it would otherwise apply is a student's edit being discarded.
    """

    @pytest.fixture
    def make_adapter(self) -> CardRepositoryFactory:
        """Return a factory handing out handles onto one empty card store.

        A binding must override this. See `README.md` in this directory.
        """
        raise NotImplementedError(
            "a CardRepositoryContract binding must override the `make_adapter` fixture with a "
            "factory returning handles onto one empty card store"
        )

    @pytest.fixture
    def repository(self, make_adapter: CardRepositoryFactory) -> CardRepository:
        """The repository under test."""
        return make_adapter()

    # ----------------------------------------------------------------------------------------
    # Creating and reading
    # ----------------------------------------------------------------------------------------

    async def test_getting_an_unknown_card_raises_not_found(self, repository: CardRepository) -> None:
        with pytest.raises(NotFound) as refused:
            await repository.get(readable_id("CARD", 99))

        assert refused.value.key == readable_id("CARD", 99)

    async def test_finding_an_unknown_card_returns_none(self, repository: CardRepository) -> None:
        """`find` is for callers to whom absence is an answer, not a failure."""
        assert await repository.find(readable_id("CARD", 99)) is None

    async def test_a_created_card_comes_back_field_for_field(self, repository: CardRepository) -> None:
        """Including the cite: every `CitationField`'s value, source and verified flag survive."""
        created = await repository.create(build_card())

        assert await repository.get(created.card_id) == created
        assert await repository.find(created.card_id) == created
        assert created.citation.is_fully_verified is True

    async def test_create_stores_the_card_at_revision_one(self, repository: CardRepository) -> None:
        """The repository owns the counter, so a caller cannot start a card part-way up it."""
        created = await repository.create(build_card(revision=7))

        assert created.revision == 1
        assert (await repository.get(created.card_id)).revision == 1

    async def test_creating_a_card_id_twice_raises_already_exists(self, repository: CardRepository) -> None:
        card = build_card()
        await repository.create(card)

        with pytest.raises(AlreadyExists) as refused:
            await repository.create(card.evolve(tag="a different claim entirely"))

        assert refused.value.key == card.card_id

    async def test_a_refused_create_writes_nothing(self, repository: CardRepository) -> None:
        created = await repository.create(build_card())

        with pytest.raises(AlreadyExists):
            await repository.create(created.evolve(tag="a different claim entirely"))

        assert await repository.get(created.card_id) == created

    async def test_a_second_handle_reads_what_the_first_stored(
        self, repository: CardRepository, make_adapter: CardRepositoryFactory
    ) -> None:
        created = await repository.create(build_card())

        assert await make_adapter().get(created.card_id) == created

    # ----------------------------------------------------------------------------------------
    # Optimistic concurrency
    # ----------------------------------------------------------------------------------------

    async def test_saving_with_the_current_revision_advances_it(self, repository: CardRepository) -> None:
        created = await repository.create(build_card())

        saved = await repository.save(created.evolve(tag="a sharper claim"), expected_revision=1)

        assert saved.revision == 2
        stored = await repository.get(created.card_id)
        assert stored.tag == "a sharper claim"
        assert stored.revision == 2

    async def test_saving_a_card_that_is_not_stored_raises_not_found(
        self, repository: CardRepository
    ) -> None:
        """`save` updates and `create` inserts; neither does the other's job by accident."""
        with pytest.raises(NotFound):
            await repository.save(build_card(), expected_revision=1)

    async def test_saving_with_a_stale_revision_raises_revision_mismatch(
        self, repository: CardRepository
    ) -> None:
        created = await repository.create(build_card())
        await repository.save(created.evolve(tag="the edit that landed"), expected_revision=1)

        with pytest.raises(RevisionMismatch) as refused:
            await repository.save(created.evolve(tag="the edit that was too late"), expected_revision=1)

        assert refused.value.key == created.card_id
        assert refused.value.expected_revision == 1
        assert refused.value.actual_revision == 2

    async def test_a_refused_save_writes_nothing(self, repository: CardRepository) -> None:
        """The point of the whole mechanism: the edit that did land is still there afterwards."""
        created = await repository.create(build_card())
        landed = await repository.save(created.evolve(tag="the edit that landed"), expected_revision=1)

        with pytest.raises(RevisionMismatch):
            await repository.save(created.evolve(tag="the edit that was too late"), expected_revision=1)

        assert await repository.get(created.card_id) == landed

    async def test_two_writers_at_the_same_revision_produce_one_success_and_one_mismatch(
        self, repository: CardRepository, make_adapter: CardRepositoryFactory
    ) -> None:
        """The race this port exists for: a student's edit against a reprocessing job's write.

        Both writers read revision 1 and both write against it. Exactly one may win, and the loser
        must be told its copy is stale rather than have its write silently applied or dropped.
        """
        created = await repository.create(build_card())
        student, reprocessing_job = make_adapter(), make_adapter()

        outcomes = await asyncio.gather(
            student.save(created.evolve(tag="the student's edit"), expected_revision=1),
            reprocessing_job.save(created.evolve(tag="the job's suggestion"), expected_revision=1),
            return_exceptions=True,
        )

        winners = [outcome for outcome in outcomes if isinstance(outcome, Card)]
        losers = [outcome for outcome in outcomes if isinstance(outcome, RevisionMismatch)]
        assert len(winners) == 1, f"exactly one write may be applied, got {outcomes}"
        assert len(losers) == 1, f"the other write must raise RevisionMismatch, got {outcomes}"
        assert losers[0].expected_revision == 1
        assert losers[0].actual_revision == 2
        stored = await repository.get(created.card_id)
        assert stored == winners[0]
        assert stored.revision == 2

    # ----------------------------------------------------------------------------------------
    # Deleting, guarded the same way
    # ----------------------------------------------------------------------------------------

    async def test_deleting_with_the_current_revision_removes_the_card(
        self, repository: CardRepository
    ) -> None:
        created = await repository.create(build_card())

        await repository.delete(created.card_id, expected_revision=1)

        assert await repository.find(created.card_id) is None

    async def test_deleting_with_a_stale_revision_raises_and_keeps_the_card(
        self, repository: CardRepository
    ) -> None:
        """Deleting a card someone has edited since it was read must not discard that edit."""
        created = await repository.create(build_card())
        edited = await repository.save(created.evolve(tag="edited since you read it"), expected_revision=1)

        with pytest.raises(RevisionMismatch) as refused:
            await repository.delete(created.card_id, expected_revision=1)

        assert refused.value.actual_revision == 2
        assert await repository.get(created.card_id) == edited

    async def test_deleting_a_card_that_is_not_stored_raises_not_found(
        self, repository: CardRepository
    ) -> None:
        with pytest.raises(NotFound):
            await repository.delete(readable_id("CARD", 99), expected_revision=1)

    # ----------------------------------------------------------------------------------------
    # Listing
    # ----------------------------------------------------------------------------------------

    async def _store_cards(
        self,
        repository: CardRepository,
        count: int,
        *,
        owner_id: Ulid = DEFAULT_OWNER_ID,
        article_id: Ulid = DEFAULT_ARTICLE_ID,
    ) -> tuple[Card, ...]:
        """Store `count` cards a minute apart and return them newest first, as a listing must."""
        stored = [
            await repository.create(
                build_card(
                    card_id=readable_id("CARD", number),
                    owner_id=owner_id,
                    article_id=article_id,
                    created_at=_minutes_after_epoch(number),
                )
            )
            for number in range(1, count + 1)
        ]
        return tuple(reversed(stored))

    async def test_list_by_owner_returns_newest_first(self, repository: CardRepository) -> None:
        newest_first = await self._store_cards(repository, 3)

        page = await repository.list_by_owner(DEFAULT_OWNER_ID)

        assert page.items == newest_first
        assert page.next_cursor is None

    async def test_list_by_owner_breaks_ties_on_the_id_descending(self, repository: CardRepository) -> None:
        for number in (1, 2, 3):
            await repository.create(build_card(card_id=readable_id("CARD", number), created_at=FAKE_EPOCH))

        page = await repository.list_by_owner(DEFAULT_OWNER_ID)

        assert [card.card_id for card in page.items] == [
            readable_id("CARD", 3),
            readable_id("CARD", 2),
            readable_id("CARD", 1),
        ]

    async def test_list_by_owner_returns_only_that_students_cards(self, repository: CardRepository) -> None:
        """A card belongs to exactly one student, and a listing must not leak across owners."""
        mine = await repository.create(build_card())
        await repository.create(build_card(card_id=readable_id("CARD", 2), owner_id=OTHER_OWNER_ID))

        page = await repository.list_by_owner(DEFAULT_OWNER_ID)

        assert page.items == (mine,)

    async def test_list_by_owner_pages_through_every_card_exactly_once(
        self, repository: CardRepository
    ) -> None:
        newest_first = await self._store_cards(repository, PAGED_RECORD_COUNT)

        walked = await walk_all_pages(
            lambda cursor: repository.list_by_owner(DEFAULT_OWNER_ID, limit=PAGE_SIZE, cursor=cursor),
            expected_pages=EXPECTED_PAGE_COUNT,
        )

        assert walked == newest_first

    async def test_list_by_owner_rejects_a_limit_below_one(self, repository: CardRepository) -> None:
        with pytest.raises(ValueError):
            await repository.list_by_owner(DEFAULT_OWNER_ID, limit=0)

    async def test_list_by_owner_rejects_a_cursor_it_did_not_mint(self, repository: CardRepository) -> None:
        await self._store_cards(repository, 2)

        with pytest.raises(InvalidCursor):
            await repository.list_by_owner(DEFAULT_OWNER_ID, cursor=FOREIGN_CURSOR)

    async def test_list_by_article_returns_newest_first(self, repository: CardRepository) -> None:
        newest_first = await self._store_cards(repository, 3)

        page = await repository.list_by_article(DEFAULT_ARTICLE_ID)

        assert page.items == newest_first

    async def test_list_by_article_returns_only_that_articles_cards(self, repository: CardRepository) -> None:
        mine = await repository.create(build_card())
        await repository.create(build_card(card_id=readable_id("CARD", 2), article_id=readable_id("ART", 2)))

        page = await repository.list_by_article(DEFAULT_ARTICLE_ID)

        assert page.items == (mine,)

    async def test_list_by_article_pages_through_every_card_exactly_once(
        self, repository: CardRepository
    ) -> None:
        newest_first = await self._store_cards(repository, PAGED_RECORD_COUNT)

        walked = await walk_all_pages(
            lambda cursor: repository.list_by_article(DEFAULT_ARTICLE_ID, limit=PAGE_SIZE, cursor=cursor),
            expected_pages=EXPECTED_PAGE_COUNT,
        )

        assert walked == newest_first

    async def test_list_by_article_rejects_a_cursor_it_did_not_mint(self, repository: CardRepository) -> None:
        await self._store_cards(repository, 2)

        with pytest.raises(InvalidCursor):
            await repository.list_by_article(DEFAULT_ARTICLE_ID, cursor=FOREIGN_CURSOR)


# ================================================================================================
# Searches and their rankings
# ================================================================================================


class SearchRepositoryContract(AdapterContract):
    """Subclass this in a `Test…` class and override `make_adapter`.

    A ranking is stored and replaced as a whole. An order is only meaningful complete, so there is
    no "add one result" on this port, and re-running a search cannot leave half an old order
    behind.
    """

    @pytest.fixture
    def make_adapter(self) -> SearchRepositoryFactory:
        """Return a factory handing out handles onto one empty search store.

        A binding must override this. See `README.md` in this directory.
        """
        raise NotImplementedError(
            "a SearchRepositoryContract binding must override the `make_adapter` fixture with "
            "a factory returning handles onto one empty search store"
        )

    @pytest.fixture
    def repository(self, make_adapter: SearchRepositoryFactory) -> SearchRepository:
        """The repository under test."""
        return make_adapter()

    # ----------------------------------------------------------------------------------------
    # The search record
    # ----------------------------------------------------------------------------------------

    async def test_getting_an_unknown_search_raises_not_found(self, repository: SearchRepository) -> None:
        with pytest.raises(NotFound) as refused:
            await repository.get(readable_id("SRCH", 99))

        assert refused.value.key == readable_id("SRCH", 99)

    async def test_a_saved_search_comes_back_field_for_field(self, repository: SearchRepository) -> None:
        """Including the filters, so a search can be replayed exactly as it was run."""
        saved = await repository.save(build_search())

        assert await repository.get(saved.search_id) == saved

    async def test_the_first_save_stores_revision_one(self, repository: SearchRepository) -> None:
        saved = await repository.save(build_search(revision=1))

        assert saved.revision == 1

    async def test_saving_again_updates_in_place_and_advances_the_revision(
        self, repository: SearchRepository
    ) -> None:
        first = await repository.save(build_search())

        second = await repository.save(first.evolve(status=SearchStatus.PARTIAL))

        assert second.revision == 2
        stored = await repository.get(second.search_id)
        assert stored.status is SearchStatus.PARTIAL
        assert stored.revision == 2
        page = await repository.list_by_owner(DEFAULT_OWNER_ID)
        assert len(page.items) == 1, "an upsert must leave one record, not two"

    async def test_a_second_handle_reads_what_the_first_stored(
        self, repository: SearchRepository, make_adapter: SearchRepositoryFactory
    ) -> None:
        saved = await repository.save(build_search())

        assert await make_adapter().get(saved.search_id) == saved

    # ----------------------------------------------------------------------------------------
    # The ranking
    # ----------------------------------------------------------------------------------------

    async def test_a_stored_ranking_comes_back_in_rank_order(self, repository: SearchRepository) -> None:
        """Given out of order, returned in order: the ranking is the answer, not the insert order."""
        search = await repository.save(build_search())
        ranking = [build_search_result(search_id=search.search_id, rank=rank) for rank in (3, 1, 2)]

        await repository.save_results(search.search_id, ranking)

        stored = await repository.list_results(search.search_id)
        assert stored == tuple(sorted(ranking, key=lambda result: result.rank))

    async def test_saving_a_ranking_replaces_the_previous_one(self, repository: SearchRepository) -> None:
        """Re-running a search must not leave half of the old order behind."""
        search = await repository.save(build_search())
        await repository.save_results(
            search.search_id,
            [build_search_result(search_id=search.search_id, rank=rank) for rank in (1, 2, 3)],
        )

        replacement = [
            build_search_result(search_id=search.search_id, rank=1, article_id=readable_id("ART", 9))
        ]
        await repository.save_results(search.search_id, replacement)

        assert await repository.list_results(search.search_id) == tuple(replacement)

    async def test_saving_an_empty_ranking_clears_the_stored_one(self, repository: SearchRepository) -> None:
        search = await repository.save(build_search())
        await repository.save_results(
            search.search_id,
            [build_search_result(search_id=search.search_id, rank=rank) for rank in (1, 2)],
        )

        await repository.save_results(search.search_id, [])

        assert await repository.list_results(search.search_id) == ()

    async def test_list_results_is_empty_for_a_search_that_stored_none(
        self, repository: SearchRepository
    ) -> None:
        """A search that found nothing is a result, not a missing record."""
        search = await repository.save(build_search())

        assert await repository.list_results(search.search_id) == ()

    async def test_list_results_for_an_unknown_search_raises_not_found(
        self, repository: SearchRepository
    ) -> None:
        with pytest.raises(NotFound):
            await repository.list_results(readable_id("SRCH", 99))

    async def test_saving_results_for_an_unknown_search_raises_not_found(
        self, repository: SearchRepository
    ) -> None:
        unknown = readable_id("SRCH", 99)

        with pytest.raises(NotFound):
            await repository.save_results(unknown, [build_search_result(search_id=unknown)])

    async def test_saving_results_that_belong_to_another_search_is_rejected(
        self, repository: SearchRepository
    ) -> None:
        """A caller bug, not a storage condition, so it is a `ValueError` rather than a DomainError."""
        search = await repository.save(build_search())
        foreign = build_search_result(search_id=readable_id("SRCH", 2))

        with pytest.raises(ValueError):
            await repository.save_results(search.search_id, [foreign])

    async def test_saving_two_results_at_the_same_rank_is_rejected(
        self, repository: SearchRepository
    ) -> None:
        search = await repository.save(build_search())
        collision = [
            build_search_result(search_id=search.search_id, rank=1, article_id=readable_id("ART", 1)),
            build_search_result(search_id=search.search_id, rank=1, article_id=readable_id("ART", 2)),
        ]

        with pytest.raises(ValueError):
            await repository.save_results(search.search_id, collision)

    async def test_saving_two_results_naming_the_same_article_is_rejected(
        self, repository: SearchRepository
    ) -> None:
        """A ranking is a total order over distinct articles: one source cannot hold two places."""
        search = await repository.save(build_search())
        duplicate = [
            build_search_result(search_id=search.search_id, rank=1, article_id=readable_id("ART", 1)),
            build_search_result(search_id=search.search_id, rank=2, article_id=readable_id("ART", 1)),
        ]

        with pytest.raises(ValueError):
            await repository.save_results(search.search_id, duplicate)

    async def test_a_rejected_ranking_leaves_the_stored_one_intact(
        self, repository: SearchRepository
    ) -> None:
        search = await repository.save(build_search())
        accepted = [build_search_result(search_id=search.search_id, rank=rank) for rank in (1, 2)]
        await repository.save_results(search.search_id, accepted)

        with pytest.raises(ValueError):
            await repository.save_results(
                search.search_id,
                [
                    build_search_result(search_id=search.search_id, rank=1, article_id=readable_id("ART", 7)),
                    build_search_result(search_id=search.search_id, rank=1, article_id=readable_id("ART", 8)),
                ],
            )

        assert await repository.list_results(search.search_id) == tuple(accepted)

    # ----------------------------------------------------------------------------------------
    # Listing one owner's searches
    # ----------------------------------------------------------------------------------------

    async def _store_searches(
        self, repository: SearchRepository, count: int, *, owner_id: Ulid = DEFAULT_OWNER_ID
    ) -> tuple[Search, ...]:
        """Store `count` searches a minute apart and return them newest first."""
        stored = [
            await repository.save(
                build_search(
                    search_id=readable_id("SRCH", number),
                    owner_id=owner_id,
                    query=f"arctic methane feedback {number}",
                    created_at=_minutes_after_epoch(number),
                )
            )
            for number in range(1, count + 1)
        ]
        return tuple(reversed(stored))

    async def test_list_by_owner_returns_newest_first(self, repository: SearchRepository) -> None:
        newest_first = await self._store_searches(repository, 3)

        page = await repository.list_by_owner(DEFAULT_OWNER_ID)

        assert page.items == newest_first
        assert page.next_cursor is None

    async def test_list_by_owner_breaks_ties_on_the_id_descending(self, repository: SearchRepository) -> None:
        for number in (1, 2, 3):
            await repository.save(build_search(search_id=readable_id("SRCH", number), created_at=FAKE_EPOCH))

        page = await repository.list_by_owner(DEFAULT_OWNER_ID)

        assert [search.search_id for search in page.items] == [
            readable_id("SRCH", 3),
            readable_id("SRCH", 2),
            readable_id("SRCH", 1),
        ]

    async def test_list_by_owner_returns_only_that_owners_searches(
        self, repository: SearchRepository
    ) -> None:
        mine = await repository.save(build_search())
        await repository.save(build_search(search_id=readable_id("SRCH", 2), owner_id=OTHER_OWNER_ID))

        page = await repository.list_by_owner(DEFAULT_OWNER_ID)

        assert page.items == (mine,)

    async def test_list_by_owner_pages_through_every_search_exactly_once(
        self, repository: SearchRepository
    ) -> None:
        newest_first = await self._store_searches(repository, PAGED_RECORD_COUNT)

        walked = await walk_all_pages(
            lambda cursor: repository.list_by_owner(DEFAULT_OWNER_ID, limit=PAGE_SIZE, cursor=cursor),
            expected_pages=EXPECTED_PAGE_COUNT,
        )

        assert walked == newest_first

    async def test_list_by_owner_rejects_a_limit_below_one(self, repository: SearchRepository) -> None:
        with pytest.raises(ValueError):
            await repository.list_by_owner(DEFAULT_OWNER_ID, limit=0)

    async def test_list_by_owner_rejects_a_cursor_it_did_not_mint(self, repository: SearchRepository) -> None:
        await self._store_searches(repository, 2)

        with pytest.raises(InvalidCursor):
            await repository.list_by_owner(DEFAULT_OWNER_ID, cursor=FOREIGN_CURSOR)
