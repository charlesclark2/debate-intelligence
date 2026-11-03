"""`caselist auth` when the keychain refuses: the cause's code and hint, not "a bug" (`v1-e34-t33`).

Run the way an operator runs them, through `CliRunner` against the real application and the real
composition root with `caselist.token_backend = "keyring"`. The keychain is a stand-in that answers
as `keyring`'s macOS backend does (keyring 25.7.0, keyring/backends/macOS/__init__.py lines 56-77),
installed as the backend `keyring.get_keyring()` returns, so no test reaches the real keychain.
Every message it raises carries a path made per run, which nothing printed may hold.
"""

from __future__ import annotations

import json
import os
import secrets
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import keyring
import pytest
from keyring import errors as keyring_errors
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.exit_codes import ExitCode
from debate_cli.output import UNMODELLED_ERROR_HINT

runner = CliRunner()

KEYCHAIN_PATH = f"/Users/stand-in-{secrets.token_hex(4)}/Library/Keychains/login.keychain-db"
ITEM_NOT_FOUND = -25300


class SecurityError(Exception):
    """`keyring.backends.macOS.api.Error`: `(status, text)`."""


class StandInKeychain:
    """`keyring`'s macOS backend over a dict, each call answering the OSStatus a test gives it."""

    priority = 5
    """What `keyring`'s macOS backend reports on a Mac, so the store takes it for a usable keychain."""

    def __init__(self) -> None:
        self.items: dict[tuple[str, str], str] = {}
        self.answers: dict[str, int] = {}

    def _refusal(self, call: str, *, missing: bool = False) -> SecurityError | None:
        status = self.answers.get(call, ITEM_NOT_FOUND if missing else 0)
        return SecurityError(status, f"Unknown Error: {KEYCHAIN_PATH}") if status else None

    def get_password(self, service: str, username: str) -> str | None:
        refusal = self._refusal("read", missing=(service, username) not in self.items)
        if refusal is None:
            return self.items[(service, username)]
        if refusal.args[0] == ITEM_NOT_FOUND:
            return None
        kind = keyring_errors.KeyringLocked if refusal.args[0] == -128 else keyring_errors.KeyringError
        raise kind(f"Can't get password from keychain: {refusal}") from refusal

    def set_password(self, service: str, username: str, password: str) -> None:
        refusal = self._refusal("store")
        if refusal is not None:
            kind = (
                keyring_errors.KeyringLocked if refusal.args[0] == -128 else keyring_errors.PasswordSetError
            )
            raise kind(f"Can't store password on keychain: {refusal}") from refusal
        self.items[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        refusal = self._refusal("delete", missing=(service, username) not in self.items)
        if refusal is not None:
            raise keyring_errors.PasswordDeleteError(
                f"Can't delete password in keychain: {refusal}"
            ) from refusal
        del self.items[(service, username)]


@pytest.fixture
def keychain(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[StandInKeychain]:
    """A `test` environment whose token backend is the keychain, and the keychain the stand-in."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    for name, value in {
        "DEBATE_ENV": "test",
        "DEBATE_STORAGE__DATA_DIR": str(tmp_path / "data"),
        "DEBATE_CASELIST__TOKEN_BACKEND": "keyring",
    }.items():
        monkeypatch.setenv(name, value)
    stand_in = StandInKeychain()
    monkeypatch.setattr(keyring, "get_keyring", lambda: stand_in)
    yield stand_in


def invoke(*args: str) -> Result:
    return runner.invoke(create_app(), list(args))


def envelope(result: Result) -> dict[str, Any]:
    return json.loads(result.stdout.strip().splitlines()[-1])


def everything_printed(result: Result) -> str:
    return result.stdout + result.stderr + repr(result.exception)


def a_stored_token(keychain: StandInKeychain) -> None:
    keychain.items[("debate-research.opencaselist", "test")] = json.dumps(
        {"token": "fixture-token", "stored_at": "2026-10-20T06:00:00+00:00"}
    )


def test_status_under_launchd_names_the_cause_and_its_fix(keychain: StandInKeychain) -> None:
    a_stored_token(keychain)
    keychain.answers["read"] = -25308

    result = invoke("--json", "caselist", "auth", "status")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, everything_printed(result)
    error = envelope(result)["error"]
    assert error["code"] == "KEYCHAIN_INTERACTION_NOT_ALLOWED"
    assert error["details"] == {"operation": "read", "os_status": -25308}
    assert error["hint"].startswith("The Mac must be logged in, not only switched on")
    assert error["hint"] != UNMODELLED_ERROR_HINT
    assert KEYCHAIN_PATH not in everything_printed(result)
    assert "Unknown Error" not in everything_printed(result)


def test_a_refused_login_store_names_the_file_backend(keychain: StandInKeychain) -> None:
    """`logout` reads first; a store refused at the prompt is the same code on every call."""
    a_stored_token(keychain)
    keychain.answers["delete"] = -128

    result = invoke("--json", "caselist", "auth", "logout")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, everything_printed(result)
    error = envelope(result)["error"]
    assert error["code"] == "KEYCHAIN_DENIED"
    assert error["details"] == {"operation": "delete", "os_status": -128}
    assert 'caselist.token_backend = "file"' in error["hint"]
    assert KEYCHAIN_PATH not in everything_printed(result)


def test_logout_of_a_token_gone_before_its_delete_succeeds_quietly(keychain: StandInKeychain) -> None:
    a_stored_token(keychain)
    keychain.answers["delete"] = ITEM_NOT_FOUND

    result = invoke("--json", "caselist", "auth", "logout")

    assert result.exit_code == ExitCode.OK, everything_printed(result)
    assert envelope(result)["data"]["deleted"] is False


def test_an_unexpected_keychain_answer_is_still_reported_as_a_bug_without_its_message(
    keychain: StandInKeychain,
) -> None:
    a_stored_token(keychain)
    keychain.answers["read"] = -25295

    result = invoke("--json", "caselist", "auth", "status")

    assert result.exit_code == ExitCode.INTERNAL_ERROR, everything_printed(result)
    error = envelope(result)["error"]
    assert error["code"] == "INTERNAL_ERROR"
    assert error["hint"] == UNMODELLED_ERROR_HINT
    assert KEYCHAIN_PATH not in result.stdout
