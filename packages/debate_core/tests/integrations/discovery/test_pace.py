"""The shared pacer, and what ResilientProvider makes of a call's time on it (v1-e07-t10).

Every test runs on :func:`~debate_core.testing.virtual_time.run_in_virtual_time`: the pacer's sleeps,
the wrapper's timeout and every clock read the one virtual loop clock, so a wait of seconds takes
none and every instant is exact. Every expected start, latency and count is written out by hand
from the pace and the scripted work above it (working agreement 6).
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Final, Literal

import pytest

from debate_core.application.errors import (
    ProviderCircuitOpen,
    ProviderError,
    ProviderRateLimited,
    ProviderTimedOut,
    ProviderUnavailable,
)
from debate_core.domain.discovery import (
    BreakerState,
    CandidateResult,
    ProviderHealth,
    ProviderQuery,
    ProviderResponse,
)
from debate_core.integrations.discovery.pace import Pace, Pacer, TurnOutcome, listening
from debate_core.integrations.discovery.resilience import (
    ResiliencePolicy,
    ResilientMultiQueryProvider,
    ResilientProvider,
)
from debate_core.testing.fakes.clock_and_ids import FAKE_EPOCH
from debate_core.testing.virtual_time import EventLoopClock, run_in_virtual_time

NAME: Final = "paced"
QUERY: Final = ProviderQuery(query="methane leakage")
NOT_ASKED: Final = "paced: not asked: its turn came too late"

type Work = float | Literal["fail", "hang", "429"]
"""What one sent call does: answer after that many seconds, fail after 0.4 s, never finish, or be
refused 0.25 s later with a 429 that states no Retry-After."""


def now_seconds() -> float:
    return asyncio.get_running_loop().time()


@dataclass
class PacedAdapter:
    """An adapter that takes a turn on `pacer` for each query and then does its scripted work."""

    pacer: Pacer
    work: list[Work]
    within: float = 30.0
    starts: list[tuple[str, float]] = field(default_factory=list[tuple[str, float]])

    @property
    def name(self) -> str:
        return NAME

    async def search(self, query: ProviderQuery) -> ProviderResponse:
        async with self.pacer.turn(within=self.within) as sent:
            if not sent:
                return ProviderResponse(provider=NAME, elapsed_ms=0.0, partial=True, error=NOT_ASKED)
            self.starts.append((query.query, now_seconds()))
            work = self.work.pop(0)
            if work == "hang":
                await asyncio.sleep(3600)
            if work == "429":
                await asyncio.sleep(0.25)
                raise ProviderRateLimited(NAME, "HTTP 429")
            if work == "fail":
                await asyncio.sleep(0.4)
                raise ProviderUnavailable(NAME, "HTTP 503")
            assert isinstance(work, float)
            await asyncio.sleep(work)
        result = CandidateResult(provider=NAME, title=query.query, url="https://example.org/a")
        return ProviderResponse(provider=NAME, elapsed_ms=0.0, results=(result,))


@dataclass
class PacedMultiQueryAdapter(PacedAdapter):
    """The same, answering every query of a search in one call, each query on its own turn."""

    async def search_each(self, queries: Sequence[ProviderQuery]) -> tuple[ProviderResponse, ...]:
        return tuple(await asyncio.gather(*(self.search(query) for query in queries)))


def wrapped(
    pace: Pace,
    work: list[Work],
    *,
    timeout_seconds: float = 5.0,
    within: float = 30.0,
    threshold: int = 3,
    cooldown_seconds: float = 60.0,
    draw: float = 0.0,
) -> tuple[ResilientProvider, PacedAdapter]:
    """A paced adapter in the wrapper, both on the loop's clock. Build it inside the running loop.

    `draw` is every random fraction the wrapper's backoff draws."""
    clock = EventLoopClock()
    adapter = PacedAdapter(Pacer(pace, clock=clock), work, within=within)
    policy = ResiliencePolicy(
        timeout_seconds=timeout_seconds, failure_threshold=threshold, cooldown_seconds=cooldown_seconds
    )
    return ResilientProvider(adapter, policy, clock=clock, random_fraction=lambda: draw), adapter


def query(number: int) -> ProviderQuery:
    return ProviderQuery(query=f"query {number}")


# --------------------------------------------------------------------------------------------
# The pacer: first come, first served, at its rate, burst and concurrency
# --------------------------------------------------------------------------------------------


def most_starts_in_any_window(starts: Sequence[float], seconds: float) -> int:
    """The most starts any window of `seconds` that opens at a start holds (the busiest windows do)."""
    return max(sum(1 for other in starts if start <= other < start + seconds - 1e-9) for start in starts)


@pytest.mark.parametrize(
    ("pace", "work_seconds", "expected_starts"),
    [
        (Pace(requests=2, interval_seconds=1.0), 0.0, [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]),
        (Pace(requests=4, interval_seconds=2.0, burst=2), 0.0, [0.0, 0.0, 1.0, 1.0, 2.0, 2.0]),
        (Pace(requests=10, interval_seconds=1.0, concurrency=2), 1.0, [0.0, 0.1, 1.0, 1.1, 2.0, 2.1]),
        (Pace(requests=1, interval_seconds=1.0, concurrency=1), 1.5, [0.0, 1.5, 3.0, 4.5, 6.0, 7.5]),
    ],
    ids=[
        "two a second, evenly spaced",
        "four every two seconds, two back to back",
        "ten a second, two at a time",
        "one a second, one at a time, answers slower than the pace",
    ],
)
def test_a_pace_shared_by_concurrent_calls_releases_them_in_order_at_its_rate(
    pace: Pace, work_seconds: float, expected_starts: list[float]
) -> None:
    async def scenario() -> PacedAdapter:
        adapter = PacedAdapter(Pacer(pace, clock=EventLoopClock()), [work_seconds] * 6)
        await asyncio.gather(*(adapter.search(query(number)) for number in range(6)))
        return adapter

    adapter = run_in_virtual_time(scenario())

    assert [name for name, _ in adapter.starts] == [query(number).query for number in range(6)]
    starts = [start for _, start in adapter.starts]
    assert starts == pytest.approx(expected_starts, abs=1e-6)
    assert most_starts_in_any_window(starts, pace.interval_seconds) <= pace.requests


def test_a_pace_retuned_while_calls_wait_paces_them_at_the_new_rate() -> None:
    async def scenario() -> PacedAdapter:
        pacer = Pacer(Pace(requests=2, interval_seconds=1.0), clock=EventLoopClock())
        adapter = PacedAdapter(pacer, [0.0] * 4)
        first = asyncio.ensure_future(adapter.search(query(0)))
        await asyncio.sleep(0)
        pacer.retune(Pace(requests=1, interval_seconds=2.0))
        await asyncio.gather(first, *(adapter.search(query(number)) for number in range(1, 4)))
        return adapter

    adapter = run_in_virtual_time(scenario())
    assert [start for _, start in adapter.starts] == pytest.approx([0.0, 2.0, 4.0, 6.0], abs=1e-6)


def test_a_call_whose_turn_would_come_after_its_deadline_is_not_asked_at_that_deadline() -> None:
    async def scenario() -> tuple[list[ProviderResponse], list[float], PacedAdapter]:
        adapter = PacedAdapter(
            Pacer(Pace(requests=1, interval_seconds=1.0), clock=EventLoopClock()), [0.0] * 4
        )
        adapter.within = 2.5
        ended: list[float] = []

        async def ask(number: int) -> ProviderResponse:
            response = await adapter.search(query(number))
            ended.append(now_seconds())
            return response

        responses = await asyncio.gather(*(ask(number) for number in range(4)))
        return list(responses), ended, adapter

    responses, ended, adapter = run_in_virtual_time(scenario())
    assert [start for _, start in adapter.starts] == pytest.approx([0.0, 1.0, 2.0], abs=1e-6)
    assert [response.error for response in responses] == [None, None, None, NOT_ASKED]
    assert ended == pytest.approx([0.0, 1.0, 2.0, 2.5], abs=1e-6)


@pytest.mark.parametrize(
    ("requests", "interval_seconds", "burst", "concurrency"),
    [(0, 1.0, 1, None), (1, 0.0, 1, None), (2, 1.0, 0, None), (3, 1.0, 2, None), (1, 1.0, 1, 0)],
    ids=["no requests", "no interval", "no burst", "a burst that does not divide the rate", "no concurrency"],
)
def test_a_pace_refuses_values_that_would_break_its_rate(
    requests: int, interval_seconds: float, burst: int, concurrency: int | None
) -> None:
    with pytest.raises(ValueError):
        Pace(requests=requests, interval_seconds=interval_seconds, burst=burst, concurrency=concurrency)


# --------------------------------------------------------------------------------------------
# The wrapper: queued time is neither latency nor the timeout's
# --------------------------------------------------------------------------------------------

ONE_A_SECOND: Final = Pace(requests=1, interval_seconds=1.0, concurrency=1)
ONE_EVERY_TWO_SECONDS: Final = Pace(requests=1, interval_seconds=2.0, concurrency=1)


def test_time_queued_on_a_pace_is_not_the_calls_latency() -> None:
    """Released at 0, 1 and 2 s and each answered 0.2 s later: three latencies of 200 ms, not 200,
    1,200 and 2,200 ms."""

    async def scenario() -> ProviderHealth:
        provider, _ = wrapped(ONE_A_SECOND, [0.2, 0.2, 0.2])
        await asyncio.gather(*(provider.search(query(number)) for number in range(3)))
        return provider.health()

    health = run_in_virtual_time(scenario())
    assert (health.success_count, health.error_count, health.not_asked_count) == (3, 0, 0)
    assert health.p50_latency_ms == pytest.approx(200.0, abs=0.01)


def test_time_queued_on_a_pace_does_not_count_towards_the_timeout() -> None:
    """A 1 s timeout, one call every 2 s, each answered 0.5 s after its release: the third call is
    answered 4.5 s after it was made and has not timed out, because 4 of those seconds were queued."""

    async def scenario() -> tuple[ProviderHealth, list[ProviderResponse]]:
        provider, _ = wrapped(ONE_EVERY_TWO_SECONDS, [0.5, 0.5, 0.5], timeout_seconds=1.0)
        responses = await asyncio.gather(*(provider.search(query(number)) for number in range(3)))
        return provider.health(), list(responses)

    health, responses = run_in_virtual_time(scenario())
    assert [response.results[0].title for response in responses] == [
        query(number).query for number in range(3)
    ]
    assert (health.success_count, health.error_count, health.consecutive_failures) == (3, 0, 0)
    assert health.p50_latency_ms == pytest.approx(500.0, abs=0.01)


@pytest.mark.parametrize(
    ("queued_first", "timed_out_at"),
    [(False, 1.0), (True, 3.0)],
    ids=["a call never queued", "a call queued for 2 s"],
)
def test_a_sent_call_that_runs_slow_still_times_out_its_timeout_after_its_release(
    queued_first: bool, timed_out_at: float
) -> None:
    async def scenario() -> tuple[ProviderHealth, float]:
        work: list[Work] = [0.5, "hang"] if queued_first else ["hang"]
        provider, _ = wrapped(ONE_EVERY_TWO_SECONDS, work, timeout_seconds=1.0)
        first = asyncio.ensure_future(provider.search(query(0))) if queued_first else None
        await asyncio.sleep(0)
        with pytest.raises(ProviderTimedOut):
            await provider.search(query(1))
        raised_at = now_seconds()
        if first is not None:
            await first
        return provider.health(), raised_at

    health, raised_at = run_in_virtual_time(scenario())
    assert raised_at == pytest.approx(timed_out_at, abs=1e-6)
    assert (health.error_count, health.consecutive_failures) == (1, 1)
    assert health.last_error == "paced: no answer within 1s"
    expected_p50 = 750.0 if queued_first else 1000.0
    assert health.p50_latency_ms == pytest.approx(expected_p50, abs=0.01)


# --------------------------------------------------------------------------------------------
# The wrapper: a "not asked" answer is neither a failure nor a latency sample
# --------------------------------------------------------------------------------------------


def test_a_call_its_pace_answers_not_asked_is_neither_a_failure_nor_a_latency_sample() -> None:
    """One answer in 0.2 s; then a failure after 0.4 s while a second call waits and is refused at
    its 0.5 s deadline. The refused call is counted apart: it does not reset the failure count, and
    the median is of 200 and 400 ms only, not of 200, 400 and its 500 ms wait."""

    async def scenario() -> tuple[ProviderHealth, ProviderResponse]:
        provider, _ = wrapped(ONE_A_SECOND, [0.2, "fail"], within=0.5)
        await provider.search(query(0))
        await asyncio.sleep(1.0)
        failed, not_asked = await asyncio.gather(
            provider.search(query(1)), provider.search(query(2)), return_exceptions=True
        )
        assert isinstance(failed, ProviderUnavailable)
        assert isinstance(not_asked, ProviderResponse)
        return provider.health(), not_asked

    health, not_asked = run_in_virtual_time(scenario())
    assert (not_asked.partial, not_asked.error, not_asked.results) == (True, NOT_ASKED, ())
    assert (health.success_count, health.error_count, health.not_asked_count) == (1, 1, 1)
    assert (health.consecutive_failures, health.last_error) == (1, "paced: HTTP 503")
    assert health.p50_latency_ms == pytest.approx(300.0, abs=0.01)


def test_a_probe_its_pace_answers_not_asked_decides_nothing_and_frees_the_probe() -> None:
    """A threshold of one: the first call fails and opens the breaker. After the cool-down the probe
    waits behind a call the pace has just released elsewhere and is refused; the breaker stays half
    open, and the next call is the probe that closes it."""

    async def scenario() -> tuple[ProviderHealth, list[BreakerState]]:
        clock = EventLoopClock()
        pacer = Pacer(ONE_A_SECOND, clock=clock)
        adapter = PacedAdapter(pacer, ["fail", 0.2], within=0.5)
        policy = ResiliencePolicy(timeout_seconds=5.0, failure_threshold=1, cooldown_seconds=60.0)
        provider = ResilientProvider(adapter, policy, clock=clock)
        states: list[BreakerState] = []
        with pytest.raises(ProviderUnavailable):
            await provider.search(query(0))
        states.append(provider.health().state)
        await asyncio.sleep(60.0)
        async with pacer.turn(within=30.0):
            refused = await provider.search(query(1))
        assert refused.partial
        states.append(provider.health().state)
        await asyncio.sleep(1.0)
        await provider.search(query(2))
        health = provider.health()
        states.append(health.state)
        return health, states

    health, states = run_in_virtual_time(scenario())
    assert states == [BreakerState.OPEN, BreakerState.HALF_OPEN, BreakerState.CLOSED]
    assert (health.success_count, health.error_count, health.not_asked_count) == (1, 1, 1)


# --------------------------------------------------------------------------------------------
# The wrapper: queries asked at once, each on its own turn
# --------------------------------------------------------------------------------------------


def test_queries_asked_at_once_count_as_queued_while_any_of_them_waits_for_its_turn() -> None:
    """Three queries in one call at one a second: released at 0, 1 and 2 s and each answered 0.2 s
    later. The second and third wait together from 0 to 1 s, so the call was queued from 0 to 2 s
    once, not for 1 + 2 s; its latency is 200 ms, and its 0.5 s timeout counted only those 200 ms."""

    async def scenario() -> ProviderHealth:
        clock = EventLoopClock()
        adapter = PacedMultiQueryAdapter(Pacer(ONE_A_SECOND, clock=clock), [0.2, 0.2, 0.2])
        policy = ResiliencePolicy(timeout_seconds=0.5)
        provider = ResilientMultiQueryProvider(adapter, policy, clock=clock)
        responses = await provider.search_each((query(0), query(1), query(2)))
        assert [response.partial for response in responses] == [False, False, False]
        return provider.health()

    health = run_in_virtual_time(scenario())
    assert (health.success_count, health.error_count, health.not_asked_count) == (1, 0, 0)
    assert health.p50_latency_ms == pytest.approx(200.0, abs=0.01)


def test_queries_asked_at_once_of_which_one_was_sent_are_an_answer_not_a_not_asked() -> None:
    """Two queries in one call, the second refused at its 0.5 s deadline: the provider answered the
    first, so the call is a success, not a "not asked"."""

    async def scenario() -> tuple[ProviderHealth, list[bool]]:
        clock = EventLoopClock()
        adapter = PacedMultiQueryAdapter(Pacer(ONE_A_SECOND, clock=clock), [0.2], within=0.5)
        provider = ResilientMultiQueryProvider(adapter, ResiliencePolicy(timeout_seconds=5.0), clock=clock)
        responses = await provider.search_each((query(0), query(1)))
        return provider.health(), [response.partial for response in responses]

    health, partial = run_in_virtual_time(scenario())
    assert partial == [False, True]
    assert (health.success_count, health.error_count, health.not_asked_count) == (1, 0, 0)


def test_a_turn_taken_outside_the_wrapper_reports_to_nobody() -> None:
    async def scenario() -> datetime:
        clock = EventLoopClock()
        pacer = Pacer(ONE_A_SECOND, clock=clock)
        async with pacer.turn(within=1.0) as sent:
            assert sent
        return clock.now()

    assert run_in_virtual_time(scenario()) == FAKE_EPOCH


# --------------------------------------------------------------------------------------------
# The turn: a queued call checks the breaker and the hold again when its turn comes (v1-e07-t22)
# --------------------------------------------------------------------------------------------


async def ask_all(provider: ResilientProvider, count: int) -> list[tuple[str, float]]:
    """`count` queries at once; for each, how it ended (an answer, or the error's type) and when."""

    async def one(number: int) -> tuple[str, float]:
        try:
            response = await provider.search(query(number))
        except ProviderError as error:
            return type(error).__name__, now_seconds()
        return ("not asked" if response.partial else "answer"), now_seconds()

    return list(await asyncio.gather(*(one(number) for number in range(count))))


def test_queued_calls_whose_turn_comes_inside_a_hold_are_skipped_and_never_sent() -> None:
    """Written by hand. Four queries at once at one a second. The first is sent at 0 s and refused at
    0.25 s with a 429 and no Retry-After: held 2 s lengthened by a quarter (draw 0.5), until 2.75 s.
    The second's turn comes at 1 s, inside the hold, so it is refused there and sends nothing; it
    takes no slot, so the third and fourth get their turns at once and are refused at 1 s too. Each
    refusal is the hold's answer, ProviderRateLimited with the 1.75 s left, and a skip, not a failure.
    The 0.5 s timeout counts none of the second spent queued. A fifth query asked when the hold ends
    is sent at once and answered 0.25 s later."""

    async def scenario() -> tuple[list[tuple[str, float]], list[float | None], ProviderHealth, PacedAdapter]:
        provider, adapter = wrapped(ONE_A_SECOND, ["429", 0.25], timeout_seconds=0.5, draw=0.5)
        retry_afters: list[float | None] = []

        async def remember(number: int) -> tuple[str, float]:
            try:
                await provider.search(query(number))
            except ProviderRateLimited as error:
                retry_afters.append(error.retry_after_seconds)
                return type(error).__name__, now_seconds()
            except ProviderError as error:
                return type(error).__name__, now_seconds()
            return "answer", now_seconds()

        ended = list(await asyncio.gather(*(remember(number) for number in range(4))))
        await asyncio.sleep(max(2.75 - now_seconds(), 0.0))
        ended.append(await remember(4))
        return ended, retry_afters, provider.health(), adapter

    ended, retry_afters, health, adapter = run_in_virtual_time(scenario())
    assert adapter.starts == [("query 0", 0.0), ("query 4", 2.75)]
    assert ended == [("ProviderRateLimited", 0.25)] + [("ProviderRateLimited", 1.0)] * 3 + [("answer", 3.0)]
    assert retry_afters == [None, 1.75, 1.75, 1.75]
    assert (health.success_count, health.error_count, health.skipped_count) == (1, 1, 3)
    assert (health.not_asked_count, health.consecutive_failures, health.state) == (0, 0, BreakerState.CLOSED)
    assert health.p50_latency_ms == pytest.approx(250.0, abs=0.01)


def test_queued_calls_whose_turn_comes_after_the_breaker_opened_are_skipped_and_never_sent() -> None:
    """Written by hand. Four queries at once at one a second, a threshold of two. The first two are
    sent at 0 and 1 s and fail 0.4 s later, so the breaker opens at 1.4 s. The third's turn comes at
    2 s: refused as the open breaker refuses a call, and the fourth at once after it. Neither is sent,
    and both are skips, not failures."""

    async def scenario() -> tuple[list[tuple[str, float]], list[object], ProviderHealth, PacedAdapter]:
        provider, adapter = wrapped(ONE_A_SECOND, ["fail", "fail"], threshold=2)
        retry_ats: list[object] = []

        async def remember(number: int) -> tuple[str, float]:
            try:
                await provider.search(query(number))
            except ProviderCircuitOpen as error:
                retry_ats.append(error.retry_at)
                return type(error).__name__, now_seconds()
            except ProviderError as error:
                return type(error).__name__, now_seconds()
            return "answer", now_seconds()

        ended = list(await asyncio.gather(*(remember(number) for number in range(4))))
        return ended, retry_ats, provider.health(), adapter

    ended, retry_ats, health, adapter = run_in_virtual_time(scenario())
    assert [start for _, start in adapter.starts] == [0.0, 1.0]
    assert ended == [
        ("ProviderUnavailable", 0.4),
        ("ProviderUnavailable", 1.4),
        ("ProviderCircuitOpen", 2.0),
        ("ProviderCircuitOpen", 2.0),
    ]
    opened_at = FAKE_EPOCH + timedelta(seconds=1.4)
    assert retry_ats == [opened_at + timedelta(seconds=60)] * 2
    assert (health.error_count, health.skipped_count, health.success_count) == (2, 2, 0)
    assert health.state is BreakerState.OPEN


def test_a_queued_call_whose_turn_comes_once_the_breaker_half_opened_is_sent_as_its_probe() -> None:
    """Written by hand. Three queries at once at one a second, a threshold of one and a 0.5 s
    cool-down. The first is sent at 0 s and fails at 0.4 s, opening the breaker until 0.9 s. The
    second's turn comes at 1 s, with the breaker half-open and no probe out: it is admitted again,
    as the probe, sent, and its answer at 1.2 s closes the breaker. The third is sent at 2 s on a
    closed breaker."""

    async def scenario() -> tuple[list[tuple[str, float]], ProviderHealth, PacedAdapter]:
        provider, adapter = wrapped(ONE_A_SECOND, ["fail", 0.2, 0.2], threshold=1, cooldown_seconds=0.5)
        ended = await ask_all(provider, 3)
        return ended, provider.health(), adapter

    ended, health, adapter = run_in_virtual_time(scenario())
    assert [start for _, start in adapter.starts] == [0.0, 1.0, 2.0]
    assert ended == [("ProviderUnavailable", 0.4), ("answer", 1.2), ("answer", 2.2)]
    assert health.state is BreakerState.CLOSED
    assert (health.error_count, health.success_count, health.skipped_count) == (1, 2, 0)


@dataclass
class RefusingListener:
    """A listener that refuses the first `refusals` turns that come, and records what it hears."""

    refusals: int
    heard: list[str] = field(default_factory=list[str])

    def waiting(self) -> None:
        self.heard.append("waiting")

    def waited(self, outcome: TurnOutcome) -> None:
        self.heard.append(f"waited {outcome.value}")

    def turn_came(self) -> None:
        self.heard.append(f"turn came at {now_seconds():g}")
        if self.refusals > 0:
            self.refusals -= 1
            raise ProviderRateLimited(NAME, "held at the turn")


def test_a_turn_its_listener_refuses_raises_the_refusal_takes_no_start_and_frees_the_next_turn() -> None:
    """Written by hand. One a second: a call released at 0 s holds the pace. The next waits for 1 s,
    and its listener refuses it there: entering the turn raises the listener's refusal, the block's
    body never runs, and the listener hears it ended `refused`. It took no start, so a third call
    asked at that instant starts at once, at 1 s, not at 2 s."""

    async def scenario() -> tuple[list[str], list[float], list[str]]:
        clock = EventLoopClock()
        pacer = Pacer(ONE_A_SECOND, clock=clock)
        listener = RefusingListener(refusals=1)
        bodies: list[str] = []
        starts: list[float] = []
        async with pacer.turn(within=30.0) as sent:
            assert sent
            starts.append(now_seconds())
        with listening(listener), pytest.raises(ProviderRateLimited, match="held at the turn"):
            async with pacer.turn(within=30.0):
                bodies.append("the refused call's body ran")
        async with pacer.turn(within=30.0) as sent:
            assert sent
            starts.append(now_seconds())
        return listener.heard, starts, bodies

    heard, starts, bodies = run_in_virtual_time(scenario())
    assert heard == ["waiting", "turn came at 1", "waited refused"]
    assert starts == [0.0, 1.0]
    assert bodies == []
