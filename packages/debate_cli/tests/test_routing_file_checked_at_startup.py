"""The routing file is loaded and validated when a run loads its settings (v1-e05-t03 ac6).

A bad `config/model_routing.*.yaml` stops every command that reads settings before it does
anything else, with the typed `RoutingConfigError` naming the offending key: the same refusals
`RoutingPolicy.load` makes (v1-e05-t01 ac3), now made at startup rather than when the first model
call is built. Plain `doctor`, `--help` and `--version` read no settings, so a bad file does not
stop them; `scripts/install_channel.sh` and `validate-dev` depend on that (`commands/doctor.py`).
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode

runner = CliRunner()

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

ROUTE = "    provider: bedrock\n    model_id: stand-in-model\n    region: r\n    timeout_seconds: 30\n"
BAD_ROUTING_FILES = {
    "routes.card_selection": f"version: 1\nroutes:\n  card_selection:\n{ROUTE}",
    "routes.high_volume.model_id": (
        "version: 1\nroutes:\n  high_volume:\n    provider: bedrock\n    region: r\n    timeout_seconds: 30\n"
    ),
    "routes.high_volume.temperature": f"version: 1\nroutes:\n  high_volume:\n{ROUTE}    temperature: 1.5\n",
}


@pytest.fixture(autouse=True)
def routing_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """A dev profile this test owns, whose routing file is `tmp_path / "routing.yaml"`."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    routing = tmp_path / "routing.yaml"
    (profiles / "dev.toml").write_text(
        f'[storage]\ndata_dir = "{tmp_path / "data"}"\n'
        f'[models]\nrouting_file = "{routing}"\nbudget_usd_daily = 1.0\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("DEBATE_PROFILE_DIR", str(profiles))
    monkeypatch.setenv("DEBATE_ENV", "dev")
    yield routing


@pytest.mark.parametrize("key", list(BAD_ROUTING_FILES))
def test_a_bad_routing_file_stops_the_command_naming_the_key(routing_file: Path, key: str) -> None:
    routing_file.write_text(BAD_ROUTING_FILES[key], encoding="utf-8")

    result = runner.invoke(create_app(), ["--json", "config", "show"])

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output[-600:]
    envelope = json.loads(result.stdout)
    assert envelope["status"] == "error"
    assert envelope["error"]["code"] == "ROUTING_CONFIG_ERROR"
    assert envelope["error"]["details"]["field"] == key
    assert envelope.get("data") is None, "the command did not run"


def test_a_missing_routing_file_stops_the_command(routing_file: Path) -> None:
    result = runner.invoke(create_app(), ["--json", "config", "show"])

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output[-600:]
    error = json.loads(result.stdout)["error"]
    assert error["code"] == "ROUTING_CONFIG_ERROR"
    assert error["details"]["source"] == str(routing_file)


def test_a_valid_routing_file_lets_the_command_run(routing_file: Path) -> None:
    shutil.copyfile(REPOSITORY_ROOT / "config" / "model_routing.example.yaml", routing_file)

    result = runner.invoke(create_app(), ["--json", "config", "show"])

    assert result.exit_code == ExitCode.OK, result.output[-600:]
    assert json.loads(result.stdout)["data"]["settings"]["models.routing_file"] == str(routing_file)


@pytest.mark.parametrize("arguments", [["doctor"], ["--help"], ["--version"], ["config", "--help"]])
def test_what_reads_no_settings_is_not_stopped_by_a_bad_routing_file(
    routing_file: Path, arguments: list[str]
) -> None:
    routing_file.write_text(BAD_ROUTING_FILES["routes.high_volume.model_id"], encoding="utf-8")

    result = runner.invoke(create_app(), arguments)

    assert result.exit_code == ExitCode.OK, result.output[-600:]
