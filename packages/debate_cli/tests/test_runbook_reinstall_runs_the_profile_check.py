"""The scheduled-sync runbook's reinstall steps run the profile check, and its troubleshooting
says what a refused run leaves behind (`v1-e34-t22` ac4).

The weekly agent is reinstalled by hand, from `docs/runbooks/caselist-scheduled-sync.md`, and a
check the runbook does not name is a check nobody runs. So the runbook is held to the code here:
the reinstall section runs `doctor --evidence-profiles` before the agent is replaced and
`install.sh --check-launchd` after, in the order they must be run; the section on a profile the
AWS config does not define no longer says the run leaves no record and no notification, which
was true until this task and is the opposite of true now; and the banner it quotes is the one the
run monitor sends, built here by the monitor's own code from the adapter's own error.

Nothing here runs a command. The command blocks are read, not executed.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from botocore.exceptions import ProfileNotFound

from debate_cli.exit_codes import codes_exit_as_a_retrieval_failure
from debate_core.application import sync_runs
from debate_core.integrations.s3 import S3Call, translate_s3_error

RUNBOOK = Path(__file__).resolve().parents[3] / "docs" / "runbooks" / "caselist-scheduled-sync.md"

PROFILE_CHECK = "doctor --evidence-profiles"
LAUNCHD_CHECK = "ops/launchd/install.sh --check-launchd"


def section(heading: str) -> str:
    """The runbook from `heading` to the next heading of its level or above, heading left off."""
    text = RUNBOOK.read_text(encoding="utf-8")
    level = len(heading) - len(heading.lstrip("#"))
    start = text.index(f"\n{heading}\n") + len(heading) + 2
    following = re.compile(rf"^#{{1,{level}}} ", re.MULTILINE).search(text, start)
    return text[start : following.start() if following else len(text)]


def commands_in(text: str) -> list[str]:
    """Every line of every `bash` block of `text`, in order."""
    return [
        line.strip()
        for block in re.findall(r"```bash\n(.*?)```", text, flags=re.DOTALL)
        for line in block.splitlines()
        if line.strip()
    ]


def on_one_line(text: str) -> str:
    """Prose as it reads, with the line breaks and block-quote marks of the Markdown taken out."""
    return " ".join(text.replace("\n> ", " ").replace("\n", " ").split())


def test_the_reinstall_steps_check_the_profile_before_the_agent_is_replaced_and_under_launchd_after() -> None:
    commands = commands_in(section("## Reinstalling the agent"))

    def first(fragment: str) -> int:
        found = [index for index, command in enumerate(commands) if fragment in command]
        assert found, f"the reinstall steps run nothing containing {fragment!r}: {commands}"
        return found[0]

    profile_check = first(PROFILE_CHECK)
    install = first("ops/launchd/install.sh --caselist")
    bootout, bootstrap = first("launchctl bootout"), first("launchctl bootstrap")
    launchd_check = first(LAUNCHD_CHECK)
    assert profile_check < install < bootout < bootstrap < launchd_check, commands
    assert "env -i" in commands[profile_check], "the profile is checked as the agent will run"
    assert "DEBATE_ENV=prod" in commands[profile_check]


def test_the_reinstall_steps_say_what_each_check_shows_and_what_fails_it() -> None:
    steps = on_one_line(section("## Reinstalling the agent"))

    assert "STORE_PROFILE_NOT_CONFIGURED" in steps
    assert "storage.s3.aws_profile" in steps
    assert "DebateProdEvidenceOperator" in steps, "the permission set the prod agent should show"
    assert "expired" in steps and "does not fail" in steps


def test_the_section_on_a_missing_profile_says_the_run_is_recorded_announced_and_published_later() -> None:
    told = on_one_line(section("### A profile the AWS config does not define"))

    assert "no run is recorded" not in told, "true until v1-e34-t22, and the opposite of true now"
    assert "no notification is sent" not in told
    assert sync_runs.NEEDS_A_PERSON_TITLE in told
    assert sync_runs.SYNC_RUN_LOG_FILENAME in told and sync_runs.SYNC_RUN_DETAILS_FILENAME in told
    assert "STORE_PROFILE_NOT_CONFIGURED" in told
    assert "caselist pull --publish-pending" in told
    assert PROFILE_CHECK in told
    assert "runs --remote" not in told, "the workaround v1-e29-t07 described is replaced by the check"


def test_the_banner_the_runbook_quotes_is_the_one_a_refused_run_sends() -> None:
    """Built by the run monitor's own code, from what the S3 adapter raises for the prod profile."""
    refusal = translate_s3_error(
        ProfileNotFound(profile="debate-prod-evidence"),
        S3Call(
            operation="CreateSession",
            bucket="",
            entity="AWS session",
            key="",
            profile="debate-prod-evidence",
            profile_setting="storage.s3.aws_profile",
        ),
    )
    at = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)
    record = sync_runs.record_for_failure(
        refusal,
        run_id="20261014T100000Z",
        started_at=at,
        finished_at=at,
        environment="prod",
        mode="run",
        caselists=("hsld26",),
    )
    details = sync_runs.details_for_failure(refusal, run_id="20261014T100000Z")
    [banner] = sync_runs.notifications_for(
        record,
        details,
        aws_login_command="aws sso login --profile debate-prod-evidence",
        credentials_expired=False,
        may_succeed_on_retry=codes_exit_as_a_retrieval_failure,
    )
    told = on_one_line(section("### A profile the AWS config does not define"))

    assert banner.title == sync_runs.NEEDS_A_PERSON_TITLE
    assert banner.message in told
    assert banner.hint is not None and banner.hint in told


def test_troubleshooting_has_an_entry_for_it_that_names_the_check() -> None:
    wrong = on_one_line(section("## When something goes wrong"))

    assert "StoreProfileNotConfigured" in wrong
    assert PROFILE_CHECK in wrong
    assert "[A profile the AWS config does not define](#a-profile-the-aws-config-does-not-define)" in wrong


def test_the_launchd_check_is_described_as_checking_the_profile() -> None:
    told = on_one_line(section("## Step 3 — enable it"))

    assert PROFILE_CHECK in told
    assert "exit code 1" in told.lower() or "exit code of 1" in told.lower()
