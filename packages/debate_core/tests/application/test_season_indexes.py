"""The backfile seasons' shelf: one season's index held at a time (`v1-e39-t18`, the PM's shape 4).

Over fake holders that record what was asked of them, so each rule is one line: which holder a
lease reached, when one was built and when one was closed. The real holders, the real pages and the
suppression list are `packages/debate_api/tests/test_search_pages_seasons.py`'s. Every slug is
invented.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, Final

import pytest

from debate_core.application.card_download import CardDownloadService, CardKey
from debate_core.application.search_index_holder import SearchIndexUnavailable
from debate_core.application.season_indexes import (
    SeasonIndexes,
    UnknownSeason,
    is_season,
    season_label,
    season_of_pointer_key,
    season_pointer_key,
    season_words,
)

SEASON_A: Final = "hsxx25"
SEASON_B: Final = "hsyy24"


class FakeHolder:
    """A season's holder: a lease yields a marker naming the season, and closing is recorded."""

    def __init__(self, season: str, log: list[str], *, fails: bool = False) -> None:
        self.season = season
        self.log = log
        self.fails = fails
        self.loaded_index_id: str | None = None

    @contextmanager
    def lease(self) -> Generator[Any]:
        self.log.append(f"lease {self.season}")
        if self.fails:
            raise SearchIndexUnavailable()
        self.loaded_index_id = f"index of {self.season}"
        yield self.season
        self.log.append(f"let go {self.season}")

    def close(self) -> None:
        self.log.append(f"close {self.season}")
        self.loaded_index_id = None


def shelf(log: list[str], *, failing: frozenset[str] = frozenset()) -> SeasonIndexes:
    def holder_for(season: str) -> Any:
        log.append(f"build {season}")
        return FakeHolder(season, log, fails=season in failing)

    return SeasonIndexes((SEASON_A, SEASON_B), holder_for)


def test_a_season_is_named_by_its_slug_and_the_year_it_starts() -> None:
    assert season_words("hspolicy25") == "2025-26"
    assert season_words("hsld24") == "2024-25"
    assert season_words("hsld99") == "2099-00"
    assert season_label("hspolicy25") == "hspolicy25 (2025-26)"
    assert [is_season(one) for one in ("hsld24", "hsld", "hsld2024", "HSLD24", "hs-ld24", "24")] == [
        True,
        False,
        False,
        False,
        False,
        False,
    ]


def test_a_seasons_pointer_sits_beside_current_json() -> None:
    assert season_pointer_key("hspolicy25") == "reports/tub/search/seasons/hspolicy25.json"
    assert season_of_pointer_key("reports/tub/search/seasons/hspolicy25.json") == "hspolicy25"
    assert season_of_pointer_key("reports/tub/search/current.json") is None
    assert season_of_pointer_key("reports/tub/search/seasons/not-a-season.json") is None
    with pytest.raises(ValueError):
        season_pointer_key("../current")


def test_nothing_is_built_until_a_season_is_chosen() -> None:
    log: list[str] = []

    seasons = shelf(log)

    assert seasons.offered == (SEASON_A, SEASON_B)
    assert seasons.holds(SEASON_A) and not seasons.holds("hsld26")
    assert seasons.held is None
    assert not seasons.is_loaded(SEASON_A)
    assert log == []


def test_a_lease_reaches_the_chosen_seasons_holder_and_loads_it() -> None:
    log: list[str] = []
    seasons = shelf(log)

    with seasons.lease(SEASON_A) as search:
        assert search == SEASON_A

    assert log == ["build hsxx25", "lease hsxx25", "let go hsxx25"]
    assert seasons.held == SEASON_A
    assert seasons.is_loaded(SEASON_A) and not seasons.is_loaded(SEASON_B)


def test_choosing_another_season_closes_the_held_one_before_building_the_next() -> None:
    log: list[str] = []
    seasons = shelf(log)
    with seasons.lease(SEASON_A):
        pass
    log.clear()

    with seasons.lease(SEASON_B):
        pass

    assert log == ["close hsxx25", "build hsyy24", "lease hsyy24", "let go hsyy24"]
    assert seasons.held == SEASON_B
    assert not seasons.is_loaded(SEASON_A)


def test_the_held_season_is_leased_again_without_a_new_holder() -> None:
    log: list[str] = []
    seasons = shelf(log)
    with seasons.lease(SEASON_A):
        pass
    log.clear()

    with seasons.lease(SEASON_A):
        pass

    assert log == ["lease hsxx25", "let go hsxx25"]


def test_a_season_the_shelf_does_not_offer_is_refused_and_nothing_is_closed() -> None:
    log: list[str] = []
    seasons = shelf(log)
    with seasons.lease(SEASON_A):
        pass
    log.clear()

    with pytest.raises(UnknownSeason), seasons.lease("hszz23"):
        pass

    assert log == []
    assert seasons.held == SEASON_A


def test_a_season_that_cannot_load_is_unavailable_and_not_loaded() -> None:
    log: list[str] = []
    seasons = shelf(log, failing=frozenset({SEASON_B}))

    with pytest.raises(SearchIndexUnavailable), seasons.lease(SEASON_B):
        pass

    assert not seasons.is_loaded(SEASON_B)


def test_closing_the_shelf_closes_the_held_season() -> None:
    log: list[str] = []
    seasons = shelf(log)
    with seasons.lease(SEASON_A):
        pass
    log.clear()

    seasons.close()

    assert log == ["close hsxx25"]
    assert seasons.held is None


def test_an_empty_shelf_offers_nothing_and_holds_nothing() -> None:
    seasons = SeasonIndexes.none()

    assert seasons.offered == ()
    assert not seasons.holds(SEASON_A)
    with pytest.raises(UnknownSeason), seasons.lease(SEASON_A):
        pass


# ------------------------------------------------------------------------------------------------
# A download's cart reaches each index in turn
# ------------------------------------------------------------------------------------------------


class Screened:
    """A lease's search: answers `card_source` with the index it was reached through, and the card."""

    def __init__(self, index: str, log: list[str]) -> None:
        self.index = index
        self.log = log
        self.parser_version = "2026.01.05-synthetic"

    def card_source(self, caselist: str, cluster_id: str) -> Any:
        self.log.append(f"{self.index} looks up {caselist}/{cluster_id[:2]}")
        return (self.index, caselist)


class CurrentHolder:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    @contextmanager
    def lease(self) -> Generator[Any]:
        self.log.append("lease current")
        yield Screened("current", self.log)
        self.log.append("let go current")


def download_service(log: list[str]) -> CardDownloadService:
    def holder_for(season: str) -> Any:
        log.append(f"build {season}")
        holder = FakeHolder(season, log)

        @contextmanager
        def lease() -> Generator[Any]:
            log.append(f"lease {season}")
            yield Screened(season, log)
            log.append(f"let go {season}")

        holder.lease = lease  # type: ignore[method-assign]
        return holder

    return CardDownloadService(
        search_index=CurrentHolder(log),  # type: ignore[arg-type]
        seasons=SeasonIndexes((SEASON_A, SEASON_B), holder_for),
        writer=lambda _sources: None,  # type: ignore[arg-type, return-value]
        source_stores=lambda _prefix: None,  # type: ignore[arg-type, return-value]
        access_audit=None,  # type: ignore[arg-type]
        parser_version="2026.01.05-synthetic",
        profile_version="2026.01.01-synthetic",
        clock=lambda: None,  # type: ignore[arg-type, return-value]
        document_size=lambda _content: None,
    )


def test_a_cart_of_several_indexes_leases_the_current_one_first_then_each_season_in_turn() -> None:
    log: list[str] = []
    keys = (
        CardKey(SEASON_B, "b1" + "0" * 62),
        CardKey("hsld26", "c1" + "0" * 62),
        CardKey(SEASON_A, "a1" + "0" * 62),
        CardKey(SEASON_B, "b2" + "0" * 62),
    )

    screened = download_service(log)._screen(keys)  # pyright: ignore[reportPrivateUsage]

    assert screened.sources == (
        (SEASON_B, SEASON_B),
        ("current", "hsld26"),
        (SEASON_A, SEASON_A),
        (SEASON_B, SEASON_B),
    )
    assert log == [
        "lease current",
        "current looks up hsld26/c1",
        "let go current",
        "build hsyy24",
        "lease hsyy24",
        "hsyy24 looks up hsyy24/b1",
        "hsyy24 looks up hsyy24/b2",
        "let go hsyy24",
        "close hsyy24",
        "build hsxx25",
        "lease hsxx25",
        "hsxx25 looks up hsxx25/a1",
        "let go hsxx25",
    ]
