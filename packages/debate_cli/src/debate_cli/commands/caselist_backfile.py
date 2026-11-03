"""`caselist backfile-survey` and `caselist backfile-import`: earlier seasons as backfiles (`v1-e34-t34`).

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

## `caselist backfile-import`

::

    debate-research caselist backfile-import --caselist hspolicy25            # dry run
    debate-research caselist backfile-import --caselist hspolicy25 --execute

One backfile caselist's complete archive, downloaded, imported, parsed and published, holding the
bucket's run lock for each publish step and never through the download or the parse. Without
`--execute` it is a dry run: the listing and a `HEAD`, the ledger and the volume read, nothing written,
nothing locked, and every refusal the real run would meet named, exit `1`. The rules are
:mod:`debate_core.application.caselist.backfile_import`'s. It reads only settings, so it runs unchanged
on the Mac and in the caselist image: the data directory, the inbox and the token backend are the
environment's.

An expired login ends it as it ends `caselist pull`: in bucket mode with what was refused and the
Wednesday login as its hint, never `caselist auth login` (`v1-e40-t35`,
:mod:`debate_cli.caselist_auth_expired`), and on the Mac as before.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, NoReturn

import typer

from debate_cli.bucket_lock import terminated_on_sigterm
from debate_cli.caselist_auth_expired import cloud_cure_for_an_expired_login
from debate_cli.caselist_events import event_for_caselist
from debate_cli.context import CliContext, cli_context, command_name
from debate_cli.exit_codes import ExitCode
from debate_cli.options.bucket_environment import CONFIRM_PROD_FLAG
from debate_cli.output import CommandFailure, JsonValue, TableSpec
from debate_core.application.caselist.backfile_import import (
    IMPORT_COMMAND,
    BackfileImportRefused,
    BackfilePlan,
    BackfileReport,
    Refusal,
    StepLine,
)
from debate_core.application.caselist.backfile_survey import (
    FIRST_BACKFILE_SEASON_START,
    BackfileSurvey,
    BackfileSurveyResult,
    SurveyedCaselist,
    season_label,
)
from debate_core.application.caselist.memory_high_water import MemoryHighWater
from debate_core.application.settings import ConfigurationError, Environment
from debate_core.domain.season import current_season_start

__all__ = [
    "backfile_import",
    "backfile_survey",
    "current_season_start",
    "import_as_json",
    "step_line_as_json",
    "survey_as_json",
]


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


# ------------------------------------------------------------------------------------------------
# caselist backfile-import
# ------------------------------------------------------------------------------------------------


def backfile_import(
    ctx: typer.Context,
    caselist: Annotated[
        str, typer.Option("--caselist", help="The backfile caselist to import, e.g. hspolicy25.")
    ],
    execute: Annotated[
        bool,
        typer.Option("--execute", help="Import it. Without it, a dry run that downloads and writes nothing."),
    ] = False,
    confirm_prod: Annotated[
        bool, typer.Option(CONFIRM_PROD_FLAG, help="Required with --execute in the production environment.")
    ] = False,
) -> None:
    """Import a backfile caselist's complete archive: download, import, parse, publish. Dry run by default."""
    cli = cli_context(ctx)
    settings = cli.services.settings
    if execute and settings.environment is Environment.PROD and not confirm_prod:
        _refuse(
            cli,
            ctx,
            (Refusal("CONFIRMATION_REQUIRED", f"refusing production's bucket without {CONFIRM_PROD_FLAG}"),),
            None,
        )
    service = cli.services.backfile_import(event_for_caselist=event_for_caselist)
    if not execute:
        with cloud_cure_for_an_expired_login(cli, ctx, bucket_mode=service.bucket_mode):
            plan = asyncio.run(service.plan(caselist))
        if plan.refused:
            _refuse(cli, ctx, plan.refusals, plan)
        cli.output.success(command_name(ctx), import_as_json(plan, None), display=_import_table(plan, None))
        return
    try:
        with (
            terminated_on_sigterm(),
            cloud_cure_for_an_expired_login(cli, ctx, bucket_mode=service.bucket_mode),
        ):
            report = asyncio.run(service.run(caselist, on_line=lambda line: _write_step_line(cli, line)))
    except BackfileImportRefused as refused:
        _refuse(cli, ctx, refused.refusals, None)
    payload = import_as_json(report.plan, report)
    if not report.succeeded:
        failure = CommandFailure(
            code="BACKFILE_IMPORT_INCOMPLETE",
            message=f"the backfile import of {caselist} did not finish: {report.bundle or 'see the steps'}",
            exit_code=ExitCode.DOMAIN_FAILURE,
            details=payload,
            hint="Run the dry run again: it says what is left, and the import resumes from the inbox.",
        )
        cli.output.failure(failure, command=command_name(ctx))
        raise typer.Exit(code=failure.exit_code)
    cli.output.success(command_name(ctx), payload, display=_import_table(report.plan, report))


def _refuse(
    cli: CliContext, ctx: typer.Context, refusals: tuple[Refusal, ...], plan: BackfilePlan | None
) -> NoReturn:
    failure = CommandFailure(
        code="BACKFILE_IMPORT_REFUSED",
        message="; ".join(f"{one.code}: {one.message}" for one in refusals),
        exit_code=ExitCode.DOMAIN_FAILURE,
        details={
            "refusals": [one.code for one in refusals],
            "plan": import_as_json(plan, None) if plan is not None else None,
        },
        hint="Nothing was downloaded or written. Fix what each refusal names, then run the dry run again.",
    )
    cli.output.failure(failure, command=command_name(ctx))
    raise typer.Exit(code=failure.exit_code)


def _write_step_line(cli: CliContext, line: StepLine) -> None:
    """A step's line on stderr as it starts, ends or goes (`v1-e40-t32`); stdout keeps the result."""
    cli.output.event_line(IMPORT_COMMAND, str(line.event), step_line_as_json(line), text=_step_sentence(line))


def step_line_as_json(line: StepLine) -> dict[str, JsonValue]:
    """A step line's `data`: the step, its seconds, its counts, and the memory figures that could be read.

    A figure that could not be read is left out, never zero (the PM's amendment of 2026-10-31).
    """
    data: dict[str, JsonValue] = {"step": line.step}
    if line.seconds is not None:
        data["seconds"] = round(line.seconds, 1)
    data["counts"] = {name: count for name, count in line.counts.items()}
    memory = _memory_as_json(line.memory)
    if memory:
        data["memory"] = memory
    return data


def _memory_as_json(memory: MemoryHighWater | None) -> dict[str, JsonValue]:
    if memory is None:
        return {}
    data: dict[str, JsonValue] = {}
    if memory.container_peak_bytes is not None:
        data["container_peak_bytes"] = memory.container_peak_bytes
        data["cgroup"] = memory.cgroup
    if memory.main_process_peak_bytes is not None:
        data["main_process_peak_bytes"] = memory.main_process_peak_bytes
    return data


def _step_sentence(line: StepLine) -> str:
    said = f"{IMPORT_COMMAND}: {line.step} {str(line.event).replace('_', ' ')}"
    if line.seconds is not None:
        said += f" at {line.seconds:.1f} s"
    if line.counts:
        said += "; " + ", ".join(f"{name} {count:,}" for name, count in line.counts.items())
    memory = line.memory
    if memory is not None and memory.container_peak_bytes is not None:
        said += f"; container peak {memory.container_peak_bytes:,} bytes (cgroup {memory.cgroup})"
    if memory is not None and memory.main_process_peak_bytes is not None:
        said += f"; main process peak {memory.main_process_peak_bytes:,} bytes"
    return said


def import_as_json(plan: BackfilePlan, report: BackfileReport | None) -> dict[str, JsonValue]:
    """The `--json` `data`: counts, a slug and a date, never a path or a name."""
    space = plan.space
    data: dict[str, JsonValue] = {
        "caselist": plan.caselist,
        "season": plan.season,
        "applied": report is not None,
        "archive_date": plan.archive_date.isoformat() if plan.archive_date else None,
        "archive_bytes": plan.archive_bytes,
        "in_inbox": plan.in_inbox,
        "already_imported": plan.already_imported,
        "backfile_downloads_left": plan.downloads_left,
        "inside_no_import_window": plan.inside_window,
        "no_import_window_ends": plan.window_ends.isoformat() if plan.window_ends else None,
        "space": {
            "estimate_bytes": space.estimate_bytes,
            "required_bytes": space.required_bytes,
            "free_bytes": space.free_bytes,
            "enough": space.enough,
        }
        if space is not None
        else None,
        "refusals": [{"code": one.code, "message": one.message} for one in plan.refusals],
    }
    if report is not None:
        data["import"] = {
            "downloaded_bytes": report.downloaded_bytes,
            "members": report.members,
            "stored": report.stored,
            "suppressed": report.suppressed,
            "held_by_request": dict(report.held_by_request),
            "sources_uploaded": report.sources_uploaded,
            "sources_skipped": report.sources_skipped,
            "bundle": report.bundle,
            "parsed": report.parsed,
            "unsupported": report.unsupported,
            "failed": report.failed,
            "cards": report.cards,
            "parsed_uploaded": report.parsed_uploaded,
            "archive_left_inbox": report.archive_left_inbox,
            "step_seconds": {name: round(seconds, 1) for name, seconds in report.steps.items()},
        }
    return data


def _import_table(plan: BackfilePlan, report: BackfileReport | None) -> TableSpec:
    space = plan.space
    rows = [
        ["Caselist", f"{plan.caselist} ({plan.season})"],
        [
            "Complete archive",
            f"{plan.archive_date} ({plan.archive_bytes:,} bytes)" if plan.archive_bytes else "—",
        ],
        ["Already imported", "yes" if plan.already_imported else "no"],
        ["Backfile downloads left (24 h)", str(plan.downloads_left)],
        ["No-import window", "inside" if plan.inside_window else "outside"],
        [
            "Free space",
            f"{space.free_bytes:,} free; {space.required_bytes:,} needed "
            f"({space.estimate_bytes:,} estimate + 25%)"
            if space is not None
            else "—",
        ],
    ]
    if report is not None:
        rows += [
            [
                "Imported",
                f"{report.members} member(s), {report.stored} stored, {report.suppressed} suppressed",
            ],
            [
                "Published",
                f"{report.sources_uploaded} source(s) uploaded, {report.sources_skipped} already there",
            ],
            ["Bundle", report.bundle or "—"],
            [
                "Parsed",
                f"{report.parsed} parsed, {report.unsupported} unsupported, {report.failed} failed, "
                f"{report.cards} card(s)",
            ],
            ["Parsed store", f"{report.parsed_uploaded} object(s) uploaded"],
        ]
    return TableSpec(
        columns=("", ""),
        rows=rows,
        title=f"caselist backfile-import{' (dry run)' if report is None else ''}",
        caption="Nothing was downloaded or written. Re-run with --execute to import it."
        if report is None
        else "Imported, parsed and published. Not indexed for the search pilot, not classified.",
    )
