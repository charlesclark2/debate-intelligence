"""The answering stance (`v1-e32-t46`): the model's stanced answer, a placement's stance as scored, and the
`wrong_stance` outcome.

Every expected value is written by hand from the invented taxonomy below. No card, heading or tag is real.

A placement's stance, as scored, is the report's: READS when every readable side its file was disclosed on is
the position's own (`v1-e32-t49`, whatever its role); otherwise ANSWERS when its role is ANSWERS, or when
every readable side is opposite the position's side; READS otherwise.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from debate_core.arguments.landscape.evaluation_breakdown import (
    ANSWERS_PREFIX,
    COUNTED_OUTCOMES,
    CardBreakdown,
    CardOutcome,
    DeterministicPlacement,
    card_outcome,
    confusion,
    labelled_as,
    model_alone_score,
    pipeline_score,
    scored_stance,
    second_label_counts,
)
from debate_core.arguments.landscape.headings import NormalizedHeading
from debate_core.arguments.landscape.model_stage import ModelCandidate, ModelItem, answer_schema, judge
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import (
    ClassificationMethod,
    ClassificationResult,
    ModelPositionAnswer,
    ModelPositionAnswers,
    ModelStancedPositionAnswer,
    ModelStancedPositionAnswers,
    PositionRole,
    Stance,
)

TAXONOMY = Taxonomy.model_validate(
    {
        "topic_id": "policy-sample-topic",
        "taxonomy_version": "1.0.0",
        "event": "POLICY",
        "positions": [
            {"id": "medicare-aff", "label": "Medicare Aff", "kind": "aff", "side": "aff"},
            {"id": "rural-adv", "label": "Rural Advantage", "kind": "advantage", "side": "aff"},
            {"id": "politics-da", "label": "Politics DA", "kind": "da", "side": "neg"},
            {"id": "spending-da", "label": "Spending DA", "kind": "da", "side": "neg"},
            {"id": "states-cp", "label": "States CP", "kind": "cp", "side": "neg"},
            {"id": "condo-bad", "label": "Condo Bad", "kind": "theory", "side": "both"},
        ],
    }
)
THRESHOLD = 0.6


def placed(
    position_id: str, *, role: PositionRole = PositionRole.READS, confidence: float = 0.8
) -> ClassificationResult:
    return ClassificationResult(
        position_id=position_id,
        role=role,
        confidence=confidence,
        rationale="a reason",
        method=ClassificationMethod.MODEL,
        taxonomy_version="1.0.0",
        prompt_id="landscape.classify_position",
        prompt_version="1.2.0",
        model_id="sample-model",
    )


# ------------------------------------------------------------------------------------------------
# The model's answer
# ------------------------------------------------------------------------------------------------


def test_a_stanced_answer_needs_its_stance_and_an_earlier_answer_takes_none() -> None:
    answer = {"item": "item-1", "position_id": "politics-da", "confidence": 0.8, "rationale": "a reason"}

    with pytest.raises(ValidationError, match="stance"):
        ModelStancedPositionAnswers.model_validate({"answers": [answer]})
    stanced = ModelStancedPositionAnswers.model_validate({"answers": [{**answer, "stance": "answers"}]})
    assert stanced.answers[0].stance is Stance.ANSWERS
    with pytest.raises(ValidationError):
        ModelPositionAnswers.model_validate({"answers": [{**answer, "stance": "answers"}]})
    assert ModelPositionAnswers.model_validate({"answers": [answer]}).answers[0].position_id == "politics-da"


@pytest.mark.parametrize(
    ("version", "schema"),
    [
        ("1.0.0", ModelPositionAnswers),
        ("1.1.0", ModelPositionAnswers),
        ("1.1.9", ModelPositionAnswers),
        ("1.2.0", ModelStancedPositionAnswers),
        ("1.10.0", ModelStancedPositionAnswers),
        ("2.0.0", ModelStancedPositionAnswers),
    ],
)
def test_prompt_1_2_0_on_answers_with_a_stance_and_earlier_versions_as_recorded(
    version: str, schema: type[ModelPositionAnswers]
) -> None:
    assert answer_schema(version) is schema


def judged(answer: ModelPositionAnswer, *, answer_heading: bool) -> ClassificationResult:
    candidate = ModelCandidate(
        fingerprint="a" * 64,
        source_sha256="0" * 64,
        first_element_index=3,
        headings=(NormalizedHeading(text="politics", answer=answer_heading),),
        tag="the vote shifts",
        short_cite=None,
        own_names=(),
    )
    return judge(
        answer,
        ModelItem(candidate=candidate, excerpt=None, evidence="an invented body of evidence"),
        taxonomy=TAXONOMY,
        prompt_id="landscape.classify_position",
        prompt_version="1.2.0",
        model_id="sample-model",
    )


def stanced(stance: Stance) -> ModelStancedPositionAnswer:
    return ModelStancedPositionAnswer(
        item="item-1", position_id="politics-da", confidence=0.8, rationale="a reason", stance=stance
    )


@pytest.mark.parametrize("answer_heading", [False, True])
def test_a_stanced_answer_sets_the_role_whatever_the_answer_heading_says(answer_heading: bool) -> None:
    assert judged(stanced(Stance.ANSWERS), answer_heading=answer_heading).role is PositionRole.ANSWERS
    assert judged(stanced(Stance.READS), answer_heading=answer_heading).role is PositionRole.READS


@pytest.mark.parametrize(
    ("answer_heading", "role"), [(False, PositionRole.READS), (True, PositionRole.ANSWERS)]
)
def test_an_answer_without_a_stance_keeps_the_role_the_headings_give(
    answer_heading: bool, role: PositionRole
) -> None:
    plain = ModelPositionAnswer(
        item="item-1", position_id="politics-da", confidence=0.8, rationale="a reason"
    )

    assert judged(plain, answer_heading=answer_heading).role is role


# ------------------------------------------------------------------------------------------------
# A placement's stance, as scored
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("position_id", "role", "sides", "stance"),
    [
        ("politics-da", PositionRole.ANSWERS, {"NEG"}, Stance.READS),
        ("politics-da", PositionRole.ANSWERS, {"CON", "UNKNOWN"}, Stance.READS),
        ("politics-da", PositionRole.ANSWERS, {"AFF"}, Stance.ANSWERS),
        ("politics-da", PositionRole.ANSWERS, {"AFF", "NEG"}, Stance.ANSWERS),
        ("politics-da", PositionRole.ANSWERS, set[str](), Stance.ANSWERS),
        ("rural-adv", PositionRole.ANSWERS, {"AFF"}, Stance.READS),
        ("condo-bad", PositionRole.ANSWERS, {"NEG"}, Stance.ANSWERS),
        ("politics-da", PositionRole.READS, {"AFF"}, Stance.ANSWERS),
        ("politics-da", PositionRole.READS, {"AFF", "UNKNOWN"}, Stance.ANSWERS),
        ("politics-da", PositionRole.READS, {"NEG"}, Stance.READS),
        ("politics-da", PositionRole.READS, {"AFF", "NEG"}, Stance.READS),
        ("politics-da", PositionRole.READS, {"UNKNOWN"}, Stance.READS),
        ("politics-da", PositionRole.READS, set[str](), Stance.READS),
        ("rural-adv", PositionRole.READS, {"NEG"}, Stance.ANSWERS),
        ("rural-adv", PositionRole.READS, {"CON"}, Stance.ANSWERS),
        ("rural-adv", PositionRole.READS, {"PRO"}, Stance.READS),
        ("rural-adv", PositionRole.READS, {"AFF"}, Stance.READS),
        ("condo-bad", PositionRole.READS, {"AFF"}, Stance.READS),
        ("condo-bad", PositionRole.ANSWERS, {"AFF"}, Stance.ANSWERS),
    ],
)
def test_a_placement_reads_on_its_own_side_and_otherwise_answers_by_its_role_or_the_other_side(
    position_id: str, role: PositionRole, sides: set[str], stance: Stance
) -> None:
    assert scored_stance(TAXONOMY, position_id, role, frozenset(sides)) is stance


def test_an_answering_label_is_written_with_the_prefix() -> None:
    assert ANSWERS_PREFIX == "at:"
    assert labelled_as("politics-da", Stance.ANSWERS) == "at:politics-da"
    assert labelled_as("politics-da", Stance.READS) == "politics-da"


# ------------------------------------------------------------------------------------------------
# The outcome
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "stance", "result", "sides", "outcome"),
    [
        ("politics-da", Stance.ANSWERS, placed("politics-da"), {"AFF"}, CardOutcome.CORRECT),
        ("politics-da", Stance.READS, placed("politics-da"), {"AFF"}, CardOutcome.WRONG_STANCE),
        ("politics-da", Stance.READS, placed("politics-da"), {"NEG"}, CardOutcome.CORRECT),
        ("politics-da", Stance.ANSWERS, placed("politics-da"), {"NEG"}, CardOutcome.WRONG_STANCE),
        (
            "politics-da",
            Stance.ANSWERS,
            placed("politics-da", role=PositionRole.ANSWERS),
            {"NEG"},
            CardOutcome.WRONG_STANCE,
        ),
        (
            "politics-da",
            Stance.READS,
            placed("politics-da", role=PositionRole.ANSWERS),
            {"NEG"},
            CardOutcome.CORRECT,
        ),
        (
            "politics-da",
            Stance.ANSWERS,
            placed("politics-da", role=PositionRole.ANSWERS),
            {"AFF", "NEG"},
            CardOutcome.CORRECT,
        ),
        ("politics-da", Stance.ANSWERS, placed("spending-da"), {"AFF"}, CardOutcome.WRONG_POSITION_SAME_KIND),
        ("politics-da", Stance.ANSWERS, placed("medicare-aff"), {"AFF"}, CardOutcome.WRONG_KIND),
        (
            "politics-da",
            Stance.ANSWERS,
            placed("politics-da", confidence=0.5),
            {"NEG"},
            CardOutcome.BELOW_THRESHOLD,
        ),
    ],
)
def test_the_label_s_position_with_the_other_stance_is_a_wrong_stance(
    label: str, stance: Stance, result: ClassificationResult, sides: set[str], outcome: CardOutcome
) -> None:
    assert (
        card_outcome(TAXONOMY, label, result, threshold=THRESHOLD, stance=stance, file_sides=frozenset(sides))
        is outcome
    )


def test_a_second_label_naming_the_same_position_with_the_other_stance_accepts_either() -> None:
    for sides in ({"AFF"}, {"NEG"}):
        assert (
            card_outcome(
                TAXONOMY,
                "politics-da",
                placed("politics-da"),
                threshold=THRESHOLD,
                also="politics-da",
                also_stance=Stance.ANSWERS,
                file_sides=frozenset(sides),
            )
            is CardOutcome.CORRECT
        )


def test_a_second_label_is_judged_with_its_own_stance() -> None:
    outcome = card_outcome(
        TAXONOMY,
        "politics-da",
        placed("states-cp"),
        threshold=THRESHOLD,
        also="states-cp",
        also_stance=Stance.ANSWERS,
        file_sides=frozenset({"NEG"}),
    )

    assert outcome is CardOutcome.WRONG_STANCE


def test_a_wrong_stance_is_counted_and_wrong() -> None:
    assert CardOutcome.WRONG_STANCE in COUNTED_OUTCOMES
    cards = [
        CardBreakdown(
            label="politics-da", label_kind="da", outcome=CardOutcome.CORRECT, answer="politics-da"
        ),
        CardBreakdown(
            label="politics-da",
            label_kind="da",
            outcome=CardOutcome.WRONG_STANCE,
            answer="politics-da",
            stance=Stance.ANSWERS,
            answer_stance=Stance.READS,
        ),
    ]

    alone = model_alone_score(cards)

    assert (alone.counted, alone.correct, alone.accuracy) == (2, 1, 0.5)


def sure(position_id: str, stance: Stance) -> DeterministicPlacement:
    return DeterministicPlacement(
        position_id=position_id, method="ALIAS", confidence=1.0, sent_to_model=False, stance=stance
    )


def test_the_pipeline_scores_the_headings_placement_with_its_stance() -> None:
    cards = [
        CardBreakdown(
            label="states-cp",
            label_kind="cp",
            outcome=CardOutcome.REFUSED,
            stance=Stance.ANSWERS,
            deterministic=sure("states-cp", Stance.ANSWERS),
        ),
        CardBreakdown(
            label="states-cp",
            label_kind="cp",
            outcome=CardOutcome.REFUSED,
            stance=Stance.READS,
            deterministic=sure("states-cp", Stance.ANSWERS),
        ),
        CardBreakdown(
            label="states-cp",
            label_kind="cp",
            outcome=CardOutcome.REFUSED,
            also="states-cp",
            also_stance=Stance.ANSWERS,
            deterministic=sure("states-cp", Stance.ANSWERS),
        ),
    ]

    pipeline = pipeline_score(cards)

    assert (pipeline.counted, pipeline.correct, pipeline.by_headings) == (3, 2, 3)


def test_the_confusion_table_writes_an_answering_label_and_answer_with_the_prefix() -> None:
    cards = [
        CardBreakdown(
            label="politics-da",
            label_kind="da",
            outcome=CardOutcome.WRONG_STANCE,
            answer="politics-da",
            stance=Stance.ANSWERS,
            answer_stance=Stance.READS,
        ),
        CardBreakdown(
            label="politics-da",
            label_kind="da",
            outcome=CardOutcome.WRONG_KIND,
            answer="medicare-aff",
            stance=Stance.READS,
            answer_stance=Stance.ANSWERS,
        ),
    ]

    assert confusion(cards) == [("at:politics-da", "politics-da", 1), ("politics-da", "at:medicare-aff", 1)]


def test_a_card_right_on_its_second_label_s_stance_is_counted_right_on_the_second_label() -> None:
    cards = [
        CardBreakdown(
            label="politics-da",
            label_kind="da",
            outcome=CardOutcome.CORRECT,
            answer="politics-da",
            also="politics-da",
            also_stance=Stance.ANSWERS,
            answer_stance=Stance.ANSWERS,
        ),
        CardBreakdown(
            label="politics-da",
            label_kind="da",
            outcome=CardOutcome.CORRECT,
            answer="politics-da",
            also="politics-da",
            also_stance=Stance.ANSWERS,
            answer_stance=Stance.READS,
        ),
    ]

    assert second_label_counts(cards) == {"cards": 2, "correct": 1}
