"""A long command's log lines as it goes: each step's start and end, and the parse's progress.

`v1-e40-t32` wrote these for `caselist backfile-import`, whose result is one line when it ends, so a
task killed part-way left nothing to read. `v1-e40-t43` moved them here, unchanged, so that the
weekly run (`caselist pull`), whose result is also one line at its end, writes the same lines through
the same code: a reader of one command's log reads the other's.

A line holds a step's name, its seconds, its counts and the memory high-water marks so far
(:mod:`~debate_core.application.caselist.memory_high_water`), and nothing else: **counts only**. No
path, school, team code, tournament, caselist or file name is ever put in one. A step's name is a
word this code chose, never one read from a file.

How a line is written (a JSON object on stderr, or a sentence) is the CLI's.
"""

from __future__ import annotations

from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final, Protocol

from debate_core.application.caselist.memory_high_water import MemoryHighWater

__all__ = [
    "PARSE_PROGRESS_INTERVAL_SECONDS",
    "OpenStep",
    "ParseProgress",
    "SourceProgress",
    "StepEvent",
    "StepLine",
    "logged_step",
    "say_nothing",
]

PARSE_PROGRESS_INTERVAL_SECONDS: Final = 300.0
"""How often the parse says how far it has got: five minutes. The parse is most of an import's 1.5 to
2.5 hours, so this is 18 to 30 lines, a dozen points of the memory's climb before a kill like the one
at 71 minutes, and six between two of the runbook's half-hourly looks at the task."""


class StepEvent(StrEnum):
    """What a :class:`StepLine` says happened."""

    STARTED = "step_started"
    ENDED = "step_ended"
    FAILED = "step_failed"
    """The step raised: a refusal, a changed bundle, a SIGTERM. A kill for memory leaves no line."""
    PARSE_PROGRESS = "parse_progress"


@dataclass(frozen=True, slots=True)
class StepLine:
    """One line of a command's log as it goes. A step's name and numbers: never a path or a name."""

    event: StepEvent
    step: str
    seconds: float | None = None
    """Since the step started; `None` on its start line."""
    counts: Mapping[str, int] = field(default_factory=dict[str, int])
    memory: MemoryHighWater | None = None
    """On an end, failure or progress line."""
    outcome: str | None = None
    """How the step ended, where the command records that apart from raising (`v1-e40-t43`): a weekly
    run's stage that fails is recorded as failed and the run goes on, so its end line says `failed`.
    One of :class:`~debate_core.application.caselist_sync.StageOutcome`'s values, or `None` where the
    command records none, as a backfile import's steps do."""


def say_nothing(line: StepLine) -> None:
    """Where a command's lines go when nobody asked for them."""
    del line


class SourceProgress(Protocol):
    """What a parse tells as it goes: how many sources it has, then how many are done after each one."""

    def start(self, total: int) -> None: ...

    def __call__(self, done: int) -> None: ...


class ParseProgress:
    """The parse's progress lines: one once it knows how many sources it has, then one each time a
    source finishes :data:`PARSE_PROGRESS_INTERVAL_SECONDS` or more after the last line, and one when
    the last is done, so that a kill in the aggregates' rebuild shows every source parsed.

    `also` are counts every line of this parse carries besides its sources: the weekly run, which
    parses one caselist after another, says how many caselists are done and left (`v1-e40-t43`).
    """

    def __init__(
        self,
        emit: Callable[[StepLine], None],
        *,
        monotonic: Callable[[], float],
        memory: Callable[[], MemoryHighWater],
        interval: float,
        also: Mapping[str, int] | None = None,
    ) -> None:
        self._emit = emit
        self._monotonic = monotonic
        self._memory = memory
        self._interval = interval
        self._also = dict(also or {})
        self._started = self._last = monotonic()
        self._total = 0

    def start(self, total: int) -> None:
        self._total = total
        self._line(0, self._monotonic())

    def __call__(self, done: int) -> None:
        now = self._monotonic()
        if done < self._total and now - self._last < self._interval:
            return
        self._line(done, now)

    def _line(self, done: int, now: float) -> None:
        self._last = now
        self._emit(
            StepLine(
                StepEvent.PARSE_PROGRESS,
                "parse",
                seconds=now - self._started,
                counts={"sources_done": done, "sources_left": self._total - done, **self._also},
                memory=self._memory(),
            )
        )


@dataclass(slots=True)
class OpenStep:
    """A step under way: the body of :func:`logged_step` fills its counts, which its end line carries."""

    counts: dict[str, int] = field(default_factory=dict[str, int])
    outcome: str | None = None
    seconds: float | None = None
    """Set as the step ends or fails."""


@contextmanager
def logged_step(
    name: str,
    emit: Callable[[StepLine], None],
    *,
    monotonic: Callable[[], float],
    memory: Callable[[], MemoryHighWater],
) -> Generator[OpenStep]:
    """Tell `emit` of step `name`'s start, then of its end, or of its failure when the body raises.

    The end and failure lines carry the seconds since the start, the counts the body filled in, and
    the memory high-water marks read as it ended. Whatever the body raises is raised again.
    """
    emit(StepLine(StepEvent.STARTED, name))
    step = OpenStep()
    started = monotonic()
    try:
        yield step
    except BaseException:
        step.seconds = monotonic() - started
        emit(StepLine(StepEvent.FAILED, name, step.seconds, step.counts, memory(), step.outcome))
        raise
    step.seconds = monotonic() - started
    emit(StepLine(StepEvent.ENDED, name, step.seconds, step.counts, memory(), step.outcome))
