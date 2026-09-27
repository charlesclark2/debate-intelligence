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
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_synthetic_archives import (
    SNAPSHOTS,
    SYNTHETIC_CASELIST,
    build_snapshot_zips,
)
from tests.fixtures.openev.build_synthetic_openev import DOCUMENT_BODIES, build_download_zips
from tests.fixtures.openev.build_synthetic_openev import expected as expected_openev

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.import_service import CaselistImportService
from debate_core.application.caselist.manifest import manifest_key, write_manifest
from debate_core.application.caselist.openev_import_service import OpenEvImportService
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.status_service import CaselistStatusService
from debate_core.application.caselist_sync import (
    DEFAULT_BULK_DOWNLOADS_PER_DAY,
    DOWNLOAD_LEDGER_FILENAME,
    LOCK_FILENAME,
    PENDING_WORK_FILENAME,
    RUN_SUMMARY_DIRECTORY,
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
    within_daily_budget,
)
from debate_core.application.errors import (
    ProviderRateLimited,
    StoreCredentialsExpired,
)
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
from debate_core.integrations.local.archive_reader import read_archive
from debate_core.integrations.local.macos_notifier import MacOsNotifier
from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository
from debate_core.integrations.s3 import S3EvidenceObjectStore

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
        caselists=SqliteCaselistRepository(database), blobs=FsSnapshotStore(data_dir)
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
) -> CaselistSyncService:
    database = SqliteDatabase.open(data_dir)
    repository = SqliteCaselistRepository(database)
    blobs = FsSnapshotStore(data_dir)
    return CaselistSyncService(
        source=source,
        archive_importer=CaselistImportService(caselists=repository, blobs=blobs),
        openev_importer=OpenEvImportService(caselists=repository, blobs=blobs),
        local=local_evidence(data_dir),
        read_archive=lambda path: read_archive(path, **_LIMITS),
        event_for_caselist=lambda slug: Event.LD if slug.startswith("testcl") else None,
        inbox=inbox,
        state_dir=data_dir,
        publisher=publisher,
        status=status,
        parse=parse,  # type: ignore[arg-type]
        landscape=landscape,  # type: ignore[arg-type]
        bulk_downloads_per_day=bulk_downloads_per_day,
        clock=clock,
    )


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


async def test_what_a_run_spent_is_carried_into_the_next_run_on_the_same_day(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """The five are a day's allowance, not a run's. A second run today starts from what is left."""
    await import_first_week(data_dir, archives)
    service = build_service(source=source, data_dir=data_dir, inbox=inbox, bulk_downloads_per_day=2)

    await service.run([SYNTHETIC_CASELIST])
    ledger = DownloadLedger(data_dir / DOWNLOAD_LEDGER_FILENAME, limit=2)

    assert ledger.spent_on(RUN_CLOCK.date()) == 2
    assert ledger.remaining_on(RUN_CLOCK.date()) == 0
    assert ledger.remaining_on(date(2026, 9, 17)) == 2, "yesterday's count is not a debt"


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
        publisher=CaselistPublishService(local=local, remote=bucket),
        status=CaselistStatusService(local=local, remote=bucket),
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
        publisher=CaselistPublishService(local=local_evidence(data_dir), remote=ExpiredBucket()),
        status=CaselistStatusService(local=local_evidence(data_dir), remote=ExpiredBucket()),
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
        publisher=CaselistPublishService(local=local_evidence(data_dir), remote=ExpiredBucket()),
    )
    await expired.run([SYNTHETIC_CASELIST])

    local = local_evidence(data_dir)
    logged_in = build_service(
        source=source,
        data_dir=data_dir,
        inbox=inbox,
        publisher=CaselistPublishService(local=local, remote=bucket),
        status=CaselistStatusService(local=local, remote=bucket),
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
        publisher=CaselistPublishService(local=local, remote=bucket),
        status=CaselistStatusService(local=local, remote=bucket),
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


def spend_todays_allowance(data_dir: Path, downloads: int = DEFAULT_BULK_DOWNLOADS_PER_DAY) -> None:
    """Record `downloads` bulk downloads as already spent today, as an earlier run would have."""
    DownloadLedger(data_dir / DOWNLOAD_LEDGER_FILENAME).record(RUN_CLOCK.date(), downloads)


async def test_a_run_the_cap_blocked_entirely_is_not_nothing_new(
    source: FakeCaselistSource, data_dir: Path, inbox: Path, archives: dict[date, Path]
) -> None:
    """The second and third dev runs of 2026-09-24: nothing fetched because nothing was allowed."""
    source.openev_files = []  # none were listed on the dev day either
    await import_first_week(data_dir, archives)
    spend_todays_allowance(data_dir)
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
    spend_todays_allowance(data_dir, DEFAULT_BULK_DOWNLOADS_PER_DAY - 1)
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
        publisher=CaselistPublishService(local=local_evidence(data_dir), remote=ExpiredBucket()),
        status=CaselistStatusService(local=local_evidence(data_dir), remote=ExpiredBucket()),
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
    spend_todays_allowance(data_dir)
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
