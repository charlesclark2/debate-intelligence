"""The presenters on providers missing only configuration (v1-e07-t23).

Each outcome is a real search: the service's fan-out over stand-in providers. The presenters render
what `debate_core` decided, so these tests check the words and the JSON:

* when no provider was asked, `search`'s and `daily`'s message names each selected provider on a line
  of its own, as the footer names it: not enabled with `enable it in providers.enabled`, or enabled
  and not configured with its reason and cure (the PM's ruling of 2026-11-12 on v1-e07-t20's
  follow-up 2). The code and exit stay `NO_PROVIDER_ENABLED`, 1;
* `partial_providers`, in `search --auto-cut`'s and `daily --auto-cut`'s report, leaves out the
  providers the status did not count, which stay in `providers` with their reasons.

Every expected line and key is written by hand (working agreement 6).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Final

from debate_cli.exit_codes import ExitCode, exit_code_for_search
from debate_cli.presenters.batch_report_presenter import AutoCutFiles, AutoCutSettings, report_payload
from debate_cli.presenters.daily_presenter import auto_cut_payload, digest_failure, exit_code_for_digest
from debate_cli.presenters.search_presenter import outcome_failure, search_payload
from debate_core.application.batch_cut_service import BatchNeed, BatchReport, BatchStopReason
from debate_core.application.digest_service import Digest, DigestWindow
from debate_core.application.errors import ProviderUnavailable
from debate_core.application.federated_search import FederatedSearchService, SearchTopics
from debate_core.application.federated_search_types import SearchOutcome, SearchRequest
from debate_core.application.ports.providers import SearchProvider
from debate_core.domain.daily_preset import DailyPair, DailyPreset
from debate_core.domain.discovery import ProviderHealth, ProviderQuery, ProviderResponse
from debate_core.testing.builders import build_candidate_result
from debate_core.testing.fakes.clock_and_ids import FixedClock, SequentialIdGenerator
from debate_core.testing.fakes.persistence import InMemorySearchRepository
from debate_core.testing.fakes.providers import FakeSearchProvider
from debate_core.testing.virtual_time import run_in_virtual_time

NHI: Final = "policy-2026-27-nhi"
TOPICS: Final = SearchTopics(known=(NHI,), providers={NHI: frozenset({"govinfo"})})
GOVINFO_MISSING_KEY: Final = "govinfo: no api.data.gov key (DEBATE_PROVIDERS__API_DATA_GOV_KEY)"
S2_MISSING_KEY: Final = (
    "semantic_scholar: no Semantic Scholar key (DEBATE_PROVIDERS__SEMANTIC_SCHOLAR_API_KEY)"
)

S2_UNCOUNTED_LINE: Final = (
    "semantic_scholar: not configured: not counted as partial: no Semantic Scholar key "
    "(DEBATE_PROVIDERS__SEMANTIC_SCHOLAR_API_KEY); request one through the form on Semantic Scholar's "
    "API page, semanticscholar.org/product/api"
)
GOVINFO_NAMED_LINE: Final = (
    "govinfo: not configured: no api.data.gov key (DEBATE_PROVIDERS__API_DATA_GOV_KEY); "
    "get a free key at api.data.gov/signup to ask GovInfo"
)
GDELT_NAMED_LINE: Final = (
    "gdelt: not configured: not enabled in settings (providers.enabled); enable it in providers.enabled"
)


class ProvidersOnHand:
    def __init__(self, *providers: SearchProvider) -> None:
        self._providers = providers

    @property
    def providers(self) -> tuple[SearchProvider, ...]:
        return self._providers

    @property
    def not_configured(self) -> dict[str, str]:
        return {"govinfo": GOVINFO_MISSING_KEY, "semantic_scholar": S2_MISSING_KEY}

    def health(self) -> tuple[ProviderHealth, ...]:
        return ()


class NoProviders(ProvidersOnHand):
    """Settings that enable nothing, and leave nothing unbuilt."""

    @property
    def not_configured(self) -> dict[str, str]:
        return {}


class FailingRss:
    name = "rss"

    async def search(self, query: ProviderQuery) -> ProviderResponse:
        raise ProviderUnavailable("rss", "HTTP 500")


def outcome_of(providers: ProvidersOnHand, request: SearchRequest) -> SearchOutcome:
    service = FederatedSearchService(
        providers,
        InMemorySearchRepository(),
        clock=FixedClock(),
        ids=SequentialIdGenerator("SRCH"),
        topics=TOPICS,
    )
    return run_in_virtual_time(service.search(request))


def openalex_and_failing_rss() -> ProvidersOnHand:
    return ProvidersOnHand(
        FakeSearchProvider("openalex", default_results=(build_candidate_result(provider="openalex"),)),
        FailingRss(),
    )


# --------------------------------------------------------------------------------------------
# No provider was asked: each one named with its own state
# --------------------------------------------------------------------------------------------


def test_no_provider_asked_names_an_enabled_provider_not_configured_with_its_reason_and_cure() -> None:
    """A keyless Semantic Scholar, the only provider settings select: enabled, so never "none of
    semantic_scholar is enabled"."""
    outcome = outcome_of(ProvidersOnHand(), SearchRequest(query="health insurance"))

    assert exit_code_for_search(outcome) is ExitCode.DOMAIN_FAILURE
    failure = outcome_failure(outcome, search_payload(outcome), ExitCode.DOMAIN_FAILURE)
    assert (failure.code, failure.exit_code) == ("NO_PROVIDER_ENABLED", ExitCode.DOMAIN_FAILURE)
    assert failure.message == f"no provider was asked:\n  {S2_UNCOUNTED_LINE}"
    assert failure.panel_message == "no provider was asked"
    assert failure.panel_details == {"semantic_scholar": S2_UNCOUNTED_LINE.removeprefix("semantic_scholar: ")}
    assert "is enabled" not in failure.message


def test_no_provider_asked_names_each_named_provider_not_configured_on_a_line_of_its_own() -> None:
    """Named with --providers: GDELT, not enabled, with `enable it in providers.enabled`; GovInfo,
    enabled without its key, with its reason and cure. In the order asked."""
    request = SearchRequest(query="health insurance", topic_id=NHI, providers=("gdelt", "govinfo"))
    outcome = outcome_of(ProvidersOnHand(), request)

    assert exit_code_for_search(outcome) is ExitCode.DOMAIN_FAILURE
    payload = search_payload(outcome)
    failure = outcome_failure(outcome, payload, ExitCode.DOMAIN_FAILURE)
    assert failure.code == "NO_PROVIDER_ENABLED"
    assert failure.message == f"no provider was asked:\n  {GDELT_NAMED_LINE}\n  {GOVINFO_NAMED_LINE}"
    assert failure.panel_details == {
        "gdelt": GDELT_NAMED_LINE.removeprefix("gdelt: "),
        "govinfo": GOVINFO_NAMED_LINE.removeprefix("govinfo: "),
    }
    providers: list[dict[str, Any]] = payload["providers"]  # type: ignore[assignment]
    assert [(entry["provider"], entry["outcome"], entry["reasons"]) for entry in providers] == [
        (
            "gdelt",
            "not configured",
            ["not enabled in settings (providers.enabled); enable it in providers.enabled"],
        ),
        (
            "govinfo",
            "not configured",
            [
                "no api.data.gov key (DEBATE_PROVIDERS__API_DATA_GOV_KEY); "
                "get a free key at api.data.gov/signup to ask GovInfo"
            ],
        ),
    ]
    assert failure.details == payload


def test_no_provider_asked_when_settings_enable_none_says_so_not_configured() -> None:
    outcome = outcome_of(NoProviders(), SearchRequest(query="health insurance"))

    assert exit_code_for_search(outcome) is ExitCode.DOMAIN_FAILURE
    failure = outcome_failure(outcome, search_payload(outcome), ExitCode.DOMAIN_FAILURE)
    assert failure.code == "NO_PROVIDER_ENABLED"
    assert failure.message == "no provider was asked: no provider is enabled; enable one in providers.enabled"
    assert failure.panel_message is None


# --------------------------------------------------------------------------------------------
# daily
# --------------------------------------------------------------------------------------------

PRESET: Final = DailyPreset(
    name="politics",
    label="Politics",
    description="An invented preset for this test.",
    queries=("health insurance",),
    pairs=(DailyPair(argument="politics-da", need="uniqueness"),),
    providers=("gdelt",),
)
DAY: Final = date(2026, 9, 17)


def digest_of(*outcomes: SearchOutcome) -> Digest:
    return Digest(
        preset=PRESET,
        day=DAY,
        window=DigestWindow(),
        since=datetime(2026, 9, 17, tzinfo=UTC),
        until=datetime(2026, 9, 18, tzinfo=UTC),
        groups=(),
        outcomes=outcomes,
        listed_before=0,
        feed_topics=(),
    )


def test_a_digest_that_asked_no_provider_names_each_preset_provider_not_configured_with_its_cure() -> None:
    """A preset provider settings do not enable is uncounted (ruling 1), so its line says so too."""
    request = SearchRequest(query="health insurance", providers=("gdelt",), providers_named=False)
    digest = digest_of(outcome_of(ProvidersOnHand(), request))

    assert exit_code_for_digest(digest) is ExitCode.DOMAIN_FAILURE
    failure = digest_failure(digest, {}, ExitCode.DOMAIN_FAILURE)
    assert failure.code == "NO_PROVIDER_ENABLED"
    assert failure.message == (
        "no provider was asked, so no digest was written:\n"
        "  gdelt: not configured: not counted as partial: not enabled in settings (providers.enabled); "
        "enable it in providers.enabled"
    )
    assert failure.panel_message == "no provider was asked, so no digest was written"
    assert failure.panel_details == {
        "gdelt": "not configured: not counted as partial: not enabled in settings (providers.enabled); "
        "enable it in providers.enabled"
    }


# --------------------------------------------------------------------------------------------
# partial_providers
# --------------------------------------------------------------------------------------------

REPORT: Final = BatchReport(wanted=1, entries=(), stop_reason=BatchStopReason.CANDIDATES_EXHAUSTED)
SETTINGS: Final = AutoCutSettings(wanted=1, concurrency=1, card_format="docx", max_cost_usd=None)
FILES: Final = AutoCutFiles(report=Path("report.json"))


def test_search_auto_cut_partial_providers_leaves_out_an_uncounted_provider_still_listed_in_providers() -> (
    None
):
    outcome = outcome_of(openalex_and_failing_rss(), SearchRequest(query="health insurance", topic_id=NHI))
    assert outcome.uncounted == ("semantic_scholar", "govinfo")

    report = report_payload(
        REPORT, outcome, BatchNeed("Politics DA", "Link", "Politics DA — Link"), SETTINGS, FILES
    )

    assert (report["search_status"], report["partial_providers"]) == ("PARTIAL", ["rss"])
    providers: list[dict[str, Any]] = search_payload(outcome)["providers"]  # type: ignore[assignment]
    assert [(entry["provider"], entry["outcome"]) for entry in providers] == [
        ("openalex", "ok"),
        ("rss", "error"),
        ("semantic_scholar", "not configured"),
        ("govinfo", "not configured"),
    ]


def test_search_auto_cut_partial_providers_keeps_a_named_provider_not_configured() -> None:
    request = SearchRequest(query="health insurance", topic_id=NHI, providers=("openalex", "rss", "govinfo"))
    outcome = outcome_of(openalex_and_failing_rss(), request)

    report = report_payload(
        REPORT, outcome, BatchNeed("Politics DA", "Link", "Politics DA — Link"), SETTINGS, FILES
    )

    assert (report["search_status"], report["partial_providers"]) == ("PARTIAL", ["rss", "govinfo"])


def test_daily_auto_cut_partial_providers_leaves_out_the_presets_uncounted_providers() -> None:
    request = SearchRequest(
        query="health insurance",
        topic_id=NHI,
        providers=("openalex", "rss", "govinfo", "gdelt"),
        providers_named=False,
    )
    digest = digest_of(outcome_of(openalex_and_failing_rss(), request))
    assert digest.uncounted == ("govinfo", "gdelt")

    report = auto_cut_payload(REPORT, digest, SETTINGS, FILES)

    assert (report["digest_status"], report["partial_providers"]) == ("PARTIAL", ["rss"])
