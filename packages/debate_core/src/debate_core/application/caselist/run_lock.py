"""The bucket's run lock: one runner at a time writes to an evidence bucket (ADR-0020 (4), `v1-e40-t04`).

In bucket mode (`caselist.run_state = "bucket"`) every command that writes to an evidence bucket
holds a lease on `reports/sync/run-lock.json` in that bucket for as long as it writes. The object
holds no personal data:

.. code-block:: json

    {
      "format_version": 1,
      "home_environment": "dev",
      "state": "held",
      "holder": {
        "kind": "cloud", "run_id": "20261104T110005Z", "task": "<ECS task>", "command": "caselist pull"
      },
      "acquired_at": "2026-11-04T11:00:05Z",
      "renewed_at": "2026-11-04T11:25:05Z",
      "lease_expires_at": "2026-11-04T11:55:05Z",
      "took_over_from": null
    }

Every change is a conditional write through
:class:`~debate_core.application.ports.run_lock.LockObjectStore`, so of two runners that move at
once exactly one succeeds.

## The rules, as ADR-0020 (4) sets them

1. **It exists only once seeded.** :meth:`BucketRunLock.create` (the seed, `caselist
   seed-run-state`) writes it with `If-None-Match: *`. Nothing else creates it: a bucket with no lock
   object has no run state, and :meth:`BucketRunLock.take` refuses it with
   :class:`RunStateNotSeeded`, before anything is restored or written.
2. **Taking it.** The object is read with its entity tag, and refused unless `home_environment`
   names this environment (:class:`RunLockWrongHome`). When it is `free`, or `held` with
   `lease_expires_at` more than :data:`CLOCK_SKEW_MARGIN` past, this runner writes itself in with
   `If-Match` on that tag. A live lease is :class:`RunLockHeld`; so is losing the race to write.
3. **The lease** is :data:`LEASE` long, renewed every :data:`RENEW_EVERY` by a background thread,
   each renewal with `If-Match` on the tag this runner last wrote.
4. **Fencing.** :meth:`BucketRunLock.before_write` is the
   :class:`~debate_core.application.ports.run_lock.WriteFence` every S3 client of a bucket-mode
   command asks before each write. A named object's write waits for a renewal that *started after
   it asked* and was confirmed; a content-addressed object's needs only a lease that is still held.
   Writers that ask while a renewal is in flight share the next one rather than each sending its
   own, so a parse publishing thousands of files does not serialise on the lock (the PM's ruling on
   the plan, 2026-10-24). A renewal answered `412` or `404` means the lease was taken: this runner
   has lost it, every later write is refused with :class:`RunLockLost`, and the run ends
   `RUN_LOCK_LOST`.
5. **Releasing** writes `state: free` with `If-Match`. The object is never deleted.
6. **Taking over an expired lease** is automatic, so that one task that died does not stop every
   later week. The new holder records `took_over_from`, and :attr:`TakenLock.took_over` says so in
   words for the run's details and its notification.
7. **Held for good** (ADR-0020 (7) step 3, `v1-e40-t11`). When the run's home moves to prod, dev's
   lock is rewritten by `caselist move-run-home`, under the lock and with `If-Match`, as held by a
   holder of kind `moved` naming `home_environment: prod`, with no lease
   (:meth:`BucketRunLock.hold_for_good`). It never expires, and every take of it is
   :class:`RunHomeMoved`, which says the weekly run now runs from prod; so are local mode's check, the
   seed's plan and the backfile import's (:meth:`BucketRunLock.home_moved`). Only
   :meth:`BucketRunLock.release_home_move`, again with `If-Match`, ends it.

The local `flock` (:class:`~debate_core.application.caselist_sync.RunLock`) stays as well, for two
runs on one machine.

## Times

All times are this runner's clock, in UTC, to the second. :data:`CLOCK_SKEW_MARGIN` is the allowance
for two runners' clocks disagreeing: a lease is taken over only once it is that long past.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Final

from debate_core.application.errors import DomainError, StoreError
from debate_core.application.ports.run_lock import LockObjectChanged, LockObjectStore
from debate_core.application.settings import RunStateMode

__all__ = [
    "CLOCK_SKEW_MARGIN",
    "LEASE",
    "LOCK_FORMAT_VERSION",
    "RENEW_EVERY",
    "RUN_LOCK_KEY",
    "BucketKeepsRunState",
    "BucketRunLock",
    "BucketWriteGuard",
    "HolderKind",
    "LockBody",
    "LockHolder",
    "LockState",
    "RunLockHeld",
    "RunLockLost",
    "RunLockNotHeld",
    "RunLockUnreadable",
    "RunHomeMoved",
    "RunHomeNotMoved",
    "RunLockWrongHome",
    "RunStateNotSeeded",
    "RunTerminated",
    "TakenLock",
    "is_content_addressed",
    "lock_run_id",
]

logger = logging.getLogger(__name__)

RUN_LOCK_KEY: Final = "reports/sync/run-lock.json"
"""Where the lock object lives in the home environment's bucket (the store layout document)."""

LOCK_FORMAT_VERSION: Final = 1

LEASE: Final = timedelta(minutes=30)
"""How long a holder's lease lasts from its last renewal (ADR-0020 (4) 3)."""

RENEW_EVERY: Final = timedelta(minutes=5)
"""How often the background thread renews it. A runner therefore survives 25 minutes of failed renewals."""

CLOCK_SKEW_MARGIN: Final = timedelta(minutes=5)
"""How far past its expiry a lease must be before another runner takes it over."""

_TIME_FORMAT: Final = "%Y-%m-%dT%H:%M:%SZ"
_RUN_ID_FORMAT: Final = "%Y%m%dT%H%M%SZ"

#: A content-addressed key: the bytes' own SHA-256 is the last segment, under a `sha256/` fan-out.
#: The same bytes whoever writes them, so such a write needs no renewal (ADR-0020 (4) 4).
_CONTENT_ADDRESSED: Final = re.compile(r"(?:^|/)sha256/[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{64}$")


def is_content_addressed(key: str) -> bool:
    """Whether `key` names bytes by their own digest (`raw/caselist/hsld26/sha256/ab/cd/<digest>`)."""
    return _CONTENT_ADDRESSED.search(key) is not None


def lock_run_id(moment: datetime) -> str:
    """The run id a holder is recorded under: the UTC second it took the lock, as run ids are written."""
    return moment.astimezone(UTC).strftime(_RUN_ID_FORMAT)


def _at(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime(_TIME_FORMAT)


def _parsed_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, _TIME_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        return None


# ------------------------------------------------------------------------------------------------
# The body
# ------------------------------------------------------------------------------------------------


class LockState(StrEnum):
    HELD = "held"
    FREE = "free"


class HolderKind(StrEnum):
    """Who holds the lock: a cloud run, a Mac, or (`v1-e40-t11`) the move of the run's home, for good."""

    CLOUD = "cloud"
    MAC = "mac"
    MOVED = "moved"


@dataclass(frozen=True, slots=True)
class LockHolder:
    """Who holds the lock.

    A `moved` holder (`v1-e40-t11`) also says who wrote it, never by a person's name: `by` is the
    kind of runner the command ran on (`mac` or `cloud`), and `build` the build's tag. Both are
    written only for that holder, so every other holder's body is as it was.
    """

    kind: str
    run_id: str
    command: str
    task: str | None = None
    by: str | None = None
    build: str | None = None

    def as_json(self) -> dict[str, object]:
        named: dict[str, object] = {
            "kind": self.kind,
            "run_id": self.run_id,
            "task": self.task,
            "command": self.command,
        }
        if self.by is not None:
            named["by"] = self.by
        if self.build is not None:
            named["build"] = self.build
        return named

    def described(self) -> str:
        if self.kind == HolderKind.MOVED:
            return f"the move of the run's home (`{self.command}`, {self.written_by()})"
        return f"{self.kind} run {self.run_id} (`{self.command}`)"

    def written_by(self) -> str:
        """Who wrote a moved holder: `from a mac, build v1.1.0-dev.262`, as far as it says."""
        runner = f"from a {self.by}" if self.by else "from an unnamed runner"
        return f"{runner}, build {self.build}" if self.build else runner


@dataclass(frozen=True, slots=True)
class LockBody:
    """The lock object's body, as ADR-0020 (4) gives it."""

    home_environment: str
    state: LockState
    holder: LockHolder | None = None
    acquired_at: datetime | None = None
    renewed_at: datetime | None = None
    lease_expires_at: datetime | None = None
    took_over_from: str | None = None

    @property
    def moved(self) -> bool:
        """Whether the lock is held for good by the move of the run's home (ADR-0020 (7), `v1-e40-t11`)."""
        return (
            self.state is LockState.HELD and self.holder is not None and self.holder.kind == HolderKind.MOVED
        )

    def as_bytes(self) -> bytes:
        body = {
            "format_version": LOCK_FORMAT_VERSION,
            "home_environment": self.home_environment,
            "state": str(self.state),
            "holder": self.holder.as_json() if self.holder is not None else None,
            "acquired_at": _at(self.acquired_at) if self.acquired_at is not None else None,
            "renewed_at": _at(self.renewed_at) if self.renewed_at is not None else None,
            "lease_expires_at": _at(self.lease_expires_at) if self.lease_expires_at is not None else None,
            "took_over_from": self.took_over_from,
        }
        return (json.dumps(body, indent=2) + "\n").encode("utf-8")

    @classmethod
    def from_bytes(cls, raw: bytes) -> LockBody:
        """Read a body this build or a later one wrote. Raises :class:`RunLockUnreadable` otherwise."""
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise RunLockUnreadable("it is not JSON") from None
        if not isinstance(body, dict):
            raise RunLockUnreadable("it is not a JSON object")
        fields: dict[str, object] = body  # pyright: ignore[reportUnknownVariableType]
        version = fields.get("format_version")
        if not isinstance(version, int) or version < LOCK_FORMAT_VERSION:
            raise RunLockUnreadable("it has no format version this build reads")
        home = fields.get("home_environment")
        if not isinstance(home, str) or not home:
            raise RunLockUnreadable("it names no home environment")
        try:
            state = LockState(str(fields.get("state")))
        except ValueError:
            raise RunLockUnreadable("its state is neither held nor free") from None
        holder = fields.get("holder")
        parsed_holder: LockHolder | None = None
        if isinstance(holder, dict):
            named: dict[str, object] = holder  # pyright: ignore[reportUnknownVariableType]
            task = named.get("task")
            by = named.get("by")
            build = named.get("build")
            parsed_holder = LockHolder(
                kind=str(named.get("kind")),
                run_id=str(named.get("run_id")),
                command=str(named.get("command")),
                task=task if isinstance(task, str) else None,
                by=by if isinstance(by, str) else None,
                build=build if isinstance(build, str) else None,
            )
        if state is LockState.HELD and parsed_holder is None:
            raise RunLockUnreadable("it is held by nobody")
        taken_over = fields.get("took_over_from")
        return cls(
            home_environment=home,
            state=state,
            holder=parsed_holder,
            acquired_at=_parsed_time(fields.get("acquired_at")),
            renewed_at=_parsed_time(fields.get("renewed_at")),
            lease_expires_at=_parsed_time(fields.get("lease_expires_at")),
            took_over_from=taken_over if isinstance(taken_over, str) else None,
        )


# ------------------------------------------------------------------------------------------------
# The refusals. Each names the lock by its key, never a path on this machine, and quotes nothing
# but run ids, commands and times.
# ------------------------------------------------------------------------------------------------


class RunStateNotSeeded(DomainError):
    """The bucket holds no run lock, so it holds no run state: a bucket-mode command does nothing.

    The safety net until the seed (ADR-0020 (4) 1): a `caselist pull` against a bucket never seeded,
    or the wrong environment's, stops before it restores or writes anything.
    """

    record_stays_local = True

    def __init__(self) -> None:
        super().__init__(
            f"this bucket holds no run lock ({RUN_LOCK_KEY}), so it keeps no run state, and nothing "
            "was done: a bucket is seeded once, by `debate-research caselist seed-run-state` on the "
            "machine that holds the run's state"
        )


class RunLockUnreadable(DomainError):
    """The lock object is there and is not one this build reads. Never written over."""

    record_stays_local = True

    def __init__(self, problem: str) -> None:
        self.problem = problem
        super().__init__(
            f"the bucket's run lock ({RUN_LOCK_KEY}) could not be read ({problem}), so nothing was "
            "done and it was left as it is"
        )


class RunLockWrongHome(DomainError):
    """The lock names another environment as the run's home (ADR-0020 (7)): this runner does nothing."""

    record_stays_local = True

    def __init__(self, *, home: str, environment: str) -> None:
        self.home = home
        self.environment = environment
        super().__init__(
            f"the bucket's run lock names {home} as the run's home environment, and this is "
            f"{environment}: nothing was done"
        )


class RunHomeMoved(DomainError):
    """The weekly run's home moved, and this bucket's lock is held for good by the move (`v1-e40-t11`).

    ADR-0020 (7) step 3: at the pilot's promotion the dev lock is rewritten, held by a holder of kind
    `moved` naming `home_environment: prod`, and it never expires. Every command that takes the lock is
    refused with this, whatever environment it runs in, before it writes anything. Its record stays on
    this machine, as every lock refusal's does.
    """

    record_stays_local = True

    def __init__(self, *, body: LockBody, environment: str) -> None:
        self.home = body.home_environment
        self.environment = environment
        self.moved_at = _at(body.acquired_at) if body.acquired_at is not None else None
        self.moved_by = body.holder.written_by() if body.holder is not None else None
        since = f" since {self.moved_at}" if self.moved_at is not None else ""
        command = f"`{body.holder.command}`, " if body.holder is not None else ""
        super().__init__(
            f"the weekly run now runs from {self.home}: this bucket's run lock ({RUN_LOCK_KEY}) is held "
            f"for good{since} by the move of the run's home to {self.home} ({command}{self.moved_by}), "
            f"so this {environment} command did nothing"
        )
        self.hint = (
            f"Run the week from {self.home}. Only if the move was a mistake, and only after the coach "
            "confirms it, `debate-research caselist move-run-home --release` gives this lock back "
            "(docs/runbooks/caselist-cutover.md)."
        )


class RunHomeNotMoved(DomainError):
    """A release of the run's home was asked for, and the lock is not held by a move (`v1-e40-t11`)."""

    record_stays_local = True

    def __init__(self, body: LockBody) -> None:
        self.home = body.home_environment
        self.state = str(body.state)
        super().__init__(
            f"this bucket's run lock ({RUN_LOCK_KEY}) is not held by a move of the run's home (it is "
            f"{body.state} and names {body.home_environment} as the home), so there is nothing to release "
            "and nothing was written"
        )


class RunLockHeld(DomainError):
    """Another runner holds a live lease on the bucket's run lock: this one did nothing at all.

    Its record stays on this machine (ADR-0020 (4), "What the Mac's agent does while the lock is
    held"): it never held the lock, so it never writes to the bucket.
    """

    record_stays_local = True

    def __init__(self, *, holder: LockHolder | None, lease_expires_at: datetime | None) -> None:
        self.holder = holder
        self.lease_expires_at = lease_expires_at
        who = holder.described() if holder is not None else "another runner"
        until = f", its lease until {_at(lease_expires_at)}" if lease_expires_at is not None else ""
        super().__init__(
            f"{who} holds the bucket's run lock{until}; this one did nothing. That run records and "
            "announces its own outcome."
        )


class RunLockLost(DomainError):
    """This runner's lease was taken over while it ran: it writes nothing more, and ends `RUN_LOCK_LOST`.

    The case this is for is a runner that went quiet past its lease (a Mac that slept through it)
    and woke while another held a new one (ADR-0020 (4) 4). Its record stays on this machine.
    """

    record_stays_local = True

    def __init__(self) -> None:
        super().__init__(
            "this runner's lease on the bucket's run lock was taken over by another runner after it "
            "expired, so it wrote nothing more to the bucket; the run that took it over records and "
            "publishes its own outcome"
        )


class RunLockNotHeld(DomainError):
    """A write to the bucket was asked for in bucket mode by a command that holds no lease.

    A guard against a command that forgot to take the lock: the write is refused, never sent
    unfenced.
    """

    def __init__(self) -> None:
        super().__init__(
            "in bucket mode a write to the evidence bucket needs the bucket's run lock, and this "
            "command does not hold it, so nothing was written"
        )


class BucketKeepsRunState(DomainError):
    """A local-mode command would write to a bucket that keeps its run state (the PM's ruling 3(a)).

    Once a bucket is seeded its state is the bucket's, and a machine in local mode would publish
    from an older copy and download against a ledger the bucket does not share. A pull so refused
    keeps its record on this machine: it would otherwise write it to the bucket it refused.
    """

    record_stays_local = True

    def __init__(self) -> None:
        super().__init__(
            f"this bucket keeps its run state (it holds {RUN_LOCK_KEY}); set caselist.run_state = bucket"
        )


class RunTerminated(DomainError):
    """The process was told to stop (SIGTERM): the container's deadline, or `ecs stop-task`.

    ADR-0020 (1) 6 and `v1-e40-t03`'s follow-up: the run's entry point is `timeout --signal=TERM
    --kill-after=120s 6h`, and ECS stops a task with SIGTERM and SIGKILL 120 seconds later. A
    command told to stop saves what ADR-0020 (3) lets it, writes a failed run record and releases
    the lock in that time. A failure, so the coach is told; the run that follows reads it stale
    under `v1-e34-t32`'s rule until its own record lands.
    """

    def __init__(self) -> None:
        super().__init__(
            "the run was told to stop (SIGTERM, the run's deadline or a stop by hand) before it "
            "finished; it saved what it may and released the bucket's run lock"
        )


# ------------------------------------------------------------------------------------------------
# The lease
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TakenLock:
    """What taking the lock found: whose lease, if anyone's, this runner took over."""

    holder: LockHolder
    took_over_from: LockHolder | None = None
    previous_lease_expired_at: datetime | None = None

    @property
    def took_over(self) -> str | None:
        """The sentence the run's details and notification carry, or `None` for an ordinary take."""
        if self.took_over_from is None:
            return None
        expired = (
            f", whose lease expired at {_at(self.previous_lease_expired_at)}"
            if self.previous_lease_expired_at is not None
            else ""
        )
        return f"took over the bucket's run lock from {self.took_over_from.described()}{expired}"


class _Phase(StrEnum):
    NOT_HELD = "not_held"
    HELD = "held"
    LOST = "lost"
    RELEASED = "released"


class BucketRunLock:
    """One runner's lease on the bucket's run lock, and the write fence that relies on it.

    Built per command by the composition root, and handed to every S3 client it builds in bucket
    mode as their :class:`~debate_core.application.ports.run_lock.WriteFence`::

        lock = BucketRunLock(store=lock_object, environment="dev", clock=clock, kind=HolderKind.CLOUD)
        taken = lock.take(command="caselist pull")
        try:
            ...                       # every bucket write asks lock.before_write first
        finally:
            lock.release()

    Args:
        store: The lock object.
        environment: This runner's environment, which the lock's `home_environment` must name.
        clock: Now, in UTC.
        kind: Who this runner is (:class:`HolderKind`).
        task: The ECS task the cloud run is, when it is one.
        lease, renew_every, skew_margin: ADR-0020 (4)'s numbers, overridable for a test.
    """

    def __init__(
        self,
        *,
        store: LockObjectStore,
        environment: str,
        clock: Callable[[], datetime],
        kind: HolderKind,
        task: str | None = None,
        lease: timedelta = LEASE,
        renew_every: timedelta = RENEW_EVERY,
        skew_margin: timedelta = CLOCK_SKEW_MARGIN,
    ) -> None:
        self._store = store
        self._environment = environment
        self._clock = clock
        self._kind = kind
        self._task = task
        self._lease = lease
        self._renew_every = renew_every
        self._skew_margin = skew_margin
        self._condition = threading.Condition()
        self._phase = _Phase.NOT_HELD
        self._body: LockBody | None = None
        self._etag: str | None = None
        # Renewals are numbered as they start; a named write waits for the first one numbered
        # after the renewals already started when it asked (rule 4 in the module docstring).
        self._renewals_started = 0
        self._renewals_finished = 0
        self._renewal_in_flight = False
        self._stop_renewing = threading.Event()
        self._renewer: threading.Thread | None = None
        self.taken: TakenLock | None = None

    # ------------------------------------------------------------------------------------------
    # What a command asks
    # ------------------------------------------------------------------------------------------

    @property
    def held(self) -> bool:
        """Whether this runner holds the lease now: taken, not lost, not released."""
        with self._condition:
            return self._phase is _Phase.HELD

    @property
    def lost(self) -> bool:
        """Whether another runner took this one's lease over while it ran."""
        with self._condition:
            return self._phase is _Phase.LOST

    def raise_if_lost(self) -> None:
        if self.lost:
            raise RunLockLost

    def bucket_is_seeded(self) -> bool:
        """Whether the bucket holds a lock object at all: the local-mode check of ruling 3(a)."""
        return self._store.read() is not None

    def take(self, *, command: str, run_id: str | None = None) -> TakenLock:
        """Take the lease for `command`, taking over an expired one. See the module docstring, rule 2.

        Raises :class:`RunStateNotSeeded`, :class:`RunLockUnreadable`, :class:`RunHomeMoved`,
        :class:`RunLockWrongHome` or :class:`RunLockHeld`, each before anything is written.
        """
        found = self._store.read()
        if found is None:
            raise RunStateNotSeeded
        current = LockBody.from_bytes(found.body)
        now = self._clock()
        previous = self._refuse_unless_takeable(current, now)
        holder = self._holder(command, run_id, now)
        body = LockBody(
            home_environment=self._environment,
            state=LockState.HELD,
            holder=holder,
            acquired_at=now,
            renewed_at=now,
            lease_expires_at=now + self._lease,
            took_over_from=previous.run_id if previous is not None else None,
        )
        try:
            etag = self._store.replace(body.as_bytes(), etag=found.etag)
        except LockObjectChanged:
            # Another runner moved between the read and this write: the first writer wins.
            raise RunLockHeld(holder=None, lease_expires_at=None) from None
        self._hold(body, etag)
        self.taken = TakenLock(
            holder=holder,
            took_over_from=previous,
            previous_lease_expired_at=current.lease_expires_at if previous is not None else None,
        )
        if self.taken.took_over is not None:
            logger.warning("run lock: %s", self.taken.took_over)
        return self.taken

    def create(self, *, command: str, run_id: str | None = None) -> TakenLock:
        """Create the lock object, held by this runner: the seed's first step (rule 1).

        Raises :class:`~debate_core.application.ports.run_lock.LockObjectChanged` when the bucket
        already holds one, which is a bucket seeded already.
        """
        now = self._clock()
        holder = self._holder(command, run_id, now)
        body = LockBody(
            home_environment=self._environment,
            state=LockState.HELD,
            holder=holder,
            acquired_at=now,
            renewed_at=now,
            lease_expires_at=now + self._lease,
        )
        etag = self._store.create(body.as_bytes())
        self._hold(body, etag)
        self.taken = TakenLock(holder=holder)
        return self.taken

    # ------------------------------------------------------------------------------------------
    # The run's home moved (ADR-0020 (7) step 3, `v1-e40-t11`)
    # ------------------------------------------------------------------------------------------

    def check(self) -> LockBody:
        """What :meth:`take` would find: the lock read and judged by take's rules, nothing written.

        A dry run's answer. Raises what :meth:`take` raises before it writes.
        """
        found = self._store.read()
        if found is None:
            raise RunStateNotSeeded
        current = LockBody.from_bytes(found.body)
        self._refuse_unless_takeable(current, self._clock())
        return current

    def home_moved(self) -> RunHomeMoved | None:
        """The refusal a lock held by the move of the run's home gives this runner, or `None`.

        For the checks that read the lock without taking it: local mode's (ruling 3(a)), the seed's
        plan and the backfile import's. No lock, or one this build cannot read, is `None`: those have
        refusals of their own.
        """
        found = self._store.read()
        if found is None:
            return None
        try:
            current = LockBody.from_bytes(found.body)
        except RunLockUnreadable:
            return None
        return RunHomeMoved(body=current, environment=self._environment) if current.moved else None

    def moved_body(self, *, home: str, command: str, build: str | None) -> LockBody:
        """The lock held for good by the move of the run's home to `home`, written now by this runner."""
        now = self._clock()
        return LockBody(
            home_environment=home,
            state=LockState.HELD,
            holder=LockHolder(
                kind=str(HolderKind.MOVED),
                run_id=lock_run_id(now),
                command=command,
                task=self._task,
                by=str(self._kind),
                build=build,
            ),
            acquired_at=now,
        )

    def hold_for_good(self, *, home: str, command: str, build: str | None) -> LockBody:
        """Rewrite the lock this runner holds as held for good by the move of the run's home.

        With `If-Match` on the version this runner last wrote, after its renewals have stopped, so the
        holder is written under the lock and over nothing but this runner's own lease. From then on this
        runner holds nothing, and :meth:`release` writes nothing. Returns the body written.

        Raises :class:`RunLockNotHeld` unless this runner holds the lease, and :class:`RunLockLost`
        when it was taken over before the write. A store that did not answer leaves the lease this
        runner's, for :meth:`release` to free.
        """
        with self._condition:
            self._refuse_unless_held()
            while self._renewal_in_flight:
                self._condition.wait()
            etag = self._etag
            # No write of this runner's goes out after this one: the fence refuses from here.
            self._phase = _Phase.RELEASED
        assert etag is not None
        self._stop_renewing.set()
        if self._renewer is not None and self._renewer is not threading.current_thread():
            self._renewer.join(timeout=5)
        body = self.moved_body(home=home, command=command, build=build)
        try:
            self._store.replace(body.as_bytes(), etag=etag)
        except LockObjectChanged:
            with self._condition:
                self._phase = _Phase.LOST
                self._condition.notify_all()
            raise RunLockLost from None
        except DomainError:
            with self._condition:
                self._phase = _Phase.HELD
            raise
        logger.warning("run lock: held for good by %s", body.holder.described() if body.holder else "a move")
        return body

    def check_home_move(self) -> LockBody:
        """The release's dry run: the lock read, refused unless a move holds it. Nothing written.

        Raises :class:`RunStateNotSeeded`, :class:`RunLockUnreadable` or :class:`RunHomeNotMoved`.
        """
        return self._moved_lock()[0]

    def release_home_move(self) -> tuple[LockBody, LockBody]:
        """Give the lock back to this environment, free: the undoing of a move.

        Only a lock a move holds, and only with `If-Match` on the version read, so a lock that changed
        since is never written over
        (:class:`~debate_core.application.ports.run_lock.LockObjectChanged`). Returns the lock as read,
        and what was written over it. Raises what :meth:`check_home_move` raises, before writing.
        """
        found, etag = self._moved_lock()
        free = LockBody(home_environment=self._environment, state=LockState.FREE, renewed_at=self._clock())
        self._store.replace(free.as_bytes(), etag=etag)
        logger.warning(
            "run lock: the move of the run's home was released; %s is its home again", self._environment
        )
        return found, free

    def _moved_lock(self) -> tuple[LockBody, str]:
        found = self._store.read()
        if found is None:
            raise RunStateNotSeeded
        current = LockBody.from_bytes(found.body)
        if not current.moved:
            raise RunHomeNotMoved(current)
        return current, found.etag

    def start_renewing(self) -> None:
        """Renew every :data:`RENEW_EVERY` in a daemon thread until :meth:`release`.

        A lease taken again after a release renews again, on a thread of its own: a command that holds
        the lock for each of several steps, as `caselist backfile-import` does (`v1-e34-t34`), takes
        and releases this same lock, whose holder the bucket client's write fence asks.
        """
        if self._renewer is not None and self._renewer.is_alive():
            return
        self._stop_renewing = threading.Event()
        self._renewer = threading.Thread(
            target=self._renew_periodically, name="run-lock-renewal", daemon=True
        )
        self._renewer.start()

    def renew(self) -> None:
        """Renew the lease with a conditional write that starts after this call. See rule 4.

        Raises :class:`RunLockLost` when the lease was taken, :class:`RunLockNotHeld` when it was
        never held or is released, and the store's own error when the store did not answer: the
        lease may still be this runner's, and the next renewal finds out.
        """
        with self._condition:
            wanted = self._renewals_started + 1
            while True:
                self._refuse_unless_held()
                if self._renewals_finished >= wanted:
                    return
                if not self._renewal_in_flight:
                    self._renewal_in_flight = True
                    self._renewals_started += 1
                    mine = self._renewals_started
                    break
                self._condition.wait()
        succeeded = False
        try:
            self._renew_once()
            succeeded = True
        finally:
            with self._condition:
                self._renewal_in_flight = False
                if succeeded:
                    self._renewals_finished = mine
                else:
                    # A renewal that failed confirms nothing: give back its number, so the writers
                    # waiting on it start another rather than going ahead unrenewed.
                    self._renewals_started = self._renewals_finished
                self._condition.notify_all()

    def before_write(self, key: str, *, renew: bool) -> None:
        """The write fence (:class:`~debate_core.application.ports.run_lock.WriteFence`)."""
        if renew and not is_content_addressed(key):
            self.renew()
            return
        with self._condition:
            self._refuse_unless_held()

    def release(self) -> None:
        """Stop renewing and write `state: free` with `If-Match`. Never deletes the object.

        Writes are refused from the moment this is called. A release that is refused (the lease was
        taken) or that the store does not answer is logged and left: the lease then expires, and the
        next runner takes it over and says so.
        """
        with self._condition:
            was = self._phase
            if was is _Phase.HELD:
                self._phase = _Phase.RELEASED
            while self._renewal_in_flight:
                self._condition.wait()
            body, etag = self._body, self._etag
        self._stop_renewing.set()
        if self._renewer is not None and self._renewer is not threading.current_thread():
            self._renewer.join(timeout=5)
        if was is not _Phase.HELD or body is None or etag is None:
            return
        free = LockBody(
            home_environment=body.home_environment,
            state=LockState.FREE,
            holder=None,
            renewed_at=self._clock(),
        )
        try:
            self._store.replace(free.as_bytes(), etag=etag)
        except LockObjectChanged:
            logger.warning("run lock: not released, because another runner had taken it over")
        except DomainError as unanswered:
            logger.warning(
                "run lock: not released (%s); its lease expires at %s and the next run takes it over",
                type(unanswered).__name__,
                _at(body.lease_expires_at) if body.lease_expires_at is not None else "an unknown time",
            )

    # ------------------------------------------------------------------------------------------
    # The pieces
    # ------------------------------------------------------------------------------------------

    def _refuse_unless_takeable(self, current: LockBody, now: datetime) -> LockHolder | None:
        """Take's rules (rule 2): raise its refusals, or return the holder of an expired lease taken over.

        A lock held for good by the move of the run's home is :class:`RunHomeMoved` whichever rule
        meets it first: the home, for this environment's own runs, or the lease, which never expires,
        for a runner of the new home pointed at this bucket.
        """
        if current.home_environment != self._environment:
            if current.moved:
                raise RunHomeMoved(body=current, environment=self._environment)
            raise RunLockWrongHome(home=current.home_environment, environment=self._environment)
        if current.state is not LockState.HELD:
            return None
        if not self._expired(current, now):
            if current.moved:
                raise RunHomeMoved(body=current, environment=self._environment)
            raise RunLockHeld(holder=current.holder, lease_expires_at=current.lease_expires_at)
        return current.holder

    def _expired(self, body: LockBody, now: datetime) -> bool:
        if body.moved:
            # Held for good (`v1-e40-t11`): only the release, after the coach confirms, ends it.
            return False
        if body.lease_expires_at is None:
            return True
        return now > body.lease_expires_at + self._skew_margin

    def _holder(self, command: str, run_id: str | None, now: datetime) -> LockHolder:
        return LockHolder(
            kind=str(self._kind), run_id=run_id or lock_run_id(now), command=command, task=self._task
        )

    def _hold(self, body: LockBody, etag: str) -> None:
        with self._condition:
            self._body = body
            self._etag = etag
            self._phase = _Phase.HELD

    def _refuse_unless_held(self) -> None:
        """Under the condition's lock."""
        if self._phase is _Phase.LOST:
            raise RunLockLost
        if self._phase is not _Phase.HELD:
            raise RunLockNotHeld

    def _renew_once(self) -> None:
        with self._condition:
            body, etag = self._body, self._etag
        assert body is not None and etag is not None
        now = self._clock()
        renewed = LockBody(
            home_environment=body.home_environment,
            state=LockState.HELD,
            holder=body.holder,
            acquired_at=body.acquired_at,
            renewed_at=now,
            lease_expires_at=now + self._lease,
            took_over_from=body.took_over_from,
        )
        try:
            new_etag = self._store.replace(renewed.as_bytes(), etag=etag)
        except LockObjectChanged:
            with self._condition:
                self._phase = _Phase.LOST
                self._condition.notify_all()
            logger.error("run lock: this runner's lease was taken over; it writes nothing more")
            raise RunLockLost from None
        with self._condition:
            self._body = renewed
            self._etag = new_etag

    def _renew_periodically(self) -> None:
        while not self._stop_renewing.wait(self._renew_every.total_seconds()):
            try:
                self.renew()
            except (RunLockLost, RunLockNotHeld):
                return
            except DomainError as unanswered:
                # The lease is still this runner's until it expires; the next renewal tries again.
                logger.warning(
                    "run lock: a renewal failed (%s); the next one tries again", type(unanswered).__name__
                )


# ------------------------------------------------------------------------------------------------
# Every command that writes to a bucket
# ------------------------------------------------------------------------------------------------


class BucketWriteGuard:
    """What every command that writes to an evidence bucket enters before it writes (ADR-0020 (4)).

    In bucket mode, the lease: taken, renewed in the background, and released when the command
    ends, however it ends. In local mode, the PM's ruling 3(a) of 2026-10-24: a command refuses a
    bucket that holds a lock object (:class:`BucketKeepsRunState`), and with no lock object, or no
    session to ask with, nothing changes. A dry run enters nothing: it reads and takes nothing.

    Args:
        mode: `caselist.run_state`.
        lock: Builds this command's lease, or `None` when the environment names no bucket.
    """

    def __init__(self, *, mode: RunStateMode, lock: Callable[[], BucketRunLock] | None) -> None:
        self._mode = mode
        self._lock = lock

    @property
    def bucket_mode(self) -> bool:
        return self._mode is RunStateMode.BUCKET and self._lock is not None

    @contextmanager
    def held(self, command: str) -> Generator[TakenLock | None]:
        """Hold what `command` needs to write to the bucket for the length of the block."""
        if self._lock is None:
            yield None
            return
        lock = self._lock()
        if self._mode is not RunStateMode.BUCKET:
            self.refuse_a_seeded_bucket(lock)
            yield None
            return
        taken = lock.take(command=command)
        lock.start_renewing()
        try:
            yield taken
        finally:
            lock.release()

    @staticmethod
    def refuse_a_seeded_bucket(lock: BucketRunLock) -> None:
        """Ruling 3(a): raise :class:`BucketKeepsRunState` when the bucket holds a lock object.

        A lock held for good by the move of the run's home is :class:`RunHomeMoved` instead
        (`v1-e40-t11`): bucket mode would be refused too, so the refusal says where the run lives.
        A store that cannot be asked (no session, most often) changes nothing: the command goes on
        as it did before, and meets the same store at its first bucket call.
        """
        try:
            seeded = lock.bucket_is_seeded()
        except StoreError as unasked:
            logger.info("run lock: not checked in local mode (%s)", type(unasked).__name__)
            return
        if seeded:
            moved = lock.home_moved()
            if moved is not None:
                raise moved
            raise BucketKeepsRunState
