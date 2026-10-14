"""Tests for restarting a partly merged task with `scripts/task` (v1-e01-t18).

A task merged with `scripts/task pr --partial` stays InProgress on `dev`, and `finish --partial`
removes its worktree and branch. These tests cover the way back to it and the verdict check that
guards the second pull request:

* `resume` recreates the worktree and branch from `origin/dev`, syncs the environment, writes a
  resumed-task prompt, and commits nothing (ac1). `start` refuses such a task and points at
  `resume`, instead of dying part-way through as it did on 2026-10-02;
* a step that fails after the worktree exists removes what that run created, and only that, so a
  retry starts clean (ac2);
* the last `**Verdict:**` line in a report decides, so a report carrying an ACCEPTED review of
  earlier work and a PENDING one for the current work is refused by `scripts/task pr` (ac3). Every
  report already in `docs/session-reports/` that reads ACCEPTED keeps reading ACCEPTED;
* `pr --partial` reads the open items (NOT RUN, NOT APPLICABLE, PARTIAL, FAIL) only from the current
  session's part of the report, after the last-but-one PM review, so an earlier session's NOT RUN
  cannot stand in for the current session's (v1-e01-t24). Every report `--partial` accepted before
  that change is still accepted.

The shell tests run the real `scripts/task` and `scripts/task_helper.py` in a throwaway repository
built in `tmp_path`, with a local bare repository as `origin`. `uv`, `gh`, `pbcopy`, `code` and
`open` are stubs on `PATH` that log their arguments: nothing here touches this checkout, GitHub,
the clipboard or the network. The `uv` stub runs the helper with this interpreter, and can be told
to fail one helper subcommand, which is how a failure is forced after the worktree is created.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import pytest
import yaml
from hypothesis import event, given
from hypothesis import strategies as st

REPO_ROOT = Path(__file__).resolve().parents[2]
TASK_SCRIPT = REPO_ROOT / "scripts" / "task"
HELPER_SCRIPT = REPO_ROOT / "scripts" / "task_helper.py"
REPORT_TEMPLATE = REPO_ROOT / "docs" / "process" / "session-report-template.md"
SESSION_REPORTS = REPO_ROOT / "docs" / "session-reports"
FIXTURES = Path(__file__).parent / "fixtures" / "task_restart"

PARTLY_MERGED = "v1-e99-t01-partly-merged"
FRESH = "v1-e99-t02-fresh-task"
FINISHED = "v1-e99-t03-finished-task"

VERDICTS = ("ACCEPTED", "CHANGES_REQUESTED", "PENDING")


def load_helper() -> ModuleType:
    spec = importlib.util.spec_from_file_location("task_helper_under_test", HELPER_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


helper = load_helper()


# --------------------------------------------------------------------------------------
# A throwaway repository: an operator's main clone on dev, a bare origin, stubbed tools.
# --------------------------------------------------------------------------------------


def spec_text(task: str, title: str, phase: str) -> str:
    return f"""# TASK {task} - {title}
---
apiVersion: planspec.io/v1alpha1
kind: Goal
metadata:
  name: {task}
  namespace: debate-intelligence
  labels:
    planspec.io/kind: task
    debate/major-version: v1
    debate/release: v1.0
    debate/epic: v1-e99-fixture
  annotations:
    debate/title: "{title}"
spec:
  description: A fixture task for the scripts/task tests.
status:
  phase: {phase}
---
apiVersion: planspec.io/v1alpha1
kind: Plan
metadata:
  name: {task}-plan
  namespace: debate-intelligence
spec:
  description: A fixture plan.
status:
  phase: Pending
"""


STUB_LOG_LINE = 'printf \'%s %s\\n\' "$(basename "$0")" "$*" >> "$TASK_TEST_LOG"\n'

UV_STUB = """#!/usr/bin/env bash
{log}if [ "${{1:-}}" = run ]; then
  shift
  [ "${{1:-}}" = --quiet ] && shift
  script="$1"; shift
  case "$script" in
    */task_helper.py)
      if [ -n "${{TASK_TEST_FAIL_HELPER:-}}" ] && [ "${{1:-}}" = "$TASK_TEST_FAIL_HELPER" ]; then
        printf 'forced failure in task_helper.py %s\\n' "$1" >&2
        exit 1
      fi
      exec "{python}" "$script" "$@" ;;
  esac
fi
exit 0
"""

GH_STUB = """#!/usr/bin/env bash
{log}if [ "${{1:-}} ${{2:-}}" = "pr view" ]; then
  printf 'no pull requests found\\n' >&2
  exit 1
fi
exit 0
"""

QUIET_STUB = """#!/usr/bin/env bash
{log}cat > /dev/null 2>&1 < /dev/null
exit 0
"""


@dataclass(frozen=True)
class TaskRepo:
    """The operator's world for one test: main clone, bare origin, worktree parent, stub log."""

    main: Path
    origin: Path
    worktrees: Path
    log: Path
    env: dict[str, str]

    def run(self, *args: str, fail_helper: str | None = None) -> subprocess.CompletedProcess[str]:
        env = dict(self.env)
        if fail_helper:
            env["TASK_TEST_FAIL_HELPER"] = fail_helper
        return subprocess.run(
            [str(self.main / "scripts" / "task"), *args],
            cwd=self.main,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

    def git(self, *args: str, cwd: Path | None = None) -> str:
        return subprocess.run(
            ["git", *args], cwd=cwd or self.main, env=self.env, capture_output=True, text=True, check=True
        ).stdout.strip()

    def worktree(self, task: str) -> Path:
        return self.worktrees / task

    def has_branch(self, task: str) -> bool:
        return (
            subprocess.run(
                ["git", "show-ref", "--verify", "--quiet", f"refs/heads/task/{task}"],
                cwd=self.main,
                env=self.env,
                check=False,
            ).returncode
            == 0
        )

    def has_remote_branch(self, task: str) -> bool:
        return bool(self.git("ls-remote", "--heads", "origin", f"task/{task}"))

    def registered_worktrees(self) -> list[Path]:
        listing = self.git("worktree", "list", "--porcelain")
        return [
            Path(line.removeprefix("worktree "))
            for line in listing.splitlines()
            if line.startswith("worktree ")
        ]

    def report(self, task: str, where: Path | None = None) -> Path:
        return (where or self.main) / "docs" / "session-reports" / f"{task}.md"


def write_stub(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text(body)
    path.chmod(0o755)


@pytest.fixture
def repo(tmp_path: Path) -> TaskRepo:
    tmp_path = tmp_path.resolve()
    stubs = tmp_path / "bin"
    stubs.mkdir()
    log = tmp_path / "stub-calls.log"
    log.touch()
    write_stub(stubs, "uv", UV_STUB.format(log=STUB_LOG_LINE, python=sys.executable))
    write_stub(stubs, "gh", GH_STUB.format(log=STUB_LOG_LINE))
    for name in ("pbcopy", "code", "open"):
        write_stub(stubs, name, QUIET_STUB.format(log=STUB_LOG_LINE))

    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text(
        "[user]\n\tname = Fixture Operator\n\temail = operator@example.invalid\n"
        "[init]\n\tdefaultBranch = dev\n[commit]\n\tgpgsign = false\n"
    )
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(
        PATH=f"{stubs}{os.pathsep}{os.environ['PATH']}",
        GIT_CONFIG_GLOBAL=str(gitconfig),
        GIT_CONFIG_NOSYSTEM="1",
        DEBATE_WORKTREES=str(tmp_path / "worktrees"),
        DEBATE_TASK_LAUNCHER="none",
        TASK_TEST_LOG=str(log),
    )

    main = tmp_path / "debate-intelligence"
    origin = tmp_path / "origin.git"
    (main / "scripts").mkdir(parents=True)
    shutil.copy2(TASK_SCRIPT, main / "scripts" / "task")
    shutil.copy2(HELPER_SCRIPT, main / "scripts" / "task_helper.py")
    (main / "docs" / "process").mkdir(parents=True)
    shutil.copy2(REPORT_TEMPLATE, main / "docs" / "process" / "session-report-template.md")
    specs = main / "plan_specs" / "v1" / "e99-fixture"
    specs.mkdir(parents=True)
    (specs / "t01-partly-merged.yaml").write_text(
        spec_text(PARTLY_MERGED, "A task merged with --partial", "InProgress")
    )
    (specs / "t02-fresh-task.yaml").write_text(spec_text(FRESH, "A task nobody has started", "Pending"))
    (specs / "t03-finished-task.yaml").write_text(spec_text(FINISHED, "A task that is done", "Succeeded"))
    reports = main / "docs" / "session-reports"
    reports.mkdir()
    shutil.copy2(FIXTURES / "first_session_accepted.md", reports / f"{PARTLY_MERGED}.md")
    (reports / f"{FINISHED}.md").write_text(
        (FIXTURES / "first_session_accepted.md").read_text().replace(PARTLY_MERGED, FINISHED)
    )

    task_repo = TaskRepo(main=main, origin=origin, worktrees=tmp_path / "worktrees", log=log, env=env)
    task_repo.git("init", "--quiet", "--bare", str(origin), cwd=tmp_path)
    task_repo.git("init", "--quiet")
    task_repo.git("add", "-A")
    task_repo.git("commit", "--quiet", "-m", "dev as the PM left it")
    task_repo.git("remote", "add", "origin", str(origin))
    task_repo.git("push", "--quiet", "-u", "origin", "dev")
    return task_repo


def commit_report(repo: TaskRepo, task: str, text: str, message: str) -> None:
    wt = repo.worktree(task)
    repo.report(task, wt).write_text(text)
    repo.git("commit", "--quiet", "-am", message, cwd=wt)


def rebuild_worktree_by_hand(repo: TaskRepo, task: str) -> Path:
    wt = repo.worktree(task)
    repo.git("worktree", "add", "--quiet", "-b", f"task/{task}", str(wt), "origin/dev")
    return wt


def resumed_report(verdict: str) -> str:
    text = (FIXTURES / "resumed_review_pending.md").read_text()
    assert text.count("**Verdict:** PENDING") == 1
    return text.replace("**Verdict:** PENDING", f"**Verdict:** {verdict}")


# --------------------------------------------------------------------------------------
# ac1: resume recreates a partly merged task; start refuses it.
# --------------------------------------------------------------------------------------


def test_start_refuses_a_partly_merged_task_and_points_at_resume(repo: TaskRepo) -> None:
    result = repo.run("start", PARTLY_MERGED)

    assert result.returncode != 0
    assert f"scripts/task resume {PARTLY_MERGED}" in result.stderr
    assert not repo.worktree(PARTLY_MERGED).exists()
    assert not repo.has_branch(PARTLY_MERGED)
    assert repo.registered_worktrees() == [repo.main]
    assert repo.report(PARTLY_MERGED).read_text() == (FIXTURES / "first_session_accepted.md").read_text()


def test_resume_recreates_the_worktree_and_branch_from_origin_dev(repo: TaskRepo) -> None:
    dev_tip = repo.git("rev-parse", "origin/dev")

    result = repo.run("resume", PARTLY_MERGED)

    assert result.returncode == 0, result.stderr
    wt = repo.worktree(PARTLY_MERGED)
    assert repo.registered_worktrees() == [repo.main, wt]
    assert repo.git("rev-parse", "--abbrev-ref", "HEAD", cwd=wt) == f"task/{PARTLY_MERGED}"
    # Nothing is committed, empty or otherwise: the branch is origin/dev and the tree is clean.
    assert repo.git("rev-parse", "HEAD", cwd=wt) == dev_tip
    assert repo.git("status", "--porcelain", cwd=wt) == ""
    assert repo.report(PARTLY_MERGED, wt).read_text() == (FIXTURES / "first_session_accepted.md").read_text()
    prompt = (wt / ".task" / "prompt.md").read_text()
    assert "This is a resumed task" in prompt
    assert "append to the existing report" in prompt
    assert "keep every earlier PM review" in prompt
    assert "uv sync --quiet --all-packages" in repo.log.read_text()


def test_resume_on_an_existing_worktree_still_just_reopens_it(repo: TaskRepo) -> None:
    assert repo.run("resume", PARTLY_MERGED).returncode == 0
    head = repo.git("rev-parse", "HEAD", cwd=repo.worktree(PARTLY_MERGED))

    again = repo.run("resume", PARTLY_MERGED)

    assert again.returncode == 0, again.stderr
    assert "Not launching" in again.stdout
    assert repo.git("rev-parse", "HEAD", cwd=repo.worktree(PARTLY_MERGED)) == head


def test_resume_dry_run_says_what_it_would_do_and_creates_nothing(repo: TaskRepo) -> None:
    result = repo.run("resume", PARTLY_MERGED, "--dry-run")

    assert result.returncode == 0, result.stderr
    assert "Dry run" in result.stdout
    assert f"task/{PARTLY_MERGED}" in result.stdout
    assert not repo.worktree(PARTLY_MERGED).exists()
    assert not repo.has_branch(PARTLY_MERGED)
    assert "uv sync" not in repo.log.read_text()


@pytest.mark.parametrize(
    ("task", "expected"),
    [
        (FRESH, f"scripts/task start {FRESH}"),
        (FINISHED, "Succeeded"),
    ],
    ids=["never-started", "already-succeeded"],
)
def test_resume_refuses_a_task_that_did_not_merge_partially(repo: TaskRepo, task: str, expected: str) -> None:
    result = repo.run("resume", task)

    assert result.returncode != 0
    assert expected in result.stderr
    assert not repo.worktree(task).exists()
    assert not repo.has_branch(task)


def test_resume_refuses_while_the_task_branch_is_on_origin(repo: TaskRepo) -> None:
    repo.git("push", "--quiet", "origin", f"dev:refs/heads/task/{PARTLY_MERGED}")

    result = repo.run("resume", PARTLY_MERGED)

    assert result.returncode != 0
    assert "origin" in result.stderr
    assert not repo.worktree(PARTLY_MERGED).exists()
    assert not repo.has_branch(PARTLY_MERGED)
    assert repo.has_remote_branch(PARTLY_MERGED)


# --------------------------------------------------------------------------------------
# ac2: a failure part-way removes what the run created, and nothing else.
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("command", "task", "failing_step"),
    [
        ("start", FRESH, "info"),
        ("start", FRESH, "set-phase"),
        ("start", FRESH, "prompt"),
        ("resume", PARTLY_MERGED, "info"),
        ("resume", PARTLY_MERGED, "prompt-resumed"),
    ],
)
def test_a_failure_after_the_worktree_exists_removes_what_the_run_created(
    repo: TaskRepo, command: str, task: str, failing_step: str
) -> None:
    failed = repo.run(command, task, fail_helper=failing_step)

    assert failed.returncode != 0
    assert "Creating worktree" in failed.stdout
    assert f"forced failure in task_helper.py {failing_step}" in failed.stderr
    assert not repo.worktree(task).exists()
    assert not repo.has_branch(task)
    assert repo.registered_worktrees() == [repo.main]

    retry = repo.run(command, task)

    assert retry.returncode == 0, retry.stderr
    assert repo.worktree(task).is_dir()


def test_a_refused_start_leaves_an_existing_worktree_and_its_work_alone(repo: TaskRepo) -> None:
    assert repo.run("resume", PARTLY_MERGED).returncode == 0
    wt = repo.worktree(PARTLY_MERGED)
    commit_report(repo, PARTLY_MERGED, resumed_report("PENDING"), "Second session's work")
    (wt / "uncommitted.txt").write_text("work in progress\n")
    head = repo.git("rev-parse", "HEAD", cwd=wt)

    result = repo.run("start", PARTLY_MERGED)

    assert result.returncode != 0
    assert "worktree already exists" in result.stderr
    assert repo.registered_worktrees() == [repo.main, wt]
    assert (wt / "uncommitted.txt").read_text() == "work in progress\n"
    assert (wt / ".task" / "prompt.md").is_file()
    assert repo.git("rev-parse", f"task/{PARTLY_MERGED}") == head
    assert repo.report(PARTLY_MERGED, wt).read_text() == resumed_report("PENDING")


@pytest.mark.parametrize(("command", "task"), [("start", FRESH), ("resume", PARTLY_MERGED)])
def test_a_refused_run_leaves_an_existing_branch_alone(repo: TaskRepo, command: str, task: str) -> None:
    repo.git("branch", f"task/{task}", "dev")
    repo.git("commit", "--quiet", "--allow-empty", "-m", "work only on the branch")
    repo.git("branch", "--force", f"task/{task}", "HEAD")
    repo.git("reset", "--quiet", "--hard", "origin/dev")
    tip = repo.git("rev-parse", f"task/{task}")

    result = repo.run(command, task)

    assert result.returncode != 0
    assert f"task/{task}" in result.stderr
    assert repo.git("rev-parse", f"task/{task}") == tip
    assert repo.registered_worktrees() == [repo.main]


# --------------------------------------------------------------------------------------
# ac3: the last verdict in the report decides.
# --------------------------------------------------------------------------------------


def test_pr_refuses_a_report_whose_current_review_is_pending(repo: TaskRepo) -> None:
    # Built the way the operator rebuilt v1-e31-t05 by hand on 2026-10-02, so this runs without resume.
    rebuild_worktree_by_hand(repo, PARTLY_MERGED)
    commit_report(repo, PARTLY_MERGED, (FIXTURES / "resumed_review_pending.md").read_text(), "Second session")

    result = repo.run("pr", PARTLY_MERGED, "--partial")

    assert result.returncode != 0
    assert "PM verdict is PENDING" in result.stderr
    assert not repo.has_remote_branch(PARTLY_MERGED)
    assert "gh pr create" not in repo.log.read_text()


def test_pr_opens_once_the_current_review_is_accepted(repo: TaskRepo) -> None:
    # The current sections must record what is still open for --partial (v1-e01-t24), which the
    # resumed_review_pending.md fixture's do not.
    rebuild_worktree_by_hand(repo, PARTLY_MERGED)
    commit_report(
        repo, PARTLY_MERGED, (FIXTURES / "resumed_still_open.md").read_text(), "Second session, reviewed"
    )

    result = repo.run("pr", PARTLY_MERGED, "--partial")

    assert result.returncode == 0, result.stderr
    assert repo.has_remote_branch(PARTLY_MERGED)
    assert "gh pr create --base dev" in repo.log.read_text()
    # The pull request quotes the review it was opened on, not the first session's.
    pr_review = (
        (repo.worktree(PARTLY_MERGED) / ".task" / "pr-body.md").read_text().split("## PM review", 1)[1]
    )
    assert "**Verdict:** ACCEPTED" in pr_review
    assert "PM, 2026-09-23" not in pr_review


def test_the_pr_body_quotes_the_last_pm_review() -> None:
    quoted = helper.section(resumed_report("ACCEPTED"), "PM review")

    assert quoted.startswith("**Verdict:** ACCEPTED")
    assert "2026-09-23" not in quoted
    assert "Accepted for a --partial merge." not in quoted


def test_the_last_verdict_line_decides() -> None:
    assert helper.report_verdict((FIXTURES / "resumed_review_pending.md").read_text()) == "PENDING"
    assert helper.report_verdict(resumed_report("CHANGES_REQUESTED")) == "CHANGES_REQUESTED"
    assert helper.report_verdict(resumed_report("ACCEPTED")) == "ACCEPTED"
    assert helper.report_verdict((FIXTURES / "first_session_accepted.md").read_text()) == "ACCEPTED"
    assert helper.report_verdict("# A report with no PM review yet\n") == "PENDING"


def review(verdict: str, notes: str) -> str:
    return (
        "## PM review\n\n<!-- Completed by the PM only. -->\n\n"
        f"**Verdict:** {verdict}\n<!-- ACCEPTED / CHANGES_REQUESTED -->\n\n"
        f"**Reviewed by / date:**\n\n**Notes:**\n\n{notes}\n"
    )


@given(
    reviews=st.lists(
        st.tuples(
            st.sampled_from((*VERDICTS, "UNDECIDED")),
            st.sampled_from(("", "Accepted.", "Fix the rollback.", "**Verdict (first review):** ACCEPTED")),
        ),
        min_size=1,
        max_size=5,
    )
)
def test_the_last_review_decides_whatever_the_earlier_ones_say(reviews: list[tuple[str, str]]) -> None:
    text = "# Session report\n\n" + "\n## Resumed\n\nMore work.\n\n".join(review(v, n) for v, n in reviews)
    last = reviews[-1][0]
    event("first and last verdicts differ" if reviews[0][0] != last else "first and last verdicts agree")

    assert helper.report_verdict(text) == (last if last in VERDICTS else "PENDING")


def verdict_before_this_task(text: str) -> str:
    """The rule scripts/task_helper.py applied until v1-e01-t18, copied by hand: the first line."""
    m = re.search(r"^\*\*Verdict:\*\*\s*`?([A-Z_]+)`?", text, re.M)
    return m.group(1) if m and m.group(1) in VERDICTS else "PENDING"


REPORTS_ACCEPTED_TODAY = sorted(
    path for path in SESSION_REPORTS.glob("v*.md") if verdict_before_this_task(path.read_text()) == "ACCEPTED"
)


def test_the_walk_over_existing_reports_is_not_vacuous() -> None:
    names = {path.stem for path in REPORTS_ACCEPTED_TODAY}
    # The two reports whose earlier review was renamed by hand are the ones the new rule must keep.
    assert {"v1-e31-t05-parser-eval", "v1-e03-t05-edit-constraints"} <= names
    assert len(names) >= 60


@pytest.mark.parametrize("report", REPORTS_ACCEPTED_TODAY, ids=lambda path: path.stem)
def test_an_existing_accepted_report_still_reads_accepted(report: Path) -> None:
    assert helper.report_verdict(report.read_text()) == "ACCEPTED"


# --------------------------------------------------------------------------------------
# finish --partial confirms the merge of the work it is about to delete.
# --------------------------------------------------------------------------------------


def test_finish_partial_refuses_until_the_resumed_report_reaches_dev(repo: TaskRepo) -> None:
    wt = rebuild_worktree_by_hand(repo, PARTLY_MERGED)
    commit_report(repo, PARTLY_MERGED, resumed_report("ACCEPTED"), "Second session, reviewed")
    repo.git("push", "--quiet", "origin", f"task/{PARTLY_MERGED}")

    # The pull request is open: origin/dev still carries only the first session's ACCEPTED report.
    early = repo.run("finish", PARTLY_MERGED, "--partial")

    assert early.returncode != 0
    assert wt.is_dir()
    assert repo.has_branch(PARTLY_MERGED)
    assert repo.has_remote_branch(PARTLY_MERGED)

    repo.git("merge", "--quiet", "--squash", f"task/{PARTLY_MERGED}")
    repo.git("commit", "--quiet", "-m", "Squash-merge the second session")
    repo.git("push", "--quiet", "origin", "dev")

    merged = repo.run("finish", PARTLY_MERGED, "--partial")

    assert merged.returncode == 0, merged.stderr
    assert not wt.exists()
    assert not repo.has_branch(PARTLY_MERGED)
    assert not repo.has_remote_branch(PARTLY_MERGED)


# --------------------------------------------------------------------------------------
# pr --partial reads the open items from the current session's sections (v1-e01-t24).
# --------------------------------------------------------------------------------------

OPEN_ITEM_MARKERS = ("NOT RUN", "NOT APPLICABLE", "PARTIAL", "FAIL")


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text()


def with_current_open_item(marker: str) -> str:
    """resumed_still_open.md, with the one open item in its current sections recorded as `marker`."""
    earlier, current = fixture_text("resumed_still_open.md").split("## Resumed", 1)
    assert current.count("NOT RUN") == 1
    return earlier + "## Resumed" + current.replace("NOT RUN", marker)


def test_pr_partial_refuses_a_resumed_report_whose_current_sections_record_nothing_open(
    repo: TaskRepo,
) -> None:
    # The first session's NOT RUN, the PM's notes and the PM's FAIL record are all above the
    # last-but-one review's end; the second session's sections and its review record nothing open.
    rebuild_worktree_by_hand(repo, PARTLY_MERGED)
    commit_report(repo, PARTLY_MERGED, fixture_text("resumed_nothing_open.md"), "Second session, reviewed")

    result = repo.run("pr", PARTLY_MERGED, "--partial")

    assert result.returncode != 0
    assert "--partial needs the current session's sections" in result.stderr
    assert not repo.has_remote_branch(PARTLY_MERGED)
    assert "gh pr create" not in repo.log.read_text()


def test_pr_partial_accepts_a_resumed_report_whose_current_sections_record_an_open_criterion(
    repo: TaskRepo,
) -> None:
    rebuild_worktree_by_hand(repo, PARTLY_MERGED)
    commit_report(repo, PARTLY_MERGED, fixture_text("resumed_still_open.md"), "Second session, reviewed")

    result = repo.run("pr", PARTLY_MERGED, "--partial")

    assert result.returncode == 0, result.stderr
    assert repo.has_remote_branch(PARTLY_MERGED)
    assert "gh pr create --base dev" in repo.log.read_text()


def test_pr_partial_accepts_a_first_session_report_that_records_an_open_criterion(repo: TaskRepo) -> None:
    # origin/dev's copy of the report is first_session_accepted.md: one review, ac2 NOT RUN.
    rebuild_worktree_by_hand(repo, PARTLY_MERGED)

    result = repo.run("pr", PARTLY_MERGED, "--partial")

    assert result.returncode == 0, result.stderr
    assert "gh pr create --base dev" in repo.log.read_text()


def test_the_open_items_are_read_from_the_current_sessions_sections() -> None:
    assert helper.open_items(fixture_text("resumed_nothing_open.md")) == []
    assert helper.open_items(fixture_text("resumed_still_open.md")) == ["NOT RUN"]
    assert helper.open_items(fixture_text("first_session_accepted.md")) == ["NOT RUN", "PARTIAL"]


@pytest.mark.parametrize("marker", OPEN_ITEM_MARKERS)
def test_each_open_item_marker_counts_in_the_current_sections(marker: str) -> None:
    assert helper.open_items(with_current_open_item(marker)) == [marker]


def test_the_markers_are_matched_in_upper_case_as_the_grep_matched_them() -> None:
    assert helper.open_items(with_current_open_item("not run")) == []


# The boundary, case by case. Each is described in task-workflow.md and the t24 session report.


def test_a_first_session_report_with_one_review_is_current_throughout() -> None:
    text = fixture_text("first_session_accepted.md")

    assert helper.current_session(text) == text


def test_a_resumed_report_before_its_own_review_is_appended_is_current_throughout() -> None:
    # Until the resumed session appends its empty review, the report has one review, and both the
    # verdict and the open items are read as they are in a first-session report.
    text = fixture_text("resumed_nothing_open.md")
    before_its_review = text[: text.rindex("## PM review")]

    assert helper.current_session(before_its_review) == before_its_review
    assert helper.report_verdict(before_its_review) == "ACCEPTED"
    assert helper.open_items(before_its_review) == ["FAIL", "NOT RUN", "PARTIAL"]


@pytest.mark.parametrize("verdict", VERDICTS)
def test_a_resumed_report_after_its_own_review_is_appended_starts_at_its_own_sections(verdict: str) -> None:
    text = fixture_text("resumed_nothing_open.md")
    head, _, tail = text.rpartition("**Verdict:** ACCEPTED")
    text = head + f"**Verdict:** {verdict}" + tail

    current = helper.current_session(text)

    assert current.startswith("## Resumed 2026-10-08: the second session\n")
    assert text.endswith(current)
    assert helper.report_verdict(text) == verdict


def test_the_earlier_reviews_notes_and_a_record_the_pm_adds_under_it_stay_with_that_review() -> None:
    # v1-e01-t23's "### Operator follow-up 1, recorded (PM, …)" is a record of this kind.
    current = helper.current_session(fixture_text("resumed_nothing_open.md"))

    assert "ac2 stays NOT RUN" not in current
    assert "Operator follow-up 1, recorded" not in current
    assert "Follow-up 1: FAIL" not in current


def test_a_record_the_pm_adds_under_the_current_review_is_current() -> None:
    text = fixture_text("resumed_nothing_open.md") + (
        "\n### Operator follow-up 2, recorded (PM, 2026-10-10)\n\n"
        "**Follow-up 2: NOT RUN.** The operator has not had the device since.\n"
    )

    assert helper.open_items(text) == ["NOT RUN"]


SECTION_THE_PM_APPENDS = """## Sandbox attempt, 2026-10-01

Recorded on the PM's instruction. ac2 remains **NOT RUN**, and this section asks for no new review.

"""


def test_a_section_the_pm_appends_after_the_only_review_is_current() -> None:
    # v1-e01-t15's "## Sandbox attempt, 2026-10-09", in the one-review report it is today.
    nothing_open = (
        fixture_text("first_session_accepted.md")
        .replace("| Session status | PARTIAL |", "| Session status | COMPLETE |")
        .replace(
            "| ac2 | NOT RUN | needs the operator's device |", "| ac2 | PASS | `device-check` → exit 0 |"
        )
    )
    assert helper.open_items(nothing_open) == []

    assert helper.open_items(nothing_open + "\n" + SECTION_THE_PM_APPENDS) == ["NOT RUN"]


def test_a_section_the_pm_appends_after_an_earlier_review_is_read_with_the_next_sessions() -> None:
    # A `##` section starts after the earlier review has ended, so it is on the current side: the
    # boundary cannot tell who wrote a section. The t24 report says why that is accepted.
    text = fixture_text("resumed_nothing_open.md").replace(
        "## Resumed 2026-10-08", SECTION_THE_PM_APPENDS + "## Resumed 2026-10-08", 1
    )

    assert helper.current_session(text).startswith("## Sandbox attempt, 2026-10-01\n")
    assert helper.open_items(text) == ["NOT RUN"]


# A report of 1 to 4 review cycles. Each cycle is a session's sections, a PM review with its notes,
# and optionally a `###` record the PM adds under the review and a `##` section appended after it.
# Each part records an open item or not. The expectation is built from the cycles, not from the
# text: with one review the whole report is current; otherwise the current part is the section
# appended after the last-but-one review, if any, and the whole last cycle.

CYCLE_PARTS = ("session", "notes", "record_under_review", "section_after_review")


def cycle_text(index: int, verdict: str, parts: dict[str, str | None]) -> str:
    def status(part: str) -> str:
        return parts[part] or "PASS"

    text = (
        f"## Session {index}\n\n| Criterion | Status |\n|---|---|\n| ac{index} | {status('session')} |\n\n"
        "## PM review\n\n<!-- Completed by the PM only. -->\n\n"
        f"**Verdict:** {verdict}\n<!-- ACCEPTED / CHANGES_REQUESTED -->\n\n"
        f"**Reviewed by / date:** PM\n\n**Notes:**\n\nac{index} reads {status('notes')}.\n\n"
    )
    if "record_under_review" in parts:
        text += f"### Operator follow-up {index}, recorded (PM)\n\nIt is {status('record_under_review')}.\n\n"
    if "section_after_review" in parts:
        text += f"## Record after review {index}\n\nIt is {status('section_after_review')}.\n\n"
    return text


@st.composite
def review_cycles(draw: st.DrawFn) -> list[tuple[str, dict[str, str | None]]]:
    cycles = []
    for _ in range(draw(st.integers(min_value=1, max_value=4))):
        present = ["session", "notes"] + [part for part in CYCLE_PARTS[2:] if draw(st.booleans())]
        parts = {part: draw(st.none() | st.sampled_from(OPEN_ITEM_MARKERS)) for part in present}
        cycles.append((draw(st.sampled_from(VERDICTS)), parts))
    return cycles


@given(cycles=review_cycles())
def test_only_the_current_part_of_a_report_decides_whether_anything_is_open(
    cycles: list[tuple[str, dict[str, str | None]]],
) -> None:
    text = "# Session report\n\n" + "".join(cycle_text(i, v, parts) for i, (v, parts) in enumerate(cycles))
    if len(cycles) == 1:
        current = [cycles[0][1]]
        earlier = []
    else:
        appended = cycles[-2][1].get("section_after_review")
        current = [cycles[-1][1], {"section_after_review": appended}]
        earlier = [parts for _, parts in cycles[:-1]]
    open_now = sorted({marker for parts in current for marker in parts.values() if marker})
    open_earlier = any(marker for parts in earlier for marker in parts.values())
    event(f"{len(cycles)} review(s)")
    if open_earlier and not open_now:
        event("open items only before the boundary: the case today's grep accepts")

    assert helper.open_items(text) == open_now


# The walk over the reports already in the repository. `--partial` reads the markers only when the
# spec's phase is InProgress: for a Succeeded task it takes the ordinary path, before and after.


def spec_phases() -> dict[str, str]:
    phases = {}
    for path in (REPO_ROOT / "plan_specs").glob("v*/e*/t*.yaml"):
        for document in yaml.safe_load_all(path.read_text()):
            if document and document.get("kind") == "Goal":
                phases[document["metadata"]["name"]] = (document.get("status") or {}).get("phase", "Pending")
    return phases


PHASES = spec_phases()


def open_items_before_this_task(text: str) -> bool:
    """The check `scripts/task pr --partial` ran until v1-e01-t24, copied by hand: the whole report."""
    return re.search(r"NOT RUN|NOT APPLICABLE|PARTIAL|FAIL", text) is not None


def partial_accepts(text: str, phase: str, open_items: Callable[[str], bool]) -> bool:
    """What `scripts/task pr --partial` decides from the report and the phase, copied from cmd_pr by hand."""
    if helper.report_verdict(text) != "ACCEPTED":
        return False
    if phase == "Succeeded":
        return True
    return phase == "InProgress" and open_items(text)


REPORTS_PARTIAL_ACCEPTS_TODAY = sorted(
    path
    for path in SESSION_REPORTS.glob("v*.md")
    if path.stem in PHASES
    and partial_accepts(path.read_text(), PHASES[path.stem], open_items_before_this_task)
)


def test_the_walk_over_reports_partial_accepts_is_not_vacuous() -> None:
    names = {path.stem for path in REPORTS_PARTIAL_ACCEPTS_TODAY}
    in_progress = {name for name in names if PHASES[name] == "InProgress"}
    # The reports whose markers --partial really reads, including the PM's two examples of records
    # added after a review.
    assert {"v1-e01-t15-promotion-guard-sweep", "v1-e01-t23-managed-python"} <= in_progress
    assert len(in_progress) >= 5
    assert len(names) >= 60


@pytest.mark.parametrize("report", REPORTS_PARTIAL_ACCEPTS_TODAY, ids=lambda path: path.stem)
def test_an_existing_report_partial_accepts_is_still_accepted(report: Path) -> None:
    assert partial_accepts(
        report.read_text(), PHASES[report.stem], lambda text: bool(helper.open_items(text))
    )


def test_the_reports_the_marker_check_alone_now_refuses_are_all_of_succeeded_tasks() -> None:
    # v1-e30-t06 and v1-e30-t08: closing sections that record every criterion PASS, after earlier
    # sessions' NOT RUN. They are ac1's case in real reports. Neither reaches the marker check.
    flipped = {
        path.stem
        for path in SESSION_REPORTS.glob("v*.md")
        if open_items_before_this_task(path.read_text()) and not helper.open_items(path.read_text())
    }

    assert {"v1-e30-t06-initial-backfill", "v1-e30-t08-import-metadata-defects"} <= flipped
    assert {name: PHASES.get(name) for name in flipped} == dict.fromkeys(flipped, "Succeeded")
