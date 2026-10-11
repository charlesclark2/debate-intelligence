"""`debate-research caselist runs`: the recent `caselist pull` runs, from the run log.

::

    debate-research caselist runs              # the last 5, from this machine's log
    debate-research caselist runs --last 20
    debate-research caselist runs --remote     # from reports/sync-runs/ in the evidence bucket

One row per run: its id, when it started, its outcome, the archives it downloaded, the archives
the daily download cap deferred, and the publish work it left pending. The records and the rules
for reading them are :mod:`debate_core.application.sync_runs` (`v1-e34-t03-sync-monitoring`); this
is the rendering.

The caption says how long it has been since the newest run. A failed run leaves a record and a
notification, but a schedule that has stopped firing leaves nothing — the newest record just gets
older — so an overdue schedule is called out here, where the operator looks.

It also says what the newest run's parse stage did, in the stage's own sentence: its counts, and
for a stage that failed or is waiting for a login, which caselists and which command finishes it
(`v1-e34-t17`). The record has no field for those counts, and gains none, so that an older build
still reads a newer build's records; the sentence is the stage's `reason`, which every record has.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Annotated, cast

import typer

from debate_cli.context import cli_context, command_name
from debate_cli.output import JsonValue, TableSpec
from debate_core.application.sync_runs import SyncRunHistory, SyncRunRecord

__all__ = ["runs"]


def runs(
    ctx: typer.Context,
    last: Annotated[int, typer.Option("--last", min=1, help="How many recent runs to show.")] = 5,
    remote: Annotated[
        bool,
        typer.Option("--remote", help="Read the run records in the evidence bucket, not this machine's log."),
    ] = False,
) -> None:
    """List recent caselist pull runs: outcome, downloads, cap deferrals and pending publishes."""
    cli = cli_context(ctx)
    settings = cli.services.settings
    history = cli.services.caselist_sync_history()
    records = asyncio.run(history.recent(last, remote=remote))
    now = datetime.now(UTC)
    days = history.days_since_last_run(records, now)
    overdue = history.overdue(records, now)
    source = "bucket" if remote else "local log"
    payload: dict[str, JsonValue] = {
        "environment": settings.environment.value,
        "source": source,
        "days_since_last_run": days,
        "overdue": overdue,
        "runs": [cast("JsonValue", record.model_dump(mode="json")) for record in records],
    }
    cli.output.success(
        command_name(ctx),
        payload,
        display=TableSpec(
            columns=(
                "Run id",
                "Started (UTC)",
                "Outcome",
                "Downloaded",
                "Deferred by cap",
                "Pending publish",
            ),
            rows=[_row(record) for record in records],
            title=f"caselist pull runs ({settings.environment.value}, {source}, last {last})",
            caption=_caption(history, days, overdue) + _parse_sentence(records[0] if records else None),
        ),
    )


def _row(record: SyncRunRecord) -> list[str]:
    downloaded = (
        f"{record.archives_downloaded} of {record.archives_wanted}"
        if record.archives_deferred
        else str(record.archives_downloaded)
    )
    return [
        record.run_id,
        record.started_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M"),
        str(record.outcome) + (f" ({record.error_class})" if record.error_class else ""),
        downloaded,
        str(record.archives_deferred),
        str(len(record.pending_publish)),
    ]


def _parse_sentence(newest: SyncRunRecord | None) -> str:
    """What the newest run's parse stage did, as a leading-space sentence; nothing for one skipped.

    A skipped stage parsed nothing, which is every week with nothing new and every run of a build
    before `v1-e34-t17`.
    """
    stage = next((one for one in newest.stages if one.stage == "parse"), None) if newest else None
    if newest is None or stage is None or stage.outcome == "skipped" or not stage.reason:
        return ""
    return f" Parse stage of the newest run ({newest.run_id}): {stage.outcome}. {stage.reason}."


def _caption(history: SyncRunHistory, days: int | None, overdue: bool) -> str:
    if days is None:
        return "No caselist pull has been recorded here. Run: debate-research caselist pull"
    since = f"The newest run started {days} day(s) ago."
    if overdue:
        return (
            f"{since} That is longer than a weekly schedule allows ({history.overdue_after_days} "
            "days): the schedule may have stopped. Run: debate-research caselist pull"
        )
    return since
