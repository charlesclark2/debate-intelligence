"""Card format profiles: how a cut card is sized and coloured, on top of the shared style profile.

A cut card is rendered (`v1-e06-t04`) in Verbatim's styles, and every one of those belongs to the
shared style profile (`v1-e31-t02`, :class:`~debate_core.domain.style_profile.StyleProfile`):
the pocket, hat, block and tag headings, the cite style, underline, emphasis and the highlight
vocabulary. A :class:`FormatProfile` names that profile and adds only the choices a team makes
when it cuts a card, the ones the style profile leaves open:

* the cite block: whether the short cite carries the cite style (which is what makes it bold),
  and the size of the full cite after it;
* the evidence base size: the size of the underlined text that is read;
* the highlight colour, or none;
* the condensed-text size: the size of the text that is not underlined, or none to leave it at
  the base size.

`team-default`, `flow` and `plain` are the profiles that ship, in `config/format_profiles/`; each
value in `team-default` cites the line of `docs/data/team-format-survey.md` it comes from.

A profile never redefines a style. A key the style profile owns (`paragraph_styles`, `cite`,
`shrink`, ...) or any key naming a style (`tag_style`, `underline_style`, ...) is refused with a
message saying who owns it; any other unknown key is refused as well. And a profile's sizes and
colour must agree with the style profile's reading of a file, so the parser reads a rendered card
back the way it was meant: a condensed size is one the style profile calls shrunk, the base size
is one it does not, and the highlight colour is one it records as a reading colour.

Nothing here touches the network. The profiles are read from `config/` like the other committed
configuration (:data:`FORMAT_PROFILES_DIRECTORY`, relative to the repository root and to an
installed build's bundled `config/`).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import yaml
from pydantic import Field, ValidationError, model_validator

from debate_core.domain.base import DomainModel, NonEmptyText
from debate_core.domain.style_profile import RunEmphasis, StructuralUnit, StyleProfile
from debate_core.evidence.style_profile_loader import StyleProfileError, load_style_profile

__all__ = [
    "FORMAT_PROFILES_DIRECTORY",
    "CiteBlockLayout",
    "FormatProfile",
    "FormatProfileError",
    "ResolvedFormatProfile",
    "load_format_profile",
    "load_format_profile_from_text",
    "load_format_profiles",
    "resolve_format_profile",
]

FORMAT_PROFILES_DIRECTORY: Final = Path("config/format_profiles")
"""The committed profiles, relative to the repository root."""


class FormatProfileError(RuntimeError):
    """A format profile is missing, unreadable, invalid, or disagrees with its style profile."""


def _style_profile_keys() -> frozenset[str]:
    return frozenset(StyleProfile.model_fields) - {"name", "description"}


def _names_a_style(key: str) -> bool:
    return key.endswith(("_style", "_styles", "_style_id", "_style_name"))


def _owned_keys(document: Mapping[str, Any], path: str = "") -> list[str]:
    """Every key in `document`, at any depth, that the style profile owns or that names a style."""
    owned: list[str] = []
    for key, value in document.items():
        dotted = f"{path}{key}"
        if isinstance(key, str) and (key in _style_profile_keys() or _names_a_style(key)):
            owned.append(dotted)
        if isinstance(value, Mapping):
            owned.extend(_owned_keys(value, f"{dotted}."))
    return owned


class CiteBlockLayout(DomainModel):
    """How the cite paragraph is laid out: the short cite, then the full cite."""

    short_cite_bold: bool = Field(
        description=(
            "Whether the short cite carries the style profile's cite character style, which is what "
            "makes it bold. False leaves it at the full cite's formatting."
        )
    )
    full_cite_half_points: int = Field(gt=0, description="The `w:sz` of the full cite after the short cite.")


class FormatProfile(DomainModel):
    """One card format profile, as `config/format_profiles/<name>.yaml` writes it."""

    name: NonEmptyText = Field(description="The profile's name, e.g. `team-default`; its file is `<name>.yaml`.")
    description: NonEmptyText = Field(description="What the profile is for, for a reader choosing one.")
    base_style_profile: NonEmptyText = Field(
        description="The shared style profile (`v1-e31-t02`) every heading, cite and run style comes from."
    )
    cite_block: CiteBlockLayout = Field(description="The cite paragraph's layout.")
    evidence_base_half_points: int = Field(gt=0, description="The `w:sz` of underlined, read evidence.")
    highlight_color: str | None = Field(
        description="The `w:highlight` token for highlighted evidence, or None for no highlighting."
    )
    condensed_half_points: int | None = Field(
        gt=0,
        description="The `w:sz` of evidence that is not underlined, or None to leave it at the base size.",
    )

    @model_validator(mode="before")
    @classmethod
    def _refuse_style_definitions(cls, data: Any) -> Any:
        if isinstance(data, Mapping):
            owned = _owned_keys(data)
            if owned:
                raise ValueError(
                    f"a format profile never defines a style: {', '.join(owned)} belongs to the base style "
                    f"profile ({data.get('base_style_profile', 'its base style profile')}), which owns every "
                    "heading, cite, underline, emphasis and highlight style"
                )
        return data


@dataclass(frozen=True)
class ResolvedFormatProfile:
    """A format profile with its base style profile loaded and checked against it.

    The renderer takes this, not a bare :class:`FormatProfile`: every style it names comes from
    :attr:`style_profile`, and every size and colour from :attr:`profile`.
    """

    profile: FormatProfile
    style_profile: StyleProfile

    @property
    def name(self) -> str:
        return self.profile.name

    def paragraph_style_id(self, unit: StructuralUnit) -> str:
        """The base profile's paragraph style for `unit`: `Heading4` for a tag."""
        for rule in self.style_profile.paragraph_styles:
            if rule.unit is unit:
                return rule.style_id
        raise FormatProfileError(f"style profile {self.style_profile.name} has no paragraph style for {unit.value}")

    def character_style_id(self, emphasis: RunEmphasis) -> str:
        """The base profile's character style for `emphasis`: `Style13ptBold` for a cite."""
        for rule in self.style_profile.character_styles:
            if rule.emphasis is emphasis:
                return rule.style_id
        raise FormatProfileError(
            f"style profile {self.style_profile.name} has no character style for {emphasis.value}"
        )


def resolve_format_profile(
    profile: FormatProfile, *, style_profiles: Callable[[str], StyleProfile] = load_style_profile
) -> ResolvedFormatProfile:
    """Load `profile`'s base style profile and check the profile's values against it."""
    try:
        style_profile = style_profiles(profile.base_style_profile)
    except StyleProfileError as error:
        raise FormatProfileError(
            f"format profile {profile.name} names base style profile {profile.base_style_profile!r}, "
            f"which does not load: {error}"
        ) from error
    shrink_maximum = style_profile.shrink.maximum_half_points
    problems: list[str] = []
    if profile.evidence_base_half_points <= shrink_maximum:
        problems.append(
            f"evidence_base_half_points {profile.evidence_base_half_points} is text the style profile "
            f"reads as shrunk (at or below {shrink_maximum})"
        )
    if profile.condensed_half_points is not None and profile.condensed_half_points > shrink_maximum:
        problems.append(
            f"condensed_half_points {profile.condensed_half_points} is text the style profile does not "
            f"read as shrunk (above {shrink_maximum})"
        )
    if profile.highlight_color is not None:
        color = style_profile.highlight_color(profile.highlight_color)
        if color is None or not color.reading_color:
            reading = ", ".join(c.value for c in style_profile.highlight_colors if c.reading_color)
            problems.append(
                f"highlight_color {profile.highlight_color!r} is not a reading colour in style profile "
                f"{style_profile.name} ({reading})"
            )
    if problems:
        raise FormatProfileError(f"format profile {profile.name} disagrees with its style profile: " + "; ".join(problems))
    return ResolvedFormatProfile(profile=profile, style_profile=style_profile)


def load_format_profile_from_text(text: str, *, source: str = "<string>") -> FormatProfile:
    """Parse and validate one profile from YAML text, without resolving its base."""
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise FormatProfileError(f"format profile {source} is not valid YAML: {error}") from error
    if not isinstance(document, dict):
        raise FormatProfileError(f"format profile {source} must be a mapping at the top level")
    try:
        return FormatProfile.model_validate(document)
    except ValidationError as error:
        raise FormatProfileError(f"format profile {source} does not match the model:\n{error}") from error


def load_format_profiles(
    directory: Path, *, style_profiles: Callable[[str], StyleProfile] = load_style_profile
) -> dict[str, ResolvedFormatProfile]:
    """Every `<name>.yaml` in `directory`, validated and resolved, by name."""
    if not directory.is_dir():
        raise FormatProfileError(f"format profile directory not found: {directory}")
    profiles: dict[str, ResolvedFormatProfile] = {}
    for path in sorted(directory.glob("*.yaml")):
        profile = load_format_profile_from_text(path.read_text(encoding="utf-8"), source=path.name)
        if profile.name != path.stem:
            raise FormatProfileError(f"format profile {path.name} is named {profile.name!r}; the file must be {profile.name}.yaml")
        profiles[profile.name] = resolve_format_profile(profile, style_profiles=style_profiles)
    return profiles


def load_format_profile(
    name: str,
    directory: Path,
    *,
    style_profiles: Callable[[str], StyleProfile] = load_style_profile,
) -> ResolvedFormatProfile:
    """The profile called `name` in `directory`, resolved; an unknown name lists the ones there are."""
    profiles = load_format_profiles(directory, style_profiles=style_profiles)
    if name not in profiles:
        raise FormatProfileError(
            f"no format profile named {name!r}; available profiles: {', '.join(profiles) or 'none'}"
        )
    return profiles[name]
