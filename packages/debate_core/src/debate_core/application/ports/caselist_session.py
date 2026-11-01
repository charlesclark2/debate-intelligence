"""The operator's OpenCaselist session: logging in, and the caselist_token kept afterwards.

`debate-research caselist auth` (`v1-e34-t01`) logs in, reports what is stored and checks that it
still works. It gets the client and the token store from the composition root and types against
these Protocols, so the command names no adapter (`v1-e01-t13-composition-root-cleanup`). The one
implementation of each is in :mod:`debate_core.integrations.opencaselist`:
`OpenCaselistClient` is a :class:`CaselistLoginSession`, and what its `CaselistTokenStore` loads
and saves is a :class:`StoredToken`.

Nothing here exposes the token beyond the :class:`~pydantic.SecretStr` it already is.

## When the keychain refuses (`v1-e34-t33`)

The token store's keychain backend translates what `keyring` raises into the
:class:`KeychainFailure` a person can act on, each with its own error code and
:attr:`~KeychainFailure.hint`, by the macOS OSStatus the keychain answered:

* `KEYCHAIN_INTERACTION_NOT_ALLOWED` (-25308): the keychain needed a person, to be unlocked or to
  allow this program, and the process has no screen to ask on: a run under launchd.
* `NO_KEYCHAIN` (-25291, -25294, -25307): no keychain was open, because nobody is logged in.
* `KEYCHAIN_DENIED` (-128): the keychain asked to be unlocked, or whether this program may use the
  item, and was told no.
* `KEYCHAIN_REFUSED_PROGRAM` (-25293, -67030): the keychain could not confirm this program, or its
  own password, as allowed to use the item.

The classes live here, beside the port the token store serves, so that a run's notification can
carry their hint (:func:`~debate_core.application.caselist_sync.fix_for`) without the application
layer importing the adapter. None of them quotes the library's message: it is told apart by the
OSStatus, which `docs/runbooks/caselist-scheduled-sync.md` lists with each fix.
"""

from __future__ import annotations

from datetime import datetime
from types import TracebackType
from typing import ClassVar, Final, Literal, Protocol, Self

from pydantic import SecretStr

from debate_core.application.errors import DomainError
from debate_core.application.ports.caselist_source import CaselistInfo

__all__ = [
    "CaselistLoginSession",
    "IssuedToken",
    "KeychainDenied",
    "KeychainFailure",
    "KeychainInteractionNotAllowed",
    "KeychainOperation",
    "KeychainRefusedProgram",
    "NoKeychain",
    "StoredToken",
]

type KeychainOperation = Literal["read", "store", "delete"]
"""Which of the token store's three keychain calls was refused."""

_FILE_BACKEND: Final = (
    'or set caselist.token_backend = "file" and log in again with '
    "`debate-research caselist auth login`, which keeps the token in a 0600 file instead"
)


class KeychainFailure(DomainError):
    """The OS keychain refused the token store, for a reason a person can put right.

    Never raised itself: each subclass is one cause, with its own error code. `os_status` is the
    macOS OSStatus the cause was told apart by; the library's message is never kept.
    """

    HINT: ClassVar[str]
    """What to do about it: :attr:`hint`, on every instance."""

    def __init__(self, operation: KeychainOperation, os_status: int, cause: str) -> None:
        self.operation: KeychainOperation = operation
        """The call that was refused: `read`, `store` or `delete` the caselist_token."""
        self.os_status = os_status
        """The OSStatus the keychain answered with, e.g. -25308."""
        self.hint = self.HINT
        """One line on what to do about it."""
        super().__init__(
            f"the keychain did not let this program {operation} the caselist_token "
            f"(OSStatus {os_status}): {cause}"
        )


class KeychainInteractionNotAllowed(KeychainFailure):
    """OSStatus -25308: the keychain needed a person, and the process cannot show a prompt."""

    HINT: ClassVar[str] = (
        "The Mac must be logged in, not only switched on, with its login keychain unlocked. If it "
        "is, run `debate-research caselist auth status` once in Terminal and choose Always Allow "
        "if the keychain asks."
    )

    def __init__(self, operation: KeychainOperation, os_status: int) -> None:
        super().__init__(
            operation,
            os_status,
            "the keychain is locked, or has not yet been told this program may use the item, and "
            "a process with no screen, like the scheduled run, cannot ask",
        )


class NoKeychain(KeychainFailure):
    """OSStatus -25291, -25294 or -25307: no keychain is open for this user."""

    HINT: ClassVar[str] = (
        "The Mac must be logged in, not only switched on: the login keychain opens when its user "
        "logs in. Then run `debate-research caselist auth status` to check the token is there."
    )

    def __init__(self, operation: KeychainOperation, os_status: int) -> None:
        super().__init__(operation, os_status, "no keychain is open for this user")


class KeychainDenied(KeychainFailure):
    """OSStatus -128: asked to unlock, or to allow this program, and told no.

    A keychain left locked and a program refused at the prompt answer the same OSStatus, so they
    share this code, and its hint covers both.
    """

    HINT: ClassVar[str] = (
        "The keychain denied this program: run `debate-research caselist auth status` in "
        "Terminal, unlock the keychain and choose Always Allow when it asks; "
        f"{_FILE_BACKEND}."
    )

    def __init__(self, operation: KeychainOperation, os_status: int) -> None:
        super().__init__(
            operation,
            os_status,
            "it asked to be unlocked, or whether this program may use the item, and was told no",
        )


class KeychainRefusedProgram(KeychainFailure):
    """OSStatus -25293 or -67030: the keychain could not confirm the program, or its own password."""

    HINT: ClassVar[str] = (
        "The keychain refused this program: in Keychain Access, open the item "
        "debate-research.opencaselist and allow this build under Access Control, or delete the "
        "item and log in again with `debate-research caselist auth login`; "
        f"{_FILE_BACKEND}."
    )

    def __init__(self, operation: KeychainOperation, os_status: int) -> None:
        super().__init__(
            operation,
            os_status,
            "it could not confirm this program, or the keychain's own password, as allowed to use the item",
        )


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
