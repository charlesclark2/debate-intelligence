"""What `.github/workflows/release.yml` runs, when, and with which permissions (v1-e09-t06).

The workflow runs only when a stable tag is pushed, so no pull request exercises it; these tests read
the file as GitHub does. Which tags start it is decided by GitHub's filter patterns, which this file
evaluates with a small matcher of the pattern forms GitHub documents (`*`, `**`, `+`, `?`, `[...]`,
and `!` to exclude what an earlier pattern matched). What each check refuses is
test_check_stable_release.py's.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
RELEASE = WORKFLOWS / "release.yml"


def release() -> dict[Any, Any]:
    return yaml.safe_load(RELEASE.read_text(encoding="utf-8"))


def triggers(flow: Mapping[Any, Any]) -> Mapping[str, Any]:
    # YAML 1.1 reads a bare `on:` key as True.
    return flow.get("on", flow.get(True))


def jobs() -> dict[str, dict[str, Any]]:
    return release()["jobs"]


def steps(job: str) -> list[dict[str, Any]]:
    return jobs()[job]["steps"]


def runs(job: str) -> str:
    return "\n".join(str(step.get("run", "")) for step in steps(job))


def step_named(job: str, prefix: str) -> dict[str, Any]:
    [step] = [step for step in steps(job) if str(step.get("name", "")).startswith(prefix)]
    return step


# --------------------------------------------------------------------------------------------
# GitHub's filter patterns
# --------------------------------------------------------------------------------------------


def pattern_regex(pattern: str) -> re.Pattern[str]:
    out = ""
    index = 0
    while index < len(pattern):
        character = pattern[index]
        if character == "*":
            if pattern[index : index + 2] == "**":
                out += ".*"
                index += 2
                continue
            out += "[^/]*"
        elif character == "[":
            end = pattern.index("]", index)
            out += pattern[index : end + 1]
            index = end + 1
            continue
        elif character in "+?":
            out += character
        else:
            out += re.escape(character)
        index += 1
    return re.compile(f"^{out}$")


def starts_the_workflow(patterns: Sequence[str], tag: str) -> bool:
    included = False
    for pattern in patterns:
        if pattern.startswith("!"):
            if pattern_regex(pattern[1:]).match(tag):
                included = False
        elif pattern_regex(pattern).match(tag):
            included = True
    return included


def test_the_matcher_reads_github_s_documented_examples() -> None:
    """The cheat sheet's own semantic-version and wildcard examples, so the matcher is not ours alone."""
    assert starts_the_workflow(["v[12].[0-9]+.[0-9]+"], "v1.10.1")
    assert starts_the_workflow(["v[12].[0-9]+.[0-9]+"], "v2.0.0")
    assert not starts_the_workflow(["v[12].[0-9]+.[0-9]+"], "v3.0.0")
    assert starts_the_workflow(["v2*"], "v2.9")
    assert not starts_the_workflow(["v2*"], "v1.0")
    assert not starts_the_workflow(["*", "!v2*"], "v2.0")


def tag_patterns() -> list[str]:
    on = triggers(release())
    return list(on["push"]["tags"])


@pytest.mark.parametrize("tag", ["v1.5.0", "v1.1.0", "v1.10.12", "v2.0.0"])
def test_a_stable_tag_starts_the_release(tag: str) -> None:
    assert starts_the_workflow(tag_patterns(), tag)


@pytest.mark.parametrize(
    "tag",
    ["v1.5.0-dev.3", "v1.1.0-dev.137", "v1.0.1-dev.1", "v1.5", "v1.5.0-rc.1", "v1.5.0.1", "vnext", "1.5.0"],
)
def test_a_dev_pre_release_tag_or_any_other_never_starts_it(tag: str) -> None:
    assert not starts_the_workflow(tag_patterns(), tag)


def test_dev_pre_release_tags_are_excluded_by_name_as_well_as_by_shape() -> None:
    """The stable shape alone excludes them; the named exclusion keeps them out if the shape widens."""
    patterns = tag_patterns()

    assert "!v*-dev.*" in patterns
    assert not starts_the_workflow([*patterns[:1], "v*", *patterns[1:]], "v1.5.0-dev.3")


def test_a_pushed_tag_is_the_only_trigger() -> None:
    on = triggers(release())

    assert set(on) == {"push"}
    assert set(on["push"]) == {"tags"}


# --------------------------------------------------------------------------------------------
# Permissions: read everywhere, contents: write for the one job that publishes
# --------------------------------------------------------------------------------------------


def test_only_the_publish_job_may_write_and_each_job_reads_only_what_it_needs() -> None:
    assert release()["permissions"] == {"contents": "read"}
    assert {name: job["permissions"] for name, job in jobs().items()} == {
        "check": {"contents": "read", "pull-requests": "read", "statuses": "read", "actions": "read"},
        "build": {"contents": "read"},
        "publish": {"contents": "write"},
    }


def test_no_secret_no_oidc_token_and_no_package_index() -> None:
    """Read from the parsed workflow, so the header's own account of what is absent is not counted."""
    written = yaml.safe_dump(release()).lower()

    for word in ("secrets.", "id-token", "pypi", "twine", "uv publish", "--publish", "aws"):
        assert word not in written, word


def test_the_token_reaches_the_jobs_that_read_or_publish_and_never_the_build() -> None:
    assert "github.token" not in yaml.safe_dump(jobs()["build"])
    assert step_named("check", "Refuse a tag")["env"]["GH_TOKEN"] == "${{ github.token }}"
    assert jobs()["publish"]["env"]["GH_TOKEN"] == "${{ github.token }}"


def test_the_publish_job_checks_out_nothing_and_runs_no_repository_code() -> None:
    publish = steps("publish")

    assert not [step for step in publish if str(step.get("uses", "")).startswith("actions/checkout@")]
    script = runs("publish")
    for program in ("sh scripts/", "python3 ", "uv ", "./"):
        assert program not in script, program


def test_every_checkout_persists_no_credentials() -> None:
    checkouts = [
        step
        for job in jobs()
        for step in steps(job)
        if str(step.get("uses", "")).startswith("actions/checkout@")
    ]
    assert len(checkouts) == 2
    assert all(step["with"]["persist-credentials"] is False for step in checkouts)


def test_no_expression_reaches_a_run_block() -> None:
    """Expressions go through env:, so a tag name can never be read as shell."""
    for job in jobs():
        for step in steps(job):
            assert "${{" not in str(step.get("run", "")), (job, step.get("name"))


def test_uv_s_cache_is_not_restored_into_a_release() -> None:
    setups = [
        step
        for job in jobs()
        for step in steps(job)
        if str(step.get("uses", "")).startswith("astral-sh/setup-uv@")
    ]
    assert len(setups) == 2
    assert all(step["with"] == {"enable-cache": False} for step in setups)


# --------------------------------------------------------------------------------------------
# What runs, in what order
# --------------------------------------------------------------------------------------------


def test_the_jobs_run_check_then_build_then_publish() -> None:
    assert "needs" not in jobs()["check"]
    assert jobs()["build"]["needs"] == "check"
    assert jobs()["publish"]["needs"] == ["check", "build"]


def test_the_check_job_runs_every_check_against_the_tagged_commit_with_main_s_history() -> None:
    [checkout] = [
        step for step in steps("check") if str(step.get("uses", "")).startswith("actions/checkout@")
    ]
    assert checkout["with"]["fetch-depth"] == 0
    assert "ref" not in checkout["with"]  # the pushed tag itself

    resolve = step_named("check", "Resolve the tagged commit")
    assert (
        resolve["run"]
        == 'echo "sha=$(git rev-parse --verify "refs/tags/${TAG}^{commit}")" >> "$GITHUB_OUTPUT"'
    )

    checks = step_named("check", "Refuse a tag")
    assert checks["id"] == "checks"
    assert checks["run"] == (
        "uv run scripts/check_stable_release.py check "
        '--tag "$TAG" --sha "$SHA" --repository "$GITHUB_REPOSITORY"'
    )
    assert checks["env"]["TAG"] == "${{ github.ref_name }}"
    assert checks["env"]["SHA"] == "${{ steps.commit.outputs.sha }}"


def test_the_check_job_hands_on_only_what_the_checks_wrote() -> None:
    assert jobs()["check"]["outputs"] == {
        "tag": "${{ steps.checks.outputs.tag }}",
        "version": "${{ steps.checks.outputs.version }}",
        "sha": "${{ steps.checks.outputs.sha }}",
    }


def test_the_build_stamps_channel_stable_at_the_checked_commit_and_refuses_bad_wheels() -> None:
    build = jobs()["build"]
    [checkout] = [
        step for step in steps("build") if str(step.get("uses", "")).startswith("actions/checkout@")
    ]
    assert checkout["with"]["ref"] == "${{ needs.check.outputs.sha }}"
    assert build["env"] == {
        "TAG": "${{ needs.check.outputs.tag }}",
        "VERSION": "${{ needs.check.outputs.version }}",
        "SHA": "${{ needs.check.outputs.sha }}",
    }

    order = [str(step.get("name", step.get("uses"))) for step in steps("build")]
    stamp = order.index("Stamp the version, build info and bundled configuration for channel stable")
    built = order.index("Build the debate_core and debate_cli wheels")
    checked = order.index("Refuse wheels that are not exactly what should ship")
    sums = order.index("Write SHA256SUMS")
    installed = order.index(
        "Install the build as its users will and check it reports this version and channel stable"
    )
    assert stamp < built < checked < sums < installed

    script = runs("build")
    assert "--channel stable" in script
    assert "--channel dev" not in script
    assert 'python3 scripts/stamp_build.py check-wheels --version "$VERSION" --dist dist' in script
    assert 'sh scripts/install_channel.sh --no-path-warning --dir dist "$TAG"' in script
    assert 'uv run scripts/check_stable_release.py notes --tag "$TAG" > release-notes.md' in script


def test_the_artifact_carries_exactly_what_install_channel_downloads_and_the_notes() -> None:
    [upload] = [
        step for step in steps("build") if str(step.get("uses", "")).startswith("actions/upload-artifact@")
    ]
    assert upload["with"]["path"].split() == [
        "dist/*.whl",
        "dist/SHA256SUMS",
        "dist/build-info.json",
        "release-notes.md",
    ]
    assert upload["with"]["if-no-files-found"] == "error"
    install = (REPO_ROOT / "scripts" / "install_channel.sh").read_text(encoding="utf-8")
    assert "--pattern '*.whl' --pattern SHA256SUMS --pattern build-info.json" in install


def test_the_release_is_a_full_release_under_the_pushed_tag_with_the_changelog_notes() -> None:
    publish = step_named("publish", "Publish the GitHub Release")["run"]

    assert (
        'gh release create "$TAG" release/dist/*.whl release/dist/SHA256SUMS release/dist/build-info.json'
        in publish
    )
    assert "--verify-tag" in publish
    assert "--notes-file release/release-notes.md" in publish
    assert "--prerelease" not in RELEASE.read_text(encoding="utf-8").replace("Never --prerelease", "")
    assert "--draft" not in publish


def test_publish_refuses_a_moved_tag_or_an_existing_release_before_creating_one() -> None:
    order = [str(step.get("name", step.get("uses"))) for step in steps("publish")]
    guard = step_named("publish", "Refuse a tag that moved")["run"]

    assert order.index(
        "Refuse a tag that moved since it was checked, or that is already released"
    ) < order.index("Publish the GitHub Release")
    assert 'if [ "$commit" != "$SHA" ]; then' in guard
    assert 'gh release view "$TAG"' in guard
    assert guard.count("exit 1") == 2


# --------------------------------------------------------------------------------------------
# Pinned as the repository's other workflows pin their actions
# --------------------------------------------------------------------------------------------


def uses(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    return set(re.findall(r"(?<![\w-])uses:\s*([^\s#]+)", text))


def test_every_action_is_pinned_as_another_workflow_pins_it() -> None:
    elsewhere: dict[str, set[str]] = {}
    for path in sorted(WORKFLOWS.glob("*.yml")):
        if path != RELEASE:
            for reference in uses(path):
                action, _, version = reference.partition("@")
                elsewhere.setdefault(action, set()).add(version)

    mine = uses(RELEASE)
    assert mine == {
        "actions/checkout@v7",
        "astral-sh/setup-uv@v10.2.0",
        "actions/upload-artifact@v6",
        "actions/download-artifact@v7",
    }
    for reference in mine:
        action, _, version = reference.partition("@")
        assert elsewhere.get(action) == {version}, reference


def test_every_job_has_a_runner_image_and_a_time_limit() -> None:
    for name, job in jobs().items():
        assert job["runs-on"] == "ubuntu-24.04", name
        assert isinstance(job["timeout-minutes"], int), name
