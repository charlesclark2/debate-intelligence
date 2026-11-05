"""The search footer on a feed that keeps failing (v1-e07-t14, PM ruling 2026-11-05).

A feed that has failed on every read for three days no longer makes the feeds' answer partial, so the
search is COMPLETE and exits 0, and the footer still names the feed, with the day it started
failing, among the rss line's reasons. A stand-in `rss` answers every query as the feed provider
does in that case. Its outlets, dates and results are invented; every expected line and key is
written by hand (working agreement 6).
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
from debate_core.domain import SourceType
from debate_core.domain.discovery import CandidateResult, ProviderHealth, ProviderQuery, ProviderResponse
from debate_core.integrations.discovery.resilience import ResiliencePolicy, ResilientProvider
from debate_core.testing.fakes.clock_and_ids import FixedClock, SequentialIdGenerator
from debate_core.testing.fakes.persistence import InMemorySearchRepository

REPOSITORY: Final = Path(__file__).resolve().parents[3]
NOW: Final = datetime(2026, 11, 6, 12, tzinfo=UTC)
QUERIES: Final = ("senate health vote", "senate health vote whip count")
STANDING: Final = "Example Wire failing since 2026-11-02: unreadable feed: not well-formed XML: ParseError"
NEW_FAILURE: Final = "1 of 3 feeds failed: Gone Gazette: HTTP 503"
STORY: Final = CandidateResult(
    provider="rss",
    provider_record_id="courier-2001",
    title="Senate health vote slips a week",
    url="https://news.example.org/2026/11/05/health-vote",
    source_type=SourceType.NEWS,
    publication="Example Courier",
    published_at=datetime(2026, 11, 5, 15, tzinfo=UTC),
)


class FeedsWithAStandingFailure:
    """The feed provider's answer when one feed has failed for days, and maybe another just now."""

    name = "rss"

    def __init__(self, *, new_failure: str | None) -> None:
        self._new_failure = new_failure

    async def search(self, query: ProviderQuery) -> ProviderResponse:
        return ProviderResponse(
            provider="rss",
            results=(STORY,) if query.query == QUERIES[0] else (),
            elapsed_ms=5.0,
            partial=self._new_failure is not None,
            error=self._new_failure,
            notes=(STANDING,),
        )


class TwoQueries:
    async def run(self, state: SearchState) -> SearchState:
        return state.evolve(queries=tuple(ProviderQuery(query=query) for query in QUERIES))


class WrappedFeeds:
    def __init__(self, clock: FixedClock, *, new_failure: str | None) -> None:
        provider = FeedsWithAStandingFailure(new_failure=new_failure)
        self.wrapped = ResilientProvider(provider, ResiliencePolicy(), clock=clock)

    @property
    def providers(self) -> tuple[ResilientProvider, ...]:
        return (self.wrapped,)

    @property
    def not_configured(self) -> dict[str, str]:
        return {}

    def health(self) -> tuple[ProviderHealth, ...]:
        return (self.wrapped.health(),)


def searched(*, new_failure: str | None = None) -> SearchOutcome:
    clock = FixedClock(NOW)
    config = load_federated_ranking_config(REPOSITORY / FEDERATED_RANKING_CONFIG_PATH)
    service = FederatedSearchService(
        WrappedFeeds(clock, new_failure=new_failure),
        InMemorySearchRepository(),
        clock=clock,
        ids=SequentialIdGenerator("SRCH"),
        expand=TwoQueries(),
        normalize=DedupeStage(),
        rank=FederatedRankStage(config, clock=clock),
    )
    return asyncio.run(service.search(SearchRequest(query=QUERIES[0])))


def test_a_standing_feed_failure_is_named_in_the_footer_and_the_search_is_complete() -> None:
    outcome = searched()

    assert footer_lines(outcome) == [
        "Providers: COMPLETE",
        f"  rss: ok, 1 result from 2 queries: not counted as partial: {STANDING}",
    ]
    assert results_table(outcome).title == '1 result for "senate health vote"'
    assert exit_code_for_search(outcome) is ExitCode.OK
    payload = search_payload(outcome)
    assert payload["status"] == "COMPLETE"
    assert payload["providers"] == [
        {
            "provider": "rss",
            "outcome": "ok",
            "queries": 2,
            "failed": 0,
            "results": 1,
            "reasons": [f"not counted as partial: {STANDING}"],
        }
    ]


def test_a_new_feed_failure_beside_a_standing_one_is_partial_and_names_both() -> None:
    outcome = searched(new_failure=NEW_FAILURE)

    assert footer_lines(outcome) == [
        "Providers: PARTIAL, results may be missing",
        f"  rss: partial, 1 result from 2 queries: {NEW_FAILURE}; not counted as partial: {STANDING}",
    ]
    assert exit_code_for_search(outcome) is ExitCode.SEARCH_PARTIAL
    (rss,) = search_payload(outcome)["providers"]  # type: ignore[misc]
    assert rss["reasons"] == [NEW_FAILURE, f"not counted as partial: {STANDING}"]  # type: ignore[index]
