"""Two kinds of card boundary the parser misses, described in counts (`v1-e31-t22`).

**A body too long to be one card.** hspf26's second-largest cluster after the 2026-10-16 re-parse
held 75 distinct texts of 1,414 to 7,485 words. A card a debater reads is a few hundred words, so
a stored body over :data:`LONG_BODY_WORDS` is either a legitimately long card or something the
parser did not divide: several cards whose tags or cites it did not read, or a document that holds
no cards at all, such as a case or a speech written out as prose. :func:`read_long_body` says, for
one such card, what ended it and what is inside it, from the paragraphs the parser read
(:class:`LongBody`). Nothing here decides which it is; the counts and a person's sample do.

**Two cards stored as one.** `v1-e31-t11`'s one false join went through a 150-word body holding two
shorter bodies whole, which share no text with each other. :func:`bodies_holding_two_cards` finds
every such body in a caselist, with
:class:`~debate_core.evidence.near_duplicates.CutIndex`'s own reading of "holds", so the count is
of exactly the containment the clusterer acts on. A body holding two passages may be a missed
boundary (a tag the parser did not read between two cut cards) or one long card that two teams cut
differently; again the sample says which.

Counts only leave this module. Rule ids are reduced to their family, the part before the first
colon, because what follows the colon can name a style the file defined.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from debate_core.domain.debate_files import FileSection, ParsedCard, ParsedDocument
from debate_core.domain.style_profile import RunEmphasis, StructuralUnit, StyleMatchSource, StyleProfile
from debate_core.evidence.near_duplicates import SHORT_BODY_SHINGLES, CutIndex
from debate_core.evidence.style_classifier import (
    MAXIMUM_HEADING_CHARACTERS,
    MAXIMUM_LONG_CITE_LINE_CHARACTERS,
    NAME_AND_YEAR_AT_THE_HEAD_CHARACTERS,
    first_name_and_year,
)

__all__ = [
    "LONG_BODY_WORDS",
    "MARKED_UP_SHARE",
    "Ending",
    "Holding",
    "LongBody",
    "LongBodyKind",
    "bodies_holding_two_cards",
    "is_cite_shaped",
    "read_long_body",
    "rule_family",
    "tally_holdings",
    "tally_long_bodies",
    "word_count",
]

LONG_BODY_WORDS: Final = 3_000
"""A stored body longer than this, in words, is counted as too long to be one card (the spec's line)."""

MARKED_UP_SHARE: Final = 0.05
"""A body with at least this share of its characters underlined, emphasised or highlighted is marked
up: cut by a debater. Below it, a body with no cite inside is counted as plain prose. A cut card
underlines a fifth to a half of its words; a speech written out underlines a heading or two."""

#: The rule id prefix of a tag the assembly demoted because no cite or body followed it.
_DEMOTED_TAG: Final = "assembly-tag-without-cite-or-evidence:"

#: Paragraphs the parser calls page furniture, wherever they sit.
_FURNITURE: Final = frozenset({"assembly-table-cell", "assembly-text-box"})

_MARKED_UP: Final = frozenset({RunEmphasis.UNDERLINE, RunEmphasis.EMPHASIS, RunEmphasis.HIGHLIGHT})

_SECTION_HEADINGS: Final = (StructuralUnit.POCKET, StructuralUnit.HAT, StructuralUnit.BLOCK)


class Ending(StrEnum):
    """What closed a card: the first paragraph after it that the parser read as something."""

    TAG_IN_A_DEBATE_STYLE = "a tag in a debate style"
    TAG_GUESSED = "a tag the classifier guessed from its formatting"
    SECTION_HEADING = "a pocket, hat or block heading"
    TAG_WITH_NOTHING_UNDER_IT = "a tag with no cite or body under it"
    ANALYTIC = "an analytic"
    CITE = "a cite, starting a card with no tag"
    END_OF_FILE = "the end of the file"


class LongBodyKind(StrEnum):
    """What a long body holds, by its paragraphs, first that applies.

    Each is a guess about what the body is, and the sample is what tests it.
    """

    LINE_ABOVE_A_CITE_INSIDE = "a short line above a cite-shaped paragraph inside"
    """A line of a tag's length, then a paragraph that names its source at its head: a card's tag
    and cite, neither read."""
    CITE_INSIDE = "a cite-shaped paragraph inside, with no short line above it"
    """Cards divided only by their cites, which the parser did not read."""
    MARKED_UP_WITHOUT_A_CITE_INSIDE = "no cite inside, marked up"
    """One long card, or cards with neither tag nor cite between them."""
    PLAIN_PROSE = "no cite inside, plain prose"
    """Little or nothing underlined or highlighted: a case, a speech or notes written out."""


@dataclass(frozen=True, slots=True)
class LongBody:
    """One card whose body is over :data:`LONG_BODY_WORDS`, as its file's paragraphs describe it.

    Counts and names of rules only: nothing here holds a word of the card.
    """

    words: int
    ending: Ending
    file_writes_tags: bool
    """The file holds a tag anywhere, read as one or demoted for having no card under it."""
    file_uses_debate_styles: bool
    """Some paragraph of the file is set in a style the profile maps to a unit, or carries the cite
    character style. False is a file with no styles a debate template gives."""
    has_tag: bool
    has_cite: bool
    cards_in_file: int
    paragraphs: int
    """The body's paragraphs that say something."""
    cite_shaped_paragraphs: int
    """Paragraphs inside the card's range, after its body has begun, that name a source at their
    head (:func:`is_cite_shaped`), read as body or as nothing."""
    short_lines_above_a_cite: int
    """Of those, the ones directly below a line no longer than a heading: where a tag would be."""
    marked_up_share: float
    cite_shaped_rules: tuple[str, ...] = ()
    """The rule family each cite-shaped paragraph was read by, in order."""

    @property
    def kind(self) -> LongBodyKind:
        if self.short_lines_above_a_cite:
            return LongBodyKind.LINE_ABOVE_A_CITE_INSIDE
        if self.cite_shaped_paragraphs:
            return LongBodyKind.CITE_INSIDE
        if self.marked_up_share >= MARKED_UP_SHARE:
            return LongBodyKind.MARKED_UP_WITHOUT_A_CITE_INSIDE
        return LongBodyKind.PLAIN_PROSE


def word_count(text: str) -> int:
    """Words as the spec counts them: runs of characters between whitespace."""
    return len(text.split())


def rule_family(rule_id: str) -> str:
    """The rule that decided, without what follows its first colon, which may name a file's style."""
    return rule_id.split(":", 1)[0]


def is_cite_shaped(text: str, profile: StyleProfile) -> bool:
    """Whether a paragraph names its source at its head, as a cite does.

    A name and a year within
    :data:`~debate_core.evidence.style_classifier.NAME_AND_YEAR_AT_THE_HEAD_CHARACTERS` of the start
    (behind a bracket or a first name too), in a paragraph no longer than the longest cite line the
    classifier reads. A sentence that opens with *In 2019* names no source and is not.
    """
    stripped = text.strip()
    if not stripped or len(stripped) > MAXIMUM_LONG_CITE_LINE_CHARACTERS:
        return False
    found = first_name_and_year(stripped, profile)
    return found is not None and found.start() <= NAME_AND_YEAR_AT_THE_HEAD_CHARACTERS


def _ending(after: Sequence[FileSection]) -> Ending:
    """What the first paragraph after a card that the parser read as something says closed it."""
    for section in after:
        unit = section.match.unit
        if unit is StructuralUnit.OTHER:
            continue
        if unit is StructuralUnit.TAG:
            if section.match.match_source is StyleMatchSource.HEURISTIC:
                return Ending.TAG_GUESSED
            return Ending.TAG_IN_A_DEBATE_STYLE
        if unit in _SECTION_HEADINGS:
            return Ending.SECTION_HEADING
        if unit is StructuralUnit.ANALYTIC:
            if section.match.rule_id.startswith(_DEMOTED_TAG):
                return Ending.TAG_WITH_NOTHING_UNDER_IT
            return Ending.ANALYTIC
        # A body paragraph or an undertag after a card is folded into it, so what is left is a cite.
        return Ending.CITE
    return Ending.END_OF_FILE


def _writes_tags(sections: Sequence[FileSection]) -> bool:
    return any(
        section.match.unit is StructuralUnit.TAG or section.match.rule_id.startswith(_DEMOTED_TAG)
        for section in sections
    )


def _uses_debate_styles(sections: Sequence[FileSection]) -> bool:
    """Whether a paragraph's own style, or a cite character style, made it a unit.

    A style the profile maps to `OTHER` (`Normal`, `Normal (Web)`) is no debate style. The assembly
    rewrites some matches; the rule it overrode is kept after the first colon, and a rewrite of a
    style match (a blank heading, a demoted tag) still says the file uses the style.
    """
    for section in sections:
        match = section.match
        if match.match_source is not StyleMatchSource.HEURISTIC and match.unit is not StructuralUnit.OTHER:
            return True
        if match.rule_id.startswith("assembly-") and match.rule_id.partition(":")[2].startswith("verbatim-"):
            return True
    return False


def _marked_up_share(card: ParsedCard) -> float:
    """The share of the body's characters under an underline, an emphasis or a highlight."""
    if not card.evidence_text:
        return 0.0
    covered = [False] * len(card.evidence_text)
    for span in card.formatting_spans:
        if span.emphasis in _MARKED_UP:
            covered[span.start_offset : span.end_offset] = [True] * (span.end_offset - span.start_offset)
    return sum(covered) / len(card.evidence_text)


def read_long_body(document: ParsedDocument, card: ParsedCard, profile: StyleProfile) -> LongBody:
    """Describe one card of `document` by its file's paragraphs: what ended it, and what is inside.

    `document` must hold its sections, as the parser returns it; the store leaves them out, so the
    caller parses the source again.
    """
    sections = document.sections
    first = card.provenance.first_element_index
    last = card.provenance.last_element_index
    inside = [section for section in sections if first <= section.element_index <= last]
    after = [section for section in sections if section.element_index > last]

    cite_shaped_rules: list[str] = []
    short_lines_above = 0
    body_begun = False
    above: FileSection | None = None
    paragraphs = 0
    for section in inside:
        if section.match.rule_id in _FURNITURE or not section.text.strip():
            continue
        unit = section.match.unit
        if unit in (StructuralUnit.EVIDENCE, StructuralUnit.OTHER):
            if body_begun and is_cite_shaped(section.text, profile):
                cite_shaped_rules.append(rule_family(section.match.rule_id))
                if (
                    above is not None
                    and above.match.unit in (StructuralUnit.EVIDENCE, StructuralUnit.OTHER)
                    and len(above.text.strip()) <= MAXIMUM_HEADING_CHARACTERS
                    and not is_cite_shaped(above.text, profile)
                ):
                    short_lines_above += 1
            if unit is StructuralUnit.EVIDENCE:
                body_begun = True
                paragraphs += 1
        above = section

    return LongBody(
        words=word_count(card.evidence_text),
        ending=_ending(after),
        file_writes_tags=_writes_tags(sections),
        file_uses_debate_styles=_uses_debate_styles(sections),
        has_tag=card.has_tag,
        has_cite=bool(card.full_cite.strip()),
        cards_in_file=len(document.cards),
        paragraphs=paragraphs,
        cite_shaped_paragraphs=len(cite_shaped_rules),
        short_lines_above_a_cite=short_lines_above,
        marked_up_share=_marked_up_share(card),
        cite_shaped_rules=tuple(cite_shaped_rules),
    )


# ------------------------------------------------------------------------------------------------
# Bodies holding two cards
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Holding:
    """A body that holds two or more shorter bodies whole, by exact fingerprint."""

    holder: str
    held: tuple[str, ...]
    """Every body it holds and does not merely copy, smallest first."""
    pair_sharing_nothing: tuple[str, str] | None
    """Two held bodies that share no five-word run: of all such pairs, the one whose smaller body
    is largest, then by fingerprint. None when every two overlap somewhere."""
    pair_not_overlapping: tuple[str, str] | None
    """The same, of two held bodies that do not overlap by the clusterer's measure
    (:meth:`~debate_core.evidence.near_duplicates.CutIndex.overlap`): a looser test than sharing
    nothing, and the one the clusterer refuses a witness by."""
    sharing_nothing: int
    """How many held bodies share no run with one another: the pair above, then the rest smallest
    first. At least this many cards are in the body; 0 when no two share nothing."""


def _best_pair(
    index: CutIndex, held: Sequence[str], apart: Callable[[str, str], bool]
) -> tuple[str, str] | None:
    best: tuple[int, str, str] | None = None
    for position, left in enumerate(held):
        for right in held[position + 1 :]:
            if not apart(left, right):
                continue
            smaller = min(index.size(left), index.size(right))
            candidate = (-smaller, min(left, right), max(left, right))
            if best is None or candidate < best:
                best = candidate
    return None if best is None else (best[1], best[2])


def bodies_holding_two_cards(index: CutIndex) -> list[Holding]:
    """Every body of `index` holding at least two other bodies whole that do not overlap.

    "Holds" is :meth:`~debate_core.evidence.near_duplicates.CutIndex.containers`: at least as large,
    holding the shorter one's first or last five-word run, and containing nine-tenths of it or all
    of it but for one word; a copy, which each holds the other, is not held. Sorted by fingerprint.
    """
    held_by: defaultdict[str, list[str]] = defaultdict(list)
    for cut in index.fingerprints:
        for holder in index.containers(cut):
            held_by[holder].append(cut)

    def share_nothing(left: str, right: str) -> bool:
        return index.sets[left].isdisjoint(index.sets[right])

    def do_not_overlap(left: str, right: str) -> bool:
        return not index.overlap(left, right)

    holdings: list[Holding] = []
    for holder in sorted(held_by):
        held = index.by_size(held_by[holder])
        if len(held) < 2:
            continue
        loose = _best_pair(index, held, do_not_overlap)
        if loose is None:
            continue
        pair = _best_pair(index, held, share_nothing)
        chosen: list[str] = list(pair or ())
        if pair is not None:
            for body in held:
                if body not in chosen and all(share_nothing(body, other) for other in chosen):
                    chosen.append(body)
        holdings.append(
            Holding(
                holder=holder,
                held=tuple(held),
                pair_sharing_nothing=pair,
                pair_not_overlapping=loose,
                sharing_nothing=len(chosen),
            )
        )
    return holdings


# ------------------------------------------------------------------------------------------------
# Tallies
# ------------------------------------------------------------------------------------------------

#: Word bands of a long body, as (lowest, highest or None).
LONG_BODY_WORD_BANDS: Final = ((3_001, 5_000), (5_001, 10_000), (10_001, None))

#: Word bands of a body holding two cards.
HOLDER_WORD_BANDS: Final = ((0, 299), (300, 999), (1_000, 2_999), (3_000, None))

#: How many cards a long body's file holds.
CARDS_IN_FILE_BANDS: Final = ((1, 1), (2, 5), (6, 20), (21, None))

#: How many held bodies share no text.
SHARING_NOTHING_BANDS: Final = ((2, 2), (3, 5), (6, None))


def _band(value: int, bands: Sequence[tuple[int, int | None]]) -> str:
    for lowest, highest in bands:
        if value >= lowest and (highest is None or value <= highest):
            if highest is None:
                return f"{lowest:,} or more"
            return f"{lowest:,}" if lowest == highest else f"{lowest:,} to {highest:,}"
    raise ValueError(f"{value} is in no band")


def _marked_up_band(share: float) -> str:
    if share == 0:
        return "none"
    return f"under {MARKED_UP_SHARE:.0%}" if share < MARKED_UP_SHARE else f"{MARKED_UP_SHARE:.0%} or more"


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _sorted(counter: Counter[str]) -> dict[str, int]:
    return dict(sorted(counter.items()))


@dataclass(slots=True)
class _Tally:
    counters: defaultdict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter[str]))

    def add(self, name: str, key: str) -> None:
        self.counters[name][key] += 1

    def result(self) -> dict[str, dict[str, int]]:
        return {name: _sorted(counter) for name, counter in sorted(self.counters.items())}


def tally_long_bodies(bodies: Iterable[LongBody]) -> dict[str, object]:
    """Counts of long bodies, split as the spec asks and by what is inside them. No text."""
    tally = _Tally()
    cards = 0
    for body in bodies:
        cards += 1
        tags = f"file writes tags: {_yes_no(body.file_writes_tags)}"
        tally.add("by_ending", body.ending.value)
        tally.add("by_file_writing_tags", tags)
        tally.add("by_ending_and_file_writing_tags", f"{body.ending.value} | {tags}")
        tally.add("by_kind", body.kind.value)
        tally.add(
            "by_kind_and_file_styles",
            f"{body.kind.value} | debate styles: {_yes_no(body.file_uses_debate_styles)}",
        )
        tally.add("by_file_using_debate_styles", _yes_no(body.file_uses_debate_styles))
        tally.add("by_words", _band(body.words, LONG_BODY_WORD_BANDS))
        tally.add("by_cards_in_file", _band(body.cards_in_file, CARDS_IN_FILE_BANDS))
        tally.add("by_marked_up_share", _marked_up_band(body.marked_up_share))
        tally.add("by_tag_and_cite", f"tag: {_yes_no(body.has_tag)} | cite: {_yes_no(body.has_cite)}")
        for rule in body.cite_shaped_rules:
            tally.add("cite_shaped_paragraphs_by_rule", rule)
    return {"cards": cards, **tally.result()}


def tally_holdings(
    holdings: Iterable[Holding],
    index: CutIndex,
    *,
    cards_by_fingerprint: Mapping[str, int],
    long_bodies: frozenset[str] = frozenset(),
) -> dict[str, object]:
    """Counts of bodies holding two cards, in distinct texts and in stored cards. No text.

    `cards_by_fingerprint` gives how many stored cards carry each body; `long_bodies` names the
    bodies over :data:`LONG_BODY_WORDS`, so the two counts can be told apart.
    """
    sharing_nothing = _Tally()
    not_overlapping = 0
    texts = cards = 0
    for holding in holdings:
        not_overlapping += 1
        pair = holding.pair_sharing_nothing
        if pair is None:
            continue
        texts += 1
        cards += cards_by_fingerprint.get(holding.holder, 0)
        words = len(index.words[holding.holder])
        smaller = min(index.size(pair[0]), index.size(pair[1]))
        sharing_nothing.add("by_holder_words", _band(words, HOLDER_WORD_BANDS))
        sharing_nothing.add(
            "by_smaller_of_the_two",
            "short (under 64 words)" if smaller < SHORT_BODY_SHINGLES else "long (64 words or more)",
        )
        sharing_nothing.add(
            "by_bodies_sharing_nothing", _band(holding.sharing_nothing, SHARING_NOTHING_BANDS)
        )
        sharing_nothing.add("by_holder_over_the_long_body_line", _yes_no(holding.holder in long_bodies))
    return {
        "full_texts": len(index.fingerprints),
        "holding_two_sharing_nothing_texts": texts,
        "holding_two_sharing_nothing_cards": cards,
        "holding_two_not_overlapping_texts": not_overlapping,
        **sharing_nothing.result(),
    }
