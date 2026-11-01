"""A stand-in for the macOS Security framework, under `keyring`'s own macOS backend (`v1-e34-t33`).

`keyring.backends.macOS.Keyring` turns what the Security framework answers into `keyring`'s errors:
which class it raises for which call, and the framework's error it chains as `__cause__`. That
translation is what the token store reads, so it is kept: the backend is `keyring`'s own class, at
the version `uv.lock` pins, and only the module it calls the framework through, `api`, is replaced.
:class:`StandInSecurity` is that module. It keeps items in a dict and answers each call with the
OSStatus a test scripts for it.

**No test reaches the real keychain.** :func:`macos_keyring_over` replaces `api` on the backend's
module before the backend is built and checks it is the stand-in that will be called; the real
`api` (which on Linux cannot even be imported) is never called.

The stand-in's errors say what the real ones say, plus :data:`KEYCHAIN_MESSAGE_SENTINEL`, a path
generated per run: a message that reached an error, a log or a run record would carry it.
"""

from __future__ import annotations

import contextlib
import secrets
from typing import Final, Literal

import pytest
from keyring.backends import macOS

type SecurityCall = Literal["find", "add", "delete"]
"""`SecItemCopyMatching` (read), `SecItemAdd` (store) and `SecItemDelete` (delete, and the delete a
store makes first)."""

ITEM_NOT_FOUND: Final = -25300
"""`errSecItemNotFound`, SecBase.h."""

KEYCHAIN_MESSAGE_SENTINEL: Final = f"/Users/stand-in-{secrets.token_hex(4)}/Library/Keychains"
"""A path that exists nowhere but in this process, in every message the stand-in's errors carry."""


class Error(Exception):
    """`keyring.backends.macOS.api.Error`: `(status, text)`, as `raise_for_status` builds it."""

    @classmethod
    def raise_for_status(cls, status: int) -> None:
        # The same mapping as keyring 25.7.0, keyring/backends/macOS/api.py lines 111-126; the text
        # carries the sentinel besides.
        if status == 0:
            return
        text = f"keychain {KEYCHAIN_MESSAGE_SENTINEL}/login.keychain-db"
        if status == ITEM_NOT_FOUND:
            raise NotFound(status, f"Item not found in {text}")
        if status == -128:
            raise KeychainDenied(status, f"Keychain Access Denied: {text}")
        if status in (-25293, -67030):
            raise SecAuthFailure(status, f"Security Auth Failure: {text}")
        raise cls(status, f"Unknown Error: {text}")


class NotFound(Error):
    pass


class KeychainDenied(Error):
    pass


class SecAuthFailure(Error):
    pass


class StandInSecurity:
    """The `api` module `keyring`'s macOS backend calls, over a dict, with scripted OSStatus answers."""

    Error = Error
    NotFound = NotFound
    KeychainDenied = KeychainDenied
    SecAuthFailure = SecAuthFailure

    def __init__(self) -> None:
        self.items: dict[tuple[str, str], str] = {}
        self.answers: dict[SecurityCall, int] = {}
        """The OSStatus each call answers with instead of doing its work."""
        self.calls: list[SecurityCall] = []

    def answer(self, call: SecurityCall, status: int) -> None:
        self.answers[call] = status

    def _scripted(self, call: SecurityCall) -> None:
        self.calls.append(call)
        Error.raise_for_status(self.answers.get(call, 0))

    def find_generic_password(self, kc_name: object, service: str, username: str) -> str:
        self._scripted("find")
        if (service, username) not in self.items:
            Error.raise_for_status(ITEM_NOT_FOUND)
        return self.items[(service, username)]

    def set_generic_password(self, name: object, service: str, username: str, password: str) -> None:
        # As keyring's: delete what is there, a missing item being no error, then add.
        with contextlib.suppress(NotFound):
            self.delete_generic_password(name, service, username)
        self._scripted("add")
        self.items[(service, username)] = password

    def delete_generic_password(self, name: object, service: str, username: str) -> None:
        self._scripted("delete")
        if (service, username) not in self.items:
            Error.raise_for_status(ITEM_NOT_FOUND)
        del self.items[(service, username)]


def macos_keyring_over(security: StandInSecurity, monkeypatch: pytest.MonkeyPatch) -> macOS.Keyring:
    """`keyring`'s own macOS backend, calling `security` in place of the Security framework."""
    monkeypatch.setattr(macOS, "api", security, raising=False)
    monkeypatch.setattr(macOS.Keyring, "keychain", None)
    assert macOS.api is security, "the real Security framework would be called"
    return macOS.Keyring()
