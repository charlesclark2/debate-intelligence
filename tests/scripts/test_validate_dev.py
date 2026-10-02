"""Tests for `scripts/validate_dev.py`, the driver that decides the `validate-dev` status.

All offline. GitHub is :class:`FakeGitHub`, the installer is a shell script that writes a fake
`debate-research` printing the identity a test chooses, and the test trees are throwaway git
repositories under tmp_path. Where a tier's verdict is the point (a skip must fail the tier), the
tier is a **real pytest run** over a tiny suite written for the test, so the verdict is read from
pytest's own JUnit report rather than from a report this file wrote.

Expected values are written by hand.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import validate_dev as driver  # noqa: E402

SHA = "1111111111111111111111111111111111111111"
OTHER_SHA = "2222222222222222222222222222222222222222"
RUN_URL = "https://github.com/charlesclark2/debate-intelligence/actions/runs/42"


class FakeGitHub:
    def __init__(self, tags: dict[str, str] | None = None, releases: dict[str, driver.Release] | None = None):
        self.tags = tags or {}
        self.releases = releases or {}
        self.posted: list[tuple[str, str, str, str]] = []

    def dev_tags_at(self, sha: str) -> list[str]:
        return [tag for tag, commit in self.tags.items() if commit == sha and driver.DEV_TAG.fullmatch(tag)]

    def tag_commit(self, tag: str) -> str | None:
        return self.tags.get(tag)

    def release(self, tag: str) -> driver.Release | None:
        return self.releases.get(tag)

    def post_status(self, sha: str, state: str, target_url: str, description: str) -> None:
        self.posted.append((sha, state, target_url, description))


def prerelease(tag: str) -> driver.Release:
    return driver.Release(tag, is_prerelease=True, is_draft=False)


# --------------------------------------------------------------------------------------------
# resolve
# --------------------------------------------------------------------------------------------


def test_the_newest_published_prerelease_at_exactly_the_commit_is_chosen() -> None:
    github = FakeGitHub(
        tags={"v0.1.0-dev.4": SHA, "v0.1.0-dev.7": SHA, "v0.1.0-dev.9": OTHER_SHA, "v0.1.0-dev.8": SHA},
        releases={tag: prerelease(tag) for tag in ("v0.1.0-dev.4", "v0.1.0-dev.7", "v0.1.0-dev.9")},
    )

    assert driver.resolve_prerelease(github, SHA) == "v0.1.0-dev.7"


def test_numbers_compare_as_numbers_not_text() -> None:
    github = FakeGitHub(
        tags={"v0.1.0-dev.9": SHA, "v0.1.0-dev.10": SHA},
        releases={"v0.1.0-dev.9": prerelease("v0.1.0-dev.9"), "v0.1.0-dev.10": prerelease("v0.1.0-dev.10")},
    )

    assert driver.resolve_prerelease(github, SHA) == "v0.1.0-dev.10"


@pytest.mark.parametrize(
    "release",
    [None, driver.Release("v0.1.0-dev.3", True, True), driver.Release("v0.1.0-dev.3", False, False)],
    ids=["no-release", "draft", "full-release"],
)
def test_a_tag_without_a_published_prerelease_does_not_count(release: driver.Release | None) -> None:
    github = FakeGitHub(tags={"v0.1.0-dev.3": SHA}, releases={"v0.1.0-dev.3": release} if release else {})

    with pytest.raises(driver.ValidationProblem, match=f"no published dev pre-release points at {SHA}"):
        driver.resolve_prerelease(github, SHA)


def test_a_named_tag_must_point_at_the_commit() -> None:
    github = FakeGitHub(
        tags={"v0.1.0-dev.5": OTHER_SHA}, releases={"v0.1.0-dev.5": prerelease("v0.1.0-dev.5")}
    )

    with pytest.raises(driver.ValidationProblem, match=f"v0.1.0-dev.5 points at {OTHER_SHA}, not at {SHA}"):
        driver.resolve_prerelease(github, SHA, "v0.1.0-dev.5")


def test_a_named_tag_needs_its_prerelease() -> None:
    github = FakeGitHub(tags={"v0.1.0-dev.5": SHA})

    with pytest.raises(driver.ValidationProblem, match="v0.1.0-dev.5 has no published pre-release"):
        driver.resolve_prerelease(github, SHA, "v0.1.0-dev.5")


@pytest.mark.parametrize("tag", ["v0.1.0", "v0.1.0-dev.0", "0.1.0-dev.3", "v0.1.0-dev.3-extra"])
def test_only_dev_prerelease_tags_are_validated(tag: str) -> None:
    with pytest.raises(driver.ValidationProblem, match="is not a dev pre-release tag"):
        driver.resolve_prerelease(FakeGitHub(tags={tag: SHA}), SHA, tag)


@pytest.mark.parametrize("sha", ["1111111", "ABCDEF" + "0" * 34, SHA + "1", "", "dev"])
def test_only_a_full_commit_sha_is_accepted(sha: str) -> None:
    with pytest.raises(driver.ValidationProblem, match="is not a full 40-character commit SHA"):
        driver.resolve_prerelease(FakeGitHub(), sha)


def test_resolve_posts_pending_before_it_looks_and_even_when_it_finds_nothing() -> None:
    github = FakeGitHub()

    exit_code = driver.main(
        ["resolve", "--sha", SHA, "--post-status", "--target-url", RUN_URL], github=github
    )

    assert exit_code == driver.PROBLEM
    assert github.posted == [
        (SHA, "pending", RUN_URL, "installing and testing this commit's dev pre-release")
    ]


def test_resolve_writes_the_tag_for_the_next_jobs(tmp_path: Path) -> None:
    github = FakeGitHub(tags={"v0.1.0-dev.5": SHA}, releases={"v0.1.0-dev.5": prerelease("v0.1.0-dev.5")})
    outputs = tmp_path / "outputs"

    exit_code = driver.main(["resolve", "--sha", SHA, "--github-output", str(outputs)], github=github)

    assert exit_code == driver.PASSED
    assert outputs.read_text(encoding="utf-8") == "tag=v0.1.0-dev.5\n"
    assert github.posted == []


# --------------------------------------------------------------------------------------------
# What the installed build says it is
# --------------------------------------------------------------------------------------------


def identity(**changes: object) -> dict[str, object]:
    base: dict[str, object] = {
        "package": "debate-cli",
        "version": "0.1.0.dev5",
        "channel": "dev",
        "commit": SHA,
        "tag": "v0.1.0-dev.5",
        "environment": "dev",
        "environment_source": "build-channel:dev",
    }
    return base | changes


def test_a_build_reporting_the_requested_commit_tag_and_channel_passes() -> None:
    assert driver.identity_problems(identity(), SHA, "v0.1.0-dev.5") == []


@pytest.mark.parametrize(
    ("changes", "problem"),
    [
        ({"commit": OTHER_SHA}, f"reports commit '{OTHER_SHA}', expected '{SHA}'"),
        ({"tag": "v0.1.0-dev.4"}, "reports tag 'v0.1.0-dev.4', expected 'v0.1.0-dev.5'"),
        ({"channel": "local"}, "reports channel 'local', expected 'dev'"),
        ({"version": "0.1.0.dev4"}, "reports version '0.1.0.dev4', expected '0.1.0.dev5'"),
        ({"environment": "prod"}, "reports environment 'prod', expected 'dev'"),
        (
            {"environment_source": "env:DEBATE_ENV"},
            "environment_source 'env:DEBATE_ENV', expected 'build-channel:dev'",
        ),
    ],
)
def test_each_way_the_build_can_be_the_wrong_one_is_named(changes: dict[str, object], problem: str) -> None:
    problems = driver.identity_problems(identity(**changes), SHA, "v0.1.0-dev.5")

    assert len(problems) == 1
    assert problem in problems[0]


def test_the_wheel_version_is_the_pep440_spelling_of_the_tag() -> None:
    assert driver.wheel_version("v1.12.0-dev.31") == "1.12.0.dev31"


# --------------------------------------------------------------------------------------------
# A tier's verdict, from pytest's JUnit report
# --------------------------------------------------------------------------------------------


JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" errors="0" failures="0" skipped="1" tests="3">
<testcase classname="tests.smoke.test_cli_smoke" name="test_verify_exits_zero"/>
<testcase classname="tests.smoke.test_cli_smoke" name="test_doctor"/>
<testcase classname="tests.smoke.test_cli_smoke" name="test_fixture">
<skipped type="pytest.skip" message="fixture missing">x</skipped></testcase>
</testsuite></testsuites>
"""


def test_the_junit_report_is_read_with_its_skips(tmp_path: Path) -> None:
    report = tmp_path / "junit.xml"
    report.write_text(JUNIT, encoding="utf-8")

    counts = driver.read_junit(report)

    assert counts == driver.JUnitCounts(
        tests=3,
        failures=0,
        errors=0,
        skipped=1,
        skipped_names=("tests.smoke.test_cli_smoke::test_fixture: fixture missing",),
    )


def test_a_missing_or_broken_report_reads_as_none(tmp_path: Path) -> None:
    broken = tmp_path / "broken.xml"
    broken.write_text("<testsuites", encoding="utf-8")

    assert driver.read_junit(tmp_path / "absent.xml") is None
    assert driver.read_junit(broken) is None


@pytest.mark.parametrize(
    ("exit_code", "counts", "problem"),
    [
        (0, driver.JUnitCounts(3, 0, 0, 1), "1 skipped; a skipped check did not run"),
        (1, driver.JUnitCounts(3, 1, 0, 0), "1 failed, 0 errors"),
        (1, driver.JUnitCounts(3, 0, 2, 0), "0 failed, 2 errors"),
        (5, driver.JUnitCounts(0, 0, 0, 0), "no tests ran"),
        (0, driver.JUnitCounts(0, 0, 0, 0), "no tests ran"),
        (2, None, "pytest wrote no JUnit report (exit 2)"),
        (1, driver.JUnitCounts(3, 0, 0, 0), "pytest exited 1"),
    ],
)
def test_a_tier_fails_unless_every_selected_test_ran_and_passed(
    exit_code: int, counts: driver.JUnitCounts | None, problem: str
) -> None:
    result = driver.TierResult("recorded", exit_code, counts)

    assert not result.passed
    assert any(problem in line for line in result.problems), result.problems


def test_a_tier_passes_when_every_selected_test_ran_and_passed() -> None:
    assert driver.TierResult("recorded", 0, driver.JUnitCounts(27, 0, 0, 0)).passed


@pytest.mark.parametrize(
    ("tier", "expression"),
    [
        (driver.RECORDED, "not live and not in_process"),
        (driver.LIVE_CANARY, "live and canary"),
        (driver.SLOW, "slow and not live and not eval"),
    ],
)
def test_the_tiers_select_what_the_readme_says(tier: driver.Tier, expression: str) -> None:
    assert tier.marker_expression == expression


# --------------------------------------------------------------------------------------------
# Real pytest runs over throwaway suites: the verdict comes from pytest itself
# --------------------------------------------------------------------------------------------

GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


def git(repo: Path, *arguments: str) -> str:
    environment = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")} | GIT_ENV
    return subprocess.run(
        ["git", *arguments], cwd=repo, env=environment, capture_output=True, text=True, check=True
    ).stdout.strip()


def tree(tmp_path: Path, suite: str) -> tuple[Path, str]:
    """A git repository holding `suite` as checks/test_suite.py; returns it and its commit."""
    repo = tmp_path / "tree"
    (repo / "checks").mkdir(parents=True)
    (repo / "pytest.ini").write_text("[pytest]\nmarkers =\n    smoke: a check\n", encoding="utf-8")
    (repo / "checks" / "test_suite.py").write_text(suite, encoding="utf-8")
    git(repo, "init", "-q")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "suite")
    return repo, git(repo, "rev-parse", "HEAD")


def pytest_in(repo: Path) -> tuple[str, ...]:
    return (sys.executable, "-m", "pytest", "-c", str(repo / "pytest.ini"))


TIER = driver.Tier("recorded", "not live", ("checks",))

PASSING = """
import os
def test_the_installed_build_is_named():
    assert os.environ["DEBATE_SMOKE_BIN"].endswith("bin/debate-research")
    assert len(os.environ["DEBATE_SMOKE_EXPECT_SHA"]) == 40
    assert os.environ["DEBATE_SMOKE_EXPECT_TAG"] == "v0.1.0-dev.5"
def test_no_token_reaches_the_tests():
    assert "GH_TOKEN" not in os.environ and "GITHUB_TOKEN" not in os.environ
"""

SKIPPING = """
import pytest
def test_runs():
    pass
def test_needs_a_fixture():
    pytest.skip("the fixture manifest is missing")
"""

EXPECTED_FAILURE = """
import pytest
def test_runs():
    pass
@pytest.mark.xfail(reason="known")
def test_known():
    assert False
"""


def fake_installer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reported: dict[str, object]) -> Path:
    """An installer that 'installs' a debate-research printing `reported` as its --version --json."""
    identity_file = tmp_path / "identity.json"
    identity_file.write_text(json.dumps({"status": "ok", "data": reported}), encoding="utf-8")
    log = tmp_path / "installer.log"
    script = tmp_path / "fake_install_channel.sh"
    script.write_text(
        "#!/bin/sh\nset -eu\n"
        f'echo "$@ UV_TOOL_DIR=$UV_TOOL_DIR" >> "{log}"\n'
        'mkdir -p "$UV_TOOL_BIN_DIR"\n'
        f'printf \'#!/bin/sh\\ncat "{identity_file}"\\n\' > "$UV_TOOL_BIN_DIR/debate-research"\n'
        'chmod +x "$UV_TOOL_BIN_DIR/debate-research"\n',
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("GH_TOKEN", "a-token-the-tests-must-not-see")
    return script


def run_smoke(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suite: str, **reported: object
) -> driver.SmokeReport:
    repo, commit = tree(tmp_path, suite)
    installer = fake_installer(tmp_path, monkeypatch, identity(commit=commit) | reported)
    return driver.smoke(
        commit,
        "v0.1.0-dev.5",
        tmp_path / "work",
        installer=(str(installer),),
        pytest_command=pytest_in(repo),
        tiers=(TIER,),
        cwd=repo,
    )


def test_the_smoke_tier_passes_against_the_build_it_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = run_smoke(tmp_path, monkeypatch, PASSING)

    assert report.problems == []
    assert report.installed_commit == report.sha == report.tests_commit
    assert report.tiers == [
        {
            "name": "recorded",
            "exit_code": 0,
            "counts": {"tests": 2, "failures": 0, "errors": 0, "skipped": 0, "skipped_names": ()},
        }
    ]
    assert (tmp_path / "installer.log").read_text(encoding="utf-8") == (
        f"v0.1.0-dev.5 UV_TOOL_DIR={tmp_path / 'work' / 'tools'}\n"
    )


def test_a_skipped_smoke_check_fails_the_tier(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The forbidden case: success while a check is skipped for a missing fixture."""
    report = run_smoke(tmp_path, monkeypatch, SKIPPING)

    assert not report.passed
    assert report.tiers[0]["exit_code"] == 0, "pytest itself calls a skip a pass; the driver must not"
    assert any(
        "1 skipped" in problem and "the fixture manifest is missing" in problem for problem in report.problems
    )


def test_an_expected_failure_counts_as_a_skip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = run_smoke(tmp_path, monkeypatch, EXPECTED_FAILURE)

    assert any("1 skipped" in problem for problem in report.problems), report.problems


def test_a_tier_that_selects_nothing_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = run_smoke(
        tmp_path, monkeypatch, "import pytest\n@pytest.mark.live\ndef test_live():\n    pass\n"
    )

    assert any("no tests ran" in problem for problem in report.problems), report.problems


def test_a_build_reporting_another_commit_is_never_tested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The SHA assertion: the binary installed is not the build of the commit being validated."""
    report = run_smoke(tmp_path, monkeypatch, PASSING, commit=OTHER_SHA)

    assert report.installed_commit == OTHER_SHA
    assert report.tiers == []
    assert report.problems == [f"the installed build reports commit '{OTHER_SHA}', expected '{report.sha}'"]


def test_smoke_tests_from_another_commit_are_refused_before_anything_is_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, commit = tree(tmp_path, PASSING)
    installer = fake_installer(tmp_path, monkeypatch, identity(commit=OTHER_SHA))

    report = driver.smoke(
        OTHER_SHA,
        "v0.1.0-dev.5",
        tmp_path / "work",
        installer=(str(installer),),
        pytest_command=pytest_in(repo),
        tiers=(TIER,),
        cwd=repo,
    )

    assert report.problems == [
        f"the smoke tests come from {commit}, not {OTHER_SHA}; check out the validated commit"
    ]
    assert not (tmp_path / "installer.log").exists()


def test_uncommitted_changes_make_the_test_tree_another_commit(tmp_path: Path) -> None:
    repo, commit = tree(tmp_path, PASSING)
    (repo / "checks" / "test_suite.py").write_text("def test_changed():\n    pass\n", encoding="utf-8")

    assert driver.tree_commit(repo) == f"{commit}-dirty"


def test_a_failing_install_stops_the_run(tmp_path: Path) -> None:
    repo, commit = tree(tmp_path, PASSING)
    failing = tmp_path / "failing.sh"
    failing.write_text("#!/bin/sh\necho 'SHA256SUMS verification failed' >&2\nexit 1\n", encoding="utf-8")
    failing.chmod(0o755)

    report = driver.smoke(commit, "v0.1.0-dev.5", tmp_path / "work", installer=(str(failing),), cwd=repo)

    assert report.problems == ["scripts/install_channel.sh v0.1.0-dev.5 failed (exit 1)"]


def test_the_live_tier_runs_only_when_asked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, commit = tree(
        tmp_path,
        "import pytest\ndef test_offline():\n    pass\n@pytest.mark.live\ndef test_live():\n    pass\n",
    )
    installer = fake_installer(tmp_path, monkeypatch, identity(commit=commit))
    live_tier = driver.Tier("live canary", "live", ("checks",))

    def ran(live: bool) -> list[object]:
        report = driver.smoke(
            commit,
            "v0.1.0-dev.5",
            tmp_path / f"work-{live}",
            live=live,
            installer=(str(installer),),
            pytest_command=pytest_in(repo),
            tiers=(TIER,),
            live_tiers=(live_tier,),
            cwd=repo,
        )
        assert report.passed, report.problems
        return [tier["name"] for tier in report.tiers]

    assert ran(False) == ["recorded"]
    assert ran(True) == ["recorded", "live canary"]


def test_the_slow_tier_refuses_a_checkout_of_another_commit(tmp_path: Path) -> None:
    repo, commit = tree(tmp_path, PASSING)

    report = driver.slow(OTHER_SHA, tmp_path / "work", pytest_command=pytest_in(repo), cwd=repo)

    assert report.problems == [
        f"the slow tier would run {commit}, not {OTHER_SHA}; check out the validated commit"
    ]


def test_a_skip_in_the_slow_tier_fails_it_too(tmp_path: Path) -> None:
    repo, commit = tree(tmp_path, SKIPPING)

    report = driver.slow(commit, tmp_path / "work", pytest_command=pytest_in(repo), tier=TIER, cwd=repo)

    assert any("1 skipped" in problem for problem in report.problems), report.problems


# --------------------------------------------------------------------------------------------
# conclude: what is posted, and on which commit
# --------------------------------------------------------------------------------------------

ALL_GREEN = {"resolve": "success", "smoke": "success", "slow": "success"}


def concluded(**changes: object) -> driver.Conclusion:
    arguments: dict[str, object] = {
        "tag": "v0.1.0-dev.5",
        "installed_sha": SHA,
        "smoke_commit": SHA,
        "slow_commit": SHA,
        "jobs": ALL_GREEN,
    } | changes
    return driver.conclude(SHA, **arguments)  # type: ignore[arg-type]


def test_success_needs_every_job_green_and_the_installed_build_to_be_the_commit() -> None:
    assert concluded() == driver.Conclusion(
        SHA,
        "success",
        "v0.1.0-dev.5 installed from its pre-release and validated: recorded and slow tiers green",
    )


@pytest.mark.parametrize(
    ("changes", "description"),
    [
        ({"installed_sha": OTHER_SHA}, f"the installed build reports {OTHER_SHA}, not this commit"),
        ({"installed_sha": None}, "the installed build reports nothing, not this commit"),
        ({"smoke_commit": f"{SHA}-dirty"}, f"the smoke tests came from {SHA}-dirty, not this commit"),
        ({"slow_commit": OTHER_SHA}, f"the slow tier ran {OTHER_SHA}, not this commit"),
        ({"jobs": ALL_GREEN | {"slow": "failure"}}, "validation failed: slow failure"),
        (
            {"jobs": {"resolve": "failure", "smoke": "skipped", "slow": "skipped"}},
            "validation failed: resolve failure, smoke skipped, slow skipped",
        ),
        ({"jobs": {"resolve": "success", "smoke": "success"}}, "validation failed: slow did not run"),
    ],
)
def test_anything_less_is_a_failure_on_the_requested_commit(
    changes: dict[str, object], description: str
) -> None:
    assert concluded(**changes) == driver.Conclusion(SHA, "failure", description)


def test_a_cancelled_run_is_an_error_not_a_pending_left_behind() -> None:
    assert concluded(jobs=ALL_GREEN | {"smoke": "cancelled"}) == driver.Conclusion(
        SHA, "error", "validation was cancelled before it finished"
    )


def conclude_command(*extra: str, installed: str = SHA) -> list[str]:
    return [
        "conclude",
        "--sha",
        SHA,
        "--tag",
        "v0.1.0-dev.5",
        "--installed-sha",
        installed,
        "--smoke-commit",
        SHA,
        "--slow-commit",
        SHA,
        "--job",
        "resolve=success",
        "--job",
        "smoke=success",
        "--job",
        "slow=success",
        "--post-status",
        "--target-url",
        RUN_URL,
        *extra,
    ]


def test_conclude_posts_success_on_exactly_the_commit_that_was_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Not the workflow's own commit: a dispatch from dev runs at dev's head, which may have moved."""
    monkeypatch.setenv("GITHUB_SHA", OTHER_SHA)
    github = FakeGitHub()

    assert driver.main(conclude_command(), github=github) == driver.PASSED

    assert github.posted == [
        (
            SHA,
            "success",
            RUN_URL,
            "v0.1.0-dev.5 installed from its pre-release and validated: recorded and slow tiers green",
        )
    ]


def test_conclude_posts_failure_on_the_requested_commit_when_another_was_installed() -> None:
    github = FakeGitHub()

    assert driver.main(conclude_command(installed=OTHER_SHA), github=github) == driver.PROBLEM

    assert [(sha, state) for sha, state, _, _ in github.posted] == [(SHA, "failure")]


def test_a_long_description_is_cut_to_what_the_statuses_api_accepts() -> None:
    github = FakeGitHub()

    driver.post(github, driver.Conclusion(SHA, "failure", "x" * 300), RUN_URL)

    assert len(github.posted[0][3]) == 140


def test_posting_outside_actions_needs_a_target_url(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"):
        monkeypatch.delenv(name, raising=False)
    github = FakeGitHub()
    command = conclude_command()
    command = command[: command.index("--target-url")]

    assert driver.main(command, github=github) == driver.PROBLEM
    assert github.posted == []


def test_the_run_link_defaults_to_this_actions_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "charlesclark2/debate-intelligence")
    monkeypatch.setenv("GITHUB_RUN_ID", "42")
    github = FakeGitHub()
    command = conclude_command()
    command = command[: command.index("--target-url")]

    driver.main(command, github=github)

    assert github.posted[0][2] == RUN_URL


def test_run_posts_pending_then_failure_when_the_commit_has_no_prerelease() -> None:
    github = FakeGitHub()

    exit_code = driver.main(["run", "--sha", SHA, "--post-status", "--target-url", RUN_URL], github=github)

    assert exit_code == driver.PROBLEM
    assert [(sha, state) for sha, state, _, _ in github.posted] == [(SHA, "pending"), (SHA, "failure")]
    assert github.posted[1][3] == "validation failed: resolve failure, smoke did not run, slow did not run"


# --------------------------------------------------------------------------------------------
# GhCli: the only code that talks to GitHub
# --------------------------------------------------------------------------------------------


class RecordingRunner:
    def __init__(self, responses: dict[str, subprocess.CompletedProcess[str]]):
        self.responses = responses
        self.calls: list[list[str]] = []

    def __call__(self, command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        for prefix, response in self.responses.items():
            if " ".join(command).startswith(prefix):
                return response
        return subprocess.CompletedProcess(command, 0, "", "")


def done(stdout: str = "", returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


REPO = "charlesclark2/debate-intelligence"


def test_gh_posts_the_validate_dev_context_on_the_given_commit() -> None:
    runner = RecordingRunner({})

    driver.GhCli(REPO, runner).post_status(SHA, "success", RUN_URL, "validated")

    assert runner.calls == [
        [
            "gh",
            "api",
            "--method",
            "POST",
            f"repos/{REPO}/statuses/{SHA}",
            "-f",
            "state=success",
            "-f",
            f"target_url={RUN_URL}",
            "-f",
            "description=validated",
            "-f",
            "context=validate-dev",
        ]
    ]


def test_gh_finds_dev_tags_at_a_commit_and_follows_an_annotated_tag() -> None:
    listing = "\n".join(
        [
            f"refs/tags/v0.1.0-dev.4\tcommit\t{SHA}",
            f"refs/tags/v0.1.0-dev.5\tcommit\t{OTHER_SHA}",
            "refs/tags/v0.1.0-dev.6\ttag\t" + "3" * 40,
            f"refs/tags/v0.1.0\tcommit\t{SHA}",
        ]
    )
    runner = RecordingRunner(
        {
            f"gh api --paginate repos/{REPO}/git/matching-refs/tags/v": done(listing + "\n"),
            f"gh api repos/{REPO}/git/tags/{'3' * 40}": done(SHA + "\n"),
        }
    )

    assert driver.GhCli(REPO, runner).dev_tags_at(SHA) == ["v0.1.0-dev.4", "v0.1.0-dev.6"]


def test_gh_reports_a_missing_release_as_none_and_other_failures_as_problems() -> None:
    missing = RecordingRunner({"gh release view": done(returncode=1, stderr="release not found")})
    broken = RecordingRunner({"gh release view": done(returncode=1, stderr="HTTP 502")})
    found = RecordingRunner(
        {
            "gh release view": done(
                json.dumps({"tagName": "v0.1.0-dev.5", "isPrerelease": True, "isDraft": False})
            )
        }
    )

    assert driver.GhCli(REPO, missing).release("v0.1.0-dev.5") is None
    with pytest.raises(driver.ValidationProblem, match="HTTP 502"):
        driver.GhCli(REPO, broken).release("v0.1.0-dev.5")
    assert driver.GhCli(REPO, found).release("v0.1.0-dev.5") == prerelease("v0.1.0-dev.5")


def test_a_failing_status_post_is_a_problem_not_a_silent_pass() -> None:
    runner = RecordingRunner(
        {"gh api --method POST": done(returncode=1, stderr="HTTP 403: Resource not accessible")}
    )

    with pytest.raises(driver.ValidationProblem, match="HTTP 403"):
        driver.GhCli(REPO, runner).post_status(SHA, "success", RUN_URL, "validated")
