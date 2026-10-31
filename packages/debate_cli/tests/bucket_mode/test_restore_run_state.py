"""`caselist restore-run-state`: the run's working copy, restored into a directory of its own (`v1-e40-t06`).

Against moto with conditional writes, through the real application, as `conftest.py`'s world runs
every bucket-mode command. Each test starts where the cutover leaves dev: two weeks pulled on "the
Mac" in local mode, published, parsed and indexed into the bucket, and the bucket seeded from that
directory. The restore must:

* take the bucket's run lock, and write nothing else to the bucket;
* write only under the directory named, and leave this environment's data directory as it was;
* refuse the data directory itself, a directory inside it or holding it, and one that is not empty,
  before it takes the lock;
* be refused, like any runner, while another holds the lease, and in local mode or on a bucket never
  seeded.

With `--with-sources` (`v1-e40-t10`) it must also fetch exactly the raw sources the restored
manifests name, or those of the `--snapshot` named, into the copy and nowhere else; stop non-zero when
a named source is missing from the bucket or arrives with another digest, keeping no mismatched byte;
refuse a disk without room before fetching; and keep every refusal above, which are each run with it
too.
"""

from __future__ import annotations

import gc
import hashlib
import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

import pytest
from tests.fixtures.parse_pipeline.build_parse_world import CASELIST, WEEKS

from debate_cli.build_info import BuildInfo
from debate_cli.exit_codes import ExitCode
from debate_core.application.caselist.run_lock import RUN_LOCK_KEY
from debate_core.application.caselist.run_state import STATE_FILES
from debate_core.application.caselist.run_state_restore import RESTORE_COMMAND, RESTORED_COPY_MARKER
from debate_core.application.caselist.suppression import SUPPRESSION_LIST_KEY
from debate_core.application.ports.suppression import ReasonCode, SuppressionAction, SuppressionEntry
from debate_core.application.search_index_refresh import RESTORED_INDEX_MARKER
from debate_core.integrations.local.suppression_list import SUPPRESSION_DIRECTORY, SUPPRESSION_LIST_FILENAME

World = Any
"""`conftest.py`'s world, which a test module cannot import by name."""

WEEK_1, WEEK_2 = (week.snapshot for week in WEEKS[:2])
OTHER_RUN: Final = "20261028T110002Z"


def seeded(world: World) -> Path:
    """Two weeks pulled, published, parsed and indexed in local mode, then the bucket seeded."""
    world.listing(WEEK_1, WEEK_2)
    pulled = world.pull()
    assert pulled["exit_code"] == ExitCode.OK, pulled
    world.seed()
    return world.data_dir


def restore(world: World, into: Path, *more: str) -> dict[str, Any]:
    return world.run("caselist", "restore-run-state", "--into", str(into), "--caselist", CASELIST, *more)


def files(directory: Path) -> dict[str, str]:
    """Every file under `directory` with its SHA-256: what "left as it was" is checked by.

    Collected first: an earlier command of the test, run in this process, can leave a SQLite
    connection for the garbage collector, and closing it checkpoints the database's write-ahead log
    into the file, whenever that happens. A probe of `sqlite3.connect` showed the restore opening no
    database at all.
    """
    gc.collect()
    return {
        path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def rows(database: Path) -> dict[str, int]:
    """Each table's row count: two copies of the database hold the same records."""
    connection = sqlite3.connect(database)
    try:
        tables = [
            name
            for (name,) in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        return {
            table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in tables
        }
    finally:
        connection.close()


def lock_bodies(world: World) -> list[dict[str, Any]]:
    """Every version of the lock object."""
    versions = world.versions(RUN_LOCK_KEY)
    return [
        json.loads(
            world.client.get_object(Bucket=world.bucket, Key=RUN_LOCK_KEY, VersionId=version["VersionId"])[
                "Body"
            ].read()
        )
        for version in versions
    ]


def without_the_lock(objects: dict[str, str]) -> dict[str, str]:
    return {key: etag for key, etag in objects.items() if key != RUN_LOCK_KEY}


def at(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def the_cloud_run_holds_the_lock(world: World) -> None:
    """The cloud run's lease, as the task writes it: held, with twenty minutes left."""
    now = world.clock.now
    body = {
        "format_version": 1,
        "home_environment": "dev",
        "state": "held",
        "holder": {
            "kind": "cloud",
            "run_id": OTHER_RUN,
            "task": "0123456789abcdef",
            "command": "caselist pull",
        },
        "acquired_at": at(now - timedelta(minutes=10)),
        "renewed_at": at(now),
        "lease_expires_at": at(now + timedelta(minutes=20)),
        "took_over_from": None,
    }
    world.client.put_object(Bucket=world.bucket, Key=RUN_LOCK_KEY, Body=json.dumps(body).encode())


# ------------------------------------------------------------------------------------------------
# The copy, and nothing else
# ------------------------------------------------------------------------------------------------


def test_the_copy_holds_the_runs_state_and_the_data_directory_and_the_bucket_are_left_as_they_were(
    world: World, tmp_path: Path
) -> None:
    live = seeded(world)
    # Counted before the snapshot: opening the live database read-write and closing it removes the
    # empty `-wal` and `-shm` files that the seed's read-only `VACUUM INTO` connection leaves when it
    # closes last, and that change is the test's own, not the restore's.
    live_rows = rows(live / "debate.sqlite3")
    live_before = files(live)
    bucket_before = without_the_lock(world.everything())
    copy = tmp_path / "copy"

    restored = restore(world, copy)

    assert restored["exit_code"] == ExitCode.OK, restored
    data = restored["data"]
    assert data["manifests"] == len(list((live / "objects" / "manifests").rglob("*.jsonl"))) > 0
    assert data["state_files"] == list(STATE_FILES), "the seed saved all five, an absent one as empty"
    assert data["parsed_objects"] > 0
    assert data["index_id"] == world.published_index()["index_id"]
    assert data["caselists"] == [CASELIST]
    assert data["sources"] is None
    assert not (copy / "blobs").exists(), "without --with-sources, no raw source is fetched"

    assert files(copy / "objects" / "manifests") == files(live / "objects" / "manifests")
    assert rows(copy / "debate.sqlite3") == live_rows
    assert world.parsed_digests(copy) == world.parsed_digests(live)
    for name in STATE_FILES:
        assert (copy / name).exists() == (live / name).exists(), name
        if (live / name).exists():
            assert (copy / name).read_bytes() == (live / name).read_bytes(), name
    index = copy / "tub-index" / data["index_id"]
    assert (index / RESTORED_INDEX_MARKER).is_file(), "a restored manifest is never published from"
    assert (index / "manifest.json").is_file()

    assert files(live) == live_before, "the data directory is left exactly as it was"
    assert without_the_lock(world.everything()) == bucket_before, "the lock is the only object written"


def test_the_copy_carries_the_marker_naming_the_environment_bucket_time_and_build_and_nothing_else(
    world: World, tmp_path: Path
) -> None:
    """`v1-e40-t21`: the runbooks find a leftover copy by this file, at any depth."""
    live = seeded(world)
    world.monkeypatch.setattr(
        "debate_cli.container.current_build_info",
        lambda: BuildInfo(
            version="1.8.0", channel="dev", commit=None, tag="v1.8.0-dev.201", built_at=None, run_id=None
        ),
    )
    copy = tmp_path / "deeper" / "than" / "three" / "levels" / f"landscape-copy-{CASELIST}"

    restored = restore(world, copy)

    assert restored["exit_code"] == ExitCode.OK, restored
    text = (copy / RESTORED_COPY_MARKER).read_text(encoding="utf-8")
    assert json.loads(text) == {
        "environment": "dev",
        "bucket": world.bucket,
        "restored_at": at(world.clock.now),
        "build_tag": "v1.8.0-dev.201",
    }
    assert CASELIST not in text and str(tmp_path) not in text
    assert list(live.rglob(RESTORED_COPY_MARKER)) == [], "the data directory never carries one"


def test_the_restore_holds_the_lock_while_it_reads_and_leaves_it_free(world: World, tmp_path: Path) -> None:
    seeded(world)

    assert restore(world, tmp_path / "copy")["exit_code"] == ExitCode.OK

    holders = [body["holder"]["command"] for body in lock_bodies(world) if body.get("holder")]
    assert RESTORE_COMMAND in holders, holders
    assert world.lock()["state"] == "free"


def test_the_copys_suppression_list_is_the_buckets(world: World, tmp_path: Path) -> None:
    """A parse or an index build in the copy leaves out what the bucket's list stops."""
    seeded(world)
    entry = SuppressionEntry(
        action=SuppressionAction.SUPPRESS,
        sha256="a" * 64,
        recorded_at=datetime(2026, 10, 20, tzinfo=UTC),
        reason=ReasonCode.REQUESTED_BY_TEAM,
        request_id="RM-2026-07",
    )
    world.client.put_object(
        Bucket=world.bucket, Key=SUPPRESSION_LIST_KEY, Body=(entry.to_line() + "\n").encode()
    )
    copy = tmp_path / "copy"

    restored = restore(world, copy)

    assert restored["exit_code"] == ExitCode.OK, restored
    assert restored["data"]["suppression_entries"] == 1
    copied = copy / SUPPRESSION_DIRECTORY / SUPPRESSION_LIST_FILENAME
    assert "a" * 64 in copied.read_text(encoding="utf-8")


def test_the_caselists_default_to_the_setting(world: World, tmp_path: Path) -> None:
    seeded(world)
    world.monkeypatch.setenv("DEBATE_CASELIST__SYNC_CASELISTS", json.dumps([CASELIST]))

    restored = world.run("caselist", "restore-run-state", "--into", str(tmp_path / "copy"))

    assert restored["exit_code"] == ExitCode.OK, restored
    assert restored["data"]["caselists"] == [CASELIST]


def test_with_no_caselist_named_or_configured_nothing_is_taken(world: World, tmp_path: Path) -> None:
    seeded(world)
    before = world.everything()

    refused = world.run("caselist", "restore-run-state", "--into", str(tmp_path / "copy"))

    assert refused["error"]["code"] == "NO_CASELISTS_CONFIGURED", refused
    assert world.everything() == before


# ------------------------------------------------------------------------------------------------
# Directories it refuses, before it takes the lock
# ------------------------------------------------------------------------------------------------


def the_data_directory(live: Path, tmp_path: Path) -> Path:
    return live


def inside_it(live: Path, tmp_path: Path) -> Path:
    return live / "copy"


def holding_it(live: Path, tmp_path: Path) -> Path:
    return live.parent


def a_link_to_it(live: Path, tmp_path: Path) -> Path:
    link = tmp_path / "link-to-the-data-directory"
    link.symlink_to(live, target_is_directory=True)
    return link


def not_empty(live: Path, tmp_path: Path) -> Path:
    directory = tmp_path / "another-store"
    directory.mkdir()
    (directory / "debate.sqlite3").write_bytes(b"another store's database")
    return directory


def a_file(live: Path, tmp_path: Path) -> Path:
    path = tmp_path / "a-file"
    path.write_bytes(b"")
    return path


REFUSED: Final[dict[str, tuple[Callable[[Path, Path], Path], str]]] = {
    "the data directory": (the_data_directory, "is this environment's own data directory"),
    "a directory inside it": (inside_it, "is inside this environment's own data directory"),
    "a directory holding it": (holding_it, "holds this environment's own data directory"),
    "a symbolic link to it": (a_link_to_it, "is this environment's own data directory"),
    "a directory that is not empty": (not_empty, "is not empty"),
    "a file": (a_file, "is not a directory"),
}
"""Each directory refused, and the reason given: the data directory is also not empty, so the reason
is what tells the refusals apart."""


WITH_AND_WITHOUT_SOURCES: Final = pytest.mark.parametrize(
    "extra", [(), ("--with-sources",)], ids=["without sources", "with sources"]
)
"""`--with-sources` adds no refusal that skips one of these, so each is run with it too."""


@WITH_AND_WITHOUT_SOURCES
@pytest.mark.parametrize("which", sorted(REFUSED))
def test_a_directory_it_must_not_write_into_is_refused_before_the_lock_is_taken(
    world: World, tmp_path: Path, which: str, extra: tuple[str, ...]
) -> None:
    live = seeded(world)
    make, reason = REFUSED[which]
    target = make(live, tmp_path)
    live_before = files(live)
    bucket_before = world.everything()
    versions_before = len(world.versions(RUN_LOCK_KEY))

    refused = restore(world, target, *extra)

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused
    assert refused["error"]["code"] == "RESTORE_TARGET_REFUSED", refused["error"]
    assert reason in refused["error"]["message"], refused["error"]["message"]
    assert "the run lock was not taken" in refused["error"]["message"]
    assert len(world.versions(RUN_LOCK_KEY)) == versions_before, "the lock was not taken"
    assert world.everything() == bucket_before
    assert files(live) == live_before


@pytest.mark.parametrize("which", ["the data directory", "the directory that will hold it"])
def test_a_fresh_machines_data_directory_not_yet_made_is_refused_too(
    world: World, tmp_path: Path, which: str
) -> None:
    """On a Mac with no data directory yet, neither it nor its empty parent is a copy's place."""
    seeded(world)
    fresh = world.use(tmp_path / "fresh-home" / "dev")
    (tmp_path / "fresh-home").mkdir()
    target = fresh if which == "the data directory" else fresh.parent

    refused = restore(world, target)

    assert refused["error"]["code"] == "RESTORE_TARGET_REFUSED", refused
    assert ("is this environment's" if which == "the data directory" else "holds this environment's") in (
        refused["error"]["message"]
    )
    assert not fresh.exists()


# ------------------------------------------------------------------------------------------------
# Refused like any runner
# ------------------------------------------------------------------------------------------------


@WITH_AND_WITHOUT_SOURCES
def test_it_is_refused_while_the_cloud_run_holds_the_lock_and_restores_nothing(
    world: World, tmp_path: Path, extra: tuple[str, ...]
) -> None:
    """The cutover's second-runner check: a Mac command meets the cloud run's lease and does nothing."""
    seeded(world)
    the_cloud_run_holds_the_lock(world)
    before = world.everything()
    copy = tmp_path / "copy"

    refused = restore(world, copy, *extra)

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused
    assert refused["error"]["code"] == "RUN_LOCK_HELD", refused["error"]
    assert OTHER_RUN in refused["error"]["message"]
    assert world.everything() == before
    assert not copy.exists() or not any(copy.iterdir()), "nothing restored, so no copy for a cleanup to find"


@WITH_AND_WITHOUT_SOURCES
def test_in_local_mode_it_restores_nothing_and_takes_nothing(
    world: World, tmp_path: Path, extra: tuple[str, ...]
) -> None:
    seeded(world)
    world.mode("local")
    before = world.everything()
    copy = tmp_path / "copy"

    refused = restore(world, copy, *extra)

    assert refused["error"]["code"] == "RUN_STATE_IS_LOCAL", refused
    assert world.everything() == before
    assert not copy.exists()


@WITH_AND_WITHOUT_SOURCES
def test_a_bucket_never_seeded_is_refused_with_nothing_restored(
    world: World, tmp_path: Path, extra: tuple[str, ...]
) -> None:
    world.mode("bucket")
    copy = tmp_path / "copy"

    refused = restore(world, copy, *extra)

    assert refused["error"]["code"] == "RUN_STATE_NOT_SEEDED", refused
    assert RUN_LOCK_KEY not in world.object_keys()
    assert not copy.exists()


@WITH_AND_WITHOUT_SOURCES
def test_in_prod_it_needs_confirm_prod(world: World, tmp_path: Path, extra: tuple[str, ...]) -> None:
    """Holding prod's lock turns a scheduled run away, so prod asks, as the seed's --execute does."""
    (world.root / "profiles" / "prod.toml").write_text(
        f'[storage]\ndata_dir = "{world.root / "prod-data"}"\n'
        '[storage.s3]\nbucket = "debate-prod-evidence-moto"\nregion = "us-east-1"\n'
        'aws_profile = "debate-dev-evidence"\n',
        encoding="utf-8",
    )
    world.monkeypatch.setenv("DEBATE_ENV", "prod")
    for name in ("DEBATE_STORAGE__DATA_DIR", "DEBATE_CASELIST__API_BASE_URL"):
        world.monkeypatch.delenv(name)
    world.mode("bucket")

    refused = restore(world, tmp_path / "copy", *extra)

    assert refused["error"]["code"] == "CONFIRMATION_REQUIRED", refused["error"]
    assert "--confirm-prod" in refused["error"]["message"]


# ------------------------------------------------------------------------------------------------
# With sources (`v1-e40-t10`)
# ------------------------------------------------------------------------------------------------

STORED: Final = frozenset({"NEW", "UNCHANGED", "CHANGED", "DUPLICATE"})
"""The importer's stored classifications: a row with one names a source its snapshot holds."""

FICTIONAL_NAMES: Final = ("Maple Grove", "Riverbend", "Cedar Hollow", "Northgate", ".docx")


def named_by(directory: Path, *, caselist: str = "", snapshot: str | None = None) -> dict[str, int]:
    """Each digest the directory's manifests name in a stored row, with its size. Read here, by hand."""
    named: dict[str, int] = {}
    for manifest in sorted((directory / "objects" / "manifests" / caselist).rglob("*.jsonl")):
        if snapshot is not None and manifest.stem != snapshot:
            continue
        for line in manifest.read_text(encoding="utf-8").splitlines():
            row = json.loads(line) if line.strip() else {}
            if row.get("kind") == "member" and row.get("classification") in STORED:
                named[row["sha256"]] = row["byte_size"]
    return named


def blobs_in(directory: Path) -> dict[str, str]:
    """Each blob in a data directory's blob tree, by its digest, with the SHA-256 of its bytes."""
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((directory / "blobs").rglob("*"))
        if path.is_file()
    }


def inodes(directory: Path) -> dict[str, int]:
    """Each file's inode: a source renamed over identical bytes leaves the bytes and changes this."""
    return {path.relative_to(directory).as_posix(): path.stat().st_ino for path in directory.rglob("*")}


def restore_with_sources(world: World, into: Path, *more: str) -> tuple[dict[str, Any], str]:
    """The envelope, and everything the command said, stdout and stderr together."""
    result = world.invoke(
        "--json", "caselist", "restore-run-state", "--into", str(into), "--with-sources", *more
    )
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert lines, f"no JSON on stdout: {result.output!r} {result.exception!r}"
    envelope = json.loads(lines[-1])
    envelope["exit_code"] = result.exit_code
    return envelope, result.stdout + result.stderr


def raw_key_of(world: World, digest: str) -> str:
    (key,) = [key for key in world.object_keys("raw/") if key.endswith(f"/{digest}")]
    return key


def test_with_sources_the_copy_holds_every_source_its_manifests_name_and_nothing_else_is_written(
    world: World, tmp_path: Path
) -> None:
    live = seeded(world)
    live_rows = rows(live / "debate.sqlite3")
    live_before = files(live)
    live_inodes = inodes(live)
    bucket_before = without_the_lock(world.everything())
    world.monkeypatch.setenv("DEBATE_CASELIST__SYNC_CASELISTS", json.dumps([CASELIST]))
    copy = tmp_path / "copy"

    restored, said = restore_with_sources(world, copy)

    assert restored["exit_code"] == ExitCode.OK, restored
    named = named_by(copy)
    assert len(list((copy / "objects" / "manifests").glob("*/*.jsonl"))) == 3, "the premise: openev's too"
    assert set(named) <= set(blobs_in(live)), "the premise: the live store holds every one"
    assert restored["data"]["sources"] == {
        "manifests": len(list((copy / "objects" / "manifests").rglob("*.jsonl"))),
        "named": len(named),
        "fetched": len(named),
        "fetched_bytes": sum(named.values()),
        "suppressed": 0,
    }
    assert blobs_in(copy) == {digest: digest for digest in named}, "each named source, its bytes its digest"
    assert f"Fetching {len(named)} raw source(s), {sum(named.values())} bytes" in said
    assert rows(copy / "debate.sqlite3") == live_rows

    assert files(live) == live_before, "the data directory is left exactly as it was"
    assert inodes(live) == live_inodes, "nothing was renamed into the data directory, even over equal bytes"
    assert without_the_lock(world.everything()) == bucket_before, "the lock is the only object written"
    assert world.lock()["state"] == "free"
    for word in (*FICTIONAL_NAMES, str(tmp_path), *named):
        assert word not in said, word


def test_with_a_snapshot_only_that_snapshots_sources_are_fetched(world: World, tmp_path: Path) -> None:
    seeded(world)
    copy = tmp_path / "copy"

    restored, _ = restore_with_sources(world, copy, "--caselist", CASELIST, "--snapshot", WEEK_1.isoformat())

    assert restored["exit_code"] == ExitCode.OK, restored
    first_week = named_by(copy, caselist=CASELIST, snapshot=WEEK_1.isoformat())
    assert set(first_week) < set(named_by(copy, caselist=CASELIST)), "the premise: a later week names more"
    assert set(blobs_in(copy)) == set(first_week)
    assert restored["data"]["sources"]["manifests"] == 1


def test_a_named_source_missing_from_the_bucket_and_not_suppressed_stops_the_command(
    world: World, tmp_path: Path
) -> None:
    """The planted store: a source the second week's manifest names, deleted from the bucket."""
    live = seeded(world)
    later = sorted(set(named_by(live)) - set(named_by(live, snapshot=WEEK_1.isoformat())))
    world.client.delete_object(Bucket=world.bucket, Key=raw_key_of(world, later[0]))
    live_before = files(live)
    copy = tmp_path / "copy"

    stopped, said = restore_with_sources(world, copy, "--caselist", CASELIST)

    assert stopped["exit_code"] == ExitCode.DOMAIN_FAILURE, stopped
    error = stopped["error"]
    assert error["code"] == "RESTORED_SOURCES_INCOMPLETE", error
    assert (error["details"]["missing"], error["details"]["mismatched"]) == (1, 0)
    assert "not a copy to publish from" in error["message"]
    assert "holds what was restored before the stop" in said
    assert later[0] not in blobs_in(copy)
    assert (copy / RESTORED_COPY_MARKER).is_file(), "what the stop left is found by the cleanup"
    assert files(live) == live_before
    assert world.lock()["state"] == "free"


def test_bytes_that_are_not_the_digest_named_stop_the_command_and_none_of_them_is_kept(
    world: World, tmp_path: Path
) -> None:
    live = seeded(world)
    victim = sorted(named_by(live))[0]
    other = b"bytes that are not the source the manifest names\n"
    world.client.put_object(
        Bucket=world.bucket,
        Key=raw_key_of(world, victim),
        Body=other,
        Metadata={"sha256": hashlib.sha256(other).hexdigest()},
    )
    copy = tmp_path / "copy"

    stopped, _ = restore_with_sources(world, copy, "--caselist", CASELIST)

    assert stopped["exit_code"] == ExitCode.DOMAIN_FAILURE, stopped
    assert stopped["error"]["code"] == "RESTORED_SOURCES_INCOMPLETE", stopped
    assert stopped["error"]["details"]["mismatched"] == 1
    assert victim not in blobs_in(copy)
    assert hashlib.sha256(other).hexdigest() not in files(copy).values(), "no file in the copy keeps them"
    assert (copy / RESTORED_COPY_MARKER).is_file(), "what the stop left is found by the cleanup"
    assert world.lock()["state"] == "free"


def test_a_disk_without_room_for_the_sources_is_refused_before_any_fetch(
    world: World, tmp_path: Path
) -> None:
    seeded(world)
    world.monkeypatch.setattr("debate_core.application.caselist.run_state_sources._free_bytes", lambda _: 0)
    copy = tmp_path / "copy"

    refused, said = restore_with_sources(world, copy, "--caselist", CASELIST)

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused
    assert refused["error"]["code"] == "TOO_LITTLE_ROOM_FOR_SOURCES", refused
    assert "Fetching " in said, "the count and bytes are said before the refusal"
    assert blobs_in(copy) == {}
    assert (copy / RESTORED_COPY_MARKER).is_file(), "what the refusal left is found by the cleanup"
    assert world.lock()["state"] == "free"


@pytest.mark.parametrize(
    "arguments",
    [("--snapshot", "2026-09-01"), ("--with-sources", "--snapshot", "last-week")],
    ids=["a snapshot without --with-sources", "a snapshot that is no snapshot's name"],
)
def test_a_snapshot_the_command_cannot_use_is_a_usage_error_before_the_lock(
    world: World, tmp_path: Path, arguments: tuple[str, ...]
) -> None:
    seeded(world)
    versions_before = len(world.versions(RUN_LOCK_KEY))
    copy = tmp_path / "copy"

    result = world.invoke(
        "caselist", "restore-run-state", "--into", str(copy), "--caselist", CASELIST, *arguments
    )

    assert result.exit_code == 2, result.output
    assert "--snapshot" in result.output
    assert len(world.versions(RUN_LOCK_KEY)) == versions_before, "the lock was not taken"
    assert not copy.exists()


def test_a_snapshot_the_copy_has_no_manifest_of_fetches_nothing(world: World, tmp_path: Path) -> None:
    seeded(world)
    copy = tmp_path / "copy"

    refused, _ = restore_with_sources(world, copy, "--caselist", CASELIST, "--snapshot", "2026-08-25")

    assert refused["exit_code"] == ExitCode.DOMAIN_FAILURE, refused
    assert refused["error"]["code"] == "SNAPSHOTS_NOT_RESTORED", refused
    assert blobs_in(copy) == {}
