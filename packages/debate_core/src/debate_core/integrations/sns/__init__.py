"""Skeleton for the red run: the real signatures, publishing the text as given, refusing nothing."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Final, Protocol, cast

import boto3

from debate_core.application.ports.notifier import Notification

__all__ = ["SUBJECT_LIMIT", "SnsClient", "SnsNotifier", "alert_message", "alert_subject", "build_sns_client", "region_of"]

SUBJECT_LIMIT: Final = 99


class SnsClient(Protocol):
    def publish(self, *, TopicArn: str, Subject: str, Message: str) -> Mapping[str, Any]: ...  # noqa: N803


def region_of(topic_arn: str) -> str:
    return "us-east-1"


def build_sns_client(*, region: str) -> SnsClient:
    client = boto3.session.Session(region_name=region).client("sns")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    return cast(SnsClient, client)


def alert_subject(notification: Notification, *, environment: str) -> str:
    return notification.title


def alert_message(notification: Notification) -> str:
    return notification.text


class SnsNotifier:
    def __init__(
        self,
        topic_arn: str,
        *,
        environment: str,
        client: SnsClient | None = None,
        build_client: Callable[..., SnsClient] = build_sns_client,
    ) -> None:
        self.topic_arn = topic_arn
        self._environment = environment
        self._client = client
        self._build_client = build_client

    def notify(self, notification: Notification) -> None:
        client = self._client or self._build_client(region=region_of(self.topic_arn))
        client.publish(
            TopicArn=self.topic_arn,
            Subject=alert_subject(notification, environment=self._environment),
            Message=alert_message(notification),
        )
