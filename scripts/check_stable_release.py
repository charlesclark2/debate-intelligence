# /// script
# dependencies = ["pyyaml>=6"]
# ///
"""Refuse a stable tag that is not a validated release of `main` (v1-e09-t06-packaging-release).

`.github/workflows/release.yml` runs this when a `vX.Y.Z` tag is pushed, before anything is built.
A stable release is the build the team installs, so its tag must name a commit that reached `main`
the one way production is reached (docs/process/branching-and-environments.md): a dev → main
promotion, validated in dev. Each check below is named, and a refusal says which failed and why:

  stable-tag       the tag is `vX.Y.Z`: never a `vX.Y.Z-dev.N` pre-release tag, which v1-e01-t09's
                   dev channel owns, nor anything else that starts with a v
  on-main          the tagged commit is on main's first-parent line: a commit `main` itself pointed
                   at, not a dev commit that a promotion merged into it
  promotion-merge  the commit is the merge commit of a merged pull request from this repository's
                   `dev` into `main`, whose head is the commit's second parent (its dev parent)
  validate-dev     the dev parent's newest `validate-dev` commit status is `success` and was posted
                   by GitHub Actions: the status protect-main required when the promotion merged
  version          the tag names the version source, packages/debate_cli/pyproject.toml, and every
                   workspace pyproject carries that version (release_version.py)
  epics            plan_specs/releases/vX.Y.yaml exists and each epic it lists is Succeeded, by
                   the rule of `validate_specs.py --require-succeeded`
  changelog        CHANGELOG.md has a `## vX.Y.Z` section that no longer says "Not yet released";
                   it becomes the release's notes (`notes`, below)
  full-suite       CI's push run on `main` for the commit concluded `success`. A push to main runs
                   the whole default test selection (working agreement 10), so this is the full
                   suite, run once on exactly this commit, reused rather than run a second time. A
                   run still in progress is waited for, up to --wait-minutes; the offline slow tier
                   and the smoke tier ran on the dev parent, which `validate-dev` records

The checks that need nothing from GitHub run first. Git reads the checkout, which the workflow
fetches whole; GitHub is read through `gh api` with the workflow's GITHUB_TOKEN, which the workflow
grants read scopes alone (`contents`, `pull-requests`, `statuses`, `actions`). Nothing here writes.

Exit codes: 0 every check passed, 1 at least one refused, 2 a check could not run (git or gh
failed), in which case nothing is known to have passed.

Usage:
  uv run scripts/check_stable_release.py check --tag v1.5.0 --sha <commit> --repository owner/name
  uv run scripts/check_stable_release.py notes --tag v1.5.0 > release-notes.md

`check` appends `tag=`, `version=` and `sha=` to $GITHUB_OUTPUT when it passes, and a table of the
checks to $GITHUB_STEP_SUMMARY, when those are set.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

SCRIPTS = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import release_version  # noqa: E402
import validate_specs  # noqa: E402

MAIN = "main"
DEV = "dev"
VALIDATE_DEV_CONTEXT = "validate-dev"
GITHUB_ACTIONS_LOGIN = "github-actions[bot]"
"""Who posts `validate-dev` (validate-dev.yml, with the workflow token): a status anyone else posted
under that context is not the validation protect-main requires."""
CI_WORKFLOW = "ci.yml"
CHANGELOG = Path("CHANGELOG.md")
NOT_YET_RELEASED = "Not yet released"
"""What a CHANGELOG section says until the PM writes it at the release's close-out."""
RELEASE_SPECS = Path("plan_specs/releases")
COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")

DEFAULT_WAIT_MINUTES = 50
"""How long `full-suite` waits for CI's push run: its longest chain on a push is five jobs (changes,
test-selection, test, coverage, ci), each limited to 10 minutes, so a run that passes has ended."""
POLL_SECONDS = 30

PASSED, REFUSED, COULD_NOT_RUN = 0, 1, 2


class CheckError(Exception):
    """A check could not run: git or GitHub failed, so its answer is unknown."""


@dataclass(frozen=True)
class Outcome:
    check: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class PullRequest:
    number: int
    merged: bool
    merge_commit_sha: str
    base_ref: str
    head_ref: str
    head_sha: str
    head_repo: str


@dataclass(frozen=True)
class CommitStatus:
    context: str
    state: str
    creator: str


@dataclass(frozen=True)
class WorkflowRun:
    run_id: int
    head_branch: str
    status: str
    conclusion: str
    url: str


class GitHub(Protocol):
    """What the checks read from GitHub: `gh api` in production, a fake in tests."""

    def pull_requests_of(self, sha: str) -> list[PullRequest]:
        """The pull requests GitHub associates with `sha`, merged or not."""
        ...

    def statuses(self, sha: str) -> list[CommitStatus]:
        """Every commit status on `sha`, newest first."""
        ...

    def ci_push_runs(self, sha: str) -> list[WorkflowRun]:
        """ci.yml's runs for a push of `sha`, newest first."""
        ...


class History(Protocol):
    """The commit graph: git over the checkout in production."""

    def first_parent_line(self, ref: str) -> set[str]:
        """Every commit `ref` has pointed at, following first parents."""
        ...

    def parents(self, sha: str) -> list[str]: ...


# ------------------------------------------------------------------------------------------------
# The checks
# ------------------------------------------------------------------------------------------------


def check_stable_tag(tag: str) -> Outcome:
    release = release_version.Release.from_stable_tag(tag)
    if release is None:
        return Outcome(
            "stable-tag",
            False,
            f"{tag!r} is not a stable tag vX.Y.Z; dev pre-releases (vX.Y.Z-dev.N) are published by "
            "dev-prerelease.yml, and nothing else is released",
        )
    return Outcome("stable-tag", True, f"{tag} names version {release}")


def check_on_main(history: History, sha: str, main_ref: str) -> Outcome:
    if sha in history.first_parent_line(main_ref):
        return Outcome("on-main", True, f"{sha} is on {MAIN}'s first-parent line")
    return Outcome(
        "on-main",
        False,
        f"{sha} is not a commit {MAIN} has pointed at ({main_ref}, first parents): a stable tag goes "
        f"on the merge commit of a promotion into {MAIN}, never on a dev or task commit",
    )


def check_promotion_merge(history: History, github: GitHub, sha: str, repository: str) -> Outcome:
    parents = history.parents(sha)
    if len(parents) != 2:
        return Outcome(
            "promotion-merge",
            False,
            f"{sha} has {len(parents)} parent(s), so it is not the merge commit of a promotion; a "
            f"{DEV} → {MAIN} promotion is merged with a merge commit",
        )
    dev_parent = parents[1]
    merged = [pull for pull in github.pull_requests_of(sha) if pull.merged and pull.merge_commit_sha == sha]
    if not merged:
        return Outcome("promotion-merge", False, f"no merged pull request has {sha} as its merge commit")
    pull = merged[0]
    where = f"#{pull.number} merged {pull.head_repo}:{pull.head_ref} into {pull.base_ref}"
    if pull.base_ref != MAIN or pull.head_ref != DEV or pull.head_repo != repository:
        return Outcome(
            "promotion-merge",
            False,
            f"{where}; only a promotion of {repository}:{DEV} into {MAIN} is released (a hotfix or "
            "site change reaches a release through the next promotion)",
        )
    if pull.head_sha != dev_parent:
        return Outcome(
            "promotion-merge",
            False,
            f"{where}, but its head {pull.head_sha} is not {sha}'s second parent {dev_parent}",
        )
    return Outcome("promotion-merge", True, f"{where}; its dev parent is {dev_parent}")


def check_validate_dev(github: GitHub, dev_parent: str) -> Outcome:
    newest = next(
        (status for status in github.statuses(dev_parent) if status.context == VALIDATE_DEV_CONTEXT), None
    )
    if newest is None:
        return Outcome(
            "validate-dev", False, f"the dev parent {dev_parent} has no {VALIDATE_DEV_CONTEXT} status"
        )
    if newest.creator != GITHUB_ACTIONS_LOGIN:
        return Outcome(
            "validate-dev",
            False,
            f"the newest {VALIDATE_DEV_CONTEXT} status on {dev_parent} was posted by {newest.creator}, "
            f"not {GITHUB_ACTIONS_LOGIN}",
        )
    if newest.state != "success":
        return Outcome(
            "validate-dev",
            False,
            f"the newest {VALIDATE_DEV_CONTEXT} status on the dev parent {dev_parent} is {newest.state}",
        )
    return Outcome("validate-dev", True, f"{VALIDATE_DEV_CONTEXT} is success on the dev parent {dev_parent}")


def check_version(tag: str, root: Path) -> Outcome:
    try:
        source = release_version.read_version_source(root)
    except release_version.ReleaseVersionError as error:
        return Outcome("version", False, str(error))
    problems = release_version.workspace_version_mismatches(root)
    if f"v{source}" != tag:
        problems.insert(
            0, f"{tag} does not name {release_version.VERSION_SOURCE.as_posix()}'s version {source}"
        )
    if problems:
        return Outcome("version", False, "; ".join(problems))
    return Outcome("version", True, f"every workspace pyproject is at {source}")


def release_of(tag: str) -> str:
    """`v1.5.0` → `v1.5`: the release spec a stable tag belongs to, its patches included."""
    release = release_version.Release.from_stable_tag(tag)
    if release is None:
        raise ValueError(f"{tag!r} is not a stable tag")
    return f"v{release.major}.{release.minor}"


def require_succeeded(root: Path, name: str) -> bool:
    """`validate_specs.py --require-succeeded NAME --root ROOT`, in process; its line is discarded."""
    with contextlib.redirect_stdout(io.StringIO()):
        return validate_specs.main(["--root", str(root), "--require-succeeded", name]) == 0


def check_epics(tag: str, root: Path) -> Outcome:
    release = release_of(tag)
    spec = RELEASE_SPECS / f"{release}.yaml"
    tree = validate_specs.collect(root)
    if release not in tree.release_epics:
        return Outcome("epics", False, f"no release spec {spec.as_posix()} for {tag}")
    epics = tree.release_epics[release]
    if not epics:
        return Outcome("epics", False, f"{spec.as_posix()} lists no epics")
    unfinished = [
        f"{epic} is {tree.phase(epic) if epic in tree.goals else 'not a Goal'}"
        for epic in epics
        if epic is None or not require_succeeded(root, epic)
    ]
    if unfinished:
        return Outcome("epics", False, f"{spec.as_posix()}: " + "; ".join(unfinished))
    return Outcome("epics", True, f"{spec.as_posix()}: {', '.join(str(epic) for epic in epics)} Succeeded")


def changelog_section(text: str, tag: str) -> tuple[str, str] | None:
    """(heading, body) of the `## <tag>` section, the body ending at the next `## ` heading."""
    heading = re.compile(rf"^## {re.escape(tag)}(?=$|[:\s])")
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if heading.match(line):
            body: list[str] = []
            for following in lines[index + 1 :]:
                if following.startswith("## "):
                    break
                body.append(following)
            return line.removeprefix("## ").strip(), "\n".join(body).strip() + "\n"
    return None


def check_changelog(tag: str, root: Path) -> Outcome:
    path = root / CHANGELOG
    section = changelog_section(path.read_text(encoding="utf-8"), tag) if path.is_file() else None
    if section is None:
        return Outcome("changelog", False, f"{CHANGELOG} has no `## {tag}` section for the release notes")
    if NOT_YET_RELEASED in section[1]:
        return Outcome(
            "changelog",
            False,
            f"{CHANGELOG}'s {tag} section still says {NOT_YET_RELEASED!r}; write it before tagging",
        )
    return Outcome("changelog", True, f"{CHANGELOG} has the {tag} section: {section[0]}")


def check_full_suite(
    github: GitHub,
    sha: str,
    *,
    wait_seconds: float,
    poll_seconds: float = POLL_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> Outcome:
    deadline = clock() + wait_seconds
    while True:
        runs = [run for run in github.ci_push_runs(sha) if run.head_branch == MAIN]
        if not runs:
            return Outcome(
                "full-suite",
                False,
                f"CI ({CI_WORKFLOW}) has no push run on {MAIN} for {sha}, so the whole test selection "
                "never ran on it",
            )
        newest = runs[0]
        if newest.status == "completed":
            if newest.conclusion == "success":
                return Outcome("full-suite", True, f"CI's push run on {MAIN} passed: {newest.url}")
            return Outcome(
                "full-suite",
                False,
                f"CI's push run on {MAIN} for {sha} concluded {newest.conclusion}: {newest.url}",
            )
        if clock() >= deadline:
            return Outcome(
                "full-suite",
                False,
                f"CI's push run on {MAIN} for {sha} is still {newest.status} after the wait: {newest.url}; "
                "re-run this workflow once it has passed",
            )
        sleep(poll_seconds)


def run_checks(
    *,
    tag: str,
    sha: str,
    repository: str,
    root: Path,
    history: History,
    github: GitHub,
    main_ref: str,
    wait_seconds: float,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> list[Outcome]:
    """Every check's outcome, in order. A malformed tag stops them: each later one reads its version."""
    outcomes = [check_stable_tag(tag)]
    if not outcomes[0].passed:
        return outcomes
    outcomes += [check_version(tag, root), check_epics(tag, root), check_changelog(tag, root)]
    outcomes.append(check_on_main(history, sha, main_ref))
    promotion = check_promotion_merge(history, github, sha, repository)
    outcomes.append(promotion)
    if promotion.passed:
        outcomes.append(check_validate_dev(github, history.parents(sha)[1]))
    else:
        outcomes.append(Outcome("validate-dev", False, "not checked: the commit is not a promotion merge"))
    outcomes.append(check_full_suite(github, sha, wait_seconds=wait_seconds, sleep=sleep, clock=clock))
    return outcomes


# ------------------------------------------------------------------------------------------------
# git and gh
# ------------------------------------------------------------------------------------------------


class GitHistory:
    def __init__(self, repository: Path = REPOSITORY_ROOT) -> None:
        self.repository = repository

    def _git(self, *arguments: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(self.repository), *arguments], capture_output=True, text=True, check=False
        )
        if completed.returncode != 0:
            raise CheckError(f"git {' '.join(arguments)} failed: {completed.stderr.strip()}")
        return completed.stdout

    def first_parent_line(self, ref: str) -> set[str]:
        if self._git("rev-parse", "--is-shallow-repository").strip() == "true":
            raise CheckError("the checkout is shallow, so main's history is incomplete; fetch it whole")
        return set(self._git("rev-list", "--first-parent", ref).split())

    def parents(self, sha: str) -> list[str]:
        return self._git("rev-list", "--parents", "-n", "1", sha).split()[1:]


class GhCli:
    """:class:`GitHub` through `gh api`, authenticated by GH_TOKEN."""

    def __init__(
        self, repository: str, runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run
    ) -> None:
        self.repository = repository
        self._run = runner

    def _json(self, *arguments: str) -> Any:
        try:
            completed = self._run(["gh", "api", *arguments], capture_output=True, text=True, check=False)
        except OSError as error:
            raise CheckError(f"could not run gh: {error}") from error
        if completed.returncode != 0:
            raise CheckError(f"gh api {' '.join(arguments)} failed: {completed.stderr.strip()}")
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise CheckError(f"gh api {' '.join(arguments)} returned no JSON: {error}") from error

    def pull_requests_of(self, sha: str) -> list[PullRequest]:
        pulls = self._json(f"repos/{self.repository}/commits/{sha}/pulls?per_page=100")
        return [
            PullRequest(
                number=int(pull["number"]),
                merged=pull.get("merged_at") is not None,
                merge_commit_sha=pull.get("merge_commit_sha") or "",
                base_ref=pull["base"]["ref"],
                head_ref=pull["head"]["ref"],
                head_sha=pull["head"]["sha"],
                head_repo=(pull["head"].get("repo") or {}).get("full_name") or "",
            )
            for pull in pulls
        ]

    def statuses(self, sha: str) -> list[CommitStatus]:
        # Newest first, as GitHub returns them; --slurp gathers every page into one array of pages.
        pages = self._json(
            "--paginate", "--slurp", f"repos/{self.repository}/commits/{sha}/statuses?per_page=100"
        )
        return [
            CommitStatus(
                context=status["context"],
                state=status["state"],
                creator=(status.get("creator") or {}).get("login") or "",
            )
            for page in pages
            for status in page
        ]

    def ci_push_runs(self, sha: str) -> list[WorkflowRun]:
        listing = self._json(
            f"repos/{self.repository}/actions/workflows/{CI_WORKFLOW}/runs?event=push&head_sha={sha}&per_page=100"
        )
        runs = sorted(listing.get("workflow_runs", []), key=lambda run: str(run["created_at"]), reverse=True)
        return [
            WorkflowRun(
                run_id=int(run["id"]),
                head_branch=run.get("head_branch") or "",
                status=run.get("status") or "",
                conclusion=run.get("conclusion") or "",
                url=run.get("html_url") or "",
            )
            for run in runs
        ]


# ------------------------------------------------------------------------------------------------
# Command line
# ------------------------------------------------------------------------------------------------


def _append(variable: str, text: str) -> None:
    path = os.environ.get(variable)
    if path:
        with Path(path).open("a", encoding="utf-8") as handle:
            handle.write(text)


def summary(tag: str, sha: str, outcomes: Sequence[Outcome]) -> str:
    rows = "".join(
        f"| {outcome.check} | {'pass' if outcome.passed else '**refused**'} | "
        f"{outcome.detail.replace('|', '/')} |\n"
        for outcome in outcomes
    )
    return f"### Release checks for {tag} at `{sha}`\n\n| Check | Result | Detail |\n|---|---|---|\n{rows}\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n", 1)[0])
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="refuse a tag that is not a validated release of main")
    check.add_argument("--tag", required=True)
    check.add_argument("--sha", required=True, help="the tagged commit (full SHA)")
    check.add_argument("--repository", required=True, help="owner/name")
    check.add_argument("--root", type=Path, default=REPOSITORY_ROOT, help="the checkout of the tagged commit")
    check.add_argument("--main-ref", default=f"origin/{MAIN}")
    check.add_argument("--wait-minutes", type=float, default=DEFAULT_WAIT_MINUTES)
    notes = commands.add_parser("notes", help="print the tag's CHANGELOG section, the release notes")
    notes.add_argument("--tag", required=True)
    notes.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.command == "notes":
        outcome = check_changelog(arguments.tag, arguments.root)
        if not outcome.passed:
            print(f"check_stable_release: {outcome.detail}", file=sys.stderr)
            return REFUSED
        section = changelog_section((arguments.root / CHANGELOG).read_text(encoding="utf-8"), arguments.tag)
        assert section is not None
        print(section[1], end="")
        return PASSED

    sha = arguments.sha.strip()
    if not COMMIT_SHA.match(sha):
        print(
            f"check_stable_release: --sha must be a full 40-character commit SHA, got {sha!r}",
            file=sys.stderr,
        )
        return COULD_NOT_RUN
    try:
        outcomes = run_checks(
            tag=arguments.tag,
            sha=sha,
            repository=arguments.repository,
            root=arguments.root,
            history=GitHistory(arguments.root),
            github=GhCli(arguments.repository),
            main_ref=arguments.main_ref,
            wait_seconds=arguments.wait_minutes * 60,
        )
    except CheckError as error:
        print(f"check_stable_release: could not run the checks: {error}", file=sys.stderr)
        return COULD_NOT_RUN
    for outcome in outcomes:
        print(f"{'pass' if outcome.passed else 'REFUSED'} {outcome.check}: {outcome.detail}")
    _append("GITHUB_STEP_SUMMARY", summary(arguments.tag, sha, outcomes))
    refused = [outcome.check for outcome in outcomes if not outcome.passed]
    if refused:
        print(
            f"check_stable_release: {arguments.tag} is not released: {', '.join(refused)} refused",
            file=sys.stderr,
        )
        return REFUSED
    release = release_version.Release.from_stable_tag(arguments.tag)
    _append("GITHUB_OUTPUT", f"tag={arguments.tag}\nversion={release}\nsha={sha}\n")
    return PASSED


if __name__ == "__main__":
    sys.exit(main())
