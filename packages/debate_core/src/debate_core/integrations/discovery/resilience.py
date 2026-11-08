"""Timeouts, a circuit breaker and a health record, the same for every discovery provider.

A federated search asks several providers at once and must not be held hostage by one of them
(architecture proposal §15). :class:`ResilientProvider` wraps an adapter and is itself a
:class:`~debate_core.application.ports.providers.SearchProvider`, so the code that fans a query out
(E08) never knows the difference. For every call it:

* **gives the adapter a fixed time** (:attr:`ResiliencePolicy.timeout_seconds`) and cancels it when
  the time is up, raising :class:`~debate_core.application.errors.ProviderTimedOut`;
* **counts consecutive failures** in a :class:`CircuitBreaker`. After
  :attr:`ResiliencePolicy.failure_threshold` of them the breaker opens and calls are refused with
  :class:`~debate_core.application.errors.ProviderCircuitOpen`, without reaching the provider, for
  :attr:`ResiliencePolicy.cooldown_seconds`. Then it half-opens: exactly one call goes through as a
  probe, and its outcome closes the breaker or opens it for another cool-down;
* **honours a rate limit.** When the adapter reports
  :class:`~debate_core.application.errors.ProviderRateLimited`, no call reaches the provider until
  its `Retry-After` has passed (the cool-down, when it named none);
* **classifies failures** into the port's error types. An adapter is supposed to translate its own
  library's exceptions; one that leaks something else is reported as
  :class:`~debate_core.application.errors.ProviderUnavailable` naming the exception's type;
* **records health** for the CLI's status footer (:meth:`ResilientProvider.health`);
* **does not hold a provider's own pace against it** (v1-e07-t10). An adapter that queues its
  requests on a :class:`~debate_core.integrations.discovery.pace.Pacer` tells the wrapper, through
  the listener installed for each call, when a call starts waiting and how its wait ended. While a
  call is queued its timeout is suspended, and when its pace releases it the timeout is moved on by
  the time it was queued, so the timeout fails a call only for `timeout_seconds` of time it was not
  queued: a call that was sent and runs slow still times out. The latency recorded is the call's
  time less its queued time, for an answer and a failure alike. A call whose pace never sent it (its
  turn would have come after its deadline, and the adapter answered "not asked") is returned as it
  is but counted apart, in `not_asked_count`: neither a success, a failure nor a latency sample, and
  its breaker permit is released with no verdict, as a cancelled call's is. A call that asks
  several queries at once is queued while any one of them waits for its turn;
* **asks an adapter that answers several queries at once with all of them** (v1-e08-t10):
  :func:`resilient` wraps a :class:`~debate_core.application.ports.providers.MultiQuerySearchProvider`
  in :class:`ResilientMultiQueryProvider`, whose `search_each` is one guarded call for every query
  of a search: one admission by the breaker, one timeout, and one success or failure in the health
  record, however many queries it carries;
* **never retries.** One search is at most one call to the adapter. Retrying a non-idempotent
  request could do the provider's work twice, and retrying a refused one ignores the provider's own
  rate limit; an adapter that retries an idempotent `GET` after a transient error does so inside its
  own call, under the same timeout.

Every message this module records, logs or raises has the configured credentials and contact email
removed first, in an adapter's exception and in each exception it was raised from, and the same
values are filtered out of httpx's and this package's log records
(:mod:`~debate_core.integrations.discovery.redaction`).

The breaker reads time only from the injected
:class:`~debate_core.application.ports.providers.Clock`, so every transition can be driven by hand
in a test with :class:`~debate_core.testing.fakes.clock_and_ids.FixedClock`. The timeout is the event
loop's own, because cancelling a call that is still running is the event loop's job.
"""

from __future__ import annotations

import asyncio
import statistics
from collections import deque
from collections.abc import Awaitable, Callable, Generator, Iterable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta

from debate_core.application.errors import (
    ProviderCircuitOpen,
    ProviderError,
    ProviderRateLimited,
    ProviderTimedOut,
    ProviderUnavailable,
)
from debate_core.application.ports.providers import Clock, MultiQuerySearchProvider, SearchProvider
from debate_core.domain.discovery import BreakerState, ProviderHealth, ProviderQuery, ProviderResponse
from debate_core.integrations.discovery.pace import TurnOutcome, listening
from debate_core.integrations.discovery.redaction import logger, protect_logs, redact_exception_chain

__all__ = [
    "BreakerPermit",
    "CircuitBreaker",
    "ResiliencePolicy",
    "ResilientMultiQueryProvider",
    "ResilientProvider",
    "resilient",
]


@dataclass(frozen=True, slots=True)
class ResiliencePolicy:
    """How long a provider is given, and how quickly it is benched.

    Built from :class:`~debate_core.application.settings.ProviderSettings` by the registry; the
    defaults here are the settings' defaults.
    """

    timeout_seconds: float = 10.0
    """How long one call may take before it is cancelled, not counting time queued on its own pace."""

    failure_threshold: int = 3
    """Consecutive failures that open the breaker."""

    cooldown_seconds: float = 60.0
    """How long an open breaker refuses calls before it lets a probe through."""

    latency_window: int = 50
    """How many recent calls the median latency is taken over."""

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError(f"timeout_seconds must be positive, got {self.timeout_seconds}")
        if self.failure_threshold < 1:
            raise ValueError(f"failure_threshold must be at least 1, got {self.failure_threshold}")
        if self.cooldown_seconds <= 0:
            raise ValueError(f"cooldown_seconds must be positive, got {self.cooldown_seconds}")
        if self.latency_window < 1:
            raise ValueError(f"latency_window must be at least 1, got {self.latency_window}")


@dataclass(frozen=True, slots=True)
class BreakerPermit:
    """Leave to make one call, handed out by :meth:`CircuitBreaker.admit`.

    The outcome of the call is reported back with the permit, because only the probe's outcome may
    decide a half-open breaker: a call that was admitted while the breaker was still closed and
    finishes after it opened says nothing about whether the provider has recovered.
    """

    probe: bool
    """True for the single call a half-open breaker lets through."""


class CircuitBreaker:
    """Closed, open and half-open, driven by consecutive failures and an injected clock.

    * **Closed:** every call is admitted. A success resets the failure count; the
      `failure_threshold`-th consecutive failure opens the breaker.
    * **Open:** every call is refused until `cooldown` has passed since it opened.
    * **Half-open:** the cool-down is over. The next call is admitted as the probe and every other
      call is refused while it runs. The probe's success closes the breaker; its failure opens it for
      another full cool-down. A probe that ends without a verdict (it was cancelled) frees the slot
      for the next call.

    The open-to-half-open step happens when the state is next read, so nothing has to run on a
    timer.
    """

    def __init__(self, *, failure_threshold: int, cooldown: timedelta, clock: Clock) -> None:
        self._failure_threshold = failure_threshold
        self._cooldown = cooldown
        self._clock = clock
        self._state = BreakerState.CLOSED
        self._consecutive_failures = 0
        self._open_until: datetime | None = None
        self._probe_in_flight = False

    @property
    def state(self) -> BreakerState:
        """Where the breaker stands now; an open breaker whose cool-down has passed is half-open."""
        if (
            self._state is BreakerState.OPEN
            and self._open_until is not None
            and self._clock.now() >= self._open_until
        ):
            self._state = BreakerState.HALF_OPEN
            self._open_until = None
        return self._state

    @property
    def consecutive_failures(self) -> int:
        """Failures since the last success."""
        return self._consecutive_failures

    @property
    def open_until(self) -> datetime | None:
        """When an open breaker lets a probe through; `None` unless it is open."""
        return self._open_until if self.state is BreakerState.OPEN else None

    def admit(self, provider: str) -> BreakerPermit:
        """Leave to make one call, or :class:`ProviderCircuitOpen` if the breaker refuses it."""
        state = self.state
        if state is BreakerState.CLOSED:
            return BreakerPermit(probe=False)
        if state is BreakerState.HALF_OPEN and not self._probe_in_flight:
            self._probe_in_flight = True
            return BreakerPermit(probe=True)
        raise ProviderCircuitOpen(provider, self._open_until)

    def record_success(self, permit: BreakerPermit) -> None:
        """The admitted call returned a response."""
        if permit.probe:
            self._probe_in_flight = False
            self._close()
        elif self.state is BreakerState.CLOSED:
            self._consecutive_failures = 0

    def record_failure(self, permit: BreakerPermit) -> None:
        """The admitted call failed."""
        self._consecutive_failures += 1
        if permit.probe:
            self._probe_in_flight = False
            self._open()
        elif self.state is BreakerState.CLOSED and self._consecutive_failures >= self._failure_threshold:
            self._open()

    def release(self, permit: BreakerPermit) -> None:
        """The admitted call ended without an outcome (it was cancelled); nothing is decided."""
        if permit.probe:
            self._probe_in_flight = False

    def _open(self) -> None:
        self._state = BreakerState.OPEN
        self._open_until = self._clock.now() + self._cooldown

    def _close(self) -> None:
        self._state = BreakerState.CLOSED
        self._open_until = None
        self._consecutive_failures = 0


class ResilientProvider:
    """A discovery adapter with a timeout, a circuit breaker, a rate-limit hold and a health record.

    A :class:`~debate_core.application.ports.providers.SearchProvider` itself, under the adapter's
    name. `secrets` are the credential and contact-email values configured for discovery; none of
    them appears in anything this wrapper records, logs, raises or prints.
    """

    def __init__(
        self,
        inner: SearchProvider,
        policy: ResiliencePolicy,
        *,
        clock: Clock,
        secrets: Iterable[str] = (),
    ) -> None:
        self._inner = inner
        self._name = inner.name
        self._policy = policy
        self._clock = clock
        self._secrets = tuple(value for value in secrets if value)
        protect_logs(self._secrets)
        self._breaker = CircuitBreaker(
            failure_threshold=policy.failure_threshold,
            cooldown=timedelta(seconds=policy.cooldown_seconds),
            clock=clock,
        )
        self._latencies_ms: deque[float] = deque(maxlen=policy.latency_window)
        self._success_count = 0
        self._error_count = 0
        self._skipped_count = 0
        self._not_asked_count = 0
        self._last_error: str | None = None
        self._last_error_at: datetime | None = None
        self._rate_limited_until: datetime | None = None

    @property
    def name(self) -> str:
        """The wrapped adapter's name, as it appears in settings."""
        return self._name

    @property
    def policy(self) -> ResiliencePolicy:
        """The timeout and breaker settings this provider runs under."""
        return self._policy

    def __repr__(self) -> str:
        return f"ResilientProvider(name={self._name!r}, state={self._breaker.state.value!r})"

    async def search(self, query: ProviderQuery) -> ProviderResponse:
        """Ask the wrapped adapter once, within the timeout, unless the breaker or a hold says not to."""

        async def ask() -> tuple[ProviderResponse, ...]:
            return (await self._inner.search(query),)

        (response,) = await self._guarded(ask, expected=1)
        return response

    async def _guarded(
        self, ask: Callable[[], Awaitable[Sequence[ProviderResponse]]], *, expected: int
    ) -> tuple[ProviderResponse, ...]:
        """Make one call to the adapter under the hold, the breaker and the timeout; `expected` answers."""
        self._refuse_while_rate_limited()
        try:
            permit = self._breaker.admit(self._name)
        except ProviderCircuitOpen:
            self._skipped_count += 1
            logger.debug("discovery provider %s skipped: circuit breaker open", self._name)
            raise
        deadline = asyncio.timeout(self._policy.timeout_seconds)
        call = _CallTime(deadline, self._clock)
        try:
            async with deadline:
                with call.timing():
                    responses = tuple(await ask())
        except TimeoutError as error:
            if deadline.expired():
                failure: ProviderError = ProviderTimedOut(self._name, self._policy.timeout_seconds)
                self._fail(permit, failure, call)
                raise failure from None
            failure = self._untranslated(error)
            self._fail(permit, failure, call, cause=error)
            raise failure from error
        except ProviderError as error:
            self._fail(permit, error, call)
            raise
        except Exception as error:
            failure = self._untranslated(error)
            self._fail(permit, failure, call, cause=error)
            raise failure from error
        except BaseException:
            self._breaker.release(permit)
            raise
        strangers = [response.provider for response in responses if response.provider != self._name]
        if strangers:
            failure = ProviderUnavailable(self._name, f"the adapter answered as {strangers[0]!r}")
            self._fail(permit, failure, call)
            raise failure
        if len(responses) != expected:
            failure = ProviderUnavailable(
                self._name, f"the adapter answered {len(responses)} of {expected} queries"
            )
            self._fail(permit, failure, call)
            raise failure
        if call.not_asked:
            self._not_asked(permit)
        else:
            self._succeed(permit, call)
        return responses

    async def aclose(self) -> None:
        """Close the wrapped adapter's connections, when it holds any (an `aclose` of its own).

        The search command closes every provider when its search ends (v1-e08-t05); an adapter with
        nothing to close, such as a test's fake, has no `aclose` and is left as it is.
        """
        close = getattr(self._inner, "aclose", None)
        if close is not None:
            await close()

    def health(self) -> ProviderHealth:
        """This provider's record so far, redacted, for the CLI's status footer."""
        now = self._clock.now()
        state = self._breaker.state
        held = self._rate_limited_until is not None and now < self._rate_limited_until
        return ProviderHealth(
            provider=self._name,
            state=state,
            consecutive_failures=self._breaker.consecutive_failures,
            success_count=self._success_count,
            error_count=self._error_count,
            skipped_count=self._skipped_count,
            not_asked_count=self._not_asked_count,
            last_error=self._last_error,
            last_error_at=self._last_error_at,
            p50_latency_ms=statistics.median(self._latencies_ms) if self._latencies_ms else None,
            open_until=self._breaker.open_until,
            rate_limited_until=self._rate_limited_until if held else None,
        )

    def _refuse_while_rate_limited(self) -> None:
        if self._rate_limited_until is None:
            return
        remaining = (self._rate_limited_until - self._clock.now()).total_seconds()
        if remaining <= 0:
            self._rate_limited_until = None
            return
        self._skipped_count += 1
        logger.debug("discovery provider %s skipped: rate-limit hold", self._name)
        raise ProviderRateLimited(
            self._name, "holding off as the provider asked", retry_after_seconds=remaining
        )

    def _untranslated(self, error: BaseException) -> ProviderUnavailable:
        return ProviderUnavailable(
            self._name, f"the adapter raised {type(error).__name__}, which it should have translated"
        )

    def _succeed(self, permit: BreakerPermit, call: _CallTime) -> None:
        was = self._breaker.state
        self._breaker.record_success(permit)
        self._success_count += 1
        self._latencies_ms.append(call.latency_ms())
        if was is not BreakerState.CLOSED and self._breaker.state is BreakerState.CLOSED:
            logger.info("discovery provider %s recovered: circuit breaker closed", self._name)

    def _fail(
        self,
        permit: BreakerPermit,
        failure: ProviderError,
        call: _CallTime,
        *,
        cause: BaseException | None = None,
    ) -> None:
        redact_exception_chain(failure, self._secrets)
        if cause is not None:
            redact_exception_chain(cause, self._secrets)
        was = self._breaker.state
        self._breaker.record_failure(permit)
        self._error_count += 1
        self._latencies_ms.append(call.latency_ms())
        now = self._clock.now()
        self._last_error = str(failure)
        self._last_error_at = now
        if isinstance(failure, ProviderRateLimited):
            wait = failure.retry_after_seconds
            hold = timedelta(seconds=self._policy.cooldown_seconds if wait is None else max(wait, 0.0))
            self._rate_limited_until = now + hold
        logger.warning("discovery provider %s failed: %s", self._name, self._last_error)
        if was is not BreakerState.OPEN and self._breaker.state is BreakerState.OPEN:
            logger.warning(
                "discovery provider %s benched: circuit breaker open until %s",
                self._name,
                self._breaker.open_until,
            )

    def _not_asked(self, permit: BreakerPermit) -> None:
        """The adapter's own pace never sent the call: no verdict for the breaker, no latency."""
        self._breaker.release(permit)
        self._not_asked_count += 1
        logger.debug("discovery provider %s answered not asked: its own pace never sent the call", self._name)


class _CallTime:
    """One call's time, and how much of it was queued on the adapter's own pace.

    The :class:`~debate_core.integrations.discovery.pace.PaceListener` the wrapper installs for the
    call. The call is queued while any of its pace turns is waiting. Its timeout is suspended then
    and moved on by the queued time when the last wait ends, on the event loop's clock, which the
    timeout runs on; its latency is read from the injected clock, less the time queued.
    """

    def __init__(self, deadline: asyncio.Timeout, clock: Clock) -> None:
        self._deadline = deadline
        self._clock = clock
        self._loop = asyncio.get_running_loop()
        self._started = clock.now()
        self._waiting = 0
        self._waiting_since = self._started
        self._waiting_since_loop = 0.0
        self._queued = timedelta(0)
        self._queued_loop_seconds = 0.0
        self._released = 0
        self._refused = 0
        self._first_deadline: float | None = None
        self._timing = False

    @contextmanager
    def timing(self) -> Generator[None]:
        """Listen to the call's pace turns; entered inside the call's `asyncio.timeout`."""
        self._first_deadline = self._deadline.when()
        self._timing = True
        try:
            with listening(self):
                yield
        finally:
            self._timing = False

    def waiting(self) -> None:
        self._waiting += 1
        if self._waiting == 1:
            self._waiting_since = self._clock.now()
            self._waiting_since_loop = self._loop.time()
            self._move_deadline(None)

    def waited(self, outcome: TurnOutcome) -> None:
        if outcome is TurnOutcome.RELEASED:
            self._released += 1
        elif outcome is TurnOutcome.NOT_ASKED:
            self._refused += 1
        self._waiting -= 1
        if self._waiting == 0:
            self._queued += self._clock.now() - self._waiting_since
            self._queued_loop_seconds += self._loop.time() - self._waiting_since_loop
            first = self._first_deadline
            self._move_deadline(None if first is None else first + self._queued_loop_seconds)

    @property
    def not_asked(self) -> bool:
        """Every pace turn the call took was refused: the adapter sent nothing."""
        return self._refused > 0 and self._released == 0

    def latency_ms(self) -> float:
        """The call's time so far, less the time it was queued on its pace."""
        now = self._clock.now()
        queued = self._queued + (now - self._waiting_since if self._waiting else timedelta(0))
        return max((now - self._started - queued).total_seconds() * 1000.0, 0.0)

    def _move_deadline(self, when: float | None) -> None:
        if self._timing and not self._deadline.expired():
            self._deadline.reschedule(when)


class ResilientMultiQueryProvider(ResilientProvider):
    """A :class:`ResilientProvider` over an adapter that answers several queries at once.

    A :class:`~debate_core.application.ports.providers.MultiQuerySearchProvider` itself, so the
    fan-out asks it every query of a search in one call (v1-e08-t10). That call is guarded exactly as
    one query is: the hold, one admission by the breaker, one timeout over the whole call, and one
    success or failure in the health record. An adapter that answers a different number of queries
    than it was asked has failed, as one answering under another name has.
    """

    def __init__(
        self,
        inner: MultiQuerySearchProvider,
        policy: ResiliencePolicy,
        *,
        clock: Clock,
        secrets: Iterable[str] = (),
    ) -> None:
        super().__init__(inner, policy, clock=clock, secrets=secrets)
        self._each = inner

    async def search_each(self, queries: Sequence[ProviderQuery]) -> tuple[ProviderResponse, ...]:
        """Ask the wrapped adapter every query in one call, under one timeout, admission and record."""
        asked = tuple(queries)

        async def ask() -> tuple[ProviderResponse, ...]:
            return await self._each.search_each(asked)

        return await self._guarded(ask, expected=len(asked))


def resilient(
    inner: SearchProvider, policy: ResiliencePolicy, *, clock: Clock, secrets: Iterable[str] = ()
) -> ResilientProvider:
    """`inner` wrapped: in a :class:`ResilientMultiQueryProvider` when it answers several queries at once."""
    if isinstance(inner, MultiQuerySearchProvider):
        return ResilientMultiQueryProvider(inner, policy, clock=clock, secrets=secrets)
    return ResilientProvider(inner, policy, clock=clock, secrets=secrets)
