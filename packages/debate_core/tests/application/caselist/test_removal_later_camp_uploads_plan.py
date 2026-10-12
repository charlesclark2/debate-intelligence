"""What the removal plan lists for a camp file's later OpenEv id (`v1-e30-t11` ac4).

`test_removal_covers_later_camp_uploads.py` checks the store after the removal, and builds the
worlds used here. This module checks the plan: the later id listed by digest, release and id, how
the two uploads were found to be at one camp path, the earlier id listed and left, `only_named`,
and the later id a team also disclosed.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from debate_core.application.caselist.removal_path_versions import SamePathEvidence, VersionRelation
from debate_core.application.caselist.removal_plan import (
    Disposition,
    Inclusion,
    LaterUploadOutcome,
    RemovalPlan,
    SourceSelector,
)
from debate_core.application.caselist_sync import OPENEV_DELIVERIES_FILENAME
from debate_core.application.ports.suppression import ReasonCode
from debate_core.integrations.local import FsSnapshotStore

from .conftest import REQUEST, RemovalWorld
from .test_removal_covers_later_camp_uploads import (
    NEW_ROW,
    OTHER_CAMP,
    OTHER_CAMP_BODY,
    OTHER_CAMP_SHA256,
    RELEASE,
    REVISED_SHA256,
    a_team_discloses_the_revised_camp_file,
    pulled_then_revised,
    raw_key,
    release_rows,
)
from .test_removal_covers_later_uploads import versions_of
from .test_sync_fetches_revised_camp_files import ESTUARY_BODY, OLD_ROW, REVISED_BODY
from .test_sync_skips_suppressed_downloads import ESTUARY_SHA256

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio


@pytest.fixture
def world(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> RemovalWorld:
    return RemovalWorld(data_dir=tmp_path / "evidence", bucket_name=evidence_bucket, client=s3_client)


async def plan_removal_of(world: RemovalWorld, digest: str, **options: bool) -> RemovalPlan:
    return await world.service().plan(
        SourceSelector(digest), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_CAMP, **options
    )


async def remove(world: RemovalWorld, digest: str) -> RemovalPlan:
    service = world.service()
    plan = await plan_removal_of(world, digest)
    assert (await service.execute(plan)).completed
    return plan


async def test_the_plan_lists_the_later_openev_id_by_digest_release_and_id(world: RemovalWorld) -> None:
    await pulled_then_revised(world)

    plan = await plan_removal_of(world, ESTUARY_SHA256)

    (later,) = plan.later_uploads
    assert (later.sha256, later.caselist, later.snapshots, later.openev_ids) == (
        REVISED_SHA256,
        "openev",
        (RELEASE,),
        (640,),
    )
    assert later.evidence is SamePathEvidence.UPSTREAM_PATH_DIGEST
    assert plan.later_upload_outcome(later) is LaterUploadOutcome.REMOVED
    added = plan.source(REVISED_SHA256)
    assert added is not None
    assert (added.inclusion, added.disposition) == (Inclusion.LATER_UPLOAD, Disposition.REMOVE)
    assert plan.earlier_versions == ()


async def test_removing_the_later_upload_lists_the_earlier_id_and_leaves_it(world: RemovalWorld) -> None:
    await pulled_then_revised(world)

    plan = await remove(world, REVISED_SHA256)

    (earlier,) = plan.earlier_versions
    assert (earlier.sha256, earlier.relation, earlier.openev_ids) == (
        ESTUARY_SHA256,
        VersionRelation.EARLIER,
        (512,),
    )
    assert plan.later_uploads == () and [source.sha256 for source in plan.sources] == [REVISED_SHA256]
    assert release_rows(world) == [{OLD_ROW: ESTUARY_SHA256}] * 2
    assert FsSnapshotStore(world.data_dir).path_for(ESTUARY_SHA256).read_bytes() == ESTUARY_BODY
    assert len(versions_of(world, raw_key(ESTUARY_SHA256))) == 1


async def test_only_named_leaves_the_later_openev_id(world: RemovalWorld) -> None:
    await pulled_then_revised(world)
    service = world.service()

    plan = await plan_removal_of(world, ESTUARY_SHA256, only_named=True)
    assert (await service.execute(plan)).completed

    assert [source.sha256 for source in plan.sources] == [ESTUARY_SHA256]
    assert release_rows(world) == [{NEW_ROW: REVISED_SHA256}] * 2
    assert FsSnapshotStore(world.data_dir).path_for(REVISED_SHA256).read_bytes() == REVISED_BODY


async def test_without_the_delivery_record_it_is_matched_by_name_and_the_plan_says_so(
    world: RemovalWorld,
) -> None:
    """A machine that never pulled, as prod is: the rows' names are all a plan there can go by."""
    await pulled_then_revised(world, (OTHER_CAMP, OTHER_CAMP_BODY))
    (world.data_dir / OPENEV_DELIVERIES_FILENAME).unlink()

    plan = await plan_removal_of(world, ESTUARY_SHA256)

    assert {one.sha256: (one.openev_ids, one.evidence) for one in plan.later_uploads} == {
        REVISED_SHA256: ((640,), SamePathEvidence.ROW_NAME),
        OTHER_CAMP_SHA256: ((700,), SamePathEvidence.ROW_NAME),
    }


async def test_a_later_openev_id_a_team_also_disclosed_is_listed_as_kept(
    world: RemovalWorld,
    tmp_path: Path,
) -> None:
    await pulled_then_revised(world)
    await a_team_discloses_the_revised_camp_file(world, tmp_path / "weekly")

    plan = await plan_removal_of(world, ESTUARY_SHA256)

    (later,) = plan.later_uploads
    assert plan.later_upload_outcome(later) is LaterUploadOutcome.KEPT_SHARED
    kept = plan.source(REVISED_SHA256)
    assert kept is not None
    assert (kept.inclusion, kept.disposition, kept.other_teams) == (
        Inclusion.LATER_UPLOAD,
        Disposition.SKIP_SHARED,
        1,
    )
    assert (plan.later_uploads_found, plan.later_uploads_added) == (1, 0)
    assert not [planned for planned in plan.objects if planned.sha256 == REVISED_SHA256]
