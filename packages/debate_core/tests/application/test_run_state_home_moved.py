"""Dev's run lock held for good when the weekly run's home moves to prod, against moto (`v1-e40-t11`).

ADR-0020 (7) step 3: `caselist move-run-home` takes dev's lock, then rewrites it held for good by a
holder of kind `moved` naming `home_environment: prod`; every take after it is refused, saying the run
now runs from prod; and only a lock a move holds is released, back to dev and free. Each test drives
:class:`~debate_core.application.caselist.run_home_move.RunHomeMove` and
:class:`~debate_core.application.caselist.run_lock.BucketRunLock` over one versioned moto bucket and
reads the lock object's versions to show what was written, which for a refusal is nothing.

The bucket here refuses an unconditional `PutObject` of the lock, as the real buckets do since
`v1-e40-t07`'s statement: a client hook answers one with `AccessDenied`. Another runner is played by a
second :class:`BucketRunLock`, or by a conditional write through the same lock object, never a plain put.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Final

import pytest
from botocore.exceptions import ClientError

from debate_core.application.caselist.run_home_move import RunHomeMove, RunHomeMoveRefused
from debate_core.application.caselist.run_lock import (
    CLOCK_SKEW_MARGIN,
    LEASE,
    RUN_LOCK_KEY,
    BucketRunLock,
    BucketWriteGuard,
    HolderKind,
    RunHomeMoved,
    RunHomeNotMoved,
    RunLockHeld,
    RunLockLost,
)
from debate_core.application.ports.run_lock import LockObject, LockObjectChanged
from debate_core.application.settings import RunStateMode
from debate_core.integrations.s3.run_lock_object import S3LockObject

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

START: Final = datetime(2026, 11, 4, 11, 0, 5, tzinfo=UTC)
BUILD: Final = "v1.1.0-dev.999"
OTHER_RUN: Final = "20261104T105000Z"

#: The lock as the move writes it, written out by hand from ADR-0020 (7) and the PM's brief: the new
#: home, held, by a `moved` holder that says when (its run id and `acquired_at`) and who (the kind of
#: runner and the build, never a person), with no lease to expire.
MOVED_AT_START: Final = {
    "format_version": 1,
    "home_environment": "prod",
    "state": "held",
    "holder": {
        "kind": "moved",
        "run_id": "20261104T110005Z",
        "task": None,
        "command": "caselist move-run-home",
        "by": "mac",
        "build": BUILD,
    },
    "acquired_at": "2026-11-04T11:00:05Z",
    "renewed_at": None,
    "lease_expires_at": None,
    "took_over_from": None,
}


class Clock:
    def __init__(self, now: datetime = START) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, by: timedelta) -> None:
        self.now += by


@pytest.fixture
def lock_puts(s3_client: S3Client) -> Iterator[list[dict[str, Any]]]:
    """Every `PutObject` of the lock, as sent; one without a condition is denied, as the bucket denies it."""
    sent: list[dict[str, Any]] = []

    def deny_an_unconditional_lock_write(params: dict[str, Any], **_: object) -> None:
        if params.get("Key") != RUN_LOCK_KEY:
            return
        sent.append(dict(params))
        if "IfMatch" not in params and "IfNoneMatch" not in params:
            raise ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "explicit deny: unconditional lock write"}},
                "PutObject",
            )

    s3_client.meta.events.register("provide-client-params.s3.PutObject", deny_an_unconditional_lock_write)
    yield sent
    s3_client.meta.events.unregister("provide-client-params.s3.PutObject", deny_an_unconditional_lock_write)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def bucket(s3_client: S3Client, evidence_bucket: str, lock_puts: list[dict[str, Any]], clock: Clock) -> str:
    """Dev's bucket as the cutover left it: seeded, the lock free."""
    seed = runner(s3_client, evidence_bucket, clock, kind=HolderKind.MAC)
    seed.create(command="caselist seed-run-state")
    seed.release()
    return evidence_bucket


def store(client: S3Client, bucket: str) -> S3LockObject:
    return S3LockObject(bucket=bucket, key=RUN_LOCK_KEY, client=client)


def runner(
    client: S3Client,
    bucket: str,
    clock: Clock,
    *,
    environment: str = "dev",
    kind: HolderKind = HolderKind.MAC,
    lock_object: Any = None,
) -> BucketRunLock:
    return BucketRunLock(
        store=lock_object or store(client, bucket), environment=environment, clock=clock, kind=kind
    )


def move_in(
    client: S3Client,
    bucket: str,
    clock: Clock,
    *,
    environment: str = "dev",
    lock_object: Any = None,
) -> RunHomeMove:
    return RunHomeMove(
        lock=lambda: runner(client, bucket, clock, environment=environment, lock_object=lock_object),
        environment=environment,
        build=BUILD,
    )


def bodies(client: S3Client, bucket: str) -> list[dict[str, Any]]:
    """Every version of the lock object's body, oldest first."""
    return [
        json.loads(
            client.get_object(Bucket=bucket, Key=RUN_LOCK_KEY, VersionId=version["VersionId"])["Body"].read()  # pyright: ignore[reportTypedDictNotRequiredAccess]
        )
        for version in versions_oldest_first(client, bucket)
    ]


def versions_oldest_first(client: S3Client, bucket: str) -> list[Any]:
    """The lock's versions, oldest first: S3 lists them newest first, and two can share a second."""
    return list(reversed(client.list_object_versions(Bucket=bucket, Prefix=RUN_LOCK_KEY).get("Versions", [])))


def current(client: S3Client, bucket: str) -> dict[str, Any]:
    return json.loads(client.get_object(Bucket=bucket, Key=RUN_LOCK_KEY)["Body"].read())


def version_ids(client: S3Client, bucket: str) -> list[str]:
    listed = client.list_object_versions(Bucket=bucket, Prefix=RUN_LOCK_KEY).get("Versions", [])
    return sorted(str(version.get("VersionId")) for version in listed)


class Interleaved:
    """The lock object, with another writer's conditional write landing just after a read or a write of it.

    What a lease lost between a take and the next write looks like to the runner that took it, or a
    lock changed between a release's read and its write: the version it holds is no longer the bucket's.
    """

    def __init__(
        self,
        inner: S3LockObject,
        *,
        other: Callable[[S3LockObject], None],
        after_read: int | None = None,
        after_write: int | None = None,
    ) -> None:
        self._inner = inner
        self._other = other
        self._after_read = after_read
        self._after_write = after_write
        self._reads = 0
        self._writes = 0
        self.key = inner.key

    def read(self) -> LockObject | None:
        found = self._inner.read()
        self._reads += 1
        if self._reads == self._after_read:
            self._other(self._inner)
        return found

    def create(self, body: bytes) -> str:
        return self._inner.create(body)

    def replace(self, body: bytes, *, etag: str) -> str:
        written = self._inner.replace(body, etag=etag)
        self._writes += 1
        if self._writes == self._after_write:
            self._other(self._inner)
        return written


def another_runner_writes(body: dict[str, Any]) -> Callable[[S3LockObject], None]:
    def write(lock_object: S3LockObject) -> None:
        found = lock_object.read()
        assert found is not None
        lock_object.replace(json.dumps(body).encode(), etag=found.etag)

    return write


def held_by_another_runner(now: datetime) -> dict[str, Any]:
    return {
        "format_version": 1,
        "home_environment": "dev",
        "state": "held",
        "holder": {"kind": "cloud", "run_id": OTHER_RUN, "task": "abc123", "command": "caselist pull"},
        "acquired_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "renewed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lease_expires_at": (now + LEASE).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "took_over_from": None,
    }


# ------------------------------------------------------------------------------------------------
# The move
# ------------------------------------------------------------------------------------------------


def test_the_move_takes_the_lock_then_holds_it_for_good_for_prod(
    s3_client: S3Client, bucket: str, clock: Clock
) -> None:
    report = move_in(s3_client, bucket, clock).move()

    assert current(s3_client, bucket) == MOVED_AT_START
    *_, taken, moved = bodies(s3_client, bucket)
    assert (taken["home_environment"], taken["state"], taken["holder"]["command"]) == (
        "dev",
        "held",
        "caselist move-run-home",
    ), "the holder is written under the lock: the move's own lease is the version before it"
    assert moved == MOVED_AT_START
    assert report.applied and not report.release
    assert report.found.state == "free"
    assert json.loads(report.written.as_bytes()) == MOVED_AT_START


def test_every_write_of_the_move_and_its_release_names_the_version_it_replaces(
    s3_client: S3Client, bucket: str, clock: Clock, lock_puts: list[dict[str, Any]]
) -> None:
    """The bucket's deny would refuse an unconditional one; each is an `If-Match` on the version before it."""
    seeded = len(lock_puts)
    move = move_in(s3_client, bucket, clock)

    move.move()
    clock.advance(timedelta(days=1))
    move.release()

    sent = lock_puts[seeded:]
    assert len(sent) == 3, "the move's take, its held-for-good write, and the release"
    assert all("IfMatch" in put and "IfNoneMatch" not in put for put in sent), sent
    etags = [str(version.get("ETag")) for version in versions_oldest_first(s3_client, bucket)]
    assert [put["IfMatch"] for put in sent] == etags[-4:-1]


def test_the_move_does_not_write_over_a_lock_that_changed_after_it_took_it(
    s3_client: S3Client, bucket: str, clock: Clock
) -> None:
    """Its lease taken over between its take and its write: the write is refused, the other holder stays."""
    taker = held_by_another_runner(START)
    racing = Interleaved(store(s3_client, bucket), other=another_runner_writes(taker), after_write=1)

    with pytest.raises(RunLockLost):
        move_in(s3_client, bucket, clock, lock_object=racing).move()

    assert current(s3_client, bucket) == taker
    assert all(
        body["holder"] is None or body["holder"]["kind"] != "moved" for body in bodies(s3_client, bucket)
    )


def test_the_move_is_refused_while_a_run_holds_the_lock_naming_the_holder_and_writes_nothing(
    s3_client: S3Client, bucket: str, clock: Clock
) -> None:
    runner(s3_client, bucket, clock, kind=HolderKind.CLOUD).take(command="caselist pull", run_id=OTHER_RUN)
    written = version_ids(s3_client, bucket)
    move = move_in(s3_client, bucket, clock)

    with pytest.raises(RunLockHeld) as planned:
        move.plan()
    with pytest.raises(RunLockHeld) as refused:
        move.move()

    for refusal in (planned.value, refused.value):
        assert f"cloud run {OTHER_RUN} (`caselist pull`) holds the bucket's run lock" in str(refusal)
        assert "its lease until 2026-11-04T11:30:05Z" in str(refusal)
    assert version_ids(s3_client, bucket) == written


def test_the_dry_run_writes_nothing_and_shows_the_holder_it_would_write(
    s3_client: S3Client, bucket: str, clock: Clock, lock_puts: list[dict[str, Any]]
) -> None:
    written = version_ids(s3_client, bucket)
    puts = len(lock_puts)

    report = move_in(s3_client, bucket, clock).plan()

    assert not report.applied
    assert json.loads(report.written.as_bytes()) == MOVED_AT_START
    assert report.found.state == "free" and report.found.home_environment == "dev"
    assert version_ids(s3_client, bucket) == written
    assert len(lock_puts) == puts


def test_a_second_move_is_refused_by_the_first(s3_client: S3Client, bucket: str, clock: Clock) -> None:
    move = move_in(s3_client, bucket, clock)
    move.move()
    written = version_ids(s3_client, bucket)

    with pytest.raises(RunHomeMoved):
        move.plan()
    with pytest.raises(RunHomeMoved):
        move.move()

    assert version_ids(s3_client, bucket) == written


def test_the_move_and_its_release_are_refused_in_prod_before_the_lock_is_read() -> None:
    def no_lock() -> BucketRunLock:
        raise AssertionError("the lock was asked for")

    move = RunHomeMove(lock=no_lock, environment="prod", build=BUILD)

    for step in (move.plan, move.move, move.plan_release, move.release):
        with pytest.raises(RunHomeMoveRefused) as refused:
            step()
        assert "moves from dev to prod, and this is prod" in str(refused.value)


# ------------------------------------------------------------------------------------------------
# After the move: every take is refused, naming the holder and where the run lives, for good
# ------------------------------------------------------------------------------------------------

LATER: Final = {
    "at once": timedelta(0),
    "a lease and its margin later": LEASE + CLOCK_SKEW_MARGIN + timedelta(seconds=1),
    "a year later": timedelta(days=365),
}


@pytest.mark.parametrize("later", sorted(LATER))
@pytest.mark.parametrize(
    ("environment", "kind"),
    [("dev", HolderKind.MAC), ("dev", HolderKind.CLOUD), ("prod", HolderKind.MAC)],
    ids=["a dev mac", "a dev cloud run", "prod pointed at dev's bucket"],
)
def test_after_the_move_every_take_is_refused_naming_the_holder_and_where_the_run_lives(
    s3_client: S3Client, bucket: str, clock: Clock, later: str, environment: str, kind: HolderKind
) -> None:
    move_in(s3_client, bucket, clock).move()
    written = version_ids(s3_client, bucket)
    clock.advance(LATER[later])

    with pytest.raises(RunHomeMoved) as refused:
        runner(s3_client, bucket, clock, environment=environment, kind=kind).take(command="caselist pull")

    assert str(refused.value) == (
        "the weekly run now runs from prod: this bucket's run lock (reports/sync/run-lock.json) is held "
        "for good since 2026-11-04T11:00:05Z by the move of the run's home to prod (`caselist "
        f"move-run-home`, from a mac, build {BUILD}), so this {environment} command did nothing"
    )
    assert "caselist move-run-home --release" in str(getattr(refused.value, "hint", ""))
    assert version_ids(s3_client, bucket) == written
    assert current(s3_client, bucket) == MOVED_AT_START


def test_after_the_move_a_dry_run_of_a_take_is_refused_the_same_way(
    s3_client: S3Client, bucket: str, clock: Clock
) -> None:
    move_in(s3_client, bucket, clock).move()

    with pytest.raises(RunHomeMoved):
        runner(s3_client, bucket, clock).check()


def test_after_the_move_a_local_mode_command_is_refused_naming_the_move(
    s3_client: S3Client, bucket: str, clock: Clock
) -> None:
    move_in(s3_client, bucket, clock).move()
    written = version_ids(s3_client, bucket)
    guard = BucketWriteGuard(mode=RunStateMode.LOCAL, lock=lambda: runner(s3_client, bucket, clock))

    with pytest.raises(RunHomeMoved), guard.held("caselist publish"):
        pytest.fail("the command ran")

    assert version_ids(s3_client, bucket) == written


def test_a_lock_a_move_does_not_hold_has_no_moved_refusal(
    s3_client: S3Client, bucket: str, clock: Clock
) -> None:
    lock = runner(s3_client, bucket, clock)
    assert lock.home_moved() is None
    lock.take(command="caselist pull")
    assert lock.home_moved() is None


# ------------------------------------------------------------------------------------------------
# The release
# ------------------------------------------------------------------------------------------------


def test_the_release_gives_the_lock_back_to_dev_free_and_a_dev_run_takes_it_again(
    s3_client: S3Client, bucket: str, clock: Clock
) -> None:
    move = move_in(s3_client, bucket, clock)
    move.move()
    clock.advance(timedelta(days=2))

    report = move.release()

    assert current(s3_client, bucket) == {
        "format_version": 1,
        "home_environment": "dev",
        "state": "free",
        "holder": None,
        "acquired_at": None,
        "renewed_at": "2026-11-06T11:00:05Z",
        "lease_expires_at": None,
        "took_over_from": None,
    }
    assert report.applied and report.release
    assert report.found.moved
    taken = runner(s3_client, bucket, clock, kind=HolderKind.CLOUD).take(command="caselist pull")
    assert taken.took_over is None


def test_the_releases_dry_run_writes_nothing(s3_client: S3Client, bucket: str, clock: Clock) -> None:
    move = move_in(s3_client, bucket, clock)
    move.move()
    written = version_ids(s3_client, bucket)

    report = move.plan_release()

    assert not report.applied and report.release
    assert report.found.moved
    assert (report.written.home_environment, report.written.state) == ("dev", "free")
    assert version_ids(s3_client, bucket) == written


@pytest.mark.parametrize("state", ["free", "held by a run"])
def test_the_release_is_refused_unless_a_move_holds_the_lock(
    s3_client: S3Client, bucket: str, clock: Clock, state: str
) -> None:
    if state != "free":
        runner(s3_client, bucket, clock, kind=HolderKind.CLOUD).take(command="caselist pull")
    written = version_ids(s3_client, bucket)
    move = move_in(s3_client, bucket, clock)

    with pytest.raises(RunHomeNotMoved):
        move.plan_release()
    with pytest.raises(RunHomeNotMoved) as refused:
        move.release()

    assert "is not held by a move of the run's home" in str(refused.value)
    assert version_ids(s3_client, bucket) == written


def test_the_release_does_not_write_over_a_lock_that_changed_after_it_read_it(
    s3_client: S3Client, bucket: str, clock: Clock
) -> None:
    move_in(s3_client, bucket, clock).move()
    clock.advance(timedelta(hours=1))
    rewritten = json.loads(json.dumps(MOVED_AT_START))
    rewritten["holder"]["build"] = "v1.1.0-dev.1000"
    racing = Interleaved(store(s3_client, bucket), other=another_runner_writes(rewritten), after_read=1)

    with pytest.raises(LockObjectChanged):
        move_in(s3_client, bucket, clock, lock_object=racing).release()

    assert current(s3_client, bucket) == rewritten
