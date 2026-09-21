"""Where `botocore` exceptions stop and :mod:`debate_core.application.errors` begins.

This module is the entire reason a use case can catch
:class:`~debate_core.application.errors.NotFound` and not care whether the evidence store is a
directory or a bucket. Every call the S3 adapters make runs inside
:func:`mapped_s3_errors`, so a `ClientError`, a missing credential or an expired SSO session is
translated here and nowhere else (architecture proposal §6).

## What maps to what

Everything in this table is in :mod:`debate_core.application.errors`:

| What S3 or botocore said | What a caller gets |
|---|---|
| `NoSuchKey`, `NotFound`, HTTP 404 | `NotFound` |
| `NoSuchBucket` | `NotFound`, naming the bucket rather than the key |
| `AccessDenied`, HTTP 403, `KMS.AccessDeniedException` | `StoreAccessDenied` |
| An expired or absent SSO token, no credentials at all | `StoreCredentialsExpired` |
| `ExpiredToken`, `RequestExpired`, `InvalidClientTokenId` | `StoreCredentialsExpired` |
| A 5xx, a throttle, a timeout, a connection that never opened | `StoreUnavailable` |
| Any other response code | `StoreUnavailable`, carrying the code |

The last row is the one that matters most. An unrecognised code is still translated, because the
promise in `application/errors.py` is that *no* `ClientError` reaches a service — not "no `ClientError`
we thought of". The original exception stays on `__cause__` for the log.

## Why an expired session gets its own error

`aws sso login` is the whole fix, and it is the most common failure an operator will hit: an SSO
session lasts hours, and the sync of a corpus takes longer than one sitting. So the expired case is
:class:`~debate_core.application.errors.StoreCredentialsExpired` with the exact command in
:attr:`~debate_core.application.errors.StoreCredentialsExpired.hint`, and
`v1-e29-t05-evidence-sync-cli` prints that one line instead of a botocore traceback (its ac4).

## What never goes in a message

The operation, the bucket, the key and the response code. Never a credential, a session token, a
presigned URL or a byte of an object. Every message this module builds is assembled from the fields
listed in :class:`S3Call`, which is why none of them can contain a secret: the caller does not have
one to pass.
"""

from __future__ import annotations

import re
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass

from boto3.exceptions import S3UploadFailedError
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    CredentialRetrievalError,
    NoCredentialsError,
    PartialCredentialsError,
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

__all__ = [
    "ACCESS_DENIED_CODES",
    "EXPIRED_CREDENTIAL_CODES",
    "NOT_FOUND_CODES",
    "S3Call",
    "mapped_s3_errors",
    "translate_s3_error",
]

NOT_FOUND_CODES = frozenset({"NoSuchKey", "NoSuchVersion", "NotFound", "404"})
"""Response codes that mean the object is not there.

`HeadObject` is the reason `"404"` is in the list beside `"NoSuchKey"`: a `HEAD` has no response
body for S3 to put an error code in, so botocore reports the status code as the code.
"""

ACCESS_DENIED_CODES = frozenset(
    {
        "AccessDenied",
        "AccessDeniedException",
        "AllAccessDisabled",
        "InvalidAccessKeyId",
        "SignatureDoesNotMatch",
        "KMS.AccessDeniedException",
        "KMSAccessDeniedException",
        "403",
    }
)
"""Response codes that mean "you are who you say you are, and you may not do this".

The two KMS codes are here because the evidence buckets are encrypted with a customer-managed key
(`v1-e29-t03`): a credential allowed to `GetObject` but not to `kms:Decrypt` fails on the key, not
on the bucket, and an operator reading "not allowed to GetObject" would go looking in the wrong
policy. The message names the resource the adapter passed, and
:meth:`~debate_core.application.errors.StoreAccessDenied.hint` is where the adapter says which grant
is missing.
"""

EXPIRED_CREDENTIAL_CODES = frozenset(
    {
        "ExpiredToken",
        "ExpiredTokenException",
        "RequestExpired",
        "InvalidClientTokenId",
        "UnrecognizedClientException",
        "TokenRefreshRequired",
    }
)
"""Response codes that mean the credentials were valid and are not any more.

Distinct from :data:`ACCESS_DENIED_CODES` because the fix is different: log in again, rather than
change a policy. botocore usually catches an expired SSO session before the request is signed and
raises :class:`~botocore.exceptions.UnauthorizedSSOTokenError` instead, but a session that expires
*between* signing and the response comes back as one of these.
"""

#: Pulls the response code out of the message `boto3` wraps a failed transfer in. `upload_file` and
#: `download_file` run inside boto3's transfer manager, which turns a `ClientError` raised in one of
#: its worker threads into :class:`~boto3.exceptions.S3UploadFailedError` with the original text —
#: "An error occurred (AccessDenied) when calling the CreateMultipartUpload operation…" — and no
#: `__cause__`. Reading the code back out is what keeps a multipart upload failing the same way a
#: single `PutObject` does, rather than as an untranslated boto3 exception.
_WRAPPED_RESPONSE_CODE = re.compile(r"An error occurred \(([A-Za-z0-9.]+)\)")


@dataclass(frozen=True, slots=True)
class S3Call:
    """What the adapter was doing, in the words an error message may use.

    Every field is something the adapter already knows from its own configuration or from the key it
    was handed, which is what makes it safe to put in a message: there is no credential here to
    leak, and an object's *contents* are never among these fields.
    """

    operation: str
    """The S3 operation, spelled as the API spells it: `"GetObject"`, `"PutObject"`, `"HeadObject"`."""

    bucket: str
    """The bucket the call was against."""

    entity: str
    """What a caller was looking for, for :class:`~debate_core.application.errors.NotFound`'s message:
    `"snapshot blob"`, `"evidence object"`."""

    key: str
    """The key *as the caller knows it* — a blob's digest, or an object key — not the full S3 key.

    A `NotFound` has to carry the key the caller passed in, because that is the one it can act on:
    the contract suite asserts `NotFound.key == the key it asked for`, and a caller that got the
    adapter's internal, prefixed spelling back could not match it against its own records.
    """

    s3_key: str | None = None
    """The full key inside the bucket, when the call named one. Used only in messages."""

    profile: str | None = None
    """The AWS profile the client was built with, for the `aws sso login` hint. Never a token."""

    @property
    def resource(self) -> str:
        """The thing acted on, as a message should name it: `s3://bucket/key`, or just the bucket."""
        return f"s3://{self.bucket}/{self.s3_key}" if self.s3_key else f"s3://{self.bucket}"

    @property
    def login_hint(self) -> str:
        """The command that refreshes the session, naming the profile when there is one."""
        if self.profile:
            return f"aws sso login --profile {self.profile}"
        return "aws sso login (or set AWS_PROFILE to the evidence profile for this environment)"


def translate_s3_error(error: BaseException, call: S3Call) -> DomainError:
    """Return the :mod:`~debate_core.application.errors` error that `error` means for `call`.

    Total and pure: every input produces an error object, and none is raised, so a caller that wants
    to log before raising can and so this can be unit-tested one response code at a time without a
    bucket. Callers normally use :func:`mapped_s3_errors` rather than calling it directly.
    """
    if isinstance(error, ClientError):
        return _translate_response_code(_response_code_of(error), error, call)
    if isinstance(error, S3UploadFailedError):
        # A transfer that failed inside boto3's thread pool; the response code is in the text.
        wrapped = _WRAPPED_RESPONSE_CODE.search(str(error))
        if wrapped is not None:
            return _translate_response_code(wrapped.group(1), error, call)
        return StoreUnavailable(call.operation, call.resource, str(error))
    if isinstance(
        error,
        UnauthorizedSSOTokenError
        | SSOTokenLoadError
        | TokenRetrievalError
        | NoCredentialsError
        | PartialCredentialsError
        | CredentialRetrievalError,
    ):
        return StoreCredentialsExpired(
            f"the AWS session for {call.resource} is not usable", hint=call.login_hint
        )
    if isinstance(error, ProfileNotFound):
        # Not an expired session but the same shape of fix: the profile has to exist before the
        # login can. Named separately so the hint says which one is missing.
        return StoreCredentialsExpired(
            f"AWS profile {call.profile!r} is not configured",
            hint=f"aws configure sso --profile {call.profile}" if call.profile else "aws configure sso",
        )
    # Everything else botocore raises — timeouts, connection failures, endpoint resolution — means
    # the store did not answer. So does anything reaching here that is not a botocore exception at
    # all: :func:`mapped_s3_errors` never hands one over, and a translation that refused to produce
    # an error would put a `ClientError`-shaped hole in the promise this module exists to keep.
    return StoreUnavailable(call.operation, call.resource, str(error) or type(error).__name__)


@contextmanager
def mapped_s3_errors(call: S3Call) -> Generator[None, None, None]:
    """Run a block of S3 calls, translating anything botocore raises out of it.

    The adapters wrap every call in this::

        with mapped_s3_errors(S3Call("GetObject", bucket, "snapshot blob", key, s3_key=full_key)):
            response = client.get_object(Bucket=bucket, Key=full_key)

    Anything this module does not recognise — a `ValueError` from the adapter's own code, a
    `KeyboardInterrupt` — passes through untouched, because translating an error nobody mapped would
    turn a bug in the adapter into a "store unavailable" that an operator would go and investigate in
    the wrong place.
    """
    try:
        yield
    except (ClientError, S3UploadFailedError, BotoCoreError) as error:
        raise translate_s3_error(error, call) from error


def _response_code_of(error: ClientError) -> str:
    """The `Error.Code` S3 returned, or the HTTP status as a string when there was no body."""
    response = error.response
    code = response.get("Error", {}).get("Code", "")
    if code:
        return code
    status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return str(status) if status is not None else ""


def _translate_response_code(code: str, error: BaseException, call: S3Call) -> DomainError:
    """Map one response code, whether it arrived on a `ClientError` or inside a wrapped transfer."""
    if code in NOT_FOUND_CODES:
        return NotFound(call.entity, call.key)
    if code == "NoSuchBucket":
        # Not the caller's key that is missing but the store itself: almost always the wrong
        # environment or a bucket name that was typed rather than read from Terraform's outputs.
        return NotFound("evidence bucket", call.bucket)
    if code in EXPIRED_CREDENTIAL_CODES:
        return StoreCredentialsExpired(
            f"the AWS session for {call.resource} has expired", hint=call.login_hint
        )
    if code in ACCESS_DENIED_CODES:
        return StoreAccessDenied(call.operation, call.resource, hint=_denial_hint(code, call))
    return StoreUnavailable(call.operation, call.resource, f"{code or type(error).__name__}")


def _denial_hint(code: str, call: S3Call) -> str | None:
    """One line about which grant is missing, for the denials where that is knowable."""
    if code.startswith("KMS") or code.startswith("KMS."):
        return "the credential may read the bucket but not use its KMS key; it needs kms:Decrypt"
    if code == "AccessDenied" and call.s3_key is None:
        # Listing the bucket root is denied by design; the grant is per prefix (v1-e29-t03).
        return "listing is granted per prefix, not at the bucket root; list one prefix at a time"
    return None
