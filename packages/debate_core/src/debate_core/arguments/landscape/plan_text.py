"""A Policy affirmative file's plan text, found and read for the aff it names (`v1-e32-t09`).

Headings name the plan in under a fifth of hspolicy26's affirmative files. The plan text names it
far more often: a short paragraph, almost always an analytic, directly under a heading or label
such as `Plan`, `Plan Text` or `PT`. The parsed card store keeps cards only, so the plan text is
read from the source's own paragraphs (:func:`paragraphs_of`), and only what is derived from it is
kept: where it is, its unit, its shape, a digest of its words and the positions it names. Never
the text (the PM's rulings of 2026-10-24).

## Finding it (:func:`read_plan_texts`)

* **A label** is a short paragraph that t01's normalizer reduces to one of
  :data:`PLAN_TEXT_LABELS` (`Plan`, `1AC - Plan Text`, `PT:`), whatever its unit: a block heading
  most often, a hat or pocket sometimes.
* **Its plan text** is the next paragraph with any text in it that is not itself a label. A label
  holding its text inline (`Plan: The United States federal government should ...`) is its own
  plan text.
* **Kept** says whether the paragraph is inside a card the store holds. Almost none is.
* **Shaped** says whether it reads like a plan text: the word `should` with a federal actor before
  it (`United States federal government`, `USFG`). It decides nothing about the aff; it tells a plan
  text that names no aff from a label over something else.
* **Not a plan text** is a text with `should` but no federal actor before it, such as a counterplan
  whose actor is the fifty states that sits under a plan label in an affirmative file. It names
  nothing and is not shaped (the PM's context for ac3, 2026-10-24).

## What it names (:class:`PlanTextVocabulary`)

Every aff position's aliases and tag keywords, matched as whole words. A retired position's words
count under the position it was merged into, and name nothing when it was retired with nowhere to
go. A child named with its parent wins; two affs neither of which is the other's ancestor, two
children of one parent included, are a conflict, and name nothing. The resolutional aff (below) is the
least specific: beside another aff it gives way to it, so it never makes a conflict.
`medicare for all` and `m4a` named single payer until the coach named its Medicare for All child,
whose keywords now hold them (the PM's rulings of 2026-10-24); no word names an aff from here, only
from the taxonomy.

**The resolutional plan** (:class:`ResolutionalPlanWords`, the PM's context for ac3). Most plan
texts that name no aff say the resolution and little else. A shaped plan text that names no aff
names the topic's resolutional aff when every word of it outside the frame is a resolutional word:
the frame is the English joining words the coach's sheet drops and the topic's frame words (those in
at least 80% of the sheet's plan texts), and the resolutional words are those of the clusters the
coach marked as the resolutional aff. Both lists are config, `config/landscape/plan_texts/`.

## A document's verdict (:func:`document_plan_text`)

`NAMES` one aff, `CONFLICTING` when its plan texts name two, `UNNAMED` when it holds a shaped plan
text that names none, `NONE` when it holds no plan text at all, and `UNREAD` for a source that could
not be parsed. Only `NAMES` identifies a round (`PLAN_TEXT`); `NONE` is the only verdict a team's aff
may be carried into (:mod:`~debate_core.arguments.landscape.aff_assignment`).

**K-aff markers** (`v1-e32-t17`) are read from the same paragraphs, in the same pass and cache, when
the topic has a K-aff config (:class:`PlanTextVocabulary`'s `kritikal`; the reading is
:func:`~debate_core.arguments.landscape.kritikal_aff.read_kritikal_markers`), and the vocabulary's
digest covers that config, so an edit to it reads every source again.

Pure and deterministic: no I/O, no model, and nothing returned or logged holds a paragraph's text.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import Field, StringConstraints

from debate_core.arguments.landscape.headings import normalize_heading
from debate_core.arguments.landscape.kritikal_aff import KritikalAffConfig, kritikal_rules
from debate_core.arguments.landscape.matcher import tag_words
from debate_core.domain.base import DomainModel
from debate_core.domain.debate_files import ParsedDocument
from debate_core.domain.landscape import POSITION_ID_PATTERN, PositionKind, Taxonomy
from debate_core.domain.style_profile import StructuralUnit

__all__ = [
    "JOINING_WORDS",
    "PLAN_TEXT_LABELS",
    "DocumentPlanText",
    "Paragraph",
    "PlanTextParagraph",
    "PlanTextVerdict",
    "PlanTextVocabulary",
    "ResolutionalPlanWords",
    "document_plan_text",
    "paragraphs_of",
    "plan_text_words",
    "read_back_plan_texts",
    "read_plan_texts",
    "sheet_plan_texts",
]

PLAN_TEXT_LABELS: Final = frozenset(
    {
        "plan",
        "plan text",
        "plan texts",
        "plan txt",
        "plantext",
        "pt",
        "the plan",
        "the plan text",
        "our plan",
        "plan and solvency",
    }
)
"""Headings that label a plan text, as t01's normalizer writes them (`v1-e32-t09`'s counts)."""

_RULE_VERSION: Final = "plan-text-3"
"""Bumped when how a plan text is found or read changes, so a cached reading is read again."""
_LONGEST_LABEL_WORDS: Final = 6
_INLINE_LABEL: Final = re.compile(
    r"^\s*(?:the\s+)?(?:plan(?:\s+text)?|pt)\s*[:\-\u2013\u2014]\s*\S", re.IGNORECASE
)
_FEDERAL_ACTOR: Final = re.compile(r"(?<!fifty) (?:usfg|federal government|united states) ")
"""A federal actor, as words; `the fifty United States` is the states, not the federal government."""
_SHOULD: Final = " should "
JOINING_WORDS: Final = frozenset(
    (
        *("a", "an", "and", "as", "at", "be", "by", "for", "from", "in", "into", "is", "its"),
        *("of", "on", "or", "that", "the", "their", "this", "to", "with"),
    )
)
"""English joining words, never a mechanism's: the coach's sheet drops them too."""


class PlanTextVerdict(StrEnum):
    NAMES = "NAMES"
    CONFLICTING = "CONFLICTING"
    UNNAMED = "UNNAMED"
    NONE = "NONE"
    UNREAD = "UNREAD"


@dataclass(frozen=True, slots=True)
class Paragraph:
    """One paragraph of a source as the parser read it. Holds text, so its `repr` withholds it."""

    element_index: int
    unit: StructuralUnit
    text: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class PlanTextParagraph:
    """What is kept of one plan text: where it is, what it is, and what it names. Never its words."""

    label_element_index: int
    element_index: int
    unit: StructuralUnit
    kept: bool
    """Inside a card the parsed store holds."""
    shaped: bool
    digest: str
    """SHA-256 of its lowercase words, one space apart: equal for two plan texts worded alike."""
    named: tuple[str, ...]
    """The aff ids it names, narrowest only, sorted; empty when it names none."""


@dataclass(frozen=True, slots=True)
class DocumentPlanText:
    verdict: PlanTextVerdict
    position_id: str | None = None


Word = Annotated[str, StringConstraints(pattern=r"^[0-9a-z]+$")]


class ResolutionalPlanWords(DomainModel):
    """`config/landscape/plan_texts/<topic id>.yaml`: when a plan text naming no aff names the resolution."""

    schema_version: Literal[1] = Field(default=1, description="Version of this file's shape.")
    topic_id: Annotated[str, StringConstraints(pattern=POSITION_ID_PATTERN)] = Field(
        description="The topic, as `topics.yaml` names it."
    )
    position_id: Annotated[str, StringConstraints(pattern=POSITION_ID_PATTERN)] = Field(
        description="The active aff such a plan text names."
    )
    frame_words: tuple[Word, ...] = Field(
        min_length=1,
        description="Words in at least 80% of the coach's sheet's plan texts, as it printed them.",
    )
    resolutional_words: tuple[Word, ...] = Field(
        min_length=1, description="The words of the clusters the coach marked as the resolutional aff."
    )


class PlanTextVocabulary:
    """The words that name each aff of a taxonomy in a plan text, and how to choose among them."""

    def __init__(
        self,
        taxonomy: Taxonomy,
        resolutional: ResolutionalPlanWords | None = None,
        kritikal: KritikalAffConfig | None = None,
    ) -> None:
        self._taxonomy = taxonomy
        self._kritikal = kritikal
        affs = [one for one in taxonomy.positions if one.kind is PositionKind.AFF]
        if resolutional is not None and not any(
            one.id == resolutional.position_id and not one.deprecated for one in affs
        ):
            raise ValueError(
                f"the resolutional plan names {resolutional.position_id}, "
                f"which is no active aff of {taxonomy.topic_id}"
            )
        if kritikal is not None and not any(
            one.id == kritikal.position_id and not one.deprecated for one in affs
        ):
            raise ValueError(
                f"the K-aff config names {kritikal.position_id}, "
                f"which is no active aff of {taxonomy.topic_id}"
            )
        self._resolutional = resolutional
        self._allowed: frozenset[str] = (
            frozenset((*JOINING_WORDS, *resolutional.frame_words, *resolutional.resolutional_words))
            if resolutional is not None
            else frozenset()
        )
        self._parents = {one.id: one.parent for one in taxonomy.active_positions}
        words: dict[str, set[str]] = {}
        for one in affs:
            resolved = taxonomy.resolve(one.id)
            if resolved.deprecated:
                continue
            for phrase in (*one.aliases, *one.tag_keywords):
                if found := tag_words(phrase):
                    words.setdefault(found, set()).add(resolved.id)
        self._words = {phrase: frozenset(ids) for phrase, ids in sorted(words.items())}
        pairs = sorted((phrase, position_id) for phrase, ids in self._words.items() for position_id in ids)
        rule = (
            None
            if resolutional is None
            else [
                resolutional.position_id,
                sorted(JOINING_WORDS | set(resolutional.frame_words)),
                sorted(resolutional.resolutional_words),
            ]
        )
        self._digest = hashlib.sha256(
            json.dumps([_RULE_VERSION, pairs, rule, kritikal_rules(kritikal)], sort_keys=True).encode()
        ).hexdigest()

    def __repr__(self) -> str:
        version = f"{self._taxonomy.topic_id} {self._taxonomy.taxonomy_version}"
        return f"PlanTextVocabulary({version}, {self._digest[:12]})"

    @property
    def kritikal(self) -> KritikalAffConfig | None:
        """The topic's K-aff position and families (`v1-e32-t17`); None when the topic reads no K aff."""
        return self._kritikal

    @property
    def digest(self) -> str:
        """Changes with any word or the aff it names, with the reading rules (:data:`_RULE_VERSION`), and
        with the K-aff config and rules (`v1-e32-t17`), whose markers are read and cached beside the plan
        texts."""
        return self._digest

    def named(self, text: str) -> tuple[str, ...]:
        """The affs `text` names, narrowest only, sorted; two unrelated ones are both returned."""
        spaced = f" {tag_words(text)} "
        return self.narrowest(
            {one for phrase, ids in self._words.items() if f" {phrase} " in spaced for one in ids}
        )

    def resolutional(self, text: str) -> tuple[str, ...]:
        """The resolutional aff, when every word of `text` is a frame or resolutional word; else none.

        For a shaped plan text that names no aff: :func:`read_plan_texts` asks only of those.
        """
        if self._resolutional is None or not set(tag_words(text).split()) <= self._allowed:
            return ()
        return (self._resolutional.position_id,)

    def narrowest(self, position_ids: set[str]) -> tuple[str, ...]:
        """`position_ids` without any that is an ancestor of another, nor the resolutional aff beside another.

        The resolutional aff is the least specific aff (the PM's ruling of 2026-10-24): beside exactly one
        other aff it gives way to it, and it never makes a conflict, nor settles one between two others.
        """
        ancestors = {ancestor for one in position_ids for ancestor in self._ancestors(one)}
        found = position_ids - ancestors
        if self._resolutional is not None and len(found) > 1:
            found = found - {self._resolutional.position_id}
        return tuple(sorted(found))

    def _ancestors(self, position_id: str) -> list[str]:
        found: list[str] = []
        parent = self._parents.get(position_id)
        while parent is not None and parent not in found:
            resolved = self._taxonomy.resolve(parent).id
            found.append(resolved)
            parent = self._parents.get(resolved)
        return found


def paragraphs_of(document: ParsedDocument) -> tuple[tuple[Paragraph, ...], frozenset[int]]:
    """Every paragraph of `document` with text in it, and the paragraphs inside its cards."""
    paragraphs = tuple(
        Paragraph(element_index=one.element_index, unit=one.match.unit, text=one.text)
        for one in document.sections
        if one.text.strip()
    )
    in_cards = frozenset(
        index
        for card in document.cards
        for index in range(card.provenance.first_element_index, card.provenance.last_element_index + 1)
    )
    return paragraphs, in_cards


def read_plan_texts(
    paragraphs: tuple[Paragraph, ...], in_cards: frozenset[int], vocabulary: PlanTextVocabulary
) -> tuple[PlanTextParagraph, ...]:
    """Each plan text of a source, in file order: the paragraph under each label, or an inline label."""
    found: list[PlanTextParagraph] = []
    written = [one for one in paragraphs if one.text.strip()]
    labels = [_is_label(one.text) for one in written]
    for position, one in enumerate(written):
        if _is_inline(one.text):
            found.append(_kept_of(one, one, in_cards, vocabulary))
        elif (
            labels[position]
            and position + 1 < len(written)
            and not labels[position + 1]
            and not _is_inline(written[position + 1].text)
        ):
            found.append(_kept_of(one, written[position + 1], in_cards, vocabulary))
    return tuple(found)


def document_plan_text(
    found: tuple[PlanTextParagraph, ...], vocabulary: PlanTextVocabulary
) -> DocumentPlanText:
    """One source's verdict over every plan text :func:`read_plan_texts` found in it."""
    named = vocabulary.narrowest({one for paragraph in found for one in paragraph.named})
    if len(named) == 1:
        return DocumentPlanText(PlanTextVerdict.NAMES, named[0])
    if named:
        return DocumentPlanText(PlanTextVerdict.CONFLICTING)
    if any(paragraph.shaped for paragraph in found):
        return DocumentPlanText(PlanTextVerdict.UNNAMED)
    return DocumentPlanText(PlanTextVerdict.NONE)


def sheet_plan_texts(found: tuple[PlanTextParagraph, ...]) -> tuple[PlanTextParagraph, ...]:
    """The plan texts the coach's sheet shows: those that name an aff or read like a plan text."""
    return tuple(one for one in found if one.named or one.shaped)


def read_back_plan_texts(
    paragraphs: tuple[Paragraph, ...], wanted: tuple[PlanTextParagraph, ...]
) -> tuple[str, ...] | None:
    """`wanted`'s paragraphs word for word, in file order; None when one is gone or reads differently.

    A paragraph is found by its element index and must hash to the digest kept for it, so nothing is
    shown from a paragraph other than the one that was read.
    """
    by_index = {one.element_index: one for one in paragraphs}
    texts: list[str] = []
    for one in sorted(wanted, key=lambda found: found.element_index):
        paragraph = by_index.get(one.element_index)
        if paragraph is None or hashlib.sha256(tag_words(paragraph.text).encode()).hexdigest() != one.digest:
            return None
        texts.append(paragraph.text)
    return tuple(texts)


def plan_text_words(
    paragraphs: tuple[Paragraph, ...], wanted: tuple[PlanTextParagraph, ...]
) -> tuple[str, ...] | None:
    """The words of `wanted`'s paragraphs, in file order; None as :func:`read_back_plan_texts` says."""
    texts = read_back_plan_texts(paragraphs, wanted)
    if texts is None:
        return None
    return tuple(word for text in texts for word in tag_words(text).split())


def _is_label(text: str) -> bool:
    return len(text.split()) <= _LONGEST_LABEL_WORDS and normalize_heading(text).text in PLAN_TEXT_LABELS


def _is_inline(text: str) -> bool:
    return _INLINE_LABEL.match(text) is not None and _shaped(text)


def _shaped(text: str) -> bool:
    """`should` with a federal actor before it."""
    words = f" {tag_words(text)} "
    last = words.rfind(_SHOULD)
    return last >= 0 and _FEDERAL_ACTOR.search(words[: last + 1]) is not None


def _another_actor(text: str) -> bool:
    """`should` with no federal actor before it: a counterplan's text, not a plan's."""
    return _SHOULD in f" {tag_words(text)} " and not _shaped(text)


def _kept_of(
    label: Paragraph, plan: Paragraph, in_cards: frozenset[int], vocabulary: PlanTextVocabulary
) -> PlanTextParagraph:
    shaped = _shaped(plan.text)
    named = () if _another_actor(plan.text) else vocabulary.named(plan.text)
    return PlanTextParagraph(
        label_element_index=label.element_index,
        element_index=plan.element_index,
        unit=plan.unit,
        kept=plan.element_index in in_cards,
        shaped=shaped,
        digest=hashlib.sha256(tag_words(plan.text).encode()).hexdigest(),
        named=named or (vocabulary.resolutional(plan.text) if shaped else ()),
    )
