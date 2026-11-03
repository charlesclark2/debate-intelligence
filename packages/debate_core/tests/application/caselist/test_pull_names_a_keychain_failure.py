"""A scheduled pull the keychain refuses records the cause's code and says its fix (`v1-e34-t33`, ac3).

The Mac's scheduled pull of 2026-10-21 stopped on a bare `KeyringError`: its record said
`INTERNAL_ERROR`, and its notification "an error nobody modelled, most likely a bug". Each run
here is that run, as the Mac's agent makes it (`run_pull` inside a real run monitor, against moto),
with the token read from the keychain when the first request needs it, as the client's token
source reads it, and the keychain answering as `keyring`'s macOS backend does under launchd.

The record keeps the cause's class, its details the cause's code and hint, and the notification
says what stopped the run in words and carries the hint. None of them, nor the bucket's copies,
holds the keychain's message.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from keyring import errors as keyring_errors

from debate_core.application.ports.caselist_session import (
    KeychainDenied,
    KeychainFailure,
    KeychainInteractionNotAllowed,
    KeychainRefusedProgram,
    NoKeychain,
)
from debate_core.application.ports.caselist_source import ArchiveListing
from debate_core.application.sync_runs import SYNC_RUN_DETAILS_FILENAME
from debate_core.integrations.opencaselist.token_store import CaselistTokenStore, KeyringTokenBackend

from .run_record_scenarios import World
from .test_inbox_retention import WEEK_1, FakeSource
from .test_pull_notification_says_retry_or_person import (
    PERSON,
    PERSON_TITLE,
    WHERE,
    assert_names_no_path,
    the_one_notification,
    world,
)

__all__ = ["world"]

pytestmark = pytest.mark.anyio

KEYCHAIN_MESSAGE = "Unknown Error: /Users/stand-in-keychain-owner/Library/Keychains/login.keychain-db"
"""What the keychain's error says, with a path in it, which nothing the run writes may hold."""


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class SecurityError(Exception):
    """`keyring.backends.macOS.api.Error`: `(status, text)`."""


class KeychainAnswering:
    """`keyring`'s macOS backend reading an item the keychain answers `os_status` for.

    keyring 25.7.0, keyring/backends/macOS/__init__.py lines 64-67: -128 is raised as
    `KeyringLocked`, any other status as a bare `KeyringError`, each from the framework's error.
    """

    def __init__(self, os_status: int) -> None:
        self.os_status = os_status

    def get_password(self, service: str, username: str) -> str | None:
        refusal = SecurityError(self.os_status, KEYCHAIN_MESSAGE)
        kind = keyring_errors.KeyringLocked if self.os_status == -128 else keyring_errors.KeyringError
        raise kind(f"Can't get password from keychain: {refusal}") from refusal

    def set_password(self, service: str, username: str, password: str) -> None:
        raise AssertionError("a run that cannot read the token stores none")

    def delete_password(self, service: str, username: str) -> None:
        raise AssertionError("a run never deletes the token")


class ReadsTheToken(FakeSource):
    """OpenCaselist, reached with the token the store loads before the first request."""

    def __init__(self, archives: dict[date, Path], store: CaselistTokenStore) -> None:
        super().__init__(archives, weeks=[WEEK_1])
        self.store = store

    async def list_archives(self, caselist: str) -> list[ArchiveListing]:
        self.store.load()
        return await super().list_archives(caselist)


@pytest.mark.parametrize(
    ("os_status", "named", "code", "stopped_on"),
    [
        pytest.param(
            -25308,
            KeychainInteractionNotAllowed,
            "KEYCHAIN_INTERACTION_NOT_ALLOWED",
            "the keychain needed a person, and a run in the background cannot ask",
            id="under-launchd",
        ),
        pytest.param(
            -25307,
            NoKeychain,
            "NO_KEYCHAIN",
            "no keychain was open: nobody was logged in to the Mac",
            id="nobody-logged-in",
        ),
        pytest.param(
            -128,
            KeychainDenied,
            "KEYCHAIN_DENIED",
            "the keychain was asked for the caselist_token and said no",
            id="denied",
        ),
        pytest.param(
            -25293,
            KeychainRefusedProgram,
            "KEYCHAIN_REFUSED_PROGRAM",
            "the keychain refused this program",
            id="refused-program",
        ),
    ],
)
async def test_a_run_the_keychain_refuses_records_the_code_and_its_notice_gives_the_hint(
    world: World, os_status: int, named: type[KeychainFailure], code: str, stopped_on: str
) -> None:
    store = CaselistTokenStore(KeyringTokenBackend(account="dev", keyring=KeychainAnswering(os_status)))

    await world.pull(world.installation.sync(ReadsTheToken(world.installation.archives, store)))

    assert [type(one) for one in world.raised] == [named]

    [record] = [json.loads(line) for line in world.run_log().decode("utf-8").splitlines()]
    assert record["outcome"] == "failed"
    assert record["error_class"] == named.__name__
    data_dir = world.installation.data_dir
    [details] = [
        json.loads(line)
        for line in (data_dir / SYNC_RUN_DETAILS_FILENAME).read_text(encoding="utf-8").splitlines()
    ]
    assert details["failure_codes"] == [code]
    assert details["hint"] == named.HINT

    notification = the_one_notification(world)
    assert notification.title == PERSON_TITLE
    assert notification.message == f"{WHERE} stopped: {stopped_on}. {PERSON}"
    assert notification.hint == named.HINT
    assert "bug" not in notification.text
    assert_names_no_path(world, notification)

    written = [
        world.run_log().decode("utf-8"),
        (data_dir / SYNC_RUN_DETAILS_FILENAME).read_text(encoding="utf-8"),
        *world.records_in_the_bucket().values(),
        notification.text,
    ]
    for text in written:
        assert "stand-in-keychain-owner" not in text
        assert "Unknown Error" not in text
