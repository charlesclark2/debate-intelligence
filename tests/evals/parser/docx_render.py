"""The labeller's own reading of a `.docx`: each paragraph's text, and how Word would show it.

The click-through labeller (`scripts/prelabel_docx.py label`) shows a sampled paragraph rendered
with its formatting, and on a span row it writes the underline and highlight a person confirms.
Those marks are a label, so they must not be the parser's opinion of the file: a span the parser
missed would be missed again here and the evaluation would never see it. This module therefore
**shares no code with the parser's run reading** (`debate_core.integrations.docx_parser`), and
`test_docx_render.py` holds it to that by its imports. It reads the XML itself, with the standard
library's zip reader and its own lxml parser, and answers one question per character: does Word
show it underlined, and highlighted?

What decides that, in Word's order of precedence, first match wins:

1. the run's own properties (`w:rPr`);
2. its character style (`w:rStyle`), then each style that one is `w:basedOn`;
3. its paragraph's style (`w:pStyle`, or the document's default paragraph style), then its chain;
4. the document defaults (`w:docDefaults/w:rPrDefault`).

`w:u w:val="none"` and `w:highlight w:val="none"` switch off what a style switched on, and
`w:u w:val="words"` underlines the words and not the spaces between them. Highlight is
`w:highlight` in any colour; paragraph shading is not highlight. Bold, italic, size and heading
level are read the same way, for display only: they are never written as a label.

Which paragraphs there are, and their text, follows the documented paragraph walk the parser's
element indices count (body paragraphs, then the text boxes inside each, table cells, content
controls; tracked insertions kept and deletions dropped). It is written again here rather than
imported, and the labeller compares each paragraph's text with the document's before it trusts a
range: a paragraph this reads differently is shown without marks and its span cells are left for a
person.

The labeller only renders a file the parser has already opened, so the package has passed the
parser's size and safety checks by the time it reaches this module. The XML is still read with
entities and network access off.
"""

from __future__ import annotations

import posixpath
import zipfile
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from io import BytesIO
from typing import Final

from lxml import etree

__all__ = ["RenderedParagraph", "RenderedRun", "render_docx"]

_W: Final = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_MC: Final = "http://schemas.openxmlformats.org/markup-compatibility/2006"
_RELATIONSHIPS: Final = "http://schemas.openxmlformats.org/package/2006/relationships"
_OFFICE_DOCUMENT: Final = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
_STYLES: Final = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles"


def _w(name: str) -> str:
    return f"{{{_W}}}{name}"


_PARAGRAPH, _RUN, _TABLE, _ROW, _CELL = _w("p"), _w("r"), _w("tbl"), _w("tr"), _w("tc")
_SDT, _SDT_CONTENT, _TEXT_BOX = _w("sdt"), _w("sdtContent"), _w("txbxContent")
_ALTERNATE, _CHOICE, _FALLBACK = f"{{{_MC}}}AlternateContent", f"{{{_MC}}}Choice", f"{{{_MC}}}Fallback"
_VAL = _w("val")

#: What a run's children add to the text, beside `w:t`.
_CHARACTERS: Final = {
    _w("tab"): "\t",
    _w("br"): "\n",
    _w("cr"): "\n",
    _w("noBreakHyphen"): "-",
    _w("softHyphen"): "",
}
#: Wrappers walked through for their runs. Tracked insertions are text; deletions are not.
_WRAPPERS: Final = frozenset(
    {
        _w(name)
        for name in (
            "ins",
            "moveTo",
            "hyperlink",
            "smartTag",
            "sdt",
            "sdtContent",
            "customXml",
            "fldSimple",
            "bdo",
            "dir",
        )
    }
    | {_ALTERNATE, _CHOICE}
)
_OFF: Final = frozenset({"0", "false", "off"})


@dataclass(frozen=True)
class RenderedRun:
    """One run's text and how Word shows it."""

    text: str
    bold: bool = False
    italic: bool = False
    #: The `w:u` value in force (`single`, `words`, `double`, …), or None.
    underline: str | None = None
    #: The highlight colour in force, or None.
    highlight: str | None = None
    half_points: int | None = None


@dataclass(frozen=True)
class RenderedParagraph:
    text: str
    runs: tuple[RenderedRun, ...]
    #: 1 to 9 for a heading (by its style's name or an outline level), else None.
    heading_level: int | None = None

    @property
    def underline(self) -> tuple[tuple[int, int], ...]:
        """Half-open ranges of the text Word shows underlined."""
        return _ranges(
            self.runs,
            lambda run, character: (
                run.underline is not None and not (run.underline == "words" and character.isspace())
            ),
        )

    @property
    def highlight(self) -> tuple[tuple[int, int], ...]:
        """Half-open ranges of the text Word shows highlighted, in any colour."""
        return _ranges(self.runs, lambda run, _: run.highlight is not None)


def _ranges(
    runs: Sequence[RenderedRun], marked: Callable[[RenderedRun, str], bool]
) -> tuple[tuple[int, int], ...]:
    ranges: list[tuple[int, int]] = []
    position = 0
    for run in runs:
        for character in run.text:
            if marked(run, character):
                if ranges and ranges[-1][1] == position:
                    ranges[-1] = (ranges[-1][0], position + 1)
                else:
                    ranges.append((position, position + 1))
            position += 1
    return tuple(ranges)


# --------------------------------------------------------------------------------------------
# The package
# --------------------------------------------------------------------------------------------


def _xml(data: bytes) -> etree._Element:
    parser = etree.XMLParser(
        resolve_entities=False, no_network=True, load_dtd=False, remove_comments=True, remove_pis=True
    )
    return etree.fromstring(data, parser)


def _target(archive: zipfile.ZipFile, rels_name: str, base: str, kind: str) -> str | None:
    if rels_name not in archive.namelist():
        return None
    for relationship in _xml(archive.read(rels_name)).iter(f"{{{_RELATIONSHIPS}}}Relationship"):
        if relationship.get("Type") == kind:
            return posixpath.normpath(posixpath.join(base, relationship.get("Target", "").lstrip("/")))
    return None


@dataclass(frozen=True)
class _Style:
    based_on: str | None
    name: str
    run_properties: etree._Element | None
    outline_level: int | None


class _Styles:
    def __init__(self, root: etree._Element | None) -> None:
        self.styles: dict[str, _Style] = {}
        self.default_paragraph: str | None = None
        self.defaults: etree._Element | None = None
        if root is None:
            return
        for element in root.iter(_w("style")):
            style_id = element.get(_w("styleId"))
            if style_id is None:
                continue
            based_on, name = element.find(_w("basedOn")), element.find(_w("name"))
            paragraph_properties = element.find(_w("pPr"))
            self.styles[style_id] = _Style(
                based_on=None if based_on is None else based_on.get(_VAL),
                name="" if name is None else (name.get(_VAL) or ""),
                run_properties=element.find(_w("rPr")),
                outline_level=_outline_level(paragraph_properties),
            )
            if element.get(_w("type")) == "paragraph" and (element.get(_w("default")) or "") in (
                "1",
                "true",
                "on",
            ):
                self.default_paragraph = style_id
        self.defaults = root.find(f"{_w('docDefaults')}/{_w('rPrDefault')}/{_w('rPr')}")

    def chain(self, style_id: str | None) -> list[_Style]:
        found: list[_Style] = []
        seen: set[str] = set()
        while style_id is not None and style_id in self.styles and style_id not in seen:
            seen.add(style_id)
            found.append(self.styles[style_id])
            style_id = self.styles[style_id].based_on
        return found


def _outline_level(properties: etree._Element | None) -> int | None:
    if properties is None:
        return None
    element = properties.find(_w("outlineLvl"))
    value = None if element is None else (element.get(_VAL) or "").strip()
    return int(value) if value is not None and value.isdigit() and int(value) <= 8 else None


# --------------------------------------------------------------------------------------------
# Paragraphs
# --------------------------------------------------------------------------------------------


def _body_paragraphs(element: etree._Element) -> Iterator[etree._Element]:
    """Every paragraph of the body in document order, as the parser's element index counts them."""
    for child in element:
        if child.tag == _PARAGRAPH:
            yield child
            yield from _text_box_paragraphs(child)
        elif child.tag == _TABLE:
            yield from _table_paragraphs(child)
        elif child.tag == _SDT:
            for content in child.iterfind(_SDT_CONTENT):
                yield from _body_paragraphs(content)


def _table_paragraphs(table: etree._Element) -> Iterator[etree._Element]:
    for row in table.iterfind(_ROW):
        for cell in row.iterfind(_CELL):
            for child in cell:
                if child.tag == _PARAGRAPH:
                    yield child
                    yield from _text_box_paragraphs(child)
                elif child.tag == _TABLE:
                    yield from _table_paragraphs(child)


def _text_box_paragraphs(paragraph: etree._Element) -> Iterator[etree._Element]:
    """A text box Word writes twice, as a choice and a fallback, is read once."""
    containers = list(paragraph.iter(_ALTERNATE))
    for container in containers:
        source = container.find(_CHOICE)
        source = source if source is not None else container.find(_FALLBACK)
        if source is not None:
            for content in source.iter(_TEXT_BOX):
                yield from content.iter(_PARAGRAPH)
    if not containers:
        for content in paragraph.iter(_TEXT_BOX):
            yield from content.iter(_PARAGRAPH)


def _runs(element: etree._Element) -> Iterator[etree._Element]:
    for child in element:
        if child.tag == _RUN:
            yield child
        elif child.tag in _WRAPPERS:
            yield from _runs(child)


def _run_text(run: etree._Element) -> str:
    pieces: list[str] = []
    for child in run:
        if child.tag == _w("t"):
            pieces.append(child.text or "")
        elif child.tag in _CHARACTERS:
            pieces.append(_CHARACTERS[child.tag])
    return "".join(pieces)


def _property(sources: Sequence[etree._Element | None], name: str) -> etree._Element | None:
    """The first of `sources` (most specific first) that sets `name`."""
    for source in sources:
        if source is not None and (found := source.find(_w(name))) is not None:
            return found
    return None


def _on(element: etree._Element | None) -> bool:
    return element is not None and (element.get(_VAL) or "true").lower() not in _OFF


def _render_paragraph(paragraph: etree._Element, styles: _Styles) -> RenderedParagraph:
    properties = paragraph.find(_w("pPr"))
    style = None if properties is None else properties.find(_w("pStyle"))
    paragraph_style = styles.default_paragraph if style is None else style.get(_VAL)
    paragraph_chain = styles.chain(paragraph_style)
    runs: list[RenderedRun] = []
    for run in _runs(paragraph):
        direct = run.find(_w("rPr"))
        character = None if direct is None else direct.find(_w("rStyle"))
        sources = [
            direct,
            *(s.run_properties for s in styles.chain(None if character is None else character.get(_VAL))),
            *(s.run_properties for s in paragraph_chain),
            styles.defaults,
        ]
        underline = _property(sources, "u")
        underline_value = None if underline is None else (underline.get(_VAL) or "single")
        highlight = _property(sources, "highlight")
        highlight_value = None if highlight is None else highlight.get(_VAL)
        size = _property(sources, "sz")
        size_value = "" if size is None else (size.get(_VAL) or "")
        runs.append(
            RenderedRun(
                text=_run_text(run),
                bold=_on(_property(sources, "b")),
                italic=_on(_property(sources, "i")),
                underline=None if underline_value == "none" else underline_value,
                highlight=None if highlight_value in (None, "none") else highlight_value,
                half_points=int(size_value) if size_value.isdigit() else None,
            )
        )
    return RenderedParagraph(
        text="".join(run.text for run in runs),
        runs=tuple(runs),
        heading_level=_heading_level(properties, paragraph_chain),
    )


def _heading_level(properties: etree._Element | None, chain: Sequence[_Style]) -> int | None:
    level = _outline_level(properties)
    if level is not None:
        return level + 1
    for style in chain:
        words = style.name.lower().split()
        if len(words) == 2 and words[0] == "heading" and words[1].isdigit():
            return int(words[1])
        if style.outline_level is not None:
            return style.outline_level + 1
    return None


def render_docx(content: bytes) -> tuple[RenderedParagraph, ...]:
    """Every paragraph of the document, in the parser's element-index order, as Word shows it."""
    with zipfile.ZipFile(BytesIO(content)) as archive:
        document_part = _target(archive, "_rels/.rels", "", _OFFICE_DOCUMENT) or "word/document.xml"
        folder, name = posixpath.split(document_part)
        styles_part = _target(archive, posixpath.join(folder, "_rels", f"{name}.rels"), folder, _STYLES)
        names = set(archive.namelist())
        styles_root = _xml(archive.read(styles_part)) if styles_part in names else None
        document = _xml(archive.read(document_part))
    styles = _Styles(styles_root)
    body = document.find(_w("body"))
    if body is None:
        return ()
    return tuple(_render_paragraph(paragraph, styles) for paragraph in _body_paragraphs(body))
