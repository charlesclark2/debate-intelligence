"""`debate-research caselist cards`, through the real application and composition root.

Disclosures are written into the installation's own SQLite file with the real repository, parsed
cards into a directory of JSONL, and the command is run with `CliRunner`. Every school, team code,
author and card is invented; the only cutter mark is the synthetic `zzTEST`, and the tests check
it is never printed.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode
from debate_core.domain.caselist import Disclosure, Event, RoundLabel, Side, SourceOrigin
from debate_core.domain.debate_files import CardCompleteness, FileImportProvenance, ParsedCard
from debate_core.domain.style_profile import StyleMatchSource
from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository
from debate_core.integrations.local.sqlite_db import SqliteDatabase

runner = CliRunner()

CASELIST = "testcl26"
WEEK_ONE, WEEK_TWO = date(2026, 9, 1), date(2026, 9, 8)
FILE_A, FILE_B, FILE_C = "a" * 64, "b" * 64, "c" * 64

HEAT = (
    "Cities that pave over their green space do not merely lose shade; they lose the evening. The "
    "Varrow Commission's survey of forty mid-sized municipalities found that asphalt and roofing "
    "retain the afternoon's heat well past midnight, so that neighbourhoods with the least canopy "
    "cool the least overnight."
)
WAREHOUSE = (
    "Automation rarely eliminates a job outright; it removes the tasks within a job that were "
    "easiest to measure, and managers raised the number of orders each picker had to fill."
)


@pytest.fixture(autouse=True)
def installation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
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
    yield tmp_path


def card(
    source: str, body: str, short_cite: str, *, snapshot: date = WEEK_ONE, cite_tail: str = ""
) -> ParsedCard:
    return ParsedCard(
        tag=f"Invented tag for {short_cite}",
        short_cite=short_cite,
        full_cite=f"{short_cite} (Invented Author, Fictional Journal, 2026){cite_tail}",
        evidence_text=body,
        completeness=CardCompleteness.FULL,
        match_source=StyleMatchSource.VERBATIM,
        confidence=1.0,
        provenance=FileImportProvenance(
            source_sha256=source,
            source_path=f"synthetic/{source[:4]}.docx",
            origin=SourceOrigin.CASELIST_ARCHIVE,
            caselist=CASELIST,
            snapshot=snapshot,
            first_element_index=2,
            last_element_index=3,
            parser_version="test-parser",
            profile_version="test-profile",
        ),
    )


def disclosure(source: str, snapshot: date, school: str, team_code: str) -> Disclosure:
    return Disclosure(
        source_sha256=source,
        caselist=CASELIST,
        snapshot=snapshot,
        event=Event.LD,
        school=school,
        team_code=team_code,
        side=Side.AFF,
        tournament="Invented Invitational",
        round_label=RoundLabel.from_raw("Round 1"),
        source_path=f"{school}/{team_code}/{school}-{team_code}-Aff-Invented Invitational-Round 1.docx",
    )


@pytest.fixture
def parsed(installation: Path) -> Path:
    """Two teams read the heat card (one file each, the second in two snapshots); one reads another."""
    directory = installation / "parsed"
    directory.mkdir()
    cards = [
        card(FILE_A, HEAT, "Pellam 26", cite_tail=" //zzTEST"),
        card(FILE_B, HEAT.replace("'", "’"), "Pellam 26", snapshot=WEEK_ONE),
        card(FILE_B, HEAT.replace("'", "’"), "Pellam 26", snapshot=WEEK_TWO),
        card(FILE_C, WAREHOUSE, "Thorne 26", snapshot=WEEK_TWO),
    ]
    (directory / "cards.jsonl").write_text(
        "".join(item.model_dump_json() + "\n" for item in cards), encoding="utf-8"
    )
    disclosures = [
        disclosure(FILE_A, WEEK_ONE, "Maple Grove", "QX"),
        disclosure(FILE_A, WEEK_TWO, "Maple Grove", "QX"),
        disclosure(FILE_B, WEEK_ONE, "Cedar Hollow", "ZaLu"),
        disclosure(FILE_B, WEEK_TWO, "Cedar Hollow", "ZaLu"),
        disclosure(FILE_C, WEEK_TWO, "Cedar Hollow", "ZaLu"),
    ]
    database = SqliteDatabase.open(installation / "data")
    repository = SqliteCaselistRepository(database)

    async def record() -> None:
        for item in disclosures:
            await repository.record_disclosure(item)

    asyncio.run(record())
    database.close()
    return directory


def invoke(*arguments: str) -> Result:
    return runner.invoke(create_app(), list(arguments))


def test_cards_prints_totals_and_the_top_clusters(parsed: Path) -> None:
    result = invoke("caselist", "cards", "--caselist", CASELIST, "--parsed", str(parsed))

    assert result.exit_code == ExitCode.OK, result.output
    # Positions A2, B2, C2 = 3 cards; heat (A, B) and warehouse = 2 clusters; 1 - 2/3 = 33.3%.
    assert "3 cards" in result.output
    assert "2 clusters" in result.output
    assert "33.3%" in result.output
    assert "Pellam 26" in result.output and "Thorne 26" in result.output
    assert "QX" not in result.output and "ZaLu" not in result.output and "Maple Grove" not in result.output
    assert "zzTEST" not in result.output


def test_cards_json_carries_counts_and_no_identities(parsed: Path) -> None:
    for arguments in (
        ("caselist", "cards", "--caselist", CASELIST, "--parsed", str(parsed), "--json"),
        ("--json", "caselist", "cards", "--caselist", CASELIST, "--parsed", str(parsed)),
    ):
        result = invoke(*arguments)
        assert result.exit_code == ExitCode.OK, result.output
        envelope = json.loads(result.stdout)
        data = envelope["data"]
        assert data["totals"] == {
            "parsed_cards": 4,
            "cards": 3,
            "occurrences": 3,
            "exact_unique": 2,
            "clusters": 2,
            "duplicate_rate": 0.3333,
            "teams": 2,
            "linked_abbreviated": 0,
            "unlinked_abbreviated": 0,
        }
        heat, warehouse = data["top_clusters"]
        assert (heat["short_cite"], heat["distinct_teams"], heat["occurrences"], heat["files"]) == (
            "Pellam 26",
            2,
            2,
            2,
        )
        assert (warehouse["short_cite"], warehouse["distinct_teams"]) == ("Thorne 26", 1)
        assert "teams" not in heat
        assert "QX" not in result.stdout and "zzTEST" not in result.stdout


def test_cards_by_team_shows_school_and_team_code_only(parsed: Path) -> None:
    result = invoke(
        "--json",
        "caselist",
        "cards",
        "--caselist",
        CASELIST,
        "--parsed",
        str(parsed),
        "--by-team",
        "--top",
        "1",
    )

    assert result.exit_code == ExitCode.OK, result.output
    (heat,) = json.loads(result.stdout)["data"]["top_clusters"]
    assert heat["teams"] == [
        {"school": "Cedar Hollow", "team_code": "ZaLu"},
        {"school": "Maple Grove", "team_code": "QX"},
    ]
    assert "zzTEST" not in result.stdout

    # Wide enough that Rich does not wrap a school name across two lines of its cell.
    table = runner.invoke(
        create_app(),
        ["caselist", "cards", "--caselist", CASELIST, "--parsed", str(parsed), "--by-team"],
        env={"COLUMNS": "240"},
    )
    assert "Cedar Hollow ZaLu, Maple Grove QX" in table.output
    assert "zzTEST" not in table.output


def test_cards_snapshot_reports_what_was_known_then(parsed: Path) -> None:
    result = invoke(
        "--json",
        "caselist",
        "cards",
        "--caselist",
        CASELIST,
        "--parsed",
        str(parsed),
        "--snapshot",
        "2026-09-01",
    )

    assert result.exit_code == ExitCode.OK, result.output
    data = json.loads(result.stdout)["data"]
    assert data["snapshot"] == "2026-09-01"
    # Week one: the heat card in files A and B only.
    assert (data["totals"]["cards"], data["totals"]["clusters"]) == (2, 1)


def test_cards_refuses_a_malformed_snapshot(parsed: Path) -> None:
    result = invoke(
        "caselist", "cards", "--caselist", CASELIST, "--parsed", str(parsed), "--snapshot", "Sept 1"
    )
    assert result.exit_code != ExitCode.OK
    assert "--snapshot" in result.output


def test_cards_reports_an_unreadable_file_by_name_and_line(parsed: Path) -> None:
    (parsed / "zz-broken.jsonl").write_text('{"tag": "only a tag"}\n', encoding="utf-8")
    result = invoke("--json", "caselist", "cards", "--caselist", CASELIST, "--parsed", str(parsed))

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    message = json.loads(result.stdout)["error"]["message"]
    assert "zz-broken.jsonl line 1" in message
    assert "only a tag" not in message
