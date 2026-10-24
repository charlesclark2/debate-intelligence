"""The weekly cloud login: the Tabroom password in, one `POST /login`, the token out (ADR-0020 (2)).

`debate-research caselist auth renew` is the login task's whole job. Every Wednesday at 03:00
America/Chicago, three hours before the run, it reads the coach's Tabroom username and password
from the environment's password secret, logs in to OpenCaselist exactly as `caselist auth login`
does, and writes the new caselist_token to the token secret. It logs in every time, whatever the
stored token's expiry.

`debate-research caselist auth set-password` is the other side: the coach types the username and
password once, with hidden input, and they are written to the password secret. Nobody reads them
back; a changed password is written again.

## A refused login is never retried

:class:`ScheduledLogin` calls `login` once. A refusal (`CaselistLoginRejected`) ends the task, as
every other failure does, so a wrong password costs one attempt a week and cannot lock the
account (`docs/policies/caselist-data-use.md`, E34 gate 5). Before it ends, the failure goes to
the operator through the :class:`~debate_core.application.ports.notifier.Notifier` the
installation is configured with: in the cloud that is the alert topic (`caselist.notifier = sns`,
`v1-e40-t05`), which emails the coach. The run three hours later uses the previous token if it
still works.

## What it never says

The password and the token never reach a log, an error or a notification. The username does not
either: a notification is built from the environment, the error's code and this module's own
sentences, so the account is never named (ADR-0020 (6)). The password is held as a
:class:`~pydantic.SecretStr` from the moment it is parsed and is deliberately *not* registered with
the caselist redaction filter, which would keep it in a process-wide set for the life of the
process (:func:`debate_core.integrations.opencaselist.redaction.register_secret`); it is never
formatted into anything instead, and the tests check that.

## The password secret's document

One JSON object, ``{"username": ..., "password": ...}``, written and read only by
:class:`TabroomPasswordSecret`, so its shape lives in one place.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from pydantic import SecretStr

from debate_core.application.errors import DomainError, error_code_of
from debate_core.application.ports.caselist_session import CaselistLoginSession, IssuedToken, StoredToken
from debate_core.application.ports.notifier import Notification, Notifier

__all__ = [
    "SET_PASSWORD_COMMAND",
    "HAND_LOGIN_COMMAND",
    "ScheduledLogin",
    "ScheduledLoginOutcome",
    "SecretText",
    "TabroomCredentials",
    "TabroomCredentialsMissing",
    "TabroomCredentialsUnreadable",
    "TabroomPasswordSecret",
    "TokenSink",
    "login_failure_notification",
]

SET_PASSWORD_COMMAND = "debate-research caselist auth set-password"
"""What the coach runs after changing the password at Tabroom, or when the login was refused."""

HAND_LOGIN_COMMAND = "debate-research caselist auth login --token-backend secretsmanager"
"""The fallback when Tabroom asks for more than a password: a login by hand that writes the token."""


class TabroomCredentialsMissing(DomainError):
    """The password secret holds no value yet: nobody has run `set-password` in this environment."""

    def __init__(self, secret_id: str) -> None:
        self.secret_id = secret_id
        super().__init__(
            f"Secrets Manager secret {secret_id} holds no Tabroom password yet; the coach writes it "
            f"once with `{SET_PASSWORD_COMMAND}`"
        )


class TabroomCredentialsUnreadable(DomainError):
    """The password secret holds something `set-password` did not write. Its contents are not quoted."""

    def __init__(self, secret_id: str) -> None:
        self.secret_id = secret_id
        super().__init__(
            f"Secrets Manager secret {secret_id} does not hold a Tabroom username and password in the "
            f"form `{SET_PASSWORD_COMMAND}` writes; write it again with that command"
        )


@dataclass(frozen=True, slots=True)
class TabroomCredentials:
    """The coach's Tabroom username and password. `repr` shows neither."""

    username: str
    password: SecretStr

    def __repr__(self) -> str:
        return "TabroomCredentials(username='**********', password=SecretStr('**********'))"


class SecretText(Protocol):
    """One secret, read and written whole as text: what the composition root hands in.

    :class:`debate_core.integrations.secrets_manager.ManagedSecret` is the implementation; the
    application layer never imports the AWS SDK.
    """

    @property
    def secret_id(self) -> str: ...

    def read(self) -> str | None:
        """The current value, or `None` when there is none."""
        ...

    def write(self, value: str) -> str | None:
        """Store a new current version; its version id, when the store gives one."""
        ...

    def describe(self) -> None:
        """Check that the secret exists and this identity may see it, reading no value."""
        ...


class TabroomPasswordSecret:
    """The password secret, in the one shape it is written and read in."""

    def __init__(self, secret: SecretText) -> None:
        self._secret = secret

    @property
    def secret_id(self) -> str:
        return self._secret.secret_id

    def check(self) -> None:
        """Fail now, before anyone types a password, if the secret cannot be reached."""
        self._secret.describe()

    def write(self, credentials: TabroomCredentials) -> str | None:
        """Replace what the secret holds with `credentials`. Returns the new version's id."""
        document = json.dumps(
            {"username": credentials.username, "password": credentials.password.get_secret_value()}
        )
        return self._secret.write(document)

    def read(self) -> TabroomCredentials:
        """The stored credentials. Raises rather than returning anything partial."""
        raw = self._secret.read()
        if raw is None:
            raise TabroomCredentialsMissing(self.secret_id)
        try:
            document: Any = json.loads(raw)
            username = document["username"]
            password = document["password"]
        except (ValueError, KeyError, TypeError):
            # `from None`: the decoder's message quotes the text it choked on, which is the secret.
            raise TabroomCredentialsUnreadable(self.secret_id) from None
        if not isinstance(username, str) or not isinstance(password, str) or not username or not password:
            raise TabroomCredentialsUnreadable(self.secret_id)
        return TabroomCredentials(username=username, password=SecretStr(password))


class TokenSink(Protocol):
    """Where the issued token goes: the token store, on its Secrets Manager backend."""

    @property
    def location(self) -> str: ...

    def save(self, token: SecretStr, *, expires_at: datetime | None) -> StoredToken: ...


@dataclass(frozen=True, slots=True)
class ScheduledLoginOutcome:
    """What a login that worked did. Holds no secret."""

    token_location: str
    expires_at: datetime | None


def login_failure_notification(error: BaseException, *, environment: str) -> Notification:
    """What the coach is told when the weekly login failed. Never the account, never a secret.

    Built from the error's code alone, never its message: a message is this project's text, but the
    rule that a notification says nothing about the account is easier to keep with no message at all.
    """
    code = error_code_of(error)
    refused = code == "CASELIST_LOGIN_REJECTED"
    return Notification(
        title="Weekly caselist login failed",
        subtitle=f"Login ({environment})",
        message=(
            f"The scheduled OpenCaselist login stopped with {code}, so no new caselist_token was "
            "stored. The run uses the previous token if it still works. A refused login is not "
            "tried again until next week."
        ),
        fix_command=SET_PASSWORD_COMMAND if refused else HAND_LOGIN_COMMAND,
        hint=(
            "If the password is right and Tabroom now asks for something more, log in by hand "
            f"instead: {HAND_LOGIN_COMMAND}."
            if refused
            else f"If the password changed at Tabroom, write it again: {SET_PASSWORD_COMMAND}."
        ),
    )


class ScheduledLogin:
    """Read the password, log in once, store the token; tell the operator when any of it fails."""

    def __init__(
        self,
        *,
        credentials: TabroomPasswordSecret,
        session: Callable[[], CaselistLoginSession],
        tokens: Callable[[], TokenSink],
        notifier: Notifier,
        environment: str,
    ) -> None:
        self._credentials = credentials
        self._session = session
        self._tokens = tokens
        self._notifier = notifier
        self._environment = environment

    async def run(self) -> ScheduledLoginOutcome:
        """One login. Every failure is notified and then raised, so the task ends non-zero."""
        try:
            return await self._log_in()
        except DomainError as error:
            self._notifier.notify(login_failure_notification(error, environment=self._environment))
            raise

    async def _log_in(self) -> ScheduledLoginOutcome:
        session = self._session()
        tokens = self._tokens()
        credentials = self._credentials.read()
        async with session:
            issued: IssuedToken = await session.login(credentials.username, credentials.password)
        del credentials
        stored = tokens.save(issued.token, expires_at=issued.expires_at)
        return ScheduledLoginOutcome(token_location=tokens.location, expires_at=stored.expires_at)
