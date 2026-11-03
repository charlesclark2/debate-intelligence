"""`caselist auth set-password`, `renew`, and `login --token-backend secretsmanager` (ADR-0020 (2)).

Through Typer's `CliRunner` against the real application and composition root. OpenCaselist is
answered by respx; Secrets Manager by a real botocore client whose requests are answered in-process
through botocore's `before-send` hook, so botocore's own DEBUG logging of each request and response
runs, which is what a leak would go through. Nothing reaches the network or AWS: fake credentials,
no AWS config, no metadata service, and the client builder replaced by one returning that client.

**No failure prints a secret.** Every value is generated per test; a leak is reported by the
secret's name (:func:`assert_never_shown`), and records holding a fixture secret are kept from
pytest's own handlers, whose "Captured log" section a failure prints. (The same harness as
`packages/debate_core/tests/integrations/secrets_manager/conftest.py`, repeated here because test
directories cannot import one another under `--import-mode=importlib`.)
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import respx
from botocore.awsrequest import AWSPreparedRequest, AWSResponse
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.commands import caselist_auth
from debate_cli.container import ServiceContainer
from debate_cli.exit_codes import ExitCode
from debate_core.application.ports.notifier import RecordingNotifier
from debate_core.integrations import secrets_manager as secrets_manager_module

API = "https://api.opencaselist.example.invalid/v1"
PASSWORD_SECRET = "debate-test-caselist-tabroom-password"
TOKEN_SECRET = "debate-test-caselist-token"

runner = CliRunner()


# ------------------------------------------------------------------------------------------------
# The harness: a leak check that names, and an in-process Secrets Manager
# ------------------------------------------------------------------------------------------------


def forms_of(value: str) -> tuple[str, ...]:
    """`value` as is, JSON-escaped once and twice, and its random hex core, which no escaping changes."""
    once = json.dumps(value)[1:-1]
    twice = json.dumps(json.dumps(value))[1:-1]
    return tuple(dict.fromkeys((value, once, twice, *re.findall(r"[0-9a-f]{12,}", value))))


def assert_never_shown(text: str, named_secrets: Mapping[str, str], where: str) -> None:
    __tracebackhide__ = True
    leaked = sorted(
        name for name, value in named_secrets.items() if any(form in text for form in forms_of(value))
    )
    if leaked:
        pytest.fail(f"{' and '.join(leaked)} reached {where}", pytrace=False)


def logged_text(records: list[logging.LogRecord]) -> str:
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
    operation: str
    parameters: dict[str, Any]


class AnsweringSecretsManager:
    """Answers queued per operation, in order; records every request. No repr of what it holds."""

    def __init__(self, client: Any) -> None:
        self.client = client
        self.answers: list[tuple[str, int, dict[str, Any]]] = []
        self.exchanges: list[Exchange] = []
        self.built_with: list[str | None] = []

    def __repr__(self) -> str:
        return "AnsweringSecretsManager()"

    def answer(self, operation: str, body: dict[str, Any]) -> None:
        self.answers.append((operation, 200, body))

    def refuse(self, operation: str, code: str) -> None:
        self.answers.append((operation, 400, {"__type": code, "message": f"synthetic {code}"}))

    def before_send(self, request: AWSPreparedRequest, **_: object) -> AWSResponse:
        target: object = request.headers.get("X-Amz-Target", "")
        operation = (target.decode() if isinstance(target, bytes) else str(target)).rsplit(".", 1)[-1]
        body = request.body or b"{}"
        self.exchanges.append(
            Exchange(operation, json.loads(body if isinstance(body, bytes) else str(body).encode()))
        )
        expected, status, answer = self.answers.pop(0)
        if expected != operation:
            raise AssertionError(f"expected a {expected} request, got {operation}")
        return AWSResponse(
            request.url,
            status,
            {"content-type": "application/x-amz-json-1.1"},  # pyright: ignore[reportArgumentType]
            _Body(json.dumps(answer).encode()),  # pyright: ignore[reportArgumentType]
        )


class _KeepSecretsOut(logging.Filter):
    def __init__(self, values: list[str]) -> None:
        super().__init__()
        self.values = values

    def filter(self, record: logging.LogRecord) -> bool:
        text = logged_text([record])
        return not any(form in text for value in self.values for form in forms_of(value))


class _Collector(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@dataclass
class Values:
    username: str
    password: str
    token: str

    @property
    def named(self) -> dict[str, str]:
        return {
            "the Tabroom username": self.username,
            "the Tabroom password": self.password,
            "the token": self.token,
        }


@pytest.fixture
def values() -> Values:
    return Values(
        username=f"fixture-coach-{secrets.token_hex(8)}@example.invalid",
        password=f'fixture-"pass\\word"-{secrets.token_hex(8)}',
        token=f"fixture-token-{secrets.token_hex(16)}",
    )


@pytest.fixture
def logs(values: Values) -> Iterator[_Collector]:
    """Every record at DEBUG for the test; none holding a fixture secret for pytest's reports."""
    root = logging.getLogger()
    keep_out = _KeepSecretsOut([values.username, values.password, values.token])
    pytest_handlers = list(root.handlers)
    wire = [logging.getLogger(name) for name in secrets_manager_module.WIRE_LOGGERS]
    saved = (root.level, [(logger.level, logger.disabled) for logger in wire])
    collector = _Collector()
    for handler in pytest_handlers:
        handler.addFilter(keep_out)
    root.addHandler(collector)
    root.setLevel(logging.DEBUG)
    for logger in wire:
        logger.setLevel(logging.DEBUG)
        logger.disabled = False
    try:
        yield collector
    finally:
        root.removeHandler(collector)
        for handler in pytest_handlers:
            handler.removeFilter(keep_out)
        root.setLevel(saved[0])
        for logger, (level, disabled) in zip(wire, saved[1], strict=True):
            logger.setLevel(level)
            logger.disabled = disabled


@pytest.fixture
def environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A `test` environment of this test's own: the API on, the token in a file, fake AWS credentials."""
    for name in list(os.environ):
        if name.startswith(("DEBATE_", "AWS_")):
            monkeypatch.delenv(name, raising=False)
    data = tmp_path / "data"
    for name, value in {
        "DEBATE_ENV": "test",
        "DEBATE_STORAGE__DATA_DIR": str(data),
        "DEBATE_ALLOW_NETWORK": "true",
        "DEBATE_CASELIST__API_ENABLED": "true",
        "DEBATE_CASELIST__API_BASE_URL": API,
        "DEBATE_CASELIST__TOKEN_BACKEND": "file",
        "AWS_ACCESS_KEY_ID": "AKIAFIXTURE000000000",
        "AWS_SECRET_ACCESS_KEY": "fixture-secret-access-key",
        "AWS_CONFIG_FILE": str(tmp_path / "no-aws-config"),
        "AWS_SHARED_CREDENTIALS_FILE": str(tmp_path / "no-aws-credentials"),
        "AWS_EC2_METADATA_DISABLED": "true",
    }.items():
        monkeypatch.setenv(name, value)
    return data


@pytest.fixture
def aws(environment: Path, monkeypatch: pytest.MonkeyPatch) -> AnsweringSecretsManager:
    client: Any = secrets_manager_module.build_secrets_manager_client(region="us-east-1")
    answering = AnsweringSecretsManager(client)
    client.meta.events.register("before-send.secrets-manager", answering.before_send)

    def build(*, region: str, profile: str | None = None) -> Any:
        assert region == "us-east-1"
        answering.built_with.append(profile)
        return client

    monkeypatch.setattr(secrets_manager_module, "build_secrets_manager_client", build)
    return answering


@pytest.fixture
def api() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


@pytest.fixture
def terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Standard input is a terminal, as on the coach's Mac. `CliRunner`'s is not."""
    monkeypatch.setattr(caselist_auth, "stdin_is_a_terminal", lambda: True)


@pytest.fixture
def notifier(monkeypatch: pytest.MonkeyPatch) -> RecordingNotifier:
    recording = RecordingNotifier()
    monkeypatch.setattr(ServiceContainer, "sync_notifier", lambda self: recording)  # pyright: ignore[reportUnknownLambdaType]
    return recording


def invoke(*args: str, stdin: str | None = None) -> Result:
    return runner.invoke(create_app(), list(args), input=stdin)


def printed(result: Result) -> str:
    return result.stdout + result.stderr + repr(result.exception)


def envelope(result: Result) -> dict[str, Any]:
    return json.loads(result.stdout.strip().splitlines()[-1])


def described() -> dict[str, Any]:
    return {
        "ARN": f"arn:aws:secretsmanager:us-east-1:111122223333:secret:{PASSWORD_SECRET}-AbCdEf",
        "Name": PASSWORD_SECRET,
    }


def put_answer(name: str) -> dict[str, Any]:
    return {
        "ARN": f"arn:aws:secretsmanager:us-east-1:111122223333:secret:{name}-AbCdEf",
        "Name": name,
        "VersionId": "v2",
    }


def accept_login(api: respx.MockRouter, values: Values, *, status: int = 201) -> respx.Route:
    body = {"message": "Successfully logged in", "token": values.token, "expires": "2026-11-11T00:00:00.000Z"}
    return api.post(f"{API}/login").respond(status, json=body if status < 400 else {"message": "refused"})


# ------------------------------------------------------------------------------------------------
# set-password
# ------------------------------------------------------------------------------------------------


def test_set_password_without_a_terminal_is_refused_before_any_prompt_or_aws_call(
    aws: AnsweringSecretsManager,
) -> None:
    result = invoke("caselist", "auth", "set-password", stdin="someone\nsomething\nsomething\n")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, printed(result)
    assert "terminal" in result.stderr
    assert "Tabroom password" not in result.stderr
    assert aws.exchanges == []
    assert aws.built_with == []


def test_set_password_takes_no_password_argument(aws: AnsweringSecretsManager, terminal: None) -> None:
    result = invoke("caselist", "auth", "set-password", "--password", "anything")

    assert result.exit_code == 2
    assert aws.exchanges == []


def test_set_password_writes_the_typed_credentials_and_prints_nothing_of_them(
    aws: AnsweringSecretsManager,
    terminal: None,
    values: Values,
    logs: _Collector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A password in the environment is not where set-password reads one from.
    monkeypatch.setenv("TABROOM_PASSWORD", "fixture-environment-password")
    monkeypatch.setenv("CASELIST_PASSWORD", "fixture-environment-password")
    aws.answer("DescribeSecret", described())
    aws.answer("PutSecretValue", put_answer(PASSWORD_SECRET))

    result = invoke(
        "--json",
        "caselist",
        "auth",
        "set-password",
        "--aws-profile",
        "debate-test-caselist-writer",
        stdin=f"{values.username}\n{values.password}\n{values.password}\n",
    )

    assert result.exit_code == ExitCode.OK, result.stderr
    assert [exchange.operation for exchange in aws.exchanges] == ["DescribeSecret", "PutSecretValue"]
    assert aws.built_with == ["debate-test-caselist-writer"]
    put = aws.exchanges[1].parameters
    assert put["SecretId"] == PASSWORD_SECRET
    document = json.loads(put["SecretString"])
    stored = document == {"username": values.username, "password": values.password}
    assert stored, "the secret does not hold exactly the typed username and password"
    assert envelope(result)["data"] == {"written": True, "secret": PASSWORD_SECRET}
    # CliRunner echoes visible input to stdout, which a terminal would not; the hidden password
    # it echoes as nothing. So the username is checked everywhere but stdout.
    assert_never_shown(printed(result), {"the Tabroom password": values.password}, "the command's output")
    assert_never_shown(result.stderr + repr(result.exception), values.named, "the command's errors")
    assert_never_shown(logged_text(logs.records), values.named, "a log record")


def test_set_password_stops_before_prompting_when_the_secret_cannot_be_reached(
    aws: AnsweringSecretsManager, terminal: None
) -> None:
    aws.refuse("DescribeSecret", "AccessDeniedException")

    result = invoke("caselist", "auth", "set-password", stdin="")

    assert result.exit_code == ExitCode.RETRIEVAL_FAILURE, printed(result)
    assert PASSWORD_SECRET in result.stderr
    assert "Tabroom password" not in result.stderr
    assert [exchange.operation for exchange in aws.exchanges] == ["DescribeSecret"]


# ------------------------------------------------------------------------------------------------
# login --token-backend secretsmanager: the hand fallback
# ------------------------------------------------------------------------------------------------


def test_a_hand_login_to_secrets_manager_writes_only_the_token_secret(
    aws: AnsweringSecretsManager, api: respx.MockRouter, values: Values, logs: _Collector, environment: Path
) -> None:
    accept_login(api, values)
    aws.answer("PutSecretValue", put_answer(TOKEN_SECRET))

    result = invoke(
        "--json",
        "caselist",
        "auth",
        "login",
        "--token-backend",
        "secretsmanager",
        stdin=f"{values.username}\n{values.password}\n",
    )

    assert result.exit_code == ExitCode.OK, result.stderr
    assert [exchange.operation for exchange in aws.exchanges] == ["PutSecretValue"]
    put = aws.exchanges[0].parameters
    assert put["SecretId"] == TOKEN_SECRET
    record = json.loads(put["SecretString"])
    assert set(record) == {"token", "stored_at", "expires_at", "last_validated_at"}
    stored = record["token"] == values.token
    assert stored, "the token secret does not hold the issued token"
    assert_never_shown(
        put["SecretString"],
        {"the Tabroom password": values.password, "the Tabroom username": values.username},
        "the token secret",
    )
    data = envelope(result)["data"]
    assert data["backend"] == "secretsmanager"
    assert data["location"] == f"Secrets Manager secret {TOKEN_SECRET}"
    assert not (environment / "secrets").exists(), "the configured file backend was written as well"
    assert_never_shown(
        printed(result),
        {"the Tabroom password": values.password, "the token": values.token},
        "the command's output",
    )
    assert_never_shown(logged_text(logs.records), values.named, "a log record")


def test_logout_does_not_delete_the_token_secret(
    aws: AnsweringSecretsManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_CASELIST__TOKEN_BACKEND", "secretsmanager")

    result = invoke("caselist", "auth", "logout")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert TOKEN_SECRET in result.stderr
    assert aws.exchanges == []


# ------------------------------------------------------------------------------------------------
# renew: the login task
# ------------------------------------------------------------------------------------------------


def stored_credentials(values: Values) -> dict[str, Any]:
    return {
        "ARN": f"arn:aws:secretsmanager:us-east-1:111122223333:secret:{PASSWORD_SECRET}-AbCdEf",
        "Name": PASSWORD_SECRET,
        "SecretString": json.dumps({"username": values.username, "password": values.password}),
        "VersionId": "v1",
    }


def test_renew_reads_the_password_logs_in_once_and_writes_only_the_token(
    aws: AnsweringSecretsManager,
    api: respx.MockRouter,
    values: Values,
    logs: _Collector,
    notifier: RecordingNotifier,
) -> None:
    route = accept_login(api, values)
    aws.answer("GetSecretValue", stored_credentials(values))
    aws.answer("PutSecretValue", put_answer(TOKEN_SECRET))

    result = invoke("--json", "caselist", "auth", "renew")

    assert result.exit_code == ExitCode.OK, result.stderr
    assert route.call_count == 1
    sent = json.loads(route.calls.last.request.content) == {
        "username": values.username,
        "password": values.password,
        "remember": True,
    }
    assert sent, "the login did not send the stored username and password"
    assert [(e.operation, e.parameters["SecretId"]) for e in aws.exchanges] == [
        ("GetSecretValue", PASSWORD_SECRET),
        ("PutSecretValue", TOKEN_SECRET),
    ]
    assert aws.built_with == [None, None], "the login task signs with its task role, not a named profile"
    assert envelope(result)["data"]["location"] == f"Secrets Manager secret {TOKEN_SECRET}"
    assert notifier.sent == []
    assert_never_shown(printed(result), values.named, "the command's output")
    assert_never_shown(logged_text(logs.records), values.named, "a log record")


def test_a_refused_renew_is_tried_once_notified_once_and_exits_non_zero(
    aws: AnsweringSecretsManager,
    api: respx.MockRouter,
    values: Values,
    logs: _Collector,
    notifier: RecordingNotifier,
) -> None:
    route = accept_login(api, values, status=401)
    aws.answer("GetSecretValue", stored_credentials(values))

    result = invoke("caselist", "auth", "renew")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, printed(result)
    assert route.call_count == 1, "a refused login was tried again"
    assert [exchange.operation for exchange in aws.exchanges] == ["GetSecretValue"]
    [notification] = notifier.sent
    assert "CASELIST_LOGIN_REJECTED" in notification.message
    assert_never_shown(
        notification.title + notification.text + str(notification.subtitle), values.named, "the alert"
    )
    assert_never_shown(printed(result), values.named, "the command's output")
    assert_never_shown(logged_text(logs.records), values.named, "a log record")
