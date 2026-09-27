"""`debate-research caselist cards` end to end, offline, as `validate-dev` runs it (`v1-e31-t04`).

The three synthetic weekly archives from `tests/fixtures/caselist/` are imported with the real
`caselist import` into a fresh installation, which records their disclosures. Then `caselist cards`
reads `tests/fixtures/fingerprints/parsed_cards_testcl26.jsonl` — four invented cards whose source
hashes are those archives' own files — and its counts are checked against the numbers below, worked
out by hand from the archive table in `build_synthetic_archives.py`:

* `grove-round-1-aff` carries the heat card. It is disclosed by Maple Grove QX in Round 1 in all
  three weeks, again as a `(1)` re-upload in weeks two and three (the same round, so the same
  occurrence), and by Cedar Hollow ZaLu in Round 3 from week two.
* `harbor-aff` (Cedar Hollow ZaLu, all three weeks) carries a copy of the heat card cut two
  sentences shorter.
* `ridgeline-doubles-aff` (Northgate Prep BeCo, from week two) carries an ABBREVIATED heat card.
* `bayview-semis-neg` (Maple Grove QX, week three) carries a different card.

So the heat cluster is read by 3 teams (QX, ZaLu, BeCo) in 4 occurrences across 3 files, the other
cluster by 1 team; 4 card positions, 4 exact bodies, 2 clusters, a duplicate rate of 0.5.

Unmarked, like the other offline caselist smoke checks: nothing here needs a deployed environment
(`tests/smoke/README.md`). Every school, team code and card is invented, and the one cutter mark in
the fixture is the synthetic `zzTEST`, which must never appear in the output.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from tests.fixtures.caselist.build_synthetic_archives import (
    DOCUMENT_BODIES,
    SNAPSHOTS,
    SYNTHETIC_CASELIST,
    build_snapshot_zips,
)
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode

runner = CliRunner()

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "fingerprints" / "parsed_cards_testcl26.jsonl"


@pytest.fixture
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


@pytest.fixture
def imported(installation: Path) -> Path:
    """The three synthetic weeks imported, and a parsed directory holding the fixture."""
    zips = build_snapshot_zips(installation / "archives")
    for week in SNAPSHOTS:
        result = invoke(
            "caselist",
            "import",
            str(zips[week.snapshot]),
            "--caselist",
            SYNTHETIC_CASELIST,
            "--snapshot",
            week.snapshot.isoformat(),
        )
        assert result.exit_code == ExitCode.OK, result.output
    parsed = installation / "parsed"
    parsed.mkdir()
    (parsed / FIXTURE.name).write_bytes(FIXTURE.read_bytes())
    return parsed


def invoke(*arguments: str) -> Result:
    return runner.invoke(create_app(), list(arguments))


def test_fixture_cards_come_from_the_synthetic_archives_files() -> None:
    """The fixture's source hashes are the archives' own bytes; this fails if either drifts."""
    archive_hashes = {hashlib.sha256(body).hexdigest() for body in DOCUMENT_BODIES.values()}
    rows = [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 4
    assert {row["provenance"]["source_sha256"] for row in rows} <= archive_hashes


def test_caselist_cards_counts_the_synthetic_caselist(imported: Path) -> None:
    result = invoke(
        "--json", "caselist", "cards", "--caselist", SYNTHETIC_CASELIST, "--parsed", str(imported)
    )

    assert result.exit_code == ExitCode.OK, result.output
    data = json.loads(result.stdout)["data"]
    assert data["fingerprint_version"] == "card-fingerprint-v1"
    assert data["totals"] == {
        "parsed_cards": 4,
        "cards": 4,
        "occurrences": 5,
        "exact_unique": 4,
        "clusters": 2,
        "duplicate_rate": 0.5,
        "teams": 3,
        "linked_abbreviated": 1,
        "unlinked_abbreviated": 0,
    }
    heat, warehouse = data["top_clusters"]
    assert (heat["short_cite"], heat["distinct_teams"], heat["occurrences"], heat["files"]) == (
        "Pellam 26",
        3,
        4,
        3,
    )
    assert (warehouse["short_cite"], warehouse["distinct_teams"], warehouse["files"]) == ("Thorne 26", 1, 1)
    assert "teams" not in heat
    for identity in ("QX", "ZaLu", "BeCo", "Maple Grove", "zzTEST"):
        assert identity not in result.stdout


def test_caselist_cards_as_of_the_first_week(imported: Path) -> None:
    result = invoke(
        "--json",
        "caselist",
        "cards",
        "--caselist",
        SYNTHETIC_CASELIST,
        "--parsed",
        str(imported),
        "--snapshot",
        "2026-09-01",
        "--top",
        "5",
    )

    assert result.exit_code == ExitCode.OK, result.output
    data = json.loads(result.stdout)["data"]
    # Week one: the Round 1 file (QX only; ZaLu disclosed it from week two) and the Harbor file.
    assert (data["totals"]["cards"], data["totals"]["clusters"], data["totals"]["occurrences"]) == (2, 1, 2)
    assert data["totals"]["teams"] == 2


def test_caselist_cards_by_team_and_table(imported: Path) -> None:
    by_team = invoke(
        "--json",
        "caselist",
        "cards",
        "--caselist",
        SYNTHETIC_CASELIST,
        "--parsed",
        str(imported),
        "--by-team",
    )
    assert by_team.exit_code == ExitCode.OK, by_team.output
    heat = json.loads(by_team.stdout)["data"]["top_clusters"][0]
    assert heat["teams"] == [
        {"school": "Cedar Hollow", "team_code": "ZaLu"},
        {"school": "Maple Grove", "team_code": "QX"},
        {"school": "Northgate Prep", "team_code": "BeCo"},
    ]
    assert "zzTEST" not in by_team.stdout

    table = invoke("caselist", "cards", "--caselist", SYNTHETIC_CASELIST, "--parsed", str(imported))
    assert table.exit_code == ExitCode.OK, table.output
    assert "Pellam 26" in table.output
    assert "zzTEST" not in table.output
