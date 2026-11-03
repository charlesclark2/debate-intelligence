"""The cutover runbook's two plan checks, run on synthetic plans (`v1-e40-t06`).

`docs/runbooks/caselist-cutover.md` checks each of the cutover's two remaining applies in
`terraform show -json`'s shape before the PM reads it, as `v1-e40-t02`, `t03` and `t05`'s runbooks
do: `IMAGEPLAN`, step 4's image change, and `SCHEDULEPLAN`, step 8's run schedule turned on (and the
fallback week's off and on again). Each prints `PLAN OK` only for its exact shape. The code is read
out of the runbook, between its heredoc markers, and run as the operator runs it (`python3 -I -`, the
plan's JSON and `owner.auto.tfvars` as its arguments), so a change to the runbook is what is tested.

Every plan here is written by hand in the shape Terraform gives a replaced task definition, a
schedule repointed at its new revision (the revision's ARN unknown until the apply) and a role
policy whose document is unknown: no account, no real ARN, nothing from a real plan.
"""

from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

import pytest

RUNBOOK = Path(__file__).resolve().parents[2] / "docs" / "runbooks" / "caselist-cutover.md"
M: Final = "module.caselist_run."
ACCOUNT: Final = "111122223333"
OLD_DIGEST: Final = "sha256:" + "1" * 64
NEW_DIGEST: Final = "sha256:" + "2" * 64
REPOSITORY: Final = f"{ACCOUNT}.dkr.ecr.us-east-1.amazonaws.com/debate-dev-caselist-run"
OWNER: Final = f'owner = "coach"\ncaselist_image_digest = "{NEW_DIGEST}"\n'

Plan = dict[str, Any]


def check_code(marker: str) -> str:
    """The Python between `<<'MARKER'` and its closing `MARKER` line in the runbook."""
    text = RUNBOOK.read_text(encoding="utf-8")
    [found] = re.findall(rf"<<'{marker}'\n(.*?)\n{marker}\n", text, flags=re.DOTALL)
    return found


def run_check(marker: str, plan: Plan, owner: str, tmp_path: Path) -> str:
    plan_file, owner_file = tmp_path / "plan.json", tmp_path / "owner.auto.tfvars"
    plan_file.write_text(json.dumps(plan), encoding="utf-8")
    owner_file.write_text(owner, encoding="utf-8")
    ran = subprocess.run(
        [sys.executable, "-I", "-", str(plan_file), str(owner_file)],
        input=check_code(marker),
        capture_output=True,
        text=True,
        check=False,
    )
    assert ran.returncode == 0, ran.stderr
    [line] = ran.stdout.splitlines()
    return line


# ------------------------------------------------------------------------------------------------
# Synthetic plans
# ------------------------------------------------------------------------------------------------

ENVIRONMENT: Final = {
    "run": {
        "DEBATE_ENV": "dev",
        "DEBATE_CASELIST__RUN_STATE": "bucket",
        "DEBATE_CASELIST__NOTIFIER": "sns",
        "DEBATE_PARSE__WORKERS": "8",
    },
    "login": {"DEBATE_ENV": "dev", "DEBATE_CASELIST__NOTIFIER": "sns"},
}


def container_definitions(which: str, digest: str, **changed: object) -> str:
    definition: dict[str, object] = {
        "name": which,
        "image": f"{REPOSITORY}@{digest}",
        "essential": True,
        "entryPoint": ["timeout", "--signal=TERM", "--kill-after=120s", "6h", "debate-research"],
        "command": ["--json", "caselist", "pull"] if which == "run" else ["caselist", "auth", "renew"],
        "environment": [{"name": name, "value": value} for name, value in ENVIRONMENT[which].items()],
        "logConfiguration": {
            "logDriver": "awslogs",
            "options": {"awslogs-group": f"debate-dev-caselist-{which}"},
        },
        "linuxParameters": {"initProcessEnabled": True},
    }
    definition.update(changed)
    return json.dumps([definition])


def task_side(which: str, digest: str, **changed: object) -> dict[str, object]:
    return {
        "family": f"debate-dev-caselist-{which}",
        "container_definitions": container_definitions(which, digest, **changed),
        "task_role_arn": f"arn:aws:iam::{ACCOUNT}:role/debate-dev-caselist-{which}",
        "execution_role_arn": f"arn:aws:iam::{ACCOUNT}:role/debate-dev-caselist-{which}-execution",
        "cpu": "8192" if which == "run" else "256",
        "memory": "16384" if which == "run" else "512",
        "network_mode": "awsvpc",
    }


def task_definition(which: str) -> dict[str, object]:
    return {
        "address": f"{M}aws_ecs_task_definition.{which}[0]",
        "change": {
            "actions": ["delete", "create"],
            "before": task_side(which, OLD_DIGEST) | {"arn": "arn:old", "revision": 7},
            "after": task_side(which, NEW_DIGEST),
            "after_unknown": {"arn": True, "revision": True, "id": True},
        },
    }


def schedule_side(which: str, state: str, *, arn: bool) -> dict[str, object]:
    parameters: dict[str, object] = {"task_count": 1, "launch_type": "FARGATE"}
    if arn:
        parameters["task_definition_arn"] = (
            f"arn:aws:ecs:us-east-1:{ACCOUNT}:task-definition/debate-dev-caselist-{which}:7"
        )
    return {
        "name": f"debate-dev-caselist-{which}",
        "state": state,
        "schedule_expression": "cron(0 6 ? * WED *)" if which == "run" else "cron(0 3 ? * WED *)",
        "target": [{"arn": "arn:cluster", "role_arn": "arn:scheduler-role", "ecs_parameters": [parameters]}],
    }


def repointed_schedule(which: str, state: str) -> dict[str, object]:
    return {
        "address": f"{M}aws_scheduler_schedule.{which}[0]",
        "change": {
            "actions": ["update"],
            "before": schedule_side(which, state, arn=True),
            "after": schedule_side(which, state, arn=False),
            "after_unknown": {"target": [{"ecs_parameters": [{"task_definition_arn": True}]}]},
        },
    }


def repointed_policy(name: str) -> dict[str, object]:
    return {
        "address": f"{M}aws_iam_role_policy.{name}[0]",
        "change": {
            "actions": ["update"],
            "before": {
                "name": "start-task",
                "role": f"debate-dev-caselist-{name}",
                "policy": '{"Statement":[]}',
            },
            "after": {"name": "start-task", "role": f"debate-dev-caselist-{name}"},
            "after_unknown": {"policy": True},
        },
    }


def unchanged(address: str) -> dict[str, object]:
    return {
        "address": address,
        "change": {"actions": ["no-op"], "before": {}, "after": {}, "after_unknown": {}},
    }


def image_plan(*, login_state: str = "ENABLED") -> Plan:
    """Step 4's plan as it should be: 2 to add, 4 to change, 2 to destroy."""
    return {
        "resource_changes": [
            task_definition("login"),
            task_definition("run"),
            repointed_schedule("login", login_state),
            repointed_schedule("run", "DISABLED"),
            repointed_policy("scheduler"),
            repointed_policy("run_scheduler"),
            unchanged(f"{M}aws_cloudwatch_metric_alarm.late_run"),
            unchanged("module.evidence_bucket.aws_s3_bucket.this"),
        ]
    }


def schedule_plan(before: str, after: str) -> Plan:
    """Step 8's plan as it should be: the run's schedule's state, and nothing else."""
    side = schedule_side("run", before, arn=True)
    return {
        "resource_changes": [
            {
                "address": f"{M}aws_scheduler_schedule.run[0]",
                "change": {
                    "actions": ["update"],
                    "before": side,
                    "after": side | {"state": after},
                    "after_unknown": {},
                },
            },
            unchanged(f"{M}aws_cloudwatch_metric_alarm.late_run"),
        ]
    }


def change_of(plan: Plan, address: str) -> dict[str, Any]:
    return next(entry["change"] for entry in plan["resource_changes"] if entry["address"] == address)


def run_definition_after(plan: Plan, **changed: object) -> None:
    after = change_of(plan, f"{M}aws_ecs_task_definition.run[0]")["after"]
    after["container_definitions"] = container_definitions("run", NEW_DIGEST, **changed)


# ------------------------------------------------------------------------------------------------
# IMAGEPLAN: step 4, the image change
# ------------------------------------------------------------------------------------------------


def test_the_image_change_as_it_should_be_is_plan_ok(tmp_path: Path) -> None:
    said = run_check("IMAGEPLAN", image_plan(), OWNER, tmp_path)

    assert said.startswith(
        "PLAN OK: 2 to add, 4 to change, 2 to destroy; the two task definitions replaced"
    ), said
    assert "the run's schedule DISABLED and the login's ENABLED; nothing else" in said


def test_with_the_login_paused_the_login_schedule_stays_disabled_and_is_plan_ok(tmp_path: Path) -> None:
    owner = OWNER + "caselist_login_schedule_enabled = false\n"

    said = run_check("IMAGEPLAN", image_plan(login_state="DISABLED"), owner, tmp_path)

    assert said.startswith("PLAN OK"), said
    assert "the login's DISABLED" in said


def environment_added(plan: Plan) -> None:
    run_definition_after(
        plan,
        environment=[{"name": n, "value": v} for n, v in (ENVIRONMENT["run"] | {"DEBATE_X": "1"}).items()],
    )


def environment_changed(plan: Plan) -> None:
    run_definition_after(
        plan,
        environment=[
            {"name": n, "value": v}
            for n, v in (ENVIRONMENT["run"] | {"DEBATE_CASELIST__RUN_STATE": "local"}).items()
        ],
    )


def another_image(plan: Plan) -> None:
    run_definition_after(plan, image=f"{REPOSITORY}@sha256:{'3' * 64}")


def the_same_image(plan: Plan) -> None:
    for which in ("login", "run"):
        change = change_of(plan, f"{M}aws_ecs_task_definition.{which}[0]")
        change["after"]["container_definitions"] = container_definitions(which, OLD_DIGEST)


def another_command(plan: Plan) -> None:
    run_definition_after(plan, command=["--json", "caselist", "pull", "--caselist", "testcl26"])


def another_entry_point(plan: Plan) -> None:
    run_definition_after(plan, entryPoint=["debate-research"])


def another_task_role(plan: Plan) -> None:
    change_of(plan, f"{M}aws_ecs_task_definition.run[0]")["after"]["task_role_arn"] = (
        "arn:aws:iam::x:role/other"
    )


def the_run_schedule_enabled(plan: Plan) -> None:
    change_of(plan, f"{M}aws_scheduler_schedule.run[0]")["after"]["state"] = "ENABLED"


def the_schedule_starting_two_tasks(plan: Plan) -> None:
    after = change_of(plan, f"{M}aws_scheduler_schedule.run[0]")["after"]
    after["target"][0]["ecs_parameters"][0]["task_count"] = 2


def the_schedule_moved_in_time(plan: Plan) -> None:
    change_of(plan, f"{M}aws_scheduler_schedule.run[0]")["after"]["schedule_expression"] = (
        "cron(0 6 ? * TUE *)"
    )


def the_alarm_switched_on(plan: Plan) -> None:
    plan["resource_changes"].append(
        {
            "address": f"{M}aws_cloudwatch_metric_alarm.late_run",
            "change": {
                "actions": ["update"],
                "before": {"actions_enabled": False},
                "after": {"actions_enabled": True},
                "after_unknown": {},
            },
        }
    )
    plan["resource_changes"] = [
        entry
        for entry in plan["resource_changes"]
        if not (entry["address"].endswith("late_run") and entry["change"]["actions"] == ["no-op"])
    ]


def an_account_assignment_destroyed(plan: Plan) -> None:
    plan["resource_changes"].append(
        {
            "address": 'aws_ssoadmin_account_assignment.evidence_operator["coach"]',
            "change": {"actions": ["delete"], "before": {}, "after": None, "after_unknown": {}},
        }
    )


def a_change_outside_the_module(plan: Plan) -> None:
    plan["resource_changes"].append(
        {
            "address": "module.evidence_bucket.aws_s3_bucket_policy.this",
            "change": {
                "actions": ["update"],
                "before": {"policy": "a"},
                "after": {"policy": "b"},
                "after_unknown": {},
            },
        }
    )


def a_task_definition_changed_in_place(plan: Plan) -> None:
    change_of(plan, f"{M}aws_ecs_task_definition.login[0]")["actions"] = ["update"]


def a_policy_changing_its_name(plan: Plan) -> None:
    change_of(plan, f"{M}aws_iam_role_policy.run_scheduler[0]")["after"]["name"] = "everything"


STOPPED: Final[dict[str, tuple[Callable[[Plan], None], str]]] = {
    "an environment variable added": (environment_added, "changes its environment: adds ['DEBATE_X']"),
    "bucket mode taken out": (environment_changed, "changes ['DEBATE_CASELIST__RUN_STATE']"),
    "an image other than the digest": (another_image, "expected the digest in owner.auto.tfvars"),
    "the same image": (the_same_image, "keeps its image"),
    "another command": (another_command, "also changes ['command']"),
    "another entry point": (another_entry_point, "also changes ['entryPoint']"),
    "another task role": (another_task_role, "changes its ['task_role_arn']"),
    "the run schedule enabled": (
        the_run_schedule_enabled,
        "DISABLED -> ENABLED, expected DISABLED throughout",
    ),
    "the schedule starting two tasks": (
        the_schedule_starting_two_tasks,
        "changes its target beyond the task",
    ),
    "the schedule moved in time": (the_schedule_moved_in_time, "changes ['schedule_expression', 'target']"),
    "the late alarm switched on": (the_alarm_switched_on, "unexpected ['module.caselist_run.aws_cloudwatch"),
    "an account assignment destroyed": (
        an_account_assignment_destroyed,
        "an account assignment or permission",
    ),
    "a change outside the module": (a_change_outside_the_module, "changes outside module.caselist_run"),
    "a task definition changed in place": (a_task_definition_changed_in_place, "replacements are"),
    "a scheduler policy renamed": (
        a_policy_changing_its_name,
        "changes ['name', 'policy'], expected only policy",
    ),
}


@pytest.mark.parametrize("case", sorted(STOPPED))
def test_any_other_image_plan_is_plan_stop_naming_why(tmp_path: Path, case: str) -> None:
    plan = copy.deepcopy(image_plan())
    change, reason = STOPPED[case]
    change(plan)

    said = run_check("IMAGEPLAN", plan, OWNER, tmp_path)

    assert said.startswith("PLAN STOP: "), said
    assert reason in said, said


def test_an_owner_file_that_enables_the_schedule_or_names_no_digest_is_plan_stop(tmp_path: Path) -> None:
    enabled = run_check("IMAGEPLAN", image_plan(), OWNER + "caselist_run_schedule_enabled = true\n", tmp_path)
    no_digest = run_check("IMAGEPLAN", image_plan(), 'owner = "coach"\n', tmp_path)

    assert enabled.startswith("PLAN STOP: ") and "step 8's apply" in enabled
    assert no_digest.startswith("PLAN STOP: ") and "names no image digest" in no_digest


# ------------------------------------------------------------------------------------------------
# SCHEDULEPLAN: step 8, the run's schedule on, and the fallback week's off and on
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("switch", "before", "after"), [("true", "DISABLED", "ENABLED"), ("false", "ENABLED", "DISABLED")]
)
def test_the_run_schedule_turned_as_the_owner_file_says_is_plan_ok(
    tmp_path: Path, switch: str, before: str, after: str
) -> None:
    owner = OWNER + f"caselist_run_schedule_enabled = {switch}\n"

    said = run_check("SCHEDULEPLAN", schedule_plan(before, after), owner, tmp_path)

    assert said == (
        f"PLAN OK: 0 to add, 1 to change, 0 to destroy; the run's schedule {before} -> {after}, nothing else"
    )


def turned_the_other_way(plan: Plan) -> None:
    change = change_of(plan, f"{M}aws_scheduler_schedule.run[0]")
    change["before"]["state"], change["after"]["state"] = "ENABLED", "DISABLED"


def moved_in_time(plan: Plan) -> None:
    change_of(plan, f"{M}aws_scheduler_schedule.run[0]")["after"]["schedule_expression"] = (
        "cron(0 5 ? * WED *)"
    )


def an_unknown_target(plan: Plan) -> None:
    change_of(plan, f"{M}aws_scheduler_schedule.run[0]")["after_unknown"] = {
        "target": [{"ecs_parameters": [{"task_definition_arn": True}]}]
    }


def the_login_schedule_too(plan: Plan) -> None:
    side = schedule_side("login", "ENABLED", arn=True)
    plan["resource_changes"].append(
        {
            "address": f"{M}aws_scheduler_schedule.login[0]",
            "change": {
                "actions": ["update"],
                "before": side,
                "after": side | {"state": "DISABLED"},
                "after_unknown": {},
            },
        }
    )


def the_alarm_too(plan: Plan) -> None:
    the_alarm_switched_on(plan)


def a_permission_set_replaced(plan: Plan) -> None:
    plan["resource_changes"].append(
        {
            "address": "aws_ssoadmin_permission_set.caselist_run_deployer",
            "change": {"actions": ["delete", "create"], "before": {}, "after": {}, "after_unknown": {}},
        }
    )


def the_schedule_replaced(plan: Plan) -> None:
    change_of(plan, f"{M}aws_scheduler_schedule.run[0]")["actions"] = ["delete", "create"]


SCHEDULE_STOPPED: Final[dict[str, tuple[Callable[[Plan], None], str]]] = {
    "turned the other way": (turned_the_other_way, "goes ENABLED -> DISABLED, expected DISABLED -> ENABLED"),
    "moved in time": (moved_in_time, "changes ['schedule_expression', 'state']"),
    "an unknown target": (an_unknown_target, "with unknown ['target']"),
    "the login's schedule too": (
        the_login_schedule_too,
        "expected only module.caselist_run.aws_scheduler_schedule",
    ),
    "the late alarm too": (the_alarm_too, "expected only module.caselist_run.aws_scheduler_schedule.run[0]"),
    "a permission set replaced": (
        a_permission_set_replaced,
        "an account assignment or permission set changes",
    ),
    "the schedule replaced": (the_schedule_replaced, "updated in place"),
}


@pytest.mark.parametrize("case", sorted(SCHEDULE_STOPPED))
def test_any_other_schedule_plan_is_plan_stop_naming_why(tmp_path: Path, case: str) -> None:
    plan = copy.deepcopy(schedule_plan("DISABLED", "ENABLED"))
    change, reason = SCHEDULE_STOPPED[case]
    change(plan)

    said = run_check("SCHEDULEPLAN", plan, OWNER + "caselist_run_schedule_enabled = true\n", tmp_path)

    assert said.startswith("PLAN STOP: "), said
    assert reason in said, said


def test_an_owner_file_without_the_switch_is_plan_stop(tmp_path: Path) -> None:
    said = run_check("SCHEDULEPLAN", schedule_plan("DISABLED", "ENABLED"), OWNER, tmp_path)

    assert said.startswith("PLAN STOP: ") and "does not set caselist_run_schedule_enabled" in said


def test_each_check_is_in_a_block_that_reads_the_plan_it_saved() -> None:
    """The check is only as good as the plan it is given: the block saves, shows and checks one file."""
    text = RUNBOOK.read_text(encoding="utf-8")
    for marker, saved in (("IMAGEPLAN", "caselist-cutover-image"), ("SCHEDULEPLAN", "caselist-run-schedule")):
        block = text[text.rindex("```bash", 0, text.index(f"<<'{marker}'")) : text.index(f"\n{marker}\n")]
        assert f"show -json {saved}.tfplan > /tmp/{saved}-plan.json" in block, marker
        assert f"python3 -I - /tmp/{saved}-plan.json infrastructure/envs/dev/owner.auto.tfvars" in block, (
            marker
        )
