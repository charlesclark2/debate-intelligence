"""One `caselist pull` in bucket mode: the lock, the restore, the saves, and a stop on SIGTERM (`v1-e40-t04`).

:func:`~debate_core.application.caselist_sync.run_pull` hands each run to a :class:`BucketRun`, which
does, in order:

1. **At the start**, inside the run monitor so that a refusal is recorded: in bucket mode, take the
   bucket's run lock (:class:`~debate_core.application.caselist.run_lock.BucketRunLock`), which
   refuses a bucket that holds no lock object, and start renewing it; then restore the working copy
   (:class:`~debate_core.application.caselist.run_state.RunState`). A dry run restores the
   run-state bundle and the state files, and takes nothing. In local mode, the PM's ruling 3(a): a
   run refuses a bucket that holds a lock object, and otherwise nothing changes.
2. **After the publish stage**, and **after the run**: save the run-state bundle, which saves only
   when every snapshot it records is confirmed in the bucket. After the run, a manifest the
   publisher withholds fails the run with the publisher's message. And a runner whose lease was
   taken while it ran ends `RUN_LOCK_LOST`: its stages may have recorded the refusals of its writes
   as failures of their own, so the lease is asked, not the stages.
3. **At the end**, after the monitor has recorded the run: save the state files, then release the
   lock. A run that lost its lease saves nothing.

## SIGTERM

The run's entry point is `timeout --signal=TERM --kill-after=120s 6h`, and ECS gives a stopped task
120 seconds after its SIGTERM. The command asks :meth:`BucketRun.terminate` from the signal, which
cancels the run's task. The cancellation becomes
:class:`~debate_core.application.caselist.run_lock.RunTerminated`, a failure the run monitor records
and publishes like any other, and then the end above runs: the state files, the bundle when it may
be saved and time is left (:data:`TERMINATION_BUNDLE_BUDGET`), the release. A hard kill skips all of
this: the lease then expires, and the next run takes it over and says so.

A run so stopped reads stale under `v1-e34-t32`'s rule until a later run's record lands, which is
right: it did not finish its week.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final

from debate_core.application.caselist.run_lock import (
    BucketRunLock,
    BucketWriteGuard,
    RunLockHeld,
    RunTerminated,
    TakenLock,
)
from debate_core.application.caselist.run_state import BundleSave, RestoreReport, RunState, RunStateWithheld
from debate_core.application.errors import DomainError
from debate_core.application.sync_runs import BucketRunDetails, RestoreDetails

__all__ = ["PULL_COMMAND_NAME", "TERMINATION_BUNDLE_BUDGET", "BucketRun"]

logger = logging.getLogger(__name__)

PULL_COMMAND_NAME: Final = "caselist pull"

TERMINATION_BUNDLE_BUDGET: Final = 60.0
"""Seconds after SIGTERM within which the end still tries the bundle. The release is always tried.

Inside the 120 seconds ECS allows, with the state files, the record's publish and the release
after it; a bundle is about 10 MB today, a few seconds in the region."""


class BucketRun:
    """What one `caselist pull` does with the bucket's run lock and state. See the module docstring.

    Args:
        guard: The command's :class:`BucketWriteGuard`: which mode, and the lock.
        lock: Builds the lease, or `None` when the environment names no bucket.
        state: Builds the run's state in the bucket, or `None` when the environment names no bucket.
        parsed_version: The parsed store's version directory this build reads and writes.
        clock: Seconds, for the termination budget.
    """

    def __init__(
        self,
        *,
        guard: BucketWriteGuard,
        lock: Callable[[], BucketRunLock] | None,
        state: Callable[[], RunState] | None,
        parsed_version: str,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._guard = guard
        self._lock_factory = lock
        self._state_factory = state
        self._parsed_version = parsed_version
        self._clock = clock
        self._lock: BucketRunLock | None = None
        self._taken: TakenLock | None = None
        self._held: RunLockHeld | None = None
        self._restored: RestoreReport | None = None
        self._bundle: BundleSave | None = None
        self._task: asyncio.Task[object] | None = None
        self._terminated_at: float | None = None
        self._finishing = False

    @property
    def bucket_mode(self) -> bool:
        return self._guard.bucket_mode and self._lock_factory is not None and self._state_factory is not None

    # ------------------------------------------------------------------------------------------
    # 1. The start
    # ------------------------------------------------------------------------------------------

    async def start(self, caselists: Sequence[str], *, dry_run: bool, restore_parsed: bool = True) -> None:
        """Take the lock and restore, or in local mode refuse a seeded bucket. See the module docstring.

        `restore_parsed` is off for `--publish-pending`, which parses nothing.
        """
        if not self.bucket_mode:
            if not dry_run and self._lock_factory is not None:
                await asyncio.to_thread(self._guard.refuse_a_seeded_bucket, self._lock_factory())
            return
        assert self._lock_factory is not None and self._state_factory is not None
        state = self._state_factory()
        if dry_run:
            # A dry run reads and takes nothing; what it restores is this machine's copy alone.
            self._restored = await state.restore(caselists, parsed_version=None)
            return
        lock = self._lock_factory()
        try:
            self._taken = await asyncio.to_thread(lock.take, command=PULL_COMMAND_NAME)
        except RunLockHeld as held:
            self._held = held
            raise
        self._lock = lock
        lock.start_renewing()
        self._restored = await state.restore(
            caselists, parsed_version=self._parsed_version if restore_parsed else None
        )

    # ------------------------------------------------------------------------------------------
    # 2. The saves during the run
    # ------------------------------------------------------------------------------------------

    def state_written(self) -> Callable[[Path], None] | None:
        """The state files' own writers' hook: each file saved as it is written. `None` in local mode."""
        if not self.bucket_mode or self._state_factory is None:
            return None
        return self._state_factory().save_state_file_now

    async def after_publish(self) -> None:
        """After the publish stage: the bundle, when every snapshot it records is confirmed."""
        if self._lock is None or self._lock.lost or self._state_factory is None:
            return
        try:
            self._bundle = await self._state_factory().save_bundle()
        except RunStateWithheld as withheld:
            # Said when the run ends, by the save after it, which fails the run with these words.
            self._bundle = BundleSave(saved=False, reason=str(withheld))
        except DomainError as unsaved:
            self._bundle = BundleSave(
                saved=False, reason=f"not saved after the publish ({type(unsaved).__name__})"
            )

    async def after_run(self) -> None:
        """After the run: end `RUN_LOCK_LOST` if the lease was taken, else save the bundle."""
        if self._lock is None or self._state_factory is None:
            return
        self._lock.raise_if_lost()
        self._bundle = await self._state_factory().save_bundle()
        self._lock.raise_if_lost()

    # ------------------------------------------------------------------------------------------
    # 3. The end, and a stop
    # ------------------------------------------------------------------------------------------

    def terminate(self) -> None:
        """SIGTERM: cancel the run's task, once. Called from the command's signal handler."""
        if self._terminated_at is not None or self._task is None or self._finishing:
            return
        self._terminated_at = self._clock()
        logger.warning("caselist pull: SIGTERM received; stopping, saving what it may and releasing the lock")
        self._task.cancel()

    def watching(self, task: asyncio.Task[object]) -> None:
        """The task :meth:`terminate` cancels: the one running the pull."""
        self._task = task

    @property
    def terminated(self) -> bool:
        return self._terminated_at is not None

    def as_terminated(self, cancelled: asyncio.CancelledError) -> BaseException:
        """What a cancellation of the run becomes: :class:`RunTerminated` when SIGTERM asked for it."""
        if not self.terminated:
            return cancelled
        if self._task is not None:
            self._task.uncancel()
        return RunTerminated()

    async def finish(self) -> None:
        """Save the state files and, after a stop, the bundle when it may be; then release the lock."""
        self._finishing = True
        lock = self._lock
        if lock is None:
            return
        try:
            if not lock.lost and self._state_factory is not None:
                state = self._state_factory()
                await state.save_state_files()
                if self.terminated and self._within_the_budget():
                    self._bundle = await state.save_bundle()
        except (DomainError, OSError) as unsaved:
            logger.warning("caselist pull: the run's state was not all saved (%s)", type(unsaved).__name__)
        finally:
            await asyncio.to_thread(lock.release)

    def details(self) -> BucketRunDetails | None:
        """What the run's details say of the lock and the state. `None` in local mode."""
        if not self.bucket_mode:
            return None
        held = self._held
        return BucketRunDetails(
            held_by=held.holder.described() if held is not None and held.holder is not None else None,
            held_until=held.lease_expires_at if held is not None else None,
            took_over=self._taken.took_over if self._taken is not None else None,
            lock_lost=self._lock is not None and self._lock.lost,
            restore=_restore_details(self._restored) if self._restored is not None else None,
            bundle=self._bundle.reason if self._bundle is not None else None,
        )

    def _within_the_budget(self) -> bool:
        return self._terminated_at is None or self._clock() - self._terminated_at < TERMINATION_BUNDLE_BUDGET


def _restore_details(report: RestoreReport) -> RestoreDetails:
    return RestoreDetails(
        started_at=report.started_at,
        finished_at=report.finished_at,
        state_files=len(report.state_files),
        parsed_version=report.parsed_version,
        parsed_objects=report.parsed_objects,
        parsed_bytes=report.parsed_bytes,
        parsed_kept=report.parsed_kept,
        index_id=report.index_id,
    )
