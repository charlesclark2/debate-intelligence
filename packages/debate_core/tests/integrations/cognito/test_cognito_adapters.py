"""The pilot's Cognito, audit and parameter adapters, against stubbed clients and a fake transport.

boto3 clients run under botocore's `Stubber`, which fails a test on any call whose parameters differ
from the ones written here. The OAuth client talks to a recorded fake transport. Nothing leaves the
process. Every value is synthetic.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import boto3
import pytest
from botocore.stub import ANY, Stubber
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
from cryptography.hazmat.primitives.hashes import SHA256

from debate_core.application.errors import (
    AlreadyExists,
    NotFound,
    StoreAccessDenied,
    StoreCredentialsExpired,
    StoreUnavailable,
)
from debate_core.application.ports.tub import CodeRefused, TokenRefused
from debate_core.application.tub.audit import AuditAction, AuditRecord
from debate_core.application.tub.identity import Role
from debate_core.application.tub.sessions import new_sign_in_transaction
from debate_core.integrations.cloudwatch_audit import CloudWatchAuditSink
from debate_core.integrations.cognito import (
    CognitoIdTokenVerifier,
    CognitoOAuthClient,
    CognitoSelfService,
    HttpResponse,
    PublishedKeySet,
    UrllibTransport,
    issuer_for,
)
from debate_core.integrations.cognito.errors import translate_cognito_error
from debate_core.integrations.parameter_store import read_secure_parameter

if TYPE_CHECKING:
    from mypy_boto3_cognito_idp import CognitoIdentityProviderClient
    from mypy_boto3_logs import CloudWatchLogsClient
    from mypy_boto3_ssm import SSMClient

NOW = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)
ISSUER = issuer_for("us-east-1", "us-east-1_SyntheticPool")
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _session() -> boto3.session.Session:
    return boto3.session.Session(
        aws_access_key_id="synthetic", aws_secret_access_key="synthetic", region_name="us-east-1"
    )


# `Session.client` is overloaded per service, and strict mode reports the overload set as partly
# unknown even where the stubs type the service. Narrowed to these three lines.
def _cognito_client() -> CognitoIdentityProviderClient:
    return _session().client("cognito-idp")  # pyright: ignore[reportUnknownMemberType]


def _logs_client() -> CloudWatchLogsClient:
    return _session().client("logs")  # pyright: ignore[reportUnknownMemberType]


def _ssm_client() -> SSMClient:
    return _session().client("ssm")  # pyright: ignore[reportUnknownMemberType]


@pytest.fixture
def cognito() -> Iterator[tuple[Any, Stubber]]:
    client = _cognito_client()
    with Stubber(client) as stubber:
        yield client, stubber
        stubber.assert_no_pending_responses()


# --------------------------------------------------------------------------------------------
# The token-authorized API
# --------------------------------------------------------------------------------------------


def test_standing_reads_the_factors_and_the_email(cognito: tuple[Any, Stubber]) -> None:
    client, stubber = cognito
    stubber.add_response(
        "get_user",
        {
            "Username": "debater.one",
            "UserAttributes": [
                {"Name": "sub", "Value": "sub-1"},
                {"Name": "email", "Value": "debater.one@example.test"},
                {"Name": "email_verified", "Value": "true"},
            ],
            "UserMFASettingList": ["SOFTWARE_TOKEN_MFA", "EMAIL_OTP"],
        },
        {"AccessToken": "access-1"},
    )

    standing = CognitoSelfService(client=client).standing("access-1")

    assert (
        standing.has_authenticator,
        standing.email,
        standing.email_verified,
        standing.email_factor_enabled,
    ) == (
        True,
        "debater.one@example.test",
        True,
        True,
    )


def test_an_account_with_neither_factor_nor_email(cognito: tuple[Any, Stubber]) -> None:
    client, stubber = cognito
    stubber.add_response(
        "get_user", {"Username": "debater.one", "UserAttributes": []}, {"AccessToken": "access-1"}
    )

    standing = CognitoSelfService(client=client).standing("access-1")

    assert (standing.has_authenticator, standing.email, standing.email_verified) == (False, None, False)


def test_a_revoked_access_token_is_a_refused_token(cognito: tuple[Any, Stubber]) -> None:
    client, stubber = cognito
    stubber.add_client_error("get_user", "NotAuthorizedException")

    with pytest.raises(TokenRefused):
        CognitoSelfService(client=client).standing("access-1")


def test_beginning_an_authenticator_returns_its_secret_wrapped(cognito: tuple[Any, Stubber]) -> None:
    client, stubber = cognito
    stubber.add_response(
        "associate_software_token", {"SecretCode": "JBSWY3DPEHPK3PXP"}, {"AccessToken": "access-1"}
    )

    secret = CognitoSelfService(client=client).begin_authenticator("access-1")

    assert secret.reveal() == "JBSWY3DPEHPK3PXP"
    assert "JBSWY3DPEHPK3PXP" not in repr(secret)


@pytest.mark.parametrize(
    ("answer", "refused"),
    [({"Status": "SUCCESS"}, False), ({"Status": "ERROR"}, True), ("CodeMismatchException", True)],
)
def test_confirming_an_authenticator(cognito: tuple[Any, Stubber], answer: Any, refused: bool) -> None:
    client, stubber = cognito
    expected = {"AccessToken": "access-1", "UserCode": "424242", "FriendlyDeviceName": "Authenticator app"}
    if isinstance(answer, str):
        stubber.add_client_error("verify_software_token", answer, expected_params=expected)
    else:
        stubber.add_response("verify_software_token", answer, expected)

    if refused:
        with pytest.raises(CodeRefused):
            CognitoSelfService(client=client).confirm_authenticator("access-1", "424242")
    else:
        CognitoSelfService(client=client).confirm_authenticator("access-1", "424242")


@pytest.mark.parametrize(
    ("authenticator", "email", "expected"),
    [
        (
            True,
            True,
            {
                "SoftwareTokenMfaSettings": {"Enabled": True, "PreferredMfa": False},
                "EmailMfaSettings": {"Enabled": True, "PreferredMfa": False},
            },
        ),
        (
            True,
            False,
            {
                "SoftwareTokenMfaSettings": {"Enabled": True, "PreferredMfa": True},
                "EmailMfaSettings": {"Enabled": False, "PreferredMfa": False},
            },
        ),
        (False, True, {"EmailMfaSettings": {"Enabled": True, "PreferredMfa": True}}),
    ],
)
def test_second_factors_with_both_prefer_neither(
    cognito: tuple[Any, Stubber], authenticator: bool, email: bool, expected: dict[str, Any]
) -> None:
    client, stubber = cognito
    stubber.add_response("set_user_mfa_preference", {}, {"AccessToken": "access-1", **expected})

    CognitoSelfService(client=client).set_second_factors("access-1", authenticator=authenticator, email=email)


def test_the_backup_email_is_set_verified_and_removed_with_the_access_token(
    cognito: tuple[Any, Stubber],
) -> None:
    client, stubber = cognito
    stubber.add_response(
        "update_user_attributes",
        {},
        {
            "AccessToken": "access-1",
            "UserAttributes": [{"Name": "email", "Value": "debater.one@example.test"}],
        },
    )
    stubber.add_response(
        "verify_user_attribute", {}, {"AccessToken": "access-1", "AttributeName": "email", "Code": "135790"}
    )
    stubber.add_response(
        "delete_user_attributes", {}, {"AccessToken": "access-1", "UserAttributeNames": ["email"]}
    )
    service = CognitoSelfService(client=client)

    service.set_backup_email("access-1", "debater.one@example.test")
    service.confirm_backup_email("access-1", "135790")
    service.remove_backup_email("access-1")


def test_a_wrong_email_code_is_a_refused_email_code(cognito: tuple[Any, Stubber]) -> None:
    client, stubber = cognito
    stubber.add_client_error("verify_user_attribute", "ExpiredCodeException")

    with pytest.raises(CodeRefused) as refused:
        CognitoSelfService(client=client).confirm_backup_email("access-1", "135790")

    assert refused.value.what == "email"


# --------------------------------------------------------------------------------------------
# Error translation
# --------------------------------------------------------------------------------------------


def _client_error(code: str) -> Exception:
    from botocore.exceptions import ClientError

    return ClientError({"Error": {"Code": code, "Message": "debater.one secret"}}, "Operation")


@pytest.mark.parametrize(
    ("code", "kind", "token_authorized"),
    [
        ("UserNotFoundException", NotFound, False),
        ("UserNotFoundException", TokenRefused, True),
        ("UsernameExistsException", AlreadyExists, False),
        ("NotAuthorizedException", StoreAccessDenied, False),
        ("NotAuthorizedException", TokenRefused, True),
        ("AccessDeniedException", StoreAccessDenied, False),
        ("ExpiredTokenException", StoreCredentialsExpired, False),
        ("CodeMismatchException", CodeRefused, True),
        ("TooManyRequestsException", StoreUnavailable, False),
        ("SomethingNewException", StoreUnavailable, False),
    ],
)
def test_each_cognito_code_becomes_a_domain_error_without_cognitos_message(
    code: str, kind: type[Exception], token_authorized: bool
) -> None:
    error = translate_cognito_error(
        _client_error(code),
        "AdminGetUser",
        profile="debate-dev-tub-accounts",
        username="debater.one",
        token_authorized=token_authorized,
    )

    assert isinstance(error, kind)
    assert "secret" not in str(error)


# --------------------------------------------------------------------------------------------
# The OAuth client and the ID-token checks
# --------------------------------------------------------------------------------------------


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _jwk(key_id: str = "key-1") -> dict[str, str]:
    numbers = KEY.public_key().public_numbers()
    return {
        "kid": key_id,
        "kty": "RSA",
        "use": "sig",
        "n": _b64url(numbers.n.to_bytes(256, "big")),
        "e": _b64url(numbers.e.to_bytes(3, "big")),
    }


def _id_token(**claims: object) -> str:
    body = {
        "iss": ISSUER,
        "aud": "synthetic-client-id",
        "token_use": "id",
        "sub": "sub-1",
        "cognito:username": "debater.one",
        "cognito:groups": ["student"],
        "exp": int(NOW.timestamp()) + 300,
        **claims,
    }
    head = _b64url(json.dumps({"alg": "RS256", "kid": "key-1"}).encode())
    payload = _b64url(json.dumps(body).encode())
    signature = KEY.sign(f"{head}.{payload}".encode(), PKCS1v15(), SHA256())
    return f"{head}.{payload}.{_b64url(signature)}"


@dataclass
class RecordedTransport:
    answers: list[HttpResponse] = field(default_factory=lambda: [])
    posts: list[tuple[str, dict[str, str], dict[str, str]]] = field(default_factory=lambda: [])
    gets: list[str] = field(default_factory=lambda: [])
    keys: list[dict[str, str]] = field(default_factory=lambda: [_jwk()])

    def post_form(self, url: str, fields: Mapping[str, str], *, headers: Mapping[str, str]) -> HttpResponse:
        self.posts.append((url, dict(fields), dict(headers)))
        return self.answers.pop(0)

    def get(self, url: str) -> HttpResponse:
        self.gets.append(url)
        return HttpResponse(200, json.dumps({"keys": self.keys}).encode())


def oauth(transport: RecordedTransport) -> CognitoOAuthClient:
    return CognitoOAuthClient(
        login_origin="https://auth.tub.example.test",
        public_origin="https://tub.example.test",
        client_id="synthetic-client-id",
        client_secret="synthetic-client-secret",
        id_tokens=CognitoIdTokenVerifier(
            issuer=ISSUER,
            client_id="synthetic-client-id",
            key_set=PublishedKeySet(issuer=ISSUER, transport=transport),
            clock=lambda: NOW,
        ),
        transport=transport,
    )


def _tokens(**extra: object) -> HttpResponse:
    return HttpResponse(
        200, json.dumps({"id_token": _id_token(), "access_token": "access-1", **extra}).encode()
    )


def test_the_authorization_url_asks_for_the_code_flow_with_s256(monkeypatch: pytest.MonkeyPatch) -> None:
    transaction = new_sign_in_transaction("/", NOW)

    url = oauth(RecordedTransport()).authorization_url(transaction)

    assert url.startswith(
        "https://auth.tub.example.test/oauth2/authorize?response_type=code&client_id=synthetic-client-id"
    )
    assert f"code_challenge={transaction.code_challenge}" in url
    assert "code_challenge_method=S256" in url and f"state={transaction.state}" in url
    assert "scope=openid+aws.cognito.signin.user.admin" in url


def test_the_exchange_sends_the_verifier_and_the_client_secret() -> None:
    transport = RecordedTransport(answers=[_tokens(refresh_token="refresh-1")])

    issued = oauth(transport).exchange_code("code-1", "verifier-1")

    url, fields, headers = transport.posts[0]
    assert url == "https://auth.tub.example.test/oauth2/token"
    assert fields == {
        "grant_type": "authorization_code",
        "client_id": "synthetic-client-id",
        "code": "code-1",
        "redirect_uri": "https://tub.example.test/auth/callback",
        "code_verifier": "verifier-1",
    }
    assert headers == {
        "Authorization": "Basic " + base64.b64encode(b"synthetic-client-id:synthetic-client-secret").decode()
    }
    assert (issued.identity.subject, issued.identity.groups, issued.refresh_token) == (
        "sub-1",
        frozenset({"student"}),
        "refresh-1",
    )


def test_an_exchange_without_a_refresh_token_is_refused() -> None:
    with pytest.raises(TokenRefused, match="no refresh token"):
        oauth(RecordedTransport(answers=[_tokens()])).exchange_code("code-1", "verifier-1")


@pytest.mark.parametrize(
    ("answer", "kind", "reason"),
    [
        (
            HttpResponse(400, b'{"error":"invalid_grant","error_description":"debater.one"}'),
            TokenRefused,
            "invalid_grant",
        ),
        (HttpResponse(400, b'{"error":"made_up"}'), TokenRefused, "HTTP 400"),
        (HttpResponse(400, b"not json"), TokenRefused, "HTTP 400"),
        (HttpResponse(503, b""), StoreUnavailable, "503"),
    ],
)
def test_a_refused_exchange_names_only_a_standard_error_code(
    answer: HttpResponse, kind: type[Exception], reason: str
) -> None:
    with pytest.raises(kind) as refused:
        oauth(RecordedTransport(answers=[answer])).exchange_code("code-1", "verifier-1")

    assert reason in str(refused.value)
    assert "debater.one" not in str(refused.value)


def test_a_refresh_sends_the_refresh_token_and_keeps_no_new_one() -> None:
    transport = RecordedTransport(answers=[_tokens()])

    issued = oauth(transport).refresh("refresh-1")

    assert transport.posts[0][1] == {
        "grant_type": "refresh_token",
        "client_id": "synthetic-client-id",
        "refresh_token": "refresh-1",
    }
    assert issued.refresh_token is None


def test_revoke_and_the_logout_url() -> None:
    transport = RecordedTransport(answers=[HttpResponse(200, b"")])
    client = oauth(transport)

    client.revoke("refresh-1")

    assert transport.posts[0][:2] == (
        "https://auth.tub.example.test/oauth2/revoke",
        {"token": "refresh-1", "client_id": "synthetic-client-id"},
    )
    assert client.sign_out_url() == (
        "https://auth.tub.example.test/logout?client_id=synthetic-client-id&logout_uri=https%3A%2F%2Ftub.example.test%2Fsigned-out"
    )


def test_the_key_set_is_fetched_once_and_again_only_for_a_key_it_does_not_hold() -> None:
    transport = RecordedTransport(answers=[_tokens(refresh_token="r"), _tokens(refresh_token="r")])
    client = oauth(transport)

    client.exchange_code("code-1", "verifier-1")
    client.exchange_code("code-2", "verifier-2")

    assert transport.gets == [f"{ISSUER}/.well-known/jwks.json"]


def test_a_rotated_in_key_is_found_by_fetching_the_key_set_again() -> None:
    transport = RecordedTransport(keys=[_jwk("an-older-key")])
    key_set = PublishedKeySet(issuer=ISSUER, transport=transport)
    verifier = CognitoIdTokenVerifier(
        issuer=ISSUER, client_id="synthetic-client-id", key_set=key_set, clock=lambda: NOW
    )
    assert set(key_set.keys()) == {"an-older-key"}
    transport.keys = [_jwk("an-older-key"), _jwk("key-1")]

    identity = verifier.verify(_id_token())

    assert identity.subject == "sub-1"
    assert len(transport.gets) == 2


def test_keys_that_are_not_rsa_signing_keys_are_ignored() -> None:
    transport = RecordedTransport(
        keys=[
            {"kid": "ec", "kty": "EC"},
            {**_jwk("enc"), "use": "enc"},
            {"kid": "bad", "kty": "RSA", "n": "!", "e": "AQAB"},
        ]
    )

    assert dict(PublishedKeySet(issuer=ISSUER, transport=transport).keys()) == {}


def test_the_transport_speaks_only_https() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        UrllibTransport().get("http://auth.tub.example.test/oauth2/token")


# --------------------------------------------------------------------------------------------
# The audit log and the parameters
# --------------------------------------------------------------------------------------------


RECORD = AuditRecord(
    time=NOW,
    action=AuditAction.BACKUP_EMAIL_ADDED,
    actor_role=Role.STUDENT,
    actor_subject="sub-1",
    account_subject="sub-1",
)


def test_the_function_creates_its_stream_once_then_appends() -> None:
    client = _logs_client()
    with Stubber(client) as stubber:
        stubber.add_response(
            "create_log_stream", {}, {"logGroupName": "debate-dev-tub-audit", "logStreamName": "tub-app-x"}
        )
        for _ in range(2):
            stubber.add_response(
                "put_log_events",
                {},
                {
                    "logGroupName": "debate-dev-tub-audit",
                    "logStreamName": "tub-app-x",
                    "logEvents": [{"timestamp": int(NOW.timestamp() * 1000), "message": RECORD.to_json()}],
                },
            )
        sink = CloudWatchAuditSink(
            client=client, log_group="debate-dev-tub-audit", log_stream="tub-app-x", create_stream=True
        )

        sink.record(RECORD)
        sink.record(RECORD)

        stubber.assert_no_pending_responses()


def test_a_stream_another_environment_created_is_used_as_it_is() -> None:
    client = _logs_client()
    with Stubber(client) as stubber:
        stubber.add_client_error("create_log_stream", "ResourceAlreadyExistsException")
        stubber.add_response(
            "put_log_events", {}, {"logGroupName": "g", "logStreamName": "s", "logEvents": ANY}
        )

        CloudWatchAuditSink(client=client, log_group="g", log_stream="s", create_stream=True).record(RECORD)


@pytest.mark.parametrize(
    ("code", "kind"),
    [
        ("AccessDeniedException", StoreAccessDenied),
        ("ExpiredTokenException", StoreCredentialsExpired),
        ("ServiceUnavailableException", StoreUnavailable),
    ],
)
def test_a_failed_audit_write_is_a_store_error(code: str, kind: type[Exception]) -> None:
    client = _logs_client()
    with Stubber(client) as stubber:
        stubber.add_client_error("put_log_events", code)

        with pytest.raises(kind):
            CloudWatchAuditSink(
                client=client, log_group="g", log_stream="tub-users", create_stream=False
            ).record(RECORD)


def test_a_parameter_is_read_decrypted_by_name() -> None:
    client = _ssm_client()
    with Stubber(client) as stubber:
        stubber.add_response(
            "get_parameter",
            {"Parameter": {"Name": "/debate-dev-tub/client-secret", "Value": "synthetic-client-secret"}},
            {"Name": "/debate-dev-tub/client-secret", "WithDecryption": True},
        )

        assert read_secure_parameter(client, "/debate-dev-tub/client-secret") == "synthetic-client-secret"


@pytest.mark.parametrize(
    ("code", "kind"),
    [
        ("ParameterNotFound", NotFound),
        ("AccessDeniedException", StoreAccessDenied),
        ("InternalServerError", StoreUnavailable),
    ],
)
def test_a_parameter_that_cannot_be_read(code: str, kind: type[Exception]) -> None:
    client = _ssm_client()
    with Stubber(client) as stubber:
        stubber.add_client_error("get_parameter", code)

        with pytest.raises(kind):
            read_secure_parameter(client, "/debate-dev-tub/cookie-keys")
