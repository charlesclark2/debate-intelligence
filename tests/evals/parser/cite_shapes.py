"""Labelled examples of the cite shapes the first corpus parses raised (`v1-e31-t12`).

`v1-e31-t09` and the operator's sample left five questions about cites: a sentence the cite
heuristics take for one, a cite in the cite character style past the profile's bound, a card with
no cite, a bracketed cite ending in the cutter's initials, and a small-print line under a cite.
The two evaluation files a person has corrected hold none of them, so each shape is rebuilt here
as invented cards, at least ten a shape, and labelled **by hand from what each paragraph was
written to be** (working agreement 6). Nothing here is corpus text: the authors, journals, tags,
initials and addresses are made up, and the lengths and formatting are the only things taken from
the corpus, as counts (`docs/data/caselist-parse-report.md`).

Each example says how the parser read it before this task:

* `MISREAD`: wrongly, and a rule of this task reads it right. Its test failed first.
* `ALREADY_RIGHT`: rightly, before and after. These are the other side of each rule: the cite
  that must stay a cite and the body that must stay a body.
* `STILL_MISREAD`: wrongly, before and after, and left on purpose. The test expects the failure.

`build_shape_file` joins a shape's examples into one invented file with a block heading above
each, and returns the labels in the evaluation's own schema, so the harness's `score_file`
measures unit precision and recall, card boundaries and completeness on it exactly as it does on
a real file. `python -m tests.evals.parser.cite_shapes` prints that table.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from tests.evals.parser.digests import keyed_digest, text_digest
from tests.evals.parser.labels_schema import (
    CardLabel,
    FileLabelHeader,
    LabelFile,
    LabelStatus,
    ParagraphLabel,
    ReviewerRole,
)
from tests.evals.parser.synthetic import TEST_DIGEST_KEY

from debate_core.domain.debate_files import CardCompleteness
from debate_core.domain.style_profile import StructuralUnit
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml

__all__ = [
    "EXAMPLES",
    "CiteShape",
    "LabelledExample",
    "Line",
    "ReadingBefore",
    "ShapeFile",
    "build_example_file",
    "build_shape_file",
    "examples_of",
]

FULL = CardCompleteness.FULL
CITE_ONLY = CardCompleteness.CITE_ONLY

TAG = StructuralUnit.TAG
CITE = StructuralUnit.CITE
EVIDENCE = StructuralUnit.EVIDENCE
OTHER = StructuralUnit.OTHER
BLOCK = StructuralUnit.BLOCK

#: Verbatim's sizes, in half-points: a cite's name, reading size, and the small print between.
CITE_SIZE = 26
READING_SIZE = 22
SMALL_PRINT = 16


class CiteShape(StrEnum):
    """The five shapes of the task's spec, in its order."""

    A_SENTENCE_GUESSED_TO_BE_A_CITE = "a-sentence-guessed-to-be-a-cite"
    A_STYLED_CITE_PAST_THE_PROFILE_BOUND = "a-styled-cite-past-the-profile-bound"
    A_CARD_WITH_NO_CITE = "a-card-with-no-cite"
    A_BRACKETED_CITE_WITH_INITIALS = "a-bracketed-cite-with-initials"
    A_SMALL_PRINT_LINE_UNDER_A_CITE = "a-small-print-line-under-a-cite"


class ReadingBefore(StrEnum):
    """How parser `2026.10.10-docx-2` read an example, against its labels."""

    MISREAD = "MISREAD"
    ALREADY_RIGHT = "ALREADY_RIGHT"
    STILL_MISREAD = "STILL_MISREAD"


@dataclass(frozen=True)
class Line:
    """One paragraph of an example: its markup, its text, and what a person labels it."""

    markup: str
    text: str
    unit: StructuralUnit
    card: int | None = None
    """The card it belongs to, counted from 0 inside its own example."""


@dataclass(frozen=True)
class LabelledExample:
    shape: CiteShape
    name: str
    before: ReadingBefore
    lines: tuple[Line, ...]
    completeness: tuple[CardCompleteness, ...] = ()
    """One entry for each card the example holds, in order."""
    why: str = ""

    def __post_init__(self) -> None:
        cards = sorted({line.card for line in self.lines if line.card is not None})
        assert cards == list(range(len(self.completeness))), self.name


# --------------------------------------------------------------------------------------------
# Invented text
# --------------------------------------------------------------------------------------------

_SENTENCES = (
    "Grid operators in the region reported that demand from new data centres rose faster than "
    "any other load category last year.",
    "The increase outpaced every scenario the utility had planned against, and reserve margins "
    "narrowed in each of the four seasons.",
    "Planners responded by delaying the retirement of older units, which raised maintenance "
    "costs and the risk of forced outages.",
    "Independent auditors later found that the forecasting models had assumed a rate of "
    "efficiency gains that never arrived.",
    "Ratepayers bore most of the cost, because the capacity auctions cleared at prices well "
    "above the levels regulators expected.",
)

_QUALIFICATIONS = (
    "Adaeze Okonkwo is a professor of energy policy at the Invented Institute of Grid Studies",
    "a senior fellow at the Fictional Centre for Reliability Research",
    "a former director of planning at an imaginary regional transmission organisation",
    "the author of three invented monographs on reserve margins and capacity markets",
    "and a member of an advisory board that exists only in this evaluation set",
)

SOURCE = '"Reserve Margins After the Moratorium", Journal of Grid Studies, 14 March 2026'
LINK = "https://example.invalid/grid-studies/reserve-margins-after-the-moratorium"

#: A clause that holds an ellipsis and a name with a year: what the wiki cite-entry guess keys on.
ELLIPSIS_AND_YEAR = (
    "The review by Lindqvist 2019 reached the same conclusion [...] and so did the regional audit."
)


def prose(characters: int, opening: str = "") -> str:
    """Invented prose of at least `characters`, starting with `opening` and ending a sentence."""
    text = opening
    position = 0
    while len(text) < characters:
        text += ("" if not text or text.endswith(" ") else " ") + _SENTENCES[position % len(_SENTENCES)]
        position += 1
    return text


def qualifications(characters: int) -> str:
    """Invented credentials, exactly `characters` long, ending in a letter."""
    text = ""
    position = 0
    while len(text) < characters:
        text += (", " if text else "") + _QUALIFICATIONS[position % len(_QUALIFICATIONS)]
        position += 1
    text = text[:characters]
    return text[:-1] + "s" if not text[-1].isalpha() else text


def cite_text(total: int, opening: str, closing: str) -> str:
    """A cite of exactly `total` characters: `opening`, invented credentials, `closing`."""
    filler = total - len(opening) - len(closing)
    assert filler > 0, (total, opening, closing)
    return opening + qualifications(filler) + closing


# --------------------------------------------------------------------------------------------
# Paragraphs, as the files write them
# --------------------------------------------------------------------------------------------

Run = tuple[str, dict[str, Any]]


def run(text: str, **formatting: Any) -> Run:
    return (text, formatting)


def line(unit: StructuralUnit, card: int | None, *runs: Run, style: str | None = None) -> Line:
    markup = paragraph_xml("".join(run_xml(text, **formatting) for text, formatting in runs), style=style)
    return Line(markup=markup, text="".join(text for text, _ in runs), unit=unit, card=card)


def tag(text: str, card: int | None = 0, unit: StructuralUnit = TAG) -> Line:
    return line(unit, card, run(text), style="Heading4")


def block(text: str) -> Line:
    return line(BLOCK, None, run(text), style="Heading3")


def styled_cite(short: str = "Okonkwo 26", tail: str = "", card: int | None = 0) -> Line:
    """A cite as Verbatim writes one: the name and year in the cite character style."""
    tail = tail or f", Adaeze Okonkwo, invented for this evaluation, {SOURCE}."
    return line(CITE, card, run(short, character_style="Style13ptBold"), run(tail))


def bold_cite(short: str = "Okonkwo 26", tail: str = "", card: int | None = 0) -> Line:
    """A cite in a file with no cite style: a bold name at 13 pt, then the rest at reading size."""
    tail = tail or f", Adaeze Okonkwo, invented for this evaluation, {SOURCE}."
    return line(CITE, card, run(short, bold=True, half_points=CITE_SIZE), run(tail, half_points=READING_SIZE))


def marked_up(card: int | None = 0, sentence: int = 0) -> Line:
    """A body paragraph: 8 pt text with an underlined, highlighted stretch a debater reads aloud."""
    text = _SENTENCES[sentence % len(_SENTENCES)] + " " + _SENTENCES[(sentence + 1) % len(_SENTENCES)]
    opening, read_aloud, closing = text[:60], text[60:140], text[140:]
    return line(
        EVIDENCE,
        card,
        run(opening, half_points=SMALL_PRINT),
        run(read_aloud, underline="single", highlight="cyan", half_points=SMALL_PRINT),
        run(closing, half_points=SMALL_PRINT),
    )


def underlined_at_reading_size(text: str, card: int | None = 0, unit: StructuralUnit = EVIDENCE) -> Line:
    """Reading size with one underlined stretch and no highlighting."""
    first, second = len(text) // 3, 2 * len(text) // 3
    return line(
        unit,
        card,
        run(text[:first], half_points=READING_SIZE),
        run(text[first:second], underline="single", half_points=READING_SIZE),
        run(text[second:], half_points=READING_SIZE),
    )


def small_print(text: str, card: int | None = 0, unit: StructuralUnit = EVIDENCE) -> Line:
    """One run, wholly at 8 pt, no underline and no highlight."""
    return line(unit, card, run(text, half_points=SMALL_PRINT))


def plain(text: str, card: int | None = 0, unit: StructuralUnit = EVIDENCE) -> Line:
    """Reading size with no formatting at all."""
    return line(unit, card, run(text, half_points=READING_SIZE))


def bold_opening_highlighted(text: str, card: int | None = 0, unit: StructuralUnit = EVIDENCE) -> Line:
    """A body paragraph whose first words are bold and which is highlighted further in."""
    return line(
        unit,
        card,
        run(text[:40], bold=True, half_points=READING_SIZE),
        run(text[40:400], half_points=READING_SIZE),
        run(text[400:520], underline="single", highlight="cyan", half_points=READING_SIZE),
        run(text[520:], half_points=READING_SIZE),
    )


def with_a_link(unit: StructuralUnit, card: int | None, before: str, after: str, **first: Any) -> Line:
    """Text at reading size around an underlined link, as Word leaves a pasted address."""
    return line(
        unit,
        card,
        run(before, **{"half_points": READING_SIZE, **first}),
        run(LINK, underline="single", half_points=READING_SIZE),
        run(after, half_points=READING_SIZE),
    )


# --------------------------------------------------------------------------------------------
# (1) A sentence the cite heuristics take for a cite
# --------------------------------------------------------------------------------------------

_SENTENCE_SHAPE = CiteShape.A_SENTENCE_GUESSED_TO_BE_A_CITE

#: Over 2,000 characters, holding an ellipsis and a name with a year past its first 300.
LONG_BODY = prose(900) + " " + ELLIPSIS_AND_YEAR + " " + prose(1_200)
LONG_BODY_OPENING_WITH_A_NAME = "Okonkwo 26 " + LONG_BODY


def _a_sentence_guessed_to_be_a_cite() -> tuple[LabelledExample, ...]:
    shape = _SENTENCE_SHAPE
    return (
        LabelledExample(
            shape,
            "a sentence opening In and a year, in the middle of a body",
            ReadingBefore.MISREAD,
            (
                tag("Data centre demand collapses the reserve margin"),
                bold_cite(),
                marked_up(),
                underlined_at_reading_size(
                    prose(260, "In 2019, the regional operator revised its forecast. ")
                ),
                marked_up(sentence=2),
            ),
            (FULL,),
            "It ended the card and began another with no tag.",
        ),
        LabelledExample(
            shape,
            "a sentence opening Since and a year, first in the body",
            ReadingBefore.MISREAD,
            (
                tag("Load growth outpaced every planning scenario"),
                styled_cite(),
                underlined_at_reading_size(prose(240, "Since 2001, the margin has narrowed every year. ")),
                marked_up(),
            ),
            (FULL,),
            "It was added to the card's cite.",
        ),
        LabelledExample(
            shape,
            "a sentence opening By and a year, the card's only body",
            ReadingBefore.MISREAD,
            (
                tag("Retirements outrun replacement capacity"),
                bold_cite(),
                underlined_at_reading_size(prose(280, "By 2030, a third of the fleet is due to retire. ")),
            ),
            (FULL,),
            "The card was stored as a cite with no body.",
        ),
        LabelledExample(
            shape,
            "plain prose opening During and a year",
            ReadingBefore.MISREAD,
            (
                tag("Forecasts assumed gains that never arrived"),
                styled_cite(),
                marked_up(),
                plain(prose(250, "During 2020, the auditors reviewed every assumption in the model. ")),
                marked_up(sentence=3),
            ),
            (FULL,),
        ),
        LabelledExample(
            shape,
            "a sentence opening After and a year with no card open",
            ReadingBefore.MISREAD,
            (
                plain(prose(250, "After 1994, the region stopped publishing its margin. "), card=None),
                marked_up(card=None),
            ),
            (),
            "A body with no tag and no cite is a stray body. It was stored as a card.",
        ),
        LabelledExample(
            shape,
            "a sentence opening The and a year, in small print between two body paragraphs",
            ReadingBefore.ALREADY_RIGHT,
            (
                tag("Capacity auctions cleared above every estimate"),
                bold_cite(),
                marked_up(),
                small_print(prose(200, "The 2022 auction cleared at a record price. ")),
                marked_up(sentence=1),
            ),
            (FULL,),
            "v1-e31-t09 keeps it in the body from the assembly; now it is never guessed at all.",
        ),
        LabelledExample(
            shape,
            "a cite line that does not open in bold is still a cite",
            ReadingBefore.ALREADY_RIGHT,
            (
                tag("Older plants fail first"),
                plain(
                    "Lindqvist 25, Professor of Engineering at an invented university, " + SOURCE,
                    unit=CITE,
                ),
                marked_up(),
            ),
            (FULL,),
            "A name the list does not hold is an author, bold or not.",
        ),
        LabelledExample(
            shape,
            "a bold cite line whose name is a listed word is still a cite",
            ReadingBefore.ALREADY_RIGHT,
            (
                tag("Schools carry the cost of the moratorium"),
                bold_cite("The 74", ", an invented education newsroom, 3 March 2026."),
                marked_up(),
            ),
            (FULL,),
            "Bold is how a cite is written; the classifier's reading stands.",
        ),
        LabelledExample(
            shape,
            "a second card under one tag still starts at its cite",
            ReadingBefore.ALREADY_RIGHT,
            (
                tag("Moratoria shift load to older plants"),
                bold_cite(),
                marked_up(),
                bold_cite("Lindqvist 25", ", Professor, Invented University, 2 February 2025.", card=1),
                marked_up(card=1, sentence=2),
            ),
            (FULL, FULL),
        ),
        LabelledExample(
            shape,
            "a long paragraph after the card's cite, opening in bold",
            ReadingBefore.MISREAD,
            (
                tag("Reserve margins fall below safe levels"),
                styled_cite(),
                bold_opening_highlighted(LONG_BODY),
            ),
            (FULL,),
            "The wiki guess has no length bound: the whole body was stored as cite text.",
        ),
        LabelledExample(
            shape,
            "a long underlined paragraph inside a body",
            ReadingBefore.MISREAD,
            (
                tag("Outage risk rises with every deferred retirement"),
                bold_cite(),
                marked_up(),
                underlined_at_reading_size(LONG_BODY),
                marked_up(sentence=4),
            ),
            (FULL,),
            "It ended the card and began another with no tag.",
        ),
        LabelledExample(
            shape,
            "a long paragraph under a tag that has no cite, opening in bold",
            ReadingBefore.MISREAD,
            (
                tag("Ratepayers bear the cost of scarcity"),
                bold_opening_highlighted(LONG_BODY),
            ),
            (FULL,),
            "It was stored as the card's cite, and the card as cite-only.",
        ),
        LabelledExample(
            shape,
            "a cite with an ellipsis in its title is still a cite",
            ReadingBefore.ALREADY_RIGHT,
            (
                tag("Planners delay retirements they cannot afford"),
                plain(
                    'Okonkwo 26, Adaeze Okonkwo, "Reserve Margins ... After the Moratorium", '
                    "Journal of Grid Studies",
                    unit=CITE,
                ),
                marked_up(),
            ),
            (FULL,),
        ),
    )


# --------------------------------------------------------------------------------------------
# (2) A cite in the cite character style past the profile's 1,000 characters
# --------------------------------------------------------------------------------------------

_STYLED_SHAPE = CiteShape.A_STYLED_CITE_PAST_THE_PROFILE_BOUND


def long_styled_cite(
    total: int,
    card: int | None = 0,
    *,
    before_the_name: str = "",
    tail_size: int = READING_SIZE,
    closing: str = f"; {SOURCE}] KR",
) -> Line:
    """`Okonkwo 26` in the cite character style, then bracketed credentials to `total` characters."""
    short = "Okonkwo 26"
    rest = cite_text(total - len(before_the_name) - len(short), " [", closing)
    runs = [run(short, character_style="Style13ptBold"), run(rest, half_points=tail_size)]
    if before_the_name:
        runs.insert(0, run(before_the_name, half_points=tail_size))
    return line(CITE, card, *runs)


def _a_styled_cite_past_the_profile_bound() -> tuple[LabelledExample, ...]:
    shape = _STYLED_SHAPE
    with_link = cite_text(1_400 - len("Okonkwo 26") - len(LINK) - len("] KR"), " [", f"; {SOURCE}, ")
    emphasised_body = prose(1_100)
    phrase_body = prose(1_150)
    return (
        LabelledExample(
            shape,
            "a styled cite of 1,200 characters",
            ReadingBefore.MISREAD,
            (tag("Data centre demand collapses the reserve margin"), long_styled_cite(1_200), marked_up()),
            (FULL,),
            "Past 1,000 characters the style rule let go: the cite was read as nothing at all.",
        ),
        LabelledExample(
            shape,
            "a styled cite of 1,100 characters in small print",
            ReadingBefore.MISREAD,
            (
                tag("Load growth outpaced every planning scenario"),
                long_styled_cite(1_100, tail_size=SMALL_PRINT),
                marked_up(),
            ),
            (FULL,),
            "It was read as the body's first paragraph.",
        ),
        LabelledExample(
            shape,
            "a styled cite of 1,400 characters with an underlined link",
            ReadingBefore.MISREAD,
            (
                tag("Retirements outrun replacement capacity"),
                line(
                    CITE,
                    0,
                    run("Okonkwo 26", character_style="Style13ptBold"),
                    run(with_link, half_points=READING_SIZE),
                    run(LINK, underline="single", half_points=READING_SIZE),
                    run("] KR", half_points=READING_SIZE),
                ),
                marked_up(),
            ),
            (FULL,),
            "It was read as the body's first paragraph.",
        ),
        LabelledExample(
            shape,
            "a styled cite of 1,300 characters ending in a full stop",
            ReadingBefore.MISREAD,
            (
                tag("Forecasts assumed gains that never arrived"),
                long_styled_cite(1_300, closing=f"; {SOURCE}]."),
                marked_up(),
            ),
            (FULL,),
            "It was read as a paragraph of prose.",
        ),
        LabelledExample(
            shape,
            "a styled cite of 1,250 characters behind a first name",
            ReadingBefore.MISREAD,
            (
                tag("Capacity auctions cleared above every estimate"),
                long_styled_cite(1_250, before_the_name="Adaeze "),
                marked_up(),
            ),
            (FULL,),
        ),
        LabelledExample(
            shape,
            "a styled cite of 1,900 characters",
            ReadingBefore.MISREAD,
            (tag("Older plants fail first"), long_styled_cite(1_900), marked_up()),
            (FULL,),
        ),
        LabelledExample(
            shape,
            "a styled cite of 3,000 characters",
            ReadingBefore.MISREAD,
            (tag("Moratoria shift load to older plants"), long_styled_cite(3_000), marked_up()),
            (FULL,),
        ),
        LabelledExample(
            shape,
            "a styled cite of 1,200 characters with nothing under it",
            ReadingBefore.MISREAD,
            (tag("Reserve margins fall below safe levels"), long_styled_cite(1_200)),
            (CITE_ONLY,),
            "With no cite and no body the tag was demoted to an analytic: no card at all.",
        ),
        LabelledExample(
            shape,
            "a styled cite of 1,300 characters with an ellipsis in its title",
            ReadingBefore.ALREADY_RIGHT,
            (
                tag("Outage risk rises with every deferred retirement"),
                long_styled_cite(1_300, closing='; "Reserve Margins ... After the Moratorium"] KR'),
                marked_up(),
            ),
            (FULL,),
            "The wiki guess caught it for its ellipsis. It is read from its style now.",
        ),
        LabelledExample(
            shape,
            "a highlighted body paragraph that opens in the cite style",
            ReadingBefore.ALREADY_RIGHT,
            (
                tag("Ratepayers bear the cost of scarcity"),
                styled_cite(),
                line(
                    EVIDENCE,
                    0,
                    run(emphasised_body[:60], character_style="Style13ptBold"),
                    run(emphasised_body[60:500], half_points=SMALL_PRINT),
                    run(emphasised_body[500:640], underline="single", highlight="cyan"),
                    run(emphasised_body[640:], half_points=SMALL_PRINT),
                ),
            ),
            (FULL,),
            "The cite style is used for emphasis in a body. Highlighting says which it is.",
        ),
        LabelledExample(
            shape,
            "a body paragraph with a phrase in the cite style and no highlighting",
            ReadingBefore.ALREADY_RIGHT,
            (
                tag("Planners delay retirements they cannot afford"),
                styled_cite(),
                line(
                    EVIDENCE,
                    0,
                    run(phrase_body[:300], half_points=READING_SIZE),
                    run(phrase_body[300:360], character_style="Style13ptBold"),
                    run(phrase_body[360:700], underline="single", half_points=READING_SIZE),
                    run(phrase_body[700:], half_points=READING_SIZE),
                ),
            ),
            (FULL,),
            "No name and year at its head: the style marks a phrase, not a cite.",
        ),
        LabelledExample(
            shape,
            "a styled cite of 600 characters",
            ReadingBefore.ALREADY_RIGHT,
            (tag("Schools carry the cost of the moratorium"), long_styled_cite(600), marked_up()),
            (FULL,),
        ),
    )


# --------------------------------------------------------------------------------------------
# (3) A card with no cite
# --------------------------------------------------------------------------------------------

_NO_CITE_SHAPE = CiteShape.A_CARD_WITH_NO_CITE


def long_bold_cite(total: int, card: int | None = 0, *, short: str = "Okonkwo 26") -> Line:
    """A bold name and year at 13 pt, then credentials at reading size, to `total` characters."""
    rest = cite_text(total - len(short), ", ", f", {SOURCE}")
    return line(CITE, card, run(short, bold=True, half_points=CITE_SIZE), run(rest, half_points=READING_SIZE))


def _a_card_with_no_cite() -> tuple[LabelledExample, ...]:
    shape = _NO_CITE_SHAPE
    opening = cite_text(700 - len("Okonkwo 26") - len(LINK) - 1, ", ", f", {SOURCE}, ")
    bold_body = prose(600)
    return (
        LabelledExample(
            shape,
            "a bold cite of 520 characters under its tag",
            ReadingBefore.MISREAD,
            (tag("Data centre demand collapses the reserve margin"), long_bold_cite(520), marked_up()),
            (FULL,),
            "Past 400 characters the cite line was read as nothing: the card had no cite.",
        ),
        LabelledExample(
            shape,
            "a bold cite of 700 characters with an underlined link",
            ReadingBefore.MISREAD,
            (
                tag("Load growth outpaced every planning scenario"),
                line(
                    CITE,
                    0,
                    run("Okonkwo 26", bold=True, half_points=CITE_SIZE),
                    run(opening, half_points=READING_SIZE),
                    run(LINK, underline="single", half_points=READING_SIZE),
                    run(".", half_points=READING_SIZE),
                ),
                marked_up(),
            ),
            (FULL,),
            "The underlined link made it body text: the cite was stored in the evidence.",
        ),
        LabelledExample(
            shape,
            "a bold cite of 900 characters",
            ReadingBefore.MISREAD,
            (tag("Retirements outrun replacement capacity"), long_bold_cite(900), marked_up()),
            (FULL,),
        ),
        LabelledExample(
            shape,
            "a bold cite of 1,500 characters",
            ReadingBefore.MISREAD,
            (tag("Forecasts assumed gains that never arrived"), long_bold_cite(1_500), marked_up()),
            (FULL,),
        ),
        LabelledExample(
            shape,
            "a bold cite of 2,000 characters",
            ReadingBefore.MISREAD,
            (tag("Capacity auctions cleared above every estimate"), long_bold_cite(2_000), marked_up()),
            (FULL,),
        ),
        LabelledExample(
            shape,
            "a bold cite of 600 characters with nothing under it",
            ReadingBefore.MISREAD,
            (tag("Older plants fail first"), long_bold_cite(600)),
            (CITE_ONLY,),
            "With no cite and no body the tag was demoted to an analytic: no card at all.",
        ),
        LabelledExample(
            shape,
            "a bold cite above a whole card written as one paragraph",
            ReadingBefore.MISREAD,
            (
                tag("Moratoria shift load to older plants"),
                long_bold_cite(600),
                small_print(LONG_BODY),
            ),
            (FULL,),
            "One of the 337: the body was re-read from a cite guess, and its cite went unread.",
        ),
        LabelledExample(
            shape,
            "a bold cite of 600 characters with no tag above it",
            ReadingBefore.MISREAD,
            (long_bold_cite(600), marked_up()),
            (FULL,),
            "A card with no tag starts at its cite. Nothing was stored.",
        ),
        LabelledExample(
            shape,
            "a second card under one tag behind a bold cite of 700 characters",
            ReadingBefore.MISREAD,
            (
                tag("Reserve margins fall below safe levels"),
                bold_cite(),
                marked_up(),
                long_bold_cite(700, card=1, short="Lindqvist 25"),
                marked_up(card=1, sentence=2),
            ),
            (FULL, FULL),
            "The second cite was read as nothing, and the second body joined the first card.",
        ),
        LabelledExample(
            shape,
            "the cite is on the tag line",
            ReadingBefore.ALREADY_RIGHT,
            (
                tag("Outage risk rises with every deferred retirement, Okonkwo 26"),
                marked_up(),
                marked_up(sentence=2),
            ),
            (FULL,),
            "The file gives the card no cite paragraph. Splitting a tag is a model question.",
        ),
        LabelledExample(
            shape,
            "the file holds no cite",
            ReadingBefore.ALREADY_RIGHT,
            (tag("Ratepayers bear the cost of scarcity"), marked_up(), small_print(prose(300))),
            (FULL,),
        ),
        LabelledExample(
            shape,
            "a body that opens in bold is not a cite",
            ReadingBefore.ALREADY_RIGHT,
            (
                tag("Planners delay retirements they cannot afford"),
                line(
                    EVIDENCE,
                    0,
                    run(bold_body[:50], bold=True, half_points=READING_SIZE),
                    run(bold_body[50:300], half_points=READING_SIZE),
                    run(bold_body[300:420], underline="single", half_points=READING_SIZE),
                    run(bold_body[420:], half_points=READING_SIZE),
                ),
                marked_up(),
            ),
            (FULL,),
            "Bold without a name and a year at the front is emphasis.",
        ),
    )


# --------------------------------------------------------------------------------------------
# (4) A bracketed cite that ends in the cutter's initials
# --------------------------------------------------------------------------------------------

_BRACKET_SHAPE = CiteShape.A_BRACKETED_CITE_WITH_INITIALS


def bracketed_cite(
    total: int,
    card: int | None = 0,
    *,
    brackets: str = "[]",
    after: str = " KR",
    size: int = READING_SIZE,
    link: bool = True,
) -> Line:
    """`Okonkwo 26`, not bold and in no cite style, then one bracket to the end and `after`.

    With `link`, the address inside the bracket is underlined, as Word leaves a pasted one.
    """
    opener, closer = brackets
    short = "Okonkwo 26"
    if not link:
        rest = cite_text(total - len(short), f" {opener}", f"; {SOURCE}{closer}{after}")
        return line(CITE, card, run(short + rest, half_points=size))
    before = cite_text(
        total - len(short) - len(LINK) - len(closer) - len(after), f" {opener}", f"; {SOURCE}, "
    )
    return line(
        CITE,
        card,
        run(short + before, half_points=size),
        run(LINK, underline="single", half_points=size),
        run(closer + after, half_points=size),
    )


def wholly_bracketed_cite(
    total: int,
    card: int | None = 0,
    *,
    brackets: str = "[]",
    after: str = " KR",
    opening: str = "Okonkwo 26, ",
    size: int = SMALL_PRINT,
) -> Line:
    """The whole cite inside one bracket, the name and year first, then `after`."""
    opener, closer = brackets
    return line(
        CITE,
        card,
        run(cite_text(total, f"{opener}{opening}", f"; {SOURCE}{closer}{after}"), half_points=size),
    )


def _a_bracketed_cite_with_initials() -> tuple[LabelledExample, ...]:
    shape = _BRACKET_SHAPE
    stored_full = "The card was stored FULL, with the cite as its evidence text."
    note = "(The 2019 survey covered four regions and is described in the appendix to the filing.)"
    followed = prose(
        420, "Okonkwo 26 [the first of the two studies] found that the margin fell in every season. "
    )
    return (
        LabelledExample(
            shape,
            "a bracketed cite ending in upper-case initials",
            ReadingBefore.MISREAD,
            (tag("Data centre demand collapses the reserve margin"), bracketed_cite(620), marked_up()),
            (FULL,),
            "The underlined link made it body text: the cite was stored in the evidence.",
        ),
        LabelledExample(
            shape,
            "a card that is only a bracketed cite ending in initials",
            ReadingBefore.MISREAD,
            (tag("Load growth outpaced every planning scenario"), bracketed_cite(620)),
            (CITE_ONLY,),
            stored_full,
        ),
        LabelledExample(
            shape,
            "a card that is only a cite in round brackets with lower-case initials, in small print",
            ReadingBefore.MISREAD,
            (
                tag("Retirements outrun replacement capacity"),
                bracketed_cite(540, brackets="()", after=" kr", size=SMALL_PRINT, link=False),
            ),
            (CITE_ONLY,),
            stored_full,
        ),
        LabelledExample(
            shape,
            "a bracketed cite with initials after two slashes",
            ReadingBefore.MISREAD,
            (
                tag("Forecasts assumed gains that never arrived"),
                bracketed_cite(800, after=" //KR"),
                marked_up(),
            ),
            (FULL,),
        ),
        LabelledExample(
            shape,
            "a card that is only a bracketed cite with initials after a dash",
            ReadingBefore.MISREAD,
            (tag("Capacity auctions cleared above every estimate"), bracketed_cite(700, after=" -- KR")),
            (CITE_ONLY,),
            stored_full,
        ),
        LabelledExample(
            shape,
            "a card that is only a bracketed cite with initials after a bar",
            ReadingBefore.MISREAD,
            (tag("Older plants fail first"), bracketed_cite(650, after="|kr")),
            (CITE_ONLY,),
            stored_full,
        ),
        LabelledExample(
            shape,
            "a card that is only a bracketed cite with no initials",
            ReadingBefore.MISREAD,
            (tag("Moratoria shift load to older plants"), bracketed_cite(600, after="")),
            (CITE_ONLY,),
            stored_full,
        ),
        LabelledExample(
            shape,
            "a card that is only a bracketed cite signed by two cutters",
            ReadingBefore.MISREAD,
            (tag("Reserve margins fall below safe levels"), bracketed_cite(900, after=" //kr + mw")),
            (CITE_ONLY,),
            stored_full,
        ),
        LabelledExample(
            shape,
            "a bracketed cite of 1,600 characters with no formatting",
            ReadingBefore.MISREAD,
            (
                tag("Outage risk rises with every deferred retirement"),
                bracketed_cite(1_600, link=False),
                marked_up(),
            ),
            (FULL,),
            "It was read as nothing: the card had no cite.",
        ),
        LabelledExample(
            shape,
            "the whole cite inside the bracket, in small print",
            ReadingBefore.MISREAD,
            (tag("Ratepayers bear the cost of scarcity"), wholly_bracketed_cite(500), marked_up()),
            (FULL,),
            "It was read as the body's first paragraph.",
        ),
        LabelledExample(
            shape,
            "a card that is only a cite wholly inside its bracket",
            ReadingBefore.MISREAD,
            (tag("Planners delay retirements they cannot afford"), wholly_bracketed_cite(500)),
            (CITE_ONLY,),
            stored_full,
        ),
        LabelledExample(
            shape,
            "a card that is only a cite in round brackets behind a first name",
            ReadingBefore.MISREAD,
            (
                tag("Schools carry the cost of the moratorium"),
                wholly_bracketed_cite(
                    450, brackets="()", after="//kr", opening="Adaeze Okonkwo 26, ", size=SMALL_PRINT
                ),
            ),
            (CITE_ONLY,),
            stored_full,
        ),
        LabelledExample(
            shape,
            "a note in brackets inside a body is not a cite",
            ReadingBefore.ALREADY_RIGHT,
            (
                tag("Demand forecasts missed the data centre boom"),
                bold_cite(),
                marked_up(),
                small_print(note),
                marked_up(sentence=3),
            ),
            (FULL,),
            "It opens with a bracket and holds a year, and no name comes with the year.",
        ),
        LabelledExample(
            shape,
            "a bracket followed by a sentence is not a cite",
            ReadingBefore.ALREADY_RIGHT,
            (
                tag("The margin fell in every season measured"),
                bold_cite(),
                marked_up(),
                underlined_at_reading_size(followed),
                marked_up(sentence=2),
            ),
            (FULL,),
            "What follows the bracket is a sentence, not a signature.",
        ),
    )


# --------------------------------------------------------------------------------------------
# (5) A short small-print line directly under a cite
# --------------------------------------------------------------------------------------------

_SMALL_PRINT_SHAPE = CiteShape.A_SMALL_PRINT_LINE_UNDER_A_CITE


def _under_a_cite(
    name: str,
    under: Line,
    *,
    before: ReadingBefore = ReadingBefore.ALREADY_RIGHT,
    then: tuple[Line, ...] | None = None,
    why: str = "",
) -> LabelledExample:
    then = (marked_up(),) if then is None else then
    return LabelledExample(
        _SMALL_PRINT_SHAPE,
        name,
        before,
        (tag("Data centre demand collapses the reserve margin"), styled_cite(), under, *then),
        (FULL,),
        why,
    )


def _a_small_print_line_under_a_cite() -> tuple[LabelledExample, ...]:
    second_cite_line = "Okonkwo 26, " + LINK + ", accessed 3 March 2026"
    return (
        _under_a_cite(
            "a small-print sentence opening In and a year",
            small_print(prose(180, "In 2019, the operator revised its forecast twice. ")),
            why="The body's first line. 178 of the 218 open with such a word.",
        ),
        _under_a_cite(
            "a small-print sentence opening Since and a year",
            small_print(prose(300, "Since 2008, no new baseload unit has entered service. ")),
        ),
        _under_a_cite(
            "a small-print sentence opening By and a year, partly underlined",
            line(
                EVIDENCE,
                0,
                run("By 2030 the fleet ", half_points=SMALL_PRINT),
                run("loses a third of its capacity", underline="single", half_points=SMALL_PRINT),
                run(", on the operator's own schedule.", half_points=SMALL_PRINT),
            ),
        ),
        _under_a_cite(
            "a small-print sentence opening with an acronym and a number",
            small_print(prose(200, "GRID-24 trials showed the same shortfall in every zone. ")),
            why="Not a listed word. v1-e31-t09's rule keeps it in the body.",
        ),
        _under_a_cite(
            "a small-print dateline",
            small_print(prose(200, "March 26, 2026 was the day the operator declared an emergency. ")),
            why="A month is not on the list, because it is also a surname. The assembly keeps it.",
        ),
        _under_a_cite(
            "a highlighted sentence opening In and a year, at reading size",
            line(
                EVIDENCE,
                0,
                run("In 2020, ", half_points=READING_SIZE),
                run("reserve margins fell below the safe level", highlight="cyan", half_points=READING_SIZE),
                run(" for the first time.", half_points=READING_SIZE),
            ),
        ),
        _under_a_cite(
            "a small-print sentence opening In and a year, the card's only body",
            small_print(prose(180, "In 2021, the shortfall reached four gigawatts. ")),
            then=(),
        ),
        _under_a_cite(
            "a small-print line with no number in it",
            small_print(prose(150)),
        ),
        _under_a_cite(
            "a second line of the cite that opens in bold",
            line(
                CITE,
                0,
                run("Okonkwo 26", bold=True, half_points=SMALL_PRINT),
                run(", " + LINK + ", accessed 3 March 2026", half_points=SMALL_PRINT),
            ),
            why="A bold name at the front is how a cite is written, whatever its size.",
        ),
        _under_a_cite(
            "a small-print line between two lines of the cite",
            small_print("Lindqvist 25 and others, cited in the filing named above", unit=CITE),
            then=(
                line(
                    CITE,
                    0,
                    run("Marchetti 24", character_style="Style13ptBold"),
                    run(", reviewing the same filing for an invented regulator."),
                ),
                marked_up(),
            ),
            why="v1-e31-t09 leaves a short guess with a cite directly below it where it is.",
        ),
        _under_a_cite(
            "a second line of the cite in small print, not bold, holding a link",
            small_print(second_cite_line, unit=CITE),
            before=ReadingBefore.STILL_MISREAD,
            why=(
                "Read as the body's first line. In small print with no bold opening it has the "
                "formatting of body text, and only its words say otherwise: at most 25 of the 218."
            ),
        ),
    )


EXAMPLES: tuple[LabelledExample, ...] = (
    *_a_sentence_guessed_to_be_a_cite(),
    *_a_styled_cite_past_the_profile_bound(),
    *_a_card_with_no_cite(),
    *_a_bracketed_cite_with_initials(),
    *_a_small_print_line_under_a_cite(),
)


def examples_of(shape: CiteShape) -> tuple[LabelledExample, ...]:
    return tuple(example for example in EXAMPLES if example.shape is shape)


# --------------------------------------------------------------------------------------------
# Files and labels
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ShapeFile:
    """An invented file and its labels, in the evaluation's own schema."""

    content: bytes
    labels: LabelFile
    lines: tuple[Line, ...]
    cards: tuple[tuple[int, int, CardCompleteness], ...]
    """Each labelled card's first and last paragraph index and its completeness."""


def _build(examples: tuple[LabelledExample, ...]) -> ShapeFile:
    """Join examples into one file, a block heading above each so no card runs into the next."""
    lines: list[Line] = []
    completeness: list[CardCompleteness] = []
    for example in examples:
        first_card = len(completeness)
        lines.append(block(example.name[:1].upper() + example.name[1:]))
        lines.extend(
            Line(
                markup=each.markup,
                text=each.text,
                unit=each.unit,
                card=None if each.card is None else first_card + each.card,
            )
            for each in example.lines
        )
        completeness.extend(example.completeness)

    content = build_docx("".join(each.markup for each in lines))
    labels = LabelFile(
        header=FileLabelHeader(
            digest=keyed_digest(content, TEST_DIGEST_KEY),
            paragraph_count=len(lines),
            blocks=((0, len(lines) - 1),),
            plan_id="",
            status=LabelStatus.CORRECTED,
            prelabel_parser_version="hand-written",
            corrected_by=ReviewerRole.OPERATOR,
        ),
        paragraphs=tuple(
            ParagraphLabel(
                index=index,
                length=len(each.text),
                text_digest=text_digest(each.text, TEST_DIGEST_KEY),
                unit=each.unit,
                card=each.card,
            )
            for index, each in enumerate(lines)
        ),
        cards=tuple(CardLabel(card=card, completeness=kind) for card, kind in enumerate(completeness)),
        spans=(),
    )
    ranges = labels.card_ranges()
    cards = tuple((*ranges[card], kind) for card, kind in enumerate(completeness))
    return ShapeFile(content=content, labels=labels, lines=tuple(lines), cards=cards)


def build_example_file(example: LabelledExample) -> ShapeFile:
    """One example on its own, under its block heading."""
    return _build((example,))


def build_shape_file(shape: CiteShape) -> ShapeFile:
    """Every example of one shape, in one file."""
    return _build(examples_of(shape))


# --------------------------------------------------------------------------------------------
# The table
# --------------------------------------------------------------------------------------------


def _table() -> str:
    """Tag and cite precision and recall, card boundaries and completeness, for each shape."""
    from datetime import date

    from tests.evals.parser.metrics import FileScore, prediction_from_document, score_file

    from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
    from debate_core.domain.debate_files import ParsedDocument
    from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION, DebateDocxParser

    parser = DebateDocxParser()
    snapshot = date(2026, 10, 12)

    def cell(value: float | None) -> str:
        return "n/a" if value is None else f"{value:.3f}"

    def row(name: str, examples: int, score: FileScore) -> str:
        tags, cites = score.units[TAG], score.units[CITE]
        return (
            f"| {name} | {examples} | {score.labeled_rows} "
            f"| {cell(tags.precision)} | {cell(tags.recall)} "
            f"| {cell(cites.precision)} | {cell(cites.recall)} "
            f"| {score.boundary_matches} of {score.labeled_cards} "
            f"| {score.predicted_cards} "
            f"| {score.completeness_correct} of {score.boundary_matches} |"
        )

    rows = [
        f"Parser `{DOCX_PARSER_VERSION}`",
        "",
        "| Shape | Examples | Paragraphs | Tag precision | Tag recall | Cite precision | Cite recall "
        "| Card boundaries | Cards parsed | Completeness |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    total = FileScore()
    for shape in CiteShape:
        built = build_shape_file(shape)
        source = SourceDocument(
            sha256="0" * 64,
            byte_size=len(built.content),
            source_format=SourceFormat.DOCX,
            origin=SourceOrigin.CASELIST_ARCHIVE,
            caselist="hsld26",
            first_seen_snapshot=snapshot,
            last_seen_snapshot=snapshot,
        )
        document = parser.parse(built.content, source, source_path=f"cite-shapes/{shape.value}.docx")
        assert isinstance(document, ParsedDocument), document
        score = score_file(built.labels, prediction_from_document(document))
        rows.append(row(shape.value, len(examples_of(shape)), score))
        total += score
    rows.append(row("**All five**", len(EXAMPLES), total))
    return "\n".join(rows)


if __name__ == "__main__":
    print(_table())
