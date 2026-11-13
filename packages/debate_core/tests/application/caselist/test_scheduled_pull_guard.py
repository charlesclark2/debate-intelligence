"""A scheduled pull refuses, before the lock, after a run the bucket's run log records within 24 hours.

`v1-e40-t44`, the PM's rulings of 2026-11-12:

1. the window is 24 hours;
2. only a pull started with `--scheduled` (which only the weekly schedule passes) is refused; a hand run
   never is;
3. a `caselist pull` run of mode `run` counts, whatever its outcome, unless it was refused by the run lock
   or by this guard; a `--publish-pending` pull does not;
4. the refusal is `RecentRunRecorded` (`RECENT_RUN_RECORDED`), recorded and announced as `RunLockHeld` is,
   and its notice and hint name the cure: "a hand run (the cloud-run runbook's Step 8) is never refused
   by this guard";
5. a run log that cannot be read refuses nothing: the run goes on to the lock, with a warning.

Each pull is `caselist pull` as the command runs it: :func:`run_pull` inside a real :class:`SyncRunMonitor`,
with the real bucket-mode bracket (:class:`BucketRun`) over a real :class:`BucketRunLock` and
:class:`RunState` on moto. The sync service is never built by a refused pull: building it is what reads
the token and calls OpenCaselist, and here it fails the test. The bucket's run log is written by the test
as a finished run's end writes it. Notifications go to a :class:`RecordingNotifier`. Every expected
sentence is written out by hand.
"""

from __future__ import annotations

import functools
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, NoReturn

import jsonschema
import pytest

from debate_core.application.caselist.bucket_run import BucketRun, latest_counting_run
from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.publish_service import withheld_manifest_reason
from debate_core.application.caselist.recent_run import RECENT_RUN_WINDOW, RecentRunRecorded
from debate_core.application.caselist.run_lock import (
    RUN_LOCK_KEY,
    BucketRunLock,
    BucketWriteGuard,
    HolderKind,
)
from debate_core.application.caselist.run_state import RunState, RunStateBundleMissing, state_key
from debate_core.application.caselist_sync import run_pull
from debate_core.application.errors import StoreAccessDenied
from debate_core.application.ports.notifier import Notification, RecordingNotifier
from debate_core.application.settings import RunStateMode
from debate_core.application.sync_runs import (
    SYNC_RUN_DETAILS_FILENAME,
    SYNC_RUN_LOG_FILENAME,
    RunMode,
    StageEntry,
    SyncRunMonitor,
    SyncRunOutcome,
    SyncRunRecord,
)
from debate_core.integrations.local import BLOB_DIRECTORY, FsEvidenceObjectStore
from debate_core.integrations.local.run_state_files import LocalRunStateFiles
from debate_core.integrations.s3 import S3EvidenceObjectStore
from debate_core.integrations.s3.run_lock_object import S3LockObject
from debate_core.testing.fakes.suppression import empty_suppression_list

from .retry_rule import the_commands_retry_rule

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

EARLIER_RUN: Final = "20261111T120101Z"
EARLIER_START: Final = datetime(2026, 11, 11, 12, 1, 1, tzinfo=UTC)
"""The Wednesday run of 2026-11-11, 06:01 America/Chicago, which took 113 minutes."""
NOW: Final = datetime(2026, 11, 11, 13, 59, 30, tzinfo=UTC)
"""A retry's second task, just after that run finished and released the lock."""
RUN_ID: Final = "20261111T135930Z"
CASELIST: Final = "testcl26"
AWS_LOGIN: Final = "aws sso login --profile debate-dev-evidence"
RUN_LOG_KEY: Final = state_key(SYNC_RUN_LOG_FILENAME)

WHERE: Final = f"Run {RUN_ID} (dev)"
CURE: Final = "a hand run (the cloud-run runbook's Step 8) is never refused by this guard"
"""The PM's words (ruling 4)."""

REFUSED_TITLE: Final = "caselist pull skipped: a run started within the last 24 hours"
REFUSED_MESSAGE: Final = (
    f"{WHERE}: the bucket's run log records run {EARLIER_RUN}, started 2026-11-11T12:01:01Z, within the "
    "last 24 hours, so this scheduled pull did nothing; that run records and announces its own outcome. "
    f"If the week still needs a run, {CURE}."
)
REFUSED_HINT: Final = (
    f"Run {EARLIER_RUN} started 2026-11-11T12:01:01Z, within the last 24 hours. If the week still needs a "
    f"run, {CURE}."
)
REFUSED_FIX: Final = "debate-research caselist runs"

STORED = Path(__file__).parent / "stored_run_records"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


def a_lock(client: S3Client, bucket: str, clock: Clock) -> BucketRunLock:
    return BucketRunLock(
        store=S3LockObject(bucket=bucket, key=RUN_LOCK_KEY, client=client),
        environment="dev",
        clock=clock,
        kind=HolderKind.CLOUD,
    )


@pytest.fixture
def seeded(s3_client: S3Client, evidence_bucket: str, clock: Clock) -> str:
    """Dev's bucket as the cutover left it: seeded, the lock free."""
    seed = a_lock(s3_client, evidence_bucket, clock)
    seed.create(command="caselist seed-run-state")
    seed.release()
    return evidence_bucket


def evidence_at(directory: Path) -> LocalEvidence:
    objects = FsEvidenceObjectStore(directory)
    blobs = FsEvidenceObjectStore(directory, subdirectory=BLOB_DIRECTORY.parent)
    return LocalEvidence(
        objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
    )


def a_record(
    started: datetime,
    *,
    outcome: SyncRunOutcome = SyncRunOutcome.COMPLETED,
    mode: RunMode = "run",
    error_class: str | None = None,
    stages: tuple[StageEntry, ...] = (),
) -> SyncRunRecord:
    """One run as the run log keeps it, started at `started` and 56 minutes long."""
    return SyncRunRecord(
        run_id=started.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ"),
        environment="dev",
        mode=mode,
        started_at=started,
        finished_at=started + timedelta(minutes=56),
        outcome=outcome,
        caselists=(CASELIST,) if mode == "run" else (),
        stages=stages,
        error_class=error_class,
    )


class RefusingTheRunLog(S3EvidenceObjectStore):
    """The bucket refusing the run log's read: a grant the role lost, or a bucket that did not answer."""

    async def get_file(self, key: str, destination: Path) -> Any:
        if key == RUN_LOG_KEY:
            raise StoreAccessDenied("GetObject", "the evidence bucket")
        return await super().get_file(key, destination)


class Task:
    """A cloud task's empty working copy, its run monitor, and the bracket around one pull."""

    def __init__(self, tmp_path: Path, client: S3Client, bucket: str, clock: Clock) -> None:
        self.data_dir = tmp_path / "data"
        self.client = client
        self.bucket = bucket
        self.clock = clock
        self.notifier = RecordingNotifier()
        self.raised: list[BaseException] = []
        self.store: Callable[[], S3EvidenceObjectStore] = lambda: S3EvidenceObjectStore(
            bucket=self.bucket, client=self.client
        )

    def the_bucket_records(self, *records: SyncRunRecord) -> None:
        """The bucket's run log, as a finished run's end saves it."""
        body = "".join(record.model_dump_json() + "\n" for record in records)
        self.client.put_object(Bucket=self.bucket, Key=RUN_LOG_KEY, Body=body.encode())

    def bracket(self) -> BucketRun:
        lock: Callable[[], BucketRunLock] = functools.partial(a_lock, self.client, self.bucket, self.clock)
        return BucketRun(
            guard=BucketWriteGuard(mode=RunStateMode.BUCKET, lock=lock),
            lock=lock,
            state=self._state,
            parsed_version="docx-test",
            now=self.clock,
        )

    def _state(self) -> RunState:
        return RunState(
            bucket=self.store(),
            files=LocalRunStateFiles(self.data_dir),
            local=evidence_at(self.data_dir),
            staged=evidence_at,
            withheld=lambda evidence: functools.partial(withheld_manifest_reason, evidence),
            suppression=empty_suppression_list(),
            data_dir=self.data_dir,
            clock=self.clock,
        )

    async def pull(self, *, scheduled: bool) -> None:
        """`caselist pull --caselist testcl26`, with `--scheduled` or by hand; what it raised is kept."""
        monitor = SyncRunMonitor(
            state_dir=self.data_dir,
            environment="dev",
            notifier=self.notifier,
            remote=self.store(),
            aws_login_command=AWS_LOGIN,
            clock=self.clock,
            **the_commands_retry_rule(),
        )
        try:
            await run_pull(
                never_built,
                [CASELIST],
                dry_run=False,
                publish_pending=False,
                monitor=lambda: monitor,
                progress=lambda _: None,
                bracket=self.bracket(),
                scheduled=scheduled,
            )
        except Exception as refused:
            self.raised.append(refused)

    def record(self) -> dict[str, Any]:
        [record] = [
            json.loads(line) for line in (self.data_dir / SYNC_RUN_LOG_FILENAME).read_text().splitlines()
        ]
        return record

    def details(self) -> dict[str, Any]:
        [details] = [
            json.loads(line) for line in (self.data_dir / SYNC_RUN_DETAILS_FILENAME).read_text().splitlines()
        ]
        return details

    def lock_versions(self) -> list[str]:
        listed = self.client.list_object_versions(Bucket=self.bucket, Prefix=RUN_LOCK_KEY)
        return [str(one.get("VersionId")) for one in listed.get("Versions", [])]

    def everything(self) -> dict[str, str]:
        listed = self.client.list_objects_v2(Bucket=self.bucket)
        return {str(one.get("Key")): str(one.get("ETag")) for one in listed.get("Contents", [])}


def never_built() -> NoReturn:
    raise AssertionError("a refused scheduled pull builds no sync service: it reads no token, calls nobody")


@pytest.fixture
def task(tmp_path: Path, s3_client: S3Client, seeded: str, clock: Clock) -> Task:
    return Task(tmp_path, s3_client, seeded, clock)


# ------------------------------------------------------------------------------------------------
# A scheduled pull after a recent run: refused before the lock, and announced as a lock refusal is
# ------------------------------------------------------------------------------------------------


async def test_a_scheduled_pull_guard_refuses_after_a_run_started_within_24_hours_before_the_lock(
    task: Task,
) -> None:
    task.the_bucket_records(a_record(EARLIER_START))
    lock_versions, bucket = task.lock_versions(), task.everything()

    await task.pull(scheduled=True)

    assert [type(one) for one in task.raised] == [RecentRunRecorded]
    assert task.lock_versions() == lock_versions, "the lock was never taken"
    assert task.everything() == bucket, "nothing was written to the bucket: its record stays on the task"
    assert not (task.data_dir / "manifests").exists(), "nothing was restored"


async def test_a_scheduled_pull_guard_refusal_is_recorded_and_announced_as_a_lock_refusal_is(
    task: Task,
) -> None:
    task.the_bucket_records(a_record(EARLIER_START))

    await task.pull(scheduled=True)

    record = task.record()
    assert (record["run_id"], record["outcome"], record["error_class"]) == (
        RUN_ID,
        "failed",
        "RecentRunRecorded",
    )
    assert record["stages"] == [] and record["caselists"] == [CASELIST]
    details = task.details()
    assert details["failure_codes"] == ["RECENT_RUN_RECORDED"]
    assert details["hint"] == REFUSED_HINT
    assert details["bucket_run"] is not None and details["bucket_run"]["took_over"] is None
    for name in ("record_schema_of_the_start_commit.json", "record_schema_of_the_cloud_image.json"):
        jsonschema.validate(record, json.loads((STORED / name).read_text()))

    [sent] = task.notifier.sent
    assert sent == Notification(
        title=REFUSED_TITLE,
        message=REFUSED_MESSAGE,
        fix_command=REFUSED_FIX,
        hint=REFUSED_HINT,
        subtitle=sent.subtitle,
    )
    assert sent.subtitle == WHERE


async def test_a_scheduled_pull_guard_refusal_names_the_cure_on_the_error_too(task: Task) -> None:
    task.the_bucket_records(a_record(EARLIER_START))

    await task.pull(scheduled=True)

    [refused] = task.raised
    assert isinstance(refused, RecentRunRecorded)
    assert (refused.run_id, refused.started_at) == (EARLIER_RUN, EARLIER_START)
    assert getattr(refused, "hint", None) == REFUSED_HINT


# ------------------------------------------------------------------------------------------------
# A hand run is never refused, and nothing else is either
# ------------------------------------------------------------------------------------------------


async def test_a_hand_pull_is_never_refused_by_the_guard_whatever_the_run_log_records(task: Task) -> None:
    task.the_bucket_records(a_record(NOW - timedelta(minutes=1)))
    lock_versions = task.lock_versions()

    await task.pull(scheduled=False)

    assert not any(isinstance(one, RecentRunRecorded) for one in task.raised)
    assert len(task.lock_versions()) > len(lock_versions), "it went on to take the lock"
    assert [type(one) for one in task.raised] == [RunStateBundleMissing], (
        "and to the restore, which this bucket, seeded with no bundle, refuses"
    )


async def test_a_scheduled_pull_guard_lets_a_run_through_after_24_hours(task: Task) -> None:
    task.the_bucket_records(a_record(NOW - RECENT_RUN_WINDOW))
    lock_versions = task.lock_versions()

    await task.pull(scheduled=True)

    assert [type(one) for one in task.raised] == [RunStateBundleMissing]
    assert len(task.lock_versions()) > len(lock_versions)


async def test_a_scheduled_pull_guard_lets_a_run_through_when_the_bucket_holds_no_run_log(task: Task) -> None:
    lock_versions = task.lock_versions()

    await task.pull(scheduled=True)

    assert [type(one) for one in task.raised] == [RunStateBundleMissing]
    assert len(task.lock_versions()) > len(lock_versions)


async def test_a_scheduled_pull_guard_goes_on_to_the_lock_when_the_run_log_cannot_be_read(
    task: Task, caplog: pytest.LogCaptureFixture
) -> None:
    task.the_bucket_records(a_record(EARLIER_START))
    task.store = lambda: RefusingTheRunLog(bucket=task.bucket, client=task.client)
    lock_versions = task.lock_versions()

    with caplog.at_level(logging.WARNING, logger="debate_core.application.caselist.bucket_run"):
        await task.pull(scheduled=True)

    assert not any(isinstance(one, RecentRunRecorded) for one in task.raised)
    assert len(task.lock_versions()) > len(lock_versions), "the lock decides, as before the guard"
    assert [
        record.getMessage()
        for record in caplog.records
        if record.name == "debate_core.application.caselist.bucket_run"
    ] == ["caselist pull: the bucket's run log could not be read (StoreAccessDenied); the run lock decides"]


# ------------------------------------------------------------------------------------------------
# Which recorded runs count (ruling 3), at the guard's own function
# ------------------------------------------------------------------------------------------------

AN_HOUR_AGO: Final = NOW - timedelta(hours=1)
FAILED_STAGE: Final = (StageEntry(stage="download", outcome="failed"),)


@pytest.mark.parametrize(
    ("record", "counts"),
    [
        (a_record(AN_HOUR_AGO), True),
        (a_record(AN_HOUR_AGO, outcome=SyncRunOutcome.NOTHING_NEW), True),
        (a_record(AN_HOUR_AGO, outcome=SyncRunOutcome.CAP_DEFERRED), True),
        (a_record(AN_HOUR_AGO, outcome=SyncRunOutcome.PUBLISH_PENDING), True),
        (a_record(AN_HOUR_AGO, outcome=SyncRunOutcome.INCOMPLETE), True),
        (a_record(AN_HOUR_AGO, outcome=SyncRunOutcome.FAILED, stages=FAILED_STAGE), True),
        (a_record(AN_HOUR_AGO, outcome=SyncRunOutcome.FAILED, error_class="CaselistAuthExpired"), True),
        (a_record(AN_HOUR_AGO, outcome=SyncRunOutcome.FAILED, error_class="RunTerminated"), True),
        (a_record(AN_HOUR_AGO, outcome=SyncRunOutcome.FAILED, error_class="RunLockLost"), True),
        (a_record(AN_HOUR_AGO, outcome=SyncRunOutcome.FAILED, error_class="RunLockHeld"), False),
        (a_record(AN_HOUR_AGO, outcome=SyncRunOutcome.FAILED, error_class="SyncRunInProgress"), False),
        (a_record(AN_HOUR_AGO, outcome=SyncRunOutcome.FAILED, error_class="RunHomeMoved"), False),
        (a_record(AN_HOUR_AGO, outcome=SyncRunOutcome.FAILED, error_class="RunLockWrongHome"), False),
        (a_record(AN_HOUR_AGO, outcome=SyncRunOutcome.FAILED, error_class="RecentRunRecorded"), False),
        (a_record(AN_HOUR_AGO, mode="publish_pending"), False),
        (a_record(NOW - RECENT_RUN_WINDOW + timedelta(seconds=1)), True),
        (a_record(NOW - RECENT_RUN_WINDOW), False),
        (a_record(NOW - timedelta(days=7)), False),
    ],
    ids=[
        "completed",
        "nothing_new",
        "cap_deferred",
        "publish_pending_outcome",
        "incomplete",
        "failed_at_a_stage",
        "stopped_on_an_expired_login",
        "stopped_by_sigterm",
        "lost_its_lease",
        "refused_by_another_runners_lease",
        "refused_by_the_local_lock",
        "refused_by_the_move_of_the_runs_home",
        "refused_by_a_lock_naming_another_home",
        "refused_by_this_guard",
        "a_publish_pending_pull",
        "a_second_inside_the_window",
        "exactly_24_hours_ago",
        "last_week",
    ],
)
def test_which_runs_count_for_the_scheduled_pull_guard(record: SyncRunRecord, counts: bool) -> None:
    assert latest_counting_run([record], now=NOW) == (record if counts else None)


def test_the_scheduled_pull_guard_names_the_latest_run_that_counts_not_a_later_refusal() -> None:
    counted = a_record(NOW - timedelta(hours=20))
    refused = a_record(AN_HOUR_AGO, outcome=SyncRunOutcome.FAILED, error_class="RunLockHeld")
    older = a_record(NOW - timedelta(hours=22))

    assert latest_counting_run([older, counted, refused], now=NOW) == counted
    assert latest_counting_run([refused], now=NOW) is None
    assert latest_counting_run([], now=NOW) is None
