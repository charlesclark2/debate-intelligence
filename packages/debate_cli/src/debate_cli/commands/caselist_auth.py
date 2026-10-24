"""`debate-research caselist auth login | status | logout | set-password | renew`: the OpenCaselist session.

::

    debate-research caselist auth login          # prompts for Tabroom credentials, once
    debate-research caselist auth status         # is a token stored, and when did it last work
    debate-research caselist auth status --check # ... and does it work right now (one request)
    debate-research caselist auth logout         # forget it
    debate-research caselist auth set-password   # the coach writes the cloud login's password
    debate-research caselist auth renew          # the cloud login task: password in, token out

`login` trades the operator's own Tabroom username and password for a `caselist_token` through
`POST /login`, and stores **only the token** — in the OS keychain, or a 0600 gitignored file
(`caselist.token_backend`). The password is read with hidden input, held as a `SecretStr`, sent
once, and never stored or printed. Prompts go to stderr, so `--json` output stays one object.

No command here ever prints the token: `status` reports whether one is stored, where, when it
expires and when a request last succeeded with it.

## The weekly run in the cloud (ADR-0020 (2))

`set-password` writes the coach's Tabroom username and password to the environment's password
secret in Secrets Manager, signed in under `Debate<Env>CaselistCredentialWriter`. It prompts with
hidden input, twice, and refuses to run without a terminal: the password is never an argument or
an environment variable, so it never reaches shell history or a process listing, and nothing it
prints says anything about it. Nobody reads it back.

`renew` is the login task's command, run every Wednesday at 03:00 America/Chicago as the login
role: it reads the password secret, logs in once (a refused login is never retried) and writes only
the token to the token secret. A failure is sent to `caselist.notifier`, which in the cloud emails
the coach without naming the account.

`login --token-backend secretsmanager` is the hand fallback for that task: the usual prompts, with
the token written to the token secret instead of the keychain.

`login` and `status --check` reach the network and are refused unless `caselist.api_enabled` is true
(`docs/policies/caselist-data-use.md`, E34 gate). `status` and `logout` are local and always work.

## Exit codes

`0` when the command did what it was asked. `1` for a refusal the operator acts on: the API is
disabled, the login was rejected, the stored token has expired (`CaselistAuthExpired`). `3` when
OpenCaselist could not be reached or rate-limited the request.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Annotated, Any

import typer
from pydantic import SecretStr

from debate_cli.context import cli_context, command_name
from debate_cli.output import JsonValue, TableSpec
from debate_core.application.caselist_login import TabroomCredentials
from debate_core.application.errors import DomainError
from debate_core.application.ports.caselist_session import CaselistLoginSession, IssuedToken, StoredToken
from debate_core.application.settings import CaselistTokenBackend

__all__ = ["login", "logout", "renew", "set_password", "status"]

AwsProfileOption = Annotated[
    str | None,
    typer.Option(
        "--aws-profile",
        help=(
            "AWS profile for the Secrets Manager secrets: the one signed in under "
            "Debate<Env>CaselistCredentialWriter. Unset uses the SDK's own chain (AWS_PROFILE)."
        ),
    ),
]


class NoTerminal(DomainError):
    """`set-password` was run without a terminal to read hidden input from."""

    def __init__(self) -> None:
        super().__init__(
            "`caselist auth set-password` reads the password from a terminal with hidden input and "
            "runs only in one; it never takes the password from an argument, a pipe or an "
            "environment variable"
        )


def login(
    ctx: typer.Context,
    username: Annotated[
        str | None,
        typer.Option("--username", help="Tabroom username (email). Prompted for when omitted."),
    ] = None,
    token_backend: Annotated[
        CaselistTokenBackend | None,
        typer.Option(
            "--token-backend",
            help=(
                "Where to store the token, instead of caselist.token_backend. `secretsmanager` "
                "writes the cloud run's token secret: the fallback when the weekly login fails."
            ),
        ),
    ] = None,
    aws_profile: AwsProfileOption = None,
) -> None:
    """Log in to OpenCaselist with Tabroom credentials and store only the caselist_token."""
    cli = cli_context(ctx)
    # Built first: a disabled API is refused before the operator is asked for a password.
    client = cli.services.opencaselist_client()
    store = (
        cli.services.caselist_token_store()
        if token_backend is None
        else cli.services.caselist_token_store_on(token_backend, aws_profile=aws_profile)
    )

    user = username or typer.prompt("Tabroom username (email)", err=True)
    password = SecretStr(typer.prompt("Tabroom password", hide_input=True, err=True))
    issued = _run(_login(client, user, password))
    del password

    stored = store.save(issued.token, expires_at=issued.expires_at)
    cli.output.success(
        command_name(ctx),
        {
            "stored": True,
            "backend": stored.backend,
            "location": store.location,
            "expires_at": _iso(stored.expires_at),
        },
        display=(
            f"Logged in. The caselist_token is stored in the {stored.backend} backend ({store.location})"
            + (f" and expires {stored.expires_at:%Y-%m-%d %H:%M} UTC." if stored.expires_at else ".")
            + " The password was not stored."
        ),
    )


def status(
    ctx: typer.Context,
    check: Annotated[
        bool,
        typer.Option("--check", help="Make one request to confirm the token still works."),
    ] = False,
) -> None:
    """Report whether a caselist_token is stored and when it last worked. Never prints it."""
    cli = cli_context(ctx)
    settings = cli.services.settings
    store = cli.services.caselist_token_store()
    configured = settings.providers.caselist_token is not None
    stored = store.load()

    checked: bool | None = None
    if check:
        client = cli.services.opencaselist_client()
        _run(_check(client))
        checked = True
        stored = store.load()

    summary = status_summary(
        stored,
        backend=store.backend_name,
        location=store.location,
        api_enabled=settings.caselist.api_enabled,
        configured_in_settings=configured,
        checked=checked,
        now=datetime.now(UTC),
    )
    cli.output.success(command_name(ctx), summary, display=_status_table(summary))


def logout(ctx: typer.Context) -> None:
    """Delete the stored caselist_token."""
    cli = cli_context(ctx)
    store = cli.services.caselist_token_store()
    deleted = store.delete()
    cli.output.success(
        command_name(ctx),
        {"deleted": deleted, "backend": store.backend_name, "location": store.location},
        display=(
            f"Deleted the caselist_token from the {store.backend_name} backend."
            if deleted
            else "No caselist_token was stored; nothing to delete."
        ),
    )


def set_password(ctx: typer.Context, aws_profile: AwsProfileOption = None) -> None:
    """Write the Tabroom username and password for the weekly cloud login. Hidden input; never read back."""
    cli = cli_context(ctx)
    if not stdin_is_a_terminal():
        raise NoTerminal
    secret = cli.services.tabroom_password_secret(aws_profile=aws_profile)
    # Checked first, so an expired session or a missing grant is found before anything is typed.
    secret.check()
    user = typer.prompt("Tabroom username (email)", err=True)
    password = SecretStr(
        typer.prompt("Tabroom password", hide_input=True, confirmation_prompt=True, err=True)
    )
    secret.write(TabroomCredentials(username=user, password=password))
    del password
    cli.output.success(
        command_name(ctx),
        {"written": True, "secret": secret.secret_id},
        display=(
            f"Written to Secrets Manager secret {secret.secret_id}. The weekly login reads it from "
            "there; nobody reads it back. Run this again after changing the password at Tabroom."
        ),
    )


def renew(ctx: typer.Context) -> None:
    """The cloud login task: read the Tabroom password, log in once, write only the new token."""
    cli = cli_context(ctx)
    outcome = _run(cli.services.scheduled_caselist_login().run())
    cli.output.success(
        command_name(ctx),
        {"stored": True, "location": outcome.token_location, "expires_at": _iso(outcome.expires_at)},
        display=(
            f"Logged in. A new caselist_token is stored in {outcome.token_location}"
            + (f" and expires {outcome.expires_at:%Y-%m-%d %H:%M} UTC." if outcome.expires_at else ".")
        ),
    )


def stdin_is_a_terminal() -> bool:
    """Whether hidden input can be read: a terminal on standard input. Tests replace this."""
    return sys.stdin.isatty()


def status_summary(
    stored: StoredToken | None,
    *,
    backend: str,
    location: str,
    api_enabled: bool,
    configured_in_settings: bool,
    checked: bool | None,
    now: datetime,
) -> dict[str, JsonValue]:
    """The `--json` `data` for `caselist auth status`. Every key is present whether or not a token is."""
    return {
        "token_stored": stored is not None,
        "token_in_settings": configured_in_settings,
        "backend": backend,
        "location": location,
        "stored_at": _iso(stored.stored_at) if stored else None,
        "expires_at": _iso(stored.expires_at) if stored else None,
        "expired": stored.expired(now) if stored else None,
        "last_validated_at": _iso(stored.last_validated_at) if stored else None,
        "checked_now": checked,
        "api_enabled": api_enabled,
    }


def _status_table(summary: dict[str, JsonValue]) -> TableSpec:
    labels = {
        "token_stored": "Token stored",
        "token_in_settings": "Token set in settings",
        "backend": "Backend",
        "location": "Location",
        "stored_at": "Stored",
        "expires_at": "Expires",
        "expired": "Expired",
        "last_validated_at": "Last worked",
        "checked_now": "Checked just now",
        "api_enabled": "API enabled",
    }
    return TableSpec(
        columns=("Field", "Value"),
        rows=[[label, "—" if summary[key] is None else str(summary[key])] for key, label in labels.items()],
        title="OpenCaselist session",
        caption="The token itself is never shown.",
    )


async def _login(client: CaselistLoginSession, username: str, password: SecretStr) -> IssuedToken:
    async with client:
        return await client.login(username, password)


async def _check(client: CaselistLoginSession) -> None:
    async with client:
        await client.list_caselists()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _run[T](awaitable: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(awaitable)
