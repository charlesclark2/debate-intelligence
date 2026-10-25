"""`debate-research caselist seed-run-state`: a bucket's run lock created, this machine's run state uploaded.

::

    debate-research caselist seed-run-state              # the plan: what would be uploaded, or why not
    debate-research caselist seed-run-state --execute    # create the lock, upload, check back, release

Run once per home environment, by the operator, at the cutover (`v1-e40-t06`), after the Mac's
agent is unloaded and with `caselist.run_state = "bucket"` set (ADR-0020 (4), cutover step 4; the
PM's rulings on the plan, 2026-10-24). What the seed checks and does is
:mod:`debate_core.application.caselist.run_state_seed`'s. Without `--execute` it writes nothing
anywhere. In prod `--execute` also needs `--confirm-prod`.

Exit `0` when the plan may be carried out, or was; `1` when it is refused, with nothing written.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from debate_cli.commands.store import CONFIRM_PROD_FLAG, SYNCABLE_ENVIRONMENTS
from debate_cli.context import CliContext, cli_context, command_name
from debate_cli.exit_codes import ExitCode
from debate_cli.output import CommandFailure, JsonValue, TableSpec
from debate_core.application.caselist.run_state import RUN_STATE_BUNDLE_KEY, STATE_FILES, state_key
from debate_core.application.caselist.run_state_seed import SeedPlan, SeedReport
from debate_core.application.settings import Environment, RunStateMode, Settings

__all__ = ["seed_run_state", "seed_summary"]


def seed_run_state(
    ctx: typer.Context,
    execute: Annotated[
        bool, typer.Option("--execute", help="Seed the bucket. Without it, a dry run that writes nothing.")
    ] = False,
    confirm_prod: Annotated[
        bool, typer.Option(CONFIRM_PROD_FLAG, help="Required with --execute in the production environment.")
    ] = False,
) -> None:
    """Create this environment's bucket run lock and upload this machine's run state, once."""
    cli = cli_context(ctx)
    settings = cli.services.settings
    _refuse(cli, ctx, _guard(settings, execute=execute, confirmed=confirm_prod))
    seed = cli.services.run_state_seed()
    plan = asyncio.run(seed.plan())
    if plan.refusal is not None:
        _refuse(cli, ctx, _refused(plan.refusal, plan, settings))
    report = asyncio.run(seed.execute()) if execute else None
    cli.output.success(command_name(ctx), seed_summary(plan, report, settings), display=_table(plan, report))


def _guard(settings: Settings, *, execute: bool, confirmed: bool) -> CommandFailure | None:
    """Dev or prod with a bucket, in bucket mode; prod's --execute needs --confirm-prod."""
    if settings.environment not in SYNCABLE_ENVIRONMENTS or not settings.storage.s3.bucket:
        return CommandFailure(
            code="EVIDENCE_STORE_NOT_CONFIGURED",
            message=f"`caselist seed-run-state` seeds dev or prod, not {settings.environment.value}",
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"environment": settings.environment.value},
            hint="Set DEBATE_ENV=dev (or prod) and try again.",
        )
    if settings.caselist.run_state is not RunStateMode.BUCKET:
        return CommandFailure(
            code="RUN_STATE_IS_LOCAL",
            message="this machine keeps its run state locally (caselist.run_state = local): a seed is not",
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"environment": settings.environment.value},
            hint="Set DEBATE_CASELIST__RUN_STATE=bucket for the seed, as the cutover runbook says.",
        )
    if execute and settings.environment is Environment.PROD and not confirmed:
        return CommandFailure(
            code="CONFIRMATION_REQUIRED",
            message=f"refusing to seed production's bucket without {CONFIRM_PROD_FLAG}",
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"environment": settings.environment.value},
            hint=f"Run it without --execute first and read the plan, then add --execute {CONFIRM_PROD_FLAG}.",
        )
    return None


def _refused(reason: str, plan: SeedPlan, settings: Settings) -> CommandFailure:
    return CommandFailure(
        code="SEED_REFUSED",
        message=f"the bucket was not seeded, and nothing was written to it: {reason}",
        exit_code=ExitCode.DOMAIN_FAILURE,
        details={
            "environment": settings.environment.value,
            "seeded_already": plan.seeded_already,
            "unconfirmed_manifests": len(plan.unconfirmed),
        },
        hint="Nothing was changed. Fix what the message names and run the dry run again.",
    )


def _refuse(cli: CliContext, ctx: typer.Context, refusal: CommandFailure | None) -> None:
    if refusal is None:
        return
    cli.output.failure(refusal, command=command_name(ctx))
    raise typer.Exit(code=refusal.exit_code)


# ------------------------------------------------------------------------------------------------
# Rendering: keys and counts only
# ------------------------------------------------------------------------------------------------


def seed_summary(plan: SeedPlan, report: SeedReport | None, settings: Settings) -> dict[str, JsonValue]:
    """The `--json` envelope's `data`."""
    return {
        "environment": settings.environment.value,
        "bucket": settings.storage.s3.bucket,
        "applied": report is not None,
        "seeded_already": plan.seeded_already,
        "manifests": plan.manifests,
        "state_files": {name: name in plan.state_files for name in STATE_FILES},
        "bundle_key": RUN_STATE_BUNDLE_KEY,
        "bundle_sha256": report.bundle.sha256 if report is not None else None,
        "checked_back": list(report.checked) if report is not None else [],
    }


def _table(plan: SeedPlan, report: SeedReport | None) -> TableSpec:
    done = set(report.checked) if report is not None else set[str]()
    rows = [
        [
            RUN_STATE_BUNDLE_KEY,
            f"{plan.manifests} manifest(s) and the database",
            _mark(RUN_STATE_BUNDLE_KEY, done),
        ]
    ]
    rows += [
        [
            state_key(name),
            "this machine's copy" if name in plan.state_files else "absent here: uploaded empty",
            _mark(state_key(name), done),
        ]
        for name in STATE_FILES
    ]
    return TableSpec(
        columns=("Object", "From", ""),
        rows=rows,
        title="caselist seed-run-state" + (" (dry run)" if report is None else ""),
        caption=(
            "Seeded: the lock created, every object above uploaded and checked back, the lock released."
            if report is not None
            else "Nothing was written. Re-run with --execute to create the lock and upload these."
        ),
    )


def _mark(key: str, done: set[str]) -> str:
    return "checked" if key in done else ""
