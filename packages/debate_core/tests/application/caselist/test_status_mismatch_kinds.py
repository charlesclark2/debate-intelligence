"""`CaselistStatusService` tells a manifest mismatch from a source mismatch (`v1-e30-t12`).

A manifest is not content-addressed: this machine rewrites one in place after a camp metadata
re-import (`v1-e30-t08`) or a removal, and the bucket's copy differs until the next publish. A
source is filed under the digest of its bytes, so other bytes under its key are never expected.
The two are told apart by comparing each mismatched key with that snapshot's own manifest key,
never by a key prefix: `manifests/` also holds the suppression records, and a complete archive's
manifest is one level further down (`manifests/<caselist>/full/<date>.jsonl`).

Also here: the suppressed objects a removal left, told per caselist, which is the level the
comparison collects them at (one listing of each caselist's source prefix).

The bucket states are made by the real publisher against moto, then by a deliberate edit to the
local store or the bucket. Synthetic archives only.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_synthetic_archives import SYNTHETIC_CASELIST
from tests.fixtures.caselist.publish_expectations import digest_of_body, expected_source_key

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.status_service import (
    CaselistStatusReport,
    CaselistStatusService,
    SnapshotStatus,
)
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.ports.evidence_store import EvidenceObjectStore
from debate_core.application.ports.suppression import ReasonCode, SuppressionAction, SuppressionEntry
from debate_core.integrations.s3 import SHA256_METADATA_NAME, S3EvidenceObjectStore
from debate_core.testing.fakes import InMemoryAppendOnlyRecord, empty_suppression_list

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

COMPLETE_ARCHIVE = "full/2026-09-20"


def manifest_key(snapshot: str) -> str:
    return f"manifests/{SYNTHETIC_CASELIST}/{snapshot}.jsonl"


async def publish(local: LocalEvidence, remote: EvidenceObjectStore) -> None:
    service = CaselistPublishService(local=local, remote=remote, suppression=empty_suppression_list())
    report = await service.execute(await service.plan(SYNTHETIC_CASELIST))
    assert report.succeeded


async def status(
    local: LocalEvidence, remote: EvidenceObjectStore, suppression: RecordedSuppressionList | None = None
) -> CaselistStatusReport:
    return await CaselistStatusService(
        local=local, remote=remote, suppression=suppression or empty_suppression_list()
    ).status(SYNTHETIC_CASELIST)


def by_snapshot(report: CaselistStatusReport) -> dict[str, SnapshotStatus]:
    return {entry.snapshot: entry for entry in report.snapshots}


def rewrite_local_manifest(data_dir: Path, snapshot: str) -> None:
    """Change this machine's manifest bytes and none of its sources, as a re-import or removal does.

    The summary row is written again with other separators: the same facts, other bytes.
    """
    path = data_dir / "objects" / manifest_key(snapshot)
    before = path.read_bytes()
    lines = before.decode("utf-8").splitlines()
    lines[-1] = json.dumps(json.loads(lines[-1]), separators=(", ", ": "), sort_keys=True)
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    assert path.read_bytes() != before


def replace_in_bucket(s3_client: S3Client, bucket: str, key: str) -> None:
    """Other bytes of the same size under `key`, with some other digest recorded."""
    size = s3_client.head_object(Bucket=bucket, Key=key)["ContentLength"]
    s3_client.put_object(Bucket=bucket, Key=key, Body=b"x" * size, Metadata={SHA256_METADATA_NAME: "0" * 64})


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


class TestMismatchKinds:
    async def test_a_rewritten_local_manifest_is_a_manifest_mismatch_and_no_source_mismatch(
        self, local: LocalEvidence, bucket: S3EvidenceObjectStore, imported_data_dir: Path
    ) -> None:
        await publish(local, bucket)
        rewrite_local_manifest(imported_data_dir, "2026-09-01")

        report = await status(local, bucket)

        rewritten = by_snapshot(report)["2026-09-01"]
        assert rewritten.checksum_mismatches == (manifest_key("2026-09-01"),)
        assert rewritten.manifest_mismatched
        assert rewritten.source_mismatches == ()
        assert rewritten.mismatch_kind(manifest_key("2026-09-01")) == "manifest"
        assert report.manifest_mismatched == (rewritten,)
        assert report.source_mismatched == ()
        assert not report.in_sync

    async def test_other_bytes_under_a_source_key_are_a_source_mismatch_and_no_manifest_mismatch(
        self, local: LocalEvidence, bucket: S3EvidenceObjectStore, s3_client: S3Client, evidence_bucket: str
    ) -> None:
        await publish(local, bucket)
        key = expected_source_key("bayview-semis-neg")
        replace_in_bucket(s3_client, evidence_bucket, key)

        report = await status(local, bucket)

        holder = by_snapshot(report)["2026-09-15"]
        assert holder.source_mismatches == (key,)
        assert not holder.manifest_mismatched
        assert holder.mismatch_kind(key) == "source"
        assert report.source_mismatched == (holder,)
        assert report.manifest_mismatched == ()

    async def test_one_snapshot_with_both_kinds_is_counted_under_each(
        self,
        local: LocalEvidence,
        bucket: S3EvidenceObjectStore,
        imported_data_dir: Path,
        s3_client: S3Client,
        evidence_bucket: str,
    ) -> None:
        await publish(local, bucket)
        key = expected_source_key("bayview-semis-neg")
        replace_in_bucket(s3_client, evidence_bucket, key)
        rewrite_local_manifest(imported_data_dir, "2026-09-15")

        report = await status(local, bucket)

        both = by_snapshot(report)["2026-09-15"]
        assert set(both.checksum_mismatches) == {key, manifest_key("2026-09-15")}
        assert both.manifest_mismatched
        assert both.source_mismatches == (key,)
        assert [both.mismatch_kind(one) for one in sorted(both.checksum_mismatches)] == ["manifest", "source"]
        assert report.manifest_mismatched == report.source_mismatched == (both,)

    async def test_a_complete_archive_manifest_is_told_by_its_own_key(
        self, local: LocalEvidence, bucket: S3EvidenceObjectStore, imported_data_dir: Path
    ) -> None:
        """`manifests/<caselist>/full/<date>.jsonl` is that snapshot's manifest, one level down."""
        weekly = imported_data_dir / "objects" / manifest_key("2026-09-15")
        complete = imported_data_dir / "objects" / manifest_key(COMPLETE_ARCHIVE)
        complete.parent.mkdir(parents=True)
        shutil.copyfile(weekly, complete)
        await publish(local, bucket)
        rewrite_local_manifest(imported_data_dir, COMPLETE_ARCHIVE)

        report = await status(local, bucket)

        entry = by_snapshot(report)[COMPLETE_ARCHIVE]
        assert entry.manifest_key == manifest_key(COMPLETE_ARCHIVE)
        assert entry.checksum_mismatches == (manifest_key(COMPLETE_ARCHIVE),)
        assert entry.manifest_mismatched
        assert entry.source_mismatches == ()
        assert report.manifest_mismatched == (entry,)
        assert by_snapshot(report)["2026-09-15"].in_sync


class TestSuppressedObjectsPerCaselist:
    async def test_a_suppressed_object_is_told_under_the_caselist_whose_sources_it_is_among(
        self, local: LocalEvidence, bucket: S3EvidenceObjectStore, s3_client: S3Client, evidence_bucket: str
    ) -> None:
        await publish(local, bucket)
        leftover = hashlib.sha256(b"a synthetic later upload nobody's manifest names").hexdigest()
        key = f"raw/caselist/{SYNTHETIC_CASELIST}/sha256/{leftover[0:2]}/{leftover[2:4]}/{leftover}"
        s3_client.put_object(Bucket=evidence_bucket, Key=key, Body=b"leftover")

        report = await status(local, bucket, suppressing(leftover))

        assert report.suppressed_objects == (key,)
        assert report.suppressed_objects_of(SYNTHETIC_CASELIST) == (key,)
        assert report.suppressed_objects_of("openev") == ()
        assert report.drifted == ()
        assert not report.in_sync

    async def test_a_snapshot_still_naming_a_suppressed_source_counts_its_rows(
        self, local: LocalEvidence, bucket: S3EvidenceObjectStore
    ) -> None:
        await publish(local, bucket)
        suppressed = digest_of_body("harbor-octas-neg")

        report = await status(local, bucket, suppressing(suppressed))

        # expected_publish.json: the first two weeks hold it, the third does not.
        assert {entry.snapshot: entry.suppressed_rows for entry in report.snapshots} == {
            "2026-09-01": (suppressed,),
            "2026-09-08": (suppressed,),
            "2026-09-15": (),
        }
        assert report.suppressed_objects_of(SYNTHETIC_CASELIST) == (expected_source_key("harbor-octas-neg"),)
