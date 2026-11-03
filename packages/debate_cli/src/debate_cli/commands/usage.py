"""`debate-research usage`: one day's model calls, tokens and estimated cost (v1-e05-t07-usage-telemetry).

::

    debate-research usage                      # today, on this machine's local date
    debate-research usage --date 2026-09-17
    debate-research --json usage --date 2026-09-17

One row per prompt and model: the calls, the input and output tokens and the estimated cost, then a
total. It reads `<data_dir>/usage/<date>.jsonl`, which every real model call made in record or live
mode appends to; replayed and fake calls cost nothing and are not there. A call to a model with no
price in `config/model_pricing.yaml` has no cost, and is counted as unpriced rather than as free.
Embedding and rerank calls run no prompt, and show as `-`.

Under the day's total, the limits the budget guard holds calls to (v1-e05-t15): the daily limit,
the calendar month's spend in America/Chicago, the month the budget counts, and the monthly limit.
The month is the one the date is in, or without `--date` the one it is now in Chicago; its spend is
every record whose own time falls in it, as the guard adds it up. An unset limit shows as `none`.

The records and their summary are `debate_core.integrations.models.usage`'s; this is the rendering.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Final

import typer

from debate_cli.context import cli_context, command_name
from debate_cli.output import JsonValue, TableSpec
from debate_core.application.budget import BUDGET_MONTH_ZONE, CalendarMonth, local_day

__all__ = ["usage"]

NO_PROMPT: Final = "-"
"""What the prompt column says for an embedding or rerank call, which runs no prompt."""

NO_LIMIT: Final = "none"
"""What the cost column says for a limit that is not set."""


class InvalidUsageDate(typer.BadParameter):
    """`--date` is not a calendar date written YYYY-MM-DD."""

    def __init__(self, value: str) -> None:
        super().__init__(f"{value!r} is not a date; write it as YYYY-MM-DD", param_hint="--date")


def usage(
    ctx: typer.Context,
    day: Annotated[
        str | None,
        typer.Option("--date", metavar="YYYY-MM-DD", help="The local day to summarize. Default: today."),
    ] = None,
) -> None:
    """Show one day's model calls, tokens and estimated cost, by prompt and model."""
    cli = cli_context(ctx)
    services = cli.services
    log = services.usage_log()
    now = services.clock()()
    wanted = _parse_day(day) if day is not None else local_day(now, log.local_zone)
    month = CalendarMonth.containing(wanted) if day is not None else CalendarMonth.of(now)
    summary = log.summary(wanted)
    month_usage = log.month_usage(month)
    daily_limit = services.settings.models.budget_usd_daily
    monthly_limit = services.settings.models.budget_usd_monthly
    groups: list[JsonValue] = [
        {
            "prompt_id": group.prompt_id,
            "model_id": group.model_id,
            "calls": group.calls,
            "input_tokens": group.input_tokens,
            "output_tokens": group.output_tokens,
            "estimated_cost_usd": group.estimated_cost_usd,
            "unpriced_calls": group.unpriced_calls,
        }
        for group in summary.groups
    ]
    payload: dict[str, JsonValue] = {
        "date": wanted.isoformat(),
        "groups": groups,
        "totals": {
            "calls": summary.calls,
            "input_tokens": summary.input_tokens,
            "output_tokens": summary.output_tokens,
            "estimated_cost_usd": summary.estimated_cost_usd,
            "unpriced_calls": summary.unpriced_calls,
        },
        "month": {
            "month": month.isoformat(),
            "zone": BUDGET_MONTH_ZONE.key,
            "calls": month_usage.calls,
            "input_tokens": month_usage.input_tokens,
            "output_tokens": month_usage.output_tokens,
            "estimated_cost_usd": month_usage.estimated_cost_usd,
            "unpriced_calls": month_usage.unpriced_calls,
        },
        "limits": {"daily_usd": daily_limit, "monthly_usd": monthly_limit},
    }
    rows = [
        [
            group.prompt_id or NO_PROMPT,
            group.model_id,
            str(group.calls),
            str(group.input_tokens),
            str(group.output_tokens),
            _cost(group.estimated_cost_usd, group.unpriced_calls),
        ]
        for group in summary.groups
    ]
    rows.extend(
        [
            [
                "Total",
                "",
                str(summary.calls),
                str(summary.input_tokens),
                str(summary.output_tokens),
                _cost(summary.estimated_cost_usd, summary.unpriced_calls),
            ],
            ["Daily limit", "", "", "", "", _limit(daily_limit)],
            [
                f"Month {month.isoformat()} ({BUDGET_MONTH_ZONE.key})",
                "",
                str(month_usage.calls),
                str(month_usage.input_tokens),
                str(month_usage.output_tokens),
                _cost(month_usage.estimated_cost_usd, month_usage.unpriced_calls),
            ],
            ["Monthly limit", "", "", "", "", _limit(monthly_limit)],
        ]
    )
    cli.output.success(
        command_name(ctx),
        payload,
        display=TableSpec(
            columns=("Prompt", "Model", "Calls", "Input tokens", "Output tokens", "Estimated cost (USD)"),
            rows=rows,
            title=f"Model usage on {wanted.isoformat()}",
            caption=_caption(summary.calls, summary.unpriced_calls),
        ),
    )


def _parse_day(value: str) -> date:
    try:
        return date.fromisoformat(value.strip())
    except ValueError as malformed:
        raise InvalidUsageDate(value) from malformed


def _cost(usd: float, unpriced_calls: int) -> str:
    """The priced calls' cost, and how many calls had no price, which it does not include."""
    cost = f"{usd:.4f}"
    return f"{cost} (+{unpriced_calls} unpriced)" if unpriced_calls else cost


def _limit(usd: float | None) -> str:
    return NO_LIMIT if usd is None else f"{usd:.4f}"


def _caption(calls: int, unpriced_calls: int) -> str | None:
    if calls == 0:
        return "No real model call was recorded on this day. Replayed and fake calls are never recorded."
    if unpriced_calls:
        return (
            f"{unpriced_calls} call(s) went to a model with no price in config/model_pricing.yaml; "
            "their cost is unknown and not in the totals."
        )
    return None
