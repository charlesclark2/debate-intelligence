"""A held upload a cloud task's import refused reaches the bucket, and another machine finds it (`v1-e40-t12`).

An import refuses an upload at a path a removal holds and records it in the working copy's
`held-digests.jsonl` (`v1-e30-t23`). The removal run again, and `caselist status`, find it through
that record. A cloud task's working copy vanishes when the task stops, so in bucket mode every save of
the run-state bundle first appends the copy's lines to `manifests/_suppression/held-digests.jsonl`
under the run's lock (the PM's rulings of 2026-10-27).

Before this task a pull reached that object one way only: its search index stage reconciles every
copy of the suppression list before it publishes (`v1-e39-t09`), held-digest record included. A task
that stops after its publish stage and before that one has saved the bundle, so the next run does not
redo the week, and nothing else would ever meet the upload again. That is the week here: the Mac pulls
two weeks and seeds the bucket, then removes Cedar Hollow ZaLu's round 2 file by `--source`
(`RM-2026-07`), which holds its path. A later weekly carries new bytes at that path. A cloud task
pulls it in a data directory of its own, refuses the upload, publishes, and dies at the start of its
parse stage; its directory is deleted. Then, from the Mac's data directory, `caselist status` says the
removal is owed, and the same removal run again plans the upload and suppresses it.

A task killed before any save leaves the previous bundle, and the next run redoes the week and meets
the upload again. Local mode is unchanged: no bundle is saved, and the record reaches the bucket only
as it did before, through the index stage or the next removal.

A hard kill is played as `test_bucket_mode_kills.py` plays it: an exception nothing catches, and every
S3 call from that moment refused, so no cleanup reaches the bucket and the lock is left held.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import zipfile
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Final

import pytest
from tests.fixtures.parse_pipeline.build_parse_world import BODIES, CASELIST, WEEKS, digest_of

import debate_core.integrations.s3 as s3_package
from debate_cli.exit_codes import ExitCode
from debate_core.application.caselist.suppression import HELD_DIGESTS_KEY
from debate_core.application.caselist_sync import CaselistSyncService, SyncStage

World = Any
"""`conftest.py`'s world, which a test module cannot import by name."""

FILE_HOST: Final = "https://files.opencaselist.example.invalid"
REMOVAL_PROFILE: Final = "debate-dev-evidence-removal"
WEEK_1, WEEK_2, _ = (week.snapshot for week in WEEKS)
LATER: Final = date(2026, 9, 22)
REMOVED: Final = digest_of("wiki")
"""Cedar Hollow ZaLu's round 2 file, disclosed once, at one path, from 09-01."""
HELD_PATH: Final = next(path for path, body in WEEKS[0].members if body == "wiki")
LATER_UPLOAD: Final = b"a later upload at the removed path, which no import may take in\n"
LATER_DIGEST: Final = hashlib.sha256(LATER_UPLOAD).hexdigest()
REQUEST: Final = "RM-2026-07"
LATER_MANIFEST: Final = f"manifests/{CASELIST}/{LATER.isoformat()}.jsonl"


class Killed(BaseException):
    """The process is gone. Nothing catches it, as nothing outlives a SIGKILL."""


@dataclass
class TheBucket:
    """Every S3 client the command builds: a kill switch, and the lock's state at each held-digest upload."""

    world: World
    dead: bool = False
    lock_states: list[dict[str, Any]] = field(default_factory=list)

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        build = s3_package.build_s3_client

        def built(**arguments: Any) -> Any:
            client = build(**arguments)

            def answer(params: dict[str, Any], model: Any, **_: object) -> None:
                if self.dead:
                    raise Killed
                if str(model.name) == "PutObject" and params.get("Key") == HELD_DIGESTS_KEY:
                    self.lock_states.append(self.world.lock())

            client.meta.events.register("before-parameter-build.s3", answer)
            return client

        monkeypatch.setattr(s3_package, "build_s3_client", built)

    def kill_at_the_start_of(self, monkeypatch: pytest.MonkeyPatch, stage: str) -> None:
        timed = CaselistSyncService._timed  # pyright: ignore[reportPrivateUsage]

        async def killed_at(
            service: CaselistSyncService, at: SyncStage, tally: Any, work: Callable[[], Awaitable[Any]]
        ) -> Any:
            if str(at) == stage:
                self.dead = True
                raise Killed
            return await timed(service, at, tally, work)

        monkeypatch.setattr(CaselistSyncService, "_timed", killed_at)


def weekly_name(day: date) -> str:
    return f"{CASELIST}-weekly-{day.isoformat()}.zip"


def the_later_weekly() -> bytes:
    """Week two's members, with new bytes at the held path: one archive, as the site builds them."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, body in sorted(WEEKS[1].members):
            info = zipfile.ZipInfo(f"{CASELIST}-{LATER:%m%d}/{path}", date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            archive.writestr(info, LATER_UPLOAD if path == HELD_PATH else BODIES[body])
    return buffer.getvalue()


def remove(world: World, *, execute: bool) -> dict[str, Any]:
    arguments = ["--source", REMOVED, "--reason", "REQUESTED_BY_TEAM", "--request", REQUEST]
    return world.run("caselist", "remove", *arguments, *(["--execute"] if execute else []))


def a_path_held_and_a_later_weekly_with_an_upload_there(world: World, *, bucket_mode: bool) -> None:
    """The Mac's two weeks (seeded in bucket mode), its removal holding the path, and the later weekly."""
    world.listing(WEEK_1, WEEK_2)
    assert world.pull()["exit_code"] == ExitCode.OK
    if bucket_mode:
        world.seed()
    world.monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", REMOVAL_PROFILE)
    removed = remove(world, execute=True)
    assert removed["exit_code"] == ExitCode.OK, removed
    world.clock.advance(timedelta(days=7))
    world.site.get(f"{FILE_HOST}/{weekly_name(LATER)}").respond(200, content=the_later_weekly())
    world.listing(WEEK_1, WEEK_2, LATER)


def a_task_killed_at_the_start_of(world: World, data_dir: Path, stage: str) -> TheBucket:
    """A pull in `data_dir` that dies as `stage` starts; the lease left held, as a dead task leaves it."""
    world.use(data_dir)
    bucket = TheBucket(world)
    with pytest.MonkeyPatch.context() as killing:
        bucket.install(killing)
        bucket.kill_at_the_start_of(killing, stage)
        with pytest.raises(Killed):
            world.invoke("--json", "caselist", "pull", "--caselist", CASELIST)
    assert LATER_DIGEST in held_here(data_dir), "the premise: the task's import refused it, and recorded it"
    return bucket


def held_here(data_dir: Path) -> str:
    record = data_dir / "suppression" / "held-digests.jsonl"
    return record.read_text(encoding="utf-8") if record.exists() else ""


def refused_at_import(world: World) -> dict[str, Any]:
    """`caselist status`'s count of the uploads an import refused that the removal has not yet listed.

    The Mac's copy lacks the week the task published, so status reports drift and exits 1 with its
    report as the error's details; that is a difference the Mac's next restore closes, not this one.
    """
    status = world.run("caselist", "status", "--caselist", CASELIST)
    report = status["data"] if status["data"] is not None else status["error"]["details"]
    return {one["caselist"]: one for one in report["refused_at_import"]}[CASELIST]


@dataclass
class KilledAfterItsPublish:
    world: World
    bucket: TheBucket


@pytest.fixture
def killed_after_its_publish(world: World, tmp_path: Path) -> Iterator[KilledAfterItsPublish]:
    """A cloud task refuses the upload, publishes and saves the bundle, and dies before its parse."""
    a_path_held_and_a_later_weekly_with_an_upload_there(world, bucket_mode=True)
    cloud = tmp_path / "cloud-task"

    bucket = a_task_killed_at_the_start_of(world, cloud, "parse")

    assert LATER_MANIFEST in world.object_keys("manifests/"), "the premise: the week was published"
    assert world.lock()["state"] == "held", "the premise: a dead task releases nothing"
    shutil.rmtree(cloud)
    world.clock.advance(timedelta(minutes=36))
    world.use(world.root / "data")
    yield KilledAfterItsPublish(world, bucket)


def test_the_held_upload_the_task_recorded_is_in_the_buckets_held_digest_record(
    killed_after_its_publish: KilledAfterItsPublish,
) -> None:
    lines = killed_after_its_publish.world.body(HELD_DIGESTS_KEY).decode().splitlines()

    assert [json.loads(one)["sha256"] for one in lines] == [LATER_DIGEST]
    assert json.loads(lines[0])["request_id"] == REQUEST


def test_caselist_status_from_another_data_directory_says_the_removal_is_owed_for_it(
    killed_after_its_publish: KilledAfterItsPublish,
) -> None:
    refused = refused_at_import(killed_after_its_publish.world)

    assert refused["uploads"] == 1, refused
    assert refused["requests"] == [REQUEST]
    assert [LATER_DIGEST.startswith(prefix) for prefix in refused["sha256_prefixes"]] == [True]


def test_the_same_removal_run_again_from_another_data_directory_plans_it_and_suppresses_it(
    killed_after_its_publish: KilledAfterItsPublish,
) -> None:
    world = killed_after_its_publish.world

    planned = remove(world, execute=False)

    assert planned["exit_code"] == ExitCode.OK, planned
    sources = {one["sha256"]: one for one in planned["data"]["sources"]}
    assert sources[LATER_DIGEST]["inclusion"] == "held_at_import", sorted(sources)

    executed = remove(world, execute=True)

    assert executed["exit_code"] == ExitCode.OK, executed
    assert LATER_DIGEST in world.body("manifests/_suppression/suppression-list.jsonl").decode()
    assert refused_at_import(world)["uploads"] == 0, "nothing is owed once the re-run has listed it"


def test_the_record_reaches_the_bucket_only_while_the_task_holds_the_lock(
    killed_after_its_publish: KilledAfterItsPublish,
) -> None:
    states = killed_after_its_publish.bucket.lock_states

    assert states, "the task uploaded the record"
    for lock in states:
        assert lock["state"] == "held", lock
        assert lock["holder"]["command"] == "caselist pull", lock


def test_no_school_team_code_or_path_reaches_a_key_or_metadata_and_the_record_holds_digests_alone(
    killed_after_its_publish: KilledAfterItsPublish, tmp_path: Path
) -> None:
    """Data-use policy rule 3, over every object the week leaves in the bucket."""
    world = killed_after_its_publish.world
    paths = {path for week in WEEKS for path, _ in week.members}
    forbidden = {str(tmp_path), "cloud-task", *paths, *(part for path in paths for part in path.split("/"))}

    for key in sorted(world.object_keys()):
        metadata = world.client.head_object(Bucket=world.bucket, Key=key).get("Metadata", {})
        shown = " ".join([key, *metadata.keys(), *metadata.values()])
        assert not [word for word in forbidden if word in shown], (key, metadata)
    record = world.body(HELD_DIGESTS_KEY).decode()
    for line in record.splitlines():
        assert set(json.loads(line)) == {"schema_version", "sha256", "disclosure", "request_id"}
    assert not [word for word in forbidden if word in record]


def test_a_task_killed_before_any_save_leaves_the_week_to_the_next_run_which_meets_the_upload_again(
    world: World, tmp_path: Path
) -> None:
    """The known edge: a task that dies after its import and before its first save of the bundle."""
    a_path_held_and_a_later_weekly_with_an_upload_there(world, bucket_mode=True)
    killed = tmp_path / "killed-task"
    a_task_killed_at_the_start_of(world, killed, "publish")
    assert HELD_DIGESTS_KEY not in world.object_keys("manifests/_suppression/"), "nothing saved yet"
    shutil.rmtree(killed)
    world.clock.advance(timedelta(minutes=36))
    world.use(tmp_path / "next-task")

    following = world.pull()

    assert following["exit_code"] == ExitCode.OK, json.dumps(following.get("error"))[:1500]
    assert following["data"]["run_details"]["held_by_request"] == {REQUEST: 1}, "the week redone"
    assert LATER_DIGEST in world.body(HELD_DIGESTS_KEY).decode()


def test_in_local_mode_a_pull_that_dies_before_its_index_stage_leaves_the_record_on_this_machine_alone(
    world: World,
) -> None:
    """Local mode is unchanged: no bundle, so no save gives the bucket the record."""
    a_path_held_and_a_later_weekly_with_an_upload_there(world, bucket_mode=False)

    a_task_killed_at_the_start_of(world, world.data_dir, "parse")

    assert LATER_MANIFEST in world.object_keys("manifests/"), "the premise: the week was published"
    assert HELD_DIGESTS_KEY not in world.object_keys("manifests/_suppression/")
