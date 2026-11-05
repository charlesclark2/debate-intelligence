"""The model's answers naming a generic position, counted on their own (`v1-e32-t49`, the PM's condition on
prompt 1.3.0's generic-confidence clause).

Every expected count is worked out by hand from the cards below. No card, heading or tag is real.

| Row | Label | Answer | Outcome | Generic answer | Counted | Named label of its kind |
|---|---|---|---|---|---|---|
| 1 | generic-k | generic-k | correct | yes | right | |
| 2 | cap-k | generic-k | same kind | yes | wrong | yes |
| 3 | cap-k | generic-k | below the threshold | yes | not counted | yes |
| 4 | none | generic-k | placed though none | yes | wrong | |
| 5 | politics-da | generic-theory | wrong kind | yes | wrong | no: a da label |
| 6 | generic-k | cap-k | same kind | no | | |
| 7 | generic-k | refused | refused | no | | |
| 8 | cap-k, also generic-k | generic-k | correct | yes | right | no: the coach accepts it |

Answers 6 (1, 2, 3, 4, 5, 8); counted 5 (all but 3); right 2 (1, 8); wrong 3 (2, 4, 5); named-label rows 2
and 3.
"""

from __future__ import annotations

from debate_core.arguments.landscape.evaluation_breakdown import (
    CardBreakdown,
    CardOutcome,
    GenericAnswers,
    generic_answer_counts,
    generic_positions,
)
from debate_core.domain.landscape import Taxonomy

TAXONOMY = Taxonomy.model_validate(
    {
        "topic_id": "policy-sample-topic",
        "taxonomy_version": "1.0.0",
        "event": "POLICY",
        "positions": [
            {"id": "cap-k", "label": "Cap K", "kind": "k", "side": "neg"},
            {"id": "generic-k", "label": "Generic K", "kind": "k", "side": "neg"},
            {"id": "politics-da", "label": "Politics DA", "kind": "da", "side": "neg"},
            {"id": "generic-theory", "label": "Generic theory", "kind": "theory", "side": "both"},
        ],
    }
)


def card(
    row: int, label: str, kind: str, outcome: CardOutcome, answer: str | None, *, also: str | None = None
) -> CardBreakdown:
    return CardBreakdown(
        label=label,
        label_kind=kind,
        outcome=outcome,
        answer=answer,
        confidence=None if answer is None else (0.5 if outcome is CardOutcome.BELOW_THRESHOLD else 0.9),
        sample_row=row,
        also=also,
    )


CARDS = (
    card(1, "generic-k", "k", CardOutcome.CORRECT, "generic-k"),
    card(2, "cap-k", "k", CardOutcome.WRONG_POSITION_SAME_KIND, "generic-k"),
    card(3, "cap-k", "k", CardOutcome.BELOW_THRESHOLD, "generic-k"),
    card(4, "none", "none", CardOutcome.PLACED_LABELLED_NONE, "generic-k"),
    card(5, "politics-da", "da", CardOutcome.WRONG_KIND, "generic-theory"),
    card(6, "generic-k", "k", CardOutcome.WRONG_POSITION_SAME_KIND, "cap-k"),
    card(7, "generic-k", "k", CardOutcome.REFUSED, None),
    card(8, "cap-k", "k", CardOutcome.CORRECT, "generic-k", also="generic-k"),
)


def test_a_taxonomy_s_generic_positions_are_its_generic_ids_with_their_kinds() -> None:
    assert generic_positions(TAXONOMY) == {"generic-k": "k", "generic-theory": "theory"}


def test_the_answers_naming_a_generic_position_are_counted_on_their_own() -> None:
    found = generic_answer_counts(CARDS, generic_positions(TAXONOMY))

    assert found == GenericAnswers(answers=6, above_threshold=5, correct=2, wrong=3, named_label_rows=(2, 3))


def test_no_generic_position_counts_nothing() -> None:
    assert generic_answer_counts(CARDS, {}) == GenericAnswers()
