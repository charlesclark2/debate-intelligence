"""`debate-research caselist backfile-survey`: what OpenCaselist serves for earlier seasons.

::

    debate-research caselist backfile-survey                      # 2021-22 to last season
    debate-research caselist backfile-survey --first-season 2024-25 --last-season 2025-26
    debate-research --json caselist backfile-survey

Read-only (`v1-e34-t34`). It lists the caselists, lists each high-school caselist's downloads for
the seasons asked about, and asks the file host the size of each one's newest complete archive with
a `HEAD`. It downloads nothing, writes nothing, spends none of the day's five bulk downloads, and
touches no bucket, so it takes no lock. Every request is paced by the client, a `HEAD` as a download.
The work, and the reason for each rule, is
:mod:`debate_core.application.caselist.backfile_survey`; this is the rendering.

Seasons before 2021-22 are refused (data-use policy 1.17, Retention). The last season defaults to the
one before the season today falls in, since the current season is the weekly run's.
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Annotated

import typer

from debate_cli.context import cli_context, command_name
from debate_cli.output import JsonValue, TableSpec
from debate_core.application.caselist.backfile_survey import (
    FIRST_BACKFILE_SEASON_START,
    BackfileSurvey,
    BackfileSurveyResult,
    SurveyedCaselist,
    season_label,
)
from debate_core.application.settings import ConfigurationError

__all__ = ["backfile_survey", "current_season_start", "survey_as_json"]

SEASON_STARTS_IN_MONTH = 8
"""A season runs 1 August to 31 July (docs/policies/caselist-data-use.md, Retention)."""


def backfile_survey(
    ctx: typer.Context,
    first_season: Annotated[
        str | None,
        typer.Option("--first-season", help="First season to survey, as 2021-22. Not before 2021-22."),
    ] = None,
    last_season: Annotated[
        str | None,
        typer.Option("--last-season", help="Last season to survey. Default: the season before this one."),
    ] = None,
    sizes: Annotated[
        bool,
        typer.Option("--sizes/--no-sizes", help="Ask the size of each newest complete archive."),
    ] = True,
) -> None:
    """Count the caselists, complete archives and their sizes for earlier seasons. Downloads nothing."""
    cli = cli_context(ctx)
    clock = cli.services.clock()
    first = _season_start(first_season, "--first-season") if first_season else FIRST_BACKFILE_SEASON_START
    last = (
        _season_start(last_season, "--last-season")
        if last_season
        else current_season_start(clock().date()) - 1
    )
    result = asyncio.run(_survey(cli.services.backfile_survey(), first, last, sizes))
    cli.output.success(
        command_name(ctx),
        survey_as_json(result, environment=cli.services.settings.environment.value),
        display=_table(result),
    )


async def _survey(survey: BackfileSurvey, first: int, last: int, sizes: bool) -> BackfileSurveyResult:
    async with survey:
        return await survey.survey(first_season_start=first, last_season_start=last, sizes=sizes)


def current_season_start(today: date) -> int:
    """The year the season `today` falls in started: 2026 from 1 August 2026 to 31 July 2027."""
    return today.year if today.month >= SEASON_STARTS_IN_MONTH else today.year - 1


def _season_start(text: str, option: str) -> int:
    start, _, end = text.partition("-")
    if not (start.isdigit() and len(start) == 4 and end.isdigit() and len(end) == 2):
        raise ConfigurationError(f"{option} takes a season written as 2021-22, not {text!r}", field=option)
    if season_label(int(start)) != text:
        raise ConfigurationError(f"{option} {text!r} does not span two consecutive years", field=option)
    return int(start)


def survey_as_json(result: BackfileSurveyResult, *, environment: str) -> dict[str, JsonValue]:
    """The `--json` `data`: counts, slugs and dates only."""
    return {
        "environment": environment,
        "first_season": result.first_season,
        "last_season": result.last_season,
        "listed_caselists": result.listed_caselists,
        "high_school_before_backfiles": result.high_school_before_backfiles,
        "high_school_after_survey": result.high_school_after_survey,
        "not_high_school": result.not_high_school,
        "listing_requests": result.listing_requests,
        "size_requests": result.size_requests,
        "complete_archive_bytes": result.complete_archive_bytes,
        "seasons": [
            {
                "season": totals.season,
                "caselists": totals.caselists,
                "with_complete_archive": totals.with_complete_archive,
                "sized": totals.sized,
                "complete_archive_bytes": totals.complete_archive_bytes,
            }
            for totals in result.season_totals()
        ],
        "caselists": [_caselist_as_json(one) for one in result.caselists],
    }


def _caselist_as_json(one: SurveyedCaselist) -> JsonValue:
    return {
        "slug": one.slug,
        "season": one.season,
        "event": one.event,
        "api_year": one.api_year,
        "archived": one.archived,
        "weeklies_listed": one.weeklies_listed,
        "complete_archives_listed": one.complete_archives_listed,
        "newest_complete_archive": one.newest_complete_archive.isoformat()
        if one.newest_complete_archive
        else None,
        "complete_archive_bytes": one.complete_archive_bytes,
        "unanswered": one.unanswered,
    }


def _table(result: BackfileSurveyResult) -> TableSpec:
    return TableSpec(
        columns=(
            "Season",
            "Caselist",
            "Event",
            "API year",
            "Archived",
            "Weeklies",
            "Complete archives",
            "Newest complete",
            "Size (bytes)",
        ),
        rows=[_row(one) for one in result.caselists],
        title=f"Backfile survey, {result.first_season} to {result.last_season}",
        caption=_caption(result),
    )


def _row(one: SurveyedCaselist) -> list[str]:
    size = (
        f"{one.complete_archive_bytes:,}"
        if one.complete_archive_bytes is not None
        else (one.unanswered or "—")
    )
    return [
        one.season,
        one.slug,
        one.event or "—",
        str(one.api_year) if one.api_year is not None else "—",
        "yes" if one.archived else "no",
        str(one.weeklies_listed),
        str(one.complete_archives_listed),
        one.newest_complete_archive.isoformat() if one.newest_complete_archive else "—",
        size,
    ]


def _caption(result: BackfileSurveyResult) -> str:
    seasons = "; ".join(
        f"{totals.season}: {totals.caselists} caselist(s), {totals.with_complete_archive} with a complete "
        f"archive, {totals.complete_archive_bytes:,} bytes over {totals.sized} sized"
        for totals in result.season_totals()
    )
    return (
        f"{result.listed_caselists} caselist(s) listed; {result.high_school_before_backfiles} high-school "
        f"caselist(s) before 2021-22 not surveyed; {result.high_school_after_survey} after the last season; "
        f"{result.not_high_school} not high school. {seasons or 'No caselist in these seasons.'} "
        f"{result.listing_requests} listing request(s) and {result.size_requests} size request(s); nothing "
        "was downloaded."
    )
