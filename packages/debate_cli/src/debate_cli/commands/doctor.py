"""`debate-research doctor`: what this installation is, before anything else is blamed.

The first question about a failed run is which CLI, which Python and which configuration produced
it, and on a student's laptop the answer is rarely the one assumed. `doctor` answers it in both
output modes, and in doing so is the worked example of the command pattern: parse nothing, ask the
composition root, render through :mod:`debate_cli.output`.

It reports what exists today. The checks that need settings — which data directory is in use,
which providers have credentials, whether the evidence store is reachable — are added here as
their tasks land, starting with v1-e02-t05 (settings) and v1-e01-t09 (environment profiles).
"""

from __future__ import annotations

import platform
import sys

import typer

from debate_cli import package_version
from debate_cli.container import SERVICE_NAMES, ServiceContainer
from debate_cli.context import cli_context, command_name
from debate_cli.output import JsonValue, TableSpec

__all__ = ["doctor"]


def doctor(ctx: typer.Context) -> None:
    """Report the versions, interpreter and wiring this installation is running with."""
    cli = cli_context(ctx)
    cli.output.detail("collecting environment facts")
    report = environment_report(cli.services)
    cli.output.success(
        command_name(ctx),
        report,
        display=TableSpec(
            columns=("Check", "Value"),
            rows=_rows(report),
            title="debate-research doctor",
        ),
    )


def environment_report(services: ServiceContainer) -> dict[str, JsonValue]:
    """The facts `doctor` reports, as the `--json` envelope's `data`."""
    return {
        "cli_version": package_version("debate-cli"),
        "core_version": package_version("debate-core"),
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "settings_configured": services.settings_configured,
        "services": list(SERVICE_NAMES),
    }


def _rows(report: dict[str, JsonValue]) -> list[list[str]]:
    """One `label, value` row per fact, in the order :func:`environment_report` lists them."""
    labels = {
        "cli_version": "debate-cli",
        "core_version": "debate-core",
        "python_version": "Python",
        "python_executable": "Interpreter",
        "platform": "Platform",
        "settings_configured": "Settings loaded",
        "services": "Services wired",
    }
    return [[labels.get(key, key), _as_text(value)] for key, value in report.items()]


def _as_text(value: JsonValue) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "none"
    return str(value)
