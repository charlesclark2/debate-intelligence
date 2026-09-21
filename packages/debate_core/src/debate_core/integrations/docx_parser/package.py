"""Opening a `.docx` that arrived from a stranger.

Caselist files are not files we wrote. They are uploaded by hundreds of teams, converted by
Google Docs and by the opencaselist wiki-to-docx script, and downloaded in bulk from a public
archive. A reader that assumes a well-formed package written by Word will, somewhere in twelve
thousand files, meet a zip that expands to fill a disk, an XML document with a billion-laughs
entity in it, a `.docm` with a VBA project, a PDF with a `.docx` extension and a file that is
simply truncated. None of those may take a parse run down, and none may be half-read.

So this module does two jobs and hands the rest of the parser a package it can trust:

**It bounds what it will open.** Entry count, total uncompressed size, the size of each XML part
and each entry's compression ratio are all checked *before* anything is decompressed to memory,
from the zip's own directory — and then the actual bytes read are counted too, because a zip
directory can lie. See :class:`PackageLimits` for the numbers and where they come from.

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

`word/document.xml` is scanned for a DTD or an entity declaration and refused if it has one,
before a parser sees it. The parser itself is then built with `resolve_entities=False`,
`no_network=True`, `load_dtd=False`, `dtd_validation=False` and `huge_tree=False`, so even a
construct the scan missed cannot expand, fetch a URL or exhaust memory. `remove_blank_text` stays
off: a `<w:t>` holding nothing but spaces is part of a card's text, and evidence is copied
exactly.
"""

from __future__ import annotations

import re
import zipfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from io import BytesIO
from typing import Final, TypeAlias

from lxml import etree

from debate_core.domain.debate_files import ParseFailureReason
from debate_core.evidence.style_profile_loader import resolve_based_on_chain

#: One element of a parsed XML tree. lxml publishes no non-underscored name for it — `_Element`
#: *is* its public type, and every lxml-typed codebase aliases it once like this rather than
#: spelling the private name at every use.
XmlElement: TypeAlias = etree._Element  # pyright: ignore[reportPrivateUsage]

__all__ = [
    "DEFAULT_PACKAGE_LIMITS",
    "W_NAMESPACE",
    "DocxPackage",
    "DocxPackageError",
    "PackageLimits",
    "StyleDefinition",
    "XmlElement",
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

#: A DTD or entity declaration anywhere in a part. Refused before a parser is built, because the
#: cheapest defence against entity expansion is never to hand the document to a parser at all.
_FORBIDDEN_XML_CONSTRUCT = re.compile(rb"<!DOCTYPE|<!ENTITY|SYSTEM\s+[\"']|PUBLIC\s+[\"']", re.IGNORECASE)


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

    def __init__(self, reason: ParseFailureReason, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


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


def _refuse_non_zip_formats(content: bytes) -> None:
    """Name the common not-a-`.docx` formats before trying to open the bytes as a zip."""
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
    """Check the zip's own directory against the limits, before decompressing anything.

    Returns `(entry count, declared uncompressed total)`. The declared total is checked again
    against what is actually read, because a zip directory is written by whoever built the file.
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
        if info.compress_size >= limits.ratio_check_minimum_compressed_bytes:
            ratio = info.file_size / info.compress_size
            if ratio > limits.maximum_compression_ratio:
                raise DocxPackageError(
                    ParseFailureReason.COMPRESSION_RATIO_EXCEEDED,
                    f"one entry expands {ratio:.0f}-fold, above the limit of "
                    f"{limits.maximum_compression_ratio:.0f}",
                )
    return len(infos), total


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

    The read is bounded by one byte more than the limit, so a part that lies about its size in the
    directory is caught here rather than after it has been decompressed in full.
    """
    if name in NEVER_READ_PARTS:
        raise AssertionError(f"{name} is on the never-read list; this is a programming error")
    try:
        with archive.open(name) as part:
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


def _parse_xml(data: bytes, name: str) -> XmlElement:
    """Parse one part with every expansion, validation and network route switched off."""
    match = _FORBIDDEN_XML_CONSTRUCT.search(data)
    if match is not None:
        raise DocxPackageError(
            ParseFailureReason.FORBIDDEN_XML_CONSTRUCT,
            f"{name} declares {match.group(0).decode('ascii', 'replace')}, which is never resolved",
        )
    parser = etree.XMLParser(
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
    try:
        root = etree.fromstring(data, parser=parser)
    except etree.XMLSyntaxError as error:
        raise DocxPackageError(ParseFailureReason.MALFORMED_XML, f"{name} is not well-formed XML") from error
    if root is None:
        raise DocxPackageError(ParseFailureReason.MALFORMED_XML, f"{name} holds no root element")
    return root


def _main_document_part(archive: zipfile.ZipFile, limits: PackageLimits) -> str:
    """Find the main document part through the package relationships, falling back to convention.

    Nearly every file names it `word/document.xml`, but Word itself writes `/word/document2.xml`
    after certain repairs, and the wiki converter has been seen to write `word/document.xml` with
    a leading slash in the relationship. Following the relationship is what makes those readable.
    """
    names = set(archive.namelist())
    if "_rels/.rels" in names:
        root = _parse_xml(_read_part(archive, "_rels/.rels", limits), "_rels/.rels")
        for relationship in root.iterfind(qualified_name("Relationship", RELATIONSHIPS_NAMESPACE)):
            if relationship.get("Type") != OFFICE_DOCUMENT_RELATIONSHIP:
                continue
            target = (relationship.get("Target") or "").lstrip("/")
            if target in names:
                return target
    if "word/document.xml" in names:
        return "word/document.xml"
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
    refused before a document part is looked for, and the XML is scanned for expansion constructs
    before a parser is built. Nothing about the document's contents is examined until all of that
    has passed.
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

        document_part = _main_document_part(archive, limits)
        document_bytes = _read_part(archive, document_part, limits)
        document_root = _parse_xml(document_bytes, document_part)
        body = document_root.find(qualified_name("body"))
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
            styles = _read_styles(_parse_xml(_read_part(archive, styles_part, limits), styles_part))
            parts_read.append(styles_part)

        return DocxPackage(
            body=body,
            styles=styles,
            parts_read=tuple(parts_read),
            entry_count=entry_count,
            uncompressed_bytes=declared_uncompressed,
            warnings=tuple(warnings),
        )


def iter_body_children(body: XmlElement) -> Iterator[XmlElement]:
    """Yield the body's direct children in document order.

    Kept here rather than in the caller so that "document order" has one definition: the order
    lxml walks the tree, which is the order the bytes are in, which is the order a reader sees the
    file in Word.
    """
    yield from body
