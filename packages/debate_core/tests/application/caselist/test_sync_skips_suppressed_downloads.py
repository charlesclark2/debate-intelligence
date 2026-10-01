"""The weekly pull does not download a camp file it has been told to remove (`v1-e34-t07`).

Reproduction first (spec node `reproduce`): a camp file is pulled, removed under the removal
procedure, and pulled again with its inbox copy gone.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.openev.build_synthetic_openev import DOCUMENT_BODIES

from debate_core.application.caselist.import_service import CaselistImportService
from debate_core.application.caselist.manifest import read_manifest_lines
from debate_core.application.caselist.openev_import_service import OpenEvImportService
from debate_core.application.caselist.openev_manifest import openev_manifest_key
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.removal_plan import SourceSelector
from debate_core.application.caselist_sync import CaselistSyncService
from debate_core.application.ports.caselist_source import (
    ArchiveListing,
    CaselistInfo,
    DownloadedFile,
    OpenEvFile,
    openev_inbox_name,
)
from debate_core.application.ports.suppression import ReasonCode
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsSnapshotStore
from debate_core.integrations.local.archive_reader import read_archive

from .conftest import REQUEST, RemovalWorld

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

CASELIST = "testcl26"
YEAR = 2026
PULLED_AT = datetime(2026, 9, 28, 6, 0, tzinfo=UTC)
LIMITS = {"max_archive_bytes": 64 * 1024 * 1024, "max_unpacked_bytes": 64 * 1024 * 1024}

ESTUARY = OpenEvFile(
    openev_id=512,
    path=f"openev/{YEAR}/Tamarack/TSF-Estuary Solvency Advocate.docx",
    filename="TSF-Estuary Solvency Advocate.docx",
    year=YEAR,
    tags=("policy",),
)
ESTUARY_SHA256 = hashlib.sha256(DOCUMENT_BODIES["estuary-solvency"]).hexdigest()


class FakeOpenEvSource:
    """OpenCaselist listing OpenEv camp files and no archives, recording every download asked of it."""

    def __init__(self, files: list[tuple[OpenEvFile, bytes]]) -> None:
        self.files = files
        self.openev_fetches: list[int] = []

    async def list_caselists(self, *, archived: bool | None = None) -> list[CaselistInfo]:
        return [CaselistInfo(slug=CASELIST)]

    async def get_caselist(self, caselist: str) -> CaselistInfo:
        return CaselistInfo(slug=caselist)

    async def list_archives(self, caselist: str) -> list[ArchiveListing]:
        return []

    async def list_openev(self, *, year: int | None = None) -> list[OpenEvFile]:
        return [file for file, _ in self.files]

    async def download_archive(self, archive: ArchiveListing, inbox: Path) -> DownloadedFile:
        raise AssertionError("no archive is listed, so none may be downloaded")

    async def download_openev(self, file: OpenEvFile, inbox: Path) -> DownloadedFile:
        self.openev_fetches.append(file.openev_id)
        body = next(body for listed, body in self.files if listed.openev_id == file.openev_id)
        destination = inbox / openev_inbox_name(file)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(body)
        return DownloadedFile(
            path=destination,
            sha256=hashlib.sha256(body).hexdigest(),
            byte_size=len(body),
            source_name=f"openev-{file.openev_id}",
        )


@pytest.fixture
def world(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> RemovalWorld:
    return RemovalWorld(data_dir=tmp_path / "evidence", bucket_name=evidence_bucket, client=s3_client)


def build_sync(
    world: RemovalWorld, source: FakeOpenEvSource, *, clock: Callable[[], datetime] = lambda: PULLED_AT
) -> CaselistSyncService:
    """The pull as the composition root builds it when the environment names a bucket."""
    repository = world.repository
    blobs = FsSnapshotStore(world.data_dir)
    return CaselistSyncService(
        source=source,
        archive_importer=CaselistImportService(
            caselists=repository, blobs=blobs, suppression=world.suppression()
        ),
        openev_importer=OpenEvImportService(caselists=repository, blobs=blobs, suppression=world.suppression()),
        local=world.local,
        read_archive=lambda path: read_archive(path, **LIMITS),
        event_for_caselist=lambda slug: Event.LD,
        inbox=world.data_dir / "inbox",
        state_dir=world.data_dir,
        publisher=CaselistPublishService(local=world.local, remote=world.bucket, suppression=world.suppression()),
        clock=clock,
    )


async def remove_source(world: RemovalWorld, sha256: str) -> None:
    """`caselist remove --source <sha256> --execute`, through the removal service the command runs."""
    service = world.service()
    plan = await service.plan(SourceSelector(sha256), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_CAMP)
    report = await service.execute(plan)
    assert report.completed


def release_summary(world: RemovalWorld) -> dict[str, object]:
    path = world.local.object_path_for(openev_manifest_key(YEAR, Event.POLICY))  # type: ignore[misc]
    rows = [json.loads(line) for line in read_manifest_lines(path)]
    return next(row for row in rows if row["kind"] == "summary")


async def test_reproduce_a_removed_camp_file_is_downloaded_again_by_the_sync(world: RemovalWorld) -> None:
    source = FakeOpenEvSource([(ESTUARY, DOCUMENT_BODIES["estuary-solvency"])])
    first = await build_sync(world, source).run([CASELIST])
    assert first.succeeded and source.openev_fetches == [ESTUARY.openev_id]

    await remove_source(world, ESTUARY_SHA256)
    (world.data_dir / "inbox" / openev_inbox_name(ESTUARY)).unlink()

    again = await build_sync(world, source).run([CASELIST])

    observed = {
        "openev_fetches": source.openev_fetches,
        "decisions": [str(one.decision) for one in again.openev],
        "openev_downloaded": again.openev_downloaded,
        "blobs_stored": again.blobs_stored,
        "release_classifications": release_summary(world)["classifications"],
        "import_stage": str(again.stage(again.stages[2].stage)),
    }
    assert source.openev_fetches == [ESTUARY.openev_id], f"the removed file was fetched again: {observed}"
    assert [str(one.decision) for one in again.openev] == ["skipped_as_removed"], observed


async def test_reproduce_a_removed_camp_file_left_in_the_inbox_is_imported_again(world: RemovalWorld) -> None:
    source = FakeOpenEvSource([(ESTUARY, DOCUMENT_BODIES["estuary-solvency"])])
    await build_sync(world, source).run([CASELIST])
    await remove_source(world, ESTUARY_SHA256)

    again = await build_sync(world, source).run([CASELIST])

    observed = {
        "openev_fetches": source.openev_fetches,
        "decisions": [str(one.decision) for one in again.openev],
        "snapshots_imported": again.snapshots_imported,
        "nothing_new": again.nothing_new,
        "release_classifications": release_summary(world)["classifications"],
    }
    assert [str(one.decision) for one in again.openev] == ["skipped_as_removed"], observed
