"""ci.yml records each test file's duration on dev's push run, keeps it in GitHub's Actions cache,
and deals whole files to the `test` parts by it (v1-e41-t17).

The PM's read of 2026-11-02 found task pull requests' slowest part at 189-289 s of pytest, against
working agreement 1's 2-minute line, while every part built each file's module fixtures again. Now:

* **Every part of dev's push run times its tests** (run_in_parts.py's `--record-durations`) and keeps
  the file as an artifact; the `test-durations` job adds the parts up and saves the record in the
  Actions cache. It runs on dev's push run alone, and a failure there never fails that run.
* **Only `test-selection` restores the record**, once, and hands every part the same deal through
  its `files_to_parts` output. The PM's mutant is a part reading the cache itself: a record saved
  while the run goes on could then give two parts different deals and a file to two parts, or none.
* **A record that is missing, or a cache that cannot be reached, fails nothing.** The restore step
  may fail without failing the job, and a failed selection script deals test by test and says so.

The steps are run here with bash, `uv` stood in for, and their outputs read the way the runner reads
`$GITHUB_OUTPUT`. What the script deals for which record is tests/scripts/test_parts_dealt_by_durations.py.
Nothing here reaches GitHub or the network.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml
from tests.scripts.test_ci_workflow_selection_once_and_no_queue import (
    SELECTION_JOB,
    run_the_selection_step,
    selection_step,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

DURATIONS_JOB = "test-durations"
DURATIONS_SCRIPT = "scripts/ci_test_durations.py"
# Where the record is restored to and saved from: one directory, so the cache's version, which GitHub
# computes from the path, is the same for both.
RECORD_DIRECTORY = "${{ runner.temp }}/test-durations"
RECORD_FILE = "$RUNNER_TEMP/test-durations/test-durations.json"
# Every save is a key of its own (a cache entry is never overwritten); a restore takes the newest.
SAVED_PREFIX = "test-durations-"
SAVED_KEY = "test-durations-${{ github.run_id }}-${{ github.run_attempt }}"
# The deal every part reads, written from test-selection's output.
DEAL_FILE = "$RUNNER_TEMP/files-to-parts.json"
DEAL_OUTPUT = f"${{{{ needs.{SELECTION_JOB}.outputs.files_to_parts }}}}"
# What a push part times its tests into, and the artifact that carries it to `test-durations`.
DURATIONS_OF_A_PART = "${{ runner.temp }}/test-durations-part-${{ matrix.part }}-of-${{ strategy.job-total }}.json"
ARTIFACT_OF_A_PART = "test-durations-part-${{ matrix.part }}-of-${{ strategy.job-total }}"
ON_A_PUSH = "github.event_name == 'push'"
ON_DEVS_PUSH = "github.event_name == 'push' && github.ref == 'refs/heads/dev'"
# Pinned as this repository pins actions: a major-version tag, the same for both halves.
RESTORE_ACTION = "actions/cache/restore@v5"
SAVE_ACTION = "actions/cache/save@v5"
UPLOAD_ARTIFACT = "actions/upload-artifact@v6"
DOWNLOAD_ARTIFACT = "actions/download-artifact@v7"


def jobs() -> dict[str, Any]:
    return yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def steps_using(action: str) -> list[tuple[str, dict[str, Any]]]:
    """(job, step) for every step of ci.yml whose `uses:` starts with `action`."""
    return [
        (name, step)
        for name, job in jobs().items()
        for step in job.get("steps", [])
        if str(step.get("uses", "")).startswith(action)
    ]


def restore_step() -> dict[str, Any]:
    [(_, step)] = steps_using("actions/cache/restore@")
    return step


def save_step() -> dict[str, Any]:
    [(_, step)] = steps_using("actions/cache/save@")
    return step


def durations_job_step(text: str) -> dict[str, Any]:
    [step] = [
        step
        for step in jobs()[DURATIONS_JOB]["steps"]
        if text in str(step.get("uses", "")) or text in step.get("run", "")
    ]
    return step


def pytest_steps() -> list[dict[str, Any]]:
    return [step for step in jobs()["test"]["steps"] if " pytest " in step.get("run", "")]


def pytest_step(condition: str) -> dict[str, Any]:
    [step] = [step for step in pytest_steps() if step.get("if") == condition]
    return step


def in_a_part(text: str, part: int, parts: int, runner_temp: Path) -> str:
    for expression, value in {
        "${{ matrix.part }}": str(part),
        "${{ strategy.job-total }}": str(parts),
        "${{ runner.temp }}": str(runner_temp),
        "$RUNNER_TEMP": str(runner_temp),
    }.items():
        text = text.replace(expression, value)
    assert "${{" not in text, text
    return text


# --------------------------------------------------------------------------------------------
# restored once, by test-selection, and never read by a part
# --------------------------------------------------------------------------------------------


def test_only_the_selection_job_restores_the_record_and_no_part_reads_the_cache() -> None:
    """The PM's mutant: parts reading the cache themselves."""
    assert [job for job, _ in steps_using("actions/cache/restore@")] == [SELECTION_JOB]
    assert [job for job, _ in steps_using("actions/cache/save@")] == [DURATIONS_JOB]
    # No step anywhere uses the cache action's combined form, which restores as well as saves.
    assert steps_using("actions/cache@") == []
    test = json.dumps(jobs()["test"])
    for read in ("actions/cache", "test-durations/", "test-durations.json", "--durations"):
        assert read not in test, read
    # What a part reads from test-selection: the files, the matrix and the deal, nothing else.
    assert sorted(set(re.findall(rf"needs\.{SELECTION_JOB}\.outputs\.(\w+)", test))) == [
        "files_to_parts", "parts", "test_files",
    ]  # fmt: skip


def test_the_restore_comes_before_the_choice_and_never_fails_the_job() -> None:
    """The PM's mutant: a missing record failing the run. A miss restores nothing; a cache service
    that cannot be reached is a failed step the job goes on past."""
    steps = jobs()[SELECTION_JOB]["steps"]
    restore = restore_step()
    assert restore["uses"] == RESTORE_ACTION
    assert restore["continue-on-error"] is True
    assert restore["with"]["path"] == RECORD_DIRECTORY
    assert restore["with"]["restore-keys"] == SAVED_PREFIX
    assert "fail-on-cache-miss" not in restore["with"]
    # A key no save ever writes and that starts no saved key, so the newest save is what comes back.
    assert not SAVED_KEY.startswith(restore["with"]["key"])
    assert restore["with"]["key"].startswith(SAVED_PREFIX)
    assert "${{" not in restore["with"]["key"]
    assert steps.index(restore) < steps.index(selection_step())


def test_the_choice_reads_the_record_where_it_was_restored(tmp_path: Path) -> None:
    run_the_selection_step(tmp_path, status=0, outputs="run_parts=true\nparts=[1]\nfiles_to_parts=\n")
    arguments = (tmp_path / "arguments.txt").read_text(encoding="utf-8").splitlines()
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import ci_test_durations

    runner_temp = tmp_path / "runner-temp"
    restored_to = in_a_part(restore_step()["with"]["path"], 1, 1, runner_temp)
    assert arguments[arguments.index("--durations") + 1] == f"{restored_to}/{ci_test_durations.RECORD_NAME}"
    assert in_a_part(RECORD_FILE, 1, 1, runner_temp) == f"{restored_to}/{ci_test_durations.RECORD_NAME}"


def test_the_deal_the_script_made_is_the_selection_jobs_output(tmp_path: Path) -> None:
    deal = '{"part_of_file":{"tests/architecture/test_layers.py":2,"tests/specs/test_specs.py":1},"parts":2}'
    _, outputs = run_the_selection_step(
        tmp_path, status=0, outputs=f"run_parts=true\nparts=[1, 2]\nfiles_to_parts={deal}\n"
    )

    assert outputs["files_to_parts"] == deal
    assert jobs()[SELECTION_JOB]["outputs"]["files_to_parts"] == "${{ steps.choose.outputs.files_to_parts }}"


def test_a_selection_script_that_fails_deals_test_by_test_and_says_so(tmp_path: Path) -> None:
    """The PM's mutant: the fallback not reported. A failed script hands every part an empty deal."""
    completed, outputs = run_the_selection_step(
        tmp_path, status=1, outputs='run_parts=true\nparts=[1]\nfiles_to_parts={"parts": 1}\n'
    )

    assert outputs["files_to_parts"] == ""
    summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "dealt test by test" in summary
    assert "::warning title=Test selection::" in completed.stdout


# --------------------------------------------------------------------------------------------
# every part follows the one deal
# --------------------------------------------------------------------------------------------


def write_down_the_deal_step() -> dict[str, Any]:
    [step] = [step for step in jobs()["test"]["steps"] if DEAL_FILE in step.get("run", "") and " pytest " not in step["run"]]
    return step


def run_the_write_down_step(tmp_path: Path, deal: str) -> str:
    runner_temp = tmp_path / "part-runner-temp"
    runner_temp.mkdir()
    completed = subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-c", write_down_the_deal_step()["run"]],
        env={"PATH": os.environ["PATH"], "RUNNER_TEMP": str(runner_temp), "FILES_TO_PARTS": deal},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return (runner_temp / "files-to-parts.json").read_text(encoding="utf-8")


def test_every_part_writes_down_the_deal_and_hands_it_to_pytest() -> None:
    steps = jobs()["test"]["steps"]
    write_down = write_down_the_deal_step()
    assert write_down["env"] == {"FILES_TO_PARTS": DEAL_OUTPUT}
    assert len(pytest_steps()) == 2
    for step in pytest_steps():
        assert steps.index(write_down) < steps.index(step)
        words = shlex.split(step["run"])
        assert words.count("--files-to-parts") == 1, step["run"]
        assert words[words.index("--files-to-parts") + 1] == DEAL_FILE


def test_the_deal_reaches_the_part_as_written_and_no_deal_as_an_empty_file(tmp_path: Path) -> None:
    deal = '{"part_of_file":{"tests/specs/test_specs.py":1},"parts":1}'
    assert run_the_write_down_step(tmp_path / "with", deal) == deal
    assert run_the_write_down_step(tmp_path / "without", "") == ""


# --------------------------------------------------------------------------------------------
# recorded by every push part, added up and saved by dev's push run
# --------------------------------------------------------------------------------------------


def test_every_push_part_times_its_tests_and_no_pull_request_part_does() -> None:
    on_a_push = pytest_step(ON_A_PUSH)
    words = shlex.split(on_a_push["run"])
    assert words[words.index("--record-durations") + 1] == "$DURATIONS_FILE"
    assert on_a_push["env"]["DURATIONS_FILE"] == DURATIONS_OF_A_PART
    assert "--record-durations" not in pytest_step("github.event_name != 'push'")["run"]


def test_every_push_part_keeps_its_durations_without_failing_for_them() -> None:
    steps = jobs()["test"]["steps"]
    [upload] = [
        step
        for step in steps
        if str(step.get("uses", "")).startswith("actions/upload-artifact@")
        and step["with"]["name"] == ARTIFACT_OF_A_PART
    ]
    assert upload["uses"] == UPLOAD_ARTIFACT
    assert upload["if"] == ON_A_PUSH
    assert upload["continue-on-error"] is True
    assert upload["with"] == {
        "name": ARTIFACT_OF_A_PART,
        "path": DURATIONS_OF_A_PART,
        "if-no-files-found": "error",
        "retention-days": 1,
    }
    assert steps.index(pytest_step(ON_A_PUSH)) < steps.index(upload)


def test_the_record_is_made_on_devs_push_run_alone_and_never_fails_it() -> None:
    job = jobs()[DURATIONS_JOB]
    assert job.get("needs") in ("test", ["test"])
    assert job["if"] == ON_DEVS_PUSH
    assert job["continue-on-error"] is True
    assert job["timeout-minutes"] <= 10
    # Not one of `ci`'s needs: a pull request never runs it.
    assert DURATIONS_JOB not in jobs()["ci"]["needs"]
    # The workflow's own read-only token and no secret: the cache is the runner's to reach.
    assert "permissions" not in job
    text = json.dumps(job)
    for forbidden in ("secrets.", "github.token", "GITHUB_TOKEN", "curl", "wget"):
        assert forbidden not in text, forbidden

    download = durations_job_step("actions/download-artifact@")
    assert download["uses"] == DOWNLOAD_ARTIFACT
    assert download["with"] == {
        "pattern": "test-durations-part-*",
        "merge-multiple": True,
        "path": "${{ runner.temp }}/test-durations-parts",
    }
    combining = durations_job_step(DURATIONS_SCRIPT)
    assert combining["env"] == {"COMMIT": "${{ github.sha }}"}
    save = save_step()
    assert save["uses"] == SAVE_ACTION
    assert save["with"] == {"path": RECORD_DIRECTORY, "key": SAVED_KEY}
    steps = job["steps"]
    assert steps.index(download) < steps.index(combining) < steps.index(save)


A_STAND_IN_FOR_UV_RUN_PYTHON = """#!/bin/sh
if [ "$1 $2 $3" != "run --frozen python" ]; then
  echo "this stand-in runs only uv run --frozen python, not: uv $*" >&2
  exit 99
fi
shift 3
exec "$PYTHON" "$@"
"""


def test_the_parts_files_added_up_land_where_the_save_takes_the_record_from(tmp_path: Path) -> None:
    """The combining step itself, over the files two push parts leave under the names their step
    gives them, downloaded where the download step puts them."""
    runner_temp = tmp_path / "runner-temp"
    downloaded = Path(in_a_part(durations_job_step("actions/download-artifact@")["with"]["path"], 1, 1, runner_temp))
    downloaded.mkdir(parents=True)
    for part, seconds in ((1, {"tests/a/test_x.py": 2.5}), (2, {"tests/a/test_x.py": 1, "tests/test_y.py": 4})):
        name = Path(in_a_part(DURATIONS_OF_A_PART, part, 2, runner_temp)).name
        (downloaded / name).write_text(json.dumps(seconds), encoding="utf-8")
    stand_ins = tmp_path / "bin"
    stand_ins.mkdir()
    uv = stand_ins / "uv"
    uv.write_text(A_STAND_IN_FOR_UV_RUN_PYTHON, encoding="utf-8")
    uv.chmod(0o755)

    completed = subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-c", durations_job_step(DURATIONS_SCRIPT)["run"]],
        cwd=REPO_ROOT,
        env={
            "PATH": f"{stand_ins}{os.pathsep}{os.environ['PATH']}",
            "RUNNER_TEMP": str(runner_temp),
            "PYTHON": sys.executable,
            "COMMIT": "4c1fc6e0123456789abcdef0123456789abcdef0",
        },
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    record = Path(in_a_part(save_step()["with"]["path"], 1, 1, runner_temp)) / "test-durations.json"
    written = json.loads(record.read_text(encoding="utf-8"))
    assert written["files"] == {"tests/a/test_x.py": 3.5, "tests/test_y.py": 4.0}
    assert written["commit"] == "4c1fc6e0123456789abcdef0123456789abcdef0"
