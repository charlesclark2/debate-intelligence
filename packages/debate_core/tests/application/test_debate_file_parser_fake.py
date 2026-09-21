"""The in-memory `DebateFileParser`, and that it really conforms to the port.

The parse pipeline (`v1-e31-t06`), the fingerprinter (`v1-e31-t04`) and V3's upload handler are
all written against :class:`~debate_core.application.ports.debate_files.DebateFileParser`, and
their tests use this fake rather than building `.docx` packages. What is checked here is what
those tests rely on: that a refusal comes back as a value, that a registered document is returned
unchanged, and that the fake's signature has not drifted from the Protocol.
"""

from __future__ import annotations

from datetime import date

from debate_core.application.ports import DebateFileParser
from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import (
    CardCompleteness,
    FileImportProvenance,
    ParseFailureReason,
    ParsedCard,
    ParsedDocument,
)
from debate_core.domain.style_profile import StyleMatchSource
from debate_core.testing import FakeDebateFileParser, build_fake_debate_file_parser

SOURCE_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
SNAPSHOT = date(2026, 9, 12)
SOURCE_PATH = "hsld26/Northside/AbCd/Neg-Invitational-Octas.docx"


def make_source(**overrides: object) -> SourceDocument:
    fields: dict[str, object] = {
        "sha256": SOURCE_SHA256,
        "byte_size": 48_000,
        "source_format": SourceFormat.DOCX,
        "origin": SourceOrigin.CASELIST_ARCHIVE,
        "caselist": "hsld26",
        "first_seen_snapshot": SNAPSHOT,
        "last_seen_snapshot": SNAPSHOT,
    }
    fields.update(overrides)
    return SourceDocument.model_validate(fields)


def test_the_fake_conforms_to_the_port() -> None:
    """`build_fake_debate_file_parser` is annotated as the Protocol, so pyright checks it too."""
    port: DebateFileParser = build_fake_debate_file_parser()
    assert isinstance(port, DebateFileParser)
    assert port.parser_version


def test_an_unregistered_docx_reads_as_a_document_with_no_cards() -> None:
    parser = FakeDebateFileParser()
    result = parser.parse(b"PK\x03\x04", make_source(), source_path=SOURCE_PATH)
    assert isinstance(result, ParsedDocument)
    assert result.cards == ()
    assert result.source_sha256 == SOURCE_SHA256


def test_a_pdf_is_refused_rather_than_read() -> None:
    parser = FakeDebateFileParser()
    result = parser.parse(b"%PDF-1.7", make_source(source_format=SourceFormat.PDF), source_path=SOURCE_PATH)
    assert not isinstance(result, ParsedDocument)
    assert result.reason is ParseFailureReason.UNSUPPORTED_FORMAT


def test_an_empty_file_is_refused() -> None:
    parser = FakeDebateFileParser()
    result = parser.parse(b"", make_source(), source_path=SOURCE_PATH)
    assert not isinstance(result, ParsedDocument)
    assert result.reason is ParseFailureReason.NOT_A_ZIP


def test_a_registered_document_comes_back_unchanged_and_the_call_is_recorded() -> None:
    parser = FakeDebateFileParser()
    document = ParsedDocument(
        source_sha256=SOURCE_SHA256,
        source_path=SOURCE_PATH,
        parser_version=parser.parser_version,
        profile_version="fake-profile-1",
        cards=(
            ParsedCard(
                tag="Data centre demand collapses the reserve margin",
                short_cite="Okonkwo 26",
                full_cite="Okonkwo 26 (Journal of Grid Studies, 14 March 2026).",
                evidence_text="Demand rose faster than any other load category last year.",
                completeness=CardCompleteness.FULL,
                match_source=StyleMatchSource.VERBATIM,
                confidence=1.0,
                provenance=FileImportProvenance(
                    source_sha256=SOURCE_SHA256,
                    source_path=SOURCE_PATH,
                    origin=SourceOrigin.CASELIST_ARCHIVE,
                    caselist="hsld26",
                    snapshot=SNAPSHOT,
                    first_element_index=3,
                    last_element_index=5,
                    parser_version=parser.parser_version,
                    profile_version="fake-profile-1",
                ),
            ),
        ),
    )
    parser.add(SOURCE_SHA256, document)

    assert parser.parse(b"PK\x03\x04", make_source(), source_path=SOURCE_PATH) == document
    assert parser.calls == [(SOURCE_SHA256, SOURCE_PATH)]
