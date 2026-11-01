"""The model stage's evaluation, card by card: what became of each labelled card, and why (`v1-e32-t39`).

`v1-e32-t07`'s evaluation counts the cards a report would count and the right ones among them. This
module gives every labelled card exactly one :class:`CardOutcome`, so the outcomes sum to the labelled
count and the gap between the two numbers can be read:

* **counted**, as the evaluation counts them (a MODEL placement at or above the review threshold):
  :attr:`~CardOutcome.CORRECT`, a wrong position of the label's own kind
  (:attr:`~CardOutcome.WRONG_POSITION_SAME_KIND`), a position of another kind
  (:attr:`~CardOutcome.WRONG_KIND`), or any position for a card the coach labelled none
  (:attr:`~CardOutcome.PLACED_LABELLED_NONE`);
* **not counted**: an answer the stage refused (:attr:`~CardOutcome.REFUSED`, with its
  :class:`~debate_core.arguments.landscape.model_stage.Refusal`), a placement below the threshold, a card
  whose batch failed validation after its repair (:attr:`~CardOutcome.LOST_TO_FAILED_BATCH`), one a stop
  left unasked, and one the store no longer holds.

Beside each card is what stage one, the deterministic matcher, makes of it (:class:`DeterministicPlacement`),
and whether a real run would send it to the model at all: only a card stage one leaves unplaced or places
below the threshold is sent, so the bar applies to those (:func:`model_set_score`).

Pure: values in, values out. A card is named by its row in the coach's file and its labels and answers
by taxonomy ids, which are committed; nothing here holds a heading, tag or card text.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from debate_core.arguments.landscape.model_stage import Refusal, places_nothing, refusal_reason
from debate_core.arguments.landscape.review_queue import needs_review
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import ClassificationResult

__all__ = [
    "COUNTED_OUTCOMES",
    "NO_POSITION_KIND",
    "NO_POSITION_LABEL",
    "CardBreakdown",
    "CardOutcome",
    "DeterministicPlacement",
    "Score",
    "StratumScore",
    "card_outcome",
    "confusion",
    "deterministic_counts",
    "deterministic_placement",
    "label_kind",
    "model_set_score",
    "outcome_counts",
    "outcomes_by_label_kind",
    "refusals_by_label",
    "related",
    "score",
    "stratum_scores",
    "weighted_accuracy",
]

NO_POSITION_LABEL: Final = "none"
"""The coach's label for a card that argues no position, as `v1-e32-t21`'s sample and t07's evaluation
read it (not imported from the local classifier, which loads scikit-learn)."""

NO_POSITION_KIND: Final = NO_POSITION_LABEL
"""The kind a card the coach labelled none is counted under: it has no position, so no kind."""


class CardOutcome(StrEnum):
    """What became of one labelled card. Exactly one per card."""

    CORRECT = "correct"
    WRONG_POSITION_SAME_KIND = "wrong_position_same_kind"
    WRONG_KIND = "wrong_kind"
    PLACED_LABELLED_NONE = "placed_labelled_none"
    REFUSED = "refused"
    """The stage refused the model's answer; :attr:`CardBreakdown.refusal` says why."""
    BELOW_THRESHOLD = "below_threshold"
    LOST_TO_FAILED_BATCH = "lost_to_failed_batch"
    """Its batch's answer and the one repair both failed validation, so nothing was judged."""
    NOT_ASKED = "not_asked"
    """The stage stopped (a provider error) before its batch was answered."""
    NOT_FOUND = "not_found"
    """The store no longer holds the card: a removal has reached it since the sample was drawn."""


COUNTED_OUTCOMES: Final = frozenset(
    {
        CardOutcome.CORRECT,
        CardOutcome.WRONG_POSITION_SAME_KIND,
        CardOutcome.WRONG_KIND,
        CardOutcome.PLACED_LABELLED_NONE,
    }
)
"""The outcomes the evaluation counts: a MODEL placement at or above the review threshold."""


@dataclass(frozen=True, slots=True)
class DeterministicPlacement:
    """What stage one makes of a card: a position or none, by which method, and whether it goes on."""

    position_id: str | None
    method: str | None
    """The :class:`~debate_core.domain.landscape_classification.ClassificationMethod`; None for unplaced."""
    confidence: float
    sent_to_model: bool
    """Whether a real run sends the card to the model: unplaced, or placed below the review threshold."""

    @property
    def decided_none(self) -> bool:
        """The coach ruled the card's headings name no position: decided, never sent."""
        return self.method is not None and self.position_id is None


@dataclass(frozen=True, slots=True)
class CardBreakdown:
    """One labelled card: the coach's label, the model's answer and its outcome, and stage one's placement."""

    label: str
    """A position id of the taxonomy, or `none`."""
    label_kind: str
    """The label's position kind (`da`, `cp`...), or :data:`NO_POSITION_KIND`."""
    outcome: CardOutcome
    refusal: str | None = None
    """The :class:`~debate_core.arguments.landscape.model_stage.Refusal` of a refused answer."""
    answer: str | None = None
    """The position id the model named, placed or below the threshold; None when it placed nothing."""
    confidence: float | None = None
    deterministic: DeterministicPlacement | None = None
    """Stage one's placement of the same card; None for a card the store no longer holds."""
    sample_row: int | None = None
    """Its row in the coach's file."""
    stratum: str | None = None
    """The sample's stratum it was drawn from (`v1-e32-t21`)."""
    batch: int | None = None
    """The batch it was asked in, from 1; None when it was not asked."""
    related: bool = False
    """A wrong answer naming the label's parent or a child of it (an advantage and its aff)."""

    @property
    def counted(self) -> bool:
        return self.outcome in COUNTED_OUTCOMES


def label_kind(taxonomy: Taxonomy, label: str) -> str:
    """The kind of position `label` names, or :data:`NO_POSITION_KIND` for `none`."""
    return NO_POSITION_KIND if label == NO_POSITION_LABEL else taxonomy.resolve(label).kind.value


def related(taxonomy: Taxonomy, one: str, other: str) -> bool:
    """Whether either position is an ancestor of the other, through `parent` links."""
    return _ancestor(taxonomy, one, other) or _ancestor(taxonomy, other, one)


def _ancestor(taxonomy: Taxonomy, ancestor: str, of: str) -> bool:
    parent = taxonomy.resolve(of).parent
    while parent is not None:
        found = taxonomy.resolve(parent)
        if found.id == taxonomy.resolve(ancestor).id:
            return True
        parent = found.parent
    return False


def card_outcome(
    taxonomy: Taxonomy, label: str, result: ClassificationResult | None, *, threshold: float
) -> CardOutcome:
    """The one outcome of a found card labelled `label` whose MODEL result is `result` (None: unasked).

    Checked in the evaluation's own order: placing nothing first, then the threshold, then the label.
    """
    if result is None:
        return CardOutcome.NOT_ASKED
    if places_nothing(result):
        if refusal_reason(result) is Refusal.BATCH_REFUSED:
            return CardOutcome.LOST_TO_FAILED_BATCH
        return CardOutcome.REFUSED
    if result.confidence < threshold:
        return CardOutcome.BELOW_THRESHOLD
    if label == NO_POSITION_LABEL:
        return CardOutcome.PLACED_LABELLED_NONE
    if result.position_id == label:
        return CardOutcome.CORRECT
    if result.position_id is not None and label_kind(taxonomy, result.position_id) == label_kind(
        taxonomy, label
    ):
        return CardOutcome.WRONG_POSITION_SAME_KIND
    return CardOutcome.WRONG_KIND


def deterministic_placement(result: ClassificationResult, *, threshold: float) -> DeterministicPlacement:
    """Stage one's `result` for a card, and whether a run would send the card to the model."""
    return DeterministicPlacement(
        position_id=result.position_id,
        method=result.method.value if result.method is not None else None,
        confidence=result.confidence,
        sent_to_model=needs_review(result, threshold),
    )


def deterministic_counts(cards: Iterable[CardBreakdown]) -> dict[str, int]:
    """What stage one makes of the labelled cards, and how often its position is the coach's label.

    `sent_to_model` counts the cards a real run would send: the unplaced and the placed below the threshold.
    """
    found: Counter[str] = Counter()
    for card in cards:
        placed = card.deterministic
        if placed is None:
            found["not_found"] += 1
            continue
        found["sent_to_model"] += placed.sent_to_model
        if placed.decided_none:
            found["decided_none"] += 1
        elif placed.position_id is None:
            found["unplaced"] += 1
        else:
            state = "below_threshold" if placed.sent_to_model else "placed"
            found[state] += 1
            found[f"{state}_naming_the_label"] += placed.position_id == card.label
    keys = (
        "not_found",
        "unplaced",
        "decided_none",
        "below_threshold",
        "below_threshold_naming_the_label",
        "placed",
        "placed_naming_the_label",
        "sent_to_model",
    )
    return {key: found[key] for key in keys}


def outcome_counts(cards: Iterable[CardBreakdown]) -> dict[str, int]:
    """Cards by outcome, every outcome named, in :class:`CardOutcome`'s order: they sum to the cards."""
    found = Counter(card.outcome for card in cards)
    return {outcome.value: found[outcome] for outcome in CardOutcome}


def refusals_by_label(cards: Iterable[CardBreakdown]) -> dict[str, dict[str, int]]:
    """Refused answers by refusal, then by whether the coach labelled a position or none."""
    found: dict[str, Counter[str]] = {}
    for card in cards:
        if card.outcome is CardOutcome.REFUSED and card.refusal is not None:
            labelled = NO_POSITION_LABEL if card.label == NO_POSITION_LABEL else "position"
            found.setdefault(card.refusal, Counter())[labelled] += 1
    return {reason: dict(sorted(counts.items())) for reason, counts in sorted(found.items())}


def outcomes_by_label_kind(cards: Iterable[CardBreakdown]) -> dict[str, dict[str, int]]:
    """Outcomes by the kind of the coach's label, each kind's outcomes summing to its cards."""
    found: dict[str, Counter[CardOutcome]] = {}
    for card in cards:
        found.setdefault(card.label_kind, Counter())[card.outcome] += 1
    return {
        kind: {outcome.value: counts[outcome] for outcome in CardOutcome if counts[outcome]}
        for kind, counts in sorted(found.items())
    }


def confusion(cards: Iterable[CardBreakdown]) -> list[tuple[str, str, int]]:
    """`(label, answer, cards)`, most cards first: the answer is the position id the model named, or
    `none` for an answer naming no position, or the outcome of a card it gave no answer for."""
    found: Counter[tuple[str, str]] = Counter()
    for card in cards:
        if card.answer is not None:
            answer = card.answer
        elif card.refusal == Refusal.NO_POSITION.value:
            answer = NO_POSITION_LABEL
        else:
            answer = card.refusal or card.outcome.value
        found[(card.label, answer)] += 1
    return [(label, answer, count) for (label, answer), count in sorted(found.items(), key=_most_first)]


def _most_first(pair: tuple[tuple[str, str], int]) -> tuple[int, str, str]:
    (label, answer), count = pair
    return (-count, label, answer)


@dataclass(frozen=True, slots=True)
class Score:
    """Cards, the counted among them, and the right ones among those."""

    cards: int
    counted: int
    correct: int

    @property
    def accuracy(self) -> float | None:
        return self.correct / self.counted if self.counted else None


def score(cards: Iterable[CardBreakdown]) -> Score:
    """The evaluation's score over `cards`: counted, and correct among the counted."""
    chosen = list(cards)
    return Score(
        cards=len(chosen),
        counted=sum(card.counted for card in chosen),
        correct=sum(card.outcome is CardOutcome.CORRECT for card in chosen),
    )


def model_set_score(cards: Iterable[CardBreakdown]) -> Score:
    """The score over the cards a real run sends to the model (stage one unplaced or below the threshold):
    the set the bar applies to. A card stage one places surely, or the store no longer holds, is not in it."""
    return score(
        card for card in cards if card.deterministic is not None and card.deterministic.sent_to_model
    )


@dataclass(frozen=True, slots=True)
class StratumScore:
    """One stratum of the coach sample: its population, its labelled cards and their score."""

    name: str
    population: int
    """The unplaced cards the stratum was drawn from, sampled or not."""
    score: Score


def stratum_scores(
    cards: Sequence[CardBreakdown], populations: Mapping[str, int]
) -> tuple[StratumScore, ...]:
    """Each stratum of `populations`, in its order, with the labelled cards drawn from it."""
    return tuple(
        StratumScore(name, population, score(card for card in cards if card.stratum == name))
        for name, population in populations.items()
    )


def weighted_accuracy(strata: Iterable[StratumScore]) -> float | None:
    """The accuracy over every card of the strata's populations, each labelled card standing for
    `population / labelled` of its stratum: the right ones over the counted ones, both weighted.

    The sample draws its strata unevenly (`v1-e32-t21`), so the plain accuracy over it weighs a stratum by
    its share of the sample, not of the cards. None when no stratum has a counted card.
    """
    right = counted = 0.0
    for one in strata:
        if not one.score.cards:
            continue
        weight = one.population / one.score.cards
        right += weight * one.score.correct
        counted += weight * one.score.counted
    return right / counted if counted else None
