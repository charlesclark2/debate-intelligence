"""The installed `debate-research verify`, run as a process against a fixture data directory.

Nothing here goes through Typer's test runner: the console script the workspace installs is started
with `subprocess`, in the `test` environment, with `DEBATE_STORAGE__DATA_DIR` pointing at a data
directory the real local adapters wrote (`tests/fixtures/verify/manifest_world.py`). It is the
closest a test gets to a student typing the command, and it is how this task's plan asks for the
end-to-end check ("run the installed command against it").

Expected verdicts are written by hand from the fixture text. The tampered card changes "had" to
"has" in "Nobody in the basin had planned for it.", at offset 22 of the card's evidence.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.verify.manifest_world import ALL_VERIFIED, MIXED, TAMPERED, build_fixture_data_dir
from tests.fixtures.verify.published_schemas import RESULT_SCHEMA, violations

COMMAND = Path(sys.executable).parent / "debate-research"


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("verify-e2e") / "data"
    build_fixture_data_dir(directory)
    return directory


def run_verify(*arguments: str, data_dir: Path) -> subprocess.CompletedProcess[str]:
    environment = {name: value for name, value in os.environ.items() if not name.startswith("DEBATE_")}
    environment |= {"DEBATE_ENV": "test", "DEBATE_STORAGE__DATA_DIR": str(data_dir), "NO_COLOR": "1"}
    return subprocess.run(
        [str(COMMAND), *arguments], capture_output=True, text=True, env=environment, check=False, timeout=60
    )


def envelope(completed: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    document: dict[str, Any] = json.loads(completed.stdout)
    assert violations(RESULT_SCHEMA, document) == []
    return document


def test_the_command_is_installed() -> None:
    assert COMMAND.is_file(), f"no console script at {COMMAND}; run `uv sync --all-packages`"


def test_a_verified_only_manifest_exits_zero(data_dir: Path) -> None:
    completed = run_verify("--json", "verify", str(ALL_VERIFIED), data_dir=data_dir)

    assert completed.returncode == 0, completed.stderr
    report = envelope(completed)["data"]
    assert [card["status"] for card in report["cards"]] == ["VERIFIED", "VERIFIED", "VERIFIED"]


def test_two_verified_and_one_tampered_card_print_three_rows_with_reasons_and_exit_one(
    data_dir: Path,
) -> None:
    completed = run_verify("verify", str(TAMPERED), data_dir=data_dir)

    assert completed.returncode == 1, completed.stderr
    rows = [line for line in completed.stdout.splitlines() if line.startswith("│ 0CARD")]
    assert len(rows) == 3, completed.stdout
    assert ["UNVERIFIED" in row for row in rows] == [False, False, True]
    assert "TEXT_MISMATCH at" in rows[2]
    assert "offset 22" in completed.stdout


def test_the_mixed_manifest_reports_each_card_with_its_reason(data_dir: Path) -> None:
    completed = run_verify("--json", "verify", str(MIXED), data_dir=data_dir)

    assert completed.returncode == 1, completed.stderr
    cards = envelope(completed)["error"]["details"]["cards"]
    assert [(card["status"], card["reason_codes"]) for card in cards] == [
        ("VERIFIED", []),
        ("VERIFIED", []),
        ("UNVERIFIED", ["TEXT_MISMATCH"]),
        ("UNVERIFIED", ["CARD_INVALID"]),
        ("UNVERIFIED", ["SNAPSHOT_MISSING"]),
    ]


def test_a_data_directory_without_the_snapshots_verifies_nothing(tmp_path: Path) -> None:
    """The forbidden case: a card whose snapshot is missing locally is never VERIFIED."""
    completed = run_verify("--json", "verify", str(ALL_VERIFIED), data_dir=tmp_path / "empty")

    assert completed.returncode == 1, completed.stderr
    cards = envelope(completed)["error"]["details"]["cards"]
    assert [(card["status"], card["reason_codes"]) for card in cards] == [
        ("UNVERIFIED", ["SNAPSHOT_MISSING"]),
        ("UNVERIFIED", ["SNAPSHOT_MISSING"]),
        ("UNVERIFIED", ["SNAPSHOT_MISSING"]),
    ]


def test_a_manifest_that_fails_its_schema_exits_two_with_the_path(data_dir: Path, tmp_path: Path) -> None:
    document = json.loads(ALL_VERIFIED.read_bytes())
    document["cards"][2]["omitted_ranges"] = [{"start_offset": 60}]
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(document), encoding="utf-8")

    completed = run_verify("--json", "verify", str(manifest), data_dir=data_dir)

    assert completed.returncode == 2, completed.stderr
    details = envelope(completed)["error"]["details"]
    assert (details["json_path"], details["problem"]) == (
        "$.cards[2].omitted_ranges[0]",
        "missing required 'end_offset'",
    )
