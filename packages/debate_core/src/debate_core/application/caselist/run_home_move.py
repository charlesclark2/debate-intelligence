"""The weekly run's home moves to prod: dev's run lock held for good, and its release (`v1-e40-t11`).

ADR-0020 (7) step 3. At the pilot's promotion, after prod's lock is seeded, dev's lock object is
rewritten held for good by a holder of kind `moved`, naming `home_environment: prod`, so that no dev
build publishes to dev's run state again. `debate-research caselist move-run-home` writes it:

1. **The dry run** (the default) reads the lock and judges it by the rules a take would
   (:meth:`~debate_core.application.caselist.run_lock.BucketRunLock.check`), and shows the body it
   would write. It writes nothing.
2. **The move** (`--execute`) takes the lock like any other command, so it is refused while a run
   holds it, naming the holder; then rewrites it, with `If-Match` on the version it took, as held for
   good by the move (:meth:`~debate_core.application.caselist.run_lock.BucketRunLock.hold_for_good`).
   The holder names the new home, when it was written, and who wrote it: the kind of runner and the
   build, never a person. It has no lease, and it never expires.
3. **The release** (`--release`, dry run first, then `--release --execute`) undoes it: only a lock
   held by a move is released, written `free` naming this environment as the home again, with
   `If-Match` on the version it read. The runbook allows it only after the coach confirms.

It applies in dev only. Prod's lock names prod from its seed, and the run's home moves from dev to
prod, never the other way, so a prod lock has nothing to move: in prod both refuse
(:class:`RunHomeMoveRefused`) before reading anything.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from debate_core.application.caselist.run_lock import BucketRunLock, LockBody, LockState
from debate_core.application.errors import DomainError

__all__ = ["MOVE_COMMAND", "NEW_HOME", "RunHomeMove", "RunHomeMoveRefused", "RunHomeMoveReport"]

MOVE_COMMAND: Final = "caselist move-run-home"

NEW_HOME: Final = "prod"
"""Where the run's home moves (ADR-0020 (7)): the only move the decision record makes."""


class RunHomeMoveRefused(DomainError):
    """The move, or its release, was asked for in the environment the home moves to. Nothing was read."""

    def __init__(self, environment: str) -> None:
        self.environment = environment
        super().__init__(
            f"the weekly run's home moves from dev to {NEW_HOME}, and this is {environment}: its lock names "
            f"{NEW_HOME} from its seed, so there is nothing here to move or release, and nothing was done"
        )
        self.hint = "Run it with DEBATE_ENV=dev, against dev's bucket, as the cutover runbook says."


@dataclass(frozen=True, slots=True)
class RunHomeMoveReport:
    """What the move or its release found in the bucket, and what it wrote, or would write."""

    applied: bool
    release: bool
    found: LockBody
    """The lock as it was read, before anything was written."""
    written: LockBody
    """The body written, or, in a dry run, the body that would be."""


class RunHomeMove:
    """The move of the weekly run's home, and its release. See the module docstring.

    Args:
        lock: This command's lease on this environment's run lock.
        environment: This environment, which must not be the new home.
        build: This build's tag, written into the moved holder as who wrote it.
    """

    def __init__(self, *, lock: Callable[[], BucketRunLock], environment: str, build: str | None) -> None:
        self._lock = lock
        self._environment = environment
        self._build = build

    def plan(self) -> RunHomeMoveReport:
        """The move's dry run: the lock judged as a take would judge it, and the body it would get."""
        self._refuse_the_new_home()
        lock = self._lock()
        found = lock.check()
        written = lock.moved_body(home=NEW_HOME, command=MOVE_COMMAND, build=self._build)
        return RunHomeMoveReport(applied=False, release=False, found=found, written=written)

    def move(self) -> RunHomeMoveReport:
        """Take the lock, then rewrite it held for good by the move. Refused as a take is refused."""
        self._refuse_the_new_home()
        lock = self._lock()
        found = lock.check()
        lock.take(command=MOVE_COMMAND)
        try:
            written = lock.hold_for_good(home=NEW_HOME, command=MOVE_COMMAND, build=self._build)
        finally:
            # Frees the lock only when the rewrite did not happen; after it, this runner holds nothing.
            lock.release()
        return RunHomeMoveReport(applied=True, release=False, found=found, written=written)

    def plan_release(self) -> RunHomeMoveReport:
        """The release's dry run: refused unless a move holds the lock, and the body it would get."""
        self._refuse_the_new_home()
        lock = self._lock()
        found = lock.check_home_move()
        written = LockBody(home_environment=self._environment, state=LockState.FREE)
        return RunHomeMoveReport(applied=False, release=True, found=found, written=written)

    def release(self) -> RunHomeMoveReport:
        """Give the lock back to this environment, free, with `If-Match` on the version read."""
        self._refuse_the_new_home()
        found, written = self._lock().release_home_move()
        return RunHomeMoveReport(applied=True, release=True, found=found, written=written)

    def _refuse_the_new_home(self) -> None:
        if self._environment == NEW_HOME:
            raise RunHomeMoveRefused(self._environment)
