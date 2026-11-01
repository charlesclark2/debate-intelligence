"""The bucket's run lock as the commands meet it, against moto with conditional writes (ac3).

`v1-e40-t04`, ADR-0020 (4) and the PM's rulings on the plan (2026-10-24):

* a second runner is refused while another's lease is live, and writes nothing;
* an expired lease is taken over, and the run says so;
* a runner whose lease is taken while it runs writes nothing more and ends `RUN_LOCK_LOST`;
* a bucket with no lock object is never started on;
* every command that writes to a bucket takes the lock in bucket mode, and every registered command
  is classified as one that does or one that does not;
* in local mode a bucket-writing command refuses a bucket that holds a lock object (ruling 3(a));
* (`v1-e40-t11`) once `caselist move-run-home` has held the lock for good for prod, every command that
  takes it is refused, naming the move and where the run now lives, and the release gives it back.

Another runner is played by the test writing the lock object directly, as a Mac or a task would.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

import pytest
import typer
from tests.fixtures.parse_pipeline.build_parse_world import WEEKS

from debate_cli.app import create_app
from debate_cli.build_info import BuildInfo
from debate_cli.exit_codes import ExitCode
from debate_core.application.caselist.bucket_run import BucketRun
from debate_core.application.caselist.run_lock import RUN_LOCK_KEY
from debate_core.application.caselist.run_state import BundleSave, RunState
from debate_core.application.ports.suppression import ReasonCode, SuppressionAction, SuppressionEntry

World = Any
"""`conftest.py`'s world, which a test module cannot import by name."""

WEEK_1, WEEK_2, WEEK_3 = (week.snapshot for week in WEEKS)
OTHER_RUN: Final = "20261021T104500Z"


def at(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def another_runner_holds_the_lock(world: World, *, lease_left: timedelta) -> None:
    """Another runner's lease, as that runner writes it: held, by a Mac, expiring `lease_left` from now."""
    now = world.clock.now
    body = {
        "format_version": 1,
        "home_environment": "dev",
        "state": "held",
        "holder": {"kind": "mac", "run_id": OTHER_RUN, "task": None, "command": "caselist pull"},
        "acquired_at": at(now - timedelta(minutes=30)),
        "renewed_at": at(now + lease_left - timedelta(minutes=30)),
        "lease_expires_at": at(now + lease_left),
        "took_over_from": None,
    }
    world.client.put_object(Bucket=world.bucket, Key=RUN_LOCK_KEY, Body=json.dumps(body).encode())


def seeded_with_two_weeks(world: World) -> None:
    world.listing(WEEK_1, WEEK_2)
    assert world.pull()["exit_code"] == ExitCode.OK
    world.seed()
    world.clock.advance(timedelta(days=7))
    world.listing(WEEK_1, WEEK_2, WEEK_3)


def lock_holders(world: World) -> list[str]:
    """The command of every version of the lock object a holder wrote, oldest first."""
    found: list[tuple[datetime, str]] = []
    for version in world.versions(RUN_LOCK_KEY):
        body = json.loads(
            world.client.get_object(Bucket=world.bucket, Key=RUN_LOCK_KEY, VersionId=version["VersionId"])[
                "Body"
            ].read()
        )
        if body.get("holder"):
            found.append((version["LastModified"], body["holder"]["command"]))
    return [command for _, command in sorted(found)]


# ------------------------------------------------------------------------------------------------
# One runner at a time
# ------------------------------------------------------------------------------------------------


def test_a_pull_is_refused_while_another_runners_lease_is_live_and_writes_nothing(
    world: World, tmp_path: Path
) -> None:
    seeded_with_two_weeks(world)
    another_runner_holds_the_lock(world, lease_left=timedelta(minutes=10))
    before = world.everything()
    calls = len(world.site.calls)
    empty = world.use(tmp_path / "empty")

    refused = world.pull()

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused
    assert refused["error"]["code"] == "RUN_LOCK_HELD"
    assert len(world.site.calls) == calls, "nothing listed or fetched"
    assert world.everything() == before, "a refused runner writes nothing to the bucket, its record included"
    record, details = world.last_record(empty)
    assert record["error_class"] == "RunLockHeld"
    assert details["bucket_run"]["held_by"] == f"mac run {OTHER_RUN} (`caselist pull`)"
    assert not (empty / "debate.sqlite3").exists(), "nothing was restored"


def test_an_expired_lease_is_taken_over_and_the_run_says_so(world: World, tmp_path: Path) -> None:
    seeded_with_two_weeks(world)
    another_runner_holds_the_lock(world, lease_left=-timedelta(minutes=5, seconds=1))
    world.use(tmp_path / "empty")

    pulled = world.pull()

    assert pulled["exit_code"] == ExitCode.OK, pulled
    took_over = pulled["data"]["run_details"]["bucket_run"]["took_over"]
    assert took_over.startswith(f"took over the bucket's run lock from mac run {OTHER_RUN} (`caselist pull`)")
    assert "whose lease expired at 2026-10-21T10:55:04Z" in took_over
    taken = [
        json.loads(
            world.client.get_object(Bucket=world.bucket, Key=RUN_LOCK_KEY, VersionId=v["VersionId"])[
                "Body"
            ].read()
        )
        for v in world.versions(RUN_LOCK_KEY)
    ]
    assert any(body.get("took_over_from") == OTHER_RUN for body in taken)
    assert world.lock()["state"] == "free"
    record = f"reports/sync-runs/2026/{pulled['data']['run_id']}.json"
    assert record in world.object_keys("reports/sync-runs/")


def test_a_lease_short_of_the_skew_margin_past_its_expiry_is_still_refused(
    world: World, tmp_path: Path
) -> None:
    seeded_with_two_weeks(world)
    another_runner_holds_the_lock(world, lease_left=-timedelta(minutes=4, seconds=59))
    world.use(tmp_path / "empty")

    assert world.pull()["error"]["code"] == "RUN_LOCK_HELD"


def test_a_bucket_with_no_lock_object_is_never_started_on(world: World, tmp_path: Path) -> None:
    """The safety net until the seed: nothing restored, nothing fetched, nothing written."""
    world.mode("bucket")
    world.listing(WEEK_1, WEEK_2)
    empty = world.use(tmp_path / "empty")

    refused = world.pull()

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused
    assert refused["error"]["code"] == "RUN_STATE_NOT_SEEDED"
    assert world.object_keys() == set(), "not one object, the run's record included"
    assert world.last_record(empty)[0]["error_class"] == "RunStateNotSeeded"
    assert not any(str(call.request.url).endswith(".zip") for call in world.site.calls), "no download"


def test_a_pull_whose_lease_is_taken_while_it_runs_writes_nothing_more_and_ends_run_lock_lost(
    world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The lease is taken over after the publish stage: the parse stage's publish is refused, and so
    is everything after it: the index, the bundle, the state files, the run's record."""
    seeded_with_two_weeks(world)
    published = BucketRun.after_publish
    taken_over: dict[str, Any] = {}

    async def then_taken_over(self: BucketRun) -> None:
        another_runner_holds_the_lock(world, lease_left=timedelta(minutes=30))
        taken_over.update(world.everything())
        await published(self)

    monkeypatch.setattr(BucketRun, "after_publish", then_taken_over)
    empty = world.use(tmp_path / "empty")

    lost = world.pull()

    assert lost["exit_code"] != ExitCode.OK, lost
    record, details = world.last_record(empty)
    assert record["error_class"] == "RunLockLost"
    assert details["failure_codes"] == ["RUN_LOCK_LOST"]
    assert details["bucket_run"]["lock_lost"] is True
    assert world.everything() == taken_over, "nothing written after the lease was taken"
    assert world.lock()["holder"]["run_id"] == OTHER_RUN


# ------------------------------------------------------------------------------------------------
# Every command that writes to a bucket takes the lock
# ------------------------------------------------------------------------------------------------

BUCKET_WRITING: Final = {
    "caselist backfile-import",
    "caselist pull",
    "caselist publish",
    "caselist parse",
    "caselist remove",
    "caselist unsuppress",
    "caselist retire",
    "caselist seed-run-state",
    "caselist restore-run-state",
    "caselist move-run-home",
    "landscape report",
    "tub index publish",
    "tub index prune",
    "store sync",
    "files publish",
}
"""Commands that write to an evidence bucket, in some mode of theirs (ADR-0020 (4) and the PM's ruling 2)."""

NEVER_WRITE_A_BUCKET: Final = {
    "doctor",
    "verify",
    "fetch",
    "config show",
    "caselist backfile-survey",
    "caselist cards",
    "caselist import",
    "caselist import-openev",
    "caselist reimport-openev-metadata",
    "caselist runs",
    "caselist status",
    "caselist auth login",
    "caselist auth status",
    "caselist auth logout",
    "caselist auth set-password",
    "caselist auth renew",
    "files build",
    "files check",
    "files suggest",
    "landscape evaluate",
    "store ls",
    "store get",
    "tub index build",
    "tub users add",
    "tub users list",
    "tub users reset",
    "tub users disable",
    "tub users enable",
    "tub users remove",
    "tub users email-second-factor",
    "usage",
}
"""Commands that read a bucket at most. A Secrets Manager or Cognito write is not an evidence bucket's."""


def registered_commands(group: Any, prefix: str = "") -> set[str]:
    found: set[str] = set()
    for name, command in group.commands.items():
        path = f"{prefix}{name}"
        if hasattr(command, "commands"):
            found |= registered_commands(command, f"{path} ")
        else:
            found.add(path)
    return found


def test_every_registered_command_is_classified_as_writing_a_bucket_or_not() -> None:
    """A new command fails here until someone says whether it writes a bucket, and so takes the lock."""
    registered = registered_commands(typer.main.get_command(create_app()))

    assert registered == BUCKET_WRITING | NEVER_WRITE_A_BUCKET, (
        f"unclassified: {sorted(registered - BUCKET_WRITING - NEVER_WRITE_A_BUCKET)}; "
        f"gone: {sorted((BUCKET_WRITING | NEVER_WRITE_A_BUCKET) - registered)}"
    )


def a_superseded_parsed_version(world: World) -> str:
    """An older parser version's directory in the bucket, for `caselist retire --bucket` to tag."""
    world.client.put_object(
        Bucket=world.bucket, Key="parsed/testcl26/2026.10.10-docx-2/index.jsonl", Body=b"{}\n"
    )
    return "2026.10.10-docx-2"


def a_source(world: World) -> str:
    rows = [json.loads(line) for line in world.body("manifests/testcl26/2026-09-01.jsonl").splitlines()]
    return str(next(row["sha256"] for row in rows if row.get("sha256")))


Command = Callable[[], dict[str, Any]]


def retire(world: World) -> Command:
    version = a_superseded_parsed_version(world)
    plan = world.run("caselist", "retire", "--bucket", "--version", version)
    code = plan["data"]["confirmation"]
    return lambda: world.run(
        "caselist", "retire", "--bucket", "--version", version, "--execute", "--confirm", code
    )


def unsuppress(world: World) -> Command:
    digest = a_source(world)
    entry = SuppressionEntry(
        action=SuppressionAction.SUPPRESS,
        sha256=digest,
        recorded_at=datetime(2026, 10, 20, tzinfo=UTC),
        reason=ReasonCode.REQUESTED_BY_TEAM,
        request_id="RM-2026-01",
    )
    world.client.put_object(
        Bucket=world.bucket,
        Key="manifests/_suppression/suppression-list.jsonl",
        Body=(entry.to_line() + "\n").encode(),
    )
    return lambda: world.run(
        "caselist", "unsuppress", "--sha256", digest, "--reason", "REMOVED_IN_ERROR",
        "--request", "RM-2026-01", "--execute",
    )  # fmt: skip


def remove(world: World) -> Command:
    digest = a_source(world)
    return lambda: world.run(
        "caselist", "remove", "--source", digest, "--reason", "REQUESTED_BY_TEAM", "--request", "RM-2026-02",
        "--execute",
    )  # fmt: skip


def restore_run_state(world: World) -> Command:
    """`v1-e40-t06`'s restore: it writes only the lock to the bucket, and takes it like every writer."""
    return lambda: world.run(
        "caselist", "restore-run-state", "--into", str(world.root / "restored-copy"), "--caselist", "testcl26"
    )


def files_publish(world: World) -> Command:
    """`v1-e33-t05`'s publish of a `.docx` with no quality report: refused by its gate, inside the lock."""
    built = world.root / "built" / "synthetic-file.docx"
    built.parent.mkdir(parents=True, exist_ok=True)
    built.write_bytes(b"not checked")
    return lambda: world.run("files", "publish", "--env", "dev", str(built))


def running(*arguments: str) -> Callable[[World], Command]:
    return lambda world: lambda: world.run(*arguments)


COMMANDS: Final[dict[str, Callable[[World], Command]]] = {
    "caselist publish": running("caselist", "publish", "--caselist", "testcl26"),
    "caselist parse --publish": running("caselist", "parse", "--caselist", "testcl26", "--publish"),
    "caselist parse --publish-only": running("caselist", "parse", "--caselist", "testcl26", "--publish-only"),
    "tub index publish": running("tub", "index", "publish", "--env", "dev", "--newest"),
    "store sync --push": running("store", "sync", "--apply", "--prefix", "manifests/"),
    "caselist retire --bucket": retire,
    "caselist unsuppress": unsuppress,
    "caselist remove": remove,
    "caselist restore-run-state": restore_run_state,
    "files publish": files_publish,
}
"""Each bucket-writing command but the pull and the seed, by the name it takes the lock under: its setup,
then the command. `landscape report --publish` has its own world (`test_landscape_command.py`)."""


@pytest.mark.parametrize("command", sorted(COMMANDS))
def test_each_bucket_writing_command_takes_the_lock_in_bucket_mode_and_releases_it(
    world: World, command: str
) -> None:
    """Whatever the command then does, its lock's versions show it held the lease, and it is free after."""
    seeded_with_two_weeks(world)
    run = COMMANDS[command](world)

    run()

    assert command in lock_holders(world), f"{command} never took the lock: {lock_holders(world)}"
    assert world.lock()["state"] == "free"


@pytest.mark.parametrize("command", sorted(COMMANDS))
def test_each_bucket_writing_command_is_refused_while_another_runner_holds_the_lock(
    world: World, command: str
) -> None:
    seeded_with_two_weeks(world)
    run = COMMANDS[command](world)
    another_runner_holds_the_lock(world, lease_left=timedelta(minutes=10))
    before = world.everything()

    refused = run()

    assert refused["exit_code"] != ExitCode.OK, refused
    assert refused["error"]["code"] == "RUN_LOCK_HELD", refused["error"]
    assert world.everything() == before


# ------------------------------------------------------------------------------------------------
# Local mode on a seeded bucket (the PM's ruling 3(a))
# ------------------------------------------------------------------------------------------------


def test_in_local_mode_a_bucket_writing_command_refuses_a_bucket_that_holds_a_lock_object(
    world: World,
) -> None:
    seeded_with_two_weeks(world)
    world.mode("local")
    before = world.everything()

    refused = world.run("caselist", "publish", "--caselist", "testcl26")

    assert refused["error"]["code"] == "BUCKET_KEEPS_RUN_STATE", refused
    assert "set caselist.run_state = bucket" in refused["error"]["message"]
    assert world.everything() == before


def test_in_local_mode_a_pull_refuses_a_seeded_bucket_before_it_downloads_and_keeps_its_record_local(
    world: World,
) -> None:
    seeded_with_two_weeks(world)
    world.mode("local")
    before = world.everything()
    calls = len(world.site.calls)

    refused = world.pull()

    assert refused["error"]["code"] == "BUCKET_KEEPS_RUN_STATE", refused
    assert world.everything() == before
    assert len(world.site.calls) == calls, "nothing listed or fetched"
    assert world.last_record()[0]["error_class"] == "BucketKeepsRunState"


def test_in_local_mode_a_bucket_with_no_lock_object_changes_nothing(world: World) -> None:
    """Before the seed, the Mac's runs go on exactly as they did."""
    world.listing(WEEK_1, WEEK_2)

    pulled = world.pull()

    assert pulled["exit_code"] == ExitCode.OK, pulled
    assert RUN_LOCK_KEY not in world.object_keys()
    assert pulled["data"]["run_details"]["bucket_run"] is None


def test_a_run_whose_lease_is_taken_ends_run_lock_lost_even_with_nothing_left_to_write(
    world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bundle that is not saved writes nothing, so no fence refusal tells the run: it asks the lease."""
    seeded_with_two_weeks(world)
    published = BucketRun.after_publish

    async def then_taken_over(self: BucketRun) -> None:
        await published(self)
        another_runner_holds_the_lock(world, lease_left=timedelta(minutes=30))

    async def not_saved(self: RunState) -> BundleSave:
        return BundleSave(saved=False, reason="not saved: a manifest is not yet confirmed in the bucket")

    monkeypatch.setattr(BucketRun, "after_publish", then_taken_over)
    monkeypatch.setattr(RunState, "save_bundle", not_saved)
    empty = world.use(tmp_path / "empty")

    lost = world.pull()

    assert lost["exit_code"] != ExitCode.OK, lost
    record, details = world.last_record(empty)
    assert (record["error_class"], details["failure_codes"]) == ("RunLockLost", ["RUN_LOCK_LOST"])


# ------------------------------------------------------------------------------------------------
# The run's home moved to prod (`v1-e40-t11`, ADR-0020 (7) step 3)
# ------------------------------------------------------------------------------------------------

MOVED: Final = (
    "the weekly run now runs from prod: this bucket's run lock (reports/sync/run-lock.json) is held "
    "for good since "
)


def the_run_home_moved(world: World) -> dict[str, Any]:
    """`caselist move-run-home --execute`, as the promotion runs it: dev, bucket mode."""
    world.mode("bucket")
    moved = world.run("caselist", "move-run-home", "--execute")
    assert moved["exit_code"] == ExitCode.OK, moved
    return moved


def test_move_run_home_plans_then_holds_the_lock_for_good_then_releases_it(world: World) -> None:
    seeded_with_two_weeks(world)
    stamped = BuildInfo(
        version="1.1.0", channel="dev", commit="0" * 40, tag="v1.1.0-dev.999", built_at=None, run_id=None
    )
    world.monkeypatch.setattr("debate_cli.container.current_build_info", lambda: stamped)
    now = at(world.clock.now)
    expected = {
        "format_version": 1,
        "home_environment": "prod",
        "state": "held",
        "holder": {
            "kind": "moved",
            "run_id": now.replace("-", "").replace(":", ""),
            "task": None,
            "command": "caselist move-run-home",
            "by": "mac",
            "build": "v1.1.0-dev.999",
        },
        "acquired_at": now,
        "renewed_at": None,
        "lease_expires_at": None,
        "took_over_from": None,
    }
    before = world.everything()

    planned = world.run("caselist", "move-run-home")

    assert planned["exit_code"] == ExitCode.OK, planned
    assert (planned["data"]["applied"], planned["data"]["release"]) == (False, False)
    assert (planned["data"]["found"]["state"], planned["data"]["found"]["home_environment"]) == (
        "free",
        "dev",
    )
    assert planned["data"]["written"] == expected
    assert world.everything() == before, "the dry run writes nothing"

    moved = the_run_home_moved(world)

    assert moved["data"]["applied"] is True
    assert moved["data"]["written"] == expected == world.lock()
    assert "caselist move-run-home" in lock_holders(world), "written under the move's own lease"
    moved_version = world.everything()

    release_planned = world.run("caselist", "move-run-home", "--release")

    assert release_planned["exit_code"] == ExitCode.OK, release_planned
    assert (release_planned["data"]["applied"], release_planned["data"]["release"]) == (False, True)
    assert release_planned["data"]["found"] == expected
    assert world.everything() == moved_version, "the release's dry run writes nothing"

    released = world.run("caselist", "move-run-home", "--release", "--execute")

    assert released["exit_code"] == ExitCode.OK, released
    assert world.lock() == {
        "format_version": 1,
        "home_environment": "dev",
        "state": "free",
        "holder": None,
        "acquired_at": None,
        "renewed_at": now,
        "lease_expires_at": None,
        "took_over_from": None,
    }
    assert world.pull()["exit_code"] == ExitCode.OK, "dev's run takes its lock again"


def test_move_run_home_is_refused_while_a_run_holds_the_lock_naming_it(world: World) -> None:
    seeded_with_two_weeks(world)
    another_runner_holds_the_lock(world, lease_left=timedelta(minutes=10))
    before = world.everything()

    for arguments in ((), ("--execute",)):
        refused = world.run("caselist", "move-run-home", *arguments)

        assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused
        assert refused["error"]["code"] == "RUN_LOCK_HELD"
        assert (
            f"mac run {OTHER_RUN} (`caselist pull`) holds the bucket's run lock"
            in refused["error"]["message"]
        )
    assert world.everything() == before


def test_the_release_is_refused_when_no_move_holds_the_lock(world: World) -> None:
    seeded_with_two_weeks(world)
    before = world.everything()

    refused = world.run("caselist", "move-run-home", "--release", "--execute")

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused
    assert refused["error"]["code"] == "RUN_HOME_NOT_MOVED"
    assert world.everything() == before


@pytest.mark.parametrize("command", sorted(COMMANDS))
def test_each_bucket_writing_command_is_refused_after_the_run_home_moved_naming_the_move(
    world: World, command: str
) -> None:
    seeded_with_two_weeks(world)
    run = COMMANDS[command](world)
    the_run_home_moved(world)
    before = world.everything()

    refused = run()

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused
    assert refused["error"]["code"] == "RUN_HOME_MOVED", refused["error"]
    assert refused["error"]["message"].startswith(MOVED), refused["error"]["message"]
    assert "(`caselist move-run-home`, from a mac, build " in refused["error"]["message"]
    assert "caselist move-run-home --release" in refused["error"]["hint"]
    assert world.everything() == before


def test_a_pull_after_the_run_home_moved_is_refused_naming_the_move_and_keeps_its_record_local(
    world: World, tmp_path: Path
) -> None:
    seeded_with_two_weeks(world)
    the_run_home_moved(world)
    before = world.everything()
    calls = len(world.site.calls)
    empty = world.use(tmp_path / "empty")

    refused = world.pull()

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused
    assert refused["error"]["code"] == "RUN_HOME_MOVED"
    assert refused["error"]["message"].startswith(MOVED)
    assert len(world.site.calls) == calls, "nothing listed or fetched"
    assert world.everything() == before
    assert world.last_record(empty)[0]["error_class"] == "RunHomeMoved"


def test_the_seed_after_the_run_home_moved_is_refused_naming_the_move(world: World) -> None:
    seeded_with_two_weeks(world)
    the_run_home_moved(world)
    before = world.everything()

    refused = world.run("caselist", "seed-run-state")

    assert refused["error"]["code"] == "SEED_REFUSED", refused
    assert MOVED in refused["error"]["message"]
    assert world.everything() == before


def test_in_local_mode_a_command_after_the_run_home_moved_is_refused_naming_the_move(world: World) -> None:
    seeded_with_two_weeks(world)
    the_run_home_moved(world)
    world.mode("local")
    before = world.everything()

    refused = world.run("caselist", "publish", "--caselist", "testcl26")

    assert refused["error"]["code"] == "RUN_HOME_MOVED", refused
    assert refused["error"]["message"].startswith(MOVED)
    assert world.everything() == before
