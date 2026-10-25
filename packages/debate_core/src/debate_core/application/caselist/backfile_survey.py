"""What OpenCaselist serves for earlier seasons, counted before any backfile is imported (`v1-e34-t34`).

Data-use policy 1.17 keeps earlier seasons' disclosures, from 2021-22 on, as backfiles, imported from
each caselist's complete archive (`<slug>-all-<date>.zip`; Permitted uses 8). Before the first import
the operator and the PM need the size of the job: which caselists the API lists for each season,
which of them offer a complete archive, and how large each one is. This module asks, and changes
nothing.

## What it asks

* `GET /caselists` twice, current and archived, because an earlier season's caselists are archived
  and the listing's `archived` filter decides what one call returns. The two answers are joined by
  slug.
* `GET /caselists/{slug}/downloads` once for each high-school caselist of a surveyed season.
* A `HEAD` of the newest complete archive each of those lists, for the size its file host declares.
  No archive is downloaded. Each `HEAD` is paced as a download, in the client's rolling window (8 a
  minute by default, never above 10), so the survey is as polite as an import.

A survey of five seasons of three events is about twenty listings and fifteen sizes: a few minutes at
the client's pace, and none of the day's five bulk downloads, because nothing is fetched.

## Seasons

A caselist slug ends in the two-digit year its season **starts**: `hspolicy26` is 2026-27 (its
topic, `policy-2026-27-nhi`, says so). The API's own `year` is reported beside the season so that a
reader can check the mapping against it. Seasons before 2021-22 are never surveyed
(:data:`FIRST_BACKFILE_SEASON_START`): the policy does not import them, and asking about their
archives would serve no decision. They are counted, by slug, and nothing more.

**Counts only.** A slug and a date are what object keys and run summaries carry already; no archive
name, URL, school, team or file name is in the result.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Final, Protocol, Self

from debate_core.application.errors import NotFound, ProviderUnavailable, error_code_of
from debate_core.application.ports.caselist_source import (
    ArchiveKind,
    ArchiveListing,
    ArchiveUnavailable,
    CaselistInfo,
    UnexpectedCaselistResponse,
)
from debate_core.application.settings import ConfigurationError

__all__ = [
    "FIRST_BACKFILE_SEASON_START",
    "BackfileSurvey",
    "BackfileSurveyResult",
    "BackfileSurveySource",
    "SeasonTotals",
    "SurveyedCaselist",
    "is_high_school",
    "season_label",
    "season_start_year",
]

FIRST_BACKFILE_SEASON_START: Final = 2021
"""The first season policy 1.17 keeps as a backfile, 2021-22, by the year it starts."""

_HIGH_SCHOOL_LEVELS: Final = frozenset({"hs", "high school", "highschool"})

#: A failure that ends one caselist's answer and not the survey. An expired token or the site's rate
#: limiter is not one: the survey stops on those, as every other command does.
_ONE_CASELIST_FAILURES: Final = (
    ArchiveUnavailable,
    NotFound,
    ProviderUnavailable,
    UnexpectedCaselistResponse,
)


class BackfileSurveySource(Protocol):
    """The three questions the survey asks of OpenCaselist. The API client answers them."""

    async def list_caselists(self, *, archived: bool | None = None) -> list[CaselistInfo]: ...

    async def list_archives(self, caselist: str) -> list[ArchiveListing]: ...

    async def archive_size(self, archive: ArchiveListing) -> int | None: ...

    async def aclose(self) -> None: ...


def season_start_year(slug: str) -> int:
    """The year a caselist's season starts, from the two digits its slug ends in: `hsld21` → 2021."""
    return 2000 + int(slug[-2:])


def season_label(start_year: int) -> str:
    """A season as debaters write it: 2021 → `2021-22`."""
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def is_high_school(info: CaselistInfo) -> bool:
    """A high-school caselist, by the API's level or, when it gives none, by the slug's `hs`."""
    if info.level:
        return info.level.strip().lower() in _HIGH_SCHOOL_LEVELS
    return info.slug.startswith("hs")


@dataclass(frozen=True, slots=True)
class SurveyedCaselist:
    """One high-school caselist of a surveyed season, as the API describes it."""

    slug: str
    season: str
    event: str | None
    """The API's event code (`ld`, `cx`, `pf`)."""
    api_year: int | None
    archived: bool
    weeklies_listed: int
    complete_archives_listed: int
    newest_complete_archive: date | None
    complete_archive_bytes: int | None
    """The newest complete archive's size as its file host declares it, or `None`."""
    unanswered: str | None
    """Why a count or the size is missing: an error code, with the HTTP status when the answer gave one
    (`PROVIDER_UNAVAILABLE (HTTP 500)`), `NO_CONTENT_LENGTH`, or `NOT_ASKED`."""


@dataclass(frozen=True, slots=True)
class SeasonTotals:
    """One season's high-school caselists, added up."""

    season: str
    caselists: int
    with_complete_archive: int
    sized: int
    """How many of those complete archives declared a size."""
    complete_archive_bytes: int
    """The sum of the declared sizes. A lower bound when `sized` is below `with_complete_archive`."""


@dataclass(frozen=True, slots=True)
class BackfileSurveyResult:
    """What the API serves for the surveyed seasons, and what it lists outside them."""

    first_season: str
    last_season: str
    caselists: tuple[SurveyedCaselist, ...]
    """Newest season first, then by slug."""
    listed_caselists: int
    """Every caselist the two listings named, joined by slug."""
    high_school_before_backfiles: int
    """High-school caselists of seasons before 2021-22: never surveyed, never imported."""
    high_school_after_survey: int
    """High-school caselists of seasons after the last surveyed one: the current season's."""
    not_high_school: int
    listing_requests: int
    size_requests: int

    def season_totals(self) -> tuple[SeasonTotals, ...]:
        seasons = sorted({one.season for one in self.caselists}, reverse=True)
        return tuple(
            _totals(season, [one for one in self.caselists if one.season == season]) for season in seasons
        )

    @property
    def complete_archive_bytes(self) -> int:
        return sum(one.complete_archive_bytes or 0 for one in self.caselists)


class BackfileSurvey:
    """Counts what OpenCaselist serves for earlier seasons. Lists and sizes; never downloads."""

    def __init__(self, source: BackfileSurveySource) -> None:
        self._source = source

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._source.aclose()

    async def survey(
        self, *, first_season_start: int, last_season_start: int, sizes: bool = True
    ) -> BackfileSurveyResult:
        """Survey the seasons from `first_season_start` to `last_season_start`, both included.

        Raises :class:`ConfigurationError` for a first season before 2021-22, or a range that runs
        backwards, before any request is made.
        """
        if first_season_start < FIRST_BACKFILE_SEASON_START:
            raise ConfigurationError(
                f"seasons before {season_label(FIRST_BACKFILE_SEASON_START)} are not imported "
                "(docs/policies/caselist-data-use.md, Retention), so they are not surveyed",
                field="first_season",
            )
        if last_season_start < first_season_start:
            raise ConfigurationError("the last season surveyed is before the first", field="last_season")
        listed = _joined(
            await self._source.list_caselists(archived=False),
            await self._source.list_caselists(archived=True),
        )
        high_school = [info for info in listed if is_high_school(info)]
        in_range = sorted(
            (
                info
                for info in high_school
                if first_season_start <= season_start_year(info.slug) <= last_season_start
            ),
            key=lambda info: (-season_start_year(info.slug), info.slug),
        )
        surveyed: list[SurveyedCaselist] = []
        size_requests = 0
        for info in in_range:
            one, asked = await self._one(info, sizes=sizes)
            surveyed.append(one)
            size_requests += asked
        return BackfileSurveyResult(
            first_season=season_label(first_season_start),
            last_season=season_label(last_season_start),
            caselists=tuple(surveyed),
            listed_caselists=len(listed),
            high_school_before_backfiles=sum(
                1 for info in high_school if season_start_year(info.slug) < first_season_start
            ),
            high_school_after_survey=sum(
                1 for info in high_school if season_start_year(info.slug) > last_season_start
            ),
            not_high_school=len(listed) - len(high_school),
            listing_requests=2 + len(in_range),
            size_requests=size_requests,
        )

    async def _one(self, info: CaselistInfo, *, sizes: bool) -> tuple[SurveyedCaselist, int]:
        season = season_label(season_start_year(info.slug))
        try:
            archives = await self._source.list_archives(info.slug)
        except _ONE_CASELIST_FAILURES as failure:
            return _surveyed(info, season, archives=(), size=None, unanswered=_why(failure)), 0
        complete = sorted(
            (one for one in archives if one.kind is ArchiveKind.FULL and one.archive_date is not None),
            key=lambda one: one.archive_date or date.min,
        )
        if not complete:
            return _surveyed(info, season, archives=archives, size=None, unanswered=None), 0
        if not sizes:
            return _surveyed(info, season, archives=archives, size=None, unanswered="NOT_ASKED"), 0
        try:
            size = await self._source.archive_size(complete[-1])
        except _ONE_CASELIST_FAILURES as failure:
            return _surveyed(info, season, archives=archives, size=None, unanswered=_why(failure)), 1
        unanswered = None if size is not None else "NO_CONTENT_LENGTH"
        return _surveyed(info, season, archives=archives, size=size, unanswered=unanswered), 1


_HTTP_STATUS: Final = re.compile(r"\bHTTP ([1-5][0-9]{2})\b")


def _why(failure: BaseException) -> str:
    """The failure's code, and the HTTP status its message names, if it names one."""
    status = _HTTP_STATUS.search(str(failure))
    return f"{error_code_of(failure)} (HTTP {status[1]})" if status else error_code_of(failure)


def _joined(*listings: Iterable[CaselistInfo]) -> list[CaselistInfo]:
    by_slug: dict[str, CaselistInfo] = {}
    for listing in listings:
        for info in listing:
            by_slug.setdefault(info.slug, info)
    return list(by_slug.values())


def _surveyed(
    info: CaselistInfo,
    season: str,
    *,
    archives: Iterable[ArchiveListing],
    size: int | None,
    unanswered: str | None,
) -> SurveyedCaselist:
    archives = tuple(archives)
    complete = [one.archive_date for one in archives if one.kind is ArchiveKind.FULL and one.archive_date]
    return SurveyedCaselist(
        slug=info.slug,
        season=season,
        event=info.event,
        api_year=info.year,
        archived=info.archived,
        weeklies_listed=sum(1 for one in archives if one.kind is ArchiveKind.WEEKLY),
        complete_archives_listed=len(complete),
        newest_complete_archive=max(complete) if complete else None,
        complete_archive_bytes=size,
        unanswered=unanswered,
    )


def _totals(season: str, caselists: list[SurveyedCaselist]) -> SeasonTotals:
    return SeasonTotals(
        season=season,
        caselists=len(caselists),
        with_complete_archive=sum(1 for one in caselists if one.complete_archives_listed),
        sized=sum(1 for one in caselists if one.complete_archive_bytes is not None),
        complete_archive_bytes=sum(one.complete_archive_bytes or 0 for one in caselists),
    )
