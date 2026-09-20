"""`debate-research config show`: what this run is actually configured with, and why.

Configuration comes from five places — a flag, the environment, `.env`, the environment profile,
the built-in profile — and the question that follows every surprise is which of them supplied the
value in front of you. This command answers it: one row per setting, with the value and its
source, in either output mode.

Every secret is replaced with `***` before it reaches either surface, and that is not this
command's decision to make: it renders
:meth:`~debate_core.application.settings.Settings.redacted_dict`, which is the only way settings
are allowed to leave `debate_core`. A command that reached into `Settings` for a raw `SecretStr`
would be one `--verbose` away from putting an OpenCaselist token in a terminal scrollback.

The command follows the pattern in :mod:`debate_cli.app`: it parses nothing, asks the composition
root for the settings, and renders what comes back. Loading and validating them is
`debate_core`'s work, and a bad value arrives here as a
:class:`~debate_core.application.settings.ConfigurationError`, which the root group already
reports and turns into an exit code — this module does not catch it.
"""

from __future__ import annotations

import typer

from debate_cli.context import cli_context, command_name
from debate_cli.output import JsonValue, TableSpec
from debate_core.application.settings import Settings

__all__ = ["show", "settings_report"]


def show(ctx: typer.Context) -> None:
    """Print the effective settings, with every secret redacted and each value's source."""
    cli = cli_context(ctx)
    cli.output.detail("loading settings")
    settings = cli.services.settings
    report = settings_report(settings)
    cli.output.success(
        command_name(ctx),
        report,
        display=TableSpec(
            columns=("Setting", "Value", "Source"),
            rows=_rows(settings),
            title=f"debate-research configuration ({settings.environment.value})",
            caption="Secrets are shown as *** and are never printed in full.",
        ),
    )


def settings_report(settings: Settings) -> dict[str, JsonValue]:
    """The `--json` envelope's `data`: the settings, and where each one came from.

    Two flat mappings rather than one mapping of `{value, source}` objects, so that the common
    read stays a single lookup — `.data.settings["storage.data_dir"]` — and a consumer that only
    wants values never has to unwrap anything. Keys are dotted paths and are identical in both.
    """
    values = settings.redacted_dict()
    sources = settings.field_sources
    return {
        "environment": settings.environment.value,
        "settings": {key: _as_json(value) for key, value in values.items()},
        "sources": {key: sources.get(key, "default") for key in values},
    }


def _rows(settings: Settings) -> list[list[str]]:
    """One `setting, value, source` row per field, in the order the settings model declares them."""
    sources = settings.field_sources
    return [
        [key, _as_text(value), sources.get(key, "default")] for key, value in settings.redacted_dict().items()
    ]


def _as_json(value: object) -> JsonValue:
    """`redacted_dict` already returns JSON scalars and lists; this only narrows the type."""
    if isinstance(value, str | int | float | bool | None):
        return value
    if isinstance(value, list):
        return [_as_json(item) for item in value]
    return str(value)


def _as_text(value: object) -> str:
    """The same value as a person reads it in the table."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if value is None:
        return "not set"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "none"
    return str(value)
