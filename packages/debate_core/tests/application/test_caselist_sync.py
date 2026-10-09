"""What one weekly `caselist pull` does, and what it does when a piece of it is missing.

The service under test is `debate_core.application.caselist_sync.CaselistSyncService`. Everything
around it is real except the source: the archive importer, the OpenEv importer, the manifests, the
SQLite store, the blob store and — where a bucket is needed — the S3 adapter against moto. The
source is a fake, because what has to be exercised here is the *decisions*: which archives are
selected, in which order they are fetched, what is not fetched at all, and what happens when the
site applies its daily limiter or the operator's AWS session has expired.

## Where the numbers come from

Every expected count in this module is written by hand, from the fixture's own committed,
hand-written `tests/fixtures/caselist/expected_summary.json` and from the reasoning in the comment
beside it (`docs/process/working-agreements.md` §6). None of them was produced by running the
service and recording what it said.

The scenario, once, so the numbers below can be read against it. `testcl26-weekly-2026-09-01.zip`
is imported before the run, so it is the baseline the run has already. The fake source then lists:

| Listed name | Kind | What the run must decide |
|---|---|---|
| `testcl26-weekly-2026-09-01.zip` | WEEKLY | already imported — not newer than the latest manifest |
| `testcl26-weekly-2026-09-08.zip` | WEEKLY | download, first |
| `testcl26-weekly-2026-09-15.zip` | WEEKLY | download, second |
| `testcl26-all-2026-09-15.zip` | FULL | a weekly run does not pull the full archive |
| `testcl26-archive-notes.txt` | UNRECOGNISED | no date, so never downloaded |

and one OpenEv camp file that is new (`openev-512-…`), tagged `policy`.

Nothing here is real caselist content: the archives are the invented ones from
`tests/fixtures/caselist/` (`docs/policies/caselist-data-use.md`).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from tests.fixtures.caselist.build_synthetic_archives import (
    SNAPSHOTS,
    SYNTHETIC_CASELIST,
    build_snapshot_zips,
)
from tests.fixtures.openev.build_synthetic_openev import DOCUMENT_BODIES, build_download_zips
from tests.fixtures.openev.build_synthetic_openev import expected as expected_openev

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.import_service import CaselistImportService
from debate_core.application.caselist.manifest import (
    manifest_key,
    read_manifest_lines,
    write_manifest,
    write_manifest_lines,
)
from debate_core.application.caselist.openev_import_service import OpenEvImportService
from debate_core.application.caselist.openev_manifest import openev_manifest_key
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.status_service import CaselistStatusService
from debate_core.application.caselist_sync import (
    DEFAULT_BULK_DOWNLOADS_PER_DAY,
    DOWNLOAD_LEDGER_FILENAME,
    LEGACY_DOWNLOAD_LEDGER_FILENAME,
    LOCK_FILENAME,
    PENDING_WORK_FILENAME,
    RUN_SUMMARY_DIRECTORY,
    RUN_SUMMARY_SCHEMA_VERSION,
    ArchiveSelection,
    CaselistSyncService,
    DownloadLedger,
    LandscapeStageResult,
    NoCaselistsConfigured,
    ParseStageResult,
    PendingWork,
    RunLock,
    SelectionDecision,
    StageOutcome,
    SyncRunInProgress,
    SyncStage,
    _held_openev_ids,  # pyright: ignore[reportPrivateUsage]
    within_daily_budget,
)
from debate_core.application.errors import (
    ProviderRateLimited,
    StoreCredentialsExpired,
    UnreadableArchive,
)
from debate_core.application.ports.archive import ArchiveEntry
from debate_core.application.ports.caselist_source import (
    ArchiveKind,
    ArchiveListing,
    CaselistAuthExpired,
    CaselistInfo,
    DownloadedFile,
    OpenEvFile,
    openev_inbox_name,
)
from debate_core.application.ports.evidence_store import ObjectInfo, ObjectKey
from debate_core.application.ports.notifier import Notification, RecordingNotifier
from debate_core.application.sync_runs import (
    SYNC_RUN_LOG_FILENAME,
    SyncRunLog,
    SyncRunMonitor,
    SyncRunOutcome,
    SyncRunRecord,
)
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsEvidenceObjectStore, FsSnapshotStore, SqliteDatabase
from debate_core.integrations.local.archive_reader import archive_digest, read_archive
from debate_core.integrations.local.macos_notifier import MacOsNotifier
from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository
from debate_core.integrations.s3 import S3EvidenceObjectStore
from debate_core.testing.fakes import empty_suppression_list

if TYPE_CHECKING:  # pragma: no cover - imported for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

RUN_CLOCK = datetime(2026, 9, 16, 6, 0, tzinfo=UTC)
"""A Wednesday morning, the day after the 09-15 archives are published."""

OPENEV_FILE_ID = 512
OPENEV_YEAR = 2026
_LIMITS = {"max_archive_bytes": 64 * 1024 * 1024, "max_unpacked_bytes": 64 * 1024 * 1024}


def weekly_name(day: date) -> str:
    return f"{SYNTHETIC_CASELIST}-weekly-{day.isoformat()}.zip"


def full_name(day: date) -> str:
    return f"{SYNTHETIC_CASELIST}-all-{day.isoformat()}.zip"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ------------------------------------------------------------------------------------------------
# The fake source
# ------------------------------------------------------------------------------------------------


class FakeCaselistSource:
    """A `CaselistArchiveSource` over files on disk, which records every call it is asked to make.

    It behaves like the real client in the one way that matters to this suite: **a download of a
    file the inbox already holds still costs a fetch.** The client streams the whole archive and
    only then notices the bytes are identical (`v1-e34-t01`), so `already_present` is not a saving
    — which is why the service checks the inbox itself, and why this fake counts such a call.
    """

    def __init__(self) -> None:
        self.archives: dict[str, list[tuple[ArchiveListing, Path | None]]] = {}
        self.openev_files: list[tuple[OpenEvFile, bytes]] = []
        self.archive_fetches: list[str] = []
        self.openev_fetches: list[int] = []
        self.listings_requested: list[str] = []
        self.rate_limit_after: int | None = None
        self.rate_limit_retry_after: float = 86_400.0

    # --- listing --------------------------------------------------------------------------------

    async def list_caselists(self, *, archived: bool | None = None) -> list[CaselistInfo]:
        return [CaselistInfo(slug=slug) for slug in self.archives]

    async def get_caselist(self, caselist: str) -> CaselistInfo:
        return CaselistInfo(slug=caselist)

    async def list_archives(self, caselist: str) -> list[ArchiveListing]:
        self.listings_requested.append(caselist)
        return [listing for listing, _ in self.archives.get(caselist, [])]

    async def list_openev(self, *, year: int | None = None) -> list[OpenEvFile]:
        return [file for file, _ in self.openev_files]

    # --- downloading ----------------------------------------------------------------------------

    async def download_archive(self, archive: ArchiveListing, inbox: Path) -> DownloadedFile:
        if self.rate_limit_after is not None and len(self.archive_fetches) >= self.rate_limit_after:
            raise ProviderRateLimited(
                "opencaselist",
                "the daily bulk download limit was reached",
                retry_after_seconds=self.rate_limit_retry_after,
            )
        self.archive_fetches.append(archive.name)
        source = next(
            path for listing, path in self.archives[archive.caselist] if listing.name == archive.name
        )
        assert source is not None, "a listing selected for download must have bytes behind it"
        return _deliver(source.read_bytes(), inbox / archive.name, archive.name)

    async def download_openev(self, file: OpenEvFile, inbox: Path) -> DownloadedFile:
        self.openev_fetches.append(file.openev_id)
        body = next(body for listed, body in self.openev_files if listed.openev_id == file.openev_id)
        name = openev_inbox_name(file)
        return _deliver(body, inbox / name, f"openev-{file.openev_id}")


def _deliver(body: bytes, destination: Path, source_name: str) -> DownloadedFile:
    """Put `body` at `destination` the way the real client does: never replacing a different file."""
    digest = hashlib.sha256(body).hexdigest()
    destination.parent.mkdir(parents=True, exist_ok=True)
    already_present = destination.is_file() and hashlib.sha256(destination.read_bytes()).hexdigest() == digest
    if not already_present:
        destination.write_bytes(body)
    return DownloadedFile(
        path=destination,
        sha256=digest,
        byte_size=len(body),
        source_name=source_name,
        already_present=already_present,
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


class RecordingParseStage:
    """A parse pipeline that is there, so the skip path is not the only one exercised."""

    def __init__(self, result: ParseStageResult | None = None, failure: Exception | None = None) -> None:
        self.result = result or ParseStageResult(files_parsed=3, cards_parsed=17, failures=1)
        self.failure = failure
        self.calls: list[tuple[str, ...]] = []

    async def parse_new_sources(self, *, caselists: object) -> ParseStageResult:
        self.calls.append(tuple(caselists))  # type: ignore[arg-type]
        if self.failure is not None:
            raise self.failure
        return self.result


class RecordingLandscapeStage:
    def __init__(self, reports_written: int = 2) -> None:
        self.reports_written = reports_written
        self.calls = 0

    async def regenerate(self, *, caselists: object) -> LandscapeStageResult:
        self.calls += 1
        return LandscapeStageResult(reports_written=self.reports_written)


# ------------------------------------------------------------------------------------------------
# The installation under test
# ------------------------------------------------------------------------------------------------


@pytest.fixture
def archives(tmp_path: Path) -> dict[date, Path]:
    return build_snapshot_zips(tmp_path / "published")


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "evidence"


@pytest.fixture
def inbox(tmp_path: Path) -> Path:
    return tmp_path / "evidence" / "inbox"


def local_evidence(data_dir: Path) -> LocalEvidence:
    objects = FsEvidenceObjectStore(data_dir)
    blobs = FsEvidenceObjectStore(data_dir, subdirectory=Path("blobs"))
    return LocalEvidence(
        objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
    )


async def import_first_week(data_dir: Path, archives: dict[date, Path]) -> None:
    """Import `2026-09-01` the way an earlier run would have, so the run under test has a baseline."""
    database = SqliteDatabase.open(data_dir)
    service = CaselistImportService(
        suppression=empty_suppression_list(),
        caselists=SqliteCaselistRepository(database),
        blobs=FsSnapshotStore(data_dir),
    )
    first = SNAPSHOTS[0].snapshot
    report = await service.import_archive(
        read_archive(archives[first], **_LIMITS),
        caselist=SYNTHETIC_CASELIST,
        snapshot=first,
        event=Event.LD,
        archive_sha256="f" * 64,
    )
    write_manifest(report, FsEvidenceObjectStore(data_dir).path_for(manifest_key(SYNTHETIC_CASELIST, first)))


@pytest.fixture
def source(archives: dict[date, Path]) -> FakeCaselistSource:
    """The five listed archives of the scenario table, and one new OpenEv camp file."""
    fake = FakeCaselistSource()
    listed: list[tuple[ArchiveListing, Path | None]] = []
    for snapshot in SNAPSHOTS:
        listed.append(
            (
                ArchiveListing(
                    caselist=SYNTHETIC_CASELIST,
                    name=weekly_name(snapshot.snapshot),
                    kind=ArchiveKind.WEEKLY,
                    archive_date=snapshot.snapshot,
                    url=f"https://files.example.invalid/{weekly_name(snapshot.snapshot)}",
                ),
                archives[snapshot.snapshot],
            )
        )
    newest = SNAPSHOTS[-1].snapshot
    listed.append(
        (
            ArchiveListing(
                caselist=SYNTHETIC_CASELIST,
                name=full_name(newest),
                kind=ArchiveKind.FULL,
                archive_date=newest,
                url=f"https://files.example.invalid/{full_name(newest)}",
            ),
            archives[newest],
        )
    )
    listed.append(
        (
            ArchiveListing(
                caselist=SYNTHETIC_CASELIST,
                name=f"{SYNTHETIC_CASELIST}-archive-notes.txt",
                kind=ArchiveKind.UNRECOGNISED,
                archive_date=None,
                url="https://files.example.invalid/notes.txt",
            ),
            None,
        )
    )
    fake.archives[SYNTHETIC_CASELIST] = listed
    fake.openev_files = [
        (
            OpenEvFile(
                openev_id=OPENEV_FILE_ID,
                path=f"openev/{OPENEV_YEAR}/Tamarack/TSF-Estuary Solvency Advocate.docx",
                filename="TSF-Estuary Solvency Advocate.docx",
                year=OPENEV_YEAR,
                tags=("policy",),
            ),
            DOCUMENT_BODIES["estuary-solvency"],
        )
    ]
    return fake


def build_service(
    *,
    source: FakeCaselistSource,
    data_dir: Path,
    inbox: Path,
    publisher: CaselistPublishService | None = None,
    status: CaselistStatusService | None = None,
    parse: object | None = None,
    landscape: object | None = None,
    bulk_downloads_per_day: int = DEFAULT_BULK_DOWNLOADS_PER_DAY,
    clock: Callable[[], datetime] = lambda: RUN_CLOCK,
    reader: Callable[[Path], Iterable[ArchiveEntry]] | None = None,
    openev_importer: Callable[[SqliteCaselistRepository, FsSnapshotStore], OpenEvImportService] | None = None,
) -> CaselistSyncService:
    database = SqliteDatabase.open(data_dir)
    repository = SqliteCaselistRepository(database)
    blobs = FsSnapshotStore(data_dir)
    return CaselistSyncService(
        source=source,
        archive_importer=CaselistImportService(
            suppression=empty_suppression_list(), caselists=repository, blobs=blobs
        ),
        openev_importer=(openev_importer or _openev_importer)(repository, blobs),
        local=local_evidence(data_dir),
        read_archive=reader or (lambda path: read_archive(path, **_LIMITS)),
        event_for_caselist=lambda slug: Event.LD if slug.startswith("testcl") else None,
        inbox=inbox,
        state_dir=data_dir,
        suppression=empty_suppression_list(),
        publisher=publisher,
        status=status,
        parse=parse,  # type: ignore[arg-type]
        landscape=landscape,  # type: ignore[arg-type]
        bulk_downloads_per_day=bulk_downloads_per_day,
        clock=clock,
    )


def _openev_importer(repository: SqliteCaselistRepository, blobs: FsSnapshotStore) -> OpenEvImportService:
    return OpenEvImportService(suppression=empty_suppression_list(), caselists=repository, blobs=blobs)


@pytest.fixture
def bucket(evidence_bucket: str, s3_client: S3Client) -> S3EvidenceObjectStore:
    return S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client)


def decisions(summary_archives: tuple[ArchiveSelection, ...]) -> dict[str, str]:
    return {one.name: str(one.decision) for one in summary_archives}


# ------------------------------------------------------------------------------------------------
# A whole weekly run (goal criterion ac1)
# ------------------------------------------------------------------------------------------------


async def test_a_run_downloads_the_new_weeklies_oldest_first_and_imports_them(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """The two new weeklies and the one OpenEv file, fetched oldest-first, imported, counted.

    The counts are read off `tests/fixtures/caselist/expected_summary.json`, which a person wrote
    from the fixture's own tables:

    * stored members — the classifications that put bytes in the store — are NEW + UNCHANGED +
      CHANGED + DUPLICATE: 7 + 3 + 1 + 2 = 13 for 09-08, and 2 + 12 + 0 + 0 = 14 for 09-15. With
      the one OpenEv file that is 28.
    * duplicates are the DUPLICATE column alone: 2 + 0 = 2, and the camp file is not one.
    * newly stored blobs are the growth of the store's distinct digests: 12 − 4 = 8 for 09-08 and
      14 − 12 = 2 for 09-15, plus the camp file's own bytes, which no archive holds: 11.
    * skips are the `zip` row: 3 for 09-08 and 5 for 09-15. A single camp file skips nothing: 8.
    """
    await import_first_week(data_dir, archives)
    service = build_service(source=source, data_dir=data_dir, inbox=inbox)

    summary = await service.run([SYNTHETIC_CASELIST])

    assert source.archive_fetches == [weekly_name(date(2026, 9, 8)), weekly_name(date(2026, 9, 15))]
    assert source.openev_fetches == [OPENEV_FILE_ID]
    assert summary.archives_downloaded == 2
    assert summary.openev_downloaded == 1
    assert summary.files_imported == 28
    assert summary.files_duplicate == 2
    assert summary.blobs_stored == 11
    assert summary.files_skipped == 8
    assert summary.snapshots_imported == (
        f"{SYNTHETIC_CASELIST} 2026-09-08",
        f"{SYNTHETIC_CASELIST} 2026-09-15",
        "openev 2026-policy",
    )
    assert summary.succeeded


async def test_the_manifests_the_run_writes_are_where_publish_and_status_look(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    await import_first_week(data_dir, archives)
    service = build_service(source=source, data_dir=data_dir, inbox=inbox)

    await service.run([SYNTHETIC_CASELIST])

    objects = FsEvidenceObjectStore(data_dir)
    for snapshot in (date(2026, 9, 8), date(2026, 9, 15)):
        assert objects.path_for(manifest_key(SYNTHETIC_CASELIST, snapshot)).is_file()
    assert objects.path_for("manifests/openev/2026-policy.jsonl").is_file()


async def test_an_immediate_re_run_downloads_nothing_and_reports_nothing_new(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """ac1's second half. The second run is idempotent because the manifests now say so."""
    await import_first_week(data_dir, archives)
    service = build_service(source=source, data_dir=data_dir, inbox=inbox)
    await service.run([SYNTHETIC_CASELIST])
    fetched_first_time = list(source.archive_fetches)

    again = await service.run([SYNTHETIC_CASELIST])

    assert source.archive_fetches == fetched_first_time, "the second run fetched an archive again"
    assert source.openev_fetches == [OPENEV_FILE_ID], "the camp file was fetched again"
    assert again.archives_downloaded == 0
    assert again.openev_downloaded == 0
    assert again.nothing_new
    assert again.succeeded
    assert again.stage(SyncStage.DOWNLOAD) is not None
    assert again.stage(SyncStage.DOWNLOAD).outcome is StageOutcome.SKIPPED  # type: ignore[union-attr]


# ------------------------------------------------------------------------------------------------
# What is listed and never fetched
# ------------------------------------------------------------------------------------------------


async def test_the_full_archive_and_an_undated_name_are_listed_and_never_downloaded(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """Every row of the scenario table, decided.

    The full archive is not a weekly run's business, and an UNRECOGNISED name has no date to file
    a snapshot under. Both are counted and named so a change upstream is a number somebody sees.
    """
    await import_first_week(data_dir, archives)
    service = build_service(source=source, data_dir=data_dir, inbox=inbox)

    summary = await service.run([SYNTHETIC_CASELIST])

    assert decisions(summary.archives) == {
        weekly_name(date(2026, 9, 1)): str(SelectionDecision.ALREADY_IMPORTED),
        weekly_name(date(2026, 9, 8)): str(SelectionDecision.DOWNLOAD),
        weekly_name(date(2026, 9, 15)): str(SelectionDecision.DOWNLOAD),
        full_name(date(2026, 9, 15)): str(SelectionDecision.FULL_ARCHIVE_NOT_PULLED_WEEKLY),
        f"{SYNTHETIC_CASELIST}-archive-notes.txt": str(SelectionDecision.UNRECOGNISED_NAME),
    }
    assert full_name(date(2026, 9, 15)) not in source.archive_fetches


async def test_an_archive_already_in_the_inbox_is_not_fetched_again(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """The `v1-e34-t01` review item: `already_present` is reported *after* the bytes are spent."""
    await import_first_week(data_dir, archives)
    inbox.mkdir(parents=True, exist_ok=True)
    name = weekly_name(date(2026, 9, 8))
    (inbox / name).write_bytes(archives[date(2026, 9, 8)].read_bytes())
    service = build_service(source=source, data_dir=data_dir, inbox=inbox)

    summary = await service.run([SYNTHETIC_CASELIST])

    assert name not in source.archive_fetches
    assert decisions(summary.archives)[name] == str(SelectionDecision.ALREADY_IN_INBOX)
    assert source.archive_fetches == [weekly_name(date(2026, 9, 15))]


async def test_a_partial_download_in_the_inbox_is_not_mistaken_for_an_archive(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """`<inbox>/.partial/` holds downloads in progress and is skipped when the inbox is read."""
    await import_first_week(data_dir, archives)
    name = weekly_name(date(2026, 9, 8))
    partial = inbox / ".partial"
    partial.mkdir(parents=True, exist_ok=True)
    (partial / f"{name}.deadbeef.part").write_bytes(b"half an archive")
    service = build_service(source=source, data_dir=data_dir, inbox=inbox)

    summary = await service.run([SYNTHETIC_CASELIST])

    assert name in source.archive_fetches, "a half-written file must not stand in for the archive"
    assert decisions(summary.archives)[name] == str(SelectionDecision.DOWNLOAD)


async def test_an_openev_file_already_in_the_release_manifest_is_not_fetched_again(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """A cleared inbox must not mean a re-fetch: the release manifest is the second check."""
    await import_first_week(data_dir, archives)
    service = build_service(source=source, data_dir=data_dir, inbox=inbox)
    await service.run([SYNTHETIC_CASELIST])
    fetched_name = openev_inbox_name(source.openev_files[0][0])
    (inbox / fetched_name).unlink()

    again = await service.run([SYNTHETIC_CASELIST])

    assert source.openev_fetches == [OPENEV_FILE_ID]
    assert [one.decision for one in again.openev] == [SelectionDecision.ALREADY_IMPORTED]


# ------------------------------------------------------------------------------------------------
# A failed import is retried by the next run (v1-e34-t06 ac1)
# ------------------------------------------------------------------------------------------------


class ReaderThatFailsOnce:
    """The archive reader, except that the first read of each named archive is refused.

    What a failed import looks like from the run's side: the archive reached the inbox, and the
    importer could not read it. `UnreadableArchive` is what a truncated zip raises. The second read
    of the same file succeeds, as it would once the operator had fixed whatever was wrong.
    """

    def __init__(self, *names: str) -> None:
        self.failing = set(names)

    def __call__(self, path: Path) -> Iterable[ArchiveEntry]:
        if path.name in self.failing:
            self.failing.discard(path.name)
            raise UnreadableArchive(path.name, "not a readable zip file")
        return read_archive(path, **_LIMITS)


def manifest_held(data_dir: Path, snapshot: date) -> bool:
    return FsEvidenceObjectStore(data_dir).path_for(manifest_key(SYNTHETIC_CASELIST, snapshot)).is_file()


async def test_retry_an_archive_whose_import_failed_is_imported_by_the_next_run_without_a_download(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """The defect as the spec states it: the newest weekly downloads and its import fails.

    Before v1-e34-t06 the next run decided `already_in_inbox` for it, and its import stage imported
    only what that run had downloaded, which was nothing. The archive sat in the inbox unimported
    for good, and re-running the command changed nothing.
    """
    await import_first_week(data_dir, archives)
    reader = ReaderThatFailsOnce(weekly_name(date(2026, 9, 15)))
    service = build_service(source=source, data_dir=data_dir, inbox=inbox, reader=reader)
    failed = await service.run([SYNTHETIC_CASELIST])
    assert failed.stage(SyncStage.IMPORT).outcome is StageOutcome.FAILED  # type: ignore[union-attr]
    assert not failed.succeeded
    assert not manifest_held(data_dir, date(2026, 9, 15))
    fetched = [weekly_name(date(2026, 9, 8)), weekly_name(date(2026, 9, 15))]
    assert source.archive_fetches == fetched

    retried = await service.run([SYNTHETIC_CASELIST])

    assert source.archive_fetches == fetched, "the retry spent a download on an archive it already had"
    assert decisions(retried.archives)[weekly_name(date(2026, 9, 15))] == str(
        SelectionDecision.ALREADY_IN_INBOX
    )
    assert retried.snapshots_imported == (f"{SYNTHETIC_CASELIST} 2026-09-15",)
    assert retried.stage(SyncStage.IMPORT).outcome is StageOutcome.COMPLETED  # type: ignore[union-attr]
    assert retried.succeeded
    assert manifest_held(data_dir, date(2026, 9, 15))
    # 09-15's own row of the first test's arithmetic: 2 + 12 + 0 + 0 = 14 stored members, and
    # 14 - 12 = 2 blobs the store did not already hold.
    assert (retried.files_imported, retried.blobs_stored) == (14, 2)


async def test_retry_a_failed_import_holds_back_the_newer_weeks_of_that_caselist(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """The same gap by a second road: the older week fails and the newer one imports past it.

    A caselist's weeklies are imported oldest first because each is classified against the one
    before it. Before v1-e34-t06 a failed 09-08 did not stop 09-15, whose manifest then made 09-08
    `already_imported` on every later run: never fetched and never imported again. A failure now
    holds that caselist's newer weeks in the inbox, and the next run imports them in order.
    """
    await import_first_week(data_dir, archives)
    reader = ReaderThatFailsOnce(weekly_name(date(2026, 9, 8)))
    service = build_service(source=source, data_dir=data_dir, inbox=inbox, reader=reader)

    failed = await service.run([SYNTHETIC_CASELIST])

    assert not manifest_held(data_dir, date(2026, 9, 8))
    assert not manifest_held(data_dir, date(2026, 9, 15)), "a newer week was imported past a failed one"
    assert failed.snapshots_imported == ("openev 2026-policy",)
    reason = failed.stage(SyncStage.IMPORT).reason or ""  # type: ignore[union-attr]
    assert "1 archive(s) in the inbox held back for a later run" in reason

    retried = await service.run([SYNTHETIC_CASELIST])

    assert source.archive_fetches == [weekly_name(date(2026, 9, 8)), weekly_name(date(2026, 9, 15))]
    assert retried.snapshots_imported == (
        f"{SYNTHETIC_CASELIST} 2026-09-08",
        f"{SYNTHETIC_CASELIST} 2026-09-15",
    )
    assert retried.succeeded


async def test_retry_an_inbox_archive_waits_behind_an_older_week_the_cap_deferred(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """An archive already in the inbox is imported only once every older wanted week is in.

    09-15 is in the inbox; 09-08 is not, and the cap leaves no download for it today. Importing
    09-15 now would make 09-08 `already_imported` for good, so 09-15 waits in the inbox too.
    """
    await import_first_week(data_dir, archives)
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / weekly_name(date(2026, 9, 15))).write_bytes(archives[date(2026, 9, 15)].read_bytes())
    service = build_service(source=source, data_dir=data_dir, inbox=inbox, bulk_downloads_per_day=0)

    summary = await service.run([SYNTHETIC_CASELIST])

    assert source.archive_fetches == []
    assert decisions(summary.archives)[weekly_name(date(2026, 9, 8))] == str(
        SelectionDecision.OVER_DAILY_BUDGET
    )
    assert not manifest_held(data_dir, date(2026, 9, 15))
    assert f"{SYNTHETIC_CASELIST} 2026-09-15" not in summary.snapshots_imported


class OpenEvImporterThatFailsOnce(OpenEvImportService):
    """The OpenEv importer, refusing its first release import the way an unreadable file would."""

    failed = False

    async def import_release(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def, override]
        if not OpenEvImporterThatFailsOnce.failed:
            OpenEvImporterThatFailsOnce.failed = True
            raise UnreadableArchive("openev-512", "not a readable document")
        return await super().import_release(*args, **kwargs)  # type: ignore[arg-type]


async def test_retry_a_camp_file_whose_import_failed_is_imported_from_the_inbox(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """The OpenEv half of the same defect: the camp file sat in the inbox, `already_in_inbox`."""
    await import_first_week(data_dir, archives)
    OpenEvImporterThatFailsOnce.failed = False
    service = build_service(
        source=source,
        data_dir=data_dir,
        inbox=inbox,
        openev_importer=lambda repository, blobs: OpenEvImporterThatFailsOnce(
            suppression=empty_suppression_list(), caselists=repository, blobs=blobs
        ),
    )
    failed = await service.run([SYNTHETIC_CASELIST])
    assert "openev 2026-policy" not in failed.snapshots_imported

    retried = await service.run([SYNTHETIC_CASELIST])

    assert source.openev_fetches == [OPENEV_FILE_ID], "the retry fetched the camp file again"
    assert [one.decision for one in retried.openev] == [SelectionDecision.ALREADY_IN_INBOX]
    assert retried.snapshots_imported == ("openev 2026-policy",)
    assert FsEvidenceObjectStore(data_dir).path_for("manifests/openev/2026-policy.jsonl").is_file()

    third = await service.run([SYNTHETIC_CASELIST])

    assert [one.decision for one in third.openev] == [SelectionDecision.ALREADY_IMPORTED]
    assert third.nothing_new, "an imported camp file left in the inbox was imported again"


# ------------------------------------------------------------------------------------------------
# OpenEv selection sees camp files imported by hand (v1-e34-t06 ac3)
# ------------------------------------------------------------------------------------------------
#
# The sync names a camp file it downloads `openev-<id>-<file name>`, and used to decide "already
# imported" by looking for that name in the release manifest. A camp file imported by hand through
# `caselist import-openev` is recorded under its own path — `Tamarack/TSF-Estuary Solvency
# Advocate.docx` — which that check could never see. The listing's own path is what the two share.

OPENEV_MANIFEST = openev_manifest_key(OPENEV_YEAR, Event.POLICY)


async def import_openev_by_hand(data_dir: Path, download: Path) -> None:
    """What `caselist import-openev <download> --year 2026 --event policy` does to the store."""
    database = SqliteDatabase.open(data_dir)
    service = OpenEvImportService(
        suppression=empty_suppression_list(),
        caselists=SqliteCaselistRepository(database),
        blobs=FsSnapshotStore(data_dir),
    )
    manifest = FsEvidenceObjectStore(data_dir).path_for(OPENEV_MANIFEST)
    report = await service.import_release(
        read_archive(download, **_LIMITS),
        year=OPENEV_YEAR,
        event=Event.POLICY,
        imported_on=date(2026, 9, 10),
        archive_sha256=archive_digest(download),
        recorded_manifest=read_manifest_lines(manifest),
    )
    write_manifest_lines(report.manifest_lines, manifest)


def manifest_paths(data_dir: Path) -> list[str]:
    rows = [
        json.loads(line)
        for line in read_manifest_lines(FsEvidenceObjectStore(data_dir).path_for(OPENEV_MANIFEST))
    ]
    return [row["path"] for row in rows if row.get("kind") == "member"]


def camp_file(openev_id: int, path: str) -> OpenEvFile:
    return OpenEvFile(
        openev_id=openev_id, path=path, filename=path.rsplit("/", 1)[-1], year=OPENEV_YEAR, tags=("policy",)
    )


async def test_openev_a_camp_file_imported_by_hand_is_already_imported_and_costs_no_download(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path], tmp_path: Path
) -> None:
    """The addendum download holds `Tamarack/TSF-Estuary Solvency Advocate.docx`: OpenEv file 512.

    Before v1-e34-t06 the sync fetched it again and recorded it a second time, as a DUPLICATE row
    under `openev-512-TSF-Estuary_Solvency_Advocate.docx`, beside the row it already had.
    """
    await import_first_week(data_dir, archives)
    await import_openev_by_hand(
        data_dir, build_download_zips(tmp_path / "camp")["openev-2026-policy-addendum"]
    )
    held = manifest_paths(data_dir)
    assert "Tamarack/TSF-Estuary Solvency Advocate.docx" in held
    service = build_service(source=source, data_dir=data_dir, inbox=inbox)

    summary = await service.run([SYNTHETIC_CASELIST])

    assert source.openev_fetches == [], "a camp file already held was downloaded again"
    assert [one.decision for one in summary.openev] == [SelectionDecision.ALREADY_IMPORTED]
    assert manifest_paths(data_dir) == held, "the release manifest gained a second row for the same file"


@pytest.mark.parametrize(
    "listed_path",
    [
        f"openev/{OPENEV_YEAR}/Tamarack/TSF-Estuary Solvency Advocate.docx",
        f"openev/{OPENEV_YEAR}/tamarack/TSF-Estuary_Solvency_Advocate.docx",
        f"{OPENEV_YEAR}/Tamarack/TSF  Estuary Solvency Advocate.DOCX",
    ],
    ids=["as-listed", "case-and-underscores", "spacing-and-extension-case"],
)
async def test_openev_a_hand_imported_file_is_matched_through_spelling_differences(
    listed_path: str, source: FakeCaselistSource, data_dir: Path, inbox: Path, tmp_path: Path
) -> None:
    await import_openev_by_hand(
        data_dir, build_download_zips(tmp_path / "camp")["openev-2026-policy-addendum"]
    )
    source.archives = {}
    source.openev_files = [(camp_file(OPENEV_FILE_ID, listed_path), DOCUMENT_BODIES["estuary-solvency"])]
    service = build_service(source=source, data_dir=data_dir, inbox=inbox)

    plan = await service.plan([SYNTHETIC_CASELIST])

    assert [one.decision for one in plan.openev] == [SelectionDecision.ALREADY_IMPORTED]


async def test_openev_the_folder_decides_between_two_listed_files_of_one_name(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, tmp_path: Path
) -> None:
    """`Tamarack/TSF-Borrowed Grove Aff.docx` is held; another camp's file of that name is not."""
    await import_openev_by_hand(data_dir, build_download_zips(tmp_path / "camp")["openev-2026-policy"])
    source.archives = {}
    source.openev_files = [
        (camp_file(601, f"openev/{OPENEV_YEAR}/Tamarack/TSF-Borrowed Grove Aff.docx"), b"held"),
        (camp_file(602, f"openev/{OPENEV_YEAR}/Brightwater/TSF-Borrowed Grove Aff.docx"), b"not held"),
    ]
    service = build_service(source=source, data_dir=data_dir, inbox=inbox)

    plan = await service.plan([SYNTHETIC_CASELIST])

    assert {one.openev_id: one.decision for one in plan.openev} == {
        601: SelectionDecision.ALREADY_IMPORTED,
        602: SelectionDecision.DOWNLOAD,
    }


async def test_openev_a_bare_name_that_two_listed_files_share_holds_neither(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, tmp_path: Path
) -> None:
    """`Brightwater Workshop - Orchard Kritik.docx` was imported with no folder to tell them apart.

    Calling either one held would be a guess, and a wrong guess never downloads a camp file the
    store does not have. Both are fetched; the one already held costs a download and a DUPLICATE row.
    """
    await import_openev_by_hand(data_dir, build_download_zips(tmp_path / "camp")["openev-2026-policy"])
    source.archives = {}
    source.openev_files = [
        (
            camp_file(701, f"openev/{OPENEV_YEAR}/Brightwater/Brightwater Workshop - Orchard Kritik.docx"),
            b"a",
        ),
        (
            camp_file(702, f"openev/{OPENEV_YEAR}/Quillfeather/Brightwater Workshop - Orchard Kritik.docx"),
            b"b",
        ),
    ]
    service = build_service(source=source, data_dir=data_dir, inbox=inbox)

    plan = await service.plan([SYNTHETIC_CASELIST])

    assert [one.decision for one in plan.openev] == [SelectionDecision.DOWNLOAD, SelectionDecision.DOWNLOAD]


async def test_openev_a_file_the_sync_named_is_matched_by_its_id(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, tmp_path: Path
) -> None:
    """The first download holds `openev-417-TSF-Spillway Advantage.docx`, a name the sync writes."""
    await import_openev_by_hand(data_dir, build_download_zips(tmp_path / "camp")["openev-2026-policy"])
    source.archives = {}
    source.openev_files = [
        (camp_file(417, f"openev/{OPENEV_YEAR}/Tamarack/TSF-Spillway Advantage (final).docx"), b"renamed"),
        (camp_file(418, f"openev/{OPENEV_YEAR}/Tamarack/TSF-Spillway Advantage.docx"), b"another id"),
    ]
    service = build_service(source=source, data_dir=data_dir, inbox=inbox)

    plan = await service.plan([SYNTHETIC_CASELIST])

    assert {one.openev_id: one.decision for one in plan.openev} == {
        417: SelectionDecision.ALREADY_IMPORTED,
        418: SelectionDecision.DOWNLOAD,
    }


async def test_openev_macos_junk_that_reads_like_a_camp_file_does_not_hold_it(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, tmp_path: Path
) -> None:
    """`__MACOSX/Tamarack/._TSF-Canal Subsidies Counterplan.docx` is skipped, and is no camp file."""
    download = tmp_path / "junk-and-one-file"
    (download / "__MACOSX" / "Tamarack").mkdir(parents=True)
    (download / "__MACOSX" / "Tamarack" / "._TSF-Canal Subsidies Counterplan.docx").write_bytes(
        b"\x00\x05\x16\x07"
    )
    (download / "Tamarack").mkdir()
    (download / "Tamarack" / "TSF-Estuary Solvency Advocate.docx").write_bytes(
        DOCUMENT_BODIES["estuary-solvency"]
    )
    await import_openev_by_hand(data_dir, download)
    assert "__MACOSX/Tamarack/._TSF-Canal Subsidies Counterplan.docx" in manifest_paths(data_dir)
    source.archives = {}
    source.openev_files = [
        (camp_file(801, f"openev/{OPENEV_YEAR}/Tamarack/TSF-Canal Subsidies Counterplan.docx"), b"canal"),
        (camp_file(802, f"openev/{OPENEV_YEAR}/Tamarack/TSF-Estuary Solvency Advocate.docx"), b"estuary"),
    ]
    service = build_service(source=source, data_dir=data_dir, inbox=inbox)

    plan = await service.plan([SYNTHETIC_CASELIST])

    assert {one.openev_id: one.decision for one in plan.openev} == {
        801: SelectionDecision.DOWNLOAD,
        802: SelectionDecision.ALREADY_IMPORTED,
    }


async def test_openev_a_sync_named_file_whose_id_is_no_longer_listed_marks_a_revision_at_its_path(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, tmp_path: Path
) -> None:
    """`openev-417-TSF-Spillway Advantage.docx` with 417 gone from the listing: 999 is its revision.

    `v1-e34-t06` held 999 here, as the same file. OpenEv changes a file only by deleting it and
    uploading it again (`v1-e34-t07`'s reading of upstream), so a row naming an id that is no longer
    listed is an old version, and the new id at its path is fetched (`v1-e34-t08`). A row that names
    no id, a hand import, still holds the file at its path: see the tests above.
    """
    await import_openev_by_hand(data_dir, build_download_zips(tmp_path / "camp")["openev-2026-policy"])
    source.archives = {}
    source.openev_files = [
        (camp_file(999, f"openev/{OPENEV_YEAR}/Tamarack/TSF-Spillway Advantage.docx"), b"x")
    ]
    service = build_service(source=source, data_dir=data_dir, inbox=inbox)

    plan = await service.plan([SYNTHETIC_CASELIST])

    assert [one.decision for one in plan.openev] == [SelectionDecision.DOWNLOAD]
    assert [one.revision_of for one in plan.openev] == [417]


_SMALL_NAMES = st.sampled_from(
    ["Tamarack", "tamarack", "Brightwater", "Juniors Lab", "Aff.docx", "aff_docx", "Neg.pdf"]
)


@st.composite
def listings_and_imports(draw: st.DrawFn) -> tuple[list[OpenEvFile], set[int], list[str]]:
    """Listed camp files over a small alphabet, so names collide, and what was imported of them.

    Each imported file is recorded the way a hand import would record it: some tail of its listed
    path, from the file name up, as the download it came in happened to be laid out.
    """
    count = draw(st.integers(min_value=1, max_value=8))
    listed = [
        camp_file(
            100 + index,
            "/".join(["openev", str(OPENEV_YEAR), *draw(st.lists(_SMALL_NAMES, min_size=1, max_size=3))]),
        )
        for index in range(count)
    ]
    imported = draw(st.sets(st.sampled_from([file.openev_id for file in listed])))
    recorded: list[str] = []
    for file in listed:
        if file.openev_id in imported:
            parts = file.path.split("/")
            recorded.append("/".join(parts[-draw(st.integers(min_value=1, max_value=len(parts) - 2)) :]))
    return listed, imported, recorded


@settings(max_examples=300, deadline=None)
@given(listings_and_imports())
def test_openev_matching_never_holds_a_listed_file_nobody_imported(
    case: tuple[list[OpenEvFile], set[int], list[str]],
) -> None:
    """A held camp file is never downloaded again, so holding one nobody imported loses it for good.

    Every recorded path is a tail of an imported file's listed path, so the imported file shares
    that whole tail. Another listed file can at most tie with it, and a tie holds neither.
    """
    listed, imported, recorded = case

    held = _held_openev_ids(listed, recorded)

    assert held <= imported, f"held {sorted(held - imported)} that nobody imported"


# ------------------------------------------------------------------------------------------------
# The daily bulk-download budget
# ------------------------------------------------------------------------------------------------


def test_the_daily_budget_is_shared_round_robin_across_the_caselists() -> None:
    """Five downloads, three caselists with three weeklies each: 2, 2, 1, oldest first in each.

    Written out by hand: the allocation takes one from each caselist in turn until the five are
    gone, so `hsld26` and `hspolicy26` get their two oldest and `hspf26` gets its oldest. What is
    deferred is always the newest of a caselist, which is the one certain to be listed next week.
    """
    selections = [
        ArchiveSelection(
            caselist=caselist,
            name=f"{caselist}-weekly-{day.isoformat()}.zip",
            kind=ArchiveKind.WEEKLY,
            archive_date=day,
            decision=SelectionDecision.DOWNLOAD,
        )
        for caselist in ("hsld26", "hspolicy26", "hspf26")
        for day in (date(2026, 9, 1), date(2026, 9, 8), date(2026, 9, 15))
    ]

    budgeted = within_daily_budget(selections, allowed=5)

    granted = {one.name for one in budgeted if one.wanted}
    assert granted == {
        "hsld26-weekly-2026-09-01.zip",
        "hsld26-weekly-2026-09-08.zip",
        "hspolicy26-weekly-2026-09-01.zip",
        "hspolicy26-weekly-2026-09-08.zip",
        "hspf26-weekly-2026-09-01.zip",
    }
    assert {one.decision for one in budgeted if not one.wanted} == {SelectionDecision.OVER_DAILY_BUDGET}


async def test_a_run_never_plans_more_downloads_than_the_day_has_left(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    await import_first_week(data_dir, archives)
    service = build_service(source=source, data_dir=data_dir, inbox=inbox, bulk_downloads_per_day=1)

    summary = await service.run([SYNTHETIC_CASELIST])

    assert source.archive_fetches == [weekly_name(date(2026, 9, 8))]
    assert decisions(summary.archives)[weekly_name(date(2026, 9, 15))] == str(
        SelectionDecision.OVER_DAILY_BUDGET
    )


async def test_window_what_a_run_spent_is_carried_into_the_next_run_for_24_hours(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """The five are a rolling day's allowance, not a run's. A second run starts from what is left."""
    await import_first_week(data_dir, archives)
    service = build_service(source=source, data_dir=data_dir, inbox=inbox, bulk_downloads_per_day=2)

    await service.run([SYNTHETIC_CASELIST])
    ledger = DownloadLedger(data_dir / DOWNLOAD_LEDGER_FILENAME, limit=2)

    assert ledger.starts() == (RUN_CLOCK, RUN_CLOCK)
    assert ledger.remaining_at(RUN_CLOCK) == 0
    assert ledger.remaining_at(RUN_CLOCK + timedelta(hours=23, minutes=59)) == 0, (
        "a new date is not a new five"
    )
    assert ledger.remaining_at(RUN_CLOCK + timedelta(hours=24, minutes=1)) == 2


# ------------------------------------------------------------------------------------------------
# The download budget is a rolling 24 hours (v1-e34-t06 ac2, ac2b)
# ------------------------------------------------------------------------------------------------
#
# Every time here is pinned. None comes from the machine's clock or its timezone: a test of a
# window that read either would pass at 14:00 and fail at 21:43, which is what the calendar-day
# ledger's tests did.

OPERATOR_EVENING = datetime(2026, 9, 29, 4, 45, 11, tzinfo=UTC)
"""23:45:11 CDT on 2026-09-28: when the operator's calendar ledger was last written."""

A_ROLLING_DAY = timedelta(hours=24)
"""Written here rather than imported: a test that took the window from the module under test
would agree with whatever window the module had."""

OPERATOR_LEGACY_LEDGER = b'{\n  "bulk_downloads": 5,\n  "date": "2026-09-29"\n}\n'
"""The operator's old-format ledger, byte for byte as the calendar-day build wrote it."""


def spend_allowance(data_dir: Path, downloads: int, *, at: datetime) -> None:
    """Record `downloads` bulk downloads started at `at`, as an earlier run would have."""
    ledger = DownloadLedger(data_dir / DOWNLOAD_LEDGER_FILENAME)
    for _ in range(downloads):
        ledger.record(at)


def written_at(path: Path, moment: datetime) -> None:
    """Give `path` the modification time `moment`, which is what an old-format ledger is read by."""
    os.utime(path, (moment.timestamp(), moment.timestamp()))


def test_window_five_downloads_at_t_are_still_counted_at_23h59m_and_released_at_24h01m(
    tmp_path: Path,
) -> None:
    ledger = DownloadLedger(tmp_path / DOWNLOAD_LEDGER_FILENAME)
    for _ in range(5):
        ledger.record(OPERATOR_EVENING)

    assert ledger.spent_in_window(OPERATOR_EVENING + timedelta(hours=23, minutes=59)) == 5
    assert ledger.remaining_at(OPERATOR_EVENING + timedelta(hours=23, minutes=59)) == 0
    # Released at exactly 24 hours, as RequestPacer releases a download at exactly 60 seconds.
    assert ledger.remaining_at(OPERATOR_EVENING + A_ROLLING_DAY) == 5
    assert ledger.remaining_at(OPERATOR_EVENING + timedelta(hours=24, minutes=1)) == 5
    assert ledger.spent_in_window(OPERATOR_EVENING + timedelta(hours=24, minutes=1)) == 0


def test_window_a_start_after_now_still_counts_so_a_clock_set_back_frees_nothing(tmp_path: Path) -> None:
    ledger = DownloadLedger(tmp_path / DOWNLOAD_LEDGER_FILENAME)
    for _ in range(5):
        ledger.record(OPERATOR_EVENING)

    assert ledger.remaining_at(OPERATOR_EVENING - timedelta(hours=2)) == 0


def test_window_the_ledger_keeps_only_what_is_inside_the_window(tmp_path: Path) -> None:
    path = tmp_path / DOWNLOAD_LEDGER_FILENAME
    ledger = DownloadLedger(path)
    ledger.record(OPERATOR_EVENING)
    ledger.record(OPERATOR_EVENING + timedelta(hours=25))

    body = json.loads(path.read_text(encoding="utf-8"))

    assert body == {
        "schema_version": 1,
        "bulk_download_starts": ["2026-09-30T05:45:11+00:00"],
    }


@pytest.mark.parametrize(
    "zone", ["UTC", "America/Chicago", "Pacific/Kiritimati", "Etc/GMT+12", "Asia/Kolkata", "Europe/London"]
)
async def test_window_five_at_t_then_five_forty_minutes_later_are_refused_across_a_midnight(
    zone: str, source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """The doubling the calendar ledger allowed, wherever the midnight is.

    The calendar-day build keyed the ledger on the date of a UTC clock, so five at 23:40 and five
    at 00:20 were two days' allowances. The window has no midnight to cross.
    """
    midnight = datetime(2026, 9, 16, tzinfo=ZoneInfo(zone))
    first = midnight - timedelta(minutes=20)
    second = first + timedelta(minutes=40)
    assert first.date() != second.astimezone(ZoneInfo(zone)).date(), "the two runs must straddle a midnight"
    await import_first_week(data_dir, archives)
    spend_allowance(data_dir, 5, at=first)
    service = build_service(source=source, data_dir=data_dir, inbox=inbox, clock=lambda: second)

    summary = await service.run([SYNTHETIC_CASELIST])

    assert source.archive_fetches == []
    assert {
        decisions(summary.archives)[weekly_name(day)] for day in (date(2026, 9, 8), date(2026, 9, 15))
    } == {str(SelectionDecision.OVER_DAILY_BUDGET)}
    assert summary.bulk_downloads_allowed == 0
    assert summary.bulk_downloads_spent_in_window == 5
    assert summary.bulk_download_window_start == second - timedelta(hours=24)


async def test_window_a_second_run_forty_minutes_later_across_utc_midnight_gets_no_fresh_allowance(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """The doubling itself, through two runs and nothing else.

    With an allowance of one, the 23:50 UTC run fetches 09-08 and defers 09-15. The calendar-day
    ledger keyed on the UTC date, so the 00:30 run found a new date, a fresh allowance, and fetched
    09-15: two downloads in forty minutes against a limit of one.
    """
    await import_first_week(data_dir, archives)
    before_midnight = datetime(2026, 9, 16, 23, 50, tzinfo=UTC)
    after_midnight = before_midnight + timedelta(minutes=40)
    first = build_service(
        source=source, data_dir=data_dir, inbox=inbox, bulk_downloads_per_day=1, clock=lambda: before_midnight
    )
    await first.run([SYNTHETIC_CASELIST])
    assert source.archive_fetches == [weekly_name(date(2026, 9, 8))]
    second = build_service(
        source=source, data_dir=data_dir, inbox=inbox, bulk_downloads_per_day=1, clock=lambda: after_midnight
    )

    summary = await second.run([SYNTHETIC_CASELIST])

    assert source.archive_fetches == [weekly_name(date(2026, 9, 8))], (
        "a new date handed out a fresh allowance"
    )
    assert decisions(summary.archives)[weekly_name(date(2026, 9, 15))] == str(
        SelectionDecision.OVER_DAILY_BUDGET
    )


async def test_window_a_run_records_each_download_at_the_moment_it_started(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """The service writes the window in its own clock's instants, not in dates."""
    await import_first_week(data_dir, archives)
    moments = iter(OPERATOR_EVENING + timedelta(seconds=10 * tick) for tick in range(1000))
    service = build_service(source=source, data_dir=data_dir, inbox=inbox, clock=lambda: next(moments))

    await service.run([SYNTHETIC_CASELIST])

    starts = DownloadLedger(data_dir / DOWNLOAD_LEDGER_FILENAME).starts()
    assert len(starts) == 2
    assert all(OPERATOR_EVENING < one < OPERATOR_EVENING + timedelta(minutes=10) for one in starts)
    assert starts[0] < starts[1]


class SourceWhoseBytesAreAlreadyThere(FakeCaselistSource):
    """Every archive comes back `already_present`, as if the inbox had gained it mid-run."""

    async def download_archive(self, archive: ArchiveListing, inbox: Path) -> DownloadedFile:
        downloaded = await super().download_archive(archive, inbox)
        return downloaded.model_copy(update={"already_present": True})


async def test_window_a_download_whose_bytes_were_already_present_is_still_counted(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """The client streams the whole archive before it can tell; the server has counted it."""
    await import_first_week(data_dir, archives)
    already = SourceWhoseBytesAreAlreadyThere()
    already.archives, already.openev_files = source.archives, source.openev_files
    service = build_service(source=already, data_dir=data_dir, inbox=inbox)

    await service.run([SYNTHETIC_CASELIST])

    assert DownloadLedger(data_dir / DOWNLOAD_LEDGER_FILENAME).spent_in_window(RUN_CLOCK) == 2


async def test_window_the_run_summary_reports_the_window_and_the_spend_inside_it(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    await import_first_week(data_dir, archives)
    spend_allowance(data_dir, 2, at=RUN_CLOCK - timedelta(hours=23))
    service = build_service(source=source, data_dir=data_dir, inbox=inbox)

    summary = await service.run([SYNTHETIC_CASELIST])
    written = json.loads(service.summary_path(summary).read_text(encoding="utf-8"))

    assert written["schema_version"] == RUN_SUMMARY_SCHEMA_VERSION == 2
    assert written["bulk_download_window_start"] == "2026-09-15T06:00:00+00:00"
    assert written["bulk_downloads_spent_in_window"] == 2
    assert written["bulk_downloads_allowed"] == 3
    assert "bulk_downloads_spent_today" not in written
    reason = summary.stage(SyncStage.SELECT).reason or ""  # type: ignore[union-attr]
    assert reason.endswith(
        "3 to fetch; 2 of 5 bulk download(s) spent in the 24 hours from 2026-09-15 06:00 UTC, 3 left"
    )


async def test_window_the_first_run_after_the_upgrade_counts_the_old_calendar_ledger(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """The operator's own ledger, forty minutes after it was written, is five spent — not none.

    A new ledger that read the old file as saying nothing would hand out a free five on the first
    run after the upgrade, on top of the five already spent.
    """
    await import_first_week(data_dir, archives)
    legacy = data_dir / LEGACY_DOWNLOAD_LEDGER_FILENAME
    legacy.write_bytes(OPERATOR_LEGACY_LEDGER)
    written_at(legacy, OPERATOR_EVENING)
    forty_minutes_later = OPERATOR_EVENING + timedelta(minutes=40)
    service = build_service(source=source, data_dir=data_dir, inbox=inbox, clock=lambda: forty_minutes_later)

    refused = await service.run([SYNTHETIC_CASELIST])

    assert source.archive_fetches == []
    assert refused.bulk_downloads_spent_in_window == 5
    assert legacy.read_bytes() == OPERATOR_LEGACY_LEDGER, "the old ledger is read, never rewritten"

    next_evening = OPERATOR_EVENING + timedelta(hours=24, minutes=1)
    later = build_service(source=source, data_dir=data_dir, inbox=inbox, clock=lambda: next_evening)
    allowed = await later.run([SYNTHETIC_CASELIST])

    assert allowed.bulk_downloads_allowed == 5
    assert source.archive_fetches == [weekly_name(date(2026, 9, 8)), weekly_name(date(2026, 9, 15))]


def test_window_an_old_ledger_counts_from_when_it_was_written_not_from_its_date(tmp_path: Path) -> None:
    """Its `date` is a UTC calendar day; its mtime is the latest any of its downloads can be.

    The operator's five were spent at 04:45 UTC on 2026-09-29. Counted from that date's midnight
    they would be released at 00:00 UTC on 09-30, almost five hours early.
    """
    legacy = tmp_path / LEGACY_DOWNLOAD_LEDGER_FILENAME
    legacy.write_bytes(OPERATOR_LEGACY_LEDGER)
    written_at(legacy, OPERATOR_EVENING)
    ledger = DownloadLedger(tmp_path / DOWNLOAD_LEDGER_FILENAME, legacy_path=legacy)

    assert ledger.starts() == (OPERATOR_EVENING,) * 5
    assert ledger.remaining_at(OPERATOR_EVENING + timedelta(hours=23, minutes=59)) == 0
    assert ledger.remaining_at(OPERATOR_EVENING + timedelta(hours=24, minutes=1)) == 5


def test_window_an_old_ledger_with_room_left_leaves_that_room(tmp_path: Path) -> None:
    legacy = tmp_path / LEGACY_DOWNLOAD_LEDGER_FILENAME
    legacy.write_bytes(b'{\n  "bulk_downloads": 2,\n  "date": "2026-09-29"\n}\n')
    written_at(legacy, OPERATOR_EVENING)
    ledger = DownloadLedger(tmp_path / DOWNLOAD_LEDGER_FILENAME, legacy_path=legacy)

    assert ledger.remaining_at(OPERATOR_EVENING + timedelta(minutes=40)) == 3


def test_window_an_old_build_spending_after_this_one_still_counts(tmp_path: Path) -> None:
    """The backfill runs from an installed build on the old format; what it spends is counted."""
    legacy = tmp_path / LEGACY_DOWNLOAD_LEDGER_FILENAME
    ledger = DownloadLedger(tmp_path / DOWNLOAD_LEDGER_FILENAME, legacy_path=legacy)
    ledger.record(OPERATOR_EVENING)
    ledger.record(OPERATOR_EVENING)
    legacy.write_bytes(b'{\n  "bulk_downloads": 3,\n  "date": "2026-09-29"\n}\n')
    written_at(legacy, OPERATOR_EVENING + timedelta(minutes=5))

    assert ledger.spent_in_window(OPERATOR_EVENING + timedelta(minutes=40)) == 5
    assert ledger.remaining_at(OPERATOR_EVENING + timedelta(minutes=40)) == 0


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"not json",
        b"[]",
        b'{"date": "2026-09-29"}',
        b'{"date": "2026-09-29", "bulk_downloads": -1}',
        b'{"date": "2026-09-29", "bulk_downloads": "five"}',
    ],
    ids=["empty", "not-json", "not-an-object", "no-count", "negative-count", "count-not-a-number"],
)
def test_window_an_unreadable_old_ledger_is_counted_as_fully_spent(tmp_path: Path, body: bytes) -> None:
    legacy = tmp_path / LEGACY_DOWNLOAD_LEDGER_FILENAME
    legacy.write_bytes(body)
    written_at(legacy, OPERATOR_EVENING)
    ledger = DownloadLedger(tmp_path / DOWNLOAD_LEDGER_FILENAME, legacy_path=legacy)

    assert ledger.remaining_at(OPERATOR_EVENING + timedelta(hours=23, minutes=59)) == 0
    assert ledger.remaining_at(OPERATOR_EVENING + timedelta(hours=24, minutes=1)) == 5


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        OPERATOR_LEGACY_LEDGER,
        b'{"schema_version": 2, "bulk_download_starts": []}',
        b'{"schema_version": 1, "bulk_download_starts": "2026-09-29T04:45:11+00:00"}',
        b'{"schema_version": 1, "bulk_download_starts": ["yesterday"]}',
        b'{"schema_version": 1, "bulk_download_starts": ["2026-09-29T04:45:11"]}',
    ],
    ids=[
        "not-json",
        "old-format-under-the-new-name",
        "unknown-version",
        "not-a-list",
        "not-a-time",
        "naive-time",
    ],
)
def test_window_an_unrecognised_ledger_is_counted_as_fully_spent(tmp_path: Path, body: bytes) -> None:
    path = tmp_path / DOWNLOAD_LEDGER_FILENAME
    path.write_bytes(body)
    written_at(path, OPERATOR_EVENING)
    ledger = DownloadLedger(path)

    assert ledger.remaining_at(OPERATOR_EVENING + timedelta(hours=23, minutes=59)) == 0
    assert ledger.remaining_at(OPERATOR_EVENING + timedelta(hours=24, minutes=1)) == 5


def test_window_a_naive_start_is_refused_rather_than_guessed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        DownloadLedger(tmp_path / DOWNLOAD_LEDGER_FILENAME).record(datetime(2026, 9, 29, 4, 45))  # noqa: DTZ001


@settings(max_examples=150, deadline=None)
@given(
    gaps=st.lists(st.integers(min_value=0, max_value=30 * 3600), min_size=1, max_size=40),
    wanted=st.lists(st.integers(min_value=0, max_value=7), min_size=40, max_size=40),
    legacy_spent=st.one_of(st.none(), st.integers(min_value=0, max_value=5)),
    legacy_age_seconds=st.integers(min_value=0, max_value=30 * 3600),
)
def test_window_no_24_hours_ever_holds_more_than_five_starts(
    gaps: list[int], wanted: list[int], legacy_spent: int | None, legacy_age_seconds: int
) -> None:
    """Runs at arbitrary gaps, each fetching as much as it wants of what the window allows.

    Every run reads the ledger afresh, as separate processes do. Whatever the gaps, the starts in
    any 24 hours ending at a start — the old calendar ledger's included — never exceed five, and
    24 hours with nothing started always leaves the whole five.

    The starts are counted from this test's own account of what it recorded and planted, never
    read back through the ledger: an oracle that asked the code under test what had been spent
    was blind to a ledger that forgot something (found by a deep run, v1-e34-t06).
    """
    with tempfile.TemporaryDirectory() as directory:
        state = Path(directory)
        legacy = state / LEGACY_DOWNLOAD_LEDGER_FILENAME
        now = OPERATOR_EVENING
        spent: list[datetime] = []
        if legacy_spent is not None:
            legacy.write_text(
                json.dumps({"date": "2026-09-29", "bulk_downloads": legacy_spent}), encoding="utf-8"
            )
            planted = now - timedelta(seconds=legacy_age_seconds)
            written_at(legacy, planted)
            # Truncated to the second, as the file system keeps it and the ledger reads it.
            spent.extend([datetime.fromtimestamp(int(planted.timestamp()), UTC)] * legacy_spent)
        for gap, want in zip(gaps, wanted, strict=False):
            now += timedelta(seconds=gap)
            ledger = DownloadLedger(state / DOWNLOAD_LEDGER_FILENAME, legacy_path=legacy)
            allowed = ledger.remaining_at(now)
            if all(started <= now - A_ROLLING_DAY for started in spent):
                assert allowed == DEFAULT_BULK_DOWNLOADS_PER_DAY, "24 idle hours must leave the whole five"
            for second in range(min(want, allowed)):
                ledger.record(now + timedelta(seconds=second))
                spent.append(now + timedelta(seconds=second))
            now += timedelta(seconds=min(want, allowed))
        for end in spent:
            inside = [one for one in spent if end - A_ROLLING_DAY < one <= end]
            assert len(inside) <= DEFAULT_BULK_DOWNLOADS_PER_DAY, (end, inside)


async def test_a_day_long_retry_after_defers_the_rest_and_the_run_still_imports(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """ "Skip today", not a failure: the bytes that landed are imported and the run exits happy."""
    await import_first_week(data_dir, archives)
    source.rate_limit_after = 1
    service = build_service(source=source, data_dir=data_dir, inbox=inbox)

    summary = await service.run([SYNTHETIC_CASELIST])

    assert source.archive_fetches == [weekly_name(date(2026, 9, 8))]
    assert decisions(summary.archives)[weekly_name(date(2026, 9, 15))] == str(
        SelectionDecision.DEFERRED_BY_RATE_LIMIT
    )
    assert summary.stage(SyncStage.DOWNLOAD).outcome is StageOutcome.COMPLETED  # type: ignore[union-attr]
    assert summary.snapshots_imported == (f"{SYNTHETIC_CASELIST} 2026-09-08",)
    assert summary.succeeded


async def test_a_short_rate_limit_is_a_download_failure_rather_than_a_deferral(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """A burst limit the transport already slept through and could not clear is a real failure."""
    await import_first_week(data_dir, archives)
    source.rate_limit_after = 0
    source.rate_limit_retry_after = 30.0
    service = build_service(source=source, data_dir=data_dir, inbox=inbox)

    summary = await service.run([SYNTHETIC_CASELIST])

    assert summary.stage(SyncStage.DOWNLOAD).outcome is StageOutcome.FAILED  # type: ignore[union-attr]
    assert not summary.succeeded


# ------------------------------------------------------------------------------------------------
# Publishing, and what happens when the AWS session has expired (ac3)
# ------------------------------------------------------------------------------------------------


async def test_a_run_publishes_the_snapshots_it_imported(
    source: FakeCaselistSource,
    data_dir: Path,
    inbox: Path,
    archives: dict[date, Path],
    bucket: S3EvidenceObjectStore,
) -> None:
    """Fourteen source objects, counted by hand from the fixture's tables.

    * `2026-09-08`'s manifest names the distinct digests that archive holds: its 13 stored members
      over 11 digests, because the two DUPLICATE members repeat the Round 1 affirmative's bytes.
      All 11 are new to the bucket.
    * `2026-09-15`'s manifest names 12: the same 11 less the Harbor Classic octafinals negative,
      which that week took down, plus the two new bodies. Ten of the eleven are already up, so two
      are uploaded.
    * the camp file is one more.

    11 + 2 + 1 = 14. `2026-09-01` is not published by this run: it was imported before it, and a
    run publishes what it imported plus whatever an earlier run left owed.
    """
    await import_first_week(data_dir, archives)
    local = local_evidence(data_dir)
    service = build_service(
        source=source,
        data_dir=data_dir,
        inbox=inbox,
        publisher=CaselistPublishService(suppression=empty_suppression_list(), local=local, remote=bucket),
        status=CaselistStatusService(suppression=empty_suppression_list(), local=local, remote=bucket),
    )

    summary = await service.run([SYNTHETIC_CASELIST])

    assert summary.objects_published == 14
    assert summary.stage(SyncStage.PUBLISH).outcome is StageOutcome.COMPLETED  # type: ignore[union-attr]
    assert (await bucket.head(manifest_key(SYNTHETIC_CASELIST, date(2026, 9, 15)))).size > 0
    assert summary.stage(SyncStage.REPORT).outcome is StageOutcome.COMPLETED  # type: ignore[union-attr]
    assert summary.succeeded


async def test_expired_credentials_leave_the_local_stages_done_and_the_rest_pending(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """ac3's first half: download and import complete, publish and report come back later."""
    await import_first_week(data_dir, archives)
    service = build_service(
        source=source,
        data_dir=data_dir,
        inbox=inbox,
        publisher=CaselistPublishService(
            suppression=empty_suppression_list(), local=local_evidence(data_dir), remote=ExpiredBucket()
        ),
        status=CaselistStatusService(
            suppression=empty_suppression_list(), local=local_evidence(data_dir), remote=ExpiredBucket()
        ),
    )

    summary = await service.run([SYNTHETIC_CASELIST])

    assert summary.stage(SyncStage.DOWNLOAD).outcome is StageOutcome.COMPLETED  # type: ignore[union-attr]
    assert summary.stage(SyncStage.IMPORT).outcome is StageOutcome.COMPLETED  # type: ignore[union-attr]
    assert summary.stage(SyncStage.PUBLISH).outcome is StageOutcome.PENDING  # type: ignore[union-attr]
    assert summary.stage(SyncStage.REPORT).outcome is StageOutcome.PENDING  # type: ignore[union-attr]
    assert summary.pending_publish == (
        f"{SYNTHETIC_CASELIST} 2026-09-08",
        f"{SYNTHETIC_CASELIST} 2026-09-15",
        "openev 2026-policy",
    )
    assert (data_dir / PENDING_WORK_FILENAME).is_file()
    assert "aws sso login" in (summary.stage(SyncStage.PUBLISH).reason or "")  # type: ignore[union-attr]


async def test_publish_pending_completes_what_the_expired_run_left(
    source: FakeCaselistSource,
    data_dir: Path,
    inbox: Path,
    archives: dict[date, Path],
    bucket: S3EvidenceObjectStore,
) -> None:
    """ac3's second half: after `aws sso login`, the same fourteen objects go up and nothing else."""
    await import_first_week(data_dir, archives)
    expired = build_service(
        source=source,
        data_dir=data_dir,
        inbox=inbox,
        publisher=CaselistPublishService(
            suppression=empty_suppression_list(), local=local_evidence(data_dir), remote=ExpiredBucket()
        ),
    )
    await expired.run([SYNTHETIC_CASELIST])

    local = local_evidence(data_dir)
    logged_in = build_service(
        source=source,
        data_dir=data_dir,
        inbox=inbox,
        publisher=CaselistPublishService(suppression=empty_suppression_list(), local=local, remote=bucket),
        status=CaselistStatusService(suppression=empty_suppression_list(), local=local, remote=bucket),
    )
    drained = await logged_in.publish_pending()

    assert drained.objects_published == 14
    assert drained.stage(SyncStage.PUBLISH).outcome is StageOutcome.COMPLETED  # type: ignore[union-attr]
    assert drained.stage(SyncStage.DOWNLOAD).outcome is StageOutcome.SKIPPED  # type: ignore[union-attr]
    assert source.archive_fetches == [weekly_name(date(2026, 9, 8)), weekly_name(date(2026, 9, 15))]
    assert not (data_dir / PENDING_WORK_FILENAME).exists(), "the pending-work file was not drained"


# ------------------------------------------------------------------------------------------------
# The dry run (ac2)
# ------------------------------------------------------------------------------------------------


async def test_a_dry_run_lists_what_it_would_do_and_changes_nothing(
    source: FakeCaselistSource,
    data_dir: Path,
    inbox: Path,
    archives: dict[date, Path],
    bucket: S3EvidenceObjectStore,
) -> None:
    """ac2: the plan is printed, and the store, the manifests and the bucket are untouched."""
    await import_first_week(data_dir, archives)
    local = local_evidence(data_dir)
    service = build_service(
        source=source,
        data_dir=data_dir,
        inbox=inbox,
        publisher=CaselistPublishService(suppression=empty_suppression_list(), local=local, remote=bucket),
        status=CaselistStatusService(suppression=empty_suppression_list(), local=local, remote=bucket),
    )
    before = _fingerprint(data_dir)

    summary = await service.run([SYNTHETIC_CASELIST], dry_run=True)

    assert summary.dry_run
    assert [one.name for one in summary.archives if one.wanted] == [
        weekly_name(date(2026, 9, 8)),
        weekly_name(date(2026, 9, 15)),
    ]
    planned = {SyncStage.DOWNLOAD, SyncStage.IMPORT, SyncStage.PUBLISH, SyncStage.REPORT}
    assert {record.outcome for record in summary.stages if record.stage in planned} == {StageOutcome.PLANNED}
    assert source.archive_fetches == []
    assert source.openev_fetches == []
    assert await bucket.list_objects("") == ()
    assert _fingerprint(data_dir) == before
    assert not (data_dir / RUN_SUMMARY_DIRECTORY).exists()


def _fingerprint(data_dir: Path) -> dict[str, int]:
    """Every file under the data directory and its size: what "unchanged" is asserted against.

    The run lock is left out. A dry run takes it — it reads the inbox and the manifests, and a
    real run writing them underneath it would make its plan a work of fiction — and an empty lock
    file is not the local store, a manifest or anything ac2 says must be left alone.
    """
    return {
        str(path.relative_to(data_dir)): path.stat().st_size
        for path in sorted(data_dir.rglob("*"))
        if path.is_file() and path.name != LOCK_FILENAME
    }


# ------------------------------------------------------------------------------------------------
# One run at a time, and the summary it leaves behind (ac4)
# ------------------------------------------------------------------------------------------------


async def test_a_second_run_while_one_is_running_exits_at_once_with_a_lock_message(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    await import_first_week(data_dir, archives)
    held = build_service(source=source, data_dir=data_dir, inbox=inbox)
    second = build_service(source=source, data_dir=data_dir, inbox=inbox)

    with RunLock(data_dir / LOCK_FILENAME), pytest.raises(SyncRunInProgress) as refused:
        await second.run([SYNTHETIC_CASELIST])

    assert "already running" in str(refused.value)
    assert source.archive_fetches == [], "the refused run must do nothing at all"
    # And the lock is released, so the next run is not blocked for ever.
    summary = await held.run([SYNTHETIC_CASELIST])
    assert summary.archives_downloaded == 2


async def test_each_run_writes_a_json_summary_with_no_school_team_code_or_token(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """ac4: the counts an operator checks the week against, and nothing the policy forbids."""
    await import_first_week(data_dir, archives)
    service = build_service(
        source=source,
        data_dir=data_dir,
        inbox=inbox,
        parse=RecordingParseStage(),
        landscape=RecordingLandscapeStage(reports_written=2),
    )

    summary = await service.run([SYNTHETIC_CASELIST])

    written = service.summary_path(summary)
    body = json.loads(written.read_text(encoding="utf-8"))
    assert body["archives_seen"] == 5
    assert body["archives_downloaded"] == 2
    assert body["files_imported"] == 28
    assert body["files_duplicate"] == 2
    assert body["cards_parsed"] == 17
    assert body["parse_failures"] == 1
    assert body["objects_published"] == 0
    assert body["reports_written"] == 2
    assert body["duration_seconds"] == 0.0
    assert set(body["stages"][0]) == {"stage", "outcome", "reason"}

    text = written.read_text(encoding="utf-8")
    for forbidden in ("Maple Grove", "Cedar Hollow", "Northgate Prep", "Riverbend Academy", "ZaLu"):
        assert forbidden not in text, f"{forbidden} must never reach a run summary"
    assert "token" not in text.lower()


# ------------------------------------------------------------------------------------------------
# The optional stages
# ------------------------------------------------------------------------------------------------


async def test_the_optional_stages_are_skipped_with_a_reason_when_they_are_not_installed(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """Today's normal path: neither v1-e31-t06 nor v1-e32-t05 exists, and the run is a success."""
    await import_first_week(data_dir, archives)
    service = build_service(source=source, data_dir=data_dir, inbox=inbox)

    summary = await service.run([SYNTHETIC_CASELIST])

    parse = summary.stage(SyncStage.PARSE)
    landscape = summary.stage(SyncStage.LANDSCAPE)
    assert parse is not None and parse.outcome is StageOutcome.SKIPPED
    assert "v1-e31-t06" in (parse.reason or "")
    assert landscape is not None and landscape.outcome is StageOutcome.SKIPPED
    assert "v1-e32-t05" in (landscape.reason or "")
    assert summary.succeeded
    assert summary.snapshots_imported, "the bytes were still captured"


async def test_an_optional_stage_that_fails_does_not_fail_a_run_whose_bytes_are_safe(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    await import_first_week(data_dir, archives)
    service = build_service(
        source=source,
        data_dir=data_dir,
        inbox=inbox,
        parse=RecordingParseStage(failure=OSError("the parse worker died")),
    )

    summary = await service.run([SYNTHETIC_CASELIST])

    assert summary.stage(SyncStage.PARSE).outcome is StageOutcome.FAILED  # type: ignore[union-attr]
    assert summary.succeeded
    assert summary.files_imported == 28


async def test_the_optional_stages_run_when_they_are_installed(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    await import_first_week(data_dir, archives)
    parse = RecordingParseStage()
    landscape = RecordingLandscapeStage(reports_written=3)
    service = build_service(source=source, data_dir=data_dir, inbox=inbox, parse=parse, landscape=landscape)

    summary = await service.run([SYNTHETIC_CASELIST])

    assert parse.calls == [(SYNTHETIC_CASELIST,)]
    assert landscape.calls == 1
    assert summary.cards_parsed == 17
    assert summary.parse_failures == 1
    assert summary.reports_written == 3


async def test_a_run_with_no_caselist_refuses_rather_than_doing_nothing_quietly(
    source: FakeCaselistSource, data_dir: Path, inbox: Path
) -> None:
    service = build_service(source=source, data_dir=data_dir, inbox=inbox)

    with pytest.raises(NoCaselistsConfigured):
        await service.run([])


# ------------------------------------------------------------------------------------------------
# The listings themselves, and the OpenEv shapes
# ------------------------------------------------------------------------------------------------


async def test_a_rate_limited_listing_ends_the_run_without_calling_it_a_failure(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """Nothing had been fetched yet, so nothing is at risk: the run says why and waits a week."""
    await import_first_week(data_dir, archives)

    async def refuse(caselist: str) -> list[ArchiveListing]:
        raise ProviderRateLimited("opencaselist", "listing is rate limited", retry_after_seconds=86_400.0)

    source.list_archives = refuse  # type: ignore[method-assign]
    service = build_service(source=source, data_dir=data_dir, inbox=inbox)

    summary = await service.run([SYNTHETIC_CASELIST])

    select = summary.stage(SyncStage.SELECT)
    assert select is not None and select.outcome is StageOutcome.SKIPPED
    assert "rate limiting" in (select.reason or "")
    assert summary.archives_downloaded == 0
    assert summary.succeeded


async def test_an_openev_release_that_is_a_zip_is_read_as_one(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path], tmp_path: Path
) -> None:
    """OpenEv publishes single documents and whole camp releases; both reach the same importer.

    The synthetic release `openev-2026-policy` holds eleven files and two pieces of macOS junk
    (`tests/fixtures/openev/`). Its hand-written expectations are in
    `expected_openev_import.json`, under `after_caselist` — the case where the caselist archives
    were imported first, which is what this run does: 9 NEW and 2 DUPLICATE, 2 skipped.

    Added to the two weeklies (13 + 14 stored members, 3 + 5 skips, from
    `expected_summary.json`), this run must report 38 files imported and 10 skipped.
    """
    await import_first_week(data_dir, archives)
    releases = build_download_zips(tmp_path / "camp")
    release = releases["openev-2026-policy"]
    source.openev_files = [
        (
            OpenEvFile(
                openev_id=901,
                path=f"openev/{OPENEV_YEAR}/releases/openev-2026-policy.zip",
                filename="openev-2026-policy.zip",
                year=OPENEV_YEAR,
                tags=("policy",),
            ),
            release.read_bytes(),
        )
    ]
    service = build_service(source=source, data_dir=data_dir, inbox=inbox)

    summary = await service.run([SYNTHETIC_CASELIST])

    release_counts = expected_openev()["first_download"]["after_caselist"]
    assert summary.openev_downloaded == 1
    assert "openev 2026-policy" in summary.snapshots_imported
    assert release_counts["counts"]["NEW"] + release_counts["counts"]["DUPLICATE"] == 11
    assert release_counts["skipped_total"] == 2
    assert summary.files_imported == 38
    assert summary.files_skipped == 10

    again = await service.run([SYNTHETIC_CASELIST])

    # Its manifest names the release's members, never the zip's own inbox name, so it is the
    # download digest the rows carry that says these bytes were imported (v1-e34-t06 ac1).
    assert [one.decision for one in again.openev] == [SelectionDecision.ALREADY_IMPORTED]
    assert again.nothing_new, "a camp release left in the inbox was imported again"


async def test_a_camp_file_whose_event_nobody_states_is_listed_and_left_alone(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """Filing it under a guess would put it in the wrong release manifest for the season."""
    await import_first_week(data_dir, archives)
    listed, body = source.openev_files[0]
    source.openev_files = [(listed.model_copy(update={"tags": ("kritiks",)}), body)]
    service = build_service(source=source, data_dir=data_dir, inbox=inbox)

    summary = await service.run([SYNTHETIC_CASELIST])

    assert [one.decision for one in summary.openev] == [SelectionDecision.NO_EVENT_CONFIGURED]
    assert source.openev_fetches == []
    assert summary.succeeded


async def test_a_caselist_whose_event_this_build_does_not_know_is_not_imported_under_a_guess(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """The event decides which sides are legal; the wrong one would mis-file a whole archive."""
    await import_first_week(data_dir, archives)
    service = build_service(source=source, data_dir=data_dir, inbox=inbox)

    def no_event_is_known(_slug: str) -> Event | None:
        return None

    service._event_for_caselist = no_event_is_known  # pyright: ignore[reportPrivateUsage]

    summary = await service.run([SYNTHETIC_CASELIST])

    stage = summary.stage(SyncStage.IMPORT)
    assert stage is not None and stage.outcome is StageOutcome.FAILED
    assert "does not know which event" in (stage.reason or "")
    assert not any(one.startswith(SYNTHETIC_CASELIST) for one in summary.snapshots_imported)
    assert not summary.succeeded
    assert summary.archives_downloaded == 2, "the bytes are in the inbox either way"


def test_an_unreadable_pending_work_file_reads_as_nothing_owed(tmp_path: Path) -> None:
    """A state file this module wrote and something else corrupted must not stop a run."""
    path = tmp_path / PENDING_WORK_FILENAME
    path.write_text("{not json at all", encoding="utf-8")

    assert PendingWork(path).read() == ()


# ------------------------------------------------------------------------------------------------
# A run the daily bulk-download cap truncated (v1-e34-t03 ac5 and ac6)
# ------------------------------------------------------------------------------------------------
#
# The condition measured in dev on 2026-09-24 (docs/data/caselist-sync-runs.md): the first run of
# the day spent the five and deferred the rest; the runs after it had nothing left to spend and
# reported "Nothing new" against a store that held none of the archives they had deferred. Here
# the scenario is the table at the top of this module: 2026-09-01 is held, so exactly two weeklies
# are wanted — 2026-09-08 and 2026-09-15. Every count below is those two, split by hand.


def spend_allowance_before_the_run(data_dir: Path, downloads: int = DEFAULT_BULK_DOWNLOADS_PER_DAY) -> None:
    """Record `downloads` bulk downloads an hour before `RUN_CLOCK`, as an earlier run would have."""
    spend_allowance(data_dir, downloads, at=RUN_CLOCK - timedelta(hours=1))


async def test_a_run_the_cap_blocked_entirely_is_not_nothing_new(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """The second and third dev runs of 2026-09-24: nothing fetched because nothing was allowed."""
    source.openev_files = []  # none were listed on the dev day either
    await import_first_week(data_dir, archives)
    spend_allowance_before_the_run(data_dir)
    service = build_service(source=source, data_dir=data_dir, inbox=inbox)

    summary = await service.run([SYNTHETIC_CASELIST])

    assert source.archive_fetches == []
    assert summary.archives_wanted == 2
    assert summary.archives_deferred == 2
    assert not summary.nothing_new, "a run that was not allowed to fetch must not say nothing was new"
    assert summary.succeeded, "the cap is a delay, not a failure (ADR-0017)"
    select = summary.stage(SyncStage.SELECT)
    assert select is not None
    assert "2 wanted" in (select.reason or "")
    assert "2 deferred by the daily download cap" in (select.reason or "")
    download = summary.stage(SyncStage.DOWNLOAD)
    assert download is not None
    assert "nothing new" not in (download.reason or "")
    assert "2 archive(s) deferred by the daily download cap" in (download.reason or "")
    body = summary.as_json()
    assert body["nothing_new"] is False
    assert body["archives_wanted"] == 2
    assert body["archives_deferred"] == 2


async def test_a_run_the_cap_truncated_states_wanted_and_deferred(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """The first dev run of 2026-09-24, in miniature: one of two fetched, one left for later."""
    source.openev_files = []  # none were listed on the dev day either
    await import_first_week(data_dir, archives)
    spend_allowance_before_the_run(data_dir, DEFAULT_BULK_DOWNLOADS_PER_DAY - 1)
    service = build_service(source=source, data_dir=data_dir, inbox=inbox)

    summary = await service.run([SYNTHETIC_CASELIST])

    assert source.archive_fetches == [weekly_name(date(2026, 9, 8))]
    assert summary.archives_downloaded == 1
    assert summary.archives_wanted == 2
    assert summary.archives_deferred == 1
    assert not summary.nothing_new
    select = summary.stage(SyncStage.SELECT)
    assert select is not None
    assert "1 to fetch of 2 wanted" in (select.reason or "")
    assert "1 deferred by the daily download cap" in (select.reason or "")


async def test_a_run_that_fetched_everything_wanted_says_nothing_about_a_cap(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """The clean week: wanted and fetched are the same number, so no deferral is mentioned."""
    source.openev_files = []  # none were listed on the dev day either
    await import_first_week(data_dir, archives)
    service = build_service(source=source, data_dir=data_dir, inbox=inbox)

    summary = await service.run([SYNTHETIC_CASELIST])

    assert summary.archives_wanted == 2
    assert summary.archives_deferred == 0
    select = summary.stage(SyncStage.SELECT)
    assert select is not None
    assert "deferred" not in (select.reason or "")


async def test_a_day_long_retry_after_counts_as_deferred_by_the_cap(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """The server's own limiter is the same cap seen from the other side: deferred, and counted."""
    source.openev_files = []  # none were listed on the dev day either
    await import_first_week(data_dir, archives)
    source.rate_limit_after = 1
    service = build_service(source=source, data_dir=data_dir, inbox=inbox)

    summary = await service.run([SYNTHETIC_CASELIST])

    assert summary.archives_downloaded == 1
    assert summary.archives_wanted == 2
    assert summary.archives_deferred == 1
    assert not summary.nothing_new


async def test_an_immediate_re_run_with_nothing_deferred_is_still_nothing_new(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """The fix must not break the true case: everything held, nothing wanted, nothing new."""
    source.openev_files = []  # none were listed on the dev day either
    await import_first_week(data_dir, archives)
    service = build_service(source=source, data_dir=data_dir, inbox=inbox)
    await service.run([SYNTHETIC_CASELIST])

    again = await service.run([SYNTHETIC_CASELIST])

    assert again.archives_wanted == 0
    assert again.archives_deferred == 0
    assert again.nothing_new


# ------------------------------------------------------------------------------------------------
# Run records and notifications around a real pull (v1-e34-t03 ac1, ac2, ac4)
# ------------------------------------------------------------------------------------------------
#
# `SyncRunMonitor` wraps the service from outside. These run the real pipeline under it, with a
# RecordingNotifier: no notification and no AWS call leaves the test (moto only).

DEV_LOGIN = "aws sso login --profile debate-dev-evidence"
FIXTURE_TOKEN = "fixture-token-8c2d41f07ab9"
SYNTHETIC_STUDENT = "Juniper Okafor"
"""An invented debater's name, planted where a real one could leak: a disclosure path."""


def sync_monitor(data_dir: Path, notifier: RecordingNotifier, remote: object | None = None) -> SyncRunMonitor:
    return SyncRunMonitor(
        state_dir=data_dir,
        environment="dev",
        notifier=notifier,
        remote=remote,  # type: ignore[arg-type]
        aws_login_command=DEV_LOGIN,
        secrets=lambda: [FIXTURE_TOKEN],
        clock=lambda: RUN_CLOCK,
    )


def run_log(data_dir: Path) -> list[SyncRunRecord]:
    return SyncRunLog(data_dir / SYNC_RUN_LOG_FILENAME).read()


async def test_a_successful_pull_leaves_one_run_record_and_notifies_nobody(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    await import_first_week(data_dir, archives)
    service = build_service(source=source, data_dir=data_dir, inbox=inbox)
    notifier = RecordingNotifier()

    monitored = await sync_monitor(data_dir, notifier).watch(
        lambda: service.run([SYNTHETIC_CASELIST]), caselists=[SYNTHETIC_CASELIST], mode="run"
    )

    [record] = run_log(data_dir)
    assert record == monitored.record
    assert record.outcome is SyncRunOutcome.COMPLETED
    assert (record.archives_wanted, record.archives_downloaded, record.archives_deferred) == (2, 2, 0)
    assert record.openev_downloaded == 1
    assert notifier.sent == []


async def test_a_failed_download_stage_leaves_a_run_record_and_one_notify_naming_the_rerun(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    await import_first_week(data_dir, archives)
    source.rate_limit_after = 0
    source.rate_limit_retry_after = 30.0  # a burst limit, not the daily one: a real failure
    service = build_service(source=source, data_dir=data_dir, inbox=inbox)
    notifier = RecordingNotifier()

    monitored = await sync_monitor(data_dir, notifier).watch(
        lambda: service.run([SYNTHETIC_CASELIST]), caselists=[SYNTHETIC_CASELIST], mode="run"
    )

    assert not monitored.summary.succeeded
    [record] = run_log(data_dir)
    assert record.outcome is SyncRunOutcome.FAILED
    [notification] = notifier.sent
    assert notification.title == "caselist pull failed"
    assert "download" in notification.message
    assert notification.fix_command == "debate-research caselist pull"


async def test_an_expired_caselist_token_leaves_a_run_record_and_one_notify_naming_auth_login(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """CaselistAuthExpired escapes the run (policy E34 gate 5); the monitor records it anyway."""
    await import_first_week(data_dir, archives)

    async def refuse(caselist: str) -> list[ArchiveListing]:
        raise CaselistAuthExpired(401, f"list archives for {caselist}")

    source.list_archives = refuse  # type: ignore[method-assign]
    service = build_service(source=source, data_dir=data_dir, inbox=inbox)
    notifier = RecordingNotifier()

    with pytest.raises(CaselistAuthExpired):
        await sync_monitor(data_dir, notifier).watch(
            lambda: service.run([SYNTHETIC_CASELIST]), caselists=[SYNTHETIC_CASELIST], mode="run"
        )

    [record] = run_log(data_dir)
    assert record.outcome is SyncRunOutcome.FAILED
    assert record.error_class == "CaselistAuthExpired"
    [notification] = notifier.sent
    assert notification.fix_command == "debate-research caselist auth login"


async def test_an_expired_sso_session_leaves_a_run_record_and_one_notify_naming_sso_login(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """Publish pends, the record's own upload pends, and the operator hears about it once."""
    await import_first_week(data_dir, archives)
    service = build_service(
        source=source,
        data_dir=data_dir,
        inbox=inbox,
        publisher=CaselistPublishService(
            suppression=empty_suppression_list(), local=local_evidence(data_dir), remote=ExpiredBucket()
        ),
        status=CaselistStatusService(
            suppression=empty_suppression_list(), local=local_evidence(data_dir), remote=ExpiredBucket()
        ),
    )
    notifier = RecordingNotifier()

    monitored = await sync_monitor(data_dir, notifier, remote=ExpiredBucket()).watch(
        lambda: service.run([SYNTHETIC_CASELIST]), caselists=[SYNTHETIC_CASELIST], mode="run"
    )

    assert monitored.summary.succeeded, "an expired session is a delay, not a failed run"
    [record] = run_log(data_dir)
    assert record.outcome is SyncRunOutcome.PUBLISH_PENDING
    assert not monitored.record_published
    [notification] = notifier.sent
    assert notification.fix_command.startswith(DEV_LOGIN)
    assert "caselist pull --publish-pending" in notification.fix_command


async def test_a_cap_blocked_run_record_is_cap_deferred_and_does_not_notify(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """ac5: a backlog that has not grown for two runs is recorded, not announced."""
    source.openev_files = []
    await import_first_week(data_dir, archives)
    spend_allowance_before_the_run(data_dir)
    service = build_service(source=source, data_dir=data_dir, inbox=inbox)
    notifier = RecordingNotifier()

    await sync_monitor(data_dir, notifier).watch(
        lambda: service.run([SYNTHETIC_CASELIST]), caselists=[SYNTHETIC_CASELIST], mode="run"
    )

    [record] = run_log(data_dir)
    assert record.outcome is SyncRunOutcome.CAP_DEFERRED
    assert record.deferred_by_caselist == {SYNTHETIC_CASELIST: 2}
    assert notifier.sent == []


async def test_redact_no_fixture_token_or_student_name_reaches_a_record_or_a_notification(
    source: FakeCaselistSource,
    data_dir: Path,
    inbox: Path,
    archives: dict[date, Path],
    bucket: S3EvidenceObjectStore,
) -> None:
    """ac4's redaction test: plant both where a careless message would carry them, and look.

    The parse stage fails with an `OSError` naming a disclosure path that holds a synthetic
    student's name and the fixture token; the run then records a parse failure and notifies. The
    local log, the object in the (moto) bucket and every notification are searched for both.
    """
    await import_first_week(data_dir, archives)
    planted = OSError(
        2,
        f"No such file or directory (caselist_token={FIXTURE_TOKEN})",
        f"inbox/Maple Grove/ZaLu/{SYNTHETIC_STUDENT}-Aff-Harbor Classic-Round 1.docx",
    )
    service = build_service(
        source=source, data_dir=data_dir, inbox=inbox, parse=RecordingParseStage(failure=planted)
    )
    notifier = RecordingNotifier()

    monitored = await sync_monitor(data_dir, notifier, remote=bucket).watch(
        lambda: service.run([SYNTHETIC_CASELIST]), caselists=[SYNTHETIC_CASELIST], mode="run"
    )

    assert monitored.record.outcome is SyncRunOutcome.INCOMPLETE
    assert monitored.record_published
    published = data_dir / "published-record.json"
    await bucket.get_file(monitored.record.object_key, published)
    notified = [f"{one.title} {one.message} {one.fix_command}" for one in notifier.sent]
    assert notified, "a failed stage must notify"
    for text in (
        (data_dir / SYNC_RUN_LOG_FILENAME).read_text(encoding="utf-8"),
        published.read_text(encoding="utf-8"),
        *notified,
    ):
        for forbidden in (FIXTURE_TOKEN, SYNTHETIC_STUDENT, "Juniper", "Okafor", "ZaLu", "Maple Grove"):
            assert forbidden not in text, f"{forbidden!r} reached a record or a notification"


def test_notify_through_osascript_passes_the_text_as_arguments_not_script() -> None:
    """A quote in the text cannot end an AppleScript string, because it is never in the script."""
    ran: list[list[str]] = []

    def record_command(command: Sequence[str]) -> int:
        ran.append(list(command))
        return 0

    hostile = 'done" & (do shell script "touch /tmp/owned") & "'
    MacOsNotifier(run=record_command, executable="/usr/bin/osascript").notify(
        Notification(
            title="caselist pull failed", message=hostile, fix_command="debate-research caselist pull"
        )
    )

    [command] = ran
    script = [command[index + 1] for index, part in enumerate(command) if part == "-e"]
    assert all(hostile not in line and "touch" not in line for line in script)
    assert command[-3].startswith('done" & (do shell script')
    assert command[-2:] == ["caselist pull failed", "debate-research caselist pull"]


def test_notify_failure_of_osascript_does_not_raise() -> None:
    def broken(command: Sequence[str]) -> int:
        raise FileNotFoundError("osascript")

    MacOsNotifier(run=broken).notify(Notification(title="t", message="m", fix_command="f"))
