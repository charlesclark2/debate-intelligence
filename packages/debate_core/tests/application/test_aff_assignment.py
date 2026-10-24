"""Affirmative rounds assigned their aff, through `v1-e32-t03`'s seam (`v1-e32-t09-policy-plan-texts` ac4).

`v1-e32-t03`'s synthetic caselist (`tests/fixtures/landscape/synthetic_caselist`), with a plan-text
verdict given each affirmative file by hand and one more round planted: team JJ, whose round on `a6`
is placed under single payer, reads a second file, `a7`, with no plan text. Expected, worked out by
hand from the fixture's README and this table:

| File | Plan text | Rounds | Expected |
|---|---|---|---|
| `a1` | none | XX's two | left to the report's `PLACED_CARD` (single payer placed) |
| `a2` | names public option | ZZ's | `PLAN_TEXT` public option (its placement is below the threshold) |
| `a3` | none | VV's | `PLACED_CARD` (public option placed) |
| `a4` | names no aff | KK's | unidentified |
| `a5` | names single payer | QQ's | `PLAN_TEXT` single payer |
| `a6` | none | JJ's first | `PLACED_CARD` (single payer placed) |
| `a7` | none | JJ's second | `TEAM_CARRY` single payer |
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from debate_core.application.aff_assignment import AffAssignmentRun, build_aff_assignments
from debate_core.application.landscape_report import LandscapeReportInputs, LandscapeReportService, round_id
from debate_core.arguments.landscape.plan_text import DocumentPlanText, PlanTextVerdict
from debate_core.domain.caselist import Side
from debate_core.domain.landscape_report import AffAssignment
from debate_core.testing.landscape_report import read_synthetic_caselist, synthetic_staleness

REPO = Path(__file__).resolve().parents[4]
FIXTURE = REPO / "tests" / "fixtures" / "landscape" / "synthetic_caselist"
SINGLE_PAYER = "single-payer-aff"
PUBLIC_OPTION = "public-option-aff"
A7 = "a7" * 32


def _source(prefix: str, inputs: LandscapeReportInputs) -> str:
    return next(one.source_sha256 for one in inputs.disclosures if one.source_sha256.startswith(prefix))


@pytest.fixture
def inputs() -> LandscapeReportInputs:
    planted = read_synthetic_caselist(FIXTURE)
    a6 = next(one for one in planted.disclosures if one.source_sha256.startswith("a6"))
    second = a6.model_copy(
        update={"source_sha256": A7, "source_path": a6.source_path.replace("R", "R9"), "round_label": None}
    )
    return dataclasses.replace(planted, disclosures=(*planted.disclosures, second))


def verdicts(inputs: LandscapeReportInputs) -> dict[str, DocumentPlanText]:
    given = {
        "a1": DocumentPlanText(PlanTextVerdict.NONE),
        "a2": DocumentPlanText(PlanTextVerdict.NAMES, PUBLIC_OPTION),
        "a3": DocumentPlanText(PlanTextVerdict.NONE),
        "a4": DocumentPlanText(PlanTextVerdict.UNNAMED),
        "a5": DocumentPlanText(PlanTextVerdict.NAMES, SINGLE_PAYER),
        "a6": DocumentPlanText(PlanTextVerdict.NONE),
    }
    return {
        **{_source(prefix, inputs): verdict for prefix, verdict in given.items()},
        A7: DocumentPlanText(PlanTextVerdict.NONE),
    }


def _round_of(prefix: str, inputs: LandscapeReportInputs) -> str:
    (found,) = {
        round_id(one)
        for one in inputs.disclosures
        if one.source_sha256.startswith(prefix) and one.snapshot <= inputs.through and one.side is Side.AFF
    }
    return found


def run(
    inputs: LandscapeReportInputs, plan_texts: dict[str, DocumentPlanText] | None = None
) -> AffAssignmentRun:
    return build_aff_assignments(
        disclosures=inputs.disclosures,
        through=inputs.through,
        classifications=inputs.classifications,
        plan_texts=verdicts(inputs) if plan_texts is None else plan_texts,
        taxonomy=inputs.taxonomy,
    )


def test_each_affirmative_round_is_assigned_by_its_signal(inputs: LandscapeReportInputs) -> None:
    found = run(inputs)
    assert sorted(found.assignments, key=lambda one: one.round_id) == sorted(
        [
            AffAssignment(round_id=_round_of("a2", inputs), position_id=PUBLIC_OPTION, method="PLAN_TEXT"),
            AffAssignment(round_id=_round_of("a5", inputs), position_id=SINGLE_PAYER, method="PLAN_TEXT"),
            AffAssignment(round_id=_round_of("a7", inputs), position_id=SINGLE_PAYER, method="TEAM_CARRY"),
        ],
        key=lambda one: one.round_id,
    )
    counts = found.counts
    assert (counts.rounds, counts.placed_only, counts.unidentified, counts.carry_refused) == (8, 4, 1, 0)
    assert counts.by_method == {"PLAN_TEXT": 2, "TEAM_CARRY": 1}
    assert (found.aff_teams, found.identified_teams) == (6, 5)


def test_the_report_counts_the_assignments_and_names_each_method(inputs: LandscapeReportInputs) -> None:
    assigned = dataclasses.replace(inputs, aff_assignments=run(inputs).assignments)
    report = LandscapeReportService().build(assigned, synthetic_staleness())
    assert {one.method: one.rounds for one in report.aff_identification} == {
        "PLACED_CARD": 4,
        "PLAN_TEXT": 2,
        "TEAM_CARRY": 1,
    }
    assert (report.unclassified.aff_rounds, report.unclassified.aff_rounds_unidentified) == (8, 1)


def test_a_round_whose_own_plan_text_names_nothing_is_not_carried_into(inputs: LandscapeReportInputs) -> None:
    given = {**verdicts(inputs), A7: DocumentPlanText(PlanTextVerdict.UNNAMED)}
    found = run(inputs, given)
    assert _round_of("a7", inputs) not in {one.round_id for one in found.assignments}
    assert (found.counts.carry_refused, found.counts.unidentified) == (1, 2)


def test_a_placement_below_the_threshold_identifies_nothing(inputs: LandscapeReportInputs) -> None:
    given = {**verdicts(inputs), _source("a2", inputs): DocumentPlanText(PlanTextVerdict.NONE)}
    found = run(inputs, given)
    assert _round_of("a2", inputs) not in {one.round_id for one in found.assignments}
    assert found.counts.unidentified == 2


def test_only_affirmative_rounds_in_range_are_assigned(inputs: LandscapeReportInputs) -> None:
    every_file = {
        one.source_sha256: DocumentPlanText(PlanTextVerdict.NAMES, SINGLE_PAYER) for one in inputs.disclosures
    }
    found = run(inputs, every_file)
    aff_rounds = {
        round_id(one) for one in inputs.disclosures if one.side is Side.AFF and one.snapshot <= inputs.through
    }
    assert {one.round_id for one in found.assignments} == aff_rounds
    LandscapeReportService().build(
        dataclasses.replace(inputs, aff_assignments=found.assignments), synthetic_staleness()
    )
