"""The 24-hour download allowance is never negative, and never above five (`v1-e34-t23`, item 13).

`v1-e34-t09`'s mutation run found two guards on the allowance that no test could tell from their
absence:

* **The clamp at zero.** `DownloadLedger.remaining_at` is `max(limit - spent, 0)`. Without it, a
  window holding more starts than the limit reports a negative allowance. Nothing more is
  downloaded, because the budget clamps again where it is spent, but the plan and the summary say
  `-1`. That happens when the operator lowers `caselist.bulk_downloads_per_day` with more already
  spent, and no test recorded more starts than the limit.
* **The service's ceiling of five.** `CaselistSyncService` takes `min(bulk_downloads_per_day, 5)`.
  The settings refuse a limit above five, so no run built from settings reaches it; only a
  service built directly can. It is kept, and tested here by building the service directly: the
  five a day is the site maintainer's, and a second guard on it costs one comparison.

Every expected number is worked out by hand from the starts each test records.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from tests.fixtures.caselist.build_synthetic_archives import build_snapshot_zips

from debate_core.application.caselist_sync import (
    DOWNLOAD_LEDGER_FILENAME,
    DownloadLedger,
    SelectionDecision,
    SyncStage,
)
from debate_core.integrations.local import FsEvidenceObjectStore

from .test_inbox_retention import CASELIST, RUN_CLOCK, WEEK_1, WEEK_2, FakeSource, Installation

pytestmark = pytest.mark.anyio

SIX_WEEKS = [date(2026, 8, 4) + timedelta(weeks=one) for one in range(6)]
"""Six weeklies listed and none held: more than any day's allowance."""


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def installation(tmp_path: Path) -> Installation:
    """No bucket is reached by anything here: a pull that downloads nothing publishes nothing."""
    return Installation(
        data_dir=tmp_path / "evidence",
        bucket=FsEvidenceObjectStore(tmp_path / "unused-bucket"),
        archives=build_snapshot_zips(tmp_path / "published"),
    )


def record_starts(installation: Installation, count: int) -> DownloadLedger:
    """`count` downloads started in the hour before the run: all inside its 24 hours."""
    ledger = DownloadLedger(installation.data_dir / DOWNLOAD_LEDGER_FILENAME)
    for minutes in range(count):
        ledger.record(RUN_CLOCK - timedelta(minutes=60 - minutes))
    return ledger


def test_six_starts_against_a_limit_of_five_leave_nothing_and_never_less(installation: Installation) -> None:
    ledger = record_starts(installation, 6)

    assert ledger.spent_in_window(RUN_CLOCK) == 6
    assert ledger.remaining_at(RUN_CLOCK) == 0


def test_a_lowered_limit_with_more_already_spent_leaves_nothing_and_never_less(
    installation: Installation,
) -> None:
    """The way it happens on the operator's Mac: five spent, and the setting lowered to three."""
    record_starts(installation, 5)

    lowered = DownloadLedger(installation.data_dir / DOWNLOAD_LEDGER_FILENAME, limit=3)

    assert lowered.spent_in_window(RUN_CLOCK) == 5
    assert lowered.remaining_at(RUN_CLOCK) == 0


async def test_the_plan_decides_from_an_allowance_of_zero(installation: Installation) -> None:
    record_starts(installation, 6)
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])

    plan = await installation.sync(source).plan([CASELIST])

    assert plan.bulk_downloads_allowed == 0
    assert plan.bulk_downloads_spent_in_window == 6
    assert [one.decision for one in plan.archives] == [SelectionDecision.OVER_DAILY_BUDGET] * 2
    assert plan.full_archive is not None
    assert plan.full_archive.allowance_after_weeklies == 0


async def test_the_summary_says_zero_left_of_six_spent(installation: Installation) -> None:
    record_starts(installation, 6)
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])

    summary = await installation.sync(source, bucket=False).run([CASELIST])

    assert source.archive_fetches == []
    assert summary.bulk_downloads_allowed == 0
    assert summary.as_json()["bulk_downloads_allowed"] == 0
    assert summary.as_json()["bulk_downloads_spent_in_window"] == 6
    select = summary.stage(SyncStage.SELECT)
    assert select is not None and select.reason is not None
    assert "6 of 5 bulk download(s) spent in the 24 hours from 2026-09-15 06:00 UTC, 0 left" in select.reason
    assert summary.archives_deferred == 2


async def test_a_service_built_directly_with_six_a_day_still_plans_five(installation: Installation) -> None:
    """Only a service built directly can be given six: the settings refuse it. The service's own
    ceiling holds then, and the sixth week waits for the next day's allowance."""
    source = FakeSource(installation.archives, weeks=SIX_WEEKS)

    plan = await installation.sync(source, bulk_downloads_per_day=6).plan([CASELIST])

    assert plan.bulk_downloads_allowed == 5
    assert [one.decision for one in plan.archives] == [SelectionDecision.DOWNLOAD] * 5 + [
        SelectionDecision.OVER_DAILY_BUDGET
    ]


async def test_a_service_built_directly_with_fewer_plans_what_it_was_given(
    installation: Installation,
) -> None:
    """The ceiling lowers nothing: a service given three plans three."""
    source = FakeSource(installation.archives, weeks=SIX_WEEKS)

    plan = await installation.sync(source, bulk_downloads_per_day=3).plan([CASELIST])

    assert plan.bulk_downloads_allowed == 3
