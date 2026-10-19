"""The run copier: a card's paragraphs copied out of a synthetic source as OOXML (`v1-e33-t02`).

Each source is built in memory. What is asserted is the markup the copier hands the writer: the
`w:t` text and run properties as the source wrote them, and every change the copier makes mirrored on
a rule of the E31 parser (tracked changes, comments, styles through the profile), plus what it refuses.
"""

from __future__ import annotations

from datetime import date

import pytest
from lxml import etree

from debate_core.application.ports.evidence_file_writer import UnsupportedContentKind
from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import ParsedDocument
from debate_core.domain.style_profile import StructuralUnit, StyleProfile
from debate_core.integrations.docx_file_writer.base_template import BaseTemplate
from debate_core.integrations.docx_file_writer.run_copier import (
    HYPERLINK_RELATIONSHIP,
    CopiedCard,
    HyperlinkTargets,
    UnsupportedCard,
    copy_card,
    open_source,
)
from debate_core.integrations.docx_parser.package import W_NAMESPACE, XmlElement, check_replacement_character
from debate_core.integrations.docx_parser.parser import DebateDocxParser
from debate_core.testing.docx_builder import (
    DEFAULT_STYLE_DEFINITIONS,
    build_docx,
    build_styles_xml,
    paragraph_xml,
    run_xml,
)

W = f"{{{W_NAMESPACE}}}"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

TAG = paragraph_xml(run_xml("Moratoria raise prices for every ratepayer"), style="Heading4")
CITE = paragraph_xml(
    run_xml("Lindqvist 26", character_style="Style13ptBold")
    + run_xml(", Senior Fellow, Synthetic Energy Review, 3-4-2026")
)
BODY = paragraph_xml(
    run_xml("A moratorium ", half_points=16)
    + run_xml("freezes supply", character_style="StyleUnderline", highlight="cyan")
    + run_xml(" while demand keeps rising, so ", half_points=16)
    + run_xml("prices climb", character_style="Emphasis", bold=True, highlight="green")
    + run_xml(" in every service area.", half_points=16)
)


def _parse(parser: DebateDocxParser, content: bytes) -> ParsedDocument:
    import hashlib

    source = SourceDocument(
        sha256=hashlib.sha256(content).hexdigest(),
        byte_size=len(content),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist="hspolicy26",
        first_seen_snapshot=date(2026, 9, 15),
        last_seen_snapshot=date(2026, 9, 15),
    )
    parsed = parser.parse(content, source, source_path="synthetic.docx")
    assert isinstance(parsed, ParsedDocument), parsed
    return parsed


def _copy(
    content: bytes,
    parser: DebateDocxParser,
    profile: StyleProfile,
    base: BaseTemplate,
    *,
    card: int = 0,
    targets: HyperlinkTargets | None = None,
) -> CopiedCard | UnsupportedCard:
    parsed = _parse(parser, content)
    assert parsed.cards, "the synthetic source holds no card"
    chosen = parsed.cards[card]
    units = {section.element_index: section.unit for section in parsed.sections}
    return copy_card(
        open_source(content),
        first_element_index=chosen.provenance.first_element_index,
        last_element_index=chosen.provenance.last_element_index,
        units=lambda index: units.get(index, StructuralUnit.OTHER),
        profile=profile,
        base_style_ids=base.style_ids,
        hyperlinks=targets if targets is not None else HyperlinkTargets(),
    )


def _copied(result: CopiedCard | UnsupportedCard) -> CopiedCard:
    assert isinstance(result, CopiedCard), result
    return result


def _xml(element: XmlElement) -> str:
    """The element in exclusive canonical form: namespace declarations it does not use are left out."""
    return etree.tostring(element, method="c14n", exclusive=True).decode("utf-8")


def _text(element: XmlElement) -> str:
    return "".join(str(piece) for piece in element.itertext())


def _source_paragraph(content: bytes, index: int) -> XmlElement:
    return open_source(content).paragraphs[index].element


# ------------------------------------------------------------------------------------------------
# What is copied as it stands
# ------------------------------------------------------------------------------------------------


def test_a_card_in_profile_styles_is_copied_element_for_element(
    parser: DebateDocxParser, profile: StyleProfile, base: BaseTemplate
) -> None:
    content = build_docx(TAG + CITE + BODY)
    card = _copied(_copy(content, parser, profile, base))
    assert card.tag is not None
    assert [_xml(paragraph) for paragraph in card.through_cite] == [_xml(_source_paragraph(content, 1))]
    assert [_xml(paragraph) for paragraph in card.after_cite] == [_xml(_source_paragraph(content, 2))]
    assert card.warnings == ()
    assert card.forbidden_characters_replaced == 0


def test_the_tag_cite_and_body_are_split_where_the_provenance_line_goes(
    parser: DebateDocxParser, profile: StyleProfile, base: BaseTemplate
) -> None:
    second_cite = paragraph_xml(
        run_xml("Okonkwo 25", character_style="Style13ptBold") + run_xml(", also cited")
    )
    undertag = paragraph_xml(run_xml("Read with the uniqueness card"), style="Undertag")
    content = build_docx(TAG + undertag + CITE + second_cite + BODY + BODY)
    card = _copied(_copy(content, parser, profile, base))
    assert card.tag is not None and _text(card.tag).startswith("Moratoria")
    assert [_text(paragraph)[:12] for paragraph in card.through_cite] == [
        "Read with th",
        "Lindqvist 26",
        "Okonkwo 25, ",
    ]
    assert len(card.after_cite) == 2


def test_a_card_with_no_cite_has_nothing_before_the_line_but_its_tag(
    parser: DebateDocxParser, profile: StyleProfile, base: BaseTemplate
) -> None:
    card = _copied(_copy(build_docx(TAG + BODY), parser, profile, base))
    assert card.tag is not None
    assert card.through_cite == ()
    assert len(card.after_cite) == 1


def test_a_heuristic_tag_is_given_the_profile_tag_style(
    parser: DebateDocxParser, profile: StyleProfile, base: BaseTemplate
) -> None:
    heuristic_tag = paragraph_xml(run_xml("Moratoria raise prices", bold=True), outline_level=3)
    card = _copied(_copy(build_docx(heuristic_tag + CITE + BODY), parser, profile, base))
    assert card.tag is not None
    style = card.tag.find(f"{W}pPr/{W}pStyle")
    assert style is not None and style.get(f"{W}val") == "Heading4"
    assert card.tag.find(f"{W}pPr/{W}outlineLvl") is not None, "the rest of the properties stay"


# ------------------------------------------------------------------------------------------------
# Tracked changes, comments and editing marks: the parser's rules
# ------------------------------------------------------------------------------------------------

AUTHOR = 'w:author="Coach Fictional" w:date="2026-09-01T10:00:00Z"'

TRACKED_BODY = (
    '<w:p w:rsidR="00A1B2C3" w:rsidRDefault="00A1B2C3" '
    'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"'
    ' w14:paraId="1A2B3C4D" w14:textId="77777777">'
    f'<w:pPr><w:rPr><w:ins w:id="9" {AUTHOR}/></w:rPr>'
    f'<w:pPrChange w:id="8" {AUTHOR}><w:pPr/></w:pPrChange></w:pPr>'
    '<w:bookmarkStart w:id="0" w:name="_Toc1"/>'
    '<w:commentRangeStart w:id="3"/>'
    '<w:r w:rsidRPr="00D4E5F6"><w:rPr><w:rStyle w:val="StyleUnderline"/>'
    f'<w:rPrChange w:id="7" {AUTHOR}><w:rPr/></w:rPrChange></w:rPr>'
    '<w:t xml:space="preserve">Supply </w:t></w:r>'
    f'<w:ins w:id="1" {AUTHOR}><w:r><w:rPr><w:highlight w:val="yellow"/>'
    "</w:rPr><w:t>shrinks</w:t></w:r></w:ins>"
    f'<w:del w:id="2" {AUTHOR}><w:r><w:delText xml:space="preserve"> grows</w:delText></w:r></w:del>'
    f'<w:moveFrom w:id="4" {AUTHOR}><w:r><w:t> later</w:t></w:r></w:moveFrom>'
    f'<w:moveTo w:id="5" {AUTHOR}><w:r><w:t xml:space="preserve"> now</w:t></w:r></w:moveTo>'
    '<w:proofErr w:type="spellStart"/><w:r><w:t xml:space="preserve"> under the moratorium.</w:t></w:r>'
    '<w:proofErr w:type="spellEnd"/>'
    '<w:commentRangeEnd w:id="3"/>'
    '<w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr><w:commentReference w:id="3"/></w:r>'
    '<w:permStart w:id="6" w:edGrp="everyone"/><w:permEnd w:id="6"/>'
    '<w:bookmarkEnd w:id="0"/>'
    "</w:p>"
)


@pytest.fixture
def tracked(parser: DebateDocxParser, profile: StyleProfile, base: BaseTemplate) -> CopiedCard:
    return _copied(_copy(build_docx(TAG + CITE + TRACKED_BODY), parser, profile, base))


def test_a_tracked_insertion_is_kept_and_a_deletion_dropped_as_the_parser_reads_them(
    tracked: CopiedCard,
) -> None:
    body = tracked.after_cite[0]
    assert _text(body) == "Supply shrinks now under the moratorium."
    markup = _xml(body)
    for gone in ("w:ins", "w:del ", "w:delText", "w:moveFrom", "w:moveTo", " grows", " later"):
        assert gone not in markup, gone
    assert '<w:highlight w:val="yellow">' in markup, "the inserted run keeps its formatting"


def test_comments_bookmarks_proofing_and_permission_marks_are_dropped(tracked: CopiedCard) -> None:
    markup = _xml(tracked.after_cite[0])
    for gone in ("commentRange", "commentReference", "CommentReference", "bookmark", "proofErr", "perm"):
        assert gone not in markup, gone
    assert tracked.warnings == (), "the comment's run goes with its reference, so no style is unmapped"


def test_no_author_date_or_editing_fingerprint_survives(tracked: CopiedCard) -> None:
    markup = _xml(tracked.after_cite[0])
    for gone in ("Coach Fictional", "w:author", "w:date", "rsid", "paraId", "textId", "PrChange"):
        assert gone not in markup, gone


def test_the_stripped_paragraph_reads_as_the_parser_read_the_source(
    parser: DebateDocxParser, tracked: CopiedCard
) -> None:
    content = build_docx(TAG + CITE + TRACKED_BODY)
    assert _parse(parser, content).cards[0].evidence_text == _text(tracked.after_cite[0])


# ------------------------------------------------------------------------------------------------
# Styles through the profile (ac3)
# ------------------------------------------------------------------------------------------------

ALIASED_STYLES = build_styles_xml(
    (
        *DEFAULT_STYLE_DEFINITIONS,
        ("Tag", "paragraph", "Tag", "Normal"),
        ("Underline", "character", "Underline", "DefaultParagraphFont"),
        ("Style1", "character", "Style Underline", "DefaultParagraphFont"),
        ("TeamUnderline", "character", "Team Underline", "StyleUnderline"),
        ("CiteChar", "character", "Cite Char", "DefaultParagraphFont"),
        ("FancyChar", "character", "Fancy Char", "DefaultParagraphFont"),
        ("Hyperlink", "character", "Hyperlink", "DefaultParagraphFont"),
    )
)


@pytest.fixture
def aliased(parser: DebateDocxParser, profile: StyleProfile, base: BaseTemplate) -> CopiedCard:
    body = paragraph_xml(
        run_xml("by alias id ", character_style="Underline")
        + run_xml("by drifted name ", character_style="Style1")
        + run_xml("by basedOn ", character_style="TeamUnderline")
        + run_xml("unknown style ", character_style="FancyChar", bold=True, highlight="cyan")
        + run_xml("a link style", character_style="Hyperlink")
    )
    cite = paragraph_xml(run_xml("Lindqvist 26", character_style="CiteChar") + run_xml(", Senior Fellow"))
    tag = paragraph_xml(run_xml("Moratoria raise prices"), style="Tag")
    content = build_docx(tag + cite + body, styles_xml=ALIASED_STYLES)
    return _copied(_copy(content, parser, profile, base))


def _run_styles(paragraph: XmlElement) -> list[str | None]:
    styles: list[str | None] = []
    for run in paragraph.iter(f"{W}r"):
        style = run.find(f"{W}rPr/{W}rStyle")
        styles.append(None if style is None else style.get(f"{W}val"))
    return styles


def test_source_character_styles_are_remapped_to_the_profile_ids(aliased: CopiedCard) -> None:
    assert _run_styles(aliased.after_cite[0]) == [
        "StyleUnderline",
        "StyleUnderline",
        "StyleUnderline",
        None,
        "Hyperlink",
    ]
    assert _run_styles(aliased.through_cite[0]) == ["Style13ptBold", None]


def test_a_source_paragraph_style_alias_is_remapped_to_the_profile_tag_style(aliased: CopiedCard) -> None:
    assert aliased.tag is not None
    style = aliased.tag.find(f"{W}pPr/{W}pStyle")
    assert style is not None and style.get(f"{W}val") == "Heading4"


def test_an_unmapped_style_keeps_its_direct_formatting_and_is_listed_as_a_warning(
    aliased: CopiedCard,
) -> None:
    unknown = list(aliased.after_cite[0].iter(f"{W}r"))[3]
    markup = _xml(unknown)
    assert "<w:b>" in markup and '<w:highlight w:val="cyan">' in markup
    assert aliased.warnings == (
        "the source's character style 'FancyChar' ('Fancy Char') is not one the style profile maps; "
        "it was removed and the direct formatting kept",
    )


def test_numbering_is_dropped_with_a_warning(
    parser: DebateDocxParser, profile: StyleProfile, base: BaseTemplate
) -> None:
    numbered = (
        '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="4"/></w:numPr></w:pPr>'
        '<w:r><w:rPr><w:rStyle w:val="StyleUnderline"/><w:highlight w:val="cyan"/></w:rPr>'
        "<w:t>first point of the card</w:t></w:r></w:p>"
    )
    card = _copied(_copy(build_docx(TAG + CITE + numbered), parser, profile, base))
    assert "numPr" not in _xml(card.after_cite[0])
    assert card.warnings == ("a list number was dropped: the built file has no numbering part",)


# ------------------------------------------------------------------------------------------------
# Hyperlinks
# ------------------------------------------------------------------------------------------------

LINKED_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1"'
    ' Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
    'Target="styles.xml"/>'
    f'<Relationship Id="rId7" Type="{HYPERLINK_RELATIONSHIP}" Target="https://example.org/synthetic-review" '
    'TargetMode="External"/>'
    "</Relationships>"
)


def _linked_cite(relationship_id: str) -> str:
    return (
        f'<w:p xmlns:r="{R_NS}"><w:r><w:rPr><w:rStyle w:val="Style13ptBold"/>'
        "</w:rPr><w:t>Lindqvist 26</w:t></w:r>"
        f'<w:hyperlink r:id="{relationship_id}"><w:r><w:rPr><w:rStyle w:val="Hyperlink"/></w:rPr>'
        "<w:t>synthetic-review</w:t></w:r></w:hyperlink></w:p>"
    )


def test_a_hyperlink_target_is_recreated_in_the_built_file(
    parser: DebateDocxParser, profile: StyleProfile, base: BaseTemplate
) -> None:
    content = build_docx(
        TAG + _linked_cite("rId7") + BODY, extra_parts={"word/_rels/document.xml.rels": LINKED_RELS}
    )
    targets = HyperlinkTargets()
    card = _copied(_copy(content, parser, profile, base, targets=targets))
    hyperlink = card.through_cite[0].find(f"{W}hyperlink")
    assert hyperlink is not None and hyperlink.get(f"{{{R_NS}}}id") == "rId3"
    assert targets.relationships() == (
        ("rId3", HYPERLINK_RELATIONSHIP, "https://example.org/synthetic-review"),
    )
    assert card.warnings == ()


def test_a_hyperlink_whose_target_is_missing_is_kept_as_text_with_a_warning(
    parser: DebateDocxParser, profile: StyleProfile, base: BaseTemplate
) -> None:
    content = build_docx(TAG + _linked_cite("rId99") + BODY)
    card = _copied(_copy(content, parser, profile, base))
    hyperlink = card.through_cite[0].find(f"{W}hyperlink")
    assert hyperlink is not None and hyperlink.get(f"{{{R_NS}}}id") is None
    assert "synthetic-review" in _text(card.through_cite[0])
    assert card.warnings == ("a hyperlink whose target the source does not give was kept as text, unlinked",)


# ------------------------------------------------------------------------------------------------
# What is refused (ac4)
# ------------------------------------------------------------------------------------------------

DRAWING_NAMESPACES = (
    'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture" '
    'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
    'xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" '
    'xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office" '
    f'xmlns:r="{R_NS}"'
)

IMAGE = (
    '<w:drawing><wp:inline><a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
    '<pic:pic><pic:blipFill><a:blip r:embed="rId9"/></pic:blipFill></pic:pic></a:graphicData></a:graphic>'
    "</wp:inline></w:drawing>"
)
TEXT_BOX = (
    "<w:drawing><wp:anchor><a:graphic><a:graphicData><wps:wsp><wps:txbx><w:txbxContent>"
    "<w:p><w:r><w:t>a note in the margin</w:t></w:r></w:p>"
    "</w:txbxContent></wps:txbx></wps:wsp></a:graphicData></a:graphic></wp:anchor></w:drawing>"
)
OBJECT = (
    '<w:object><v:shape id="_x0000_i1025"/><o:OLEObject ProgID="Excel.Sheet.12" r:id="rId10"/></w:object>'
)
CHART = (
    '<w:drawing><wp:inline><a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/chart">'
    '<c:chart r:id="rId11"/></a:graphicData></a:graphic></wp:inline></w:drawing>'
)
FOOTNOTE = '<w:footnoteReference w:id="1"/>'


def _body_holding(inner: str) -> str:
    return (
        f"<w:p {DRAWING_NAMESPACES}>"
        '<w:r><w:rPr><w:rStyle w:val="StyleUnderline"/><w:highlight w:val="cyan"/></w:rPr>'
        '<w:t xml:space="preserve">Prices climb </w:t></w:r>'
        f"<w:r>{inner}</w:r>"
        '<w:r><w:rPr><w:rStyle w:val="StyleUnderline"/></w:rPr>'
        '<w:t xml:space="preserve"> everywhere.</w:t></w:r>'
        "</w:p>"
    )


@pytest.mark.parametrize(
    ("inner", "kind"),
    [
        (IMAGE, UnsupportedContentKind.IMAGE),
        (TEXT_BOX, UnsupportedContentKind.TEXT_BOX),
        (OBJECT, UnsupportedContentKind.EMBEDDED_OBJECT),
        (CHART, UnsupportedContentKind.EMBEDDED_OBJECT),
        (FOOTNOTE, UnsupportedContentKind.FOOTNOTE),
    ],
    ids=["image", "text-box", "embedded-object", "chart", "footnote"],
)
def test_content_that_cannot_be_copied_losslessly_is_refused_by_kind(
    parser: DebateDocxParser,
    profile: StyleProfile,
    base: BaseTemplate,
    inner: str,
    kind: UnsupportedContentKind,
) -> None:
    result = _copy(build_docx(TAG + CITE + _body_holding(inner)), parser, profile, base)
    assert isinstance(result, UnsupportedCard)
    assert result.kinds == (kind,)
    assert result.element_indices == (2,)


def test_every_kind_a_card_holds_is_listed(
    parser: DebateDocxParser, profile: StyleProfile, base: BaseTemplate
) -> None:
    content = build_docx(TAG + CITE + _body_holding(IMAGE) + _body_holding(FOOTNOTE + OBJECT))
    result = _copy(content, parser, profile, base)
    assert isinstance(result, UnsupportedCard)
    assert set(result.kinds) == {
        UnsupportedContentKind.IMAGE,
        UnsupportedContentKind.FOOTNOTE,
        UnsupportedContentKind.EMBEDDED_OBJECT,
    }
    assert result.element_indices == (2, 3)


def test_a_table_inside_a_card_is_refused(
    parser: DebateDocxParser, profile: StyleProfile, base: BaseTemplate
) -> None:
    table = "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>speech time</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
    result = _copy(build_docx(TAG + CITE + BODY + table + BODY), parser, profile, base)
    assert isinstance(result, UnsupportedCard)
    assert result.kinds == (UnsupportedContentKind.TABLE,)


def test_a_picture_somebody_deleted_does_not_refuse_the_card(
    parser: DebateDocxParser, profile: StyleProfile, base: BaseTemplate
) -> None:
    deleted = f'<w:del w:id="1" {AUTHOR}><w:r>{IMAGE}</w:r></w:del>'
    body = _body_holding("").replace("<w:r></w:r>", deleted)
    card = _copied(_copy(build_docx(TAG + CITE + body), parser, profile, base))
    assert "<w:drawing" not in _xml(card.after_cite[0])


# ------------------------------------------------------------------------------------------------
# Characters XML 1.0 forbids (t15's rule)
# ------------------------------------------------------------------------------------------------


def _raw_body(text: str) -> str:
    return (
        '<w:p><w:r><w:rPr><w:rStyle w:val="StyleUnderline"/><w:highlight w:val="cyan"/></w:rPr>'
        f'<w:t xml:space="preserve">{text}</w:t></w:r></w:p>'
    )


def test_forbidden_characters_are_written_as_the_replacement_character_and_counted(
    parser: DebateDocxParser, profile: StyleProfile, base: BaseTemplate
) -> None:
    content = build_docx(TAG + CITE + _raw_body("Prices\x01 climb￾ everywhere."))
    card = _copied(_copy(content, parser, profile, base))
    assert _text(card.after_cite[0]) == "Prices� climb� everywhere."
    assert card.forbidden_characters_replaced == 2
    assert _parse(parser, content).cards[0].evidence_text == "Prices� climb� everywhere."


def test_a_replacement_character_the_source_wrote_itself_is_not_counted(
    parser: DebateDocxParser, profile: StyleProfile, base: BaseTemplate
) -> None:
    content = build_docx(TAG + CITE + _raw_body("Prices� climb\x02 everywhere."))
    card = _copied(_copy(content, parser, profile, base))
    assert _text(card.after_cite[0]) == "Prices� climb� everywhere."
    assert card.forbidden_characters_replaced == 1


def test_the_count_holds_when_the_source_uses_the_first_private_use_character(
    parser: DebateDocxParser, profile: StyleProfile, base: BaseTemplate
) -> None:
    content = build_docx(TAG + CITE + _raw_body("Prices climb\x01 everywhere."))
    assert open_source(content).stand_in == ""
    card = _copied(_copy(content, parser, profile, base))
    assert _text(card.after_cite[0]) == "Prices climb� everywhere."
    assert card.forbidden_characters_replaced == 1


def test_a_source_with_no_forbidden_character_is_opened_once_with_no_stand_in() -> None:
    assert open_source(build_docx(TAG + CITE + BODY)).stand_in is None


def test_only_the_copied_cards_replacements_are_counted(
    parser: DebateDocxParser, profile: StyleProfile, base: BaseTemplate
) -> None:
    second_tag = paragraph_xml(run_xml("A second card\x01 tag"), style="Heading4")
    content = build_docx(
        TAG + CITE + _raw_body("one\x01") + second_tag + CITE + _raw_body("two\x01 three\x01")
    )
    assert _copied(_copy(content, parser, profile, base, card=0)).forbidden_characters_replaced == 1
    assert _copied(_copy(content, parser, profile, base, card=1)).forbidden_characters_replaced == 3


@pytest.mark.parametrize("stand_in", ["<", "&", '"', "'", " ", "\n", "\x01", "￾", "ab", ""])
def test_a_stand_in_that_could_build_markup_or_move_a_word_is_refused(stand_in: str) -> None:
    with pytest.raises(ValueError, match="not a character a forbidden one may be replaced by"):
        check_replacement_character(stand_in)


@pytest.mark.parametrize("stand_in", ["�", "", ""])
def test_the_replacement_character_and_the_private_use_area_are_allowed(stand_in: str) -> None:
    assert check_replacement_character(stand_in) == stand_in


def test_a_comment_reference_inside_a_run_with_text_is_dropped_and_the_text_kept(
    parser: DebateDocxParser, profile: StyleProfile, base: BaseTemplate
) -> None:
    shared = (
        '<w:p><w:r><w:rPr><w:highlight w:val="cyan"/></w:rPr>'
        '<w:t xml:space="preserve">Supply shrinks under the moratorium.</w:t>'
        '<w:commentReference w:id="5"/></w:r></w:p>'
    )
    card = _copied(_copy(build_docx(TAG + CITE + shared), parser, profile, base))
    assert _text(card.after_cite[0]) == "Supply shrinks under the moratorium."
    assert "commentReference" not in _xml(card.after_cite[0])


def test_an_embedded_object_is_refused_even_with_no_relationship(
    parser: DebateDocxParser, profile: StyleProfile, base: BaseTemplate
) -> None:
    unlinked = '<w:object><v:shape id="_x0000_i1026"/></w:object>'
    result = _copy(build_docx(TAG + CITE + _body_holding(unlinked)), parser, profile, base)
    assert isinstance(result, UnsupportedCard)
    assert result.kinds == (UnsupportedContentKind.EMBEDDED_OBJECT,)


def test_anything_else_that_points_into_another_part_is_refused(
    parser: DebateDocxParser, profile: StyleProfile, base: BaseTemplate
) -> None:
    """Ink, as Word writes it: a content part behind a relationship, in no list of known objects."""
    ink = (
        '<mc:AlternateContent xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml">'
        '<mc:Choice Requires="w14"><w14:contentPart r:id="rId12"/></mc:Choice></mc:AlternateContent>'
    )
    result = _copy(build_docx(TAG + CITE + _body_holding(ink)), parser, profile, base)
    assert isinstance(result, UnsupportedCard)
    assert result.kinds == (UnsupportedContentKind.EMBEDDED_OBJECT,)


def test_a_hyperlink_to_an_internal_target_is_kept_as_text_with_a_warning(
    parser: DebateDocxParser, profile: StyleProfile, base: BaseTemplate
) -> None:
    internal = LINKED_RELS.replace(' TargetMode="External"', "")
    content = build_docx(
        TAG + _linked_cite("rId7") + BODY, extra_parts={"word/_rels/document.xml.rels": internal}
    )
    targets = HyperlinkTargets()
    card = _copied(_copy(content, parser, profile, base, targets=targets))
    hyperlink = card.through_cite[0].find(f"{W}hyperlink")
    assert hyperlink is not None and hyperlink.get(f"{{{R_NS}}}id") is None
    assert targets.relationships() == ()
    assert card.warnings == ("a hyperlink whose target the source does not give was kept as text, unlinked",)
