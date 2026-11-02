"""Tests for `scripts/check_stable_release.py`: what a stable tag must be before it is built (v1-e09-t06).

The release workflow runs only when a `vX.Y.Z` tag is pushed to GitHub, so no pull request runs it;
these tests are the evidence each refusal works before the first stable release. A tag is checked
against a checkout (its pyprojects, CHANGELOG.md and spec tree, written under tmp_path), the commit
graph and GitHub. The graph and GitHub are fakes here, except in the last sections, which run real
git on a repository built under tmp_path and feed `gh api`'s JSON to the real client. Every expected
message is written by hand.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from tests.scripts.spec_graph_tree import Epic, SpecTree, Task

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_stable_release as csr  # noqa: E402

REPOSITORY = "charlesclark2/debate-intelligence"
MERGE = "a" * 40
MAIN_PARENT = "b" * 40
DEV_PARENT = "c" * 40
OLDER_MAIN = "d" * 40
TAG = "v1.5.0"

FILLED_CHANGELOG = """\
# Changelog

Intro.

## v1.5.0: V1 quality gate & team pilot

Tagged on `main`.

### For students and coaches

* One command installs it.

## v1.4.0: Federated research from the CLI

Not yet released.
"""


# --------------------------------------------------------------------------------------------
# The checkout: pyprojects, CHANGELOG.md and the spec tree
# --------------------------------------------------------------------------------------------


def write_checkout(
    root: Path,
    *,
    version: str = "1.5.0",
    changelog: str = FILLED_CHANGELOG,
    e09_phase: str = "Succeeded",
    e42_phase: str = "Succeeded",
) -> Path:
    for relative in (*csr.release_version.WORKSPACE_PYPROJECTS, csr.release_version.VERSION_SOURCE):
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_text(f'[project]\nname = "x"\nversion = "{version}"\n', encoding="utf-8")
    (root / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    SpecTree(
        # v1.6 has a spec and no epic yet.
        releases={"v1.4": "Succeeded", "v1.5": "Pending", "v1.6": "Pending"},
        epics=[
            Epic("e08", "research", "v1.4", [Task("t01", "search", phase="Succeeded")], phase="Succeeded"),
            Epic(
                "e09", "quality-pilot", "v1.5", [Task("t01", "packaging", phase="Succeeded")], phase=e09_phase
            ),
            Epic(
                "e42", "pilot-upkeep", "v1.5", [Task("t01", "feedback", phase="Succeeded")], phase=e42_phase
            ),
        ],
    ).write(root)
    return root


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    return write_checkout(tmp_path / "checkout")


# --------------------------------------------------------------------------------------------
# Fakes for the commit graph and GitHub
# --------------------------------------------------------------------------------------------


@dataclass
class FakeHistory:
    main_line: set[str] = field(default_factory=lambda: {MERGE, OLDER_MAIN})
    parent_map: dict[str, list[str]] = field(default_factory=lambda: {MERGE: [MAIN_PARENT, DEV_PARENT]})

    def first_parent_line(self, ref: str) -> set[str]:
        assert ref == "origin/main"
        return self.main_line

    def parents(self, sha: str) -> list[str]:
        return self.parent_map.get(sha, [OLDER_MAIN])


def promotion(**changes: object) -> csr.PullRequest:
    values: dict[str, object] = {
        "number": 812,
        "merged": True,
        "merge_commit_sha": MERGE,
        "base_ref": "main",
        "head_ref": "dev",
        "head_sha": DEV_PARENT,
        "head_repo": REPOSITORY,
    }
    values.update(changes)
    return csr.PullRequest(**values)  # pyright: ignore[reportArgumentType]


def run(status: str = "completed", conclusion: str = "success", branch: str = "main") -> csr.WorkflowRun:
    return csr.WorkflowRun(
        run_id=99, head_branch=branch, status=status, conclusion=conclusion, url="https://github.com/run/99"
    )


@dataclass
class FakeGitHub:
    pulls: list[csr.PullRequest] = field(default_factory=lambda: [promotion()])
    commit_statuses: list[csr.CommitStatus] = field(
        default_factory=lambda: [csr.CommitStatus("validate-dev", "success", "github-actions[bot]")]
    )
    #: each poll of ci_push_runs takes the next list; the last one repeats
    runs: list[list[csr.WorkflowRun]] = field(default_factory=lambda: [[run()]])
    polls: int = 0
    asked_statuses_of: list[str] = field(default_factory=list)

    def pull_requests_of(self, sha: str) -> list[csr.PullRequest]:
        assert sha == MERGE
        return self.pulls

    def statuses(self, sha: str) -> list[csr.CommitStatus]:
        self.asked_statuses_of.append(sha)
        return self.commit_statuses

    def ci_push_runs(self, sha: str) -> list[csr.WorkflowRun]:
        assert sha == MERGE
        self.polls += 1
        return self.runs[min(self.polls, len(self.runs)) - 1]


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def outcomes(
    checkout: Path,
    *,
    tag: str = TAG,
    history: FakeHistory | None = None,
    github: FakeGitHub | None = None,
    wait_seconds: float = 0,
    clock: FakeClock | None = None,
) -> dict[str, csr.Outcome]:
    clock = clock or FakeClock()
    results = csr.run_checks(
        tag=tag,
        sha=MERGE,
        repository=REPOSITORY,
        root=checkout,
        history=history or FakeHistory(),
        github=github or FakeGitHub(),
        main_ref="origin/main",
        wait_seconds=wait_seconds,
        sleep=clock.sleep,
        clock=clock,
    )
    named = {outcome.check: outcome for outcome in results}
    assert len(named) == len(results), "a check reported twice"
    return named


def refused(results: dict[str, csr.Outcome]) -> dict[str, str]:
    return {name: outcome.detail for name, outcome in results.items() if not outcome.passed}


# --------------------------------------------------------------------------------------------
# A validated promotion passes every check
# --------------------------------------------------------------------------------------------


def test_a_validated_promotion_on_main_passes_every_check(checkout: Path) -> None:
    results = outcomes(checkout)

    assert list(results) == [
        "stable-tag",
        "version",
        "epics",
        "changelog",
        "on-main",
        "promotion-merge",
        "validate-dev",
        "full-suite",
    ]
    assert refused(results) == {}


def test_validate_dev_is_read_from_the_dev_parent_not_the_merge(checkout: Path) -> None:
    github = FakeGitHub()
    outcomes(checkout, github=github)

    assert github.asked_statuses_of == [DEV_PARENT]


# --------------------------------------------------------------------------------------------
# stable-tag: only vX.Y.Z, never a dev pre-release tag
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("tag", ["v1.5.0-dev.3", "v1.5", "1.5.0", "v1.5.0-rc.1", "v01.5.0", "vnext"])
def test_a_tag_that_is_not_vxyz_is_refused_and_nothing_else_is_checked(checkout: Path, tag: str) -> None:
    results = outcomes(checkout, tag=tag)

    assert refused(results) == {
        "stable-tag": f"{tag!r} is not a stable tag vX.Y.Z; dev pre-releases (vX.Y.Z-dev.N) are published "
        "by dev-prerelease.yml, and nothing else is released"
    }
    assert list(results) == ["stable-tag"]


# --------------------------------------------------------------------------------------------
# version: the tag names the version source, and the workspace agrees with it
# --------------------------------------------------------------------------------------------


def test_a_tag_that_does_not_name_the_package_version_is_refused(tmp_path: Path) -> None:
    checkout = write_checkout(tmp_path, version="1.4.2")

    assert refused(outcomes(checkout))["version"] == (
        "v1.5.0 does not name packages/debate_cli/pyproject.toml's version 1.4.2"
    )


def test_a_workspace_pyproject_off_the_version_source_is_refused(checkout: Path) -> None:
    (checkout / "packages/debate_core/pyproject.toml").write_text(
        '[project]\nname = "debate-core"\nversion = "1.4.0"\n', encoding="utf-8"
    )

    assert refused(outcomes(checkout))["version"] == (
        "packages/debate_core/pyproject.toml has version 1.4.0, but packages/debate_cli/pyproject.toml "
        "(the version source) has 1.5.0"
    )


def test_a_patch_tag_names_its_patch_version(tmp_path: Path) -> None:
    checkout = write_checkout(
        tmp_path, version="1.5.1", changelog=FILLED_CHANGELOG.replace("v1.5.0", "v1.5.1")
    )

    assert refused(outcomes(checkout, tag="v1.5.1")) == {}


# --------------------------------------------------------------------------------------------
# epics: the release spec's epics are Succeeded
# --------------------------------------------------------------------------------------------


def test_a_release_whose_epic_is_not_succeeded_is_refused_naming_it(tmp_path: Path) -> None:
    checkout = write_checkout(tmp_path, e42_phase="InProgress")

    assert refused(outcomes(checkout)) == {
        "epics": "plan_specs/releases/v1.5.yaml: v1-e42-pilot-upkeep is InProgress"
    }


def test_every_unfinished_epic_is_named(tmp_path: Path) -> None:
    checkout = write_checkout(tmp_path, e09_phase="Pending", e42_phase="Blocked")

    assert refused(outcomes(checkout))["epics"] == (
        "plan_specs/releases/v1.5.yaml: v1-e09-quality-pilot is Pending; v1-e42-pilot-upkeep is Blocked"
    )


def test_a_tag_with_no_release_spec_is_refused(tmp_path: Path) -> None:
    checkout = write_checkout(
        tmp_path, version="1.7.0", changelog=FILLED_CHANGELOG.replace("v1.5.0", "v1.7.0")
    )

    assert refused(outcomes(checkout, tag="v1.7.0")) == {
        "epics": "no release spec plan_specs/releases/v1.7.yaml for v1.7.0"
    }


def test_a_release_spec_that_lists_no_epics_is_refused(tmp_path: Path) -> None:
    """Nothing to be Succeeded is not every epic Succeeded."""
    checkout = write_checkout(
        tmp_path, version="1.6.0", changelog=FILLED_CHANGELOG.replace("v1.5.0", "v1.6.0")
    )

    assert refused(outcomes(checkout, tag="v1.6.0")) == {
        "epics": "plan_specs/releases/v1.6.yaml lists no epics"
    }


def test_the_epics_check_is_validate_specs_require_succeeded(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rule is the command's, not a copy of it: each epic is asked of validate_specs.main."""
    asked: list[Sequence[str]] = []

    def main(argv: Sequence[str]) -> int:
        asked.append(list(argv))
        return 0

    monkeypatch.setattr(csr.validate_specs, "main", main)

    assert csr.check_epics(TAG, checkout).passed
    assert asked == [
        ["--root", str(checkout), "--require-succeeded", "v1-e09-quality-pilot"],
        ["--root", str(checkout), "--require-succeeded", "v1-e42-pilot-upkeep"],
    ]


@pytest.mark.parametrize(("tag", "release"), [("v1.5.0", "v1.5"), ("v1.5.12", "v1.5"), ("v2.0.3", "v2.0")])
def test_a_stable_tag_belongs_to_its_minor_release(tag: str, release: str) -> None:
    assert csr.release_of(tag) == release


# --------------------------------------------------------------------------------------------
# changelog: the release notes exist and are written
# --------------------------------------------------------------------------------------------


def test_a_tag_whose_changelog_section_is_not_yet_released_is_refused(tmp_path: Path) -> None:
    checkout = write_checkout(
        tmp_path, changelog="# Changelog\n\n## v1.5.0: V1 quality gate & team pilot\n\nNot yet released.\n"
    )

    assert refused(outcomes(checkout)) == {
        "changelog": "CHANGELOG.md's v1.5.0 section still says 'Not yet released'; write it before tagging"
    }


@pytest.mark.parametrize(
    "changelog",
    [
        "# Changelog\n\n## v1.4.0: Earlier\n\nNotes.\n",
        "# Changelog\n\n## v1.5.01: Not this one\n\nNotes.\n",
        "# Changelog\n\n### v1.5.0: Too deep\n\nNotes.\n",
    ],
)
def test_a_tag_with_no_changelog_section_is_refused(tmp_path: Path, changelog: str) -> None:
    checkout = write_checkout(tmp_path, changelog=changelog)

    assert refused(outcomes(checkout)) == {
        "changelog": "CHANGELOG.md has no `## v1.5.0` section for the release notes"
    }


def test_the_notes_are_the_section_s_body_up_to_the_next_release(
    checkout: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert csr.main(["notes", "--tag", TAG, "--root", str(checkout)]) == 0

    assert capsys.readouterr().out == (
        "Tagged on `main`.\n\n### For students and coaches\n\n* One command installs it.\n"
    )


def test_notes_for_an_unwritten_section_are_refused(
    checkout: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert csr.main(["notes", "--tag", "v1.4.0", "--root", str(checkout)]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "still says 'Not yet released'" in captured.err


def test_the_committed_changelog_has_a_section_for_each_v1_release() -> None:
    """ac4: v1.0 through v1.5, each linking its release spec; only v1.0.0 is written yet."""
    text = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    for minor in range(6):
        section = csr.changelog_section(text, f"v1.{minor}.0")
        assert section is not None, f"no v1.{minor}.0 section"
        assert f"plan_specs/releases/v1.{minor}.yaml" in section[1]
        assert (csr.NOT_YET_RELEASED in section[1]) == (minor > 0)


# --------------------------------------------------------------------------------------------
# on-main and promotion-merge: the merge commit of a dev → main promotion
# --------------------------------------------------------------------------------------------


def test_a_commit_main_never_pointed_at_is_refused(checkout: Path) -> None:
    history = FakeHistory(main_line={OLDER_MAIN})

    assert refused(outcomes(checkout, history=history))["on-main"] == (
        f"{MERGE} is not a commit main has pointed at (origin/main, first parents): a stable tag goes on "
        "the merge commit of a promotion into main, never on a dev or task commit"
    )


def test_a_commit_with_one_parent_is_not_a_promotion(checkout: Path) -> None:
    history = FakeHistory(parent_map={MERGE: [MAIN_PARENT]})

    results = refused(outcomes(checkout, history=history))

    assert results == {
        "promotion-merge": f"{MERGE} has 1 parent(s), so it is not the merge commit of a promotion; a "
        "dev → main promotion is merged with a merge commit",
        "validate-dev": "not checked: the commit is not a promotion merge",
    }


def test_a_merge_no_pull_request_made_is_refused(checkout: Path) -> None:
    github = FakeGitHub(pulls=[promotion(merged=False), promotion(number=700, merge_commit_sha=OLDER_MAIN)])

    assert refused(outcomes(checkout, github=github))["promotion-merge"] == (
        f"no merged pull request has {MERGE} as its merge commit"
    )


@pytest.mark.parametrize(
    ("changes", "where"),
    [
        ({"head_ref": "hotfix/login"}, f"#812 merged {REPOSITORY}:hotfix/login into main"),
        ({"head_ref": "site/results"}, f"#812 merged {REPOSITORY}:site/results into main"),
        (
            {"head_repo": "someone/debate-intelligence"},
            "#812 merged someone/debate-intelligence:dev into main",
        ),
        (
            {"base_ref": "dev", "head_ref": "task/v1-e09-t06"},
            f"#812 merged {REPOSITORY}:task/v1-e09-t06 into dev",
        ),
    ],
)
def test_a_merge_that_is_not_a_promotion_of_dev_into_main_is_refused(
    checkout: Path, changes: dict[str, str], where: str
) -> None:
    github = FakeGitHub(pulls=[promotion(**changes)])

    assert refused(outcomes(checkout, github=github))["promotion-merge"] == (
        f"{where}; only a promotion of {REPOSITORY}:dev into main is released (a hotfix or site change "
        "reaches a release through the next promotion)"
    )


def test_a_promotion_whose_head_is_not_the_dev_parent_is_refused(checkout: Path) -> None:
    github = FakeGitHub(pulls=[promotion(head_sha=OLDER_MAIN)])

    assert refused(outcomes(checkout, github=github))["promotion-merge"] == (
        f"#812 merged {REPOSITORY}:dev into main, but its head {OLDER_MAIN} is not {MERGE}'s second parent "
        f"{DEV_PARENT}"
    )


# --------------------------------------------------------------------------------------------
# validate-dev: green on the dev parent, posted by GitHub Actions
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("statuses", "message"),
    [
        ([], f"the dev parent {DEV_PARENT} has no validate-dev status"),
        (
            [csr.CommitStatus("ci", "success", "github-actions[bot]")],
            f"the dev parent {DEV_PARENT} has no validate-dev status",
        ),
        (
            [
                csr.CommitStatus("validate-dev", "failure", "github-actions[bot]"),
                csr.CommitStatus("validate-dev", "success", "github-actions[bot]"),
            ],
            f"the newest validate-dev status on the dev parent {DEV_PARENT} is failure",
        ),
        (
            [csr.CommitStatus("validate-dev", "pending", "github-actions[bot]")],
            f"the newest validate-dev status on the dev parent {DEV_PARENT} is pending",
        ),
        (
            [
                csr.CommitStatus("validate-dev", "success", "charlesclark2"),
                csr.CommitStatus("validate-dev", "failure", "github-actions[bot]"),
            ],
            f"the newest validate-dev status on {DEV_PARENT} was posted by charlesclark2, "
            "not github-actions[bot]",
        ),
    ],
)
def test_a_dev_parent_without_a_green_validate_dev_is_refused(
    checkout: Path, statuses: list[csr.CommitStatus], message: str
) -> None:
    github = FakeGitHub(commit_statuses=statuses)

    assert refused(outcomes(checkout, github=github)) == {"validate-dev": message}


def test_only_the_newest_validate_dev_status_counts(checkout: Path) -> None:
    github = FakeGitHub(
        commit_statuses=[
            csr.CommitStatus("smoke", "failure", "github-actions[bot]"),
            csr.CommitStatus("validate-dev", "success", "github-actions[bot]"),
            csr.CommitStatus("validate-dev", "failure", "github-actions[bot]"),
        ]
    )

    assert refused(outcomes(checkout, github=github)) == {}


# --------------------------------------------------------------------------------------------
# full-suite: CI's push run on main for the commit, waited for while it runs
# --------------------------------------------------------------------------------------------


def test_a_commit_with_no_ci_push_run_on_main_is_refused(checkout: Path) -> None:
    github = FakeGitHub(runs=[[run(branch="dev")]])

    assert refused(outcomes(checkout, github=github)) == {
        "full-suite": f"CI (ci.yml) has no push run on main for {MERGE}, so the whole test selection "
        "never ran on it"
    }


@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "timed_out"])
def test_a_ci_push_run_that_did_not_pass_is_refused(checkout: Path, conclusion: str) -> None:
    github = FakeGitHub(runs=[[run(conclusion=conclusion), run()]])

    assert refused(outcomes(checkout, github=github)) == {
        "full-suite": f"CI's push run on main for {MERGE} concluded {conclusion}: https://github.com/run/99"
    }


def test_a_ci_push_run_in_progress_is_waited_for(checkout: Path) -> None:
    github = FakeGitHub(
        runs=[[run(status="in_progress", conclusion="")], [run(status="queued", conclusion="")], [run()]]
    )
    clock = FakeClock()

    results = outcomes(checkout, github=github, wait_seconds=600, clock=clock)

    assert refused(results) == {}
    assert results["full-suite"].detail == "CI's push run on main passed: https://github.com/run/99"
    assert (github.polls, clock.sleeps) == (3, [30, 30])


def test_a_ci_push_run_still_running_at_the_deadline_is_refused(checkout: Path) -> None:
    github = FakeGitHub(runs=[[run(status="in_progress", conclusion="")]])
    clock = FakeClock()

    results = outcomes(checkout, github=github, wait_seconds=90, clock=clock)

    assert refused(results) == {
        "full-suite": f"CI's push run on main for {MERGE} is still in_progress after the wait: "
        "https://github.com/run/99; re-run this workflow once it has passed"
    }
    assert clock.sleeps == [30, 30, 30]


# --------------------------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------------------------


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch) -> FakeGitHub:
    github = FakeGitHub()
    monkeypatch.setattr(csr, "GhCli", lambda repository: github)
    monkeypatch.setattr(csr, "GitHistory", lambda root: FakeHistory())
    return github


def check_command(checkout: Path, tag: str = TAG) -> list[str]:
    return [
        "check",
        "--tag",
        tag,
        "--sha",
        MERGE,
        "--repository",
        REPOSITORY,
        "--root",
        str(checkout),
        "--wait-minutes",
        "0",
    ]


def test_a_passing_check_writes_its_outputs_and_summary(
    checkout: Path, wired: FakeGitHub, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "output"))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "summary"))

    assert csr.main(check_command(checkout)) == 0

    assert (tmp_path / "output").read_text(encoding="utf-8") == f"tag=v1.5.0\nversion=1.5.0\nsha={MERGE}\n"
    assert "| full-suite | pass |" in (tmp_path / "summary").read_text(encoding="utf-8")


def test_a_refused_check_exits_1_names_every_refusal_and_writes_no_outputs(
    tmp_path: Path, wired: FakeGitHub, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    checkout = write_checkout(tmp_path / "checkout", version="1.4.2", e09_phase="InProgress")
    wired.commit_statuses = []
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "output"))

    assert csr.main(check_command(checkout)) == 1

    captured = capsys.readouterr()
    assert "v1.5.0 is not released: version, epics, validate-dev refused" in captured.err
    assert "REFUSED version: v1.5.0 does not name" in captured.out
    assert not (tmp_path / "output").exists()


def test_a_check_that_cannot_run_exits_2(checkout: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Broken(FakeGitHub):
        def pull_requests_of(self, sha: str) -> list[csr.PullRequest]:
            raise csr.CheckError("gh api failed: HTTP 403")

    monkeypatch.setattr(csr, "GhCli", lambda repository: Broken())
    monkeypatch.setattr(csr, "GitHistory", lambda root: FakeHistory())

    assert csr.main(check_command(checkout)) == 2


def test_a_short_sha_is_refused_before_anything_is_read(checkout: Path, wired: FakeGitHub) -> None:
    assert csr.main(["check", "--tag", TAG, "--sha", "abc1234", "--repository", REPOSITORY]) == 2
    assert wired.polls == 0


# --------------------------------------------------------------------------------------------
# Real git: main's first-parent line and a promotion's parents
# --------------------------------------------------------------------------------------------


def git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        capture_output=True,
        text=True,
        check=True,
        env={
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.invalid",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.invalid",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "HOME": str(repository),
            "PATH": os.environ["PATH"],
        },
    ).stdout.strip()


def commit(repository: Path, message: str) -> str:
    git(repository, "commit", "-q", "--allow-empty", "-m", message)
    return git(repository, "rev-parse", "HEAD")


def test_git_history_reads_main_s_first_parent_line_and_a_merge_s_parents(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    git(repository, "init", "-q", "-b", "main")
    root = commit(repository, "root")
    git(repository, "switch", "-q", "-c", "dev")
    dev_commit = commit(repository, "a task merged into dev")
    git(repository, "switch", "-q", "main")
    hotfix = commit(repository, "a hotfix on main")
    git(repository, "merge", "-q", "--no-ff", "-m", "Merge pull request #812 from owner/dev", "dev")
    merge = git(repository, "rev-parse", "HEAD")

    history = csr.GitHistory(repository)

    assert history.first_parent_line("main") == {root, hotfix, merge}
    assert history.parents(merge) == [hotfix, dev_commit]
    assert history.parents(root) == []


def test_git_history_refuses_a_shallow_clone(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    git(source, "init", "-q", "-b", "main")
    commit(source, "one")
    commit(source, "two")
    shallow = tmp_path / "shallow"
    git(tmp_path, "clone", "-q", "--depth", "1", f"file://{source}", str(shallow))

    with pytest.raises(csr.CheckError, match="shallow"):
        csr.GitHistory(shallow).first_parent_line("origin/main")


# --------------------------------------------------------------------------------------------
# The gh client reads GitHub's JSON as the checks expect it
# --------------------------------------------------------------------------------------------


class GhRunner:
    def __init__(self, answers: dict[str, object]) -> None:
        self.answers = answers
        self.calls: list[list[str]] = []

    def __call__(self, command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        endpoint = next(argument for argument in command if argument.startswith("repos/"))
        path = endpoint.split("?")[0]
        return subprocess.CompletedProcess(command, 0, json.dumps(self.answers[path]), "")


def test_gh_reads_a_merged_pull_request_and_an_open_one() -> None:
    runner = GhRunner(
        {
            f"repos/{REPOSITORY}/commits/{MERGE}/pulls": [
                {
                    "number": 812,
                    "merged_at": "2026-11-20T10:00:00Z",
                    "merge_commit_sha": MERGE,
                    "base": {"ref": "main"},
                    "head": {"ref": "dev", "sha": DEV_PARENT, "repo": {"full_name": REPOSITORY}},
                },
                {
                    "number": 813,
                    "merged_at": None,
                    "merge_commit_sha": None,
                    "base": {"ref": "main"},
                    "head": {"ref": "dev", "sha": DEV_PARENT, "repo": None},
                },
            ]
        }
    )

    pulls = csr.GhCli(REPOSITORY, runner).pull_requests_of(MERGE)

    assert pulls == [promotion(), promotion(number=813, merged=False, merge_commit_sha="", head_repo="")]


def test_gh_reads_every_page_of_statuses_in_order() -> None:
    runner = GhRunner(
        {
            f"repos/{REPOSITORY}/commits/{DEV_PARENT}/statuses": [
                [
                    {
                        "context": "validate-dev",
                        "state": "success",
                        "creator": {"login": "github-actions[bot]"},
                    }
                ],
                [{"context": "validate-dev", "state": "pending", "creator": None}],
            ]
        }
    )

    statuses = csr.GhCli(REPOSITORY, runner).statuses(DEV_PARENT)

    assert statuses == [
        csr.CommitStatus("validate-dev", "success", "github-actions[bot]"),
        csr.CommitStatus("validate-dev", "pending", ""),
    ]
    assert runner.calls[0][2:4] == ["--paginate", "--slurp"]


def test_gh_lists_ci_push_runs_newest_first() -> None:
    runner = GhRunner(
        {
            f"repos/{REPOSITORY}/actions/workflows/ci.yml/runs": {
                "workflow_runs": [
                    {
                        "id": 1,
                        "created_at": "2026-11-20T10:00:00Z",
                        "head_branch": "main",
                        "status": "completed",
                        "conclusion": "failure",
                        "html_url": "u1",
                    },
                    {
                        "id": 2,
                        "created_at": "2026-11-20T11:00:00Z",
                        "head_branch": "main",
                        "status": "in_progress",
                        "conclusion": None,
                        "html_url": "u2",
                    },
                ]
            }
        }
    )

    runs = csr.GhCli(REPOSITORY, runner).ci_push_runs(MERGE)

    assert [(r.run_id, r.status, r.conclusion) for r in runs] == [
        (2, "in_progress", ""),
        (1, "completed", "failure"),
    ]
    assert f"event=push&head_sha={MERGE}" in runner.calls[0][-1]


def test_gh_failing_is_a_check_that_could_not_run() -> None:
    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "", "HTTP 403: Resource not accessible by integration")

    with pytest.raises(csr.CheckError, match="HTTP 403"):
        csr.GhCli(REPOSITORY, runner).statuses(DEV_PARENT)
