"""The stale-data banner a landscape report carries when its caselist has stopped refreshing (ac3).

The landscape report itself is `v1-e32-t03`'s and does not exist yet, so the report here is a
stand-in: a few lines of Markdown and a CSV header block, the shape that task's spec describes.
What is under test is the hook — whether the banner goes on, what it says, and that nothing else
about the report changes. The dates are chosen by hand around the eight-day threshold.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from debate_core.application.caselist.recent_run import RecentRunRecorded
from debate_core.application.caselist.run_lock import (
    LockBody,
    LockHolder,
    LockState,
    RunHomeMoved,
    RunLockHeld,
    RunLockLost,
    RunLockWrongHome,
    RunTerminated,
)
from debate_core.application.caselist_sync import (
    ArchiveSelection,
    RunSummary,
    SelectionDecision,
    StageOutcome,
    StageRecord,
    SyncRunInProgress,
    SyncStage,
)
from debate_core.application.landscape_staleness import (
    LOCK_REFUSALS,
    STALE_BANNER_HEADING,
    FailedSyncRun,
    LandscapeStalenessCheck,
    assess_staleness,
    with_stale_banner,
    with_staleness_metadata,
)
from debate_core.application.ports.caselist_source import ArchiveKind, CaselistAuthExpired
from debate_core.application.sync_runs import (
    SYNC_RUN_LOG_FILENAME,
    RunMode,
    StageEntry,
    SyncRunLog,
    SyncRunOutcome,
    SyncRunRecord,
    record_for_failure,
    record_for_summary,
)
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


# ------------------------------------------------------------------------------------------------
# A run that failed is not current (`v1-e34-t32`)
# ------------------------------------------------------------------------------------------------

OTHER_CASELIST = "hspolicy26"
FAILED_RUN_ID = "20260916T060000Z"

SCHOOL_LIKE = "Harrowgate Prep"
"""Fictional, like every school in the synthetic fixtures."""

PATH_LIKE = "Harrowgate/HaPX/Harrowgate-HaPX-Aff-Thistle-Open-Round1.docx"
"""A disclosure's path has exactly this shape: school, team code, file name."""


def run_of(
    started: datetime,
    *,
    caselists: tuple[str, ...] = (CASELIST,),
    failed: tuple[SyncStage, ...] = (),
    deferred: int = 0,
    failed_reason: str = "1 fetched, then: OpenCaselist did not answer",
) -> RunSummary:
    """A run that listed `caselists`, with each stage in `failed` failed and the rest completed.

    The stage names are `SyncStage`'s own, the ones the record writes.
    """
    return RunSummary(
        run_id=started.strftime("%Y%m%dT%H%M%SZ"),
        started_at=started,
        finished_at=started + timedelta(minutes=4),
        dry_run=False,
        caselists=caselists,
        stages=tuple(
            StageRecord(stage=stage, outcome=StageOutcome.FAILED, reason=failed_reason)
            if stage in failed
            else StageRecord(stage=stage, outcome=StageOutcome.COMPLETED)
            for stage in SyncStage
        ),
        archives=tuple(
            ArchiveSelection(
                caselist=caselist,
                name=f"{caselist}-weekly-2026-09-{22 + week}.zip",
                kind=ArchiveKind.WEEKLY,
                archive_date=date(2026, 9, 22 + week),
                decision=SelectionDecision.OVER_DAILY_BUDGET,
            )
            for caselist in caselists
            for week in range(deferred)
        )
        or tuple(
            ArchiveSelection(
                caselist=caselist,
                name=f"{caselist}-weekly-{NEWEST.isoformat()}.zip",
                kind=ArchiveKind.WEEKLY,
                archive_date=NEWEST,
                decision=SelectionDecision.ALREADY_IMPORTED,
            )
            for caselist in caselists
        ),
    )


def log_of(tmp_path: Path, *runs: RunSummary, mode: RunMode = "run") -> SyncRunLog:
    """A run log holding `runs`, oldest first, each recorded the way the monitor records it."""
    log = SyncRunLog(tmp_path / SYNC_RUN_LOG_FILENAME)
    for run in runs:
        log.append(record_for_summary(run, environment="dev", mode=mode, previous=log.read()))
    return log


SEPTEMBER_16 = datetime(2026, 9, 16, 6, tzinfo=UTC)
SEPTEMBER_17 = datetime(2026, 9, 17, 6, tzinfo=UTC)
FRESH = NEWEST + timedelta(days=2)
"""Two days after the newest snapshot: current by its age alone."""


async def test_a_failed_latest_run_makes_a_fresh_snapshot_stale_naming_the_run_and_its_stage(
    objects: FsEvidenceObjectStore, tmp_path: Path
) -> None:
    log = log_of(tmp_path, run_of(SEPTEMBER_16, failed=(SyncStage.DOWNLOAD,)))
    check = LandscapeStalenessCheck(objects=objects, run_log=log)

    staleness = await check.check(CASELIST, report_date=FRESH)

    assert not staleness.too_old
    assert not staleness.cap_bound
    assert staleness.latest_run_failed
    assert staleness.stale
    assert staleness.failed_run == FailedSyncRun(run_id=FAILED_RUN_ID, stages=("download",))
    banner = staleness.banner() or ""
    assert banner.startswith(STALE_BANNER_HEADING)
    assert f"The latest sync run of this caselist, {FAILED_RUN_ID}, failed at its download stage." in banner
    assert with_staleness_metadata(STAND_IN_METADATA, staleness)["stale"] == "true"


async def test_a_later_successful_run_makes_it_current_again(
    objects: FsEvidenceObjectStore, tmp_path: Path
) -> None:
    log = log_of(tmp_path, run_of(SEPTEMBER_16, failed=(SyncStage.DOWNLOAD,)), run_of(SEPTEMBER_17))
    check = LandscapeStalenessCheck(objects=objects, run_log=log)

    staleness = await check.check(CASELIST, report_date=FRESH)

    assert staleness.failed_run is None
    assert not staleness.stale
    assert with_stale_banner(STAND_IN_REPORT, staleness) == STAND_IN_REPORT
    assert with_staleness_metadata(STAND_IN_METADATA, staleness)["stale"] == "false"


async def test_a_failed_run_of_another_caselist_does_not_make_this_one_stale(
    objects: FsEvidenceObjectStore, tmp_path: Path
) -> None:
    log = log_of(
        tmp_path,
        run_of(SEPTEMBER_16),
        run_of(SEPTEMBER_17, caselists=(OTHER_CASELIST,), failed=(SyncStage.DOWNLOAD,)),
    )
    check = LandscapeStalenessCheck(objects=objects, run_log=log)

    staleness = await check.check(CASELIST, report_date=FRESH)

    assert not staleness.stale


async def test_a_successful_run_of_another_caselist_does_not_make_this_one_current(
    objects: FsEvidenceObjectStore, tmp_path: Path
) -> None:
    log = log_of(
        tmp_path,
        run_of(SEPTEMBER_16, failed=(SyncStage.IMPORT,)),
        run_of(SEPTEMBER_17, caselists=(OTHER_CASELIST,)),
    )
    check = LandscapeStalenessCheck(objects=objects, run_log=log)

    staleness = await check.check(CASELIST, report_date=FRESH)

    assert staleness.failed_run == FailedSyncRun(run_id=FAILED_RUN_ID, stages=("import",))


async def test_a_failed_run_of_both_caselists_makes_each_stale(
    objects: FsEvidenceObjectStore, tmp_path: Path
) -> None:
    """The record says the run failed, not which caselist's archive did: both read stale."""
    log = log_of(
        tmp_path, run_of(SEPTEMBER_16, caselists=(OTHER_CASELIST, CASELIST), failed=(SyncStage.PUBLISH,))
    )
    check = LandscapeStalenessCheck(objects=objects, run_log=log)

    assert (await check.check(CASELIST, report_date=FRESH)).latest_run_failed
    assert (await check.check(OTHER_CASELIST, report_date=FRESH)).latest_run_failed


async def test_a_run_that_failed_only_after_publishing_is_not_a_failed_run(
    objects: FsEvidenceObjectStore, tmp_path: Path
) -> None:
    """`incomplete`: the parse stage failed, and what the snapshot rule reads was captured."""
    log = log_of(tmp_path, run_of(SEPTEMBER_16, failed=(SyncStage.PARSE,)))
    check = LandscapeStalenessCheck(objects=objects, run_log=log)

    staleness = await check.check(CASELIST, report_date=FRESH)

    assert log.read()[0].outcome is SyncRunOutcome.INCOMPLETE
    assert not staleness.stale


STOPPED_RUN_ID = "20260917T060000Z"


def stopped(
    error: BaseException, *, caselists: tuple[str, ...] = (CASELIST,), started: datetime = SEPTEMBER_17
) -> SyncRunRecord:
    """A run that raised instead of returning a summary, recorded the way the monitor records it."""
    return record_for_failure(
        error,
        run_id=started.strftime("%Y%m%dT%H%M%SZ"),
        started_at=started,
        finished_at=started,
        environment="dev",
        mode="run",
        caselists=caselists,
    )


EXPIRED_TOKEN = CaselistAuthExpired(401, f"list archives for {CASELIST}")
"""The likeliest way a weekly run fails outright (policy E34 gate 5)."""


async def test_a_run_that_stopped_on_an_error_naming_the_caselist_makes_it_stale(
    objects: FsEvidenceObjectStore, tmp_path: Path
) -> None:
    """A run that raised listed no archive and has no stage: the reason names its error's class.

    The PM's ruling 1 of 2026-10-24. Before it, this run changed nothing.
    """
    log = log_of(tmp_path, run_of(SEPTEMBER_16))
    record = stopped(EXPIRED_TOKEN)
    log.append(record)
    check = LandscapeStalenessCheck(objects=objects, run_log=log)

    staleness = await check.check(CASELIST, report_date=FRESH)

    assert record.outcome is SyncRunOutcome.FAILED and not record.deferred_by_caselist and not record.stages
    assert not staleness.too_old and not staleness.cap_bound
    assert staleness.stale
    assert staleness.failed_run == FailedSyncRun(
        run_id=STOPPED_RUN_ID, stopped_before_stages=True, error_class="CaselistAuthExpired"
    )
    banner = staleness.banner() or ""
    assert (
        f"The latest sync run of this caselist, {STOPPED_RUN_ID}, stopped before its stages "
        "(CaselistAuthExpired)." in banner
    )
    assert "caselist_token" not in banner and "HTTP" not in banner, "the message is never read"


async def test_a_later_run_that_listed_the_caselist_clears_a_run_that_stopped(
    objects: FsEvidenceObjectStore, tmp_path: Path
) -> None:
    log = log_of(tmp_path, run_of(SEPTEMBER_16))
    log.append(stopped(EXPIRED_TOKEN))
    log.append(
        record_for_summary(
            run_of(datetime(2026, 9, 18, 6, tzinfo=UTC)), environment="dev", mode="run", previous=log.read()
        )
    )
    check = LandscapeStalenessCheck(objects=objects, run_log=log)

    staleness = await check.check(CASELIST, report_date=FRESH)

    assert staleness.failed_run is None
    assert not staleness.stale


# ------------------------------------------------------------------------------------------------
# A lock refusal is no run at all (`v1-e40-t38`)
# ------------------------------------------------------------------------------------------------
#
# A pull the run lock refused did nothing: another runner held the lock, the weekly run's home had
# moved, or the lock named another home. Its record says `failed` with the refusal's class and no
# stage, the shape of a run that stopped on an error, and until `v1-e40-t38` only the local lock's
# `SyncRunInProgress` was exempt. Every holder, run id, task and time below is invented.

INVENTED_LOCK_FILE = "invented-sync.lock"
INVENTED_HOLDER = LockHolder(
    kind="cloud", run_id="20260918T055500Z", command="caselist pull", task="invented-task-7f3e"
)
INVENTED_MOVE = LockBody(
    home_environment="prod",
    state=LockState.HELD,
    holder=LockHolder(
        kind="moved", run_id="20260910T120000Z", command="caselist move-run-home", by="mac", build="v0.0.0-x"
    ),
    acquired_at=datetime(2026, 9, 10, 12, tzinfo=UTC),
)


def lock_refusals(tmp_path: Path) -> dict[str, BaseException]:
    """One of each refusal of the run lock, by the class name its record carries."""
    refusals: list[BaseException] = [
        SyncRunInProgress(tmp_path / INVENTED_LOCK_FILE),
        RunLockHeld(holder=INVENTED_HOLDER, lease_expires_at=datetime(2026, 9, 18, 6, 25, tzinfo=UTC)),
        RunHomeMoved(body=INVENTED_MOVE, environment="dev"),
        RunLockWrongHome(home="prod", environment="dev"),
        # A scheduled pull refused before the lock after a recent run (`v1-e40-t44`, the PM's amendment of
        # 2026-11-07): it did nothing either.
        RecentRunRecorded(run_id="20260918T053000Z", started_at=datetime(2026, 9, 18, 5, 30, tzinfo=UTC)),
    ]
    return {type(refusal).__name__: refusal for refusal in refusals}


LOCK_REFUSAL_CLASSES = (
    "SyncRunInProgress",
    "RunLockHeld",
    "RunHomeMoved",
    "RunLockWrongHome",
    "RecentRunRecorded",
)


def test_the_lock_refusals_are_the_ones_parametrised_here() -> None:
    """Each refusal `LOCK_REFUSALS` passes over has its case below, and no other class is passed over."""
    assert frozenset(LOCK_REFUSAL_CLASSES) == LOCK_REFUSALS


REFUSED_AT = datetime(2026, 9, 18, 6, tzinfo=UTC)
"""After every run the tests below record: the refusal is the latest record."""


def refused(tmp_path: Path, refusal_class: str, *, started: datetime = REFUSED_AT) -> SyncRunRecord:
    """A pull the run lock refused, recorded the way the monitor records it (`record_for_failure`)."""
    record = stopped(lock_refusals(tmp_path)[refusal_class], started=started)
    assert record.error_class == refusal_class and not record.stages and not record.deferred_by_caselist
    return record


@pytest.mark.parametrize("refusal_class", LOCK_REFUSAL_CLASSES)
async def test_a_lock_refusal_after_a_completed_run_leaves_the_report_as_that_run_made_it(
    objects: FsEvidenceObjectStore, tmp_path: Path, refusal_class: str
) -> None:
    """Current stays current, and a backlog the completed run left to the cap stays counted."""
    current = log_of(tmp_path / "current", run_of(SEPTEMBER_16))
    cap_bound = log_of(tmp_path / "cap-bound", run_of(SEPTEMBER_16, deferred=2))
    for log in (current, cap_bound):
        log.append(refused(tmp_path, refusal_class))

    after_current = await LandscapeStalenessCheck(objects=objects, run_log=current).check(
        CASELIST, report_date=FRESH
    )
    after_cap_bound = await LandscapeStalenessCheck(objects=objects, run_log=cap_bound).check(
        CASELIST, report_date=FRESH
    )

    assert after_current.failed_run is None
    assert not after_current.stale
    assert with_stale_banner(STAND_IN_REPORT, after_current) == STAND_IN_REPORT
    assert with_staleness_metadata(STAND_IN_METADATA, after_current)["stale"] == "false"
    assert after_cap_bound.failed_run is None
    assert after_cap_bound.archives_awaiting_download == 2
    assert "stopped before its stages" not in (after_cap_bound.banner() or "")


@pytest.mark.parametrize("refusal_class", LOCK_REFUSAL_CLASSES)
async def test_a_lock_refusal_after_a_failed_run_leaves_it_failed(
    objects: FsEvidenceObjectStore, tmp_path: Path, refusal_class: str
) -> None:
    """The failed run is still the latest run that ran: its stage, or its error, is what the banner says."""
    at_a_stage = log_of(tmp_path / "at-a-stage", run_of(SEPTEMBER_16, failed=(SyncStage.DOWNLOAD,)))
    on_an_error = log_of(tmp_path / "on-an-error", run_of(SEPTEMBER_16))
    on_an_error.append(stopped(EXPIRED_TOKEN))
    for log in (at_a_stage, on_an_error):
        log.append(refused(tmp_path, refusal_class))

    after_stage = await LandscapeStalenessCheck(objects=objects, run_log=at_a_stage).check(
        CASELIST, report_date=FRESH
    )
    after_error = await LandscapeStalenessCheck(objects=objects, run_log=on_an_error).check(
        CASELIST, report_date=FRESH
    )

    assert after_stage.failed_run == FailedSyncRun(run_id=FAILED_RUN_ID, stages=("download",))
    assert after_error.failed_run == FailedSyncRun(
        run_id=STOPPED_RUN_ID, stopped_before_stages=True, error_class="CaselistAuthExpired"
    )
    for staleness in (after_stage, after_error):
        assert staleness.stale
        assert refusal_class not in (staleness.banner() or "")


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(RunLockLost(), id="RunLockLost"),
        pytest.param(RunTerminated(), id="RunTerminated"),
    ],
)
async def test_a_run_that_failed_after_it_started_still_reads_stopped(
    objects: FsEvidenceObjectStore, tmp_path: Path, error: BaseException
) -> None:
    """These runs held the lock and began: a lease lost mid-run, or a run told to stop. Not refusals.

    `RunLockLost` is the lock's own error and its record stays local, as a refusal's does; neither
    makes it a run that did nothing.
    """
    log = log_of(tmp_path, run_of(SEPTEMBER_16))
    log.append(stopped(error, started=REFUSED_AT))
    check = LandscapeStalenessCheck(objects=objects, run_log=log)

    staleness = await check.check(CASELIST, report_date=FRESH)

    name = type(error).__name__
    assert staleness.stale
    assert staleness.failed_run == FailedSyncRun(
        run_id="20260918T060000Z", stopped_before_stages=True, error_class=name
    )
    assert f"stopped before its stages ({name})." in (staleness.banner() or "")


async def test_a_log_holding_only_lock_refusals_reads_as_no_run(
    objects: FsEvidenceObjectStore, tmp_path: Path
) -> None:
    """Every refusal, one after another: the report is what it would be with no run log at all."""
    log = SyncRunLog(tmp_path / SYNC_RUN_LOG_FILENAME)
    for hour, refusal_class in enumerate(LOCK_REFUSAL_CLASSES):
        log.append(refused(tmp_path, refusal_class, started=REFUSED_AT + timedelta(hours=hour)))

    with_refusals = await LandscapeStalenessCheck(objects=objects, run_log=log).check(
        CASELIST, report_date=FRESH
    )
    without_a_log = await LandscapeStalenessCheck(objects=objects, run_log=None).check(
        CASELIST, report_date=FRESH
    )

    assert len(log.read()) == len(LOCK_REFUSAL_CLASSES)
    assert with_refusals == without_a_log
    assert with_refusals.failed_run is None
    assert not with_refusals.stale


async def test_refusals_after_a_failed_run_and_before_a_completed_one_change_nothing_either_way(
    objects: FsEvidenceObjectStore, tmp_path: Path
) -> None:
    """Several refusals in a row are passed over to the run before them, and a later run clears it."""
    log = log_of(tmp_path, run_of(SEPTEMBER_16, failed=(SyncStage.IMPORT,)))
    for hour, refusal_class in enumerate(LOCK_REFUSAL_CLASSES):
        log.append(refused(tmp_path, refusal_class, started=REFUSED_AT + timedelta(hours=hour)))
    check = LandscapeStalenessCheck(objects=objects, run_log=log)

    still_failed = await check.check(CASELIST, report_date=FRESH)
    log.append(
        record_for_summary(
            run_of(datetime(2026, 9, 19, 6, tzinfo=UTC)), environment="dev", mode="run", previous=log.read()
        )
    )
    cleared = await check.check(CASELIST, report_date=FRESH)

    assert still_failed.failed_run == FailedSyncRun(run_id=FAILED_RUN_ID, stages=("import",))
    assert cleared.failed_run is None and not cleared.stale


async def test_a_run_that_stopped_naming_another_caselist_changes_nothing(
    objects: FsEvidenceObjectStore, tmp_path: Path
) -> None:
    log = log_of(tmp_path, run_of(SEPTEMBER_16))
    log.append(stopped(EXPIRED_TOKEN, caselists=(OTHER_CASELIST,)))
    check = LandscapeStalenessCheck(objects=objects, run_log=log)

    assert not (await check.check(CASELIST, report_date=FRESH)).stale
    assert (await check.check(OTHER_CASELIST, report_date=FRESH)).failed_run == FailedSyncRun(
        run_id=STOPPED_RUN_ID, stopped_before_stages=True, error_class="CaselistAuthExpired"
    )


async def test_a_run_that_stopped_after_a_cap_bound_run_leaves_the_backlog_counted(
    objects: FsEvidenceObjectStore, tmp_path: Path
) -> None:
    """The cap-bound rule still reads the latest run that listed the caselist: a run that stopped
    before listing knows nothing of the backlog, so it neither clears it nor hides it. Both apply."""
    log = log_of(tmp_path, run_of(SEPTEMBER_16, deferred=2))
    log.append(stopped(EXPIRED_TOKEN))
    check = LandscapeStalenessCheck(objects=objects, run_log=log)

    staleness = await check.check(CASELIST, report_date=FRESH)
    banner = staleness.banner() or ""

    assert staleness.archives_awaiting_download == 2 and staleness.cap_bound
    assert staleness.latest_run_failed
    assert "2 newer weekly archive(s) are published but not yet downloaded" in banner
    assert "stopped before its stages (CaselistAuthExpired)." in banner


@pytest.mark.parametrize("error_class", [SCHOOL_LIKE, PATH_LIKE, "Expired-Token", "", "1Expired"])
async def test_an_error_class_that_is_not_an_identifier_is_left_out(
    objects: FsEvidenceObjectStore, tmp_path: Path, error_class: str
) -> None:
    """The class is a string in the log like any other; only an identifier is repeated, and the
    message, whatever it holds, never is."""
    log = log_of(tmp_path, run_of(SEPTEMBER_16))
    log.append(
        SyncRunRecord(
            run_id=STOPPED_RUN_ID,
            environment="dev",
            mode="run",
            started_at=SEPTEMBER_17,
            finished_at=SEPTEMBER_17,
            outcome=SyncRunOutcome.FAILED,
            caselists=(CASELIST,),
            error_class=error_class,
            error_message=f"{SCHOOL_LIKE}: {PATH_LIKE}",
        )
    )
    check = LandscapeStalenessCheck(objects=objects, run_log=log)

    staleness = await check.check(CASELIST, report_date=FRESH)
    said = (staleness.banner() or "") + json.dumps(staleness.csv_metadata())

    assert staleness.failed_run == FailedSyncRun(run_id=STOPPED_RUN_ID, stopped_before_stages=True)
    assert f"The latest sync run of this caselist, {STOPPED_RUN_ID}, stopped before its stages." in said
    for part in (SCHOOL_LIKE, "Harrowgate", "HaPX", PATH_LIKE, ".docx", "/", "Expired"):
        assert part not in said, part


async def test_the_class_is_named_and_the_message_is_not(
    objects: FsEvidenceObjectStore, tmp_path: Path
) -> None:
    log = log_of(tmp_path, run_of(SEPTEMBER_16))
    log.append(
        SyncRunRecord(
            run_id=STOPPED_RUN_ID,
            environment="dev",
            mode="run",
            started_at=SEPTEMBER_17,
            finished_at=SEPTEMBER_17,
            outcome=SyncRunOutcome.FAILED,
            caselists=(CASELIST,),
            error_class="ManifestsNotWritable",
            error_message=f"{SCHOOL_LIKE}: {PATH_LIKE}",
        )
    )
    check = LandscapeStalenessCheck(objects=objects, run_log=log)

    said = (await check.check(CASELIST, report_date=FRESH)).banner() or ""

    assert "stopped before its stages (ManifestsNotWritable)." in said
    for part in (SCHOOL_LIKE, "Harrowgate", PATH_LIKE, ".docx", "/"):
        assert part not in said, part


async def test_a_failed_publish_pending_run_changes_nothing(
    objects: FsEvidenceObjectStore, tmp_path: Path
) -> None:
    """`caselist pull --publish-pending` lists no archive: neither its failure nor its success counts."""
    after_success = log_of(tmp_path / "after-success", run_of(SEPTEMBER_16))
    after_failure = log_of(tmp_path / "after-failure", run_of(SEPTEMBER_16, failed=(SyncStage.DOWNLOAD,)))
    drain = RunSummary(
        run_id=SEPTEMBER_17.strftime("%Y%m%dT%H%M%SZ"),
        started_at=SEPTEMBER_17,
        finished_at=SEPTEMBER_17,
        dry_run=False,
        caselists=(),
        stages=(StageRecord(stage=SyncStage.PUBLISH, outcome=StageOutcome.FAILED, reason="refused"),),
    )
    for log in (after_success, after_failure):
        log.append(record_for_summary(drain, environment="dev", mode="publish_pending"))

    current = await LandscapeStalenessCheck(objects=objects, run_log=after_success).check(
        CASELIST, report_date=FRESH
    )
    still_failed = await LandscapeStalenessCheck(objects=objects, run_log=after_failure).check(
        CASELIST, report_date=FRESH
    )

    assert not current.stale
    assert still_failed.failed_run == FailedSyncRun(run_id=FAILED_RUN_ID, stages=("download",))


async def test_a_run_with_no_end_recorded_never_flips_the_hook(
    objects: FsEvidenceObjectStore, tmp_path: Path
) -> None:
    """A killed run writes no record. A line without `finished_at`, or one cut off mid-write, is
    not a record either: the log skips it, and the hook reads the run before it."""
    no_end = json.dumps(
        {
            "run_id": "20260918T060000Z",
            "environment": "dev",
            "mode": "run",
            "started_at": "2026-09-18T06:00:00Z",
            "outcome": "failed",
            "caselists": [CASELIST],
            "deferred_by_caselist": {CASELIST: 0},
        }
    )
    cut_off = record_for_summary(run_of(SEPTEMBER_17), environment="dev", mode="run").model_dump_json()[:80]
    current = log_of(tmp_path / "current", run_of(SEPTEMBER_16))
    failed = log_of(tmp_path / "failed", run_of(SEPTEMBER_16, failed=(SyncStage.DOWNLOAD,)))
    for log in (current, failed):
        with log.path.open("a", encoding="utf-8") as appended:
            appended.write(f"{no_end}\n{cut_off}\n")

    assert len(current.read()) == 1 and len(failed.read()) == 1
    assert not (
        await LandscapeStalenessCheck(objects=objects, run_log=current).check(CASELIST, report_date=FRESH)
    ).stale
    assert (
        await LandscapeStalenessCheck(objects=objects, run_log=failed).check(CASELIST, report_date=FRESH)
    ).failed_run == FailedSyncRun(run_id=FAILED_RUN_ID, stages=("download",))


async def test_when_every_rule_applies_the_banner_names_each(
    objects: FsEvidenceObjectStore, tmp_path: Path
) -> None:
    """Too old, cap-bound and failed: a run that listed two deferred weeklies, then failed to publish."""
    log = log_of(tmp_path, run_of(SEPTEMBER_16, failed=(SyncStage.DOWNLOAD, SyncStage.PUBLISH), deferred=2))
    check = LandscapeStalenessCheck(objects=objects, run_log=log)

    staleness = await check.check(CASELIST, report_date=NEWEST + timedelta(days=9))
    banner = staleness.banner() or ""

    assert staleness.too_old and staleness.cap_bound and staleness.latest_run_failed
    assert "9 day(s) before this report" in banner
    assert "2 newer weekly archive(s) are published but not yet downloaded" in banner
    assert (
        f"The latest sync run of this caselist, {FAILED_RUN_ID}, failed at its download and publish stages."
        in banner
    )


async def test_the_reason_names_no_school_and_no_path_from_the_stage_details(
    objects: FsEvidenceObjectStore, tmp_path: Path
) -> None:
    """The record's stage reasons are redacted text, and may still say more than a banner should.

    The reason is built from the run id and the stage's name alone. A stage name no build writes is
    not repeated either: it is a string in the log, not one of `SyncStage`'s.
    """
    log = log_of(
        tmp_path,
        run_of(
            SEPTEMBER_16,
            failed=(SyncStage.IMPORT,),
            failed_reason=f"{SCHOOL_LIKE}: {PATH_LIKE} is unreadable",
        ),
    )
    started = SEPTEMBER_17
    log.append(
        SyncRunRecord(
            run_id="20260917T060000Z",
            environment="dev",
            mode="run",
            started_at=started,
            finished_at=started,
            outcome=SyncRunOutcome.FAILED,
            caselists=(OTHER_CASELIST,),
            deferred_by_caselist={OTHER_CASELIST: 0},
            stages=(
                StageEntry(stage=SCHOOL_LIKE, outcome="failed", reason=PATH_LIKE),
                StageEntry(stage="download", outcome="failed", reason=f"{SCHOOL_LIKE} {PATH_LIKE}"),
            ),
        )
    )
    check = LandscapeStalenessCheck(objects=objects, run_log=log)

    for caselist, stage in ((CASELIST, "import"), (OTHER_CASELIST, "download")):
        staleness = await check.check(caselist, report_date=FRESH)
        said = (staleness.banner() or "") + json.dumps(staleness.csv_metadata())
        assert f"failed at its {stage} stage." in said
        for part in (SCHOOL_LIKE, "Harrowgate", "HaPX", PATH_LIKE, ".docx", "/"):
            assert part not in said, part
