"""Imported, confirmed downloads leave the sync's inbox (`v1-e34-t11`).

Before this task nothing cleared `<data_dir>/inbox`. Every weekly archive and camp download stayed
after it was imported, and because the weeklies are cumulative the dev inbox grew by a season's
caselist every week (25 zips, 527 MB on 2026-10-01, measured by `v1-e30-t09`). The retention stage
removes a download once it is imported and its snapshot is confirmed in the bucket, under the run
lock, and the run summary names what went.

Everything here is real except the OpenCaselist source: the archive and OpenEv importers, the
manifests, the SQLite store, the blob store, the publisher and the status comparison, against moto.
The archives are the invented ones from `tests/fixtures/caselist/` and the camp files the invented
ones from `tests/fixtures/openev/` (no real caselist content, `docs/policies/caselist-data-use.md`).

Every expected list and count is written by hand from what each test sets up (working agreement 6).
A byte count freed is the sum of the sizes of the fixture files the test put in the inbox, read off
those files, not off the run.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_synthetic_archives import SYNTHETIC_CASELIST, build_snapshot_zips

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.import_service import CaselistImportService
from debate_core.application.caselist.openev_import_service import OpenEvImportService
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.status_service import CaselistStatusService
from debate_core.application.caselist_sync import CaselistSyncService, RunSummary, SyncStage
from debate_core.application.ports.caselist_source import (
    ArchiveKind,
    ArchiveListing,
    CaselistInfo,
    DownloadedFile,
    OpenEvFile,
    openev_inbox_name,
)
from debate_core.application.ports.evidence_store import EvidenceObjectStore
from debate_core.application.sync_runs import record_for_summary
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsEvidenceObjectStore, FsSnapshotStore, SqliteDatabase
from debate_core.integrations.local.archive_reader import read_archive
from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository
from debate_core.integrations.s3 import S3EvidenceObjectStore
from debate_core.testing.fakes import empty_suppression_list

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

CASELIST = SYNTHETIC_CASELIST
WEEK_1, WEEK_2, WEEK_3 = date(2026, 9, 1), date(2026, 9, 8), date(2026, 9, 15)
RUN_CLOCK = datetime(2026, 9, 16, 6, 0, tzinfo=UTC)
LIMITS = {"max_archive_bytes": 64 * 1024 * 1024, "max_unpacked_bytes": 64 * 1024 * 1024}


def weekly_name(day: date) -> str:
    return f"{CASELIST}-weekly-{day.isoformat()}.zip"


def label(day: date) -> str:
    """How the run summary names a weekly archive: its caselist and its date."""
    return f"{CASELIST} {day.isoformat()}"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ------------------------------------------------------------------------------------------------
# The source, and the installation a pull runs in
# ------------------------------------------------------------------------------------------------


class FakeSource:
    """OpenCaselist listing the given weeklies and camp files, and recording every download asked of it.

    A download is a request to OpenCaselist and, for an archive, one of the five a day:
    `archive_fetches` and `openev_fetches` are what reached the site.
    """

    def __init__(
        self, archives: dict[date, Path], *, weeks: Sequence[date], openev: Sequence[tuple[OpenEvFile, bytes]] = ()
    ) -> None:
        self.archives = archives
        self.weeks = list(weeks)
        self.openev = list(openev)
        self.archive_fetches: list[str] = []
        self.openev_fetches: list[int] = []

    async def list_caselists(self, *, archived: bool | None = None) -> list[CaselistInfo]:
        return [CaselistInfo(slug=CASELIST)]

    async def get_caselist(self, caselist: str) -> CaselistInfo:
        return CaselistInfo(slug=caselist)

    async def list_archives(self, caselist: str) -> list[ArchiveListing]:
        return [
            ArchiveListing(
                caselist=CASELIST,
                name=weekly_name(day),
                kind=ArchiveKind.WEEKLY,
                archive_date=day,
                url=f"https://files.example.invalid/{weekly_name(day)}",
            )
            for day in self.weeks
        ]

    async def list_openev(self, *, year: int | None = None) -> list[OpenEvFile]:
        return [file for file, _ in self.openev]

    async def download_archive(self, archive: ArchiveListing, inbox: Path) -> DownloadedFile:
        self.archive_fetches.append(archive.name)
        assert archive.archive_date is not None
        return _deliver(self.archives[archive.archive_date].read_bytes(), inbox / archive.name, archive.name)

    async def download_openev(self, file: OpenEvFile, inbox: Path) -> DownloadedFile:
        self.openev_fetches.append(file.openev_id)
        body = next(body for listed, body in self.openev if listed.openev_id == file.openev_id)
        return _deliver(body, inbox / openev_inbox_name(file), f"openev-{file.openev_id}")


def _deliver(body: bytes, destination: Path, source_name: str) -> DownloadedFile:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(body)
    return DownloadedFile(
        path=destination,
        sha256=hashlib.sha256(body).hexdigest(),
        byte_size=len(body),
        source_name=source_name,
    )


@dataclass
class Installation:
    """One environment's data directory, its inbox, and the moto bucket it publishes to."""

    data_dir: Path
    bucket: EvidenceObjectStore
    archives: dict[date, Path]
    status_remote: EvidenceObjectStore | None = None
    """The bucket the status comparison reads, when not the one published to."""
    built: list[CaselistSyncService] = field(default_factory=lambda: list[CaselistSyncService]())

    @property
    def inbox(self) -> Path:
        return self.data_dir / "inbox"

    @property
    def local(self) -> LocalEvidence:
        objects = FsEvidenceObjectStore(self.data_dir)
        blobs = FsEvidenceObjectStore(self.data_dir, subdirectory=Path("blobs"))
        return LocalEvidence(
            objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
        )

    def sync(self, source: FakeSource, *, bucket: bool = True) -> CaselistSyncService:
        """The pull as the composition root builds it for an environment with a bucket (or without)."""
        repository = SqliteCaselistRepository(SqliteDatabase.open(self.data_dir))
        blobs = FsSnapshotStore(self.data_dir)
        local = self.local
        return CaselistSyncService(
            source=source,
            archive_importer=CaselistImportService(
                caselists=repository, blobs=blobs, suppression=empty_suppression_list()
            ),
            openev_importer=OpenEvImportService(
                caselists=repository, blobs=blobs, suppression=empty_suppression_list()
            ),
            local=local,
            read_archive=lambda path: read_archive(path, **LIMITS),
            event_for_caselist=lambda slug: Event.LD if slug == CASELIST else None,
            inbox=self.inbox,
            state_dir=self.data_dir,
            suppression=empty_suppression_list(),
            publisher=(
                CaselistPublishService(local=local, remote=self.bucket, suppression=empty_suppression_list())
                if bucket
                else None
            ),
            status=(
                CaselistStatusService(
                    local=local, remote=self.status_remote or self.bucket, suppression=empty_suppression_list()
                )
                if bucket
                else None
            ),
            clock=lambda: RUN_CLOCK,
        )

    def inbox_names(self) -> set[str]:
        if not self.inbox.is_dir():
            return set()
        return {path.name for path in self.inbox.iterdir() if path.is_file()}

    def size_of(self, *days: date) -> int:
        """The bytes of the fixture archives for `days`: what removing their inbox copies frees."""
        return sum(self.archives[day].stat().st_size for day in days)


@pytest.fixture
def installation(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> Installation:
    return Installation(
        data_dir=tmp_path / "evidence",
        bucket=S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client),
        archives=build_snapshot_zips(tmp_path / "published"),
    )


def retention_of(summary: RunSummary) -> dict[str, object]:
    written = summary.as_json()["inbox_retention"]
    assert isinstance(written, dict)
    return written  # pyright: ignore[reportUnknownVariableType]


def removed(summary: RunSummary) -> list[str]:
    return [one["name"] for one in retention_of(summary)["removed"]]  # type: ignore[index,union-attr]


def stage_reason(summary: RunSummary, stage: SyncStage) -> str:
    record = summary.stage(stage)
    assert record is not None and record.reason is not None, summary.stages
    return record.reason


# ------------------------------------------------------------------------------------------------
# ac1: a week imported and confirmed this run leaves the inbox, and is not fetched again
# ------------------------------------------------------------------------------------------------


async def test_retention_removes_the_weeks_a_run_imported_and_confirmed_and_names_them(
    installation: Installation,
) -> None:
    """Two weeklies fetched, imported, published and confirmed: both zips leave, and both are named.

    The following run lists the same two weeks and fetches neither: an imported week is
    `already_imported` whether or not its zip is in the inbox (`_decide_archive`, `v1-e30-t09`).
    """
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])

    summary = await installation.sync(source).run([CASELIST])

    assert summary.succeeded, summary.stages
    assert installation.inbox_names() == set(), "an imported, confirmed week stayed in the inbox"
    assert removed(summary) == [label(WEEK_1), label(WEEK_2)]
    assert retention_of(summary)["bytes_freed"] == installation.size_of(WEEK_1, WEEK_2)
    reason = stage_reason(summary, SyncStage.RETENTION)
    assert label(WEEK_1) in reason and label(WEEK_2) in reason
    assert f"{installation.size_of(WEEK_1, WEEK_2)} bytes freed" in reason
    # The run log's record, which the bucket's run report is a copy of, carries the same sentence.
    record = record_for_summary(summary, environment="dev", mode="run")
    assert [entry.reason for entry in record.stages if entry.stage == "retention"] == [reason]

    again = await installation.sync(source).run([CASELIST])

    assert source.archive_fetches == [weekly_name(WEEK_1), weekly_name(WEEK_2)], "a removed week was fetched again"
    assert {one.name: str(one.decision) for one in again.archives} == {
        weekly_name(WEEK_1): "already_imported",
        weekly_name(WEEK_2): "already_imported",
    }
    assert again.nothing_new
