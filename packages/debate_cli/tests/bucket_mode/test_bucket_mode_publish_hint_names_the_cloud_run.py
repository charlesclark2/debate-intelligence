"""In bucket mode the command's own next step for a failed publish names the cloud run (`v1-e40-t25`).

`caselist pull` ends a run whose publish stage failed with a hint of its own, under the panel and in
the `--json` envelope's error. It said "Re-run `caselist pull --publish-pending`", which publishes
from the working copy of the machine it is run on; the cloud run's working copy ends with its task.
In bucket mode, as the composition root's bracket says, it names the next cloud run instead. Local
mode keeps every word. The banners of the same run are held to the cloud run in
`packages/debate_core/tests/application/caselist/test_caselist_sync_bucket_mode_publish_hints_point_at_the_cloud.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Final

import pytest
from tests.fixtures.parse_pipeline.build_parse_world import CASELIST, WEEKS

from debate_cli.commands.caselist_pull import _pull_failure  # pyright: ignore[reportPrivateUsage]
from debate_cli.exit_codes import ExitCode
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist_sync import RunSummary, StageOutcome, StageRecord, SyncStage
from debate_core.application.errors import StoreUnavailable
from debate_core.application.sync_runs import SyncRunDetails, SyncRunRecord, notifications_for

World = Any
"""`conftest.py`'s world, which a test module cannot import by name."""

WEEK_1, WEEK_2, WEEK_3 = (week.snapshot for week in WEEKS)

TRANSIENT: Final = (
    "Transient: every failure here is one a later run may not meet, and the next scheduled run retries it. "
)
THE_NEXT_STEP_IN_THE_CLOUD: Final = (
    "In bucket mode the next cloud run takes up what this run did not publish, from the run state saved "
    'in the bucket: the weekly run, or one started by hand (caselist-cloud-run.md, "A failed publish '
    "stage\"); never a publish from the operator's Mac."
)
THE_NEXT_STEP_ON_THE_MAC: Final = (
    "Re-run `caselist pull --publish-pending`: every confirmed source is skipped."
)
THE_BANNERS_CLOUD_FIX: Final = (
    "the next cloud run takes up what this run did not publish, from the run state saved in the "
    'bucket: the weekly run, or one started by hand (caselist-cloud-run.md, "A failed publish stage"); '
    "never a publish from the operator's Mac"
)


def a_failed_publish() -> RunSummary:
    started = datetime(2026, 9, 16, 6, 0, tzinfo=UTC)
    return RunSummary(
        run_id="20260916T060000Z",
        started_at=started,
        finished_at=started,
        dry_run=False,
        caselists=(CASELIST,),
        stages=(
            StageRecord(
                SyncStage.PUBLISH, StageOutcome.FAILED, "a sentence", error_codes=("STORE_UNAVAILABLE",)
            ),
        ),
    )


@pytest.mark.parametrize(
    ("bucket_mode", "hint"),
    [(True, TRANSIENT + THE_NEXT_STEP_IN_THE_CLOUD), (False, TRANSIENT + THE_NEXT_STEP_ON_THE_MAC)],
    ids=["bucket", "local"],
)
def test_a_failed_publish_gives_its_modes_next_step(bucket_mode: bool, hint: str) -> None:
    failure = _pull_failure(a_failed_publish(), {}, bucket_mode=bucket_mode)

    assert failure.hint == hint


def test_the_command_in_bucket_mode_names_the_next_cloud_run_when_the_bucket_refused_its_publish(
    world: World,
) -> None:
    """Weeks one and two pulled on "the Mac" and seeded; week three pulled in bucket mode, where the
    bucket does not answer the publish. The command's next step, and the banner built from the record
    and details it kept, name the next cloud run and no Mac-side publish."""
    world.listing(WEEK_1, WEEK_2)
    assert world.pull()["exit_code"] == ExitCode.OK
    world.seed()
    world.clock.advance(timedelta(days=7))
    world.listing(WEEK_1, WEEK_2, WEEK_3)

    async def refused(self: CaselistPublishService, plan: Any) -> Any:
        raise StoreUnavailable("PutObject", f"sources/{CASELIST}", "SlowDown")

    world.monkeypatch.setattr(CaselistPublishService, "execute", refused)
    pulled = world.pull()

    assert pulled["exit_code"] == ExitCode.RETRIEVAL_FAILURE, pulled
    [publish] = [one for one in pulled["error"]["details"]["stages"] if one["stage"] == "publish"]
    assert (publish["outcome"], publish["error_codes"]) == ("failed", ["STORE_UNAVAILABLE"])
    assert pulled["error"]["hint"] == TRANSIENT + THE_NEXT_STEP_IN_THE_CLOUD
    record, details = world.last_record()
    assert details["bucket_run"] is not None
    [banner] = [
        one
        for one in notifications_for(
            SyncRunRecord.model_validate(record),
            SyncRunDetails.model_validate(details),
            aws_login_command="aws sso login",
            credentials_expired=False,
        )
        if one.title.startswith("caselist pull failed")
    ]
    assert banner.fix_command == THE_BANNERS_CLOUD_FIX
    for mac_side in ("--publish", "caselist pull", "aws sso login", "this machine's copy"):
        assert mac_side not in banner.text
        assert mac_side not in pulled["error"]["hint"]
