"""Where the labelled evaluation's missed cites, tags and highlights go, in counts (`v1-e31-t31`).

The first labelled baseline (2026-10-20) missed v1-e31-t05's targets for cites above all: CITE
recall 0.623 over the full tier. Before any rule is proposed, this module says, for every labelled
row whose gold unit is `CITE` or `TAG` and that the parser read as something else, what it was read
as, by which rule, and what the row looks like, as counts. For highlight it counts, character by
character over the sampled span rows, the highlight the parser missed and the highlight it added,
by what the run under each character carries.

Beside the misses it counts **candidate shapes**: the paragraphs a proposed rule would take, as
the parser can see them, over every labelled row whatever its gold unit. A shape's `CITE` count is
what the rule could add to recall; its other counts are what it would cost in precision. Nothing
here changes a reading; the PM rules on the counts first, as `v1-e31-t19`, `t22` and `t24` did.

Counts only leave this module. No text, no file name, and no style name: a rule id is reduced to
its family (`line_above_a_cite.rule_family`), and a highlight colour is named only when it is one
the profile lists.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any, Final

from tests.evals.parser.labels_schema import LabelFile, ManifestEntry
from tests.evals.parser.metrics import (
    FileScore,
    Prediction,
    group_scores,
    prediction_from_document,
    score_file,
)

from debate_core.domain.debate_files import FileSection, ParsedDocument
from debate_core.domain.style_profile import RunEmphasis, StructuralUnit, StyleProfile
from debate_core.evidence.line_above_a_cite import line_above, rule_family
from debate_core.evidence.style_classifier import (
    MAXIMUM_CITE_LINE_CHARACTERS,
    NAME_AND_YEAR_AT_THE_HEAD_CHARACTERS,
    ParagraphDescription,
    first_name_and_year,
)
from debate_core.integrations.docx_parser import DebateDocxParser
from debate_core.integrations.docx_parser.runs import as_word_shows_it

__all__ = [
    "CANDIDATE_SHAPES",
    "CardOutcome",
    "FileCounts",
    "HighlightCharacter",
    "LengthBand",
    "MissedRow",
    "NameAndYear",
    "ReadingParser",
    "ShapeRow",
    "count_file",
    "tally",
]

#: The gold units whose misses are counted, row by row.
COUNTED_UNITS: Final = (StructuralUnit.CITE, StructuralUnit.TAG)

#: A link, as a cite holds one. Only its presence is counted.
_LINK: Final = re.compile(r"https?://|www\.", re.IGNORECASE)

#: A year as a cite writes it: four digits from 1900, or an apostrophe and two digits.
_YEAR: Final = re.compile(r"\b(?:19|20)\d{2}\b|['’‘]\d{2}\b")


class LengthBand(StrEnum):
    """A row's length, against the classifier's cite-line bound."""

    UP_TO_100 = "up to 100"
    UP_TO_A_CITE_LINE = f"101 to {MAXIMUM_CITE_LINE_CHARACTERS}"
    LONGER = f"over {MAXIMUM_CITE_LINE_CHARACTERS}"


class NameAndYear(StrEnum):
    """Where the profile's name-and-year pattern first matches the row."""

    AT_THE_HEAD = "at the head"
    """Within the classifier's head bound, where a cite's author stands."""
    FURTHER_IN = "further in"
    NONE = "none"


class CardOutcome(StrEnum):
    """What the parser did with the labelled card a missed cite row belongs to."""

    CITE_READ_IN_PART = "another row of the card's cite was read as a cite"
    NO_CITE_READ = "no row of the card's cite was read as a cite"
    NOT_IN_A_CARD = "the row is in no labelled card"


class MarkUp(StrEnum):
    HIGHLIGHTED = "highlighted"
    UNDERLINED = "underlined, not highlighted"
    NONE = "neither"


@dataclass(frozen=True, slots=True)
class MissedRow:
    """One labelled CITE or TAG row the parser read otherwise, described without its text."""

    labelled: StructuralUnit
    read_as: StructuralUnit
    rule: str
    category: str
    template_family: str
    debate_format: str
    above_labelled: StructuralUnit | None
    """The gold unit of the paragraph above that says something; None when it is unlabelled or absent."""
    above_read_as: StructuralUnit | None
    below_labelled: StructuralUnit | None
    below_read_as: StructuralUnit | None
    length: LengthBand
    name_and_year: NameAndYear
    holds_a_link: bool
    holds_a_year: bool
    mark_up: MarkUp
    opens_in_bold: bool
    bold_as_word_shows_it: bool
    card_outcome: CardOutcome
    taken_by: tuple[str, ...] = ()
    """The candidate shapes that take this row, by name."""


@dataclass(frozen=True, slots=True)
class ShapeRow:
    """A labelled row a candidate shape takes, with its gold unit."""

    shape: str
    labelled: StructuralUnit
    category: str
    template_family: str
    debate_format: str


@dataclass(frozen=True, slots=True)
class HighlightCharacter:
    """Highlight the parser missed or added on one character of a sampled span row."""

    missed: bool
    """True for a labelled highlight the parser did not read; False for one it added."""
    colour: str
    """The run's highlight colour, if the profile lists it; else a description."""
    read_as: StructuralUnit
    category: str
    template_family: str
    debate_format: str
    file: str
    """The file's digest prefix, as `MANIFEST.md` names it."""


class ReadingParser(DebateDocxParser):
    """The parser, keeping each file's paragraphs as it read them and as Word shows them."""

    def __init__(self) -> None:
        super().__init__()
        self.descriptions: list[ParagraphDescription] = []
        self.shown: list[ParagraphDescription] = []
        self.run_offsets: list[tuple[tuple[int, int], ...]] = []

    def _read_sections(self, package: Any) -> Any:  # pyright: ignore[reportIncompatibleMethodOverride]
        sections = super()._read_sections(package)  # pyright: ignore[reportPrivateUsage]
        self.descriptions = [section.read.description for section in sections]
        self.shown = [as_word_shows_it(description, package) for description in self.descriptions]
        self.run_offsets = [tuple(section.read.run_offsets) for section in sections]
        return sections


# --------------------------------------------------------------------------------------------
# Describing one row
# --------------------------------------------------------------------------------------------


def _length(text: str) -> LengthBand:
    if len(text) <= 100:
        return LengthBand.UP_TO_100
    return LengthBand.UP_TO_A_CITE_LINE if len(text) <= MAXIMUM_CITE_LINE_CHARACTERS else LengthBand.LONGER


def _name_and_year(text: str, profile: StyleProfile) -> NameAndYear:
    found = first_name_and_year(text, profile)
    if found is None:
        return NameAndYear.NONE
    return (
        NameAndYear.AT_THE_HEAD
        if found.start() <= NAME_AND_YEAR_AT_THE_HEAD_CHARACTERS
        else NameAndYear.FURTHER_IN
    )


def _mark_up(description: ParagraphDescription) -> MarkUp:
    if description.has_highlighted_run:
        return MarkUp.HIGHLIGHTED
    return MarkUp.UNDERLINED if description.has_underlined_run else MarkUp.NONE


def _opens_in_bold(description: ParagraphDescription) -> bool:
    visible = description.visible_runs
    if not visible:
        return False
    first = visible[0]
    return first.bold if first.bold is not None else bool(description.paragraph_bold)


def _says_nothing(section: FileSection) -> bool:
    """A blank line, a table cell or a text box, stepped over as `line_above` steps over them."""
    return (
        not section.text.strip()
        or section.in_table
        or section.match.rule_id.startswith(("assembly-table-cell", "assembly-text-box"))
    )


def _line_below(sections: Sequence[FileSection], position: int) -> int | None:
    below = position + 1
    while below < len(sections) and _says_nothing(sections[below]):
        below += 1
    return below if below < len(sections) else None


def _units_at(
    position: int | None, sections: Sequence[FileSection], gold: Mapping[int, StructuralUnit]
) -> tuple[StructuralUnit | None, StructuralUnit | None]:
    if position is None:
        return None, None
    return gold.get(position), sections[position].unit


# --------------------------------------------------------------------------------------------
# Candidate shapes: what a proposed rule would take, as the parser sees the file
# --------------------------------------------------------------------------------------------


#: The assembly's demotion of a tag that has no cite or body under it. A tag above a cite the
#: parser missed can be demoted by it, and a rule that reads the cite gives the tag back.
DEMOTED_TAG_RULE: Final = "assembly-tag-without-cite-or-evidence"


def _read_as_nothing(section: FileSection) -> bool:
    return section.unit is StructuralUnit.OTHER and not _says_nothing(section)


def _is_a_tag(section: FileSection) -> bool:
    """Read as a tag, or as an analytic only because nothing under it was read as a cite or body."""
    return section.unit is StructuralUnit.TAG or rule_family(section.match.rule_id) == DEMOTED_TAG_RULE


def _names_a_source(text: str) -> bool:
    return bool(_LINK.search(text) or _YEAR.search(text))


def _above(sections: Sequence[FileSection], position: int) -> FileSection | None:
    above = line_above(sections, position)
    return None if above is None else sections[above]


def _below(sections: Sequence[FileSection], position: int) -> FileSection | None:
    below = _line_below(sections, position)
    return None if below is None else sections[below]


def _over_a_body(sections: Sequence[FileSection], position: int) -> bool:
    below = _below(sections, position)
    return below is not None and below.unit is StructuralUnit.EVIDENCE


def _second_line_of_a_cite(
    sections: Sequence[FileSection], position: int, _description: ParagraphDescription, _profile: StyleProfile
) -> bool:
    """Read as nothing, directly under a line read as a cite, directly over a line read as body."""
    above = _above(sections, position)
    return (
        _read_as_nothing(sections[position])
        and above is not None
        and above.unit is StructuralUnit.CITE
        and _over_a_body(sections, position)
    )


def _second_line_of_a_cite_naming_a_source(
    sections: Sequence[FileSection], position: int, description: ParagraphDescription, profile: StyleProfile
) -> bool:
    """The second line of a cite, holding a link or a year."""
    return _second_line_of_a_cite(sections, position, description, profile) and _names_a_source(
        sections[position].text
    )


def _between_a_cite_and_a_body(
    sections: Sequence[FileSection], position: int, _description: ParagraphDescription, _profile: StyleProfile
) -> bool:
    """Read as nothing, with a link or a year, in a run of lines read as nothing between a cite and a body."""
    if not _read_as_nothing(sections[position]) or not _names_a_source(sections[position].text):
        return False
    above = line_above(sections, position)
    while above is not None and _read_as_nothing(sections[above]):
        above = line_above(sections, above)
    below = _line_below(sections, position)
    while below is not None and _read_as_nothing(sections[below]):
        below = _line_below(sections, below)
    return (
        above is not None
        and sections[above].unit is StructuralUnit.CITE
        and below is not None
        and sections[below].unit is StructuralUnit.EVIDENCE
    )


def _unread_cite_under_a_tag(
    sections: Sequence[FileSection], position: int, _description: ParagraphDescription, _profile: StyleProfile
) -> bool:
    """Read as nothing, directly under a tag, directly over a body, holding a link or a year."""
    above = _above(sections, position)
    return (
        _read_as_nothing(sections[position])
        and above is not None
        and _is_a_tag(above)
        and _over_a_body(sections, position)
        and _names_a_source(sections[position].text)
    )


def _marked_up_cite_under_a_tag(
    sections: Sequence[FileSection], position: int, description: ParagraphDescription, _profile: StyleProfile
) -> bool:
    """Read as body, no longer than a cite line, under a tag, over a body, with a link, not highlighted."""
    section = sections[position]
    above = _above(sections, position)
    return (
        section.unit is StructuralUnit.EVIDENCE
        and len(section.text.strip()) <= MAXIMUM_CITE_LINE_CHARACTERS
        and above is not None
        and _is_a_tag(above)
        and _over_a_body(sections, position)
        and bool(_LINK.search(section.text))
        and not description.has_highlighted_run
    )


def _cite_read_as_a_second_tag(
    sections: Sequence[FileSection], position: int, _description: ParagraphDescription, profile: StyleProfile
) -> bool:
    """Read as a tag, directly under a tag, over a body, with a name and year at its head."""
    section = sections[position]
    above = _above(sections, position)
    return (
        section.unit is StructuralUnit.TAG
        and above is not None
        and _is_a_tag(above)
        and _over_a_body(sections, position)
        and _name_and_year(section.text.strip(), profile) is NameAndYear.AT_THE_HEAD
    )


SECOND_LINE: Final = "second line of a cite, read as nothing, with a link or year"
LONGER_CITE: Final = "every line between a cite and a body, read as nothing, with a link or year"
UNDER_A_TAG: Final = "line under a tag, read as nothing, with a link or year, over a body"
BODY_UNDER_A_TAG: Final = "line under a tag, read as body, with a link, not highlighted"
SECOND_TAG: Final = "line read as a tag under a tag, name and year at its head, over a body"

#: Each shape a rule could be written for, by name, with the test that says a paragraph is of it.
#: The first, unguarded, is measured to show what its guard is for. `LONGER_CITE` takes
#: `SECOND_LINE`'s lines and the further lines of cites written over three or more.
CANDIDATE_SHAPES: Final = {
    "second line of a cite, read as nothing": _second_line_of_a_cite,
    SECOND_LINE: _second_line_of_a_cite_naming_a_source,
    LONGER_CITE: _between_a_cite_and_a_body,
    UNDER_A_TAG: _unread_cite_under_a_tag,
    BODY_UNDER_A_TAG: _marked_up_cite_under_a_tag,
    SECOND_TAG: _cite_read_as_a_second_tag,
}

#: The shapes proposed together, and the same with the longer cite in place of the second line.
PROPOSED_SHAPES: Final = (SECOND_LINE, UNDER_A_TAG, BODY_UNDER_A_TAG, SECOND_TAG)
PROPOSED_WITH_THE_LONGER_CITE: Final = (LONGER_CITE, UNDER_A_TAG, BODY_UNDER_A_TAG, SECOND_TAG)


# --------------------------------------------------------------------------------------------
# One file
# --------------------------------------------------------------------------------------------


def _colour(run_highlight: str | None, profile: StyleProfile) -> str:
    if not run_highlight:
        return "no highlight on the run"
    colour = profile.highlight_color(run_highlight)
    if colour is None:
        return "a colour the profile does not list"
    return f"{colour.value} ({'a reading colour' if colour.reading_color else 'not a reading colour'})"


def _run_at(offsets: Sequence[tuple[int, int]], character: int) -> int | None:
    return next((index for index, (start, end) in enumerate(offsets) if start <= character < end), None)


WHITE_HIGHLIGHT_VARIANT: Final = "white highlight not read as highlight"
PROPOSED_VARIANT: Final = "the four proposed cite shapes together"
LONGER_CITE_VARIANT: Final = "the four, with the longer cite in place of the second line"


@dataclass(frozen=True, slots=True)
class FileCounts:
    """One parsed, labelled file, in counts."""

    missed: tuple[MissedRow, ...]
    shapes: tuple[ShapeRow, ...]
    highlight: tuple[HighlightCharacter, ...]
    outcomes: Counter[tuple[str, ...]]
    """Each labelled CITE and TAG row as `(unit, "read right" | "missed")`, and each labelled card
    holding a cite row as `("cards with a labelled cite", what-if, "all" | "part" | "none")`: how
    much of its cite was read, as read and under each what-if."""
    what_if: Mapping[str, FileScore]
    """The harness's score of the file as read (`"as read"`) and with each variant applied."""


def _with_cites(prediction: Prediction, sections: Sequence[FileSection], taken: Iterable[int]) -> Prediction:
    """The prediction with `taken` read as cites, and each tag the assembly demoted above one given back.

    Card boundaries are left as the parser drew them: what-if scores are unit and span scores only.
    """
    units = dict(prediction.units)
    for position in taken:
        units[position] = StructuralUnit.CITE
        above = line_above(sections, position)
        while above is not None and units[above] is StructuralUnit.CITE:
            above = line_above(sections, above)
        if above is not None and rule_family(sections[above].match.rule_id) == DEMOTED_TAG_RULE:
            units[above] = StructuralUnit.TAG
    return replace(prediction, units=units)


def _without_white_highlight(prediction: Prediction, sections: Sequence[FileSection]) -> Prediction:
    highlight = {
        section.element_index: [
            (span.start_offset, span.end_offset)
            for span in section.formatting_spans
            if span.emphasis is RunEmphasis.HIGHLIGHT and span.highlight_color != "white"
        ]
        for section in sections
    }
    return replace(prediction, highlight=highlight)


def _cite_read(
    card_rows: Mapping[int, Sequence[int]],
    gold: Mapping[int, StructuralUnit],
    units: Mapping[int, StructuralUnit],
) -> Counter[str]:
    """How much of each labelled card's cite was read: `all`, `part` or `none` of its cite rows."""
    counts: Counter[str] = Counter()
    for rows in card_rows.values():
        cites = [row for row in rows if gold[row] is StructuralUnit.CITE]
        if not cites:
            continue
        read = sum(units.get(row) is StructuralUnit.CITE for row in cites)
        counts["all" if read == len(cites) else ("none" if read == 0 else "part")] += 1
    return counts


def count_file(
    entry: ManifestEntry,
    labels: LabelFile,
    document: ParsedDocument,
    parser: ReadingParser,
) -> FileCounts:
    """Count one file. `parser` must be the one that parsed `document`: its descriptions are this file's."""
    sections = document.sections
    if [section.element_index for section in sections] != list(range(len(sections))):
        raise ValueError("the parsed sections are not indexed by their position")
    profile = parser.profile
    group = (entry.category.value, entry.template_family.value, entry.debate_format.value)
    gold = {paragraph.index: paragraph.unit for paragraph in labels.paragraphs}
    card_rows: dict[int, list[int]] = {}
    for paragraph in labels.paragraphs:
        if paragraph.card is not None:
            card_rows.setdefault(paragraph.card, []).append(paragraph.index)

    taken = {
        name: [
            position
            for position in range(len(sections))
            if takes(sections, position, parser.descriptions[position], profile)
        ]
        for name, takes in CANDIDATE_SHAPES.items()
    }
    taken_at: dict[int, list[str]] = {}
    for name, positions in taken.items():
        for position in positions:
            taken_at.setdefault(position, []).append(name)

    outcomes: Counter[tuple[str, ...]] = Counter()
    missed: list[MissedRow] = []
    for paragraph in labels.paragraphs:
        if paragraph.unit not in COUNTED_UNITS:
            continue
        section = sections[paragraph.index]
        if section.unit is paragraph.unit:
            outcomes[(paragraph.unit.value, "read right")] += 1
            continue
        outcomes[(paragraph.unit.value, "missed")] += 1
        description = parser.descriptions[paragraph.index]
        text = section.text.strip()
        above_labelled, above_read = _units_at(line_above(sections, paragraph.index), sections, gold)
        below_labelled, below_read = _units_at(_line_below(sections, paragraph.index), sections, gold)
        if paragraph.card is None:
            outcome = CardOutcome.NOT_IN_A_CARD
        elif any(
            gold[row] is StructuralUnit.CITE and sections[row].unit is StructuralUnit.CITE
            for row in card_rows[paragraph.card]
        ):
            outcome = CardOutcome.CITE_READ_IN_PART
        else:
            outcome = CardOutcome.NO_CITE_READ
        missed.append(
            MissedRow(
                labelled=paragraph.unit,
                read_as=section.unit,
                rule=rule_family(section.match.rule_id),
                category=group[0],
                template_family=group[1],
                debate_format=group[2],
                above_labelled=above_labelled,
                above_read_as=above_read,
                below_labelled=below_labelled,
                below_read_as=below_read,
                length=_length(text),
                name_and_year=_name_and_year(text, profile),
                holds_a_link=bool(_LINK.search(text)),
                holds_a_year=bool(_YEAR.search(text)),
                mark_up=_mark_up(description),
                opens_in_bold=_opens_in_bold(description),
                bold_as_word_shows_it=parser.shown[paragraph.index].effective_bold,
                card_outcome=outcome,
                taken_by=tuple(taken_at.get(paragraph.index, ())),
            )
        )

    shapes = tuple(
        ShapeRow(name, gold[position], *group)
        for name, positions in taken.items()
        for position in positions
        if position in gold
    )

    highlight: list[HighlightCharacter] = []
    for span in labels.spans:
        section = sections[span.index]
        read = {
            character
            for formatting in section.formatting_spans
            if formatting.emphasis is RunEmphasis.HIGHLIGHT
            for character in range(formatting.start_offset, formatting.end_offset)
        }
        labelled = {character for start, end in span.highlight for character in range(start, end)}
        runs = parser.descriptions[span.index].runs
        offsets = parser.run_offsets[span.index]
        for is_missed, characters in ((True, labelled - read), (False, read - labelled)):
            for character in sorted(characters):
                run = _run_at(offsets, character)
                colour = _colour(None if run is None else runs[run].highlight, profile)
                highlight.append(
                    HighlightCharacter(is_missed, colour, section.unit, *group, file=entry.digest[:16])
                )

    prediction = prediction_from_document(document)
    variants = {
        **{name: _with_cites(prediction, sections, positions) for name, positions in taken.items()},
        PROPOSED_VARIANT: _with_cites(
            prediction, sections, sorted({p for name in PROPOSED_SHAPES for p in taken[name]})
        ),
        LONGER_CITE_VARIANT: _with_cites(
            prediction, sections, sorted({p for name in PROPOSED_WITH_THE_LONGER_CITE for p in taken[name]})
        ),
        WHITE_HIGHLIGHT_VARIANT: _without_white_highlight(prediction, sections),
    }
    what_if = {"as read": score_file(labels, prediction)}
    for name, variant in (("as read", prediction), *variants.items()):
        what_if[name] = score_file(labels, variant)
        for how_much, count in _cite_read(card_rows, gold, variant.units).items():
            outcomes[("cards with a labelled cite", name, how_much)] += count
    return FileCounts(tuple(missed), shapes, tuple(highlight), outcomes, what_if)


# --------------------------------------------------------------------------------------------
# Tallies
# --------------------------------------------------------------------------------------------


def _key(*parts: object) -> str:
    return " | ".join("-" if part is None else str(part) for part in parts)


def _counts(values: Iterable[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items(), key=lambda item: (-item[1], item[0])))


#: The groups the what-if scores are reported for: the two the targets are stated on, and overall.
WHAT_IF_GROUPS: Final = ("overall", "template:verbatim", "template:non-verbatim")

#: The scores each what-if reports: the units a cite rule can move, and spans.
_WHAT_IF_UNITS: Final = (
    StructuralUnit.CITE,
    StructuralUnit.TAG,
    StructuralUnit.EVIDENCE,
    StructuralUnit.ANALYTIC,
)


def _what_if_scores(scored: Sequence[tuple[ManifestEntry, FileScore]]) -> dict[str, Any]:
    groups = group_scores(scored)
    result: dict[str, Any] = {}
    for name in WHAT_IF_GROUPS:
        group = groups.get(name)
        if group is None:
            continue
        score = group.score
        result[name] = {
            **{
                unit.value: {
                    key: value
                    for key, value in score.units[unit].as_json().items()
                    if key in ("tp", "fp", "fn", "precision", "recall", "f1")
                }
                for unit in _WHAT_IF_UNITS
            },
            "highlight_f1": score.spans["highlight"].as_json()["f1"],
            "span_f1": score.as_json()["spans"]["combined_f1"],
        }
    return result


def tally(counted: Sequence[tuple[ManifestEntry, FileCounts]]) -> dict[str, Any]:
    """Counts only, keyed by plain descriptions, for the report and the PM."""
    missed = [row for _, counts in counted for row in counts.missed]
    shapes = [row for _, counts in counted for row in counts.shapes]
    highlight = [character for _, counts in counted for character in counts.highlight]
    outcomes: Counter[tuple[str, ...]] = Counter()
    for _, counts in counted:
        outcomes += counts.outcomes
    variants = list(counted[0][1].what_if) if counted else []

    result: dict[str, Any] = {
        "cards_with_a_labelled_cite": {
            variant: {
                how_much: outcomes[("cards with a labelled cite", variant, how_much)]
                for how_much in ("all", "part", "none")
            }
            for variant in variants
        }
    }
    for unit in COUNTED_UNITS:
        rows = [row for row in missed if row.labelled is unit]
        right = outcomes[(unit.value, "read right")]
        entry: dict[str, Any] = {
            "labelled": right + len(rows),
            "read_right": right,
            "missed": len(rows),
            "read_as": _counts(row.read_as.value for row in rows),
            "read_as_by_rule": _counts(_key(row.read_as.value, row.rule) for row in rows),
            "by_category": _counts(_key(row.category, row.read_as.value) for row in rows),
            "by_template_family": _counts(_key(row.template_family, row.read_as.value) for row in rows),
            "by_format": _counts(_key(row.debate_format, row.read_as.value) for row in rows),
            "above_labelled_and_read_as": _counts(
                _key(
                    row.above_labelled and row.above_labelled.value,
                    row.above_read_as and row.above_read_as.value,
                )
                for row in rows
            ),
            "below_labelled_and_read_as": _counts(
                _key(
                    row.below_labelled and row.below_labelled.value,
                    row.below_read_as and row.below_read_as.value,
                )
                for row in rows
            ),
            "length": _counts(row.length.value for row in rows),
            "name_and_year": _counts(row.name_and_year.value for row in rows),
            "holds_a_link": _counts(str(row.holds_a_link) for row in rows),
            "holds_a_year": _counts(str(row.holds_a_year) for row in rows),
            "mark_up": _counts(row.mark_up.value for row in rows),
            "opens_in_bold": _counts(str(row.opens_in_bold) for row in rows),
            "bold_as_word_shows_it": _counts(str(row.bold_as_word_shows_it) for row in rows),
        }
        if unit is StructuralUnit.CITE:
            entry["card_outcome"] = _counts(row.card_outcome.value for row in rows)
        left = [row for row in rows if not set(row.taken_by) & set(PROPOSED_SHAPES)]
        entry["left_by_the_proposed_shapes"] = {
            "rows": len(left),
            "read_as_and_above": _counts(
                _key(
                    row.read_as.value,
                    row.above_labelled and row.above_labelled.value,
                    row.above_read_as and row.above_read_as.value,
                )
                for row in left
            ),
            "taken_only_by": _counts(" + ".join(row.taken_by) for row in left if row.taken_by),
        }
        result[unit.value] = entry
    result["candidate_shapes"] = {
        name: {
            "labelled_as": _counts(row.labelled.value for row in shapes if row.shape == name),
            "by_template_family": _counts(
                _key(row.template_family, row.labelled.value) for row in shapes if row.shape == name
            ),
        }
        for name in CANDIDATE_SHAPES
    }
    result["highlight"] = {
        "missed_characters": _counts(
            _key(c.category, c.template_family, c.debate_format, c.file, c.colour)
            for c in highlight
            if c.missed
        ),
        "added_characters": _counts(
            _key(c.category, c.template_family, c.debate_format, c.file, c.colour)
            for c in highlight
            if not c.missed
        ),
        "added_characters_by_read_as": _counts(
            _key(c.read_as.value, c.colour) for c in highlight if not c.missed
        ),
    }
    result["what_if"] = {
        variant: _what_if_scores([(entry, counts.what_if[variant]) for entry, counts in counted])
        for variant in variants
    }
    return result
