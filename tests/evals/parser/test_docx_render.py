"""The labeller's own reading of underline and highlight, from the document's XML (t18 ac4).

Every document here is invented. Expected ranges are written by hand from the markup each test
builds, never taken from a run of the renderer.
"""

from __future__ import annotations

import ast
from pathlib import Path
from xml.sax.saxutils import quoteattr

from tests.evals.parser.corpus import parse_evaluation_file
from tests.evals.parser.docx_render import render_docx
from tests.evals.parser.labels_schema import Category, DebateFormat, ManifestEntry, TemplateFamily
from tests.evals.parser.synthetic import CLOSING, OPENING, SECOND_BODY, UNDERLINED, build_synthetic_file

from debate_core.integrations.docx_parser import DebateDocxParser
from debate_core.testing.docx_builder import W_NAMESPACE, build_docx, paragraph_xml, run_xml

RENDERER = Path(__file__).with_name("docx_render.py")


def styles_xml(*styles: str, defaults: str = "") -> str:
    """A style table from raw `w:style` elements, with an optional `w:rPrDefault` run property set."""
    doc_defaults = f"<w:docDefaults><w:rPrDefault><w:rPr>{defaults}</w:rPr></w:rPrDefault></w:docDefaults>"
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:styles xmlns:w="{W_NAMESPACE}">{doc_defaults if defaults else ""}{"".join(styles)}</w:styles>'
    )


def style(
    style_id: str,
    kind: str,
    name: str,
    *,
    based_on: str | None = None,
    run_properties: str = "",
    default: bool = False,
) -> str:
    based = f"<w:basedOn w:val={quoteattr(based_on)}/>" if based_on else ""
    properties = f"<w:rPr>{run_properties}</w:rPr>" if run_properties else ""
    flag = ' w:default="1"' if default else ""
    return (
        f"<w:style w:type={quoteattr(kind)}{flag} w:styleId={quoteattr(style_id)}>"
        f"<w:name w:val={quoteattr(name)}/>{based}{properties}</w:style>"
    )


def an_entry() -> ManifestEntry:
    return ManifestEntry(
        digest=build_synthetic_file().digest,
        category=Category.TEAM,
        season="2025-26",
        debate_format=DebateFormat.LD,
        template_family=TemplateFamily.VERBATIM,
    )


def test_direct_underline_and_highlight_are_read() -> None:
    content = build_docx(
        paragraph_xml(
            run_xml("Plain start, ")
            + run_xml("underlined", underline="single")
            + run_xml(" then ")
            + run_xml("lit", highlight="yellow")
            + run_xml(" and ")
            + run_xml("both", underline="single", highlight="green")
        )
    )

    (paragraph,) = render_docx(content)

    assert paragraph.text == "Plain start, underlined then lit and both"
    assert paragraph.underline == ((13, 23), (37, 41))
    assert paragraph.highlight == ((29, 32), (37, 41))


def test_underline_and_highlight_inherited_from_a_style_are_read() -> None:
    """A character style's own `w:u`, a paragraph style's `w:highlight`, through `w:basedOn`."""
    content = build_docx(
        paragraph_xml(
            run_xml("Marked by the style")
            + run_xml(" and ")
            + run_xml("by run style", character_style="Cut"),
            style="Glow",
        ),
        styles_xml=styles_xml(
            style("Normal", "paragraph", "Normal", default=True),
            style("Lit", "paragraph", "Lit", based_on="Normal", run_properties='<w:highlight w:val="cyan"/>'),
            style("Glow", "paragraph", "Glow", based_on="Lit"),
            style("Base", "character", "Base", run_properties='<w:u w:val="single"/>'),
            style("Cut", "character", "Cut", based_on="Base"),
        ),
    )

    (paragraph,) = render_docx(content)

    assert paragraph.text == "Marked by the style and by run style"
    assert paragraph.highlight == ((0, 36),)
    assert paragraph.underline == ((24, 36),)


def test_the_default_paragraph_style_and_document_defaults_apply_to_a_paragraph_with_no_style() -> None:
    content = build_docx(
        paragraph_xml(run_xml("defaults")),
        styles_xml=styles_xml(
            style("Normal", "paragraph", "Normal", default=True, run_properties='<w:u w:val="single"/>'),
            defaults='<w:highlight w:val="yellow"/>',
        ),
    )

    (paragraph,) = render_docx(content)

    assert paragraph.underline == ((0, 8),)
    assert paragraph.highlight == ((0, 8),)


def test_direct_formatting_switches_off_what_a_style_switches_on() -> None:
    content = build_docx(
        paragraph_xml(
            run_xml("on ", character_style="Both")
            + '<w:r><w:rPr><w:rStyle w:val="Both"/><w:u w:val="none"/><w:highlight w:val="none"/></w:rPr>'
            '<w:t xml:space="preserve">off</w:t></w:r>'
        ),
        styles_xml=styles_xml(
            style(
                "Both", "character", "Both", run_properties='<w:u w:val="single"/><w:highlight w:val="red"/>'
            )
        ),
    )

    (paragraph,) = render_docx(content)

    assert paragraph.underline == ((0, 3),)
    assert paragraph.highlight == ((0, 3),)


def test_a_bare_underline_element_is_a_single_underline_and_words_mode_skips_spaces() -> None:
    content = build_docx(
        paragraph_xml(
            '<w:r><w:rPr><w:u/></w:rPr><w:t xml:space="preserve">bare</w:t></w:r>'
            + run_xml(" two words", underline="words")
        )
    )

    (paragraph,) = render_docx(content)

    assert paragraph.text == "bare two words"
    assert paragraph.underline == ((0, 4), (5, 8), (9, 14))


def test_headings_are_known_by_style_name_and_outline_level() -> None:
    content = build_docx(
        paragraph_xml(run_xml("Pocket"), style="Heading1")
        + paragraph_xml(run_xml("Block by outline"), outline_level=2)
        + paragraph_xml(run_xml("Body"))
    )

    pocket, block, body = render_docx(content)

    assert (pocket.heading_level, block.heading_level, body.heading_level) == (1, 3, None)


def test_bold_is_read_for_display() -> None:
    content = build_docx(paragraph_xml(run_xml("bold", bold=True) + run_xml(" not", bold=False)))

    (paragraph,) = render_docx(content)

    assert [(run.text, run.bold) for run in paragraph.runs] == [("bold", True), (" not", False)]


def test_the_renderer_finds_the_same_paragraphs_and_text_as_the_parser() -> None:
    """Paragraph order is the parser's element index: tables, text boxes and tracked changes included."""
    text_box = (
        '<w:r><mc:AlternateContent><mc:Choice Requires="wps"><w:drawing><w:txbxContent>'
        + paragraph_xml(run_xml("In a box"))
        + "</w:txbxContent></w:drawing></mc:Choice><mc:Fallback><w:pict><w:txbxContent>"
        + paragraph_xml(run_xml("In a box"))
        + "</w:txbxContent></w:pict></mc:Fallback></mc:AlternateContent></w:r>"
    )
    body = (
        paragraph_xml(run_xml("Before") + '<w:r><w:tab/><w:t>tabbed</w:t><w:br/><w:t>broken</w:t></w:r>')
        + paragraph_xml(
            run_xml("Kept ")
            + "<w:ins>" + run_xml("inserted") + "</w:ins>"
            + "<w:del><w:r><w:delText>gone</w:delText></w:r></w:del>"
            + '<w:hyperlink><w:r><w:t xml:space="preserve"> linked</w:t></w:r></w:hyperlink>'
        )
        + paragraph_xml(run_xml("Holds a box") + text_box)
        + "<w:tbl><w:tr><w:tc>"
        + paragraph_xml(run_xml("cell one"))
        + "</w:tc><w:tc>"
        + paragraph_xml(run_xml("cell two"))
        + "</w:tc></w:tr></w:tbl>"
        + "<w:sdt><w:sdtContent>" + paragraph_xml(run_xml("In a control")) + "</w:sdtContent></w:sdt>"
        + paragraph_xml(run_xml("After"))
    )  # fmt: skip
    for content in (build_docx(body), build_synthetic_file().content):
        parsed = parse_evaluation_file(DebateDocxParser(), an_entry(), content)
        rendered = render_docx(content)
        assert [paragraph.text for paragraph in rendered] == [section.text for section in parsed.sections]


def test_the_synthetic_files_formatting_is_what_its_markup_says() -> None:
    rendered = render_docx(build_synthetic_file().content)

    evidence, second_body = rendered[5], rendered[10]
    marked = (len(OPENING), len(OPENING) + len(UNDERLINED))
    assert evidence.text == OPENING + UNDERLINED + CLOSING
    assert evidence.underline == (marked,)
    assert evidence.highlight == (marked,)
    assert second_body.underline == ((0, len(SECOND_BODY)),)
    assert second_body.highlight == ()


def test_the_renderer_shares_no_code_with_the_parsers_run_reading() -> None:
    """ac4: the span a row shows is a second opinion, so it may not import the first one."""
    tree = ast.parse(RENDERER.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert imported, "the walk found no imports at all, so it proves nothing"
    assert not [name for name in imported if name.startswith(("debate_core", "tests."))], imported
