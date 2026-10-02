"""A local evidence store holding the three synthetic weeks, as `caselist import` leaves one.

The publish, plan and status tests all start from the same place an operator does: three weekly
archives imported in order, blobs under `<data_dir>/blobs/` and one manifest per week under
`<data_dir>/objects/manifests/testcl26/`. The importer is the real one, run over the synthetic
archives from `tests/fixtures/caselist/`; it is set-up here, not the thing under test, and what the
tests assert against is `expected_publish.json`, which a person wrote from the fixture's tables.

Nothing in these archives is real caselist content (`docs/policies/caselist-data-use.md`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_synthetic_archives import (
    SNAPSHOTS,
    SYNTHETIC_CASELIST,
    SYNTHETIC_EVENT,
    build_snapshot_zips,
)
from tests.fixtures.openev.build_synthetic_openev import CAMP_ALIASES_PATH, build_download_zips
from tests.fixtures.openev.build_synthetic_openev import DOWNLOADS as OPENEV_DOWNLOADS
from tests.fixtures.openev.build_synthetic_openev import SYNTHETIC_EVENT as OPENEV_EVENT
from tests.fixtures.openev.build_synthetic_openev import SYNTHETIC_YEAR as OPENEV_YEAR

from debate_core.application.caselist.camp_metadata import load_camp_aliases
from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.import_service import CaselistImportService
from debate_core.application.caselist.inbox_purge import CaselistInbox
from debate_core.application.caselist.manifest import manifest_key, write_manifest, write_manifest_lines
from debate_core.application.caselist.openev_import_service import OpenEvImportService
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.removal_plan import RemovalPlanner
from debate_core.application.caselist.removal_service import CaselistRemovalService, TakedownAccess
from debate_core.application.caselist.suppression import (
    SUPPRESSION_LIST_KEY,
    ObjectStoreAppendOnlyRecord,
    RecordedSuppressionList,
)
from debate_core.application.ports.evidence_versions import EvidenceVersionStore
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsEvidenceObjectStore, FsSnapshotStore, SqliteDatabase
from debate_core.integrations.local.archive_reader import ZipArchiveRewriter, archive_digest, read_archive
from debate_core.integrations.local.fs_version_store import FsEvidenceVersionStore
from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository
from debate_core.integrations.local.suppression_list import (
    local_removal_log_file,
    local_suppression_list_file,
)
from debate_core.integrations.s3 import S3EvidenceObjectStore, S3EvidenceVersionStore
from debate_core.testing.fakes import FixedClock, empty_suppression_list

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

_LIMITS = {"max_archive_bytes": 64 * 1024 * 1024, "max_unpacked_bytes": 64 * 1024 * 1024}


async def import_synthetic_weeks(data_dir: Path, zips_dir: Path) -> None:
    """Import all three synthetic weeks into `data_dir`, writing each week's manifest."""
    database = SqliteDatabase.open(data_dir)
    service = CaselistImportService(
        caselists=SqliteCaselistRepository(database),
        blobs=FsSnapshotStore(data_dir),
        suppression=empty_suppression_list(),
    )
    objects = FsEvidenceObjectStore(data_dir)
    zips = build_snapshot_zips(zips_dir)
    for week in SNAPSHOTS:
        report = await service.import_archive(
            read_archive(zips[week.snapshot], **_LIMITS),
            caselist=SYNTHETIC_CASELIST,
            snapshot=week.snapshot,
            event=Event(SYNTHETIC_EVENT),
            archive_sha256=archive_digest(zips[week.snapshot]),
        )
        write_manifest(report, objects.path_for(manifest_key(SYNTHETIC_CASELIST, week.snapshot)))


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def imported_data_dir(tmp_path: Path) -> Path:
    """A data directory holding the three imported synthetic weeks."""
    data_dir = tmp_path / "evidence"
    await import_synthetic_weeks(data_dir, tmp_path / "downloads")
    return data_dir


@pytest.fixture
def local(imported_data_dir: Path) -> LocalEvidence:
    """The imported data directory as the publisher reads it: named objects and blobs."""
    objects = FsEvidenceObjectStore(imported_data_dir)
    blobs = FsEvidenceObjectStore(imported_data_dir, subdirectory=Path("blobs"))
    return LocalEvidence(
        objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
    )


@pytest.fixture
def bucket(evidence_bucket: str, s3_client: S3Client) -> S3EvidenceObjectStore:
    """The moto evidence bucket, through the real S3 adapter."""
    return S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client)


# ------------------------------------------------------------------------------------------------
# A store to remove things from (v1-e30-t07)
# ------------------------------------------------------------------------------------------------

#: The fixed instant every removal test records entries at.
REMOVAL_TIME = datetime(2026, 9, 30, 18, 0, tzinfo=UTC)

#: The synthetic team every `--team` test removes, and the request it removes it under.
TEAM = "testcl26/Maple Grove/QX"
REQUEST = "RM-2026-01"


@dataclass
class RemovalWorld:
    """The three synthetic weeks and one OpenEv download, imported here and published to moto.

    The state an operator is in when a request arrives: everything on this machine is also in the
    environment's bucket, and `caselist status` would say so.
    """

    data_dir: Path
    bucket_name: str
    client: S3Client
    removal_inbox: Path | None = None
    """The inbox a removal purges, when not this machine's `<data_dir>/inbox`: a test of the pull that
    stages the inbox's state by hand gives the removal one it cannot reach, as a removal made on
    another machine is."""

    @property
    def bucket(self) -> S3EvidenceObjectStore:
        return S3EvidenceObjectStore(bucket=self.bucket_name, client=self.client)

    @property
    def local(self) -> LocalEvidence:
        objects = FsEvidenceObjectStore(self.data_dir)
        blobs = FsEvidenceObjectStore(self.data_dir, subdirectory=Path("blobs"))
        return LocalEvidence(
            objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
        )

    @property
    def repository(self) -> SqliteCaselistRepository:
        return SqliteCaselistRepository(SqliteDatabase.open(self.data_dir))

    @property
    def inbox(self) -> CaselistInbox:
        """The sync's inbox where the composition root puts it when `caselist.inbox_dir` is unset."""
        return CaselistInbox(
            directory=self.removal_inbox or self.data_dir / "inbox",
            state_dir=self.data_dir,
            archives=ZipArchiveRewriter(**_LIMITS),
        )

    def suppression(self) -> RecordedSuppressionList:
        """The local copy and the bucket's, as every bucket-holding command reads them."""
        return RecordedSuppressionList(
            local_suppression_list_file(self.data_dir),
            ObjectStoreAppendOnlyRecord(self.bucket, SUPPRESSION_LIST_KEY),
        )

    def planner(self, *, versions: EvidenceVersionStore | None = None) -> RemovalPlanner:
        return RemovalPlanner(
            caselists=self.repository,
            local=self.local,
            local_blobs=FsEvidenceVersionStore(self.data_dir / "blobs"),
            local_parsed=FsEvidenceVersionStore(self.data_dir / "parsed"),
            remote=self.bucket,
            remote_versions=versions or S3EvidenceVersionStore(bucket=self.bucket_name, client=self.client),
            inbox=self.inbox,
            suppression=self.suppression(),
            clock=FixedClock(REMOVAL_TIME),
            environment="dev",
            bucket=self.bucket_name,
        )

    def takedown(self) -> TakedownAccess:
        """The takedown credential's reach, on moto (which does not enforce IAM: the tests that need a
        refusal build one that refuses)."""
        return TakedownAccess(
            versions=S3EvidenceVersionStore(bucket=self.bucket_name, client=self.client),
            objects=self.bucket,
            profile="debate-dev-evidence-removal",
            bucket=self.bucket_name,
        )

    def service(self, *, takedown: Callable[[], TakedownAccess] | None = None) -> CaselistRemovalService:
        return CaselistRemovalService(
            planner=self.planner(),
            caselists=self.repository,
            local=self.local,
            local_blobs=FsEvidenceVersionStore(self.data_dir / "blobs"),
            local_parsed=FsEvidenceVersionStore(self.data_dir / "parsed"),
            inbox=self.inbox,
            remote=self.bucket,
            suppression=self.suppression(),
            local_suppression=local_suppression_list_file(self.data_dir),
            local_removal_log=local_removal_log_file(self.data_dir),
            takedown=takedown or self.takedown,
            clock=FixedClock(REMOVAL_TIME),
            environment="dev",
        )

    def tree(self) -> dict[str, bytes]:
        """Every file under the data directory, by path: what "changed nothing" is checked against."""
        return {
            path.relative_to(self.data_dir).as_posix(): path.read_bytes()
            for path in sorted(self.data_dir.rglob("*"))
            if path.is_file() and not path.name.startswith("debate.sqlite3")
        }

    def versions(self) -> list[tuple[str, str]]:
        """Every (key, version id) in the bucket, delete markers included."""
        listed = self.client.list_object_versions(Bucket=self.bucket_name)
        return sorted(
            [(str(v.get("Key")), str(v.get("VersionId"))) for v in listed.get("Versions", [])]
            + [(str(m.get("Key")), str(m.get("VersionId"))) for m in listed.get("DeleteMarkers", [])]
        )

    def records(self) -> list[str]:
        """Every caselist record in the database, rendered, for "changed nothing" checks."""
        database = SqliteDatabase.open(self.data_dir)
        rows: list[str] = []
        for table in (
            "caselist_sources",
            "caselist_disclosures",
            "caselist_camp_files",
            "caselist_snapshots",
        ):
            rows += [
                f"{table}:{row[0]}"
                for row in database.connection.execute(f"SELECT document FROM {table} ORDER BY 1")
            ]  # noqa: S608 - fixed table names
        return rows


async def import_synthetic_openev(data_dir: Path, downloads_dir: Path) -> None:
    """Import the first synthetic OpenEv download into `data_dir` and write its release manifest."""
    service = OpenEvImportService(
        caselists=SqliteCaselistRepository(SqliteDatabase.open(data_dir)),
        blobs=FsSnapshotStore(data_dir),
        suppression=empty_suppression_list(),
    )
    download = build_download_zips(downloads_dir)[OPENEV_DOWNLOADS[0].name]
    report = await service.import_release(
        read_archive(download, **_LIMITS),
        year=OPENEV_YEAR,
        event=Event(OPENEV_EVENT),
        imported_on=date(2026, 9, 14),
        archive_sha256=archive_digest(download),
        aliases=load_camp_aliases(CAMP_ALIASES_PATH),
    )
    write_manifest_lines(report.manifest_lines, FsEvidenceObjectStore(data_dir).path_for(report.manifest_key))


@pytest.fixture
async def removal_world(
    imported_data_dir: Path, tmp_path: Path, s3_client: S3Client, evidence_bucket: str
) -> RemovalWorld:
    await import_synthetic_openev(imported_data_dir, tmp_path / "openev-downloads")
    world = RemovalWorld(data_dir=imported_data_dir, bucket_name=evidence_bucket, client=s3_client)
    for caselist in (SYNTHETIC_CASELIST, "openev"):
        service = CaselistPublishService(
            local=world.local, remote=world.bucket, suppression=empty_suppression_list()
        )
        report = await service.execute(await service.plan(caselist))
        assert report.succeeded
    return world
