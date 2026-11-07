"""The coach's stance labels and the model's stanced answers, through the evaluation's path (`v1-e32-t46`).

Three invented sources, one disclosed on the affirmative, one on the negative and one on both (`v1-e32-t49`),
seven cards labelled by hand,
asked about through the real prompt (1.2.0, the stage's default) over a scripted model. Stage one, by hand:
`States CP` is an alias, placed surely and never sent; `AT: Link turn` is an answer heading; the rest are
unplaced.

| Row | File | Tag | Headings | Label | Model answers | Model alone |
|---|---|---|---|---|---|---|
| 1 | aff | Not unique | Politics | at:election-da | election-da reads 0.9 | correct: aff file |
| 2 | neg | Midterms shift | Politics | election-da | election-da, answers, 0.9 | correct: own side |
| 3 | neg | Link turn wrong | AT: Link turn | election-da | election-da reads 0.8 | correct: by the stance |
| 4 | aff | Fed key wrong | States CP | at:states-cp | states-cp, reads, 0.9 | correct |
| 5 | aff | Rural hospitals close | Solvency | rural-adv | rural-adv, reads, 0.9 | correct |
| 6 | neg | Rural fine | Case | at:rural-adv | medicare-aff, answers, 0.9 | wrong kind |
| 7 | both | Midterms flip | Politics | election-da | election-da, answers, 0.9 | wrong stance |

Row 2 was a wrong stance until `v1-e32-t49`: a card in a file disclosed only on its position's own side reads
it, whatever the model's stance. Row 7, in a file disclosed on both sides, keeps the model's stance.

The model alone: counted 7, correct 1 to 5 (5), wrong kind 6, wrong stance 7. The pipeline: row 4 by the
headings (states-cp in an aff file: answers, as labelled), the rest by the model: counted 7, correct 5.
Every school, team, tournament, heading and tag is invented.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from debate_core.application.landscape_model_evaluation import (
    CoachLabel,
    EvaluationRefused,
    LabelledCard,
    break_down_labelled_cards,
    coach_label,
    evaluate_labelled_cards,
    read_coach_sample,
    stance_counts,
)
from debate_core.application.landscape_model_stage import (
    CLASSIFY_POSITION_PROMPT_ID,
    CLASSIFY_POSITION_VERSION,
    ModelClassificationStage,
    ParsedStoreCardTexts,
)
from debate_core.application.landscape_seeding import SeedReading
from debate_core.application.structured_output import StructuredOutputGuard
from debate_core.arguments.landscape.evaluation_breakdown import CardOutcome, outcome_counts
from debate_core.arguments.landscape.seeding import SeedCard, SeedSource, SeedTeam
from debate_core.domain.caselist import Side
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import (
    ModelPositionAnswers,
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
AFF_SHA = "a" * 64
NEG_SHA = "b" * 64
BOTH_SHA = "c" * 64
TOPIC = "policy-sample-topic"

TAXONOMY = Taxonomy.model_validate(
    {
        "topic_id": TOPIC,
        "taxonomy_version": "1.0.0",
        "event": "POLICY",
        "positions": [
            {"id": "medicare-aff", "label": "Medicare Aff", "kind": "aff", "side": "aff"},
            {"id": "rural-adv", "label": "Rural Hospitals Advantage", "kind": "advantage", "side": "aff"},
            {"id": "election-da", "label": "Election DA", "kind": "da", "side": "neg"},
            {"id": "states-cp", "label": "States CP", "kind": "cp", "side": "neg", "aliases": ["states cp"]},
        ],
    }
)
OVERRIDES = OverrideRules.model_validate({"topic_id": TOPIC, "overrides": []})

# (row, source, tag, heading, label, stance, the model's answer: position, stance, confidence)
CARDS: tuple[tuple[int, str, str, str, str, Stance, tuple[str, Stance, float]], ...] = (
    (1, AFF_SHA, "Not unique", "Politics", "election-da", Stance.ANSWERS, ("election-da", Stance.READS, 0.9)),
    (
        2,
        NEG_SHA,
        "Midterms shift",
        "Politics",
        "election-da",
        Stance.READS,
        ("election-da", Stance.ANSWERS, 0.9),
    ),
    (
        3,
        NEG_SHA,
        "Link turn wrong",
        "AT: Link turn",
        "election-da",
        Stance.READS,
        ("election-da", Stance.READS, 0.8),
    ),
    (4, AFF_SHA, "Fed key wrong", "States CP", "states-cp", Stance.ANSWERS, ("states-cp", Stance.READS, 0.9)),
    (
        5,
        AFF_SHA,
        "Rural hospitals close",
        "Solvency",
        "rural-adv",
        Stance.READS,
        ("rural-adv", Stance.READS, 0.9),
    ),
    (6, NEG_SHA, "Rural fine", "Case", "rural-adv", Stance.ANSWERS, ("medicare-aff", Stance.ANSWERS, 0.9)),
    (
        7,
        BOTH_SHA,
        "Midterms flip",
        "Politics",
        "election-da",
        Stance.READS,
        ("election-da", Stance.ANSWERS, 0.9),
    ),
)
ANSWERS = {tag.lower(): answer for _, _, tag, _, _, _, answer in CARDS}


def index_of(row: int) -> int:
    return 3 * row


def source(sha: str, *sides: Side) -> SeedSource:
    return SeedSource(
        sha256=sha,
        teams=tuple(
            SeedTeam(
                identity=f"birch/{side.value.lower()}",
                side=side,
                names=("Birch Hollow", "MN"),
                tournament=None,
            )
            for side in sides
        ),
        cards=tuple(
            SeedCard(tag=tag, section_path=(heading,), first_element_index=index_of(row))
            for row, card_sha, tag, heading, _, _, _ in CARDS
            if card_sha == sha
        ),
    )


READING = SeedReading(
    caselist="hspolicy99",
    version="2026.10.20-docx-6",
    topic_id=TOPIC,
    entries=3,
    parsed=3,
    parsed_off_topic=0,
    sources=(
        source(AFF_SHA, Side.AFF),
        source(NEG_SHA, Side.NEG),
        source(BOTH_SHA, Side.AFF, Side.NEG),
    ),
    caselist_names={"Birch Hollow": ("MN",)},
)
LABELLED = [
    LabelledCard(card_item_id(sha, index_of(row)), label, sample_row=row, stance=stance)
    for row, sha, _, _, label, stance, _ in CARDS
]


class StancedByTag(ScriptedModelRouter):
    """Answers each card by its tag, with a stance when the schema asks for one; records the schemas asked."""

    def __init__(self) -> None:
        super().__init__(model_id="recorded-model")
        self.schemas: list[type[BaseModel]] = []

    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        self.schemas.append(schema)
        items: list[dict[str, Any]] = json.loads(str(prompt.variables["items"]))
        stanced = schema is ModelStancedPositionAnswers
        self.enqueue(
            {
                "answers": [
                    {
                        "item": item["item"],
                        "position_id": ANSWERS[item["tag"]][0],
                        "confidence": ANSWERS[item["tag"]][2],
                        "rationale": "a reason in the model's words",
                        **({"stance": ANSWERS[item["tag"]][1].value} if stanced else {}),
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


def stage_over(router: Any, registry: PromptRegistry, version: str | None = None) -> ModelClassificationStage:
    guard = StructuredOutputGuard(router, registry)
    texts = ParsedStoreCardTexts(InMemoryParsedStore())
    if version is None:
        return ModelClassificationStage(guard, texts)
    return ModelClassificationStage(guard, texts, prompt_version=version)


# ------------------------------------------------------------------------------------------------
# The stage asks 1.2.0, in its stanced schema
# ------------------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_the_stage_asks_prompt_1_2_0_for_stanced_answers(prompts: PromptRegistry) -> None:
    router = StancedByTag()

    await evaluate_labelled_cards(
        READING, TAXONOMY, LABELLED, stage_over(router, prompts, "1.2.0"), overrides=OVERRIDES
    )

    assert router.schemas == [ModelStancedPositionAnswers]


@pytest.mark.anyio
async def test_the_stage_asks_prompt_1_3_0_for_stanced_answers(prompts: PromptRegistry) -> None:
    router = StancedByTag()

    await evaluate_labelled_cards(
        READING, TAXONOMY, LABELLED, stage_over(router, prompts, "1.3.0"), overrides=OVERRIDES
    )

    assert router.schemas == [ModelStancedPositionAnswers]


@pytest.mark.anyio
async def test_the_stage_asks_prompt_1_3_1_by_default_in_the_stanced_schema(prompts: PromptRegistry) -> None:
    router = StancedByTag()

    await evaluate_labelled_cards(
        READING, TAXONOMY, LABELLED, stage_over(router, prompts), overrides=OVERRIDES
    )

    assert CLASSIFY_POSITION_VERSION == "1.3.1"
    assert router.schemas == [ModelStancedPositionAnswers]


@pytest.mark.anyio
async def test_a_1_1_0_stage_still_asks_in_the_schema_it_was_recorded_in(prompts: PromptRegistry) -> None:
    router = StancedByTag()

    await evaluate_labelled_cards(
        READING, TAXONOMY, LABELLED, stage_over(router, prompts, "1.1.0"), overrides=OVERRIDES
    )

    assert router.schemas == [ModelPositionAnswers]


@pytest.mark.anyio
async def test_1_1_0_recordings_replay_unchanged_and_1_2_0_finds_none_of_them(
    tmp_path: Path, prompts: PromptRegistry
) -> None:
    recording = RecordReplayModelRouter(
        StancedByTag(), mode=ModelMode.RECORD, cassette_dir=tmp_path, environ={}
    )
    recorded = await evaluate_labelled_cards(
        READING, TAXONOMY, LABELLED, stage_over(recording, prompts, "1.1.0"), overrides=OVERRIDES
    )
    [cassette] = sorted((tmp_path / CLASSIFY_POSITION_PROMPT_ID).glob("*.json"))
    request = json.loads(cassette.read_text(encoding="utf-8"))["request"]
    assert request["output_schema"] == "debate_core.domain.landscape_classification.ModelPositionAnswers"

    replaying = RecordReplayModelRouter(None, mode=ModelMode.REPLAY, cassette_dir=tmp_path)
    replayed = await evaluate_labelled_cards(
        READING, TAXONOMY, LABELLED, stage_over(replaying, prompts, "1.1.0"), overrides=OVERRIDES
    )
    assert (replayed.counted, replayed.correct) == (recorded.counted, recorded.correct)
    with pytest.raises(MissingFixtureError, match="1.2.0"):
        await evaluate_labelled_cards(
            READING, TAXONOMY, LABELLED, stage_over(replaying, prompts, "1.2.0"), overrides=OVERRIDES
        )


# ------------------------------------------------------------------------------------------------
# Scored with the stance
# ------------------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_a_wrong_stance_is_its_own_outcome_counted_and_wrong(prompts: PromptRegistry) -> None:
    broken_down = await break_down_labelled_cards(
        READING, TAXONOMY, OVERRIDES, LABELLED, stage_over(StancedByTag(), prompts)
    )
    by_row = {card.sample_row: card for card in broken_down.cards}

    assert {row: card.outcome for row, card in by_row.items()} == {
        1: CardOutcome.CORRECT,
        2: CardOutcome.CORRECT,
        3: CardOutcome.CORRECT,
        4: CardOutcome.CORRECT,
        5: CardOutcome.CORRECT,
        6: CardOutcome.WRONG_KIND,
        7: CardOutcome.WRONG_STANCE,
    }
    assert outcome_counts(broken_down.cards)["wrong_stance"] == 1
    evaluation = broken_down.evaluation
    assert (evaluation.counted, evaluation.correct) == (7, 5)
    assert (evaluation.model_alone.counted, evaluation.model_alone.correct) == (7, 5)
    assert (evaluation.pipeline.counted, evaluation.pipeline.correct, evaluation.pipeline.by_headings) == (
        7,
        5,
        1,
    )


@pytest.mark.anyio
async def test_each_card_carries_its_labels_and_its_answers_stance_as_scored(prompts: PromptRegistry) -> None:
    broken_down = await break_down_labelled_cards(
        READING, TAXONOMY, OVERRIDES, LABELLED, stage_over(StancedByTag(), prompts)
    )
    by_row = {card.sample_row: card for card in broken_down.cards}

    assert [(by_row[row].stance, by_row[row].answer_stance) for row in range(1, 8)] == [
        (Stance.ANSWERS, Stance.ANSWERS),
        (Stance.READS, Stance.READS),
        (Stance.READS, Stance.READS),
        (Stance.ANSWERS, Stance.ANSWERS),
        (Stance.READS, Stance.READS),
        (Stance.ANSWERS, Stance.ANSWERS),
        (Stance.READS, Stance.ANSWERS),
    ]
    placed = by_row[4].deterministic
    assert placed is not None
    assert (placed.position_id, placed.stance, placed.sent_to_model) == ("states-cp", Stance.ANSWERS, False)


# ------------------------------------------------------------------------------------------------
# The coach's sample, with `at:` labels
# ------------------------------------------------------------------------------------------------

ACTIVE = {position.id for position in TAXONOMY.active_positions}
ROWS = [json.dumps({"schema": "local-classifier-sample-1"})] + [
    json.dumps({"sample_row": row, "item_id": card_item_id(AFF_SHA, row)}) for row in range(1, 8)
]


@pytest.mark.parametrize(
    ("cell", "label"),
    [
        ("election-da", CoachLabel("election-da", Stance.READS)),
        ("at:election-da", CoachLabel("election-da", Stance.ANSWERS)),
        ("AT:election-da", CoachLabel("election-da", Stance.ANSWERS)),
        ("At: election-da ", CoachLabel("election-da", Stance.ANSWERS)),
        ("none", CoachLabel("none", Stance.READS)),
        ("None", CoachLabel("none", Stance.READS)),
        ("unsure", None),
        ("  ", None),
    ],
)
def test_a_cell_reads_its_position_or_answers_it(cell: str, label: CoachLabel | None) -> None:
    assert coach_label(cell, ACTIVE) == label


@pytest.mark.parametrize("cell", ["at:none", "at:", "AT:  ", "at:made-up-da", "at:unsure", "made-up-da"])
def test_a_cell_naming_no_position_to_answer_is_refused(cell: str) -> None:
    with pytest.raises(ValueError):
        coach_label(cell, ACTIVE)


def test_the_sample_reads_each_rows_labels_and_stances() -> None:
    sample = (
        "sample_row,position,also\n"
        "1,at:election-da,\n"
        "2,election-da,at:election-da\n"
        "3,AT: states-cp,rural-adv\n"
        "4,none,\n"
        "5,rural-adv,\n"
    )

    labelled = read_coach_sample(io.StringIO(sample), ROWS, TAXONOMY)

    assert [(one.sample_row, one.label, one.stance, one.also, one.also_stance) for one in labelled] == [
        (1, "election-da", Stance.ANSWERS, None, Stance.READS),
        (2, "election-da", Stance.READS, "election-da", Stance.ANSWERS),
        (3, "states-cp", Stance.ANSWERS, "rural-adv", Stance.READS),
        (4, "none", Stance.READS, None, Stance.READS),
        (5, "rural-adv", Stance.READS, None, Stance.READS),
    ]
    assert stance_counts(labelled) == {"answers": 2, "reads": 2}


@pytest.mark.parametrize(
    ("row", "refused"),
    [
        ("6,at:none,", "row 6"),
        ("6,at:,", "row 6"),
        ("6,at:made-up-da,", "row 6"),
        ("6,at:election-da,at:election-da", "row 6's second label is its first"),
        ("6,election-da,at:none", "row 6's second label is none"),
        ("6,none,at:election-da", "row 6 is labelled none"),
        ("6,election-da,at:made-up-da", "row 6's second label"),
    ],
)
def test_a_row_whose_stance_label_names_nothing_to_answer_is_refused_by_row(row: str, refused: str) -> None:
    with pytest.raises(EvaluationRefused, match=refused) as raised:
        read_coach_sample(io.StringIO(f"sample_row,position,also\n{row}\n"), ROWS, TAXONOMY)

    assert "made-up" not in str(raised.value)


def test_stance_counts_name_both_stances_and_leave_out_none() -> None:
    labelled = [LabelledCard("x", "none"), LabelledCard("y", "election-da")]

    assert stance_counts(labelled) == {"answers": 0, "reads": 1}


# ------------------------------------------------------------------------------------------------
# Prompt 1.2.0: the refusal fixes (a) and (b) and the stance (c), with 1.1.0's variables and user turn
# ------------------------------------------------------------------------------------------------


def rendered(registry: PromptRegistry, version: str) -> tuple[str, str]:
    from debate_core.arguments.landscape.model_stage import ModelCandidate, ModelItem, prompt_variables

    item = ModelItem(
        candidate=ModelCandidate(
            fingerprint="f" * 64,
            source_sha256=AFF_SHA,
            first_element_index=0,
            headings=(),
            tag="the vote shifts",
            short_cite=None,
            own_names=(),
        ),
        excerpt=None,
    )
    text = registry.render(
        ModelPrompt(
            prompt_id=CLASSIFY_POSITION_PROMPT_ID,
            prompt_version=version,
            variables=prompt_variables(TAXONOMY, [item]),
        )
    )
    assert text.system is not None
    return " ".join(text.system.split()), text.user


def test_prompt_1_2_0_is_released_with_the_stanced_schema(prompts: PromptRegistry) -> None:
    registered = prompts.get(CLASSIFY_POSITION_PROMPT_ID, "1.2.0")

    assert registered.spec.status.value == "released"
    assert registered.schema is ModelStancedPositionAnswers
    assert registered.spec.task_class is TaskClass.HIGH_VOLUME
    assert prompts.get(CLASSIFY_POSITION_PROMPT_ID, "1.1.0").schema is ModelPositionAnswers


def test_prompt_1_2_0_keeps_1_1_0_s_variables_and_user_turn(prompts: PromptRegistry) -> None:
    _, new_user = rendered(prompts, "1.2.0")
    _, old_user = rendered(prompts, "1.1.0")

    assert new_user == old_user


@pytest.mark.parametrize(
    "sentence",
    [
        "its stance toward that argument",
        "The stance is reads when the card makes the position's own argument, and answers when the other "
        "side reads the card against the position.",
        "A card that answers a position belongs to the position it answers, with the stance answers",
        "When a card is marked as under an answer heading, it answers the position the headings name: stance "
        "answers.",
        "belongs to a kritik or a counterplan even when it reads as general",
        "Never answer null for such a card.",
        "under a heading that names a word of a position's label serves that position",
        "Answer null only when no listed position fits, or when the card is general and no heading names a "
        "word of a position",
        "how likely your position and stance are the ones the coach would choose",
    ],
)
def test_prompt_1_2_0_says_the_refusal_fixes_and_the_stance(prompts: PromptRegistry, sentence: str) -> None:
    new_system, _ = rendered(prompts, "1.2.0")
    old_system, _ = rendered(prompts, "1.1.0")

    assert sentence in new_system
    assert sentence not in old_system


def test_prompt_1_2_0_drops_1_1_0_s_null_clause_for_a_general_card(prompts: PromptRegistry) -> None:
    new_system, _ = rendered(prompts, "1.2.0")

    assert "and you cannot tell which position it serves" not in new_system
    assert "it answers the position rather than reading it" not in new_system


# ------------------------------------------------------------------------------------------------
# Prompt 1.3.0 (`v1-e32-t49`): the own side's answers, the coach's rulings of 2026-11-05 and generic-k,
# with 1.2.0's variables, user turn and schema; 1.2.0's recordings keep their key
# ------------------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_1_2_0_recordings_replay_unchanged_and_1_3_0_finds_none_of_them(
    tmp_path: Path, prompts: PromptRegistry
) -> None:
    recording = RecordReplayModelRouter(
        StancedByTag(), mode=ModelMode.RECORD, cassette_dir=tmp_path, environ={}
    )
    recorded = await evaluate_labelled_cards(
        READING, TAXONOMY, LABELLED, stage_over(recording, prompts, "1.2.0"), overrides=OVERRIDES
    )
    [cassette] = sorted((tmp_path / CLASSIFY_POSITION_PROMPT_ID).glob("*.json"))
    request = json.loads(cassette.read_text(encoding="utf-8"))["request"]
    assert request["prompt"]["prompt_version"] == "1.2.0"
    assert (
        request["output_schema"] == "debate_core.domain.landscape_classification.ModelStancedPositionAnswers"
    )

    replaying = RecordReplayModelRouter(None, mode=ModelMode.REPLAY, cassette_dir=tmp_path)
    replayed = await evaluate_labelled_cards(
        READING, TAXONOMY, LABELLED, stage_over(replaying, prompts, "1.2.0"), overrides=OVERRIDES
    )
    assert (replayed.counted, replayed.correct) == (recorded.counted, recorded.correct) == (7, 5)
    with pytest.raises(MissingFixtureError, match="1.3.0"):
        await evaluate_labelled_cards(
            READING, TAXONOMY, LABELLED, stage_over(replaying, prompts, "1.3.0"), overrides=OVERRIDES
        )


def test_prompt_1_3_0_is_released_with_the_stanced_schema(prompts: PromptRegistry) -> None:
    registered = prompts.get(CLASSIFY_POSITION_PROMPT_ID, "1.3.0")

    assert registered.spec.status.value == "released"
    assert registered.schema is ModelStancedPositionAnswers
    assert registered.spec.task_class is TaskClass.HIGH_VOLUME


def test_prompt_1_3_0_keeps_1_2_0_s_variables_and_user_turn(prompts: PromptRegistry) -> None:
    _, new_user = rendered(prompts, "1.3.0")
    _, old_user = rendered(prompts, "1.2.0")

    assert new_user == old_user


@pytest.mark.parametrize(
    "sentence",
    [
        pytest.param(
            "A card that defends a position against the other side's answers to it reads the position",
            id="own side: defending reads",
        ),
        pytest.param(
            "Its stance is reads, even under an answer heading.", id="own side: even under a heading"
        ),
        pytest.param(
            "When a card is marked as under an answer heading and does not defend the position the headings "
            "name, it answers that position: stance answers.",
            id="own side: the answer heading otherwise",
        ),
        pytest.param(
            "An advantage and a disadvantage about the same subject are different positions, and neither "
            "stands for the other.",
            id="ruling: no mirror pairs",
        ),
        pytest.param(
            "never choose the disadvantage about the same subject for it",
            id="ruling: an answer to an advantage is not the DA",
        ),
        pytest.param(
            "with the stance answers, never to the answering side's own case",
            id="ruling: an answer is never the answering side's case",
        ),
        pytest.param(
            "not to the negative's own disadvantage, counterplan or kritik",
            id="ruling: the negative's direction",
        ),
        pytest.param(
            "A definition the affirmative reads against a counterplan, to show that the counterplan does not "
            "compete or is ruled out, is not topicality: it answers that counterplan.",
            id="ruling: a definition against a counterplan",
        ),
        pytest.param(
            "Choose a named one only when the card argues its theory or its text, as its description says",
            id="generic: a named kritik by its theory",
        ),
        pytest.param(
            "even when the card's subject is near a named one", id="generic: not the nearest subject"
        ),
        pytest.param(
            "A kritik's framework card (how the judge should weigh the round: that representations, ethics "
            "or ontology come before consequences, or the role of the ballot) belongs to a kritik, named or "
            "generic, never to a topicality position.",
            id="generic: a kritik's framework is not topicality",
        ),
        pytest.param(
            "A generic position is never named by a tag or heading: give it 0.9 or more when the card is "
            "plainly that kind's and no named position of the kind fits",
            id="generic: its confidence",
        ),
    ],
)
def test_prompt_1_3_0_says_the_own_side_rule_the_coach_s_rulings_and_generic_k(
    prompts: PromptRegistry, sentence: str
) -> None:
    new_system, _ = rendered(prompts, "1.3.0")
    old_system, _ = rendered(prompts, "1.2.0")

    assert sentence in new_system
    assert sentence not in old_system


@pytest.mark.parametrize(
    "sentence",
    [
        "When a card is marked as under an answer heading, it answers the position the headings name: stance "
        "answers.",
        "A card under an answer heading inside the position's own block, answering the other side's answers "
        "to it, still reads it.",
        "Choose the named one it fits;",
        "Do not choose the plan or advantage the card defends instead.",
    ],
)
def test_prompt_1_3_0_drops_the_1_2_0_sentences_it_replaces(prompts: PromptRegistry, sentence: str) -> None:
    new_system, _ = rendered(prompts, "1.3.0")
    old_system, _ = rendered(prompts, "1.2.0")

    assert sentence in old_system
    assert sentence not in new_system


# ------------------------------------------------------------------------------------------------
# Prompt 1.3.1 (`v1-e32-t55`): 1.3.0 less the generic-confidence sentence, the stage's default. Its
# cassettes are keyed by 1.3.1, and 1.3.0's still replay when 1.3.0 is asked for
# ------------------------------------------------------------------------------------------------


async def record_into(cassettes: Path, prompts: PromptRegistry, version: str | None) -> Any:
    recording = RecordReplayModelRouter(
        StancedByTag(), mode=ModelMode.RECORD, cassette_dir=cassettes, environ={}
    )
    return await evaluate_labelled_cards(
        READING, TAXONOMY, LABELLED, stage_over(recording, prompts, version), overrides=OVERRIDES
    )


def recorded_version(cassettes: Path) -> str:
    [cassette] = sorted((cassettes / CLASSIFY_POSITION_PROMPT_ID).glob("*.json"))
    return json.loads(cassette.read_text(encoding="utf-8"))["request"]["prompt"]["prompt_version"]


@pytest.mark.anyio
async def test_1_3_0_recordings_replay_unchanged_and_1_3_1_finds_none_of_them(
    tmp_path: Path, prompts: PromptRegistry
) -> None:
    recorded = await record_into(tmp_path, prompts, "1.3.0")
    assert recorded_version(tmp_path) == "1.3.0"

    replaying = RecordReplayModelRouter(None, mode=ModelMode.REPLAY, cassette_dir=tmp_path)
    replayed = await evaluate_labelled_cards(
        READING, TAXONOMY, LABELLED, stage_over(replaying, prompts, "1.3.0"), overrides=OVERRIDES
    )
    assert (replayed.counted, replayed.correct) == (recorded.counted, recorded.correct) == (7, 5)
    with pytest.raises(MissingFixtureError, match="1.3.1"):
        await evaluate_labelled_cards(
            READING, TAXONOMY, LABELLED, stage_over(replaying, prompts), overrides=OVERRIDES
        )


@pytest.mark.anyio
async def test_the_default_records_under_1_3_1_and_1_3_0_finds_none_of_those_recordings(
    tmp_path: Path, prompts: PromptRegistry
) -> None:
    recorded = await record_into(tmp_path, prompts, None)
    assert recorded_version(tmp_path) == "1.3.1"

    replaying = RecordReplayModelRouter(None, mode=ModelMode.REPLAY, cassette_dir=tmp_path)
    replayed = await evaluate_labelled_cards(
        READING, TAXONOMY, LABELLED, stage_over(replaying, prompts), overrides=OVERRIDES
    )
    assert (replayed.counted, replayed.correct) == (recorded.counted, recorded.correct) == (7, 5)
    with pytest.raises(MissingFixtureError, match="1.3.0"):
        await evaluate_labelled_cards(
            READING, TAXONOMY, LABELLED, stage_over(replaying, prompts, "1.3.0"), overrides=OVERRIDES
        )


@pytest.mark.anyio
async def test_the_breakdown_carries_the_taxonomy_s_generic_positions(prompts: PromptRegistry) -> None:
    """`v1-e32-t49`: the breakdown counts the answers naming a generic position from its taxonomy's own."""
    positions = [one.model_dump(mode="json", exclude_none=True) for one in TAXONOMY.positions]
    with_generic = Taxonomy.model_validate(
        {
            **TAXONOMY.model_dump(mode="json", exclude_none=True),
            "positions": [
                *positions,
                {"id": "generic-k", "label": "Generic K", "kind": "k", "side": "neg"},
            ],
        }
    )

    broken_down = await break_down_labelled_cards(
        READING, with_generic, OVERRIDES, LABELLED, stage_over(StancedByTag(), prompts)
    )

    assert broken_down.generic == {"generic-k": "k"}
    assert broken_down.generic_answers.answers == 0
