"""`v1-e31-t23`: an in-round marker is never a cite.

A debater who stops reading a card in a round marks the place, `Marked 10:42`, and later copies
carry the mark. Capitalised with a two-digit hour, the cite-line heuristic took `Marked 10` for a name
and a two-digit year: the card ended at the marker, and the rest of its body became a card with no
tag whose cite was the marker, or, with nothing below it, a `CITE_ONLY` card of its own. The PM's
ruling of 2026-11-03 (M3): a marker word is never a cite's author name, so a line of one of the three
marker forms (`marker-word-and-clock-time`, `clock-time-alone`, `marker-word-alone`) reads as it
would otherwise. Markers are otherwise left as they are (M1): a marker in small print stays body.

Every file is built in memory from invented text, and every expectation is written by hand from it
(working agreement 6).
"""

from __future__ import annotations

from datetime import date

import pytest
from tests.evals.parser.cite_shapes import prose

from debate_core.application.ports.parsed_store import parse_version_directory
from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import CardCompleteness, FileSection, ParsedDocument
from debate_core.domain.style_profile import StructuralUnit, StyleProfile
from debate_core.integrations.docx_parser.parser import DOCX_PARSER_VERSION, DebateDocxParser
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml

SNAPSHOT = date(2026, 11, 3)
TAG, SECOND_TAG = "Reserve margins collapse under data centre demand", "Storage cannot close the gap"
CITE = "Okonkwo 26, invented professor of grid planning, invented report on reserve margins"
SECOND_CITE = "Ferreira 25, invented analyst, invented report on grid storage"
A1, A2 = prose(300, "Alpha reserve margins"), prose(300, "Alpha imports")
B1 = prose(300, "Bravo storage")
FULL = CardCompleteness.FULL


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


def plain(text: str, *, half_points: int = 22, bold: bool | None = None) -> str:
    return paragraph_xml(run_xml(text, half_points=half_points, bold=bold))


def body(text: str) -> str:
    return paragraph_xml(run_xml(text, underline="single", half_points=22))


def section_with(document: ParsedDocument, text: str) -> FileSection:
    return next(section for section in document.sections if section.text == text)


#: Marker lines the cite-line heuristic took for a name and a two-digit year.
MARKERS_READ_AS_CITES = ("Marked 10:42", "MARKED 11:05", "Stopped 12:30", "Marked 10:42 in the 1AR")


class TestTheDividedCard:
    @pytest.mark.parametrize("marker", MARKERS_READ_AS_CITES)
    def test_a_marker_between_two_body_paragraphs_leaves_the_card_whole(
        self, parser: DebateDocxParser, marker: str
    ) -> None:
        document = parse(parser, tag(TAG), plain(CITE), body(A1), plain(marker), body(A2))
        assert [(card.tag, card.full_cite, card.evidence_text) for card in document.cards] == [
            (TAG, CITE, f"{A1}\n{A2}")
        ]
        assert [card.completeness for card in document.cards] == [FULL]
        marker_line = section_with(document, marker)
        assert marker_line.unit is StructuralUnit.OTHER
        assert marker_line.match.rule_id == "heuristic-unclassified-paragraph"

    def test_a_marker_in_bold_is_no_cite_either(self, parser: DebateDocxParser) -> None:
        document = parse(parser, tag(TAG), plain(CITE), body(A1), plain("Marked 10:42", bold=True), body(A2))
        assert [card.evidence_text for card in document.cards] == [f"{A1}\n{A2}"]
        assert section_with(document, "Marked 10:42").unit is not StructuralUnit.CITE


class TestTheStrayCiteOnlyCard:
    def test_a_marker_at_the_end_of_a_body_makes_no_card_of_its_own(self, parser: DebateDocxParser) -> None:
        document = parse(
            parser,
            tag(TAG),
            plain(CITE),
            body(A1),
            plain("Marked 11:20"),
            tag(SECOND_TAG),
            plain(SECOND_CITE),
            body(B1),
        )
        assert [(card.tag, card.completeness) for card in document.cards] == [(TAG, FULL), (SECOND_TAG, FULL)]
        assert document.cards[0].evidence_text == A1
        assert section_with(document, "Marked 11:20").unit is StructuralUnit.OTHER


class TestWhereACiteStands:
    def test_a_bracketed_marker_under_a_tag_is_no_cite(self, parser: DebateDocxParser) -> None:
        document = parse(parser, tag(TAG), plain("[Marked 10:42]"), plain(CITE), body(A1))
        assert [(card.tag, card.full_cite, card.evidence_text) for card in document.cards] == [
            (TAG, CITE, A1)
        ]

    def test_a_marker_in_the_tag_style_under_a_tag_is_no_cite(self, parser: DebateDocxParser) -> None:
        document = parse(parser, tag(TAG), tag("Marked 10:42"), plain(CITE), body(A1))
        assert section_with(document, "Marked 10:42").unit is not StructuralUnit.CITE
        assert [card.full_cite for card in document.cards] == [CITE]


class TestMarkersLeftAsTheyAre:
    def test_a_marker_in_small_print_stays_in_the_body(self, parser: DebateDocxParser) -> None:
        """M1: a marker read as body is left there, the evidence text exactly as the file holds it."""
        document = parse(
            parser, tag(TAG), plain(CITE), body(A1), plain("Marked 10:42", half_points=16), body(A2)
        )
        assert [card.evidence_text for card in document.cards] == [f"{A1}\nMarked 10:42\n{A2}"]
        assert section_with(document, "Marked 10:42").match.rule_id == "heuristic-shrunk-body-text"


class TestRealCitesUnchanged:
    @pytest.mark.parametrize(
        "cite",
        [
            CITE,
            "Okonkwo 10, invented report on reserve margins",
            "Mark 19, invented professor of grid planning",
            "Marker 21, invented analyst of storage markets",
            "Stopford 24",
        ],
    )
    def test_a_name_and_year_cite_is_still_the_cards_cite(self, parser: DebateDocxParser, cite: str) -> None:
        document = parse(parser, tag(TAG), plain(cite), body(A1))
        assert [(card.tag, card.full_cite, card.evidence_text) for card in document.cards] == [
            (TAG, cite, A1)
        ]
        assert section_with(document, cite).match.rule_id == "heuristic-cite-line-author-year"


class TestTheParserVersion:
    def test_it_is_the_version_this_task_bumped_to_or_a_later_one(self) -> None:
        assert parse_version_directory(DOCX_PARSER_VERSION) >= parse_version_directory("2026.11.03-docx-8")

    def test_every_card_names_it(self, parser: DebateDocxParser) -> None:
        document = parse(parser, tag(TAG), plain(CITE), body(A1), plain("Marked 10:42"), body(A2))
        assert {card.provenance.parser_version for card in document.cards} == {DOCX_PARSER_VERSION}
