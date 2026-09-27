"""`debate-research caselist pull`: the weekly run, by hand or on the launchd schedule.

One command, three shapes::

    debate-research caselist pull --caselist hsld26 --caselist hspolicy26
    debate-research caselist pull --caselist hsld26 --dry-run     # list only, write nothing
    debate-research caselist pull --publish-pending               # after `aws sso login`

Every decision in it belongs to
:class:`~debate_core.application.caselist_sync.CaselistSyncService`: which archives are new, what
the day's five bulk downloads are spent on, what a `Retry-After` of a day means, which stages are
optional, and what happens when the AWS session has expired. What is here is the command-line
surface — which flags mean what, which caselists are pulled when none are named, and how a run is
rendered for a person and for a program.

## Which caselists

`--caselist`, repeatable, or `caselist.sync_caselists` in the environment's profile when the flag
is not given. There is no default list: which caselists this installation follows is the
operator's decision, and a slug hardcoded in a committed file would make it ours.

## The schedule is weekly

`docs/policies/caselist-data-use.md` E34 gate 4 permits weekly cadence at most, agreed with the
OpenCaselist maintainer. This command does the work of one weekly run and nothing in it is a
loop; `ops/launchd/` is what runs it once a week, and installing that is a deliberate operator
step (`docs/runbooks/caselist-scheduled-sync.md`).

## Exit codes

From :mod:`debate_cli.exit_codes`. `0` when every stage that puts bytes somewhere durable
finished — including a run that found nothing new, and a run whose publish is pending because the
SSO session expired, because in both cases nothing was lost and the next run continues. `1` when
a download, an import or a publish failed, or when a guard refused to start: an expired
OpenCaselist token, an API this installation has not turned on, no caselist to pull, or another
run already holding the lock. A parse or landscape stage that failed is reported in the table and
does not change the exit code — the captured bytes are safe and the derivation can be recomputed.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Annotated, Any, cast

import typer

from debate_cli.commands.caselist import event_for_caselist
from debate_cli.context import cli_context, command_name
from debate_cli.exit_codes import ExitCode
from debate_cli.output import CommandFailure, JsonValue, TableSpec
from debate_core.application.caselist_sync import (
    CaselistSyncService,
    NoCaselistsConfigured,
    RunSummary,
    StageOutcome,
    SyncStage,
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
) -> None:
    """Download, import and publish this week's caselist archives and OpenEv files."""
    cli = cli_context(ctx)
    settings = cli.services.settings
    if publish_pending and dry_run:
        raise ConflictingPullMode
    slugs = [] if publish_pending else list(caselist) if caselist else list(settings.caselist.sync_caselists)

    def sync_service() -> CaselistSyncService:
        return cli.services.caselist_sync(event_for_caselist=event_for_caselist)

    record: SyncRunRecord | None = None
    if dry_run:
        # A dry run writes nothing (v1-e34-t02 ac2), so it leaves no run record either.
        if not slugs:
            raise NoCaselistsConfigured
        cli.output.detail(f"pulling {', '.join(slugs)} (dry run)")
        summary = _run(sync_service().run(slugs, dry_run=True))
    else:

        async def one_run() -> RunSummary:
            # Inside the monitor, so that a refusal — no caselist, the API not turned on, an
            # expired token, another run holding the lock — is recorded and announced too.
            if publish_pending:
                cli.output.detail("completing the publishes an earlier run deferred")
                return await sync_service().publish_pending()
            if not slugs:
                raise NoCaselistsConfigured
            cli.output.detail(f"pulling {', '.join(slugs)}")
            return await sync_service().run(slugs)

        monitored = _run(
            cli.services.caselist_sync_monitor().watch(
                one_run, caselists=slugs, mode="publish_pending" if publish_pending else "run"
            )
        )
        summary, record = monitored.summary, monitored.record

    written_to = sync_service().summary_path(summary) if not summary.dry_run else None
    payload = pull_summary(summary, settings, written_to, record)
    display = _pull_table(summary, settings, record)
    if summary.succeeded:
        cli.output.success(command_name(ctx), payload, display=display)
        return
    if not cli.output.is_json:
        cli.output.success(command_name(ctx), payload, display=display)
    cli.output.failure(_pull_failure(summary, payload), command=command_name(ctx))
    raise typer.Exit(code=ExitCode.DOMAIN_FAILURE)


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
    if summary.dry_run:
        wanted = sum(1 for one in summary.archives if one.wanted)
        camp = sum(1 for one in summary.openev if one.wanted)
        over_cap = f" ({deferred} more wanted, over today's download cap)" if deferred else ""
        return (
            f"{summary.archives_seen} archive(s) listed; would download {wanted} archive(s){over_cap} "
            f"and {camp} OpenEv file(s). Nothing was written. Re-run without --dry-run to do it."
        )
    if summary.nothing_new:
        return (
            f"Nothing new: {summary.archives_seen} archive(s) listed, none newer than what this "
            f"machine already holds. {summary.duration_seconds:.1f}s."
        )
    if deferred and summary.archives_downloaded == 0 and summary.openev_downloaded == 0:
        return (
            f"Nothing fetched: {summary.archives_wanted} archive(s) wanted and all {deferred} deferred "
            f"by the daily download cap; a later run fetches them.{backlog} "
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
        f"{summary.objects_published} object(s) published{pending}.{waiting}{backlog} "
        f"{summary.duration_seconds:.1f}s."
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
    """What an incomplete run exits `1` with: the stages that failed, and the whole summary."""
    failed = [record for record in summary.stages if record.outcome is StageOutcome.FAILED]
    named = "; ".join(f"{record.stage}: {record.reason}" for record in failed)
    return CommandFailure(
        code="CASELIST_PULL_INCOMPLETE",
        message=f"{len(failed)} stage(s) of the caselist pull did not complete — {named}",
        exit_code=ExitCode.DOMAIN_FAILURE,
        details=payload,
        hint=_hint_for(failed),
    )


def _hint_for(failed: list[Any]) -> str:
    stages = {record.stage for record in failed}
    if SyncStage.DOWNLOAD in stages:
        return (
            "Nothing that did download was lost: it is in the inbox and imported. Run the same "
            "command again — an archive already held is not fetched twice."
        )
    if SyncStage.PUBLISH in stages:
        return "Re-run `caselist pull --publish-pending`: every confirmed source is skipped."
    return "Run the same command again; every stage is idempotent."


def _run[T](awaitable: Coroutine[Any, Any, T]) -> T:
    """Run one coroutine to completion; a CLI command is the one caller with no loop of its own."""
    return asyncio.run(awaitable)
