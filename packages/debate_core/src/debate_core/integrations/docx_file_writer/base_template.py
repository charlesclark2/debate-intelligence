"""The base document every built file starts from, generated from the style profile.

A built file's style definitions are the team's Verbatim template's, by way of the E31 style profile
(`v1-e31-t02`), and never a source document's: a file CardMirror has saved carries CardMirror's own
default definitions (ADR-0014; `docs/architecture/cardmirror-evaluation.md`, the hand check), and a
caselist upload carries whatever its author's machine had. So nothing a source holds outside a
card's paragraphs reaches a built file, and the style table comes from here.

:func:`render_base_template` writes `templates/base.docx` from the profile's
:attr:`~debate_core.domain.style_profile.StyleProfile.writer_style_definitions` and
:attr:`~debate_core.domain.style_profile.StyleProfile.writer_document_defaults`;
`scripts/build_file_base_template.py` commits the result, and a test fails when the committed file
and the profile differ. The writer reads the committed file, so it never hard-codes a style id.

## What is not measured

The Verbatim definitions are the survey's measurements. The rest are Word defaults the PM asked for
(2026-10-19), each marked "Word default, not measured" in the profile: `Normal`,
`Default Paragraph Font`, `Hyperlink`, the three linked character styles, and the document defaults.
`word/settings.xml` holds one more, Word's compatibility mode 15, so Word opens a built file as a
current document rather than in compatibility mode.

## A team's own template

`team_styles_xml` takes the `word/styles.xml` of a team's Verbatim template, committed and scrubbed,
when there is one (PM ruling, 2026-10-19). A style the profile names is then taken from the team's
definition, and so are the document defaults; a profile style the team's file does not define is
generated as before, and anything else in the team's file is left out. None is committed yet.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from importlib import resources
from io import BytesIO
from typing import Final
from zipfile import ZipFile

from lxml import etree

from debate_core.domain.style_profile import StyleProfile, WriterDocumentDefaults, WriterStyleDefinition
from debate_core.integrations.docx_file_writer.package_writer import write_package
from debate_core.integrations.docx_parser.package import (
    W_NAMESPACE,
    XmlElement,
    hardened_xml_parser,
    qualified_name,
)

__all__ = [
    "BASE_TEMPLATE_RESOURCE",
    "BaseTemplate",
    "load_base_template",
    "render_base_template",
    "render_styles_xml",
]

#: Where the committed base lives, inside this package.
BASE_TEMPLATE_RESOURCE: Final = "templates/base.docx"

_W: Final = {"w": W_NAMESPACE}

#: Word's compatibility mode for a current document. A Word default, not measured.
_COMPATIBILITY_MODE: Final = "15"
_WORD_COMPATIBILITY_URI: Final = "http://schemas.microsoft.com/office/word"

CONTENT_TYPES: Final = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    b'<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    b'<Default Extension="xml" ContentType="application/xml"/>'
    b'<Override PartName="/word/document.xml" '
    b'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    b'<Override PartName="/word/styles.xml" '
    b'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
    b'<Override PartName="/word/settings.xml" '
    b'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
    b'<Override PartName="/docProps/core.xml" '
    b'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
    b"</Types>"
)

PACKAGE_RELATIONSHIPS: Final = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    b'<Relationship Id="rId1" '
    b'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    b'Target="word/document.xml"/>'
    b'<Relationship Id="rId2" '
    b'Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
    b'Target="docProps/core.xml"/>'
    b"</Relationships>"
)

#: The document part's relationships every built file starts with; hyperlinks are added after them.
DOCUMENT_RELATIONSHIPS: Final = (
    ("rId1", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles", "styles.xml"),
    ("rId2", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings", "settings.xml"),
)


def _sub(parent: XmlElement, local_name: str, **attributes: str) -> XmlElement:
    element = etree.SubElement(parent, qualified_name(local_name))
    for key, value in attributes.items():
        element.set(qualified_name(key), value)
    return element


def _serialize(root: XmlElement) -> bytes:
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _run_properties(
    parent: XmlElement,
    *,
    font: str | None,
    bold: bool | None,
    color: str | None,
    half_points: int | None,
    underline: str | None,
) -> None:
    """`w:rPr` in the schema's element order: rFonts, b, color, sz, szCs, u."""
    if all(value is None for value in (font, bold, color, half_points, underline)):
        return
    properties = _sub(parent, "rPr")
    if font is not None:
        _sub(properties, "rFonts", ascii=font, hAnsi=font, cs=font)
    if bold is not None:
        if bold:
            _sub(properties, "b")
        else:
            _sub(properties, "b", val="0")
    if color is not None:
        _sub(properties, "color", val=color)
    if half_points is not None:
        _sub(properties, "sz", val=str(half_points))
        _sub(properties, "szCs", val=str(half_points))
    if underline is not None:
        _sub(properties, "u", val=underline)


def _style_element(definition: WriterStyleDefinition) -> XmlElement:
    """One `w:style`, its children in the schema's order: name, basedOn, next, qFormat, pPr, rPr."""
    style = etree.Element(qualified_name("style"), nsmap=_W)
    style.set(qualified_name("type"), definition.style_type)
    if definition.is_default:
        style.set(qualified_name("default"), "1")
    style.set(qualified_name("styleId"), definition.style_id)
    _sub(style, "name", val=definition.style_name)
    if definition.based_on is not None:
        _sub(style, "basedOn", val=definition.based_on)
    if definition.next_style_id is not None:
        _sub(style, "next", val=definition.next_style_id)
    _sub(style, "qFormat")
    if definition.style_type == "paragraph" and (
        definition.keep_with_next or definition.page_break_before or definition.outline_level is not None
    ):
        paragraph = _sub(style, "pPr")
        if definition.keep_with_next:
            _sub(paragraph, "keepNext")
        if definition.page_break_before:
            _sub(paragraph, "pageBreakBefore")
        if definition.outline_level is not None:
            _sub(paragraph, "outlineLvl", val=str(definition.outline_level))
    _run_properties(
        style,
        font=definition.font,
        bold=definition.bold,
        color=definition.color,
        half_points=definition.half_points,
        underline=definition.underline,
    )
    return style


def _document_defaults(defaults: WriterDocumentDefaults) -> XmlElement:
    element = etree.Element(qualified_name("docDefaults"), nsmap=_W)
    run = _sub(element, "rPrDefault")
    _run_properties(
        run, font=defaults.font, bold=None, color=None, half_points=defaults.half_points, underline=None
    )
    _sub(element, "pPrDefault")
    return element


def _team_styles(team_styles_xml: bytes) -> tuple[XmlElement | None, dict[str, XmlElement]]:
    """A team template's document defaults and its styles by id, read with the hardened parser."""
    root = etree.fromstring(team_styles_xml, parser=hardened_xml_parser())
    if root.tag != qualified_name("styles"):
        raise ValueError("a team styles part is a w:styles document")
    defaults = root.find(qualified_name("docDefaults"))
    styles: dict[str, XmlElement] = {}
    for style in root.iterfind(qualified_name("style")):
        style_id = style.get(qualified_name("styleId"))
        if style_id:
            styles[style_id] = style
    return defaults, styles


def render_styles_xml(profile: StyleProfile, *, team_styles_xml: bytes | None = None) -> bytes:
    """`word/styles.xml`: the document defaults, then every writer definition in the profile's order."""
    team_defaults, team = (None, {}) if team_styles_xml is None else _team_styles(team_styles_xml)
    root = etree.Element(qualified_name("styles"), nsmap=_W)
    root.append(
        etree.fromstring(etree.tostring(team_defaults))
        if team_defaults is not None
        else _document_defaults(profile.writer_document_defaults)
    )
    for definition in profile.writer_style_definitions:
        taken = team.get(definition.style_id)
        root.append(
            etree.fromstring(etree.tostring(taken)) if taken is not None else _style_element(definition)
        )
    return _serialize(root)


def _settings_xml() -> bytes:
    root = etree.Element(qualified_name("settings"), nsmap=_W)
    compatibility = _sub(root, "compat")
    _sub(
        compatibility,
        "compatSetting",
        name="compatibilityMode",
        uri=_WORD_COMPATIBILITY_URI,
        val=_COMPATIBILITY_MODE,
    )
    return _serialize(root)


def document_relationships_xml(extra: Iterable[tuple[str, str, str]] = ()) -> bytes:
    """`word/_rels/document.xml.rels`: styles and settings, then `extra` external targets in order."""
    namespace = "http://schemas.openxmlformats.org/package/2006/relationships"
    default_namespace: dict[str | None, str] = {None: namespace}
    root = etree.Element(f"{{{namespace}}}Relationships", nsmap=default_namespace)  # pyright: ignore[reportArgumentType]
    for relationship_id, relationship_type, target in DOCUMENT_RELATIONSHIPS:
        etree.SubElement(
            root, f"{{{namespace}}}Relationship", Id=relationship_id, Type=relationship_type, Target=target
        )
    for relationship_id, relationship_type, target in extra:
        etree.SubElement(
            root,
            f"{{{namespace}}}Relationship",
            Id=relationship_id,
            Type=relationship_type,
            Target=target,
            TargetMode="External",
        )
    return _serialize(root)


def core_properties_xml(title: str | None) -> bytes:
    """`docProps/core.xml` with a title at most: no creator, no lastModifiedBy, no dates."""
    core = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
    dc = "http://purl.org/dc/elements/1.1/"
    root = etree.Element(f"{{{core}}}coreProperties", nsmap={"cp": core, "dc": dc})
    if title is not None:
        etree.SubElement(root, f"{{{dc}}}title").text = title
    return _serialize(root)


def _empty_document_xml() -> bytes:
    root = etree.Element(qualified_name("document"), nsmap=_W)
    _sub(root, "body")
    return _serialize(root)


def render_base_template(profile: StyleProfile, *, team_styles_xml: bytes | None = None) -> bytes:
    """`base.docx`: the profile's styles, Word's compatibility setting, an empty body, a core part with
    no properties at all. The same profile always renders the same bytes."""
    return write_package(
        (
            ("[Content_Types].xml", CONTENT_TYPES),
            ("_rels/.rels", PACKAGE_RELATIONSHIPS),
            ("word/document.xml", _empty_document_xml()),
            ("word/_rels/document.xml.rels", document_relationships_xml()),
            ("word/styles.xml", render_styles_xml(profile, team_styles_xml=team_styles_xml)),
            ("word/settings.xml", _settings_xml()),
            ("docProps/core.xml", core_properties_xml(None)),
        )
    )


@dataclass(frozen=True, slots=True)
class BaseTemplate:
    """What the writer takes from the committed base: its style table and its settings, as bytes."""

    styles_xml: bytes
    settings_xml: bytes

    @property
    def style_ids(self) -> frozenset[str]:
        """Every `w:styleId` the base defines."""
        root = etree.fromstring(self.styles_xml, parser=hardened_xml_parser())
        return frozenset(
            style_id
            for style in root.iterfind(qualified_name("style"))
            if (style_id := style.get(qualified_name("styleId")))
        )

    @classmethod
    def from_docx(cls, content: bytes) -> BaseTemplate:
        """The style table and settings of a base `.docx`."""
        with ZipFile(BytesIO(content)) as archive:
            return cls(
                styles_xml=archive.read("word/styles.xml"), settings_xml=archive.read("word/settings.xml")
            )


def load_base_template() -> BaseTemplate:
    """The committed `templates/base.docx`."""
    content = resources.files(__package__).joinpath(BASE_TEMPLATE_RESOURCE).read_bytes()
    return BaseTemplate.from_docx(content)
