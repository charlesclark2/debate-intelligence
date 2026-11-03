"""Who is signing in: usernames, roles and groups, and the secrets that are shown once.

**Usernames.** The pool signs in by username and never by email (ADR-0019 (d)), so a username is 3
to 32 lowercase letters, digits and dots, and never anything with an `@` in it. Cognito compares
usernames without regard to case; refusing capitals here, rather than folding them, means the name
the coach typed is the name the student types.

**Roles** come from the pool's groups: `coach` and `student`. An account in both is a coach; an
account in neither has no role and is given no session. `email-second-factor` is a group too, but
it is not a role: it is the coach's ruling that this one account may use a verified email as its
only second factor (PM ruling, 2026-10-19).

**Secrets.** A temporary password and an authenticator's secret are held in objects whose `repr`
and `str` say nothing, so that an f-string, a log line or a traceback that reaches one prints a
placeholder. Only :meth:`TemporaryPassword.reveal` and :meth:`AuthenticatorSecret.reveal` give
the value, and only the two displays the spec allows call them: `tub users add`'s and `reset`'s
one line, and the authenticator page itself.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Iterable
from enum import StrEnum
from typing import Final

from debate_core.application.errors import DomainError

__all__ = [
    "EMAIL_SECOND_FACTOR_GROUP",
    "TEMPORARY_PASSWORD_ALPHABET",
    "USERNAME_PATTERN",
    "AuthenticatorSecret",
    "InvalidUsername",
    "Role",
    "TemporaryPassword",
    "generate_temporary_password",
    "parse_username",
    "role_from_groups",
]


class Role(StrEnum):
    """What an account may do in the pilot, named as the pool's group is."""

    STUDENT = "student"
    COACH = "coach"


EMAIL_SECOND_FACTOR_GROUP: Final = "email-second-factor"
"""The group whose members may sign in with a verified email as their only second factor."""

USERNAME_PATTERN: Final = re.compile(r"[a-z0-9.]{3,32}")
"""A whole username: 3 to 32 lowercase letters, digits and dots."""


class InvalidUsername(DomainError):
    """A name that cannot be a pilot username. The message says why and does not repeat the name."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        """What is wrong with it, in words a coach can act on."""
        super().__init__(f"not a username: {reason}")


def parse_username(raw: str) -> str:
    """Return `raw` if it is a pilot username, or raise :class:`InvalidUsername` saying why not."""
    if "@" in raw:
        raise InvalidUsername("a username is never an email address")
    if USERNAME_PATTERN.fullmatch(raw) is None:
        raise InvalidUsername("use 3 to 32 lowercase letters, digits and dots")
    return raw


def role_from_groups(groups: Iterable[str]) -> Role | None:
    """The role an account's groups give it: coach over student, and `None` for neither."""
    names = set(groups)
    if Role.COACH.value in names:
        return Role.COACH
    if Role.STUDENT.value in names:
        return Role.STUDENT
    return None


TEMPORARY_PASSWORD_ALPHABET: Final = "abcdefghjkmnpqrstuvwxyz23456789"
"""Lowercase letters and digits without the ones a person misreads aloud: 0, 1, i, l and o."""

_TEMPORARY_PASSWORD_GROUPS: Final = 4
_TEMPORARY_PASSWORD_GROUP_LENGTH: Final = 4


class TemporaryPassword:
    """A temporary password, which prints as a placeholder everywhere except :meth:`reveal`."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        """The password itself, for the one display `tub users add` and `reset` make."""
        return self._value

    def __repr__(self) -> str:
        return "TemporaryPassword(<shown once, never logged>)"

    __str__ = __repr__


def generate_temporary_password() -> TemporaryPassword:
    """Sixteen random characters in four groups of four, about 79 bits, from :mod:`secrets`.

    Nineteen characters with the hyphens, which the pool's 12-character minimum and its absence
    of character-class rules both accept. The coach reads it to the student, so it avoids
    characters that look alike.
    """
    groups = (
        "".join(secrets.choice(TEMPORARY_PASSWORD_ALPHABET) for _ in range(_TEMPORARY_PASSWORD_GROUP_LENGTH))
        for _ in range(_TEMPORARY_PASSWORD_GROUPS)
    )
    return TemporaryPassword("-".join(groups))


class AuthenticatorSecret:
    """A new authenticator's shared secret, from `AssociateSoftwareToken`. Never stored or logged."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        """The base32 secret, for the QR code and the typed-in fallback on the enrolment page."""
        return self._value

    def __repr__(self) -> str:
        return "AuthenticatorSecret(<shown on the enrolment page only>)"

    __str__ = __repr__
