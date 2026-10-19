"""The base document is the style profile's, and the committed file is what the profile renders.

`templates/base.docx` holds the style table every built file uses (`v1-e33-t02`, node
`base-template`). Its style ids must be exactly the profile's writer definitions, its definitions the
profile's values, and nothing in it may come from a source document.
"""

from __future__ import annotations

import zipfile
from importlib import resources
from io import BytesIO
from pathlib import Path

from lxml import etree

from debate_core.domain.style_profile import UNMEASURED_MARKER, StructuralUnit, StyleProfile
from debate_core.integrations.docx_file_writer.base_template import (
    BASE_TEMPLATE_RESOURCE,
    BaseTemplate,
    render_base_template,
    render_styles_xml,
)
from debate_core.integrations.docx_file_writer.package_writer import ENTRY_ATTRIBUTES, FIXED_ZIP_TIMESTAMP
from debate_core.integrations.docx_parser.package import W_NAMESPACE, XmlElement

W = f"{{{W_NAMESPACE}}}"

COMMITTED = Path(
    str(resources.files("debate_core.integrations.docx_file_writer").joinpath(BASE_TEMPLATE_RESOURCE))
)


def _styles(styles_xml: bytes) -> dict[str, XmlElement]:
    root = etree.fromstring(styles_xml)
    return {style.get(f"{W}styleId") or "": style for style in root.iterfind(f"{W}style")}


def _value(style: XmlElement, path: str) -> str | None:
    found = style.find(path.replace("w:", W))
    return None if found is None else found.get(f"{W}val")


def test_the_committed_base_is_what_the_profile_renders(profile: StyleProfile) -> None:
    assert COMMITTED.is_file(), "missing; run: uv run scripts/build_file_base_template.py"
    assert COMMITTED.read_bytes() == render_base_template(profile), (
        "stale; run: uv run scripts/build_file_base_template.py"
    )


def test_the_base_style_ids_match_the_profile(profile: StyleProfile, base: BaseTemplate) -> None:
    assert base.style_ids == {definition.style_id for definition in profile.writer_style_definitions}


def test_every_heading_and_card_style_the_writer_writes_is_defined(
    profile: StyleProfile, base: BaseTemplate
) -> None:
    written_units = (
        StructuralUnit.POCKET,
        StructuralUnit.HAT,
        StructuralUnit.BLOCK,
        StructuralUnit.TAG,
        StructuralUnit.ANALYTIC,
        StructuralUnit.UNDERTAG,
        StructuralUnit.OTHER,
    )
    paragraph_ids = {rule.unit: rule.style_id for rule in profile.paragraph_styles}
    assert {paragraph_ids[unit] for unit in written_units} <= base.style_ids
    assert {rule.style_id for rule in profile.character_styles} <= base.style_ids


def test_each_definition_carries_the_profiles_values(base: BaseTemplate) -> None:
    styles = _styles(base.styles_xml)
    assert _value(styles["Heading1"], "w:rPr/w:sz") == "52"
    assert styles["Heading1"].find(f"{W}pPr/{W}pageBreakBefore") is not None
    assert _value(styles["Heading2"], "w:rPr/w:u") == "double"
    assert styles["Heading4"].find(f"{W}pPr/{W}pageBreakBefore") is None
    assert _value(styles["Heading4"], "w:pPr/w:outlineLvl") == "3"
    assert _value(styles["Analytic"], "w:basedOn") == "Heading4"
    assert _value(styles["Analytic"], "w:rPr/w:color") == "1F3864"
    assert _value(styles["Undertag"], "w:rPr/w:color") == "385623"
    assert _value(styles["Style13ptBold"], "w:rPr/w:u") == "none"
    assert _value(styles["StyleUnderline"], "w:rPr/w:b") == "0"
    assert styles["Emphasis"].find(f"{W}rPr/{W}b") is None, "left inherited, as the profile says"
    assert styles["Normal"].get(f"{W}default") == "1"
    assert styles["DefaultParagraphFont"].get(f"{W}default") == "1"
    assert _value(styles["Hyperlink"], "w:rPr/w:color") == "0563C1"


def test_paragraph_properties_are_written_in_the_schemas_order(base: BaseTemplate) -> None:
    """Word refuses a style whose `w:pPr` children are out of the schema's sequence."""
    order = ["keepNext", "pageBreakBefore", "outlineLvl"]
    for style in _styles(base.styles_xml).values():
        properties = style.find(f"{W}pPr")
        if properties is None:
            continue
        names = [etree.QName(child).localname for child in properties]
        assert names == sorted(names, key=order.index), names


def test_the_document_defaults_are_the_profiles(profile: StyleProfile, base: BaseTemplate) -> None:
    root = etree.fromstring(base.styles_xml)
    defaults = root.find(f"{W}docDefaults/{W}rPrDefault/{W}rPr")
    assert defaults is not None
    fonts = defaults.find(f"{W}rFonts")
    assert fonts is not None and fonts.get(f"{W}ascii") == profile.writer_document_defaults.font
    assert _value(defaults, "w:sz") == str(profile.writer_document_defaults.half_points)


def test_the_word_defaults_are_the_pms_list_and_say_they_are_not_measured(profile: StyleProfile) -> None:
    unmeasured = {
        definition.style_id: definition.notes
        for definition in profile.writer_style_definitions
        if not definition.measured
    }
    assert set(unmeasured) == {
        "Normal",
        "DefaultParagraphFont",
        "Hyperlink",
        "UndertagChar",
        "AnalyticChar",
        "Heading4Char",
    }
    assert all(UNMEASURED_MARKER in notes for notes in unmeasured.values())
    assert UNMEASURED_MARKER in profile.writer_document_defaults.notes
    assert profile.writer_document_defaults.measured is False


def test_word_opens_it_as_a_current_document(base: BaseTemplate) -> None:
    root = etree.fromstring(base.settings_xml)
    setting = root.find(f"{W}compat/{W}compatSetting")
    assert setting is not None
    assert (setting.get(f"{W}name"), setting.get(f"{W}val")) == ("compatibilityMode", "15")


def test_the_base_carries_no_person_and_no_time(profile: StyleProfile) -> None:
    with zipfile.ZipFile(BytesIO(render_base_template(profile))) as archive:
        core = archive.read("docProps/core.xml").decode("utf-8")
        assert sorted(archive.namelist()) == sorted(
            [
                "[Content_Types].xml",
                "_rels/.rels",
                "docProps/core.xml",
                "word/_rels/document.xml.rels",
                "word/document.xml",
                "word/settings.xml",
                "word/styles.xml",
            ]
        )
        assert all(info.date_time == FIXED_ZIP_TIMESTAMP for info in archive.infolist())
        assert all(
            info.create_system == 0 and info.external_attr == ENTRY_ATTRIBUTES for info in archive.infolist()
        )
    for absent in ("creator", "lastModifiedBy", "created", "modified", "title"):
        assert absent not in core, absent


def test_the_same_profile_renders_the_same_bytes(profile: StyleProfile) -> None:
    assert render_base_template(profile) == render_base_template(profile)


TEAM_STYLES = (
    f'<w:styles xmlns:w="{W_NAMESPACE}">'
    '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Georgia" w:hAnsi="Georgia"/><w:sz w:val="24"/>'
    "</w:rPr></w:rPrDefault></w:docDefaults>"
    '<w:style w:type="paragraph" w:styleId="Heading4"><w:name w:val="heading 4"/>'
    '<w:rPr><w:b/><w:sz w:val="28"/></w:rPr></w:style>'
    '<w:style w:type="character" w:styleId="TeamOnlyStyle"><w:name w:val="Team Only"/></w:style>'
    "</w:styles>"
).encode()


def test_a_team_template_supplies_the_styles_it_defines_and_nothing_else(profile: StyleProfile) -> None:
    rendered = render_styles_xml(profile, team_styles_xml=TEAM_STYLES)
    styles = _styles(rendered)
    assert _value(styles["Heading4"], "w:rPr/w:sz") == "28", "the team's own tag size"
    assert _value(styles["Heading1"], "w:rPr/w:sz") == "52", "a style the team lacks is the profile's"
    assert "TeamOnlyStyle" not in styles, "a style the profile does not name is left out"
    assert set(styles) == {definition.style_id for definition in profile.writer_style_definitions}
    defaults = etree.fromstring(rendered).find(f"{W}docDefaults/{W}rPrDefault/{W}rPr/{W}sz")
    assert defaults is not None and defaults.get(f"{W}val") == "24"
