"""The search presenter on Crossref's answers: partial dates in the table, and queries it never sent.

The outcome is a real search: the service's fan-out, dedupe and rank stages over a stand-in Crossref
wrapped in the real ResilientProvider. The stand-in answers the first of three queries and gives the
other two the answer the Crossref adapter gives a query its pacer never sends (v1-e07-t03), word for
word. Every expected row, line and key is written by hand (working agreement 6).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from debate_cli.exit_codes import ExitCode, exit_code_for_search
from debate_cli.presenters.search_presenter import footer_lines, results_table, search_payload
from debate_core.application.federated_dedupe import DedupeStage
from debate_core.application.federated_ranking import (
    FEDERATED_RANKING_CONFIG_PATH,
    FederatedRankStage,
    load_federated_ranking_config,
)
from debate_core.application.federated_search import FederatedSearchService
from debate_core.application.federated_search_types import SearchOutcome, SearchRequest, SearchState
from debate_core.domain import ArticleIdentifiers, SourceType
from debate_core.domain.discovery import (
    CandidateResult,
    DatePrecision,
    ProviderHealth,
    ProviderQuery,
    ProviderResponse,
)
from debate_core.integrations.discovery.resilience import ResiliencePolicy, ResilientProvider
from debate_core.testing.fakes.clock_and_ids import FixedClock, SequentialIdGenerator
from debate_core.testing.fakes.persistence import InMemorySearchRepository

REPOSITORY: Final = Path(__file__).resolve().parents[3]
NOW: Final = datetime(2026, 10, 21, 12, tzinfo=UTC)
QUERIES: Final = (
    "carbon capture subsidies",
    "carbon capture subsidies cost",
    "carbon capture storage liability",
)
NOT_ASKED: Final = (
    "crossref: not asked: the public pool allows 1 query a second; set a contact email for the polite pool"
)


def work(
    number: int, title: str, published_at: datetime | None, precision: DatePrecision | None
) -> CandidateResult:
    return CandidateResult(
        provider="crossref",
        provider_record_id=f"10.5555/capture.{number}",
        title=title,
        url=f"https://doi.org/10.5555/capture.{number}",
        identifiers=ArticleIdentifiers(doi=f"10.5555/capture.{number}"),
        source_type=SourceType.SCHOLARLY,
        published_at=published_at,
        date_precision=precision,
    )


WORKS: Final = (
    work(1, "Subsidy design for capture plants", datetime(2021, 1, 1, tzinfo=UTC), DatePrecision.YEAR),
    work(2, "Who pays for stored carbon?", datetime(2023, 3, 1, tzinfo=UTC), DatePrecision.MONTH),
    work(
        3,
        "Pricing carbon capture under production subsidies",
        datetime(2022, 5, 17, tzinfo=UTC),
        DatePrecision.DAY,
    ),
    work(4, "Capture credits, undated", None, None),
)


class AnswersOnlyTheFirstQuery:
    """Crossref as its pacer leaves it: the first query answered, the others not sent."""

    name = "crossref"

    async def search(self, query: ProviderQuery) -> ProviderResponse:
        if query.query == QUERIES[0]:
            return ProviderResponse(provider="crossref", results=WORKS, elapsed_ms=4.0)
        return ProviderResponse(provider="crossref", elapsed_ms=8000.0, partial=True, error=NOT_ASKED)


class ThreeQueries:
    """An expand stage that asks the three queries."""

    async def run(self, state: SearchState) -> SearchState:
        return state.evolve(queries=tuple(ProviderQuery(query=query) for query in QUERIES))


class WrappedCrossref:
    def __init__(self, clock: FixedClock) -> None:
        self.wrapped = ResilientProvider(AnswersOnlyTheFirstQuery(), ResiliencePolicy(), clock=clock)

    @property
    def providers(self) -> tuple[ResilientProvider, ...]:
        return (self.wrapped,)

    @property
    def not_configured(self) -> dict[str, str]:
        return {}

    def health(self) -> tuple[ProviderHealth, ...]:
        return (self.wrapped.health(),)


def searched() -> SearchOutcome:
    clock = FixedClock(NOW)
    config = load_federated_ranking_config(REPOSITORY / FEDERATED_RANKING_CONFIG_PATH)
    service = FederatedSearchService(
        WrappedCrossref(clock),
        InMemorySearchRepository(),
        clock=clock,
        ids=SequentialIdGenerator("SRCH"),
        expand=ThreeQueries(),
        normalize=DedupeStage(),
        rank=FederatedRankStage(config, clock=clock),
    )
    return asyncio.run(service.search(SearchRequest(query=QUERIES[0])))


def test_the_table_shows_a_year_or_a_month_and_never_an_invented_day() -> None:
    table = results_table(searched())

    date_column = list(table.columns).index("Date")
    dates = {row[1]: row[date_column] for row in table.rows}
    assert dates == {
        "Subsidy design for capture plants": "2021",
        "Who pays for stored carbon?": "2023-03",
        "Pricing carbon capture under production subsidies": "2022-05-17",
        "Capture credits, undated": "undated",
    }


def test_queries_crossref_never_sent_make_the_search_partial_and_say_why_without_a_failure() -> None:
    outcome = searched()
    reason = NOT_ASKED.removeprefix("crossref: ")

    assert footer_lines(outcome) == [
        "Providers: PARTIAL, results may be missing",
        f"  crossref: partial, 4 results from 3 queries: {reason}",
    ]
    assert results_table(outcome).title == 'PARTIAL: 4 results for "carbon capture subsidies"'
    assert exit_code_for_search(outcome) is ExitCode.SEARCH_PARTIAL

    payload = search_payload(outcome)
    assert payload["status"] == "PARTIAL"
    assert payload["providers"] == [
        {
            "provider": "crossref",
            "outcome": "partial",
            "queries": 3,
            "failed": 0,
            "results": 4,
            "reasons": [reason],
        }
    ]
    assert payload["provider_calls"] == [
        {
            "provider": "crossref",
            "query": query,
            "outcome": "ok",
            "elapsed_ms": call["elapsed_ms"],
            "results": 4 if query == QUERIES[0] else 0,
            "partial": query != QUERIES[0],
            "error": None if query == QUERIES[0] else NOT_ASKED,
        }
        for query, call in zip(QUERIES, payload["provider_calls"], strict=True)  # type: ignore[arg-type]
    ]
    (health,) = payload["provider_health"]  # type: ignore[misc]
    assert (health["state"], health["error_count"], health["consecutive_failures"], health["last_error"]) == (  # type: ignore[index]
        "closed",
        0,
        0,
        None,
    )
    assert health["success_count"] == 3  # type: ignore[index]


def test_the_json_keeps_the_period_start_and_names_no_precision_yet() -> None:
    """Ruling 3 of 2026-11-02: the JSON is unchanged here; a `date_precision` key is a follow-up."""
    results = search_payload(searched())["results"]
    by_title = {item["title"]: item for item in results}  # type: ignore[index, union-attr]
    year = by_title["Subsidy design for capture plants"]
    assert year["published_at"] == "2021-01-01T00:00:00+00:00"  # type: ignore[index]
    assert "date_precision" not in year  # type: ignore[operator]
