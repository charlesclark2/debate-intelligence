"""`--max-cost`: the most one command may spend on model calls (v1-e05-t07-usage-telemetry).

Any command that calls a model (the landscape's classification, `cut`, auto-cut, `daily`) adopts it
the same way: take the option, and build the command's services from the settings it returns::

    def classify(ctx: typer.Context, max_cost: MaxCost = None) -> None:
        settings = with_max_cost(cli_context(ctx).services.settings, max_cost)

The option sets `models.budget_usd_per_run` for that one command, in place of whatever the settings
said. The accounting is the budget guard's (`debate_core.application.budget`), which refuses a call
that could take the run past it; nothing here counts anything.
"""

from __future__ import annotations

from typing import Annotated, Final

import typer

from debate_core.application.settings import Settings

__all__ = ["MAX_COST_OPTION", "MaxCost", "with_max_cost"]

MAX_COST_OPTION: Final = "--max-cost"

MaxCost = Annotated[
    float | None,
    typer.Option(
        MAX_COST_OPTION,
        min=0.0,
        metavar="USD",
        help=(
            "The most this command may spend on model calls, in USD. A call that could take it past "
            "this is refused before it is made. Default: models.budget_usd_per_run, else no limit."
        ),
    ),
]
"""The `--max-cost` option, for a command's signature: `max_cost: MaxCost = None`."""


def with_max_cost(settings: Settings, max_cost: float | None) -> Settings:
    """`settings` with `--max-cost` as the per-run limit; unchanged when the option was not given."""
    return settings
