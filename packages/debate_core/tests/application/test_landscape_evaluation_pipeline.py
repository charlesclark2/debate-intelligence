"""The evaluation scored as students meet it, through the service's own path (`v1-e32-t43` ac1).

Nine invented cards in one source, labelled by hand, asked about through the real prompt over a scripted
model, and placed by stage one with the topic's taxonomy and the coach's overrides. By hand, from the
table (stage one: `States CP` and `Spending DA` are aliases, placed surely and never sent; `Theory` is
overridden to no position; the rest are unplaced and sent):

| Row | Tag | Headings | Label (also) | Stage one | The model answers | Pipeline |
|---|---|---|---|---|---|---|
| 1 | Fed key | States CP | states-cp | states-cp | spending-da 0.9 | headings: correct |
| 2 | Deficits rise | Spending DA | spending-da | spending-da | no position | headings: correct |
| 3 | Court clog | States CP | election-da | states-cp | election-da 0.9 | headings: wrong |
| 4 | Bad framing | Theory | none | decided none | spending-da 0.7 | decided none |
| 5 | Midterms shift | Politics | election-da | unplaced | election-da 0.9 | model: correct |
| 6 | Rural hospitals close | Solvency | rural-adv | unplaced | no position | model: refused |
| 7 | Recession | Econ | spending-da | unplaced | spending-da 0.4 | model: below |
| 8 | Cliff nears | Impacts | spending-da (election-da) | unplaced | election-da 0.8 | model: correct |
| 9 | Util good | Spending DA | none | spending-da | no position | headings: wrong |

The model alone: counted 1, 3, 4, 5, 8 (5), correct 3, 5, 8 (3), refused 2, 6, 9 (3), below 7 (1).
The pipeline: counted 1, 2, 3, 9 by the headings and 5, 8 by the model (6), correct 1, 2, 5, 8 (4), refused
6 (1), below 7 (1), decided none 4 (1).
"""

from __future__ import annotations

import dataclasses
import hashlib
import io
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.landscape_model_evaluation import (
    TARGET_ACCURACY,
    FormatEvaluation,
    LabelledCard,
    LandscapeModelEvaluationService,
    break_down_labelled_cards,
    evaluate_labelled_cards,
)
from debate_core.application.landscape_model_stage import ModelClassificationStage, ParsedStoreCardTexts
from debate_core.application.landscape_seeding import SeedReading
from debate_core.application.ports.parsed_store import OCCURRENCES_NAME, PARSED_PREFIX
from debate_core.application.structured_output import StructuredOutputGuard
from debate_core.arguments.landscape.evaluation_breakdown import LabelledScore
from debate_core.arguments.landscape.seeding import SeedCard, SeedSource, SeedTeam
from debate_core.domain.caselist import Side
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import OverrideRules, card_item_id
from debate_core.domain.model_contracts import ModelParams, ModelPrompt, ModelResponse, TaskClass
from debate_core.integrations.landscape.yaml_taxonomy_repository import (
    YamlTaxonomyRepository,
    render_override_file,
)
from debate_core.integrations.local import BLOB_DIRECTORY, FsEvidenceObjectStore
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.local.suppression_list import local_suppression_list_file
from debate_core.integrations.models.prompt_registry import PromptRegistry
from debate_core.testing.fakes.model_router import ScriptedModelRouter
from debate_core.testing.fakes.parsed_store import InMemoryParsedStore
from debate_core.testing.landscape_run import SYNTHETIC_RUN_CASELIST, SYNTHETIC_RUN_TOPIC, plant_synthetic_run
from debate_core.testing.landscape_store import PARSER_VERSION

REPOSITORY = Path(__file__).resolve().parents[4]
SHA = "f" * 64
TOPIC = "policy-sample-topic"

TAXONOMY = Taxonomy.model_validate(
    {
        "topic_id": TOPIC,
        "taxonomy_version": "1.0.0",
        "event": "POLICY",
        "positions": [
            {"id": "medicare-aff", "label": "Medicare Aff", "kind": "aff", "side": "aff"},
            {
                "id": "rural-adv",
                "label": "Rural Hospitals Advantage",
                "kind": "advantage",
                "side": "aff",
                "parent": "medicare-aff",
            },
            {
                "id": "spending-da",
                "label": "Spending DA",
                "kind": "da",
                "side": "neg",
                "aliases": ["spending da"],
            },
            {"id": "election-da", "label": "Election DA", "kind": "da", "side": "neg"},
            {"id": "states-cp", "label": "States CP", "kind": "cp", "side": "neg", "aliases": ["states cp"]},
        ],
    }
)
OVERRIDES = OverrideRules.model_validate(
    {"topic_id": TOPIC, "overrides": [{"heading": "theory", "position_id": None}]}
)
NO_OVERRIDES = OverrideRules.model_validate({"topic_id": TOPIC, "overrides": []})

# (row, tag, headings, label, second label, the model's answer)
CARDS: tuple[tuple[int, str, str, str, str | None, tuple[str | None, float]], ...] = (
    (1, "Fed key", "States CP", "states-cp", None, ("spending-da", 0.9)),
    (2, "Deficits rise", "Spending DA", "spending-da", None, (None, 0.9)),
    (3, "Court clog", "States CP", "election-da", None, ("election-da", 0.9)),
    (4, "Bad framing", "Theory", "none", None, ("spending-da", 0.7)),
    (5, "Midterms shift", "Politics", "election-da", None, ("election-da", 0.9)),
    (6, "Rural hospitals close", "Solvency", "rural-adv", None, (None, 0.9)),
    (7, "Recession", "Econ", "spending-da", None, ("spending-da", 0.4)),
    (8, "Cliff nears", "Impacts", "spending-da", "election-da", ("election-da", 0.8)),
    (9, "Util good", "Spending DA", "none", None, (None, 0.8)),
)
ANSWERS = {tag.lower(): answer for _, tag, _, _, _, answer in CARDS}

SOURCE = SeedSource(
    sha256=SHA,
    teams=(
        SeedTeam(
            identity="birch/mn",
            side=Side.NEG,
            names=("Birch Hollow", "MN", "Pinecrest Invitational"),
            tournament="Pinecrest Invitational",
        ),
    ),
    cards=tuple(
        SeedCard(tag=tag, section_path=(heading,), first_element_index=3 * index)
        for index, (_, tag, heading, _, _, _) in enumerate(CARDS)
    ),
)
READING = SeedReading(
    caselist="hspolicy99",
    version="2026.10.20-docx-6",
    topic_id=TOPIC,
    entries=1,
    parsed=1,
    parsed_off_topic=0,
    sources=(SOURCE,),
    caselist_names={"Birch Hollow": ("MN",)},
)
LABELLED = {
    row: LabelledCard(card_item_id(SHA, 3 * index), label, sample_row=row, also=also)
    for index, (row, _, _, label, also, _) in enumerate(CARDS)
}


class AnswersByTag(ScriptedModelRouter):
    def __init__(self) -> None:
        super().__init__(model_id="recorded-model")

    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        items: list[dict[str, Any]] = json.loads(str(prompt.variables["items"]))
        self.enqueue(
            {
                "answers": [
                    {
                        "item": item["item"],
                        "position_id": ANSWERS[item["tag"]][0],
                        "confidence": ANSWERS[item["tag"]][1],
                        "rationale": "a reason in the model's words",
                    }
                    for item in items
                ]
            }
        )
        return await super().generate_structured(task_class, prompt, schema, params)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="module")
def prompts() -> PromptRegistry:
    return PromptRegistry.load(REPOSITORY / "prompts")


def stage(registry: PromptRegistry) -> ModelClassificationStage:
    return ModelClassificationStage(
        StructuredOutputGuard(AnswersByTag(), registry), ParsedStoreCardTexts(InMemoryParsedStore())
    )


async def evaluated(
    registry: PromptRegistry, rows: Sequence[int], overrides: OverrideRules = OVERRIDES
) -> FormatEvaluation:
    labelled = [LABELLED[row] for row in rows]
    return await evaluate_labelled_cards(READING, TAXONOMY, labelled, stage(registry), overrides=overrides)


@pytest.mark.anyio
async def test_evaluation_reports_the_pipelines_score_beside_the_models_own(prompts: PromptRegistry) -> None:
    result = await evaluated(prompts, list(LABELLED))

    assert result.model_alone == LabelledScore(labelled=9, counted=5, correct=3, refused=3, below_threshold=1)
    assert result.pipeline == LabelledScore(
        labelled=9, counted=6, correct=4, refused=1, below_threshold=1, by_headings=4, decided_none=1
    )
    assert (result.counted, result.correct, result.placed_below_threshold, result.placed_labelled_none) == (
        5,
        3,
        1,
        1,
    )


@pytest.mark.anyio
async def test_evaluation_pipeline_reads_the_coachs_overrides(prompts: PromptRegistry) -> None:
    """Without the `Theory` override, row 4 is unplaced and sent: the model's placement of it is counted,
    and wrong, since the coach labelled it none."""
    result = await evaluated(prompts, list(LABELLED), overrides=NO_OVERRIDES)

    assert result.pipeline == LabelledScore(
        labelled=9, counted=7, correct=4, refused=1, below_threshold=1, by_headings=4, decided_none=0
    )


@pytest.mark.anyio
async def test_evaluation_bar_reads_the_pipeline_when_only_the_pipeline_meets_it(
    prompts: PromptRegistry,
) -> None:
    """Rows 1, 2, 5, 8: the model alone counts 1, 5, 8 and is right on 5 and 8 (2 of 3); the pipeline is right
    on all four, rows 1 and 2 by the headings."""
    result = await evaluated(prompts, [1, 2, 5, 8])

    assert (result.model_alone.correct, result.model_alone.counted) == (2, 3)
    assert (result.pipeline.correct, result.pipeline.counted) == (4, 4)
    assert result.meets_target


@pytest.mark.anyio
async def test_evaluation_bar_reads_the_pipeline_when_only_the_model_meets_it(
    prompts: PromptRegistry,
) -> None:
    """Rows 3 and 5: the model alone is right on both; the pipeline takes row 3's headings, and they are
    wrong."""
    result = await evaluated(prompts, [3, 5])

    assert (result.model_alone.correct, result.model_alone.counted) == (2, 2)
    assert (result.pipeline.correct, result.pipeline.counted) == (1, 2)
    assert not result.meets_target


def test_evaluation_meets_the_bar_on_the_pipelines_accuracy_alone() -> None:
    """The bar is 85%: a pipeline at 17 of 20 meets it whatever the model alone scored, 16 of 20 does not."""
    base = FormatEvaluation(
        caselist="hspolicy99",
        event="POLICY",
        topic_id=TOPIC,
        taxonomy_version="1.0.0",
        prompt_version="1.1.0",
        snapshot=None,
        labelled=20,
        found=20,
        asked=20,
        calls=1,
        counted=20,
        correct=10,
        placed_below_threshold=0,
        placed_labelled_none=0,
        model_alone=LabelledScore(labelled=20, counted=20, correct=10, refused=0, below_threshold=0),
    )
    meeting = LabelledScore(labelled=20, counted=20, correct=17, refused=0, below_threshold=0, by_headings=4)

    assert TARGET_ACCURACY == 0.85
    assert dataclasses.replace(base, pipeline=meeting).meets_target
    assert not dataclasses.replace(base, pipeline=dataclasses.replace(meeting, correct=16)).meets_target
    assert not dataclasses.replace(
        base,
        correct=20,
        model_alone=dataclasses.replace(base.model_alone, correct=20),
        pipeline=dataclasses.replace(meeting, correct=16),
    ).meets_target


@pytest.mark.anyio
async def test_evaluation_breakdown_scores_the_pipeline_as_the_evaluation_does(
    prompts: PromptRegistry,
) -> None:
    labelled = list(LABELLED.values())
    alone = await evaluate_labelled_cards(READING, TAXONOMY, labelled, stage(prompts), overrides=OVERRIDES)
    broken_down = await break_down_labelled_cards(READING, TAXONOMY, OVERRIDES, labelled, stage(prompts))

    assert broken_down.evaluation == alone
    assert broken_down.evaluation.pipeline.counted == 6


# ------------------------------------------------------------------------------------------------
# The service's own path: `synthetic26` (:mod:`debate_core.testing.landscape_run`), its stores and its
# config, with an overrides file deciding that `framing` names no position. Two cards labelled: the
# `Costs Advantage` card costs-advantage, which its alias heading places surely, and the `Framing` card
# none, which the model places under spending-da. By hand: with the coach's overrides the pipeline counts
# the costs card alone, right, and the framing card is decided none (1 of 1); without them the framing
# card is sent, and the model's placement of it is counted and wrong (1 of 2).
# ------------------------------------------------------------------------------------------------

SYNTHETIC_LABELLED = (
    ("Premiums are rising fast", "Delacroix 25", "costs-advantage"),
    ("Probability first", "Szabo 24", "none"),
)
SYNTHETIC_ANSWERS = {"premiums are rising fast": "costs-advantage", "probability first": "spending-da"}


class AnswersSyntheticCards(ScriptedModelRouter):
    def __init__(self) -> None:
        super().__init__(model_id="recorded-model")

    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        items: list[dict[str, Any]] = json.loads(str(prompt.variables["items"]))
        answers = [
            {
                "item": item["item"],
                "position_id": SYNTHETIC_ANSWERS[item["tag"]],
                "confidence": 0.9,
                "rationale": "the tag states the argument",
            }
            for item in items
        ]
        self.enqueue({"answers": answers})
        return await super().generate_structured(task_class, prompt, schema, params)


async def synthetic_evaluation(
    tmp_path: Path, registry: PromptRegistry, *, framing_override: bool
) -> FormatEvaluation:
    world = plant_synthetic_run(tmp_path / "world")
    if framing_override:
        rules = OverrideRules.model_validate(
            {"topic_id": SYNTHETIC_RUN_TOPIC, "overrides": [{"heading": "framing", "position_id": None}]}
        )
        (world.config_dir / "overrides").mkdir()
        (world.config_dir / "overrides" / f"{SYNTHETIC_RUN_TOPIC}.yaml").write_text(
            render_override_file(rules), encoding="utf-8"
        )
    table = world.data_dir / PARSED_PREFIX / SYNTHETIC_RUN_CASELIST / PARSER_VERSION / OCCURRENCES_NAME
    item_ids: dict[str, str] = {}
    for line in table.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        item_ids[record["exact_fingerprint"]] = card_item_id(
            record["source_sha256"], record["first_element_index"]
        )
    sample = ["sample_row,position"]
    rows = [json.dumps({"schema": "local-classifier-sample-1"})]
    for row, (tag, cite, label) in enumerate(SYNTHETIC_LABELLED, start=1):
        sample.append(f"{row},{label}")
        fingerprint = hashlib.sha256(f"{tag}|{cite}".encode()).hexdigest()
        rows.append(json.dumps({"sample_row": row, "item_id": item_ids[fingerprint]}))
    data_dir = world.data_dir
    objects = FsEvidenceObjectStore(data_dir)
    blobs = FsEvidenceObjectStore(data_dir, subdirectory=BLOB_DIRECTORY.parent)
    service = LandscapeModelEvaluationService(
        taxonomies=YamlTaxonomyRepository.load(world.config_dir),
        parsed_store=LocalParsedStore(data_dir),
        local=LocalEvidence(
            objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
        ),
        suppression=RecordedSuppressionList(local_suppression_list_file(data_dir)),
        objects=objects,
        stage=lambda max_items: ModelClassificationStage(
            StructuredOutputGuard(AnswersSyntheticCards(), registry),
            ParsedStoreCardTexts(LocalParsedStore(data_dir)),
            max_items=max_items,
        ),
        cassette_texts=lambda: (),
    )
    return await service.evaluate(
        SYNTHETIC_RUN_CASELIST,
        io.StringIO("\n".join(sample) + "\n"),
        rows,
        snapshot=date(2026, 9, 15),
    )


@pytest.mark.anyio
async def test_evaluation_service_scores_the_pipeline_with_the_topics_overrides(
    tmp_path: Path, prompts: PromptRegistry
) -> None:
    decided = await synthetic_evaluation(tmp_path / "decided", prompts, framing_override=True)
    sent = await synthetic_evaluation(tmp_path / "sent", prompts, framing_override=False)

    assert decided.pipeline == LabelledScore(
        labelled=2, counted=1, correct=1, refused=0, below_threshold=0, by_headings=1, decided_none=1
    )
    assert sent.pipeline == LabelledScore(
        labelled=2, counted=2, correct=1, refused=0, below_threshold=0, by_headings=1, decided_none=0
    )
    assert (
        decided.model_alone
        == sent.model_alone
        == LabelledScore(labelled=2, counted=2, correct=1, refused=0, below_threshold=0)
    )
