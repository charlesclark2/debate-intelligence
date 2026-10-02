"""`debate-research doctor`: what this installation is, before anything else is blamed.

The first question about a failed run is which CLI, which Python and which configuration produced
it, and on a student's laptop the answer is rarely the one assumed. `doctor` answers it in both
output modes, and in doing so is the worked example of the command pattern: parse nothing, ask the
composition root, render through :mod:`debate_cli.output`.

It reports what exists today. The checks that need settings — which data directory is in use,
which providers have credentials, whether the evidence store is reachable — are added here as
their tasks land, starting with v1-e02-t05 (settings) and v1-e01-t09 (environment profiles).

## Exit codes

`doctor` fails on one check only, the one it can state precisely (`v1-e01-t14`):

* `0`: the report was produced and the running Python's Unicode database is the one the current
  evidence normalizer is pinned to.
* `1` (`DOMAIN_FAILURE`): the two databases differ. Under any other database `normalize` refuses to
  run (`UnicodeDatabaseMismatchError`), so every command that touches evidence text would fail on
  first use. The error names both versions and the policy page, `docs/evidence/normalization.md`,
  and carries the whole report in `error.details`. `scripts/install_channel.sh` runs `doctor` before
  it replaces an install, so an install on the wrong interpreter is refused there.
* `70` (`INTERNAL_ERROR`): `doctor` could not determine the pinned version at all, which only a
  broken build can cause. That is a bug, not a verdict on the interpreter, so it surfaces through
  the root handler like any other unmodelled exception, with its "This is a bug" hint.

Every other fact is description and never changes the exit status: an unloaded settings file, an
unknown package version, an unexpected Python version or platform. None of them is a failure this
command can state precisely, and a `doctor` that guessed would be worse than one that only
describes.
"""

from __future__ import annotations

import platform
import sys
import unicodedata
from collections.abc import Mapping

import typer

from debate_cli import package_version
from debate_cli.container import SERVICE_NAMES, ServiceContainer
from debate_cli.context import cli_context, command_name
from debate_cli.exit_codes import ExitCode
from debate_cli.output import CommandFailure, JsonValue, TableSpec
from debate_core.evidence.normalization import NORMALIZER_VERSION, pinned_unicode_version

__all__ = ["doctor"]

UNICODE_DATABASE_MISMATCH_CODE = "UNICODE_DATABASE_MISMATCH"
NORMALIZATION_POLICY_PAGE = "docs/evidence/normalization.md"


def doctor(ctx: typer.Context) -> None:
    """Report the versions, interpreter and wiring this installation is running with.

    Exit codes:
    0   the report was produced, and this Python's Unicode database is the one the evidence
        normalizer is pinned to
    1   the Unicode databases differ: commands that normalize evidence text would refuse to run
        (the error names both versions and docs/evidence/normalization.md)
    70  the pinned version could not be determined, which is a bug in the build
    Every other fact is reported for information and never fails the command.
    """
    cli = cli_context(ctx)
    cli.output.detail("collecting environment facts")
    report = environment_report(cli.services)
    failure = unicode_database_failure(report)
    # A program gets one envelope: the report under `data`, or under `error.details` on a failure.
    # A person gets the table either way, then the failure's panel.
    if failure is None or not cli.output.is_json:
        cli.output.success(
            command_name(ctx),
            report,
            display=TableSpec(columns=("Check", "Value"), rows=_rows(report), title="debate-research doctor"),
        )
    if failure is not None:
        cli.output.failure(failure, command=command_name(ctx))
        raise typer.Exit(code=failure.exit_code)


def environment_report(services: ServiceContainer) -> dict[str, JsonValue]:
    """The facts `doctor` reports, as the `--json` envelope's `data`."""
    pinned = pinned_unicode_version(NORMALIZER_VERSION)
    running = unicodedata.unidata_version
    return {
        "cli_version": package_version("debate-cli"),
        "core_version": package_version("debate-core"),
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "settings_configured": services.settings_configured,
        "services": list(SERVICE_NAMES),
        "normalizer_version": NORMALIZER_VERSION,
        "normalizer_unicode_version": pinned,
        "python_unicode_version": running,
        "unicode_database_matches": running == pinned,
    }


def unicode_database_failure(report: Mapping[str, JsonValue]) -> CommandFailure | None:
    """The one failure `doctor` reports, or None: the two Unicode databases differ."""
    pinned = report["normalizer_unicode_version"]
    running = report["python_unicode_version"]
    if running == pinned:
        return None
    return CommandFailure(
        code=UNICODE_DATABASE_MISMATCH_CODE,
        message=(
            f"This Python's Unicode database is {running}, but {report['normalizer_version']} is pinned "
            f"to Unicode {pinned}, so every command that normalizes evidence text will refuse to run. "
            f"See {NORMALIZATION_POLICY_PAGE}."
        ),
        exit_code=ExitCode.DOMAIN_FAILURE,
        details=dict(report),
        hint=(
            "Install debate-research with scripts/install_channel.sh, which runs it on a Python that "
            "debate_core's Requires-Python admits. In a checkout, `uv sync` uses .python-version."
        ),
    )


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
        "normalizer_version": "Evidence normalizer",
        "normalizer_unicode_version": "Normalizer's Unicode",
        "python_unicode_version": "Python's Unicode",
        "unicode_database_matches": "Unicode matches pin",
    }
    return [[labels.get(key, key), _as_text(value)] for key, value in report.items()]


def _as_text(value: JsonValue) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "none"
    return str(value)
