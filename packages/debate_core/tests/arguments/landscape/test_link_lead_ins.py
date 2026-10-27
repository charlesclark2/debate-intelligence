"""A labelled link names an impact rank, after its internal link and before its tag (`v1-e32-t27`).

The PM's ruling of 2026-10-26 (2a): a rank under "What each impact runs through" is named by the first
of its scenario, its labelled internal link, its labelled link, its own tag and the card above it. The
link is read as `v1-e32-t25` reads the internal link, with `v1-e32-t14`'s label reader, and marked
`(link)`. A label naming an answer is no link, and a withheld link falls through to the next source and
is counted.

The synthetic caselist read unchanged reaches `(link)` once, on the Spending DA's rank 1
(`tests/fixtures/landscape/golden/`). `tests/fixtures/landscape/link_lead_ins/` edits three tags and
drops `recession`, to reach `(link)` behind a withheld internal link and a withheld link falling through
to the tag. Its report sections and impact_cards.csv were written by hand from the fixture (that
directory's README.md), before any code. The service cases below change one card more each and say, by
hand, what the rows then show.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest
import yaml

from debate_core.application.landscape_report import LandscapeReportInputs, LandscapeReportService
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import PositionRole
from debate_core.domain.landscape_report import ImpactCard, LandscapeReport, LeadInSource
from debate_core.testing.landscape_report import read_synthetic_caselist, synthetic_staleness

LANDSCAPE = Path(__file__).resolve().parents[5] / "tests" / "fixtures" / "landscape"
FIXTURE = LANDSCAPE / "synthetic_caselist"
GOLDEN = LANDSCAPE / "golden"
LINKS = LANDSCAPE / "link_lead_ins"
SECTIONS = ("#### Advantages: impact cards", "#### Disadvantages: impact cards")
RUNS_THROUGH = "What each impact runs through:"

SCENARIO = LeadInSource.SCENARIO
INTERNAL_LINK = LeadInSource.INTERNAL_LINK
LINK = LeadInSource.LINK
TAG = LeadInSource.TAG
CARD_ABOVE = LeadInSource.CARD_ABOVE

B5_LINK = ("b5", 3)
"""`b5`'s cluster 14, under `spending da` alone: the edits' tag opening `Link:` labels it a link."""


def _edits() -> dict[str, Any]:
    return yaml.safe_load((LINKS / "edits.yaml").read_text(encoding="utf-8"))


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


def _without_lists() -> dict[str, Any]:
    """The edits' tags, with `recession` kept, so the Spending DA's rank 3 has its scenario again."""
    return {"cards": _edits()["cards"]}


def _report(inputs: LandscapeReportInputs) -> LandscapeReport:
    return LandscapeReportService().build(inputs, synthetic_staleness())


def _named(report: LandscapeReport, position_id: str) -> list[LeadInSource | None]:
    return [row.named_by for row in report.impact_cards if row.position_id == position_id]


def _rank(report: LandscapeReport, position_id: str, rank: int) -> ImpactCard:
    return next(one for one in report.impact_cards if one.position_id == position_id and one.rank == rank)


def _counts(report: LandscapeReport) -> dict[str, tuple[int, ...]]:
    """Per kind: rows named by scenario, internal link, link, tag and card above; left out; tags withheld."""
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


def _files(inputs: LandscapeReportInputs) -> dict[str, str]:
    return LandscapeReportService().bundle(inputs, synthetic_staleness()).files


# ------------------------------------------------------------------------------------------------
# The hand-written golden files
# ------------------------------------------------------------------------------------------------


def test_the_impact_sections_match_the_hand_written_golden() -> None:
    sections, _ = _split(_files(_with_edits(_edits()))["report.md"])
    assert sections == (LINKS / "impact_sections.md").read_text(encoding="utf-8")


def test_the_rest_of_report_md_is_the_unchanged_caselists_but_for_the_tags_left_empty() -> None:
    # `v1-e32-t28`: cluster 41 (`b5` paragraph 9), holding `birchmoor`, is the Spending DA's internal-link
    # row and its top_cards.csv rank 5; both leave the tag cell empty.
    _, rest = _split(_files(_with_edits(_edits()))["report.md"])
    _, base_rest = _split((GOLDEN / "report.md").read_text(encoding="utf-8"))
    assert rest == base_rest.replace(
        "0 in the impact cards, 0 in the link chains and 0 in `top_cards.csv`",
        "0 in the impact cards, 1 in the link chains and 1 in `top_cards.csv`",
    )


def test_impact_cards_csv_matches_the_hand_written_golden() -> None:
    assert _files(_with_edits(_edits()))["impact_cards.csv"] == (LINKS / "impact_cards.csv").read_text(
        encoding="utf-8"
    )


def test_the_unchanged_caselist_names_the_spending_das_rank_1_by_its_link() -> None:
    report = _report(read_synthetic_caselist(FIXTURE))
    assert _named(report, "spending-da") == [LINK, TAG, SCENARIO]
    assert _named(report, "costs-advantage") == [SCENARIO, TAG, TAG]
    assert _named(report, "hospital-closures-da") == [TAG]
    rank_1 = _rank(report, "spending-da", 1)
    assert (rank_1.link_tag, rank_1.runs_through) == (
        "Spending triggers a debt spiral",
        "Spending triggers a debt spiral",
    )
    assert _counts(report) == {"advantage": (1, 0, 0, 2, 0, 0, 0), "da": (1, 0, 1, 2, 0, 0, 0)}


# ------------------------------------------------------------------------------------------------
# The order: scenario, internal link, link, tag, card above
# ------------------------------------------------------------------------------------------------


def test_the_edits_name_rank_3_by_its_link_behind_a_withheld_internal_link() -> None:
    report = _report(_with_edits(_edits()))
    assert _named(report, "spending-da") == [TAG, TAG, LINK]
    rank_3 = _rank(report, "spending-da", 3)
    assert (rank_3.internal_link_tag, rank_3.link_tag, rank_3.named_by) == (
        None,
        "Link: deficits follow new spending",
        LINK,
    )
    assert _counts(report) == {"advantage": (1, 0, 0, 2, 0, 0, 0), "da": (0, 0, 1, 3, 0, 0, 2)}


def test_an_internal_link_names_a_rank_ahead_of_its_link() -> None:
    # The PM's: the internal link is the step nearest the impact. b5's paragraph 9, not withheld, sits
    # between rank 3 and the link above it.
    report = _report(_with_edits(_edits(), {("b5", 9): "Deficits spike interest rates"}))
    rank_3 = _rank(report, "spending-da", 3)
    assert (rank_3.internal_link_tag, rank_3.link_tag, rank_3.named_by) == (
        "Deficits spike interest rates",
        "Link: deficits follow new spending",
        INTERNAL_LINK,
    )
    assert _counts(report)["da"] == (0, 1, 0, 3, 0, 0, 1)


def test_a_scenario_names_a_rank_ahead_of_its_link() -> None:
    # `recession` kept: rank 3's scenario names it, and its withheld internal link is never reached.
    report = _report(_with_edits(_without_lists()))
    assert _named(report, "spending-da") == [TAG, TAG, SCENARIO]
    assert _counts(report)["da"] == (1, 0, 0, 3, 0, 0, 1)


def test_a_link_names_a_rank_ahead_of_its_own_tag() -> None:
    report = _report(read_synthetic_caselist(FIXTURE))
    rank_1 = _rank(report, "spending-da", 1)
    assert (rank_1.tag, rank_1.named_by) == ("Debt ceiling fights are near", LINK)


def test_the_link_is_the_nearest_link_above_under_the_same_position_heading() -> None:
    # b5's paragraph 6, under `u`, now opens `Link:` too: it is nearer rank 3 than paragraph 3.
    report = _report(_with_edits(_edits(), {("b5", 6): "Link: record spending persists"}))
    rank_3 = _rank(report, "spending-da", 3)
    assert (rank_3.link_tag, rank_3.named_by) == ("Link: record spending persists", LINK)


def test_a_link_in_another_section_names_nothing() -> None:
    # b4's Hospital closures impact (paragraph 6) has b4's paragraph 3 above it, under no heading, and
    # `The link: reform polls badly` (paragraph 9) is below it, under the Midterms DA.
    report = _report(read_synthetic_caselist(FIXTURE))
    assert _named(report, "hospital-closures-da") == [TAG]
    assert _rank(report, "hospital-closures-da", 1).link_tag is None


def test_a_link_under_another_heading_of_the_position_names_nothing() -> None:
    # b5's link card moves under `neg file > spending da`: still the Spending DA's, but another section
    # of the file than rank 3's `spending da`, so the walk up from rank 3 stops before it.
    inputs = _with_edits(_edits())
    cards = tuple(
        card.model_copy(update={"headings": ("neg file", "spending da")})
        if (card.source_sha256[:2], card.element_index) == B5_LINK
        else card
        for card in inputs.cards
    )
    rank_3 = _rank(_report(dataclasses.replace(inputs, cards=cards)), "spending-da", 3)
    assert (rank_3.link_tag, rank_3.named_by) == (None, TAG)


def test_a_link_on_a_card_that_answers_the_position_names_nothing() -> None:
    # b5's link card is classified as answering the Spending DA, so it is not counted for it.
    inputs = _with_edits(_edits())
    classifications = tuple(
        one.model_copy(update={"role": PositionRole.ANSWERS})
        if (one.source_sha256[:2], one.first_element_index) == B5_LINK
        else one
        for one in inputs.classifications
    )
    rank_3 = _rank(_report(dataclasses.replace(inputs, classifications=classifications)), "spending-da", 3)
    assert (rank_3.link_tag, rank_3.named_by) == (None, TAG)


def test_no_advantage_rank_is_named_by_a_link_when_no_advantage_card_labels_one() -> None:
    # a2's copy of cluster 2 is under `no link`, an answer.
    report = _report(_with_edits(_edits()))
    assert LINK not in _named(report, "costs-advantage")
    assert {row.link_tag for row in report.impact_cards if row.position_id == "costs-advantage"} == {None}


# ------------------------------------------------------------------------------------------------
# A label naming an answer is no link
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tag",
    [
        "The link turns: deficits follow new spending",
        "Links are non-unique: deficits follow new spending",
        "No link: deficits follow new spending",
        "Link turn: deficits follow new spending",
        "Link defense: deficits follow new spending",
    ],
)
def test_a_link_answer_names_no_rank_and_the_tag_does(tag: str) -> None:
    # Rank 3's internal link is withheld and `recession` dropped, so b5's paragraph 3 is the only link
    # that could name it. Labelled an answer, it is none, and the rank's own tag names it.
    report = _report(_with_edits(_edits(), {B5_LINK: tag}))
    rank_3 = _rank(report, "spending-da", 3)
    assert (rank_3.link_tag, rank_3.named_by, rank_3.runs_through) == (
        None,
        TAG,
        "Rate spikes cause a recession",
    )
    assert _counts(report)["da"] == (0, 0, 0, 4, 0, 0, 2)


# ------------------------------------------------------------------------------------------------
# Withholding (policy 1.13)
# ------------------------------------------------------------------------------------------------


def test_a_withheld_link_falls_through_to_the_tag_and_is_counted() -> None:
    report = _report(_with_edits(_edits()))
    rank_1 = _rank(report, "spending-da", 1)
    assert (rank_1.link_tag, rank_1.named_by, rank_1.runs_through) == (
        None,
        TAG,
        "Debt ceiling fights are near",
    )
    assert _counts(report)["da"][-1] == 2


def test_a_withheld_link_is_never_shown() -> None:
    # The PM's: b1's link holds `birchmoor`, a school's word. The table and the link chain quote tags as
    # parsed (t10, t14), so only the lines under "What each impact runs through" are read here.
    files = _files(_with_edits(_edits()))
    assert not any("Birchmoor" in line for line in _runs_through_lines(files["report.md"]))
    assert "Birchmoor" not in files["impact_cards.csv"]


def test_a_withheld_link_falls_through_to_the_card_above_when_the_tag_is_withheld_too() -> None:
    # Rank 3's own tag now holds `xx`, a team code, and its link `ashgrove`: both are passed over, as is
    # its internal link, and nothing else names it.
    report = _report(
        _with_edits(
            _edits(),
            {B5_LINK: "Link: Ashgrove deficits follow", ("b5", 12): "Rate spikes cause an XX recession"},
        )
    )
    assert _named(report, "spending-da") == [TAG, TAG, None]
    assert _counts(report)["da"] == (0, 0, 0, 3, 0, 1, 4)


def test_a_withheld_link_a_rank_never_reaches_is_not_counted() -> None:
    # `recession` kept: rank 3's scenario names it before its withheld internal link or its link.
    report = _report(_with_edits(_without_lists(), {B5_LINK: "Link: Ashgrove deficits follow"}))
    assert _named(report, "spending-da") == [TAG, TAG, SCENARIO]
    assert _counts(report)["da"][-1] == 1
