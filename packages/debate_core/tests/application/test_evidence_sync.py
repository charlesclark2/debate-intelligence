"""What `EvidenceSyncService` decides, what it transfers, and what it refuses to transfer.

Run against the real adapters — the filesystem store on `tmp_path` and the S3 store on a moto
bucket — rather than against fakes, because most of what this module promises is about the *seam*
between them: which calls it makes, which digests it compares, and what it does when the two sides
disagree. A fake remote store that answered every head with the digest it was given would pass
every test here and prove nothing.

`s3_operations` records every S3 API call botocore actually issues, through the same event system
the SDK signs requests on. That is how "a dry run performs no PutObject or GetObject" and "a blob
diff heads nothing" are asserted: on the wire, not on a counter this code keeps about itself.

Nothing here reaches AWS. `packages/debate_core/tests/conftest.py` builds the bucket in moto with
fake credentials, and the workspace's pytest options disable sockets.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from debate_core.application.errors import (
    BlobIntegrityError,
    NotFound,
    StoreCredentialsExpired,
)
from debate_core.application.evidence_sync import (
    EVIDENCE_PREFIXES,
    EvidenceSyncService,
    JournalEntry,
    SyncAction,
    SyncDirection,
    SyncJournal,
    SyncKeyspace,
    UnsyncableKeyspace,
)
from debate_core.application.ports.evidence_store import ObjectInfo
from debate_core.integrations.local import BLOB_DIRECTORY, FsEvidenceObjectStore, FsSnapshotStore
from debate_core.integrations.s3 import SHA256_METADATA_NAME, S3EvidenceObjectStore
from debate_core.testing.fakes import FixedClock

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

BLOB_PREFIX = "raw/caselist/hsld26"
MANIFEST_KEY = "manifests/hsld26/2026-09-15.jsonl"
REPORT_KEY = "reports/sync/2026-09-15T06-00Z.json"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """One environment's local evidence directory: `objects/`, `blobs/` and the journal."""
    return tmp_path / "evidence"


@pytest.fixture
def s3_operations(s3_client: S3Client) -> list[str]:
    """Every S3 operation botocore issues on this client, in order, by name.

    Registered on botocore's own event system rather than by wrapping the store, so that what is
    counted is the request that would go to AWS — including the ones boto3's transfer manager
    makes on its own behalf during a multipart upload.
    """
    recorded: list[str] = []

    def record(model: Any = None, **_: Any) -> None:
        recorded.append(str(getattr(model, "name", model)))

    s3_client.meta.events.register("before-call.s3", record)
    return recorded


@pytest.fixture
def objects_keyspace(data_dir: Path, evidence_bucket: str, s3_client: S3Client) -> SyncKeyspace:
    """Named objects: `<data_dir>/objects/<key>` is `<key>` in the bucket."""
    local = FsEvidenceObjectStore(data_dir)
    return SyncKeyspace(
        name="objects",
        local=local,
        remote=S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client),
        local_path_for=local.path_for,
    )


@pytest.fixture
def blobs_keyspace(data_dir: Path, evidence_bucket: str, s3_client: S3Client) -> SyncKeyspace:
    """Content-addressed blobs: `<data_dir>/blobs/sha256/…` under one corpus prefix."""
    local = FsEvidenceObjectStore(data_dir, subdirectory=BLOB_DIRECTORY.parent)
    return SyncKeyspace(
        name="blobs",
        local=local,
        remote=S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client),
        remote_prefix=BLOB_PREFIX,
        content_addressed=True,
        local_path_for=local.path_for,
    )


@pytest.fixture
def journal(data_dir: Path, evidence_bucket: str) -> SyncJournal:
    return SyncJournal.open(data_dir, environment="dev", remote=evidence_bucket)


@pytest.fixture
def service(
    objects_keyspace: SyncKeyspace,
    blobs_keyspace: SyncKeyspace,
    journal: SyncJournal,
    evidence_bucket: str,
) -> EvidenceSyncService:
    return EvidenceSyncService(
        keyspaces=(objects_keyspace, blobs_keyspace),
        journal=journal,
        remote_name=evidence_bucket,
        clock=FixedClock(),
    )


# ------------------------------------------------------------------------------------------------
# Building the two sides
# ------------------------------------------------------------------------------------------------


def write_local_object(data_dir: Path, key: str, body: bytes) -> str:
    """Put a named object in the local store and return its digest."""
    path = data_dir / "objects" / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return hashlib.sha256(body).hexdigest()


async def write_local_blob(data_dir: Path, body: bytes) -> str:
    """Put a blob in the local store through the store that owns that tree, and return its key."""
    digest = await FsSnapshotStore(data_dir).put(body)
    return f"sha256/{digest[0:2]}/{digest[2:4]}/{digest}"


def put_remote_object(client: S3Client, bucket: str, key: str, body: bytes) -> None:
    """Put an object in the bucket the way the adapter does, digest metadata and all."""
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        Metadata={SHA256_METADATA_NAME: hashlib.sha256(body).hexdigest()},
    )


def remote_keys(client: S3Client, bucket: str) -> list[str]:
    listing = client.list_objects_v2(Bucket=bucket)
    return sorted(str(stored.get("Key", "")) for stored in listing.get("Contents", []))


def actions(plan: Any, action: SyncAction) -> list[str]:
    return sorted(planned.remote_key for planned in plan.of(action))


# ------------------------------------------------------------------------------------------------
# Planning: what a dry run says, and what it costs (acceptance criterion 1)
# ------------------------------------------------------------------------------------------------


class TestPlanning:
    async def test_an_object_absent_from_the_bucket_is_new(
        self, service: EvidenceSyncService, data_dir: Path
    ) -> None:
        write_local_object(data_dir, MANIFEST_KEY, b'{"sha256":"abc"}\n')

        plan = await service.plan()

        assert actions(plan, SyncAction.NEW) == [MANIFEST_KEY]
        assert plan.count(SyncAction.CHANGED) == 0
        assert plan.bytes_to_transfer == 17

    async def test_an_identical_object_is_skipped(
        self, service: EvidenceSyncService, data_dir: Path, s3_client: S3Client, evidence_bucket: str
    ) -> None:
        body = b'{"sha256":"abc"}\n'
        write_local_object(data_dir, MANIFEST_KEY, body)
        put_remote_object(s3_client, evidence_bucket, MANIFEST_KEY, body)

        plan = await service.plan()

        assert actions(plan, SyncAction.SKIPPED) == [MANIFEST_KEY]
        assert plan.count(SyncAction.NEW) == 0

    async def test_a_rewritten_manifest_of_the_same_length_is_changed(
        self, service: EvidenceSyncService, data_dir: Path, s3_client: S3Client, evidence_bucket: str
    ) -> None:
        """The case that costs a head: same size, different bytes."""
        write_local_object(data_dir, MANIFEST_KEY, b"aaaaaaaaaa")
        put_remote_object(s3_client, evidence_bucket, MANIFEST_KEY, b"bbbbbbbbbb")

        plan = await service.plan()

        assert actions(plan, SyncAction.CHANGED) == [MANIFEST_KEY]
        assert plan.objects[0].reason == "different digest"

    async def test_a_manifest_of_a_different_length_is_changed_without_a_head(
        self,
        service: EvidenceSyncService,
        data_dir: Path,
        s3_client: S3Client,
        evidence_bucket: str,
        s3_operations: list[str],
    ) -> None:
        write_local_object(data_dir, MANIFEST_KEY, b"aaaaaaaaaaaa")
        put_remote_object(s3_client, evidence_bucket, MANIFEST_KEY, b"bb")
        s3_operations.clear()

        plan = await service.plan()

        assert actions(plan, SyncAction.CHANGED) == [MANIFEST_KEY]
        assert plan.remote_head_requests == 0
        assert "HeadObject" not in s3_operations

    async def test_an_object_only_in_the_bucket_is_reported_and_never_deleted(
        self, service: EvidenceSyncService, s3_client: S3Client, evidence_bucket: str
    ) -> None:
        put_remote_object(s3_client, evidence_bucket, REPORT_KEY, b"{}")

        plan = await service.plan()
        report = await service.execute(plan)

        assert actions(plan, SyncAction.WOULD_DELETE) == [REPORT_KEY]
        assert remote_keys(s3_client, evidence_bucket) == [REPORT_KEY]
        assert report.outcomes == ()

    async def test_a_local_key_outside_the_documented_prefixes_is_skipped(
        self, service: EvidenceSyncService, data_dir: Path
    ) -> None:
        """`evidence-store-layout.md` is the contract; a key outside it is not uploaded."""
        write_local_object(data_dir, "scratch/notes.txt", b"mine")

        plan = await service.plan()

        assert plan.count(SyncAction.NEW) == 0
        assert plan.objects[0].action is SyncAction.SKIPPED
        assert plan.objects[0].reason == "not under a documented evidence prefix"

    async def test_the_prefix_filter_selects_one_part_of_the_store(
        self, service: EvidenceSyncService, data_dir: Path
    ) -> None:
        write_local_object(data_dir, MANIFEST_KEY, b"a")
        write_local_object(data_dir, REPORT_KEY, b"b")

        plan = await service.plan(prefix="manifests/")

        assert actions(plan, SyncAction.NEW) == [MANIFEST_KEY]

    async def test_an_unfiltered_run_never_lists_the_bucket_root(
        self, service: EvidenceSyncService, s3_operations: list[str], s3_client: S3Client
    ) -> None:
        """The operator credential may list each documented prefix and not the bucket itself."""
        listed: list[str] = []

        def record_prefix(params: Any = None, **_: Any) -> None:
            listed.append(str(dict(params or {}).get("Prefix", "")))

        s3_client.meta.events.register("provide-client-params.s3.ListObjectsV2", record_prefix)

        await service.plan()

        assert listed, "the planner listed nothing at all"
        assert "" not in listed
        assert set(EVIDENCE_PREFIXES) <= set(listed)

    async def test_a_dry_run_moves_nothing(
        self,
        service: EvidenceSyncService,
        data_dir: Path,
        s3_client: S3Client,
        evidence_bucket: str,
        s3_operations: list[str],
    ) -> None:
        """Acceptance criterion 1: planning issues no PutObject and no GetObject."""
        write_local_object(data_dir, MANIFEST_KEY, b'{"sha256":"abc"}\n')
        put_remote_object(s3_client, evidence_bucket, REPORT_KEY, b"{}")
        s3_operations.clear()

        plan = await service.plan()

        assert plan.counts["new"] == 1
        assert plan.counts["would_delete"] == 1
        assert "PutObject" not in s3_operations
        assert "GetObject" not in s3_operations
        assert "DeleteObject" not in s3_operations
        assert remote_keys(s3_client, evidence_bucket) == [REPORT_KEY]


# ------------------------------------------------------------------------------------------------
# Content-addressed blobs: a key-set comparison, and never an overwrite
# ------------------------------------------------------------------------------------------------


class TestBlobs:
    async def test_a_blob_the_bucket_already_holds_is_skipped_without_heading_it(
        self,
        service: EvidenceSyncService,
        data_dir: Path,
        s3_client: S3Client,
        evidence_bucket: str,
        s3_operations: list[str],
    ) -> None:
        """The PM's cost rule: identical keys are identical bytes, so nothing is asked of S3."""
        body = b"a disclosed file"
        key = await write_local_blob(data_dir, body)
        put_remote_object(s3_client, evidence_bucket, f"{BLOB_PREFIX}/{key}", body)
        s3_operations.clear()

        plan = await service.plan()

        assert actions(plan, SyncAction.SKIPPED) == [f"{BLOB_PREFIX}/{key}"]
        assert plan.remote_head_requests == 0
        assert "HeadObject" not in s3_operations

    async def test_a_new_blob_is_uploaded_under_its_corpus_prefix(
        self, service: EvidenceSyncService, data_dir: Path, s3_client: S3Client, evidence_bucket: str
    ) -> None:
        key = await write_local_blob(data_dir, b"a disclosed file")

        report = await service.execute(await service.plan())

        assert remote_keys(s3_client, evidence_bucket) == [f"{BLOB_PREFIX}/{key}"]
        assert report.succeeded

    async def test_a_blob_whose_two_sides_differ_is_mismatched_and_never_written_over(
        self, service: EvidenceSyncService, data_dir: Path, s3_client: S3Client, evidence_bucket: str
    ) -> None:
        """A content-addressed key cannot hold two different things; this is how that is reported."""
        key = await write_local_blob(data_dir, b"a disclosed file")
        put_remote_object(s3_client, evidence_bucket, f"{BLOB_PREFIX}/{key}", b"something else entirely")

        plan = await service.plan()
        report = await service.execute(plan)

        assert actions(plan, SyncAction.MISMATCHED) == [f"{BLOB_PREFIX}/{key}"]
        assert plan.transfers == ()
        assert not report.succeeded
        stored = s3_client.get_object(Bucket=evidence_bucket, Key=f"{BLOB_PREFIX}/{key}")
        assert stored["Body"].read() == b"something else entirely"

    async def test_blobs_with_no_corpus_prefix_are_refused_rather_than_guessed_at(
        self, data_dir: Path, evidence_bucket: str, s3_client: S3Client, objects_keyspace: SyncKeyspace
    ) -> None:
        await write_local_blob(data_dir, b"a disclosed file")
        local = FsEvidenceObjectStore(data_dir, subdirectory=BLOB_DIRECTORY.parent)
        unmapped = SyncKeyspace(
            name="blobs",
            local=local,
            remote=S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client),
            content_addressed=True,
        )
        service = EvidenceSyncService(keyspaces=(objects_keyspace, unmapped))

        with pytest.raises(UnsyncableKeyspace, match="raw/caselist/hsld26"):
            await service.plan()

    async def test_the_blob_keyspace_owns_its_prefix_so_nothing_is_planned_twice(
        self, service: EvidenceSyncService, data_dir: Path
    ) -> None:
        """A blob filed by hand under `objects/raw/…` belongs to the blob keyspace, not both."""
        key = await write_local_blob(data_dir, b"a disclosed file")
        write_local_object(data_dir, f"{BLOB_PREFIX}/{key}", b"a disclosed file")

        plan = await service.plan()

        assert len(plan.of(SyncAction.NEW)) == 1
        assert plan.of(SyncAction.NEW)[0].keyspace == "blobs"
        assert [planned.reason for planned in plan.of(SyncAction.SKIPPED)] == [
            "in the blobs keyspace, not this one"
        ]


# ------------------------------------------------------------------------------------------------
# Executing, and then converging (acceptance criterion 1)
# ------------------------------------------------------------------------------------------------


class TestExecuting:
    async def test_a_sync_uploads_exactly_what_the_plan_named(
        self, service: EvidenceSyncService, data_dir: Path, s3_client: S3Client, evidence_bucket: str
    ) -> None:
        write_local_object(data_dir, MANIFEST_KEY, b'{"sha256":"abc"}\n')
        write_local_object(data_dir, REPORT_KEY, b"{}")
        blob_key = await write_local_blob(data_dir, b"a disclosed file")

        plan = await service.plan()
        report = await service.execute(plan)

        assert sorted(planned.remote_key for planned in plan.transfers) == remote_keys(
            s3_client, evidence_bucket
        )
        assert remote_keys(s3_client, evidence_bucket) == sorted(
            [MANIFEST_KEY, REPORT_KEY, f"{BLOB_PREFIX}/{blob_key}"]
        )
        assert report.succeeded
        assert len(report.transferred) == 3
        assert report.bytes_transferred == 35

    async def test_a_second_sync_of_an_unchanged_store_reports_nothing_to_do(
        self, service: EvidenceSyncService, data_dir: Path, s3_operations: list[str]
    ) -> None:
        """Acceptance criterion 1's last clause, and the idempotence the PM asked for."""
        write_local_object(data_dir, MANIFEST_KEY, b'{"sha256":"abc"}\n')
        await write_local_blob(data_dir, b"a disclosed file")
        await service.execute(await service.plan())
        s3_operations.clear()

        second = await service.plan()

        assert second.counts["new"] == 0
        assert second.counts["changed"] == 0
        assert second.counts["skipped"] == 2
        assert second.remote_head_requests == 0
        assert "PutObject" not in s3_operations
        assert "HeadObject" not in s3_operations

    async def test_a_rewritten_manifest_is_re_uploaded_on_the_next_sync(
        self, service: EvidenceSyncService, data_dir: Path, s3_client: S3Client, evidence_bucket: str
    ) -> None:
        write_local_object(data_dir, MANIFEST_KEY, b"aaaaaaaaaa")
        await service.execute(await service.plan())
        write_local_object(data_dir, MANIFEST_KEY, b"bbbbbbbbbb")

        plan = await service.plan()
        await service.execute(plan)

        assert actions(plan, SyncAction.CHANGED) == [MANIFEST_KEY]
        stored = s3_client.get_object(Bucket=evidence_bucket, Key=MANIFEST_KEY)
        assert stored["Body"].read() == b"bbbbbbbbbb"

    async def test_transfers_happen_in_the_plans_order(
        self, service: EvidenceSyncService, data_dir: Path
    ) -> None:
        """An interrupted run and its resume have to walk the store the same way."""
        for name in ("c", "a", "b"):
            write_local_object(data_dir, f"manifests/hsld26/{name}.jsonl", name.encode())

        report = await service.execute(await service.plan())

        assert [outcome.key for outcome in report.outcomes] == [
            "manifests/hsld26/a.jsonl",
            "manifests/hsld26/b.jsonl",
            "manifests/hsld26/c.jsonl",
        ]


# ------------------------------------------------------------------------------------------------
# Verification (acceptance criterion 2)
# ------------------------------------------------------------------------------------------------


class RemoteStoreWithABadHead:
    """A remote store that stores correctly and then misreports what it holds.

    Stands in for a bucket that dropped or mangled the digest metadata. Only `head` lies; a store
    that also corrupted the bytes would be testing the adapter's own integrity check instead of
    this module's decision to ask a second time.
    """

    def __init__(self, real: S3EvidenceObjectStore, *, digest: str | None) -> None:
        self._real = real
        self._digest = digest

    async def list_objects(self, prefix: str) -> tuple[ObjectInfo, ...]:
        return await self._real.list_objects(prefix)

    async def head(self, key: str) -> ObjectInfo:
        recorded = await self._real.head(key)
        return ObjectInfo(key=key, size=recorded.size, sha256=self._digest)

    async def put_file(self, key: str, source: Path) -> ObjectInfo:
        return await self._real.put_file(key, source)

    async def get_file(self, key: str, destination: Path) -> ObjectInfo:
        return await self._real.get_file(key, destination)


class TestVerification:
    async def test_an_upload_is_confirmed_against_the_stores_own_head(
        self,
        service: EvidenceSyncService,
        data_dir: Path,
        s3_client: S3Client,
        evidence_bucket: str,
        s3_operations: list[str],
    ) -> None:
        digest = write_local_object(data_dir, MANIFEST_KEY, b'{"sha256":"abc"}\n')

        report = await service.execute(await service.plan())

        assert report.transferred[0].sha256 == digest
        assert s3_operations.count("HeadObject") >= 1
        head = s3_client.head_object(Bucket=evidence_bucket, Key=MANIFEST_KEY)
        assert head["Metadata"][SHA256_METADATA_NAME] == digest

    async def test_a_head_that_disagrees_with_the_upload_fails_that_object(
        self, data_dir: Path, evidence_bucket: str, s3_client: S3Client, journal: SyncJournal
    ) -> None:
        """Acceptance criterion 2: a mismatch is a failed object, not a transferred one."""
        write_local_object(data_dir, MANIFEST_KEY, b'{"sha256":"abc"}\n')
        local = FsEvidenceObjectStore(data_dir)
        lying = RemoteStoreWithABadHead(
            S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client), digest="0" * 64
        )
        service = EvidenceSyncService(
            keyspaces=(
                SyncKeyspace(name="objects", local=local, remote=lying, local_path_for=local.path_for),
            ),
            journal=journal,
            remote_name=evidence_bucket,
        )

        report = await service.execute(await service.plan())

        assert not report.succeeded
        assert [outcome.key for outcome in report.failed] == [MANIFEST_KEY]
        assert report.failed[0].error_code == "BLOB_INTEGRITY_ERROR"
        assert journal.entry_count == 0

    async def test_a_head_that_records_no_digest_fails_that_object(
        self, data_dir: Path, evidence_bucket: str, s3_client: S3Client
    ) -> None:
        """An upload nobody can verify is not an upload this platform reports as done."""
        write_local_object(data_dir, MANIFEST_KEY, b'{"sha256":"abc"}\n')
        local = FsEvidenceObjectStore(data_dir)
        silent = RemoteStoreWithABadHead(
            S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client), digest=None
        )
        service = EvidenceSyncService(
            keyspaces=(
                SyncKeyspace(name="objects", local=local, remote=silent, local_path_for=local.path_for),
            ),
        )

        report = await service.execute(await service.plan())

        assert [outcome.error_code for outcome in report.failed] == ["BLOB_INTEGRITY_ERROR"]

    async def test_a_downloaded_blob_whose_bytes_do_not_match_its_key_is_refused(
        self, service: EvidenceSyncService, data_dir: Path, s3_client: S3Client, evidence_bucket: str
    ) -> None:
        """Pulling: the landed digest is checked against the digest the key itself states."""
        digest = hashlib.sha256(b"what the key claims").hexdigest()
        key = f"sha256/{digest[0:2]}/{digest[2:4]}/{digest}"
        s3_client.put_object(
            Bucket=evidence_bucket,
            Key=f"{BLOB_PREFIX}/{key}",
            Body=b"not what the key claims",
            Metadata={SHA256_METADATA_NAME: hashlib.sha256(b"not what the key claims").hexdigest()},
        )

        report = await service.execute(await service.plan(direction=SyncDirection.PULL))

        assert [outcome.error_code for outcome in report.failed] == ["BLOB_INTEGRITY_ERROR"]
        assert not (data_dir / BLOB_DIRECTORY / digest[0:2] / digest[2:4] / digest).exists()

    async def test_a_download_whose_bytes_do_not_match_the_recorded_digest_is_refused(
        self, service: EvidenceSyncService, data_dir: Path, s3_client: S3Client, evidence_bucket: str
    ) -> None:
        """A named object: the adapter re-hashes before its atomic rename and refuses the file."""
        s3_client.put_object(
            Bucket=evidence_bucket,
            Key=MANIFEST_KEY,
            Body=b"the bytes that are really there",
            Metadata={SHA256_METADATA_NAME: "0" * 64},
        )

        report = await service.execute(await service.plan(direction=SyncDirection.PULL))

        assert [outcome.error_code for outcome in report.failed] == ["BLOB_INTEGRITY_ERROR"]
        assert not (data_dir / "objects" / MANIFEST_KEY).exists()


# ------------------------------------------------------------------------------------------------
# Resuming (acceptance criterion 3)
# ------------------------------------------------------------------------------------------------


class RemoteStoreThatStopsAfter:
    """A remote store that is killed part-way through a run, like a laptop closing.

    Raises `KeyboardInterrupt` rather than a store error on purpose: a store error is something
    :class:`EvidenceSyncService` collects and carries on from, and what is being tested here is the
    other thing — a run that ends without finishing, leaving only what the journal says.
    """

    def __init__(self, real: S3EvidenceObjectStore, *, after: int) -> None:
        self._real = real
        self._after = after
        self.uploads = 0

    async def list_objects(self, prefix: str) -> tuple[ObjectInfo, ...]:
        return await self._real.list_objects(prefix)

    async def head(self, key: str) -> ObjectInfo:
        return await self._real.head(key)

    async def put_file(self, key: str, source: Path) -> ObjectInfo:
        if self.uploads >= self._after:
            raise KeyboardInterrupt(f"interrupted before {key}")
        self.uploads += 1
        return await self._real.put_file(key, source)

    async def get_file(self, key: str, destination: Path) -> ObjectInfo:
        return await self._real.get_file(key, destination)


class TestResume:
    @staticmethod
    def build_service(
        data_dir: Path,
        evidence_bucket: str,
        remote: Any,
        journal: SyncJournal,
    ) -> EvidenceSyncService:
        local = FsEvidenceObjectStore(data_dir)
        return EvidenceSyncService(
            keyspaces=(
                SyncKeyspace(name="objects", local=local, remote=remote, local_path_for=local.path_for),
            ),
            journal=journal,
            remote_name=evidence_bucket,
            clock=FixedClock(),
        )

    async def test_a_sync_interrupted_after_two_objects_resumes_with_the_rest(
        self, data_dir: Path, evidence_bucket: str, s3_client: S3Client, s3_operations: list[str]
    ) -> None:
        """Acceptance criterion 3, with the interruption injected mid-run."""
        for name in ("a", "b", "c", "d"):
            write_local_object(data_dir, f"manifests/hsld26/{name}.jsonl", name.encode() * 4)
        real = S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client)
        interrupted = self.build_service(
            data_dir,
            evidence_bucket,
            RemoteStoreThatStopsAfter(real, after=2),
            SyncJournal.open(data_dir, environment="dev", remote=evidence_bucket),
        )

        with pytest.raises(KeyboardInterrupt):
            await interrupted.execute(await interrupted.plan())

        assert remote_keys(s3_client, evidence_bucket) == [
            "manifests/hsld26/a.jsonl",
            "manifests/hsld26/b.jsonl",
        ]

        resumed = self.build_service(
            data_dir,
            evidence_bucket,
            real,
            SyncJournal.open(data_dir, environment="dev", remote=evidence_bucket),
        )
        assert resumed.journal.entry_count == 2
        s3_operations.clear()

        plan = await resumed.plan()
        report = await resumed.execute(plan)

        assert actions(plan, SyncAction.NEW) == [
            "manifests/hsld26/c.jsonl",
            "manifests/hsld26/d.jsonl",
        ]
        assert actions(plan, SyncAction.SKIPPED) == [
            "manifests/hsld26/a.jsonl",
            "manifests/hsld26/b.jsonl",
        ]
        assert [planned.reason for planned in plan.of(SyncAction.SKIPPED)] == [
            "journaled at this digest",
            "journaled at this digest",
        ]
        # The two already-transferred objects cost nothing at all on the way back through.
        assert plan.remote_head_requests == 0
        assert report.succeeded
        assert len(remote_keys(s3_client, evidence_bucket)) == 4

    async def test_a_journal_entry_does_not_excuse_an_object_the_bucket_no_longer_holds(
        self, data_dir: Path, evidence_bucket: str, s3_client: S3Client
    ) -> None:
        """Presence comes from the listing; the journal is only allowed to make the digest free."""
        write_local_object(data_dir, MANIFEST_KEY, b"aaaa")
        service = self.build_service(
            data_dir,
            evidence_bucket,
            S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client),
            SyncJournal.open(data_dir, environment="dev", remote=evidence_bucket),
        )
        await service.execute(await service.plan())
        s3_client.delete_object(Bucket=evidence_bucket, Key=MANIFEST_KEY)

        plan = await service.plan()

        assert actions(plan, SyncAction.NEW) == [MANIFEST_KEY]

    async def test_a_journal_entry_does_not_excuse_an_object_that_changed_locally(
        self, data_dir: Path, evidence_bucket: str, s3_client: S3Client
    ) -> None:
        write_local_object(data_dir, MANIFEST_KEY, b"aaaa")
        service = self.build_service(
            data_dir,
            evidence_bucket,
            S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client),
            SyncJournal.open(data_dir, environment="dev", remote=evidence_bucket),
        )
        await service.execute(await service.plan())
        write_local_object(data_dir, MANIFEST_KEY, b"bbbb")

        plan = await service.plan()

        assert actions(plan, SyncAction.CHANGED) == [MANIFEST_KEY]


class TestTheJournalFile:
    async def test_an_entry_is_written_per_object_and_flushed(
        self, service: EvidenceSyncService, data_dir: Path, evidence_bucket: str
    ) -> None:
        digest = write_local_object(data_dir, MANIFEST_KEY, b'{"sha256":"abc"}\n')

        await service.execute(await service.plan())

        lines = (data_dir / "sync-journal" / "dev.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0]) == {
            "finished_at": FixedClock().now().isoformat(),
            "direction": "push",
            "keyspace": "objects",
            "key": MANIFEST_KEY,
            "sha256": digest,
            "size": 17,
            "remote": evidence_bucket,
        }

    async def test_the_journal_lives_beside_the_trees_it_describes_and_is_never_synced(
        self, service: EvidenceSyncService, data_dir: Path
    ) -> None:
        write_local_object(data_dir, MANIFEST_KEY, b"a")
        await service.execute(await service.plan())

        plan = await service.plan()

        assert (data_dir / "sync-journal" / "dev.jsonl").is_file()
        assert all("sync-journal" not in planned.local_key for planned in plan.objects)

    async def test_a_truncated_last_line_is_skipped_rather_than_failing_the_run(
        self, data_dir: Path, evidence_bucket: str
    ) -> None:
        """The last line of a journal is the one a killed process was in the middle of."""
        path = data_dir / "sync-journal" / "dev.jsonl"
        path.parent.mkdir(parents=True)
        good = JournalEntry(
            finished_at="2026-09-15T06:00:00+00:00",
            direction=SyncDirection.PUSH,
            keyspace="objects",
            key=MANIFEST_KEY,
            sha256="a" * 64,
            size=4,
            remote=evidence_bucket,
        )
        path.write_text(json.dumps(good.as_json()) + '\n{"direction": "pu', encoding="utf-8")

        journal = SyncJournal.open(data_dir, environment="dev", remote=evidence_bucket)

        assert journal.entry_count == 1
        assert (
            journal.verified_digest(keyspace="objects", direction=SyncDirection.PUSH, key=MANIFEST_KEY)
            == "a" * 64
        )

    async def test_entries_recorded_against_another_bucket_are_ignored(
        self, data_dir: Path, evidence_bucket: str
    ) -> None:
        elsewhere = SyncJournal.open(data_dir, environment="dev", remote="some-other-bucket")
        elsewhere.record(
            JournalEntry(
                finished_at="2026-09-15T06:00:00+00:00",
                direction=SyncDirection.PUSH,
                keyspace="objects",
                key=MANIFEST_KEY,
                sha256="a" * 64,
                size=4,
                remote="some-other-bucket",
            )
        )

        ours = SyncJournal.open(data_dir, environment="dev", remote=evidence_bucket)

        assert ours.entry_count == 0

    async def test_a_dry_runs_journal_writes_nothing(self, data_dir: Path) -> None:
        journal = SyncJournal.unwritten(remote="debate-dev-evidence")

        journal.record(
            JournalEntry(
                finished_at="2026-09-15T06:00:00+00:00",
                direction=SyncDirection.PUSH,
                keyspace="objects",
                key=MANIFEST_KEY,
                sha256="a" * 64,
                size=4,
                remote="debate-dev-evidence",
            )
        )

        assert journal.path is None
        assert not (data_dir / "sync-journal").exists()


# ------------------------------------------------------------------------------------------------
# Pulling, listing and fetching one object
# ------------------------------------------------------------------------------------------------


class TestPulling:
    async def test_a_pull_writes_the_bucket_into_the_local_store(
        self, service: EvidenceSyncService, data_dir: Path, s3_client: S3Client, evidence_bucket: str
    ) -> None:
        put_remote_object(s3_client, evidence_bucket, MANIFEST_KEY, b'{"sha256":"abc"}\n')

        plan = await service.plan(direction=SyncDirection.PULL)
        report = await service.execute(plan)

        assert actions(plan, SyncAction.NEW) == [MANIFEST_KEY]
        assert (data_dir / "objects" / MANIFEST_KEY).read_bytes() == b'{"sha256":"abc"}\n'
        assert report.succeeded

    async def test_a_pull_reports_what_only_the_local_store_has(
        self, service: EvidenceSyncService, data_dir: Path
    ) -> None:
        write_local_object(data_dir, MANIFEST_KEY, b"a")

        plan = await service.plan(direction=SyncDirection.PULL)

        assert actions(plan, SyncAction.WOULD_DELETE) == [MANIFEST_KEY]

    async def test_a_pull_stages_through_a_temporary_file_when_the_store_names_no_path(
        self, data_dir: Path, evidence_bucket: str, s3_client: S3Client
    ) -> None:
        """The port-only path, for a local store that cannot hand over a filename."""
        put_remote_object(s3_client, evidence_bucket, MANIFEST_KEY, b'{"sha256":"abc"}\n')
        service = EvidenceSyncService(
            keyspaces=(
                SyncKeyspace(
                    name="objects",
                    local=FsEvidenceObjectStore(data_dir),
                    remote=S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client),
                ),
            )
        )

        report = await service.execute(await service.plan(direction=SyncDirection.PULL))

        assert report.succeeded
        assert (data_dir / "objects" / MANIFEST_KEY).read_bytes() == b'{"sha256":"abc"}\n'

    async def test_a_push_stages_through_a_temporary_file_when_the_store_names_no_path(
        self, data_dir: Path, evidence_bucket: str, s3_client: S3Client
    ) -> None:
        write_local_object(data_dir, MANIFEST_KEY, b'{"sha256":"abc"}\n')
        service = EvidenceSyncService(
            keyspaces=(
                SyncKeyspace(
                    name="objects",
                    local=FsEvidenceObjectStore(data_dir),
                    remote=S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client),
                ),
            )
        )

        report = await service.execute(await service.plan())

        assert report.succeeded
        assert remote_keys(s3_client, evidence_bucket) == [MANIFEST_KEY]


class TestListingAndFetching:
    async def test_listing_returns_every_object_once(
        self, service: EvidenceSyncService, s3_client: S3Client, evidence_bucket: str
    ) -> None:
        put_remote_object(s3_client, evidence_bucket, MANIFEST_KEY, b"a")
        put_remote_object(s3_client, evidence_bucket, f"{BLOB_PREFIX}/sha256/ab/cd/{'ab' * 32}", b"b")

        listed = await service.list_remote()

        assert [info.key for info in listed] == [
            MANIFEST_KEY,
            f"{BLOB_PREFIX}/sha256/ab/cd/{'ab' * 32}",
        ]

    async def test_listing_a_prefix_returns_only_that_prefix(
        self, service: EvidenceSyncService, s3_client: S3Client, evidence_bucket: str
    ) -> None:
        put_remote_object(s3_client, evidence_bucket, MANIFEST_KEY, b"a")
        put_remote_object(s3_client, evidence_bucket, REPORT_KEY, b"b")

        listed = await service.list_remote("manifests/")

        assert [info.key for info in listed] == [MANIFEST_KEY]

    async def test_fetching_by_key_lands_it_in_the_local_store(
        self, service: EvidenceSyncService, data_dir: Path, s3_client: S3Client, evidence_bucket: str
    ) -> None:
        put_remote_object(s3_client, evidence_bucket, MANIFEST_KEY, b'{"sha256":"abc"}\n')

        await service.fetch(MANIFEST_KEY)

        assert (data_dir / "objects" / MANIFEST_KEY).read_bytes() == b'{"sha256":"abc"}\n'

    async def test_fetching_to_a_named_path_writes_there_instead(
        self, service: EvidenceSyncService, tmp_path: Path, s3_client: S3Client, evidence_bucket: str
    ) -> None:
        put_remote_object(s3_client, evidence_bucket, MANIFEST_KEY, b'{"sha256":"abc"}\n')
        destination = tmp_path / "out" / "manifest.jsonl"

        landed = await service.fetch(MANIFEST_KEY, destination)

        assert destination.read_bytes() == b'{"sha256":"abc"}\n'
        assert landed.sha256 == hashlib.sha256(b'{"sha256":"abc"}\n').hexdigest()

    async def test_fetching_a_blob_whose_bytes_do_not_match_its_key_is_refused(
        self, service: EvidenceSyncService, tmp_path: Path, s3_client: S3Client, evidence_bucket: str
    ) -> None:
        digest = hashlib.sha256(b"what the key claims").hexdigest()
        key = f"{BLOB_PREFIX}/sha256/{digest[0:2]}/{digest[2:4]}/{digest}"
        put_remote_object(s3_client, evidence_bucket, key, b"not what the key claims")

        with pytest.raises(BlobIntegrityError):
            await service.fetch(key, tmp_path / "blob")

    async def test_fetching_a_key_no_keyspace_can_place_says_so(
        self, service: EvidenceSyncService, tmp_path: Path
    ) -> None:
        service = EvidenceSyncService(
            keyspaces=(
                SyncKeyspace(
                    name="blobs",
                    local=service.keyspaces[1].local,
                    remote=service.keyspaces[1].remote,
                    remote_prefix=BLOB_PREFIX,
                    content_addressed=True,
                ),
            )
        )

        with pytest.raises(NotFound):
            await service.fetch("manifests/hsld26/2026-09-15.jsonl", tmp_path / "out")


# ------------------------------------------------------------------------------------------------
# Failures
# ------------------------------------------------------------------------------------------------


class RemoteStoreWithNoCredentials:
    """Every call fails the way an expired SSO session does."""

    def __init__(self, real: S3EvidenceObjectStore, *, profile: str) -> None:
        self._real = real
        self._hint = f"aws sso login --profile {profile}"
        self.attempts = 0

    async def list_objects(self, prefix: str) -> tuple[ObjectInfo, ...]:
        return await self._real.list_objects(prefix)

    async def head(self, key: str) -> ObjectInfo:
        return await self._real.head(key)

    async def put_file(self, key: str, source: Path) -> ObjectInfo:
        self.attempts += 1
        raise StoreCredentialsExpired("the AWS session has expired", hint=self._hint)

    async def get_file(self, key: str, destination: Path) -> ObjectInfo:
        return await self._real.get_file(key, destination)


class TestFailures:
    async def test_one_failed_object_does_not_abandon_the_rest(
        self, data_dir: Path, evidence_bucket: str, s3_client: S3Client
    ) -> None:
        for name in ("a", "b"):
            write_local_object(data_dir, f"manifests/hsld26/{name}.jsonl", name.encode())
        local = FsEvidenceObjectStore(data_dir)
        lying = RemoteStoreWithABadHead(
            S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client), digest="0" * 64
        )
        service = EvidenceSyncService(
            keyspaces=(
                SyncKeyspace(name="objects", local=local, remote=lying, local_path_for=local.path_for),
            )
        )

        report = await service.execute(await service.plan())

        assert len(report.failed) == 2
        assert not report.succeeded

    async def test_an_expired_session_ends_the_run_at_the_first_object(
        self, data_dir: Path, evidence_bucket: str, s3_client: S3Client
    ) -> None:
        """2,300 copies of "your session expired" is not a report."""
        for name in ("a", "b", "c"):
            write_local_object(data_dir, f"manifests/hsld26/{name}.jsonl", name.encode())
        local = FsEvidenceObjectStore(data_dir)
        expired = RemoteStoreWithNoCredentials(
            S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client), profile="debate-dev-evidence"
        )
        service = EvidenceSyncService(
            keyspaces=(
                SyncKeyspace(name="objects", local=local, remote=expired, local_path_for=local.path_for),
            )
        )

        with pytest.raises(StoreCredentialsExpired) as raised:
            await service.execute(await service.plan())

        assert expired.attempts == 1
        assert raised.value.hint == "aws sso login --profile debate-dev-evidence"

    async def test_a_service_with_no_keyspaces_is_a_programming_error(self) -> None:
        with pytest.raises(ValueError, match="at least one keyspace"):
            EvidenceSyncService(keyspaces=())


# ------------------------------------------------------------------------------------------------
# Sizing a real run
# ------------------------------------------------------------------------------------------------


@pytest.fixture
def corpus(data_dir: Path) -> Iterator[int]:
    """A miniature of the hsld26 corpus: many small blobs under one prefix."""
    yield 40


class TestCostAtVolume:
    async def test_a_first_sync_of_a_whole_corpus_heads_nothing(
        self, service: EvidenceSyncService, data_dir: Path, corpus: int, s3_operations: list[str]
    ) -> None:
        """What sizes the backfill: a first push is one list per prefix and one put per object."""
        for index in range(corpus):
            await write_local_blob(data_dir, f"disclosure {index}".encode())
        s3_operations.clear()

        plan = await service.plan()

        assert plan.counts["new"] == corpus
        assert plan.remote_head_requests == 0
        assert s3_operations.count("ListObjectsV2") == len(EVIDENCE_PREFIXES) + 1
        assert "HeadObject" not in s3_operations

    async def test_a_repeat_sync_of_a_whole_corpus_heads_nothing_either(
        self, service: EvidenceSyncService, data_dir: Path, corpus: int, s3_operations: list[str]
    ) -> None:
        for index in range(corpus):
            await write_local_blob(data_dir, f"disclosure {index}".encode())
        await service.execute(await service.plan())
        s3_operations.clear()

        plan = await service.plan()

        assert plan.counts["skipped"] == corpus
        assert plan.counts["new"] == 0
        assert plan.remote_head_requests == 0
        assert "HeadObject" not in s3_operations
        assert "PutObject" not in s3_operations
