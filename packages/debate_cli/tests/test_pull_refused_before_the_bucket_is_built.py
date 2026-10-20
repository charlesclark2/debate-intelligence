"""`caselist pull` with a profile setting that names no profile: recorded, announced, and published later.

`v1-e34-t22`, through the real application and the real composition root. `storage.s3.aws_profile`
names a profile the AWS config does not define, so boto3 raises `ProfileNotFound` when the S3
adapter builds its session, and the bucket's adapter cannot be built (`v1-e29-t07`). The command
has always ended with exit `1` there. What it did not do is leave any trace a person would see:
the run monitor was handed the bucket built, so it could not be built either, and the weekly agent
recorded no run and sent no notification.

boto3 reads an AWS config written for each test; nothing reads the config of the machine the suite
runs on and nothing reaches AWS (moto answers S3 for the run that publishes). The clock is pinned,
so that the record this command writes can be compared, line for line, with the one the older
build's code wrote for the same refusal
(`packages/debate_core/tests/application/caselist/stored_run_records/`).

`caselist pull` beside its site, importing and publishing a week after a refused one, is in
`tests/smoke/test_caselist_pull.py`.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import boto3
import pytest
from moto import mock_aws
from tests.fixtures.caselist.build_synthetic_archives import SYNTHETIC_CASELIST
from tests.fixtures.model_routing import EXAMPLE_ROUTING_FILE
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.container import ServiceContainer
from debate_cli.exit_codes import ExitCode
from debate_core.application.ports.notifier import RecordingNotifier

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

runner = CliRunner()

BUCKET = "debate-dev-evidence-refusal-moto"
EVERYDAY_PROFILE = "debate-dev-evidence"
MISSPELT_PROFILE = "debate-dev-evidence-typo"
PROFILE_SETTING = "storage.s3.aws_profile"
AWS_CONFIG_NAME = "an-aws-config-written-for-this-test"

FIRST_RUN = datetime(2026, 9, 16, 6, 0, tzinfo=UTC)
SECOND_RUN = datetime(2026, 9, 23, 6, 0, tzinfo=UTC)
FIRST_RUN_ID = "20260916T060000Z"
SECOND_RUN_ID = "20260923T060000Z"

RUN_LOG = "caselist-sync-runs.jsonl"
DETAILS_FILE = "caselist-sync-run-details.jsonl"
OWED_FILE = "caselist-sync-records-pending.json"
RECORDS_PREFIX = "reports/sync-runs/"
DETAILS_PREFIX = "reports/sync-run-details/"
"""The names the runbook gives, written out and not imported."""

PERSON_TITLE = "caselist pull failed: needs a person"
PERSON = "A person should look: at least one failure here will be the same on the next scheduled run."
THE_FIX = (
    "The bucket was never reached: set storage.s3.aws_profile to a profile this machine's AWS config "
    "defines, or add the profile to it: docs/runbooks/evidence-store.md lists the evidence profiles "
    "and how they are added. It is not an expired session, and logging in changes nothing."
)
THE_RECORDED_MESSAGE = (
    "AWS profile 'debate-dev-evidence-typo', named by storage.s3.aws_profile, is not defined in this "
    "machine's AWS config: set storage.s3.aws_profile to a profile this machine's AWS config defines, "
    "or add the profile to it: docs/runbooks/evidence-store.md lists the evidence profiles and how "
    "they are added. It is not an expired session, and logging in changes nothing"
)

STORED_BY_THE_OLDER_BUILD = (
    Path(__file__).resolve().parents[2]
    / "debate_core/tests/application/caselist/stored_run_records/written_by_the_start_commit"
    / "a_refusal_to_start_published_by_the_next_run.run-log.jsonl"
)

AN_ACCOUNT_OR_AN_ADDRESS = re.compile(r"\b\d{12}\b|arn:|https?://|awsapps\.com")


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> dict[str, datetime]:
    """The one clock the pull and its run log read, pinned; a test moves it between runs."""
    now = {"at": FIRST_RUN}
    monkeypatch.setattr(ServiceContainer, "clock", lambda _: lambda: now["at"])
    return now


@pytest.fixture
def notified(monkeypatch: pytest.MonkeyPatch) -> RecordingNotifier:
    """What the run monitor would have shown: the profile here says `none`, so nothing is shown."""
    notifier = RecordingNotifier()
    monkeypatch.setattr(ServiceContainer, "sync_notifier", lambda _: notifier)
    return notifier


@pytest.fixture(autouse=True)
def installation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clock: dict[str, datetime], notified: RecordingNotifier
) -> Iterator[Path]:
    """A dev profile naming a moto bucket, the API on, and an AWS config defining the everyday profile."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    config = tmp_path / AWS_CONFIG_NAME
    config.write_text(f"[profile {EVERYDAY_PROFILE}]\nregion = us-east-1\n", encoding="utf-8")
    credentials = tmp_path / "aws-credentials"
    credentials.write_text(
        f"[{EVERYDAY_PROFILE}]\naws_access_key_id = testing\naws_secret_access_key = testing\n",
        encoding="utf-8",
    )
    for name, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_EC2_METADATA_DISABLED": "true",
        "AWS_CONFIG_FILE": str(config),
        "AWS_SHARED_CREDENTIALS_FILE": str(credentials),
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("AWS_PROFILE", raising=False)

    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "dev.toml").write_text(
        "allow_network = true\n"
        f'[storage]\ndata_dir = "{tmp_path / "data"}"\n'
        f'[storage.s3]\nbucket = "{BUCKET}"\nregion = "us-east-1"\naws_profile = "{EVERYDAY_PROFILE}"\n'
        "[caselist]\n"
        "api_enabled = true\n"
        'notifier = "none"\n'
        'api_base_url = "https://api.opencaselist.example.invalid/v1"\n'
        f'sync_caselists = ["{SYNTHETIC_CASELIST}"]\n'
        f'[models]\nrouting_file = "{EXAMPLE_ROUTING_FILE}"\nbudget_usd_daily = 1.0\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("DEBATE_PROFILE_DIR", str(profiles))
    monkeypatch.setenv("DEBATE_ENV", "dev")
    monkeypatch.setenv("DEBATE_PROVIDERS__CASELIST_TOKEN", "fixture-token-not-a-real-one")
    yield tmp_path


@pytest.fixture
def bucket(installation: Path) -> Iterator[S3Client]:
    with mock_aws():
        client: S3Client = boto3.client("s3", region_name="us-east-1")  # pyright: ignore[reportUnknownMemberType]
        client.create_bucket(Bucket=BUCKET)
        yield client


def run(*arguments: str) -> tuple[int, dict[str, Any]]:
    """Run one command with `--json`; return its exit code and its one envelope."""
    result: Result = runner.invoke(create_app(), ["--json", *arguments])
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, f"expected one line of JSON on stdout; got {lines!r}\n{result.stderr}"
    envelope: dict[str, Any] = json.loads(lines[0])
    assert envelope["error"] is None or envelope["error"]["exit_code"] == result.exit_code
    return result.exit_code, envelope


def pull_with_the_misspelt_profile(monkeypatch: pytest.MonkeyPatch, *more: str) -> tuple[int, dict[str, Any]]:
    monkeypatch.setenv("DEBATE_STORAGE__S3__AWS_PROFILE", MISSPELT_PROFILE)
    try:
        return run("caselist", "pull", "--caselist", SYNTHETIC_CASELIST, *more)
    finally:
        monkeypatch.delenv("DEBATE_STORAGE__S3__AWS_PROFILE")


def lines_of(installation: Path, name: str) -> list[dict[str, Any]]:
    file = installation / "data" / name
    if not file.exists():
        return []
    return [json.loads(line) for line in file.read_text("utf-8").splitlines()]


def owed(installation: Path) -> list[str] | None:
    file = installation / "data" / OWED_FILE
    if not file.exists():
        return None
    listed: list[str] = json.loads(file.read_text("utf-8"))["run_ids"]
    return listed


def in_the_bucket(client: S3Client, prefix: str) -> dict[str, Any]:
    listed = client.list_objects_v2(Bucket=BUCKET, Prefix=prefix).get("Contents", [])
    return {
        str(one.get("Key")): json.loads(
            client.get_object(Bucket=BUCKET, Key=str(one.get("Key")))["Body"].read()
        )
        for one in listed
    }


# ------------------------------------------------------------------------------------------------
# ac1
# ------------------------------------------------------------------------------------------------


def test_a_pull_whose_profile_the_aws_config_lacks_still_ends_with_one_under_its_own_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Out of scope and unchanged (`v1-e29-t07`): the exit code and the envelope."""
    exit_code, envelope = pull_with_the_misspelt_profile(monkeypatch)

    assert exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope["error"]["code"] == "STORE_PROFILE_NOT_CONFIGURED"
    assert MISSPELT_PROFILE in envelope["error"]["message"]
    assert PROFILE_SETTING in envelope["error"]["hint"]


def test_it_writes_a_local_run_record_with_status_failed(
    installation: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ac1. There used to be no record at all, and no data directory."""
    pull_with_the_misspelt_profile(monkeypatch)

    [record] = lines_of(installation, RUN_LOG)
    assert (record["run_id"], record["environment"], record["mode"]) == (FIRST_RUN_ID, "dev", "run")
    assert record["outcome"] == "failed"
    assert record["caselists"] == [SYNTHETIC_CASELIST]
    assert record["stages"] == []
    assert record["error_class"] == "StoreProfileNotConfigured"
    assert record["error_message"] == THE_RECORDED_MESSAGE


def test_its_details_name_the_code_and_the_setting(
    installation: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ac1."""
    pull_with_the_misspelt_profile(monkeypatch)

    assert lines_of(installation, DETAILS_FILE) == [
        {
            "schema_version": 1,
            "run_id": FIRST_RUN_ID,
            "stages": [],
            "failure_codes": ["STORE_PROFILE_NOT_CONFIGURED"],
            "hint": THE_FIX,
            "parse": None,
            "search_index": None,
            "held_by_request": {},
        }
    ]
    assert PROFILE_SETTING in THE_FIX


def test_it_sends_one_notification_that_a_person_should_look_with_the_adapters_hint(
    notified: RecordingNotifier, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ac1. There used to be none."""
    pull_with_the_misspelt_profile(monkeypatch)

    [notification] = notified.sent
    assert notification.title == PERSON_TITLE
    assert (
        notification.message == f"Run {FIRST_RUN_ID} (dev) stopped: the AWS profile it publishes with is not "
        f"one this machine's AWS config defines. {PERSON}"
    )
    assert notification.hint == THE_FIX
    assert "aws sso login" not in notification.text


def test_caselist_runs_shows_the_refused_run_with_its_code(
    installation: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pull_with_the_misspelt_profile(monkeypatch)

    exit_code, envelope = run("caselist", "runs", "--last", "5")

    assert exit_code == ExitCode.OK, envelope
    [shown] = envelope["data"]["runs"]
    assert (shown["run_id"], shown["outcome"]) == (FIRST_RUN_ID, "failed")
    assert shown["details"]["failure_codes"] == ["STORE_PROFILE_NOT_CONFIGURED"]


def test_the_record_is_the_line_the_older_builds_code_wrote_for_the_same_refusal(
    installation: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Compatibility, at the composition root. The stored line is what the start commit's run
    monitor wrote when handed this refusal; this is what the command writes when boto3 raises it."""
    pull_with_the_misspelt_profile(monkeypatch)

    [written] = (installation / "data" / RUN_LOG).read_text("utf-8").splitlines()
    as_stored = STORED_BY_THE_OLDER_BUILD.read_text("utf-8").splitlines()[0]
    # Those words but one: since `v1-e34-t23` the redaction keeps the runbook the message points at.
    stored = as_stored.replace(
        "[redacted] lists the evidence profiles",
        "docs/runbooks/evidence-store.md lists the evidence profiles",
    )
    assert stored != as_stored
    assert json.loads(written) == json.loads(stored)
    assert list(json.loads(written)) == list(json.loads(stored)), "the same keys in the same order"
    assert written == stored, "byte for byte"


def test_a_dry_run_still_records_nothing_and_announces_nothing(
    installation: Path, notified: RecordingNotifier, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dry run leaves no run record (`v1-e34-t02`), a refused one included."""
    exit_code, envelope = pull_with_the_misspelt_profile(monkeypatch, "--dry-run")

    assert exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope["error"]["code"] == "STORE_PROFILE_NOT_CONFIGURED"
    assert lines_of(installation, RUN_LOG) == []
    assert lines_of(installation, DETAILS_FILE) == []
    assert owed(installation) is None
    assert notified.sent == []


def test_a_dry_run_refused_for_the_profile_creates_nothing_on_disk(
    installation: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`v1-e34-t24` ac3. A dry run writes nothing, and one refused for its profile wrote the data
    directory and an empty database first: the pull's services opened the database before they
    built the bucket (`v1-e34-t22` Follow-up 7). Whatever stops the bucket being built now stops
    the dry run before anything else is opened."""
    before = sorted(path.relative_to(installation) for path in installation.rglob("*"))

    exit_code, envelope = pull_with_the_misspelt_profile(monkeypatch, "--dry-run")

    assert exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope["error"]["code"] == "STORE_PROFILE_NOT_CONFIGURED"
    assert not (installation / "data").exists(), "the refused dry run created the data directory"
    assert sorted(path.relative_to(installation) for path in installation.rglob("*")) == before


def test_nothing_it_writes_says_or_logs_names_a_path_an_account_or_an_address(
    installation: Path,
    notified: RecordingNotifier,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with (
        caplog.at_level(logging.DEBUG, logger="debate_core"),
        caplog.at_level(logging.DEBUG, logger="debate_cli"),
    ):
        _, envelope = pull_with_the_misspelt_profile(monkeypatch)

    [notification] = notified.sent
    everything = "\n".join(
        (
            json.dumps(envelope["error"]),
            (installation / "data" / RUN_LOG).read_text("utf-8"),
            (installation / "data" / DETAILS_FILE).read_text("utf-8"),
            (installation / "data" / OWED_FILE).read_text("utf-8"),
            notification.title,
            notification.text,
            caplog.text,
        )
    )
    for forbidden in (str(installation), str(Path.home()), AWS_CONFIG_NAME, "/.aws", "aws configure"):
        assert forbidden not in everything
    assert AN_ACCOUNT_OR_AN_ADDRESS.search(everything) is None, everything


# ------------------------------------------------------------------------------------------------
# ac2
# ------------------------------------------------------------------------------------------------


def test_the_record_is_owed_and_the_next_run_that_reaches_the_bucket_publishes_it_with_its_details(
    installation: Path, bucket: S3Client, clock: dict[str, datetime], monkeypatch: pytest.MonkeyPatch
) -> None:
    """ac2. The setting is corrected, and the operator drains what is owed; next week's scheduled
    run does the same."""
    pull_with_the_misspelt_profile(monkeypatch)
    assert owed(installation) == [FIRST_RUN_ID]
    assert in_the_bucket(bucket, "reports/") == {}

    clock["at"] = SECOND_RUN
    exit_code, envelope = run("caselist", "pull", "--publish-pending")

    assert exit_code == ExitCode.OK, envelope
    records = in_the_bucket(bucket, RECORDS_PREFIX)
    assert sorted(records) == [
        f"{RECORDS_PREFIX}2026/{FIRST_RUN_ID}.json",
        f"{RECORDS_PREFIX}2026/{SECOND_RUN_ID}.json",
    ]
    [refused, _] = lines_of(installation, RUN_LOG)
    assert records[f"{RECORDS_PREFIX}2026/{FIRST_RUN_ID}.json"] == refused
    details = in_the_bucket(bucket, DETAILS_PREFIX)
    assert details[f"{DETAILS_PREFIX}2026/{FIRST_RUN_ID}.json"] == lines_of(installation, DETAILS_FILE)[0]
    assert details[f"{DETAILS_PREFIX}2026/{FIRST_RUN_ID}.json"]["hint"] == THE_FIX
    assert owed(installation) is None


def test_the_bucket_then_shows_the_refused_run_to_caselist_runs_remote(
    installation: Path, bucket: S3Client, clock: dict[str, datetime], monkeypatch: pytest.MonkeyPatch
) -> None:
    pull_with_the_misspelt_profile(monkeypatch)
    clock["at"] = SECOND_RUN
    run("caselist", "pull", "--publish-pending")

    exit_code, envelope = run("caselist", "runs", "--last", "5", "--remote")

    assert exit_code == ExitCode.OK, envelope
    assert [(one["run_id"], one["outcome"]) for one in envelope["data"]["runs"]] == [
        (SECOND_RUN_ID, "nothing_new"),
        (FIRST_RUN_ID, "failed"),
    ]
    assert envelope["data"]["runs"][1]["details"]["failure_codes"] == ["STORE_PROFILE_NOT_CONFIGURED"]
