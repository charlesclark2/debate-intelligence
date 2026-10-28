"""The site-only step of promotion-guard.yml, run as the runner runs it (v1-e37-t09).

promotion-guard.yml runs only on pull requests into main, so no task pull request into dev
exercises it. These tests run the step's own `run:` text with bash, in a throwaway repository with
an `origin/main`, against the branch shapes the site lane has to refuse or accept. Nothing here
reaches GitHub.
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
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "promotion-guard.yml"


def promotion_source() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["promotion-source"]


def step_named(name: str) -> dict[str, Any]:
    [step] = [step for step in promotion_source()["steps"] if step.get("name") == name]
    return step


SITE_ONLY = "A site branch changes only site content, pages and assets"


def test_the_promotion_source_job_checks_out_full_history_and_fetches_main_before_the_site_step() -> None:
    steps = promotion_source()["steps"]
    names = [step.get("name") for step in steps]

    assert steps[0]["with"] == {"persist-credentials": False, "fetch-depth": 0}
    assert names.index("Fetch main") < names.index(SITE_ONLY)
    assert (
        step_named("Fetch main")["run"]
        == "git fetch --no-tags origin +refs/heads/main:refs/remotes/origin/main"
    )
    site_only = step_named(SITE_ONLY)
    assert site_only["if"] == "${{ !cancelled() }}"
    assert site_only["env"] == {
        "HEAD_REF": "${{ github.head_ref }}",
        "HEAD_SHA": "${{ github.event.pull_request.head.sha }}",
    }
    assert "${{" not in site_only["run"]


@pytest.fixture
def clone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A clone whose origin has main (with the guard script and a site) and dev one task ahead."""
    for name in list(os.environ):
        if name.startswith("GIT_"):
            monkeypatch.delenv(name)
    for name, value in {
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.test",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.test",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
    }.items():
        monkeypatch.setenv(name, value)
    origin = tmp_path / "origin"
    (origin / "scripts").mkdir(parents=True)
    (origin / "site" / "content").mkdir(parents=True)
    shutil.copy2(REPO_ROOT / "scripts" / "check_promotion_source.py", origin / "scripts")
    (origin / "site" / "content" / "results.yaml").write_text("results: []\n", encoding="utf-8")
    (origin / "site" / "package.json").write_text("{}\n", encoding="utf-8")
    git(origin, "init", "-q", "-b", "main")
    git(origin, "add", "-A")
    git(origin, "commit", "-q", "-m", "Base")
    git(origin, "switch", "-q", "-c", "dev")
    (origin / "packages.py").write_text("x = 1\n", encoding="utf-8")
    git(origin, "add", "-A")
    git(origin, "commit", "-q", "-m", "A task on dev")
    git(origin, "switch", "-q", "main")
    work = tmp_path / "work"
    git(tmp_path, "clone", "-q", str(origin), str(work))
    git(work, "fetch", "-q", "origin", "dev:refs/remotes/origin/dev")
    return work


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def branch(work: Path, name: str, files: dict[str, str]) -> str:
    git(work, "switch", "-q", "-c", name, "origin/main")
    for path, text in files.items():
        (work / path).parent.mkdir(parents=True, exist_ok=True)
        (work / path).write_text(text, encoding="utf-8")
    if files:
        git(work, "add", "-A")
        git(work, "commit", "-q", "-m", f"Change on {name}")
    return git(work, "rev-parse", "HEAD").strip()


def run_site_step(work: Path, head_ref: str, head_sha: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-e", "-c", step_named(SITE_ONLY)["run"]],
        cwd=work,
        env={"PATH": os.environ["PATH"], "HEAD_REF": head_ref, "HEAD_SHA": head_sha},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_the_step_passes_a_results_change(clone: Path) -> None:
    sha = branch(clone, "site/results", {"site/content/results.yaml": "results: [ronald-reagan]\n"})
    result = run_site_step(clone, "site/results", sha)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.startswith("OK: Every one of the 1 changed path(s) is under `site/`")


@pytest.mark.parametrize(
    ("name", "files", "named"),
    [
        (
            "site/and-a-script",
            {"site/content/results.yaml": "r\n", "scripts/site_deploy.sh": "x\n"},
            "scripts/site_deploy.sh",
        ),
        ("site/a-dependency", {"site/package.json": '{"dependencies": {}}\n'}, "site/package.json"),
        ("site/nothing", {}, "changes nothing"),
    ],
    ids=["touches-scripts", "touches-site-package-json", "empty-diff"],
)
def test_the_step_refuses_the_three_branches_the_pm_named(
    clone: Path, name: str, files: dict[str, str], named: str
) -> None:
    sha = branch(clone, name, files)
    result = run_site_step(clone, name, sha)
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.startswith("FAILED: ")
    assert named in result.stdout


def test_the_step_refuses_a_site_branch_that_merged_dev(clone: Path) -> None:
    branch(clone, "site/with-dev", {"site/content/results.yaml": "r\n"})
    git(clone, "merge", "-q", "--no-ff", "-m", "Merge dev", "origin/dev")
    result = run_site_step(clone, "site/with-dev", git(clone, "rev-parse", "HEAD").strip())
    assert result.returncode == 1
    assert "  packages.py\n" in result.stdout


@pytest.mark.parametrize("head", ["dev", "hotfix/login-crash"])
def test_the_step_leaves_a_promotion_or_a_hotfix_alone(clone: Path, head: str) -> None:
    result = run_site_step(clone, head, "0" * 40)  # a SHA git would refuse: it is never asked
    assert result.returncode == 0
    assert result.stdout == f"OK: `{head}` is not a site branch; nothing to check.\n"
