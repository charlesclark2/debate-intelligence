"""The pilot's published search index, read from the evidence bucket (`v1-e39-t06`).

The bucket implementation of
:class:`~debate_core.application.ports.search_index_source.SearchIndexSource`: three kinds of
`GetObject` under `reports/tub/search/`, the only calls the function's role allows there (ADR-0019,
The function's role). No `ListBucket`, so a missing key is refused as `AccessDenied` by S3 rather
than answered `NoSuchKey`; either way the holder gets a
:class:`~debate_core.application.errors.DomainError` and keeps what it has.

* The pointer is read with `If-None-Match` and the entity tag of the last read, and S3's `304`
  comes back as an unchanged :class:`~debate_core.application.ports.search_index_source.PointerRead`
  with no body.
* A manifest is read whole, up to the size the caller allows.
* The gzip object is streamed a megabyte at a time and never held whole.
* The suppression list, `manifests/_suppression/suppression-list.jsonl`, is read as the pointer is,
  by conditional GET (`v1-e39-t07`). The role may `s3:GetObject` that one key and nothing else under
  `manifests/`. A list that does not exist has no lines: S3 answers `NoSuchKey` only to a caller
  that may list, so to the function a missing list is `AccessDenied`, refused like any other failure.

Every call runs inside :func:`~debate_core.integrations.s3.errors.mapped_s3_errors`, so nothing
botocore raises leaves this module.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, Final

from botocore.exceptions import ClientError

from debate_core.application.ports.evidence_store import validate_object_key
from debate_core.application.caselist.suppression import SUPPRESSION_LIST_KEY
from debate_core.application.ports.search_index_source import SUPPRESSION_LIST_MAX_BYTES, PointerRead
from debate_core.domain.search_index import SEARCH_INDEX_POINTER_KEY
from debate_core.integrations.s3.client import build_s3_client
from debate_core.integrations.s3.errors import S3Call, mapped_s3_errors

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

__all__ = ["POINTER_MAX_BYTES", "S3SearchIndexSource"]

POINTER_MAX_BYTES: Final = 64 * 1024
"""A pointer is under a kilobyte; one far larger is not a pointer."""

_STREAM_CHUNK: Final = 1024 * 1024
_NOT_MODIFIED: Final = frozenset({"304", "NotModified"})
_NO_SUCH_KEY: Final = frozenset({"404", "NoSuchKey"})
_ENTITY: Final = "search index object"


class S3SearchIndexSource:
    """A :class:`~debate_core.application.ports.search_index_source.SearchIndexSource` on one bucket.

    Also the function's :class:`~debate_core.application.ports.search_index_source.SuppressionListSource`,
    on the same bucket and client.
    """

    def __init__(self, *, bucket: str, region: str | None = None, client: S3Client | None = None) -> None:
        self._bucket = bucket
        self._client = client if client is not None else build_s3_client(region=region)

    def read_pointer(self, *, if_none_match: str | None) -> PointerRead:
        arguments: dict[str, Any] = {"Bucket": self._bucket, "Key": SEARCH_INDEX_POINTER_KEY}
        if if_none_match is not None:
            arguments["IfNoneMatch"] = if_none_match
        with mapped_s3_errors(self._call(SEARCH_INDEX_POINTER_KEY)):
            try:
                response = self._client.get_object(**arguments)
            except ClientError as error:
                if _code_of(error) in _NOT_MODIFIED:
                    return PointerRead(body=None, etag=if_none_match)
                raise
            body = _read_at_most(response, POINTER_MAX_BYTES)
            etag = response.get("ETag")
        return PointerRead(body=body, etag=etag)

    def read_suppression_list(self, *, if_none_match: str | None) -> PointerRead:
        arguments: dict[str, Any] = {"Bucket": self._bucket, "Key": SUPPRESSION_LIST_KEY}
        if if_none_match is not None:
            arguments["IfNoneMatch"] = if_none_match
        with mapped_s3_errors(self._call(SUPPRESSION_LIST_KEY)):
            try:
                response = self._client.get_object(**arguments)
            except ClientError as error:
                code = _code_of(error)
                if code in _NOT_MODIFIED:
                    return PointerRead(body=None, etag=if_none_match)
                if code in _NO_SUCH_KEY:
                    return PointerRead(body=b"", etag=None)
                raise
            body = _read_at_most(response, SUPPRESSION_LIST_MAX_BYTES)
            etag = response.get("ETag")
        return PointerRead(body=body, etag=etag)

    def read_object(self, key: str, *, max_bytes: int) -> bytes:
        key = validate_object_key(key)
        with mapped_s3_errors(self._call(key)):
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            return _read_at_most(response, max_bytes)

    def stream_object(self, key: str) -> Iterator[bytes]:
        key = validate_object_key(key)
        call = self._call(key)
        with mapped_s3_errors(call):
            body = self._client.get_object(Bucket=self._bucket, Key=key)["Body"]
        try:
            while True:
                with mapped_s3_errors(call):
                    chunk = body.read(_STREAM_CHUNK)
                if not chunk:
                    return
                yield chunk
        finally:
            body.close()

    def _call(self, key: str) -> S3Call:
        return S3Call(operation="GetObject", bucket=self._bucket, entity=_ENTITY, key=key, s3_key=key)


def _code_of(error: ClientError) -> str:
    code = error.response.get("Error", {}).get("Code", "")
    return code or str(error.response.get("ResponseMetadata", {}).get("HTTPStatusCode", ""))


def _read_at_most(response: Any, limit: int) -> bytes:
    """The object's body, or :class:`ValueError` once it runs past `limit` bytes."""
    body = response["Body"]
    try:
        if int(response.get("ContentLength", 0)) > limit:
            raise ValueError(f"the object is longer than {limit} bytes")
        data: bytes = body.read(limit + 1)
    finally:
        body.close()
    if len(data) > limit:
        raise ValueError(f"the object is longer than {limit} bytes")
    return data
