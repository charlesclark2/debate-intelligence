"""A coach's scenario list per DA and advantage, in the report (`v1-e32-t22`).

The synthetic caselist is read unchanged, and `tests/fixtures/landscape/scenario_vocabulary/` adds a
list to the Costs advantage: two forms merged under one name, one form dropped as no scenario. Its
report sections and impact_cards.csv were written by hand from the fixture (that directory's
README.md), before any code. The service cases below change one list each and say, by hand, what
the rows then show.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import yaml

from debate_core.application.landscape_report import LandscapeReportInputs, LandscapeReportService
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_report import LandscapeReport
from debate_core.testing.landscape_report import read_synthetic_caselist, synthetic_staleness

LANDSCAPE = Path(__file__).resolve().parents[5] / "tests" / "fixtures" / "landscape"
FIXTURE = LANDSCAPE / "synthetic_caselist"
GOLDEN = LANDSCAPE / "golden"
VOCABULARY = LANDSCAPE / "scenario_vocabulary"
SECTIONS = ("#### Advantages: impact cards", "#### Disadvantages: impact cards")


def _with_lists(lists: dict[str, dict[str, Any]]) -> LandscapeReportInputs:
    """The synthetic caselist, its taxonomy's positions given these scenario lists by id."""
    inputs = read_synthetic_caselist(FIXTURE)
    document = inputs.taxonomy.model_dump()
    document["positions"] = [{**one, **lists.get(one["id"], {})} for one in document["positions"]]
    return dataclasses.replace(inputs, taxonomy=Taxonomy.model_validate(document))


def _fixture_lists() -> dict[str, dict[str, Any]]:
    return yaml.safe_load((VOCABULARY / "scenarios.yaml").read_text(encoding="utf-8"))


def _report(lists: dict[str, dict[str, Any]]) -> LandscapeReport:
    return LandscapeReportService().build(_with_lists(lists), synthetic_staleness())


def _scenarios(report: LandscapeReport, position_id: str) -> list[str | None]:
    return [row.scenario for row in report.impact_cards if row.position_id == position_id]


def _withheld(report: LandscapeReport) -> dict[str, int]:
    return {one.kind.value: one.withheld_names for one in report.chain_coverage}


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


# ------------------------------------------------------------------------------------------------
# The hand-written golden files
# ------------------------------------------------------------------------------------------------


def _bundle_files() -> dict[str, str]:
    return LandscapeReportService().bundle(_with_lists(_fixture_lists()), synthetic_staleness()).files


def test_the_impact_sections_match_the_hand_written_golden() -> None:
    sections, _ = _split(_bundle_files()["report.md"])
    assert sections == (VOCABULARY / "impact_sections.md").read_text(encoding="utf-8")


def test_the_rest_of_report_md_is_the_report_without_a_list() -> None:
    _, rest = _split(_bundle_files()["report.md"])
    _, base_rest = _split((GOLDEN / "report.md").read_text(encoding="utf-8"))
    assert rest == base_rest


def test_impact_cards_csv_matches_the_hand_written_golden() -> None:
    assert _bundle_files()["impact_cards.csv"] == (VOCABULARY / "impact_cards.csv").read_text(
        encoding="utf-8"
    )


def test_only_the_scenario_cells_differ_from_the_files_without_a_list() -> None:
    files = _bundle_files()
    for name in ("positions.csv", "top_cards.csv", "trends.csv", "schools.csv", "schools.md"):
        assert files[name] == (GOLDEN / name).read_text(encoding="utf-8"), name


# ------------------------------------------------------------------------------------------------
# One list at a time, on the synthetic caselist
# ------------------------------------------------------------------------------------------------


def test_with_no_list_every_position_keeps_t14s_names() -> None:
    report = _report({})
    assert _scenarios(report, "costs-advantage") == ["economic collapse", None, None]
    assert _scenarios(report, "spending-da") == [None, None, "recession"]
    assert _withheld(report) == {"advantage": 0, "da": 1}


def test_a_list_shows_its_names_and_no_words_it_does_not_hold() -> None:
    # `cedarvale crash` (b1: JJ and YY) is listed under a name with no caselist word; `recession` (QQ,
    # ZZ) is not listed, so rank 3 shows none, and nothing that would show is withheld.
    report = _report({"spending-da": {"scenarios": [{"name": "Market crash", "forms": ["cedarvale crash"]}]}})
    assert _scenarios(report, "spending-da") == ["Market crash", None, None]
    assert _withheld(report) == {"advantage": 0, "da": 0}


def test_a_listed_name_holding_a_caselist_word_is_withheld_and_counted() -> None:
    report = _report(
        {"spending-da": {"scenarios": [{"name": "Cedarvale crash", "forms": ["cedarvale crash"]}]}}
    )
    assert _scenarios(report, "spending-da") == [None, None, None]
    assert _withheld(report) == {"advantage": 0, "da": 1}


def test_a_listed_scenario_one_team_files_under_does_not_show() -> None:
    # `debt crisis` is a3's (VV) alone; merged with `drug prices` (a4, KK) in the fixture it shows.
    report = _report({"costs-advantage": {"scenarios": [{"name": "Debt", "forms": ["debt crisis"]}]}})
    assert _scenarios(report, "costs-advantage") == [None, None, None]


def test_merged_forms_count_every_form_s_teams_under_the_one_name() -> None:
    report = _report(_fixture_lists())
    assert _scenarios(report, "costs-advantage") == [None, "Rising costs", "Rising costs"]


def test_a_list_of_forms_that_name_no_scenario_shows_no_name() -> None:
    report = _report({"spending-da": {"not_scenarios": ["cedarvale crash"]}})
    assert _scenarios(report, "spending-da") == [None, None, None]
    assert _withheld(report) == {"advantage": 0, "da": 0}


def test_a_dropped_named_heading_is_no_scenario_heading() -> None:
    # a5's only scenario heading is `economic collapse`, and its other card labels no role.
    def unstructured(report: LandscapeReport) -> dict[str, int]:
        return {one.kind.value: one.unstructured_documents for one in report.chain_coverage}

    assert unstructured(_report({})) == {"advantage": 1, "da": 2}
    assert unstructured(_report({"costs-advantage": {"not_scenarios": ["economic collapse"]}})) == {
        "advantage": 2,
        "da": 2,
    }


def test_a_list_on_one_position_leaves_the_others_alone() -> None:
    report = _report(_fixture_lists())
    assert _scenarios(report, "spending-da") == [None, None, "recession"]
    assert _withheld(report) == {"advantage": 0, "da": 1}
