"""The `debate-research` root application: global options, and one place where failures end.

`debate-research` is a command group. Its callback runs before every command, turns the global
options into a :class:`~debate_cli.context.CliContext`, and leaves it where subcommands find it;
:class:`DebateResearchGroup` wraps the whole invocation so that any exception a command raises —
at any depth, in `verify`, in `store sync`, in a group a later epic adds — is reported once,
through :mod:`debate_cli.output`, and exits with the code
:func:`~debate_cli.exit_codes.exit_code_for` gives it.

The pattern every command follows, with nothing else in it::

    def doctor(ctx: typer.Context) -> None:
        cli = cli_context(ctx)                     # 1. the run's output and services
        report = cli.services.something.run(...)   # 2. work, done by debate_core
        cli.output.success(command_name(ctx), report, display=...)   # 3. render

A command does not catch `DomainError`, does not call `sys.exit`, and does not print. That is what
keeps the exit codes and the `--json` envelope identical across commands written months apart by
different tasks.
"""

from __future__ import annotations

import traceback
from typing import Annotated, Any

import typer
from typer.core import TyperGroup

from debate_cli import DISTRIBUTION_NAME, package_version
from debate_cli.commands import register_commands
from debate_cli.container import ServiceContainer
from debate_cli.context import CliContext, command_name
from debate_cli.exit_codes import ExitCode
from debate_cli.output import CliOutput, CommandFailure, OutputMode
from debate_core.application.errors import DomainError
from debate_core.application.settings import load_settings

__all__ = ["APP_NAME", "DebateResearchGroup", "app", "create_app", "main"]

APP_NAME = "debate-research"

_HELP = """
Debate evidence research: find sources, cut cards, and verify that every card is reproducible
from a stored snapshot of what it quotes.
"""


class DebateResearchGroup(TyperGroup):
    """The root group, which is also the CLI's only error handler.

    Click already gives usage errors the right exit status (2); what this adds is the `--json`
    envelope for them, and the translation of everything else — a `DomainError` from a service, a
    bug in a command — into the documented exit code with a single rendered failure.

    Commands and subgroups need nothing to take part: every one of them is invoked inside
    :meth:`invoke`, however deeply nested.
    """

    def make_context(self, info_name: str | None, args: list[str], parent: Any = None, **extra: Any) -> Any:
        """Parse the root command line, reporting a parse failure in the requested shape.

        Parsing happens before the callback runs, so there is no `CliContext` yet and no parsed
        `--json` flag to consult: the raw arguments are all there is to go on. They are read
        before parsing starts, because Click's parser consumes the list it is given.
        """
        json_requested = _json_requested(args)
        try:
            return super().make_context(info_name, args, parent=parent, **extra)
        except typer.TyperException as exception:
            if json_requested:
                CliOutput(OutputMode.JSON).failure(CommandFailure.from_exception(exception))
            raise

    def invoke(self, ctx: Any) -> Any:
        """Run the callback and the chosen command, mapping any failure onto an exit code."""
        try:
            return super().invoke(ctx)
        except (typer.Exit, typer.Abort):
            # Already a decision about how this run ends; nothing to report or translate.
            raise
        except typer.TyperException as exception:
            # A usage error from resolving the command name or parsing a subcommand's own
            # options. Typer prints it and exits 2 itself; this only adds the envelope a --json
            # consumer is owed. `exception.ctx` is the level that failed, which is where the
            # command name comes from — `nope` in `debate-research --json nope` has no context at
            # all, and is reported with a null command.
            output = _output_of(ctx)
            if output.is_json:
                failing_ctx = getattr(exception, "ctx", None) or ctx
                output.failure(
                    CommandFailure.from_exception(exception),
                    command=command_name(failing_ctx) or None,
                )
            raise
        except DomainError as exception:
            raise self._reported(ctx, exception) from exception
        except Exception as exception:
            output = _output_of(ctx)
            output.detail(traceback.format_exc())
            raise self._reported(
                ctx,
                exception,
                hint="This is a bug in debate-research. Re-run with --verbose for the traceback.",
            ) from exception

    def _reported(self, ctx: Any, exception: Exception, *, hint: str | None = None) -> typer.Exit:
        """Report `exception` and return the `typer.Exit` that ends the run with its code."""
        cli = _cli_of(ctx)
        failure = CommandFailure.from_exception(exception, hint=hint)
        _output_of(ctx).failure(failure, command=cli.command if cli is not None else None)
        return typer.Exit(code=failure.exit_code)


def create_app() -> typer.Typer:
    """Build the `debate-research` application.

    Tests build their own with this function and register a command on it, which is how the
    error handling and the exit codes are exercised without waiting for a real command to exist.
    """
    app = typer.Typer(
        name=APP_NAME,
        cls=DebateResearchGroup,
        help=_HELP,
        invoke_without_command=True,
        add_completion=False,
        # This CLI renders its own failures (debate_cli.output); Typer's pretty tracebacks would
        # print a second, differently shaped one on top.
        pretty_exceptions_enable=False,
        context_settings={"help_option_names": ["-h", "--help"]},
    )
    app.callback()(root_callback)
    register_commands(app)
    return app


def root_callback(
    ctx: typer.Context,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Write progress and diagnostics to stderr."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Write one machine-readable JSON object to stdout."),
    ] = False,
    show_version: Annotated[
        bool,
        typer.Option("--version", help="Show the installed version and exit.", is_eager=True),
    ] = False,
) -> None:
    """Runs before every command: turns the global options into this run's CliContext."""
    output = CliOutput(OutputMode.JSON if json_output else OutputMode.RICH, verbose=verbose)
    # The loader is passed, not called: the container runs it the first time a command asks for
    # settings, so `--help` and `--version` never read a profile file (v1-e02-t05).
    ctx.obj = CliContext(output=output, services=ServiceContainer(settings_loader=load_settings))

    if show_version:
        # Handled here rather than in an option callback so that `--json --version` gets the
        # envelope like any other result.
        output.success(
            "version",
            {"package": DISTRIBUTION_NAME, "version": package_version()},
            display=f"{APP_NAME} {package_version()}",
        )
        raise typer.Exit(code=ExitCode.OK)

    if ctx.invoked_subcommand is None:
        if not output.is_json:
            # A person who typed the bare command wants the command list. Typer renders its rich
            # help itself, to stdout, and then returns an empty string; the fallback is for a
            # Typer that returns the text instead, which then belongs on stderr with the failure.
            help_text = ctx.get_help()
            if help_text:
                output.note(help_text)
        output.failure(
            CommandFailure(
                code=ExitCode.USAGE_ERROR.name,
                message="no command given",
                exit_code=ExitCode.USAGE_ERROR,
                hint=f"Run `{APP_NAME} --help` for the list of commands.",
            )
        )
        raise typer.Exit(code=ExitCode.USAGE_ERROR)


app = create_app()
"""The application the `debate-research` console script runs."""


def main() -> None:
    """Console-script entry point (`debate-research`), registered in pyproject.toml."""
    app()


def _cli_of(ctx: Any) -> CliContext | None:
    """The run's :class:`CliContext`, or `None` if the root callback has not built it yet."""
    obj = getattr(ctx, "obj", None)
    return obj if isinstance(obj, CliContext) else None


def _output_of(ctx: Any) -> CliOutput:
    """The run's console.

    A failure can happen before the callback builds one — an unknown command name is resolved
    first — and the global options are then read from the root command line Click has already
    parsed. The names are the root callback's parameters, not the option spellings.
    """
    cli = _cli_of(ctx)
    if cli is not None:
        return cli.output
    params: dict[str, Any] = getattr(ctx, "params", None) or {}
    mode = OutputMode.JSON if params.get("json_output") else OutputMode.RICH
    return CliOutput(mode, verbose=bool(params.get("verbose")))


def _json_requested(args: list[str]) -> bool:
    """Whether `--json` appears in raw arguments that could not be parsed.

    The root group's options are all flags, so a bare scan is exact for the root command line; an
    unparseable *subcommand* line never reaches this, because by then the callback has run and the
    real flag is known.
    """
    return "--json" in args
