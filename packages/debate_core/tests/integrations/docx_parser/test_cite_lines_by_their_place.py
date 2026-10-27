"""`v1-e31-t31`: cite lines the classifier cannot call, read by where they stand.

The labelled evaluation's tallies (`docs/data/parser-eval-gaps-2026-10.md`) put most of its missed
cites in three places, and the PM ruled a rule for each (2026-10-27, Q1 (a)):

1. **a later line of a cite**, read as nothing, directly under a line read as a cite and directly
   over a body, holding a link or a year: part of the cite;
2. **a line under a tag**, read as nothing, directly over a body, holding a link or a year: the
   card's cite;
3. **a cite set in the tag style**, read as a second tag directly under a tag, over a body, with a
   name and year at its head: the card's cite, and the tag above it keeps its tag reading.

Each rule's negative case is here too: the line with neither a link nor a year, and the second tag
with no name and year at its head, keep the reading they had.

Every file is built in memory from invented text, and every expectation is written by hand from it
(working agreement 6).
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from tests.evals.parser.cite_shapes import CITE_SIZE, READING_SIZE, SMALL_PRINT, SOURCE, prose

from debate_core.application.ports.parsed_store import parse_version_directory
from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import ParsedCard, ParsedDocument
from debate_core.domain.style_profile import StructuralUnit, StyleProfile
from debate_core.integrations.docx_parser.parser import DOCX_PARSER_VERSION, DebateDocxParser
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml

SOURCE_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
SNAPSHOT = date(2026, 10, 27)
SOURCE_PATH = "hspolicy26/Invented High/AB/Invented High-AB-Neg-Imaginary Invitational-Round 2.docx"

TAG = "Data centre demand collapses the reserve margin"

Runs = list[tuple[str, dict[str, Any]]]


@pytest.fixture
def parser(profile: StyleProfile) -> DebateDocxParser:
    return DebateDocxParser(profile)


def parse(parser: DebateDocxParser, *paragraphs: str) -> ParsedDocument:
    source = SourceDocument(
        sha256=SOURCE_SHA256,
        byte_size=48_000,
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist="hspolicy26",
        first_seen_snapshot=SNAPSHOT,
        last_seen_snapshot=SNAPSHOT,
    )
    result = parser.parse(build_docx("".join(paragraphs)), source, source_path=SOURCE_PATH)
    assert isinstance(result, ParsedDocument), result
    return result


def only_card(document: ParsedDocument) -> ParsedCard:
    """The document's one card. Any other number of cards fails here, by assertion."""
    ranges = [(c.provenance.first_element_index, c.provenance.last_element_index) for c in document.cards]
    assert len(ranges) == 1, ranges
    return document.cards[0]


def paragraph(runs: Runs, style: str | None = None) -> tuple[str, str]:
    """A paragraph's markup and its text."""
    markup = paragraph_xml("".join(run_xml(text, **formatting) for text, formatting in runs), style=style)
    return markup, "".join(text for text, _ in runs)


def plain(text: str, style: str | None = None) -> tuple[str, str]:
    """A line with nothing set: no style, no bold, no size."""
    return paragraph([(text, {})], style)


def unit_of(document: ParsedDocument, text: str) -> tuple[StructuralUnit, str]:
    (section,) = [section for section in document.sections if section.text == text]
    return section.unit, section.match.rule_id


TAG_MARKUP = paragraph_xml(run_xml(TAG), style="Heading4")
BODY_TEXT = prose(240)
BODY, _ = paragraph(
    [
        (BODY_TEXT[:60], {"half_points": SMALL_PRINT}),
        (BODY_TEXT[60:140], {"underline": "single", "highlight": "cyan", "half_points": SMALL_PRINT}),
        (BODY_TEXT[140:], {"half_points": SMALL_PRINT}),
    ]
)
CITE_MARKUP, CITE_TEXT = paragraph(
    [
        ("Ferreira 25", {"bold": True, "half_points": CITE_SIZE}),
        (f", Ines Ferreira, invented for this test, {SOURCE}", {"half_points": READING_SIZE}),
    ]
)
#: Later lines of a cite, each opening in lower case so that no cite rule of the classifier reads it.
LINK_LINE, LINK_TEXT = plain("accessed through https://example.org/reserve-margins")
YEAR_LINE, YEAR_TEXT = plain("reprinted in the spring of 2026 by an invented press")
NEITHER_LINE, NEITHER_TEXT = plain("as the invented press reprinted it")
#: A line under a tag that is the card's only cite.
UNDER_A_TAG_LINE, UNDER_A_TAG_TEXT = plain(
    "reported by an invented grid desk, 2026, https://example.org/desk"
)
NOT_A_SOURCE_LINE, NOT_A_SOURCE_TEXT = plain("as the invented grid desk reported it")
#: A cite set in the tag style, and a second tag that is no cite.
TAG_STYLE_CITE, TAG_STYLE_CITE_TEXT = plain(
    "Lindqvist 25, Professor of Grid Studies, Invented University", "Heading4"
)
SECOND_TAG, SECOND_TAG_TEXT = plain("Reserve margins recover by the spring", "Heading4")
BLANK = paragraph_xml(run_xml(""))

CITE_LINE_BELOW_A_CITE = "assembly-cite-line-below-a-cite"
CITE_LINE_BELOW_A_TAG = "assembly-cite-line-below-a-tag"
CITE_IN_THE_TAG_STYLE = "assembly-cite-in-the-tag-style-below-a-tag"


class TestALaterLineOfACite:
    @pytest.mark.parametrize(("line", "text"), [(LINK_LINE, LINK_TEXT), (YEAR_LINE, YEAR_TEXT)])
    def test_a_line_with_a_link_or_a_year_is_part_of_the_cite(
        self, parser: DebateDocxParser, line: str, text: str
    ) -> None:
        document = parse(parser, TAG_MARKUP, CITE_MARKUP, line, BODY)

        card = only_card(document)
        assert (card.tag, card.full_cite, card.evidence_text) == (TAG, f"{CITE_TEXT}\n{text}", BODY_TEXT)
        unit, rule = unit_of(document, text)
        assert unit is StructuralUnit.CITE
        assert rule == f"{CITE_LINE_BELOW_A_CITE}:heuristic-unclassified-paragraph"

    def test_a_blank_line_between_it_and_the_cite_is_stepped_over(self, parser: DebateDocxParser) -> None:
        document = parse(parser, TAG_MARKUP, CITE_MARKUP, BLANK, LINK_LINE, BODY)

        assert only_card(document).full_cite == f"{CITE_TEXT}\n{LINK_TEXT}"

    def test_a_line_with_neither_keeps_its_reading(self, parser: DebateDocxParser) -> None:
        document = parse(parser, TAG_MARKUP, CITE_MARKUP, NEITHER_LINE, BODY)

        card = only_card(document)
        assert (card.tag, card.full_cite, card.evidence_text) == (TAG, CITE_TEXT, BODY_TEXT)
        assert unit_of(document, NEITHER_TEXT) == (StructuralUnit.OTHER, "heuristic-unclassified-paragraph")

    def test_a_line_with_no_body_below_it_keeps_its_reading(self, parser: DebateDocxParser) -> None:
        document = parse(parser, TAG_MARKUP, CITE_MARKUP, LINK_LINE, SECOND_TAG, CITE_MARKUP, BODY)

        assert unit_of(document, LINK_TEXT)[0] is StructuralUnit.OTHER


class TestALineUnderATag:
    def test_a_line_with_a_link_or_a_year_is_the_cards_cite(self, parser: DebateDocxParser) -> None:
        document = parse(parser, TAG_MARKUP, UNDER_A_TAG_LINE, BODY)

        card = only_card(document)
        assert (card.tag, card.full_cite, card.evidence_text) == (TAG, UNDER_A_TAG_TEXT, BODY_TEXT)
        assert unit_of(document, UNDER_A_TAG_TEXT) == (
            StructuralUnit.CITE,
            f"{CITE_LINE_BELOW_A_TAG}:heuristic-unclassified-paragraph",
        )

    def test_a_line_with_neither_leaves_the_card_with_no_cite(self, parser: DebateDocxParser) -> None:
        document = parse(parser, TAG_MARKUP, NOT_A_SOURCE_LINE, BODY)

        card = only_card(document)
        assert (card.tag, card.full_cite, card.evidence_text) == (TAG, "", BODY_TEXT)
        assert unit_of(document, NOT_A_SOURCE_TEXT)[0] is StructuralUnit.OTHER

    def test_a_line_with_no_body_below_it_keeps_its_reading(self, parser: DebateDocxParser) -> None:
        document = parse(parser, TAG_MARKUP, UNDER_A_TAG_LINE, SECOND_TAG, CITE_MARKUP, BODY)

        assert unit_of(document, UNDER_A_TAG_TEXT)[0] is StructuralUnit.OTHER


class TestACiteInTheTagStyle:
    def test_it_is_the_cite_and_the_tag_above_gets_its_reading_back(self, parser: DebateDocxParser) -> None:
        document = parse(parser, TAG_MARKUP, TAG_STYLE_CITE, BODY)

        card = only_card(document)
        assert (card.tag, card.full_cite, card.evidence_text) == (TAG, TAG_STYLE_CITE_TEXT, BODY_TEXT)
        assert unit_of(document, TAG)[0] is StructuralUnit.TAG
        assert unit_of(document, TAG_STYLE_CITE_TEXT) == (
            StructuralUnit.CITE,
            f"{CITE_IN_THE_TAG_STYLE}:verbatim-style-id:Heading4",
        )

    def test_a_second_tag_with_no_name_and_year_at_its_head_stays_a_tag(
        self, parser: DebateDocxParser
    ) -> None:
        document = parse(parser, TAG_MARKUP, SECOND_TAG, BODY)

        card = only_card(document)
        assert (card.tag, card.full_cite) == (SECOND_TAG_TEXT, "")
        assert unit_of(document, TAG)[0] is StructuralUnit.ANALYTIC

    def test_with_no_body_below_it_it_stays_a_tag(self, parser: DebateDocxParser) -> None:
        document = parse(parser, TAG_MARKUP, TAG_STYLE_CITE, SECOND_TAG, CITE_MARKUP, BODY)

        assert unit_of(document, TAG_STYLE_CITE_TEXT)[0] is not StructuralUnit.CITE


class TestTheParserVersion:
    """One bump for the three cite rules and the white highlight together (the PM's ruling Q5)."""

    def test_it_is_the_version_this_task_bumped_to(self) -> None:
        assert DOCX_PARSER_VERSION == "2026.10.27-docx-7"

    def test_its_directory_sorts_after_the_store_it_replaces(self) -> None:
        names = sorted([DOCX_PARSER_VERSION, "2026.10.20-docx-6"], key=parse_version_directory)
        assert names == ["2026.10.20-docx-6", DOCX_PARSER_VERSION]

    def test_every_card_names_it(self, parser: DebateDocxParser) -> None:
        document = parse(parser, TAG_MARKUP, UNDER_A_TAG_LINE, BODY)

        assert {card.provenance.parser_version for card in document.cards} == {"2026.10.27-docx-7"}
