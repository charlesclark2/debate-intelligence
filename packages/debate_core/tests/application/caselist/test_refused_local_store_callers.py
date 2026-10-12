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

`v1-e31-t06` merged while this task was in progress and added two more callers, the parse
pipeline's source listing and the parsed store's publisher. Neither file is changed here; both are
tested at the end, because what they do with a refusal changed underneath them.

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
from debate_core.application.caselist.parse_sources import enumerate_sources
from debate_core.application.caselist.parsed_publish import ParsedStorePublisher
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.removal_plan import SourceSelector
from debate_core.application.caselist.removal_service import RemovalIncomplete
from debate_core.application.caselist.status_service import CaselistStatusService
from debate_core.application.errors import StoreAccessDenied
from debate_core.application.evidence_sync import EvidenceSyncService, SyncDirection, SyncKeyspace
from debate_core.application.ports.suppression import ReasonCode, RemovalLogEntry, RemovalOutcome
from debate_core.integrations.local import FsEvidenceObjectStore
from debate_core.integrations.local.suppression_list import local_removal_log_file
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


async def test_a_removal_this_machine_refuses_part_way_is_logged_as_a_store_that_refused(
    removal_world: RemovalWorld,
) -> None:
    """The plan is made, and when it runs this machine will not let the file's blob be deleted.

    The removal stops as it always did, incomplete and logged, with the suppression entry appended
    first. What changed is what stopped it: a store that refused, not a raw `PermissionError`, so
    the log entry's code is the store's and the CLI's rule for a removal stopped by a store applies
    (`v1-e01-t20`): the same command, once the permission is fixed, finishes it."""
    digest = hashlib.sha256(DOCUMENT_BODIES["bayview-semis-neg"]).hexdigest()
    service = removal_world.service()
    plan = await service.plan(SourceSelector(digest), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM)
    fan_out = removal_world.data_dir / "blobs" / "sha256" / digest[0:2] / digest[2:4]
    assert (fan_out / digest).is_file()

    fan_out.chmod(0o500)  # the blob can be found, and its directory entry cannot be removed
    try:
        with pytest.raises(RemovalIncomplete) as stopped:
            await service.execute(plan)
    finally:
        fan_out.chmod(0o700)

    assert type(stopped.value.__cause__) is errors.LocalStoreAccessDenied
    assert stopped.value.error_code == "STORE_ACCESS_DENIED"
    log = local_removal_log_file(removal_world.data_dir).path.read_text(encoding="utf-8").splitlines()
    (entry,) = [RemovalLogEntry.from_line(line) for line in log]
    assert (entry.outcome, entry.error_code) == (RemovalOutcome.INCOMPLETE, "STORE_ACCESS_DENIED")
    assert (fan_out / digest).is_file(), "the blob is still there for the re-run to delete"
    assert str(removal_world.data_dir) not in str(stopped.value)


# ------------------------------------------------------------------------------------------------
# The callers `v1-e31-t06` added
# ------------------------------------------------------------------------------------------------


async def test_the_parse_pipeline_stops_rather_than_finding_no_source_to_parse(
    imported_data_dir: Path, local: LocalEvidence
) -> None:
    """`caselist parse` lists a caselist's manifests to find its sources. Three weeks are imported:
    an unreadable manifest directory used to mean "nothing to parse"."""
    assert await enumerate_sources(local, SYNTHETIC_CASELIST) != ()

    with refused(imported_data_dir / "objects" / "manifests"), pytest.raises(StoreAccessDenied) as caught:
        await enumerate_sources(local, SYNTHETIC_CASELIST)

    assert_stopped_on(caught, "the manifest directory", imported_data_dir)


async def test_the_parsed_store_publisher_stops_rather_than_publishing_nothing(
    tmp_path: Path, bucket: S3EvidenceObjectStore, s3_client: S3Client, evidence_bucket: str
) -> None:
    """The publisher lists one version directory of `<data_dir>/parsed`. Unreadable, the listing
    used to be empty and the publish a success that had uploaded nothing."""
    data_dir = tmp_path / "evidence"
    parsed = FsEvidenceObjectStore(data_dir, subdirectory=Path("parsed"))
    held = parsed.root / SYNTHETIC_CASELIST / "a-parser-version" / "sources" / "ab" / "a-source.jsonl"
    held.parent.mkdir(parents=True)
    held.write_bytes(b'{"an invented": "parsed record"}\n')
    publisher = ParsedStorePublisher(
        local=parsed, local_path_for=parsed.path_for, remote=bucket, suppression=empty_suppression_list()
    )

    with refused(parsed.root), pytest.raises(StoreAccessDenied) as caught:
        await publisher.publish(SYNTHETIC_CASELIST, "a-parser-version")

    assert_stopped_on(caught, "the parsed card store", data_dir)
    assert keys_in(s3_client, evidence_bucket) == set()
