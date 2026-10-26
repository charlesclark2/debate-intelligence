"""The model stage's pure half: what a card sends, and what an answer may place (`v1-e32-t07`).

Stage one (`v1-e32-t02`'s matcher) places a card from its headings and tag. A card it leaves unplaced, or
places below the review threshold (a tag keyword alone), may go to a model. Never a card it placed at or
above the threshold, a card the coach ruled names no position, a section, or a document.

## What a card sends (:class:`ModelItem`)

The headings over it as the matcher reads them (normalized, with the disclosing teams' own names and the
caselist's schools taken out, and each heading's answer flag), and three pieces of free text, each read
as lowercase words by :func:`~debate_core.arguments.landscape.tag_scrub.card_tag`: the same names, every
school of the caselist and every word of every team code taken out.

* the tag;
* the short cite, at most :data:`CITE_WORDS` words;
* a bounded excerpt of the evidence: its first :data:`EXCERPT_WORDS` words, never the whole card.

No digest, path, file name, team, tournament or round goes with it. A batch names its cards `item-1`,
`item-2`... in the order it lists them.

## One card for many

Cards read alike (one :attr:`~debate_core.arguments.landscape.matcher.MatchItem.fingerprint`: the same
headings and tag) are placed alike and share one cached result, as stage one's are. So the model is asked
about each fingerprint once, through one card of it: the first in the reading's order. A fingerprint the
cards of many rounds share is asked about first (:func:`model_order`), so a capped run places the most
cards it can.

## What an answer may place (:func:`judge`)

The model answers a position id or none, a confidence and a rationale (`ModelPositionAnswers`). An answer
is refused, and its card stays where stage one left it, in the review queue, when:

* its position id is not an active id of the taxonomy version the run is under;
* its rationale repeats :data:`ECHO_WORDS` or more consecutive words of the card's evidence text or of its
  tag (:func:`echoes`): the model returns ids and a reason, never the card's own text;
* it names no position: only the coach decides that a card names none.

A refused answer is kept as a MODEL result placing nothing (:func:`refusal`), so the same card is not
asked about again under the same prompt version. Such a result never reaches the report: the service
keeps stage one's result for the card. An accepted answer becomes a MODEL result with the model's
confidence, the role the headings give (ANSWERS under an `AT:` heading, as the matcher's), and the
rationale it gave, which the review threshold then judges like any other.

Pure: values in, values out. Nothing here logs, and every value holding card text withholds it from
its `repr`.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from pydantic import JsonValue, ValidationError

from debate_core.arguments.landscape.headings import NormalizedHeading
from debate_core.arguments.landscape.matcher import tag_words
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import (
    RATIONALE_LIMIT,
    ClassificationMethod,
    ClassificationResult,
    ModelPositionAnswer,
    ModelPositionAnswers,
    PositionRole,
    checked_against,
)

__all__ = [
    "CITE_WORDS",
    "DEFAULT_BATCH_SIZE",
    "ECHO_WORDS",
    "EXCERPT_WORDS",
    "BatchProblem",
    "ModelCandidate",
    "ModelItem",
    "Refusal",
    "answer_problems",
    "batches",
    "bounded_words",
    "echoes",
    "item_label",
    "judge",
    "model_order",
    "places_nothing",
    "prompt_variables",
    "refusal",
    "refusal_reason",
]

EXCERPT_WORDS: Final = 120
"""The most words of a card's evidence a model is shown: its first 120, never the whole card."""

CITE_WORDS: Final = 12
"""The most words of a short cite a model is shown: an author and a date need fewer."""

ECHO_WORDS: Final = 12
"""A rationale repeating this many consecutive words of the card's evidence or tag is refused (ac2)."""

DEFAULT_BATCH_SIZE: Final = 20
"""Cards asked about in one call. Twenty answers fit the high-volume route's 2,048 output tokens."""


class Refusal(StrEnum):
    """Why an answer placed nothing."""

    UNKNOWN_POSITION = "UNKNOWN_POSITION"
    """Its position id is not an active id of the run's taxonomy version."""

    ECHOES_EVIDENCE = "ECHOES_EVIDENCE"
    """Its rationale repeats twelve or more consecutive words of the card's evidence or tag."""

    NO_POSITION = "NO_POSITION"
    """It named no position, which only the coach may decide."""

    BATCH_REFUSED = "BATCH_REFUSED"
    """The batch's answer, and its one repair, did not fit the schema or left a card unanswered."""


_REFUSED_RATIONALE: Final = {
    Refusal.UNKNOWN_POSITION: (
        "the model's answer was refused: it named a position id the taxonomy does not have"
    ),
    Refusal.ECHOES_EVIDENCE: (
        f"the model's answer was refused: its rationale repeated {ECHO_WORDS} or more consecutive words of "
        "the card"
    ),
    Refusal.NO_POSITION: "the model named no position; only the coach decides that a card names none",
    Refusal.BATCH_REFUSED: "the model's answer to its batch did not validate after one repair",
}


@dataclass(frozen=True, slots=True)
class ModelCandidate:
    """A card stage one could not place surely, standing for every card of the reading read alike."""

    fingerprint: str
    source_sha256: str
    first_element_index: int
    headings: tuple[NormalizedHeading, ...] = field(repr=False)
    tag: str | None = field(repr=False)
    """The tag as :func:`~debate_core.arguments.landscape.tag_scrub.card_tag` reads it: no names."""
    short_cite: str | None = field(repr=False)
    """The short cite, read the same way and cut to :data:`CITE_WORDS` words."""
    own_names: tuple[str, ...] = field(repr=False)
    """The disclosing teams' school, code and tournament, to take out of the excerpt; never sent."""
    cards: int = 1
    """How many of the reading's cards share this fingerprint."""


@dataclass(frozen=True, slots=True)
class ModelItem:
    """A candidate with its excerpt read: what one card of a batch sends, and what its answer meets."""

    candidate: ModelCandidate
    excerpt: str | None = field(repr=False)
    """The first :data:`EXCERPT_WORDS` words of the evidence, without names; None when the card has none."""
    evidence: str = field(default="", repr=False)
    """The card's whole evidence text, as stored: only to check a rationale against; never sent."""


def bounded_words(text: str | None, limit: int) -> str | None:
    """The first `limit` words of `text` (already words, one space apart), or None for no words."""
    if text is None:
        return None
    return " ".join(text.split()[:limit]) or None


def model_order(candidates: Iterable[ModelCandidate]) -> list[ModelCandidate]:
    """The order a run asks in: the most cards first, then by fingerprint, so every run asks alike."""
    return sorted(candidates, key=lambda one: (-one.cards, one.fingerprint))


def batches[T](items: Sequence[T], size: int = DEFAULT_BATCH_SIZE) -> list[Sequence[T]]:
    """`items` in runs of `size`, the last one shorter."""
    if size < 1:
        raise ValueError(f"a batch holds at least one card; got {size}")
    return [items[start : start + size] for start in range(0, len(items), size)]


def item_label(index: int) -> str:
    """The batch's name of its `index`-th card (from 0): `item-1` for the first."""
    return f"item-{index + 1}"


def prompt_variables(taxonomy: Taxonomy, batch: Sequence[ModelItem]) -> dict[str, JsonValue]:
    """The `landscape.classify_position` variables for one batch: the positions, then the cards, as JSON.

    Keys are sorted and nothing depends on time or order of construction, so one batch always has one
    fixture key. The positions are the taxonomy's committed text; the cards are what :class:`ModelItem`
    holds and nothing else.
    """
    positions = [
        {
            "id": one.id,
            "kind": one.kind.value,
            "label": one.label,
            "side": one.side.value,
            **({"parent": taxonomy.resolve(one.parent).id} if one.parent is not None else {}),
            **({"description": one.description} if one.description.strip() else {}),
        }
        for one in taxonomy.active_positions
    ]
    items = [
        {
            "item": item_label(index),
            "headings": [heading.text for heading in item.candidate.headings],
            "under_an_answer_heading": any(heading.answer for heading in item.candidate.headings),
            "tag": item.candidate.tag,
            "cite": item.candidate.short_cite,
            "excerpt": item.excerpt,
        }
        for index, item in enumerate(batch)
    ]
    return {
        "taxonomy_version": taxonomy.taxonomy_version,
        "positions": _json(positions),
        "items": _json(items),
    }


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, indent=1)


@dataclass(frozen=True, slots=True)
class BatchProblem:
    """One thing wrong with a batch's answer as a whole, in labels and counts only."""

    type: str
    msg: str


def answer_problems(answers: ModelPositionAnswers, size: int) -> tuple[BatchProblem, ...]:
    """What is wrong with a batch's answer as a whole: a card unanswered, answered twice, or not asked about.

    The guard repairs an answer with any of these once, then refuses it. A problem names labels and
    counts, never the answer's text.
    """
    asked = {item_label(index) for index in range(size)}
    seen: dict[str, int] = {}
    for answer in answers.answers:
        seen[answer.item] = seen.get(answer.item, 0) + 1
    problems = [
        BatchProblem("unknown_item", f"{label} is not an item of the request")
        for label in sorted(set(seen) - asked, key=_label_number)
    ]
    problems += [
        BatchProblem("missing_item", f"{label} has no answer")
        for label in sorted(asked - set(seen), key=_label_number)
    ]
    problems += [
        BatchProblem("duplicate_item", f"{label} is answered {seen[label]} times")
        for label in sorted(
            (one for one, count in seen.items() if count > 1 and one in asked), key=_label_number
        )
    ]
    return tuple(problems)


def _label_number(label: str) -> int:
    return int(label.removeprefix("item-"))


def echoes(rationale: str, text: str | None, run: int = ECHO_WORDS) -> bool:
    """Whether `rationale` repeats `run` or more consecutive words of `text`, as lowercase words."""
    if not text:
        return False
    said = tag_words(rationale).split()
    if len(said) < run:
        return False
    source = tag_words(text).split()
    if len(source) < run:
        return False
    runs = {tuple(source[start : start + run]) for start in range(len(source) - run + 1)}
    return any(tuple(said[start : start + run]) in runs for start in range(len(said) - run + 1))


def judge(
    answer: ModelPositionAnswer,
    item: ModelItem,
    *,
    taxonomy: Taxonomy,
    prompt_id: str,
    prompt_version: str,
    model_id: str,
) -> ClassificationResult:
    """The MODEL result `answer` gives `item`: a placement, or a :func:`refusal` placing nothing."""

    def refused(reason: Refusal) -> ClassificationResult:
        return refusal(
            reason,
            taxonomy_version=taxonomy.taxonomy_version,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            model_id=model_id,
        )

    if answer.position_id is None:
        return refused(Refusal.NO_POSITION)
    if echoes(answer.rationale, item.evidence) or echoes(answer.rationale, item.candidate.tag):
        return refused(Refusal.ECHOES_EVIDENCE)
    answers = any(heading.answer for heading in item.candidate.headings)
    try:
        return checked_against(
            taxonomy,
            ClassificationResult(
                position_id=answer.position_id,
                role=PositionRole.ANSWERS if answers else PositionRole.READS,
                confidence=answer.confidence,
                rationale=answer.rationale[:RATIONALE_LIMIT],
                method=ClassificationMethod.MODEL,
                taxonomy_version=taxonomy.taxonomy_version,
                prompt_id=prompt_id,
                prompt_version=prompt_version,
                model_id=model_id,
            ),
        )
    except ValidationError:
        return refused(Refusal.UNKNOWN_POSITION)


def refusal(
    reason: Refusal, *, taxonomy_version: str, prompt_id: str, prompt_version: str, model_id: str
) -> ClassificationResult:
    """The MODEL result kept for a refused answer: no position, confidence 0, and why; never the answer."""
    return ClassificationResult(
        position_id=None,
        role=None,
        confidence=0.0,
        rationale=_REFUSED_RATIONALE[reason],
        method=ClassificationMethod.MODEL,
        taxonomy_version=taxonomy_version,
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        model_id=model_id,
    )


def places_nothing(result: ClassificationResult) -> bool:
    """Whether `result` is a MODEL result that placed nothing: stage one's result stands for its card."""
    return result.method is ClassificationMethod.MODEL and result.position_id is None


def refusal_reason(result: ClassificationResult) -> Refusal | None:
    """Which :class:`Refusal` a result :func:`places_nothing` records; None for any other result."""
    if not places_nothing(result):
        return None
    return next((reason for reason, text in _REFUSED_RATIONALE.items() if text == result.rationale), None)
