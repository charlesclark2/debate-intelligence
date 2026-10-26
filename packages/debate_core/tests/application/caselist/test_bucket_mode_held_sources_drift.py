"""In bucket mode, a source the bucket holds at the manifest's digest is present (`v1-e40-t13`).

A cloud run's working copy is restored from the bucket's manifests and parsed store, without raw
sources, so this machine holds only what the run itself downloaded. The comparison then counts a
source the manifest names, that this machine lacks and the bucket holds with the manifest's digest
and size, as present: not drift, so the report stage confirms the snapshot and retention releases
its download. Everything else that was drift still is, and local mode is unchanged.

The bucket states are made by the real publisher against moto, and the restored working copy by
deleting the local blobs the publish read; the bucket's other bytes by a deliberate edit to the
moto bucket. Expected digests come from `tests/fixtures/caselist/expected_publish.json`, written by
hand. Nothing here opens a socket.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from tests.fixtures.caselist.build_synthetic_archives import SYNTHETIC_CASELIST
from tests.fixtures.caselist.publish_expectations import (
    digest_of_body,
    expected_publish,
    expected_source_key,
)

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.status_service import (
    CaselistStatusService,
    SnapshotStatus,
)
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.caselist_sync import DriftKind, SnapshotDrift
from debate_core.application.ports.suppression import ReasonCode, SuppressionAction, SuppressionEntry
from debate_core.integrations.s3 import SHA256_METADATA_NAME, S3EvidenceObjectStore
from debate_core.testing.fakes.suppression import InMemoryAppendOnlyRecord, empty_suppression_list

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

EXPECTED = expected_publish()
WEEKS = {week["snapshot"]: week for week in EXPECTED["snapshots"]}
WEEK: str = "2026-09-15"
"""The newest synthetic week: the one these tests compare."""
SOURCES: tuple[str, ...] = tuple(sorted(digest_of_body(name) for name in WEEKS[WEEK]["sources"]))
LOST: str = "seaside-round-5-aff"
"""One of the week's bodies, whose bucket object a test takes away or changes."""


async def publish_everything(local: LocalEvidence, remote: S3EvidenceObjectStore) -> None:
    service = CaselistPublishService(local=local, remote=remote, suppression=empty_suppression_list())
    report = await service.execute(await service.plan(SYNTHETIC_CASELIST))
    assert all(one.complete for one in report.snapshots), "the premise: the bucket holds every week"


def restored_without_raw_sources(data_dir: Path) -> None:
    """What a cloud run's restore leaves: the manifests and no raw source at all."""
    shutil.rmtree(data_dir / "blobs")


async def compared(
    local: LocalEvidence,
    remote: S3EvidenceObjectStore,
    *,
    bucket_mode: bool,
    suppression: RecordedSuppressionList | None = None,
) -> SnapshotStatus:
    report = await CaselistStatusService(
        local=local,
        remote=remote,
        suppression=suppression or empty_suppression_list(),
        bucket_mode=bucket_mode,
    ).status(SYNTHETIC_CASELIST, WEEK)
    (entry,) = report.snapshots
    assert report.in_sync is entry.in_sync, "one snapshot asked about, nothing else found"
    return entry


def suppressing(sha256: str) -> RecordedSuppressionList:
    return RecordedSuppressionList(
        InMemoryAppendOnlyRecord(
            "suppression list",
            [
                SuppressionEntry(
                    action=SuppressionAction.SUPPRESS,
                    sha256=sha256,
                    recorded_at=datetime(2026, 9, 30, 12, 0, tzinfo=UTC),
                    reason=ReasonCode.REQUESTED_BY_TEAM,
                    request_id="RM-2026-01",
                ).to_line()
            ],
        )
    )


@pytest.fixture
def s3_calls(s3_client: S3Client) -> list[tuple[str, str]]:
    """Every object request the comparison makes: its operation and key."""
    recorded: list[tuple[str, str]] = []

    def record(operation: str) -> Callable[..., None]:
        def handler(params: dict[str, Any], **_: Any) -> None:
            recorded.append((operation, str(params.get("Key"))))

        return handler

    for operation in ("HeadObject", "GetObject"):
        s3_client.meta.events.register(f"provide-client-params.s3.{operation}", record(operation))
    return recorded


class TestARestoredWorkingCopyIsNotDrift:
    async def test_in_bucket_mode_sources_the_bucket_holds_at_the_manifests_digests_are_not_drift(
        self, local: LocalEvidence, bucket: S3EvidenceObjectStore, imported_data_dir: Path
    ) -> None:
        await publish_everything(local, bucket)
        restored_without_raw_sources(imported_data_dir)

        entry = await compared(local, bucket, bucket_mode=True)

        assert entry.in_sync
        assert not entry.incomplete
        assert entry.missing_local == ()
        assert entry.held_only_in_bucket == SOURCES
        assert entry.local_files == 0, "the facts stay visible: this machine holds none of them"
        assert entry.published_sources == entry.sources == len(SOURCES)
        assert SnapshotDrift.of(entry).kinds == ()

    async def test_in_bucket_mode_a_source_this_machine_holds_is_still_a_local_file(
        self, local: LocalEvidence, bucket: S3EvidenceObjectStore, imported_data_dir: Path
    ) -> None:
        """Only the sources this machine lacks are held only in the bucket: a new file joined older ones."""
        await publish_everything(local, bucket)
        kept = digest_of_body(LOST)
        for digest in SOURCES:
            if digest != kept:
                (imported_data_dir / "blobs" / "sha256" / digest[0:2] / digest[2:4] / digest).unlink()

        entry = await compared(local, bucket, bucket_mode=True)

        assert entry.in_sync
        assert entry.local_files == 1
        assert entry.held_only_in_bucket == tuple(digest for digest in SOURCES if digest != kept)

    async def test_the_same_working_copy_in_local_mode_is_drift_as_it_always_was(
        self, local: LocalEvidence, bucket: S3EvidenceObjectStore, imported_data_dir: Path
    ) -> None:
        await publish_everything(local, bucket)
        restored_without_raw_sources(imported_data_dir)

        entry = await compared(local, bucket, bucket_mode=False)

        assert not entry.in_sync
        assert entry.incomplete
        assert entry.missing_local == SOURCES
        assert entry.held_only_in_bucket == ()
        assert entry.local_files == 0
        assert SnapshotDrift.of(entry).kinds == (DriftKind.MISSING,)

    async def test_bucket_mode_reads_no_bytes_and_heads_what_local_mode_heads(
        self,
        local: LocalEvidence,
        bucket: S3EvidenceObjectStore,
        imported_data_dir: Path,
        s3_calls: list[tuple[str, str]],
    ) -> None:
        """No download decides presence, and no request is added: the heads made for `published_sources`."""
        await publish_everything(local, bucket)
        restored_without_raw_sources(imported_data_dir)
        s3_calls.clear()
        await compared(local, bucket, bucket_mode=False)
        in_local_mode = sorted(s3_calls)
        s3_calls.clear()

        await compared(local, bucket, bucket_mode=True)

        assert sorted(s3_calls) == in_local_mode
        assert [operation for operation, _ in s3_calls].count("HeadObject") == len(SOURCES) + 1
        assert not [call for call in s3_calls if call[0] == "GetObject"], "nothing is downloaded"


class TestWhatIsStillDriftInBucketMode:
    async def test_a_source_the_bucket_lacks_is_drift(
        self,
        local: LocalEvidence,
        bucket: S3EvidenceObjectStore,
        imported_data_dir: Path,
        s3_client: S3Client,
        evidence_bucket: str,
    ) -> None:
        await publish_everything(local, bucket)
        restored_without_raw_sources(imported_data_dir)
        s3_client.delete_object(Bucket=evidence_bucket, Key=expected_source_key(LOST))

        entry = await compared(local, bucket, bucket_mode=True)

        lost = digest_of_body(LOST)
        assert not entry.in_sync
        assert entry.missing_local == (lost,)
        assert entry.missing_sources == (lost,)
        assert lost not in entry.held_only_in_bucket
        assert entry.held_only_in_bucket == tuple(digest for digest in SOURCES if digest != lost)
        assert DriftKind.MISSING in SnapshotDrift.of(entry).kinds

    async def test_a_source_the_bucket_holds_with_another_digest_is_drift(
        self,
        local: LocalEvidence,
        bucket: S3EvidenceObjectStore,
        imported_data_dir: Path,
        s3_client: S3Client,
        evidence_bucket: str,
    ) -> None:
        """The same size, so only the recorded digest tells the bytes apart."""
        await publish_everything(local, bucket)
        key = expected_source_key(LOST)
        size = s3_client.head_object(Bucket=evidence_bucket, Key=key)["ContentLength"]
        restored_without_raw_sources(imported_data_dir)
        s3_client.put_object(
            Bucket=evidence_bucket, Key=key, Body=b"x" * size, Metadata={SHA256_METADATA_NAME: "1" * 64}
        )

        entry = await compared(local, bucket, bucket_mode=True)

        assert not entry.in_sync
        assert entry.checksum_mismatches == (key,)
        assert entry.missing_local == (digest_of_body(LOST),)
        assert digest_of_body(LOST) not in entry.held_only_in_bucket
        assert SnapshotDrift.of(entry).kinds == (DriftKind.SOURCE, DriftKind.MISSING)

    async def test_a_source_the_bucket_holds_with_no_recorded_digest_is_drift(
        self,
        local: LocalEvidence,
        bucket: S3EvidenceObjectStore,
        imported_data_dir: Path,
        s3_client: S3Client,
        evidence_bucket: str,
    ) -> None:
        await publish_everything(local, bucket)
        key = expected_source_key(LOST)
        body = s3_client.get_object(Bucket=evidence_bucket, Key=key)["Body"].read()
        restored_without_raw_sources(imported_data_dir)
        s3_client.put_object(Bucket=evidence_bucket, Key=key, Body=body)

        entry = await compared(local, bucket, bucket_mode=True)

        assert not entry.in_sync
        assert entry.checksum_mismatches == (key,)
        assert entry.missing_local == (digest_of_body(LOST),)
        assert digest_of_body(LOST) not in entry.held_only_in_bucket

    async def test_a_manifest_the_bucket_lacks_is_drift(
        self,
        local: LocalEvidence,
        bucket: S3EvidenceObjectStore,
        imported_data_dir: Path,
        s3_client: S3Client,
        evidence_bucket: str,
    ) -> None:
        await publish_everything(local, bucket)
        restored_without_raw_sources(imported_data_dir)
        s3_client.delete_object(Bucket=evidence_bucket, Key=f"manifests/{SYNTHETIC_CASELIST}/{WEEK}.jsonl")

        entry = await compared(local, bucket, bucket_mode=True)

        assert not entry.manifest_present
        assert not entry.in_sync
        assert entry.incomplete

    async def test_a_suppressed_row_is_drift(
        self, local: LocalEvidence, bucket: S3EvidenceObjectStore, imported_data_dir: Path
    ) -> None:
        await publish_everything(local, bucket)
        restored_without_raw_sources(imported_data_dir)
        suppressed = digest_of_body(LOST)

        entry = await compared(local, bucket, bucket_mode=True, suppression=suppressing(suppressed))

        assert entry.suppressed_rows == (suppressed,)
        assert not entry.in_sync
        assert suppressed not in entry.held_only_in_bucket
