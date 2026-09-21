"""`CaselistStatusService`: this machine against the bucket, snapshot by snapshot (ac4).

The bucket states it reads are made by the real publisher against moto — including the one the
manifest-last rule exists for, a publish killed after its sources and before its manifest — or by a
deliberate edit to the moto bucket or the local store. Expected counts come from
`tests/fixtures/caselist/expected_publish.json`, written by hand.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from tests.fixtures.caselist.build_synthetic_archives import SYNTHETIC_CASELIST
from tests.fixtures.caselist.interruptible_bucket import ScriptedBucket, SimulatedKill
from tests.fixtures.caselist.publish_expectations import (
    FICTIONAL_IDENTIFIERS,
    digest_of_body,
    expected_publish,
    expected_source_key,
)

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.publish_service import CaselistPublishService, PublishReport
from debate_core.application.caselist.status_service import (
    CaselistStatusReport,
    CaselistStatusService,
    NoCaselistEvidence,
    SnapshotStatus,
)
from debate_core.application.ports.evidence_store import EvidenceObjectStore, ObjectKey
from debate_core.integrations.s3 import SHA256_METADATA_NAME, S3EvidenceObjectStore

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

EXPECTED = expected_publish()
WEEKS = {week["snapshot"]: week for week in EXPECTED["snapshots"]}


async def publish(local: LocalEvidence, remote: EvidenceObjectStore, snapshot: str | None = None) -> PublishReport:
    service = CaselistPublishService(local=local, remote=remote)
    return await service.execute(await service.plan(SYNTHETIC_CASELIST, snapshot))


async def status(
    local: LocalEvidence, remote: EvidenceObjectStore, caselist: str | None = SYNTHETIC_CASELIST, snapshot: str | None = None
) -> CaselistStatusReport:
    return await CaselistStatusService(local=local, remote=remote).status(caselist, snapshot)


def by_snapshot(report: CaselistStatusReport) -> dict[str, SnapshotStatus]:
    return {entry.snapshot: entry for entry in report.snapshots}


def manifest_key(snapshot: str) -> str:
    return f"manifests/{SYNTHETIC_CASELIST}/{snapshot}.jsonl"


@pytest.fixture
def head_calls(s3_client: S3Client) -> list[str]:
    recorded: list[str] = []

    def record(params: dict[str, Any], **_: Any) -> None:
        recorded.append(str(params.get("Key")))

    s3_client.meta.events.register("provide-client-params.s3.HeadObject", record)
    return recorded


class TestBeforeAndAfterAPublish:
    async def test_nothing_published_yet_is_drift_in_every_snapshot(
        self, local: LocalEvidence, bucket: S3EvidenceObjectStore
    ) -> None:
        report = await status(local, bucket)

        assert not report.in_sync
        for snapshot, entry in by_snapshot(report).items():
            names = WEEKS[snapshot]["sources"]
            assert entry.local_manifest
            assert not entry.manifest_present
            assert entry.sources == len(names)
            assert entry.local_files == len(names)
            assert entry.published_sources == 0
            assert entry.missing_sources == tuple(sorted(digest_of_body(name) for name in names))
            assert entry.checksum_mismatches == ()

    async def test_after_a_complete_publish_every_snapshot_agrees(
        self, local: LocalEvidence, bucket: S3EvidenceObjectStore, head_calls: list[str]
    ) -> None:
        await publish(local, bucket)
        head_calls.clear()

        report = await status(local, bucket)

        assert report.in_sync
        assert [entry.snapshot for entry in report.snapshots] == ["2026-09-01", "2026-09-08", "2026-09-15"]
        for snapshot, entry in by_snapshot(report).items():
            count = len(WEEKS[snapshot]["sources"])
            assert (entry.sources, entry.local_files, entry.published_sources) == (count, count, count)
            assert entry.manifest_present
            assert entry.missing_sources == entry.missing_local == entry.checksum_mismatches == ()
        # One head per distinct key, however many snapshots name it: 14 sources and 3 manifests.
        assert sorted(head_calls) == sorted(set(head_calls))
        assert len(head_calls) == EXPECTED["totals"]["source_objects"] + EXPECTED["totals"]["manifest_objects"]

    async def test_one_snapshot_can_be_asked_about_alone(
        self, local: LocalEvidence, bucket: S3EvidenceObjectStore
    ) -> None:
        await publish(local, bucket, "2026-09-01")

        report = await status(local, bucket, snapshot="2026-09-01")

        assert [entry.snapshot for entry in report.snapshots] == ["2026-09-01"]
        assert report.in_sync

    async def test_with_no_caselist_every_caselist_either_side_holds_is_compared(
        self, local: LocalEvidence, bucket: S3EvidenceObjectStore
    ) -> None:
        await publish(local, bucket)

        report = await status(local, bucket, caselist=None)

        assert {entry.caselist for entry in report.snapshots} == {SYNTHETIC_CASELIST}
        assert report.in_sync

    async def test_a_caselist_neither_side_holds_is_refused_rather_than_reported_clean(
        self, local: LocalEvidence, bucket: S3EvidenceObjectStore
    ) -> None:
        with pytest.raises(NoCaselistEvidence):
            await status(local, bucket, caselist="hspf26")


class TestInterruptedPublishIsNeverClean:
    async def test_sources_without_their_manifest_are_drift_until_a_rerun_completes_them(
        self, local: LocalEvidence, bucket: S3EvidenceObjectStore
    ) -> None:
        """The case the ordering rule exists for, end to end.

        Killed after every source of the second week is in the bucket and before its manifest.
        The sources are all there — `published_sources` says so — and the snapshot is still not
        in sync, because a manifest is what says a snapshot is whole. A re-run of the same publish
        writes the manifest, and only then is it clean.
        """
        second_manifest = manifest_key("2026-09-08")

        def kill_at_second_manifest(key: ObjectKey, _: int) -> None:
            if key == second_manifest:
                raise SimulatedKill

        scripted = ScriptedBucket(bucket, kill_at_second_manifest)
        with pytest.raises(SimulatedKill):
            await publish(local, scripted)
        await scripted.settle()

        interrupted = by_snapshot(await status(local, bucket))
        second = interrupted["2026-09-08"]
        assert second.published_sources == len(WEEKS["2026-09-08"]["sources"])
        assert second.missing_sources == ()
        assert not second.manifest_present
        assert not second.in_sync
        assert interrupted["2026-09-01"].in_sync
        assert not interrupted["2026-09-15"].in_sync

        await publish(local, bucket)

        assert (await status(local, bucket)).in_sync


class TestDrift:
    async def test_a_source_the_bucket_lost_is_missing(
        self, local: LocalEvidence, bucket: S3EvidenceObjectStore, s3_client: S3Client, evidence_bucket: str
    ) -> None:
        await publish(local, bucket)
        s3_client.delete_object(Bucket=evidence_bucket, Key=expected_source_key("harbor-aff"))

        report = by_snapshot(await status(local, bucket))

        lost = digest_of_body("harbor-aff")
        for snapshot in ("2026-09-01", "2026-09-08", "2026-09-15"):
            assert report[snapshot].missing_sources == (lost,)
            assert not report[snapshot].in_sync

    async def test_other_bytes_under_a_source_key_are_a_checksum_mismatch(
        self, local: LocalEvidence, bucket: S3EvidenceObjectStore, s3_client: S3Client, evidence_bucket: str
    ) -> None:
        await publish(local, bucket)
        key = expected_source_key("bayview-semis-neg")
        size = s3_client.head_object(Bucket=evidence_bucket, Key=key)["ContentLength"]
        s3_client.put_object(
            Bucket=evidence_bucket, Key=key, Body=b"x" * size, Metadata={SHA256_METADATA_NAME: "0" * 64}
        )

        report = by_snapshot(await status(local, bucket))

        assert report["2026-09-15"].checksum_mismatches == (key,)
        assert report["2026-09-15"].published_sources == len(WEEKS["2026-09-15"]["sources"]) - 1
        assert not report["2026-09-15"].in_sync
        assert report["2026-09-08"].in_sync

    async def test_a_manifest_that_differs_from_the_local_one_is_a_checksum_mismatch(
        self, local: LocalEvidence, bucket: S3EvidenceObjectStore, s3_client: S3Client, evidence_bucket: str
    ) -> None:
        await publish(local, bucket)
        key = manifest_key("2026-09-01")
        s3_client.put_object(
            Bucket=evidence_bucket, Key=key, Body=b"{}\n", Metadata={SHA256_METADATA_NAME: "1" * 64}
        )

        report = by_snapshot(await status(local, bucket))

        assert report["2026-09-01"].checksum_mismatches == (key,)
        assert not report["2026-09-01"].in_sync

    async def test_a_source_this_machine_lost_is_missing_locally(
        self, local: LocalEvidence, bucket: S3EvidenceObjectStore, imported_data_dir: Path
    ) -> None:
        await publish(local, bucket)
        digest = digest_of_body("seaside-round-5-aff")
        (imported_data_dir / "blobs" / "sha256" / digest[0:2] / digest[2:4] / digest).unlink()

        report = by_snapshot(await status(local, bucket))

        assert report["2026-09-15"].missing_local == (digest,)
        assert report["2026-09-15"].local_files == len(WEEKS["2026-09-15"]["sources"]) - 1
        assert not report["2026-09-15"].in_sync

    async def test_a_snapshot_only_the_bucket_holds_is_drift(
        self, local: LocalEvidence, bucket: S3EvidenceObjectStore, imported_data_dir: Path
    ) -> None:
        await publish(local, bucket)
        (imported_data_dir / "objects" / manifest_key("2026-09-15")).unlink()

        report = by_snapshot(await status(local, bucket))

        remote_only = report["2026-09-15"]
        assert not remote_only.local_manifest
        assert remote_only.manifest_present
        assert not remote_only.in_sync

    async def test_a_suppressed_source_is_counted_not_missed(
        self, local: LocalEvidence, bucket: S3EvidenceObjectStore
    ) -> None:
        suppressed = {digest_of_body("harbor-octas-neg")}
        service = CaselistPublishService(local=local, remote=bucket, suppressed=suppressed)
        await service.execute(await service.plan(SYNTHETIC_CASELIST, "2026-09-01"))

        report = await CaselistStatusService(local=local, remote=bucket, suppressed=suppressed).status(
            SYNTHETIC_CASELIST, "2026-09-01"
        )

        (entry,) = report.snapshots
        assert entry.suppressed == 1
        assert entry.sources == len(WEEKS["2026-09-01"]["sources"]) - 1
        assert entry.in_sync

    async def test_a_drift_report_names_digests_and_keys_and_nothing_identifying(
        self, local: LocalEvidence, bucket: S3EvidenceObjectStore, s3_client: S3Client, evidence_bucket: str
    ) -> None:
        await publish(local, bucket)
        s3_client.delete_object(Bucket=evidence_bucket, Key=expected_source_key("harbor-aff"))
        s3_client.delete_object(Bucket=evidence_bucket, Key=manifest_key("2026-09-08"))

        report = await status(local, bucket)

        rendered = repr(report)
        assert digest_of_body("harbor-aff") in rendered
        for identifier in FICTIONAL_IDENTIFIERS:
            assert identifier not in rendered, identifier
