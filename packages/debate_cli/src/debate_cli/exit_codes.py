"""The exit codes `debate-research` returns, and the one place a failure is turned into one.

A script that runs the CLI — a caselist sync on a schedule, a Makefile, another agent — decides
what to do next from the exit code alone, so the numbers are part of the CLI's public contract and
are fixed here rather than at each `raise`:

`0` — `OK`
    The command did what it was asked to do.

`1` — `DOMAIN_FAILURE`
    The command ran and the answer is a failure: `verify` found a card `UNVERIFIED`, a record was
    not found, a write lost its revision check. Running the same command again gives the same
    answer.

`2` — `USAGE_ERROR`
    The command line was wrong: unknown command or option, missing argument, no command given.
    Nothing was executed.

`3` — `RETRIEVAL_FAILURE`
    Something the command depends on did not answer, so there is no answer yet: an external
    provider (search, fetch, a model) failed or rate-limited the call, or a store could not be read
    or written — it was unavailable, the session for it expired, or it refused access
    (:data:`RETRYABLE_STORE_FAILURES`, `v1-e01-t20`). The same command may well succeed later,
    which is why this is never `DOMAIN_FAILURE`: a script reading the code must be able to tell an
    outage from a verdict. A model call the provider *refused* is not on it
    (:data:`REFUSED_MODEL_CALLS`, `v1-e05-t09`): no retry fixes it, so it is a `1`.

`4` — `CARD_UNVERIFIED`
    `cut` made a card and the evidence verifier did not pass it (`v1-e06-t06`): the card was saved
    and exported `UNVERIFIED`, with its banner, and each reason was printed. It is never `0`, because
    an unverified card is not finished evidence (architecture proposal §8), and it is not `1`, so that
    a script can tell a card that needs a person's look from a cut that could not run at all: a
    refused model call, a missing or damaged snapshot or an unregistered prompt saves no card and is a
    `1`, and a source that could not be retrieved, or a model provider that did not answer, is a `3`.

`70` — `INTERNAL_ERROR`
    A bug: an exception the CLI does not model. 70 is `EX_SOFTWARE` from `sysexits.h`.

Later command tasks import :class:`ExitCode` instead of writing the numbers down again::

    raise typer.Exit(code=ExitCode.DOMAIN_FAILURE)

Most commands never need to: :class:`~debate_cli.app.DebateResearchGroup` catches what a command
raises and applies :func:`exit_code_for` for it. A command only chooses a code itself when the
failure is an *outcome* rather than an exception — `verify` reporting an `UNVERIFIED` card is the
V1 example, and it reports that outcome through
:meth:`~debate_cli.output.CliOutput.failure` and then exits with `DOMAIN_FAILURE`; `cut` reporting
an `UNVERIFIED` card it exported exits with `CARD_UNVERIFIED` the same way.

`debate_core` never imports this module: an exit code is a property of a command-line surface, not
of the domain. The dependency runs the other way for **error codes**: the word a failure is
reported under is defined once, in :mod:`debate_core.application.errors`
(:func:`~debate_core.application.errors.error_code_of`), because the services that record a
failure's code and this module, which turns recorded codes into an exit status
(:func:`exit_code_for_failure_codes`), have to mean the same thing by it (`v1-e34-t13`).
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import IntEnum

import typer

from debate_core.application.caselist.removal_service import RemovalIncomplete, TakedownPreflightFailed
from debate_core.application.errors import (
    DomainError,
    ModelAccessDenied,
    ModelRequestRejected,
    ProviderError,
    ProviderRateLimited,
    ProviderUnavailable,
    StoreAccessDenied,
    StoreCredentialsExpired,
    StoreUnavailable,
    error_code_of,
    error_code_of_class,
)
from debate_core.application.landscape_model_stage import ModelStageInterrupted

__all__ = [
    "REFUSED_MODEL_CALLS",
    "RETRYABLE_PROVIDER_FAILURES",
    "RETRYABLE_STORE_FAILURES",
    "STOPPED_BY_A_STORE",
    "ExitCode",
    "codes_exit_as_a_retrieval_failure",
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

:class:`~debate_core.application.errors.StoreProfileNotConfigured` is a `StoreError` and is
deliberately not here (`v1-e29-t07`): a profile the AWS config does not define is defined by
nobody's retry, so it ends a command with `DOMAIN_FAILURE` (1), and a run that recorded its code,
`STORE_PROFILE_NOT_CONFIGURED`, is a 1 whatever else it recorded.
"""

RETRYABLE_PROVIDER_FAILURES: tuple[type[ProviderError], ...] = (ProviderUnavailable, ProviderRateLimited)
"""The provider failures a run records by code and a retry may cure (`v1-e34-t13`).

A provider failure that ends a command is a `RETRIEVAL_FAILURE` unless it is one of
:data:`REFUSED_MODEL_CALLS` (:func:`exit_code_for`). These two are the ones a run can record
instead: a download stage of `caselist pull` that met a 5xx, a timeout, or a rate limit that
outlasted the client's bounded retries. Named one by one, like the store failures, so that a code
is on the list because someone decided it is. OpenCaselist's *daily* limiter is not here although
it arrives as a rate limit: the sync records it under a code of its own, because it is a verdict
for the day.
"""

REFUSED_MODEL_CALLS: tuple[type[ProviderError], ...] = (ModelAccessDenied, ModelRequestRejected)
"""The provider failures no retry fixes, which end a command with `DOMAIN_FAILURE` (1), not 3 (`v1-e05-t09`).

The model provider refused the caller (no usable credentials, or none granted the model) or the
request itself (a parameter the model refuses, a model it does not know). The Bedrock adapter
already never retries either (`v1-e05-t02`); a script that retried on the exit code would only send
the same refused call again. A throttled call stays a `3`: it is :class:`ProviderRateLimited`.

A landscape run whose model stage one of these stopped
(:class:`~debate_core.application.landscape_model_stage.ModelStageInterrupted`) is a `1` too, and one
that :data:`RETRYABLE_PROVIDER_FAILURES` stopped is a `3` (`v1-e32-t32`).
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
    CARD_UNVERIFIED = 4
    INTERNAL_ERROR = 70


def exit_code_for(exception: BaseException) -> ExitCode:
    """Return the exit code that `exception` ends the process with.

    The order of the checks is the contract: a provider failure, or a store failure on
    :data:`RETRYABLE_STORE_FAILURES`, is also a `DomainError`, and it is the more specific answer
    (3, "try again later") that callers want. A provider failure on :data:`REFUSED_MODEL_CALLS` is
    checked first, and is a `DOMAIN_FAILURE`: trying again later gives the same refusal.

    A landscape model stage that stopped partway (:class:`ModelStageInterrupted`) exits as its cause
    does when that cause is on :data:`RETRYABLE_PROVIDER_FAILURES`, a `3`, since the answered cards are
    cached and the next run asks only about the rest (`v1-e32-t32`). Any other cause, a refused call
    or one nobody classified, keeps it a `DOMAIN_FAILURE`.

    Click-family errors (`typer.TyperException` and its `UsageError` subclasses) already carry the
    code Typer's standalone runner exits with, so this reports that number rather than inventing a
    second one — which is what keeps the JSON envelope's `exit_code` equal to the real exit status.
    """
    if isinstance(exception, typer.Exit):
        return _known_exit_code(exception.exit_code)
    if isinstance(exception, typer.TyperException):
        return _known_exit_code(exception.exit_code)
    if isinstance(exception, REFUSED_MODEL_CALLS):
        return ExitCode.DOMAIN_FAILURE
    if isinstance(exception, (ProviderError, *RETRYABLE_STORE_FAILURES)):
        return ExitCode.RETRIEVAL_FAILURE
    if isinstance(exception, STOPPED_BY_A_STORE) and is_retryable_store_failure(exception.__cause__):
        return ExitCode.RETRIEVAL_FAILURE
    if isinstance(exception, ModelStageInterrupted) and isinstance(
        exception.cause, RETRYABLE_PROVIDER_FAILURES
    ):
        return ExitCode.RETRIEVAL_FAILURE
    if isinstance(exception, DomainError):
        return ExitCode.DOMAIN_FAILURE
    return ExitCode.INTERNAL_ERROR


def is_retryable_store_failure(exception: BaseException | None) -> bool:
    """True when `exception` is one of :data:`RETRYABLE_STORE_FAILURES`."""
    return isinstance(exception, RETRYABLE_STORE_FAILURES)


def exit_code_for_failure_codes(codes: Iterable[str | None]) -> ExitCode:
    """The exit code for a run that recorded these failures by error code instead of raising them.

    `store sync` and `caselist publish` carry on past one object's failure and report each by its
    error code (`STORE_UNAVAILABLE`, `CHECKSUM_MISMATCH`, …), and a stage of `caselist pull`
    records the code of each failure that failed it (`v1-e34-t13`). The run is a
    `RETRIEVAL_FAILURE` only when every failure is one a retry may cure: a code of
    :data:`RETRYABLE_STORE_FAILURES` or :data:`RETRYABLE_PROVIDER_FAILURES`. One deterministic
    failure among them makes the whole run a `DOMAIN_FAILURE`, because running it again cannot
    succeed, and so does a failure with no code or with a code this list does not name: nothing
    reaches `3` because nobody classified it. No failures at all is not a call this function
    answers.
    """
    recorded = list(codes)
    if not recorded:
        raise ValueError("a run with no failures has no failure exit code")
    if all(code in _RETRYABLE_ERROR_CODES for code in recorded):
        return ExitCode.RETRIEVAL_FAILURE
    return ExitCode.DOMAIN_FAILURE


def codes_exit_as_a_retrieval_failure(codes: Iterable[str | None]) -> bool:
    """Whether a run that recorded exactly these failures exits `3`: one a retry may cure.

    :func:`exit_code_for_failure_codes` asked as a question, and nothing more: the rule is that
    function's and is not restated here. It is what the composition root hands the caselist run
    monitor (`v1-e34-t19`), so that the notification for a failed `caselist pull` says "the next
    scheduled run should retry it" for exactly the runs the command exits `3` on, and "a person
    should look" for the rest. False for no codes at all: a failure nobody recorded a code for is
    never called transient.
    """
    recorded = list(codes)
    return bool(recorded) and exit_code_for_failure_codes(recorded) is ExitCode.RETRIEVAL_FAILURE


def error_code_for(exception: BaseException) -> str:
    """Return the machine-readable error code for `exception`, e.g. `"REVISION_MISMATCH"`.

    This is the `error.code` a `--json` consumer branches on. For a
    :class:`~debate_core.application.errors.DomainError` it is the class name in upper snake case,
    so the code a script sees and the class a developer reads are the same word
    (:func:`~debate_core.application.errors.error_code_of`, which a service recording the failure
    instead uses too); for everything else it is the name of the exit code.
    """
    if isinstance(exception, DomainError):
        return error_code_of(exception)
    return exit_code_for(exception).name


def _known_exit_code(value: int) -> ExitCode:
    """Return `value` as an :class:`ExitCode`, or `INTERNAL_ERROR` if it is not one of ours."""
    try:
        return ExitCode(value)
    except ValueError:
        return ExitCode.INTERNAL_ERROR


#: The error codes the two lists are reported under, e.g. `STORE_UNAVAILABLE`, `PROVIDER_UNAVAILABLE`.
_RETRYABLE_ERROR_CODES = frozenset(
    error_code_of_class(kind) for kind in (*RETRYABLE_STORE_FAILURES, *RETRYABLE_PROVIDER_FAILURES)
)
