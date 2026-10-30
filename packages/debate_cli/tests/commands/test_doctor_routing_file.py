"""`debate-research doctor --routing-file`: whether the model-routing file the settings name loads.

`v1-e05-t09`, from `v1-e05-t03`'s Deviation 4. A bad routing file stops every command that reads
settings (`v1-e05-t03` ac6), but not plain `doctor`, which loads no settings because
`scripts/install_channel.sh` and `validate-dev` run it on machines with no installation at all.
With `--routing-file`, `doctor` loads them and reports the file: the classes it routes, or the
refusal with the offending key, and then it fails.

Every installation here is a dev profile under `tmp_path` whose routing file this test writes.
Nothing reads an AWS config or reaches a network.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.model_routing import EXAMPLE_ROUTING_FILE
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.container import ServiceContainer
from debate_cli.exit_codes import ExitCode

runner = CliRunner()

DOES_NOT_LOAD_CODE = "ROUTING_CONFIG_ERROR"
ROUTE = "    provider: bedrock\n    model_id: stand-in-model\n    region: r\n    timeout_seconds: 30\n"
BAD_ROUTING_FILES = {
    "routes.card_selection": f"version: 1\nroutes:\n  card_selection:\n{ROUTE}",
    "routes.high_volume.model_id": (
        "version: 1\nroutes:\n  high_volume:\n    provider: bedrock\n    region: r\n    timeout_seconds: 30\n"
    ),
    "routes.high_volume.temperature": f"version: 1\nroutes:\n  high_volume:\n{ROUTE}    temperature: 1.5\n",
}
EXAMPLE_ROUTES = ["complex_reasoning", "deep_audit", "embeddings", "high_volume", "rerank"]
"""What `config/model_routing.example.yaml` routes, read from the file, sorted."""


@pytest.fixture(autouse=True)
def routing_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """A dev profile whose routing file is `tmp_path / "routing.yaml"`, not yet written. No AWS config."""
    for name in list(os.environ):
        if name.startswith(("DEBATE_", "AWS_")):
            monkeypatch.delenv(name, raising=False)
    for name in ("AWS_CONFIG_FILE", "AWS_SHARED_CREDENTIALS_FILE"):
        monkeypatch.setenv(name, os.devnull)
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


def doctor(*arguments: str) -> tuple[int, dict[str, Any]]:
    result: Result = runner.invoke(create_app(), ["--json", "doctor", *arguments])
    lines = result.stdout.splitlines()
    assert len(lines) == 1, f"expected one line of JSON on stdout, got {lines!r}\n{result.stderr}"
    envelope: dict[str, Any] = json.loads(lines[0])
    return result.exit_code, envelope


def as_a_person_sees_it(*arguments: str) -> tuple[int, str]:
    """The table and any panel, on one line with the box drawn around them taken off."""
    result = runner.invoke(create_app(), ["doctor", *arguments])
    text = re.sub(r"[│┃┏┓┗┛━─┡┩╇╭╮╰╯┼┬┴├┤┌┐└┘╰╯]", " ", result.stdout + result.stderr)
    return result.exit_code, " ".join(text.split())


# ------------------------------------------------------------------------------------------------
# Plain doctor is as it was
# ------------------------------------------------------------------------------------------------


def test_plain_doctor_loads_no_settings_and_passes_with_a_bad_routing_file(
    routing_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    routing_file.write_text(BAD_ROUTING_FILES["routes.high_volume.model_id"], encoding="utf-8")

    def no_settings(self: ServiceContainer) -> Any:
        pytest.fail("plain doctor loaded settings")

    monkeypatch.setattr(ServiceContainer, "settings", property(no_settings))

    exit_code, envelope = doctor()

    assert exit_code == ExitCode.OK, envelope
    assert "routing_file" not in envelope["data"]


def test_plain_doctor_shows_no_routing_file_row(routing_file: Path) -> None:
    routing_file.write_text(BAD_ROUTING_FILES["routes.high_volume.model_id"], encoding="utf-8")

    exit_code, text = as_a_person_sees_it()

    assert exit_code == ExitCode.OK, text
    assert "Routing file" not in text
    assert "routing.yaml" not in text


# ------------------------------------------------------------------------------------------------
# A routing file that does not load fails the check, naming the key
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("key", list(BAD_ROUTING_FILES))
def test_doctor_routing_file_names_a_bad_files_key_and_exits_1(routing_file: Path, key: str) -> None:
    routing_file.write_text(BAD_ROUTING_FILES[key], encoding="utf-8")

    exit_code, envelope = doctor("--routing-file")

    assert exit_code == ExitCode.DOMAIN_FAILURE
    error = envelope["error"]
    assert error["code"] == DOES_NOT_LOAD_CODE
    assert key in error["message"]
    assert (
        error["hint"] == f"Fix `{key}` in {routing_file}, or point models.routing_file at a file that loads."
    )
    found = error["details"]["routing_file"]
    assert (found["routing_file"], found["loads"], found["field"], found["routes"]) == (
        str(routing_file),
        False,
        key,
        [],
    )
    assert envelope.get("data") is None


def test_doctor_routing_file_names_a_missing_file_and_exits_1(routing_file: Path) -> None:
    exit_code, envelope = doctor("--routing-file")

    assert exit_code == ExitCode.DOMAIN_FAILURE
    error = envelope["error"]
    assert error["code"] == DOES_NOT_LOAD_CODE
    assert f"model-routing file not found: {routing_file}" in error["message"]
    assert error["hint"] == f"Fix {routing_file}, or point models.routing_file at a file that loads."
    found = error["details"]["routing_file"]
    assert (found["loads"], found["field"]) == (False, None)


def test_doctor_routing_file_failure_as_a_person_sees_it(routing_file: Path) -> None:
    routing_file.write_text(BAD_ROUTING_FILES["routes.high_volume.temperature"], encoding="utf-8")

    exit_code, text = as_a_person_sees_it("--routing-file")

    assert exit_code == ExitCode.DOMAIN_FAILURE
    assert f"Routing file {routing_file}: does not load at routes.high_volume.temperature" in text
    assert "The model-routing file does not load, so every command that reads settings will refuse" in text


# ------------------------------------------------------------------------------------------------
# A routing file that loads passes it
# ------------------------------------------------------------------------------------------------


def test_doctor_routing_file_passes_and_lists_what_a_good_file_routes(routing_file: Path) -> None:
    shutil.copyfile(EXAMPLE_ROUTING_FILE, routing_file)

    exit_code, envelope = doctor("--routing-file")

    assert exit_code == ExitCode.OK, envelope
    assert envelope["data"]["routing_file"] == {
        "routing_file": str(routing_file),
        "loads": True,
        "routes": EXAMPLE_ROUTES,
        "field": None,
        "problem": None,
    }


def test_doctor_routing_file_row_as_a_person_sees_it(routing_file: Path) -> None:
    shutil.copyfile(EXAMPLE_ROUTING_FILE, routing_file)

    exit_code, text = as_a_person_sees_it("--routing-file")

    assert exit_code == ExitCode.OK, text
    assert f"Routing file {routing_file}: loads; routes {', '.join(EXAMPLE_ROUTES)}" in text
