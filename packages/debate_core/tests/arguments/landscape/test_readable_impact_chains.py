"""What each impact runs through, named in words a debater uses (`v1-e32-t25`).

Each impact row is named by the first of its scenario, its labelled internal link, its own tag and the
card above it, marked with that source; a withheld text falls through to the next, and a row with none
is left out and counted. The synthetic caselist read unchanged names every row by its scenario or its
tag (`tests/fixtures/landscape/golden/`). `tests/fixtures/landscape/readable_impact_chains/` edits two
tags and adds two scenario lists to reach every source, a withheld tag and a left-out row; its report
sections and impact_cards.csv were written by hand from the fixture (that directory's README.md), before
any code. The service cases below change one card more each and say, by hand, what the rows then show.
"""

from __future__ import annotations

import csv
import dataclasses
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from debate_core.application.landscape_report import LandscapeReportInputs, LandscapeReportService
from debate_core.arguments.landscape.link_chains import caselist_words, is_withheld, rank_name
from debate_core.domain.landscape import PositionKind, Taxonomy
from debate_core.domain.landscape_report import (
    LEAD_IN_ORDER,
    ChainCoverage,
    ChainRole,
    ImpactCard,
    LandscapeReport,
    LeadInSource,
    NamedRows,
    RoleGap,
)
from debate_core.testing.landscape_report import read_synthetic_caselist, synthetic_staleness

LANDSCAPE = Path(__file__).resolve().parents[5] / "tests" / "fixtures" / "landscape"
FIXTURE = LANDSCAPE / "synthetic_caselist"
GOLDEN = LANDSCAPE / "golden"
READABLE = LANDSCAPE / "readable_impact_chains"
SECTIONS = ("#### Advantages: impact cards", "#### Disadvantages: impact cards")
RUNS_THROUGH = "What each impact runs through:"

SCENARIO = LeadInSource.SCENARIO
INTERNAL_LINK = LeadInSource.INTERNAL_LINK
TAG = LeadInSource.TAG
CARD_ABOVE = LeadInSource.CARD_ABOVE


def _edits() -> dict[str, Any]:
    return yaml.safe_load((READABLE / "edits.yaml").read_text(encoding="utf-8"))


def _with_edits(
    edits: dict[str, Any], tags: dict[tuple[str, int], str | None] | None = None
) -> LandscapeReportInputs:
    """The synthetic caselist with `edits`' tags and lists, then `tags`' tags, by file and paragraph."""
    inputs = read_synthetic_caselist(FIXTURE)
    changed = {(one["file"], one["element_index"]): one["tag"] for one in edits.get("cards", ())}
    changed.update(tags or {})
    cards = tuple(
        card.model_copy(update={"tag": changed[(card.source_sha256[:2], card.element_index)]})
        if (card.source_sha256[:2], card.element_index) in changed
        else card
        for card in inputs.cards
    )
    lists = edits.get("scenario_lists", {})
    document = inputs.taxonomy.model_dump()
    document["positions"] = [{**one, **lists.get(one["id"], {})} for one in document["positions"]]
    return dataclasses.replace(inputs, cards=cards, taxonomy=Taxonomy.model_validate(document))


def _report(inputs: LandscapeReportInputs) -> LandscapeReport:
    return LandscapeReportService().build(inputs, synthetic_staleness())


def _named(report: LandscapeReport, position_id: str) -> list[LeadInSource | None]:
    return [row.named_by for row in report.impact_cards if row.position_id == position_id]


def _counts(report: LandscapeReport) -> dict[str, tuple[int, ...]]:
    """Per kind: rows named by scenario, internal link, tag and card above; left out; tags withheld."""
    return {
        one.kind.value: (*(named.rows for named in one.named_rows), one.rows_left_out, one.withheld_tags)
        for one in report.chain_coverage
    }


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


def _runs_through_lines(report_md: str) -> list[str]:
    """Every line under a "What each impact runs through" heading, up to the next blank line after it."""
    lines = report_md.splitlines()
    found: list[str] = []
    for number, line in enumerate(lines):
        if line != RUNS_THROUGH:
            continue
        for following in lines[number + 2 :]:
            if not following:
                break
            found.append(following)
    return found


# ------------------------------------------------------------------------------------------------
# The hand-written golden files
# ------------------------------------------------------------------------------------------------


def _bundle_files() -> dict[str, str]:
    return LandscapeReportService().bundle(_with_edits(_edits()), synthetic_staleness()).files


def test_the_impact_sections_match_the_hand_written_golden() -> None:
    sections, _ = _split(_bundle_files()["report.md"])
    assert sections == (READABLE / "impact_sections.md").read_text(encoding="utf-8")


def test_the_rest_of_report_md_is_the_unchanged_caselists() -> None:
    _, rest = _split(_bundle_files()["report.md"])
    _, base_rest = _split((GOLDEN / "report.md").read_text(encoding="utf-8"))
    assert rest == base_rest


def test_impact_cards_csv_matches_the_hand_written_golden() -> None:
    assert _bundle_files()["impact_cards.csv"] == (READABLE / "impact_cards.csv").read_text(encoding="utf-8")


def test_the_unchanged_caselist_names_every_row_by_its_scenario_or_its_tag() -> None:
    report = _report(read_synthetic_caselist(FIXTURE))
    assert _named(report, "costs-advantage") == [SCENARIO, TAG, TAG]
    assert _named(report, "spending-da") == [TAG, TAG, SCENARIO]
    assert _named(report, "hospital-closures-da") == [TAG]
    assert _counts(report) == {"advantage": (1, 0, 2, 0, 0, 0), "da": (1, 0, 3, 0, 0, 0)}


# ------------------------------------------------------------------------------------------------
# The order, on the edited caselist
# ------------------------------------------------------------------------------------------------


def test_each_row_takes_the_first_source_it_has() -> None:
    report = _report(_with_edits(_edits()))
    # Costs: rank 1's tag is withheld, so the card above; rank 2 its tag; rank 3 nothing.
    assert _named(report, "costs-advantage") == [CARD_ABOVE, TAG, None]
    # Spending: rank 1 the coach's `Market crash`; rank 3's internal link ahead of its own tag.
    assert _named(report, "spending-da") == [SCENARIO, TAG, INTERNAL_LINK]
    assert _counts(report) == {"advantage": (0, 0, 1, 1, 1, 1), "da": (1, 1, 2, 0, 0, 0)}


def test_a_scenario_names_a_row_ahead_of_its_internal_link() -> None:
    # The unchanged Spending DA's rank 3 has both `recession` and its internal link.
    row = _report(read_synthetic_caselist(FIXTURE)).impact_cards
    rank_3 = next(one for one in row if one.position_id == "spending-da" and one.rank == 3)
    assert (rank_3.scenario, rank_3.internal_link_tag, rank_3.named_by) == (
        "recession",
        "Deficits spike interest rates",
        SCENARIO,
    )


def test_an_empty_row_is_left_out_and_counted_never_shown() -> None:
    # The Costs advantage's lines come first: rank 3 has no line of its own, only the count.
    assert _runs_through_lines(_bundle_files()["report.md"])[:3] == [
        "* Rank 1: Single payer cuts administrative costs (card above)",
        "* Rank 2: Bulk purchasing lowers drug prices (tag)",
        "* Ranks left out, with no scenario, internal link, tag or card above to name them: 1.",
    ]


def test_a_blank_tag_is_no_tag() -> None:
    report = _report(_with_edits(_edits(), {("a3", 15): "   "}))
    assert _named(report, "costs-advantage") == [CARD_ABOVE, TAG, None]
    assert _counts(report)["advantage"] == (0, 0, 1, 1, 1, 1)


# ------------------------------------------------------------------------------------------------
# Withholding (policy 1.13)
# ------------------------------------------------------------------------------------------------


def test_a_withheld_tag_falls_through_to_the_card_above() -> None:
    report = _report(_with_edits(_edits()))
    rank_1 = report.impact_cards[0]
    assert (rank_1.position_id, rank_1.tag, rank_1.card_above_tag, rank_1.named_by) == (
        "costs-advantage",
        "2. Extinction from a Cedarvale collapse",
        "Single payer cuts administrative costs",
        CARD_ABOVE,
    )


def test_a_withheld_card_above_leaves_the_row_out_and_both_are_counted() -> None:
    # a1's copy `a` above rank 1 now holds `driftwood`, a school's word, as well as rank 1's own tag.
    report = _report(_with_edits(_edits(), {("a1", 3): "Single payer cuts Driftwood costs"}))
    assert _named(report, "costs-advantage") == [None, TAG, None]
    assert report.impact_cards[0].card_above_tag is None
    assert _counts(report)["advantage"] == (0, 0, 1, 0, 2, 2)


def test_a_withheld_internal_link_falls_through_to_the_tag_and_leaves_the_csv() -> None:
    # b5's cluster 41 above Spending rank 3 now holds `birchmoor`; `recession` is dropped by the edits.
    inputs = _with_edits(_edits(), {("b5", 9): "Deficits spike Birchmoor rates"})
    report = _report(inputs)
    assert _named(report, "spending-da") == [SCENARIO, TAG, TAG]
    assert _counts(report)["da"] == (1, 0, 3, 0, 0, 1)
    rank_3 = next(one for one in report.impact_cards if one.position_id == "spending-da" and one.rank == 3)
    assert rank_3.internal_link_tag is None
    files = LandscapeReportService().bundle(inputs, synthetic_staleness()).files
    assert "Birchmoor" not in files["impact_cards.csv"]
    assert not any("Birchmoor" in line for line in _runs_through_lines(files["report.md"]))


def test_a_withheld_text_a_row_never_reaches_is_not_counted_but_never_quoted() -> None:
    # Unchanged lists: Spending rank 3 is named by `recession`, and Costs rank 1 by `economic collapse`.
    inputs = _with_edits(
        {},
        {("b5", 9): "Deficits spike Birchmoor rates", ("a1", 6): "2. Extinction from a Cedarvale collapse"},
    )
    report = _report(inputs)
    assert _named(report, "spending-da") == [TAG, TAG, SCENARIO]
    assert _named(report, "costs-advantage") == [SCENARIO, TAG, TAG]
    assert _counts(report) == {"advantage": (1, 0, 2, 0, 0, 0), "da": (1, 0, 3, 0, 0, 0)}
    rows = list(
        csv.DictReader(
            line
            for line in LandscapeReportService()
            .bundle(inputs, synthetic_staleness())
            .files["impact_cards.csv"]
            .splitlines()
            if not line.startswith("#")
        )
    )
    spending = next(row for row in rows if row["position_id"] == "spending-da" and row["rank"] == "3")
    assert spending["internal_link_tag"] == ""


@pytest.mark.parametrize(
    "tags",
    [
        pytest.param({}, id="the edits"),
        pytest.param({("a1", 3): "Single payer cuts Driftwood costs"}, id="a withheld card above"),
        pytest.param({("b5", 9): "Deficits spike Birchmoor rates"}, id="a withheld internal link"),
        pytest.param({("b4", 6): "Rural hospitals close in XX counties"}, id="a team code in a tag"),
    ],
)
def test_no_line_under_what_each_impact_runs_through_holds_a_caselist_word(
    tags: dict[tuple[str, int], str | None],
) -> None:
    inputs = _with_edits(_edits(), tags)
    words = caselist_words(inputs.disclosures)
    lines = _runs_through_lines(
        LandscapeReportService().bundle(inputs, synthetic_staleness()).files["report.md"]
    )
    assert lines
    assert [line for line in lines if is_withheld(line, words)] == []


def test_a_tag_holding_a_team_code_is_withheld_for_the_next_source() -> None:
    # `XX` is a team code of the caselist; the Hospital closures DA's only row has no card above it.
    report = _report(_with_edits(_edits(), {("b4", 6): "Rural hospitals close in XX counties"}))
    assert _named(report, "hospital-closures-da") == [None]
    assert _counts(report)["da"] == (1, 1, 1, 0, 1, 1)


# ------------------------------------------------------------------------------------------------
# The rule alone
# ------------------------------------------------------------------------------------------------

WORDS = frozenset({"cedarvale", "xx"})


def test_the_order_is_scenario_internal_link_tag_card_above() -> None:
    assert LEAD_IN_ORDER == (SCENARIO, INTERNAL_LINK, TAG, CARD_ABOVE)
    every = {SCENARIO: "dome", INTERNAL_LINK: "il", TAG: "tag", CARD_ABOVE: "above"}
    assert rank_name(every, WORDS) == (SCENARIO, 0)
    assert rank_name({**every, SCENARIO: None}, WORDS) == (INTERNAL_LINK, 0)
    assert rank_name({TAG: "tag", CARD_ABOVE: "above"}, WORDS) == (TAG, 0)
    assert rank_name({CARD_ABOVE: "above"}, WORDS) == (CARD_ABOVE, 0)


def test_with_nothing_there_nothing_names_the_row() -> None:
    assert rank_name({}, WORDS) == (None, 0)
    assert rank_name({SCENARIO: None, INTERNAL_LINK: "", TAG: " \t", CARD_ABOVE: None}, WORDS) == (None, 0)


def test_withheld_texts_are_passed_over_and_counted() -> None:
    texts = {INTERNAL_LINK: "Cedarvale spike", TAG: "Crash in XX", CARD_ABOVE: "Rates rise"}
    assert rank_name(texts, WORDS) == (CARD_ABOVE, 2)
    assert rank_name({**texts, CARD_ABOVE: "cedarvale"}, WORDS) == (None, 3)
    assert rank_name({TAG: "Cedarvales crash"}, WORDS) == (TAG, 0)


# ------------------------------------------------------------------------------------------------
# The domain's checks
# ------------------------------------------------------------------------------------------------


def _row(**changes: object) -> ImpactCard:
    return ImpactCard.model_validate(
        {
            "position_id": "spending-da",
            "rank": 1,
            "fingerprint": "15" * 32,
            "teams_reading": 2,
            "tag": "Debt ceiling fights are near",
            "short_cite": "Ruiz 26",
            "source_object_key": "raw/caselist/synthpolicy26/sha256/b1/b1/" + "b1" * 32,
            "element_index": 3,
            "source_snapshot": "2026-09-08",
            **changes,
        }
    )


@pytest.mark.parametrize(
    ("source", "field"),
    [
        (SCENARIO, "scenario"),
        (INTERNAL_LINK, "internal_link_tag"),
        (TAG, "tag"),
        (CARD_ABOVE, "card_above_tag"),
    ],
)
def test_a_row_is_named_only_by_a_source_it_has(source: LeadInSource, field: str) -> None:
    with pytest.raises(ValidationError, match="names"):
        _row(named_by=source, **{field: None})
    with pytest.raises(ValidationError, match="names"):
        _row(named_by=source, **{field: "  "})
    assert _row(named_by=source, **{field: "words"}).named_by is source


def _coverage(**changes: object) -> ChainCoverage:
    return ChainCoverage.model_validate(
        {
            "kind": PositionKind.DA,
            "documents": 6,
            "unstructured_documents": 2,
            "positions": 4,
            "impact_rows": 4,
            "rows_with_scenario": 1,
            "rows_with_internal_link": 1,
            "rows_with_card_above": 0,
            "withheld_names": 0,
            "roles_without_card": (RoleGap(role=ChainRole.IMPACT, positions=2),),
            "unlisted_words": 0,
            "unlisted_words_withheld": 0,
            "named_rows": tuple(
                NamedRows(source=source, rows=rows)
                for source, rows in zip(LEAD_IN_ORDER, (1, 1, 2, 0), strict=True)
            ),
            "rows_left_out": 0,
            "withheld_tags": 0,
            **changes,
        }
    )


def test_coverage_names_every_row_once_or_leaves_it_out() -> None:
    assert _coverage().rows_left_out == 0
    with pytest.raises(ValidationError, match="left out"):
        _coverage(rows_left_out=1)
    with pytest.raises(ValidationError, match="left out"):
        _coverage(impact_rows=5)


def test_coverage_counts_each_source_once_in_naming_order() -> None:
    swapped = (
        NamedRows(source=SCENARIO, rows=1),
        NamedRows(source=TAG, rows=2),
        NamedRows(source=INTERNAL_LINK, rows=1),
        NamedRows(source=CARD_ABOVE, rows=0),
    )
    with pytest.raises(ValidationError, match="naming order"):
        _coverage(named_rows=swapped)
    with pytest.raises(ValidationError, match="naming order"):
        _coverage(named_rows=swapped[:3])


def test_coverage_rows_named_by_a_scenario_are_the_rows_with_one() -> None:
    with pytest.raises(ValidationError, match="scenario"):
        _coverage(rows_with_scenario=2)
