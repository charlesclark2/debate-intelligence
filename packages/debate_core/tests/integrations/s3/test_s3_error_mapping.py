"""Every botocore failure becomes a `debate_core.application.errors` type, one response code at a time.

:func:`~debate_core.integrations.s3.errors.translate_s3_error` is a pure function, so this module
needs no bucket and no moto: it builds the exception botocore would have raised and checks what a use
case would have caught. The adapters' own tests cover that they route their calls through it at all.

The rule being protected is the one in `application/errors.py`: **no `ClientError` reaches a service**
— not "none that we thought of". So the last test here is the one that matters most, and it is about a
response code nobody has written a translation for.
"""

from __future__ import annotations

import pytest
from boto3.exceptions import S3UploadFailedError
from botocore.exceptions import (
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
    NoCredentialsError,
    ProfileNotFound,
    SSOTokenLoadError,
    TokenRetrievalError,
    UnauthorizedSSOTokenError,
)

from debate_core.application.errors import (
    DomainError,
    NotFound,
    StoreAccessDenied,
    StoreCredentialsExpired,
    StoreUnavailable,
)
from debate_core.integrations.s3 import S3Call, mapped_s3_errors, translate_s3_error

BUCKET = "debate-test-evidence-moto"
BLOB_KEY = "ab" * 32
S3_KEY = f"raw/caselist/hsld26/sha256/ab/ab/{BLOB_KEY}"
PROFILE = "debate-dev-evidence"


@pytest.fixture
def call() -> S3Call:
    """A `GetObject` on one blob, with a profile, which is the common case."""
    return S3Call(
        operation="GetObject",
        bucket=BUCKET,
        entity="snapshot blob",
        key=BLOB_KEY,
        s3_key=S3_KEY,
        profile=PROFILE,
    )


def client_error(code: str, *, status: int = 400, operation: str = "GetObject") -> ClientError:
    """The exception botocore raises when S3 answers with `code`."""
    return ClientError(
        {
            "Error": {"Code": code, "Message": "irrelevant to the mapping"},
            "ResponseMetadata": {"HTTPStatusCode": status},
        },
        operation,
    )


class TestAMissingObject:
    @pytest.mark.parametrize("code", ["NoSuchKey", "NotFound", "404"])
    def test_every_spelling_of_absence_becomes_not_found(self, code: str, call: S3Call) -> None:
        refused = translate_s3_error(client_error(code, status=404), call)

        assert isinstance(refused, NotFound)
        assert refused.entity == "snapshot blob"
        assert refused.key == BLOB_KEY, "a NotFound must carry the key the caller passed in"

    def test_a_head_with_no_response_body_still_becomes_not_found(self, call: S3Call) -> None:
        """A `HEAD` has no body for S3 to put a code in, so botocore reports only the status."""
        response_without_an_error_block = ClientError(
            {"ResponseMetadata": {"HTTPStatusCode": 404}}, "HeadObject"
        )

        assert isinstance(translate_s3_error(response_without_an_error_block, call), NotFound)

    def test_a_missing_bucket_names_the_bucket_rather_than_the_key(self, call: S3Call) -> None:
        """The wrong environment, or a bucket name typed instead of read from Terraform's outputs."""
        refused = translate_s3_error(client_error("NoSuchBucket", status=404), call)

        assert isinstance(refused, NotFound)
        assert refused.entity == "evidence bucket"
        assert refused.key == BUCKET


class TestARefusedRequest:
    @pytest.mark.parametrize("code", ["AccessDenied", "403", "AllAccessDisabled", "InvalidAccessKeyId"])
    def test_a_denial_becomes_store_access_denied_naming_the_operation(
        self, code: str, call: S3Call
    ) -> None:
        refused = translate_s3_error(client_error(code, status=403), call)

        assert isinstance(refused, StoreAccessDenied)
        assert refused.operation == "GetObject"
        assert refused.resource == f"s3://{BUCKET}/{S3_KEY}"

    def test_a_kms_denial_says_the_key_is_the_problem_and_not_the_bucket(self, call: S3Call) -> None:
        """The buckets are encrypted with a customer-managed key, so this is a real and confusing case."""
        refused = translate_s3_error(client_error("KMS.AccessDeniedException", status=403), call)

        assert isinstance(refused, StoreAccessDenied)
        assert refused.hint is not None
        assert "kms:Decrypt" in refused.hint

    def test_a_denied_listing_says_listing_is_granted_per_prefix(self) -> None:
        """Listing the bucket root is denied by design (`v1-e29-t03`); the grant is per prefix."""
        listing = S3Call(operation="ListObjectsV2", bucket=BUCKET, entity="evidence object", key="")

        refused = translate_s3_error(client_error("AccessDenied", status=403), listing)

        assert isinstance(refused, StoreAccessDenied)
        assert refused.hint is not None
        assert "per prefix" in refused.hint


class TestASessionThatIsNoLongerUsable:
    """The most common failure an operator meets, and the one with a one-line fix."""

    @pytest.mark.parametrize(
        "error",
        [
            UnauthorizedSSOTokenError(),
            SSOTokenLoadError(error_msg="expired"),
            TokenRetrievalError(provider="sso", error_msg="expired"),
            NoCredentialsError(),
        ],
        ids=["unauthorized-sso-token", "token-not-loadable", "token-not-retrievable", "no-credentials"],
    )
    def test_botocore_giving_up_on_credentials_becomes_a_login_hint(
        self, error: Exception, call: S3Call
    ) -> None:
        refused = translate_s3_error(error, call)

        assert isinstance(refused, StoreCredentialsExpired)
        assert refused.hint == f"aws sso login --profile {PROFILE}"
        assert PROFILE in str(refused)

    @pytest.mark.parametrize("code", ["ExpiredToken", "RequestExpired", "InvalidClientTokenId"])
    def test_a_session_that_expired_mid_request_becomes_the_same_hint(
        self, code: str, call: S3Call
    ) -> None:
        """A session can expire between signing a request and reading the response."""
        refused = translate_s3_error(client_error(code, status=403), call)

        assert isinstance(refused, StoreCredentialsExpired)
        assert refused.hint == f"aws sso login --profile {PROFILE}"

    def test_a_missing_profile_is_reported_with_the_command_that_creates_it(self, call: S3Call) -> None:
        refused = translate_s3_error(ProfileNotFound(profile=PROFILE), call)

        assert isinstance(refused, StoreCredentialsExpired)
        assert refused.hint == f"aws configure sso --profile {PROFILE}"

    def test_without_a_profile_the_hint_still_says_something_actionable(self) -> None:
        """A role on an instance or a task has no profile; the message must not name an empty one."""
        no_profile = S3Call(operation="GetObject", bucket=BUCKET, entity="snapshot blob", key=BLOB_KEY)

        refused = translate_s3_error(UnauthorizedSSOTokenError(), no_profile)

        assert isinstance(refused, StoreCredentialsExpired)
        assert refused.hint is not None
        assert "AWS_PROFILE" in refused.hint


class TestAStoreThatDidNotAnswer:
    @pytest.mark.parametrize("code", ["InternalError", "ServiceUnavailable", "SlowDown"])
    def test_a_server_side_failure_becomes_store_unavailable(self, code: str, call: S3Call) -> None:
        refused = translate_s3_error(client_error(code, status=503), call)

        assert isinstance(refused, StoreUnavailable)
        assert code in str(refused)

    @pytest.mark.parametrize(
        "error",
        [
            EndpointConnectionError(endpoint_url="https://s3.us-east-1.amazonaws.com"),
            ConnectTimeoutError(endpoint_url="https://s3.us-east-1.amazonaws.com"),
        ],
        ids=["endpoint-unreachable", "connect-timeout"],
    )
    def test_never_reaching_s3_at_all_becomes_store_unavailable(
        self, error: Exception, call: S3Call
    ) -> None:
        assert isinstance(translate_s3_error(error, call), StoreUnavailable)

    def test_an_unrecognised_response_code_is_still_translated(self, call: S3Call) -> None:
        """The promise is that *no* `ClientError` reaches a service, including one nobody mapped."""
        refused = translate_s3_error(client_error("ACodeNobodyHasSeenYet"), call)

        assert isinstance(refused, DomainError)
        assert isinstance(refused, StoreUnavailable)
        assert "ACodeNobodyHasSeenYet" in str(refused)


class TestAFailedMultipartTransfer:
    """boto3 wraps an upload's `ClientError` in its own exception, with the code only in the text."""

    def test_a_wrapped_denial_maps_the_same_way_a_plain_one_does(self, call: S3Call) -> None:
        wrapped = S3UploadFailedError(
            "Failed to upload archive to bucket/key: An error occurred (AccessDenied) when calling "
            "the CreateMultipartUpload operation: Access Denied"
        )

        refused = translate_s3_error(wrapped, call)

        assert isinstance(refused, StoreAccessDenied)

    def test_a_wrapped_failure_with_no_recognisable_code_is_still_translated(
        self, call: S3Call
    ) -> None:
        refused = translate_s3_error(S3UploadFailedError("the transfer gave up"), call)

        assert isinstance(refused, StoreUnavailable)


class TestTheContextManagerTheAdaptersUse:
    def test_it_raises_the_translated_error_and_keeps_the_original_as_the_cause(
        self, call: S3Call
    ) -> None:
        """The original exception stays reachable for a log, and only for a log."""
        original = client_error("NoSuchKey", status=404)

        with pytest.raises(NotFound) as refused:
            with mapped_s3_errors(call):
                raise original

        assert refused.value.__cause__ is original

    def test_it_leaves_an_error_that_is_not_botocores_alone(self, call: S3Call) -> None:
        """A bug in the adapter must not arrive dressed as a store that is unavailable."""
        with pytest.raises(ValueError, match="a bug in the adapter"):
            with mapped_s3_errors(call):
                raise ValueError("a bug in the adapter")
