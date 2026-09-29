#!/usr/bin/env python3
"""Compute and claim the next dev pre-release version (v1-e01-t09-dev-prerelease-channel).

Every green merge to `dev` becomes a GitHub pre-release tagged `vX.Y.Z-dev.N`, where `X.Y.Z` is the
next stable release and `N` counts dev builds of it. The wheels carry the PEP 440 spelling of the
same version, `X.Y.Z.devN`, which sorts *before* `X.Y.Z`, so a stable release always supersedes
every dev build of it (docs/process/branching-and-environments.md, "Releases").

Where `X.Y.Z` comes from:

* **dev** (a merge to `dev`): the `version` in `packages/debate_cli/pyproject.toml`, the single
  version source v1-e09-t06 later shares with debate_core. If a stable tag for that version, or a
  later one, already exists, the version was never bumped after a release; a dev build of it would
  sort before what is already published, so this refuses rather than guessing.
* **hotfix** (a manual dispatch for a `hotfix/*` head): the patch after the newest stable tag the
  head contains, e.g. `v1.1.1-dev.1` for a fix to `v1.1.0`. With no stable tag yet, the pyproject
  version, because nothing has been released that the fix could be a patch of.

## Claiming N when runs overlap

Two merges close together both list the tags, both see `dev.4` as the newest, and both want
`dev.5`. Computing N and hoping is how a number gets reused, and published tags are immutable, so a
collision could not be repaired by re-tagging. The one atomic operation available is the tag push
itself: the remote either creates `refs/tags/v0.1.0-dev.5` or rejects it because it exists. So
:func:`claim_dev_tag` pushes the tag for the head commit *first*, before anything is built, and a
rejected push means "another run took that N": it lists the tags again and tries the next one.

A commit that already has a dev tag for the same target gets that tag back instead of a second one,
which is what makes re-running the workflow for one commit safe.

N is unique and increases in the order runs *claim* it. Two overlapping merges are numbered in the
order their `ci` runs finished, which is not always the order they merged.

## Commands

    release_version.py next  --source dev|hotfix --sha SHA   # what would be claimed; pushes nothing
    release_version.py claim --source dev|hotfix --sha SHA   # push the tag, print the claim
    release_version.py prune --keep 30 < releases.json       # dev pre-releases to delete

`claim` also appends `tag=`, `version=`, `number=`, `target=` and `reused=` lines to the file named
by `$GITHUB_OUTPUT` when it is set. Standard library only, so the runner's own python3 runs it.
"""

from __future__ import annotations

import argparse
import enum
import json
import os
import re
import subprocess
import sys
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
VERSION_SOURCE = Path("packages/debate_cli/pyproject.toml")
"""The single version source, relative to the repository root."""

STABLE_TAG = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
DEV_TAG = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)-dev\.([1-9]\d*)$")
PLAIN_VERSION = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")

MAX_CLAIM_ATTEMPTS = 20
"""How many numbers one run will try before giving up. Each rejection means another run succeeded."""

MAX_UNEXPLAINED_PUSH_FAILURES = 3
"""Push failures that are not "the tag exists" (a ref lock held by a concurrent push, a network
blip) that one claim will retry before reporting the error."""

DEFAULT_KEEP = 30
"""Dev pre-releases kept by `prune`; older ones lose their release but keep their tag."""


class ReleaseVersionError(Exception):
    """The next version cannot be computed or claimed; the message says what to fix."""


class Source(enum.StrEnum):
    """What triggered the build, which decides where the stable target comes from."""

    DEV = "dev"
    HOTFIX = "hotfix"


@dataclass(frozen=True, order=True)
class Release:
    """A stable version `X.Y.Z`."""

    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, text: str) -> Release:
        match = PLAIN_VERSION.match(text.strip())
        if match is None:
            raise ReleaseVersionError(
                f"{text!r} is not a plain X.Y.Z version; {VERSION_SOURCE} must hold the next stable "
                "release, with no pre-release or local suffix"
            )
        major, minor, patch = (int(part) for part in match.groups())
        return cls(major, minor, patch)

    @classmethod
    def from_stable_tag(cls, tag: str) -> Release | None:
        match = STABLE_TAG.match(tag)
        if match is None:
            return None
        major, minor, patch = (int(part) for part in match.groups())
        return cls(major, minor, patch)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    @property
    def tag(self) -> str:
        return f"v{self}"

    def next_patch(self) -> Release:
        return Release(self.major, self.minor, self.patch + 1)


@dataclass(frozen=True)
class DevBuild:
    """Dev build number `number` of the stable release `target`."""

    target: Release
    number: int

    @property
    def tag(self) -> str:
        """The git tag and GitHub release name: `v0.1.0-dev.3`."""
        return f"{self.target.tag}-dev.{self.number}"

    @property
    def pep440(self) -> str:
        """The wheel version: `0.1.0.dev3`, which sorts before `0.1.0`."""
        return f"{self.target}.dev{self.number}"

    @classmethod
    def from_tag(cls, tag: str) -> DevBuild | None:
        match = DEV_TAG.match(tag)
        if match is None:
            return None
        major, minor, patch, number = (int(part) for part in match.groups())
        return cls(Release(major, minor, patch), number)


@dataclass(frozen=True)
class Claim:
    """The outcome of :func:`claim_dev_tag`."""

    build: DevBuild
    sha: str
    reused: bool
    """True when the commit already had this tag, from an earlier run for the same commit."""

    def as_outputs(self) -> dict[str, str]:
        return {
            "tag": self.build.tag,
            "version": self.build.pep440,
            "number": str(self.build.number),
            "target": str(self.build.target),
            "sha": self.sha,
            "reused": "true" if self.reused else "false",
        }


# ------------------------------------------------------------------------------------------------
# Pure computation
# ------------------------------------------------------------------------------------------------


def stable_releases(tags: Iterable[str]) -> list[Release]:
    """Every `vX.Y.Z` among `tags`, ignoring dev tags and anything else."""
    return [release for tag in tags if (release := Release.from_stable_tag(tag)) is not None]


def target_for_dev(version_source: Release, stable_tags: Iterable[str]) -> Release:
    """The stable target a merge to dev builds towards: the pyproject version, if still unreleased."""
    released = [release for release in stable_releases(stable_tags) if release >= version_source]
    if released:
        newest = max(released)
        raise ReleaseVersionError(
            f"{newest.tag} is already released, so dev builds of {version_source} would sort before "
            f"it; bump `version` in {VERSION_SOURCE} past {newest} (the next stable target)"
        )
    return version_source


def target_for_hotfix(version_source: Release, stable_tags_in_head: Iterable[str]) -> Release:
    """The patch a hotfix head builds towards: one past the newest stable release it contains."""
    released = stable_releases(stable_tags_in_head)
    if not released:
        return version_source
    return max(released).next_patch()


def next_dev_number(target: Release, dev_tags: Iterable[str]) -> int:
    """One more than the highest N already tagged for `target`, starting at 1."""
    numbers = [
        build.number
        for tag in dev_tags
        if (build := DevBuild.from_tag(tag)) is not None and build.target == target
    ]
    return max(numbers, default=0) + 1


def existing_build_for(target: Release, sha: str, dev_tags: Mapping[str, str]) -> DevBuild | None:
    """The dev build of `target` already tagged at `sha`, if a previous run claimed one."""
    builds = [
        build
        for tag, commit in dev_tags.items()
        if commit == sha and (build := DevBuild.from_tag(tag)) is not None and build.target == target
    ]
    return min(builds, key=lambda build: build.number) if builds else None


def releases_to_prune(releases: Iterable[Mapping[str, object]], keep: int) -> list[str]:
    """Tags of the dev pre-releases beyond the newest `keep`, oldest last.

    `releases` is `gh release list --json tagName,isPrerelease,createdAt` output. Only pre-releases
    whose tag is a dev tag are candidates: a stable release, or a pre-release someone made by hand,
    is never pruned. Pruning deletes the release and keeps its tag, so N keeps counting from the
    highest number ever claimed and is never reused.
    """
    if keep < 1:
        raise ReleaseVersionError(f"--keep must be at least 1, got {keep}")
    candidates = [
        release
        for release in releases
        if release.get("isPrerelease") is True
        and isinstance(release.get("tagName"), str)
        and DevBuild.from_tag(str(release["tagName"])) is not None
    ]
    candidates.sort(key=lambda release: str(release.get("createdAt", "")), reverse=True)
    return [str(release["tagName"]) for release in candidates[keep:]]


# ------------------------------------------------------------------------------------------------
# Claiming against a remote
# ------------------------------------------------------------------------------------------------


class PushResult(enum.Enum):
    CREATED = "created"
    TAKEN = "taken"
    """The remote already has a tag of that name: another run claimed the number."""
    FAILED = "failed"
    """Anything else, e.g. a ref lock held by a concurrent push. Worth retrying a few times."""


class TagStore(Protocol):
    """Where tags are listed and claimed: the git remote in production, a fake in some tests."""

    def dev_tags(self) -> dict[str, str]:
        """Every `v*-dev.*` tag on the remote, mapped to the commit it points at."""
        ...

    def push_tag(self, tag: str, sha: str) -> tuple[PushResult, str]:
        """Create `tag` at `sha` on the remote, never overwriting; the second item is git's stderr."""
        ...


def claim_dev_tag(
    store: TagStore, target: Release, sha: str, *, max_attempts: int = MAX_CLAIM_ATTEMPTS
) -> Claim:
    """Claim the next free dev number for `target` by pushing its tag at `sha`.

    The push is the claim. A rejected push means another run pushed that tag between our listing
    and our push, so the tags are listed again and the next number is tried.
    """
    unexplained: list[str] = []
    for _ in range(max_attempts):
        tags = store.dev_tags()
        already = existing_build_for(target, sha, tags)
        if already is not None:
            return Claim(already, sha, reused=True)
        build = DevBuild(target, next_dev_number(target, tags))
        result, detail = store.push_tag(build.tag, sha)
        if result is PushResult.CREATED:
            return Claim(build, sha, reused=False)
        if result is PushResult.FAILED:
            unexplained.append(detail.strip())
            if len(unexplained) >= MAX_UNEXPLAINED_PUSH_FAILURES:
                raise ReleaseVersionError(
                    f"pushing {build.tag} failed {len(unexplained)} times for a reason other than "
                    f"the tag existing; last error: {unexplained[-1] or '(no output)'}"
                )
    raise ReleaseVersionError(
        f"could not claim a dev number for {target} in {max_attempts} attempts; every number tried "
        "was taken by a concurrent run"
    )


_COLLISION_SIGNS = ("already exists", "cannot lock ref")
"""What git says when a tag push loses to another push of the same tag."""


class GitTagStore:
    """Tags on a git remote, listed with `ls-remote` and claimed with a non-forced push."""

    def __init__(self, remote: str = "origin", repository: Path = REPOSITORY_ROOT) -> None:
        self.remote = remote
        self.repository = repository

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", "-C", str(self.repository), *args],
            capture_output=True,
            text=True,
            check=False,
        )
        if check and result.returncode != 0:
            raise ReleaseVersionError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
        return result

    def dev_tags(self) -> dict[str, str]:
        output = self._git("ls-remote", "--tags", self.remote, "refs/tags/v*-dev.*").stdout
        return parse_ls_remote_tags(output)

    def push_tag(self, tag: str, sha: str) -> tuple[PushResult, str]:
        # A tag push without --force never replaces an existing tag, so the remote's ref update is
        # the atomic "is this number free" check.
        pushed = self._git("push", "--quiet", self.remote, f"{sha}:refs/tags/{tag}", check=False)
        if pushed.returncode == 0:
            return PushResult.CREATED, ""
        # "cannot lock ref" is another push writing this same tag at this moment: a concurrent run
        # claiming the same number, which is a collision exactly as much as "already exists" is.
        if any(sign in pushed.stderr for sign in _COLLISION_SIGNS) or tag in self.dev_tags():
            return PushResult.TAKEN, pushed.stderr
        return PushResult.FAILED, pushed.stderr

    def stable_tags(self, *, merged_into: str | None = None) -> list[str]:
        """Local stable tags; with `merged_into`, only those reachable from that commit."""
        args = ["tag", "--list", "v*"]
        if merged_into is not None:
            args += ["--merged", merged_into]
        return [tag for tag in self._git(*args).stdout.split() if STABLE_TAG.match(tag)]


def parse_ls_remote_tags(output: str) -> dict[str, str]:
    """`git ls-remote --tags` output as `{tag: commit}`, peeling annotated tags to their commit."""
    tags: dict[str, str] = {}
    peeled: dict[str, str] = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        sha, _, ref = line.partition("\t")
        name = ref.removeprefix("refs/tags/")
        if name.endswith("^{}"):
            peeled[name[:-3]] = sha
        else:
            tags[name] = sha
    tags.update(peeled)
    return tags


def read_version_source(repository: Path = REPOSITORY_ROOT) -> Release:
    """The `[project] version` of the debate_cli pyproject."""
    path = repository / VERSION_SOURCE
    with path.open("rb") as handle:
        project = tomllib.load(handle).get("project", {})
    version = project.get("version")
    if not isinstance(version, str):
        raise ReleaseVersionError(f"{VERSION_SOURCE} has no [project] version")
    return Release.parse(version)


def target_for(source: Source, sha: str, store: GitTagStore, repository: Path) -> Release:
    version_source = read_version_source(repository)
    if source is Source.HOTFIX:
        return target_for_hotfix(version_source, store.stable_tags(merged_into=sha))
    return target_for_dev(version_source, store.stable_tags())


# ------------------------------------------------------------------------------------------------
# Command line
# ------------------------------------------------------------------------------------------------


def _write_github_output(values: Mapping[str, str]) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with Path(path).open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n", 1)[0])
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("next", "print the version that would be claimed, without pushing anything"),
        ("claim", "push the next dev tag at --sha and print what was claimed"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--source", type=Source, choices=list(Source), required=True)
        command.add_argument("--sha", required=True, help="the commit to tag (full SHA)")
        command.add_argument("--remote", default="origin")
        command.add_argument("--repository", type=Path, default=REPOSITORY_ROOT)
    prune = commands.add_parser("prune", help="dev pre-release tags beyond the newest --keep")
    prune.add_argument("--keep", type=int, default=DEFAULT_KEEP)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "prune":
            for tag in releases_to_prune(json.load(sys.stdin), arguments.keep):
                print(tag)
            return 0

        store = GitTagStore(arguments.remote, arguments.repository)
        sha = arguments.sha.strip()
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ReleaseVersionError(f"--sha must be a full 40-character commit SHA, got {sha!r}")
        target = target_for(arguments.source, sha, store, arguments.repository)
        if arguments.command == "next":
            tags = store.dev_tags()
            existing = existing_build_for(target, sha, tags)
            build = existing or DevBuild(target, next_dev_number(target, tags))
            print(json.dumps(Claim(build, sha, reused=existing is not None).as_outputs()))
            return 0

        claim = claim_dev_tag(store, target, sha)
        outputs = claim.as_outputs()
        _write_github_output(outputs)
        print(json.dumps(outputs))
        return 0
    except ReleaseVersionError as error:
        print(f"release_version: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
