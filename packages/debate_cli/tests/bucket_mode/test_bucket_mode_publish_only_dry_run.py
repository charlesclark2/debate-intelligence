"""`caselist parse --publish-only --dry-run` and the bucket's run lock (`v1-e31-t40`).

The real `--publish-only` holds the lock while it writes (`v1-e40-t04`): in bucket mode it takes the
lease, and in local mode it refuses a bucket that holds a lock object. The dry run takes nothing: it
reads the lock and refuses what taking it would refuse, with the same code, and leaves every object,
the lock's versions included, as it was.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from debate_cli.exit_codes import ExitCode
from debate_core.application.caselist.run_lock import RUN_LOCK_KEY

from .test_bucket_mode_lock import another_runner_holds_the_lock, lock_holders, seeded_with_two_weeks

World = Any
"""`conftest.py`'s world, which a test module cannot import by name."""

PUBLISH_ONLY = ("caselist", "parse", "--caselist", "testcl26", "--publish-only")


def test_in_bucket_mode_the_dry_run_takes_no_lock_and_writes_nothing(world: World) -> None:
    seeded_with_two_weeks(world)
    before, versions, holders = world.everything(), world.versions(RUN_LOCK_KEY), lock_holders(world)

    planned = world.run(*PUBLISH_ONLY, "--dry-run")

    assert planned["exit_code"] == ExitCode.OK, planned
    assert planned["data"]["dry_run"] is True
    assert world.everything() == before
    assert world.versions(RUN_LOCK_KEY) == versions
    assert lock_holders(world) == holders
    assert "caselist parse --publish-only" not in holders


def test_in_bucket_mode_the_dry_run_is_refused_while_another_runner_holds_the_lock_as_the_publish_is(
    world: World,
) -> None:
    seeded_with_two_weeks(world)
    another_runner_holds_the_lock(world, lease_left=timedelta(minutes=10))
    before = world.everything()

    refused = world.run(*PUBLISH_ONLY, "--dry-run")
    real = world.run(*PUBLISH_ONLY)

    assert refused["error"]["code"] == "RUN_LOCK_HELD", refused
    assert refused["error"] == real["error"]
    assert refused["exit_code"] == real["exit_code"] != ExitCode.OK
    assert world.everything() == before


def test_in_local_mode_the_dry_run_refuses_a_bucket_that_holds_a_lock_object_as_the_publish_does(
    world: World,
) -> None:
    seeded_with_two_weeks(world)
    world.mode("local")
    before = world.everything()

    refused = world.run(*PUBLISH_ONLY, "--dry-run")
    real = world.run(*PUBLISH_ONLY)

    assert refused["error"]["code"] == "BUCKET_KEEPS_RUN_STATE", refused
    assert refused["error"] == real["error"]
    assert refused["exit_code"] == real["exit_code"]
    assert world.everything() == before
