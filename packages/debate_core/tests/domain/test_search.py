"""Search, SearchFilters and SearchResult: the record of one federated search."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from debate_core.domain import (
    Search,
    SearchFilters,
    SearchResult,
    SearchStatus,
    SourceType,
    new_id,
)


def make_search(**overrides: object) -> Search:
    """A Search with every required field filled in."""
    fields: dict[str, object] = {"query": "midterm elections turnout", "status": SearchStatus.COMPLETE}
    fields.update(overrides)
    return Search.model_validate(fields)


# --------------------------------------------------------------------------------------------
# SearchFilters
# --------------------------------------------------------------------------------------------


def test_filters_default_to_an_unconstrained_window() -> None:
    filters = SearchFilters()
    assert filters.since is None
    assert filters.until is None
    assert filters.source_types == ()
    assert filters.max_results == 20
    assert filters.language is None


def test_filters_reject_an_inverted_window() -> None:
    with pytest.raises(ValidationError) as caught:
        SearchFilters(
            since=datetime(2026, 9, 17, tzinfo=UTC),
            until=datetime(2026, 9, 14, tzinfo=UTC),
        )
    assert "after until" in str(caught.value)


def test_filters_reject_naive_bounds() -> None:
    with pytest.raises(ValidationError):
        SearchFilters(since=datetime(2026, 9, 17))  # deliberately naive


@pytest.mark.parametrize("max_results", [0, -1, 201])
def test_max_results_is_bounded(max_results: int) -> None:
    with pytest.raises(ValidationError):
        SearchFilters(max_results=max_results)


# --------------------------------------------------------------------------------------------
# Search
# --------------------------------------------------------------------------------------------


def test_search_records_query_filters_providers_and_status() -> None:
    search = make_search(
        filters=SearchFilters(
            since=datetime(2026, 9, 14, tzinfo=UTC),
            source_types=(SourceType.NEWS, SourceType.GOVERNMENT),
            max_results=20,
        ),
        provider_set=("openalex", "publisher_rss"),
        status=SearchStatus.PARTIAL,
        owner_id=new_id(),
        organization_id=new_id(),
    )
    assert search.search_id
    assert search.query == "midterm elections turnout"
    assert search.provider_set == ("openalex", "publisher_rss")
    assert search.status is SearchStatus.PARTIAL
    assert search.filters.source_types == (SourceType.NEWS, SourceType.GOVERNMENT)
    assert search.created_at.tzinfo is UTC


def test_search_status_is_required_so_a_partial_search_cannot_look_complete() -> None:
    with pytest.raises(ValidationError) as caught:
        Search.model_validate({"query": "midterm elections"})
    assert "status" in str(caught.value)


def test_search_query_must_not_be_blank() -> None:
    with pytest.raises(ValidationError):
        make_search(query="   ")


def test_search_round_trips_through_json() -> None:
    search = make_search(
        filters=SearchFilters(
            since=datetime(2026, 9, 14, 6, 0, tzinfo=UTC),
            until=datetime(2026, 9, 17, 6, 0, tzinfo=UTC),
            source_types=(SourceType.SCHOLARLY,),
            language="en",
        ),
        provider_set=("openalex",),
        owner_id=new_id(),
    )
    assert Search.model_validate_json(search.model_dump_json()) == search


# --------------------------------------------------------------------------------------------
# SearchResult
# --------------------------------------------------------------------------------------------


def make_result(**overrides: object) -> SearchResult:
    """A SearchResult with every required field filled in."""
    fields: dict[str, object] = {"search_id": new_id(), "article_id": new_id(), "rank": 1}
    fields.update(overrides)
    return SearchResult.model_validate(fields)


def test_result_carries_rank_scores_features_and_an_explanation() -> None:
    result = make_result(
        rank=3,
        total_score=0.82,
        lexical_score=0.61,
        source_quality_features={"recency": 1.0, "peer_reviewed": 1.0, "provider_agreement": 0.5},
        explanation="recent (3 days), peer-reviewed, strong term match",
        providers=("openalex", "crossref"),
    )
    assert result.rank == 3
    assert result.total_score == pytest.approx(0.82)
    assert result.source_quality_features["peer_reviewed"] == pytest.approx(1.0)
    assert result.explanation == "recent (3 days), peer-reviewed, strong term match"
    assert result.providers == ("openalex", "crossref")


def test_result_scores_are_optional_because_v1_ranking_is_lexical() -> None:
    result = make_result()
    assert result.total_score is None
    assert result.semantic_score is None
    assert result.rerank_score is None
    assert result.source_quality_features == {}


@pytest.mark.parametrize("rank", [0, -1])
def test_rank_is_one_based(rank: int) -> None:
    with pytest.raises(ValidationError):
        make_result(rank=rank)


def test_result_round_trips_through_json() -> None:
    result = make_result(
        rank=2,
        total_score=0.5,
        semantic_score=0.44,
        rerank_score=0.91,
        source_quality_features={"bm25": 12.5, "open_access": 1.0},
        explanation="open access",
        providers=("openalex",),
    )
    assert SearchResult.model_validate_json(result.model_dump_json()) == result
