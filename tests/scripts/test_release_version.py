"""Tests for `scripts/release_version.py`: dev version computation and claiming N (v1-e01-t09).

The dev-prerelease workflow only runs after a merge to dev, so no task pull request exercises it;
these tests are the evidence the numbering is right before its first real run.

The first sections are pure functions. The last runs real git against a bare "remote" under
tmp_path, because the property that matters most — two overlapping runs never get the same N — is
decided by git refusing to overwrite a tag, and only git can show that. Expected versions are
written by hand.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from packaging.version import Version

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import release_version as rv  # noqa: E402

# --------------------------------------------------------------------------------------------
# Versions and tags
# --------------------------------------------------------------------------------------------


def test_a_dev_build_has_a_git_tag_and_a_pep440_version() -> None:
    build = rv.DevBuild(rv.Release(0, 1, 0), 3)

    assert build.tag == "v0.1.0-dev.3"
    assert build.pep440 == "0.1.0.dev3"


def test_the_pep440_form_sorts_before_the_release_and_numerically_between_builds() -> None:
    target = rv.Release(1, 2, 0)
    versions = [Version(rv.DevBuild(target, number).pep440) for number in (1, 2, 9, 10)]

    assert versions == sorted(versions)  # dev9 < dev10: numeric, not lexicographic
    assert all(version < Version("1.2.0") for version in versions)
    assert all(version.is_prerelease for version in versions)
    assert Version(rv.DevBuild(target, 10).pep440) > Version("1.1.9")


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("v0.1.0-dev.3", rv.DevBuild(rv.Release(0, 1, 0), 3)),
        ("v1.10.2-dev.12", rv.DevBuild(rv.Release(1, 10, 2), 12)),
        ("v0.1.0-dev.0", None),
        ("v0.1.0-dev.01", None),
        ("v0.1.0", None),
        ("0.1.0-dev.1", None),
        ("v0.1.0-dev.1-extra", None),
    ],
)
def test_dev_tags_are_parsed_strictly(tag: str, expected: rv.DevBuild | None) -> None:
    assert rv.DevBuild.from_tag(tag) == expected


@pytest.mark.parametrize("text", ["0.1", "0.1.0.dev1", "0.1.0a1", "v0.1.0", "01.1.0", ""])
def test_the_version_source_must_be_a_plain_release(text: str) -> None:
    with pytest.raises(rv.ReleaseVersionError, match="plain X.Y.Z"):
        rv.Release.parse(text)


# --------------------------------------------------------------------------------------------
# The stable target and N
# --------------------------------------------------------------------------------------------


def test_n_starts_at_one() -> None:
    assert rv.next_dev_number(rv.Release(0, 1, 0), []) == 1


def test_n_is_one_past_the_highest_for_the_same_target_only() -> None:
    tags = [
        "v0.1.0-dev.1",
        "v0.1.0-dev.2",
        "v0.1.0-dev.10",
        "v0.0.9-dev.40",
        "v0.1.1-dev.7",
        "v0.1.0",
        "junk",
    ]

    assert rv.next_dev_number(rv.Release(0, 1, 0), tags) == 11
    assert rv.next_dev_number(rv.Release(0, 1, 1), tags) == 8
    assert rv.next_dev_number(rv.Release(0, 2, 0), tags) == 1


def test_dev_builds_target_the_unreleased_pyproject_version() -> None:
    assert rv.target_for_dev(rv.Release(0, 2, 0), ["v0.1.0", "v0.1.0-dev.4"]) == rv.Release(0, 2, 0)


@pytest.mark.parametrize("released", ["v0.1.0", "v0.2.0"])
def test_dev_builds_refuse_a_version_already_released_or_passed(released: str) -> None:
    with pytest.raises(rv.ReleaseVersionError, match="bump `version`"):
        rv.target_for_dev(rv.Release(0, 1, 0), [released])


def test_a_hotfix_targets_the_patch_after_the_newest_release_in_its_head() -> None:
    assert rv.target_for_hotfix(rv.Release(1, 2, 0), ["v1.0.0", "v1.1.0", "v1.1.0-dev.3"]) == rv.Release(
        1, 1, 1
    )


def test_a_hotfix_before_any_release_targets_the_pyproject_version() -> None:
    assert rv.target_for_hotfix(rv.Release(0, 1, 0), []) == rv.Release(0, 1, 0)


def test_ls_remote_output_is_peeled_to_commits() -> None:
    output = (
        "1111111111111111111111111111111111111111\trefs/tags/v0.1.0-dev.1\n"
        "2222222222222222222222222222222222222222\trefs/tags/v0.1.0-dev.2\n"
        "3333333333333333333333333333333333333333\trefs/tags/v0.1.0-dev.2^{}\n"
    )

    assert rv.parse_ls_remote_tags(output) == {
        "v0.1.0-dev.1": "1" * 40,
        "v0.1.0-dev.2": "3" * 40,
    }


# --------------------------------------------------------------------------------------------
# Pruning
# --------------------------------------------------------------------------------------------


def test_prune_keeps_the_newest_dev_prereleases_and_never_touches_anything_else() -> None:
    releases: list[dict[str, object]] = [
        {"tagName": f"v0.1.0-dev.{n}", "isPrerelease": True, "createdAt": f"2026-09-{n:02d}T00:00:00Z"}
        for n in range(1, 8)
    ]
    releases += [
        {"tagName": "v0.0.9", "isPrerelease": False, "createdAt": "2026-08-01T00:00:00Z"},
        {"tagName": "v0.0.9-rc.1", "isPrerelease": True, "createdAt": "2026-07-01T00:00:00Z"},
    ]

    assert rv.releases_to_prune(releases, keep=5) == ["v0.1.0-dev.2", "v0.1.0-dev.1"]
    assert rv.releases_to_prune(releases, keep=30) == []


def test_prune_refuses_to_keep_nothing() -> None:
    with pytest.raises(rv.ReleaseVersionError, match="at least 1"):
        rv.releases_to_prune([], keep=0)


# --------------------------------------------------------------------------------------------
# Claiming against a fake store
# --------------------------------------------------------------------------------------------


class ScriptedStore:
    """A tag store whose pushes fail as scripted, for the failure paths real git cannot stage."""

    def __init__(self, results: list[tuple[rv.PushResult, str]]) -> None:
        self.results = results
        self.tags: dict[str, str] = {}
        self.pushed: list[str] = []

    def dev_tags(self) -> dict[str, str]:
        return dict(self.tags)

    def push_tag(self, tag: str, sha: str) -> tuple[rv.PushResult, str]:
        self.pushed.append(tag)
        result = self.results.pop(0)
        if result[0] is rv.PushResult.CREATED:
            self.tags[tag] = sha
        return result


def test_a_push_that_keeps_failing_for_another_reason_is_reported() -> None:
    store = ScriptedStore([(rv.PushResult.FAILED, "fatal: could not read from remote repository")] * 5)

    with pytest.raises(rv.ReleaseVersionError, match="could not read from remote"):
        rv.claim_dev_tag(store, rv.Release(0, 1, 0), "a" * 40)
    assert len(store.pushed) == rv.MAX_UNEXPLAINED_PUSH_FAILURES


def test_a_transient_failure_is_retried() -> None:
    store = ScriptedStore([(rv.PushResult.FAILED, "blip"), (rv.PushResult.CREATED, "")])

    claim = rv.claim_dev_tag(store, rv.Release(0, 1, 0), "a" * 40)

    assert claim.build.tag == "v0.1.0-dev.1"
    assert store.pushed == ["v0.1.0-dev.1", "v0.1.0-dev.1"]


# --------------------------------------------------------------------------------------------
# Claiming against a real git remote
# --------------------------------------------------------------------------------------------


@pytest.fixture
def git_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Git that ignores the worktree the tests run in and any user or system config."""
    for name in list(os.environ):
        if name.startswith("GIT_"):
            monkeypatch.delenv(name)
    for name, value in {
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.test",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.test",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def commit(cwd: Path, name: str) -> str:
    (cwd / name).write_text(name, encoding="utf-8")
    git(cwd, "add", name)
    git(cwd, "commit", "-q", "-m", f"Add {name}")
    return git(cwd, "rev-parse", "HEAD").strip()


def remote_tags(remote: Path) -> dict[str, str]:
    return rv.parse_ls_remote_tags(git(remote, "ls-remote", "--tags", str(remote)))


@pytest.fixture
def remote(tmp_path: Path, git_env: None) -> Path:
    """A bare repository standing in for GitHub."""
    path = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "dev", str(path))
    return path


@pytest.fixture
def clone(tmp_path: Path, remote: Path) -> Path:
    """A checkout of `remote` with the debate_cli pyproject at version 0.1.0, pushed to dev."""
    path = tmp_path / "clone"
    git(tmp_path, "clone", "-q", str(remote), str(path))
    git(path, "switch", "-q", "-c", "dev")
    pyproject = path / rv.VERSION_SOURCE
    pyproject.parent.mkdir(parents=True)
    pyproject.write_text('[project]\nname = "debate-cli"\nversion = "0.1.0"\n', encoding="utf-8")
    git(path, "add", ".")
    git(path, "commit", "-q", "-m", "Initial")
    git(path, "push", "-q", "origin", "dev")
    return path


def merge_to_dev(clone: Path, name: str) -> str:
    sha = commit(clone, name)
    git(clone, "push", "-q", "origin", "dev")
    return sha


def test_two_consecutive_merges_get_n_and_n_plus_one(clone: Path, remote: Path) -> None:
    store = rv.GitTagStore("origin", clone)
    first = merge_to_dev(clone, "first")
    second = merge_to_dev(clone, "second")

    one = rv.claim_dev_tag(store, rv.Release(0, 1, 0), first)
    two = rv.claim_dev_tag(store, rv.Release(0, 1, 0), second)

    assert (one.build.tag, two.build.tag) == ("v0.1.0-dev.1", "v0.1.0-dev.2")
    assert remote_tags(remote) == {"v0.1.0-dev.1": first, "v0.1.0-dev.2": second}


def test_overlapping_runs_never_reuse_a_number(clone: Path, remote: Path) -> None:
    """Run B lists the tags, run A claims the number B computed, B's push is rejected, B retries."""
    target = rv.Release(0, 1, 0)
    rv.claim_dev_tag(rv.GitTagStore("origin", clone), target, merge_to_dev(clone, "earlier"))
    sha_a = merge_to_dev(clone, "merge-a")
    sha_b = merge_to_dev(clone, "merge-b")

    class StaleAfterListing(rv.GitTagStore):
        """B's store: right after B's first listing, A's whole run happens."""

        interleaved = False

        def dev_tags(self) -> dict[str, str]:
            listing = super().dev_tags()
            if not self.interleaved:
                self.interleaved = True
                rv.claim_dev_tag(rv.GitTagStore("origin", clone), target, sha_a)
            return listing

    run_b = rv.claim_dev_tag(StaleAfterListing("origin", clone), target, sha_b)

    assert run_b.build.tag == "v0.1.0-dev.3"
    tags = remote_tags(remote)
    assert tags["v0.1.0-dev.2"] == sha_a  # A kept the number B first computed
    assert tags["v0.1.0-dev.3"] == sha_b
    assert len(tags) == 3


def test_many_simultaneous_runs_get_distinct_consecutive_numbers(clone: Path, remote: Path) -> None:
    shas = [merge_to_dev(clone, f"merge-{index}") for index in range(8)]
    claims: dict[str, str] = {}
    errors: list[BaseException] = []
    start = threading.Barrier(len(shas))

    def run(sha: str) -> None:
        try:
            start.wait()
            claims[sha] = rv.claim_dev_tag(
                rv.GitTagStore("origin", clone), rv.Release(0, 1, 0), sha
            ).build.tag
        except BaseException as error:  # noqa: BLE001 - surfaced below
            errors.append(error)

    threads = [threading.Thread(target=run, args=(sha,)) for sha in shas]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert sorted(claims.values(), key=lambda tag: int(tag.rsplit(".", 1)[1])) == [
        f"v0.1.0-dev.{n}" for n in range(1, 9)
    ]
    assert {sha: tag for tag, sha in remote_tags(remote).items()} == claims


def test_rerunning_for_the_same_commit_returns_its_existing_tag(clone: Path, remote: Path) -> None:
    store = rv.GitTagStore("origin", clone)
    sha = merge_to_dev(clone, "only")

    first = rv.claim_dev_tag(store, rv.Release(0, 1, 0), sha)
    again = rv.claim_dev_tag(store, rv.Release(0, 1, 0), sha)

    assert (first.reused, again.reused) == (False, True)
    assert again.build == first.build
    assert remote_tags(remote) == {"v0.1.0-dev.1": sha}


def test_an_existing_tag_is_never_moved(clone: Path, remote: Path) -> None:
    store = rv.GitTagStore("origin", clone)
    taken_by = merge_to_dev(clone, "first")
    rv.claim_dev_tag(store, rv.Release(0, 1, 0), taken_by)
    other = merge_to_dev(clone, "second")

    result, _ = store.push_tag("v0.1.0-dev.1", other)

    assert result is rv.PushResult.TAKEN
    assert remote_tags(remote)["v0.1.0-dev.1"] == taken_by


# --------------------------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------------------------


def test_claim_prints_and_writes_github_outputs(
    clone: Path,
    remote: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sha = merge_to_dev(clone, "merged")
    outputs = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))

    code = rv.main(["claim", "--source", "dev", "--sha", sha, "--repository", str(clone)])

    assert code == 0
    expected = {
        "tag": "v0.1.0-dev.1",
        "version": "0.1.0.dev1",
        "number": "1",
        "target": "0.1.0",
        "sha": sha,
        "reused": "false",
    }
    assert json.loads(capsys.readouterr().out) == expected
    assert outputs.read_text(encoding="utf-8").splitlines() == [
        f"{key}={value}" for key, value in expected.items()
    ]


def test_next_pushes_nothing(clone: Path, remote: Path, capsys: pytest.CaptureFixture[str]) -> None:
    sha = merge_to_dev(clone, "merged")

    assert rv.main(["next", "--source", "dev", "--sha", sha, "--repository", str(clone)]) == 0

    assert json.loads(capsys.readouterr().out)["tag"] == "v0.1.0-dev.1"
    assert remote_tags(remote) == {}


def test_a_hotfix_head_is_tagged_with_its_patch_target(
    clone: Path, remote: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    released = merge_to_dev(clone, "released")
    git(clone, "tag", "v0.1.0", released)
    git(clone, "push", "-q", "origin", "v0.1.0")
    git(clone, "switch", "-q", "-c", "hotfix/login-crash", released)
    fix = commit(clone, "fix")
    git(clone, "push", "-q", "origin", "hotfix/login-crash")

    code = rv.main(["claim", "--source", "hotfix", "--sha", fix, "--repository", str(clone)])

    assert code == 0
    assert json.loads(capsys.readouterr().out)["tag"] == "v0.1.1-dev.1"
    assert remote_tags(remote)["v0.1.1-dev.1"] == fix


def test_claim_refuses_a_version_that_was_already_released(
    clone: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sha = merge_to_dev(clone, "released")
    git(clone, "tag", "v0.1.0", sha)

    assert rv.main(["claim", "--source", "dev", "--sha", sha, "--repository", str(clone)]) == 1
    assert "v0.1.0 is already released" in capsys.readouterr().err


def test_claim_refuses_an_abbreviated_sha(clone: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert rv.main(["claim", "--source", "dev", "--sha", "abc123", "--repository", str(clone)]) == 1
    assert "full 40-character" in capsys.readouterr().err
