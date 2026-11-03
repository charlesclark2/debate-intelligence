"""What a bucket-mode command OpenCaselist refused for an expired login prints (`v1-e40-t35`).

`CaselistAuthExpired`'s message ends "Run `debate-research caselist auth login` again", which is the
Mac's fix: the transport that raises it does not know the mode. In the cloud the caselist_token is
the one the Wednesday 03:00 login renews, and a login by hand would be a second login that week
(`docs/runbooks/caselist-cloud-run.md`, "A run refused for an expired login"). So in bucket mode
`caselist pull` and `caselist backfile-import` report the error, under its own code, details and exit
status, with what was refused as its message and the cloud's cure as its hint, in
`caselist_pull._hint_for`'s "In bucket mode …" idiom. Outside bucket mode the error goes on to the
root handler, which prints it as it always has.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Final

import typer

from debate_cli.context import CliContext, command_name
from debate_cli.output import CommandFailure
from debate_core.application.caselist_sync import message_for
from debate_core.application.ports.caselist_source import CaselistAuthExpired
from debate_core.application.sync_runs import CLOUD_AUTH_EXPIRED_CURE

__all__ = ["CLOUD_AUTH_EXPIRED_HINT", "cloud_cure_for_an_expired_login"]

CLOUD_AUTH_EXPIRED_HINT: Final = f"In bucket mode {CLOUD_AUTH_EXPIRED_CURE}."
"""A bucket-mode command's hint for an expired login: `v1-e40-t33`'s cure, not a second wording."""


@contextmanager
def cloud_cure_for_an_expired_login(
    cli: CliContext, ctx: typer.Context, *, bucket_mode: bool
) -> Iterator[None]:
    """Report an expired login the block raises in bucket mode, with the cloud's cure, and end the run.

    Only :class:`CaselistAuthExpired`, and only in bucket mode; anything else, in either mode, passes on
    unchanged.
    """
    try:
        yield
    except CaselistAuthExpired as expired:
        if not bucket_mode:
            raise
        failure = dataclasses.replace(
            CommandFailure.from_exception(expired),
            message=message_for(expired, bucket_mode=True),
            hint=CLOUD_AUTH_EXPIRED_HINT,
        )
        cli.output.failure(failure, command=command_name(ctx))
        raise typer.Exit(code=failure.exit_code) from expired
