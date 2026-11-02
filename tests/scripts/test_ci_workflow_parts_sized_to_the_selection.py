"""ci.yml runs as many test parts as the selection needs, and a dispatch can ask for xdist's work
stealing (v1-e41-t16).

Until v1-e41-t16 the `test` matrix was eight parts for every selection, and ordinary task pull
requests took 297-318 s of `ci` wall time with each part paying the whole selection's collection and
setup (docs/process/ci-test-part-costs.md). Now `test-selection` says how many parts run, one per 30
selected test files, at most eight and eight for the whole selection (the PM's ruling, 2026-11-02),
and the matrix is that list. Which number the script gives for which selection is
tests/scripts/test_ci_workflow_test_selection.py; that the parts partition the selection at every
size is the partition proof, tests/scripts/test_ci_workflow_test_job.py. What is checked here:

* **The matrix is the list `test-selection` gives**, every part asks for its number out of the
  matrix's total, and a broken choice runs the most parts over the whole selection.
* **`ci` still fails when any part of a sized matrix failed**, and still accepts a skip only behind
  a closed gate. The `ci` step is run with jq over the `needs` it would be given.
* **`--dist` is `load` on every run but a dispatch that asks for `worksteal`.** The PM compares the
  two on one commit after the merge and decides the default in a later change; the bot's dispatch
  asks for nothing. The locked pytest-xdist is run with `--dist worksteal` to show it takes it.

Nothing here reaches GitHub or the network.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml
from tests.scripts.test_ci_workflow_selection_once_and_no_queue import (
    SELECTION_JOB,
    every_need_passed,
    run_ci,
    selection_step,
    verdict_of,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
REFRESH_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "refresh-generated-files.yml"

THE_PARTS_CHOSEN = f"${{{{ fromJSON(needs.{SELECTION_JOB}.outputs.parts) }}}}"
PART_OF_THE_MATRIX = "${{ matrix.part }}/${{ strategy.job-total }}"
# What a part's pytest reads for xdist's distribution, and where the job sets it.
DIST_VARIABLE = "XDIST_DIST"
DIST_OF_THE_RUN = "${{ inputs.xdist_dist || 'load' }}"
A_SMALL_TEST_FILE = "packages/debate_workers/tests/test_smoke.py"


def workflow() -> dict[Any, Any]:
    return yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))


def jobs() -> dict[str, Any]:
    return workflow()["jobs"]


def triggers() -> dict[str, Any]:
    """The `on:` block; YAML 1.1 reads the bare key `on` as true."""
    flow = workflow()
    return flow["on"] if "on" in flow else flow[True]


def the_script() -> Any:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import ci_test_selection

    return ci_test_selection


def pytest_steps() -> list[dict[str, Any]]:
    return [step for step in jobs()["test"]["steps"] if " pytest " in step.get("run", "")]


# --------------------------------------------------------------------------------------------
# the matrix: the parts test-selection chose
# --------------------------------------------------------------------------------------------


def test_the_matrix_is_the_list_of_parts_the_selection_job_gives() -> None:
    test = jobs()["test"]
    assert test["strategy"]["matrix"] == {"part": THE_PARTS_CHOSEN}
    # Every part reports for itself.
    assert test["strategy"]["fail-fast"] is False
    assert sorted(test["needs"]) == sorted(["changes", SELECTION_JOB])
    assert "parts" in jobs()[SELECTION_JOB]["outputs"]


def test_every_part_asks_for_its_number_out_of_the_matrix_total_not_a_fixed_count() -> None:
    """The PM's mutant: a sized matrix whose parts still deal by eight. `strategy.job-total` is the
    length of the list, so `--part K/N` follows it; any number written in would not."""
    assert len(pytest_steps()) == 2
    for step in pytest_steps():
        words = shlex.split(step["run"])
        assert words[words.index("--part") + 1] == PART_OF_THE_MATRIX, step["run"]
    assert not re.search(r"--part\S* +\S*/\d", CI_WORKFLOW.read_text(encoding="utf-8"))


def test_a_selection_script_that_fails_runs_the_most_parts() -> None:
    """The fallback writes the whole selection's list, the script's own: more tests, never fewer."""
    run = selection_step()["run"]
    [fallback] = re.findall(r"echo \"parts=(\[[^\]]*\])\" >> \"\$GITHUB_OUTPUT\"", run)
    script = the_script()
    assert json.loads(fallback) == script.parts_of(script.whole("the script failed"))
    assert json.loads(fallback) == list(range(1, script.MOST_PARTS + 1))


# --------------------------------------------------------------------------------------------
# `ci`: a failed part of a matrix of any size fails it
# --------------------------------------------------------------------------------------------


def sized(parts: int) -> dict[str, dict[str, Any]]:
    needs = every_need_passed()
    needs[SELECTION_JOB]["outputs"]["parts"] = json.dumps(list(range(1, parts + 1)))
    return needs


@pytest.mark.parametrize("parts", [1, 2, 8])
@pytest.mark.parametrize("result", ["failure", "cancelled"])
def test_ci_fails_when_a_part_of_a_sized_matrix_failed(tmp_path: Path, parts: int, result: str) -> None:
    """The PM's mutant: a sized matrix whose `ci` gate reads a skip as success when a part failed. A
    matrix job's result is `failure` when any of its parts failed, whatever their number."""
    needs = sized(parts)
    needs["test"] = {"result": result, "outputs": {}}
    status, lines = run_ci(tmp_path, needs)
    assert status == 1
    assert verdict_of(lines, "test") == f"FAIL  test: {result}"


@pytest.mark.parametrize("parts", [1, 8])
def test_ci_passes_a_sized_matrix_whose_parts_passed_and_fails_one_skipped_while_tests_were_chosen(
    tmp_path: Path, parts: int
) -> None:
    status, lines = run_ci(tmp_path, sized(parts))
    assert status == 0, lines
    needs = sized(parts)
    needs["test"] = {"result": "skipped", "outputs": {}}
    status, lines = run_ci(tmp_path, needs)
    assert status == 1
    assert verdict_of(lines, "test") == "FAIL  test: skipped"


def test_the_gate_of_the_parts_is_unchanged_by_their_number() -> None:
    [verdict] = jobs()["ci"]["steps"]
    gates = json.loads(verdict["env"]["GATES_OF_JOB"])
    assert gates["test"] == ["changes.python", f"{SELECTION_JOB}.run_parts"]


# --------------------------------------------------------------------------------------------
# --dist: load, unless a dispatch asks for worksteal
# --------------------------------------------------------------------------------------------


def test_a_dispatch_can_ask_for_worksteal_and_load_is_the_default() -> None:
    inputs = triggers()["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"xdist_dist"}
    xdist_dist = inputs["xdist_dist"]
    assert xdist_dist["type"] == "choice"
    assert xdist_dist["options"] == ["load", "worksteal"]
    assert xdist_dist["default"] == "load"
    assert xdist_dist.get("required", False) is False
    assert xdist_dist["description"]


def test_every_part_runs_with_the_distribution_the_run_asked_for() -> None:
    test = jobs()["test"]
    # A job-level variable, not the input spelled into the command, which would be shell text.
    assert test["env"] == {DIST_VARIABLE: DIST_OF_THE_RUN}
    for step in pytest_steps():
        assert step["run"].count(f'--dist "${DIST_VARIABLE}"') == 1, step["run"]
        assert "inputs." not in step["run"]


def value_of(expression: str, context: Mapping[str, str]) -> str:
    """`a || 'literal'` as GitHub evaluates it: the first term that is not empty."""
    match = re.fullmatch(r"\$\{\{(.*)\}\}", expression.strip())
    assert match, expression
    value = ""
    for term in match.group(1).split("||"):
        term = term.strip()
        literal = re.fullmatch(r"'([^']*)'", term)
        value = literal.group(1) if literal else context.get(term, "")
        if value:
            return value
    return value


@pytest.mark.parametrize(
    ("inputs", "dist"),
    [
        # A push, a pull request and the bot's dispatch carry no inputs.
        ({}, "load"),
        # A dispatch from the Actions page or `gh workflow run` without -f gets the default.
        ({"inputs.xdist_dist": "load"}, "load"),
        ({"inputs.xdist_dist": "worksteal"}, "worksteal"),
    ],
    ids=["no-inputs", "default", "asked-for-worksteal"],
)
def test_only_a_dispatch_that_asks_for_worksteal_gets_it(inputs: dict[str, str], dist: str) -> None:
    assert value_of(jobs()["test"]["env"][DIST_VARIABLE], inputs) == dist


def test_the_bots_dispatch_asks_for_no_input() -> None:
    refresh = REFRESH_WORKFLOW.read_text(encoding="utf-8")
    [dispatch] = [line for line in refresh.splitlines() if "gh workflow run ci.yml" in line]
    assert not re.search(r"\s(-f|-F|--field|--raw-field|--json)\b", dispatch), dispatch


@pytest.mark.parametrize("dist", ["load", "worksteal"])
def test_the_locked_xdist_runs_a_part_with_either_distribution(dist: str) -> None:
    """Both choices are ones the locked pytest-xdist takes, on real workers."""
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-n",
            "2",
            "--dist",
            dist,
            "-p",
            "no:cacheprovider",
            "--color=no",
            "-q",
            "--no-cov",
            A_SMALL_TEST_FILE,
        ],  # fmt: skip
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout[-2000:] + completed.stderr[-2000:]
    assert "2 passed" in completed.stdout
