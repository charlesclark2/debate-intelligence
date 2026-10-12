"""ci.yml's `test` job: no coverage on a pull request, and a split that loses no test (v1-e01-t27).

The wait for `ci` on a pull request is the budget in working agreement 1. Two things keep the
`test` job inside it, and each could be undone by a change that still looks green:

* **Coverage is measured on pushes to dev and main only.** It cost a third of the suite's time and
  gates nothing. It could come back to pull requests through `addopts`, through the job's command
  or through `PYTEST_ADDOPTS`, so the commands are also run here and their output read.
* **The job is a matrix of parts.** A part that is never asked for, or a test dealt to no part,
  would simply not run, and nothing would fail. So every part is collected the way CI asks for
  it, and the node ids are compared with the unsplit collection of the `coverage` job's command.

The commands are read out of ci.yml, not restated, so these tests follow the workflow.
"""

from __future__ import annotations

import importlib
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
# One small file, so that running the two commands for real costs a second each. It imports a
# workspace package, which is what gives coverage something to report on.
A_SMALL_TEST_FILE = "packages/debate_workers/tests/test_smoke.py"


def jobs() -> dict[str, Any]:
    return yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def pytest_arguments(job: str) -> list[str]:
    """What the job passes to pytest, read out of its one pytest step."""
    [run] = [step["run"] for step in jobs()[job]["steps"] if " pytest " in step.get("run", "")]
    words = shlex.split(run)
    assert words[: len(UV_RUN_PYTEST)] == UV_RUN_PYTEST, run
    arguments = words[len(UV_RUN_PYTEST) :]
    # Neither job names a path: each runs everything `testpaths` lists. (It also keeps the commands
    # run below to the one small file they are given.)
    assert [word for word in arguments if (REPO_ROOT / word).exists()] == [], run
    return arguments


def part_arguments(part: int, parts: int) -> list[str]:
    arguments = pytest_arguments("test")
    assert arguments.count(PART_OF_THE_MATRIX) == 1, arguments
    return [f"{part}/{parts}" if word == PART_OF_THE_MATRIX else word for word in arguments]


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


def test_a_pull_request_run_prints_no_coverage_report_and_a_push_run_prints_it() -> None:
    with ThreadPoolExecutor() as pool:
        on_a_pull_request, on_a_push = pool.map(
            lambda arguments: run_pytest(*arguments, A_SMALL_TEST_FILE),
            [part_arguments(1, 1), pytest_arguments("coverage")],
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


def test_the_parts_together_are_exactly_the_default_selection_and_no_test_is_in_two_of_them() -> None:
    """The proof that splitting the job dropped nothing (ac3): one collection for each part and one
    unsplit, run side by side."""
    parts = parts_in_the_matrix()
    unsplit_arguments = pytest_arguments("coverage")
    with ThreadPoolExecutor(max_workers=len(parts) + 1) as pool:
        unsplit, *each_part = pool.map(
            lambda arguments: collected(*arguments),
            [unsplit_arguments, *(part_arguments(part, len(parts)) for part in parts)],
        )

    assert len(unsplit) > 5000, "the unsplit collection is not the whole suite"
    assert len(set(unsplit)) == len(unsplit)
    in_parts = Counter(node_id for part in each_part for node_id in part)
    in_two_parts = {node_id for node_id, times in in_parts.items() if times > 1}
    assert not in_two_parts, f"in more than one part: {some(in_two_parts)}"
    in_no_part = set(unsplit) - set(in_parts)
    assert not in_no_part, f"in the default selection and in no part: {some(in_no_part)}"
    only_in_a_part = set(in_parts) - set(unsplit)
    assert not only_in_a_part, f"in a part and not in the default selection: {some(only_in_a_part)}"
    assert sum(len(part) for part in each_part) == len(unsplit)

    # Level parts: each file's tests are dealt round the parts, so no part holds more than one
    # test more of any file than another does.
    held_by_part = [Counter(node_id.partition("::")[0] for node_id in part) for part in each_part]
    for test_file in {node_id.partition("::")[0] for node_id in unsplit}:
        held = [held_by_this_part[test_file] for held_by_this_part in held_by_part]
        assert max(held) - min(held) <= 1, f"{test_file} is dealt unevenly: {held}"
