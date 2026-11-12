"""The search presenter on a provider settings enable but cannot configure (v1-e07-t15).

The outcome is a real search: the service's fan-out over stand-in providers, with GovInfo enabled and
unbuilt for want of its key, on a topic that lists it. Nothing is hidden: GovInfo keeps its line, its
`providers` entry and its reason, in the same place as before, and its reason says it was not counted
as partial and how to cure it. Every expected line and key is written by hand (working agreement 6).
"""

from __future__ import annotations

from typing import Any, Final

from debate_cli.exit_codes import ExitCode, exit_code_for_search
from debate_cli.presenters.search_presenter import footer_lines, outcome_failure, search_payload
from debate_core.application.federated_search import FederatedSearchService, SearchTopics
from debate_core.application.federated_search_types import SearchOutcome, SearchRequest
from debate_core.application.ports.providers import SearchProvider
from debate_core.domain.discovery import ProviderHealth
from debate_core.testing.builders import build_candidate_result
from debate_core.testing.fakes.clock_and_ids import FixedClock, SequentialIdGenerator
from debate_core.testing.fakes.persistence import InMemorySearchRepository
from debate_core.testing.fakes.providers import FakeSearchProvider
from debate_core.testing.virtual_time import run_in_virtual_time

NHI: Final = "policy-2026-27-nhi"
TOPICS: Final = SearchTopics(known=(NHI,), providers={NHI: frozenset({"govinfo"})})
MISSING_KEY: Final = "govinfo: no api.data.gov key (DEBATE_PROVIDERS__API_DATA_GOV_KEY)"
UNCOUNTED_LINE: Final = (
    "  govinfo: not configured: not counted as partial: no api.data.gov key "
    "(DEBATE_PROVIDERS__API_DATA_GOV_KEY); get a free key at api.data.gov/signup to ask GovInfo"
)
UNCOUNTED_REASON: Final = (
    "not counted as partial: no api.data.gov key (DEBATE_PROVIDERS__API_DATA_GOV_KEY); "
    "get a free key at api.data.gov/signup to ask GovInfo"
)


class WithoutGovInfosKey:
    def __init__(self, *providers: SearchProvider) -> None:
        self._providers = providers

    @property
    def providers(self) -> tuple[SearchProvider, ...]:
        return self._providers

    @property
    def not_configured(self) -> dict[str, str]:
        return {"govinfo": MISSING_KEY}

    def health(self) -> tuple[ProviderHealth, ...]:
        return ()


def outcome_of(request: SearchRequest, *, results: bool = True) -> SearchOutcome:
    found = (build_candidate_result(provider="openalex"),) if results else ()
    service = FederatedSearchService(
        WithoutGovInfosKey(FakeSearchProvider("openalex", default_results=found)),
        InMemorySearchRepository(),
        clock=FixedClock(),
        ids=SequentialIdGenerator("SRCH"),
        topics=TOPICS,
    )
    return run_in_virtual_time(service.search(request))


def providers_json(outcome: SearchOutcome) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = search_payload(outcome)["providers"]  # type: ignore[assignment]
    return entries


def test_footer_names_an_enabled_provider_not_configured_with_its_cure_under_a_complete_heading() -> None:
    outcome = outcome_of(SearchRequest(query="health insurance", topic_id=NHI))

    assert footer_lines(outcome) == ["Providers: COMPLETE", "  openalex: ok, 1 result", UNCOUNTED_LINE]


def test_json_keeps_the_not_configured_provider_with_its_cure_in_reasons_and_calls() -> None:
    outcome = outcome_of(SearchRequest(query="health insurance", topic_id=NHI))
    payload = search_payload(outcome)

    assert payload["status"] == "COMPLETE"
    assert providers_json(outcome) == [
        {"provider": "openalex", "outcome": "ok", "queries": 1, "failed": 0, "results": 1, "reasons": []},
        {
            "provider": "govinfo",
            "outcome": "not configured",
            "queries": 1,
            "failed": 1,
            "results": 0,
            "reasons": [UNCOUNTED_REASON],
        },
    ]
    calls: list[dict[str, Any]] = payload["provider_calls"]  # type: ignore[assignment]
    assert [(call["provider"], call["outcome"], call["error"]) for call in calls] == [
        ("openalex", "ok", None),
        (
            "govinfo",
            "not_configured",
            f"{MISSING_KEY}; get a free key at api.data.gov/signup to ask GovInfo",
        ),
    ]


def test_with_no_results_an_uncounted_not_configured_provider_exits_7_and_says_who_was_asked() -> None:
    outcome = outcome_of(SearchRequest(query="health insurance", topic_id=NHI), results=False)

    assert exit_code_for_search(outcome) is ExitCode.NO_RESULTS
    failure = outcome_failure(outcome, search_payload(outcome), ExitCode.NO_RESULTS)
    assert failure.message == 'every provider asked answered, and nothing matched "health insurance"'
    assert failure.panel_details == {
        "openalex": "ok, 0 results",
        "govinfo": f"not configured: {UNCOUNTED_REASON}",
    }


def test_a_provider_named_with_providers_not_configured_keeps_the_partial_footer_and_gains_its_cure() -> None:
    """v1-e07-t15's ruling 2 holds (PARTIAL); since v1-e07-t23 the named provider's reason carries the
    cure too, and still says nothing of `not counted as partial`."""
    outcome = outcome_of(
        SearchRequest(query="health insurance", topic_id=NHI, providers=("openalex", "govinfo"))
    )

    assert footer_lines(outcome) == [
        "Providers: PARTIAL, results may be missing",
        "  openalex: ok, 1 result",
        "  govinfo: not configured: no api.data.gov key (DEBATE_PROVIDERS__API_DATA_GOV_KEY); "
        "get a free key at api.data.gov/signup to ask GovInfo",
    ]
    assert exit_code_for_search(outcome) is ExitCode.SEARCH_PARTIAL
