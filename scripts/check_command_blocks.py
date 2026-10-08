# /// script
# requires-python = ">=3.11"
# ///
"""Fail on a `#` comment inside a shell code block that a person pastes into zsh (v1-e01-t19).

The operator's shell is zsh, which does not treat `#` as a comment when commands are pasted
interactively unless `interactivecomments` is set. A trailing comment becomes arguments:
`git status --porcelain # must print nothing` reads the words as pathspecs and prints nothing even
on a dirty tree. Working agreement 9 says: no `#` comments inside a shell code block, put the
explanation in the prose. This script enforces it.

What counts as a comment: what interactive zsh without `interactivecomments` would pass on as an
argument, which is an unquoted `#` at the start of a word, including after `;`, `&&`, `|`, `(` or
a line continuation. These are not comments, and pass:

  * `#!` at the start of a block's first line
  * `#` inside single quotes, double quotes or `$'...'`
  * `\\#`
  * `$#`, `${#var}`, `${var#pattern}` and anything else inside `${...}` or `$((...))`
  * a `#` inside a word, as in a URL's `.../page#anchor`
  * anything in a heredoc body: the lines up to the terminator of `<<'EOF'`, `<<EOF` or `<<-EOF`
    are not shell words, so the Python inside one may carry `#` comments

Which blocks are scanned: fenced blocks whose info string starts with `bash`, `sh`, `zsh`,
`shell` or `console`. Untagged and `text` blocks are not. In a `console` block only commands are
checked: a line starting with a `$ ` or `% ` prompt, and the lines that continue it (a trailing
backslash, an open quote, a heredoc). Output lines are never checked. A fence nested inside
another fence is content of the outer block, as Markdown renders it.

Which files: every Markdown file `git ls-files` reports, so nothing ignored or vendored is read,
except the session reports in docs/session-reports/ (their README is scanned). A session report is
a record: it is scanned only when `--base REF` is given and the report was added or changed since
the merge base of REF and HEAD (working-tree edits included). In CI, `--base` is the pull request's
target branch, so a new report's operator follow-ups are checked and historical reports are left
as written.

It cannot pass by scanning nothing. Before it reports success it confirms that every runbook under
docs/runbooks/, docs/process/task-workflow.md and the evaluation labeling guide
tests/fixtures/debate_files/eval/labels/README.md were among the scanned files, found on disk
rather than in the git listing, and that each one with a shell-tagged fence (found by a separate,
plain search of its lines) produced at least one scanned block. If any of that fails, so does the
check.

Usage:
  uv run scripts/check_command_blocks.py                   # every scanned file, no session reports
  uv run scripts/check_command_blocks.py --base origin/dev # also the session reports changed since dev
  uv run scripts/check_command_blocks.py --list            # the files and block counts, no checking
  uv run scripts/check_command_blocks.py --root DIR        # another repository
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL_TAGS = frozenset({"bash", "sh", "zsh", "shell", "console"})
SESSION_REPORTS = "docs/session-reports/"
LABELING_GUIDE = "tests/fixtures/debate_files/eval/labels/README.md"
TASK_WORKFLOW = "docs/process/task-workflow.md"
RUNBOOKS = "docs/runbooks"

OPENING_FENCE = re.compile(r"^(?P<indent>[ \t]*)(?P<marker>`{3,}|~{3,})(?P<info>.*)$")
CONSOLE_PROMPT = re.compile(r"^[ \t]*[$%](?: |$)")
# Deliberately not the parser below: the cross-check that a file with a shell fence yielded a block.
SHELL_FENCE_LINE = re.compile(r"^[ \t]*(?:`{3,}|~{3,})[ \t]*(?:bash|sh|zsh|shell|console)\b", re.IGNORECASE)
# Characters that end a shell word: after one of them, the next character starts a new word.
WORD_BREAKS = frozenset(" \t;&|<>()")


class CheckError(Exception):
    """The check could not run as asked (git failed, no merge base); exit status 2."""


@dataclass(frozen=True)
class Block:
    tag: str
    first_line: int  # line number, in the Markdown file, of the block's first content line
    lines: tuple[str, ...]


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    comment: str  # the text from the `#` to the end of the line

    def render(self) -> str:
        return (
            f"{self.path}:{self.line}: zsh passes `{self.comment}` to the command as arguments; "
            "move the comment into the prose around the block (working agreement 9)"
        )


# --------------------------------------------------------------------------------------------
# Markdown: the shell-tagged fenced blocks of a file
# --------------------------------------------------------------------------------------------


def shell_blocks(text: str) -> list[Block]:
    """Every fenced block tagged bash, sh, zsh, shell or console, with its content de-indented."""
    blocks: list[Block] = []
    lines = text.split("\n")
    index = 0
    while index < len(lines):
        opening = OPENING_FENCE.match(lines[index])
        if opening is None or (opening["marker"][0] == "`" and "`" in opening["info"]):
            index += 1
            continue
        marker, indent = opening["marker"], len(opening["indent"].expandtabs(4))
        words = opening["info"].strip().split()
        tag = words[0].lower() if words else ""
        closing = re.compile(rf"^[ \t]*{re.escape(marker[0])}{{{len(marker)},}}[ \t]*$")
        content: list[str] = []
        index += 1
        start = index + 1
        while index < len(lines) and not closing.match(lines[index]):
            content.append(dedent(lines[index], indent))
            index += 1
        index += 1  # past the closing fence, or past the end of an unclosed block
        if tag in SHELL_TAGS:
            blocks.append(Block(tag, start, tuple(content)))
    return blocks


def dedent(line: str, indent: int) -> str:
    """The line with up to `indent` columns of leading whitespace removed, as Markdown does."""
    removed = 0
    while removed < len(line) and line[removed] in " \t" and len(line[: removed + 1].expandtabs(4)) <= indent:
        removed += 1
    return line[removed:]


# --------------------------------------------------------------------------------------------
# Shell: where zsh would see a word starting with `#`
# --------------------------------------------------------------------------------------------


@dataclass
class ShellScanner:
    """Reads a command one line at a time, the way zsh splits it into words.

    `contexts` is a stack: `'` (single quotes), `$'` (ANSI-C quotes), `"` (double quotes), `${`
    (parameter expansion), `$((` (arithmetic), `$(` (command substitution), `(` (subshell) and
    `` ` `` (backticks). Only in the last three, and at the top level, do words exist.
    """

    contexts: list[str] = field(default_factory=list)
    word_start: bool = True
    continued: bool = False  # the last line ended with a backslash
    pending_heredocs: list[tuple[str, bool]] = field(default_factory=list)  # (terminator, strip tabs)
    heredoc: tuple[str, bool] | None = None  # the body being skipped

    @property
    def complete(self) -> bool:
        """Whether the command read so far is finished, so the next line starts a new one."""
        return not (self.contexts or self.continued or self.pending_heredocs or self.heredoc)

    def feed(self, line: str, allow_shebang: bool = False) -> str | None:
        """Scan one line; return the comment it holds, from its `#` to the end of the line, if any."""
        if self.heredoc is not None:
            terminator, strip_tabs = self.heredoc
            if (line.lstrip("\t") if strip_tabs else line) == terminator:
                self.heredoc = self.pending_heredocs.pop(0) if self.pending_heredocs else None
            return None
        if allow_shebang and line.startswith("#!"):
            return None
        if self.continued:
            self.continued = False  # the backslash-newline is removed; word_start carries over
        comment = self._scan(line)
        if not self.continued and self.contexts[-1:] not in (["'"], ["$'"], ['"']):
            self.word_start = True  # a newline outside quotes ends a word
        if not self.continued and self.pending_heredocs and not self.contexts:
            self.heredoc = self.pending_heredocs.pop(0)
        return comment

    def _scan(self, line: str) -> str | None:
        i, n = 0, len(line)
        while i < n:
            c, rest = line[i], line[i:]
            context = self.contexts[-1] if self.contexts else ""
            if context in ("'", "$'"):
                if c == "\\" and context == "$'":
                    i += 2
                    continue
                if c == "'":
                    self.contexts.pop()
                i += 1
                continue
            if context in ('"', "${", "$(("):
                i = self._scan_inside_expansion(line, i, context)
                continue
            # Words exist here: the top level, a subshell, a command substitution, backticks.
            if c == "\\":
                if i == n - 1:
                    self.continued = True
                    return None
                self.word_start = False
                i += 2
                continue
            if c == "#" and self.word_start:
                # The rest of the line is what the author meant as a comment. Reading on would let
                # an apostrophe in it (`# don't`) open a quote that swallows the following lines.
                return rest
            if c in " \t":
                self.word_start = True
            elif rest.startswith("<<<"):
                self.word_start = True  # a here-string; its word follows like any other
                i += 3
                continue
            elif rest.startswith("<<"):
                i = self._read_heredoc_terminator(line, i + 2)
                self.word_start = False
                continue
            elif c in ";&|<>":
                self.word_start = True
            elif c == "(":
                self.contexts.append("(")
                self.word_start = True
            elif c == ")":
                if context in ("(", "$("):
                    closed = self.contexts.pop()
                    self.word_start = closed == "("
                else:
                    self.word_start = True
            elif c == "`":
                if context == "`":
                    self.contexts.pop()
                    self.word_start = False
                else:
                    self.contexts.append("`")
                    self.word_start = True
            elif rest.startswith("$(("):
                self.contexts.append("$((")
                self.word_start = False
                i += 3
                continue
            elif rest.startswith("$("):
                self.contexts.append("$(")
                self.word_start = True
                i += 2
                continue
            elif rest.startswith("${"):
                self.contexts.append("${")
                self.word_start = False
                i += 2
                continue
            elif rest.startswith("$'"):
                self.contexts.append("$'")
                self.word_start = False
                i += 2
                continue
            elif c in "'\"":
                self.contexts.append(c)
                self.word_start = False
            else:
                self.word_start = False
            i += 1
        return None

    def _scan_inside_expansion(self, line: str, i: int, context: str) -> int:
        """One step inside double quotes, `${...}` or `$((...))`, where `#` is never a comment."""
        c, rest = line[i], line[i:]
        if c == "\\":
            if i == len(line) - 1:
                self.continued = True
            return i + 2
        if context == '"' and c == '"':
            self.contexts.pop()
            return i + 1
        if context == "${" and c == "}":
            self.contexts.pop()
            return i + 1
        if context == "$((" and rest.startswith("))"):
            self.contexts.pop()
            return i + 2
        if context == "${" and c in "'\"":
            self.contexts.append(c)
            return i + 1
        for opener in ("$((", "$(", "${"):
            if rest.startswith(opener):
                self.contexts.append(opener)
                if opener == "$(":
                    self.word_start = True
                return i + len(opener)
        if c == "`":
            self.contexts.append("`")
            self.word_start = True
        return i + 1

    def _read_heredoc_terminator(self, line: str, i: int) -> int:
        """Record the terminator of a `<<WORD`, `<<'WORD'` or `<<-WORD` and return where it ends."""
        strip_tabs = line.startswith("-", i)
        i += 1 if strip_tabs else 0
        while i < len(line) and line[i] in " \t":
            i += 1
        terminator, quote = [], ""
        while i < len(line):
            c = line[i]
            if quote:
                if c == quote:
                    quote = ""
                else:
                    terminator.append(c)
            elif c in "'\"":
                quote = c
            elif c == "\\" and i + 1 < len(line):
                i += 1
                terminator.append(line[i])
            elif c in WORD_BREAKS:
                break
            else:
                terminator.append(c)
            i += 1
        if terminator:
            self.pending_heredocs.append(("".join(terminator), strip_tabs))
        return i


def comments_in(block: Block) -> list[tuple[int, str]]:
    """(line number, comment) for every word-starting `#` in the block's commands."""
    found: list[tuple[int, str]] = []
    scanner = ShellScanner()
    for offset, line in enumerate(block.lines):
        if block.tag == "console" and scanner.complete:
            prompt = CONSOLE_PROMPT.match(line)
            if prompt is None:
                continue  # output, or a blank line
            line = line[prompt.end() :]
            scanner = ShellScanner()
        comment = scanner.feed(line, allow_shebang=offset == 0 and block.tag != "console")
        if comment is not None:
            found.append((block.first_line + offset, comment.rstrip()))
    return found


# --------------------------------------------------------------------------------------------
# Files: what is scanned
# --------------------------------------------------------------------------------------------


def git(root: Path, *args: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, check=True, text=True
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise CheckError(f"git {' '.join(args)} failed: {detail.strip()}") from exc


def is_session_report(name: str) -> bool:
    return name.startswith(SESSION_REPORTS) and Path(name).name != "README.md"


def changed_session_reports(root: Path, base: str) -> set[str]:
    """Session reports added or changed since the merge base of `base` and HEAD, uncommitted edits
    included. In CI the working tree is HEAD, so this is exactly what the pull request changes."""
    try:
        merge_base = git(root, "merge-base", base, "HEAD").strip()
    except CheckError as exc:
        raise CheckError(
            f"cannot find where HEAD branched from {base}; the checkout needs that history "
            f"(in CI, actions/checkout with fetch-depth: 0). {exc}"
        ) from exc
    listed = git(root, "diff", "--name-only", "-z", "--diff-filter=AMR", merge_base, "--", SESSION_REPORTS)
    return {name for name in listed.split("\0") if name.endswith(".md") and is_session_report(name)}


def scanned_files(root: Path, base: str | None) -> list[str]:
    """Repository-relative paths of the Markdown files to scan, in order."""
    tracked = [name for name in git(root, "ls-files", "-z", "--", "*.md").split("\0") if name]
    reports = changed_session_reports(root, base) if base else set()
    return sorted(name for name in tracked if not is_session_report(name) or name in reports)


def required_files(root: Path) -> list[str]:
    """The files the check exists for, found on disk so a broken git listing cannot hide them."""
    runbooks = sorted(p.relative_to(root).as_posix() for p in (root / RUNBOOKS).glob("*.md"))
    return [*runbooks, TASK_WORKFLOW, LABELING_GUIDE]


def coverage_problems(root: Path, blocks_by_file: dict[str, int]) -> list[str]:
    """Why the scan does not prove anything, if it does not; empty when it does."""
    problems: list[str] = []
    if not (root / RUNBOOKS).is_dir() or not any((root / RUNBOOKS).glob("*.md")):
        problems.append(f"no runbooks found under {RUNBOOKS}/, which this check exists to protect")
    for name in required_files(root):
        path = root / name
        if not path.is_file():
            problems.append(f"{name} does not exist, and this check exists to protect it")
        elif name not in blocks_by_file:
            problems.append(f"{name} was not among the scanned files (is it tracked by git?)")
        elif blocks_by_file[name] == 0 and any(
            SHELL_FENCE_LINE.match(line) for line in path.read_text(encoding="utf-8").split("\n")
        ):
            problems.append(f"{name} has a shell code block, but none was scanned")
    if not any(blocks_by_file.values()):
        problems.append("no shell code blocks were scanned at all")
    return problems


@dataclass
class Result:
    findings: list[Finding]
    blocks_by_file: dict[str, int]
    coverage: list[str]


def check(root: Path, base: str | None = None) -> Result:
    findings: list[Finding] = []
    blocks_by_file: dict[str, int] = {}
    for name in scanned_files(root, base):
        blocks = shell_blocks((root / name).read_text(encoding="utf-8"))
        blocks_by_file[name] = len(blocks)
        for block in blocks:
            findings.extend(Finding(name, line, comment) for line, comment in comments_in(block))
    return Result(findings, blocks_by_file, coverage_problems(root, blocks_by_file))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=ROOT, help="repository root to check")
    ap.add_argument(
        "--base",
        help="also scan the session reports added or changed since this ref's merge base with HEAD",
    )
    ap.add_argument("--list", action="store_true", help="list the scanned files and block counts")
    args = ap.parse_args(argv)

    root = args.root.resolve()
    try:
        result = check(root, args.base)
    except CheckError as exc:
        print(exc, file=sys.stderr)
        return 2
    if args.list:
        for name, count in result.blocks_by_file.items():
            print(f"{count:3d}  {name}")
        return 0

    for finding in result.findings:
        print(finding.render())
    for problem in result.coverage:
        print(f"coverage: {problem}")
    files = len(result.blocks_by_file)
    blocks = sum(result.blocks_by_file.values())
    reports = sum(1 for name in result.blocks_by_file if is_session_report(name))
    if args.base:
        scope = f"{files} Markdown files ({reports} session reports changed since {args.base})"
    else:
        scope = f"{files} Markdown files (no session reports: pass --base to include changed ones)"
    if result.findings or result.coverage:
        print(
            f"\n{len(result.findings)} `#` comment(s) in shell code blocks; {blocks} blocks in {scope}",
            file=sys.stderr,
        )
        return 1
    print(f"OK: no `#` comments in {blocks} shell code blocks in {scope}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
