"""`debate-research doctor`: what this installation is, before anything else is blamed.

The first question about a failed run is which CLI, which Python and which configuration produced
it, and on a student's laptop the answer is rarely the one assumed. `doctor` answers it in both
output modes, and in doing so is the worked example of the command pattern: parse nothing, ask the
composition root, render through :mod:`debate_cli.output`.

It reports what exists today. The checks that need settings — which data directory is in use,
which providers have credentials, whether the evidence store is reachable — are added here as
their tasks land, starting with v1-e02-t05 (settings) and v1-e01-t09 (environment profiles).

## Exit codes

`doctor` fails on two checks only, the ones it can state precisely:

* **The Unicode database** (`v1-e01-t14`). Under any database but the one the current evidence
  normalizer is pinned to, `normalize` refuses to run (`UnicodeDatabaseMismatchError`), so every
  command that touches evidence text would fail on first use. The error names both versions and the
  policy page, `docs/evidence/normalization.md`.
* **The wired integrations** (`v1-e01-t22`). Every `debate_core.integrations` module the composition
  root imports must import. The list and the imports are :func:`debate_cli.installation.check_installation`,
  the same logic as the installer's post-install check, so there is no second list to keep up. Each
  module that does not import is named, with why, and a command that uses it would fail.

* `0`: the report was produced, and both checks passed.
* `1` (`DOMAIN_FAILURE`): a check failed. One failure has its own code, `UNICODE_DATABASE_MISMATCH`
  or `INTEGRATIONS_DO_NOT_IMPORT`; both at once are `INSTALLATION_CHECKS_FAILED`, with both messages.
  `--json` carries the whole report in `error.details`. `scripts/install_channel.sh` runs `doctor`
  before it replaces an install, so a build that fails either check is refused there.
* `70` (`INTERNAL_ERROR`): `doctor` could not establish a check at all: the normalizer's pinned
  version is unknown, or the container wires an integration in a way an import statement does not
  show (:class:`~debate_cli.installation.UnfollowableWiring`). Only a broken build causes either.
  That is a bug, not a verdict on the installation, so it surfaces through the root handler like any
  other unmodelled exception, with its "This is a bug" hint.

Every other fact is description and never changes the exit status: an unloaded settings file, an
unknown package version, an unexpected Python version or platform, and a declared `debate-core`
extra whose distributions are not installed. That last one is not a failure `doctor` can state
precisely: nothing breaks until a wired integration needs the distribution, and then the
integration check names it. The installer's own check (`python -m debate_cli.installation`) holds a
build to everything it declares and refuses it at install. A `doctor` that guessed would be worse
than one that only describes.
"""

from __future__ import annotations

import platform
import sys
import unicodedata
from collections.abc import Mapping
from dataclasses import replace

import typer

from debate_cli import installation, package_version
from debate_cli.container import SERVICE_NAMES, ServiceContainer
from debate_cli.context import cli_context, command_name
from debate_cli.exit_codes import ExitCode
from debate_cli.output import CommandFailure, JsonValue, TableSpec
from debate_core.evidence.normalization import NORMALIZER_VERSION, pinned_unicode_version

__all__ = ["doctor"]

UNICODE_DATABASE_MISMATCH_CODE = "UNICODE_DATABASE_MISMATCH"
INTEGRATIONS_DO_NOT_IMPORT_CODE = "INTEGRATIONS_DO_NOT_IMPORT"
INSTALLATION_CHECKS_FAILED_CODE = "INSTALLATION_CHECKS_FAILED"
NORMALIZATION_POLICY_PAGE = "docs/evidence/normalization.md"
_MISMATCH_FACTS = ("normalizer_version", "normalizer_unicode_version", "python_unicode_version")


def doctor(ctx: typer.Context) -> None:
    """Report the versions, interpreter and wiring this installation is running with.

    Exit codes:
    0   the report was produced, this Python's Unicode database is the one the evidence
        normalizer is pinned to, and every integration the CLI wires imports
    1   a check failed: the Unicode databases differ, so commands that normalize evidence text
        would refuse to run (the error names both versions and docs/evidence/normalization.md),
        or a wired integration does not import (the error names each one, with why)
    70  a check could not be made at all (the pinned version is unknown, or the CLI wires an
        integration in a way that cannot be followed), which is a bug in the build
    Every other fact is reported for information and never fails the command, including a
    declared extra whose packages are missing.
    """
    cli = cli_context(ctx)
    cli.output.detail("collecting environment facts")
    report = environment_report(cli.services)
    failure = doctor_failure(report)
    # A program gets one envelope: the report under `data`, or under `error.details` on a failure.
    # A person gets the table either way, then the failure's panel.
    if failure is None or not cli.output.is_json:
        cli.output.success(
            command_name(ctx),
            report,
            display=TableSpec(columns=("Check", "Value"), rows=_rows(report), title="debate-research doctor"),
        )
    if failure is not None:
        if not cli.output.is_json:
            # The table above already lists every fact; the panel names only what failed.
            failure = replace(failure, details=_failed_facts(report))
        cli.output.failure(failure, command=command_name(ctx))
        raise typer.Exit(code=failure.exit_code)


def environment_report(services: ServiceContainer) -> dict[str, JsonValue]:
    """The facts `doctor` reports, as the `--json` envelope's `data`."""
    pinned = pinned_unicode_version(NORMALIZER_VERSION)
    running = unicodedata.unidata_version
    integrations = installation.check_installation()
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
        "integrations_wired": list(integrations.wired),
        "integrations_failed": dict(integrations.failed),
        "integrations_import": not integrations.failed,
        "extras_missing_distributions": dict(integrations.missing_distributions),
    }


def doctor_failure(report: Mapping[str, JsonValue]) -> CommandFailure | None:
    """What `doctor` reports as its failure, or None: every check it fails on, together."""
    failures = [
        failure
        for failure in (unicode_database_failure(report), integration_failure(report))
        if failure is not None
    ]
    if len(failures) <= 1:
        return failures[0] if failures else None
    return CommandFailure(
        code=INSTALLATION_CHECKS_FAILED_CODE,
        message=" ".join(failure.message for failure in failures),
        exit_code=ExitCode.DOMAIN_FAILURE,
        details=dict(report),
        hint=" ".join(failure.hint for failure in failures if failure.hint),
    )


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


def integration_failure(report: Mapping[str, JsonValue]) -> CommandFailure | None:
    """The integrations the CLI wires that do not import, each named with why, or None."""
    failed = _failed_integrations(report)
    if not failed:
        return None
    wired = report["integrations_wired"]
    total = len(wired) if isinstance(wired, list) else len(failed)
    named = "; ".join(f"{module} ({reason})" for module, reason in sorted(failed.items()))
    return CommandFailure(
        code=INTEGRATIONS_DO_NOT_IMPORT_CODE,
        message=(
            f"{len(failed)} of the {total} integrations debate-research wires do not import: {named}. "
            "Every command that uses one of them will fail."
        ),
        exit_code=ExitCode.DOMAIN_FAILURE,
        details=dict(report),
        hint=(
            "Reinstall a complete build with `scripts/install_channel.sh <tag>` at a fixed release tag, "
            "never by adding packages by hand. In a checkout, run `uv sync --all-packages` from the "
            "workspace root."
        ),
    )


def _failed_integrations(report: Mapping[str, JsonValue]) -> dict[str, str]:
    failed = report["integrations_failed"]
    if not isinstance(failed, Mapping):  # pragma: no cover - environment_report always writes one
        raise TypeError(f"integrations_failed is {type(failed).__name__}, not a mapping")
    return {str(module): str(reason) for module, reason in failed.items()}


def _failed_facts(report: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    """For a person's panel: the two databases if they differ, and each integration that failed."""
    facts: dict[str, JsonValue] = {}
    if unicode_database_failure(report) is not None:
        facts.update({key: report[key] for key in _MISMATCH_FACTS})
    facts.update(_failed_integrations(report))
    return facts


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
        "integrations_wired": "Integrations wired",
        "integrations_failed": "Integrations failing",
        "integrations_import": "Integrations import",
        "extras_missing_distributions": "Extras' packages missing",
    }
    return [[labels.get(key, key), _as_text(value)] for key, value in report.items()]


def _as_text(value: JsonValue) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "none"
    if isinstance(value, Mapping):
        return "; ".join(f"{key} ({item})" for key, item in value.items()) if value else "none"
    return str(value)
