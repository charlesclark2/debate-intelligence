"""Federated search: ask every selected discovery provider at once, and say which ones answered.

:class:`FederatedSearchService` runs a search's four stages (expand, fan_out, normalize, rank; see
:mod:`debate_core.application.federated_search_types`) and stores the result. This module owns the
fan_out stage, :class:`FanOutStage`, and the rule that turns its per-call record into the search's
status, :func:`search_status`. Deduplication, ranking and query expansion are sibling tasks
(v1-e08-t02 to t04) and default to stages that change nothing.

## Fan-out

Every selected provider is asked every query at the same time, in one :class:`asyncio.TaskGroup`,
and the whole fan-out runs under one overall deadline. A search therefore takes as long as its
slowest provider or its deadline, whichever comes first, never the sum of its providers.

Each provider the :class:`~debate_core.application.ports.DiscoveryProviders` port hands out is
already wrapped in its own timeout, circuit breaker and rate-limit hold
(:class:`~debate_core.integrations.discovery.resilience.ResilientProvider`), so the fan-out adds no
per-provider timeout of its own. What it adds is the deadline over all of them and the record of
how each call ended (:class:`~debate_core.domain.discovery.ProviderOutcome`):

* an answer is `ok`;
* :class:`~debate_core.application.errors.ProviderTimedOut` is `timeout`, and so is a call still
  running when the deadline passes, which is cancelled there;
* :class:`~debate_core.application.errors.ProviderCircuitOpen` is `breaker_open`: the call was
  skipped without reaching the provider;
* :class:`~debate_core.application.errors.ProviderRateLimited` is `rate_limited`;
* any other failure is `error`, including an exception a provider should have translated and did
  not, which is recorded by its type alone because its text was never redacted;
* a provider the request names that settings do not enable is `not_configured`.

**One provider never fails the search.** Nothing a provider raises leaves the fan-out: every
failure becomes that call's record, and the search goes on with the providers that answered.
Only cancellation of the search itself propagates.

## Status

:func:`search_status`: COMPLETE when every call answered in full, FAILED when none answered, and
PARTIAL otherwise. A provider that answered but marked its own answer partial (some of its feeds
failed) makes the search PARTIAL, because the search did not get everything it asked for.

## Storage

The search record, every call's record (the raw per-provider results) and the ranking, if a rank
stage produced one, go through :class:`~debate_core.application.ports.SearchRepository` after the
last stage, so a search can be reloaded by its id, audited and replayed. Times come from the
injected :class:`~debate_core.application.ports.Clock`; the deadline itself is the event loop's,
because cancelling a call that is still running is the event loop's job.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Final

from debate_core.application.errors import (
    ProviderCircuitOpen,
    ProviderError,
    ProviderRateLimited,
    ProviderTimedOut,
)
from debate_core.application.federated_search_types import (
    PassThroughStage,
    SearchOutcome,
    SearchPipeline,
    SearchRequest,
    SearchStage,
    SearchState,
)
from debate_core.application.ports import (
    Clock,
    DiscoveryProviders,
    IdGenerator,
    SearchProvider,
    SearchRepository,
)
from debate_core.domain import Search, SearchStatus
from debate_core.domain.discovery import ProviderOutcome, ProviderQuery, ProviderStatus

__all__ = [
    "DEFAULT_DEADLINE_SECONDS",
    "FanOutStage",
    "FederatedSearchService",
    "search_status",
    "selected_providers",
]

DEFAULT_DEADLINE_SECONDS: Final = 15.0
"""The overall deadline when none is given: above the providers' own default timeout of 10 s, so a
provider that times out by itself is reported by its own timeout rather than cut off by this one."""


def search_status(statuses: Sequence[ProviderStatus]) -> SearchStatus:
    """COMPLETE if every call answered in full, FAILED if none answered, PARTIAL otherwise.

    A search that made no calls at all (no provider enabled, or every one asked for is not
    configured) answered nothing, so it is FAILED.
    """
    answered = [status for status in statuses if status.outcome is ProviderOutcome.OK]
    if not answered:
        return SearchStatus.FAILED
    in_full = all(status.response is not None and not status.response.partial for status in answered)
    if len(answered) == len(statuses) and in_full:
        return SearchStatus.COMPLETE
    return SearchStatus.PARTIAL


def selected_providers(request: SearchRequest, enabled: Iterable[str]) -> tuple[str, ...]:
    """The providers a search asks, by name: the ones the request names, or every enabled one.

    In the request's order, each once. A requested name that is not enabled stays in the
    selection, so the search reports it as not configured instead of silently asking fewer.
    """
    if request.providers is None:
        return tuple(dict.fromkeys(enabled))
    return tuple(dict.fromkeys(request.providers))


class FanOutStage:
    """Asks every selected provider every query, concurrently, under one overall deadline."""

    def __init__(self, providers: DiscoveryProviders, *, clock: Clock, deadline_seconds: float) -> None:
        if deadline_seconds <= 0:
            raise ValueError(f"deadline_seconds must be positive, got {deadline_seconds}")
        self._providers = providers
        self._clock = clock
        self._deadline_seconds = deadline_seconds

    @property
    def deadline_seconds(self) -> float:
        """How long the whole fan-out may take."""
        return self._deadline_seconds

    def __repr__(self) -> str:
        return f"FanOutStage(deadline_seconds={self._deadline_seconds:g})"

    async def run(self, state: SearchState) -> SearchState:
        """Record one :class:`ProviderStatus` per (query, provider), and collect what was returned."""
        enabled = {provider.name: provider for provider in self._providers.providers}
        names = selected_providers(state.request, enabled)
        calls = [(query, name) for query in state.queries for name in names]
        finished: dict[int, ProviderStatus] = {}
        started = self._clock.now()
        deadline = asyncio.timeout(self._deadline_seconds)
        try:
            async with deadline, asyncio.TaskGroup() as group:
                for index, (query, name) in enumerate(calls):
                    provider = enabled.get(name)
                    if provider is None:
                        finished[index] = self._not_configured(name, query)
                    else:
                        group.create_task(self._record(finished, index, provider, query))
        except TimeoutError:
            if not deadline.expired():
                raise
        statuses = tuple(
            finished[index] if index in finished else self._cut_off(name, query, started)
            for index, (query, name) in enumerate(calls)
        )
        candidates = tuple(
            candidate
            for status in statuses
            if status.response is not None
            for candidate in status.response.results
        )
        return state.evolve(provider_statuses=statuses, candidates=candidates)

    async def _record(
        self,
        finished: dict[int, ProviderStatus],
        index: int,
        provider: SearchProvider,
        query: ProviderQuery,
    ) -> None:
        finished[index] = await self._call(provider, query)

    async def _call(self, provider: SearchProvider, query: ProviderQuery) -> ProviderStatus:
        """Ask one provider one query; every way it can fail becomes a status, never an exception."""
        name = provider.name
        started = self._clock.now()
        try:
            response = await provider.search(query)
        except ProviderTimedOut as error:
            return self._failed(name, query, ProviderOutcome.TIMEOUT, str(error), started)
        except ProviderCircuitOpen as error:
            return self._failed(name, query, ProviderOutcome.BREAKER_OPEN, str(error), started)
        except ProviderRateLimited as error:
            return self._failed(name, query, ProviderOutcome.RATE_LIMITED, str(error), started)
        except ProviderError as error:
            return self._failed(name, query, ProviderOutcome.ERROR, str(error), started)
        except Exception as error:
            reason = f"{name}: the provider raised {type(error).__name__}, which it should have translated"
            return self._failed(name, query, ProviderOutcome.ERROR, reason, started)
        if response.provider != name:
            reason = f"{name}: the provider answered as {response.provider!r}"
            return self._failed(name, query, ProviderOutcome.ERROR, reason, started)
        return ProviderStatus(
            provider=name,
            query=query,
            outcome=ProviderOutcome.OK,
            elapsed_ms=self._elapsed_ms(started),
            response=response,
        )

    def _failed(
        self, name: str, query: ProviderQuery, outcome: ProviderOutcome, error: str, started: datetime
    ) -> ProviderStatus:
        return ProviderStatus(
            provider=name, query=query, outcome=outcome, elapsed_ms=self._elapsed_ms(started), error=error
        )

    def _cut_off(self, name: str, query: ProviderQuery, started: datetime) -> ProviderStatus:
        """A call still running when the deadline passed: cancelled there, and reported as a timeout."""
        reason = f"{name}: no answer before the search's {self._deadline_seconds:g}s deadline"
        return self._failed(name, query, ProviderOutcome.TIMEOUT, reason, started)

    @staticmethod
    def _not_configured(name: str, query: ProviderQuery) -> ProviderStatus:
        return ProviderStatus(
            provider=name,
            query=query,
            outcome=ProviderOutcome.NOT_CONFIGURED,
            elapsed_ms=0.0,
            error=f"{name}: not enabled in settings (providers.enabled)",
        )

    def _elapsed_ms(self, started: datetime) -> float:
        return max((self._clock.now() - started).total_seconds() * 1000.0, 0.0)


class FederatedSearchService:
    """Runs a federated search through its four stages and stores what it found.

    `expand`, `normalize` and `rank` are the sibling tasks' stages and default to
    :class:`~debate_core.application.federated_search_types.PassThroughStage`; fan_out is this
    module's :class:`FanOutStage` over `providers`, under `deadline_seconds`.
    """

    def __init__(
        self,
        providers: DiscoveryProviders,
        searches: SearchRepository,
        *,
        clock: Clock,
        ids: IdGenerator,
        deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
        expand: SearchStage | None = None,
        normalize: SearchStage | None = None,
        rank: SearchStage | None = None,
    ) -> None:
        self._providers = providers
        self._searches = searches
        self._clock = clock
        self._ids = ids
        self._pipeline = SearchPipeline(
            expand=PassThroughStage() if expand is None else expand,
            fan_out=FanOutStage(providers, clock=clock, deadline_seconds=deadline_seconds),
            normalize=PassThroughStage() if normalize is None else normalize,
            rank=PassThroughStage() if rank is None else rank,
        )

    @property
    def pipeline(self) -> SearchPipeline:
        """The stages this service runs, in order."""
        return self._pipeline

    async def search(self, request: SearchRequest) -> SearchOutcome:
        """Run every stage, store the search with its per-provider record and ranking, and return it.

        Never raises because a provider failed: the outcome says which providers answered, and the
        stored status is PARTIAL or FAILED accordingly.
        """
        created_at = self._clock.now()
        state = SearchState.start(self._ids.new_id(), request)
        for _, stage in self._pipeline.stages:
            state = await stage.run(state)
        enabled = (provider.name for provider in self._providers.providers)
        search = Search(
            search_id=state.search_id,
            owner_id=request.owner_id,
            organization_id=request.organization_id,
            query=request.query,
            filters=request.filters,
            provider_set=selected_providers(request, enabled),
            status=search_status(state.provider_statuses),
            created_at=created_at,
            updated_at=self._clock.now(),
        )
        stored = await self._searches.save(search)
        await self._searches.save_provider_statuses(stored.search_id, state.provider_statuses)
        await self._searches.save_results(stored.search_id, state.results)
        return SearchOutcome(
            search=stored,
            provider_statuses=state.provider_statuses,
            candidates=state.candidates,
            results=state.results,
            provider_health=self._providers.health(),
        )
