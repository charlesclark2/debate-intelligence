"""With no readable caselist_token, a bucket-mode run gives the cloud's cure, not a hand login (`v1-e40-t40`).

`v1-e40-t35` gave a bucket-mode `CASELIST_AUTH_EXPIRED` the cloud's cure in the command's output and the
run record. Two gaps were left, and this file closes both:

* `CASELIST_TOKEN_MISSING` and `CASELIST_TOKEN_UNREADABLE` still printed "run `debate-research caselist
  auth login`" (or the logout, then the login) in a bucket-mode command's output and kept it as the
  record's `error_message`, which `caselist-cloud-run.md` forbids: the cloud run's token is the secret the
  Wednesday 03:00 login writes, and a login by hand would be a second login. In bucket mode each code in
  the table of cloud cures now prints what happened, with its cure as the hint, in `_hint_for`'s
  "In bucket mode …" idiom, and the record keeps what happened alone.
* The notice of a bucket-mode run whose download stage failed on `CASELIST_AUTH_EXPIRED` gave
  `v1-e40-t28`'s "the next cloud run … or one started by hand". A run started by hand before the
  Wednesday login is refused again; its fix line is now `v1-e40-t33`'s Wednesday login.

On the Mac every word stays, pinned here by its old text: these pins were written, and passed, before
anything changed. A code outside the table keeps its words in bucket mode too.

Each run is the real command through Typer's `CliRunner`, against moto and the stand-in site of
`conftest.py`. In bucket mode the token is the Secrets Manager secret the cloud run reads (moto's), as in
the cloud; on the Mac it is the file backend's 0600 file. The notice is read as the coach's email: the
real `sns` notifier publishes to a moto topic, and a moto queue subscribed to it receives the message.
Every expected sentence is written out by hand. Nothing here opens a socket.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any, Final

import boto3
import pytest
from tests.fixtures.parse_pipeline.build_parse_world import CASELIST, WEEKS

from debate_cli.exit_codes import ExitCode

World = Any
"""`conftest.py`'s world, which a test module cannot import by name."""

API: Final = "https://api.opencaselist.example.invalid/v1"
WEEK_1, WEEK_2, WEEK_3 = (week.snapshot for week in WEEKS)
BACKFILE: Final = "testcl25"
TOKEN_SECRET: Final = "debate-dev-caselist-token"
"""The secret Terraform names for dev's caselist_token, which the container reads when no id is set."""

# ------------------------------------------------------------------------------------------------
# What each output says, by hand
# ------------------------------------------------------------------------------------------------

NO_TOKEN_ON_THE_MAC: Final = "no caselist_token is stored; run `debate-research caselist auth login` first"
"""`CaselistTokenMissing`'s message, as before `v1-e40-t40`, word for word."""

NO_TOKEN_IN_THE_CLOUD: Final = "no caselist_token is stored"
"""What happened, without the Mac's login: the message's first clause."""

UNREADABLE_ON_THE_MAC: Final = (
    "the caselist_token stored in the file backend is not readable; run `debate-research caselist auth "
    "logout` and then `caselist auth login`"
)
"""`CaselistTokenUnreadable`'s message for the Mac's file backend, as before `v1-e40-t40`, word for word."""

UNREADABLE_IN_THE_CLOUD: Final = "the caselist_token stored in the secretsmanager backend is not readable"
"""What happened in the cloud, where the token is the Secrets Manager secret, without the Mac's logout and
login."""

THE_NO_TOKEN_CURE_IN_THE_CLOUD: Final = (
    "In bucket mode the next Wednesday 03:00 login writes a new caselist_token to the token secret, and the "
    "run after it takes up what this run did not finish, from the run state saved in the bucket; a backfile "
    'import refused for it starts again after Thursday 00:00 (caselist-cloud-run.md, "A run with no readable '
    'caselist_token"); never a login by hand, which would be a second login.'
)
"""The bucket-mode hint for both token codes, in `_hint_for`'s idiom: the wording proposed to the PM."""

THE_EXPIRED_LOGIN_CURE: Final = (
    "the next Wednesday 03:00 login renews the caselist_token, and the run after it takes up what this run "
    "did not finish, from the run state saved in the bucket; a backfile import refused for it starts again "
    'after Thursday 00:00 (caselist-cloud-run.md, "A run refused for an expired login"); never a login by '
    "hand, which would be a second login"
)
"""`v1-e40-t33`'s cure, as the notice's fix line gives it."""

THE_UNFINISHED_RUN_CURE: Final = (
    "the next cloud run takes up what this run did not finish, from the run state saved in the bucket: the "
    'weekly run, or one started by hand (caselist-cloud-run.md, "A failed or stopped run"); never a publish '
    "from the operator's Mac"
)
"""`v1-e40-t28`'s fix line for any other failed download in bucket mode: unchanged."""

THE_LOGIN: Final = "auth login"
THE_LOGOUT: Final = "auth logout"

A_NEW_CAMP_FILE: Final = {
    "openev_id": 513,
    "path": "/openev/2026/Tamarack/TSF-Floodplain Permit Counterplan.docx",
    "filename": "TSF-Floodplain Permit Counterplan.docx",
    "year": 2026,
    "camp": "Tamarack",
    "tags": {"policy": True},
}
"""An invented camp file listed after the first pull, so that the next run downloads it from the API host."""


def flattened(text: str) -> str:
    """`text` as one line, with a panel's borders gone: Rich wraps a panel at the terminal's width."""
    return " ".join(text.replace("│", " ").split())


# ------------------------------------------------------------------------------------------------
# The installation, its token, and the coach's inbox
# ------------------------------------------------------------------------------------------------


def seeded_with_two_weeks(world: World) -> None:
    """Two weeks pulled on the Mac and seeded into the bucket; then a week later, a third listed."""
    world.listing(WEEK_1, WEEK_2)
    assert world.pull()["exit_code"] == ExitCode.OK
    world.seed()
    world.clock.advance(timedelta(days=7))
    world.listing(WEEK_1, WEEK_2, WEEK_3)


def pulled_on_the_mac(world: World) -> None:
    """Two weeks pulled on the Mac, in local mode; then a week later, a third listed."""
    world.listing(WEEK_1, WEEK_2)
    assert world.pull()["exit_code"] == ExitCode.OK
    world.clock.advance(timedelta(days=7))
    world.listing(WEEK_1, WEEK_2, WEEK_3)


def in_a_cloud_task(world: World, tmp_path: Path) -> Path:
    """The cloud run's own empty data directory, in bucket mode: it restores from the bucket."""
    world.mode("bucket")
    return world.use(tmp_path / "cloud-task")


def the_token_is_the_secret(world: World, holding: str | None) -> None:
    """The token is the Secrets Manager secret, as in the cloud, holding `holding` or no value at all."""
    world.monkeypatch.delenv("DEBATE_PROVIDERS__CASELIST_TOKEN", raising=False)
    world.monkeypatch.setenv("DEBATE_CASELIST__TOKEN_BACKEND", "secretsmanager")
    if holding is not None:
        boto3.client("secretsmanager", region_name="us-east-1").create_secret(  # pyright: ignore[reportUnknownMemberType]
            Name=TOKEN_SECRET, SecretString=holding
        )


def the_token_is_the_macs_file(world: World, holding: str | None, *, mode: int = 0o600) -> Path:
    """The token is the file backend's file under the data directory, holding `holding`, or none at all."""
    world.monkeypatch.delenv("DEBATE_PROVIDERS__CASELIST_TOKEN", raising=False)
    world.monkeypatch.setenv("DEBATE_CASELIST__TOKEN_BACKEND", "file")
    path: Path = world.data_dir / "secrets" / "caselist_token"
    if holding is not None:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_text(holding, encoding="utf-8")
        os.chmod(path, mode)
    return path


NOT_A_TOKEN_RECORD: Final = "not a record this program wrote"


def the_coachs_inbox(world: World) -> Callable[[], list[str]]:
    """Every alert the `sns` notifier sends from now on, as the coach's email reads it."""
    sns = boto3.client("sns", region_name="us-east-1")  # pyright: ignore[reportUnknownMemberType]
    sqs = boto3.client("sqs", region_name="us-east-1")  # pyright: ignore[reportUnknownMemberType]
    topic = sns.create_topic(Name="debate-dev-caselist-run-alerts")["TopicArn"]
    queue = sqs.create_queue(QueueName="the-coachs-inbox")["QueueUrl"]
    queue_arn = sqs.get_queue_attributes(QueueUrl=queue, AttributeNames=["QueueArn"])["Attributes"][
        "QueueArn"
    ]
    sns.subscribe(
        TopicArn=topic, Protocol="sqs", Endpoint=queue_arn, Attributes={"RawMessageDelivery": "true"}
    )
    world.monkeypatch.setenv("DEBATE_CASELIST__NOTIFIER", "sns")
    world.monkeypatch.setenv("DEBATE_CASELIST__ALERT_TOPIC_ARN", topic)

    def received() -> list[str]:
        answer = sqs.receive_message(QueueUrl=queue, MaxNumberOfMessages=10, VisibilityTimeout=300)
        return [message["Body"] for message in answer.get("Messages", [])]

    return received


def a_new_camp_file_whose_download_answers(world: World, status: int) -> None:
    world.site.get(f"{API}/openev").respond(200, json=[A_NEW_CAMP_FILE])
    world.site.get(f"{API}/download").respond(status)


def the_record_of(world: World) -> dict[str, Any]:
    record, _ = world.last_record()
    return record


def what_the_bucket_holds_as_text(world: World) -> str:
    """Every JSON object the bucket holds under the run reports, as one text."""
    return "\n".join(
        world.body(key).decode("utf-8")
        for key in sorted(world.object_keys("reports/sync/"))
        if key.endswith((".json", ".jsonl"))
    )


# ------------------------------------------------------------------------------------------------
# The Mac: every word as it was
# ------------------------------------------------------------------------------------------------


def test_a_mac_pull_with_no_token_keeps_its_output_word_for_word(world: World) -> None:
    pulled_on_the_mac(world)
    the_token_is_the_macs_file(world, None)

    refused = world.pull()

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused
    error = refused["error"]
    assert error["code"] == "CASELIST_TOKEN_MISSING"
    assert error["message"] == NO_TOKEN_ON_THE_MAC
    assert error["hint"] is None
    assert error["details"] == {}
    assert "Wednesday" not in json.dumps(refused)


def test_a_mac_pull_with_no_token_keeps_its_panel_and_record_word_for_word(world: World) -> None:
    pulled_on_the_mac(world)
    the_token_is_the_macs_file(world, None)

    result = world.invoke("caselist", "pull", "--caselist", CASELIST)

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    panel = flattened(result.output)
    assert NO_TOKEN_ON_THE_MAC in panel
    assert "Wednesday" not in panel
    record = the_record_of(world)
    assert record["error_class"] == "CaselistTokenMissing"
    assert record["error_message"] == NO_TOKEN_ON_THE_MAC


def test_a_mac_pull_with_an_unreadable_token_keeps_its_output_word_for_word(world: World) -> None:
    pulled_on_the_mac(world)
    the_token_is_the_macs_file(world, NOT_A_TOKEN_RECORD)

    refused = world.pull()

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused
    error = refused["error"]
    assert error["code"] == "CASELIST_TOKEN_UNREADABLE"
    assert error["message"] == UNREADABLE_ON_THE_MAC
    assert error["hint"] is None
    assert error["details"] == {"backend": "file"}
    assert "Wednesday" not in json.dumps(refused)


def test_a_mac_pull_with_an_unreadable_token_keeps_its_panel_and_record_word_for_word(world: World) -> None:
    pulled_on_the_mac(world)
    the_token_is_the_macs_file(world, NOT_A_TOKEN_RECORD)

    result = world.invoke("caselist", "pull", "--caselist", CASELIST)

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    panel = flattened(result.output)
    assert UNREADABLE_ON_THE_MAC in panel
    assert "Wednesday" not in panel
    record = the_record_of(world)
    assert record["error_class"] == "CaselistTokenUnreadable"
    assert record["error_message"] == UNREADABLE_ON_THE_MAC


@pytest.mark.parametrize(
    ("holding", "code", "message"),
    [
        pytest.param(None, "CASELIST_TOKEN_MISSING", NO_TOKEN_ON_THE_MAC, id="no-token"),
        pytest.param(NOT_A_TOKEN_RECORD, "CASELIST_TOKEN_UNREADABLE", UNREADABLE_ON_THE_MAC, id="unreadable"),
    ],
)
def test_a_mac_backfile_import_with_no_readable_token_keeps_its_output_word_for_word(
    world: World, holding: str | None, code: str, message: str
) -> None:
    """In local mode the import lists before it returns its refusals, so the token error ends it as before."""
    world.monkeypatch.setenv("DEBATE_CASELIST__BACKFILE_CASELISTS", json.dumps([BACKFILE]))
    the_token_is_the_macs_file(world, holding)

    refused = world.run("caselist", "backfile-import", "--caselist", BACKFILE)

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused
    error = refused["error"]
    assert error["code"] == code
    assert error["message"] == message
    assert error["hint"] is None


def test_a_mac_download_refused_for_auth_expired_keeps_its_notice_word_for_word(world: World) -> None:
    pulled_on_the_mac(world)
    inbox = the_coachs_inbox(world)
    a_new_camp_file_whose_download_answers(world, 401)

    world.pull()

    where = f"Run {the_record_of(world)['run_id']} (dev)"
    assert inbox() == [
        "caselist pull failed: needs a person\n"
        f"{where}\n"
        "\n"
        f"{where}: the download stage failed on CASELIST_AUTH_EXPIRED. A person should look: at least one "
        "failure here will be the same on the next scheduled run. What was captured is kept.\n"
        "\n"
        "Fix: debate-research caselist pull"
    ]


# ------------------------------------------------------------------------------------------------
# Bucket mode: `caselist pull` with no readable token
# ------------------------------------------------------------------------------------------------

THE_TWO_TOKEN_CODES: Final = [
    pytest.param(None, "CASELIST_TOKEN_MISSING", NO_TOKEN_IN_THE_CLOUD, {}, id="no-token"),
    pytest.param(
        NOT_A_TOKEN_RECORD,
        "CASELIST_TOKEN_UNREADABLE",
        UNREADABLE_IN_THE_CLOUD,
        {"backend": "secretsmanager"},
        id="unreadable",
    ),
]


@pytest.mark.parametrize(("holding", "code", "message", "details"), THE_TWO_TOKEN_CODES)
def test_a_bucket_mode_pull_with_no_readable_token_names_the_wednesday_login(
    world: World, tmp_path: Path, holding: str | None, code: str, message: str, details: dict[str, str]
) -> None:
    seeded_with_two_weeks(world)
    in_a_cloud_task(world, tmp_path)
    the_token_is_the_secret(world, holding)

    refused = world.pull()

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused
    error = refused["error"]
    assert error["code"] == code
    assert error["message"] == message
    assert error["hint"] == THE_NO_TOKEN_CURE_IN_THE_CLOUD
    assert error["details"] == details
    assert THE_LOGIN not in json.dumps(refused)
    assert THE_LOGOUT not in json.dumps(refused)


@pytest.mark.parametrize(("holding", "code", "message", "details"), THE_TWO_TOKEN_CODES)
def test_a_bucket_mode_pull_with_no_readable_token_prints_no_login_in_its_panel(
    world: World, tmp_path: Path, holding: str | None, code: str, message: str, details: dict[str, str]
) -> None:
    """What the cloud run's log keeps when the command is run without `--json`."""
    seeded_with_two_weeks(world)
    in_a_cloud_task(world, tmp_path)
    the_token_is_the_secret(world, holding)

    result = world.invoke("caselist", "pull", "--caselist", CASELIST)

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    panel = flattened(result.output)
    assert message in panel
    assert THE_NO_TOKEN_CURE_IN_THE_CLOUD in panel
    assert THE_LOGIN not in panel
    assert THE_LOGOUT not in panel
    assert "debate-research" not in panel


@pytest.mark.parametrize(("holding", "code", "message", "details"), THE_TWO_TOKEN_CODES)
def test_a_bucket_mode_run_with_no_readable_token_records_no_login(
    world: World, tmp_path: Path, holding: str | None, code: str, message: str, details: dict[str, str]
) -> None:
    """`error_message` keeps what happened, a string as every build reads it, without the Mac's login."""
    seeded_with_two_weeks(world)
    in_a_cloud_task(world, tmp_path)
    the_token_is_the_secret(world, holding)

    world.pull()

    record = the_record_of(world)
    assert record["outcome"] == "failed"
    assert record["error_message"] == message
    assert THE_LOGIN not in what_the_bucket_holds_as_text(world)
    assert THE_LOGOUT not in what_the_bucket_holds_as_text(world)
    listed = world.run("caselist", "runs")
    assert listed["exit_code"] == ExitCode.OK, listed
    assert message in json.dumps(listed)
    assert THE_LOGIN not in json.dumps(listed)


def test_a_bucket_mode_pull_stopped_by_a_token_code_outside_the_table_keeps_its_words(
    world: World, tmp_path: Path
) -> None:
    """A token file others can read (`InsecureTokenFile`) is outside the table: no cure, its words kept."""
    seeded_with_two_weeks(world)
    in_a_cloud_task(world, tmp_path)
    path = the_token_is_the_macs_file(world, NOT_A_TOKEN_RECORD, mode=0o644)

    refused = world.pull()

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused
    error = refused["error"]
    assert error["code"] not in {
        "CASELIST_AUTH_EXPIRED",
        "CASELIST_TOKEN_MISSING",
        "CASELIST_TOKEN_UNREADABLE",
    }
    insecure = (
        " has permissions -rw-r--r--; a caselist_token file must be readable by its owner only (0600). It "
        "was not used. Delete it, then run `debate-research caselist auth login` again."
    )
    assert error["message"] == f"{path}{insecure}"
    assert error["hint"] is None
    assert "Wednesday" not in json.dumps(refused)
    assert the_record_of(world)["error_message"] == f"[redacted]{insecure}"


# ------------------------------------------------------------------------------------------------
# Bucket mode: `caselist backfile-import` with no readable token
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("execute", [False, True], ids=["dry-run", "execute"])
@pytest.mark.parametrize(("holding", "code", "message", "details"), THE_TWO_TOKEN_CODES)
def test_a_bucket_mode_backfile_import_with_no_readable_token_names_the_wednesday_login(
    world: World,
    tmp_path: Path,
    holding: str | None,
    code: str,
    message: str,
    details: dict[str, str],
    execute: bool,
) -> None:
    in_a_cloud_task(world, tmp_path)
    world.monkeypatch.setenv("DEBATE_CASELIST__BACKFILE_CASELISTS", json.dumps([BACKFILE]))
    the_token_is_the_secret(world, holding)

    refused = world.run(
        "caselist", "backfile-import", "--caselist", BACKFILE, *(["--execute"] if execute else [])
    )

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused
    error = refused["error"]
    assert error["code"] == code
    assert error["message"] == message
    assert error["hint"] == THE_NO_TOKEN_CURE_IN_THE_CLOUD
    assert THE_LOGIN not in json.dumps(refused)
    assert THE_LOGOUT not in json.dumps(refused)


# ------------------------------------------------------------------------------------------------
# Bucket mode: the notice of a download refused for an expired login
# ------------------------------------------------------------------------------------------------


def test_a_bucket_mode_download_refused_for_auth_expired_gets_the_wednesday_login_in_its_notice(
    world: World, tmp_path: Path
) -> None:
    seeded_with_two_weeks(world)
    in_a_cloud_task(world, tmp_path)
    inbox = the_coachs_inbox(world)
    a_new_camp_file_whose_download_answers(world, 401)

    world.pull()

    where = f"Run {the_record_of(world)['run_id']} (dev)"
    assert inbox() == [
        "caselist pull failed: needs a person\n"
        f"{where}\n"
        "\n"
        f"{where}: the download stage failed on CASELIST_AUTH_EXPIRED. A person should look: at least one "
        "failure here will be the same on the next scheduled run. What the bucket confirmed is kept; the "
        "cloud run's working copy ends with its task.\n"
        "\n"
        f"Fix: {THE_EXPIRED_LOGIN_CURE}"
    ]


def test_a_bucket_mode_download_failed_on_another_code_keeps_the_next_cloud_run_in_its_notice(
    world: World, tmp_path: Path
) -> None:
    seeded_with_two_weeks(world)
    in_a_cloud_task(world, tmp_path)
    inbox = the_coachs_inbox(world)
    a_new_camp_file_whose_download_answers(world, 404)

    world.pull()

    [email] = inbox()
    assert "CASELIST_AUTH_EXPIRED" not in email
    assert "Wednesday" not in email
    assert email.endswith(f"\n\nFix: {THE_UNFINISHED_RUN_CURE}")


# ------------------------------------------------------------------------------------------------
# The table, and the runbook section its cure names
# ------------------------------------------------------------------------------------------------


def test_the_table_of_cloud_cures_holds_the_three_token_codes_and_no_other() -> None:
    from debate_core.application.sync_runs import CLOUD_TOKEN_CURES

    assert set(CLOUD_TOKEN_CURES) == {
        "CASELIST_AUTH_EXPIRED",
        "CASELIST_TOKEN_MISSING",
        "CASELIST_TOKEN_UNREADABLE",
    }
    assert CLOUD_TOKEN_CURES["CASELIST_AUTH_EXPIRED"] == THE_EXPIRED_LOGIN_CURE


def test_what_an_unreadable_token_says_in_bucket_mode_is_the_store_s_own_first_clause() -> None:
    """The application words it from the error's `backend`: kept in step with the store's own sentence."""
    from debate_core.application.caselist_sync import message_for
    from debate_core.integrations.opencaselist.token_store import CaselistTokenUnreadable

    for backend in ("secretsmanager", "file", "keyring"):
        unreadable = CaselistTokenUnreadable(backend)
        in_the_cloud = message_for(unreadable, bucket_mode=True)
        assert str(unreadable).startswith(f"{in_the_cloud}; run `debate-research caselist auth logout`")
        assert message_for(unreadable, bucket_mode=False) == str(unreadable)


CLOUD_RUNBOOK: Final = Path(__file__).resolve().parents[4] / "docs" / "runbooks" / "caselist-cloud-run.md"


def test_the_cloud_runbook_has_the_section_the_no_token_cure_names() -> None:
    text = CLOUD_RUNBOOK.read_text(encoding="utf-8")
    assert "\n## A run with no readable caselist_token\n" in text
    flat = flattened(text)
    assert f"> {THE_NO_TOKEN_CURE_IN_THE_CLOUD}" in flat
    assert "and the messages of the other two codes still do" not in flat
    assert (
        "**A second Wednesday stopped on `CASELIST_TOKEN_UNREADABLE`**, after a login that sent no failure"
        in flat
    )
    assert "the run stops on `STORE_ACCESS_DENIED`, error class `StoreAccessDenied`" in flat
