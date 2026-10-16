"""`debate-research caselist retire`: superseded parsed-store version directories, listed and retired.

::

    debate-research caselist retire
    debate-research caselist retire --version 2026.10.10-docx-2
    debate-research caselist retire --version 2026.10.10-docx-2 --execute --confirm <code>
    debate-research caselist retire --bucket --version 2026.10.10-docx-2
    debate-research caselist retire --bucket --version 2026.10.10-docx-2 --execute --confirm <code>
    debate-research caselist retire --bucket --version 2026.10.10-docx-2 --restore

Every decision is :class:`~debate_core.application.caselist.version_retention.VersionDirectoryRetention`'s
(`v1-e31-t16`); this is the guards and the rendering. The rule is in
`docs/data/parsed-card-store.md` ("Retention") and the procedure in
`docs/runbooks/parsed-store-retention.md`.

## A dry run, then a confirmation

Without `--execute` nothing changes anywhere: the command lists every version directory of the
caselists asked for (all of them by default), with its standing against this build's parser
version, its object count and size, and a confirmation code. `--execute` needs the directories named
with `--version` and that code with `--confirm`. The code is a digest of what the dry run showed, so
a directory that changed since, or a different place, is refused rather than acted on. In prod,
`--execute` also needs `--confirm-prod`.

## Where

This machine by default, where retiring deletes the directory. `--bucket` works on `DEBATE_ENV`'s
evidence bucket instead, under the everyday profile, where retiring tags each object for the
bucket's lifecycle rule and deletes nothing. `--restore` sets that tag to `restored` in the bucket,
which undoes a retirement until the lifecycle rule has acted.

## Exit code

0, or 1 with the reason code when the plan refuses: the current directory, a directory a newer
build wrote, a directory with no successor in that place, a name no caselist has, a missing or
stale confirmation code. Nothing this command prints names a path, a school or a team code.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from debate_cli.commands.store import CONFIRM_PROD_FLAG, SYNCABLE_ENVIRONMENTS
from debate_cli.context import CliContext, cli_context, command_name
from debate_cli.exit_codes import ExitCode
from debate_cli.output import CliOutput, CommandFailure, JsonValue, OutputMode, TableSpec
from debate_core.application.caselist.version_retention import (
    DirectoryRow,
    RetentionPlan,
    RetentionRefusal,
    RetentionResult,
)
from debate_core.application.settings import Environment, Settings

__all__ = ["retire", "retire_summary"]


def retire(
    ctx: typer.Context,
    caselists: Annotated[
        list[str] | None,
        typer.Option(
            "--caselist", help="Only this caselist, e.g. hsld26 or openev. Repeatable. Default: all."
        ),
    ] = None,
    versions: Annotated[
        list[str] | None,
        typer.Option("--version", help="A version directory to retire, as the dry run lists it. Repeatable."),
    ] = None,
    bucket: Annotated[
        bool, typer.Option("--bucket", help="Work on DEBATE_ENV's evidence bucket instead of this machine.")
    ] = False,
    restore: Annotated[
        bool,
        typer.Option("--restore", help="Undo a retirement in the bucket before the lifecycle rule acts."),
    ] = False,
    execute: Annotated[
        bool, typer.Option("--execute", help="Act on the plan. Without it, nothing changes anywhere.")
    ] = False,
    confirmation: Annotated[
        str | None, typer.Option("--confirm", help="The confirmation code the dry run printed.")
    ] = None,
    confirm_prod: Annotated[
        bool, typer.Option(CONFIRM_PROD_FLAG, help="Required to change anything with DEBATE_ENV=prod.")
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Write one machine-readable JSON object to stdout.")
    ] = False,
) -> None:
    """List superseded parsed-store version directories and, with confirmation, retire them."""
    cli = cli_context(ctx)
    if json_output and not cli.output.is_json:
        cli.output = CliOutput(OutputMode.JSON, verbose=cli.output.verbose)
    settings = cli.services.settings
    _refuse(cli, ctx, _guard(settings, bucket=bucket, execute=execute, confirmed=confirm_prod))
    service = cli.services.version_retention(bucket=bucket)
    plan = asyncio.run(service.plan(caselists=caselists or (), versions=versions or (), restore=restore))
    refusal = plan.refusal(confirmation) if execute else (plan.refusals[0] if plan.refusals else None)
    if refusal is not None:
        _refuse(cli, ctx, _failure(refusal, plan))
    result = asyncio.run(service.execute(plan, confirmation=confirmation)) if execute else None
    cli.output.success(
        command_name(ctx), retire_summary(plan, result, settings), display=_table(plan, result)
    )


# ------------------------------------------------------------------------------------------------
# Guards
# ------------------------------------------------------------------------------------------------


def _guard(settings: Settings, *, bucket: bool, execute: bool, confirmed: bool) -> CommandFailure | None:
    """A bucket means dev or prod with a bucket named; changing anything in prod needs --confirm-prod."""
    if bucket and (settings.environment not in SYNCABLE_ENVIRONMENTS or not settings.storage.s3.bucket):
        return CommandFailure(
            code="EVIDENCE_STORE_NOT_CONFIGURED",
            message=f"`caselist retire --bucket` works on dev or prod, not {settings.environment.value}",
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"environment": settings.environment.value},
            hint="Set DEBATE_ENV=dev (or prod) and try again.",
        )
    if execute and settings.environment is Environment.PROD and not confirmed:
        return CommandFailure(
            code="CONFIRMATION_REQUIRED",
            message=f"refusing to change production's parsed store without {CONFIRM_PROD_FLAG}",
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"environment": settings.environment.value},
            hint=f"Run it without --execute first and read the plan, then add {CONFIRM_PROD_FLAG}.",
        )
    return None


def _failure(refusal: RetentionRefusal, plan: RetentionPlan) -> CommandFailure:
    return CommandFailure(
        code=refusal.code,
        message=refusal.message,
        exit_code=ExitCode.DOMAIN_FAILURE,
        details={
            "location": plan.location,
            "parser_version": plan.parser_version,
            "refusals": [refusal.code for refusal in plan.refusals] or [refusal.code],
        },
        hint="Nothing was changed. A dry run without --version lists each directory's standing.",
    )


def _refuse(cli: CliContext, ctx: typer.Context, refusal: CommandFailure | None) -> None:
    if refusal is None:
        return
    cli.output.failure(refusal, command=command_name(ctx))
    raise typer.Exit(code=refusal.exit_code)


# ------------------------------------------------------------------------------------------------
# Rendering: names, standings and counts only
# ------------------------------------------------------------------------------------------------


def retire_summary(
    plan: RetentionPlan, result: RetentionResult | None, settings: Settings
) -> dict[str, JsonValue]:
    """The `--json` envelope's `data`."""
    selected = {(row.caselist, row.version) for row in plan.selected}
    return {
        "environment": settings.environment.value,
        "location": plan.location,
        "method": str(plan.method),
        "action": "restore" if plan.restore else "retire",
        "parser_version": plan.parser_version,
        "applied": result is not None,
        "named": list(plan.named),
        "confirmation": plan.confirmation,
        "directories": [
            {
                "caselist": row.caselist,
                "version": row.version,
                "standing": str(row.standing),
                "objects": row.contents.objects,
                "bytes": row.contents.bytes,
                "tagged": row.contents.tagged,
                "selected": (row.caselist, row.version) in selected,
            }
            for row in plan.rows
        ],
        "refusals": [
            {
                "code": refusal.code,
                "caselist": refusal.caselist,
                "version": refusal.version,
                "message": refusal.message,
            }
            for refusal in plan.refusals
        ],
        "acted_on": None
        if result is None
        else [
            {"caselist": row.caselist, "version": row.version, "objects": count}
            for row, count in result.acted_on
        ],
    }


def _table(plan: RetentionPlan, result: RetentionResult | None) -> TableSpec:
    acted = {(row.caselist, row.version): count for row, count in result.acted_on} if result else {}
    selected = {(row.caselist, row.version) for row in plan.selected}
    rows = [
        [
            row.caselist,
            row.version,
            str(row.standing).replace("_", " "),
            str(row.contents.objects),
            _size(row.contents.bytes),
            "-" if row.contents.tagged is None else str(row.contents.tagged),
            _mark(row, selected, acted, plan),
        ]
        for row in plan.rows
    ]
    return TableSpec(
        columns=("Caselist", "Version", "Standing", "Objects", "Size", "Tagged", ""),
        rows=rows,
        title=f"caselist retire on {plan.location} (parser version {plan.parser_version})",
        caption=_caption(plan, result),
    )


def _mark(
    row: DirectoryRow, selected: set[tuple[str, str]], acted: dict[tuple[str, str], int], plan: RetentionPlan
) -> str:
    key = (row.caselist, row.version)
    verb = "restored" if plan.restore else ("tagged" if str(plan.method) == "tag" else "deleted")
    if key in acted:
        return f"{verb}: {acted[key]}"
    if key in selected and plan.named:
        return "would be " + verb
    return ""


def _caption(plan: RetentionPlan, result: RetentionResult | None) -> str:
    if result is not None:
        done = sum(count for _, count in result.acted_on)
        verb = "restored" if plan.restore else "retired"
        return f"{len(result.acted_on)} directory(ies), {done} object(s) {verb}."
    if not plan.named:
        return (
            "Dry run: nothing was changed. Name the directories to retire with --version, then run it "
            "again with --execute and the code that dry run prints."
        )
    return f"Dry run: nothing was changed. To carry it out, add: --execute --confirm {plan.confirmation}"


def _size(count: int) -> str:
    size = float(count)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1000 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1000
    return f"{size:.1f} GB"
