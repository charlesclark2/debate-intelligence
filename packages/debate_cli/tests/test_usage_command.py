"""`debate-research usage` and the `--max-cost` option helper (v1-e05-t07-usage-telemetry, ac4).

Through Typer's `CliRunner` against the real application, in a `test` environment whose data
directory is the test's own. The day's usage log is written by hand below, line by line, and every
expected group and total is added up by hand from those lines. The month's spend and the limits
beside the day's are v1-e05-t15's (ac3).
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import typer
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.container import ServiceContainer
from debate_cli.exit_codes import ExitCode
from debate_cli.options.budget import MaxCost, with_max_cost
from debate_core.application.budget import BudgetLimits
from debate_core.application.settings import Settings, load_settings
from debate_core.integrations.models.factory import budget_limits
from debate_core.integrations.models.usage import UsageLog
from debate_core.testing.fakes.clock_and_ids import FixedClock

runner = CliRunner()

CHICAGO = ZoneInfo("America/Chicago")
LATE_EVENING = datetime(2026, 9, 18, 3, 30, tzinfo=UTC)
"""22:30 on 2026-09-17 in Chicago: "today" for a command run then."""

DAY_LINES: list[dict[str, Any]] = [
    {
        "run_id": "r1",
        "prompt_id": "landscape.classify-position",
        "prompt_version": "1.0.0",
        "model_id": "test.haiku",
        "attempt": 1,
        "input_tokens": 1200,
        "output_tokens": 300,
        "latency_ms": 900.0,
        "estimated_cost_usd": 0.0027,
        "recorded_at": "2026-09-17T15:00:00Z",
    },
    {
        "run_id": "r1",
        "prompt_id": "model.repair",
        "prompt_version": "1.0.0",
        "model_id": "test.haiku",
        "attempt": 2,
        "input_tokens": 1500,
        "output_tokens": 200,
        "latency_ms": 950.0,
        "estimated_cost_usd": 0.0025,
        "recorded_at": "2026-09-17T15:00:01Z",
    },
    {
        "run_id": "r2",
        "prompt_id": "landscape.classify-position",
        "prompt_version": "1.0.0",
        "model_id": "test.haiku",
        "attempt": 1,
        "input_tokens": 800,
        "output_tokens": 100,
        "latency_ms": 700.0,
        "estimated_cost_usd": 0.0013,
        "recorded_at": "2026-09-17T16:00:00Z",
    },
    {
        "run_id": "r2",
        "prompt_id": "landscape.classify-position",
        "prompt_version": "1.0.0",
        "model_id": "anthropic.claude-sonnet-5-5",
        "attempt": 1,
        "input_tokens": 1000,
        "output_tokens": 50,
        "latency_ms": 1200.0,
        "estimated_cost_usd": None,
        "recorded_at": "2026-09-17T16:00:01Z",
    },
    {
        "run_id": "r2",
        "prompt_id": None,
        "prompt_version": None,
        "model_id": "amazon.titan-embed-text-v2:0",
        "attempt": 1,
        "input_tokens": 400,
        "output_tokens": None,
        "latency_ms": 80.0,
        "estimated_cost_usd": 8e-05,
        "recorded_at": "2026-09-17T16:00:02Z",
    },
]
DAY_FILE = "".join(json.dumps(line) + "\n" for line in DAY_LINES)
"""Five calls on 2026-09-17: three to test.haiku (one a repair), one to an unpriced model, one embedding."""

EXPECTED_GROUPS = [
    # Sorted by prompt id, the embedding's none first, then by model id.
    {
        "prompt_id": None,
        "model_id": "amazon.titan-embed-text-v2:0",
        "calls": 1,
        "input_tokens": 400,
        "output_tokens": 0,
        "estimated_cost_usd": 0.00008,
        "unpriced_calls": 0,
    },
    {
        "prompt_id": "landscape.classify-position",
        "model_id": "anthropic.claude-sonnet-5-5",
        "calls": 1,
        "input_tokens": 1000,
        "output_tokens": 50,
        "estimated_cost_usd": 0.0,
        "unpriced_calls": 1,
    },
    {
        # 1200 + 800 input, 300 + 100 output, $0.0027 + $0.0013.
        "prompt_id": "landscape.classify-position",
        "model_id": "test.haiku",
        "calls": 2,
        "input_tokens": 2000,
        "output_tokens": 400,
        "estimated_cost_usd": 0.004,
        "unpriced_calls": 0,
    },
    {
        "prompt_id": "model.repair",
        "model_id": "test.haiku",
        "calls": 1,
        "input_tokens": 1500,
        "output_tokens": 200,
        "estimated_cost_usd": 0.0025,
        "unpriced_calls": 0,
    },
]

EXPECTED_TOTALS = {
    # 400 + 1000 + 2000 + 1500 input; 0 + 50 + 400 + 200 output; $0.00008 + $0.004 + $0.0025 priced.
    "calls": 5,
    "input_tokens": 4900,
    "output_tokens": 650,
    "estimated_cost_usd": 0.00658,
    "unpriced_calls": 1,
}


def month_line(cost: float, input_tokens: int, output_tokens: int, recorded_at: str) -> str:
    return (
        json.dumps(
            {
                "run_id": "r0",
                "prompt_id": "landscape.classify-position",
                "prompt_version": "1.0.0",
                "model_id": "test.haiku",
                "attempt": 1,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "latency_ms": 500.0,
                "estimated_cost_usd": cost,
                "recorded_at": recorded_at,
            }
        )
        + "\n"
    )


MONTH_FILES = {
    # 10:00 CDT on 2 September.
    "2026-09-02.jsonl": month_line(0.01, 100, 10, "2026-09-02T15:00:00Z"),
    # 22:00 CDT on 30 September, filed under 1 October as a machine in UTC files it: September's.
    "2026-10-01.jsonl": month_line(0.02, 200, 20, "2026-10-01T03:00:00Z"),
    # 23:00 CDT on 31 August, filed under 1 September by the same machine: not September's.
    "2026-09-01.jsonl": month_line(0.04, 300, 30, "2026-09-01T04:00:00Z"),
}
"""Three more calls around September 2026, each placed in its month by its own time in Chicago."""

EXPECTED_SEPTEMBER = {
    # The day's five calls, and 2 and 30 September's: 4900 + 100 + 200 input, 650 + 10 + 20 output,
    # $0.00658 + $0.01 + $0.02, and the day's one unpriced call. 31 August's $0.04 is not in it.
    "month": "2026-09",
    "zone": "America/Chicago",
    "calls": 7,
    "input_tokens": 5200,
    "output_tokens": 680,
    "estimated_cost_usd": 0.03658,
    "unpriced_calls": 1,
}


@pytest.fixture
def data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """A `test` environment with its own data directory, read in Chicago at 22:30 on 2026-09-17."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    data = tmp_path / "data"
    monkeypatch.setenv("DEBATE_ENV", "test")
    monkeypatch.setenv("DEBATE_STORAGE__DATA_DIR", str(data))
    monkeypatch.setattr(ServiceContainer, "clock", lambda self: FixedClock(LATE_EVENING).now)
    monkeypatch.setattr(
        ServiceContainer,
        "usage_log",
        lambda self: UsageLog.for_data_dir(self.settings.storage.data_dir, local_zone=CHICAGO),
    )
    yield data


def write_day(data_dir: Path, name: str = "2026-09-17.jsonl", text: str = DAY_FILE) -> None:
    usage = data_dir / "usage"
    usage.mkdir(parents=True, exist_ok=True)
    (usage / name).write_text(text, encoding="utf-8")


def write_month(data_dir: Path) -> None:
    write_day(data_dir)
    for name, text in MONTH_FILES.items():
        write_day(data_dir, name, text)


def with_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    """The bundled prod values: $1.50 a day and $50 a month."""
    monkeypatch.setenv("DEBATE_MODELS__BUDGET_USD_DAILY", "1.5")
    monkeypatch.setenv("DEBATE_MODELS__BUDGET_USD_MONTHLY", "50.0")


def invoke(*arguments: str) -> Result:
    return runner.invoke(create_app(), list(arguments), env={"COLUMNS": "200"})


def as_json(*arguments: str) -> dict[str, Any]:
    result = invoke("--json", *arguments)
    assert result.exit_code == 0, result.output
    [line] = [line for line in result.stdout.splitlines() if line.strip()]
    envelope: dict[str, Any] = json.loads(line)
    return envelope["data"]


def approximately(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row | {"estimated_cost_usd": pytest.approx(row["estimated_cost_usd"])} for row in rows]


# ---------------------------------------------------------------------------------------------
# usage
# ---------------------------------------------------------------------------------------------


def test_usage_json_groups_a_days_calls_tokens_and_cost_by_prompt_and_model(data_dir: Path) -> None:
    write_day(data_dir)

    data = as_json("usage", "--date", "2026-09-17")

    assert data["date"] == "2026-09-17"
    assert data["groups"] == approximately(EXPECTED_GROUPS)
    assert data["totals"] == approximately([EXPECTED_TOTALS])[0]


def test_usage_table_shows_the_same_groups_and_a_total(data_dir: Path) -> None:
    write_day(data_dir)

    result = invoke("usage", "--date", "2026-09-17")

    assert result.exit_code == 0, result.output
    rows = [" ".join(line.replace("│", " ").split()) for line in result.output.splitlines()]
    assert "- amazon.titan-embed-text-v2:0 1 400 0 0.0001" in rows
    assert "landscape.classify-position anthropic.claude-sonnet-5-5 1 1000 50 0.0000 (+1 unpriced)" in rows
    assert "landscape.classify-position test.haiku 2 2000 400 0.0040" in rows
    assert "model.repair test.haiku 1 1500 200 0.0025" in rows
    assert "Total 5 4900 650 0.0066 (+1 unpriced)" in rows
    assert "Model usage on 2026-09-17" in result.output
    assert "not in the totals" in " ".join(result.output.split())


def test_usage_json_shows_the_month_s_spend_and_both_limits_beside_the_day_s(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with_limits(monkeypatch)
    write_month(data_dir)

    data = as_json("usage", "--date", "2026-09-17")

    assert data["totals"] == approximately([EXPECTED_TOTALS])[0]
    assert data["month"] == approximately([EXPECTED_SEPTEMBER])[0]
    assert data["limits"] == {"daily_usd": 1.5, "monthly_usd": 50.0}


def test_usage_table_shows_the_month_s_spend_and_both_limits_under_the_day_s_total(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with_limits(monkeypatch)
    write_month(data_dir)

    result = invoke("usage", "--date", "2026-09-17")

    assert result.exit_code == 0, result.output
    rows = [" ".join(line.replace("│", " ").split()) for line in result.output.splitlines()]
    assert "Total 5 4900 650 0.0066 (+1 unpriced)" in rows
    assert "Daily limit 1.5000" in rows
    assert "Month 2026-09 (America/Chicago) 7 5200 680 0.0366 (+1 unpriced)" in rows
    assert "Monthly limit 50.0000" in rows


def test_usage_without_a_date_shows_this_month_in_chicago(data_dir: Path) -> None:
    write_month(data_dir)

    data = as_json("usage")

    assert data["month"] == approximately([EXPECTED_SEPTEMBER])[0]


def test_usage_shows_an_unset_limit_as_none(data_dir: Path) -> None:
    """The test profile sets the day's limit to $0 and leaves the month's unset."""
    write_day(data_dir)

    result = invoke("usage", "--date", "2026-09-17")

    rows = [" ".join(line.replace("│", " ").split()) for line in result.output.splitlines()]
    assert "Daily limit 0.0000" in rows
    assert "Monthly limit none" in rows
    assert as_json("usage", "--date", "2026-09-17")["limits"] == {"daily_usd": 0.0, "monthly_usd": None}


def test_usage_without_a_date_reads_today_on_the_local_clock(data_dir: Path) -> None:
    """At 22:30 on the 17th in Chicago it is the 18th in UTC; today is the 17th."""
    write_day(data_dir)
    write_day(data_dir, "2026-09-18.jsonl", "")

    data = as_json("usage")

    assert data["date"] == "2026-09-17"
    assert data["totals"]["calls"] == 5


def test_usage_of_a_day_with_no_calls_says_so(data_dir: Path) -> None:
    result = invoke("usage", "--date", "2026-09-16")

    assert result.exit_code == 0, result.output
    assert "No real model call was recorded on this day" in " ".join(result.output.split())
    assert as_json("usage", "--date", "2026-09-16") == {
        "date": "2026-09-16",
        "groups": [],
        "totals": {
            "calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "estimated_cost_usd": 0.0,
            "unpriced_calls": 0,
        },
        "month": {
            "month": "2026-09",
            "zone": "America/Chicago",
            "calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "estimated_cost_usd": 0.0,
            "unpriced_calls": 0,
        },
        "limits": {"daily_usd": 0.0, "monthly_usd": None},
    }


@pytest.mark.parametrize("value", ["17-09-2026", "2026-09-31", "yesterday"])
def test_usage_refuses_a_date_that_is_not_one(value: str, data_dir: Path) -> None:
    result = invoke("usage", "--date", value)

    assert result.exit_code == ExitCode.USAGE_ERROR
    assert "YYYY-MM-DD" in result.output


def test_usage_help_says_what_it_shows() -> None:
    result = invoke("usage", "--help")

    assert result.exit_code == 0
    assert "--date" in result.output
    assert "tokens and estimated cost" in " ".join(result.output.split())


# ---------------------------------------------------------------------------------------------
# --max-cost
# ---------------------------------------------------------------------------------------------


def probe_app(settings: Settings, seen: list[float | None]) -> typer.Typer:
    """A one-command app adopting `--max-cost` as the helper's docstring says a command does."""
    app = typer.Typer()

    @app.command()
    def classify(max_cost: MaxCost = None) -> None:  # pyright: ignore[reportUnusedFunction]
        seen.append(with_max_cost(settings, max_cost).models.budget_usd_per_run)

    return app


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    return load_settings(
        environment="test", overrides={"models": {"budget_usd_per_run": 1.5}}, env_file=tmp_path / "no.env"
    )


def test_max_cost_sets_the_per_run_limit_for_the_one_command(settings: Settings) -> None:
    seen: list[float | None] = []

    result = runner.invoke(probe_app(settings, seen), ["--max-cost", "0.05"])

    assert result.exit_code == 0, result.output
    assert seen == [0.05]
    assert settings.models.budget_usd_per_run == 1.5


def test_max_cost_left_out_keeps_the_settings_limit(settings: Settings) -> None:
    seen: list[float | None] = []

    runner.invoke(probe_app(settings, seen), [])

    assert seen == [1.5]


def test_max_cost_below_zero_is_a_usage_error(settings: Settings) -> None:
    seen: list[float | None] = []

    result = runner.invoke(probe_app(settings, seen), ["--max-cost", "-0.01"])

    assert result.exit_code == ExitCode.USAGE_ERROR
    assert seen == []


def test_max_cost_is_the_limit_the_router_s_budget_guard_is_built_with(settings: Settings) -> None:
    limited = with_max_cost(settings, 0.05)

    assert budget_limits(limited) == BudgetLimits(
        per_run_usd=0.05,
        per_day_usd=settings.models.budget_usd_daily,
        per_month_usd=settings.models.budget_usd_monthly,
    )


def test_the_router_s_budget_guard_is_built_with_the_monthly_limit(settings: Settings) -> None:
    monthly = settings.model_copy(
        update={"models": settings.models.model_copy(update={"budget_usd_monthly": 50.0})}
    )

    assert budget_limits(monthly).per_month_usd == 50.0
