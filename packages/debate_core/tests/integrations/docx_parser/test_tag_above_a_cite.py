"""`v1-e31-t24`: what stands between a cite and the rest of its card.

**An Undertag line between a highlighted cite and its body** (ac4, the PM's amendment of
2026-10-19, from `v1-e33-t02`'s ruling (d)). `v1-e31-t19` reads a highlighted paragraph with a
cite's shape as the cite only where a cite stands and a body follows; a card written as one
paragraph behind its cite has the same shape and no body after it. "Follows" stepped over blank
lines and page furniture, not over an Undertag line, so the provenance line a built file writes
below every cite turned a highlighted cite into body. The look-ahead now steps over an Undertag too.

Every file is built in memory from invented text, and every expectation is written by hand from it
(working agreement 6).
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from tests.evals.parser.cite_shapes import CITE_SIZE, READING_SIZE, SMALL_PRINT, SOURCE, prose, qualifications

from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import CardCompleteness, ParsedCard, ParsedDocument
from debate_core.domain.style_profile import StyleProfile
from debate_core.integrations.docx_parser.parser import DebateDocxParser
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml

SOURCE_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
SNAPSHOT = date(2026, 10, 20)
SOURCE_PATH = "hspf26/Invented High/AB/Invented High-AB-Aff-Imaginary Invitational-Round 3.docx"

TAG = "Data centre demand collapses the reserve margin"
FULL = CardCompleteness.FULL
HIGHLIGHTED_CITE = "assembly-highlighted-cite-before-the-body"

Runs = list[tuple[str, dict[str, Any]]]


@pytest.fixture
def parser(profile: StyleProfile) -> DebateDocxParser:
    return DebateDocxParser(profile)


def parse(parser: DebateDocxParser, *paragraphs: str, styles_xml: str | None = None) -> ParsedDocument:
    source = SourceDocument(
        sha256=SOURCE_SHA256,
        byte_size=48_000,
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist="hspf26",
        first_seen_snapshot=SNAPSHOT,
        last_seen_snapshot=SNAPSHOT,
    )
    result = parser.parse(
        build_docx("".join(paragraphs), styles_xml=styles_xml), source, source_path=SOURCE_PATH
    )
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


def tag_paragraph(text: str = TAG) -> str:
    return paragraph_xml(run_xml(text), style="Heading4")


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
        (f", Ines Ferreira, invented for this test, {SOURCE}.", {"half_points": READING_SIZE}),
    ]
)
#: A cite whose name a debater highlighted to read: a bold, highlighted name and year, then the rest.
HIGHLIGHTED_MARKUP, HIGHLIGHTED_TEXT = paragraph(
    [("Okonkwo 26", {"bold": True, "highlight": "yellow"}), (", " + qualifications(588), {})]
)
UNDERTAG_MARKUP, UNDERTAG_TEXT = paragraph([("[Disclosed: hspf26 2026-09-15]", {})], "Undertag")
BLANK = paragraph_xml(run_xml(""))


class TestAnUndertagBetweenAHighlightedCiteAndItsBody:
    def test_the_highlighted_cite_is_still_the_cards_cite(self, parser: DebateDocxParser) -> None:
        document = parse(parser, tag_paragraph(), HIGHLIGHTED_MARKUP, UNDERTAG_MARKUP, BODY)

        card = only_card(document)
        assert (card.tag, card.full_cite, card.undertag, card.evidence_text, card.completeness) == (
            TAG,
            HIGHLIGHTED_TEXT,
            UNDERTAG_TEXT,
            BODY_TEXT,
            FULL,
        )
        (cite,) = [section for section in document.sections if section.text == HIGHLIGHTED_TEXT]
        assert cite.match.rule_id == f"{HIGHLIGHTED_CITE}:heuristic-marked-up-body-text"

    def test_two_undertag_lines_and_a_blank_line_are_stepped_over(self, parser: DebateDocxParser) -> None:
        document = parse(
            parser, tag_paragraph(), HIGHLIGHTED_MARKUP, UNDERTAG_MARKUP, BLANK, UNDERTAG_MARKUP, BODY
        )

        card = only_card(document)
        assert (card.full_cite, card.undertag, card.evidence_text) == (
            HIGHLIGHTED_TEXT,
            f"{UNDERTAG_TEXT}\n{UNDERTAG_TEXT}",
            BODY_TEXT,
        )

    def test_with_no_body_after_the_undertag_it_is_a_card_written_as_one_paragraph(
        self, parser: DebateDocxParser
    ) -> None:
        document = parse(
            parser,
            tag_paragraph(),
            HIGHLIGHTED_MARKUP,
            UNDERTAG_MARKUP,
            tag_paragraph("Another tag"),
            CITE_MARKUP,
            BODY,
        )

        assert [(c.tag, c.full_cite, c.undertag, c.evidence_text) for c in document.cards] == [
            (TAG, "", UNDERTAG_TEXT, HIGHLIGHTED_TEXT),
            ("Another tag", CITE_TEXT, "", BODY_TEXT),
        ]

    def test_a_cite_after_the_undertag_is_not_a_body(self, parser: DebateDocxParser) -> None:
        document = parse(parser, tag_paragraph(), HIGHLIGHTED_MARKUP, UNDERTAG_MARKUP, CITE_MARKUP, BODY)

        assert [(c.tag, c.full_cite, c.evidence_text) for c in document.cards] == [
            (TAG, "", HIGHLIGHTED_TEXT),
            (None, CITE_TEXT, BODY_TEXT),
        ]


# --------------------------------------------------------------------------------------------
# A bold tag above a cite that opens a card with no tag (ac2, the PM's ruling of 2026-10-20)
# --------------------------------------------------------------------------------------------

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NORMAL_AND_HEADINGS = (
    '<w:style w:type="paragraph" w:styleId="Normal" w:default="1"><w:name w:val="normal"/></w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading4"><w:name w:val="heading 4"/><w:basedOn w:val="Normal"/>'
    "</w:style>"
    '<w:style w:type="paragraph" w:styleId="Undertag"><w:name w:val="Undertag"/></w:style>'
    '<w:style w:type="character" w:styleId="StyleUnderline"><w:name w:val="Style Underline"/></w:style>'
    '<w:style w:type="character" w:styleId="Emphasis"><w:name w:val="Emphasis"/></w:style>'
)


def styles_with_defaults(run_properties: str) -> str:
    return (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="{W}">'
        f"<w:docDefaults><w:rPrDefault><w:rPr>{run_properties}</w:rPr></w:rPrDefault></w:docDefaults>"
        f"{NORMAL_AND_HEADINGS}</w:styles>"
    )


#: (7)'s file: every run that says nothing is bold at 13 pt.
BOLD_DEFAULTS = styles_with_defaults('<w:b w:val="1"/><w:sz w:val="26"/>')
#: An ordinary Word file: defaults that set a size and nothing else.
SIZE_DEFAULTS = styles_with_defaults('<w:sz w:val="24"/>')
TAKEN = "assembly-bold-tag-above-a-cite"

LINE = "Demand outruns new generation"


def off(text: str, **formatting: Any) -> tuple[str, dict[str, Any]]:
    """A run that switches bold off and sets its size, as the file's bodies and cites write theirs."""
    return (text, {"bold": False, "half_points": READING_SIZE, **formatting})


SECOND_CITE_MARKUP, SECOND_CITE_TEXT = paragraph(
    [off("Okonkwo 26"), off(f", Adaeze Okonkwo, invented for this test, {SOURCE}.")]
)
SECOND_BODY_TEXT = prose(260, "Reserve margins ")
SECOND_BODY, _ = paragraph(
    [
        off(SECOND_BODY_TEXT[:80], half_points=SMALL_PRINT),
        off(SECOND_BODY_TEXT[80:], underline="single", half_points=SMALL_PRINT),
    ]
)
#: (7)'s line: nothing set of bold or size, its last words underlined directly.
SEVENS_LINE, _ = paragraph([("Demand outruns ", {}), ("new generation", {"underline": "single"})])


def card_above_then(
    line: str, *, styles_xml: str = BOLD_DEFAULTS, parser: DebateDocxParser
) -> ParsedDocument:
    """A card under a tag, then `line`, then a cite that opens a card with no tag, and its body."""
    return parse(
        parser,
        tag_paragraph(),
        CITE_MARKUP,
        BODY,
        line,
        SECOND_CITE_MARKUP,
        SECOND_BODY,
        styles_xml=styles_xml,
    )


def cards_of(document: ParsedDocument) -> list[tuple[str | None, str, str]]:
    return [(card.tag, card.full_cite, card.evidence_text) for card in document.cards]


def section_with(document: ParsedDocument, text: str) -> Any:
    (section,) = [section for section in document.sections if section.text == text]
    return section


AS_IT_SHOULD = [(TAG, CITE_TEXT, BODY_TEXT), (LINE, SECOND_CITE_TEXT, SECOND_BODY_TEXT)]


class TestABoldLineAboveACiteThatOpensACardWithNoTag:
    def test_a_line_bold_only_through_the_document_defaults_is_the_cards_tag(
        self, parser: DebateDocxParser
    ) -> None:
        document = card_above_then(SEVENS_LINE, parser=parser)

        assert cards_of(document) == AS_IT_SHOULD, "the card above loses the line and the card below gains it"
        line = section_with(document, LINE)
        assert line.match.rule_id == f"{TAKEN}:heuristic-marked-up-body-text"
        assert line.match.confidence == 0.5
        assert document.cards[1].provenance.first_element_index == line.element_index

    def test_a_line_bold_by_its_own_run_with_no_size_stated_is_the_cards_tag(
        self, parser: DebateDocxParser
    ) -> None:
        markup, _ = paragraph([(LINE, {"bold": True})])
        document = card_above_then(markup, styles_xml=SIZE_DEFAULTS, parser=parser)

        assert cards_of(document) == AS_IT_SHOULD
        assert section_with(document, LINE).match.rule_id == f"{TAKEN}:heuristic-unclassified-paragraph"

    def test_a_blank_line_between_it_and_the_cite_is_stepped_over(self, parser: DebateDocxParser) -> None:
        document = card_above_then(SEVENS_LINE + paragraph_xml(run_xml("")), parser=parser)

        assert cards_of(document) == AS_IT_SHOULD

    def test_with_no_card_above_it_the_line_still_tags_the_card(self, parser: DebateDocxParser) -> None:
        document = parse(parser, SEVENS_LINE, SECOND_CITE_MARKUP, SECOND_BODY, styles_xml=BOLD_DEFAULTS)

        assert cards_of(document) == [(LINE, SECOND_CITE_TEXT, SECOND_BODY_TEXT)]

    def test_the_classifier_still_reads_only_what_a_run_says(self, parser: DebateDocxParser) -> None:
        """Inherited formatting is read inside this rule only: elsewhere the line is what it was."""
        document = parse(
            parser, tag_paragraph(), CITE_MARKUP, BODY, SEVENS_LINE, BODY, styles_xml=BOLD_DEFAULTS
        )

        assert cards_of(document) == [(TAG, CITE_TEXT, f"{BODY_TEXT}\n{LINE}\n{BODY_TEXT}")]
        assert section_with(document, LINE).match.rule_id == "heuristic-marked-up-body-text"


class TestWhatTheRuleLeaves:
    """Each guard's refusal: the file reads as it did at `2026.10.18-docx-5`."""

    def assert_left(self, document: ParsedDocument, line: str, rule: str) -> None:
        assert [card.tag for card in document.cards] == [TAG, None]
        assert line in document.cards[0].evidence_text or rule == "heuristic-unclassified-paragraph"
        assert section_with(document, line).match.rule_id == rule

    def test_a_card_that_already_has_a_tag(self, parser: DebateDocxParser) -> None:
        markup, _ = paragraph([(LINE, {"bold": True})])
        document = parse(
            parser, tag_paragraph(), markup, SECOND_CITE_MARKUP, SECOND_BODY, styles_xml=SIZE_DEFAULTS
        )

        assert cards_of(document) == [(TAG, SECOND_CITE_TEXT, SECOND_BODY_TEXT)]
        assert section_with(document, LINE).match.rule_id == "heuristic-unclassified-paragraph"

    def test_a_line_with_a_highlighted_run(self, parser: DebateDocxParser) -> None:
        markup, _ = paragraph([("Demand outruns ", {}), ("new generation", {"highlight": "yellow"})])
        self.assert_left(card_above_then(markup, parser=parser), LINE, "heuristic-marked-up-body-text")

    @pytest.mark.parametrize("style", ["StyleUnderline", "Emphasis"])
    def test_a_line_in_the_underline_or_emphasis_style(self, parser: DebateDocxParser, style: str) -> None:
        markup, _ = paragraph([("Demand outruns ", {}), ("new generation", {"character_style": style})])
        document = card_above_then(markup, parser=parser)

        assert [card.tag for card in document.cards] == [TAG, None]
        assert not section_with(document, LINE).match.rule_id.startswith(TAKEN)

    def test_a_line_over_300_characters(self, parser: DebateDocxParser) -> None:
        long_line = "Demand outruns new generation in " + "every region and every season, " * 9 + "again."
        assert len(long_line) > 300
        markup, _ = paragraph([(long_line[:-6], {}), (long_line[-6:], {"underline": "single"})])
        self.assert_left(card_above_then(markup, parser=parser), long_line, "heuristic-marked-up-body-text")

    def test_a_line_that_names_a_source_at_its_head(self, parser: DebateDocxParser) -> None:
        named = "As Lindqvist 2019 warned, demand outruns new generation"
        markup, _ = paragraph([(named[:-14], {}), (named[-14:], {"underline": "single"})])
        self.assert_left(card_above_then(markup, parser=parser), named, "heuristic-marked-up-body-text")

    def test_a_bold_line_with_no_size_anywhere(self, parser: DebateDocxParser) -> None:
        """Word shows no size the bold-heading rule could read: the rule's size test is not passed."""
        markup, _ = paragraph([(LINE, {"bold": True})])
        document = card_above_then(markup, styles_xml=styles_with_defaults(""), parser=parser)

        self.assert_left(document, LINE, "heuristic-unclassified-paragraph")

    def test_a_line_bold_off_by_its_own_run(self, parser: DebateDocxParser) -> None:
        markup, _ = paragraph([off("Demand outruns "), off("new generation", underline="single")])
        self.assert_left(card_above_then(markup, parser=parser), LINE, "heuristic-marked-up-body-text")

    def test_only_the_paragraph_directly_above_and_never_a_second(self, parser: DebateDocxParser) -> None:
        between, between_text = paragraph([off("A note left plain")])
        document = card_above_then(SEVENS_LINE + between, parser=parser)

        assert [card.tag for card in document.cards] == [TAG, None]
        for text in (LINE, between_text):
            assert not section_with(document, text).match.rule_id.startswith(TAKEN)
