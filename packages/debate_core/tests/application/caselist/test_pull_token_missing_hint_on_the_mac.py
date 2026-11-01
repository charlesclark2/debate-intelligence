"""A run on this Mac stopped for a missing caselist_token says to log in again (`v1-e34-t35`).

Until now such a run's banner read "stopped: an error recorded as CASELIST_TOKEN_MISSING", with
`caselist pull` as its fix and no hint. On the Mac the fix is `caselist auth login`, as `v1-e34-t33`
says for a keychain that refused the token. In the cloud the token is in Secrets Manager, and the fix
is the Wednesday login the renew task makes, so a bucket-mode run's notice for the code stays as it
was, word for word.

Each run here is `caselist pull` as the command runs it: `run_pull` inside a real run monitor, against
moto, with the token read when the first request needs it, as the client's token source reads it, and
the keychain answering as `keyring`'s macOS backend does for an item that is not there (`None`). Bucket
mode is told as every banner tells it, from the details' `bucket_run`, which the bracket around a
bucket-mode pull writes; here that bracket is the stand-in `v1-e40-t18` wrote. Every expected sentence
is written out by hand.
"""

from __future__ import annotations

import json
from typing import Any, Final

import pytest

from debate_core.application.caselist_sync import CaselistSyncService, run_pull
from debate_core.application.ports.caselist_source import (
    ArchiveListing,
    CaselistAuthExpired,
    CaselistTokenMissing,
)
from debate_core.application.sync_runs import SYNC_RUN_DETAILS_FILENAME, SyncRunMonitor
from debate_core.integrations.opencaselist.token_store import (
    CaselistTokenStore,
    CaselistTokenUnreadable,
    KeyringTokenBackend,
)

from . import test_inbox_retention as inbox_retention
from .retry_rule import the_commands_retry_rule
from .run_record_scenarios import AWS_LOGIN, World
from .test_caselist_sync_names_the_cloud_cure_in_bucket_mode import BucketModeBracket
from .test_inbox_retention import CASELIST, WEEK_1, FakeSource
from .test_pull_notification_says_retry_or_person import (
    PERSON,
    PERSON_TITLE,
    WHERE,
    assert_names_no_path,
    shown,
    the_one_notification,
    world,
)

__all__ = ["world"]

pytestmark = pytest.mark.anyio

LOG_IN_AGAIN: Final = (
    "No caselist_token is stored on this machine for the environment: log in again with "
    "`debate-research caselist auth login`."
)
"""The hint of a run on this Mac stopped for a missing token."""

STOPPED_ON_THE_MAC: Final = f"{WHERE} stopped: no caselist_token was stored on this machine. {PERSON}"

STOPPED_IN_THE_CLOUD: Final = (
    f"{WHERE} stopped: an error recorded as CASELIST_TOKEN_MISSING. A person should look: at least one "
    "failure here will be the same on the next scheduled run."
)
"""What a bucket-mode run stopped for a missing token said before `v1-e34-t35`, and says still."""

THE_UNFINISHED_RUN_CURE_IN_THE_CLOUD: Final = (
    "the next cloud run takes up what this run did not finish, from the run state saved in the bucket: "
    'the weekly run, or one started by hand (caselist-cloud-run.md, "A failed or stopped run"); never a '
    "publish from the operator's Mac"
)
"""A bucket-mode stopped run's fix, as before `v1-e34-t35` (`v1-e40-t28`)."""

THE_PULL: Final = "debate-research caselist pull"
THE_LOGIN: Final = "caselist auth login"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class KeychainWithNoItem:
    """`keyring`'s macOS backend reading an item that is not there: `None` (keyring 25.7.0, -25300)."""

    def get_password(self, service: str, username: str) -> str | None:
        return None

    def set_password(self, service: str, username: str, password: str) -> None:
        raise AssertionError("a run that has no token stores none")

    def delete_password(self, service: str, username: str) -> None:
        raise AssertionError("a run never deletes the token")


class ReadsNoToken(FakeSource):
    """OpenCaselist, reached with the token the store loads before the first request.

    The store has none, so the first request is never made: :class:`CaselistTokenMissing`, as the
    client's token source raises it.
    """

    def __init__(self, world: World) -> None:
        super().__init__(world.installation.archives, weeks=[WEEK_1])
        self.store = CaselistTokenStore(KeyringTokenBackend(account="dev", keyring=KeychainWithNoItem()))

    async def list_archives(self, caselist: str) -> list[ArchiveListing]:
        if self.store.load() is None:
            raise CaselistTokenMissing
        return await super().list_archives(caselist)  # pragma: no cover - the store is empty


class StoppedBy(FakeSource):
    """OpenCaselist, reached with a token the run could not use: the first request raises `error`."""

    def __init__(self, world: World, error: Exception) -> None:
        super().__init__(world.installation.archives, weeks=[WEEK_1])
        self.error = error

    async def list_archives(self, caselist: str) -> list[ArchiveListing]:
        raise self.error


async def pull(world: World, service: CaselistSyncService, *, bucket_mode: bool) -> None:
    """`caselist pull` as the command runs it, with a bucket-mode bracket when `bucket_mode`.

    :meth:`World.pull`, with the bracket the composition root puts around a bucket-mode pull.
    """
    monitor = SyncRunMonitor(
        state_dir=world.installation.data_dir,
        environment="dev",
        notifier=world.notifier,
        remote=world.installation.bucket,
        aws_login_command=AWS_LOGIN,
        clock=lambda: inbox_retention.RUN_CLOCK,
        **the_commands_retry_rule(),
    )
    try:
        world.pulled.append(
            await run_pull(
                lambda: service,
                [CASELIST],
                dry_run=False,
                publish_pending=False,
                monitor=lambda: monitor,
                progress=lambda _: None,
                bracket=BucketModeBracket() if bucket_mode else None,
            )
        )
    except Exception as stopped:
        world.raised.append(stopped)


def the_service(world: World, source: FakeSource, *, bucket_mode: bool) -> CaselistSyncService:
    return world.installation.sync(
        source, working_copy_outlives_the_run=not bucket_mode, bucket_mode=bucket_mode
    )


def the_record(world: World) -> dict[str, Any]:
    [record] = [json.loads(line) for line in world.run_log().decode("utf-8").splitlines()]
    return record


def the_details(world: World) -> dict[str, Any]:
    path = world.installation.data_dir / SYNC_RUN_DETAILS_FILENAME
    [details] = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return details


# ------------------------------------------------------------------------------------------------
# On this Mac: the login, in the record's details, the notification and the banner it shows
# ------------------------------------------------------------------------------------------------


async def test_a_mac_run_stopped_by_token_missing_says_to_log_in_again(world: World) -> None:
    await pull(world, the_service(world, ReadsNoToken(world), bucket_mode=False), bucket_mode=False)

    assert [type(one) for one in world.raised] == [CaselistTokenMissing]

    record = the_record(world)
    assert record["outcome"] == "failed"
    assert record["error_class"] == "CaselistTokenMissing"
    details = the_details(world)
    assert details["failure_codes"] == ["CASELIST_TOKEN_MISSING"]
    assert details["hint"] == LOG_IN_AGAIN
    assert details.get("bucket_run") is None

    notification = the_one_notification(world)
    assert notification.title == PERSON_TITLE
    assert notification.message == STOPPED_ON_THE_MAC
    assert notification.hint == LOG_IN_AGAIN
    assert notification.fix_command == THE_PULL
    assert "CASELIST_TOKEN_MISSING" not in notification.text
    assert_names_no_path(world, notification)

    body, title, _ = shown(notification)
    assert title == PERSON_TITLE
    assert f"`debate-research {THE_LOGIN}`" in body
    assert "no caselist_token was stored on this machine" in body


@pytest.mark.parametrize(
    ("error", "code", "stopped_on"),
    [
        pytest.param(
            CaselistTokenUnreadable("keyring"),
            "CASELIST_TOKEN_UNREADABLE",
            "an error recorded as CASELIST_TOKEN_UNREADABLE",
            id="token-unreadable",
        ),
        pytest.param(
            CaselistAuthExpired(401, f"list archives for {CASELIST}"),
            "CASELIST_AUTH_EXPIRED",
            None,
            id="auth-expired",
        ),
    ],
)
async def test_token_missing_hint_and_words_are_given_to_no_other_code_on_the_mac(
    world: World, error: Exception, code: str, stopped_on: str | None
) -> None:
    """The two codes nearest a missing token keep what they had: no hint, and their own notice."""
    await pull(world, the_service(world, StoppedBy(world, error), bucket_mode=False), bucket_mode=False)

    assert [type(one) for one in world.raised] == [type(error)]
    details = the_details(world)
    assert details["failure_codes"] == [code]
    assert details.get("hint") is None

    notification = the_one_notification(world)
    assert notification.hint is None
    assert "no caselist_token was stored" not in notification.text
    if stopped_on is not None:
        assert notification.message == f"{WHERE} stopped: {stopped_on}. {PERSON}"


# ------------------------------------------------------------------------------------------------
# In bucket mode: the notice as it was, word for word
# ------------------------------------------------------------------------------------------------


async def test_a_bucket_mode_run_stopped_by_token_missing_is_unchanged(world: World) -> None:
    await pull(world, the_service(world, ReadsNoToken(world), bucket_mode=True), bucket_mode=True)

    assert [type(one) for one in world.raised] == [CaselistTokenMissing]

    record = the_record(world)
    assert record["outcome"] == "failed"
    assert record["error_class"] == "CaselistTokenMissing"
    details = the_details(world)
    assert details["failure_codes"] == ["CASELIST_TOKEN_MISSING"]
    assert details.get("hint") is None
    assert details["bucket_run"] is not None

    notification = the_one_notification(world)
    assert notification.title == PERSON_TITLE
    assert notification.message == STOPPED_IN_THE_CLOUD
    assert notification.hint is None
    assert notification.fix_command == THE_UNFINISHED_RUN_CURE_IN_THE_CLOUD
    assert THE_LOGIN not in notification.text
    assert "no caselist_token was stored" not in notification.text
