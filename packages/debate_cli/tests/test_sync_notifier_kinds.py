"""Which notifier `caselist.notifier` builds: the alert topic for `sns`, by name only (`v1-e40-t05`).

The cloud run's and login's task definitions set `caselist.notifier = sns` and the topic, and the
composition root builds :class:`~debate_core.integrations.sns.SnsNotifier` for that topic. `auto`
never chooses it, on a Mac or off one, and building it sends nothing: its client is made at the
first notification.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from debate_cli.container import ServiceContainer
from debate_core.application.ports.notifier import NullNotifier
from debate_core.application.settings import load_settings
from debate_core.integrations.sns import SnsNotifier

COMMITTED_PROFILES = Path(__file__).resolve().parents[3] / "config" / "profiles"
ALERT_TOPIC = "arn:aws:sns:us-east-1:111122223333:debate-dev-caselist-run-alerts"


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    yield


def container(environment: str = "dev") -> ServiceContainer:
    return ServiceContainer(
        settings_loader=lambda: load_settings(
            environment=environment, profile_dir=COMMITTED_PROFILES, env_file=None
        )
    )


def test_sns_builds_the_alert_topics_notifier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEBATE_CASELIST__NOTIFIER", "sns")
    monkeypatch.setenv("DEBATE_CASELIST__ALERT_TOPIC_ARN", ALERT_TOPIC)

    notifier = container().sync_notifier()

    assert isinstance(notifier, SnsNotifier)
    assert notifier.topic_arn == ALERT_TOPIC


def test_auto_never_builds_the_alert_topics_notifier_off_a_mac(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEBATE_CASELIST__NOTIFIER", "auto")
    monkeypatch.setenv("DEBATE_CASELIST__ALERT_TOPIC_ARN", ALERT_TOPIC)
    monkeypatch.setattr("sys.platform", "linux")

    assert isinstance(container().sync_notifier(), NullNotifier)
