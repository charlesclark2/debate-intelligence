"""`debate-research tub users`: the coach's accounts for the student search pilot (ADR-0019 (d)).

::

    debate-research tub users add <username> --role student --env prod
    debate-research tub users add <username> --role student --email-second-factor --env prod
    debate-research tub users list --env prod
    debate-research tub users reset <username> --env prod
    debate-research tub users disable <username> --env prod
    debate-research tub users enable <username> --env prod
    debate-research tub users remove <username> --env prod
    debate-research tub users email-second-factor <username> --allow --env prod

Every command runs as the environment's `TubAccounts` permission set, through the profile
`debate-<env>-tub-accounts` unless `--profile` names another, on the pool `--pool-id` or
`TUB_USER_POOL_ID` names (`terraform output -raw evidence_search_user_pool_id`). A profile is
allowed only its own environment's pool, so a prod profile with the dev pool's id is refused before
anything changes.

A username is 3 to 32 lowercase letters, digits and dots, never an email address; anything else is
refused before the pool is asked. `add` and `reset` print the temporary password once, on that
command's own output, and nowhere else: not in `--verbose`, not in an error. `list` prints
usernames and roles only. Each command writes one record to the audit log's `tub-users` stream,
with the account's pool subject and no name.

## Exit codes

`0` when it did what it was asked. `1` for a refusal: an invalid username, an account that does not
exist or already exists, a profile this machine's AWS config does not define. `3` when the SSO
session expired, the profile was refused, or AWS did not answer (the store failures every command
treats alike, `debate_cli.exit_codes`).

If the audit record cannot be written, the command fails with `3` after making the change, and
`add` and `reset` do not print the password: run `reset` once the audit log is reachable.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

import typer

from debate_cli.context import cli_context, command_name
from debate_cli.output import TableSpec
from debate_core.application.tub.accounts import AccountSummary, IssuedPassword
from debate_core.application.tub.identity import Role

__all__ = ["add", "disable", "email_second_factor", "enable", "list_accounts", "remove", "reset"]


class PilotEnvironment(StrEnum):
    DEV = "dev"
    PROD = "prod"


EnvironmentOption = Annotated[
    PilotEnvironment,
    typer.Option("--env", help="Which pilot: dev or prod. Its profile, pool and audit log follow from it."),
]
PoolOption = Annotated[
    str,
    typer.Option(
        "--pool-id",
        envvar="TUB_USER_POOL_ID",
        help="The pilot's user pool id (terraform output -raw evidence_search_user_pool_id).",
    ),
]
ProfileOption = Annotated[
    str | None,
    typer.Option("--profile", help="The AWS profile to use. Default: debate-<env>-tub-accounts."),
]
UsernameArgument = Annotated[str, typer.Argument(help="3 to 32 lowercase letters, digits and dots.")]


def add(
    ctx: typer.Context,
    username: UsernameArgument,
    environment: EnvironmentOption,
    pool_id: PoolOption,
    role: Annotated[Role, typer.Option("--role", help="student or coach.")] = Role.STUDENT,
    email_second_factor: Annotated[
        bool,
        typer.Option(
            "--email-second-factor",
            help="Let this account use a verified email as its only second factor (no phone).",
        ),
    ] = False,
    profile: ProfileOption = None,
) -> None:
    """Create an account and print its temporary password, once."""
    cli = cli_context(ctx)
    accounts = cli.services.tub_account_administration(environment.value, pool_id, profile)
    issued = accounts.add(username, role, email_second_factor=email_second_factor)
    _password_shown_once(ctx, issued, verb="Created")


def list_accounts(
    ctx: typer.Context, environment: EnvironmentOption, pool_id: PoolOption, profile: ProfileOption = None
) -> None:
    """List every account's username and role."""
    cli = cli_context(ctx)
    summaries = cli.services.tub_account_administration(environment.value, pool_id, profile).list()
    cli.output.success(
        command_name(ctx),
        {"accounts": [{"username": s.username, "role": _role(s)} for s in summaries]},
        display=TableSpec(
            columns=("Username", "Role"),
            rows=[(summary.username, _role(summary)) for summary in summaries],
            title=f"{len(summaries)} account(s) in the {environment.value} pilot",
        ),
    )


def reset(
    ctx: typer.Context,
    username: UsernameArgument,
    environment: EnvironmentOption,
    pool_id: PoolOption,
    profile: ProfileOption = None,
) -> None:
    """A new temporary password, the authenticator removed, and every session signed out."""
    cli = cli_context(ctx)
    issued = cli.services.tub_account_administration(environment.value, pool_id, profile).reset(username)
    _password_shown_once(ctx, issued, verb="Reset")


def disable(
    ctx: typer.Context,
    username: UsernameArgument,
    environment: EnvironmentOption,
    pool_id: PoolOption,
    profile: ProfileOption = None,
) -> None:
    """Sign the account out everywhere and stop it signing in. `enable` undoes it."""
    cli = cli_context(ctx)
    summary = cli.services.tub_account_administration(environment.value, pool_id, profile).disable(username)
    _done(ctx, summary, "Disabled", "Any open session ends within five minutes.")


def enable(
    ctx: typer.Context,
    username: UsernameArgument,
    environment: EnvironmentOption,
    pool_id: PoolOption,
    profile: ProfileOption = None,
) -> None:
    """Let a disabled account sign in again."""
    cli = cli_context(ctx)
    summary = cli.services.tub_account_administration(environment.value, pool_id, profile).enable(username)
    _done(ctx, summary, "Enabled", "It can sign in again.")


def remove(
    ctx: typer.Context,
    username: UsernameArgument,
    environment: EnvironmentOption,
    pool_id: PoolOption,
    profile: ProfileOption = None,
) -> None:
    """Sign the account out everywhere and delete it, with its email if it had one."""
    cli = cli_context(ctx)
    summary = cli.services.tub_account_administration(environment.value, pool_id, profile).remove(username)
    _done(ctx, summary, "Removed", "Any open session ends within five minutes.")


def email_second_factor(
    ctx: typer.Context,
    username: UsernameArgument,
    environment: EnvironmentOption,
    pool_id: PoolOption,
    allow: Annotated[
        bool,
        typer.Option(
            "--allow/--withdraw",
            help="Allow, or withdraw, a verified email as this account's only second factor.",
        ),
    ],
    profile: ProfileOption = None,
) -> None:
    """Allow or withdraw a verified email as the account's only second factor, for a student with no phone."""
    cli = cli_context(ctx)
    accounts = cli.services.tub_account_administration(environment.value, pool_id, profile)
    summary = accounts.set_email_second_factor(username, allowed=allow)
    _done(
        ctx,
        summary,
        "Allowed an email second factor for" if allow else "Withdrew the email second factor from",
        "It takes effect at the next sign-in.",
    )


def _role(summary: AccountSummary) -> str:
    return summary.role.value if summary.role is not None else "none"


def _password_shown_once(ctx: typer.Context, issued: IssuedPassword, *, verb: str) -> None:
    """The one place a temporary password is printed: this command's own result."""
    password = issued.temporary_password.reveal()
    role = issued.role.value if issued.role is not None else "no role"
    cli_context(ctx).output.success(
        command_name(ctx),
        {"username": issued.username, "role": role, "temporary_password": password},
        display=(
            f"{verb} {issued.username} ({role}).\n"
            f"Temporary password, shown this once: {password}\n"
            "Give it to the student in person. It works for 7 days, and they choose their own at "
            "the first sign-in."
        ),
    )


def _done(ctx: typer.Context, summary: AccountSummary, verb: str, consequence: str) -> None:
    cli_context(ctx).output.success(
        command_name(ctx),
        {"username": summary.username, "role": _role(summary)},
        display=f"{verb} {summary.username}. {consequence}",
    )
