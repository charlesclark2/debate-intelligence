"""Sections, cards and provenance: what the parser makes of a whole file.

The file-shaped tests are here rather than in the fixture suite because each one is about a
single decision — a tag with no card under it, a cite with no body, a table cell, a card whose
body is two paragraphs — and a fixture that held all of them at once would fail for a dozen
reasons at a time. Goal criteria ac1, ac2, ac4 and the tables-and-text-boxes half of ac5 are
checked here; ac3 is in `test_runs.py`, and the template families are in
`test_structural_fixtures.py`.
"""

from __future__ import annotations

from datetime import date

import pytest

from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import (
    CardCompleteness,
    ParsedDocument,
    ParseFailure,
    ParseFailureReason,
)
from debate_core.domain.enums import ProvenanceMode, VerificationStatus
from debate_core.domain.style_profile import StructuralUnit, StyleMatchSource, StyleProfile
from debate_core.integrations.docx_parser.parser import DOCX_PARSER_VERSION, DebateDocxParser
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml

SOURCE_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
SNAPSHOT = date(2026, 9, 12)
DISCLOSURE_SNAPSHOT = date(2026, 9, 5)
SOURCE_PATH = "hsld26/Northside/AbCd/Neg-Invitational-Octas.docx"

# Invented for these tests. No real evidence, no real cite, no real team.
OPENING = "Grid operators in the region reported that demand from new data centres rose "
UNDERLINED = "faster than any other load category last year"
CLOSING = ", and the increase outpaced every scenario the utility had planned against."
CITE_TAIL = " (Journal of Grid Studies, 14 March 2026), example.invalid/grid"


def make_source(**overrides: object) -> SourceDocument:
    fields: dict[str, object] = {
        "sha256": SOURCE_SHA256,
        "byte_size": 48_000,
        "source_format": SourceFormat.DOCX,
        "origin": SourceOrigin.CASELIST_ARCHIVE,
        "caselist": "hsld26",
        "first_seen_snapshot": DISCLOSURE_SNAPSHOT,
        "last_seen_snapshot": SNAPSHOT,
    }
    fields.update(overrides)
    return SourceDocument.model_validate(fields)


def tag_paragraph(text: str = "Data centre demand collapses the reserve margin") -> str:
    return paragraph_xml(run_xml(text), style="Heading4")


def cite_paragraph(short: str = "Okonkwo 26", tail: str = CITE_TAIL) -> str:
    return paragraph_xml(run_xml(short, character_style="Style13ptBold") + run_xml(tail))


def evidence_paragraph(opening: str = OPENING, underlined: str = UNDERLINED, closing: str = CLOSING) -> str:
    return paragraph_xml(
        run_xml(opening, half_points=16)
        + run_xml(
            underlined,
            character_style="StyleUnderline",
            underline="single",
            highlight="cyan",
            half_points=22,
        )
        + run_xml(closing, half_points=16)
    )


VERBATIM_CARD = (
    paragraph_xml(run_xml("Data Centre Moratorium Negative"), style="Heading1")
    + paragraph_xml(run_xml("Grid Reliability"), style="Heading2")
    + paragraph_xml(run_xml("AT: Reserve Margin Turn"), style="Heading3")
    + tag_paragraph()
    + cite_paragraph()
    + evidence_paragraph()
)


@pytest.fixture
def parser(profile: StyleProfile) -> DebateDocxParser:
    return DebateDocxParser(profile)


def parse(parser: DebateDocxParser, body: str, **kwargs: object) -> ParsedDocument:
    """Parse a body and assert it came back as a document rather than a refusal."""
    source = kwargs.pop("source", None)
    result = parser.parse(
        build_docx(body),
        source if isinstance(source, SourceDocument) else make_source(),
        source_path=SOURCE_PATH,
        **kwargs,  # type: ignore[arg-type]
    )
    assert isinstance(result, ParsedDocument), result
    return result


# --------------------------------------------------------------------------------------------
# ac1: units and section paths
# --------------------------------------------------------------------------------------------


class TestUnitsAndSectionPaths:
    def test_every_verbatim_unit_resolves_through_its_own_style(self, parser: DebateDocxParser) -> None:
        document = parse(parser, VERBATIM_CARD)
        assert [section.unit for section in document.sections] == [
            StructuralUnit.POCKET,
            StructuralUnit.HAT,
            StructuralUnit.BLOCK,
            StructuralUnit.TAG,
            StructuralUnit.CITE,
            StructuralUnit.EVIDENCE,
        ]

    def test_every_section_records_the_rule_that_decided_it(self, parser: DebateDocxParser) -> None:
        document = parse(parser, VERBATIM_CARD)
        assert document.sections[0].match.rule_id == "verbatim-style-id:Heading1"
        assert document.sections[0].match.match_source is StyleMatchSource.VERBATIM
        assert document.sections[4].match.rule_id == "verbatim-cite-run-style"

    def test_a_section_path_holds_the_headings_still_open_above_it(self, parser: DebateDocxParser) -> None:
        document = parse(parser, VERBATIM_CARD)
        evidence = document.sections_of(StructuralUnit.EVIDENCE)[0]
        assert evidence.section_path == (
            "Data Centre Moratorium Negative",
            "Grid Reliability",
            "AT: Reserve Margin Turn",
            "Data centre demand collapses the reserve margin",
        )

    def test_a_heading_is_not_in_its_own_path(self, parser: DebateDocxParser) -> None:
        document = parse(parser, VERBATIM_CARD)
        assert document.sections[0].section_path == ()
        assert document.sections[1].section_path == ("Data Centre Moratorium Negative",)

    def test_a_new_hat_closes_the_blocks_and_tags_under_the_old_one(self, parser: DebateDocxParser) -> None:
        body = VERBATIM_CARD + paragraph_xml(run_xml("Cost"), style="Heading2") + evidence_paragraph()
        document = parse(parser, body)
        assert document.sections[-1].section_path == ("Data Centre Moratorium Negative", "Cost")

    def test_an_alias_style_resolves_and_says_it_was_an_alias(self, parser: DebateDocxParser) -> None:
        """`Analytics` is `Analytic` with a plural `s`; Word's digit-stripping does not reach it."""
        body = paragraph_xml(run_xml("They have no evidence for this claim."), style="Analytics")
        document = parse(parser, body)
        assert document.sections[0].unit is StructuralUnit.ANALYTIC
        assert document.sections[0].match.match_source is StyleMatchSource.VERBATIM_ALIAS


# --------------------------------------------------------------------------------------------
# ac2: cards
# --------------------------------------------------------------------------------------------


class TestCardAssembly:
    def test_a_tag_a_cite_and_a_body_become_one_card(self, parser: DebateDocxParser) -> None:
        document = parse(parser, VERBATIM_CARD)
        assert document.card_count == 1
        card = document.cards[0]
        assert card.tag == "Data centre demand collapses the reserve margin"
        assert card.evidence_text == OPENING + UNDERLINED + CLOSING
        assert card.completeness is CardCompleteness.FULL

    def test_the_short_cite_is_split_off_the_front_of_the_full_cite(self, parser: DebateDocxParser) -> None:
        card = parse(parser, VERBATIM_CARD).cards[0]
        assert card.short_cite == "Okonkwo 26"
        assert card.full_cite == "Okonkwo 26" + CITE_TAIL

    def test_a_cite_the_pattern_does_not_recognise_gets_no_short_cite(self, parser: DebateDocxParser) -> None:
        """An invented short cite would be repeated back to a debater as fact."""
        body = (
            tag_paragraph()
            + paragraph_xml(
                run_xml("[no author given]", character_style="Style13ptBold")
                + run_xml(", an unsigned briefing note")
            )
            + evidence_paragraph()
        )
        assert parse(parser, body).cards[0].short_cite is None

    def test_a_cards_body_may_run_across_several_paragraphs(self, parser: DebateDocxParser) -> None:
        body = tag_paragraph() + cite_paragraph() + evidence_paragraph() + evidence_paragraph()
        card = parse(parser, body).cards[0]
        assert card.evidence_text.count(UNDERLINED) == 2
        assert "\n" in card.evidence_text

    def test_spans_land_on_the_joined_body(self, parser: DebateDocxParser) -> None:
        body = tag_paragraph() + cite_paragraph() + evidence_paragraph() + evidence_paragraph()
        card = parse(parser, body).cards[0]
        underlines = [span for span in card.formatting_spans if span.emphasis.value == "UNDERLINE"]
        assert len(underlines) == 2
        for span in underlines:
            assert card.evidence_text[span.start_offset : span.end_offset] == UNDERLINED

    def test_a_tag_with_no_cite_and_no_evidence_is_an_analytic(self, parser: DebateDocxParser) -> None:
        """`Heading4` is what a debater types for a line of analysis too. Goal criterion ac2."""
        body = (
            paragraph_xml(run_xml("AT: Reserve Margin Turn"), style="Heading3")
            + tag_paragraph("Their evidence is from before the load growth began")
            + paragraph_xml(run_xml("Grid Reliability"), style="Heading2")
        )
        document = parse(parser, body)
        assert document.sections[1].unit is StructuralUnit.ANALYTIC
        assert document.sections[1].match.rule_id.startswith("assembly-tag-without-cite-or-evidence")
        assert document.cards == ()

    def test_an_undertag_belongs_to_the_tag_above_it_and_starts_no_new_card(
        self, parser: DebateDocxParser
    ) -> None:
        body = (
            tag_paragraph()
            + paragraph_xml(run_xml("And the margin is already thin"), style="Undertag")
            + cite_paragraph()
            + evidence_paragraph()
        )
        document = parse(parser, body)
        assert document.card_count == 1
        assert document.cards[0].undertag == "And the margin is already thin"

    def test_two_tags_produce_two_cards(self, parser: DebateDocxParser) -> None:
        body = (
            tag_paragraph("First claim")
            + cite_paragraph("Okonkwo 26")
            + evidence_paragraph()
            + tag_paragraph("Second claim")
            + cite_paragraph("Ferreira 25")
            + evidence_paragraph()
        )
        document = parse(parser, body)
        assert [card.tag for card in document.cards] == ["First claim", "Second claim"]
        assert [card.short_cite for card in document.cards] == ["Okonkwo 26", "Ferreira 25"]


class TestCompleteness:
    def test_a_wiki_converted_card_is_abbreviated_rather_than_padded_or_dropped(
        self, parser: DebateDocxParser
    ) -> None:
        """An opencaselist disclosure records the first and last words and an ellipsis between."""
        body = (
            tag_paragraph()
            + cite_paragraph()
            + evidence_paragraph(
                opening="Grid operators in the region reported ",
                underlined="…",
                closing=" thinner than at any point in the past decade.",
            )
        )
        card = parse(parser, body).cards[0]
        assert card.completeness is CardCompleteness.ABBREVIATED
        assert card.is_abbreviated
        assert "…" in card.evidence_text

    def test_a_tag_and_a_cite_with_no_body_is_cite_only(self, parser: DebateDocxParser) -> None:
        body = (
            tag_paragraph() + cite_paragraph() + paragraph_xml(run_xml("Grid Reliability"), style="Heading2")
        )
        card = parse(parser, body).cards[0]
        assert card.completeness is CardCompleteness.CITE_ONLY
        assert card.evidence_text == ""
        assert card.formatting_spans == ()

    def test_a_cite_with_no_tag_above_it_still_makes_a_card(self, parser: DebateDocxParser) -> None:
        """Ordinary in a wiki-converted disclosure, where the tag was not carried across."""
        document = parse(parser, cite_paragraph() + evidence_paragraph())
        assert document.card_count == 1
        assert document.cards[0].tag == ""

    def test_a_stray_body_with_no_cite_and_no_tag_is_not_a_card(self, parser: DebateDocxParser) -> None:
        document = parse(parser, evidence_paragraph())
        assert document.cards == ()
        assert document.sections[0].unit is StructuralUnit.EVIDENCE


# --------------------------------------------------------------------------------------------
# ac4: provenance
# --------------------------------------------------------------------------------------------


class TestProvenance:
    def test_a_card_records_the_file_the_caselist_and_the_snapshot(self, parser: DebateDocxParser) -> None:
        provenance = parse(parser, VERBATIM_CARD).cards[0].provenance
        assert provenance.provenance_mode is ProvenanceMode.FILE_IMPORT
        assert provenance.source_sha256 == SOURCE_SHA256
        assert provenance.source_path == SOURCE_PATH
        assert provenance.caselist == "hsld26"
        assert provenance.snapshot == SNAPSHOT

    def test_a_caller_may_name_the_snapshot_the_file_was_read_under(self, parser: DebateDocxParser) -> None:
        """A file read for one disclosure belongs to that disclosure's snapshot, not the latest."""
        provenance = parse(parser, VERBATIM_CARD, snapshot=DISCLOSURE_SNAPSHOT).cards[0].provenance
        assert provenance.snapshot == DISCLOSURE_SNAPSHOT

    def test_a_camp_file_records_its_camp_and_no_caselist(self, parser: DebateDocxParser) -> None:
        source = make_source(origin=SourceOrigin.OPENEV, caselist=None)
        provenance = parse(parser, VERBATIM_CARD, source=source, camp="Northwestern").cards[0].provenance
        assert provenance.camp == "Northwestern"
        assert provenance.caselist is None

    def test_the_element_range_covers_the_paragraphs_the_card_was_built_from(
        self, parser: DebateDocxParser
    ) -> None:
        provenance = parse(parser, VERBATIM_CARD).cards[0].provenance
        assert (provenance.first_element_index, provenance.last_element_index) == (3, 5)

    def test_the_parser_and_profile_versions_are_recorded(
        self, parser: DebateDocxParser, profile: StyleProfile
    ) -> None:
        document = parse(parser, VERBATIM_CARD)
        assert document.parser_version == DOCX_PARSER_VERSION
        assert document.profile_version == profile.profile_version
        assert document.cards[0].provenance.parser_version == DOCX_PARSER_VERSION
        assert document.cards[0].provenance.profile_version == profile.profile_version

    def test_an_imported_card_is_never_verified(self, parser: DebateDocxParser) -> None:
        assert parse(parser, VERBATIM_CARD).cards[0].verification_status is (VerificationStatus.UNVERIFIED)

    def test_a_verbatim_cards_body_is_found_by_its_markup_rather_than_by_a_style(
        self, parser: DebateDocxParser
    ) -> None:
        """Which is why even a perfectly styled Verbatim card reports a heuristic match.

        Verbatim gives a card's body no paragraph style of its own, so the body step is always a
        heuristic and the card reports the weakest step it was built from. The detail a reader
        actually wants is in `rule_ids`.
        """
        card = parse(parser, VERBATIM_CARD).cards[0]
        assert card.match_source is StyleMatchSource.HEURISTIC
        assert card.confidence == pytest.approx(0.75)
        assert card.rule_ids == (
            "verbatim-style-id:Heading4",
            "verbatim-cite-run-style",
            "heuristic-marked-up-body-text",
        )

    def test_a_card_reports_the_weakest_match_that_built_it(self, parser: DebateDocxParser) -> None:
        """A cite found only by its shape drags the card's confidence below its body's."""
        body = tag_paragraph() + paragraph_xml(run_xml("Okonkwo 26, a briefing note")) + evidence_paragraph()
        card = parse(parser, body).cards[0]
        assert card.match_source is StyleMatchSource.HEURISTIC
        assert card.confidence == pytest.approx(0.6)
        assert card.rule_ids == (
            "verbatim-style-id:Heading4",
            "heuristic-cite-line-author-year",
            "heuristic-marked-up-body-text",
        )


# --------------------------------------------------------------------------------------------
# ac5: tables, text boxes, and what is refused
# --------------------------------------------------------------------------------------------


class TestTablesAndTextBoxes:
    def test_a_table_cell_is_other_however_much_it_looks_like_a_tag(self, parser: DebateDocxParser) -> None:
        body = (
            "<w:tbl><w:tr><w:tc>"
            + paragraph_xml(run_xml("Speech times"), style="Heading4")
            + "</w:tc><w:tc>"
            + paragraph_xml(run_xml("6 minutes"))
            + "</w:tc></w:tr></w:tbl>"
        )
        document = parse(parser, body)
        assert [section.unit for section in document.sections] == [
            StructuralUnit.OTHER,
            StructuralUnit.OTHER,
        ]
        assert document.sections[0].match.rule_id == "assembly-table-cell"
        assert all(section.in_table for section in document.sections)
        assert document.cards == ()

    def test_a_text_box_is_other_and_is_read_once(self, parser: DebateDocxParser) -> None:
        box = "<w:txbxContent>" + paragraph_xml(run_xml("Northside Debate")) + "</w:txbxContent>"
        body = (
            "<w:p><w:r><w:t>body text</w:t>"
            f'<mc:AlternateContent><mc:Choice Requires="wps">{box}</mc:Choice>'
            f"<mc:Fallback>{box}</mc:Fallback></mc:AlternateContent>"
            "</w:r></w:p>"
        )
        document = parse(parser, body)
        text_box_sections = [
            section for section in document.sections if section.match.rule_id == "assembly-text-box"
        ]
        assert len(text_box_sections) == 1
        assert text_box_sections[0].unit is StructuralUnit.OTHER
        assert text_box_sections[0].text == "Northside Debate"

    def test_sections_stay_in_document_order_across_tables_and_text_boxes(
        self, parser: DebateDocxParser
    ) -> None:
        body = (
            VERBATIM_CARD
            + "<w:tbl><w:tr><w:tc>"
            + paragraph_xml(run_xml("Speech times"))
            + "</w:tc></w:tr></w:tbl>"
        )
        document = parse(parser, body)
        indices = [section.element_index for section in document.sections]
        assert indices == sorted(indices) == list(range(len(indices)))


class TestRefusals:
    def test_a_pdf_source_is_refused_before_the_bytes_are_opened(self, parser: DebateDocxParser) -> None:
        result = parser.parse(
            b"%PDF-1.7", make_source(source_format=SourceFormat.PDF), source_path=SOURCE_PATH
        )
        assert isinstance(result, ParseFailure)
        assert result.reason is ParseFailureReason.UNSUPPORTED_FORMAT

    def test_a_legacy_doc_source_is_refused(self, parser: DebateDocxParser) -> None:
        result = parser.parse(
            b"\xd0\xcf\x11\xe0", make_source(source_format=SourceFormat.DOC), source_path=SOURCE_PATH
        )
        assert isinstance(result, ParseFailure)
        assert result.reason is ParseFailureReason.UNSUPPORTED_FORMAT

    def test_a_malformed_package_yields_a_failure_and_no_partial_document(
        self, parser: DebateDocxParser
    ) -> None:
        result = parser.parse(b"not a zip at all", make_source(), source_path=SOURCE_PATH)
        assert isinstance(result, ParseFailure)
        assert result.reason is ParseFailureReason.NOT_A_ZIP
        assert result.parser_version == DOCX_PARSER_VERSION

    def test_a_macro_enabled_package_yields_a_failure(self, parser: DebateDocxParser) -> None:
        content = build_docx(VERBATIM_CARD, extra_parts={"word/vbaProject.bin": b"\x00"})
        result = parser.parse(content, make_source(), source_path=SOURCE_PATH)
        assert isinstance(result, ParseFailure)
        assert result.reason is ParseFailureReason.MACRO_ENABLED


class TestTrackedChangesInACard:
    def test_an_insertion_is_in_the_card_and_a_deletion_is_not(self, parser: DebateDocxParser) -> None:
        body = (
            tag_paragraph()
            + cite_paragraph()
            + "<w:p>"
            + '<w:r><w:rPr><w:sz w:val="22"/></w:rPr><w:t xml:space="preserve">demand rose </w:t></w:r>'
            + '<w:ins w:id="1" w:author="a" w:date="2026-03-14T00:00:00Z">'
            + '<w:r><w:rPr><w:sz w:val="22"/></w:rPr><w:t xml:space="preserve">sharply </w:t></w:r></w:ins>'
            + '<w:del w:id="2" w:author="a" w:date="2026-03-14T00:00:00Z">'
            + "<w:r><w:delText>slightly </w:delText></w:r></w:del>"
            + '<w:r><w:rPr><w:sz w:val="22"/><w:u w:val="single"/></w:rPr>'
            + "<w:t>last year across every planning scenario the utility had on file.</w:t></w:r>"
            + "</w:p>"
        )
        document = parse(parser, body)
        card = document.cards[0]
        assert "sharply" in card.evidence_text
        assert "slightly" not in card.evidence_text
        assert any("tracked deletion" in warning for warning in document.warnings)


class TestDeterminism:
    def test_the_same_bytes_produce_the_same_document_twice(self, parser: DebateDocxParser) -> None:
        """No clock, no random source, no model call: a re-parse is a byte-identical claim."""
        content = build_docx(VERBATIM_CARD)
        source = make_source()
        first = parser.parse(content, source, source_path=SOURCE_PATH)
        second = parser.parse(content, source, source_path=SOURCE_PATH)
        assert first == second
