"""A provider's own pace, for any adapter that needs one, and how the wrapper hears of it (v1-e07-t10).

Some providers limit how fast they may be asked, and a federated search sends every query at once,
so an adapter for such a provider queues its own requests: Crossref since v1-e07-t03, Semantic
Scholar next (v1-e07-t04). :class:`Pacer` is that queue, shared by every adapter that configures
one with its own :class:`Pace`, read from its own settings or constants.

**The pace.** `requests` per `interval_seconds`, with `burst` of them allowed back to back and no
more than `concurrency` in flight. Exactly: no more than `burst` calls start in any window of
`burst × interval_seconds / requests` seconds. With the default burst of one, starts are evenly
spaced, `interval_seconds / requests` apart, which is Crossref's pace. `burst` divides `requests`,
so no window of `interval_seconds` ever holds more than `requests` starts. The pace is read again on
every look, so :meth:`Pacer.retune` (Crossref tightening itself to the limits an answer advertises)
applies to every call still waiting.

**The turn.** Calls are released first come, first served. Each call says how long after it arrived
it is still worth sending (`within`, read again on every look, since Crossref's moves as answers
arrive). A call whose turn has not come by then is not sent at all: the adapter answers it "not
asked". Waiting in line holds no slot, so a call cancelled while it waits gives up only its turn;
a released call holds its slot until its `async with` block ends, however it ends.

**The wrapper hears of it.** For every call it makes,
:class:`~debate_core.integrations.discovery.resilience.ResilientProvider` installs a
:class:`PaceListener` with :func:`listening`, a context variable, so no port changes and an adapter
that does not pace is untouched. The pacer tells that listener when the call starts waiting and how
its wait ended (:class:`TurnOutcome`). The wrapper then counts the time queued neither towards the
call's timeout nor towards its latency, and a call its pace answered "not asked" as neither a
failure nor a latency sample.

Every time is read from the injected
:class:`~debate_core.application.ports.providers.Clock` and every wait is the injected sleep, so a
test drives the pace on virtual time.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable, Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from types import TracebackType
from typing import Protocol

from debate_core.application.ports.providers import Clock

__all__ = [
    "Pace",
    "PaceListener",
    "Pacer",
    "Sleep",
    "Turn",
    "TurnOutcome",
    "listening",
]

type Sleep = Callable[[float], Awaitable[None]]
"""How a pacer waits: `asyncio.sleep` in a real run, a test's virtual time in a test."""


@dataclass(frozen=True, slots=True)
class Pace:
    """How fast one provider may be asked: `requests` per `interval_seconds`, `burst` back to back."""

    requests: int
    """Starts allowed per `interval_seconds`."""

    interval_seconds: float
    """The window `requests` is counted over."""

    burst: int = 1
    """Starts allowed back to back; one spreads them evenly. Divides `requests`."""

    concurrency: int | None = None
    """Calls allowed in flight at once; `None` for no limit beyond the rate."""

    def __post_init__(self) -> None:
        if self.requests < 1:
            raise ValueError(f"requests must be at least 1, got {self.requests}")
        if self.interval_seconds <= 0:
            raise ValueError(f"interval_seconds must be positive, got {self.interval_seconds}")
        if self.burst < 1 or self.requests % self.burst != 0:
            raise ValueError(
                f"burst must be at least 1 and divide requests, got {self.burst} of {self.requests}"
            )
        if self.concurrency is not None and self.concurrency < 1:
            raise ValueError(f"concurrency must be at least 1, got {self.concurrency}")

    @property
    def spacing(self) -> timedelta:
        """The time one start uses up: `interval_seconds / requests`."""
        return timedelta(seconds=self.interval_seconds / self.requests)


class TurnOutcome(StrEnum):
    """How a call's wait for its turn ended."""

    RELEASED = "released"
    """Its turn came: it may be sent now."""

    NOT_ASKED = "not_asked"
    """Its turn would have come too late, so it is never sent."""

    CANCELLED = "cancelled"
    """It was cancelled while it waited."""


class PaceListener(Protocol):
    """What a pacer tells the code that made a call (the wrapper) about that call's wait."""

    def waiting(self) -> None:
        """The call joined its pace's queue."""
        ...

    def waited(self, outcome: TurnOutcome) -> None:
        """The call left the queue, and how."""
        ...


_LISTENER: ContextVar[PaceListener | None] = ContextVar("debate_pace_listener", default=None)


@contextmanager
def listening(listener: PaceListener) -> Generator[None]:
    """Every pace turn taken inside this block, in this task or one it starts, reports to `listener`."""
    token = _LISTENER.set(listener)
    try:
        yield
    finally:
        _LISTENER.reset(token)


class Pacer:
    """Releases calls first come, first served, at a :class:`Pace`, or tells one it was too late.

    One per adapter, so one per process in the CLI.
    """

    def __init__(self, pace: Pace, *, clock: Clock, sleep: Sleep = asyncio.sleep) -> None:
        self._pace = pace
        self._clock = clock
        self._sleep = sleep
        self._line = asyncio.Lock()
        self._in_flight = 0
        self._released = asyncio.Event()
        self._starts: deque[datetime] = deque()
        self._history = pace.burst

    @property
    def pace(self) -> Pace:
        """The pace kept now."""
        return self._pace

    def retune(self, pace: Pace) -> None:
        """Keep `pace` from now on, for every call still waiting too."""
        self._pace = pace
        self._history = max(self._history, pace.burst)

    def turn(self, *, within: float | Callable[[], float]) -> Turn:
        """This call's turn: `async with pacer.turn(within=...) as sent:`, `sent` False when too late.

        `within` is how many seconds after the call arrived it may still be sent, or a function
        giving that, read on every look.
        """
        return Turn(lambda: self._wait(within), self._finish)

    async def _wait(self, within: float | Callable[[], float]) -> bool:
        arrived = self._clock.now()
        async with self._line:
            while True:
                now = self._clock.now()
                seconds = within() if callable(within) else within
                deadline = arrived + timedelta(seconds=seconds)
                if now >= deadline:
                    return False
                ready_at = self._ready_at(now)
                concurrency = self._pace.concurrency
                free = concurrency is None or self._in_flight < concurrency
                if free and now >= ready_at:
                    self._start(now)
                    return True
                if free:
                    await self._sleep((min(ready_at, deadline) - now).total_seconds())
                else:
                    await self._until_released_or((deadline - now).total_seconds())

    def _ready_at(self, now: datetime) -> datetime:
        """When the next call may start: `burst` starts ago plus `burst` spacings, or now."""
        burst = self._pace.burst
        if len(self._starts) < burst:
            return now
        return self._starts[-burst] + self._pace.spacing * burst

    def _start(self, now: datetime) -> None:
        self._in_flight += 1
        self._starts.append(now)
        while len(self._starts) > self._history:
            self._starts.popleft()

    def _finish(self) -> None:
        self._in_flight -= 1
        released, self._released = self._released, asyncio.Event()
        released.set()

    async def _until_released_or(self, seconds: float) -> None:
        waiting = (
            asyncio.ensure_future(self._released.wait()),
            asyncio.ensure_future(self._sleep(seconds)),
        )
        try:
            await asyncio.wait(waiting, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in waiting:
                task.cancel()


class Turn:
    """One call's turn on a :class:`Pacer`, as an async context manager that yields whether to send it."""

    def __init__(self, wait: Callable[[], Awaitable[bool]], finish: Callable[[], None]) -> None:
        self._wait = wait
        self._finish = finish
        self._sent = False

    async def __aenter__(self) -> bool:
        listener = _LISTENER.get()
        if listener is not None:
            listener.waiting()
        try:
            self._sent = await self._wait()
        except BaseException:
            if listener is not None:
                listener.waited(TurnOutcome.CANCELLED)
            raise
        if listener is not None:
            listener.waited(TurnOutcome.RELEASED if self._sent else TurnOutcome.NOT_ASKED)
        return self._sent

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._sent:
            self._sent = False
            self._finish()
