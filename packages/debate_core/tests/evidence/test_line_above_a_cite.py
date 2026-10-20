"""The line above a cite, described in counts (`v1-e31-t24`).

One invented file in (7)'s formatting: its document defaults make every run bold at 13 pt, and its
bodies and cites switch bold off and set their size, as a Google Docs export of such a file does.
Its lines above cites are each written to be one case, and every expectation below is written by
hand from what the file was built to hold (working agreement 6):

====  =========================================================  =====================================
 at    paragraph                                                  read by the parser (docx-5) as
====  =========================================================  =====================================
  0    a tag in `Heading4`                                        tag
  1    cite A, bracketed                                          cite, under the tag
  2    body A                                                     body
  3    (7)'s line: nothing set, part underlined                   body, the last of card A
  4    cite B, bracketed                                          cite, opening a card with no tag
  5    body B                                                     body
  6    a line in bold of its own, no size, not underlined         nothing
  7    cite C, bracketed                                          cite, opening a card with no tag
  8    body C                                                     body
  9    a plain line: bold off, 11 pt                              nothing
 10    cite D, bracketed                                          cite, opening a card with no tag
 11    body D                                                     body
 12    a line naming a source within its first 40 characters      body
 13    cite E, bracketed                                          cite, opening a card with no tag
 14    body E                                                     body
 15    a line of over 300 characters, nothing set                 body
 16    cite F, bracketed                                          cite, opening a card with no tag
 17    body F                                                     body
 18    a line with nothing set                                    body
 19    cite G, a short name-and-year line (not bracketed)         cite, opening a card with no tag
 20    body G                                                     body
 21    a line with nothing set, not underlined                    nothing, inside card G
 22    body G, continued                                          body
 23    a tag in `Heading4`                                        tag
 24    cite H, bracketed                                          cite, under the tag
 25    body H                                                     body
====  =========================================================  =====================================
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from tests.evals.parser.cite_shapes import SOURCE, prose

from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import ParsedDocument
from debate_core.domain.style_profile import StructuralUnit
from debate_core.evidence.line_above_a_cite import (
    Boldness,
    LineAboveACite,
    LineSize,
    bold_lines_read_as_body_or_nothing,
    line_above,
    lines_above_cites,
    tally_bold_lines,
    tally_lines_above_cites,
)
from debate_core.evidence.style_classifier import ParagraphDescription
from debate_core.integrations.docx_parser import DebateDocxParser
from debate_core.integrations.docx_parser.runs import as_word_shows_it
from debate_core.testing.docx_builder import W_NAMESPACE, build_docx, paragraph_xml, run_xml

#: The file's styles: bold at 13 pt by default, as (7)'s are.
BOLD_DEFAULTS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<w:styles xmlns:w="{W_NAMESPACE}">'
    '<w:docDefaults><w:rPrDefault><w:rPr><w:b w:val="1"/><w:sz w:val="26"/></w:rPr></w:rPrDefault>'
    "</w:docDefaults>"
    '<w:style w:type="paragraph" w:styleId="Normal" w:default="1"><w:name w:val="normal"/></w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading4"><w:name w:val="heading 4"/>'
    '<w:basedOn w:val="Normal"/></w:style>'
    "</w:styles>"
)

#: Credentials long enough that the cite is past the short cite-line rule's 400 characters.
CREDENTIALS = "Adaeze Okonkwo is an invented professor of grid planning at an invented university; " * 5


def plain(text: str, **formatting: Any) -> str:
    """A run with bold switched off and its size set, as the file's bodies and cites write theirs."""
    return run_xml(text, bold=False, half_points=22, **formatting)


def bracketed_cite(name: str) -> str:
    return paragraph_xml(plain(f"{name} [{CREDENTIALS}{SOURCE}] KR"))


def body(stem: str) -> str:
    return paragraph_xml(plain(prose(400, f"{stem} "), underline="single"))


def nothing_set(text: str, *, underlined_tail: str = "") -> str:
    """A line whose runs say nothing of bold or size: bold at 13 pt in Word, by the defaults."""
    tail = run_xml(underlined_tail, underline="single") if underlined_tail else ""
    return paragraph_xml(run_xml(text) + tail)


LONG_LINE = "Grid operators warn that " + "reserve margins thin every winter and " * 8 + "fall."

SEVEN_LIKE_FILE = build_docx(
    paragraph_xml(run_xml("First tag"), style="Heading4")
    + bracketed_cite("Okonkwo 26")
    + body("Alpha")
    + nothing_set("Demand outruns ", underlined_tail="new generation")
    + bracketed_cite("Ferreira 25")
    + body("Bravo")
    + paragraph_xml(run_xml("Reserve margins fall", bold=True))
    + bracketed_cite("Lindqvist 24")
    + body("Charlie")
    + paragraph_xml(plain("A note left plain"))
    + bracketed_cite("Achebe 23")
    + body("Delta")
    + nothing_set("As shown by Lindqvist 2019 ", underlined_tail="margins fall")
    + bracketed_cite("Tanaka 22")
    + body("Echo")
    + nothing_set(LONG_LINE, underlined_tail=" again")
    + bracketed_cite("Mensah 21")
    + body("Foxtrot")
    + nothing_set("Imports cannot ", underlined_tail="close the gap")
    + paragraph_xml(plain("Nakamura 20, invented report on grid imports"))
    + body("Golf")
    + nothing_set("A line in the middle of a body")
    + body("Hotel")
    + paragraph_xml(run_xml("Last tag"), style="Heading4")
    + bracketed_cite("Ibsen 19")
    + body("India"),
    styles_xml=BOLD_DEFAULTS,
)


class _ReadingParser(DebateDocxParser):
    """The parser, keeping each paragraph as read and as Word shows it."""

    def __init__(self) -> None:
        super().__init__()
        self.descriptions: list[ParagraphDescription] = []
        self.shown: list[ParagraphDescription] = []

    def _read_sections(self, package: Any) -> Any:  # pyright: ignore[reportIncompatibleMethodOverride]
        sections = super()._read_sections(package)  # pyright: ignore[reportPrivateUsage]
        self.descriptions = [section.read.description for section in sections]
        self.shown = [as_word_shows_it(description, package) for description in self.descriptions]
        return sections


@pytest.fixture(scope="module")
def parsed() -> tuple[_ReadingParser, ParsedDocument]:
    parser = _ReadingParser()
    snapshot = date(2026, 10, 20)
    source = SourceDocument(
        sha256="a" * 64,
        byte_size=len(SEVEN_LIKE_FILE),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist="hspf26",
        first_seen_snapshot=snapshot,
        last_seen_snapshot=snapshot,
    )
    document = parser.parse(SEVEN_LIKE_FILE, source, source_path="invented.docx")
    assert isinstance(document, ParsedDocument)
    return parser, document


def lines(parsed: tuple[_ReadingParser, ParsedDocument], **options: Any) -> dict[int, LineAboveACite]:
    parser, document = parsed
    found = lines_above_cites(
        parser.descriptions, document.sections, document.cards, parser.profile, shown=parser.shown, **options
    )
    return dict(found)


def test_the_file_reads_as_the_table_says(parsed: tuple[_ReadingParser, ParsedDocument]) -> None:
    _, document = parsed
    units = [section.unit for section in document.sections]
    tag, cite, body_, nothing = (
        StructuralUnit.TAG,
        StructuralUnit.CITE,
        StructuralUnit.EVIDENCE,
        StructuralUnit.OTHER,
    )
    assert units == [
        tag, cite, body_, body_, cite, body_, nothing, cite, body_, nothing, cite, body_, body_, cite,
        body_, body_, cite, body_, body_, cite, body_, nothing, body_, tag, cite, body_,
    ]  # fmt: skip
    assert [card.tag for card in document.cards] == [
        "First tag",
        None,
        None,
        None,
        None,
        None,
        None,
        "Last tag",
    ]


class TestTheLineAboveEachBracketedCite:
    def test_only_bracketed_cites_by_default(self, parsed: tuple[_ReadingParser, ParsedDocument]) -> None:
        assert sorted(lines(parsed)) == [1, 4, 7, 10, 13, 16, 24]
        assert {line.cite_rule for line in lines(parsed).values()} == {"heuristic-cite-line-bracketed"}

    def test_sevens_line_is_bold_only_as_word_shows_it(
        self, parsed: tuple[_ReadingParser, ParsedDocument]
    ) -> None:
        assert lines(parsed)[4] == LineAboveACite(
            cite_rule="heuristic-cite-line-bracketed",
            cite_opens_a_card_with_no_tag=True,
            line_unit=StructuralUnit.EVIDENCE,
            line_rule="heuristic-marked-up-body-text",
            line_read_by_a_heuristic=True,
            line_behind_an_unmapped_style=False,
            boldness=Boldness.NONE,
            boldness_as_word_shows_it=Boldness.ALL,
            in_a_tag_style=False,
            size=LineSize.NOT_STATED,
            size_as_word_shows_it=LineSize.READING_SIZE_OR_LARGER,
            underlined=True,
            highlighted=False,
            no_longer_than_a_heading=True,
            names_a_source_at_its_head=False,
            ends_the_card_above=True,
            blank_lines_between=False,
        )

    def test_a_line_bold_of_its_own_with_no_size_is_read_as_nothing(
        self, parsed: tuple[_ReadingParser, ParsedDocument]
    ) -> None:
        line = lines(parsed)[7]
        assert (line.line_unit, line.line_rule) == (StructuralUnit.OTHER, "heuristic-unclassified-paragraph")
        assert (line.boldness, line.boldness_as_word_shows_it) == (Boldness.ALL, Boldness.ALL)
        assert (line.size, line.size_as_word_shows_it) == (
            LineSize.NOT_STATED,
            LineSize.READING_SIZE_OR_LARGER,
        )
        assert not line.ends_the_card_above
        assert line.is_the_shape and line.the_proposed_rule_takes

    def test_which_lines_are_the_shape_and_which_the_proposed_rule_takes(
        self, parsed: tuple[_ReadingParser, ParsedDocument]
    ) -> None:
        found = lines(parsed)
        assert {at for at, line in found.items() if line.is_the_shape} == {4, 7, 13, 16}
        assert {at for at, line in found.items() if line.the_proposed_rule_takes} == {4, 7}
        assert found[13].names_a_source_at_its_head and found[13].no_longer_than_a_heading
        assert not found[16].no_longer_than_a_heading and not found[16].names_a_source_at_its_head
        assert found[10].boldness_as_word_shows_it is Boldness.NONE
        assert found[10].size is LineSize.READING_SIZE_OR_LARGER

    def test_a_cite_under_a_tag_has_the_tag_above_it(
        self, parsed: tuple[_ReadingParser, ParsedDocument]
    ) -> None:
        for at in (1, 24):
            line = lines(parsed)[at]
            assert line.line_unit is StructuralUnit.TAG
            assert not line.cite_opens_a_card_with_no_tag
            assert not line.is_the_shape and not line.the_proposed_rule_takes

    def test_every_cite_when_asked(self, parsed: tuple[_ReadingParser, ParsedDocument]) -> None:
        found = lines(parsed, cite_rules=None)
        assert sorted(found) == [1, 4, 7, 10, 13, 16, 19, 24]
        assert found[19].cite_rule == "heuristic-cite-line-author-year"
        assert found[19].the_proposed_rule_takes

    def test_without_what_word_shows_only_bold_of_its_own_counts(
        self, parsed: tuple[_ReadingParser, ParsedDocument]
    ) -> None:
        parser, document = parsed
        found = dict(
            lines_above_cites(parser.descriptions, document.sections, document.cards, parser.profile)
        )
        assert {at for at, line in found.items() if line.is_the_shape} == {7}

    def test_the_tally(self, parsed: tuple[_ReadingParser, ParsedDocument]) -> None:
        tally = tally_lines_above_cites(lines(parsed).values())
        assert tally["cites"] == 7
        assert tally["cites_opening_a_card_with_no_tag"] == 5
        assert tally["line_above_read_as"] == {"EVIDENCE": 3, "OTHER": 2, "TAG": 2}
        assert tally["line_above_read_as_body_or_nothing"] == 5
        assert tally["the_proposed_rule_takes"] == 2
        assert tally["the_proposed_rule_takes_lines_bold_only_by_inheritance"] == 1
        assert tally["read_as_body_or_nothing_and_not_the_shape_by_bold_as_word_shows_it"] == {"not bold": 1}
        shape = tally["the_shape"]
        assert isinstance(shape, dict)
        assert shape["lines"] == 4
        assert shape["read_as"] == {"EVIDENCE": 3, "OTHER": 1}
        assert shape["bold_as_the_reader_sees_it"] == {"bold throughout": 1, "not bold": 3}
        assert shape["bold_as_word_shows_it"] == {"bold throughout": 4}
        assert shape["size_as_the_reader_sees_it"] == {"no size stated": 4}
        assert shape["no_longer_than_a_heading"] == {"False": 1, "True": 3}
        assert shape["names_a_source_at_its_head"] == {"False": 3, "True": 1}
        assert shape["ends_the_card_above"] == {"False": 1, "True": 3}
        assert shape["underlined"] == {"False": 1, "True": 3}


class TestBoldLinesReadAsBodyOrNothing:
    def test_every_line_word_shows_as_a_bold_heading(
        self, parsed: tuple[_ReadingParser, ParsedDocument]
    ) -> None:
        parser, document = parsed
        found = bold_lines_read_as_body_or_nothing(
            parser.descriptions, parser.shown, document.sections, document.cards, parser.profile
        )
        assert [line.position for line in found] == [3, 6, 12, 18, 21]
        assert [line.above_a_cite for line in found] == [True, True, True, True, False]
        assert [line.bold_as_the_reader_sees_it for line in found] == [False, True, False, False, False]
        assert tally_bold_lines(found) == {
            "lines": 5,
            "directly_above_a_cite": 4,
            "directly_above_a_cite_opening_a_card_with_no_tag": 4,
            "bold_as_the_reader_sees_it": 1,
            "behind_a_style_that_maps_to_no_unit": 0,
        }


def test_the_line_above_steps_over_blank_lines(parsed: tuple[_ReadingParser, ParsedDocument]) -> None:
    _, document = parsed
    assert line_above(document.sections, 0) is None
    assert line_above(document.sections, 4) == 3
