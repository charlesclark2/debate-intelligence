"""Removing a camp file also takes down a later OpenEv id at the same camp path (`v1-e30-t11` ac4).

OpenEv changes a camp file one way: it is deleted and uploaded again under a new id, normally at the
same path (`v1-e34-t08`). The sync fetches that new id as a revision, so the release manifest then
holds two rows, `openev-512-…` and `openev-640-…`, and removing the bytes of 512 used to leave 640's
in the store and the bucket. `v1-e34-t14` holds a new id back when it has not been imported; this
is the case where it already was.

Each world is built by the real pull, through the helpers of the `v1-e34-t07` and `t08` tests, on
the synthetic camp files of `tests/fixtures/openev/`. The pull here publishes to moto, and its
inbox is this machine's, so the removal purges it. Every expected value is worked out by hand from
what each test lists upstream. Like `test_removal_covers_later_uploads.py`, this module asks the
planner for nothing the task added, so it also runs against the planner as it was; what the plan
*lists* for a camp file is in `test_removal_later_camp_uploads_plan.py`.

| OpenEv id | Upstream path | Bytes |
|---|---|---|
| 512 | `openev/2026/Tamarack/TSF-Estuary Solvency Advocate.docx` | `estuary-solvency` |
| 640 | the same path, uploaded again | `canal-counterplan-revised` |
| 700 | the same file name in another camp's folder, `Quillfeather/` | `harbor-tariffs-aff` |
"""

from __future__ import annotations

import json
import zipfile
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.openev.build_synthetic_openev import DOCUMENT_BODIES

from debate_core.application.caselist.import_service import CaselistImportService
from debate_core.application.caselist.manifest import manifest_key, read_manifest_lines, write_manifest
from debate_core.application.caselist.openev_manifest import openev_manifest_key
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.removal_plan import SourceSelector
from debate_core.application.caselist_sync import OPENEV_DELIVERIES_FILENAME, SelectionDecision
from debate_core.application.ports.suppression import ReasonCode
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsEvidenceObjectStore, FsSnapshotStore
from debate_core.integrations.local.archive_reader import archive_digest, read_archive
from debate_core.testing.fakes.suppression import empty_suppression_list

from .conftest import REQUEST, RemovalWorld
from .test_removal_covers_later_uploads import suppression_lines, versions_of
from .test_sync_fetches_revised_camp_files import ESTUARY_BODY, OLD_ROW, REVISED_BODY, REVISION
from .test_sync_skips_suppressed_downloads import (
    CASELIST,
    ESTUARY,
    ESTUARY_SHA256,
    LIMITS,
    YEAR,
    FakeOpenEvSource,
    decisions,
    inbox_copy,
    pull,
    sha256,
)

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

REVISED_SHA256 = sha256("canal-counterplan-revised")
NEW_ROW = "openev-640-TSF-Estuary_Solvency_Advocate.docx"

#: Another camp's file with the same file name: a different upstream path, so a different camp path.
OTHER_CAMP = ESTUARY.model_copy(
    update={"openev_id": 700, "path": f"openev/{YEAR}/Quillfeather/TSF-Estuary Solvency Advocate.docx"}
)
OTHER_CAMP_BODY = DOCUMENT_BODIES["harbor-tariffs-aff"]
OTHER_CAMP_SHA256 = sha256("harbor-tariffs-aff")
OTHER_CAMP_ROW = "openev-700-TSF-Estuary_Solvency_Advocate.docx"

RELEASE = f"{YEAR}-policy"
RELEASE_KEY = openev_manifest_key(YEAR, Event.POLICY)


@pytest.fixture
def world(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> RemovalWorld:
    return RemovalWorld(data_dir=tmp_path / "evidence", bucket_name=evidence_bucket, client=s3_client)


async def pulled_then_revised(world: RemovalWorld, *also: tuple[object, bytes]) -> FakeOpenEvSource:
    """512 pulled and imported; then deleted upstream and uploaded again as 640, which is pulled too."""
    source = FakeOpenEvSource([(ESTUARY, ESTUARY_BODY)])
    await pull(world, source)
    source.files = [(REVISION, REVISED_BODY), *also]  # type: ignore[list-item]
    await pull(world, source)
    return source


def raw_key(digest: str) -> str:
    return f"raw/openev/{YEAR}/sha256/{digest[:2]}/{digest[2:4]}/{digest}"


def release_rows(world: RemovalWorld) -> list[dict[str, list[str]]]:
    """The release manifest's member rows, `{path: sha256}`, on this machine and in the bucket."""
    local = read_manifest_lines(FsEvidenceObjectStore(world.data_dir).path_for(RELEASE_KEY))
    bucket = world.client.get_object(Bucket=world.bucket_name, Key=RELEASE_KEY)["Body"].read().decode()
    return [
        {row["path"]: row["sha256"] for row in map(json.loads, lines) if row["kind"] == "member"}
        for lines in (local, bucket.splitlines())
    ]


async def remove(world: RemovalWorld, digest: str) -> None:
    """`caselist remove --source <digest> --execute`, through the service the command runs."""
    service = world.service()
    plan = await service.plan(SourceSelector(digest), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_CAMP)
    assert (await service.execute(plan)).completed


# ------------------------------------------------------------------------------------------------
# ac4
# ------------------------------------------------------------------------------------------------


async def test_before_the_removal_the_release_holds_both_uploads_at_one_camp_path(
    world: RemovalWorld,
) -> None:
    await pulled_then_revised(world)

    assert release_rows(world) == [{OLD_ROW: ESTUARY_SHA256, NEW_ROW: REVISED_SHA256}] * 2
    deliveries = json.loads((world.data_dir / OPENEV_DELIVERIES_FILENAME).read_text())["deliveries"]
    assert deliveries["512"]["path_sha256"] == deliveries["640"]["path_sha256"]


async def test_removing_a_camp_file_removes_the_later_openev_id_here_and_in_the_bucket(
    world: RemovalWorld,
) -> None:
    await pulled_then_revised(world)
    world.client.put_object(Bucket=world.bucket_name, Key=raw_key(REVISED_SHA256), Body=REVISED_BODY)
    assert len(versions_of(world, raw_key(REVISED_SHA256))) == 2

    await remove(world, ESTUARY_SHA256)

    assert release_rows(world) == [{}, {}], "both rows, on both sides"
    for digest in (ESTUARY_SHA256, REVISED_SHA256):
        assert not FsSnapshotStore(world.data_dir).path_for(digest).exists(), digest
        assert versions_of(world, raw_key(digest)) == [], digest
        assert await world.repository.find_source(digest) is None
        assert not (await world.repository.list_camp_files(source_sha256=digest, limit=5)).items
    for entries in suppression_lines(world):
        assert {(entry.sha256, entry.disclosure) for entry in entries} == {
            (ESTUARY_SHA256, None),
            (REVISED_SHA256, None),
        }
    assert not inbox_copy(world, ESTUARY).exists() and not inbox_copy(world, REVISION).exists()


async def test_the_next_pull_does_not_fetch_the_removed_later_id_again(world: RemovalWorld) -> None:
    """The plan removed what was imported; the sync's own skip keeps it out afterwards."""
    source = await pulled_then_revised(world)
    assert source.openev_fetches == [512, 640]
    await remove(world, ESTUARY_SHA256)

    summary = await pull(world, source)

    assert source.openev_fetches == [512, 640], "640 was fetched again"
    assert decisions(summary) == {640: SelectionDecision.SKIPPED_AS_REMOVED}
    assert release_rows(world) == [{}, {}]


# ------------------------------------------------------------------------------------------------
# The same file name in another camp's folder
# ------------------------------------------------------------------------------------------------


async def test_another_camps_file_of_the_same_name_is_left_where_the_delivery_record_knows_its_path(
    world: RemovalWorld,
) -> None:
    """A release row keeps no folder, so all three rows read alike. The delivery record tells them apart."""
    await pulled_then_revised(world, (OTHER_CAMP, OTHER_CAMP_BODY))
    assert release_rows(world)[0] == {
        OLD_ROW: ESTUARY_SHA256,
        NEW_ROW: REVISED_SHA256,
        OTHER_CAMP_ROW: OTHER_CAMP_SHA256,
    }

    await remove(world, ESTUARY_SHA256)

    assert release_rows(world) == [{OTHER_CAMP_ROW: OTHER_CAMP_SHA256}] * 2
    assert FsSnapshotStore(world.data_dir).path_for(OTHER_CAMP_SHA256).read_bytes() == OTHER_CAMP_BODY
    assert len(versions_of(world, raw_key(OTHER_CAMP_SHA256))) == 1
    for entries in suppression_lines(world):
        assert {entry.sha256 for entry in entries} == {ESTUARY_SHA256, REVISED_SHA256}


# ------------------------------------------------------------------------------------------------
# A later id whose bytes a team disclosed too
# ------------------------------------------------------------------------------------------------

TEAM_PATH = "Alder Point/KR/Alder Point-KR-Neg-Lakeshore Open-Round 6.docx"


async def a_team_discloses_the_revised_camp_file(world: RemovalWorld, scratch: Path) -> None:
    archive = scratch / f"{CASELIST}-weekly-2026-09-22.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w") as built:
        built.writestr(zipfile.ZipInfo(TEAM_PATH, date_time=(1980, 1, 1, 0, 0, 0)), REVISED_BODY)
    week = date(2026, 9, 22)
    report = await CaselistImportService(
        caselists=world.repository,
        blobs=FsSnapshotStore(world.data_dir),
        suppression=empty_suppression_list(),
    ).import_archive(
        read_archive(archive, **LIMITS),
        caselist=CASELIST,
        snapshot=week,
        event=Event.LD,
        archive_sha256=archive_digest(archive),
    )
    write_manifest(report, FsEvidenceObjectStore(world.data_dir).path_for(manifest_key(CASELIST, week)))
    publisher = CaselistPublishService(
        local=world.local, remote=world.bucket, suppression=empty_suppression_list()
    )
    assert (await publisher.execute(await publisher.plan(CASELIST))).succeeded


async def test_a_later_openev_id_a_team_also_disclosed_is_withdrawn_from_its_camp_path_for_that_team(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """The shared-bytes rule: the team keeps the bytes, and the camp path is withdrawn on its own.

    Until `v1-e30-t14` no entry of the list stopped one camp path of a file, so the later id stayed
    whole. `test_removal_withdraws_one_camp_path.py` has the rest of what the withdrawal does.
    """
    await pulled_then_revised(world)
    await a_team_discloses_the_revised_camp_file(world, tmp_path / "weekly")

    await remove(world, ESTUARY_SHA256)

    assert release_rows(world) == [{}, {}]
    assert FsSnapshotStore(world.data_dir).path_for(REVISED_SHA256).read_bytes() == REVISED_BODY
    assert versions_of(world, raw_key(REVISED_SHA256)) == []
    assert not (await world.repository.list_camp_files(source_sha256=REVISED_SHA256, limit=5)).items
    for entries in suppression_lines(world):
        assert {entry.sha256: entry.disclosure is None for entry in entries} == {
            ESTUARY_SHA256: True,
            REVISED_SHA256: False,
        }
