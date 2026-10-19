"""Cites the parser missed or misread, each shape rebuilt as an invented file (`v1-e31-t12`).

`v1-e31-t09` and the operator's sample of the 2026-10-11 re-parse left five questions about cites.
Counted over the corpus, read in place and by counts only (`docs/data/caselist-parse-report.md`),
they came to these rules:

* **A sentence is not a cite line.** The cite-line guess took any capitalised word followed by two
  or four digits for an author, so *In 2019* opened a cite. A word that opens a sentence is not an
  author unless the line opens in bold, which is how a cite is written.
* **A wiki cite entry has an end.** Past 2,000 characters, with no name and year in its first 300
  and no cite style, a guess is body wherever a card is open, whatever its formatting.
* **A cite in the cite character style is a cite past the profile's 1,000 characters** when the
  style marks a name and a year at its head and nothing in it is highlighted.
* **A cite line can be longer than 400 characters** when it opens in bold with a name and a year,
  or when everything after its name and year sits in one bracket, but for the cutter's signature.
* **A cite written wholly inside a bracket is a cite where a cite stands:** under a tag or under
  the card's cite, before any body.

The labelled examples are in `tests/evals/parser/cite_shapes.py`, where each says how the parser
read it before. This file reads every one of them on its own and compares the card it stores with
the card its paragraphs were written to be. Then it holds each rule at its edges. Every file is
built in memory from invented text, and every expectation is written by hand (working agreement 6).
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from tests.evals.parser.cite_shapes import (
    CITE_SIZE,
    EXAMPLES,
    LINK,
    READING_SIZE,
    SMALL_PRINT,
    SOURCE,
    LabelledExample,
    ReadingBefore,
    ShapeFile,
    build_example_file,
    cite_text,
    prose,
)

from debate_core.application.ports.parsed_store import parse_version_directory
from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import CardCompleteness, ParsedCard, ParsedDocument
from debate_core.domain.style_profile import StructuralUnit, StyleMatchSource, StyleProfile
from debate_core.integrations.docx_parser.parser import DOCX_PARSER_VERSION, DebateDocxParser
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml

SOURCE_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
SNAPSHOT = date(2026, 10, 12)
SOURCE_PATH = "hsld26/Maple Grove/QX/Maple Grove-QX-Neg-Grove City Invitational-Round 1.docx"

#: The version directory the 2026-10-11 re-parse wrote. It stays as it is.
SECOND_CORPUS_PARSE_VERSION = "2026.10.10-docx-2"

TAG = "Data centre demand collapses the reserve margin"
SHORT_CITE = "Okonkwo 26"
CITE_TAIL = f", Adaeze Okonkwo, invented for this test, {SOURCE}."

CITE = StructuralUnit.CITE
EVIDENCE = StructuralUnit.EVIDENCE
OTHER = StructuralUnit.OTHER

PAST_THE_PROFILE_BOUND = "verbatim-cite-run-style-past-the-profile-bound"
BOLD_CITE_LINE = "heuristic-cite-line-bold-author-year"
BRACKETED_CITE_LINE = "heuristic-cite-line-bracketed"
BRACKETED_BEFORE_THE_BODY = "assembly-bracketed-cite-before-the-body"
INSIDE_THE_BODY = "assembly-cite-guess-inside-card-body"
AFTER_THE_CARDS_CITE = "assembly-cite-guess-after-card-cite"
LONGER_THAN_A_CITE = "assembly-cite-guess-longer-than-a-cite"


@pytest.fixture
def parser(profile: StyleProfile) -> DebateDocxParser:
    return DebateDocxParser(profile)


def make_source() -> SourceDocument:
    return SourceDocument(
        sha256=SOURCE_SHA256,
        byte_size=48_000,
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist="hsld26",
        first_seen_snapshot=SNAPSHOT,
        last_seen_snapshot=SNAPSHOT,
    )


def parse_bytes(parser: DebateDocxParser, content: bytes) -> ParsedDocument:
    result = parser.parse(content, make_source(), source_path=SOURCE_PATH)
    assert isinstance(result, ParsedDocument), result
    return result


def parse(parser: DebateDocxParser, body: str) -> ParsedDocument:
    return parse_bytes(parser, build_docx(body))


def units(document: ParsedDocument) -> list[StructuralUnit]:
    return [section.unit for section in document.sections]


def only_card(document: ParsedDocument) -> ParsedCard:
    """The document's one card. Any other number of cards fails here, by assertion."""
    ranges = [
        (card.provenance.first_element_index, card.provenance.last_element_index) for card in document.cards
    ]
    assert len(ranges) == 1, ranges
    return document.cards[0]


def tag_paragraph(text: str = TAG) -> str:
    return paragraph_xml(run_xml(text), style="Heading4")


def block_paragraph(text: str = "Grid Reliability") -> str:
    return paragraph_xml(run_xml(text), style="Heading3")


def cite_paragraph(short: str = SHORT_CITE, tail: str = CITE_TAIL) -> str:
    """A cite as a file with no cite style writes one: a bold name at 13 pt, then the rest."""
    return paragraph_xml(
        run_xml(short, bold=True, half_points=CITE_SIZE) + run_xml(tail, half_points=READING_SIZE)
    )


def body_paragraph(text: str | None = None) -> str:
    """8 pt text with an underlined, highlighted stretch a debater reads aloud."""
    text = text if text is not None else prose(240)
    return paragraph_xml(
        run_xml(text[:60], half_points=SMALL_PRINT)
        + run_xml(text[60:140], underline="single", highlight="cyan", half_points=SMALL_PRINT)
        + run_xml(text[140:], half_points=SMALL_PRINT)
    )


def plain_paragraph(text: str, half_points: int = READING_SIZE) -> str:
    return paragraph_xml(run_xml(text, half_points=half_points))


def underlined_paragraph(text: str, half_points: int = READING_SIZE) -> str:
    """One underlined stretch in the middle third, and no highlighting."""
    first, second = len(text) // 3, 2 * len(text) // 3
    return paragraph_xml(
        run_xml(text[:first], half_points=half_points)
        + run_xml(text[first:second], underline="single", half_points=half_points)
        + run_xml(text[second:], half_points=half_points)
    )


def highlighted_paragraph(text: str, half_points: int = READING_SIZE) -> str:
    first, second = len(text) // 3, 2 * len(text) // 3
    return paragraph_xml(
        run_xml(text[:first], half_points=half_points)
        + run_xml(text[first:second], highlight="cyan", half_points=half_points)
        + run_xml(text[second:], half_points=half_points)
    )


def bold_opening_paragraph(text: str, bold_characters: int = 40) -> str:
    """A paragraph at reading size whose first words are bold, with a highlighted stretch further in."""
    return paragraph_xml(
        run_xml(text[:bold_characters], bold=True, half_points=READING_SIZE)
        + run_xml(text[bold_characters:400], half_points=READING_SIZE)
        + run_xml(text[400:520], underline="single", highlight="cyan", half_points=READING_SIZE)
        + run_xml(text[520:], half_points=READING_SIZE)
    )


def wiki_guess(characters: int, name_and_year_at: int = 900, opening: str = "") -> str:
    """Prose of exactly `characters` that holds an ellipsis and a name with a year.

    The name and year start `name_and_year_at` characters in. It is what the wiki cite-entry guess
    takes for a cite entry, at any length.
    """
    head = prose(name_and_year_at, opening)[: name_and_year_at - 1] + " "
    clause = "Lindqvist 2019 reached the same conclusion [...] and so did the regional audit. "
    text = (head + clause + prose(characters))[:characters]
    assert text.index("Lindqvist 2019") == name_and_year_at
    return text[:-1] + "."


# --------------------------------------------------------------------------------------------
# Every labelled example, read on its own
# --------------------------------------------------------------------------------------------


def expected_cards(built: ShapeFile) -> list[dict[str, object]]:
    """What each labelled card holds, written out from its labelled paragraphs."""
    cards: list[dict[str, object]] = []
    for first, last, completeness in built.cards:
        inside = [line for line in built.lines[first : last + 1] if line.card is not None]
        tags = [line.text for line in inside if line.unit is StructuralUnit.TAG]
        cites = [line.text for line in inside if line.unit is CITE]
        bodies = [line.text for line in inside if line.unit is EVIDENCE]
        cards.append(
            {
                "range": (first, last),
                "tag": tags[0] if tags else "",
                "full_cite": "\n".join(cites),
                "evidence_text": "\n".join(bodies),
                "completeness": completeness,
            }
        )
    return cards


def stored_cards(document: ParsedDocument) -> list[dict[str, object]]:
    return [
        {
            "range": (card.provenance.first_element_index, card.provenance.last_element_index),
            "tag": card.tag or "",
            "full_cite": card.full_cite,
            "evidence_text": card.evidence_text,
            "completeness": card.completeness,
        }
        for card in document.cards
    ]


def _example(example: LabelledExample):  # type: ignore[no-untyped-def]
    marks = (
        [pytest.mark.xfail(strict=True, reason=f"Left as it is. {example.why}")]
        if example.before is ReadingBefore.STILL_MISREAD
        else []
    )
    return pytest.param(example, id=f"{example.shape.value}: {example.name}", marks=marks)


class TestEveryLabelledExample:
    """Each example is its own file: a block heading, then its paragraphs."""

    @pytest.mark.parametrize("example", [_example(example) for example in EXAMPLES])
    def test_each_paragraph_is_read_as_it_is_labelled(
        self, parser: DebateDocxParser, example: LabelledExample
    ) -> None:
        built = build_example_file(example)

        document = parse_bytes(parser, built.content)

        assert [section.text for section in document.sections] == [line.text for line in built.lines]
        assert units(document) == [line.unit for line in built.lines]

    @pytest.mark.parametrize("example", [_example(example) for example in EXAMPLES])
    def test_each_card_holds_its_tag_its_cite_and_its_body(
        self, parser: DebateDocxParser, example: LabelledExample
    ) -> None:
        """The cite is in the cite and the body in the body: neither is stored as the other."""
        built = build_example_file(example)

        document = parse_bytes(parser, built.content)

        assert stored_cards(document) == expected_cards(built)

    def test_the_examples_cover_every_way_the_five_shapes_were_read(self) -> None:
        """Defects, the readings that must not move, and the one left: none is an empty set."""
        readings = {example.before for example in EXAMPLES}
        assert readings == set(ReadingBefore)


# --------------------------------------------------------------------------------------------
# ac3: a card whose only paragraph is a cite is CITE_ONLY
# --------------------------------------------------------------------------------------------

BRACKETS = ["[]", "()"]

#: What a cutter leaves after the closing bracket. Initials in either case, behind slashes, a dash
#: or a bar, two cutters, a word and initials, a full stop, and nothing at all.
SIGNATURES = [
    "",
    " KR",
    " kr",
    "KR",
    " //KR",
    "//kr",
    " -- KR",
    " - kr",
    "|kr",
    " KR + MW",
    " //kr + mw",
    " recut KR",
    ".",
]

FORMS = [
    "after a name and year",
    "after a bold name and year",
    "after a name and year in the cite style",
    "around the whole cite",
    "around the whole cite behind a first name",
]

FORMATTING = ["reading size", "small print", "an underlined link"]


def cite_only_paragraph(
    form: str, brackets: str, signature: str, formatting: str, total: int
) -> tuple[str, str]:
    """One cite paragraph of exactly `total` characters, as markup and as text."""
    opener, closer = brackets
    size = SMALL_PRINT if formatting == "small print" else READING_SIZE
    link = LINK if formatting == "an underlined link" else ""
    closing = f"; {SOURCE}, " if link else f"; {SOURCE}"
    end = f"{closer}{signature}"
    if form.startswith("around"):
        opening = f"{opener}Adaeze Okonkwo 26, " if form.endswith("first name") else f"{opener}Okonkwo 26, "
        before = cite_text(total - len(link) - len(end), opening, closing)
        head = ""
    else:
        head = SHORT_CITE
        before = cite_text(total - len(head) - len(link) - len(end), f" {opener}", closing)
    head_formatting: dict[str, Any] = {
        "after a name and year": {"half_points": size},
        "after a bold name and year": {"bold": True, "half_points": CITE_SIZE},
        "after a name and year in the cite style": {"character_style": "Style13ptBold"},
    }.get(form, {})
    runs = run_xml(head, **head_formatting) if head else ""
    runs += run_xml(before, half_points=size)
    if link:
        runs += run_xml(link, underline="single", half_points=size)
    runs += run_xml(end, half_points=size)
    return paragraph_xml(runs), head + before + link + end


class TestACardThatIsOnlyACite:
    """A tag and one paragraph under it, and that paragraph is the card's cite (Goal criterion ac3).

    The operator's sample of the 2026-10-11 re-parse held such a card stored `FULL`: a bracketed
    cite ending in the cutter's initials after the closing bracket, read as body text.
    """

    @pytest.mark.parametrize("signature", SIGNATURES, ids=lambda signature: repr(signature))
    @pytest.mark.parametrize("brackets", BRACKETS)
    @pytest.mark.parametrize("form", FORMS)
    def test_it_is_cite_only_whatever_its_bracket_and_initials_form(
        self, parser: DebateDocxParser, form: str, brackets: str, signature: str
    ) -> None:
        markup, text = cite_only_paragraph(form, brackets, signature, "an underlined link", 620)

        document = parse(parser, tag_paragraph() + markup)

        card = only_card(document)
        assert units(document) == [StructuralUnit.TAG, CITE]
        assert card.tag == TAG
        assert card.completeness is CardCompleteness.CITE_ONLY
        assert card.full_cite == text
        assert card.evidence_text == ""

    @pytest.mark.parametrize("total", [300, 620, 1_400])
    @pytest.mark.parametrize("formatting", FORMATTING)
    @pytest.mark.parametrize("brackets", BRACKETS)
    @pytest.mark.parametrize("form", FORMS)
    def test_it_is_cite_only_at_any_length_and_in_any_formatting(
        self, parser: DebateDocxParser, form: str, brackets: str, formatting: str, total: int
    ) -> None:
        markup, text = cite_only_paragraph(form, brackets, " KR", formatting, total)
        assert len(text) == total

        document = parse(parser, tag_paragraph() + markup)

        card = only_card(document)
        assert units(document) == [StructuralUnit.TAG, CITE]
        assert card.completeness is CardCompleteness.CITE_ONLY
        assert card.full_cite == text
        assert card.evidence_text == ""

    @pytest.mark.parametrize("form", FORMS[:3])
    def test_its_short_cite_is_the_name_and_year(self, parser: DebateDocxParser, form: str) -> None:
        markup, _ = cite_only_paragraph(form, "[]", " KR", "an underlined link", 620)

        card = only_card(parse(parser, tag_paragraph() + markup))

        assert card.short_cite == SHORT_CITE

    @pytest.mark.parametrize("form", FORMS[3:])
    def test_a_cite_that_opens_with_its_bracket_gets_no_guessed_short_cite(
        self, parser: DebateDocxParser, form: str
    ) -> None:
        """The short-cite pattern reads the front of a line. An invented one would be repeated as fact."""
        markup, _ = cite_only_paragraph(form, "[]", " KR", "small print", 500)

        card = only_card(parse(parser, tag_paragraph() + markup))

        assert card.short_cite is None

    def test_the_card_under_it_is_untouched(self, parser: DebateDocxParser) -> None:
        """Two cards: the first only its cite, the second whole."""
        markup, text = cite_only_paragraph(FORMS[0], "[]", " KR", "an underlined link", 620)
        body = prose(240)

        document = parse(
            parser,
            tag_paragraph()
            + markup
            + tag_paragraph("Older plants fail first")
            + cite_paragraph()
            + body_paragraph(body),
        )

        assert len(document.cards) == 2
        first, second = document.cards
        assert (first.completeness, first.full_cite, first.evidence_text) == (
            CardCompleteness.CITE_ONLY,
            text,
            "",
        )
        assert (second.completeness, second.full_cite, second.evidence_text) == (
            CardCompleteness.FULL,
            SHORT_CITE + CITE_TAIL,
            body,
        )

    def test_with_a_body_under_it_the_card_is_full_and_the_cite_is_not_in_the_evidence(
        self, parser: DebateDocxParser
    ) -> None:
        """The same cite in a full card: it was the evidence text's first paragraph."""
        markup, text = cite_only_paragraph(FORMS[0], "[]", " KR", "an underlined link", 620)
        body = prose(240)

        card = only_card(parse(parser, tag_paragraph() + markup + body_paragraph(body)))

        assert card.completeness is CardCompleteness.FULL
        assert card.full_cite == text
        assert card.evidence_text == body


# --------------------------------------------------------------------------------------------
# A sentence is not a cite line
# --------------------------------------------------------------------------------------------

IN_2019 = prose(260, "In 2019, the regional operator revised its forecast. ")


class TestASentenceIsNotACiteLine:
    def test_it_stays_in_its_card(self, parser: DebateDocxParser) -> None:
        first, last = prose(240), prose(260, "Planners then delayed two retirements. ")
        body = (
            tag_paragraph()
            + cite_paragraph()
            + body_paragraph(first)
            + underlined_paragraph(IN_2019)
            + body_paragraph(last)
        )

        card = only_card(parse(parser, body))

        assert card.evidence_text == "\n".join([first, IN_2019, last])
        assert card.full_cite == SHORT_CITE + CITE_TAIL
        assert (card.provenance.first_element_index, card.provenance.last_element_index) == (0, 4)

    def test_it_is_read_as_the_body_it_is_formatted_as_and_not_as_a_guess_overridden(
        self, parser: DebateDocxParser
    ) -> None:
        """The classifier no longer guesses, so the assembly has nothing to re-read."""
        document = parse(
            parser, tag_paragraph() + cite_paragraph() + body_paragraph() + underlined_paragraph(IN_2019)
        )

        assert document.sections[3].unit is EVIDENCE
        assert document.sections[3].match.rule_id == "heuristic-marked-up-body-text"

    def test_in_small_print_it_names_the_shrunk_text_rule(self, parser: DebateDocxParser) -> None:
        """v1-e31-t09 re-read it from the assembly. The same paragraph is body by its own formatting now."""
        document = parse(
            parser, tag_paragraph() + cite_paragraph() + plain_paragraph(IN_2019, half_points=SMALL_PRINT)
        )

        assert document.sections[2].match.rule_id == "heuristic-shrunk-body-text"
        assert document.cards[0].evidence_text == IN_2019

    def test_with_no_card_open_it_starts_no_card(self, parser: DebateDocxParser) -> None:
        """A body with no tag and no cite is a stray body. It was stored as a card with no tag."""
        document = parse(parser, block_paragraph() + plain_paragraph(IN_2019) + body_paragraph())

        assert document.cards == ()
        assert units(document) == [StructuralUnit.BLOCK, EVIDENCE, EVIDENCE]

    def test_a_line_that_opens_in_bold_is_still_the_classifiers_call(self, parser: DebateDocxParser) -> None:
        """Bold is how a cite is written, and what such a line is cannot be told from here."""
        line = paragraph_xml(
            run_xml("In 2019", bold=True, half_points=CITE_SIZE)
            + run_xml(", a year the operator revised its forecast twice.", half_points=READING_SIZE)
        )

        document = parse(parser, tag_paragraph() + line + body_paragraph())

        assert document.sections[1].unit is CITE
        assert document.sections[1].match.rule_id == "heuristic-cite-line-author-year"

    def test_an_authors_name_is_still_an_author_when_the_line_is_not_bold(
        self, parser: DebateDocxParser
    ) -> None:
        line = plain_paragraph("Lindqvist 25, Professor of Engineering at an invented university.")

        card = only_card(parse(parser, tag_paragraph() + line + body_paragraph()))

        assert card.short_cite == "Lindqvist 25"


# --------------------------------------------------------------------------------------------
# A wiki cite entry has an end
# --------------------------------------------------------------------------------------------


class TestAGuessLongerThanACiteEntry:
    """Past 2,000 characters a guess with no name at its head is body, whatever its formatting.

    `v1-e31-t09` asked that such a paragraph be formatted as body: small print throughout, or
    highlighted, and not opening in bold. A body's first words are often bold, and 220 cards were
    still stored with their body in the cite and no evidence text.
    """

    def test_after_the_cards_cite_it_is_the_body(self, parser: DebateDocxParser) -> None:
        text = wiki_guess(2_300)

        document = parse(parser, tag_paragraph() + cite_paragraph() + bold_opening_paragraph(text))

        card = only_card(document)
        assert card.completeness is CardCompleteness.FULL
        assert card.full_cite == SHORT_CITE + CITE_TAIL
        assert card.evidence_text == text
        assert document.sections[2].match.rule_id == f"{AFTER_THE_CARDS_CITE}:heuristic-wiki-cite-entry"

    def test_inside_a_body_it_stays_in_the_body(self, parser: DebateDocxParser) -> None:
        first, text, last = (
            prose(240),
            wiki_guess(2_300),
            prose(250, "Planners then delayed two retirements. "),
        )
        body = (
            tag_paragraph()
            + cite_paragraph()
            + body_paragraph(first)
            + underlined_paragraph(text)
            + body_paragraph(last)
        )

        document = parse(parser, body)

        card = only_card(document)
        assert card.evidence_text == "\n".join([first, text, last])
        assert document.sections[3].match.rule_id == f"{INSIDE_THE_BODY}:heuristic-wiki-cite-entry"

    def test_under_a_tag_with_no_cite_it_is_the_body(self, parser: DebateDocxParser) -> None:
        text = wiki_guess(2_300)

        document = parse(parser, tag_paragraph() + bold_opening_paragraph(text))

        card = only_card(document)
        assert (card.completeness, card.full_cite, card.evidence_text) == (CardCompleteness.FULL, "", text)
        assert document.sections[1].match.rule_id == f"{LONGER_THAN_A_CITE}:heuristic-wiki-cite-entry"

    def test_it_is_a_guess_reread_and_says_so(self, parser: DebateDocxParser) -> None:
        document = parse(
            parser, tag_paragraph() + cite_paragraph() + bold_opening_paragraph(wiki_guess(2_300))
        )

        match = document.sections[2].match
        assert match.match_source is StyleMatchSource.HEURISTIC
        assert match.confidence <= 0.6

    def test_at_the_bound_it_is_still_the_cite_the_classifier_called_it(
        self, parser: DebateDocxParser
    ) -> None:
        text = wiki_guess(2_000)
        assert len(text) == 2_000

        document = parse(parser, tag_paragraph() + cite_paragraph() + bold_opening_paragraph(text))

        assert document.sections[2].unit is CITE
        assert document.cards[0].completeness is CardCompleteness.CITE_ONLY

    def test_one_character_past_the_bound_it_is_the_body(self, parser: DebateDocxParser) -> None:
        text = wiki_guess(2_001)
        assert len(text) == 2_001

        document = parse(parser, tag_paragraph() + cite_paragraph() + bold_opening_paragraph(text))

        assert document.sections[2].unit is EVIDENCE
        assert document.cards[0].evidence_text == text

    def test_a_name_and_a_year_in_its_first_300_characters_leave_it_a_cite(
        self, parser: DebateDocxParser
    ) -> None:
        """A cite run together with its card names its source at the front. That is a model question."""
        text = wiki_guess(2_300, name_and_year_at=300)

        document = parse(parser, tag_paragraph() + cite_paragraph() + bold_opening_paragraph(text))

        assert document.sections[2].unit is CITE

    def test_a_name_and_a_year_one_character_further_in_do_not(self, parser: DebateDocxParser) -> None:
        text = wiki_guess(2_300, name_and_year_at=301)

        document = parse(parser, tag_paragraph() + cite_paragraph() + bold_opening_paragraph(text))

        assert document.sections[2].unit is EVIDENCE

    def test_a_sentence_opener_and_a_year_at_its_head_is_not_a_name_and_a_year(
        self, parser: DebateDocxParser
    ) -> None:
        """*In 2019* in a body's first words is a date, not a source."""
        text = wiki_guess(2_300, opening="In 2019, the regional operator revised its forecast. ")

        document = parse(parser, tag_paragraph() + cite_paragraph() + bold_opening_paragraph(text))

        assert document.sections[2].unit is EVIDENCE

    def test_a_guess_whose_only_name_and_year_is_a_sentence_opener_is_the_body(
        self, parser: DebateDocxParser
    ) -> None:
        """An ellipsis and *In 2019* are all the guess had. Nothing in the paragraph names a source."""
        text = prose(2_300, "In 2019, the regional operator revised its forecast [...] and then again. ")
        assert "Lindqvist" not in text

        document = parse(parser, tag_paragraph() + cite_paragraph() + bold_opening_paragraph(text))

        assert document.sections[2].match.rule_id == f"{AFTER_THE_CARDS_CITE}:heuristic-wiki-cite-entry"
        assert only_card(document).evidence_text == text

    def test_under_a_bare_tag_a_sentence_opener_and_a_year_at_its_head_do_not_hold_it(
        self, parser: DebateDocxParser
    ) -> None:
        """v1-e31-t09 left a long first paragraph that opens with a name and a year. *In 2019* is neither."""
        text = wiki_guess(2_300, opening="In 2019, the regional operator revised its forecast. ")

        document = parse(parser, tag_paragraph() + bold_opening_paragraph(text))

        assert document.sections[1].unit is EVIDENCE
        assert document.cards[0].evidence_text == text

    def test_a_short_guess_above_it_is_not_a_line_between_two_cites(self, parser: DebateDocxParser) -> None:
        """A short guess with a cite directly below it stays a line of the cite. A long guess is no cite."""
        short = "March 2019 was the first time the operator revised its forecast upward in a decade."
        long = wiki_guess(2_300)
        body = (
            tag_paragraph()
            + cite_paragraph()
            + plain_paragraph(short, half_points=SMALL_PRINT)
            + bold_opening_paragraph(long)
        )

        card = only_card(parse(parser, body))

        assert card.full_cite == SHORT_CITE + CITE_TAIL
        assert card.evidence_text == short + "\n" + long

    def test_a_run_in_the_cite_character_style_in_its_middle_is_emphasis(
        self, parser: DebateDocxParser
    ) -> None:
        """Until `v1-e31-t19` any cite-style run held the guess as a cite. The style here marks a
        phrase 1,200 characters in, not a name and year at the head, so it is emphasis and the
        paragraph is the body (the PM's ruling in `v1-e31-t12`'s review). A style at the head still
        holds a guess: `test_remaining_cite_shapes.py`, `TestTheCiteStyleHold`."""
        text = wiki_guess(2_300)
        styled = paragraph_xml(
            run_xml(text[:40], bold=True, half_points=READING_SIZE)
            + run_xml(text[40:1_200], half_points=READING_SIZE)
            + run_xml(text[1_200:1_260], character_style="Style13ptBold")
            + run_xml(text[1_260:], half_points=READING_SIZE)
        )

        document = parse(parser, tag_paragraph() + cite_paragraph() + styled)

        assert document.sections[2].unit is EVIDENCE
        assert document.sections[2].match.rule_id == f"{AFTER_THE_CARDS_CITE}:heuristic-wiki-cite-entry"

    def test_with_no_card_open_it_is_left_the_cite_of_a_card_with_no_tag(
        self, parser: DebateDocxParser
    ) -> None:
        """Re-read as body it would belong to no card, and the text would be dropped."""
        text = wiki_guess(2_300)

        document = parse(parser, block_paragraph() + bold_opening_paragraph(text))

        card = only_card(document)
        assert document.sections[1].unit is CITE
        assert (card.tag or "", card.full_cite) == ("", text)


# --------------------------------------------------------------------------------------------
# A cite in the cite character style, past the profile's bound
# --------------------------------------------------------------------------------------------


def styled_cite(
    total: int,
    *,
    before_the_name: str = "",
    short: str = SHORT_CITE,
    highlight: bool = False,
    closing: str = f"; {SOURCE}] KR",
) -> tuple[str, str]:
    """`short` in the cite character style, then bracketed credentials, to `total` characters."""
    rest = cite_text(total - len(before_the_name) - len(short), " [", closing)
    runs = run_xml(before_the_name, half_points=READING_SIZE) if before_the_name else ""
    runs += run_xml(short, character_style="Style13ptBold")
    if highlight:
        runs += run_xml(rest[:200], half_points=READING_SIZE)
        runs += run_xml(rest[200:300], highlight="cyan", half_points=READING_SIZE)
        runs += run_xml(rest[300:], half_points=READING_SIZE)
    else:
        runs += run_xml(rest, half_points=READING_SIZE)
    return paragraph_xml(runs), before_the_name + short + rest


class TestAStyledCitePastTheProfileBound:
    """The style rule let go at 1,000 characters, and 811 such cites were read as nothing at all."""

    def test_it_is_the_cards_cite_and_the_body_is_the_body(self, parser: DebateDocxParser) -> None:
        markup, text = styled_cite(1_400)
        body = prose(240)

        document = parse(parser, tag_paragraph() + markup + body_paragraph(body))

        card = only_card(document)
        assert (card.full_cite, card.short_cite, card.evidence_text) == (text, SHORT_CITE, body)
        assert document.sections[1].match.rule_id == PAST_THE_PROFILE_BOUND
        assert document.sections[1].match.match_source is StyleMatchSource.VERBATIM_ALIAS

    def test_under_the_bound_it_is_read_by_the_rule_it_always_was(self, parser: DebateDocxParser) -> None:
        markup, text = styled_cite(1_000)
        assert len(text) == 1_000

        document = parse(parser, tag_paragraph() + markup + body_paragraph())

        assert document.sections[1].match.rule_id == "verbatim-cite-run-style"

    def test_one_character_past_the_bound_it_is_still_a_cite(self, parser: DebateDocxParser) -> None:
        markup, _ = styled_cite(1_001)

        document = parse(parser, tag_paragraph() + markup + body_paragraph())

        assert document.sections[1].unit is CITE
        assert document.sections[1].match.rule_id == PAST_THE_PROFILE_BOUND

    def test_at_4000_characters_it_is_a_cite(self, parser: DebateDocxParser) -> None:
        markup, text = styled_cite(4_000)
        assert len(text) == 4_000

        document = parse(parser, tag_paragraph() + markup + body_paragraph())

        assert document.sections[1].unit is CITE

    def test_past_4000_characters_it_is_left_as_it_was(self, parser: DebateDocxParser) -> None:
        """Longer than any such cite in the corpus: a card run together with its cite, if anything."""
        markup, _ = styled_cite(4_001)

        document = parse(parser, tag_paragraph() + markup + body_paragraph())

        assert document.sections[1].unit is not CITE

    def test_a_styled_name_behind_a_first_name_is_a_cite(self, parser: DebateDocxParser) -> None:
        markup, text = styled_cite(1_400, before_the_name="Adaeze ")

        card = only_card(parse(parser, tag_paragraph() + markup + body_paragraph()))

        assert card.full_cite == text

    def test_a_name_and_year_that_start_40_characters_in_are_at_its_head(
        self, parser: DebateDocxParser
    ) -> None:
        before = "x" * 39 + " "
        markup, _ = styled_cite(1_400, before_the_name=before)

        document = parse(parser, tag_paragraph() + markup + body_paragraph())

        assert document.sections[1].unit is CITE

    def test_a_name_and_year_that_start_41_characters_in_are_not(self, parser: DebateDocxParser) -> None:
        before = "x" * 40 + " "
        markup, _ = styled_cite(1_400, before_the_name=before)

        document = parse(parser, tag_paragraph() + markup + body_paragraph())

        assert document.sections[1].unit is not CITE

    def test_highlighting_leaves_it_as_it_was(self, parser: DebateDocxParser) -> None:
        """Nobody highlights a citation. A highlighted paragraph behind a name is a card in one paragraph."""
        markup, _ = styled_cite(1_400, highlight=True)

        document = parse(parser, tag_paragraph() + markup + body_paragraph())

        assert document.sections[1].unit is EVIDENCE

    def test_the_style_on_a_phrase_further_in_does_not_make_a_cite(self, parser: DebateDocxParser) -> None:
        """The name and year at its head are plain, and the style marks something else."""
        text = SHORT_CITE + cite_text(1_390, " argues that ", " in every season measured.")
        markup = paragraph_xml(
            run_xml(text[:600], half_points=READING_SIZE)
            + run_xml(text[600:660], character_style="Style13ptBold")
            + run_xml(text[660:], half_points=READING_SIZE)
        )

        document = parse(parser, tag_paragraph() + cite_paragraph() + markup)

        assert document.sections[2].unit is not CITE

    def test_a_sentence_opener_in_the_cite_style_does_not_make_a_cite(self, parser: DebateDocxParser) -> None:
        text = prose(1_300, "In 2019, the regional operator revised its forecast. ")
        markup = paragraph_xml(
            run_xml(text[:7], character_style="Style13ptBold") + run_xml(text[7:], half_points=READING_SIZE)
        )

        document = parse(parser, tag_paragraph() + cite_paragraph() + markup)

        assert document.sections[2].unit is EVIDENCE


# --------------------------------------------------------------------------------------------
# A cite line longer than 400 characters
# --------------------------------------------------------------------------------------------


def bold_cite(
    total: int, *, short: str = SHORT_CITE, bold: bool = True, highlight: bool = False
) -> tuple[str, str]:
    """A name and year at 13 pt, then credentials with no bracket, to `total` characters."""
    rest = cite_text(total - len(short), ", ", f", {SOURCE}")
    runs = run_xml(short, bold=bold, half_points=CITE_SIZE)
    if highlight:
        runs += run_xml(rest[:100], half_points=READING_SIZE)
        runs += run_xml(rest[100:200], highlight="cyan", half_points=READING_SIZE)
        runs += run_xml(rest[200:], half_points=READING_SIZE)
    else:
        runs += run_xml(rest, half_points=READING_SIZE)
    return paragraph_xml(runs), short + rest


class TestACiteLineLongerThanFourHundredCharacters:
    """33,624 tagged cards in the corpus have no cite, and 21,585 of them an unread line under the tag."""

    def test_a_bold_name_and_year_open_the_cards_cite(self, parser: DebateDocxParser) -> None:
        markup, text = bold_cite(700)
        body = prose(240)

        document = parse(parser, tag_paragraph() + markup + body_paragraph(body))

        card = only_card(document)
        assert (card.full_cite, card.short_cite, card.evidence_text) == (text, SHORT_CITE, body)
        assert document.sections[1].match.rule_id == BOLD_CITE_LINE
        assert document.sections[1].match.match_source is StyleMatchSource.HEURISTIC

    def test_at_400_characters_it_is_read_by_the_rule_it_always_was(self, parser: DebateDocxParser) -> None:
        markup, text = bold_cite(400)
        assert len(text) == 400

        document = parse(parser, tag_paragraph() + markup + body_paragraph())

        assert document.sections[1].match.rule_id == "heuristic-cite-line-author-year"

    def test_at_401_characters_it_is_a_cite(self, parser: DebateDocxParser) -> None:
        markup, _ = bold_cite(401)

        document = parse(parser, tag_paragraph() + markup + body_paragraph())

        assert document.sections[1].match.rule_id == BOLD_CITE_LINE

    def test_at_2000_characters_it_is_a_cite(self, parser: DebateDocxParser) -> None:
        markup, text = bold_cite(2_000)
        assert len(text) == 2_000

        document = parse(parser, tag_paragraph() + markup + body_paragraph())

        assert document.sections[1].unit is CITE

    def test_past_2000_characters_it_is_left_as_it_was(self, parser: DebateDocxParser) -> None:
        markup, _ = bold_cite(2_001)

        document = parse(parser, tag_paragraph() + markup + body_paragraph())

        assert document.sections[1].unit is OTHER

    def test_without_the_bold_opening_or_a_bracket_it_is_left_as_it_was(
        self, parser: DebateDocxParser
    ) -> None:
        """A long paragraph at reading size that opens with a name and a year: evidence naming its source."""
        markup, _ = bold_cite(700, bold=False)

        document = parse(parser, tag_paragraph() + markup + body_paragraph())

        assert document.sections[1].unit is OTHER

    def test_highlighting_leaves_it_as_it_was(self, parser: DebateDocxParser) -> None:
        markup, _ = bold_cite(700, highlight=True)

        document = parse(parser, tag_paragraph() + markup + body_paragraph())

        assert document.sections[1].unit is EVIDENCE

    def test_a_bold_sentence_opener_and_a_year_do_not_open_a_long_cite(
        self, parser: DebateDocxParser
    ) -> None:
        """Under 400 characters the old rule's reading stands. Over it, nothing new is taken for a cite."""
        markup, _ = bold_cite(700, short="In 2019")

        document = parse(parser, tag_paragraph() + markup + body_paragraph())

        assert document.sections[1].unit is OTHER

    def test_with_no_tag_above_it_it_starts_a_card_with_no_tag(self, parser: DebateDocxParser) -> None:
        markup, text = bold_cite(700)
        body = prose(240)

        card = only_card(parse(parser, block_paragraph() + markup + body_paragraph(body)))

        assert (card.tag or "", card.full_cite, card.evidence_text) == ("", text, body)

    def test_after_a_body_it_starts_a_second_card_and_takes_its_own_body(
        self, parser: DebateDocxParser
    ) -> None:
        """Its body was joined to the card above it: two cards stored as one."""
        markup, text = bold_cite(700, short="Lindqvist 25")
        first_body, second_body = prose(240), prose(250, "Planners then delayed two retirements. ")
        body = (
            tag_paragraph()
            + cite_paragraph()
            + body_paragraph(first_body)
            + markup
            + body_paragraph(second_body)
        )

        document = parse(parser, body)
        assert len(document.cards) == 2
        first, second = document.cards

        assert (first.full_cite, first.evidence_text) == (SHORT_CITE + CITE_TAIL, first_body)
        assert (second.tag or "", second.full_cite, second.evidence_text) == ("", text, second_body)


def bracketed_cite(
    total: int,
    *,
    brackets: str = "[]",
    after: str = " KR",
    between: str = " ",
    short: str = SHORT_CITE,
    highlight: bool = False,
    inside: str = "",
) -> tuple[str, str]:
    """`short`, not bold and in no cite style, then one bracket to the end and `after`."""
    opener, closer = brackets
    rest = cite_text(total - len(short), f"{between}{opener}{inside}", f"; {SOURCE}{closer}{after}")
    if highlight:
        runs = run_xml(short + rest[:100], half_points=READING_SIZE)
        runs += run_xml(rest[100:200], highlight="cyan", half_points=READING_SIZE)
        runs += run_xml(rest[200:], half_points=READING_SIZE)
    else:
        runs = run_xml(short + rest, half_points=READING_SIZE)
    return paragraph_xml(runs), short + rest


class TestABracketedCiteLine:
    """A name and year, then everything else in one bracket, but for the cutter's signature."""

    def test_it_is_the_cards_cite(self, parser: DebateDocxParser) -> None:
        markup, text = bracketed_cite(700)
        body = prose(240)

        document = parse(parser, tag_paragraph() + markup + body_paragraph(body))

        card = only_card(document)
        assert (card.full_cite, card.short_cite, card.evidence_text) == (text, SHORT_CITE, body)
        assert document.sections[1].match.rule_id == BRACKETED_CITE_LINE

    @pytest.mark.parametrize("between", [" ", ", ", " - ", " – ", " — ", ": ", "; ", ". ", ""])
    def test_the_bracket_opens_straight_after_the_name_and_year(
        self, parser: DebateDocxParser, between: str
    ) -> None:
        markup, _ = bracketed_cite(700, between=between)

        document = parse(parser, tag_paragraph() + markup + body_paragraph())

        assert document.sections[1].unit is CITE

    def test_words_between_the_year_and_the_bracket_leave_it_as_it_was(
        self, parser: DebateDocxParser
    ) -> None:
        markup, _ = bracketed_cite(700, between=" writes that ")

        document = parse(parser, tag_paragraph() + markup + body_paragraph())

        assert document.sections[1].unit is OTHER

    def test_a_bracket_inside_the_bracket_does_not_close_it(self, parser: DebateDocxParser) -> None:
        markup, text = bracketed_cite(700, inside="formerly [until 2024] at the regulator; ")

        card = only_card(parse(parser, tag_paragraph() + markup + body_paragraph()))

        assert card.full_cite == text

    def test_a_signature_of_30_characters_is_a_signature(self, parser: DebateDocxParser) -> None:
        after = " //recut kr + mw, grove city xi"
        assert len(after.strip()) == 30
        markup, _ = bracketed_cite(700, after=after)

        document = parse(parser, tag_paragraph() + markup + body_paragraph())

        assert document.sections[1].unit is CITE

    def test_31_characters_after_the_bracket_are_not(self, parser: DebateDocxParser) -> None:
        after = " //recut kr + mw, grove city xii"
        assert len(after.strip()) == 31
        markup, _ = bracketed_cite(700, after=after)

        document = parse(parser, tag_paragraph() + markup + body_paragraph())

        assert document.sections[1].unit is OTHER

    def test_a_bracket_that_never_closes_leaves_it_as_it_was(self, parser: DebateDocxParser) -> None:
        markup, text = bracketed_cite(700, brackets="[)", after="")
        assert "]" not in text

        document = parse(parser, tag_paragraph() + markup + body_paragraph())

        assert document.sections[1].unit is OTHER

    def test_at_2000_characters_it_is_a_cite(self, parser: DebateDocxParser) -> None:
        markup, text = bracketed_cite(2_000)
        assert len(text) == 2_000

        document = parse(parser, tag_paragraph() + markup + body_paragraph())

        assert document.sections[1].unit is CITE

    def test_past_2000_characters_it_is_left_as_it_was(self, parser: DebateDocxParser) -> None:
        markup, _ = bracketed_cite(2_001)

        document = parse(parser, tag_paragraph() + markup + body_paragraph())

        assert document.sections[1].unit is OTHER

    def test_highlighting_leaves_it_as_it_was(self, parser: DebateDocxParser) -> None:
        markup, _ = bracketed_cite(700, highlight=True)

        document = parse(parser, tag_paragraph() + markup + body_paragraph())

        assert document.sections[1].unit is EVIDENCE

    def test_a_sentence_opener_and_a_year_before_a_bracket_are_not_a_cite(
        self, parser: DebateDocxParser
    ) -> None:
        markup, _ = bracketed_cite(700, short="In 2019")

        document = parse(parser, tag_paragraph() + markup + body_paragraph())

        assert document.sections[1].unit is OTHER

    def test_in_small_print_inside_a_body_it_stays_in_the_body(self, parser: DebateDocxParser) -> None:
        """v1-e31-t09's rule for a guess formatted as body, inside an open body, still holds."""
        text = SHORT_CITE + cite_text(690, " [", f"; {SOURCE}] KR")
        first = prose(240)
        body = (
            tag_paragraph()
            + cite_paragraph()
            + body_paragraph(first)
            + plain_paragraph(text, half_points=SMALL_PRINT)
        )

        document = parse(parser, body)

        card = only_card(document)
        assert card.evidence_text == "\n".join([first, text])
        assert document.sections[3].match.rule_id == f"{INSIDE_THE_BODY}:{BRACKETED_CITE_LINE}"


# --------------------------------------------------------------------------------------------
# A cite written wholly inside a bracket
# --------------------------------------------------------------------------------------------


def wholly_bracketed(
    total: int = 500,
    *,
    brackets: str = "[]",
    after: str = " KR",
    opening: str = "Okonkwo 26, ",
    half_points: int = SMALL_PRINT,
    highlight: bool = False,
) -> tuple[str, str]:
    opener, closer = brackets
    text = cite_text(total, f"{opener}{opening}", f"; {SOURCE}{closer}{after}")
    if highlight:
        runs = run_xml(text[:100], half_points=half_points)
        runs += run_xml(text[100:200], highlight="cyan", half_points=half_points)
        runs += run_xml(text[200:], half_points=half_points)
    else:
        runs = run_xml(text, half_points=half_points)
    return paragraph_xml(runs), text


class TestACiteWhollyInsideABracket:
    """It opens with the bracket, so nothing that reads the front of a line sees a name and a year."""

    def test_under_a_tag_it_is_the_cards_cite(self, parser: DebateDocxParser) -> None:
        markup, text = wholly_bracketed()
        body = prose(240)

        document = parse(parser, tag_paragraph() + markup + body_paragraph(body))

        card = only_card(document)
        assert (card.full_cite, card.evidence_text, card.completeness) == (text, body, CardCompleteness.FULL)
        assert document.sections[1].match.rule_id == f"{BRACKETED_BEFORE_THE_BODY}:heuristic-shrunk-body-text"
        assert document.sections[1].match.match_source is StyleMatchSource.HEURISTIC
        assert document.sections[1].match.confidence == 0.6

    def test_at_reading_size_with_nothing_under_it_the_tag_is_still_a_tag(
        self, parser: DebateDocxParser
    ) -> None:
        """Read as nothing, it left the tag with no cite and no body: the tag was demoted to an analytic."""
        markup, text = wholly_bracketed(half_points=READING_SIZE)

        document = parse(parser, tag_paragraph() + markup)

        card = only_card(document)
        assert units(document) == [StructuralUnit.TAG, CITE]
        assert (card.tag, card.full_cite, card.completeness) == (TAG, text, CardCompleteness.CITE_ONLY)
        assert (
            document.sections[1].match.rule_id
            == f"{BRACKETED_BEFORE_THE_BODY}:heuristic-unclassified-paragraph"
        )

    def test_under_the_cards_cite_it_is_a_second_line_of_the_cite(self, parser: DebateDocxParser) -> None:
        markup, text = wholly_bracketed(half_points=READING_SIZE)
        body = prose(240)

        card = only_card(parse(parser, tag_paragraph() + cite_paragraph() + markup + body_paragraph(body)))

        assert card.full_cite == SHORT_CITE + CITE_TAIL + "\n" + text
        assert card.evidence_text == body

    def test_a_blank_line_above_it_changes_nothing(self, parser: DebateDocxParser) -> None:
        markup, text = wholly_bracketed()

        card = only_card(parse(parser, tag_paragraph() + paragraph_xml("") + markup + body_paragraph()))

        assert card.full_cite == text

    def test_inside_a_body_it_stays_in_the_body(self, parser: DebateDocxParser) -> None:
        """A reference in brackets inside a source's own text is the source's, not the card's."""
        markup, text = wholly_bracketed()
        first, last = prose(240), prose(250, "Planners then delayed two retirements. ")
        body = tag_paragraph() + cite_paragraph() + body_paragraph(first) + markup + body_paragraph(last)

        document = parse(parser, body)

        card = only_card(document)
        assert card.evidence_text == "\n".join([first, text, last])
        assert document.sections[3].match.rule_id == "heuristic-shrunk-body-text"

    def test_after_a_guess_that_becomes_the_body_it_is_left_as_it_was(self, parser: DebateDocxParser) -> None:
        """The paragraph above it is a guessed cite the assembly re-reads as body, so a body is open.

        Read as a cite there, a reference in brackets ended the card and took the rest of its body
        for a card with no tag: eight cards in the corpus, before this was held.
        """
        markup, text = wholly_bracketed(half_points=READING_SIZE)
        long_body, last = wiki_guess(2_300), prose(240)
        body = (
            tag_paragraph()
            + cite_paragraph()
            + bold_opening_paragraph(long_body)
            + markup
            + body_paragraph(last)
        )

        document = parse(parser, body)

        card = only_card(document)
        assert document.sections[3].unit is OTHER
        assert card.evidence_text == "\n".join([long_body, last])
        assert text not in card.full_cite

    def test_under_a_guess_that_stays_the_cards_cite_it_is_a_second_line_of_it(
        self, parser: DebateDocxParser
    ) -> None:
        """A cite line the classifier guessed, at reading size, is a line of the cite like any other."""
        markup, text = wholly_bracketed(half_points=READING_SIZE)
        first_line = "Okonkwo 26, Adaeze Okonkwo, invented for this test"
        body = prose(240)

        card = only_card(
            parse(parser, tag_paragraph() + plain_paragraph(first_line) + markup + body_paragraph(body))
        )

        assert card.full_cite == first_line + "\n" + text
        assert card.evidence_text == body

    def test_under_an_undertag_it_is_the_cards_cite(self, parser: DebateDocxParser) -> None:
        markup, text = wholly_bracketed()
        undertag = paragraph_xml(run_xml("Answers the reserve margin turn"), style="Undertag")

        card = only_card(parse(parser, tag_paragraph() + undertag + markup + body_paragraph()))

        assert card.full_cite == text
        assert card.undertag == "Answers the reserve margin turn"

    def test_in_a_body_paragraph_style_it_is_taken_at_the_styles_word(self, parser: DebateDocxParser) -> None:
        """Only what the classifier guessed is re-read. A style is the file's author saying what it is."""
        _, text = wholly_bracketed()
        styled = paragraph_xml(run_xml(text, half_points=SMALL_PRINT), style="CardBody")

        document = parse(parser, tag_paragraph() + styled + body_paragraph())

        assert document.sections[1].unit is EVIDENCE
        assert document.sections[1].match.match_source is not StyleMatchSource.HEURISTIC
        assert document.cards[0].full_cite == ""

    def test_in_a_table_cell_it_is_page_furniture(self, parser: DebateDocxParser) -> None:
        """A table under a tag is a chart, whatever its cells hold."""
        markup, text = wholly_bracketed()
        table = f"<w:tbl><w:tr><w:tc>{markup}</w:tc></w:tr></w:tbl>"

        document = parse(parser, tag_paragraph() + table + body_paragraph())

        assert document.sections[1].unit is OTHER
        assert document.sections[1].match.rule_id == "assembly-table-cell"
        assert text not in document.cards[0].full_cite

    def test_at_the_head_of_a_file_it_is_left_as_it_was(self, parser: DebateDocxParser) -> None:
        """Nothing is above it, so no card is open for it to be the cite of."""
        markup, _ = wholly_bracketed()

        document = parse(parser, markup + body_paragraph())

        assert document.cards == ()
        assert units(document) == [EVIDENCE, EVIDENCE]

    def test_with_no_card_open_it_is_left_as_it_was(self, parser: DebateDocxParser) -> None:
        markup, _ = wholly_bracketed()

        document = parse(parser, block_paragraph() + markup + body_paragraph())

        assert document.cards == ()
        assert document.sections[1].unit is EVIDENCE

    def test_a_note_that_holds_a_year_and_no_name_is_not_a_cite(self, parser: DebateDocxParser) -> None:
        note = "(The 2019 survey covered four regions and is described in the appendix to the filing.)"
        body = prose(240)

        card = only_card(
            parse(
                parser,
                tag_paragraph() + plain_paragraph(note, half_points=SMALL_PRINT) + body_paragraph(body),
            )
        )

        assert (card.full_cite, card.evidence_text) == ("", "\n".join([note, body]))

    def test_a_name_and_year_that_start_40_characters_in_are_at_its_head(
        self, parser: DebateDocxParser
    ) -> None:
        markup, text = wholly_bracketed(opening="x" * 38 + " Okonkwo 26, ")
        assert text.index("Okonkwo 26") == 40

        document = parse(parser, tag_paragraph() + markup + body_paragraph())

        assert document.sections[1].unit is CITE

    def test_a_name_and_year_that_start_41_characters_in_are_not(self, parser: DebateDocxParser) -> None:
        markup, text = wholly_bracketed(opening="x" * 39 + " Okonkwo 26, ")
        assert text.index("Okonkwo 26") == 41

        document = parse(parser, tag_paragraph() + markup + body_paragraph())

        assert document.sections[1].unit is EVIDENCE

    def test_31_characters_after_the_bracket_leave_it_as_it_was(self, parser: DebateDocxParser) -> None:
        markup, _ = wholly_bracketed(after=" //recut kr + mw, grove city xii")

        document = parse(parser, tag_paragraph() + markup + body_paragraph())

        assert document.sections[1].unit is EVIDENCE

    def test_past_2000_characters_it_is_left_as_it_was(self, parser: DebateDocxParser) -> None:
        markup, _ = wholly_bracketed(2_001)

        document = parse(parser, tag_paragraph() + markup + body_paragraph())

        assert document.sections[1].unit is EVIDENCE

    def test_at_2000_characters_it_is_a_cite(self, parser: DebateDocxParser) -> None:
        markup, text = wholly_bracketed(2_000)
        assert len(text) == 2_000

        document = parse(parser, tag_paragraph() + markup + body_paragraph())

        assert document.sections[1].unit is CITE

    def test_highlighting_leaves_it_as_it_was(self, parser: DebateDocxParser) -> None:
        markup, _ = wholly_bracketed(highlight=True)

        document = parse(parser, tag_paragraph() + markup + body_paragraph())

        assert document.sections[1].unit is EVIDENCE


# --------------------------------------------------------------------------------------------
# The parser version
# --------------------------------------------------------------------------------------------


class TestTheParserVersion:
    def test_it_is_not_the_version_the_second_corpus_parse_wrote(self) -> None:
        """A reading that differs has to say so: the stored cards name the reading that made them."""
        assert DOCX_PARSER_VERSION != SECOND_CORPUS_PARSE_VERSION

    def test_it_is_the_version_this_task_bumped_to_or_a_later_one(self) -> None:
        """`2026.10.12-docx-3`, or one a later task bumped to (`v1-e31-t15`: `2026.10.18-docx-4`)."""
        assert parse_version_directory(DOCX_PARSER_VERSION) >= parse_version_directory("2026.10.12-docx-3")

    def test_its_directory_sorts_after_the_second_corpus_parses(self) -> None:
        """The newest version directory is the one a reader takes."""
        names = sorted([DOCX_PARSER_VERSION, SECOND_CORPUS_PARSE_VERSION], key=parse_version_directory)
        assert names == [SECOND_CORPUS_PARSE_VERSION, DOCX_PARSER_VERSION]

    def test_every_card_names_it(self, parser: DebateDocxParser) -> None:
        card = only_card(parse(parser, tag_paragraph() + cite_paragraph() + body_paragraph()))

        assert card.provenance.parser_version == DOCX_PARSER_VERSION
