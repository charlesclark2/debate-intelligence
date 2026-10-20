"""The pilot's encrypted cookies (ADR-0019 (d), Where the session lives).

Each is a `__Host-` cookie, `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/` and no `Domain`, whose
value is AES-GCM ciphertext under a key only the function holds:

* `__Host-tub_session`: a `Session`, until the session's 12-hour end;
* `__Host-tub_signin`: a `SignInTransaction`, 5 minutes;
* `__Host-tub_enrol`: a `PendingEnrolment`, 15 minutes;
* `__Host-tub_cart`: `v1-e39-t08`'s download cart, which is only cleared here, at sign-out.

The three types are in :mod:`debate_core.application.tub.sessions`.

**Sealing.** `v1.` then unpadded base64url of a 12-byte random nonce and the ciphertext. The
cookie's own name is the additional authenticated data, so a value sealed as one cookie never
opens as another: a sign-in transaction cannot be replayed as a session. A value opens under the
current key or, during a rotation, the previous one; anything that does not open, or opens to
something that is not the expected shape, is treated as no cookie at all.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Final, cast

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from debate_api.configuration import CookieKeys
from debate_core.application.tub.identity import Role
from debate_core.application.tub.sessions import PendingEnrolment, Session, SignInTransaction

__all__ = [
    "ALL_COOKIES",
    "CART_COOKIE",
    "ENROLMENT_COOKIE",
    "SESSION_COOKIE",
    "SIGN_IN_COOKIE",
    "CookieSealer",
    "enrolment_from_payload",
    "enrolment_payload",
    "session_from_payload",
    "session_payload",
    "transaction_from_payload",
    "transaction_payload",
]

SESSION_COOKIE: Final = "__Host-tub_session"
SIGN_IN_COOKIE: Final = "__Host-tub_signin"
ENROLMENT_COOKIE: Final = "__Host-tub_enrol"
CART_COOKIE: Final = "__Host-tub_cart"
ALL_COOKIES: Final = (SESSION_COOKIE, SIGN_IN_COOKIE, ENROLMENT_COOKIE, CART_COOKIE)

_FORMAT: Final = "v1."
_NONCE_BYTES: Final = 12


class CookieSealer:
    """Seals and opens cookie values with the current key, and opens with the previous one too."""

    def __init__(self, keys: CookieKeys) -> None:
        self._current = AESGCM(keys.current)
        self._previous = AESGCM(keys.previous)

    def seal(self, name: str, payload: Mapping[str, object]) -> str:
        nonce = os.urandom(_NONCE_BYTES)
        plaintext = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ciphertext = self._current.encrypt(nonce, plaintext, name.encode())
        return _FORMAT + base64.urlsafe_b64encode(nonce + ciphertext).rstrip(b"=").decode("ascii")

    def open(self, name: str, value: str | None) -> dict[str, object] | None:
        if not value or not value.startswith(_FORMAT):
            return None
        encoded = value[len(_FORMAT) :]
        try:
            sealed = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        except (binascii.Error, ValueError):
            return None
        nonce, ciphertext = sealed[:_NONCE_BYTES], sealed[_NONCE_BYTES:]
        if len(nonce) != _NONCE_BYTES or not ciphertext:
            return None
        for key in (self._current, self._previous):
            try:
                plaintext = key.decrypt(nonce, ciphertext, name.encode())
            except InvalidTag:
                continue
            try:
                document = json.loads(plaintext)
            except ValueError:
                return None
            return cast(dict[str, object], document) if isinstance(document, dict) else None
        return None


# --------------------------------------------------------------------------------------------
# What each cookie holds, field by field
# --------------------------------------------------------------------------------------------


def session_payload(session: Session) -> dict[str, object]:
    return {
        "subject": session.subject,
        "username": session.username,
        "role": session.role.value,
        "email_second_factor": session.email_second_factor,
        "started_at": _timestamp(session.started_at),
        "last_seen_at": _timestamp(session.last_seen_at),
        "revalidated_at": _timestamp(session.revalidated_at),
        "csrf_token": session.csrf_token,
        "refresh_token": session.refresh_token,
    }


def session_from_payload(payload: Mapping[str, object] | None) -> Session | None:
    if payload is None:
        return None
    try:
        return Session(
            subject=_text(payload, "subject"),
            username=_text(payload, "username"),
            role=Role(_text(payload, "role")),
            email_second_factor=_flag(payload, "email_second_factor"),
            started_at=_time(payload, "started_at"),
            last_seen_at=_time(payload, "last_seen_at"),
            revalidated_at=_time(payload, "revalidated_at"),
            csrf_token=_text(payload, "csrf_token"),
            refresh_token=_text(payload, "refresh_token"),
        )
    except (KeyError, TypeError, ValueError):
        return None


def enrolment_payload(enrolment: PendingEnrolment) -> dict[str, object]:
    return {
        "subject": enrolment.subject,
        "username": enrolment.username,
        "role": enrolment.role.value,
        "email_second_factor": enrolment.email_second_factor,
        "started_at": _timestamp(enrolment.started_at),
        "return_to": enrolment.return_to,
        "csrf_token": enrolment.csrf_token,
        "refresh_token": enrolment.refresh_token,
    }


def enrolment_from_payload(payload: Mapping[str, object] | None) -> PendingEnrolment | None:
    if payload is None:
        return None
    try:
        return PendingEnrolment(
            subject=_text(payload, "subject"),
            username=_text(payload, "username"),
            role=Role(_text(payload, "role")),
            email_second_factor=_flag(payload, "email_second_factor"),
            started_at=_time(payload, "started_at"),
            return_to=_text(payload, "return_to"),
            csrf_token=_text(payload, "csrf_token"),
            refresh_token=_text(payload, "refresh_token"),
        )
    except (KeyError, TypeError, ValueError):
        return None


def transaction_payload(transaction: SignInTransaction) -> dict[str, object]:
    return {
        "state": transaction.state,
        "nonce": transaction.nonce,
        "return_to": transaction.return_to,
        "created_at": _timestamp(transaction.created_at),
        "code_verifier": transaction.code_verifier,
    }


def transaction_from_payload(payload: Mapping[str, object] | None) -> SignInTransaction | None:
    if payload is None:
        return None
    try:
        return SignInTransaction(
            state=_text(payload, "state"),
            nonce=_text(payload, "nonce"),
            return_to=_text(payload, "return_to"),
            created_at=_time(payload, "created_at"),
            code_verifier=_text(payload, "code_verifier"),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _timestamp(moment: datetime) -> float:
    return moment.timestamp()


def _text(payload: Mapping[str, object], name: str) -> str:
    value = payload[name]
    if not isinstance(value, str) or not value:
        raise TypeError(name)
    return value


def _flag(payload: Mapping[str, object], name: str) -> bool:
    value = payload[name]
    if not isinstance(value, bool):
        raise TypeError(name)
    return value


def _time(payload: Mapping[str, object], name: str) -> datetime:
    value = payload[name]
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise TypeError(name)
    return datetime.fromtimestamp(value, tz=UTC)
