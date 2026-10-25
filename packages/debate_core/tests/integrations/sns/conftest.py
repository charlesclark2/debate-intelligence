"""A real botocore SNS client answered in-process, and every log record a test needs to read.

**Nothing leaves the process.** :class:`AnsweringSns` builds the client the adapter builds
(:func:`~debate_core.integrations.sns.build_sns_client`) and answers every request from botocore's
`before-send` hook, the place botocore documents for a handler to return a response instead of
sending the request. Everything before that point runs for real: parameter validation (SNS's own
model refuses a subject it cannot take), serialisation, signing, and botocore's DEBUG log of the
request body, which is what the log tests exist for and what botocore's `Stubber` would skip.
Credentials are fixed fake values from the environment, and the instance metadata service is off.

SNS speaks the query protocol: a request is a form, an answer is XML.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from botocore.awsrequest import AWSPreparedRequest, AWSResponse

from debate_core.integrations.secrets_manager import WIRE_LOGGERS
from debate_core.integrations.sns import SnsClient, build_sns_client

TOPIC_ARN = "arn:aws:sns:us-east-1:111122223333:debate-dev-caselist-run-alerts"

_PUBLISHED = (
    '<PublishResponse xmlns="https://sns.amazonaws.com/doc/2010-03-31/">'
    "<PublishResult><MessageId>94f20ce6-13c5-43a0-9a9e-ca52d816e90b</MessageId></PublishResult>"
    "<ResponseMetadata><RequestId>f187a3c1-376f-11df-8963-01868b7c937a</RequestId></ResponseMetadata>"
    "</PublishResponse>"
)


def _refused(code: str) -> str:
    return (
        '<ErrorResponse xmlns="https://sns.amazonaws.com/doc/2010-03-31/">'
        f"<Error><Type>Sender</Type><Code>{code}</Code><Message>synthetic {code}</Message></Error>"
        "<RequestId>f187a3c1-376f-11df-8963-01868b7c937a</RequestId></ErrorResponse>"
    )


class _Body:
    def __init__(self, content: bytes) -> None:
        self._content = content

    def stream(self, **_: object) -> Iterator[bytes]:
        yield self._content

    def read(self, *_: object, **__: object) -> bytes:
        return self._content


@dataclass(frozen=True)
class Published:
    """One request the client sent, as SNS would have received it."""

    host: str
    action: str
    topic_arn: str
    subject: str | None
    message: str


class AnsweringSns:
    """A real client whose requests are answered here and recorded: published, unless told to refuse."""

    def __init__(self, client: SnsClient) -> None:
        self.client = client
        self.sent: list[Published] = []
        self._refusal: tuple[int, str] | None = None
        self._failure: Exception | None = None

    def refuse(self, code: str, *, status: int = 403) -> None:
        self._refusal = (status, code)

    def fail_with(self, error: Exception) -> None:
        self._failure = error

    def before_send(self, request: AWSPreparedRequest, **_: object) -> AWSResponse:
        body = request.body or b""
        form = parse_qs(body.decode() if isinstance(body, bytes) else str(body), keep_blank_values=True)
        self.sent.append(
            Published(
                host=urlsplit(request.url).hostname or "",
                action=form.get("Action", [""])[0],
                topic_arn=form.get("TopicArn", [""])[0],
                subject=form["Subject"][0] if "Subject" in form else None,
                message=form.get("Message", [""])[0],
            )
        )
        if self._failure is not None:
            raise self._failure
        status, text = (200, _PUBLISHED) if self._refusal is None else (self._refusal[0], _refused(self._refusal[1]))
        return AWSResponse(
            request.url,
            status,
            {"content-type": "text/xml"},  # pyright: ignore[reportArgumentType]
            _Body(text.encode()),  # pyright: ignore[reportArgumentType]
        )


@pytest.fixture
def fake_aws_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """Fixed fake credentials, no AWS config files, no metadata service, no endpoint override."""
    for name in (
        "AWS_PROFILE",
        "AWS_DEFAULT_PROFILE",
        "AWS_SESSION_TOKEN",
        "AWS_ENDPOINT_URL",
        "AWS_ENDPOINT_URL_SNS",
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAFIXTURE000000000")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "fixture-secret-access-key")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "no-aws-config"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "no-aws-credentials"))
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")


def answering(client: Any) -> AnsweringSns:
    """`client`, answered here: what every test that publishes uses."""
    answered = AnsweringSns(client)
    client.meta.events.register("before-send.sns", answered.before_send)
    return answered


@pytest.fixture
def sns(fake_aws_environment: None) -> AnsweringSns:
    return answering(build_sns_client(region="us-east-1"))


class _Collector(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def everything_logged(records: list[logging.LogRecord]) -> str:
    """Every rendered message, every string extra, and every traceback the records carry."""
    parts: list[str] = []
    for record in records:
        try:
            parts.append(record.getMessage())
        except Exception:  # noqa: BLE001 - a malformed record still has its raw text checked
            parts.append(str(record.msg))
        parts.extend(value for value in record.__dict__.values() if isinstance(value, str))
        if record.exc_info and record.exc_info[1] is not None:
            parts.append(repr(record.exc_info[1]))
    return "\n".join(parts)


@pytest.fixture
def every_record() -> Iterator[list[logging.LogRecord]]:
    """Every record at DEBUG, botocore's wire loggers included, whatever another suite set them to.

    Starts from the loggers as it finds them and puts them back (working agreement 10: tests that
    share process-wide logging state restore it).
    """
    collector = _Collector()
    root = logging.getLogger()
    wire = [logging.getLogger(name) for name in WIRE_LOGGERS]
    saved = (root.level, [(logger.level, logger.disabled, logger.propagate) for logger in wire])
    root.addHandler(collector)
    root.setLevel(logging.DEBUG)
    for logger in wire:
        logger.setLevel(logging.DEBUG)
        logger.disabled = False
        logger.propagate = True
    try:
        yield collector.records
    finally:
        root.removeHandler(collector)
        root.setLevel(saved[0])
        for logger, (level, disabled, propagate) in zip(wire, saved[1], strict=True):
            logger.setLevel(level)
            logger.disabled = disabled
            logger.propagate = propagate
