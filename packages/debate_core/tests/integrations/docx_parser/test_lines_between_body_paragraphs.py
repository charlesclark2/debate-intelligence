"""`v1-e31-t23`: a line read as nothing between two body paragraphs of one card (ruling N1).

`v1-e31-t19` counted the plain lines the classifier reads as nothing between two body paragraphs of
one card, and the coach's sample of 2026-11-03 found two strata of them the source's own text: 15
of 16 lines over 200 characters, or of 41 to 200 characters ending a sentence, and none a note by
whoever cut the card. The PM's ruling N1 (2026-11-03) reads those two as body. Everything else
between body paragraphs stays nothing: lines of 40 characters or fewer, lines of 41 to 200 that end
no sentence, omission notes, a number or punctuation alone, and in-round markers. A cite guard holds
a line as nothing when it carries a URL, a DOI or the word "accessed".

Every file is built in memory from invented text, and every expectation is written by hand from it
(working agreement 6).
"""

from __future__ import annotations

from datetime import date

import pytest
from tests.evals.parser.cite_shapes import prose

from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import FileSection, ParsedDocument
from debate_core.domain.style_profile import StructuralUnit, StyleProfile
from debate_core.integrations.docx_parser.parser import DebateDocxParser
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml

SNAPSHOT = date(2026, 11, 3)
TAG = "Reserve margins collapse under data centre demand"
CITE = "Okonkwo 26, invented professor of grid planning, invented report on reserve margins"
A1, A2, A3 = prose(300, "Alpha reserve margins"), prose(300, "Alpha imports"), prose(300, "Alpha exports")

SENTENCE = "The review found that reserve margins narrowed in every season of the year."
#: Over 200 characters and ending no sentence: a line the cutter broke off mid-sentence.
LONG_LINE = prose(230, "Planners in four regional markets") + " and the operators who answer for"
SENTENCE_RULE = "assembly-sentence-between-body-paragraphs"
LONG_LINE_RULE = "assembly-long-line-between-body-paragraphs"
UNCLASSIFIED = "heuristic-unclassified-paragraph"


@pytest.fixture
def parser(profile: StyleProfile) -> DebateDocxParser:
    return DebateDocxParser(profile)


def parse(parser: DebateDocxParser, *paragraphs: str) -> ParsedDocument:
    source = SourceDocument(
        sha256="f" * 64,
        byte_size=48_000,
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist="testcl26",
        first_seen_snapshot=SNAPSHOT,
        last_seen_snapshot=SNAPSHOT,
    )
    result = parser.parse(build_docx("".join(paragraphs)), source, source_path="invented.docx")
    assert isinstance(result, ParsedDocument), result
    return result


def tag(text: str) -> str:
    return paragraph_xml(run_xml(text), style="Heading4")


def plain(text: str) -> str:
    return paragraph_xml(run_xml(text, half_points=22))


def body(text: str) -> str:
    return paragraph_xml(run_xml(text, underline="single", half_points=22))


def section_with(document: ParsedDocument, text: str) -> FileSection:
    return next(section for section in document.sections if section.text == text)


def between_two_bodies(parser: DebateDocxParser, *lines: str) -> ParsedDocument:
    return parse(parser, tag(TAG), plain(CITE), body(A1), *(plain(line) for line in lines), body(A2))


def test_the_lines_are_the_lengths_their_strata_name() -> None:
    assert 41 <= len(SENTENCE) <= 200
    assert SENTENCE.endswith(".")
    assert len(LONG_LINE) > 200
    assert not LONG_LINE.endswith((".", "!", "?"))


class TestTheTwoStrataN1Reads:
    @pytest.mark.parametrize(("line", "rule"), [(SENTENCE, SENTENCE_RULE), (LONG_LINE, LONG_LINE_RULE)])
    def test_the_line_is_body_and_its_card_keeps_it(
        self, parser: DebateDocxParser, line: str, rule: str
    ) -> None:
        document = between_two_bodies(parser, line)
        assert [(card.tag, card.full_cite, card.evidence_text) for card in document.cards] == [
            (TAG, CITE, f"{A1}\n{line}\n{A2}")
        ]
        section = section_with(document, line)
        assert section.unit is StructuralUnit.EVIDENCE
        assert section.match.rule_id == f"{rule}:{UNCLASSIFIED}"
        assert [card.provenance.last_element_index for card in document.cards] == [4]

    def test_two_such_lines_together_are_both_body(self, parser: DebateDocxParser) -> None:
        document = between_two_bodies(parser, SENTENCE, LONG_LINE)
        assert [card.evidence_text for card in document.cards] == [f"{A1}\n{SENTENCE}\n{LONG_LINE}\n{A2}"]

    def test_a_line_between_body_paragraphs_further_down_the_card_is_read_too(
        self, parser: DebateDocxParser
    ) -> None:
        document = parse(parser, tag(TAG), plain(CITE), body(A1), body(A2), plain(SENTENCE), body(A3))
        assert [card.evidence_text for card in document.cards] == [f"{A1}\n{A2}\n{SENTENCE}\n{A3}"]


#: The five strata N1 leaves alone, one line each, written by hand.
LEFT_ALONE = {
    "40 characters or fewer, in capitals": "THE REGIONAL PICTURE",
    "40 characters or fewer, not in capitals": "Grid operators disagree.",
    "41 to 200 characters, not ending a sentence": "Reserve margins in four regional markets and planners",
    "an omission note": "[Table omitted]",
    "a number alone": "12",
    "punctuation alone": "…",
    "an in-round marker": "marked 3:05",
    "a time alone": "10:42",
}


class TestWhatN1LeavesAlone:
    @pytest.mark.parametrize("line", list(LEFT_ALONE.values()), ids=list(LEFT_ALONE))
    def test_the_line_stays_nothing(self, parser: DebateDocxParser, line: str) -> None:
        document = between_two_bodies(parser, line)
        assert [card.evidence_text for card in document.cards] == [f"{A1}\n{A2}"]
        section = section_with(document, line)
        assert (section.unit, section.match.rule_id) == (StructuralUnit.OTHER, UNCLASSIFIED)

    @pytest.mark.parametrize(
        "line",
        [
            "The review is at https://example.invalid/grid-review and found that margins narrowed.",
            "The review, www.example.invalid/grid-review, found that margins narrowed every season.",
            "The review found that margins narrowed every season, doi:10.5555/grid.2026.014.",
            "The review found that margins narrowed every season (10.5555/grid.2026.014).",
            "Invented Journal of Grid Studies, ACCESSED 3 March 2026, on reserve margins.",
        ],
        ids=["a link", "a web address", "a doi", "a bare doi", "accessed"],
    )
    def test_the_cite_guard_holds_a_sentence_that_carries_a_cite_mark(
        self, parser: DebateDocxParser, line: str
    ) -> None:
        assert 41 <= len(line) <= 200
        assert line.endswith(".")
        document = between_two_bodies(parser, line)
        assert [card.evidence_text for card in document.cards] == [f"{A1}\n{A2}"]
        assert section_with(document, line).unit is StructuralUnit.OTHER

    def test_the_cite_guard_holds_a_long_line_too(self, parser: DebateDocxParser) -> None:
        line = LONG_LINE + " https://example.invalid/grid-review"
        document = between_two_bodies(parser, line)
        assert section_with(document, line).unit is StructuralUnit.OTHER

    def test_a_real_cite_between_two_bodies_is_still_a_cite(self, parser: DebateDocxParser) -> None:
        second_cite = "Ferreira 25, invented analyst, invented report on grid storage"
        document = between_two_bodies(parser, second_cite)
        assert [(card.tag, card.full_cite, card.evidence_text) for card in document.cards] == [
            (TAG, CITE, A1),
            (None, second_cite, A2),
        ]
        assert section_with(document, second_cite).unit is StructuralUnit.CITE


class TestWhereN1DoesNotReach:
    def test_a_sentence_after_the_last_body_paragraph_stays_nothing(self, parser: DebateDocxParser) -> None:
        document = parse(parser, tag(TAG), plain(CITE), body(A1), plain(SENTENCE), tag("A second tag"))
        assert [card.evidence_text for card in document.cards] == [A1]
        assert section_with(document, SENTENCE).unit is StructuralUnit.OTHER

    def test_a_sentence_before_the_body_stays_nothing(self, parser: DebateDocxParser) -> None:
        document = parse(parser, tag(TAG), plain(CITE), plain(SENTENCE), body(A1))
        assert [card.evidence_text for card in document.cards] == [A1]
        assert section_with(document, SENTENCE).unit is StructuralUnit.OTHER

    def test_a_sentence_between_the_bodies_of_two_cards_stays_nothing(self, parser: DebateDocxParser) -> None:
        second_cite = "Ferreira 25, invented analyst, invented report on grid storage"
        document = parse(
            parser, tag(TAG), plain(CITE), body(A1), plain(SENTENCE), plain(second_cite), body(A2)
        )
        assert [card.evidence_text for card in document.cards] == [A1, A2]
        assert section_with(document, SENTENCE).unit is StructuralUnit.OTHER

    def test_a_prose_paragraph_is_read_as_before(self, parser: DebateDocxParser) -> None:
        """A line of 200 characters or more that ends a sentence was body already."""
        document = between_two_bodies(parser, prose(250, "Bravo storage"))
        assert (
            section_with(document, prose(250, "Bravo storage")).match.rule_id == "heuristic-prose-paragraph"
        )
