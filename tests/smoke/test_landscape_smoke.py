"""`debate-research landscape report` end to end, offline, as `validate-dev` runs it (`v1-e32-t05` ac4).

`synthetic26` (:mod:`debate_core.testing.landscape_run`) is planted into a fresh installation's data
directory with its own `config/landscape/`: two weekly manifests, four parsed sources by three
invented teams, and their occurrence table. The installed build then writes the report with
`--model-mode none` (the PM's amendment of 2026-10-22: no model, no Bedrock) and `--no-publish`, so
it needs no bucket and no stand-in. The counts below are the fixture table's, worked out by hand in
that module's docstring: nine cards, seven under a heading an alias names. The bundle is seven files,
five circuit-wide and two school view, and the command marks each (`v1-e32-t12`); the trend and
school-view counts are worked out by hand in `packages/debate_cli/tests/test_landscape_command.py`.

Unmarked, like the other offline caselist smoke checks. Every school, team code and card is
invented, and none of them may appear in what the command prints.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from tests.fixtures.model_routing import EXAMPLE_ROUTING_FILE
from tests.smoke.installed_build import InstalledCli

from debate_cli.exit_codes import ExitCode
from debate_core.integrations.docx_parser import DebateDocxParser
from debate_core.testing.landscape_run import SyntheticRun, plant_synthetic_run
from debate_core.testing.landscape_store import PARSER_VERSION

BUNDLE = (
    ("positions.csv", "circuit_wide"),
    ("top_cards.csv", "circuit_wide"),
    ("impact_cards.csv", "circuit_wide"),
    ("trends.csv", "circuit_wide"),
    ("schools.csv", "school_view"),
    ("schools.md", "school_view"),
    ("report.md", "circuit_wide"),
)


@pytest.fixture
def world(installed_cli: InstalledCli, tmp_path: Path) -> Iterator[SyntheticRun]:
    """`synthetic26` planted, and a dev profile of this check's own naming its data directory."""
    planted = plant_synthetic_run(tmp_path / "world")
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "dev.toml").write_text(
        f'[storage]\ndata_dir = "{planted.data_dir}"\n'
        f'[models]\nrouting_file = "{EXAMPLE_ROUTING_FILE}"\nbudget_usd_daily = 1.0\n',
        encoding="utf-8",
    )
    installed_cli.configure(DEBATE_PROFILE_DIR=str(profiles), DEBATE_ENV="dev", DEBATE_STORAGE__DATA_DIR=None)
    yield planted


def test_landscape_report_writes_the_bundle_offline_with_no_model(
    installed_cli: InstalledCli, world: SyntheticRun
) -> None:
    result = installed_cli.run(
        "--json",
        "landscape",
        "report",
        "--caselist",
        "synthetic26",
        "--no-publish",
        "--model-mode",
        "none",
        "--config-dir",
        str(world.config_dir),
    )

    assert result.exit_code == ExitCode.OK, result.output
    data = json.loads(result.stdout)["data"]
    directory = world.data_dir / "reports" / "landscape" / "synthetic26" / "2026-09-15"
    assert data["paths"]["directory"] == str(directory)
    assert data["bundle"] == [
        {"name": name, "path": str(directory / name), "view": view} for name, view in BUNDLE
    ]
    for name, _ in BUNDLE:
        assert (directory / name).is_file()
        assert (directory / name).stat().st_size > 0
    assert (data["model_mode"], data["model_calls"], data["publish"]) == ("none", 0, None)
    assert data["classification"]["cards_by_method"] == {"ALIAS": 7, "UNPLACED": 2}
    assert (data["counts"]["cards"], data["counts"]["positions"]) == (9, 4)
    assert data["trends"] == {
        "rows_by_label": {"NEW": 0, "RISING": 0, "FALLING": 0, "STEADY": 4},
        "held_back_by_team_floor": 1,
    }
    assert data["school_view"] == {"schools": 3, "team_codes": 3, "rows": 7}
    assert data["staleness"]["failed_run"] is None
    assert data["scan"]["hits"] == []
    for identity in ("Quillmere", "Brindle", "Harrowgate", "Lantern Classic", "Thistle Open", '"QW"', '"PX"'):
        assert identity not in result.stdout


def test_landscape_report_refuses_an_unknown_caselist_with_exit_2(
    installed_cli: InstalledCli, world: SyntheticRun
) -> None:
    result = installed_cli.run(
        "--json", "landscape", "report", "--caselist", "hsnope26", "--config-dir", str(world.config_dir)
    )

    assert result.exit_code == ExitCode.USAGE_ERROR, result.output
    assert json.loads(result.stdout)["error"]["details"]["known"] == ["synthetic26"]
    assert not (world.data_dir / "reports").exists()


def test_landscape_report_reads_a_restored_copy_and_writes_nothing_on_a_dry_run(
    installed_cli: InstalledCli, world: SyntheticRun, tmp_path: Path
) -> None:
    """`v1-e40-t17`: the data directory stops at 2026-09-08; the copy, parsed by this build, at 09-15."""
    (world.data_dir / "objects" / "manifests" / "synthetic26" / "2026-09-15.jsonl").unlink()
    copy = plant_synthetic_run(tmp_path / "copy-root").data_dir.resolve()
    parsed = copy / "parsed" / "synthetic26"
    (parsed / PARSER_VERSION).rename(parsed / DebateDocxParser().parser_version)

    result = installed_cli.run(
        "--json",
        "landscape",
        "report",
        "--caselist",
        "synthetic26",
        "--dry-run",
        "--restored-copy",
        str(copy),
        "--config-dir",
        str(world.config_dir),
    )

    assert result.exit_code == ExitCode.OK, result.output
    data = json.loads(result.stdout)["data"]
    assert (data["snapshot"], data["restored_copy"], data["written"]) == ("2026-09-15", str(copy), False)
    assert data["classification"]["model"]["would_ask"] == 0
    assert data["counts"]["cards"] == 9
    for directory in (world.data_dir, copy):
        assert not (directory / "landscape").exists()
        assert not (directory / "reports").exists()
