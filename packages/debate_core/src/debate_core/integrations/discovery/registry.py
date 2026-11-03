"""The discovery providers settings switch on, each wrapped, and their health.

:meth:`ProviderRegistry.from_settings` reads `settings.providers.enabled` and builds those
providers and no others: an adapter that is not enabled is never constructed, so it can neither
reach the network nor read a credential. Each adapter is wrapped in a
:class:`~debate_core.integrations.discovery.resilience.ResilientProvider` whose timeout and breaker
come from the same settings group, and whose redaction list is every credential in it.

Which adapter answers to which name is the composition root's to say, through `factories`: one
function per :class:`~debate_core.application.settings.SearchProviderName`, taking the provider
settings (its keys and contact email, still as `SecretStr`) and returning an adapter. The adapters
are v1-e07-t02 to t07; until one exists, enabling its name is a configuration error that says so.
A factory that cannot build its adapter because a credential is not set raises
:class:`ProviderNotConfigured`: the registry builds nothing for it and lists it in
:attr:`ProviderRegistry.not_configured` with the reason, which a search reports for each call (v1-e07-t07).

:meth:`ProviderRegistry.health` is what the CLI's provider status footer reads, and
:meth:`ProviderRegistry.aclose` closes every adapter's connections when a search ends (v1-e08-t05).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from types import MappingProxyType

from pydantic import SecretStr

from debate_core.application.errors import NotFound
from debate_core.application.ports.providers import Clock, SearchProvider
from debate_core.application.settings import ConfigurationError, ProviderSettings, SearchProviderName
from debate_core.domain.discovery import ProviderHealth
from debate_core.integrations.discovery.resilience import ResiliencePolicy, ResilientProvider

__all__ = [
    "ProviderNotConfigured",
    "ProviderRegistry",
    "SearchProviderFactory",
    "configured_secrets",
    "policy_from_settings",
]


class ProviderNotConfigured(Exception):  # noqa: N818 - a reported outcome, as ProviderOutcome.NOT_CONFIGURED is
    """A factory cannot build its adapter from these settings: a credential it needs is not set.

    Not an error of the search: :meth:`ProviderRegistry.from_settings` records the provider as enabled
    but not configured, with `reason`, and the fan-out reports each call to it so (v1-e07-t07).
    `reason` names the setting to set and never its value.
    """

    def __init__(self, provider: str, reason: str) -> None:
        self.provider = provider
        """The provider's settings name."""
        self.reason = reason
        """What is missing, as a person reads it: `govinfo: no api.data.gov key (DEBATE_PROVIDERS__...)`."""
        super().__init__(reason)


type SearchProviderFactory = Callable[[ProviderSettings], SearchProvider]
"""Builds one adapter from the provider settings; its other dependencies come from the closure."""


def policy_from_settings(settings: ProviderSettings) -> ResiliencePolicy:
    """The timeout and breaker every provider runs under, from `settings.providers`."""
    return ResiliencePolicy(
        timeout_seconds=settings.timeout_seconds,
        failure_threshold=settings.breaker_failure_threshold,
        cooldown_seconds=settings.breaker_cooldown_seconds,
    )


def configured_secrets(settings: ProviderSettings) -> tuple[str, ...]:
    """Every credential and contact address in the group: each field that holds a `SecretStr`.

    Read from the fields rather than listed by name, so a key a later adapter adds to the group is
    redacted from the day it is added.
    """
    values: list[str] = []
    for field_name in type(settings).model_fields:
        value = getattr(settings, field_name)
        if isinstance(value, SecretStr) and value.get_secret_value():
            values.append(value.get_secret_value())
    return tuple(values)


class ProviderRegistry:
    """The enabled discovery providers, each a :class:`ResilientProvider`, in settings order."""

    def __init__(
        self, providers: Iterable[ResilientProvider], *, not_configured: Mapping[str, str] | None = None
    ) -> None:
        self._providers: dict[str, ResilientProvider] = {}
        for provider in providers:
            if provider.name in self._providers:
                raise ValueError(f"two discovery providers are named {provider.name!r}")
            self._providers[provider.name] = provider
        self._not_configured = MappingProxyType(dict(not_configured or {}))

    @classmethod
    def from_settings(
        cls,
        settings: ProviderSettings,
        factories: Mapping[SearchProviderName, SearchProviderFactory],
        *,
        clock: Clock,
    ) -> ProviderRegistry:
        """Build, and wrap, exactly the providers `settings.enabled` names.

        A factory that raises :class:`ProviderNotConfigured` builds nothing; its provider is in
        :attr:`not_configured` instead, with the reason, and in no other list here.

        Raises :class:`~debate_core.application.settings.ConfigurationError` on
        `providers.enabled` when a name has no adapter in this build, or when the adapter built for
        a name calls itself something else (health and results are reported by that name).
        """
        policy = policy_from_settings(settings)
        secrets = configured_secrets(settings)
        wrapped: list[ResilientProvider] = []
        not_configured: dict[str, str] = {}
        for name in dict.fromkeys(settings.enabled):
            factory = factories.get(name)
            if factory is None:
                raise ConfigurationError(
                    f"discovery provider {name.value!r} is enabled, but this build has no adapter for it",
                    field="providers.enabled",
                )
            try:
                adapter = factory(settings)
            except ProviderNotConfigured as missing:
                not_configured[name.value] = missing.reason
                continue
            if adapter.name != name.value:
                raise ConfigurationError(
                    f"the adapter built for {name.value!r} calls itself {adapter.name!r}",
                    field="providers.enabled",
                )
            wrapped.append(ResilientProvider(adapter, policy, clock=clock, secrets=secrets))
        return cls(wrapped, not_configured=not_configured)

    @property
    def not_configured(self) -> Mapping[str, str]:
        """Enabled providers whose factory could not build them, by name, with why; in settings order."""
        return self._not_configured

    @property
    def names(self) -> tuple[str, ...]:
        """The enabled providers' names, in settings order."""
        return tuple(self._providers)

    @property
    def providers(self) -> tuple[ResilientProvider, ...]:
        """The enabled providers, wrapped, in settings order."""
        return tuple(self._providers.values())

    def get(self, name: str) -> ResilientProvider:
        """The provider called `name`; :class:`NotFound` when it is not enabled."""
        try:
            return self._providers[name]
        except KeyError:
            raise NotFound("discovery provider", name) from None

    def health(self) -> tuple[ProviderHealth, ...]:
        """One snapshot per enabled provider, in settings order: state, last error, p50, counts."""
        return tuple(provider.health() for provider in self._providers.values())

    async def aclose(self) -> None:
        """Close every provider's connections, each one even when closing another fails.

        The first failure is raised once all have been asked to close.
        """
        failures: list[BaseException] = []
        for provider in self._providers.values():
            try:
                await provider.aclose()
            except Exception as error:
                failures.append(error)
        if failures:
            raise failures[0]

    def __repr__(self) -> str:
        not_configured = f", not_configured={list(self._not_configured)!r}" if self._not_configured else ""
        return f"ProviderRegistry(providers={list(self._providers)!r}{not_configured})"
