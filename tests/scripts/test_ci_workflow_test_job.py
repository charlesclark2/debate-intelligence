"""ci.yml's `test` job: no coverage on a pull request, and a split that loses no test (v1-e01-t27).

The wait for `ci` on a pull request is the budget in working agreement 1. Two things keep the
`test` job inside it, and each could be undone by a change that still looks green:

* **Coverage is measured on pushes to dev and main only.** It cost a third of the suite's time and
  gates nothing. It could come back to pull requests through `addopts`, through the job's command
  or through `PYTEST_ADDOPTS`, so the commands are also run here and their output read.
* **The job is a matrix of parts.** A part that is never asked for, or a test dealt to no part,
  would simply not run, and nothing would fail. So every part is collected the way CI asks for
  it, and the node ids are compared with the unsplit collection of the `coverage` job's command.
* **Each part runs the selection it is given** (v1-e01-t38): on a pull request into dev, the test
  files `scripts/ci_test_selection.py` wrote; otherwise an empty file, which is the whole default
  selection. The parts are compared with the unsplit collection of both. The step that writes the
  file is run here too, with a stand-in for the script, to show that a script that cannot run
  leaves the whole selection rather than part of one. Which files the script chooses for which
  event is `tests/scripts/test_ci_workflow_test_selection.py`.

The commands are read out of ci.yml, not restated, so these tests follow the workflow.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
import tomllib
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

DEFAULT_SELECTION = "not slow and not live"
PART_OF_THE_MATRIX = "${{ matrix.part }}/${{ strategy.job-total }}"
UV_RUN_PYTEST = ["uv", "run", "--frozen", "pytest"]
# Where the selection step writes the test files and the pytest step reads them, as `@FILE`.
SELECTION_FILE = "$RUNNER_TEMP/test-selection.txt"
# One small file, so that running the two commands for real costs a second each. It imports a
# workspace package, which is what gives coverage something to report on.
A_SMALL_TEST_FILE = "packages/debate_workers/tests/test_smoke.py"


def jobs() -> dict[str, Any]:
    return yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def pytest_step(job: str) -> dict[str, Any]:
    [step] = [step for step in jobs()[job]["steps"] if " pytest " in step.get("run", "")]
    return step


def pytest_arguments(job: str) -> list[str]:
    """What the job passes to pytest, read out of its one pytest step."""
    run = pytest_step(job)["run"]
    words = shlex.split(run)
    assert words[: len(UV_RUN_PYTEST)] == UV_RUN_PYTEST, run
    arguments = words[len(UV_RUN_PYTEST) :]
    # Neither job names a path: the coverage job runs everything `testpaths` lists, and a part runs
    # what its selection file holds. (It also keeps the commands run below to the files they are
    # given.)
    assert [word for word in arguments if (REPO_ROOT / word).exists()] == [], run
    return arguments


def part_arguments(part: int, parts: int, selection: Path) -> list[str]:
    """A part's pytest arguments, reading its test files from `selection` as CI reads its own."""
    arguments = pytest_arguments("test")
    assert arguments.count(PART_OF_THE_MATRIX) == 1, arguments
    assert arguments.count(f"@{SELECTION_FILE}") == 1, arguments
    replaced = {PART_OF_THE_MATRIX: f"{part}/{parts}", f"@{SELECTION_FILE}": f"@{selection}"}
    return [replaced.get(word, word) for word in arguments]


def the_whole_selection(tmp_path: Path) -> Path:
    """What the selection step writes for every event but a pull request into dev: nothing."""
    selection = tmp_path / "whole-selection.txt"
    selection.write_text("", encoding="utf-8")
    return selection


def always_run_test_files() -> list[str]:
    """scripts/affected_tests.py's always-run list, as test files: it is in every selection."""
    spec = importlib.util.spec_from_file_location(
        "affected_tests_for_parts", REPO_ROOT / "scripts" / "affected_tests.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Its dataclasses look their module up in sys.modules while the class is built.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    files: set[str] = set()
    for entry in module.ALWAYS_RUN:
        path = REPO_ROOT / entry
        found = sorted(path.rglob("test_*.py")) if entry.endswith("/") else [path]
        assert found and all(file.is_file() for file in found), entry
        files |= {file.relative_to(REPO_ROOT).as_posix() for file in found}
    return sorted(files)


def parts_in_the_matrix() -> list[int]:
    return jobs()["test"]["strategy"]["matrix"]["part"]


def run_pytest(*arguments: str) -> subprocess.CompletedProcess[str]:
    """A fresh pytest in this checkout, in one process, without what this run put in the environment."""
    environment = {
        name: value for name, value in os.environ.items() if not name.startswith(("PYTEST_", "COV_CORE_"))
    }
    return subprocess.run(
        [sys.executable, "-m", "pytest", *arguments, "-n", "0", "-p", "no:cacheprovider", "--color=no"],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def collected(*arguments: str) -> list[str]:
    """The node ids pytest collects for these arguments."""
    completed = run_pytest(*arguments, "--collect-only", "-q", "--no-cov")
    assert completed.returncode == 0, completed.stdout[-2000:] + completed.stderr[-2000:]
    listing, _, summary = completed.stdout.partition("\n\n")
    node_ids = listing.splitlines()
    counted = re.search(r"^(\d+)(?:/\d+)? tests collected", summary, re.MULTILINE)
    assert counted and int(counted.group(1)) == len(node_ids), summary
    return node_ids


def some(node_ids: set[str]) -> str:
    return f"{len(node_ids)}, such as {sorted(node_ids)[:5]}"


# --------------------------------------------------------------------------------------------
# coverage: never on a pull request, still on a push to dev or main
# --------------------------------------------------------------------------------------------


def test_addopts_measure_no_coverage_so_neither_a_pull_request_nor_a_local_run_pays_for_it() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    addopts: list[str] = pyproject["tool"]["pytest"]["ini_options"]["addopts"]
    assert [option for option in addopts if option.startswith("--cov")] == []


def test_the_test_job_asks_for_no_coverage_and_runs_on_every_event() -> None:
    test = jobs()["test"]
    assert [word for word in pytest_arguments("test") if word.startswith("--cov")] == []
    assert "PYTEST_ADDOPTS" not in CI_WORKFLOW.read_text(encoding="utf-8")
    # Only the path filter decides whether it runs: pull requests, pushes and dispatches alike.
    assert test["if"] == "needs.changes.outputs.python == 'true'"


def test_coverage_is_measured_on_pushes_only_over_the_whole_default_selection() -> None:
    coverage = jobs()["coverage"]
    assert coverage["if"] == "github.event_name == 'push'"
    arguments = pytest_arguments("coverage")
    assert "--cov" in arguments
    assert "--cov-report=term-missing" in arguments
    assert arguments[arguments.index("-m") + 1] == DEFAULT_SELECTION
    assert "--part" not in arguments


def test_what_coverage_measures_is_what_it_measured_before_the_split() -> None:
    coverage = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["coverage"]
    assert coverage["run"]["branch"] is True
    assert coverage["run"]["source_pkgs"] == ["debate_core", "debate_cli", "debate_api", "debate_workers"]
    assert coverage["report"] == {"show_missing": True, "skip_empty": True}


def test_a_pull_request_run_prints_no_coverage_report_and_a_push_run_prints_it(tmp_path: Path) -> None:
    with ThreadPoolExecutor() as pool:
        on_a_pull_request, on_a_push = pool.map(
            lambda arguments: run_pytest(*arguments, A_SMALL_TEST_FILE),
            [part_arguments(1, 1, the_whole_selection(tmp_path)), pytest_arguments("coverage")],
        )

    for completed in (on_a_pull_request, on_a_push):
        assert completed.returncode == 0, completed.stdout[-2000:] + completed.stderr[-2000:]
        assert " passed" in completed.stdout
    assert "coverage" not in on_a_pull_request.stdout
    assert "TOTAL" not in on_a_pull_request.stdout
    assert "coverage: platform" in on_a_push.stdout
    assert re.search(r"^Name +Stmts +Miss +Branch +BrPart +Cover +Missing$", on_a_push.stdout, re.MULTILINE)
    assert re.search(r"^TOTAL +\d+", on_a_push.stdout, re.MULTILINE)


# --------------------------------------------------------------------------------------------
# the split: every part is asked for, and `ci` waits for all of them
# --------------------------------------------------------------------------------------------


def test_the_parts_are_numbered_from_one_and_each_asks_for_its_number_out_of_the_matrix_total() -> None:
    strategy = jobs()["test"]["strategy"]
    parts = parts_in_the_matrix()
    assert len(parts) >= 2
    assert parts == list(range(1, len(parts) + 1))
    # Each part reports for itself: one failing part does not cancel the others' results.
    assert strategy["fail-fast"] is False
    arguments = pytest_arguments("test")
    assert arguments[arguments.index("--part") + 1] == PART_OF_THE_MATRIX
    assert arguments[arguments.index("-m") + 1] == DEFAULT_SELECTION


def test_ci_needs_every_job_but_the_push_only_coverage_report() -> None:
    every_job = jobs()
    # A matrix job is one entry in `needs`, and its result is a failure if any part failed.
    assert sorted(every_job["ci"]["needs"]) == sorted(set(every_job) - {"ci", "coverage"})


def test_every_path_filtered_job_is_in_the_map_ci_reads_its_skips_from() -> None:
    every_job = jobs()
    [verdict] = every_job["ci"]["steps"]
    filter_of_job = json.loads(verdict["env"]["PATH_FILTER_OF_JOB"])
    gated = {
        name: match.group(1)
        for name, job in every_job.items()
        if (match := re.fullmatch(r"needs\.changes\.outputs\.(\w+) == 'true'", str(job.get("if", ""))))
    }
    assert gated["test"] == "python"
    assert filter_of_job == gated


@pytest.mark.parametrize("nonsense", ["0/4", "5/4", "2", "2/", "/4", "two/four", "-1/4", "1/0"])
def test_a_part_that_is_not_one_of_the_parts_is_refused(nonsense: str) -> None:
    run_in_parts = importlib.import_module("run_in_parts")
    with pytest.raises(Exception, match="expected K/N"):
        run_in_parts.part_of_parts(nonsense)


def assert_the_parts_are_exactly(unsplit: list[str], each_part: list[list[str]], what: str) -> None:
    """Every test of `unsplit` in exactly one part, nothing else in any, and the parts level."""
    assert len(set(unsplit)) == len(unsplit)
    in_parts = Counter(node_id for part in each_part for node_id in part)
    in_two_parts = {node_id for node_id, times in in_parts.items() if times > 1}
    assert not in_two_parts, f"in more than one part: {some(in_two_parts)}"
    in_no_part = set(unsplit) - set(in_parts)
    assert not in_no_part, f"in {what} and in no part: {some(in_no_part)}"
    only_in_a_part = set(in_parts) - set(unsplit)
    assert not only_in_a_part, f"in a part and not in {what}: {some(only_in_a_part)}"
    assert sum(len(part) for part in each_part) == len(unsplit)

    # Level parts: each file's tests are dealt round the parts, so no part holds more than one
    # test more of any file than another does.
    held_by_part = [Counter(node_id.partition("::")[0] for node_id in part) for part in each_part]
    for test_file in {node_id.partition("::")[0] for node_id in unsplit}:
        held = [held_by_this_part[test_file] for held_by_this_part in held_by_part]
        assert max(held) - min(held) <= 1, f"{test_file} is dealt unevenly: {held}"


def collect_unsplit_and_each_part(selection: Path) -> tuple[list[str], list[list[str]]]:
    """One unsplit collection of what `selection` names (the coverage job's command), and each part's,
    run side by side."""
    parts = parts_in_the_matrix()
    with ThreadPoolExecutor(max_workers=len(parts) + 1) as pool:
        unsplit, *each_part = pool.map(
            lambda arguments: collected(*arguments),
            [
                [*pytest_arguments("coverage"), f"@{selection}"],
                *(part_arguments(part, len(parts), selection) for part in parts),
            ],
        )
    return unsplit, each_part


def test_the_parts_together_are_exactly_the_default_selection_and_no_test_is_in_two_of_them(
    tmp_path: Path,
) -> None:
    """The proof that splitting the job dropped nothing (v1-e01-t27 ac3), for the whole selection:
    what every push, promotion and dispatch runs."""
    unsplit, each_part = collect_unsplit_and_each_part(the_whole_selection(tmp_path))

    assert len(unsplit) > 5000, "the unsplit collection is not the whole suite"
    assert_the_parts_are_exactly(unsplit, each_part, "the default selection")


def test_the_parts_together_are_exactly_an_affected_set_and_each_holds_some_of_the_always_run_list(
    tmp_path: Path,
) -> None:
    """The same proof for a selection given in the file, as a pull request into dev gives one (v1-e01-t38).

    Every selection holds the always-run list, and each part gets some of it, so no part of a small
    selection collects nothing (pytest's exit status 5, which would fail the part).
    """
    always_run = always_run_test_files()
    given = sorted({*always_run, A_SMALL_TEST_FILE, "tests/scripts/test_ci_workflow_test_job.py"})
    selection = tmp_path / "selection.txt"
    selection.write_text("".join(f"{test_file}\n" for test_file in given), encoding="utf-8")

    unsplit, each_part = collect_unsplit_and_each_part(selection)

    collected_files = {node_id.partition("::")[0] for node_id in unsplit}
    assert collected_files <= set(given)
    assert {A_SMALL_TEST_FILE, "tests/scripts/test_ci_workflow_test_job.py"} <= collected_files
    assert len(unsplit) < 5000, "the selection file was not read: this is the whole suite"
    assert_the_parts_are_exactly(unsplit, each_part, "the selection given")
    for number, part in enumerate(each_part, start=1):
        assert any(node_id.partition("::")[0] in always_run for node_id in part), f"part {number}"


# --------------------------------------------------------------------------------------------
# the selection: chosen in every part, read by its pytest, and never fewer tests than everything
# --------------------------------------------------------------------------------------------


def selection_step() -> dict[str, Any]:
    [step] = [
        step for step in jobs()["test"]["steps"] if "scripts/ci_test_selection.py" in step.get("run", "")
    ]
    return step


def test_every_part_chooses_its_tests_before_pytest_and_pytest_reads_the_file_it_wrote() -> None:
    steps = jobs()["test"]["steps"]
    chooser, runner = selection_step(), pytest_step("test")
    assert steps.index(chooser) < steps.index(runner)
    # In every part and on every event: the script, not the workflow, decides what the event runs.
    assert "if" not in chooser
    assert "if" not in runner
    assert f'--output "{SELECTION_FILE}"' in chooser["run"]
    assert pytest_arguments("test").count(f"@{SELECTION_FILE}") == 1
    assert chooser["env"] == {
        "EVENT_NAME": "${{ github.event_name }}",
        "BASE_BRANCH": "${{ github.base_ref }}",
        "BASE_SHA": "${{ github.event.pull_request.base.sha }}",
        "REF_NAME": "${{ github.ref_name }}",
    }


def test_the_checkout_holds_the_base_commit_and_the_job_fetches_and_reads_nothing_else() -> None:
    test = jobs()["test"]
    [checkout] = [step for step in test["steps"] if str(step.get("uses", "")).startswith("actions/checkout@")]
    # The merge commit GitHub tests and its parents; the first parent is the pull request's base.
    assert checkout["with"] == {"persist-credentials": False, "fetch-depth": 2}
    assert "permissions" not in test
    job = json.dumps(test)
    for forbidden in ("secrets.", "github.token", "GITHUB_TOKEN", "git fetch", "curl", "wget"):
        assert forbidden not in job, forbidden


A_STAND_IN_FOR_THE_SCRIPT = """#!/bin/sh
printf '%s\\n' "$@" > "$ARGUMENTS_SEEN"
previous=""
for argument in "$@"; do
  if [ "$previous" = "--output" ]; then
    printf 'packages/debate_core/tests/test_a_part_of_the_selection.py\\n' > "$argument"
  fi
  previous="$argument"
done
exit "$STAND_IN_STATUS"
"""


def run_the_selection_step(tmp_path: Path, status: int) -> tuple[subprocess.CompletedProcess[str], Path]:
    """The step's own shell, as a runner's default `bash -e` runs it, with `uv` standing in for the
    script: it writes one test file and exits with `status`."""
    stand_ins = tmp_path / "bin"
    stand_ins.mkdir()
    uv = stand_ins / "uv"
    uv.write_text(A_STAND_IN_FOR_THE_SCRIPT, encoding="utf-8")
    uv.chmod(0o755)
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    (tmp_path / "summary.md").write_text("", encoding="utf-8")
    environment = {
        "PATH": f"{stand_ins}{os.pathsep}{os.environ['PATH']}",
        "RUNNER_TEMP": str(runner_temp),
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"),
        "ARGUMENTS_SEEN": str(tmp_path / "arguments.txt"),
        "STAND_IN_STATUS": str(status),
        "EVENT_NAME": "pull_request",
        "BASE_BRANCH": "dev",
        "BASE_SHA": "0123abc",
        "REF_NAME": "7/merge",
    }
    completed = subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-c", selection_step()["run"]],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    arguments = (tmp_path / "arguments.txt").read_text(encoding="utf-8").splitlines()
    assert arguments == [
        "run", "--frozen", "python", "scripts/ci_test_selection.py",
        "--event", "pull_request", "--base-branch", "dev", "--base-sha", "0123abc", "--ref-name", "7/merge",
        "--output", f"{runner_temp}/test-selection.txt", "--summary", str(tmp_path / "summary.md"),
    ]  # fmt: skip
    return completed, runner_temp / "test-selection.txt"


def test_the_step_keeps_what_the_script_chose_when_it_succeeds(tmp_path: Path) -> None:
    completed, selection = run_the_selection_step(tmp_path, status=0)

    assert (
        selection.read_text(encoding="utf-8")
        == "packages/debate_core/tests/test_a_part_of_the_selection.py\n"
    )
    assert "::warning" not in completed.stdout
    assert (tmp_path / "summary.md").read_text(encoding="utf-8") == ""


def test_a_script_that_fails_leaves_the_whole_selection_not_the_part_it_wrote(tmp_path: Path) -> None:
    completed, selection = run_the_selection_step(tmp_path, status=1)

    assert selection.read_text(encoding="utf-8") == "", "a failed choice must run every test, not some"
    assert "::warning title=Test selection::" in completed.stdout
    summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert summary.startswith("### Tests: the whole default selection\n")
    assert "scripts/ci_test_selection.py failed" in summary
