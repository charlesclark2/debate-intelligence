"""The evaluation scored as students meet it (`v1-e32-t43`): stage one's sure placements, then the model.

Twelve labelled cards, built by hand as the breakdown builds them: each with the model's outcome and
stage one's placement. Every count below is worked out from the table, never from the code.

| Card | Label (also) | Model's outcome | Stage one | Pipeline scores |
|---|---|---|---|---|
| a | states-cp | wrong kind | states-cp, sure | headings: correct |
| b | spending-da | refused | spending-da, sure | headings: correct |
| c | election-da | correct | states-cp, sure | headings: wrong |
| d | none | placed though none | decided none | decided none |
| e | election-da | correct | unplaced | model: correct |
| f | rural-adv | refused | unplaced | model: refused |
| g | spending-da | below threshold | election-da at 0.5, sent | model: below |
| h | spending-da (election-da) | correct, on the second label | unplaced | model: correct |
| i | none | refused | spending-da, sure | headings: wrong |
| j | states-cp | not found | not found | model: not found |
| k | states-cp | lost to a failed batch | states-cp, sure | headings: correct |
| l | spending-da (states-cp) | refused | states-cp, sure | headings: correct, on the second label |

The model alone: counted a, c, d, e, h (5), correct c, e, h (3), refused b, f, i, l (4), below g (1).
The pipeline: counted a, b, c, i, k, l by the headings and e, h by the model (8), correct a, b, k, l, e, h
(6), refused f (1), below g (1), decided none d (1).
"""

from __future__ import annotations

from debate_core.arguments.landscape.evaluation_breakdown import (
    CardBreakdown,
    CardOutcome,
    DeterministicPlacement,
    LabelledScore,
    model_alone_score,
    pipeline_score,
    placed_by_headings,
)

SURE = 1.0


def sure(position_id: str) -> DeterministicPlacement:
    return DeterministicPlacement(
        position_id=position_id, method="ALIAS", confidence=SURE, sent_to_model=False
    )


UNPLACED = DeterministicPlacement(position_id=None, method=None, confidence=0.0, sent_to_model=True)
DECIDED_NONE = DeterministicPlacement(
    position_id=None, method="OVERRIDE", confidence=SURE, sent_to_model=False
)
BELOW = DeterministicPlacement(
    position_id="election-da", method="TAG_KEYWORD", confidence=0.5, sent_to_model=True
)


def card(
    label: str,
    outcome: CardOutcome,
    placed: DeterministicPlacement | None,
    *,
    answer: str | None = None,
    also: str | None = None,
) -> CardBreakdown:
    kind = "none" if label == "none" else label.rsplit("-", 1)[-1]
    return CardBreakdown(
        label=label, label_kind=kind, outcome=outcome, answer=answer, deterministic=placed, also=also
    )


CARDS = {
    "a": card("states-cp", CardOutcome.WRONG_KIND, sure("states-cp"), answer="spending-da"),
    "b": card("spending-da", CardOutcome.REFUSED, sure("spending-da")),
    "c": card("election-da", CardOutcome.CORRECT, sure("states-cp"), answer="election-da"),
    "d": card("none", CardOutcome.PLACED_LABELLED_NONE, DECIDED_NONE, answer="spending-da"),
    "e": card("election-da", CardOutcome.CORRECT, UNPLACED, answer="election-da"),
    "f": card("rural-adv", CardOutcome.REFUSED, UNPLACED),
    "g": card("spending-da", CardOutcome.BELOW_THRESHOLD, BELOW, answer="spending-da"),
    "h": card("spending-da", CardOutcome.CORRECT, UNPLACED, answer="election-da", also="election-da"),
    "i": card("none", CardOutcome.REFUSED, sure("spending-da")),
    "j": card("states-cp", CardOutcome.NOT_FOUND, None),
    "k": card("states-cp", CardOutcome.LOST_TO_FAILED_BATCH, sure("states-cp")),
    "l": card("spending-da", CardOutcome.REFUSED, sure("states-cp"), also="states-cp"),
}


def test_evaluation_model_alone_scores_every_cards_model_answer_and_counts_no_refusal() -> None:
    assert model_alone_score(CARDS.values()) == LabelledScore(
        labelled=12, counted=5, correct=3, refused=4, below_threshold=1
    )


def test_evaluation_pipeline_scores_stage_ones_sure_placements_and_the_model_for_the_rest() -> None:
    assert pipeline_score(CARDS.values()) == LabelledScore(
        labelled=12, counted=8, correct=6, refused=1, below_threshold=1, by_headings=6, decided_none=1
    )


def test_evaluation_pipeline_takes_the_cards_stage_one_places_surely_and_no_other() -> None:
    assert {name for name, one in CARDS.items() if placed_by_headings(one)} == {"a", "b", "c", "i", "k", "l"}


def test_evaluation_scores_give_accuracy_over_the_counted_and_coverage_over_the_labelled() -> None:
    model, pipeline = model_alone_score(CARDS.values()), pipeline_score(CARDS.values())

    assert (model.accuracy, model.coverage) == (3 / 5, 5 / 12)
    assert (pipeline.accuracy, pipeline.coverage) == (6 / 8, 8 / 12)


def test_evaluation_score_of_no_card_has_no_accuracy_and_no_coverage() -> None:
    nothing = pipeline_score([])

    assert nothing == LabelledScore(labelled=0, counted=0, correct=0, refused=0, below_threshold=0)
    assert (nothing.accuracy, nothing.coverage) == (None, None)


def test_evaluation_pipeline_of_a_card_stage_one_sends_is_the_models_whatever_stage_one_named() -> None:
    """A placement below the threshold is sent: g is scored on the model's answer, not on election-da."""
    sent_below = {"g": CARDS["g"], "below-and-right": card("election-da", CardOutcome.REFUSED, BELOW)}

    assert pipeline_score(sent_below.values()) == LabelledScore(
        labelled=2, counted=0, correct=0, refused=1, below_threshold=1
    )
