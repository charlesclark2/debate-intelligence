"""The backfile seasons' indexes on the function: one held at a time, each fetched when it is chosen.

The PM's ruling of 2026-11-12 on `v1-e39-t18` (shape 4): each backfile season is an index of its own
store, published to its own pointer, and a student searches an earlier season by picking it. The
current seasons' index, its holder and its cold start are untouched: nothing here is reached by a
search that names no season (ADR-0019 (c) 7 holds for it as before).

## Where a season's index is

`tub index build --caselist <season>` builds it and `tub index publish --season <season>` publishes it:
its objects under `reports/tub/search/<index id>/`, as every index's are, and its pointer, written
last, at :func:`season_pointer_key`, `reports/tub/search/seasons/<season>.json`. So the function reads
it under the grant it already has, `s3:GetObject` under `reports/tub/search/`, and the prune
(`v1-e39-t15`) lists it with the rest and keeps what each season's pointer names. Each pointer has
its own shrink guard (:class:`~debate_core.application.search_index_publish.SearchIndexPublishService`
with a `season`).

## One held at a time

:class:`SeasonIndexes` builds a season's :class:`~debate_core.application.search_index_holder.
SearchIndexHolder` the first time a request picks that season, and keeps at most one: picking
another closes the held one, which deletes its file, before the next is built. Every season's holder
works in one directory, so building one also clears what an earlier process left there. So the
function's `/tmp` holds the current index, at a swap its replacement, and one season, which the
PM's ruling measured at 2.99 GB at most against 4,096 MB. A request holds the shelf's lock for its
whole lease, so a season is never closed while it is read; the function serves one request at a
time, and only season requests wait on each other.

## What a season's holder does

All of what the current index's does, from its own pointer: fetched and checked on first need,
rechecked at most five minutes apart, and every lease screened by the one suppression list, read
fresh in the same pass. So a removal hides a backfile card within five minutes, as it hides a
current one (gate item 1), and a season first loaded after a removal hides it at once.

## A season's words

A caselist slug's two digits are the year its season starts (`docs/data/caselist-backfile-seasons.md`:
"the API's `year` agrees for all 15"), so `hspolicy25` is the 2025-26 season and `hsld24` the
2024-25 one. :func:`season_words` gives `2025-26`, :func:`season_label` the slug with them,
`hspolicy25 (2025-26)`, which is what the search page and a card's page name the season by. The
provenance line itself is unchanged: a season in its words awaits the data-use policy's owner.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Callable, Generator, Sequence
from contextlib import contextmanager
from typing import Final

from debate_core.application.errors import DomainError
from debate_core.application.search_index_holder import ScreenedSearch, SearchIndexHolder
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
"""Where the season pointers live, beside `current.json`."""

SEASON_POINTER_SUFFIX: Final = ".json"

_SEASON: Final = re.compile(r"^[a-z]+(?P<year>[0-9]{2})$")
"""A caselist slug with its season's two digits: `hspolicy25`, `hsld24`."""


def is_season(slug: str) -> bool:
    """Whether `slug` is a caselist slug a season index can be named by: lower-case letters, two digits."""
    return _SEASON.match(slug) is not None


def _checked(slug: str) -> str:
    if not is_season(slug):
        raise ValueError(
            f"a season is a caselist slug ending in its two-digit year, such as hspolicy25; got {slug!r}"
        )
    return slug


def season_pointer_key(season: str) -> str:
    """`reports/tub/search/seasons/<season>.json`: the pointer `tub index publish --season` writes last."""
    return f"{SEASON_POINTER_PREFIX}{_checked(season)}{SEASON_POINTER_SUFFIX}"


def season_of_pointer_key(key: str) -> str | None:
    """The season `key` is the pointer of, or `None` for any other key."""
    if not key.startswith(SEASON_POINTER_PREFIX) or not key.endswith(SEASON_POINTER_SUFFIX):
        return None
    slug = key.removeprefix(SEASON_POINTER_PREFIX).removesuffix(SEASON_POINTER_SUFFIX)
    return slug if is_season(slug) else None


def season_words(season: str) -> str:
    """The season in words, `2025-26` for `hspolicy25`: the year it starts, then the next one's two digits."""
    match = _SEASON.match(_checked(season))
    if match is None:  # pragma: no cover - `_checked` refused it already
        raise ValueError(season)
    start = 2000 + int(match["year"])
    return f"{start}-{(start + 1) % 100:02d}"


def season_label(season: str) -> str:
    """What the search page calls a season: `hspolicy25 (2025-26)`."""
    return f"{season} ({season_words(season)})"


class UnknownSeason(DomainError):
    """A season this pilot does not offer was asked for. Nothing was built or closed."""

    def __init__(self, season: str) -> None:
        self.season = season
        super().__init__(f"{season} is not a season this pilot offers")


HolderFactory = Callable[[str], SearchIndexHolder]
"""Builds the holder of one season's index, reading that season's pointer."""


class SeasonIndexes:
    """The backfile seasons a pilot offers, and the one whose index it holds.

    Safe to share between threads: one lock covers choosing a season and the whole of its lease.
    """

    def __init__(self, seasons: Sequence[str], holder_for: HolderFactory) -> None:
        offered = tuple(seasons)
        if any(not is_season(one) for one in offered) or len(set(offered)) != len(offered):
            raise ValueError("the offered seasons are distinct caselist slugs ending in their two-digit year")
        self._offered = offered
        self._holder_for = holder_for
        self._lock = threading.Lock()
        self._held: tuple[str, SearchIndexHolder] | None = None

    @classmethod
    def none(cls) -> SeasonIndexes:
        """No season offered: every lease is refused, and nothing is ever built."""

        def no_holder(season: str) -> SearchIndexHolder:  # pragma: no cover - nothing is offered to build
            raise UnknownSeason(season)

        return cls((), no_holder)

    @property
    def offered(self) -> tuple[str, ...]:
        """The seasons a student may pick, in the order the search page lists them."""
        return self._offered

    def holds(self, caselist: str) -> bool:
        """Whether `caselist` is an offered season, whose cards are looked up in its own index."""
        return caselist in self._offered

    @property
    def held(self) -> str | None:
        """The season whose holder is kept, loaded or not; `None` before one is picked. Never waits."""
        held = self._held
        return held[0] if held is not None else None

    def is_loaded(self, season: str) -> bool:
        """Whether `season`'s index is loaded now, so its next search waits for no fetch. Never waits."""
        held = self._held
        return held is not None and held[0] == season and held[1].loaded_index_id is not None

    @contextmanager
    def lease(self, season: str) -> Generator[ScreenedSearch]:
        """The search over `season`'s index and the suppression list, checked fresh, for one request.

        Raises :class:`UnknownSeason` for a season not offered, and what the holder's lease raises
        (:class:`~debate_core.application.search_index_holder.SearchIndexUnavailable`) when its index
        cannot be loaded or the list cannot be read.
        """
        if season not in self._offered:
            raise UnknownSeason(season)
        with self._lock:
            holder = self._holder(season)
            with holder.lease() as search:
                yield search

    def close(self) -> None:
        """Close the held season's index and delete its file."""
        with self._lock:
            if self._held is not None:
                self._held[1].close()
            self._held = None

    def _holder(self, season: str) -> SearchIndexHolder:
        """`season`'s holder, built after closing the held one if it is another's. Call it locked."""
        held = self._held
        if held is not None and held[0] == season:
            return held[1]
        if held is not None:
            held[1].close()
            self._held = None
        holder = self._holder_for(season)
        self._held = (season, holder)
        return holder
