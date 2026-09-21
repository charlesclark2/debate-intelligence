"""What `S3EvidenceObjectStore` does that the shared contract does not ask about.

The contract (`tests/contracts/test_evidence_object_store_contract.py`) covers everything a caller may
assume of either implementation. This module covers the bucket-shaped half: that a key is used
unchanged, that a listing pages, that a versioned bucket's version id comes back, and that an object
somebody else put there is reported honestly rather than guessed at.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from debate_core.application.errors import NotFound
from debate_core.integrations.s3 import SHA256_METADATA_NAME, S3EvidenceObjectStore

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

MANIFEST_KEY = "manifests/hsld26/2026-09-15.jsonl"
MANIFEST_ROW = b'{"sha256":"5e88489","bytes":48213,"content_type":"application/pdf"}\n'


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def store(evidence_bucket: str, s3_client: S3Client) -> S3EvidenceObjectStore:
    return S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client)


@pytest.fixture
def manifest_file(tmp_path: Path) -> Path:
    source = tmp_path / "2026-09-15.jsonl"
    source.write_bytes(MANIFEST_ROW)
    return source


class TestTheKeyAnObjectLandsUnder:
    async def test_the_key_is_used_exactly_as_given(
        self, store: S3EvidenceObjectStore, manifest_file: Path, s3_client: S3Client, evidence_bucket: str
    ) -> None:
        """No prefix and no rewriting: the sync diffs this store against the local one by key."""
        await store.put_file(MANIFEST_KEY, manifest_file)

        listing = s3_client.list_objects_v2(Bucket=evidence_bucket)
        assert [stored.get("Key") for stored in listing.get("Contents", [])] == [MANIFEST_KEY]

    async def test_an_upload_records_the_digest_and_carries_s3s_own_checksum(
        self, store: S3EvidenceObjectStore, manifest_file: Path, s3_client: S3Client, evidence_bucket: str
    ) -> None:
        await store.put_file(MANIFEST_KEY, manifest_file)

        head = s3_client.head_object(Bucket=evidence_bucket, Key=MANIFEST_KEY, ChecksumMode="ENABLED")
        assert head["Metadata"] == {SHA256_METADATA_NAME: hashlib.sha256(MANIFEST_ROW).hexdigest()}
        assert "ChecksumSHA256" in head


class TestVersions:
    """The bucket is versioned, and a named object is the kind that really does get a second version."""

    async def test_a_stored_object_reports_the_version_it_was_written_as(
        self, store: S3EvidenceObjectStore, manifest_file: Path
    ) -> None:
        stored = await store.put_file(MANIFEST_KEY, manifest_file)

        assert stored.version_id is not None
        assert (await store.head(MANIFEST_KEY)).version_id == stored.version_id

    async def test_replacing_an_object_reports_a_new_version(
        self, store: S3EvidenceObjectStore, manifest_file: Path, tmp_path: Path
    ) -> None:
        """What makes a re-published manifest recoverable: the previous one is still in the bucket."""
        first = await store.put_file(MANIFEST_KEY, manifest_file)
        appended = tmp_path / "appended.jsonl"
        appended.write_bytes(MANIFEST_ROW * 2)

        second = await store.put_file(MANIFEST_KEY, appended)

        assert second.version_id != first.version_id


class TestAnObjectThisStoreDidNotWrite:
    async def test_it_heads_with_no_digest_rather_than_an_error(
        self, store: S3EvidenceObjectStore, s3_client: S3Client, evidence_bucket: str
    ) -> None:
        """A console upload or an earlier tool: the honest answer is "read it to find out"."""
        s3_client.put_object(Bucket=evidence_bucket, Key=MANIFEST_KEY, Body=MANIFEST_ROW)

        found = await store.head(MANIFEST_KEY)

        assert found.size == len(MANIFEST_ROW)
        assert found.sha256 is None

    async def test_downloading_it_reports_the_digest_of_what_landed(
        self, store: S3EvidenceObjectStore, s3_client: S3Client, evidence_bucket: str, tmp_path: Path
    ) -> None:
        """With no recorded digest there is nothing to verify against, so the digest is computed."""
        s3_client.put_object(Bucket=evidence_bucket, Key=MANIFEST_KEY, Body=MANIFEST_ROW)

        got = await store.get_file(MANIFEST_KEY, tmp_path / "downloaded.jsonl")

        assert got.sha256 == hashlib.sha256(MANIFEST_ROW).hexdigest()
        assert (tmp_path / "downloaded.jsonl").read_bytes() == MANIFEST_ROW


class TestListingTheStore:
    async def test_a_listing_walks_every_page(
        self, store: S3EvidenceObjectStore, s3_client: S3Client, evidence_bucket: str
    ) -> None:
        """S3 returns at most 1,000 keys per request, and a sync that stopped there would sync 1,000.

        The objects go in through the client rather than through `put_file` so that the test is about
        paging and not about 1,001 uploads.
        """
        for number in range(1001):
            s3_client.put_object(
                Bucket=evidence_bucket, Key=f"manifests/hsld26/{number:05d}.jsonl", Body=b"{}\n"
            )

        listed = await store.list_objects("manifests/")

        assert len(listed) == 1001
        assert listed[0].key == "manifests/hsld26/00000.jsonl"
        assert listed[-1].key == "manifests/hsld26/01000.jsonl"

    async def test_a_listing_of_a_bucket_that_does_not_exist_says_so(self, s3_client: S3Client) -> None:
        """Not an empty listing: an empty answer would make a sync think the bucket had been emptied."""
        store = S3EvidenceObjectStore(bucket="debate-test-evidence-never-created", client=s3_client)

        with pytest.raises(NotFound) as refused:
            await store.list_objects("manifests/")
        assert refused.value.entity == "evidence bucket"


class TestWhenTheBucketIsNotThere:
    async def test_heading_an_object_reports_the_bucket_rather_than_the_key(
        self, s3_client: S3Client
    ) -> None:
        """A store pointed at the wrong bucket must not report every key in it as merely absent."""
        store = S3EvidenceObjectStore(bucket="debate-test-evidence-never-created", client=s3_client)

        with pytest.raises(NotFound) as refused:
            await store.head(MANIFEST_KEY)
        assert refused.value.entity == "evidence bucket"
