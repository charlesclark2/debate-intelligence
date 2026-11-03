"""ci.yml's `test` and `coverage` jobs: coverage on a push only, measured in the parts and combined,
and a split that loses no test (v1-e01-t27, v1-e01-t42).

The wait for `ci` on a pull request is the budget in working agreement 1, and the dev pre-release
waits for the push run. Three things keep both short, and each could be undone by a change that
still looks green:

* **Coverage is measured on pushes to dev and main only.** It costs about half again a part's time
  and gates nothing. It could come back to pull requests through `addopts`, through the pytest step
  a pull request runs or through `PYTEST_ADDOPTS`, so the commands are also run here and their
  output read.
* **On a push, each part measures its own share and one short job combines them** (v1-e01-t42).
  The unsplit run that measured it before passed its 20-minute limit on every push from 2026-10-26
  and held the pre-release. A part whose data went missing would quietly drop its tests out of the
  total, so the combining step is run here against a part's data taken away, and its report is
  compared with the unsplit report of the same tests.
* **The job is a matrix of parts.** A part that is never asked for, or a test dealt to no part,
  would simply not run, and nothing would fail. So every part is collected the way CI asks for
  it, and the node ids are compared with the unsplit collection of the same command. Those two
  proofs collect the whole suite nine times between them, so they carry the `partition_proof`
  marker: the parts leave them out, and ci.yml's `partition-proof` job runs them on every push and
  on a pull request that changes what they prove (v1-e41-t15). Since v1-e41-t16 the matrix is as
  many parts as `test-selection` gives for the selection, one to eight, so the proofs collect the
  parts it gives and also deal the real collection with the plugin's own function at every size the
  rule can give: milliseconds, where collecting every size would collect the suite 45 times.
* **Each part runs the selection it is given** (v1-e01-t38): on a pull request into dev, the test
  files `scripts/ci_test_selection.py` chose; otherwise an empty file, which is the whole default
  selection. Since v1-e41-t17 every part is also given the same deal of whole test files to parts,
  made from the durations dev's push run recorded, or an empty one that deals test by test as
  before; the proofs collect the parts under a deal made from invented durations and under none, and
  deal the real collection both ways at every size. The parts are compared with the unsplit collection of both. Since v1-e41-t15 the
  `test-selection` job chooses them once for every part, and
  `tests/scripts/test_ci_workflow_selection_once_and_no_queue.py` runs its step and the part's;
  which files the script chooses for which event is `tests/scripts/test_ci_workflow_test_selection.py`.

The commands are read out of ci.yml, not restated, so these tests follow the workflow.
"""

from __future__ import annotations

import fnmatch
import importlib
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tomllib
import zlib
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from coverage import CoverageData

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

# The default selection, less the partition proof, which has a job of its own (v1-e41-t15).
PARTS_SELECTION = "not slow and not live and not partition_proof"
PART_OF_THE_MATRIX = "${{ matrix.part }}/${{ strategy.job-total }}"
UV_RUN_PYTEST = ["uv", "run", "--frozen", "pytest"]
# xdist's distribution, set by the job: `worksteal` but on a dispatch that asks for load (v1-e41-t16).
# It moves no test between parts, so the commands here run with the default.
XDIST_DIST = "$XDIST_DIST"
THE_DEFAULT_DIST = "worksteal"
# Where the selection step writes the test files and the pytest step reads them, as `@FILE`.
SELECTION_FILE = "$RUNNER_TEMP/test-selection.txt"
# Where a part writes down test-selection's deal of whole files to parts (v1-e41-t17), and where a
# push part times its tests into.
DEAL_FILE = "$RUNNER_TEMP/files-to-parts.json"
DURATIONS_FILE = "$DURATIONS_FILE"
RECORD_DURATIONS = ["--record-durations", DURATIONS_FILE]
# One small file, so that running the commands for real costs a second each. It imports a workspace
# package, which is what gives coverage something to report on. It holds two tests, so two parts of
# it each run one.
A_SMALL_TEST_FILE = "packages/debate_workers/tests/test_smoke.py"

# A part runs one of two pytest steps: with coverage on a push, without it on any other event.
ON_A_PUSH = "github.event_name == 'push'"
ON_ANY_OTHER_EVENT = "github.event_name != 'push'"
# What a part's pytest adds on a push: coverage as [tool.coverage] says, and no report of its own.
# The `coverage` job prints one report, for every part together.
MEASURE_COVERAGE_WITHOUT_A_REPORT = ["--cov", "--cov-report="]
# Each part's data file and artifact are named for its part out of the matrix total, so the job that
# combines them can tell which part is missing without reading this file.
DATA_FILE_OF_A_PART = "${{ runner.temp }}/coverage-part-${{ matrix.part }}-of-${{ strategy.job-total }}"
ARTIFACT_OF_A_PART = "coverage-data-part-${{ matrix.part }}-of-${{ strategy.job-total }}"
DURATIONS_OF_A_PART = "${{ runner.temp }}/test-durations-part-${{ matrix.part }}-of-${{ strategy.job-total }}.json"
DOWNLOADED_DATA = "${{ runner.temp }}/coverage-data"
# Pinned the way every action in this repository is: a major-version tag.
UPLOAD_ARTIFACT = "actions/upload-artifact@v6"
DOWNLOAD_ARTIFACT = "actions/download-artifact@v7"
# The pytest-cov report's table, which the unsplit job printed and the combining job prints.
REPORT_HEADER = re.compile(r"^Name +Stmts +Miss +Branch +BrPart +Cover +Missing$", re.MULTILINE)
REPORT_TOTAL = re.compile(r"^TOTAL +\d+", re.MULTILINE)


def jobs() -> dict[str, Any]:
    return yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def pytest_step(condition: str) -> dict[str, Any]:
    """The `test` job's pytest step that runs under `condition`: one with coverage, one without."""
    [step] = [
        step
        for step in jobs()["test"]["steps"]
        if " pytest " in step.get("run", "") and step.get("if") == condition
    ]
    return step


def pytest_arguments(condition: str = ON_ANY_OTHER_EVENT) -> list[str]:
    """What a part passes to pytest under `condition`, read out of that pytest step."""
    run = pytest_step(condition)["run"]
    words = shlex.split(run)
    assert words[: len(UV_RUN_PYTEST)] == UV_RUN_PYTEST, run
    arguments = words[len(UV_RUN_PYTEST) :]
    # A part names no path: it runs what its selection file holds, or everything `testpaths` lists.
    # (It also keeps the commands run below to the files they are given.)
    assert [word for word in arguments if (REPO_ROOT / word).exists()] == [], run
    return [THE_DEFAULT_DIST if word == XDIST_DIST else word for word in arguments]


def unsplit_arguments() -> list[str]:
    """A part's own command without `--part` and its deal: the whole of what the parts share out, in
    one run."""
    arguments = pytest_arguments()
    at = arguments.index("--part")
    assert arguments[at + 1] == PART_OF_THE_MATRIX, arguments
    arguments = arguments[:at] + arguments[at + 2 :]
    at = arguments.index("--files-to-parts")
    assert arguments[at + 1] == DEAL_FILE, arguments
    arguments = arguments[:at] + arguments[at + 2 :]
    assert f"@{SELECTION_FILE}" in arguments, arguments
    return [word for word in arguments if word != f"@{SELECTION_FILE}"]


def in_a_part(text: str, part: int, parts: int, runner_temp: Path) -> str:
    """`text` as the runner sees it in part `part` of `parts`, with `runner_temp` as its temp dir."""
    replaced = {
        "${{ matrix.part }}": str(part),
        "${{ strategy.job-total }}": str(parts),
        "${{ runner.temp }}": str(runner_temp),
        "$RUNNER_TEMP": str(runner_temp),
    }
    for expression, value in replaced.items():
        text = text.replace(expression, value)
    assert "${{" not in text, text
    return text


def part_arguments(
    part: int,
    parts: int,
    selection: Path,
    condition: str = ON_ANY_OTHER_EVENT,
    deal: Path | None = None,
    durations: Path | None = None,
) -> list[str]:
    """A part's pytest arguments, reading its test files from `selection` and its deal from `deal`
    as CI reads its own. No deal is an empty file beside the selection: test by test. A push part
    times its tests into `durations`, or a file beside the selection."""
    arguments = pytest_arguments(condition)
    assert arguments.count(PART_OF_THE_MATRIX) == 1, arguments
    assert arguments.count(f"@{SELECTION_FILE}") == 1, arguments
    assert arguments.count(DEAL_FILE) == 1, arguments
    if deal is None:
        deal = selection.with_name(f"{selection.stem}-no-deal.json")
        deal.write_text("", encoding="utf-8")
    replaced = {
        PART_OF_THE_MATRIX: f"{part}/{parts}",
        f"@{SELECTION_FILE}": f"@{selection}",
        DEAL_FILE: str(deal),
        DURATIONS_FILE: str(durations or selection.with_name(f"durations-{part}-of-{parts}.json")),
    }
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


def the_selection_script() -> Any:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import ci_test_selection

    return ci_test_selection


def parts_given_for(test_files: list[str] | None) -> list[int]:
    """The matrix `test-selection` hands the `test` job for these test files (None: the whole
    selection), read from the `parts` output the script writes."""
    script = the_selection_script()
    choice = script.whole("the proof") if test_files is None else script.Choice(tuple(test_files), "", 0)
    [parts] = [
        line.removeprefix("parts=")
        for line in script.github_outputs(choice).splitlines()
        if line.startswith("parts=")
    ]
    return json.loads(parts)


def dealt_into(node_ids: list[str], parts: int, part_of_file: dict[str, int] | None = None) -> list[list[str]]:
    """`node_ids` dealt into `parts` parts by run_in_parts.py's own function, as its hook deals them,
    by the deal `part_of_file` or, without one, test by test."""
    dealt = importlib.import_module("run_in_parts").parts_dealt(node_ids, parts, part_of_file)
    return [
        [node_id for node_id, to in zip(node_ids, dealt, strict=True) if to == part] for part in range(parts)
    ]


def environment_without_this_run(**more: str) -> dict[str, str]:
    """This process's environment, less what this run put there: its pytest and coverage settings.
    On a push this file runs under `--cov` itself, and a COVERAGE_FILE handed down would send a
    child's data into this part's file."""
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("PYTEST_", "COV_CORE_", "COVERAGE_"))
    }
    return {**environment, **more}


def run_pytest(*arguments: str, **environment: str) -> subprocess.CompletedProcess[str]:
    """A fresh pytest in this checkout, in one process, without what this run put in the environment.
    `--dist no` as well as `-n 0`: given a part's `--dist load` and no workers, pytest-cov measures as
    xdist's controller and keeps no data. On a runner `-n auto` starts the workers."""
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *arguments,
            "-n",
            "0",
            "--dist",
            "no",
            "-p",
            "no:cacheprovider",
            "--color=no",
        ],
        cwd=REPO_ROOT,
        env=environment_without_this_run(**environment),
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
# coverage: never on a pull request; on a push, measured in every part and combined in one job
# --------------------------------------------------------------------------------------------


def test_addopts_measure_no_coverage_so_neither_a_pull_request_nor_a_local_run_pays_for_it() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    addopts: list[str] = pyproject["tool"]["pytest"]["ini_options"]["addopts"]
    assert [option for option in addopts if option.startswith("--cov")] == []


def test_a_part_measures_no_coverage_on_any_event_but_a_push() -> None:
    test = jobs()["test"]
    assert [word for word in pytest_arguments(ON_ANY_OTHER_EVENT) if "cov" in word] == []
    assert "PYTEST_ADDOPTS" not in CI_WORKFLOW.read_text(encoding="utf-8")
    # Only the path filter and the selection decide whether the job runs: pull requests, pushes and
    # dispatches alike.
    assert (
        test["if"]
        == "needs.changes.outputs.python == 'true' && needs.test-selection.outputs.run_parts == 'true'"
    )
    # Exactly one pytest step runs on any event, and every step that has to do with coverage runs on
    # a push alone.
    pytest_steps = [step for step in test["steps"] if " pytest " in step.get("run", "")]
    assert sorted(step.get("if") for step in pytest_steps) == sorted([ON_A_PUSH, ON_ANY_OTHER_EVENT])
    about_coverage = [
        step for step in test["steps"] if re.search(r"--cov|COVERAGE_|-artifact@", json.dumps(step))
    ]
    assert about_coverage, "no step of the test job measures or keeps coverage"
    assert {step.get("if") for step in about_coverage} == {ON_A_PUSH}


def test_on_a_push_a_part_runs_the_same_tests_measuring_coverage_into_a_file_of_its_own() -> None:
    steps = jobs()["test"]["steps"]
    without, with_coverage = pytest_step(ON_ANY_OTHER_EVENT), pytest_step(ON_A_PUSH)
    # The same command, the same part of the same selection, and coverage added: so the partition
    # proof below, which collects the command without coverage, holds for the one with it.
    # It also times its tests for the next runs' deals (v1-e41-t17), which moves no test.
    arguments = pytest_arguments(ON_A_PUSH)
    at = arguments.index(RECORD_DURATIONS[0])
    assert arguments[at : at + 2] == RECORD_DURATIONS
    arguments = arguments[:at] + arguments[at + 2 :]
    assert [word for word in arguments if word not in MEASURE_COVERAGE_WITHOUT_A_REPORT] == pytest_arguments(
        ON_ANY_OTHER_EVENT
    )
    assert [word for word in arguments if word in MEASURE_COVERAGE_WITHOUT_A_REPORT] == (
        MEASURE_COVERAGE_WITHOUT_A_REPORT
    )
    assert with_coverage.get("env") == {
        "COVERAGE_FILE": DATA_FILE_OF_A_PART,
        "DURATIONS_FILE": DURATIONS_OF_A_PART,
    }
    assert "env" not in without
    assert steps.index(without) + 1 == steps.index(with_coverage)


def test_on_a_push_each_part_keeps_its_data_as_an_artifact_and_fails_without_any() -> None:
    steps = jobs()["test"]["steps"]
    [upload] = [
        step
        for step in steps
        if str(step.get("uses", "")).startswith("actions/upload-artifact@")
        and step["with"]["name"] == ARTIFACT_OF_A_PART
    ]
    assert upload["uses"] == UPLOAD_ARTIFACT
    assert upload["if"] == ON_A_PUSH
    assert upload["with"] == {
        "name": ARTIFACT_OF_A_PART,
        "path": DATA_FILE_OF_A_PART,
        "if-no-files-found": "error",
        # Read once, by the `coverage` job of the same run.
        "retention-days": 1,
    }
    assert steps.index(pytest_step(ON_A_PUSH)) < steps.index(upload)


def coverage_job_step(uses_or_runs: str) -> dict[str, Any]:
    [step] = [
        step
        for step in jobs()["coverage"]["steps"]
        if uses_or_runs in str(step.get("uses", "")) or uses_or_runs in step.get("run", "")
    ]
    return step


def test_the_coverage_job_waits_for_every_part_and_fails_the_push_run_when_it_fails() -> None:
    coverage = jobs()["coverage"]
    assert coverage["if"] == ON_A_PUSH
    # `test` as a whole: a matrix job is one entry in `needs`, done when every part is.
    assert coverage.get("needs") in ("test", ["test"])
    # Its result is the push run's (batch 2026-10-27v let it fail quietly while it was unsplit).
    assert "continue-on-error" not in coverage
    # It combines and reports; it runs no tests, so it stays short.
    assert coverage["timeout-minutes"] <= 10
    assert [step for step in coverage["steps"] if " pytest" in step.get("run", "")] == []

    download = coverage_job_step("actions/download-artifact@")
    assert download["uses"] == DOWNLOAD_ARTIFACT
    assert download["with"] == {
        "pattern": "coverage-data-part-*",
        "merge-multiple": True,
        "path": DOWNLOADED_DATA,
    }
    # Every part's artifact matches the pattern, whatever the matrix's size.
    for parts in (1, 8, 12):
        for part in range(1, parts + 1):
            name = in_a_part(ARTIFACT_OF_A_PART, part, parts, Path("/unused"))
            assert fnmatch.fnmatchcase(name, download["with"]["pattern"]), name
    steps = coverage["steps"]
    assert steps.index(download) < steps.index(coverage_job_step("coverage combine"))


def test_what_coverage_measures_is_what_it_measured_before_the_split() -> None:
    coverage = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["coverage"]
    assert coverage["run"]["branch"] is True
    assert coverage["run"]["source_pkgs"] == ["debate_core", "debate_cli", "debate_api", "debate_workers"]
    assert coverage["report"] == {"show_missing": True, "skip_empty": True}


A_STAND_IN_FOR_UV_RUN_COVERAGE = """#!/bin/sh
printf '%s\\n' "$*" >> "$UV_CALLS"
if [ "$1 $2 $3" != "run --frozen coverage" ]; then
  echo "this stand-in runs only uv run --frozen coverage, not: uv $*" >&2
  exit 99
fi
shift 3
exec "$PYTHON" -m coverage "$@"
"""


def run_the_combining_step(
    tmp_path: Path, downloaded: list[Path]
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """The `coverage` job's combining step in its own shell, as a runner's default `bash -e` runs it,
    over `downloaded` placed where the download step leaves them. `uv run --frozen coverage` is this
    interpreter's coverage, run from the checkout so that it reads pyproject.toml as the job does.
    Returns the step's result and every `uv` command it ran."""
    runner_temp = tmp_path / "combining-runner-temp"
    data = Path(in_a_part(DOWNLOADED_DATA, 1, 1, runner_temp))
    data.mkdir(parents=True)
    for data_file in downloaded:
        shutil.copyfile(data_file, data / data_file.name)
    stand_ins = tmp_path / "combining-bin"
    stand_ins.mkdir()
    uv = stand_ins / "uv"
    uv.write_text(A_STAND_IN_FOR_UV_RUN_COVERAGE, encoding="utf-8")
    uv.chmod(0o755)
    calls = tmp_path / "uv-calls.txt"
    calls.write_text("", encoding="utf-8")
    completed = subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-c", coverage_job_step("coverage combine")["run"]],
        cwd=REPO_ROOT,
        env=environment_without_this_run(
            PATH=f"{stand_ins}{os.pathsep}{os.environ['PATH']}",
            RUNNER_TEMP=str(runner_temp),
            UV_CALLS=str(calls),
            PYTHON=sys.executable,
        ),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    return completed, calls.read_text(encoding="utf-8").splitlines()


def report_table(output: str) -> list[list[str]]:
    """The rows of a coverage report, from its header to its TOTAL, split into columns."""
    lines = output.splitlines()
    start = next(index for index, line in enumerate(lines) if REPORT_HEADER.match(line))
    end = next(index for index, line in enumerate(lines) if REPORT_TOTAL.match(line))
    return [line.split() for line in lines[start : end + 1] if not set(line) <= {"-"}]


def test_a_pull_request_part_keeps_no_coverage_and_the_push_parts_combine_into_the_unsplit_report(
    tmp_path: Path,
) -> None:
    """The commands themselves, over two parts of one small file: the pull request's measures nothing,
    each push part leaves the data file its artifact uploads and prints no report, and the combining
    step prints the report the unsplit job printed for the same tests."""
    selection = tmp_path / "selection.txt"
    selection.write_text(f"{A_SMALL_TEST_FILE}\n", encoding="utf-8")
    pull_request_temp = tmp_path / "pull-request-runner-temp"
    pull_request_temp.mkdir()
    push_temps = [tmp_path / f"push-runner-temp-{part}" for part in (1, 2)]
    for runner_temp in push_temps:
        runner_temp.mkdir()
    # Where the push step tells coverage to write, and where the upload step reads, each read out of
    # ci.yml: the data has to be where its artifact is taken from.
    data_file_of_a_part = pytest_step(ON_A_PUSH).get("env", {}).get("COVERAGE_FILE")
    # Without it, the parts would write to .coverage in the checkout, and here in this one.
    assert data_file_of_a_part, "the push step names no data file of its own"
    data_files = [Path(in_a_part(data_file_of_a_part, part, 2, push_temps[part - 1])) for part in (1, 2)]
    [upload] = [
        step
        for step in jobs()["test"]["steps"]
        if step.get("uses") == UPLOAD_ARTIFACT and step["with"]["name"] == ARTIFACT_OF_A_PART
    ]
    uploaded = [Path(in_a_part(upload["with"]["path"], part, 2, push_temps[part - 1])) for part in (1, 2)]
    unsplit_data = tmp_path / "unsplit-coverage"

    with ThreadPoolExecutor() as pool:
        on_a_pull_request, *on_a_push, unsplit = pool.map(
            lambda command: run_pytest(*command[0], **command[1]),
            [
                # Were it to measure coverage, it would leave its data here.
                (part_arguments(1, 1, selection), {"COVERAGE_FILE": str(pull_request_temp / "leftover")}),
                *(
                    (
                        part_arguments(
                            part, 2, selection, ON_A_PUSH, durations=tmp_path / f"durations-{part}.json"
                        ),
                        {"COVERAGE_FILE": str(data_files[part - 1])},
                    )
                    for part in (1, 2)
                ),
                # What the unsplit job ran, over the same file.
                (
                    [*unsplit_arguments(), "--cov", "--cov-report=term-missing", A_SMALL_TEST_FILE],
                    {"COVERAGE_FILE": str(unsplit_data)},
                ),
            ],
        )

    for completed in (on_a_pull_request, *on_a_push, unsplit):
        assert completed.returncode == 0, completed.stdout[-2000:] + completed.stderr[-2000:]
        assert " passed" in completed.stdout
    # pytest-cov's report heading; the word alone is also in the checkout's path, which pytest prints.
    assert "coverage: platform" not in on_a_pull_request.stdout
    assert "coverage: platform" in unsplit.stdout
    assert "TOTAL" not in on_a_pull_request.stdout
    assert list(pull_request_temp.iterdir()) == []
    for part, completed in enumerate(on_a_push, start=1):
        assert "1 passed" in completed.stdout, f"part {part} of 2 did not run one of the two tests"
        assert "TOTAL" not in completed.stdout, "a part printed a report of its own share"
        assert uploaded[part - 1].is_file(), f"part {part} left no data where its artifact uploads from"
        assert sorted(path.name for path in push_temps[part - 1].iterdir()) == [data_files[part - 1].name]

    combined, calls = run_the_combining_step(tmp_path, data_files)

    assert combined.returncode == 0, combined.stdout[-2000:] + combined.stderr[-2000:]
    assert [call.split()[:3] for call in calls] == [["run", "--frozen", "coverage"]] * 2
    assert REPORT_HEADER.search(combined.stdout)
    assert report_table(combined.stdout) == report_table(unsplit.stdout)


def a_part_data_file(path: Path) -> Path:
    """A part's coverage data as pytest-cov leaves it: branch data for one workspace module."""
    module = REPO_ROOT / "packages" / "debate_workers" / "src" / "debate_workers" / "__init__.py"
    data = CoverageData(basename=str(path))
    data.add_arcs({str(module): {(-1, 1), (1, -1)}})
    data.write()
    return path


def downloaded_parts(tmp_path: Path, names: list[str]) -> list[Path]:
    made = tmp_path / "made"
    made.mkdir()
    return [a_part_data_file(made / name) for name in names]


def of(parts: int, *numbers: int) -> list[str]:
    return [f"coverage-part-{number}-of-{parts}" for number in numbers]


def test_the_combining_step_reports_when_every_part_of_the_matrix_is_there(tmp_path: Path) -> None:
    combined, calls = run_the_combining_step(tmp_path, downloaded_parts(tmp_path, of(8, *range(1, 9))))

    assert combined.returncode == 0, combined.stdout[-2000:] + combined.stderr[-2000:]
    [combine, report] = calls
    assert combine.split()[3] == "combine"
    assert sorted(word.rpartition("/")[2] for word in combine.split()[5:]) == sorted(of(8, *range(1, 9)))
    assert report.split()[3] == "report"
    assert REPORT_HEADER.search(combined.stdout)
    assert REPORT_TOTAL.search(combined.stdout)


@pytest.mark.parametrize(
    ("names", "named_in_the_error"),
    [
        # One part's data missing: the case each of the step's two checks refuses.
        (of(8, 1, 2, 3, 4, 6, 7, 8), "missing: 5;"),
        # The last part missing, and one of a matrix of another size in its place: the count is right,
        # so only the check of every part number refuses it.
        ([*of(8, 1, 2, 3, 4, 5, 6, 7), *of(9, 3)], "missing: 8;"),
        # Every part there, and one more of a matrix of another size: only the count refuses it.
        ([*of(8, *range(1, 9)), *of(9, 3)], "missing: none; found: coverage-part-1-of-8"),
        # Nothing downloaded at all.
        ([], "no part's coverage data"),
        # A name that says no matrix total.
        (["coverage-part-3"], "coverage-part-3 does not say"),
    ],
    ids=["one-part-missing", "last-part-missing", "a-part-too-many", "none", "no-total-in-the-name"],
)
def test_the_combining_step_fails_unless_it_has_exactly_every_part_of_the_matrix(
    tmp_path: Path, names: list[str], named_in_the_error: str
) -> None:
    """The PM's mutant: a combining job that reads fewer parts than the matrix has would report a
    total over fewer tests, and nothing would say so."""
    combined, calls = run_the_combining_step(tmp_path, downloaded_parts(tmp_path, names))

    assert combined.returncode != 0, combined.stdout
    assert calls == [], "it combined data while a part was missing"
    [error] = [line for line in combined.stdout.splitlines() if line.startswith("::error")]
    assert named_in_the_error in error
    assert "TOTAL" not in combined.stdout


# --------------------------------------------------------------------------------------------
# the split: every part is asked for, and `ci` waits for all of them
# --------------------------------------------------------------------------------------------


def test_the_parts_are_numbered_from_one_and_each_asks_for_its_number_out_of_the_matrix_total() -> None:
    strategy = jobs()["test"]["strategy"]
    # The list test-selection gives (v1-e41-t16), at every size its rule gives.
    assert strategy["matrix"] == {"part": "${{ fromJSON(needs.test-selection.outputs.parts) }}"}
    script = the_selection_script()
    assert len(script.SIZES_THE_RULE_GIVES) >= 2
    for size in script.SIZES_THE_RULE_GIVES:
        files = [f"tests/test_{number}.py" for number in range(size * script.TEST_FILES_PER_PART)]
        assert parts_given_for(files) == list(range(1, size + 1))
    assert parts_given_for(None) == list(range(1, max(script.SIZES_THE_RULE_GIVES) + 1))
    # Each part reports for itself: one failing part does not cancel the others' results.
    assert strategy["fail-fast"] is False
    arguments = pytest_arguments()
    assert arguments[arguments.index("--part") + 1] == PART_OF_THE_MATRIX
    assert arguments[arguments.index("-m") + 1] == PARTS_SELECTION


def test_ci_needs_every_job_but_the_push_only_coverage_report_and_durations_record() -> None:
    every_job = jobs()
    # A matrix job is one entry in `needs`, and its result is a failure if any part failed.
    assert sorted(every_job["ci"]["needs"]) == sorted(set(every_job) - {"ci", "coverage", "test-durations"})


@pytest.mark.parametrize("nonsense", ["0/4", "5/4", "2", "2/", "/4", "two/four", "-1/4", "1/0"])
def test_a_part_that_is_not_one_of_the_parts_is_refused(nonsense: str) -> None:
    run_in_parts = importlib.import_module("run_in_parts")
    with pytest.raises(Exception, match="expected K/N"):
        run_in_parts.part_of_parts(nonsense)


def assert_the_parts_are_exactly(
    unsplit: list[str], each_part: list[list[str]], what: str, part_of_file: dict[str, int] | None = None
) -> None:
    """Every test of `unsplit` in exactly one part, nothing else in any, and the parts dealt as asked:
    a file in the deal `part_of_file` whole in its part, and every other file level round them."""
    assert len(set(unsplit)) == len(unsplit)
    in_parts = Counter(node_id for part in each_part for node_id in part)
    in_two_parts = {node_id for node_id, times in in_parts.items() if times > 1}
    assert not in_two_parts, f"in more than one part: {some(in_two_parts)}"
    in_no_part = set(unsplit) - set(in_parts)
    assert not in_no_part, f"in {what} and in no part: {some(in_no_part)}"
    only_in_a_part = set(in_parts) - set(unsplit)
    assert not only_in_a_part, f"in a part and not in {what}: {some(only_in_a_part)}"
    assert sum(len(part) for part in each_part) == len(unsplit)

    # Whole files where the deal names them (v1-e41-t17), so a module's fixtures are built in one
    # part. Level parts for the rest: each file's tests are dealt round the parts, so no part holds
    # more than one test more of any file than another does.
    part_of_file = part_of_file or {}
    held_by_part = [Counter(node_id.partition("::")[0] for node_id in part) for part in each_part]
    for test_file in {node_id.partition("::")[0] for node_id in unsplit}:
        held = [held_by_this_part[test_file] for held_by_this_part in held_by_part]
        if test_file in part_of_file:
            assert [part for part, count in enumerate(held, start=1) if count] == [part_of_file[test_file]], (
                f"{test_file} is not whole in part {part_of_file[test_file]}: {held}"
            )
        else:
            assert max(held) - min(held) <= 1, f"{test_file} is dealt unevenly: {held}"


def collect_unsplit_and_each_part(
    selection: Path, *matrices: tuple[list[int], Path]
) -> tuple[list[str], list[list[list[str]]]]:
    """One unsplit collection of what `selection` names (a part's command without `--part`), and each
    part's of each matrix under its deal, run side by side. Until v1-e01-t42 the unsplit command was
    the `coverage` job's; a push part's command is this one with coverage added, which collects
    nothing more or less."""
    commands = [[*unsplit_arguments(), f"@{selection}"]]
    for parts, deal in matrices:
        commands += [part_arguments(part, len(parts), selection, deal=deal) for part in parts]
    with ThreadPoolExecutor(max_workers=len(commands)) as pool:
        unsplit, *every_part = pool.map(lambda arguments: collected(*arguments), commands)
    each_matrix: list[list[list[str]]] = []
    for parts, _ in matrices:
        each_matrix.append(every_part[: len(parts)])
        every_part = every_part[len(parts) :]
    return unsplit, each_matrix


def invented_record(tmp_path: Path, test_files: list[str]) -> Path:
    """Durations for `test_files` shaped like the costs page's (a few heavy files and a long tail), from
    a checksum of each path, and none for one file in twelve, which the deal counts as the median."""
    record = tmp_path / "test-durations.json"
    files = {}
    for test_file in test_files:
        checksum = zlib.crc32(test_file.encode("utf-8"))
        if checksum % 12:
            files[test_file] = 300.0 if checksum % 97 == 0 else 0.1 + checksum % 400 / 20
    record.write_text(
        json.dumps({"format": 1, "recorded_at": datetime.now(UTC).isoformat(), "commit": "proof", "files": files}),
        encoding="utf-8",
    )
    return record


def the_deal(test_files: list[str], parts: int, record: Path, tmp_path: Path) -> tuple[Any, Path]:
    """The deal `test-selection` makes of `test_files` into `parts` from `record`, and the file a part
    writes it down in, read from the `files_to_parts` output the script writes."""
    script = the_selection_script()
    deal = importlib.import_module("ci_test_durations").deal(test_files, parts, record, datetime.now(UTC))
    [handed] = [
        line.removeprefix("files_to_parts=")
        for line in script.github_outputs(script.Choice(tuple(test_files), "", 0), deal).splitlines()
        if line.startswith("files_to_parts=")
    ]
    path = tmp_path / f"files-to-parts-{parts}.json"
    path.write_text(handed, encoding="utf-8")
    return deal, path


def assert_dealt_at_every_size(
    unsplit: list[str],
    collected_parts: list[list[str]],
    part_of_file: dict[str, int],
    test_files: list[str],
    record: Path,
    what: str,
) -> None:
    """The collected parts are the plugin's function's dealing under the deal they were given, so that
    function, at every size the rule can give, under the deal the script makes for that size and
    under none, is what those parts would collect; and each of those is a partition."""
    assert [set(part) for part in dealt_into(unsplit, len(collected_parts), part_of_file)] == [
        set(part) for part in collected_parts
    ]
    durations = importlib.import_module("ci_test_durations")
    for size in the_selection_script().SIZES_THE_RULE_GIVES:
        assert_the_parts_are_exactly(unsplit, dealt_into(unsplit, size), f"{what}, in {size} parts")
        deal = durations.deal(test_files, size, record, datetime.now(UTC))
        assert_the_parts_are_exactly(
            unsplit,
            dealt_into(unsplit, size, deal.part_of_file),
            f"{what}, in {size} parts by durations",
            deal.part_of_file,
        )


@pytest.mark.partition_proof
def test_the_parts_together_are_exactly_the_default_selection_and_no_test_is_in_two_of_them(
    tmp_path: Path,
) -> None:
    """The proof that splitting the job dropped nothing (v1-e01-t27 ac3), for the whole selection:
    what every push, promotion and dispatch runs. The default selection here is the parts' own,
    which leaves out this proof and the next: the partition-proof job runs them. The parts are
    collected under a deal of whole files by invented durations (v1-e41-t17), the files being the
    ones test-selection lists for the whole selection."""
    parts = parts_given_for(None)
    script = the_selection_script()
    test_files = script.test_files_to_deal(REPO_ROOT, script.whole("the proof"))
    record = invented_record(tmp_path, test_files)
    deal, deal_file = the_deal(test_files, len(parts), record, tmp_path)
    assert deal.by_durations, deal.why

    unsplit, [each_part] = collect_unsplit_and_each_part(the_whole_selection(tmp_path), (parts, deal_file))

    assert len(unsplit) > 5000, "the unsplit collection is not the whole suite"
    # Every file pytest collects is one the deal counted, so none is a stranger to its durations.
    collected_files = {node_id.partition("::")[0] for node_id in unsplit}
    assert collected_files <= set(deal.part_of_file) | set(deal.spread), some(
        collected_files - set(deal.part_of_file) - set(deal.spread)
    )
    assert_the_parts_are_exactly(unsplit, each_part, "the default selection", deal.part_of_file)
    assert_dealt_at_every_size(unsplit, each_part, deal.part_of_file, test_files, record, "the default selection")


@pytest.mark.partition_proof
def test_the_parts_together_are_exactly_an_affected_set_and_each_holds_some_of_the_always_run_list(
    tmp_path: Path,
) -> None:
    """The same proof for a selection given in the file, as a pull request into dev gives one (v1-e01-t38).

    The selection's own matrix (v1-e41-t16) is collected dealt test by test, as when no record can be
    used, and the most parts there are under a deal by invented durations (v1-e41-t17). Every
    selection holds the always-run list, and dealt test by test each part gets some of it, so no part
    of a small selection collects nothing (pytest's exit status 5, which would fail the part), even
    in the most parts there are; a deal by durations gives every part a file with a recorded time.
    """
    always_run = always_run_test_files()
    given = sorted({*always_run, A_SMALL_TEST_FILE, "tests/scripts/test_ci_workflow_test_job.py"})
    selection = tmp_path / "selection.txt"
    selection.write_text("".join(f"{test_file}\n" for test_file in given), encoding="utf-8")
    test_by_test = tmp_path / "no-deal.json"
    test_by_test.write_text("", encoding="utf-8")

    its_own, the_most = parts_given_for(given), parts_given_for(None)
    assert len(its_own) < len(the_most), (its_own, the_most)
    record = invented_record(tmp_path, given)
    deal, deal_file = the_deal(given, len(the_most), record, tmp_path)
    assert deal.by_durations, deal.why
    unsplit, [in_its_own_parts, each_part] = collect_unsplit_and_each_part(
        selection, (its_own, test_by_test), (the_most, deal_file)
    )

    collected_files = {node_id.partition("::")[0] for node_id in unsplit}
    assert collected_files <= set(given)
    assert {A_SMALL_TEST_FILE, "tests/scripts/test_ci_workflow_test_job.py"} <= collected_files
    assert len(unsplit) < 5000, "the selection file was not read: this is the whole suite"
    assert_the_parts_are_exactly(unsplit, in_its_own_parts, "the selection given")
    assert_the_parts_are_exactly(unsplit, each_part, "the selection given", deal.part_of_file)
    assert_dealt_at_every_size(unsplit, each_part, deal.part_of_file, given, record, "the selection given")
    for number, part in enumerate(dealt_into(unsplit, len(the_most)), start=1):
        assert any(node_id.partition("::")[0] in always_run for node_id in part), f"part {number}"
    for number, part in enumerate(each_part, start=1):
        assert part, f"part {number} of {len(the_most)} by durations collects no test"
