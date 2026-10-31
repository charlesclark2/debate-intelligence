"""A week a killed run published is parsed by the next run, not left for the next import (`v1-e40-t08`).

A publish records a parse owed, per caselist and snapshot, in the run's state files: the data
directory's `caselist-sync-parse-owed.json`, saved to `reports/sync/state/` as it is written in bucket
mode. The entry is cleared only when that caselist's parsed store is published complete, so a parse
whose publish failed stays owed. A run that starts with entries owed parses and publishes those
caselists first, though it imports nothing. A parser version the store has no directory of owes a
full parse of every caselist the run follows, `openev` included, before the index stage.
`caselist runs` and `caselist status` say what is owed, and a removal that reaches a snapshot clears
its entry.

Through the real command and composition root, over moto's bucket and the fictional caselist, as the
rest of this directory runs (`conftest.py`). The kills are `v1-e40-t04`'s harness
(`test_bucket_mode_kills.py`). Every file body expected here is written by hand from the fixture:
weeks 2026-09-01, 2026-09-08 and 2026-09-15 of `testcl26`, and one camp file in release
`2026-policy` (working agreement 6).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any, Final

import pytest
from tests.fixtures.parse_pipeline.build_parse_world import CASELIST, WEEKS, digest_of

from debate_cli.exit_codes import ExitCode
from debate_core.application.caselist_pull_parse import PullParseStage
from debate_core.application.caselist_sync import PublishedParsedStore
from debate_core.application.errors import StoreUnavailable
from debate_core.application.sync_runs import SyncRunDetails, SyncRunRecord, notifications_for
from debate_core.integrations.docx_parser import DebateDocxParser

from .test_bucket_mode_kills import Killed, KillSwitch, an_uninterrupted_week, evidence, kill_at_stage

World = Any
"""`conftest.py`'s world, which a test module cannot import by name."""

WEEK_1, WEEK_2, WEEK_3 = (week.snapshot for week in WEEKS)

PARSE_OWED_FILE: Final = "caselist-sync-parse-owed.json"
PARSE_OWED_KEY: Final = f"reports/sync/state/{PARSE_OWED_FILE}"

WEEK_3_OWED: Final = {"full_parses": [], "snapshots": [{"caselist": CASELIST, "snapshot": "2026-09-15"}]}
"""What a run killed after publishing week three owes: that week's parse, and nothing else."""

FIRST_PULL_OWED: Final = {
    "full_parses": [],
    "snapshots": [
        {"caselist": CASELIST, "snapshot": "2026-09-01"},
        {"caselist": CASELIST, "snapshot": "2026-09-08"},
        {"caselist": "openev", "snapshot": "2026-policy"},
    ],
}
"""What a first pull killed after its publish owes: both weeks, then the camp release, in import order."""

BUMPED: Final = "2099.01.01-docx-9"
"""A parser version later than the one the store was parsed under."""

CLOUD_CURE: Final = (
    f"the next cloud run publishes the parsed store of {CASELIST}: the weekly run, or one started by hand "
    '(caselist-cloud-run.md, "A failed parse stage"); never a publish from the operator\'s Mac'
)
"""`v1-e40-t18`'s cure without "that imports into": the next run publishes it whatever it imports."""

CLOUD_HINT: Final = (
    f"The cloud run publishes the parsed store of {CASELIST}, never the operator's Mac, whose working "
    "copy is not the one the cloud run owns: the next weekly run rebuilds it and publishes it, whether "
    "or not it imports into the caselist, and so does a run started by hand "
    '(caselist-cloud-run.md, "A failed parse stage").'
)

OWED_SENTENCE: Final = (
    f"Parse owed: {CASELIST} 2026-09-15. The next caselist pull parses and publishes it, whether or not "
    "it imports anything."
)
"""What `caselist runs` and `caselist status` say of :data:`WEEK_3_OWED`."""


def owed_here(data_dir: Path) -> dict[str, Any] | None:
    """The data directory's parse-owed file, or `None` when it is not there: nothing owed."""
    path = data_dir / PARSE_OWED_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def owed_in_the_bucket(world: World) -> dict[str, Any] | None:
    """The bucket's copy, `None` for the empty object that records a removed file."""
    body = world.body(PARSE_OWED_KEY)
    return json.loads(body) if body else None


@pytest.fixture
def parses(world: World) -> Iterator[list[str]]:
    """Every caselist the parse stage hands the pipeline, in order."""
    called: list[str] = []
    parse = PullParseStage.parse_new_sources

    async def recorded(self: PullParseStage, caselist: str) -> Any:
        called.append(caselist)
        return await parse(self, caselist)

    world.monkeypatch.setattr(PullParseStage, "parse_new_sources", recorded)
    yield called


def killed_at_parse(world: World) -> None:
    """A pull killed as its parse stage starts: after its publish, and after the bundle's save."""
    with pytest.MonkeyPatch.context() as killing:
        switch = KillSwitch()
        switch.install(killing)
        kill_at_stage(killing, switch, "parse")
        with pytest.raises(Killed):
            world.invoke("--json", "caselist", "pull", "--caselist", CASELIST)


def week_three_killed_in_local_mode(world: World) -> None:
    """The Mac's two weeks pulled whole, then week three's run killed after its publish."""
    world.listing(WEEK_1, WEEK_2)
    assert world.pull()["exit_code"] == ExitCode.OK
    world.clock.advance(timedelta(days=7))
    world.listing(WEEK_1, WEEK_2, WEEK_3)
    killed_at_parse(world)


def seeded(world: World) -> None:
    """The Mac's two weeks, published and seeded, and week three on the site for the cloud run to come."""
    world.listing(WEEK_1, WEEK_2)
    assert world.pull()["exit_code"] == ExitCode.OK
    world.seed()
    world.clock.advance(timedelta(days=7))
    world.listing(WEEK_1, WEEK_2, WEEK_3)


def stage(pulled: dict[str, Any], name: str) -> dict[str, Any]:
    [found] = [one for one in pulled["data"]["stages"] if one["stage"] == name]
    return found


def flat(text: str) -> str:
    """Rich wraps a caption at the table's width: words alone are compared."""
    return " ".join(text.split())


# ------------------------------------------------------------------------------------------------
# ac1: a run killed after its publish owes the parse, and the next run parses it first
# ------------------------------------------------------------------------------------------------


def test_a_local_run_killed_after_its_publish_owes_the_parse_and_the_next_run_parses_it(
    world: World, parses: list[str]
) -> None:
    week_three_killed_in_local_mode(world)

    assert owed_here(world.data_dir) == WEEK_3_OWED, "owed per caselist and snapshot, written at the publish"
    parses.clear()
    following = world.pull()

    assert following["exit_code"] == ExitCode.OK, following
    assert following["data"]["snapshots_imported"] == [], "the premise: nothing new to import"
    assert parses == [CASELIST], "the owed caselist is parsed though the run imported nothing"
    assert following["data"]["parse"]["attempted"] == 1, "week three's one new source, `direct`"
    assert stage(following, "parse")["outcome"] == "completed"
    assert owed_here(world.data_dir) is None, "cleared once the parsed store was published complete"
    assert world.pull()["data"]["parse"] is None, "and owed nothing after: the run after parses nothing"


def test_a_bucket_mode_run_killed_after_its_publish_owes_the_parse_in_the_bucket_and_the_next_run_parses_it(
    world: World, tmp_path: Path, parses: list[str]
) -> None:
    seeded(world)
    uninterrupted = an_uninterrupted_week(world, tmp_path)
    world.use(tmp_path / "killed")
    killed_at_parse(world)

    assert owed_in_the_bucket(world) == WEEK_3_OWED, "saved to the bucket as it was written"
    world.clock.advance(timedelta(minutes=36))
    world.use(tmp_path / "next")
    parses.clear()
    following = world.pull()

    assert following["exit_code"] == ExitCode.OK, following
    assert following["data"]["snapshots_imported"] == []
    assert parses == [CASELIST]
    assert owed_in_the_bucket(world) is None, "cleared in the bucket too"
    assert evidence(world) == uninterrupted, "parsed, published and indexed as an uninterrupted run leaves it"


def test_owed_caselists_are_parsed_before_the_ones_the_run_imports_into(
    world: World, tmp_path: Path, parses: list[str]
) -> None:
    """A first pull killed after its publish owes `testcl26` and `openev`. The next run imports week
    three into `testcl26`, the caselist it follows first; the owed ones come first all the same,
    `openev` before what the run imported."""
    world.listing(WEEK_1, WEEK_2)
    killed_at_parse(world)
    assert owed_here(world.data_dir) == FIRST_PULL_OWED
    world.listing(WEEK_1, WEEK_2, WEEK_3)
    parses.clear()

    following = world.pull()

    assert following["exit_code"] == ExitCode.OK, following
    assert following["data"]["snapshots_imported"] == [f"{CASELIST} 2026-09-15"]
    assert parses == [CASELIST, "openev"], "the owed, in the order owed, then nothing more: testcl26 is both"
    assert owed_here(world.data_dir) is None


def test_a_parse_owed_for_a_caselist_the_run_does_not_follow_is_left_owed_and_said(
    world: World, parses: list[str]
) -> None:
    """Its parsed store is not restored, in bucket mode, for a caselist the run does not follow, and a
    caselist retired since is not the run's to publish: the entry waits for a run that follows it."""
    world.listing(WEEK_1, WEEK_2)
    assert world.pull()["exit_code"] == ExitCode.OK
    other: dict[str, Any] = {
        "full_parses": [],
        "snapshots": [{"caselist": "hsld26", "snapshot": "2026-09-08"}],
    }
    (world.data_dir / PARSE_OWED_FILE).write_text(json.dumps(other), encoding="utf-8")
    parses.clear()

    following = world.pull()

    assert following["exit_code"] == ExitCode.OK, following
    assert parses == []
    assert stage(following, "parse")["reason"] == (
        "nothing new was imported; the parse owed for hsld26 is left owed, as this run does not follow it"
    )
    assert owed_here(world.data_dir) == other


# ------------------------------------------------------------------------------------------------
# ac3: a parse whose publish failed stays owed, and the next run publishes it; the cure says so
# ------------------------------------------------------------------------------------------------


async def refused(self: PullParseStage, caselist: str, version: str) -> Any:
    """The bucket does not answer: the publish raises."""
    raise StoreUnavailable("PutObject", f"parsed/{caselist}", "SlowDown")


async def unconfirmed(self: PullParseStage, caselist: str, version: str) -> PublishedParsedStore:
    """The publish ends, and reports an object the bucket did not confirm."""
    return PublishedParsedStore(uploaded=8, failure_codes=("CHECKSUM_MISMATCH",))


@pytest.mark.parametrize(
    ("failed_publish", "codes"),
    [(refused, ["STORE_UNAVAILABLE"]), (unconfirmed, ["CHECKSUM_MISMATCH"])],
    ids=["raised", "reported"],
)
def test_a_parse_whose_publish_failed_stays_owed_and_the_next_run_publishes_it_though_it_imports_nothing(
    world: World, tmp_path: Path, parses: list[str], failed_publish: Any, codes: list[str]
) -> None:
    seeded(world)
    uninterrupted = an_uninterrupted_week(world, tmp_path)
    world.use(tmp_path / "refused")
    parses.clear()
    with pytest.MonkeyPatch.context() as refusing:
        refusing.setattr(PullParseStage, "publish", failed_publish)
        pulled = world.pull()

    assert pulled["exit_code"] == ExitCode.OK, pulled
    parse = stage(pulled, "parse")
    assert (parse["outcome"], parse["error_codes"]) == ("failed", codes)
    assert parses == [CASELIST], "the premise: the parse itself ran"
    assert owed_in_the_bucket(world) == WEEK_3_OWED, "a parse whose publish failed is still owed"
    assert parse["hint"] == CLOUD_HINT
    record, details = world.last_record()
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
    assert "that imports into" not in banner.text

    world.use(tmp_path / "next")
    parses.clear()
    following = world.pull()

    assert following["exit_code"] == ExitCode.OK, following
    assert following["data"]["snapshots_imported"] == []
    assert parses == [CASELIST]
    assert stage(following, "parse")["outcome"] == "completed"
    assert owed_in_the_bucket(world) is None
    assert evidence(world) == uninterrupted


# ------------------------------------------------------------------------------------------------
# A parser version the store has no directory of
# ------------------------------------------------------------------------------------------------


def test_a_parser_version_the_store_has_no_directory_of_owes_a_full_parse_of_every_caselist_followed(
    world: World, tmp_path: Path, parses: list[str]
) -> None:
    """The first run on a new image, a week with nothing new: it parses `testcl26` and `openev` in
    full under the new version, publishes both, and builds and publishes an index of that version."""
    world.listing(WEEK_1, WEEK_2)
    assert world.pull()["exit_code"] == ExitCode.OK
    world.seed()
    world.clock.advance(timedelta(days=7))
    world.use(tmp_path / "new-image")
    world.monkeypatch.setattr(DebateDocxParser, "parser_version", property(lambda _: BUMPED))
    parses.clear()

    pulled = world.pull()

    assert pulled["exit_code"] == ExitCode.OK, pulled
    assert pulled["data"]["snapshots_imported"] == [], "the premise: nothing new to import"
    assert parses == [CASELIST, "openev"], "every caselist the run follows, openev included"
    assert pulled["data"]["parse"]["full_parses"] == 2
    for store in (CASELIST, "openev"):
        assert world.object_keys(f"parsed/{store}/{BUMPED}/"), f"{store}'s new version is published"
    # Built from the new version's directories, where before it failed for want of one. A relabelled
    # parser reads the same cards, so the index is the published one's twin and is not published
    # again; a real bump's is another index.
    assert stage(pulled, "search_index")["outcome"] == "completed", stage(pulled, "search_index")
    assert pulled["data"]["search_index"]["built"] is True
    assert owed_in_the_bucket(world) is None, "nothing left owed"


def test_a_full_parse_cut_short_is_still_owed_by_the_next_run(world: World, tmp_path: Path) -> None:
    """Killed as it publishes the new version's parsed store, part of which is in the bucket: the
    entry says so, and the next run finishes it rather than reading the part as a directory held."""
    world.listing(WEEK_1, WEEK_2)
    assert world.pull()["exit_code"] == ExitCode.OK
    world.seed()
    world.clock.advance(timedelta(days=7))
    world.monkeypatch.setattr(DebateDocxParser, "parser_version", property(lambda _: BUMPED))
    world.use(tmp_path / "killed")
    publish = PullParseStage.publish
    with pytest.MonkeyPatch.context() as killing:
        switch = KillSwitch()
        switch.install(killing)

        async def killed_after_the_first(self: PullParseStage, caselist: str, version: str) -> Any:
            # A few writes in: each named object's write is a lease renewal and the object.
            switch.kill_at_write = switch.writes + 6
            return await publish(self, caselist, version)

        killing.setattr(PullParseStage, "publish", killed_after_the_first)
        with pytest.raises(Killed):
            world.invoke("--json", "caselist", "pull", "--caselist", CASELIST)

    assert 0 < len(world.object_keys(f"parsed/{CASELIST}/{BUMPED}/")) < 9, (
        "the premise: part of it is in the bucket"
    )
    assert owed_in_the_bucket(world) == {
        "full_parses": [
            {"caselist": CASELIST, "parser_version": BUMPED},
            {"caselist": "openev", "parser_version": BUMPED},
        ],
        "snapshots": [],
    }
    world.clock.advance(timedelta(minutes=36))
    world.use(tmp_path / "next")

    following = world.pull()

    assert following["exit_code"] == ExitCode.OK, following
    assert world.object_keys(f"parsed/openev/{BUMPED}/")
    assert stage(following, "search_index")["outcome"] == "completed", stage(following, "search_index")
    assert following["data"]["search_index"]["built"] is True
    assert owed_in_the_bucket(world) is None


# ------------------------------------------------------------------------------------------------
# ac2: what is owed is said, and a removal that reaches a snapshot clears its entry
# ------------------------------------------------------------------------------------------------


def test_caselist_runs_and_caselist_status_say_a_parse_is_owed(world: World) -> None:
    week_three_killed_in_local_mode(world)

    runs = world.run("caselist", "runs")
    status = world.run("caselist", "status", "--caselist", CASELIST)

    assert runs["data"]["parses_owed"] == WEEK_3_OWED
    assert status["data"]["parses_owed"] == WEEK_3_OWED
    assert OWED_SENTENCE in flat(world.invoke("caselist", "runs").output)
    assert OWED_SENTENCE in flat(world.invoke("caselist", "status", "--caselist", CASELIST).output)


def test_caselist_runs_remote_says_what_the_cloud_run_owes(world: World, tmp_path: Path) -> None:
    seeded(world)
    world.use(tmp_path / "killed")
    killed_at_parse(world)
    world.mode("local")
    world.use(tmp_path / "the-macs-copy")

    runs = world.run("caselist", "runs", "--remote")

    assert runs["data"]["parses_owed"] == WEEK_3_OWED, "the bucket's state file, not this machine's"


def test_nothing_owed_is_said_as_nothing(world: World) -> None:
    world.listing(WEEK_1, WEEK_2)
    assert world.pull()["exit_code"] == ExitCode.OK

    assert world.run("caselist", "runs")["data"]["parses_owed"] == {"full_parses": [], "snapshots": []}
    assert "Parse owed" not in world.invoke("caselist", "runs").output


def test_a_removal_that_reaches_a_snapshot_clears_its_entry_and_no_other(world: World) -> None:
    """`wiki` is disclosed in 09-01 and every week after: a removal of it reaches both weeks a first
    pull owes, and not the camp release."""
    world.listing(WEEK_1, WEEK_2)
    killed_at_parse(world)
    assert owed_here(world.data_dir) == FIRST_PULL_OWED
    world.monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", "debate-dev-evidence-removal")

    removed = world.run(
        "caselist", "remove", "--source", digest_of("wiki"), "--reason", "REQUESTED_BY_TEAM",
        "--request", "RM-2026-03", "--execute",
    )  # fmt: skip

    assert removed["exit_code"] == ExitCode.OK, removed
    assert owed_here(world.data_dir) == {
        "full_parses": [],
        "snapshots": [{"caselist": "openev", "snapshot": "2026-policy"}],
    }


def test_a_bucket_mode_removal_clears_the_entry_in_the_bucket(world: World, tmp_path: Path) -> None:
    seeded(world)
    world.use(tmp_path / "killed")
    killed_at_parse(world)
    assert owed_in_the_bucket(world) == WEEK_3_OWED
    world.clock.advance(timedelta(minutes=36))
    world.use(tmp_path / "the-removal")
    world.monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", "debate-dev-evidence-removal")
    # The killed run's lease is past; a removal takes the lock over as a run does.

    removed = world.run(
        "caselist", "remove", "--source", digest_of("wiki"), "--reason", "REQUESTED_BY_TEAM",
        "--request", "RM-2026-03", "--execute",
    )  # fmt: skip

    assert removed["exit_code"] == ExitCode.OK, removed
    assert owed_in_the_bucket(world) is None


# ------------------------------------------------------------------------------------------------
# What the file may hold
# ------------------------------------------------------------------------------------------------


def test_the_parse_owed_file_holds_caselist_slugs_snapshot_names_and_a_parser_version_alone(
    world: World,
) -> None:
    """No school, team code or path (the spec's forbidden list): the whole file is compared."""
    world.listing(WEEK_1, WEEK_2)
    killed_at_parse(world)

    written = (world.data_dir / PARSE_OWED_FILE).read_text(encoding="utf-8")

    assert written == json.dumps(FIRST_PULL_OWED, sort_keys=True, indent=2) + "\n"
