"""The refusals `caselist publish` and `caselist parse` share before they write to a bucket.

They lived in :mod:`debate_cli.commands.caselist` until v1-e01-t32, and `caselist parse` imported
that command's module to reach them.
"""

from __future__ import annotations

import typer

from debate_cli.context import CliContext, command_name
from debate_cli.exit_codes import ExitCode
from debate_cli.options.bucket_environment import CONFIRM_PROD_FLAG, SYNCABLE_ENVIRONMENTS
from debate_cli.output import CommandFailure
from debate_core.application.settings import Environment, Settings

__all__ = ["no_bucket", "refuse", "unconfirmed_production_write"]


def refuse(cli: CliContext, ctx: typer.Context, refusal: CommandFailure | None) -> None:
    """Report `refusal` and end the run, or return so the command can continue.

    The same outcome-not-exception pattern as `store` (see :mod:`debate_cli.commands.store`).
    """
    if refusal is None:
        return
    cli.output.failure(refusal, command=command_name(ctx))
    raise typer.Exit(code=refusal.exit_code)


def no_bucket(settings: Settings, *, writing: bool) -> CommandFailure | None:
    """A publish needs dev or prod; even a dry run or a status needs a bucket to read."""
    if writing and settings.environment not in SYNCABLE_ENVIRONMENTS:
        return CommandFailure(
            code="ENVIRONMENT_NOT_SYNCABLE",
            message=f"`caselist publish` writes to dev or prod, not {settings.environment.value}",
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"environment": settings.environment.value},
            hint="Set DEBATE_ENV=dev (or prod) and try again.",
        )
    if not settings.storage.s3.bucket:
        return CommandFailure(
            code="EVIDENCE_STORE_NOT_CONFIGURED",
            message=f"the {settings.environment.value} environment names no evidence bucket",
            exit_code=ExitCode.DOMAIN_FAILURE,
            details={"environment": settings.environment.value},
            hint="Set DEBATE_ENV to dev or prod, or set storage.s3.bucket for this environment.",
        )
    return None


def unconfirmed_production_write(
    settings: Settings, *, writing: bool, confirmed: bool
) -> CommandFailure | None:
    """Publishing to the production bucket needs `--confirm-prod`; a dry run writes nothing."""
    if not writing or settings.environment is not Environment.PROD or confirmed:
        return None
    return CommandFailure(
        code="CONFIRMATION_REQUIRED",
        message=(
            "refusing to publish to the production evidence bucket without "
            f"{CONFIRM_PROD_FLAG}: {settings.storage.s3.bucket}"
        ),
        exit_code=ExitCode.DOMAIN_FAILURE,
        details={"environment": settings.environment.value, "bucket": settings.storage.s3.bucket},
        hint=f"Run it with --dry-run first, then again with {CONFIRM_PROD_FLAG}.",
    )
