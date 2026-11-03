"""`debate-research usage` on the build under test, offline (v1-e05-t07-usage-telemetry).

The build is checked for what a person runs it for: it is installed with its help, it reads a day's
usage log from the data directory and adds it up by prompt and model, and it refuses a date that is
not one. The log is written by hand into the scratch data directory, two calls on 2026-09-17, and
the totals below are added up by hand from those two lines. No model is called: the usage log is
what earlier real calls left behind, and this reads it.
"""

from __future__ import annotations

import json

from tests.smoke.installed_build import InstalledCli

DAY = "2026-09-17"

CALLS = [
    {
        "run_id": "smoke-run",
        "prompt_id": "landscape.classify-position",
        "prompt_version": "1.0.0",
        "model_id": "anthropic.claude-haiku-5-5",
        "attempt": 1,
        "input_tokens": 1200,
        "output_tokens": 300,
        "latency_ms": 900.0,
        "estimated_cost_usd": None,
        "recorded_at": "2026-09-17T15:00:00Z",
    },
    {
        "run_id": "smoke-run",
        "prompt_id": "model.repair",
        "prompt_version": "1.0.0",
        "model_id": "anthropic.claude-haiku-5-5",
        "attempt": 2,
        "input_tokens": 1500,
        "output_tokens": 200,
        "latency_ms": 950.0,
        "estimated_cost_usd": 0.0025,
        "recorded_at": "2026-09-17T15:00:01Z",
    },
]


def write_day(installed_cli: InstalledCli) -> None:
    usage = installed_cli.data_dir / "usage"
    usage.mkdir(parents=True, exist_ok=True)
    (usage / f"{DAY}.jsonl").write_text("".join(json.dumps(call) + "\n" for call in CALLS), encoding="utf-8")


def test_usage_is_installed_with_its_help(installed_cli: InstalledCli) -> None:
    run = installed_cli.run("usage", "--help")

    assert run.exit_code == 0, run.output
    assert "--date" in run.stdout


def test_usage_adds_up_a_days_log_by_prompt_and_model(installed_cli: InstalledCli) -> None:
    write_day(installed_cli)

    run = installed_cli.run("--json", "usage", "--date", DAY)

    assert run.exit_code == 0, run.output
    data = run.envelope()["data"]
    assert isinstance(data, dict)
    assert data["groups"] == [
        {
            "prompt_id": "landscape.classify-position",
            "model_id": "anthropic.claude-haiku-5-5",
            "calls": 1,
            "input_tokens": 1200,
            "output_tokens": 300,
            "estimated_cost_usd": 0.0,
            "unpriced_calls": 1,
        },
        {
            "prompt_id": "model.repair",
            "model_id": "anthropic.claude-haiku-5-5",
            "calls": 1,
            "input_tokens": 1500,
            "output_tokens": 200,
            "estimated_cost_usd": 0.0025,
            "unpriced_calls": 0,
        },
    ]
    assert data["totals"] == {
        "calls": 2,
        "input_tokens": 2700,
        "output_tokens": 500,
        "estimated_cost_usd": 0.0025,
        "unpriced_calls": 1,
    }


def test_usage_refuses_a_date_that_is_not_one(installed_cli: InstalledCli) -> None:
    run = installed_cli.run("usage", "--date", "2026-02-30")

    assert run.exit_code == 2, run.output
