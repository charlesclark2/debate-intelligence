"""Shared fixtures for the OpenCaselist client's tests: secrets made at run time, a fake keychain.

**No token and no password is committed.** Both are generated per test from `secrets`, so the
leak assertions look for strings that exist nowhere but in this process, and a grep of the
repository for anything token-shaped finds nothing (`docs/policies/caselist-data-use.md`).

**No test reaches the real keychain.** :class:`InMemoryKeyring` is handed to the store in place of
the OS backend; a test that forgot to would be writing to the developer's login keychain.
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "opencaselist"


def load_fixture(name: str) -> Any:
    """One of the synthetic response bodies in `tests/fixtures/opencaselist/`."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class InMemoryKeyring:
    """The three `keyring` calls the token store makes, answered from a dict."""

    def __init__(self) -> None:
        self.items: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.items.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.items[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        del self.items[(service, username)]


@pytest.fixture
def fake_token() -> str:
    """A caselist_token that exists only in this test run."""
    return f"fixture-token-{secrets.token_hex(16)}"


@pytest.fixture
def fake_password() -> str:
    """A Tabroom password that exists only in this test run."""
    return f"fixture-password-{secrets.token_hex(8)}"


@pytest.fixture
def fake_username() -> str:
    return f"fixture-user-{secrets.token_hex(4)}@example.invalid"


@pytest.fixture
def memory_keyring() -> InMemoryKeyring:
    return InMemoryKeyring()
