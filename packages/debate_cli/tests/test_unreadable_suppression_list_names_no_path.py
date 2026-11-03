"""`caselist import` against a suppression list it cannot read names the list, never its path.

The local copy of the list is `<data_dir>/suppression/suppression-list.jsonl`, and a data directory
sits under the operator's home directory. An error is copied into a terminal, a log and the `--json`
envelope, so the copy is named by its role, the local suppression list under `storage.data_dir`
(`v1-e30-t10`, from `v1-e34-t13`'s follow-up work).

The data directory here is a probe: its path holds a marker that occurs nowhere else, so the marker
in the command's output can only have come from the path.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from tests.fixtures.caselist.build_synthetic_archives import (
    SNAPSHOTS,
    SYNTHETIC_CASELIST,
    build_snapshot_zips,
)
from tests.fixtures.model_routing import EXAMPLE_ROUTING_FILE
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode

runner = CliRunner()

PROBE = "Zqxprobe"
ROLE = "the local suppression list under storage.data_dir"
#: One finished line and one a write never finished: the list is refused, not read as far as it goes.
TORN_LIST = '{"action":"SUPPRESS"}\n{"action":"SUPP'
#: One finished line this build cannot read as an entry: it names no file.
NOT_AN_ENTRY = '{"action":"SUPPRESS"}\n'
#: Each unreadable list, the line the error names and the reason it gives.
UNREADABLE = [
    pytest.param(
        TORN_LIST, 2, "the last line has no newline (a write was interrupted)", id="a torn last line"
    ),
    pytest.param(NOT_AN_ENTRY, 1, "Field required", id="not an entry"),
]


@pytest.fixture
def probe_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """A dev profile whose data directory's path holds :data:`PROBE`, and no inherited DEBATE_* vars."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    assert PROBE.casefold() not in str(tmp_path).casefold()
    data_dir = tmp_path / f"home-of-{PROBE}" / "data"
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "dev.toml").write_text(
        f'[storage]\ndata_dir = "{data_dir}"\n'
        f'[models]\nrouting_file = "{EXAMPLE_ROUTING_FILE}"\nbudget_usd_daily = 1.0\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("DEBATE_PROFILE_DIR", str(profiles))
    monkeypatch.setenv("DEBATE_ENV", "dev")
    yield data_dir


def import_first_week(tmp_path: Path, *prefix: str) -> Result:
    week = SNAPSHOTS[0].snapshot
    archive = build_snapshot_zips(tmp_path / "archives")[week]
    target = ("--caselist", SYNTHETIC_CASELIST, "--snapshot", week.isoformat())
    return runner.invoke(create_app(), [*prefix, "caselist", "import", str(archive), *target])


def write_list(data_dir: Path, text: str) -> Path:
    path = data_dir / "suppression" / "suppression-list.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize(("unreadable", "line_number", "reason"), UNREADABLE)
def test_the_error_a_person_reads_names_the_list_by_its_role(
    probe_data_dir: Path, tmp_path: Path, unreadable: str, line_number: int, reason: str
) -> None:
    write_list(probe_data_dir, unreadable)

    result = import_first_week(tmp_path)

    shown = result.stdout + result.stderr
    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert "UNREADABLE_APPEND_ONLY_RECORD" in shown
    assert PROBE.casefold() not in shown.casefold(), "the data directory's path reached the terminal"
    assert "suppression-list.jsonl" not in shown
    assert f"line {line_number}" in " ".join(shown.split())


@pytest.mark.parametrize(("unreadable", "line_number", "reason"), UNREADABLE)
def test_the_json_envelope_names_the_list_by_its_role(
    probe_data_dir: Path, tmp_path: Path, unreadable: str, line_number: int, reason: str
) -> None:
    write_list(probe_data_dir, unreadable)

    result = import_first_week(tmp_path, "--json")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert PROBE.casefold() not in (result.stdout + result.stderr).casefold()
    (line,) = [line for line in result.stdout.splitlines() if line.strip()]
    error = json.loads(line)["error"]
    assert error["code"] == "UNREADABLE_APPEND_ONLY_RECORD"
    assert error["message"] == f"{ROLE} line {line_number} is not readable: {reason}; nothing was changed"
    assert error["details"] == {"location": ROLE, "line_number": line_number}


def test_nothing_was_imported_and_the_list_is_as_it_was(probe_data_dir: Path, tmp_path: Path) -> None:
    torn = write_list(probe_data_dir, TORN_LIST)

    result = import_first_week(tmp_path)

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert torn.read_text(encoding="utf-8") == TORN_LIST
    assert not (probe_data_dir / "blobs").exists() and not (probe_data_dir / "objects").exists()
