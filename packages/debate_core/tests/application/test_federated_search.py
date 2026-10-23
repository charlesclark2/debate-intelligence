"""FederatedSearchService: concurrent fan-out, partial results, the stored record and the stage pipeline.

Every test runs on :class:`~debate_core.testing.virtual_time.VirtualTimeEventLoop`, whose clock jumps
to the next timer instead of waiting. A provider that "takes 30 seconds" is an `asyncio.sleep(30)`
that costs no real time, and the deadlines asyncio enforces (the providers' own timeouts, the
search's overall deadline) fire at their virtual instant. The service reads time through
:class:`~debate_core.testing.virtual_time.EventLoopClock`, the `Clock` port over that same loop
clock, so its recorded times and elapsed milliseconds agree with the deadlines. No test here sleeps
for real; the timing tests also assert that they took under 100 ms of wall-clock time.

Expected values are written out by hand from the fakes beside them (working agreement 6).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Sequence
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from debate_core.application.errors import (
    ProviderCircuitOpen,
    ProviderError,
    ProviderRateLimited,
    ProviderTimedOut,
    ProviderUnavailable,
)
from debate_core.application.federated_search import (
    DEFAULT_DEADLINE_SECONDS,
    FanOutStage,
    FederatedSearchService,
    search_status,
)
from debate_core.application.federated_search_types import (
    PassThroughStage,
    SearchOutcome,
    SearchRequest,
    SearchStage,
    SearchState,
    StageName,
)
from debate_core.application.ports.persistence import SearchRepository
from debate_core.application.ports.providers import SearchProvider
from debate_core.domain import Search, SearchFilters, SearchResult, SearchStatus
from debate_core.domain.discovery import (
    CandidateResult,
    ProviderHealth,
    ProviderOutcome,
    ProviderQuery,
    ProviderResponse,
    ProviderStatus,
)
from debate_core.integrations.discovery.registry import ProviderRegistry
from debate_core.integrations.discovery.resilience import ResiliencePolicy, ResilientProvider
from debate_core.integrations.local import SqliteDatabase, SqliteSearchRepository
from debate_core.testing.builders import (
    build_candidate_result,
    build_provider_status,
    build_search_result,
)
from debate_core.testing.fakes.clock_and_ids import FAKE_EPOCH, SequentialIdGenerator
from debate_core.testing.fakes.persistence import InMemorySearchRepository
from debate_core.testing.fakes.providers import FakeSearchProvider
from debate_core.testing.virtual_time import EventLoopClock, run_in_virtual_time

#: The most wall-clock time a test about seconds of provider latency may take.
REAL_TIME_BUDGET_SECONDS = 0.1

FIRST_SEARCH_ID = "0SRCH000000000000000000001"

METHANE = build_candidate_result(provider="openalex")
PERMAFROST = build_candidate_result(
    provider="openalex",
    title="Permafrost carbon feedback in a warming Arctic",
    url="https://example.org/permafrost-carbon",
)
METHANE_FROM_CROSSREF = build_candidate_result(provider="crossref")
METHANE_FROM_CORE = build_candidate_result(provider="core")


# --------------------------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------------------------


class SlowProvider:
    """Answers with `results` after `seconds` of loop time; asked queries are kept in `queries`."""

    def __init__(self, name: str, seconds: float, results: Sequence[CandidateResult] = ()) -> None:
        self._name = name
        self._seconds = seconds
        self._results = tuple(results)
        self.queries: list[ProviderQuery] = []

    @property
    def name(self) -> str:
        return self._name

    async def search(self, query: ProviderQuery) -> ProviderResponse:
        self.queries.append(query)
        await asyncio.sleep(self._seconds)
        return ProviderResponse(provider=self._name, results=self._results, elapsed_ms=self._seconds * 1000)


class ProvidersOnHand:
    """The `DiscoveryProviders` port over providers given directly, with no health to report."""

    def __init__(self, *providers: SearchProvider) -> None:
        self._providers = providers

    @property
    def providers(self) -> tuple[SearchProvider, ...]:
        return self._providers

    def health(self) -> tuple[ProviderHealth, ...]:
        return ()


def wrapped(
    *adapters: SearchProvider, timeout_seconds: float = 10.0, failure_threshold: int = 3
) -> ProviderRegistry:
    """A real registry: each adapter in a ResilientProvider timed and benched by the loop clock."""
    policy = ResiliencePolicy(
        timeout_seconds=timeout_seconds, failure_threshold=failure_threshold, cooldown_seconds=60.0
    )
    return ProviderRegistry(
        ResilientProvider(adapter, policy, clock=EventLoopClock()) for adapter in adapters
    )


def service_over(
    providers: ProvidersOnHand | ProviderRegistry,
    *,
    searches: SearchRepository | None = None,
    deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
    expand: SearchStage | None = None,
    normalize: SearchStage | None = None,
    rank: SearchStage | None = None,
) -> FederatedSearchService:
    return FederatedSearchService(
        providers,
        InMemorySearchRepository() if searches is None else searches,
        clock=EventLoopClock(),
        ids=SequentialIdGenerator("SRCH"),
        deadline_seconds=deadline_seconds,
        expand=expand,
        normalize=normalize,
        rank=rank,
    )


def outcomes(statuses: Sequence[ProviderStatus]) -> list[tuple[str, ProviderOutcome]]:
    return [(status.provider, status.outcome) for status in statuses]


REQUEST = SearchRequest(query="arctic methane feedback")


# --------------------------------------------------------------------------------------------
# Fan-out: partial results (ac1)
# --------------------------------------------------------------------------------------------


def test_fan_out_with_one_provider_past_its_timeout_and_one_raising_is_partial_with_the_healthy_results() -> (
    None
):
    """ac1, through the real registry: the timeout is ResilientProvider's own, not the service's."""
    registry = wrapped(
        FakeSearchProvider("openalex", default_results=(METHANE, PERMAFROST)),
        SlowProvider("crossref", seconds=30.0, results=(METHANE_FROM_CROSSREF,)),
        FakeSearchProvider("core", failure=ProviderUnavailable("core", "server error 503")),
        timeout_seconds=10.0,
    )

    outcome = run_in_virtual_time(service_over(registry).search(REQUEST))

    assert outcome.status is SearchStatus.PARTIAL
    assert outcome.candidates == (METHANE, PERMAFROST)
    assert outcomes(outcome.provider_statuses) == [
        ("openalex", ProviderOutcome.OK),
        ("crossref", ProviderOutcome.TIMEOUT),
        ("core", ProviderOutcome.ERROR),
    ]
    assert [status.error for status in outcome.provider_statuses] == [
        None,
        "crossref: no answer within 10s",
        "core: server error 503",
    ]
    assert outcome.search.provider_set == ("openalex", "crossref", "core")


def test_fan_out_with_every_provider_answering_is_complete() -> None:
    providers = ProvidersOnHand(
        FakeSearchProvider("openalex", default_results=(METHANE,)),
        FakeSearchProvider("crossref", default_results=(METHANE_FROM_CROSSREF,)),
    )

    outcome = run_in_virtual_time(service_over(providers).search(REQUEST))

    assert outcome.status is SearchStatus.COMPLETE
    assert outcome.candidates == (METHANE, METHANE_FROM_CROSSREF)
    assert outcomes(outcome.provider_statuses) == [
        ("openalex", ProviderOutcome.OK),
        ("crossref", ProviderOutcome.OK),
    ]


def test_fan_out_with_no_provider_answering_is_failed_and_still_returns() -> None:
    providers = ProvidersOnHand(
        FakeSearchProvider("openalex", failure=ProviderUnavailable("openalex", "server error 502")),
        FakeSearchProvider("crossref", failure=ProviderTimedOut("crossref", 10.0)),
    )

    outcome = run_in_virtual_time(service_over(providers).search(REQUEST))

    assert outcome.status is SearchStatus.FAILED
    assert outcome.candidates == ()
    assert outcomes(outcome.provider_statuses) == [
        ("openalex", ProviderOutcome.ERROR),
        ("crossref", ProviderOutcome.TIMEOUT),
    ]


@pytest.mark.parametrize(
    ("failure", "expected_outcome", "expected_error"),
    [
        (ProviderTimedOut("crossref", 10.0), ProviderOutcome.TIMEOUT, "crossref: no answer within 10s"),
        (
            ProviderCircuitOpen("crossref", FAKE_EPOCH + timedelta(minutes=1)),
            ProviderOutcome.BREAKER_OPEN,
            "crossref: circuit breaker open after repeated failures; skipped until 2024-01-01T00:01:00+00:00",
        ),
        (
            ProviderRateLimited("crossref", retry_after_seconds=120),
            ProviderOutcome.RATE_LIMITED,
            "crossref: rate limited (retry after 120s)",
        ),
        (
            ProviderUnavailable("crossref", "server error 503"),
            ProviderOutcome.ERROR,
            "crossref: server error 503",
        ),
        (
            ProviderError("crossref", "unreadable answer"),
            ProviderOutcome.ERROR,
            "crossref: unreadable answer",
        ),
    ],
    ids=["timed-out", "breaker-open", "rate-limited", "unavailable", "provider-error"],
)
def test_fan_out_records_each_kind_of_failure_as_its_own_outcome(
    failure: Exception, expected_outcome: ProviderOutcome, expected_error: str
) -> None:
    """Timed out, skipped by an open breaker, rate limited and errored are four different answers."""
    providers = ProvidersOnHand(
        FakeSearchProvider("openalex", default_results=(METHANE,)),
        FakeSearchProvider("crossref", failure=failure),
    )

    outcome = run_in_virtual_time(service_over(providers).search(REQUEST))

    failed = outcome.provider_statuses[1]
    assert (failed.provider, failed.outcome, failed.error) == ("crossref", expected_outcome, expected_error)
    assert failed.response is None
    assert outcome.status is SearchStatus.PARTIAL


def test_fan_out_records_an_untranslated_exception_by_its_type_alone() -> None:
    """Its text was never redacted, so none of it is kept: only that the adapter failed, and how."""
    leaky = FakeSearchProvider("crossref", failure=ValueError("GET https://api.example.org?key=secret-7f3a"))
    providers = ProvidersOnHand(FakeSearchProvider("openalex", default_results=(METHANE,)), leaky)

    outcome = run_in_virtual_time(service_over(providers).search(REQUEST))

    failed = outcome.provider_statuses[1]
    assert failed.outcome is ProviderOutcome.ERROR
    assert failed.error == "crossref: the provider raised ValueError, which it should have translated"
    assert outcome.status is SearchStatus.PARTIAL


def test_fan_out_reports_a_provider_benched_by_its_breaker_as_skipped_not_errored() -> None:
    """Through the real breaker: the first search's failure opens it, the second search is refused."""
    registry = wrapped(
        FakeSearchProvider("openalex", default_results=(METHANE,)),
        FakeSearchProvider("crossref", failure=ProviderUnavailable("crossref", "server error 503")),
        failure_threshold=1,
    )
    service = service_over(registry)

    async def search_twice() -> tuple[list[tuple[str, ProviderOutcome]], list[tuple[str, ProviderOutcome]]]:
        first = await service.search(REQUEST)
        second = await service.search(REQUEST)
        return outcomes(first.provider_statuses), outcomes(second.provider_statuses)

    first, second = run_in_virtual_time(search_twice())

    assert first == [("openalex", ProviderOutcome.OK), ("crossref", ProviderOutcome.ERROR)]
    assert second == [("openalex", ProviderOutcome.OK), ("crossref", ProviderOutcome.BREAKER_OPEN)]


def test_fan_out_reports_a_provider_answering_under_another_name_as_an_error() -> None:
    class Impostor:
        name = "crossref"

        async def search(self, query: ProviderQuery) -> ProviderResponse:
            return ProviderResponse(provider="openalex", results=(METHANE,), elapsed_ms=1.0)

    outcome = run_in_virtual_time(service_over(ProvidersOnHand(Impostor())).search(REQUEST))

    (status,) = outcome.provider_statuses
    assert status.outcome is ProviderOutcome.ERROR
    assert status.error == "crossref: the provider answered as 'openalex'"
    assert outcome.candidates == ()


def test_fan_out_reports_a_requested_provider_that_settings_do_not_enable_as_not_configured() -> None:
    openalex = FakeSearchProvider("openalex", default_results=(METHANE,))
    request = SearchRequest(query="arctic methane feedback", providers=("gdelt", "openalex"))

    outcome = run_in_virtual_time(service_over(ProvidersOnHand(openalex)).search(request))

    assert outcomes(outcome.provider_statuses) == [
        ("gdelt", ProviderOutcome.NOT_CONFIGURED),
        ("openalex", ProviderOutcome.OK),
    ]
    assert outcome.provider_statuses[0].error == "gdelt: not enabled in settings (providers.enabled)"
    assert outcome.status is SearchStatus.PARTIAL
    assert outcome.search.provider_set == ("gdelt", "openalex")


def test_fan_out_asks_only_the_requested_providers_in_the_requested_order() -> None:
    openalex = FakeSearchProvider("openalex", default_results=(METHANE,))
    crossref = FakeSearchProvider("crossref", default_results=(METHANE_FROM_CROSSREF,))
    core = FakeSearchProvider("core", default_results=(METHANE_FROM_CORE,))
    request = SearchRequest(query="arctic methane feedback", providers=("core", "openalex", "core"))

    outcome = run_in_virtual_time(service_over(ProvidersOnHand(openalex, crossref, core)).search(request))

    assert outcomes(outcome.provider_statuses) == [
        ("core", ProviderOutcome.OK),
        ("openalex", ProviderOutcome.OK),
    ]
    assert crossref.queries == []
    assert outcome.candidates == (METHANE_FROM_CORE, METHANE)
    assert outcome.status is SearchStatus.COMPLETE


def test_fan_out_with_no_provider_enabled_is_failed() -> None:
    outcome = run_in_virtual_time(service_over(ProvidersOnHand()).search(REQUEST))

    assert outcome.provider_statuses == ()
    assert outcome.status is SearchStatus.FAILED


def test_fan_out_asks_every_provider_every_query_an_expand_stage_produced() -> None:
    since = FAKE_EPOCH - timedelta(days=14)
    uniqueness = ProviderQuery(query="midterms polling", filters=SearchFilters(since=since))

    class TwoQueries:
        async def run(self, state: SearchState) -> SearchState:
            return state.evolve(queries=(*state.queries, uniqueness))

    openalex = FakeSearchProvider("openalex", default_results=(METHANE,))
    crossref = FakeSearchProvider("crossref", default_results=(METHANE_FROM_CROSSREF,))

    outcome = run_in_virtual_time(
        service_over(ProvidersOnHand(openalex, crossref), expand=TwoQueries()).search(REQUEST)
    )

    original = ProviderQuery(query="arctic methane feedback")
    assert [(status.query, status.provider) for status in outcome.provider_statuses] == [
        (original, "openalex"),
        (original, "crossref"),
        (uniqueness, "openalex"),
        (uniqueness, "crossref"),
    ]
    assert openalex.queries == [original, uniqueness]
    assert crossref.queries == [original, uniqueness]


def test_fan_out_passes_the_requests_filters_to_every_provider() -> None:
    filters = SearchFilters(since=FAKE_EPOCH - timedelta(days=30), max_results=5)
    openalex = FakeSearchProvider("openalex")

    run_in_virtual_time(
        service_over(ProvidersOnHand(openalex)).search(SearchRequest(query="arctic methane", filters=filters))
    )

    assert openalex.queries == [ProviderQuery(query="arctic methane", filters=filters)]


# --------------------------------------------------------------------------------------------
# Fan-out: concurrency and the overall deadline (ac2)
# --------------------------------------------------------------------------------------------


def test_fan_out_takes_as_long_as_the_slowest_provider_not_the_sum_of_them() -> None:
    """3 s, 4 s and 5 s of latency take 5 s together, not 12: the providers run at once."""
    providers = ProvidersOnHand(
        SlowProvider("openalex", 3.0, (METHANE,)),
        SlowProvider("crossref", 4.0, (METHANE_FROM_CROSSREF,)),
        SlowProvider("core", 5.0, (METHANE_FROM_CORE,)),
    )
    service = service_over(providers, deadline_seconds=15.0)

    started = time.perf_counter()
    outcome = run_in_virtual_time(service.search(REQUEST))
    real_seconds = time.perf_counter() - started

    assert outcome.search.updated_at - outcome.search.created_at == timedelta(seconds=5)
    assert [status.elapsed_ms for status in outcome.provider_statuses] == [3000.0, 4000.0, 5000.0]
    assert outcome.status is SearchStatus.COMPLETE
    assert real_seconds < REAL_TIME_BUDGET_SECONDS


def test_fan_out_cuts_off_a_provider_still_running_at_the_deadline_and_keeps_the_others() -> None:
    """The search ends at its 8 s deadline, not at the 60 s provider; the 3 s provider's answer stands."""
    providers = ProvidersOnHand(
        SlowProvider("openalex", 3.0, (METHANE,)),
        SlowProvider("crossref", 60.0, (METHANE_FROM_CROSSREF,)),
    )
    service = service_over(providers, deadline_seconds=8.0)

    started = time.perf_counter()
    outcome = run_in_virtual_time(service.search(REQUEST))
    real_seconds = time.perf_counter() - started

    assert outcome.search.updated_at - outcome.search.created_at == timedelta(seconds=8)
    assert outcomes(outcome.provider_statuses) == [
        ("openalex", ProviderOutcome.OK),
        ("crossref", ProviderOutcome.TIMEOUT),
    ]
    cut_off = outcome.provider_statuses[1]
    assert cut_off.error == "crossref: no answer before the search's 8s deadline"
    assert cut_off.elapsed_ms == 8000.0
    assert outcome.candidates == (METHANE,)
    assert outcome.status is SearchStatus.PARTIAL
    assert real_seconds < REAL_TIME_BUDGET_SECONDS


def test_fan_out_with_every_provider_past_the_deadline_fails_at_the_deadline() -> None:
    providers = ProvidersOnHand(SlowProvider("openalex", 40.0), SlowProvider("crossref", 50.0))

    started = time.perf_counter()
    outcome = run_in_virtual_time(service_over(providers, deadline_seconds=12.0).search(REQUEST))
    real_seconds = time.perf_counter() - started

    assert outcome.search.updated_at - outcome.search.created_at == timedelta(seconds=12)
    assert outcomes(outcome.provider_statuses) == [
        ("openalex", ProviderOutcome.TIMEOUT),
        ("crossref", ProviderOutcome.TIMEOUT),
    ]
    assert outcome.status is SearchStatus.FAILED
    assert real_seconds < REAL_TIME_BUDGET_SECONDS


def test_fan_out_refuses_a_deadline_that_is_not_positive() -> None:
    with pytest.raises(ValueError, match="deadline_seconds must be positive"):
        FanOutStage(ProvidersOnHand(), clock=EventLoopClock(), deadline_seconds=0.0)


# --------------------------------------------------------------------------------------------
# The status rule
# --------------------------------------------------------------------------------------------


def test_search_status_is_complete_only_when_every_call_answered_in_full() -> None:
    assert search_status(
        [build_provider_status(provider="openalex"), build_provider_status(provider="core")]
    ) is (SearchStatus.COMPLETE)


def test_search_status_is_partial_when_an_answer_was_itself_partial() -> None:
    """Some of a provider's feeds failed: the search did not get everything it asked for."""
    partial_answer = ProviderStatus(
        provider="rss",
        query=ProviderQuery(query="arctic methane feedback"),
        outcome=ProviderOutcome.OK,
        elapsed_ms=1.0,
        response=ProviderResponse(
            provider="rss", elapsed_ms=1.0, partial=True, error="feed 2 of 3 timed out"
        ),
    )

    assert search_status([build_provider_status(provider="openalex"), partial_answer]) is SearchStatus.PARTIAL


@pytest.mark.parametrize(
    "outcome", [outcome for outcome in ProviderOutcome if outcome is not ProviderOutcome.OK]
)
def test_search_status_is_partial_when_one_call_did_not_answer(outcome: ProviderOutcome) -> None:
    statuses = [
        build_provider_status(provider="openalex"),
        build_provider_status(provider="core", outcome=outcome),
    ]

    assert search_status(statuses) is SearchStatus.PARTIAL


def test_search_status_is_failed_when_no_call_answered() -> None:
    statuses = [
        build_provider_status(provider="openalex", outcome=ProviderOutcome.TIMEOUT),
        build_provider_status(provider="core", outcome=ProviderOutcome.ERROR),
    ]

    assert search_status(statuses) is SearchStatus.FAILED


def test_search_status_is_failed_when_no_call_was_made() -> None:
    assert search_status([]) is SearchStatus.FAILED


# --------------------------------------------------------------------------------------------
# Storage (ac3)
# --------------------------------------------------------------------------------------------


@pytest.fixture(params=["in-memory", "sqlite"])
def searches(request: pytest.FixtureRequest, tmp_path: Path) -> SearchRepository:
    if request.param == "in-memory":
        return InMemorySearchRepository()
    database = SqliteDatabase.open(tmp_path)
    request.addfinalizer(database.close)
    return SqliteSearchRepository(database)


def test_a_search_and_its_raw_provider_results_reload_by_search_id(searches: SearchRepository) -> None:
    providers = ProvidersOnHand(
        SlowProvider("openalex", 2.0, (METHANE, PERMAFROST)),
        FakeSearchProvider("crossref", failure=ProviderTimedOut("crossref", 10.0)),
    )
    filters = SearchFilters(since=FAKE_EPOCH - timedelta(days=30), max_results=10)
    request = SearchRequest(
        query="arctic methane feedback",
        filters=filters,
        owner_id="0WNER000000000000000000001",
        organization_id="0TEAM000000000000000000001",
    )
    service = service_over(providers, searches=searches)

    async def search_then_reload() -> tuple[
        SearchOutcome, Search, tuple[ProviderStatus, ...], tuple[SearchResult, ...]
    ]:
        outcome = await service.search(request)
        return (
            outcome,
            await searches.get(FIRST_SEARCH_ID),
            await searches.list_provider_statuses(FIRST_SEARCH_ID),
            await searches.list_results(FIRST_SEARCH_ID),
        )

    outcome, stored, statuses, results = run_in_virtual_time(search_then_reload())

    assert stored == outcome.search
    assert stored.search_id == FIRST_SEARCH_ID
    assert stored.query == "arctic methane feedback"
    assert stored.filters == filters
    assert stored.provider_set == ("openalex", "crossref")
    assert stored.status is SearchStatus.PARTIAL
    assert stored.owner_id == "0WNER000000000000000000001"
    assert stored.created_at == FAKE_EPOCH
    assert stored.updated_at == FAKE_EPOCH + timedelta(seconds=2)
    assert stored.revision == 1
    assert statuses == outcome.provider_statuses
    assert outcomes(statuses) == [("openalex", ProviderOutcome.OK), ("crossref", ProviderOutcome.TIMEOUT)]
    assert statuses[0].response is not None
    assert statuses[0].response.results == (METHANE, PERMAFROST)
    assert results == ()


def test_a_ranking_a_rank_stage_produced_is_stored_with_the_search(searches: SearchRepository) -> None:
    ranked = build_search_result(search_id=FIRST_SEARCH_ID, rank=1)

    class RankOne:
        async def run(self, state: SearchState) -> SearchState:
            return state.evolve(results=(ranked,))

    service = service_over(
        ProvidersOnHand(FakeSearchProvider("openalex", default_results=(METHANE,))),
        searches=searches,
        rank=RankOne(),
    )

    async def search_then_reload() -> tuple[tuple[SearchResult, ...], tuple[SearchResult, ...]]:
        outcome = await service.search(REQUEST)
        return outcome.results, await searches.list_results(FIRST_SEARCH_ID)

    returned, stored = run_in_virtual_time(search_then_reload())

    assert returned == (ranked,)
    assert stored == (ranked,)


# --------------------------------------------------------------------------------------------
# The stage pipeline (ac4)
# --------------------------------------------------------------------------------------------


class RecordingStage:
    """Notes that it ran, and what it was handed, then hands on what `change` makes of it."""

    def __init__(
        self,
        name: str,
        log: list[tuple[str, SearchState]],
        change: Callable[[SearchState], SearchState] | None = None,
    ) -> None:
        self._name = name
        self._log = log
        self._change = change

    async def run(self, state: SearchState) -> SearchState:
        self._log.append((self._name, state))
        return state if self._change is None else self._change(state)


def test_the_pipeline_is_expand_fan_out_normalize_rank_in_that_order() -> None:
    service = service_over(ProvidersOnHand())

    assert [name for name, _ in service.pipeline.stages] == [
        StageName.EXPAND,
        StageName.FAN_OUT,
        StageName.NORMALIZE,
        StageName.RANK,
    ]
    assert [name.value for name in StageName] == ["expand", "fan_out", "normalize", "rank"]


def test_the_sibling_tasks_stages_default_to_changing_nothing() -> None:
    service = service_over(
        ProvidersOnHand(FakeSearchProvider("openalex", default_results=(METHANE, PERMAFROST)))
    )

    assert isinstance(service.pipeline.expand, PassThroughStage)
    assert isinstance(service.pipeline.normalize, PassThroughStage)
    assert isinstance(service.pipeline.rank, PassThroughStage)
    assert isinstance(service.pipeline.fan_out, FanOutStage)

    outcome = run_in_virtual_time(service.search(REQUEST))

    assert outcome.candidates == (METHANE, PERMAFROST)
    assert outcome.results == ()


def test_each_stage_runs_once_in_order_and_sees_what_the_one_before_it_produced() -> None:
    log: list[tuple[str, SearchState]] = []
    service = service_over(
        ProvidersOnHand(FakeSearchProvider("openalex", default_results=(METHANE, PERMAFROST))),
        expand=RecordingStage("expand", log),
        normalize=RecordingStage(
            "normalize", log, lambda state: state.evolve(candidates=state.candidates[:1])
        ),
        rank=RecordingStage("rank", log),
    )

    run_in_virtual_time(service.search(REQUEST))

    assert [name for name, _ in log] == ["expand", "normalize", "rank"]
    expand_saw, normalize_saw, rank_saw = (state for _, state in log)
    assert expand_saw.provider_statuses == ()
    assert expand_saw.queries == (ProviderQuery(query="arctic methane feedback"),)
    assert outcomes(normalize_saw.provider_statuses) == [("openalex", ProviderOutcome.OK)]
    assert normalize_saw.candidates == (METHANE, PERMAFROST)
    assert rank_saw.candidates == (METHANE,)


def test_a_stage_swapped_in_changes_the_result_without_any_change_to_the_service() -> None:
    """A stand-in for t02's deduplication: the same paper from two providers becomes one candidate."""

    class KeepFirstPerDoi:
        async def run(self, state: SearchState) -> SearchState:
            seen: dict[str | None, CandidateResult] = {}
            for candidate in state.candidates:
                seen.setdefault(candidate.identifiers.doi, candidate)
            return state.evolve(candidates=tuple(seen.values()))

    providers = ProvidersOnHand(
        FakeSearchProvider("openalex", default_results=(METHANE,)),
        FakeSearchProvider("crossref", default_results=(METHANE_FROM_CROSSREF,)),
    )

    plain = run_in_virtual_time(service_over(providers).search(REQUEST))
    deduplicated = run_in_virtual_time(service_over(providers, normalize=KeepFirstPerDoi()).search(REQUEST))

    assert plain.candidates == (METHANE, METHANE_FROM_CROSSREF)
    assert deduplicated.candidates == (METHANE,)
    assert deduplicated.provider_statuses == plain.provider_statuses


def test_the_outcome_carries_each_providers_health_after_the_search() -> None:
    registry = wrapped(
        FakeSearchProvider("openalex", default_results=(METHANE,)),
        FakeSearchProvider("crossref", failure=ProviderUnavailable("crossref", "server error 503")),
    )

    outcome = run_in_virtual_time(service_over(registry).search(REQUEST))

    assert [
        (health.provider, health.success_count, health.error_count) for health in outcome.provider_health
    ] == [
        ("openalex", 1, 0),
        ("crossref", 0, 1),
    ]
    assert outcome.provider_health[1].last_error == "crossref: server error 503"


# --------------------------------------------------------------------------------------------
# The request
# --------------------------------------------------------------------------------------------


def test_a_request_that_names_providers_names_at_least_one() -> None:
    with pytest.raises(ValidationError, match="names at least one provider"):
        SearchRequest(query="arctic methane feedback", providers=())


def test_a_request_needs_a_query() -> None:
    with pytest.raises(ValidationError):
        SearchRequest(query="  ")
