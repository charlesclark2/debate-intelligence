"""The SQLite repositories store what they are given, find it again, and refuse a stale write.

The adapter-specific half: that a row survives closing and reopening the file, that the JSON
column is revalidated on the way out, that a card's revision check is one conditional `UPDATE`
rather than a read followed by a hopeful write, and that a rejected call writes nothing. The
behaviour these share with every other implementation of the same ports — and with the in-memory
fakes — is the shared contract suite's, in v1-e02-t04-repo-contract-tests.

Every database is created under `tmp_path`; nothing here reaches a network or a real data
directory.
"""

from __future__ import annotations

from collections.abc import Coroutine, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

from debate_core.application.errors import (
    AlreadyExists,
    InvalidCursor,
    NotFound,
    RevisionMismatch,
)
from debate_core.application.ports import ArticleRepository, CardRepository, SearchRepository
from debate_core.domain import (
    AccessStatus,
    Article,
    ArticleIdentifiers,
    Card,
    CardSpan,
    Citation,
    CitationField,
    CitationFieldSource,
    ProvenanceMode,
    Search,
    SearchFilters,
    SearchResult,
    SearchStatus,
    SourceSnapshot,
    SourceType,
    SpanPurpose,
    SpanStyle,
    VerificationStatus,
    new_id,
)
from debate_core.integrations.local import (
    CorruptRecordError,
    SqliteArticleRepository,
    SqliteCardRepository,
    SqliteDatabase,
    SqliteSearchRepository,
)

EPOCH = datetime(2024, 1, 1, tzinfo=UTC)
DIGEST = "d" * 64
OTHER_DIGEST = "e" * 64


def run[ResultT](coroutine: Coroutine[Any, Any, ResultT]) -> ResultT:
    """Drive one repository call to completion; see `test_fs_blob_store.run` for why not asyncio."""
    try:
        coroutine.send(None)
    except StopIteration as finished:
        return cast("ResultT", finished.value)
    coroutine.close()
    raise AssertionError("a local adapter suspended; it is expected to do its I/O synchronously")


# --------------------------------------------------------------------------------------------
# Fixtures and builders
# --------------------------------------------------------------------------------------------


@pytest.fixture
def database(tmp_path: Path) -> Iterator[SqliteDatabase]:
    with SqliteDatabase.open(tmp_path) as opened:
        yield opened


@pytest.fixture
def articles(database: SqliteDatabase) -> SqliteArticleRepository:
    return SqliteArticleRepository(database)


@pytest.fixture
def cards(database: SqliteDatabase) -> SqliteCardRepository:
    return SqliteCardRepository(database)


@pytest.fixture
def searches(database: SqliteDatabase) -> SqliteSearchRepository:
    return SqliteSearchRepository(database)


def make_article(
    *,
    owner_id: str | None = None,
    url: str = "https://example.org/a",
    created_at: datetime = EPOCH,
    article_id: str | None = None,
) -> Article:
    return Article(
        article_id=article_id or new_id(),
        owner_id=owner_id,
        canonical_url=url,
        title=f"Article at {url}",
        created_at=created_at,
        updated_at=created_at,
    )


def make_card(
    *,
    owner_id: str,
    article_id: str | None = None,
    tag: str = "Warming is anthropogenic",
    created_at: datetime = EPOCH,
    card_id: str | None = None,
) -> Card:
    return Card(
        card_id=card_id or new_id(),
        owner_id=owner_id,
        article_id=article_id or new_id(),
        tag=tag,
        provenance_mode=ProvenanceMode.PUBLISHER_RETRIEVED,
        created_at=created_at,
        updated_at=created_at,
    )


def make_search(
    *, owner_id: str | None = None, query: str = "arctic methane", created_at: datetime = EPOCH
) -> Search:
    return Search(
        search_id=new_id(),
        owner_id=owner_id,
        query=query,
        status=SearchStatus.COMPLETE,
        created_at=created_at,
        updated_at=created_at,
    )


def make_snapshot(*, article_id: str, retrieved_at: datetime = EPOCH) -> SourceSnapshot:
    return SourceSnapshot(
        snapshot_id=new_id(),
        article_id=article_id,
        canonical_url="https://example.org/a",
        retrieved_at=retrieved_at,
        access_status=AccessStatus.ACCESSIBLE,
        provenance_mode=ProvenanceMode.PUBLISHER_RETRIEVED,
        raw_blob_key=DIGEST,
        normalized_blob_key=OTHER_DIGEST,
        sha256=DIGEST,
        normalized_text_hash=OTHER_DIGEST,
        extractor_version="test-extractor-1.0.0",
        normalizer_version="test-normalizer-1.0.0",
    )


# --------------------------------------------------------------------------------------------
# The adapters really are their ports
# --------------------------------------------------------------------------------------------


def test_each_adapter_satisfies_its_port(database: SqliteDatabase) -> None:
    """Annotated with the Protocols, so pyright fails here if an adapter drifts from its port.

    The same guard `build_fake_ports` gives the fakes. `isinstance` adds the runtime half: these
    are `runtime_checkable` Protocols, so it confirms the methods exist under the right names.
    """
    article_repository: ArticleRepository = SqliteArticleRepository(database)
    card_repository: CardRepository = SqliteCardRepository(database)
    search_repository: SearchRepository = SqliteSearchRepository(database)

    assert isinstance(article_repository, ArticleRepository)
    assert isinstance(card_repository, CardRepository)
    assert isinstance(search_repository, SearchRepository)


# --------------------------------------------------------------------------------------------
# Articles
# --------------------------------------------------------------------------------------------


def test_an_article_survives_a_save_and_a_reopen(tmp_path: Path) -> None:
    """The point of a file-backed repository: what was written is still there next command."""
    with SqliteDatabase.open(tmp_path) as first:
        saved = run(SqliteArticleRepository(first).save(make_article(url="https://example.org/a")))

    with SqliteDatabase.open(tmp_path) as second:
        assert run(SqliteArticleRepository(second).get(saved.article_id)) == saved


def test_every_field_survives_the_json_round_trip(articles: SqliteArticleRepository) -> None:
    rich = Article(
        article_id=new_id(),
        owner_id=new_id(),
        organization_id=new_id(),
        canonical_url="https://example.org/study?id=7",
        title="Methane release from Arctic permafrost",
        authors=("Ada Lovelace", "Grace Hopper"),
        publication="Nature",
        published_at=datetime(2023, 6, 1, 12, 30, tzinfo=UTC),
        source_type=SourceType.SCHOLARLY,
        access_status=AccessStatus.ACCESSIBLE,
        identifiers=ArticleIdentifiers(doi="10.1038/nature12373", pmid="23883933"),
        created_at=EPOCH,
        updated_at=EPOCH + timedelta(hours=3),
    )

    saved = run(articles.save(rich))

    assert run(articles.get(rich.article_id)) == saved
    assert saved == rich.evolve(revision=1)


def test_saving_increments_the_revision_and_leaves_the_timestamps_alone(
    articles: SqliteArticleRepository,
) -> None:
    saved = run(articles.save(make_article()))
    resaved = run(articles.save(saved.evolve(title="Corrected title")))

    assert saved.revision == 1
    assert resaved.revision == 2
    assert resaved.created_at == saved.created_at
    assert resaved.updated_at == saved.updated_at
    assert run(articles.get(saved.article_id)).title == "Corrected title"


def test_get_reports_an_unknown_article(articles: SqliteArticleRepository) -> None:
    missing = new_id()

    with pytest.raises(NotFound) as caught:
        run(articles.get(missing))

    assert caught.value.entity == "Article"
    assert caught.value.key == missing


def test_find_by_canonical_url_matches_byte_for_byte(articles: SqliteArticleRepository) -> None:
    saved = run(articles.save(make_article(url="https://example.org/a?utm_source=x")))

    assert run(articles.find_by_canonical_url("https://example.org/a?utm_source=x")) == saved
    assert run(articles.find_by_canonical_url("https://example.org/a")) is None


def test_deleting_an_article(articles: SqliteArticleRepository) -> None:
    saved = run(articles.save(make_article()))

    run(articles.delete(saved.article_id))

    with pytest.raises(NotFound):
        run(articles.get(saved.article_id))
    with pytest.raises(NotFound):
        run(articles.delete(saved.article_id))


def test_a_hand_edited_row_is_reported_rather_than_returned(
    articles: SqliteArticleRepository, database: SqliteDatabase
) -> None:
    saved = run(articles.save(make_article()))
    database.connection.execute(
        "UPDATE articles SET document = ? WHERE article_id = ?",
        ('{"article_id": "not a ULID"}', saved.article_id),
    )

    with pytest.raises(CorruptRecordError) as caught:
        run(articles.get(saved.article_id))

    assert caught.value.entity == "Article"
    assert caught.value.key == saved.article_id


# --------------------------------------------------------------------------------------------
# Listing and pagination
# --------------------------------------------------------------------------------------------


def test_listings_are_newest_first_and_filtered_by_owner(
    articles: SqliteArticleRepository,
) -> None:
    owner = new_id()
    oldest = run(articles.save(make_article(owner_id=owner, url="https://example.org/1")))
    newest = run(
        articles.save(
            make_article(owner_id=owner, url="https://example.org/2", created_at=EPOCH + timedelta(days=1))
        )
    )
    run(articles.save(make_article(owner_id=new_id(), url="https://example.org/3")))

    page = run(articles.list_by_owner(owner))

    assert page.items == (newest, oldest)
    assert page.next_cursor is None
    assert page.has_more is False


def test_identical_timestamps_are_broken_by_id_descending(
    articles: SqliteArticleRepository,
) -> None:
    """Two records created in the same microsecond must not be able to swap places between pages."""
    owner = new_id()
    lower = run(
        articles.save(
            make_article(owner_id=owner, url="https://example.org/1", article_id="01J" + "0" * 22 + "1")
        )
    )
    higher = run(
        articles.save(
            make_article(owner_id=owner, url="https://example.org/2", article_id="01J" + "0" * 22 + "2")
        )
    )

    assert run(articles.list_by_owner(owner)).items == (higher, lower)


def test_pagination_walks_every_record_once(articles: SqliteArticleRepository) -> None:
    owner = new_id()
    for index in range(5):
        run(
            articles.save(
                make_article(
                    owner_id=owner,
                    url=f"https://example.org/{index}",
                    created_at=EPOCH + timedelta(days=index),
                )
            )
        )

    first = run(articles.list_by_owner(owner, limit=2))
    second = run(articles.list_by_owner(owner, limit=2, cursor=first.next_cursor))
    third = run(articles.list_by_owner(owner, limit=2, cursor=second.next_cursor))

    assert first.has_more and second.has_more
    assert third.next_cursor is None
    walked = first.items + second.items + third.items
    assert len(walked) == 5
    assert len({article.article_id for article in walked}) == 5
    assert [article.created_at for article in walked] == sorted(
        (article.created_at for article in walked), reverse=True
    )


def test_a_full_last_page_reports_no_more(articles: SqliteArticleRepository) -> None:
    owner = new_id()
    for index in range(4):
        run(
            articles.save(
                make_article(
                    owner_id=owner,
                    url=f"https://example.org/{index}",
                    created_at=EPOCH + timedelta(days=index),
                )
            )
        )

    first = run(articles.list_by_owner(owner, limit=2))
    second = run(articles.list_by_owner(owner, limit=2, cursor=first.next_cursor))

    assert len(second.items) == 2
    assert second.next_cursor is None


def test_a_cursor_from_another_listing_is_refused(articles: SqliteArticleRepository) -> None:
    owner = new_id()
    run(articles.save(make_article(owner_id=owner)))

    with pytest.raises(InvalidCursor):
        run(articles.list_by_owner(owner, cursor="card:" + new_id()))
    with pytest.raises(InvalidCursor):
        run(articles.list_by_owner(owner, cursor="article:" + new_id()))
    with pytest.raises(InvalidCursor):
        run(articles.list_by_owner(owner, cursor="nonsense"))


def test_a_listing_needs_a_positive_limit(articles: SqliteArticleRepository) -> None:
    with pytest.raises(ValueError, match="limit must be at least 1"):
        run(articles.list_by_owner(new_id(), limit=0))


def test_listing_an_owner_with_nothing_stored(articles: SqliteArticleRepository) -> None:
    page = run(articles.list_by_owner(new_id()))

    assert page.items == ()
    assert page.next_cursor is None


# --------------------------------------------------------------------------------------------
# Snapshots, stored through the article repository
# --------------------------------------------------------------------------------------------


def test_snapshots_are_immutable(articles: SqliteArticleRepository) -> None:
    article = run(articles.save(make_article()))
    snapshot = run(articles.save_snapshot(make_snapshot(article_id=article.article_id)))

    assert run(articles.get_snapshot(snapshot.snapshot_id)) == snapshot
    with pytest.raises(AlreadyExists) as caught:
        run(articles.save_snapshot(snapshot))
    assert caught.value.entity == "SourceSnapshot"


def test_snapshots_of_one_article_come_back_newest_retrieval_first(
    articles: SqliteArticleRepository,
) -> None:
    article = run(articles.save(make_article()))
    older = run(articles.save_snapshot(make_snapshot(article_id=article.article_id)))
    newer = run(
        articles.save_snapshot(
            make_snapshot(article_id=article.article_id, retrieved_at=EPOCH + timedelta(days=2))
        )
    )
    run(articles.save_snapshot(make_snapshot(article_id=new_id())))

    assert run(articles.list_snapshots(article.article_id)) == (newer, older)


def test_get_snapshot_reports_an_unknown_id(articles: SqliteArticleRepository) -> None:
    with pytest.raises(NotFound):
        run(articles.get_snapshot(new_id()))


def test_listing_snapshots_of_an_article_with_none(articles: SqliteArticleRepository) -> None:
    assert run(articles.list_snapshots(new_id())) == ()


# --------------------------------------------------------------------------------------------
# Cards and the revision check
# --------------------------------------------------------------------------------------------


def test_a_card_is_created_at_revision_one(cards: SqliteCardRepository) -> None:
    created = run(cards.create(make_card(owner_id=new_id())))

    assert created.revision == 1
    assert run(cards.get(created.card_id)) == created
    assert run(cards.find(created.card_id)) == created


def test_create_refuses_to_overwrite(cards: SqliteCardRepository) -> None:
    card = run(cards.create(make_card(owner_id=new_id())))

    with pytest.raises(AlreadyExists) as caught:
        run(cards.create(card))

    assert caught.value.key == card.card_id


def test_find_returns_none_and_get_raises(cards: SqliteCardRepository) -> None:
    missing = new_id()

    assert run(cards.find(missing)) is None
    with pytest.raises(NotFound):
        run(cards.get(missing))


def test_a_card_with_evidence_and_spans_round_trips(cards: SqliteCardRepository) -> None:
    evidence = "Permafrost is thawing faster than models predicted, releasing methane."
    card = Card(
        card_id=new_id(),
        owner_id=new_id(),
        organization_id=new_id(),
        article_id=new_id(),
        snapshot_id=new_id(),
        tag="Permafrost thaw is accelerating",
        citation=Citation(
            title=CitationField[str](
                value="Methane release from Arctic permafrost",
                source=CitationFieldSource.META_TAG,
                verified=True,
                raw="<meta name='citation_title' …>",
            ),
        ),
        evidence_text=evidence,
        evidence_start_offset=1200,
        evidence_end_offset=1200 + len(evidence),
        normalized_text_hash=DIGEST,
        normalizer_version="test-normalizer-1.0.0",
        spans=(
            CardSpan(start_offset=0, end_offset=10, style=SpanStyle.UNDERLINE),
            CardSpan(
                start_offset=11,
                end_offset=30,
                style=SpanStyle.HIGHLIGHT,
                purpose=SpanPurpose.WARRANT,
            ),
        ),
        verification_status=VerificationStatus.VERIFIED,
        provenance_mode=ProvenanceMode.PUBLISHER_RETRIEVED,
        created_at=EPOCH,
        updated_at=EPOCH,
    )

    created = run(cards.create(card))
    reread = run(cards.get(card.card_id))

    assert reread == created
    assert reread.spans == card.spans
    assert reread.evidence_text == evidence
    assert reread.citation.title.verified is True


def test_saving_a_card_needs_the_revision_that_was_read(cards: SqliteCardRepository) -> None:
    created = run(cards.create(make_card(owner_id=new_id())))

    saved = run(cards.save(created.evolve(tag="Edited once"), expected_revision=created.revision))

    assert saved.revision == 2
    assert run(cards.get(created.card_id)).tag == "Edited once"


def test_a_stale_write_is_refused_and_changes_nothing(cards: SqliteCardRepository) -> None:
    """The reprocessing job must not overwrite the student's edit (architecture proposal §7)."""
    created = run(cards.create(make_card(owner_id=new_id(), tag="Original")))
    read_by_the_student = created
    read_by_the_job = created

    run(cards.save(read_by_the_student.evolve(tag="Student edit"), expected_revision=1))

    with pytest.raises(RevisionMismatch) as caught:
        run(cards.save(read_by_the_job.evolve(tag="Model suggestion"), expected_revision=1))

    assert caught.value.entity == "Card"
    assert caught.value.key == created.card_id
    assert caught.value.expected_revision == 1
    assert caught.value.actual_revision == 2
    stored = run(cards.get(created.card_id))
    assert stored.tag == "Student edit"
    assert stored.revision == 2


def test_saving_a_card_that_is_gone_reports_not_found(cards: SqliteCardRepository) -> None:
    card = make_card(owner_id=new_id())

    with pytest.raises(NotFound):
        run(cards.save(card, expected_revision=1))


def test_deleting_a_card_is_guarded_too(cards: SqliteCardRepository) -> None:
    created = run(cards.create(make_card(owner_id=new_id())))
    run(cards.save(created.evolve(tag="Edited"), expected_revision=1))

    with pytest.raises(RevisionMismatch):
        run(cards.delete(created.card_id, expected_revision=1))
    assert run(cards.find(created.card_id)) is not None

    run(cards.delete(created.card_id, expected_revision=2))
    assert run(cards.find(created.card_id)) is None

    with pytest.raises(NotFound):
        run(cards.delete(created.card_id, expected_revision=2))


def test_cards_list_by_owner_and_by_article(cards: SqliteCardRepository) -> None:
    owner = new_id()
    article = new_id()
    mine_on_this_article = run(
        cards.create(make_card(owner_id=owner, article_id=article, tag="Mine, this article"))
    )
    mine_elsewhere = run(
        cards.create(
            make_card(
                owner_id=owner,
                article_id=new_id(),
                tag="Mine, another article",
                created_at=EPOCH + timedelta(days=1),
            )
        )
    )
    someone_elses = run(cards.create(make_card(owner_id=new_id(), article_id=article, tag="Not mine")))

    by_owner = run(cards.list_by_owner(owner))
    by_article = run(cards.list_by_article(article))

    assert by_owner.items == (mine_elsewhere, mine_on_this_article)
    # Both were created at the same instant, so the id tie-break decides the order between them.
    assert {card.card_id for card in by_article.items} == {
        mine_on_this_article.card_id,
        someone_elses.card_id,
    }
    assert [card.card_id for card in by_article.items] == sorted(
        (card.card_id for card in by_article.items), reverse=True
    )


# --------------------------------------------------------------------------------------------
# Searches and their rankings
# --------------------------------------------------------------------------------------------


def test_a_search_round_trips_with_its_filters(searches: SqliteSearchRepository) -> None:
    search = Search(
        search_id=new_id(),
        owner_id=new_id(),
        query="arctic methane feedback",
        filters=SearchFilters(
            since=datetime(2020, 1, 1, tzinfo=UTC),
            source_types=(SourceType.SCHOLARLY, SourceType.GOVERNMENT),
            max_results=50,
            language="en",
        ),
        provider_set=("openalex", "semantic-scholar"),
        status=SearchStatus.PARTIAL,
        created_at=EPOCH,
        updated_at=EPOCH,
    )

    saved = run(searches.save(search))

    assert run(searches.get(search.search_id)) == saved
    assert saved.filters == search.filters
    assert saved.provider_set == search.provider_set


def test_saving_a_search_increments_its_revision(searches: SqliteSearchRepository) -> None:
    saved = run(searches.save(make_search()))
    resaved = run(searches.save(saved.evolve(status=SearchStatus.PARTIAL)))

    assert (saved.revision, resaved.revision) == (1, 2)
    assert run(searches.get(saved.search_id)).status is SearchStatus.PARTIAL


def test_get_reports_an_unknown_search(searches: SqliteSearchRepository) -> None:
    with pytest.raises(NotFound):
        run(searches.get(new_id()))


def test_a_ranking_is_stored_and_read_back_in_rank_order(
    searches: SqliteSearchRepository,
) -> None:
    search = run(searches.save(make_search()))
    third = SearchResult(
        search_id=search.search_id,
        article_id=new_id(),
        rank=3,
        total_score=0.4,
        source_quality_features={"recency": 0.2, "peer_reviewed": 1.0},
        explanation="peer-reviewed, older",
        providers=("openalex",),
    )
    first = SearchResult(
        search_id=search.search_id,
        article_id=new_id(),
        rank=1,
        total_score=0.9,
        lexical_score=0.8,
        source_quality_features={"recency": 0.9},
        explanation="recent (3 days), peer-reviewed",
        providers=("openalex", "semantic-scholar"),
    )

    run(searches.save_results(search.search_id, [third, first]))

    stored = run(searches.list_results(search.search_id))
    assert [result.rank for result in stored] == [1, 3]
    assert stored[0] == first
    assert stored[0].source_quality_features == {"recency": 0.9}


def test_saving_a_ranking_replaces_the_previous_one(searches: SqliteSearchRepository) -> None:
    search = run(searches.save(make_search()))
    stale = [SearchResult(search_id=search.search_id, article_id=new_id(), rank=rank) for rank in (1, 2, 3)]
    run(searches.save_results(search.search_id, stale))

    fresh = [SearchResult(search_id=search.search_id, article_id=new_id(), rank=1)]
    run(searches.save_results(search.search_id, fresh))

    assert run(searches.list_results(search.search_id)) == tuple(fresh)


def test_a_search_with_no_results_lists_nothing(searches: SqliteSearchRepository) -> None:
    search = run(searches.save(make_search()))

    assert run(searches.list_results(search.search_id)) == ()


def test_results_for_an_unknown_search_are_reported(searches: SqliteSearchRepository) -> None:
    missing = new_id()

    with pytest.raises(NotFound):
        run(searches.list_results(missing))
    with pytest.raises(NotFound):
        run(searches.save_results(missing, []))


def test_a_ranking_that_is_not_this_searchs_is_rejected_before_anything_is_written(
    searches: SqliteSearchRepository,
) -> None:
    search = run(searches.save(make_search()))
    good = [SearchResult(search_id=search.search_id, article_id=new_id(), rank=1)]
    run(searches.save_results(search.search_id, good))

    article = new_id()
    rejected: list[list[SearchResult]] = [
        [SearchResult(search_id=new_id(), article_id=new_id(), rank=1)],
        [
            SearchResult(search_id=search.search_id, article_id=new_id(), rank=1),
            SearchResult(search_id=search.search_id, article_id=new_id(), rank=1),
        ],
        [
            SearchResult(search_id=search.search_id, article_id=article, rank=1),
            SearchResult(search_id=search.search_id, article_id=article, rank=2),
        ],
    ]
    for results in rejected:
        with pytest.raises(ValueError, match="search"):
            run(searches.save_results(search.search_id, results))

    assert run(searches.list_results(search.search_id)) == tuple(good)


def test_searches_list_by_owner_newest_first(searches: SqliteSearchRepository) -> None:
    owner = new_id()
    older = run(searches.save(make_search(owner_id=owner, query="first")))
    newer = run(
        searches.save(make_search(owner_id=owner, query="second", created_at=EPOCH + timedelta(hours=1)))
    )
    run(searches.save(make_search(owner_id=new_id(), query="someone else")))

    assert run(searches.list_by_owner(owner)).items == (newer, older)


# --------------------------------------------------------------------------------------------
# The repositories share one database
# --------------------------------------------------------------------------------------------


def test_every_repository_shares_one_connection_and_one_file(
    database: SqliteDatabase,
    articles: SqliteArticleRepository,
    cards: SqliteCardRepository,
    searches: SqliteSearchRepository,
) -> None:
    article = run(articles.save(make_article(owner_id=new_id())))
    card = run(cards.create(make_card(owner_id=new_id(), article_id=article.article_id)))
    run(searches.save(make_search()))

    counted = database.connection.execute(
        "SELECT (SELECT COUNT(*) FROM articles) AS articles, "
        "(SELECT COUNT(*) FROM cards) AS cards, "
        "(SELECT COUNT(*) FROM searches) AS searches"
    ).fetchone()

    assert (counted["articles"], counted["cards"], counted["searches"]) == (1, 1, 1)
    assert run(cards.list_by_article(article.article_id)).items == (card,)
    assert len(list(database.path.parent.glob("*.sqlite3"))) == 1


def test_a_refused_create_leaves_the_stored_card_exactly_as_it_was(
    cards: SqliteCardRepository,
) -> None:
    """The insert and its transaction are one unit: a rejected write changes nothing at all."""
    created = run(cards.create(make_card(owner_id=new_id(), tag="Original")))

    with pytest.raises(AlreadyExists):
        run(cards.create(created.evolve(tag="Would have clobbered the original")))

    stored = run(cards.get(created.card_id))
    assert stored.tag == "Original"
    assert stored.revision == 1
    assert run(cards.list_by_owner(created.owner_id)).items == (created,)


def test_a_refused_snapshot_leaves_the_stored_one_exactly_as_it_was(
    articles: SqliteArticleRepository,
) -> None:
    article = run(articles.save(make_article()))
    snapshot = run(articles.save_snapshot(make_snapshot(article_id=article.article_id)))

    with pytest.raises(AlreadyExists):
        run(articles.save_snapshot(snapshot.evolve(extractor_version="a-different-extractor")))

    assert run(articles.get_snapshot(snapshot.snapshot_id)) == snapshot
    assert run(articles.list_snapshots(article.article_id)) == (snapshot,)
