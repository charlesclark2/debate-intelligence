"""Ranked candidates become stored results through Articles, never fetched (v1-e08-t05).

:class:`ArticleMatchingStage` over the in-memory Article repository, fed rankings built by the real
dedupe and rank code from hand-made provider records, and the whole service once with the stage in
its rank slot (:class:`StagesInOrder`). Expected Articles are written out by hand from the records.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from debate_core.application.federated_dedupe import DedupeStage, merge_candidates
from debate_core.application.federated_ranking import (
    FEDERATED_RANKING_CONFIG_PATH,
    FederatedRankStage,
    load_federated_ranking_config,
    rank_merged_candidates,
)
from debate_core.application.federated_search import FederatedSearchService
from debate_core.application.federated_search_articles import ArticleMatchingStage
from debate_core.application.federated_search_types import (
    PassThroughStage,
    SearchRequest,
    SearchState,
    StagesInOrder,
)
from debate_core.domain import AccessStatus, Article, ArticleIdentifiers, SearchFilters, SourceType
from debate_core.domain.discovery import CandidateResult, DatePrecision, ProviderHealth
from debate_core.testing.fakes.clock_and_ids import FixedClock, SequentialIdGenerator
from debate_core.testing.fakes.persistence import InMemoryArticleRepository, InMemorySearchRepository
from debate_core.testing.fakes.providers import FakeSearchProvider

REPOSITORY = Path(__file__).resolve().parents[4]
NOW = datetime(2026, 10, 21, 12, tzinfo=UTC)
CONFIG = load_federated_ranking_config(REPOSITORY / FEDERATED_RANKING_CONFIG_PATH)
SEARCH_ID = "0SRCH000000000000000000001"

PAPER = CandidateResult(
    provider="openalex",
    provider_record_id="W4410000001",
    title="Midterm elections and health insurance",
    url="https://doi.org/10.5555/ipr.2026.0031",
    identifiers=ArticleIdentifiers(doi="10.5555/ipr.2026.0031", openalex_id="W4410000001"),
    source_type=SourceType.SCHOLARLY,
    authors=("Ada Placeholder",),
    publication="Invented Politics Review",
    published_at=datetime(2026, 10, 2, tzinfo=UTC),
    snippet="Not stored on an Article.",
)
STORY = CandidateResult(
    provider="rss",
    title="Midterm elections tighten",
    url="https://news.example.org/2026/10/20/midterms-tighten?utm_source=feed",
    source_type=SourceType.NEWS,
    publication="The Example Courier",
    published_at=datetime(2026, 10, 20, tzinfo=UTC),
)
STORY_CANONICAL = "https://news.example.org/2026/10/20/midterms-tighten"


def run[ResultT](awaitable: Coroutine[Any, Any, ResultT]) -> ResultT:
    return asyncio.run(awaitable)


def ranked_state(*records: CandidateResult) -> SearchState:
    """The state the rank stage leaves for these records: deduplicated and ranked by the real code."""
    request = SearchRequest(query="midterm elections")
    ranked = rank_merged_candidates(
        merge_candidates(records),
        queries=("midterm elections",),
        filters=SearchFilters(),
        answered_providers=2,
        now=NOW,
        config=CONFIG,
    )
    return SearchState.start(SEARCH_ID, request).evolve(ranked_candidates=ranked)


def stage(articles: InMemoryArticleRepository) -> ArticleMatchingStage:
    return ArticleMatchingStage(articles, clock=FixedClock(NOW), ids=SequentialIdGenerator("ART"))


def test_a_source_no_article_has_is_registered_discovery_only_with_its_metadata() -> None:
    articles = InMemoryArticleRepository()
    state = ranked_state(STORY)

    done = run(stage(articles).run(state))

    [article] = done.articles
    assert article.model_dump(exclude={"created_at", "updated_at", "revision"}) == Article(
        article_id="0ART0000000000000000000001",
        canonical_url=STORY_CANONICAL,
        title="Midterm elections tighten",
        publication="The Example Courier",
        published_at=datetime(2026, 10, 20, tzinfo=UTC),
        source_type=SourceType.NEWS,
        access_status=AccessStatus.UNKNOWN,
        created_at=NOW,
        updated_at=NOW,
    ).model_dump(exclude={"created_at", "updated_at", "revision"})
    assert run(articles.find_by_canonical_url(STORY_CANONICAL)) == article
    [result] = done.results
    assert (result.search_id, result.article_id, result.rank) == (SEARCH_ID, article.article_id, 1)
    assert result.explanation == state.ranked_candidates[0].explanation
    assert list(result.source_quality_features) == list(state.ranked_candidates[0].features)


def test_a_stored_article_answers_its_url_as_it_stands() -> None:
    articles = InMemoryArticleRepository()
    known = Article(
        article_id="0KNWN000000000000000000001",
        canonical_url=STORY_CANONICAL,
        title="The title a fetch read",
        access_status=AccessStatus.PAYWALLED,
        created_at=NOW,
        updated_at=NOW,
    )
    stored = run(articles.save(known))

    done = run(stage(articles).run(ranked_state(STORY)))

    assert done.articles == (stored,)
    assert done.results[0].article_id == "0KNWN000000000000000000001"
    assert run(articles.get("0KNWN000000000000000000001")) == stored


def test_every_ranked_candidate_gets_one_result_in_rank_order() -> None:
    articles = InMemoryArticleRepository()
    state = ranked_state(PAPER, STORY)

    done = run(stage(articles).run(state))

    assert [result.rank for result in done.results] == [1, 2]
    assert [article.title for article in done.articles] == [
        ranked.candidate.title for ranked in state.ranked_candidates
    ]
    assert done.articles[[a.title for a in done.articles].index(PAPER.title)].identifiers == PAPER.identifiers


def test_two_candidates_naming_one_article_store_it_once() -> None:
    articles = InMemoryArticleRepository()
    state = ranked_state(STORY, PAPER)
    first, second = state.ranked_candidates
    same_url = second.model_copy(
        update={
            "candidate": second.candidate.model_copy(update={"canonical_url": first.candidate.canonical_url})
        }
    )

    done = run(stage(articles).run(state.evolve(ranked_candidates=(first, same_url))))

    assert [result.rank for result in done.results] == [1]
    assert len(done.articles) == 1


def test_a_candidate_with_no_canonical_url_stores_no_result() -> None:
    articles = InMemoryArticleRepository()
    state = ranked_state(STORY)
    [only] = state.ranked_candidates
    no_url = only.model_copy(update={"candidate": only.candidate.model_copy(update={"canonical_url": None})})

    done = run(stage(articles).run(state.evolve(ranked_candidates=(no_url,))))

    assert (done.results, done.articles) == ((), ())


def test_stages_in_order_run_one_after_another_and_need_one() -> None:
    articles = InMemoryArticleRepository()
    state = SearchState.start(SEARCH_ID, SearchRequest(query="midterm elections"))
    rank_then_match = StagesInOrder(FederatedRankStage(CONFIG, clock=FixedClock(NOW)), stage(articles))

    done = run(rank_then_match.run(state.evolve(merged_candidates=merge_candidates([STORY]))))

    assert [ranked.candidate.title for ranked in done.ranked_candidates] == ["Midterm elections tighten"]
    assert len(done.results) == 1
    with pytest.raises(ValueError, match="at least one"):
        StagesInOrder()
    assert run(StagesInOrder(PassThroughStage()).run(state)) is state


class _Providers:
    def __init__(self, *providers: FakeSearchProvider) -> None:
        self._providers = providers

    @property
    def providers(self) -> tuple[FakeSearchProvider, ...]:
        return self._providers

    @property
    def not_configured(self) -> dict[str, str]:
        return {}

    def health(self) -> tuple[ProviderHealth, ...]:
        return ()


def test_the_service_stores_the_matched_results_and_returns_the_ranking_and_articles() -> None:
    articles = InMemoryArticleRepository()
    searches = InMemorySearchRepository()
    clock = FixedClock(NOW)
    service = FederatedSearchService(
        _Providers(
            FakeSearchProvider("openalex", default_results=[PAPER]),
            FakeSearchProvider("rss", default_results=[STORY]),
        ),
        searches,
        clock=clock,
        ids=SequentialIdGenerator("SRCH"),
        normalize=DedupeStage(),
        rank=StagesInOrder(
            FederatedRankStage(CONFIG, clock=clock),
            ArticleMatchingStage(articles, clock=clock, ids=SequentialIdGenerator("ART")),
        ),
    )

    outcome = run(service.search(SearchRequest(query="midterm elections")))

    assert len(outcome.ranked_candidates) == 2
    assert [article.access_status for article in outcome.articles] == [AccessStatus.UNKNOWN] * 2
    assert run(searches.list_results(outcome.search.search_id)) == outcome.results
    assert [result.article_id for result in outcome.results] == [
        article.article_id for article in outcome.articles
    ]


@pytest.mark.parametrize(
    ("published_at", "precision", "stored", "stored_precision"),
    [
        (
            datetime(2021, 1, 1, tzinfo=UTC),
            DatePrecision.YEAR,
            datetime(2021, 1, 1, tzinfo=UTC),
            DatePrecision.YEAR,
        ),
        (
            datetime(2023, 3, 1, tzinfo=UTC),
            DatePrecision.MONTH,
            datetime(2023, 3, 1, tzinfo=UTC),
            DatePrecision.MONTH,
        ),
        (
            datetime(2022, 5, 17, tzinfo=UTC),
            DatePrecision.DAY,
            datetime(2022, 5, 17, tzinfo=UTC),
            DatePrecision.DAY,
        ),
        (datetime(2022, 5, 17, tzinfo=UTC), None, datetime(2022, 5, 17, tzinfo=UTC), DatePrecision.DAY),
    ],
    ids=["year", "month", "day", "no precision"],
)
def test_a_discovery_only_article_keeps_a_year_or_a_month_date_at_its_precision_never_a_day(
    published_at: datetime,
    precision: DatePrecision | None,
    stored: datetime,
    stored_precision: DatePrecision,
) -> None:
    """A year or a month is stored with its precision (v1-e06-t13); until then v1-e07-t03 stored none."""
    crossref = PAPER.model_copy(
        update={
            "provider": "crossref",
            "provider_record_id": "10.5555/ipr.2026.0031",
            "identifiers": ArticleIdentifiers(doi="10.5555/ipr.2026.0031"),
            "published_at": published_at,
            "date_precision": precision,
        }
    )
    done = run(stage(InMemoryArticleRepository()).run(ranked_state(crossref)))

    [article] = done.articles
    assert (article.published_at, article.date_precision) == (stored, stored_precision)
