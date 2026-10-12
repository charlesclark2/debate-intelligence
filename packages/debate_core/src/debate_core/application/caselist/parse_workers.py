"""Running the parser over many sources: in this process, or in a bounded pool with a time limit.

:class:`~debate_core.application.ports.debate_files.DebateFileParser` is synchronous and does no
I/O, so parsing a corpus in parallel means processes. :class:`ProcessPoolParseRunner` is what
`caselist parse` uses; :class:`InProcessParseRunner` is what most tests use, and what a run with one
worker could use, because it starts nothing.

## Why not `concurrent.futures.ProcessPoolExecutor`

A per-file time limit has to be able to stop the file. An executor's future can only be abandoned:
the worker stays busy with the stuck parse for the rest of the run, and enough of them stall the
pool. Here each worker is a process with a pipe of its own, so a parse that runs past its limit is
ended by terminating that worker and starting another, and the run goes on. A worker that dies
(out of memory, a crash in a C library) is replaced the same way.

## What a result is

The parser's own answer, a :class:`~debate_core.domain.debate_files.ParsedDocument` or a
:class:`~debate_core.domain.debate_files.ParseFailure`, or a :class:`WorkerFailure` for what the
parser could not report itself: the time limit, a dead worker, a parser that raised, or a source
that could not be read. Results arrive in completion order, not submission order.

## Sized for a laptop doing other things

The pool never starts more workers than there are sources, so a run that skips everything starts
none. How many it starts otherwise is the `parse.workers` setting, which defaults to the machine's
cores minus one, capped (`debate_core.application.settings.ParseSettings`). Sources are read one at
a time as a worker frees up, never all at once.
"""

from __future__ import annotations

import contextlib
import multiprocessing
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import date
from multiprocessing.connection import Connection, wait
from multiprocessing.process import BaseProcess
from typing import Final, Protocol

from debate_core.application.ports.debate_files import DebateFileParser
from debate_core.application.ports.parsed_store import PipelineFailureReason
from debate_core.domain.caselist import SourceDocument
from debate_core.domain.debate_files import ParsedDocument, ParseFailure

__all__ = [
    "InProcessParseRunner",
    "ParseJob",
    "ParseResult",
    "ParseRunner",
    "ProcessPoolParseRunner",
    "SourceLoadError",
    "WorkerFailure",
]

#: How long a stopping worker is given to exit before it is killed.
_SHUTDOWN_GRACE_SECONDS: Final = 2.0


@dataclass(frozen=True, slots=True)
class ParseJob:
    """One source to parse and what the parser needs to know about it besides its bytes.

    `source_path` is a disclosure path and names a school and a team; it goes to the parser, which
    puts it on each card's provenance, and nowhere else.
    """

    source: SourceDocument
    source_path: str
    snapshot: date
    camp: str | None

    def __repr__(self) -> str:
        return f"ParseJob(sha256={self.source.sha256[:12]}…, snapshot={self.snapshot.isoformat()})"


@dataclass(frozen=True, slots=True)
class WorkerFailure:
    """A source with no parser answer, and why. `detail` names a limit or a class, never text."""

    reason: PipelineFailureReason
    detail: str = ""


ParseResult = ParsedDocument | ParseFailure | WorkerFailure


class SourceLoadError(Exception):
    """A source's bytes could not be given to the parser. Raised by a job's loader."""

    def __init__(self, reason: PipelineFailureReason, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}")


#: A job and the function that reads its bytes, called only when a worker is ready for them.
LoadableJob = tuple[ParseJob, Callable[[], bytes]]


class ParseRunner(Protocol):
    """Parses jobs and yields each job with its result as it completes."""

    @property
    def workers(self) -> int:
        """How many parses run at once, for the run summary."""
        ...

    def run(
        self, parser: DebateFileParser, jobs: Iterable[LoadableJob]
    ) -> Iterator[tuple[ParseJob, ParseResult]]: ...


def parse_one(parser: DebateFileParser, job: ParseJob, content: bytes) -> ParseResult:
    """One parse, with a parser that raises turned into a failure that names only the class."""
    try:
        return parser.parse(
            content, job.source, source_path=job.source_path, snapshot=job.snapshot, camp=job.camp
        )
    except Exception as error:  # noqa: BLE001 - a parser bug is one source's failure, not the run's
        return WorkerFailure(PipelineFailureReason.PARSER_ERROR, type(error).__name__)


class InProcessParseRunner:
    """Parses each job here, one after another. No time limit: nothing here can stop a parse."""

    @property
    def workers(self) -> int:
        return 1

    def run(
        self, parser: DebateFileParser, jobs: Iterable[LoadableJob]
    ) -> Iterator[tuple[ParseJob, ParseResult]]:
        for job, load in jobs:
            try:
                content = load()
            except SourceLoadError as error:
                yield job, WorkerFailure(error.reason, error.detail)
                continue
            yield job, parse_one(parser, job, content)


@dataclass
class _Worker:
    process: BaseProcess
    connection: Connection
    job: ParseJob | None = None
    deadline: float = 0.0


class ProcessPoolParseRunner:
    """At most `workers` processes, each parse limited to `timeout_seconds`.

    Workers are spawned rather than forked, on every platform, so a worker starts from a clean
    interpreter whatever threads the parent holds; the parser is sent to each worker once, when it
    starts.
    """

    def __init__(
        self,
        *,
        workers: int,
        timeout_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if workers < 1:
            raise ValueError("a pool needs at least one worker")
        if timeout_seconds <= 0:
            raise ValueError("the per-file time limit must be positive")
        self._workers = workers
        self._timeout = timeout_seconds
        self._clock = clock
        self._context = multiprocessing.get_context("spawn")

    @property
    def workers(self) -> int:
        return self._workers

    def run(
        self, parser: DebateFileParser, jobs: Iterable[LoadableJob]
    ) -> Iterator[tuple[ParseJob, ParseResult]]:
        pending = iter(jobs)
        pool: list[_Worker] = []
        exhausted = False
        try:
            while True:
                for worker in [worker for worker in pool if worker.job is None]:
                    exhausted, loaded = self._next_loaded(pending, exhausted)
                    for failed in loaded.failures:
                        yield failed
                    if loaded.job is None:
                        break
                    self._dispatch(worker, loaded.job, loaded.content)
                while not exhausted and len(pool) < self._workers:
                    exhausted, loaded = self._next_loaded(pending, exhausted)
                    for failed in loaded.failures:
                        yield failed
                    if loaded.job is None:
                        break
                    worker = self._start(parser)
                    pool.append(worker)
                    self._dispatch(worker, loaded.job, loaded.content)
                busy = [worker for worker in pool if worker.job is not None]
                if not busy:
                    return
                yield from self._collect(parser, pool, busy)
        finally:
            self._stop(pool)

    # -- the loop's parts ---------------------------------------------------------------------

    def _next_loaded(self, pending: Iterator[LoadableJob], exhausted: bool) -> tuple[bool, _Loaded]:
        """The next job whose bytes could be read, and the failures of any that could not."""
        failures: list[tuple[ParseJob, ParseResult]] = []
        while not exhausted:
            try:
                job, load = next(pending)
            except StopIteration:
                return True, _Loaded(None, b"", failures)
            try:
                return False, _Loaded(job, load(), failures)
            except SourceLoadError as error:
                failures.append((job, WorkerFailure(error.reason, error.detail)))
        return True, _Loaded(None, b"", failures)

    def _dispatch(self, worker: _Worker, job: ParseJob, content: bytes) -> None:
        worker.connection.send((job, content))
        worker.job = job
        worker.deadline = self._clock() + self._timeout

    def _collect(
        self, parser: DebateFileParser, pool: list[_Worker], busy: list[_Worker]
    ) -> Iterator[tuple[ParseJob, ParseResult]]:
        """Wait for the first result or the nearest deadline, and settle every worker that is due."""
        remaining = max(0.0, min(worker.deadline for worker in busy) - self._clock())
        waitables: list[Connection | int] = [worker.connection for worker in busy]
        waitables += [worker.process.sentinel for worker in busy]
        ready = wait(waitables, timeout=remaining)
        now = self._clock()
        for worker in busy:
            job = worker.job
            assert job is not None
            if worker.connection in ready or worker.connection.poll():
                try:
                    result: ParseResult = worker.connection.recv()
                except (EOFError, OSError):
                    result = WorkerFailure(PipelineFailureReason.WORKER_CRASHED, "the worker exited")
                    self._replace(parser, pool, worker)
                worker.job = None
                yield job, result
            elif worker.process.sentinel in ready or not worker.process.is_alive():
                self._replace(parser, pool, worker)
                yield job, WorkerFailure(PipelineFailureReason.WORKER_CRASHED, "the worker exited")
            elif now >= worker.deadline:
                self._replace(parser, pool, worker)
                yield job, WorkerFailure(PipelineFailureReason.TIMEOUT, f"over {self._timeout:g} s")

    # -- workers ------------------------------------------------------------------------------

    def _start(self, parser: DebateFileParser) -> _Worker:
        ours, theirs = self._context.Pipe(duplex=True)
        process = self._context.Process(target=_work, args=(theirs, parser), daemon=True)
        process.start()
        theirs.close()
        return _Worker(process=process, connection=ours)

    def _replace(self, parser: DebateFileParser, pool: list[_Worker], worker: _Worker) -> None:
        """Stop a worker that timed out or died, and put a fresh one in its place."""
        _terminate(worker)
        fresh = self._start(parser)
        pool[pool.index(worker)] = fresh
        worker.job = None

    def _stop(self, pool: list[_Worker]) -> None:
        for worker in pool:
            with contextlib.suppress(OSError, ValueError):
                worker.connection.send(None)
        for worker in pool:
            worker.process.join(_SHUTDOWN_GRACE_SECONDS)
            _terminate(worker)


@dataclass(frozen=True, slots=True)
class _Loaded:
    job: ParseJob | None
    content: bytes
    failures: list[tuple[ParseJob, ParseResult]]


def _terminate(worker: _Worker) -> None:
    if worker.process.is_alive():
        worker.process.terminate()
        worker.process.join(_SHUTDOWN_GRACE_SECONDS)
    if worker.process.is_alive():  # pragma: no cover - terminate is enough on every platform we run
        worker.process.kill()
        worker.process.join(_SHUTDOWN_GRACE_SECONDS)
    worker.connection.close()


def _work(connection: Connection, parser: DebateFileParser) -> None:  # pragma: no cover - runs in a worker
    """A worker's whole life: parse what arrives until told to stop or the pipe closes."""
    while True:
        try:
            message = connection.recv()
        except (EOFError, OSError, KeyboardInterrupt):
            return
        if message is None:
            return
        job, content = message
        connection.send(parse_one(parser, job, content))
