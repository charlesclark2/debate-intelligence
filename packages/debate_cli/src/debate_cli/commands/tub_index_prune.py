"""`debate-research tub index prune`: the search pilot's superseded index versions, deleted (`v1-e39-t15`).

::

    export DEBATE_REMOVAL_PROFILE=debate-dev-evidence-removal
    DEBATE_ENV=dev debate-research tub index prune --env dev
    DEBATE_ENV=dev debate-research tub index prune --env dev --execute --confirm <code>

The removal runbook's P4 (`docs/runbooks/caselist-removal.md`) as one command. Every decision is
:class:`~debate_core.application.search_index_prune.SearchIndexPrune`'s; this is the guards, the lock
and the rendering.

## A dry run, then a confirmation

Without `--execute` nothing changes: the command reads `current.json`, lists every version and delete
marker under `reports/tub/search/`, keeps the current index's directory and the current
`current.json`, and prints what it would delete, by index directory, with a confirmation code.
`--execute --confirm <code>` plans again and deletes only if that plan's code is the one given: exactly
what the dry run listed. A pointer the listing does not hold is refused, in either.

## The guards

`--env` must name the environment `DEBATE_ENV` selects, as for `tub index publish`, and `--execute` in
prod needs `--confirm-prod`. Both runs need `DEBATE_REMOVAL_PROFILE`: the takedown profile is the one
that may list and delete versions under `reports/tub/search/`, and it must be signed in as this
environment's takedown role. `--execute` refuses on a Wednesday in Chicago, the cloud run's day, and
holds the bucket's run lock while it deletes, so it is refused while the cloud run, a publish or a
removal holds it. Inside the lock it reads `current.json` again and deletes nothing if it moved.

## What it prints

Counts, index ids shortened to eight characters, and the code. No key: `--json`'s `delete` lists each
version it would delete or did, by key and version id, as other store commands' `--json` does.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from debate_cli.bucket_lock import run_holding_the_bucket_lock
from debate_cli.context import CliContext, cli_context, command_name
from debate_cli.exit_codes import ExitCode
from debate_cli.options.bucket_environment import CONFIRM_PROD_FLAG, SYNCABLE_ENVIRONMENTS
from debate_cli.output import CliOutput, CommandFailure, JsonValue, OutputMode, TableSpec
from debate_core.application.search_index_prune import (
    PRUNE_COMMAND,
    PruneGroup,
    PrunePlan,
    PruneRefusal,
    PruneResult,
    SearchIndexPrune,
)
from debate_core.application.settings import Environment, Settings

__all__ = ["prune", "prune_summary"]

SHORT_INDEX_ID = 8
"""How much of an index id the console shows."""


def prune(
    ctx: typer.Context,
    env: Annotated[
        Environment,
        typer.Option("--env", help="dev or prod: must be the environment DEBATE_ENV selects."),
    ],
    execute: Annotated[
        bool, typer.Option("--execute", help="Delete what the dry run listed. Without it, nothing changes.")
    ] = False,
    confirmation: Annotated[
        str | None, typer.Option("--confirm", help="The confirmation code the dry run printed.")
    ] = None,
    confirm_prod: Annotated[
        bool, typer.Option(CONFIRM_PROD_FLAG, help="Required to delete with DEBATE_ENV=prod.")
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Write one machine-readable JSON object to stdout.")
    ] = False,
) -> None:
    """List superseded search index versions in the bucket and, with confirmation, delete them."""
    cli = cli_context(ctx)
    if json_output and not cli.output.is_json:
        cli.output = CliOutput(OutputMode.JSON, verbose=cli.output.verbose)
    settings = cli.services.settings
    _refuse(cli, ctx, _guard(settings, env, execute=execute, confirmed=confirm_prod))
    service = cli.services.search_index_prune()
    if execute:
        service.refuse_on_cloud_run_day()
    plan = asyncio.run(service.plan())
    refusal = plan.refusal(confirmation) if execute else (plan.refusals[0] if plan.refusals else None)
    if refusal is not None:
        _refuse(cli, ctx, _failure(refusal, plan))
    result = _execute(cli, service, plan, confirmation) if execute else None
    cli.output.success(command_name(ctx), prune_summary(plan, result, settings), display=_table(plan, result))


def _execute(
    cli: CliContext, service: SearchIndexPrune, plan: PrunePlan, confirmation: str | None
) -> PruneResult:
    """Delete holding the bucket's run lock, which every publish holds too (`v1-e40-t04`)."""
    return run_holding_the_bucket_lock(
        cli, PRUNE_COMMAND, lambda: service.execute(plan, confirmation=confirmation)
    )


# ------------------------------------------------------------------------------------------------
# Guards
# ------------------------------------------------------------------------------------------------


def _guard(settings: Settings, env: Environment, *, execute: bool, confirmed: bool) -> CommandFailure | None:
    running = settings.environment
    if env not in SYNCABLE_ENVIRONMENTS or not settings.storage.s3.bucket:
        return CommandFailure(
            code="EVIDENCE_STORE_NOT_CONFIGURED",
            message=f"`{PRUNE_COMMAND}` works on dev's or prod's evidence bucket, not {env.value}'s",
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"environment": env.value},
        )
    if env is not running:
        return CommandFailure(
            code="ENVIRONMENT_MISMATCH",
            message=f"--env {env.value} names another environment than DEBATE_ENV selects ({running.value})",
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"requested": env.value, "environment": running.value},
            hint=f"Run it with DEBATE_ENV={env.value}, or with --env {running.value}.",
        )
    if not settings.removal_profile:
        return CommandFailure(
            code="TAKEDOWN_NOT_CONFIGURED",
            message=(
                f"`{PRUNE_COMMAND}` lists and deletes with the takedown profile: set DEBATE_REMOVAL_PROFILE "
                f"to debate-{running.value}-evidence-removal and sign in to it; nothing was listed"
            ),
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"environment": running.value},
        )
    if execute and running is Environment.PROD and not confirmed:
        return CommandFailure(
            code="CONFIRMATION_REQUIRED",
            message=f"refusing to delete from the production evidence bucket without {CONFIRM_PROD_FLAG}",
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"environment": running.value},
            hint=f"Run it without --execute first and read the plan, then add {CONFIRM_PROD_FLAG}.",
        )
    return None


def _failure(refusal: PruneRefusal, plan: PrunePlan) -> CommandFailure:
    return CommandFailure(
        code=refusal.code,
        message=refusal.message,
        exit_code=ExitCode.DOMAIN_FAILURE,
        details={"location": plan.location, "index_id": plan.index_id},
        hint="Nothing was deleted.",
    )


def _refuse(cli: CliContext, ctx: typer.Context, refusal: CommandFailure | None) -> None:
    if refusal is None:
        return
    cli.output.failure(refusal, command=command_name(ctx))
    raise typer.Exit(code=refusal.exit_code)


# ------------------------------------------------------------------------------------------------
# Rendering: counts and short index ids on the console; keys in --json only
# ------------------------------------------------------------------------------------------------


def prune_summary(plan: PrunePlan, result: PruneResult | None, settings: Settings) -> dict[str, JsonValue]:
    """The `--json` envelope's `data`."""
    return {
        "environment": settings.environment.value,
        "location": plan.location,
        "index_id": plan.index_id,
        "keeps": plan.keep_prefix,
        "applied": result is not None,
        "confirmation": plan.confirmation,
        "counts": _counts(plan),
        "groups": [
            {"name": one.name, "delete": one.delete, "delete_markers": one.delete_markers, "keep": one.keep}
            for one in plan.groups
        ],
        "delete": [
            {"key": one.key, "version_id": one.version_id, "delete_marker": one.is_delete_marker}
            for one in plan.doomed
        ],
        "deleted": None if result is None else result.deleted,
    }


def _counts(plan: PrunePlan) -> dict[str, JsonValue]:
    return {
        "versions": sum(1 for one in plan.doomed if not one.is_delete_marker),
        "delete_markers": sum(1 for one in plan.doomed if one.is_delete_marker),
        "keys": len({one.key for one in plan.doomed}),
        "superseded_directories": sum(1 for one in plan.groups if one.name.endswith("/") and not one.keep),
        "kept": len(plan.kept),
    }


def _table(plan: PrunePlan, result: PruneResult | None) -> TableSpec:
    rows = [
        [
            _short(one.name),
            str(one.delete),
            str(one.delete_markers),
            str(one.keep),
            _mark(one, applied=result is not None),
        ]
        for one in plan.groups
    ]
    return TableSpec(
        columns=("Under the index prefix", "Versions to delete", "Delete markers", "Kept", ""),
        rows=rows,
        title=f"{PRUNE_COMMAND} on {plan.location}: current index {(plan.index_id or '')[:SHORT_INDEX_ID]}",
        caption=_caption(plan, result),
    )


def _mark(group: PruneGroup, *, applied: bool) -> str:
    deleting = group.delete + group.delete_markers
    verb = "deleted" if applied else "would be deleted"
    if group.keep and deleting:
        return f"current kept, older {verb}"
    return "kept" if group.keep else verb


def _caption(plan: PrunePlan, result: PruneResult | None) -> str:
    counts = _counts(plan)
    listed = (
        f"{counts['versions']} version(s) and {counts['delete_markers']} delete marker(s) of "
        f"{counts['keys']} key(s), in {counts['superseded_directories']} superseded index directory(ies) "
        "and current.json's older versions"
    )
    if result is not None:
        return f"Deleted {result.deleted} of {listed}. Kept {counts['kept']} version(s)."
    if not plan.doomed:
        return f"Dry run: nothing to delete. Kept {counts['kept']} version(s)."
    return (
        f"Dry run: nothing was changed. Would delete {listed}; keeps {counts['kept']} version(s). "
        f"To carry it out, add: --execute --confirm {plan.confirmation}"
    )


def _short(name: str) -> str:
    """An index directory as its id's first eight characters; `current.json` as it is."""
    head = name.removesuffix("/")
    if name.endswith("/") and len(head) > SHORT_INDEX_ID:
        return f"{head[:SHORT_INDEX_ID]}../"
    return name
