"""A bucket-mode pull names the cloud cure for every parsed store it owes (`v1-e34-t31`, `v1-e40-t18`).

The parse stage names `caselist parse --publish-only` for a caselist only where the version
directory it rebuilt is still there to publish after the run. In local mode it is: the data
directory is the operator's. In bucket mode it is not: the cloud run's working copy is on its
task's ephemeral storage, and the parsed store a later run or `caselist restore-run-state` restores
is the bucket's, not the one the failed publish left. Nor is any `caselist parse` command the cure in
bucket mode: run on the operator's Mac, it publishes the Mac's own working copy over the parsed
store the cloud run owns (`v1-e40-t18`). The stage names the cloud cure instead: the next cloud run,
which since `v1-e40-t08` parses and publishes what is owed whether or not it imports into the
caselist. The composition root tells the pull which mode it is in, and
`packages/debate_core/tests/application/caselist/test_caselist_sync_names_the_cloud_cure_in_bucket_mode.py`
holds the stage and the banners to it. The last test here runs the whole command in bucket mode.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Final

import pytest
from tests.fixtures.parse_pipeline.build_parse_world import CASELIST, WEEKS

from debate_cli.caselist_events import event_for_caselist
from debate_cli.container import ServiceContainer
from debate_cli.exit_codes import ExitCode
from debate_core.application.caselist_pull_parse import PullParseStage
from debate_core.application.errors import StoreUnavailable
from debate_core.application.settings import load_settings
from debate_core.application.sync_runs import SyncRunDetails, SyncRunRecord, notifications_for

World = Any
"""`conftest.py`'s world, which a test module cannot import by name."""

WEEK_1, WEEK_2, WEEK_3 = (week.snapshot for week in WEEKS)

CLOUD_CURE: Final = (
    f"the next cloud run publishes the parsed store of {CASELIST}: the weekly run, or one started by hand "
    '(caselist-cloud-run.md, "A failed parse stage"); never a publish from the operator\'s Mac'
)
"""Without "that imports into" since `v1-e40-t08`: the next run parses what is owed whatever it imports."""
CLOUD_HINT: Final = (
    f"The cloud run publishes the parsed store of {CASELIST}, never the operator's Mac, whose working "
    "copy is not the one the cloud run owns: the next weekly run rebuilds it and publishes it, whether "
    "or not it imports into the caselist, and so does a run started by hand "
    '(caselist-cloud-run.md, "A failed parse stage").'
)


@pytest.mark.parametrize(("run_state", "kept"), [("local", True), ("bucket", False)])
def test_the_pull_is_told_whether_its_working_copy_outlives_it(
    world: World, run_state: str, kept: bool
) -> None:
    world.mode(run_state)

    service = ServiceContainer(settings_loader=load_settings).caselist_sync(
        event_for_caselist=event_for_caselist
    )

    assert service._working_copy_outlives_the_run is kept  # pyright: ignore[reportPrivateUsage]


@pytest.mark.parametrize(("run_state", "bucket_mode"), [("local", False), ("bucket", True)])
def test_the_pull_is_told_whether_it_runs_in_bucket_mode(
    world: World, run_state: str, bucket_mode: bool
) -> None:
    world.mode(run_state)

    service = ServiceContainer(settings_loader=load_settings).caselist_sync(
        event_for_caselist=event_for_caselist
    )

    assert service._bucket_mode is bucket_mode  # pyright: ignore[reportPrivateUsage]


def test_a_bucket_mode_pull_whose_parsed_publish_was_refused_names_the_cloud_cure(world: World) -> None:
    """Weeks one and two pulled on "the Mac" and seeded; week three pulled in bucket mode, where the
    bucket does not answer for the parsed store. The command's own summary, the details it kept and
    the banner built from its record and details name the cloud cure and no Mac-side publish."""
    world.listing(WEEK_1, WEEK_2)
    assert world.pull()["exit_code"] == ExitCode.OK
    world.seed()
    world.clock.advance(timedelta(days=7))
    world.listing(WEEK_1, WEEK_2, WEEK_3)

    async def refused(self: PullParseStage, caselist: str, version: str) -> Any:
        raise StoreUnavailable("PutObject", f"parsed/{caselist}", "SlowDown")

    world.monkeypatch.setattr(PullParseStage, "publish", refused)
    pulled = world.pull()

    assert pulled["exit_code"] == ExitCode.OK, pulled
    [parse] = [one for one in pulled["data"]["stages"] if one["stage"] == "parse"]
    assert (parse["outcome"], parse["error_codes"]) == ("failed", ["STORE_UNAVAILABLE"])
    assert parse["hint"] == CLOUD_HINT
    record, details = world.last_record()
    assert details["bucket_run"] is not None
    assert details["parsed_stores_owed"] == [{"caselist": CASELIST, "publish_only": False}]
    [banner] = [
        one
        for one in notifications_for(
            SyncRunRecord.model_validate(record),
            SyncRunDetails.model_validate(details),
            aws_login_command="aws sso login",
            credentials_expired=False,
        )
        if one.title == "caselist pull finished with a failed stage"
    ]
    assert banner.fix_command == CLOUD_CURE
    assert "--publish" not in banner.text
    assert "caselist parse" not in banner.text
