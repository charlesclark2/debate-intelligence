"""`scripts/validate_specs.py`, rule by rule.

Every test starts from the minimal valid spec tree in `fixtures/minimal_valid/`, copies it to a
temporary directory, breaks exactly one thing, and asserts the error message the validator is
expected to produce. The expected messages are written by hand here, not copied out of a run, so a
message that changes has to be changed here too — which is the point: these strings are what a
contributor reads when a spec is wrong.

Errors are asserted with `in`, not by comparing the whole list, because breaking one rule often
trips a second one (renaming a task, for instance, also orphans the epic Plan node that named it).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import validate_specs
from spec_tree import (
    EPIC_E01,
    RELEASE_V10,
    RELEASE_V11,
    REPO_ROOT,
    TASK_LATER,
    TASK_T01,
    TASK_T02,
    Tree,
    copy_fixture,
    write_release,
)

ALL_PHASES = "['Blocked', 'Cancelled', 'Failed', 'InProgress', 'Pending', 'Ready', 'Succeeded']"
ALL_NODE_KINDS = "['External', 'Gate', 'Group', 'Task']"

Capture = pytest.CaptureFixture[str]


def errors(tree: Tree) -> list[str]:
    return validate_specs.collect(tree.path).errors


@pytest.fixture
def tree(tmp_path: Path) -> Tree:
    return copy_fixture(tmp_path)


# --------------------------------------------------------------------------------------------
# the passing baseline
# --------------------------------------------------------------------------------------------


def test_minimal_fixture_tree_is_valid(tree: Tree) -> None:
    assert errors(tree) == []


def test_minimal_fixture_tree_is_read_completely(tree: Tree) -> None:
    collected = validate_specs.collect(tree.path)
    assert sorted(collected.epics) == ["v1-e01-minimal-foundation", "v1-e02-minimal-followup"]
    assert sorted(collected.task_release) == [
        "v1-e01-t01-first-step",
        "v1-e01-t02-second-step",
        "v1-e02-t01-later-step",
    ]
    assert len(collected.files) == 7


def test_the_repository_spec_tree_is_valid() -> None:
    assert validate_specs.collect(REPO_ROOT).errors == []


# --------------------------------------------------------------------------------------------
# document shape
# --------------------------------------------------------------------------------------------


def test_api_version_must_be_the_planspec_alpha_version(tree: Tree) -> None:
    tree.edit(TASK_T01, "apiVersion: planspec.io/v1alpha1", "apiVersion: planspec.io/v1beta1")
    assert f"{TASK_T01}: apiVersion must be planspec.io/v1alpha1" in errors(tree)


def test_document_kind_must_be_known(tree: Tree) -> None:
    tree.edit(TASK_T01, "kind: Goal", "kind: Wish")
    assert f"{TASK_T01}: unknown kind 'Wish'" in errors(tree)


def test_metadata_name_is_required(tree: Tree) -> None:
    tree.edit(TASK_T01, "  name: v1-e01-t01-first-step\n", "")
    assert f"{TASK_T01}: metadata.name is required" in errors(tree)


def test_unparseable_yaml_is_reported_rather_than_raised(tree: Tree) -> None:
    tree.write(TASK_T01, "kind: [unclosed\n")
    prefix = f"{TASK_T01}: YAML parse error:"
    assert any(e.startswith(prefix) for e in errors(tree))


def test_metadata_names_are_unique_across_the_tree(tree: Tree) -> None:
    tree.edit(TASK_T02, "  name: v1-e01-t02-second-step\n", "  name: v1-e01-t01-first-step\n")
    expected = f"duplicate metadata.name 'v1-e01-t01-first-step' (also in {TASK_T01})"
    assert f"{TASK_T02}: {expected}" in errors(tree)


def test_goal_phase_must_be_in_the_lifecycle(tree: Tree) -> None:
    tree.edit(TASK_T01, "  phase: Succeeded", "  phase: Done")
    assert f"{TASK_T01}: status.phase 'Done' not in {ALL_PHASES}" in errors(tree)


def test_goal_needs_acceptance_criteria(tree: Tree) -> None:
    tree.drop_lines(TASK_T01, "  acceptanceCriteria:", "status:\n  phase: Succeeded")
    assert f"{TASK_T01}: Goal needs spec.acceptanceCriteria" in errors(tree)


def test_epic_and_task_files_hold_one_goal_and_one_plan(tree: Tree) -> None:
    tree.drop_document(TASK_T01, "Plan")
    assert f"{TASK_T01}: epic/task files need exactly one Goal and one Plan" in errors(tree)


def test_release_files_hold_one_goal_one_gate_and_one_plan(tree: Tree) -> None:
    tree.drop_document(RELEASE_V10, "Gate")
    assert f"{RELEASE_V10}: release files need exactly one Goal, one Gate and one Plan" in errors(tree)


def test_release_file_name_must_be_a_version(tree: Tree) -> None:
    shutil.copy(tree.path / RELEASE_V10, tree.path / "plan_specs/releases/next.yaml")
    assert "plan_specs/releases/next.yaml: release file name must be vMAJOR.MINOR.yaml" in errors(tree)


# --------------------------------------------------------------------------------------------
# labels and names
# --------------------------------------------------------------------------------------------


def test_major_version_label_must_match_the_folder(tree: Tree) -> None:
    tree.edit(TASK_T01, "debate/major-version: v1", "debate/major-version: v2", count=0)
    assert f"{TASK_T01}: debate/major-version label must be 'v1' (folder)" in errors(tree)


def test_every_document_in_a_file_carries_identical_labels(tree: Tree) -> None:
    tree.edit(
        TASK_T01,
        "    debate/epic: v1-e01-minimal-foundation\nspec:\n  description: >-\n    One node.",
        "    debate/epic: v1-e01-other-epic\nspec:\n  description: >-\n    One node.",
    )
    assert f"{TASK_T01}: every document in a file must carry identical labels" in errors(tree)


def test_release_label_must_have_a_release_file(tree: Tree) -> None:
    tree.edit(TASK_T01, "debate/release: v1.0", "debate/release: v1.9", count=0)
    assert f"{TASK_T01}: debate/release 'v1.9' has no file in plan_specs/releases/" in errors(tree)


def test_release_label_must_belong_to_the_major_version(tree: Tree) -> None:
    write_release(tree, "v2.0", "v1-e01-minimal-foundation")
    tree.edit(TASK_T01, "debate/release: v1.0", "debate/release: v2.0", count=0)
    assert f"{TASK_T01}: debate/release 'v2.0' must be a v1 release" in errors(tree)


def test_task_name_must_match_its_epic_folder_and_file(tree: Tree) -> None:
    tree.edit(TASK_T01, "name: v1-e01-t01-first-step", "name: v1-e01-t09-first-step", count=0)
    assert f"{TASK_T01}: task name 'v1-e01-t09-first-step' must start with 'v1-e01-t01-'" in errors(tree)


def test_release_label_must_equal_the_release_file_name(tree: Tree) -> None:
    label = "    debate/release: {}\n  annotations:"
    tree.edit(RELEASE_V11, label.format("v1.1"), label.format("v1.9"))
    assert f"{RELEASE_V11}: debate/release label must equal the file name" in errors(tree)


# --------------------------------------------------------------------------------------------
# Plan graphs
# --------------------------------------------------------------------------------------------


def test_plan_graph_needs_nodes(tree: Tree) -> None:
    tree.drop_lines(TASK_T01, "    nodes:", "status:\n  phase: Succeeded")
    tree.edit(TASK_T01, "  graph:\nstatus:", "  graph:\n    nodes: []\nstatus:")
    assert f"{TASK_T01}: Plan graph has no nodes" in errors(tree)


def test_plan_graph_node_ids_are_unique(tree: Tree) -> None:
    tree.edit(TASK_T02, "    - id: test-the-code", "    - id: write-the-code")
    assert f"{TASK_T02}: duplicate node ids: ['write-the-code']" in errors(tree)


def test_plan_graph_node_kind_must_be_known(tree: Tree) -> None:
    tree.edit(TASK_T01, "      kind: Task", "      kind: Chore")
    assert f"{TASK_T01}: node do-the-thing: kind must be one of {ALL_NODE_KINDS}" in errors(tree)


def test_plan_graph_depends_on_must_resolve(tree: Tree) -> None:
    tree.edit(TASK_T02, "      - write-the-code", "      - wash-the-dishes")
    assert f"{TASK_T02}: node test-the-code: dependsOn 'wash-the-dishes' does not resolve" in errors(tree)


def test_plan_graph_must_be_acyclic(tree: Tree) -> None:
    tree.edit(
        TASK_T02,
        "      estimatedEffort: 30m",
        "      dependsOn:\n      - test-the-code\n      estimatedEffort: 30m",
    )
    assert f"{TASK_T02}: Plan graph contains a cycle" in errors(tree)


def test_plan_goal_ref_must_name_a_goal_in_the_same_file(tree: Tree) -> None:
    tree.edit(TASK_T01, "  goalRef:\n    name: v1-e01-t01-first-step", "  goalRef:\n    name: release-v1-0")
    assert f"{TASK_T01}: Plan goalRef 'release-v1-0' does not match a Goal in the same file" in errors(tree)


def test_gate_nodes_need_a_gate_ref(tree: Tree) -> None:
    tree.edit(RELEASE_V10, "      gateRef:\n        name: release-v1-0-gate\n", "")
    assert f"{RELEASE_V10}: node gate: Gate nodes need gateRef.name" in errors(tree)


# --------------------------------------------------------------------------------------------
# typed acceptance criteria
# --------------------------------------------------------------------------------------------


def test_task_nodes_need_acceptance_criteria(tree: Tree) -> None:
    tree.drop_lines(TASK_T01, "      acceptanceCriteria:", "status:\n  phase: Succeeded")
    assert f"{TASK_T01}: node do-the-thing: Task nodes need acceptanceCriteria" in errors(tree)


def test_criteria_type_must_be_known(tree: Tree) -> None:
    tree.edit(TASK_T01, "      - type: command_succeeds", "      - type: vibes_good")
    assert f"{TASK_T01}: node do-the-thing: unknown criteria type 'vibes_good'" in errors(tree)


@pytest.mark.parametrize(
    ("path", "node", "line", "ctype", "missing"),
    [
        (TASK_T01, "do-the-thing", "        command: 'true'\n", "command_succeeds", "command"),
        (TASK_T02, "write-the-code", "        path: README.md\n", "artifact_exists", "path"),
        (TASK_T02, "test-the-code", "        command: 'true'\n", "test_passes", "command"),
        (
            TASK_LATER,
            "do-the-later-thing",
            "        url: http://localhost:8000/health\n",
            "endpoint_responds",
            "url",
        ),
    ],
)
def test_criteria_need_the_fields_their_type_requires(
    tree: Tree, path: str, node: str, line: str, ctype: str, missing: str
) -> None:
    tree.edit(path, line, "")
    assert f"{path}: node {node}: {ctype} criteria missing ['{missing}']" in errors(tree)


def test_criteria_need_a_name(tree: Tree) -> None:
    tree.edit(TASK_T01, "        name: The thing succeeds\n", "")
    assert f"{TASK_T01}: node do-the-thing: command_succeeds criteria missing ['name']" in errors(tree)


# --------------------------------------------------------------------------------------------
# epics
# --------------------------------------------------------------------------------------------


def test_an_epic_needs_task_files(tree: Tree) -> None:
    (tree.path / TASK_T01).unlink()
    (tree.path / TASK_T02).unlink()
    assert f"{EPIC_E01}: epic has no task files" in errors(tree)


def test_a_task_ships_in_its_epics_release(tree: Tree) -> None:
    tree.edit(TASK_T01, "debate/release: v1.0", "debate/release: v1.1", count=0)
    assert f"{TASK_T01}: task release v1.1 differs from epic release v1.0" in errors(tree)


def test_a_task_file_lives_in_its_epics_folder(tree: Tree) -> None:
    moved = "plan_specs/v1/e02-minimal-followup/t01-first-step.yaml"
    shutil.move(tree.path / TASK_T01, tree.path / moved)
    assert f"{moved}: task file must live in its epic's folder" in errors(tree)


def test_an_epic_plan_lists_every_task_in_its_folder(tree: Tree) -> None:
    tree.drop_lines(
        EPIC_E01,
        "    - id: t02",
        "status:\n  phase: Pending",
    )
    assert f"{EPIC_E01}: epic Plan does not list task v1-e01-t02-second-step" in errors(tree)


def test_an_epic_plan_lists_no_task_without_a_file(tree: Tree) -> None:
    tree.edit(EPIC_E01, "goalRef: v1-e01-t02-second-step", "goalRef: v1-e01-t03-ghost-step", count=0)
    assert f"{EPIC_E01}: epic Plan lists v1-e01-t03-ghost-step but no task file declares it" in errors(tree)


def test_a_task_epic_label_must_name_a_real_epic(tree: Tree) -> None:
    tree.edit(TASK_T01, "debate/epic: v1-e01-minimal-foundation", "debate/epic: v1-e01-ghost-epic", count=0)
    assert "plan_specs: tasks reference unknown epic 'v1-e01-ghost-epic'" in errors(tree)


# --------------------------------------------------------------------------------------------
# cross-task prerequisites
# --------------------------------------------------------------------------------------------


def test_a_prerequisite_must_resolve_to_a_task(tree: Tree) -> None:
    tree.edit(TASK_T02, "    name: v1-e01-t01-first-step", "    name: v1-e01-t09-missing-step")
    expected = "context TaskRef 'v1-e01-t09-missing-step' does not resolve to a task"
    assert f"{TASK_T02}: {expected}" in errors(tree)


def test_release_order_forbids_a_prerequisite_from_a_later_release(tree: Tree) -> None:
    tree.edit(TASK_T02, "    name: v1-e01-t01-first-step", "    name: v1-e02-t01-later-step")
    assert f"{TASK_T02}: prerequisite v1-e02-t01-later-step ships in a later release (v1.1)" in errors(tree)


def test_the_cross_task_prerequisite_graph_must_be_acyclic(tree: Tree) -> None:
    tree.edit(
        TASK_T01,
        "  priority: 1\n",
        "  priority: 1\n"
        "  context:\n"
        "  - kind: TaskRef\n"
        "    name: v1-e01-t02-second-step\n"
        "    relation: dependsOn\n",
    )
    assert "plan_specs: cross-task prerequisite graph contains a cycle" in errors(tree)


# --------------------------------------------------------------------------------------------
# releases
# --------------------------------------------------------------------------------------------


def test_a_release_references_only_epics_that_exist(tree: Tree) -> None:
    tree.edit(RELEASE_V10, "goalRef: v1-e01-minimal-foundation", "goalRef: v1-e09-ghost-epic")
    assert f"{RELEASE_V10}: unknown epic 'v1-e09-ghost-epic'" in errors(tree)


def test_a_release_references_only_epics_labeled_with_it(tree: Tree) -> None:
    tree.edit(RELEASE_V10, "goalRef: v1-e01-minimal-foundation", "goalRef: v1-e02-minimal-followup")
    assert f"{RELEASE_V10}: epic v1-e02-minimal-followup is labeled v1.1" in errors(tree)


def test_every_epic_is_referenced_by_its_release(tree: Tree) -> None:
    tree.edit(RELEASE_V10, "goalRef: v1-e01-minimal-foundation", "goalRef: v1-e09-ghost-epic")
    assert f"{EPIC_E01}: epic is not referenced by release v1.0" in errors(tree)


# --------------------------------------------------------------------------------------------
# release order comes from the release files, not from a list in the script
# --------------------------------------------------------------------------------------------


def test_release_order_is_not_hardcoded_in_the_validator() -> None:
    source = (REPO_ROOT / "scripts" / "validate_specs.py").read_text()
    assert "RELEASE_ORDER" not in source
    assert not hasattr(validate_specs, "RELEASE_ORDER")


def test_release_order_sorts_by_version_number_not_by_file_name(tmp_path: Path) -> None:
    releases = tmp_path / "plan_specs" / "releases"
    releases.mkdir(parents=True)
    for name in ["v1.10.yaml", "v1.2.yaml", "v2.0.yaml", "v1.0.yaml", "notes.yaml"]:
        (releases / name).touch()
    assert validate_specs.release_order(tmp_path / "plan_specs") == ["v1.0", "v1.2", "v1.10", "v2.0"]


def test_release_order_grows_with_a_new_release_file(tree: Tree) -> None:
    assert validate_specs.collect(tree.path).release_order == ["v1.0", "v1.1"]
    write_release(tree, "v1.2", "v1-e01-minimal-foundation")
    assert validate_specs.collect(tree.path).release_order == ["v1.0", "v1.1", "v1.2"]


def test_release_order_matches_the_repositorys_release_files() -> None:
    files = sorted(p.stem for p in (REPO_ROOT / "plan_specs" / "releases").glob("*.yaml"))
    assert sorted(validate_specs.collect(REPO_ROOT).release_order) == files


# --------------------------------------------------------------------------------------------
# --status and --require-succeeded
# --------------------------------------------------------------------------------------------


def test_status_counts_phases_per_release_and_per_epic(tree: Tree) -> None:
    lines = validate_specs.render_status(validate_specs.collect(tree.path))
    assert "v1.0 — Minimal foundation: 1 epic, 2 tasks — InProgress 1, Succeeded 1" in lines
    assert "  v1-e01-minimal-foundation: 2 tasks — InProgress 1, Succeeded 1" in lines
    assert "v1.1 — Minimal follow-up: 1 epic, 1 task — Pending 1" in lines
    assert "  v1-e02-minimal-followup: 1 task — Pending 1" in lines


def test_status_says_when_nothing_needs_attention(tree: Tree) -> None:
    lines = validate_specs.render_status(validate_specs.collect(tree.path))
    assert lines[-1] == "No Blocked or Failed tasks."


def test_status_names_blocked_and_failed_tasks(tree: Tree) -> None:
    tree.edit(TASK_T01, "status:\n  phase: Succeeded", "status:\n  phase: Failed")
    tree.edit(TASK_T02, "status:\n  phase: InProgress", "status:\n  phase: Blocked")
    lines = validate_specs.render_status(validate_specs.collect(tree.path))
    assert "Blocked or Failed tasks:" in lines
    assert "  v1-e01-t01-first-step: Failed (v1.0, v1-e01-minimal-foundation)" in lines
    assert "  v1-e01-t02-second-step: Blocked (v1.0, v1-e01-minimal-foundation)" in lines


def test_status_option_prints_the_roll_up(tree: Tree, capsys: Capture) -> None:
    assert validate_specs.main(["--status", "--root", str(tree.path)]) == 0
    out = capsys.readouterr().out
    assert "Status by release and epic" in out
    assert "  v1-e01-minimal-foundation: 2 tasks — InProgress 1, Succeeded 1" in out


def test_status_reports_every_release_in_the_repository(capsys: Capture) -> None:
    assert validate_specs.main(["--status", "--root", str(REPO_ROOT)]) == 0
    out = capsys.readouterr().out
    for version in validate_specs.release_order(REPO_ROOT / "plan_specs"):
        assert f"{version} — " in out
    for epic in validate_specs.collect(REPO_ROOT).epics:
        assert f"  {epic}: " in out


def require_succeeded(tree: Tree, name: str) -> int:
    return validate_specs.main(["--require-succeeded", name, "--root", str(tree.path)])


def test_require_succeeded_exits_zero_for_a_succeeded_goal(tree: Tree, capsys: Capture) -> None:
    assert require_succeeded(tree, "v1-e01-t01-first-step") == 0
    assert capsys.readouterr().out == "v1-e01-t01-first-step: Succeeded\n"


def test_require_succeeded_exits_one_for_an_unfinished_goal(tree: Tree, capsys: Capture) -> None:
    assert require_succeeded(tree, "v1-e01-t02-second-step") == 1
    assert capsys.readouterr().out == "v1-e01-t02-second-step: InProgress\n"


def test_require_succeeded_exits_one_for_an_unknown_name(tree: Tree, capsys: Capture) -> None:
    assert require_succeeded(tree, "v1-e01-t09-nothing") == 1
    assert capsys.readouterr().out == "v1-e01-t09-nothing: no such Goal\n"


def test_validation_exits_zero_on_a_valid_tree(tree: Tree, capsys: Capture) -> None:
    assert validate_specs.main(["--root", str(tree.path)]) == 0
    assert capsys.readouterr().out == "OK: 7 files, 2 epics, 3 tasks, 2 releases\n"


def test_validation_exits_one_and_lists_the_errors(tree: Tree, capsys: Capture) -> None:
    tree.edit(TASK_T01, "  phase: Succeeded", "  phase: Done")
    assert validate_specs.main(["--root", str(tree.path)]) == 1
    captured = capsys.readouterr()
    assert f"{TASK_T01}: status.phase 'Done' not in {ALL_PHASES}" in captured.out
    assert "1 error(s) in 7 files" in captured.err
