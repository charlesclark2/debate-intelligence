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

A student meets neither stage alone (`v1-e32-t43`): a run places what the headings place surely, and asks
the model about the rest. :func:`pipeline_score` scores the labelled cards that way, a card stage one
places surely on that placement and every other on the model's answer, beside :func:`model_alone_score`,
the model's answers for every card. The bar reads the pipeline's accuracy (the PM's ruling, 2026-11-02).

A card the coach gave a second label (`v1-e32-t41`) is correct when the answer names either label
(:func:`second_label_counts` counts those right on the second); a wrong answer, its kind and the confusion
table are judged against the first label.

Pure: values in, values out. A card is named by its row in the coach's file and its labels and answers
by taxonomy ids, which are committed; nothing here holds a heading, tag or card text.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from debate_core.arguments.landscape.model_stage import Refusal, places_nothing, refusal_reason
from debate_core.arguments.landscape.review_queue import needs_review
from debate_core.arguments.landscape.side_role import OPPOSITE_SIDES, readable_sides, side_role
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import ClassificationResult, PositionRole, Stance

__all__ = [
    "ANSWERS_PREFIX",
    "COUNTED_OUTCOMES",
    "NO_POSITION_KIND",
    "NO_POSITION_LABEL",
    "CardBreakdown",
    "CardOutcome",
    "DeterministicPlacement",
    "GENERIC_POSITION_PREFIX",
    "GenericAnswers",
    "LabelledScore",
    "Score",
    "StratumScore",
    "card_outcome",
    "confusion",
    "deterministic_counts",
    "deterministic_placement",
    "generic_answer_counts",
    "generic_positions",
    "label_kind",
    "model_alone_score",
    "model_set_score",
    "outcome_counts",
    "outcomes_by_label_kind",
    "pipeline_score",
    "placed_by_headings",
    "refusals_by_label",
    "related",
    "score",
    "labelled_as",
    "scored_stance",
    "second_label_counts",
    "stratum_scores",
    "weighted_accuracy",
]

NO_POSITION_LABEL: Final = "none"
"""The coach's label for a card that argues no position, as `v1-e32-t21`'s sample and t07's evaluation
read it (not imported from the local classifier, which loads scikit-learn)."""

NO_POSITION_KIND: Final = NO_POSITION_LABEL
"""The kind a card the coach labelled none is counted under: it has no position, so no kind."""

ANSWERS_PREFIX: Final = "at:"
"""How the coach writes a label for a card that answers a position: `at:politics-da` (`v1-e32-t46`)."""


class CardOutcome(StrEnum):
    """What became of one labelled card. Exactly one per card."""

    CORRECT = "correct"
    WRONG_STANCE = "wrong_stance"
    """The label's position (or the second label's) with the other stance (`v1-e32-t46`)."""
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
        CardOutcome.WRONG_STANCE,
        CardOutcome.WRONG_POSITION_SAME_KIND,
        CardOutcome.WRONG_KIND,
        CardOutcome.PLACED_LABELLED_NONE,
    }
)
"""The outcomes the evaluation counts: a MODEL placement at or above the review threshold. A wrong stance is
counted, and wrong (the PM's ruling for `v1-e32-t46`)."""


@dataclass(frozen=True, slots=True)
class DeterministicPlacement:
    """What stage one makes of a card: a position or none, by which method, and whether it goes on."""

    position_id: str | None
    method: str | None
    """The :class:`~debate_core.domain.landscape_classification.ClassificationMethod`; None for unplaced."""
    confidence: float
    sent_to_model: bool
    """Whether a real run sends the card to the model: unplaced, or placed below the review threshold."""
    stance: Stance | None = None
    """Its stance as scored (:func:`scored_stance`); None when it places no position."""

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
    also: str | None = None
    """The second position id the coach accepts (`v1-e32-t41`); None when the sample gives none."""
    stance: Stance = Stance.READS
    """The stance of the coach's label: ANSWERS for `at:<id>` (`v1-e32-t46`)."""
    also_stance: Stance = Stance.READS
    """The stance of the second label."""
    answer_stance: Stance | None = None
    """The answer's stance as scored (:func:`scored_stance`); None when the model placed nothing."""

    @property
    def counted(self) -> bool:
        return self.outcome in COUNTED_OUTCOMES

    @property
    def correct_on_second_label(self) -> bool:
        """Scored correct because the answer names the second label, with its stance, not the first."""
        if self.outcome is not CardOutcome.CORRECT or self.also is None or self.answer is None:
            return False
        answered = (self.answer, self.answer_stance or Stance.READS)
        return answered == (self.also, self.also_stance) and answered != (self.label, self.stance)


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


def labelled_as(position_id: str, stance: Stance) -> str:
    """A label or an answer as the coach writes it: the id, or `at:<id>` for one that answers."""
    return f"{ANSWERS_PREFIX}{position_id}" if stance is Stance.ANSWERS else position_id


GENERIC_POSITION_PREFIX: Final = "generic-"
"""The id prefix of a kind's generic position (`generic-k`, `generic-theory`): the one whose description says
it fits no named position of its kind, which the classify prompt sends a card of that kind to
(`v1-e32-t40`)."""


def generic_positions(taxonomy: Taxonomy) -> dict[str, str]:
    """Each active generic position of `taxonomy`, by id, with its kind's value."""
    return {
        one.id: one.kind.value
        for one in taxonomy.active_positions
        if one.id.startswith(GENERIC_POSITION_PREFIX)
    }


@dataclass(frozen=True, slots=True)
class GenericAnswers:
    """The model's answers naming a generic position, on their own (the PM's condition on prompt 1.3.0's
    generic-confidence clause, `v1-e32-t49`)."""

    answers: int = 0
    """Answers naming a generic position, at any confidence."""
    above_threshold: int = 0
    """Of those, the ones counted: at or above the review threshold."""
    correct: int = 0
    """Of the counted, the ones the coach's label (or second label) agrees with."""
    wrong: int = 0
    """Of the counted, the rest."""
    named_label_rows: tuple[int, ...] = ()
    """The sample rows labelled with a named position of a generic's kind that the model answered with that
    generic position, at any confidence, unless the answer is scored right (a second label the coach gave): a
    named kritik's card turning generic, the clause's other risk."""


def generic_answer_counts(cards: Iterable[CardBreakdown], generic: Mapping[str, str]) -> GenericAnswers:
    """The answers among `cards` naming one of the `generic` positions (id to kind:
    :func:`generic_positions`)."""
    named = [card for card in cards if card.answer is not None and card.answer in generic]
    counted = [card for card in named if card.counted]
    correct = sum(card.outcome is CardOutcome.CORRECT for card in counted)
    return GenericAnswers(
        answers=len(named),
        above_threshold=len(counted),
        correct=correct,
        wrong=len(counted) - correct,
        named_label_rows=tuple(
            sorted(
                card.sample_row
                for card in named
                if card.sample_row is not None
                and card.label not in generic
                and card.label_kind == generic[card.answer or ""]
                and card.outcome is not CardOutcome.CORRECT
            )
        ),
    )


def scored_stance(
    taxonomy: Taxonomy, position_id: str, role: PositionRole | None, file_sides: Collection[str] = ()
) -> Stance:
    """The stance a placement of `position_id` is scored with: the report's (`v1-e32-t46`, `v1-e32-t49`).

    Its role first takes its file's own side (:func:`~debate_core.arguments.landscape.side_role.side_role`:
    READS when every readable side its file was disclosed on, `file_sides`, the disclosures'
    :class:`~debate_core.domain.caselist.Side` values, is the position's own). Then ANSWERS when that role is
    ANSWERS, or when every readable side is the side opposite the position's: the landscape report never
    counts either as a read. READS otherwise, a position either side reads and a file on no readable side
    among them.
    """
    if side_role(taxonomy, position_id, role, file_sides) is PositionRole.ANSWERS:
        return Stance.ANSWERS
    opposite = OPPOSITE_SIDES.get(taxonomy.resolve(position_id).side)
    if opposite is not None and readable_sides(file_sides) == frozenset({opposite}):
        return Stance.ANSWERS
    return Stance.READS


def card_outcome(
    taxonomy: Taxonomy,
    label: str,
    result: ClassificationResult | None,
    *,
    threshold: float,
    also: str | None = None,
    stance: Stance = Stance.READS,
    also_stance: Stance = Stance.READS,
    file_sides: Collection[str] = (),
) -> CardOutcome:
    """The one outcome of a found card labelled `label` whose MODEL result is `result` (None: unasked).

    Checked in the evaluation's own order: placing nothing first, then the threshold, then the label. An
    answer naming `also`, the coach's second label, is correct too; a wrong one is judged against `label`.
    An answer is right when it names a label's position with that label's `stance` (`v1-e32-t46`), its own
    scored by :func:`scored_stance` from its role and the `file_sides` of the card's file; one naming a
    label's position with the other stance is :attr:`~CardOutcome.WRONG_STANCE`.
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
    if result.position_id is None:
        return CardOutcome.WRONG_KIND
    answered = (result.position_id, scored_stance(taxonomy, result.position_id, result.role, file_sides))
    labels = [(label, stance)] + ([(also, also_stance)] if also is not None else [])
    if answered in labels:
        return CardOutcome.CORRECT
    if result.position_id in (label, also):
        return CardOutcome.WRONG_STANCE
    if label_kind(taxonomy, result.position_id) == label_kind(taxonomy, label):
        return CardOutcome.WRONG_POSITION_SAME_KIND
    return CardOutcome.WRONG_KIND


def deterministic_placement(
    result: ClassificationResult,
    *,
    threshold: float,
    taxonomy: Taxonomy | None = None,
    file_sides: Collection[str] = (),
) -> DeterministicPlacement:
    """Stage one's `result` for a card, and whether a run would send the card to the model.

    With `taxonomy`, a placement carries its stance as scored (:func:`scored_stance`), from its role and the
    `file_sides` of the card's file (`v1-e32-t46`).
    """
    stance = (
        scored_stance(taxonomy, result.position_id, result.role, file_sides)
        if taxonomy is not None and result.position_id is not None
        else None
    )
    return DeterministicPlacement(
        position_id=result.position_id,
        method=result.method.value if result.method is not None else None,
        confidence=result.confidence,
        sent_to_model=needs_review(result, threshold),
        stance=stance,
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


def second_label_counts(cards: Iterable[CardBreakdown]) -> dict[str, int]:
    """The cards the coach gave a second label, and those scored correct on it."""
    chosen = [card for card in cards if card.also is not None]
    return {"cards": len(chosen), "correct": sum(card.correct_on_second_label for card in chosen)}


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
            answer = labelled_as(card.answer, card.answer_stance or Stance.READS)
        elif card.refusal == Refusal.NO_POSITION.value:
            answer = NO_POSITION_LABEL
        else:
            answer = card.refusal or card.outcome.value
        found[(labelled_as(card.label, card.stance), answer)] += 1
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
class LabelledScore:
    """Every labelled card scored one way: by the model alone, or by the pipeline (`v1-e32-t43`).

    `counted` are the cards placed at or above the review threshold, what a report shows; `refused` the
    model's answers naming no position, and `below_threshold` its placements under the threshold, neither
    counted. :attr:`coverage` is the counted over the labelled.
    """

    labelled: int
    counted: int
    correct: int
    refused: int
    below_threshold: int
    by_headings: int = 0
    """Of the counted, the cards stage one placed surely, scored on that placement (the pipeline only)."""
    decided_none: int = 0
    """Cards a coach's override decides argue no position: never sent, never counted (the pipeline only)."""

    @property
    def accuracy(self) -> float | None:
        return self.correct / self.counted if self.counted else None

    @property
    def coverage(self) -> float | None:
        return self.counted / self.labelled if self.labelled else None


def placed_by_headings(card: CardBreakdown) -> bool:
    """Whether stage one places `card` surely: a run never sends it, and the pipeline scores its placement."""
    placed = card.deterministic
    return placed is not None and not placed.sent_to_model and placed.position_id is not None


def model_alone_score(cards: Iterable[CardBreakdown]) -> LabelledScore:
    """The model's answers for every labelled card, whatever stage one made of it: the evaluation's own."""
    chosen = list(cards)
    return LabelledScore(
        labelled=len(chosen),
        counted=sum(card.counted for card in chosen),
        correct=sum(card.outcome is CardOutcome.CORRECT for card in chosen),
        refused=sum(card.outcome is CardOutcome.REFUSED for card in chosen),
        below_threshold=sum(card.outcome is CardOutcome.BELOW_THRESHOLD for card in chosen),
    )


def pipeline_score(cards: Iterable[CardBreakdown]) -> LabelledScore:
    """The labelled cards as students meet them: a card stage one places surely is scored on that placement,
    a card a coach's override decides is no position is not counted, and every other on the model's answer."""
    chosen = list(cards)
    by_headings = [card for card in chosen if placed_by_headings(card)]
    decided = [card for card in chosen if card.deterministic is not None and card.deterministic.decided_none]
    by_model = model_alone_score(
        card for card in chosen if card.deterministic is None or card.deterministic.sent_to_model
    )
    return LabelledScore(
        labelled=len(chosen),
        counted=len(by_headings) + by_model.counted,
        correct=sum(_names_a_label(card) for card in by_headings) + by_model.correct,
        refused=by_model.refused,
        below_threshold=by_model.below_threshold,
        by_headings=len(by_headings),
        decided_none=len(decided),
    )


def _names_a_label(card: CardBreakdown) -> bool:
    """Whether stage one's placement of `card` is the coach's label or second label, each with its stance;
    never for `none`."""
    placed = card.deterministic
    if placed is None or placed.position_id is None:
        return False
    answered = (placed.position_id, placed.stance or Stance.READS)
    labels = [(card.label, card.stance)] + ([(card.also, card.also_stance)] if card.also is not None else [])
    return answered in labels


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
