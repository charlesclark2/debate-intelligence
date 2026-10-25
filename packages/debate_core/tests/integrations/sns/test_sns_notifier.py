"""The alert topic as a notifier: one publish per notification, best effort, and never in a log.

ADR-0020 (6) and `v1-e40-t05`: the cloud run and the cloud login send what the Mac's banners say
to `debate-<env>-caselist-run-alerts`, which emails the coach. The PM's rules for the adapter are
t02's for the Secrets Manager client: one small boto3 client, no endpoint override, nothing about
the message body in a log. A notifier also never fails the run it reports on (the port's rule).

botocore writes a request's body to its DEBUG log, so the first test shows that it does for a
publish (a check that cannot see the leak proves nothing), and the next that this adapter stops it.
"""

from __future__ import annotations

import logging
import string
from typing import Any

import pytest
from botocore.exceptions import EndpointConnectionError
from hypothesis import event, given, settings
from hypothesis import strategies as st

from debate_core.application.ports.notifier import Notification
from debate_core.integrations import sns as sns_module
from debate_core.integrations.sns import SUBJECT_LIMIT, SnsNotifier, build_sns_client, region_of

from .conftest import TOPIC_ARN, AnsweringSns, answering, everything_logged

BODY_PROBE = "Zqxbodyprobe"
"""In every message a test publishes, so a log that holds the body is caught by name."""

FAILED_RUN = Notification(
    title="caselist pull failed: needs a person",
    subtitle="Run 20261104T110002Z (dev)",
    message=f"Run 20261104T110002Z (dev): the download stage failed on PROVIDER_UNAVAILABLE. {BODY_PROBE}",
    fix_command="debate-research caselist pull",
    hint="Nothing that did download was lost.",
)


def notifier(answered: AnsweringSns, *, environment: str = "dev", topic_arn: str = TOPIC_ARN) -> SnsNotifier:
    return SnsNotifier(topic_arn, environment=environment, client=answered.client)


# ------------------------------------------------------------------------------------------------
# What is published
# ------------------------------------------------------------------------------------------------


def test_a_notification_is_one_publish_to_the_topic(sns: AnsweringSns) -> None:
    notifier(sns).notify(FAILED_RUN)

    assert [(one.action, one.topic_arn, one.host) for one in sns.sent] == [
        ("Publish", TOPIC_ARN, "sns.us-east-1.amazonaws.com")
    ]


def test_the_subject_is_the_environment_and_the_title(sns: AnsweringSns) -> None:
    notifier(sns).notify(FAILED_RUN)

    assert sns.sent[0].subject == "debate dev: caselist pull failed: needs a person"


def test_the_message_says_what_the_banner_says_with_the_fix_on_its_own_line(sns: AnsweringSns) -> None:
    notifier(sns).notify(FAILED_RUN)

    assert sns.sent[0].message == (
        "caselist pull failed: needs a person\n"
        "Run 20261104T110002Z (dev)\n"
        "\n"
        f"Run 20261104T110002Z (dev): the download stage failed on PROVIDER_UNAVAILABLE. {BODY_PROBE}\n"
        "Nothing that did download was lost.\n"
        "\n"
        "Fix: debate-research caselist pull"
    )


def test_a_notification_with_no_subtitle_or_hint_leaves_their_lines_out(sns: AnsweringSns) -> None:
    notifier(sns).notify(
        Notification(title="Weekly caselist login failed", message="It stopped.", fix_command="x")
    )

    assert sns.sent[0].message == "Weekly caselist login failed\n\nIt stopped.\n\nFix: x"


_PRINTABLE_ASCII = frozenset(string.printable) - frozenset("\t\n\r\x0b\x0c")


@settings(max_examples=300, deadline=None)
@given(
    # Half short, half past the limit: plain st.text() made a title too long for a subject 0.33% of
    # the time (measured with --hypothesis-show-statistics), so the cut was barely exercised.
    title=st.one_of(st.text(max_size=60), st.text(min_size=SUBJECT_LIMIT, max_size=300)),
    environment=st.sampled_from(["dev", "prod"]),
)
def test_every_subject_is_one_line_of_ascii_under_100_characters(title: str, environment: str) -> None:
    """SNS refuses a subject it cannot take, and a refused publish is an alert nobody gets.

    Its rule: ASCII, starting with a letter, a digit or punctuation, no line break or control
    character, fewer than 100 characters. Titles carry an em dash or an apostrophe today, and any
    text tomorrow.
    """
    event(
        "a title with a character outside printable ASCII"
        if set(title) - _PRINTABLE_ASCII
        else "an ASCII title"
    )
    event("a title too long for a subject" if len(title) > SUBJECT_LIMIT else "a title that fits")
    subject = sns_module.alert_subject(
        Notification(title=title, message="m", fix_command="f"), environment=environment
    )

    assert 0 < len(subject) <= SUBJECT_LIMIT < 100
    assert set(subject) <= _PRINTABLE_ASCII
    assert subject[0] not in " "


def test_a_long_title_is_shortened_and_the_whole_title_is_still_in_the_message(sns: AnsweringSns) -> None:
    title = "caselist pull failed — " + "x" * 200

    notifier(sns).notify(Notification(title=title, message="m", fix_command="f"))

    assert sns.sent[0].subject is not None
    assert len(sns.sent[0].subject) == SUBJECT_LIMIT
    assert sns.sent[0].subject.endswith("...")
    assert sns.sent[0].message.startswith(title + "\n")


# ------------------------------------------------------------------------------------------------
# Where it goes
# ------------------------------------------------------------------------------------------------


def test_the_region_is_the_topics(fake_aws_environment: None) -> None:
    eu_topic = "arn:aws:sns:eu-west-1:111122223333:debate-dev-caselist-run-alerts"
    built: list[str] = []

    def build(*, region: str) -> Any:
        built.append(region)
        return answering(build_sns_client(region=region)).client

    SnsNotifier(eu_topic, environment="dev", build_client=build).notify(FAILED_RUN)

    assert built == ["eu-west-1"]
    assert region_of(TOPIC_ARN) == "us-east-1"


def test_an_endpoint_override_in_the_environment_is_ignored(
    fake_aws_environment: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A message for the coach goes to AWS, never wherever AWS_ENDPOINT_URL points."""
    monkeypatch.setenv("AWS_ENDPOINT_URL", "https://collector.example.invalid")
    monkeypatch.setenv("AWS_ENDPOINT_URL_SNS", "https://collector.example.invalid")
    answered = answering(build_sns_client(region="us-east-1"))

    notifier(answered).notify(FAILED_RUN)

    assert answered.sent[0].host == "sns.us-east-1.amazonaws.com"


def test_the_client_is_built_once_and_only_when_a_notification_is_sent(fake_aws_environment: None) -> None:
    built: list[str] = []

    def build(*, region: str) -> Any:
        built.append(region)
        return answering(build_sns_client(region=region)).client

    alerts = SnsNotifier(TOPIC_ARN, environment="dev", build_client=build)
    assert built == []

    alerts.notify(FAILED_RUN)
    alerts.notify(FAILED_RUN)

    assert built == ["us-east-1"]


def test_the_client_gives_up_inside_the_two_minutes_a_stopped_run_has(fake_aws_environment: None) -> None:
    """A run told to stop (RUN_TERMINATED) records, notifies and releases the lock in the 120 seconds
    before SIGKILL. botocore's defaults (60-second timeouts, five attempts) could spend all of it."""
    client: Any = build_sns_client(region="us-east-1")
    config: Any = client.meta.config

    worst = int((config.connect_timeout + config.read_timeout) * config.retries["total_max_attempts"])

    assert worst <= 60


@pytest.mark.parametrize(
    "topic_arn", ["", "debate-dev-caselist-run-alerts", "arn:aws:sqs:us-east-1:111122223333:x"]
)
def test_a_topic_that_is_not_an_sns_arn_is_refused_when_the_notifier_is_built(topic_arn: str) -> None:
    with pytest.raises(ValueError, match="SNS topic ARN"):
        SnsNotifier(topic_arn, environment="dev")


# ------------------------------------------------------------------------------------------------
# Best effort: a failed delivery never fails the run
# ------------------------------------------------------------------------------------------------


def test_a_refused_publish_is_logged_by_its_code_and_not_raised(
    sns: AnsweringSns, every_record: list[logging.LogRecord]
) -> None:
    sns.refuse("AuthorizationError")

    notifier(sns).notify(FAILED_RUN)

    warnings = [record for record in every_record if record.levelno >= logging.WARNING]
    assert [record.name for record in warnings] == ["debate_core.integrations.sns"]
    assert "AuthorizationError" in warnings[0].getMessage()


def test_an_unreachable_sns_is_logged_by_its_class_and_not_raised(
    sns: AnsweringSns, every_record: list[logging.LogRecord]
) -> None:
    sns.fail_with(EndpointConnectionError(endpoint_url="https://sns.us-east-1.amazonaws.com/"))

    notifier(sns).notify(FAILED_RUN)

    warnings = [record for record in every_record if record.name == "debate_core.integrations.sns"]
    assert len(warnings) == 1
    assert "EndpointConnectionError" in warnings[0].getMessage()


def test_no_credentials_is_logged_and_not_raised(
    fake_aws_environment: None, monkeypatch: pytest.MonkeyPatch, every_record: list[logging.LogRecord]
) -> None:
    monkeypatch.delenv("AWS_ACCESS_KEY_ID")
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY")
    answered = answering(build_sns_client(region="us-east-1"))

    notifier(answered).notify(FAILED_RUN)

    assert any(record.name == "debate_core.integrations.sns" for record in every_record)


def test_a_client_that_cannot_be_built_is_logged_and_not_raised(
    every_record: list[logging.LogRecord],
) -> None:
    def cannot(*, region: str) -> Any:
        raise RuntimeError("no boto3 here")

    SnsNotifier(TOPIC_ARN, environment="dev", build_client=cannot).notify(FAILED_RUN)

    assert any(record.name == "debate_core.integrations.sns" for record in every_record)


# ------------------------------------------------------------------------------------------------
# Nothing about the message reaches a log
# ------------------------------------------------------------------------------------------------


def test_botocore_logs_a_publishs_body_when_nothing_quiets_it(
    sns: AnsweringSns, every_record: list[logging.LogRecord]
) -> None:
    """The control: the same publish, on the raw client, puts the body in a DEBUG record."""
    sns.client.publish(TopicArn=TOPIC_ARN, Subject="s", Message=FAILED_RUN.message)

    found = BODY_PROBE in everything_logged(every_record)
    assert found, "botocore's DEBUG log no longer shows a request body; the test below would be blind"


def test_nothing_published_reaches_a_log(sns: AnsweringSns, every_record: list[logging.LogRecord]) -> None:
    notifier(sns).notify(FAILED_RUN)

    assert sns.sent, "nothing was published, so this proves nothing"
    assert BODY_PROBE not in everything_logged(every_record)


def test_nothing_published_reaches_a_log_when_the_publish_is_refused(
    sns: AnsweringSns, every_record: list[logging.LogRecord]
) -> None:
    sns.refuse("InvalidParameter", status=400)

    notifier(sns).notify(FAILED_RUN)

    assert BODY_PROBE not in everything_logged(every_record)
