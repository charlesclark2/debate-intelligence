"""The operator's OpenCaselist session: logging in, and the caselist_token kept afterwards.

`debate-research caselist auth` (`v1-e34-t01`) logs in, reports what is stored and checks that it
still works. It gets the client and the token store from the composition root and types against
these Protocols, so the command names no adapter (`v1-e01-t13-composition-root-cleanup`). The one
implementation of each is in :mod:`debate_core.integrations.opencaselist`:
`OpenCaselistClient` is a :class:`CaselistLoginSession`, and what its `CaselistTokenStore` loads
and saves is a :class:`StoredToken`.

Nothing here exposes the token beyond the :class:`~pydantic.SecretStr` it already is.
"""

from __future__ import annotations

from datetime import datetime
from types import TracebackType
from typing import Protocol, Self

from pydantic import SecretStr

from debate_core.application.ports.caselist_source import CaselistInfo

__all__ = ["CaselistLoginSession", "IssuedToken", "StoredToken"]


class IssuedToken(Protocol):
    """What a successful login yields: the token, and the expiry the API stated for it."""

    @property
    def token(self) -> SecretStr: ...

    @property
    def expires_at(self) -> datetime | None: ...


class StoredToken(Protocol):
    """A caselist_token as the token store holds it, and what is known about it."""

    @property
    def stored_at(self) -> datetime: ...

    @property
    def expires_at(self) -> datetime | None: ...

    @property
    def last_validated_at(self) -> datetime | None: ...

    @property
    def backend(self) -> str:
        """`keyring`, `file` or `settings`."""
        ...

    def expired(self, now: datetime) -> bool:
        """Whether the API's stated expiry has passed. A token with no stated expiry never has."""
        ...


class CaselistLoginSession(Protocol):
    """An OpenCaselist client used for one login or one check, as an async context manager."""

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def login(self, username: str, password: SecretStr) -> IssuedToken:
        """Trade Tabroom credentials for a token. Stores nothing."""
        ...

    async def list_caselists(self, *, archived: bool | None = None) -> list[CaselistInfo]:
        """Every caselist the API lists; `auth status --check` makes this one request."""
        ...
