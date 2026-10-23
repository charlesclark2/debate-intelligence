"""Where the search index stage sits in a weekly run, and what the run records of it (`v1-e39-t09`).

The run is the real :class:`~debate_core.application.caselist_sync.CaselistSyncService`, with the real
importers, manifests and stores, over a fake OpenCaselist source; the search index stage is a stub
that records what it is asked and answers what a test tells it. What the stage itself decides is
`test_search_index_stage.py`'s. What is under test here is the run around it: the order, the
stores it is handed, when it is told there is no session, when it is skipped, and what the summary,
the run record, its details and the notifications make of each answer.

The archives are the invented ones of `tests/fixtures/caselist/` (`docs/policies/caselist-data-use.md`);
an index id here is a made-up hex string.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final

import pytest
from tests.fixtures.caselist.build_synthetic_archives import (
    SNAPSHOTS,
    SYNTHETIC_CASELIST,
    build_snapshot_zips,
)

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.import_service import CaselistImportService
from debate_core.application.caselist.openev_import_service import OpenEvImportService
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist_sync import (
    CaselistParseStage,
    CaselistSyncService,
    ParsedCaselist,
    PublishedParsedStore,
    RunSummary,
    SearchIndexStageCounts,
    SearchIndexStageReport,
    StageOutcome,
    SyncStage,
)
from debate_core.application.errors import StoreCredentialsExpired
from debate_core.application.ports.caselist_source import (
    ArchiveKind,
    ArchiveListing,
    CaselistInfo,
    DownloadedFile,
    OpenEvFile,
)
from debate_core.application.ports.evidence_store import ObjectInfo
from debate_core.application.ports.parsed_store import OPENEV_STORE
from debate_core.application.search_index_build import SearchIndexStoreNotReady
from debate_core.application.search_index_publish import SearchIndexWouldShrink, StoreShrink
from debate_core.application.sync_runs import (
    SyncRunOutcome,
    details_for_summary,
    notifications_for,
    record_for_summary,
)
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsEvidenceObjectStore, FsSnapshotStore, SqliteDatabase
from debate_core.integrations.local.archive_reader import read_archive
from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository
from debate_core.testing.fakes.suppression import empty_suppression_list

RUN_CLOCK: Final = datetime(2026, 9, 2, 6, 0, tzinfo=UTC)
INDEX_ID: Final = "0123456789abcdef"
LOGIN: Final = "aws sso login --profile debate-dev-evidence"
_LIMITS: Final = {"max_archive_bytes": 64 * 1024 * 1024, "max_unpacked_bytes": 64 * 1024 * 1024}

COUNTS: Final = SearchIndexStageCounts(
    index_id=INDEX_ID,
    built=True,
    published=False,
    documents=4,
    sqlite_bytes=40_000,
    gzip_bytes=12_000,
    bytes_per_document=10_000,
)


class FakeSource:
    """OpenCaselist listing the weeklies a test names, and no camp file."""

    def __init__(self, archives: Sequence[tuple[ArchiveListing, Path]] = ()) -> None:
        self.archives = list(archives)

    async def list_caselists(self, *, archived: bool | None = None) -> list[CaselistInfo]:
        return [CaselistInfo(slug=SYNTHETIC_CASELIST)]

    async def get_caselist(self, caselist: str) -> CaselistInfo:
        return CaselistInfo(slug=caselist)

    async def list_archives(self, caselist: str) -> list[ArchiveListing]:
        return [listing for listing, _ in self.archives if listing.caselist == caselist]

    async def list_openev(self, *, year: int | None = None) -> list[OpenEvFile]:
        return []

    async def download_archive(self, archive: ArchiveListing, inbox: Path) -> DownloadedFile:
        body = next(path for listing, path in self.archives if listing.name == archive.name).read_bytes()
        destination = inbox / archive.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(body)
        return DownloadedFile(
            path=destination,
            sha256=hashlib.sha256(body).hexdigest(),
            byte_size=len(body),
            source_name=archive.name,
            already_present=False,
        )

    async def download_openev(self, file: OpenEvFile, inbox: Path) -> DownloadedFile:  # pragma: no cover
        raise AssertionError("no camp file is listed")


class ExpiredBucket:
    """An evidence bucket whose credentials have run out."""

    async def list_objects(self, prefix: str) -> tuple[ObjectInfo, ...]:
        raise StoreCredentialsExpired(hint=LOGIN)

    async def head(self, key: str) -> ObjectInfo:
        raise StoreCredentialsExpired(hint=LOGIN)

    async def put_file(self, key: str, source: Path) -> ObjectInfo:
        raise StoreCredentialsExpired(hint=LOGIN)

    async def get_file(self, key: str, destination: Path) -> ObjectInfo:
        raise StoreCredentialsExpired(hint=LOGIN)


class FailingParseStage:
    """A parse stage whose pipeline raises on every caselist."""

    async def parse_new_sources(self, caselist: str) -> ParsedCaselist:
        raise SearchIndexStoreNotReady(caselist, "a synthetic parse failure")

    async def publish(self, caselist: str, version: str) -> PublishedParsedStore:  # pragma: no cover
        raise AssertionError("a failed parse is not published")


class RecordingIndexStage:
    """The search index stage, recording what the run hands it and answering `report`, or raising."""

    def __init__(
        self, report: SearchIndexStageReport | None = None, *, raises: Exception | None = None
    ) -> None:
        self.report = report or SearchIndexStageReport(
            outcome=StageOutcome.COMPLETED, reason=f"built {INDEX_ID}; published", counts=COUNTS
        )
        self.raises = raises
        self.calls: list[tuple[tuple[str, ...], str | None]] = []

    async def refresh(self, stores: Sequence[str], *, no_session: str | None) -> SearchIndexStageReport:
        self.calls.append((tuple(stores), no_session))
        if self.raises is not None:
            raise self.raises
        return self.report


def weekly(archives: dict[date, Path], snapshot: date) -> tuple[ArchiveListing, Path]:
    name = f"{SYNTHETIC_CASELIST}-weekly-{snapshot.isoformat()}.zip"
    listing = ArchiveListing(
        caselist=SYNTHETIC_CASELIST,
        name=name,
        kind=ArchiveKind.WEEKLY,
        archive_date=snapshot,
        url=f"https://files.example.invalid/{name}",
    )
    return listing, archives[snapshot]


def local_evidence(data_dir: Path) -> LocalEvidence:
    objects = FsEvidenceObjectStore(data_dir)
    blobs = FsEvidenceObjectStore(data_dir, subdirectory=Path("blobs"))
    return LocalEvidence(
        objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
    )


def run(
    tmp_path: Path,
    *,
    search_index: RecordingIndexStage | None,
    source: FakeSource | None = None,
    parse: CaselistParseStage | None = None,
    publisher: CaselistPublishService | None = None,
    dry_run: bool = False,
) -> RunSummary:
    data_dir = tmp_path / "evidence"
    database = SqliteDatabase.open(data_dir)
    repository = SqliteCaselistRepository(database)
    blobs = FsSnapshotStore(data_dir)
    service = CaselistSyncService(
        source=source or FakeSource(),
        archive_importer=CaselistImportService(
            suppression=empty_suppression_list(), caselists=repository, blobs=blobs
        ),
        openev_importer=OpenEvImportService(
            suppression=empty_suppression_list(), caselists=repository, blobs=blobs
        ),
        local=local_evidence(data_dir),
        read_archive=lambda path: read_archive(path, **_LIMITS),
        event_for_caselist=lambda slug: Event.LD if slug.startswith("testcl") else None,
        inbox=data_dir / "inbox",
        state_dir=data_dir,
        suppression=empty_suppression_list(),
        publisher=publisher,
        parse=parse,
        search_index=search_index,
        clock=lambda: RUN_CLOCK,
    )
    return asyncio.run(service.run([SYNTHETIC_CASELIST], dry_run=dry_run))


def stage_names(summary: RunSummary) -> list[str]:
    return [str(one.stage) for one in summary.stages]


def search_index_record(summary: RunSummary):  # noqa: ANN201 - the StageRecord, or a failed assertion
    record = summary.stage(SyncStage.SEARCH_INDEX)
    assert record is not None
    return record


# ------------------------------------------------------------------------------------------------
# Where it runs, and what it is handed
# ------------------------------------------------------------------------------------------------


def test_index_stage_runs_after_parse_and_before_landscape_even_when_nothing_was_imported(
    tmp_path: Path,
) -> None:
    stage = RecordingIndexStage()

    summary = run(tmp_path, search_index=stage)

    assert stage_names(summary) == [
        "select",
        "download",
        "import",
        "publish",
        "parse",
        "search_index",
        "landscape",
        "report",
        "retention",
    ]
    assert summary.snapshots_imported == ()
    assert stage.calls == [((SYNTHETIC_CASELIST, OPENEV_STORE), None)], "the configured caselists plus openev"
    record = search_index_record(summary)
    assert (record.outcome, record.reason) == (StageOutcome.COMPLETED, f"built {INDEX_ID}; published")
    assert summary.search_index == COUNTS
    assert summary.as_json()["search_index"] == {
        "index_id": INDEX_ID,
        "built": True,
        "published": False,
        "documents": 4,
        "sqlite_bytes": 40_000,
        "gzip_bytes": 12_000,
        "bytes_per_document": 10_000,
        "warnings": [],
        "removed": 0,
        "bytes_freed": 0,
        "previous_index_id": None,
        "documents_growth": None,
        "sqlite_bytes_growth": None,
        "gzip_bytes_growth": None,
        "not_cards_by_store": None,
    }


def test_index_stage_is_told_there_is_no_session_when_the_publish_stage_pended(tmp_path: Path) -> None:
    archives = build_snapshot_zips(tmp_path / "published")
    stage = RecordingIndexStage()
    data_dir = tmp_path / "evidence"

    summary = run(
        tmp_path,
        search_index=stage,
        source=FakeSource([weekly(archives, SNAPSHOTS[0].snapshot)]),
        publisher=CaselistPublishService(
            suppression=empty_suppression_list(), local=local_evidence(data_dir), remote=ExpiredBucket()
        ),
    )

    assert summary.stage(SyncStage.PUBLISH).outcome is StageOutcome.PENDING  # type: ignore[union-attr]
    assert stage.calls == [((SYNTHETIC_CASELIST, OPENEV_STORE), "the publish stage found no AWS session")]


def test_index_stage_is_skipped_when_this_runs_parse_stage_failed(tmp_path: Path) -> None:
    archives = build_snapshot_zips(tmp_path / "published")
    stage = RecordingIndexStage()

    summary = run(
        tmp_path,
        search_index=stage,
        source=FakeSource([weekly(archives, SNAPSHOTS[0].snapshot)]),
        parse=FailingParseStage(),
    )

    assert summary.stage(SyncStage.PARSE).outcome is StageOutcome.FAILED  # type: ignore[union-attr]
    record = search_index_record(summary)
    assert record.outcome is StageOutcome.SKIPPED
    assert record.reason == (
        "the parse stage failed in this run, so the index is not rebuilt from what it left; "
        "the previous index stays current"
    )
    assert stage.calls == []
    assert summary.search_index is None


def test_index_stage_not_wired_in_is_skipped_with_its_reason(tmp_path: Path) -> None:
    record = search_index_record(run(tmp_path, search_index=None))

    assert record.outcome is StageOutcome.SKIPPED
    assert (
        record.reason
        == "no search index stage is wired in: an environment that names no evidence bucket has none"
    )


def test_index_stage_a_dry_run_says_what_it_would_do_and_asks_nothing(tmp_path: Path) -> None:
    stage = RecordingIndexStage()

    record = search_index_record(run(tmp_path, search_index=stage, dry_run=True))

    assert record.outcome is StageOutcome.PLANNED
    assert "would rebuild the search index if the parsed store changed" in (record.reason or "")
    assert stage.calls == []


# ------------------------------------------------------------------------------------------------
# What the run records of a pending publish and of a failure
# ------------------------------------------------------------------------------------------------


def test_index_stage_pending_publish_makes_the_run_publish_pending_and_the_login_banner_names_it(
    tmp_path: Path,
) -> None:
    pending = SearchIndexStageReport(
        outcome=StageOutcome.PENDING,
        reason=f"built {INDEX_ID}; built, publish pending, for want of an AWS login",
        counts=COUNTS,
        local_copy_only="the AWS session has expired",
    )

    summary = run(tmp_path, search_index=RecordingIndexStage(pending))
    record = record_for_summary(summary, environment="dev", mode="run")
    details = details_for_summary(summary)
    banners = notifications_for(record, details, aws_login_command=LOGIN, credentials_expired=True)

    assert summary.succeeded
    assert record.outcome is SyncRunOutcome.PUBLISH_PENDING
    assert summary.suppression_list_local_copy_only == "the AWS session has expired"
    assert details.search_index is not None and details.search_index.index_id == INDEX_ID
    [login] = [one for one in banners if one.title == "caselist publish waiting for an AWS login"]
    assert f"The search index {INDEX_ID} waits too" in login.message
    assert (
        "after the login: DEBATE_ENV=dev debate-research tub index publish --env dev --newest"
        in login.message
    )


def test_index_stage_failure_is_recorded_with_its_code_and_the_index_still_current_and_notified(
    tmp_path: Path,
) -> None:
    failed = SearchIndexStageReport(
        outcome=StageOutcome.FAILED,
        reason=f"the index was not built; the newest index on this machine stays {INDEX_ID}",
        failure=SearchIndexStoreNotReady(OPENEV_STORE, "its occurrence table holds no rows"),
        hint="a synthetic fix",
    )

    summary = run(tmp_path, search_index=RecordingIndexStage(failed))
    stage = search_index_record(summary)
    record = record_for_summary(summary, environment="dev", mode="run")
    details = details_for_summary(summary)
    banners = notifications_for(record, details, aws_login_command=LOGIN, credentials_expired=False)

    assert summary.succeeded, "a failed search index stage does not fail a run whose bytes are safe"
    assert summary.failure_codes == ()
    assert stage.outcome is StageOutcome.FAILED
    assert stage.error_codes == ("SEARCH_INDEX_STORE_NOT_READY",)
    assert stage.reason == (
        f"the index was not built; the newest index on this machine stays {INDEX_ID}; "
        "the parsed store of openev cannot be indexed: its occurrence table holds no rows"
    )
    assert stage.hint == "a synthetic fix"
    assert record.outcome is SyncRunOutcome.INCOMPLETE
    [entry] = [one for one in record.stages if one.stage == "search_index"]
    assert entry.reason == stage.reason, "an index id and a store name are nothing a record redacts"
    [banner] = banners
    assert banner.title == "caselist pull finished with a failed stage"
    assert "the search_index stage failed on SEARCH_INDEX_STORE_NOT_READY" in banner.message
    assert banner.hint == "a synthetic fix"


def test_index_stage_refused_by_the_shrink_guard_is_named_in_the_summary_details_and_notification(
    tmp_path: Path,
) -> None:
    """The report the stage gives for a refused shrink (`v1-e39-t14`), as the run records and announces it."""
    previous = "fedcba9876543210"
    shrink = StoreShrink(OPENEV_STORE, 0, 5_846)
    counts = replace(
        COUNTS,
        previous_index_id=previous,
        documents_growth=-5_846,
        sqlite_bytes_growth=-90_000,
        gzip_bytes_growth=-30_000,
    )
    refused = SearchIndexStageReport(
        outcome=StageOutcome.FAILED,
        reason=f"built {INDEX_ID}; not published, current.json still names {previous}",
        counts=counts,
        failure=SearchIndexWouldShrink(INDEX_ID, previous, (shrink,), 90),
        hint="a synthetic fix naming --allow-shrink",
    )

    summary = run(tmp_path, search_index=RecordingIndexStage(refused))
    stage = search_index_record(summary)
    record = record_for_summary(summary, environment="dev", mode="run")
    details = details_for_summary(summary)
    banners = notifications_for(record, details, aws_login_command=LOGIN, credentials_expired=False)

    assert stage.outcome is StageOutcome.FAILED
    assert stage.error_codes == ("SEARCH_INDEX_WOULD_SHRINK",)
    assert stage.reason is not None
    assert f"openev has 0 documents against 5,846 in index {previous}" in stage.reason
    assert f"current.json still names {previous}" in stage.reason
    assert summary.as_json()["search_index"]["documents_growth"] == -5_846  # pyright: ignore[reportIndexIssue]
    assert details.search_index is not None
    assert (details.search_index.previous_index_id, details.search_index.documents_growth) == (
        previous,
        -5_846,
    )
    [banner] = banners
    assert "the search_index stage failed on SEARCH_INDEX_WOULD_SHRINK" in banner.message
    assert banner.hint == "a synthetic fix naming --allow-shrink"


def test_index_stage_what_its_build_left_out_as_no_card_is_in_the_summary_and_details(tmp_path: Path) -> None:
    """The counts `v1-e39-t12`'s rule left out, as the run records them: the summary and the details."""
    not_cards = {
        SYNTHETIC_CASELIST: {"cite_only": 7, "no_cite_few_words": 2},
        OPENEV_STORE: {"cite_only": 1, "no_cite_few_words": 0},
    }
    built = SearchIndexStageReport(
        outcome=StageOutcome.COMPLETED,
        reason=f"built {INDEX_ID}; published",
        counts=replace(COUNTS, not_cards_by_store=not_cards),
    )

    summary = run(tmp_path, search_index=RecordingIndexStage(built))
    details = details_for_summary(summary)

    assert summary.as_json()["search_index"]["not_cards_by_store"] == not_cards  # pyright: ignore[reportIndexIssue]
    assert details.search_index is not None
    assert details.search_index.not_cards_by_store == not_cards


def test_index_stage_that_raises_is_its_own_failure_and_the_run_goes_on(tmp_path: Path) -> None:
    summary = run(tmp_path, search_index=RecordingIndexStage(raises=RuntimeError("a synthetic bug")))

    stage = search_index_record(summary)
    assert stage.outcome is StageOutcome.FAILED
    assert stage.error_codes == ("INTERNAL_ERROR",)
    assert "a synthetic bug" not in (stage.reason or ""), "a bug's message is not this project's to repeat"
    assert stage_names(summary)[-3:] == ["landscape", "report", "retention"]
    assert summary.succeeded


@pytest.mark.parametrize("outcome", [StageOutcome.COMPLETED, StageOutcome.SKIPPED])
def test_index_stage_that_did_its_work_leaves_the_runs_outcome_alone(
    tmp_path: Path, outcome: StageOutcome
) -> None:
    report = SearchIndexStageReport(outcome=outcome, reason="unchanged", counts=COUNTS)

    summary = run(tmp_path, search_index=RecordingIndexStage(report))

    assert record_for_summary(summary, environment="dev", mode="run").outcome is SyncRunOutcome.NOTHING_NEW


def test_index_stage_turned_off_by_setting_is_skipped_with_the_settings_name_and_never_absent(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "evidence"
    database = SqliteDatabase.open(data_dir)
    repository = SqliteCaselistRepository(database)
    blobs = FsSnapshotStore(data_dir)
    service = CaselistSyncService(
        source=FakeSource(),
        archive_importer=CaselistImportService(
            suppression=empty_suppression_list(), caselists=repository, blobs=blobs
        ),
        openev_importer=OpenEvImportService(
            suppression=empty_suppression_list(), caselists=repository, blobs=blobs
        ),
        local=local_evidence(data_dir),
        read_archive=lambda path: read_archive(path, **_LIMITS),
        event_for_caselist=lambda slug: Event.LD if slug.startswith("testcl") else None,
        inbox=data_dir / "inbox",
        state_dir=data_dir,
        suppression=empty_suppression_list(),
        search_index_turned_off=True,
        clock=lambda: RUN_CLOCK,
    )

    for dry_run in (True, False):
        summary = asyncio.run(service.run([SYNTHETIC_CASELIST], dry_run=dry_run))
        record = search_index_record(summary)
        assert record.outcome is StageOutcome.SKIPPED
        assert (record.reason or "").startswith("turned off by setting (caselist.refresh_search_index)")
        [entry] = [
            one
            for one in record_for_summary(summary, environment="dev", mode="run").stages
            if one.stage == "search_index"
        ]
        assert entry.reason == record.reason, "caselist runs reads the stage from the record"
