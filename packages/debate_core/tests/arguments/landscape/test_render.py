"""The landscape report's files against hand-written golden files (`v1-e32-t03` ac1, ac2, ac4).

`tests/fixtures/landscape/golden/` was written by hand from the synthetic caselist's table, never by
running the renderer (working agreement 6). The scan reads every school, team code and tournament
the fixture's disclosures name, and the paths they were filed under, and finds none in the output.
"""

from __future__ import annotations

import csv
import dataclasses
import random
import re
from datetime import date
from pathlib import Path

import pytest

from debate_core.application.landscape_report import LandscapeReportBundle, LandscapeReportService
from debate_core.application.landscape_staleness import STALE_BANNER_HEADING
from debate_core.arguments.landscape.render import (
    POSITION_COLUMNS,
    TOP_CARD_COLUMNS,
    header_metadata,
    render_markdown,
    render_top_cards_csv,
)
from debate_core.domain.landscape_report import LandscapeReport, TopCard
from debate_core.testing.landscape_report import (
    SYNTHETIC_REPORT_DATE,
    read_synthetic_caselist,
    synthetic_staleness,
)

REPO = Path(__file__).resolve().parents[5]
FIXTURE = REPO / "tests" / "fixtures" / "landscape" / "synthetic_caselist"
GOLDEN = REPO / "tests" / "fixtures" / "landscape" / "golden"
FILES = ("report.md", "positions.csv", "top_cards.csv")


def _bundle(
    *, report_date: date = SYNTHETIC_REPORT_DATE, archives_awaiting_download: int = 0
) -> LandscapeReportBundle:
    staleness = synthetic_staleness(
        report_date=report_date, archives_awaiting_download=archives_awaiting_download
    )
    return LandscapeReportService().bundle(read_synthetic_caselist(FIXTURE), staleness)


@pytest.mark.parametrize("name", FILES)
def test_rendering_the_fixture_matches_the_golden_file(name: str) -> None:
    assert _bundle().files[name] == (GOLDEN / name).read_text(encoding="utf-8")


def test_rendering_the_same_inputs_twice_in_any_order_is_byte_identical() -> None:
    first = _bundle().files
    inputs = read_synthetic_caselist(FIXTURE)
    shuffler = random.Random(20261023)
    for _ in range(3):
        shuffled = dataclasses.replace(
            inputs,
            classifications=tuple(shuffler.sample(list(inputs.classifications), len(inputs.classifications))),
            disclosures=tuple(shuffler.sample(list(inputs.disclosures), len(inputs.disclosures))),
            cards=tuple(shuffler.sample(list(inputs.cards), len(inputs.cards))),
        )
        assert LandscapeReportService().bundle(shuffled, synthetic_staleness()).files == first


def test_a_scan_of_the_output_finds_no_team_code_school_tournament_or_path_from_the_disclosures() -> None:
    disclosures = read_synthetic_caselist(FIXTURE).disclosures
    codes = {one.team_code for one in disclosures}
    schools = {one.school for one in disclosures}
    names = schools | {one.tournament for one in disclosures if one.tournament}
    paths = {one.source_path for one in disclosures}
    assert len(codes) == 8
    for name, text in _bundle().files.items():
        found = {code for code in codes if re.search(rf"(?<![A-Za-z0-9]){code}(?![A-Za-z0-9])", text)}
        found |= {one for one in names | paths if one.casefold() in text.casefold()}
        found |= {one.split()[0] for one in schools if one.split()[0].casefold() in text.casefold()}
        assert not found, f"{name} names {sorted(found)}"


def test_the_scan_finds_a_team_code_planted_in_a_tag() -> None:
    planted = _with_tag(_bundle().report, "As XX said")
    assert re.search(r"(?<![A-Za-z0-9])XX(?![A-Za-z0-9])", render_top_cards_csv(planted, {}))


def test_the_csv_columns_are_the_specs() -> None:
    files = _bundle().files
    for name, columns in (("positions.csv", POSITION_COLUMNS), ("top_cards.csv", TOP_CARD_COLUMNS)):
        rows = list(csv.reader(line for line in files[name].splitlines() if not line.startswith("#")))
        assert tuple(rows[0]) == columns
    assert POSITION_COLUMNS == (
        "position_id",
        "label",
        "kind",
        "rounds",
        "teams",
        "aff_rounds",
        "neg_rounds",
        "first_seen_snapshot",
        "is_new",
        "share_of_teams",
    )
    assert {
        "teams_reading",
        "tag",
        "short_cite",
        "source_object_key",
        "element_index",
        "provenance_mode",
    } <= set(TOP_CARD_COLUMNS)


def test_a_stale_report_starts_with_the_banner_and_its_csvs_say_stale_true() -> None:
    files = _bundle(report_date=date(2026, 9, 25)).files
    assert files["report.md"].startswith(STALE_BANNER_HEADING)
    assert "2026-09-15, 10 day(s) before this report" in files["report.md"].splitlines()[0]
    assert "| Data freshness | Stale: the newest snapshot is 2026-09-15, 10 day(s) old" in files["report.md"]
    for name in ("positions.csv", "top_cards.csv"):
        assert "# stale=true\n" in files[name]
        assert "# snapshot_age_days=10\n" in files[name]


def test_a_cap_bound_run_makes_a_fresh_report_stale() -> None:
    files = _bundle(archives_awaiting_download=2).files
    assert files["report.md"].startswith(STALE_BANNER_HEADING)
    assert "# archives_awaiting_download=2\n" in files["positions.csv"]
    assert files["positions.csv"].count("# stale=true\n") == 1


def test_a_current_report_has_no_banner_and_says_stale_false() -> None:
    files = _bundle().files
    assert files["report.md"].startswith("# Argument landscape: synthpolicy26 through 2026-09-15\n")
    assert all("# stale=false\n" in files[name] for name in ("positions.csv", "top_cards.csv"))


def _with_tag(report: LandscapeReport, tag: str) -> LandscapeReport:
    first: TopCard = report.top_cards[0]
    return report.model_copy(
        update={"top_cards": (first.model_copy(update={"tag": tag}), *report.top_cards[1:])}
    )


def test_report_md_lists_no_card_and_points_to_top_cards_csv() -> None:
    files = _bundle().files
    report = _bundle().report
    for card in report.top_cards:
        assert card.source_object_key not in files["report.md"]
        assert card.tag is None or card.tag not in files["report.md"]
        assert card.source_object_key in files["top_cards.csv"]
    assert "most-read cards are in `top_cards.csv`" in files["report.md"]


def test_markdown_escapes_what_would_break_a_table_in_a_label() -> None:
    report = _bundle().report
    first = report.positions[0].model_copy(update={"label": "Single | payer *now*\nwith_plan"})
    row = next(
        line
        for line in render_markdown(
            report.model_copy(update={"positions": (first, *report.positions[1:])})
        ).splitlines()
        if "(`single-payer-aff`)" in line
    )
    assert row.startswith(r"| Single \| payer \*now\* with\_plan (`single-payer-aff`) |")
    assert row.count(" | ") == 7


def test_the_csv_keeps_a_tag_exact_and_writes_no_tag_as_empty() -> None:
    tag = "Costs | fall *fast*\nunder_plan [1] <b>"
    rows = list(
        csv.reader(render_top_cards_csv(_with_tag(_bundle().report, tag), {}).splitlines(keepends=True)[1:])
    )
    assert rows[1][TOP_CARD_COLUMNS.index("tag")] == tag
    report = _bundle().report
    untagged = report.top_cards[0].model_copy(update={"tag": None, "short_cite": None})
    blank = report.model_copy(update={"top_cards": (untagged, *report.top_cards[1:])})
    rows = list(csv.reader(render_top_cards_csv(blank, {}).splitlines()[1:]))
    assert (rows[1][TOP_CARD_COLUMNS.index("tag")], rows[1][TOP_CARD_COLUMNS.index("short_cite")]) == ("", "")


def test_markdown_counts_carry_thousands_separators_and_the_csv_does_not() -> None:
    report = _bundle().report
    large = report.model_copy(
        update={"header": report.header.model_copy(update={"cards": 126681, "cards_placed": 60987})}
    )
    assert "| Classification coverage | 60,987 of 126,681 cards (48.1%);" in render_markdown(large)
    assert "# coverage_cards=60987/126681\n" in render_top_cards_csv(large, header_metadata(large))
