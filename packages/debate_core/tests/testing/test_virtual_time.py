"""The virtual-time loop: timers fire in order, at their virtual instant, and nothing waits for real."""

from __future__ import annotations

import asyncio
import time
from datetime import timedelta

import pytest

from debate_core.testing.fakes.clock_and_ids import FAKE_EPOCH
from debate_core.testing.virtual_time import (
    EventLoopClock,
    VirtualTimeDeadlock,
    run_in_virtual_time,
)

#: The most real time any test here may take. A real hour's sleep would blow it by six orders.
REAL_TIME_BUDGET_SECONDS = 0.1


def test_an_hour_of_sleep_passes_instantly_and_is_seen_by_the_loop_clock() -> None:
    async def sleep_an_hour() -> float:
        await asyncio.sleep(3600)
        return asyncio.get_running_loop().time()

    started = time.perf_counter()
    elapsed = run_in_virtual_time(sleep_an_hour())

    assert elapsed == 3600.0
    assert time.perf_counter() - started < REAL_TIME_BUDGET_SECONDS


def test_concurrent_sleeps_end_at_the_longest_not_the_sum() -> None:
    finished: list[tuple[str, float]] = []

    async def sleeper(name: str, seconds: float) -> None:
        await asyncio.sleep(seconds)
        finished.append((name, asyncio.get_running_loop().time()))

    async def three_at_once() -> float:
        async with asyncio.TaskGroup() as group:
            group.create_task(sleeper("five", 5))
            group.create_task(sleeper("three", 3))
            group.create_task(sleeper("four", 4))
        return asyncio.get_running_loop().time()

    assert run_in_virtual_time(three_at_once()) == 5.0
    assert finished == [("three", 3.0), ("four", 4.0), ("five", 5.0)]


def test_asyncio_timeout_fires_at_its_virtual_deadline() -> None:
    async def cut_off() -> float:
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(8):
                await asyncio.sleep(60)
        return asyncio.get_running_loop().time()

    assert run_in_virtual_time(cut_off()) == 8.0


def test_the_clock_port_reads_the_loop_clock_from_its_start() -> None:
    clock = EventLoopClock()

    async def read_twice() -> tuple[object, object]:
        before = clock.now()
        await asyncio.sleep(2.5)
        return before, clock.now()

    before, after = run_in_virtual_time(read_twice())

    assert before == FAKE_EPOCH
    assert after == FAKE_EPOCH + timedelta(seconds=2.5)


def test_waiting_on_nothing_raises_instead_of_hanging() -> None:
    async def wait_forever() -> None:
        await asyncio.get_running_loop().create_future()

    started = time.perf_counter()
    with pytest.raises(VirtualTimeDeadlock):
        run_in_virtual_time(wait_forever())
    assert time.perf_counter() - started < REAL_TIME_BUDGET_SECONDS
