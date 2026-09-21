"""Opening a package that arrived from a stranger: what is refused, and what is never read.

These tests are the reason the loader exists. A caselist backfill reads twelve thousand files
uploaded by hundreds of teams and converted by two different scripts, so "this file is hostile"
and "this file is not a .docx" are ordinary events that must produce a named reason and no
partial output. Each refusal is checked by the reason it names, because the parse pipeline
(`v1-e31-t06`) counts them separately: a corpus with a hundred PDFs in it is normal and a corpus
with a hundred zip bombs in it is not.
"""

from __future__ import annotations

import zipfile
from io import BytesIO

import pytest

from debate_core.domain.debate_files import ParseFailureReason
from debate_core.integrations.docx_parser.package import (
    NEVER_READ_PARTS,
    DocxPackageError,
    PackageLimits,
    open_debate_docx,
)
from debate_core.testing.docx_builder import (
    MACRO_ENABLED_CONTENT_TYPES,
    build_document_xml,
    build_docx,
    build_styles_xml,
    paragraph_xml,
    run_xml,
)

CARD_BODY = paragraph_xml(run_xml("Demand rose faster than any other load category last year."))
TAG = paragraph_xml(run_xml("Data centre demand collapses the reserve margin"), style="Heading4")


def reason_of(content: bytes, **kwargs: object) -> ParseFailureReason:
    """Open `content`, expect a refusal, and return the reason it named."""
    with pytest.raises(DocxPackageError) as raised:
        open_debate_docx(content, **kwargs)  # type: ignore[arg-type]
    return raised.value.reason


# --------------------------------------------------------------------------------------------
# Formats V1 does not parse
# --------------------------------------------------------------------------------------------


class TestFormatsThatAreNotDocx:
    def test_a_pdf_is_named_as_unsupported_rather_than_malformed(self) -> None:
        assert reason_of(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n") is ParseFailureReason.UNSUPPORTED_FORMAT

    def test_a_legacy_doc_is_named_as_unsupported(self) -> None:
        legacy = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 512
        assert reason_of(legacy) is ParseFailureReason.UNSUPPORTED_FORMAT

    def test_an_encrypted_package_is_told_apart_from_a_legacy_doc(self) -> None:
        """Both are OLE compound files; only one has an `EncryptedPackage` stream in it."""
        encrypted = (
            b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
            + b"\x00" * 64
            + "EncryptedPackage".encode("utf-16-le")
            + b"\x00" * 64
        )
        assert reason_of(encrypted) is ParseFailureReason.ENCRYPTED

    def test_arbitrary_bytes_are_not_a_zip(self) -> None:
        assert reason_of(b"this is a text file, not a document") is ParseFailureReason.NOT_A_ZIP

    def test_a_truncated_zip_is_not_a_readable_container(self) -> None:
        truncated = build_docx(CARD_BODY)[:64]
        assert reason_of(truncated) is ParseFailureReason.NOT_A_ZIP

    def test_a_zip_that_is_not_an_opc_package_is_malformed(self) -> None:
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("notes.txt", "a zip of something else entirely")
        assert reason_of(buffer.getvalue()) is ParseFailureReason.MALFORMED_PACKAGE


class TestMacroEnabledPackages:
    def test_a_vba_project_makes_a_package_macro_enabled_whatever_its_extension(self) -> None:
        content = build_docx(CARD_BODY, extra_parts={"word/vbaProject.bin": b"\x00\x01\x02"})
        assert reason_of(content) is ParseFailureReason.MACRO_ENABLED

    def test_a_macro_enabled_content_type_is_refused_even_with_no_vba_part(self) -> None:
        content = build_docx(CARD_BODY, content_types=MACRO_ENABLED_CONTENT_TYPES)
        assert reason_of(content) is ParseFailureReason.MACRO_ENABLED


# --------------------------------------------------------------------------------------------
# Hostile packages
# --------------------------------------------------------------------------------------------


class TestPackageLimits:
    def test_an_entry_that_expands_a_thousandfold_is_refused(self) -> None:
        """The shape of a zip bomb: one member of highly compressible filler."""
        content = build_docx(CARD_BODY, extra_parts={"word/media/image1.bin": b"\x00" * (8 * 1024 * 1024)})
        assert reason_of(content) is ParseFailureReason.COMPRESSION_RATIO_EXCEEDED

    def test_a_ratio_is_not_judged_on_an_entry_too_small_to_mean_anything(self) -> None:
        """A tiny, highly compressible part is ordinary; `.rels` files compress well."""
        content = build_docx(CARD_BODY, extra_parts={"word/footer1.xml": " " * 2000})
        assert open_debate_docx(content).entry_count == 6

    def test_a_package_above_the_uncompressed_limit_is_refused(self) -> None:
        content = build_docx(CARD_BODY, extra_parts={"word/media/image1.bin": b"x" * 20_000})
        limits = PackageLimits(maximum_total_uncompressed_bytes=10_000)
        assert reason_of(content, limits=limits) is ParseFailureReason.TOO_LARGE

    def test_a_package_with_too_many_entries_is_refused(self) -> None:
        extra = {f"word/media/image{index}.png": b"\x89PNG" for index in range(20)}
        content = build_docx(CARD_BODY, extra_parts=extra)
        assert reason_of(content, limits=PackageLimits(maximum_entries=10)) is (
            ParseFailureReason.TOO_MANY_ENTRIES
        )

    def test_a_document_part_above_the_part_limit_is_refused(self) -> None:
        content = build_docx(CARD_BODY * 200)
        limits = PackageLimits(maximum_part_bytes=1000, maximum_compression_ratio=10_000)
        assert reason_of(content, limits=limits) is ParseFailureReason.TOO_LARGE


class TestHostileXml:
    def test_a_doctype_is_refused_before_a_parser_sees_the_document(self) -> None:
        """Billion laughs, and everything like it, never reaches an XML parser at all."""
        hostile = (
            '<?xml version="1.0"?>'
            '<!DOCTYPE w:document [<!ENTITY lol "lol">'
            '<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">]>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>&lol2;</w:t></w:r></w:p></w:body></w:document>"
        )
        content = build_docx("", document_xml=hostile)
        assert reason_of(content) is ParseFailureReason.FORBIDDEN_XML_CONSTRUCT

    def test_an_external_entity_reference_is_refused(self) -> None:
        hostile = (
            '<?xml version="1.0"?>'
            '<!DOCTYPE w:document [<!ENTITY secret SYSTEM "file:///etc/passwd">]>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>&secret;</w:t></w:r></w:p></w:body></w:document>"
        )
        content = build_docx("", document_xml=hostile)
        assert reason_of(content) is ParseFailureReason.FORBIDDEN_XML_CONSTRUCT

    def test_a_document_part_that_is_not_well_formed_is_refused(self) -> None:
        content = build_docx("", document_xml="<w:document><w:body><w:p></w:document>")
        assert reason_of(content) is ParseFailureReason.MALFORMED_XML


class TestMissingParts:
    def test_a_package_with_no_document_part_is_refused(self) -> None:
        content = build_docx(CARD_BODY, omit_parts=["word/document.xml"])
        assert reason_of(content) is ParseFailureReason.MISSING_DOCUMENT_PART

    def test_a_package_with_no_content_types_is_refused(self) -> None:
        content = build_docx(CARD_BODY, omit_parts=["[Content_Types].xml"])
        assert reason_of(content) is ParseFailureReason.MALFORMED_PACKAGE

    def test_a_document_part_with_no_body_is_refused(self) -> None:
        no_body = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>'
        content = build_docx("", document_xml=no_body)
        assert reason_of(content) is ParseFailureReason.MISSING_DOCUMENT_PART

    def test_a_package_with_no_styles_part_opens_with_a_warning(self) -> None:
        """A Google Docs export sometimes has none. Every unit then comes from a heuristic."""
        content = build_docx(CARD_BODY, omit_parts=["word/styles.xml"])
        package = open_debate_docx(content)
        assert package.styles == {}
        assert any("no styles part" in warning for warning in package.warnings)


# --------------------------------------------------------------------------------------------
# What a package that opens gives back
# --------------------------------------------------------------------------------------------


class TestOpenedPackage:
    def test_the_body_and_the_style_table_come_back(self) -> None:
        package = open_debate_docx(build_docx(TAG + CARD_BODY))
        assert len(package.body) == 2
        assert package.style_name("Heading4") == "heading 4"
        assert package.styles["Analytic"].based_on == "Heading4"

    def test_a_based_on_chain_is_read_from_the_documents_own_style_table(self) -> None:
        """`Analytic` inherits from `Heading4`, which inherits from `Normal`."""
        package = open_debate_docx(build_docx(TAG))
        assert package.based_on_chain("Analytic") == ("Heading4", "Normal")

    def test_a_style_the_document_no_longer_defines_gets_an_empty_chain(self) -> None:
        package = open_debate_docx(build_docx(TAG))
        assert package.based_on_chain("Heading411") == ()

    def test_the_main_document_part_is_followed_through_the_relationship(self) -> None:
        """Word writes `word/document2.xml` after some repairs; the relationship still points at it."""
        relationship = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/officeDocument" Target="/word/document2.xml"/></Relationships>'
        )
        content = build_docx(
            CARD_BODY,
            omit_parts=["word/document.xml"],
            extra_parts={
                "_rels/.rels": relationship,
                "word/document2.xml": build_document_xml(TAG),
            },
        )
        package = open_debate_docx(content)
        assert "word/document2.xml" in package.parts_read

    def test_a_style_with_no_name_element_is_still_recorded(self) -> None:
        styles = build_styles_xml([("CardBody", "paragraph", "Card Body", None)]).replace(
            '<w:name w:val="Card Body"/>', ""
        )
        package = open_debate_docx(build_docx(CARD_BODY, styles_xml=styles))
        assert package.styles["CardBody"].style_name is None


class TestPartsThatAreNeverRead:
    def test_authorship_and_comment_parts_are_not_opened(self) -> None:
        """The list is asserted, so a change that starts reading authorship has to edit this test.

        `docProps/core.xml` carries `dc:creator` and `cp:lastModifiedBy`; `word/comments.xml` and
        `word/people.xml` carry comment authors. A debate file's author is a student
        (architecture proposal §14, data minimization).
        """
        content = build_docx(
            TAG + CARD_BODY,
            extra_parts={
                "docProps/core.xml": "<cp:coreProperties/>",
                "word/comments.xml": "<w:comments/>",
                "word/people.xml": "<w15:people/>",
                "word/settings.xml": "<w:settings/>",
            },
        )
        package = open_debate_docx(content)
        assert package.parts_read == (
            "_rels/.rels",
            "[Content_Types].xml",
            "word/document.xml",
            "word/styles.xml",
        )
        assert not set(package.parts_read) & NEVER_READ_PARTS

    def test_every_never_read_part_is_one_that_carries_a_name_or_a_fingerprint(self) -> None:
        assert "docProps/core.xml" in NEVER_READ_PARTS
        assert "word/comments.xml" in NEVER_READ_PARTS
        assert "word/people.xml" in NEVER_READ_PARTS


class TestRefusalDetail:
    def test_a_refusal_names_formats_and_limits_and_never_document_text(self) -> None:
        """`detail` is logged and published in the failure list, so it must carry nothing private."""
        content = build_docx(paragraph_xml(run_xml("Okonkwo 26, Journal of Grid Studies")))
        with pytest.raises(DocxPackageError) as raised:
            open_debate_docx(content, limits=PackageLimits(maximum_entries=2))
        assert "Okonkwo" not in raised.value.detail
        assert "entries" in raised.value.detail
