"""`debate-research caselist auth login | status | logout`: the operator's OpenCaselist session.

::

    debate-research caselist auth login          # prompts for Tabroom credentials, once
    debate-research caselist auth status         # is a token stored, and when did it last work
    debate-research caselist auth status --check # ... and does it work right now (one request)
    debate-research caselist auth logout         # forget it

`login` trades the operator's own Tabroom username and password for a `caselist_token` through
`POST /login`, and stores **only the token** — in the OS keychain, or a 0600 gitignored file
(`caselist.token_backend`). The password is read with hidden input, held as a `SecretStr`, sent
once, and never stored or printed. Prompts go to stderr, so `--json` output stays one object.

No command here ever prints the token: `status` reports whether one is stored, where, when it
expires and when a request last succeeded with it.

`login` and `status --check` reach the network and are refused unless `caselist.api_enabled` is true
(`docs/policies/caselist-data-use.md`, E34 gate). `status` and `logout` are local and always work.

## Exit codes

`0` when the command did what it was asked. `1` for a refusal the operator acts on: the API is
disabled, the login was rejected, the stored token has expired (`CaselistAuthExpired`). `3` when
OpenCaselist could not be reached or rate-limited the request.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Annotated, Any

import typer
from pydantic import SecretStr

from debate_cli.context import cli_context, command_name
from debate_cli.output import JsonValue, TableSpec
from debate_core.integrations.opencaselist import OpenCaselistClient, StoredCaselistToken
from debate_core.integrations.opencaselist.auth import IssuedToken

__all__ = ["login", "logout", "status"]


def login(
    ctx: typer.Context,
    username: Annotated[
        str | None,
        typer.Option("--username", help="Tabroom username (email). Prompted for when omitted."),
    ] = None,
) -> None:
    """Log in to OpenCaselist with Tabroom credentials and store only the caselist_token."""
    cli = cli_context(ctx)
    # Built first: a disabled API is refused before the operator is asked for a password.
    client = cli.services.opencaselist_client()
    store = cli.services.caselist_token_store()

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


def status_summary(
    stored: StoredCaselistToken | None,
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


async def _login(client: OpenCaselistClient, username: str, password: SecretStr) -> IssuedToken:
    async with client:
        return await client.login(username, password)


async def _check(client: OpenCaselistClient) -> None:
    async with client:
        await client.list_caselists()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _run[T](awaitable: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(awaitable)
