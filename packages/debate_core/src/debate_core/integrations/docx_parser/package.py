"""Opening a `.docx` that arrived from a stranger.

Caselist files are not files we wrote. They are uploaded by hundreds of teams, converted by
Google Docs and by the opencaselist wiki-to-docx script, and downloaded in bulk from a public
archive. A reader that assumes a well-formed package written by Word will, somewhere in twelve
thousand files, meet a zip that expands to fill a disk, an XML document with a billion-laughs
entity in it, a `.docm` with a VBA project, a PDF with a `.docx` extension and a file that is
simply truncated. None of those may take a parse run down, and none may be half-read.

So this module does two jobs and hands the rest of the parser a package it can trust:

**It bounds what it will open.** Entry count and total uncompressed size are checked over every
entry, from the zip's own directory, before anything is decompressed to memory. The compression
ratio is judged on each part the reader opens, from the same directory, before that part is
inflated; and the bytes actually read are bounded too, because a zip directory can lie. See
:class:`PackageLimits` for the numbers and where they come from.

**It refuses rather than guesses.** Every refusal is a
:class:`~debate_core.domain.debate_files.ParseFailureReason`, raised as
:class:`DocxPackageError` and turned into a
:class:`~debate_core.domain.debate_files.ParseFailure` at the parser's edge. A `.doc`, a PDF, an
encrypted package and a macro-enabled one are each named for what they are, because the pipeline
that reads a corpus needs to tell "we do not parse PDFs" apart from "this archive is hostile".

## What is deliberately never read

`docProps/core.xml` and `docProps/app.xml` carry `dc:creator` and `cp:lastModifiedBy` — the name
of whoever last saved the file. `word/comments.xml` and `word/people.xml` carry comment authors.
`word/settings.xml` carries `w:rsid` values that fingerprint an editing session. None of them is
opened. :attr:`DocxPackage.parts_read` records every part that *was*, and a test asserts the list,
so a later change that starts reading authorship has to change that test to do it
(architecture proposal §14).

## XML hardening

Every part this reader opens is refused if it declares a document type, in three steps:

1. **The bytes are scanned for `<!DOCTYPE` and `<!ENTITY`** before a parser is built. XML allows an
   entity declaration, and the `SYSTEM` and `PUBLIC` identifiers of an external reference, in one
   place only: a document type declaration. So a part with no `<!DOCTYPE` declares none of them.
2. **The parser is built to resolve nothing** (:func:`hardened_xml_parser`): `resolve_entities=False`,
   `no_network=True`, `load_dtd=False`, `dtd_validation=False` and `huge_tree=False`. Whatever
   reaches it cannot expand an entity, read a file, fetch a URL or exhaust memory.
3. **The parsed part is refused if it carries a document type at all.** The scan reads bytes, and in
   UTF-16 a zero byte sits between every two letters of `<!DOCTYPE`. What the parser found is the
   same in every encoding.

The scan once also looked for `SYSTEM "` and `PUBLIC '` anywhere in the part. Those are words, and
they are markup only inside a declaration step 1 already refuses. The first parse of the whole
corpus refused 23 ordinary files for card text such as *the system "works"* (`v1-e31-t09`), and not
one of them holds a declaration.

`remove_blank_text` stays off: a `<w:t>` holding nothing but spaces is part of a card's text, and
evidence is copied exactly, but for the one decided exception below.

## Characters XML 1.0 forbids

XML 1.0 allows tab, line feed and carriage return, and no other C0 control, anywhere in a document,
nor the noncharacters U+FFFE and U+FFFF. CardMirror's exporter has written U+0001, U+0002 and
U+FFFE raw into card text, and no conforming parser reads such a part: the first parse of the
corpus refused five files for it (`v1-e31-t09`). The PM decided with Charlie (2026-10-18, recorded
in `v1-e31-t15`'s spec):

    Each character XML 1.0 forbids that appears raw in a part the parser reads is replaced
    one-for-one by U+FFFD before the part is parsed. Nothing is deleted, no author's word changes,
    every other character keeps its position, and each source records how many it replaced. A
    forbidden character written as a character reference (`&#1;` and the like) is still refused.

So between step 1 and step 2 above, :func:`_replace_forbidden_characters` rewrites the part's raw
bytes, and :attr:`DocxPackage.forbidden_characters_replaced` carries the count to the parser, which
records it among the document's warnings. The rewrite cannot build markup: it only ever writes
U+FFFD, which is not markup, in place of a character that can never be legitimate where it stands.
A character reference is not a raw character, is left as it is, and the parser refuses it. The
rewrite reads the part in its own encoding, UTF-8 or UTF-16, the two Office Open XML allows; a
part in any other is handed to the parser unchanged.
"""

from __future__ import annotations

import re
import zipfile
import zlib
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from io import BytesIO
from typing import Final

from lxml import etree

from debate_core.domain.caselist import SourceFormat
from debate_core.domain.debate_files import ParseFailureReason
from debate_core.evidence.style_profile_loader import resolve_based_on_chain

#: One element of a parsed XML tree. lxml publishes no non-underscored name for it — `_Element`
#: *is* its public type, and every lxml-typed codebase aliases it once like this rather than
#: spelling the private name at every use.
type XmlElement = etree._Element  # pyright: ignore[reportPrivateUsage]

__all__ = [
    "DEFAULT_PACKAGE_LIMITS",
    "W_NAMESPACE",
    "DocxPackage",
    "DocxPackageError",
    "PackageLimits",
    "StyleDefinition",
    "XmlElement",
    "hardened_xml_parser",
    "open_debate_docx",
    "qualified_name",
]

#: The WordprocessingML main namespace. Every element this parser reads lives in it.
W_NAMESPACE: Final = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

#: Markup Compatibility, which wraps the two renderings of a text box.
MC_NAMESPACE: Final = "http://schemas.openxmlformats.org/markup-compatibility/2006"

#: The OPC relationship namespace, used to find the main document part.
RELATIONSHIPS_NAMESPACE: Final = "http://schemas.openxmlformats.org/package/2006/relationships"

#: The relationship type of the main document part.
OFFICE_DOCUMENT_RELATIONSHIP: Final = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
)

#: The relationship type of the styles part.
STYLES_RELATIONSHIP: Final = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles"

#: Parts this reader will never open, whatever a package's relationships say. Every one of them
#: carries either a person's name or an editing fingerprint; none of them carries card text.
NEVER_READ_PARTS: Final = frozenset(
    {
        "docProps/core.xml",
        "docProps/app.xml",
        "docProps/custom.xml",
        "word/comments.xml",
        "word/commentsExtended.xml",
        "word/commentsIds.xml",
        "word/commentsExtensible.xml",
        "word/people.xml",
        "word/settings.xml",
    }
)

#: A VBA project part. Its presence makes a package macro-enabled whatever its extension says.
VBA_PROJECT_PART: Final = "word/vbaProject.bin"

#: The content type of a macro-enabled main document part.
MACRO_ENABLED_CONTENT_TYPE: Final = "application/vnd.ms-word.document.macroEnabled.main+xml"

#: First bytes of a zip local file header. A `.docx` is a zip; anything else is not one.
ZIP_MAGIC: Final = b"PK\x03\x04"

#: First bytes of an OLE2 compound file: a legacy `.doc`, or an encrypted OOXML package.
OLE_MAGIC: Final = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

#: The OLE stream name that tells an encrypted package apart from a legacy `.doc`. OLE directory
#: entry names are UTF-16LE, so the marker is searched for in that encoding.
ENCRYPTED_PACKAGE_STREAM: Final = "EncryptedPackage".encode("utf-16-le")

#: First bytes of a PDF.
PDF_MAGIC: Final = b"%PDF"

#: First bytes of a gzip stream, which is what CardMirror's native `.cmir` file is.
GZIP_MAGIC: Final = b"\x1f\x8b"

#: How much of a gzip stream is read to tell a `.cmir` from any other: one inflated byte, from no
#: more than the first 4 KiB. A gzip stream is a compression ratio of its own, so it is never
#: inflated further than the one question needs.
_CMIR_HEAD_INPUT_BYTES: Final = 4096

#: Every character XML 1.0 forbids that can appear raw in a part: the C0 controls but tab, line
#: feed and carriage return, and the noncharacters U+FFFE and U+FFFF (XML 1.0 section 2.2, `Char`).
_FORBIDDEN_XML_CHARACTERS: Final = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")

#: The same characters as UTF-8 writes them. A C0 control is one byte that never occurs inside
#: another character's encoding, and `EF` only ever begins a character, so a match is always one
#: whole character.
_FORBIDDEN_XML_CHARACTERS_IN_UTF8: Final = re.compile(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]|\xef\xbf[\xbe\xbf]")

#: What a forbidden character is replaced by: U+FFFD, the character Unicode keeps for one that
#: cannot be represented.
REPLACEMENT_CHARACTER: Final = "�"

#: The encoding an XML declaration names, read from a part that begins in an ASCII-compatible one.
_DECLARED_ENCODING: Final = re.compile(rb"""(?:\xef\xbb\xbf)?<\?xml\s[^>]*?encoding\s*=\s*["']([^"']*)["']""")

#: A document type or entity declaration anywhere in a part. Refused before a parser is built,
#: because the cheapest defence against entity expansion is never to hand the document to a parser
#: at all. An external `SYSTEM` or `PUBLIC` identifier can only be written inside one of these two
#: declarations, so the words themselves are not looked for: in a `w:t` they are card text.
_FORBIDDEN_XML_CONSTRUCT = re.compile(rb"<!DOCTYPE|<!ENTITY", re.IGNORECASE)


def qualified_name(local_name: str, namespace: str = W_NAMESPACE) -> str:
    """Return `{namespace}local_name`, the form lxml compares element tags in."""
    return f"{{{namespace}}}{local_name}"


# --------------------------------------------------------------------------------------------
# Limits
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PackageLimits:
    """What this reader will open, and what it refuses as a hazard.

    The numbers are set from what real debate files measure, with room above the largest ones
    seen, rather than from what a zip can theoretically hold:

    * A 300-page camp file is about 5 MB compressed and its `word/document.xml` about 20 MB
      uncompressed. The largest file in the surveyed corpus is well under a tenth of
      `maximum_total_uncompressed_bytes`.
    * A Word package has a few dozen parts; a file with several hundred embedded images has a few
      hundred. `maximum_entries` is an order of magnitude above that.
    * WordprocessingML compresses roughly ten to twenty times. `maximum_compression_ratio` allows
      an order of magnitude more than that, which still leaves a zip bomb — a thousandfold and up
      — outside. The ratio is only checked on entries big enough for it to mean anything:
      a 40-byte `.rels` file that compresses to 20 bytes is not evidence of anything.
    * The ratio is judged on the parts the reader opens, and the entry count and the total on every
      entry. One file in the first corpus parse had a page thumbnail 278 times its stored size, in
      a part nothing opens, and no other entry in 9,738 files above 100 (`v1-e31-t09`). A part that
      is never inflated cannot exhaust anything, and the total still bounds the package.
    """

    maximum_entries: int = 1024
    maximum_total_uncompressed_bytes: int = 128 * 1024 * 1024
    maximum_part_bytes: int = 64 * 1024 * 1024
    maximum_compression_ratio: float = 200.0
    ratio_check_minimum_compressed_bytes: int = 4096


#: The limits every caller gets unless it says otherwise.
DEFAULT_PACKAGE_LIMITS: Final = PackageLimits()


class DocxPackageError(Exception):
    """A package this reader refuses, carrying the reason the pipeline will record.

    Raised rather than returned because it can happen at a dozen points inside the reader; the
    parser catches it once, at its edge, and returns a
    :class:`~debate_core.domain.debate_files.ParseFailure`. `detail` names formats, limits and
    part names only — never document text, a team code or a path from outside the package.
    """

    def __init__(
        self, reason: ParseFailureReason, detail: str, *, source_format: SourceFormat | None = None
    ) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail
        #: The format the bytes turned out to be, when the reader identified one; None otherwise.
        self.source_format = source_format


# --------------------------------------------------------------------------------------------
# What a package gives the rest of the parser
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StyleDefinition:
    """One `w:style` from `word/styles.xml`: enough to resolve it through the style profile."""

    style_id: str
    style_name: str | None
    style_type: str | None
    based_on: str | None


@dataclass(frozen=True, slots=True)
class DocxPackage:
    """An opened debate `.docx`: its body, its style table, and what was read to get them.

    Nothing here is interpreted yet. `body` is the raw `w:body` element and `styles` is the
    document's own style table; deciding that a paragraph is a tag is the classifier's job, and
    reading run text is :mod:`debate_core.integrations.docx_parser.runs`'s.
    """

    body: XmlElement
    styles: Mapping[str, StyleDefinition]
    parts_read: tuple[str, ...]
    entry_count: int
    uncompressed_bytes: int
    warnings: tuple[str, ...] = field(default=())
    forbidden_characters_replaced: int = 0
    """How many characters XML 1.0 forbids were replaced by U+FFFD, over every part parsed."""

    def style_name(self, style_id: str | None) -> str | None:
        """The `w:name` of a style as this document defines it, or None."""
        if style_id is None:
            return None
        definition = self.styles.get(style_id)
        return definition.style_name if definition is not None else None

    def based_on_chain(self, style_id: str | None) -> tuple[str, ...]:
        """A style's ancestors, nearest first, from this document's own `w:basedOn` links.

        A file that refers to a style it no longer defines gets an empty chain rather than an
        error: three seasons of copying between documents makes that ordinary.
        """
        if style_id is None:
            return ()
        return resolve_based_on_chain(style_id, {key: value.based_on for key, value in self.styles.items()})


# --------------------------------------------------------------------------------------------
# Opening
# --------------------------------------------------------------------------------------------


def _is_cardmirror_native(content: bytes) -> bool:
    """True for a gzip stream whose first inflated byte opens a JSON object: CardMirror's `.cmir`.

    `docs/architecture/cardmirror-evaluation.md` describes the format as a gzip-compressed JSON
    envelope, and the one the corpus holds is exactly that (`v1-e31-t09`). One inflated byte is
    read, from at most the first :data:`_CMIR_HEAD_INPUT_BYTES` of the stream.
    """
    if not content.startswith(GZIP_MAGIC):
        return False
    try:
        head = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(content[:_CMIR_HEAD_INPUT_BYTES], 1)
    except zlib.error:
        return False
    return head == b"{"


def _refuse_non_zip_formats(content: bytes) -> None:
    """Name the common not-a-`.docx` formats before trying to open the bytes as a zip."""
    if _is_cardmirror_native(content):
        raise DocxPackageError(
            ParseFailureReason.UNSUPPORTED_FORMAT,
            "a gzip stream holding a JSON document, CardMirror's native .cmir format; "
            "V1 stores these without parsing them",
            source_format=SourceFormat.CMIR,
        )
    if content.startswith(PDF_MAGIC):
        raise DocxPackageError(
            ParseFailureReason.UNSUPPORTED_FORMAT, "a PDF; V1 stores PDFs without parsing them"
        )
    if content.startswith(OLE_MAGIC):
        if ENCRYPTED_PACKAGE_STREAM in content[:65_536]:
            raise DocxPackageError(
                ParseFailureReason.ENCRYPTED,
                "an OLE-wrapped encrypted package; there is nothing to read without the password",
            )
        raise DocxPackageError(
            ParseFailureReason.UNSUPPORTED_FORMAT,
            "an OLE compound file, i.e. a legacy .doc; V1 stores these without parsing them",
        )
    if not content.startswith(ZIP_MAGIC):
        raise DocxPackageError(
            ParseFailureReason.NOT_A_ZIP, "the bytes do not begin with a zip local file header"
        )


def _check_directory(archive: zipfile.ZipFile, limits: PackageLimits) -> tuple[int, int]:
    """Check the entry count and the total uncompressed size over every entry, before decompressing
    anything.

    Every entry counts toward the total, read or not: a zip bomb in a part nobody opens still has to
    be written to a disk by whoever unpacks the file. The compression ratio is judged on the parts
    the reader opens, as each is opened (:func:`_judge_compression_ratio`).

    Returns `(entry count, declared uncompressed total)`.
    """
    infos = archive.infolist()
    if len(infos) > limits.maximum_entries:
        raise DocxPackageError(
            ParseFailureReason.TOO_MANY_ENTRIES,
            f"{len(infos)} entries, above the limit of {limits.maximum_entries}",
        )
    total = 0
    for info in infos:
        total += info.file_size
        if total > limits.maximum_total_uncompressed_bytes:
            raise DocxPackageError(
                ParseFailureReason.TOO_LARGE,
                f"the package declares more than {limits.maximum_total_uncompressed_bytes} "
                f"uncompressed bytes",
            )
    return len(infos), total


def _judge_compression_ratio(info: zipfile.ZipInfo, limits: PackageLimits) -> None:
    """Refuse a part the reader is about to open whose directory entry expands past the limit.

    Judged from the directory, before a byte of the part is inflated, and only on the parts the
    reader opens: which those are is decided from their names and the package relationships, and
    every part is opened through :func:`_read_part`, which calls this first. A page thumbnail Word
    saves can expand hundreds of times over, and it is never opened (`v1-e31-t15`).
    """
    if info.compress_size < limits.ratio_check_minimum_compressed_bytes:
        return
    ratio = info.file_size / info.compress_size
    if ratio > limits.maximum_compression_ratio:
        raise DocxPackageError(
            ParseFailureReason.COMPRESSION_RATIO_EXCEEDED,
            f"{info.filename} expands {ratio:.0f}-fold, above the limit of "
            f"{limits.maximum_compression_ratio:.0f}",
        )


def _refuse_macro_enabled(archive: zipfile.ZipFile, content_types: bytes) -> None:
    """Refuse a package carrying a VBA project, whatever its extension claims."""
    if VBA_PROJECT_PART in archive.namelist():
        raise DocxPackageError(ParseFailureReason.MACRO_ENABLED, f"the package contains {VBA_PROJECT_PART}")
    if MACRO_ENABLED_CONTENT_TYPE.encode("utf-8") in content_types:
        raise DocxPackageError(
            ParseFailureReason.MACRO_ENABLED,
            "the main document part is declared as a macro-enabled content type",
        )


def _read_part(archive: zipfile.ZipFile, name: str, limits: PackageLimits) -> bytes:
    """Read one part, refusing to hold more of it in memory than the limits allow.

    Its compression ratio is judged first, from the directory. The read is bounded by one byte more
    than the limit, so a part that lies about its size in the directory is caught here rather than
    after it has been decompressed in full.
    """
    if name in NEVER_READ_PARTS:
        raise AssertionError(f"{name} is on the never-read list; this is a programming error")
    try:
        info = archive.getinfo(name)
    except KeyError as error:
        raise DocxPackageError(
            ParseFailureReason.MALFORMED_PACKAGE, f"{name} could not be read from the package"
        ) from error
    _judge_compression_ratio(info, limits)
    try:
        with archive.open(info) as part:
            data = part.read(limits.maximum_part_bytes + 1)
    except (KeyError, zipfile.BadZipFile, OSError, EOFError) as error:
        raise DocxPackageError(
            ParseFailureReason.MALFORMED_PACKAGE, f"{name} could not be read from the package"
        ) from error
    if len(data) > limits.maximum_part_bytes:
        raise DocxPackageError(
            ParseFailureReason.TOO_LARGE,
            f"{name} is larger than the {limits.maximum_part_bytes}-byte part limit",
        )
    return data


def hardened_xml_parser() -> etree.XMLParser:
    """An XML parser with every expansion, validation and network route switched off.

    `resolve_entities=False` leaves an entity reference as a reference: nothing is expanded and no
    external entity is read. `load_dtd=False` and `dtd_validation=False` leave an external subset
    unread. `no_network=True` forbids a fetch outright, and `huge_tree=False` keeps libxml2's own
    limits on depth and size. A new parser for every part, so one part's errors are never another's.
    """
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        huge_tree=False,
        recover=False,
        remove_blank_text=False,
        remove_comments=True,
        remove_pis=True,
    )


def _part_encoding(data: bytes) -> str | None:
    """The encoding a part's bytes are in, read as XML 1.0 Appendix F reads it.

    None for an encoding the forbidden-character rewrite does not read: UTF-32, anything else with a
    zero byte in its first four, and any encoding a declaration names other than UTF-8.
    """
    head = data[:4]
    if head.startswith(b"\xef\xbb\xbf"):
        return "utf-8"
    if head == b"\xff\xfe\x00\x00":
        return None
    if head.startswith(b"\xff\xfe") or head == b"<\x00?\x00":
        return "utf-16-le"
    if head.startswith(b"\xfe\xff") or head == b"\x00<\x00?":
        return "utf-16-be"
    if b"\x00" in head:
        return None
    declared = _DECLARED_ENCODING.match(data)
    if declared is None or declared.group(1).lower() in (b"utf-8", b"utf8"):
        return "utf-8"
    return None


def _replace_forbidden_characters(data: bytes) -> tuple[bytes, int]:
    """Replace each raw character XML 1.0 forbids by U+FFFD, and count them.

    The decision recorded in `v1-e31-t15`'s spec. One character in, one character out, so every
    other character keeps its position. A character reference is markup, not a raw character, and is
    left for the parser to refuse. A part this cannot read in its own encoding is returned unchanged.
    """
    encoding = _part_encoding(data)
    if encoding == "utf-8":
        return _FORBIDDEN_XML_CHARACTERS_IN_UTF8.subn(REPLACEMENT_CHARACTER.encode("utf-8"), data)
    if encoding is None:
        return data, 0
    try:
        text = data.decode(encoding)
    except UnicodeDecodeError:
        return data, 0
    replaced, count = _FORBIDDEN_XML_CHARACTERS.subn(REPLACEMENT_CHARACTER, text)
    return (replaced.encode(encoding), count) if count else (data, 0)


@dataclass(frozen=True, slots=True)
class _ParsedPart:
    root: XmlElement
    forbidden_characters_replaced: int


def _parse_xml(data: bytes, name: str) -> _ParsedPart:
    """Parse one part, refusing it if it declares a document type in any encoding.

    A raw character XML forbids is replaced by U+FFFD after the declaration scan and before the
    parser sees the part, and the count comes back with the root.
    """
    match = _FORBIDDEN_XML_CONSTRUCT.search(data)
    if match is not None:
        raise DocxPackageError(
            ParseFailureReason.FORBIDDEN_XML_CONSTRUCT,
            f"{name} declares {match.group(0).decode('ascii', 'replace')}, which is never resolved",
        )
    data, replaced = _replace_forbidden_characters(data)
    try:
        root = etree.fromstring(data, parser=hardened_xml_parser())
    except etree.XMLSyntaxError as error:
        raise DocxPackageError(ParseFailureReason.MALFORMED_XML, f"{name} is not well-formed XML") from error
    if root is None:
        raise DocxPackageError(ParseFailureReason.MALFORMED_XML, f"{name} holds no root element")
    # The scan above reads bytes, so a declaration in UTF-16 passes it. The parser has resolved
    # nothing, and what it found is the same whatever the encoding: any document type is refused.
    # libxml2 records a subset for every document type declaration, even one that declares
    # nothing; lxml's stubs type it as always present, which it is not.
    declared: object = root.getroottree().docinfo.internalDTD
    if declared is not None:
        raise DocxPackageError(
            ParseFailureReason.FORBIDDEN_XML_CONSTRUCT,
            f"{name} declares <!DOCTYPE in an encoding the byte scan does not read, which is never resolved",
        )
    return _ParsedPart(root, replaced)


def _main_document_part(archive: zipfile.ZipFile, limits: PackageLimits) -> tuple[str, int]:
    """Find the main document part through the package relationships, falling back to convention.

    Nearly every file names it `word/document.xml`, but Word itself writes `/word/document2.xml`
    after certain repairs, and the wiki converter has been seen to write `word/document.xml` with
    a leading slash in the relationship. Following the relationship is what makes those readable.

    Returns the part's name, and how many forbidden characters the relationships part held.
    """
    names = set(archive.namelist())
    replaced = 0
    if "_rels/.rels" in names:
        relationships = _parse_xml(_read_part(archive, "_rels/.rels", limits), "_rels/.rels")
        replaced = relationships.forbidden_characters_replaced
        for relationship in relationships.root.iterfind(
            qualified_name("Relationship", RELATIONSHIPS_NAMESPACE)
        ):
            if relationship.get("Type") != OFFICE_DOCUMENT_RELATIONSHIP:
                continue
            target = (relationship.get("Target") or "").lstrip("/")
            if target in names:
                return target, replaced
    if "word/document.xml" in names:
        return "word/document.xml", replaced
    raise DocxPackageError(
        ParseFailureReason.MISSING_DOCUMENT_PART,
        "the package declares no main document part and holds no word/document.xml",
    )


def _styles_part(archive: zipfile.ZipFile, document_part: str) -> str | None:
    """The styles part beside a document part, or None when the package defines no styles."""
    names = set(archive.namelist())
    directory = document_part.rsplit("/", 1)[0] if "/" in document_part else ""
    candidate = f"{directory}/styles.xml" if directory else "styles.xml"
    return candidate if candidate in names else None


def _read_styles(root: XmlElement) -> dict[str, StyleDefinition]:
    """Build the document's own style table: id, name, type and `basedOn` for every `w:style`."""
    styles: dict[str, StyleDefinition] = {}
    for element in root.iterfind(qualified_name("style")):
        style_id = element.get(qualified_name("styleId"))
        if not style_id:
            continue
        name_element = element.find(qualified_name("name"))
        based_on_element = element.find(qualified_name("basedOn"))
        styles[style_id] = StyleDefinition(
            style_id=style_id,
            style_name=None if name_element is None else name_element.get(qualified_name("val")),
            style_type=element.get(qualified_name("type")),
            based_on=None if based_on_element is None else based_on_element.get(qualified_name("val")),
        )
    return styles


def open_debate_docx(content: bytes, *, limits: PackageLimits = DEFAULT_PACKAGE_LIMITS) -> DocxPackage:
    """Open `content` as a debate `.docx`, or raise :class:`DocxPackageError` saying why not.

    The order is deliberate: the formats we do not parse are named from their magic bytes before
    a zip is opened, the zip directory is checked before anything is decompressed, macros are
    refused before a document part is looked for, each part's compression ratio is judged before
    it is inflated, and the XML is scanned for a document type declaration before a parser is
    built. Nothing about the document's contents is examined until
    all of that has passed.
    """
    _refuse_non_zip_formats(content)
    try:
        archive = zipfile.ZipFile(BytesIO(content))
    except zipfile.BadZipFile as error:
        raise DocxPackageError(
            ParseFailureReason.NOT_A_ZIP, "the bytes are not a readable zip container"
        ) from error

    with archive:
        entry_count, declared_uncompressed = _check_directory(archive, limits)
        if "[Content_Types].xml" not in archive.namelist():
            raise DocxPackageError(
                ParseFailureReason.MALFORMED_PACKAGE,
                "the zip has no [Content_Types].xml, so it is not an OPC package",
            )
        content_types = _read_part(archive, "[Content_Types].xml", limits)
        _refuse_macro_enabled(archive, content_types)

        document_part, replaced = _main_document_part(archive, limits)
        document = _parse_xml(_read_part(archive, document_part, limits), document_part)
        replaced += document.forbidden_characters_replaced
        body = document.root.find(qualified_name("body"))
        if body is None:
            raise DocxPackageError(
                ParseFailureReason.MISSING_DOCUMENT_PART,
                f"{document_part} holds no w:body element",
            )

        parts_read = ["[Content_Types].xml", document_part]
        if "_rels/.rels" in archive.namelist():
            parts_read.insert(0, "_rels/.rels")
        warnings: list[str] = []
        styles: dict[str, StyleDefinition] = {}
        styles_part = _styles_part(archive, document_part)
        if styles_part is None:
            warnings.append("the package defines no styles part; every unit comes from a heuristic")
        else:
            styles_xml = _parse_xml(_read_part(archive, styles_part, limits), styles_part)
            replaced += styles_xml.forbidden_characters_replaced
            styles = _read_styles(styles_xml.root)
            parts_read.append(styles_part)

        return DocxPackage(
            body=body,
            styles=styles,
            parts_read=tuple(parts_read),
            entry_count=entry_count,
            uncompressed_bytes=declared_uncompressed,
            warnings=tuple(warnings),
            forbidden_characters_replaced=replaced,
        )


def iter_body_children(body: XmlElement) -> Iterator[XmlElement]:
    """Yield the body's direct children in document order.

    Kept here rather than in the caller so that "document order" has one definition: the order
    lxml walks the tree, which is the order the bytes are in, which is the order a reader sees the
    file in Word.
    """
    yield from body
