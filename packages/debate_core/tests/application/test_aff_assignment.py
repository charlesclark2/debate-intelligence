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
from datetime import date
from pathlib import Path

import pytest
import yaml

from debate_core.application.aff_assignment import (
    AffAssignmentCannotStart,
    AffAssignmentRun,
    AffAssignmentService,
    AffAssignmentSource,
    build_aff_assignments,
)
from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.parse_workers import InProcessParseRunner
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.landscape_report import LandscapeReportInputs, LandscapeReportService, round_id
from debate_core.application.plan_texts import PlanTextService
from debate_core.arguments.landscape.kritikal_aff import (
    KritikalAffConfig,
    KritikalFamily,
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
    PositionClassification,
    PositionRole,
)
from debate_core.domain.landscape_report import AffAssignment
from debate_core.domain.landscape_texts import TextForm
from debate_core.domain.style_profile import StructuralUnit
from debate_core.integrations.docx_parser import DebateDocxParser
from debate_core.integrations.landscape.classification_store import LocalClassificationStore
from debate_core.integrations.landscape.plan_text_store import LocalPlanTextStore
from debate_core.integrations.landscape.yaml_taxonomy_repository import YamlTaxonomyRepository
from debate_core.integrations.local import FsEvidenceObjectStore
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.local.suppression_list import local_suppression_list_file
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml
from debate_core.testing.landscape_report import read_synthetic_caselist, synthetic_staleness
from debate_core.testing.landscape_store import PlantedCard, PlantedCaselist

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


# ------------------------------------------------------------------------------------------------
# The producer v1-e32-t05 takes: assignments for a caselist and a through date
# ------------------------------------------------------------------------------------------------

PRODUCER_CASELIST = "hspolicy99"
PRODUCER_TOPICS = f"""\
schema_version: 1
topics:
  - id: policy-sample-topic
    event: POLICY
    taxonomy_version: 1.0.0
    caselists:
      - {{caselist: {PRODUCER_CASELIST}, from: 2026-09-01, to: 2026-12-31}}
"""
PRODUCER_TAXONOMY = """\
schema_version: 1
topic_id: policy-sample-topic
taxonomy_version: 1.0.0
event: POLICY
positions:
  - {id: sample-plan-aff, label: Sample plan, kind: aff, side: aff, aliases: [sample plan]}
  - {id: national-plan-aff, label: National plan, kind: aff, side: aff}
  - {id: kritikal-aff, label: Kritikal affirmative, kind: aff, side: aff}
  - {id: spending-da, label: Spending DA, kind: da, side: neg, aliases: [spending da]}
"""
PRODUCER_PLAN_WORDS = """\
schema_version: 1
topic_id: policy-sample-topic
position_id: national-plan-aff
frame_words: [establish, federal, government, should, states, united]
resolutional_words: [national, program, route, using, voucher]
"""
NAMED = "The United States federal government should establish a sample plan financed by a payroll levy."
UNNAMED = "The United States federal government should establish a national program using a voucher route."


PRODUCER_KRITIKAL = """\
schema_version: 1
topic_id: policy-sample-topic
position_id: kritikal-aff
families:
  - {id: cap, label: Capitalism, phrases: [cap, capitalism]}
"""
KRITIKAL_FILE = "a K-aff file: an advocacy statement and no plan text"


def _plan_file(plan: str | None) -> bytes:
    if plan == KRITIKAL_FILE:
        return build_docx(
            paragraph_xml(run_xml("1AC - Capitalism"), style="Heading2")
            + paragraph_xml(run_xml("Advocacy"), style="Heading3")
            + paragraph_xml(run_xml("We affirm an invented refusal."), style="Analytic")
        )

    if plan is None:
        return build_docx(paragraph_xml(run_xml("Advantage One"), style="Heading3"))
    return build_docx(
        paragraph_xml(run_xml("Plan"), style="Heading3") + paragraph_xml(run_xml(plan), style="Analytic")
    )


def _disclosure_path(school: str, side: str, round_number: int) -> str:
    file = f"School {school}-Code{school}-{side}-Sample Invitational-Round {round_number}.docx"
    return f"School {school}/Code{school}/{file}"


def producer(
    tmp_path: Path,
    *,
    plan_words: str | None = None,
    extra: tuple[tuple[str, str | None], ...] = (),
    kritikal: str | None = None,
) -> AffAssignmentService:
    """The service over a planted data directory; `plan_words` is the topic's plan-text file.

    `extra` plants more affirmative rounds, each a school and its plan text.
    """

    data_dir = tmp_path / "data"
    store = PlantedCaselist(data_dir, PRODUCER_CASELIST)
    planted = [
        ("Two", NAMED),
        ("Three", NAMED),
        ("Six", NAMED),
        ("Four", UNNAMED),
        ("Five", UNNAMED),
        ("Two", None),
        *extra,
    ]
    for number, (school, plan) in enumerate(planted, start=1):
        store.source(
            f"aff-{number}",
            [PlantedCard(("1AC", "Advantage One"))],
            disclosures=[("2026-09-15", _disclosure_path(school, "Aff", number))],
            content=_plan_file(plan),
        )
    store.source(
        "neg",
        [PlantedCard(("1NC", "Spending DA"))],
        disclosures=[("2026-09-15", _disclosure_path("One", "Neg", 1))],
    )
    config_dir = tmp_path / "config"
    (config_dir / "taxonomies").mkdir(parents=True)
    (config_dir / "topics.yaml").write_text(PRODUCER_TOPICS, encoding="utf-8")
    (config_dir / "taxonomies" / "policy-sample-topic.yaml").write_text(PRODUCER_TAXONOMY, encoding="utf-8")
    if plan_words is not None:
        (config_dir / "plan_texts").mkdir()
        (config_dir / "plan_texts" / "policy-sample-topic.yaml").write_text(plan_words, encoding="utf-8")
    if kritikal is not None:
        (config_dir / "kritikal_affs").mkdir()
        (config_dir / "kritikal_affs" / "policy-sample-topic.yaml").write_text(kritikal, encoding="utf-8")
    objects = FsEvidenceObjectStore(data_dir)
    blobs = FsEvidenceObjectStore(data_dir, subdirectory=Path("blobs"))
    local = LocalEvidence(
        objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
    )
    return AffAssignmentService(
        store=LocalParsedStore(data_dir),
        local=local,
        suppression=RecordedSuppressionList(local_suppression_list_file(data_dir)),
        taxonomies=YamlTaxonomyRepository.load(config_dir),
        classifications=LocalClassificationStore(data_dir),
        plan_texts=PlanTextService(
            parser=DebateDocxParser(),
            runner=InProcessParseRunner(),
            store=LocalPlanTextStore(data_dir),
            local=local,
        ),
    )


@pytest.mark.anyio
async def test_the_producer_returns_assignments_for_a_caselist_and_a_through_date(tmp_path: Path) -> None:

    service = producer(tmp_path)
    assert isinstance(service, AffAssignmentSource)
    found = await service.aff_assignments(PRODUCER_CASELIST, date(2026, 9, 29))
    assert sorted(one.method for one in found) == ["PLAN_TEXT", "PLAN_TEXT", "PLAN_TEXT", "TEAM_CARRY"]
    assert {one.position_id for one in found} == {"sample-plan-aff"}
    assert len({one.round_id for one in found}) == 4
    counts = (await service.run(PRODUCER_CASELIST, date(2026, 9, 29))).counts
    assert (counts.rounds, counts.unidentified, counts.placed_only) == (6, 2, 0)


@pytest.mark.anyio
async def test_the_producer_names_the_resolutional_aff_from_the_topics_plan_text_file(tmp_path: Path) -> None:

    service = producer(tmp_path, plan_words=PRODUCER_PLAN_WORDS)
    found = await service.aff_assignments(PRODUCER_CASELIST, date(2026, 9, 29))
    assert sorted((one.method, one.position_id) for one in found) == [
        ("PLAN_TEXT", "national-plan-aff"),
        ("PLAN_TEXT", "national-plan-aff"),
        ("PLAN_TEXT", "sample-plan-aff"),
        ("PLAN_TEXT", "sample-plan-aff"),
        ("PLAN_TEXT", "sample-plan-aff"),
        ("TEAM_CARRY", "sample-plan-aff"),
    ]


@pytest.mark.anyio
async def test_the_producer_carries_the_other_aff_of_a_team_that_also_reads_the_resolutional_one(
    tmp_path: Path,
) -> None:

    service = producer(tmp_path, plan_words=PRODUCER_PLAN_WORDS, extra=(("Four", NAMED), ("Four", None)))
    found = await service.aff_assignments(PRODUCER_CASELIST, date(2026, 9, 29))
    assert sorted((one.method, one.position_id) for one in found) == [
        ("PLAN_TEXT", "national-plan-aff"),
        ("PLAN_TEXT", "national-plan-aff"),
        ("PLAN_TEXT", "sample-plan-aff"),
        ("PLAN_TEXT", "sample-plan-aff"),
        ("PLAN_TEXT", "sample-plan-aff"),
        ("PLAN_TEXT", "sample-plan-aff"),
        ("TEAM_CARRY", "sample-plan-aff"),
        ("TEAM_CARRY", "sample-plan-aff"),
    ]


@pytest.mark.anyio
async def test_the_producer_reads_the_topics_k_aff_config_and_carries_the_k_aff(tmp_path: Path) -> None:
    service = producer(
        tmp_path, kritikal=PRODUCER_KRITIKAL, extra=(("Seven", KRITIKAL_FILE), ("Seven", None))
    )
    run = await service.run(PRODUCER_CASELIST, date(2026, 9, 29))
    assert sorted(
        (one.method, one.position_id) for one in run.assignments if one.position_id == "kritikal-aff"
    ) == [
        ("KRITIKAL_AFF_CARRY", "kritikal-aff"),
        ("KRITIKAL_AFF_MARKER", "kritikal-aff"),
    ]
    assert run.kritikal is not None
    assert (len(run.kritikal.marker_sources), set(run.kritikal.heading_families.values())) == (1, {("cap",)})
    without = await producer(tmp_path / "plain", extra=(("Seven", KRITIKAL_FILE), ("Seven", None))).run(
        PRODUCER_CASELIST, date(2026, 9, 29)
    )
    assert "kritikal-aff" not in {one.position_id for one in without.assignments}
    assert without.kritikal is None


@pytest.mark.anyio
async def test_the_producer_reads_nothing_disclosed_after_the_through_date(tmp_path: Path) -> None:

    found = await producer(tmp_path).aff_assignments(PRODUCER_CASELIST, date(2026, 9, 10))
    assert found == ()


@pytest.mark.anyio
async def test_the_producer_refuses_a_date_on_no_topic_with_a_taxonomy(tmp_path: Path) -> None:

    with pytest.raises(AffAssignmentCannotStart):
        await producer(tmp_path).aff_assignments(PRODUCER_CASELIST, date(2027, 3, 1))


# ------------------------------------------------------------------------------------------------
# Kritikal affirmatives (`v1-e32-t17`)
# ------------------------------------------------------------------------------------------------
#
# Over `tests/fixtures/landscape/kritikal_affs/`: its rounds and cards, every file with no plan text but
# d1's, which names single payer, and the fixture's marker files and heading families as the K-aff
# reading. The rule gives the assignments and the refusal the fixture's README table gives by hand.

KRITIKAL_FIXTURE = REPO / "tests" / "fixtures" / "landscape" / "kritikal_affs"
KRITIKAL_CONFIG = KritikalAffConfig(
    topic_id="synthetic-policy-topic",
    position_id="kritikal-aff",
    families=(
        KritikalFamily(id="cap", label="Capitalism", phrases=("cap",)),
        KritikalFamily(id="settler-colonialism", label="Settler colonialism", phrases=("set col",)),
        KritikalFamily(id="afropessimism", label="Afropessimism", phrases=("afropessimism",)),
        KritikalFamily(id="feminism", label="Feminism", phrases=("feminism",)),
        KritikalFamily(id="queer", label="Queer theory", phrases=("queer",)),
    ),
)


def _kritikal_world() -> tuple[list[Disclosure], list[PositionClassification], Taxonomy, dict[str, str]]:
    table = yaml.safe_load((KRITIKAL_FIXTURE / "rounds.yaml").read_text(encoding="utf-8"))
    taxonomy = Taxonomy.model_validate(
        yaml.safe_load((KRITIKAL_FIXTURE / "taxonomy.yaml").read_text(encoding="utf-8"))
    )
    school_of = {code: school for school, codes in table["schools"].items() for code in codes}
    disclosures: list[Disclosure] = []
    names: dict[str, str] = {}
    for row in table["rounds"]:
        school, code, side = school_of[row["team"]], row["team"], Side(row["side"])
        for name in row["files"]:
            disclosures.append(
                Disclosure(
                    caselist="synthpolicy26",
                    event=Event.POLICY,
                    school=school,
                    team_code=code,
                    side=side,
                    tournament=row["tournament"],
                    round_label=RoundLabel(raw=row["round"], normalized=row["round"]),
                    snapshot=date(2026, 9, 15),
                    source_path=f"{school}/{school} {code}/{code}-{side.value}-{row['round']}-{name}.docx",
                    source_sha256=name * 32,
                )
            )
        names[f"{row['team']} {row['tournament']} {row['side']}"] = round_id(disclosures[-1])
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
        for name, cards in table["files"].items()
        for index, position in enumerate(cards)
    ]
    return disclosures, classifications, taxonomy, names


def _kritikal_run(
    *, kritikal: KritikalAffConfig | None = KRITIKAL_CONFIG, below_threshold: bool = False
) -> tuple[AffAssignmentRun, dict[str, str]]:
    disclosures, classifications, taxonomy, names = _kritikal_world()
    if below_threshold:
        classifications = [
            one.model_copy(update={"confidence": 0.5}) if one.position_id == "costs-advantage" else one
            for one in classifications
        ]
    table = yaml.safe_load((KRITIKAL_FIXTURE / "rounds.yaml").read_text(encoding="utf-8"))["kritikal"]
    marker = KritikalMarker(KritikalMarkerKind.ROLE_OF_THE_BALLOT, TextForm.SENTENCE, 3, StructuralUnit.TAG)
    readings = {
        one.source_sha256: KritikalReading(
            markers=(marker,) if one.source_sha256[:2] in table["marker_files"] else (),
            heading_families=tuple(table["heading_families"].get(one.source_sha256[:2], ())),
        )
        for one in disclosures
    }
    plan_texts = {
        one.source_sha256: DocumentPlanText(PlanTextVerdict.NAMES, SINGLE_PAYER)
        if one.source_sha256.startswith("d1")
        else DocumentPlanText(PlanTextVerdict.NONE)
        for one in disclosures
    }
    found = build_aff_assignments(
        disclosures=disclosures,
        through=date(2026, 9, 15),
        classifications=classifications,
        plan_texts=plan_texts,
        taxonomy=taxonomy,
        kritikal=kritikal,
        kritikal_readings=readings,
    )
    return found, names


def test_kritikal_the_rule_gives_the_fixtures_assignments_and_refusal() -> None:
    found, names = _kritikal_run()
    assert {(one.round_id, one.position_id, one.method) for one in found.assignments} == {
        (names["AA Fictional Invitational AFF"], "kritikal-aff", "KRITIKAL_AFF_MARKER"),
        (names["AA Imaginary Classic AFF"], "kritikal-aff", "KRITIKAL_AFF_CARRY"),
        (names["BB Fictional Invitational AFF"], "kritikal-aff", "KRITIKAL_AFF_MARKER"),
        (names["CC Fictional Invitational AFF"], SINGLE_PAYER, "PLAN_TEXT"),
    }
    assert found.counts.refused_by_advantage == (names["AA Pretend Open AFF"],)
    assert (found.counts.placed_only, found.counts.unidentified) == (1, 2)


def test_kritikal_the_report_inputs_hold_the_marker_files_families_and_refusals() -> None:
    found, names = _kritikal_run()
    assert found.kritikal is not None
    assert found.kritikal.position_id == "kritikal-aff"
    assert found.kritikal.marker_sources == {name * 32 for name in ("c1", "c4", "d1", "e1", "f1")}
    assert found.kritikal.heading_families["c1" * 32] == ("cap", "settler-colonialism")
    assert "c2" * 32 in found.kritikal.heading_families and "e1" * 32 not in found.kritikal.heading_families
    assert list(found.kritikal.families) == [
        "cap",
        "settler-colonialism",
        "afropessimism",
        "feminism",
        "queer",
    ]
    assert found.kritikal.refused_by_advantage == {names["AA Pretend Open AFF"]}


def test_kritikal_an_advantage_placed_below_the_threshold_does_not_stop_the_carry() -> None:
    found, names = _kritikal_run(below_threshold=True)
    assert (names["AA Pretend Open AFF"], "kritikal-aff", "KRITIKAL_AFF_CARRY") in {
        (one.round_id, one.position_id, one.method) for one in found.assignments
    }
    assert found.counts.refused_by_advantage == ()


def test_kritikal_without_a_config_no_round_is_a_k_aff_and_there_are_no_inputs() -> None:
    found, _ = _kritikal_run(kritikal=None)
    assert {one.method for one in found.assignments} == {"PLAN_TEXT"}
    assert found.kritikal is None
