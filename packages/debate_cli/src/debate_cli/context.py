"""What every command receives: the output console and the composition root.

Typer gives a command its own arguments; these two are what the *run* has — the mode the user
asked for (`--verbose`, `--json`) and the services available to it. The root callback builds one
:class:`CliContext` and stores it on Click's context object, where every subcommand at every depth
inherits it, so a command's first line is::

    cli = cli_context(ctx)

and never a module-level global.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import typer

from debate_cli.container import ServiceContainer
from debate_cli.output import CliOutput, OutputMode

__all__ = ["CliContext", "cli_context", "command_name"]


@dataclass(slots=True)
class CliContext:
    """The per-run state of the CLI, built once by the root callback."""

    output: CliOutput
    services: ServiceContainer
    command: str | None = None
    """The command that is running, recorded by :func:`cli_context` when the command starts.

    The error handler is the root group, whose own Click context knows only that *something*
    below it failed, so the name is taken from here when a failure has to say which command
    produced it.
    """

    @property
    def verbose(self) -> bool:
        return self.output.verbose

    @property
    def json_output(self) -> bool:
        return self.output.mode is OutputMode.JSON


def cli_context(ctx: typer.Context) -> CliContext:
    """Return the :class:`CliContext` the root callback stored for this run.

    Calling this is also how a command announces itself: the returned context records
    :func:`command_name`, so a failure raised anywhere inside the command can be reported under
    the name the user typed.

    A missing or wrong object means a command was wired up outside
    :func:`debate_cli.app.create_app`, which is a programming error rather than a user's mistake:
    it raises here and is reported as exit 70.
    """
    obj = ctx.obj
    if not isinstance(obj, CliContext):
        raise RuntimeError(
            "no CliContext on the Click context: this command was not reached through "
            "debate_cli.app.create_app()"
        )
    obj.command = command_name(ctx)
    return obj


def command_name(ctx: typer.Context) -> str:
    """The command as the user typed it, without the program name: `"doctor"`, `"store sync"`.

    This is what the `--json` envelope reports as `command`, so a scheduled consumer can tell
    which command produced the object it is reading.
    """
    parts: list[str] = []
    # Walked with `Any` because Click types `Context.parent` as its own base class, which Typer
    # vendors privately and does not re-export; only `info_name` and `parent` are touched.
    node: Any = ctx
    while node.parent is not None:
        if node.info_name is not None:
            parts.append(str(node.info_name))
        node = node.parent
    return " ".join(reversed(parts))
