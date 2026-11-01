"""A run on this Mac stopped for an unreadable caselist_token says to log out and log in again (`v1-e34-t36`).

Until now such a run's banner read "stopped: an error recorded as CASELIST_TOKEN_UNREADABLE", with
`caselist pull` as its fix and no hint. On the Mac the fix is the error's own: `caselist auth logout`,
which deletes the record without reading it, then `caselist auth login`. In the cloud the token is in
Secrets Manager, and the fix is the Wednesday login the renew task makes, so a bucket-mode run's
notice for the code stays as it was, word for word.

Each run here is `caselist pull` as `v1-e34-t35`'s `test_pull_token_missing_hint_on_the_mac.py` runs
it: `run_pull` inside a real run monitor, against moto, with the token read when the first request
needs it, as the client's token source reads it. The keychain answers with an item whose contents are
not a record this program wrote, as an item another program or an older build left there would be.
Every expected sentence is written out by hand.
"""

from __future__ import annotations

from typing import Final

import pytest

from debate_core.application.ports.caselist_source import ArchiveListing, CaselistTokenMissing
from debate_core.integrations.opencaselist.token_store import (
    CaselistTokenStore,
    CaselistTokenUnreadable,
    KeyringTokenBackend,
)

from .run_record_scenarios import World
from .test_inbox_retention import WEEK_1, FakeSource
from .test_pull_notification_says_retry_or_person import (
    PERSON,
    PERSON_TITLE,
    WHERE,
    assert_names_no_path,
    shown,
    the_one_notification,
    world,
)
from .test_pull_token_missing_hint_on_the_mac import (
    LOG_IN_AGAIN,
    THE_PULL,
    THE_UNFINISHED_RUN_CURE_IN_THE_CLOUD,
    ReadsNoToken,
    pull,
    the_details,
    the_record,
    the_service,
)

__all__ = ["world"]

pytestmark = pytest.mark.anyio

LOG_OUT_THEN_LOG_IN: Final = (
    "The caselist_token stored on this machine for the environment cannot be read: log out with "
    "`debate-research caselist auth logout`, then log in again with `debate-research caselist auth login`."
)
"""The hint of a run on this Mac stopped for an unreadable token."""

STOPPED_ON_THE_MAC: Final = (
    f"{WHERE} stopped: the caselist_token stored on this machine could not be read. {PERSON}"
)

STOPPED_IN_THE_CLOUD: Final = (
    f"{WHERE} stopped: an error recorded as CASELIST_TOKEN_UNREADABLE. A person should look: at least "
    "one failure here will be the same on the next scheduled run."
)
"""What a bucket-mode run stopped for an unreadable token said before `v1-e34-t36`, and says still."""

THE_LOGOUT: Final = "`debate-research caselist auth logout`"
THE_LOGIN: Final = "`debate-research caselist auth login`"
THE_WORDS: Final = "the caselist_token stored on this machine could not be read"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class KeychainWithAnUnreadableItem:
    """`keyring`'s macOS backend reading an item that holds something this program never wrote."""

    def get_password(self, service: str, username: str) -> str | None:
        return "not a caselist_token record"

    def set_password(self, service: str, username: str, password: str) -> None:
        raise AssertionError("a run that cannot read the token stores none")

    def delete_password(self, service: str, username: str) -> None:
        raise AssertionError("a run never deletes the token")


class ReadsAnUnreadableToken(FakeSource):
    """OpenCaselist, reached with the token the store loads before the first request.

    The store's record cannot be read, so the first request is never made:
    :class:`CaselistTokenUnreadable`, as the store raises it.
    """

    def __init__(self, world: World) -> None:
        super().__init__(world.installation.archives, weeks=[WEEK_1])
        self.store = CaselistTokenStore(
            KeyringTokenBackend(account="dev", keyring=KeychainWithAnUnreadableItem())
        )

    async def list_archives(self, caselist: str) -> list[ArchiveListing]:
        self.store.load()
        raise AssertionError("an unreadable record is never sent")  # pragma: no cover


# ------------------------------------------------------------------------------------------------
# On this Mac: logout then login, in the record's details, the notification and the banner it shows
# ------------------------------------------------------------------------------------------------


async def test_a_mac_run_stopped_by_token_unreadable_says_to_log_out_and_log_in_again(
    world: World,
) -> None:
    await pull(world, the_service(world, ReadsAnUnreadableToken(world), bucket_mode=False), bucket_mode=False)

    assert [type(one) for one in world.raised] == [CaselistTokenUnreadable]

    record = the_record(world)
    assert record["outcome"] == "failed"
    assert record["error_class"] == "CaselistTokenUnreadable"
    details = the_details(world)
    assert details["failure_codes"] == ["CASELIST_TOKEN_UNREADABLE"]
    assert details["hint"] == LOG_OUT_THEN_LOG_IN
    assert details.get("bucket_run") is None

    notification = the_one_notification(world)
    assert notification.title == PERSON_TITLE
    assert notification.message == STOPPED_ON_THE_MAC
    assert notification.hint == LOG_OUT_THEN_LOG_IN
    assert notification.fix_command == THE_PULL
    assert "CASELIST_TOKEN_UNREADABLE" not in notification.text
    assert_names_no_path(world, notification)

    body, title, _ = shown(notification)
    assert title == PERSON_TITLE
    assert THE_WORDS in body
    assert THE_LOGOUT in body
    assert body.index(THE_LOGOUT) < body.index(THE_LOGIN)


async def test_a_mac_run_stopped_by_token_missing_is_not_told_to_log_out(world: World) -> None:
    """The neighbouring code keeps `v1-e34-t35`'s login: there is nothing stored to log out of."""
    await pull(world, the_service(world, ReadsNoToken(world), bucket_mode=False), bucket_mode=False)

    assert [type(one) for one in world.raised] == [CaselistTokenMissing]
    assert the_details(world)["hint"] == LOG_IN_AGAIN

    notification = the_one_notification(world)
    assert notification.hint == LOG_IN_AGAIN
    assert "auth logout" not in notification.text
    assert THE_WORDS not in notification.text


# ------------------------------------------------------------------------------------------------
# In bucket mode: the notice as it was, word for word
# ------------------------------------------------------------------------------------------------


async def test_a_bucket_mode_run_stopped_by_token_unreadable_is_unchanged(world: World) -> None:
    await pull(world, the_service(world, ReadsAnUnreadableToken(world), bucket_mode=True), bucket_mode=True)

    assert [type(one) for one in world.raised] == [CaselistTokenUnreadable]

    record = the_record(world)
    assert record["outcome"] == "failed"
    assert record["error_class"] == "CaselistTokenUnreadable"
    details = the_details(world)
    assert details["failure_codes"] == ["CASELIST_TOKEN_UNREADABLE"]
    assert details.get("hint") is None
    assert details["bucket_run"] is not None

    notification = the_one_notification(world)
    assert notification.title == PERSON_TITLE
    assert notification.message == STOPPED_IN_THE_CLOUD
    assert notification.hint is None
    assert notification.fix_command == THE_UNFINISHED_RUN_CURE_IN_THE_CLOUD
    assert "auth logout" not in notification.text
    assert "auth login" not in notification.text
    assert THE_WORDS not in notification.text
