"""`v1-e31-t31`: white highlight is not read as highlight (the PM's ruling of 2026-10-27, Q3 (a)).

White is invisible on the page, and the profile already calls it not a reading colour. The labelled
evaluation's only highlight errors were added highlight, 187 of its 707 characters white. Read as
highlight, white text also counted as read aloud in search. lightGray and black are visible and are
still read as highlight.

The ruling is read as the formatting spans: a white run carries no `HIGHLIGHT` span. The classifier's
"has a highlighted run", which decides units, still sees the run's `w:highlight` and is unchanged.

Every file is built in memory from invented text, and every expectation is written by hand from it.
"""

from __future__ import annotations

from datetime import date

import pytest

from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import ParsedCard, ParsedDocument
from debate_core.domain.search_index import read_aloud_text
from debate_core.domain.style_profile import RunEmphasis, StructuralUnit, StyleProfile
from debate_core.integrations.docx_parser.parser import DebateDocxParser
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml

SNAPSHOT = date(2026, 10, 27)
TAG = "Moratoria raise prices"
CITE = "Lindqvist 26, Senior Fellow, Synthetic Energy Review"
READ = "Supply freezes in place"
HIDDEN = " while the grid waits"
REST = " this year."


@pytest.fixture
def parser(profile: StyleProfile) -> DebateDocxParser:
    return DebateDocxParser(profile)


def card_with(parser: DebateDocxParser, hidden_colour: str) -> tuple[ParsedDocument, ParsedCard]:
    """A card whose body reads `READ` in cyan, `HIDDEN` in `hidden_colour`, then `REST` plain."""
    body = paragraph_xml(
        run_xml(READ, underline="single", highlight="cyan")
        + run_xml(HIDDEN, highlight=hidden_colour)
        + run_xml(REST)
    )
    content = build_docx(
        paragraph_xml(run_xml(TAG), style="Heading4")
        + paragraph_xml(run_xml("Lindqvist 26", character_style="Style13ptBold") + run_xml(CITE[12:]))
        + body
    )
    source = SourceDocument(
        sha256="0" * 64,
        byte_size=len(content),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.OPENEV,
        first_seen_snapshot=SNAPSHOT,
        last_seen_snapshot=SNAPSHOT,
    )
    document = parser.parse(content, source, source_path="invented.docx", camp="camp")
    assert isinstance(document, ParsedDocument), document
    (card,) = document.cards
    return document, card


def highlighted(card: ParsedCard) -> list[tuple[int, int, str | None]]:
    return [
        (span.start_offset, span.end_offset, span.highlight_color)
        for span in card.formatting_spans
        if span.emphasis is RunEmphasis.HIGHLIGHT
    ]


HIDDEN_RANGE = (len(READ), len(READ) + len(HIDDEN))


class TestTheParsersSpans:
    def test_a_white_run_carries_no_highlight_span(self, parser: DebateDocxParser) -> None:
        _, card = card_with(parser, "white")

        assert highlighted(card) == [(0, len(READ), "cyan")]

    @pytest.mark.parametrize("colour", ["lightGray", "black"])
    def test_lightgray_and_black_are_still_read_as_highlight(
        self, parser: DebateDocxParser, colour: str
    ) -> None:
        _, card = card_with(parser, colour)

        assert highlighted(card) == [(0, len(READ), "cyan"), (*HIDDEN_RANGE, colour)]

    def test_the_paragraph_is_read_as_it_was(self, parser: DebateDocxParser) -> None:
        """A white run still marks the paragraph as marked up for the classifier, as before."""
        document, card = card_with(parser, "white")

        body = document.sections[-1]
        assert (body.unit, body.match.rule_id) == (StructuralUnit.EVIDENCE, "heuristic-marked-up-body-text")
        assert card.evidence_text == READ + HIDDEN + REST


class TestSearchReadAloud:
    def test_white_text_is_not_read_aloud(self, parser: DebateDocxParser) -> None:
        _, card = card_with(parser, "white")

        assert read_aloud_text(card.evidence_text, card.formatting_spans) == READ

    def test_lightgray_text_still_is(self, parser: DebateDocxParser) -> None:
        _, card = card_with(parser, "lightGray")

        assert read_aloud_text(card.evidence_text, card.formatting_spans) == READ + HIDDEN
