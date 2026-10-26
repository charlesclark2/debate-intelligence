"""Affs identified by a plan text under a transition label, in the report (`v1-e32-t24` ac2).

Over `tests/fixtures/landscape/transition_plan_affs/`, whose README holds the table every expected number
here was counted from by hand, and whose `method_table.md` was written by hand from it. The fixture's
readings go through the real assignment (`build_aff_assignments`), so the table checks the rule and the
report together: the new methods' rounds, the K-aff carries refused, and the control.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from debate_core.application.aff_assignment import AffAssignmentRun, build_aff_assignments
from debate_core.application.landscape_report import LandscapeReportInputs, LandscapeReportService
from debate_core.arguments.landscape.kritikal_aff import (
    KritikalAffConfig,
    KritikalMarker,
    KritikalMarkerKind,
    KritikalReading,
)
from debate_core.arguments.landscape.plan_text import DocumentPlanText, PlanTextVerdict
from debate_core.domain.caselist import Disclosure, Event, RoundLabel, Side
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import (
    ClassificationMethod,
    ItemKind,
    OverrideRules,
    PositionClassification,
    PositionRole,
)
from debate_core.domain.landscape_report import LandscapeReport
from debate_core.domain.landscape_texts import TextForm
from debate_core.domain.style_profile import StructuralUnit
from debate_core.testing.landscape_report import SYNTHETIC_CASELIST, synthetic_staleness

FIXTURE = Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "landscape" / "transition_plan_affs"
SNAPSHOT = date(2026, 9, 15)
_VERDICTS = {one.value: one for one in PlanTextVerdict}


def _verdict(value: str) -> DocumentPlanText:
    if value in _VERDICTS:
        return DocumentPlanText(_VERDICTS[value])
    return DocumentPlanText(PlanTextVerdict.NAMES, value)


def _run(*, with_transition: bool = True) -> tuple[AffAssignmentRun, LandscapeReportInputs]:
    """The fixture's rounds and readings, assigned by the real rule, and the report's inputs from them.

    Without the transition readings, as a run before this task: no plan text under `Thus` is read."""
    table: dict[str, Any] = yaml.safe_load((FIXTURE / "rounds.yaml").read_text(encoding="utf-8"))
    taxonomy = Taxonomy.model_validate(
        yaml.safe_load((FIXTURE / "taxonomy.yaml").read_text(encoding="utf-8"))
    )
    school_of = {code: school for school, codes in table["schools"].items() for code in codes}
    disclosures = [
        Disclosure(
            caselist=SYNTHETIC_CASELIST,
            event=Event.POLICY,
            school=school_of[row["team"]],
            team_code=row["team"],
            side=Side(row["side"]),
            tournament=row["tournament"],
            round_label=RoundLabel(raw=row["round"], normalized=row["round"]),
            snapshot=SNAPSHOT,
            source_path=f"{school_of[row['team']]}/{row['team']}-{row['side']}-{row['round']}-{name}.docx",
            source_sha256=name * 32,
        )
        for row in table["rounds"]
        for name in row["files"]
    ]
    files: dict[str, dict[str, Any]] = table["files"]
    classifications = [
        PositionClassification(
            item_id=f"{name * 32}:card:{index}",
            item_kind=ItemKind.CARD,
            source_sha256=name * 32,
            first_element_index=index,
            position_id=position,
            role=PositionRole.READS,
            method=ClassificationMethod.ALIAS,
            confidence=1.0,
            rationale="synthetic fixture: placed as the fixture table says",
            taxonomy_version=taxonomy.taxonomy_version,
            prompt_version="none",
        )
        for name, found in files.items()
        for index, position in enumerate(found.get("cards", ()))
    ]
    marker = KritikalMarker(
        kind=KritikalMarkerKind.METHOD, form=TextForm.SENTENCE, element_index=0, unit=StructuralUnit.TAG
    )
    run = build_aff_assignments(
        disclosures=disclosures,
        through=SNAPSHOT,
        classifications=classifications,
        plan_texts={name * 32: _verdict(found["t09"]) for name, found in files.items()},
        taxonomy=taxonomy,
        kritikal=KritikalAffConfig(topic_id=taxonomy.topic_id, position_id=table["kritikal_position"]),
        kritikal_readings={
            name * 32: KritikalReading(markers=(marker,) if found.get("marker") else ())
            for name, found in files.items()
        },
        transition_plan_texts={
            name * 32: _verdict(found.get("thus", "NONE")) for name, found in files.items()
        }
        if with_transition
        else None,
    )
    inputs = LandscapeReportInputs(
        caselist=SYNTHETIC_CASELIST,
        through=SNAPSHOT,
        taxonomy=taxonomy,
        overrides=OverrideRules(topic_id=taxonomy.topic_id, overrides=()),
        parser_version="2026.10.20-docx-6",
        classifications=classifications,
        disclosures=disclosures,
        cards=(),
        aff_assignments=run.assignments,
        kritikal_affs=run.kritikal,
        transition_plans=run.transition,
    )
    return run, inputs


def _report(inputs: LandscapeReportInputs) -> LandscapeReport:
    return LandscapeReportService().build(inputs, synthetic_staleness())


def _method_table(inputs: LandscapeReportInputs) -> str:
    report_md = LandscapeReportService().bundle(inputs, synthetic_staleness()).files["report.md"]
    start = report_md.index("How affirmative rounds were identified:\n")
    end = report_md.index("not read this season.\n", start) + len("not read this season.\n")
    return report_md[start:end]


def test_the_method_table_matches_the_hand_written_golden_file() -> None:
    assert _method_table(_run()[1]) == (FIXTURE / "method_table.md").read_text(encoding="utf-8")


def test_the_new_methods_rounds_are_counted_with_the_others() -> None:
    report = _report(_run()[1])
    assert {one.method: one.rounds for one in report.aff_identification} == {
        "KRITIKAL_AFF_CARRY": 1,
        "KRITIKAL_AFF_MARKER": 2,
        "PLAN_TEXT": 2,
        "TEAM_CARRY": 1,
        "TRANSITION_PLAN_CARRY": 1,
        "TRANSITION_PLAN_TEXT": 3,
    }
    assert (report.unclassified.aff_rounds, report.unclassified.aff_rounds_unidentified) == (13, 3)


def test_the_refused_k_aff_carries_and_the_control_by_method() -> None:
    found = _report(_run()[1]).transition_plans
    assert found is not None
    assert (found.refused_kritikal_carry, found.control_rounds) == (1, 3)
    assert found.control_by_method == {"KRITIKAL_AFF_MARKER": 1, "PLAN_TEXT": 1, "TEAM_CARRY": 1}


def test_a_round_whose_own_plan_text_names_another_aff_keeps_it() -> None:
    run, _ = _run()
    methods = {one.method for one in run.assignments if one.position_id == "public-option-aff"}
    assert methods == {"PLAN_TEXT", "TEAM_CARRY"}
    assert sum(one.position_id == "public-option-aff" for one in run.assignments) == 3


def test_the_advantage_guard_s_row_counts_only_rounds_still_unidentified() -> None:
    found = _report(_run()[1]).kritikal_affs
    assert found is not None
    assert (found.rounds, found.by_marker, found.by_carry, found.refused_by_advantage) == (3, 2, 1, 0)


def test_without_transition_readings_there_are_no_new_rounds_and_no_new_rows() -> None:
    run, inputs = _run(with_transition=False)
    assert run.transition is None
    assert not {one.method for one in run.assignments} & {"TRANSITION_PLAN_TEXT", "TRANSITION_PLAN_CARRY"}
    report = _report(inputs)
    assert report.transition_plans is None
    table = _method_table(inputs)
    assert "under `Thus`" not in table
    assert re.search(r"\| Not identified \| 6 \|", table)
