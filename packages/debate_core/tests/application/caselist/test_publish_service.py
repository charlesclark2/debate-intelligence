"""`CaselistPublishService` against a moto bucket: what lands, what is skipped, what is withheld.

The bucket is moto's and the local store is the real filesystem store holding the three synthetic
weeks, imported by the real importer (see `conftest.py`). Every expected key, count and object set
comes from `tests/fixtures/caselist/expected_publish.json`, written by hand from the fixture's
tables — never from a run of this service (working agreements §6).

`PutObject` calls are counted at botocore's own event hook, so "uploads nothing" means no request
was built for AWS, not that a counter this code keeps about itself stayed at zero.

The interrupted cases use :class:`ScriptedBucket`, a wrapper that passes every call through to the
real S3 adapter and raises when told to. :class:`SimulatedKill` is a `BaseException`, like the
`KeyboardInterrupt` or `SystemExit` an operator's Ctrl-C or a killed job produces: the service does
not catch it, so the run stops where it stands, and what the bucket holds afterwards is exactly what
a real interruption would leave.

Nothing here reaches AWS; `packages/debate_core/tests/conftest.py` builds the bucket in moto.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from tests.fixtures.caselist.build_synthetic_archives import DOCUMENT_BODIES, SYNTHETIC_CASELIST
from tests.fixtures.caselist.publish_expectations import (
    FICTIONAL_IDENTIFIERS,
    digest_of_body,
    expected_publish,
    expected_source_key,
)

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.publish_service import (
    CaselistPublishService,
    ManifestOutcome,
    NothingToPublish,
    PublishReport,
    SourceResult,
)
from debate_core.application.errors import StoreCredentialsExpired, StoreUnavailable
from debate_core.application.ports.evidence_store import ObjectInfo, ObjectKey
from debate_core.integrations.local import FsEvidenceObjectStore
from debate_core.integrations.s3 import SHA256_METADATA_NAME, S3EvidenceObjectStore

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

EXPECTED = expected_publish()
WEEKS = {week["snapshot"]: week for week in EXPECTED["snapshots"]}
EVERY_BODY = sorted({name for week in EXPECTED["snapshots"] for name in week["sources"]})
EXPECTED_SOURCE_KEYS = {expected_source_key(name) for name in EVERY_BODY}
EXPECTED_MANIFEST_KEYS = {f"manifests/{SYNTHETIC_CASELIST}/{week}.jsonl" for week in WEEKS}


class SimulatedKill(BaseException):
    """What a Ctrl-C or a killed process looks like to the code it interrupts."""


class ScriptedBucket:
    """The real S3 store, with a hook that may raise before a `put_file` reaches it.

    Uploads already started when a :class:`SimulatedKill` lands keep running in the adapter's
    worker threads — in a real killed process they would die with it — so a test awaits
    :meth:`settle` before it reads the bucket, and what it reads is then stable.
    """

    def __init__(
        self, inner: S3EvidenceObjectStore, before_put: Callable[[ObjectKey, int], None] | None = None
    ) -> None:
        self.inner = inner
        self.before_put = before_put
        self.puts = 0
        self._uploads: list[asyncio.Future[ObjectInfo]] = []

    async def settle(self) -> None:
        """Wait for every upload that was started, however its caller ended."""
        await asyncio.gather(*self._uploads, return_exceptions=True)

    async def list_objects(self, prefix: str) -> tuple[ObjectInfo, ...]:
        return await self.inner.list_objects(prefix)

    async def head(self, key: ObjectKey) -> ObjectInfo:
        return await self.inner.head(key)

    async def put_file(self, key: ObjectKey, source: Path) -> ObjectInfo:
        self.puts += 1
        if self.before_put is not None:
            self.before_put(key, self.puts)
        upload = asyncio.ensure_future(self.inner.put_file(key, source))
        self._uploads.append(upload)
        return await asyncio.shield(upload)

    async def get_file(self, key: ObjectKey, destination: Path) -> ObjectInfo:
        return await self.inner.get_file(key, destination)


# ------------------------------------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------------------------------------


@pytest.fixture
def put_keys(s3_client: S3Client) -> list[str]:
    """Every key a `PutObject` request was built for, in order, from botocore's own events."""
    recorded: list[str] = []

    def record(params: dict[str, Any], **_: Any) -> None:
        recorded.append(str(params.get("Key")))

    s3_client.meta.events.register("provide-client-params.s3.PutObject", record)
    return recorded


@pytest.fixture
def local(imported_data_dir: Path) -> LocalEvidence:
    objects = FsEvidenceObjectStore(imported_data_dir)
    blobs = FsEvidenceObjectStore(imported_data_dir, subdirectory=Path("blobs"))
    return LocalEvidence(objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for)


@pytest.fixture
def bucket(evidence_bucket: str, s3_client: S3Client) -> S3EvidenceObjectStore:
    return S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client)


def service_over(local: LocalEvidence, remote: Any, **options: Any) -> CaselistPublishService:
    return CaselistPublishService(local=local, remote=remote, **options)


async def publish(service: CaselistPublishService, snapshot: str | None = None) -> PublishReport:
    return await service.execute(await service.plan(SYNTHETIC_CASELIST, snapshot))


def bucket_keys(client: S3Client, bucket: str) -> set[str]:
    listing = client.list_objects_v2(Bucket=bucket)
    return {str(stored.get("Key")) for stored in listing.get("Contents", [])}


def version_count(client: S3Client, bucket: str, key: str) -> int:
    versions = client.list_object_versions(Bucket=bucket, Prefix=key).get("Versions", [])
    return sum(1 for version in versions if version.get("Key") == key)


# ------------------------------------------------------------------------------------------------
# ac1: each distinct source once, with a SHA-256 checksum; one manifest per snapshot
# ------------------------------------------------------------------------------------------------


class TestFirstPublish:
    async def test_every_distinct_source_lands_once_and_one_manifest_per_snapshot(
        self,
        local: LocalEvidence,
        bucket: S3EvidenceObjectStore,
        s3_client: S3Client,
        evidence_bucket: str,
        put_keys: list[str],
    ) -> None:
        report = await publish(service_over(local, bucket))

        assert report.succeeded
        assert bucket_keys(s3_client, evidence_bucket) == EXPECTED_SOURCE_KEYS | EXPECTED_MANIFEST_KEYS
        assert len(EXPECTED_SOURCE_KEYS) == EXPECTED["totals"]["source_objects"]
        assert sorted(put_keys) == sorted(EXPECTED_SOURCE_KEYS | EXPECTED_MANIFEST_KEYS)
        assert len(put_keys) == EXPECTED["totals"]["put_object_calls_first_publish"]
        for key in EXPECTED_SOURCE_KEYS:
            assert version_count(s3_client, evidence_bucket, key) == 1, key

    async def test_each_week_uploads_what_is_new_to_the_run_and_every_manifest_is_written(
        self, local: LocalEvidence, bucket: S3EvidenceObjectStore
    ) -> None:
        report = await publish(service_over(local, bucket))

        for outcome in report.snapshots:
            week = WEEKS[outcome.snapshot]
            assert len(outcome.of(SourceResult.UPLOADED)) == week["first_publish"]["upload"], outcome.snapshot
            assert len(outcome.of(SourceResult.SKIPPED)) == week["first_publish"]["uploaded_earlier"]
            assert {source.sha256 for source in outcome.sources} == {
                digest_of_body(name) for name in week["sources"]
            }
            assert outcome.manifest is ManifestOutcome.UPLOADED
        assert report.count(SourceResult.UPLOADED) == EXPECTED["totals"]["source_objects"]

    async def test_a_source_carries_its_sha256_as_a_checksum_and_nothing_else_as_metadata(
        self,
        local: LocalEvidence,
        bucket: S3EvidenceObjectStore,
        s3_client: S3Client,
        evidence_bucket: str,
    ) -> None:
        await publish(service_over(local, bucket))

        for name in EVERY_BODY:
            head = s3_client.head_object(
                Bucket=evidence_bucket, Key=expected_source_key(name), ChecksumMode="ENABLED"
            )
            assert head["Metadata"] == {SHA256_METADATA_NAME: digest_of_body(name)}
            assert head.get("ChecksumSHA256"), f"no S3 SHA-256 checksum on {name}"
            assert head["ContentLength"] == len(DOCUMENT_BODIES[name])

    async def test_the_published_manifest_is_the_local_manifest_byte_for_byte(
        self,
        local: LocalEvidence,
        bucket: S3EvidenceObjectStore,
        s3_client: S3Client,
        evidence_bucket: str,
        imported_data_dir: Path,
    ) -> None:
        await publish(service_over(local, bucket))

        for key in EXPECTED_MANIFEST_KEYS:
            body = s3_client.get_object(Bucket=evidence_bucket, Key=key)["Body"].read()
            assert body == (imported_data_dir / "objects" / key).read_bytes()

    async def test_one_snapshot_can_be_published_on_its_own(
        self,
        local: LocalEvidence,
        bucket: S3EvidenceObjectStore,
        s3_client: S3Client,
        evidence_bucket: str,
    ) -> None:
        report = await publish(service_over(local, bucket), "2026-09-08")

        assert [outcome.snapshot for outcome in report.snapshots] == ["2026-09-08"]
        assert bucket_keys(s3_client, evidence_bucket) == {
            expected_source_key(name) for name in WEEKS["2026-09-08"]["sources"]
        } | {f"manifests/{SYNTHETIC_CASELIST}/2026-09-08.jsonl"}

    async def test_a_dry_run_plans_every_upload_and_sends_none(
        self, local: LocalEvidence, bucket: S3EvidenceObjectStore, put_keys: list[str]
    ) -> None:
        plan = await service_over(local, bucket).plan(SYNTHETIC_CASELIST)

        assert {source.key for source in plan.uploads} == EXPECTED_SOURCE_KEYS
        assert put_keys == []

    async def test_asking_for_a_snapshot_this_machine_does_not_hold_is_refused(
        self, local: LocalEvidence, bucket: S3EvidenceObjectStore
    ) -> None:
        with pytest.raises(NothingToPublish, match="manifests/testcl26/2026-09-22.jsonl"):
            await service_over(local, bucket).plan(SYNTHETIC_CASELIST, "2026-09-22")


# ------------------------------------------------------------------------------------------------
# ac2: a second publish uploads nothing; an interrupted one resumes
# ------------------------------------------------------------------------------------------------


class TestIdempotentAndResumable:
    async def test_a_second_publish_uploads_nothing_and_reports_everything_skipped(
        self, local: LocalEvidence, bucket: S3EvidenceObjectStore, put_keys: list[str]
    ) -> None:
        await publish(service_over(local, bucket))
        put_keys.clear()

        report = await publish(service_over(local, bucket))

        assert put_keys == []
        assert len(put_keys) == EXPECTED["totals"]["put_object_calls_second_publish"]
        assert report.succeeded
        assert report.count(SourceResult.UPLOADED) == 0
        assert report.count(SourceResult.SKIPPED) == EXPECTED["totals"]["source_objects"]
        for outcome in report.snapshots:
            assert {source.result for source in outcome.sources} == {SourceResult.SKIPPED}
            assert outcome.manifest is ManifestOutcome.SKIPPED

    @pytest.mark.parametrize("concurrency", [1, 8])
    async def test_a_publish_killed_between_uploads_resumes_without_re_uploading(
        self,
        local: LocalEvidence,
        bucket: S3EvidenceObjectStore,
        s3_client: S3Client,
        evidence_bucket: str,
        put_keys: list[str],
        concurrency: int,
    ) -> None:
        """Killed on the seventh upload: the first week is whole, the second is part-way."""

        def kill_on_seventh(_: ObjectKey, count: int) -> None:
            if count == 7:
                raise SimulatedKill

        scripted = ScriptedBucket(bucket, kill_on_seventh)
        with pytest.raises(SimulatedKill):
            await publish(service_over(local, scripted, concurrency=concurrency))
        await scripted.settle()
        landed = bucket_keys(s3_client, evidence_bucket)
        assert f"manifests/{SYNTHETIC_CASELIST}/2026-09-01.jsonl" in landed
        assert f"manifests/{SYNTHETIC_CASELIST}/2026-09-08.jsonl" not in landed
        assert f"manifests/{SYNTHETIC_CASELIST}/2026-09-15.jsonl" not in landed
        put_keys.clear()

        report = await publish(service_over(local, bucket, concurrency=concurrency))

        assert report.succeeded
        assert set(put_keys).isdisjoint(landed), "an object already in the bucket was uploaded again"
        assert set(put_keys) | landed == EXPECTED_SOURCE_KEYS | EXPECTED_MANIFEST_KEYS
        assert bucket_keys(s3_client, evidence_bucket) == EXPECTED_SOURCE_KEYS | EXPECTED_MANIFEST_KEYS
        for key in EXPECTED_SOURCE_KEYS:
            assert version_count(s3_client, evidence_bucket, key) == 1, key

    async def test_a_publish_killed_after_its_sources_and_before_its_manifest_completes_on_rerun(
        self,
        local: LocalEvidence,
        bucket: S3EvidenceObjectStore,
        s3_client: S3Client,
        evidence_bucket: str,
        put_keys: list[str],
    ) -> None:
        """The case the manifest-last rule exists for.

        Every source of the second week is in the bucket and its manifest is not. The snapshot is
        visibly incomplete — no manifest — and a re-run finishes it: no source of the second week
        is uploaded again, its manifest goes up, and the third week follows. Four uploads, worked
        out by hand: the second week's manifest, the third week's two new sources, its manifest.
        """
        second_manifest = f"manifests/{SYNTHETIC_CASELIST}/2026-09-08.jsonl"

        def kill_at_second_manifest(key: ObjectKey, _: int) -> None:
            if key == second_manifest:
                raise SimulatedKill

        scripted = ScriptedBucket(bucket, kill_at_second_manifest)
        with pytest.raises(SimulatedKill):
            await publish(service_over(local, scripted))
        await scripted.settle()
        landed = bucket_keys(s3_client, evidence_bucket)
        second_week_sources = {expected_source_key(name) for name in WEEKS["2026-09-08"]["sources"]}
        assert second_week_sources <= landed
        assert second_manifest not in landed
        put_keys.clear()

        report = await publish(service_over(local, bucket))

        assert report.succeeded
        assert sorted(put_keys) == sorted(
            {
                second_manifest,
                expected_source_key("bayview-semis-neg"),
                expected_source_key("seaside-round-5-aff"),
                f"manifests/{SYNTHETIC_CASELIST}/2026-09-15.jsonl",
            }
        )
        resumed = {outcome.snapshot: outcome for outcome in report.snapshots}
        assert resumed["2026-09-08"].manifest is ManifestOutcome.UPLOADED
        assert resumed["2026-09-08"].of(SourceResult.UPLOADED) == ()


# ------------------------------------------------------------------------------------------------
# ac3: a failed source withholds the manifest and is named
# ------------------------------------------------------------------------------------------------


def fail_uploads_of(*digests: str) -> Callable[[ObjectKey, int], None]:
    def before_put(key: ObjectKey, _: int) -> None:
        if any(key.endswith(digest) for digest in digests):
            raise StoreUnavailable("PutObject", key, "simulated 503 SlowDown")

    return before_put


class TestFailedSourcesWithholdTheManifest:
    async def test_a_failed_upload_withholds_every_manifest_that_names_it(
        self,
        local: LocalEvidence,
        bucket: S3EvidenceObjectStore,
        s3_client: S3Client,
        evidence_bucket: str,
    ) -> None:
        """`ridgeline-round-6-neg` first appears in the second week and is still in the third."""
        failing = digest_of_body("ridgeline-round-6-neg")

        report = await publish(service_over(local, ScriptedBucket(bucket, fail_uploads_of(failing))))

        assert not report.succeeded
        assert report.failed_sha256 == (failing,)
        outcomes = {outcome.snapshot: outcome for outcome in report.snapshots}
        assert outcomes["2026-09-01"].manifest is ManifestOutcome.UPLOADED
        assert outcomes["2026-09-08"].manifest is ManifestOutcome.WITHHELD
        assert outcomes["2026-09-15"].manifest is ManifestOutcome.WITHHELD
        assert failing in (outcomes["2026-09-08"].manifest_error or "")
        landed = bucket_keys(s3_client, evidence_bucket)
        assert f"manifests/{SYNTHETIC_CASELIST}/2026-09-08.jsonl" not in landed
        assert f"manifests/{SYNTHETIC_CASELIST}/2026-09-15.jsonl" not in landed
        # Everything else was still uploaded: one failure does not abandon the rest.
        assert landed >= EXPECTED_SOURCE_KEYS - {expected_source_key("ridgeline-round-6-neg")}

    async def test_the_next_run_after_a_failure_completes_the_withheld_snapshots(
        self,
        local: LocalEvidence,
        bucket: S3EvidenceObjectStore,
        s3_client: S3Client,
        evidence_bucket: str,
        put_keys: list[str],
    ) -> None:
        failing = digest_of_body("ridgeline-round-6-neg")
        await publish(service_over(local, ScriptedBucket(bucket, fail_uploads_of(failing))))
        put_keys.clear()

        report = await publish(service_over(local, bucket))

        assert report.succeeded
        assert sorted(put_keys) == sorted(
            {
                expected_source_key("ridgeline-round-6-neg"),
                f"manifests/{SYNTHETIC_CASELIST}/2026-09-08.jsonl",
                f"manifests/{SYNTHETIC_CASELIST}/2026-09-15.jsonl",
            }
        )

    async def test_an_object_of_another_size_under_a_source_key_is_left_alone_and_fails(
        self,
        local: LocalEvidence,
        bucket: S3EvidenceObjectStore,
        s3_client: S3Client,
        evidence_bucket: str,
    ) -> None:
        key = expected_source_key("grove-round-1-aff")
        s3_client.put_object(Bucket=evidence_bucket, Key=key, Body=b"other bytes")

        report = await publish(service_over(local, bucket), "2026-09-01")

        assert report.failed_sha256 == (digest_of_body("grove-round-1-aff"),)
        assert report.snapshots[0].failed[0].error_code == "CHECKSUM_MISMATCH"
        assert report.snapshots[0].manifest is ManifestOutcome.WITHHELD
        assert version_count(s3_client, evidence_bucket, key) == 1
        assert s3_client.get_object(Bucket=evidence_bucket, Key=key)["Body"].read() == b"other bytes"

    @pytest.mark.parametrize("recorded", [None, "0" * 64])
    async def test_a_same_size_object_without_this_digest_recorded_fails(
        self,
        local: LocalEvidence,
        bucket: S3EvidenceObjectStore,
        s3_client: S3Client,
        evidence_bucket: str,
        recorded: str | None,
    ) -> None:
        key = expected_source_key("harbor-aff")
        body = DOCUMENT_BODIES["harbor-aff"]
        metadata = {} if recorded is None else {SHA256_METADATA_NAME: recorded}
        s3_client.put_object(Bucket=evidence_bucket, Key=key, Body=body, Metadata=metadata)

        report = await publish(service_over(local, bucket), "2026-09-01")

        assert report.failed_sha256 == (digest_of_body("harbor-aff"),)
        assert report.snapshots[0].manifest is ManifestOutcome.WITHHELD
        assert version_count(s3_client, evidence_bucket, key) == 1

    async def test_a_local_blob_that_no_longer_matches_its_key_is_not_published(
        self,
        local: LocalEvidence,
        bucket: S3EvidenceObjectStore,
        s3_client: S3Client,
        evidence_bucket: str,
        imported_data_dir: Path,
    ) -> None:
        digest = digest_of_body("harbor-octas-neg")
        blob = imported_data_dir / "blobs" / "sha256" / digest[0:2] / digest[2:4] / digest
        blob.chmod(0o644)
        blob.write_bytes(b"damaged on disk")

        report = await publish(service_over(local, bucket), "2026-09-01")

        assert report.failed_sha256 == (digest,)
        assert report.snapshots[0].failed[0].error_code == "BLOB_INTEGRITY_ERROR"
        assert expected_source_key("harbor-octas-neg") not in bucket_keys(s3_client, evidence_bucket)
        assert report.snapshots[0].manifest is ManifestOutcome.WITHHELD

    async def test_a_source_missing_from_this_machine_withholds_the_manifest(
        self,
        local: LocalEvidence,
        bucket: S3EvidenceObjectStore,
        s3_client: S3Client,
        evidence_bucket: str,
        imported_data_dir: Path,
    ) -> None:
        digest = digest_of_body("harbor-octas-neg")
        (imported_data_dir / "blobs" / "sha256" / digest[0:2] / digest[2:4] / digest).unlink()

        report = await publish(service_over(local, bucket), "2026-09-01")

        assert report.failed_sha256 == (digest,)
        assert report.snapshots[0].failed[0].error_code == "MISSING_LOCALLY"
        assert f"manifests/{SYNTHETIC_CASELIST}/2026-09-01.jsonl" not in bucket_keys(s3_client, evidence_bucket)

    async def test_an_expired_session_ends_the_run_with_no_manifest_written(
        self,
        local: LocalEvidence,
        bucket: S3EvidenceObjectStore,
        s3_client: S3Client,
        evidence_bucket: str,
    ) -> None:
        def expire(_: ObjectKey, count: int) -> None:
            if count == 2:
                raise StoreCredentialsExpired(hint="aws sso login --profile debate-dev-evidence")

        with pytest.raises(StoreCredentialsExpired):
            await publish(service_over(local, ScriptedBucket(bucket, expire)))

        assert not any(key.startswith("manifests/") for key in bucket_keys(s3_client, evidence_bucket))


# ------------------------------------------------------------------------------------------------
# The suppression list, and what never leaves this machine
# ------------------------------------------------------------------------------------------------


async def test_a_suppressed_source_is_never_uploaded_and_does_not_hold_back_the_manifest(
    local: LocalEvidence, bucket: S3EvidenceObjectStore, s3_client: S3Client, evidence_bucket: str
) -> None:
    suppressed = digest_of_body("harbor-octas-neg")

    report = await publish(service_over(local, bucket, suppressed={suppressed}), "2026-09-01")

    assert report.succeeded
    landed = bucket_keys(s3_client, evidence_bucket)
    assert expected_source_key("harbor-octas-neg") not in landed
    assert f"manifests/{SYNTHETIC_CASELIST}/2026-09-01.jsonl" in landed


async def test_no_school_team_code_or_filename_reaches_a_key_metadata_log_or_error(
    local: LocalEvidence,
    bucket: S3EvidenceObjectStore,
    s3_client: S3Client,
    evidence_bucket: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Personal-data rules 3 and 4 (`docs/policies/caselist-data-use.md`), asserted, not trusted.

    A failing run as well as a clean one, because a failure is where a message is most likely to
    quote something it should not. The capture is this application's loggers at every level;
    botocore's own wire logging is off unless someone turns it on, and is not this code's output.
    """
    caplog.set_level(logging.DEBUG, logger="debate_core")
    failing = digest_of_body("seaside-round-5-aff")
    failed_run = await publish(service_over(local, ScriptedBucket(bucket, fail_uploads_of(failing))))
    clean_run = await publish(service_over(local, bucket))

    source_keys = {key for key in bucket_keys(s3_client, evidence_bucket) if key.startswith("raw/")}
    surfaces: list[str] = [*source_keys, caplog.text]
    for key in source_keys:
        head = s3_client.head_object(Bucket=evidence_bucket, Key=key)
        surfaces.extend(f"{name}={value}" for name, value in head["Metadata"].items())
    for report in (failed_run, clean_run):
        for outcome in report.snapshots:
            surfaces.append(outcome.manifest_error or "")
            surfaces.extend(f"{source.error_code} {source.error_message}" for source in outcome.sources)

    everything = "\n".join(surfaces)
    assert failing in everything, "the failed run's digest should have been named somewhere"
    for identifier in FICTIONAL_IDENTIFIERS:
        assert identifier not in everything, identifier
