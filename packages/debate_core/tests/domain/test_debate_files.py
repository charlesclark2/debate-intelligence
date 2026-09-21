"""The parse output model: what it refuses, and that it survives a JSON round-trip.

These models are the contract between the parser and everything downstream — the fingerprinter,
the parse pipeline's card store, the accuracy evaluation and V3's upload persistence. Two things
therefore matter more than usual and are tested here rather than inside the parser:

* the invariants that keep a parsed card honest — an offset that runs past the end of the text it
  indexes, a card that claims to be verified, a CITE_ONLY card with a body;
* the JSON round-trip, because the pipeline writes these as JSONL and reads them back, and a
  lossy round-trip would silently rewrite provenance.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import pytest
from pydantic import ValidationError

from debate_core.domain.base import DomainModel
from debate_core.domain.caselist import SourceOrigin
from debate_core.domain.debate_files import (
    CardCompleteness,
    FileImportProvenance,
    FileSection,
    FontSizeSpan,
    FormattingSpan,
    ParsedCard,
    ParsedDocument,
    ParseFailure,
    ParseFailureReason,
)
from debate_core.domain.enums import ProvenanceMode, VerificationStatus
from debate_core.domain.style_profile import (
    ParagraphStyleMatch,
    RunEmphasis,
    StructuralUnit,
    StyleMatchSource,
)

SOURCE_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
OTHER_SHA256 = "5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03"
SNAPSHOT = date(2026, 9, 12)
PARSER_VERSION = "2026.09.20-docx-1"
PROFILE_VERSION = "2026.09.20-verbatim-1"

EVIDENCE = (
    "Grid operators in the region reported that demand from new data centres rose faster than any "
    "other load category last year."
)


def make_provenance(**overrides: object) -> FileImportProvenance:
    """Provenance for a card disclosed on a caselist, for tests that vary one thing about it."""
    fields: dict[str, object] = {
        "source_sha256": SOURCE_SHA256,
        "source_path": "hsld26/Northside/AbCd/Neg-Invitational-Octas.docx",
        "origin": SourceOrigin.CASELIST_ARCHIVE,
        "caselist": "hsld26",
        "snapshot": SNAPSHOT,
        "first_element_index": 3,
        "last_element_index": 5,
        "parser_version": PARSER_VERSION,
        "profile_version": PROFILE_VERSION,
    }
    fields.update(overrides)
    return FileImportProvenance.model_validate(fields)


def make_card(**overrides: object) -> ParsedCard:
    """A full card, for tests that vary one thing about it."""
    fields: dict[str, object] = {
        "tag": "Data centre demand collapses the reserve margin",
        "short_cite": "Okonkwo 26",
        "full_cite": "Okonkwo 26 (Adaeze Okonkwo, Journal of Grid Studies, 14 March 2026).",
        "evidence_text": EVIDENCE,
        "completeness": CardCompleteness.FULL,
        "section_path": ("Data Centre Moratorium Negative", "Grid Reliability"),
        "formatting_spans": (
            FormattingSpan(
                emphasis=RunEmphasis.UNDERLINE,
                start_offset=0,
                end_offset=20,
                rule_id="verbatim-style-id:StyleUnderline",
                match_source=StyleMatchSource.VERBATIM,
            ),
        ),
        "font_size_spans": (FontSizeSpan(start_offset=0, end_offset=len(EVIDENCE), half_points=22),),
        "match_source": StyleMatchSource.VERBATIM,
        "confidence": 1.0,
        "rule_ids": ("verbatim-style-id:Heading4", "verbatim-cite-run-style"),
        "provenance": make_provenance(),
    }
    fields.update(overrides)
    return ParsedCard.model_validate(fields)


def make_section(**overrides: object) -> FileSection:
    """One classified paragraph, for tests that vary one thing about it."""
    fields: dict[str, object] = {
        "unit": StructuralUnit.EVIDENCE,
        "text": EVIDENCE,
        "section_path": ("Data Centre Moratorium Negative",),
        "match": ParagraphStyleMatch(
            unit=StructuralUnit.EVIDENCE,
            rule_id="verbatim-style-id:CardBody",
            match_source=StyleMatchSource.VERBATIM,
        ),
        "element_index": 5,
    }
    fields.update(overrides)
    return FileSection.model_validate(fields)


# --------------------------------------------------------------------------------------------
# Spans
# --------------------------------------------------------------------------------------------


class TestFormattingSpan:
    def test_a_span_must_cover_at_least_one_character(self) -> None:
        with pytest.raises(ValidationError, match="must be before end_offset"):
            FormattingSpan(
                emphasis=RunEmphasis.BOLD,
                start_offset=7,
                end_offset=7,
                rule_id="direct-bold",
                match_source=StyleMatchSource.VERBATIM,
            )

    def test_a_highlight_span_names_its_colour(self) -> None:
        with pytest.raises(ValidationError, match="must name the highlight colour"):
            FormattingSpan(
                emphasis=RunEmphasis.HIGHLIGHT,
                start_offset=0,
                end_offset=4,
                rule_id="direct-highlight:cyan",
                match_source=StyleMatchSource.VERBATIM,
            )

    def test_only_a_highlight_span_carries_a_colour(self) -> None:
        with pytest.raises(ValidationError, match="only a HIGHLIGHT span carries a colour"):
            FormattingSpan(
                emphasis=RunEmphasis.UNDERLINE,
                start_offset=0,
                end_offset=4,
                highlight_color="cyan",
                rule_id="direct-underline",
                match_source=StyleMatchSource.VERBATIM,
            )

    def test_length_is_the_number_of_characters_covered(self) -> None:
        span = FormattingSpan(
            emphasis=RunEmphasis.EMPHASIS,
            start_offset=4,
            end_offset=11,
            rule_id="verbatim-style-id:Emphasis",
            match_source=StyleMatchSource.VERBATIM,
        )
        assert span.length == 7

    def test_a_font_size_span_must_cover_at_least_one_character(self) -> None:
        with pytest.raises(ValidationError, match="must be before end_offset"):
            FontSizeSpan(start_offset=3, end_offset=2, half_points=16)


# --------------------------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------------------------


class TestFileImportProvenance:
    def test_a_parsed_card_is_always_file_import(self) -> None:
        with pytest.raises(ValidationError, match="always FILE_IMPORT"):
            make_provenance(provenance_mode=ProvenanceMode.PUBLISHER_RETRIEVED)

    def test_the_default_provenance_mode_is_file_import(self) -> None:
        assert make_provenance().provenance_mode is ProvenanceMode.FILE_IMPORT

    def test_a_caselist_card_names_its_caselist(self) -> None:
        with pytest.raises(ValidationError, match="must name its caselist"):
            make_provenance(caselist=None)

    def test_a_camp_card_names_a_camp_and_no_caselist(self) -> None:
        provenance = make_provenance(origin=SourceOrigin.OPENEV, caselist=None, camp="Northwestern")
        assert provenance.camp == "Northwestern"
        assert provenance.caselist is None

    def test_a_camp_card_may_not_claim_a_caselist(self) -> None:
        with pytest.raises(ValidationError, match="belongs to a camp, not to a caselist"):
            make_provenance(origin=SourceOrigin.OPENEV, caselist="hsld26")

    def test_the_element_range_runs_forwards(self) -> None:
        with pytest.raises(ValidationError, match="precedes first_element_index"):
            make_provenance(first_element_index=9, last_element_index=4)

    def test_one_paragraph_is_a_legal_range(self) -> None:
        assert make_provenance(first_element_index=4, last_element_index=4).last_element_index == 4


# --------------------------------------------------------------------------------------------
# Cards
# --------------------------------------------------------------------------------------------


class TestParsedCard:
    def test_an_imported_card_is_unverified(self) -> None:
        assert make_card().verification_status is VerificationStatus.UNVERIFIED

    def test_an_imported_card_cannot_claim_to_be_verified(self) -> None:
        with pytest.raises(ValidationError, match="has not been verified"):
            make_card(verification_status=VerificationStatus.VERIFIED)

    def test_a_span_may_not_run_past_the_end_of_the_evidence(self) -> None:
        with pytest.raises(ValidationError, match="runs past the end"):
            make_card(
                formatting_spans=(
                    FormattingSpan(
                        emphasis=RunEmphasis.UNDERLINE,
                        start_offset=0,
                        end_offset=len(EVIDENCE) + 1,
                        rule_id="verbatim-style-id:StyleUnderline",
                        match_source=StyleMatchSource.VERBATIM,
                    ),
                )
            )

    def test_a_font_size_span_may_not_run_past_the_end_of_the_evidence(self) -> None:
        with pytest.raises(ValidationError, match="runs past the end"):
            make_card(
                font_size_spans=(FontSizeSpan(start_offset=0, end_offset=len(EVIDENCE) + 4, half_points=16),)
            )

    def test_a_cite_only_card_has_no_body(self) -> None:
        card = make_card(
            completeness=CardCompleteness.CITE_ONLY,
            evidence_text="",
            formatting_spans=(),
            font_size_spans=(),
        )
        assert card.is_abbreviated

    def test_a_cite_only_card_that_carries_a_body_is_a_contradiction(self) -> None:
        with pytest.raises(ValidationError, match="CITE_ONLY card has no body"):
            make_card(completeness=CardCompleteness.CITE_ONLY)

    def test_a_card_with_no_body_must_say_it_is_cite_only(self) -> None:
        with pytest.raises(ValidationError, match="it is CITE_ONLY"):
            make_card(evidence_text="", formatting_spans=(), font_size_spans=())

    def test_an_abbreviated_card_is_not_full(self) -> None:
        card = make_card(
            completeness=CardCompleteness.ABBREVIATED,
            evidence_text="Grid operators reported … thinner than at any point in the past decade.",
            formatting_spans=(),
            font_size_spans=(),
        )
        assert card.is_abbreviated
        assert card.completeness is CardCompleteness.ABBREVIATED

    def test_a_full_card_is_not_abbreviated(self) -> None:
        assert not make_card().is_abbreviated


# --------------------------------------------------------------------------------------------
# Sections and documents
# --------------------------------------------------------------------------------------------


class TestFileSection:
    def test_a_section_and_its_match_must_agree_on_the_unit(self) -> None:
        with pytest.raises(ValidationError, match="one of them is wrong"):
            make_section(unit=StructuralUnit.TAG)

    def test_a_span_may_not_run_past_the_end_of_the_paragraph(self) -> None:
        with pytest.raises(ValidationError, match="runs past the end"):
            make_section(
                formatting_spans=(
                    FormattingSpan(
                        emphasis=RunEmphasis.BOLD,
                        start_offset=0,
                        end_offset=len(EVIDENCE) + 10,
                        rule_id="direct-bold",
                        match_source=StyleMatchSource.VERBATIM,
                    ),
                )
            )


class TestParsedDocument:
    def test_sections_must_be_in_document_order(self) -> None:
        with pytest.raises(ValidationError, match="in document order"):
            ParsedDocument(
                source_sha256=SOURCE_SHA256,
                source_path="hsld26/Northside/AbCd/Neg.docx",
                parser_version=PARSER_VERSION,
                profile_version=PROFILE_VERSION,
                sections=(make_section(element_index=7), make_section(element_index=2)),
            )

    def test_a_card_must_belong_to_the_document_that_holds_it(self) -> None:
        with pytest.raises(ValidationError, match="but the document is"):
            ParsedDocument(
                source_sha256=OTHER_SHA256,
                source_path="hsld26/Northside/AbCd/Neg.docx",
                parser_version=PARSER_VERSION,
                profile_version=PROFILE_VERSION,
                cards=(make_card(),),
            )

    def test_sections_of_filters_by_unit_in_document_order(self) -> None:
        document = ParsedDocument(
            source_sha256=SOURCE_SHA256,
            source_path="hsld26/Northside/AbCd/Neg.docx",
            parser_version=PARSER_VERSION,
            profile_version=PROFILE_VERSION,
            sections=(
                make_section(element_index=1),
                make_section(
                    element_index=2,
                    unit=StructuralUnit.TAG,
                    text="Data centre demand collapses the reserve margin",
                    match=ParagraphStyleMatch(
                        unit=StructuralUnit.TAG,
                        rule_id="verbatim-style-id:Heading4",
                        match_source=StyleMatchSource.VERBATIM,
                    ),
                ),
                make_section(element_index=3),
            ),
            cards=(make_card(),),
        )
        assert [section.element_index for section in document.sections_of(StructuralUnit.EVIDENCE)] == [1, 3]
        assert document.card_count == 1


class TestParseFailure:
    def test_a_failure_records_a_reason_and_the_parser_that_refused(self) -> None:
        failure = ParseFailure(
            source_sha256=SOURCE_SHA256,
            source_path="hsld26/Northside/AbCd/Neg.pdf",
            reason=ParseFailureReason.UNSUPPORTED_FORMAT,
            detail="PDF is stored unparsed in V1",
            parser_version=PARSER_VERSION,
        )
        assert failure.reason is ParseFailureReason.UNSUPPORTED_FORMAT
        assert failure.parser_version == PARSER_VERSION


# --------------------------------------------------------------------------------------------
# JSON round-trip
# --------------------------------------------------------------------------------------------


PARSE_MODELS: tuple[Callable[[], DomainModel], ...] = (
    make_provenance,
    make_card,
    make_section,
    lambda: ParsedDocument(
        source_sha256=SOURCE_SHA256,
        source_path="hsld26/Northside/AbCd/Neg-Invitational-Octas.docx",
        parser_version=PARSER_VERSION,
        profile_version=PROFILE_VERSION,
        sections=(make_section(),),
        cards=(make_card(),),
        warnings=("one text box was read as OTHER",),
    ),
    lambda: ParseFailure(
        source_sha256=SOURCE_SHA256,
        source_path="hsld26/Northside/AbCd/Neg.doc",
        reason=ParseFailureReason.UNSUPPORTED_FORMAT,
        parser_version=PARSER_VERSION,
    ),
)


@pytest.mark.parametrize("build", PARSE_MODELS, ids=lambda build: build().__class__.__name__)
def test_every_parse_model_survives_a_json_round_trip(build: Callable[[], DomainModel]) -> None:
    """Dump to JSON, load it back, and get an equal object.

    The parse pipeline writes cards as JSONL and reads them back to fingerprint them; a field that
    did not survive would take a card's provenance with it.
    """
    original = build()
    restored = type(original).model_validate_json(original.model_dump_json())
    assert restored == original


def test_a_round_tripped_card_keeps_its_offsets_pointing_at_the_same_text() -> None:
    """The offsets are the whole point: a span must still select the same characters."""
    card = make_card()
    restored = ParsedCard.model_validate_json(card.model_dump_json())
    span = restored.formatting_spans[0]
    assert restored.evidence_text[span.start_offset : span.end_offset] == "Grid operators in th"
