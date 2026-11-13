"""`caselist pull --scheduled` through the real application, over moto and the fictional site (`v1-e40-t44`).

The PM's rulings of 2026-11-12, as the command meets them:

* `--scheduled` is the weekly schedule's whole run in bucket mode: beside `--dry-run` or `--publish-pending`,
  or in local mode, it is a usage error (exit 2) before anything runs (ruling 2);
* a scheduled pull a retry starts after the first run has finished is refused (exit 1,
  `RECENT_RUN_RECORDED`), before the lock and before OpenCaselist is called, writing nothing to the bucket,
  and its error names the run it found and the cure (rulings 1 and 4);
* a hand run at the same moment is not refused (ruling 2).

The case in full is `debate_core`'s `test_scheduled_pull_guard.py`; this is the command's wiring of it.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any, Final

import pytest
from tests.fixtures.parse_pipeline.build_parse_world import WEEKS

from debate_cli.exit_codes import ExitCode

World = Any
"""`conftest.py`'s world, which a test module cannot import by name."""

WEEK_1, WEEK_2, WEEK_3 = (week.snapshot for week in WEEKS)
CURE: Final = "a hand run (the cloud-run runbook's Step 8) is never refused by this guard"


def seeded_a_week_ago(world: World) -> None:
    """Two weeks pulled on the Mac and seeded into the bucket, then a week on, with a third listed."""
    world.listing(WEEK_1, WEEK_2)
    assert world.pull()["exit_code"] == ExitCode.OK
    world.seed()
    world.clock.advance(timedelta(days=7))
    world.listing(WEEK_1, WEEK_2, WEEK_3)


# ------------------------------------------------------------------------------------------------
# What --scheduled is refused beside, before anything runs
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("arguments", "mode", "said"),
    [
        (("--dry-run",), "bucket", "a dry run takes nothing to guard"),
        (("--publish-pending",), "bucket", "--publish-pending lists and fetches nothing"),
        ((), "local", "only bucket mode keeps the bucket's run log"),
    ],
    ids=["beside_dry_run", "beside_publish_pending", "in_local_mode"],
)
def test_a_scheduled_pull_guard_refuses_what_it_cannot_guard_as_a_usage_error(
    world: World, tmp_path: Path, arguments: tuple[str, ...], mode: str, said: str
) -> None:
    world.mode(mode)
    world.listing(WEEK_1)
    calls = len(world.site.calls)
    data_dir = world.use(tmp_path / "task")

    refused = world.run("caselist", "pull", "--scheduled", *arguments)

    assert refused["exit_code"] == ExitCode.USAGE_ERROR, refused
    assert refused["error"]["code"] == "USAGE_ERROR"
    assert said in refused["error"]["message"]
    assert len(world.site.calls) == calls, "nothing listed or fetched"
    assert world.object_keys() == set(), "nothing written to the bucket"
    assert not (data_dir / "caselist-sync-runs.jsonl").exists(), "no run, so no record"


# ------------------------------------------------------------------------------------------------
# A retry's second task after the week's run: refused; a hand run at the same moment: not
# ------------------------------------------------------------------------------------------------


def test_a_scheduled_pull_guard_refuses_a_second_scheduled_pull_and_never_a_hand_run(
    world: World, tmp_path: Path
) -> None:
    seeded_a_week_ago(world)
    world.use(tmp_path / "wednesday-task")
    first = world.pull("--scheduled")
    assert first["exit_code"] == ExitCode.OK, first
    first_run = first["data"]["run_id"]
    assert world.lock()["state"] == "free"

    world.clock.advance(timedelta(minutes=58))
    before, calls = world.everything(), len(world.site.calls)
    retried = world.use(tmp_path / "retry-task")
    refused = world.pull("--scheduled")

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused
    error = refused["error"]
    assert error["code"] == "RECENT_RUN_RECORDED"
    assert f"records run {first_run}, started " in error["message"]
    assert error["hint"].endswith(f"If the week still needs a run, {CURE}.")
    assert len(world.site.calls) == calls, "OpenCaselist was not called"
    assert world.everything() == before, "nothing written to the bucket, the lock and the record included"
    record, details = world.last_record(retried)
    assert (record["outcome"], record["error_class"]) == ("failed", "RecentRunRecorded")
    assert details["failure_codes"] == ["RECENT_RUN_RECORDED"]
    assert not (retried / "debate.sqlite3").exists(), "nothing was restored"

    world.use(tmp_path / "hand-run-task")
    by_hand = world.pull()

    assert by_hand["exit_code"] == ExitCode.OK, by_hand
    assert world.lock()["state"] == "free"
