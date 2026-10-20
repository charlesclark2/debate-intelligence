"""The student search pilot's ports for accounts and sign-in (ADR-0019, Where the code goes).

* :class:`AccountDirectory`: the pool's administrative API, as the coach's `tub users` uses it.
* :class:`IdentityProvider`: the OAuth endpoints of managed login, and the ID token's checks.
* :class:`AccountSelfService`: the token-authorized calls the account and enrolment pages make.
* :class:`AuditSink`: the append-only audit log.

An implementation translates its library's failures into :mod:`debate_core.application.errors`
and the errors below, and never puts a password, a code, a token or a secret in a message.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from debate_core.application.errors import DomainError
from debate_core.application.tub.audit import AuditRecord
from debate_core.application.tub.identity import AuthenticatorSecret, TemporaryPassword
from debate_core.application.tub.sessions import SignInTransaction

__all__ = [
    "AccountDirectory",
    "AccountSelfService",
    "AccountStanding",
    "AuditSink",
    "CodeRefused",
    "DirectoryAccount",
    "IdentityProvider",
    "IssuedTokens",
    "TokenRefused",
    "VerifiedIdentity",
]


# --------------------------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------------------------


class TokenRefused(DomainError):
    """The identity provider refused a code or a refresh token, or issued an ID token that failed a check.

    :attr:`reason` is a short fixed phrase ("the ID token's audience is another client"), never a
    token or a claim's value.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"sign-in refused: {reason}")


class CodeRefused(DomainError):
    """A one-time code (an authenticator's, or an email's) was wrong or expired."""

    def __init__(self, what: str) -> None:
        self.what = what
        """Which code: `"authenticator"` or `"email"`."""
        super().__init__(f"that {what} code was not accepted")


# --------------------------------------------------------------------------------------------
# The administrative API
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DirectoryAccount:
    """An account as the coach's commands see it: no attribute beyond its subject."""

    username: str
    subject: str
    groups: frozenset[str]
    enabled: bool


class AccountDirectory(Protocol):
    """The pool's administrative API, on one pool. A missing account raises `NotFound`."""

    def create(self, username: str, temporary_password: TemporaryPassword) -> str:
        """Create the account with the invitation suppressed; return its subject. `AlreadyExists` if taken."""
        ...

    def add_to_group(self, username: str, group: str) -> None: ...

    def remove_from_group(self, username: str, group: str) -> None: ...

    def get(self, username: str) -> DirectoryAccount: ...

    def list_accounts(self) -> Sequence[DirectoryAccount]:
        """Every account in the pool, with its groups."""
        ...

    def set_temporary_password(self, username: str, temporary_password: TemporaryPassword) -> None:
        """A new temporary password, which the student must change at the next sign-in."""
        ...

    def remove_authenticator(self, username: str) -> None:
        """Delete the account's TOTP factor, if it has one; nothing if it has none."""
        ...

    def sign_out_everywhere(self, username: str) -> None:
        """Revoke every refresh token the account holds, so each session ends at its next revalidation."""
        ...

    def disable(self, username: str) -> None: ...

    def enable(self, username: str) -> None: ...

    def delete(self, username: str) -> None:
        """Delete the account and every attribute on it, the email included (gate item 9)."""
        ...


# --------------------------------------------------------------------------------------------
# Managed login's OAuth endpoints
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class VerifiedIdentity:
    """The claims of an ID token whose signature, issuer, audience, expiry and use were checked."""

    subject: str
    username: str
    groups: frozenset[str]
    nonce: str | None


@dataclass(frozen=True, slots=True)
class IssuedTokens:
    """What a code exchange or a refresh gives back. Used once, then discarded (ADR-0019 (d) 4)."""

    identity: VerifiedIdentity
    access_token: str = field(repr=False)
    refresh_token: str | None = field(repr=False)
    """`None` from a refresh: rotation is off, so the session keeps the one it has."""


class IdentityProvider(Protocol):
    """Managed login, seen from the server: authorize, exchange, refresh, revoke and log out."""

    def authorization_url(self, transaction: SignInTransaction) -> str:
        """Where to send the browser: `/oauth2/authorize` with the state, nonce and S256 challenge."""
        ...

    def exchange_code(self, code: str, code_verifier: str) -> IssuedTokens:
        """Redeem a code with the client secret and the PKCE verifier. `TokenRefused` if refused."""
        ...

    def refresh(self, refresh_token: str) -> IssuedTokens:
        """Redeem the refresh token. `TokenRefused` once the account was signed out, disabled or removed."""
        ...

    def revoke(self, refresh_token: str) -> None:
        """Revoke the refresh token at `/oauth2/revoke`."""
        ...

    def sign_out_url(self) -> str:
        """Managed login's `/logout`, returning to the pilot's `/signed-out`."""
        ...


# --------------------------------------------------------------------------------------------
# The token-authorized self-service calls
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AccountStanding:
    """What `GetUser` says about the account's second factors and its backup email."""

    has_authenticator: bool
    email: str | None
    email_verified: bool
    email_factor_enabled: bool


class AccountSelfService(Protocol):
    """The calls an access token authorizes. A revoked or expired token raises `TokenRefused`."""

    def standing(self, access_token: str) -> AccountStanding: ...

    def begin_authenticator(self, access_token: str) -> AuthenticatorSecret:
        """A new, unverified TOTP secret. The account's current authenticator, if any, keeps working."""
        ...

    def confirm_authenticator(self, access_token: str, code: str) -> None:
        """Verify a code from the new secret, which replaces any earlier one. `CodeRefused` if wrong."""
        ...

    def set_second_factors(self, access_token: str, *, authenticator: bool, email: bool) -> None:
        """Enable exactly these factors; with both, prefer neither, so managed login asks which."""
        ...

    def set_backup_email(self, access_token: str, email: str) -> None:
        """Set an unverified email; Cognito sends it a code."""
        ...

    def confirm_backup_email(self, access_token: str, code: str) -> None:
        """Verify the email with the code it was sent. `CodeRefused` if wrong."""
        ...

    def remove_backup_email(self, access_token: str) -> None: ...


# --------------------------------------------------------------------------------------------
# The audit log
# --------------------------------------------------------------------------------------------


class AuditSink(Protocol):
    """The append-only audit log. A failure to write raises a `StoreError`."""

    def record(self, record: AuditRecord) -> None: ...
