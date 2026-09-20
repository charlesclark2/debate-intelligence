"""Where every `debate-research` command is attached to the root application.

V1 fills this package up over several epics — `verify` (E03), `fetch` (E04), `search` and `cut`
(E08), `daily`, `config`, `store` (v1-e29-t05), `caselist` (E30, E34), `landscape` (E32) and
`files` (E33) — so registration happens in one function, :func:`register_commands`, rather than
through decorators scattered across modules. Reading it tells you the whole surface.

## Adding a plain command

Write the command function in its own module (one module per command), then register it::

    from debate_cli.commands import verify

    def register_commands(app: typer.Typer) -> None:
        app.command("verify")(verify.verify)

The function's docstring is its `--help` text.

## Adding a command group

Commands like `store` and `caselist` are groups with subcommands (`debate-research store sync`).
Build the group with :func:`command_group`, register its subcommands on it, and add it to the
root app::

    from debate_cli.commands import store

    def register_commands(app: typer.Typer) -> None:
        evidence_store = command_group("store", "Work with the evidence store.")
        evidence_store.command("sync")(store.sync)
        evidence_store.command("status")(store.status)
        app.add_typer(evidence_store)

Groups need nothing else. They inherit the run's `CliContext` (Click passes `ctx.obj` down), and
their failures are reported and given an exit code by
:class:`~debate_cli.app.DebateResearchGroup`, which wraps every level of the invocation.
"""

from __future__ import annotations

import typer

from debate_cli.commands import doctor

__all__ = ["command_group", "register_commands"]


def register_commands(app: typer.Typer) -> None:
    """Attach every command and command group to the root application."""
    app.command("doctor")(doctor.doctor)


def command_group(name: str, help_text: str) -> typer.Typer:
    """Create a subcommand group for the root app, configured the way all of them are.

    `no_args_is_help` is the reason this is a function rather than a bare `typer.Typer(...)`:
    `debate-research store` with no subcommand should list what `store` can do, not fail silently.
    """
    return typer.Typer(name=name, help=help_text, no_args_is_help=True)
