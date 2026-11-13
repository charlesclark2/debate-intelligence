"""What a bucket-mode command prints for an error over its caselist_token (`v1-e40-t35`, `v1-e40-t40`).

`CaselistAuthExpired`'s message ends "Run `debate-research caselist auth login` again",
`CaselistTokenMissing`'s "run `debate-research caselist auth login` first", and
`CaselistTokenUnreadable`'s "run `debate-research caselist auth logout` and then `caselist auth login`".
Those are the Mac's fixes: the transport and the token store that raise them do not know the mode. In
the cloud the caselist_token is the token secret's, which the Wednesday 03:00 login writes, and a login
by hand would be a second login that week (`docs/runbooks/caselist-cloud-run.md`, "A run refused for an
expired login" and "A run with no readable caselist_token"). So in bucket mode `caselist pull` and
`caselist backfile-import` report each code in the table of cloud cures
(:data:`~debate_core.application.sync_runs.CLOUD_TOKEN_CURES`), under its own code, details and exit
status, with what happened as its message and the code's cure as its hint, in
`caselist_pull._hint_for`'s "In bucket mode …" idiom. Any other error, and every error outside bucket
mode, goes on to the root handler, which prints it as it always has.

The module's name has no `caselist_token` in it on purpose: the wheel check in `scripts/stamp_build.py`
refuses any member whose name carries those words, so that the token file can never ship. v1-e40-t40
named it `caselist_token_cures.py`, and the build's wheel test refused it (v1-e07-t20's pull request).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from contextlib import contextmanager

import typer

from debate_cli.context import CliContext, command_name
from debate_cli.output import CommandFailure
from debate_core.application.caselist_sync import message_for
from debate_core.application.errors import DomainError
from debate_core.application.sync_runs import cloud_cure_for

__all__ = ["cloud_cure_for_a_token_error", "in_bucket_mode"]


def in_bucket_mode(cure: str) -> str:
    """A bucket-mode command's hint for a cloud cure: the table's cure, not a second wording."""
    return f"In bucket mode {cure}."


@contextmanager
def cloud_cure_for_a_token_error(cli: CliContext, ctx: typer.Context, *, bucket_mode: bool) -> Iterator[None]:
    """Report an error the block raises in bucket mode whose code has a cloud cure, with it, and end the run.

    Only an error whose code, as the CLI reports it, is in the table, and only in bucket mode; anything
    else, in either mode, passes on unchanged.
    """
    try:
        yield
    except DomainError as error:
        reported = CommandFailure.from_exception(error)
        cure = cloud_cure_for((reported.code,)) if bucket_mode else None
        if cure is None:
            raise
        failure = dataclasses.replace(
            reported, message=message_for(error, bucket_mode=True), hint=in_bucket_mode(cure)
        )
        cli.output.failure(failure, command=command_name(ctx))
        raise typer.Exit(code=failure.exit_code) from error
