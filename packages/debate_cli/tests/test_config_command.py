"""`debate-research config show`: what it prints, and what it must never print.

Run through Typer's `CliRunner` against the real application, so these exercise the same parsing,
the same envelope and the same exit codes an installed `debate-research` produces.

The secret used throughout is a distinctive string that would be unmistakable in output. Every
redaction test asserts on the *whole* of stdout and stderr, not on the field it expects to find
it in: a leak that reaches a Rich caption, a verbose diagnostic or an error message is exactly as
bad as one in the value column, and is likelier, because nobody was looking there.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.commands.config import settings_report
from debate_cli.container import ServiceContainer
from debate_cli.exit_codes import ExitCode
from debate_core.application.settings import SECRET_PLACEHOLDER, Settings, load_settings

runner = CliRunner()

CASELIST_TOKEN = "caselist-token-that-must-never-be-printed"
API_KEY = "semantic-scholar-key-that-must-never-be-printed"
CONTACT_EMAIL = "coach-address-that-must-never-be-printed@example.org"


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Run every command against a profile directory this test owns, with a known set of secrets."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)

    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "dev.toml").write_text(
        f'[storage]\ndata_dir = "{tmp_path / "dev-data"}"\n'
        f'[models]\nrouting_file = "{tmp_path / "routing.yaml"}"\nbudget_usd_daily = 2.0\n',
        encoding="utf-8",
    )
    (profiles / "prod.toml").write_text(
        f'[storage]\ndata_dir = "{tmp_path / "prod-data"}"\n'
        f'[models]\nrouting_file = "{tmp_path / "routing-prod.yaml"}"\nbudget_usd_daily = 20.0\n',
        encoding="utf-8",
    )
    (profiles / "test.toml").write_text(
        "allow_network = false\n[providers]\nenabled = []\n"
        f'[models]\nrouting_file = "{tmp_path / "routing.yaml"}"\nbudget_usd_daily = 0.0\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("DEBATE_PROFILE_DIR", str(profiles))
    monkeypatch.setenv("DEBATE_PROVIDERS__CASELIST_TOKEN", CASELIST_TOKEN)
    monkeypatch.setenv("DEBATE_PROVIDERS__SEMANTIC_SCHOLAR_API_KEY", API_KEY)
    monkeypatch.setenv("DEBATE_PROVIDERS__CONTACT_EMAIL", CONTACT_EMAIL)
    yield


def envelope_of(result: Result) -> dict[str, Any]:
    """Parse the result's stdout, asserting it is exactly one JSON object."""
    lines = result.stdout.splitlines()
    assert len(lines) == 1, f"expected one line of JSON on stdout, got {lines!r}"
    parsed = json.loads(lines[0])
    assert isinstance(parsed, dict)
    return parsed


def everything_written(result: Result) -> str:
    """Every byte the command produced, on either stream."""
    return result.stdout + result.stderr


# ---------------------------------------------------------------------------------------------
# The command runs and reports (acceptance criterion 3)
# ---------------------------------------------------------------------------------------------


def test_config_show_renders_a_table() -> None:
    result = runner.invoke(create_app(), ["config", "show"])

    assert result.exit_code == ExitCode.OK
    assert "Setting" in result.stdout
    assert "Source" in result.stdout
    assert "storage.data_dir" in result.stdout


def test_config_show_as_json_emits_one_envelope() -> None:
    result = runner.invoke(create_app(), ["--json", "config", "show"])

    assert result.exit_code == ExitCode.OK
    envelope = envelope_of(result)
    assert envelope["status"] == "ok"
    assert envelope["command"] == "config show"
    assert envelope["error"] is None


def test_the_json_payload_carries_every_setting() -> None:
    data = envelope_of(runner.invoke(create_app(), ["--json", "config", "show"]))["data"]

    expected = set(load_settings(environment="dev").redacted_dict())
    assert set(data["settings"]) == expected
    assert data["environment"] == "dev"


def test_every_setting_carries_a_source() -> None:
    data = envelope_of(runner.invoke(create_app(), ["--json", "config", "show"]))["data"]

    assert set(data["sources"]) == set(data["settings"])
    assert all(source for source in data["sources"].values())


def test_the_source_names_the_environment_variable_that_set_a_value() -> None:
    data = envelope_of(runner.invoke(create_app(), ["--json", "config", "show"]))["data"]

    assert data["sources"]["providers.caselist_token"] == "env:DEBATE_PROVIDERS__CASELIST_TOKEN"
    assert data["sources"]["storage.data_dir"].startswith("profile:")
    assert data["sources"]["http.user_agent_product"] == "default"


def test_the_payload_is_json_serialisable_all_the_way_down() -> None:
    envelope = envelope_of(runner.invoke(create_app(), ["--json", "config", "show"]))

    # Re-serialising without `default=str` proves nothing needed coercing on the way out.
    json.dumps(envelope)


def test_config_with_no_subcommand_lists_what_it_can_do() -> None:
    result = runner.invoke(create_app(), ["config"])

    assert result.exit_code == ExitCode.USAGE_ERROR
    assert "show" in everything_written(result)


def test_config_show_appears_in_the_root_help() -> None:
    assert "config" in runner.invoke(create_app(), ["--help"]).stdout


# ---------------------------------------------------------------------------------------------
# Redaction (acceptance criterion 3)
# ---------------------------------------------------------------------------------------------


def test_secrets_are_starred_in_the_json_payload() -> None:
    data = envelope_of(runner.invoke(create_app(), ["--json", "config", "show"]))["data"]

    assert data["settings"]["providers.caselist_token"] == SECRET_PLACEHOLDER
    assert data["settings"]["providers.semantic_scholar_api_key"] == SECRET_PLACEHOLDER
    assert data["settings"]["providers.contact_email"] == SECRET_PLACEHOLDER


@pytest.mark.parametrize(
    "arguments",
    [
        ["config", "show"],
        ["--json", "config", "show"],
        ["--verbose", "config", "show"],
        ["--json", "--verbose", "config", "show"],
    ],
)
def test_no_secret_reaches_either_stream_in_any_mode(arguments: list[str]) -> None:
    written = everything_written(runner.invoke(create_app(), arguments))

    assert CASELIST_TOKEN not in written
    assert API_KEY not in written
    assert CONTACT_EMAIL not in written


def test_an_unset_secret_is_reported_as_unset_rather_than_as_stars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`***` must mean "there is a secret here", or it tells the reader nothing."""
    monkeypatch.delenv("DEBATE_PROVIDERS__CASELIST_TOKEN")

    data = envelope_of(runner.invoke(create_app(), ["--json", "config", "show"]))["data"]

    assert data["settings"]["providers.caselist_token"] is None


def test_the_table_shows_stars_and_says_why() -> None:
    result = runner.invoke(create_app(), ["config", "show"])

    assert SECRET_PLACEHOLDER in result.stdout
    assert "Secrets" in result.stdout


# ---------------------------------------------------------------------------------------------
# Environment selection through the command (acceptance criterion 4)
# ---------------------------------------------------------------------------------------------


def test_debate_env_selects_the_reported_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEBATE_ENV", "prod")

    data = envelope_of(runner.invoke(create_app(), ["--json", "config", "show"]))["data"]

    assert data["environment"] == "prod"
    assert data["sources"]["environment"] == "env:DEBATE_ENV"


def test_dev_and_prod_report_different_data_dirs(monkeypatch: pytest.MonkeyPatch) -> None:
    development = envelope_of(runner.invoke(create_app(), ["--json", "config", "show"]))["data"]
    monkeypatch.setenv("DEBATE_ENV", "prod")
    production = envelope_of(runner.invoke(create_app(), ["--json", "config", "show"]))["data"]

    assert development["settings"]["storage.data_dir"] != production["settings"]["storage.data_dir"]
    assert (
        development["settings"]["models.budget_usd_daily"]
        < (production["settings"]["models.budget_usd_daily"])
    )


def test_an_unusable_debate_env_fails_the_command_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A typo in a variable is the user's mistake to fix, not a crash to report as a bug."""
    monkeypatch.setenv("DEBATE_ENV", "staging")

    result = runner.invoke(create_app(), ["--json", "config", "show"])

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    envelope = envelope_of(result)
    assert envelope["status"] == "error"
    assert envelope["error"]["code"] == "CONFIGURATION_ERROR"
    assert "dev, prod, test" in envelope["error"]["message"]
    assert envelope["error"]["hint"] is None  # not "this is a bug in debate-research"


def test_an_invalid_setting_is_reported_with_the_field_that_is_wrong(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEBATE_HTTP__MAX_RETRIES", "99")

    result = runner.invoke(create_app(), ["--json", "config", "show"])

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    error = envelope_of(result)["error"]
    assert "http.max_retries" in error["message"]
    assert error["details"]["field"] == "http.max_retries"


# ---------------------------------------------------------------------------------------------
# The command stays thin
# ---------------------------------------------------------------------------------------------


def test_settings_are_loaded_from_the_container_not_from_the_command(tmp_path: Path) -> None:
    """The command renders whatever the composition root hands it; it loads nothing itself."""
    prepared = load_settings(
        environment="test",
        overrides={"storage": {"data_dir": tmp_path / "from-the-container"}},
    )
    container = ServiceContainer(settings_loader=lambda: prepared)

    report = settings_report(container.settings)
    values = report["settings"]

    assert isinstance(values, dict)
    assert values["storage.data_dir"] == str(tmp_path / "from-the-container")
    assert report["environment"] == "test"


def test_loading_settings_is_deferred_until_a_command_asks_for_them() -> None:
    """`--version` must not read a profile file, or the CLI stops being instant."""
    calls: list[int] = []

    def counting_loader() -> Settings:
        calls.append(1)
        return load_settings(environment="test")

    container = ServiceContainer(settings_loader=counting_loader)

    assert container.settings_configured is True
    assert calls == []
    _ = container.settings
    assert calls == [1]


def test_version_does_not_load_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Belt and braces: a profile directory that would fail to load must not be touched."""
    monkeypatch.setenv("DEBATE_PROFILE_DIR", "/definitely/not/a/directory")

    assert runner.invoke(create_app(), ["--version"]).exit_code == ExitCode.OK
