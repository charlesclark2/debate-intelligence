"""A cloud run refused for an expired login names the Wednesday login, not a login by hand (`v1-e40-t33`).

A run OpenCaselist refused with 401 or 403 records `CASELIST_AUTH_EXPIRED`, and its notice, "caselist
pull stopped: OpenCaselist login expired", gave `debate-research caselist auth login` as its fix in
both modes. In the cloud that is the one thing `caselist-cloud-run.md` forbids: the token is in
Secrets Manager, the Wednesday 03:00 login task renews it, and a login by hand is a second login. In
bucket mode the notice now gives the cloud's cure, in `v1-e40-t22`'s shape: what puts it right, the
runbook section in brackets, and what never to do. On the Mac every word stays.

Each run here is `caselist pull` as the command runs it, as `v1-e34-t35`'s
`test_pull_token_missing_hint_on_the_mac.py` runs it: `run_pull` inside a real run monitor, against
moto, with OpenCaselist refusing the first request, and in bucket mode the bracket stand-in
`v1-e40-t18` wrote. The monitor's notifier is the Mac's recording one and the real
:class:`~debate_core.integrations.sns.SnsNotifier` together, so the email the alert topic sends is
checked as well as the notification; its client records the publish in-process and nothing leaves
the process. Every expected sentence is written out by hand.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

import pytest

from debate_core.application.caselist_sync import CaselistSyncService, run_pull
from debate_core.application.errors import StoreUnavailable
from debate_core.application.ports.caselist_source import CaselistAuthExpired, CaselistTokenMissing
from debate_core.application.ports.notifier import Notification
from debate_core.application.sync_runs import (
    SyncRunDetails,
    SyncRunMonitor,
    SyncRunRecord,
    banner_words,
)
from debate_core.integrations.opencaselist.token_store import CaselistTokenUnreadable
from debate_core.integrations.sns import SnsNotifier

from . import test_inbox_retention as inbox_retention
from .retry_rule import the_commands_retry_rule
from .run_record_scenarios import AWS_LOGIN, World
from .test_caselist_sync_bucket_mode_publish_hints_point_at_the_cloud import (
    REPO_ROOT,
    points_at_the_mac,
    section,
)
from .test_caselist_sync_names_the_cloud_cure_in_bucket_mode import BucketModeBracket
from .test_inbox_retention import CASELIST
from .test_pull_notification_says_retry_or_person import WHERE, the_one_notification, world
from .test_pull_token_missing_hint_on_the_mac import (
    THE_UNFINISHED_RUN_CURE_IN_THE_CLOUD,
    StoppedBy,
    the_details,
    the_record,
    the_service,
)

__all__ = ["world"]

pytestmark = pytest.mark.anyio

TOPIC_ARN: Final = "arn:aws:sns:us-east-1:111122223333:debate-dev-caselist-run-alerts"

# ------------------------------------------------------------------------------------------------
# What each notice says, by hand
# ------------------------------------------------------------------------------------------------

LOGIN_EXPIRED_TITLE: Final = "caselist pull stopped: OpenCaselist login expired"
"""The same in both modes, so `caselist runs` shows the same banner words (none) for it."""

REFUSED: Final = f"{WHERE} was refused by OpenCaselist and fetched nothing more."
"""The same in both modes: only the fix changes."""

THE_LOGIN_ON_THE_MAC: Final = "debate-research caselist auth login"
"""The Mac's fix, as it was before `v1-e40-t33`, word for word."""

THE_WEDNESDAY_LOGIN_IN_THE_CLOUD: Final = (
    "the next Wednesday 03:00 login renews the caselist_token, and the run after it takes up what this "
    "run did not finish, from the run state saved in the bucket; a backfile import refused for it starts "
    'again after Thursday 00:00 (caselist-cloud-run.md, "A run refused for an expired login"); never a '
    "login by hand, which would be a second login"
)
"""The bucket-mode fix (`v1-e40-t33`)."""

THE_EMAIL_FROM_THE_MAC: Final = (
    "caselist pull stopped: OpenCaselist login expired\n"
    "Run 20260916T060000Z (dev)\n"
    "\n"
    "Run 20260916T060000Z (dev) was refused by OpenCaselist and fetched nothing more.\n"
    "\n"
    "Fix: debate-research caselist auth login"
)
"""What the alert topic would send for a run on the Mac, were its notifier `sns`: unchanged."""

THE_EMAIL_FROM_THE_CLOUD: Final = (
    "caselist pull stopped: OpenCaselist login expired\n"
    "Run 20260916T060000Z (dev)\n"
    "\n"
    "Run 20260916T060000Z (dev) was refused by OpenCaselist and fetched nothing more.\n"
    "\n"
    "Fix: the next Wednesday 03:00 login renews the caselist_token, and the run after it takes up what "
    "this run did not finish, from the run state saved in the bucket; a backfile import refused for it "
    'starts again after Thursday 00:00 (caselist-cloud-run.md, "A run refused for an expired login"); '
    "never a login by hand, which would be a second login"
)

THE_SUBJECT: Final = "debate dev: caselist pull stopped: OpenCaselist login expired"

THE_LOGIN: Final = "caselist auth login"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ------------------------------------------------------------------------------------------------
# The run, its notifiers and the email
# ------------------------------------------------------------------------------------------------


class RecordedPublishes:
    """The alert topic's client, answered here: each publish is recorded, and nothing is sent."""

    def __init__(self) -> None:
        self.published: list[dict[str, str]] = []

    def publish(self, *, TopicArn: str, Subject: str, Message: str) -> Mapping[str, Any]:  # noqa: N803 - boto3's names
        self.published.append({"TopicArn": TopicArn, "Subject": Subject, "Message": Message})
        return {"MessageId": "94f20ce6-13c5-43a0-9a9e-ca52d816e90b"}


class ToTheMacAndTheTopic:
    """The Mac's recording notifier and the alert topic's, each told every notification."""

    def __init__(self, world: World, emails: RecordedPublishes) -> None:
        self._world = world
        self._topic = SnsNotifier(TOPIC_ARN, environment="dev", client=emails)

    def notify(self, notification: Notification) -> None:
        self._world.notifier.notify(notification)
        self._topic.notify(notification)


async def pull(world: World, service: CaselistSyncService, *, bucket_mode: bool) -> RecordedPublishes:
    """`caselist pull` as the command runs it, with a bucket-mode bracket when `bucket_mode`; the emails."""
    emails = RecordedPublishes()
    monitor = SyncRunMonitor(
        state_dir=world.installation.data_dir,
        environment="dev",
        notifier=ToTheMacAndTheTopic(world, emails),
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
    return emails


async def refused_for_an_expired_login(world: World, *, bucket_mode: bool) -> RecordedPublishes:
    expired = CaselistAuthExpired(401, f"list archives for {CASELIST}")
    service = the_service(world, StoppedBy(world, expired), bucket_mode=bucket_mode)
    emails = await pull(world, service, bucket_mode=bucket_mode)

    assert [type(one) for one in world.raised] == [CaselistAuthExpired]
    record = the_record(world)
    assert record["outcome"] == "failed"
    assert record["error_class"] == "CaselistAuthExpired"
    details = the_details(world)
    assert details["failure_codes"] == ["CASELIST_AUTH_EXPIRED"]
    assert details.get("hint") is None
    assert (details.get("bucket_run") is not None) is bucket_mode
    return emails


def the_one_email(emails: RecordedPublishes) -> dict[str, str]:
    [email] = emails.published
    assert email["TopicArn"] == TOPIC_ARN
    return email


def the_banner_words(world: World) -> str | None:
    """What `caselist runs` shows beside the run's verdict, decided from the record and details written."""
    return banner_words(
        SyncRunRecord.model_validate(the_record(world)),
        SyncRunDetails.model_validate(the_details(world)),
        **the_commands_retry_rule(),
    )


# ------------------------------------------------------------------------------------------------
# On the Mac: every word as it was
# ------------------------------------------------------------------------------------------------


async def test_a_mac_run_refused_for_auth_expired_keeps_its_notice_word_for_word(world: World) -> None:
    emails = await refused_for_an_expired_login(world, bucket_mode=False)

    notification = the_one_notification(world)
    assert notification.title == LOGIN_EXPIRED_TITLE
    assert notification.subtitle == WHERE
    assert notification.message == REFUSED
    assert notification.hint is None
    assert notification.fix_command == THE_LOGIN_ON_THE_MAC
    assert "Wednesday" not in notification.text

    email = the_one_email(emails)
    assert email["Subject"] == THE_SUBJECT
    assert email["Message"] == THE_EMAIL_FROM_THE_MAC
    assert the_banner_words(world) is None


# ------------------------------------------------------------------------------------------------
# In bucket mode: the Wednesday login, in the notification and the email
# ------------------------------------------------------------------------------------------------


async def test_a_bucket_mode_run_refused_for_auth_expired_names_the_wednesday_login(world: World) -> None:
    await refused_for_an_expired_login(world, bucket_mode=True)

    notification = the_one_notification(world)
    assert notification.title == LOGIN_EXPIRED_TITLE
    assert notification.subtitle == WHERE
    assert notification.message == REFUSED
    assert notification.hint is None
    assert notification.fix_command == THE_WEDNESDAY_LOGIN_IN_THE_CLOUD
    assert THE_LOGIN not in notification.text
    assert "debate-research" not in notification.text
    assert points_at_the_mac(notification.text) == []
    assert the_banner_words(world) is None


async def test_the_alert_email_of_a_bucket_mode_run_refused_for_auth_expired_names_the_wednesday_login(
    world: World,
) -> None:
    """What the coach reads: the subject unchanged, and the cloud's cure on the fix line."""
    emails = await refused_for_an_expired_login(world, bucket_mode=True)

    email = the_one_email(emails)
    assert email["Subject"] == THE_SUBJECT
    assert email["Message"] == THE_EMAIL_FROM_THE_CLOUD
    assert THE_LOGIN not in email["Message"]


# ------------------------------------------------------------------------------------------------
# The Wednesday login is this code's cure alone
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(CaselistTokenMissing(), id="token-missing"),
        pytest.param(CaselistTokenUnreadable("keyring"), id="token-unreadable"),
        pytest.param(StoreUnavailable("list archives", CASELIST, "synthetic 503"), id="store-unavailable"),
    ],
)
async def test_a_bucket_mode_run_stopped_by_another_code_than_auth_expired_names_no_wednesday_login(
    world: World, error: Exception
) -> None:
    """The neighbouring codes keep `v1-e40-t28`'s cure: the next cloud run, and no login named."""
    emails = await pull(
        world, the_service(world, StoppedBy(world, error), bucket_mode=True), bucket_mode=True
    )

    assert [type(one) for one in world.raised] == [type(error)]
    notification = the_one_notification(world)
    assert notification.title != LOGIN_EXPIRED_TITLE
    assert notification.fix_command == THE_UNFINISHED_RUN_CURE_IN_THE_CLOUD
    assert "Wednesday" not in notification.text
    assert "Wednesday" not in the_one_email(emails)["Message"]


# ------------------------------------------------------------------------------------------------
# The runbooks say what the notice says
# ------------------------------------------------------------------------------------------------

ALERTS_RUNBOOK: Final = REPO_ROOT / "docs" / "runbooks" / "caselist-run-alerts.md"


def test_the_runbook_section_the_auth_expired_cure_names_quotes_it_and_keeps_the_rule() -> None:
    refused = section("A run refused for an expired login")
    assert f"> Fix: {THE_WEDNESDAY_LOGIN_IN_THE_CLOUD}" in refused
    assert "Never run `debate-research caselist auth login`" in refused
    assert "a second login" in refused


def test_the_alerts_runbook_says_what_to_do_when_the_auth_expired_email_arrives() -> None:
    text = " ".join(ALERTS_RUNBOOK.read_text(encoding="utf-8").split())
    row = next(line for line in text.split("| `") if line.startswith(f"{LOGIN_EXPIRED_TITLE}`"))
    assert "Wednesday 03:00 login" in row
    assert "A run refused for an expired login" in row
