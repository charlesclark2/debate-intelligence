"""The body of a rendered .docx, as Word shows it, cut into cards by style (`v1-e06-t07`).

`verify` reads a document the platform exported twice: its embedded manifest
(:func:`~debate_core.evidence.docx_manifest_part.embedded_manifest_bytes`) and its body, which this
module reads into a :class:`~debate_core.evidence.docx_verify.DocumentBody` for
:mod:`debate_core.evidence.docx_verify` to compare with the manifest's cards.

## Cards, by the profile's styles

Each paragraph's style is resolved by the base style profile
(:meth:`~debate_core.domain.style_profile.StyleProfile.resolve_paragraph_style`), from its id, its
name in the document's `word/styles.xml` and the styles it is based on. A paragraph whose style is
the profile's tag style starts a card; one whose style is a pocket, hat or block ends the card before
it; the paragraphs between belong to the card. Matching by name as well as id is what keeps a
document that German Word saved readable: it renames heading 4's id `berschrift4` and keeps its
name. A paragraph is the cite when it carries the profile's cite paragraph style or a run in its cite
character style (the bold short cite the renderer writes).

## What Word shows, and nothing else

The comparison is only as honest as the text it is given, so a paragraph is read as a reader of the
document sees it, in Word's final view:

* text in runs anywhere in the paragraph: inside hyperlinks, content controls, simple fields, smart
  tags and tracked insertions, which python-docx's `Paragraph.text` would leave out;
* not tracked deletions or the text of a move's old place, not field codes, and not a run formatted
  hidden (`w:vanish`), which Word does not show;
* tabs as a tab, line and carriage breaks as a line feed;
* anything Word shows that is not text (a picture, an embedded object, a symbol, a footnote or
  endnote mark, an equation) as one object replacement character, U+FFFC, which no snapshot text
  holds, so it can never pass for evidence.

A table, or any block this reader does not know, inside a card is read as one paragraph of all the
text in it, a line feed between its paragraphs. Under a card's cite that is text a reader would take
for evidence, and the comparison reports it.

## What it refuses

Like :mod:`debate_core.evidence.docx_manifest_part`, it uses only the standard library, so
`debate_core.application` can call it without reaching a document library (the import contract
"Document libraries stay inside debate_core.integrations.docx_parser"), and a document is a file a
student hands back: a part that declares a document type (and with it any entity) is refused, and so
is one larger than :data:`MAXIMUM_PART_BYTES`. A file that is not a zip package, or has no main
document, is :class:`UnreadableDocument`. Nothing here writes: the reader is given bytes.
"""

from __future__ import annotations

import io
import posixpath
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final
from xml.etree import ElementTree

from debate_core.domain.style_profile import RunEmphasis, StructuralUnit, StyleProfile
from debate_core.evidence.docx_verify import BodyCard, BodyParagraph, DocumentBody

__all__ = ["MAXIMUM_PART_BYTES", "OBJECT_REPLACEMENT", "UnreadableDocument", "read_document_body"]

MAXIMUM_PART_BYTES: Final = 64 * 1024 * 1024
"""The largest part the reader opens, uncompressed: the manifest part's limit, far above a card file."""

OBJECT_REPLACEMENT: Final = "\ufffc"
"""What the reader reads in place of anything Word shows that is not text."""

_W: Final = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_PACKAGE_RELATIONSHIPS: Final = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_OFFICE_DOCUMENT: Final = "/officeDocument"
_STYLES: Final = "/styles"

#: Units whose paragraphs end the card before them, and the unit that starts one.
_HEADINGS: Final = frozenset({StructuralUnit.POCKET, StructuralUnit.HAT, StructuralUnit.BLOCK})

#: Never shown in Word's final view, or not text: skipped with everything inside them.
_NOT_SHOWN: Final = frozenset(
    _W + name
    for name in (
        "pPr",
        "rPr",
        "del",
        "moveFrom",
        "instrText",
        "delText",
        "delInstrText",
        "sdtPr",
        "sdtEndPr",
        "rubyPr",
        "commentReference",
        "annotationRef",
    )
)

#: Shown, and not text: one object replacement character each, nothing inside them read.
_OBJECTS: Final = frozenset(
    {
        *(
            _W + name
            for name in ("sym", "drawing", "pict", "object", "footnoteReference", "endnoteReference")
        ),
        "{http://schemas.openxmlformats.org/markup-compatibility/2006}AlternateContent",
        "{http://schemas.openxmlformats.org/officeDocument/2006/math}oMath",
        "{http://schemas.openxmlformats.org/officeDocument/2006/math}oMathPara",
    }
)

_CHARACTERS: Final = {
    _W + "tab": "\t",
    _W + "ptab": "\t",
    _W + "br": "\n",
    _W + "cr": "\n",
    _W + "noBreakHyphen": "\u2011",
    _W + "softHyphen": "\u00ad",
}

#: Body-level elements that hold no text a reader sees.
_NOT_BLOCKS: Final = frozenset(
    _W + name
    for name in (
        "sectPr",
        "bookmarkStart",
        "bookmarkEnd",
        "proofErr",
        "permStart",
        "permEnd",
        "commentRangeStart",
        "commentRangeEnd",
        "moveFromRangeStart",
        "moveFromRangeEnd",
        "moveToRangeStart",
        "moveToRangeEnd",
        "del",
        "moveFrom",
    )
)


class UnreadableDocument(ValueError):
    """The document is not a .docx this reader will open, so its body cannot be compared."""


@dataclass(frozen=True, slots=True)
class _Style:
    name: str | None
    based_on: str | None


@dataclass(frozen=True, slots=True)
class _Block:
    """One paragraph of the body, or one table or other block read as a paragraph of its text."""

    text: str
    unit: StructuralUnit | None
    is_cite: bool


def read_document_body(document: bytes, style_profile: StyleProfile) -> DocumentBody:
    """Every card in ``document``'s body, its paragraphs classified by ``style_profile``'s styles.

    Raises :class:`UnreadableDocument` for a file this reader does not open (see the module docstring).
    """
    try:
        package = zipfile.ZipFile(io.BytesIO(document))
    except zipfile.BadZipFile as error:
        raise UnreadableDocument("not a .docx: the file is not a zip package") from error
    with package:
        main = _main_document_name(package)
        body = _parse(package, main).find(f"{_W}body")
        if body is None:
            raise UnreadableDocument("the main document has no body")
        reader = _BlockReader(_styles(package, main), style_profile)
        return _cards(reader.blocks(body))


def _cards(blocks: Iterator[_Block]) -> DocumentBody:
    cards: list[BodyCard] = []
    tag: str | None = None
    paragraphs: list[BodyParagraph] = []

    def close() -> None:
        if tag is not None:
            cards.append(BodyCard(position=len(cards), tag=tag, paragraphs=tuple(paragraphs)))

    for block in blocks:
        if block.unit is StructuralUnit.TAG or block.unit in _HEADINGS:
            close()
            tag, paragraphs = (block.text, []) if block.unit is StructuralUnit.TAG else (None, [])
        elif tag is not None:
            paragraphs.append(BodyParagraph(block.text, is_cite=block.is_cite))
    close()
    return DocumentBody(cards=tuple(cards))


# --------------------------------------------------------------------------------------------
# The package
# --------------------------------------------------------------------------------------------


def _read(package: zipfile.ZipFile, name: str) -> bytes | None:
    try:
        member = package.getinfo(name)
    except KeyError:
        return None
    if member.file_size > MAXIMUM_PART_BYTES:
        raise UnreadableDocument(
            f"part {name} is {member.file_size} bytes, over the {MAXIMUM_PART_BYTES} this reader opens"
        )
    try:
        return package.read(member)
    except (zipfile.BadZipFile, OSError, EOFError) as error:
        raise UnreadableDocument(f"part {name} cannot be read from the package") from error


def _parse(package: zipfile.ZipFile, name: str) -> ElementTree.Element:
    content = _read(package, name)
    if content is None:
        raise UnreadableDocument(f"the package has no part {name}")
    if b"<!DOCTYPE" in content or b"<!ENTITY" in content:
        raise UnreadableDocument(
            f"part {name} declares a document type, which no .docx part needs; it is not opened"
        )
    try:
        return ElementTree.fromstring(content)
    except ElementTree.ParseError as error:
        raise UnreadableDocument(f"part {name} is not well-formed XML") from error


def _relationship_target(package: zipfile.ZipFile, source: str, kind: str) -> str | None:
    """The part ``source``'s relationship of type ``…kind`` points at, as a name in the package."""
    folder, file_name = posixpath.split(source)
    relationships = posixpath.join(folder, "_rels", file_name + ".rels")
    if _read(package, relationships) is None:
        return None
    for relationship in _parse(package, relationships).iter(f"{_PACKAGE_RELATIONSHIPS}Relationship"):
        if relationship.get("Type", "").endswith(kind) and relationship.get("TargetMode") != "External":
            target = relationship.get("Target", "")
            joined = target.lstrip("/") if target.startswith("/") else posixpath.join(folder, target)
            return posixpath.normpath(joined)
    return None


def _main_document_name(package: zipfile.ZipFile) -> str:
    name = _relationship_target(package, "", _OFFICE_DOCUMENT)
    if name is None or _read(package, name) is None:
        raise UnreadableDocument("not a .docx: the package has no main document")
    if _parse(package, name).tag != f"{_W}document":
        raise UnreadableDocument("the main document is not a WordprocessingML document")
    return name


def _styles(package: zipfile.ZipFile, main: str) -> dict[str, _Style]:
    """Every style in the document's styles part by id, with the default paragraph style under ``""``."""
    name = _relationship_target(package, main, _STYLES)
    if name is None or _read(package, name) is None:
        return {}
    styles: dict[str, _Style] = {}
    for style in _parse(package, name).iter(f"{_W}style"):
        style_id = style.get(f"{_W}styleId")
        if style_id is None:
            continue
        named = style.find(f"{_W}name")
        based_on = style.find(f"{_W}basedOn")
        styles[style_id] = _Style(
            name=named.get(f"{_W}val") if named is not None else None,
            based_on=based_on.get(f"{_W}val") if based_on is not None else None,
        )
        if style.get(f"{_W}type") == "paragraph" and style.get(f"{_W}default") in ("1", "true", "on"):
            styles[""] = _Style(name=None, based_on=style_id)
    return styles


# --------------------------------------------------------------------------------------------
# The body
# --------------------------------------------------------------------------------------------


class _BlockReader:
    def __init__(self, styles: dict[str, _Style], style_profile: StyleProfile) -> None:
        self._styles = styles
        self._profile = style_profile

    def blocks(self, container: ElementTree.Element) -> Iterator[_Block]:
        for child in container:
            if child.tag == f"{_W}p":
                yield self._paragraph(child)
            elif child.tag in (f"{_W}sdt", f"{_W}customXml"):
                content = child.find(f"{_W}sdtContent") if child.tag == f"{_W}sdt" else child
                if content is not None:
                    yield from self.blocks(content)
            elif child.tag not in _NOT_BLOCKS:
                yield _Block(text=self._text_of_block(child), unit=None, is_cite=False)

    def _paragraph(self, paragraph: ElementTree.Element) -> _Block:
        unit = self._unit(paragraph)
        is_cite = unit is StructuralUnit.CITE or any(
            self._emphasis(run) is RunEmphasis.CITE for run in paragraph.iter(f"{_W}r")
        )
        return _Block(text="".join(_shown_text(paragraph)), unit=unit, is_cite=is_cite)

    def _text_of_block(self, block: ElementTree.Element) -> str:
        """A table or unknown block: each paragraph in it read as shown, joined with a line feed."""
        paragraphs = list(block.iter(f"{_W}p"))
        if not paragraphs:
            return "".join(_shown_text(block))
        return "\n".join("".join(_shown_text(paragraph)) for paragraph in paragraphs)

    def _chain(self, style_id: str) -> tuple[str, ...]:
        """The ids and names of ``style_id``'s ancestors, nearest first."""
        chain: list[str] = []
        seen = {style_id}
        parent = self._styles.get(style_id, _Style(None, None)).based_on
        while parent is not None and parent not in seen:
            seen.add(parent)
            style = self._styles.get(parent, _Style(None, None))
            chain.extend(key for key in (parent, style.name) if key)
            parent = style.based_on
        return tuple(chain)

    def _unit(self, paragraph: ElementTree.Element) -> StructuralUnit | None:
        reference = paragraph.find(f"{_W}pPr/{_W}pStyle")
        style_id = reference.get(f"{_W}val") if reference is not None else None
        if style_id is None:
            style_id = self._styles.get("", _Style(None, None)).based_on
        if style_id is None:
            return None
        style = self._styles.get(style_id, _Style(None, None))
        match = self._profile.resolve_paragraph_style(style_id, style.name, self._chain(style_id))
        return match.unit if match is not None else None

    def _emphasis(self, run: ElementTree.Element) -> RunEmphasis | None:
        reference = run.find(f"{_W}rPr/{_W}rStyle")
        style_id = reference.get(f"{_W}val") if reference is not None else None
        if style_id is None:
            return None
        style = self._styles.get(style_id, _Style(None, None))
        match = self._profile.resolve_character_style(style_id, style.name, self._chain(style_id))
        return match.emphasis if match is not None else None


def _shown_text(element: ElementTree.Element) -> Iterator[str]:
    """The text Word shows for ``element``, in document order (see the module docstring)."""
    for child in element:
        tag = child.tag
        if tag in _NOT_SHOWN:
            continue
        if tag in _OBJECTS:
            yield OBJECT_REPLACEMENT
        elif tag == f"{_W}t":
            yield child.text or ""
        elif tag in _CHARACTERS:
            yield _CHARACTERS[tag]
        elif tag == f"{_W}r" and _is_hidden(child):
            continue
        else:
            yield from _shown_text(child)


def _is_hidden(run: ElementTree.Element) -> bool:
    vanish = run.find(f"{_W}rPr/{_W}vanish")
    return vanish is not None and vanish.get(f"{_W}val", "true") not in ("0", "false", "off")
