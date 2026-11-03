"""The wheels a stable release publishes: one version, and nothing that must not ship (v1-e09-t06).

`packages/debate_cli/pyproject.toml` is the single version source (`release_version.VERSION_SOURCE`):
the dev channel reads it, and a stable tag must name it. uv_build reads only a static version, so
every workspace pyproject carries the same number and a release bumps them together; the first tests
refuse a workspace where one differs.

The rest build the real debate_core and debate_cli wheels, as the release workflow does: a copy of
the checkout's tracked files is stamped for the stable channel at the version source, and `uv build`
runs on the copy, offline, with uv's own build backend. The member lists of those wheels are then
read: `stamp_build.py check-wheels` must accept them, and no member may be a fixture, a test module,
a `.env` file or a data file. The checkout the tests run in is never stamped.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import release_version as rv  # noqa: E402
import stamp_build as sb  # noqa: E402

COMMIT = "0123456789abcdef0123456789abcdef01234567"

BUILD_INPUTS = (
    "pyproject.toml",
    "uv.lock",
    "README.md",
    ".python-version",
    "packages",
    "config",
    "prompts",
)
"""What a wheel build of the workspace reads: the workspace root, its members, and what `stamp`
bundles. Tracked files only, as a CI checkout has them."""


def project_version(path: Path) -> str:
    with path.open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


# --------------------------------------------------------------------------------------------
# One version
# --------------------------------------------------------------------------------------------


def test_the_version_source_is_the_cli_pyproject() -> None:
    assert Path("packages/debate_cli/pyproject.toml") == rv.VERSION_SOURCE
    assert rv.read_version_source() == rv.Release.parse(project_version(REPO_ROOT / rv.VERSION_SOURCE))


def test_every_workspace_pyproject_carries_the_version_source_s_version() -> None:
    assert rv.workspace_version_mismatches(REPO_ROOT) == []


def test_the_workspace_pyprojects_are_every_member_and_the_root() -> None:
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        members = tomllib.load(handle)["tool"]["uv"]["workspace"]["members"]

    expected = {Path("pyproject.toml"), *(Path(member) / "pyproject.toml" for member in members)}
    assert {*rv.WORKSPACE_PYPROJECTS, rv.VERSION_SOURCE} == expected


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """The workspace's pyprojects, copied, each at version 1.4.0."""
    for relative in (*rv.WORKSPACE_PYPROJECTS, rv.VERSION_SOURCE):
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relative).write_text('[project]\nname = "x"\nversion = "1.4.0"\n', encoding="utf-8")
    return tmp_path


def test_a_workspace_at_one_version_has_no_mismatch(workspace: Path) -> None:
    assert rv.workspace_version_mismatches(workspace) == []


def test_debate_core_at_another_version_is_named(workspace: Path) -> None:
    (workspace / "packages/debate_core/pyproject.toml").write_text(
        '[project]\nname = "debate-core"\nversion = "1.3.0"\n', encoding="utf-8"
    )

    assert rv.workspace_version_mismatches(workspace) == [
        "packages/debate_core/pyproject.toml has version 1.3.0, but packages/debate_cli/pyproject.toml "
        "(the version source) has 1.4.0"
    ]


def test_every_pyproject_that_differs_is_named(workspace: Path) -> None:
    for relative in ("pyproject.toml", "packages/debate_workers/pyproject.toml"):
        (workspace / relative).write_text('[project]\nname = "x"\nversion = "1.5.0"\n', encoding="utf-8")

    problems = rv.workspace_version_mismatches(workspace)

    assert [problem.split(" has version ")[0] for problem in problems] == [
        "pyproject.toml",
        "packages/debate_workers/pyproject.toml",
    ]


def test_a_pyproject_with_no_version_is_named(workspace: Path) -> None:
    (workspace / "packages/debate_api/pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")

    assert rv.workspace_version_mismatches(workspace) == [
        "packages/debate_api/pyproject.toml has no [project] version"
    ]


# --------------------------------------------------------------------------------------------
# The real wheels
# --------------------------------------------------------------------------------------------


def tracked_build_inputs() -> list[str]:
    listed = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z", "--", *BUILD_INPUTS],
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    return [name for name in listed.split("\0") if name]


@pytest.fixture(scope="module")
def stable_build(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path, str]:
    """(copied checkout, dist directory, version): a stable build, stamped and built as release.yml does."""
    root = tmp_path_factory.mktemp("release") / "checkout"
    for name in tracked_build_inputs():
        source = REPO_ROOT / name
        if source.is_file():  # a tracked file deleted in the working tree is not built
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, root / name)
    version = str(rv.read_version_source(root))
    dist = root / "dist"
    info = sb.build_info(
        version=version,
        tag=f"v{version}",
        channel="stable",
        commit=COMMIT,
        run_id="4242",
        built_at="2026-11-02T12:00:00Z",
    )
    sb.stamp(root, info, dist)
    environment = {key: value for key, value in os.environ.items() if not key.startswith("UV_")}
    environment["UV_OFFLINE"] = "1"
    for package in ("debate-core", "debate-cli"):
        built = subprocess.run(
            ["uv", "build", "--package", package, "--wheel", "--out-dir", str(dist)],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert built.returncode == 0, (
            f"uv build --package {package} failed offline. uv builds these wheels with its own "
            "backend only when its version is inside the pyprojects' `uv_build` requirement; outside "
            f"it, it would download uv_build, which a test may not.\n{built.stderr}"
        )
    return root, dist, version


def members(dist: Path, distribution: str, version: str) -> list[str]:
    with zipfile.ZipFile(dist / f"{distribution}-{version}-py3-none-any.whl") as archive:
        return archive.namelist()


def test_the_build_is_exactly_the_two_wheels_at_the_version_source(
    stable_build: tuple[Path, Path, str],
) -> None:
    _, dist, version = stable_build

    assert version == str(rv.read_version_source(REPO_ROOT))
    assert sorted(wheel.name for wheel in dist.glob("*.whl")) == [
        f"debate_cli-{version}-py3-none-any.whl",
        f"debate_core-{version}-py3-none-any.whl",
    ]


def test_check_wheels_accepts_the_stable_build(stable_build: tuple[Path, Path, str]) -> None:
    root, dist, version = stable_build

    assert sb.check_wheels(dist, version, repository=root) == []


@pytest.mark.parametrize("distribution", ["debate_core", "debate_cli"])
def test_no_member_is_a_fixture_test_secret_or_data_file(
    stable_build: tuple[Path, Path, str], distribution: str
) -> None:
    _, dist, version = stable_build
    names = members(dist, distribution, version)

    assert len(names) > 50, f"{distribution}'s wheel lists only {len(names)} members"
    assert [(name, sb.forbidden_member(name)) for name in names if sb.forbidden_member(name)] == []


@pytest.mark.parametrize("distribution", ["debate_core", "debate_cli"])
def test_every_member_comes_from_the_package_s_own_source(
    stable_build: tuple[Path, Path, str], distribution: str
) -> None:
    """Nothing from a package's tests/, the repository's tests/ or a data directory reaches a wheel."""
    _, dist, version = stable_build

    outside = [
        name
        for name in members(dist, distribution, version)
        if not (
            name.startswith(f"{distribution}/") or name.startswith(f"{distribution}-{version}.dist-info/")
        )
    ]
    assert outside == []


def test_the_stable_build_info_names_the_stable_channel(stable_build: tuple[Path, Path, str]) -> None:
    _, dist, version = stable_build

    with zipfile.ZipFile(dist / f"debate_cli-{version}-py3-none-any.whl") as archive:
        stamped = sb._stamped_build_info(archive.read("debate_cli/_build_info.py").decode("utf-8"))
    assert (stamped["version"], stamped["tag"], stamped["channel"]) == (version, f"v{version}", "stable")
