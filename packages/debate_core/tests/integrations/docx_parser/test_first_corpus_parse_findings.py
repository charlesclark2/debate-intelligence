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

And a fourth, which the same reading turned up: **an ellipsis anywhere made a card `ABBREVIATED`.**
21,278 of the 22,443 cards marked that way have a body over 1,000 characters. They are whole cards
whose text leaves something out, not disclosures of a card's first and last words.

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
    ParsedCard,
    ParsedDocument,
    ParseFailure,
    ParseFailureReason,
)
from debate_core.domain.style_profile import StructuralUnit, StyleMatchSource, StyleProfile
from debate_core.integrations.docx_parser import package as docx_package
from debate_core.integrations.docx_parser.package import DocxPackageError, open_debate_docx
from debate_core.integrations.docx_parser.parser import DOCX_PARSER_VERSION, DebateDocxParser
from debate_core.testing.docx_builder import (
    DEFAULT_STYLE_DEFINITIONS,
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
    "a document type that declares nothing": (
        "<!DOCTYPE w:document>",
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
    def test_one_the_scan_can_read_never_reaches_an_xml_parser(
        self, variant: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The cheapest defence is never to hand the part to a parser at all, and it still holds.

        The package has no `_rels/.rels`, so the document part is the first XML the reader opens.
        """

        def no_parser_is_built() -> etree.XMLParser:
            raise AssertionError("an XML parser was built for a part that declares a document type")

        monkeypatch.setattr(docx_package, "hardened_xml_parser", no_parser_is_built)
        declaration, text = HOSTILE_DECLARATIONS[variant]
        content = build_docx("", document_xml=hostile_document(declaration, text), omit_parts=["_rels/.rels"])

        assert refusal_of(content).reason is ParseFailureReason.FORBIDDEN_XML_CONSTRUCT

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
        serialised = etree.tostring(root, encoding="unicode")

        assert "a &filler; b" in serialised
        assert "filler filler filler" not in serialised

    def test_an_external_entity_is_not_read_from_disk(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside.txt"
        outside.write_text("READ FROM OUTSIDE THE PACKAGE", encoding="utf-8")
        declaration = f'<!DOCTYPE w:document [<!ENTITY outside SYSTEM "{outside.as_uri()}">]>'
        root = etree.fromstring(
            hostile_document(declaration, "a &outside; b").encode(),
            parser=docx_package.hardened_xml_parser(),
        )
        serialised = etree.tostring(root, encoding="unicode")

        assert "a &outside; b" in serialised
        assert "READ FROM OUTSIDE" not in serialised

    def test_an_external_dtd_is_not_loaded(self, tmp_path: Path) -> None:
        """A DTD that was loaded would be on the parsed tree, and would define the entity used."""
        dtd = tmp_path / "document.dtd"
        dtd.write_text('<!ENTITY fromdtd "DEFINED IN THE EXTERNAL SUBSET">', encoding="utf-8")
        declaration = f'<!DOCTYPE w:document SYSTEM "{dtd.as_uri()}">'
        root = etree.fromstring(
            hostile_document(declaration, "a &fromdtd; b").encode(),
            parser=docx_package.hardened_xml_parser(),
        )
        loaded: object = root.getroottree().docinfo.externalDTD

        assert loaded is None
        assert "DEFINED IN THE EXTERNAL SUBSET" not in etree.tostring(root, encoding="unicode")


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

    def test_the_first_card_is_a_full_card(self, parser: DebateDocxParser) -> None:
        """Its body holds two ellipses, in the source's own prose. It is whole all the same."""
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
# ac6: ABBREVIATED is a disclosure's shape, not an ellipsis
# --------------------------------------------------------------------------------------------

#: A whole card, 77 words, whose source leaves a clause out in the middle.
WHOLE_BODY_WITH_ONE_OMISSION = (
    "Grid operators in the region reported that demand from new data centres rose faster than "
    "any other load category last year, and the increase outpaced every scenario the utility had "
    "planned against … which left the reserve margin thinner than at any point in the past "
    "decade, a result the regional operator had warned of in each of its three preceding annual "
    "assessments and that the utility had dismissed as unlikely on every occasion it was raised."
)

#: A whole card cut down hard, as a debater cuts one: three omissions in three spellings.
WHOLE_BODY_WITH_SEVERAL_OMISSIONS = (
    "Planners at the utility assumed that load would grow by one percent a year through the "
    "decade [...] a figure the regional operator abandoned within eighteen months of adopting it "
    "*** because the connection requests already filed by developers exceeded the whole of the "
    "forecast growth ... and none of the planning scenarios the commission had reviewed and "
    "approved allowed for a single one of those requests being granted."
)

#: A whole card of one sentence: 21 words, an omission, 8 words. The shortest one-ellipsis bodies
#: in the first corpus parse have this shape, and nothing separates them from any other short card.
ONE_SENTENCE_WITH_AN_OMISSION = (
    "The regional operator told the commission that the reserve margin would fall below its "
    "target in three of the five zones … unless new capacity came online before the summer."
)

FIRST_WORDS = "Grid operators in the region reported that demand"
LAST_WORDS = "thinner than at any point in the past decade."

#: Twelve words, and thirteen: either side of the bound.
TWELVE_WORDS = "one two three four five six seven eight nine ten eleven twelve"
THIRTEEN_WORDS = TWELVE_WORDS + " thirteen"

MARKER_SPELLINGS = ["…", "...", "[…]", "[...]", "***"]


def card_with_body(parser: DebateDocxParser, *paragraphs: str, cite: str | None = None) -> ParsedCard:
    """The one card of a file that is a tag, a cite and these body paragraphs in small print."""
    body = tag_paragraph() + (cite_paragraph() if cite is None else cite_paragraph(tail=cite))
    document = parse(parser, body + "".join(small_print_paragraph(text) for text in paragraphs))
    assert len(document.cards) == 1
    assert document.cards[0].evidence_text == "\n".join(paragraphs)
    return document.cards[0]


class TestAbbreviatedIsADisclosuresShape:
    """A disclosure of first and last words is a few words, one ellipsis, and a few words more.

    Measured over the 19,402 bodies of the corpus that hold an ellipsis marker: not one has a
    single marker with 15 words or fewer on both sides, and only 37 are 60 words or shorter in
    all. So the bound is set from what a disclosure is, twelve words a side, and it sits below
    every whole card the corpus holds.
    """

    def test_a_whole_card_with_one_omission_is_full(self, parser: DebateDocxParser) -> None:
        card = card_with_body(parser, WHOLE_BODY_WITH_ONE_OMISSION)

        assert card.completeness is CardCompleteness.FULL
        assert card.is_abbreviated is False

    def test_a_whole_card_with_several_omissions_is_full(self, parser: DebateDocxParser) -> None:
        card = card_with_body(parser, WHOLE_BODY_WITH_SEVERAL_OMISSIONS)

        assert card.completeness is CardCompleteness.FULL

    def test_a_whole_card_of_several_paragraphs_with_an_omission_in_each_is_full(
        self, parser: DebateDocxParser
    ) -> None:
        card = card_with_body(parser, WHOLE_BODY_WITH_ONE_OMISSION, WHOLE_BODY_WITH_SEVERAL_OMISSIONS)

        assert card.completeness is CardCompleteness.FULL

    def test_a_whole_card_of_one_sentence_with_an_omission_is_full(self, parser: DebateDocxParser) -> None:
        """Twenty-one words is not a card's first few. In doubt a whole card is not called abbreviated."""
        card = card_with_body(parser, ONE_SENTENCE_WITH_AN_OMISSION)

        assert card.completeness is CardCompleteness.FULL

    def test_the_profile_still_names_the_five_marker_spellings(self, profile: StyleProfile) -> None:
        """The spellings are the profile's. This list is here so each one is tried below."""
        assert sorted(profile.cite.wiki_ellipsis_markers) == sorted(MARKER_SPELLINGS)

    @pytest.mark.parametrize("marker", MARKER_SPELLINGS)
    def test_first_words_a_marker_and_last_words_is_abbreviated(
        self, parser: DebateDocxParser, marker: str
    ) -> None:
        card = card_with_body(parser, f"{FIRST_WORDS} {marker} {LAST_WORDS}")

        assert card.completeness is CardCompleteness.ABBREVIATED
        assert card.is_abbreviated is True
        assert card.evidence_text == f"{FIRST_WORDS} {marker} {LAST_WORDS}"

    @pytest.mark.parametrize("marker", MARKER_SPELLINGS)
    def test_a_marker_written_against_the_words_either_side_is_still_one(
        self, parser: DebateDocxParser, marker: str
    ) -> None:
        card = card_with_body(parser, f"{FIRST_WORDS}{marker}{LAST_WORDS}")

        assert card.completeness is CardCompleteness.ABBREVIATED

    def test_a_short_body_with_no_marker_is_full(self, parser: DebateDocxParser) -> None:
        """Short is not abbreviated. 10,682 bodies in the corpus are 100 words or fewer."""
        card = card_with_body(parser, f"{FIRST_WORDS} {LAST_WORDS}")

        assert card.completeness is CardCompleteness.FULL

    def test_a_marker_in_the_cite_does_not_abbreviate_a_whole_body(self, parser: DebateDocxParser) -> None:
        """A cite carries an ellipsis for its own reasons: a shortened title, a list of authors."""
        whole = "".join(MARKED_UP)
        card = card_with_body(
            parser, whole, cite=", Reserve Margins … and Load Growth, Journal of Grid Studies."
        )

        assert "…" in card.full_cite
        assert card.completeness is CardCompleteness.FULL

    @pytest.mark.parametrize("marker", MARKER_SPELLINGS)
    def test_a_marker_in_the_cite_does_not_abbreviate_a_short_body_either(
        self, parser: DebateDocxParser, marker: str
    ) -> None:
        card = card_with_body(
            parser, f"{FIRST_WORDS} {LAST_WORDS}", cite=f", Reserve Margins {marker} Journal of Grid Studies."
        )

        assert marker in card.full_cite
        assert card.completeness is CardCompleteness.FULL

    def test_a_cite_with_a_marker_and_no_body_is_still_cite_only(self, parser: DebateDocxParser) -> None:
        body = tag_paragraph() + cite_paragraph(tail=", Reserve Margins … Journal of Grid Studies.")
        card = parse(parser, body + paragraph_xml(run_xml("Grid Reliability"), style="Heading2")).cards[0]

        assert card.completeness is CardCompleteness.CITE_ONLY
        assert card.evidence_text == ""

    @pytest.mark.parametrize("marker", MARKER_SPELLINGS)
    def test_twelve_words_either_side_is_the_most_a_disclosure_holds(
        self, parser: DebateDocxParser, marker: str
    ) -> None:
        """In every spelling: a bracketed marker is one marker, and its brackets are not words."""
        card = card_with_body(parser, f"{TWELVE_WORDS} {marker} {TWELVE_WORDS}")

        assert card.completeness is CardCompleteness.ABBREVIATED

    @pytest.mark.parametrize(
        ("before", "after"),
        [
            (THIRTEEN_WORDS, "one two three"),
            ("one two three", THIRTEEN_WORDS),
            (THIRTEEN_WORDS, THIRTEEN_WORDS),
        ],
        ids=["thirteen before", "thirteen after", "thirteen both"],
    )
    def test_thirteen_words_on_either_side_is_a_card_with_an_omission(
        self, parser: DebateDocxParser, before: str, after: str
    ) -> None:
        card = card_with_body(parser, f"{before} … {after}")

        assert card.completeness is CardCompleteness.FULL

    @pytest.mark.parametrize(
        "text",
        [f"… {LAST_WORDS}", f"{FIRST_WORDS} …", f"[...] {LAST_WORDS}", f"{FIRST_WORDS}..."],
        ids=["opens with it", "closes with it", "opens with a bracketed one", "trails off"],
    )
    def test_a_marker_at_either_end_joins_nothing(self, parser: DebateDocxParser, text: str) -> None:
        """A quotation that starts or stops mid-sentence. There is no first-and-last to it."""
        card = card_with_body(parser, text)

        assert card.completeness is CardCompleteness.FULL

    @pytest.mark.parametrize(
        "text",
        [
            "Grid operators reported … demand rose … thinner than ever.",
            "Grid operators reported ... demand rose [...] thinner than ever.",
            "Grid operators reported ****** thinner than ever.",
        ],
        ids=["two markers", "two spellings", "one marker written twice"],
    )
    def test_two_markers_are_two_omissions_however_short_the_body(
        self, parser: DebateDocxParser, text: str
    ) -> None:
        """One marker joins a beginning to an end. Two leave things out of a quotation."""
        card = card_with_body(parser, text)

        assert card.completeness is CardCompleteness.FULL

    def test_a_disclosure_spread_over_two_paragraphs_is_read_as_one_body(
        self, parser: DebateDocxParser
    ) -> None:
        """The words are counted over the body, so where the line breaks fall changes nothing."""
        card = card_with_body(parser, f"{FIRST_WORDS} …", LAST_WORDS)

        assert card.completeness is CardCompleteness.ABBREVIATED


# --------------------------------------------------------------------------------------------
# ac4: the output changed, so the version did
# --------------------------------------------------------------------------------------------


# --------------------------------------------------------------------------------------------
# ac7: a card's body filed as its cite
# --------------------------------------------------------------------------------------------

#: A whole card's body in one paragraph: 355 words and 2,104 characters of a source's own prose,
#: with an omission and a name followed by a year. The classifier's wiki rule calls it a cite
#: entry, at any length.
WHOLE_BODY_IN_ONE_PARAGRAPH = (
    "Reserve margins across the interconnection have narrowed in every one of the last six "
    "planning cycles, and the regional operator no longer treats the trend as a forecasting "
    "error. The projections that Halvorsen 2019 set out assumed that new load would arrive "
    "slowly … and that assumption failed within two years of the report being filed. Data "
    "centre developers asked for more firm capacity in a single quarter than the utility had "
    "expected to connect over the whole of the decade, and most of those requests were sited on "
    "the eastern side of the system, where the transmission lines were already carrying close to "
    "their thermal limits on ordinary summer afternoons. The utility answered by deferring the "
    "retirement of two ageing gas units and by asking the commission for permission to sign "
    "emergency purchase agreements with its neighbours. Neither measure adds a megawatt of new "
    "supply. The deferred units were scheduled to close because they failed too often to be "
    "counted on during a heat wave, and the neighbouring systems face the same shortage of spare "
    "generation at exactly the same hours of the year. The operator's own assessment says as "
    "much in plain terms: if the connection queue is honoured as it stands, the reserve margin "
    "falls below the reliability standard in three of the five zones by the second summer, and "
    "it stays below the standard in every later year of the study. A shortfall of that size "
    "cannot be managed with voluntary conservation appeals, which have never delivered more than "
    "a small fraction of the reduction the operator would need. It means rotating outages on the "
    "hottest days, ordered by the operator and carried out by the distribution companies, in "
    "neighbourhoods that have no say in which large customers were connected ahead of them. The "
    "utility's reply, that the queue will thin itself as speculative projects withdraw, is a "
    "hope and not a plan, and the filings give no figure for it. The "
    "commission has the authority to pause new large connections until supply catches up, and "
    "nothing in the record suggests that any other remedy would arrive in time to matter."
)

#: A disclosure's first and last words on their own line, where the words happen to name a study.
FIRST_AND_LAST_WORDS_NAMING_A_STUDY = (
    "Reserve margins narrowed after Halvorsen 2019 … no slack would be left."
)

#: A wiki cite entry: a name, a year, the card's first words, a marker and its last words.
WIKI_CITE_ENTRIES = [
    "Okonkwo 26 — Grid operators in the region … thinner than at any point.",
    "Grid operators in the region … thinner than at any point (Okonkwo 2026).",
]

FERREIRA_TAIL = " (Journal of Grid Studies, 2 November 2025)."

#: The default styles, and the cite paragraph style a few templates define.
STYLES_WITH_A_CITE_PARAGRAPH = build_styles_xml(
    [*DEFAULT_STYLE_DEFINITIONS, ("CiteParagraph", "paragraph", "Cite Paragraph", "Normal")]
)

AFTER_THE_CARDS_CITE = "assembly-cite-guess-after-card-cite"
LONGER_THAN_A_CITE = "assembly-cite-guess-longer-than-a-cite"
INSIDE_THE_BODY = "assembly-cite-guess-inside-card-body"


def highlighted_paragraph(text: str) -> str:
    """A paragraph at reading size whose middle third a debater has highlighted."""
    third = len(text) // 3
    return paragraph_xml(
        run_xml(text[:third], half_points=22)
        + run_xml(text[third : 2 * third], highlight="yellow", half_points=22)
        + run_xml(text[2 * third :], half_points=22)
    )


def reading_size_paragraph(text: str) -> str:
    """A paragraph at 11 pt with nothing done to it: how a cite's second line is often left."""
    return paragraph_xml(run_xml(text, half_points=22))


def behind_a_bold_opening(text: str, *, highlight: str | None = None) -> str:
    """A small-print paragraph whose first two words are bold, the way a cite opens."""
    opening_ends = text.index(" ", text.index(" ") + 1)
    return paragraph_xml(
        run_xml(text[:opening_ends], bold=True, half_points=10)
        + run_xml(text[opening_ends:], highlight=highlight, half_points=10)
    )


def in_a_cite_paragraph_style(text: str) -> str:
    return paragraph_xml(run_xml(text, half_points=10), style="CiteParagraph")


def with_a_run_in_the_cite_character_style(text: str) -> str:
    """Small print throughout, with the name and year in Verbatim's cite character style."""
    before, name, after = text.partition("Halvorsen 2019")
    return paragraph_xml(
        run_xml(before, half_points=10)
        + run_xml(name, character_style="Style13ptBold", half_points=10)
        + run_xml(after, half_points=10)
    )


def cut_to(characters: int) -> str:
    """The whole body cut to an exact length, ending on a letter and not on a space."""
    cut = WHOLE_BODY_IN_ONE_PARAGRAPH[:characters].rstrip()
    return cut + "s" * (characters - len(cut))


def parse_with_a_cite_paragraph_style(parser: DebateDocxParser, body: str) -> ParsedDocument:
    result = parse_bytes(parser, build_docx(body, styles_xml=STYLES_WITH_A_CITE_PARAGRAPH))
    assert isinstance(result, ParsedDocument), result
    return result


class TestABodyFiledAsTheCardsCite:
    """A body paragraph the classifier guesses to be a cite, before the card has any body.

    The rule from the first findings keeps such a paragraph in its card when a body is already
    open. The *first* body paragraph has no body open before it, so it was added to the card's
    cite, and a card whose whole body is that one paragraph was stored with no evidence text at
    all.
    """

    def test_a_body_paragraph_after_the_cards_cite_opens_the_body(self, parser: DebateDocxParser) -> None:
        document = parse(
            parser, tag_paragraph() + cite_paragraph() + small_print_paragraph(ELLIPSIS_AND_YEAR)
        )

        (card,) = document.cards
        assert card.tag == TAG
        assert card.full_cite == SHORT_CITE + CITE_TAIL
        assert card.evidence_text == ELLIPSIS_AND_YEAR
        assert card.completeness is CardCompleteness.FULL

    def test_a_whole_card_in_one_paragraph_under_its_cite_is_a_full_card(
        self, parser: DebateDocxParser
    ) -> None:
        """It was stored as cite-only: a tag, and a cite 2,000 characters long."""
        document = parse(
            parser, tag_paragraph() + cite_paragraph() + small_print_paragraph(WHOLE_BODY_IN_ONE_PARAGRAPH)
        )

        (card,) = document.cards
        assert card.full_cite == SHORT_CITE + CITE_TAIL
        assert card.short_cite == SHORT_CITE
        assert card.evidence_text == WHOLE_BODY_IN_ONE_PARAGRAPH
        assert card.completeness is CardCompleteness.FULL

    def test_the_rest_of_the_body_follows_it(self, parser: DebateDocxParser) -> None:
        body = (
            tag_paragraph()  # 0
            + cite_paragraph()  # 1
            + small_print_paragraph(ELLIPSIS_AND_YEAR)  # 2: read as a cite entry, and no body is open
            + marked_up_paragraph(SECOND_BODY)  # 3
            + underlined_small_print_paragraph(UNDERLINED_ELLIPSIS_AND_YEAR)  # 4: read as one too
        )
        document = parse(parser, body)

        (card,) = document.cards
        assert card.evidence_text == "\n".join(
            [ELLIPSIS_AND_YEAR, "".join(SECOND_BODY), "".join(UNDERLINED_ELLIPSIS_AND_YEAR)]
        )
        assert card.full_cite == SHORT_CITE + CITE_TAIL
        assert (card.provenance.first_element_index, card.provenance.last_element_index) == (0, 4)

    def test_each_paragraph_names_the_rule_that_reread_it(self, parser: DebateDocxParser) -> None:
        """The one that opens the body and the one inside it are two rules, and say which."""
        body = (
            tag_paragraph()
            + cite_paragraph()
            + small_print_paragraph(ELLIPSIS_AND_YEAR)
            + marked_up_paragraph(SECOND_BODY)
            + underlined_small_print_paragraph(UNDERLINED_ELLIPSIS_AND_YEAR)
        )
        document = parse(parser, body)

        opening, inside = document.sections[2], document.sections[4]
        assert opening.unit is StructuralUnit.EVIDENCE
        assert opening.match.rule_id == f"{AFTER_THE_CARDS_CITE}:heuristic-wiki-cite-entry"
        assert opening.match.match_source is StyleMatchSource.HEURISTIC
        assert opening.match.confidence <= 0.6
        assert inside.match.rule_id == f"{INSIDE_THE_BODY}:heuristic-wiki-cite-entry"
        assert document.cards[0].rule_ids == (
            "verbatim-style-id:Heading4",
            "heuristic-cite-line-author-year",
            f"{AFTER_THE_CARDS_CITE}:heuristic-wiki-cite-entry",
            "heuristic-marked-up-body-text",
            f"{INSIDE_THE_BODY}:heuristic-wiki-cite-entry",
        )

    @pytest.mark.parametrize("formatting", ["small print", "highlighted"])
    def test_a_first_body_paragraph_that_opens_with_a_year_opens_the_body(
        self, parser: DebateDocxParser, formatting: str
    ) -> None:
        """`In 2019 …` opens the way a short cite does. Under the card's cite, set as body, it is prose."""
        first = (
            small_print_paragraph(OPENS_WITH_A_YEAR)
            if formatting == "small print"
            else highlighted_paragraph(OPENS_WITH_A_YEAR)
        )
        document = parse(parser, tag_paragraph() + cite_paragraph() + first + marked_up_paragraph())

        (card,) = document.cards
        assert card.evidence_text == OPENS_WITH_A_YEAR + "\n" + "".join(MARKED_UP)
        assert card.full_cite == SHORT_CITE + CITE_TAIL
        assert document.sections[2].match.rule_id == (
            f"{AFTER_THE_CARDS_CITE}:heuristic-cite-line-author-year"
        )

    def test_its_underline_lands_on_its_own_words(self, parser: DebateDocxParser) -> None:
        """It is body now, so its spans are the card's."""
        body = (
            tag_paragraph()
            + cite_paragraph()
            + underlined_small_print_paragraph(UNDERLINED_ELLIPSIS_AND_YEAR)
        )
        (card,) = parse(parser, body).cards
        underlined = UNDERLINED_ELLIPSIS_AND_YEAR[1]

        assert card.evidence_text == "".join(UNDERLINED_ELLIPSIS_AND_YEAR)
        assert any(
            card.evidence_text[span.start_offset : span.end_offset] == underlined
            and span.start_offset == len(UNDERLINED_ELLIPSIS_AND_YEAR[0])
            for span in card.formatting_spans
        )

    def test_first_and_last_words_on_their_own_line_under_the_cite_are_the_abbreviated_body(
        self, parser: DebateDocxParser
    ) -> None:
        """Six words, a marker and five: a disclosure, whose words happen to name a study."""
        document = parse(
            parser,
            tag_paragraph() + cite_paragraph() + small_print_paragraph(FIRST_AND_LAST_WORDS_NAMING_A_STUDY),
        )

        (card,) = document.cards
        assert card.evidence_text == FIRST_AND_LAST_WORDS_NAMING_A_STUDY
        assert card.full_cite == SHORT_CITE + CITE_TAIL
        assert card.completeness is CardCompleteness.ABBREVIATED

    def test_a_card_with_a_cite_and_no_tag_gets_its_body_too(self, parser: DebateDocxParser) -> None:
        body = (
            paragraph_xml(run_xml("Sources"), style="Heading3")
            + cite_paragraph()
            + small_print_paragraph(ELLIPSIS_AND_YEAR)
        )
        (card,) = parse(parser, body).cards

        assert card.has_tag is False
        assert card.short_cite == SHORT_CITE
        assert card.evidence_text == ELLIPSIS_AND_YEAR
        assert card.completeness is CardCompleteness.FULL

    def test_a_real_cite_after_it_starts_the_next_card(self, parser: DebateDocxParser) -> None:
        """The body is open now, so a second cite under the tag is a second card, as it always was."""
        body = (
            tag_paragraph()
            + cite_paragraph()
            + small_print_paragraph(ELLIPSIS_AND_YEAR)
            + cite_paragraph("Ferreira 25", FERREIRA_TAIL)
            + marked_up_paragraph(SECOND_BODY)
        )
        document = parse(parser, body)

        assert [(card.tag, card.short_cite, card.evidence_text) for card in document.cards] == [
            (TAG, "Okonkwo 26", ELLIPSIS_AND_YEAR),
            ("", "Ferreira 25", "".join(SECOND_BODY)),
        ]


class TestALongGuessUnderATagWithNoCite:
    """The first paragraph under a tag, guessed to be a cite, with no cite before it.

    Nothing says where the card's cite ends, so only length can: a guess is re-read as the body
    when it is longer than 2,000 characters, which no paragraph the corpus marks as a cite reaches.
    """

    def test_the_fixture_is_past_the_bound_and_is_300_words(self) -> None:
        assert len(WHOLE_BODY_IN_ONE_PARAGRAPH) == 2104
        assert len(WHOLE_BODY_IN_ONE_PARAGRAPH.split()) == 355

    @pytest.mark.parametrize("formatting", ["small print", "highlighted"])
    def test_a_whole_card_in_one_paragraph_under_its_tag_is_the_cards_body(
        self, parser: DebateDocxParser, formatting: str
    ) -> None:
        paragraph = (
            small_print_paragraph(WHOLE_BODY_IN_ONE_PARAGRAPH)
            if formatting == "small print"
            else highlighted_paragraph(WHOLE_BODY_IN_ONE_PARAGRAPH)
        )
        document = parse(parser, tag_paragraph() + paragraph)

        (card,) = document.cards
        assert card.tag == TAG
        assert card.evidence_text == WHOLE_BODY_IN_ONE_PARAGRAPH
        assert card.full_cite == ""
        assert card.short_cite is None
        assert card.completeness is CardCompleteness.FULL
        assert document.sections[1].unit is StructuralUnit.EVIDENCE
        assert document.sections[1].match.rule_id == f"{LONGER_THAN_A_CITE}:heuristic-wiki-cite-entry"
        assert document.sections[1].match.confidence <= 0.6

    def test_the_paragraphs_under_it_are_the_same_body(self, parser: DebateDocxParser) -> None:
        document = parse(
            parser,
            tag_paragraph() + small_print_paragraph(WHOLE_BODY_IN_ONE_PARAGRAPH) + marked_up_paragraph(),
        )

        (card,) = document.cards
        assert card.evidence_text == WHOLE_BODY_IN_ONE_PARAGRAPH + "\n" + "".join(MARKED_UP)

    def test_a_guess_one_character_past_the_bound_is_the_body(self, parser: DebateDocxParser) -> None:
        text = cut_to(2001)
        assert len(text) == 2001

        (card,) = parse(parser, tag_paragraph() + small_print_paragraph(text)).cards

        assert (card.completeness, card.full_cite, card.evidence_text) == (CardCompleteness.FULL, "", text)

    def test_a_guess_at_the_bound_is_still_the_cards_cite(self, parser: DebateDocxParser) -> None:
        text = cut_to(2000)
        assert len(text) == 2000

        (card,) = parse(parser, tag_paragraph() + small_print_paragraph(text)).cards

        assert (card.completeness, card.full_cite, card.evidence_text) == (
            CardCompleteness.CITE_ONLY,
            text,
            "",
        )

    @pytest.mark.parametrize("entry", WIKI_CITE_ENTRIES)
    @pytest.mark.parametrize("formatting", ["small print", "highlighted"])
    def test_a_short_wiki_cite_entry_is_still_the_cards_cite(
        self, parser: DebateDocxParser, entry: str, formatting: str
    ) -> None:
        """A name, a year, first words, a marker and last words: the entry is the card's cite."""
        paragraph = (
            small_print_paragraph(entry) if formatting == "small print" else highlighted_paragraph(entry)
        )
        document = parse(parser, tag_paragraph() + paragraph)

        (card,) = document.cards
        assert card.full_cite == entry
        assert card.evidence_text == ""
        assert card.completeness is CardCompleteness.CITE_ONLY
        assert document.sections[1].match.rule_id == "heuristic-wiki-cite-entry"

    def test_a_long_first_paragraph_that_opens_with_a_name_and_a_year_is_still_the_cite(
        self, parser: DebateDocxParser
    ) -> None:
        """A cite and its card run together in one paragraph. The cite is in there, so it is left."""
        text = "Okonkwo 26, " + WHOLE_BODY_IN_ONE_PARAGRAPH
        (card,) = parse(parser, tag_paragraph() + small_print_paragraph(text)).cards

        assert card.short_cite == "Okonkwo 26"
        assert card.full_cite == text
        assert card.completeness is CardCompleteness.CITE_ONLY

    def test_a_long_guess_with_no_card_open_is_still_a_card_with_no_tag(
        self, parser: DebateDocxParser
    ) -> None:
        """No tag and no cite: re-read as body it would belong to no card and be dropped."""
        body = paragraph_xml(run_xml("Sources"), style="Heading3") + small_print_paragraph(
            WHOLE_BODY_IN_ONE_PARAGRAPH
        )
        (card,) = parse(parser, body).cards

        assert card.has_tag is False
        assert card.full_cite == WHOLE_BODY_IN_ONE_PARAGRAPH
        assert card.completeness is CardCompleteness.CITE_ONLY


class TestACiteThatDoesNotOpenTheBody:
    """What the rule leaves alone, in the place where it would otherwise act."""

    @pytest.mark.parametrize(
        "as_a_cite",
        [
            reading_size_paragraph(ELLIPSIS_AND_YEAR),
            behind_a_bold_opening(ELLIPSIS_AND_YEAR),
            behind_a_bold_opening(ELLIPSIS_AND_YEAR, highlight="yellow"),
        ],
        ids=["at reading size", "small print behind a bold opening", "highlighted behind a bold opening"],
    )
    def test_the_same_paragraph_formatted_as_a_cite_stays_a_cite(
        self, parser: DebateDocxParser, as_a_cite: str
    ) -> None:
        document = parse(parser, tag_paragraph() + cite_paragraph() + as_a_cite)

        (card,) = document.cards
        assert card.full_cite == SHORT_CITE + CITE_TAIL + "\n" + ELLIPSIS_AND_YEAR
        assert card.evidence_text == ""
        assert card.completeness is CardCompleteness.CITE_ONLY
        assert document.sections[2].unit is StructuralUnit.CITE
        assert document.sections[2].match.rule_id == "heuristic-wiki-cite-entry"

    @pytest.mark.parametrize("position", ["after the card's cite", "as the card's first cite"])
    def test_a_paragraph_of_300_words_in_a_cite_paragraph_style_stays_a_cite(
        self, parser: DebateDocxParser, position: str
    ) -> None:
        """The file's author said "cite". Small print and 355 words do not overrule that."""
        before = cite_paragraph() if position == "after the card's cite" else ""
        document = parse_with_a_cite_paragraph_style(
            parser, tag_paragraph() + before + in_a_cite_paragraph_style(WHOLE_BODY_IN_ONE_PARAGRAPH)
        )

        (card,) = document.cards
        assert card.full_cite.endswith(WHOLE_BODY_IN_ONE_PARAGRAPH)
        assert card.evidence_text == ""
        assert card.completeness is CardCompleteness.CITE_ONLY
        assert document.sections[-1].unit is StructuralUnit.CITE
        assert document.sections[-1].match.rule_id == "verbatim-style-id:CiteParagraph"

    @pytest.mark.parametrize("position", ["after the card's cite", "as the card's first cite"])
    def test_a_paragraph_of_300_words_with_a_run_in_the_cite_character_style_stays_a_cite(
        self, parser: DebateDocxParser, position: str
    ) -> None:
        """Past 1,000 characters the classifier's style rule lets go of it and its guess takes over.

        The guess is still about a paragraph the author marked with the cite style, so it stands.
        """
        before = cite_paragraph() if position == "after the card's cite" else ""
        document = parse(
            parser,
            tag_paragraph() + before + with_a_run_in_the_cite_character_style(WHOLE_BODY_IN_ONE_PARAGRAPH),
        )

        (card,) = document.cards
        assert card.full_cite.endswith(WHOLE_BODY_IN_ONE_PARAGRAPH)
        assert card.evidence_text == ""
        assert card.completeness is CardCompleteness.CITE_ONLY
        assert document.sections[-1].unit is StructuralUnit.CITE
        assert document.sections[-1].match.rule_id == "heuristic-wiki-cite-entry"

    @pytest.mark.parametrize(
        ("second", "second_text"),
        [
            (cite_paragraph("Ferreira 25", FERREIRA_TAIL), "Ferreira 25" + FERREIRA_TAIL),
            (
                paragraph_xml(
                    run_xml("Ferreira 25", character_style="Style13ptBold", half_points=16)
                    + run_xml(FERREIRA_TAIL, half_points=16)
                ),
                "Ferreira 25" + FERREIRA_TAIL,
            ),
            (
                paragraph_xml(
                    run_xml("Ferreira 25", bold=True, half_points=16) + run_xml(FERREIRA_TAIL, half_points=16)
                ),
                "Ferreira 25" + FERREIRA_TAIL,
            ),
            (
                paragraph_xml(
                    run_xml("Ferreira 25, Journal of Grid Studies, ", half_points=22)
                    + run_xml("example.invalid/grid", underline="single", half_points=22)
                ),
                "Ferreira 25, Journal of Grid Studies, example.invalid/grid",
            ),
        ],
        ids=[
            "a bold name",
            "the cite character style in small print",
            "a bold name in small print",
            "reading size with an underlined link",
        ],
    )
    def test_a_card_with_two_real_cites_keeps_both(
        self, parser: DebateDocxParser, second: str, second_text: str
    ) -> None:
        document = parse(parser, tag_paragraph() + cite_paragraph() + second + marked_up_paragraph())

        (card,) = document.cards
        assert card.full_cite == SHORT_CITE + CITE_TAIL + "\n" + second_text
        assert card.short_cite == SHORT_CITE
        assert card.evidence_text == "".join(MARKED_UP)
        assert [section.unit for section in document.sections] == [
            StructuralUnit.TAG,
            StructuralUnit.CITE,
            StructuralUnit.CITE,
            StructuralUnit.EVIDENCE,
        ]


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
