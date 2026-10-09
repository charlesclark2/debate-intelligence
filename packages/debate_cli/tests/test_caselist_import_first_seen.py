"""`caselist import` reports first-seen beside NEW, as an operator reads it (`v1-e30-t08`, ac3).

The same three consecutive synthetic weeks as
`packages/debate_core/tests/application/caselist/test_new_count_and_first_seen.py`, imported through
the real command and composition root: 25 NEW against 16 first seen, the backfill's shape. Filenames
carry no school, team code or name; the bodies are filler. Counts written by hand from `WEEKS`.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode

runner = CliRunner()

EARLY = [f"early-{number:02d}.docx" for number in range(1, 10)]
MIDDLE = [f"middle-{number:02d}.docx" for number in range(1, 4)]
LATE = [f"late-{number:02d}.docx" for number in range(1, 5)]
WEEKS: dict[date, list[str]] = {
    date(2026, 8, 11): EARLY,
    date(2026, 8, 18): MIDDLE,
    date(2026, 8, 25): [*LATE, *EARLY, MIDDLE[0]],
}


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "dev.toml").write_text(
        f'[storage]\ndata_dir = "{tmp_path / "data"}"\n'
        f'[models]\nrouting_file = "{tmp_path / "routing.yaml"}"\nbudget_usd_daily = 1.0\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("DEBATE_PROFILE_DIR", str(profiles))
    monkeypatch.setenv("DEBATE_ENV", "dev")
    yield profiles


def import_weeks(tmp_path: Path) -> list[dict[str, Any]]:
    """Import the three weeks in order, each a directory of its files; the `--json` data of each."""
    reported: list[dict[str, Any]] = []
    for snapshot, names in WEEKS.items():
        week = tmp_path / "downloads" / snapshot.isoformat()
        week.mkdir(parents=True)
        for name in names:
            (week / name).write_bytes(f"filler for {name}".encode())
        result = runner.invoke(
            create_app(),
            [
                "--json",
                "caselist",
                "import",
                str(week),
                "--caselist",
                "testcl26",
                "--snapshot",
                snapshot.isoformat(),
            ],
        )
        assert result.exit_code == ExitCode.OK, result.stdout
        reported.append(json.loads(result.stdout)["data"])
    return reported


def test_first_seen_is_reported_beside_new_and_they_differ_where_the_backfill_measured(
    tmp_path: Path,
) -> None:
    reported = import_weeks(tmp_path)

    assert [week["counts"]["NEW"] for week in reported] == [9, 3, 13]
    assert [week.get("first_seen") for week in reported] == [9, 3, 4]


def test_the_manifest_summary_carries_first_seen_beside_new(tmp_path: Path) -> None:
    import_weeks(tmp_path)

    manifest = tmp_path / "data" / "objects" / "manifests" / "testcl26" / "2026-08-25.jsonl"
    summary = json.loads(manifest.read_text(encoding="utf-8").splitlines()[-1])

    assert (summary["classifications"]["NEW"], summary.get("first_seen")) == (13, 4)


def test_the_new_count_caption_says_what_new_is_measured_against(tmp_path: Path) -> None:
    import_weeks(tmp_path)
    week = tmp_path / "downloads" / "2026-08-25"

    result = runner.invoke(
        create_app(), ["caselist", "import", str(week), "--caselist", "testcl26", "--snapshot", "2026-08-25"]
    )

    caption = " ".join(result.stdout.split())
    assert "NEW: not present in the 2026-08-18 snapshot" in caption
    assert "4 first seen in testcl26" in caption
