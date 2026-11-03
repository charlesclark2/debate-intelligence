"""In-round markers and the short lines between body paragraphs, described in counts (`v1-e31-t23`).

Every line here is invented, and every expectation is written by hand from what the line or the
file was built to hold (working agreement 6). The file holds a marker read each of the three ways
`2026.10.27-docx-7` read one, when the counts were taken. `2026.11.03-docx-8` reads no marker as a
cite (the PM's ruling M3), so the file is parsed as `docx-7` read it, that rule switched off
(:func:`parse_as_docx_7`); the last test reads it as `docx-8` does.

====  ===========================================================  =========================================
 at    paragraph                                                    read by the parser as
====  ===========================================================  =========================================
  0    a tag in `Heading4`                                          tag of card 0
  1    a short name-and-year cite                                   cite
  2    body A1, underlined                                          body
  3    `marked 3:05`, plain at reading size                         nothing, between two body paragraphs
  4    body A2, underlined                                          body, the end of card 0
  5    `Marked 10:42`, plain at reading size                        a cite: `Marked 10` is a name and a year;
                                                                    it opens card 1, with no tag
  6    body A3, underlined                                          body of card 1
  7    `MARKED`, plain at 8 pt                                      body (shrunk), the end of card 1
  8    a tag in `Heading4`                                          tag of card 2
  9    a short name-and-year cite                                   cite
 10    `10:42`, plain at reading size                               nothing, before card 2's body
 11    body B1, underlined, a line break, `marked 3:05 pm` at 8 pt  body: two lines
 12    body B2, underlined, holding `marked at 11:15` inside it     body, the end of card 2
 13    `p. 12`, plain at reading size                               nothing, after card 2's body
 14    a tag in `Heading4`                                          tag of card 3
 15    a short name-and-year cite                                   cite
 16    body C, underlined                                           body, card 3's only line
 17    `Marked 11:20`, plain at reading size                        a cite: card 4, with no tag and no body
 18    a plain line of a few words                                  nothing, elsewhere
====  ===========================================================  =========================================
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import date

import pytest
from tests.evals.parser.cite_shapes import prose

from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import CardCompleteness, ParsedDocument
from debate_core.evidence import style_classifier
from debate_core.evidence.fingerprints import card_fingerprint, fingerprint_text
from debate_core.evidence.in_round_markers import (
    MARKER_FORMS,
    DescribedLine,
    LineForm,
    LinePlace,
    MarkerFreeBody,
    Reading,
    describe_lines,
    length_band,
    line_form,
    marker_free_bodies,
)
from debate_core.integrations.docx_parser import parser as parser_module
from debate_core.integrations.docx_parser.parser import DebateDocxParser
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml


@pytest.mark.parametrize(
    ("line", "form"),
    [
        ("Marked 10:42", LineForm.MARKER_WORD_AND_CLOCK_TIME),
        ("[marked at 3:05 pm]", LineForm.MARKER_WORD_AND_CLOCK_TIME),
        ("**MARKED 9:07 AM**", LineForm.MARKER_WORD_AND_CLOCK_TIME),
        ("10:42 marked", LineForm.MARKER_WORD_AND_CLOCK_TIME),
        ("card marked 10:42 in the 1AR", LineForm.MARKER_WORD_AND_CLOCK_TIME),
        ("stopped 23:59", LineForm.MARKER_WORD_AND_CLOCK_TIME),
        ("10:42", LineForm.CLOCK_TIME_ALONE),
        ("(3:05 PM)", LineForm.CLOCK_TIME_ALONE),
        ("12:30:15", LineForm.CLOCK_TIME_ALONE),
        ("MARKED", LineForm.MARKER_WORD_ALONE),
        ("*mark here*", LineForm.MARKER_WORD_ALONE),
        ("card marked", LineForm.MARKER_WORD_ALONE),
        ("stopped reading here", LineForm.MARKER_WORD_ALONE),
        ("Marked increases in reserve margins", LineForm.MARKER_WORD_OPENS_A_SHORT_LINE),
        ("marking the second paragraph", LineForm.MARKER_WORD_OPENS_A_SHORT_LINE),
        ("Reserve margins fall MARKED 10:42", LineForm.MARKER_INSIDE_A_LINE),
        (prose(120, "The grid holds") + " marked at 11:15 " + prose(80), LineForm.MARKER_INSIDE_A_LINE),
        ("12", LineForm.NUMBER_ALONE),
        ("p. 12", LineForm.NUMBER_ALONE),
        ("Page 4", LineForm.NUMBER_ALONE),
        ("[4]", LineForm.NUMBER_ALONE),
        ("…", LineForm.NO_LETTER_OR_DIGIT),
        ("[...]", LineForm.NO_LETTER_OR_DIGIT),
        ("***", LineForm.NO_LETTER_OR_DIGIT),
        ("[Table omitted]", LineForm.OMISSION_NOTE),
        ("Text omitted", LineForm.OMISSION_NOTE),
        ("The market closed at 10:42", LineForm.NO_MARKER_FORM),
        ("Reserve margins after the moratorium", LineForm.NO_MARKER_FORM),
        ("Ratios of 3:1 hold", LineForm.NO_MARKER_FORM),
        ("Marked " + "x" * 60, LineForm.NO_MARKER_FORM),
        ("Marked 10:42 " + "x" * 50, LineForm.MARKER_INSIDE_A_LINE),
    ],
)
def test_each_line_has_the_form_its_pattern_names(line: str, form: LineForm) -> None:
    assert line_form(line) is form


def test_the_marker_forms_are_the_four_whole_line_forms() -> None:
    assert MARKER_FORMS == (
        LineForm.MARKER_WORD_AND_CLOCK_TIME,
        LineForm.CLOCK_TIME_ALONE,
        LineForm.MARKER_WORD_ALONE,
        LineForm.MARKER_WORD_OPENS_A_SHORT_LINE,
    )


@pytest.mark.parametrize(
    ("length", "band"),
    [
        (1, "40 characters or fewer"),
        (40, "40 characters or fewer"),
        (41, "41 to 100"),
        (200, "101 to 200"),
        (201, "201 to 400"),
        (1_000, "401 to 1,000"),
        (4_000, "1,001 to 4,000"),
        (4_001, "over 4,000"),
    ],
)
def test_the_length_bands_are_v1_e31_t19s(length: int, band: str) -> None:
    assert length_band("  " + "x" * length + "  ") == band


def plain(text: str, *, half_points: int = 22) -> str:
    return run_xml(text, half_points=half_points)


def body(text: str) -> str:
    return run_xml(text, underline="single", half_points=22)


LINE_BREAK = "<w:r><w:br/></w:r>"
A1, A2, A3 = prose(300, "Alpha reserve margins"), prose(300, "Alpha imports"), prose(300, "Alpha exports")
B1, B2_HEAD, B2_TAIL = prose(300, "Bravo storage"), prose(150, "Bravo peak demand"), prose(150, "Bravo")
B2 = f"{B2_HEAD} marked at 11:15 {B2_TAIL}"
C = prose(300, "Charlie transmission")

FILE = build_docx(
    paragraph_xml(plain("Grid tag one"), style="Heading4")
    + paragraph_xml(plain("Okonkwo 26, invented report on grid reserves"))
    + paragraph_xml(body(A1))
    + paragraph_xml(plain("marked 3:05"))
    + paragraph_xml(body(A2))
    + paragraph_xml(plain("Marked 10:42"))
    + paragraph_xml(body(A3))
    + paragraph_xml(plain("MARKED", half_points=16))
    + paragraph_xml(plain("Grid tag two"), style="Heading4")
    + paragraph_xml(plain("Ferreira 25, invented report on grid storage"))
    + paragraph_xml(plain("10:42"))
    + paragraph_xml(body(B1) + LINE_BREAK + plain("marked 3:05 pm", half_points=16))
    + paragraph_xml(body(B2))
    + paragraph_xml(plain("p. 12"))
    + paragraph_xml(plain("Grid tag three"), style="Heading4")
    + paragraph_xml(plain("Achebe 23, invented report on transmission"))
    + paragraph_xml(body(C))
    + paragraph_xml(plain("Marked 11:20"))
    + paragraph_xml(plain("Reserve margins after the moratorium"))
)


def no_line_is_a_marker(_line: str) -> bool:
    return False


def parse_as_docx_7(parse: Callable[[], ParsedDocument]) -> ParsedDocument:
    """`parse()` with `docx-8`'s marker rule switched off: an in-round marker may be read as a cite."""
    with pytest.MonkeyPatch.context() as patch:
        for module in (style_classifier, parser_module):
            patch.setattr(module, "is_an_in_round_marker", no_line_is_a_marker)
        return parse()


def parsed_file() -> ParsedDocument:
    snapshot = date(2026, 11, 2)
    source = SourceDocument(
        sha256="a" * 64,
        byte_size=len(FILE),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist="testcl26",
        first_seen_snapshot=snapshot,
        last_seen_snapshot=snapshot,
    )
    parsed = DebateDocxParser().parse(FILE, source, source_path="invented.docx")
    assert isinstance(parsed, ParsedDocument)
    return parsed


@pytest.fixture(scope="module")
def document() -> ParsedDocument:
    return parse_as_docx_7(parsed_file)


def test_the_file_reads_as_the_table_above_says(document: ParsedDocument) -> None:
    assert all(201 <= len(text) <= 400 for text in (A1, A2, A3, B1, C))
    assert 401 <= len(B2) <= 1_000
    assert [card.tag for card in document.cards] == [
        "Grid tag one",
        None,
        "Grid tag two",
        "Grid tag three",
        None,
    ]
    assert [
        (card.provenance.first_element_index, card.provenance.last_element_index) for card in document.cards
    ] == [(0, 4), (5, 7), (8, 12), (14, 16), (17, 17)]
    assert [section.unit.value for section in document.sections] == [
        "TAG", "CITE", "EVIDENCE", "OTHER", "EVIDENCE", "CITE", "EVIDENCE", "EVIDENCE",
        "TAG", "CITE", "OTHER", "EVIDENCE", "EVIDENCE", "OTHER",
        "TAG", "CITE", "EVIDENCE", "CITE", "OTHER",
    ]  # fmt: skip
    assert [card.evidence_text for card in document.cards] == [
        f"{A1}\n{A2}",
        f"{A3}\nMARKED",
        f"{B1}\nmarked 3:05 pm\n{B2}",
        C,
        "",
    ]
    assert document.cards[4].completeness is CardCompleteness.CITE_ONLY


def described(
    reading: Reading, form: LineForm, place: LinePlace, card: int | None, rule: str, band: str
) -> DescribedLine:
    return DescribedLine(
        reading=reading,
        form=form,
        place=place,
        card=card,
        rule=rule,
        length_band=band,
        ends_a_sentence=form is LineForm.NO_MARKER_FORM and reading is Reading.BODY,
        in_capitals=form is LineForm.MARKER_WORD_ALONE,
    )


def test_every_line_is_described_by_its_form_and_its_place(document: ParsedDocument) -> None:
    body_, nothing, cite = Reading.BODY, Reading.NOTHING, Reading.CITE
    marked_up, shrunk = "heuristic-marked-up-body-text", "heuristic-shrunk-body-text"
    unclassified, cite_line = "heuristic-unclassified-paragraph", "heuristic-cite-line-author-year"
    short, cite_long, long_, longer = "40 characters or fewer", "41 to 100", "201 to 400", "401 to 1,000"
    no_form, word_and_time = LineForm.NO_MARKER_FORM, LineForm.MARKER_WORD_AND_CLOCK_TIME
    assert describe_lines(document.sections, document.cards) == [
        described(body_, no_form, LinePlace.BODY_FIRST_LINE, 0, marked_up, long_),
        described(body_, no_form, LinePlace.BODY_LAST_LINE, 0, marked_up, long_),
        described(body_, no_form, LinePlace.BODY_FIRST_LINE, 1, marked_up, long_),
        described(body_, LineForm.MARKER_WORD_ALONE, LinePlace.BODY_LAST_LINE, 1, shrunk, short),
        described(body_, no_form, LinePlace.BODY_FIRST_LINE, 2, marked_up, long_),
        described(body_, word_and_time, LinePlace.BODY_INSIDE, 2, marked_up, short),
        replace(
            described(body_, LineForm.MARKER_INSIDE_A_LINE, LinePlace.BODY_LAST_LINE, 2, marked_up, longer),
            ends_a_sentence=True,
        ),
        described(body_, no_form, LinePlace.BODY_ONLY_LINE, 3, marked_up, long_),
        described(nothing, word_and_time, LinePlace.BETWEEN_BODY_PARAGRAPHS, 0, unclassified, short),
        described(nothing, LineForm.CLOCK_TIME_ALONE, LinePlace.BEFORE_A_BODY, 2, unclassified, short),
        described(nothing, LineForm.NUMBER_ALONE, LinePlace.AFTER_A_BODY, 2, unclassified, short),
        described(nothing, no_form, LinePlace.ELSEWHERE, None, unclassified, short),
        described(cite, no_form, LinePlace.ELSEWHERE, None, cite_line, cite_long),
        described(cite, word_and_time, LinePlace.CITE_BELOW_A_BODY_OPENING_A_CARD, 1, cite_line, short),
        described(cite, no_form, LinePlace.ELSEWHERE, None, cite_line, cite_long),
        described(cite, no_form, LinePlace.ELSEWHERE, None, cite_line, cite_long),
        described(cite, word_and_time, LinePlace.CITE_BELOW_A_BODY_ALONE, 4, cite_line, short),
    ]  # fmt: skip


def fingerprints(*bodies: str) -> tuple[str, ...]:
    return tuple(fingerprint_text(text) for text in bodies)


def test_marker_free_bodies_leave_out_the_lines_and_join_the_halves_of_every_form(
    document: ParsedDocument,
) -> None:
    card_0, card_1, card_2 = fingerprints(f"{A1}\n{A2}", f"{A3}\nMARKED", f"{B1}\nmarked 3:05 pm\n{B2}")
    assert marker_free_bodies(document.sections, document.cards, MARKER_FORMS) == [
        # `Marked 10:42` read as a cite divides card 0's body; `MARKED` ends it.
        MarkerFreeBody(
            exact_fingerprints=(card_0, card_1), fingerprint=fingerprint_text(f"{A1}\n{A2}\n{A3}")
        ),
        # The marker inside B2 is no whole line, so B2 stays. `Marked 11:20` alone changes no body.
        MarkerFreeBody(exact_fingerprints=(card_2,), fingerprint=fingerprint_text(f"{B1}\n{B2}")),
    ]


def test_marker_free_bodies_leave_out_only_the_forms_asked_for(document: ParsedDocument) -> None:
    card_1, card_2 = fingerprints(f"{A3}\nMARKED", f"{B1}\nmarked 3:05 pm\n{B2}")
    sections, cards = document.sections, document.cards
    assert marker_free_bodies(sections, cards, [LineForm.CLOCK_TIME_ALONE]) == []
    assert marker_free_bodies(sections, cards, [LineForm.MARKER_WORD_ALONE]) == [
        MarkerFreeBody(exact_fingerprints=(card_1,), fingerprint=fingerprint_text(A3))
    ]
    assert marker_free_bodies(sections, cards, [LineForm.MARKER_INSIDE_A_LINE]) == [
        MarkerFreeBody(exact_fingerprints=(card_2,), fingerprint=fingerprint_text(f"{B1}\nmarked 3:05 pm"))
    ]


def test_an_exact_fingerprint_is_the_cards_own(document: ParsedDocument) -> None:
    assert [card_fingerprint(card).exact_fingerprint for card in document.cards[:4]] == list(
        fingerprints(f"{A1}\n{A2}", f"{A3}\nMARKED", f"{B1}\nmarked 3:05 pm\n{B2}", C)
    )


def test_at_docx_8_no_marker_is_a_cite_and_the_divided_card_is_whole() -> None:
    document = parsed_file()
    assert [card.tag for card in document.cards] == ["Grid tag one", "Grid tag two", "Grid tag three"]
    assert document.cards[0].evidence_text == f"{A1}\n{A2}\n{A3}\nMARKED"
    lines = describe_lines(document.sections, document.cards)
    assert not [
        line for line in lines if line.reading is Reading.CITE and line.form is not LineForm.NO_MARKER_FORM
    ]
    assert [(line.form, line.place) for line in lines if line.reading is Reading.NOTHING][:2] == [
        (LineForm.MARKER_WORD_AND_CLOCK_TIME, LinePlace.BETWEEN_BODY_PARAGRAPHS),
        (LineForm.MARKER_WORD_AND_CLOCK_TIME, LinePlace.BETWEEN_BODY_PARAGRAPHS),
    ]
    card_0 = fingerprint_text(f"{A1}\n{A2}\n{A3}\nMARKED")
    assert marker_free_bodies(document.sections, document.cards, MARKER_FORMS)[0] == MarkerFreeBody(
        exact_fingerprints=(card_0,), fingerprint=fingerprint_text(f"{A1}\n{A2}\n{A3}")
    )
