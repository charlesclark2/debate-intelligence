"""`debate-research caselist restore-run-state`: the run's working copy, restored into a directory of its own.

::

    debate-research caselist restore-run-state --into ~/.debate-research/dev-copy-2026-10-29
    debate-research caselist restore-run-state --into ~/prod-copy --with-sources --snapshot 2026-11-04

For the cutover's comparison and for a hand publish to prod from a copy restored under the dev lock
(`v1-e40-t06`; ADR-0020 (4) and (7)). `--with-sources` (`v1-e40-t10`) also fetches, under the same lock
and into the same directory, the raw sources the restored manifests name, or only those of the
`--caselist` and `--snapshot` named: what that publish needs. It says how many sources and bytes before
the first fetch, refuses a disk without room for them, and stops non-zero when one is missing from the
bucket or arrives with another digest (:mod:`debate_core.application.caselist.run_state_sources`).

Bucket mode only: it holds the bucket's run lock while it restores, so no runner is part-way through its
week, and it writes nothing to the bucket but the lock.
Everything else it writes is under the directory named, which must be new or empty and is never this
environment's data directory. What it restores, and what it refuses, is
:mod:`debate_core.application.caselist.run_state_restore`'s. In prod it also needs `--confirm-prod`,
because holding prod's lock would turn away a scheduled run.

Exit `0` when the copy is restored; `1` when it is refused or a runner holds the lock, with nothing
restored. With `--with-sources`, also `1` when a source is missing or mismatched, or there is no room
for them; the directory then holds a copy that is not complete, and the message says so.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from debate_cli.bucket_lock import run_holding_the_bucket_lock
from debate_cli.context import CliContext, cli_context, command_name
from debate_cli.exit_codes import ExitCode
from debate_cli.options.bucket_environment import CONFIRM_PROD_FLAG, SYNCABLE_ENVIRONMENTS
from debate_cli.output import CommandFailure, JsonValue, TableSpec
from debate_core.application.caselist.publish_plan import (
    OPENEV,
    InvalidPublishTarget,
    validate_publish_target,
)
from debate_core.application.caselist.run_state_restore import RESTORE_COMMAND, RestoredCopy
from debate_core.application.caselist.run_state_sources import SourceSelection, SourcesPlan
from debate_core.application.caselist_sync import NoCaselistsConfigured
from debate_core.application.errors import DomainError
from debate_core.application.settings import Environment, RunStateMode, Settings

__all__ = ["restore_run_state", "restore_summary"]


def restore_run_state(
    ctx: typer.Context,
    into: Annotated[
        Path,
        typer.Option(
            "--into", help="A new or empty directory to restore the copy into. Never the data directory."
        ),
    ],
    caselist: Annotated[
        list[str] | None,
        typer.Option(
            "--caselist",
            help="A caselist whose parsed store to restore; repeatable. Default: caselist.sync_caselists.",
        ),
    ] = None,
    with_sources: Annotated[
        bool,
        typer.Option(
            "--with-sources",
            help=(
                "Also fetch the raw sources the restored manifests name, each checked against its digest: "
                "what a hand publish from the copy needs."
            ),
        ),
    ] = False,
    snapshot: Annotated[
        list[str] | None,
        typer.Option(
            "--snapshot",
            help=(
                "With --with-sources, only the sources of this snapshot's manifests (of --caselist, when "
                "named); repeatable. Default: every restored manifest's."
            ),
        ),
    ] = None,
    confirm_prod: Annotated[
        bool, typer.Option(CONFIRM_PROD_FLAG, help="Required in the production environment.")
    ] = False,
) -> None:
    """Restore the run's working copy from this environment's bucket into a new directory, under its lock."""
    cli = cli_context(ctx)
    settings = cli.services.settings
    snapshots = list(snapshot or ())
    if snapshots and not with_sources:
        raise typer.BadParameter(
            "--snapshot narrows the sources --with-sources fetches", param_hint="--snapshot"
        )
    _refuse(cli, ctx, _guard(settings, confirmed=confirm_prod))
    slugs = list(caselist) if caselist else list(settings.caselist.sync_caselists)
    if not slugs:
        raise NoCaselistsConfigured
    _refuse_snapshot_names(snapshots, list(caselist) if caselist else [*slugs, OPENEV])
    sources = (
        SourceSelection(caselists=tuple(caselist or ()), snapshots=tuple(snapshots)) if with_sources else None
    )
    restore = cli.services.run_state_restore()
    refusal = restore.refusal(into)
    if refusal is not None:
        _refuse(cli, ctx, _refused(refusal, settings))
    try:
        copy = run_holding_the_bucket_lock(
            cli,
            RESTORE_COMMAND,
            lambda: restore.restore(
                into, slugs, sources=sources, on_sources_planned=lambda plan: _announce(cli, plan)
            ),
        )
    except DomainError:
        if sources is not None and into.expanduser().is_dir() and any(into.expanduser().iterdir()):
            cli.output.note(
                "The directory named holds what was restored before the stop, and is not a copy to publish "
                "from. Delete it before restoring again."
            )
        raise
    cli.output.success(command_name(ctx), restore_summary(copy, slugs, settings), display=_table(copy))


def _refuse_snapshot_names(snapshots: list[str], caselists: list[str]) -> None:
    """Each `--snapshot` must name a snapshot of one of `caselists`, before any lock or restore."""
    for name in snapshots:
        valid = False
        for slug in caselists:
            try:
                validate_publish_target(slug, name)
            except InvalidPublishTarget:
                continue
            valid = True
        if not valid:
            raise typer.BadParameter(
                "a snapshot is YYYY-MM-DD, full/YYYY-MM-DD, or <year>-<event> for openev, of a caselist "
                "restored",
                param_hint="--snapshot",
            )


def _announce(cli: CliContext, plan: SourcesPlan) -> None:
    """Before the first fetch: how many sources, and how many bytes. Counts only."""
    cli.output.note(
        f"Fetching {len(plan.to_fetch)} raw source(s), {plan.bytes_to_fetch} bytes, that "
        f"{plan.manifests} restored manifest(s) name; {plan.suppressed} skipped as the suppression list "
        "holds them."
    )


def _guard(settings: Settings, *, confirmed: bool) -> CommandFailure | None:
    """Dev or prod with a bucket, in bucket mode; prod needs --confirm-prod."""
    if settings.environment not in SYNCABLE_ENVIRONMENTS or not settings.storage.s3.bucket:
        return CommandFailure(
            code="EVIDENCE_STORE_NOT_CONFIGURED",
            message=f"`caselist restore-run-state` restores dev or prod, not {settings.environment.value}",
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"environment": settings.environment.value},
            hint="Set DEBATE_ENV=dev (or prod) and try again.",
        )
    if settings.caselist.run_state is not RunStateMode.BUCKET:
        return CommandFailure(
            code="RUN_STATE_IS_LOCAL",
            message=(
                "this machine keeps its run state locally (caselist.run_state = local), so the bucket holds "
                "no run state for it to restore"
            ),
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"environment": settings.environment.value},
            hint="A bucket the cutover has seeded is restored in bucket mode: caselist.run_state = bucket.",
        )
    if settings.environment is Environment.PROD and not confirmed:
        return CommandFailure(
            code="CONFIRMATION_REQUIRED",
            message=f"refusing to hold production's run lock without {CONFIRM_PROD_FLAG}",
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"environment": settings.environment.value},
            hint=f"Holding it turns a scheduled run away. Add {CONFIRM_PROD_FLAG} when none is due.",
        )
    return None


def _refused(reason: str, settings: Settings) -> CommandFailure:
    return CommandFailure(
        code="RESTORE_TARGET_REFUSED",
        message=f"nothing was restored, and the run lock was not taken: {reason}",
        exit_code=ExitCode.DOMAIN_FAILURE,
        details={"environment": settings.environment.value},
        hint="Name a new or empty directory outside the data directory, for example one beside it.",
    )


def _refuse(cli: CliContext, ctx: typer.Context, refusal: CommandFailure | None) -> None:
    if refusal is None:
        return
    cli.output.failure(refusal, command=command_name(ctx))
    raise typer.Exit(code=refusal.exit_code)


# ------------------------------------------------------------------------------------------------
# Rendering: counts and ids only, never the directory or a name
# ------------------------------------------------------------------------------------------------


def restore_summary(copy: RestoredCopy, caselists: list[str], settings: Settings) -> dict[str, JsonValue]:
    """The `--json` envelope's `data`."""
    report = copy.report
    return {
        "environment": settings.environment.value,
        "bucket": settings.storage.s3.bucket,
        "caselists": list(caselists),
        "manifests": copy.manifests,
        "state_files": list(report.state_files),
        "parsed_version": report.parsed_version,
        "parsed_objects": report.parsed_objects,
        "parsed_bytes": report.parsed_bytes,
        "index_id": report.index_id,
        "suppression_entries": copy.suppression_entries,
        "sources": _sources_summary(copy),
        "seconds": round((report.finished_at - report.started_at).total_seconds(), 1),
    }


def _sources_summary(copy: RestoredCopy) -> dict[str, JsonValue] | None:
    """`--with-sources`' counts; `None` without it."""
    fetched = copy.sources
    if fetched is None:
        return None
    return {
        "manifests": fetched.manifests,
        "named": fetched.named,
        "fetched": fetched.fetched,
        "fetched_bytes": fetched.fetched_bytes,
        "suppressed": fetched.suppressed,
    }


def _table(copy: RestoredCopy) -> TableSpec:
    report = copy.report
    rows = [
        ["Manifests and the database", f"{copy.manifests} manifest(s)"],
        ["State files", ", ".join(report.state_files) or "none in the bucket"],
        [
            "Parsed store",
            f"{report.parsed_version}: {report.parsed_objects} object(s), {report.parsed_bytes} bytes",
        ],
        ["Published index", f"{report.index_id}'s manifest" if report.index_id else "none published"],
        ["Suppression list", f"{copy.suppression_entries} entr(ies), as the bucket holds them"],
    ]
    if copy.sources is not None:
        fetched = copy.sources
        rows.append(
            [
                "Raw sources",
                f"{fetched.fetched} fetched, {fetched.fetched_bytes} bytes, each checked against its digest; "
                f"{fetched.suppressed} skipped as the suppression list holds them",
            ]
        )
    return TableSpec(
        columns=("Restored", ""),
        rows=rows,
        title="caselist restore-run-state",
        caption=(
            f"Restored under the lock in {(report.finished_at - report.started_at).total_seconds():.1f}s; "
            "the lock is released. "
            + (
                "The raw sources the manifests name are in the copy."
                if copy.sources is not None
                else "Raw sources are fetched from the bucket as a parse in the copy needs them."
            )
        ),
    )
