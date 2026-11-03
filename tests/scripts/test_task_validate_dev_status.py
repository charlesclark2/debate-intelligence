"""`scripts/task ready` and `scripts/task list` show dev's latest validate-dev result (v1-e01-t34).

protect-main requires `validate-dev` green on a promotion's head commit. From 2026-10-20 it failed
on every dev pre-release for days and no one saw it, so the two views the operator and the PM read
most now print dev's head and its latest validate-dev status first. It comes from GitHub's combined
status for `dev`, read with `gh`; without `gh`, or when `gh` fails, the line says unknown and the
command still succeeds.

`task_helper.validate_dev_status` is tested on combined-status documents written by hand in the
shape `gh api repos/{owner}/{repo}/commits/dev/status` returned on 2026-10-22. The shell tests run
the real `scripts/task` in a throwaway repository with a local bare `origin`; `uv` and `gh` are
stubs, and for "gh is not installed" `PATH` is a sandbox of links to the ordinary tools the two
commands use, so the runner's own `gh` cannot be found. Nothing here reaches GitHub.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TASK_SCRIPT = REPO_ROOT / "scripts" / "task"
HELPER_SCRIPT = REPO_ROOT / "scripts" / "task_helper.py"

HEAD = "f809eca673" + "0" * 30
RUN = "https://github.com/charlesclark2/debate-intelligence/actions/runs/39893406822"


def load_helper() -> ModuleType:
    spec = importlib.util.spec_from_file_location("task_helper_for_status", HELPER_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


helper = load_helper()


def combined(*statuses: dict[str, str], sha: str = HEAD) -> str:
    return json.dumps(
        {
            "state": "pending" if not statuses else statuses[0]["state"],
            "sha": sha,
            "total_count": len(statuses),
            "statuses": list(statuses),
        }
    )


def status(state: str, context: str = "validate-dev") -> dict[str, str]:
    return {
        "context": context,
        "state": state,
        "target_url": RUN,
        "description": "validation failed: slow failure",
    }


# --------------------------------------------------------------------------------------------
# The line, from the combined status
# --------------------------------------------------------------------------------------------


def test_a_failure_names_the_head_the_run_and_what_it_blocks() -> None:
    assert helper.validate_dev_status(combined(status("failure"))) == (
        f"validate-dev: failure on dev f809eca  {RUN}\n"
        "  No promotion to main can merge until dev's head validates; the run says what failed."
    )


def test_a_success_and_a_pending_are_one_line() -> None:
    assert (
        helper.validate_dev_status(combined(status("success")))
        == f"validate-dev: success on dev f809eca  {RUN}"
    )
    assert (
        helper.validate_dev_status(combined(status("pending")))
        == f"validate-dev: pending on dev f809eca  {RUN}"
    )


def test_a_cancelled_run_is_red_too() -> None:
    assert helper.validate_dev_status(combined(status("error"))).startswith(
        f"validate-dev: error on dev f809eca  {RUN}\n  No promotion to main can merge"
    )


def test_a_head_with_no_validate_dev_status_yet_says_so() -> None:
    assert helper.validate_dev_status(combined(status("success", context="ci"))) == (
        "validate-dev: none yet on dev f809eca (its pre-release may still be building)"
    )
    assert helper.validate_dev_status(combined()) == (
        "validate-dev: none yet on dev f809eca (its pre-release may still be building)"
    )


@pytest.mark.parametrize(
    "document",
    ["", "not json", "[]", json.dumps({"message": "Not Found"}), json.dumps({"sha": HEAD, "statuses": None})],
    ids=["nothing", "not json", "a list", "an error document", "no statuses"],
)
def test_anything_unreadable_is_unknown(document: str) -> None:
    assert (
        helper.validate_dev_status(document)
        == "validate-dev: unknown (gh could not read dev's commit status)"
    )


# --------------------------------------------------------------------------------------------
# scripts/task ready and list, with gh answering, failing and missing
# --------------------------------------------------------------------------------------------

UV_STUB = """#!/usr/bin/env bash
if [ "${{1:-}}" = run ]; then
  shift
  [ "${{1:-}}" = --quiet ] && shift
  script="$1"; shift
  exec "{python}" "$script" "$@"
fi
exit 0
"""

GH_STUB = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$GH_CALLS"
if [ "${1:-}" = api ]; then
  [ "$GH_STATUS_EXIT" = 0 ] || { echo "HTTP 502" >&2; exit "$GH_STATUS_EXIT"; }
  printf '%s' "$GH_STATUS"
  exit 0
fi
exit 1
"""

#: What `ready` and `list` run besides git, uv and gh, linked into the sandbox PATH.
ORDINARY_TOOLS = (
    "bash",
    "env",
    "git",
    "mktemp",
    "tar",
    "rm",
    "sed",
    "sort",
    "tr",
    "awk",
    "cut",
    "dirname",
    "basename",
    "cat",
    "grep",
    "head",
    "mkdir",
)

SPEC = """# TASK v1-e99-t01-ready-task - A task ready to start
---
apiVersion: planspec.io/v1alpha1
kind: Goal
metadata:
  name: v1-e99-t01-ready-task
  namespace: debate-intelligence
  labels:
    planspec.io/kind: task
    debate/major-version: v1
    debate/release: v1.0
    debate/epic: v1-e99-fixture
  annotations:
    debate/title: "A task ready to start"
spec:
  description: A fixture task.
status:
  phase: Pending
"""


def write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


@pytest.fixture
def operator(tmp_path: Path) -> dict[str, Path | dict[str, str]]:
    """The operator's main clone on dev with a bare origin, stub uv and gh, and a no-gh PATH."""
    tmp_path = tmp_path.resolve()
    stubs, sandbox = tmp_path / "stubs", tmp_path / "sandbox"
    stubs.mkdir()
    sandbox.mkdir()
    write_executable(stubs / "uv", UV_STUB.format(python=sys.executable))
    write_executable(stubs / "gh", GH_STUB)
    for tool in ORDINARY_TOOLS:
        found = shutil.which(tool)
        assert found, f"{tool} is not on this machine's PATH"
        (sandbox / tool).symlink_to(found)
    (sandbox / "uv").symlink_to(stubs / "uv")

    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text(
        "[user]\n\tname = Fixture Operator\n\temail = operator@example.invalid\n"
        "[init]\n\tdefaultBranch = dev\n[commit]\n\tgpgsign = false\n"
    )
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(
        GIT_CONFIG_GLOBAL=str(gitconfig),
        GIT_CONFIG_NOSYSTEM="1",
        DEBATE_WORKTREES=str(tmp_path / "worktrees"),
        DEBATE_TASK_LAUNCHER="none",
        GH_CALLS=str(tmp_path / "gh-calls.log"),
        GH_STATUS=combined(status("failure")),
        GH_STATUS_EXIT="0",
    )

    main = tmp_path / "debate-intelligence"
    (main / "scripts").mkdir(parents=True)
    shutil.copy2(TASK_SCRIPT, main / "scripts" / "task")
    shutil.copy2(HELPER_SCRIPT, main / "scripts" / "task_helper.py")
    (main / "docs" / "process").mkdir(parents=True)
    (main / "docs" / "process" / "README.md").write_text("process\n")
    (main / "plan_specs" / "v1" / "e99-fixture").mkdir(parents=True)
    (main / "plan_specs" / "v1" / "e99-fixture" / "t01-ready-task.yaml").write_text(SPEC)

    def git(*args: str, cwd: Path = main) -> None:
        subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, check=True)

    git("init", "--quiet", "--bare", str(tmp_path / "origin.git"), cwd=tmp_path)
    git("init", "--quiet")
    git("add", "-A")
    git("commit", "--quiet", "-m", "dev")
    git("remote", "add", "origin", str(tmp_path / "origin.git"))
    git("push", "--quiet", "-u", "origin", "dev")
    return {
        "main": main,
        "stubs": stubs,
        "sandbox": sandbox,
        "env": env,
        "gh_calls": tmp_path / "gh-calls.log",
    }


def run_task(operator: dict, command: str, *, path: str, **env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(operator["main"] / "scripts" / "task"), command],
        cwd=operator["main"],
        env={**operator["env"], "PATH": path, **env},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def with_gh(operator: dict) -> str:
    return f"{operator['stubs']}{os.pathsep}{operator['sandbox']}"


@pytest.mark.parametrize("command", ["ready", "list"])
def test_the_view_starts_with_dev_s_head_and_its_validate_dev_status(operator: dict, command: str) -> None:
    result = run_task(operator, command, path=with_gh(operator))

    assert result.returncode == 0, result.stderr
    assert f"validate-dev: failure on dev f809eca  {RUN}\n  No promotion to main can merge" in result.stdout
    assert "api repos/{owner}/{repo}/commits/dev/status" in operator["gh_calls"].read_text()
    rest = "v1-e99-t01-ready-task" if command == "ready" else "(no active task worktrees)"
    assert result.stdout.index("validate-dev:") < result.stdout.index(rest)


@pytest.mark.parametrize("command", ["ready", "list"])
def test_a_failing_gh_says_unknown_and_the_command_still_succeeds(operator: dict, command: str) -> None:
    result = run_task(operator, command, path=with_gh(operator), GH_STATUS_EXIT="1")

    assert result.returncode == 0, result.stderr
    assert "validate-dev: unknown (gh could not read dev's commit status)\n" in result.stdout


@pytest.mark.parametrize("command", ["ready", "list"])
def test_without_gh_it_says_unknown_and_the_command_still_succeeds(operator: dict, command: str) -> None:
    result = run_task(operator, command, path=str(operator["sandbox"]))

    assert result.returncode == 0, result.stderr
    assert "validate-dev: unknown (gh is not installed)\n" in result.stdout
    assert not operator["gh_calls"].exists()
