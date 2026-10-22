"""An event loop whose clock jumps instead of waiting, for tests about deadlines and concurrency.

A federated search gives its providers a few seconds each and itself an overall deadline, and the
claims worth testing are about time: three providers that take 3, 4 and 5 seconds finish in 5, not
12; a provider still running at the deadline is cut off at the deadline. Proving that with real
sleeps would cost the suite seconds per test, and proving it with tiny sleeps would make the
assertions about scheduling noise.

:class:`VirtualTimeEventLoop` is an ordinary asyncio selector loop with one change: when it has
nothing to do but wait for the next timer, it moves its clock to that timer instead of sleeping.
Everything that reads the loop's clock — `asyncio.sleep`, `asyncio.timeout`, `loop.call_later` —
therefore sees the time pass, and none of it takes wall-clock time. Tasks still interleave exactly
as they would on a real loop, because the loop runs the same scheduler; only the waiting is gone.

:class:`EventLoopClock` is the :class:`~debate_core.application.ports.providers.Clock` port read
from that same loop clock, so a service's own timestamps and elapsed times agree with the
deadlines asyncio enforces. :func:`run_in_virtual_time` runs one coroutine on a fresh loop.

A loop with nothing scheduled and nothing ready would block forever on a real selector. Here that
is a deadlock in the test, so it raises :class:`VirtualTimeDeadlock` rather than hanging the suite.
"""

from __future__ import annotations

import asyncio
import selectors
from collections.abc import Coroutine
from datetime import datetime, timedelta
from typing import Any

from debate_core.testing.fakes import FAKE_EPOCH

__all__ = [
    "EventLoopClock",
    "VirtualTimeDeadlock",
    "VirtualTimeEventLoop",
    "run_in_virtual_time",
]


class VirtualTimeDeadlock(RuntimeError):
    """The loop had no timer to jump to and nothing ready to run: the test would hang forever."""


class _JumpingSelector(selectors.DefaultSelector):
    """A real selector that never blocks: it polls, and reports the wait it skipped to the loop."""

    def __init__(self, loop: VirtualTimeEventLoop) -> None:
        super().__init__()
        self._loop = loop

    def select(self, timeout: float | None = None) -> list[tuple[selectors.SelectorKey, int]]:
        ready = super().select(0)
        if ready:
            return ready
        if timeout is None:
            raise VirtualTimeDeadlock(
                "the event loop is waiting with no timer pending and nothing ready to run"
            )
        self._loop.advance(timeout)
        return ready


class VirtualTimeEventLoop(asyncio.SelectorEventLoop):
    """A selector loop whose `time()` starts at zero and moves only when the loop would wait."""

    def __init__(self) -> None:
        self._virtual_now = 0.0
        super().__init__(_JumpingSelector(self))

    def time(self) -> float:
        """Seconds of virtual time since the loop was created."""
        return self._virtual_now

    def advance(self, seconds: float) -> None:
        """Move the clock forward; the selector calls this instead of sleeping."""
        if seconds > 0:
            self._virtual_now += seconds


class EventLoopClock:
    """The `Clock` port, read from the running event loop's clock.

    `now()` is `start` plus the loop's `time()`. On a :class:`VirtualTimeEventLoop` that is
    `start` plus the virtual seconds elapsed, so the instants a service records line up with the
    timers asyncio fires. It must be read from inside a running loop.
    """

    def __init__(self, start: datetime = FAKE_EPOCH) -> None:
        self._start = start

    def now(self) -> datetime:
        return self._start + timedelta(seconds=asyncio.get_running_loop().time())


def run_in_virtual_time[ResultT](main: Coroutine[Any, Any, ResultT]) -> ResultT:
    """Run `main` to completion on a new :class:`VirtualTimeEventLoop` and return its result."""
    with asyncio.Runner(loop_factory=VirtualTimeEventLoop) as runner:
        return runner.run(main)
