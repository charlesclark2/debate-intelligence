"""`debate-research caselist pull`: the weekly run, by hand or on the launchd schedule.

One command, three shapes::

    debate-research caselist pull --caselist hsld26 --caselist hspolicy26
    debate-research caselist pull --caselist hsld26 --dry-run     # list only, write nothing
    debate-research caselist pull --publish-pending               # after `aws sso login`
    debate-research caselist pull --full-archive hsld26           # one complete archive, on demand

Every decision in it belongs to
:class:`~debate_core.application.caselist_sync.CaselistSyncService`, and which of the three a run
is to :func:`~debate_core.application.caselist_sync.run_pull`: which archives are new, what
the day's five bulk downloads are spent on, what a `Retry-After` of a day means, which stages are
optional, and what happens when the AWS session has expired. What is here is the command-line
surface — which flags mean what, which caselists are pulled when none are named, and how a run is
rendered for a person and for a program.

## Which caselists

`--caselist`, repeatable, or `caselist.sync_caselists` in the environment's profile when the flag
is not given. There is no default list: which caselists this installation follows is the
operator's decision, and a slug hardcoded in a committed file would make it ours.

## The complete archive

The weekly run refreshes at most one caselist's complete archive (`<slug>-all-<date>.zip`) on a
rotation, after its weeklies and only from the bulk downloads they leave (`v1-e34-t04`; see
:mod:`debate_core.application.caselist_sync`, "The complete archive"). `--full-archive <slug>`
takes that one slot for the named caselist whatever the rotation says, still after the weeklies,
and the run refuses — exit `1`, nothing fetched — when the day's allowance cannot cover it. With
`--dry-run` it reports what would happen, refusal included, and fetches nothing. The caption says
what the rotation decided, every run.

## The schedule is weekly

`docs/policies/caselist-data-use.md` E34 gate 4 permits weekly cadence at most, agreed with the
OpenCaselist maintainer. This command does the work of one weekly run and nothing in it is a
loop; `ops/launchd/` is what runs it once a week, and installing that is a deliberate operator
step (`docs/runbooks/caselist-scheduled-sync.md`).

## Exit codes

From :mod:`debate_cli.exit_codes`. `0` when every stage that puts bytes somewhere durable
finished — including a run that found nothing new, and a run whose publish is pending because the
SSO session expired, because in both cases nothing was lost and the next run continues. A parse,
landscape, report or retention stage that failed is reported in the table and does not change the
exit code — the captured bytes are safe and the rest can be recomputed.

When a download, an import or a publish failed, the exit code comes from **what they failed on**
(`v1-e34-t13`). Each failed stage records the error code of every failure behind it, and
:func:`~debate_cli.exit_codes.exit_code_for_failure_codes` reads those of the stages that had to
finish:

* `3` when every one is a failure a retry may cure: the bucket or this machine's store did not
  answer or refused (`STORE_UNAVAILABLE`, `STORE_ACCESS_DENIED`), or an OpenCaselist download got a
  5xx, a timeout, or a rate limit that is not the daily cap (`PROVIDER_UNAVAILABLE`,
  `PROVIDER_RATE_LIMITED`). Nothing captured is lost and the snapshots not yet published stay owed,
  so the next run, or the same command, finishes the job.
* `1` as soon as one is a verdict: an archive that cannot be read or is over the size ceiling, one
  the file host no longer serves, an expired OpenCaselist token (never retried, by policy), the
  site's daily download cap on a camp file, a checksum mismatch. So is any failure with a code
  nobody put on the retryable list.

`1` also when a guard refused to start: an expired OpenCaselist token, an API this installation has
not turned on, no caselist to pull, another run already holding the lock, or a `--full-archive` the
day's allowance cannot cover. A failure that ends the run before any stage records it exits as that
exception does in every other command: `3` for a store or provider failure (`v1-e01-t20`).

The envelope's `error.code` for a failed stage is `CASELIST_PULL_INCOMPLETE` whichever it is; the
exit status and each stage's `error_codes` say which.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Annotated, Any, cast

import typer

from debate_cli.commands.caselist import event_for_caselist
from debate_cli.context import cli_context, command_name
from debate_cli.exit_codes import ExitCode, exit_code_for_failure_codes
from debate_cli.output import CommandFailure, JsonValue, TableSpec
from debate_core.application.caselist_sync import (
    RunSummary,
    StageOutcome,
    StageRecord,
    SyncStage,
    run_pull,
)
from debate_core.application.settings import Settings
from debate_core.application.sync_runs import SyncRunRecord

__all__ = ["pull", "pull_summary"]


def pull(
    ctx: typer.Context,
    caselist: Annotated[
        list[str] | None,
        typer.Option(
            "--caselist",
            help="Caselist slug to pull; repeat for more. Default: caselist.sync_caselists.",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="List what would be downloaded and processed; write nothing."),
    ] = False,
    publish_pending: Annotated[
        bool,
        typer.Option(
            "--publish-pending",
            help="Only complete the publishes an earlier run deferred, and exit.",
        ),
    ] = False,
    full_archive: Annotated[
        str | None,
        typer.Option(
            "--full-archive",
            metavar="SLUG",
            help=(
                "Also fetch this caselist's complete archive (<slug>-all-<date>.zip) now, outside the "
                "rotation, after the run's weeklies and from the same daily allowance; refused, "
                "fetching nothing, when the allowance cannot cover it."
            ),
        ),
    ] = None,
) -> None:
    """Download, import and publish this week's caselist archives and OpenEv files."""
    cli = cli_context(ctx)
    settings = cli.services.settings
    if publish_pending and dry_run:
        raise ConflictingPullMode
    if publish_pending and full_archive is not None:
        raise typer.BadParameter(
            "--publish-pending fetches nothing, so it cannot fetch a complete archive; pass one or the other",
            param_hint="--full-archive",
        )
    slugs = [] if publish_pending else list(caselist) if caselist else list(settings.caselist.sync_caselists)

    pulled = _run(
        run_pull(
            lambda: cli.services.caselist_sync(event_for_caselist=event_for_caselist),
            slugs,
            dry_run=dry_run,
            publish_pending=publish_pending,
            monitor=cli.services.caselist_sync_monitor,
            progress=cli.output.detail,
            full_archive=full_archive,
        )
    )
    summary = pulled.summary
    payload = pull_summary(summary, settings, pulled.summary_path, pulled.record)
    display = _pull_table(summary, settings, pulled.record)
    if summary.succeeded:
        cli.output.success(command_name(ctx), payload, display=display)
        return
    if not cli.output.is_json:
        cli.output.success(command_name(ctx), payload, display=display)
    failure = _pull_failure(summary, payload)
    cli.output.failure(failure, command=command_name(ctx))
    raise typer.Exit(code=failure.exit_code)


class ConflictingPullMode(typer.BadParameter):
    """`--dry-run` and `--publish-pending` ask for opposite things."""

    def __init__(self) -> None:
        super().__init__(
            "--publish-pending completes work an earlier run deferred, so there is nothing for "
            "--dry-run to rehearse; pass one or the other"
        )


# ------------------------------------------------------------------------------------------------
# Rendering
# ------------------------------------------------------------------------------------------------


def pull_summary(
    summary: RunSummary, settings: Settings, written_to: Any = None, record: SyncRunRecord | None = None
) -> dict[str, JsonValue]:
    """The `--json` envelope's `data`: the run summary, plus where it was written.

    The run summary itself is
    :meth:`~debate_core.application.caselist_sync.RunSummary.as_json` unchanged, so the object a
    monitoring check reads out of `<data_dir>/caselist-sync-runs/` and the object this command
    prints are the same shape. `v1-e34-t03`'s run log reads one or the other and never both.
    """
    # `as_json` is declared `dict[str, object]` because `debate_core` may not name the CLI's
    # JSON alias; every value in it is a number, a string, a bool, `None` or a list of those.
    body = cast("dict[str, JsonValue]", dict(summary.as_json()))
    body["environment"] = settings.environment.value
    body["bucket"] = settings.storage.s3.bucket
    body["summary_written_to"] = str(written_to) if written_to is not None else None
    # The run log's record of this run (v1-e34-t03), or `None` for a dry run, which records nothing.
    body["run_record"] = cast("JsonValue", record.model_dump(mode="json")) if record is not None else None
    return body


def _pull_table(summary: RunSummary, settings: Settings, record: SyncRunRecord | None = None) -> TableSpec:
    """One row per stage: what it was asked to do, what happened, and the sentence that says why."""
    rows = [[str(record.stage), str(record.outcome), record.reason or ""] for record in summary.stages]
    kind = "dry run" if summary.dry_run else "run"
    return TableSpec(
        columns=("Stage", "Outcome", "Detail"),
        rows=rows,
        title=(
            f"caselist pull {kind} {summary.run_id} "
            f"({', '.join(summary.caselists) or 'pending publishes'}, {settings.environment.value})"
        ),
        caption=_caption(summary, record),
    )


def _caption(summary: RunSummary, record: SyncRunRecord | None = None) -> str:
    """The numbers an operator checks the week against, in the one line under the table.

    Whenever the daily cap deferred anything, the caption says how many archives were wanted and
    how many are waiting, so a truncated week never reads like a clean one (v1-e34-t03 ac5, ac6).
    """
    deferred = summary.archives_deferred
    backlog = _backlog_sentence(record)
    inbox = _full_archive_sentence(summary) + _inbox_sentence(summary)
    if summary.dry_run:
        wanted = sum(1 for one in summary.archives if one.wanted)
        camp = sum(1 for one in summary.openev if one.wanted)
        over_cap = f" ({deferred} more wanted, over the 24-hour download cap)" if deferred else ""
        return (
            f"{summary.archives_seen} archive(s) listed; would download {wanted} archive(s){over_cap} "
            f"and {camp} OpenEv file(s).{inbox} Nothing was written. Re-run without --dry-run to do it."
        )
    if summary.nothing_new:
        return (
            f"Nothing new: {summary.archives_seen} archive(s) listed, none newer than what this "
            f"machine already holds.{inbox} {summary.duration_seconds:.1f}s."
        )
    if deferred and summary.archives_downloaded == 0 and summary.openev_downloaded == 0:
        return (
            f"Nothing fetched: {summary.archives_wanted} archive(s) wanted and all {deferred} deferred "
            f"by the daily download cap; a later run fetches them.{backlog}{inbox} "
            f"{summary.duration_seconds:.1f}s."
        )
    pending = (
        f", {len(summary.pending_publish)} snapshot(s) pending publish" if summary.pending_publish else ""
    )
    archives = (
        f"{summary.archives_downloaded} of {summary.archives_wanted} wanted archive(s)"
        if deferred
        else f"{summary.archives_downloaded} archive(s)"
    )
    waiting = (
        f" {deferred} archive(s) deferred by the daily download cap wait for a later run." if deferred else ""
    )
    return (
        f"{archives} and {summary.openev_downloaded} OpenEv file(s) "
        f"downloaded; {summary.files_imported} file(s) imported, {summary.blobs_stored} new; "
        f"{summary.objects_published} object(s) published{pending}.{waiting}{backlog}{inbox} "
        f"{summary.duration_seconds:.1f}s."
    )


def _full_archive_sentence(summary: RunSummary) -> str:
    """What the complete-archive rotation decided, as a leading-space sentence (`v1-e34-t04`).

    The select row of the table carries the whole reason, each caselist's state included; this is
    the headline, and the allowance the weeklies left, which a dry run before `--full-archive` is
    run to read.
    """
    plan = summary.full_archive
    if plan is None:
        return ""
    left = f"{plan.allowance_after_weeklies} bulk download(s) left after the weeklies"
    withdrawn = "".join(
        f" {one.caselist} {one.snapshot}: {one.withdrawn} withdrawn, {one.superseded} superseded."
        for one in summary.full_archive_imports
    )
    verb = "would be fetched" if summary.dry_run else "fetched"
    if plan.fetch is not None:
        return f" Complete archive: {plan.fetch}'s {verb}; {left}.{withdrawn}"
    if plan.first_in_turn is not None:
        return f" Complete archive: none {verb}; {plan.first_in_turn} is first in turn but {left}.{withdrawn}"
    if not plan.rotation and plan.requested is None:
        return f" Complete archive: the rotation is off; {left}.{withdrawn}"
    return f" Complete archive: none due; {left}.{withdrawn}"


def _inbox_sentence(summary: RunSummary) -> str:
    """What the retention stage did to the inbox, as a leading-space sentence (`v1-e34-t11`).

    Counts and bytes only; the retention row of the table names every file and why each kept one
    stays.
    """
    retention = summary.inbox_retention
    if retention is None:
        return ""
    kept = f", {len(retention.kept)} kept" if retention.kept else ""
    if retention.dry_run:
        later = len(retention.once_imported) + retention.camp_downloads_once_imported
        also = (
            f", and {later} more once this run has imported them and the bucket confirms them"
            if later
            else ""
        )
        would = f"would remove {len(retention.removed)} file(s) ({retention.bytes_freed} bytes)"
        return f" Inbox: {would}{kept}{also}."
    failed = f", {len(retention.failed)} could not be removed" if retention.failed else ""
    return (
        f" Inbox: {len(retention.removed)} file(s) removed ({retention.bytes_freed} bytes freed)"
        f"{kept}{failed}."
    )


def _backlog_sentence(record: SyncRunRecord | None) -> str:
    """What the previous run left to the cap, when it left anything, as a leading-space sentence."""
    if record is None or not record.backlog_carried:
        return ""
    growing = (
        f" It has grown for two runs in a row ({', '.join(record.backlog_growing)})."
        if record.backlog_growing
        else ""
    )
    return f" Carried from the previous run: {record.backlog_carried} deferred.{growing}"


def _pull_failure(summary: RunSummary, payload: dict[str, JsonValue]) -> CommandFailure:
    """What an incomplete run reports: the stages that failed, and the whole summary.

    Its exit code is `3` when every failure behind a stage that had to finish is one a retry may
    cure, and `1` as soon as one is not (:attr:`RunSummary.failure_codes`,
    :func:`~debate_cli.exit_codes.exit_code_for_failure_codes`, `v1-e34-t13`).
    """
    failed = [record for record in summary.stages if record.outcome is StageOutcome.FAILED]
    named = "; ".join(f"{record.stage}: {record.reason}" for record in failed)
    exit_code = exit_code_for_failure_codes(summary.failure_codes)
    return CommandFailure(
        code="CASELIST_PULL_INCOMPLETE",
        message=f"{len(failed)} stage(s) of the caselist pull did not complete — {named}",
        exit_code=exit_code,
        details=payload,
        hint=_hint_for(failed, retryable=exit_code is ExitCode.RETRIEVAL_FAILURE),
    )


def _hint_for(failed: list[StageRecord], *, retryable: bool) -> str:
    """What to do about the failed stages: the fix a stage names, or else how to run it again.

    A stage a store refused carries its own fix, a permission on this machine or a grant the AWS
    profile lacks, and that comes first: running the command again before it is made changes
    nothing.
    """
    fixes = list(dict.fromkeys(record.hint for record in failed if record.hint))
    if fixes:
        return " ".join(fixes) + " Then run the same command again: what was captured is kept."
    stages = {record.stage for record in failed}
    again = (
        "Transient: every failure here is one a later run may not meet, and the next scheduled run "
        "retries it. "
        if retryable
        else ""
    )
    if SyncStage.DOWNLOAD in stages:
        return (
            f"{again}Nothing that did download was lost: it is in the inbox and imported. Run the same "
            "command again — an archive already held is not fetched twice."
        )
    if SyncStage.PUBLISH in stages:
        return f"{again}Re-run `caselist pull --publish-pending`: every confirmed source is skipped."
    return f"{again}Run the same command again; every stage is idempotent."


def _run[T](awaitable: Coroutine[Any, Any, T]) -> T:
    """Run one coroutine to completion; a CLI command is the one caller with no loop of its own."""
    return asyncio.run(awaitable)
