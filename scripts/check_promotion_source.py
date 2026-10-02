# /// script
# requires-python = ">=3.11"
# ///
"""Guard the pull requests into `main`: where they come from, what they say, and what dev lacks.

`main` is production and `dev` is the development environment (ADR-0013). Nothing reaches `main`
that has not been deployed to and validated in dev, so a pull request into `main` comes from `dev`
(a promotion) or from `hotfix/<slug>` (an urgent fix, validated in dev by a manual dispatch all the
same). docs/process/branching-and-environments.md is the rule; this script is what enforces it, run
by .github/workflows/promotion-guard.yml and .github/workflows/back-merge.yml.

Subcommands:
  source      the head branch may merge into the base branch: into `main`, only `dev` or
              `hotfix/<slug>` from this repository (a fork can name its branch `dev` too)
  template    the pull request body fills in the "Dev build:" line of the promotion or hotfix
              template. It asks for no validate-dev run link: protect-main requires the
              `validate-dev` commit status on the head commit (v1-e01-t10), and that status links
              its run, so a line in the description could only repeat it or disagree with it
  back-merge  `main` holds no non-merge commit that `dev` lacks, i.e. every hotfix was back-merged.
              A hotfix/* head passes without looking, so that a second urgent fix is never blocked
              by the first one not having been back-merged yet

Exit codes: 0 the check passed, 1 the check failed, 2 the check could not run (git failed, or the
clone is shallow and would give a wrong answer rather than an error).

The checks are pure functions over their inputs; only `unmerged_commits` runs git.

Usage:
  uv run scripts/check_promotion_source.py source --base main --head dev
  uv run scripts/check_promotion_source.py source --base main --head "$HEAD_REF" \\
      --head-repo "$HEAD_REPO" --base-repo "$BASE_REPO"
  printf '%s' "$PR_BODY" | uv run scripts/check_promotion_source.py template --body-file -
  uv run scripts/check_promotion_source.py back-merge --head dev
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

PROCESS_DOC = "docs/process/branching-and-environments.md"
GUARDED_BASE = "main"
PROMOTION_HEAD = "dev"
HOTFIX_PREFIX = "hotfix/"
# The lines of .github/PULL_REQUEST_TEMPLATE/promotion.md and hotfix.md that must not be left blank.
# "validate-dev run" was one until v1-e01-t10 made the `validate-dev` status itself required.
REQUIRED_FIELDS = ("Dev build",)

PASSED, FAILED, COULD_NOT_RUN = 0, 1, 2

HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
# `Dev build: v1.1.0-dev.7`, optionally as a list item and optionally with the label in bold.
FIELD_LINE = re.compile(
    r"^\s{0,3}(?:[-*+]\s+)?(?:\*\*|__)?(?P<label>"
    + "|".join(re.escape(f) for f in REQUIRED_FIELDS)
    + r")\s*:(?:\*\*|__)?(?P<value>.*)$",
    re.IGNORECASE | re.MULTILINE,
)

HOW_TO_PROMOTE = (
    f"Only `{PROMOTION_HEAD}` (a promotion) or `{HOTFIX_PREFIX}<slug>` (a hotfix) may merge into "
    f"`{GUARDED_BASE}`. Merge task branches into `dev`, let dev build and validate them, then open "
    f"a promotion pull request from `dev`. See {PROCESS_DOC}."
)
HOW_TO_FILL_TEMPLATE = (
    "Open a promotion with ?template=promotion.md or a hotfix with ?template=hotfix.md, or copy "
    "the template from .github/PULL_REQUEST_TEMPLATE/ into the description, and fill in each line. "
    f"See {PROCESS_DOC}#what-validated-in-dev-means."
)


@dataclass(frozen=True)
class Verdict:
    passed: bool
    message: str

    @property
    def exit_code(self) -> int:
        return PASSED if self.passed else FAILED


class GitError(RuntimeError):
    """git could not answer, so the check has no verdict to give."""


def is_hotfix(head: str) -> bool:
    """`hotfix/<slug>` with a single non-empty slug, as the ruleset pattern `hotfix/*` matches it."""
    if not head.startswith(HOTFIX_PREFIX):
        return False
    slug = head.removeprefix(HOTFIX_PREFIX)
    return bool(slug) and "/" not in slug and not any(c.isspace() for c in slug)


def check_source(base: str, head: str, head_repo: str | None = None, base_repo: str | None = None) -> Verdict:
    """May a pull request from `head` merge into `base`?

    `head_repo` and `base_repo` are the `owner/name` of each side. They are optional so the
    check can be run by hand, but when either is given both must be, and they must match.
    """
    if not base:
        return Verdict(False, "No base branch was given, so the pull request cannot be checked.")
    if not head:
        return Verdict(False, "No head branch was given, so the pull request cannot be checked.")
    if base != GUARDED_BASE:
        return Verdict(
            True, f"`{head}` → `{base}`: not a pull request into `{GUARDED_BASE}`; nothing to check."
        )
    if (head_repo is None) != (base_repo is None) or head_repo == "" or base_repo == "":
        return Verdict(
            False,
            f"`{head}` → `{base}`: the head and base repositories must both be known "
            f"(head: {head_repo!r}, base: {base_repo!r}).",
        )
    if head_repo is not None and base_repo is not None and head_repo.lower() != base_repo.lower():
        return Verdict(
            False,
            f"`{head_repo}:{head}` → `{base}`: a pull request from another repository cannot be a "
            f"promotion or a hotfix, whatever its branch is called. {HOW_TO_PROMOTE}",
        )
    if head == PROMOTION_HEAD:
        return Verdict(True, f"`{head}` → `{base}`: a promotion.")
    if is_hotfix(head):
        return Verdict(True, f"`{head}` → `{base}`: a hotfix.")
    return Verdict(False, f"`{head}` → `{base}` is not allowed. {HOW_TO_PROMOTE}")


def template_fields(body: str) -> dict[str, str | None]:
    """Each required field's value from a pull request body; None when its line is missing.

    HTML comments are dropped first, so a line still holding only the template's guidance comment
    reads as blank. The first line for a field is the one that counts.
    """
    visible = HTML_COMMENT.sub("", body)
    values: dict[str, str | None] = dict.fromkeys(REQUIRED_FIELDS)
    by_lowercase = {f.lower(): f for f in REQUIRED_FIELDS}
    for match in FIELD_LINE.finditer(visible):
        field = by_lowercase[match["label"].lower()]
        if values[field] is None:
            values[field] = match["value"].strip()
    return values


def check_template(body: str) -> Verdict:
    """Does the body fill in every required line of the promotion or hotfix template?"""
    problems = []
    for field, value in template_fields(body).items():
        if value is None:
            problems.append(f'  * "{field}:" is missing')
        elif not value:
            problems.append(f'  * "{field}:" is blank')
    if problems:
        return Verdict(
            False,
            "The pull request description is incomplete:\n"
            + "\n".join(problems)
            + f"\n{HOW_TO_FILL_TEMPLATE}",
        )
    return Verdict(True, "Every required template line is filled in: " + ", ".join(REQUIRED_FIELDS) + ".")


def back_merge_applies(head: str) -> bool:
    """A hotfix is exempt: the fix before it may still be waiting for its back-merge."""
    return not is_hotfix(head)


def check_back_merge(head: str, unmerged: Sequence[str]) -> Verdict:
    """Given the non-merge commits on main that dev lacks, may `head` merge into main?"""
    if not back_merge_applies(head):
        return Verdict(True, f"`{head}` is a hotfix; the back-merge check does not apply to it.")
    if not unmerged:
        return Verdict(True, f"`{PROMOTION_HEAD}` holds every non-merge commit on `{GUARDED_BASE}`.")
    listing = "\n".join(f"  {line}" for line in unmerged)
    return Verdict(
        False,
        f"`{GUARDED_BASE}` has {len(unmerged)} non-merge commit(s) that `{PROMOTION_HEAD}` lacks, "
        f"so a hotfix was never back-merged:\n{listing}\n"
        f"Merge the open 'Back-merge main → dev' pull request into `{PROMOTION_HEAD}` with a merge "
        f"commit (not a squash), then update this pull request. See {PROCESS_DOC}.",
    )


GitRunner = Callable[[Sequence[str]], str]


def run_git(args: Sequence[str]) -> str:
    try:
        done = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    except OSError as exc:
        raise GitError(f"could not run git: {exc}") from exc
    if done.returncode != 0:
        raise GitError(f"`git {' '.join(args)}` failed: {done.stderr.strip()}")
    return done.stdout


def unmerged_commits(dev_ref: str, main_ref: str, git: GitRunner | None = None) -> list[str]:
    """`<sha> <subject>` for each non-merge commit reachable from `main_ref` but not `dev_ref`.

    Refuses a shallow clone: there, rev-list stops at the graft and reports a wrong answer rather
    than an error, which is the one way this check could pass when it should fail.
    """
    git = git or run_git
    if git(["rev-parse", "--is-shallow-repository"]).strip() == "true":
        raise GitError(
            "the clone is shallow, so rev-list cannot see the history; check out with fetch-depth: 0"
        )
    for ref in (dev_ref, main_ref):
        try:
            git(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"])
        except GitError as exc:
            raise GitError(f"`{ref}` is not a commit in this clone; fetch it first") from exc
    out = git(["rev-list", "--no-merges", "--no-commit-header", "--format=%H %s", f"{dev_ref}..{main_ref}"])
    return [line for line in out.splitlines() if line.strip()]


def read_body(path: str) -> str:
    return sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    source = sub.add_parser("source", help="the head branch may merge into the base branch")
    source.add_argument("--base", required=True, help="the pull request's base branch")
    source.add_argument("--head", required=True, help="the pull request's head branch")
    source.add_argument("--head-repo", help="owner/name of the repository the head branch lives in")
    source.add_argument("--base-repo", help="owner/name of the repository the base branch lives in")

    template = sub.add_parser("template", help="the required template lines are filled in")
    template.add_argument(
        "--body-file", required=True, help="file holding the pull request body, or - for stdin"
    )

    back_merge = sub.add_parser("back-merge", help="main holds no non-merge commit that dev lacks")
    back_merge.add_argument("--head", required=True, help="the pull request's head branch")
    back_merge.add_argument("--dev-ref", default=f"origin/{PROMOTION_HEAD}")
    back_merge.add_argument("--main-ref", default=f"origin/{GUARDED_BASE}")

    args = ap.parse_args(argv)
    if args.command == "source":
        verdict = check_source(args.base, args.head, args.head_repo, args.base_repo)
    elif args.command == "template":
        verdict = check_template(read_body(args.body_file))
    else:
        unmerged: list[str] = []
        if back_merge_applies(args.head):
            try:
                unmerged = unmerged_commits(args.dev_ref, args.main_ref)
            except GitError as exc:
                print(f"back-merge check could not run: {exc}", file=sys.stderr)
                return COULD_NOT_RUN
        verdict = check_back_merge(args.head, unmerged)

    print(("OK: " if verdict.passed else "FAILED: ") + verdict.message)
    return verdict.exit_code


if __name__ == "__main__":
    sys.exit(main())
