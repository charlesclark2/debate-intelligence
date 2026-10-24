"""One Secrets Manager secret through a real botocore client, and what never reaches a log or an error.

ADR-0020 (2) and `docs/policies/caselist-data-use.md` E34 gate 3: the Tabroom password and the
caselist_token are stored in Secrets Manager and nowhere else, never in a log. botocore writes
request parameters and response bodies to its own loggers at DEBUG, so the first tests here show
that it does (a check that cannot see the leak proves nothing), and the rest that nothing this
package does lets it.
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import UTC, datetime

import pytest
from pydantic import SecretStr

from debate_core.application.caselist_login import (
    TabroomCredentials,
    TabroomCredentialsMissing,
    TabroomCredentialsUnreadable,
    TabroomPasswordSecret,
)
from debate_core.application.errors import (
    NotFound,
    StoreAccessDenied,
    StoreCredentialsExpired,
    StoreProfileNotConfigured,
    StoreUnavailable,
)
from debate_core.integrations.opencaselist.token_store import CaselistTokenStore, SecretsManagerTokenBackend
from debate_core.integrations.secrets_manager import ManagedSecret, build_secrets_manager_client

from .conftest import AnsweringSecretsManager, SecretSafeLog, assert_never_shown, everything_logged

TOKEN_SECRET = "debate-test-caselist-token"
PASSWORD_SECRET = "debate-test-caselist-tabroom-password"
NOW = datetime(2026, 10, 28, 8, 0, tzinfo=UTC)


def answered_value(name: str, value: str) -> dict[str, object]:
    return {
        "ARN": f"arn:aws:secretsmanager:us-east-1:111122223333:secret:{name}-AbCdEf",
        "Name": name,
        "SecretString": value,
        "VersionId": "11111111-2222-3333-4444-555555555555",
    }


def written(name: str) -> dict[str, object]:
    return {
        "ARN": f"arn:aws:secretsmanager:us-east-1:111122223333:secret:{name}-AbCdEf",
        "Name": name,
        "VersionId": "66666666-7777-8888-9999-000000000000",
    }


# ------------------------------------------------------------------------------------------------
# The leak is real: botocore logs both values when nothing stops it
# ------------------------------------------------------------------------------------------------


def test_botocore_logs_a_read_secret_when_nothing_quiets_it(
    secrets_manager: AnsweringSecretsManager, wire_log: SecretSafeLog, token: str
) -> None:
    """The control: the same call, made on the raw client, puts the value in a DEBUG record."""
    secrets_manager.answer("GetSecretValue", answered_value(TOKEN_SECRET, token))

    secrets_manager.client.get_secret_value(SecretId=TOKEN_SECRET)

    logged = everything_logged(wire_log.records)
    found = token in logged
    assert found, "botocore's DEBUG log no longer shows a response body; the tests below would be blind"


def test_botocore_logs_a_written_secret_when_nothing_quiets_it(
    secrets_manager: AnsweringSecretsManager, wire_log: SecretSafeLog, token: str
) -> None:
    secrets_manager.answer("PutSecretValue", written(TOKEN_SECRET))

    secrets_manager.client.put_secret_value(SecretId=TOKEN_SECRET, SecretString=token)

    found = token in everything_logged(wire_log.records)
    assert found, (
        "botocore's DEBUG log no longer shows a request's parameters; the tests below would be blind"
    )


# ------------------------------------------------------------------------------------------------
# ManagedSecret: reads, writes and describes, and logs neither value
# ------------------------------------------------------------------------------------------------


def test_a_read_returns_the_value_and_logs_none_of_it(
    secrets_manager: AnsweringSecretsManager, wire_log: SecretSafeLog, token: str
) -> None:
    secrets_manager.answer("GetSecretValue", answered_value(TOKEN_SECRET, token))

    value = ManagedSecret(secrets_manager.client, TOKEN_SECRET).read()

    matches = value == token
    assert matches, "the value read is not the value Secrets Manager answered with"
    assert secrets_manager.calls("GetSecretValue")[0].parameters == {"SecretId": TOKEN_SECRET}
    assert_never_shown(everything_logged(wire_log.records), {"the token": token}, "a log record")
    assert wire_log.records, "nothing was logged at all, so the check above saw nothing"


def test_a_write_sends_the_value_once_and_logs_none_of_it(
    secrets_manager: AnsweringSecretsManager, wire_log: SecretSafeLog, password: str
) -> None:
    secrets_manager.answer("PutSecretValue", written(PASSWORD_SECRET))

    version = ManagedSecret(secrets_manager.client, PASSWORD_SECRET).write(password)

    assert version == "66666666-7777-8888-9999-000000000000"
    [put] = secrets_manager.calls("PutSecretValue")
    sent_whole = put.parameters["SecretString"] == password
    assert sent_whole, "the value Secrets Manager received is not the value written"
    assert set(put.parameters) <= {"SecretId", "SecretString", "ClientRequestToken"}
    assert_never_shown(everything_logged(wire_log.records), {"the password": password}, "a log record")


def test_an_empty_secret_reads_as_none(secrets_manager: AnsweringSecretsManager) -> None:
    """Terraform creates both secrets with no value; Secrets Manager answers that as not found."""
    secrets_manager.refuse("GetSecretValue", "ResourceNotFoundException")

    assert ManagedSecret(secrets_manager.client, TOKEN_SECRET).read() is None


def test_describe_reads_no_value(secrets_manager: AnsweringSecretsManager) -> None:
    secrets_manager.answer(
        "DescribeSecret",
        {"ARN": "arn:aws:secretsmanager:us-east-1:111122223333:secret:x", "Name": PASSWORD_SECRET},
    )

    ManagedSecret(secrets_manager.client, PASSWORD_SECRET).describe()

    assert [exchange.operation for exchange in secrets_manager.exchanges] == ["DescribeSecret"]


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("AccessDeniedException", StoreAccessDenied),
        ("DecryptionFailure", StoreAccessDenied),
        ("ExpiredTokenException", StoreCredentialsExpired),
        ("ResourceNotFoundException", NotFound),
        ("InternalServiceError", StoreUnavailable),
    ],
)
def test_a_refused_write_is_a_store_error_naming_the_secret_and_carrying_nothing_of_botocores(
    secrets_manager: AnsweringSecretsManager,
    wire_log: SecretSafeLog,
    password: str,
    code: str,
    expected: type[Exception],
) -> None:
    secrets_manager.refuse("PutSecretValue", code)

    with pytest.raises(expected) as refused:
        ManagedSecret(secrets_manager.client, PASSWORD_SECRET, login_hint="run `aws sso login`").write(
            password
        )

    assert PASSWORD_SECRET in str(refused.value)
    assert refused.value.__cause__ is None
    assert refused.value.__suppress_context__
    assert_never_shown(str(refused.value) + repr(refused.value), {"the password": password}, "the error")
    assert_never_shown(everything_logged(wire_log.records), {"the password": password}, "a log record")


def test_a_wrongly_typed_value_is_refused_without_quoting_it(
    secrets_manager: AnsweringSecretsManager, password: str
) -> None:
    """botocore's parameter validation quotes the value it rejects; `from None` keeps it out."""
    with pytest.raises(StoreUnavailable) as refused:
        ManagedSecret(secrets_manager.client, PASSWORD_SECRET).write(SecretStr(password))  # pyright: ignore[reportArgumentType]

    assert refused.value.__cause__ is None and refused.value.__suppress_context__
    assert_never_shown(str(refused.value), {"the password": password}, "the error")


def test_an_unknown_profile_is_a_configuration_error(fake_aws_environment: None) -> None:
    with pytest.raises(StoreProfileNotConfigured):
        build_secrets_manager_client(region="us-east-1", profile="debate-test-no-such-profile")


def test_an_endpoint_override_in_the_environment_is_ignored(
    fake_aws_environment: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`AWS_ENDPOINT_URL` cannot send a password anywhere but Secrets Manager."""
    monkeypatch.setenv("AWS_ENDPOINT_URL", "https://collector.example.invalid")
    monkeypatch.setenv("AWS_ENDPOINT_URL_SECRETS_MANAGER", "https://collector.example.invalid")

    client = build_secrets_manager_client(region="us-east-1")

    assert client.meta.endpoint_url == "https://secretsmanager.us-east-1.amazonaws.com"  # pyright: ignore[reportAttributeAccessIssue]


def test_quieting_is_for_the_calling_thread_and_the_call_only(wire_log: SecretSafeLog) -> None:
    from debate_core.integrations.secrets_manager import quiet_wire_log

    endpoint = logging.getLogger("botocore.endpoint")
    with quiet_wire_log():
        endpoint.debug("inside")
    endpoint.debug("outside")

    assert [record.getMessage() for record in wire_log.records if record.name == "botocore.endpoint"] == [
        "outside"
    ]


# ------------------------------------------------------------------------------------------------
# The two documents kept in it: the token record and the Tabroom credentials
# ------------------------------------------------------------------------------------------------


def test_the_token_store_on_secrets_manager_logs_neither_write_nor_read(
    secrets_manager: AnsweringSecretsManager, wire_log: SecretSafeLog, token: str
) -> None:
    secrets_manager.answer("PutSecretValue", written(TOKEN_SECRET))
    writer = CaselistTokenStore(
        SecretsManagerTokenBackend(ManagedSecret(secrets_manager.client, TOKEN_SECRET)), clock=lambda: NOW
    )
    writer.save(SecretStr(token), expires_at=None)
    [put] = secrets_manager.calls("PutSecretValue")
    secrets_manager.answer("GetSecretValue", answered_value(TOKEN_SECRET, put.parameters["SecretString"]))
    reader = CaselistTokenStore(
        SecretsManagerTokenBackend(ManagedSecret(secrets_manager.client, TOKEN_SECRET)), clock=lambda: NOW
    )

    loaded = reader.load()

    assert loaded is not None
    round_tripped = loaded.token.get_secret_value() == token
    assert round_tripped, "the token read back is not the token written"
    assert_never_shown(
        everything_logged(wire_log.records) + repr(loaded),
        {"the token": token},
        "a log record or the stored token's repr",
    )


def test_the_password_document_round_trips_and_logs_nothing(
    secrets_manager: AnsweringSecretsManager, wire_log: SecretSafeLog, password: str
) -> None:
    username = f"fixture-coach-{secrets.token_hex(8)}@example.invalid"
    wire_log.guard(username)
    secrets_manager.answer("PutSecretValue", written(PASSWORD_SECRET))
    secret = TabroomPasswordSecret(ManagedSecret(secrets_manager.client, PASSWORD_SECRET))
    secret.write(TabroomCredentials(username=username, password=SecretStr(password)))
    [put] = secrets_manager.calls("PutSecretValue")
    assert set(json.loads(put.parameters["SecretString"])) == {"username", "password"}
    secrets_manager.answer("GetSecretValue", answered_value(PASSWORD_SECRET, put.parameters["SecretString"]))

    read = secret.read()

    assert read.username == username
    round_tripped = read.password.get_secret_value() == password
    assert round_tripped, "the password read back is not the password written"
    assert_never_shown(
        everything_logged(wire_log.records) + repr(read),
        {"the password": password, "the username": username},
        "a log record or the credentials' repr",
    )


def test_an_empty_password_secret_says_who_writes_it(secrets_manager: AnsweringSecretsManager) -> None:
    secrets_manager.refuse("GetSecretValue", "ResourceNotFoundException")

    with pytest.raises(TabroomCredentialsMissing, match="set-password"):
        TabroomPasswordSecret(ManagedSecret(secrets_manager.client, PASSWORD_SECRET)).read()


@pytest.mark.parametrize(
    "document",
    [
        '{"username": "u", "password": PASSWORD',
        '{"password": "PASSWORD"}',
        '"PASSWORD"',
        '{"username": "", "password": "PASSWORD"}',
    ],
)
def test_a_password_secret_in_another_shape_is_refused_without_quoting_it(
    secrets_manager: AnsweringSecretsManager, password: str, document: str
) -> None:
    secrets_manager.answer(
        "GetSecretValue",
        answered_value(PASSWORD_SECRET, document.replace("PASSWORD", password.replace('"', "'"))),
    )

    with pytest.raises(TabroomCredentialsUnreadable) as unreadable:
        TabroomPasswordSecret(ManagedSecret(secrets_manager.client, PASSWORD_SECRET)).read()

    assert unreadable.value.__cause__ is None
    assert_never_shown(str(unreadable.value), {"the password": password.replace('"', "'")}, "the error")
