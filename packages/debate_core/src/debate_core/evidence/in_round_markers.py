"""In-round markers and the short lines between body paragraphs, described in counts (`v1-e31-t23`).

A debater who stops reading a card in a round marks the place, and files carry the mark into later
copies: a short line such as `Marked 10:42` inside or at the end of the evidence. Where the parser
reads that line as body, it is evidence text, so two copies of one card differ by the marker and
their exact fingerprints differ. `v1-e31-t19` counted a second population beside it: short plain
lines read as nothing between two body paragraphs of one card (43,488 in 15,796 cards). Reading
every such line as body would bring the markers among them into the evidence, so the two are ruled
together, on one table.

`2026.10.27-docx-7`, which the counts were taken under, read a marker three ways, by its formatting
and its spelling, never by what it is:

* **as body**, when it is typed into the small print or the marked-up text of a card and takes
  that formatting: it is evidence text;
* **as nothing**, when it is plain at reading size: it is left out of the evidence, as every line
  the classifier reads as nothing is;
* **as a cite**, when it opens with a capital and its hour is a two-digit number:
  `heuristic-cite-line-author-year` takes `Marked 10` for a name and a year. The card ends at the
  marker, and the rest of its body is a card with no tag whose cite is the marker.

`2026.11.03-docx-8` reads no marker as a cite (the PM's ruling M3, 2026-11-03,
:func:`~debate_core.evidence.marker_lines.is_an_in_round_marker`); the other two readings are left as
they are (M1).

:func:`line_form` names a line's form by a pattern id (:class:`LineForm`), never by its text.
:func:`describe_lines` says, for one parsed file, how each line of a body, each paragraph read as
nothing and each cite was read and where it stands (:class:`LinePlace`): the end of a body or inside
it. :func:`marker_free_bodies` gives the fingerprint each body would have with the lines of some
forms left out, and with the halves a marker read as a cite divides joined again, for matching only,
so a count can say how many clusters the markers split today.

Nothing here decides what a marker is or changes what the parser reads; the counts and the PM's
ruling do. Counts only leave this module.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from debate_core.domain.debate_files import CardCompleteness, FileSection, ParsedCard
from debate_core.domain.style_profile import StructuralUnit
from debate_core.evidence.fingerprints import card_fingerprint, fingerprint_text
from debate_core.evidence.line_above_a_cite import rule_family
from debate_core.evidence.marker_lines import (
    IN_ROUND_MARKER_FORMS,
    MARKER_FORMS,
    MARKER_LINE_MAXIMUM_CHARACTERS,
    LineForm,
    line_form,
)

__all__ = [
    "IN_ROUND_MARKER_FORMS",
    "LENGTH_BANDS",
    "MARKER_FORMS",
    "MARKER_LINE_MAXIMUM_CHARACTERS",
    "DescribedLine",
    "LineForm",
    "LinePlace",
    "MarkerFreeBody",
    "Reading",
    "describe_lines",
    "length_band",
    "line_form",
    "marker_free_bodies",
]

#: `v1-e31-t19`'s length bands, so the lines read as nothing are counted as that task counted them.
LENGTH_BANDS: Final = (
    (40, "40 characters or fewer"),
    (100, "41 to 100"),
    (200, "101 to 200"),
    (400, "201 to 400"),
    (1_000, "401 to 1,000"),
    (4_000, "1,001 to 4,000"),
)
_LONGEST_BAND: Final = "over 4,000"

#: The classifier's own sentence end (`style_classifier._SENTENCE_END`), so "ends a sentence" means
#: what it meant in `v1-e31-t19`'s table.
_SENTENCE_END: Final = re.compile(r"[.!?][\"'’”)\]]*\s*$")

#: Paragraphs the parser calls page furniture, wherever they sit.
_FURNITURE: Final = ("assembly-table-cell", "assembly-text-box")


def length_band(line: str) -> str:
    """`v1-e31-t19`'s band for a line's length, its ends trimmed."""
    length = len(line.strip())
    for bound, name in LENGTH_BANDS:
        if length <= bound:
            return name
    return _LONGEST_BAND


class Reading(StrEnum):
    """How the parser read a line."""

    BODY = "read as body"
    NOTHING = "read as nothing"
    CITE = "read as a cite"


class LinePlace(StrEnum):
    """Where a line stands. For a body, among the card's lines that say something; for a line read
    as nothing, by the nearest paragraphs above and below it that are neither blank, page furniture
    nor read as nothing."""

    BODY_ONLY_LINE = "the body's only line"
    BODY_FIRST_LINE = "the body's first line"
    BODY_INSIDE = "inside the body"
    BODY_LAST_LINE = "the end of the body"
    BETWEEN_BODY_PARAGRAPHS = "between two body paragraphs of one card"
    """Inside a body: the population `v1-e31-t19` counted 43,488 of."""
    AFTER_A_BODY = "after a body, before something else"
    """The end of a body."""
    BEFORE_A_BODY = "before a body, under a tag or a cite"
    CITE_BELOW_A_BODY_OPENING_A_CARD = "below a body, opening a card with no tag and a body"
    """Inside a body: a cite that divides one card's body in two."""
    CITE_BELOW_A_BODY_ALONE = "below a body, a card with no tag and no body"
    """The end of a body: a cite that is a card on its own, `CITE_ONLY`."""
    ELSEWHERE = "elsewhere"


@dataclass(frozen=True, slots=True)
class DescribedLine:
    """One line of a body, or one paragraph read as nothing, described without its text."""

    reading: Reading
    form: LineForm
    place: LinePlace
    card: int | None
    """The card's position in the document: its body's card, the card a line read as nothing
    stands inside or after, or the card a cite below a body opens. None elsewhere."""
    rule: str
    """The family of the rule that read the paragraph (the part before the first colon)."""
    length_band: str
    ends_a_sentence: bool
    in_capitals: bool


def _says_nothing(section: FileSection) -> bool:
    return not section.text.strip() or section.in_table or section.match.rule_id.startswith(_FURNITURE)


def _is_read_as_nothing(section: FileSection) -> bool:
    """The parser's own test: read as `OTHER`, and not a blank line or page furniture."""
    return section.unit is StructuralUnit.OTHER and not _says_nothing(section)


def _describe(
    text: str, reading: Reading, place: LinePlace, card: int | None, rule: str, form: LineForm | None = None
) -> DescribedLine:
    stripped = text.strip()
    letters = [character for character in stripped if character.isalpha()]
    return DescribedLine(
        reading=reading,
        form=form if form is not None else line_form(stripped),
        place=place,
        card=card,
        rule=rule,
        length_band=length_band(stripped),
        ends_a_sentence=_SENTENCE_END.search(stripped) is not None,
        in_capitals=bool(letters) and all(character.isupper() for character in letters),
    )


def _cards_by_element(cards: Sequence[ParsedCard]) -> dict[int, int]:
    owner: dict[int, int] = {}
    for number, card in enumerate(cards):
        for index in range(card.provenance.first_element_index, card.provenance.last_element_index + 1):
            owner[index] = number
    return owner


def _body_lines(sections: Sequence[FileSection], owner: dict[int, int]) -> list[DescribedLine]:
    """Every line of every card's body that says something: each paragraph read as body, split at
    its line breaks, as the card's evidence text splits."""
    by_card: dict[int, list[tuple[str, str]]] = {}
    for section in sections:
        card = owner.get(section.element_index)
        if section.unit is not StructuralUnit.EVIDENCE or card is None:
            continue
        rule = rule_family(section.match.rule_id)
        by_card.setdefault(card, []).extend((line, rule) for line in section.text.split("\n") if line.strip())
    described: list[DescribedLine] = []
    for card, lines in by_card.items():
        last = len(lines) - 1
        for number, (line, rule) in enumerate(lines):
            if last == 0:
                place = LinePlace.BODY_ONLY_LINE
            elif number == 0:
                place = LinePlace.BODY_FIRST_LINE
            elif number == last:
                place = LinePlace.BODY_LAST_LINE
            else:
                place = LinePlace.BODY_INSIDE
            described.append(_describe(line, Reading.BODY, place, card, rule))
    return described


def _nearest(sections: Sequence[FileSection], position: int, step: int) -> int | None:
    """The nearest paragraph that is neither blank, page furniture nor read as nothing."""
    other = position + step
    while 0 <= other < len(sections) and (
        _says_nothing(sections[other]) or _is_read_as_nothing(sections[other])
    ):
        other += step
    return other if 0 <= other < len(sections) else None


def _lines_read_as_nothing(sections: Sequence[FileSection], owner: dict[int, int]) -> list[DescribedLine]:
    described: list[DescribedLine] = []
    for position, section in enumerate(sections):
        if not _is_read_as_nothing(section):
            continue
        above, below = _nearest(sections, position, -1), _nearest(sections, position, 1)
        body_above = (
            owner.get(sections[above].element_index)
            if above is not None and sections[above].unit is StructuralUnit.EVIDENCE
            else None
        )
        body_below = (
            owner.get(sections[below].element_index)
            if below is not None and sections[below].unit is StructuralUnit.EVIDENCE
            else None
        )
        if body_above is not None and body_above == body_below:
            place, card = LinePlace.BETWEEN_BODY_PARAGRAPHS, body_above
        elif body_above is not None:
            place, card = LinePlace.AFTER_A_BODY, body_above
        elif body_below is not None and owner.get(section.element_index) == body_below:
            place, card = LinePlace.BEFORE_A_BODY, body_below
        else:
            place, card = LinePlace.ELSEWHERE, None
        # A paragraph read as nothing is one line to the count, its line breaks read as spaces.
        text = " ".join(section.text.split())
        described.append(_describe(text, Reading.NOTHING, place, card, rule_family(section.match.rule_id)))
    return described


def _opens_a_card_below_a_body(
    sections: Sequence[FileSection], position: int, owner: dict[int, int], cards: Sequence[ParsedCard]
) -> int | None:
    """The card a cite opens directly below the body of the card above, with no tag: or None."""
    section = sections[position]
    card = owner.get(section.element_index)
    if card is None or card == 0 or cards[card].tag is not None:
        return None
    if cards[card].provenance.first_element_index != section.element_index:
        return None
    above = _nearest(sections, position, -1)
    if above is None or sections[above].unit is not StructuralUnit.EVIDENCE:
        return None
    return card if owner.get(sections[above].element_index) == card - 1 else None


def _cite_lines(
    sections: Sequence[FileSection], owner: dict[int, int], cards: Sequence[ParsedCard]
) -> list[DescribedLine]:
    described: list[DescribedLine] = []
    for position, section in enumerate(sections):
        if section.unit is not StructuralUnit.CITE or not section.text.strip():
            continue
        card = _opens_a_card_below_a_body(sections, position, owner, cards)
        if card is None:
            place = LinePlace.ELSEWHERE
        elif cards[card].completeness is CardCompleteness.CITE_ONLY:
            place = LinePlace.CITE_BELOW_A_BODY_ALONE
        else:
            place = LinePlace.CITE_BELOW_A_BODY_OPENING_A_CARD
        text = " ".join(section.text.split())
        described.append(_describe(text, Reading.CITE, place, card, rule_family(section.match.rule_id)))
    return described


def describe_lines(sections: Sequence[FileSection], cards: Sequence[ParsedCard]) -> list[DescribedLine]:
    """Every line of a card's body, every paragraph read as nothing and every cite in one parsed file.

    A body's lines are its paragraphs read as body split at their line breaks, so a marker typed
    after a line break at the end of a paragraph is a line of its own, as it is in the card's
    evidence text. A paragraph read as nothing, or as a cite, is one line.
    """
    owner = _cards_by_element(cards)
    return [
        *_body_lines(sections, owner),
        *_lines_read_as_nothing(sections, owner),
        *_cite_lines(sections, owner, cards),
    ]


@dataclass(frozen=True, slots=True)
class MarkerFreeBody:
    """A body as it would be matched with the lines of some forms left out.

    For matching only: :attr:`fingerprint` is a digest, and the text it was computed from is never
    kept, stored or shown, exactly as
    :func:`~debate_core.evidence.fingerprints.normalize_for_matching`'s output is not.
    """

    exact_fingerprints: tuple[str, ...]
    """The exact fingerprints of the cards the body is today: one, or each card with a body that a
    marker read as a cite divides it into, in document order."""
    fingerprint: str
    """The body's fingerprint with the lines of the forms left out and its parts joined again."""


def _kept_lines(evidence_text: str, forms: frozenset[LineForm]) -> list[str]:
    return [line for line in evidence_text.split("\n") if not (line.strip() and line_form(line) in forms)]


def marker_free_bodies(
    sections: Sequence[FileSection], cards: Sequence[ParsedCard], forms: Iterable[LineForm]
) -> list[MarkerFreeBody]:
    """Each body in one parsed file that the lines of `forms` change, as it would be without them.

    A body changes when a line of its evidence text has one of the forms, or when a cite of one of
    the forms opens a card with no tag directly below it (:attr:`LinePlace.CITE_BELOW_A_BODY_OPENING_A_CARD`
    and :attr:`LinePlace.CITE_BELOW_A_BODY_ALONE`): the card below is then the rest of this body, and
    the two are joined, as many times over as such cites follow one another. A body no line or cite
    of `forms` touches is not listed.
    """
    left_out = frozenset(forms)
    owner = _cards_by_element(cards)
    continues: set[int] = set()
    for position, section in enumerate(sections):
        if section.unit is not StructuralUnit.CITE:
            continue
        card = _opens_a_card_below_a_body(sections, position, owner, cards)
        if card is None:
            continue
        cite_lines = [line for line in cards[card].full_cite.split("\n") if line.strip()]
        if cite_lines and all(line_form(line) in left_out for line in cite_lines):
            continues.add(card)

    groups: list[list[int]] = []
    for number in range(len(cards)):
        if number in continues and groups:
            groups[-1].append(number)
        else:
            groups.append([number])

    bodies: list[MarkerFreeBody] = []
    for group in groups:
        with_a_body = [
            cards[number] for number in group if cards[number].completeness is not CardCompleteness.CITE_ONLY
        ]
        if not with_a_body:
            continue
        kept = [line for card in with_a_body for line in _kept_lines(card.evidence_text, left_out)]
        exact = tuple(card_fingerprint(card).exact_fingerprint for card in with_a_body)
        fingerprint = fingerprint_text("\n".join(kept))
        if len(exact) == 1 and fingerprint == exact[0]:
            continue
        bodies.append(MarkerFreeBody(exact_fingerprints=exact, fingerprint=fingerprint))
    return bodies
