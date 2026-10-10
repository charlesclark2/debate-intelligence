"""What each caller of this machine's store does now that a refused directory is a refusal (`v1-e34-t13`).

`FsEvidenceObjectStore.list_objects` and `FsEvidenceVersionStore.list_versions` used to list nothing
under a directory the operating system would not let them read, and each caller went on with "this
machine holds nothing":

* a publish planned every source as missing from this machine;
* `caselist status` reported every snapshot as drifted;
* `store sync` planned to push nothing, or to pull everything;
* a removal planned to take nothing out of this machine, and said so.

Each of them now stops, with `LocalStoreAccessDenied` naming the directory's role, before it writes
anything. The pull's own stages (select, publish, report, retention) are in
`test_pull_stage_failure_codes.py`. The session report tabulates every caller.

Real stores, real `chmod 000`, the synthetic weeks, and moto for the bucket.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_synthetic_archives import DOCUMENT_BODIES, SYNTHETIC_CASELIST
from tests.fixtures.permissions import needs_permissions, refused

from debate_core.application import errors
from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.removal_plan import SourceSelector
from debate_core.application.caselist.status_service import CaselistStatusService
from debate_core.application.errors import StoreAccessDenied
from debate_core.application.evidence_sync import EvidenceSyncService, SyncDirection, SyncKeyspace
from debate_core.application.ports.suppression import ReasonCode
from debate_core.integrations.local import FsEvidenceObjectStore
from debate_core.integrations.s3 import S3EvidenceObjectStore
from debate_core.testing.fakes import empty_suppression_list

from .conftest import REQUEST, RemovalWorld

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = [pytest.mark.anyio, needs_permissions]


def assert_stopped_on(caught: pytest.ExceptionInfo[StoreAccessDenied], role: str, data_dir: Path) -> None:
    """Stopped by this machine's refusal, named by role. The subclass is looked up here rather than
    imported by name, so that against a build without it each test fails on what the caller did."""
    assert type(caught.value) is errors.LocalStoreAccessDenied
    assert caught.value.resource == role
    assert str(data_dir) not in str(caught.value)
    assert "aws sso login" not in str(caught.value)


def keys_in(client: S3Client, bucket: str) -> set[str]:
    return {str(one.get("Key")) for one in client.list_objects_v2(Bucket=bucket).get("Contents", [])}


async def test_a_publish_stops_rather_than_planning_every_source_as_missing(
    imported_data_dir: Path, local: LocalEvidence, bucket: S3EvidenceObjectStore
) -> None:
    service = CaselistPublishService(local=local, remote=bucket, suppression=empty_suppression_list())

    with refused(imported_data_dir / "blobs"), pytest.raises(StoreAccessDenied) as caught:
        await service.plan(SYNTHETIC_CASELIST)

    assert_stopped_on(caught, "the blob directory", imported_data_dir)


async def test_a_publish_stops_rather_than_finding_no_manifest_to_publish(
    imported_data_dir: Path, local: LocalEvidence, bucket: S3EvidenceObjectStore
) -> None:
    """It used to raise `NothingToPublish`, "import the archive first", for an imported caselist."""
    service = CaselistPublishService(local=local, remote=bucket, suppression=empty_suppression_list())
    manifests = imported_data_dir / "objects" / "manifests"

    with refused(manifests), pytest.raises(StoreAccessDenied) as caught:
        await service.plan(SYNTHETIC_CASELIST)

    assert_stopped_on(caught, "the manifest directory", imported_data_dir)


async def test_status_stops_rather_than_reporting_every_snapshot_as_drifted(
    imported_data_dir: Path, local: LocalEvidence, bucket: S3EvidenceObjectStore
) -> None:
    publisher = CaselistPublishService(local=local, remote=bucket, suppression=empty_suppression_list())
    assert (await publisher.execute(await publisher.plan(SYNTHETIC_CASELIST))).succeeded
    status = CaselistStatusService(local=local, remote=bucket, suppression=empty_suppression_list())
    assert (await status.status(SYNTHETIC_CASELIST)).in_sync

    with refused(imported_data_dir / "blobs"), pytest.raises(StoreAccessDenied) as caught:
        await status.status(SYNTHETIC_CASELIST)

    assert_stopped_on(caught, "the blob directory", imported_data_dir)


@pytest.mark.parametrize("direction", [SyncDirection.PUSH, SyncDirection.PULL])
async def test_store_sync_stops_rather_than_planning_against_an_empty_store(
    imported_data_dir: Path, evidence_bucket: str, s3_client: S3Client, direction: SyncDirection
) -> None:
    """A push used to plan nothing, and a pull to plan a download of everything the bucket holds."""
    objects = FsEvidenceObjectStore(imported_data_dir)
    service = EvidenceSyncService(
        suppression=empty_suppression_list(),
        keyspaces=(
            SyncKeyspace(
                name="objects",
                local=objects,
                remote=S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client),
                local_path_for=objects.path_for,
            ),
        ),
    )

    with refused(objects.root), pytest.raises(StoreAccessDenied) as caught:
        await service.plan(direction=direction)

    assert_stopped_on(caught, "the evidence object directory", imported_data_dir)


async def test_a_removal_stops_rather_than_planning_to_take_nothing_out_of_this_machine(
    removal_world: RemovalWorld,
) -> None:
    """The planner reads this machine's manifests to find where a file is held. Unreadable, it used
    to find none here, and plan a removal that left this machine's copies in place."""
    digest = hashlib.sha256(DOCUMENT_BODIES["grove-round-1-aff"]).hexdigest()
    manifests = removal_world.data_dir / "objects" / "manifests"
    before = keys_in(removal_world.client, removal_world.bucket_name)

    with refused(manifests), pytest.raises(StoreAccessDenied) as caught:
        await removal_world.planner().plan(
            SourceSelector(digest), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM
        )

    assert_stopped_on(caught, "the manifest directory", removal_world.data_dir)
    assert keys_in(removal_world.client, removal_world.bucket_name) == before


async def test_a_removal_stops_rather_than_reporting_no_local_blob(removal_world: RemovalWorld) -> None:
    """The planner asks this machine's blob tree whether it holds the bytes. "Refused" is not "no".

    A file one team alone disclosed, so the plan is to remove it and the blob tree is asked."""
    digest = hashlib.sha256(DOCUMENT_BODIES["bayview-semis-neg"]).hexdigest()

    with refused(removal_world.data_dir / "blobs"), pytest.raises(StoreAccessDenied) as caught:
        await removal_world.planner().plan(
            SourceSelector(digest), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM
        )

    assert_stopped_on(caught, "the blob directory", removal_world.data_dir)
