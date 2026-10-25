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
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Final

from debate_core.application.errors import DomainError
from debate_core.application.ports.run_lock import LockObjectChanged, LockObjectStore

__all__ = [
    "CLOCK_SKEW_MARGIN",
    "LEASE",
    "LOCK_FORMAT_VERSION",
    "RENEW_EVERY",
    "RUN_LOCK_KEY",
    "BucketKeepsRunState",
    "BucketRunLock",
    "HolderKind",
    "LockBody",
    "LockHolder",
    "LockState",
    "RunLockHeld",
    "RunLockLost",
    "RunLockNotHeld",
    "RunLockUnreadable",
    "RunLockWrongHome",
    "RunStateNotSeeded",
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
    """Who holds the lock. `moved` is reserved for `v1-e40-t06`'s move of the home to prod."""

    CLOUD = "cloud"
    MAC = "mac"
    MOVED = "moved"


@dataclass(frozen=True, slots=True)
class LockHolder:
    kind: str
    run_id: str
    command: str
    task: str | None = None

    def as_json(self) -> dict[str, object]:
        return {"kind": self.kind, "run_id": self.run_id, "task": self.task, "command": self.command}

    def described(self) -> str:
        return f"{self.kind} run {self.run_id} (`{self.command}`)"


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
            parsed_holder = LockHolder(
                kind=str(named.get("kind")),
                run_id=str(named.get("run_id")),
                command=str(named.get("command")),
                task=task if isinstance(task, str) else None,
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
    from an older copy and download against a ledger the bucket does not share.
    """

    def __init__(self) -> None:
        super().__init__(
            f"this bucket keeps its run state (it holds {RUN_LOCK_KEY}); set caselist.run_state = bucket"
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

        Raises :class:`RunStateNotSeeded`, :class:`RunLockUnreadable`, :class:`RunLockWrongHome` or
        :class:`RunLockHeld`, each before anything is written.
        """
        found = self._store.read()
        if found is None:
            raise RunStateNotSeeded
        current = LockBody.from_bytes(found.body)
        if current.home_environment != self._environment:
            raise RunLockWrongHome(home=current.home_environment, environment=self._environment)
        now = self._clock()
        previous: LockHolder | None = None
        if current.state is LockState.HELD:
            if not self._expired(current, now):
                raise RunLockHeld(holder=current.holder, lease_expires_at=current.lease_expires_at)
            previous = current.holder
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

    def start_renewing(self) -> None:
        """Renew every :data:`RENEW_EVERY` in a daemon thread until :meth:`release`."""
        if self._renewer is not None:
            return
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

    def _expired(self, body: LockBody, now: datetime) -> bool:
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
