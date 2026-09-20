"""The exit codes `debate-research` returns, and the one place a failure is turned into one.

A script that runs the CLI — a caselist sync on a schedule, a Makefile, another agent — decides
what to do next from the exit code alone, so the numbers are part of the CLI's public contract and
are fixed here rather than at each `raise`:

`0` — `OK`
    The command did what it was asked to do.

`1` — `DOMAIN_FAILURE`
    The command ran and the answer is a failure: a card is `UNVERIFIED`, a record was not found,
    a write lost its revision check. Running the same command again gives the same answer.

`2` — `USAGE_ERROR`
    The command line was wrong: unknown command or option, missing argument, no command given.
    Nothing was executed.

`3` — `RETRIEVAL_FAILURE`
    An external provider — search, fetch, a model — failed or rate-limited the call. The same
    command may well succeed later, which is why this is not `DOMAIN_FAILURE`.

`70` — `INTERNAL_ERROR`
    A bug: an exception the CLI does not model. 70 is `EX_SOFTWARE` from `sysexits.h`.

Later command tasks import :class:`ExitCode` instead of writing the numbers down again::

    raise typer.Exit(code=ExitCode.DOMAIN_FAILURE)

Most commands never need to: :class:`~debate_cli.app.DebateResearchGroup` catches what a command
raises and applies :func:`exit_code_for` for it. A command only chooses a code itself when the
failure is an *outcome* rather than an exception — `verify` reporting an `UNVERIFIED` card is the
V1 example, and it reports that outcome through
:meth:`~debate_cli.output.CliOutput.failure` and then exits with `DOMAIN_FAILURE`.

`debate_core` never imports this module: an exit code is a property of a command-line surface, not
of the domain.
"""

from __future__ import annotations

import re
from enum import IntEnum

import typer

from debate_core.application.errors import DomainError, ProviderError

__all__ = ["ExitCode", "error_code_for", "exit_code_for"]


class ExitCode(IntEnum):
    """Every status `debate-research` can exit with. See the table in the module docstring."""

    OK = 0
    DOMAIN_FAILURE = 1
    USAGE_ERROR = 2
    RETRIEVAL_FAILURE = 3
    INTERNAL_ERROR = 70


def exit_code_for(exception: BaseException) -> ExitCode:
    """Return the exit code that `exception` ends the process with.

    The order of the checks is the contract: a provider failure is a `ProviderError` *and* a
    `DomainError`, and it is the more specific answer (3, "try again later") that callers want.

    Click-family errors (`typer.TyperException` and its `UsageError` subclasses) already carry the
    code Typer's standalone runner exits with, so this reports that number rather than inventing a
    second one — which is what keeps the JSON envelope's `exit_code` equal to the real exit status.
    """
    if isinstance(exception, typer.Exit):
        return _known_exit_code(exception.exit_code)
    if isinstance(exception, typer.TyperException):
        return _known_exit_code(exception.exit_code)
    if isinstance(exception, ProviderError):
        return ExitCode.RETRIEVAL_FAILURE
    if isinstance(exception, DomainError):
        return ExitCode.DOMAIN_FAILURE
    return ExitCode.INTERNAL_ERROR


def error_code_for(exception: BaseException) -> str:
    """Return the machine-readable error code for `exception`, e.g. `"REVISION_MISMATCH"`.

    This is the `error.code` a `--json` consumer branches on. For a
    :class:`~debate_core.application.errors.DomainError` it is the class name in upper snake case,
    so the code a script sees and the class a developer reads are the same word; for everything
    else it is the name of the exit code.
    """
    if isinstance(exception, DomainError):
        return _upper_snake_case(type(exception).__name__)
    return exit_code_for(exception).name


def _known_exit_code(value: int) -> ExitCode:
    """Return `value` as an :class:`ExitCode`, or `INTERNAL_ERROR` if it is not one of ours."""
    try:
        return ExitCode(value)
    except ValueError:
        return ExitCode.INTERNAL_ERROR


def _upper_snake_case(class_name: str) -> str:
    """`"RevisionMismatch"` → `"REVISION_MISMATCH"`."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", class_name).upper()
