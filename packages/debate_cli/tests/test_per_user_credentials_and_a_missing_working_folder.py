"""`config show` names a per-user credential's source, and a deleted working folder warns (`v1-e41-t22`).

Run through Typer's `CliRunner` against the real application. Each test's home folder is under
`tmp_path`, with `HOME` pointed at it and the settings' seam at its `.debate-research`; the values
are short invented strings, and every test that sets one asserts it reaches neither stream.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.model_routing import EXAMPLE_ROUTING_FILE
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode
from debate_core.application import settings as settings_module
from debate_core.application.settings import MISSING_WORKING_FOLDER_WARNING, SECRET_PLACEHOLDER

runner = CliRunner()

EMAIL = "cs-Em4il-k2W"
KEY = "cs-K3y-8Np5"
DEV_SOURCE = "user-env:~/.debate-research/dev.env"
MODES = [[], ["--json"], ["--verbose"], ["--json", "--verbose"]]


@pytest.fixture(autouse=True)
def installation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """A dev profile under tmp_path, a home folder with an empty per-user folder, run outside any checkout."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "dev.toml").write_text(
        f'[storage]\ndata_dir = "{tmp_path / "data"}"\n'
        f'[models]\nrouting_file = "{EXAMPLE_ROUTING_FILE}"\nbudget_usd_daily = 1.0\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("DEBATE_PROFILE_DIR", str(profiles))
    monkeypatch.setenv("DEBATE_ENV", "dev")
    home = tmp_path / "home"
    (home / ".debate-research").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(settings_module, "user_credentials_directory", lambda: home / ".debate-research")
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    yield home


def per_user_file(home: Path, *lines: str, mode: int = 0o600) -> Path:
    path = home / ".debate-research" / "dev.env"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(mode)
    return path


def envelope_of(result: Result) -> dict[str, Any]:
    lines = result.stdout.splitlines()
    assert len(lines) == 1, f"expected one line of JSON on stdout, got {lines!r}\n{result.stderr}"
    parsed: dict[str, Any] = json.loads(lines[0])
    return parsed


def flat(text: str) -> str:
    """Text with the table's and panel's borders taken off, on one line."""
    return " ".join(re.sub(r"[│┃┏┓┗┛━─┡┩╇╭╮╰╯┼┬┴├┤┌┐└┘]", " ", text).split())


@pytest.fixture
def deleted_folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    folder = tmp_path / "removed-worktree"
    folder.mkdir()
    monkeypatch.chdir(folder)
    folder.rmdir()
    return folder


# ---------------------------------------------------------------------------------------------
# config show
# ---------------------------------------------------------------------------------------------


def test_config_show_names_the_per_user_file_as_the_source_and_masks_the_value(installation: Path) -> None:
    per_user_file(
        installation, f"DEBATE_PROVIDERS__CONTACT_EMAIL={EMAIL}", f"DEBATE_PROVIDERS__API_DATA_GOV_KEY={KEY}"
    )

    data = envelope_of(runner.invoke(create_app(), ["--json", "config", "show"]))["data"]

    assert data["sources"]["providers.contact_email"] == DEV_SOURCE
    assert data["sources"]["providers.api_data_gov_key"] == DEV_SOURCE
    assert data["settings"]["providers.contact_email"] == SECRET_PLACEHOLDER
    assert data["settings"]["providers.api_data_gov_key"] == SECRET_PLACEHOLDER
    assert set(data) == {"environment", "settings", "sources"}


def test_the_config_show_table_puts_the_source_beside_the_stars(installation: Path) -> None:
    per_user_file(installation, f"DEBATE_PROVIDERS__CONTACT_EMAIL={EMAIL}")

    result = runner.invoke(create_app(), ["config", "show"])

    assert result.exit_code == ExitCode.OK
    assert f"providers.contact_email {SECRET_PLACEHOLDER} {DEV_SOURCE}" in flat(result.stdout)


def test_config_show_names_only_the_winner_when_a_variable_shadows_the_file(
    installation: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    per_user_file(installation, f"DEBATE_PROVIDERS__CONTACT_EMAIL={EMAIL}")
    monkeypatch.setenv("DEBATE_PROVIDERS__CONTACT_EMAIL", KEY)

    result = runner.invoke(create_app(), ["config", "show"])

    assert "providers.contact_email *** env:DEBATE_PROVIDERS__CONTACT_EMAIL" in flat(result.stdout)
    assert DEV_SOURCE not in result.stdout


@pytest.mark.parametrize("mode", MODES)
def test_no_per_user_value_reaches_either_stream_in_any_mode(installation: Path, mode: list[str]) -> None:
    per_user_file(
        installation, f"DEBATE_PROVIDERS__CONTACT_EMAIL={EMAIL}", f"DEBATE_PROVIDERS__API_DATA_GOV_KEY={KEY}"
    )

    result = runner.invoke(create_app(), [*mode, "config", "show"])

    assert result.exit_code == ExitCode.OK
    assert EMAIL not in result.stdout + result.stderr
    assert KEY not in result.stdout + result.stderr


@pytest.mark.parametrize("mode", MODES)
def test_a_group_readable_file_stops_the_command_with_the_chmod_fix_and_no_value(
    installation: Path, mode: list[str]
) -> None:
    per_user_file(installation, f"DEBATE_PROVIDERS__CONTACT_EMAIL={EMAIL}", mode=0o640)

    result = runner.invoke(create_app(), [*mode, "config", "show"])

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert "chmod 600 ~/.debate-research/dev.env" in flat(result.stdout + result.stderr)
    assert EMAIL not in result.stdout + result.stderr


def test_a_name_that_is_not_a_credential_stops_the_command_by_line_and_no_value(installation: Path) -> None:
    per_user_file(installation, f"DEBATE_PROVIDERS__CONTACT_EMAIL={EMAIL}", f"DEBATE_HTTP__CONTACT_URL={KEY}")

    result = runner.invoke(create_app(), ["--json", "config", "show"])

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope_of(result)["error"]["message"].startswith(
        "~/.debate-research/dev.env line 2: DEBATE_HTTP__CONTACT_URL is not a credential;"
    )
    assert EMAIL not in result.stdout + result.stderr
    assert KEY not in result.stdout + result.stderr


# ---------------------------------------------------------------------------------------------
# A working folder that no longer exists
# ---------------------------------------------------------------------------------------------


@pytest.mark.usefixtures("deleted_folder")
def test_version_from_a_deleted_folder_exits_0_with_one_warning_line() -> None:
    result = runner.invoke(create_app(), ["--version"])

    assert result.exit_code == ExitCode.OK, result.stdout + result.stderr
    assert result.stderr.splitlines() == [MISSING_WORKING_FOLDER_WARNING]
    assert "debate-research" in result.stdout


@pytest.mark.usefixtures("deleted_folder")
def test_version_as_json_from_a_deleted_folder_keeps_stdout_one_envelope() -> None:
    result = runner.invoke(create_app(), ["--json", "--version"])

    assert result.exit_code == ExitCode.OK, result.stdout + result.stderr
    assert envelope_of(result)["data"]["environment"] == "dev"
    assert result.stderr.splitlines() == [MISSING_WORKING_FOLDER_WARNING]


@pytest.mark.usefixtures("deleted_folder")
def test_a_command_that_loads_settings_runs_from_a_deleted_folder_and_warns_once(installation: Path) -> None:
    per_user_file(installation, f"DEBATE_PROVIDERS__CONTACT_EMAIL={EMAIL}")

    result = runner.invoke(create_app(), ["--json", "config", "show"])

    assert result.exit_code == ExitCode.OK, result.stdout + result.stderr
    assert envelope_of(result)["data"]["sources"]["providers.contact_email"] == DEV_SOURCE
    assert result.stderr.splitlines() == [MISSING_WORKING_FOLDER_WARNING]


def test_the_warning_says_what_was_skipped_and_what_still_applies() -> None:
    assert MISSING_WORKING_FOLDER_WARNING == (
        "warning: the folder this command was run from no longer exists, so no .env was read from it or "
        "from a checkout around it; exported variables and ~/.debate-research/<env>.env still apply."
    )


def test_no_warning_from_a_folder_that_exists() -> None:
    result = runner.invoke(create_app(), ["--version"])

    assert result.exit_code == ExitCode.OK
    assert MISSING_WORKING_FOLDER_WARNING not in result.stderr


@pytest.mark.usefixtures("deleted_folder")
def test_help_from_a_deleted_folder_exits_0() -> None:
    result = runner.invoke(create_app(), ["--help"])

    assert result.exit_code == ExitCode.OK
