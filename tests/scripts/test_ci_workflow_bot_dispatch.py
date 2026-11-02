"""The run refresh-generated-files.yml dispatches on its branch selects no job a path filter gates,
unless the branch carries more than the generated files (v1-e41-t16).

The bot's pull request is opened with the workflow token, which starts no pull_request run, so the
bot dispatches ci.yml on `bot/refresh-generated-files`. Since v1-e41-t15 that run's
`test-selection` compares the branch with origin/dev and runs no test part, but `changes` said
'true' for every event but a pull request, so the dispatch still ran typecheck, import-boundaries,
terraform-checks, the site job and workflow-lint over two regenerated Markdown files. Now `changes`
compares a dispatch of that branch with origin/dev too, as `test-selection` does, and gives what the
bot's pull request gives: nothing to check. A person's commit under the bot's, a deleted generated
file, or a branch that cannot be compared still runs everything, as a dispatch did before.

The step is run here with bash in a clone shaped as the runner's checkout of the branch, and its
`$GITHUB_OUTPUT` is read into the `changes` job's outputs as GitHub evaluates them. Nothing here
reaches GitHub or the network.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from tests.scripts.test_ci_workflow_selection_once_and_no_queue import read_github_output
from tests.scripts.test_ci_workflow_site_changes import (
    DISPATCH,
    DISPATCH_OF_THE_BOTS_BRANCH,
    PULL_REQUEST_INTO_DEV,
    PUSH,
    STEP_OUTPUT,
    changes_outputs,
    ci_jobs,
    holds,
)
from tests.scripts.test_ci_workflow_test_selection import (
    A_DOMAIN_CHANGE,
    GENERATED_FILES_BRANCH,
    REGENERATED,
    bot_branch,
    git,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
# The outputs no dispatch has ever set: the partition proof runs on pushes and on its own triggers.
NOT_ON_A_DISPATCH = {"partition_proof"}


def the_branch_step() -> dict[str, Any]:
    """The `changes` step that compares the bot's branch with origin/dev: its one `run:` step."""
    [step] = [step for step in ci_jobs()["changes"]["steps"] if "run" in step]
    return step


def run_the_branch_step(
    checkout: Path, tmp_path: Path
) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
    """The step in its own shell in `checkout`, as a runner's default `bash -e` runs it; returns its
    result and what it wrote to `$GITHUB_OUTPUT`, read as the runner reads it."""
    github_output = tmp_path / "github-output"
    github_output.write_text("", encoding="utf-8")
    completed = subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-c", the_branch_step()["run"]],
        cwd=checkout,
        env={"PATH": os.environ["PATH"], "HOME": str(tmp_path), "GITHUB_OUTPUT": str(github_output)},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return completed, read_github_output(github_output.read_text(encoding="utf-8"))


def outputs_of_the_dispatch(checkout: Path, tmp_path: Path) -> dict[str, str]:
    completed, written = run_the_branch_step(checkout, tmp_path)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return changes_outputs([], DISPATCH_OF_THE_BOTS_BRANCH, {the_branch_step()["id"]: written})


def assert_everything_runs(outputs: dict[str, str]) -> None:
    """What a dispatch selected before v1-e41-t16: every job but the partition proof."""
    assert {name for name, value in outputs.items() if value == "false"} == NOT_ON_A_DISPATCH, outputs
    assert outputs["python"] == "true"


@pytest.mark.parametrize(
    ("change", "dev_moves_on"),
    [
        (REGENERATED, False),
        (REGENERATED, True),
        ({"ROADMAP.md": REGENERATED["ROADMAP.md"]}, False),
        ({"docs/README.md": REGENERATED["docs/README.md"]}, True),
    ],
    ids=["both-on-dev-tip", "both-dev-moved-on", "roadmap", "docs-index-dev-moved-on"],
)
def test_the_bots_dispatch_of_the_generated_files_alone_selects_no_python_job_and_no_other(
    tmp_path: Path, change: dict[str, str | None], dev_moves_on: bool
) -> None:
    """The PM's mutant: the bot's dispatch still selecting Python jobs. It now gives what the bot's
    pull request gives (test_ci_workflow_site_changes.py): every output 'false'."""
    checkout = bot_branch(tmp_path, change, dev_moves_on=dev_moves_on)

    outputs = outputs_of_the_dispatch(checkout, tmp_path)

    assert outputs["python"] == "false"
    assert set(outputs.values()) == {"false"}, outputs
    assert outputs == changes_outputs(list(change), PULL_REQUEST_INTO_DEV)


def test_a_persons_commit_under_the_bots_still_runs_everything(tmp_path: Path) -> None:
    """v1-e41-t15's rule: the branch carries code, whatever its last commit does."""
    checkout = bot_branch(tmp_path, A_DOMAIN_CHANGE, REGENERATED)

    assert_everything_runs(outputs_of_the_dispatch(checkout, tmp_path))


def test_a_generated_file_deleted_on_the_bots_branch_runs_everything(tmp_path: Path) -> None:
    """A deleted generated file is not a regenerated one: links to it break."""
    checkout = bot_branch(tmp_path, {"ROADMAP.md": None})

    assert_everything_runs(outputs_of_the_dispatch(checkout, tmp_path))


def test_the_bots_branch_with_no_change_from_dev_runs_everything(tmp_path: Path) -> None:
    """Nothing to compare is not 'only the generated files'; the selection script says the same."""
    checkout = bot_branch(tmp_path)

    assert_everything_runs(outputs_of_the_dispatch(checkout, tmp_path))


def test_the_bots_branch_without_origin_dev_runs_everything_and_says_why(tmp_path: Path) -> None:
    """A comparison that cannot be made fails toward every job, and does not fail `changes`, which
    would fail `ci` with every gated job skipped."""
    checkout = bot_branch(tmp_path, REGENERATED)
    git(checkout, "update-ref", "-d", "refs/remotes/origin/dev")

    completed, written = run_the_branch_step(checkout, tmp_path)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "::warning" in completed.stdout
    assert_everything_runs(
        changes_outputs([], DISPATCH_OF_THE_BOTS_BRANCH, {the_branch_step()["id"]: written})
    )


@pytest.mark.parametrize(
    "context", [DISPATCH, PULL_REQUEST_INTO_DEV, PUSH], ids=["dispatch-of-dev", "pull-request", "push"]
)
def test_the_comparison_runs_only_for_a_dispatch_of_the_bots_branch(context: dict[str, str]) -> None:
    """Any other dispatch runs everything, whatever the step would have said; a pull request has its
    path filters and a push runs everything."""
    step = the_branch_step()
    assert not holds(step["if"], context)
    assert holds(step["if"], DISPATCH_OF_THE_BOTS_BRANCH)
    said_nothing_to_check = {step["id"]: dict.fromkeys(written_names(), "true")}
    if context is DISPATCH:
        assert_everything_runs(changes_outputs([], context, said_nothing_to_check))


def written_names() -> set[str]:
    """The step's outputs that the `changes` job reads."""
    step_id = the_branch_step()["id"]
    return {
        name
        for expression in ci_jobs()["changes"]["outputs"].values()
        for found_id, name in STEP_OUTPUT.findall(expression)
        if found_id == step_id
    }


def test_every_path_filtered_output_but_the_proof_reads_the_comparison() -> None:
    names = written_names()
    assert len(names) == 1, names
    readers = {
        output
        for output, expression in ci_jobs()["changes"]["outputs"].items()
        if f"steps.{the_branch_step()['id']}.outputs." in expression
    }
    assert readers == set(ci_jobs()["changes"]["outputs"]) - NOT_ON_A_DISPATCH


def test_only_the_bots_dispatch_checks_out_the_history_and_it_holds_no_token() -> None:
    """`changes` checked out nothing before: a full history only where the comparison needs it."""
    steps = ci_jobs()["changes"]["steps"]
    [checkout] = [step for step in steps if str(step.get("uses", "")).startswith("actions/checkout@")]
    assert checkout["if"] == the_branch_step()["if"]
    assert checkout["with"] == {"persist-credentials": False, "fetch-depth": 0}
    assert steps.index(checkout) < steps.index(the_branch_step())
    assert "env" not in the_branch_step()
    for forbidden in ("secrets.", "github.token", "GITHUB_TOKEN", "git fetch", "curl", "wget"):
        assert forbidden not in the_branch_step()["run"], forbidden


def test_the_step_names_the_same_branch_and_files_as_the_selection_script() -> None:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import ci_test_selection

    assert ci_test_selection.GENERATED_FILES_BRANCH == GENERATED_FILES_BRANCH
    assert f"github.ref_name == '{GENERATED_FILES_BRANCH}'" in the_branch_step()["if"]
    run = the_branch_step()["run"]
    for path in ci_test_selection.GENERATED_FILES:
        assert path in run, path
    assert f"origin/{ci_test_selection.AFFECTED_SET_BRANCH}...HEAD" in run
