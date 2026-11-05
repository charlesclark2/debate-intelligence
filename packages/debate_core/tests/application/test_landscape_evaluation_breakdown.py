"""The evaluation broken down card by card (`v1-e32-t39`), recorded once and replayed with no model behind it.

One synthetic source of nine cards, one per batch, and a tenth labelled card the store does not hold. The
scripted model's answers, and so every card's outcome, the headings' placement beside it and each batch's
calls, are worked out by hand below from the taxonomy, the overrides and the answers. Every school, team,
tournament, heading, tag and rationale is invented.
"""

from __future__ import annotations

import dataclasses
import io
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from debate_core.application.errors import ProviderRateLimited
from debate_core.application.landscape_model_evaluation import (
    BATCH_ANSWERED,
    BATCH_REFUSED,
    BATCH_REPAIRED,
    EvaluationBreakdown,
    EvaluationRefused,
    LabelledCard,
    break_down_labelled_cards,
    coach_sample_counts,
    evaluate_labelled_cards,
    read_coach_sample,
    read_sample_populations,
)
from debate_core.application.landscape_model_stage import (
    CLASSIFY_POSITION_PROMPT_ID,
    ModelClassificationStage,
    ParsedStoreCardTexts,
)
from debate_core.application.landscape_seeding import SeedReading
from debate_core.application.structured_output import REPAIR_PROMPT_ID, StructuredOutputGuard
from debate_core.arguments.landscape.evaluation_breakdown import (
    CardOutcome,
    confusion,
    outcome_counts,
    outcomes_by_label_kind,
    refusals_by_label,
    second_label_counts,
    weighted_accuracy,
)
from debate_core.arguments.landscape.scan_hits import HitField, HitKind, ScanHit
from debate_core.arguments.landscape.seeding import SeedCard, SeedSource, SeedTeam
from debate_core.domain.caselist import Side
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import (
    ModelStancedPositionAnswers,
    OverrideRules,
    Stance,
    card_item_id,
)
from debate_core.domain.model_contracts import ModelParams, ModelPrompt, ModelResponse, TaskClass
from debate_core.integrations.models.errors import MissingFixtureError
from debate_core.integrations.models.model_mode import ModelMode
from debate_core.integrations.models.prompt_registry import PromptRegistry
from debate_core.integrations.models.record_replay import RecordReplayModelRouter
from debate_core.testing.fakes.model_router import ScriptedModelRouter
from debate_core.testing.fakes.parsed_store import InMemoryParsedStore

REPOSITORY = Path(__file__).resolve().parents[4]
SHA = "c" * 64
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
            {
                "id": "election-da",
                "label": "Election DA",
                "kind": "da",
                "side": "neg",
                "tag_keywords": ["midterms"],
            },
            {"id": "states-cp", "label": "States CP", "kind": "cp", "side": "neg", "aliases": ["states cp"]},
        ],
    }
)
OVERRIDES = OverrideRules.model_validate(
    {"topic_id": TOPIC, "overrides": [{"heading": "theory", "position_id": None}]}
)

# (tag, headings, the coach's label, sample row, stratum). Stage one, by hand: the `States CP` heading is
# an alias (ALIAS 1.0, not sent); `midterms` is election-da's tag keyword (TAG_KEYWORD 0.5, below the
# 0.6 threshold, sent); `Theory` is overridden to no position (decided, not sent); the rest are unplaced
# and sent. `harbor classic` is another team's tournament, which the scrub takes out of a tag since
# `v1-e32-t40` (it left it in before).
CARDS: tuple[tuple[str, tuple[str, ...], str, int, str], ...] = (
    ("Fed key", ("States CP",), "states-cp", 1, "top"),
    ("Cliff nears", ("Impacts",), "spending-da", 2, "rest"),
    ("Midterms shift", ("Politics",), "election-da", 3, "rest"),
    ("Rural hospitals close", ("Solvency",), "rural-adv", 4, "rest"),
    ("Util good", ("Framing",), "none", 5, "rest"),
    ("Recession", ("Econ",), "spending-da", 6, "top"),
    ("Bad framing", ("Theory",), "none", 7, "top"),
    ("Court clog Harbor Classic", ("Courts",), "states-cp", 8, "rest"),
    ("Lost card Harbor Classic", ("Misc",), "spending-da", 9, "rest"),
)
SOURCE = SeedSource(
    sha256=SHA,
    teams=(
        SeedTeam(
            identity="maple/ab",
            side=Side.NEG,
            names=("Maple Grove", "AB", "Lakeside Invitational"),
            tournament="Lakeside Invitational",
        ),
    ),
    cards=tuple(
        SeedCard(tag=tag, section_path=headings, first_element_index=3 * index)
        for index, (tag, headings, _, _, _) in enumerate(CARDS)
    ),
)
OTHER_SOURCE = SeedSource(
    sha256="e" * 64,
    teams=(
        SeedTeam(
            identity="cedar/kl",
            side=Side.AFF,
            names=("Cedar Ridge", "KL", "Harbor Classic"),
            tournament="Harbor Classic",
        ),
    ),
    cards=(),
)
READING = SeedReading(
    caselist="hspolicy99",
    version="2026.10.20-docx-6",
    topic_id=TOPIC,
    entries=2,
    parsed=2,
    parsed_off_topic=0,
    sources=(SOURCE, OTHER_SOURCE),
    caselist_names={"Maple Grove": ("AB",), "Cedar Ridge": ("KL",)},
)
NOT_HELD = LabelledCard(card_item_id("d" * 64, 0), "states-cp", sample_row=10, stratum="rest")
LABELLED = (
    *(
        LabelledCard(card_item_id(SHA, 3 * index), label, sample_row=row, stratum=stratum)
        for index, (_, _, label, row, stratum) in enumerate(CARDS)
    ),
    NOT_HELD,
)
POPULATIONS = {"top": 100, "rest": 300}

# The model's answers, by the tag as sent (words, the disclosing team's names out). `cliff nears` and
# `lost card` are first answered for an item the batch does not have; the repair answers
# the first rightly and the second wrongly again, so that batch is refused.
ANSWERS: dict[str, tuple[str | None, float]] = {
    "fed key": ("states-cp", 0.9),
    "cliff nears": ("election-da", 0.8),
    "midterms shift": ("states-cp", 0.7),
    "rural hospitals close": ("medicare-aff", 0.9),
    "util good": ("spending-da", 0.65),
    "recession": (None, 0.9),
    "bad framing": (None, 0.8),
    "court clog": ("states-cp", 0.4),
}
FAIL_FIRST = {"cliff nears", "lost card"}
FAIL_REPAIR = {"lost card"}
RATIONALES = {"util good": "as cedar ridge reads it"}
REPAIR_RATIONALES = {"cliff nears": "as maple grove reads it"}
"""The repair's rationale for a card, where it differs: a school in the repair cassette alone."""

# By sample row, by hand: (outcome, refusal, the model's answer, its batch's verdict, stage one's
# (position, method, sent to the model)).
EXPECTED: dict[
    int, tuple[CardOutcome, str | None, str | None, str | None, tuple[str | None, str | None, bool] | None]
] = {
    1: (CardOutcome.CORRECT, None, "states-cp", BATCH_ANSWERED, ("states-cp", "ALIAS", False)),
    2: (CardOutcome.WRONG_POSITION_SAME_KIND, None, "election-da", BATCH_REPAIRED, (None, None, True)),
    3: (CardOutcome.WRONG_KIND, None, "states-cp", BATCH_ANSWERED, ("election-da", "TAG_KEYWORD", True)),
    4: (CardOutcome.WRONG_KIND, None, "medicare-aff", BATCH_ANSWERED, (None, None, True)),
    5: (CardOutcome.PLACED_LABELLED_NONE, None, "spending-da", BATCH_ANSWERED, (None, None, True)),
    6: (CardOutcome.REFUSED, "NO_POSITION", None, BATCH_ANSWERED, (None, None, True)),
    7: (CardOutcome.REFUSED, "NO_POSITION", None, BATCH_ANSWERED, (None, "OVERRIDE", False)),
    8: (CardOutcome.BELOW_THRESHOLD, None, "states-cp", BATCH_ANSWERED, (None, None, True)),
    9: (CardOutcome.LOST_TO_FAILED_BATCH, None, None, BATCH_REFUSED, (None, None, True)),
    10: (CardOutcome.NOT_FOUND, None, None, None, None),
}


class ScriptedByTag(ScriptedModelRouter):
    """Answers each card by its tag; answers an item the batch lacks for the tags it is told to fail."""

    def __init__(self) -> None:
        super().__init__(model_id="recorded-model")

    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        repair = prompt.prompt_id == REPAIR_PROMPT_ID
        if repair:
            rendered = str(prompt.variables["failed_user"])
            tags = [tag for tag in (*ANSWERS, *FAIL_FIRST) if f'"tag": "{tag}"' in rendered]
            items: list[dict[str, Any]] = [{"item": "item-1", "tag": tags[0]}]
        else:
            items = json.loads(str(prompt.variables["items"]))
        answers: list[dict[str, Any]] = []
        for item in items:
            tag = item["tag"]
            fails = tag in (FAIL_REPAIR if repair else FAIL_FIRST)
            position, confidence = ANSWERS.get(tag, ("spending-da", 0.9))
            answers.append(
                {
                    "item": "item-9" if fails else item["item"],
                    "position_id": position,
                    "confidence": confidence,
                    "rationale": (REPAIR_RATIONALES if repair else RATIONALES).get(
                        tag, "a reason in the model's words"
                    ),
                    **({"stance": "reads"} if issubclass(schema, ModelStancedPositionAnswers) else {}),
                }
            )
        self.enqueue({"answers": answers})
        return await super().generate_structured(task_class, prompt, schema, params)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="module")
def prompts() -> PromptRegistry:
    return PromptRegistry.load(REPOSITORY / "prompts")


def stage_over(router: Any, registry: PromptRegistry) -> ModelClassificationStage:
    return ModelClassificationStage(
        StructuredOutputGuard(router, registry), ParsedStoreCardTexts(InMemoryParsedStore()), batch_size=1
    )


def texts_under(directory: Path) -> list[str]:
    return [path.read_text(encoding="utf-8") for path in sorted(directory.glob("*.json"))]


async def broken_down(router: Any, registry: PromptRegistry, cassettes: Path) -> EvaluationBreakdown:
    return await break_down_labelled_cards(
        READING,
        TAXONOMY,
        OVERRIDES,
        LABELLED,
        stage_over(router, registry),
        cassette_texts=lambda: texts_under(cassettes / CLASSIFY_POSITION_PROMPT_ID),
        repair_cassette_texts=lambda: texts_under(cassettes / REPAIR_PROMPT_ID),
        populations=POPULATIONS,
    )


@pytest.fixture
async def recorded_and_replayed(
    tmp_path: Path, prompts: PromptRegistry
) -> tuple[EvaluationBreakdown, EvaluationBreakdown]:
    recording = RecordReplayModelRouter(
        ScriptedByTag(), mode=ModelMode.RECORD, cassette_dir=tmp_path, environ={}
    )
    recorded = await broken_down(recording, prompts, tmp_path)
    replaying = RecordReplayModelRouter(None, mode=ModelMode.REPLAY, cassette_dir=tmp_path)
    return recorded, await broken_down(replaying, prompts, tmp_path)


@pytest.mark.anyio
async def test_evaluation_breakdown_gives_every_labelled_card_one_outcome_summing_to_the_labelled(
    recorded_and_replayed: tuple[EvaluationBreakdown, EvaluationBreakdown],
) -> None:
    for result in recorded_and_replayed:
        assert result.evaluation.labelled == len(result.cards) == 10
        assert sum(result.outcomes.values()) == 10
        assert result.outcomes == {
            "correct": 1,
            "wrong_stance": 0,
            "wrong_position_same_kind": 1,
            "wrong_kind": 2,
            "placed_labelled_none": 1,
            "refused": 2,
            "below_threshold": 1,
            "lost_to_failed_batch": 1,
            "not_asked": 0,
            "not_found": 1,
        }
        by_row = {card.sample_row: card for card in result.cards}
        assert {row: (card.outcome, card.refusal, card.answer) for row, card in by_row.items()} == {
            row: expected[:3] for row, expected in EXPECTED.items()
        }
        assert {card.sample_row for card in result.cards if card.related} == {4}
        assert refusals_by_label(result.cards) == {"NO_POSITION": {"none": 1, "position": 1}}


@pytest.mark.anyio
async def test_evaluation_breakdown_puts_each_cards_own_deterministic_placement_beside_it(
    recorded_and_replayed: tuple[EvaluationBreakdown, EvaluationBreakdown],
) -> None:
    for result in recorded_and_replayed:
        placed = {
            card.sample_row: None
            if card.deterministic is None
            else (card.deterministic.position_id, card.deterministic.method, card.deterministic.sent_to_model)
            for card in result.cards
        }
        assert placed == {row: expected[4] for row, expected in EXPECTED.items()}


@pytest.mark.anyio
async def test_evaluation_breakdown_agrees_with_the_evaluation_and_scores_the_model_set_alone(
    recorded_and_replayed: tuple[EvaluationBreakdown, EvaluationBreakdown], prompts: PromptRegistry
) -> None:
    """Counted 5 (rows 1-5), correct 1 (row 1); a run sends rows 2-6, 8 and 9, counted 4, correct 0."""
    for result in recorded_and_replayed:
        evaluation = result.evaluation
        assert (evaluation.counted, evaluation.correct, evaluation.placed_below_threshold) == (5, 1, 1)
        assert (evaluation.placed_labelled_none, evaluation.refused) == (
            1,
            {"BATCH_REFUSED": 1, "NO_POSITION": 2},
        )
        assert (evaluation.calls, evaluation.found, evaluation.asked) == (11, 9, 9)
        model_set = result.model_set
        assert (model_set.cards, model_set.counted, model_set.correct, model_set.accuracy) == (7, 4, 0, 0.0)
        assert evaluation.accuracy == 0.2


@pytest.mark.anyio
async def test_evaluation_breakdown_weighs_the_strata_by_their_populations(
    recorded_and_replayed: tuple[EvaluationBreakdown, EvaluationBreakdown],
) -> None:
    """top: rows 1, 6, 7 (3 labelled, 1 counted, 1 right) of 100; rest: 7 labelled, 4 counted, 0 right, of
    300. Weighted: (100/3 * 1) / (100/3 * 1 + 300/7 * 4) = 7/43, where the plain accuracy is 1/5."""
    _, result = recorded_and_replayed
    assert [
        (one.name, one.population, one.score.cards, one.score.counted, one.score.correct)
        for one in result.strata
    ] == [
        ("top", 100, 3, 1, 1),
        ("rest", 300, 7, 4, 0),
    ]
    assert weighted_accuracy(result.strata) == pytest.approx(7 / 43)


@pytest.mark.anyio
async def test_evaluation_breakdown_says_what_the_guard_did_with_each_batch(
    recorded_and_replayed: tuple[EvaluationBreakdown, EvaluationBreakdown],
) -> None:
    for result in recorded_and_replayed:
        verdicts = Counter((one.outcome, one.cards, one.calls) for one in result.batches)
        assert verdicts == {(BATCH_ANSWERED, 1, 1): 7, (BATCH_REPAIRED, 1, 2): 1, (BATCH_REFUSED, 1, 2): 1}
        by_number = {one.number: one for one in result.batches}
        batch_of = {card.sample_row: card.batch for card in result.cards}
        assert {row: by_number[batch].outcome for row, batch in batch_of.items() if batch is not None} == {
            row: expected[3] for row, expected in EXPECTED.items() if expected[3] is not None
        }
        repaired = by_number[batch_of[2] or 0]
        assert (dict(repaired.problems), repaired.error_count) == ({"missing_item": 1, "unknown_item": 1}, 2)
        refused = by_number[batch_of[9] or 0]
        assert (dict(refused.problems), refused.error_count) == ({"missing_item": 2, "unknown_item": 2}, 4)


def shown(hits: tuple[ScanHit, ...]) -> Counter[tuple[HitField, HitKind, str, bool]]:
    return Counter((hit.where, hit.kind, hit.matched, hit.team_name) for hit in hits)


@pytest.mark.anyio
async def test_evaluation_breakdown_lists_the_scans_hits_by_text_field_and_kind(
    recorded_and_replayed: tuple[EvaluationBreakdown, EvaluationBreakdown],
) -> None:
    """Since `v1-e32-t40` the scrub takes the tournament out of both tags, so no input batch has a hit. The
    school in a rationale is in its cassette, on the school list only (the third list holds tournaments),
    and the school in the repaired answer's rationale is in the repair cassette, which the evaluation's
    own scan now reads too."""
    _, result = recorded_and_replayed
    assert shown(result.sent_hits) == {}
    assert shown(result.cassette_hits) == {(HitField.RATIONALE, HitKind.SCHOOL, "cedar ridge", False): 1}
    assert result.repair_cassettes == 2
    assert shown(result.repair_hits) == {(HitField.RATIONALE, HitKind.SCHOOL, "maple grove", False): 1}
    # The evaluation's own scan counts the same texts the listing shows hits in.
    sent, cassettes, repairs = (
        result.evaluation.sent,
        result.evaluation.cassettes,
        result.evaluation.repair_cassettes,
    )
    assert (sent.texts, sent.schools, sent.team_codes, sent.other_names) == (9, 0, 0, 0)
    assert (cassettes.texts, cassettes.schools, cassettes.team_codes, cassettes.other_names) == (9, 1, 0, 0)
    assert (repairs.texts, repairs.schools, repairs.team_codes, repairs.other_names) == (2, 1, 0, 0)


@pytest.mark.anyio
async def test_evaluation_breakdown_reads_only_this_prompts_repairs_filed_under_the_caselist(
    tmp_path: Path, prompts: PromptRegistry
) -> None:
    """A repair cassette another caselist alone names, or of another prompt or version, is not listed."""
    recording = RecordReplayModelRouter(
        ScriptedByTag(), mode=ModelMode.RECORD, cassette_dir=tmp_path, environ={}
    )
    await broken_down(recording, prompts, tmp_path)
    [repair, _] = texts_under(tmp_path / REPAIR_PROMPT_ID)
    document = json.loads(repair)
    foreign = json.dumps({**document, "caselists": ["hspolicy98"]})
    variables = document["request"]["prompt"]["variables"]
    other_version = json.dumps(
        {
            **document,
            "request": {
                **document["request"],
                "prompt": {
                    **document["request"]["prompt"],
                    "variables": {**variables, "failed_prompt": f"{CLASSIFY_POSITION_PROMPT_ID}@0.9.0"},
                },
            },
        }
    )
    replaying = RecordReplayModelRouter(None, mode=ModelMode.REPLAY, cassette_dir=tmp_path)

    result = await break_down_labelled_cards(
        READING,
        TAXONOMY,
        OVERRIDES,
        LABELLED,
        stage_over(replaying, prompts),
        repair_cassette_texts=lambda: [*texts_under(tmp_path / REPAIR_PROMPT_ID), foreign, other_version],
    )

    assert result.repair_cassettes == 2


@pytest.mark.anyio
async def test_evaluation_breakdown_withholds_every_hits_words_from_its_repr(
    recorded_and_replayed: tuple[EvaluationBreakdown, EvaluationBreakdown],
) -> None:
    for result in recorded_and_replayed:
        shown = repr(result) + "".join(
            map(repr, (*result.sent_hits, *result.cassette_hits, *result.repair_hits))
        )
        assert "harbor" not in shown.casefold()
        assert "cedar" not in shown.casefold()
        assert "maple" not in shown.casefold()


@pytest.mark.anyio
async def test_evaluation_breakdown_replay_refuses_a_request_no_cassette_recorded(
    tmp_path: Path, prompts: PromptRegistry
) -> None:
    """A replay holds no model: the first unrecorded request fails, and nothing is sent anywhere."""
    replaying = RecordReplayModelRouter(None, mode=ModelMode.REPLAY, cassette_dir=tmp_path)

    with pytest.raises(MissingFixtureError):
        await broken_down(replaying, prompts, tmp_path)
    assert not any(tmp_path.rglob("*.json"))


class StopsAfterTwoCalls(ScriptedByTag):
    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        if len(self.calls) >= 2:
            raise ProviderRateLimited("bedrock", "recorded-model: ThrottlingException")
        return await super().generate_structured(task_class, prompt, schema, params)


@pytest.mark.anyio
async def test_evaluation_breakdown_counts_the_cards_a_stop_left_unasked(prompts: PromptRegistry) -> None:
    result = await break_down_labelled_cards(
        READING, TAXONOMY, OVERRIDES, LABELLED, stage_over(StopsAfterTwoCalls(), prompts)
    )

    assert sum(result.outcomes.values()) == 10
    assert result.outcomes["not_found"] == 1
    assert result.evaluation.unanswered == result.outcomes["not_asked"]
    answered = sum(one.cards for one in result.batches)
    assert 0 < answered < 9
    assert result.outcomes["not_asked"] == 9 - answered


@pytest.mark.anyio
async def test_evaluation_breakdown_scores_as_the_evaluation_does(
    prompts: PromptRegistry, tmp_path: Path
) -> None:
    recording = RecordReplayModelRouter(
        ScriptedByTag(), mode=ModelMode.RECORD, cassette_dir=tmp_path, environ={}
    )
    evaluated = await evaluate_labelled_cards(
        READING,
        TAXONOMY,
        LABELLED,
        stage_over(recording, prompts),
        overrides=OVERRIDES,
        cassette_texts=lambda: texts_under(tmp_path / CLASSIFY_POSITION_PROMPT_ID),
        repair_cassette_texts=lambda: texts_under(tmp_path / REPAIR_PROMPT_ID),
    )
    replaying = RecordReplayModelRouter(None, mode=ModelMode.REPLAY, cassette_dir=tmp_path)
    result = await broken_down(replaying, prompts, tmp_path)

    assert result.evaluation == evaluated
    counted = sum(card.counted for card in result.cards)
    assert (counted, result.outcomes["correct"]) == (evaluated.counted, evaluated.correct)
    assert outcome_counts(result.cards)["below_threshold"] == evaluated.placed_below_threshold


ROWS = [
    '{"schema": "local-classifier-sample-1", "populations": {"top": 100, "rest": 300}}\n',
    f'{{"sample_row": 1, "item_id": "{card_item_id(SHA, 0)}", "stratum": "top"}}\n',
    f'{{"sample_row": 2, "item_id": "{card_item_id(SHA, 3)}", "stratum": "rest"}}\n',
    f'{{"sample_row": 3, "item_id": "{card_item_id(SHA, 6)}"}}\n',
]


def test_evaluation_coach_sample_keeps_each_cards_row_and_stratum() -> None:
    sample = io.StringIO("sample_row,position\n1,states-cp\n2,none\n3,unsure\n")

    assert read_coach_sample(sample, ROWS, TAXONOMY) == (
        LabelledCard(card_item_id(SHA, 0), "states-cp", sample_row=1, stratum="top"),
        LabelledCard(card_item_id(SHA, 3), "none", sample_row=2, stratum="rest"),
    )
    assert read_sample_populations(ROWS) == {"top": 100, "rest": 300}
    assert read_sample_populations(['{"schema": "local-classifier-sample-1"}\n']) == {}


# ------------------------------------------------------------------------------------------------
# v1-e32-t41: a second label the coach accepts. An answer naming either label is correct; the confusion
# table and the label's kind stay on the first label, and a sample without the column scores as before.
# ------------------------------------------------------------------------------------------------

SECOND_LABELS = {2: "election-da", 3: "spending-da", 4: "medicare-aff"}
"""By sample row: row 2's repaired answer and row 4's answer name these, row 3's (states-cp) does not."""
SECOND_LABELS_ANSWERING = {4}
"""Since `v1-e32-t46` a placement of an affirmative position in a file only the negative disclosed answers it,
so row 4's second label is written `at:medicare-aff` for the answer naming it to be right."""
WITH_SECOND_LABELS = tuple(
    dataclasses.replace(
        card,
        also=SECOND_LABELS.get(card.sample_row or 0),
        also_stance=Stance.ANSWERS if card.sample_row in SECOND_LABELS_ANSWERING else Stance.READS,
    )
    for card in LABELLED
)


@pytest.mark.anyio
async def test_evaluation_breakdown_scores_an_answer_naming_the_second_label_correct(
    prompts: PromptRegistry,
) -> None:
    """By hand from t39's answers: rows 2 and 4 become correct on their second label, row 3 stays a wrong
    kind. Counted 5 (rows 1-5), correct 3; a run sends rows 2-6, 8 and 9: counted 4, correct 2."""
    result = await break_down_labelled_cards(
        READING, TAXONOMY, OVERRIDES, WITH_SECOND_LABELS, stage_over(ScriptedByTag(), prompts)
    )

    assert result.outcomes == {
        "correct": 3,
        "wrong_stance": 0,
        "wrong_position_same_kind": 0,
        "wrong_kind": 1,
        "placed_labelled_none": 1,
        "refused": 2,
        "below_threshold": 1,
        "lost_to_failed_batch": 1,
        "not_asked": 0,
        "not_found": 1,
    }
    by_row = {card.sample_row: card for card in result.cards}
    assert {row: by_row[row].outcome for row in SECOND_LABELS} == {
        2: CardOutcome.CORRECT,
        3: CardOutcome.WRONG_KIND,
        4: CardOutcome.CORRECT,
    }
    assert {row for row, card in by_row.items() if card.correct_on_second_label} == {2, 4}
    assert {card.sample_row for card in result.cards if card.related} == set()
    assert second_label_counts(result.cards) == {"cards": 3, "correct": 2}
    assert (result.evaluation.counted, result.evaluation.correct, result.evaluation.accuracy) == (5, 3, 0.6)
    model_set = result.model_set
    assert (model_set.cards, model_set.counted, model_set.correct) == (7, 4, 2)


@pytest.mark.anyio
async def test_evaluation_breakdown_keeps_the_confusion_table_and_label_kinds_on_the_first_label(
    prompts: PromptRegistry,
) -> None:
    result = await break_down_labelled_cards(
        READING, TAXONOMY, OVERRIDES, WITH_SECOND_LABELS, stage_over(ScriptedByTag(), prompts)
    )

    assert ("spending-da", "election-da", 1) in confusion(result.cards)
    assert ("rural-adv", "at:medicare-aff", 1) in confusion(result.cards)
    assert outcomes_by_label_kind(result.cards) == {
        "advantage": {"correct": 1},
        "cp": {"correct": 1, "below_threshold": 1, "not_found": 1},
        "da": {"correct": 1, "wrong_kind": 1, "refused": 1, "lost_to_failed_batch": 1},
        "none": {"placed_labelled_none": 1, "refused": 1},
    }


ROWS_OF_EVERY_CARD = [
    '{"schema": "local-classifier-sample-1", "populations": {"top": 100, "rest": 300}}\n',
    *(
        json.dumps({"sample_row": card.sample_row, "item_id": card.item_id, "stratum": card.stratum}) + "\n"
        for card in LABELLED
    ),
]


def t39_sample(*, second_label_column: bool) -> io.StringIO:
    """t39's ten labels as the coach's CSV, with an empty second-label column or none."""
    header = "sample_row,tag,position" + (",also" if second_label_column else "")
    lines = [
        f"{card.sample_row},a tag,{card.label}" + ("," if second_label_column else "") for card in LABELLED
    ]
    return io.StringIO("\n".join([header, *lines]) + "\n")


@pytest.mark.anyio
async def test_a_sample_without_the_second_label_column_scores_exactly_as_t39s(
    prompts: PromptRegistry,
) -> None:
    without = read_coach_sample(t39_sample(second_label_column=False), ROWS_OF_EVERY_CARD, TAXONOMY)
    blank = read_coach_sample(t39_sample(second_label_column=True), ROWS_OF_EVERY_CARD, TAXONOMY)

    assert without == blank == LABELLED
    result = await break_down_labelled_cards(
        READING, TAXONOMY, OVERRIDES, without, stage_over(ScriptedByTag(), prompts)
    )
    assert {card.sample_row: (card.outcome, card.answer) for card in result.cards} == {
        row: (expected[0], expected[2]) for row, expected in EXPECTED.items()
    }
    assert (result.evaluation.counted, result.evaluation.correct) == (5, 1)
    assert second_label_counts(result.cards) == {"cards": 0, "correct": 0}
    assert not any(card.correct_on_second_label for card in result.cards)


def test_the_coach_sample_reads_a_second_label_beside_the_first() -> None:
    sample = io.StringIO("sample_row,position,also\n1,states-cp,\n2,spending-da,election-da\n3,none,\n")

    assert read_coach_sample(sample, ROWS, TAXONOMY) == (
        LabelledCard(card_item_id(SHA, 0), "states-cp", sample_row=1, stratum="top"),
        LabelledCard(card_item_id(SHA, 3), "spending-da", sample_row=2, stratum="rest", also="election-da"),
        LabelledCard(card_item_id(SHA, 6), "none", sample_row=3),
    )


@pytest.mark.parametrize(
    ("also", "refused"),
    [
        ("spending-da", "row 2's second label is its first"),
        ("none", "row 2's second label is none"),
        ("None", "row 2's second label is none"),
        ("made-up-cp", f"row 2's second label is not an active id of {TOPIC} 1.0.0"),
        ("unsure", f"row 2's second label is not an active id of {TOPIC} 1.0.0"),
    ],
)
def test_a_second_label_that_is_none_the_first_or_no_position_is_refused_by_row(
    also: str, refused: str
) -> None:
    sample = io.StringIO(f"sample_row,position,also\n1,states-cp,\n2,spending-da,{also}\n")

    with pytest.raises(EvaluationRefused, match=refused):
        read_coach_sample(sample, ROWS, TAXONOMY)


def test_a_card_labelled_none_takes_no_second_label() -> None:
    sample = io.StringIO("sample_row,position,also\n2,none,spending-da\n")

    with pytest.raises(EvaluationRefused, match="row 2 is labelled none and names a second label"):
        read_coach_sample(sample, ROWS, TAXONOMY)


def test_the_coach_sample_is_counted_by_label_kind_and_second_label_kind() -> None:
    sample = io.StringIO(
        "sample_row,position,also\n1,states-cp,spending-da\n2,spending-da,election-da\n3,none,\n"
    )

    labelled = read_coach_sample(sample, ROWS, TAXONOMY)

    assert coach_sample_counts(labelled, TAXONOMY) == ({"cp": 1, "da": 1, "none": 1}, {"da": 2})
