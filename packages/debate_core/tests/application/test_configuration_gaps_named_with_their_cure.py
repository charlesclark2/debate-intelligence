"""Missing only configuration: named with its cure, and counted only when a person asked (v1-e07-t23).

The PM's rulings of 2026-11-11 on v1-e07-t15's follow-ups, and of 2026-11-12 on v1-e07-t20's:

1. A daily preset's provider that settings do not enable at all is configuration too: its reason ends
   with `enable it in providers.enabled`, and the search's status leaves it out (`uncounted`).
2. A provider a person names with `--providers` that lacks its key gets its cure in its reason as well,
   and still makes the search PARTIAL. A named provider settings do not enable gets its cure the same way.
3. :func:`partial_providers`, which `batch report`'s `partial_providers` reads, leaves out the providers
   the search did not count. They stay in the record, with their reasons.

"A person asked" means named with `--providers` (`providers_named=True`); a preset or the settings'
selection is not a person's ask. A government provider its topic does not list is still counted, as
before. Expected values are written by hand (working agreement 6).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from debate_core.application.errors import ProviderUnavailable
from debate_core.application.federated_search import (
    NOT_ENABLED_CURE,
    FederatedSearchService,
    SearchTopics,
    partial_providers,
    search_status,
)
from debate_core.application.federated_search_types import SearchOutcome, SearchRequest
from debate_core.application.ports.providers import SearchProvider
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
GOVINFO_WITH_CURE: Final = f"{MISSING_KEY}; get a free key at api.data.gov/signup to ask GovInfo"
S2_MISSING_KEY: Final = (
    "semantic_scholar: no Semantic Scholar key (DEBATE_PROVIDERS__SEMANTIC_SCHOLAR_API_KEY)"
)
S2_WITH_CURE: Final = (
    f"{S2_MISSING_KEY}; request one through the form on Semantic Scholar's API page, "
    "semanticscholar.org/product/api"
)
GDELT_NOT_ENABLED: Final = (
    "gdelt: not enabled in settings (providers.enabled); enable it in providers.enabled"
)
GOOGLE_NEWS_NOT_ENABLED: Final = (
    "google_news: not enabled in settings (providers.enabled); enable it in providers.enabled"
)
FEDERAL_REGISTER_OFF_TOPIC: Final = (
    "federal_register: asked only for a search on a topic that lists it, and politics-test-topic does not"
)

METHANE: Final = build_candidate_result(provider="openalex")


class ProvidersOnHand:
    """The `DiscoveryProviders` port: `providers` built, `not_configured` enabled but unbuilt."""

    def __init__(self, *providers: SearchProvider, not_configured: Mapping[str, str] | None = None) -> None:
        self._providers = providers
        self._not_configured = dict(
            {"govinfo": MISSING_KEY, "semantic_scholar": S2_MISSING_KEY}
            if not_configured is None
            else not_configured
        )

    @property
    def providers(self) -> tuple[SearchProvider, ...]:
        return self._providers

    @property
    def not_configured(self) -> dict[str, str]:
        return self._not_configured

    def health(self) -> tuple[ProviderHealth, ...]:
        return ()


class Unavailable:
    """OpenAlex, never answering."""

    name = "openalex"

    async def search(self, query: ProviderQuery) -> ProviderResponse:
        raise ProviderUnavailable("openalex", "HTTP 503")


def openalex_answering() -> ProvidersOnHand:
    return ProvidersOnHand(FakeSearchProvider("openalex", default_results=(METHANE,)))


def search(providers: ProvidersOnHand, request: SearchRequest) -> tuple[SearchOutcome, SearchStatus]:
    """The outcome, and the status the search was stored with."""
    searches = InMemorySearchRepository()
    service = FederatedSearchService(
        providers, searches, clock=FixedClock(), ids=SequentialIdGenerator("SRCH"), topics=TOPICS
    )
    outcome = run_in_virtual_time(service.search(request))
    return outcome, run_in_virtual_time(searches.get(outcome.search.search_id)).status


def records(outcome: SearchOutcome) -> list[tuple[str, ProviderOutcome, str | None]]:
    return [(status.provider, status.outcome, status.error) for status in outcome.provider_statuses]


def preset(*providers: str, topic_id: str | None = None) -> SearchRequest:
    return SearchRequest(
        query="health insurance", topic_id=topic_id, providers=providers, providers_named=False
    )


def named(*providers: str, topic_id: str | None = None) -> SearchRequest:
    return SearchRequest(query="health insurance", topic_id=topic_id, providers=providers)


# --------------------------------------------------------------------------------------------
# Ruling 1: a preset's provider that settings do not enable
# --------------------------------------------------------------------------------------------


def test_a_preset_provider_settings_do_not_enable_is_uncounted_and_named_with_its_cure() -> None:
    outcome, stored = search(openalex_answering(), preset("openalex", "gdelt"))

    assert records(outcome) == [
        ("openalex", ProviderOutcome.OK, None),
        ("gdelt", ProviderOutcome.NOT_CONFIGURED, GDELT_NOT_ENABLED),
    ]
    assert outcome.uncounted == ("gdelt",)
    assert (outcome.status, stored) == (SearchStatus.COMPLETE, SearchStatus.COMPLETE)
    assert outcome.search.provider_set == ("openalex", "gdelt")


def test_a_preset_naming_providers_not_enabled_and_without_a_key_leaves_every_one_uncounted_in_order() -> (
    None
):
    outcome, stored = search(
        openalex_answering(), preset("google_news", "openalex", "govinfo", "gdelt", topic_id=NHI)
    )

    assert records(outcome) == [
        ("google_news", ProviderOutcome.NOT_CONFIGURED, GOOGLE_NEWS_NOT_ENABLED),
        ("openalex", ProviderOutcome.OK, None),
        ("govinfo", ProviderOutcome.NOT_CONFIGURED, GOVINFO_WITH_CURE),
        ("gdelt", ProviderOutcome.NOT_CONFIGURED, GDELT_NOT_ENABLED),
    ]
    assert outcome.uncounted == ("google_news", "govinfo", "gdelt")
    assert (outcome.status, stored) == (SearchStatus.COMPLETE, SearchStatus.COMPLETE)


def test_a_preset_provider_not_enabled_beside_one_that_failed_leaves_the_search_failed_not_configured() -> (
    None
):
    outcome, stored = search(ProvidersOnHand(Unavailable()), preset("openalex", "gdelt"))

    assert records(outcome) == [
        ("openalex", ProviderOutcome.ERROR, "openalex: HTTP 503"),
        ("gdelt", ProviderOutcome.NOT_CONFIGURED, GDELT_NOT_ENABLED),
    ]
    assert outcome.uncounted == ("gdelt",)
    assert (outcome.status, stored) == (SearchStatus.FAILED, SearchStatus.FAILED)


def test_a_preset_whose_every_provider_is_not_enabled_asks_nothing_and_is_failed_not_configured() -> None:
    outcome, _ = search(ProvidersOnHand(), preset("gdelt"))

    assert records(outcome) == [("gdelt", ProviderOutcome.NOT_CONFIGURED, GDELT_NOT_ENABLED)]
    assert outcome.uncounted == ("gdelt",)
    assert outcome.status is SearchStatus.FAILED


def test_a_preset_government_provider_not_enabled_and_off_its_topic_is_still_counted_not_configured() -> None:
    """The topic rule is unchanged: off its topic, a government provider is a refusal, not configuration."""
    outcome, stored = search(
        openalex_answering(), preset("openalex", "federal_register", topic_id="politics-test-topic")
    )

    assert records(outcome) == [
        ("openalex", ProviderOutcome.OK, None),
        ("federal_register", ProviderOutcome.NOT_CONFIGURED, FEDERAL_REGISTER_OFF_TOPIC),
    ]
    assert outcome.uncounted == ()
    assert (outcome.status, stored) == (SearchStatus.PARTIAL, SearchStatus.PARTIAL)


# --------------------------------------------------------------------------------------------
# Ruling 2: a provider a person names keeps the search partial, and now carries its cure
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("provider", "reason", "topic_id"),
    [
        ("govinfo", GOVINFO_WITH_CURE, NHI),
        ("semantic_scholar", S2_WITH_CURE, None),
        ("gdelt", GDELT_NOT_ENABLED, None),
    ],
    ids=["govinfo-without-its-key", "semantic-scholar-without-its-key", "gdelt-not-enabled"],
)
def test_a_named_provider_not_configured_is_named_with_its_cure_and_keeps_the_search_partial(
    provider: str, reason: str, topic_id: str | None
) -> None:
    outcome, stored = search(openalex_answering(), named("openalex", provider, topic_id=topic_id))

    assert records(outcome) == [
        ("openalex", ProviderOutcome.OK, None),
        (provider, ProviderOutcome.NOT_CONFIGURED, reason),
    ]
    assert outcome.uncounted == ()
    assert (outcome.status, stored) == (SearchStatus.PARTIAL, SearchStatus.PARTIAL)


def test_a_named_provider_without_a_cure_keeps_the_registrys_reason_alone_not_configured() -> None:
    """A provider provider_credentials knows no cure for (here a keyless one the registry refused) keeps
    the registry's words, with nothing after them."""
    providers = ProvidersOnHand(
        FakeSearchProvider("openalex", default_results=(METHANE,)),
        not_configured={"rss": "rss: no feed list (invented for this test)"},
    )

    outcome, _ = search(providers, named("openalex", "rss"))

    assert records(outcome)[1] == (
        "rss",
        ProviderOutcome.NOT_CONFIGURED,
        "rss: no feed list (invented for this test)",
    )
    assert outcome.status is SearchStatus.PARTIAL


def test_not_enabled_cure_is_the_pms_words_not_configured() -> None:
    assert NOT_ENABLED_CURE == "enable it in providers.enabled"


# --------------------------------------------------------------------------------------------
# Ruling 3: partial_providers leaves out what the status left out
# --------------------------------------------------------------------------------------------


def not_configured(provider: str) -> ProviderStatus:
    return build_provider_status(provider=provider, outcome=ProviderOutcome.NOT_CONFIGURED)


def answered_in_part(provider: str) -> ProviderStatus:
    return ProviderStatus(
        provider=provider,
        query=ProviderQuery(query="health insurance"),
        outcome=ProviderOutcome.OK,
        elapsed_ms=1.0,
        response=ProviderResponse(
            provider=provider, elapsed_ms=1.0, partial=True, error="1 of 3 feeds failed"
        ),
    )


def test_partial_providers_leaves_out_an_uncounted_not_configured_provider() -> None:
    statuses = [
        build_provider_status(provider="openalex"),
        not_configured("govinfo"),
        not_configured("gdelt"),
    ]

    assert partial_providers(statuses, uncounted={"govinfo", "gdelt"}) == ()
    assert partial_providers(statuses, uncounted={"gdelt"}) == ("govinfo",)
    assert partial_providers(statuses) == ("govinfo", "gdelt")


@pytest.mark.parametrize(
    "outcome",
    [
        outcome
        for outcome in ProviderOutcome
        if outcome not in (ProviderOutcome.OK, ProviderOutcome.NOT_CONFIGURED)
    ],
)
def test_partial_providers_keeps_an_uncounted_providers_other_failures(outcome: ProviderOutcome) -> None:
    """As in :func:`search_status`, only the `not_configured` calls of an uncounted provider are left out."""
    statuses = [
        build_provider_status(provider="openalex"),
        not_configured("govinfo"),
        build_provider_status(provider="govinfo", outcome=outcome),
    ]

    assert partial_providers(statuses, uncounted={"govinfo"}) == ("govinfo",)


def test_partial_providers_names_each_provider_once_in_the_order_first_asked() -> None:
    statuses = [
        answered_in_part("rss"),
        build_provider_status(provider="openalex", outcome=ProviderOutcome.TIMEOUT),
        not_configured("govinfo"),
        answered_in_part("rss"),
        build_provider_status(provider="crossref"),
        build_provider_status(provider="openalex", outcome=ProviderOutcome.ERROR),
    ]

    assert partial_providers(statuses, uncounted={"govinfo"}) == ("rss", "openalex")


def test_partial_providers_of_a_real_search_leaves_out_its_uncounted_providers() -> None:
    outcome, _ = search(ProvidersOnHand(Unavailable()), preset("openalex", "govinfo", "gdelt", topic_id=NHI))

    assert outcome.uncounted == ("govinfo", "gdelt")
    assert partial_providers(outcome.provider_statuses, uncounted=outcome.uncounted) == ("openalex",)


_PROVIDERS: Final = ("openalex", "crossref", "govinfo")
_FAILURES: Final = tuple(
    outcome
    for outcome in ProviderOutcome
    if outcome not in (ProviderOutcome.OK, ProviderOutcome.NOT_CONFIGURED)
)


def call(provider: str, outcome: ProviderOutcome | None) -> ProviderStatus:
    """One call: `outcome`, or an answer in part when None."""
    if outcome is None:
        return answered_in_part(provider)
    return build_provider_status(provider=provider, outcome=outcome)


_CALL: Final = st.builds(
    call,
    st.sampled_from(_PROVIDERS),
    # Weighted toward answers and not_configured calls: a search that is COMPLETE only because an
    # uncounted provider is left out needs both, and no other failure.
    st.sampled_from([*[ProviderOutcome.OK] * 6, *[ProviderOutcome.NOT_CONFIGURED] * 4, *_FAILURES, None]),
)


@settings(max_examples=300)
@given(
    statuses=st.lists(_CALL, min_size=1, max_size=4),
    uncounted=st.sets(st.sampled_from(_PROVIDERS), min_size=1),
)
def test_partial_providers_is_empty_exactly_when_a_search_that_got_an_answer_is_complete(
    statuses: list[ProviderStatus], uncounted: set[str]
) -> None:
    """For every status but FAILED: COMPLETE, and only COMPLETE, has no partial provider."""
    status = search_status(statuses, uncounted=uncounted)
    event(f"status {status.value}")
    if status is SearchStatus.COMPLETE and partial_providers(statuses):
        event("complete only because an uncounted provider is left out")

    if status is not SearchStatus.FAILED:
        assert (status is SearchStatus.COMPLETE) == (partial_providers(statuses, uncounted=uncounted) == ())
