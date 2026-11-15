"""The plan that finishes v1-e40-t48's move after dev's failed apply of 2026-11-15 (the PM's brief).

That apply replaced both task definitions (the run's new revision is :17), repointed both scheduler
policies and the login schedule, and was refused at the run schedule: "Invalid RequestJson provided.
Reason Request payload is missing the following field(s): TaskDefinition". Scheduler validates a
universal target's Input against the SDK's PascalCase names, not the RunTask API reference's camelCase.
The run schedule stayed on the ECS template, starting revision :15, which the apply deregistered, while
the run scheduler role's policy names :17 alone.

So the fix plan, from that state, changes the run schedule alone, in place: `0 to add, 1 to change,
0 to destroy`. Its revision is already in state, so the plan knows the whole Input, and
`check_image_plan.py --run-schedule-only` reads it key by key: the SDK's names, the current run
revision (the one the scheduler policy names, running the owner file's image), the template's own
cluster, network and launch settings, and the command `--json caselist pull --scheduled`.

v1-e05-t20 may merge first (the PM's note of 2026-11-15). Then the same dev plan also updates
`module.bedrock_access`'s inline policy in place, and that alone is allowed outside the module: no add,
no destroy, no replace, no account assignment or permission set. The check names it on a line of its
own, so the PM reads both.

Every plan here is written by hand; no account, no real ARN.
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
from tests.infrastructure.test_the_schedule_passes_scheduled import (
    REVISIONS,
    SCHEDULED,
    UNIVERSAL,
    write_owner_and_plan,
)
from tests.scripts.test_caselist_run_image_plan_check import (
    LOGIN_DEFINITION,
    LOGIN_POLICY,
    LOGIN_SCHEDULE,
    NEW_DIGEST,
    OLD_DIGEST,
    RUN_DEFINITION,
    RUN_POLICY,
    RUN_SCHEDULE,
    SCRIPT,
    TASK_STOPPED_RUN,
    M,
    Plan,
    change_of,
    changed_instead,
    container_definitions,
    entry,
    task_side,
    unchanged,
)

FLAG: Final = "--run-schedule-only"
BEDROCK_POLICY: Final = "module.bedrock_access.aws_ssoadmin_permission_set_inline_policy.invoker[0]"
BEDROCK_SET: Final = "module.bedrock_access.aws_ssoadmin_permission_set.invoker[0]"
BEDROCK_ASSIGNMENT: Final = 'module.bedrock_access.aws_ssoadmin_account_assignment.invokers["coach"]'
CLUSTER: Final = "arn:aws:ecs:us-east-1:111122223333:cluster/debate-dev-caselist-run"
DIFFERS: Final = f"{RUN_SCHEDULE}'s Input differs from the template's settings and the scheduled command at "


def run_check(plan: Plan, tmp_path: Path, *flags: str) -> tuple[int, list[str]]:
    plan_file, owner_file = write_owner_and_plan(plan, tmp_path)
    ran = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), str(plan_file), str(owner_file), *flags],
        capture_output=True,
        text=True,
        check=False,
    )
    assert ran.stderr == "", ran.stderr
    return ran.returncode, ran.stdout.splitlines()


# ------------------------------------------------------------------------------------------------
# The state after the failed apply, and the fix plan from it
# ------------------------------------------------------------------------------------------------


def templated_target(revision: int) -> list[dict[str, object]]:
    """The run schedule's ECS template as `terraform show -json` gives it."""
    return [
        {
            "arn": CLUSTER,
            "role_arn": "arn:aws:iam::111122223333:role/debate-dev-caselist-run-scheduler",
            "input": None,
            "ecs_parameters": [
                {
                    "task_definition_arn": f"{REVISIONS}{revision}",
                    "task_count": 1,
                    "launch_type": "FARGATE",
                    "platform_version": "LATEST",
                    "enable_execute_command": False,
                    "enable_ecs_managed_tags": False,
                    "network_configuration": [
                        {
                            "subnets": ["subnet-0b", "subnet-0a"],
                            "security_groups": ["sg-0a"],
                            "assign_public_ip": True,
                        }
                    ],
                }
            ],
            "retry_policy": [{"maximum_retry_attempts": 3, "maximum_event_age_in_seconds": 3600}],
            "dead_letter_config": [{"arn": "arn:aws:sqs:us-east-1:111122223333:debate-dev-caselist-run-dlq"}],
        }
    ]


def request(revision: int = 17, **changed: object) -> dict[str, object]:
    """The Input the fixed module writes, in the SDK's PascalCase, written out by hand."""
    body: dict[str, object] = {
        "Cluster": CLUSTER,
        "TaskDefinition": f"{REVISIONS}{revision}",
        "Count": 1,
        "LaunchType": "FARGATE",
        "PlatformVersion": "LATEST",
        "EnableExecuteCommand": False,
        "EnableECSManagedTags": False,
        "NetworkConfiguration": {
            "AwsvpcConfiguration": {
                "Subnets": ["subnet-0a", "subnet-0b"],
                "SecurityGroups": ["sg-0a"],
                "AssignPublicIp": "ENABLED",
            }
        },
        "Overrides": {"ContainerOverrides": [{"Name": "run", "Command": SCHEDULED}]},
    }
    body.update(changed)
    return body


def universal_target(input_: dict[str, object] | None) -> list[dict[str, object]]:
    [target] = copy.deepcopy(templated_target(15))
    target.update(arn=UNIVERSAL, ecs_parameters=[], input=None if input_ is None else json.dumps(input_))
    return [target]


def schedule_side(target: list[dict[str, object]], state: str = "ENABLED") -> dict[str, object]:
    return {
        "name": "debate-dev-caselist-run",
        "group_name": "debate-dev-caselist-run",
        "state": state,
        "schedule_expression": "cron(0 6 ? * WED *)",
        "target": target,
    }


def run_schedule(input_: dict[str, object] | None = None) -> dict[str, Any]:
    change = entry(
        RUN_SCHEDULE,
        ["update"],
        schedule_side(templated_target(15)),
        schedule_side(universal_target(request() if input_ is None else input_)),
    )
    return change


def current_revision(revision: int = 17, digest: str = NEW_DIGEST) -> dict[str, Any]:
    """The run task definition the failed apply left: refreshed, not changed."""
    side = task_side("run", digest) | {"arn": f"{REVISIONS}{revision}", "revision": revision}
    side["container_definitions"] = container_definitions("run", digest)
    return entry(RUN_DEFINITION, ["no-op"], side, copy.deepcopy(side))


def run_policy(revision: int = 17) -> dict[str, Any]:
    side = {
        "name": "start-the-run-task",
        "role": "debate-dev-caselist-run-scheduler",
        "policy": json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "RunThisRunTaskDefinitionOnTheRunsCluster",
                        "Effect": "Allow",
                        "Action": "ecs:RunTask",
                        "Resource": f"{REVISIONS}{revision}",
                        "Condition": {"ArnEquals": {"ecs:cluster": CLUSTER}},
                    },
                    {
                        "Sid": "PassTheRunRolesToEcsOnly",
                        "Effect": "Allow",
                        "Action": "iam:PassRole",
                        "Resource": [],
                    },
                ],
            }
        ),
    }
    return entry(RUN_POLICY, ["no-op"], side, copy.deepcopy(side))


def bedrock_policy_update(actions: list[str] | None = None, **after: object) -> dict[str, Any]:
    before = {
        "instance_arn": "arn:aws:sso:::instance/ssoins-1",
        "permission_set_arn": "arn:aws:sso:::permissionSet/ssoins-1/ps-1",
        "inline_policy": '{"Statement":[{"Action":"bedrock:InvokeModel","Resource":["arn:old"]}]}',
    }
    new = before | {
        "inline_policy": '{"Statement":[{"Action":"bedrock:InvokeModel","Resource":["arn:new"]}]}'
    }
    new.update(after)
    return entry(BEDROCK_POLICY, actions or ["update"], before, new)


def fix_plan() -> Plan:
    """From the state after the failed apply: the run schedule alone, 0 to add, 1 to change."""
    return {
        "format_version": "1.2",
        "terraform_version": "1.16.0",
        "resource_changes": [
            run_schedule(),
            current_revision(),
            run_policy(),
            unchanged(LOGIN_DEFINITION),
            unchanged(LOGIN_SCHEDULE),
            unchanged(LOGIN_POLICY),
            unchanged(f"{M}aws_cloudwatch_metric_alarm.late_run"),
            unchanged(TASK_STOPPED_RUN),
            unchanged(BEDROCK_POLICY),
            unchanged(BEDROCK_SET),
            unchanged(BEDROCK_ASSIGNMENT),
            unchanged('aws_ssoadmin_account_assignment.evidence_operator["coach"]'),
            entry("data.aws_caller_identity.current", ["read"], None, {}),
        ],
    }


def with_bedrock(plan: Plan, change: dict[str, Any] | None = None) -> Plan:
    changed_instead(plan, change or bedrock_policy_update())
    return plan


SAID: Final = (
    "PLAN OK: 0 to add, 1 to change, 0 to destroy; the run schedule alone moved onto Scheduler's "
    "universal RunTask target, starting debate-dev-caselist-run:17 with --json caselist pull --scheduled "
    "on its cluster, network and launch settings as before, and its role and every other target setting "
    "as before; the run scheduler role's policy names that revision, which runs the image "
    "sha256:222222222222...; the run schedule ENABLED throughout; nothing else changes"
)
SAID_BESIDE_BEDROCK: Final = SAID.replace("0 to add, 1 to change", "0 to add, 2 to change").replace(
    "nothing else changes", "nothing else in module.caselist_run changes"
)
BEDROCK_LINE: Final = (
    f"PLAN OK, outside module.caselist_run: {BEDROCK_POLICY} updated in place, its inline_policy alone "
    "(v1-e05-t20's grant): read its diff in the plan"
)


# ------------------------------------------------------------------------------------------------
# PLAN OK
# ------------------------------------------------------------------------------------------------


def test_the_fix_plan_is_plan_ok_with_run_schedule_only(tmp_path: Path) -> None:
    code, said = run_check(fix_plan(), tmp_path, FLAG)

    assert said == [SAID]
    assert code == 0


def test_the_fix_plan_beside_v1_e05_t20s_grant_names_the_grant_on_its_own_line(tmp_path: Path) -> None:
    code, said = run_check(with_bedrock(fix_plan()), tmp_path, FLAG)

    assert said == [SAID_BESIDE_BEDROCK, BEDROCK_LINE]
    assert code == 0


def test_the_input_reads_the_same_in_any_subnet_order(tmp_path: Path) -> None:
    plan = fix_plan()
    networks = request()["NetworkConfiguration"]
    assert isinstance(networks, dict)
    networks["AwsvpcConfiguration"]["Subnets"] = ["subnet-0b", "subnet-0a"]
    changed_instead(plan, run_schedule(request(NetworkConfiguration=networks)))

    code, said = run_check(plan, tmp_path, FLAG)

    assert said == [SAID]
    assert code == 0


# ------------------------------------------------------------------------------------------------
# PLAN STOP: the run schedule, the revision and the module
# ------------------------------------------------------------------------------------------------


def input_of(**changed: object) -> Callable[[Plan], None]:
    return lambda plan: changed_instead(plan, run_schedule(request(**changed)))


def camel_case_input(plan: Plan) -> None:
    body = request()
    body["taskDefinition"] = body.pop("TaskDefinition")
    changed_instead(plan, run_schedule(body))


def input_unknown(plan: Plan) -> None:
    schedule = change_of(plan, RUN_SCHEDULE)
    del schedule["after"]["target"][0]["input"]
    schedule["after_unknown"] = {"target": [{"ecs_parameters": [], "input": True}]}


def target_after(**changed: object) -> Callable[[Plan], None]:
    return lambda plan: change_of(plan, RUN_SCHEDULE)["after"]["target"][0].update(changed)


def replaced(address: str) -> Callable[[Plan], None]:
    def change(plan: Plan) -> None:
        change_of(plan, address)["actions"] = ["delete", "create"]

    return change


def the_run_revision_replaced(plan: Plan) -> None:
    found = change_of(plan, RUN_DEFINITION)
    found["actions"] = ["delete", "create"]
    found["after_unknown"] = {"arn": True, "revision": True}


def the_policy_naming(revision: int) -> Callable[[Plan], None]:
    return lambda plan: changed_instead(plan, run_policy(revision))


def the_revision_on(digest: str) -> Callable[[Plan], None]:
    return lambda plan: changed_instead(plan, current_revision(digest=digest))


def the_login_schedule_changed(plan: Plan) -> None:
    changed_instead(plan, entry(LOGIN_SCHEDULE, ["update"], {"state": "ENABLED"}, {"state": "DISABLED"}))


def disabled(plan: Plan) -> None:
    change_of(plan, RUN_SCHEDULE)["after"]["state"] = "DISABLED"


def no_run_revision(plan: Plan) -> None:
    plan["resource_changes"] = [
        found for found in plan["resource_changes"] if found["address"] != RUN_DEFINITION
    ]


STOPS: Final[dict[str, tuple[Callable[[Plan], None], str]]] = {
    "the Input names the revision the apply deregistered": (
        input_of(TaskDefinition=f"{REVISIONS}15"),
        f"{RUN_SCHEDULE}'s Input starts debate-dev-caselist-run:15, not the run task definition's current "
        "revision debate-dev-caselist-run:17",
    ),
    "the Input in the API reference's camelCase": (
        camel_case_input,
        f"{RUN_SCHEDULE}'s Input lacks ['TaskDefinition'] and has names the SDK's RunTask request does not: "
        "['taskDefinition']",
    ),
    "the command without --scheduled": (
        input_of(
            Overrides={"ContainerOverrides": [{"Name": "run", "Command": ["--json", "caselist", "pull"]}]}
        ),
        DIFFERS + "['Overrides']",
    ),
    "another cluster": (
        input_of(Cluster="arn:aws:ecs:us-east-1:111122223333:cluster/another"),
        DIFFERS + "['Cluster']",
    ),
    "another subnet": (
        input_of(
            NetworkConfiguration={
                "AwsvpcConfiguration": {
                    "Subnets": ["subnet-0a", "subnet-0c"],
                    "SecurityGroups": ["sg-0a"],
                    "AssignPublicIp": "ENABLED",
                }
            }
        ),
        DIFFERS + "['NetworkConfiguration']",
    ),
    "two tasks": (
        input_of(Count=2),
        DIFFERS + "['Count']",
    ),
    "an Input the plan cannot know": (
        input_unknown,
        f"{RUN_SCHEDULE}'s Input is unknown in the plan, which means a revision this plan creates; this "
        "plan creates none",
    ),
    "the templated parameters left beside the universal target": (
        target_after(ecs_parameters=templated_target(15)[0]["ecs_parameters"]),
        f"{RUN_SCHEDULE} keeps templated ECS parameters beside the universal target",
    ),
    "another role": (
        target_after(role_arn="arn:aws:iam::111122223333:role/another"),
        f"{RUN_SCHEDULE} also changes its target's ['role_arn']",
    ),
    "a universal target for another API": (
        target_after(arn="arn:aws:scheduler:::aws-sdk:ecs:stopTask"),
        f"{RUN_SCHEDULE}'s target is the ECS template -> the ECS template, expected the ECS template -> "
        "Scheduler's universal RunTask target",
    ),
    "the schedule replaced": (replaced(RUN_SCHEDULE), f"{RUN_SCHEDULE}: delete/create, expected an update"),
    "the schedule disabled": (
        disabled,
        f"{RUN_SCHEDULE} is ENABLED -> DISABLED, expected ENABLED throughout",
    ),
    "the run task definition replaced again": (
        the_run_revision_replaced,
        f"{RUN_DEFINITION} changes in this plan (delete/create): this plan changes the run schedule alone",
    ),
    "no run task definition in the plan": (
        no_run_revision,
        f"{RUN_DEFINITION} is not in the plan, so the revision the schedule starts cannot be read",
    ),
    "the policy naming another revision": (
        the_policy_naming(15),
        "the run scheduler role's policy names debate-dev-caselist-run:15, not the revision the schedule "
        "will start, debate-dev-caselist-run:17",
    ),
    "the revision on another image": (
        the_revision_on(OLD_DIGEST),
        f"{RUN_DEFINITION}'s image is 111122223333.dkr.ecr.us-east-1.amazonaws.com/debate-dev-caselist-run@"
        f"{OLD_DIGEST}, expected the digest in owner.auto.tfvars",
    ),
    "the login schedule changed too": (
        the_login_schedule_changed,
        f"an unexpected change in module.caselist_run: {LOGIN_SCHEDULE} (update)",
    ),
    "a change elsewhere": (
        lambda plan: changed_instead(
            plan,
            entry(
                "module.evidence_bucket.aws_s3_bucket_policy.this",
                ["update"],
                {"policy": "a"},
                {"policy": "b"},
            ),
        ),
        "a change outside module.caselist_run: module.evidence_bucket.aws_s3_bucket_policy.this (update)",
    ),
}


@pytest.mark.parametrize("case", STOPS)
def test_any_other_fix_plan_is_plan_stop_naming_the_change(tmp_path: Path, case: str) -> None:
    plan = fix_plan()
    change, expected = STOPS[case]
    change(plan)

    code, said = run_check(plan, tmp_path, FLAG)

    assert len(said) == 1, said
    assert said[0].startswith("PLAN STOP: "), said
    assert expected in said[0], said
    assert code == 1


# ------------------------------------------------------------------------------------------------
# PLAN STOP: anything from v1-e05-t20 but the policy's in-place update
# ------------------------------------------------------------------------------------------------

BEDROCK_STOPS: Final[dict[str, dict[str, Any]]] = {
    "the policy replaced": bedrock_policy_update(["delete", "create"]),
    "the policy replaced, created first": bedrock_policy_update(["create", "delete"]),
    "the policy created": entry(BEDROCK_POLICY, ["create"], None, {"inline_policy": "{}"}),
    "the policy destroyed": entry(BEDROCK_POLICY, ["delete"], {"inline_policy": "{}"}, None),
    "the policy moved to another permission set": bedrock_policy_update(permission_set_arn="arn:other"),
    "the permission set changed": entry(
        BEDROCK_SET, ["update"], {"session_duration": "PT8H"}, {"session_duration": "PT1H"}
    ),
    "an account assignment added": entry(
        BEDROCK_ASSIGNMENT.replace("coach", "other"), ["create"], None, {"id": "y"}
    ),
    "an account assignment removed": entry(BEDROCK_ASSIGNMENT, ["delete"], {"id": "x"}, None),
}


@pytest.mark.parametrize("case", BEDROCK_STOPS)
def test_anything_from_the_grant_but_its_policys_update_in_place_is_plan_stop(
    tmp_path: Path, case: str
) -> None:
    plan = fix_plan()
    changed_instead(plan, copy.deepcopy(BEDROCK_STOPS[case]))

    code, said = run_check(plan, tmp_path, FLAG)

    assert len(said) == 1, said
    assert said[0].startswith("PLAN STOP: "), said
    assert "an Identity Center change, which never passes" in said[0], said
    assert code == 1


def test_a_replaced_grant_policy_is_named_as_more_than_its_update_in_place(tmp_path: Path) -> None:
    code, said = run_check(
        with_bedrock(fix_plan(), bedrock_policy_update(["delete", "create"])), tmp_path, FLAG
    )

    assert f"{BEDROCK_POLICY} (delete/create): only an in-place update of its inline_policy passes" in said[0]
    assert code == 1


def test_the_grants_update_is_allowed_by_run_schedule_only_alone(tmp_path: Path) -> None:
    """The image check, its memory and its universal-target modes never allow it."""
    for flags in ([], ["--memory"], ["--universal-target"]):
        code, said = run_check(with_bedrock(fix_plan()), tmp_path, *flags)

        assert said[0].startswith("PLAN STOP: "), (flags, said)
        assert f"an Identity Center change, which never passes: {BEDROCK_POLICY} (update)" in said[0], said
        assert code == 1


def test_run_schedule_only_beside_another_mode_is_refused(tmp_path: Path) -> None:
    plan_file, owner_file = write_owner_and_plan(fix_plan(), tmp_path)
    for other in ("--memory", "--universal-target"):
        ran = subprocess.run(
            [sys.executable, "-I", str(SCRIPT), str(plan_file), str(owner_file), FLAG, other],
            capture_output=True,
            text=True,
            check=False,
        )

        assert ran.returncode == 2, ran
        assert "not allowed with argument" in ran.stderr, ran.stderr


def test_the_image_check_refuses_the_fix_plan(tmp_path: Path) -> None:
    code, said = run_check(fix_plan(), tmp_path)

    assert said[0].startswith("PLAN STOP: "), said
    assert f"{RUN_SCHEDULE} moves its target onto Scheduler's universal RunTask target" in said[0], said
    assert code == 1


# ------------------------------------------------------------------------------------------------
# The runbook's section: the fix's blocks, and the PLAN OK lines it quotes
# ------------------------------------------------------------------------------------------------

RUNBOOK: Final = Path(__file__).resolve().parents[2] / "docs" / "runbooks" / "caselist-cloud-run.md"
FIX_HEADING: Final = "\n## The run schedule alone, after the apply of 2026-11-15 (`v1-e40-t48`)\n"
DEV_439: Final = "sha256:764f9ba4f621" + "0" * 52


def fix_section() -> str:
    text = RUNBOOK.read_text(encoding="utf-8")
    start = text.index(FIX_HEADING)
    return text[start : text.index("\n## ", start + 1)]


def fix_blocks() -> list[str]:
    return re.findall(r"```bash\n(.*?)```", fix_section(), flags=re.DOTALL)


def fix_block_with(needle: str) -> str:
    [found] = [block for block in fix_blocks() if needle in block]
    return found


def quoted_plan_ok_lines() -> list[str]:
    return re.findall(r"`(PLAN OK[^`]*)`", fix_section())


def test_the_fix_section_follows_the_schedule_section() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    schedule = text.index("\n## The schedule passes --scheduled (`v1-e40-t48`), once\n")

    assert schedule < text.index(FIX_HEADING) < text.index("\n## A failed parse stage\n")
    assert text.index("\n## ", schedule + 1) == text.index(FIX_HEADING)


def test_the_quoted_plan_ok_lines_are_what_the_check_prints_for_dev_439_and_revision_17(
    tmp_path: Path,
) -> None:
    """The lines the PM is told to expect, held to the check's own output on the same state."""
    plan = fix_plan()
    changed_instead(plan, current_revision(digest=DEV_439))
    alone_file, owner_file = write_owner_and_plan(plan, tmp_path)
    owner_file.write_text(
        owner_file.read_text(encoding="utf-8").replace(NEW_DIGEST, DEV_439), encoding="utf-8"
    )
    beside = tmp_path / "beside.json"
    beside.write_text(json.dumps(with_bedrock(copy.deepcopy(plan))), encoding="utf-8")

    said = []
    for plan_file in (alone_file, beside):
        ran = subprocess.run(
            [sys.executable, "-I", str(SCRIPT), str(plan_file), str(owner_file), FLAG],
            capture_output=True,
            text=True,
            check=False,
        )
        assert ran.returncode == 0, ran.stdout
        said += ran.stdout.splitlines()

    assert quoted_plan_ok_lines() == said
    assert "`Plan: 0 to add, 1 to change, 0 to destroy.`" in fix_section()
    assert "`Plan: 0 to add, 2 to change, 0 to\ndestroy.`" in fix_section()


def test_the_state_block_prints_the_target_the_revision_and_the_state_alone(tmp_path: Path) -> None:
    block = fix_block_with("<<'STATE'")
    schedules = {
        "the template on :15": (
            {
                "Name": "debate-dev-caselist-run",
                "State": "ENABLED",
                "Target": {
                    "Arn": CLUSTER,
                    "RoleArn": "arn:aws:iam::111122223333:role/debate-dev-caselist-run-scheduler",
                    "EcsParameters": {"TaskDefinitionArn": f"{REVISIONS}15", "TaskCount": 1},
                },
            },
            "target: the ECS template, cluster debate-dev-caselist-run\n"
            "revision: debate-dev-caselist-run:15\nstate: ENABLED\n",
        ),
        "the universal target on :17": (
            {
                "Name": "debate-dev-caselist-run",
                "State": "ENABLED",
                "Target": {
                    "Arn": UNIVERSAL,
                    "Input": json.dumps(request()),
                },
            },
            f"target: {UNIVERSAL}\nrevision: debate-dev-caselist-run:17\nstate: ENABLED\n",
        ),
    }
    for schedule, expected in schedules.values():
        saved = tmp_path / "schedule.json"
        saved.write_text(json.dumps(schedule), encoding="utf-8")

        ran = subprocess.run(
            [sys.executable, "-I", "-", str(saved)],
            input=re.findall(r"<<'STATE'\n(.*?)\nSTATE\n", block, flags=re.DOTALL)[0],
            capture_output=True,
            text=True,
            check=False,
        )

        assert ran.returncode == 0, ran.stderr
        assert ran.stdout == expected
        assert "111122223333" not in ran.stdout
    assert (
        "get-schedule --region us-east-1 --group-name debate-dev-caselist-run --name debate-dev-caselist-run "
        in block
    )


def test_the_plan_block_checks_the_saved_plans_json_with_run_schedule_only() -> None:
    block = fix_block_with(" plan ")

    assert "rm -f infrastructure/envs/dev/caselist-run-schedule-alone.tfplan" in block
    assert "plan -input=false -no-color -out=caselist-run-schedule-alone.tfplan" in block
    assert (
        "show -json caselist-run-schedule-alone.tfplan > /tmp/caselist-run-schedule-alone-plan.json" in block
    )
    assert (
        "python3 -I ops/caselist_run/check_image_plan.py /tmp/caselist-run-schedule-alone-plan.json "
        "infrastructure/envs/dev/owner.auto.tfvars --run-schedule-only"
    ) in block
    assert " apply " not in block


def test_the_apply_block_applies_the_checked_plan_never_on_a_wednesday_in_chicago() -> None:
    block = fix_block_with(" apply ")

    assert "apply -input=false caselist-run-schedule-alone.tfplan" in block
    assert 'if [ "$(TZ=America/Chicago date +%A)" = "Wednesday" ]; then echo "STOP' in block
    assert "--desired-status RUNNING" in block
    assert " plan " not in block
    assert "never a Wednesday" in fix_section()


def test_the_section_says_the_fallback_if_it_is_not_applied_by_tuesday() -> None:
    section = " ".join(fix_section().split())

    assert "If it is not applied by Tuesday night" in section
    assert "After 06:00 Chicago on Wednesday, start the week by hand" in section
    assert "launch-refused email" in section


def test_no_block_of_the_fix_section_puts_an_exclamation_mark_in_a_shell_line() -> None:
    for block in fix_blocks():
        shell = re.sub(r"<<'([A-Z]+)'\n.*?\n\1\n", "\n", block, flags=re.DOTALL)
        assert "!" not in shell, block
