"""`scripts/check_command_blocks.py`: no `#` comments in a shell block someone pastes into zsh (v1-e01-t19).

The word-splitting cases are written by hand in `REFUSED` and `ALLOWED` (working agreement 6). Each
body is harmless to run, a `print -rl --` or a `cat` with a heredoc, because every one of them was
also pasted into a real interactive zsh with `nointeractivecomments` and its word splitting compared
with this check's verdict; the session report records that run. It is not part of this suite: CI
has no zsh.

The file-selection tests build a small git repository in a temporary directory, so a fixture can
hold a comment, a historical session report or an untracked runbook without touching this one.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_command_blocks as check  # noqa: E402
import task_helper  # noqa: E402

Capture = pytest.CaptureFixture[str]

# --------------------------------------------------------------------------------------------
# what counts as a comment
# --------------------------------------------------------------------------------------------

# name -> (block body, the block lines, counted from 1, that hold a comment)
REFUSED: dict[str, tuple[str, list[int]]] = {
    "a trailing comment": ("print -rl -- status --porcelain # must print nothing", [1]),
    "a whole-line comment": ("# set up first\nprint -rl -- ready", [1]),
    "an indented whole-line comment": ("  # set up first\nprint -rl -- ready", [1]),
    "a comment after a tab": ("print -rl -- a\t# tab before", [1]),
    "a bare # at the end of a line": ("print -rl -- a #", [1]),
    "after a semicolon with no space": ("print -rl -- a;# after semicolon", [1]),
    "after &&": ("true &&# after and\nprint -rl -- next", [1]),
    "after || and a space": ("false || # after or\nprint -rl -- next", [1]),
    "after a pipe": ("print -rl -- a |# after pipe\ncat", [1]),
    "on a continuation line": ("print -rl -- a \\\n  # on a continuation line", [2]),
    "inside a subshell": ("( print -rl -- a # in a subshell\n)", [1]),
    "inside a command substitution": ('print -rl -- "$(print -rl -- a # in a substitution\n)"', [1]),
    "inside backticks": ("print -rl -- `print -rl -- a # in backticks\n`", [1]),
    "a shebang after the first line": ("print -rl -- a\n#!/bin/bash", [2]),
    "after a heredoc's terminator": ("cat <<'EOF'\nbody\nEOF\n# after the heredoc", [4]),
    "after a here-string, which has no body": ('cat <<< "a"\n# after a here-string', [2]),
    "after a closing quote": ("print -rl -- 'a' # after a quote", [1]),
    "each one in a block": ("print -rl -- a # one\nprint -rl -- b\nprint -rl -- c # two", [1, 3]),
    "one per line, with an apostrophe in it": ("print -rl -- a # don't\nprint -rl -- b # two", [1, 2]),
}

ALLOWED: dict[str, str] = {
    "a shebang on the first line": "#!/usr/bin/env bash\nprint -rl -- a",
    "inside single quotes": "print -rl -- 'a # b'",
    "inside double quotes": 'print -rl -- "a # b"',
    "inside ANSI-C quotes": "print -rl -- $'a # b'",
    "escaped": "print -rl -- \\# not a comment",
    "the argument count": "print -rl -- $#",
    "a length": "print -rl -- ${#PATH}",
    "a prefix removal": "print -rl -- ${PATH#/usr} ${PATH##*/}",
    "a suffix removal with a space in its pattern": 'print -rl -- "${PATH% #}"',
    "inside a word": "print -rl -- https://example.com/page#anchor a#b",
    "inside a quoted substitution with its own quotes": 'print -rl -- "$(print -rl -- "a # b")"',
    "inside arithmetic": "print -rl -- $(( 1 + 2 ))",
    "inside a quoted heredoc": "cat <<'EOF'\n# a Python comment\nx = 1  # another\nEOF\nprint -rl -- done",
    "inside an unquoted heredoc": "cat <<EOF\n# a comment line\nEOF",
    "inside a tab-stripped heredoc": "cat <<-EOF\n\t# a comment line\n\tEOF\nprint -rl -- done",
    "inside two heredocs on one line": "cat <<A - <<B\n# first\nA\n# second\nB",
    "inside a quoted string across lines": "print -rl -- 'first\n# still quoted'",
    "after an escaped space": "print -rl -- a\\ #b",
    "after a backslash-newline that joins words": "print -rl -- a\\\n#b",
}


def flagged(body: str, tag: str = "bash") -> list[int]:
    """The lines of the block, counted from 1, that the check reports."""
    [block] = check.shell_blocks(f"```{tag}\n{body}\n```\n")
    return [line - block.first_line + 1 for line, _ in check.comments_in(block)]


@pytest.mark.parametrize("body, lines", REFUSED.values(), ids=REFUSED.keys())
def test_a_word_starting_with_hash_is_refused(body: str, lines: list[int]) -> None:
    assert flagged(body) == lines


@pytest.mark.parametrize("body", ALLOWED.values(), ids=ALLOWED.keys())
def test_a_hash_zsh_does_not_split_into_its_own_word_is_allowed(body: str) -> None:
    assert flagged(body) == []


def test_the_reported_comment_is_the_text_from_the_hash_to_the_end_of_the_line() -> None:
    [block] = check.shell_blocks("```bash\nprint -rl -- a   # must print nothing  \n```\n")
    assert check.comments_in(block) == [(2, "# must print nothing")]


# --------------------------------------------------------------------------------------------
# which blocks are scanned
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("tag", ["bash", "sh", "zsh", "shell", "console", "Bash", "bash title=setup"])
def test_shell_tagged_blocks_are_scanned(tag: str) -> None:
    text = f"```{tag}\n$ print -rl -- a # c\n```\n"
    assert [block.tag for block in check.shell_blocks(text)] == [tag.split()[0].lower()]


@pytest.mark.parametrize("info", ["", "text", "python", "yaml", "powershell", "bashrc"])
def test_other_blocks_are_not_scanned(info: str) -> None:
    assert check.shell_blocks(f"```{info}\nprint -rl -- a # c\n```\n") == []


def test_tilde_and_long_fences_and_indented_list_fences_are_read() -> None:
    text = (
        "1. Run:\n\n"
        "   ```bash\n"
        "   print -rl -- a # in a list\n"
        "   ```\n\n"
        "~~~sh\nprint -rl -- b # tilde\n~~~\n\n"
        "````zsh\n```\nprint -rl -- c # inner fence is content\n````\n"
    )
    blocks = check.shell_blocks(text)
    assert [(b.tag, b.first_line) for b in blocks] == [("bash", 4), ("sh", 8), ("zsh", 12)]
    assert blocks[0].lines == ("print -rl -- a # in a list",)
    assert [line for b in blocks for line, _ in check.comments_in(b)] == [4, 8, 13]


def test_a_shell_fence_nested_in_another_block_is_that_blocks_content() -> None:
    text = "````markdown\n```bash\nprint -rl -- a # example\n```\n````\n"
    assert check.shell_blocks(text) == []


def test_console_output_lines_are_never_checked() -> None:
    body = (
        "$ print -rl -- a\n# output that starts with a hash\nresult  # trailing in output\n% print -rl -- b"
    )
    assert flagged(body, "console") == []


def test_console_prompt_lines_are_checked() -> None:
    body = "$ print -rl -- a # dollar prompt\nout\n% print -rl -- b # percent prompt\n$ print -rl -- '#ok'"
    assert flagged(body, "console") == [1, 3]


def test_console_lines_that_continue_a_command_are_checked_as_part_of_it() -> None:
    body = (
        "$ print -rl -- a \\\n"
        "  # continued\n"
        "out # not a command\n"
        "$ cat <<'EOF'\n"
        "# heredoc body\n"
        "EOF\n"
        "# output"
    )
    assert flagged(body, "console") == [2]


def test_a_shebang_is_not_allowed_in_a_console_block() -> None:
    assert flagged("$ print -rl -- a\n#!/bin/bash", "console") == []
    assert flagged("#!/bin/bash", "console") == []
    assert flagged("$ #!/bin/bash", "console") == [1]


# --------------------------------------------------------------------------------------------
# which files are scanned
# --------------------------------------------------------------------------------------------

CLEAN = "```bash\nprint -rl -- a\n```\n"
DIRTY = "Intro.\n\n```bash\nprint -rl -- a # comment\n```\n"
REQUIRED = {
    "docs/runbooks/restore.md": CLEAN,
    "docs/process/task-workflow.md": CLEAN,
    "tests/fixtures/debate_files/eval/labels/README.md": "# Labeling\n\nNo commands.\n",
}


class Repo:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        root.mkdir(parents=True)
        self.git("init", "-q", "-b", "dev")

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
            cwd=self.root,
            env=self.env,
            capture_output=True,
            check=True,
            text=True,
        ).stdout

    def write(self, name: str, text: str) -> None:
        (self.root / name).parent.mkdir(parents=True, exist_ok=True)
        (self.root / name).write_text(text, encoding="utf-8")

    def commit(self, files: dict[str, str], message: str = "commit") -> None:
        for name, text in files.items():
            self.write(name, text)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    made = Repo(tmp_path / "repo")
    made.commit(REQUIRED)
    return made


def run(repo: Repo, capsys: Capture, *args: str) -> tuple[int, str, str]:
    status = check.main(["--root", str(repo.root), *args])
    out, err = capsys.readouterr()
    return status, out, err


def test_a_clean_repository_passes(repo: Repo, capsys: Capture) -> None:
    status, out, _ = run(repo, capsys)
    assert status == 0
    assert out.startswith("OK: no `#` comments in 2 shell code blocks in 3 Markdown files")


def test_the_failure_names_the_file_and_the_line(repo: Repo, capsys: Capture) -> None:
    repo.commit({"docs/runbooks/restore.md": DIRTY})
    status, out, err = run(repo, capsys)
    assert status == 1
    assert out.splitlines() == [
        "docs/runbooks/restore.md:4: zsh passes `# comment` to the command as arguments; "
        "move the comment into the prose around the block (working agreement 9)"
    ]
    assert "1 `#` comment(s)" in err


@pytest.mark.parametrize(
    "name",
    ["README.md", "web/README.md", "CONTRIBUTING.md", "docs/guides/use.md", "docs/session-reports/README.md"],
)
def test_every_tracked_markdown_file_is_scanned(repo: Repo, capsys: Capture, name: str) -> None:
    repo.commit({name: DIRTY})
    status, out, _ = run(repo, capsys)
    assert status == 1
    assert out.startswith(f"{name}:4:")


def test_untracked_and_ignored_files_are_not_scanned(repo: Repo, capsys: Capture) -> None:
    repo.commit({".gitignore": "node_modules/\n"})
    repo.write("docs/guides/draft.md", DIRTY)
    repo.write("node_modules/pkg/README.md", DIRTY)
    status, _, _ = run(repo, capsys)
    assert status == 0


def test_a_historical_session_report_is_not_scanned(repo: Repo, capsys: Capture) -> None:
    repo.commit({"docs/session-reports/v1-old.md": DIRTY})
    repo.git("checkout", "-q", "-b", "task/new")
    assert run(repo, capsys)[0] == 0
    assert run(repo, capsys, "--base", "dev")[0] == 0


def test_a_session_report_the_branch_adds_is_scanned_against_the_base(repo: Repo, capsys: Capture) -> None:
    repo.git("checkout", "-q", "-b", "task/new")
    repo.commit({"docs/session-reports/v1-new.md": DIRTY})
    assert run(repo, capsys)[0] == 0
    status, out, _ = run(repo, capsys, "--base", "dev")
    assert status == 1
    assert out.startswith("docs/session-reports/v1-new.md:4:")


def test_a_session_report_changed_by_the_branch_is_scanned(repo: Repo, capsys: Capture) -> None:
    repo.commit({"docs/session-reports/v1-old.md": "# Old\n"})
    repo.git("checkout", "-q", "-b", "task/new")
    repo.commit({"docs/session-reports/v1-old.md": DIRTY})
    assert run(repo, capsys, "--base", "dev")[0] == 1


def test_an_uncommitted_edit_to_a_session_report_is_scanned(repo: Repo, capsys: Capture) -> None:
    repo.commit({"docs/session-reports/v1-new.md": "# New\n"})
    repo.git("checkout", "-q", "-b", "task/new")
    repo.write("docs/session-reports/v1-new.md", DIRTY)
    assert run(repo, capsys, "--base", "dev")[0] == 1


def test_only_the_branchs_own_reports_count_when_the_base_has_moved_on(repo: Repo, capsys: Capture) -> None:
    repo.git("checkout", "-q", "-b", "task/new")
    repo.commit({"docs/session-reports/v1-new.md": CLEAN})
    repo.git("checkout", "-q", "dev")
    repo.commit({"docs/session-reports/v1-other.md": DIRTY})
    repo.git("checkout", "-q", "task/new")
    status, out, _ = run(repo, capsys, "--base", "dev")
    assert status == 0
    assert "(1 session reports changed since dev)" in out


def test_a_base_with_no_shared_history_is_an_error_not_a_pass(repo: Repo, capsys: Capture) -> None:
    status, _, err = run(repo, capsys, "--base", "no-such-branch")
    assert status == 2
    assert "fetch-depth: 0" in err


# --------------------------------------------------------------------------------------------
# it cannot pass by scanning nothing
# --------------------------------------------------------------------------------------------


def test_an_untracked_runbook_fails_the_check(repo: Repo, capsys: Capture) -> None:
    repo.write("docs/runbooks/new.md", CLEAN)
    status, out, _ = run(repo, capsys)
    assert status == 1
    assert "coverage: docs/runbooks/new.md was not among the scanned files (is it tracked by git?)" in out


@pytest.mark.parametrize("name", REQUIRED.keys())
def test_a_missing_required_file_fails_the_check(repo: Repo, capsys: Capture, name: str) -> None:
    repo.git("rm", "-q", name)
    repo.git("commit", "-q", "-m", "remove")
    status, out, _ = run(repo, capsys)
    assert status == 1
    assert "coverage: " in out


def test_a_file_whose_shell_block_the_parser_misses_fails_the_check(
    repo: Repo, capsys: Capture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(check, "shell_blocks", lambda text: [])
    status, out, _ = run(repo, capsys)
    assert status == 1
    assert "coverage: docs/runbooks/restore.md has a shell code block, but none was scanned" in out
    assert "coverage: no shell code blocks were scanned at all" in out


def test_a_git_listing_that_finds_nothing_fails_the_check(
    repo: Repo, capsys: Capture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(check, "scanned_files", lambda root, base: [])
    status, out, _ = run(repo, capsys)
    assert status == 1
    assert out.count("was not among the scanned files") == 3


# --------------------------------------------------------------------------------------------
# this repository
# --------------------------------------------------------------------------------------------


def test_this_repository_passes() -> None:
    result = check.check(REPO_ROOT)
    assert [finding.render() for finding in result.findings] == []
    assert result.coverage == []


def test_this_repository_scans_the_files_the_check_exists_for() -> None:
    scanned = check.check(REPO_ROOT).blocks_by_file
    for name in [*check.required_files(REPO_ROOT), "CONTRIBUTING.md", "README.md"]:
        assert name in scanned
    assert scanned["docs/runbooks/evidence-store.md"] > 0
    assert scanned["docs/process/task-workflow.md"] > 0


def test_ci_runs_the_check_with_the_pull_requests_base_and_its_history() -> None:
    flow = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    job: dict[str, Any] = flow["jobs"]["spec-validate"]
    assert "if" not in job and "needs" not in job  # every trigger, no path filter
    [checkout] = [step for step in job["steps"] if str(step.get("uses", "")).startswith("actions/checkout")]
    assert checkout["with"]["fetch-depth"] == 0
    [step] = [step for step in job["steps"] if "check_command_blocks.py" in step.get("run", "")]
    assert step["env"]["BASE_REF"] == "${{ github.base_ref }}"
    assert '--base "origin/${BASE_REF}"' in step["run"]


# --------------------------------------------------------------------------------------------
# the kickoff prompt (ac4)
# --------------------------------------------------------------------------------------------


def test_the_kickoff_prompt_tells_sessions_the_rule_and_links_agreement_9() -> None:
    prompt = " ".join(task_helper.PROMPT.split())
    assert "no `#` comments" in prompt
    assert "operator's shell is zsh" in prompt
    assert "docs/process/working-agreements.md#9-command-blocks-are-safe-to-paste-into-zsh" in prompt
    agreement = (REPO_ROOT / "docs/process/working-agreements.md").read_text(encoding="utf-8")
    assert "\n## 9. Command blocks are safe to paste into zsh\n" in agreement
