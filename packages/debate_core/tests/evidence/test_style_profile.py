"""Tests for the Verbatim/CardMirror style profile and its loader.

Three things are being held down here.

**The profile loads and resolves what real files contain.** The style ids, names and `basedOn`
links exercised below are the ones
[the style survey](../../../../docs/data/debate-file-style-survey.md) found across 2,066 files,
not invented examples — including `Heading411`, which appears in 197 files and is a Heading 4 that
inherits from `Heading1`.

**The CardMirror mapping is complete.** The coverage test reads the node and mark tables out of
`docs/architecture/cardmirror-evaluation.md` and fails if the profile has not accounted for every
type in them. A CardMirror schema change, or a new unit of our own, then shows up as a failing
test rather than as a silent gap.

**A malformed profile is refused loudly.** A style table with an ambiguous key, a shrink rule that
is not smaller than body text, or a CardMirror gap with no explanation are all things a future
edit could introduce and nothing else would catch.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from debate_core.domain.style_profile import (
    RunEmphasis,
    StructuralUnit,
    StyleMatchSource,
    StyleProfile,
    normalize_style_key,
    strip_deduplication_suffix,
)
from debate_core.evidence.style_profile_loader import (
    DEFAULT_STYLE_PROFILE_NAME,
    StyleProfileError,
    available_style_profiles,
    load_style_profile,
    load_style_profile_from_text,
    resolve_based_on_chain,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
CARDMIRROR_EVALUATION = REPO_ROOT / "docs" / "architecture" / "cardmirror-evaluation.md"
PROFILE_YAML = (
    REPO_ROOT
    / "packages/debate_core/src/debate_core/evidence/style_profiles"
    / f"{DEFAULT_STYLE_PROFILE_NAME}.yaml"
)


@pytest.fixture(scope="module")
def profile() -> StyleProfile:
    return load_style_profile()


# --------------------------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------------------------


def test_the_verbatim_profile_ships_with_the_package_and_loads(profile: StyleProfile) -> None:
    assert DEFAULT_STYLE_PROFILE_NAME in available_style_profiles()
    assert profile.name == DEFAULT_STYLE_PROFILE_NAME
    assert profile.profile_version
    assert profile.description


def test_the_profile_is_cached_so_every_parse_does_not_reread_it() -> None:
    assert load_style_profile() is load_style_profile()


def test_an_unknown_profile_name_lists_the_ones_that_exist() -> None:
    with pytest.raises(StyleProfileError, match="available profiles: verbatim"):
        load_style_profile("cardmirror-native")


def test_a_profile_that_is_not_a_mapping_is_refused() -> None:
    with pytest.raises(StyleProfileError, match="must be a mapping"):
        load_style_profile_from_text("- one\n- two\n")


def test_a_profile_that_is_not_valid_yaml_is_refused() -> None:
    with pytest.raises(StyleProfileError, match="not valid YAML"):
        load_style_profile_from_text("profile_version: [unclosed\n")


def test_a_profile_missing_a_required_section_names_the_section() -> None:
    with pytest.raises(StyleProfileError, match="does not match the model"):
        load_style_profile_from_text("profile_version: '1'\nname: partial\n")


# --------------------------------------------------------------------------------------------
# ac1 — the enum, and resolving every spelling the survey found
# --------------------------------------------------------------------------------------------


def test_the_structural_unit_enum_is_the_one_the_spec_names() -> None:
    assert [unit.value for unit in StructuralUnit] == [
        "POCKET",
        "HAT",
        "BLOCK",
        "TAG",
        "CITE",
        "EVIDENCE",
        "ANALYTIC",
        "UNDERTAG",
        "OTHER",
    ]


def test_every_structural_unit_has_a_paragraph_style_rule(profile: StyleProfile) -> None:
    assert {rule.unit for rule in profile.paragraph_styles} == set(StructuralUnit)


def test_every_run_emphasis_is_reachable_from_a_character_style_or_direct_formatting(
    profile: StyleProfile,
) -> None:
    """HIGHLIGHT, BOLD and SHRUNK are direct formatting; the rest have a character style."""
    from_styles = {rule.emphasis for rule in profile.character_styles}
    direct_only = {RunEmphasis.HIGHLIGHT, RunEmphasis.BOLD, RunEmphasis.SHRUNK}
    assert from_styles | direct_only == set(RunEmphasis)
    assert from_styles.isdisjoint(direct_only)


@pytest.mark.parametrize(
    ("style_id", "unit"),
    [
        ("Heading1", StructuralUnit.POCKET),
        ("Heading2", StructuralUnit.HAT),
        ("Heading3", StructuralUnit.BLOCK),
        ("Heading4", StructuralUnit.TAG),
        ("Analytic", StructuralUnit.ANALYTIC),
        ("Undertag", StructuralUnit.UNDERTAG),
        ("CiteParagraph", StructuralUnit.CITE),
        ("CardBody", StructuralUnit.EVIDENCE),
        ("Normal", StructuralUnit.OTHER),
    ],
)
def test_a_canonical_paragraph_style_id_resolves_as_verbatim(
    profile: StyleProfile, style_id: str, unit: StructuralUnit
) -> None:
    match = profile.resolve_paragraph_style(style_id)
    assert match is not None
    assert match.unit is unit
    assert match.match_source is StyleMatchSource.VERBATIM
    assert match.rule_id == f"verbatim-style-id:{style_id}"
    assert match.confidence == 1.0


@pytest.mark.parametrize(
    ("style_id", "emphasis"),
    [
        ("StyleUnderline", RunEmphasis.UNDERLINE),
        ("Emphasis", RunEmphasis.EMPHASIS),
        ("Style13ptBold", RunEmphasis.CITE),
        ("UndertagChar", RunEmphasis.UNDERTAG),
        ("AnalyticChar", RunEmphasis.ANALYTIC),
        ("Heading4Char", RunEmphasis.HEADING),
    ],
)
def test_a_canonical_character_style_id_resolves_as_verbatim(
    profile: StyleProfile, style_id: str, emphasis: RunEmphasis
) -> None:
    match = profile.resolve_character_style(style_id)
    assert match is not None
    assert match.emphasis is emphasis
    assert match.match_source is StyleMatchSource.VERBATIM


@pytest.mark.parametrize(
    ("alias", "unit"),
    [
        ("Pocket", StructuralUnit.POCKET),
        ("%tag", StructuralUnit.TAG),
        ("Analytics", StructuralUnit.ANALYTIC),
        ("cardtext", StructuralUnit.EVIDENCE),
        ("ListParagraph", StructuralUnit.OTHER),
        ("NormalWeb", StructuralUnit.OTHER),
    ],
)
def test_a_recorded_paragraph_alias_resolves_as_a_verbatim_alias(
    profile: StyleProfile, alias: str, unit: StructuralUnit
) -> None:
    match = profile.resolve_paragraph_style(alias)
    assert match is not None
    assert match.unit is unit
    assert match.match_source is StyleMatchSource.VERBATIM_ALIAS
    assert match.rule_id == f"verbatim-alias-id:{alias}"


@pytest.mark.parametrize(
    ("alias", "emphasis"),
    [
        ("UnderlineFIXEDChar", RunEmphasis.UNDERLINE),
        ("StyleBoldUnderline", RunEmphasis.UNDERLINE),
        ("AAAUNDERLINEKEYBOARD", RunEmphasis.UNDERLINE),
        ("IntenseEmphasis", RunEmphasis.EMPHASIS),
        ("CiteChar", RunEmphasis.CITE),
        ("TitleChar", RunEmphasis.HEADING),
    ],
)
def test_a_recorded_character_alias_resolves_as_a_verbatim_alias(
    profile: StyleProfile, alias: str, emphasis: RunEmphasis
) -> None:
    match = profile.resolve_character_style(alias)
    assert match is not None
    assert match.emphasis is emphasis
    assert match.match_source is StyleMatchSource.VERBATIM_ALIAS


@pytest.mark.parametrize(
    "spelling", ["Style 13 pt Bold", "style-13pt-bold", "STYLE13PTBOLD", "Style_13_pt_Bold"]
)
def test_spelling_and_separators_do_not_change_the_resolution(profile: StyleProfile, spelling: str) -> None:
    match = profile.resolve_character_style(spelling)
    assert match is not None
    assert match.emphasis is RunEmphasis.CITE


def test_a_style_id_a_converter_mangled_still_resolves_through_its_display_name(
    profile: StyleProfile,
) -> None:
    """Converted caselist uploads keep `<w:name w:val="heading 4"/>` when the id is lost."""
    match = profile.resolve_paragraph_style("a7", style_name="heading 4")
    assert match is not None
    assert match.unit is StructuralUnit.TAG
    assert match.match_source is StyleMatchSource.VERBATIM_ALIAS
    assert match.rule_id == "verbatim-alias-name:heading 4"


# --------------------------------------------------------------------------------------------
# ac1 — the resolution order, which the survey decided
# --------------------------------------------------------------------------------------------


def test_words_numeric_deduplication_suffix_is_stripped() -> None:
    assert strip_deduplication_suffix("heading411") == ["heading41", "heading4", "heading"]
    assert strip_deduplication_suffix("emphasis1") == ["emphasis"]
    assert strip_deduplication_suffix("heading4") == ["heading"]
    assert strip_deduplication_suffix("emphasis") == [], "nothing to strip"
    assert strip_deduplication_suffix("") == []


def test_heading411_is_a_tag_even_though_it_inherits_from_heading1(profile: StyleProfile) -> None:
    """The finding that fixes the resolution order: 197 surveyed files carry this style.

    Resolving it by `basedOn` would call those files' tags pockets. De-duplication runs first, so
    it does not.
    """
    match = profile.resolve_paragraph_style(
        "Heading411", style_name="Heading 411", based_on_chain=("Heading1", "Normal")
    )
    assert match is not None
    assert match.unit is StructuralUnit.TAG
    assert match.match_source is StyleMatchSource.VERBATIM_ALIAS
    assert match.rule_id == "verbatim-deduplicated:Heading411->Heading4"


def test_a_style_nobody_recognises_falls_back_to_its_based_on_ancestor(
    profile: StyleProfile,
) -> None:
    """`HeadingFake` inherits from `Heading3` in 32 surveyed files and means what it inherits."""
    match = profile.resolve_paragraph_style(
        "HeadingFake", style_name="Heading Fake", based_on_chain=("Heading3", "Normal")
    )
    assert match is not None
    assert match.unit is StructuralUnit.BLOCK
    assert match.match_source is StyleMatchSource.VERBATIM_ALIAS
    assert match.rule_id == "verbatim-based-on:Heading3"


def test_the_nearest_recognised_ancestor_wins(profile: StyleProfile) -> None:
    match = profile.resolve_paragraph_style(
        "SomebodysOwnTag", based_on_chain=("AlsoTheirs", "Heading4", "Normal")
    )
    assert match is not None
    assert match.unit is StructuralUnit.TAG
    assert match.rule_id == "verbatim-based-on:Heading4"


def test_a_style_no_route_resolves_returns_none_so_the_heuristics_can_try(
    profile: StyleProfile,
) -> None:
    assert profile.resolve_paragraph_style("inqyif", based_on_chain=("s2",)) is None
    assert profile.resolve_paragraph_style(None) is None
    assert profile.resolve_character_style("", "") is None


# --------------------------------------------------------------------------------------------
# basedOn chains read from a document's own style table
# --------------------------------------------------------------------------------------------


def test_a_based_on_chain_is_walked_nearest_ancestor_first() -> None:
    table = {"MyTag": "Heading411", "Heading411": "Heading1", "Heading1": "Normal", "Normal": None}
    assert resolve_based_on_chain("MyTag", table) == ("Heading411", "Heading1", "Normal")


def test_a_chain_that_refers_to_a_style_the_file_no_longer_defines_simply_ends() -> None:
    """Three seasons of copying between documents leaves these behind; it is not a parse failure."""
    assert resolve_based_on_chain("MyTag", {"MyTag": "DeletedStyle"}) == ("DeletedStyle",)


def test_a_cycle_in_the_style_table_ends_the_chain_rather_than_hanging() -> None:
    table = {"A": "B", "B": "C", "C": "A"}
    assert resolve_based_on_chain("A", table) == ("B", "C")


def test_a_style_with_no_parent_has_an_empty_chain() -> None:
    assert resolve_based_on_chain("Normal", {"Normal": None}) == ()
    assert resolve_based_on_chain("Absent", {}) == ()


# --------------------------------------------------------------------------------------------
# ac2 — the CardMirror mapping covers everything the evaluation note lists
# --------------------------------------------------------------------------------------------

_IDENTIFIER = re.compile(r"`([a-z][a-z0-9_]*)(?:\([a-zA-Z]+\))?`")


def _first_column_identifiers(section_heading: str) -> set[str]:
    """Every backticked identifier in the first column of the table under `section_heading`."""
    text = CARDMIRROR_EVALUATION.read_text(encoding="utf-8")
    start = text.index(section_heading)
    end = text.find("\n### ", start + 1)
    section = text[start : end if end != -1 else len(text)]
    identifiers: set[str] = set()
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        first_cell = line.split("|")[1]
        identifiers.update(_IDENTIFIER.findall(first_cell))
    return identifiers


def test_the_evaluation_note_still_has_the_tables_this_test_reads() -> None:
    """Guards the two tests below: an empty extraction would make them pass vacuously."""
    assert len(_first_column_identifiers("### Nodes")) >= 15
    assert len(_first_column_identifiers("### Marks")) >= 15


def test_every_cardmirror_node_in_the_evaluation_note_is_accounted_for(
    profile: StyleProfile,
) -> None:
    documented = _first_column_identifiers("### Nodes")
    recorded = {mapping.node for mapping in profile.cardmirror_nodes}
    assert documented - recorded == set(), "CardMirror nodes the profile does not mention"
    assert recorded - documented == set(), "profile mentions nodes the evaluation note does not"


def test_every_cardmirror_mark_in_the_evaluation_note_is_accounted_for(
    profile: StyleProfile,
) -> None:
    documented = _first_column_identifiers("### Marks")
    recorded = {mapping.mark for mapping in profile.cardmirror_marks}
    assert documented - recorded == set(), "CardMirror marks the profile does not mention"
    assert recorded - documented == set(), "profile mentions marks the evaluation note does not"


def test_every_structural_unit_has_a_cardmirror_node(profile: StyleProfile) -> None:
    for unit in StructuralUnit:
        assert profile.cardmirror_node_for(unit) is not None, f"{unit} has no CardMirror node"


def test_heading_is_the_only_emphasis_with_no_cardmirror_mark(profile: StyleProfile) -> None:
    unmapped = {emphasis for emphasis in RunEmphasis if not profile.cardmirror_marks_for(emphasis)}
    assert unmapped == {RunEmphasis.HEADING}
    heading_rule = next(rule for rule in profile.character_styles if rule.emphasis is RunEmphasis.HEADING)
    assert "no mark" in heading_rule.notes


def test_underline_maps_to_both_cardmirror_encodings(profile: StyleProfile) -> None:
    """The dual encoding ADR-0014 makes t02's responsibility to state."""
    assert set(profile.cardmirror_marks_for(RunEmphasis.UNDERLINE)) == {
        "underline_mark",
        "underline_direct",
    }
    rule = profile.underline_encoding
    assert rule.both_encodings_on_body_runs is True
    assert StructuralUnit.EVIDENCE in rule.named_style_slots
    assert StructuralUnit.TAG in rule.direct_slots
    assert set(rule.named_style_slots).isdisjoint(rule.direct_slots)


def test_a_cardmirror_type_with_no_counterpart_has_to_say_why(profile: StyleProfile) -> None:
    for mapping in profile.cardmirror_nodes:
        if mapping.unit is None:
            assert mapping.notes, f"node {mapping.node} maps to nothing and explains nothing"
    for mark_mapping in profile.cardmirror_marks:
        if mark_mapping.emphasis is None:
            assert mark_mapping.notes, f"mark {mark_mapping.mark} maps to nothing and explains nothing"


# --------------------------------------------------------------------------------------------
# Direct formatting, heuristics and writer definitions
# --------------------------------------------------------------------------------------------


def test_the_highlight_colours_the_survey_measured_are_recorded(profile: StyleProfile) -> None:
    for value in ("cyan", "green", "yellow", "magenta", "lightGray", "white"):
        assert profile.highlight_color(value) is not None, value
    assert {color.value for color in profile.highlight_colors if color.reading_color} == {
        "cyan",
        "green",
        "yellow",
    }
    assert profile.highlight_color("chartreuse") is None


def test_shrunk_text_is_small_and_not_underlined(profile: StyleProfile) -> None:
    assert profile.is_shrunk(16, underlined=False) is True
    assert profile.is_shrunk(14, underlined=False) is True
    assert profile.is_shrunk(22, underlined=False) is False
    assert profile.is_shrunk(16, underlined=True) is False
    assert profile.is_shrunk(None, underlined=False) is False


def test_every_heuristic_threshold_names_a_heading_unit(profile: StyleProfile) -> None:
    assert [threshold.unit for threshold in profile.heuristics] == [
        StructuralUnit.POCKET,
        StructuralUnit.HAT,
        StructuralUnit.BLOCK,
        StructuralUnit.TAG,
    ]
    assert [threshold.outline_level for threshold in profile.heuristics] == [0, 1, 2, 3]
    assert all(threshold.requires_bold for threshold in profile.heuristics)


def test_the_writer_definitions_match_what_the_survey_measured(profile: StyleProfile) -> None:
    pocket = profile.writer_style_definition("Heading1")
    assert pocket is not None
    assert (pocket.half_points, pocket.bold, pocket.outline_level) == (52, True, 0)
    assert pocket.page_break_before is True

    hat = profile.writer_style_definition("Heading2")
    assert hat is not None
    assert hat.underline == "double", "measured in 370 of 400 files; single would look wrong"

    tag = profile.writer_style_definition("Heading4")
    assert tag is not None
    assert tag.page_break_before is False, "a tag belongs on the same page as its card"

    analytic = profile.writer_style_definition("Analytic")
    assert analytic is not None
    assert analytic.color == "1F3864"
    assert analytic.based_on == "Heading4"

    assert profile.writer_style_definition("NotAStyle") is None


def test_every_style_the_profile_recognises_canonically_has_a_writer_definition(
    profile: StyleProfile,
) -> None:
    """A reader that knows a style but cannot write it back is half a profile."""
    written = {normalize_style_key(d.style_id) for d in profile.writer_style_definitions}
    structural = {
        normalize_style_key(rule.style_id)
        for rule in profile.paragraph_styles
        if rule.unit not in (StructuralUnit.OTHER, StructuralUnit.CITE, StructuralUnit.EVIDENCE)
    }
    assert structural <= written
    assert {normalize_style_key("StyleUnderline"), normalize_style_key("Style13ptBold")} <= written


def test_the_cite_patterns_match_the_short_cites_debaters_write(profile: StyleProfile) -> None:
    short = re.compile(profile.cite.short_cite_pattern)
    for line in ("Smith 26", "Smith '26", "Smith, 2026", "Smith et al. 26", "Smith and Jones 26"):
        match = short.match(line)
        assert match is not None, line
        assert match.group("author").startswith("Smith")
    assert short.match("the evidence says") is None


# --------------------------------------------------------------------------------------------
# A malformed profile is refused
# --------------------------------------------------------------------------------------------


def _profile_document() -> dict[str, Any]:
    """The committed YAML as a plain mapping, for tests that damage a copy of it on purpose."""
    document: dict[str, Any] = yaml.safe_load(PROFILE_YAML.read_text(encoding="utf-8"))
    return document


def test_the_committed_yaml_is_what_the_loader_returns(profile: StyleProfile) -> None:
    assert StyleProfile.model_validate(_profile_document()) == profile


def test_two_rules_claiming_the_same_style_key_are_refused() -> None:
    document = _profile_document()
    styles: list[dict[str, Any]] = document["paragraph_styles"]
    styles[0]["aliases"] = [*styles[0]["aliases"], "Heading4"]
    with pytest.raises(StyleProfileError, match="resolves to two rules"):
        load_style_profile_from_text(yaml.safe_dump(document))


def test_shrunk_text_that_is_not_smaller_than_body_text_is_refused() -> None:
    document = _profile_document()
    shrink: dict[str, Any] = document["shrink"]
    shrink["maximum_half_points"] = shrink["body_half_points"]
    with pytest.raises(StyleProfileError, match="must be smaller than body text"):
        load_style_profile_from_text(yaml.safe_dump(document))


def test_a_cardmirror_node_with_no_unit_and_no_explanation_is_refused() -> None:
    document = _profile_document()
    nodes: list[dict[str, Any]] = document["cardmirror_nodes"]
    nodes[0]["notes"] = ""
    with pytest.raises(StyleProfileError, match="maps to no unit and says no why"):
        load_style_profile_from_text(yaml.safe_dump(document))


def test_a_unit_with_a_style_but_no_cardmirror_node_is_refused() -> None:
    document = _profile_document()
    nodes: list[dict[str, Any]] = document["cardmirror_nodes"]
    for node in nodes:
        if node.get("unit") == "UNDERTAG":
            node["unit"] = None
            node["notes"] = "removed by a test"
    with pytest.raises(StyleProfileError, match="must record a CardMirror node; missing: UNDERTAG"):
        load_style_profile_from_text(yaml.safe_dump(document))


def test_a_writer_definition_with_a_bad_colour_is_refused() -> None:
    document = _profile_document()
    definitions: list[dict[str, Any]] = document["writer_style_definitions"]
    definitions[0]["color"] = "not-a-colour"
    with pytest.raises(StyleProfileError, match="six hex digits"):
        load_style_profile_from_text(yaml.safe_dump(document))


def test_a_writer_definition_with_an_unknown_style_type_is_refused() -> None:
    document = _profile_document()
    definitions: list[dict[str, Any]] = document["writer_style_definitions"]
    definitions[0]["style_type"] = "table"
    with pytest.raises(StyleProfileError, match="must be 'paragraph' or 'character'"):
        load_style_profile_from_text(yaml.safe_dump(document))


def test_the_profile_is_frozen_like_every_other_domain_model(profile: StyleProfile) -> None:
    from pydantic import ValidationError

    attribute = "profile_version"
    with pytest.raises(ValidationError):
        setattr(profile, attribute, "tampered")


# --------------------------------------------------------------------------------------------
# Import boundaries
# --------------------------------------------------------------------------------------------
#
# `uv run lint-imports` is the repo-wide version of this and arrives with
# v1-e02-t06-import-boundary-guard. Until it does, these two tests hold the same line for the
# modules this task adds.

FORBIDDEN_IN_THE_DOMAIN = ("docx", "lxml", "yaml", "boto3", "botocore", "httpx", "typer", "fastapi")
FORBIDDEN_IN_STYLE_CLASSIFICATION = ("model_router", "ModelRouter", "bedrock", "anthropic", "openai")


def test_the_style_profile_model_imports_no_io_library() -> None:
    """`debate_core.domain` holds data and invariants; reading the YAML is the loader's job."""
    import inspect

    from debate_core.domain import style_profile

    for line in inspect.getsource(style_profile).splitlines():
        if not line.startswith(("import ", "from ")) or line.startswith("from __future__"):
            continue
        assert not any(forbidden in line for forbidden in FORBIDDEN_IN_THE_DOMAIN), line


def test_style_classification_reaches_no_model() -> None:
    """The spec forbids a model call anywhere in style classification. Nothing here can make one."""
    import inspect

    from debate_core.evidence import style_classifier

    source = inspect.getsource(style_classifier)
    for forbidden in FORBIDDEN_IN_STYLE_CLASSIFICATION:
        assert forbidden not in source, forbidden


# --------------------------------------------------------------------------------------------
# Character styles take the same five routes as paragraph styles
# --------------------------------------------------------------------------------------------


def test_a_character_style_resolves_through_its_display_name(profile: StyleProfile) -> None:
    match = profile.resolve_character_style("cs7", style_name="Style Underline")
    assert match is not None
    assert match.emphasis is RunEmphasis.UNDERLINE
    assert match.rule_id == "verbatim-alias-name:Style Underline"


def test_a_deduplicated_character_style_resolves(profile: StyleProfile) -> None:
    """`Emphasis1` inherits from `Heading1` in 10 surveyed files and is still an Emphasis."""
    match = profile.resolve_character_style("Emphasis1", based_on_chain=("Heading1",))
    assert match is not None
    assert match.emphasis is RunEmphasis.EMPHASIS
    assert match.rule_id == "verbatim-deduplicated:Emphasis1->Emphasis"


def test_a_character_style_falls_back_to_its_based_on_ancestor(profile: StyleProfile) -> None:
    """`Rehighlighting` inherits from `Emphasis` in 9 surveyed files."""
    match = profile.resolve_character_style("Rehighlighting", based_on_chain=("Emphasis",))
    assert match is not None
    assert match.emphasis is RunEmphasis.EMPHASIS
    assert match.rule_id == "verbatim-based-on:Emphasis"


def test_an_unrecognised_character_style_returns_none(profile: StyleProfile) -> None:
    assert profile.resolve_character_style("inqyif", based_on_chain=("s2",)) is None


def test_a_cardmirror_mark_with_no_emphasis_and_no_explanation_is_refused() -> None:
    document = _profile_document()
    marks: list[dict[str, Any]] = document["cardmirror_marks"]
    for mark in marks:
        if mark.get("emphasis") is None:
            mark["notes"] = ""
    with pytest.raises(StyleProfileError, match="maps to no emphasis and says no why"):
        load_style_profile_from_text(yaml.safe_dump(document))
