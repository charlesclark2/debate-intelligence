"""`debate-research caselist runs`: the recent `caselist pull` runs, from the run log.

::

    debate-research caselist runs              # the last 5, from this machine's log
    debate-research caselist runs --last 20
    debate-research caselist runs --remote     # from reports/sync-runs/ in the evidence bucket

One row per run: its id, when it started, its outcome, the codes it failed on and its verdict, the
archives it downloaded, the archives the daily download cap deferred, the publish work it left
pending, and what its parse stage did.
The records and the rules for reading them are :mod:`debate_core.application.sync_runs`
(`v1-e34-t03-sync-monitoring`); this is the rendering.

The caption says how long it has been since the newest run. A failed run leaves a record and a
notification, but a schedule that has stopped firing leaves nothing — the newest record just gets
older — so an overdue schedule is called out here, where the operator looks.

It also says what the newest run's parse stage did, in the stage's own sentence: its counts, and
for a stage that failed or is waiting for a login, which caselists and which command finishes it
(`v1-e34-t17`).

## The parse stage's column

Every run's nine parse counts are in the table, in its last column (`v1-e34-t19`). The record has
no field for them and gains none, so that a build already installed still reads a newer build's
records; they are in the run's **details**, kept beside the record under the same run id
(:class:`~debate_core.application.sync_runs.SyncRunDetails`). The column says one of three things:

* the nine counts, for a run whose parse stage parsed something;
* `did not run`, for a run whose details say the stage parsed nothing: it was turned off, or the
  run imported nothing;
* `not recorded`, for a run with no details: one a build before `v1-e34-t19` recorded.

`--json` gives each run its record's own fields, as before, and a `details` object beside them, or
`null`: the stages' error codes and hints, the codes the exit status was decided from, and `parse`.

## Codes and verdict (`v1-e34-t23`)

Two columns after the outcome, from the same details:

* `Failed on`: the codes the run's exit status was decided from, or `none` for a run that did not
  fail on any;
* `Verdict`: `retry` when every one of them is a failure a retry may cure, the command's own rule
  for exit `3` (:func:`~debate_cli.exit_codes.codes_exit_as_a_retrieval_failure`), which the run's
  notification asks too; `person` for any other failure; `none` when there were none.

Both say `not recorded` for a run with no details. `--json` gives the verdict as `verdict`, `retry`
or `person`, or `null` when there is none or no details.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Annotated, Final, cast

import typer

from debate_cli.context import cli_context, command_name
from debate_cli.exit_codes import codes_exit_as_a_retrieval_failure
from debate_cli.output import JsonValue, TableSpec
from debate_core.application.sync_runs import RecordedRun, SyncRunHistory, SyncRunRecord

__all__ = ["runs"]


def runs(
    ctx: typer.Context,
    last: Annotated[int, typer.Option("--last", min=1, help="How many recent runs to show.")] = 5,
    remote: Annotated[
        bool,
        typer.Option("--remote", help="Read the run records in the evidence bucket, not this machine's log."),
    ] = False,
) -> None:
    """List recent caselist pull runs: outcome, downloads, cap deferrals, pending publishes, parse counts."""
    cli = cli_context(ctx)
    settings = cli.services.settings
    history = cli.services.caselist_sync_history()
    recorded = asyncio.run(history.recent_runs(last, remote=remote))
    records = [run.record for run in recorded]
    now = datetime.now(UTC)
    days = history.days_since_last_run(records, now)
    overdue = history.overdue(records, now)
    source = "bucket" if remote else "local log"
    payload: dict[str, JsonValue] = {
        "environment": settings.environment.value,
        "source": source,
        "days_since_last_run": days,
        "overdue": overdue,
        "runs": [_run_as_json(run) for run in recorded],
    }
    cli.output.success(
        command_name(ctx),
        payload,
        display=TableSpec(
            columns=(
                "Run id",
                "Started (UTC)",
                "Outcome",
                "Failed on",
                "Verdict",
                "Downloaded",
                "Deferred by cap",
                "Pending publish",
                "Parse stage",
            ),
            rows=[_row(run) for run in recorded],
            title=f"caselist pull runs ({settings.environment.value}, {source}, last {last})",
            caption=_caption(history, days, overdue) + _parse_sentence(records[0] if records else None),
        ),
    )


def _row(run: RecordedRun) -> list[str]:
    record = run.record
    downloaded = (
        f"{record.archives_downloaded} of {record.archives_wanted}"
        if record.archives_deferred
        else str(record.archives_downloaded)
    )
    return [
        record.run_id,
        record.started_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M"),
        str(record.outcome) + (f" ({record.error_class})" if record.error_class else ""),
        *_failed_on_and_verdict(run),
        downloaded,
        str(record.archives_deferred),
        str(len(record.pending_publish)),
        _parse_stage(run),
    ]


def _run_as_json(run: RecordedRun) -> JsonValue:
    """One run for `--json`: the record's fields as they always were, its details beside them, and
    its verdict (`v1-e34-t23`)."""
    body = cast("dict[str, JsonValue]", run.record.model_dump(mode="json"))
    body["details"] = (
        cast("JsonValue", run.details.model_dump(mode="json")) if run.details is not None else None
    )
    body["verdict"] = _verdict(run)
    return body


NOT_RECORDED: Final = "not recorded"
"""A run with no details beside its record: a build before `v1-e34-t19` recorded it."""

NONE: Final = "none"


def _verdict(run: RecordedRun) -> str | None:
    """`retry` or `person` for a run that failed, by the command's rule for exit `3`; else `None`."""
    if run.details is None or not run.details.failure_codes:
        return None
    return "retry" if codes_exit_as_a_retrieval_failure(run.details.failure_codes) else "person"


def _failed_on_and_verdict(run: RecordedRun) -> tuple[str, str]:
    """The table's two cells: the codes the exit was decided from, and the verdict on them."""
    if run.details is None:
        return NOT_RECORDED, NOT_RECORDED
    codes = run.details.failure_codes
    return (", ".join(codes) or NONE), (_verdict(run) or NONE)


PARSE_STAGE_NOT_RECORDED: Final = NOT_RECORDED

PARSE_STAGE_DID_NOT_RUN: Final = "did not run"
"""A run whose parse stage parsed nothing: turned off, or nothing was imported."""


def _parse_stage(run: RecordedRun) -> str:
    """The parse stage's nine counts as the table's last cell, one line for each kind of count.

    Every one of the nine is here, by name: the caselists parsed and how many of them in full; the
    sources attempted, skipped, unsupported and failed; the cards; and the parsed store's objects
    uploaded and the caselists whose store was not published.
    """
    if run.details is None:
        return PARSE_STAGE_NOT_RECORDED
    parse = run.details.parse
    if parse is None:
        return PARSE_STAGE_DID_NOT_RUN
    return "\n".join(
        (
            f"{parse.caselists} caselist(s), {parse.full_parses} in full",
            f"{parse.attempted} attempted, {parse.skipped} skipped, "
            f"{parse.unsupported} unsupported, {parse.failed} failed",
            f"{parse.cards} card(s)",
            f"{parse.uploaded} uploaded, {parse.not_published} caselist(s) not published",
        )
    )


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
