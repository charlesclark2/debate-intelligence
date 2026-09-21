"""`S3SnapshotStore` under the shared `SnapshotStore` contract, plus the half only S3 has.

The contract binding is the point of this module. Whatever
`packages/debate_core/tests/contracts/test_snapshot_store_contract.py` proves about the filesystem
and in-memory stores, :class:`TestS3SnapshotStore` proves about the bucket in the same words — that
is what makes moving the evidence store to S3 a change of wiring rather than of behaviour
(`v1-e29-t04` ac1).

Everything after it is the part the contract deliberately does not cover, because it is this
adapter's business and nobody else's: where an object lands in the bucket, that a repeat `put` issues
no `PutObject` and leaves one version, what the upload tells S3, and that botocore's failures arrive
as `debate_core.application.errors` types. The bucket itself comes from the moto fixtures in
`packages/debate_core/tests/conftest.py`.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import pytest

from debate_core.application.errors import BlobIntegrityError, NotFound
from debate_core.application.ports import BlobKey, SnapshotStore
from debate_core.integrations.s3 import SHA256_METADATA_NAME, S3SnapshotStore
from debate_core.testing.contracts import (
    ASYNC_BACKEND,
    BlobCorruptor,
    SnapshotStoreContract,
    SnapshotStoreFactory,
)

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

#: Every test in this module drives an `async def` store on a real event loop, as the contract does.
pytestmark = pytest.mark.anyio

DISCLOSED_FILE = b"<html><body><p>Arctic methane release is accelerating.</p></body></html>"
OTHER_DISCLOSED_FILE = b"<html><body><p>Ocean heat content reached a new high.</p></body></html>"


def digest_of(data: bytes) -> BlobKey:
    """The key `data` will be stored under, spelled out where a test asserts on it."""
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def anyio_backend() -> str:
    """asyncio, the backend the CLI, the API and the workers run on."""
    return ASYNC_BACKEND


@pytest.fixture
def store(evidence_bucket: str, blob_prefix: str, s3_client: S3Client) -> S3SnapshotStore:
    """One store over the test bucket, for the adapter-specific tests below."""
    return S3SnapshotStore(bucket=evidence_bucket, prefix=blob_prefix, client=s3_client)


class TestS3SnapshotStore(SnapshotStoreContract):
    """The bucket store, held to every rule the filesystem store is held to."""

    @pytest.fixture
    def make_adapter(
        self, evidence_bucket: str, blob_prefix: str, s3_client: S3Client
    ) -> SnapshotStoreFactory:
        """Fresh handles onto one bucket, so two handles really are two views of one store."""
        return lambda: S3SnapshotStore(bucket=evidence_bucket, prefix=blob_prefix, client=s3_client)

    @pytest.fixture
    def corrupt_blob(self, evidence_bucket: str, blob_prefix: str, s3_client: S3Client) -> BlobCorruptor:
        """Overwrite an object's bytes while leaving its key and recorded digest saying otherwise.

        This is the damage a bad actor with write access does, and it is the one thing no production
        path can do: the store itself refuses to overwrite a content-addressed key, so the contract has
        to reach past it and write the object directly. The recorded `sha256` metadata is left as the
        key, so what is staged is genuinely "the bytes changed underneath a correct-looking record"
        rather than an object that advertises its own mismatch.
        """
        store = S3SnapshotStore(bucket=evidence_bucket, prefix=blob_prefix, client=s3_client)

        def rewrite(key: BlobKey, replacement: bytes) -> None:
            s3_client.put_object(
                Bucket=evidence_bucket,
                Key=store.s3_key_for(key),
                Body=replacement,
                Metadata={SHA256_METADATA_NAME: key},
            )

        return rewrite


class TestTheKeyAnObjectLandsUnder:
    """`<prefix>/sha256/<ab>/<cd>/<digest>`, the same shape as the local store and the layout doc."""

    async def test_an_object_lands_under_the_documented_content_addressed_key(
        self, store: S3SnapshotStore, s3_client: S3Client, evidence_bucket: str, blob_prefix: str
    ) -> None:
        key = await store.put(DISCLOSED_FILE)

        expected = f"{blob_prefix}/sha256/{key[0:2]}/{key[2:4]}/{key}"
        listing = s3_client.list_objects_v2(Bucket=evidence_bucket)
        assert [stored.get("Key") for stored in listing.get("Contents", [])] == [expected]
        assert store.s3_key_for(key) == expected

    async def test_the_key_carries_the_digest_and_no_extension_or_name(
        self, store: S3SnapshotStore, blob_prefix: str
    ) -> None:
        """A key is quoted in logs and in CloudTrail, so it names no file and no team."""
        key = digest_of(DISCLOSED_FILE)

        s3_key = store.s3_key_for(key)
        assert s3_key.endswith(key)
        assert "." not in s3_key.removeprefix(blob_prefix)

    async def test_a_key_that_is_not_a_digest_is_refused_before_any_request(
        self, store: S3SnapshotStore
    ) -> None:
        """The containment guard: no key can name an object outside this store's prefix."""
        for not_a_key in ["../../etc/passwd", "ABCD" * 16, "short", f"{'a' * 63}/x"]:
            with pytest.raises(ValueError, match="not a blob key"):
                store.s3_key_for(not_a_key)

    async def test_a_key_that_is_not_a_digest_reads_as_absent_rather_than_as_an_error(
        self, store: S3SnapshotStore
    ) -> None:
        """Nothing could have stored it, so the port's own answers — `NotFound`, `False` — apply."""
        with pytest.raises(NotFound):
            await store.get("not-a-digest")
        assert await store.exists("not-a-digest") is False

    async def test_a_prefix_that_could_escape_the_store_is_refused_at_construction(
        self, evidence_bucket: str, s3_client: S3Client
    ) -> None:
        for bad_prefix in ["/raw", "raw/", "raw/../parsed", ""]:
            with pytest.raises(ValueError):
                S3SnapshotStore(bucket=evidence_bucket, prefix=bad_prefix, client=s3_client)


class TestARepeatPutCostsNothingAndChangesNothing:
    """The bucket is versioned, so "idempotent" has to mean "no new version", not just "same bytes"."""

    async def test_a_second_put_of_identical_bytes_issues_no_put_object(
        self, store: S3SnapshotStore, s3_client: S3Client
    ) -> None:
        uploads: list[str] = []

        def record_upload(**_: object) -> None:
            uploads.append("PutObject")

        s3_client.meta.events.register("before-call.s3.PutObject", record_upload)

        first = await store.put(DISCLOSED_FILE)
        assert uploads == ["PutObject"], "the first put should upload exactly once"
        second = await store.put(DISCLOSED_FILE)

        assert first == second
        assert uploads == ["PutObject"], "the second put re-uploaded an object that was already stored"

    async def test_a_second_put_of_identical_bytes_leaves_one_version(
        self, store: S3SnapshotStore, s3_client: S3Client, evidence_bucket: str
    ) -> None:
        """In a content-addressed store, a key with two versions means something went wrong."""
        key = await store.put(DISCLOSED_FILE)
        await store.put(DISCLOSED_FILE)

        versions = s3_client.list_object_versions(Bucket=evidence_bucket, Prefix=store.s3_key_for(key))
        assert len(versions.get("Versions", [])) == 1

    async def test_bytes_that_disagree_with_a_stored_objects_recorded_digest_are_refused(
        self, store: S3SnapshotStore, s3_client: S3Client, evidence_bucket: str
    ) -> None:
        """Two different contents can never be filed under one content-addressed key.

        Staged the only way it can happen: an object written outside this store, at one blob's key,
        recording another blob's digest. A put of the bytes that really do hash to that key then finds a
        store it cannot safely write to, and says so instead of adding a version.
        """
        key = digest_of(DISCLOSED_FILE)
        s3_client.put_object(
            Bucket=evidence_bucket,
            Key=store.s3_key_for(key),
            Body=OTHER_DISCLOSED_FILE,
            Metadata={SHA256_METADATA_NAME: digest_of(OTHER_DISCLOSED_FILE)},
        )

        with pytest.raises(BlobIntegrityError) as refused:
            await store.put(DISCLOSED_FILE)
        assert refused.value.key == key
        assert refused.value.actual_sha256 == digest_of(OTHER_DISCLOSED_FILE)

    async def test_an_object_this_store_did_not_write_is_left_alone(
        self, store: S3SnapshotStore, s3_client: S3Client, evidence_bucket: str
    ) -> None:
        """No recorded digest means "not ours": the put skips it rather than overwriting evidence.

        The mismatch is not ignored — it surfaces at `get`, which re-hashes every read — but it is not
        resolved by replacing an object in a versioned bucket with one this store happens to prefer.
        """
        key = digest_of(DISCLOSED_FILE)
        s3_client.put_object(Bucket=evidence_bucket, Key=store.s3_key_for(key), Body=OTHER_DISCLOSED_FILE)

        assert await store.put(DISCLOSED_FILE) == key
        versions = s3_client.list_object_versions(Bucket=evidence_bucket, Prefix=store.s3_key_for(key))
        assert len(versions.get("Versions", [])) == 1
        with pytest.raises(BlobIntegrityError):
            await store.get(key)


class TestWhatTheUploadTellsS3:
    """The checksum S3 verifies, the digest a `HeadObject` can state, and the encryption."""

    async def test_the_upload_carries_s3s_own_sha256_checksum(
        self, store: S3SnapshotStore, s3_client: S3Client, evidence_bucket: str
    ) -> None:
        """So S3 refuses bytes that arrived damaged instead of storing them."""
        key = await store.put(DISCLOSED_FILE)

        head = s3_client.head_object(
            Bucket=evidence_bucket, Key=store.s3_key_for(key), ChecksumMode="ENABLED"
        )
        assert "ChecksumSHA256" in head

    async def test_the_full_object_digest_is_recorded_in_object_metadata(
        self, store: S3SnapshotStore, s3_client: S3Client, evidence_bucket: str
    ) -> None:
        """A `HeadObject` can then state the digest without downloading the object."""
        key = await store.put(DISCLOSED_FILE)

        head = s3_client.head_object(Bucket=evidence_bucket, Key=store.s3_key_for(key))
        assert head["Metadata"][SHA256_METADATA_NAME] == key

    async def test_metadata_carries_the_digest_and_nothing_that_identifies_anyone(
        self, store: S3SnapshotStore, s3_client: S3Client, evidence_bucket: str
    ) -> None:
        """`docs/policies/caselist-data-use.md`: no school, team or filename, in a key or in metadata."""
        key = await store.put(DISCLOSED_FILE)

        head = s3_client.head_object(Bucket=evidence_bucket, Key=store.s3_key_for(key))
        assert head["Metadata"] == {SHA256_METADATA_NAME: key}

    async def test_a_given_kms_key_is_stated_on_the_upload(
        self, evidence_bucket: str, blob_prefix: str, s3_client: S3Client
    ) -> None:
        """For a caller passing the environment's `evidence_kms_key_arn` rather than inheriting it."""
        key_arn = "arn:aws:kms:us-east-1:111111111111:key/00000000-0000-0000-0000-000000000000"
        store = S3SnapshotStore(
            bucket=evidence_bucket, prefix=blob_prefix, client=s3_client, kms_key_id=key_arn
        )

        key = await store.put(DISCLOSED_FILE)

        head = s3_client.head_object(Bucket=evidence_bucket, Key=store.s3_key_for(key))
        assert head["ServerSideEncryption"] == "aws:kms"
        assert head["SSEKMSKeyId"] == key_arn
        assert await store.get(key) == DISCLOSED_FILE


class TestWhatBotocoreFailuresLookLikeToACaller:
    """No `ClientError` crosses the port; `test_s3_error_mapping.py` has the whole table."""

    async def test_a_bucket_that_does_not_exist_is_reported_as_the_bucket_being_missing(
        self, blob_prefix: str, s3_client: S3Client
    ) -> None:
        """Almost always the wrong environment, or a bucket name typed instead of read from Terraform."""
        never_created = "debate-test-evidence-never-created"
        store = S3SnapshotStore(bucket=never_created, prefix=blob_prefix, client=s3_client)

        with pytest.raises(NotFound) as refused:
            await store.get(digest_of(DISCLOSED_FILE))
        assert refused.value.entity == "evidence bucket"
        assert refused.value.key == never_created


class TestHowTheStoreIsBuilt:
    """The constructor takes its coordinates; it reads no settings and names no bucket of its own."""

    async def test_the_store_satisfies_the_snapshot_store_port(self, store: S3SnapshotStore) -> None:
        """Structurally, at runtime, and — through the annotation — statically under pyright."""
        port: SnapshotStore = store

        assert isinstance(port, SnapshotStore)

    async def test_a_store_built_from_a_region_and_profile_makes_its_own_client(
        self, evidence_bucket: str, blob_prefix: str, aws_region: str
    ) -> None:
        """The production path: no client passed in, and botocore's own chain resolves the session.

        `evidence_bucket` is what puts moto in front of that client, so the round trip here is against
        the same in-process bucket as everything else in this module.
        """
        store = S3SnapshotStore(bucket=evidence_bucket, prefix=blob_prefix, region=aws_region)

        key = await store.put(DISCLOSED_FILE)

        assert store.bucket == evidence_bucket
        assert store.prefix == blob_prefix
        assert await store.get(key) == DISCLOSED_FILE

    async def test_a_part_size_below_s3s_minimum_is_refused(
        self, evidence_bucket: str, blob_prefix: str, s3_client: S3Client
    ) -> None:
        """Checked at construction, not discovered when a multi-gigabyte upload fails halfway."""
        with pytest.raises(ValueError, match="at least S3's minimum"):
            S3SnapshotStore(
                bucket=evidence_bucket,
                prefix=blob_prefix,
                client=s3_client,
                multipart_part_size_bytes=1024,
            )
