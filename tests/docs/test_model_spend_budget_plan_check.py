"""The model spend budget's plan check, run on synthetic plans (`v1-e05-t16`).

`docs/runbooks/aws-account-baseline.md` checks the organization root's plan in `terraform show
-json`'s shape before the PM reads it: `MODELBUDGETPLAN` prints `PLAN OK` only for one change, the
budget updated in place (moved into `modules/model_spend_budget` the first time), with the coach's
limit, notices and filter, and nothing else in the root changed, so no permission set or account
assignment. The code is read out of the runbook, between its heredoc markers, and run as the
operator runs it (`python3 -I -` with the plan's JSON as its argument), so a change to the runbook is
what is tested.

Every plan here is written by hand: no account, no real address, nothing from a real plan.
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
ADDRESS: Final = "module.model_spend_budget.aws_budgets_budget.model_spend"
COACH: Final = ["coach@example.org"]

Plan = dict[str, Any]


def check_code() -> str:
    """The Python between `<<'MODELBUDGETPLAN'` and its closing line in the runbook."""
    text = RUNBOOK.read_text(encoding="utf-8")
    [found] = re.findall(r"<<'MODELBUDGETPLAN'\n(.*?)\nMODELBUDGETPLAN\n", text, flags=re.DOTALL)
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


def notice(kind: str, threshold: float) -> dict[str, object]:
    return {
        "comparison_operator": "GREATER_THAN",
        "notification_type": kind,
        "threshold": threshold,
        "threshold_type": "ABSOLUTE_VALUE",
        "subscriber_email_addresses": list(COACH),
        "subscriber_sns_topic_arns": [],
    }


def budget_after() -> dict[str, object]:
    return {
        "name": "debate-shared-bedrock-monthly",
        "budget_type": "COST",
        "limit_amount": "100",
        "limit_unit": "USD",
        "time_unit": "MONTHLY",
        "cost_filter": [
            {
                "name": "Service",
                "values": [
                    "Amazon Bedrock",
                    "Claude Haiku 4.5 (Amazon Bedrock Edition)",
                    "Claude Sonnet 4.6 (Amazon Bedrock Edition)",
                    "Cohere Rerank v3.5 (Amazon Bedrock Edition)",
                ],
            },
            {
                "name": "UsageType",
                "values": [
                    "USE1-MP:USE1_InputTokenCount-Units",
                    "USE1-MP:USE1_OutputTokenCount-Units",
                    "USE1-MP:USE1_search_units-Units",
                    "USE1-TitanEmbeddingV2-Text-input-tokens",
                ],
            },
        ],
        "notification": [
            notice("ACTUAL", 50),
            notice("ACTUAL", 80),
            notice("ACTUAL", 100),
            notice("FORECASTED", 100),
        ],
    }


def unchanged(address: str, resource_type: str) -> dict[str, object]:
    return {"address": address, "type": resource_type, "change": {"actions": ["no-op"]}}


def first_apply_plan() -> Plan:
    """The first apply: the v1-e29-t01 budget moved into the module and updated in place."""
    return {
        "resource_changes": [
            {
                "address": ADDRESS,
                "previous_address": "aws_budgets_budget.bedrock_monthly",
                "type": "aws_budgets_budget",
                "change": {"actions": ["update"], "before": {}, "after": budget_after()},
            },
            unchanged('aws_budgets_budget.environment_monthly["dev"]', "aws_budgets_budget"),
            unchanged("aws_ssoadmin_permission_set.maintainer", "aws_ssoadmin_permission_set"),
            unchanged(
                'aws_ssoadmin_account_assignment.maintainer["mock-maintainer"]',
                "aws_ssoadmin_account_assignment",
            ),
            {
                "address": "data.aws_caller_identity.current",
                "type": "aws_caller_identity",
                "change": {"actions": ["read"]},
            },
        ]
    }


def budget_change(plan: Plan) -> dict[str, Any]:
    [change] = [c for c in plan["resource_changes"] if c["address"] == ADDRESS]
    return change


def edit_after(edit: Callable[[dict[str, Any]], None]) -> Callable[[Plan], None]:
    def mutate(plan: Plan) -> None:
        edit(budget_change(plan)["change"]["after"])

    return mutate


# ------------------------------------------------------------------------------------------------
# What passes
# ------------------------------------------------------------------------------------------------


def test_the_first_apply_s_plan_is_ok(tmp_path: Path) -> None:
    assert run_check(first_apply_plan(), tmp_path) == (
        "PLAN OK: one change, module.model_spend_budget.aws_budgets_budget.model_spend updated in place"
        " (moved from aws_budgets_budget.bedrock_monthly); 100 USD a month; notices at 50, 80 and 100"
        " actual and 100 forecast, to 1 address(es); filter of 4 services and 4 usage types;"
        " permission set or assignment changes: 0"
    )


def test_a_later_plan_with_the_budget_already_in_the_module_is_ok(tmp_path: Path) -> None:
    plan = first_apply_plan()
    del budget_change(plan)["previous_address"]

    assert run_check(plan, tmp_path).startswith(
        f"PLAN OK: one change, {ADDRESS} updated in place (already in the module);"
    )


def test_amounts_aws_writes_as_decimals_are_the_same_amounts(tmp_path: Path) -> None:
    plan = first_apply_plan()
    after = budget_change(plan)["change"]["after"]
    after["limit_amount"] = "100.0"
    for planned in after["notification"]:
        planned["threshold"] = float(planned["threshold"])

    assert run_check(plan, tmp_path).startswith("PLAN OK: ")


# ------------------------------------------------------------------------------------------------
# What stops the apply
# ------------------------------------------------------------------------------------------------


def add_change(address: str, resource_type: str, actions: list[str]) -> Callable[[Plan], None]:
    def mutate(plan: Plan) -> None:
        plan["resource_changes"].append(
            {"address": address, "type": resource_type, "change": {"actions": actions}}
        )

    return mutate


def set_actions(actions: list[str]) -> Callable[[Plan], None]:
    def mutate(plan: Plan) -> None:
        budget_change(plan)["change"]["actions"] = actions

    return mutate


def created_and_old_destroyed(plan: Plan) -> None:
    change = budget_change(plan)
    del change["previous_address"]
    change["change"]["actions"] = ["create"]
    plan["resource_changes"].append(
        {
            "address": "aws_budgets_budget.bedrock_monthly",
            "type": "aws_budgets_budget",
            "change": {"actions": ["delete"]},
        }
    )


def moved_from_elsewhere(plan: Plan) -> None:
    budget_change(plan)["previous_address"] = 'aws_budgets_budget.environment_monthly["prod"]'


def drop_forecast(after: dict[str, Any]) -> None:
    after["notification"] = [n for n in after["notification"] if n["notification_type"] != "FORECASTED"]


def threshold(index: int, value: float) -> Callable[[dict[str, Any]], None]:
    def edit(after: dict[str, Any]) -> None:
        after["notification"][index]["threshold"] = value

    return edit


def as_percentages(after: dict[str, Any]) -> None:
    for planned in after["notification"]:
        planned["threshold_type"] = "PERCENTAGE"


def filter_values(key: str, edit: Callable[[list[str]], list[str]]) -> Callable[[dict[str, Any]], None]:
    def change(after: dict[str, Any]) -> None:
        for cost_filter in after["cost_filter"]:
            if cost_filter["name"] == key:
                cost_filter["values"] = edit(cost_filter["values"])

    return change


def project_tag_back(after: dict[str, Any]) -> None:
    after["cost_filter"].append({"name": "TagKeyValue", "values": ["user:Project$debate-intelligence"]})


def sns_topic(after: dict[str, Any]) -> None:
    after["notification"][0]["subscriber_sns_topic_arns"] = ["arn:aws:sns:us-east-1:111122223333:alerts"]


def nobody(after: dict[str, Any]) -> None:
    for planned in after["notification"]:
        planned["subscriber_email_addresses"] = []


def one_notice_elsewhere(after: dict[str, Any]) -> None:
    after["notification"][0]["subscriber_email_addresses"] = ["someone-else@example.org"]


def set_key(key: str, value: object) -> Callable[[dict[str, Any]], None]:
    def edit(after: dict[str, Any]) -> None:
        after[key] = value

    return edit


REFUSED: Final[dict[str, tuple[Callable[[Plan], None], str]]] = {
    "a permission set changed": (
        add_change("aws_ssoadmin_permission_set.maintainer", "aws_ssoadmin_permission_set", ["update"]),
        "permission set or assignment changes: 1",
    ),
    "an account assignment added": (
        add_change(
            'aws_ssoadmin_account_assignment.maintainer["someone"]',
            "aws_ssoadmin_account_assignment",
            ["create"],
        ),
        'other changes: aws_ssoadmin_account_assignment.maintainer["someone"] create',
    ),
    "another budget changed": (
        add_change('aws_budgets_budget.environment_monthly["prod"]', "aws_budgets_budget", ["update"]),
        "other changes: ",
    ),
    "the budget replaced": (
        set_actions(["delete", "create"]),
        "the budget is delete/create, not updated in place",
    ),
    "the moved block missing": (
        created_and_old_destroyed,
        "other changes: aws_budgets_budget.bedrock_monthly delete",
    ),
    "the budget moved from another budget": (moved_from_elsewhere, "the budget moves from "),
    "the budget renamed": (
        edit_after(set_key("name", "debate-shared-model-monthly")),
        "the budget is named ",
    ),
    "a daily budget": (edit_after(set_key("time_unit", "DAILY")), "not a monthly cost budget"),
    "the old $40 limit": (edit_after(set_key("limit_amount", "40")), "the limit is 40, not 100"),
    "the forecast notice dropped": (edit_after(drop_forecast), "the notices are "),
    "the $80 notice at $90": (edit_after(threshold(1, 90)), "the notices are "),
    "the forecast at $80": (edit_after(threshold(3, 80)), "the notices are "),
    "notices as percentages": (edit_after(as_percentages), "the notices are "),
    "a model service missing": (
        edit_after(filter_values("Service", lambda values: values[:-1])),
        "the filter is ",
    ),
    "a non-model service added": (
        edit_after(filter_values("Service", lambda values: [*values, "Amazon Simple Storage Service"])),
        "the filter is ",
    ),
    "a model usage type missing": (
        edit_after(filter_values("UsageType", lambda values: values[1:])),
        "the filter is ",
    ),
    "Nova Micro's usage type added": (
        edit_after(filter_values("UsageType", lambda values: [*values, "USE1-NovaMicro-input-tokens"])),
        "the filter is ",
    ),
    "the Project tag back in the filter": (edit_after(project_tag_back), "the filter is "),
    "a notice sent to an SNS topic": (edit_after(sns_topic), "a notice goes to an SNS topic"),
    "notices to nobody": (edit_after(nobody), "one non-empty list of addresses"),
    "one notice to someone else": (edit_after(one_notice_elsewhere), "one non-empty list of addresses"),
}


@pytest.mark.parametrize("mutate,reason", REFUSED.values(), ids=list(REFUSED))
def test_a_plan_that_differs_is_not_ok_and_says_why(
    mutate: Callable[[Plan], None], reason: str, tmp_path: Path
) -> None:
    plan = copy.deepcopy(first_apply_plan())
    mutate(plan)

    line = run_check(plan, tmp_path)

    assert line.startswith("PLAN NOT OK: ")
    assert reason in line


def test_a_plan_without_the_budget_is_not_ok(tmp_path: Path) -> None:
    plan = first_apply_plan()
    plan["resource_changes"] = [c for c in plan["resource_changes"] if c["address"] != ADDRESS]

    assert run_check(plan, tmp_path) == (
        "PLAN NOT OK: the budget is changed 0 times, not once | permission set or assignment changes: 0"
    )


def test_the_check_prints_no_address(tmp_path: Path) -> None:
    for mutate, _ in [(lambda plan: None, ""), *REFUSED.values()]:
        plan = copy.deepcopy(first_apply_plan())
        mutate(plan)

        assert "@" not in run_check(plan, tmp_path)
