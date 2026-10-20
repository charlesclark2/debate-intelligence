"""What a signed-in browser holds, and how long each piece of it lasts (ADR-0019 (d), Lifetimes).

Three things live in the browser, each in its own encrypted `__Host-` cookie that `debate_api`
seals and opens:

* a :class:`SignInTransaction` while the student is on managed login: the OAuth `state`, the
  OIDC `nonce` and the PKCE verifier, for five minutes;
* a :class:`PendingEnrolment` when the account has no authenticator yet: enough to finish the
  app's own enrolment page and nothing more, for fifteen minutes;
* a :class:`Session` once it has one.

No ID or access token is kept in any of them. The refresh token is, because revalidation needs it
and only the function holds the client secret that redeems it.

| Lifetime | Value |
|---|---|
| Idle timeout | 60 minutes without a request |
| Absolute session lifetime | 12 hours from sign-in |
| Revalidation | at most every 5 minutes |
| Sign-in transaction | 5 minutes |
| Pending enrolment | 15 minutes (this module's choice: ADR-0019 sets none) |
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final

from debate_core.application.tub.identity import Role

__all__ = [
    "ENROLMENT_LIFETIME",
    "SESSION_ABSOLUTE_LIFETIME",
    "SESSION_IDLE_TIMEOUT",
    "SESSION_REVALIDATION_INTERVAL",
    "SIGN_IN_TRANSACTION_LIFETIME",
    "PendingEnrolment",
    "Session",
    "SessionStanding",
    "SignInTransaction",
    "enrolment_is_current",
    "new_csrf_token",
    "new_sign_in_transaction",
    "safe_return_path",
    "session_standing",
    "transaction_is_current",
]

SESSION_IDLE_TIMEOUT: Final = timedelta(minutes=60)
SESSION_ABSOLUTE_LIFETIME: Final = timedelta(hours=12)
SESSION_REVALIDATION_INTERVAL: Final = timedelta(minutes=5)
SIGN_IN_TRANSACTION_LIFETIME: Final = timedelta(minutes=5)
ENROLMENT_LIFETIME: Final = timedelta(minutes=15)
"""Long enough to install an authenticator app and scan a code, short enough to be one sitting."""


def new_csrf_token() -> str:
    """A session's CSRF token: 32 random bytes, URL-safe, compared in constant time by the app."""
    return secrets.token_urlsafe(32)


@dataclass(frozen=True, slots=True)
class Session:
    """A signed-in browser. Sealed into `__Host-tub_session` by the app."""

    subject: str
    """The pool subject: the account, without naming anyone."""
    username: str
    role: Role
    email_second_factor: bool
    """Whether the account is in `email-second-factor`, as of the last revalidation."""
    started_at: datetime
    last_seen_at: datetime
    revalidated_at: datetime
    csrf_token: str = field(repr=False)
    refresh_token: str = field(repr=False)

    def seen(self, now: datetime) -> Session:
        """This session, with a request at `now`."""
        return replace(self, last_seen_at=now)


class SessionStanding(StrEnum):
    """Where a session is in its lifetimes, at one moment."""

    CURRENT = "current"
    DUE_FOR_REVALIDATION = "due-for-revalidation"
    IDLE = "idle"
    EXPIRED = "expired"


def session_standing(session: Session, now: datetime) -> SessionStanding:
    """The session's standing at `now`. Expiry is checked first, then idleness, then revalidation.

    A time in the future is treated as expired: the cookie is authenticated, so it can only come
    from a clock that moved, and a session whose age cannot be trusted is not one to keep.
    """
    if now - session.started_at >= SESSION_ABSOLUTE_LIFETIME or session.started_at > now:
        return SessionStanding.EXPIRED
    if now - session.last_seen_at >= SESSION_IDLE_TIMEOUT or session.last_seen_at > now:
        return SessionStanding.IDLE
    if now - session.revalidated_at >= SESSION_REVALIDATION_INTERVAL or session.revalidated_at > now:
        return SessionStanding.DUE_FOR_REVALIDATION
    return SessionStanding.CURRENT


@dataclass(frozen=True, slots=True)
class PendingEnrolment:
    """An account that signed in without an authenticator: no session yet, only the enrolment page."""

    subject: str
    username: str
    role: Role
    email_second_factor: bool
    started_at: datetime
    return_to: str
    csrf_token: str = field(repr=False)
    refresh_token: str = field(repr=False)


def enrolment_is_current(enrolment: PendingEnrolment, now: datetime) -> bool:
    """Whether a pending enrolment may still be finished at `now`."""
    return enrolment.started_at <= now < enrolment.started_at + ENROLMENT_LIFETIME


@dataclass(frozen=True, slots=True)
class SignInTransaction:
    """One trip to managed login and back: what the callback checks the answer against."""

    state: str
    nonce: str
    return_to: str
    created_at: datetime
    code_verifier: str = field(repr=False)

    @property
    def code_challenge(self) -> str:
        """The PKCE `S256` challenge: unpadded base64url of the verifier's SHA-256 (RFC 7636)."""
        digest = hashlib.sha256(self.code_verifier.encode("ascii")).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def new_sign_in_transaction(return_to: str, now: datetime) -> SignInTransaction:
    """A fresh transaction: random `state` and `nonce`, and an 86-character verifier (RFC 7636: 43-128)."""
    return SignInTransaction(
        state=secrets.token_urlsafe(32),
        nonce=secrets.token_urlsafe(32),
        return_to=safe_return_path(return_to),
        created_at=now,
        code_verifier=secrets.token_urlsafe(64),
    )


def transaction_is_current(transaction: SignInTransaction, now: datetime) -> bool:
    """Whether the callback may still accept an answer to `transaction` at `now`."""
    return transaction.created_at <= now < transaction.created_at + SIGN_IN_TRANSACTION_LIFETIME


def safe_return_path(raw: str | None) -> str:
    """`raw` if it is a path on this site, else `/`: never another host, however it is spelled.

    A path starts with one `/`, and not `//` or `/\\`, which a browser reads as another host; it
    holds no control character and no backslash.
    """
    if not raw or not raw.startswith("/") or raw.startswith(("//", "/\\")):
        return "/"
    if "\\" in raw or any(ord(character) < 0x20 or ord(character) == 0x7F for character in raw):
        return "/"
    return raw
