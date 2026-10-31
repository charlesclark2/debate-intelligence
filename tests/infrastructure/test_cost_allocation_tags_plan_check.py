"""The cost allocation tags' plan check, run on synthetic plans (`v1-e05-t18`).

`docs/runbooks/aws-account-baseline.md` checks the organization root's plan in `terraform show
-json`'s shape before the PM reads it: `COSTTAGSPLAN` prints `PLAN OK` only when the plan's change
entries are the `Project` and `Environment` cost allocation tags, each imported with nothing to
change (or created), each `Active`, and nothing else in the root. A change entry is a resource whose
actions are not `no-op` or `read`, or one being imported, so permission sets and budgets that the
plan only reads are never counted. The code is read out of the runbook, between its heredoc markers,
and run as the operator runs it (`python3 -I -` with the plan's JSON as its argument), so a change
to the runbook is what is tested.

Every plan here is written by hand. Its shape is the one Terraform 1.16 and hashicorp/aws 5.100.0
gave for these import blocks against a loopback stand-in for Cost Explorer (the session report):
`actions: ["no-op"]` and `importing: {"id": <key>}` for a tag found Active, `actions: ["update"]`
with `importing` for one found Inactive. No account, no real address, nothing from a real plan.
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

RUNBOOK = Path(__file__).resolve().parents[2] / "docs" / "runbooks" / "aws-account-baseline.md"
PROJECT: Final = 'module.cost_allocation_tags.aws_ce_cost_allocation_tag.this["Project"]'
ENVIRONMENT: Final = 'module.cost_allocation_tags.aws_ce_cost_allocation_tag.this["Environment"]'

Plan = dict[str, Any]


def check_code() -> str:
    """The Python between `<<'COSTTAGSPLAN'` and its closing line in the runbook."""
    text = RUNBOOK.read_text(encoding="utf-8")
    [found] = re.findall(r"<<'COSTTAGSPLAN'\n(.*?)\nCOSTTAGSPLAN\n", text, flags=re.DOTALL)
    return found


def run_check(plan: Plan, tmp_path: Path) -> str:
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(plan), encoding="utf-8")
    ran = subprocess.run(
        [sys.executable, "-I", "-", str(plan_file)],
        input=check_code(),
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


def tag_state(key: str, status: str) -> dict[str, str]:
    return {"id": key, "status": status, "tag_key": key, "type": "UserDefined"}


def imported(address: str, key: str) -> dict[str, Any]:
    return {
        "address": address,
        "type": "aws_ce_cost_allocation_tag",
        "change": {
            "actions": ["no-op"],
            "before": tag_state(key, "Active"),
            "after": tag_state(key, "Active"),
            "importing": {"id": key},
        },
    }


def created(address: str, key: str) -> dict[str, Any]:
    return {
        "address": address,
        "type": "aws_ce_cost_allocation_tag",
        "change": {"actions": ["create"], "before": None, "after": {"status": "Active", "tag_key": key}},
    }


def unchanged(address: str, resource_type: str) -> dict[str, Any]:
    return {"address": address, "type": resource_type, "change": {"actions": ["no-op"]}}


def import_plan() -> Plan:
    """The first apply: both tags already Active, imported, and the rest of the root unchanged."""
    return {
        "resource_changes": [
            imported(ENVIRONMENT, "Environment"),
            imported(PROJECT, "Project"),
            unchanged('aws_budgets_budget.environment_monthly["dev"]', "aws_budgets_budget"),
            unchanged("module.model_spend_budget.aws_budgets_budget.model_spend", "aws_budgets_budget"),
            unchanged("aws_ssoadmin_permission_set.maintainer", "aws_ssoadmin_permission_set"),
            unchanged(
                'aws_ssoadmin_account_assignment.maintainer["mock-maintainer"]',
                "aws_ssoadmin_account_assignment",
            ),
            {
                "address": "data.aws_ssoadmin_instances.current",
                "type": "aws_ssoadmin_instances",
                "change": {"actions": ["read"]},
            },
        ]
    }


def tag_change(plan: Plan, address: str) -> dict[str, Any]:
    [change] = [c for c in plan["resource_changes"] if c["address"] == address]
    return change


# ------------------------------------------------------------------------------------------------
# What passes
# ------------------------------------------------------------------------------------------------


def test_the_import_plan_is_ok(tmp_path: Path) -> None:
    assert run_check(import_plan(), tmp_path) == (
        "PLAN OK: two changes, Project imported and Environment imported, each Active; nothing else"
        " changes; permission set or assignment changes: 0; budget changes: 0"
    )


def test_a_plan_that_creates_both_tags_is_ok(tmp_path: Path) -> None:
    plan = import_plan()
    plan["resource_changes"][:2] = [created(ENVIRONMENT, "Environment"), created(PROJECT, "Project")]

    assert run_check(plan, tmp_path).startswith(
        "PLAN OK: two changes, Project created and Environment created, each Active;"
    )


# ------------------------------------------------------------------------------------------------
# What stops the apply
# ------------------------------------------------------------------------------------------------


def add_change(address: str, resource_type: str, actions: list[str]) -> Callable[[Plan], None]:
    def mutate(plan: Plan) -> None:
        plan["resource_changes"].append(
            {"address": address, "type": resource_type, "change": {"actions": actions}}
        )

    return mutate


def found_inactive(address: str, key: str) -> Callable[[Plan], None]:
    def mutate(plan: Plan) -> None:
        change = tag_change(plan, address)["change"]
        change["actions"] = ["update"]
        change["before"] = tag_state(key, "Inactive")

    return mutate


def planned_inactive(address: str) -> Callable[[Plan], None]:
    def mutate(plan: Plan) -> None:
        tag_change(plan, address)["change"]["after"]["status"] = "Inactive"

    return mutate


def dropped(address: str) -> Callable[[Plan], None]:
    def mutate(plan: Plan) -> None:
        plan["resource_changes"] = [c for c in plan["resource_changes"] if c["address"] != address]

    return mutate


def third_tag_imported(plan: Plan) -> None:
    plan["resource_changes"].append(
        imported('module.cost_allocation_tags.aws_ce_cost_allocation_tag.this["Owner"]', "Owner")
    )


def imported_under_the_other_key(plan: Plan) -> None:
    tag_change(plan, PROJECT)["change"]["importing"] = {"id": "Environment"}


def replaced(plan: Plan) -> None:
    tag_change(plan, PROJECT)["change"]["actions"] = ["delete", "create"]


def destroyed(plan: Plan) -> None:
    change = tag_change(plan, PROJECT)["change"]
    del change["importing"]
    change["actions"] = ["delete"]
    change["after"] = None


def imported_tag_key_differs(plan: Plan) -> None:
    tag_change(plan, ENVIRONMENT)["change"]["after"]["tag_key"] = "environment"


REFUSED: Final[dict[str, tuple[Callable[[Plan], None], str]]] = {
    "the Environment tag found Inactive": (
        found_inactive(ENVIRONMENT, "Environment"),
        "the Environment tag is update on import, not imported unchanged or created",
    ),
    "the Project tag planned Inactive": (
        planned_inactive(PROJECT),
        "the Project tag is planned as Project Inactive",
    ),
    "the Environment tag missing": (
        dropped(ENVIRONMENT),
        "the Environment tag is in the plan 0 times, not once",
    ),
    "a third tag managed": (
        third_tag_imported,
        'other changes: module.cost_allocation_tags.aws_ce_cost_allocation_tag.this["Owner"] no-op',
    ),
    "the Project tag imported as Environment": (
        imported_under_the_other_key,
        "the Project tag is no-op on import, not imported unchanged or created",
    ),
    "a tag replaced": (replaced, "the Project tag is delete/create on import"),
    "a tag destroyed": (destroyed, "the Project tag is delete, not imported unchanged or created"),
    "a tag key in another case": (
        imported_tag_key_differs,
        "the Environment tag is planned as environment Active",
    ),
    "a permission set changed": (
        add_change("aws_ssoadmin_permission_set.maintainer", "aws_ssoadmin_permission_set", ["update"]),
        "permission set or assignment changes: 1; budget changes: 0",
    ),
    "an account assignment added": (
        add_change(
            'aws_ssoadmin_account_assignment.maintainer["someone"]',
            "aws_ssoadmin_account_assignment",
            ["create"],
        ),
        'other changes: aws_ssoadmin_account_assignment.maintainer["someone"] create',
    ),
    "the model spend budget changed": (
        add_change(
            "module.model_spend_budget.aws_budgets_budget.model_spend", "aws_budgets_budget", ["update"]
        ),
        "permission set or assignment changes: 0; budget changes: 1",
    ),
    "an environment budget destroyed": (
        add_change('aws_budgets_budget.environment_monthly["prod"]', "aws_budgets_budget", ["delete"]),
        'other changes: aws_budgets_budget.environment_monthly["prod"] delete',
    ),
    "the anomaly monitor replaced": (
        add_change("aws_ce_anomaly_monitor.project", "aws_ce_anomaly_monitor", ["delete", "create"]),
        "other changes: aws_ce_anomaly_monitor.project delete/create",
    ),
}


@pytest.mark.parametrize("mutate,reason", REFUSED.values(), ids=list(REFUSED))
def test_a_plan_that_differs_is_not_ok_and_says_why(
    mutate: Callable[[Plan], None], reason: str, tmp_path: Path
) -> None:
    plan = copy.deepcopy(import_plan())
    mutate(plan)

    line = run_check(plan, tmp_path)

    assert line.startswith("PLAN NOT OK: ")
    assert reason in line


def test_a_plan_with_nothing_to_do_is_not_ok(tmp_path: Path) -> None:
    """A later plan, after the tags are in state, has no entries: that is not this apply's plan."""
    plan = import_plan()
    plan["resource_changes"] = plan["resource_changes"][2:]

    assert run_check(plan, tmp_path) == (
        "PLAN NOT OK: the Project tag is in the plan 0 times, not once | the Environment tag is in the"
        " plan 0 times, not once | permission set or assignment changes: 0; budget changes: 0"
    )


def test_read_and_unchanged_permission_sets_are_not_counted(tmp_path: Path) -> None:
    plan = import_plan()
    for n in range(26):
        plan["resource_changes"].append(
            unchanged(
                f'aws_ssoadmin_managed_policy_attachment.extra["{n}"]',
                "aws_ssoadmin_managed_policy_attachment",
            )
        )

    assert run_check(plan, tmp_path).endswith("permission set or assignment changes: 0; budget changes: 0")
