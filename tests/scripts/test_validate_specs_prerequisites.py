"""`scripts/validate_specs.py` asks every unfinished task to name its prerequisites (v1-e41-t27).

Five unfinished tasks listed no prerequisite until the PM's batch of 2026-11-09, and a session started
one with nothing to check. So the validator refuses a task Goal that is neither Succeeded nor
Cancelled and names no prerequisite, unless a `debate/no-prerequisite` annotation says why. It also
warns, never refuses, when an unfinished task's description names another task id its context does
not list, in three kinds: an unfinished task of the same or an earlier release (most likely a missing
prerequisite), a Succeeded one (a graph link that could be added), and one of a later release (never
a prerequisite).

Every tree here is invented (`spec_graph_tree.py`), and every expected line is written by hand.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from tests.scripts.spec_graph_tree import E01_T01, E01_T02, E02_T01, SpecTree, Task, baseline

VALIDATOR = Path(__file__).resolve().parents[2] / "scripts" / "validate_specs.py"

E01_T02_FILE = "plan_specs/v1/e01-foundation/t02-second-step.yaml"
E01_T03_FILE = "plan_specs/v1/e01-foundation/t03-third-step.yaml"
E02_T01_FILE = "plan_specs/v1/e02-followup/t01-later-step.yaml"
E01_T03 = "v1-e01-t03-third-step"

UNFINISHED = ["Pending", "Ready", "InProgress", "Blocked", "Failed"]


def load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("validate_specs_for_prerequisites", VALIDATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up while the class is built
    spec.loader.exec_module(module)
    return module


validate_specs = load_validator()


def collect(tree: SpecTree, tmp_path: Path):  # noqa: ANN201 - the validator's own SpecTree
    return validate_specs.collect(tree.write(tmp_path / "repo"))


def errors(tree: SpecTree, tmp_path: Path) -> list[str]:
    return collect(tree, tmp_path).errors


def run(tree: SpecTree, tmp_path: Path, capsys: pytest.CaptureFixture[str], *flags: str) -> tuple[int, str]:
    code = validate_specs.main(["--root", str(tree.write(tmp_path / "repo")), *flags])
    return code, capsys.readouterr().out


@pytest.fixture
def tree() -> SpecTree:
    return baseline()


def later_step(tree: SpecTree) -> Task:
    return tree.epic("e02").task("t01")


def refusal(path: str, task: str, phase: str) -> str:
    return (
        f"{path}: task {task} is {phase} and names no prerequisite: list the task that built the code "
        "it changes in spec.context, or say why there is none in a debate/no-prerequisite annotation"
    )


# --------------------------------------------------------------------------------------------
# the refusal
# --------------------------------------------------------------------------------------------


def test_the_baseline_tree_passes_with_no_warning(tree: SpecTree, tmp_path: Path) -> None:
    collected = collect(tree, tmp_path)
    assert (collected.errors, collected.warnings) == ([], [])


@pytest.mark.parametrize("phase", UNFINISHED)
def test_an_unfinished_task_with_no_prerequisite_is_refused(
    tree: SpecTree, tmp_path: Path, phase: str
) -> None:
    later_step(tree).context = []
    later_step(tree).phase = phase
    assert errors(tree, tmp_path) == [refusal(E02_T01_FILE, E02_T01, phase)]


@pytest.mark.parametrize("phase", ["Succeeded", "Cancelled"])
def test_a_succeeded_or_cancelled_task_needs_no_prerequisite(
    tree: SpecTree, tmp_path: Path, phase: str
) -> None:
    later_step(tree).context = []
    later_step(tree).phase = phase
    assert errors(tree, tmp_path) == []


def test_a_task_whose_phase_is_not_one_gets_the_phase_error_alone(tree: SpecTree, tmp_path: Path) -> None:
    later_step(tree).context = []
    later_step(tree).phase = "Done"
    assert errors(tree, tmp_path) == [
        f"{E02_T01_FILE}: status.phase 'Done' not in "
        "['Blocked', 'Cancelled', 'Failed', 'InProgress', 'Pending', 'Ready', 'Succeeded']"
    ]


def test_the_refusal_exits_one_and_prints_the_line(
    tree: SpecTree, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    later_step(tree).context = []
    assert run(tree, tmp_path, capsys) == (1, refusal(E02_T01_FILE, E02_T01, "Pending") + "\n")


def test_a_context_that_names_no_dependency_names_no_prerequisite(tree: SpecTree, tmp_path: Path) -> None:
    later_step(tree).context = []
    root = tree.write(tmp_path / "repo")
    path = root / E02_T01_FILE
    path.write_text(
        path.read_text().replace(
            "  acceptanceCriteria:",
            "  context:\n  - kind: TaskRef\n    name: v1-e01-t01-first-step\n    relation: relatesTo\n"
            "  acceptanceCriteria:",
            1,
        )
    )
    assert validate_specs.collect(root).errors == [refusal(E02_T01_FILE, E02_T01, "Pending")]


# --------------------------------------------------------------------------------------------
# the annotation
# --------------------------------------------------------------------------------------------


def test_an_annotation_with_a_reason_lets_a_task_name_no_prerequisite(tree: SpecTree, tmp_path: Path) -> None:
    later_step(tree).context = []
    later_step(tree).annotations = {"debate/no-prerequisite": "The first task of a new epic."}
    assert errors(tree, tmp_path) == []


@pytest.mark.parametrize("reason", ["", "   ", None, True])
def test_an_annotation_without_a_reason_is_refused(tree: SpecTree, tmp_path: Path, reason: object) -> None:
    later_step(tree).context = []
    later_step(tree).annotations = {"debate/no-prerequisite": reason}
    assert errors(tree, tmp_path) == [
        f"{E02_T01_FILE}: task {E02_T01} is Pending and names no prerequisite, and its "
        "debate/no-prerequisite annotation gives no reason: say why there is none, or list the task "
        "that built the code it changes in spec.context"
    ]


def test_a_task_that_names_its_prerequisites_is_never_refused_over_the_annotation(
    tree: SpecTree, tmp_path: Path
) -> None:
    later_step(tree).annotations = {"debate/no-prerequisite": ""}
    assert errors(tree, tmp_path) == []


# --------------------------------------------------------------------------------------------
# the warnings: a task id named in a description but not in the context
# --------------------------------------------------------------------------------------------


def missing_prerequisite_tree() -> SpecTree:
    """e02-t01 (v1.1) names e01-t02 (v1.0, InProgress), which its context does not list."""
    tree = baseline()
    later_step(tree).description = "Follows from v1-e01-t02's report."
    return tree


def graph_link_tree() -> SpecTree:
    """e02-t01 lists e01-t02 and names e01-t01 (v1.0, Succeeded), which it does not list."""
    tree = baseline()
    later_step(tree).context = [E01_T02]
    later_step(tree).description = "Uses what v1-e01-t01 built."
    return tree


def later_release_tree() -> SpecTree:
    """e01-t02 (v1.0) names e02-t01, which ships in v1.1."""
    tree = baseline()
    tree.epic("e01").task("t02").description = "v1-e02-t01 will build on this."
    return tree


MISSING_PREREQUISITE_LINE = (
    f"{E02_T01_FILE}: {E02_T01} names v1-e01-t02 ({E01_T02}, InProgress in v1.0), which its "
    "spec.context does not list: list it if this task needs its work first"
)
GRAPH_LINK_LINE = (
    f"{E02_T01_FILE}: {E02_T01} names v1-e01-t01 ({E01_T01}, Succeeded in v1.0), which its "
    "spec.context does not list: a graph link that could be added"
)
LATER_RELEASE_LINE = (
    f"{E01_T02_FILE}: {E01_T02} (v1.0) names v1-e02-t01 ({E02_T01}, in v1.1), a later release: "
    "it can never be a prerequisite"
)


def warnings(tree: SpecTree, tmp_path: Path) -> list[tuple[str, str]]:
    collected = collect(tree, tmp_path)
    assert collected.errors == []  # a warning never refuses
    return [(w.kind, w.line) for w in collected.warnings]


def test_an_unfinished_task_named_from_an_earlier_release_is_a_likely_missing_prerequisite(
    tmp_path: Path,
) -> None:
    assert warnings(missing_prerequisite_tree(), tmp_path) == [
        (validate_specs.MISSING_PREREQUISITE, MISSING_PREREQUISITE_LINE)
    ]


def test_an_unfinished_task_named_from_the_same_release_is_a_likely_missing_prerequisite(
    tree: SpecTree, tmp_path: Path
) -> None:
    tree.epic("e01").tasks.append(
        Task("t03", "third-step", context=[E01_T01], description="Waits on v1-e01-t02.")
    )
    assert warnings(tree, tmp_path) == [
        (
            validate_specs.MISSING_PREREQUISITE,
            f"{E01_T03_FILE}: {E01_T03} names v1-e01-t02 ({E01_T02}, InProgress in v1.0), which its "
            "spec.context does not list: list it if this task needs its work first",
        )
    ]


def test_a_cancelled_task_named_from_an_earlier_release_is_never_a_prerequisite(tmp_path: Path) -> None:
    """A Cancelled task is never Succeeded, so listing it would hold the task back (PM, 2026-11-11)."""
    tree = missing_prerequisite_tree()
    tree.epic("e01").task("t02").phase = "Cancelled"
    assert warnings(tree, tmp_path) == [
        (
            validate_specs.NEVER_A_PREREQUISITE,
            f"{E02_T01_FILE}: {E02_T01} names v1-e01-t02 ({E01_T02}, Cancelled in v1.0): "
            "it can never be a prerequisite",
        )
    ]


def test_a_succeeded_task_named_from_an_earlier_release_is_a_graph_link(tmp_path: Path) -> None:
    assert warnings(graph_link_tree(), tmp_path) == [(validate_specs.GRAPH_LINK, GRAPH_LINK_LINE)]


def test_a_task_named_from_a_later_release_is_never_a_prerequisite(tmp_path: Path) -> None:
    assert warnings(later_release_tree(), tmp_path) == [
        (validate_specs.NEVER_A_PREREQUISITE, LATER_RELEASE_LINE)
    ]


def test_a_named_task_is_warned_about_once(tmp_path: Path) -> None:
    tree = missing_prerequisite_tree()
    later_step(tree).description = "Follows from v1-e01-t02's report; v1-e01-t02-second-step said so."
    assert warnings(tree, tmp_path) == [(validate_specs.MISSING_PREREQUISITE, MISSING_PREREQUISITE_LINE)]


@pytest.mark.parametrize(
    "description",
    [
        "Builds on v1-e01-t01.",  # in its context
        "v1-e02-t01 is this task.",  # itself
        "Moved from E01 as v1-e01-t37-an-old-name.",  # an id no task declares
    ],
)
def test_a_listed_task_itself_or_no_task_is_not_warned_about(
    tree: SpecTree, tmp_path: Path, description: str
) -> None:
    later_step(tree).description = description
    assert warnings(tree, tmp_path) == []


@pytest.mark.parametrize("phase", ["Succeeded", "Cancelled"])
def test_a_finished_task_is_not_warned_about(tmp_path: Path, phase: str) -> None:
    tree = missing_prerequisite_tree()
    later_step(tree).phase = phase
    assert warnings(tree, tmp_path) == []


# --------------------------------------------------------------------------------------------
# what the warnings print
# --------------------------------------------------------------------------------------------


def all_three_kinds() -> SpecTree:
    tree = graph_link_tree()
    later_step(tree).description = "Uses what v1-e01-t01 built."
    tree.epic("e01").task("t02").description = "v1-e02-t01 will build on this."
    tree.epic("e01").tasks.append(
        Task("t03", "third-step", context=[E01_T01], description="Waits on v1-e01-t02.")
    )
    return tree


THIRD_STEP_LINE = (
    f"{E01_T03_FILE}: {E01_T03} names v1-e01-t02 ({E01_T02}, InProgress in v1.0), which its "
    "spec.context does not list: list it if this task needs its work first"
)
OK_LINE = "OK: 8 files, 2 epics, 4 tasks, 2 releases"


def test_a_missing_prerequisite_prints_in_full_and_the_other_kinds_as_counts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(all_three_kinds(), tmp_path, capsys) == (
        0,
        "Prerequisite warnings, none refused: 3 task ids named in an unfinished task's description "
        "and not in its spec.context\n"
        "  Most likely a missing prerequisite (an unfinished task of the same or an earlier release): 1\n"
        f"    {THIRD_STEP_LINE}\n"
        "  A graph link that could be added (a Succeeded task of the same or an earlier release): 1, "
        "--all-warnings prints them\n"
        "  Never a prerequisite (a later release, or Cancelled): 1, --all-warnings prints them\n"
        f"{OK_LINE}\n",
    )


def test_all_warnings_prints_every_kind_in_full(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(all_three_kinds(), tmp_path, capsys, "--all-warnings") == (
        0,
        "Prerequisite warnings, none refused: 3 task ids named in an unfinished task's description "
        "and not in its spec.context\n"
        "  Most likely a missing prerequisite (an unfinished task of the same or an earlier release): 1\n"
        f"    {THIRD_STEP_LINE}\n"
        "  A graph link that could be added (a Succeeded task of the same or an earlier release): 1\n"
        f"    {GRAPH_LINK_LINE}\n"
        "  Never a prerequisite (a later release, or Cancelled): 1\n"
        f"    {LATER_RELEASE_LINE}\n"
        f"{OK_LINE}\n",
    )


def test_a_tree_with_no_warning_prints_only_its_ok_line(
    tree: SpecTree, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(tree, tmp_path, capsys, "--all-warnings") == (0, "OK: 7 files, 2 epics, 3 tasks, 2 releases\n")
