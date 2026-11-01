"""Tests for `ops/caselist_run/check_image_plan.py`, a new run image's plan after the cutover (`v1-e40-t15`).

Since the cutover the run's schedule stays `ENABLED`, so the cutover runbook's image-plan check, which
expects it `DISABLED`, stops on every image apply. Until this task the PM read the plan by eye, from
`grep` counts over the plan's text, and one of them read 40 on a clean plan, because `terraform plan`
prints a "Refreshing state..." line for each Identity Center resource in state. This check reads
`terraform show -json` instead, as the operator runs it (`python3 -I`, the plan's JSON and
`owner.auto.tfvars` as its arguments).

Every plan here is written by hand in the shape `terraform show -json` gives: a replaced task
definition, a schedule repointed at its new revision (whose ARN is unknown until the apply), a role
policy whose document is unknown. No account, no real ARN, nothing from a real plan.

What is worth asserting, and why:

* `PLAN OK` for exactly the expected shape: the two task definitions replaced with the owner file's
  image, the two schedules and their roles' policies repointed, both schedules `ENABLED` throughout;
* the refreshed, unchanged Identity Center resources of every real plan (no-op, read) still `PLAN OK`;
* `PLAN STOP` naming the address and its actions for anything else: an Identity Center change
  anywhere, a change outside the module, a schedule's state, a task definition updated rather than
  replaced, an expected change missing, and an extra change in the module like 2026-10-29's
  event-target update;
* the runbook's block saves the plan, shows it as JSON and runs this check on that file.

`--memory` checks the run task's memory change instead (`v1-e40-t30`): the run task definition replaced
with 32768 MiB and nothing else in it changed, its image still the owner file's; the run schedule and
its role's policy repointed at the new revision, the schedule `ENABLED` throughout; the login's task
definition, schedule and policy untouched. Its cases are the last section: the PM's five refusals (an
image change, a login change, an Identity Center change, a size other than 32768 or a vCPU change, a
schedule left on the old revision) and the neighbours of each, and each mode refusing the other's plan.
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

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "ops" / "caselist_run" / "check_image_plan.py"
RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "caselist-cloud-run.md"

M: Final = "module.caselist_run."
ACCOUNT: Final = "111122223333"
OLD_DIGEST: Final = "sha256:" + "1" * 64
NEW_DIGEST: Final = "sha256:" + "2" * 64
REPOSITORY: Final = f"{ACCOUNT}.dkr.ecr.us-east-1.amazonaws.com/debate-dev-caselist-run"
OWNER: Final = (
    f'owner = "coach"\ncaselist_image_digest = "{NEW_DIGEST}"\ncaselist_run_schedule_enabled = true\n'
)
TASK_STOPPED_RUN: Final = M + 'aws_cloudwatch_event_target.task_stopped["run"]'

Plan = dict[str, Any]


def run_check(
    plan: Plan | str, tmp_path: Path, owner: str = OWNER, *, memory: bool = False
) -> tuple[int, str]:
    plan_file, owner_file = tmp_path / "plan.json", tmp_path / "owner.auto.tfvars"
    plan_file.write_text(plan if isinstance(plan, str) else json.dumps(plan), encoding="utf-8")
    owner_file.write_text(owner, encoding="utf-8")
    ran = subprocess.run(
        [
            sys.executable,
            "-I",
            str(SCRIPT),
            str(plan_file),
            str(owner_file),
            *(["--memory"] if memory else []),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert ran.stderr == "", ran.stderr
    [line] = ran.stdout.splitlines()
    return ran.returncode, line


# ------------------------------------------------------------------------------------------------
# Synthetic plans
# ------------------------------------------------------------------------------------------------


def entry(
    address: str, actions: list[str], before: object, after: object, **unknown: object
) -> dict[str, Any]:
    """One `resource_changes` entry, with the fields `terraform show -json` gives one."""
    parts = re.fullmatch(r"((?:module\.[a-z0-9_]+\.)*)(data\.)?([a-z0-9_]+)\.([a-z0-9_]+)(\[.*\])?", address)
    assert parts is not None, address
    module, data, kind, name, _ = parts.groups()
    found: dict[str, Any] = {
        "address": address,
        "mode": "data" if data else "managed",
        "type": kind,
        "name": name,
        "provider_name": "registry.terraform.io/hashicorp/aws",
        "change": {
            "actions": actions,
            "before": before,
            "after": after,
            "after_unknown": unknown,
            "before_sensitive": {},
            "after_sensitive": {},
        },
    }
    if module:
        found["module_address"] = module.rstrip(".")
    return found


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


def task_side(which: str, digest: str) -> dict[str, object]:
    return {
        "family": f"debate-dev-caselist-{which}",
        "container_definitions": container_definitions(which, digest),
        "task_role_arn": f"arn:aws:iam::{ACCOUNT}:role/debate-dev-caselist-{which}",
        "execution_role_arn": f"arn:aws:iam::{ACCOUNT}:role/debate-dev-caselist-{which}-execution",
        "cpu": "8192" if which == "run" else "256",
        "memory": "16384" if which == "run" else "512",
        "network_mode": "awsvpc",
        "requires_compatibilities": ["FARGATE"],
    }


def replaced_task_definition(which: str) -> dict[str, Any]:
    return entry(
        f"{M}aws_ecs_task_definition.{which}[0]",
        ["delete", "create"],
        task_side(which, OLD_DIGEST) | {"arn": "arn:old", "revision": 7},
        task_side(which, NEW_DIGEST),
        arn=True,
        revision=True,
        id=True,
    )


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


def repointed_schedule(which: str) -> dict[str, Any]:
    return entry(
        f"{M}aws_scheduler_schedule.{which}[0]",
        ["update"],
        schedule_side(which, "ENABLED", arn=True),
        schedule_side(which, "ENABLED", arn=False),
        target=[{"ecs_parameters": [{"task_definition_arn": True}]}],
    )


def repointed_policy(name: str) -> dict[str, Any]:
    return entry(
        f"{M}aws_iam_role_policy.{name}[0]",
        ["update"],
        {"name": "start-task", "role": f"debate-dev-caselist-{name}", "policy": '{"Statement":[]}'},
        {"name": "start-task", "role": f"debate-dev-caselist-{name}"},
        policy=True,
    )


def unchanged(address: str) -> dict[str, Any]:
    return entry(address, ["no-op"], {"id": "x"}, {"id": "x"})


def image_plan() -> Plan:
    """A new image's plan as it should be after the cutover: 2 to add, 4 to change, 2 to destroy."""
    return {
        "format_version": "1.2",
        "terraform_version": "1.16.0",
        "resource_changes": [
            replaced_task_definition("login"),
            replaced_task_definition("run"),
            repointed_schedule("login"),
            repointed_schedule("run"),
            repointed_policy("scheduler"),
            repointed_policy("run_scheduler"),
            unchanged(f"{M}aws_cloudwatch_metric_alarm.late_run"),
            unchanged(TASK_STOPPED_RUN),
            unchanged("module.evidence_bucket.aws_s3_bucket.this"),
            entry("data.aws_caller_identity.current", ["read"], None, {}),
        ],
    }


def change_of(plan: Plan, address: str) -> dict[str, Any]:
    return next(found["change"] for found in plan["resource_changes"] if found["address"] == address)


def without(plan: Plan, address: str) -> None:
    plan["resource_changes"] = [found for found in plan["resource_changes"] if found["address"] != address]


def changed_instead(plan: Plan, replacement: dict[str, Any]) -> None:
    """`replacement` in place of the no-op entry at its address, or added where there is none."""
    without(plan, replacement["address"])
    plan["resource_changes"].append(replacement)


# ------------------------------------------------------------------------------------------------
# PLAN OK
# ------------------------------------------------------------------------------------------------


def test_the_expected_shape_is_plan_ok(tmp_path: Path) -> None:
    code, said = run_check(image_plan(), tmp_path)

    assert said == (
        "PLAN OK: 2 to add, 4 to change, 2 to destroy; the login and run task definitions replaced "
        "with the image sha256:222222222222... and nothing else in them changed; the two schedules and "
        "their roles' policies repointed at the new revisions; both schedules ENABLED throughout; "
        "nothing else changes"
    ), said
    assert code == 0


def test_a_task_definition_created_before_its_old_revision_is_destroyed_is_still_a_replace(
    tmp_path: Path,
) -> None:
    plan = image_plan()
    change_of(plan, f"{M}aws_ecs_task_definition.run[0]")["actions"] = ["create", "delete"]

    code, said = run_check(plan, tmp_path)

    assert said.startswith("PLAN OK: 2 to add, 4 to change, 2 to destroy"), said
    assert code == 0


def test_refreshed_identity_center_resources_that_do_not_change_are_plan_ok(tmp_path: Path) -> None:
    """2026-10-29's false 40: a refresh line per resource in state is not a change."""
    plan = image_plan()
    for n in range(10):
        plan["resource_changes"] += [
            unchanged(f'aws_ssoadmin_account_assignment.evidence_operator["person{n}"]'),
            unchanged(f'aws_ssoadmin_permission_set.caselist{n}["dev"]'),
            unchanged(f'aws_identitystore_user.people["person{n}"]'),
            unchanged(f'module.organization.aws_identitystore_group_membership.members["person{n}"]'),
        ]
    plan["resource_changes"] += [
        entry("data.aws_ssoadmin_instances.this", ["read"], None, {}),
        entry('module.organization.data.aws_identitystore_group.operators["dev"]', ["read"], None, {}),
    ]

    code, said = run_check(plan, tmp_path)

    assert said.startswith("PLAN OK: 2 to add, 4 to change, 2 to destroy"), said
    assert code == 0


# ------------------------------------------------------------------------------------------------
# PLAN STOP
# ------------------------------------------------------------------------------------------------


def test_the_plan_of_2026_10_29_is_plan_stop_naming_the_event_target(tmp_path: Path) -> None:
    """The expected six and an in-place update to the run's task-stopped message: read by a person."""
    plan = image_plan()
    changed_instead(
        plan,
        entry(
            TASK_STOPPED_RUN,
            ["update"],
            {"rule": "debate-dev-caselist-run-stopped", "input_transformer": [{"input_template": '"old"'}]},
            {"rule": "debate-dev-caselist-run-stopped", "input_transformer": [{"input_template": '"new"'}]},
        ),
    )

    code, said = run_check(plan, tmp_path)

    assert said == (
        "PLAN STOP: an unexpected change in module.caselist_run: " + TASK_STOPPED_RUN + " (update)"
    ), said
    assert code == 1


def identity_center_change(address: str, actions: list[str]) -> Callable[[Plan], None]:
    return lambda plan: changed_instead(plan, entry(address, actions, {"id": "x"}, {"id": "y"}))


def outside_the_module(plan: Plan) -> None:
    changed_instead(
        plan,
        entry(
            "module.evidence_bucket.aws_s3_bucket_policy.this", ["update"], {"policy": "a"}, {"policy": "b"}
        ),
    )


def a_root_resource_created(plan: Plan) -> None:
    changed_instead(plan, entry("aws_sns_topic.extra", ["create"], None, {"name": "extra"}))


def run_schedule_turned_off(plan: Plan) -> None:
    change_of(plan, f"{M}aws_scheduler_schedule.run[0]")["after"]["state"] = "DISABLED"


def login_schedule_turned_on(plan: Plan) -> None:
    change_of(plan, f"{M}aws_scheduler_schedule.login[0]")["before"]["state"] = "DISABLED"


def run_schedule_disabled_throughout(plan: Plan) -> None:
    change = change_of(plan, f"{M}aws_scheduler_schedule.run[0]")
    change["before"]["state"] = change["after"]["state"] = "DISABLED"


def schedule_state_unknown(plan: Plan) -> None:
    change = change_of(plan, f"{M}aws_scheduler_schedule.login[0]")
    del change["after"]["state"]
    change["after_unknown"]["state"] = True


def task_definition_updated_in_place(plan: Plan) -> None:
    change_of(plan, f"{M}aws_ecs_task_definition.login[0]")["actions"] = ["update"]


def task_definition_only_created(plan: Plan) -> None:
    change_of(plan, f"{M}aws_ecs_task_definition.run[0]")["actions"] = ["create"]


def a_missing(address: str) -> Callable[[Plan], None]:
    return lambda plan: without(plan, address)


def schedule_replaced(plan: Plan) -> None:
    change_of(plan, f"{M}aws_scheduler_schedule.run[0]")["actions"] = ["delete", "create"]


def an_old_revision_left_deposed(plan: Plan) -> None:
    deposed = entry(f"{M}aws_ecs_task_definition.run[0]", ["delete"], {"revision": 6}, None)
    plan["resource_changes"].append(deposed | {"deposed": "00000001"})


def the_alarm_switched_on(plan: Plan) -> None:
    changed_instead(
        plan,
        entry(
            f"{M}aws_cloudwatch_metric_alarm.late_run",
            ["update"],
            {"actions_enabled": False},
            {"actions_enabled": True},
        ),
    )


def an_in_module_resource_destroyed(plan: Plan) -> None:
    changed_instead(plan, entry(f"{M}aws_iam_role_policy.run_alerts", ["delete"], {"name": "alerts"}, None))


def a_resource_forgotten(plan: Plan) -> None:
    changed_instead(plan, entry(f"{M}aws_cloudwatch_metric_alarm.late_run", ["forget"], {"id": "x"}, None))


def run_definition_after(plan: Plan, **changed: object) -> None:
    after = change_of(plan, f"{M}aws_ecs_task_definition.run[0]")["after"]
    after["container_definitions"] = container_definitions("run", NEW_DIGEST, **changed)


def another_image(plan: Plan) -> None:
    run_definition_after(plan, image=f"{REPOSITORY}@sha256:{'3' * 64}")


def the_same_image(plan: Plan) -> None:
    for which in ("login", "run"):
        change = change_of(plan, f"{M}aws_ecs_task_definition.{which}[0]")
        change["after"]["container_definitions"] = container_definitions(which, OLD_DIGEST)


def an_environment_variable_added(plan: Plan) -> None:
    run_definition_after(
        plan,
        environment=[{"name": n, "value": v} for n, v in (ENVIRONMENT["run"] | {"DEBATE_X": "1"}).items()],
    )


def another_command(plan: Plan) -> None:
    run_definition_after(plan, command=["--json", "caselist", "pull", "--caselist", "testcl26"])


def another_task_role(plan: Plan) -> None:
    after = change_of(plan, f"{M}aws_ecs_task_definition.run[0]")["after"]
    after["task_role_arn"] = "arn:aws:iam::x:role/other"


def unreadable_container_definitions(plan: Plan) -> None:
    change_of(plan, f"{M}aws_ecs_task_definition.login[0]")["after"]["container_definitions"] = "not json"


def the_schedule_moved_in_time(plan: Plan) -> None:
    after = change_of(plan, f"{M}aws_scheduler_schedule.run[0]")["after"]
    after["schedule_expression"] = "cron(0 6 ? * TUE *)"


def the_schedule_starting_two_tasks(plan: Plan) -> None:
    after = change_of(plan, f"{M}aws_scheduler_schedule.run[0]")["after"]
    after["target"][0]["ecs_parameters"][0]["task_count"] = 2


def a_policy_renamed(plan: Plan) -> None:
    change_of(plan, f"{M}aws_iam_role_policy.run_scheduler[0]")["after"]["name"] = "everything"


STOPPED: Final[dict[str, tuple[Callable[[Plan], None], str]]] = {
    "a permission set replaced": (
        identity_center_change("aws_ssoadmin_permission_set.caselist_run_deployer", ["delete", "create"]),
        "an Identity Center change, which never passes: "
        "aws_ssoadmin_permission_set.caselist_run_deployer (delete/create); never apply this plan",
    ),
    "an account assignment destroyed": (
        identity_center_change('aws_ssoadmin_account_assignment.evidence_operator["coach"]', ["delete"]),
        'never passes: aws_ssoadmin_account_assignment.evidence_operator["coach"] (delete);',
    ),
    "an identity store user created in another module": (
        identity_center_change('module.organization.aws_identitystore_user.people["coach"]', ["create"]),
        "an Identity Center change, which never passes: "
        'module.organization.aws_identitystore_user.people["coach"] (create); never apply this plan',
    ),
    "a change outside the module": (
        outside_the_module,
        "a change outside module.caselist_run: module.evidence_bucket.aws_s3_bucket_policy.this (update)",
    ),
    "a root resource created": (
        a_root_resource_created,
        "a change outside module.caselist_run: aws_sns_topic.extra (create)",
    ),
    "the run schedule turned off": (
        run_schedule_turned_off,
        M + "aws_scheduler_schedule.run[0] is ENABLED -> DISABLED, expected ENABLED throughout",
    ),
    "the login schedule turned on": (
        login_schedule_turned_on,
        M + "aws_scheduler_schedule.login[0] is DISABLED -> ENABLED, expected ENABLED throughout",
    ),
    "the run schedule disabled throughout": (
        run_schedule_disabled_throughout,
        M + "aws_scheduler_schedule.run[0] is DISABLED -> DISABLED, expected ENABLED throughout",
    ),
    "a schedule's state unknown": (
        schedule_state_unknown,
        M + "aws_scheduler_schedule.login[0] is ENABLED -> (unknown), expected ENABLED throughout",
    ),
    "a task definition updated in place": (
        task_definition_updated_in_place,
        M + "aws_ecs_task_definition.login[0]: update, expected a replace (delete and create)",
    ),
    "a task definition only created": (
        task_definition_only_created,
        M + "aws_ecs_task_definition.run[0]: create, expected a replace (delete and create)",
    ),
    "the run task definition missing": (
        a_missing(f"{M}aws_ecs_task_definition.run[0]"),
        M + "aws_ecs_task_definition.run[0]: no change, expected a replace (delete and create)",
    ),
    "the login schedule missing": (
        a_missing(f"{M}aws_scheduler_schedule.login[0]"),
        M + "aws_scheduler_schedule.login[0]: no change, expected an update",
    ),
    "a scheduler policy missing": (
        a_missing(f"{M}aws_iam_role_policy.scheduler[0]"),
        M + "aws_iam_role_policy.scheduler[0]: no change, expected an update",
    ),
    "a schedule replaced": (
        schedule_replaced,
        M + "aws_scheduler_schedule.run[0]: delete/create, expected an update",
    ),
    "an old revision left deposed": (
        an_old_revision_left_deposed,
        "an unexpected change in module.caselist_run: "
        + M
        + "aws_ecs_task_definition.run[0] deposed 00000001 (delete)",
    ),
    "the late alarm switched on": (
        the_alarm_switched_on,
        "an unexpected change in module.caselist_run: " + M + "aws_cloudwatch_metric_alarm.late_run (update)",
    ),
    "a resource in the module destroyed": (
        an_in_module_resource_destroyed,
        "an unexpected change in module.caselist_run: " + M + "aws_iam_role_policy.run_alerts (delete)",
    ),
    "a resource forgotten": (
        a_resource_forgotten,
        "an unexpected change in module.caselist_run: " + M + "aws_cloudwatch_metric_alarm.late_run (forget)",
    ),
    "an image other than the owner file's digest": (
        another_image,
        M + "aws_ecs_task_definition.run[0]'s image is " + REPOSITORY + "@sha256:333",
    ),
    "the same image": (the_same_image, "aws_ecs_task_definition.login[0] keeps its image"),
    "an environment variable added": (
        an_environment_variable_added,
        M + "aws_ecs_task_definition.run[0] changes its environment: adds ['DEBATE_X']",
    ),
    "another command": (another_command, M + "aws_ecs_task_definition.run[0] also changes ['command']"),
    "another task role": (
        another_task_role,
        M + "aws_ecs_task_definition.run[0] changes its ['task_role_arn']",
    ),
    "unreadable container definitions": (
        unreadable_container_definitions,
        M + "aws_ecs_task_definition.login[0]: its container definitions cannot be read from the plan",
    ),
    "the schedule moved in time": (
        the_schedule_moved_in_time,
        M + "aws_scheduler_schedule.run[0] changes ['schedule_expression', 'target'], expected only target",
    ),
    "the schedule starting two tasks": (
        the_schedule_starting_two_tasks,
        M + "aws_scheduler_schedule.run[0] changes its target beyond the task definition it starts",
    ),
    "a scheduler policy renamed": (
        a_policy_renamed,
        M + "aws_iam_role_policy.run_scheduler[0] changes ['name', 'policy'], expected only policy",
    ),
}


@pytest.mark.parametrize("case", sorted(STOPPED))
def test_any_other_plan_is_plan_stop_naming_the_address(tmp_path: Path, case: str) -> None:
    plan = copy.deepcopy(image_plan())
    change, reason = STOPPED[case]
    change(plan)

    code, said = run_check(plan, tmp_path)

    assert said.startswith("PLAN STOP: "), said
    assert reason in said, said
    assert code == 1


def test_an_identity_center_change_anywhere_says_never_to_apply(tmp_path: Path) -> None:
    plan = image_plan()
    identity_center_change(f"{M}aws_ssoadmin_account_assignment.run", ["create"])(plan)

    code, said = run_check(plan, tmp_path)

    assert said.startswith(
        "PLAN STOP: an Identity Center change, which never passes: "
        "module.caselist_run.aws_ssoadmin_account_assignment.run (create); never apply this plan"
    ), said
    assert code == 1


def test_every_problem_is_named_in_one_line(tmp_path: Path) -> None:
    plan = image_plan()
    outside_the_module(plan)
    run_schedule_turned_off(plan)
    changed_instead(plan, entry(TASK_STOPPED_RUN, ["update"], {"a": 1}, {"a": 2}))

    code, said = run_check(plan, tmp_path)

    assert "module.evidence_bucket.aws_s3_bucket_policy.this (update)" in said
    assert "aws_scheduler_schedule.run[0] is ENABLED -> DISABLED" in said
    assert TASK_STOPPED_RUN + " (update)" in said
    assert code == 1


def test_an_owner_file_without_a_digest_is_plan_stop(tmp_path: Path) -> None:
    code, said = run_check(image_plan(), tmp_path, owner='owner = "coach"\n')

    assert said.startswith("PLAN STOP: owner.auto.tfvars names no image digest"), said
    assert code == 1


@pytest.mark.parametrize(
    ("plan", "reason"),
    [
        ("Refreshing state... [id=x]\nPlan: 2 to add, 4 to change, 2 to destroy.\n", "is not JSON"),
        ("[]", "has no resource_changes"),
        ('{"format_version": "1.2", "resource_changes": [{"address": "x"}]}', "has no resource_changes"),
        (
            json.dumps(
                {
                    "resource_changes": [
                        {"address": "aws_ssoadmin_permission_set.x", "change": {"actions": ["create"]}}
                    ]
                }
            ),
            "has no resource_changes",
        ),
    ],
    ids=["the plan's text", "a list", "an entry without a change", "an entry without its type"],
)
def test_a_file_that_is_not_a_plans_json_is_plan_stop(tmp_path: Path, plan: str, reason: str) -> None:
    code, said = run_check(plan, tmp_path)

    assert said.startswith("PLAN STOP: ") and reason in said, said
    assert code == 2


# ------------------------------------------------------------------------------------------------
# The runbook's block
# ------------------------------------------------------------------------------------------------


def new_image_section() -> str:
    text = RUNBOOK.read_text(encoding="utf-8")
    start = text.index("\n## A new image, later\n")
    return text[start : text.index("\n## ", start + 1)]


def bash_blocks(section: str) -> list[str]:
    return re.findall(r"```bash\n(.*?)```", section, flags=re.DOTALL)


def test_the_runbook_checks_the_json_of_the_plan_it_saved_and_counts_nothing_in_its_text() -> None:
    [plan_block] = [block for block in bash_blocks(new_image_section()) if " plan " in block]

    assert "rm -f infrastructure/envs/dev/caselist-new-image.tfplan /tmp/caselist-new-image-plan.json" in (
        plan_block
    )
    assert "plan -input=false -no-color -out=caselist-new-image.tfplan" in plan_block
    assert "show -json caselist-new-image.tfplan > /tmp/caselist-new-image-plan.json" in plan_block
    assert (
        "python3 -I ops/caselist_run/check_image_plan.py /tmp/caselist-new-image-plan.json "
        "infrastructure/envs/dev/owner.auto.tfvars"
    ) in plan_block
    assert "grep" not in plan_block.replace("grep -qE '^(TF_VAR_|", "")


def test_the_runbook_applies_the_checked_plan_after_the_pms_word_and_never_on_a_wednesday() -> None:
    section = new_image_section()
    [apply_block] = [block for block in bash_blocks(section) if " apply " in block]

    assert "apply -input=false caselist-new-image.tfplan" in apply_block
    assert 'if [ "$(date +%A)" = "Wednesday" ]; then echo "STOP' in apply_block
    assert "`PLAN STOP` goes to the PM" in section
    assert "after the PM's word" in section


# ------------------------------------------------------------------------------------------------
# --memory: the run task's memory change (v1-e40-t30)
# ------------------------------------------------------------------------------------------------

RUN_DEFINITION: Final = M + "aws_ecs_task_definition.run[0]"
RUN_SCHEDULE: Final = M + "aws_scheduler_schedule.run[0]"
RUN_POLICY: Final = M + "aws_iam_role_policy.run_scheduler[0]"
LOGIN_DEFINITION: Final = M + "aws_ecs_task_definition.login[0]"
LOGIN_SCHEDULE: Final = M + "aws_scheduler_schedule.login[0]"
LOGIN_POLICY: Final = M + "aws_iam_role_policy.scheduler[0]"


def memory_plan() -> Plan:
    """The run task's memory to 32 GB: 1 to add, 2 to change, 1 to destroy. The image stays the owner
    file's digest, which is NEW_DIGEST here; the login and everything else are refreshed, unchanged."""
    return {
        "format_version": "1.2",
        "terraform_version": "1.16.0",
        "resource_changes": [
            entry(
                RUN_DEFINITION,
                ["delete", "create"],
                task_side("run", NEW_DIGEST) | {"arn": "arn:old", "revision": 10},
                task_side("run", NEW_DIGEST) | {"memory": "32768"},
                arn=True,
                revision=True,
                id=True,
            ),
            repointed_schedule("run"),
            repointed_policy("run_scheduler"),
            unchanged(LOGIN_DEFINITION),
            unchanged(LOGIN_SCHEDULE),
            unchanged(LOGIN_POLICY),
            unchanged(f"{M}aws_cloudwatch_metric_alarm.late_run"),
            unchanged(TASK_STOPPED_RUN),
            unchanged("module.evidence_bucket.aws_s3_bucket.this"),
            unchanged('aws_ssoadmin_account_assignment.evidence_operator["coach"]'),
            unchanged("aws_ssoadmin_permission_set.caselist_run_deployer"),
            entry("data.aws_caller_identity.current", ["read"], None, {}),
        ],
    }


def test_the_memory_change_is_plan_ok(tmp_path: Path) -> None:
    code, said = run_check(memory_plan(), tmp_path, memory=True)

    assert said == (
        "PLAN OK: 1 to add, 2 to change, 1 to destroy; the run task definition replaced with its memory "
        "16384 -> 32768 and nothing else in it changed, 8192 CPU units and the image "
        "sha256:222222222222... as before; the run schedule and its role's policy repointed at the new "
        "revision; the run schedule ENABLED throughout; the login task definition, its schedule and its "
        "policy unchanged; nothing else changes"
    ), said
    assert code == 0


def test_the_memory_change_created_before_its_old_revision_is_destroyed_is_still_plan_ok(
    tmp_path: Path,
) -> None:
    plan = memory_plan()
    change_of(plan, RUN_DEFINITION)["actions"] = ["create", "delete"]

    code, said = run_check(plan, tmp_path, memory=True)

    assert said.startswith("PLAN OK: 1 to add, 2 to change, 1 to destroy"), said
    assert code == 0


def test_the_image_check_refuses_the_memory_change(tmp_path: Path) -> None:
    """Without --memory the plan is not an image change: the login is unchanged, the image kept."""
    code, said = run_check(memory_plan(), tmp_path)

    assert said.startswith("PLAN STOP: "), said
    assert LOGIN_DEFINITION + ": no change, expected a replace (delete and create)" in said, said
    assert RUN_DEFINITION + " keeps its image, so there is no image change to apply" in said, said
    assert code == 1


def test_the_memory_check_refuses_an_image_plan(tmp_path: Path) -> None:
    """The image apply's plan, even with the new memory in it, is not the memory change."""
    plan = image_plan()
    change_of(plan, RUN_DEFINITION)["after"]["memory"] = "32768"

    code, said = run_check(plan, tmp_path, memory=True)

    assert said.startswith("PLAN STOP: "), said
    assert RUN_DEFINITION + " also changes ['image']" in said, said
    assert "a login change, which the memory change never makes: " in said, said
    for address in (LOGIN_DEFINITION, LOGIN_SCHEDULE, LOGIN_POLICY):
        assert address in said, said
    assert code == 1


def run_after(plan: Plan, **changed: object) -> None:
    change_of(plan, RUN_DEFINITION)["after"].update(changed)


def run_container_after(plan: Plan, **changed: object) -> None:
    change_of(plan, RUN_DEFINITION)["after"]["container_definitions"] = container_definitions(
        "run", NEW_DIGEST, **changed
    )


def run_schedule_starting(revision: str) -> Callable[[Plan], None]:
    """The run schedule's target set to a revision already known when the plan is made."""

    def change(plan: Plan) -> None:
        schedule = change_of(plan, RUN_SCHEDULE)
        schedule["after"]["target"][0]["ecs_parameters"][0]["task_definition_arn"] = (
            f"arn:aws:ecs:us-east-1:{ACCOUNT}:task-definition/debate-dev-caselist-run:{revision}"
        )
        schedule["after_unknown"] = {}

    return change


def the_memory_change_for(owner_digest: str) -> Callable[[Plan], None]:
    """Both sides of the run definition on another image than the owner file names."""

    def change(plan: Plan) -> None:
        definition = change_of(plan, RUN_DEFINITION)
        for side in ("before", "after"):
            definition[side]["container_definitions"] = container_definitions("run", owner_digest)

    return change


MEMORY_STOPPED: Final[dict[str, tuple[Callable[[Plan], None], str]]] = {
    # The image: it stays the owner file's digest.
    "an image change as well": (
        lambda plan: run_container_after(plan, image=f"{REPOSITORY}@sha256:{'3' * 64}"),
        RUN_DEFINITION + " also changes ['image']",
    ),
    "a run task on another image than the owner file's": (
        the_memory_change_for(OLD_DIGEST),
        RUN_DEFINITION + "'s image is " + REPOSITORY + "@" + OLD_DIGEST + ", expected the digest in "
        "owner.auto.tfvars",
    ),
    # The login: never changed by this.
    "the login task definition replaced": (
        lambda plan: changed_instead(plan, replaced_task_definition("login")),
        "a login change, which the memory change never makes: " + LOGIN_DEFINITION + " (delete/create)",
    ),
    "the login task definition updated": (
        lambda plan: changed_instead(
            plan, entry(LOGIN_DEFINITION, ["update"], {"memory": "512"}, {"memory": "1024"})
        ),
        "a login change, which the memory change never makes: " + LOGIN_DEFINITION + " (update)",
    ),
    "the login schedule repointed": (
        lambda plan: changed_instead(plan, repointed_schedule("login")),
        "a login change, which the memory change never makes: " + LOGIN_SCHEDULE + " (update)",
    ),
    "the login scheduler policy updated": (
        lambda plan: changed_instead(plan, repointed_policy("scheduler")),
        "a login change, which the memory change never makes: " + LOGIN_POLICY + " (update)",
    ),
    # Identity Center, anywhere.
    "an account assignment destroyed": (
        identity_center_change('aws_ssoadmin_account_assignment.evidence_operator["coach"]', ["delete"]),
        "an Identity Center change, which never passes: "
        'aws_ssoadmin_account_assignment.evidence_operator["coach"] (delete); never apply this plan',
    ),
    "a permission set replaced": (
        identity_center_change("aws_ssoadmin_permission_set.caselist_run_deployer", ["delete", "create"]),
        "an Identity Center change, which never passes: "
        "aws_ssoadmin_permission_set.caselist_run_deployer (delete/create); never apply this plan",
    ),
    "an identity store user created in another module": (
        identity_center_change('module.organization.aws_identitystore_user.people["coach"]', ["create"]),
        'never passes: module.organization.aws_identitystore_user.people["coach"] (create)',
    ),
    # The size.
    "the memory left at 16 GB": (
        lambda plan: run_after(plan, memory="16384"),
        RUN_DEFINITION + "'s memory is 16384 -> 16384, expected 32768",
    ),
    "a memory of 28 GB": (
        lambda plan: run_after(plan, memory="28672"),
        RUN_DEFINITION + "'s memory is 16384 -> 28672, expected 32768",
    ),
    "a memory of 60 GB": (
        lambda plan: run_after(plan, memory="61440"),
        RUN_DEFINITION + "'s memory is 16384 -> 61440, expected 32768",
    ),
    "a vCPU change": (
        lambda plan: run_after(plan, cpu="16384"),
        RUN_DEFINITION + " changes its ['cpu']",
    ),
    "the ephemeral storage changed": (
        lambda plan: run_after(plan, ephemeral_storage=[{"size_in_gib": 200}]),
        RUN_DEFINITION + " changes its ['ephemeral_storage']",
    ),
    "another task role": (
        lambda plan: run_after(plan, task_role_arn="arn:aws:iam::x:role/other"),
        RUN_DEFINITION + " changes its ['task_role_arn']",
    ),
    "the parse workers changed": (
        lambda plan: run_container_after(
            plan,
            environment=[
                {"name": n, "value": v}
                for n, v in (ENVIRONMENT["run"] | {"DEBATE_PARSE__WORKERS": "12"}).items()
            ],
        ),
        RUN_DEFINITION + " changes its environment: adds [], removes [], changes ['DEBATE_PARSE__WORKERS']",
    ),
    "another command": (
        lambda plan: run_container_after(plan, command=["--json", "caselist", "backfile-import"]),
        RUN_DEFINITION + " also changes ['command']",
    ),
    "unreadable container definitions": (
        lambda plan: run_after(plan, container_definitions="not json"),
        RUN_DEFINITION + ": its container definitions cannot be read from the plan",
    ),
    "the run task definition updated in place": (
        lambda plan: change_of(plan, RUN_DEFINITION).update(actions=["update"]),
        RUN_DEFINITION + ": update, expected a replace (delete and create)",
    ),
    "the run task definition unchanged": (
        lambda plan: changed_instead(plan, unchanged(RUN_DEFINITION)),
        RUN_DEFINITION + ": no change, expected a replace (delete and create)",
    ),
    # The schedule, on the new revision.
    "the run schedule left on the old revision": (
        lambda plan: changed_instead(plan, unchanged(RUN_SCHEDULE)),
        RUN_SCHEDULE + ": no change, expected an update",
    ),
    "the run schedule set to the old revision by name": (
        run_schedule_starting("7"),
        RUN_SCHEDULE + " changes [], expected only target",
    ),
    "the run schedule set to another revision already registered": (
        run_schedule_starting("9"),
        RUN_SCHEDULE
        + " starts debate-dev-caselist-run:9, a revision known before the apply, not the new one",
    ),
    "the run scheduler policy left as it is": (
        lambda plan: changed_instead(plan, unchanged(RUN_POLICY)),
        RUN_POLICY + ": no change, expected an update",
    ),
    "the run scheduler policy renamed": (
        lambda plan: change_of(plan, RUN_POLICY)["after"].update(name="everything"),
        RUN_POLICY + " changes ['name', 'policy'], expected only policy",
    ),
    "the run schedule turned off": (
        run_schedule_turned_off,
        RUN_SCHEDULE + " is ENABLED -> DISABLED, expected ENABLED throughout",
    ),
    "the run schedule moved in time": (
        the_schedule_moved_in_time,
        RUN_SCHEDULE + " changes ['schedule_expression', 'target'], expected only target",
    ),
    "the run schedule starting two tasks": (
        the_schedule_starting_two_tasks,
        RUN_SCHEDULE + " changes its target beyond the task definition it starts",
    ),
    # Anything else.
    "a change outside the module": (
        outside_the_module,
        "a change outside module.caselist_run: module.evidence_bucket.aws_s3_bucket_policy.this (update)",
    ),
    "an old revision left deposed": (
        an_old_revision_left_deposed,
        "an unexpected change in module.caselist_run: " + RUN_DEFINITION + " deposed 00000001 (delete)",
    ),
    "the task-stopped target updated": (
        lambda plan: changed_instead(plan, entry(TASK_STOPPED_RUN, ["update"], {"a": 1}, {"a": 2})),
        "an unexpected change in module.caselist_run: " + TASK_STOPPED_RUN + " (update)",
    ),
}


@pytest.mark.parametrize("case", sorted(MEMORY_STOPPED))
def test_any_other_plan_is_memory_plan_stop_naming_the_address(tmp_path: Path, case: str) -> None:
    plan = copy.deepcopy(memory_plan())
    change, reason = MEMORY_STOPPED[case]
    change(plan)

    code, said = run_check(plan, tmp_path, memory=True)

    assert said.startswith("PLAN STOP: "), said
    assert reason in said, said
    assert code == 1


def test_the_memory_check_needs_the_owner_files_digest(tmp_path: Path) -> None:
    code, said = run_check(memory_plan(), tmp_path, owner='owner = "coach"\n', memory=True)

    assert said.startswith("PLAN STOP: owner.auto.tfvars names no image digest"), said
    assert code == 1


def test_a_file_that_is_not_a_plans_json_is_memory_plan_stop(tmp_path: Path) -> None:
    code, said = run_check("Plan: 1 to add, 2 to change, 1 to destroy.\n", tmp_path, memory=True)

    assert said.startswith("PLAN STOP: the plan file is not JSON"), said
    assert code == 2


# The runbook's section


def memory_section() -> str:
    text = RUNBOOK.read_text(encoding="utf-8")
    start = text.index("\n## The run task's memory\n")
    return text[start : text.index("\n## ", start + 1)]


def test_the_memory_section_follows_a_new_image_later() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    image = text.index("\n## A new image, later\n")
    memory = text.index("\n## The run task's memory\n")

    assert image < memory
    assert text.index("\n## ", image + 1) == memory


def test_the_memory_section_checks_the_saved_plans_json_with_memory_and_names_its_plan_line() -> None:
    section = memory_section()
    [plan_block] = [block for block in bash_blocks(section) if " plan " in block]

    assert "rm -f infrastructure/envs/dev/caselist-run-memory.tfplan /tmp/caselist-run-memory-plan.json" in (
        plan_block
    )
    assert "plan -input=false -no-color -out=caselist-run-memory.tfplan" in plan_block
    assert "show -json caselist-run-memory.tfplan > /tmp/caselist-run-memory-plan.json" in plan_block
    assert (
        "python3 -I ops/caselist_run/check_image_plan.py /tmp/caselist-run-memory-plan.json "
        "infrastructure/envs/dev/owner.auto.tfvars --memory"
    ) in plan_block
    assert " apply " not in plan_block
    assert "`Plan: 1 to add, 2 to change, 1 to destroy.`" in section


def test_the_memory_section_applies_the_checked_plan_after_the_pms_word_and_never_on_a_wednesday() -> None:
    section = memory_section()
    [apply_block] = [block for block in bash_blocks(section) if " apply " in block]

    assert "apply -input=false caselist-run-memory.tfplan" in apply_block
    assert 'if [ "$(TZ=America/Chicago date +%A)" = "Wednesday" ]; then echo "STOP' in apply_block
    assert " plan " not in apply_block
    assert "after the PM's word" in section
    assert "2026-11-04 06:00" in section


def test_the_memory_section_reads_back_only_the_scheduled_revisions_memory_and_cpu() -> None:
    [read_back] = [block for block in bash_blocks(memory_section()) if "describe-task-definition" in block]

    assert "scheduler get-schedule" in read_back
    assert "--query 'taskDefinition.[cpu,memory]'" in read_back


def inside_double_quotes(block: str) -> list[str]:
    """The text inside each double-quoted string of a shell block (one with no heredoc or escaped quote)."""
    found, quote, current = [], None, ""
    for character in block:
        if quote is None:
            quote = character if character in "'\"" else None
        elif character == quote:
            if quote == '"':
                found.append(current)
            quote, current = None, ""
        elif quote == '"':
            current += character
    return found


def test_no_memory_section_block_puts_an_exclamation_mark_inside_double_quotes() -> None:
    """zsh expands `!` inside double quotes when a block is pasted (agreement 9's neighbour)."""
    assert inside_double_quotes('echo "a!b" \'c!d\' "e"') == ["a!b", "e"]
    for block in bash_blocks(memory_section()):
        assert not [text for text in inside_double_quotes(block) if "!" in text], block
