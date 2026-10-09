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
import io
import json
import shutil
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_synthetic_archives import (
    DOCUMENT_BODIES,
    SYNTHETIC_CASELIST,
    build_snapshot_zips,
)
from tests.fixtures.openev.build_synthetic_openev import DOCUMENT_BODIES as CAMP_BODIES
from tests.fixtures.openev.build_synthetic_openev import DOWNLOADS as CAMP_DOWNLOADS
from tests.fixtures.openev.build_synthetic_openev import build_download_zips

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.import_service import CaselistImportService
from debate_core.application.caselist.manifest import manifest_key, write_manifest
from debate_core.application.caselist.openev_import_service import OpenEvImportReport, OpenEvImportService
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.removal_plan import SourceSelector
from debate_core.application.caselist.status_service import CaselistStatusService
from debate_core.application.caselist_sync import (
    LOCK_FILENAME,
    OPENEV_DELIVERIES_FILENAME,
    CaselistSyncService,
    RunLock,
    RunSummary,
    StageOutcome,
    SyncRunInProgress,
    SyncStage,
)
from debate_core.application.errors import StoreCredentialsExpired, UnreadableArchive
from debate_core.application.ports.archive import ArchiveEntry
from debate_core.application.ports.caselist_source import (
    ArchiveKind,
    ArchiveListing,
    CaselistInfo,
    DownloadedFile,
    OpenEvFile,
    openev_inbox_name,
)
from debate_core.application.ports.evidence_store import EvidenceObjectStore, ObjectInfo, ObjectKey
from debate_core.application.ports.suppression import ReasonCode, SuppressionList
from debate_core.application.sync_runs import record_for_summary
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsEvidenceObjectStore, FsSnapshotStore, SqliteDatabase
from debate_core.integrations.local.archive_reader import archive_digest, read_archive
from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository
from debate_core.integrations.s3 import S3EvidenceObjectStore
from debate_core.testing.fakes import empty_suppression_list

from .conftest import REQUEST, RemovalWorld
from .test_sync_fetches_revised_camp_files import JUNK_RELEASE, junk_release_zip

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

CASELIST = SYNTHETIC_CASELIST
WEEK_1, WEEK_2, WEEK_3 = date(2026, 9, 1), date(2026, 9, 8), date(2026, 9, 15)
RUN_CLOCK = datetime(2026, 9, 16, 6, 0, tzinfo=UTC)
LIMITS = {"max_archive_bytes": 64 * 1024 * 1024, "max_unpacked_bytes": 64 * 1024 * 1024}
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def weekly_name(day: date) -> str:
    return f"{CASELIST}-weekly-{day.isoformat()}.zip"


def label(day: date) -> str:
    """How the run summary names a weekly archive: its caselist and its date."""
    return f"{CASELIST} {day.isoformat()}"


def sha256_label(body: bytes) -> str:
    """How the run summary names a camp download or any other file: by the start of its SHA-256."""
    return f"sha256 {hashlib.sha256(body).hexdigest()[:12]}"


#: A camp file published as a single document.
ESTUARY = OpenEvFile(
    openev_id=512,
    path="openev/2026/Tamarack/TSF-Estuary Solvency Advocate.docx",
    filename="TSF-Estuary Solvency Advocate.docx",
    year=2026,
    tags=("policy",),
)
ESTUARY_BODY = CAMP_BODIES["estuary-solvency"]

#: A camp release published as a zip: two camp files and one piece of macOS junk.
RELEASE = OpenEvFile(
    openev_id=901,
    path="openev/2026/Quillfeather/QDI Release.zip",
    filename="QDI Release.zip",
    year=2026,
    tags=("policy",),
)


def release_zip() -> bytes:
    """The release, byte-identically every time: fixed timestamps, members in path order."""
    members = (
        ("QDI Release/.DS_Store", b"\x00\x05\x16\x07 invented macOS metadata"),
        ("QDI Release/Quillfeather/QDI - Harbor Tariffs Aff.docx", CAMP_BODIES["harbor-tariffs-aff"]),
        ("QDI Release/Quillfeather/QDI - Harbor Tariffs Neg.docx", CAMP_BODIES["harbor-tariffs-neg"]),
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, body in members:
            info = zipfile.ZipInfo(path, date_time=_ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, body)
    return buffer.getvalue()


RELEASE_BODY = release_zip()


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
        self,
        archives: dict[date, Path],
        *,
        weeks: Sequence[date] = (),
        openev: Sequence[tuple[OpenEvFile, bytes]] = (),
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


class ExpiredBucket:
    """An evidence bucket whose credentials have run out: every call refuses the same way."""

    hint = "aws sso login --profile debate-dev-evidence"

    async def list_objects(self, prefix: str) -> tuple[ObjectInfo, ...]:
        raise StoreCredentialsExpired(hint=self.hint)

    async def head(self, key: ObjectKey) -> ObjectInfo:
        raise StoreCredentialsExpired(hint=self.hint)

    async def put_file(self, key: ObjectKey, source: Path) -> ObjectInfo:
        raise StoreCredentialsExpired(hint=self.hint)

    async def get_file(self, key: ObjectKey, destination: Path) -> ObjectInfo:
        raise StoreCredentialsExpired(hint=self.hint)


class FailingOpenEvImporter(OpenEvImportService):
    """The OpenEv importer refusing every download, as it does an unreadable one."""

    async def import_release(self, entries: Iterable[ArchiveEntry], **_: object) -> OpenEvImportReport:
        raise UnreadableArchive("an OpenEv download", "a fault this test injects")


@dataclass
class Installation:
    """One environment's data directory, its inbox, and the bucket it publishes to.

    `sync()` builds the pull the way the composition root does for an environment with a bucket:
    the publisher and the status comparison over the same local store and bucket. The keyword
    arguments stand in for the world going wrong in one way at a time.
    """

    data_dir: Path
    bucket: EvidenceObjectStore
    archives: dict[date, Path]
    suppression: SuppressionList | None = None
    """The list the importers, the skip and the status comparison read; empty unless a test removes."""

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

    def sync(
        self,
        source: FakeSource,
        *,
        bucket: bool = True,
        publish_to: EvidenceObjectStore | None = None,
        compare_with: EvidenceObjectStore | None = None,
        unreadable: Sequence[str] = (),
        openev_fails: bool = False,
    ) -> CaselistSyncService:
        """The pull.

        Args:
            bucket: False for an environment that names no bucket: no publisher, no status check.
            publish_to: The bucket the publisher writes to, when not :attr:`bucket`.
            compare_with: The bucket the status comparison reads, when not :attr:`bucket`.
            unreadable: Inbox file names the archive reader refuses, as it refuses a corrupt zip.
            openev_fails: Every OpenEv import is refused.
        """
        listed = self.suppression or empty_suppression_list()
        repository = SqliteCaselistRepository(SqliteDatabase.open(self.data_dir))
        blobs = FsSnapshotStore(self.data_dir)
        local = self.local
        importer = FailingOpenEvImporter if openev_fails else OpenEvImportService

        def reader(path: Path) -> Iterable[ArchiveEntry]:
            if path.name in unreadable:
                raise UnreadableArchive(path.name, "a fault this test injects")
            return read_archive(path, **LIMITS)

        return CaselistSyncService(
            source=source,
            archive_importer=CaselistImportService(caselists=repository, blobs=blobs, suppression=listed),
            openev_importer=importer(caselists=repository, blobs=blobs, suppression=listed),
            local=local,
            read_archive=reader,
            event_for_caselist=lambda slug: Event.LD if slug == CASELIST else None,
            inbox=self.inbox,
            state_dir=self.data_dir,
            suppression=listed,
            publisher=(
                CaselistPublishService(local=local, remote=publish_to or self.bucket, suppression=listed)
                if bucket
                else None
            ),
            status=(
                CaselistStatusService(local=local, remote=compare_with or self.bucket, suppression=listed)
                if bucket
                else None
            ),
            clock=lambda: RUN_CLOCK,
        )

    async def publish(self, caselist: str = CASELIST) -> None:
        """`caselist publish --caselist <caselist>`, every snapshot this machine holds."""
        service = CaselistPublishService(
            local=self.local, remote=self.bucket, suppression=self.suppression or empty_suppression_list()
        )
        assert (await service.execute(await service.plan(caselist))).succeeded

    def inbox_names(self) -> set[str]:
        """Every file under the inbox, by its path inside it."""
        if not self.inbox.is_dir():
            return set()
        return {path.relative_to(self.inbox).as_posix() for path in self.inbox.rglob("*") if path.is_file()}

    def inbox_state(self) -> dict[str, tuple[bytes, int]]:
        """Every file under the inbox with its bytes and modification time: what "changed nothing" means."""
        return {
            path.relative_to(self.inbox).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in sorted(self.inbox.rglob("*"))
            if path.is_file()
        }

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


@pytest.fixture
def empty_bucket(s3_client: S3Client) -> S3EvidenceObjectStore:
    """A second bucket in the same moto account, holding nothing: a comparison against it confirms nothing."""
    s3_client.create_bucket(Bucket="debate-test-evidence-moto-empty")
    return S3EvidenceObjectStore(bucket="debate-test-evidence-moto-empty", client=s3_client)


async def backlog(installation: Installation, *weeks: date) -> FakeSource:
    """The inbox a build before this task leaves: weeks pulled, imported and published, zips still here.

    The pull runs with no bucket, so it imports and its retention has nothing to confirm against;
    `caselist publish` then puts every snapshot in the bucket, which is where the earlier builds'
    own publish left them.
    """
    source = FakeSource(installation.archives, weeks=weeks)
    pulled = await installation.sync(source, bucket=False).run([CASELIST])
    assert pulled.succeeded, pulled.stages
    assert installation.inbox_names() == {weekly_name(day) for day in weeks}
    await installation.publish()
    return source


def retention_of(summary: RunSummary) -> dict[str, object]:
    written = summary.as_json()["inbox_retention"]
    assert isinstance(written, dict)
    return written  # pyright: ignore[reportUnknownVariableType]


def removed(summary: RunSummary) -> list[str]:
    return [one["name"] for one in retention_of(summary)["removed"]]  # type: ignore[index,union-attr]


def kept(summary: RunSummary) -> dict[str, str]:
    return {one["name"]: one["reason"] for one in retention_of(summary)["kept"]}  # type: ignore[index,union-attr]


def stage_reason(summary: RunSummary, stage: SyncStage) -> str:
    record = summary.stage(stage)
    assert record is not None and record.reason is not None, summary.stages
    return record.reason


def outcome(summary: RunSummary, stage: SyncStage) -> StageOutcome:
    record = summary.stage(stage)
    assert record is not None, summary.stages
    return record.outcome


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

    assert source.archive_fetches == [weekly_name(WEEK_1), weekly_name(WEEK_2)], (
        "a removed week was fetched again"
    )
    assert {one.name: str(one.decision) for one in again.archives} == {
        weekly_name(WEEK_1): "already_imported",
        weekly_name(WEEK_2): "already_imported",
    }
    assert again.nothing_new


async def test_retention_clears_a_backlog_on_a_run_that_downloads_nothing(installation: Installation) -> None:
    """The first run after this task ships: weeks earlier builds imported and published, zips kept.

    Nothing new is listed, so the run downloads, imports and publishes nothing. Retention still
    runs, compares each week with the bucket itself, and removes all three.
    """
    source = await backlog(installation, WEEK_1, WEEK_2, WEEK_3)

    summary = await installation.sync(source).run([CASELIST])

    assert source.archive_fetches == [weekly_name(WEEK_1), weekly_name(WEEK_2), weekly_name(WEEK_3)]
    assert summary.archives_downloaded == 0 and summary.snapshots_imported == ()
    assert outcome(summary, SyncStage.REPORT) is StageOutcome.SKIPPED
    assert outcome(summary, SyncStage.RETENTION) is StageOutcome.COMPLETED
    assert removed(summary) == [label(WEEK_1), label(WEEK_2), label(WEEK_3)]
    assert retention_of(summary)["bytes_freed"] == installation.size_of(WEEK_1, WEEK_2, WEEK_3)
    assert installation.inbox_names() == set()


# ------------------------------------------------------------------------------------------------
# ac2: what is not imported, or not confirmed, stays and is finished by the next run
# ------------------------------------------------------------------------------------------------


async def test_retention_keeps_a_week_whose_import_failed_and_the_next_run_imports_and_removes_it(
    installation: Installation,
) -> None:
    """09-08's zip cannot be read in the first run: 09-01 leaves, 09-08 stays for `v1-e34-t06`'s retry.

    The second run imports 09-08 from the inbox without downloading it again, publishes it, and
    only then removes it.
    """
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])

    first = await installation.sync(source, unreadable=[weekly_name(WEEK_2)]).run([CASELIST])

    assert outcome(first, SyncStage.IMPORT) is StageOutcome.FAILED
    assert removed(first) == [label(WEEK_1)]
    assert kept(first) == {label(WEEK_2): "not_imported"}
    assert installation.inbox_names() == {weekly_name(WEEK_2)}
    assert f"1 kept: {label(WEEK_2)} (not imported)" in stage_reason(first, SyncStage.RETENTION)

    second = await installation.sync(source).run([CASELIST])

    assert source.archive_fetches == [weekly_name(WEEK_1), weekly_name(WEEK_2)], "09-08 was fetched again"
    assert second.snapshots_imported == (label(WEEK_2),)
    assert removed(second) == [label(WEEK_2)]
    assert installation.inbox_names() == set()


async def test_retention_keeps_weeks_whose_publish_is_pending_and_removes_them_once_it_is_confirmed(
    installation: Installation,
) -> None:
    """An expired SSO session: imported, publish and report pending, so nothing is confirmed.

    The bucket cannot be read for retention's own check either, and both weeks stay. After
    `aws sso login` the next run drains the pending publish, its report confirms both, and they go.
    """
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])

    expired = await installation.sync(source, publish_to=ExpiredBucket(), compare_with=ExpiredBucket()).run(
        [CASELIST]
    )

    assert outcome(expired, SyncStage.PUBLISH) is StageOutcome.PENDING
    assert kept(expired) == {label(WEEK_1): "not_confirmed", label(WEEK_2): "not_confirmed"}
    assert removed(expired) == []
    assert installation.inbox_names() == {weekly_name(WEEK_1), weekly_name(WEEK_2)}

    logged_in = await installation.sync(source).run([CASELIST])

    assert source.archive_fetches == [weekly_name(WEEK_1), weekly_name(WEEK_2)]
    assert outcome(logged_in, SyncStage.REPORT) is StageOutcome.COMPLETED
    assert removed(logged_in) == [label(WEEK_1), label(WEEK_2)]
    assert installation.inbox_names() == set()


async def test_retention_keeps_a_week_the_report_found_out_of_sync_although_its_publish_succeeded(
    installation: Installation, empty_bucket: S3EvidenceObjectStore
) -> None:
    """The publish stage's word is not a confirmation; the report stage's comparison is.

    The publish uploads to the bucket, and the comparison reads another one that holds nothing, so
    the report finds both weeks missing and retention keeps them.
    """
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])

    summary = await installation.sync(source, compare_with=empty_bucket).run([CASELIST])

    assert outcome(summary, SyncStage.PUBLISH) is StageOutcome.COMPLETED
    assert outcome(summary, SyncStage.REPORT) is StageOutcome.FAILED
    assert kept(summary) == {label(WEEK_1): "not_confirmed", label(WEEK_2): "not_confirmed"}
    assert installation.inbox_names() == {weekly_name(WEEK_1), weekly_name(WEEK_2)}


async def test_retention_compares_a_week_an_earlier_run_imported_afresh_and_keeps_it_when_the_bucket_lost_it(
    installation: Installation, s3_client: S3Client, evidence_bucket: str
) -> None:
    """A week an earlier run published is not taken on that run's word: retention compares it now.

    09-01 and 09-08 were imported and published before; then 09-08's manifest goes from the bucket.
    The run publishes nothing (nothing new), so its report confirms nothing, and retention's own
    comparison finds 09-01 in sync and 09-08 not. After `caselist publish` puts it back, the next
    run removes it.
    """
    source = await backlog(installation, WEEK_1, WEEK_2)
    s3_client.delete_object(Bucket=evidence_bucket, Key=manifest_key(CASELIST, WEEK_2))

    summary = await installation.sync(source).run([CASELIST])

    assert outcome(summary, SyncStage.PUBLISH) is StageOutcome.SKIPPED
    assert removed(summary) == [label(WEEK_1)]
    assert kept(summary) == {label(WEEK_2): "not_confirmed"}
    assert installation.inbox_names() == {weekly_name(WEEK_2)}

    await installation.publish()
    again = await installation.sync(source).run([CASELIST])

    assert removed(again) == [label(WEEK_2)]
    assert installation.inbox_names() == set()


async def test_retention_keeps_a_weekly_whose_bytes_are_not_the_ones_imported(
    installation: Installation,
) -> None:
    """09-01 was imported from another copy, so its manifest names other bytes than the inbox zip's.

    The week is held and published, but these bytes were never imported, so they stay, named.
    """
    database = SqliteDatabase.open(installation.data_dir)
    report = await CaselistImportService(
        caselists=SqliteCaselistRepository(database),
        blobs=FsSnapshotStore(installation.data_dir),
        suppression=empty_suppression_list(),
    ).import_archive(
        read_archive(installation.archives[WEEK_1], **LIMITS),
        caselist=CASELIST,
        snapshot=WEEK_1,
        event=Event.LD,
        archive_sha256="f" * 64,
    )
    objects = FsEvidenceObjectStore(installation.data_dir)
    write_manifest(report, objects.path_for(manifest_key(CASELIST, WEEK_1)))
    await installation.publish()
    installation.inbox.mkdir(parents=True)
    shutil.copyfile(installation.archives[WEEK_1], installation.inbox / weekly_name(WEEK_1))

    summary = await installation.sync(FakeSource(installation.archives, weeks=[WEEK_1])).run([CASELIST])

    assert {one.name: str(one.decision) for one in summary.archives} == {
        weekly_name(WEEK_1): "already_imported"
    }
    assert kept(summary) == {label(WEEK_1): "not_imported"}
    assert installation.inbox_names() == {weekly_name(WEEK_1)}


async def test_retention_keeps_and_names_files_the_pull_did_not_name(installation: Installation) -> None:
    """A note and a copy put in the inbox by hand stay, named by their SHA-256 alone, never by name."""
    source = await backlog(installation, WEEK_1)
    note = b"a note somebody left here"
    copy = installation.archives[WEEK_2].read_bytes()
    (installation.inbox / "Maple Grove notes.txt").write_bytes(note)
    (installation.inbox / "by hand").mkdir()
    (installation.inbox / "by hand" / weekly_name(WEEK_2)).write_bytes(copy)

    summary = await installation.sync(source).run([CASELIST])

    assert removed(summary) == [label(WEEK_1)]
    assert kept(summary) == {sha256_label(copy): "unclassified", sha256_label(note): "unclassified"}
    assert installation.inbox_names() == {"Maple Grove notes.txt", f"by hand/{weekly_name(WEEK_2)}"}
    reason = stage_reason(summary, SyncStage.RETENTION)
    assert "2 kept: 2 other file(s)" in reason and "(not a download the pull names)" in reason
    assert "Maple Grove" not in reason and "Maple Grove" not in json.dumps(retention_of(summary))


async def test_retention_removes_nothing_where_no_bucket_can_confirm_a_publish(
    installation: Installation,
) -> None:
    summary = await installation.sync(FakeSource(installation.archives, weeks=[WEEK_1]), bucket=False).run(
        [CASELIST]
    )

    assert outcome(summary, SyncStage.RETENTION) is StageOutcome.SKIPPED
    assert "nothing leaves the inbox" in stage_reason(summary, SyncStage.RETENTION)
    assert summary.inbox_retention is None
    assert installation.inbox_names() == {weekly_name(WEEK_1)}


async def test_retention_is_not_part_of_publish_pending(installation: Installation) -> None:
    """`--publish-pending` completes publishes and nothing else; the next pull removes what it confirmed."""
    source = FakeSource(installation.archives, weeks=[WEEK_1])
    await installation.sync(source, publish_to=ExpiredBucket(), compare_with=ExpiredBucket()).run([CASELIST])

    drained = await installation.sync(source).publish_pending()

    assert outcome(drained, SyncStage.REPORT) is StageOutcome.COMPLETED
    assert outcome(drained, SyncStage.RETENTION) is StageOutcome.SKIPPED
    assert installation.inbox_names() == {weekly_name(WEEK_1)}

    after = await installation.sync(source).run([CASELIST])

    assert removed(after) == [label(WEEK_1)]


# ------------------------------------------------------------------------------------------------
# ac2: a dry run removes nothing and lists what a run would remove
# ------------------------------------------------------------------------------------------------


async def test_retention_in_a_dry_run_removes_nothing_and_lists_what_the_run_then_removes(
    installation: Installation,
) -> None:
    """Two weeks imported and published before, a third new on the site.

    The dry run would remove the two now, and the third once a run has imported it and the bucket
    confirms it. The real run that follows removes exactly those three.
    """
    await backlog(installation, WEEK_1, WEEK_2)
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2, WEEK_3])
    before = installation.inbox_state()

    dry = await installation.sync(source).run([CASELIST], dry_run=True)

    assert installation.inbox_state() == before, "the dry run changed the inbox"
    assert source.archive_fetches == []
    assert outcome(dry, SyncStage.RETENTION) is StageOutcome.PLANNED
    written = retention_of(dry)
    assert written["removed"] == [] and written["bytes_freed"] == 0
    assert [one["name"] for one in written["would_remove"]] == [label(WEEK_1), label(WEEK_2)]  # type: ignore[union-attr]
    assert written["bytes_would_free"] == installation.size_of(WEEK_1, WEEK_2)
    assert written["would_remove_once_imported"] == [label(WEEK_3)]
    reason = stage_reason(dry, SyncStage.RETENTION)
    would_free = installation.size_of(WEEK_1, WEEK_2)
    assert reason.startswith(f"would remove 2 file(s), {would_free} bytes: {label(WEEK_1)}, {label(WEEK_2)}")
    assert reason.endswith(
        f"once this run has imported them and the bucket confirms their publish, also {label(WEEK_3)}"
    )

    real = await installation.sync(source).run([CASELIST])

    assert removed(real) == [label(WEEK_1), label(WEEK_2), label(WEEK_3)]
    assert installation.inbox_names() == set()


# ------------------------------------------------------------------------------------------------
# ac3: a camp download goes only once the delivery record holds its digests
# ------------------------------------------------------------------------------------------------


async def test_retention_removes_camp_downloads_once_recorded_and_the_next_pull_fetches_neither(
    installation: Installation,
) -> None:
    """A single camp document and a camp release zip, imported, recorded, published and confirmed.

    Both leave, named by count and SHA-256 prefix, never by a camp's title. The next pull knows the
    document by the id its manifest row carries and the zip by the delivery record, and fetches
    neither.
    """
    source = FakeSource(installation.archives, openev=[(ESTUARY, ESTUARY_BODY), (RELEASE, RELEASE_BODY)])

    summary = await installation.sync(source).run([CASELIST])

    assert summary.succeeded, summary.stages
    assert removed(summary) == [sha256_label(ESTUARY_BODY), sha256_label(RELEASE_BODY)]
    assert retention_of(summary)["bytes_freed"] == len(ESTUARY_BODY) + len(RELEASE_BODY)
    reason = stage_reason(summary, SyncStage.RETENTION)
    assert f"2 camp download(s), {sha256_label(ESTUARY_BODY)}, {sha256_label(RELEASE_BODY)}" in reason
    record = record_for_summary(summary, environment="dev", mode="run")
    for title in ("Estuary", "QDI", "Tamarack", "Quillfeather"):
        assert title not in reason and title not in json.dumps(retention_of(summary))
        assert title not in record.model_dump_json()
    assert installation.inbox_names() == set()

    again = await installation.sync(source).run([CASELIST])

    assert source.openev_fetches == [ESTUARY.openev_id, RELEASE.openev_id], (
        "a removed camp file was fetched again"
    )
    assert {one.openev_id: str(one.decision) for one in again.openev} == {
        ESTUARY.openev_id: "already_imported",
        RELEASE.openev_id: "already_imported",
    }


async def test_retention_removes_a_revised_camp_file_only_on_the_conditions_any_camp_download_meets(
    installation: Installation, empty_bucket: S3EvidenceObjectStore
) -> None:
    """512 is pulled and leaves the inbox; upstream deletes it and 640 is uploaded at its path.

    640 is fetched as a revision of 512 (`v1-e34-t08`) and is a camp download like any other here:
    with its release not confirmed in the bucket it stays, and once it is confirmed it goes, named
    by its SHA-256 prefix. 512 is not fetched again.
    """
    revised_body = CAMP_BODIES["canal-counterplan-revised"]
    source = FakeSource(installation.archives, openev=[(ESTUARY, ESTUARY_BODY)])
    first = await installation.sync(source).run([CASELIST])
    assert removed(first) == [sha256_label(ESTUARY_BODY)]
    source.openev = [(ESTUARY.model_copy(update={"openev_id": 640}), revised_body)]

    unconfirmed = await installation.sync(source, compare_with=empty_bucket).run([CASELIST])

    assert source.openev_fetches == [ESTUARY.openev_id, 640]
    assert [one.revision_of for one in unconfirmed.openev] == [ESTUARY.openev_id]
    assert kept(unconfirmed) == {sha256_label(revised_body): "not_confirmed"}

    confirmed = await installation.sync(source).run([CASELIST])

    assert source.openev_fetches == [ESTUARY.openev_id, 640]
    assert removed(confirmed) == [sha256_label(revised_body)]
    assert installation.inbox_names() == set()


async def test_retention_keeps_a_camp_release_of_junk_alone_and_the_next_pull_does_not_import_it_again(
    installation: Installation,
) -> None:
    """A camp release holding only junk (`v1-e30-t09` Follow-up 4) has no manifest row with a
    classification, so no manifest came from its bytes and retention keeps it as `not_imported`,
    before `v1-e34-t08` and after. What changed is the next pull: it used to import it again."""
    source = FakeSource(installation.archives, openev=[(JUNK_RELEASE, junk_release_zip())])

    first = await installation.sync(source).run([CASELIST])

    assert kept(first) == {sha256_label(junk_release_zip()): "not_imported"}

    again = await installation.sync(source).run([CASELIST])

    assert source.openev_fetches == [JUNK_RELEASE.openev_id]
    assert again.snapshots_imported == (), "the junk-only release was imported again"
    assert kept(again) == {sha256_label(junk_release_zip()): "not_imported"}


async def test_retention_keeps_a_camp_download_the_delivery_record_does_not_cover(
    installation: Installation,
) -> None:
    """Imported and published, but the delivery record lost (or never written, before `v1-e34-t07`).

    Both downloads stay. Without its copy and without the record, the next pull could not tell the
    zip was imported, and would fetch it again; with the copy kept, it fetches nothing.
    """
    source = FakeSource(installation.archives, openev=[(ESTUARY, ESTUARY_BODY), (RELEASE, RELEASE_BODY)])
    await installation.sync(source, bucket=False).run([CASELIST])
    (installation.data_dir / OPENEV_DELIVERIES_FILENAME).unlink()
    await installation.publish("openev")

    summary = await installation.sync(source).run([CASELIST])

    assert kept(summary) == {
        sha256_label(ESTUARY_BODY): "no_delivery_record",
        sha256_label(RELEASE_BODY): "no_delivery_record",
    }
    assert "(the delivery record does not hold its digests)" in stage_reason(summary, SyncStage.RETENTION)
    assert installation.inbox_names() == {openev_inbox_name(ESTUARY), openev_inbox_name(RELEASE)}

    await installation.sync(source).run([CASELIST])

    assert source.openev_fetches == [ESTUARY.openev_id, RELEASE.openev_id]


async def test_retention_keeps_a_camp_download_waiting_for_its_import_although_the_record_holds_its_digests(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    """The retry hold: a camp file fetched again after an `unsuppress`, whose import then failed.

    Its first import left the delivery record holding its digests, and the release it belongs to is
    published and in sync, kept there by the camp release zip beside it. But the removal took the
    file's own manifest rows out, so no manifest came from these bytes: it is waiting for
    `v1-e34-t06`'s retry, and stays. The next run imports it from the inbox without fetching it
    again, and only then removes it.
    """
    world = RemovalWorld(data_dir=tmp_path / "evidence", bucket_name=evidence_bucket, client=s3_client)
    installation = Installation(
        data_dir=world.data_dir,
        bucket=world.bucket,
        archives=build_snapshot_zips(tmp_path / "published"),
        suppression=world.suppression(),
    )
    source = FakeSource(installation.archives, openev=[(ESTUARY, ESTUARY_BODY), (RELEASE, RELEASE_BODY)])
    first = await installation.sync(source).run([CASELIST])
    assert removed(first) == [sha256_label(ESTUARY_BODY), sha256_label(RELEASE_BODY)]
    removal = world.service()
    estuary_sha256 = hashlib.sha256(ESTUARY_BODY).hexdigest()
    plan = await removal.plan(
        SourceSelector(estuary_sha256), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_CAMP
    )
    assert (await removal.execute(plan)).completed
    await removal.unsuppress(
        await removal.plan_unsuppress(estuary_sha256, reason=ReasonCode.REMOVED_IN_ERROR)
    )

    failed = await installation.sync(source, openev_fails=True).run([CASELIST])

    fetched = [ESTUARY.openev_id, RELEASE.openev_id, ESTUARY.openev_id]
    assert source.openev_fetches == fetched, (
        "the camp file is fetched again after the unsuppress, and only it"
    )
    assert outcome(failed, SyncStage.IMPORT) is StageOutcome.FAILED
    assert kept(failed) == {sha256_label(ESTUARY_BODY): "not_imported"}
    assert installation.inbox_names() == {openev_inbox_name(ESTUARY)}

    retried = await installation.sync(source).run([CASELIST])

    assert source.openev_fetches == fetched, "the waiting copy was fetched again"
    assert retried.snapshots_imported == ("openev 2026-policy",)
    assert removed(retried) == [sha256_label(ESTUARY_BODY)]
    assert installation.inbox_names() == set()


# ------------------------------------------------------------------------------------------------
# The run lock, and a removal
# ------------------------------------------------------------------------------------------------


async def test_retention_removes_files_only_while_the_run_holds_the_lock(
    installation: Installation, monkeypatch: pytest.MonkeyPatch
) -> None:
    """At the moment each inbox file is deleted, another holder (a removal) cannot take the lock."""
    source = await backlog(installation, WEEK_1, WEEK_2)
    lock = installation.data_dir / LOCK_FILENAME
    seen: list[str] = []
    unlink = Path.unlink

    def watched(path: Path, missing_ok: bool = False) -> None:
        if path.parent == installation.inbox:
            try:
                with RunLock(lock):
                    seen.append(f"{path.name}: lock free")
            except SyncRunInProgress:
                seen.append(f"{path.name}: lock held")
        unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", watched)

    summary = await installation.sync(source).run([CASELIST])

    assert removed(summary) == [label(WEEK_1), label(WEEK_2)]
    assert seen == [f"{weekly_name(WEEK_1)}: lock held", f"{weekly_name(WEEK_2)}: lock held"]


async def test_retention_does_not_run_while_a_removal_holds_the_lock(installation: Installation) -> None:
    """A removal changing the inbox holds the sync's lock; a pull started then does nothing at all."""
    source = await backlog(installation, WEEK_1)
    before = installation.inbox_state()

    with RunLock(installation.data_dir / LOCK_FILENAME), pytest.raises(SyncRunInProgress):
        await installation.sync(source).run([CASELIST])

    assert installation.inbox_state() == before


async def test_a_removal_then_retention_each_removes_only_its_own_files(
    removal_world: RemovalWorld, tmp_path: Path
) -> None:
    """`caselist remove` deletes the week holding the removed file; the next pull's retention the rest.

    The world imported the three synthetic weeks and one camp release and published them; the inbox
    holds the very bytes it imported, as a pull leaves it. The Bayview semifinal negative is new in
    09-15, so the removal deletes 09-15's zip (imported, so deleted rather than rewritten,
    `v1-e30-t09`) and nothing else. Retention then removes 09-01 and 09-08, and keeps the camp
    release, which was imported before the delivery record existed. Nothing is counted twice, and
    nothing a removal deleted is fetched again.
    """
    archives = build_snapshot_zips(tmp_path / "published")
    inbox = removal_world.data_dir / "inbox"
    inbox.mkdir(parents=True)
    for day in (WEEK_1, WEEK_2, WEEK_3):
        shutil.copyfile(archives[day], inbox / weekly_name(day))
    camp_release = build_download_zips(tmp_path / "openev")[CAMP_DOWNLOADS[0].name]
    camp_name = f"openev-701-{CAMP_DOWNLOADS[0].name}.zip"
    shutil.copyfile(camp_release, inbox / camp_name)
    bayview = hashlib.sha256(DOCUMENT_BODIES["bayview-semis-neg"]).hexdigest()
    holding = {
        day
        for day in (WEEK_1, WEEK_2, WEEK_3)
        if any(hashlib.sha256(member).hexdigest() == bayview for member in _members(archives[day]))
    }
    assert holding == {WEEK_3}, "the fixture: the removed file is in 09-15 alone"

    removal = removal_world.service()
    plan = await removal.plan(
        SourceSelector(bayview), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM
    )
    report = await removal.execute(plan)

    assert report.completed and report.inbox_files_deleted == 1
    assert {path.name for path in inbox.iterdir()} == {weekly_name(WEEK_1), weekly_name(WEEK_2), camp_name}

    installation = Installation(
        data_dir=removal_world.data_dir,
        bucket=removal_world.bucket,
        archives=archives,
        suppression=removal_world.suppression(),
    )
    source = FakeSource(archives, weeks=[WEEK_1, WEEK_2, WEEK_3])
    summary = await installation.sync(source).run([CASELIST])

    assert source.archive_fetches == [], "a week the removal deleted was fetched again"
    assert removed(summary) == [label(WEEK_1), label(WEEK_2)]
    assert kept(summary) == {sha256_label(camp_release.read_bytes()): "no_delivery_record"}
    assert {path.name for path in inbox.iterdir()} == {camp_name}
    assert archive_digest(camp_release) == hashlib.sha256((inbox / camp_name).read_bytes()).hexdigest()


def _members(path: Path) -> list[bytes]:
    with zipfile.ZipFile(path) as archive:
        return [archive.read(info) for info in archive.infolist() if not info.is_dir()]
