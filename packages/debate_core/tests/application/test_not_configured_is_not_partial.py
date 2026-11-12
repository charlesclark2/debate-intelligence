"""A provider the profile enables that settings cannot configure is named and not counted (v1-e07-t15).

The PM's rulings of 2026-11-09:

1. A provider settings enable but cannot build, because its key or the contact email is missing, is
   named in the search's record with its cure and left out of the partial reckoning. A search whose
   other providers all answered is COMPLETE; a search in which nothing answered is still FAILED.
2. A provider the request names (`search --providers`) keeps today's rule: not configured makes the
   search PARTIAL. Since v1-e07-t23 its reason carries the cure as well.
3. A list that is configuration (a daily preset's, `providers_named=False`) counts like the enabled
   providers.

A government provider its topic does not list still makes the search PARTIAL whoever chose it. A name
settings do not enable at all did too, until v1-e07-t23 left it out of a preset's reckoning
(`test_configuration_gaps_named_with_their_cure.py`). Expected values are written by hand (working
agreement 6).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

import pytest

from debate_core.application.errors import ProviderUnavailable
from debate_core.application.federated_search import FederatedSearchService, SearchTopics, search_status
from debate_core.application.federated_search_types import SearchOutcome, SearchRequest
from debate_core.application.ports.providers import SearchProvider
from debate_core.application.provider_credentials import missing_credential_cure
from debate_core.domain import SearchStatus
from debate_core.domain.discovery import (
    ProviderHealth,
    ProviderOutcome,
    ProviderQuery,
    ProviderResponse,
    ProviderStatus,
)
from debate_core.testing.builders import build_candidate_result, build_provider_status
from debate_core.testing.fakes.clock_and_ids import FixedClock, SequentialIdGenerator
from debate_core.testing.fakes.persistence import InMemorySearchRepository
from debate_core.testing.fakes.providers import FakeSearchProvider
from debate_core.testing.virtual_time import run_in_virtual_time

NHI: Final = "policy-2026-27-nhi"
TOPICS: Final = SearchTopics(
    known=(NHI, "politics-test-topic"),
    providers={NHI: frozenset({"federal_register", "govinfo"}), "politics-test-topic": frozenset()},
)
MISSING_KEY: Final = "govinfo: no api.data.gov key (DEBATE_PROVIDERS__API_DATA_GOV_KEY)"
"""The registry's reason, as `data_gov.missing_key_reason` words it."""
GOVINFO_CURE: Final = "get a free key at api.data.gov/signup to ask GovInfo"
WITH_CURE: Final = f"{MISSING_KEY}; {GOVINFO_CURE}"

METHANE: Final = build_candidate_result(provider="openalex")
RULE: Final = build_candidate_result(
    provider="federal_register", title="Invented coverage rule", url="https://register.example.org/1"
)


class ProvidersWithoutAKey:
    """The `DiscoveryProviders` port: `providers` built, and `not_configured` enabled but unbuilt."""

    def __init__(self, *providers: SearchProvider, not_configured: Mapping[str, str] | None = None) -> None:
        self._providers = providers
        self._not_configured = dict({"govinfo": MISSING_KEY} if not_configured is None else not_configured)

    @property
    def providers(self) -> tuple[SearchProvider, ...]:
        return self._providers

    @property
    def not_configured(self) -> dict[str, str]:
        return self._not_configured

    def health(self) -> tuple[ProviderHealth, ...]:
        return ()


class Unavailable:
    """A provider that never answers."""

    name = "openalex"

    async def search(self, query: ProviderQuery) -> ProviderResponse:
        raise ProviderUnavailable("openalex", "HTTP 503")


def search(
    providers: ProvidersWithoutAKey, request: SearchRequest
) -> tuple[SearchOutcome, InMemorySearchRepository]:
    searches = InMemorySearchRepository()
    service = FederatedSearchService(
        providers, searches, clock=FixedClock(), ids=SequentialIdGenerator("SRCH"), topics=TOPICS
    )
    return run_in_virtual_time(service.search(request)), searches


def records(outcome: SearchOutcome) -> list[tuple[str, ProviderOutcome, str | None]]:
    return [(status.provider, status.outcome, status.error) for status in outcome.provider_statuses]


def two_answering() -> ProvidersWithoutAKey:
    return ProvidersWithoutAKey(
        FakeSearchProvider("openalex", default_results=(METHANE,)),
        FakeSearchProvider("federal_register", default_results=(RULE,)),
    )


# --------------------------------------------------------------------------------------------
# The status rule
# --------------------------------------------------------------------------------------------


def not_configured(provider: str) -> ProviderStatus:
    return build_provider_status(provider=provider, outcome=ProviderOutcome.NOT_CONFIGURED)


def test_search_status_leaves_out_a_not_configured_provider_it_is_told_not_to_count() -> None:
    statuses = [build_provider_status(provider="openalex"), not_configured("govinfo")]

    assert search_status(statuses, uncounted={"govinfo"}) is SearchStatus.COMPLETE


def test_search_status_counts_a_not_configured_provider_it_is_not_told_to_leave_out() -> None:
    statuses = [build_provider_status(provider="openalex"), not_configured("govinfo")]

    assert search_status(statuses) is SearchStatus.PARTIAL
    assert search_status(statuses, uncounted={"federal_register"}) is SearchStatus.PARTIAL


@pytest.mark.parametrize(
    "outcome",
    [
        outcome
        for outcome in ProviderOutcome
        if outcome not in (ProviderOutcome.OK, ProviderOutcome.NOT_CONFIGURED)
    ],
)
def test_search_status_leaves_out_only_the_not_configured_calls_of_an_uncounted_provider(
    outcome: ProviderOutcome,
) -> None:
    """A provider on the list that was asked and failed is a missing answer like any other."""
    statuses = [
        build_provider_status(provider="openalex"),
        build_provider_status(provider="govinfo", outcome=outcome),
    ]

    assert search_status(statuses, uncounted={"govinfo"}) is SearchStatus.PARTIAL


def test_search_status_is_partial_when_an_answer_beside_an_uncounted_not_configured_one_was_partial() -> None:
    partial_answer = ProviderStatus(
        provider="rss",
        query=ProviderQuery(query="health insurance"),
        outcome=ProviderOutcome.OK,
        elapsed_ms=1.0,
        response=ProviderResponse(provider="rss", elapsed_ms=1.0, partial=True, error="1 of 3 feeds failed"),
    )

    assert (
        search_status([partial_answer, not_configured("govinfo")], uncounted={"govinfo"})
        is SearchStatus.PARTIAL
    )


@pytest.mark.parametrize(
    "others",
    [
        [build_provider_status(provider="openalex", outcome=ProviderOutcome.TIMEOUT)],
        [],
    ],
    ids=["the-other-timed-out", "no-other-provider"],
)
def test_search_status_with_nothing_answered_beside_an_uncounted_not_configured_provider_is_failed(
    others: list[ProviderStatus],
) -> None:
    assert search_status([*others, not_configured("govinfo")], uncounted={"govinfo"}) is SearchStatus.FAILED


# --------------------------------------------------------------------------------------------
# Ruling 1: an enabled provider without its key, on a search that does not name it
# --------------------------------------------------------------------------------------------


def test_an_enabled_provider_without_its_key_not_configured_is_left_out_and_named_with_its_cure() -> None:
    outcome, searches = search(two_answering(), SearchRequest(query="health insurance", topic_id=NHI))

    assert records(outcome) == [
        ("openalex", ProviderOutcome.OK, None),
        ("federal_register", ProviderOutcome.OK, None),
        ("govinfo", ProviderOutcome.NOT_CONFIGURED, WITH_CURE),
    ]
    assert outcome.uncounted == ("govinfo",)
    assert outcome.status is SearchStatus.COMPLETE
    assert outcome.search.provider_set == ("openalex", "federal_register", "govinfo")
    stored = run_in_virtual_time(searches.get(outcome.search.search_id))
    assert stored.status is SearchStatus.COMPLETE


def test_an_enabled_provider_without_its_key_off_its_topic_is_neither_asked_nor_named_not_configured() -> (
    None
):
    """The topic rule is unchanged: a search with no topic selects no government provider at all."""
    outcome, _ = search(two_answering(), SearchRequest(query="health insurance"))

    assert records(outcome) == [("openalex", ProviderOutcome.OK, None)]
    assert outcome.uncounted == ()
    assert outcome.status is SearchStatus.COMPLETE


def test_nothing_answered_beside_an_uncounted_not_configured_provider_is_failed() -> None:
    providers = ProvidersWithoutAKey(Unavailable())

    outcome, _ = search(providers, SearchRequest(query="health insurance", topic_id=NHI))

    assert records(outcome) == [
        ("openalex", ProviderOutcome.ERROR, "openalex: HTTP 503"),
        ("govinfo", ProviderOutcome.NOT_CONFIGURED, WITH_CURE),
    ]
    assert outcome.uncounted == ("govinfo",)
    assert outcome.status is SearchStatus.FAILED


def test_a_search_whose_only_provider_is_not_configured_is_failed() -> None:
    outcome, _ = search(ProvidersWithoutAKey(), SearchRequest(query="health insurance", topic_id=NHI))

    assert records(outcome) == [("govinfo", ProviderOutcome.NOT_CONFIGURED, WITH_CURE)]
    assert outcome.status is SearchStatus.FAILED


# --------------------------------------------------------------------------------------------
# Ruling 2: a provider the student names keeps today's rule
# --------------------------------------------------------------------------------------------


def test_a_provider_named_by_the_request_without_its_key_not_configured_keeps_the_search_partial() -> None:
    request = SearchRequest(query="health insurance", topic_id=NHI, providers=("openalex", "govinfo"))

    outcome, searches = search(two_answering(), request)

    assert records(outcome) == [
        ("openalex", ProviderOutcome.OK, None),
        ("govinfo", ProviderOutcome.NOT_CONFIGURED, WITH_CURE),
    ]
    assert outcome.uncounted == ()
    assert outcome.status is SearchStatus.PARTIAL
    assert run_in_virtual_time(searches.get(outcome.search.search_id)).status is SearchStatus.PARTIAL


# --------------------------------------------------------------------------------------------
# Ruling 3: a list that is configuration counts like the enabled providers
# --------------------------------------------------------------------------------------------


def test_a_preset_list_without_a_providers_key_not_configured_is_left_out_like_an_enabled_one() -> None:
    request = SearchRequest(
        query="health insurance", topic_id=NHI, providers=("openalex", "govinfo"), providers_named=False
    )

    outcome, _ = search(two_answering(), request)

    assert records(outcome) == [
        ("openalex", ProviderOutcome.OK, None),
        ("govinfo", ProviderOutcome.NOT_CONFIGURED, WITH_CURE),
    ]
    assert outcome.uncounted == ("govinfo",)
    assert outcome.status is SearchStatus.COMPLETE


def test_a_preset_list_naming_a_provider_settings_do_not_enable_is_uncounted_not_configured() -> None:
    """Not enabled at all was counted under v1-e07-t15's narrow reading of ruling 1; v1-e07-t23 (the PM's
    ruling on its follow-up 1) makes it configuration too, named with `enable it in providers.enabled`."""
    request = SearchRequest(query="health insurance", providers=("openalex", "gdelt"), providers_named=False)

    outcome, _ = search(two_answering(), request)

    assert records(outcome) == [
        ("openalex", ProviderOutcome.OK, None),
        (
            "gdelt",
            ProviderOutcome.NOT_CONFIGURED,
            "gdelt: not enabled in settings (providers.enabled); enable it in providers.enabled",
        ),
    ]
    assert outcome.uncounted == ("gdelt",)
    assert outcome.status is SearchStatus.COMPLETE


def test_a_preset_list_naming_a_government_provider_off_its_topic_is_still_partial_not_configured() -> None:
    request = SearchRequest(
        query="health insurance",
        topic_id="politics-test-topic",
        providers=("openalex", "govinfo"),
        providers_named=False,
    )

    outcome, _ = search(two_answering(), request)

    assert records(outcome) == [
        ("openalex", ProviderOutcome.OK, None),
        (
            "govinfo",
            ProviderOutcome.NOT_CONFIGURED,
            "govinfo: asked only for a search on a topic that lists it, and politics-test-topic does not",
        ),
    ]
    assert outcome.uncounted == ()
    assert outcome.status is SearchStatus.PARTIAL


def test_providers_named_not_configured_rule_is_left_out_of_a_requests_json_unless_false() -> None:
    named = SearchRequest(query="q", providers=("openalex",))
    preset = SearchRequest(query="q", providers=("openalex",), providers_named=False)

    assert "providers_named" not in named.model_dump(mode="json")
    assert preset.model_dump(mode="json")["providers_named"] is False


# --------------------------------------------------------------------------------------------
# The cure, in provider_credentials' words
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("provider", "cure"),
    [
        ("govinfo", GOVINFO_CURE),
        ("crossref", "set a contact email for Crossref's polite pool"),
        ("openalex", "set an OpenAlex key for a higher daily allowance"),
        (
            "semantic_scholar",
            "request one through the form on Semantic Scholar's API page, semanticscholar.org/product/api",
        ),
        ("rss", None),
        ("federal_register", None),
        ("gdelt", None),
        ("no-such-provider", None),
    ],
)
def test_missing_credential_cure_for_a_not_configured_provider(provider: str, cure: str | None) -> None:
    assert missing_credential_cure(provider) == cure
