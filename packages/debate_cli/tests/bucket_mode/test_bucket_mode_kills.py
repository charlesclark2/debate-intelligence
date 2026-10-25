"""A run killed at any stage leaves the bucket readable by the next run (ac2).

`v1-e40-t04`, ADR-0020 (3), "A run killed at any stage", and the PM's context: "killed at each stage"
covers SIGTERM as well as a hard kill.

**A hard kill** is the task's process gone: no `finally`, no release, no record. It is played here
by :class:`Killed`, which derives from `BaseException` so that no stage, monitor or saver catches
it, and by making every S3 call from that moment raise it too, so that whatever cleanup Python still
runs reaches nothing in the bucket. The lock is left held, as a dead task leaves it.

**SIGTERM** is the real signal, sent to this process at the stage's start, which the command's
handler turns into a stop: the run records `RUN_TERMINATED`, saves what it may and releases.

After either, the next run starts as the cloud task would: an empty data directory, and, after a
hard kill, a clock past the dead runner's lease. It must take the run over, finish the week, and
leave the bucket as a run that was never interrupted leaves a copy of it: the same evidence, key by
key and byte by byte.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
from collections.abc import Awaitable, Callable
from datetime import timedelta
from pathlib import Path
from typing import Any, Final

import pytest
from tests.fixtures.parse_pipeline.build_parse_world import WEEKS

import debate_core.integrations.s3 as s3_package
from debate_cli.exit_codes import ExitCode
from debate_core.application.caselist.bucket_run import BucketRun
from debate_core.application.caselist_sync import CaselistSyncService, SyncStage

World = Any
"""`conftest.py`'s world, which a test module cannot import by name."""

WEEK_1, WEEK_2, WEEK_3 = (week.snapshot for week in WEEKS)
REFERENCE: Final = "debate-dev-evidence-moto-reference"
ORIGINAL: Final = "debate-dev-evidence-moto"


class Killed(BaseException):
    """The process is gone. Nothing catches it, as nothing outlives a SIGKILL."""


class KillSwitch:
    """Every S3 client the command builds, the lock's included, answers nothing once the switch is thrown."""

    def __init__(self) -> None:
        self.dead = False
        self.writes = 0
        self.kill_at_write: int | None = None

    def kill(self) -> None:
        self.dead = True
        raise Killed

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        build = s3_package.build_s3_client

        def built(**arguments: Any) -> Any:
            client = build(**arguments)

            def answer(model: Any, **_: object) -> None:
                if self.dead:
                    raise Killed
                if not str(model.name).startswith(("Get", "Head", "List")):
                    self.writes += 1
                    if self.kill_at_write is not None and self.writes >= self.kill_at_write:
                        self.kill()

            client.meta.events.register("before-parameter-build.s3", answer)
            return client

        monkeypatch.setattr(s3_package, "build_s3_client", built)


def seeded(world: World) -> None:
    """The Mac's two weeks, published and seeded, and week three on the site for the run to come."""
    world.listing(WEEK_1, WEEK_2)
    assert world.pull()["exit_code"] == ExitCode.OK
    world.seed()
    world.clock.advance(timedelta(days=7))
    world.listing(WEEK_1, WEEK_2, WEEK_3)


def evidence(world: World) -> dict[str, str]:
    """The bucket's evidence by key and ETag: not the runs' records, state, bundle or lock."""
    return {
        key: etag
        for key, etag in world.everything().items()
        if not key.startswith(("reports/sync", "manifests/_run-state/"))
    }


def an_uninterrupted_week(world: World, tmp_path: Path) -> dict[str, str]:
    """What a run never interrupted leaves, on a copy of the seeded bucket."""
    world.copy_bucket(REFERENCE)
    world.use_bucket(REFERENCE)
    world.use(tmp_path / "reference")
    assert world.pull()["exit_code"] == ExitCode.OK
    left = evidence(world)
    world.use_bucket(ORIGINAL)
    return left


LATE_ONLY_UNDER: Final = ("parsed/", "reports/tub/search/")
"""What a kill may leave late: the parse and the index of the week the killed run had published."""


def the_next_run_finishes_the_week(
    world: World, tmp_path: Path, *, uninterrupted: dict[str, str]
) -> dict[str, Any]:
    """The next run takes over and finishes; the bucket then ends as an uninterrupted run leaves it.

    One thing may be late, never lost, exactly as on the Mac: a run killed after its publish stage
    saved the bundle leaves that week's sources imported and published but not parsed, and the next
    run, finding nothing new, parses nothing (the parse stage parses what its own run imported). The
    week is parsed by the next pull that imports into the caselist, or by hand with the fix the
    run's reason names. Both halves are shown: the difference is under `parsed/` and the index
    alone, and the by-hand catch-up closes it.
    """
    world.use(tmp_path / "next")
    following = world.pull()
    assert following["exit_code"] == ExitCode.OK, following
    assert world.lock()["state"] == "free"
    bundle = following["data"]["run_details"]["bucket_run"]["bundle"]
    assert bundle.startswith("saved, "), bundle
    now = evidence(world)
    late = {key for key in set(now) | set(uninterrupted) if now.get(key) != uninterrupted.get(key)}
    assert all(key.startswith(LATE_ONLY_UNDER) for key in late), sorted(late)
    if late:
        assert following["data"]["parse"] is None, "late only when the next run had nothing to parse"
        assert world.run("caselist", "parse", "--caselist", "testcl26", "--publish")["exit_code"] == ExitCode.OK
        built = world.run("tub", "index", "build", "--caselist", "testcl26", "--caselist", "openev")
        assert built["exit_code"] == ExitCode.OK, built
        assert world.run("tub", "index", "publish", "--env", "dev", "--newest")["exit_code"] == ExitCode.OK
    assert evidence(world) == uninterrupted, "the bucket ends as a run that was never interrupted leaves it"
    return following


def kill_at_stage(monkeypatch: pytest.MonkeyPatch, switch: KillSwitch, stage: str) -> None:
    timed = CaselistSyncService._timed  # pyright: ignore[reportPrivateUsage]

    async def killed_at(
        self: CaselistSyncService, at: SyncStage, tally: Any, work: Callable[[], Awaitable[Any]]
    ) -> Any:
        if str(at) == stage:
            switch.kill()
        return await timed(self, at, tally, work)

    monkeypatch.setattr(CaselistSyncService, "_timed", killed_at)


STAGES: Final = ("select", "download", "import", "publish", "parse", "search_index", "report", "retention")


@pytest.mark.parametrize("stage", STAGES)
def test_a_run_killed_at_the_start_of_each_stage_leaves_the_bucket_readable_by_the_next(
    world: World, tmp_path: Path, stage: str
) -> None:
    seeded(world)
    uninterrupted = an_uninterrupted_week(world, tmp_path)
    world.use(tmp_path / "killed")
    with pytest.MonkeyPatch.context() as killing:
        switch = KillSwitch()
        switch.install(killing)
        kill_at_stage(killing, switch, stage)

        with pytest.raises(Killed):
            world.invoke("--json", "caselist", "pull", "--caselist", "testcl26")

    assert world.lock()["state"] == "held", "a dead runner releases nothing"
    world.clock.advance(timedelta(minutes=36))
    following = the_next_run_finishes_the_week(world, tmp_path, uninterrupted=uninterrupted)
    assert following["data"]["run_details"]["bucket_run"]["took_over"] is not None


@pytest.mark.parametrize("write", [1, 2, 4, 8, 12, 16, 20])
def test_a_run_killed_after_its_nth_bucket_write_leaves_the_bucket_readable_by_the_next(
    world: World, tmp_path: Path, write: int
) -> None:
    """Inside the stages: between a source and its manifest, among the parsed files, between the
    index's objects and its pointer, between the state files and the bundle."""
    seeded(world)
    uninterrupted = an_uninterrupted_week(world, tmp_path)
    world.use(tmp_path / "killed")
    with pytest.MonkeyPatch.context() as killing:
        switch = KillSwitch()
        switch.install(killing)
        switch.kill_at_write = write

        with pytest.raises(Killed):
            world.invoke("--json", "caselist", "pull", "--caselist", "testcl26")

    world.clock.advance(timedelta(minutes=36))
    the_next_run_finishes_the_week(world, tmp_path, uninterrupted=uninterrupted)


def test_a_run_killed_after_its_last_write_leaves_the_bucket_as_a_finished_run_does(
    world: World, tmp_path: Path
) -> None:
    """Killed as it ends, before the state files and the release: the next run has nothing to redo."""
    seeded(world)
    uninterrupted = an_uninterrupted_week(world, tmp_path)
    world.use(tmp_path / "killed")
    with pytest.MonkeyPatch.context() as killing:
        switch = KillSwitch()
        switch.install(killing)

        async def killed_at_the_end(self: BucketRun) -> None:
            switch.kill()

        killing.setattr(BucketRun, "finish", killed_at_the_end)

        with pytest.raises(Killed):
            world.invoke("--json", "caselist", "pull", "--caselist", "testcl26")

    assert evidence(world) == uninterrupted
    world.clock.advance(timedelta(minutes=36))
    following = the_next_run_finishes_the_week(world, tmp_path, uninterrupted=uninterrupted)
    assert following["data"]["parse"] is None or following["data"]["parse"]["attempted"] == 0


# ------------------------------------------------------------------------------------------------
# SIGTERM
# ------------------------------------------------------------------------------------------------


def sigterm_at_stage(monkeypatch: pytest.MonkeyPatch, stage: str) -> None:
    timed = CaselistSyncService._timed  # pyright: ignore[reportPrivateUsage]

    async def stopped_at(
        self: CaselistSyncService, at: SyncStage, tally: Any, work: Callable[[], Awaitable[Any]]
    ) -> Any:
        if str(at) == stage:
            os.kill(os.getpid(), signal.SIGTERM)
            await asyncio.sleep(0.05)
        return await timed(self, at, tally, work)

    monkeypatch.setattr(CaselistSyncService, "_timed", stopped_at)


@pytest.mark.parametrize("stage", ["download", "publish", "parse", "search_index", "report"])
def test_a_run_sent_sigterm_at_a_stage_records_a_failure_releases_the_lock_and_the_next_finishes(
    world: World, tmp_path: Path, stage: str
) -> None:
    seeded(world)
    uninterrupted = an_uninterrupted_week(world, tmp_path)
    stopped_in = world.use(tmp_path / "stopped")
    with pytest.MonkeyPatch.context() as stopping:
        sigterm_at_stage(stopping, stage)

        stopped = world.pull()

    assert stopped["exit_code"] != ExitCode.OK, stopped
    assert stopped["error"]["code"] == "RUN_TERMINATED", stopped["error"]
    record, details = world.last_record(stopped_in)
    assert (record["outcome"], record["error_class"]) == ("failed", "RunTerminated")
    assert details["failure_codes"] == ["RUN_TERMINATED"]
    published = json.loads(world.body(f"reports/sync-runs/2026/{record['run_id']}.json"))
    assert published["error_class"] == "RunTerminated", "a stopped run shows in the run log"
    assert world.lock()["state"] == "free", "released within the stop"
    log = world.body("reports/sync/state/caselist-sync-runs.jsonl").decode().splitlines()
    assert json.loads(log[-1])["run_id"] == record["run_id"], "the state files were saved on the way out"
    following = the_next_run_finishes_the_week(world, tmp_path, uninterrupted=uninterrupted)
    assert following["data"]["run_details"]["bucket_run"]["took_over"] is None, "nothing to take over"
