"""The weekly schedule starts its pull with `--scheduled` (`v1-e40-t48`, the PM's ruling of 2026-11-14).

AWS's Scheduler pages do not say a templated ECS target's Input reaches RunTask as overrides (read
2026-11-13), so the run's schedule became Scheduler's universal RunTask target,
`arn:aws:scheduler:::aws-sdk:ecs:runTask`, whose Input is the whole RunTask request with the run
container's command overridden. The module's own plan-time test
(`infrastructure/modules/caselist_run/tests/caselist_run.tftest.hcl`,
`the_run_schedule_starts_its_pull_with_scheduled`) pins that request whole; Terraform runs it, in CI's
`terraform-checks` job. This file holds what Python can check:

* **The module's source** names `--scheduled` in the schedule's command and sends it through the
  universal target, read as text the way `test_model_spend_budget_grants_nothing.py` reads its module,
  so a pull request's Python tests see a change that drops it.
* **`ops/caselist_run/check_image_plan.py` learns the universal shape.** The plan that makes this
  change moves the run schedule from the ECS template to the universal target, which only the new
  `--universal-target` mode passes. Every later image plan repoints a universal run schedule, whose
  Input names the new revision and so is known only after the apply. Under the universal shape an
  Input already known in the plan names a revision registered earlier, and every mode refuses it, as
  `--memory` refuses a known revision under the template (`v1-e41-t13` gives the image mode that rule
  for the template).

The plans here reuse the image check's own synthetic plans
(`tests/scripts/test_caselist_run_image_plan_check.py`, unchanged); every plan is written by hand. No
account, no real ARN, nothing from a real plan.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

import pytest
from tests.scripts.test_caselist_run_image_plan_check import (
    ACCOUNT,
    LOGIN_SCHEDULE,
    OWNER,
    RUN_DEFINITION,
    RUN_SCHEDULE,
    SCRIPT,
    Plan,
    change_of,
    changed_instead,
    entry,
    image_plan,
    memory_plan,
    schedule_side,
)

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
RUN_TASK_TF: Final = REPO_ROOT / "infrastructure" / "modules" / "caselist_run" / "run_task.tf"

UNIVERSAL: Final = "arn:aws:scheduler:::aws-sdk:ecs:runTask"
SCHEDULED: Final = ["--json", "caselist", "pull", "--scheduled"]
REVISIONS: Final = f"arn:aws:ecs:us-east-1:{ACCOUNT}:task-definition/debate-dev-caselist-run:"
KNOWN_REVISION_12: Final = (
    f"{RUN_SCHEDULE} starts debate-dev-caselist-run:12, a revision known before the apply, not the new one"
)


def write_owner_and_plan(plan: Plan, tmp_path: Path) -> tuple[Path, Path]:
    plan_file, owner_file = tmp_path / "plan.json", tmp_path / "owner.auto.tfvars"
    plan_file.write_text(json.dumps(plan), encoding="utf-8")
    owner_file.write_text(OWNER, encoding="utf-8")
    return plan_file, owner_file


def run_check(plan: Plan, tmp_path: Path, *flags: str) -> tuple[int, str]:
    plan_file, owner_file = write_owner_and_plan(plan, tmp_path)
    ran = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), str(plan_file), str(owner_file), *flags],
        capture_output=True,
        text=True,
        check=False,
    )
    assert ran.stderr == "", ran.stderr
    [line] = ran.stdout.splitlines()
    return ran.returncode, line


# ------------------------------------------------------------------------------------------------
# The module's source
# ------------------------------------------------------------------------------------------------


def hcl_list(text: str, name: str) -> list[str]:
    """The string list a `name = [...]` line of run_task.tf assigns."""
    [found] = re.findall(rf"^\s*{re.escape(name)}\s*=\s*\[([^\]\n]*)\]\s*$", text, flags=re.MULTILINE)
    return re.findall(r'"([^"]*)"', found)


def schedule_target_block(text: str) -> str:
    start = text.index('resource "aws_scheduler_schedule" "run" {')
    target = text.index("  target {", start)
    return text[target : text.index("\n  }\n", target)]


def test_the_schedules_command_is_the_pull_with_scheduled() -> None:
    text = RUN_TASK_TF.read_text(encoding="utf-8")

    assert hcl_list(text, "run_scheduled_command") == SCHEDULED
    assert (
        "containerOverrides = [{ name = local.run_container_name, command = local.run_scheduled_command }]"
        in text
    )


def test_the_schedule_sends_it_through_the_universal_run_task_target() -> None:
    text = RUN_TASK_TF.read_text(encoding="utf-8")
    target = schedule_target_block(text)

    assert 'run_task_target_arn = "arn:${local.partition}:scheduler:::aws-sdk:ecs:runTask"' in text
    assert re.search(r"^\s*arn\s*=\s*local\.run_task_target_arn$", target, flags=re.MULTILINE), target
    assert re.search(r"^\s*input\s*=\s*jsonencode\(local\.run_task_request\)$", target, flags=re.MULTILINE), (
        target
    )
    assert "ecs_parameters" not in target


def test_a_run_by_hand_keeps_the_task_definitions_command() -> None:
    text = RUN_TASK_TF.read_text(encoding="utf-8")

    assert hcl_list(text, "command") == ["--json", "caselist", "pull"]


# ------------------------------------------------------------------------------------------------
# Synthetic plans: the run schedule on the universal target
# ------------------------------------------------------------------------------------------------


def request(revision: int, command: list[str] = SCHEDULED) -> str:
    """The universal target's Input as Terraform's jsonencode writes it, naming one known revision."""
    return json.dumps(
        {
            "cluster": "arn:cluster",
            "count": 1,
            "enableECSManagedTags": False,
            "enableExecuteCommand": False,
            "launchType": "FARGATE",
            "networkConfiguration": {
                "awsvpcConfiguration": {
                    "assignPublicIp": "ENABLED",
                    "securityGroups": ["sg-1"],
                    "subnets": ["subnet-1", "subnet-2"],
                }
            },
            "overrides": {"containerOverrides": [{"command": command, "name": "run"}]},
            "platformVersion": "LATEST",
            "taskDefinition": f"{REVISIONS}{revision}",
        },
        separators=(",", ":"),
    )


def universal_side(state: str, input_: str | None) -> dict[str, object]:
    """A run schedule side on the universal target; no Input when the plan cannot know it yet."""
    side = schedule_side("run", state, arn=False)
    target: dict[str, object] = {"arn": UNIVERSAL, "role_arn": "arn:scheduler-role", "ecs_parameters": []}
    if input_ is not None:
        target["input"] = input_
    side["target"] = [target]
    return side


def moved_run_schedule() -> dict[str, Any]:
    """t48's change: the template's target before, the universal one after, its Input unknown (the run
    task definition is replaced in the same plan)."""
    return entry(
        RUN_SCHEDULE,
        ["update"],
        schedule_side("run", "ENABLED", arn=True),
        universal_side("ENABLED", None),
        target=[{"ecs_parameters": [], "input": True}],
    )


def repointed_universal_run_schedule() -> dict[str, Any]:
    """A later image plan: the universal target before and after, the Input unknown after."""
    return entry(
        RUN_SCHEDULE,
        ["update"],
        universal_side("ENABLED", request(15)),
        universal_side("ENABLED", None),
        target=[{"ecs_parameters": [], "input": True}],
    )


def move_plan() -> Plan:
    """t48's plan in dev: a new image, and the run schedule moved onto the universal target."""
    plan = image_plan()
    changed_instead(plan, moved_run_schedule())
    return plan


def later_image_plan() -> Plan:
    """A new image after t48's apply: the run schedule's universal target repointed."""
    plan = image_plan()
    changed_instead(plan, repointed_universal_run_schedule())
    return plan


def later_memory_plan() -> Plan:
    plan = memory_plan()
    changed_instead(plan, repointed_universal_run_schedule())
    return plan


def input_known(revision: int, command: list[str] = SCHEDULED) -> Callable[[Plan], None]:
    """The run schedule's Input already known in the plan: it names a revision registered earlier."""

    def change(plan: Plan) -> None:
        schedule = change_of(plan, RUN_SCHEDULE)
        schedule["after"]["target"][0]["input"] = request(revision, command)
        schedule["after_unknown"] = {"target": [{"ecs_parameters": []}]}

    return change


def run_target_after(**changed: object) -> Callable[[Plan], None]:
    return lambda plan: change_of(plan, RUN_SCHEDULE)["after"]["target"][0].update(changed)


# ------------------------------------------------------------------------------------------------
# --universal-target: the plan that moves the run schedule (t48's, once)
# ------------------------------------------------------------------------------------------------


def test_the_move_is_plan_ok_with_universal_target(tmp_path: Path) -> None:
    code, said = run_check(move_plan(), tmp_path, "--universal-target")

    assert said == (
        "PLAN OK: 2 to add, 4 to change, 2 to destroy; the login and run task definitions replaced "
        "with the image sha256:222222222222... and nothing else in them changed; the login schedule and "
        "the two roles' policies repointed at the new revisions; the run schedule moved onto Scheduler's "
        "universal RunTask target, its role and every other target setting as before, and its Input, "
        "which names the new revision, known only after the apply: read it back after the apply; both "
        "schedules ENABLED throughout; nothing else changes"
    ), said
    assert code == 0


def test_the_image_check_refuses_the_move(tmp_path: Path) -> None:
    code, said = run_check(move_plan(), tmp_path)

    assert said == (
        f"PLAN STOP: {RUN_SCHEDULE} moves its target onto Scheduler's universal RunTask target, which "
        "only --universal-target passes, for the run schedule"
    ), said
    assert code == 1


def test_the_memory_check_refuses_the_move(tmp_path: Path) -> None:
    plan = memory_plan()
    changed_instead(plan, moved_run_schedule())

    code, said = run_check(plan, tmp_path, "--memory")

    assert said.startswith("PLAN STOP: "), said
    assert f"{RUN_SCHEDULE} moves its target onto Scheduler's universal RunTask target" in said, said
    assert code == 1


def test_the_universal_target_check_refuses_the_image_plan_that_does_not_move(tmp_path: Path) -> None:
    code, said = run_check(image_plan(), tmp_path, "--universal-target")

    assert said == (
        f"PLAN STOP: {RUN_SCHEDULE}'s target is the ECS template -> the ECS template, expected the ECS "
        "template -> Scheduler's universal RunTask target"
    ), said
    assert code == 1


def test_the_universal_target_check_refuses_a_later_image_plan(tmp_path: Path) -> None:
    code, said = run_check(later_image_plan(), tmp_path, "--universal-target")

    assert said == (
        f"PLAN STOP: {RUN_SCHEDULE}'s target is Scheduler's universal RunTask target -> Scheduler's "
        "universal RunTask target, expected the ECS template -> Scheduler's universal RunTask target"
    ), said
    assert code == 1


def the_login_moved_too(plan: Plan) -> None:
    schedule = change_of(plan, LOGIN_SCHEDULE)
    schedule["after"]["target"] = [{"arn": UNIVERSAL, "role_arn": "arn:scheduler-role", "ecs_parameters": []}]
    schedule["after_unknown"] = {"target": [{"ecs_parameters": [], "input": True}]}


def the_task_definition_updated_in_place(plan: Plan) -> None:
    change_of(plan, RUN_DEFINITION)["actions"] = ["update"]


def the_schedule_replaced(plan: Plan) -> None:
    change_of(plan, RUN_SCHEDULE)["actions"] = ["delete", "create"]


def the_schedule_disabled(plan: Plan) -> None:
    change_of(plan, RUN_SCHEDULE)["after"]["state"] = "DISABLED"


def another_schedule_setting(plan: Plan) -> None:
    change_of(plan, RUN_SCHEDULE)["after"]["schedule_expression"] = "cron(0 6 ? * TUE *)"


MOVE_STOPS: Final[dict[str, tuple[Callable[[Plan], None], str]]] = {
    "an Input already known names an old revision": (
        input_known(12),
        KNOWN_REVISION_12,
    ),
    "the templated ECS parameters left beside the universal target": (
        run_target_after(ecs_parameters=[{"task_count": 1, "launch_type": "FARGATE"}]),
        f"{RUN_SCHEDULE} keeps templated ECS parameters beside the universal target",
    ),
    "another role": (
        run_target_after(role_arn="arn:another-role"),
        f"{RUN_SCHEDULE} also changes its target's ['role_arn']",
    ),
    "the retries dropped": (
        lambda plan: change_of(plan, RUN_SCHEDULE)["before"]["target"][0].update(
            retry_policy=[{"maximum_retry_attempts": 3, "maximum_event_age_in_seconds": 3600}]
        ),
        f"{RUN_SCHEDULE} also changes its target's ['retry_policy']",
    ),
    "a templated target of another kind": (
        run_target_after(arn="arn:cluster"),
        f"{RUN_SCHEDULE}'s target is the ECS template -> the ECS template, expected the ECS template -> "
        "Scheduler's universal RunTask target",
    ),
    "a universal target for another API": (
        run_target_after(arn="arn:aws:scheduler:::aws-sdk:ecs:stopTask"),
        f"{RUN_SCHEDULE}'s target is the ECS template -> the ECS template, expected the ECS template -> "
        "Scheduler's universal RunTask target",
    ),
    "the schedule replaced, not updated": (
        the_schedule_replaced,
        f"{RUN_SCHEDULE}: delete/create, expected an update",
    ),
    "a schedule setting beside the target": (
        another_schedule_setting,
        f"{RUN_SCHEDULE} changes ['schedule_expression', 'target'], expected only target",
    ),
    "the run schedule disabled": (
        the_schedule_disabled,
        f"{RUN_SCHEDULE} is ENABLED -> DISABLED, expected ENABLED throughout",
    ),
    "the login moved as well": (
        the_login_moved_too,
        f"{LOGIN_SCHEDULE} moves its target onto Scheduler's universal RunTask target, which only "
        "--universal-target passes, for the run schedule",
    ),
    "the run task definition updated in place": (
        the_task_definition_updated_in_place,
        f"{RUN_DEFINITION}: update, expected a replace (delete and create)",
    ),
}


@pytest.mark.parametrize("case", MOVE_STOPS)
def test_any_other_move_is_plan_stop_naming_the_change(tmp_path: Path, case: str) -> None:
    plan = move_plan()
    change, expected = MOVE_STOPS[case]
    change(plan)

    code, said = run_check(plan, tmp_path, "--universal-target")

    assert said.startswith("PLAN STOP: "), said
    assert expected in said, said
    assert code == 1


def test_the_move_still_refuses_what_the_image_check_refuses(tmp_path: Path) -> None:
    """Identity Center, outside the module, an unexpected change: the image check's screening, kept."""
    plan = move_plan()
    plan["resource_changes"] += [
        entry('aws_ssoadmin_account_assignment.evidence_operator["coach"]', ["delete"], {"id": "x"}, None),
        entry(
            "module.evidence_bucket.aws_s3_bucket_policy.this", ["update"], {"policy": "a"}, {"policy": "b"}
        ),
    ]

    code, said = run_check(plan, tmp_path, "--universal-target")

    assert said.startswith("PLAN STOP: "), said
    assert "an Identity Center change, which never passes" in said, said
    assert "a change outside module.caselist_run: module.evidence_bucket.aws_s3_bucket_policy.this" in said
    assert code == 1


def test_universal_target_and_memory_together_are_refused(tmp_path: Path) -> None:
    plan_file, owner_file = write_owner_and_plan(move_plan(), tmp_path)

    ran = subprocess.run(
        [
            sys.executable,
            "-I",
            str(SCRIPT),
            str(plan_file),
            str(owner_file),
            "--universal-target",
            "--memory",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert ran.returncode == 2, ran
    assert "not allowed with argument" in ran.stderr, ran.stderr


# ------------------------------------------------------------------------------------------------
# After the move: the image and memory modes read the universal shape
# ------------------------------------------------------------------------------------------------


def test_a_later_image_plan_is_plan_ok_and_says_the_input_is_read_after_the_apply(tmp_path: Path) -> None:
    code, said = run_check(later_image_plan(), tmp_path)

    assert said == (
        "PLAN OK: 2 to add, 4 to change, 2 to destroy; the login and run task definitions replaced "
        "with the image sha256:222222222222... and nothing else in them changed; the two schedules and "
        "their roles' policies repointed at the new revisions; the run schedule's Input, which names the "
        "new revision, known only after the apply: read it back after the apply; both schedules ENABLED "
        "throughout; nothing else changes"
    ), said
    assert code == 0


def test_a_later_memory_plan_is_plan_ok(tmp_path: Path) -> None:
    code, said = run_check(later_memory_plan(), tmp_path, "--memory")

    assert said.startswith("PLAN OK: 1 to add, 2 to change, 1 to destroy"), said
    assert code == 0


LATER_STOPS: Final[dict[str, tuple[Callable[[Plan], None], str]]] = {
    "an Input already known names an old revision": (
        input_known(12),
        KNOWN_REVISION_12,
    ),
    "an Input already known that drops --scheduled": (
        input_known(12, ["--json", "caselist", "pull"]),
        KNOWN_REVISION_12,
    ),
    "the target moved back onto the ECS template": (
        lambda plan: change_of(plan, RUN_SCHEDULE)["after"].update(
            target=schedule_side("run", "ENABLED", arn=False)["target"]
        ),
        f"{RUN_SCHEDULE} moves its target off Scheduler's universal RunTask target",
    ),
    "another role": (
        run_target_after(role_arn="arn:another-role"),
        f"{RUN_SCHEDULE} changes its target beyond the task definition it starts",
    ),
    "templated ECS parameters added": (
        run_target_after(ecs_parameters=[{"task_count": 1}]),
        f"{RUN_SCHEDULE} changes its target beyond the task definition it starts",
    ),
}


@pytest.mark.parametrize("mode", ["image", "memory"])
@pytest.mark.parametrize("case", LATER_STOPS)
def test_a_later_plan_changing_the_universal_target_otherwise_is_plan_stop(
    tmp_path: Path, case: str, mode: str
) -> None:
    plan = later_image_plan() if mode == "image" else later_memory_plan()
    change, expected = LATER_STOPS[case]
    change(plan)

    code, said = run_check(plan, tmp_path, *(["--memory"] if mode == "memory" else []))

    assert said.startswith("PLAN STOP: "), said
    assert expected in said, said
    assert code == 1


def test_the_memory_check_still_refuses_a_known_revision_under_the_template(tmp_path: Path) -> None:
    """v1-e40-t30's rule on the template's shape, unchanged by the universal one."""
    plan = memory_plan()
    schedule = change_of(plan, RUN_SCHEDULE)
    schedule["after"]["target"][0]["ecs_parameters"][0]["task_definition_arn"] = (
        f"arn:aws:ecs:us-east-1:{ACCOUNT}:task-definition/debate-dev-caselist-run:12"
    )
    schedule["after_unknown"] = {}

    code, said = run_check(plan, tmp_path, "--memory")

    assert said.startswith("PLAN STOP: "), said
    assert f"{RUN_SCHEDULE} starts debate-dev-caselist-run:12, a revision known before the apply" in said
    assert code == 1
