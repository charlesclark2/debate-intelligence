"""A pull refused because the weekly run moved to prod is recorded skipped, with its own notice.

`v1-e40-t29`, from `v1-e40-t11`'s follow-up.

Since `v1-e40-t11`, once `caselist move-run-home` has held dev's run lock for good for prod, a `caselist
pull` is refused with `RUN_HOME_MOVED`. Its run was recorded as failed and announced with the generic
failed-run notice ("caselist pull failed: needs a person"), which reads like something broke. Nothing
did: the weekly run runs from prod now. So:

* its details say `skipped`, with `RUN_HOME_MOVED` as the reason, and no failure code;
* its notice is its own: the weekly run now runs from prod and this pull did nothing, naming no person,
  school or path;
* its **record** is the one every earlier build reads, unchanged: `failed`, `RunHomeMoved`. The record's
  outcome is a closed set an earlier build validates (`v1-e34-t19`), so `skipped` there would be a
  record those builds refuse, and a run that vanishes from their `caselist runs`.

A refusal because a runner holds the lock keeps today's record and wording, pinned here word for word,
and so does every other lock refusal: a lock naming another home, and local mode's refusal of a seeded
bucket.

Each run is `caselist pull` as the command runs it: :func:`run_pull` inside a real
:class:`SyncRunMonitor`, with the real bucket-mode bracket (:class:`BucketRun`) over a real
:class:`BucketRunLock` on moto, whose lock object `caselist move-run-home`'s own code
(:class:`RunHomeMove`) wrote with `v1-e40-t11`'s `moved` holder. Notifications go to a
:class:`RecordingNotifier`; none is posted. Every expected sentence is written out by hand.
"""

from __future__ import annotations

import functools
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, NoReturn

import jsonschema
import pytest

from debate_core.application import sync_runs
from debate_core.application.caselist.bucket_run import BucketRun
from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.publish_service import withheld_manifest_reason
from debate_core.application.caselist.run_home_move import RunHomeMove
from debate_core.application.caselist.run_lock import (
    RUN_LOCK_KEY,
    BucketKeepsRunState,
    BucketRunLock,
    BucketWriteGuard,
    HolderKind,
    RunHomeMoved,
    RunLockHeld,
    RunLockWrongHome,
)
from debate_core.application.caselist.run_state import RunState
from debate_core.application.caselist_sync import run_pull
from debate_core.application.ports.notifier import Notification, RecordingNotifier
from debate_core.application.settings import RunStateMode
from debate_core.application.sync_runs import (
    SYNC_RUN_DETAILS_FILENAME,
    SYNC_RUN_LOG_FILENAME,
    SyncRunDetails,
    SyncRunMonitor,
    SyncRunRecord,
    banner_words,
)
from debate_core.integrations.local import BLOB_DIRECTORY, FsEvidenceObjectStore
from debate_core.integrations.local.run_state_files import LocalRunStateFiles
from debate_core.integrations.s3 import S3EvidenceObjectStore
from debate_core.integrations.s3.run_lock_object import S3LockObject
from debate_core.testing.fakes.suppression import empty_suppression_list

from .retry_rule import a_retry_may_cure, the_commands_retry_rule

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

START: Final = datetime(2026, 11, 4, 11, 0, 5, tzinfo=UTC)
RUN_ID: Final = "20261104T110005Z"
OTHER_RUN: Final = "20261104T105005Z"
BUILD: Final = "v1.1.0-dev.999"
CASELIST: Final = "testcl26"
AWS_LOGIN: Final = "aws sso login --profile debate-dev-evidence"

WHERE: Final = f"Run {RUN_ID} (dev)"

MOVED_TITLE: Final = "caselist pull skipped: the weekly run moved to prod"
MOVED_MESSAGE: Final = (
    f"{WHERE} skipped: the weekly run now runs from prod, so this pull did nothing. Nothing here needs a "
    "person."
)
MOVED_FIX: Final = "none: prod's weekly cloud run records and announces its own runs"
"""The notice of a pull the move refused, in `v1-e34-t35`'s shape: the run, what it did, and the verdict."""

HELD_TITLE: Final = "caselist pull skipped: another was running"
HELD_MESSAGE: Final = (
    f"{WHERE}: Another runner held the bucket's run lock (cloud run {OTHER_RUN} (`caselist pull`), its "
    "lease until 2026-11-04T11:20:05Z), so this one did nothing. That run records and announces its own "
    "outcome."
)
HELD_FIX: Final = "debate-research caselist runs"
"""A pull refused by a runner's live lease, word for word as `v1-e40-t04` wrote it and as it stays."""

PERSON_TITLE: Final = "caselist pull failed: needs a person"
"""Every other lock refusal's title, as before: a failed run a person should look at."""

STORED = Path(__file__).parent / "stored_run_records"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


def a_lock(
    client: S3Client,
    bucket: str,
    clock: Clock,
    *,
    environment: str = "dev",
    kind: HolderKind = HolderKind.MAC,
) -> BucketRunLock:
    return BucketRunLock(
        store=S3LockObject(bucket=bucket, key=RUN_LOCK_KEY, client=client),
        environment=environment,
        clock=clock,
        kind=kind,
    )


@pytest.fixture
def seeded(s3_client: S3Client, evidence_bucket: str, clock: Clock) -> str:
    """Dev's bucket as the cutover left it: seeded, the lock free."""
    seed = a_lock(s3_client, evidence_bucket, clock)
    seed.create(command="caselist seed-run-state")
    seed.release()
    return evidence_bucket


def the_run_home_moved(client: S3Client, bucket: str, clock: Clock) -> None:
    """`caselist move-run-home --execute`, by its own code: dev's lock held for good by a `moved` holder."""
    RunHomeMove(lock=lambda: a_lock(client, bucket, clock), environment="dev", build=BUILD).move()
    moved = json.loads(client.get_object(Bucket=bucket, Key=RUN_LOCK_KEY)["Body"].read())
    assert (moved["home_environment"], moved["state"], moved["holder"]["kind"]) == ("prod", "held", "moved")


def evidence_at(directory: Path) -> LocalEvidence:
    objects = FsEvidenceObjectStore(directory)
    blobs = FsEvidenceObjectStore(directory, subdirectory=BLOB_DIRECTORY.parent)
    return LocalEvidence(
        objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
    )


class Mac:
    """This Mac's dev installation: its data directory, its run monitor and the bracket around a pull."""

    def __init__(self, tmp_path: Path, client: S3Client, bucket: str, clock: Clock) -> None:
        self.data_dir = tmp_path / "data"
        self.client = client
        self.bucket = bucket
        self.clock = clock
        self.notifier = RecordingNotifier()
        self.raised: list[BaseException] = []

    def bracket(self, mode: RunStateMode) -> BucketRun:
        lock: Callable[[], BucketRunLock] = functools.partial(a_lock, self.client, self.bucket, self.clock)
        return BucketRun(
            guard=BucketWriteGuard(mode=mode, lock=lock),
            lock=lock,
            state=self._state,
            parsed_version="docx-test",
        )

    def _state(self) -> RunState:
        return RunState(
            bucket=S3EvidenceObjectStore(bucket=self.bucket, client=self.client),
            files=LocalRunStateFiles(self.data_dir),
            local=evidence_at(self.data_dir),
            staged=evidence_at,
            withheld=lambda evidence: functools.partial(withheld_manifest_reason, evidence),
            suppression=empty_suppression_list(),
            data_dir=self.data_dir,
            clock=self.clock,
        )

    async def pull(self, mode: RunStateMode = RunStateMode.BUCKET) -> None:
        """`caselist pull --caselist testcl26` as the command runs it, the refusal kept."""
        monitor = SyncRunMonitor(
            state_dir=self.data_dir,
            environment="dev",
            notifier=self.notifier,
            remote=S3EvidenceObjectStore(bucket=self.bucket, client=self.client),
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
                bracket=self.bracket(mode),
            )
        except Exception as refused:
            self.raised.append(refused)

    def record(self) -> dict[str, Any]:
        [record] = [
            json.loads(line) for line in (self.data_dir / SYNC_RUN_LOG_FILENAME).read_text().splitlines()
        ]
        return record

    def details(self) -> dict[str, Any]:
        lines = (self.data_dir / SYNC_RUN_DETAILS_FILENAME).read_text().splitlines()
        [details] = [json.loads(line) for line in lines]
        return details

    def the_one_notification(self) -> Notification:
        [sent] = self.notifier.sent
        return sent

    def lock_versions(self) -> list[str]:
        listed = self.client.list_object_versions(Bucket=self.bucket, Prefix=RUN_LOCK_KEY)
        return [str(one.get("VersionId")) for one in listed.get("Versions", [])]

    def keys_in_the_bucket(self) -> list[str]:
        listed = self.client.list_objects_v2(Bucket=self.bucket)
        return [str(one.get("Key")) for one in listed.get("Contents", [])]


def never_built() -> NoReturn:
    raise AssertionError("a pull the lock refused builds no sync service: it fetches nothing")


@pytest.fixture
def mac(tmp_path: Path, s3_client: S3Client, seeded: str, clock: Clock) -> Mac:
    return Mac(tmp_path, s3_client, seeded, clock)


def assert_names_no_person_school_or_path(notification: Notification) -> None:
    """Nothing in what the banner shows is a path, the lock's key, the holder's runner or build."""
    shown = " ".join(
        one or "" for one in (notification.title, notification.subtitle, notification.text, notification.body)
    )
    assert "/" not in shown and "\\" not in shown and "~" not in shown, shown
    assert RUN_LOCK_KEY not in shown and "run-lock" not in shown, shown
    assert BUILD not in shown and "from a mac" not in shown, "the move's holder is not named: " + shown


# ------------------------------------------------------------------------------------------------
# A pull the move refused: skipped, with its own notice
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("mode", [RunStateMode.BUCKET, RunStateMode.LOCAL], ids=["bucket_mode", "local_mode"])
async def test_a_pull_after_the_run_home_moved_is_recorded_skipped_with_its_own_notice(
    mac: Mac, mode: RunStateMode
) -> None:
    the_run_home_moved(mac.client, mac.bucket, mac.clock)
    versions = mac.lock_versions()

    await mac.pull(mode)

    assert [type(one) for one in mac.raised] == [RunHomeMoved]
    details = mac.details()
    assert details.get("skipped") == "RUN_HOME_MOVED"
    assert details["failure_codes"] == [], "a skipped run failed on nothing"
    assert details["hint"] is None
    assert (details["bucket_run"] is not None) is (mode is RunStateMode.BUCKET)

    notification = mac.the_one_notification()
    assert notification.title == MOVED_TITLE
    assert notification.message == MOVED_MESSAGE
    assert notification.fix_command == MOVED_FIX
    assert notification.hint is None
    assert notification.subtitle == WHERE
    assert_names_no_person_school_or_path(notification)

    assert mac.lock_versions() == versions, "the moved lock is left as the move wrote it"
    assert mac.keys_in_the_bucket() == [RUN_LOCK_KEY], (
        "its record, its details and its state stay on this machine, as every lock refusal's"
    )


async def test_a_pull_after_the_run_home_moved_keeps_the_record_every_earlier_build_reads(mac: Mac) -> None:
    the_run_home_moved(mac.client, mac.bucket, mac.clock)

    await mac.pull()

    record = mac.record()
    assert (record["outcome"], record["error_class"]) == ("failed", "RunHomeMoved")
    assert record["stages"] == [] and record["caselists"] == [CASELIST]
    for name in ("record_schema_of_the_start_commit.json", "record_schema_of_the_cloud_image.json"):
        jsonschema.validate(record, json.loads((STORED / name).read_text()))
    details = mac.details()
    for name in (
        "details_schema_before_parsed_stores_owed.json",
        "details_schema_of_the_macs_installed_build.json",
    ):
        jsonschema.validate(details, json.loads((STORED / name).read_text()))


async def test_a_pull_after_the_run_home_moved_reads_back_as_skipped_beside_its_banner(mac: Mac) -> None:
    the_run_home_moved(mac.client, mac.bucket, mac.clock)

    await mac.pull()

    record = SyncRunRecord.model_validate(mac.record())
    details = SyncRunDetails.model_validate(mac.details())
    assert details.model_dump(mode="json").get("skipped") == "RUN_HOME_MOVED"
    assert banner_words(record, details, may_succeed_on_retry=a_retry_may_cure) == "skipped"


def test_details_with_no_skip_write_no_skipped_key_so_every_other_run_reads_as_before_run_home_moved() -> (
    None
):
    """The key is written only on a skipped run: every other run's details are byte for byte as before."""
    assert "skipped" not in SyncRunDetails(run_id=RUN_ID).model_dump(mode="json")
    assert "skipped" not in json.loads(SyncRunDetails(run_id=RUN_ID).model_dump_json())
    assert (
        SyncRunDetails.model_validate({"run_id": RUN_ID, "skipped": "RUN_HOME_MOVED"})
        .model_dump(mode="json")
        .get("skipped")
        == "RUN_HOME_MOVED"
    ), "and read back where it is"


# ------------------------------------------------------------------------------------------------
# Every other lock refusal: today's record and wording
# ------------------------------------------------------------------------------------------------


async def test_a_pull_a_runners_hold_refused_keeps_its_record_and_wording_not_run_home_moved(
    mac: Mac,
) -> None:
    mac.clock.now = START - timedelta(minutes=10)
    a_lock(mac.client, mac.bucket, mac.clock, kind=HolderKind.CLOUD).take(command="caselist pull")
    mac.clock.now = START

    await mac.pull()

    assert [type(one) for one in mac.raised] == [RunLockHeld]
    record = mac.record()
    assert (record["outcome"], record["error_class"]) == ("failed", "RunLockHeld")
    details = mac.details()
    assert "skipped" not in details
    assert details["failure_codes"] == ["RUN_LOCK_HELD"]
    notification = mac.the_one_notification()
    assert (notification.title, notification.message, notification.fix_command, notification.hint) == (
        HELD_TITLE,
        HELD_MESSAGE,
        HELD_FIX,
        None,
    )
    assert (
        banner_words(
            SyncRunRecord.model_validate(record),
            SyncRunDetails.model_validate(details),
            may_succeed_on_retry=a_retry_may_cure,
        )
        == "skipped"
    ), "the banner's word, as `v1-e34-t26` gave it"


async def test_a_pull_a_lock_naming_another_home_refused_is_failed_not_skipped_as_run_home_moved_is(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str, clock: Clock
) -> None:
    a_lock(s3_client, evidence_bucket, clock, environment="prod").create(command="caselist seed-run-state")
    mac = Mac(tmp_path, s3_client, evidence_bucket, clock)

    await mac.pull()

    assert [type(one) for one in mac.raised] == [RunLockWrongHome]
    assert (mac.record()["outcome"], mac.record()["error_class"]) == ("failed", "RunLockWrongHome")
    assert "skipped" not in mac.details()
    assert mac.details()["failure_codes"] == ["RUN_LOCK_WRONG_HOME"]
    assert mac.the_one_notification().title == PERSON_TITLE


async def test_a_local_mode_pull_refused_by_a_seeded_bucket_is_failed_not_skipped_as_run_home_moved_is(
    mac: Mac,
) -> None:
    await mac.pull(RunStateMode.LOCAL)

    assert [type(one) for one in mac.raised] == [BucketKeepsRunState]
    assert (mac.record()["outcome"], mac.record()["error_class"]) == ("failed", "BucketKeepsRunState")
    assert "skipped" not in mac.details()
    assert mac.the_one_notification().title == PERSON_TITLE


# ------------------------------------------------------------------------------------------------
# The runbook says what the banner says
# ------------------------------------------------------------------------------------------------

RUNBOOK = Path(__file__).resolve().parents[5] / "docs" / "runbooks" / "caselist-scheduled-sync.md"


def test_the_runbook_quotes_the_notice_of_a_pull_after_the_run_home_moved_word_for_word() -> None:
    section = RUNBOOK.read_text(encoding="utf-8").split("\n## What a notification says\n", 1)[1]
    section = " ".join(section.split("\n## ", 1)[0].split())

    assert (sync_runs.RUN_HOME_MOVED_TITLE, sync_runs.RUN_HOME_MOVED_FIX) == (MOVED_TITLE, MOVED_FIX)
    assert f"{WHERE} {sync_runs.RUN_HOME_MOVED_NOTICE}" == MOVED_MESSAGE
    for wording in (MOVED_TITLE, MOVED_MESSAGE, MOVED_FIX, "skipped (RUN_HOME_MOVED)", "none (skipped)"):
        assert " ".join(wording.split()) in section, wording
