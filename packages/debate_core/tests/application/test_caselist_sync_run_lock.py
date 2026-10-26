"""The bucket's run lock and its lease, against moto's S3 with conditional writes (`v1-e40-t04` ac3).

ADR-0020 (4): `reports/sync/run-lock.json`, held by `If-Match` and `If-None-Match` writes, a
30-minute lease renewed every 5 minutes and before every named-object write. Each test drives two
:class:`~debate_core.application.caselist.run_lock.BucketRunLock` runners over one versioned moto
bucket with a clock the test moves, and reads the lock object's versions to show what each runner
wrote, which for a refused runner is nothing.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Final

import boto3
import pytest
from botocore.exceptions import ClientError

from debate_core.application.caselist.run_lock import (
    CLOCK_SKEW_MARGIN,
    LEASE,
    RUN_LOCK_KEY,
    BucketRunLock,
    HolderKind,
    RunLockHeld,
    RunLockLost,
    RunLockNotHeld,
    RunLockUnreadable,
    RunLockWrongHome,
    RunStateNotSeeded,
    is_content_addressed,
)
from debate_core.application.errors import StoreAccessDenied
from debate_core.application.ports.run_lock import LockObject, LockObjectChanged, LockObjectStore
from debate_core.integrations.s3.fencing import fence_client
from debate_core.integrations.s3.run_lock_object import S3LockObject

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

START: Final = datetime(2026, 11, 4, 11, 0, 5, tzinfo=UTC)
BLOB_KEY: Final = "raw/caselist/hsld26/sha256/ab/cd/" + "abcd" * 16


class Clock:
    """Now, as the test says."""

    def __init__(self, now: datetime = START) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, by: timedelta) -> None:
        self.now += by


def lock_object(client: S3Client, bucket: str) -> S3LockObject:
    return S3LockObject(bucket=bucket, key=RUN_LOCK_KEY, client=client)


def runner(
    client: S3Client,
    bucket: str,
    clock: Clock,
    *,
    environment: str = "dev",
    kind: HolderKind = HolderKind.CLOUD,
) -> BucketRunLock:
    return BucketRunLock(store=lock_object(client, bucket), environment=environment, clock=clock, kind=kind)


def versions(client: S3Client, bucket: str) -> list[dict[str, Any]]:
    """Every version of the lock object, newest first, and every delete marker on it."""
    listed = client.list_object_versions(Bucket=bucket, Prefix=RUN_LOCK_KEY)
    return [*listed.get("Versions", []), *listed.get("DeleteMarkers", [])]  # pyright: ignore[reportReturnType]


def body(client: S3Client, bucket: str) -> dict[str, Any]:
    return json.loads(client.get_object(Bucket=bucket, Key=RUN_LOCK_KEY)["Body"].read())


def seeded(client: S3Client, bucket: str, clock: Clock) -> None:
    """A bucket the seed has run against: the lock created, held by the seed, then released."""
    seed = runner(client, bucket, clock, kind=HolderKind.MAC)
    seed.create(command="caselist seed-run-state")
    seed.release()


# ------------------------------------------------------------------------------------------------
# A bucket with no lock object is never started on
# ------------------------------------------------------------------------------------------------


def test_a_runner_refuses_a_bucket_with_no_lock_object_and_writes_nothing(
    s3_client: S3Client, evidence_bucket: str
) -> None:
    lock = runner(s3_client, evidence_bucket, Clock())

    with pytest.raises(RunStateNotSeeded) as refused:
        lock.take(command="caselist pull")

    assert RUN_LOCK_KEY in str(refused.value)
    assert "seed-run-state" in str(refused.value)
    assert s3_client.list_object_versions(Bucket=evidence_bucket).get("Versions") is None
    assert not lock.held


def test_a_read_refused_for_a_missing_key_is_absence_and_for_a_present_one_is_a_refusal() -> None:
    """Without `s3:ListBucket` on the key, S3 answers a missing key's `GetObject` with 403."""

    class Refusing:
        def __init__(self, listed: bool) -> None:
            self.listed = listed

        def get_object(self, **_: object) -> dict[str, Any]:
            raise ClientError({"Error": {"Code": "AccessDenied", "Message": "denied"}}, "GetObject")

        def list_objects_v2(self, **_: object) -> dict[str, Any]:
            return {"Contents": [{"Key": RUN_LOCK_KEY}]} if self.listed else {}

    absent = S3LockObject(bucket="b", key=RUN_LOCK_KEY, client=Refusing(listed=False))  # pyright: ignore[reportArgumentType]
    present = S3LockObject(bucket="b", key=RUN_LOCK_KEY, client=Refusing(listed=True))  # pyright: ignore[reportArgumentType]

    assert absent.read() is None
    with pytest.raises(StoreAccessDenied):
        present.read()


# ------------------------------------------------------------------------------------------------
# A live lease refuses a second runner; an expired one is taken over, and says so
# ------------------------------------------------------------------------------------------------


def test_a_second_runner_is_refused_while_the_lease_is_live_and_writes_nothing(
    s3_client: S3Client, evidence_bucket: str
) -> None:
    clock = Clock()
    seeded(s3_client, evidence_bucket, clock)
    first = runner(s3_client, evidence_bucket, clock)
    first.take(command="caselist pull")
    written = versions(s3_client, evidence_bucket)

    clock.advance(LEASE + CLOCK_SKEW_MARGIN)  # the last moment the lease is still live
    second = runner(s3_client, evidence_bucket, clock, kind=HolderKind.MAC)
    with pytest.raises(RunLockHeld) as refused:
        second.take(command="caselist pull")

    assert versions(s3_client, evidence_bucket) == written
    assert "cloud run 20261104T110005Z (`caselist pull`)" in str(refused.value)
    assert "its lease until 2026-11-04T11:30:05Z" in str(refused.value)
    assert not second.held
    with pytest.raises(RunLockNotHeld):
        second.before_write("manifests/hsld26/2026-11-04.jsonl", renew=True)


def test_an_expired_lease_is_taken_over_and_the_new_holder_says_so(
    s3_client: S3Client, evidence_bucket: str
) -> None:
    clock = Clock()
    seeded(s3_client, evidence_bucket, clock)
    first = runner(s3_client, evidence_bucket, clock, kind=HolderKind.MAC)
    first.take(command="caselist pull")

    clock.advance(LEASE + CLOCK_SKEW_MARGIN + timedelta(seconds=1))
    second = runner(s3_client, evidence_bucket, clock)
    taken = second.take(command="caselist pull")

    assert taken.took_over == (
        "took over the bucket's run lock from mac run 20261104T110005Z (`caselist pull`), "
        "whose lease expired at 2026-11-04T11:30:05Z"
    )
    now = body(s3_client, evidence_bucket)
    assert now["state"] == "held"
    assert now["holder"]["kind"] == "cloud"
    assert now["took_over_from"] == "20261104T110005Z"
    assert now["lease_expires_at"] == "2026-11-04T12:05:06Z"


def test_a_free_lock_is_taken_with_no_takeover(s3_client: S3Client, evidence_bucket: str) -> None:
    clock = Clock()
    seeded(s3_client, evidence_bucket, clock)

    taken = runner(s3_client, evidence_bucket, clock).take(command="tub index publish")

    assert taken.took_over is None
    assert body(s3_client, evidence_bucket)["took_over_from"] is None
    assert body(s3_client, evidence_bucket)["holder"]["command"] == "tub index publish"


def test_a_lock_naming_another_home_is_refused(s3_client: S3Client, evidence_bucket: str) -> None:
    clock = Clock()
    seeded(s3_client, evidence_bucket, clock)
    written = versions(s3_client, evidence_bucket)

    with pytest.raises(RunLockWrongHome) as refused:
        runner(s3_client, evidence_bucket, clock, environment="prod").take(command="caselist pull")

    assert "names dev as the run's home environment, and this is prod" in str(refused.value)
    assert versions(s3_client, evidence_bucket) == written


def test_a_lock_this_build_cannot_read_is_left_as_it_is(s3_client: S3Client, evidence_bucket: str) -> None:
    s3_client.put_object(Bucket=evidence_bucket, Key=RUN_LOCK_KEY, Body=b'{"format_version": 1}')
    written = versions(s3_client, evidence_bucket)

    with pytest.raises(RunLockUnreadable):
        runner(s3_client, evidence_bucket, Clock()).take(command="caselist pull")

    assert versions(s3_client, evidence_bucket) == written


def test_of_two_runners_that_read_the_same_version_only_the_first_writer_takes_it(
    s3_client: S3Client, evidence_bucket: str
) -> None:
    """Both read the free lock; the second's `If-Match` names a version that is no longer current."""
    clock = Clock()
    seeded(s3_client, evidence_bucket, clock)
    store = lock_object(s3_client, evidence_bucket)
    stale = store.read()
    assert stale is not None

    class ReadsTheStaleVersion:
        key = RUN_LOCK_KEY

        def read(self) -> LockObject:
            assert stale is not None
            return stale

        def create(self, body: bytes) -> str:
            return store.create(body)

        def replace(self, body: bytes, *, etag: str) -> str:
            return store.replace(body, etag=etag)

    runner(s3_client, evidence_bucket, clock).take(command="caselist pull")
    late = BucketRunLock(store=ReadsTheStaleVersion(), environment="dev", clock=clock, kind=HolderKind.MAC)

    with pytest.raises(RunLockHeld):
        late.take(command="caselist pull")
    assert body(s3_client, evidence_bucket)["holder"]["kind"] == "cloud"


def test_the_seed_cannot_create_a_lock_that_is_there(s3_client: S3Client, evidence_bucket: str) -> None:
    clock = Clock()
    seeded(s3_client, evidence_bucket, clock)

    with pytest.raises(LockObjectChanged):
        runner(s3_client, evidence_bucket, clock).create(command="caselist seed-run-state")


# ------------------------------------------------------------------------------------------------
# A runner whose lease was taken writes nothing more
# ------------------------------------------------------------------------------------------------


def test_a_runner_whose_lease_was_taken_over_loses_it_at_its_next_renewal_and_writes_nothing_more(
    s3_client: S3Client, evidence_bucket: str
) -> None:
    clock = Clock()
    seeded(s3_client, evidence_bucket, clock)
    sleeper = runner(s3_client, evidence_bucket, clock, kind=HolderKind.MAC)
    sleeper.take(command="caselist pull")
    clock.advance(LEASE + CLOCK_SKEW_MARGIN + timedelta(minutes=1))
    runner(s3_client, evidence_bucket, clock).take(command="caselist pull")
    taken_over = versions(s3_client, evidence_bucket)

    with pytest.raises(RunLockLost):
        sleeper.before_write("manifests/hsld26/2026-11-04.jsonl", renew=True)

    assert sleeper.lost
    for key in ("manifests/hsld26/2026-11-04.jsonl", BLOB_KEY):
        with pytest.raises(RunLockLost):
            sleeper.before_write(key, renew=False)
    sleeper.release()
    assert versions(s3_client, evidence_bucket) == taken_over
    assert body(s3_client, evidence_bucket)["holder"]["kind"] == "cloud"


def test_a_renewal_moves_the_lease_on_and_release_frees_it_without_deleting(
    s3_client: S3Client, evidence_bucket: str
) -> None:
    clock = Clock()
    seeded(s3_client, evidence_bucket, clock)
    lock = runner(s3_client, evidence_bucket, clock)
    lock.take(command="caselist pull")

    clock.advance(timedelta(minutes=5))
    lock.renew()
    assert body(s3_client, evidence_bucket)["lease_expires_at"] == "2026-11-04T11:35:05Z"
    assert body(s3_client, evidence_bucket)["renewed_at"] == "2026-11-04T11:05:05Z"

    lock.release()

    released = body(s3_client, evidence_bucket)
    assert released["state"] == "free"
    assert released["holder"] is None
    listed = s3_client.list_object_versions(Bucket=evidence_bucket, Prefix=RUN_LOCK_KEY)
    assert "DeleteMarkers" not in listed
    with pytest.raises(RunLockNotHeld):
        lock.before_write("manifests/hsld26/2026-11-04.jsonl", renew=True)


# ------------------------------------------------------------------------------------------------
# Fencing: a named write waits for a renewal that started after it asked
# ------------------------------------------------------------------------------------------------


class GatedStore:
    """A lock object in memory whose `replace` can be held at a gate, to put a renewal in flight."""

    key = RUN_LOCK_KEY

    def __init__(self) -> None:
        self.object: LockObject | None = None
        self.version = 0
        self.replaced = 0
        self.gate = threading.Event()
        self.gate.set()
        self.entered = threading.Event()

    def read(self) -> LockObject | None:
        return self.object

    def create(self, body: bytes) -> str:
        if self.object is not None:
            raise LockObjectChanged(self.key, "it is there")
        return self._write(body)

    def replace(self, body: bytes, *, etag: str) -> str:
        self.entered.set()
        self.gate.wait(timeout=10)
        if self.object is None or self.object.etag != etag:
            raise LockObjectChanged(self.key, "another runner changed it first")
        self.replaced += 1
        return self._write(body)

    def _write(self, body: bytes) -> str:
        self.version += 1
        self.object = LockObject(body=body, etag=f'"{self.version}"')
        return self.object.etag


def held_on(store: LockObjectStore, clock: Clock) -> BucketRunLock:
    lock = BucketRunLock(store=store, environment="dev", clock=clock, kind=HolderKind.CLOUD)
    lock.create(command="caselist pull")
    return lock


def in_thread(work: Callable[[], None]) -> tuple[threading.Thread, list[BaseException]]:
    failures: list[BaseException] = []

    def run() -> None:
        try:
            work()
        except BaseException as failed:  # noqa: BLE001 - reported to the test
            failures.append(failed)

    thread = threading.Thread(target=run)
    thread.start()
    return thread, failures


def test_a_write_that_arrives_during_an_in_flight_renewal_waits_for_the_next_one() -> None:
    """The PM's condition on shared renewals (ruling 5): the renewal in flight started before the
    write asked, so it does not count; the write goes ahead only after the next one is confirmed."""
    store = GatedStore()
    lock = held_on(store, Clock())
    store.gate.clear()
    store.entered.clear()
    in_flight, first_failures = in_thread(lock.renew)
    assert store.entered.wait(timeout=5)

    wrote = threading.Event()

    def write() -> None:
        lock.before_write("manifests/hsld26/2026-11-04.jsonl", renew=True)
        wrote.set()

    writer, writer_failures = in_thread(write)
    assert not wrote.wait(timeout=0.2), "the write went ahead on a renewal that started before it asked"
    assert store.replaced == 0

    store.gate.set()
    in_flight.join(timeout=5)
    writer.join(timeout=5)

    assert wrote.is_set()
    assert store.replaced == 2, "the write's own renewal is the second, started after it asked"
    assert first_failures == []
    assert writer_failures == []


def test_writers_waiting_together_share_one_renewal() -> None:
    store = GatedStore()
    lock = held_on(store, Clock())
    store.gate.clear()
    store.entered.clear()
    in_flight, _ = in_thread(lock.renew)
    assert store.entered.wait(timeout=5)
    writers = [
        in_thread(lambda: lock.before_write("manifests/hsld26/2026-11-04.jsonl", renew=True))
        for _ in range(5)
    ]

    store.gate.set()
    in_flight.join(timeout=5)
    for thread, failures in writers:
        thread.join(timeout=5)
        assert failures == []

    assert store.replaced == 2, "five writers that asked during one renewal share the next one"


def test_a_content_addressed_write_needs_a_held_lease_and_no_renewal() -> None:
    store = GatedStore()
    lock = held_on(store, Clock())

    lock.before_write(BLOB_KEY, renew=True)
    lock.before_write("manifests/hsld26/2026-11-04.jsonl", renew=False)

    assert store.replaced == 0
    assert is_content_addressed(BLOB_KEY)
    assert not is_content_addressed("manifests/hsld26/2026-11-04.jsonl")
    assert not is_content_addressed("parsed/hsld26/2026.10.20-docx-6/sources/" + "ab" * 32 + ".json")


def test_a_renewal_the_store_did_not_answer_lets_no_write_through_and_keeps_the_lease() -> None:
    class Unanswered(GatedStore):
        def replace(self, body: bytes, *, etag: str) -> str:
            raise StoreAccessDenied("lock", RUN_LOCK_KEY)

    lock = held_on(Unanswered(), Clock())

    with pytest.raises(StoreAccessDenied):
        lock.before_write("manifests/hsld26/2026-11-04.jsonl", renew=True)
    assert lock.held


def test_the_background_thread_renews_until_released() -> None:
    store = GatedStore()
    clock = Clock()
    lock = BucketRunLock(
        store=store,
        environment="dev",
        clock=clock,
        kind=HolderKind.CLOUD,
        renew_every=timedelta(milliseconds=20),
    )
    lock.create(command="caselist pull")
    lock.start_renewing()
    deadline = datetime.now(UTC) + timedelta(seconds=5)
    while store.replaced < 3 and datetime.now(UTC) < deadline:
        threading.Event().wait(0.01)
    lock.release()
    renewed = store.replaced

    threading.Event().wait(0.1)
    assert renewed >= 4, "three renewals at least, and the release"
    assert store.replaced == renewed, "nothing renews after the release"
    assert store.object is not None and json.loads(store.object.body)["state"] == "free"


def test_a_lease_taken_again_after_a_release_renews_again() -> None:
    """`caselist backfile-import` takes and releases one lock for each of its steps (`v1-e34-t34`)."""
    store = GatedStore()
    lock = BucketRunLock(
        store=store,
        environment="dev",
        clock=Clock(),
        kind=HolderKind.MAC,
        renew_every=timedelta(milliseconds=20),
    )
    lock.create(command="caselist backfile-import")
    lock.start_renewing()
    lock.release()

    lock.take(command="caselist backfile-import")
    lock.start_renewing()
    before = store.replaced
    deadline = datetime.now(UTC) + timedelta(seconds=5)
    while store.replaced < before + 2 and datetime.now(UTC) < deadline:
        threading.Event().wait(0.01)
    renewed_again = store.replaced - before
    lock.before_write("manifests/testcl25/full/2026-06-30.jsonl", renew=True)
    lock.release()

    assert renewed_again >= 2, "the second lease renews in the background, as the first did"
    assert store.object is not None and json.loads(store.object.body)["state"] == "free"


# ------------------------------------------------------------------------------------------------
# The fence on a real client: every write asks first
# ------------------------------------------------------------------------------------------------


def test_a_fenced_client_refuses_every_write_without_the_lease_and_lets_reads_through(
    s3_client: S3Client, evidence_bucket: str
) -> None:
    clock = Clock()
    seeded(s3_client, evidence_bucket, clock)
    s3_client.put_object(Bucket=evidence_bucket, Key="reports/sync/state/x.json", Body=b"{}")
    lock = runner(s3_client, evidence_bucket, clock)
    # The lock's own client is never fenced; a second client is, as the container builds them.
    fenced: S3Client = boto3.client("s3", region_name="us-east-1")  # pyright: ignore[reportUnknownMemberType]
    fence_client(fenced, lock)

    with pytest.raises(RunLockNotHeld):
        fenced.put_object(Bucket=evidence_bucket, Key="manifests/hsld26/2026-11-04.jsonl", Body=b"x")
    with pytest.raises(RunLockNotHeld):
        fenced.delete_object(Bucket=evidence_bucket, Key="reports/sync/state/x.json")
    with pytest.raises(RunLockNotHeld):
        fenced.put_object_tagging(
            Bucket=evidence_bucket, Key="reports/sync/state/x.json", Tagging={"TagSet": []}
        )
    assert fenced.get_object(Bucket=evidence_bucket, Key="reports/sync/state/x.json")["Body"].read() == b"{}"
    assert "manifests/hsld26/2026-11-04.jsonl" not in {
        item.get("Key") for item in fenced.list_objects_v2(Bucket=evidence_bucket).get("Contents", [])
    }

    lock.take(command="caselist publish")
    before = len(versions(s3_client, evidence_bucket))
    fenced.put_object(Bucket=evidence_bucket, Key="manifests/hsld26/2026-11-04.jsonl", Body=b"x")
    fenced.put_object(Bucket=evidence_bucket, Key=BLOB_KEY, Body=b"y")

    assert len(versions(s3_client, evidence_bucket)) == before + 1, "the manifest renewed; the blob did not"


def test_the_lease_is_thirty_minutes_renewed_every_five_with_five_minutes_for_clock_skew() -> None:
    """ADR-0020 (4)'s numbers, and the lease every command is built with unless a test says otherwise."""
    import inspect

    from debate_core.application.caselist.run_lock import RENEW_EVERY

    numbers = (LEASE, RENEW_EVERY, CLOCK_SKEW_MARGIN)
    assert numbers == (timedelta(minutes=30), timedelta(minutes=5), timedelta(minutes=5))
    defaults = {name: one.default for name, one in inspect.signature(BucketRunLock).parameters.items()}
    assert (defaults["lease"], defaults["renew_every"], defaults["skew_margin"]) == (
        LEASE,
        RENEW_EVERY,
        CLOCK_SKEW_MARGIN,
    )
