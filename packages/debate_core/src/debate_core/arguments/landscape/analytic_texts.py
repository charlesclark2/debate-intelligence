"""CP texts, K alternatives, roles of the ballot and overviews, read from the sources (`v1-e32-t11`).

The parsed card store keeps cards only, and most of these texts are analytics, so they are read from the
source's paragraphs as `v1-e32-t09` reads plan texts, and only what is derived from each is kept
(:class:`~debate_core.domain.landscape_texts.AnalyticTextReading`): where it is, its unit, a digest of its
words, and the position it is placed under. Never the text. The labels are the PM's rulings of 2026-10-24
on `v1-e32-t11`'s counts.

## Finding them (:func:`read_analytic_texts`)

A **label** is a paragraph of at most 8 words, not evidence or a cite, that t01's normalizer (with the
team's own names and the caselist's schools taken out) reduces to one of a kind's labels below. Its text is
the next paragraph with words in it, when that is a tag, an analytic, an undertag or an unstyled
paragraph; a heading or evidence under a label is no text, and the label is not counted. An **inline**
label opens the paragraph that holds the text (`Text: The fifty states should ...`) and is no part of
the text, so a labelled copy and an unlabelled one are one text; a **sentence**
label is the text itself (`The alternative is ...`).

* **CP text:** `text`, `texts`, `the text`, `cp text`, `cp texts`, `counterplan text`, `counterplan texts`
  on their own, with a text that holds `should`; inline `Text:`, `CP Text:`, `Counterplan Text:`, `CP:`,
  `Counterplan:`, `The CP:` or `The counterplan:` opening a paragraph that holds `should`. **By its
  place**, with no label: the first paragraph with `should` in a block, when it is an analytic the store
  does not keep, of at most 120 words, whose nearest placed heading is a CP the team reads, and which passes
  the **actor guard**: at most 12 words before its first `should`, and among them an actor phrase of the
  topic's config (`config/landscape/analytic_texts/`), such as `fifty states`, `usfg` or `congress`.
* **K alternative:** `alt`, `alternative`, `the alt`, `the alternative`, `alt text`, `alternative text`,
  `alts` on their own; inline `Alt:`, `Alternative:`, `Alt text:`, `The alt:` in a tag or analytic; the
  sentences `The alternative is`, `The alt is`, `Our alternative is`, `Our alt is` and their `should` and
  `will`. Left out: `Alt: <name>` as a heading (it names the alt, it is not its text), and `Alt causes`,
  `Alt fails`, `Perm do the alt` (answers).
* **Role of the ballot:** `role of the ballot`, `the role of the ballot`, `role of ballot`, `rob`, `rotb`,
  `role of the judge`, `the role of the judge`, `role of judge`, `roj` on their own; inline `ROB:`, `ROJ:`,
  `Role of the ballot:`, `Role of the judge:` in a tag or analytic; the sentences `The role of the ballot
  is` (or `should`), `The role of the judge is` (or `should`), `Our role of the ballot is`. Left out:
  `Ballot` on its own (it also heads ballot-PIK and presumption blocks) and `Ballot PIK`.
* **Overview:** `overview`, `overviews`, `ov`, `o v` (`O/V`), `ovw` on their own or with other words
  (`Impact overview`, `Link O/V`, `Overview - Cap K`). Counted only: no digest. `O/W` is "outweighs".

## Placing them

A text belongs to the position its section is placed under: the nearest placed heading over its label, by
`v1-e32-t02`'s matcher, read as the matcher reads a card's (:func:`heading_placement`). A label under no
placed heading is kept as unplaced and never guessed: under headings that place nothing (`1NC`, `OFF`), or
under no heading at all. A text read by its place is only ever one placed under a CP the team reads.

## Showing them (:func:`top_texts`)

Per position, texts are grouped by their normalized words (their digest), ranked by the teams reading
each, then by digest. A group shows one of its texts word for word, the commonest, the first by source and
paragraph on a tie. A text naming a school of the caselist is withheld and counted
(:func:`names_a_school`), and a group no text of which could be read again is not shown.

Pure and deterministic: no I/O, no model, and nothing returned or logged holds a paragraph's text but
:func:`read_back_texts`' and :func:`top_texts`' quoted texts, which the report shows.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Annotated, Final, Literal

from pydantic import Field, StringConstraints

from debate_core.arguments.landscape.matcher import MatchItem, PositionMatcher, tag_words
from debate_core.arguments.landscape.source_headings import (
    CaselistNames,
    heading_path,
    normalize_source_heading,
)
from debate_core.domain.base import DomainModel
from debate_core.domain.debate_files import ParsedDocument
from debate_core.domain.landscape import POSITION_ID_PATTERN, PositionKind, Taxonomy
from debate_core.domain.landscape_classification import ItemKind, OverrideRules, PositionRole
from debate_core.domain.landscape_texts import (
    AnalyticTextKind,
    AnalyticTextReading,
    MoreTexts,
    QuotedText,
    TextForm,
    TextPlacement,
)
from debate_core.domain.style_profile import StructuralUnit

__all__ = [
    "ALTERNATIVE_LABELS",
    "AnalyticTextInputs",
    "CP_TEXT_LABELS",
    "MAX_LABEL_WORDS",
    "MAX_WORDS_BEFORE_SHOULD",
    "OVERVIEW_WORDS",
    "ROLE_OF_THE_BALLOT_LABELS",
    "MAX_PLANK_WORDS",
    "AnalyticTextRules",
    "CounterplanActors",
    "Placement",
    "advantage_aliases_in",
    "commonest_text",
    "plank_words",
    "SectionParagraph",
    "SourceParagraphs",
    "SourceTexts",
    "TEXT_UNITS",
    "TextGroup",
    "heading_placement",
    "label_form",
    "names_a_school",
    "passes_actor_guard",
    "read_analytic_texts",
    "read_back_texts",
    "role_of_the_ballot_form",
    "section_paragraphs_of",
    "text_digest",
    "top_texts",
]

CP_TEXT_LABELS: Final = frozenset(
    {"text", "texts", "the text", "cp text", "cp texts", "counterplan text", "counterplan texts"}
)
ALTERNATIVE_LABELS: Final = frozenset(
    {"alt", "alternative", "the alt", "the alternative", "alt text", "alternative text", "alts"}
)
ROLE_OF_THE_BALLOT_LABELS: Final = frozenset(
    {
        "role of the ballot",
        "the role of the ballot",
        "role of ballot",
        "rob",
        "rotb",
        "role of the judge",
        "the role of the judge",
        "role of judge",
        "roj",
    }
)
OVERVIEW_WORDS: Final = frozenset({"overview", "overviews", "ov", "ovw"})
"""With `o v`, the words that make a short paragraph an overview's label."""

MAX_LABEL_WORDS: Final = 8
MAX_WORDS_BEFORE_SHOULD: Final = 12
"""The actor guard (the PM's ruling 1 of 2026-10-24)."""
MAX_BY_PLACE_WORDS: Final = 120
MAX_PLANK_WORDS: Final = 60
"""A list plank's limit (the PM's ruling 1 of 2026-10-25)."""
_RULE_VERSION: Final = "analytic-texts-2"
"""Bumped when how a text is found, read or placed changes, so a cached reading is read again."""

_SEPARATOR: Final = r"\s*[:\-\u2013\u2014]\s*(?=\S)"
_CP_INLINE: Final = re.compile(
    r"^\s*(?:(?:the\s+)?(?:cp|counterplan)(?:\s+text)?|(?:the\s+)?text)" + _SEPARATOR, re.IGNORECASE
)
_ALTERNATIVE_INLINE: Final = re.compile(
    r"^\s*(?:the\s+)?alt(?:ernative)?(?:\s+text)?" + _SEPARATOR, re.IGNORECASE
)
_ROLE_INLINE: Final = re.compile(
    r"^\s*(?:rob|roj|role\s+of\s+the\s+(?:ballot|judge))" + _SEPARATOR, re.IGNORECASE
)
_INLINE_LABELS: Final = {
    AnalyticTextKind.CP_TEXT: _CP_INLINE,
    AnalyticTextKind.K_ALTERNATIVE: _ALTERNATIVE_INLINE,
    AnalyticTextKind.ROLE_OF_THE_BALLOT: _ROLE_INLINE,
}
"""An inline label, up to its text: the label is no part of the text it opens."""
_ALTERNATIVE_SENTENCE: Final = re.compile(
    r"^\s*(?:the|our)\s+alt(?:ernative)?\s+(?:is|should|will)\b", re.IGNORECASE
)
_ROLE_SENTENCE: Final = re.compile(
    r"^\s*(?:the|our)\s+role\s+of\s+the\s+(?:ballot|judge)\s+(?:is|should)\b", re.IGNORECASE
)
_PLANK_NUMBER: Final = r"(?:\d{1,2}|one|two|three|four|five|six|i{1,3}|iv|vi?)"
_PLANK_LABEL: Final = re.compile(
    rf"^\s*(?:plank\s*#?\s*{_PLANK_NUMBER}\b\s*[:.)\-\u2013\u2014]?"
    r"|\(?\d{1,2}[.)](?=\s)"
    r"|(?:first|second|third|fourth|fifth|sixth|finally|lastly)\s*[,:])\s*(?=\S)",
    re.IGNORECASE,
)
"""A plank label opening a paragraph, up to the plank's words (`Plank 2:`, `2.`, `Second,`)."""
_SOLVES_VERBS: Final = ("solves", "solve", "solving")
_HEADING_UNITS: Final = frozenset({StructuralUnit.POCKET, StructuralUnit.HAT, StructuralUnit.BLOCK})
_NOT_TEXT_UNITS: Final = frozenset({StructuralUnit.EVIDENCE, StructuralUnit.CITE})
TEXT_UNITS: Final = frozenset(
    {StructuralUnit.TAG, StructuralUnit.ANALYTIC, StructuralUnit.UNDERTAG, StructuralUnit.OTHER}
)
"""The units that can hold a label's text: what may follow a label for it to count."""
_LIST_UNITS: Final = frozenset({StructuralUnit.ANALYTIC, StructuralUnit.UNDERTAG, StructuralUnit.OTHER})

Phrase = Annotated[str, StringConstraints(pattern=r"^[0-9a-z]+(?: [0-9a-z]+)*$")]


class CounterplanActors(DomainModel):
    """`config/landscape/analytic_texts/<topic id>.yaml`: who a CP text read by its place may name."""

    schema_version: Literal[1] = Field(default=1, description="Version of this file's shape.")
    topic_id: Annotated[str, StringConstraints(pattern=POSITION_ID_PATTERN)] = Field(
        description="The topic, as `topics.yaml` names it."
    )
    cp_text_actors: tuple[Phrase, ...] = Field(
        min_length=1,
        description="Actor phrases as lowercase words, one of which must come before a CP text's `should`.",
    )


@dataclass(frozen=True, slots=True)
class SectionParagraph:
    """One paragraph of a source with its place in the headings. Holds text, so its `repr` withholds it."""

    element_index: int
    unit: StructuralUnit
    text: str = field(repr=False)
    section_path: tuple[str, ...] = field(default=(), repr=False)


@dataclass(frozen=True, slots=True)
class SourceParagraphs:
    paragraphs: tuple[SectionParagraph, ...] = field(repr=False)
    """Every paragraph with words in it, in file order."""
    in_cards: frozenset[int] = frozenset()
    """The paragraphs inside a card the parsed store holds."""
    tags: frozenset[str] = field(default=frozenset(), repr=False)
    """The document's card tags, to tell an open tag from a heading in a path."""


@dataclass(frozen=True, slots=True)
class Placement:
    placement: TextPlacement
    position_id: str | None = None
    role: PositionRole | None = None


@dataclass(frozen=True, slots=True)
class SourceTexts:
    readings: tuple[AnalyticTextReading, ...]
    refused_by_guard: int = 0
    """First `should` analytics placed under a CP that the actor guard left out."""
    planks_refused_by_guard: int = 0
    """List planks left out because their CP text fails the actor guard."""
    plank_labels: int = 0
    """List paragraphs that are only an advantage's alias: labels naming the plank after them."""


@dataclass(frozen=True, slots=True)
class TextGroup:
    """One position's texts alike in their words: the teams reading them, and the texts read again."""

    teams: frozenset[object] = field(repr=False)
    texts: tuple[tuple[str, int, str], ...] = field(default=(), repr=False)
    """(source digest, paragraph, text) of each copy read again as it was read."""


@dataclass(frozen=True, slots=True)
class AnalyticTextInputs:
    """What the landscape report is given of the caselist's analytic texts (`v1-e32-t11`)."""

    readings: Mapping[str, tuple[AnalyticTextReading, ...]] = field(repr=False)
    """Each readable source's readings, by source digest."""
    texts: Mapping[tuple[str, int], str] = field(repr=False)
    """Each quoted kind's text read again as it was read, by (source digest, paragraph)."""
    caselist_names: Mapping[str, Sequence[str]] = field(repr=False)
    """Every school of the caselist with its codes: a text naming one is withheld."""
    refused_by_guard: Mapping[str, int] = field(default_factory=dict[str, int], repr=False)
    """Each source's first `should` analytics under a CP the actor guard left out."""
    planks_refused_by_guard: Mapping[str, int] = field(default_factory=dict[str, int], repr=False)
    """Each source's list planks left out because their CP text fails the actor guard (`v1-e32-t16`)."""
    plank_labels: Mapping[str, int] = field(default_factory=dict[str, int], repr=False)
    """Each source's list paragraphs that are only an advantage's alias, naming the plank after them."""


class AnalyticTextRules:
    """The labels, the guard's actors, and the taxonomy and overrides that place a text."""

    def __init__(
        self, taxonomy: Taxonomy, overrides: OverrideRules, actors: CounterplanActors | None
    ) -> None:
        self.taxonomy = taxonomy
        self.overrides = overrides
        self.actors: tuple[str, ...] = actors.cp_text_actors if actors is not None else ()
        self.matcher = PositionMatcher(taxonomy, overrides)
        self.advantage_aliases: dict[str, str] = _advantage_aliases(taxonomy)
        """Every alias of an active advantage, with the advantage it names: what a plank is read for."""
        self._digest = hashlib.sha256(
            json.dumps(
                [
                    _RULE_VERSION,
                    sorted(CP_TEXT_LABELS),
                    sorted(ALTERNATIVE_LABELS),
                    sorted(ROLE_OF_THE_BALLOT_LABELS),
                    sorted(OVERVIEW_WORDS),
                    [MAX_LABEL_WORDS, MAX_WORDS_BEFORE_SHOULD, MAX_BY_PLACE_WORDS, MAX_PLANK_WORDS],
                    sorted(self.actors),
                    taxonomy.model_dump(mode="json"),
                    overrides.model_dump(mode="json"),
                ],
                sort_keys=True,
            ).encode()
        ).hexdigest()

    def __repr__(self) -> str:
        version = f"{self.taxonomy.topic_id} {self.taxonomy.taxonomy_version}"
        return f"AnalyticTextRules({version}, {self._digest[:12]})"

    @property
    def digest(self) -> str:
        """Changes with any label, rule, actor, position or override: the cache key's third part."""
        return self._digest


def text_digest(text: str) -> str:
    """SHA-256 of `text`'s lowercase words, one space apart: equal for two texts worded alike."""
    return hashlib.sha256(tag_words(text).encode()).hexdigest()


def advantage_aliases_in(words: str, aliases: Mapping[str, str]) -> tuple[str, ...]:
    """The advantage aliases `words` (lowercase words, one space apart) hold as whole phrases, sorted."""
    spaced = f" {words} "
    return tuple(sorted(alias for alias in aliases if f" {alias} " in spaced))


def plank_words(text: str) -> str:
    """A plank's words: `text` without the plank label (`Plank 2:`, `2.`, `Second,`) that opens it."""
    found = _PLANK_LABEL.match(text)
    return text[found.end() :] if found is not None else text


def section_paragraphs_of(document: ParsedDocument) -> SourceParagraphs:
    """Every paragraph of `document` with words in it, the paragraphs inside its cards, and its tags."""
    return SourceParagraphs(
        paragraphs=tuple(
            SectionParagraph(
                element_index=one.element_index,
                unit=one.match.unit,
                text=one.text,
                section_path=tuple(one.section_path),
            )
            for one in document.sections
            if one.text.strip()
        ),
        in_cards=frozenset(
            index
            for card in document.cards
            for index in range(card.provenance.first_element_index, card.provenance.last_element_index + 1)
        ),
        tags=frozenset(card.tag for card in document.cards if card.tag is not None),
    )


def heading_placement(
    rules: AnalyticTextRules, own_names: Sequence[str], caselist: CaselistNames
) -> Callable[[Sequence[str], frozenset[str]], Placement]:
    """Where the headings of a section path place a text, as the matcher places a card under them.

    The path is cut as a card's is (an open tag dropped, three levels at most), and each heading is
    normalized with the team's own names and the caselist's schools taken out; the empty ones say nothing.
    """
    names = [name for name in own_names if name.strip()]

    def place(section_path: Sequence[str], tags: frozenset[str]) -> Placement:
        headings = tuple(
            heading
            for heading in (
                normalize_source_heading(raw, names, caselist)
                for raw in heading_path(None, section_path, tags)
            )
            if heading.text
        )
        if not headings:
            return Placement(TextPlacement.NO_HEADING)
        result = rules.matcher.place(
            MatchItem(
                item_id="analytic-text",
                kind=ItemKind.SECTION,
                source_sha256="",
                first_element_index=None,
                headings=headings,
                tag=None,
            )
        )
        if result.position_id is None or result.role is None:
            return Placement(TextPlacement.HEADINGS_PLACE_NOTHING)
        return Placement(TextPlacement.PLACED, result.position_id, result.role)

    return place


def role_of_the_ballot_form(
    text: str, unit: StructuralUnit, form: str | None, next_unit: StructuralUnit | None
) -> TextForm | None:
    """How a paragraph holds a role of the ballot, by the labels above; None when it holds none.

    `form` is the paragraph's label form (:func:`label_form`) and `next_unit` the unit of the next
    paragraph with words in it. A label counts only over a text; an inline label never in a heading.
    `v1-e32-t17` reads a K aff's role of the ballot by this same rule.
    """
    if form in ROLE_OF_THE_BALLOT_LABELS:
        return TextForm.LABEL if next_unit in TEXT_UNITS else None
    if _ROLE_INLINE.match(text) and unit not in _HEADING_UNITS:
        return TextForm.INLINE
    if _ROLE_SENTENCE.match(text):
        return TextForm.SENTENCE
    return None


def passes_actor_guard(text: str, actors: Collection[str]) -> bool:
    """At most 12 words before the first `should`, and an actor phrase among them, as whole words."""
    words = tag_words(text).split()
    if "should" not in words:
        return False
    before = words[: words.index("should")]
    if len(before) > MAX_WORDS_BEFORE_SHOULD:
        return False
    spaced = f" {' '.join(before)} "
    return any(f" {actor} " in spaced for actor in actors)


def read_analytic_texts(
    source: SourceParagraphs,
    rules: AnalyticTextRules,
    *,
    own_names: Sequence[str] = (),
    caselist: CaselistNames | None = None,
) -> SourceTexts:
    """Every CP text, alternative, role of the ballot and overview of one source, placed, in file order."""
    names = caselist or CaselistNames({})
    place = heading_placement(rules, own_names, names)
    written = [one for one in source.paragraphs if one.text.strip()]
    found: list[AnalyticTextReading] = []
    cp_paragraphs: set[int] = set()

    def keep(kind: AnalyticTextKind, form: TextForm, label: SectionParagraph, text: SectionParagraph) -> None:
        where = place(label.section_path, source.tags)
        words = _without_inline_label(kind, text.text) if form is TextForm.INLINE else text.text
        found.append(
            AnalyticTextReading(
                kind=kind,
                form=form,
                label_element_index=label.element_index,
                element_index=text.element_index,
                unit=text.unit,
                kept=text.element_index in source.in_cards,
                digest=None if kind is AnalyticTextKind.OVERVIEW else text_digest(words),
                placement=where.placement,
                position_id=where.position_id,
                role=where.role,
            )
        )
        if kind is AnalyticTextKind.CP_TEXT:
            cp_paragraphs.add(text.element_index)

    for position, one in enumerate(written):
        if one.unit in _NOT_TEXT_UNITS:
            continue
        following = written[position + 1] if position + 1 < len(written) else None
        under = following if following is not None and following.unit in TEXT_UNITS else None
        form = _label_form(one, own_names, names)
        should = _holds_should(one.text)
        if form in CP_TEXT_LABELS:
            if under is not None and _holds_should(under.text):
                keep(AnalyticTextKind.CP_TEXT, TextForm.LABEL, one, under)
        elif _CP_INLINE.match(one.text) and should:
            keep(AnalyticTextKind.CP_TEXT, TextForm.INLINE, one, one)
        if form in ALTERNATIVE_LABELS:
            if under is not None:
                keep(AnalyticTextKind.K_ALTERNATIVE, TextForm.LABEL, one, under)
        elif _ALTERNATIVE_INLINE.match(one.text) and one.unit not in _HEADING_UNITS:
            keep(AnalyticTextKind.K_ALTERNATIVE, TextForm.INLINE, one, one)
        elif _ALTERNATIVE_SENTENCE.match(one.text):
            keep(AnalyticTextKind.K_ALTERNATIVE, TextForm.SENTENCE, one, one)
        role = role_of_the_ballot_form(one.text, one.unit, form, under.unit if under is not None else None)
        if role is TextForm.LABEL and under is not None:
            keep(AnalyticTextKind.ROLE_OF_THE_BALLOT, TextForm.LABEL, one, under)
        elif role is not None:
            keep(AnalyticTextKind.ROLE_OF_THE_BALLOT, role, one, one)
        if form is not None and _is_overview(form):
            keep(AnalyticTextKind.OVERVIEW, TextForm.LABEL, one, one)
    refused = 0
    for one in _first_should_of_each_block(written):
        if one.element_index in cp_paragraphs or one.unit is not StructuralUnit.ANALYTIC:
            continue
        if one.element_index in source.in_cards:
            continue
        where = place(one.section_path, source.tags)
        if where.position_id is None or where.role is not PositionRole.READS:
            continue
        if rules.taxonomy.resolve(where.position_id).kind is not PositionKind.CP:
            continue
        if not passes_actor_guard(one.text, rules.actors):
            refused += 1
            continue
        keep(AnalyticTextKind.CP_TEXT, TextForm.BY_PLACE, one, one)
    planks = _Planks(source, rules, written, own_names, names)
    for stem in sorted(
        (one for one in found if one.kind is AnalyticTextKind.CP_TEXT), key=lambda one: one.element_index
    ):
        found += planks.of(stem, cp_paragraphs)
    return SourceTexts(
        readings=tuple(sorted(found, key=lambda one: (one.label_element_index, one.element_index, one.kind))),
        refused_by_guard=refused,
        planks_refused_by_guard=planks.refused_by_guard,
        plank_labels=planks.labels,
    )


class _Planks:
    """The planks of a source's CP texts (`v1-e32-t16`, the PM's rulings of 2026-10-25).

    A CP text ending in a colon lists its planks in the paragraphs after it, up to the block's first card
    or heading: analytics, undertags and unstyled paragraphs the store does not keep, of at most
    :data:`MAX_PLANK_WORDS` words. Their actor is the CP text's, so they are read only when it passes the
    actor guard itself, and counted as refused otherwise. A list paragraph that is only an advantage's
    alias is a label naming the plank after it. Later in the block, up to its next heading or CP text,
    each `should` analytic past the guard and each paragraph opening with a plank label is a separate
    plank, named also by the cards under it. A plank is placed where its CP text is.
    """

    def __init__(
        self,
        source: SourceParagraphs,
        rules: AnalyticTextRules,
        written: Sequence[SectionParagraph],
        own_names: Sequence[str],
        caselist: CaselistNames,
    ) -> None:
        self._source = source
        self._rules = rules
        self._written = written
        self._at = {one.element_index: position for position, one in enumerate(written)}
        self._names = [name for name in own_names if name.strip()]
        self._caselist = caselist
        self.refused_by_guard = 0
        self.labels = 0

    def of(self, stem: AnalyticTextReading, cp_paragraphs: Collection[int]) -> list[AnalyticTextReading]:
        text = self._written[self._at[stem.element_index]].text
        words = (
            _without_inline_label(AnalyticTextKind.CP_TEXT, text) if stem.form is TextForm.INLINE else text
        )
        listing = words.rstrip().endswith(":")
        guarded = passes_actor_guard(words, self._rules.actors)
        listed: list[tuple[SectionParagraph, SectionParagraph | None]] = []
        separate: list[tuple[SectionParagraph, list[str]]] = []
        label: SectionParagraph | None = None
        for one in self._written[self._at[stem.element_index] + 1 :]:
            if one.unit in _HEADING_UNITS or one.element_index in cp_paragraphs:
                break
            if one.element_index in self._source.in_cards or one.unit is StructuralUnit.TAG:
                listing = False
                if separate and one.unit is StructuralUnit.TAG:
                    separate[-1][1].append(one.text)
                continue
            if listing:
                if one.unit not in _LIST_UNITS:
                    continue
                if self._is_alias_label(one):
                    self.labels += 1
                    label = one
                elif len(tag_words(one.text).split()) <= MAX_PLANK_WORDS:
                    listed.append((one, label))
                    label = None
                continue
            if self._is_separate(one):
                separate.append((one, []))
        if not guarded:
            self.refused_by_guard += len(listed)
            listed = []
        found = [self._reading(stem, one, TextForm.LIST, label, ()) for one, label in listed]
        found += [self._reading(stem, one, TextForm.SEPARATE, None, tags) for one, tags in separate]
        return found

    def _is_alias_label(self, one: SectionParagraph) -> bool:
        form = normalize_source_heading(one.text, self._names, self._caselist).text
        return form in self._rules.advantage_aliases

    def _is_separate(self, one: SectionParagraph) -> bool:
        if one.unit not in TEXT_UNITS:
            return False
        if _PLANK_LABEL.match(one.text):
            return True
        return (
            one.unit is StructuralUnit.ANALYTIC
            and len(tag_words(one.text).split()) <= MAX_BY_PLACE_WORDS
            and passes_actor_guard(one.text, self._rules.actors)
        )

    def _reading(
        self,
        stem: AnalyticTextReading,
        one: SectionParagraph,
        form: TextForm,
        label: SectionParagraph | None,
        tags: Sequence[str],
    ) -> AnalyticTextReading:
        aliases = self._rules.advantage_aliases
        words = plank_words(one.text)
        named = set(advantage_aliases_in(self._caselist.without_schools(tag_words(words)), aliases))
        if label is not None:
            named.add(normalize_source_heading(label.text, self._names, self._caselist).text)
        other = 0
        for tag in tags:
            in_tag = self._card_names(tag_words(tag))
            named |= in_tag
            if not in_tag and any(f" {verb} " in f" {tag_words(tag)} " for verb in _SOLVES_VERBS):
                other += 1
        return AnalyticTextReading(
            kind=AnalyticTextKind.CP_PLANK,
            form=form,
            label_element_index=label.element_index if label is not None else one.element_index,
            element_index=one.element_index,
            unit=one.unit,
            kept=False,
            digest=text_digest(words),
            placement=stem.placement,
            position_id=stem.position_id,
            role=stem.role,
            stem_element_index=stem.element_index,
            solves=tuple(sorted({aliases[alias] for alias in named})),
            solves_other_words=other,
        )

    def _card_names(self, words: str) -> set[str]:
        """The aliases a card's tag names: `solves <alias>` in it, or the whole tag an alias."""
        aliases = self._rules.advantage_aliases
        if words in aliases:
            return {words}
        spaced = f" {words} "
        return {alias for alias in aliases if any(f" {verb} {alias} " in spaced for verb in _SOLVES_VERBS)}


def read_back_texts(
    paragraphs: Sequence[SectionParagraph], wanted: Sequence[AnalyticTextReading]
) -> dict[int, str]:
    """Each wanted text word for word, by paragraph, when its paragraph still hashes to the digest kept.

    A paragraph is found by its element index and must hash to the reading's digest, so nothing is shown
    from a paragraph other than the one that was read. An overview, which keeps no digest, is never read.
    """
    by_index = {one.element_index: one for one in paragraphs}
    texts: dict[int, str] = {}
    for one in wanted:
        paragraph = by_index.get(one.element_index)
        if one.digest is None or paragraph is None:
            continue
        if one.kind is AnalyticTextKind.CP_PLANK:
            text = plank_words(paragraph.text)
        elif one.form is TextForm.INLINE:
            text = _without_inline_label(one.kind, paragraph.text)
        else:
            text = paragraph.text
        if text_digest(text) == one.digest:
            texts[one.element_index] = text
    return texts


def names_a_school(text: str, caselist: CaselistNames) -> bool:
    """Whether `text`'s words hold a school of the caselist, as whole words."""
    words = tag_words(text)
    return caselist.without_schools(words) != words


def top_texts(
    position_id: str,
    kind: AnalyticTextKind,
    groups: Mapping[str, TextGroup],
    *,
    limit: int,
    caselist: CaselistNames,
) -> tuple[tuple[QuotedText, ...], MoreTexts | None, int]:
    """The position's top `limit` texts, the rest as a count, and how many distinct texts were withheld.

    A group none of whose copies was read again is left out, neither shown nor withheld.
    """
    shown: list[tuple[str, TextGroup, str]] = []
    withheld = 0
    for digest, group in groups.items():
        if not group.texts:
            continue
        text = commonest_text(group.texts)
        if names_a_school(text, caselist):
            withheld += 1
            continue
        shown.append((digest, group, text))
    ranked = sorted(shown, key=lambda one: (-len(one[1].teams), one[0]))
    quoted = tuple(
        QuotedText(position_id=position_id, kind=kind, rank=rank, teams=len(group.teams), text=text)
        for rank, (_, group, text) in enumerate(ranked[:limit], start=1)
    )
    rest = ranked[limit:]
    more = (
        MoreTexts(
            position_id=position_id,
            kind=kind,
            texts=len(rest),
            teams=len({team for _, group, _ in rest for team in group.teams}),
        )
        if rest
        else None
    )
    return quoted, more, withheld


def _advantage_aliases(taxonomy: Taxonomy) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for position in taxonomy.positions:
        resolved = taxonomy.resolve(position.id)
        if not resolved.deprecated and resolved.kind is PositionKind.ADVANTAGE:
            aliases.update(dict.fromkeys(position.aliases, resolved.id))
    return aliases


def _without_inline_label(kind: AnalyticTextKind, text: str) -> str:
    """`text` without the inline label that opens it, when one does."""
    label = _INLINE_LABELS.get(kind)
    found = label.match(text) if label is not None else None
    return text[found.end() :] if found is not None else text


def commonest_text(texts: Sequence[tuple[str, int, str]]) -> str:
    """What a group shows: the wording most copies hold, then the first copy's by source and paragraph."""
    counts = Counter(text for _, _, text in texts)
    best = max(counts.values())
    return min((sha, index, text) for sha, index, text in texts if counts[text] == best)[2]


def _label_form(one: SectionParagraph, own_names: Sequence[str], caselist: CaselistNames) -> str | None:
    return label_form(one.text, own_names, caselist)


def label_form(text: str, own_names: Sequence[str] = (), caselist: CaselistNames | None = None) -> str | None:
    """A short paragraph's normalized form, as a label is matched; None for a longer one."""
    words = tag_words(text).split()
    if not 0 < len(words) <= MAX_LABEL_WORDS:
        return None
    names = [name for name in own_names if name.strip()]
    return normalize_source_heading(text, names, caselist or CaselistNames({})).text


def _is_overview(form: str) -> bool:
    return bool(OVERVIEW_WORDS & set(form.split())) or " o v " in f" {form} "


def _holds_should(text: str) -> bool:
    return " should " in f" {tag_words(text)} "


def _first_should_of_each_block(paragraphs: Sequence[SectionParagraph]) -> list[SectionParagraph]:
    """Per block (from each pocket, hat or block heading), the first paragraph with `should` that is not
    evidence or a cite and holds at most :data:`MAX_BY_PLACE_WORDS` words."""
    found: list[SectionParagraph] = []
    open_block = True
    for one in paragraphs:
        if one.unit in _HEADING_UNITS:
            open_block = True
            continue
        if not open_block or one.unit in _NOT_TEXT_UNITS or not _holds_should(one.text):
            continue
        if len(tag_words(one.text).split()) > MAX_BY_PLACE_WORDS:
            continue
        found.append(one)
        open_block = False
    return found
