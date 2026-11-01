"""The card manifest inside a rendered .docx, and reading it back (`v1-e06-t04`, for `v1-e06-t07`).

A rendered document carries the manifest it was rendered from, so `verify` can check the document
against the snapshots without anything beside it. The manifest is `v1-e06-t05`'s
:func:`~debate_core.evidence.manifest.serialize_manifest` bytes, embedded as they are: the text of one
element, `manifest`, in the namespace :data:`MANIFEST_NAMESPACE`, which is the whole of a custom XML
data part (`customXml/item1.xml`). One document has one manifest, and its `cards` list is the
document's cards in document order: one entry per card.

The part sits where Word keeps custom XML: related from the main document, with a properties part
that names the namespace as its schema and an item id derived from the manifest's bytes, so the
same manifest always gives the same part.

## Reading it back

:func:`read_embedded_manifest_bytes` finds the part by what it is, not by its name: Word keeps custom
XML parts through a save but may renumber them, and may add its own (a bibliography). Every custom
XML data part is read; exactly one must be a manifest element. The reader uses only the standard
library, so `debate_core.application` can call it without reaching a document library (the import
contract "Document libraries stay inside debate_core.integrations.docx_parser"). A document is a
file a student hands back, so it refuses a part that declares a document type (and with it any
entity), a part larger than :data:`MAXIMUM_MANIFEST_PART_BYTES`, and a manifest element holding
anything but text.

:func:`embedded_manifest_bytes` is the same reader for a document held as bytes, which is how `verify`
is handed one (`v1-e06-t07`). A document with no manifest part at all is
:class:`NoEmbeddedManifest`, so that `verify` can tell a hand-cut team file, which it does not read,
from a document whose manifest is damaged; a file that is not a zip package, or whose custom XML part
is not XML, is an :class:`EmbeddedManifestError` like every other refusal.
"""

from __future__ import annotations

import hashlib
import io
import uuid
import zipfile
from pathlib import Path
from typing import IO, Final
from xml.etree import ElementTree
from xml.sax.saxutils import escape

from debate_core.evidence.manifest import CardManifest

__all__ = [
    "MANIFEST_ELEMENT",
    "MANIFEST_NAMESPACE",
    "MANIFEST_PART_NAME",
    "MANIFEST_PROPERTIES_PART_NAME",
    "MAXIMUM_MANIFEST_PART_BYTES",
    "EmbeddedManifestError",
    "NoEmbeddedManifest",
    "embedded_manifest_bytes",
    "manifest_part_xml",
    "manifest_properties_xml",
    "read_embedded_manifest",
    "read_embedded_manifest_bytes",
]

MANIFEST_NAMESPACE: Final = "urn:debate-intelligence:manifest:v1"
MANIFEST_ELEMENT: Final = f"{{{MANIFEST_NAMESPACE}}}manifest"
MANIFEST_PART_NAME: Final = "/customXml/item1.xml"
MANIFEST_PROPERTIES_PART_NAME: Final = "/customXml/itemProps1.xml"
MAXIMUM_MANIFEST_PART_BYTES: Final = 64 * 1024 * 1024
"""The largest custom XML part the reader opens, uncompressed: far above any manifest of cards."""

_DECLARATION: Final = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
_DATASTORE_NAMESPACE: Final = "http://schemas.openxmlformats.org/officeDocument/2006/customXml"


class EmbeddedManifestError(ValueError):
    """A document's embedded manifest is missing, ambiguous, or not something this reader will open."""


class NoEmbeddedManifest(EmbeddedManifestError):
    """The document holds no manifest part at all: it was not exported by the platform, or lost its part."""


def manifest_part_xml(manifest_bytes: bytes) -> bytes:
    """The custom XML part holding `manifest_bytes` as the text of one manifest element.

    Raises :class:`EmbeddedManifestError` for a manifest holding a character XML 1.0 cannot carry
    (serialized JSON escapes control characters, but not U+FFFE or U+FFFF).
    """
    text = manifest_bytes.decode("utf-8")
    for offset, character in enumerate(text):
        code = ord(character)
        if not (character in "\t\n" or 0x20 <= code <= 0xD7FF or 0xE000 <= code <= 0xFFFD or code >= 0x10000):
            raise EmbeddedManifestError(
                f"the manifest holds U+{code:04X} at offset {offset}, which an XML part cannot carry"
            )
    return (_DECLARATION + f'<manifest xmlns="{MANIFEST_NAMESPACE}">{escape(text)}</manifest>').encode(
        "utf-8"
    )


def manifest_properties_xml(manifest_bytes: bytes) -> bytes:
    """The part's properties: an item id from the manifest's SHA-256, and the namespace as its schema."""
    item_id = uuid.UUID(bytes=hashlib.sha256(manifest_bytes).digest()[:16], version=4)
    return (
        _DECLARATION
        + f'<ds:datastoreItem ds:itemID="{{{str(item_id).upper()}}}" xmlns:ds="{_DATASTORE_NAMESPACE}">'
        + f'<ds:schemaRefs><ds:schemaRef ds:uri="{MANIFEST_NAMESPACE}"/></ds:schemaRefs></ds:datastoreItem>'
    ).encode("utf-8")


def _is_data_part(name: str) -> bool:
    folder, _, file_name = name.rpartition("/")
    return folder == "customXml" and file_name.endswith(".xml") and not file_name.startswith("itemProps")


def read_embedded_manifest_bytes(path: Path) -> bytes:
    """The manifest bytes embedded in the .docx at `path`, exactly as they were serialized."""
    return _manifest_bytes(path, path.name)


def embedded_manifest_bytes(document: bytes) -> bytes:
    """The manifest bytes embedded in the .docx `document`, exactly as they were serialized.

    Raises :class:`NoEmbeddedManifest` when it holds none, and :class:`EmbeddedManifestError` when it is
    not a zip package, holds two, or holds one this reader will not open.
    """
    return _manifest_bytes(io.BytesIO(document), "the document")


def _manifest_bytes(source: Path | IO[bytes], name: str) -> bytes:
    found: list[str] = []
    try:
        package = zipfile.ZipFile(source)
    except zipfile.BadZipFile as error:
        raise EmbeddedManifestError(f"{name} is not a .docx: it is not a zip package") from error
    with package:
        for member in package.infolist():
            if not _is_data_part(member.filename):
                continue
            if member.file_size > MAXIMUM_MANIFEST_PART_BYTES:
                raise EmbeddedManifestError(
                    f"{name}: custom XML part {member.filename} is {member.file_size} bytes, over the "
                    f"{MAXIMUM_MANIFEST_PART_BYTES} this reader opens"
                )
            content = package.read(member)
            if b"<!DOCTYPE" in content or b"<!ENTITY" in content:
                raise EmbeddedManifestError(
                    f"{name}: custom XML part {member.filename} declares a document type, which no "
                    "manifest does; it is not opened"
                )
            try:
                root = ElementTree.fromstring(content)
            except ElementTree.ParseError as error:
                raise EmbeddedManifestError(
                    f"{name}: custom XML part {member.filename} is not well-formed XML"
                ) from error
            if root.tag != MANIFEST_ELEMENT:
                continue
            if len(root) or root.attrib:
                raise EmbeddedManifestError(
                    f"{name}: the manifest element in {member.filename} holds only the manifest's text"
                )
            found.append(root.text or "")
    if len(found) != 1:
        count = "no embedded manifest" if not found else f"{len(found)} embedded manifests"
        error = NoEmbeddedManifest if not found else EmbeddedManifestError
        raise error(
            f"{name} holds {count}; a rendered document holds exactly one, in namespace {MANIFEST_NAMESPACE}"
        )
    return found[0].encode("utf-8")


def read_embedded_manifest(path: Path) -> CardManifest:
    """The :class:`~debate_core.evidence.manifest.CardManifest` embedded in the .docx at `path`.

    Validation errors from the manifest model propagate: a document from a newer build, or one whose
    manifest was edited, is `v1-e06-t07`'s to report.
    """
    return CardManifest.model_validate_json(read_embedded_manifest_bytes(path))
