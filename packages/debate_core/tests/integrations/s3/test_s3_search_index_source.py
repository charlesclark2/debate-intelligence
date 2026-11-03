"""`S3SearchIndexSource` against moto: the pointer and the suppression list by conditional GET, a manifest
whole, an object streamed.

moto answers in-process; nothing reaches AWS. Every object is synthetic bytes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NoReturn, cast

import pytest
from botocore.exceptions import ClientError

from debate_core.application.caselist.suppression import SUPPRESSION_LIST_KEY
from debate_core.application.errors import NotFound, StoreAccessDenied
from debate_core.application.ports.search_index_source import SUPPRESSION_LIST_MAX_BYTES
from debate_core.domain.search_index import SEARCH_INDEX_POINTER_KEY
from debate_core.integrations.s3 import S3SearchIndexSource
from debate_core.integrations.s3.search_index_source import POINTER_MAX_BYTES

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

POINTER = b'{"pointer_version": 1, "synthetic": true}\n'
OBJECT_KEY = "reports/tub/search/0123456789abcdef/search-index.sqlite.gz"
MANIFEST_KEY = "reports/tub/search/0123456789abcdef/manifest.json"


@pytest.fixture
def source(evidence_bucket: str, s3_client: S3Client) -> S3SearchIndexSource:
    return S3SearchIndexSource(bucket=evidence_bucket, client=s3_client)


def test_the_pointer_is_read_with_its_entity_tag(
    source: S3SearchIndexSource, s3_client: S3Client, evidence_bucket: str
) -> None:
    s3_client.put_object(Bucket=evidence_bucket, Key=SEARCH_INDEX_POINTER_KEY, Body=POINTER)

    read = source.read_pointer(if_none_match=None)

    assert read.body == POINTER
    assert read.etag == s3_client.head_object(Bucket=evidence_bucket, Key=SEARCH_INDEX_POINTER_KEY)["ETag"]


def test_an_unchanged_pointer_comes_back_as_unchanged_with_no_body(
    source: S3SearchIndexSource, s3_client: S3Client, evidence_bucket: str
) -> None:
    s3_client.put_object(Bucket=evidence_bucket, Key=SEARCH_INDEX_POINTER_KEY, Body=POINTER)
    first = source.read_pointer(if_none_match=None)

    again = source.read_pointer(if_none_match=first.etag)

    assert again.unchanged and again.body is None
    assert again.etag == first.etag


def test_a_rewritten_pointer_comes_back_whole_with_its_new_tag(
    source: S3SearchIndexSource, s3_client: S3Client, evidence_bucket: str
) -> None:
    s3_client.put_object(Bucket=evidence_bucket, Key=SEARCH_INDEX_POINTER_KEY, Body=POINTER)
    first = source.read_pointer(if_none_match=None)
    s3_client.put_object(Bucket=evidence_bucket, Key=SEARCH_INDEX_POINTER_KEY, Body=POINTER + b" ")

    again = source.read_pointer(if_none_match=first.etag)

    assert again.body == POINTER + b" "
    assert again.etag != first.etag


def test_no_pointer_is_not_found(source: S3SearchIndexSource) -> None:
    with pytest.raises(NotFound):
        source.read_pointer(if_none_match=None)


def test_a_pointer_far_larger_than_a_pointer_is_refused(
    source: S3SearchIndexSource, s3_client: S3Client, evidence_bucket: str
) -> None:
    s3_client.put_object(
        Bucket=evidence_bucket, Key=SEARCH_INDEX_POINTER_KEY, Body=b" " * (POINTER_MAX_BYTES + 1)
    )

    with pytest.raises(ValueError, match="longer than"):
        source.read_pointer(if_none_match=None)


def test_a_manifest_is_read_whole_up_to_the_limit(
    source: S3SearchIndexSource, s3_client: S3Client, evidence_bucket: str
) -> None:
    s3_client.put_object(Bucket=evidence_bucket, Key=MANIFEST_KEY, Body=b"x" * 100)

    assert source.read_object(MANIFEST_KEY, max_bytes=100) == b"x" * 100
    with pytest.raises(ValueError, match="longer than 99 bytes"):
        source.read_object(MANIFEST_KEY, max_bytes=99)


def test_an_object_is_streamed_in_chunks_that_join_to_its_bytes(
    source: S3SearchIndexSource, s3_client: S3Client, evidence_bucket: str
) -> None:
    body = bytes(range(256)) * 9000
    s3_client.put_object(Bucket=evidence_bucket, Key=OBJECT_KEY, Body=body)

    chunks = list(source.stream_object(OBJECT_KEY))

    assert len(chunks) == 3
    assert b"".join(chunks) == body


def test_a_missing_object_is_not_found_when_the_stream_starts(source: S3SearchIndexSource) -> None:
    with pytest.raises(NotFound):
        next(iter(source.stream_object(OBJECT_KEY)))


def test_a_key_that_is_not_an_object_key_is_refused_unasked(source: S3SearchIndexSource) -> None:
    with pytest.raises(ValueError, match="not an evidence object key"):
        source.read_object("reports/../raw/x", max_bytes=10)


# ------------------------------------------------------------------------------------------------
# The suppression list (v1-e39-t07)
# ------------------------------------------------------------------------------------------------

LIST = b'{"synthetic":"line one"}\n{"synthetic":"line two"}\n'


def test_the_suppression_list_is_read_with_its_entity_tag_and_an_unchanged_one_costs_no_body(
    source: S3SearchIndexSource, s3_client: S3Client, evidence_bucket: str
) -> None:
    s3_client.put_object(Bucket=evidence_bucket, Key=SUPPRESSION_LIST_KEY, Body=LIST)

    first = source.read_suppression_list(if_none_match=None)
    again = source.read_suppression_list(if_none_match=first.etag)

    assert first.body == LIST
    assert first.etag == s3_client.head_object(Bucket=evidence_bucket, Key=SUPPRESSION_LIST_KEY)["ETag"]
    assert again.unchanged and again.etag == first.etag


def test_a_list_that_does_not_exist_has_no_lines(source: S3SearchIndexSource) -> None:
    """To a caller that may list, as moto's is; the function's role may not, and gets AccessDenied."""
    read = source.read_suppression_list(if_none_match=None)

    assert read.body == b""
    assert read.etag is None


def test_a_list_the_role_may_not_read_is_refused_as_access_denied(evidence_bucket: str) -> None:
    class Refusing:
        def get_object(self, **_: object) -> NoReturn:
            raise ClientError({"Error": {"Code": "AccessDenied", "Message": "synthetic"}}, "GetObject")

    source = S3SearchIndexSource(bucket=evidence_bucket, client=cast("S3Client", Refusing()))

    with pytest.raises(StoreAccessDenied):
        source.read_suppression_list(if_none_match=None)


def test_a_list_past_its_limit_is_refused(
    source: S3SearchIndexSource, s3_client: S3Client, evidence_bucket: str
) -> None:
    s3_client.put_object(
        Bucket=evidence_bucket, Key=SUPPRESSION_LIST_KEY, Body=b"\n" * (SUPPRESSION_LIST_MAX_BYTES + 1)
    )

    with pytest.raises(ValueError, match="longer than"):
        source.read_suppression_list(if_none_match=None)
