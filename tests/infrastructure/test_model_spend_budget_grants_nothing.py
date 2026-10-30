"""The model spend budget module creates a budget and nothing else (`v1-e05-t16` ac2).

`infrastructure/modules/model_spend_budget` is called from `bootstrap/organization`, the root that
also holds the account's permission sets and their assignments. The task's spec forbids a
permission set or account assignment changed, and its Terraform tests cannot list what a module
declares, so this test reads the module's `.tf` files: every resource is an `aws_budgets_budget`,
and there is no module call, through which a grant could arrive without a resource here. Data
sources are refused too: the budget needs none, so one would be a new read of the account.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_DIR = REPO_ROOT / "infrastructure" / "modules" / "model_spend_budget"

BLOCK = re.compile(r'^\s*(resource|data|module)\s+"([^"]+)"', re.MULTILINE)


def _declarations() -> list[tuple[str, str, str]]:
    found = []
    for tf_file in sorted(MODULE_DIR.glob("*.tf")):
        for kind, label in BLOCK.findall(tf_file.read_text(encoding="utf-8")):
            found.append((tf_file.name, kind, label))
    return found


def test_the_module_declares_one_budget_and_no_other_resource() -> None:
    resources = [(name, label) for name, kind, label in _declarations() if kind == "resource"]

    assert resources == [("main.tf", "aws_budgets_budget")]


def test_the_module_calls_no_module_and_reads_no_data_source() -> None:
    others = [(name, kind, label) for name, kind, label in _declarations() if kind != "resource"]

    assert others == []
