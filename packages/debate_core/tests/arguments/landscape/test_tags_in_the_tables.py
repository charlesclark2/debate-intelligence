"""Tags the tables quote, held to the report's withholding (`v1-e32-t28`, the PM's ruling (b) of 2026-10-27).

A tag holding a word of a caselist school or team code is withheld everywhere the report quotes one: the
lines under "What each impact runs through" (`v1-e32-t25`), the impact table and impact_cards.csv, the
link-chain table and top_cards.csv. In a table the cell is left empty and the row kept with its counts,
and report.md's header counts the cells left empty. A tournament's words are withheld nowhere.

`tests/fixtures/landscape/tags_in_the_tables/` is t25's edits and four tags more: a tag holding only a
tournament word in the impact table and its line, one in the link chain, and a school word and a team
code in top_cards.csv. Its goldens were written by hand from the fixture (that directory's README.md),
before any code.
"""

from __future__ import annotations

import csv
import dataclasses
from pathlib import Path
from typing import Any

import yaml

from debate_core.application.landscape_report import LandscapeReportInputs, LandscapeReportService
from debate_core.arguments.landscape.link_chains import caselist_words, is_withheld
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_report import ChainRole, LandscapeReport, TableTagsWithheld
from debate_core.testing.landscape_report import read_synthetic_caselist, synthetic_staleness

LANDSCAPE = Path(__file__).resolve().parents[5] / "tests" / "fixtures" / "landscape"
FIXTURE = LANDSCAPE / "synthetic_caselist"
GOLDEN = LANDSCAPE / "golden"
TABLES = LANDSCAPE / "tags_in_the_tables"
SECTIONS = ("#### Advantages: impact cards", "#### Disadvantages: impact cards")
LEFT_EMPTY = "* **Tags left empty**: "
GOLDEN_COUNTS = "0 in the impact cards, 0 in the link chains and 0 in `top_cards.csv`"


def _with_edits(tags: dict[tuple[str, int], str | None] | None = None) -> LandscapeReportInputs:
    """The synthetic caselist with this directory's edits, then `tags`' tags, by file and paragraph."""
    edits: dict[str, Any] = yaml.safe_load((TABLES / "edits.yaml").read_text(encoding="utf-8"))
    inputs = read_synthetic_caselist(FIXTURE)
    changed = {(one["file"], one["element_index"]): one["tag"] for one in edits["cards"]}
    changed.update(tags or {})
    cards = tuple(
        card.model_copy(update={"tag": changed[(card.source_sha256[:2], card.element_index)]})
        if (card.source_sha256[:2], card.element_index) in changed
        else card
        for card in inputs.cards
    )
    lists = edits["scenario_lists"]
    document = inputs.taxonomy.model_dump()
    document["positions"] = [{**one, **lists.get(one["id"], {})} for one in document["positions"]]
    return dataclasses.replace(inputs, cards=cards, taxonomy=Taxonomy.model_validate(document))


def _report(inputs: LandscapeReportInputs) -> LandscapeReport:
    return LandscapeReportService().build(inputs, synthetic_staleness())


def _files(inputs: LandscapeReportInputs | None = None) -> dict[str, str]:
    return LandscapeReportService().bundle(inputs or _with_edits(), synthetic_staleness()).files


def _split(report_md: str) -> tuple[str, str]:
    """report.md's two impact-card sections, and everything else."""
    kept: list[str] = []
    sections: list[str] = []
    inside = False
    for line in report_md.splitlines(keepends=True):
        if line.startswith(SECTIONS):
            inside = True
        elif inside and line.startswith(("### ", "## ", "# ")):
            inside = False
        (sections if inside else kept).append(line)
    return "".join(sections), "".join(kept)


def _rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(line for line in text.splitlines() if not line.startswith("#")))


def _row(rows: list[dict[str, str]], position_id: str, rank: int) -> dict[str, str]:
    return next(row for row in rows if row["position_id"] == position_id and row["rank"] == str(rank))


# ------------------------------------------------------------------------------------------------
# The hand-written golden files
# ------------------------------------------------------------------------------------------------


def test_the_impact_sections_match_the_hand_written_golden() -> None:
    sections, _ = _split(_files()["report.md"])
    assert sections == (TABLES / "impact_sections.md").read_text(encoding="utf-8")


def test_impact_cards_csv_matches_the_hand_written_golden() -> None:
    assert _files()["impact_cards.csv"] == (TABLES / "impact_cards.csv").read_text(encoding="utf-8")


def test_top_cards_csv_matches_the_hand_written_golden() -> None:
    assert _files()["top_cards.csv"] == (TABLES / "top_cards.csv").read_text(encoding="utf-8")


def test_the_rest_of_report_md_is_the_unchanged_caselists_but_for_the_count_of_tags_left_empty() -> None:
    _, rest = _split(_files()["report.md"])
    _, base_rest = _split((GOLDEN / "report.md").read_text(encoding="utf-8"))
    assert GOLDEN_COUNTS in base_rest
    assert rest == base_rest.replace(
        GOLDEN_COUNTS, "1 in the impact cards, 1 in the link chains and 2 in `top_cards.csv`"
    )


# ------------------------------------------------------------------------------------------------
# Withheld: the row stays, its tag cell empty
# ------------------------------------------------------------------------------------------------


def test_a_withheld_tag_leaves_its_row_with_its_counts_in_every_table() -> None:
    report = _report(_with_edits())
    unchanged = _report(read_synthetic_caselist(FIXTURE))
    for edited, before in (
        (report.top_cards, unchanged.top_cards),
        (report.impact_cards, unchanged.impact_cards),
        (report.chain_cards, unchanged.chain_cards),
    ):
        assert [(one.position_id, one.rank, one.fingerprint) for one in edited] == [
            (one.position_id, one.rank, one.fingerprint) for one in before
        ]
    impact = next(one for one in report.impact_cards if one.position_id == "costs-advantage" and one.rank == 1)
    assert (impact.tag, impact.teams_reading, impact.short_cite, impact.element_index) == (None, 1, "Okafor 25", 6)
    chain = next(
        one for one in report.chain_cards if one.position_id == "costs-advantage" and one.role is ChainRole.IMPACT
    )
    assert (chain.tag, chain.teams_reading, chain.short_cite) == (None, 1, "Okafor 25")
    top = {(one.position_id, one.rank): one for one in report.top_cards}
    assert (top["nhi-t", 2].tag, top["nhi-t", 2].teams_reading, top["nhi-t", 2].short_cite) == (None, 1, "Lund 21")
    assert (top["condo-bad", 1].tag, top["condo-bad", 1].teams_reading) == (None, 1)


def test_the_withheld_rows_are_counted_per_table() -> None:
    assert _report(_with_edits()).table_tags_withheld == TableTagsWithheld(
        impact_cards=1, chain_cards=1, top_cards=2
    )
    assert _report(read_synthetic_caselist(FIXTURE)).table_tags_withheld == TableTagsWithheld(
        impact_cards=0, chain_cards=0, top_cards=0
    )


def test_no_tag_the_bundle_quotes_holds_a_school_word_or_a_team_code() -> None:
    inputs = _with_edits()
    words = caselist_words(inputs.disclosures)
    files = _files(inputs)
    for name in ("top_cards.csv", "impact_cards.csv"):
        assert [row["tag"] for row in _rows(files[name]) if is_withheld(row["tag"], words)] == []
    for word in ("Cedarvale", "Birchmoor", "for VV"):
        assert word not in files["report.md"]
        assert word not in files["top_cards.csv"]


def test_an_empty_cell_is_written_for_the_withheld_tag_in_both_csvs() -> None:
    files = _files()
    top = _row(_rows(files["top_cards.csv"]), "nhi-t", 2)
    assert (top["tag"], top["teams_reading"], top["short_cite"]) == ("", "1", "Lund 21")
    impact = _row(_rows(files["impact_cards.csv"]), "costs-advantage", 1)
    assert (impact["tag"], impact["teams_reading"], impact["short_cite"]) == ("", "1", "Okafor 25")


# ------------------------------------------------------------------------------------------------
# A tournament's words: shown everywhere
# ------------------------------------------------------------------------------------------------


def test_a_tag_holding_only_a_tournament_word_is_shown_in_every_place() -> None:
    files = _files()
    report_md = files["report.md"]
    assert "| 2 | 1 | Bulk purchasing lowers drug prices later | Haddad 23 |  |" in report_md
    assert "* Rank 2: Bulk purchasing lowers drug prices later (tag)" in report_md
    assert "| Uniqueness | 1 | Spending is at a classic record high now | Ito 25 |" in report_md
    impact = _row(_rows(files["impact_cards.csv"]), "costs-advantage", 2)
    assert impact["tag"] == "Bulk purchasing lowers drug prices later"
    top = _rows(files["top_cards.csv"])
    assert _row(top, "costs-advantage", 2)["tag"] == "Bulk purchasing lowers drug prices later"
    assert _row(top, "spending-da", 4)["tag"] == "Spending is at a classic record high now"


def test_a_scenario_name_holding_only_a_tournament_word_is_shown() -> None:
    # The Spending DA's list names `cedarvale crash` `Market crash`; renamed `Classic crash`, it shows.
    inputs = _with_edits()
    document = inputs.taxonomy.model_dump()
    for one in document["positions"]:
        if one["id"] == "spending-da":
            one["scenarios"] = [{"name": "Classic crash", "forms": ["cedarvale crash"]}]
    report = _report(dataclasses.replace(inputs, taxonomy=Taxonomy.model_validate(document)))
    rank_1 = next(one for one in report.impact_cards if one.position_id == "spending-da" and one.rank == 1)
    assert (rank_1.scenario, rank_1.runs_through) == ("Classic crash", "Classic crash")
    assert next(one for one in report.chain_coverage if one.kind.value == "da").withheld_names == 0
