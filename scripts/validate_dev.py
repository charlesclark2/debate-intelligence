# /// script
# requires-python = ">=3.11"
# ///
"""Validate one commit's dev pre-release and post the `validate-dev` status (v1-e01-t10).

"Validated in dev" (docs/process/branching-and-environments.md) means: the pre-release built from
this exact commit was installed the way a coach installs it, it reported that commit, and the smoke
suite passed against that installed binary, never against a source tree. protect-main requires a
green `validate-dev` status on a promotion's head commit, so this script is the only thing that may
turn it green, and only on the commit it installed.

Subcommands, in the order .github/workflows/validate-dev.yml runs them:

``resolve``
    Post ``pending`` on the commit (with ``--post-status``), then find its published dev
    pre-release: the ``vX.Y.Z-dev.N`` tag pointing at exactly that commit (``--tag`` to name one).
``smoke``
    Install that tag with ``scripts/install_channel.sh`` into a scratch ``UV_TOOL_DIR`` and
    ``UV_TOOL_BIN_DIR``. The installer downloads the assets, verifies ``SHA256SUMS`` and the wheels'
    provenance, and fails on an incomplete build; none of that is repeated here. Then assert that
    the installed ``debate-research --version --json``, with ``DEBATE_ENV`` unset, reports this
    commit, this tag and channel ``dev``, and run the recorded smoke tier against that binary
    (``-m "not live and not in_process"``) and, with ``--live``, the canary tier
    (``-m "live and canary"``).
``slow``
    From a checkout of the same commit, run the offline slow tier,
    ``-m "slow and not live and not eval"``. The parser evaluation (``eval``) is excluded: it needs
    the evaluation corpus, which by policy never reaches a runner, so there it could only skip. It
    runs on the operator's Mac before any promotion that changes the parser (v1-e31-t05).
``conclude``
    Post the final state. ``success`` only when every job succeeded, the installed build reported
    the requested commit, and both test trees were that commit; ``success`` is posted on the commit
    the installed build reported, which by then is the requested one. Anything else posts
    ``failure`` (``error`` if the run was cancelled) on the requested commit.
``run``
    All of the above in one process, for an operator's rehearsal or a caller with one job.

**A skipped test fails its tier.** A tier passes only when pytest exits 0, wrote its JUnit report,
ran at least one test, and that report shows no failure, no error and no skip (an expected failure
counts as a skip). A check skipped for a missing fixture is a check that did not run, and the task
spec forbids a green status built on one.

Every ``gh`` call goes through :class:`GhCli`, behind the :class:`GitHub` protocol, so
tests/scripts/test_validate_dev.py drives everything here offline.

Exit status: 0 when the step passed, 1 when it found a problem, 2 for a usage error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ElementTree
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPOSITORY = "charlesclark2/debate-intelligence"
STATUS_CONTEXT = "validate-dev"
CHANNEL = "dev"

FULL_SHA = re.compile(r"[0-9a-f]{40}")
DEV_TAG = re.compile(r"v(?P<x>0|[1-9]\d*)\.(?P<y>0|[1-9]\d*)\.(?P<z>0|[1-9]\d*)-dev\.(?P<n>[1-9]\d*)")
DESCRIPTION_LIMIT = 140  # the statuses API refuses a longer description

PASSED, PROBLEM = 0, 1

#: Variables never passed on to the code under test. The smoke job holds only `contents: read`,
#: but the tests of the commit being validated have no business with any token.
WITHHELD = ("GH_TOKEN", "GITHUB_TOKEN", "ACTIONS_RUNTIME_TOKEN", "ACTIONS_ID_TOKEN_REQUEST_TOKEN")

PYTEST = ("uv", "run", "--frozen", "pytest")
INSTALLER = ("sh", str(REPO_ROOT / "scripts" / "install_channel.sh"))


class ValidationProblem(Exception):
    """Something this commit's validation found wrong. The message says what."""


# --------------------------------------------------------------------------------------------
# The GitHub API, behind a protocol
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Release:
    tag: str
    is_prerelease: bool
    is_draft: bool


class GitHub(Protocol):
    def dev_tags_at(self, sha: str) -> list[str]:
        """Every `vX.Y.Z-dev.N` tag that points at the commit `sha`."""
        ...

    def tag_commit(self, tag: str) -> str | None:
        """The commit `tag` points at, or None when there is no such tag."""
        ...

    def release(self, tag: str) -> Release | None:
        """The GitHub release published for `tag`, or None when there is none."""
        ...

    def post_status(self, sha: str, state: str, target_url: str, description: str) -> None:
        """Create a `validate-dev` commit status on `sha`."""
        ...


class GhCli:
    """:class:`GitHub` through the `gh` command line, authenticated by `GH_TOKEN`."""

    def __init__(
        self, repository: str, runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run
    ):
        self.repository = repository
        self._run = runner

    def _gh(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return self._run(["gh", *arguments], capture_output=True, text=True, check=False)

    def _api(self, *arguments: str) -> str:
        completed = self._gh("api", *arguments)
        if completed.returncode != 0:
            raise ValidationProblem(f"gh api {' '.join(arguments)} failed: {completed.stderr.strip()}")
        return completed.stdout

    def _tags(self) -> list[tuple[str, str, str]]:
        listing = self._api(
            "--paginate",
            f"repos/{self.repository}/git/matching-refs/tags/v",
            "--jq",
            ".[] | [.ref, .object.type, .object.sha] | @tsv",
        )
        rows = []
        for line in listing.splitlines():
            ref, kind, sha = line.split("\t")
            rows.append((ref.removeprefix("refs/tags/"), kind, sha))
        return rows

    def _commit_of(self, kind: str, sha: str) -> str:
        # Release tags are lightweight (scripts/release_version.py); an annotated one is followed.
        if kind == "tag":
            return self._api(f"repos/{self.repository}/git/tags/{sha}", "--jq", ".object.sha").strip()
        return sha

    def dev_tags_at(self, sha: str) -> list[str]:
        return [
            tag
            for tag, kind, target in self._tags()
            if DEV_TAG.fullmatch(tag) and self._commit_of(kind, target) == sha
        ]

    def tag_commit(self, tag: str) -> str | None:
        for name, kind, target in self._tags():
            if name == tag:
                return self._commit_of(kind, target)
        return None

    def release(self, tag: str) -> Release | None:
        completed = self._gh(
            "release", "view", tag, "--repo", self.repository, "--json", "tagName,isPrerelease,isDraft"
        )
        if completed.returncode != 0:
            if "not found" in completed.stderr.lower():
                return None
            raise ValidationProblem(f"gh release view {tag} failed: {completed.stderr.strip()}")
        document = json.loads(completed.stdout)
        return Release(document["tagName"], bool(document["isPrerelease"]), bool(document["isDraft"]))

    def post_status(self, sha: str, state: str, target_url: str, description: str) -> None:
        self._api(
            "--method",
            "POST",
            f"repos/{self.repository}/statuses/{sha}",
            "-f",
            f"state={state}",
            "-f",
            f"target_url={target_url}",
            "-f",
            f"description={description}",
            "-f",
            f"context={STATUS_CONTEXT}",
        )


# --------------------------------------------------------------------------------------------
# resolve: which pre-release is this commit's
# --------------------------------------------------------------------------------------------


def require_sha(sha: str) -> str:
    if not FULL_SHA.fullmatch(sha):
        raise ValidationProblem(f"{sha!r} is not a full 40-character commit SHA")
    return sha


def tag_order(tag: str) -> tuple[int, int, int, int]:
    match = DEV_TAG.fullmatch(tag)
    if not match:
        raise ValidationProblem(f"{tag!r} is not a dev pre-release tag (vX.Y.Z-dev.N)")
    return int(match["x"]), int(match["y"]), int(match["z"]), int(match["n"])


def wheel_version(tag: str) -> str:
    """vX.Y.Z-dev.N → X.Y.Z.devN, the version the installed build reports."""
    x, y, z, n = tag_order(tag)
    return f"{x}.{y}.{z}.dev{n}"


def is_published_prerelease(release: Release | None) -> bool:
    return release is not None and release.is_prerelease and not release.is_draft


def resolve_prerelease(github: GitHub, sha: str, tag: str | None = None) -> str:
    """The published dev pre-release tag for exactly `sha`."""
    require_sha(sha)
    if tag:
        tag_order(tag)
        commit = github.tag_commit(tag)
        if commit is None:
            raise ValidationProblem(f"there is no tag {tag}")
        if commit != sha:
            raise ValidationProblem(f"{tag} points at {commit}, not at {sha}")
        if not is_published_prerelease(github.release(tag)):
            raise ValidationProblem(f"{tag} has no published pre-release")
        return tag
    published = [
        candidate
        for candidate in github.dev_tags_at(sha)
        if is_published_prerelease(github.release(candidate))
    ]
    if not published:
        raise ValidationProblem(
            f"no published dev pre-release points at {sha}; dev-prerelease.yml builds one after a "
            "green ci on dev, or on a dispatch for a hotfix/* head"
        )
    return max(published, key=tag_order)


# --------------------------------------------------------------------------------------------
# smoke: install the tag, check what it says it is, run the suite against it
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Tier:
    name: str
    marker_expression: str
    paths: tuple[str, ...] = ()


RECORDED = Tier("recorded", "not live and not in_process", ("tests/smoke",))
LIVE_CANARY = Tier("live canary", "live and canary", ("tests/smoke",))
SLOW = Tier("slow", "slow and not live and not eval")


@dataclass(frozen=True)
class JUnitCounts:
    tests: int
    failures: int
    errors: int
    skipped: int
    skipped_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class TierResult:
    name: str
    exit_code: int
    counts: JUnitCounts | None

    @property
    def problems(self) -> list[str]:
        return tier_problems(self)

    @property
    def passed(self) -> bool:
        return not self.problems


def read_junit(path: Path) -> JUnitCounts | None:
    """The totals of a pytest JUnit report, or None when there is no readable report."""
    try:
        root = ElementTree.parse(path).getroot()
    except (OSError, ElementTree.ParseError):
        return None
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    skipped_names = tuple(
        f"{case.get('classname')}::{case.get('name')}: {(case.find('skipped').get('message') or '').strip()}"  # type: ignore[union-attr]
        for suite in suites
        for case in suite.iter("testcase")
        if case.find("skipped") is not None
    )
    return JUnitCounts(
        tests=sum(int(suite.get("tests", 0)) for suite in suites),
        failures=sum(int(suite.get("failures", 0)) for suite in suites),
        errors=sum(int(suite.get("errors", 0)) for suite in suites),
        skipped=sum(int(suite.get("skipped", 0)) for suite in suites),
        skipped_names=skipped_names,
    )


def tier_problems(result: TierResult) -> list[str]:
    """Why a tier did not pass; empty when it did. A skip is a failure here."""
    counts = result.counts
    if counts is None:
        return [f"{result.name} tier: pytest wrote no JUnit report (exit {result.exit_code})"]
    problems = []
    if result.exit_code != 0:
        problems.append(f"{result.name} tier: pytest exited {result.exit_code}")
    if counts.tests == 0:
        problems.append(f"{result.name} tier: no tests ran, and an empty tier proves nothing")
    if counts.failures or counts.errors:
        problems.append(f"{result.name} tier: {counts.failures} failed, {counts.errors} errors")
    if counts.skipped:
        problems.append(
            f"{result.name} tier: {counts.skipped} skipped; a skipped check did not run, so validate-dev "
            "counts it as a failure:\n    " + "\n    ".join(counts.skipped_names)
        )
    return problems


def run_tier(
    tier: Tier,
    junit: Path,
    environment: Mapping[str, str],
    *,
    pytest_command: Sequence[str] = PYTEST,
    cwd: Path = REPO_ROOT,
) -> TierResult:
    """Run one tier with pytest, its output going straight to the log."""
    command = [
        *pytest_command,
        *tier.paths,
        "-m",
        tier.marker_expression,
        "--no-cov",
        f"--junitxml={junit}",
        "-o",
        "junit_family=xunit2",
        "-p",
        "no:cacheprovider",
        "-rfEs",
    ]
    print(f"\n== {tier.name} tier: {' '.join(command)}", flush=True)
    completed = subprocess.run(command, cwd=cwd, env=dict(environment), check=False)
    result = TierResult(tier.name, completed.returncode, read_junit(junit))
    print(f"== {tier.name} tier: {'passed' if result.passed else 'FAILED'}", flush=True)
    for problem in result.problems:
        print(f"   {problem}", flush=True)
    return result


def environment_for_tests(environ: Mapping[str, str]) -> dict[str, str]:
    """pytest's environment: no token, no inherited DEBATE_* setting, no other project's venv."""
    return {
        name: value
        for name, value in environ.items()
        if name not in WITHHELD and name != "VIRTUAL_ENV" and not name.startswith("DEBATE_")
    }


def tree_commit(cwd: Path = REPO_ROOT) -> str:
    """The commit this checkout's tests come from, marked `-dirty` if it has changes."""
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True, check=True)
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return head.stdout.strip() + ("-dirty" if status.stdout.strip() else "")


def install_prerelease(
    tag: str,
    work: Path,
    *,
    installer: Sequence[str] = INSTALLER,
    environment: Mapping[str, str] | None = None,
) -> Path:
    """Install `tag` with scripts/install_channel.sh into a tool directory under `work`."""
    tools, bin_dir = work / "tools", work / "bin"
    env = dict(os.environ if environment is None else environment)
    env |= {"UV_TOOL_DIR": str(tools), "UV_TOOL_BIN_DIR": str(bin_dir)}
    print(f"== installing {tag} into {tools} with {' '.join(installer)}", flush=True)
    completed = subprocess.run([*installer, tag], env=env, check=False)
    if completed.returncode != 0:
        raise ValidationProblem(f"scripts/install_channel.sh {tag} failed (exit {completed.returncode})")
    binary = bin_dir / "debate-research"
    if not binary.is_file():
        raise ValidationProblem(f"the installer succeeded but {binary} does not exist")
    return binary


def installed_identity(binary: Path, home: Path) -> dict[str, object]:
    """`--version --json` of the installed build, with DEBATE_ENV unset and a scratch HOME.

    DEBATE_ENV is left out on purpose: an exported DEBATE_ENV measures the shell, not the build
    (v1-e01-t09's closing note).
    """
    home.mkdir(parents=True, exist_ok=True)
    environment = {"PATH": os.environ.get("PATH", ""), "HOME": str(home), "NO_COLOR": "1"}
    completed = subprocess.run(
        [str(binary), "--version", "--json"],
        cwd=home,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ValidationProblem(f"{binary} --version --json failed: {completed.stderr.strip()}")
    data = json.loads(completed.stdout)["data"]
    if not isinstance(data, dict):
        raise ValidationProblem(f"{binary} --version --json printed no data object")
    return data


def identity_problems(identity: Mapping[str, object], sha: str, tag: str) -> list[str]:
    """How the installed build's account of itself differs from what was asked for."""
    expected = {
        "commit": sha,
        "tag": tag,
        "channel": CHANNEL,
        "version": wheel_version(tag),
        "environment": "dev",
        "environment_source": "build-channel:dev",
    }
    return [
        f"the installed build reports {key} {identity.get(key)!r}, expected {value!r}"
        for key, value in expected.items()
        if identity.get(key) != value
    ]


@dataclass
class SmokeReport:
    sha: str
    tag: str
    tests_commit: str
    installed_commit: str | None = None
    identity: dict[str, object] = field(default_factory=dict)
    tiers: list[dict[str, object]] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.problems


def smoke(
    sha: str,
    tag: str,
    work: Path,
    *,
    live: bool = False,
    rehearsal: bool = False,
    installer: Sequence[str] = INSTALLER,
    pytest_command: Sequence[str] = PYTEST,
    tiers: Sequence[Tier] = (RECORDED,),
    live_tiers: Sequence[Tier] = (LIVE_CANARY,),
    cwd: Path = REPO_ROOT,
) -> SmokeReport:
    """Install `tag`, check it is the build of `sha`, and run the smoke tiers against it."""
    require_sha(sha)
    report = SmokeReport(sha=sha, tag=tag, tests_commit=tree_commit(cwd))
    if report.tests_commit != sha and not rehearsal:
        report.problems.append(
            f"the smoke tests come from {report.tests_commit}, not {sha}; check out the validated commit"
        )
        return report
    try:
        binary = install_prerelease(tag, work, installer=installer)
        report.identity = installed_identity(binary, work / "version-home")
    except ValidationProblem as problem:
        report.problems.append(str(problem))
        return report
    commit = report.identity.get("commit")
    report.installed_commit = commit if isinstance(commit, str) else None
    print(f"== installed build: {json.dumps(report.identity, sort_keys=True)}", flush=True)
    print(
        f"== installed {report.identity.get('version')} from {tag}: commit {report.installed_commit}, "
        f"validating {sha}",
        flush=True,
    )
    report.problems.extend(identity_problems(report.identity, sha, tag))
    if report.problems:
        return report

    environment = environment_for_tests(os.environ)
    environment |= {
        "DEBATE_SMOKE_BIN": str(binary),
        "DEBATE_SMOKE_EXPECT_SHA": sha,
        "DEBATE_SMOKE_EXPECT_TAG": tag,
    }
    for tier in [*tiers, *(live_tiers if live else ())]:
        junit = work / f"junit-{tier.name.replace(' ', '-')}.xml"
        result = run_tier(tier, junit, environment, pytest_command=pytest_command, cwd=cwd)
        report.tiers.append(
            {
                "name": result.name,
                "exit_code": result.exit_code,
                "counts": asdict(result.counts) if result.counts else None,
            }
        )
        report.problems.extend(result.problems)
    return report


# --------------------------------------------------------------------------------------------
# slow: the offline slow tier, from the source at the same commit
# --------------------------------------------------------------------------------------------


@dataclass
class SlowReport:
    sha: str
    tests_commit: str
    tier: dict[str, object] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.problems


def slow(
    sha: str, work: Path, *, pytest_command: Sequence[str] = PYTEST, tier: Tier = SLOW, cwd: Path = REPO_ROOT
) -> SlowReport:
    require_sha(sha)
    report = SlowReport(sha=sha, tests_commit=tree_commit(cwd))
    if report.tests_commit != sha:
        report.problems.append(
            f"the slow tier would run {report.tests_commit}, not {sha}; check out the validated commit"
        )
        return report
    environment = environment_for_tests(os.environ)
    result = run_tier(tier, work / "junit-slow.xml", environment, pytest_command=pytest_command, cwd=cwd)
    report.tier = {
        "name": result.name,
        "exit_code": result.exit_code,
        "counts": asdict(result.counts) if result.counts else None,
    }
    report.problems.extend(result.problems)
    return report


# --------------------------------------------------------------------------------------------
# conclude: the one status this validation posts
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Conclusion:
    sha: str
    """The commit the status goes on."""
    state: str
    description: str


REQUIRED_JOBS = ("resolve", "smoke", "slow")


def conclude(
    requested_sha: str,
    *,
    tag: str | None,
    installed_sha: str | None,
    smoke_commit: str | None,
    slow_commit: str | None,
    jobs: Mapping[str, str],
    required: Sequence[str] = REQUIRED_JOBS,
) -> Conclusion:
    """The final status for `requested_sha`, from what each job reported.

    `success` goes on the commit the installed build reported, and only when that is the requested
    one and both test trees were too. Anything less goes on the requested commit as `failure`, or as
    `error` when the run was cancelled.
    """
    require_sha(requested_sha)
    if any(jobs.get(job) == "cancelled" for job in required):
        return Conclusion(requested_sha, "error", "validation was cancelled before it finished")
    unfinished = [f"{job} {jobs.get(job) or 'did not run'}" for job in required if jobs.get(job) != "success"]
    if unfinished:
        return Conclusion(requested_sha, "failure", "validation failed: " + ", ".join(unfinished))
    for label, commit in (
        ("the installed build reports", installed_sha),
        ("the smoke tests came from", smoke_commit),
        ("the slow tier ran", slow_commit),
    ):
        if commit != requested_sha:
            return Conclusion(requested_sha, "failure", f"{label} {commit or 'nothing'}, not this commit")
    assert installed_sha is not None
    return Conclusion(
        installed_sha,
        "success",
        f"{tag} installed from its pre-release and validated: recorded and slow tiers green",
    )


def post(github: GitHub, conclusion: Conclusion, target_url: str) -> None:
    description = conclusion.description[:DESCRIPTION_LIMIT]
    github.post_status(conclusion.sha, conclusion.state, target_url, description)
    print(f"== posted {STATUS_CONTEXT} {conclusion.state} on {conclusion.sha}: {description}", flush=True)


# --------------------------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------------------------


def run_url(environ: Mapping[str, str]) -> str | None:
    """This workflow run's page, when running in GitHub Actions."""
    try:
        server, repository, run = (
            environ[name] for name in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID")
        )
    except KeyError:
        return None
    return f"{server}/{repository}/actions/runs/{run}"


def write_outputs(path: str | None, values: Mapping[str, str | None]) -> None:
    if not path:
        return
    with open(path, "a", encoding="utf-8") as outputs:  # noqa: PTH123
        for key, value in values.items():
            outputs.write(f"{key}={value or ''}\n")


def write_report(path: str | None, report: object) -> None:
    if path:
        Path(path).write_text(json.dumps(asdict(report), indent=2, sort_keys=True) + "\n", encoding="utf-8")  # type: ignore[call-overload]


def parse_jobs(values: Sequence[str]) -> dict[str, str]:
    jobs = {}
    for value in values:
        name, _, result = value.partition("=")
        jobs[name] = result
    return jobs


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY")
        or os.environ.get("DEBATE_RELEASE_REPO")
        or DEFAULT_REPOSITORY,
    )
    sub = ap.add_subparsers(dest="command", required=True)

    def status_options(parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--post-status", action="store_true", help=f"post the {STATUS_CONTEXT} commit status"
        )
        parser.add_argument("--target-url", help="the run the status links to (default: this Actions run)")

    def work_options(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--work-dir", type=Path, help="scratch directory (default: a new temporary one)")
        parser.add_argument("--report", help="write a JSON report here")
        parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))

    resolve = sub.add_parser("resolve", help="post pending, then find the commit's dev pre-release")
    resolve.add_argument("--sha", required=True)
    resolve.add_argument("--tag")
    resolve.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))
    status_options(resolve)

    smoke_parser = sub.add_parser("smoke", help="install the pre-release and run the smoke suite against it")
    smoke_parser.add_argument("--sha", required=True)
    smoke_parser.add_argument("--tag", required=True)
    smoke_parser.add_argument("--live", action="store_true", help="also run the live canary tier")
    smoke_parser.add_argument(
        "--rehearsal",
        action="store_true",
        help="run this checkout's smoke tests even if it is not the commit being validated; the "
        "report records the difference and conclude refuses it",
    )
    work_options(smoke_parser)

    slow_parser = sub.add_parser("slow", help="run the offline slow tier from a checkout of the commit")
    slow_parser.add_argument("--sha", required=True)
    work_options(slow_parser)

    conclude_parser = sub.add_parser("conclude", help="post the final validate-dev status")
    conclude_parser.add_argument("--sha", required=True, help="the commit that was asked to be validated")
    conclude_parser.add_argument("--tag")
    conclude_parser.add_argument("--installed-sha")
    conclude_parser.add_argument("--smoke-commit")
    conclude_parser.add_argument("--slow-commit")
    conclude_parser.add_argument("--job", action="append", default=[], help="name=result, e.g. smoke=success")
    conclude_parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))
    status_options(conclude_parser)

    run_parser = sub.add_parser("run", help="resolve, smoke, slow and conclude in one process")
    run_parser.add_argument("--sha", required=True)
    run_parser.add_argument("--tag")
    run_parser.add_argument("--live", action="store_true")
    work_options(run_parser)
    status_options(run_parser)
    return ap


def target_for(args: argparse.Namespace) -> str:
    url = args.target_url or run_url(os.environ)
    if args.post_status and not url:
        raise ValidationProblem("--post-status needs --target-url outside GitHub Actions")
    return url or ""


def work_dir(args: argparse.Namespace) -> Path:
    if args.work_dir:
        args.work_dir.mkdir(parents=True, exist_ok=True)
        return Path(args.work_dir)
    return Path(tempfile.mkdtemp(prefix="validate-dev-"))


def main(argv: list[str] | None = None, *, github: GitHub | None = None) -> int:
    args = build_parser().parse_args(argv)
    client = github or GhCli(args.repo)
    try:
        if args.command == "resolve":
            return command_resolve(args, client)
        if args.command == "smoke":
            report = smoke(args.sha, args.tag, work_dir(args), live=args.live, rehearsal=args.rehearsal)
            write_report(args.report, report)
            write_outputs(
                args.github_output,
                {"installed_sha": report.installed_commit, "tests_commit": report.tests_commit},
            )
            return finish("smoke", report.problems)
        if args.command == "slow":
            slow_report = slow(args.sha, work_dir(args))
            write_report(args.report, slow_report)
            write_outputs(args.github_output, {"tests_commit": slow_report.tests_commit})
            return finish("slow", slow_report.problems)
        if args.command == "conclude":
            conclusion = conclude(
                args.sha,
                tag=args.tag,
                installed_sha=args.installed_sha,
                smoke_commit=args.smoke_commit,
                slow_commit=args.slow_commit,
                jobs=parse_jobs(args.job),
            )
            if args.post_status:
                post(client, conclusion, target_for(args))
            write_outputs(args.github_output, {"state": conclusion.state, "status_sha": conclusion.sha})
            print(f"validate-dev: {conclusion.state} on {conclusion.sha}: {conclusion.description}")
            return PASSED if conclusion.state == "success" else PROBLEM
        return command_run(args, client)
    except ValidationProblem as problem:
        print(f"validate-dev: {problem}", file=sys.stderr)
        return PROBLEM


def command_resolve(args: argparse.Namespace, client: GitHub) -> int:
    require_sha(args.sha)
    if args.post_status:
        post(
            client,
            Conclusion(args.sha, "pending", "installing and testing this commit's dev pre-release"),
            target_for(args),
        )
    tag = resolve_prerelease(client, args.sha, args.tag)
    print(f"validate-dev: {args.sha} is the commit of the published pre-release {tag}")
    write_outputs(args.github_output, {"tag": tag})
    return PASSED


def command_run(args: argparse.Namespace, client: GitHub) -> int:
    require_sha(args.sha)
    target = target_for(args)
    if args.post_status:
        post(
            client,
            Conclusion(args.sha, "pending", "installing and testing this commit's dev pre-release"),
            target,
        )
    jobs: dict[str, str] = {}
    smoke_report = slow_report = None
    tag = None
    try:
        tag = resolve_prerelease(client, args.sha, args.tag)
        jobs["resolve"] = "success"
    except ValidationProblem as problem:
        print(f"validate-dev: {problem}", file=sys.stderr)
        jobs["resolve"] = "failure"
    if tag:
        work = work_dir(args)
        smoke_report = smoke(args.sha, tag, work / "smoke", live=args.live)
        jobs["smoke"] = "success" if smoke_report.passed else "failure"
        slow_report = slow(args.sha, work / "slow")
        jobs["slow"] = "success" if slow_report.passed else "failure"
    conclusion = conclude(
        args.sha,
        tag=tag,
        installed_sha=smoke_report.installed_commit if smoke_report else None,
        smoke_commit=smoke_report.tests_commit if smoke_report else None,
        slow_commit=slow_report.tests_commit if slow_report else None,
        jobs=jobs,
    )
    if args.post_status:
        post(client, conclusion, target)
    print(f"validate-dev: {conclusion.state} on {conclusion.sha}: {conclusion.description}")
    return PASSED if conclusion.state == "success" else PROBLEM


def finish(step: str, problems: Sequence[str]) -> int:
    if problems:
        print(f"validate-dev {step}: FAILED", file=sys.stderr)
        for problem in problems:
            print(f"  * {problem}", file=sys.stderr)
        return PROBLEM
    print(f"validate-dev {step}: passed")
    return PASSED


if __name__ == "__main__":
    sys.exit(main())
