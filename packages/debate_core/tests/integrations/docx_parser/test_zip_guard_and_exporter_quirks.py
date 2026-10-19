"""The zip guard judges only the parts it reads, and exporter quirks are decided (`v1-e31-t15`).

Three refusals the first full-corpus parse left for a decision (`v1-e31-t09`), each tested here as
it was decided:

* **The compression ratio is judged on the parts the reader opens.** One openev file was refused
  for a 278-fold page thumbnail, `docProps/thumbnail.emf`, which the parser never opens. A part the
  reader opens is still refused over the ratio, and the total uncompressed limit still counts every
  entry, read or not.
* **A character XML 1.0 forbids is replaced by U+FFFD** (Decision, PM with Charlie, 2026-10-18, in
  the task spec). Five CardMirror exports were refused for raw U+0001, U+0002 and U+FFFE inside a
  `w:t`. Each such character is replaced one for one before the part is parsed, nothing is deleted,
  and the source records how many. One written as a character reference is still refused, and so is
  a document type, whatever else the part holds.
* **A `.cmir` is unsupported, with a format of its own.** CardMirror's native file is a gzip stream
  holding a JSON document; one arrived named `.docx` and was counted as a failed parse.

Every package is synthetic and built in memory. Every expected text below is written by hand from
the markup its test builds, never read back from the parser (working agreement 6).
"""

from __future__ import annotations

import gzip
import struct
import zipfile
from datetime import date
from io import BytesIO
from typing import Final

import pytest

from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import ParsedDocument, ParseFailure, ParseFailureReason
from debate_core.domain.style_profile import RunEmphasis, StyleProfile
from debate_core.integrations.docx_parser.package import (
    DEFAULT_PACKAGE_LIMITS,
    DocxPackageError,
    PackageLimits,
    open_debate_docx,
)
from debate_core.integrations.docx_parser.parser import DebateDocxParser
from debate_core.testing.docx_builder import (
    CONTENT_TYPES,
    PACKAGE_RELS,
    W_NAMESPACE,
    build_document_xml,
    build_docx,
    build_styles_xml,
    paragraph_xml,
    run_xml,
)

SOURCE_SHA256: Final = "5f2b1c8e9a0d4e7f6b3a2c1d0e9f8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f"
SOURCE_PATH: Final = "hsld26/Lakeview/QaZx/Lakeview-QaZx-Aff-Harbor Classic-Round 2.docx"

#: Eight mebibytes of one byte value: compresses about a thousandfold, five times the limit.
FILLER_BYTES: Final = 8 * 1024 * 1024

# Invented for these tests. No real evidence, no real cite, no real team.
TAG_TEXT: Final = "Rationing ends before the reservoir refills"
SHORT_CITE: Final = "Adeyemi 26"
CITE_TAIL: Final = " (Water Policy Quarterly, 3 June 2026), example.invalid/reservoir"


def make_source(**overrides: object) -> SourceDocument:
    fields: dict[str, object] = {
        "sha256": SOURCE_SHA256,
        "byte_size": 52_000,
        "source_format": SourceFormat.DOCX,
        "origin": SourceOrigin.CASELIST_ARCHIVE,
        "caselist": "hsld26",
        "first_seen_snapshot": date(2026, 9, 8),
        "last_seen_snapshot": date(2026, 9, 15),
    }
    fields.update(overrides)
    return SourceDocument.model_validate(fields)


@pytest.fixture
def parser(profile: StyleProfile) -> DebateDocxParser:
    return DebateDocxParser(profile)


def reason_of(content: bytes, **kwargs: object) -> ParseFailureReason:
    """Open `content`, expect a refusal, and return the reason it named."""
    with pytest.raises(DocxPackageError) as raised:
        open_debate_docx(content, **kwargs)  # type: ignore[arg-type]
    return raised.value.reason


def card_body(*evidence_runs: str) -> str:
    """A tag, a cite and one evidence paragraph made of `evidence_runs`."""
    return (
        paragraph_xml(run_xml(TAG_TEXT), style="Heading4")
        + paragraph_xml(run_xml(SHORT_CITE, character_style="Style13ptBold") + run_xml(CITE_TAIL))
        + paragraph_xml("".join(evidence_runs))
    )


def underlined(text: str) -> str:
    return run_xml(text, character_style="StyleUnderline", underline="single", highlight="cyan")


ORDINARY_CARD: Final = card_body(underlined("Storage fell to forty per cent by the first week of August."))


def entry_info(content: bytes, name: str) -> zipfile.ZipInfo:
    with zipfile.ZipFile(BytesIO(content)) as archive:
        return archive.getinfo(name)


def over_the_ratio(content: bytes, name: str) -> bool:
    """True when `name` is an entry the ratio is judged on and it is above the limit.

    Asserted by every ratio test before its real assertion, so that none of them can pass
    because its filler happened to compress less than the test assumed.
    """
    info = entry_info(content, name)
    limits = DEFAULT_PACKAGE_LIMITS
    return (
        info.compress_size >= limits.ratio_check_minimum_compressed_bytes
        and info.file_size / info.compress_size > limits.maximum_compression_ratio
    )


# --------------------------------------------------------------------------------------------
# The compression ratio, judged on the parts the reader opens
# --------------------------------------------------------------------------------------------

#: The package relationships Word writes when it saves a thumbnail: the document, and the picture.
PACKAGE_RELS_WITH_THUMBNAIL: Final = PACKAGE_RELS.replace(
    "</Relationships>",
    '  <Relationship Id="rId2"\n'
    '    Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/thumbnail"\n'
    '    Target="docProps/thumbnail.emf"/>\n'
    "</Relationships>",
)

#: The relationships of a package whose main document part is `word/document2.xml`.
PACKAGE_RELS_TO_DOCUMENT2: Final = PACKAGE_RELS.replace("word/document.xml", "word/document2.xml")


def padded(xml: str) -> bytes:
    """A part's XML followed by filler whitespace: still well-formed, and far over the ratio."""
    return xml.encode("utf-8") + b" " * FILLER_BYTES


class TestTheRatioIsJudgedOnThePartsTheReaderOpens:
    def test_an_over_ratio_thumbnail_the_reader_never_opens_does_not_refuse_the_file(
        self, parser: DebateDocxParser
    ) -> None:
        """The openev file's shape: a page thumbnail Word saved, far over the ratio, never read."""
        content = build_docx(
            ORDINARY_CARD,
            extra_parts={
                "_rels/.rels": PACKAGE_RELS_WITH_THUMBNAIL,
                "docProps/thumbnail.emf": b"\x00" * FILLER_BYTES,
            },
        )
        assert over_the_ratio(content, "docProps/thumbnail.emf")

        package = open_debate_docx(content)
        assert "docProps/thumbnail.emf" not in package.parts_read

        result = parser.parse(content, make_source(), source_path=SOURCE_PATH)
        assert isinstance(result, ParsedDocument), result
        assert [card.tag for card in result.cards] == [TAG_TEXT]

    def test_an_over_ratio_media_part_the_reader_never_opens_does_not_refuse_the_file(self) -> None:
        content = build_docx(ORDINARY_CARD, extra_parts={"word/media/image1.bin": b"\x00" * FILLER_BYTES})
        assert over_the_ratio(content, "word/media/image1.bin")
        assert open_debate_docx(content).entry_count == 6

    def test_an_over_ratio_document_part_is_still_refused(self) -> None:
        content = build_docx("", document_xml=build_document_xml(ORDINARY_CARD) + " " * FILLER_BYTES)
        assert over_the_ratio(content, "word/document.xml")
        assert reason_of(content) is ParseFailureReason.COMPRESSION_RATIO_EXCEEDED

    @pytest.mark.parametrize(
        ("name", "xml"),
        [
            ("[Content_Types].xml", CONTENT_TYPES),
            ("_rels/.rels", PACKAGE_RELS),
            ("word/styles.xml", build_styles_xml()),
        ],
    )
    def test_every_other_part_the_reader_opens_is_still_judged(self, name: str, xml: str) -> None:
        content = build_docx(ORDINARY_CARD, extra_parts={name: padded(xml)})
        assert over_the_ratio(content, name)
        assert reason_of(content) is ParseFailureReason.COMPRESSION_RATIO_EXCEEDED

    def test_the_document_part_the_relationships_name_is_the_one_judged(self) -> None:
        """`word/document2.xml` is read when the relationships name it, so it is judged; the
        `word/document.xml` beside it is then a part the reader never opens."""
        named = build_docx(
            "",
            extra_parts={
                "_rels/.rels": PACKAGE_RELS_TO_DOCUMENT2,
                "word/document2.xml": padded(build_document_xml(ORDINARY_CARD)),
            },
        )
        assert over_the_ratio(named, "word/document2.xml")
        assert reason_of(named) is ParseFailureReason.COMPRESSION_RATIO_EXCEEDED

        unnamed = build_docx(
            "",
            document_xml=build_document_xml(ORDINARY_CARD) + " " * FILLER_BYTES,
            extra_parts={
                "_rels/.rels": PACKAGE_RELS_TO_DOCUMENT2,
                "word/document2.xml": build_document_xml(ORDINARY_CARD),
            },
        )
        assert over_the_ratio(unnamed, "word/document.xml")
        package = open_debate_docx(unnamed)
        assert "word/document.xml" not in package.parts_read
        assert "word/document2.xml" in package.parts_read

    def test_a_part_is_judged_before_any_of_it_is_inflated(self) -> None:
        """Its compressed bytes are broken, so inflating it would fail as a malformed package.

        It is refused for its ratio instead, which only the zip's directory can have told.
        """
        content = bytearray(
            build_docx("", document_xml=build_document_xml(ORDINARY_CARD) + " " * FILLER_BYTES)
        )
        info = entry_info(bytes(content), "word/document.xml")
        name_length, extra_length = struct.unpack(
            "<HH", content[info.header_offset + 26 : info.header_offset + 30]
        )
        middle = info.header_offset + 30 + name_length + extra_length + info.compress_size // 2
        content[middle : middle + 64] = b"\xff" * 64
        assert reason_of(bytes(content)) is ParseFailureReason.COMPRESSION_RATIO_EXCEEDED


class TestTheTotalLimitCountsEveryEntry:
    def test_the_default_limits_are_unchanged(self) -> None:
        assert (
            PackageLimits(
                maximum_entries=1024,
                maximum_total_uncompressed_bytes=128 * 1024 * 1024,
                maximum_part_bytes=64 * 1024 * 1024,
                maximum_compression_ratio=200.0,
                ratio_check_minimum_compressed_bytes=4096,
            )
            == DEFAULT_PACKAGE_LIMITS
        )

    def test_parts_the_reader_never_opens_still_count_toward_the_total(self) -> None:
        """Three 48 MiB parts no reader opens: 144 MiB against the limit of 128, at the defaults."""
        extra = {f"word/media/image{index}.bin": b"\x00" * (48 * 1024 * 1024) for index in range(3)}
        content = build_docx(ORDINARY_CARD, extra_parts=extra)
        assert reason_of(content) is ParseFailureReason.TOO_LARGE

    def test_an_unread_part_alone_above_the_total_is_refused(self) -> None:
        content = build_docx(ORDINARY_CARD, extra_parts={"docProps/thumbnail.emf": b"\x00" * 40_000})
        limits = PackageLimits(maximum_total_uncompressed_bytes=30_000)
        assert reason_of(content, limits=limits) is ParseFailureReason.TOO_LARGE


# --------------------------------------------------------------------------------------------
# Characters XML 1.0 forbids: replaced one for one (Decision, PM with Charlie, 2026-10-18)
# --------------------------------------------------------------------------------------------

#: Every character XML 1.0 forbids that a raw byte stream can hold: the C0 controls but tab, line
#: feed and carriage return, and the two noncharacters at the top of the Basic Multilingual Plane.
FORBIDDEN_CHARACTERS: Final = (
    *(chr(code) for code in range(0x20) if code not in (0x09, 0x0A, 0x0D)),
    "￾",
    "￿",
)

#: The parts a CardMirror export carries beside the document, synthetic. No real document id.
CARDMIRROR_PARTS: Final[dict[str, bytes | str]] = {
    "docProps/core.xml": (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"'
        ' xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:creator>Invented Author</dc:creator>'
        "</cp:coreProperties>"
    ),
    "docProps/custom.xml": (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"'
        ' xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        '<property fmtid="{D5CDD505-2E9C-101B-9397-08002B2CF9AE}" pid="2" name="CardMirrorDocId">'
        "<vt:lpwstr>00000000-0000-4000-8000-000000000000</vt:lpwstr></property></Properties>"
    ),
    "word/numbering.xml": f'<?xml version="1.0" encoding="UTF-8"?><w:numbering xmlns:w="{W_NAMESPACE}"/>',
}


def cardmirror_export(*evidence_runs: str) -> bytes:
    """A card in the shape of a CardMirror export, its body made of `evidence_runs`."""
    return build_docx(card_body(*evidence_runs), extra_parts=CARDMIRROR_PARTS)


def only_card(result: ParsedDocument | ParseFailure) -> tuple[ParsedDocument, str]:
    assert isinstance(result, ParsedDocument), result
    assert len(result.cards) == 1, result.cards
    return result, result.cards[0].evidence_text


def replacement_warning(count: int) -> str:
    return f"{count} character(s) XML 1.0 forbids were each replaced by U+FFFD; no other character moved"


class TestTheShapesTheFirstParseFound:
    """The two shapes the five refused CardMirror exports had, inside `w:t`."""

    #: Four raw U+0001, as three of the five files had.
    FOUR_START_OF_HEADING: Final = (
        "The council\x01s own figures show\x01 storage at\x01 forty per cent by\x01 August."
    )
    FOUR_START_OF_HEADING_READ: Final = (
        "The council�s own figures show� storage at� forty per cent by� August."
    )

    #: One raw U+0002 and twenty-six raw U+FFFE, as the other two had.
    START_OF_TEXT_AND_NONCHARACTERS: Final = (
        "Reservoir levels\x02 fell￾￾￾￾￾￾￾￾￾￾￾￾￾￾￾￾￾￾￾￾￾￾￾￾￾￾ in a single week."
    )
    START_OF_TEXT_AND_NONCHARACTERS_READ: Final = (
        "Reservoir levels� fell�������������������������� in a single week."
    )

    def test_four_start_of_heading_characters_are_each_replaced(self, parser: DebateDocxParser) -> None:
        content = cardmirror_export(underlined(self.FOUR_START_OF_HEADING))
        document, text = only_card(parser.parse(content, make_source(), source_path=SOURCE_PATH))

        assert text == self.FOUR_START_OF_HEADING_READ
        assert len(text) == len(self.FOUR_START_OF_HEADING) == 70
        assert replacement_warning(4) in document.warnings
        assert open_debate_docx(content).forbidden_characters_replaced == 4

    def test_a_start_of_text_and_twenty_six_noncharacters_are_each_replaced(
        self, parser: DebateDocxParser
    ) -> None:
        content = cardmirror_export(underlined(self.START_OF_TEXT_AND_NONCHARACTERS))
        document, text = only_card(parser.parse(content, make_source(), source_path=SOURCE_PATH))

        assert text == self.START_OF_TEXT_AND_NONCHARACTERS_READ
        assert len(text) == len(self.START_OF_TEXT_AND_NONCHARACTERS) == 66
        assert replacement_warning(27) in document.warnings
        assert open_debate_docx(content).forbidden_characters_replaced == 27

    def test_the_formatting_keeps_its_offsets(self, parser: DebateDocxParser) -> None:
        """Plain `Officials said` + U+0001 + ` the plan ` (0-25), then underlined `cannot` + U+0001 +
        ` hold` (25-37), then plain ` past August.`: the underline is where it was."""
        content = cardmirror_export(
            run_xml("Officials said\x01 the plan "),
            underlined("cannot\x01 hold"),
            run_xml(" past August."),
        )
        document, text = only_card(parser.parse(content, make_source(), source_path=SOURCE_PATH))

        assert text == "Officials said� the plan cannot� hold past August."
        underlines = [
            (span.start_offset, span.end_offset)
            for span in document.cards[0].formatting_spans
            if span.emphasis is RunEmphasis.UNDERLINE
        ]
        assert underlines == [(25, 37)]
        assert text[25:37] == "cannot� hold"

    def test_a_file_with_none_says_nothing_about_replacing(self, parser: DebateDocxParser) -> None:
        content = cardmirror_export(underlined("Storage fell to forty per cent by August."))
        document, _ = only_card(parser.parse(content, make_source(), source_path=SOURCE_PATH))
        assert not any("U+FFFD" in warning for warning in document.warnings)
        assert open_debate_docx(content).forbidden_characters_replaced == 0


class TestEveryForbiddenCharacter:
    @pytest.mark.parametrize("character", FORBIDDEN_CHARACTERS, ids=lambda c: f"U+{ord(c):04X}")
    def test_each_is_replaced_by_one_replacement_character(
        self, parser: DebateDocxParser, character: str
    ) -> None:
        content = cardmirror_export(underlined(f"before{character}after"))
        document, text = only_card(parser.parse(content, make_source(), source_path=SOURCE_PATH))
        assert text == "before�after"
        assert replacement_warning(1) in document.warnings

    @pytest.mark.parametrize(
        "character",
        ["�", "\x85", "\x7f", "퟿", "", "\U0001f4a7"],
        ids=lambda c: f"U+{ord(c):04X}",
    )
    def test_a_character_xml_allows_is_left_as_it_is(self, parser: DebateDocxParser, character: str) -> None:
        content = cardmirror_export(underlined(f"before{character}after"))
        document, text = only_card(parser.parse(content, make_source(), source_path=SOURCE_PATH))
        assert text == f"before{character}after"
        assert not any("U+FFFD" in warning for warning in document.warnings)

    @pytest.mark.parametrize("character", ["\t", "\n", "\r"], ids=["tab", "line-feed", "carriage-return"])
    def test_tab_line_feed_and_carriage_return_are_not_counted(self, character: str) -> None:
        content = cardmirror_export(underlined(f"before{character}after"))
        assert open_debate_docx(content).forbidden_characters_replaced == 0

    def test_a_utf16_part_is_read_in_its_own_encoding(self, parser: DebateDocxParser) -> None:
        """In UTF-16 every other byte of ASCII text is zero, so the rule reads characters, not bytes."""
        xml = build_document_xml(card_body(underlined("before\x01middle￾after")))
        utf16 = xml.replace('encoding="UTF-8"', 'encoding="UTF-16"').encode("utf-16")
        content = build_docx("", extra_parts={"word/document.xml": utf16})
        document, text = only_card(parser.parse(content, make_source(), source_path=SOURCE_PATH))
        assert text == "before�middle�after"
        assert replacement_warning(2) in document.warnings

    def test_a_forbidden_character_in_the_styles_part_is_counted_with_the_documents(self) -> None:
        """The styles part is read too; a style name with one in it is no different."""
        styles = build_styles_xml(
            (
                ("Normal", "paragraph", "Normal", None),
                ("Heading4", "paragraph", "heading\x01 4", "Normal"),
                ("Style13ptBold", "character", "Style 13 pt Bold", None),
                ("StyleUnderline", "character", "Style Underline", None),
            )
        )
        content = build_docx(card_body(underlined("before\x01after")), styles_xml=styles)
        package = open_debate_docx(content)
        assert package.forbidden_characters_replaced == 2
        assert package.style_name("Heading4") == "heading� 4"


class TestWhatIsStillRefused:
    @pytest.mark.parametrize(
        "reference", ["&#1;", "&#x1;", "&#x0002;", "&#0;", "&#xFFFE;", "&#xffff;", "&#31;"]
    )
    def test_a_forbidden_character_written_as_a_character_reference(self, reference: str) -> None:
        xml = build_document_xml(card_body(underlined("REFERENCE")).replace("REFERENCE", f"a{reference}b"))
        content = build_docx("", document_xml=xml)
        assert reason_of(content) is ParseFailureReason.MALFORMED_XML

    def test_a_character_reference_beside_a_raw_forbidden_character(self) -> None:
        xml = build_document_xml(card_body(underlined("a\x01b")).replace("a\x01b", "a\x01b&#1;c"))
        content = build_docx("", document_xml=xml)
        assert reason_of(content) is ParseFailureReason.MALFORMED_XML

    def test_a_document_type_with_a_forbidden_character_beside_it(self) -> None:
        hostile = (
            '<?xml version="1.0"?>'
            '<!DOCTYPE w:document [<!ENTITY lol "lol">'
            '<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">]>'
            f'<w:document xmlns:w="{W_NAMESPACE}">'
            "<w:body><w:p><w:r><w:t>&lol2;\x01</w:t></w:r></w:p></w:body></w:document>"
        )
        assert reason_of(build_docx("", document_xml=hostile)) is ParseFailureReason.FORBIDDEN_XML_CONSTRUCT

    def test_an_external_entity_with_a_forbidden_character_beside_it(self) -> None:
        hostile = (
            '<?xml version="1.0"?>'
            '<!DOCTYPE w:document [<!ENTITY secret SYSTEM "file:///etc/passwd">]>'
            f'<w:document xmlns:w="{W_NAMESPACE}">'
            "<w:body><w:p><w:r><w:t>￾&secret;</w:t></w:r></w:p></w:body></w:document>"
        )
        assert reason_of(build_docx("", document_xml=hostile)) is ParseFailureReason.FORBIDDEN_XML_CONSTRUCT

    def test_a_utf16_document_type_with_a_forbidden_character_beside_it(self) -> None:
        """The byte scan cannot read UTF-16; the parsed part's document type is what refuses it."""
        hostile = (
            '<?xml version="1.0" encoding="UTF-16"?>'
            '<!DOCTYPE w:document [<!ENTITY lol "lol">]>'
            f'<w:document xmlns:w="{W_NAMESPACE}">'
            "<w:body><w:p><w:r><w:t>&lol;\x02</w:t></w:r></w:p></w:body></w:document>"
        )
        content = build_docx("", extra_parts={"word/document.xml": hostile.encode("utf-16")})
        assert reason_of(content) is ParseFailureReason.FORBIDDEN_XML_CONSTRUCT

    def test_a_part_in_an_encoding_with_no_replacement_character_is_judged_as_it_is(self) -> None:
        """U+FFFD cannot be written in ISO-8859-1, so such a part is left to the parser unchanged.
        Office Open XML parts are UTF-8 or UTF-16, and every one the corpus holds is UTF-8."""
        xml = build_document_xml(card_body(underlined("before\x01after")))
        latin = xml.replace('encoding="UTF-8"', 'encoding="ISO-8859-1"').encode("latin-1")
        content = build_docx("", extra_parts={"word/document.xml": latin})
        assert reason_of(content) is ParseFailureReason.MALFORMED_XML


# --------------------------------------------------------------------------------------------
# CardMirror's native file: unsupported, with a format of its own
# --------------------------------------------------------------------------------------------

#: A synthetic `.cmir`: a gzip stream around a JSON envelope. Its keys are invented.
CMIR_DOCUMENT: Final = b'{"format":"cardmirror-native","version":1,"doc":{"type":"doc","content":[]}}'


def cmir(document: bytes = CMIR_DOCUMENT) -> bytes:
    return gzip.compress(document, mtime=0)


class TestCardMirrorNativeFiles:
    def test_a_cmir_named_docx_is_unsupported_with_its_own_format(self, parser: DebateDocxParser) -> None:
        result = parser.parse(cmir(), make_source(), source_path=SOURCE_PATH)
        assert isinstance(result, ParseFailure), result
        assert result.reason is ParseFailureReason.UNSUPPORTED_FORMAT
        assert result.source_format is SourceFormat.CMIR
        assert ".cmir" in result.detail

    def test_only_the_head_of_the_stream_is_inflated(self, parser: DebateDocxParser) -> None:
        """A stream cut off after its first bytes: inflating it in full fails.

        Written in stored blocks, so the head holds the document's first bytes as they are.
        """
        whole = gzip.compress(CMIR_DOCUMENT[:-1] + b" " * 1_000_000 + b"}", compresslevel=0, mtime=0)
        head = whole[:64]
        with pytest.raises(EOFError):
            gzip.decompress(head)
        result = parser.parse(head, make_source(), source_path=SOURCE_PATH)
        assert isinstance(result, ParseFailure), result
        assert result.source_format is SourceFormat.CMIR

    @pytest.mark.parametrize(
        "content",
        [
            gzip.compress(b"a gzip of plain text, not a CardMirror document", mtime=0),
            gzip.compress(b"", mtime=0),
            b"\x1f\x8b",
            b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff not deflate data at all",
        ],
        ids=["plain-text", "empty", "magic-only", "not-deflate"],
    )
    def test_a_gzip_stream_that_is_not_a_cardmirror_document_is_still_not_a_zip(
        self, parser: DebateDocxParser, content: bytes
    ) -> None:
        result = parser.parse(content, make_source(), source_path=SOURCE_PATH)
        assert isinstance(result, ParseFailure), result
        assert result.reason is ParseFailureReason.NOT_A_ZIP
        assert result.source_format is None

    def test_a_refusal_for_any_other_reason_names_no_format(self, parser: DebateDocxParser) -> None:
        result = parser.parse(b"%PDF-1.7\n", make_source(), source_path=SOURCE_PATH)
        assert isinstance(result, ParseFailure)
        assert result.reason is ParseFailureReason.UNSUPPORTED_FORMAT
        assert result.source_format is None

    def test_a_cmir_source_is_never_parsable(self) -> None:
        assert not make_source(source_format=SourceFormat.CMIR).is_parsable
