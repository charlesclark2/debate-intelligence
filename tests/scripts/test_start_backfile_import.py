"""Tests for `ops/caselist_run/start_backfile_import.py`, which starts one backfile import (`v1-e40-t09`).

The script drives the `aws` CLI, so here `aws` is a stand-in that records each call and answers as
AWS would: the lock's body for `s3api get-object`, a task definition for `ecs describe-task-definition`
and a started task for `ecs run-task`. Nothing here reaches AWS. The account, ids and digests are
invented.

What is worth asserting, and why (the PM's rulings of 2026-10-27):

* outside the window, with the lock free, it starts the run's own task definition, at a revision it
  names, with `v1-e34-t34`'s command and nothing else overridden, and prints the task and how to watch it;
* inside the no-import window it starts nothing and asks AWS nothing, and its window is
  `backfile_import.in_no_import_window` exactly, at every quarter hour of a year with both changes of
  daylight saving time;
* while a run holds the bucket's lock it starts nothing; a lease long expired is not held;
* a revision that is not the run's (another family, another role, an image by tag) is never started;
* it reads the lock as the everyday evidence profile and starts the task as the run deployer, and
  makes no other call: no schedule, no rule, no role.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any, Final

import pytest

from debate_core.application.caselist.backfile_import import in_no_import_window, no_import_window_ends

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "ops" / "caselist_run" / "start_backfile_import.py"

ACCOUNT: Final = "111122223333"
DIGEST: Final = "sha256:" + "4" * 64
REVISION_ARN: Final = f"arn:aws:ecs:us-east-1:{ACCOUNT}:task-definition/debate-dev-caselist-run:12"
TASK_ARN: Final = (
    f"arn:aws:ecs:us-east-1:{ACCOUNT}:task/debate-dev-caselist-run/0123456789abcdef0123456789abcdef"
)
SUBNETS: Final = "subnet-0aa,subnet-0bb"
SECURITY_GROUP: Final = "sg-0cc"

ON_A_THURSDAY: Final = datetime(2026, 11, 5, 15, 0, tzinfo=UTC)
"""09:00 in Chicago, the Thursday after a weekly run: outside the window."""
ON_A_WEDNESDAY: Final = datetime(2026, 11, 4, 18, 0, tzinfo=UTC)


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("start_backfile_import", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


script = load_script()


def lock_body(state: str = "free", **changed: object) -> dict[str, object]:
    body: dict[str, object] = {
        "format_version": 1,
        "home_environment": "dev",
        "state": state,
        "holder": None,
        "acquired_at": None,
        "renewed_at": None,
        "lease_expires_at": None,
        "took_over_from": None,
    }
    if state == "held":
        body["holder"] = {
            "kind": "cloud",
            "run_id": "20261105T140000Z",
            "task": None,
            "command": "caselist pull",
        }
        body["lease_expires_at"] = (ON_A_THURSDAY + timedelta(minutes=20)).isoformat()
    body.update(changed)
    return body


def task_definition(**changed: object) -> dict[str, object]:
    definition: dict[str, object] = {
        "taskDefinitionArn": REVISION_ARN,
        "family": "debate-dev-caselist-run",
        "revision": 12,
        "status": "ACTIVE",
        "taskRoleArn": f"arn:aws:iam::{ACCOUNT}:role/debate-dev-caselist-run",
        "executionRoleArn": f"arn:aws:iam::{ACCOUNT}:role/debate-dev-caselist-run-execution",
        "containerDefinitions": [
            {
                "name": "run",
                "image": f"{ACCOUNT}.dkr.ecr.us-east-1.amazonaws.com/debate-dev-caselist-run@{DIGEST}",
                "entryPoint": ["timeout", "--signal=TERM", "--kill-after=120s", "6h", "debate-research"],
                "command": ["--json", "caselist", "pull"],
            }
        ],
        "ephemeralStorage": {"sizeInGiB": 100},
    }
    definition.update(changed)
    return definition


class StandInAws:
    """`aws`, answering as AWS would, and recording each call."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.lock: dict[str, object] | None = lock_body()
        self.definition: dict[str, object] = task_definition()
        self.run_task: dict[str, object] = {"tasks": [{"taskArn": TASK_ARN}], "failures": []}

    def __call__(self, arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
        call = list(arguments)
        self.calls.append(call)
        if call[:2] == ["s3api", "get-object"]:
            if self.lock is None:
                return self.answer(
                    255, stderr="An error occurred (AccessDenied) when calling the GetObject operation"
                )
            Path(call[-1]).write_text(json.dumps(self.lock), encoding="utf-8")
            return self.answer(0, stdout=json.dumps({"ContentLength": 1}))
        if call[:2] == ["ecs", "describe-task-definition"]:
            return self.answer(0, stdout=json.dumps({"taskDefinition": self.definition}))
        if call[:2] == ["ecs", "run-task"]:
            return self.answer(0, stdout=json.dumps(self.run_task))
        return self.answer(252, stderr=f"the stand-in does not answer {call[:2]}")

    @staticmethod
    def answer(code: int, *, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=["aws"], returncode=code, stdout=stdout, stderr=stderr)

    def kinds(self) -> list[str]:
        return [" ".join(call[:2]) for call in self.calls]

    def option(self, kind: str, name: str) -> str:
        [call] = [call for call in self.calls if " ".join(call[:2]) == kind]
        return call[call.index(name) + 1]


def start(
    aws: StandInAws,
    *extra: str,
    now: datetime = ON_A_THURSDAY,
    caselist: str = "hspolicy25",
    env: str = "dev",
) -> int:
    argv = [
        "--env",
        env,
        "--caselist",
        caselist,
        "--subnets",
        SUBNETS,
        "--security-group",
        SECURITY_GROUP,
        *extra,
    ]
    return int(script.main(argv, now=now, aws=aws))


def refused(capsys: pytest.CaptureFixture[str]) -> str:
    [line] = [line for line in capsys.readouterr().out.splitlines() if line.startswith("REFUSED: ")]
    return line


# ------------------------------------------------------------------------------------------------
# A start
# ------------------------------------------------------------------------------------------------


def test_outside_the_window_with_the_lock_free_it_starts_the_runs_revision_with_the_import_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    aws = StandInAws()

    assert start(aws) == 0

    assert aws.kinds() == ["s3api get-object", "ecs describe-task-definition", "ecs run-task"]
    assert aws.option("ecs run-task", "--task-definition") == REVISION_ARN, "the revision it printed, by ARN"
    assert aws.option("ecs run-task", "--cluster") == "debate-dev-caselist-run"
    assert aws.option("ecs run-task", "--started-by") == "backfile-import"
    assert json.loads(aws.option("ecs run-task", "--overrides")) == {
        "containerOverrides": [
            {
                "name": "run",
                "command": ["--json", "caselist", "backfile-import", "--caselist", "hspolicy25", "--execute"],
            }
        ]
    }, "the command and nothing else: the run's entry point, deadline, role and storage stay"
    assert aws.option("ecs run-task", "--network-configuration") == (
        "awsvpcConfiguration={subnets=[subnet-0aa,subnet-0bb],securityGroups=[sg-0cc],assignPublicIp=ENABLED}"
    )
    printed = capsys.readouterr().out
    assert f"task definition: {REVISION_ARN} (revision 12)" in printed
    assert f"image digest: {DIGEST}" in printed
    assert f"started {TASK_ARN}" in printed
    assert "task id: 0123456789abcdef0123456789abcdef" in printed
    assert "aws ecs describe-tasks --profile debate-dev-caselist-run-deployer" in printed
    assert "--log-stream-names run/run/0123456789abcdef0123456789abcdef" in printed


def test_it_reads_the_lock_as_the_everyday_profile_and_starts_the_task_as_the_deployer() -> None:
    aws = StandInAws()

    assert start(aws) == 0

    assert aws.option("s3api get-object", "--profile") == "debate-dev-evidence"
    assert aws.option("s3api get-object", "--bucket") == "debate-dev-evidence-a7508de8"
    assert aws.option("s3api get-object", "--key") == "reports/sync/run-lock.json"
    assert aws.option("ecs describe-task-definition", "--profile") == "debate-dev-caselist-run-deployer"
    assert aws.option("ecs run-task", "--profile") == "debate-dev-caselist-run-deployer"


def test_a_dry_run_starts_the_import_without_execute() -> None:
    aws = StandInAws()

    assert start(aws, "--dry-run") == 0

    command = json.loads(aws.option("ecs run-task", "--overrides"))["containerOverrides"][0]["command"]
    assert command == ["--json", "caselist", "backfile-import", "--caselist", "hspolicy25"]


def test_a_named_revision_is_the_one_read_and_started() -> None:
    aws = StandInAws()
    named = REVISION_ARN.replace(":12", ":9")
    aws.definition = task_definition(taskDefinitionArn=named, revision=9)

    assert start(aws, "--task-definition", named) == 0

    assert aws.option("ecs describe-task-definition", "--task-definition") == named
    assert aws.option("ecs run-task", "--task-definition") == named


def test_without_a_named_revision_it_reads_the_familys_newest_active_one() -> None:
    aws = StandInAws()

    assert start(aws) == 0

    assert aws.option("ecs describe-task-definition", "--task-definition") == "debate-dev-caselist-run"


def test_prod_asks_for_its_confirmation_and_passes_it_to_the_import(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as refused_here:
        start(StandInAws(), env="prod")
    assert refused_here.value.code == 2
    assert "--confirm-prod" in capsys.readouterr().err

    aws = StandInAws()
    aws.lock = lock_body(home_environment="prod")
    aws.definition = task_definition(
        family="debate-prod-caselist-run", taskRoleArn=f"arn:aws:iam::{ACCOUNT}:role/debate-prod-caselist-run"
    )
    assert start(aws, "--confirm-prod", env="prod") == 0
    assert aws.option("s3api get-object", "--profile") == "debate-prod-evidence"
    command = json.loads(aws.option("ecs run-task", "--overrides"))["containerOverrides"][0]["command"]
    assert command[-2:] == ["--execute", "--confirm-prod"]


@pytest.mark.parametrize(
    "argv",
    [
        ["--caselist", "hspolicy-25"],
        ["--subnets", "subnet-0aa subnet-0bb"],
        ["--security-group", "sg-0cc,sg-0dd"],
    ],
)
def test_arguments_it_cannot_use_are_refused_before_any_call(argv: list[str]) -> None:
    aws = StandInAws()
    full = {
        "--env": "dev",
        "--caselist": "hspolicy25",
        "--subnets": SUBNETS,
        "--security-group": SECURITY_GROUP,
    }
    full[argv[0]] = argv[1]

    with pytest.raises(SystemExit) as stopped:
        script.main([part for pair in full.items() for part in pair], now=ON_A_THURSDAY, aws=aws)

    assert stopped.value.code == 2
    assert aws.calls == []


# ------------------------------------------------------------------------------------------------
# The window
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 11, 3, 12, 0, tzinfo=UTC),  # Tuesday 06:00 Chicago, CST: the window opens
        ON_A_WEDNESDAY,
        datetime(2026, 11, 5, 5, 59, tzinfo=UTC),  # Wednesday 23:59 Chicago
    ],
)
def test_inside_the_no_import_window_it_starts_nothing_and_asks_aws_nothing(
    capsys: pytest.CaptureFixture[str], now: datetime
) -> None:
    aws = StandInAws()

    assert start(aws, now=now) == 1

    line = refused(capsys)
    assert "inside the no-import window" in line and "2026-11-05T00:00:00-06:00" in line
    assert aws.calls == []


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 11, 3, 11, 59, tzinfo=UTC),  # Tuesday 05:59 Chicago
        datetime(2026, 11, 5, 6, 0, tzinfo=UTC),  # Thursday 00:00 Chicago: the window has closed
    ],
)
def test_either_side_of_the_window_it_starts(now: datetime) -> None:
    assert start(StandInAws(), now=now) == 0


def test_its_window_is_the_imports_own_at_every_quarter_hour_of_a_year() -> None:
    """Both changes of daylight saving time included: 2026-03-08 and 2026-11-01 in Chicago."""
    moment, end, checked = datetime(2026, 1, 1, tzinfo=UTC), datetime(2027, 1, 1, tzinfo=UTC), 0
    while moment < end:
        assert script.in_no_import_window(moment) == in_no_import_window(moment), moment
        if in_no_import_window(moment):
            assert script.window_closes(moment) == no_import_window_ends(moment), moment
        moment += timedelta(minutes=15)
        checked += 1
    assert checked == 365 * 96


# ------------------------------------------------------------------------------------------------
# The lock
# ------------------------------------------------------------------------------------------------


def test_while_a_run_holds_the_lock_it_starts_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    aws = StandInAws()
    aws.lock = lock_body("held")

    assert start(aws) == 1

    line = refused(capsys)
    assert "held by cloud run 20261105T140000Z (`caselist pull`)" in line
    assert aws.kinds() == ["s3api get-object"]


def test_a_lease_inside_the_skew_margin_is_still_held() -> None:
    aws = StandInAws()
    aws.lock = lock_body("held", lease_expires_at=(ON_A_THURSDAY - timedelta(minutes=4)).isoformat())

    assert start(aws) == 1
    assert aws.kinds() == ["s3api get-object"]


def test_a_lease_that_ran_out_past_the_skew_margin_is_not_held_and_the_task_takes_it_over() -> None:
    aws = StandInAws()
    aws.lock = lock_body("held", lease_expires_at=(ON_A_THURSDAY - timedelta(minutes=6)).isoformat())

    assert start(aws) == 0


@pytest.mark.parametrize(
    ("lock", "reason"),
    [
        (lock_body(home_environment="prod"), "the run lock's home is 'prod', not 'dev'"),
        (
            lock_body(
                "held",
                holder={"kind": "moved", "run_id": "x", "command": "caselist move-home"},
                lease_expires_at="9999-12-31T00:00:00+00:00",
            ),
            "held for good",
        ),
        (lock_body("unknown"), "neither held nor free"),
        (None, "could not read the bucket's run lock as debate-dev-evidence"),
    ],
)
def test_a_lock_it_cannot_read_or_another_homes_lock_starts_nothing(
    capsys: pytest.CaptureFixture[str], lock: dict[str, object] | None, reason: str
) -> None:
    aws = StandInAws()
    aws.lock = lock

    assert start(aws) == 1

    assert reason in refused(capsys)
    assert aws.kinds() == ["s3api get-object"]


# ------------------------------------------------------------------------------------------------
# The revision
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("changed", "reason"),
    [
        ({"family": "debate-dev-caselist-login"}, "its family is 'debate-dev-caselist-login'"),
        (
            {"taskRoleArn": f"arn:aws:iam::{ACCOUNT}:role/debate-dev-caselist-login"},
            "task role is not the run role",
        ),
        ({"status": "INACTIVE"}, "not ACTIVE"),
        (
            {"containerDefinitions": [{"name": "run", "image": "debate-dev-caselist-run:v1.8.0"}]},
            "not pinned by digest",
        ),
        ({"containerDefinitions": [{"name": "login", "image": f"x@{DIGEST}"}]}, "not named 'run'"),
    ],
)
def test_a_revision_that_is_not_the_runs_is_never_started(
    capsys: pytest.CaptureFixture[str], changed: dict[str, Any], reason: str
) -> None:
    aws = StandInAws()
    aws.definition = task_definition(**changed)

    assert start(aws) == 1

    assert reason in refused(capsys)
    assert "ecs run-task" not in aws.kinds()


def test_a_start_ecs_could_not_place_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    aws = StandInAws()
    aws.run_task = {"tasks": [], "failures": [{"reason": "RESOURCE:CPU"}]}

    assert start(aws) == 1

    assert "started 0 task(s)" in refused(capsys)


# ------------------------------------------------------------------------------------------------
# As the operator runs it
# ------------------------------------------------------------------------------------------------


def test_it_runs_as_the_runbook_runs_it_isolated_with_aws_from_path(tmp_path: Path) -> None:
    """`python3 -I`, the standard library only, and `aws` found on PATH; this clock, not a test's."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "aws"
    fake.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        "argv = sys.argv[1:]\n"
        "if argv[:2] == ['s3api', 'get-object']:\n"
        f"    open(argv[-1], 'w').write({json.dumps(json.dumps(lock_body()))})\n"
        "elif argv[:2] == ['ecs', 'describe-task-definition']:\n"
        f"    print({json.dumps(json.dumps({'taskDefinition': task_definition()}))})\n"
        "elif argv[:2] == ['ecs', 'run-task']:\n"
        f"    print({json.dumps(json.dumps({'tasks': [{'taskArn': TASK_ARN}], 'failures': []}))})\n"
        "else:\n"
        "    sys.exit(252)\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    ran = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "--env", "dev", "--caselist", "hspolicy25",
         "--subnets", SUBNETS, "--security-group", SECURITY_GROUP, "--dry-run"],
        capture_output=True, text=True, check=False, cwd=tmp_path,
        env={"PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin", "HOME": str(tmp_path)},
    )  # fmt: skip

    if in_no_import_window(datetime.now(UTC)):
        assert ran.returncode == 1 and "REFUSED: inside the no-import window" in ran.stdout, ran
    else:
        assert ran.returncode == 0, ran
        assert f"started {TASK_ARN}" in ran.stdout
