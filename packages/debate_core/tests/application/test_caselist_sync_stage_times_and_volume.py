"""When each stage of a weekly run started and ended, and the data volume's 70% warning (`v1-e40-t03`).

ADR-0020 could not time a run's stages from what a run left behind, and the cloud run works in a
fixed ephemeral volume the season's corpus grows into. So the summary and the run's details carry
each stage's start and end, and a run under `storage.volume_warning_percent` says in its summary
when the data directory's volume passed it. The record's own fields do not change: every installed
build reads it (`test_pull_run_record_is_read_by_every_build.py`).

The run is the real :class:`~debate_core.application.caselist_sync.CaselistSyncService` over a fake
OpenCaselist source that lists nothing new, with a search index stage stub that moves the run's
clock and the volume. The volume is a stub: no test reads this machine's disk. Every expected
value below is written by hand from the stubs' numbers.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final, cast

import pytest
from tests.fixtures.caselist.build_synthetic_archives import SYNTHETIC_CASELIST

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.import_service import CaselistImportService
from debate_core.application.caselist.openev_import_service import OpenEvImportService
from debate_core.application.caselist_sync import (
    CaselistSyncService,
    DataVolumeUsage,
    RunSummary,
    SearchIndexStageReport,
    StageOutcome,
    SyncStage,
    VolumeReading,
    read_volume,
)
from debate_core.application.ports.caselist_source import (
    ArchiveListing,
    CaselistInfo,
    DownloadedFile,
    OpenEvFile,
)
from debate_core.application.sync_runs import (
    SyncRunDetails,
    SyncRunRecord,
    details_for_summary,
    record_for_summary,
)
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsEvidenceObjectStore, FsSnapshotStore, SqliteDatabase
from debate_core.integrations.local.archive_reader import read_archive
from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository
from debate_core.testing.fakes.suppression import empty_suppression_list

RUN_START: Final = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
GIB: Final = 1024**3
VOLUME: Final = 100 * GIB
"""The cloud task's ephemeral volume: 100 GiB (ADR-0020 (1) 2)."""

#: Every stage a whole run carries out, in the run's order.
EVERY_STAGE: Final = [
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


class Clock:
    """The run's clock: still unless a stage moves it."""

    def __init__(self) -> None:
        self.now = RUN_START

    def __call__(self) -> datetime:
        return self.now


class Volume:
    """The data directory's volume: 100 GiB, `used` bytes of it used, every reading kept."""

    def __init__(self, used: int) -> None:
        self.used = used
        self.read_from: list[Path] = []

    def __call__(self, directory: Path) -> VolumeReading:
        self.read_from.append(directory)
        return VolumeReading(total_bytes=VOLUME, used_bytes=self.used)


class NothingNewSource:
    """OpenCaselist listing one caselist with no archive and no camp file."""

    async def list_caselists(self, *, archived: bool | None = None) -> list[CaselistInfo]:
        return [CaselistInfo(slug=SYNTHETIC_CASELIST)]

    async def get_caselist(self, caselist: str) -> CaselistInfo:
        return CaselistInfo(slug=caselist)

    async def list_archives(self, caselist: str) -> list[ArchiveListing]:
        return []

    async def list_openev(self, *, year: int | None = None) -> list[OpenEvFile]:
        return []

    async def download_archive(
        self, archive: ArchiveListing, inbox: Path
    ) -> DownloadedFile:  # pragma: no cover
        raise AssertionError("nothing is listed")

    async def download_openev(self, file: OpenEvFile, inbox: Path) -> DownloadedFile:  # pragma: no cover
        raise AssertionError("nothing is listed")


class SlowGrowingIndexStage:
    """The search index stage: takes `minutes` by the run's clock and fills the volume to `used_after`."""

    def __init__(
        self, clock: Clock, *, minutes: int, volume: Volume | None = None, used_after: int = 0
    ) -> None:
        self.clock = clock
        self.minutes = minutes
        self.volume = volume
        self.used_after = used_after

    async def refresh(self, stores: Sequence[str], *, no_session: str | None) -> SearchIndexStageReport:
        self.clock.now += timedelta(minutes=self.minutes)
        if self.volume is not None:
            self.volume.used = self.used_after
        return SearchIndexStageReport(outcome=StageOutcome.SKIPPED, reason="the parsed store has not changed")


def service(
    tmp_path: Path,
    clock: Clock,
    *,
    search_index: SlowGrowingIndexStage | None = None,
    volume_warning_percent: int | None = None,
    volume: Callable[[Path], VolumeReading] = read_volume,
) -> CaselistSyncService:
    data_dir = tmp_path / "evidence"
    database = SqliteDatabase.open(data_dir)
    repository = SqliteCaselistRepository(database)
    blobs = FsSnapshotStore(data_dir)
    objects = FsEvidenceObjectStore(data_dir)
    raw = FsEvidenceObjectStore(data_dir, subdirectory=Path("blobs"))
    return CaselistSyncService(
        source=NothingNewSource(),
        archive_importer=CaselistImportService(
            suppression=empty_suppression_list(), caselists=repository, blobs=blobs
        ),
        openev_importer=OpenEvImportService(
            suppression=empty_suppression_list(), caselists=repository, blobs=blobs
        ),
        local=LocalEvidence(
            objects=objects, blobs=raw, object_path_for=objects.path_for, blob_path_for=raw.path_for
        ),
        read_archive=lambda path: read_archive(path, max_archive_bytes=1024, max_unpacked_bytes=1024),
        event_for_caselist=lambda slug: Event.LD,
        inbox=data_dir / "inbox",
        state_dir=data_dir,
        suppression=empty_suppression_list(),
        search_index=search_index,
        clock=clock,
        volume_warning_percent=volume_warning_percent,
        read_volume=volume,
    )


def data_volume_json(summary: RunSummary) -> dict[str, object]:
    """The summary's `data_volume` object, as `caselist pull --json` prints it."""
    body = summary.as_json()["data_volume"]
    assert isinstance(body, dict)
    return cast("dict[str, object]", body)


def times(summary: RunSummary) -> list[tuple[str, datetime, datetime]]:
    return [(str(one.stage), one.started_at, one.finished_at) for one in summary.stage_times]


# ------------------------------------------------------------------------------------------------
# Each stage's start and end
# ------------------------------------------------------------------------------------------------


def test_a_whole_run_times_every_stage_it_carries_out_in_its_order(tmp_path: Path) -> None:
    clock = Clock()
    seven_minutes_later = RUN_START + timedelta(minutes=7)

    summary = asyncio.run(
        service(tmp_path, clock, search_index=SlowGrowingIndexStage(clock, minutes=7)).run(
            [SYNTHETIC_CASELIST]
        )
    )

    before_the_index = [(stage, RUN_START, RUN_START) for stage in EVERY_STAGE[:5]]
    the_index = [("search_index", RUN_START, seven_minutes_later)]
    after_it = [(stage, seven_minutes_later, seven_minutes_later) for stage in EVERY_STAGE[6:]]
    assert times(summary) == before_the_index + the_index + after_it
    assert (summary.started_at, summary.finished_at) == (RUN_START, seven_minutes_later)
    assert summary.stage_times[5].as_json() == {
        "stage": "search_index",
        "started_at": "2026-11-04T12:00:00+00:00",
        "finished_at": "2026-11-04T12:07:00+00:00",
        "duration_seconds": 420.0,
    }


def test_a_dry_run_times_only_the_stages_it_carries_out_and_none_it_only_planned(tmp_path: Path) -> None:
    summary = asyncio.run(service(tmp_path, Clock()).run([SYNTHETIC_CASELIST], dry_run=True))

    assert [stage for stage, _, _ in times(summary)] == ["select", "retention"]
    assert {str(one.stage): str(one.outcome) for one in summary.stages}["download"] == "planned"


def test_publish_pending_times_its_publish_and_its_report(tmp_path: Path) -> None:
    summary = asyncio.run(service(tmp_path, Clock()).publish_pending())

    assert [stage for stage, _, _ in times(summary)] == ["publish", "report"]


def test_the_runs_details_keep_each_stages_times_and_the_record_gains_no_field(tmp_path: Path) -> None:
    clock = Clock()
    summary = asyncio.run(
        service(tmp_path, clock, search_index=SlowGrowingIndexStage(clock, minutes=7)).run(
            [SYNTHETIC_CASELIST]
        )
    )

    details = SyncRunDetails.model_validate_json(details_for_summary(summary).model_dump_json())
    assert [(one.stage, one.started_at, one.finished_at) for one in details.stage_times] == times(summary)
    assert details.data_volume is None, "no volume is read unless the setting asks"

    record = record_for_summary(summary, environment="dev", mode="run")
    # The record's fields as every installed build reads them (`v1-e34-t19`), written out by hand.
    assert set(record.model_dump()) == {
        "schema_version", "run_id", "environment", "mode", "started_at", "finished_at", "outcome",
        "caselists", "archives_seen", "archives_wanted", "archives_downloaded", "archives_deferred",
        "deferred_by_caselist", "backlog_carried", "backlog_growing", "openev_downloaded",
        "files_imported", "snapshots_imported", "objects_published", "pending_publish", "stages",
        "error_class", "error_message",
    }  # fmt: skip
    assert set(SyncRunRecord.model_fields) == set(record.model_dump())


def test_details_written_before_stage_times_existed_read_as_none_recorded() -> None:
    older = SyncRunDetails.model_validate_json('{"schema_version": 1, "run_id": "20261021T110000Z"}')

    assert (older.stage_times, older.data_volume) == ((), None)


# ------------------------------------------------------------------------------------------------
# The data volume's warning
# ------------------------------------------------------------------------------------------------


def test_a_run_whose_volume_passes_seventy_percent_says_so_in_its_summary(tmp_path: Path) -> None:
    clock = Clock()
    volume = Volume(used=40 * GIB)
    index = SlowGrowingIndexStage(clock, minutes=1, volume=volume, used_after=75 * GIB)

    summary = asyncio.run(
        service(tmp_path, clock, search_index=index, volume_warning_percent=70, volume=volume).run(
            [SYNTHETIC_CASELIST]
        )
    )

    assert summary.data_volume == DataVolumeUsage(
        total_bytes=VOLUME, peak_used_bytes=75 * GIB, peak_after=SyncStage.SEARCH_INDEX, warning_percent=70
    )
    assert data_volume_json(summary) == {
        "total_bytes": 107374182400,
        "peak_used_bytes": 80530636800,
        "peak_percent": 75.0,
        "peak_after": "search_index",
        "warning_percent": 70,
        "warning": "the data volume was 75.0% used after the search_index stage, past the 70% warning: "
        "enlarge it before a run fills it",
    }
    assert len(volume.read_from) == len(EVERY_STAGE), "read once after each stage"
    assert set(volume.read_from) == {tmp_path / "evidence"}, "the data directory's volume"
    details = details_for_summary(summary)
    assert details.data_volume is not None
    assert details.data_volume.warning == data_volume_json(summary)["warning"]


def test_the_fullest_reading_is_kept_when_the_volume_empties_again(tmp_path: Path) -> None:
    clock = Clock()
    volume = Volume(used=80 * GIB)
    # The index stage frees space; the peak is still the 80% the earlier stages saw.
    index = SlowGrowingIndexStage(clock, minutes=1, volume=volume, used_after=10 * GIB)

    summary = asyncio.run(
        service(tmp_path, clock, search_index=index, volume_warning_percent=70, volume=volume).run(
            [SYNTHETIC_CASELIST]
        )
    )

    assert summary.data_volume is not None
    assert (summary.data_volume.peak_used_bytes, summary.data_volume.peak_after) == (
        80 * GIB,
        SyncStage.SELECT,
    )
    assert summary.data_volume.warning is not None


def test_exactly_seventy_percent_has_not_passed_seventy(tmp_path: Path) -> None:
    volume = Volume(used=70 * GIB)

    summary = asyncio.run(
        service(tmp_path, Clock(), volume_warning_percent=70, volume=volume).run([SYNTHETIC_CASELIST])
    )

    assert summary.data_volume is not None
    assert summary.data_volume.peak_percent == 70.0
    assert summary.data_volume.warning is None
    assert data_volume_json(summary)["warning"] is None


def test_one_byte_past_seventy_percent_has_passed_it(tmp_path: Path) -> None:
    volume = Volume(used=70 * GIB + 1)

    summary = asyncio.run(
        service(tmp_path, Clock(), volume_warning_percent=70, volume=volume).run([SYNTHETIC_CASELIST])
    )

    assert summary.data_volume is not None
    assert summary.data_volume.passed_warning


def test_without_the_setting_no_volume_is_read(tmp_path: Path) -> None:
    def must_not_be_read(directory: Path) -> VolumeReading:
        raise AssertionError("the volume was read with storage.volume_warning_percent unset")

    summary = asyncio.run(service(tmp_path, Clock(), volume=must_not_be_read).run([SYNTHETIC_CASELIST]))

    assert summary.data_volume is None
    assert summary.as_json()["data_volume"] is None


def test_a_volume_that_cannot_be_read_costs_the_reading_and_never_a_stage(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def unreadable(directory: Path) -> VolumeReading:
        raise PermissionError(13, "Permission denied", str(directory))

    with caplog.at_level(logging.WARNING, logger="debate_core.application.caselist_sync"):
        summary = asyncio.run(
            service(tmp_path, Clock(), volume_warning_percent=70, volume=unreadable).run([SYNTHETIC_CASELIST])
        )

    assert summary.data_volume is None
    assert summary.succeeded
    assert [str(one.stage) for one in summary.stage_times] == EVERY_STAGE
    warnings = [record.getMessage() for record in caplog.records if "data volume" in record.getMessage()]
    assert warnings[0] == "Could not read the data volume after the select stage (PermissionError)"
    assert not any(str(tmp_path) in message for message in warnings), "no path on this machine"
