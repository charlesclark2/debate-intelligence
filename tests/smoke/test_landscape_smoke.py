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

`debate-research landscape cassettes` (`v1-e32-t34`, its removal form `v1-e32-t36`) is checked at the
end, over the build's own scratch data directory: empty, and then with a cassette directory planted by
:class:`~debate_core.integrations.models.record_replay.CassetteDirectory` as the model stage files one,
under synthetic slugs, with invented prompt variables and answers. No model is called.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import BaseModel
from tests.fixtures.model_routing import EXAMPLE_ROUTING_FILE
from tests.smoke.installed_build import InstalledCli

from debate_cli.exit_codes import ExitCode
from debate_core.application.cassette_filing import filed_under
from debate_core.domain.model_contracts import ModelPrompt, ModelRequest, TaskClass
from debate_core.integrations.docx_parser import DebateDocxParser
from debate_core.integrations.models.record_replay import CassetteDirectory
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


def test_landscape_report_reads_a_restored_copy_and_writes_only_the_text_caches_on_a_dry_run(
    installed_cli: InstalledCli, world: SyntheticRun, tmp_path: Path
) -> None:
    """`v1-e40-t17`: the data directory stops at 2026-09-08; the copy, parsed by this build, at 09-15.

    Since `v1-e32-t30` a dry run keeps the plan-text and analytic-text caches, in the data directory, and
    writes nothing else here or in the copy.
    """
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
    assert not (copy / "landscape").exists()
    for directory in (world.data_dir, copy):
        assert not (directory / "reports").exists()
    kept = world.data_dir / "landscape"
    assert sorted(path.relative_to(kept).as_posix() for path in kept.rglob("*") if path.is_file()) == [
        "analytic_texts/synthetic26.jsonl",
        "plan_texts/synthetic26.jsonl",
    ]


# --- landscape cassettes (v1-e32-t34, v1-e32-t36) ---------------------------------------------

CASSETTE_CASELIST = "synthld21"
OTHER_CASELIST = "synthld26"
CASSETTE_CARD = "InventedCardText"
"""In every planted cassette's prompt variables: what printing a cassette's content would show."""


class SortedCard(BaseModel):
    position: str


def plant_cassette(data_dir: Path, card: str, *caselists: str) -> None:
    """The cassette of `card` in the model stage's directory, filed under each of `caselists` (or none)."""
    directory = CassetteDirectory(data_dir / "landscape" / "model-cassettes")
    prompt = ModelPrompt(
        prompt_id="example.sort-card", prompt_version="1.0.0", variables={"items": f"{CASSETTE_CARD} {card}"}
    )
    request = ModelRequest.build(TaskClass.HIGH_VOLUME, prompt, SortedCard)
    response = {"output": {"position": "invented"}, "model_id": "recorded-model"}
    if not caselists:
        directory.write_structured(request, response)
    for caselist in caselists:
        with filed_under(caselist):
            directory.write_structured(request, response)


@pytest.fixture
def planted_cassettes(installed_cli: InstalledCli) -> Path:
    """2 of the caselist's alone, 3 shared with another, 1 unattributed, 4 of the other alone."""
    data_dir = installed_cli.data_dir
    for card in ("one", "two"):
        plant_cassette(data_dir, card, CASSETTE_CASELIST)
    for card in ("three", "four", "five"):
        plant_cassette(data_dir, card, CASSETTE_CASELIST, OTHER_CASELIST)
    plant_cassette(data_dir, "six")
    for card in ("seven", "eight", "nine", "ten"):
        plant_cassette(data_dir, card, OTHER_CASELIST)
    return data_dir / "landscape" / "model-cassettes"


def files_under(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }


def test_landscape_cassettes_on_an_empty_data_directory_finds_none_and_creates_nothing(
    installed_cli: InstalledCli,
) -> None:
    before = sorted(installed_cli.data_dir.rglob("*")) if installed_cli.data_dir.exists() else None

    result = installed_cli.run("--json", "landscape", "cassettes", "--caselist", CASSETTE_CASELIST)

    assert result.exit_code == ExitCode.OK, result.output
    data = json.loads(result.stdout)["data"]
    assert (data["directory_found"], data["deleted"]) == (False, False)
    assert data["cassettes"] == {"sole": 0, "shared": 0, "unattributed": 0, "other_caselists": 0}
    after = sorted(installed_cli.data_dir.rglob("*")) if installed_cli.data_dir.exists() else None
    assert after == before


def test_landscape_cassettes_counts_a_planted_directory_and_changes_nothing(
    installed_cli: InstalledCli, planted_cassettes: Path
) -> None:
    before = files_under(planted_cassettes)

    result = installed_cli.run("--json", "landscape", "cassettes", "--caselist", CASSETTE_CASELIST)

    assert result.exit_code == ExitCode.OK, result.output
    data = json.loads(result.stdout)["data"]
    assert data["directory_found"] is True
    assert data["cassettes"] == {"sole": 2, "shared": 3, "unattributed": 1, "other_caselists": 4}
    assert files_under(planted_cassettes) == before
    assert CASSETTE_CARD not in result.output and str(installed_cli.data_dir) not in result.output


def test_landscape_cassettes_for_removal_deletes_every_copy_with_its_own_code(
    installed_cli: InstalledCli, planted_cassettes: Path
) -> None:
    base = ("--json", "landscape", "cassettes", "--caselist", CASSETTE_CASELIST)
    purge_code = json.loads(installed_cli.run(*base).stdout)["data"]["confirmation"]
    removal_code = json.loads(installed_cli.run(*base, "--for-removal").stdout)["data"]["confirmation"]
    before = files_under(planted_cassettes)

    refused = installed_cli.run(*base, "--for-removal", "--delete", "--confirm", purge_code)

    assert refused.exit_code == ExitCode.DOMAIN_FAILURE, refused.output
    assert json.loads(refused.stdout)["error"]["code"] == "CONFIRMATION_MISMATCH"
    assert files_under(planted_cassettes) == before

    done = installed_cli.run(*base, "--for-removal", "--delete", "--confirm", removal_code)

    assert done.exit_code == ExitCode.OK, done.output
    assert json.loads(done.stdout)["data"]["deleted"] is True
    assert len(files_under(planted_cassettes)) == 4
    again = json.loads(installed_cli.run(*base).stdout)["data"]["cassettes"]
    assert again == {"sole": 0, "shared": 0, "unattributed": 0, "other_caselists": 4}
