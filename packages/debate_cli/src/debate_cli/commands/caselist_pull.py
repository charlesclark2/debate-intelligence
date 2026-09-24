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
    NoCaselistsConfigured,
    RunSummary,
    StageOutcome,
    SyncStage,
)
from debate_core.application.settings import Settings

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
    service = cli.services.caselist_sync(event_for_caselist=event_for_caselist)

    if publish_pending:
        cli.output.detail("completing the publishes an earlier run deferred")
        summary = _run(service.publish_pending())
    else:
        slugs = list(caselist) if caselist else list(settings.caselist.sync_caselists)
        if not slugs:
            raise NoCaselistsConfigured
        cli.output.detail(f"pulling {', '.join(slugs)}" + (" (dry run)" if dry_run else ""))
        summary = _run(service.run(slugs, dry_run=dry_run))

    payload = pull_summary(summary, settings, service.summary_path(summary) if not summary.dry_run else None)
    display = _pull_table(summary, settings)
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


def pull_summary(summary: RunSummary, settings: Settings, written_to: Any = None) -> dict[str, JsonValue]:
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
    return body


def _pull_table(summary: RunSummary, settings: Settings) -> TableSpec:
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
        caption=_caption(summary),
    )


def _caption(summary: RunSummary) -> str:
    """The numbers an operator checks the week against, in the one line under the table."""
    if summary.dry_run:
        wanted = sum(1 for one in summary.archives if one.wanted)
        camp = sum(1 for one in summary.openev if one.wanted)
        return (
            f"{summary.archives_seen} archive(s) listed; would download {wanted} archive(s) and "
            f"{camp} OpenEv file(s). Nothing was written. Re-run without --dry-run to do it."
        )
    if summary.nothing_new:
        return (
            f"Nothing new: {summary.archives_seen} archive(s) listed, none newer than what this "
            f"machine already holds. {summary.duration_seconds:.1f}s."
        )
    pending = (
        f", {len(summary.pending_publish)} snapshot(s) pending publish" if summary.pending_publish else ""
    )
    return (
        f"{summary.archives_downloaded} archive(s) and {summary.openev_downloaded} OpenEv file(s) "
        f"downloaded; {summary.files_imported} file(s) imported, {summary.blobs_stored} new; "
        f"{summary.objects_published} object(s) published{pending}. "
        f"{summary.duration_seconds:.1f}s."
    )


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
