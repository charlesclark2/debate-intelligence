"""The in-memory fakes really behave like the adapters they stand in for.

These tests exist because a fake that quietly does *less* than the real thing is worse than no
fake: a test suite that passes against a card repository which does not enforce its revision check
would tell us the edit-protection works when it does not. So the behaviour each port promises —
dedupe, immutability, revision conflicts, listing order, structured-output validation — is checked
here, against the fake, exactly as the shared contract suite (v1-e02-t04-repo-contract-tests) will
later check it against SQLite, the filesystem, DynamoDB and S3.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from pydantic import BaseModel

from debate_core.application.errors import (
    AlreadyExists,
    BlobIntegrityError,
    InvalidCursor,
    InvalidModelOutput,
    NotFound,
    ProviderUnavailable,
    RevisionMismatch,
)
from debate_core.application.ports import (
    CandidateResult,
    ModelTaskClass,
    ProviderQuery,
)
from debate_core.domain import (
    ULID_PATTERN,
    AccessStatus,
    Article,
    Card,
    ProvenanceMode,
    Search,
    SearchFilters,
    SearchResult,
    SearchStatus,
    SourceSnapshot,
    new_id,
)
from debate_core.testing import (
    FAKE_EPOCH,
    FakeArticleFetcher,
    FakeContentExtractor,
    FakeModelRouter,
    FakeSearchProvider,
    FixedClock,
    InMemoryArticleRepository,
    InMemoryCardRepository,
    InMemorySearchRepository,
    InMemorySnapshotStore,
    SequentialIdGenerator,
    build_fake_ports,
)


def run[ResultT](coroutine: Coroutine[Any, Any, ResultT]) -> ResultT:
    """Drive one coroutine to completion without an event loop.

    The ports are `async` because their real implementations are I/O-bound, but the fakes never
    await anything, so a single `send(None)` runs one to completion. That is also an assertion
    worth making: a fake that suspended would be doing real I/O, which is the one thing these
    doubles exist to avoid. `asyncio.run` is not used because it opens a socket pair for its
    self-pipe, and the suite runs with `--disable-socket`.

    When the first genuinely concurrent test arrives — the contract suites in
    v1-e02-t04-repo-contract-tests are the likely place — it brings an async test plugin with it
    and this helper goes away. See the session report's follow-up work.
    """
    try:
        coroutine.send(None)
    except StopIteration as stopped:
        return cast("ResultT", stopped.value)
    coroutine.close()
    raise AssertionError("an in-memory fake suspended; fakes must not perform real I/O")


# --------------------------------------------------------------------------------------------
# Builders. The shared entity builders are v1-e02-t04-repo-contract-tests; these are local.
# --------------------------------------------------------------------------------------------


def make_article(*, owner_id: str | None = None, url: str, created_at: datetime | None = None) -> Article:
    return Article(
        article_id=new_id(),
        owner_id=owner_id,
        canonical_url=url,
        title=f"Article at {url}",
        created_at=created_at or FAKE_EPOCH,
        updated_at=created_at or FAKE_EPOCH,
    )


def make_card(
    *, owner_id: str, article_id: str, tag: str = "A tag", created_at: datetime | None = None
) -> Card:
    return Card(
        card_id=new_id(),
        owner_id=owner_id,
        article_id=article_id,
        tag=tag,
        provenance_mode=ProvenanceMode.PUBLISHER_RETRIEVED,
        created_at=created_at or FAKE_EPOCH,
        updated_at=created_at or FAKE_EPOCH,
    )


def make_search(*, owner_id: str | None = None, query: str = "arctic methane") -> Search:
    return Search(
        search_id=new_id(),
        owner_id=owner_id,
        query=query,
        status=SearchStatus.COMPLETE,
        created_at=FAKE_EPOCH,
        updated_at=FAKE_EPOCH,
    )


def make_snapshot(*, article_id: str, retrieved_at: datetime, digest: str) -> SourceSnapshot:
    return SourceSnapshot(
        snapshot_id=new_id(),
        article_id=article_id,
        canonical_url="https://example.org/a",
        retrieved_at=retrieved_at,
        access_status=AccessStatus.ACCESSIBLE,
        provenance_mode=ProvenanceMode.PUBLISHER_RETRIEVED,
        raw_blob_key=digest,
        normalized_blob_key=digest,
        sha256=digest,
        normalized_text_hash=digest,
        extractor_version="fake-1.0.0",
        normalizer_version="fake-1.0.0",
    )


DIGEST = hashlib.sha256(b"body").hexdigest()


# --------------------------------------------------------------------------------------------
# InMemoryArticleRepository
# --------------------------------------------------------------------------------------------


def test_article_get_raises_not_found_and_find_returns_none() -> None:
    articles = InMemoryArticleRepository()
    missing = new_id()
    with pytest.raises(NotFound) as caught:
        run(articles.get(missing))
    assert caught.value.entity == "Article"
    assert caught.value.key == missing
    assert run(articles.find_by_canonical_url("https://example.org/nothing")) is None


def test_article_save_is_an_upsert_that_bumps_the_revision() -> None:
    articles = InMemoryArticleRepository()
    saved = run(articles.save(make_article(url="https://example.org/a")))
    assert saved.revision == 1

    resaved = run(articles.save(saved.evolve(title="Corrected title")))
    assert resaved.revision == 2
    assert resaved.title == "Corrected title"
    assert run(articles.get(saved.article_id)).revision == 2


def test_article_lookup_by_canonical_url_is_exact() -> None:
    articles = InMemoryArticleRepository()
    saved = run(articles.save(make_article(url="https://example.org/a?utm_source=x")))
    assert run(articles.find_by_canonical_url("https://example.org/a?utm_source=x")) == saved
    # Canonicalization happens before the repository, so a near-miss is a miss.
    assert run(articles.find_by_canonical_url("https://example.org/a")) is None


def test_article_delete_reports_when_nothing_matched() -> None:
    articles = InMemoryArticleRepository()
    saved = run(articles.save(make_article(url="https://example.org/a")))
    run(articles.delete(saved.article_id))
    with pytest.raises(NotFound):
        run(articles.delete(saved.article_id))


def test_article_listing_is_newest_first_and_scoped_to_the_owner() -> None:
    articles = InMemoryArticleRepository()
    owner, other_owner = new_id(), new_id()
    for index in range(3):
        run(
            articles.save(
                make_article(
                    owner_id=owner,
                    url=f"https://example.org/{index}",
                    created_at=FAKE_EPOCH + timedelta(days=index),
                )
            )
        )
    run(articles.save(make_article(owner_id=other_owner, url="https://example.org/other")))

    page = run(articles.list_by_owner(owner))
    assert [article.canonical_url for article in page.items] == [
        "https://example.org/2",
        "https://example.org/1",
        "https://example.org/0",
    ]
    assert page.next_cursor is None
    assert page.has_more is False


def test_article_listing_paginates_with_an_opaque_cursor() -> None:
    articles = InMemoryArticleRepository()
    owner = new_id()
    for index in range(5):
        run(
            articles.save(
                make_article(
                    owner_id=owner,
                    url=f"https://example.org/{index}",
                    created_at=FAKE_EPOCH + timedelta(days=index),
                )
            )
        )

    first = run(articles.list_by_owner(owner, limit=2))
    assert first.has_more is True
    assert first.next_cursor is not None
    second = run(articles.list_by_owner(owner, limit=2, cursor=first.next_cursor))
    third = run(articles.list_by_owner(owner, limit=2, cursor=second.next_cursor))

    seen = [article.canonical_url for page in (first, second, third) for article in page.items]
    assert seen == [f"https://example.org/{index}" for index in (4, 3, 2, 1, 0)]
    assert third.next_cursor is None


def test_a_cursor_from_another_listing_is_rejected() -> None:
    articles = InMemoryArticleRepository()
    owner = new_id()
    run(articles.save(make_article(owner_id=owner, url="https://example.org/a")))
    with pytest.raises(InvalidCursor):
        run(articles.list_by_owner(owner, cursor="card:01J0000000000000000000000"))


def test_listing_rejects_a_limit_below_one() -> None:
    articles = InMemoryArticleRepository()
    with pytest.raises(ValueError, match="limit must be at least 1"):
        run(articles.list_by_owner(new_id(), limit=0))


def test_snapshots_are_immutable_and_listed_newest_retrieval_first() -> None:
    articles = InMemoryArticleRepository()
    article = run(articles.save(make_article(url="https://example.org/a")))
    older = run(
        articles.save_snapshot(
            make_snapshot(article_id=article.article_id, retrieved_at=FAKE_EPOCH, digest=DIGEST)
        )
    )
    newer = run(
        articles.save_snapshot(
            make_snapshot(
                article_id=article.article_id,
                retrieved_at=FAKE_EPOCH + timedelta(days=1),
                digest=DIGEST,
            )
        )
    )

    assert run(articles.list_snapshots(article.article_id)) == (newer, older)
    assert run(articles.get_snapshot(older.snapshot_id)) == older
    with pytest.raises(AlreadyExists):
        run(articles.save_snapshot(older))


# --------------------------------------------------------------------------------------------
# InMemorySnapshotStore
# --------------------------------------------------------------------------------------------


def test_blobs_are_addressed_by_their_own_sha256_and_deduplicate() -> None:
    store = InMemorySnapshotStore()
    key = run(store.put(b"the article text"))
    assert key == hashlib.sha256(b"the article text").hexdigest()
    assert run(store.put(b"the article text")) == key
    assert run(store.get(key)) == b"the article text"
    assert run(store.exists(key)) is True


def test_a_missing_blob_raises_not_found() -> None:
    store = InMemorySnapshotStore()
    absent = hashlib.sha256(b"never stored").hexdigest()
    assert run(store.exists(absent)) is False
    with pytest.raises(NotFound):
        run(store.get(absent))


def test_a_tampered_blob_is_never_served() -> None:
    store = InMemorySnapshotStore()
    key = run(store.put(b"the article text"))
    store.corrupt(key, b"quietly edited text")
    with pytest.raises(BlobIntegrityError) as caught:
        run(store.get(key))
    assert caught.value.key == key
    assert caught.value.actual_sha256 == hashlib.sha256(b"quietly edited text").hexdigest()


# --------------------------------------------------------------------------------------------
# InMemoryCardRepository
# --------------------------------------------------------------------------------------------


def test_creating_a_card_twice_is_refused() -> None:
    cards = InMemoryCardRepository()
    card = make_card(owner_id=new_id(), article_id=new_id())
    created = run(cards.create(card))
    assert created.revision == 1
    with pytest.raises(AlreadyExists):
        run(cards.create(card))


def test_saving_a_card_that_does_not_exist_is_not_a_create() -> None:
    cards = InMemoryCardRepository()
    card = make_card(owner_id=new_id(), article_id=new_id())
    with pytest.raises(NotFound):
        run(cards.save(card, expected_revision=1))


def test_two_writers_with_the_same_revision_produce_one_winner() -> None:
    """The reason CardRepository exists in this shape (architecture proposal §7)."""
    cards = InMemoryCardRepository()
    stored = run(cards.create(make_card(owner_id=new_id(), article_id=new_id(), tag="Original")))

    student_edit = stored.evolve(tag="Edited by the student")
    reprocessing_job = stored.evolve(tag="Rewritten by the model")

    winner = run(cards.save(student_edit, expected_revision=stored.revision))
    assert winner.revision == 2

    with pytest.raises(RevisionMismatch) as caught:
        run(cards.save(reprocessing_job, expected_revision=stored.revision))
    assert caught.value.expected_revision == 1
    assert caught.value.actual_revision == 2
    assert run(cards.get(stored.card_id)).tag == "Edited by the student"


def test_deleting_a_card_is_guarded_by_its_revision() -> None:
    cards = InMemoryCardRepository()
    stored = run(cards.create(make_card(owner_id=new_id(), article_id=new_id())))
    run(cards.save(stored, expected_revision=1))
    with pytest.raises(RevisionMismatch):
        run(cards.delete(stored.card_id, expected_revision=1))
    run(cards.delete(stored.card_id, expected_revision=2))
    assert run(cards.find(stored.card_id)) is None


def test_cards_list_by_owner_and_by_article() -> None:
    cards = InMemoryCardRepository()
    owner, article = new_id(), new_id()
    run(cards.create(make_card(owner_id=owner, article_id=article, tag="first")))
    second = run(
        cards.create(
            make_card(
                owner_id=owner,
                article_id=new_id(),
                tag="second",
                created_at=FAKE_EPOCH + timedelta(hours=1),
            )
        )
    )
    run(
        cards.create(
            make_card(
                owner_id=new_id(),
                article_id=article,
                tag="someone else's",
                created_at=FAKE_EPOCH + timedelta(hours=2),
            )
        )
    )

    assert [card.tag for card in run(cards.list_by_owner(owner)).items] == ["second", "first"]

    from_article = run(cards.list_by_article(article))
    assert [card.tag for card in from_article.items] == ["someone else's", "first"]
    assert second.card_id not in {card.card_id for card in from_article.items}


# --------------------------------------------------------------------------------------------
# InMemorySearchRepository
# --------------------------------------------------------------------------------------------


def test_search_results_are_stored_as_a_whole_ranking() -> None:
    searches = InMemorySearchRepository()
    search = run(searches.save(make_search(owner_id=new_id())))
    results = [SearchResult(search_id=search.search_id, article_id=new_id(), rank=rank) for rank in (3, 1, 2)]
    run(searches.save_results(search.search_id, results))
    assert [result.rank for result in run(searches.list_results(search.search_id))] == [1, 2, 3]

    run(searches.save_results(search.search_id, results[:1]))
    assert len(run(searches.list_results(search.search_id))) == 1


def test_search_results_for_an_unknown_search_are_refused() -> None:
    searches = InMemorySearchRepository()
    with pytest.raises(NotFound):
        run(searches.save_results(new_id(), []))
    with pytest.raises(NotFound):
        run(searches.list_results(new_id()))


def test_results_belonging_to_another_search_or_sharing_a_rank_are_caller_bugs() -> None:
    searches = InMemorySearchRepository()
    search = run(searches.save(make_search()))
    stray = SearchResult(search_id=new_id(), article_id=new_id(), rank=1)
    with pytest.raises(ValueError, match="another search"):
        run(searches.save_results(search.search_id, [stray]))

    duplicated = [SearchResult(search_id=search.search_id, article_id=new_id(), rank=1) for _ in range(2)]
    with pytest.raises(ValueError, match="share a rank"):
        run(searches.save_results(search.search_id, duplicated))


def test_a_search_with_no_results_is_not_a_missing_search() -> None:
    searches = InMemorySearchRepository()
    search = run(searches.save(make_search()))
    assert run(searches.list_results(search.search_id)) == ()


# --------------------------------------------------------------------------------------------
# FakeSearchProvider
# --------------------------------------------------------------------------------------------


def candidate(title: str) -> CandidateResult:
    return CandidateResult(provider="fake-provider", title=title, url=f"https://example.org/{title}")


def test_the_fake_provider_answers_from_its_script_and_records_the_query() -> None:
    provider = FakeSearchProvider(
        "openalex-fake", results_by_query={"methane": [candidate("a"), candidate("b")]}
    )
    response = run(provider.search(ProviderQuery(query="methane")))
    assert provider.name == "openalex-fake"
    assert [result.title for result in response.results] == ["a", "b"]
    assert [query.query for query in provider.queries] == ["methane"]

    unknown = run(provider.search(ProviderQuery(query="something else")))
    assert unknown.results == ()


def test_the_fake_provider_honours_the_result_cap() -> None:
    provider = FakeSearchProvider(default_results=[candidate(str(index)) for index in range(10)])
    response = run(provider.search(ProviderQuery(query="q", filters=SearchFilters(max_results=3))))
    assert len(response.results) == 3


def test_a_provider_can_be_scripted_to_answer_partially_or_to_fail() -> None:
    partial = FakeSearchProvider(partial=True, default_results=[candidate("a")])
    response = run(partial.search(ProviderQuery(query="q")))
    assert response.partial is True
    assert response.error is not None

    broken = FakeSearchProvider(failure=ProviderUnavailable("openalex-fake", "timed out"))
    with pytest.raises(ProviderUnavailable):
        run(broken.search(ProviderQuery(query="q")))


# --------------------------------------------------------------------------------------------
# FakeArticleFetcher and FakeContentExtractor
# --------------------------------------------------------------------------------------------


def test_the_fetcher_serves_what_was_registered_and_404s_the_rest() -> None:
    fetcher = FakeArticleFetcher()
    fetcher.add("https://example.org/a", b"<html>body</html>")

    found = run(fetcher.fetch("https://example.org/a"))
    assert found.status_code == 200
    assert found.access_status is AccessStatus.ACCESSIBLE
    assert found.byte_size == len(b"<html>body</html>")
    assert found.fetched_at == FAKE_EPOCH

    missing = run(fetcher.fetch("https://example.org/gone"))
    assert missing.status_code == 404
    assert missing.access_status is AccessStatus.NOT_FOUND
    assert fetcher.requested_urls == ["https://example.org/a", "https://example.org/gone"]


def test_a_refused_retrieval_is_an_answer_not_an_exception() -> None:
    fetcher = FakeArticleFetcher()
    fetcher.add(
        "https://example.org/paywalled",
        b"",
        status_code=200,
        access_status=AccessStatus.PAYWALLED,
    )
    result = run(fetcher.fetch("https://example.org/paywalled"))
    assert result.access_status is AccessStatus.PAYWALLED


def test_the_extractor_splits_paragraphs_and_refuses_what_it_cannot_read() -> None:
    fetcher = FakeArticleFetcher()
    fetched = fetcher.add("https://example.org/a", b"First paragraph.\n\nSecond paragraph.\n\n")
    extracted = FakeContentExtractor().extract(fetched)
    assert extracted.paragraphs == ("First paragraph.", "Second paragraph.")
    assert extracted.text == "First paragraph.\n\nSecond paragraph."
    assert extracted.quality.paragraph_count == 2
    assert extracted.metadata_hints.canonical_url == "https://example.org/a"

    pdf = fetcher.add("https://example.org/a.pdf", b"%PDF-1.7", content_type="application/pdf")
    with pytest.raises(ValueError, match="does not handle application/pdf"):
        FakeContentExtractor().extract(pdf)


# --------------------------------------------------------------------------------------------
# FakeModelRouter
# --------------------------------------------------------------------------------------------


class PassageChoice(BaseModel):
    """A stand-in for a real structured output: ids and offsets, never quoted evidence text."""

    paragraph_id: int
    start_offset: int
    end_offset: int


class SomethingElse(BaseModel):
    note: str


def test_the_router_returns_a_validated_instance_and_call_metadata() -> None:
    router = FakeModelRouter([PassageChoice(paragraph_id=2, start_offset=0, end_offset=40)])
    invocation = run(
        router.invoke(
            task_class=ModelTaskClass.COMPLEX_REASONING,
            prompt_id="select-passage",
            prompt_version="1.2.0",
            output_type=PassageChoice,
            variables={"tag": "Warming is anthropogenic"},
        )
    )
    assert invocation.output.paragraph_id == 2
    assert invocation.metadata.model_id == "fake-model"
    assert invocation.metadata.prompt_version == "1.2.0"
    assert invocation.metadata.task_class is ModelTaskClass.COMPLEX_REASONING
    assert invocation.metadata.invoked_at == FAKE_EPOCH
    assert router.calls[0].variables == {"tag": "Warming is anthropogenic"}


def test_a_mapping_is_validated_against_the_requested_schema() -> None:
    router = FakeModelRouter([{"paragraph_id": 1, "start_offset": 0, "end_offset": 10}])
    invocation = run(
        router.invoke(
            task_class=ModelTaskClass.HIGH_VOLUME,
            prompt_id="p",
            prompt_version="1.0.0",
            output_type=PassageChoice,
        )
    )
    assert invocation.output == PassageChoice(paragraph_id=1, start_offset=0, end_offset=10)


def test_output_that_does_not_fit_the_schema_raises_invalid_model_output() -> None:
    router = FakeModelRouter([{"paragraph_id": "not a number"}, SomethingElse(note="wrong type")])
    for _ in range(2):
        with pytest.raises(InvalidModelOutput) as caught:
            run(
                router.invoke(
                    task_class=ModelTaskClass.HIGH_VOLUME,
                    prompt_id="select-passage",
                    prompt_version="1.0.0",
                    output_type=PassageChoice,
                )
            )
        assert caught.value.prompt_id == "select-passage"
        assert caught.value.model_id == "fake-model"


def test_an_unreachable_model_and_an_empty_script_are_both_provider_failures() -> None:
    router = FakeModelRouter([ProviderUnavailable("bedrock-fake", "throttled")])
    with pytest.raises(ProviderUnavailable):
        run(
            router.invoke(
                task_class=ModelTaskClass.HIGH_VOLUME,
                prompt_id="p",
                prompt_version="1.0.0",
                output_type=PassageChoice,
            )
        )
    with pytest.raises(ProviderUnavailable, match="no scripted response"):
        run(
            router.invoke(
                task_class=ModelTaskClass.HIGH_VOLUME,
                prompt_id="p",
                prompt_version="1.0.0",
                output_type=PassageChoice,
            )
        )
    assert len(router.calls) == 2


# --------------------------------------------------------------------------------------------
# FixedClock and SequentialIdGenerator
# --------------------------------------------------------------------------------------------


def test_a_fixed_clock_stays_put_unless_it_is_given_a_step() -> None:
    clock = FixedClock()
    assert clock.now() == clock.now() == FAKE_EPOCH

    stepping = FixedClock(step=timedelta(seconds=1))
    assert [stepping.now() for _ in range(3)] == [
        FAKE_EPOCH,
        FAKE_EPOCH + timedelta(seconds=1),
        FAKE_EPOCH + timedelta(seconds=2),
    ]

    clock.advance(timedelta(days=1))
    assert clock.now() == FAKE_EPOCH + timedelta(days=1)
    clock.set(datetime(2025, 6, 1, tzinfo=UTC))
    assert clock.now() == datetime(2025, 6, 1, tzinfo=UTC)


def test_a_clock_cannot_be_set_to_a_naive_instant() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        FixedClock(datetime(2025, 1, 1))  # a naive instant: the point of the test
    with pytest.raises(ValueError, match="timezone-aware"):
        FixedClock().set(datetime(2025, 1, 1))  # a naive instant: the point of the test


def test_generated_ids_are_valid_ulids_that_count_up() -> None:
    generator = SequentialIdGenerator()
    ids = [generator.new_id() for _ in range(3)]
    assert all(re.match(ULID_PATTERN, value) for value in ids)
    assert ids == sorted(ids)
    assert len({len(value) for value in ids}) == 1

    labelled = SequentialIdGenerator("CARD", start=7)
    first = labelled.new_id()
    assert first.startswith("0CARD")
    assert first.endswith("7")
    assert re.match(ULID_PATTERN, first)
    assert (
        Card(
            card_id=first,
            owner_id=new_id(),
            article_id=new_id(),
            tag="A tag",
            provenance_mode=ProvenanceMode.PUBLISHER_RETRIEVED,
        ).card_id
        == first
    )


def test_a_prefix_outside_the_ulid_alphabet_is_refused() -> None:
    with pytest.raises(ValueError, match="Crockford base32"):
        SequentialIdGenerator("card")
    with pytest.raises(ValueError, match="at most 24"):
        SequentialIdGenerator("C" * 25)


# --------------------------------------------------------------------------------------------
# build_fake_ports
# --------------------------------------------------------------------------------------------


def test_build_fake_ports_wires_one_fake_per_port_on_a_shared_clock() -> None:
    clock = FixedClock(step=timedelta(minutes=1))
    ports = build_fake_ports(clock=clock, id_generator=SequentialIdGenerator("AB"))
    assert ports.clock is clock
    assert ports.id_generator.new_id().startswith("0AB")

    fetched = run(ports.article_fetcher.fetch("https://example.org/unknown"))
    assert fetched.fetched_at == FAKE_EPOCH
    # The fetcher and the router read the same clock, so their timestamps advance together.
    with pytest.raises(ProviderUnavailable):
        run(
            ports.model_router.invoke(
                task_class=ModelTaskClass.HIGH_VOLUME,
                prompt_id="p",
                prompt_version="1.0.0",
                output_type=PassageChoice,
            )
        )
