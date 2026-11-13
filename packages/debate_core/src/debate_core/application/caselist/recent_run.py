"""A scheduled `caselist pull` refuses after a run recorded within 24 hours (`v1-e40-t44`).

`v1-e40-t42` made the weekly schedule retry a launch ECS refused, three times within an hour. A retry
after an ambiguous answer (a task placed, the call answered as an error) can start a second task,
since Scheduler sends ECS no idempotency token. The bucket's run lock refuses it while the first run
holds the lock; this refuses it after the first run has finished and released it, so that "never
twice in a week" does not rest on the retries landing before a run can end. The PM's rulings of
2026-11-12:

1. **The window** is :data:`RECENT_RUN_WINDOW`, 24 hours: Scheduler's own ceiling on a schedule's
   event age, so it holds under any retry policy the schedule is given, and the download ledger's
   window, so a second run inside it could only spend what the first left. A hand run between Tuesday
   06:00 and Wednesday 06:00 makes that Wednesday's scheduled pull refuse: the week is then the hand
   run's, and anything newer is late, never lost.
2. **Only a scheduled start is refused**: `caselist pull --scheduled`, which only the weekly
   schedule's container override passes. A pull without it is a hand run and is never refused,
   whatever the day or the hour (:data:`HAND_RUN_CURE`).
3. **Which records count** (:func:`~debate_core.application.caselist.bucket_run.latest_counting_run`):
   a `caselist pull` run of mode `run` that started within the window, whatever its outcome, unless
   it was a refusal of the run lock or of this guard
   (:data:`~debate_core.application.landscape_staleness.LOCK_REFUSALS`). Only `caselist pull` writes
   this log (`test_only_caselist_pull_writes_the_run_log.py` pins it); a `--publish-pending` pull lists
   and fetches nothing and does not count.
4. **Where it sits**: inside the run monitor, so that it is recorded and announced as a lock refusal
   is, and before the lock's take, the restore and the build of the sync service, so before the
   token is read or OpenCaselist is called. It never held the lock, so its record stays on the
   machine that made it.
5. **A run log that cannot be read** is no reason to refuse: the run goes on to the lock, with a
   warning line, as `v1-e34-t26` decided for the drift guard ("late, never the run").
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Final

from debate_core.application.errors import DomainError

__all__ = ["HAND_RUN_CURE", "RECENT_RUN_WINDOW", "RecentRunRecorded"]

RECENT_RUN_WINDOW: Final = timedelta(hours=24)
"""How far back a recorded run's start refuses a scheduled pull (the PM's ruling 1, 2026-11-12)."""

HAND_RUN_CURE: Final = "a hand run (the cloud-run runbook's Step 8) is never refused by this guard"
"""The cure the notice and the hint name, in the PM's words (ruling 4, 2026-11-12)."""


class RecentRunRecorded(DomainError):
    """A scheduled pull found a run started within :data:`RECENT_RUN_WINDOW` in the bucket's run log.

    It did nothing: it took no lock, restored nothing and called no provider. Its record stays on this
    machine, as a lock refusal's does: it never held the lock, so it never writes to the bucket.
    """

    record_stays_local = True

    def __init__(self, *, run_id: str, started_at: datetime) -> None:
        self.run_id = run_id
        self.started_at = started_at
        started = started_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        super().__init__(
            f"the bucket's run log records run {run_id}, started {started}, within the last 24 hours, "
            "so this scheduled pull did nothing; that run records and announces its own outcome"
        )
        self.hint = (
            f"Run {run_id} started {started}, within the last 24 hours. If the week still needs a run, "
            f"{HAND_RUN_CURE}."
        )
