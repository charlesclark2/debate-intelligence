"""The environment's alert topic, as a :class:`~debate_core.application.ports.notifier.Notifier`.

ADR-0020 (6), `v1-e40-t05`. The account has no general mail path, so each environment has one SNS
topic, `debate-<env>-caselist-run-alerts`, whose one subscription is the coach's email address.
`caselist.notifier = sns` sends there what the Mac's banners say: the cloud run's failed stage with
its codes and hint, an expired token, a growing backlog, a lost or taken-over lock; and the cloud
login's failure, never naming the account. :class:`SnsNotifier` is that kind's adapter, built under
the rules of t02's Secrets Manager client beside it (PM ruling 2026-10-24): one small boto3 client,
no endpoint override, nothing about the message in a log.

## What a message may say

What the caller gives it, and the caller builds it from run ids, stage names, codes and this
project's own sentences (:mod:`debate_core.application.ports.notifier`). This adapter adds the
environment, and lays the notification out as an email: the subject is `debate <env>: <title>`, the
body the title, the subtitle (the run and its environment), the message and its hint, and the fix
on a line of its own. SNS takes a subject of ASCII on one line under 100 characters and refuses any
other, and a refused publish is an alert nobody gets, so the subject is cut down to one; the whole
title is the body's first line.

## Nothing here reaches a log

botocore writes each request's parameters to `botocore.endpoint` at DEBUG, which is the message
whole. Every publish runs under
:func:`~debate_core.integrations.secrets_manager.quiet_wire_log`, the same guard the secrets'
client uses, which drops that logger's and `botocore.parsers`' records on the calling thread for
the length of the call. A failed publish is logged by the operation and SNS's code, or the
exception's class, and never by botocore's message.

## Best effort, and quick

A notifier never fails the run it reports on: every failure to deliver is logged and swallowed,
the client's own construction included. And it gives up in time. A run told to stop
(`RUN_TERMINATED`) writes its record, notifies and releases the bucket's lock in the 120 seconds
before SIGKILL, and botocore's defaults (60-second timeouts, five attempts) could spend them all;
the client here waits 5 seconds to connect and 10 for an answer, and tries 3 times.

## Where requests go

Only to AWS, in the topic's own region. The client is built with
`ignore_configured_endpoint_urls`, so neither `AWS_ENDPOINT_URL` nor an endpoint in the AWS config
can send a message somewhere else, and with no profile: the cloud tasks sign with their task role.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping
from typing import Any, Final, Protocol, cast

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from debate_core.application.ports.notifier import Notification
from debate_core.application.settings import SNS_TOPIC_ARN_PATTERN
from debate_core.integrations.secrets_manager import quiet_wire_log

__all__ = [
    "SUBJECT_LIMIT",
    "SnsClient",
    "SnsNotifier",
    "alert_message",
    "alert_subject",
    "build_sns_client",
    "region_of",
]

logger = logging.getLogger(__name__)

SUBJECT_LIMIT: Final = 99
"""SNS: a subject is "less than 100 characters long"."""

_TOPIC_ARN: Final = re.compile(SNS_TOPIC_ARN_PATTERN)
_NOT_PRINTABLE_ASCII: Final = re.compile(r"[^\x20-\x7e]+")

_CONFIG: Final = {
    "connect_timeout": 5,
    "read_timeout": 10,
    "retries": {"total_max_attempts": 3, "mode": "standard"},
}
"""At worst (5 + 10) x 3 = 45 seconds, inside the 120 a stopped run has."""


class SnsClient(Protocol):
    """The one SNS call this module makes, as boto3's client spells it."""

    def publish(self, *, TopicArn: str, Subject: str, Message: str) -> Mapping[str, Any]: ...  # noqa: N803 - boto3's names


def region_of(topic_arn: str) -> str:
    """The topic's region, which the client publishes in.

    Raises `ValueError` for anything but an SNS topic's ARN.
    """
    if not _TOPIC_ARN.fullmatch(topic_arn):
        raise ValueError("expected an SNS topic ARN, arn:aws:sns:<region>:<account>:<name>")
    return topic_arn.split(":")[3]


def build_sns_client(*, region: str) -> SnsClient:
    """An SNS client for `region`, signed by the SDK's own chain: the task role, in the cloud."""
    session = boto3.session.Session(region_name=region)
    # botocore has taken ignore_configured_endpoint_urls since 1.31; the botocore-stubs installed
    # here do not list it (as in debate_core.integrations.secrets_manager).
    config = Config(ignore_configured_endpoint_urls=True, **_CONFIG)  # pyright: ignore[reportCallIssue, reportArgumentType]
    # No boto3-stubs package is installed for SNS, so the overload is Unknown; the Protocol above is
    # the part of the client this module relies on.
    client = session.client("sns", config=config)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    return cast(SnsClient, client)


def alert_subject(notification: Notification, *, environment: str) -> str:
    """`debate <env>: <title>`, as one line of printable ASCII SNS will take."""
    subject = " ".join(_NOT_PRINTABLE_ASCII.sub(" ", f"debate {environment}: {notification.title}").split())
    if len(subject) > SUBJECT_LIMIT:
        subject = subject[: SUBJECT_LIMIT - 3].rstrip() + "..."
    return subject


def alert_message(notification: Notification) -> str:
    """The email's body: the title and subtitle, the message and its hint, and the fix on its own line."""
    heading = [notification.title, *([notification.subtitle] if notification.subtitle else [])]
    said = [notification.message, *([notification.hint] if notification.hint else [])]
    return "\n".join([*heading, "", *said, "", f"Fix: {notification.fix_command}"])


class SnsNotifier:
    """Publishes each notification to the environment's alert topic, once, best effort.

    Args:
        topic_arn: `caselist.alert_topic_arn`. Refused at once unless it is an SNS topic's ARN.
        environment: `dev` or `prod`, which the subject names.
        client: A client already built; tests pass one answered in-process.
        build_client: Builds the client for the topic's region on the first notification, never
            before, so a run that has nothing to say builds none.
    """

    def __init__(
        self,
        topic_arn: str,
        *,
        environment: str,
        client: SnsClient | None = None,
        build_client: Callable[..., SnsClient] = build_sns_client,
    ) -> None:
        self._region = region_of(topic_arn)
        self.topic_arn = topic_arn
        self._environment = environment
        self._client = client
        self._build_client = build_client

    def notify(self, notification: Notification) -> None:
        """Publish `notification`. A failure is logged by its code and swallowed: the run is recorded."""
        try:
            if self._client is None:
                self._client = self._build_client(region=self._region)
            with quiet_wire_log():
                self._client.publish(
                    TopicArn=self.topic_arn,
                    Subject=alert_subject(notification, environment=self._environment),
                    Message=alert_message(notification),
                )
        except ClientError as refused:
            code = str(refused.response.get("Error", {}).get("Code", "")) or "an unknown response"
            logger.warning("The alert to the coach was not sent: SNS Publish answered %s", code)
        except BotoCoreError as failed:
            logger.warning("The alert to the coach was not sent: %s", type(failed).__name__)
        except Exception as failed:  # noqa: BLE001 - the port's rule: a notifier never fails the run
            logger.warning("The alert to the coach was not sent: %s", type(failed).__name__)
