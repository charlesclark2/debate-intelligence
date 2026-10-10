"""What the first full-corpus parse found, each finding rebuilt as an invented file (`v1-e31-t09`).

The first parse of the whole corpus (`docs/data/caselist-parse-report.md`) refused 23 files as
`FORBIDDEN_XML_CONSTRUCT` and stored 15,528 cards with an empty tag. Read in place, by counts and
construct names only, they came to three rules:

* **The refusal's scan read prose as markup.** It looked for `SYSTEM "` and `PUBLIC '` anywhere in
  a part, so a card whose text says *the system "works"* was refused as if it declared an external
  entity. None of the 23 files holds a `DOCTYPE` or an entity declaration.
* **A body paragraph guessed to be a cite split its card.** A paragraph inside a card's body that
  holds an ellipsis and a name with a year, or that opens *In 2019*, comes back from the
  classifier as a cite. The assembly closed the card there and opened another with no tag.
* **A blank line in a heading style was read as a heading.** An empty `Heading4` opened a card
  with an empty tag and demoted the real tag above it to an analytic.

Every file here is built in memory from invented text, in the formatting structure the real files
have. The expected cards are written by hand from what each file holds, never taken from the
parser (working agreement 6).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from lxml import etree

from debate_core.application.ports.parsed_store import parse_version_directory
from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import (
    CardCompleteness,
    ParsedDocument,
    ParseFailure,
    ParseFailureReason,
)
from debate_core.domain.style_profile import StructuralUnit, StyleMatchSource, StyleProfile
from debate_core.integrations.docx_parser import package as docx_package
from debate_core.integrations.docx_parser.package import DocxPackageError, open_debate_docx
from debate_core.integrations.docx_parser.parser import DOCX_PARSER_VERSION, DebateDocxParser
from debate_core.testing.docx_builder import (
    W_NAMESPACE,
    build_docx,
    build_styles_xml,
    paragraph_xml,
    run_xml,
)

SOURCE_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
SNAPSHOT = date(2026, 9, 12)
SOURCE_PATH = "hsld26/Maple Grove/QX/Maple Grove-QX-Neg-Grove City Invitational-Round 1.docx"

#: The version directory the first corpus parse wrote. It stays as it is.
FIRST_CORPUS_PARSE_VERSION = "2026.09.20-docx-1"

W = f'xmlns:w="{W_NAMESPACE}"'


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


def parse_bytes(parser: DebateDocxParser, content: bytes) -> ParsedDocument | ParseFailure:
    return parser.parse(content, make_source(), source_path=SOURCE_PATH)


def parse(parser: DebateDocxParser, body: str) -> ParsedDocument:
    result = parse_bytes(parser, build_docx(body))
    assert isinstance(result, ParsedDocument), result
    return result


def refusal_of(content: bytes) -> DocxPackageError:
    with pytest.raises(DocxPackageError) as raised:
        open_debate_docx(content)
    return raised.value


# --------------------------------------------------------------------------------------------
# The invented card every file below is built from
# --------------------------------------------------------------------------------------------

TAG = "Data centre demand collapses the reserve margin"
SHORT_CITE = "Okonkwo 26"
CITE_TAIL = " (Adaeze Okonkwo, invented for this test), Journal of Grid Studies, 14 March 2026."
SECOND_TAG = "Load growth outpaced every planning scenario"

MARKED_UP = (
    "Grid operators in the region reported that demand from new data centres rose ",
    "faster than any other load category last year",
    ", and the increase outpaced every scenario the utility had planned against.",
)
SMALL_PRINT = "The figures in this section are drawn from the regional filings described above."


def tag_paragraph(text: str = TAG) -> str:
    return paragraph_xml(run_xml(text), style="Heading4")


def cite_paragraph(short: str = SHORT_CITE, tail: str = CITE_TAIL) -> str:
    """A cite as a file with no cite style writes one: a bold name at 13 pt, then the rest."""
    return paragraph_xml(run_xml(short, bold=True, half_points=26) + run_xml(tail, half_points=22))


def marked_up_paragraph(parts: tuple[str, str, str] = MARKED_UP) -> str:
    """A body paragraph: 8 pt text with an underlined, highlighted stretch a debater reads aloud."""
    opening, read_aloud, closing = parts
    return paragraph_xml(
        run_xml(opening, half_points=16)
        + run_xml(read_aloud, underline="single", highlight="cyan", half_points=16)
        + run_xml(closing, half_points=16)
    )


def small_print_paragraph(text: str = SMALL_PRINT) -> str:
    """A body paragraph nobody reads aloud: one run, wholly at 5 pt, no underline, no highlight."""
    return paragraph_xml(run_xml(text, half_points=10))


def blank_paragraph(style: str | None = None) -> str:
    return paragraph_xml("", style=style)


# --------------------------------------------------------------------------------------------
# ac2: the 23 refusals were prose, and prose is accepted
# --------------------------------------------------------------------------------------------

#: The six spellings the scan matched in `w:t` text across the 23 refused files, each in an
#: invented sentence.
PROSE_THE_SCAN_REFUSED = [
    'Critics describe the system "as it stands" in terms the utility rejects.',
    "Critics describe the system 'as it stands' in terms the utility rejects.",
    "System 'adequacy' is the phrase the regional filing uses for it.",
    'The System "Adequacy" Review was published in the spring.',
    "The commission took public 'comment' for ninety days.",
    "Public 'interest' is the standard the statute sets.",
]


class TestProseThatNamesASystemOrThePublic:
    @pytest.mark.parametrize("sentence", PROSE_THE_SCAN_REFUSED)
    def test_a_card_whose_text_quotes_a_word_after_system_or_public_is_read(
        self, parser: DebateDocxParser, sentence: str
    ) -> None:
        """Refused by the first corpus parse; the text is ordinary and comes out exactly."""
        body = tag_paragraph() + cite_paragraph() + small_print_paragraph(sentence)
        document = parse(parser, body)

        assert [card.tag for card in document.cards] == [TAG]
        assert document.cards[0].evidence_text == sentence
        assert document.cards[0].full_cite == SHORT_CITE + CITE_TAIL

    @pytest.mark.parametrize("sentence", PROSE_THE_SCAN_REFUSED)
    def test_the_same_words_in_a_tag_or_a_cite_are_read_too(
        self, parser: DebateDocxParser, sentence: str
    ) -> None:
        body = (
            tag_paragraph(sentence) + cite_paragraph(tail=f", quoting: {sentence}") + small_print_paragraph()
        )
        document = parse(parser, body)

        assert document.cards[0].tag == sentence
        assert document.cards[0].full_cite.endswith(sentence)

    def test_the_words_in_a_style_name_do_not_refuse_the_package(self) -> None:
        """`word/styles.xml` goes through the same scan as the document part."""
        styles = build_styles_xml([("SystemQuote", "paragraph", 'System "Quote"', None)])
        package = open_debate_docx(build_docx(small_print_paragraph(), styles_xml=styles))
        assert package.styles["SystemQuote"].style_name == 'System "Quote"'


# --------------------------------------------------------------------------------------------
# ac2: the declarations those words belong to are still refused
# --------------------------------------------------------------------------------------------


def hostile_document(declaration: str, text: str = "ordinary text", *, encoding: str = "UTF-8") -> str:
    return (
        f'<?xml version="1.0" encoding="{encoding}"?>{declaration}'
        f"<w:document {W}><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
    )


#: Each hostile variant of the construct: the same `SYSTEM "` and `PUBLIC "` words, where XML
#: gives them their meaning, and the entity declarations the refusal exists to stop.
HOSTILE_DECLARATIONS = {
    "an entity defined and used": (
        '<!DOCTYPE w:document [<!ENTITY filler "filler filler filler">]>',
        "a &filler; b",
    ),
    "entities that expand one another": (
        '<!DOCTYPE w:document [<!ENTITY a "aaaaaaaaaa">'
        '<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;"><!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">]>',
        "&c;",
    ),
    "an external entity with a SYSTEM identifier": (
        '<!DOCTYPE w:document [<!ENTITY outside SYSTEM "file:///etc/hostname">]>',
        "a &outside; b",
    ),
    "an external entity with a PUBLIC identifier": (
        '<!DOCTYPE w:document [<!ENTITY outside PUBLIC "-//EXAMPLE//TEXT//EN" '
        '"http://example.invalid/outside.txt">]>',
        "a &outside; b",
    ),
    "an external subset with a SYSTEM identifier": (
        '<!DOCTYPE w:document SYSTEM "http://example.invalid/document.dtd">',
        "ordinary text",
    ),
    "an external subset with a PUBLIC identifier": (
        '<!DOCTYPE w:document PUBLIC "-//EXAMPLE//DTD DOCUMENT//EN" "http://example.invalid/document.dtd">',
        "ordinary text",
    ),
    "a parameter entity": (
        '<!DOCTYPE w:document [<!ENTITY % outside SYSTEM "http://example.invalid/more.dtd"> %outside;]>',
        "ordinary text",
    ),
    "a declaration beside the prose the scan used to refuse": (
        '<!DOCTYPE w:document [<!ENTITY filler "filler">]>',
        "the system \"as it stands\" and public 'comment'",
    ),
}


class TestDeclarationsAreStillRefused:
    @pytest.mark.parametrize("variant", HOSTILE_DECLARATIONS, ids=str)
    def test_a_document_part_that_declares_one_is_refused(self, variant: str) -> None:
        declaration, text = HOSTILE_DECLARATIONS[variant]
        refusal = refusal_of(build_docx("", document_xml=hostile_document(declaration, text)))

        assert refusal.reason is ParseFailureReason.FORBIDDEN_XML_CONSTRUCT
        assert "word/document.xml" in refusal.detail

    @pytest.mark.parametrize("variant", HOSTILE_DECLARATIONS, ids=str)
    @pytest.mark.parametrize("encoding", ["UTF-16", "UTF-16LE", "UTF-16BE"])
    def test_one_written_in_utf_16_is_refused_although_the_byte_scan_cannot_see_it(
        self, variant: str, encoding: str
    ) -> None:
        """In UTF-16 a zero byte sits between every two letters of `<!DOCTYPE`.

        The scan reads bytes, so it finds nothing. The refusal has to hold whatever encoding the
        part declares, or a declaration is accepted by being written two bytes to a letter.
        """
        declaration, text = HOSTILE_DECLARATIONS[variant]
        encoded = hostile_document(declaration, text, encoding=encoding).encode(encoding)
        if encoding != "UTF-16":
            encoded = ("﻿".encode(encoding)) + encoded
        refusal = refusal_of(build_docx("", extra_parts={"word/document.xml": encoded}))

        assert refusal.reason is ParseFailureReason.FORBIDDEN_XML_CONSTRUCT

    @pytest.mark.parametrize("part", ["word/styles.xml", "_rels/.rels"])
    def test_one_in_any_other_part_the_reader_opens_is_refused(self, part: str) -> None:
        declared = (
            '<?xml version="1.0"?><!DOCTYPE root [<!ENTITY outside SYSTEM "file:///etc/hostname">]>'
            "<root>&outside;</root>"
        )
        refusal = refusal_of(build_docx(small_print_paragraph(), extra_parts={part: declared}))

        assert refusal.reason is ParseFailureReason.FORBIDDEN_XML_CONSTRUCT
        assert part in refusal.detail

    def test_the_parser_returns_a_failure_and_no_document(self, parser: DebateDocxParser) -> None:
        declaration, text = HOSTILE_DECLARATIONS["an external entity with a SYSTEM identifier"]
        result = parse_bytes(parser, build_docx("", document_xml=hostile_document(declaration, text)))

        assert isinstance(result, ParseFailure)
        assert result.reason is ParseFailureReason.FORBIDDEN_XML_CONSTRUCT

    def test_the_refusal_says_what_was_declared_and_quotes_no_text(self) -> None:
        declaration, _ = HOSTILE_DECLARATIONS["a declaration beside the prose the scan used to refuse"]
        refusal = refusal_of(
            build_docx("", document_xml=hostile_document(declaration, 'Okonkwo said the system "works"'))
        )

        assert "DOCTYPE" in refusal.detail
        assert "Okonkwo" not in refusal.detail
        assert "works" not in refusal.detail


# --------------------------------------------------------------------------------------------
# ac2: what the XML parser is allowed to do, whatever reaches it
# --------------------------------------------------------------------------------------------


class TestTheXmlParserResolvesNothing:
    """The options, tested by what they stop. The refusals above are in front of this parser; if
    one of them ever missed a declaration, these are what would be left."""

    def test_an_entity_it_is_handed_is_not_expanded(self) -> None:
        declaration, text = HOSTILE_DECLARATIONS["an entity defined and used"]
        root = etree.fromstring(
            hostile_document(declaration, text).encode(), parser=docx_package.hardened_xml_parser()
        )

        assert "filler filler" not in "".join(root.itertext())
        assert b"filler filler filler</" not in etree.tostring(root)

    def test_an_external_entity_is_not_read_from_disk(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside.txt"
        outside.write_text("READ FROM OUTSIDE THE PACKAGE", encoding="utf-8")
        declaration = f'<!DOCTYPE w:document [<!ENTITY outside SYSTEM "{outside.as_uri()}">]>'
        root = etree.fromstring(
            hostile_document(declaration, "a &outside; b").encode(),
            parser=docx_package.hardened_xml_parser(),
        )

        assert "READ FROM OUTSIDE" not in "".join(root.itertext())
        assert b"READ FROM OUTSIDE" not in etree.tostring(root)

    def test_an_external_dtd_is_not_loaded(self, tmp_path: Path) -> None:
        """A DTD that was loaded would add its default attribute to the root element."""
        dtd = tmp_path / "document.dtd"
        dtd.write_text('<!ATTLIST w:document loaded CDATA "from the DTD">', encoding="utf-8")
        declaration = f'<!DOCTYPE w:document SYSTEM "{dtd.as_uri()}">'
        root = etree.fromstring(
            hostile_document(declaration).encode(), parser=docx_package.hardened_xml_parser()
        )

        assert root.get("loaded") is None


# --------------------------------------------------------------------------------------------
# ac3: a body paragraph that looks like a cite stays in its card
# --------------------------------------------------------------------------------------------

#: A paragraph of the source's own prose, wholly in small print, that happens to hold an ellipsis
#: and a name followed by a year. The classifier's wiki rule calls it a cite entry.
ELLIPSIS_AND_YEAR = (
    "Reserve margins across the interconnection narrowed for a third year running … the "
    "regional operator had warned, in the projections Halvorsen 2019 set out, that no slack "
    "would be left once the new load was connected to the eastern substations."
)

#: Another, with an underlined stretch, as the second such paragraph in the operator's sample had.
UNDERLINED_ELLIPSIS_AND_YEAR = (
    "The filing concedes as much. Ferreira 2021 found that ",
    "every planning scenario assumed slower growth",
    " ... and the utility has not revised a single one of them since the review closed.",
)

#: A short body paragraph that opens with a capitalised word and a year, as prose often does.
OPENS_WITH_A_YEAR = "In 2019 the operator revised its forecast upward for the first time in a decade."

SECOND_BODY = (
    "Planners at the utility assumed that load would grow by ",
    "one percent a year through the decade",
    ", a figure the regional operator abandoned within eighteen months.",
)


def underlined_small_print_paragraph(parts: tuple[str, str, str]) -> str:
    opening, underlined, closing = parts
    return paragraph_xml(
        run_xml(opening, half_points=10)
        + run_xml(underlined, underline="single", half_points=10)
        + run_xml(closing, half_points=10)
    )


#: The operator's sample, rebuilt: one card whose body runs on through two paragraphs the
#: classifier takes for cite entries, then a blank line and a second, ordinary card.
SPLIT_BY_A_GUESSED_CITE = (
    tag_paragraph()  # 0
    + cite_paragraph()  # 1
    + marked_up_paragraph()  # 2
    + small_print_paragraph()  # 3
    + small_print_paragraph(ELLIPSIS_AND_YEAR)  # 4: read as a cite entry
    + marked_up_paragraph(SECOND_BODY)  # 5
    + small_print_paragraph(SMALL_PRINT)  # 6
    + underlined_small_print_paragraph(UNDERLINED_ELLIPSIS_AND_YEAR)  # 7: read as a cite entry
    + blank_paragraph()  # 8
    + tag_paragraph(SECOND_TAG)  # 9
    + cite_paragraph("Ferreira 25", " (Journal of Grid Studies, 2 November 2025).")  # 10
    + marked_up_paragraph(SECOND_BODY)  # 11
)

WHOLE_FIRST_BODY = "\n".join(
    [
        "".join(MARKED_UP),
        SMALL_PRINT,
        ELLIPSIS_AND_YEAR,
        "".join(SECOND_BODY),
        SMALL_PRINT,
        "".join(UNDERLINED_ELLIPSIS_AND_YEAR),
    ]
)


class TestABodyParagraphGuessedToBeACite:
    def test_the_file_holds_two_cards_and_each_has_its_tag(self, parser: DebateDocxParser) -> None:
        """The first corpus parse stored four: the first card cut short, and two with no tag."""
        document = parse(parser, SPLIT_BY_A_GUESSED_CITE)

        assert [card.tag for card in document.cards] == [TAG, SECOND_TAG]

    def test_the_first_cards_body_runs_to_its_last_paragraph(self, parser: DebateDocxParser) -> None:
        first = parse(parser, SPLIT_BY_A_GUESSED_CITE).cards[0]

        assert first.evidence_text == WHOLE_FIRST_BODY
        assert first.full_cite == SHORT_CITE + CITE_TAIL
        assert (first.provenance.first_element_index, first.provenance.last_element_index) == (0, 7)

    def test_the_second_card_is_untouched(self, parser: DebateDocxParser) -> None:
        second = parse(parser, SPLIT_BY_A_GUESSED_CITE).cards[1]

        assert second.short_cite == "Ferreira 25"
        assert second.evidence_text == "".join(SECOND_BODY)
        assert second.completeness is CardCompleteness.FULL
        assert (second.provenance.first_element_index, second.provenance.last_element_index) == (9, 11)

    def test_the_two_paragraphs_are_recorded_as_body_with_the_guess_they_overrode(
        self, parser: DebateDocxParser
    ) -> None:
        document = parse(parser, SPLIT_BY_A_GUESSED_CITE)

        for index in (4, 7):
            section = document.sections[index]
            assert section.unit is StructuralUnit.EVIDENCE
            assert section.match.rule_id == "assembly-cite-guess-inside-card-body:heuristic-wiki-cite-entry"
            assert section.match.match_source is StyleMatchSource.HEURISTIC
            assert section.match.confidence <= 0.6
        assert (
            parse(parser, SPLIT_BY_A_GUESSED_CITE)
            .cards[0]
            .rule_ids.count("assembly-cite-guess-inside-card-body:heuristic-wiki-cite-entry")
            == 2
        )

    def test_the_underline_in_the_second_paragraph_lands_on_its_own_words(
        self, parser: DebateDocxParser
    ) -> None:
        """It is body now, so its spans are the card's, at offsets into the joined text."""
        first = parse(parser, SPLIT_BY_A_GUESSED_CITE).cards[0]
        underlined = UNDERLINED_ELLIPSIS_AND_YEAR[1]
        start = WHOLE_FIRST_BODY.index(underlined)

        assert any(
            first.evidence_text[span.start_offset : span.end_offset] == underlined
            and span.start_offset == start
            for span in first.formatting_spans
        )

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "The card is whole, but any body holding an ellipsis is called ABBREVIATED: the "
            "completeness rule is t03's, is wrong for 95% of the cards it marks, and is reported "
            "in the v1-e31-t09 session report as follow-up work rather than changed here."
        ),
    )
    def test_the_first_card_is_a_full_card(self, parser: DebateDocxParser) -> None:
        assert parse(parser, SPLIT_BY_A_GUESSED_CITE).cards[0].completeness is CardCompleteness.FULL

    def test_a_small_print_paragraph_that_opens_with_a_year_stays_in_the_body(
        self, parser: DebateDocxParser
    ) -> None:
        """`In 2019 …` opens the way a short cite does. Inside a body, in small print, it is prose."""
        body = (
            tag_paragraph()
            + cite_paragraph()
            + marked_up_paragraph()
            + small_print_paragraph(OPENS_WITH_A_YEAR)
            + marked_up_paragraph(SECOND_BODY)
        )
        document = parse(parser, body)

        assert [card.tag for card in document.cards] == [TAG]
        assert document.cards[0].evidence_text == "\n".join(
            ["".join(MARKED_UP), OPENS_WITH_A_YEAR, "".join(SECOND_BODY)]
        )
        assert document.cards[0].completeness is CardCompleteness.FULL
        assert document.sections[3].match.rule_id == (
            "assembly-cite-guess-inside-card-body:heuristic-cite-line-author-year"
        )

    def test_a_highlighted_paragraph_that_opens_with_a_year_stays_in_the_body(
        self, parser: DebateDocxParser
    ) -> None:
        """Highlighting is what a debater does to evidence, at any size."""
        highlighted = paragraph_xml(
            run_xml("In 2019 the operator ", half_points=22)
            + run_xml("revised its forecast upward", highlight="yellow", half_points=22)
            + run_xml(" for the first time in a decade.", half_points=22)
        )
        document = parse(parser, tag_paragraph() + cite_paragraph() + marked_up_paragraph() + highlighted)

        assert len(document.cards) == 1
        assert document.cards[0].evidence_text.endswith(OPENS_WITH_A_YEAR)


class TestACiteThatIsStillACite:
    """The rule is narrow on purpose. Each of these keeps the reading it had."""

    def test_a_second_cite_with_a_bold_name_under_one_tag_still_starts_a_card(
        self, parser: DebateDocxParser
    ) -> None:
        """Two cards under one tag. The second has a cite and a body and no tag of its own."""
        body = (
            tag_paragraph()
            + cite_paragraph()
            + marked_up_paragraph()
            + cite_paragraph("Ferreira 25", " (Journal of Grid Studies, 2 November 2025).")
            + marked_up_paragraph(SECOND_BODY)
        )
        document = parse(parser, body)

        assert [(card.tag, card.short_cite) for card in document.cards] == [
            (TAG, "Okonkwo 26"),
            ("", "Ferreira 25"),
        ]
        assert [card.has_tag for card in document.cards] == [True, False]
        assert document.cards[0].evidence_text == "".join(MARKED_UP)
        assert document.cards[1].evidence_text == "".join(SECOND_BODY)

    def test_a_bold_name_keeps_a_cite_a_cite_even_in_small_print(self, parser: DebateDocxParser) -> None:
        """Small print says body and a bold name says cite. In doubt the classifier's answer stands."""
        small_cite = paragraph_xml(
            run_xml("Ferreira 25", bold=True, half_points=16)
            + run_xml(" (Journal of Grid Studies, 2 November 2025).", half_points=16)
        )
        body = tag_paragraph() + cite_paragraph() + marked_up_paragraph() + small_cite + marked_up_paragraph()
        document = parse(parser, body)

        assert [card.short_cite for card in document.cards] == ["Okonkwo 26", "Ferreira 25"]
        assert document.sections[3].unit is StructuralUnit.CITE

    def test_an_underlined_link_does_not_make_a_cite_into_body(self, parser: DebateDocxParser) -> None:
        """A cite's URL is often underlined. Underline alone, at reading size, proves nothing."""
        linked_cite = paragraph_xml(
            run_xml("Ferreira 25, Journal of Grid Studies, ", half_points=22)
            + run_xml("example.invalid/grid", underline="single", half_points=22)
        )
        body = (
            tag_paragraph() + cite_paragraph() + marked_up_paragraph() + linked_cite + marked_up_paragraph()
        )
        document = parse(parser, body)

        assert [card.short_cite for card in document.cards] == ["Okonkwo 26", "Ferreira 25"]

    def test_a_cite_character_style_inside_a_body_still_starts_a_card(self, parser: DebateDocxParser) -> None:
        """A Verbatim cite style is a style match, not a guess, and is not second-guessed."""
        styled_cite = paragraph_xml(
            run_xml("Ferreira 25", character_style="Style13ptBold", half_points=16)
            + run_xml(" (Journal of Grid Studies, 2 November 2025).", half_points=16)
        )
        body = (
            tag_paragraph() + cite_paragraph() + marked_up_paragraph() + styled_cite + marked_up_paragraph()
        )
        document = parse(parser, body)

        assert len(document.cards) == 2
        assert document.sections[3].match.rule_id == "verbatim-cite-run-style"

    def test_a_cite_entry_straight_after_its_tag_is_still_the_cards_cite(
        self, parser: DebateDocxParser
    ) -> None:
        """No body is open yet, so there is no body for it to belong to."""
        entry = "Okonkwo 26 — Grid operators in the region … thinner than at any point."
        document = parse(parser, tag_paragraph() + small_print_paragraph(entry))

        assert len(document.cards) == 1
        assert document.cards[0].full_cite == entry
        assert document.cards[0].completeness is CardCompleteness.CITE_ONLY
        assert document.sections[1].match.rule_id == "heuristic-wiki-cite-entry"

    def test_a_cite_with_nothing_open_above_it_is_still_a_card_with_no_tag(
        self, parser: DebateDocxParser
    ) -> None:
        """A bare citation under a block heading: the file gives it no claim and no text."""
        body = paragraph_xml(run_xml("Sources"), style="Heading3") + small_print_paragraph(
            "Okonkwo 26 — Grid operators in the region … thinner than at any point."
        )
        document = parse(parser, body)

        assert len(document.cards) == 1
        assert document.cards[0].has_tag is False
        assert document.cards[0].completeness is CardCompleteness.CITE_ONLY
        assert document.cards[0].section_path == ("Sources",)


# --------------------------------------------------------------------------------------------
# ac3: a blank line in a heading style is not a heading
# --------------------------------------------------------------------------------------------


class TestABlankLineInAStructuralStyle:
    def test_a_blank_heading_4_under_a_tag_does_not_take_the_cards_tag(
        self, parser: DebateDocxParser
    ) -> None:
        """39 stored cards: the tag became an analytic and the card kept an empty one."""
        body = tag_paragraph() + blank_paragraph("Heading4") + cite_paragraph() + marked_up_paragraph()
        document = parse(parser, body)

        assert [card.tag for card in document.cards] == [TAG]
        assert [section.unit for section in document.sections] == [
            StructuralUnit.TAG,
            StructuralUnit.OTHER,
            StructuralUnit.CITE,
            StructuralUnit.EVIDENCE,
        ]
        assert document.sections[1].match.rule_id == "assembly-empty-paragraph:verbatim-style-id:Heading4"

    def test_a_blank_heading_4_inside_a_body_does_not_end_the_card(self, parser: DebateDocxParser) -> None:
        """It used to open a card with no tag and no cite, which was dropped with the body under it."""
        body = (
            tag_paragraph()
            + cite_paragraph()
            + marked_up_paragraph()
            + blank_paragraph("Heading4")
            + marked_up_paragraph(SECOND_BODY)
        )
        document = parse(parser, body)

        assert len(document.cards) == 1
        assert document.cards[0].evidence_text == "".join(MARKED_UP) + "\n" + "".join(SECOND_BODY)

    def test_a_blank_analytic_line_inside_a_body_does_not_end_the_card(
        self, parser: DebateDocxParser
    ) -> None:
        body = (
            tag_paragraph()
            + cite_paragraph()
            + marked_up_paragraph()
            + blank_paragraph("Analytic")
            + marked_up_paragraph(SECOND_BODY)
        )
        document = parse(parser, body)

        assert len(document.cards) == 1
        assert document.cards[0].evidence_text == "".join(MARKED_UP) + "\n" + "".join(SECOND_BODY)

    @pytest.mark.parametrize("style", ["Heading1", "Heading2", "Heading3", "Heading4"])
    def test_a_blank_heading_closes_no_level_and_names_none(
        self, parser: DebateDocxParser, style: str
    ) -> None:
        """1,847 stored cards carry an empty string in their section path."""
        body = (
            paragraph_xml(run_xml("Data Centre Moratorium Negative"), style="Heading1")
            + paragraph_xml(run_xml("Grid Reliability"), style="Heading2")
            + paragraph_xml(run_xml("AT: Reserve Margin Turn"), style="Heading3")
            + blank_paragraph(style)
            + tag_paragraph()
            + cite_paragraph()
            + marked_up_paragraph()
        )
        document = parse(parser, body)

        assert document.cards[0].section_path == (
            "Data Centre Moratorium Negative",
            "Grid Reliability",
            "AT: Reserve Margin Turn",
        )
        assert all("" not in section.section_path for section in document.sections)

    def test_a_line_of_spaces_is_a_blank_line(self, parser: DebateDocxParser) -> None:
        spaces = paragraph_xml(run_xml("   "), style="Heading4")
        document = parse(parser, tag_paragraph() + spaces + cite_paragraph() + marked_up_paragraph())

        assert [card.tag for card in document.cards] == [TAG]

    def test_a_blank_line_in_a_body_style_is_still_a_line_of_the_body(self, parser: DebateDocxParser) -> None:
        """Evidence text is copied as the file lays it out. This rule changes structure, not text."""
        styles = build_styles_xml(
            [
                ("Normal", "paragraph", "Normal", None),
                ("Heading4", "paragraph", "heading 4", "Normal"),
                ("CardBody", "paragraph", "Card Body", "Normal"),
            ]
        )
        body = (
            tag_paragraph()
            + cite_paragraph()
            + paragraph_xml(run_xml("First paragraph of the body."), style="CardBody")
            + blank_paragraph("CardBody")
            + paragraph_xml(run_xml("Third paragraph of the body."), style="CardBody")
        )
        result = parse_bytes(parser, build_docx(body, styles_xml=styles))
        assert isinstance(result, ParsedDocument)

        assert result.sections[3].unit is StructuralUnit.EVIDENCE
        assert result.cards[0].evidence_text == "First paragraph of the body.\n\nThird paragraph of the body."


# --------------------------------------------------------------------------------------------
# ac4: the output changed, so the version did
# --------------------------------------------------------------------------------------------


class TestTheParserVersion:
    def test_it_is_not_the_version_the_first_corpus_parse_wrote(self) -> None:
        """A reading that differs has to say so: the stored cards name the reading that made them."""
        assert DOCX_PARSER_VERSION != FIRST_CORPUS_PARSE_VERSION

    def test_its_directory_sorts_after_the_first_corpus_parses(self) -> None:
        """The newest version directory is the one a reader takes."""
        names = sorted([DOCX_PARSER_VERSION, FIRST_CORPUS_PARSE_VERSION], key=parse_version_directory)
        assert names == [FIRST_CORPUS_PARSE_VERSION, DOCX_PARSER_VERSION]

    def test_a_refusal_names_the_version_that_refused(self, parser: DebateDocxParser) -> None:
        result = parse_bytes(parser, b"not a zip at all")

        assert isinstance(result, ParseFailure)
        assert result.parser_version == DOCX_PARSER_VERSION
