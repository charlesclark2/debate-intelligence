"""Where every `debate-research` command is attached to the root application.

V1 fills this package up over several epics — `verify` (E03), `fetch` (E04), `search` and `cut`
(E08), `daily`, `config`, `store` (v1-e29-t05), `caselist` (E30, E34), `landscape` (E32),
`files` (E33) and `tub` (E39) — so registration happens in one function,
:func:`register_commands`, rather than through decorators scattered across modules. Reading it
tells you the whole surface.

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

from debate_cli.commands import (
    caselist,
    caselist_auth,
    caselist_cards,
    caselist_parse,
    caselist_pull,
    caselist_remove,
    caselist_retire,
    caselist_runs,
    config,
    doctor,
    landscape,
    store,
    tub_index,
    tub_users,
    verify,
)

__all__ = ["command_group", "register_commands"]


def register_commands(app: typer.Typer) -> None:
    """Attach every command and command group to the root application."""
    app.command("doctor")(doctor.doctor)
    app.command("verify")(verify.verify)

    configuration = command_group("config", "Inspect the settings this installation runs with.")
    configuration.command("show")(config.show)
    app.add_typer(configuration)

    disclosed_evidence = command_group("caselist", "Import, publish and check disclosed caselist evidence.")
    disclosed_evidence.command("cards")(caselist_cards.cards)
    disclosed_evidence.command("import")(caselist.import_archive)
    disclosed_evidence.command("import-openev")(caselist.import_openev)
    disclosed_evidence.command("parse")(caselist_parse.parse)
    disclosed_evidence.command("publish")(caselist.publish)
    disclosed_evidence.command("pull")(caselist_pull.pull)
    disclosed_evidence.command("reimport-openev-metadata")(caselist.reimport_openev_metadata)
    disclosed_evidence.command("remove")(caselist_remove.remove)
    disclosed_evidence.command("retire")(caselist_retire.retire)
    disclosed_evidence.command("runs")(caselist_runs.runs)
    disclosed_evidence.command("status")(caselist.status)
    disclosed_evidence.command("unsuppress")(caselist_remove.unsuppress)

    opencaselist_session = command_group("auth", "Log in to OpenCaselist and manage the stored token.")
    opencaselist_session.command("login")(caselist_auth.login)
    opencaselist_session.command("status")(caselist_auth.status)
    opencaselist_session.command("logout")(caselist_auth.logout)
    opencaselist_session.command("set-password")(caselist_auth.set_password)
    opencaselist_session.command("renew")(caselist_auth.renew)
    disclosed_evidence.add_typer(opencaselist_session)
    app.add_typer(disclosed_evidence)

    argument_landscape = command_group(
        "landscape", "Argument landscape reports: what positions a caselist reads."
    )
    argument_landscape.command("report")(landscape.report)
    app.add_typer(argument_landscape)

    evidence_store = command_group("store", "Move evidence between this machine and its bucket.")
    evidence_store.command("sync")(store.sync)
    evidence_store.command("ls")(store.ls)
    evidence_store.command("get")(store.get)
    app.add_typer(evidence_store)

    # The student search pilot (E39): its index (v1-e39-t02) and its users (v1-e39-t05).
    search_pilot = command_group("tub", "The team's student evidence search pilot: its index and its users.")
    search_index = command_group("index", "Build the search pilot's index and publish it to a bucket.")
    search_index.command("build")(tub_index.build)
    search_index.command("publish")(tub_index.publish)
    search_pilot.add_typer(search_index)
    pilot_accounts = command_group(
        "users", "The coach's accounts for the pilot: add, list, reset, disable, remove."
    )
    pilot_accounts.command("add")(tub_users.add)
    pilot_accounts.command("list")(tub_users.list_accounts)
    pilot_accounts.command("reset")(tub_users.reset)
    pilot_accounts.command("disable")(tub_users.disable)
    pilot_accounts.command("enable")(tub_users.enable)
    pilot_accounts.command("remove")(tub_users.remove)
    pilot_accounts.command("email-second-factor")(tub_users.email_second_factor)
    search_pilot.add_typer(pilot_accounts)
    app.add_typer(search_pilot)


def command_group(name: str, help_text: str) -> typer.Typer:
    """Create a subcommand group for the root app, configured the way all of them are.

    `no_args_is_help` is the reason this is a function rather than a bare `typer.Typer(...)`:
    `debate-research store` with no subcommand should list what `store` can do, not fail silently.
    """
    return typer.Typer(name=name, help=help_text, no_args_is_help=True)
