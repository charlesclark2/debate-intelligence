"""`scripts/validate_specs.py` refuses a spec whose name, label or graph reference is missing (v1-e41-t09).

Until v1-e41-t09 pyright reported 10 errors in the validator, each a value read from YAML that may
be missing (`None`) and was used as a name. v1-e41-t09 typed them without changing what the
validator accepts. These tests pin what it does when each of those values is missing: the document
or task is still recorded under `None` and the tree is refused, naming `None`. A type fix that
dropped the missing value instead (an `isinstance(..., str)` filter, an early return) would make the
validator accept some of these trees, and fail here. Each test writes a synthetic tree
(`spec_graph_tree.py`), removes one value, and asserts the whole error list, written by hand.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest
import yaml
from tests.scripts.spec_graph_tree import E01_EPIC, E01_T02, RELEASE_V10, SpecTree, baseline, criteria

VALIDATOR = Path(__file__).resolve().parents[2] / "scripts" / "validate_specs.py"
RELEASE_V11 = "plan_specs/releases/v1.1.yaml"
E01_T02_FILE = "plan_specs/v1/e01-foundation/t02-second-step.yaml"


def load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("validate_specs_for_missing_values", VALIDATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up while the class is built
    spec.loader.exec_module(module)
    return module


validate_specs = load_validator()

Documents = list[dict]


def edit(root: Path, relative: str, change: Callable[[Documents], None]) -> None:
    path = root / relative
    documents = list(yaml.safe_load_all(path.read_text()))
    change(documents)
    path.write_text(yaml.safe_dump_all(documents, sort_keys=False, explicit_start=True))


def errors(root: Path) -> list[str]:
    return validate_specs.collect(root).errors


@pytest.fixture
def root(tmp_path: Path) -> Path:
    tree: SpecTree = baseline()
    return tree.write(tmp_path / "repo")


def test_the_baseline_is_clean(root: Path) -> None:
    assert errors(root) == []


def test_two_documents_without_a_name_are_also_reported_as_duplicates(root: Path) -> None:
    def drop_gate_name(documents: Documents) -> None:
        del documents[1]["metadata"]["name"]

    edit(root, RELEASE_V10, drop_gate_name)
    edit(root, RELEASE_V11, drop_gate_name)

    assert errors(root) == [
        f"{RELEASE_V10}: metadata.name is required",
        f"{RELEASE_V11}: metadata.name is required",
        f"{RELEASE_V11}: duplicate metadata.name None (also in {RELEASE_V10})",
    ]


def test_a_task_without_a_release_label_is_refused_and_still_recorded(root: Path) -> None:
    def drop_release_label(documents: Documents) -> None:
        for document in documents:
            del document["metadata"]["labels"]["debate/release"]

    edit(root, E01_T02_FILE, drop_release_label)

    assert errors(root) == [
        f"{E01_T02_FILE}: debate/release None has no file in plan_specs/releases/",
        f"{E01_T02_FILE}: task release None differs from epic release v1.0",
    ]


def test_a_task_without_an_epic_label_is_refused_and_still_recorded(root: Path) -> None:
    def drop_epic_label(documents: Documents) -> None:
        for document in documents:
            del document["metadata"]["labels"]["debate/epic"]

    edit(root, E01_T02_FILE, drop_epic_label)

    assert errors(root) == [
        f"{E01_EPIC}: epic Plan lists {E01_T02} but no task file declares it",
        "plan_specs: tasks reference unknown epic None",
    ]


def test_a_release_node_that_names_no_epic_is_refused(root: Path) -> None:
    def add_unnamed_node(documents: Documents) -> None:
        documents[2]["spec"]["graph"]["nodes"].append({"id": "epic-unnamed", "kind": "External", "name": "?"})

    edit(root, RELEASE_V10, add_unnamed_node)

    assert errors(root) == [f"{RELEASE_V10}: unknown epic None"]


def unnamed_task_node(node_id: str) -> dict:
    return {
        "id": node_id,
        "kind": "Task",
        "name": "unnamed",
        "dependsOn": [],
        "acceptanceCriteria": criteria("it"),
    }


def test_an_epic_task_node_that_names_no_task_is_refused(root: Path) -> None:
    def add_unnamed_node(documents: Documents) -> None:
        documents[1]["spec"]["graph"]["nodes"].append(unnamed_task_node("t09"))

    edit(root, E01_EPIC, add_unnamed_node)

    assert errors(root) == [f"{E01_EPIC}: epic Plan lists None but no task file declares it"]


def test_epic_task_nodes_naming_no_task_and_an_undeclared_task_are_each_refused(root: Path) -> None:
    """Until v1-e41-t09 sorting `None` with a task name raised TypeError instead of reporting both."""
    undeclared = "v1-e01-t08-undeclared-step"

    def add_nodes(documents: Documents) -> None:
        nodes = documents[1]["spec"]["graph"]["nodes"]
        nodes.append(unnamed_task_node("t09"))
        nodes.append({**unnamed_task_node("t08"), "inputs": {"goalRef": undeclared}})

    edit(root, E01_EPIC, add_nodes)

    assert errors(root) == [
        f"{E01_EPIC}: epic Plan lists None but no task file declares it",
        f"{E01_EPIC}: epic Plan lists {undeclared} but no task file declares it",
    ]
