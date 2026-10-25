"""A pull that cannot build its bucket still records itself and says so (`v1-e34-t22`).

`storage.s3.aws_profile` names a profile this machine's AWS config does not define. boto3 refuses to
build a session for it, so the bucket's adapter cannot be built (`v1-e29-t07`). The run monitor
publishes run records through that same adapter, and it used to be handed the adapter built: so the
monitor could not be built either, and the weekly agent recorded no run and sent no notification.
Only launchd's exit code showed it.

The monitor is now handed the bucket to build when a record is first published. A refusal to build
it is then one more thing the run failed on:

* the record is written on this machine, as it is for any run that stopped on an error, with the
  run's details beside it carrying `STORE_PROFILE_NOT_CONFIGURED` and the fix, which names the
  setting;
* one notification says a person should look, with that fix;
* the record stays owed to the bucket, and the next run that can build the bucket publishes it with
  its details.

The run is `run_record_scenarios.World.pull_with_no_bucket`, which is also the run the older
build's code was given for the stored records. Through the real composition root, with boto3
refusing a real session, it is `packages/debate_cli/tests/test_pull_refused_before_the_bucket_is_built.py`.
Every expected sentence here is written out by hand.
"""

from __future__ import annotations

import inspect
import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from tests.fixtures.caselist.build_synthetic_archives import build_snapshot_zips

from debate_core.application import errors
from debate_core.application.caselist_sync import CaselistSyncService, run_pull
from debate_core.application.ports.evidence_store import EvidenceObjectStore
from debate_core.application.ports.notifier import RecordingNotifier
from debate_core.application.sync_runs import SYNC_RUN_LOG_FILENAME, SyncRunLog, SyncRunMonitor
from debate_core.integrations.s3 import S3EvidenceObjectStore, build_s3_client

from . import test_inbox_retention as inbox_retention
from .retry_rule import the_commands_retry_rule
from .run_record_scenarios import (
    AWS_LOGIN,
    MISSPELT_PROFILE,
    PROFILE_SETTING,
    RECORDS_PREFIX,
    SECOND_RUN,
    World,
    a_refusal_to_start_published_by_the_next_run,
    the_adapters_refusal_of_a_session,
)
from .test_inbox_retention import CASELIST, WEEK_1, ExpiredBucket, FakeSource, Installation

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

FIRST_RUN_ID = "20260916T060000Z"
SECOND_RUN_ID = "20260923T060000Z"
THIRD_RUN = datetime(2026, 9, 30, 6, 0, tzinfo=UTC)
THIRD_RUN_ID = "20260930T060000Z"

DETAILS_FILE = "caselist-sync-run-details.jsonl"
DETAILS_PREFIX = "reports/sync-run-details/"
OWED_FILE = "caselist-sync-records-pending.json"
"""The three names as the runbook gives them, written out and not imported."""

PERSON_TITLE = "caselist pull failed: needs a person"
PERSON = "A person should look: at least one failure here will be the same on the next scheduled run."

THE_RECORDED_MESSAGE = (
    "AWS profile 'debate-dev-evidence-typo', named by storage.s3.aws_profile, is not defined in this "
    "machine's AWS config: set storage.s3.aws_profile to a profile this machine's AWS config defines, "
    "or add the profile to it: docs/runbooks/evidence-store.md lists the evidence profiles and how "
    "they are added. It is not an expired session, and logging in changes nothing"
)
"""The error's own sentence as a record keeps it, the runbook it points at included. Until
`v1-e34-t23` the record's redaction took that runbook for a path (`v1-e34-t19`'s Follow-up 9)."""

THE_FIX = (
    "The bucket was never reached: set storage.s3.aws_profile to a profile this machine's AWS config "
    "defines, or add the profile to it: docs/runbooks/evidence-store.md lists the evidence profiles "
    "and how they are added. It is not an expired session, and logging in changes nothing."
)
"""The adapter's fix for a profile the AWS config does not define (`v1-e29-t07`), as a run that
stopped on it gives it: in the run's details and on its notification."""

A_PATH_ON_A_MACHINE = re.compile(r"(?:^|[\s(\"'`])(?:~/|/)\S")
AN_ACCOUNT_OR_AN_ADDRESS = re.compile(r"\b\d{12}\b|arn:|https?://|awsapps\.com")
"""An account id, a role's full identifier, or an address a session is started at."""


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def world(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str, monkeypatch: pytest.MonkeyPatch
) -> World:
    def set_clock(moment: datetime) -> None:
        monkeypatch.setattr(inbox_retention, "RUN_CLOCK", moment)

    return World(
        installation=Installation(
            data_dir=tmp_path / "evidence",
            bucket=S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client),
            archives=build_snapshot_zips(tmp_path / "published"),
        ),
        s3_client=s3_client,
        bucket_name=evidence_bucket,
        scratch=tmp_path,
        set_clock=set_clock,
    )


def run_log(world: World) -> list[dict[str, Any]]:
    return [json.loads(line) for line in world.run_log().decode("utf-8").splitlines()]


def details_kept(world: World) -> list[dict[str, Any]]:
    kept = (world.installation.data_dir / DETAILS_FILE).read_text("utf-8")
    return [json.loads(line) for line in kept.splitlines()]


def owed(world: World) -> list[str] | None:
    """The run ids whose record the bucket does not have yet, or `None` when the file is gone."""
    file = world.installation.data_dir / OWED_FILE
    if not file.exists():
        return None
    listed: list[str] = json.loads(file.read_text("utf-8"))["run_ids"]
    return listed


def in_the_bucket(world: World, prefix: str) -> dict[str, Any]:
    listed = world.s3_client.list_objects_v2(Bucket=world.bucket_name, Prefix=prefix).get("Contents", [])
    return {
        str(one.get("Key")): json.loads(
            world.s3_client.get_object(Bucket=world.bucket_name, Key=str(one.get("Key")))["Body"].read()
        )
        for one in listed
    }


def monitor_that_builds(world: World, build: Any, **more: Any) -> SyncRunMonitor:
    """A monitor of this build, handed its bucket to build. The keyword is looked up when a test
    runs, so that a source without it fails the test and not the collection of this file."""
    keywords: dict[str, Any] = {
        "state_dir": world.installation.data_dir,
        "environment": "dev",
        "notifier": world.notifier,
        "remote": None,
        "build_remote": build,
        "aws_login_command": AWS_LOGIN,
        "clock": lambda: inbox_retention.RUN_CLOCK,
        **the_commands_retry_rule(),
        **more,
    }
    return SyncRunMonitor(**keywords)


async def pull_through(world: World, monitor: SyncRunMonitor, service: Any) -> None:
    try:
        world.pulled.append(
            await run_pull(
                service,
                [CASELIST],
                dry_run=False,
                publish_pending=False,
                monitor=lambda: monitor,
                progress=lambda _: None,
            )
        )
    except Exception as stopped:
        world.raised.append(stopped)


# ------------------------------------------------------------------------------------------------
# ac1: recorded here, and announced once
# ------------------------------------------------------------------------------------------------


def test_this_builds_monitor_is_handed_its_bucket_to_build() -> None:
    """The scenario below gives an older build's monitor a built bucket that refuses every call,
    because that is all it takes. This build's is given the bucket to build, which is the path the
    composition root uses, and the rest of this file is about that path only if this holds."""
    assert "build_remote" in inspect.signature(SyncRunMonitor).parameters


async def test_a_pull_whose_bucket_cannot_be_built_is_recorded_on_this_machine_as_failed(
    world: World,
) -> None:
    await world.pull_with_no_bucket()

    [stopped] = world.raised
    assert type(stopped).__name__ == "StoreProfileNotConfigured", "the command still ends on the refusal"
    [record] = run_log(world)
    assert record == {
        "schema_version": 1,
        "run_id": FIRST_RUN_ID,
        "environment": "dev",
        "mode": "run",
        "started_at": "2026-09-16T06:00:00Z",
        "finished_at": "2026-09-16T06:00:00Z",
        "outcome": "failed",
        "caselists": ["testcl26"],
        "archives_seen": 0,
        "archives_wanted": 0,
        "archives_downloaded": 0,
        "archives_deferred": 0,
        "deferred_by_caselist": {},
        "backlog_carried": None,
        "backlog_growing": [],
        "openev_downloaded": 0,
        "files_imported": 0,
        "snapshots_imported": [],
        "objects_published": 0,
        "pending_publish": [],
        "stages": [],
        "error_class": "StoreProfileNotConfigured",
        "error_message": THE_RECORDED_MESSAGE,
    }


async def test_its_details_carry_the_code_and_the_fix_which_names_the_setting(world: World) -> None:
    await world.pull_with_no_bucket()

    assert details_kept(world) == [
        {
            "schema_version": 1,
            "run_id": FIRST_RUN_ID,
            "stages": [],
            "failure_codes": ["STORE_PROFILE_NOT_CONFIGURED"],
            "hint": THE_FIX,
            "parse": None,
            "search_index": None,
            "held_by_request": {},
            "manifests_published": 0,
            # A run refused before any stage has no stage to time and read no volume (`v1-e40-t03`).
            "stage_times": [],
            "data_volume": None,
        }
    ]
    assert PROFILE_SETTING in THE_FIX


async def test_one_notification_says_a_person_should_look_and_carries_the_adapters_fix(
    world: World,
) -> None:
    await world.pull_with_no_bucket()

    [notification] = world.notifier.sent
    assert notification.title == PERSON_TITLE
    assert (
        notification.message == f"Run {FIRST_RUN_ID} (dev) stopped: the AWS profile it publishes with is not "
        f"one this machine's AWS config defines. {PERSON}"
    )
    assert notification.hint == THE_FIX
    assert notification.fix_command == "debate-research caselist pull"
    assert "aws sso login" not in notification.text, "no login defines a profile"
    assert "will be retried" not in notification.title + notification.text


async def test_its_record_is_owed_to_the_bucket_and_nothing_has_reached_it(world: World) -> None:
    await world.pull_with_no_bucket()

    assert owed(world) == [FIRST_RUN_ID]
    assert in_the_bucket(world, RECORDS_PREFIX) == {}
    assert in_the_bucket(world, DETAILS_PREFIX) == {}


async def test_what_it_logs_names_the_run_and_the_errors_class_and_nothing_else(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger="debate_core"):
        await world.pull_with_no_bucket()

    assert [
        one.getMessage() for one in caplog.records if one.name == "debate_core.application.sync_runs"
    ] == [
        f"caselist run record {FIRST_RUN_ID} not published: the bucket's adapter could not be built "
        "(StoreProfileNotConfigured)"
    ]


async def test_nothing_it_writes_or_says_names_a_path_an_account_or_an_address(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger="debate_core"):
        await world.pull_with_no_bucket()

    [notification] = world.notifier.sent
    everything = "\n".join(
        (
            world.run_log().decode("utf-8"),
            (world.installation.data_dir / DETAILS_FILE).read_text("utf-8"),
            (world.installation.data_dir / OWED_FILE).read_text("utf-8"),
            notification.title,
            notification.text,
            caplog.text,
        )
    )
    for forbidden in (str(world.installation.data_dir), str(world.scratch), str(Path.home()), "/.aws"):
        assert forbidden not in everything
    assert AN_ACCOUNT_OR_AN_ADDRESS.search(everything) is None, everything
    said = "\n".join((notification.title, notification.text, world.run_log().decode("utf-8")))
    assert A_PATH_ON_A_MACHINE.search(said) is None, said


def test_the_refusal_these_runs_are_given_is_what_boto3_raises_when_the_session_is_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The scenario's refusal is the adapter's translation of botocore's `ProfileNotFound`. This is
    boto3 raising it for real, at the construction of a session, against an AWS config written for
    this test that defines another profile: the same class, the same words, the same fix."""
    config = tmp_path / "an-aws-config-written-for-this-test"
    config.write_text("[profile debate-dev-evidence]\nregion = us-east-1\n", encoding="utf-8")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(config))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "no-credentials"))
    monkeypatch.delenv("AWS_PROFILE", raising=False)

    with pytest.raises(errors.StoreProfileNotConfigured) as raised:
        build_s3_client(region="us-east-1", profile=MISSPELT_PROFILE, profile_setting=PROFILE_SETTING)

    given = the_adapters_refusal_of_a_session()
    assert type(raised.value) is type(given)
    assert str(raised.value) == str(given)
    assert raised.value.hint == getattr(given, "hint", None)
    assert type(raised.value.__cause__).__name__ == "ProfileNotFound"
    assert str(config) not in str(raised.value)


# ------------------------------------------------------------------------------------------------
# ac2: published by the next run that can reach the bucket
# ------------------------------------------------------------------------------------------------


async def test_the_next_pull_that_reaches_the_bucket_publishes_the_refused_runs_record_and_details(
    world: World,
) -> None:
    await a_refusal_to_start_published_by_the_next_run(world)

    records = in_the_bucket(world, RECORDS_PREFIX)
    assert sorted(records) == [
        f"{RECORDS_PREFIX}2026/{FIRST_RUN_ID}.json",
        f"{RECORDS_PREFIX}2026/{SECOND_RUN_ID}.json",
    ]
    refused, published = run_log(world)
    assert records[f"{RECORDS_PREFIX}2026/{FIRST_RUN_ID}.json"] == refused
    assert refused["outcome"] == "failed" and published["outcome"] == "completed"
    details = in_the_bucket(world, DETAILS_PREFIX)
    assert sorted(details) == [
        f"{DETAILS_PREFIX}2026/{FIRST_RUN_ID}.json",
        f"{DETAILS_PREFIX}2026/{SECOND_RUN_ID}.json",
    ]
    assert details[f"{DETAILS_PREFIX}2026/{FIRST_RUN_ID}.json"]["failure_codes"] == [
        "STORE_PROFILE_NOT_CONFIGURED"
    ]
    assert details[f"{DETAILS_PREFIX}2026/{FIRST_RUN_ID}.json"]["hint"] == THE_FIX
    assert owed(world) is None, "nothing is owed once both are in the bucket"
    assert [one.title for one in world.notifier.sent] == [PERSON_TITLE], "the second run had nothing to say"


async def test_publish_pending_publishes_it_too_once_the_setting_is_corrected(world: World) -> None:
    """What an operator runs after correcting the setting, without waiting for next week."""
    await world.pull_with_no_bucket()
    world.set_clock(SECOND_RUN)
    source = FakeSource(world.installation.archives, weeks=[WEEK_1])

    await world.pull(world.installation.sync(source), publish_pending=True)

    assert sorted(in_the_bucket(world, RECORDS_PREFIX)) == [
        f"{RECORDS_PREFIX}2026/{FIRST_RUN_ID}.json",
        f"{RECORDS_PREFIX}2026/{SECOND_RUN_ID}.json",
    ]
    assert owed(world) is None


async def test_two_refused_weeks_are_two_records_both_owed_and_both_published_later(world: World) -> None:
    await world.pull_with_no_bucket()
    world.set_clock(SECOND_RUN)
    await world.pull_with_no_bucket()

    assert [one["run_id"] for one in run_log(world)] == [FIRST_RUN_ID, SECOND_RUN_ID]
    assert owed(world) == [FIRST_RUN_ID, SECOND_RUN_ID]
    assert [one.title for one in world.notifier.sent] == [PERSON_TITLE, PERSON_TITLE], "one a week"

    world.set_clock(THIRD_RUN)
    source = FakeSource(world.installation.archives, weeks=[WEEK_1])
    await world.pull(world.installation.sync(source))

    assert sorted(key.removeprefix(RECORDS_PREFIX) for key in in_the_bucket(world, RECORDS_PREFIX)) == [
        f"2026/{FIRST_RUN_ID}.json",
        f"2026/{SECOND_RUN_ID}.json",
        f"2026/{THIRD_RUN_ID}.json",
    ]
    assert owed(world) is None


async def test_a_record_already_owed_stays_owed_ahead_of_the_refused_runs(world: World) -> None:
    """A week whose session had expired, then a week whose setting was wrong. The refusal must not
    drop what was already owed: an environment with no bucket clears that list, and this is not one."""
    source = FakeSource(world.installation.archives, weeks=[WEEK_1])
    working_bucket = world.installation.bucket
    world.installation.bucket = ExpiredBucket()
    await world.pull(world.installation.sync(source))
    assert owed(world) == [FIRST_RUN_ID]

    world.set_clock(SECOND_RUN)
    await world.pull_with_no_bucket()

    assert owed(world) == [FIRST_RUN_ID, SECOND_RUN_ID]

    world.installation.bucket = working_bucket
    world.set_clock(THIRD_RUN)
    await world.pull(world.installation.sync(source))

    assert len(in_the_bucket(world, RECORDS_PREFIX)) == len(in_the_bucket(world, DETAILS_PREFIX)) == 3
    assert owed(world) is None


# ------------------------------------------------------------------------------------------------
# The bucket is built when a record is published, and not before
# ------------------------------------------------------------------------------------------------


async def test_the_bucket_is_built_once_and_only_when_a_record_is_to_be_published(world: World) -> None:
    built: list[str] = []
    seen_when_the_pull_ran: list[int] = []

    def build() -> EvidenceObjectStore:
        built.append("built")
        return world.installation.bucket

    source = FakeSource(world.installation.archives, weeks=[WEEK_1])
    service = world.installation.sync(source)

    def the_service() -> CaselistSyncService:
        seen_when_the_pull_ran.append(len(built))
        return service

    monitor = monitor_that_builds(world, build)
    assert built == [], "building the monitor builds no bucket"

    await pull_through(world, monitor, the_service)

    assert world.raised == []
    assert seen_when_the_pull_ran[0] == 0, "the pull started before the monitor's bucket was built"
    assert built == ["built"]
    assert len(in_the_bucket(world, RECORDS_PREFIX)) == 1


async def test_a_bucket_that_cannot_be_built_for_a_reason_nobody_modelled_is_recorded_and_announced_too(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    """Whatever stops the adapter being built stops the service being built, and the run is one
    that stopped on an error: recorded here, owed, announced as needing a person, and raised again
    as itself. An error this project did not write is recorded by its class and no message."""

    def broken() -> Any:
        raise RuntimeError("could not open /Users/someone/.aws/config")

    monitor = monitor_that_builds(world, broken)
    with caplog.at_level(logging.WARNING):
        await pull_through(world, monitor, broken)

    [stopped] = world.raised
    assert isinstance(stopped, RuntimeError)
    [record] = run_log(world)
    assert (record["outcome"], record["error_class"], record["error_message"]) == (
        "failed",
        "RuntimeError",
        None,
    )
    assert owed(world) == [FIRST_RUN_ID]
    [notification] = world.notifier.sent
    assert notification.title == PERSON_TITLE
    assert notification.hint is None
    assert "/Users/someone" not in caplog.text + notification.text + world.run_log().decode("utf-8")
    assert "could not be built (RuntimeError)" in caplog.text


async def test_an_environment_with_no_bucket_still_owes_nothing(world: World) -> None:
    """Unchanged: a monitor given no bucket and none to build has nowhere to publish, and keeps no
    list of what it owes."""
    monitor = SyncRunMonitor(
        state_dir=world.installation.data_dir,
        environment="dev",
        notifier=RecordingNotifier(),
        remote=None,
        aws_login_command=AWS_LOGIN,
        clock=lambda: inbox_retention.RUN_CLOCK,
    )
    source = FakeSource(world.installation.archives, weeks=[WEEK_1])
    service = world.installation.sync(source, bucket=False)

    await pull_through(world, monitor, lambda: service)

    assert world.raised == []
    assert len(SyncRunLog(world.installation.data_dir / SYNC_RUN_LOG_FILENAME).read()) == 1
    assert owed(world) is None


def test_a_monitor_is_given_a_bucket_or_one_to_build_and_never_both(world: World) -> None:
    with pytest.raises(ValueError, match="remote or build_remote"):
        monitor_that_builds(world, lambda: world.installation.bucket, remote=world.installation.bucket)
