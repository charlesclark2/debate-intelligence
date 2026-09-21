"""A file too big to hold in memory goes up in parts, comes back byte-identical, and keeps its digest.

The evidence store's ordinary object is a disclosed file of a few hundred kilobytes, which is one
`PutObject`. The ones this module is about are the camp archives and season dumps — the reason
:meth:`~debate_core.integrations.s3.S3SnapshotStore.put_file` exists beside `put`, and the reason a
multipart transfer has to keep every promise a single request keeps (`v1-e29-t04` ac3).

The one that takes work is the digest. S3's own `ChecksumSHA256` on a multipart object is a
*composite* — the digest of the concatenated part digests, with a `-N` suffix — so it is not the
SHA-256 of the file and cannot be compared with a blob key. The store therefore computes the
full-object digest itself while streaming the file and records it in object metadata, which is what
these tests check.

The fixture file is 11 MiB against a 5 MiB part size: three parts, the smallest arrangement that is
genuinely multipart, with a last part that is not a whole one. Its bytes are seeded rather than
random so that a failure is reproducible, and incompressible so that nothing along the way can make
the transfer smaller than the test intends.
"""

from __future__ import annotations

import hashlib
import random
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from debate_core.application.errors import BlobIntegrityError, NotFound
from debate_core.integrations.s3 import SHA256_METADATA_NAME, S3SnapshotStore

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

#: Small enough to keep the suite fast, large enough to be a real multipart upload.
MULTIPART_PART_SIZE_BYTES = 5 * 1024 * 1024
MULTIPART_THRESHOLD_BYTES = 5 * 1024 * 1024

#: 11 MiB: two whole parts and a remainder, so an off-by-one in the last part cannot hide.
CAMP_ARCHIVE_SIZE_BYTES = 11 * 1024 * 1024

#: Any fixed seed; named so it is obvious the bytes are reproducible rather than random per run.
ARCHIVE_CONTENT_SEED = 20260920


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def camp_archive(tmp_path: Path) -> Path:
    """A file of incompressible, reproducible bytes, standing in for a camp archive."""
    archive = tmp_path / "camp-archive-fixture"
    archive.write_bytes(random.Random(ARCHIVE_CONTENT_SEED).randbytes(CAMP_ARCHIVE_SIZE_BYTES))
    return archive


@pytest.fixture
def multipart_store(evidence_bucket: str, blob_prefix: str, s3_client: S3Client) -> S3SnapshotStore:
    """A store whose thresholds make an 11 MiB file a three-part upload."""
    return S3SnapshotStore(
        bucket=evidence_bucket,
        prefix=blob_prefix,
        client=s3_client,
        multipart_threshold_bytes=MULTIPART_THRESHOLD_BYTES,
        multipart_part_size_bytes=MULTIPART_PART_SIZE_BYTES,
    )


def count_operation(client: S3Client, operation: str) -> list[str]:
    """Return a list that grows by one entry each time `operation` is sent."""
    sent: list[str] = []

    def record(**_: object) -> None:
        sent.append(operation)

    client.meta.events.register(f"before-call.s3.{operation}", record)
    return sent


class TestAFileAboveTheThreshold:
    async def test_it_is_uploaded_in_parts(
        self, multipart_store: S3SnapshotStore, camp_archive: Path, s3_client: S3Client
    ) -> None:
        """Three parts for 11 MiB at 5 MiB each, and one `PutObject` would be none."""
        created = count_operation(s3_client, "CreateMultipartUpload")
        parts = count_operation(s3_client, "UploadPart")
        completed = count_operation(s3_client, "CompleteMultipartUpload")
        single_requests = count_operation(s3_client, "PutObject")

        await multipart_store.put_file(camp_archive)

        assert len(created) == 1
        assert len(parts) == 3, "11 MiB at a 5 MiB part size is three parts"
        assert len(completed) == 1
        assert single_requests == []

    async def test_it_reads_back_byte_identical(
        self, multipart_store: S3SnapshotStore, camp_archive: Path, tmp_path: Path
    ) -> None:
        """The property everything else rests on: what came out is what went in."""
        key = await multipart_store.put_file(camp_archive)

        restored = await multipart_store.get_file(key, tmp_path / "restored" / "camp-archive")

        assert restored.read_bytes() == camp_archive.read_bytes()

    async def test_the_full_object_digest_is_stored_in_object_metadata(
        self,
        multipart_store: S3SnapshotStore,
        camp_archive: Path,
        s3_client: S3Client,
        evidence_bucket: str,
    ) -> None:
        """Not S3's composite checksum: the SHA-256 of the whole file, which is also its key."""
        key = await multipart_store.put_file(camp_archive)

        head = s3_client.head_object(
            Bucket=evidence_bucket, Key=multipart_store.s3_key_for(key), ChecksumMode="ENABLED"
        )
        assert key == hashlib.sha256(camp_archive.read_bytes()).hexdigest()
        assert head["Metadata"][SHA256_METADATA_NAME] == key
        assert head["ContentLength"] == CAMP_ARCHIVE_SIZE_BYTES

    async def test_a_second_put_of_the_same_file_uploads_nothing(
        self, multipart_store: S3SnapshotStore, camp_archive: Path, s3_client: S3Client
    ) -> None:
        """Content addressing makes re-publishing a 40-gigabyte archive free, which is the point."""
        first = await multipart_store.put_file(camp_archive)
        created = count_operation(s3_client, "CreateMultipartUpload")
        parts = count_operation(s3_client, "UploadPart")

        second = await multipart_store.put_file(camp_archive)

        assert first == second
        assert created == []
        assert parts == []

    async def test_it_can_also_be_read_whole_through_the_port(
        self, multipart_store: S3SnapshotStore, camp_archive: Path
    ) -> None:
        """`get` still works on a multipart object; it is `put_file`'s counterpart that streams."""
        key = await multipart_store.put_file(camp_archive)

        assert await multipart_store.get(key) == camp_archive.read_bytes()


class TestAFileBelowTheThreshold:
    async def test_it_goes_up_in_a_single_request(
        self, multipart_store: S3SnapshotStore, tmp_path: Path, s3_client: S3Client
    ) -> None:
        """Almost everything in the store is this file, and it should cost one request, not four."""
        disclosure = tmp_path / "disclosed-file"
        disclosure.write_bytes(b"<html><body><p>A few hundred kilobytes, really.</p></body></html>")
        single_requests = count_operation(s3_client, "PutObject")
        created = count_operation(s3_client, "CreateMultipartUpload")

        key = await multipart_store.put_file(disclosure)

        assert len(single_requests) == 1
        assert created == []
        assert await multipart_store.get(key) == disclosure.read_bytes()

    async def test_an_empty_file_round_trips(self, multipart_store: S3SnapshotStore, tmp_path: Path) -> None:
        """A zero-length retrieval is a legitimate one — a blocked page, a stripped PDF."""
        empty = tmp_path / "empty-file"
        empty.write_bytes(b"")

        key = await multipart_store.put_file(empty)

        assert key == hashlib.sha256(b"").hexdigest()
        assert await multipart_store.get(key) == b""


class TestWhatADownloadLeavesBehind:
    """A file on disk is either the whole object or nothing, whatever happens to the transfer."""

    async def test_a_download_whose_bytes_do_not_match_the_key_writes_no_file(
        self,
        multipart_store: S3SnapshotStore,
        camp_archive: Path,
        s3_client: S3Client,
        evidence_bucket: str,
        tmp_path: Path,
    ) -> None:
        """Damaged evidence is refused rather than landed and hoped about."""
        key = await multipart_store.put_file(camp_archive)
        s3_client.put_object(
            Bucket=evidence_bucket,
            Key=multipart_store.s3_key_for(key),
            Body=b"not the archive at all",
            Metadata={SHA256_METADATA_NAME: key},
        )
        destination = tmp_path / "restored" / "camp-archive"

        with pytest.raises(BlobIntegrityError) as refused:
            await multipart_store.get_file(key, destination)

        assert refused.value.key == key
        assert not destination.exists()

    async def test_a_failed_download_leaves_an_existing_file_untouched(
        self, multipart_store: S3SnapshotStore, camp_archive: Path, tmp_path: Path
    ) -> None:
        """A retried sync must not be able to replace a good local file with a failed download.

        The failure staged here is the plainest one — a key the store holds nothing under — because
        that is what a resumed sync working from a stale plan actually asks for.
        """
        key = await multipart_store.put_file(camp_archive)
        destination = tmp_path / "already-there"
        destination.write_bytes(b"a file the operator already had")

        with pytest.raises(NotFound):
            await multipart_store.get_file("f" * 64, destination)

        assert destination.read_bytes() == b"a file the operator already had"
        assert await multipart_store.get_file(key, destination) == destination
        assert destination.read_bytes() == camp_archive.read_bytes()

    async def test_no_partial_download_is_left_in_the_destination_directory(
        self,
        multipart_store: S3SnapshotStore,
        camp_archive: Path,
        s3_client: S3Client,
        evidence_bucket: str,
        tmp_path: Path,
    ) -> None:
        """The temporary file a transfer wrote is deleted, so nothing walking the tree finds it."""
        key = await multipart_store.put_file(camp_archive)
        s3_client.put_object(
            Bucket=evidence_bucket,
            Key=multipart_store.s3_key_for(key),
            Body=b"not the archive at all",
            Metadata={SHA256_METADATA_NAME: key},
        )
        destination = tmp_path / "restored" / "camp-archive"

        with pytest.raises(BlobIntegrityError):
            await multipart_store.get_file(key, destination)

        assert list(destination.parent.iterdir()) == []
