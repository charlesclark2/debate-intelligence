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

## What the runs owe (`v1-e40-t08`)

The caption ends by saying which parses are owed, from the parse-owed file: this machine's, or with
`--remote` the bucket's, which is the cloud run's. A week a run published and did not parse and
publish the parsed store of, and a caselist owed a full parse under a new parser version, both of
which the next `caselist pull` does whether or not it imports anything. `--json` gives the file's
entries as `parses_owed`, or `null` when the file cannot be read.

## The banner's own words (`v1-e34-t26`)

Two banners put words of their own beside the verdict, and the `Verdict` cell shows them after it, in
brackets: `person (skipped)` for a run the lock refused, and `retry (retry once fixed)` for a refusal
the next run gets past only once its fix is made. `--json` gives them as `banner`, or `null` for
every other run and for a run with no details. They are
:func:`~debate_core.application.sync_runs.banner_words`, decided as the banner's title is, by the
same rule as the verdict.

## A skipped run (`v1-e40-t29`)

A pull refused because the weekly run's home moved to prod did nothing by design, and its details say
so: its `Outcome` is `skipped (RUN_HOME_MOVED)`, with `none` failed on and `none (skipped)` as its
verdict (:func:`~debate_core.application.sync_runs.outcome_shown`). Its record still says `failed`
(`RunHomeMoved`), which is what a build from before it shows, and what `--json` gives as the record's
`outcome`; the details' `skipped` is the code, `RUN_HOME_MOVED`.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Annotated, Final, cast

import typer

from debate_cli.context import cli_context, command_name
from debate_cli.exit_codes import codes_exit_as_a_retrieval_failure
from debate_cli.output import JsonValue, TableSpec
from debate_cli.parses_owed import parses_owed
from debate_core.application.sync_runs import (
    RecordedRun,
    SyncRunHistory,
    SyncRunRecord,
    banner_words,
    outcome_shown,
)

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
    owed, owed_sentence = parses_owed(cli.services, remote=remote)
    payload: dict[str, JsonValue] = {
        "environment": settings.environment.value,
        "source": source,
        "days_since_last_run": days,
        "overdue": overdue,
        "runs": [_run_as_json(run) for run in recorded],
        "parses_owed": owed,
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
            caption=_caption(history, days, overdue)
            + _parse_sentence(records[0] if records else None)
            + (f" {owed_sentence}" if owed_sentence else ""),
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
        outcome_shown(record, run.details),
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
    body["banner"] = _banner(run)
    return body


NOT_RECORDED: Final = "not recorded"
"""A run with no details beside its record: a build before `v1-e34-t19` recorded it."""

NONE: Final = "none"


def _verdict(run: RecordedRun) -> str | None:
    """`retry` or `person` for a run that failed, by the command's rule for exit `3`; else `None`."""
    if run.details is None or not run.details.failure_codes:
        return None
    return "retry" if codes_exit_as_a_retrieval_failure(run.details.failure_codes) else "person"


def _banner(run: RecordedRun) -> str | None:
    """`skipped` or `retry once fixed`, the words the run's banner put beside its verdict; else `None`."""
    return banner_words(run.record, run.details, may_succeed_on_retry=codes_exit_as_a_retrieval_failure)


def _failed_on_and_verdict(run: RecordedRun) -> tuple[str, str]:
    """The table's two cells: the codes the exit was decided from, and the verdict on them, with the
    banner's own words beside it in brackets when it had some (`v1-e34-t26`)."""
    if run.details is None:
        return NOT_RECORDED, NOT_RECORDED
    codes = run.details.failure_codes
    verdict = _verdict(run) or NONE
    words = _banner(run)
    return (", ".join(codes) or NONE), (f"{verdict} ({words})" if words else verdict)


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
