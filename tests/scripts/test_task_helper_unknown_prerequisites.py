"""`task_helper.py ready` and `prereqs` refuse a prerequisite they cannot find (v1-e41-t07).

`scripts/task ready` lists the Pending tasks whose prerequisites are all Succeeded, reading only
`spec.context`. Until v1-e41-t07 it skipped a prerequisite no task spec declared, so a misspelt or
deleted prerequisite counted as met and the task was offered to the operator. `prereqs`, which
`scripts/task start` runs, already exited 1 on one, printed as BLOCKED with the phase MISSING; it
now names it as unknown and exits 2, the helper's code for a spec it cannot use.

The helper reads the specs of the directory it runs in, so each test writes a synthetic tree
(`spec_graph_tree.py`) and runs the real script there.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.scripts.spec_graph_tree import E01_T01, E01_T02, E02_T01, SpecTree, baseline

HELPER = Path(__file__).resolve().parents[2] / "scripts" / "task_helper.py"
UNKNOWN = "v1-e01-t09-missing-step"


def run_helper(tree: SpecTree, tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    root = tree.write(tmp_path / "repo")
    return subprocess.run(
        [sys.executable, str(HELPER), *args], cwd=root, capture_output=True, text=True, timeout=60
    )


@pytest.fixture
def tree() -> SpecTree:
    """The baseline with E01's second task Pending, so `ready` has two tasks to offer."""
    tree = baseline()
    tree.epic("e01").task("t02").phase = "Pending"
    return tree


def test_ready_lists_tasks_whose_prerequisites_are_succeeded(tree: SpecTree, tmp_path: Path) -> None:
    result = run_helper(tree, tmp_path, "ready")
    assert (result.returncode, result.stderr) == (0, "")
    assert result.stdout == f"v1.0\t{E01_T02}\tsecond-step\nv1.1\t{E02_T01}\tlater-step\n"


def test_ready_leaves_out_a_task_with_an_unknown_prerequisite_and_says_why(tree: SpecTree, tmp_path: Path) -> None:
    tree.epic("e01").task("t02").context.append(UNKNOWN)
    result = run_helper(tree, tmp_path, "ready")
    assert result.returncode == 0
    assert result.stdout == f"v1.1\t{E02_T01}\tlater-step\n"
    assert result.stderr == (
        f"{E01_T02} is not listed: its spec.context names {UNKNOWN}, which no task spec declares\n"
    )


def test_ready_leaves_out_a_task_whose_only_prerequisite_is_unknown(tree: SpecTree, tmp_path: Path) -> None:
    """With nothing else to check, the old `if p in goals` filter left an empty, always-true `all()`."""
    tree.epic("e01").task("t02").context = [UNKNOWN]
    result = run_helper(tree, tmp_path, "ready")
    assert result.stdout == f"v1.1\t{E02_T01}\tlater-step\n"
    assert UNKNOWN in result.stderr


def test_prereqs_passes_when_every_prerequisite_is_succeeded(tree: SpecTree, tmp_path: Path) -> None:
    result = run_helper(tree, tmp_path, "prereqs", E01_T02)
    assert (result.returncode, result.stdout) == (0, f"  ok      {E01_T01} (Succeeded)\n")


def test_prereqs_exits_one_on_a_prerequisite_not_yet_succeeded(tree: SpecTree, tmp_path: Path) -> None:
    tree.epic("e01").task("t01").phase = "InProgress"
    result = run_helper(tree, tmp_path, "prereqs", E01_T02)
    assert (result.returncode, result.stdout) == (1, f"  BLOCKED {E01_T01} (InProgress)\n")


def test_prereqs_refuses_an_unknown_prerequisite_by_name(tree: SpecTree, tmp_path: Path) -> None:
    tree.epic("e01").task("t02").context.append(UNKNOWN)
    result = run_helper(tree, tmp_path, "prereqs", E01_T02)
    assert result.returncode == 2
    assert result.stdout == f"  ok      {E01_T01} (Succeeded)\n  UNKNOWN {UNKNOWN} (no task spec declares it)\n"
    assert result.stderr == f"{E01_T02}'s spec.context names {UNKNOWN}, which no task spec declares\n"
