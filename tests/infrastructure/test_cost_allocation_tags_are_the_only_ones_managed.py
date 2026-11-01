"""The account's cost allocation tags are managed in one place (`v1-e05-t18`).

`infrastructure/modules/cost_allocation_tags` keeps the `Project` and `Environment` tags Active, and
its Terraform tests hold the two keys and their status. Those tests read only the module's
`aws_ce_cost_allocation_tag.this`, so a second resource block, in the module or in any root, would
manage a third tag without failing them. This test reads the `.tf` files: the one
`aws_ce_cost_allocation_tag` resource under `infrastructure/` is the module's `this`, the module
declares nothing else, and the organization root calls the module once. The module reads no data
source and calls no module either: it needs neither, and the organization root also holds the
permission sets.

The root's two `import` blocks adopted the tags on 2026-10-31 and were then removed
(`v1-e05-t19`): once both tags are in state they do nothing, and in a new account they fail the
whole root's plan until AWS has listed both keys. No `import` block under `infrastructure/` names a
cost allocation tag again.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INFRASTRUCTURE = REPO_ROOT / "infrastructure"
MODULE_DIR = INFRASTRUCTURE / "modules" / "cost_allocation_tags"
ORGANIZATION_DIR = INFRASTRUCTURE / "bootstrap" / "organization"

BLOCK = re.compile(r'^\s*(resource|data|module)\s+"([^"]+)"(?:\s+"([^"]+)")?', re.MULTILINE)
MODULE_SOURCE = re.compile(r'^\s*source\s*=\s*"([^"]+)"', re.MULTILINE)
IMPORT_BLOCK = re.compile(r"^\s*import\s*\{(.*?)^\s*\}", re.MULTILINE | re.DOTALL)
IMPORT_TO = re.compile(r"^\s*to\s*=\s*(.+?)\s*$", re.MULTILINE)


def _tf_files(directory: Path) -> list[Path]:
    return sorted(p for p in directory.rglob("*.tf") if ".terraform" not in p.parts)


def _declarations(directory: Path) -> list[tuple[str, str, str, str]]:
    found = []
    for tf_file in _tf_files(directory):
        text = tf_file.read_text(encoding="utf-8")
        for kind, first, second in BLOCK.findall(text):
            found.append((tf_file.relative_to(REPO_ROOT).as_posix(), kind, first, second))
    return found


def test_the_only_cost_allocation_tag_resource_is_the_module_s() -> None:
    tag_resources = [
        (path, name)
        for path, kind, resource_type, name in _declarations(INFRASTRUCTURE)
        if kind == "resource" and resource_type == "aws_ce_cost_allocation_tag"
    ]

    assert tag_resources == [("infrastructure/modules/cost_allocation_tags/main.tf", "this")]


def test_the_module_declares_the_tag_resource_and_nothing_else() -> None:
    declared = [(kind, first, second) for _, kind, first, second in _declarations(MODULE_DIR)]

    assert declared == [("resource", "aws_ce_cost_allocation_tag", "this")]


def test_the_organization_root_calls_the_module_once() -> None:
    sources = [
        source
        for tf_file in _tf_files(ORGANIZATION_DIR)
        for source in MODULE_SOURCE.findall(tf_file.read_text(encoding="utf-8"))
    ]

    assert sources.count("../../modules/cost_allocation_tags") == 1


def test_no_import_block_adopts_a_cost_allocation_tag() -> None:
    targets = [
        (tf_file.relative_to(REPO_ROOT).as_posix(), target)
        for tf_file in _tf_files(INFRASTRUCTURE)
        for body in IMPORT_BLOCK.findall(tf_file.read_text(encoding="utf-8"))
        for target in IMPORT_TO.findall(body)
    ]

    assert [found for found in targets if "aws_ce_cost_allocation_tag" in found[1]] == []
