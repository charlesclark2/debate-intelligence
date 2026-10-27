"""`scripts/ci_test_selection.py`: which tests a `test` part of ci.yml runs (v1-e01-t38).

A pull request into dev runs the tests its changes reach; everything else runs the whole default
selection, and so does a pull request into dev whose selection cannot be trusted. The forbidden
outcome is fewer tests: a promotion, a push, a selection error or a missing base commit that runs
less than the whole selection.

Every case builds a small workspace in a temporary git repository, shaped the way GitHub checks a
pull request out: `BASE` is committed on `dev`, the change is committed on a branch, and HEAD is a
merge commit of the branch into `dev`, as on `refs/pull/N/merge`, whose first parent is the base.
The script runs in a subprocess with the workspace as its working directory, as CI runs it, and
the expected selections are written by hand from `BASE` (working agreement 6).
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ci_test_selection.py"

CORE = "packages/debate_core/src/debate_core"
CORE_TESTS = "packages/debate_core/tests"
ALWAYS = {
    "tests/architecture/test_layers.py",
    "tests/specs/test_specs.py",
    "packages/debate_cli/tests/test_app.py",
    "packages/debate_cli/tests/test_help_rendering.py",
}
A_PASSING_TEST = "def test_it():\n    pass\n"

BASE: dict[str, str] = {
    "pyproject.toml": (
        "[tool.pytest.ini_options]\n"
        'testpaths = ["packages/debate_core/tests", "packages/debate_cli/tests", "tests"]\n'
    ),
    "uv.lock": "version = 1\n",
    ".github/workflows/ci.yml": "name: ci\n",
    "conftest.py": "import pytest\n",
    f"{CORE}/__init__.py": "",
    f"{CORE}/domain.py": "VALUE = 1\n",
    f"{CORE}/service.py": "from debate_core.domain import VALUE\n\nDOUBLE = VALUE * 2\n",
    f"{CORE}/unrelated.py": "X = 1\n",
    f"{CORE_TESTS}/test_domain.py": "from debate_core.domain import VALUE\n\n\n" + A_PASSING_TEST,
    f"{CORE_TESTS}/test_service.py": "from debate_core.service import DOUBLE\n\n\n" + A_PASSING_TEST,
    f"{CORE_TESTS}/test_unrelated.py": "from debate_core.unrelated import X\n\n\n" + A_PASSING_TEST,
    **dict.fromkeys(ALWAYS, A_PASSING_TEST),
}
EVERY_TEST_FILE = {path for path in BASE if path.rpartition("/")[2].startswith("test_")}


@dataclass
class Ran:
    tests: list[str]
    summary: str
    stdout: str


def git(root: Path, *args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return completed.stdout.strip()


def write(root: Path, files: dict[str, str | None]) -> None:
    for path, text in files.items():
        if text is None:
            (root / path).unlink()
        else:
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_text(text, encoding="utf-8")


def pull_request(root: Path, change: dict[str, str | None], base: dict[str, str] = BASE) -> str:
    """A repository whose HEAD merges a branch with `change` into dev; returns dev's commit, the base."""
    root.mkdir()
    git(root, "init", "-q", "-b", "dev")
    git(root, "config", "user.email", "ci@example.invalid")
    git(root, "config", "user.name", "CI")
    write(root, dict(base))
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    base_sha = git(root, "rev-parse", "HEAD")
    git(root, "switch", "-q", "-c", "task")
    write(root, change)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "change")
    git(root, "switch", "-q", "--detach", "dev")
    git(root, "merge", "-q", "--no-ff", "-m", "Merge task into dev", "task")
    return base_sha


def run(
    root: Path,
    tmp_path: Path,
    *,
    event: str = "pull_request",
    base_branch: str = "dev",
    base_sha: str = "",
    ref_name: str = "7/merge",
) -> Ran:
    output = tmp_path / "selection.txt"
    output.write_text("left over from an earlier step\n", encoding="utf-8")
    summary = tmp_path / "summary.md"
    summary.write_text("", encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--event",
            event,
            "--base-branch",
            base_branch,
            "--base-sha",
            base_sha,
            "--ref-name",
            ref_name,
            "--output",
            str(output),
            "--summary",
            str(summary),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return Ran(
        output.read_text(encoding="utf-8").splitlines(), summary.read_text(encoding="utf-8"), completed.stdout
    )


def assert_whole(ran: Ran, why: str) -> None:
    assert ran.tests == [], "the whole selection is an empty file: pytest then runs every testpath"
    assert ran.summary.startswith("### Tests: the whole default selection\n"), ran.summary
    assert why in ran.summary, ran.summary
    assert ran.summary in ran.stdout


A_DOMAIN_CHANGE: dict[str, str | None] = {f"{CORE}/domain.py": "VALUE = 2\n"}
THE_DOMAIN_CHANGE_REACHES = {f"{CORE_TESTS}/test_domain.py", f"{CORE_TESTS}/test_service.py", *ALWAYS}


# --------------------------------------------------------------------------------------------
# A pull request into dev: the affected set
# --------------------------------------------------------------------------------------------


def test_a_pull_request_into_dev_runs_the_tests_its_change_reaches_and_the_always_run_list(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    base_sha = pull_request(root, A_DOMAIN_CHANGE)

    ran = run(root, tmp_path, base_sha=base_sha)

    assert set(ran.tests) == THE_DOMAIN_CHANGE_REACHES
    assert ran.tests == sorted(ran.tests)
    assert ran.summary.startswith("### Tests: the affected set\n"), ran.summary
    assert f"6 of {len(EVERY_TEST_FILE)} test files" in ran.summary
    assert f"against the base commit {base_sha[:12]}" in ran.summary
    assert all(f"- `{test}`" in ran.summary for test in THE_DOMAIN_CHANGE_REACHES)


def test_the_selection_is_the_changes_between_the_base_and_the_merge_not_the_whole_history(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    pull_request(root, {f"{CORE}/unrelated.py": "X = 2\n"})
    git(root, "switch", "-q", "dev")
    write(root, A_DOMAIN_CHANGE)
    git(root, "commit", "-q", "-am", "an earlier pull request")
    base_sha = git(root, "rev-parse", "HEAD")
    git(root, "merge", "-q", "--no-ff", "-m", "Merge task into dev", "task")

    ran = run(root, tmp_path, base_sha=base_sha)

    assert set(ran.tests) == {f"{CORE_TESTS}/test_unrelated.py", *ALWAYS}


def test_a_checkout_two_commits_deep_holds_the_base_and_selects_as_a_full_clone_does(tmp_path: Path) -> None:
    """ci.yml's test job checks out with fetch-depth 2: the merge commit and its parents."""
    source = tmp_path / "source"
    base_sha = pull_request(source, A_DOMAIN_CHANGE)
    shallow = tmp_path / "shallow"
    git(tmp_path, "clone", "-q", "--depth", "2", f"file://{source}", str(shallow))
    assert git(shallow, "rev-parse", "--is-shallow-repository") == "true"

    ran = run(shallow, tmp_path, base_sha=base_sha)

    assert set(ran.tests) == THE_DOMAIN_CHANGE_REACHES


# --------------------------------------------------------------------------------------------
# Every other event: the whole selection
# --------------------------------------------------------------------------------------------


def test_a_pull_request_into_main_is_a_promotion_and_runs_the_whole_selection(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    base_sha = pull_request(root, A_DOMAIN_CHANGE)

    ran = run(root, tmp_path, base_branch="main", base_sha=base_sha)

    assert_whole(ran, "because a pull request into main is a promotion, which runs the whole selection.")


@pytest.mark.parametrize("branch", ["dev", "main"])
def test_a_push_runs_the_whole_selection(tmp_path: Path, branch: str) -> None:
    root = tmp_path / "repo"
    base_sha = pull_request(root, A_DOMAIN_CHANGE)

    # A push carries no base branch; a base commit is given anyway, to show that it is not read.
    ran = run(root, tmp_path, event="push", base_branch="", base_sha=base_sha, ref_name=branch)

    assert_whole(ran, f"because a push to {branch} runs the whole selection.")


@pytest.mark.parametrize("event", ["workflow_dispatch", "schedule", ""])
def test_a_dispatched_run_or_any_other_event_runs_the_whole_selection(tmp_path: Path, event: str) -> None:
    root = tmp_path / "repo"
    base_sha = pull_request(root, A_DOMAIN_CHANGE)

    ran = run(root, tmp_path, event=event, base_branch="dev", base_sha=base_sha, ref_name="dev")

    assert_whole(ran, "runs the whole selection.")


# --------------------------------------------------------------------------------------------
# A pull request into dev whose selection cannot be trusted: the whole selection
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("shared", ["pyproject.toml", "uv.lock", ".github/workflows/ci.yml", "conftest.py"])
def test_shared_test_ground_runs_the_whole_selection_and_says_which_file(tmp_path: Path, shared: str) -> None:
    root = tmp_path / "repo"
    base_sha = pull_request(root, {**A_DOMAIN_CHANGE, shared: BASE[shared] + "\n"})

    ran = run(root, tmp_path, base_sha=base_sha)

    assert_whole(ran, f"because {shared} is shared test ground.")


@pytest.mark.parametrize("missing", ["", "0123456789abcdef0123456789abcdef01234567"])
def test_a_base_commit_missing_from_the_checkout_runs_the_whole_selection(
    tmp_path: Path, missing: str
) -> None:
    root = tmp_path / "repo"
    pull_request(root, A_DOMAIN_CHANGE)

    ran = run(root, tmp_path, base_sha=missing)

    assert_whole(
        ran,
        f"because the pull request's base commit {missing[:12] or '(none given)'} is not in the checkout.",
    )


def test_a_shallow_checkout_without_the_base_runs_the_whole_selection(tmp_path: Path) -> None:
    source = tmp_path / "source"
    base_sha = pull_request(source, A_DOMAIN_CHANGE)
    shallow = tmp_path / "shallow"
    git(tmp_path, "clone", "-q", "--depth", "1", f"file://{source}", str(shallow))

    ran = run(shallow, tmp_path, base_sha=base_sha)

    assert_whole(ran, f"because the pull request's base commit {base_sha[:12]} is not in the checkout.")


def test_a_selection_that_fails_runs_the_whole_selection(tmp_path: Path) -> None:
    """A base with no history in common with HEAD: `git merge-base` fails inside affected_tests."""
    root = tmp_path / "repo"
    pull_request(root, A_DOMAIN_CHANGE)
    empty_tree = git(root, "hash-object", "-t", "tree", "-w", "/dev/null")
    unrelated = git(root, "commit-tree", empty_tree, "-m", "a commit with no parent in common")

    ran = run(root, tmp_path, base_sha=unrelated)

    assert_whole(ran, "because the selection failed (affected_tests: git merge-base")


def test_an_empty_selection_when_python_changed_runs_the_whole_selection(tmp_path: Path) -> None:
    """Without an always-run list, a change no test reaches selects nothing; that is not trusted."""
    without_always_run = {path: text for path, text in BASE.items() if path not in ALWAYS}
    without_always_run.pop(f"{CORE_TESTS}/test_unrelated.py")
    root = tmp_path / "repo"
    base_sha = pull_request(root, {f"{CORE}/unrelated.py": "X = 2\n"}, base=without_always_run)

    ran = run(root, tmp_path, base_sha=base_sha)

    assert_whole(ran, "because the selection is empty, and 1 Python files changed.")
