"""`debate-research tub index prune`. SKELETON for the red run: no guard, no lock."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from debate_cli.context import cli_context, command_name
from debate_cli.output import CliOutput, JsonValue, OutputMode, TableSpec
from debate_core.application.search_index_prune import PrunePlan, PruneResult
from debate_core.application.settings import Environment, Settings

__all__ = ["prune", "prune_summary"]


def prune(
    ctx: typer.Context,
    env: Annotated[Environment, typer.Option("--env", help="dev or prod.")],
    execute: Annotated[bool, typer.Option("--execute", help="Delete.")] = False,
    confirmation: Annotated[str | None, typer.Option("--confirm", help="The dry run's code.")] = None,
    confirm_prod: Annotated[bool, typer.Option("--confirm-prod", help="For prod.")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="JSON.")] = False,
) -> None:
    """Delete superseded search index versions."""
    del env, confirm_prod
    cli = cli_context(ctx)
    if json_output and not cli.output.is_json:
        cli.output = CliOutput(OutputMode.JSON, verbose=cli.output.verbose)
    service = cli.services.search_index_prune()
    plan = asyncio.run(service.plan())
    result = asyncio.run(service.execute(plan, confirmation=confirmation)) if execute else None
    cli.output.success(
        command_name(ctx), prune_summary(plan, result, cli.services.settings), display=_table(plan, result)
    )


def prune_summary(plan: PrunePlan, result: PruneResult | None, settings: Settings) -> dict[str, JsonValue]:
    return {
        "environment": settings.environment.value,
        "location": plan.location,
        "index_id": plan.index_id,
        "applied": result is not None,
        "confirmation": plan.confirmation,
        "delete": [
            {"key": one.key, "version_id": one.version_id, "delete_marker": one.is_delete_marker}
            for one in plan.doomed
        ],
        "deleted": None if result is None else result.deleted,
    }


def _table(plan: PrunePlan, result: PruneResult | None) -> TableSpec:
    del result
    return TableSpec(columns=("Group", "Versions"), rows=[], title=f"tub index prune on {plan.location}")
