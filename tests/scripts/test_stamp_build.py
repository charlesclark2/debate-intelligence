"""Tests for `scripts/stamp_build.py`: stamping a build and refusing unpublishable wheels (v1-e01-t09).

Wheels here are small zip files written by hand with the members and METADATA a real `uv build`
produces, so the checks are exercised without building anything. The stamp itself runs against a
copy of the files it edits, never the checkout the tests run in.
"""

from __future__ import annotations

import json
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import stamp_build as sb  # noqa: E402

COMMIT = "0123456789abcdef0123456789abcdef01234567"
VERSION = "0.1.0.dev3"


def info(**changes: str) -> dict[str, str]:
    values = {
        "version": VERSION,
        "tag": "v0.1.0-dev.3",
        "channel": "dev",
        "commit": COMMIT,
        "run_id": "4242",
        "built_at": "2026-09-27T12:00:00Z",
    }
    values.update(changes)
    return sb.build_info(**values)


# --------------------------------------------------------------------------------------------
# Build info
# --------------------------------------------------------------------------------------------


def test_build_info_carries_every_field() -> None:
    assert info() == {
        "version": "0.1.0.dev3",
        "tag": "v0.1.0-dev.3",
        "channel": "dev",
        "commit": COMMIT,
        "built_at": "2026-09-27T12:00:00Z",
        "run_id": "4242",
    }


def test_a_stable_build_info_names_its_plain_tag() -> None:
    assert info(version="0.1.0", tag="v0.1.0", channel="stable")["tag"] == "v0.1.0"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"version": "0.1.0-dev.3"}, "X.Y.Z or X.Y.Z.devN"),
        ({"channel": "local"}, "--channel"),
        ({"commit": "abc123"}, "40-character"),
        ({"tag": "v0.1.0-dev.4"}, "does not name version"),
    ],
)
def test_bad_build_info_is_refused(changes: dict[str, str], message: str) -> None:
    with pytest.raises(sb.StampError, match=message):
        info(**changes)


# --------------------------------------------------------------------------------------------
# Stamping a checkout
# --------------------------------------------------------------------------------------------


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """The files `stamp` reads and edits, copied from the real checkout."""
    root = tmp_path / "checkout"
    for relative in (sb.CORE_PYPROJECT, sb.CLI_PYPROJECT):
        (root / relative).parent.mkdir(parents=True)
        shutil.copyfile(REPO_ROOT / relative, root / relative)
    (root / sb.CLI_PACKAGE).mkdir(parents=True)
    shutil.copytree(REPO_ROOT / "config", root / "config")
    return root


def test_stamp_sets_both_versions_and_pins_debate_core(checkout: Path, tmp_path: Path) -> None:
    sb.stamp(checkout, info(), tmp_path / "dist")

    core = (checkout / sb.CORE_PYPROJECT).read_text(encoding="utf-8")
    cli = (checkout / sb.CLI_PYPROJECT).read_text(encoding="utf-8")
    assert 'version = "0.1.0.dev3"' in core
    assert 'version = "0.1.0.dev3"' in cli
    assert '"debate-core[aws,docx,opencaselist]==0.1.0.dev3"' in cli


def test_stamp_writes_the_build_info_module_and_asset(checkout: Path, tmp_path: Path) -> None:
    sb.stamp(checkout, info(), tmp_path / "dist")

    module = (checkout / sb.BUILD_INFO_MODULE).read_text(encoding="utf-8")
    assert sb._stamped_build_info(module) == info()
    assert json.loads((tmp_path / "dist" / "build-info.json").read_text(encoding="utf-8")) == info()


def test_stamp_bundles_the_committed_profiles_and_routing_files(checkout: Path, tmp_path: Path) -> None:
    sb.stamp(checkout, info(), tmp_path / "dist")

    bundled = checkout / sb.BUNDLED_CONFIG / "config"
    assert sorted(path.relative_to(bundled).as_posix() for path in bundled.rglob("*") if path.is_file()) == [
        "model_routing.dev.yaml",
        "model_routing.example.yaml",
        "model_routing.prod.yaml",
        "profiles/dev.toml",
        "profiles/prod.toml",
        "profiles/test.toml",
    ]
    # The E34 policy gate travels with the build.
    assert "api_enabled = true" in (bundled / "profiles" / "dev.toml").read_text(encoding="utf-8")


def test_stamp_refuses_a_pyproject_it_cannot_edit_unambiguously(checkout: Path, tmp_path: Path) -> None:
    path = checkout / sb.CLI_PYPROJECT
    path.write_text(
        path.read_text(encoding="utf-8").replace('"debate-core[aws,docx,opencaselist]"', '"typer"')
    )

    with pytest.raises(sb.StampError, match="unpinned debate-core"):
        sb.stamp(checkout, info(), tmp_path / "dist")


# --------------------------------------------------------------------------------------------
# Checking wheels
# --------------------------------------------------------------------------------------------


def write_wheel(
    dist: Path, distribution: str, version: str, members: dict[str, str], requires: list[str]
) -> Path:
    dist.mkdir(parents=True, exist_ok=True)
    wheel = dist / f"{distribution}-{version}-py3-none-any.whl"
    metadata = "\n".join(
        ["Metadata-Version: 2.4", f"Name: {distribution.replace('_', '-')}", f"Version: {version}"]
        + [f"Requires-Dist: {requirement}" for requirement in requires]
    )
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, text in members.items():
            archive.writestr(name, text)
        archive.writestr(f"{distribution}-{version}.dist-info/METADATA", metadata + "\n")
    return wheel


def cli_members(version: str = VERSION) -> dict[str, str]:
    members = {member: "" for member in sb.REQUIRED_CLI_MEMBERS}
    members["debate_cli/_build_info.py"] = sb.render_build_info_module(info(version=version))
    members["debate_cli/app.py"] = ""
    return members


def good_dist(dist: Path) -> Path:
    write_wheel(dist, "debate_core", VERSION, {"debate_core/__init__.py": ""}, ["pydantic>=2.9"])
    write_wheel(
        dist, "debate_cli", VERSION, cli_members(), [f"debate-core[opencaselist]=={VERSION}", "typer>=0.15"]
    )
    return dist


def test_a_correct_pair_of_wheels_is_publishable(tmp_path: Path) -> None:
    assert sb.check_wheels(good_dist(tmp_path / "dist"), VERSION) == []


def test_an_extra_wheel_is_refused(tmp_path: Path) -> None:
    dist = good_dist(tmp_path / "dist")
    write_wheel(dist, "debate_api", VERSION, {}, [])

    assert any("expected exactly the wheels" in problem for problem in sb.check_wheels(dist, VERSION))


def test_an_unpinned_debate_core_is_refused(tmp_path: Path) -> None:
    dist = good_dist(tmp_path / "dist")
    write_wheel(dist, "debate_cli", VERSION, cli_members(), ["debate-core[opencaselist]", "typer>=0.15"])

    assert any("not pinned" in problem for problem in sb.check_wheels(dist, VERSION))


def test_a_wheel_without_bundled_profiles_is_refused(tmp_path: Path) -> None:
    dist = good_dist(tmp_path / "dist")
    members = cli_members()
    del members["debate_cli/_bundled_config/config/profiles/prod.toml"]
    write_wheel(dist, "debate_cli", VERSION, members, [f"debate-core=={VERSION}"])

    assert sb.check_wheels(dist, VERSION) == [
        f"debate_cli-{VERSION}-py3-none-any.whl: missing debate_cli/_bundled_config/config/profiles/prod.toml"
    ]


def test_a_version_mismatch_is_refused(tmp_path: Path) -> None:
    problems = sb.check_wheels(good_dist(tmp_path / "dist"), "0.1.0.dev4")

    assert any("METADATA says version 0.1.0.dev3, expected 0.1.0.dev4" in problem for problem in problems)


@pytest.mark.parametrize(
    "member",
    [
        "debate_cli/.env",
        "debate_cli/_bundled_config/.env.local",
        "debate_cli/secrets/anything.txt",
        "debate_cli/caselist_token",
        "debate_core/.debate-research/dev/evidence.json",
        "debate_core/store.sqlite3",
    ],
)
def test_secrets_and_local_data_are_refused(member: str, tmp_path: Path) -> None:
    dist = good_dist(tmp_path / "dist")
    members = cli_members()
    members[member] = "x"
    write_wheel(dist, "debate_cli", VERSION, members, [f"debate-core=={VERSION}"])

    assert any(member in problem for problem in sb.check_wheels(dist, VERSION))


def test_ordinary_members_are_allowed() -> None:
    assert sb.forbidden_member("debate_cli/commands/config.py") is None
    assert sb.forbidden_member("debate_cli/_bundled_config/config/profiles/dev.toml") is None
