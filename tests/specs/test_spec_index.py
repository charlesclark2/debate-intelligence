"""`scripts/spec_index.py`: the ROADMAP.md generator.

The expectation is `fixtures/minimal_valid/ROADMAP.md`, whose generated section was written by hand
from the spec files beside it. Comparing the renderer with that file is a real check; comparing it
with its own previous output would only prove it is consistent.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import spec_index
from spec_tree import REPO_ROOT, ROADMAP, TASK_T01, Tree, copy_fixture, write_release

Capture = pytest.CaptureFixture[str]

BEGIN, END = spec_index.BEGIN, spec_index.END


@pytest.fixture
def tree(tmp_path: Path) -> Tree:
    return copy_fixture(tmp_path)


def generated_section(text: str) -> str:
    """Just the marked block, markers included."""
    return text[text.index(BEGIN) : text.index(END) + len(END)]


# --------------------------------------------------------------------------------------------
# the rendered tables
# --------------------------------------------------------------------------------------------


def test_render_matches_the_hand_written_expectation(tree: Tree) -> None:
    assert spec_index.render(tree.path) == generated_section(tree.read(ROADMAP))


def test_check_passes_on_the_committed_fixture_roadmap(tree: Tree, capsys: Capture) -> None:
    assert spec_index.main(["--check", "--root", str(tree.path)]) == 0
    assert capsys.readouterr().out == "ROADMAP.md is up to date\n"


def test_the_release_summary_counts_epics_tasks_and_finished_tasks(tree: Tree) -> None:
    rendered = spec_index.render(tree.path).splitlines()
    assert "| [v1.0](plan_specs/releases/v1.0.yaml) | Minimal foundation | 1 | 2 | 1 | 4 |" in rendered
    assert "| [v1.1](plan_specs/releases/v1.1.yaml) | Minimal follow-up | 1 | 1 | 0 | 6 |" in rendered


def test_a_task_row_carries_its_title_name_phase_and_prerequisite_count(tree: Tree) -> None:
    row = (
        "| [Second step](plan_specs/v1/e01-minimal-foundation/t02-second-step.yaml) "
        "`v1-e01-t02-second-step` | InProgress | 1 | 2.0 |"
    )
    assert row in spec_index.render(tree.path).splitlines()


def test_a_new_release_file_adds_a_summary_row_in_version_order(tree: Tree) -> None:
    write_release(tree, "v1.2", "v1-e01-minimal-foundation")
    rendered = spec_index.render(tree.path).splitlines()
    new_row = "| [v1.2](plan_specs/releases/v1.2.yaml) | Added by a test | 0 | 0 | 0 | 0 |"
    previous = "| [v1.1](plan_specs/releases/v1.1.yaml) | Minimal follow-up | 1 | 1 | 0 | 6 |"
    assert new_row in rendered
    assert rendered.index(new_row) == rendered.index(previous) + 1


@pytest.mark.parametrize(
    ("effort", "expected"),
    [("30m", 0.5), ("2h", 2.0), ("1.5h", 1.5), ("1d", 6.0), (None, 0.0), ("a while", 0.0)],
)
def test_effort_estimates_convert_to_hours(effort: str | None, expected: float) -> None:
    assert spec_index.hours(effort) == expected


# --------------------------------------------------------------------------------------------
# rewriting ROADMAP.md
# --------------------------------------------------------------------------------------------


def test_regenerating_twice_produces_no_second_diff(tree: Tree, capsys: Capture) -> None:
    tree.edit(TASK_T01, "  phase: Succeeded", "  phase: Pending")
    assert spec_index.main(["--root", str(tree.path)]) == 0
    assert capsys.readouterr().out == "ROADMAP.md updated\n"
    after_first = tree.read(ROADMAP)

    assert spec_index.main(["--root", str(tree.path)]) == 0
    assert capsys.readouterr().out == "ROADMAP.md is already up to date\n"
    assert tree.read(ROADMAP) == after_first
    assert spec_index.main(["--check", "--root", str(tree.path)]) == 0


def test_regenerating_keeps_the_hand_written_sections(tree: Tree) -> None:
    before = tree.read(ROADMAP)
    tree.write(ROADMAP, before.replace(f"{BEGIN}\n", f"{BEGIN}\nstale junk\n"))
    assert spec_index.main(["--root", str(tree.path)]) == 0
    after = tree.read(ROADMAP)
    assert after == before
    assert "# Roadmap — the minimal fixture tree" in after
    assert "This section is below the END marker and has to survive a regeneration untouched." in after


def test_a_changed_phase_makes_the_roadmap_stale(tree: Tree, capsys: Capture) -> None:
    tree.edit(TASK_T01, "  phase: Succeeded", "  phase: Blocked")
    assert spec_index.main(["--check", "--root", str(tree.path)]) == 1
    assert "ROADMAP.md is stale" in capsys.readouterr().err


def test_a_new_task_file_makes_the_roadmap_stale(tree: Tree) -> None:
    original = tree.read(TASK_T01)
    third = original.replace("t01-first-step", "t03-third-step").replace("First step", "Third step")
    tree.write("plan_specs/v1/e01-minimal-foundation/t03-third-step.yaml", third)
    assert spec_index.main(["--check", "--root", str(tree.path)]) == 1
    assert "`v1-e01-t03-third-step`" in spec_index.render(tree.path)


def test_a_new_release_file_makes_the_roadmap_stale(tree: Tree) -> None:
    write_release(tree, "v1.2", "v1-e01-minimal-foundation")
    assert spec_index.main(["--check", "--root", str(tree.path)]) == 1


def test_check_does_not_write(tree: Tree) -> None:
    tree.edit(TASK_T01, "  phase: Succeeded", "  phase: Blocked")
    before = tree.read(ROADMAP)
    assert spec_index.main(["--check", "--root", str(tree.path)]) == 1
    assert tree.read(ROADMAP) == before


# --------------------------------------------------------------------------------------------
# a ROADMAP.md that cannot be regenerated
# --------------------------------------------------------------------------------------------


def test_a_missing_roadmap_is_reported(tree: Tree, capsys: Capture) -> None:
    (tree.path / ROADMAP).unlink()
    assert spec_index.main(["--root", str(tree.path)]) == 2
    assert "does not exist" in capsys.readouterr().err


@pytest.mark.parametrize("marker", [BEGIN, END])
def test_a_missing_marker_is_reported_rather_than_appended_to(
    tree: Tree, capsys: Capture, marker: str
) -> None:
    tree.edit(ROADMAP, marker, "")
    assert spec_index.main(["--root", str(tree.path)]) == 2
    assert f"ROADMAP.md has no {marker} marker" in capsys.readouterr().err


# --------------------------------------------------------------------------------------------
# the real repository
# --------------------------------------------------------------------------------------------


def test_the_repository_roadmap_renders_deterministically() -> None:
    assert spec_index.render(REPO_ROOT) == spec_index.render(REPO_ROOT)


def test_the_repository_roadmap_keeps_its_generated_markers() -> None:
    text = (REPO_ROOT / "ROADMAP.md").read_text()
    assert text.count(BEGIN) == 1
    assert text.count(END) == 1


def test_every_repository_release_and_epic_appears_in_the_rendered_roadmap() -> None:
    rendered = spec_index.render(REPO_ROOT)
    for version in spec_index.release_order(REPO_ROOT / "plan_specs"):
        assert f"[{version}](plan_specs/releases/{version}.yaml)" in rendered
    for epic_file in sorted((REPO_ROOT / "plan_specs").glob("v*/e*/epic.yaml")):
        assert f"]({epic_file.relative_to(REPO_ROOT).as_posix()})" in rendered
