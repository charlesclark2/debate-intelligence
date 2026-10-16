"""`debate-research caselist retire`, offline, on this machine: a dry run, a refusal, a retirement.

The data directory holds two version directories written here: one named for the parser version the
installed build reports, which is current, and an older one, which is superseded. Nothing reaches a
bucket. What it checks is the path an operator takes (`docs/runbooks/parsed-store-retention.md`):
the dry run's listing and code, the refusal of the current directory, and `--execute --confirm`
deleting the superseded directory and nothing else (`v1-e31-t16`).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Final

import pytest
from tests.smoke.installed_build import CliRun, InstalledCli

from debate_cli.exit_codes import ExitCode

CASELIST: Final = "testcl26"
OLDER: Final = "2026.01.01-docx-0"


@pytest.fixture
def installation(installed_cli: InstalledCli, tmp_path: Path) -> Iterator[Path]:
    """A data directory and a dev profile of this check's own, for the build under test."""
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "dev.toml").write_text(
        f'[storage]\ndata_dir = "{tmp_path / "data"}"\n'
        f'[models]\nrouting_file = "{tmp_path / "routing.yaml"}"\nbudget_usd_daily = 1.0\n',
        encoding="utf-8",
    )
    installed_cli.configure(DEBATE_PROFILE_DIR=str(profiles), DEBATE_ENV="dev", DEBATE_STORAGE__DATA_DIR=None)
    yield tmp_path / "data"


def envelope(result: CliRun) -> dict[str, Any]:
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, f"expected one line of JSON on stdout; got {lines!r}\n{result.stderr}"
    parsed = json.loads(lines[0])
    assert isinstance(parsed, dict)
    return parsed


def write_directory(data_dir: Path, version: str) -> None:
    path = data_dir / "parsed" / CASELIST / version / "index.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}\n", encoding="utf-8")


def test_a_superseded_directory_is_listed_refused_when_current_and_retired_with_its_code(
    installed_cli: InstalledCli, installation: Path
) -> None:
    write_directory(installation, OLDER)
    current = envelope(installed_cli.run("--json", "caselist", "retire"))["data"]["parser_version"]
    write_directory(installation, current)

    listed = envelope(installed_cli.run("--json", "caselist", "retire", "--version", OLDER))["data"]
    refused = installed_cli.run("--json", "caselist", "retire", "--version", current)
    retired = installed_cli.run(
        "--json", "caselist", "retire", "--version", OLDER, "--execute", "--confirm", listed["confirmation"]
    )

    assert [(row["version"], row["standing"]) for row in listed["directories"]] == [
        (OLDER, "superseded"),
        (current, "current"),
    ]
    assert refused.exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope(refused)["error"]["code"] == "CURRENT_VERSION_DIRECTORY"
    assert retired.exit_code == ExitCode.OK, retired.stdout
    assert sorted(path.name for path in (installation / "parsed" / CASELIST).iterdir()) == [current]
