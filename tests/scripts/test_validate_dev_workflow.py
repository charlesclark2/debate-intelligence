"""The shape of validate-dev.yml where a mistake would be silent (v1-e01-t34).

validate-dev only runs after a merge into dev, so no task pull request exercises it; a step that
pulls the wrong image, or a red result that reaches no one, shows up days later or not at all. These
tests hold those parts: the slow job pulls the Lambda image the deploy script names before the tier
runs, and the conclude job opens or updates an issue on a failure and closes it on a success.

Where a step's shell is the point, the test runs that step's own `run:` text with bash, in a
throwaway directory, against stub `docker` and `gh` commands that log their arguments. Nothing here
reaches GitHub, a registry or the network.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "validate-dev.yml"
PYTHON_DECLARATION = REPO_ROOT / "packages" / "debate_core" / "pyproject.toml"

STUB_LOG_LINE = 'printf \'%s %s\\n\' "$(basename "$0")" "$*" >> "$STUB_LOG"\n'


def jobs() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def step_named(job: dict[str, Any], start: str) -> tuple[int, dict[str, Any]]:
    [found] = [
        (index, step) for index, step in enumerate(job["steps"]) if step.get("name", "").startswith(start)
    ]
    return found


def write_stub(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text("#!/usr/bin/env bash\n" + STUB_LOG_LINE + body, encoding="utf-8")
    path.chmod(0o755)


def run_step(
    script: str, cwd: Path, stubs: Path, log: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    """A step's `run:` text as the runner runs it: bash -e, from the checkout."""
    return subprocess.run(
        ["bash", "-e", "-c", script],
        cwd=cwd,
        env={"PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}", "STUB_LOG": str(log), **env},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


# --------------------------------------------------------------------------------------------
# slow: the Lambda image is on the runner before the tier runs
# --------------------------------------------------------------------------------------------


def test_the_slow_job_sets_up_qemu_and_pulls_the_image_before_the_tier_runs() -> None:
    slow = jobs()["slow"]
    qemu_at, qemu = step_named(slow, "Set up QEMU")
    pull_at, pull = step_named(slow, "Pull the Lambda base image")
    tier_at, _ = step_named(slow, "Run pytest")

    assert qemu_at < pull_at < tier_at
    assert qemu["uses"].startswith("docker/setup-qemu-action@")
    assert "arm64" in qemu["with"]["platforms"]
    assert "scripts/tub_deploy.sh --print-base-image" in pull["run"]
    assert "continue-on-error" not in pull
    assert "continue-on-error" not in qemu


def declared_image() -> str:
    """The base image read from requires-python by hand, not by the script under test."""
    text = PYTHON_DECLARATION.read_text(encoding="utf-8")
    [line] = [line for line in text.splitlines() if line.startswith("requires-python")]
    minor = line.split('">=')[1].split(",")[0]
    return f"public.ecr.aws/lambda/python:{minor}"


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """The two files the pull step reads: the deploy script and the requires-python declaration."""
    root = tmp_path / "checkout"
    (root / "scripts").mkdir(parents=True)
    shutil.copy2(REPO_ROOT / "scripts" / "tub_deploy.sh", root / "scripts" / "tub_deploy.sh")
    (root / "packages" / "debate_core").mkdir(parents=True)
    shutil.copy2(PYTHON_DECLARATION, root / "packages" / "debate_core" / "pyproject.toml")
    return root


def test_the_pull_step_pulls_what_the_deploy_script_names_for_arm64(checkout: Path, tmp_path: Path) -> None:
    stubs, log = tmp_path / "bin", tmp_path / "calls.log"
    stubs.mkdir()
    write_stub(stubs, "docker", "")
    _, pull = step_named(jobs()["slow"], "Pull the Lambda base image")

    result = run_step(pull["run"], checkout, stubs, log, {})

    assert result.returncode == 0, result.stderr
    [pulled, inspected] = log.read_text(encoding="utf-8").splitlines()
    assert pulled == f"docker pull --platform linux/arm64 {declared_image()}"
    assert inspected.startswith("docker image inspect --format")
    assert inspected.endswith(f" {declared_image()}")


def test_a_failed_pull_fails_the_step(checkout: Path, tmp_path: Path) -> None:
    """Never a skip: a pull that fails stops the job before the tier could skip for it."""
    stubs, log = tmp_path / "bin", tmp_path / "calls.log"
    stubs.mkdir()
    write_stub(stubs, "docker", "exit 1\n")
    _, pull = step_named(jobs()["slow"], "Pull the Lambda base image")

    result = run_step(pull["run"], checkout, stubs, log, {})

    assert result.returncode != 0
    assert log.read_text(encoding="utf-8").splitlines() == [
        f"docker pull --platform linux/arm64 {declared_image()}"
    ]


@pytest.mark.parametrize("job", ["resolve", "smoke", "slow"])
def test_the_jobs_that_run_the_validated_commits_code_hold_no_write_permission(job: str) -> None:
    permissions = jobs()[job]["permissions"]

    if job == "resolve":
        assert permissions == {"contents": "read", "statuses": "write"}
    else:
        assert permissions == {"contents": "read"}


def test_only_conclude_may_write_issues_and_the_workflow_grants_nothing_else() -> None:
    flow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))

    assert flow["permissions"] == {"contents": "read"}
    assert jobs()["conclude"]["permissions"] == {"contents": "read", "statuses": "write", "issues": "write"}


# --------------------------------------------------------------------------------------------
# conclude: a red result opens or updates an issue, a green one closes it
# --------------------------------------------------------------------------------------------

SHA = "1" * 40
TAG = "v1.1.0-dev.102"
REPOSITORY = "charlesclark2/debate-intelligence"
RUN_LINK = f"https://github.com/{REPOSITORY}/actions/runs/42"
TOKEN = "ghs_SENTINELTOKEN0123456789"

GH_STUB = """
mkdir -p "$GH_CALLS"
printf '%s\\0' "$@" > "$GH_CALLS/$(ls "$GH_CALLS" | wc -l | tr -d ' ')"
if [ "${1:-} ${2:-}" = "issue list" ]; then printf '%s' "$GH_OPEN_ISSUES"; fi
"""


def test_the_issue_step_runs_after_conclude_even_when_it_failed_and_only_for_dev() -> None:
    conclude = jobs()["conclude"]
    conclude_at, _ = step_named(conclude, "Post success on the installed commit")
    issue_at, issue = step_named(conclude, "Open or update the validate-dev issue")
    summary_at, _ = step_named(conclude, "Summary")

    assert conclude_at < issue_at < summary_at
    condition = issue["if"]
    assert condition.startswith("always()")
    assert "steps.conclude.outputs.state != ''" in condition
    assert "env.POST_STATUS == 'true'" in condition
    assert "github.ref == 'refs/heads/dev'" in condition
    assert issue["env"]["STATE"] == "${{ steps.conclude.outputs.state }}"
    assert issue["env"]["DESCRIPTION"] == "${{ steps.conclude.outputs.description }}"
    assert issue["env"]["GH_TOKEN"] == "${{ github.token }}"
    assert "scripts/validate_dev.py issue" in issue["run"]


def gh_calls(directory: Path) -> list[list[str]]:
    files = sorted(directory.iterdir(), key=lambda path: int(path.name)) if directory.exists() else []
    return [path.read_text(encoding="utf-8").split("\0")[:-1] for path in files]


def run_issue_step(
    tmp_path: Path, state: str, open_issues: str
) -> tuple[subprocess.CompletedProcess[str], list[list[str]]]:
    checkout, stubs = tmp_path / "checkout", tmp_path / "bin"
    (checkout / "scripts").mkdir(parents=True)
    shutil.copy2(REPO_ROOT / "scripts" / "validate_dev.py", checkout / "scripts" / "validate_dev.py")
    stubs.mkdir()
    write_stub(stubs, "gh", GH_STUB)
    write_stub(stubs, "python3", f'exec "{sys.executable}" "$@"\n')
    _, step = step_named(jobs()["conclude"], "Open or update the validate-dev issue")

    result = run_step(
        step["run"],
        checkout,
        stubs,
        tmp_path / "stub.log",
        {
            "REQUESTED_SHA": SHA,
            "TAG": TAG,
            "STATE": state,
            "DESCRIPTION": "validation failed: slow failure" if state == "failure" else f"{TAG} validated",
            "GITHUB_SERVER_URL": "https://github.com",
            "GITHUB_REPOSITORY": REPOSITORY,
            "GITHUB_RUN_ID": "42",
            "GH_TOKEN": TOKEN,
            "GITHUB_TOKEN": TOKEN,
            "GH_CALLS": str(tmp_path / "gh-calls"),
            "GH_OPEN_ISSUES": open_issues,
        },
    )
    return result, gh_calls(tmp_path / "gh-calls")


LISTED = ["issue", "list", "--label", "validate-dev", "--state", "open", "--json", "number", "--limit", "100"]


def test_a_failure_with_no_issue_open_creates_the_label_and_opens_one(tmp_path: Path) -> None:
    result, calls = run_issue_step(tmp_path, "failure", "[]")

    assert result.returncode == 0, result.stderr
    [listed, labelled, opened] = calls
    assert listed == [*LISTED, "--repo", REPOSITORY]
    assert labelled == [
        "label",
        "create",
        "validate-dev",
        "--color",
        "B60205",
        "--force",
        "--repo",
        REPOSITORY,
    ]
    assert opened[:5] == ["issue", "create", "--title", "validate-dev is failing on dev", "--body"]
    assert opened[6:] == ["--label", "validate-dev", "--repo", REPOSITORY]
    body = opened[5]
    assert body.startswith(
        f"validate-dev failed on `{SHA}` ({TAG}): validation failed: slow failure\n\nRun: {RUN_LINK}"
    )
    assert TOKEN not in "\0".join(part for call in calls for part in call)


def test_a_failure_with_an_issue_open_comments_on_it(tmp_path: Path) -> None:
    result, calls = run_issue_step(tmp_path, "failure", json.dumps([{"number": 7}]))

    assert result.returncode == 0, result.stderr
    [_, commented] = calls
    assert commented[:3] == ["issue", "comment", "7"]
    assert commented[4].startswith(f"validate-dev failed on `{SHA}` ({TAG})")
    assert TOKEN not in "\0".join(part for call in calls for part in call)


def test_a_success_closes_the_open_issue(tmp_path: Path) -> None:
    result, calls = run_issue_step(tmp_path, "success", json.dumps([{"number": 7}]))

    assert result.returncode == 0, result.stderr
    assert calls[1] == [
        "issue",
        "close",
        "7",
        "--comment",
        f"validate-dev is green again on `{SHA}` ({TAG}): {RUN_LINK}",
        "--repo",
        REPOSITORY,
    ]


def test_a_success_with_no_issue_open_only_looks(tmp_path: Path) -> None:
    result, calls = run_issue_step(tmp_path, "success", "[]")

    assert result.returncode == 0, result.stderr
    assert calls == [[*LISTED, "--repo", REPOSITORY]]
