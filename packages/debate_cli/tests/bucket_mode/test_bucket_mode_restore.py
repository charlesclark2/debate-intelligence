"""A run on an empty data directory restores what it needs and does what a run on a full one does (ac1).

`v1-e40-t04`, ADR-0020 (3). Each test builds the week the cloud run would find: two weeks pulled on
"the Mac" in local mode, published, parsed and indexed into the bucket, then the bucket seeded from
that directory. Week three is then pulled in bucket mode twice, against two copies of the same
bucket: once on the Mac's full directory and once on an empty one, as the cloud task starts. The two
must parse the same sources into the same files and publish the same index.

The world is `conftest.py`'s: moto's S3, the fictional site, the real pipeline.
"""

from __future__ import annotations

import json
import shutil
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

from tests.fixtures.parse_pipeline.build_parse_world import WEEKS

from debate_cli.exit_codes import ExitCode
from debate_core.application.caselist.run_state import RUN_STATE_BUNDLE_KEY, STATE_PREFIX
from debate_core.application.ports.suppression import ReasonCode, SuppressionAction, SuppressionEntry
from debate_core.application.search_index_refresh import RESTORED_INDEX_MARKER

World = Any
"""`conftest.py`'s world, which a test module cannot import by name."""

WEEK_1, WEEK_2, WEEK_3 = (week.snapshot for week in WEEKS)
ORIGINAL: Final = "debate-dev-evidence-moto"

COPY = "debate-dev-evidence-moto-copy"


def stage(envelope: dict[str, Any], name: str) -> dict[str, Any]:
    summary = envelope["data"] or envelope["error"]["details"]
    [found] = [one for one in summary["stages"] if one["stage"] == name]
    return found


def the_macs_two_weeks_seeded(world: World, *, parse: bool = True) -> Path:
    """Weeks one and two pulled on the Mac in local mode, then the bucket seeded from its directory."""
    if not parse:
        world.monkeypatch.setenv("DEBATE_CASELIST__PARSE_IMPORTED_SOURCES", "false")
        world.monkeypatch.setenv("DEBATE_CASELIST__REFRESH_SEARCH_INDEX", "false")
    world.listing(WEEK_1, WEEK_2)
    first = world.pull()
    assert first["exit_code"] == ExitCode.OK, first
    world.seed()
    world.monkeypatch.delenv("DEBATE_CASELIST__PARSE_IMPORTED_SOURCES", raising=False)
    world.monkeypatch.delenv("DEBATE_CASELIST__REFRESH_SEARCH_INDEX", raising=False)
    world.clock.advance(timedelta(days=7))
    world.listing(WEEK_1, WEEK_2, WEEK_3)
    return world.data_dir


def comparable(world: World) -> dict[str, str]:
    """The bucket's evidence by key and ETag: everything but the run's own record, state and lock."""
    return {
        key: etag
        for key, etag in world.everything().items()
        if not key.startswith(("reports/sync", "manifests/_run-state/"))
    }


def test_a_run_on_an_empty_data_directory_parses_and_indexes_what_a_run_on_the_full_one_does(
    world: World, tmp_path: Path
) -> None:
    full = the_macs_two_weeks_seeded(world)
    world.copy_bucket(COPY)
    mac_copy = tmp_path / "mac-copy"
    shutil.copytree(full, mac_copy)

    world.use(mac_copy)
    on_the_full_directory = world.pull()
    world.use_bucket(COPY)
    empty = world.use(tmp_path / "empty")
    on_an_empty_directory = world.pull()

    for envelope in (on_the_full_directory, on_an_empty_directory):
        assert envelope["exit_code"] == ExitCode.OK, envelope
    assert on_an_empty_directory["data"]["parse"] == on_the_full_directory["data"]["parse"]
    assert on_an_empty_directory["data"]["parse"]["attempted"] == 1, (
        "week three's one new source, not a re-parse"
    )
    assert world.parsed_digests(empty) == world.parsed_digests(mac_copy)
    restored = on_an_empty_directory["data"]["run_details"]["bucket_run"]["restore"]
    assert restored["parsed_objects"] > 0
    assert restored["state_files"] == 5
    copied_index = world.published_index()
    world.use_bucket(ORIGINAL)
    original_index = world.published_index()
    assert copied_index == original_index, "the same stores, the same index, byte for byte"
    copied = comparable(world)
    world.use_bucket(COPY)
    assert comparable(world) == copied


def test_a_run_on_an_empty_directory_where_the_bucket_holds_no_parsed_store_fetches_raw_and_parses_all(
    world: World, tmp_path: Path
) -> None:
    """A version directory the bucket does not hold is a full parse, from sources fetched from `raw/`."""
    full = the_macs_two_weeks_seeded(world, parse=False)
    assert not world.keys("parsed/")
    world.copy_bucket(COPY)
    mac_copy = tmp_path / "mac-copy"
    shutil.copytree(full, mac_copy)

    world.use(mac_copy)
    on_the_full_directory = world.pull()
    world.use_bucket(COPY)
    empty = world.use(tmp_path / "empty")
    on_an_empty_directory = world.pull()

    assert on_an_empty_directory["exit_code"] == ExitCode.OK, on_an_empty_directory
    assert on_an_empty_directory["data"]["parse"] == on_the_full_directory["data"]["parse"]
    assert on_an_empty_directory["data"]["parse"]["attempted"] == 7, "all seven of testcl26's sources, afresh"
    assert on_an_empty_directory["data"]["parse"]["full_parses"] == 1
    assert world.parsed_digests(empty) == world.parsed_digests(mac_copy)
    assert on_an_empty_directory["data"]["run_details"]["bucket_run"]["restore"]["parsed_objects"] == 0


def test_a_parsed_file_whose_bytes_are_not_the_publishers_stops_the_restore(
    world: World, tmp_path: Path
) -> None:
    the_macs_two_weeks_seeded(world)
    [key] = sorted(key for key in world.keys("parsed/testcl26/") if key.endswith("index.jsonl"))
    head = world.client.head_object(Bucket=world.bucket, Key=key)
    world.client.put_object(
        Bucket=world.bucket, Key=key, Body=b"not what was published\n", Metadata=head["Metadata"]
    )
    world.use(tmp_path / "empty")

    refused = world.pull()

    assert refused["exit_code"] != ExitCode.OK, refused
    _, details = world.last_record()
    assert details["failure_codes"] == ["BLOB_INTEGRITY_ERROR"]
    assert world.lock()["state"] == "free", "the lock is released whatever the run ended on"
    assert not (tmp_path / "empty" / "parsed" / key.removeprefix("parsed/")).exists()


def test_a_bundle_holding_a_manifest_the_publisher_withholds_is_never_restored(
    world: World, tmp_path: Path
) -> None:
    """A removal made since the bundle was saved stops it being restored, in the publisher's words."""
    the_macs_two_weeks_seeded(world)
    rows = [json.loads(line) for line in world.body("manifests/testcl26/2026-09-01.jsonl").splitlines()]
    suppressed = next(row["sha256"] for row in rows if row.get("sha256"))
    entry = SuppressionEntry(
        action=SuppressionAction.SUPPRESS,
        sha256=suppressed,
        recorded_at=datetime(2026, 10, 20, tzinfo=UTC),
        reason=ReasonCode.REQUESTED_BY_TEAM,
        request_id="RM-2026-01",
    )
    world.client.put_object(
        Bucket=world.bucket,
        Key="manifests/_suppression/suppression-list.jsonl",
        Body=(entry.to_line() + "\n").encode(),
    )
    empty = world.use(tmp_path / "empty")

    refused = world.pull()

    assert refused["exit_code"] != ExitCode.OK, refused
    assert world.last_record(empty)[1]["failure_codes"] == ["RUN_STATE_WITHHELD"]
    assert suppressed in refused["error"]["message"], "the publisher's own words, which name the row"
    assert "re-run `caselist remove`" in refused["error"]["message"]
    assert not (empty / "objects" / "manifests").exists(), "nothing of the bundle was installed"
    assert not (empty / "debate.sqlite3").exists() or (empty / "debate.sqlite3").stat().st_size < 100_000


def test_an_unchanged_store_is_not_rebuilt_and_its_restored_index_holds_the_manifest_alone(
    world: World, tmp_path: Path
) -> None:
    """No gzip object is restored, and digests that match skip the build (the PM's ruling 6)."""
    the_macs_two_weeks_seeded(world)
    world.listing(WEEK_1, WEEK_2)
    before = world.published_index()
    empty = world.use(tmp_path / "empty")

    unchanged = world.pull()

    assert unchanged["exit_code"] == ExitCode.OK, unchanged
    index = stage(unchanged, "search_index")
    assert index["outcome"] == "skipped", index
    assert "which current.json names: nothing to build or publish" in index["reason"]
    [directory] = (empty / "tub-index").iterdir()
    assert sorted(path.name for path in directory.iterdir()) == ["manifest.json", RESTORED_INDEX_MARKER]
    assert world.published_index() == before


def test_a_restored_index_directory_is_never_published_by_hand(world: World, tmp_path: Path) -> None:
    """`tub index publish --newest` over a restored directory is refused: it holds no index files."""
    the_macs_two_weeks_seeded(world)
    world.listing(WEEK_1, WEEK_2)
    world.use(tmp_path / "empty")
    assert world.pull()["exit_code"] == ExitCode.OK
    pointer = world.body("reports/tub/search/current.json")

    refused = world.run("tub", "index", "publish", "--newest")

    assert refused["exit_code"] != ExitCode.OK, refused
    assert world.body("reports/tub/search/current.json") == pointer


def test_the_state_files_saved_are_the_runs_own_and_the_bundle_records_the_week(
    world: World, tmp_path: Path
) -> None:
    the_macs_two_weeks_seeded(world)
    world.use(tmp_path / "empty")

    pulled = world.pull()

    assert pulled["exit_code"] == ExitCode.OK, pulled
    run_id = pulled["data"]["run_id"]
    log = world.body(f"{STATE_PREFIX}caselist-sync-runs.jsonl").decode().splitlines()
    assert json.loads(log[-1])["run_id"] == run_id
    assert len(log) == 2, "the Mac's run, restored, and this one"
    ledger = json.loads(world.body(f"{STATE_PREFIX}caselist-sync-download-starts.json"))
    assert ledger["bulk_download_starts"] == ["2026-10-21T11:00:05+00:00"], "this run's one, in the window"
    assert world.body(f"{STATE_PREFIX}caselist-sync-pending.json") == b"", "nothing owed: saved as absent"
    bundle = tmp_path / "bundle.tar.gz"
    bundle.write_bytes(world.body(RUN_STATE_BUNDLE_KEY))
    with tarfile.open(bundle, "r:gz") as archive:
        names = sorted(archive.getnames())
    assert "objects/manifests/testcl26/2026-09-15.jsonl" in names
    assert "debate.sqlite3" in names
    assert pulled["data"]["run_details"]["bucket_run"]["bundle"].startswith("saved, ")
