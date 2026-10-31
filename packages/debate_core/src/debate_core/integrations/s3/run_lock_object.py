"""The bucket's run lock object, changed only by S3 conditional writes (ADR-0020 (4), `v1-e40-t04`).

:class:`~debate_core.application.ports.run_lock.LockObjectStore` over one key of the evidence
bucket, `reports/sync/run-lock.json`. Its every write is a `PutObject` with a condition:

* `If-None-Match: *` to create it, which S3 refuses with `412` when an object is there (a delete
  marker counts as absent);
* `If-Match: <entity tag>` to change it, refused with `412` when the object is another version and
  `404` when it is gone; two writes racing may get `409`.

Each of those refusals is :class:`~debate_core.application.ports.run_lock.LockObjectChanged`.
Everything else botocore raises is translated as every adapter here translates it
(:mod:`debate_core.integrations.s3.errors`). Conditional writes need no grant beyond `s3:PutObject`,
which the everyday evidence policy holds on the whole bucket.

## Whether the object is there

A `GetObject` of a missing key answers `404` only to a caller allowed `s3:ListBucket` on that key.
The everyday policy allows listing per prefix, which a `GetObject` carries no prefix for, so it
answers `403`. :meth:`S3LockObject.read` therefore asks a listing of the key itself whenever the read
is refused, and only a key the listing does not show is absent. A refusal of an object that is there
stays a refusal.

## Encryption

As for every upload here: the bucket's default, or the key the composition root names. The bucket
policy refuses an upload under another key.

This adapter's client is never given the write fence
(:mod:`debate_core.integrations.s3.fencing`): its writes are the lock's own.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from botocore.exceptions import ClientError

from debate_core.application.errors import NotFound, StoreAccessDenied
from debate_core.application.ports.run_lock import LockObject, LockObjectChanged
from debate_core.integrations.s3.errors import S3Call, mapped_s3_errors

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

__all__ = ["S3LockObject"]

_ENTITY: Final = "run lock"

#: The answers S3 gives a conditional write that did not hold, and what each means here.
_REFUSED_CONDITIONS: Final = {
    "PreconditionFailed": "another runner changed it first",
    "412": "another runner changed it first",
    "NoSuchKey": "it is not there",
    "404": "it is not there",
    "ConditionalRequestConflict": "another write raced this one",
    "409": "another write raced this one",
}


class S3LockObject:
    """The run lock object in one bucket. See the module docstring.

    Args:
        bucket: The home environment's evidence bucket.
        key: The lock's key, `reports/sync/run-lock.json`.
        client: A client of its own, never one the write fence is registered on.
        profile, profile_setting: As for every adapter here: what an error names.
        login_hint: What a missing or expired session names instead of `aws sso login`, or `None` for
            that command (`v1-e40-t28`). The composition root gives the cloud run's.
        kms_key_id: The evidence key, to state on each write, or `None` for the bucket's default.
    """

    def __init__(
        self,
        *,
        bucket: str,
        key: str,
        client: S3Client,
        profile: str | None = None,
        profile_setting: str | None = None,
        login_hint: str | None = None,
        kms_key_id: str | None = None,
    ) -> None:
        self._bucket = bucket
        self._key = key
        self._client = client
        self._profile = profile
        self._profile_setting = profile_setting
        self._login_hint = login_hint
        self._kms_key_id = kms_key_id

    @property
    def key(self) -> str:
        return self._key

    def read(self) -> LockObject | None:
        try:
            with mapped_s3_errors(self._call("GetObject")):
                response = self._client.get_object(Bucket=self._bucket, Key=self._key)
                body = response["Body"].read()
        except NotFound as absent:
            if absent.entity != _ENTITY:
                raise
            return None
        except StoreAccessDenied:
            if not self._listed():
                return None
            raise
        return LockObject(body=body, etag=str(response["ETag"]))

    def create(self, body: bytes) -> str:
        return self._put(body, {"IfNoneMatch": "*"})

    def replace(self, body: bytes, *, etag: str) -> str:
        return self._put(body, {"IfMatch": etag})

    def _put(self, body: bytes, condition: dict[str, str]) -> str:
        arguments: dict[str, Any] = {
            "Bucket": self._bucket,
            "Key": self._key,
            "Body": body,
            "ContentType": "application/json",
            "ChecksumAlgorithm": "SHA256",
            **condition,
            **self._encryption_arguments(),
        }
        try:
            response = self._client.put_object(**arguments)
        except ClientError as refused:
            reason = _REFUSED_CONDITIONS.get(_code_of(refused))
            if reason is not None:
                raise LockObjectChanged(self._key, reason) from refused
            with mapped_s3_errors(self._call("PutObject")):
                raise
        except Exception:
            with mapped_s3_errors(self._call("PutObject")):
                raise
        return str(response["ETag"])

    def _listed(self) -> bool:
        with mapped_s3_errors(self._call("ListObjectsV2")):
            listing = self._client.list_objects_v2(Bucket=self._bucket, Prefix=self._key, MaxKeys=1)
        return any(item.get("Key") == self._key for item in listing.get("Contents", []))

    def _encryption_arguments(self) -> dict[str, str]:
        if self._kms_key_id is None:
            return {}
        return {"ServerSideEncryption": "aws:kms", "SSEKMSKeyId": self._kms_key_id}

    def _call(self, operation: str) -> S3Call:
        return S3Call(
            operation=operation,
            bucket=self._bucket,
            entity=_ENTITY,
            key=self._key,
            s3_key=self._key,
            profile=self._profile,
            profile_setting=self._profile_setting,
            given_login_hint=self._login_hint,
        )


def _code_of(error: ClientError) -> str:
    """The error's code, or its HTTP status when S3 sent no body (as for a `HEAD`)."""
    code = str(error.response.get("Error", {}).get("Code", ""))
    if code:
        return code
    return str(error.response.get("ResponseMetadata", {}).get("HTTPStatusCode", ""))
