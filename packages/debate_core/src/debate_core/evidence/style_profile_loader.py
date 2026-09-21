"""Read a :class:`~debate_core.domain.style_profile.StyleProfile` from its YAML data file.

The profiles ship inside the package, under `style_profiles/`, and are read through
:mod:`importlib.resources` so they are found the same way from a source checkout, an installed
wheel and a zipped deployment. Loading is cached: the profile is immutable, every parse of every
file consults it, and re-reading a 500-line YAML per document would be a silly thing to pay for.

This module also holds the `basedOn` resolution the profile's lookup needs but cannot do itself:
turning the `styleId -> basedOn` map read out of a document's `word/styles.xml` into the ancestor
chain :meth:`StyleProfile.resolve_paragraph_style` takes. That lives here rather than in the
domain because it is about a document's own style table, not about the profile.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from importlib import resources
from typing import Final

import yaml
from pydantic import ValidationError

from debate_core.domain.style_profile import StyleProfile

__all__ = [
    "DEFAULT_STYLE_PROFILE_NAME",
    "MAXIMUM_BASED_ON_DEPTH",
    "STYLE_PROFILE_PACKAGE",
    "StyleProfileError",
    "available_style_profiles",
    "load_style_profile",
    "load_style_profile_from_text",
    "resolve_based_on_chain",
]

STYLE_PROFILE_PACKAGE: Final = "debate_core.evidence.style_profiles"
DEFAULT_STYLE_PROFILE_NAME: Final = "verbatim"

#: A `basedOn` chain longer than this is a cycle or a corrupt style table, not a style hierarchy.
#: Word's own nesting rarely exceeds four.
MAXIMUM_BASED_ON_DEPTH: Final = 32


class StyleProfileError(RuntimeError):
    """A style profile is missing, unreadable, or does not match the model."""


def available_style_profiles() -> tuple[str, ...]:
    """The names of the profiles that ship with this package, sorted."""
    directory = resources.files(STYLE_PROFILE_PACKAGE)
    return tuple(
        sorted(
            entry.name.removesuffix(".yaml") for entry in directory.iterdir() if entry.name.endswith(".yaml")
        )
    )


def load_style_profile_from_text(text: str, *, source: str = "<string>") -> StyleProfile:
    """Parse and validate one profile from YAML text.

    Separate from :func:`load_style_profile` so a test — or a future task that wants to try a
    profile before shipping it — can validate a candidate without installing it in the package.
    """
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise StyleProfileError(f"style profile {source} is not valid YAML: {error}") from error
    if not isinstance(document, dict):
        raise StyleProfileError(f"style profile {source} must be a mapping at the top level")
    try:
        return StyleProfile.model_validate(document)
    except ValidationError as error:
        raise StyleProfileError(f"style profile {source} does not match the model:\n{error}") from error


@lru_cache(maxsize=8)
def load_style_profile(name: str = DEFAULT_STYLE_PROFILE_NAME) -> StyleProfile:
    """Load the named profile, e.g. `verbatim`. Cached: profiles are immutable."""
    try:
        text = resources.files(STYLE_PROFILE_PACKAGE).joinpath(f"{name}.yaml").read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError) as error:
        available = ", ".join(available_style_profiles()) or "none"
        raise StyleProfileError(
            f"no style profile named {name!r}; available profiles: {available}"
        ) from error
    return load_style_profile_from_text(text, source=f"{name}.yaml")


def resolve_based_on_chain(style_id: str, based_on_by_style_id: Mapping[str, str | None]) -> tuple[str, ...]:
    """Return `style_id`'s ancestors, nearest first, from a document's own style table.

    `based_on_by_style_id` is what a reader builds from `word/styles.xml`: every `w:styleId`
    mapped to its `w:basedOn`, or to None where it has none. A missing ancestor ends the chain
    rather than raising — a debate file that has been copied between documents for three seasons
    routinely refers to styles it no longer defines, and that is not a reason to refuse to parse
    it. A cycle ends the chain too, at the first repeat.
    """
    chain: list[str] = []
    seen = {style_id}
    current = based_on_by_style_id.get(style_id)
    while current and current not in seen and len(chain) < MAXIMUM_BASED_ON_DEPTH:
        chain.append(current)
        seen.add(current)
        current = based_on_by_style_id.get(current)
    return tuple(chain)
