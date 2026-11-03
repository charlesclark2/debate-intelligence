"""Copying one card's paragraphs out of its source document, as OOXML, without retyping a character.

The writer never holds a card's text as a string. It finds the card's paragraphs in the source's own
parsed XML, by the element indices the E31 parser gave it, and deep-copies those `w:p` elements: the
`w:t` text exactly as the source wrote it, and every run's formatting with it. What changes on the way
is what the E31 parser itself does not read as text, and each change mirrors one of its rules
(:mod:`debate_core.integrations.docx_parser.runs`), so that a re-parse of the copy reads what a
parse of the source read:

* **Tracked changes are resolved the parser's way.** A `w:ins` or `w:moveTo` is unwrapped and its runs
  kept; a `w:del` or `w:moveFrom` is dropped whole, `w:delText` with it. A tracked change to a
  paragraph's or a run's properties is dropped, which leaves the properties as they now read.
* **Comments, bookmarks, proofing marks and permission ranges are dropped.** None is text, and a
  comment carries its author's name (the task's forbidden list).
* **Editing fingerprints are dropped.** `w:rsid*` attributes and Word 2010's paragraph ids fingerprint
  an editing session.
* **Styles are re-mapped through the style profile.** A paragraph or character style the profile
  resolves (by id, name, `basedOn` chain or de-duplication suffix, exactly as the classifier
  resolves it) becomes the profile's own id for the same unit or emphasis, because the built file's
  style table is the profile's (:mod:`.base_template`), not the source's. A style the base defines
  (`Hyperlink`, `Normal`) is kept. A style neither knows is removed from the run or paragraph, its
  direct formatting stays, and it is listed as a warning: never silently dropped (task ac3).
* **A hyperlink keeps its target.** Its relationship is re-created in the built file's document part.
* **Numbering is dropped, with a warning.** A list number lives in a numbering part the built file
  does not have; the parser reads no number as text.

## What is refused

A card holding something that cannot be copied this way is refused, whole, as `UNSUPPORTED_CONTENT`
(task ac4): a picture, a text box, an embedded object, chart or shape, a footnote or endnote
reference, any other element pointing into a part the built file would not have, and a table. Each
is detected after tracked deletions are dropped, so a picture somebody deleted does not refuse a card.

## Characters XML forbids

The source is opened through the parser's own reader, so a raw character XML 1.0 forbids has already
been replaced, by the decision recorded in `v1-e31-t15`. To count the replacements card by card, a
source that had any is opened a second time with a character it does not hold in place of U+FFFD;
each such character in a copied card is counted and written as U+FFFD (PM, 2026-10-19).
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Final

from debate_core.application.ports.evidence_file_writer import UnsupportedContentKind
from debate_core.domain.style_profile import StructuralUnit, StyleProfile
from debate_core.integrations.docx_parser.package import (
    DEFAULT_PACKAGE_LIMITS,
    REPLACEMENT_CHARACTER,
    DocxPackage,
    PackageLimits,
    PartRelationship,
    XmlElement,
    open_debate_docx,
    qualified_name,
    read_part_relationships,
)
from debate_core.integrations.docx_parser.parser import BodyParagraph, body_paragraphs

__all__ = [
    "CopiedCard",
    "HyperlinkTargets",
    "OpenedSource",
    "copy_card",
    "open_source",
]

R_NAMESPACE: Final = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
W14_NAMESPACE: Final = "http://schemas.microsoft.com/office/word/2010/wordml"
HYPERLINK_RELATIONSHIP: Final = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
)


def _w(local_name: str) -> str:
    return qualified_name(local_name)


W_RUN: Final = _w("r")
W_PARAGRAPH_PROPERTIES: Final = _w("pPr")
W_RUN_PROPERTIES: Final = _w("rPr")
W_PARAGRAPH_STYLE: Final = _w("pStyle")
W_RUN_STYLE: Final = _w("rStyle")
W_HYPERLINK: Final = _w("hyperlink")
W_NUMBERING: Final = _w("numPr")
W_VALUE: Final = _w("val")

#: Unwrapped: a tracked insertion is text, as the parser reads it.
_UNWRAP: Final = frozenset({_w("ins"), _w("moveTo")})

#: Dropped whole wherever they stand, children and all.
_DROP: Final = frozenset(
    {
        _w(name)
        for name in (
            "del",
            "moveFrom",
            "delText",
            "delInstrText",
            "moveFromRangeStart",
            "moveFromRangeEnd",
            "moveToRangeStart",
            "moveToRangeEnd",
            "commentRangeStart",
            "commentRangeEnd",
            "commentReference",
            "bookmarkStart",
            "bookmarkEnd",
            "proofErr",
            "permStart",
            "permEnd",
            "rPrChange",
            "pPrChange",
            "sectPr",
            "numberingChange",
            "customXmlInsRangeStart",
            "customXmlInsRangeEnd",
            "customXmlDelRangeStart",
            "customXmlDelRangeEnd",
            "customXmlMoveFromRangeStart",
            "customXmlMoveFromRangeEnd",
            "customXmlMoveToRangeStart",
            "customXmlMoveToRangeEnd",
            "lastRenderedPageBreak",
        )
    }
)

#: Attributes that fingerprint an editing session.
_EDITING_ATTRIBUTES: Final = frozenset(
    {_w(name) for name in ("rsidR", "rsidRPr", "rsidRDefault", "rsidP", "rsidDel", "rsidSect", "rsidTr")}
    | {f"{{{W14_NAMESPACE}}}paraId", f"{{{W14_NAMESPACE}}}textId"}
)

#: A comment's anchor in the text: its run holds nothing else, and goes with it.
_COMMENT_REFERENCE: Final = _w("commentReference")

_TEXT_BOX: Final = _w("txbxContent")
_DRAWINGS: Final = frozenset({_w("drawing"), _w("pict")})
_IMAGE_MARKS: Final = frozenset(
    {
        "{http://schemas.openxmlformats.org/drawingml/2006/main}blip",
        "{http://schemas.openxmlformats.org/drawingml/2006/picture}pic",
        "{urn:schemas-microsoft-com:vml}imagedata",
    }
)
_OBJECTS: Final = frozenset(
    {_w("object"), _w("control"), _w("altChunk"), _w("subDoc"), _w("embedObject"), _w("embedRegularFont")}
)
_NOTES: Final = frozenset({_w("footnoteReference"), _w("endnoteReference")})


# ------------------------------------------------------------------------------------------------
# Opening a source
# ------------------------------------------------------------------------------------------------


#: Characters tried, in order, as the stand-in for U+FFFD when a source's replacements are counted:
#: the Private Use Area, which no debate file's prose is written in.
_STAND_IN_CANDIDATES: Final = tuple(chr(code) for code in range(0xE000, 0xF900))


@dataclass(frozen=True, slots=True)
class OpenedSource:
    """A source document opened for copying: its parsed body, numbered, and its relationships.

    `stand_in` is the character the source's forbidden characters were replaced by in this tree, or
    None when the source had none (and the tree holds no replacement at all).
    """

    package: DocxPackage
    paragraphs: tuple[BodyParagraph, ...]
    relationships: Mapping[str, PartRelationship]
    stand_in: str | None


def _string(value: str | bytes) -> str:
    """An attribute name or value as text. lxml gives `str` on Python 3; its stubs allow bytes too."""
    return value if isinstance(value, str) else value.decode("utf-8")


def _characters_in(body: XmlElement) -> set[str]:
    seen: set[str] = set()
    for element in body.iter():
        if element.text:
            seen.update(element.text)
        if element.tail:
            seen.update(element.tail)
        for value in element.attrib.values():
            seen.update(_string(value))
    return seen


def open_source(content: bytes, *, limits: PackageLimits = DEFAULT_PACKAGE_LIMITS) -> OpenedSource:
    """Open a source through the parser's own reader, guards and all.

    Raises :class:`~debate_core.integrations.docx_parser.package.DocxPackageError` exactly where the
    parser would refuse the bytes.
    """
    package = open_debate_docx(content, limits=limits)
    stand_in: str | None = None
    if package.forbidden_characters_replaced:
        present = _characters_in(package.body)
        stand_in = next(candidate for candidate in _STAND_IN_CANDIDATES if candidate not in present)
        package = open_debate_docx(content, limits=limits, forbidden_character_replacement=stand_in)
    return OpenedSource(
        package=package,
        paragraphs=body_paragraphs(package.body),
        relationships=read_part_relationships(content, package.document_part, limits=limits),
        stand_in=stand_in,
    )


# ------------------------------------------------------------------------------------------------
# Hyperlink targets in the built file
# ------------------------------------------------------------------------------------------------


@dataclass(slots=True)
class HyperlinkTargets:
    """The built file's hyperlink relationships, allocated in the order they are met.

    One relationship per distinct target, numbered after the base's own two, so the same file always
    numbers them the same way.
    """

    first_number: int = 3
    _by_target: dict[str, str] = field(default_factory=lambda: {})

    def relationship_for(self, target: str) -> str:
        if target not in self._by_target:
            self._by_target[target] = f"rId{self.first_number + len(self._by_target)}"
        return self._by_target[target]

    def relationships(self) -> tuple[tuple[str, str, str], ...]:
        """`(id, type, target)` for every allocated hyperlink, in allocation order."""
        return tuple(
            (relationship_id, HYPERLINK_RELATIONSHIP, target)
            for target, relationship_id in self._by_target.items()
        )


# ------------------------------------------------------------------------------------------------
# Copying
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CopiedCard:
    """A card's paragraphs, copied, split after its last cite paragraph.

    `tag` is the copied tag paragraph, or None when the card has none. `through_cite` runs from the
    paragraph after the tag to the card's last cite paragraph; `after_cite` is the rest. The
    provenance line went between the two until data-use policy version 1.11 (`v1-e33-t08`); the
    writer now writes one after the other, as the source has them.
    """

    tag: XmlElement | None
    through_cite: tuple[XmlElement, ...]
    after_cite: tuple[XmlElement, ...]
    warnings: tuple[str, ...]
    forbidden_characters_replaced: int


@dataclass(frozen=True, slots=True)
class UnsupportedCard:
    """A card that holds something the writer cannot copy, with every kind it holds."""

    kinds: tuple[UnsupportedContentKind, ...]
    element_indices: tuple[int, ...]


def _remove(element: XmlElement) -> None:
    parent = element.getparent()
    if parent is not None:
        parent.remove(element)


def _unwrap(element: XmlElement) -> None:
    """Put an element's children where it stood, keeping their order."""
    parent = element.getparent()
    if parent is None:
        return
    position = parent.index(element)
    for offset, child in enumerate(list(element)):
        parent.insert(position + offset, child)
    parent.remove(element)


def _resolve_tracked_changes_and_marks(paragraph: XmlElement) -> None:
    """Drop what the parser drops and unwrap what it keeps, in one pass over a copied paragraph.

    A tracked change to the paragraph mark (`w:ins` or `w:del` inside `w:pPr/w:rPr`) needs no rule of
    its own: the insertion is an empty element and unwraps to nothing, and the deletion is dropped.
    """
    for reference in list(paragraph.iter(_COMMENT_REFERENCE)):
        run = reference.getparent()
        if (
            run is not None
            and run.tag == W_RUN
            and all(child is reference or child.tag == W_RUN_PROPERTIES for child in run)
        ):
            _remove(run)
    for element in [element for element in paragraph.iter() if element.tag in _DROP]:
        _remove(element)
    while True:
        wrappers = [element for element in paragraph.iter() if element.tag in _UNWRAP]
        if not wrappers:
            break
        _unwrap(wrappers[0])
    for element in paragraph.iter():
        for name in [name for name in element.attrib if name in _EDITING_ATTRIBUTES]:
            del element.attrib[name]


def _drawing_kind(drawing: XmlElement) -> UnsupportedContentKind:
    """What a `w:drawing` or `w:pict` holds: a text box, a picture, or an object, chart or shape."""
    inside = {descendant.tag for descendant in drawing.iter()}
    if _TEXT_BOX in inside:
        return UnsupportedContentKind.TEXT_BOX
    if inside & _IMAGE_MARKS:
        return UnsupportedContentKind.IMAGE
    return UnsupportedContentKind.EMBEDDED_OBJECT


def _unsupported_kinds(element: XmlElement) -> set[UnsupportedContentKind]:
    """Everything in a (cleaned) paragraph that cannot be copied losslessly.

    A drawing, an object or a text box is judged whole and not descended into, so the relationship
    a picture points through is not counted again as an object of its own. Anywhere else, an
    attribute pointing through a relationship is content in a part the built file would not have,
    unless it is a hyperlink's, which the writer re-creates.
    """
    kinds: set[UnsupportedContentKind] = set()
    for child in element:
        tag = child.tag
        if tag == _TEXT_BOX:
            kinds.add(UnsupportedContentKind.TEXT_BOX)
            continue
        if tag in _DRAWINGS:
            kinds.add(_drawing_kind(child))
            continue
        if tag in _OBJECTS:
            kinds.add(UnsupportedContentKind.EMBEDDED_OBJECT)
            continue
        if tag in _NOTES:
            kinds.add(UnsupportedContentKind.FOOTNOTE)
        if tag != W_HYPERLINK and any(
            _string(name).startswith(f"{{{R_NAMESPACE}}}") for name in child.attrib
        ):
            kinds.add(UnsupportedContentKind.EMBEDDED_OBJECT)
        kinds |= _unsupported_kinds(child)
    return kinds


class _StyleMap:
    """Re-maps the source's style ids to the profile's, the way the classifier resolves them."""

    def __init__(self, package: DocxPackage, profile: StyleProfile, base_style_ids: frozenset[str]) -> None:
        self._package = package
        self._profile = profile
        self._base = base_style_ids
        self._paragraph_ids = {rule.unit: rule.style_id for rule in reversed(profile.paragraph_styles)}
        self._character_ids = {rule.emphasis: rule.style_id for rule in reversed(profile.character_styles)}

    def paragraph(self, style_id: str) -> str | None:
        match = self._profile.resolve_paragraph_style(
            style_id, self._package.style_name(style_id), self._package.based_on_chain(style_id)
        )
        if match is not None:
            return self._paragraph_ids[match.unit]
        return style_id if style_id in self._base else None

    def character(self, style_id: str) -> str | None:
        match = self._profile.resolve_character_style(
            style_id, self._package.style_name(style_id), self._package.based_on_chain(style_id)
        )
        if match is not None:
            return self._character_ids[match.emphasis]
        return style_id if style_id in self._base else None

    def describe(self, style_id: str) -> str:
        name = self._package.style_name(style_id)
        return f"{style_id!r} ({name!r})" if name and name != style_id else repr(style_id)

    @property
    def tag_style_id(self) -> str:
        return self._paragraph_ids[StructuralUnit.TAG]


def _remap_styles(paragraph: XmlElement, styles: _StyleMap, warnings: list[str]) -> None:
    for element in list(paragraph.iter(W_PARAGRAPH_STYLE, W_RUN_STYLE)):
        old = element.get(W_VALUE) or ""
        mapped = styles.paragraph(old) if element.tag == W_PARAGRAPH_STYLE else styles.character(old)
        if mapped is None:
            kind = "paragraph" if element.tag == W_PARAGRAPH_STYLE else "character"
            warnings.append(
                f"the source's {kind} style {styles.describe(old)} is not one the style profile maps; "
                "it was removed and the direct formatting kept"
            )
            _remove(element)
        elif mapped != old:
            element.set(W_VALUE, mapped)


def _set_paragraph_style(paragraph: XmlElement, style_id: str) -> None:
    """Give a paragraph `style_id`, as the first child of its properties as the schema orders them."""
    properties = paragraph.find(W_PARAGRAPH_PROPERTIES)
    if properties is None:
        properties = paragraph.makeelement(W_PARAGRAPH_PROPERTIES, {})
        paragraph.insert(0, properties)
    style = properties.find(W_PARAGRAPH_STYLE)
    if style is None:
        style = properties.makeelement(W_PARAGRAPH_STYLE, {})
        properties.insert(0, style)
    style.set(W_VALUE, style_id)


def _relink_hyperlinks(
    paragraph: XmlElement,
    relationships: Mapping[str, PartRelationship],
    targets: HyperlinkTargets,
    warnings: list[str],
) -> None:
    attribute = f"{{{R_NAMESPACE}}}id"
    for hyperlink in paragraph.iter(W_HYPERLINK):
        old = hyperlink.get(attribute)
        if old is None:
            continue
        relationship = relationships.get(old)
        if (
            relationship is None
            or not relationship.external
            or relationship.relationship_type != HYPERLINK_RELATIONSHIP
        ):
            del hyperlink.attrib[attribute]
            warnings.append("a hyperlink whose target the source does not give was kept as text, unlinked")
            continue
        hyperlink.set(attribute, targets.relationship_for(relationship.target))


def _drop_numbering(paragraph: XmlElement, warnings: list[str]) -> None:
    for numbering in list(paragraph.iter(W_NUMBERING)):
        _remove(numbering)
        warnings.append("a list number was dropped: the built file has no numbering part")


def _write_replacements(paragraph: XmlElement, stand_in: str | None) -> int:
    """Write U+FFFD where the stand-in stands, counting each one."""
    if stand_in is None:
        return 0
    count = 0
    for element in paragraph.iter():
        if element.text and stand_in in element.text:
            count += element.text.count(stand_in)
            element.text = element.text.replace(stand_in, REPLACEMENT_CHARACTER)
        if element.tail and stand_in in element.tail:
            count += element.tail.count(stand_in)
            element.tail = element.tail.replace(stand_in, REPLACEMENT_CHARACTER)
        for name, raw in list(element.attrib.items()):
            value = _string(raw)
            if stand_in in value:
                count += value.count(stand_in)
                element.set(name, value.replace(stand_in, REPLACEMENT_CHARACTER))
    return count


def _in_range(source: OpenedSource, first: int, last: int) -> Iterator[tuple[int, BodyParagraph]]:
    for index in range(first, last + 1):
        yield index, source.paragraphs[index]


def copy_card(
    source: OpenedSource,
    *,
    first_element_index: int,
    last_element_index: int,
    units: Callable[[int], StructuralUnit],
    profile: StyleProfile,
    base_style_ids: frozenset[str],
    hyperlinks: HyperlinkTargets,
) -> CopiedCard | UnsupportedCard:
    """Copy the paragraphs `first_element_index` to `last_element_index` of `source`, or refuse them.

    `units` gives the unit the E31 parser read each paragraph as; it says which paragraph is the tag
    and which the last of the cite. Hyperlinks are allocated in `hyperlinks` only for a card that is
    copied.
    """
    if not 0 <= first_element_index <= last_element_index < len(source.paragraphs):
        raise ValueError("the card's element indices fall outside its source's paragraphs")
    kinds: set[UnsupportedContentKind] = set()
    refused_at: list[int] = []
    cleaned: list[tuple[int, XmlElement]] = []
    for index, paragraph in _in_range(source, first_element_index, last_element_index):
        found: set[UnsupportedContentKind] = set()
        if paragraph.in_text_box:
            # A text box's paragraphs follow the paragraph that holds the box, which is in the card's
            # range before them and is refused for the box (`_unsupported_kinds`).
            continue
        if paragraph.in_table:
            found.add(UnsupportedContentKind.TABLE)
        else:
            copied = copy.deepcopy(paragraph.element)
            _resolve_tracked_changes_and_marks(copied)
            found |= _unsupported_kinds(copied)
            cleaned.append((index, copied))
        if found:
            kinds |= found
            refused_at.append(index)
    if kinds:
        return UnsupportedCard(kinds=tuple(sorted(kinds)), element_indices=tuple(refused_at))

    styles = _StyleMap(source.package, profile, base_style_ids)
    warnings: list[str] = []
    replaced = 0
    for _, paragraph in cleaned:
        _remap_styles(paragraph, styles, warnings)
        _drop_numbering(paragraph, warnings)
        _relink_hyperlinks(paragraph, source.relationships, hyperlinks, warnings)
        replaced += _write_replacements(paragraph, source.stand_in)

    tag: XmlElement | None = None
    body = list(cleaned)
    if units(first_element_index) is StructuralUnit.TAG:
        tag = body.pop(0)[1]
        _set_paragraph_style(tag, styles.tag_style_id)
    last_cite = max(
        (position for position, (index, _) in enumerate(body) if units(index) is StructuralUnit.CITE),
        default=-1,
    )
    return CopiedCard(
        tag=tag,
        through_cite=tuple(paragraph for _, paragraph in body[: last_cite + 1]),
        after_cite=tuple(paragraph for _, paragraph in body[last_cite + 1 :]),
        warnings=tuple(dict.fromkeys(warnings)),
        forbidden_characters_replaced=replaced,
    )
