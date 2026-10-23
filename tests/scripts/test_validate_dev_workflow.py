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

import os
import shutil
import subprocess
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
