"""`debate-research landscape cassettes`: skeleton."""

from __future__ import annotations

from typing import Annotated

import typer

from debate_cli.context import cli_context, command_name
from debate_cli.options.bucket_environment import CONFIRM_PROD_FLAG
from debate_cli.output import CliOutput, OutputMode

__all__ = ["cassettes"]


def cassettes(
    ctx: typer.Context,
    caselist: Annotated[str, typer.Option("--caselist", help="Caselist slug, e.g. hsld26.")],
    delete: Annotated[bool, typer.Option("--delete")] = False,
    confirmation: Annotated[str | None, typer.Option("--confirm")] = None,
    confirm_prod: Annotated[bool, typer.Option(CONFIRM_PROD_FLAG)] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Skeleton."""
    cli = cli_context(ctx)
    if json_output and not cli.output.is_json:
        cli.output = CliOutput(OutputMode.JSON, verbose=cli.output.verbose)
    cli.output.success(command_name(ctx), {}, display="")
