"""Every command that writes to an evidence bucket holds the bucket's run lock while it writes (`v1-e40-t04`).

ADR-0020 (4), "Who takes it", and the PM's rulings on the plan (2026-10-24): `caselist publish`,
`caselist parse --publish` and `--publish-only`, `caselist remove --execute`, `caselist
unsuppress --execute`, `caselist retire --bucket --execute` (and `--restore`), `landscape report
--publish`, `tub index publish` and `store sync --push --apply`. `caselist pull` and `caselist
seed-run-state` take it inside their own services, because what they do around it is theirs. A dry
run takes nothing.

What the lock is, and what local mode does instead, is
:class:`~debate_core.application.caselist.run_lock.BucketWriteGuard`'s. What is here is the part
that belongs to a process: SIGTERM. While a command holds the lock, SIGTERM (the container's
deadline, `ecs stop-task`) raises
:class:`~debate_core.application.caselist.run_lock.RunTerminated` in the main thread instead of
killing the process outright, so the guard's `finally` releases the lock before the process exits.
"""

from __future__ import annotations

import asyncio
import signal
from collections.abc import Callable, Coroutine, Iterator
from contextlib import contextmanager
from types import FrameType
from typing import Any

from debate_cli.context import CliContext
from debate_core.application.caselist.run_lock import RunTerminated

__all__ = ["holding_the_bucket_lock", "run_holding_the_bucket_lock", "terminated_on_sigterm"]


@contextmanager
def holding_the_bucket_lock(cli: CliContext, command: str) -> Iterator[None]:
    """Hold what `command` needs to write to this environment's bucket, and stop cleanly on SIGTERM."""
    with terminated_on_sigterm(), cli.services.bucket_write_guard().held(command):
        yield


def run_holding_the_bucket_lock[T](
    cli: CliContext, command: str, work: Callable[[], Coroutine[Any, Any, T]]
) -> T:
    """Run the coroutine `work` builds while holding the lock (:func:`holding_the_bucket_lock`)."""
    with holding_the_bucket_lock(cli, command):
        return asyncio.run(work())


@contextmanager
def terminated_on_sigterm() -> Iterator[None]:
    """For the block, SIGTERM raises :class:`RunTerminated` in the main thread. Restored after.

    Only the main thread may set a handler; anywhere else the block runs as it would without one.
    """

    def terminate(signum: int, frame: FrameType | None) -> None:
        del signum, frame
        raise RunTerminated

    try:
        previous = signal.signal(signal.SIGTERM, terminate)
    except ValueError:  # not the main thread
        yield
        return
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)
