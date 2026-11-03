"""`debate-research caselist move-run-home`: dev's run lock held for good when the weekly run moves to prod.

::

    debate-research caselist move-run-home                      # the dry run: the lock, and what it would get
    debate-research caselist move-run-home --execute            # take the lock, then hold it for good
    debate-research caselist move-run-home --release            # the release's dry run
    debate-research caselist move-run-home --release --execute  # the lock back to dev, free

ADR-0020 (7) step 3, at the pilot's promotion (`v1-e40-t11`), after prod's lock is seeded: dev's
lock is rewritten held for good by a holder of kind `moved` naming `home_environment: prod`, so that
every dev command that would take it is refused, saying the weekly run now runs from prod. The
release is for a move made by mistake, and the runbook allows it only after the coach confirms. What
each does is :mod:`debate_core.application.caselist.run_home_move`'s. Without `--execute` nothing is
written anywhere. Dev only: in prod both refuse before reading anything.

Exit `0` when the dry run may be carried out, or the write was made; `1` when it is refused, with
nothing written.
"""

from __future__ import annotations

import json
from typing import Annotated

import typer

from debate_cli.context import CliContext, cli_context, command_name
from debate_cli.exit_codes import ExitCode
from debate_cli.options.bucket_environment import SYNCABLE_ENVIRONMENTS
from debate_cli.output import CommandFailure, JsonValue, TableSpec
from debate_core.application.caselist.run_home_move import RunHomeMoveReport
from debate_core.application.caselist.run_lock import RUN_LOCK_KEY, LockBody
from debate_core.application.settings import RunStateMode, Settings

__all__ = ["move_run_home", "move_summary"]


def move_run_home(
    ctx: typer.Context,
    execute: Annotated[
        bool, typer.Option("--execute", help="Write the lock. Without it, a dry run that writes nothing.")
    ] = False,
    release: Annotated[
        bool,
        typer.Option(
            "--release",
            help="Undo a move: the lock back to this environment, free. Only after the coach confirms.",
        ),
    ] = False,
) -> None:
    """Hold this environment's run lock for good when the weekly run's home moves to prod, or release it."""
    cli = cli_context(ctx)
    settings = cli.services.settings
    _refuse(cli, ctx, _guard(settings))
    move = cli.services.run_home_move()
    if release:
        report = move.release() if execute else move.plan_release()
    else:
        report = move.move() if execute else move.plan()
    cli.output.success(command_name(ctx), move_summary(report, settings), display=_table(report))


def _guard(settings: Settings) -> CommandFailure | None:
    """Dev or prod with a bucket, in bucket mode. Prod is refused by the move itself."""
    if settings.environment not in SYNCABLE_ENVIRONMENTS or not settings.storage.s3.bucket:
        return CommandFailure(
            code="EVIDENCE_STORE_NOT_CONFIGURED",
            message=f"`caselist move-run-home` writes dev's run lock, not {settings.environment.value}'s",
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"environment": settings.environment.value},
            hint="Set DEBATE_ENV=dev and try again.",
        )
    if settings.caselist.run_state is not RunStateMode.BUCKET:
        return CommandFailure(
            code="RUN_STATE_IS_LOCAL",
            message=(
                "this machine keeps its run state locally (caselist.run_state = local), and the lock is "
                "the bucket's"
            ),
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"environment": settings.environment.value},
            hint="Use a build whose profile sets caselist.run_state = bucket, as the cutover runbook says.",
        )
    return None


def _refuse(cli: CliContext, ctx: typer.Context, refusal: CommandFailure | None) -> None:
    if refusal is None:
        return
    cli.output.failure(refusal, command=command_name(ctx))
    raise typer.Exit(code=refusal.exit_code)


# ------------------------------------------------------------------------------------------------
# Rendering: the lock's bodies, which hold run ids, commands, times and a build tag only
# ------------------------------------------------------------------------------------------------


def move_summary(report: RunHomeMoveReport, settings: Settings) -> dict[str, JsonValue]:
    """The `--json` envelope's `data`."""
    return {
        "environment": settings.environment.value,
        "bucket": settings.storage.s3.bucket,
        "lock_key": RUN_LOCK_KEY,
        "release": report.release,
        "applied": report.applied,
        "found": _as_json(report.found),
        "written": _as_json(report.written),
    }


def _as_json(body: LockBody) -> JsonValue:
    parsed: JsonValue = json.loads(body.as_bytes())
    return parsed


def _described(body: LockBody) -> str:
    holder = f", held by {body.holder.described()}" if body.holder is not None else ""
    return f"{body.state}, home {body.home_environment}{holder}"


def _table(report: RunHomeMoveReport) -> TableSpec:
    if report.applied:
        caption = (
            "Released: the lock is free and names this environment as the run's home again."
            if report.release
            else "Moved: the lock is held for good, and every command that takes it here is refused."
        )
    else:
        again = "--release --execute" if report.release else "--execute"
        caption = f"Nothing was written. Re-run with {again} to write it."
    return TableSpec(
        columns=("", RUN_LOCK_KEY),
        rows=[
            ["Found", _described(report.found)],
            ["Written" if report.applied else "Would write", _described(report.written)],
        ],
        title="caselist move-run-home"
        + (" --release" if report.release else "")
        + ("" if report.applied else " (dry run)"),
        caption=caption,
    )
