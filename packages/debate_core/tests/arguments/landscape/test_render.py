"""The landscape report's files against hand-written golden files (`v1-e32-t03`, `v1-e32-t10`, `v1-e32-t04`).

`tests/fixtures/landscape/golden/` was written by hand from the synthetic caselist's table, never by
running the renderer (working agreement 6), and so was the third window's `expected_trends.csv`. The
scan reads every school, team code and tournament the fixture's disclosures name, and the paths they
were filed under, and finds none in the circuit-wide files; the school view names schools and team
codes and nothing more, but the link to each team's openCaselist page (`v1-e32-t18`), which no
circuit-wide file carries.
"""

from __future__ import annotations

import csv
import dataclasses
import random
import re
from datetime import date
from pathlib import Path

import pytest

from debate_core.application.landscape_report import (
    CIRCUIT_WIDE_FILES,
    SCHOOL_VIEW_FILES,
    LandscapeReportBundle,
    LandscapeReportInputs,
    LandscapeReportService,
)
from debate_core.application.landscape_scan import scan_report
from debate_core.application.landscape_staleness import STALE_BANNER_HEADING
from debate_core.arguments.landscape.render import (
    IMPACT_CARD_COLUMNS,
    POSITION_COLUMNS,
    SCHOOL_COLUMNS,
    TOP_CARD_COLUMNS,
    TREND_COLUMNS,
    header_metadata,
    render_impact_cards_csv,
    render_markdown,
    render_top_cards_csv,
)
from debate_core.domain.landscape_report import LandscapeReport, TopCard
from debate_core.testing.landscape_report import (
    SYNTHETIC_REPORT_DATE,
    SYNTHETIC_THIRD_SNAPSHOT,
    read_synthetic_caselist,
    read_topic_change_caselist,
    synthetic_staleness,
)

REPO = Path(__file__).resolve().parents[5]
FIXTURE = REPO / "tests" / "fixtures" / "landscape" / "synthetic_caselist"
GOLDEN = REPO / "tests" / "fixtures" / "landscape" / "golden"
TOPIC_CHANGE = REPO / "tests" / "fixtures" / "landscape" / "topic_change_caselist"
FILES = (
    "report.md",
    "positions.csv",
    "top_cards.csv",
    "impact_cards.csv",
    "trends.csv",
    "schools.csv",
    "schools.md",
)
CSV_FILES = ("positions.csv", "top_cards.csv", "impact_cards.csv", "trends.csv", "schools.csv")


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


def test_the_bundle_is_the_circuit_wide_files_and_the_school_view() -> None:
    assert sorted(_bundle().files) == sorted(FILES) == sorted((*CIRCUIT_WIDE_FILES, *SCHOOL_VIEW_FILES))


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
    files = _bundle().files
    for name in CIRCUIT_WIDE_FILES:
        text = files[name]
        found = {code for code in codes if re.search(rf"(?<![A-Za-z0-9]){code}(?![A-Za-z0-9])", text)}
        found |= {one for one in names | paths if one.casefold() in text.casefold()}
        found |= {one.split()[0] for one in schools if one.split()[0].casefold() in text.casefold()}
        assert not found, f"{name} names {sorted(found)}"


def test_the_scan_finds_a_team_code_planted_in_a_tag() -> None:
    planted = _with_tag(_bundle().report, "As XX said")
    assert re.search(r"(?<![A-Za-z0-9])XX(?![A-Za-z0-9])", render_top_cards_csv(planted, {}))


def test_the_csv_columns_are_the_specs() -> None:
    files = _bundle().files
    for name, columns in (
        ("positions.csv", POSITION_COLUMNS),
        ("top_cards.csv", TOP_CARD_COLUMNS),
        ("impact_cards.csv", IMPACT_CARD_COLUMNS),
    ):
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
    # v1-e32-t14, the PM's ruling of 2026-10-25: scenario and internal_link_tag only, no card-above column.
    assert (*TOP_CARD_COLUMNS, "scenario", "internal_link_tag") == IMPACT_CARD_COLUMNS


def test_a_stale_report_starts_with_the_banner_and_its_csvs_say_stale_true() -> None:
    files = _bundle(report_date=date(2026, 9, 25)).files
    assert files["report.md"].startswith(STALE_BANNER_HEADING)
    assert "2026-09-15, 10 day(s) before this report" in files["report.md"].splitlines()[0]
    assert "| Data freshness | Stale: the newest snapshot is 2026-09-15, 10 day(s) old" in files["report.md"]
    for name in CSV_FILES:
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
    assert all("# stale=false\n" in files[name] for name in CSV_FILES)


def _with_tag(report: LandscapeReport, tag: str) -> LandscapeReport:
    first: TopCard = report.top_cards[0]
    return report.model_copy(
        update={"top_cards": (first.model_copy(update={"tag": tag}), *report.top_cards[1:])}
    )


def test_report_md_lists_impact_and_chain_cards_only_and_points_to_top_cards_csv() -> None:
    """The coach's reviews of 2026-10-24: no most-read cards in report.md, the impact cards instead, and
    (`v1-e32-t14`) each position's link chain and what leads into each impact."""
    files = _bundle().files
    report = _bundle().report
    shown = {card.tag for card in (*report.impact_cards, *report.chain_cards)}
    shown |= {card.internal_link_tag for card in report.impact_cards}
    shown |= {card.card_above_tag for card in report.impact_cards}
    for card in (*report.top_cards, *report.impact_cards, *report.chain_cards):
        assert card.source_object_key not in files["report.md"]
        assert card.tag is None or card.tag in shown or card.tag not in files["report.md"]
    for card in report.top_cards:
        assert card.source_object_key in files["top_cards.csv"]
    for card in report.impact_cards:
        assert card.source_object_key in files["impact_cards.csv"]
        assert (
            f"| {card.rank} | {card.teams_reading} | {card.tag} | {card.short_cite} |" in files["report.md"]
        )
    assert "most-read cards are in `top_cards.csv`" in files["report.md"]


def test_each_kind_says_how_many_of_its_documents_carry_no_labelled_impact() -> None:
    files = _bundle().files
    # a3 and b5 carry v1-e32-t14's impact cards (README, "Scenarios and link chains").
    assert "Advantage documents with no labelled impact: 3 of 6 (50.0%)." in files["report.md"]
    assert "DA documents with no labelled impact: 2 of 6 (33.3%)." in files["report.md"]
    assert "# no_labelled_impact_advantage=3/6\n# no_labelled_impact_da=2/6\n" in files["impact_cards.csv"]


def test_the_card_above_an_impact_is_never_called_its_internal_link() -> None:
    """`v1-e32-t14`, the PM's ruling: a fact about the file, in report.md only, counted apart."""
    files = _bundle().files
    above = "Single payer cuts administrative costs"
    assert f"* Rank 1: no labelled internal link. Card above it in the file: {above}\n" in files["report.md"]
    assert f"Internal link: {above}" not in files["report.md"]
    rows = list(
        csv.DictReader(line for line in files["impact_cards.csv"].splitlines() if not line.startswith("#"))
    )
    costs = next(row for row in rows if row["position_id"] == "costs-advantage" and row["rank"] == "1")
    assert costs["internal_link_tag"] == ""
    assert above not in files["impact_cards.csv"]
    labelled = next(row for row in rows if row["position_id"] == "spending-da" and row["rank"] == "3")
    assert labelled["internal_link_tag"] == "Deficits spike interest rates"
    assert "* Rank 3: Internal link: Deficits spike interest rates\n" in files["report.md"]


def test_a_tag_in_an_impact_row_is_escaped_in_markdown_and_exact_in_the_csv() -> None:
    report = _bundle().report
    tag = "Costs | fall *fast*\nunder_plan"
    first = report.impact_cards[0].model_copy(update={"tag": tag})
    changed = report.model_copy(update={"impact_cards": (first, *report.impact_cards[1:])})
    assert r"| 1 | 1 | Costs \| fall \*fast\* under\_plan | Okafor 25 |" in render_markdown(changed)
    rendered = render_impact_cards_csv(changed, {})
    rows = list(csv.reader(line for line in rendered.splitlines(keepends=True) if not line.startswith("#")))
    assert rows[1][IMPACT_CARD_COLUMNS.index("tag")] == tag


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


def test_plan_text_and_team_carry_identifications_have_labels() -> None:
    """`v1-e32-t09`'s two methods, as the method table names them."""
    from debate_core.application.landscape_report import round_id
    from debate_core.domain.caselist import Side
    from debate_core.domain.landscape_report import AffAssignment

    inputs = read_synthetic_caselist(FIXTURE)
    aff_rounds = sorted({round_id(one) for one in inputs.disclosures if one.side is Side.AFF})
    aff_id = next(one.id for one in inputs.taxonomy.positions if one.kind.value == "aff")
    assigned = dataclasses.replace(
        inputs,
        aff_assignments=(
            AffAssignment(round_id=aff_rounds[0], position_id=aff_id, method="PLAN_TEXT"),
            AffAssignment(round_id=aff_rounds[1], position_id=aff_id, method="TEAM_CARRY"),
        ),
    )
    report = LandscapeReportService().bundle(assigned, synthetic_staleness()).files["report.md"]
    assert "| The round's plan text names the aff (`PLAN_TEXT`) | 1 |" in report
    assert "| The team's other rounds name the aff (`TEAM_CARRY`) | 1 |" in report


# ------------------------------------------------------------------------------------------------
# Trends and the school view (`v1-e32-t04`)
# ------------------------------------------------------------------------------------------------


def _files(inputs: LandscapeReportInputs) -> dict[str, str]:
    staleness = synthetic_staleness(caselist=inputs.caselist, newest_snapshot=inputs.through)
    return LandscapeReportService().bundle(inputs, staleness).files


def _csv_rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(line for line in text.splitlines() if not line.startswith("#")))


def _metadata(text: str) -> dict[str, str]:
    return dict(line[2:].split("=", 1) for line in text.splitlines() if line.startswith("# "))


def test_the_third_windows_trends_csv_matches_the_hand_computed_expected_file() -> None:
    """ac1, on the three-snapshot fixture."""
    files = _files(read_synthetic_caselist(FIXTURE, through=SYNTHETIC_THIRD_SNAPSHOT))
    body = [line for line in files["trends.csv"].splitlines(keepends=True) if not line.startswith("#")]
    assert "".join(body) == (FIXTURE / "expected_trends.csv").read_text(encoding="utf-8")
    assert _metadata(files["trends.csv"])["held_back_by_team_floor"] == "8"


def test_the_third_windows_report_lists_its_rising_and_falling_positions() -> None:
    report = _files(read_synthetic_caselist(FIXTURE, through=SYNTHETIC_THIRD_SNAPSHOT))["report.md"]
    rising = report.split("## Rising\n", 1)[1].split("## Falling", 1)[0]
    falling = report.split("## Falling\n", 1)[1].split("## Unclassified", 1)[0]
    assert rising.index("(`cap-k`, k): 25.0% to 100.0%") < rising.index("(`innovation-advantage`, advantage)")
    assert "(+75.0 points), 1 team to 3" in rising
    assert (
        "(`costs-advantage`, advantage): 75.0% to 0.0% of the week's affirmative teams (-75.0 points)"
        in falling
    )
    assert "Held back by the team floor: 8 positions" in falling
    assert "* Courts CP (`courts-cp`, cp): 1 team, 33.3% of the week's negative teams" in report


def test_a_first_snapshot_writes_all_new_with_no_previous_share_or_delta() -> None:
    """ac2."""
    files = _files(read_synthetic_caselist(FIXTURE, through=date(2026, 9, 8)))
    rows = _csv_rows(files["trends.csv"])
    assert rows
    assert {row["trend_label"] for row in rows} == {"NEW"}
    assert {(row["previous_teams"], row["previous_share"], row["delta_points"]) for row in rows} == {
        ("", "", "")
    }
    assert (
        "This is the caselist's first weekly window on this topic: every position read is NEW"
        in files["report.md"]
    )
    assert files["report.md"].count("No trend is drawn: there is no earlier window on this topic") == 2


def test_a_topic_change_draws_no_trend_and_the_report_says_the_topic_changed() -> None:
    """ac3."""
    files = _files(read_topic_change_caselist(TOPIC_CHANGE))
    rows = _csv_rows(files["trends.csv"])
    assert [(row["position_id"], row["trend_label"], row["delta_points"]) for row in rows] == [
        ("restored-ecosystems-contention", "NEW", ""),
        ("biopower-k", "NEW", ""),
    ]
    metadata = _metadata(files["trends.csv"])
    assert (metadata["topic_changed_from"], metadata["previous_window"]) == (
        "synthetic-ld-jul-aug on 2026-08-25",
        "",
    )
    assert (
        "The topic changed: the previous snapshot, 2026-08-25, is on synthetic-ld-jul-aug. A trend never "
        "compares two topics, so this is the first window of synthetic-ld-sep-oct here"
    ) in files["report.md"]
    assert (
        "The snapshot before, 2026-08-25, is on synthetic-ld-jul-aug, so no trend is drawn |"
        in files["report.md"]
    )


def test_a_report_short_of_a_full_topic_cycle_says_so_on_its_face() -> None:
    files = _files(read_topic_change_caselist(TOPIC_CHANGE))
    face = files["report.md"].split("## About this report", 1)[0]
    assert (
        "**Short history.** The data covers 1 weekly window on this topic, 2026-08-26 to 2026-09-01, of a "
        "topic that runs 2026-09-01 to 2026-10-31: less than a full topic cycle."
    ) in face
    assert _metadata(files["trends.csv"])["full_topic_cycle"] == "false"


def test_a_report_over_a_full_topic_cycle_has_no_short_history_notice() -> None:
    inputs = read_synthetic_caselist(FIXTURE, through=SYNTHETIC_THIRD_SNAPSHOT)
    files = _files(dataclasses.replace(inputs, topic_range=(date(2026, 9, 2), date(2026, 9, 28))))
    assert "Short history" not in files["report.md"]
    assert _metadata(files["trends.csv"])["full_topic_cycle"] == "true"


def test_the_trend_and_school_csv_columns_are_the_specs() -> None:
    files = _bundle().files
    assert list(_csv_rows(files["trends.csv"])[0]) == list(TREND_COLUMNS)
    assert {"weekly_teams", "weekly_share", "previous_share", "delta_points", "trend_label"} <= set(
        TREND_COLUMNS
    )
    assert SCHOOL_COLUMNS == ("school", "team_code", "side", "position_id", "rounds", "team_page")
    assert list(_csv_rows(files["schools.csv"])[0]) == list(SCHOOL_COLUMNS)


def test_the_school_view_carries_no_debater_name_tag_cite_or_path() -> None:
    """ac4: names planted where a team's own words could carry them never reach the view's files."""
    inputs = read_synthetic_caselist(FIXTURE)
    names = ("Jordan Ellis", "Priya Natarajan")
    cards = tuple(
        card.model_copy(update={"tag": f"{names[0]} 1AC", "short_cite": names[1], "headings": names})
        for card in inputs.cards
    )
    paths = tuple(
        one.evolve(source_path=one.source_path.replace(".docx", "-JordanEllis.docx"))
        for one in inputs.disclosures
    )
    files = _files(dataclasses.replace(inputs, cards=cards, disclosures=paths))
    for name in SCHOOL_VIEW_FILES:
        assert files[name] == (GOLDEN / name).read_text(encoding="utf-8")
        for planted in (*names, "JordanEllis", ".docx"):
            assert planted not in files[name]
    for card in read_synthetic_caselist(FIXTURE).cards:
        assert card.tag is None or card.tag not in files["schools.md"]


def test_only_the_school_view_names_schools_and_team_codes() -> None:
    files = _bundle().files
    disclosures = read_synthetic_caselist(FIXTURE).disclosures
    for name in SCHOOL_VIEW_FILES:
        assert all(one.school in files[name] for one in disclosures)
        assert all(
            re.search(rf"(?<![A-Za-z0-9]){one.team_code}(?![A-Za-z0-9])", files[name]) for one in disclosures
        )
        assert not any(one.source_path in files[name] for one in disclosures)
        # The PM's ruling of 2026-10-24: school plus team code, never more; no tournament or round.
        assert not any(one.tournament and one.tournament in files[name] for one in disclosures)


def test_a_stale_school_view_starts_with_the_banner() -> None:
    files = _bundle(report_date=date(2026, 9, 25)).files
    assert files["schools.md"].startswith(STALE_BANNER_HEADING)
    assert "# stale=true\n" in files["schools.csv"]


BIRCHMOOR_PAGE = "https://opencaselist.com/synthpolicy26/Birchmoor"


def test_no_circuit_wide_file_carries_a_link_and_the_school_view_does() -> None:
    """`v1-e32-t18`: policy 1.14 allows the team-page link in the school view and nowhere else."""
    files = _bundle().files
    for name in CIRCUIT_WIDE_FILES:
        assert "opencaselist" not in files[name].casefold(), name
        assert not re.search(r"https?:|www\.", files[name]), name
    for name in SCHOOL_VIEW_FILES:
        assert f"{BIRCHMOOR_PAGE}/QQ" in files[name]
        assert f"{BIRCHMOOR_PAGE}/ZZ" in files[name]


def test_the_scan_still_reads_the_school_view_for_paths_only_and_finds_nothing() -> None:
    """The run scans the bundle so; a team-page link is no path, so the school view has no hit."""
    files = _bundle().files
    disclosures = read_synthetic_caselist(FIXTURE).disclosures
    assert scan_report(files, disclosures, school_view_files=SCHOOL_VIEW_FILES) == ()
    named = scan_report({name: files[name] for name in SCHOOL_VIEW_FILES}, disclosures)
    assert {hit.file for hit in named} == set(SCHOOL_VIEW_FILES)


def test_a_team_code_that_is_not_one_address_word_gets_no_link_and_is_counted() -> None:
    inputs = read_synthetic_caselist(FIXTURE)
    disclosures = tuple(
        one.evolve(team_code="Q-Q") if one.team_code == "QQ" else one for one in inputs.disclosures
    )
    files = _files(dataclasses.replace(inputs, disclosures=disclosures))
    counted = (
        "1 of 8 team codes link to their openCaselist page; 7 do not: 6 whose school is not one address "
        "word, 1 whose team code is not one address word"
    )
    assert f"| Team pages | {counted} |" in files["schools.md"]
    assert f"# team_pages={counted}\n" in files["schools.csv"]
    assert "| Birchmoor | Q-Q | neg | 1 | none |" in files["schools.md"]
    assert f"| Birchmoor | ZZ | neg | 1 | [openCaselist]({BIRCHMOOR_PAGE}/ZZ) |" in files["schools.md"]
    rows = [row for row in _csv_rows(files["schools.csv"]) if row["school"] == "Birchmoor"]
    assert {(row["team_code"], row["team_page"]) for row in rows} == {
        ("Q-Q", ""),
        ("ZZ", f"{BIRCHMOOR_PAGE}/ZZ"),
    }
    assert "opencaselist" not in "".join(files[name] for name in CIRCUIT_WIDE_FILES).casefold()


def test_the_by_position_section_follows_the_by_school_section() -> None:
    text = _bundle().files["schools.md"]
    headings = [line for line in text.splitlines() if line.startswith("## ")]
    assert headings == ["## By school", "## By position"]
