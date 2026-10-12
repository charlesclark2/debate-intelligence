"""`debate-research caselist parse`, offline: the structural fixtures into a fresh data directory.

The ten `v1-e31-t03` structural fixtures are filed as one fictional weekly archive, imported with
`caselist import` and parsed with `caselist parse`, both through the installed command, with two
workers in the process pool. Nothing is published. How many cards each fixture holds comes from its
`<name>.expected.json`, which was written by hand when the parser was built.

What it checks is the path an operator uses: the console script, the composition root, the
settings profile, the spawned workers, the real parser and the local store. Like the import smoke
check, it is offline and unmarked, because a check skipped in CI and before every promotion would
not check the command at all.
"""

from __future__ import annotations

import json
import zipfile
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from typing import Any, Final

import pytest
from tests.smoke.installed_build import CliRun, InstalledCli

from debate_cli.exit_codes import ExitCode

STRUCTURAL: Final = Path(__file__).resolve().parents[1] / "fixtures" / "debate_files" / "structural"
CASELIST: Final = "testcl26"
SNAPSHOT: Final = "2026-09-01"


def fixtures() -> list[Path]:
    return sorted(STRUCTURAL.glob("*.docx"))


def expected_cards() -> int:
    """The cards the hand-written expectations name, across every structural fixture."""
    return sum(
        len(json.loads(path.with_suffix(".expected.json").read_text(encoding="utf-8"))["cards"])
        for path in fixtures()
    )


@pytest.fixture
def installation(installed_cli: InstalledCli, tmp_path: Path) -> Iterator[Path]:
    """A data directory and a dev profile of this check's own, for the build under test."""
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "dev.toml").write_text(
        f'[storage]\ndata_dir = "{tmp_path / "data"}"\n'
        f'[models]\nrouting_file = "{tmp_path / "routing.yaml"}"\nbudget_usd_daily = 1.0\n'
        "[parse]\nworkers = 2\nfailure_rate_threshold = 0.0\n",
        encoding="utf-8",
    )
    installed_cli.configure(DEBATE_PROFILE_DIR=str(profiles), DEBATE_ENV="dev", DEBATE_STORAGE__DATA_DIR=None)
    yield tmp_path / "data"


@pytest.fixture
def imported(installed_cli: InstalledCli, installation: Path, tmp_path: Path) -> Path:
    """One weekly archive holding every structural fixture under an invented team's directory."""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for number, path in enumerate(fixtures(), start=1):
            member = (
                f"{CASELIST}-0901/Maple Grove/QX/Maple Grove-QX-Aff-Smoke Invitational-Round {number}.docx"
            )
            archive.writestr(member, path.read_bytes())
    zip_path = tmp_path / f"{CASELIST}-0901.zip"
    zip_path.write_bytes(buffer.getvalue())
    result = installed_cli.run(
        "--json", "caselist", "import", str(zip_path), "--caselist", CASELIST, "--snapshot", SNAPSHOT
    )
    assert result.exit_code == ExitCode.OK, result.output
    return installation


def reported(result: CliRun) -> dict[str, Any]:
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, f"expected one line of JSON on stdout; got {lines!r}\n{result.stderr}"
    envelope = json.loads(lines[0])
    assert result.exit_code == ExitCode.OK, envelope.get("error")
    data = envelope["data"]
    assert isinstance(data, dict)
    return data


def test_the_structural_fixtures_parse_into_the_store_and_a_second_run_parses_nothing(
    installed_cli: InstalledCli, imported: Path
) -> None:
    first = reported(installed_cli.run("--json", "caselist", "parse", "--caselist", CASELIST))

    assert (first["sources"], first["parsed"], first["cards"]) == (
        len(fixtures()),
        len(fixtures()),
        expected_cards(),
    )
    assert (first["failed"], first["unsupported"], first["workers"]) == ({}, {}, 2)
    assert first["store"]["cards"] == expected_cards()
    assert first["publish"] is None

    second = reported(installed_cli.run("--json", "caselist", "parse", "--caselist", CASELIST))
    assert (second["attempted"], second["skipped"]) == (0, len(fixtures()))


def test_the_store_is_laid_out_as_documented_and_holds_no_path(
    installed_cli: InstalledCli, imported: Path
) -> None:
    reported(installed_cli.run("--json", "caselist", "parse", "--caselist", CASELIST))

    version = (
        imported
        / "parsed"
        / CASELIST
        / reported(installed_cli.run("--json", "caselist", "parse", "--caselist", CASELIST, "--dry-run"))[
            "version"
        ]
    )
    assert {path.name for path in version.glob("*.jsonl")} == {
        "index.jsonl",
        "failures.jsonl",
        "occurrences.jsonl",
    }
    assert len(list((version / "sha256").rglob("*.jsonl"))) == len(fixtures())
    written = "".join(path.read_text(encoding="utf-8") for path in version.rglob("*.jsonl"))
    for fragment in ("Maple Grove", "QX", "Smoke Invitational", "source_path"):
        assert fragment not in written


def test_failures_with_nothing_failed_lists_nothing(installed_cli: InstalledCli, imported: Path) -> None:
    reported(installed_cli.run("--json", "caselist", "parse", "--caselist", CASELIST))

    listed = reported(installed_cli.run("--json", "caselist", "parse", "--caselist", CASELIST, "--failures"))

    assert (listed["present"], listed["failures"], listed["contains_disclosure_paths"]) == (True, [], True)
