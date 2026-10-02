"""Tests for `scripts/check_promotion_source.py`, the guard on pull requests into `main`.

The workflows that run this script (.github/workflows/promotion-guard.yml and back-merge.yml) only
fire on pull requests into main and on pushes to main, so no task pull request into dev ever
exercises them. These tests are the evidence the guard is right before its first real run, which
is why they walk every head/base combination rather than a sample.

Everything above the last section is a pure function over its inputs: no network and no git. The
last section runs real git against throwaway repositories under tmp_path, because the one way the
back-merge check can go wrong silently is git's own answer on a shallow clone, and only git can
show that. Expected verdicts and messages are written by hand.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_promotion_source as guard  # noqa: E402

TEMPLATES = REPO_ROOT / ".github" / "PULL_REQUEST_TEMPLATE"
PROCESS_DOC = "docs/process/branching-and-environments.md"
REPO = "charlesclark2/debate-intelligence"


# --------------------------------------------------------------------------------------------
# source: which head branches may merge into which base
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("head", "kind"),
    [
        ("dev", "a promotion"),
        ("hotfix/login-crash", "a hotfix"),
        ("hotfix/x", "a hotfix"),
        ("hotfix/v1.1.1", "a hotfix"),
    ],
)
def test_main_accepts_dev_and_hotfix_heads(head: str, kind: str) -> None:
    verdict = guard.check_source("main", head)
    assert verdict.passed
    assert verdict.message == f"`{head}` → `main`: {kind}."


@pytest.mark.parametrize(
    "head",
    [
        "task/v1-e04-t02-http-fetcher",  # a task branch straight into main: the case the guard exists for
        "feature/new-parser",
        "main",
        "Dev",  # git branch names are case-sensitive
        "DEV",
        "develop",
        "dev2",
        "dev-hotfix",
        "dev/anything",
        " dev",
        "refs/heads/dev",  # github.head_ref is a short name; a full ref is not what the workflow sends
        "hotfix",
        "hotfix/",
        "hotfix/a/b",  # the ruleset pattern hotfix/* does not match a nested branch
        "hotfix/has space",
        "Hotfix/login-crash",
        "HOTFIX/login-crash",
        "hotfixes/login-crash",
        "release/v1.1",
        "back-merge/main-to-dev",
        "dependabot/pip/httpx-0.28",
    ],
)
def test_main_rejects_every_other_head(head: str) -> None:
    verdict = guard.check_source("main", head)
    assert not verdict.passed
    assert verdict.message.startswith(f"`{head}` → `main` is not allowed.")
    assert PROCESS_DOC in verdict.message


@pytest.mark.parametrize(
    "head",
    ["task/v1-e04-t02-http-fetcher", "main", "back-merge/main-to-dev", "hotfix/login-crash", "dev"],
)
@pytest.mark.parametrize("base", ["dev", "task/v1-e04-t02-http-fetcher", "hotfix/login-crash", "Main"])
def test_bases_other_than_main_are_not_guarded(head: str, base: str) -> None:
    verdict = guard.check_source(base, head)
    assert verdict.passed
    assert verdict.message == f"`{head}` → `{base}`: not a pull request into `main`; nothing to check."


@pytest.mark.parametrize(("base", "head"), [("", "dev"), ("", "task/x"), ("", "")])
def test_an_empty_base_fails(base: str, head: str) -> None:
    verdict = guard.check_source(base, head)
    assert not verdict.passed
    assert verdict.message == "No base branch was given, so the pull request cannot be checked."


@pytest.mark.parametrize("base", ["main", "dev"])
def test_an_empty_head_fails(base: str) -> None:
    verdict = guard.check_source(base, "")
    assert not verdict.passed
    assert verdict.message == "No head branch was given, so the pull request cannot be checked."


@pytest.mark.parametrize("head", ["dev", "hotfix/login-crash"])
def test_same_repository_heads_pass(head: str) -> None:
    assert guard.check_source("main", head, REPO, REPO).passed
    # GitHub owner and repository names are case-insensitive.
    assert guard.check_source("main", head, REPO.upper(), REPO).passed


@pytest.mark.parametrize("head", ["dev", "hotfix/login-crash"])
def test_a_fork_cannot_promote_by_naming_its_branch_dev(head: str) -> None:
    verdict = guard.check_source("main", head, "someone-else/debate-intelligence", REPO)
    assert not verdict.passed
    assert verdict.message.startswith(
        f"`someone-else/debate-intelligence:{head}` → `main`: a pull request from another repository"
    )


@pytest.mark.parametrize(
    ("head_repo", "base_repo"),
    [
        (REPO, None),
        (None, REPO),
        ("", REPO),  # head.repo is null when the fork was deleted; the workflow passes ""
        (REPO, ""),
        ("", ""),
    ],
)
def test_half_known_repositories_fail(head_repo: str | None, base_repo: str | None) -> None:
    verdict = guard.check_source("main", "dev", head_repo, base_repo)
    assert not verdict.passed
    assert "the head and base repositories must both be known" in verdict.message


def test_a_fork_into_dev_is_not_this_guards_business() -> None:
    assert guard.check_source("dev", "task/x", "someone-else/debate-intelligence", REPO).passed


# --------------------------------------------------------------------------------------------
# template: the "Dev build:" line. The validate-dev run is not asked for: protect-main requires
# the `validate-dev` commit status on the head commit itself (v1-e01-t10), and that status links
# the run, so a line in the description could only repeat it or disagree with it.
# --------------------------------------------------------------------------------------------

FILLED = """## Validation in dev

Dev build: v1.1.0-dev.7
"""


def fill(template: str, dev_build: str) -> str:
    """The template with its required line replaced, the way someone would fill it in."""
    return "\n".join(
        f"Dev build: {dev_build}" if line.startswith("Dev build:") else line for line in template.splitlines()
    )


def test_a_filled_body_passes() -> None:
    verdict = guard.check_template(FILLED)
    assert verdict.passed
    assert verdict.message == "Every required template line is filled in: Dev build."


def test_the_field_values_are_read_from_their_lines() -> None:
    assert guard.template_fields(FILLED) == {"Dev build": "v1.1.0-dev.7"}


@pytest.mark.parametrize("name", ["promotion.md", "hotfix.md"])
def test_an_untouched_template_fails_with_the_dev_build_blank(name: str) -> None:
    body = (TEMPLATES / name).read_text(encoding="utf-8")
    assert guard.template_fields(body) == {"Dev build": ""}
    verdict = guard.check_template(body)
    assert not verdict.passed
    assert '  * "Dev build:" is blank' in verdict.message
    assert "validate-dev" not in verdict.message


@pytest.mark.parametrize("name", ["promotion.md", "hotfix.md"])
def test_a_template_with_the_dev_build_filled_passes_without_a_run_link(name: str) -> None:
    """The case t08 refused: the validate-dev status, not a link in the body, is the evidence."""
    body = fill((TEMPLATES / name).read_text(encoding="utf-8"), "v1.1.0-dev.7")
    assert guard.check_template(body).passed


@pytest.mark.parametrize("name", ["promotion.md", "hotfix.md"])
def test_the_templates_point_at_the_required_status_and_ask_for_no_run_link(name: str) -> None:
    text = (TEMPLATES / name).read_text(encoding="utf-8")
    assert "validate-dev run:" not in text.lower()
    visible = guard.HTML_COMMENT.sub("", text)
    assert "`validate-dev` status" in visible


def test_a_leftover_validate_dev_line_is_neither_required_nor_refused() -> None:
    assert guard.check_template("Dev build: v1.1.0-dev.7\nvalidate-dev run:\n").passed
    assert guard.check_template("Dev build: v1.1.0-dev.7\nvalidate-dev run: https://x.test/1\n").passed


@pytest.mark.parametrize(
    "body",
    [
        "",  # no description at all: github.event.pull_request.body is null
        "Promoting dev.",
        "## Validation in dev\n\nsee the dev build\n",
        "The Dev build: v1.1.0-dev.7 is here\n",  # the label has to start the line
    ],
)
def test_a_body_without_the_template_line_fails_with_it_missing(body: str) -> None:
    verdict = guard.check_template(body)
    assert not verdict.passed
    assert '  * "Dev build:" is missing' in verdict.message
    assert "validate-dev" not in verdict.message
    assert "?template=promotion.md" in verdict.message


@pytest.mark.parametrize(
    "body",
    [
        "Dev build:\n",
        "Dev build:    \n",
        "Dev build:\t\n",
        "Dev build: <!-- pre-release tag -->\n",
        "Dev build: <!-- one --> <!-- two -->\n",
        "Dev build: <!-- a comment\nthat runs on -->\n",
        "Dev build: \r\n",  # the web editor sends CRLF
        "- **Dev build:**\n",
    ],
)
def test_a_blank_dev_build_fails(body: str) -> None:
    verdict = guard.check_template(body)
    assert not verdict.passed
    assert '"Dev build:" is blank' in verdict.message


@pytest.mark.parametrize(
    ("body", "dev_build"),
    [
        ("Dev build: v1.1.0-dev.7\r\n", "v1.1.0-dev.7"),
        ("dev build: v1.1.0-dev.7\n", "v1.1.0-dev.7"),
        ("- Dev build: v1.1.0-dev.7\n", "v1.1.0-dev.7"),
        ("**Dev build:** v1.1.0-dev.7\n", "v1.1.0-dev.7"),
        ("__Dev build:__ v1.1.0-dev.7\n", "v1.1.0-dev.7"),
        ("Dev build : v1.1.0-dev.7\n", "v1.1.0-dev.7"),
        ("   Dev build: v1.1.0-dev.7\n", "v1.1.0-dev.7"),
        ("Dev build: v1.1.0-dev.7 <!-- tag -->\n", "v1.1.0-dev.7"),
    ],
)
def test_filled_lines_in_their_accepted_forms_pass(body: str, dev_build: str) -> None:
    assert guard.check_template(body).passed
    assert guard.template_fields(body)["Dev build"] == dev_build


def test_the_first_line_for_a_field_is_the_one_that_counts() -> None:
    body = "Dev build:\n\nDev build: v1.1.0-dev.7\n"
    verdict = guard.check_template(body)
    assert not verdict.passed
    assert '"Dev build:" is blank' in verdict.message


def test_a_field_inside_a_comment_does_not_count() -> None:
    body = "<!--\nDev build: v1.1.0-dev.7\n-->\n"
    verdict = guard.check_template(body)
    assert not verdict.passed
    assert '"Dev build:" is missing' in verdict.message


# --------------------------------------------------------------------------------------------
# back-merge: main holds nothing dev lacks, and hotfix heads are exempt
# --------------------------------------------------------------------------------------------

UNMERGED = ["1f0e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c Fix the crash on an empty caselist page"]


@pytest.mark.parametrize(
    ("head", "applies"),
    [
        ("dev", True),
        ("task/v1-e04-t02-http-fetcher", True),
        ("hotfix/login-crash", False),
        ("hotfix/", True),  # not a hotfix branch, so not exempt
        ("hotfix/a/b", True),
    ],
)
def test_which_heads_the_back_merge_check_applies_to(head: str, applies: bool) -> None:
    assert guard.back_merge_applies(head) is applies


def test_a_dev_head_passes_when_main_has_nothing_dev_lacks() -> None:
    verdict = guard.check_back_merge("dev", [])
    assert verdict.passed
    assert verdict.message == "`dev` holds every non-merge commit on `main`."


def test_a_dev_head_fails_and_names_the_commits_dev_lacks() -> None:
    verdict = guard.check_back_merge("dev", UNMERGED)
    assert not verdict.passed
    assert verdict.message.startswith(
        "`main` has 1 non-merge commit(s) that `dev` lacks, so a hotfix was never back-merged:\n"
        "  1f0e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c Fix the crash on an empty caselist page\n"
    )
    assert "merge commit (not a squash)" in verdict.message


def test_a_hotfix_head_passes_even_when_an_earlier_hotfix_is_not_back_merged() -> None:
    verdict = guard.check_back_merge("hotfix/second-fix", UNMERGED)
    assert verdict.passed
    assert verdict.message == "`hotfix/second-fix` is a hotfix; the back-merge check does not apply to it."


def test_any_other_head_is_held_to_the_back_merge_check_too() -> None:
    assert not guard.check_back_merge("task/v1-e04-t02-http-fetcher", UNMERGED).passed


class FakeGit:
    """Answers the git calls `unmerged_commits` makes, and records them."""

    def __init__(self, *, shallow: bool = False, missing: str | None = None, rev_list: str = "") -> None:
        self.shallow = shallow
        self.missing = missing
        self.rev_list = rev_list
        self.calls: list[list[str]] = []

    def __call__(self, args: Sequence[str]) -> str:
        self.calls.append(list(args))
        if args[:2] == ["rev-parse", "--is-shallow-repository"]:
            return "true\n" if self.shallow else "false\n"
        if args[:2] == ["rev-parse", "--verify"]:
            if self.missing and args[-1].startswith(self.missing):
                raise guard.GitError("`git rev-parse` failed: ")
            return "0" * 40 + "\n"
        if args[0] == "rev-list":
            return self.rev_list
        raise AssertionError(f"unexpected git call: {args}")


def test_unmerged_commits_asks_rev_list_for_non_merge_commits_on_main_that_dev_lacks() -> None:
    git = FakeGit(rev_list=UNMERGED[0] + "\n\n")
    assert guard.unmerged_commits("origin/dev", "origin/main", git) == UNMERGED
    assert git.calls[-1] == [
        "rev-list",
        "--no-merges",
        "--no-commit-header",
        "--format=%H %s",
        "origin/dev..origin/main",
    ]


def test_unmerged_commits_refuses_a_shallow_clone() -> None:
    git = FakeGit(shallow=True, rev_list="")
    with pytest.raises(guard.GitError, match="shallow"):
        guard.unmerged_commits("origin/dev", "origin/main", git)
    assert not any(call[0] == "rev-list" for call in git.calls)


@pytest.mark.parametrize("missing", ["origin/dev", "origin/main"])
def test_unmerged_commits_refuses_a_ref_that_was_not_fetched(missing: str) -> None:
    git = FakeGit(missing=missing)
    with pytest.raises(guard.GitError, match=f"`{missing}` is not a commit in this clone"):
        guard.unmerged_commits("origin/dev", "origin/main", git)


# --------------------------------------------------------------------------------------------
# the command line: exit codes the workflows act on
# --------------------------------------------------------------------------------------------


def test_cli_source_exit_codes(capsys: pytest.CaptureFixture[str]) -> None:
    assert guard.main(["source", "--base", "main", "--head", "dev"]) == 0
    assert capsys.readouterr().out == "OK: `dev` → `main`: a promotion.\n"
    assert guard.main(["source", "--base", "main", "--head", "task/x"]) == 1
    assert capsys.readouterr().out.startswith("FAILED: `task/x` → `main` is not allowed.")
    assert guard.main(["source", "--base", "main", "--head", ""]) == 1
    args = ["source", "--base", "main", "--head", "dev", "--head-repo", "fork/x", "--base-repo", REPO]
    assert guard.main(args) == 1


def test_cli_template_reads_a_file_or_stdin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    filled = tmp_path / "filled.md"
    filled.write_text(FILLED, encoding="utf-8")
    blank = tmp_path / "blank.md"
    blank.write_text((TEMPLATES / "promotion.md").read_text(encoding="utf-8"), encoding="utf-8")
    assert guard.main(["template", "--body-file", str(filled)]) == 0
    assert guard.main(["template", "--body-file", str(blank)]) == 1

    monkeypatch.setattr(sys, "stdin", io.StringIO(FILLED))
    assert guard.main(["template", "--body-file", "-"]) == 0
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert guard.main(["template", "--body-file", "-"]) == 1


def test_cli_back_merge_does_not_run_git_for_a_hotfix(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_git(args: Sequence[str]) -> str:
        raise AssertionError("git must not run for a hotfix head")

    monkeypatch.setattr(guard, "run_git", no_git)
    assert guard.main(["back-merge", "--head", "hotfix/login-crash"]) == 0


def test_cli_back_merge_exit_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(guard, "run_git", FakeGit())
    assert guard.main(["back-merge", "--head", "dev"]) == 0
    monkeypatch.setattr(guard, "run_git", FakeGit(rev_list=UNMERGED[0] + "\n"))
    assert guard.main(["back-merge", "--head", "dev"]) == 1
    # Could not run is not the same as failed: back-merge.yml opens a pull request only on 1.
    monkeypatch.setattr(guard, "run_git", FakeGit(shallow=True))
    assert guard.main(["back-merge", "--head", "dev"]) == 2
    monkeypatch.setattr(guard, "run_git", FakeGit(missing="origin/main"))
    assert guard.main(["back-merge", "--head", "dev"]) == 2


# --------------------------------------------------------------------------------------------
# real git, local only: the history shapes the back-merge check has to read correctly
# --------------------------------------------------------------------------------------------


@pytest.fixture
def git_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """An environment where git ignores the worktree the tests run in and any user config."""
    for name in list(os.environ):
        if name.startswith("GIT_"):
            monkeypatch.delenv(name)
    identity = {
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.test",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.test",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    for name, value in identity.items():
        monkeypatch.setenv(name, value)
    return identity


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def commit(cwd: Path, name: str) -> str:
    (cwd / name).write_text(name, encoding="utf-8")
    git(cwd, "add", name)
    git(cwd, "commit", "-q", "-m", f"Add {name}")
    return git(cwd, "rev-parse", "HEAD").strip()


@pytest.fixture
def promoted(tmp_path: Path, git_env: dict[str, str]) -> Path:
    """main and dev after a promotion: dev merged into main with a merge commit, nothing else."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    commit(repo, "base")
    git(repo, "switch", "-q", "-c", "dev")
    commit(repo, "task-one")
    git(repo, "switch", "-q", "main")
    git(repo, "merge", "-q", "--no-ff", "-m", "Promote dev", "dev")
    return repo


def test_git_after_a_promotion_only_a_merge_commit_is_on_main(
    promoted: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(promoted)
    assert guard.unmerged_commits("dev", "main") == []


def test_git_an_un_back_merged_hotfix_is_found_and_a_back_merge_clears_it(
    promoted: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    git(promoted, "switch", "-q", "-c", "hotfix/crash")
    fix = commit(promoted, "fix")
    git(promoted, "switch", "-q", "main")
    git(promoted, "merge", "-q", "--no-ff", "-m", "Merge hotfix", "hotfix/crash")
    monkeypatch.chdir(promoted)

    assert guard.unmerged_commits("dev", "main") == [f"{fix} Add fix"]
    local_refs = ["--dev-ref", "dev", "--main-ref", "main"]
    assert guard.main(["back-merge", "--head", "dev", *local_refs]) == 1
    assert guard.main(["back-merge", "--head", "hotfix/second", *local_refs]) == 0

    git(promoted, "switch", "-q", "dev")
    git(promoted, "merge", "-q", "--no-ff", "-m", "Back-merge main into dev", "main")
    assert guard.unmerged_commits("dev", "main") == []


def test_git_a_squashed_back_merge_does_not_clear_it(promoted: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    git(promoted, "switch", "-q", "-c", "hotfix/crash")
    fix = commit(promoted, "fix")
    git(promoted, "switch", "-q", "main")
    git(promoted, "merge", "-q", "--no-ff", "-m", "Merge hotfix", "hotfix/crash")
    git(promoted, "switch", "-q", "dev")
    git(promoted, "merge", "-q", "--squash", "main")
    git(promoted, "commit", "-q", "-m", "Squashed back-merge")
    monkeypatch.chdir(promoted)
    assert guard.unmerged_commits("dev", "main") == [f"{fix} Add fix"]


def test_git_a_shallow_clone_is_refused_rather_than_answered(
    promoted: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clone = tmp_path / "shallow"
    git(tmp_path, "clone", "-q", "--depth", "1", "--no-single-branch", f"file://{promoted}", str(clone))
    monkeypatch.chdir(clone)
    with pytest.raises(guard.GitError, match="shallow"):
        guard.unmerged_commits("origin/dev", "origin/main")
    assert guard.main(["back-merge", "--head", "dev"]) == 2
