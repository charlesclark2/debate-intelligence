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
            caption=_caption(history, days, overdue),
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
