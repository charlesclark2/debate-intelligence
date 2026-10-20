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
