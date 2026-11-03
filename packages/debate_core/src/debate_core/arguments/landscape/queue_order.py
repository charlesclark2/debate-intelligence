"""The review queue ordered by the local proxy model's confidence, which places nothing (`v1-e32-t26`).

`v1-e32-t21` found its proxy model (a card's tag and the headings that place nothing on their own,
TF-IDF word 1- and 2-grams with a logistic regression) fit to order the review queue, not to place
cards: on the coach's sample its confidence ranked well (13 of 24 right at or above its threshold, 4
of 17 just below, 0 of 6 far below) and its guess was often wrong. So it orders the queue and
suggests, and nothing else reads it.

## What it reads

A card as t21's feature table holds it (:func:`card_features`): its normalized headings, which of
them place a card on their own, and its tag as words without the disclosing teams' names, the
caselist's schools or any team code. :func:`card_tokens` turns that into the model's tokens, exactly
as t21 trained it. Never a school, a team code, a name, a cite or the card's text.

## The model (:class:`QueueOrderModel`)

The weights of a trained proxy, written out once by `scripts/compare_local_classifier.py
train-queue-order` and scored here in plain Python: no scikit-learn, so an installed build, which
has none, orders its queue too. It gives the probabilities scikit-learn gives, to rounding.

## The order (:func:`order_review_queue`)

A row of the queue is a heading. Its score is how surely the model puts the cards under it under one
position: for each position, the sum of the confidences of the row's cards predicted as it, divided
by all the row's cards, scored or not; the row's score is the largest of these, and that position is
its guess. A row of one card scores that card's confidence; a row whose cards disagree, or that the
model knows little of, scores less.

* Rows the model scores come first, highest score first. Rows with equal scores keep today's order
  among themselves.
* Rows it cannot score (no card under them has a feature it knows, or only sections sit under them)
  follow, in today's order.
* A row's guess is shown as its suggestion only when its score is at or above t21's threshold, the
  confidence from which the proxy's held-out precision stays at 90% (:attr:`QueueOrderModel.suggest_from`).
  Below it the row shows no position, only its place in the order.

The rows' counts and the queue's counts are left as they are, and no item is placed: the coach's
`decision` column stays empty for the coach.

Pure: values in, values out. A value that holds a heading, a tag or a weight withholds it from its `repr`.
"""

from __future__ import annotations

import base64
import math
import operator
import sys
from array import array
from collections import Counter, defaultdict
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from itertools import pairwise
from typing import Any, cast

from debate_core.arguments.landscape.matcher import MatchItem, PositionMatcher
from debate_core.arguments.landscape.review_queue import QueuedItem, ReviewQueue
from debate_core.arguments.landscape.source_headings import CaselistNames
from debate_core.arguments.landscape.tag_scrub import card_tag
from debate_core.domain.landscape_classification import ItemKind

__all__ = [
    "CardFeatures",
    "Prediction",
    "QueueOrderModel",
    "RowScore",
    "card_features",
    "card_tokens",
    "order_review_queue",
    "row_scores",
]


@dataclass(frozen=True, slots=True)
class Prediction:
    position_id: str
    confidence: float
    """The model's probability for that position: the largest it gives."""


# ------------------------------------------------------------------------------------------------
# What it reads
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CardFeatures:
    """A card as the classifier reads it: its headings, which of them place on their own, and its tag."""

    headings: tuple[str, ...] = field(repr=False)
    """The non-empty normalized headings over the card, outermost first, names taken out."""
    placing: tuple[bool, ...]
    """For each heading, whether it places a card on its own: an alias, or an override naming a position."""
    tag: str | None = field(repr=False)
    """The tag as words, the teams' own names, the caselist's schools and every team code taken out."""


def card_features(
    item: MatchItem,
    own_names: Sequence[str],
    caselist: CaselistNames,
    matcher: PositionMatcher,
    codes: Collection[str] = frozenset(),
) -> CardFeatures:
    """`item`, a card the matcher read, as t21's feature table holds it."""
    headings = tuple(heading.text for heading in item.headings)
    return CardFeatures(
        headings=headings,
        placing=tuple(matcher.placing_index([text]) is not None for text in headings),
        tag=card_tag(item.tag, own_names, caselist, codes),
    )


def card_tokens(
    headings: Sequence[str],
    placing: Sequence[bool],
    tag: str | None,
    *,
    without_placing_headings: bool = False,
) -> tuple[str, ...]:
    """A card's word 1- and 2-grams: each heading's as `h:` tokens, the tag's as `t:` tokens.

    A phrase never runs from one heading into the next, or from a heading into the tag. With
    `without_placing_headings`, a heading that places a card on its own is left out, as no heading over
    an unplaced card does.
    """
    found: list[str] = []
    for text, places in zip(headings, placing, strict=True):
        if not (without_placing_headings and places):
            found += _grams("h", text.split())
    if tag:
        found += _grams("t", tag.split())
    return tuple(found)


def _grams(prefix: str, words: Sequence[str]) -> list[str]:
    return [f"{prefix}:{word}" for word in words] + [f"{prefix}:{one} {two}" for one, two in pairwise(words)]


# ------------------------------------------------------------------------------------------------
# The model
# ------------------------------------------------------------------------------------------------


def _packed(values: Iterable[float]) -> str:
    packed = array("d", values)
    if sys.byteorder != "little":
        packed.byteswap()
    return base64.b64encode(packed.tobytes()).decode("ascii")


def _unpacked(text: str) -> array[float]:
    unpacked = array("d")
    unpacked.frombytes(base64.b64decode(text.encode("ascii"), validate=True))
    if sys.byteorder != "little":
        unpacked.byteswap()
    return unpacked


@dataclass(frozen=True, slots=True)
class QueueOrderModel:
    """A trained proxy's weights: sublinear, L2-normed TF-IDF over its vocabulary, then a logistic regression.

    `coefficients` holds, token by token, one weight per class (one in all for two classes, as
    scikit-learn keeps a binary model). Scoring needs nothing but these numbers.
    """

    classes: tuple[str, ...]
    vocabulary: tuple[str, ...] = field(repr=False)
    idf: array[float] = field(repr=False)
    coefficients: array[float] = field(repr=False)
    intercepts: tuple[float, ...] = field(repr=False)
    suggest_from: float | None
    """t21's threshold for this model: the lowest confidence from which its held-out precision stays at
    90% (`HeldOutMeasure.confidence_at_target`). None when no confidence reached it: nothing is suggested."""
    without_placing_headings: bool = True
    """Whether it was trained without the headings that place on their own, as the proxy is."""
    _index: Mapping[str, int] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        width = len(self.intercepts)
        if len(self.classes) < 2 or width != (1 if len(self.classes) == 2 else len(self.classes)):
            raise ValueError("a model has two classes or more, and one intercept per class (one for two)")
        if len(self.idf) != len(self.vocabulary) or len(self.coefficients) != len(self.vocabulary) * width:
            raise ValueError("a model has one weight per token, and one coefficient per token and class")
        object.__setattr__(self, "_index", {token: number for number, token in enumerate(self.vocabulary)})

    def tokens(self, features: CardFeatures) -> tuple[str, ...]:
        """`features` as this model reads them."""
        return card_tokens(
            features.headings,
            features.placing,
            features.tag,
            without_placing_headings=self.without_placing_headings,
        )

    def predict(self, tokens: Sequence[str]) -> Prediction | None:
        """The likeliest position for a card of `tokens`, and its probability; None with no known token."""
        counts = Counter(number for token in tokens if (number := self._index.get(token)) is not None)
        if not counts:
            return None
        weights = {number: (1.0 + math.log(count)) * self.idf[number] for number, count in counts.items()}
        norm = math.sqrt(math.fsum(weight * weight for weight in weights.values()))
        width = len(self.intercepts)
        scores = list(self.intercepts)
        for number, weight in sorted(weights.items()):
            column = self.coefficients[number * width : (number + 1) * width]
            scores = list(map(operator.add, scores, map((weight / norm).__mul__, column)))
        if width == 1:
            positive = 1.0 / (1.0 + math.exp(-scores[0]))
            probabilities = [1.0 - positive, positive]
        else:
            top = max(scores)
            exponents = [math.exp(score - top) for score in scores]
            total = math.fsum(exponents)
            probabilities = [one / total for one in exponents]
        best = max(range(len(probabilities)), key=probabilities.__getitem__)
        return Prediction(self.classes[best], probabilities[best])

    def to_json(self) -> dict[str, object]:
        """The weights as JSON values, the arrays packed as little-endian doubles."""
        return {
            "classes": list(self.classes),
            "vocabulary": list(self.vocabulary),
            "idf": _packed(self.idf),
            "coefficients": _packed(self.coefficients),
            "intercepts": list(self.intercepts),
            "suggest_from": self.suggest_from,
            "without_placing_headings": self.without_placing_headings,
        }

    @classmethod
    def from_json(cls, data: Mapping[str, object]) -> QueueOrderModel:
        """A model :meth:`to_json` wrote. Raises `ValueError` on a malformed one."""
        try:
            suggest_from = data["suggest_from"]
            return cls(
                classes=tuple(str(one) for one in cast(list[Any], data["classes"])),
                vocabulary=tuple(str(one) for one in cast(list[Any], data["vocabulary"])),
                idf=_unpacked(str(data["idf"])),
                coefficients=_unpacked(str(data["coefficients"])),
                intercepts=tuple(float(one) for one in cast(list[Any], data["intercepts"])),
                suggest_from=None if suggest_from is None else float(cast(float, suggest_from)),
                without_placing_headings=bool(data["without_placing_headings"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"not a review-order model: {type(error).__name__}") from None


# ------------------------------------------------------------------------------------------------
# The order
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RowScore:
    """How surely the model puts a row's cards under one position, and that position."""

    confidence: float
    position_id: str


def row_scores(
    items: Sequence[QueuedItem], predictions: Sequence[Prediction | None]
) -> dict[tuple[str, bool], RowScore]:
    """Each `(heading, answer)` row's score, from its queued items and their predictions, item by item.

    A row's cards are the card items under its heading, as :func:`~debate_core.arguments.landscape.
    review_queue.build_review_queue` counts them. A row none of whose cards has a prediction has no
    score. Two positions with the same sum: the first by id.
    """
    if len(items) != len(predictions):
        raise ValueError("one prediction, or None, per queued item")
    cards: Counter[tuple[str, bool]] = Counter()
    sums: dict[tuple[str, bool], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for item, prediction in zip(items, predictions, strict=True):
        if item.kind is not ItemKind.CARD:
            continue
        for heading in {(one.text, one.answer) for one in item.headings}:
            cards[heading] += 1
            if prediction is not None:
                sums[heading][prediction.position_id] += prediction.confidence
    scores: dict[tuple[str, bool], RowScore] = {}
    for heading, found in sums.items():
        position_id = min(found, key=lambda one: (-found[one], one))
        scores[heading] = RowScore(found[position_id] / cards[heading], position_id)
    return scores


def order_review_queue(
    queue: ReviewQueue, scores: Mapping[tuple[str, bool], RowScore], suggest_from: float | None
) -> ReviewQueue:
    """`queue` with its scored rows first, highest score first, then the rest, each kept in today's order.

    A scored row carries its score, and its guess as a suggestion when the score is at or above
    `suggest_from`. The counts are the queue's own.
    """
    scored = [
        (row, scores[key]) for row in queue.rows if (key := (row.normalized_heading, row.answer)) in scores
    ]
    scored.sort(key=lambda pair: -pair[1].confidence)
    rows = [
        replace(
            row,
            proxy_confidence=score.confidence,
            suggested_position=score.position_id
            if suggest_from is not None and score.confidence >= suggest_from
            else None,
        )
        for row, score in scored
    ]
    rows += [row for row in queue.rows if (row.normalized_heading, row.answer) not in scores]
    return ReviewQueue(rows=tuple(rows), counts=queue.counts)
