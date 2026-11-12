"""Federated search: ask every selected discovery provider at once, and say which ones answered.

:class:`FederatedSearchService` runs a search's four stages (expand, fan_out, normalize, rank; see
:mod:`debate_core.application.federated_search_types`) and stores the result. This module owns the
fan_out stage, :class:`FanOutStage`, and the rule that turns its per-call record into the search's
status, :func:`search_status`. Query expansion, deduplication and ranking are sibling tasks
(v1-e08-t02 to t04) and default to stages that change nothing.

## Fan-out

Every selected provider is asked every query at the same time, in one :class:`asyncio.TaskGroup`,
and the whole fan-out runs under one overall deadline. A search therefore takes as long as its
slowest provider or its deadline, whichever comes first, never the sum of its providers.

**A provider that answers several queries at once is asked once** (v1-e08-t10). A
:class:`~debate_core.application.ports.providers.MultiQuerySearchProvider` gets one call with every
query of the search, however many the expansion gave, and answers each query separately; any other
provider gets one call per query. Either way the search keeps one record per query and provider, in
the same order (query by query, each provider in the selection's order), so nothing after the
fan-out can tell how a provider was asked. A batched call that fails, or is still running at the
deadline, is recorded on each of its queries with the same reason.

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
* a provider the request names that settings do not enable is `not_configured`, and so is one
  settings enable but cannot build because its key or the contact email is missing.

**One provider never fails the search.** Nothing a provider raises leaves the fan-out: every
failure becomes that call's record, and the search goes on with the providers that answered.
Only cancellation of the search itself propagates.

## Status

:func:`search_status`: COMPLETE when every call answered in full, FAILED when none answered, and
PARTIAL otherwise. A provider that answered but marked its own answer partial (some of its feeds
failed) makes the search PARTIAL, because the search did not get everything it asked for.

**A provider settings enable but cannot configure is not counted** (v1-e07-t15, the PM's rulings of
2026-11-09). GovInfo without the api.data.gov key is the case: no retry can get more from it, so it
no longer makes every search partial. Its calls stay in the record, `not_configured`, with the
cure from :func:`~debate_core.application.provider_credentials.missing_credential_cure` after the
registry's reason, and the outcome lists it in `uncounted` (:meth:`FanOutStage.uncounted`). A
search in which nothing else answered is still FAILED. Two cases are counted as before:

* a provider the request names (`search --providers`): the student asked for it, so missing it is a
  missing answer, PARTIAL, with today's reason. A request whose `providers` are configuration, a
  daily preset's (`providers_named=False`), counts like the enabled providers instead;
* a name settings do not enable at all, and a government provider the search's topic does not list:
  neither is a missing key.

## Storage

The search record (with its expansion, when the expand stage made one), every call's record (the
raw per-provider results) and the ranking, if a rank stage produced one, go through
:class:`~debate_core.application.ports.SearchRepository` after the last stage, so a search can be
reloaded by its id, audited and replayed. Times come from the injected
:class:`~debate_core.application.ports.Clock`; the deadline itself is the event loop's,
because cancelling a call that is still running is the event loop's job.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
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
from debate_core.application.ports.persistence import SearchRepository
from debate_core.application.ports.providers import (
    Clock,
    DiscoveryProviders,
    IdGenerator,
    MultiQuerySearchProvider,
    SearchProvider,
)
from debate_core.application.provider_credentials import missing_credential_cure
from debate_core.application.query_expansion import UnknownExpansionChoice
from debate_core.application.settings import TOPIC_ENABLED_PROVIDERS
from debate_core.domain import Search, SearchStatus
from debate_core.domain.discovery import ProviderOutcome, ProviderQuery, ProviderResponse, ProviderStatus

__all__ = [
    "DEFAULT_DEADLINE_SECONDS",
    "FanOutStage",
    "FederatedSearchService",
    "NO_TOPICS",
    "SearchTopics",
    "search_status",
    "selected_providers",
]

DEFAULT_DEADLINE_SECONDS: Final = 15.0
"""The overall deadline when none is given: above the providers' own default timeout of 10 s, so a
provider that times out by itself is reported by its own timeout rather than cut off by this one."""


def search_status(statuses: Sequence[ProviderStatus], *, uncounted: Collection[str] = ()) -> SearchStatus:
    """COMPLETE if every counted call answered in full, FAILED if none answered, PARTIAL otherwise.

    The `not_configured` calls of a provider in `uncounted` are left out (v1-e07-t15); any other call
    of it counts. A search that made no calls at all (no provider enabled, or every one asked for is
    not configured) answered nothing, so it is FAILED.
    """
    counted = [
        status
        for status in statuses
        if not (status.outcome is ProviderOutcome.NOT_CONFIGURED and status.provider in uncounted)
    ]
    answered = [status for status in counted if status.outcome is ProviderOutcome.OK]
    if not answered:
        return SearchStatus.FAILED
    in_full = all(status.response is not None and not status.response.partial for status in answered)
    if len(answered) == len(counted) and in_full:
        return SearchStatus.COMPLETE
    return SearchStatus.PARTIAL


@dataclass(frozen=True)
class SearchTopics:
    """The debate topics a search may name, and the government providers each one enables (v1-e07-t07).

    Built by the composition root from the taxonomy's topic presets and the feed files' `search_topics`
    and `government_providers` (`config/feeds/`). A provider in
    :data:`~debate_core.application.settings.TOPIC_ENABLED_PROVIDERS` is asked only by a search on a
    topic whose entry here lists it; every other provider is untouched by topics.
    """

    known: tuple[str, ...] = ()
    """Every topic id `--topic` accepts, in the order a refusal lists them."""

    providers: Mapping[str, frozenset[str]] = field(default_factory=dict[str, frozenset[str]])
    """For each topic that enables any, the government providers a search on it asks, by name."""

    def check(self, topic_id: str | None) -> None:
        """Refuse a topic nobody configured, listing the ones there are; a search with none passes."""
        if topic_id is not None and topic_id not in self.known:
            raise UnknownExpansionChoice("topic", topic_id, self.known)

    def allows(self, name: str, topic_id: str | None) -> bool:
        """Whether a search on `topic_id` may ask `name`: always, unless `name` is enabled per topic."""
        if name not in _TOPIC_ENABLED:
            return True
        return topic_id is not None and name in self.providers.get(topic_id, frozenset())

    def refusal(self, name: str, topic_id: str | None) -> str:
        """Why a search on `topic_id` does not ask `name`, which :meth:`allows` refused."""
        if topic_id is None:
            return f"{name}: asked only for a search on a topic that lists it, and this search names no topic"
        return f"{name}: asked only for a search on a topic that lists it, and {topic_id} does not"


_TOPIC_ENABLED: Final = frozenset(name.value for name in TOPIC_ENABLED_PROVIDERS)

NO_TOPICS: Final = SearchTopics()
"""No topic is known and no government provider is enabled by one: what a search has unless given topics."""


def selected_providers(
    request: SearchRequest,
    enabled: Iterable[str],
    *,
    not_configured: Iterable[str] = (),
    topics: SearchTopics = NO_TOPICS,
) -> tuple[str, ...]:
    """The providers a search asks, by name: the ones the request names, or every enabled one.

    In the request's order, each once. A requested name that is not enabled stays in the
    selection, so the search reports it as not configured instead of silently asking fewer; so does
    a requested government provider its topic does not list.

    Unrequested, the selection is the enabled providers, then those enabled but not configured (a
    key is missing), each reported so; and of the government providers, only those the search's
    topic lists (:class:`SearchTopics`). A search with no topic asks none of them and reports none.
    """
    if request.providers is not None:
        return tuple(dict.fromkeys(request.providers))
    return tuple(
        name for name in dict.fromkeys((*enabled, *not_configured)) if topics.allows(name, request.topic_id)
    )


class FanOutStage:
    """Asks every selected provider every query, concurrently, under one overall deadline.

    A provider that answers several queries at once is asked them in one call (see the module's
    docstring); every other provider is asked each query in a call of its own.
    """

    def __init__(
        self,
        providers: DiscoveryProviders,
        *,
        clock: Clock,
        deadline_seconds: float,
        topics: SearchTopics = NO_TOPICS,
    ) -> None:
        if deadline_seconds <= 0:
            raise ValueError(f"deadline_seconds must be positive, got {deadline_seconds}")
        self._providers = providers
        self._clock = clock
        self._deadline_seconds = deadline_seconds
        self._topics = topics

    def selection(self, request: SearchRequest) -> tuple[str, ...]:
        """The providers `request` asks, by name (:func:`selected_providers` over these providers)."""
        return selected_providers(
            request,
            (provider.name for provider in self._providers.providers),
            not_configured=self._providers.not_configured,
            topics=self._topics,
        )

    def uncounted(self, request: SearchRequest) -> tuple[str, ...]:
        """The selected providers `request`'s status leaves out, by name, in selection order (v1-e07-t15).

        Those settings enable but could not build (a key or the email missing), when the request names
        no provider or its list is configuration (`providers_named=False`) and its topic lists them.
        None when a person named the providers: each one missing is a missing answer.
        """
        if request.providers is not None and request.providers_named:
            return ()
        unbuilt = self._providers.not_configured
        return tuple(
            name
            for name in self.selection(request)
            if name in unbuilt and self._topics.allows(name, request.topic_id)
        )

    @property
    def deadline_seconds(self) -> float:
        """How long the whole fan-out may take."""
        return self._deadline_seconds

    def __repr__(self) -> str:
        return f"FanOutStage(deadline_seconds={self._deadline_seconds:g})"

    async def run(self, state: SearchState) -> SearchState:
        """Record one :class:`ProviderStatus` per (query, provider), and collect what was returned."""
        enabled = {provider.name: provider for provider in self._providers.providers}
        unbuilt = self._providers.not_configured
        topic_id = state.request.topic_id
        names = self.selection(state.request)
        uncounted = self.uncounted(state.request)
        calls = [(query, name) for query in state.queries for name in names]
        finished: dict[int, ProviderStatus] = {}
        started = self._clock.now()
        deadline = asyncio.timeout(self._deadline_seconds)
        try:
            async with deadline, asyncio.TaskGroup() as group:
                for name in names:
                    indices = [index for index, (_, called) in enumerate(calls) if called == name]
                    provider = enabled.get(name)
                    if not self._topics.allows(name, topic_id):
                        reason = self._topics.refusal(name, topic_id)
                        for index in indices:
                            finished[index] = self._not_configured(name, calls[index][0], reason)
                    elif provider is None:
                        reason = unbuilt.get(name)
                        if name in uncounted:
                            reason = _with_cure(name, reason)
                        for index in indices:
                            finished[index] = self._not_configured(name, calls[index][0], reason)
                    elif isinstance(provider, MultiQuerySearchProvider):
                        group.create_task(self._record_each(finished, indices, provider, calls))
                    else:
                        for index in indices:
                            group.create_task(self._record(finished, index, provider, calls[index][0]))
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

    async def _record_each(
        self,
        finished: dict[int, ProviderStatus],
        indices: Sequence[int],
        provider: MultiQuerySearchProvider,
        calls: Sequence[tuple[ProviderQuery, str]],
    ) -> None:
        """Ask `provider` every query at `indices` in one call, and record each query's answer."""
        queries = tuple(calls[index][0] for index in indices)
        statuses = await self._ask(provider.name, queries, lambda: provider.search_each(queries))
        finished.update(zip(indices, statuses, strict=True))

    async def _call(self, provider: SearchProvider, query: ProviderQuery) -> ProviderStatus:
        """Ask one provider one query; every way it can fail becomes a status, never an exception."""

        async def one() -> tuple[ProviderResponse, ...]:
            return (await provider.search(query),)

        (status,) = await self._ask(provider.name, (query,), one)
        return status

    async def _ask(
        self,
        name: str,
        queries: Sequence[ProviderQuery],
        ask: Callable[[], Awaitable[Sequence[ProviderResponse]]],
    ) -> tuple[ProviderStatus, ...]:
        """Make one call for `queries`: one status each, and every way the call can fail on each of them."""
        started = self._clock.now()
        try:
            responses = tuple(await ask())
        except ProviderTimedOut as error:
            return self._failed_each(name, queries, ProviderOutcome.TIMEOUT, str(error), started)
        except ProviderCircuitOpen as error:
            return self._failed_each(name, queries, ProviderOutcome.BREAKER_OPEN, str(error), started)
        except ProviderRateLimited as error:
            return self._failed_each(name, queries, ProviderOutcome.RATE_LIMITED, str(error), started)
        except ProviderError as error:
            return self._failed_each(name, queries, ProviderOutcome.ERROR, str(error), started)
        except Exception as error:
            reason = f"{name}: the provider raised {type(error).__name__}, which it should have translated"
            return self._failed_each(name, queries, ProviderOutcome.ERROR, reason, started)
        strangers = [response.provider for response in responses if response.provider != name]
        if strangers:
            reason = f"{name}: the provider answered as {strangers[0]!r}"
            return self._failed_each(name, queries, ProviderOutcome.ERROR, reason, started)
        if len(responses) != len(queries):
            reason = f"{name}: the provider answered {len(responses)} of {len(queries)} queries"
            return self._failed_each(name, queries, ProviderOutcome.ERROR, reason, started)
        elapsed_ms = self._elapsed_ms(started)
        return tuple(
            ProviderStatus(
                provider=name,
                query=query,
                outcome=ProviderOutcome.OK,
                elapsed_ms=elapsed_ms,
                response=response,
            )
            for query, response in zip(queries, responses, strict=True)
        )

    def _failed_each(
        self,
        name: str,
        queries: Sequence[ProviderQuery],
        outcome: ProviderOutcome,
        error: str,
        started: datetime,
    ) -> tuple[ProviderStatus, ...]:
        return tuple(self._failed(name, query, outcome, error, started) for query in queries)

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
    def _not_configured(name: str, query: ProviderQuery, reason: str | None = None) -> ProviderStatus:
        return ProviderStatus(
            provider=name,
            query=query,
            outcome=ProviderOutcome.NOT_CONFIGURED,
            elapsed_ms=0.0,
            error=reason or f"{name}: not enabled in settings (providers.enabled)",
        )

    def _elapsed_ms(self, started: datetime) -> float:
        return max((self._clock.now() - started).total_seconds() * 1000.0, 0.0)


def _with_cure(name: str, reason: str | None) -> str | None:
    """The registry's reason for an unbuilt provider, then what cures it, when anything does."""
    cure = missing_credential_cure(name)
    if reason is None or cure is None:
        return reason
    return f"{reason}; {cure}"


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
        topics: SearchTopics = NO_TOPICS,
    ) -> None:
        self._providers = providers
        self._searches = searches
        self._clock = clock
        self._ids = ids
        self._topics = topics
        self._fan_out = FanOutStage(providers, clock=clock, deadline_seconds=deadline_seconds, topics=topics)
        self._pipeline = SearchPipeline(
            expand=PassThroughStage() if expand is None else expand,
            fan_out=self._fan_out,
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
        self._topics.check(request.topic_id)
        created_at = self._clock.now()
        state = SearchState.start(self._ids.new_id(), request)
        for _, stage in self._pipeline.stages:
            state = await stage.run(state)
        uncounted = self._fan_out.uncounted(request)
        search = Search(
            search_id=state.search_id,
            owner_id=request.owner_id,
            organization_id=request.organization_id,
            query=request.query,
            filters=request.filters,
            provider_set=self._fan_out.selection(request),
            status=search_status(state.provider_statuses, uncounted=uncounted),
            expansion=state.expansion,
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
            ranked_candidates=state.ranked_candidates,
            articles=state.articles,
            uncounted=uncounted,
        )
