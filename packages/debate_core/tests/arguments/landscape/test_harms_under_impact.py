"""Harms headings counted under Impact (`v1-e32-t29`, the PM's ruling of 2026-10-27).

The coach, 2026-10-27: Policy debate no longer says "Harms"; debaters call that part of an advantage its
impact. A `harms` or `harm` sub-heading under an advantage labels its impact, exactly where the Harms role
read it before, and every card it carried is counted under Impact: the impact table, impact_cards.csv, the
chain's Impact row and the count of documents with no labelled impact. No table or line names Harms. A DA's
`harms` heading labels nothing, as before.

`tests/fixtures/landscape/harms_under_impact/` edits five cards' headings: an advantage with only harms
headings, an advantage with both, and a DA. Its goldens were written by hand from the fixture (that
directory's README.md), before any code.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Any

import yaml

from debate_core.application.landscape_report import LandscapeReportInputs, LandscapeReportService
from debate_core.domain.landscape import PositionKind
from debate_core.domain.landscape_report import (
    CHAIN_ROLES,
    DEFAULT_IMPACT_CARDS,
    ChainRole,
    LandscapeCard,
    LandscapeReport,
    TableTagsWithheld,
)
from debate_core.testing.landscape_report import read_synthetic_caselist, synthetic_staleness

LANDSCAPE = Path(__file__).resolve().parents[5] / "tests" / "fixtures" / "landscape"
FIXTURE = LANDSCAPE / "synthetic_caselist"
GOLDEN = LANDSCAPE / "golden"
HARMS = LANDSCAPE / "harms_under_impact"
SECTIONS = ("#### Advantages: impact cards", "#### Disadvantages: impact cards")
HARMS_WORD = re.compile(r"\bharms?\b", re.IGNORECASE)

Key = tuple[str, int]


def _with_edits(
    headings: dict[Key, tuple[str, ...]] | None = None, tags: dict[Key, str] | None = None
) -> LandscapeReportInputs:
    """The synthetic caselist with this directory's heading edits, then `headings` and `tags`, by file
    and paragraph."""
    edits: dict[str, Any] = yaml.safe_load((HARMS / "edits.yaml").read_text(encoding="utf-8"))
    changed: dict[Key, tuple[str, ...]] = {
        (one["file"], one["element_index"]): tuple(one["headings"]) for one in edits["cards"]
    }
    changed.update(headings or {})
    return _edited(read_synthetic_caselist(FIXTURE), changed, tags or {})


def _edited(
    inputs: LandscapeReportInputs, headings: dict[Key, tuple[str, ...]], tags: dict[Key, str]
) -> LandscapeReportInputs:
    cards: list[LandscapeCard] = []
    for card in inputs.cards:
        key = (card.source_sha256[:2], card.element_index)
        update: dict[str, Any] = {}
        if key in headings:
            update["headings"] = headings[key]
        if key in tags:
            update["tag"] = tags[key]
        cards.append(card.model_copy(update=update) if update else card)
    return dataclasses.replace(inputs, cards=tuple(cards))


def _report(inputs: LandscapeReportInputs, impact_cards: int = DEFAULT_IMPACT_CARDS) -> LandscapeReport:
    return LandscapeReportService(impact_cards=impact_cards).build(inputs, synthetic_staleness())


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


def _impact_rows(report: LandscapeReport, position_id: str) -> list[tuple[str, int]]:
    return [
        (one.fingerprint[:2], one.teams_reading)
        for one in report.impact_cards
        if one.position_id == position_id
    ]


# ------------------------------------------------------------------------------------------------
# The hand-written golden files
# ------------------------------------------------------------------------------------------------


def test_the_impact_sections_match_the_hand_written_golden() -> None:
    sections, _ = _split(_files()["report.md"])
    assert sections == (HARMS / "impact_sections.md").read_text(encoding="utf-8")


def test_impact_cards_csv_matches_the_hand_written_golden() -> None:
    assert _files()["impact_cards.csv"] == (HARMS / "impact_cards.csv").read_text(encoding="utf-8")


def test_the_rest_of_report_md_is_the_unchanged_caselists() -> None:
    _, rest = _split(_files()["report.md"])
    _, base_rest = _split((GOLDEN / "report.md").read_text(encoding="utf-8"))
    assert rest == base_rest


# ------------------------------------------------------------------------------------------------
# No section, row or line names Harms
# ------------------------------------------------------------------------------------------------


def test_no_role_named_harms_is_left() -> None:
    assert "harms" not in {role.value for role in ChainRole}
    assert CHAIN_ROLES[PositionKind.ADVANTAGE] == (
        ChainRole.UNIQUENESS,
        ChainRole.LINK,
        ChainRole.INTERNAL_LINK,
        ChainRole.IMPACT,
        ChainRole.INHERENCY,
        ChainRole.SOLVENCY,
    )


def test_harms_is_named_only_where_the_header_says_a_harms_heading_labels_an_impact() -> None:
    for inputs in (_with_edits(), read_synthetic_caselist(FIXTURE)):
        files = _files(inputs)
        assert "Harms" not in files["report.md"]
        lines = [line for line in files["report.md"].splitlines() if HARMS_WORD.search(line)]
        assert len(lines) == 1
        assert lines[0].startswith("* **Impact cards**, under each advantage and DA")
        assert "Under an advantage, a heading saying `harms` or `harm` labels its impact too" in lines[0]
        for name in ("impact_cards.csv", "top_cards.csv", "positions.csv"):
            assert HARMS_WORD.search(files[name]) is None


# ------------------------------------------------------------------------------------------------
# No count lost
# ------------------------------------------------------------------------------------------------


def test_every_harms_card_is_counted_under_impact_past_the_ranks_shown() -> None:
    report = _report(_with_edits(), impact_cards=10)
    # Cluster 2 gains a3's `harm` copy (VV) beside a1's (XX); a5's `harms` card, cluster 38, ranks fourth.
    assert _impact_rows(report, "costs-advantage") == [("02", 2), ("03", 1), ("37", 1), ("38", 1)]
    assert _impact_rows(report, "innovation-advantage") == [("06", 2)]
    unchanged = _report(read_synthetic_caselist(FIXTURE), impact_cards=10)
    assert _impact_rows(unchanged, "costs-advantage") == [("02", 1), ("03", 1), ("37", 1)]
    assert _impact_rows(unchanged, "innovation-advantage") == []


def test_the_documents_with_no_labelled_impact_count_the_harms_cards() -> None:
    coverage = {one.kind: one for one in _report(_with_edits()).impact_coverage}
    advantage = coverage[PositionKind.ADVANTAGE]
    assert (advantage.documents, advantage.unlabelled_documents) == (6, 1)


def test_the_chains_impact_row_is_the_impact_tables_rank_one_with_its_harms_teams() -> None:
    report = _report(_with_edits())
    impact = {
        one.position_id: (one.fingerprint[:2], one.teams_reading)
        for one in report.chain_cards
        if one.role is ChainRole.IMPACT
    }
    assert impact["costs-advantage"] == ("02", 2)
    assert impact["innovation-advantage"] == ("06", 2)


# ------------------------------------------------------------------------------------------------
# Where the Harms role read a heading, and only there
# ------------------------------------------------------------------------------------------------


def test_a_harms_heading_naming_another_role_too_labels_nothing() -> None:
    report = _report(_with_edits({("a4", 0): ("innovation advantage", "harms and solvency")}))
    # a6's `harm` copy is left: one team.
    assert _impact_rows(report, "innovation-advantage") == [("06", 1)]


def test_a_harms_heading_that_answers_labels_nothing() -> None:
    edited = _with_edits()
    cards = tuple(
        card.model_copy(update={"heading_answers": (False, True)})
        if (card.source_sha256[:2], card.element_index) in {("a4", 0), ("a6", 3)}
        else card
        for card in edited.cards
    )
    report = _report(dataclasses.replace(edited, cards=cards))
    assert _impact_rows(report, "innovation-advantage") == []


def test_a_harms_heading_at_the_position_heading_or_above_it_labels_nothing() -> None:
    report = _report(
        _with_edits(
            {("a4", 0): ("harms", "innovation advantage"), ("a6", 3): ("harm", "innovation advantage")}
        )
    )
    assert _impact_rows(report, "innovation-advantage") == []


# ------------------------------------------------------------------------------------------------
# A DA, untouched
# ------------------------------------------------------------------------------------------------


def test_a_das_harms_heading_changes_nothing_a_da_shows() -> None:
    report = _report(_with_edits(), impact_cards=10)
    unchanged = _report(read_synthetic_caselist(FIXTURE), impact_cards=10)
    for position_id in ("spending-da", "election-da", "hospital-closures-da", "provider-strikes-da"):
        assert [one for one in report.impact_cards if one.position_id == position_id] == [
            one for one in unchanged.impact_cards if one.position_id == position_id
        ]
        assert [one for one in report.chain_cards if one.position_id == position_id] == [
            one for one in unchanged.chain_cards if one.position_id == position_id
        ]
    for edited, before in (
        (report.chain_coverage, unchanged.chain_coverage),
        (report.impact_coverage, unchanged.impact_coverage),
    ):
        assert [one for one in edited if one.kind is PositionKind.DA] == [
            one for one in before if one.kind is PositionKind.DA
        ]


# ------------------------------------------------------------------------------------------------
# t28's withholding on the rows the fold adds; t25's card above
# ------------------------------------------------------------------------------------------------


def test_a_tag_the_fold_adds_is_withheld_as_any_other() -> None:
    # a6's copy of cluster 6, the one Innovation's row shows, now holds `Birchmoor`, a school's word.
    report = _report(_with_edits(tags={("a6", 3): "Birchmoor research funding prevents extinction"}))
    row = next(one for one in report.impact_cards if one.position_id == "innovation-advantage")
    assert (row.rank, row.teams_reading, row.tag, row.short_cite, row.named_by) == (
        1,
        2,
        None,
        "Moreau 25",
        None,
    )
    chain = next(
        one
        for one in report.chain_cards
        if one.position_id == "innovation-advantage" and one.role is ChainRole.IMPACT
    )
    assert (chain.teams_reading, chain.tag, chain.short_cite) == (2, None, "Moreau 25")
    assert report.table_tags_withheld == TableTagsWithheld(impact_cards=1, chain_cards=1, top_cards=0)
    advantage = next(one for one in report.chain_coverage if one.kind is PositionKind.ADVANTAGE)
    assert (advantage.withheld_tags, advantage.rows_left_out) == (1, 1)
    files = _files(_with_edits(tags={("a6", 3): "Birchmoor research funding prevents extinction"}))
    assert "Birchmoor" not in files["report.md"]
    assert "Birchmoor" not in files["impact_cards.csv"]


def test_a_harms_card_above_an_impact_card_is_an_impact_card_not_the_card_above() -> None:
    # a1's copies a and d of cluster 2 share one block. Under `impact`, copy a is an impact card, so it is
    # not shown as the card above copy d; under `harms` it is one too.
    base = read_synthetic_caselist(FIXTURE)
    for heading in ("impact", "harms"):
        both = {("a1", 3): ("costs advantage", heading), ("a1", 6): ("costs advantage", heading)}
        row = next(
            one
            for one in _report(_edited(base, both, {})).impact_cards
            if one.position_id == "costs-advantage" and one.rank == 1
        )
        assert (row.fingerprint[:2], row.card_above_tag) == ("02", None), heading
    # Under a DA's `harms`, the card above is no impact card, as before.
    above = {("b5", 9): ("spending da", "harms"), ("b5", 12): ("spending da", "harms")}
    tags = {("b5", 12): "Extinction from a recession"}
    row = next(
        one
        for one in _report(_edited(base, above, tags)).impact_cards
        if one.position_id == "spending-da" and one.fingerprint.startswith("42")
    )
    assert row.card_above_tag == "Deficits spike interest rates"
