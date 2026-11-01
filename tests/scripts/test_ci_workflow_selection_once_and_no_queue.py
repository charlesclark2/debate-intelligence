"""ci.yml chooses the tests once, skips the test parts when none are chosen, cancels superseded
pull-request runs and no other run, and proves the partition only when it can change (v1-e41-t15).

Measured by the PM on 2026-11-01: every one of the eight `test` parts chose the tests for itself
(17 to 33 seconds each), the bot's refresh pull requests, which change only ROADMAP.md and
docs/README.md, ran all eight parts, and the partition proof, one test collecting the whole suite
nine times, held part 1 for 70 seconds on every whole-selection pull request. Each of the four
changes here could be undone by an edit that still looks green, so each is checked by what it does:

* **The selection is chosen once.** Only the `test-selection` job runs scripts/ci_test_selection.py,
  and every part writes down what that job chose and hands it to pytest. The selection step and the
  part's step are run here with bash, the script stood in for, and their outputs read the way the
  runner reads `$GITHUB_OUTPUT`.
* **No tests chosen skips the parts, and `ci` still passes; a failed part still fails it.** The
  `ci` job's own step is run with jq over the `needs` it would be given, for each case.
* **A new push to a pull request cancels its superseded run; nothing else is ever cancelled.** The
  concurrency group is evaluated for each kind of run, and GitHub's rule for a group (cancel what is
  going when cancel-in-progress is set; otherwise keep one pending run, cancelling the one before
  it) is applied to runs that arrive while the earlier ones still run.
* **The partition proof runs in a job of its own**, on every push and on a pull request that changes
  what it proves, and the parts never run it. Its path filter is evaluated as dorny/paths-filter
  evaluates it.

Nothing here reaches GitHub or the network.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml
from tests.scripts.test_ci_workflow_site_changes import (
    DISPATCH,
    PULL_REQUEST_INTO_DEV,
    PULL_REQUEST_INTO_MAIN,
    PUSH,
    changes_outputs,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

SELECTION_JOB = "test-selection"
SELECTION_SCRIPT = "scripts/ci_test_selection.py"
# What a part hands pytest as `@FILE`, written from the selection job's `test_files` output.
SELECTION_FILE = "$RUNNER_TEMP/test-selection.txt"
# The marker of the partition proof's tests, which the parts leave to a job of their own.
PARTITION_PROOF = "partition_proof"
PROOF_FILE = "tests/scripts/test_ci_workflow_test_job.py"


def workflow() -> dict[Any, Any]:
    return yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))


def jobs() -> dict[str, Any]:
    return workflow()["jobs"]


def read_github_output(text: str) -> dict[str, str]:
    """A `$GITHUB_OUTPUT` file as the runner reads it: `name=value` lines and `name<<DELIMITER`
    blocks, whose value is the lines up to the delimiter's own line. A later value of a name wins."""
    outputs: dict[str, str] = {}
    lines = text.split("\n")
    at = 0
    while at < len(lines):
        line = lines[at]
        at += 1
        if not line:
            continue
        name, equals, value = line.partition("=")
        if "<<" in name or not equals:
            name, _, delimiter = line.partition("<<")
            assert delimiter, f"neither name=value nor name<<DELIMITER: {line!r}"
            end = lines.index(delimiter, at)
            outputs[name] = "\n".join(lines[at:end])
            at = end + 1
        else:
            outputs[name] = value
    return outputs


# --------------------------------------------------------------------------------------------
# the selection: chosen once, in its own job, and read by every part
# --------------------------------------------------------------------------------------------


def jobs_running(text: str) -> list[str]:
    return [name for name, job in jobs().items() if any(text in step.get("run", "") for step in job["steps"])]


def selection_step() -> dict[str, Any]:
    [step] = [step for step in jobs()[SELECTION_JOB]["steps"] if SELECTION_SCRIPT in step.get("run", "")]
    return step


def test_one_job_chooses_the_tests_and_no_part_chooses_its_own() -> None:
    """The PM's mutant: a part that computes its own selection again."""
    assert jobs_running(SELECTION_SCRIPT) == [SELECTION_JOB]
    assert jobs_running("affected_tests") == []
    # Nothing gates it: whether any test runs is its answer to give.
    assert "if" not in jobs()[SELECTION_JOB]
    assert "if" not in selection_step()
    assert "strategy" not in jobs()[SELECTION_JOB]


def test_the_selection_job_hands_on_its_steps_answer_and_every_part_reads_it() -> None:
    selection = jobs()[SELECTION_JOB]
    step = selection_step()
    assert selection["outputs"] == {
        "run_parts": f"${{{{ steps.{step['id']}.outputs.run_parts }}}}",
        "test_files": f"${{{{ steps.{step['id']}.outputs.test_files }}}}",
    }
    test = jobs()["test"]
    assert sorted(test["needs"]) == sorted(["changes", SELECTION_JOB])
    [write_down] = [
        step
        for step in test["steps"]
        if SELECTION_FILE in step.get("run", "") and " pytest " not in step["run"]
    ]
    assert write_down["env"] == {"TEST_FILES": f"${{{{ needs.{SELECTION_JOB}.outputs.test_files }}}}"}
    pytest_steps = [step for step in test["steps"] if " pytest " in step.get("run", "")]
    assert len(pytest_steps) == 2
    for pytest_step in pytest_steps:
        assert test["steps"].index(write_down) < test["steps"].index(pytest_step)
        assert pytest_step["run"].count(f'"@{SELECTION_FILE}"') == 1


def test_the_selection_job_checks_out_the_history_it_compares_and_holds_no_token() -> None:
    selection = jobs()[SELECTION_JOB]
    [checkout] = [
        step for step in selection["steps"] if str(step.get("uses", "")).startswith("actions/checkout@")
    ]
    # A pull request's base commit, and origin/dev for the bot's dispatched run (v1-e41-t15).
    assert checkout["with"] == {"persist-credentials": False, "fetch-depth": 0}
    assert "permissions" not in selection
    job = json.dumps(selection)
    for forbidden in ("secrets.", "github.token", "GITHUB_TOKEN", "git fetch", "curl", "wget"):
        assert forbidden not in job, forbidden
    assert selection_step()["env"] == {
        "EVENT_NAME": "${{ github.event_name }}",
        "BASE_BRANCH": "${{ github.base_ref }}",
        "BASE_SHA": "${{ github.event.pull_request.base.sha }}",
        "REF_NAME": "${{ github.ref_name }}",
    }


A_STAND_IN_FOR_THE_SCRIPT = """#!/bin/sh
printf '%s\\n' "$@" > "$ARGUMENTS_SEEN"
previous=""
for argument in "$@"; do
  if [ "$previous" = "--outputs" ]; then
    printf '%s' "$STAND_IN_OUTPUTS" > "$argument"
  fi
  previous="$argument"
done
exit "$STAND_IN_STATUS"
"""

TWO_FILES_CHOSEN = (
    "run_parts=true\n"
    "test_files<<test_files_0123abcd\n"
    "packages/debate_core/tests/test_domain.py\n"
    "tests/architecture/test_layers.py\n"
    "test_files_0123abcd\n"
)


def run_the_selection_step(
    tmp_path: Path, status: int, outputs: str
) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
    """The selection step in its own shell, as a runner's default `bash -e` runs it, with `uv`
    standing in for the script: it writes `outputs` where it is told to and exits with `status`.
    Returns the step's result and its outputs, read from `$GITHUB_OUTPUT` as the runner reads them."""
    stand_ins = tmp_path / "bin"
    stand_ins.mkdir()
    uv = stand_ins / "uv"
    uv.write_text(A_STAND_IN_FOR_THE_SCRIPT, encoding="utf-8")
    uv.chmod(0o755)
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    github_output = tmp_path / "github-output"
    github_output.write_text("", encoding="utf-8")
    (tmp_path / "summary.md").write_text("", encoding="utf-8")
    completed = subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-c", selection_step()["run"]],
        env={
            "PATH": f"{stand_ins}{os.pathsep}{os.environ['PATH']}",
            "RUNNER_TEMP": str(runner_temp),
            "GITHUB_OUTPUT": str(github_output),
            "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"),
            "ARGUMENTS_SEEN": str(tmp_path / "arguments.txt"),
            "STAND_IN_STATUS": str(status),
            "STAND_IN_OUTPUTS": outputs,
            "EVENT_NAME": "pull_request",
            "BASE_BRANCH": "dev",
            "BASE_SHA": "0123abc",
            "REF_NAME": "7/merge",
        },
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    arguments = (tmp_path / "arguments.txt").read_text(encoding="utf-8").splitlines()
    assert arguments[:4] == ["run", "--frozen", "python", SELECTION_SCRIPT]
    assert arguments[4:12] == [
        "--event", "pull_request", "--base-branch", "dev", "--base-sha", "0123abc", "--ref-name", "7/merge",
    ]  # fmt: skip
    assert arguments[arguments.index("--summary") + 1] == str(tmp_path / "summary.md")
    return completed, read_github_output(github_output.read_text(encoding="utf-8"))


def run_the_part_step(tmp_path: Path, test_files: str) -> str:
    """A part's step that writes down the chosen test files, as `bash -e` runs it; returns the file."""
    [step] = [
        step
        for step in jobs()["test"]["steps"]
        if SELECTION_FILE in step.get("run", "") and " pytest " not in step["run"]
    ]
    runner_temp = tmp_path / "part-runner-temp"
    runner_temp.mkdir()
    completed = subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-c", step["run"]],
        env={"PATH": os.environ["PATH"], "RUNNER_TEMP": str(runner_temp), "TEST_FILES": test_files},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return (runner_temp / "test-selection.txt").read_text(encoding="utf-8")


def test_what_the_script_chose_reaches_every_part_as_one_test_file_per_line(tmp_path: Path) -> None:
    completed, outputs = run_the_selection_step(tmp_path, status=0, outputs=TWO_FILES_CHOSEN)

    assert outputs == {
        "run_parts": "true",
        "test_files": "packages/debate_core/tests/test_domain.py\ntests/architecture/test_layers.py",
    }
    assert "::warning" not in completed.stdout
    # pytest reads `@FILE` one argument per line; a blank line would be an empty path.
    assert run_the_part_step(tmp_path, outputs["test_files"]).splitlines() == [
        "packages/debate_core/tests/test_domain.py",
        "tests/architecture/test_layers.py",
    ]


def test_the_whole_selection_reaches_every_part_as_an_empty_file(tmp_path: Path) -> None:
    _, outputs = run_the_selection_step(
        tmp_path, status=0, outputs="run_parts=true\ntest_files<<end_x\nend_x\n"
    )

    assert outputs == {"run_parts": "true", "test_files": ""}
    assert run_the_part_step(tmp_path, outputs["test_files"]) == ""


def test_a_script_that_fails_runs_every_part_over_the_whole_selection(tmp_path: Path) -> None:
    """Even after writing an answer of its own: a failed choice runs every test, never some or none."""
    completed, outputs = run_the_selection_step(
        tmp_path, status=1, outputs="run_parts=false\ntest_files<<end_x\nend_x\n"
    )

    assert outputs.get("run_parts") == "true"
    assert outputs.get("test_files", "") == ""
    assert "::warning title=Test selection::" in completed.stdout
    summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert summary.startswith("### Tests: the whole default selection\n")
    assert "scripts/ci_test_selection.py failed" in summary


# --------------------------------------------------------------------------------------------
# `ci`: a skip is accepted only when an output its job is gated on says there is nothing to do
# --------------------------------------------------------------------------------------------

GATE = re.compile(r"needs\.([\w-]+)\.outputs\.(\w+) == 'true'")


def gates_in_the_if(job: dict[str, Any]) -> list[str] | None:
    """The `job.output` names a job's `if:` requires to be 'true', or None for a job that is not gated."""
    condition = job.get("if")
    if condition is None:
        return None
    terms = [term.strip() for term in str(condition).split("&&")]
    found = [GATE.fullmatch(term) for term in terms]
    assert all(found), f"not a conjunction of gates: {condition!r}"
    return [f"{match.group(1)}.{match.group(2)}" for match in found if match]


def gates_ci_reads() -> dict[str, list[str]]:
    [verdict] = jobs()["ci"]["steps"]
    return json.loads(verdict["env"]["GATES_OF_JOB"])


def test_ci_reads_each_jobs_gates_from_the_jobs_own_condition() -> None:
    every_job = jobs()
    gated = {
        name: gates
        for name, job in every_job.items()
        if name not in ("ci", "coverage") and (gates := gates_in_the_if(job)) is not None
    }
    assert gated["test"] == ["changes.python", f"{SELECTION_JOB}.run_parts"]
    assert gates_ci_reads() == gated
    # Every output a gate reads is one the job holding it declares, and `ci` can see it.
    for gates in gated.values():
        for gate in gates:
            holder, _, output = gate.partition(".")
            assert output in every_job[holder]["outputs"], gate
            assert holder in every_job["ci"]["needs"], gate


def every_need_passed() -> dict[str, dict[str, Any]]:
    """`toJSON(needs)` for a run in which every job `ci` needs ran and passed."""
    needs: dict[str, dict[str, Any]] = {
        name: {"result": "success", "outputs": {}} for name in jobs()["ci"]["needs"]
    }
    needs["changes"]["outputs"] = dict.fromkeys(jobs()["changes"]["outputs"], "true")
    needs[SELECTION_JOB]["outputs"] = {"run_parts": "true", "test_files": ""}
    return needs


def run_ci(tmp_path: Path, needs: Mapping[str, Any]) -> tuple[int, list[str]]:
    """The `ci` job's step, as `bash -e` runs it on the runner, given `needs`. Returns its exit status
    and the verdict line of each job."""
    [step] = jobs()["ci"]["steps"]
    environment = {name: str(value) for name, value in step["env"].items() if name != "NEEDS"}
    completed = subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-c", step["run"]],
        cwd=tmp_path,
        env={"PATH": os.environ["PATH"], "NEEDS": json.dumps(needs), **environment},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.stderr == "", completed.stderr
    return completed.returncode, completed.stdout.splitlines()


def verdict_of(lines: list[str], job: str) -> str:
    [line] = [line for line in lines if line.split()[1].rstrip(":") == job]
    return line


def test_ci_passes_when_every_job_passed(tmp_path: Path) -> None:
    status, lines = run_ci(tmp_path, every_need_passed())
    assert status == 0, lines
    assert len(lines) == len(jobs()["ci"]["needs"])


def no_tests_chosen() -> dict[str, dict[str, Any]]:
    """The bot's run: Python's filter matched, the selection chose nothing, and the parts were skipped."""
    needs = every_need_passed()
    needs[SELECTION_JOB]["outputs"] = {"run_parts": "false", "test_files": ""}
    needs["test"] = {"result": "skipped", "outputs": {}}
    return needs


def test_ci_passes_when_no_test_was_chosen_and_the_parts_were_skipped(tmp_path: Path) -> None:
    status, lines = run_ci(tmp_path, no_tests_chosen())
    assert status == 0, lines
    assert verdict_of(lines, "test").startswith("skip  test")
    assert f"{SELECTION_JOB}.run_parts" in verdict_of(lines, "test")


@pytest.mark.parametrize("result", ["failure", "cancelled"])
def test_ci_fails_when_a_part_failed_or_was_cancelled(tmp_path: Path, result: str) -> None:
    """The PM's mutant: `ci` treating a failed part as a skipped one. A matrix job's result is
    `failure` when any part failed, so the test job's result is what `ci` reads."""
    needs = every_need_passed()
    needs["test"] = {"result": result, "outputs": {}}
    status, lines = run_ci(tmp_path, needs)
    assert status == 1
    assert verdict_of(lines, "test") == f"FAIL  test: {result}"


def test_ci_fails_when_a_part_failed_whatever_its_gates_say(tmp_path: Path) -> None:
    """A gate that says 'false' excuses a skip, never a failure."""
    needs = no_tests_chosen()
    needs["test"] = {"result": "failure", "outputs": {}}
    status, lines = run_ci(tmp_path, needs)
    assert status == 1
    assert verdict_of(lines, "test") == "FAIL  test: failure"


def test_ci_fails_when_the_parts_were_skipped_though_tests_were_chosen(tmp_path: Path) -> None:
    needs = no_tests_chosen()
    needs[SELECTION_JOB]["outputs"]["run_parts"] = "true"
    status, lines = run_ci(tmp_path, needs)
    assert status == 1
    assert verdict_of(lines, "test") == "FAIL  test: skipped"


def test_ci_fails_when_the_selection_job_failed_and_so_skipped_the_parts(tmp_path: Path) -> None:
    needs = no_tests_chosen()
    needs[SELECTION_JOB] = {"result": "failure", "outputs": {}}
    status, lines = run_ci(tmp_path, needs)
    assert status == 1
    assert verdict_of(lines, SELECTION_JOB) == f"FAIL  {SELECTION_JOB}: failure"
    assert verdict_of(lines, "test") == "FAIL  test: skipped"


def test_ci_fails_when_the_changes_job_failed_and_every_gated_job_was_skipped(tmp_path: Path) -> None:
    needs = every_need_passed()
    needs["changes"] = {"result": "failure", "outputs": {}}
    for job in gates_ci_reads():
        needs[job] = {"result": "skipped", "outputs": {}}
    status, lines = run_ci(tmp_path, needs)
    assert status == 1
    for job in gates_ci_reads():
        assert verdict_of(lines, job) == f"FAIL  {job}: skipped"


# --------------------------------------------------------------------------------------------
# concurrency: a pull request's new push cancels its old run; no other run is ever cancelled
# --------------------------------------------------------------------------------------------

EXPRESSION = re.compile(r"\$\{\{(.*?)\}\}")
EQUALITY = re.compile(r"\s*([\w.]+)\s*==\s*'([^']*)'\s*")
NAME = re.compile(r"\s*([\w.]+)\s*")


def value_of(expression: str, context: Mapping[str, str | None]) -> str | bool | None:
    """One `${{ }}` expression, for the forms the concurrency block uses: a context name, `a || b`
    (the first value that is not empty, as GitHub returns it) and `name == 'literal'`. Anything else,
    or a name the context does not give, raises, so a form this cannot read fails the test."""
    value: str | bool | None = None
    for either in expression.split("||"):
        if equality := EQUALITY.fullmatch(either):
            value = context[equality.group(1)] == equality.group(2)
        elif name := NAME.fullmatch(either):
            value = context[name.group(1)]
        else:
            raise ValueError(f"not an expression this test reads: {either!r}")
        if value:
            return value
    return value


def evaluated(text: str, context: Mapping[str, str | None]) -> str | bool | None:
    """A workflow value: one expression alone keeps its type; within text, each becomes a string."""
    whole = EXPRESSION.fullmatch(text.strip())
    if whole:
        return value_of(whole.group(1), context)

    def as_text(match: re.Match[str]) -> str:
        value = value_of(match.group(1), context)
        return "" if value is None else str(value).lower() if isinstance(value, bool) else str(value)

    return EXPRESSION.sub(as_text, text)


def a_run(
    event: str, run_id: int, *, pull_request: int | None = None, ref: str = "refs/heads/dev"
) -> dict[str, str | None]:
    return {
        "github.event_name": event,
        "github.run_id": str(run_id),
        "github.ref": ref,
        "github.event.pull_request.number": None if pull_request is None else str(pull_request),
    }


def concurrency_of(run: Mapping[str, str | None]) -> tuple[str, bool]:
    block = workflow()["concurrency"]
    group = evaluated(block["group"], run)
    cancel = evaluated(str(block.get("cancel-in-progress", False)), run)
    assert isinstance(group, str) and group
    assert isinstance(cancel, bool) or cancel in ("true", "false"), cancel
    return group, cancel in (True, "true")


def cancelled(runs: list[dict[str, str | None]]) -> list[int]:
    """Which runs GitHub cancels when they start in this order and none has finished. A run with
    cancel-in-progress cancels every run of its group still going. Any other run waits behind its
    group's run in progress, and GitHub keeps one pending run per group: the one it replaces is
    cancelled."""
    in_progress: dict[str, list[int]] = {}
    pending: dict[str, int] = {}
    gone: list[int] = []
    for index, run in enumerate(runs):
        group, cancel_in_progress = concurrency_of(run)
        if cancel_in_progress:
            gone += in_progress.pop(group, [])
            if group in pending:
                gone.append(pending.pop(group))
            in_progress[group] = [index]
        elif in_progress.get(group):
            if group in pending:
                gone.append(pending.pop(group))
            pending[group] = index
        else:
            in_progress[group] = [index]
    return sorted(gone)


@pytest.mark.parametrize("branch", ["dev", "main"])
def test_pushes_to_dev_or_main_are_never_cancelled_however_quickly_they_land(branch: str) -> None:
    """The PM's mutant: push runs in a cancelling group. Dev's push run gates the pre-release, so
    each merge commit keeps its own verdict, even when three merges land while the first still runs."""
    pushes = [a_run("push", run_id, ref=f"refs/heads/{branch}") for run_id in (101, 102, 103)]
    assert cancelled(pushes) == []


def test_dispatched_runs_are_never_cancelled() -> None:
    dispatches = [
        a_run("workflow_dispatch", run_id, ref="refs/heads/bot/refresh-generated-files")
        for run_id in (201, 202)
    ]
    assert cancelled(dispatches) == []


def test_a_new_push_to_a_pull_request_cancels_its_superseded_run_and_nothing_else() -> None:
    runs = [
        a_run("pull_request", 301, pull_request=7, ref="refs/pull/7/merge"),
        a_run("push", 302),
        a_run("pull_request", 303, pull_request=8, ref="refs/pull/8/merge"),
        a_run("pull_request", 304, pull_request=7, ref="refs/pull/7/merge"),
        a_run("push", 305),
    ]
    assert cancelled(runs) == [0]


def test_the_pull_request_runs_of_one_pull_request_share_a_group_whatever_their_run() -> None:
    first, _ = concurrency_of(a_run("pull_request", 401, pull_request=9, ref="refs/pull/9/merge"))
    second, _ = concurrency_of(a_run("pull_request", 402, pull_request=9, ref="refs/pull/9/merge"))
    assert first == second


# --------------------------------------------------------------------------------------------
# the partition proof: a job of its own, on every push and when what it proves changes
# --------------------------------------------------------------------------------------------

PROOF_TRIGGERS = [
    ".github/workflows/ci.yml",
    "tests/pytest_plugins/run_in_parts.py",
    "tests/pytest_plugins/a_new_plugin.py",
    "scripts/ci_test_selection.py",
    "scripts/affected_tests.py",
    PROOF_FILE,
    "pyproject.toml",
    "conftest.py",
    "uv.lock",
]


def proof_step() -> dict[str, Any]:
    [step] = [step for step in jobs()["partition-proof"]["steps"] if " pytest " in step.get("run", "")]
    return step


def marked_tests() -> dict[str, list[str]]:
    """Every test function marked as the partition proof, by file, read with ast."""
    listing = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z", "--", "*.py"], capture_output=True, check=True
    ).stdout
    found: dict[str, list[str]] = {}
    for name in sorted(listing.decode().split("\0")):
        path = REPO_ROOT / name
        if not name or not path.name.startswith("test_") or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if PARTITION_PROOF not in text:
            continue
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.FunctionDef) and any(
                PARTITION_PROOF in ast.unparse(decorator) for decorator in node.decorator_list
            ):
                found.setdefault(path.relative_to(REPO_ROOT).as_posix(), []).append(node.name)
    return found


def test_the_proof_has_a_job_of_its_own_that_runs_its_marked_tests_and_nothing_else() -> None:
    proof = jobs()["partition-proof"]
    assert proof["needs"] in ("changes", ["changes"])
    assert gates_in_the_if(proof) == [f"changes.{PARTITION_PROOF}"]
    assert proof["timeout-minutes"] <= 10
    words = proof_step()["run"].split()
    assert words[:4] == ["uv", "run", "--frozen", "pytest"]
    assert words[-1] == PROOF_FILE
    assert f'-m "{PARTITION_PROOF} and not slow and not live"' in proof_step()["run"]
    # Both proofs, the whole selection and an affected set, and every marked test, are in that file.
    assert marked_tests() == {
        PROOF_FILE: [
            "test_the_parts_together_are_exactly_the_default_selection_and_no_test_is_in_two_of_them",
            "test_the_parts_together_are_exactly_an_affected_set_and_each_holds_some_of_the_always_run_list",
        ]
    }
    markers = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["pytest"][
        "ini_options"
    ]["markers"]
    assert any(marker.startswith(f"{PARTITION_PROOF}:") for marker in markers)


def test_the_parts_leave_the_proof_to_its_job() -> None:
    for step in jobs()["test"]["steps"]:
        if " pytest " in step.get("run", ""):
            assert f'-m "not slow and not live and not {PARTITION_PROOF}"' in step["run"], step["run"]


@pytest.mark.parametrize("path", PROOF_TRIGGERS)
def test_the_proof_runs_on_a_pull_request_that_changes_what_it_proves(path: str) -> None:
    for context in (PULL_REQUEST_INTO_DEV, PULL_REQUEST_INTO_MAIN):
        assert changes_outputs([path], context)[PARTITION_PROOF] == "true", path
        assert (
            changes_outputs(["packages/debate_core/src/debate_core/__init__.py", path], context)[
                PARTITION_PROOF
            ]
            == "true"
        )


@pytest.mark.parametrize(
    "path",
    [
        "packages/debate_core/src/debate_core/__init__.py",
        "tests/scripts/test_ci_workflow_test_selection.py",
        "scripts/validate_specs.py",
        "docs/process/working-agreements.md",
        "ROADMAP.md",
    ],
)
def test_the_proof_does_not_run_on_a_pull_request_that_leaves_it_alone(path: str) -> None:
    """The proof collects the whole suite nine times; a change that cannot move a test between parts
    does not pay for it."""
    assert changes_outputs([path], PULL_REQUEST_INTO_DEV)[PARTITION_PROOF] == "false"


def test_the_proof_runs_on_every_push_whatever_changed() -> None:
    """The PM's mutant: the partition proof never selected. Every push to dev and main proves it."""
    assert changes_outputs(["site/content/pages/results.md"], PUSH)[PARTITION_PROOF] == "true"
    assert changes_outputs([], PUSH)[PARTITION_PROOF] == "true"


def test_a_dispatched_run_leaves_the_proof_to_the_push_run_of_its_commit() -> None:
    """The PM's ruling: the proof runs on its triggers and on every push run. A dispatch runs every
    other job (test_ci_workflow_site_changes.py)."""
    assert changes_outputs([], DISPATCH)[PARTITION_PROOF] == "false"
