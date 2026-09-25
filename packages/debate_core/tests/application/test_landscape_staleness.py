"""The stale-data banner a landscape report carries when its caselist has stopped refreshing (ac3).

The landscape report itself is `v1-e32-t03`'s and does not exist yet, so the report here is a
stand-in: a few lines of Markdown and a CSV header block, the shape that task's spec describes.
What is under test is the hook — whether the banner goes on, what it says, and that nothing else
about the report changes. The dates are chosen by hand around the eight-day threshold.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from debate_core.application.caselist_sync import (
    ArchiveSelection,
    RunSummary,
    SelectionDecision,
    StageOutcome,
    StageRecord,
    SyncStage,
)
from debate_core.application.landscape_staleness import (
    STALE_BANNER_HEADING,
    LandscapeStalenessCheck,
    assess_staleness,
    with_stale_banner,
    with_staleness_metadata,
)
from debate_core.application.ports.caselist_source import ArchiveKind
from debate_core.application.sync_runs import SYNC_RUN_LOG_FILENAME, SyncRunLog, record_for_summary
from debate_core.integrations.local import FsEvidenceObjectStore

pytestmark = pytest.mark.anyio

CASELIST = "hsld26"
NEWEST = date(2026, 9, 15)

STAND_IN_REPORT = "# Argument landscape: hsld26\n\n## Positions\n\n| Position | Rounds |\n|---|---|\n"
STAND_IN_METADATA = {"caselist": CASELIST, "snapshot": NEWEST.isoformat(), "taxonomy_version": "1"}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def objects(tmp_path: Path) -> FsEvidenceObjectStore:
    """A local store holding manifests for 2026-09-01, 09-08 and 09-15: the newest is 09-15."""
    store = FsEvidenceObjectStore(tmp_path)
    for day in (date(2026, 9, 1), date(2026, 9, 8), NEWEST):
        path = store.path_for(f"manifests/{CASELIST}/{day.isoformat()}.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"kind": "summary"}\n', encoding="utf-8")
    return store


def run_listing(started: datetime, *, deferred: int) -> RunSummary:
    """A run that listed hsld26 and left `deferred` newer weeklies to the daily cap."""
    return RunSummary(
        run_id=started.strftime("%Y%m%dT%H%M%SZ"),
        started_at=started,
        finished_at=started,
        dry_run=False,
        caselists=(CASELIST,),
        stages=tuple(StageRecord(stage=stage, outcome=StageOutcome.COMPLETED) for stage in SyncStage),
        archives=tuple(
            ArchiveSelection(
                caselist=CASELIST,
                name=f"{CASELIST}-weekly-2026-09-{22 + week}.zip",
                kind=ArchiveKind.WEEKLY,
                archive_date=date(2026, 9, 22 + week),
                decision=SelectionDecision.OVER_DAILY_BUDGET,
            )
            for week in range(deferred)
        )
        or (
            ArchiveSelection(
                caselist=CASELIST,
                name=f"{CASELIST}-weekly-{NEWEST.isoformat()}.zip",
                kind=ArchiveKind.WEEKLY,
                archive_date=NEWEST,
                decision=SelectionDecision.ALREADY_IMPORTED,
            ),
        ),
    )


# ------------------------------------------------------------------------------------------------
# The boundary: nine days is stale, seven is not
# ------------------------------------------------------------------------------------------------


async def test_a_report_nine_days_after_the_newest_snapshot_starts_with_the_banner(
    objects: FsEvidenceObjectStore,
) -> None:
    check = LandscapeStalenessCheck(objects=objects, run_log=None)

    staleness = await check.check(CASELIST, report_date=NEWEST + timedelta(days=9))
    report = with_stale_banner(STAND_IN_REPORT, staleness)
    metadata = with_staleness_metadata(STAND_IN_METADATA, staleness)

    first_line = report.splitlines()[0]
    assert first_line.startswith(STALE_BANNER_HEADING)
    assert "2026-09-15" in first_line
    assert "9 day(s)" in first_line
    assert metadata["stale"] == "true"
    assert report.endswith(STAND_IN_REPORT), "the report's own content is unchanged"
    assert {key: metadata[key] for key in STAND_IN_METADATA} == STAND_IN_METADATA


async def test_a_report_seven_days_after_the_newest_snapshot_has_no_banner(
    objects: FsEvidenceObjectStore,
) -> None:
    check = LandscapeStalenessCheck(objects=objects, run_log=None)

    staleness = await check.check(CASELIST, report_date=NEWEST + timedelta(days=7))

    assert with_stale_banner(STAND_IN_REPORT, staleness) == STAND_IN_REPORT
    assert with_staleness_metadata(STAND_IN_METADATA, staleness)["stale"] == "false"


def test_eight_days_is_the_last_day_that_is_not_stale() -> None:
    """ "More than eight days older": eight is current, nine is not."""
    at_eight = assess_staleness(CASELIST, report_date=NEWEST + timedelta(days=8), newest_snapshot=NEWEST)
    at_nine = assess_staleness(CASELIST, report_date=NEWEST + timedelta(days=9), newest_snapshot=NEWEST)

    assert not at_eight.stale
    assert at_nine.stale


def test_the_threshold_is_configurable() -> None:
    staleness = assess_staleness(
        CASELIST, report_date=NEWEST + timedelta(days=4), newest_snapshot=NEWEST, stale_after_days=3
    )

    assert staleness.stale


async def test_a_caselist_with_no_snapshot_at_all_is_stale(tmp_path: Path) -> None:
    check = LandscapeStalenessCheck(objects=FsEvidenceObjectStore(tmp_path / "empty"), run_log=None)

    staleness = await check.check(CASELIST, report_date=NEWEST)

    assert staleness.stale
    assert "No snapshot of hsld26" in (staleness.banner() or "")
    assert staleness.csv_metadata()["newest_snapshot"] == ""


# ------------------------------------------------------------------------------------------------
# A run the daily cap held back is not current (ac6)
# ------------------------------------------------------------------------------------------------


async def test_a_cap_bound_run_makes_a_fresh_snapshot_stale(
    objects: FsEvidenceObjectStore, tmp_path: Path
) -> None:
    """Two days old would be current — but the last run left two newer weeklies to the cap."""
    log = SyncRunLog(tmp_path / SYNC_RUN_LOG_FILENAME)
    log.append(
        record_for_summary(
            run_listing(datetime(2026, 9, 16, 6, tzinfo=UTC), deferred=2), environment="dev", mode="run"
        )
    )
    check = LandscapeStalenessCheck(objects=objects, run_log=log)

    staleness = await check.check(CASELIST, report_date=NEWEST + timedelta(days=2))

    assert not staleness.too_old
    assert staleness.cap_bound
    assert staleness.stale
    banner = staleness.banner() or ""
    assert "2 newer weekly archive(s) are published but not yet downloaded" in banner
    assert staleness.csv_metadata()["archives_awaiting_download"] == "2"


async def test_a_later_run_that_fetched_the_backlog_makes_it_current_again(
    objects: FsEvidenceObjectStore, tmp_path: Path
) -> None:
    log = SyncRunLog(tmp_path / SYNC_RUN_LOG_FILENAME)
    earlier = record_for_summary(
        run_listing(datetime(2026, 9, 16, 6, tzinfo=UTC), deferred=2), environment="dev", mode="run"
    )
    log.append(earlier)
    log.append(
        record_for_summary(
            run_listing(datetime(2026, 9, 17, 6, tzinfo=UTC), deferred=0),
            environment="dev",
            mode="run",
            previous=[earlier],
        )
    )
    check = LandscapeStalenessCheck(objects=objects, run_log=log)

    staleness = await check.check(CASELIST, report_date=NEWEST + timedelta(days=2))

    assert not staleness.stale
