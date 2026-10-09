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
    Something the command depends on did not answer, so there is no answer yet: an external
    provider (search, fetch, a model) failed or rate-limited the call, or a store could not be read
    or written — it was unavailable, the session for it expired, or it refused access
    (:data:`RETRYABLE_STORE_FAILURES`, `v1-e01-t20`). The same command may well succeed later,
    which is why this is never `DOMAIN_FAILURE`: a script reading the code must be able to tell an
    outage from a verdict.

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
from collections.abc import Iterable
from enum import IntEnum

import typer

from debate_core.application.caselist.removal_service import RemovalIncomplete, TakedownPreflightFailed
from debate_core.application.errors import (
    DomainError,
    ProviderError,
    StoreAccessDenied,
    StoreCredentialsExpired,
    StoreUnavailable,
)

__all__ = [
    "RETRYABLE_STORE_FAILURES",
    "STOPPED_BY_A_STORE",
    "ExitCode",
    "error_code_for",
    "exit_code_for",
    "exit_code_for_failure_codes",
    "is_retryable_store_failure",
]

RETRYABLE_STORE_FAILURES: tuple[type[DomainError], ...] = (
    StoreUnavailable,
    StoreCredentialsExpired,
    StoreAccessDenied,
)
"""The store failures a retry may cure, which end a command with `RETRIEVAL_FAILURE` (3).

Named one by one rather than as their base class, so that the list is the decision: a new
`StoreError` subclass is mapped when someone decides it belongs here, not by inheritance. Nothing
deterministic is on it — :class:`~debate_core.application.errors.NotFound` is an answer, and so are
a refused manifest and an `UNVERIFIED` card.
"""

STOPPED_BY_A_STORE: tuple[type[DomainError], ...] = (TakedownPreflightFailed, RemovalIncomplete)
"""Errors a service raises *from* a store failure, whose own advice is to run the command again.

`caselist remove` and `unsuppress` wrap what stopped them, so the store's failure arrives as the
wrapper's `__cause__`. When that cause is on :data:`RETRYABLE_STORE_FAILURES`, the run ends with
`RETRIEVAL_FAILURE` like the bare failure would; any other cause keeps it a `DOMAIN_FAILURE`.
:class:`~debate_core.application.caselist.removal_service.RemovalCompletedUnlogged` is deliberately
not here: the removal finished, and running it again would log zero counts, so it is an outcome a
person deals with, not something to retry.
"""


class ExitCode(IntEnum):
    """Every status `debate-research` can exit with. See the table in the module docstring."""

    OK = 0
    DOMAIN_FAILURE = 1
    USAGE_ERROR = 2
    RETRIEVAL_FAILURE = 3
    INTERNAL_ERROR = 70


def exit_code_for(exception: BaseException) -> ExitCode:
    """Return the exit code that `exception` ends the process with.

    The order of the checks is the contract: a provider failure, or a store failure on
    :data:`RETRYABLE_STORE_FAILURES`, is also a `DomainError`, and it is the more specific answer
    (3, "try again later") that callers want.

    Click-family errors (`typer.TyperException` and its `UsageError` subclasses) already carry the
    code Typer's standalone runner exits with, so this reports that number rather than inventing a
    second one — which is what keeps the JSON envelope's `exit_code` equal to the real exit status.
    """
    if isinstance(exception, typer.Exit):
        return _known_exit_code(exception.exit_code)
    if isinstance(exception, typer.TyperException):
        return _known_exit_code(exception.exit_code)
    if isinstance(exception, (ProviderError, *RETRYABLE_STORE_FAILURES)):
        return ExitCode.RETRIEVAL_FAILURE
    if isinstance(exception, STOPPED_BY_A_STORE) and is_retryable_store_failure(exception.__cause__):
        return ExitCode.RETRIEVAL_FAILURE
    if isinstance(exception, DomainError):
        return ExitCode.DOMAIN_FAILURE
    return ExitCode.INTERNAL_ERROR


def is_retryable_store_failure(exception: BaseException | None) -> bool:
    """True when `exception` is one of :data:`RETRYABLE_STORE_FAILURES`."""
    return isinstance(exception, RETRYABLE_STORE_FAILURES)


def exit_code_for_failure_codes(codes: Iterable[str | None]) -> ExitCode:
    """The exit code for a run that recorded these per-item failures by error code.

    `store sync` and `caselist publish` carry on past one object's failure and report each by its
    error code (`STORE_UNAVAILABLE`, `CHECKSUM_MISMATCH`, …). The run is a `RETRIEVAL_FAILURE` only
    when every failure is a store failure a retry may cure; one deterministic failure among them —
    or a failure with no code — makes the whole run a `DOMAIN_FAILURE`, because running it again
    cannot succeed. No failures at all is not a call this function answers.
    """
    recorded = list(codes)
    if not recorded:
        raise ValueError("a run with no failures has no failure exit code")
    if all(code in _RETRYABLE_STORE_ERROR_CODES for code in recorded):
        return ExitCode.RETRIEVAL_FAILURE
    return ExitCode.DOMAIN_FAILURE


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


#: The error codes :data:`RETRYABLE_STORE_FAILURES` are reported under, e.g. `STORE_UNAVAILABLE`.
_RETRYABLE_STORE_ERROR_CODES = frozenset(
    _upper_snake_case(kind.__name__) for kind in RETRYABLE_STORE_FAILURES
)
