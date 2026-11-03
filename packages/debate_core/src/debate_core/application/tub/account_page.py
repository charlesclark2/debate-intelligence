"""The student's own account changes: the backup email and the authenticator (ADR-0019 (d) 3 and 5).

Managed login does not change a profile, so the app does, with the student's own access token. The
session holds no access token, so each change redeems the refresh token for one, uses it and drops
it.

**The backup email.** Adding one sets it unverified and Cognito emails a code. Entering the code
verifies it and turns both factors on with neither preferred, so managed login asks which to use.
Removing it turns the email factor off first. An account whose email is its only second factor (in
`email-second-factor`, with no authenticator) cannot remove it here: that would leave it with
none, so the student asks the coach.

**The authenticator**, for a pending enrolment only. Beginning gives a new secret; confirming a code
from it turns the factor on. There is no self-service replacement in the pilot (PM ruling (d),
2026-10-20): on dev, beginning a secret dropped an authenticator managed login had set up at once,
which would leave an unfinished replacement open to enrolment by anyone with the password. A
student with a new phone asks the coach for a reset.

Each completed change writes one audit record with the student's subject and no address (ADR-0019
(d) 5: "the audit record says an email was added or removed, never which").
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Final
from urllib.parse import quote, urlencode

from debate_core.application.errors import DomainError
from debate_core.application.ports.tub import (
    AccountSelfService,
    AccountStanding,
    AuditSink,
    CodeRefused,
    IdentityProvider,
    TokenRefused,
)
from debate_core.application.tub.audit import AuditAction, AuditRecord
from debate_core.application.tub.identity import AuthenticatorSecret, Role
from debate_core.application.tub.sessions import PendingEnrolment, Session
from debate_core.application.tub.sign_in import SessionEnded

__all__ = [
    "ONE_TIME_CODE_PATTERN",
    "AccountPageService",
    "AccountView",
    "AuthenticatorEnrolment",
    "EmailIsTheOnlySecondFactor",
    "InvalidEmail",
    "authenticator_uri",
    "parse_email",
]

ONE_TIME_CODE_PATTERN: Final = re.compile(r"[0-9]{6}")
"""An authenticator's code, and the code Cognito emails: six digits."""

_EMAIL_PATTERN: Final = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s.]+")
_EMAIL_MAX_LENGTH: Final = 254


class InvalidEmail(DomainError):
    """Not an email address. The message does not repeat what was typed."""

    def __init__(self) -> None:
        super().__init__("that is not an email address")


class EmailIsTheOnlySecondFactor(DomainError):
    """The backup email is this account's only second factor, so it cannot be removed here."""

    def __init__(self) -> None:
        super().__init__(
            "this account signs in with its email as its only second factor; "
            "ask the coach to change that first"
        )


def parse_email(raw: str) -> str:
    """`raw`, trimmed, if it looks like one email address; :class:`InvalidEmail` if not."""
    email = raw.strip()
    if len(email) > _EMAIL_MAX_LENGTH or _EMAIL_PATTERN.fullmatch(email) is None:
        raise InvalidEmail
    return email


def _one_time_code(raw: str, what: str) -> str:
    code = raw.strip().replace(" ", "")
    if ONE_TIME_CODE_PATTERN.fullmatch(code) is None:
        raise CodeRefused(what)
    return code


def authenticator_uri(secret: AuthenticatorSecret, *, issuer: str, username: str) -> str:
    """The `otpauth://` URI an authenticator app reads from the QR code: SHA-1, six digits, 30 seconds."""
    label = quote(f"{issuer}:{username}", safe="")
    query = urlencode(
        {"secret": secret.reveal(), "issuer": issuer, "algorithm": "SHA1", "digits": "6", "period": "30"},
        quote_via=quote,
    )
    return f"otpauth://totp/{label}?{query}"


@dataclass(frozen=True, slots=True)
class AccountView:
    """What the account page shows: the student's own name, role, factors and email."""

    username: str
    role: Role
    has_authenticator: bool
    email: str | None
    email_verified: bool
    email_second_factor: bool

    @property
    def may_remove_email(self) -> bool:
        """Whether the page offers to remove the email: only while an authenticator remains."""
        return self.email is not None and self.has_authenticator


@dataclass(frozen=True, slots=True)
class AuthenticatorEnrolment:
    """A new authenticator secret and the URI its QR code encodes. Rendered once, never stored."""

    secret: AuthenticatorSecret
    uri: str


class AccountPageService:
    """The account page's and the enrolment page's changes, each on a freshly redeemed access token."""

    def __init__(
        self,
        *,
        identity_provider: IdentityProvider,
        self_service: AccountSelfService,
        audit: AuditSink,
        clock: Callable[[], datetime],
        authenticator_issuer: str,
    ) -> None:
        self._identity_provider = identity_provider
        self._self_service = self_service
        self._audit = audit
        self._clock = clock
        self._issuer = authenticator_issuer

    def view(self, session: Session) -> AccountView:
        standing = self._standing(session.refresh_token)
        return AccountView(
            username=session.username,
            role=session.role,
            has_authenticator=standing.has_authenticator,
            email=standing.email,
            email_verified=standing.email_verified,
            email_second_factor=session.email_second_factor,
        )

    def add_backup_email(self, session: Session, raw_email: str) -> None:
        """Set the backup email, unverified; Cognito sends it a code."""
        email = parse_email(raw_email)
        self._self_service.set_backup_email(self._access_token(session.refresh_token), email)

    def confirm_backup_email(self, session: Session, raw_code: str) -> None:
        """Verify the backup email with its code, and turn both factors on with neither preferred."""
        code = _one_time_code(raw_code, "email")
        access_token = self._access_token(session.refresh_token)
        self._self_service.confirm_backup_email(access_token, code)
        standing = self._self_service.standing(access_token)
        self._self_service.set_second_factors(
            access_token, authenticator=standing.has_authenticator, email=True
        )
        self._record(AuditAction.BACKUP_EMAIL_ADDED, session)

    def remove_backup_email(self, session: Session) -> None:
        """Turn the email factor off and remove the address, unless it is the only second factor."""
        access_token = self._access_token(session.refresh_token)
        standing = self._self_service.standing(access_token)
        if not standing.has_authenticator:
            raise EmailIsTheOnlySecondFactor
        self._self_service.set_second_factors(access_token, authenticator=True, email=False)
        self._self_service.remove_backup_email(access_token)
        self._record(AuditAction.BACKUP_EMAIL_REMOVED, session)

    def begin_authenticator(self, enrolment: PendingEnrolment) -> AuthenticatorEnrolment:
        """A new secret for the enrolment page."""
        secret = self._self_service.begin_authenticator(self._access_token(enrolment.refresh_token))
        return AuthenticatorEnrolment(
            secret=secret, uri=authenticator_uri(secret, issuer=self._issuer, username=enrolment.username)
        )

    def confirm_authenticator(self, enrolment: PendingEnrolment, raw_code: str) -> None:
        """Confirm the new secret with a code from it, and turn the factor on."""
        code = _one_time_code(raw_code, "authenticator")
        access_token = self._access_token(enrolment.refresh_token)
        self._self_service.confirm_authenticator(access_token, code)
        standing = self._self_service.standing(access_token)
        self._self_service.set_second_factors(
            access_token,
            authenticator=True,
            email=standing.email is not None and standing.email_verified,
        )
        self._record(AuditAction.AUTHENTICATOR_REGISTERED, enrolment)

    def _standing(self, refresh_token: str) -> AccountStanding:
        return self._self_service.standing(self._access_token(refresh_token))

    def _access_token(self, refresh_token: str) -> str:
        try:
            return self._identity_provider.refresh(refresh_token).access_token
        except TokenRefused as refused:
            raise SessionEnded("the account was signed out, disabled or removed") from refused

    def _record(self, action: AuditAction, holder: Session | PendingEnrolment) -> None:
        self._audit.record(
            AuditRecord(
                time=self._clock(),
                action=action,
                actor_role=holder.role,
                actor_subject=holder.subject,
                account_subject=holder.subject,
            )
        )
