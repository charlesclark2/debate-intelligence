"""`debate-research --version`: version, release channel, environment and commit (v1-e01-t09).

A source checkout has no stamp and reports channel `local` with git's commit. A published build is
simulated by putting a `debate_cli._build_info` module in `sys.modules`, exactly what
`scripts/stamp_build.py` writes into the wheel, so these tests exercise the same lookup an installed
`debate-research` does without building one. Expected payloads are written by hand.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner, Result

from debate_cli import __version__, build_info
from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode
from debate_core.application.settings import find_repository_root

runner = CliRunner()

DEV_COMMIT = "0123456789abcdef0123456789abcdef01234567"
STABLE_COMMIT = "fedcba9876543210fedcba9876543210fedcba98"


def _repository_root() -> Path:
    root = find_repository_root(Path(__file__).parent)
    assert root is not None
    return root


REPOSITORY_ROOT = _repository_root()


@pytest.fixture(autouse=True)
def outside_any_checkout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """No `DEBATE_*` variables, and a working directory with no checkout and no `.env` around it."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.chdir(home)
    yield home


def stamp(monkeypatch: pytest.MonkeyPatch, **info: str) -> None:
    """Make this process look like a published build stamped with `info`."""
    module = types.ModuleType("debate_cli._build_info")
    module.BUILD_INFO = dict(info)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "debate_cli._build_info", module)


def stamp_dev_prerelease(monkeypatch: pytest.MonkeyPatch) -> None:
    stamp(
        monkeypatch,
        version="0.1.0.dev3",
        tag="v0.1.0-dev.3",
        channel="dev",
        commit=DEV_COMMIT,
        built_at="2026-09-27T12:00:00Z",
        run_id="4242",
    )


def envelope_of(result: Result) -> dict[str, Any]:
    lines = result.stdout.splitlines()
    assert len(lines) == 1, f"expected one line of JSON on stdout, got {lines!r}"
    parsed = json.loads(lines[0])
    assert isinstance(parsed, dict)
    return parsed


# ---------------------------------------------------------------------------------------------
# A source checkout
# ---------------------------------------------------------------------------------------------


def test_a_source_checkout_reports_channel_local_and_the_checkouts_commit() -> None:
    head = subprocess.run(
        ["git", "-C", str(REPOSITORY_ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()

    result = runner.invoke(create_app(), ["--version", "--json"])

    assert result.exit_code == ExitCode.OK
    assert envelope_of(result)["data"] == {
        "package": "debate-cli",
        "version": __version__,
        "channel": "local",
        "commit": head,
        "tag": None,
        "built_at": None,
        "run_id": None,
        "environment": "dev",
        "environment_source": "default",
    }


def test_a_checkout_git_cannot_read_reports_no_commit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(build_info, "_PACKAGE_DIRECTORY", tmp_path)

    result = runner.invoke(create_app(), ["--version"])

    assert result.exit_code == ExitCode.OK
    assert "unknown commit" in result.stdout
    assert build_info.current_build_info().commit is None


def test_a_source_checkout_has_no_bundled_configuration() -> None:
    assert build_info.build_channel() == "local"
    assert build_info.bundled_config_root() is None


# ---------------------------------------------------------------------------------------------
# A published build
# ---------------------------------------------------------------------------------------------


def test_a_dev_prerelease_reports_its_tag_channel_environment_and_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stamp_dev_prerelease(monkeypatch)

    result = runner.invoke(create_app(), ["--version", "--json"])

    assert result.exit_code == ExitCode.OK
    assert envelope_of(result)["data"] == {
        "package": "debate-cli",
        "version": "0.1.0.dev3",
        "channel": "dev",
        "commit": DEV_COMMIT,
        "tag": "v0.1.0-dev.3",
        "built_at": "2026-09-27T12:00:00Z",
        "run_id": "4242",
        "environment": "dev",
        "environment_source": "build-channel:dev",
    }


def test_the_human_form_names_the_channel_environment_and_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    stamp_dev_prerelease(monkeypatch)

    result = runner.invoke(create_app(), ["--version"])

    assert result.exit_code == ExitCode.OK
    assert result.stdout.strip() == "debate-research 0.1.0.dev3 (dev channel, dev environment, 0123456789ab)"


def test_a_stable_build_defaults_to_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    stamp(monkeypatch, version="0.1.0", tag="v0.1.0", channel="stable", commit=STABLE_COMMIT)

    data = envelope_of(runner.invoke(create_app(), ["--json", "--version"]))["data"]

    assert (data["channel"], data["environment"], data["environment_source"]) == (
        "stable",
        "prod",
        "build-channel:stable",
    )


def test_an_explicit_debate_env_beats_the_build_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    stamp(monkeypatch, version="0.1.0", tag="v0.1.0", channel="stable", commit=STABLE_COMMIT)
    monkeypatch.setenv("DEBATE_ENV", "dev")

    data = envelope_of(runner.invoke(create_app(), ["--json", "--version"]))["data"]

    assert (data["environment"], data["environment_source"]) == ("dev", "env:DEBATE_ENV")


def test_version_still_reads_no_profile_in_a_published_build(monkeypatch: pytest.MonkeyPatch) -> None:
    stamp_dev_prerelease(monkeypatch)
    monkeypatch.setenv("DEBATE_PROFILE_DIR", "/definitely/not/a/directory")

    assert runner.invoke(create_app(), ["--version"]).exit_code == ExitCode.OK


# ---------------------------------------------------------------------------------------------
# A published build reads the configuration bundled in its wheel
# ---------------------------------------------------------------------------------------------


@pytest.fixture
def bundled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """The committed config/ copied the way stamp_build.py bundles it, and the package pointed at it."""
    root = tmp_path / "_bundled_config"
    shutil.copytree(REPOSITORY_ROOT / "config", root / "config")
    monkeypatch.setattr(build_info, "_BUNDLED_CONFIG", root)
    return root


def test_the_bundle_is_used_only_by_a_stamped_build(bundled: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert build_info.bundled_config_root() is None
    stamp_dev_prerelease(monkeypatch)
    assert build_info.bundled_config_root() == bundled


def test_an_installed_dev_build_run_from_home_gets_the_dev_profile_and_the_caselist_gate(
    bundled: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What the launchd agent sees: no DEBATE_ENV, no checkout, working directory $HOME."""
    stamp_dev_prerelease(monkeypatch)

    result = runner.invoke(create_app(), ["--json", "config", "show"])

    assert result.exit_code == ExitCode.OK, result.output
    data = envelope_of(result)["data"]
    assert data["environment"] == "dev"
    assert data["sources"]["environment"] == "build-channel:dev"
    assert data["settings"]["caselist.api_enabled"] is True
    assert data["settings"]["models.routing_file"] == str(bundled / "config" / "model_routing.dev.yaml")
    assert (
        data["sources"]["models.budget_usd_daily"]
        == f"profile:{bundled / 'config' / 'profiles' / 'dev.toml'}"
    )


@pytest.mark.parametrize(("environment", "budget"), [("dev", 2.0), ("prod", 20.0)])
def test_config_show_differs_between_dev_and_prod_in_an_installed_build(
    environment: str, budget: float, bundled: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stamp_dev_prerelease(monkeypatch)
    monkeypatch.setenv("DEBATE_ENV", environment)

    data = envelope_of(runner.invoke(create_app(), ["--json", "config", "show"]))["data"]["settings"]

    assert data["storage.data_dir"] == str(Path(f"~/.debate-research/{environment}").expanduser())
    assert data["models.routing_file"] == str(bundled / "config" / f"model_routing.{environment}.yaml")
    assert data["models.budget_usd_daily"] == budget
