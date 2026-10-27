"""Tests for `debate_core.evidence.format_profile`, the card format profiles.

A format profile names the shared style profile and adds only sizes and a colour. These tests hold
it to that: it may not define a style, its base must load, and its values must read back the way
the style profile reads a file (condensed text shrunk, read text not, the colour a reading
colour). The expected style ids are the verbatim profile's, written here by hand.

The committed profiles are checked too, and `team-default`'s values against the lines of
`docs/data/team-format-survey.md` they cite.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from debate_core.domain.card import DEFAULT_FORMAT_PROFILE
from debate_core.domain.style_profile import RunEmphasis, StructuralUnit
from debate_core.evidence.format_profile import (
    FORMAT_PROFILES_DIRECTORY,
    FormatProfileError,
    ResolvedFormatProfile,
    load_format_profile,
    load_format_profile_from_text,
    load_format_profiles,
    resolve_format_profile,
)

REPOSITORY = Path(__file__).resolve().parents[4]
COMMITTED_PROFILES = REPOSITORY / FORMAT_PROFILES_DIRECTORY
SURVEY = REPOSITORY / "docs" / "data" / "team-format-survey.md"

VALID: dict[str, Any] = {
    "name": "candidate",
    "description": "A profile for these tests.",
    "base_style_profile": "verbatim",
    "cite_block": {"short_cite_bold": True, "full_cite_half_points": 16},
    "evidence_base_half_points": 22,
    "highlight_color": "cyan",
    "condensed_half_points": 16,
}


def profile_text(**changes: Any) -> str:
    document = {**VALID, **changes}
    return yaml.safe_dump(document, sort_keys=False)


def resolve(**changes: Any) -> ResolvedFormatProfile:
    return resolve_format_profile(load_format_profile_from_text(profile_text(**changes)))


def write_profiles(directory: Path, **profiles: dict[str, Any]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for file_stem, changes in profiles.items():
        (directory / f"{file_stem}.yaml").write_text(profile_text(**changes), encoding="utf-8")
    return directory


# --------------------------------------------------------------------------------------------
# A valid profile, and what it resolves to
# --------------------------------------------------------------------------------------------


def test_a_valid_profile_resolves_against_its_base_style_profile() -> None:
    resolved = resolve()

    assert resolved.name == "candidate"
    assert resolved.style_profile.name == "verbatim"
    assert resolved.profile.cite_block.short_cite_bold is True
    assert resolved.profile.cite_block.full_cite_half_points == 16
    assert resolved.profile.evidence_base_half_points == 22
    assert resolved.profile.highlight_color == "cyan"
    assert resolved.profile.condensed_half_points == 16


@pytest.mark.parametrize(
    ("unit", "style_id"),
    [
        (StructuralUnit.POCKET, "Heading1"),
        (StructuralUnit.HAT, "Heading2"),
        (StructuralUnit.BLOCK, "Heading3"),
        (StructuralUnit.TAG, "Heading4"),
    ],
)
def test_headings_come_from_the_base_style_profile(unit: StructuralUnit, style_id: str) -> None:
    assert resolve().paragraph_style_id(unit) == style_id


@pytest.mark.parametrize(
    ("emphasis", "style_id"),
    [
        (RunEmphasis.CITE, "Style13ptBold"),
        (RunEmphasis.UNDERLINE, "StyleUnderline"),
        (RunEmphasis.EMPHASIS, "Emphasis"),
    ],
)
def test_cite_underline_and_emphasis_come_from_the_base_style_profile(emphasis: RunEmphasis, style_id: str) -> None:
    assert resolve().character_style_id(emphasis) == style_id


def test_a_unit_the_base_has_no_style_for_is_an_error_not_a_guess() -> None:
    resolved = resolve()
    stripped = resolved.style_profile.model_copy(
        update={
            "paragraph_styles": tuple(
                rule for rule in resolved.style_profile.paragraph_styles if rule.unit is not StructuralUnit.HAT
            )
        }
    )
    without_hat = type(resolved)(profile=resolved.profile, style_profile=stripped)

    with pytest.raises(FormatProfileError, match="no paragraph style for HAT"):
        without_hat.paragraph_style_id(StructuralUnit.HAT)


def test_no_highlighting_and_no_condensing_are_choices_a_profile_can_make() -> None:
    resolved = resolve(highlight_color=None, condensed_half_points=None)

    assert resolved.profile.highlight_color is None
    assert resolved.profile.condensed_half_points is None


# --------------------------------------------------------------------------------------------
# A profile never defines a style
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("changes", "owned_key"),
    [
        ({"paragraph_styles": [{"unit": "TAG", "style_id": "MyTag", "style_name": "My Tag"}]}, "paragraph_styles"),
        ({"character_styles": []}, "character_styles"),
        ({"highlight_colors": [{"value": "magenta", "reading_color": True}]}, "highlight_colors"),
        ({"cite": {"short_cite_pattern": ".*"}}, "cite"),
        ({"shrink": {"maximum_half_points": 18}}, "shrink"),
        ({"underline_encoding": {}}, "underline_encoding"),
        ({"writer_style_definitions": []}, "writer_style_definitions"),
        ({"tag_style": "Heading4"}, "tag_style"),
        ({"underline_style": "StyleUnderline"}, "underline_style"),
        (
            {"cite_block": {"short_cite_bold": True, "full_cite_half_points": 16, "short_cite_style_id": "Cite"}},
            "cite_block.short_cite_style_id",
        ),
    ],
)
def test_a_profile_that_defines_a_style_is_refused_and_told_who_owns_it(
    changes: dict[str, Any], owned_key: str
) -> None:
    with pytest.raises(FormatProfileError, match="never defines a style") as refused:
        load_format_profile_from_text(profile_text(**changes))

    assert owned_key in str(refused.value)
    assert "verbatim" in str(refused.value)


def test_any_other_unknown_key_is_refused_too() -> None:
    with pytest.raises(FormatProfileError, match="does not match the model"):
        load_format_profile_from_text(profile_text(font_colour="1F3864"))


# --------------------------------------------------------------------------------------------
# Its base must load, and its values must agree with the base
# --------------------------------------------------------------------------------------------


def test_an_unknown_base_style_profile_is_refused() -> None:
    with pytest.raises(FormatProfileError, match="'cardmirror-2027', which does not load"):
        resolve(base_style_profile="cardmirror-2027")


@pytest.mark.parametrize("color", ["magenta", "lightGray", "teal"])
def test_a_highlight_colour_the_base_does_not_read_as_reading_is_refused(color: str) -> None:
    with pytest.raises(FormatProfileError, match=f"highlight_color '{color}' is not a reading colour"):
        resolve(highlight_color=color)


@pytest.mark.parametrize("color", ["cyan", "green", "yellow"])
def test_every_reading_colour_is_accepted(color: str) -> None:
    assert resolve(highlight_color=color).profile.highlight_color == color


def test_condensed_text_the_base_would_not_read_as_shrunk_is_refused() -> None:
    with pytest.raises(FormatProfileError, match="condensed_half_points 18 is text the style profile does not"):
        resolve(condensed_half_points=18)


def test_condensed_text_exactly_at_the_shrink_maximum_is_accepted() -> None:
    assert resolve(condensed_half_points=16).profile.condensed_half_points == 16


def test_a_base_size_the_base_would_read_as_shrunk_is_refused() -> None:
    with pytest.raises(FormatProfileError, match="evidence_base_half_points 16 is text the style profile reads"):
        resolve(evidence_base_half_points=16, condensed_half_points=None)


def test_the_smallest_base_size_above_the_shrink_maximum_is_accepted() -> None:
    assert resolve(evidence_base_half_points=17).profile.evidence_base_half_points == 17


def test_every_disagreement_is_reported_at_once() -> None:
    with pytest.raises(FormatProfileError) as refused:
        resolve(evidence_base_half_points=14, condensed_half_points=12, highlight_color="red")

    assert "evidence_base_half_points 14" in str(refused.value)
    assert "highlight_color 'red'" in str(refused.value)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"evidence_base_half_points": 0}, "evidence_base_half_points"),
        ({"condensed_half_points": 0}, "condensed_half_points"),
        ({"cite_block": {"short_cite_bold": True, "full_cite_half_points": 0}}, "full_cite_half_points"),
        ({"cite_block": {"short_cite_bold": True}}, "full_cite_half_points"),
        ({"name": ""}, "name"),
    ],
)
def test_impossible_values_are_refused(changes: dict[str, Any], message: str) -> None:
    with pytest.raises(FormatProfileError, match=message):
        load_format_profile_from_text(profile_text(**changes))


def test_text_that_is_not_yaml_or_not_a_mapping_is_refused() -> None:
    with pytest.raises(FormatProfileError, match="not valid YAML"):
        load_format_profile_from_text("name: [unclosed")
    with pytest.raises(FormatProfileError, match="must be a mapping"):
        load_format_profile_from_text("- team-default")


# --------------------------------------------------------------------------------------------
# The registry
# --------------------------------------------------------------------------------------------


def test_the_registry_loads_every_profile_in_a_directory_by_name(tmp_path: Path) -> None:
    directory = write_profiles(tmp_path, alpha={"name": "alpha"}, beta={"name": "beta", "highlight_color": None})

    profiles = load_format_profiles(directory)

    assert sorted(profiles) == ["alpha", "beta"]
    assert profiles["beta"].profile.highlight_color is None
    assert load_format_profile("alpha", directory).name == "alpha"


def test_a_profile_whose_name_is_not_its_file_name_is_refused(tmp_path: Path) -> None:
    directory = write_profiles(tmp_path, alpha={"name": "beta"})

    with pytest.raises(FormatProfileError, match="alpha.yaml is named 'beta'"):
        load_format_profiles(directory)


def test_an_unknown_profile_name_lists_the_ones_there_are(tmp_path: Path) -> None:
    directory = write_profiles(tmp_path, alpha={"name": "alpha"}, beta={"name": "beta"})

    with pytest.raises(FormatProfileError, match="no format profile named 'gamma'; available profiles: alpha, beta"):
        load_format_profile("gamma", directory)


def test_one_bad_profile_fails_the_whole_directory(tmp_path: Path) -> None:
    directory = write_profiles(tmp_path, alpha={"name": "alpha"}, beta={"name": "beta", "base_style_profile": "nope"})

    with pytest.raises(FormatProfileError, match="beta"):
        load_format_profile("alpha", directory)


def test_a_missing_directory_is_reported(tmp_path: Path) -> None:
    with pytest.raises(FormatProfileError, match="directory not found"):
        load_format_profiles(tmp_path / "absent")


# --------------------------------------------------------------------------------------------
# The committed profiles
# --------------------------------------------------------------------------------------------


def test_the_committed_profiles_validate_and_resolve_against_the_shared_style_profile() -> None:
    profiles = load_format_profiles(COMMITTED_PROFILES)

    assert sorted(profiles) == ["flow", "plain", "team-default"]
    assert {resolved.style_profile.name for resolved in profiles.values()} == {"verbatim"}


def test_the_card_default_names_a_committed_profile() -> None:
    assert load_format_profile(DEFAULT_FORMAT_PROFILE, COMMITTED_PROFILES).name == "team-default"


def test_plain_has_no_highlighting() -> None:
    assert load_format_profile("plain", COMMITTED_PROFILES).profile.highlight_color is None


_VALUE_LINE = re.compile(r"^(?P<indent>\s*)(?P<key>[a-z_]+):\s*(?P<value>[^\s#][^#]*?)\s*$")
_CITED = re.compile(r'^\s*# team-format-survey\.md: "(?P<line>[^"]+)"\s*$')
_NOT_MEASURED = ("name", "description", "base_style_profile")


def _cited_values(text: str) -> list[tuple[str, str, str | None]]:
    """`(key, value, cited survey line or None)` for every scalar value in a profile's YAML."""
    lines = text.splitlines()
    found: list[tuple[str, str, str | None]] = []
    for index, line in enumerate(lines):
        match = _VALUE_LINE.match(line)
        if match is None or match["key"] in _NOT_MEASURED or match["value"].startswith(">"):
            continue
        previous = next((lines[i] for i in range(index - 1, -1, -1) if lines[i].strip()), "")
        cited = _CITED.match(previous)
        found.append((match["key"], match["value"], cited["line"] if cited else None))
    return found


def test_every_team_default_value_cites_the_survey_line_it_comes_from() -> None:
    survey = SURVEY.read_text(encoding="utf-8")
    values = _cited_values((COMMITTED_PROFILES / "team-default.yaml").read_text(encoding="utf-8"))

    assert {key for key, _, _ in values} == {
        "short_cite_bold",
        "full_cite_half_points",
        "evidence_base_half_points",
        "highlight_color",
        "condensed_half_points",
    }
    for key, value, cited in values:
        assert cited is not None, f"{key} has no `# team-format-survey.md: \"...\"` comment above it"
        assert cited in survey, f"{key} cites a line the survey does not have: {cited}"
        if value.isdigit():
            assert f"{value} half-points" in cited, f"{key}: {value} is not the size its survey line names"
        elif value not in ("true", "false", "null"):
            assert f"`{value}`" in cited, f"{key}: {value} is not the colour its survey line names"


def test_the_citation_check_notices_a_value_its_line_does_not_name() -> None:
    text = '# team-format-survey.md: "- Underlined evidence size: 22 half-points (11 pt)"\nevidence_base_half_points: 24\n'

    [(key, value, cited)] = _cited_values(text)

    assert (key, value) == ("evidence_base_half_points", "24")
    assert cited is not None and f"{value} half-points" not in cited
