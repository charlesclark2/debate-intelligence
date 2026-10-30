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


def run_check(plan: Plan | str, tmp_path: Path, owner: str = OWNER) -> tuple[int, str]:
    plan_file, owner_file = tmp_path / "plan.json", tmp_path / "owner.auto.tfvars"
    plan_file.write_text(plan if isinstance(plan, str) else json.dumps(plan), encoding="utf-8")
    owner_file.write_text(owner, encoding="utf-8")
    ran = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), str(plan_file), str(owner_file)],
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
