"""A real botocore Secrets Manager client answered in-process, and a leak check that never prints a secret.

**Nothing leaves the process.** :class:`AnsweringSecretsManager` builds the client the adapter
builds (:func:`~debate_core.integrations.secrets_manager.build_secrets_manager_client`) and answers
every request from botocore's `before-send` hook, which botocore documents as the place a handler
may return a response instead of sending the request. Everything before that point runs for real:
parameter validation, serialisation, signing, and botocore's own DEBUG logging of the request; and
everything after: parsing, and the DEBUG logging of the response. That logging is what the
redaction tests exist for, and botocore's `Stubber` would skip it. Credentials are fixed fake
values from the environment, and the instance metadata service is switched off.

**No secret is committed.** Every value is generated per test from `secrets`.

**A failed test prints no secret** (the PM's line for E40: not even a test failure may print the
password or the token). :func:`assert_never_shown` reports a leaked secret's *name*, never its
value, and is the only assertion these tests make about a secret's absence. :class:`SecretSafeLog`
collects every record for the tests to check, and keeps every record that holds a secret away from
pytest's own handlers, whose "Captured log" section a failure would print. The harness's own
objects have no repr that shows what they hold, because botocore logs the handlers it calls.
"""

from __future__ import annotations

import json
import logging
import re
import secrets
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

import pytest
from botocore.awsrequest import AWSPreparedRequest, AWSResponse

from debate_core.integrations.secrets_manager import (
    WIRE_LOGGERS,
    SecretsManagerClient,
    build_secrets_manager_client,
)


def forms_of(value: str) -> tuple[str, ...]:
    """`value` as it could appear in a log, however escaped.

    As is, JSON-escaped once (a body) and twice (a body in a body), and its random core: every
    fixture secret ends in a run of hex digits from `secrets`, which no escaping changes. The core is
    what catches a form nobody listed, such as botocore's `repr` of a request body, which escapes
    the quotes and backslashes a JSON body already escaped.
    """
    once = json.dumps(value)[1:-1]
    twice = json.dumps(json.dumps(value))[1:-1]
    cores = re.findall(r"[0-9a-f]{12,}", value)
    return tuple(dict.fromkeys((value, once, twice, *cores)))


def assert_never_shown(text: str, named_secrets: Mapping[str, str], where: str) -> None:
    """Fail if any of `named_secrets`' values, in any of its forms, is in `text`. Names only."""
    __tracebackhide__ = True
    leaked = sorted(
        name for name, value in named_secrets.items() if any(form in text for form in forms_of(value))
    )
    if leaked:
        pytest.fail(f"{' and '.join(leaked)} reached {where}", pytrace=False)


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


class _Body:
    def __init__(self, content: bytes) -> None:
        self._content = content

    def stream(self, **_: object) -> Iterator[bytes]:
        yield self._content

    def read(self, *_: object, **__: object) -> bytes:
        return self._content


@dataclass(repr=False)
class Exchange:
    """One request the client sent, as Secrets Manager would have received it."""

    operation: str
    parameters: dict[str, Any]


class AnsweringSecretsManager:
    """A real client whose requests are answered here, in order, and recorded.

    Deliberately not a dataclass: botocore logs `repr` of every event handler it calls, and this
    one holds the values it answers with.
    """

    def __init__(self, client: SecretsManagerClient) -> None:
        self.client = client
        self.answers: list[tuple[str, int, dict[str, Any]]] = []
        self.exchanges: list[Exchange] = []

    def __repr__(self) -> str:
        return "AnsweringSecretsManager()"

    def answer(self, operation: str, body: dict[str, Any], *, status: int = 200) -> None:
        self.answers.append((operation, status, body))

    def refuse(self, operation: str, code: str, *, status: int = 400) -> None:
        self.answers.append((operation, status, {"__type": code, "message": f"synthetic {code}"}))

    def calls(self, operation: str) -> list[Exchange]:
        return [exchange for exchange in self.exchanges if exchange.operation == operation]

    def before_send(self, request: AWSPreparedRequest, **_: object) -> AWSResponse:
        target: object = request.headers.get("X-Amz-Target", "")
        operation = (target.decode() if isinstance(target, bytes) else str(target)).rsplit(".", 1)[-1]
        body = request.body or b"{}"
        raw = body if isinstance(body, bytes) else str(body).encode()
        self.exchanges.append(Exchange(operation, json.loads(raw)))
        if not self.answers:
            raise AssertionError(f"no answer queued for {operation}")
        expected, status, answer = self.answers.pop(0)
        if expected != operation:
            raise AssertionError(f"expected a {expected} request, got {operation}")
        return AWSResponse(
            request.url,
            status,
            {"content-type": "application/x-amz-json-1.1"},
            _Body(json.dumps(answer).encode()),  # pyright: ignore[reportArgumentType]
        )


@pytest.fixture
def fake_aws_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """Fixed fake credentials, no AWS config files, no metadata service, no endpoint override."""
    for name in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE", "AWS_SESSION_TOKEN", "AWS_ENDPOINT_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAFIXTURE000000000")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "fixture-secret-access-key")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "no-aws-config"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "no-aws-credentials"))
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")


@pytest.fixture
def secrets_manager(fake_aws_environment: None) -> AnsweringSecretsManager:
    client: Any = build_secrets_manager_client(region="us-east-1")
    answering = AnsweringSecretsManager(client)
    client.meta.events.register("before-send.secrets-manager", answering.before_send)
    return answering


class _Collector(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class _KeepSecretsOut(logging.Filter):
    """On pytest's handlers: drops a record that holds a fixture secret, so no report can print it."""

    def __init__(self, values: list[str]) -> None:
        super().__init__()
        self._values = values

    def filter(self, record: logging.LogRecord) -> bool:
        text = everything_logged([record])
        return not any(form in text for value in self._values for form in forms_of(value))


class SecretSafeLog:
    """Every record at DEBUG, for the test to check, and none with a secret for pytest to print."""

    def __init__(self, guarded: list[str]) -> None:
        self._guarded = guarded
        self._collector = _Collector()

    @property
    def records(self) -> list[logging.LogRecord]:
        return self._collector.records

    def guard(self, value: str) -> None:
        """Keep `value` out of pytest's reports too: for a secret a test makes itself."""
        self._guarded.append(value)


@pytest.fixture
def wire_log(token: str, password: str) -> Iterator[SecretSafeLog]:
    """Every record at DEBUG, botocore's wire loggers included, whatever another suite set them to.

    Starts from the loggers as it finds them and puts them back (working agreement 10: tests that
    share process-wide logging state restore it).
    """
    log = SecretSafeLog([token, password])
    root = logging.getLogger()
    keep_out = _KeepSecretsOut(log._guarded)  # pyright: ignore[reportPrivateUsage]
    pytest_handlers = list(root.handlers)
    wire = [logging.getLogger(name) for name in WIRE_LOGGERS]
    saved = (root.level, [(logger.level, logger.disabled, logger.propagate) for logger in wire])
    for handler in pytest_handlers:
        handler.addFilter(keep_out)
    root.addHandler(log._collector)  # pyright: ignore[reportPrivateUsage]
    root.setLevel(logging.DEBUG)
    for logger in wire:
        logger.setLevel(logging.DEBUG)
        logger.disabled = False
        logger.propagate = True
    try:
        yield log
    finally:
        root.removeHandler(log._collector)  # pyright: ignore[reportPrivateUsage]
        for handler in pytest_handlers:
            handler.removeFilter(keep_out)
        root.setLevel(saved[0])
        for logger, (level, disabled, propagate) in zip(wire, saved[1], strict=True):
            logger.setLevel(level)
            logger.disabled = disabled
            logger.propagate = propagate


@pytest.fixture
def password() -> str:
    # Quotes, a backslash and a non-ASCII letter, so the value is escaped in JSON and a check that
    # only looked for the raw string would miss it.
    return f'fixture-"pass\\word"-é-{secrets.token_hex(8)}'


@pytest.fixture
def token() -> str:
    return f"fixture-token-{secrets.token_hex(16)}"
