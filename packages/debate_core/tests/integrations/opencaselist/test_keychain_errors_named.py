"""A keychain that refuses the token store says why, by code and hint, never by message (`v1-e34-t33`).

The Mac's scheduled pull of 2026-10-21 stopped on a bare `KeyringError`, reported as
`INTERNAL_ERROR`, "a bug in debate-research". `keyring`'s macOS backend raises that one class for
most of what the keychain answers, and its message, which can quote a path, is rightly never
printed. What it does keep is the keychain's OSStatus, on the error it chains as `__cause__`, and
the token store now reads that:

* **ac2.** A locked keychain under launchd (-25308), no keychain open (-25291, -25294, -25307), a
  prompt answered no (-128) and a refused program (-25293, -67030) each give their own error code
  and hint, for each of the store's three calls, and quote no message. A missing item reads as no
  token, as it did, and deleting a token that is already gone succeeds quietly, even when it goes
  between the store's read and its delete. Anything else is raised as `keyring` raised it, which
  the CLI and a run report as `INTERNAL_ERROR`.

Every keychain here is `keyring`'s own macOS backend over :mod:`.stand_in_keychain`, so the
translation `keyring` makes, which class for which call, is the real one.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from keyring import errors as keyring_errors
from keyring.backends import fail
from pydantic import SecretStr

from debate_core.application.caselist_sync import fix_for
from debate_core.application.errors import error_code_of, reported_error_code
from debate_core.application.ports.caselist_session import (
    KeychainDenied,
    KeychainFailure,
    KeychainInteractionNotAllowed,
    KeychainOperation,
    KeychainRefusedProgram,
    NoKeychain,
)
from debate_core.integrations.opencaselist.token_store import (
    KEYRING_SERVICE,
    CaselistTokenStore,
    KeyringTokenBackend,
    KeyringUnavailable,
)

from .stand_in_keychain import (
    ITEM_NOT_FOUND,
    KEYCHAIN_MESSAGE_SENTINEL,
    SecurityCall,
    StandInSecurity,
    macos_keyring_over,
)

NOW = datetime(2026, 10, 21, 6, 0, tzinfo=UTC)
ACCOUNT = "dev"

LOG_IN_AGAIN = "`debate-research caselist auth login`"
THE_MAC_MUST_BE_LOGGED_IN = "The Mac must be logged in, not only switched on"
THE_FILE_BACKEND = 'caselist.token_backend = "file"'


@pytest.fixture
def security() -> StandInSecurity:
    return StandInSecurity()


@pytest.fixture
def store(security: StandInSecurity, monkeypatch: pytest.MonkeyPatch) -> CaselistTokenStore:
    keychain = macos_keyring_over(security, monkeypatch)
    return CaselistTokenStore(KeyringTokenBackend(account=ACCOUNT, keyring=keychain), clock=lambda: NOW)


def a_stored_token(security: StandInSecurity, store: CaselistTokenStore) -> None:
    store.save(SecretStr("fixture-token-for-the-keychain"), expires_at=None)
    security.calls.clear()


def the_call(store: CaselistTokenStore, operation: KeychainOperation) -> None:
    """The token store's `operation`, the way `caselist auth` and the pull make it."""
    if operation == "read":
        store.load()
    elif operation == "store":
        store.save(SecretStr("fixture-token-stored-again"), expires_at=None)
    else:
        store.delete()


THE_CALL_THAT_ANSWERS: dict[KeychainOperation, SecurityCall] = {
    "read": "find",
    "store": "add",
    "delete": "delete",
}
"""Which Security call a scripted OSStatus is put on, for each of the store's operations."""


def assert_quotes_nothing(error: BaseException) -> None:
    """No message of `keyring`'s or the framework's, and no path, anywhere a report could read."""
    for said in (str(error), repr(error), *(repr(value) for value in vars(error).values())):
        assert KEYCHAIN_MESSAGE_SENTINEL not in said, said
        assert "/Users/" not in said, said
    assert error.__cause__ is None
    assert error.__suppress_context__, "the library's error is not printed beneath it"


# ------------------------------------------------------------------------------------------------
# ac2: each cause its own code and hint
# ------------------------------------------------------------------------------------------------

NAMED_CAUSES = [
    pytest.param(
        -25308,
        KeychainInteractionNotAllowed,
        "KEYCHAIN_INTERACTION_NOT_ALLOWED",
        id="interaction-not-allowed",
    ),
    pytest.param(-25291, NoKeychain, "NO_KEYCHAIN", id="no-keychain-available"),
    pytest.param(-25294, NoKeychain, "NO_KEYCHAIN", id="no-such-keychain"),
    pytest.param(-25307, NoKeychain, "NO_KEYCHAIN", id="no-default-keychain"),
    pytest.param(-128, KeychainDenied, "KEYCHAIN_DENIED", id="denied-at-the-prompt"),
    pytest.param(-25293, KeychainRefusedProgram, "KEYCHAIN_REFUSED_PROGRAM", id="auth-failed"),
    pytest.param(-67030, KeychainRefusedProgram, "KEYCHAIN_REFUSED_PROGRAM", id="code-signature"),
]

OPERATIONS: list[KeychainOperation] = ["read", "store", "delete"]


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize(("os_status", "named", "code"), NAMED_CAUSES)
def test_each_cause_has_its_own_code_and_hint_and_quotes_no_message(
    security: StandInSecurity,
    store: CaselistTokenStore,
    operation: KeychainOperation,
    os_status: int,
    named: type[KeychainFailure],
    code: str,
) -> None:
    a_stored_token(security, store)
    security.answer(THE_CALL_THAT_ANSWERS[operation], os_status)

    with pytest.raises(KeychainFailure) as raised:
        the_call(store, operation)

    error = raised.value
    assert type(error) is named
    assert (error_code_of(error), reported_error_code(error)) == (code, code)
    assert (error.operation, error.os_status) == (operation, os_status)
    assert error.hint == named.HINT
    assert fix_for(error) == named.HINT, "a run's notification carries the same hint"
    assert_quotes_nothing(error)


def test_the_hints_say_what_the_spec_asks_of_each() -> None:
    """Written out by hand: a background run needs a logged-in Mac; a refusal names the file backend."""
    assert KeychainInteractionNotAllowed.HINT.startswith(THE_MAC_MUST_BE_LOGGED_IN)
    assert NoKeychain.HINT.startswith(THE_MAC_MUST_BE_LOGGED_IN)
    assert KeychainDenied.HINT.startswith("The keychain denied this program")
    assert KeychainRefusedProgram.HINT.startswith("The keychain refused this program")
    for refusal in (KeychainDenied, KeychainRefusedProgram):
        assert THE_FILE_BACKEND in refusal.HINT and LOG_IN_AGAIN in refusal.HINT
    codes = {error_code_of(kind(operation="read", os_status=0)) for kind in KeychainFailure.__subclasses__()}
    hints = {kind.HINT for kind in KeychainFailure.__subclasses__()}
    assert len(codes) == len(hints) == 4, "four causes, four codes, four hints"


# ------------------------------------------------------------------------------------------------
# ac2: a missing item
# ------------------------------------------------------------------------------------------------


def test_a_missing_item_reads_as_no_token(security: StandInSecurity, store: CaselistTokenStore) -> None:
    assert store.load() is None
    assert security.calls == ["find"]


def test_deleting_a_token_that_was_never_stored_succeeds_quietly(
    security: StandInSecurity, store: CaselistTokenStore
) -> None:
    assert store.delete() is False


def test_deleting_a_token_gone_between_the_read_and_the_delete_succeeds_quietly(
    security: StandInSecurity, store: CaselistTokenStore
) -> None:
    """Another process (`caselist auth logout` in Terminal, under the agent) took it first."""
    a_stored_token(security, store)
    security.answer("delete", ITEM_NOT_FOUND)

    assert store.delete() is False
    assert security.calls == ["find", "delete"]


def test_deleting_a_stored_token_deletes_it(security: StandInSecurity, store: CaselistTokenStore) -> None:
    a_stored_token(security, store)

    assert store.delete() is True
    assert security.items == {}
    assert store.delete() is False, "and a second delete has nothing to do"


# ------------------------------------------------------------------------------------------------
# ac2: anything else is raised as keyring raised it
# ------------------------------------------------------------------------------------------------

UNEXPECTED_STATUSES = [
    pytest.param(-25295, id="invalid-keychain"),
    pytest.param(-25292, id="read-only"),
    pytest.param(-61, id="write-permission"),
    pytest.param(-50, id="bad-parameter"),
]


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("os_status", UNEXPECTED_STATUSES)
def test_an_unexpected_os_status_is_still_an_internal_error(
    security: StandInSecurity, store: CaselistTokenStore, operation: KeychainOperation, os_status: int
) -> None:
    a_stored_token(security, store)
    security.answer(THE_CALL_THAT_ANSWERS[operation], os_status)

    with pytest.raises(keyring_errors.KeyringError) as raised:
        the_call(store, operation)

    assert not isinstance(raised.value, KeychainFailure)
    assert reported_error_code(raised.value) == "INTERNAL_ERROR"
    assert fix_for(raised.value) is None


class RaisesWithoutAStatus:
    """A keychain whose errors carry no OSStatus: `keyring`'s other backends, or one of ours."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def get_password(self, service: str, username: str) -> str | None:
        raise self.error

    def set_password(self, service: str, username: str, password: str) -> None:
        raise self.error

    def delete_password(self, service: str, username: str) -> None:
        raise self.error


def an_error_caused_by(cause: BaseException) -> keyring_errors.KeyringError:
    try:
        raise keyring_errors.KeyringError(f"Can't get password from keychain: {cause}") from cause
    except keyring_errors.KeyringError as raised:
        return raised


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(keyring_errors.KeyringError("no status at all"), id="keyring-error-with-no-cause"),
        pytest.param(
            keyring_errors.KeyringLocked("Failed to unlock the collection!"), id="locked-with-no-status"
        ),
        pytest.param(an_error_caused_by(OSError(13, "Permission denied")), id="caused-by-an-os-error"),
        pytest.param(an_error_caused_by(ValueError("-25308")), id="a-status-only-in-a-message"),
        pytest.param(RuntimeError("not keyring's"), id="not-a-keyring-error"),
    ],
)
@pytest.mark.parametrize("operation", OPERATIONS)
def test_an_error_with_no_os_status_is_raised_as_it_came(
    operation: KeychainOperation, error: Exception
) -> None:
    keychain = RaisesWithoutAStatus(error)
    backend = KeyringTokenBackend(account=ACCOUNT, keyring=keychain)
    call = {"read": backend.read, "store": lambda: backend.write("{}"), "delete": backend.delete}[operation]

    with pytest.raises(type(error)) as raised:
        call()

    assert raised.value is error
    assert reported_error_code(raised.value) == "INTERNAL_ERROR"


@pytest.mark.parametrize("operation", OPERATIONS)
def test_keyring_with_no_backend_at_all_is_keyring_unavailable(operation: KeychainOperation) -> None:
    """`keyring`'s `fail` backend, which raises `NoKeyringError` on every call: the store's own
    refusal for a machine with no usable keychain, whose message names the file backend."""
    store = CaselistTokenStore(
        KeyringTokenBackend(account=ACCOUNT, keyring=fail.Keyring()), clock=lambda: NOW
    )

    with pytest.raises(KeyringUnavailable) as raised:
        the_call(store, operation)

    assert reported_error_code(raised.value) == "KEYRING_UNAVAILABLE"
    assert "DEBATE_CASELIST__TOKEN_BACKEND=file" in str(raised.value)


def test_the_stand_in_is_the_keychain_that_was_called(
    security: StandInSecurity, store: CaselistTokenStore
) -> None:
    """The guard on every test above: the store's calls reached the stand-in, under the service the
    real keychain item has."""
    a_stored_token(security, store)

    assert store.load() is not None
    assert security.calls == ["find"]
    assert list(security.items) == [(KEYRING_SERVICE, ACCOUNT)]
