"""`scripts/validate_specs.py` holds each epic's graph to its tasks' prerequisites (v1-e41-t07).

The PM's dependency audit of 2026-11-01 found 38 places where an epic's graph and its tasks'
`spec.context` disagreed, an External node in an epic graph naming a task from a later release (the
validator refused that in a context, never in a graph), and an epic marked Succeeded with tasks
still open. `scripts/task ready` reads only `spec.context`, so a graph that drifts from it misleads
whoever reads the graph. Each test writes a synthetic tree (`spec_graph_tree.py`) with one thing
wrong and asserts the whole error list, written by hand: one refusal, naming the file, the node and
the task.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from tests.scripts.spec_graph_tree import (
    E01_EPIC,
    E01_T01,
    E01_T02,
    E02_EPIC,
    E02_T01,
    RELEASE_V10,
    Epic,
    SpecTree,
    Task,
    baseline,
)

VALIDATOR = Path(__file__).resolve().parents[2] / "scripts" / "validate_specs.py"


def load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("validate_specs_for_epic_graphs", VALIDATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up while the class is built
    spec.loader.exec_module(module)
    return module


validate_specs = load_validator()


def errors(tree: SpecTree, tmp_path: Path) -> list[str]:
    return validate_specs.collect(tree.write(tmp_path / "repo")).errors


@pytest.fixture
def tree() -> SpecTree:
    return baseline()


# --------------------------------------------------------------------------------------------
# the clean trees
# --------------------------------------------------------------------------------------------


def test_the_baseline_tree_passes(tree: SpecTree, tmp_path: Path) -> None:
    assert errors(tree, tmp_path) == []


def test_an_epic_whose_tasks_are_succeeded_or_cancelled_may_be_succeeded(tree: SpecTree, tmp_path: Path) -> None:
    tree.epic("e01").phase = "Succeeded"
    tree.epic("e01").task("t02").phase = "Cancelled"
    assert errors(tree, tmp_path) == []


def test_a_release_whose_epics_are_succeeded_may_be_succeeded(tree: SpecTree, tmp_path: Path) -> None:
    tree.releases["v1.0"] = "Succeeded"
    tree.epic("e01").phase = "Succeeded"
    tree.epic("e01").task("t02").phase = "Succeeded"
    assert errors(tree, tmp_path) == []


def test_an_external_node_from_an_earlier_release_passes(tree: SpecTree, tmp_path: Path) -> None:
    """The baseline's E02 (v1.1) already depends on E01 (v1.0); an unused one is no error either."""
    tree.epic("e02").externals.append(E01_T02)
    assert errors(tree, tmp_path) == []


def test_an_external_node_from_the_same_release_passes(tree: SpecTree, tmp_path: Path) -> None:
    tree.epics.append(Epic("e03", "sibling", "v1.1", [Task("t01", "sibling-step", context=[E02_T01])]))
    assert errors(tree, tmp_path) == []


# --------------------------------------------------------------------------------------------
# graph and context name the same prerequisites
# --------------------------------------------------------------------------------------------


def test_a_same_epic_edge_missing_from_the_context_is_refused(tree: SpecTree, tmp_path: Path) -> None:
    second = tree.epic("e01").task("t02")
    second.graph, second.context = [E01_T01], []
    assert errors(tree, tmp_path) == [
        f"{E01_EPIC}: node t02 ({E01_T02}) depends on node t01 ({E01_T01}), "
        f"which {E01_T02}'s spec.context does not list"
    ]


def test_a_cross_epic_edge_missing_from_the_context_is_refused(tree: SpecTree, tmp_path: Path) -> None:
    later = tree.epic("e02").task("t01")
    later.graph, later.context = [E01_T01], []
    assert errors(tree, tmp_path) == [
        f"{E02_EPIC}: node t01 ({E02_T01}) depends on node ext-{E01_T01} ({E01_T01}), "
        f"which {E02_T01}'s spec.context does not list"
    ]


def test_a_same_epic_prerequisite_missing_from_the_graph_is_refused(tree: SpecTree, tmp_path: Path) -> None:
    tree.epic("e01").task("t02").graph = []
    assert errors(tree, tmp_path) == [
        f"{E01_EPIC}: node t02 ({E01_T02}) does not depend on {E01_T01}, "
        "which its spec.context lists: depend on node t01"
    ]


def test_a_cross_epic_prerequisite_missing_from_the_graph_is_refused(tree: SpecTree, tmp_path: Path) -> None:
    tree.epic("e02").task("t01").graph = []
    assert errors(tree, tmp_path) == [
        f"{E02_EPIC}: node t01 ({E02_T01}) does not depend on {E01_T01}, "
        "which its spec.context lists: depend on an External node for it"
    ]


def test_a_prerequisite_whose_external_node_is_there_but_unused_is_refused(tree: SpecTree, tmp_path: Path) -> None:
    epic = tree.epic("e02")
    epic.task("t01").graph = []
    epic.externals.append(E01_T01)
    assert errors(tree, tmp_path) == [
        f"{E02_EPIC}: node t01 ({E02_T01}) does not depend on {E01_T01}, "
        f"which its spec.context lists: depend on node ext-{E01_T01}"
    ]


def test_a_same_epic_prerequisite_reached_through_an_external_node_is_refused(
    tree: SpecTree, tmp_path: Path
) -> None:
    """The edge and the context agree; the External node itself is the error."""
    tree.epic("e01").externals.append(E01_T01)
    tree.epic("e01").task("t02").depends_on = [f"ext-{E01_T01}"]
    assert errors(tree, tmp_path) == [
        f"{E01_EPIC}: External node ext-{E01_T01} names {E01_T01}, a task of this epic: "
        "depend on its Task node instead"
    ]


def test_an_external_node_naming_no_task_is_refused(tree: SpecTree, tmp_path: Path) -> None:
    tree.epic("e02").externals.append("v1-e09-t01-nowhere")
    assert errors(tree, tmp_path) == [
        f"{E02_EPIC}: External node ext-v1-e09-t01-nowhere names 'v1-e09-t01-nowhere', which is not a task"
    ]


# --------------------------------------------------------------------------------------------
# an External node ships no later than its epic
# --------------------------------------------------------------------------------------------


def test_an_unused_external_node_from_a_later_release_is_refused(tree: SpecTree, tmp_path: Path) -> None:
    tree.epic("e01").externals.append(E02_T01)
    assert errors(tree, tmp_path) == [
        f"{E01_EPIC}: External node ext-{E02_T01} names {E02_T01}, "
        "which ships in a later release (v1.1) than this epic (v1.0)"
    ]


def test_an_edge_to_a_later_release_is_refused_in_the_graph_as_in_the_context(
    tree: SpecTree, tmp_path: Path
) -> None:
    """The audit's case: graph and context agree, and both name a later release's task."""
    tree.epic("e01").task("t02").context.append(E02_T01)
    found = errors(tree, tmp_path)
    assert (
        f"{E01_EPIC}: External node ext-{E02_T01} names {E02_T01}, "
        "which ships in a later release (v1.1) than this epic (v1.0)"
    ) in found
    assert (
        f"plan_specs/v1/e01-foundation/t02-second-step.yaml: prerequisite {E02_T01} ships in a later release (v1.1)"
    ) in found


# --------------------------------------------------------------------------------------------
# a Succeeded epic or release has nothing open under it
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("open_phase", ["Pending", "Ready", "InProgress", "Blocked", "Failed"])
def test_a_succeeded_epic_with_an_open_task_is_refused(tree: SpecTree, tmp_path: Path, open_phase: str) -> None:
    tree.epic("e01").phase = "Succeeded"
    tree.epic("e01").task("t02").phase = open_phase
    assert errors(tree, tmp_path) == [
        f"{E01_EPIC}: epic Goal v1-e01-foundation is Succeeded but its task {E01_T02} is {open_phase}"
    ]


def test_a_succeeded_epic_names_every_open_task(tree: SpecTree, tmp_path: Path) -> None:
    tree.epic("e01").phase = "Succeeded"
    tree.epic("e01").task("t01").phase = "Ready"
    assert errors(tree, tmp_path) == [
        f"{E01_EPIC}: epic Goal v1-e01-foundation is Succeeded but its task {E01_T01} is Ready",
        f"{E01_EPIC}: epic Goal v1-e01-foundation is Succeeded but its task {E01_T02} is InProgress",
    ]


def test_a_succeeded_release_with_an_open_epic_is_refused(tree: SpecTree, tmp_path: Path) -> None:
    tree.releases["v1.0"] = "Succeeded"
    assert errors(tree, tmp_path) == [
        f"{RELEASE_V10}: release Goal release-v1-0 is Succeeded but its epic v1-e01-foundation is Pending"
    ]


# --------------------------------------------------------------------------------------------
# the command line
# --------------------------------------------------------------------------------------------


def test_the_command_exits_one_and_prints_a_graph_refusal(
    tree: SpecTree, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tree.epic("e01").task("t02").graph = []
    root = tree.write(tmp_path / "repo")
    assert validate_specs.main(["--root", str(root)]) == 1
    out = capsys.readouterr().out
    assert f"{E01_EPIC}: node t02 ({E01_T02}) does not depend on {E01_T01}" in out
