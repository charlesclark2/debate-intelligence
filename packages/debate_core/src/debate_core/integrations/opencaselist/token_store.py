"""Where the operator's caselist_token lives between runs, and nowhere else.

`debate-research caselist auth login` trades the operator's Tabroom credentials for a
`caselist_token` once; this module keeps that token so the scheduled pull (v1-e34-t02) can use it
without anyone typing a password again. The password itself never reaches this module.

## Two backends

* :class:`KeyringTokenBackend` — the OS keychain through `keyring`. On the operator's Mac that is
  the login keychain, which is encrypted at rest and unlocked with the session.
* :class:`FileTokenBackend` — a file created `0600` inside a `0700` directory, for a machine with
  no usable keychain. Its default place is `<data_dir>/secrets/caselist_token`, and `.gitignore`
  ignores both `secrets/` directories and any file named `caselist_token`, so a data directory
  pointed inside a checkout still cannot commit it.

The file backend **refuses to read a file anyone but the owner can read**. A token file that became
group- or world-readable may already have been read, and quietly carrying on would hide that; the
operator is told to log in again instead.

## What is stored

A small JSON document: the token, when it was stored, when the API says it expires, and when a
request last succeeded with it (what `caselist auth status` reports). Never the password, never
the Tabroom username.

## The token is a SecretStr from the moment it is read

:class:`StoredCaselistToken` holds it as a :class:`~pydantic.SecretStr`, so `repr`, a traceback's
locals and a careless f-string show `**********`. Reading it registers it with
:mod:`~debate_core.integrations.opencaselist.redaction`, so even a log line somebody else's code
writes has it scrubbed.
"""

from __future__ import annotations

import contextlib
import json
import os
import stat
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Protocol, cast

from pydantic import SecretStr

from debate_core.application.errors import DomainError
from debate_core.application.settings import CaselistTokenBackend
from debate_core.integrations.opencaselist.redaction import register_secret

__all__ = [
    "DEFAULT_SECRET_FILE",
    "KEYRING_SERVICE",
    "CaselistTokenStore",
    "CaselistTokenUnreadable",
    "FileTokenBackend",
    "InsecureTokenFile",
    "KeyringTokenBackend",
    "KeyringUnavailable",
    "StoredCaselistToken",
    "TokenBackend",
    "default_secret_file",
    "keyring_is_usable",
]

KEYRING_SERVICE: Final = "debate-research.opencaselist"
"""The keychain item's service name. The account is the environment (`dev`, `prod`)."""

DEFAULT_SECRET_FILE: Final = Path("secrets") / "caselist_token"
"""The file backend's path relative to `storage.data_dir`, when `caselist.secret_file` is unset."""

_FILE_MODE: Final = 0o600
_DIRECTORY_MODE: Final = 0o700


def default_secret_file(data_dir: Path) -> Path:
    """Where the file backend keeps the token for a data directory."""
    return data_dir / DEFAULT_SECRET_FILE


# ------------------------------------------------------------------------------------------------
# Errors. None of them carries the token, and none carries the file's contents.
# ------------------------------------------------------------------------------------------------


class InsecureTokenFile(DomainError):
    """The token file can be read by someone other than its owner, so it is not used."""

    def __init__(self, path: Path, mode: int) -> None:
        self.path = path
        self.mode = mode
        super().__init__(
            f"{path} has permissions {stat.filemode(mode)}; a caselist_token file must be readable "
            "by its owner only (0600). It was not used. Delete it, then run "
            "`debate-research caselist auth login` again."
        )


class CaselistTokenUnreadable(DomainError):
    """A stored token record exists but is not one this module wrote."""

    def __init__(self, backend: str) -> None:
        self.backend = backend
        super().__init__(
            f"the caselist_token stored in the {backend} backend is not readable; run "
            "`debate-research caselist auth logout` and then `caselist auth login`"
        )


class KeyringUnavailable(DomainError):
    """`caselist.token_backend` is `keyring`, and this machine has no usable keychain."""

    def __init__(self) -> None:
        super().__init__(
            "caselist.token_backend is `keyring` but no usable OS keychain was found; set "
            "DEBATE_CASELIST__TOKEN_BACKEND=file to keep the token in a 0600 file instead"
        )


# ------------------------------------------------------------------------------------------------
# The stored record
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StoredCaselistToken:
    """The token and what is known about it. `repr` shows `SecretStr('**********')`."""

    token: SecretStr
    stored_at: datetime
    expires_at: datetime | None
    last_validated_at: datetime | None
    backend: str
    """`keyring`, `file` or `settings` (a token supplied through `providers.caselist_token`)."""

    def expired(self, now: datetime) -> bool:
        """Whether the API's stated expiry has passed. A token with no stated expiry never has."""
        return self.expires_at is not None and self.expires_at <= now

    def to_json(self) -> str:
        return json.dumps(
            {
                "token": self.token.get_secret_value(),
                "stored_at": self.stored_at.isoformat(),
                "expires_at": _iso(self.expires_at),
                "last_validated_at": _iso(self.last_validated_at),
            }
        )

    @classmethod
    def from_json(cls, raw: str, *, backend: str) -> StoredCaselistToken:
        try:
            document: Any = json.loads(raw)
            token = document["token"]
            if not isinstance(token, str) or not token:
                raise ValueError("empty token")
            return cls(
                token=SecretStr(token),
                stored_at=datetime.fromisoformat(document["stored_at"]),
                expires_at=_parse_optional(document.get("expires_at")),
                last_validated_at=_parse_optional(document.get("last_validated_at")),
                backend=backend,
            )
        except (ValueError, KeyError, TypeError):
            # `from None`: the JSON decoder's message quotes the text it choked on, which is the
            # token record. The operator needs to know it is unreadable, not what it said.
            raise CaselistTokenUnreadable(backend) from None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _parse_optional(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("not a timestamp")
    return datetime.fromisoformat(value)


# ------------------------------------------------------------------------------------------------
# Backends
# ------------------------------------------------------------------------------------------------


class TokenBackend(Protocol):
    """Somewhere a serialized token record can be kept."""

    @property
    def name(self) -> str: ...

    def read(self) -> str | None: ...

    def write(self, value: str) -> None: ...

    def delete(self) -> bool: ...


class KeyringLike(Protocol):
    """The three calls this module makes on a `keyring` backend."""

    def get_password(self, service: str, username: str) -> str | None: ...

    def set_password(self, service: str, username: str, password: str) -> None: ...

    def delete_password(self, service: str, username: str) -> None: ...


class KeyringTokenBackend:
    """The token record in the OS keychain, one item per environment."""

    @property
    def name(self) -> str:
        return "keyring"

    def __init__(self, *, account: str, keyring: KeyringLike | None = None) -> None:
        self._account = account
        self._keyring = keyring if keyring is not None else _system_keyring()

    def read(self) -> str | None:
        return self._keyring.get_password(KEYRING_SERVICE, self._account)

    def write(self, value: str) -> None:
        self._keyring.set_password(KEYRING_SERVICE, self._account, value)

    def delete(self) -> bool:
        if self.read() is None:
            return False
        self._keyring.delete_password(KEYRING_SERVICE, self._account)
        return True


def _system_keyring() -> KeyringLike:
    import keyring

    # keyring's backends are untyped; the three methods used here are its documented interface.
    return cast(KeyringLike, keyring.get_keyring())


def keyring_is_usable() -> bool:
    """Whether this machine has a keychain `keyring` can store a password in."""
    try:
        import keyring
        from keyring.backends import fail
    except ImportError:  # pragma: no cover - keyring ships with the opencaselist extra
        return False
    backend = keyring.get_keyring()
    return not isinstance(backend, fail.Keyring) and getattr(backend, "priority", 0) > 0


class FileTokenBackend:
    """The token record in a `0600` file inside a `0700` directory."""

    @property
    def name(self) -> str:
        return "file"

    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self) -> str | None:
        try:
            status = self.path.stat()
        except FileNotFoundError:
            return None
        mode = stat.S_IMODE(status.st_mode)
        if mode & 0o077:
            raise InsecureTokenFile(self.path, status.st_mode)
        return self.path.read_text(encoding="utf-8")

    def write(self, value: str) -> None:
        directory = self.path.parent
        directory.mkdir(mode=_DIRECTORY_MODE, parents=True, exist_ok=True)
        os.chmod(directory, _DIRECTORY_MODE)
        # Written to a sibling and renamed, so the token file is never observable half-written or
        # with the process umask's permissions: the descriptor is created 0600 before any byte.
        temporary = directory / f".{self.path.name}.{os.getpid()}.tmp"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, _FILE_MODE)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(value)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, _FILE_MODE)
            os.replace(temporary, self.path)
        except BaseException:
            with contextlib.suppress(FileNotFoundError):
                temporary.unlink()
            raise

    def delete(self) -> bool:
        try:
            self.path.unlink()
        except FileNotFoundError:
            return False
        return True


# ------------------------------------------------------------------------------------------------
# The store
# ------------------------------------------------------------------------------------------------


class CaselistTokenStore:
    """Load, save, stamp and delete the operator's caselist_token in one backend."""

    def __init__(self, backend: TokenBackend, *, clock: Callable[[], datetime] | None = None) -> None:
        self._backend = backend
        self._clock = clock or (lambda: datetime.now(UTC))

    @classmethod
    def for_settings(
        cls,
        choice: CaselistTokenBackend,
        *,
        account: str,
        secret_file: Path,
        keyring: KeyringLike | None = None,
        keyring_usable: Callable[[], bool] = keyring_is_usable,
        clock: Callable[[], datetime] | None = None,
    ) -> CaselistTokenStore:
        """The store `caselist.token_backend` names.

        `auto` falls back to the file only when no keychain is usable.
        """
        if choice is CaselistTokenBackend.FILE:
            return cls(FileTokenBackend(secret_file), clock=clock)
        if keyring is not None or keyring_usable():
            return cls(KeyringTokenBackend(account=account, keyring=keyring), clock=clock)
        if choice is CaselistTokenBackend.KEYRING:
            raise KeyringUnavailable
        return cls(FileTokenBackend(secret_file), clock=clock)

    @property
    def backend_name(self) -> str:
        return self._backend.name

    @property
    def location(self) -> str:
        """Where the token is, for `auth status`: the file's path, or the keychain item's name."""
        if isinstance(self._backend, FileTokenBackend):
            return str(self._backend.path)
        return f"keychain item {KEYRING_SERVICE}"

    def load(self) -> StoredCaselistToken | None:
        """The stored token, or `None` when there is none. Registers it for log redaction."""
        raw = self._backend.read()
        if raw is None:
            return None
        stored = StoredCaselistToken.from_json(raw, backend=self._backend.name)
        register_secret(stored.token.get_secret_value())
        return stored

    def save(self, token: SecretStr, *, expires_at: datetime | None) -> StoredCaselistToken:
        """Keep `token`, replacing any token stored before."""
        register_secret(token.get_secret_value())
        stored = StoredCaselistToken(
            token=token,
            stored_at=self._clock(),
            expires_at=expires_at,
            last_validated_at=self._clock(),
            backend=self._backend.name,
        )
        self._backend.write(stored.to_json())
        return stored

    def record_validation(self) -> None:
        """Stamp the stored token as having just worked. A no-op when none is stored."""
        stored = self.load()
        if stored is not None:
            self._backend.write(replace(stored, last_validated_at=self._clock()).to_json())

    def delete(self) -> bool:
        """Forget the token. True when there was one."""
        return self._backend.delete()
