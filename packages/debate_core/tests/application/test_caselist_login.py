"""The weekly cloud login (`caselist auth renew`): the password in, one login, the token out.

ADR-0020 (2) and (6), and the data-use policy's E34 gate 5: the login runs once and a refused login
is never retried; every failure reaches the operator through the notifier, and no notification
names the account. Fakes stand in for the secret, the OpenCaselist session and the token store;
every value is generated per test.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import TracebackType
from typing import Self

import pytest
from pydantic import SecretStr

from debate_core.application.caselist_login import (
    HAND_LOGIN_COMMAND,
    SET_PASSWORD_COMMAND,
    ScheduledLogin,
    TabroomCredentials,
    TabroomCredentialsMissing,
    TabroomPasswordSecret,
)
from debate_core.application.ports.caselist_source import (
    CaselistApiDisabled,
    CaselistInfo,
    CaselistLoginRejected,
    UnexpectedCaselistResponse,
)
from debate_core.application.ports.notifier import Notification, RecordingNotifier

pytestmark = pytest.mark.anyio

EXPIRY = datetime(2026, 11, 11, 0, 0, tzinfo=UTC)
PASSWORD_SECRET = "debate-test-caselist-tabroom-password"


class SecretInMemory:
    def __init__(self, value: str | None = None) -> None:
        self.secret_id = PASSWORD_SECRET
        self.value = value
        self.reads = 0

    def read(self) -> str | None:
        self.reads += 1
        return self.value

    def write(self, value: str) -> str | None:
        self.value = value
        return "v1"

    def describe(self) -> None:
        return None


@dataclass(frozen=True)
class Issued:
    token: SecretStr
    expires_at: datetime | None


@dataclass
class Session:
    """An OpenCaselist session that answers `login` with `answer`, counting every attempt."""

    answer: Issued | Exception
    attempts: list[tuple[str, str]] = field(default_factory=lambda: [])

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> None:
        return None

    async def login(self, username: str, password: SecretStr) -> Issued:
        self.attempts.append((username, password.get_secret_value()))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer

    async def list_caselists(self, *, archived: bool | None = None) -> list[CaselistInfo]:
        raise AssertionError("the login lists nothing")


@dataclass(frozen=True)
class Stored:
    stored_at: datetime
    expires_at: datetime | None
    last_validated_at: datetime | None
    backend: str = "secretsmanager"

    def expired(self, now: datetime) -> bool:
        return False


@dataclass
class Tokens:
    saved: list[tuple[str, datetime | None]] = field(default_factory=lambda: [])
    location: str = "Secrets Manager secret debate-test-caselist-token"

    def save(self, token: SecretStr, *, expires_at: datetime | None) -> Stored:
        self.saved.append((token.get_secret_value(), expires_at))
        return Stored(stored_at=EXPIRY, expires_at=expires_at, last_validated_at=EXPIRY)


@dataclass
class World:
    username: str
    password: str
    token: str
    secret: SecretInMemory
    tokens: Tokens = field(default_factory=Tokens)
    notifier: RecordingNotifier = field(default_factory=RecordingNotifier)

    def login(self, session: Session | Exception) -> ScheduledLogin:
        def open_session() -> Session:
            if isinstance(session, Exception):
                raise session
            return session

        return ScheduledLogin(
            credentials=TabroomPasswordSecret(self.secret),
            session=open_session,
            tokens=lambda: self.tokens,
            notifier=self.notifier,
            environment="dev",
        )

    def never_named(self, notification: Notification) -> None:
        __tracebackhide__ = True
        text = " ".join(
            str(part)
            for part in (notification.title, notification.subtitle, notification.text, notification.body)
        )
        leaked = [
            name
            for name, value in (
                ("the username", self.username),
                ("the password", self.password),
                ("the token", self.token),
            )
            if value in text
        ]
        if leaked:
            pytest.fail(f"the notification names {' and '.join(leaked)}", pytrace=False)


@pytest.fixture
def world() -> World:
    username = f"fixture-coach-{secrets.token_hex(4)}@example.invalid"
    password = f"fixture-password-{secrets.token_hex(8)}"
    secret = SecretInMemory()
    TabroomPasswordSecret(secret).write(TabroomCredentials(username=username, password=SecretStr(password)))
    return World(username, password, f"fixture-token-{secrets.token_hex(16)}", secret)


async def test_a_login_reads_the_password_once_logs_in_once_and_stores_only_the_token(world: World) -> None:
    session = Session(Issued(SecretStr(world.token), EXPIRY))

    outcome = await world.login(session).run()

    assert len(session.attempts) == 1
    sent = session.attempts[0] == (world.username, world.password)
    assert sent, "the login did not send the stored username and password"
    assert world.secret.reads == 1
    stored = world.tokens.saved == [(world.token, EXPIRY)]
    assert stored, "the issued token was not what was stored"
    assert outcome.expires_at == EXPIRY
    assert outcome.token_location == world.tokens.location
    assert world.notifier.sent == []


async def test_a_refused_login_is_not_retried_is_notified_once_and_ends_the_task(world: World) -> None:
    session = Session(CaselistLoginRejected(401))

    with pytest.raises(CaselistLoginRejected):
        await world.login(session).run()

    assert len(session.attempts) == 1, "a refused login was tried again"
    assert world.tokens.saved == []
    [notification] = world.notifier.sent
    assert "CASELIST_LOGIN_REJECTED" in notification.message
    assert notification.fix_command == SET_PASSWORD_COMMAND
    assert notification.hint is not None and HAND_LOGIN_COMMAND in notification.hint
    assert notification.subtitle == "Login (dev)"
    world.never_named(notification)


@pytest.mark.parametrize(
    "failure",
    [UnexpectedCaselistResponse("log in", "the login answer carries no token")],
)
async def test_any_other_failure_of_the_login_is_notified_with_the_hand_fallback(
    world: World, failure: Exception
) -> None:
    session = Session(failure)

    with pytest.raises(type(failure)):
        await world.login(session).run()

    assert len(session.attempts) == 1
    [notification] = world.notifier.sent
    assert notification.fix_command == HAND_LOGIN_COMMAND
    world.never_named(notification)


async def test_no_password_stored_is_notified_and_nothing_is_attempted(world: World) -> None:
    world.secret.value = None
    session = Session(Issued(SecretStr(world.token), EXPIRY))

    with pytest.raises(TabroomCredentialsMissing):
        await world.login(session).run()

    assert session.attempts == []
    [notification] = world.notifier.sent
    assert "TABROOM_CREDENTIALS_MISSING" in notification.message
    world.never_named(notification)


async def test_a_disabled_api_is_refused_before_the_password_is_read(world: World) -> None:
    with pytest.raises(CaselistApiDisabled):
        await world.login(CaselistApiDisabled()).run()

    assert world.secret.reads == 0, "the password was read although no login could be made"
    assert len(world.notifier.sent) == 1


def test_the_credentials_repr_shows_neither_the_username_nor_the_password(world: World) -> None:
    credentials = TabroomPasswordSecret(world.secret).read()

    shown = world.username in repr(credentials) or world.password in repr(credentials)
    assert not shown, "the credentials' repr shows the username or the password"
