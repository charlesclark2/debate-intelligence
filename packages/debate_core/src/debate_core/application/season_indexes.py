"""The backfile seasons' indexes on the function: one held at a time, each fetched when it is chosen.

SKELETON for the red run (v1-e39-t18): the keys and words are real; the shelf serves no season.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Generator, Sequence
from contextlib import contextmanager
from typing import Final

from debate_core.application.errors import DomainError
from debate_core.application.search_index_holder import (
    ScreenedSearch,
    SearchIndexHolder,
    SearchIndexUnavailable,
)
from debate_core.domain.search_index import SEARCH_INDEX_PREFIX

__all__ = [
    "SEASON_POINTER_PREFIX",
    "SEASON_POINTER_SUFFIX",
    "SeasonIndexes",
    "UnknownSeason",
    "is_season",
    "season_label",
    "season_of_pointer_key",
    "season_pointer_key",
    "season_words",
]

SEASON_POINTER_PREFIX: Final = f"{SEARCH_INDEX_PREFIX}seasons/"
SEASON_POINTER_SUFFIX: Final = ".json"
_SEASON: Final = re.compile(r"^[a-z]+(?P<year>[0-9]{2})$")


def is_season(slug: str) -> bool:
    return _SEASON.match(slug) is not None


def _checked(slug: str) -> str:
    if not is_season(slug):
        raise ValueError(f"a season is a caselist slug ending in its two-digit year; got {slug!r}")
    return slug


def season_pointer_key(season: str) -> str:
    return f"{SEASON_POINTER_PREFIX}{_checked(season)}{SEASON_POINTER_SUFFIX}"


def season_of_pointer_key(key: str) -> str | None:
    if not key.startswith(SEASON_POINTER_PREFIX) or not key.endswith(SEASON_POINTER_SUFFIX):
        return None
    slug = key.removeprefix(SEASON_POINTER_PREFIX).removesuffix(SEASON_POINTER_SUFFIX)
    return slug if is_season(slug) else None


def season_words(season: str) -> str:
    match = _SEASON.match(_checked(season))
    assert match is not None
    start = 2000 + int(match["year"])
    return f"{start}-{(start + 1) % 100:02d}"


def season_label(season: str) -> str:
    return f"{season} ({season_words(season)})"


class UnknownSeason(DomainError):
    def __init__(self, season: str) -> None:
        self.season = season
        super().__init__(f"{season} is not a season this pilot offers")


class SeasonIndexes:
    def __init__(self, seasons: Sequence[str], holder_for: Callable[[str], SearchIndexHolder]) -> None:
        self._offered = tuple(seasons)
        self._holder_for = holder_for

    @classmethod
    def none(cls) -> SeasonIndexes:
        def no_holder(season: str) -> SearchIndexHolder:
            raise UnknownSeason(season)

        return cls((), no_holder)

    @property
    def offered(self) -> tuple[str, ...]:
        return self._offered

    def holds(self, caselist: str) -> bool:
        return False

    def is_loaded(self, season: str) -> bool:
        return False

    @property
    def held(self) -> str | None:
        return None

    @contextmanager
    def lease(self, season: str) -> Generator[ScreenedSearch]:
        raise SearchIndexUnavailable()
        yield  # pragma: no cover

    def close(self) -> None:
        return None
