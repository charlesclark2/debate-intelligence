"""Building WordprocessingML packages from strings, for tests and for fixture generation.

A test of the debate `.docx` parser needs a Word package with particular contents: a paragraph
carrying `Heading4`, a run carrying both underline encodings at once, a zip with a hostile
compression ratio, a document part with an entity declaration in it. Writing that markup inline in
each test buries the one thing the test is about, and keeping `.docx` files on disk for it would
put twenty opaque binaries in the repository.

So packages are built here, in memory, from strings. The same helpers build the committed
structural fixtures (`scripts/generate_structural_fixtures.py`), which is what keeps a fixture and
a unit test describing a file the same way.

These build files the way Word writes them, not the way the parser happens to read them. When a
helper takes a shortcut — no `w:rsid` values, no theme part — it is because the parser is
documented never to read that part, not because it would fail on one.

**Nothing here is a real debate file.** Every string a caller passes is invented for a test. See
`tests/fixtures/debate_files/structural/MANIFEST.md` for why the repository holds no real ones.
"""

from __future__ import annotations

import zipfile
from collections.abc import Iterable, Mapping
from io import BytesIO
from xml.sax.saxutils import escape, quoteattr

__all__ = [
    "CONTENT_TYPES",
    "DEFAULT_STYLE_DEFINITIONS",
    "DOCUMENT_RELS",
    "MACRO_ENABLED_CONTENT_TYPES",
    "PACKAGE_RELS",
    "W_NAMESPACE",
    "build_docx",
    "build_document_xml",
    "build_styles_xml",
    "paragraph_xml",
    "run_xml",
]

W_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>
"""

MACRO_ENABLED_CONTENT_TYPES = CONTENT_TYPES.replace(
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
    "application/vnd.ms-word.document.macroEnabled.main+xml",
)

PACKAGE_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
    Target="word/document.xml"/>
</Relationships>
"""

DOCUMENT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles"
    Target="styles.xml"/>
</Relationships>
"""

#: A minimal style table: Word's two defaults plus the Verbatim styles a test refers to by id.
DEFAULT_STYLE_DEFINITIONS: tuple[tuple[str, str, str, str | None], ...] = (
    ("Normal", "paragraph", "Normal", None),
    ("DefaultParagraphFont", "character", "Default Paragraph Font", None),
    ("Heading1", "paragraph", "heading 1", "Normal"),
    ("Heading2", "paragraph", "heading 2", "Normal"),
    ("Heading3", "paragraph", "heading 3", "Normal"),
    ("Heading4", "paragraph", "heading 4", "Normal"),
    ("Analytic", "paragraph", "Analytic", "Heading4"),
    ("Undertag", "paragraph", "Undertag", "Normal"),
    ("Style13ptBold", "character", "Style 13 pt Bold", "DefaultParagraphFont"),
    ("StyleUnderline", "character", "Style Underline", "DefaultParagraphFont"),
    ("Emphasis", "character", "Emphasis", "DefaultParagraphFont"),
)


def build_styles_xml(
    definitions: Iterable[tuple[str, str, str, str | None]] = DEFAULT_STYLE_DEFINITIONS,
) -> str:
    """Render a `word/styles.xml` from `(styleId, type, name, basedOn)` tuples."""
    styles: list[str] = []
    for style_id, style_type, name, based_on in definitions:
        based = f"<w:basedOn w:val={quoteattr(based_on)}/>" if based_on else ""
        styles.append(
            f"<w:style w:type={quoteattr(style_type)} w:styleId={quoteattr(style_id)}>"
            f"<w:name w:val={quoteattr(name)}/>{based}</w:style>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:styles xmlns:w="{W_NAMESPACE}">' + "".join(styles) + "</w:styles>"
    )


def build_document_xml(body: str) -> str:
    """Wrap body markup in a `w:document`/`w:body`."""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W_NAMESPACE}" '
        'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006">'
        f"<w:body>{body}</w:body></w:document>"
    )


def run_xml(
    text: str,
    *,
    character_style: str | None = None,
    bold: bool | None = None,
    italic: bool | None = None,
    underline: str | None = None,
    highlight: str | None = None,
    half_points: int | None = None,
) -> str:
    """One `w:r` with the run properties a test cares about."""
    properties: list[str] = []
    if character_style is not None:
        properties.append(f"<w:rStyle w:val={quoteattr(character_style)}/>")
    if bold is not None:
        properties.append("<w:b/>" if bold else '<w:b w:val="0"/>')
    if italic is not None:
        properties.append("<w:i/>" if italic else '<w:i w:val="0"/>')
    if underline is not None:
        properties.append(f"<w:u w:val={quoteattr(underline)}/>")
    if highlight is not None:
        properties.append(f"<w:highlight w:val={quoteattr(highlight)}/>")
    if half_points is not None:
        properties.append(f'<w:sz w:val="{half_points}"/>')
    run_properties = f"<w:rPr>{''.join(properties)}</w:rPr>" if properties else ""
    return f'<w:r>{run_properties}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def paragraph_xml(
    runs: str,
    *,
    style: str | None = None,
    outline_level: int | None = None,
    bold: bool | None = None,
    half_points: int | None = None,
) -> str:
    """One `w:p` holding `runs`, with the paragraph properties a test cares about."""
    properties: list[str] = []
    if style is not None:
        properties.append(f"<w:pStyle w:val={quoteattr(style)}/>")
    if outline_level is not None:
        properties.append(f'<w:outlineLvl w:val="{outline_level}"/>')
    mark_properties: list[str] = []
    if bold is not None:
        mark_properties.append("<w:b/>" if bold else '<w:b w:val="0"/>')
    if half_points is not None:
        mark_properties.append(f'<w:sz w:val="{half_points}"/>')
    if mark_properties:
        properties.append(f"<w:rPr>{''.join(mark_properties)}</w:rPr>")
    paragraph_properties = f"<w:pPr>{''.join(properties)}</w:pPr>" if properties else ""
    return f"<w:p>{paragraph_properties}{runs}</w:p>"


def build_docx(
    body: str,
    *,
    styles_xml: str | None = None,
    content_types: str = CONTENT_TYPES,
    extra_parts: Mapping[str, bytes | str] | None = None,
    omit_parts: Iterable[str] = (),
    document_xml: str | None = None,
    compression: int = zipfile.ZIP_DEFLATED,
) -> bytes:
    """Build a `.docx` package in memory and return its bytes.

    `body` is the markup inside `w:body`; `document_xml` replaces the whole part when a test needs
    malformed or hostile XML. `omit_parts` drops a part that is normally present, which is how the
    tests for a package missing its document or its content types are built.
    """
    omitted = set(omit_parts)
    parts: dict[str, bytes | str] = {}
    if "[Content_Types].xml" not in omitted:
        parts["[Content_Types].xml"] = content_types
    if "_rels/.rels" not in omitted:
        parts["_rels/.rels"] = PACKAGE_RELS
    if "word/_rels/document.xml.rels" not in omitted:
        parts["word/_rels/document.xml.rels"] = DOCUMENT_RELS
    if "word/styles.xml" not in omitted:
        parts["word/styles.xml"] = styles_xml if styles_xml is not None else build_styles_xml()
    if "word/document.xml" not in omitted:
        parts["word/document.xml"] = document_xml if document_xml is not None else build_document_xml(body)
    for name, data in (extra_parts or {}).items():
        parts[name] = data

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    return buffer.getvalue()
