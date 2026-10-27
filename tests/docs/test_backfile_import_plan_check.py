"""The backfile imports' plan check, run on synthetic plans, and what it guards in the code (`v1-e40-t09`).

`docs/runbooks/caselist-cloud-run.md`, "Backfile imports", checks the one apply this task needs in
`terraform show -json`'s shape before the PM reads it, as `v1-e40-t06`'s cutover checks do:
`BACKFILEPLAN` prints `PLAN OK` only when the run-stopped alert's text gains the sentence naming a
hand-started backfile import and nothing else in the plan changes. The code is read out of the runbook,
between its heredoc markers, and run as the operator runs it (`python3 -I -`, the plan's JSON as its
argument), so a change to the runbook is what is tested.

Every plan here is written by hand in the shape Terraform gives an event target updated in place: no
account, no real ARN, nothing from a real plan. The alert's text is written out here too, and held to
`alerts.tf`'s own, so the check and the module cannot part.

Beside it, what no synthetic plan can show of the code itself: that the module and the roots declare
no schedule but the login's and the run's, and that the storage figure the module's tests hold is
`v1-e34-t34`'s own estimate for the largest backfile.
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

from debate_core.application.caselist.backfile_import import space_needed

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "caselist-cloud-run.md"
MODULE = REPO_ROOT / "infrastructure" / "modules" / "caselist_run"
INFRASTRUCTURE = REPO_ROOT / "infrastructure"
SEASONS = REPO_ROOT / "docs" / "data" / "caselist-backfile-seasons.md"

M: Final = "module.caselist_run."
TARGET: Final = M + 'aws_cloudwatch_event_target.task_stopped["run"]'
TOPIC: Final = "arn:aws:sns:us-east-1:111122223333:debate-dev-caselist-run-alerts"
OLD_TEXT: Final = (
    '"The dev weekly caselist run task stopped with exit code <exit_code> (<stop_code>: <reason>). Task '
    "<task>. Read its log, debate-dev-caselist-run, and debate-research caselist runs --remote; "
    'docs/runbooks/caselist-cloud-run.md."'
)
SENTENCE: Final = (
    " It is the weekly run, or a backfile import someone started by hand "
    "(docs/runbooks/caselist-cloud-run.md, Backfile imports): the command on the last line of its log "
    "says which."
)
NEW_TEXT: Final = OLD_TEXT.replace("Task <task>.", "Task <task>." + SENTENCE)
PATHS: Final = {
    "task": "$.detail.taskArn",
    "exit_code": "$.detail.containers[0].exitCode",
    "stop_code": "$.detail.stopCode",
    "reason": "$.detail.stoppedReason",
}
LARGEST_REQUIRED_BYTES: Final = 32_750_091_060
"""hsld25's need with headroom, the figure the module's test holds the run's storage to."""

Plan = dict[str, Any]


def check_code(marker: str) -> str:
    """The Python between `<<'MARKER'` and its closing `MARKER` line in the runbook."""
    text = RUNBOOK.read_text(encoding="utf-8")
    [found] = re.findall(rf"<<'{marker}'\n(.*?)\n{marker}\n", text, flags=re.DOTALL)
    return found


def run_check(plan: Plan, tmp_path: Path) -> str:
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(plan), encoding="utf-8")
    ran = subprocess.run(
        [sys.executable, "-I", "-", str(plan_file)],
        input=check_code("BACKFILEPLAN"),
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


def target_side(text: str, **changed: object) -> dict[str, object]:
    side: dict[str, object] = {
        "rule": "debate-dev-caselist-run-stopped",
        "target_id": "tell-the-coach",
        "arn": TOPIC,
        "event_bus_name": "default",
        "input_transformer": [{"input_paths": dict(PATHS), "input_template": text}],
    }
    side.update(changed)
    return side


def unchanged(address: str) -> dict[str, object]:
    return {
        "address": address,
        "change": {"actions": ["no-op"], "before": {}, "after": {}, "after_unknown": {}},
    }


def alert_plan() -> Plan:
    """The plan as it should be: 0 to add, 1 to change, 0 to destroy."""
    return {
        "resource_changes": [
            {
                "address": TARGET,
                "change": {
                    "actions": ["update"],
                    "before": target_side(OLD_TEXT),
                    "after": target_side(NEW_TEXT),
                    "after_unknown": {},
                },
            },
            unchanged(M + 'aws_cloudwatch_event_target.task_stopped["login"]'),
            unchanged(M + "aws_ecs_task_definition.run[0]"),
            unchanged(M + "aws_scheduler_schedule.run[0]"),
            unchanged(M + "aws_iam_role_policy.run_credentials"),
            unchanged("module.evidence_store.aws_s3_bucket.evidence"),
        ]
    }


def change_of(plan: Plan, address: str) -> dict[str, Any]:
    return next(entry["change"] for entry in plan["resource_changes"] if entry["address"] == address)


def added(plan: Plan, address: str, actions: list[str], after: dict[str, object] | None = None) -> None:
    plan["resource_changes"].append(
        {
            "address": address,
            "change": {"actions": actions, "before": {}, "after": after or {}, "after_unknown": {}},
        }
    )


def a_schedule_added_for_the_import(plan: Plan) -> None:
    added(
        plan,
        M + "aws_scheduler_schedule.backfile_import[0]",
        ["create"],
        {"name": "debate-dev-caselist-backfile-import", "schedule_expression": "cron(0 6 ? * THU *)"},
    )


def the_run_schedule_given_an_input_aimed_at_the_import(plan: Plan) -> None:
    command = ["--json", "caselist", "backfile-import", "--caselist", "hsld25", "--execute"]
    before = {"name": "debate-dev-caselist-run", "target": [{"input": None}]}
    after = {
        "name": "debate-dev-caselist-run",
        "target": [{"input": json.dumps({"containerOverrides": [{"name": "run", "command": command}]})}],
    }
    plan["resource_changes"] = [
        e for e in plan["resource_changes"] if not e["address"].endswith("schedule.run[0]")
    ]
    plan["resource_changes"].append(
        {
            "address": M + "aws_scheduler_schedule.run[0]",
            "change": {"actions": ["update"], "before": before, "after": after, "after_unknown": {}},
        }
    )


def the_run_task_definition_replaced(plan: Plan) -> None:
    plan["resource_changes"] = [
        e for e in plan["resource_changes"] if not e["address"].endswith("definition.run[0]")
    ]
    added(
        plan,
        M + "aws_ecs_task_definition.run[0]",
        ["delete", "create"],
        {"family": "debate-dev-caselist-run"},
    )


def a_grant_on_the_run_role(plan: Plan) -> None:
    plan["resource_changes"] = [
        e for e in plan["resource_changes"] if not e["address"].endswith("run_credentials")
    ]
    added(
        plan,
        M + "aws_iam_role_policy.run_credentials",
        ["update"],
        {"policy": '{"Statement":[{"Action":"*"}]}'},
    )


def a_new_policy_on_the_run_role(plan: Plan) -> None:
    added(plan, M + "aws_iam_role_policy.run_backfile", ["create"], {"role": "debate-dev-caselist-run"})


def the_deployers_permission_set_widened(plan: Plan) -> None:
    added(plan, M + "aws_ssoadmin_permission_set_inline_policy.deployer[0]", ["update"])


def an_account_assignment_destroyed(plan: Plan) -> None:
    added(plan, 'aws_ssoadmin_account_assignment.evidence_operator["coach"]', ["delete"])


def a_change_outside_the_module(plan: Plan) -> None:
    added(plan, "module.evidence_store.aws_s3_bucket_policy.evidence", ["update"])


def the_target_replaced(plan: Plan) -> None:
    change_of(plan, TARGET)["actions"] = ["delete", "create"]


def its_input_paths_changed(plan: Plan) -> None:
    after = change_of(plan, TARGET)["after"]
    after["input_transformer"][0]["input_paths"] = PATHS | {"started_by": "$.detail.startedBy"}


def a_text_that_does_not_name_the_import(plan: Plan) -> None:
    after = change_of(plan, TARGET)["after"]
    after["input_transformer"][0]["input_template"] = OLD_TEXT.replace("Task <task>.", "Task <task>. Or not.")


def the_text_changed_beyond_the_sentence(plan: Plan) -> None:
    after = change_of(plan, TARGET)["after"]
    after["input_transformer"][0]["input_template"] = NEW_TEXT.replace(
        " weekly caselist run task", " run task"
    )


def the_rule_moved_too(plan: Plan) -> None:
    change_of(plan, TARGET)["after"]["rule"] = "debate-dev-caselist-anything"


def the_login_alert_changed_too(plan: Plan) -> None:
    plan["resource_changes"] = [e for e in plan["resource_changes"] if '["login"]' not in e["address"]]
    added(plan, M + 'aws_cloudwatch_event_target.task_stopped["login"]', ["update"])


def no_change_to_the_alert(plan: Plan) -> None:
    plan["resource_changes"] = [e for e in plan["resource_changes"] if e["address"] != TARGET]


STOPPED: Final[dict[str, tuple[Callable[[Plan], None], str]]] = {
    "a schedule added for the import": (a_schedule_added_for_the_import, "a schedule is added or changed"),
    "the run schedule given an input aimed at the import": (
        the_run_schedule_given_an_input_aimed_at_the_import,
        "a schedule is added or changed: ['module.caselist_run.aws_scheduler_schedule.run[0] update']",
    ),
    "the run task definition replaced": (
        the_run_task_definition_replaced,
        "aws_ecs_task_definition.run[0] delete/create",
    ),
    "a grant on the run role": (a_grant_on_the_run_role, "aws_iam_role_policy.run_credentials update"),
    "a new policy on the run role": (a_new_policy_on_the_run_role, "aws_iam_role_policy.run_backfile create"),
    "the deployer's permission set widened": (
        the_deployers_permission_set_widened,
        "an account assignment or permission set changes",
    ),
    "an account assignment destroyed": (
        an_account_assignment_destroyed,
        "an account assignment or permission set changes",
    ),
    "a change outside the module": (a_change_outside_the_module, "changes outside module.caselist_run"),
    "the target replaced": (the_target_replaced, "expected an update in place"),
    "its input paths changed": (its_input_paths_changed, "changes its input paths"),
    "a text that does not name the import": (a_text_that_does_not_name_the_import, "does not name"),
    "the text changed beyond the sentence": (the_text_changed_beyond_the_sentence, "beyond the sentence"),
    "the rule moved too": (the_rule_moved_too, "changes ['input_transformer', 'rule']"),
    "the login's alert changed too": (the_login_alert_changed_too, 'task_stopped["login"] update'),
    "no change to the alert": (no_change_to_the_alert, "does not change"),
}


# ------------------------------------------------------------------------------------------------
# BACKFILEPLAN
# ------------------------------------------------------------------------------------------------


def test_the_alerts_text_gaining_its_sentence_and_nothing_else_is_plan_ok(tmp_path: Path) -> None:
    said = run_check(alert_plan(), tmp_path)

    assert said == (
        "PLAN OK: 0 to add, 1 to change, 0 to destroy; the run-stopped alert's text names a hand-started "
        "backfile import and nothing else in it changed; no schedule, task definition, role, policy or "
        "permission set changes; nothing else"
    )


@pytest.mark.parametrize("case", sorted(STOPPED))
def test_any_other_plan_is_plan_stop_naming_why(tmp_path: Path, case: str) -> None:
    plan = copy.deepcopy(alert_plan())
    change, reason = STOPPED[case]
    change(plan)

    said = run_check(plan, tmp_path)

    assert said.startswith("PLAN STOP: "), said
    assert reason in said, said


def test_the_check_is_in_a_block_that_reads_the_plan_it_saved() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    block = text[text.rindex("```bash", 0, text.index("<<'BACKFILEPLAN'")) : text.index("\nBACKFILEPLAN\n")]
    assert "show -json caselist-backfile-alert.tfplan > /tmp/caselist-backfile-alert-plan.json" in block
    assert "python3 -I - /tmp/caselist-backfile-alert-plan.json <<'BACKFILEPLAN'" in block
    assert "apply -input=false caselist-backfile-alert.tfplan" in text


def test_the_text_the_check_expects_is_the_modules_own() -> None:
    """`alerts.tf`'s run message for dev, as Terraform renders it: the check's after-text exactly."""
    alerts = (MODULE / "alerts.tf").read_text(encoding="utf-8")
    [template] = re.findall(r'^\s+run\s+=\s+"(.*)"$', alerts, flags=re.M)
    rendered = template.replace("${var.environment}", "dev").replace('\\"', '"')

    assert rendered == NEW_TEXT


# ------------------------------------------------------------------------------------------------
# What it guards, in the code
# ------------------------------------------------------------------------------------------------


def terraform_files() -> list[Path]:
    return sorted(path for path in INFRASTRUCTURE.rglob("*.tf") if ".terraform" not in path.parts)


def test_no_schedule_but_the_logins_and_the_runs_is_declared_and_neither_passes_an_input() -> None:
    """A schedule that starts a backfile import would be a third schedule, an EventBridge rule with an
    ECS target, or an input (RunTask overrides) on one of the two. None exists."""
    schedules = {
        (path.relative_to(REPO_ROOT).as_posix(), name)
        for path in terraform_files()
        for name in re.findall(
            r'^resource "aws_scheduler_schedule" "(\w+)"', path.read_text(encoding="utf-8"), re.M
        )
    }
    assert schedules == {
        ("infrastructure/modules/caselist_run/login_task.tf", "login"),
        ("infrastructure/modules/caselist_run/run_task.tf", "run"),
    }
    for path in terraform_files():
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"^\s*input\s*=", text, re.M), f"{path}: a target input"
        assert "ecs_target" not in text, f"{path}: an EventBridge rule that starts a task"
        assert "backfile" not in text.lower() or path.name == "alerts.tf", f"{path} names a backfile"


def test_the_storage_figure_is_t34s_own_estimate_for_the_largest_backfile() -> None:
    """The four archives' sizes from docs/data, through `space_needed`, against the module's test and
    the runbook's table."""
    sizes = {
        slug: int(size.replace(",", ""))
        for slug, size in re.findall(
            r"^\| 20\d\d-\d\d \| `(hspolicy2[45]|hsld2[45])` \|[^\n]*\| ([\d,]+) \|$",
            SEASONS.read_text(encoding="utf-8"),
            re.M,
        )
    }
    assert set(sizes) == {"hspolicy25", "hsld25", "hspolicy24", "hsld24"}
    required = {slug: space_needed(size, free_bytes=0).required_bytes for slug, size in sizes.items()}

    assert max(required.values()) == required["hsld25"] == LARGEST_REQUIRED_BYTES
    tests = (MODULE / "tests" / "caselist_run.tftest.hcl").read_text(encoding="utf-8")
    assert f">= {LARGEST_REQUIRED_BYTES} + 5 * 1073741824 + 1 * 1073741824" in tests
    runbook = RUNBOOK.read_text(encoding="utf-8")
    for slug, size in sizes.items():
        assert re.search(rf"^\| \d \| `{slug}` \| [^|]+ \| {size} \| {required[slug]} \|$", runbook, re.M), (
            slug
        )
