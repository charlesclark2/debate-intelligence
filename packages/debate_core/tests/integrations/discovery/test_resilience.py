"""ResilientProvider and its CircuitBreaker: timeouts, the three breaker states, holds and health.

Every transition is driven by hand on a :class:`FixedClock` that only moves when a test moves it,
and every expected instant and count is written out from the steps above it (working agreement 6).
The timeout is the one thing measured on the event loop's own clock, with a deadline of a few
milliseconds against a call that never finishes.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from datetime import timedelta
from typing import Any, Literal

import pytest

from debate_core.application.errors import (
    ProviderCircuitOpen,
    ProviderRateLimited,
    ProviderTimedOut,
    ProviderUnavailable,
)
from debate_core.domain.discovery import BreakerState, CandidateResult, ProviderQuery, ProviderResponse
from debate_core.integrations.discovery.resilience import (
    BreakerPermit,
    CircuitBreaker,
    ResiliencePolicy,
    ResilientProvider,
    redact,
)
from debate_core.testing.fakes import FAKE_EPOCH, FixedClock

COOLDOWN = timedelta(seconds=60)
QUERY = ProviderQuery(query="methane leakage")

type Outcome = ProviderResponse | BaseException | Literal["hang"]


def run[ResultT](awaitable: Coroutine[Any, Any, ResultT]) -> ResultT:
    return asyncio.run(awaitable)


def answer(provider: str = "openalex") -> ProviderResponse:
    return ProviderResponse(
        provider=provider,
        results=(CandidateResult(provider=provider, title="A paper", url="https://example.org/a"),),
        elapsed_ms=5.0,
    )


class ScriptedProvider:
    """An adapter that plays its outcomes in order, taking `latency` of the test clock for each."""

    def __init__(
        self,
        clock: FixedClock,
        outcomes: list[Outcome],
        *,
        name: str = "openalex",
        latency: timedelta = timedelta(milliseconds=100),
    ) -> None:
        self._clock = clock
        self._outcomes = list(outcomes)
        self._name = name
        self.latency = latency
        """How far each call moves the test clock: the call's latency."""
        self.calls = 0
        self.cancelled = 0
        self._hanging: asyncio.Event | None = None

    @property
    def name(self) -> str:
        return self._name

    def release(self) -> None:
        """Let the call that is hanging finish, as a failure."""
        assert self._hanging is not None, "nothing is hanging"
        self._hanging.set()

    async def search(self, query: ProviderQuery) -> ProviderResponse:
        self.calls += 1
        outcome = self._outcomes.pop(0)
        self._clock.advance(self.latency)
        if outcome == "hang":
            self._hanging = asyncio.Event()
            try:
                await self._hanging.wait()
            except asyncio.CancelledError:
                self.cancelled += 1
                raise
            raise ProviderUnavailable(self._name, "released after hanging")
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def make_breaker(clock: FixedClock, threshold: int = 3) -> CircuitBreaker:
    return CircuitBreaker(failure_threshold=threshold, cooldown=COOLDOWN, clock=clock)


def make_provider(
    clock: FixedClock,
    outcomes: list[Outcome],
    *,
    threshold: int = 3,
    timeout_seconds: float = 5.0,
    secrets: tuple[str, ...] = (),
) -> tuple[ResilientProvider, ScriptedProvider]:
    inner = ScriptedProvider(clock, outcomes)
    policy = ResiliencePolicy(
        timeout_seconds=timeout_seconds,
        failure_threshold=threshold,
        cooldown_seconds=COOLDOWN.total_seconds(),
    )
    return ResilientProvider(inner, policy, clock=clock, secrets=secrets), inner


# --------------------------------------------------------------------------------------------
# The breaker, by hand: closed
# --------------------------------------------------------------------------------------------


def test_a_new_breaker_is_closed_and_admits_ordinary_calls() -> None:
    breaker = make_breaker(FixedClock())
    assert breaker.state is BreakerState.CLOSED
    assert breaker.admit("openalex") == BreakerPermit(probe=False)
    assert breaker.open_until is None


def test_the_breaker_stays_closed_below_the_threshold_and_opens_on_it() -> None:
    clock = FixedClock()
    breaker = make_breaker(clock, threshold=3)
    for expected_failures in (1, 2):
        breaker.record_failure(breaker.admit("openalex"))
        assert breaker.state is BreakerState.CLOSED
        assert breaker.consecutive_failures == expected_failures

    breaker.record_failure(breaker.admit("openalex"))

    assert breaker.state is BreakerState.OPEN
    assert breaker.consecutive_failures == 3
    assert breaker.open_until == FAKE_EPOCH + timedelta(seconds=60)


def test_a_threshold_of_one_opens_on_the_first_failure() -> None:
    breaker = make_breaker(FixedClock(), threshold=1)
    breaker.record_failure(breaker.admit("openalex"))
    assert breaker.state is BreakerState.OPEN


def test_a_success_resets_the_count_so_only_consecutive_failures_open_the_breaker() -> None:
    breaker = make_breaker(FixedClock(), threshold=3)
    breaker.record_failure(breaker.admit("openalex"))
    breaker.record_failure(breaker.admit("openalex"))
    breaker.record_success(breaker.admit("openalex"))
    assert breaker.consecutive_failures == 0
    breaker.record_failure(breaker.admit("openalex"))
    breaker.record_failure(breaker.admit("openalex"))
    assert breaker.state is BreakerState.CLOSED
    assert breaker.consecutive_failures == 2


# --------------------------------------------------------------------------------------------
# Open
# --------------------------------------------------------------------------------------------


def open_breaker(clock: FixedClock) -> CircuitBreaker:
    breaker = make_breaker(clock, threshold=1)
    breaker.record_failure(breaker.admit("openalex"))
    assert breaker.state is BreakerState.OPEN
    return breaker


def test_an_open_breaker_refuses_calls_and_says_when_it_will_probe() -> None:
    clock = FixedClock()
    breaker = open_breaker(clock)
    with pytest.raises(ProviderCircuitOpen) as refused:
        breaker.admit("openalex")
    assert refused.value.retry_at == FAKE_EPOCH + timedelta(seconds=60)
    assert refused.value.provider == "openalex"


def test_an_open_breaker_still_refuses_one_microsecond_before_the_cool_down_ends() -> None:
    clock = FixedClock()
    breaker = open_breaker(clock)
    clock.advance(timedelta(seconds=60) - timedelta(microseconds=1))
    assert breaker.state is BreakerState.OPEN
    with pytest.raises(ProviderCircuitOpen):
        breaker.admit("openalex")


def test_a_late_failure_while_open_does_not_extend_the_cool_down() -> None:
    clock = FixedClock()
    breaker = make_breaker(clock, threshold=1)
    straggler = breaker.admit("openalex")
    breaker.record_failure(breaker.admit("openalex"))
    clock.advance(timedelta(seconds=30))
    breaker.record_failure(straggler)
    assert breaker.open_until == FAKE_EPOCH + timedelta(seconds=60)


# --------------------------------------------------------------------------------------------
# Half-open
# --------------------------------------------------------------------------------------------


def test_the_breaker_half_opens_exactly_when_the_cool_down_ends() -> None:
    clock = FixedClock()
    breaker = open_breaker(clock)
    clock.advance(timedelta(seconds=60))
    assert breaker.state is BreakerState.HALF_OPEN
    assert breaker.open_until is None


def test_a_half_open_breaker_admits_one_probe_and_refuses_everything_else_while_it_runs() -> None:
    clock = FixedClock()
    breaker = open_breaker(clock)
    clock.advance(timedelta(seconds=60))

    assert breaker.admit("openalex") == BreakerPermit(probe=True)
    with pytest.raises(ProviderCircuitOpen) as refused:
        breaker.admit("openalex")
    assert refused.value.retry_at is None
    assert "another call is already probing it" in str(refused.value)


def test_a_probe_that_succeeds_closes_the_breaker() -> None:
    clock = FixedClock()
    breaker = open_breaker(clock)
    clock.advance(timedelta(seconds=60))
    breaker.record_success(breaker.admit("openalex"))
    assert breaker.state is BreakerState.CLOSED
    assert breaker.consecutive_failures == 0
    assert breaker.admit("openalex") == BreakerPermit(probe=False)


def test_a_probe_that_fails_reopens_the_breaker_for_a_fresh_cool_down() -> None:
    clock = FixedClock()
    breaker = open_breaker(clock)
    clock.advance(timedelta(seconds=75))
    breaker.record_failure(breaker.admit("openalex"))

    assert breaker.state is BreakerState.OPEN
    assert breaker.open_until == FAKE_EPOCH + timedelta(seconds=75 + 60)
    assert breaker.consecutive_failures == 2
    clock.advance(timedelta(seconds=59))
    with pytest.raises(ProviderCircuitOpen):
        breaker.admit("openalex")
    clock.advance(timedelta(seconds=1))
    assert breaker.admit("openalex") == BreakerPermit(probe=True)


def test_a_probe_that_ends_without_an_outcome_frees_the_slot_for_the_next_call() -> None:
    clock = FixedClock()
    breaker = open_breaker(clock)
    clock.advance(timedelta(seconds=60))
    breaker.release(breaker.admit("openalex"))
    assert breaker.state is BreakerState.HALF_OPEN
    assert breaker.admit("openalex") == BreakerPermit(probe=True)


def test_releasing_an_ordinary_call_does_not_free_the_probe_slot() -> None:
    clock = FixedClock()
    breaker = make_breaker(clock, threshold=1)
    straggler = breaker.admit("openalex")
    breaker.record_failure(breaker.admit("openalex"))
    clock.advance(timedelta(seconds=60))
    breaker.admit("openalex")
    breaker.release(straggler)
    with pytest.raises(ProviderCircuitOpen):
        breaker.admit("openalex")


def test_a_late_ordinary_success_does_not_decide_a_half_open_breaker() -> None:
    """Only the probe says whether the provider recovered; a call from before the opening does not."""
    clock = FixedClock()
    breaker = make_breaker(clock, threshold=1)
    straggler = breaker.admit("openalex")
    breaker.record_failure(breaker.admit("openalex"))
    clock.advance(timedelta(seconds=60))
    probe = breaker.admit("openalex")

    breaker.record_success(straggler)

    assert breaker.state is BreakerState.HALF_OPEN
    with pytest.raises(ProviderCircuitOpen):
        breaker.admit("openalex")
    breaker.record_failure(probe)
    assert breaker.state is BreakerState.OPEN


# --------------------------------------------------------------------------------------------
# ResilientProvider: the timeout
# --------------------------------------------------------------------------------------------


def test_a_call_that_outlives_the_timeout_is_cancelled_and_reported_as_timed_out() -> None:
    clock = FixedClock()
    provider, inner = make_provider(clock, ["hang"], timeout_seconds=0.01)

    with pytest.raises(ProviderTimedOut) as timed_out:
        run(provider.search(QUERY))

    assert isinstance(timed_out.value, ProviderUnavailable)
    assert timed_out.value.timeout_seconds == 0.01
    assert str(timed_out.value) == "openalex: no answer within 0.01s"
    assert inner.cancelled == 1
    health = provider.health()
    assert (health.error_count, health.consecutive_failures) == (1, 1)
    assert health.last_error == "openalex: no answer within 0.01s"


def test_a_call_inside_the_timeout_returns_the_adapters_response_unchanged() -> None:
    clock = FixedClock()
    expected = answer()
    provider, inner = make_provider(clock, [expected], timeout_seconds=5.0)
    assert run(provider.search(QUERY)) is expected
    assert inner.calls == 1


def test_an_adapters_own_timeout_error_is_not_mistaken_for_the_deadline() -> None:
    clock = FixedClock()
    provider, _ = make_provider(clock, [TimeoutError("socket read timed out")], timeout_seconds=5.0)
    with pytest.raises(ProviderUnavailable) as failed:
        run(provider.search(QUERY))
    assert not isinstance(failed.value, ProviderTimedOut)
    assert "raised TimeoutError, which it should have translated" in str(failed.value)


def test_timeouts_count_towards_the_breaker() -> None:
    clock = FixedClock()
    provider, inner = make_provider(clock, ["hang", "hang"], threshold=2, timeout_seconds=0.01)
    for _ in range(2):
        with pytest.raises(ProviderTimedOut):
            run(provider.search(QUERY))
    with pytest.raises(ProviderCircuitOpen):
        run(provider.search(QUERY))
    assert inner.calls == 2


# --------------------------------------------------------------------------------------------
# ResilientProvider: the breaker in front of a real call
# --------------------------------------------------------------------------------------------


def test_after_n_consecutive_failures_calls_are_skipped_for_the_cool_down() -> None:
    clock = FixedClock()
    failures: list[Outcome] = [ProviderUnavailable("openalex", "HTTP 503") for _ in range(3)]
    provider, inner = make_provider(clock, [*failures, answer()], threshold=3)
    for _ in range(3):
        with pytest.raises(ProviderUnavailable):
            run(provider.search(QUERY))
    opened_at = clock.now()

    for _ in range(2):
        with pytest.raises(ProviderCircuitOpen) as skipped:
            run(provider.search(QUERY))
        assert skipped.value.retry_at == opened_at + COOLDOWN
    assert inner.calls == 3
    assert provider.health().skipped_count == 2

    clock.advance(COOLDOWN)
    assert provider.health().state is BreakerState.HALF_OPEN
    run(provider.search(QUERY))
    assert inner.calls == 4
    assert provider.health().state is BreakerState.CLOSED


def test_a_half_open_provider_sends_one_probe_and_skips_concurrent_calls() -> None:
    clock = FixedClock()
    provider, inner = make_provider(
        clock, [ProviderUnavailable("openalex", "HTTP 503"), "hang"], threshold=1, timeout_seconds=5.0
    )
    with pytest.raises(ProviderUnavailable):
        run(provider.search(QUERY))
    clock.advance(COOLDOWN)

    async def probe_while_another_call_arrives() -> tuple[BaseException | None, BaseException | None]:
        probe = asyncio.create_task(provider.search(QUERY))
        await asyncio.sleep(0)
        second: BaseException | None = None
        try:
            await provider.search(QUERY)
        except ProviderCircuitOpen as refused:
            second = refused
        inner.release()
        try:
            await probe
        except ProviderUnavailable as failed:
            return failed, second
        return None, second

    probe_failure, second = run(probe_while_another_call_arrives())

    assert isinstance(second, ProviderCircuitOpen)
    assert inner.calls == 2
    assert isinstance(probe_failure, ProviderUnavailable)
    health = provider.health()
    assert health.state is BreakerState.OPEN
    assert health.open_until == clock.now() + COOLDOWN


def test_a_cancelled_probe_leaves_the_breaker_half_open_for_the_next_call() -> None:
    clock = FixedClock()
    provider, inner = make_provider(
        clock, [ProviderUnavailable("openalex", "HTTP 503"), "hang", answer()], threshold=1
    )
    with pytest.raises(ProviderUnavailable):
        run(provider.search(QUERY))
    clock.advance(COOLDOWN)

    async def cancel_the_probe() -> None:
        probe = asyncio.create_task(provider.search(QUERY))
        await asyncio.sleep(0)
        probe.cancel()
        with pytest.raises(asyncio.CancelledError):
            await probe

    run(cancel_the_probe())
    assert inner.cancelled == 1
    assert provider.health().state is BreakerState.HALF_OPEN
    run(provider.search(QUERY))
    assert provider.health().state is BreakerState.CLOSED


# --------------------------------------------------------------------------------------------
# ResilientProvider: never retries, honours rate limits, classifies failures
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("failure", "raised"),
    [
        (ProviderUnavailable("openalex", "HTTP 503"), ProviderUnavailable),
        (ProviderRateLimited("openalex", "HTTP 429", retry_after_seconds=1.0), ProviderRateLimited),
        (ValueError("adapter bug"), ProviderUnavailable),
    ],
    ids=["unavailable", "rate-limited", "untranslated"],
)
def test_a_failed_call_is_made_exactly_once(failure: Exception, raised: type[Exception]) -> None:
    clock = FixedClock()
    provider, inner = make_provider(clock, [failure, answer()])
    with pytest.raises(raised):
        run(provider.search(QUERY))
    assert inner.calls == 1


def test_a_rate_limit_holds_every_call_until_retry_after_has_passed() -> None:
    clock = FixedClock()
    limited = ProviderRateLimited("openalex", "HTTP 429", retry_after_seconds=120.0)
    provider, inner = make_provider(clock, [limited, answer()], threshold=5)
    with pytest.raises(ProviderRateLimited):
        run(provider.search(QUERY))
    limited_at = clock.now()

    clock.advance(timedelta(seconds=20))
    with pytest.raises(ProviderRateLimited) as held:
        run(provider.search(QUERY))
    assert held.value.retry_after_seconds == 100.0
    assert inner.calls == 1
    health = provider.health()
    assert health.rate_limited_until == limited_at + timedelta(seconds=120)
    assert health.skipped_count == 1
    assert health.state is BreakerState.CLOSED

    clock.advance(timedelta(seconds=100))
    assert provider.health().rate_limited_until is None
    run(provider.search(QUERY))
    assert inner.calls == 2


def test_a_rate_limit_without_retry_after_holds_for_the_cool_down() -> None:
    clock = FixedClock()
    provider, inner = make_provider(clock, [ProviderRateLimited("openalex"), answer()], threshold=5)
    with pytest.raises(ProviderRateLimited):
        run(provider.search(QUERY))
    clock.advance(COOLDOWN - timedelta(seconds=1))
    with pytest.raises(ProviderRateLimited):
        run(provider.search(QUERY))
    clock.advance(timedelta(seconds=1))
    run(provider.search(QUERY))
    assert inner.calls == 2


def test_an_untranslated_exception_becomes_provider_unavailable_naming_its_type() -> None:
    clock = FixedClock()
    leaked = KeyError("results")
    provider, _ = make_provider(clock, [leaked])
    with pytest.raises(ProviderUnavailable) as failed:
        run(provider.search(QUERY))
    assert str(failed.value) == "openalex: the adapter raised KeyError, which it should have translated"
    assert failed.value.__cause__ is leaked


def test_a_response_under_another_name_is_a_failure() -> None:
    clock = FixedClock()
    provider, _ = make_provider(clock, [answer(provider="crossref")])
    with pytest.raises(ProviderUnavailable, match="the adapter answered as 'crossref'"):
        run(provider.search(QUERY))
    assert provider.health().error_count == 1


# --------------------------------------------------------------------------------------------
# Health
# --------------------------------------------------------------------------------------------


def test_health_reports_counts_last_error_and_the_median_latency() -> None:
    clock = FixedClock()
    provider, inner = make_provider(clock, [answer(), ProviderUnavailable("openalex", "HTTP 502"), answer()])
    assert provider.health().p50_latency_ms is None

    inner.latency = timedelta(milliseconds=100)
    run(provider.search(QUERY))
    inner.latency = timedelta(milliseconds=300)
    with pytest.raises(ProviderUnavailable):
        run(provider.search(QUERY))
    failed_at = clock.now()
    inner.latency = timedelta(milliseconds=200)
    run(provider.search(QUERY))

    health = provider.health()
    assert health.provider == "openalex"
    assert health.state is BreakerState.CLOSED
    assert (health.success_count, health.error_count, health.skipped_count) == (2, 1, 0)
    assert health.consecutive_failures == 0
    assert health.last_error == "openalex: HTTP 502"
    assert health.last_error_at == failed_at
    assert health.p50_latency_ms == 200.0
    assert health.open_until is None


def test_the_median_is_taken_over_the_latency_window_only() -> None:
    clock = FixedClock()
    inner = ScriptedProvider(clock, [answer(), answer(), answer()])
    provider = ResilientProvider(inner, ResiliencePolicy(latency_window=2), clock=clock)
    for latency_ms in (1000, 100, 300):
        inner.latency = timedelta(milliseconds=latency_ms)
        run(provider.search(QUERY))
    assert provider.health().p50_latency_ms == 200.0


def test_an_open_provider_reports_when_it_will_probe() -> None:
    clock = FixedClock()
    provider, _ = make_provider(clock, [ProviderUnavailable("openalex", "HTTP 503")], threshold=1)
    with pytest.raises(ProviderUnavailable):
        run(provider.search(QUERY))
    health = provider.health()
    assert health.state is BreakerState.OPEN
    assert health.open_until == clock.now() + COOLDOWN
    assert repr(provider) == "ResilientProvider(name='openalex', state='open')"


# --------------------------------------------------------------------------------------------
# Secrets
# --------------------------------------------------------------------------------------------

API_KEY = "s2-key-0d9f8e7c6b5a"
CONTACT_EMAIL = "coach+discovery@example.org"
SECRETS = (API_KEY, CONTACT_EMAIL)
EMAIL_IN_A_URL = "coach%2Bdiscovery%40example.org"


def leaks(text: str) -> list[str]:
    return [
        secret for secret in (API_KEY, CONTACT_EMAIL, EMAIL_IN_A_URL, "coach+discovery") if secret in text
    ]


def test_redact_removes_a_value_in_every_spelling_a_url_gives_it() -> None:
    text = f"GET https://api.example.org/works?mailto={EMAIL_IN_A_URL}&key={API_KEY} for {CONTACT_EMAIL}"
    assert redact(text, SECRETS) == "GET https://api.example.org/works?mailto=***&key=*** for ***"
    assert redact("coach discovery@example.org", ("coach discovery@example.org",)) == "***"
    assert redact("q=coach+discovery%40example.org", ("coach discovery@example.org",)) == "q=***"
    assert redact("nothing here", ("", API_KEY)) == "nothing here"


def test_no_secret_reaches_an_error_its_cause_a_log_line_the_health_record_or_a_repr(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="debate_core.integrations.discovery")
    clock = FixedClock()
    url = f"https://api.example.org/works?mailto={EMAIL_IN_A_URL}&api_key={API_KEY}"
    transport = RuntimeError(f"connection reset fetching {url}")
    adapter_error = ProviderUnavailable("openalex", f"GET {url} failed for {CONTACT_EMAIL}")
    adapter_error.__cause__ = transport
    leaked = OSError(f"[Errno 54] {url}")
    provider, _ = make_provider(clock, [adapter_error, leaked], threshold=2, secrets=SECRETS)

    raised: list[BaseException] = []
    for _ in range(2):
        with pytest.raises(ProviderUnavailable) as failed:
            run(provider.search(QUERY))
        raised.append(failed.value)
    with pytest.raises(ProviderCircuitOpen) as skipped:
        run(provider.search(QUERY))
    raised.append(skipped.value)

    surfaces: list[str] = [repr(provider), provider.health().model_dump_json()]
    for error in raised:
        chain: BaseException | None = error
        while chain is not None:
            surfaces.extend((str(chain), repr(chain)))
            chain = chain.__cause__ or chain.__context__
    surfaces.extend(record.getMessage() for record in caplog.records)

    assert caplog.records, "the failures should have been logged"
    assert all(not leaks(surface) for surface in surfaces), [
        surface for surface in surfaces if leaks(surface)
    ]
    assert (
        provider.health().last_error
        == "openalex: the adapter raised OSError, which it should have translated"
    )
    assert str(raised[0]) == (
        "openalex: GET https://api.example.org/works?mailto=***&api_key=*** failed for ***"
    )


# --------------------------------------------------------------------------------------------
# Policy
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("timeout_seconds", 0.0),
        ("failure_threshold", 0),
        ("cooldown_seconds", 0.0),
        ("latency_window", 0),
    ],
)
def test_a_policy_refuses_values_that_would_disable_it(field: str, value: float) -> None:
    with pytest.raises(ValueError, match=field):
        ResiliencePolicy(**{field: value})  # pyright: ignore[reportArgumentType]


def test_the_policy_defaults_match_the_settings_defaults() -> None:
    assert ResiliencePolicy() == ResiliencePolicy(
        timeout_seconds=10.0, failure_threshold=3, cooldown_seconds=60.0, latency_window=50
    )
