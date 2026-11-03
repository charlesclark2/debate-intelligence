"""The line above a cite, described in counts (`v1-e31-t24`).

`v1-e31-t19`'s item (7): in one hspf26 file, two cards read by the bracketed cite-line rule
(`heuristic-cite-line-bracketed`) have no tag, and the line above each cite was read as body. The
operator checked both in Word: each line is the card's tag, formatted as an ordinary bold tag. A
tag the parser does not read leaves its card with none, and the line goes into the body of the
card above it.

:func:`lines_above_cites` says, for each cite in one parsed file, what the paragraph directly above
it was read as and how it is formatted, so that a count over the store can say how often a line in
bold or in a tag style stands above such a cite read as body or as nothing
(:attr:`LineAboveACite.is_the_shape`), and what kept the classifier's bold-heading rule from reading
it as a tag. Bold and size are described twice: as the reader gives them, from what each run says,
and as Word shows them, with what a run inherits from its styles and the document's defaults
(:func:`~debate_core.integrations.docx_parser.runs.as_word_shows_it`). (7)'s two lines say nothing of
bold or size; their file's defaults make every such run bold at 13 pt.

:func:`bold_lines_read_as_body_or_nothing` counts, in one file, every line Word shows as the
classifier's bold-heading rule would take it, where the parser read body or nothing.

`v1-e31-t32` asks where the tags t24's rule leaves stand. :attr:`LineAboveACite.failing_conditions`
lists, in the order t24's report counted them, each :class:`FailingCondition` of the rule a line
fails, and :func:`unbolded_part` says, in counts, where the unbolded part of a line bold in part
sits and what it is made of: never its text. :attr:`UnboldedPart.shape` names the
:class:`BoldInPartShape` the sample's answers were split by.

Nothing here decides whether such a line is a tag; the counts and the PM's ruling do. Counts only
leave this module. Rule ids are reduced to their family, the part before the first colon, because
what follows the colon can name a style the file defined.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from debate_core.domain.debate_files import FileSection, ParsedCard
from debate_core.domain.style_profile import RunEmphasis, StructuralUnit, StyleMatchSource, StyleProfile
from debate_core.evidence.style_classifier import (
    MAXIMUM_HEADING_CHARACTERS,
    NAME_AND_YEAR_AT_THE_HEAD_CHARACTERS,
    ParagraphDescription,
    first_name_and_year,
)

__all__ = [
    "BRACKETED_CITE_RULES",
    "BoldInPartShape",
    "BoldLine",
    "Boldness",
    "FailingCondition",
    "LineAboveACite",
    "LineSize",
    "Place",
    "UnboldedPart",
    "bold_lines_read_as_body_or_nothing",
    "line_above",
    "lines_above_cites",
    "rule_family",
    "tally_bold_lines",
    "tally_lines_above_cites",
    "unbolded_part",
]

BRACKETED_CITE_RULES: Final = frozenset(
    {"heuristic-cite-line-bracketed", "assembly-bracketed-cite-before-the-body"}
)
"""The rules that read a cite by its bracket: a cite line whose credentials sit in one bracket after
the name and year (`v1-e31-t12`'s classifier rule), and a cite written wholly inside one bracket
where a cite stands (`v1-e31-t12`'s assembly rule)."""

#: Paragraphs the parser calls page furniture, wherever they sit.
_FURNITURE: Final = ("assembly-table-cell", "assembly-text-box")


class Boldness(StrEnum):
    """How much of a line is bold, its paragraph mark's bold counted for a run that says nothing."""

    ALL = "bold throughout"
    SOME = "bold in part"
    NONE = "not bold"


class LineSize(StrEnum):
    """A line's size, as the classifier's bold-heading rule reads it (its largest run, or its mark)."""

    NOT_STATED = "no size stated"
    """Nothing gives a size. As the reader sees it, the bold-heading rule needs one, so a bold line
    of this kind is never a tag by it."""
    BELOW_READING_SIZE = "below reading size"
    READING_SIZE_OR_LARGER = "reading size or larger"


class FailingCondition(StrEnum):
    """One condition of `v1-e31-t24`'s rule that a line above a cite fails, in the order t24's
    report counted the 3,573 lines the rule left on `2026.10.18-docx-5`: how the line was read,
    then its bold, then what a bold line must also be. The guards the PM added in the ruling of
    2026-10-20 come last, so that a line they leave is counted as bold throughout first."""

    READ_BY_AN_ASSEMBLY_RULE_OR_A_STYLE = "read by an assembly rule or through a style"
    BEHIND_AN_UNMAPPED_STYLE = "behind a style that maps to no unit"
    NOT_BOLD = "not bold, as Word shows it"
    BOLD_IN_PART = "bold in part, as Word shows it"
    LONGER_THAN_A_HEADING = "over 300 characters"
    NOT_AT_READING_SIZE = "below reading size or no size stated, as Word shows it"
    NAMES_A_SOURCE_AT_ITS_HEAD = "names a source at its head"
    HIGHLIGHTED = "a highlighted run"
    IN_AN_EVIDENCE_STYLE = "a run in the underline or emphasis style"


@dataclass(frozen=True, slots=True)
class LineAboveACite:
    """The paragraph directly above one cite, as the parser read it. Counts and rule names only."""

    cite_rule: str
    """The family of the rule that read the cite."""
    cite_opens_a_card_with_no_tag: bool
    """The cite is the first paragraph of a card whose tag is empty."""
    line_unit: StructuralUnit | None
    """What the line was read as; None when nothing stands above the cite in the file."""
    line_rule: str = ""
    """The family of the rule that read the line."""
    line_read_by_a_heuristic: bool = False
    """The classifier read the line by a heuristic, not from a paragraph style, and the assembly
    did not re-read it."""
    line_behind_an_unmapped_style: bool = False
    """The line's paragraph style maps to no unit, which the classifier's heading rules never see
    through (`v1-e31-t19`)."""
    boldness: Boldness = Boldness.NONE
    """As the reader gives it: from what the line's runs and paragraph mark say."""
    boldness_as_word_shows_it: Boldness = Boldness.NONE
    in_a_tag_style: bool = False
    """The line's paragraph style is a tag's, or every run of it carries a heading's character style."""
    size: LineSize = LineSize.NOT_STATED
    """As the reader gives it."""
    size_as_word_shows_it: LineSize = LineSize.NOT_STATED
    underlined: bool = False
    highlighted: bool = False
    in_an_evidence_style: bool = False
    """A run carries the underline or emphasis character style: evidence a debater cut."""
    no_longer_than_a_heading: bool = False
    """At most :data:`~debate_core.evidence.style_classifier.MAXIMUM_HEADING_CHARACTERS`."""
    names_a_source_at_its_head: bool = False
    """A name and a year within the first
    :data:`~debate_core.evidence.style_classifier.NAME_AND_YEAR_AT_THE_HEAD_CHARACTERS` characters."""
    ends_the_card_above: bool = False
    """The line is the last paragraph of another card: read as body, it went into that card."""
    blank_lines_between: bool = False
    """Blank lines or page furniture stand between the line and the cite."""

    @property
    def read_as_body_or_nothing(self) -> bool:
        return self.line_unit in (StructuralUnit.EVIDENCE, StructuralUnit.OTHER)

    @property
    def is_the_shape(self) -> bool:
        """Read as body or as nothing, and bold throughout as Word shows it or in a tag style: (7)'s shape."""
        return self.read_as_body_or_nothing and (
            self.boldness_as_word_shows_it is Boldness.ALL or self.in_a_tag_style
        )

    @property
    def the_proposed_rule_takes(self) -> bool:
        """Whether the rule proposed to the PM would read the line as the card's tag. Counted only.

        The cite opens a card with no tag; the line was read as body or as nothing by a heuristic,
        not through a style that maps to no unit; and, as Word shows it, it is bold throughout at
        reading size or larger, as the classifier's bold-heading rule asks, no longer than a
        heading, and names no source at its head.
        """
        return (
            self.cite_opens_a_card_with_no_tag
            and self.read_as_body_or_nothing
            and self.line_read_by_a_heuristic
            and not self.line_behind_an_unmapped_style
            and self.boldness_as_word_shows_it is Boldness.ALL
            and self.size_as_word_shows_it is LineSize.READING_SIZE_OR_LARGER
            and self.no_longer_than_a_heading
            and not self.names_a_source_at_its_head
        )

    @property
    def failing_conditions(self) -> tuple[FailingCondition, ...]:
        """Each condition of `v1-e31-t24`'s rule the line fails, in :class:`FailingCondition`'s order.

        Empty for a line that fails none, which the parser still leaves when the cite below is a
        guess a body may yet take. Asked only of a line read as body or as nothing; whether the cite
        opens a card with no tag is the caller's.
        """
        failing: list[FailingCondition] = []
        if not self.line_read_by_a_heuristic:
            failing.append(FailingCondition.READ_BY_AN_ASSEMBLY_RULE_OR_A_STYLE)
        if self.line_behind_an_unmapped_style:
            failing.append(FailingCondition.BEHIND_AN_UNMAPPED_STYLE)
        if self.boldness_as_word_shows_it is Boldness.NONE:
            failing.append(FailingCondition.NOT_BOLD)
        elif self.boldness_as_word_shows_it is Boldness.SOME:
            failing.append(FailingCondition.BOLD_IN_PART)
        if not self.no_longer_than_a_heading:
            failing.append(FailingCondition.LONGER_THAN_A_HEADING)
        if self.size_as_word_shows_it is not LineSize.READING_SIZE_OR_LARGER:
            failing.append(FailingCondition.NOT_AT_READING_SIZE)
        if self.names_a_source_at_its_head:
            failing.append(FailingCondition.NAMES_A_SOURCE_AT_ITS_HEAD)
        if self.highlighted:
            failing.append(FailingCondition.HIGHLIGHTED)
        if self.in_an_evidence_style:
            failing.append(FailingCondition.IN_AN_EVIDENCE_STYLE)
        return tuple(failing)


class Place(StrEnum):
    """Where in a line a stretch of it stands."""

    HEAD = "the head"
    MIDDLE = "the middle"
    TAIL = "the tail"


class BoldInPartShape(StrEnum):
    """Where a line bold in part is left unbolded, as `v1-e31-t32`'s sample split its answers."""

    TAIL_PUNCTUATION_ONLY = "unbolded only at the tail, punctuation only"
    TAIL_WITHOUT_DIGITS = "unbolded only at the tail, letters and no digits"
    TAIL_WITH_DIGITS = "unbolded only at the tail, with digits"
    HEAD_ONLY = "unbolded only at the head"
    BOTH_ENDS_ONLY = "unbolded at the head and the tail only"
    IN_THE_MIDDLE = "unbolded in the middle"


@dataclass(frozen=True, slots=True)
class UnboldedPart:
    """The unbolded part of a line bold in part, in counts. Spaces are not counted."""

    characters: int
    of: int
    """Every character of the line."""
    stretches: int
    """Runs of unbolded characters with bold between them."""
    places: tuple[Place, ...]
    """Where the stretches stand, each place once, head first."""
    holds_letters: bool
    holds_digits: bool

    def described(self) -> str:
        """For example `4 of 52 characters, 1 stretch, at the tail; digits and punctuation only`."""
        stretches = "1 stretch" if self.stretches == 1 else f"{self.stretches} stretches"
        places = " and ".join(place.value for place in self.places)
        if self.holds_letters:
            kind = "letters" + (" and digits" if self.holds_digits else "")
        else:
            kind = "digits and punctuation only" if self.holds_digits else "punctuation only"
        return f"{self.characters} of {self.of} characters, {stretches}, at {places}; {kind}"

    @property
    def shape(self) -> BoldInPartShape:
        if Place.MIDDLE in self.places:
            return BoldInPartShape.IN_THE_MIDDLE
        if self.places == (Place.HEAD,):
            return BoldInPartShape.HEAD_ONLY
        if self.places == (Place.HEAD, Place.TAIL):
            return BoldInPartShape.BOTH_ENDS_ONLY
        if self.holds_digits:
            return BoldInPartShape.TAIL_WITH_DIGITS
        if self.holds_letters:
            return BoldInPartShape.TAIL_WITHOUT_DIGITS
        return BoldInPartShape.TAIL_PUNCTUATION_ONLY


def unbolded_part(description: ParagraphDescription) -> UnboldedPart | None:
    """Where the line's unbolded characters stand and what they are; None when none is or all are.

    A run's bold is what it says, or its paragraph mark's when it says nothing, as
    :class:`Boldness` counts it; pass the line as Word shows it to count what Word shows.
    """
    bold: list[bool] = []
    letters = digits = False
    for run in description.runs:
        run_bold = run.bold if run.bold is not None else bool(description.paragraph_bold)
        for character in run.text:
            if character.isspace():
                continue
            bold.append(run_bold)
            if not run_bold:
                letters = letters or character.isalpha()
                digits = digits or character.isdigit()
    unbolded = bold.count(False)
    if not unbolded or unbolded == len(bold):
        return None
    places: set[Place] = set()
    stretches = 0
    for at, is_bold in enumerate(bold):
        if is_bold or (at > 0 and not bold[at - 1]):
            continue
        stretches += 1
        ends = at
        while ends + 1 < len(bold) and not bold[ends + 1]:
            ends += 1
        places.add(Place.HEAD if at == 0 else Place.TAIL if ends == len(bold) - 1 else Place.MIDDLE)
    return UnboldedPart(
        characters=unbolded,
        of=len(bold),
        stretches=stretches,
        places=tuple(place for place in Place if place in places),
        holds_letters=letters,
        holds_digits=digits,
    )


@dataclass(frozen=True, slots=True)
class BoldLine:
    """A line the parser read as body or as nothing that Word shows as a bold heading would look."""

    position: int
    """The line's position among the file's paragraphs."""
    above_a_cite: bool
    """Directly above a cite, blank lines and page furniture stepped over."""
    above_a_cite_opening_a_card_with_no_tag: bool
    bold_as_the_reader_sees_it: bool
    behind_an_unmapped_style: bool


def rule_family(rule_id: str) -> str:
    """The rule that decided, without what follows its first colon, which may name a file's style."""
    return rule_id.split(":", 1)[0]


def _says_nothing(section: FileSection) -> bool:
    """A blank line, a table cell or a text box: stepped over, as the assembly steps over them."""
    return not section.text.strip() or section.in_table or section.match.rule_id.startswith(_FURNITURE)


def _boldness(description: ParagraphDescription) -> Boldness:
    visible = description.visible_runs
    bold = [run.bold if run.bold is not None else bool(description.paragraph_bold) for run in visible]
    if bold and all(bold):
        return Boldness.ALL
    return Boldness.SOME if any(bold) else Boldness.NONE


def _size(description: ParagraphDescription, profile: StyleProfile) -> LineSize:
    size = description.effective_half_points
    if size is None:
        return LineSize.NOT_STATED
    if size < profile.shrink.body_half_points:
        return LineSize.BELOW_READING_SIZE
    return LineSize.READING_SIZE_OR_LARGER


def _paragraph_style_unit(description: ParagraphDescription, profile: StyleProfile) -> StructuralUnit | None:
    match = profile.resolve_paragraph_style(
        description.style_id, description.style_name, description.style_based_on
    )
    return None if match is None else match.unit


def _in_a_tag_style(description: ParagraphDescription, profile: StyleProfile) -> bool:
    if _paragraph_style_unit(description, profile) is StructuralUnit.TAG:
        return True
    visible = description.visible_runs
    if not visible:
        return False
    for run in visible:
        match = profile.resolve_character_style(
            run.character_style_id, run.character_style_name, run.character_style_based_on
        )
        if match is None or match.emphasis is not RunEmphasis.HEADING:
            return False
    return True


def _in_an_evidence_style(description: ParagraphDescription, profile: StyleProfile) -> bool:
    for run in description.visible_runs:
        match = profile.resolve_character_style(
            run.character_style_id, run.character_style_name, run.character_style_based_on
        )
        if match is not None and match.emphasis in (RunEmphasis.UNDERLINE, RunEmphasis.EMPHASIS):
            return True
    return False


def _describe_line(
    read: ParagraphDescription,
    shown: ParagraphDescription,
    line: FileSection,
    profile: StyleProfile,
    *,
    cite_rule: str,
    cite_opens_a_card_with_no_tag: bool,
    ends_the_card_above: bool,
    blank_lines_between: bool,
) -> LineAboveACite:
    text = line.text.strip()
    source = first_name_and_year(text, profile)
    return LineAboveACite(
        cite_rule,
        cite_opens_a_card_with_no_tag,
        line_unit=line.unit,
        line_rule=rule_family(line.match.rule_id),
        line_read_by_a_heuristic=line.match.match_source is StyleMatchSource.HEURISTIC
        and not line.match.rule_id.startswith("assembly-"),
        line_behind_an_unmapped_style=_paragraph_style_unit(read, profile) is StructuralUnit.OTHER,
        boldness=_boldness(read),
        boldness_as_word_shows_it=_boldness(shown),
        in_a_tag_style=_in_a_tag_style(read, profile),
        size=_size(read, profile),
        size_as_word_shows_it=_size(shown, profile),
        underlined=read.has_underlined_run,
        highlighted=read.has_highlighted_run,
        in_an_evidence_style=_in_an_evidence_style(read, profile),
        no_longer_than_a_heading=len(text) <= MAXIMUM_HEADING_CHARACTERS,
        names_a_source_at_its_head=source is not None
        and source.start() <= NAME_AND_YEAR_AT_THE_HEAD_CHARACTERS,
        ends_the_card_above=ends_the_card_above,
        blank_lines_between=blank_lines_between,
    )


def line_above(sections: Sequence[FileSection], position: int) -> int | None:
    """The position of the paragraph above `position` that says something, or None at the top.

    Blank lines and page furniture are stepped over, as the assembly steps over them.
    """
    above = position - 1
    while above >= 0 and _says_nothing(sections[above]):
        above -= 1
    return above if above >= 0 else None


def _tagless_starts(cards: Iterable[ParsedCard]) -> frozenset[int]:
    return frozenset(card.provenance.first_element_index for card in cards if not (card.tag or "").strip())


def lines_above_cites(
    descriptions: Sequence[ParagraphDescription],
    sections: Sequence[FileSection],
    cards: Sequence[ParsedCard],
    profile: StyleProfile,
    *,
    shown: Sequence[ParagraphDescription] | None = None,
    cite_rules: frozenset[str] | None = BRACKETED_CITE_RULES,
) -> list[tuple[int, LineAboveACite]]:
    """The line above each cite of one file whose rule family is in `cite_rules` (any, when None).

    `descriptions` and `sections` are the file's paragraphs as read and as the parser decided them,
    aligned; `shown` is the same paragraphs as Word shows them, the reader's own when not given. A
    cite whose paragraph above is another line of the cite is not described: the line above a cite
    is the one above its first line. Each is returned with the cite's position.
    """
    shown = descriptions if shown is None else shown
    tagless_starts = _tagless_starts(cards)
    card_ends = {card.provenance.last_element_index for card in cards}
    found: list[tuple[int, LineAboveACite]] = []
    for position, section in enumerate(sections):
        if section.unit is not StructuralUnit.CITE:
            continue
        cite_rule = rule_family(section.match.rule_id)
        if cite_rules is not None and cite_rule not in cite_rules:
            continue
        above = line_above(sections, position)
        if above is not None and sections[above].unit is StructuralUnit.CITE:
            continue
        opens_tagless = section.element_index in tagless_starts
        if above is None:
            found.append((position, LineAboveACite(cite_rule, opens_tagless, line_unit=None)))
            continue
        line = sections[above]
        described = _describe_line(
            descriptions[above],
            shown[above],
            line,
            profile,
            cite_rule=cite_rule,
            cite_opens_a_card_with_no_tag=opens_tagless,
            ends_the_card_above=line.element_index in card_ends,
            blank_lines_between=above < position - 1,
        )
        found.append((position, described))
    return found


def bold_lines_read_as_body_or_nothing(
    descriptions: Sequence[ParagraphDescription],
    shown: Sequence[ParagraphDescription],
    sections: Sequence[FileSection],
    cards: Sequence[ParsedCard],
    profile: StyleProfile,
) -> list[BoldLine]:
    """Every line of one file read as body or as nothing that Word shows as a bold heading would look.

    That is: bold throughout, at reading size or larger, no longer than a heading, with no outline
    level, as Word shows it (`shown`). These are the lines the classifier's bold-heading rule would
    read as headings if it were given what Word shows; most of them it would read as tags.
    """
    tagless_starts = _tagless_starts(cards)
    lines_above: dict[int, bool] = {}
    for position, section in enumerate(sections):
        if section.unit is StructuralUnit.CITE:
            above = line_above(sections, position)
            if above is not None:
                lines_above[above] = lines_above.get(above, False) or section.element_index in tagless_starts
    found: list[BoldLine] = []
    for position, section in enumerate(sections):
        if section.unit not in (StructuralUnit.EVIDENCE, StructuralUnit.OTHER) or _says_nothing(section):
            continue
        description = shown[position]
        if (
            description.outline_level is not None
            or len(section.text.strip()) > MAXIMUM_HEADING_CHARACTERS
            or _boldness(description) is not Boldness.ALL
            or _size(description, profile) is not LineSize.READING_SIZE_OR_LARGER
        ):
            continue
        found.append(
            BoldLine(
                position=position,
                above_a_cite=position in lines_above,
                above_a_cite_opening_a_card_with_no_tag=lines_above.get(position, False),
                bold_as_the_reader_sees_it=_boldness(descriptions[position]) is Boldness.ALL,
                behind_an_unmapped_style=_paragraph_style_unit(descriptions[position], profile)
                is StructuralUnit.OTHER,
            )
        )
    return found


def _split(values: Iterable[object]) -> dict[str, int]:
    return dict(sorted(Counter(str(value) for value in values).items()))


def tally_lines_above_cites(lines: Iterable[LineAboveACite]) -> dict[str, object]:
    """The counts the report gives: every line above a cite, and (7)'s shape split every way."""
    lines = list(lines)
    shape = [line for line in lines if line.is_the_shape]
    return {
        "cites": len(lines),
        "cites_opening_a_card_with_no_tag": sum(line.cite_opens_a_card_with_no_tag for line in lines),
        "line_above_read_as": _split(
            "nothing above" if line.line_unit is None else line.line_unit.value for line in lines
        ),
        "line_above_read_as_body_or_nothing": sum(line.read_as_body_or_nothing for line in lines),
        "the_shape": {
            "lines": len(shape),
            "cite_opens_a_card_with_no_tag": _split(line.cite_opens_a_card_with_no_tag for line in shape),
            "read_as": _split(line.line_unit.value for line in shape if line.line_unit is not None),
            "by_line_rule": _split(line.line_rule for line in shape),
            "behind_a_style_that_maps_to_no_unit": _split(
                line.line_behind_an_unmapped_style for line in shape
            ),
            "bold_as_the_reader_sees_it": _split(line.boldness.value for line in shape),
            "bold_as_word_shows_it": _split(line.boldness_as_word_shows_it.value for line in shape),
            "in_a_tag_style": _split(line.in_a_tag_style for line in shape),
            "size_as_the_reader_sees_it": _split(line.size.value for line in shape),
            "size_as_word_shows_it": _split(line.size_as_word_shows_it.value for line in shape),
            "underlined": _split(line.underlined for line in shape),
            "highlighted": _split(line.highlighted for line in shape),
            "no_longer_than_a_heading": _split(line.no_longer_than_a_heading for line in shape),
            "names_a_source_at_its_head": _split(line.names_a_source_at_its_head for line in shape),
            "ends_the_card_above": _split(line.ends_the_card_above for line in shape),
            "blank_lines_between": _split(line.blank_lines_between for line in shape),
        },
        "the_proposed_rule_takes": sum(line.the_proposed_rule_takes for line in lines),
        "the_proposed_rule_takes_lines_bold_only_by_inheritance": sum(
            line.the_proposed_rule_takes and line.boldness is not Boldness.ALL for line in lines
        ),
        "read_as_body_or_nothing_and_not_the_shape_by_bold_as_word_shows_it": _split(
            line.boldness_as_word_shows_it.value
            for line in lines
            if line.read_as_body_or_nothing and not line.is_the_shape
        ),
    }


def tally_bold_lines(lines: Iterable[BoldLine]) -> dict[str, int]:
    """How many bold lines read as body or as nothing, and where they stand."""
    lines = list(lines)
    return {
        "lines": len(lines),
        "directly_above_a_cite": sum(line.above_a_cite for line in lines),
        "directly_above_a_cite_opening_a_card_with_no_tag": sum(
            line.above_a_cite_opening_a_card_with_no_tag for line in lines
        ),
        "bold_as_the_reader_sees_it": sum(line.bold_as_the_reader_sees_it for line in lines),
        "behind_a_style_that_maps_to_no_unit": sum(line.behind_an_unmapped_style for line in lines),
    }
