"""`caselist.notifier = sns` and its topic, read as the cloud run and login read them (`v1-e40-t05`).

ADR-0020 (5) and (6): both task definitions set the notifier to `sns` and name the environment's
alert topic, `debate-<env>-caselist-run-alerts`. The two names below are what
`infrastructure/modules/caselist_run/run_task.tf` and `login_task.tf` write for dev, copied by hand;
the module's Terraform tests pin the same names and values. An `sns` notifier with no topic would
announce nothing, silently, so it is refused when the settings load, which fails the task loudly
and is caught by the task-state rule.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from debate_core.application.settings import ConfigurationError, SyncNotifierKind, load_settings

COMMITTED_PROFILES = Path(__file__).resolve().parents[4] / "config" / "profiles"

ALERT_TOPIC = "arn:aws:sns:us-east-1:111122223333:debate-dev-caselist-run-alerts"

ALERTS_ENVIRONMENT = {
    "DEBATE_CASELIST__NOTIFIER": "sns",
    "DEBATE_CASELIST__ALERT_TOPIC_ARN": ALERT_TOPIC,
}


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Remove every `DEBATE_*` variable, so a test sees only what it sets itself."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    yield


def test_the_cloud_tasks_read_the_sns_notifier_and_its_topic(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in ALERTS_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)

    settings = load_settings(environment="dev", profile_dir=COMMITTED_PROFILES, env_file=None)

    assert settings.caselist.notifier is SyncNotifierKind.SNS
    assert settings.caselist.alert_topic_arn == ALERT_TOPIC
    assert settings.field_sources["caselist.alert_topic_arn"] == "env:DEBATE_CASELIST__ALERT_TOPIC_ARN"


def test_the_committed_dev_profile_names_no_topic_and_does_not_choose_sns() -> None:
    """The Mac reads the same profile: its banners stay on its screen."""
    settings = load_settings(environment="dev", profile_dir=COMMITTED_PROFILES, env_file=None)

    assert settings.caselist.notifier is not SyncNotifierKind.SNS
    assert settings.caselist.alert_topic_arn is None


def test_sns_with_no_topic_is_refused_naming_the_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEBATE_CASELIST__NOTIFIER", "sns")

    with pytest.raises(ConfigurationError, match="alert_topic_arn"):
        load_settings(environment="dev", profile_dir=COMMITTED_PROFILES, env_file=None)


@pytest.mark.parametrize(
    "topic",
    [
        "debate-dev-caselist-run-alerts",
        "arn:aws:sqs:us-east-1:111122223333:debate-dev-caselist-run-alerts",
        "arn:aws:sns:us-east-1:1111:debate-dev-caselist-run-alerts",
        "arn:aws:sns:us-east-1:111122223333:debate dev alerts",
    ],
)
def test_a_topic_that_is_not_an_sns_topic_arn_is_refused(topic: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEBATE_CASELIST__NOTIFIER", "sns")
    monkeypatch.setenv("DEBATE_CASELIST__ALERT_TOPIC_ARN", topic)

    # The topic's own refusal: its shape, not an unknown key or the notifier.
    with pytest.raises(
        ConfigurationError, match=r"caselist\.alert_topic_arn \(from env:\S+\): String should match pattern"
    ):
        load_settings(environment="dev", profile_dir=COMMITTED_PROFILES, env_file=None)
