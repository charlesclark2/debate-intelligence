"""ProviderRegistry: only enabled providers are built, each is wrapped, and health is reported redacted."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from datetime import timedelta
from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from debate_core.application.errors import NotFound, ProviderUnavailable
from debate_core.application.ports.providers import DiscoveryProviders
from debate_core.application.settings import ConfigurationError, ProviderSettings, SearchProviderName
from debate_core.domain.discovery import BreakerState, ProviderQuery, ProviderResponse
from debate_core.integrations.discovery.registry import (
    ProviderRegistry,
    SearchProviderFactory,
    configured_secrets,
    policy_from_settings,
)
from debate_core.integrations.discovery.resilience import ResiliencePolicy, ResilientProvider
from debate_core.testing.fakes import FixedClock

QUERY = ProviderQuery(query="data center water use")
API_KEY = "s2-key-registry-7a6b5c"
CONTACT_EMAIL = "coach@example.org"
CASELIST_TOKEN = "caselist-cookie-registry-1f2e"


def run[ResultT](awaitable: Coroutine[Any, Any, ResultT]) -> ResultT:
    return asyncio.run(awaitable)


class StubAdapter:
    """An adapter that answers empty, or fails with `failure`, taking 50 ms of the test clock."""

    def __init__(self, name: str, clock: FixedClock, failure: Exception | None = None) -> None:
        self._name = name
        self._clock = clock
        self.failure = failure
        self.settings_seen: ProviderSettings | None = None

    @property
    def name(self) -> str:
        return self._name

    async def search(self, query: ProviderQuery) -> ProviderResponse:
        self._clock.advance(timedelta(milliseconds=50))
        if self.failure is not None:
            raise self.failure
        return ProviderResponse(provider=self._name, elapsed_ms=50.0)


class Factories:
    """One factory per provider name, recording which were called and what they built."""

    def __init__(self, clock: FixedClock) -> None:
        self.clock = clock
        self.built: dict[SearchProviderName, StubAdapter] = {}

    def factory(self, name: SearchProviderName, *, calls_itself: str | None = None) -> SearchProviderFactory:
        def build(settings: ProviderSettings) -> StubAdapter:
            adapter = StubAdapter(calls_itself or name.value, self.clock)
            adapter.settings_seen = settings
            self.built[name] = adapter
            return adapter

        return build

    def every_name(self) -> dict[SearchProviderName, SearchProviderFactory]:
        return {name: self.factory(name) for name in SearchProviderName}


def test_only_the_enabled_providers_are_built() -> None:
    clock = FixedClock()
    factories = Factories(clock)
    settings = ProviderSettings(enabled=(SearchProviderName.RSS, SearchProviderName.OPENALEX))

    registry = ProviderRegistry.from_settings(settings, factories.every_name(), clock=clock)

    assert set(factories.built) == {SearchProviderName.RSS, SearchProviderName.OPENALEX}
    assert registry.names == ("rss", "openalex")
    assert all(isinstance(provider, ResilientProvider) for provider in registry.providers)


def test_the_registry_is_the_discovery_providers_port_a_federated_search_fans_out_over() -> None:
    """The application layer cannot import the registry, so it takes `DiscoveryProviders`; this is that.

    The annotated assignment is the real check: pyright strict fails it if the registry stops
    satisfying the port. The `isinstance` is the runtime half, and the reads show the two members a
    search uses answer through the port as they do on the registry.
    """
    clock = FixedClock()
    settings = ProviderSettings(enabled=(SearchProviderName.RSS, SearchProviderName.OPENALEX))
    registry = ProviderRegistry.from_settings(settings, Factories(clock).every_name(), clock=clock)

    port: DiscoveryProviders = registry

    assert isinstance(registry, DiscoveryProviders)
    assert [provider.name for provider in port.providers] == ["rss", "openalex"]
    assert [health.provider for health in port.health()] == ["rss", "openalex"]


def test_nothing_enabled_builds_nothing() -> None:
    clock = FixedClock()
    factories = Factories(clock)
    registry = ProviderRegistry.from_settings(ProviderSettings(), factories.every_name(), clock=clock)
    assert factories.built == {}
    assert registry.names == ()
    assert registry.health() == ()


def test_a_provider_named_twice_is_built_once() -> None:
    clock = FixedClock()
    factories = Factories(clock)
    settings = ProviderSettings(enabled=(SearchProviderName.GDELT, SearchProviderName.GDELT))
    registry = ProviderRegistry.from_settings(settings, factories.every_name(), clock=clock)
    assert registry.names == ("gdelt",)


def test_an_enabled_provider_with_no_adapter_in_this_build_is_a_configuration_error() -> None:
    clock = FixedClock()
    factories = Factories(clock)
    settings = ProviderSettings(enabled=(SearchProviderName.OPENALEX, SearchProviderName.CROSSREF))
    with pytest.raises(ConfigurationError) as refused:
        ProviderRegistry.from_settings(
            settings,
            {SearchProviderName.OPENALEX: factories.factory(SearchProviderName.OPENALEX)},
            clock=clock,
        )
    assert refused.value.field == "providers.enabled"
    assert "'crossref' is enabled, but this build has no adapter for it" in str(refused.value)


def test_an_adapter_that_calls_itself_something_else_is_a_configuration_error() -> None:
    clock = FixedClock()
    factories = Factories(clock)
    settings = ProviderSettings(enabled=(SearchProviderName.CROSSREF,))
    with pytest.raises(ConfigurationError, match="the adapter built for 'crossref' calls itself 'openalex'"):
        ProviderRegistry.from_settings(
            settings,
            {
                SearchProviderName.CROSSREF: factories.factory(
                    SearchProviderName.CROSSREF, calls_itself="openalex"
                )
            },
            clock=clock,
        )


def test_a_factory_is_handed_the_provider_settings_with_their_credentials() -> None:
    clock = FixedClock()
    factories = Factories(clock)
    settings = ProviderSettings(
        enabled=(SearchProviderName.SEMANTIC_SCHOLAR,), semantic_scholar_api_key=SecretStr(API_KEY)
    )
    ProviderRegistry.from_settings(settings, factories.every_name(), clock=clock)
    seen = factories.built[SearchProviderName.SEMANTIC_SCHOLAR].settings_seen
    assert seen is settings


def test_every_provider_runs_under_the_timeout_and_breaker_from_settings() -> None:
    clock = FixedClock()
    settings = ProviderSettings(
        enabled=(SearchProviderName.OPENALEX, SearchProviderName.GDELT),
        timeout_seconds=4.5,
        breaker_failure_threshold=2,
        breaker_cooldown_seconds=90.0,
    )
    registry = ProviderRegistry.from_settings(settings, Factories(clock).every_name(), clock=clock)
    expected = ResiliencePolicy(timeout_seconds=4.5, failure_threshold=2, cooldown_seconds=90.0)
    assert policy_from_settings(settings) == expected
    assert [provider.policy for provider in registry.providers] == [expected, expected]


def test_the_settings_defaults_are_the_policy_defaults() -> None:
    assert policy_from_settings(ProviderSettings()) == ResiliencePolicy()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("timeout_seconds", 0),
        ("timeout_seconds", 121),
        ("breaker_failure_threshold", 0),
        ("breaker_cooldown_seconds", 0),
        ("breaker_cooldown_seconds", 3601),
    ],
)
def test_settings_refuse_a_timeout_or_breaker_that_would_disable_it(field: str, value: float) -> None:
    with pytest.raises(ValidationError, match=field):
        ProviderSettings.model_validate({field: value})


def test_get_finds_an_enabled_provider_and_refuses_one_that_is_not() -> None:
    clock = FixedClock()
    settings = ProviderSettings(enabled=(SearchProviderName.OPENALEX,))
    registry = ProviderRegistry.from_settings(settings, Factories(clock).every_name(), clock=clock)
    assert registry.get("openalex").name == "openalex"
    with pytest.raises(NotFound, match="discovery provider not found: crossref"):
        registry.get("crossref")


def test_two_providers_with_one_name_are_refused() -> None:
    clock = FixedClock()
    first = ResilientProvider(StubAdapter("rss", clock), ResiliencePolicy(), clock=clock)
    second = ResilientProvider(StubAdapter("rss", clock), ResiliencePolicy(), clock=clock)
    with pytest.raises(ValueError, match="two discovery providers are named 'rss'"):
        ProviderRegistry([first, second])


# --------------------------------------------------------------------------------------------
# Health
# --------------------------------------------------------------------------------------------


def test_health_has_one_snapshot_per_provider_with_state_last_error_p50_and_counts() -> None:
    clock = FixedClock()
    factories = Factories(clock)
    settings = ProviderSettings(
        enabled=(SearchProviderName.OPENALEX, SearchProviderName.CROSSREF), breaker_failure_threshold=1
    )
    registry = ProviderRegistry.from_settings(settings, factories.every_name(), clock=clock)
    factories.built[SearchProviderName.CROSSREF].failure = ProviderUnavailable("crossref", "HTTP 503")

    run(registry.get("openalex").search(QUERY))
    with pytest.raises(ProviderUnavailable):
        run(registry.get("crossref").search(QUERY))

    openalex, crossref = registry.health()
    assert openalex.provider == "openalex"
    assert openalex.state is BreakerState.CLOSED
    assert (openalex.success_count, openalex.error_count) == (1, 0)
    assert openalex.last_error is None
    assert openalex.p50_latency_ms == 50.0
    assert crossref.provider == "crossref"
    assert crossref.state is BreakerState.OPEN
    assert (crossref.success_count, crossref.error_count) == (0, 1)
    assert crossref.last_error == "crossref: HTTP 503"
    assert crossref.p50_latency_ms == 50.0


# --------------------------------------------------------------------------------------------
# Secrets
# --------------------------------------------------------------------------------------------


def secret_settings() -> ProviderSettings:
    return ProviderSettings(
        enabled=(SearchProviderName.SEMANTIC_SCHOLAR, SearchProviderName.OPENALEX),
        contact_email=SecretStr(CONTACT_EMAIL),
        semantic_scholar_api_key=SecretStr(API_KEY),
        caselist_token=SecretStr(CASELIST_TOKEN),
        breaker_failure_threshold=1,
    )


def test_every_secret_in_the_group_is_on_the_redaction_list() -> None:
    assert set(configured_secrets(secret_settings())) == {CONTACT_EMAIL, API_KEY, CASELIST_TOKEN}
    assert configured_secrets(ProviderSettings()) == ()
    assert configured_secrets(ProviderSettings(contact_email=SecretStr(""))) == ()


def test_no_key_or_contact_email_reaches_a_log_an_error_a_health_snapshot_or_a_repr(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="debate_core.integrations.discovery")
    clock = FixedClock()
    factories = Factories(clock)
    settings = secret_settings()
    registry = ProviderRegistry.from_settings(settings, factories.every_name(), clock=clock)
    factories.built[SearchProviderName.SEMANTIC_SCHOLAR].failure = ProviderUnavailable(
        "semantic_scholar", f"HTTP 403 for x-api-key {API_KEY} (caselist_token={CASELIST_TOKEN})"
    )
    factories.built[SearchProviderName.OPENALEX].failure = RuntimeError(
        f"GET https://api.openalex.org/works?mailto=coach%40example.org failed for {CONTACT_EMAIL}"
    )

    raised: list[BaseException] = []
    for name in registry.names:
        with pytest.raises(ProviderUnavailable) as failed:
            run(registry.get(name).search(QUERY))
        raised.append(failed.value)

    surfaces = [repr(registry), repr(settings), *(repr(provider) for provider in registry.providers)]
    surfaces.extend(snapshot.model_dump_json() for snapshot in registry.health())
    for error in raised:
        chain: BaseException | None = error
        while chain is not None:
            surfaces.extend((str(chain), repr(chain)))
            chain = chain.__cause__ or chain.__context__
    surfaces.extend(record.getMessage() for record in caplog.records)

    secrets = (API_KEY, CONTACT_EMAIL, "coach%40example.org", CASELIST_TOKEN)
    leaked = [surface for surface in surfaces if any(secret in surface for secret in secrets)]
    assert caplog.records
    assert leaked == []
    assert (
        registry.health()[0].last_error == "semantic_scholar: HTTP 403 for x-api-key *** (caselist_token=***)"
    )
