"""Sign-in, from the redirect to managed login to a session, and each request after (ADR-0019 (d)).

**The callback** accepts an answer only when it carries the `state` of a transaction this browser
started in the last five minutes, and only after the code has been redeemed with that
transaction's PKCE verifier and the ID token's signature, issuer, audience, expiry, use and `nonce`
have been checked. Cognito does not insist on PKCE for a confidential client, so the app does: every
transaction carries an `S256` challenge, and every exchange sends its verifier.

**No session without an authenticator.** The account's own second factors decide what comes next
(:func:`sign_in_decision`):

* an account with an authenticator gets a session;
* an account in `email-second-factor` with a verified email gets one too (PM ruling, 2026-10-19);
* any other account gets a :class:`PendingEnrolment`, which opens the app's authenticator page and
  nothing else. This is the student who chose email at managed login's first setup.

An account in neither `coach` nor `student` gets nothing.

**Every request** checks the session's lifetimes (:func:`session_standing`). At most every five
minutes it redeems the refresh token again and re-reads the account, so a coach's disable, reset or
removal, which signs the account out everywhere, ends the session within five minutes, and so does
losing the last second factor or the role.
"""

from __future__ import annotations

import contextlib
import hmac
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from debate_core.application.errors import DomainError
from debate_core.application.ports.tub import (
    AccountSelfService,
    AccountStanding,
    AuditSink,
    IdentityProvider,
    TokenRefused,
)
from debate_core.application.tub.identity import EMAIL_SECOND_FACTOR_GROUP, role_from_groups
from debate_core.application.tub.sessions import (
    PendingEnrolment,
    Session,
    SessionStanding,
    SignInTransaction,
    enrolment_is_current,
    new_csrf_token,
    new_sign_in_transaction,
    session_standing,
    transaction_is_current,
)

__all__ = [
    "EnrolmentRequired",
    "SessionEnded",
    "SessionStarted",
    "SignInDecision",
    "SignInRefusal",
    "SignInRefused",
    "SignInService",
    "sign_in_decision",
]


class SignInRefusal(StrEnum):
    """Why the callback refused an answer, as a page can tell the student."""

    NO_TRANSACTION = "no-transaction"
    TOO_SLOW = "too-slow"
    PROVIDER_ERROR = "provider-error"
    NOT_THIS_SIGN_IN = "not-this-sign-in"
    TOKEN_REFUSED = "token-refused"
    NO_ROLE = "no-role"


class SignInRefused(DomainError):
    """The callback's answer was not accepted. :attr:`reason` is a fixed phrase, never a value it was sent."""

    def __init__(self, refusal: SignInRefusal, reason: str) -> None:
        self.refusal = refusal
        self.reason = reason
        super().__init__(f"sign-in was not completed: {reason}")


class SessionEnded(DomainError):
    """A session or pending enrolment is over: its time ran out, or the account no longer qualifies."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"the session has ended: {reason}")


class SignInDecision(StrEnum):
    START_SESSION = "start-session"
    ENROL_AUTHENTICATOR = "enrol-authenticator"


def sign_in_decision(*, email_second_factor: bool, standing: AccountStanding) -> SignInDecision:
    """Whether an account with this standing may have a session, or must enrol an authenticator first."""
    if standing.has_authenticator:
        return SignInDecision.START_SESSION
    if email_second_factor and standing.email is not None and standing.email_verified:
        return SignInDecision.START_SESSION
    return SignInDecision.ENROL_AUTHENTICATOR


@dataclass(frozen=True, slots=True)
class SessionStarted:
    session: Session
    return_to: str


@dataclass(frozen=True, slots=True)
class EnrolmentRequired:
    enrolment: PendingEnrolment


class SignInService:
    """The sign-in flow and the per-request session check, over the identity provider's ports."""

    def __init__(
        self,
        *,
        identity_provider: IdentityProvider,
        self_service: AccountSelfService,
        audit: AuditSink,
        clock: Callable[[], datetime],
    ) -> None:
        self._identity_provider = identity_provider
        self._self_service = self_service
        self._audit = audit
        self._clock = clock

    def begin(self, return_to: str | None) -> tuple[SignInTransaction, str]:
        """A new transaction, and the managed login URL to send the browser to."""
        transaction = new_sign_in_transaction(return_to or "/", self._clock())
        return transaction, self._identity_provider.authorization_url(transaction)

    def complete(
        self,
        *,
        transaction: SignInTransaction | None,
        state: str | None,
        code: str | None,
        provider_error: str | None,
    ) -> SessionStarted | EnrolmentRequired:
        """Check the callback's answer against `transaction` and turn it into a session or an enrolment."""
        now = self._clock()
        if transaction is None:
            raise SignInRefused(SignInRefusal.NO_TRANSACTION, "this browser has no sign-in in progress")
        if not transaction_is_current(transaction, now):
            raise SignInRefused(SignInRefusal.TOO_SLOW, "the sign-in took longer than five minutes")
        if provider_error:
            raise SignInRefused(SignInRefusal.PROVIDER_ERROR, "managed login answered with an error")
        if not state or not hmac.compare_digest(state.encode(), transaction.state.encode()):
            raise SignInRefused(
                SignInRefusal.NOT_THIS_SIGN_IN, "the answer is not for the sign-in this browser started"
            )
        if not code:
            raise SignInRefused(SignInRefusal.NOT_THIS_SIGN_IN, "the answer carries no code")
        try:
            tokens = self._identity_provider.exchange_code(code, transaction.code_verifier)
        except TokenRefused as refused:
            raise SignInRefused(SignInRefusal.TOKEN_REFUSED, refused.reason) from refused
        identity = tokens.identity
        if identity.nonce is None or not hmac.compare_digest(
            identity.nonce.encode(), transaction.nonce.encode()
        ):
            raise SignInRefused(
                SignInRefusal.NOT_THIS_SIGN_IN, "the ID token was not issued for this sign-in"
            )
        role = role_from_groups(identity.groups)
        if role is None:
            raise SignInRefused(SignInRefusal.NO_ROLE, "the account has no role in the pilot")
        if tokens.refresh_token is None:
            raise SignInRefused(SignInRefusal.TOKEN_REFUSED, "no refresh token was issued")
        email_second_factor = EMAIL_SECOND_FACTOR_GROUP in identity.groups
        standing = self._self_service.standing(tokens.access_token)
        decision = sign_in_decision(email_second_factor=email_second_factor, standing=standing)
        if decision is SignInDecision.ENROL_AUTHENTICATOR:
            return EnrolmentRequired(
                PendingEnrolment(
                    subject=identity.subject,
                    username=identity.username,
                    role=role,
                    email_second_factor=email_second_factor,
                    started_at=now,
                    return_to=transaction.return_to,
                    csrf_token=new_csrf_token(),
                    refresh_token=tokens.refresh_token,
                )
            )
        session = Session(
            subject=identity.subject,
            username=identity.username,
            role=role,
            email_second_factor=email_second_factor,
            started_at=now,
            last_seen_at=now,
            revalidated_at=now,
            csrf_token=new_csrf_token(),
            refresh_token=tokens.refresh_token,
        )
        return SessionStarted(session=session, return_to=transaction.return_to)

    def check(self, session: Session) -> Session:
        """The session for this request, revalidated if it is due. `SessionEnded` if it is over."""
        now = self._clock()
        standing = session_standing(session, now)
        if standing is SessionStanding.EXPIRED:
            raise SessionEnded("twelve hours have passed since sign-in")
        if standing is SessionStanding.IDLE:
            raise SessionEnded("an hour passed without a request")
        if standing is SessionStanding.DUE_FOR_REVALIDATION:
            session = self._revalidated(session, now)
        return session.seen(now)

    def check_enrolment(self, enrolment: PendingEnrolment) -> PendingEnrolment:
        """The pending enrolment, if it may still be finished. `SessionEnded` if not."""
        if not enrolment_is_current(enrolment, self._clock()):
            raise SessionEnded("the enrolment took longer than fifteen minutes")
        return enrolment

    def finish_enrolment(self, enrolment: PendingEnrolment) -> Session:
        """The session an enrolment becomes once its authenticator is confirmed."""
        now = self._clock()
        return Session(
            subject=enrolment.subject,
            username=enrolment.username,
            role=enrolment.role,
            email_second_factor=enrolment.email_second_factor,
            started_at=enrolment.started_at,
            last_seen_at=now,
            revalidated_at=now,
            csrf_token=new_csrf_token(),
            refresh_token=enrolment.refresh_token,
        )

    def sign_out(self, refresh_token: str | None) -> str:
        """Revoke the refresh token if there is one, and return managed login's `/logout` URL.

        A revocation that fails does not stop the sign-out: the cookies are cleared either way, and
        the token expires within twelve hours on its own.
        """
        if refresh_token is not None:
            with contextlib.suppress(DomainError):
                self._identity_provider.revoke(refresh_token)
        return self._identity_provider.sign_out_url()

    def _revalidated(self, session: Session, now: datetime) -> Session:
        try:
            tokens = self._identity_provider.refresh(session.refresh_token)
        except TokenRefused as refused:
            raise SessionEnded("the account was signed out, disabled or removed") from refused
        identity = tokens.identity
        if identity.subject != session.subject:
            raise SessionEnded("the refresh token belongs to another account")
        role = role_from_groups(identity.groups)
        if role is None:
            raise SessionEnded("the account no longer has a role in the pilot")
        email_second_factor = EMAIL_SECOND_FACTOR_GROUP in identity.groups
        try:
            standing = self._self_service.standing(tokens.access_token)
        except TokenRefused as refused:
            raise SessionEnded("the account was signed out, disabled or removed") from refused
        if sign_in_decision(email_second_factor=email_second_factor, standing=standing) is not (
            SignInDecision.START_SESSION
        ):
            raise SessionEnded("the account no longer has a second factor it may sign in with")
        return replace(session, role=role, email_second_factor=email_second_factor, revalidated_at=now)
