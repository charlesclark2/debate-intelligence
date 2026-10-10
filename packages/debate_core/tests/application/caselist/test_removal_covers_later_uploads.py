"""A removal also takes down the later uploads at the removed file's path (`v1-e30-t11`).

Everything here is checked on the store after `caselist remove --source <named-version> --execute`,
through the removal service the command runs, against moto and a local data directory. It asks the
planner for nothing this task added, so every test also runs against the planner as it was before
the task, where the ones about a later upload fail on what that planner left behind.

The world is `tests/fixtures/caselist/build_revised_path_archives.py`: six weekly windows and two
complete archives of `testcl26` in which one path is revised again and again, and one weekly of
another caselist with a file at the same spelling of that path. Its docstring works the answer out
by hand, and :data:`EXPECTED` there is what these tests assert. On top of it, as a store that has
been used is:

* a second version in the bucket of `later-revision`'s raw object and of the manifest that names it;
* parsed files for `later-revision` and `later-also-at-another-path`, and the three aggregates of
  `testcl26`, here and in the bucket (two versions each there). They are written by hand at the
  parsed store's own keys, so no parser runs;
* in the download inbox, the imported weekly of `2026-09-15` (it holds `later-revision`), the imported
  weekly of `2026-09-01` (it holds only the earlier version), and a weekly of `2026-10-13` still
  waiting to be imported, with the `2026-10-06` members.
"""

from __future__ import annotations

import json
import shutil
import zipfile
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest
from tests.fixtures.caselist.build_revised_path_archives import (
    BODIES,
    CASELIST,
    EXPECTED,
    KEPT_PATH,
    OTHER_CASELIST,
    OTHER_TEAM_PATH,
    REVISED_PATH,
    WEEKLY_WINDOWS,
    build_complete_archive_zips,
    build_weekly_zips,
    digest_of,
    write_archive,
)

from debate_core.application.caselist.evidence_listing import LocalEvidence, snapshots_before_full_archive
from debate_core.application.caselist.import_service import CaselistImportService, Classification
from debate_core.application.caselist.manifest import (
    full_archive_manifest_key,
    manifest_key,
    write_manifest,
)
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.removal_plan import Disposition, SourceSelector, parse_team_selector
from debate_core.application.caselist.status_service import CaselistStatusService
from debate_core.application.caselist.suppression import SUPPRESSION_LIST_KEY, RecordedSuppressionList
from debate_core.application.ports.parsed_store import AGGREGATE_NAMES, source_object_key
from debate_core.application.ports.suppression import (
    ReasonCode,
    RemovalLogEntry,
    SuppressionEntry,
    disclosure_digest,
)
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsEvidenceObjectStore, FsSnapshotStore, SqliteDatabase
from debate_core.integrations.local.archive_reader import archive_digest, read_archive
from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository
from debate_core.integrations.local.suppression_list import (
    local_removal_log_file,
    local_suppression_list_file,
)
from debate_core.testing.fakes import empty_suppression_list

from .conftest import REQUEST, RemovalWorld

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

LIMITS: Final = {"max_archive_bytes": 64 * 1024 * 1024, "max_unpacked_bytes": 64 * 1024 * 1024}
PARSED_VERSION: Final = "2026.09.20-docx-1"

NAMED: Final = digest_of("named-version")
LATER_REVISION: Final = digest_of("later-revision")
LATER_IN_COMPLETE_ARCHIVE: Final = digest_of("later-in-complete-archive-only")
LATER_SHARED: Final = digest_of("later-also-at-another-path")
EARLIER: Final = digest_of("earlier-version")
OTHER_CASELIST_FILE: Final = digest_of("other-caselist-same-path")

IMPORTED_WEEKLY_HOLDING_THE_REVISION: Final = f"{CASELIST}-weekly-2026-09-15.zip"
IMPORTED_WEEKLY_HOLDING_THE_EARLIER_VERSION: Final = f"{CASELIST}-weekly-2026-09-01.zip"
WAITING_WEEKLY: Final = f"{CASELIST}-weekly-2026-10-13.zip"

#: Every word that names a school, a team code or the tournament in the fixture's paths.
NAMES: Final = ("Alder Point", "KR", "Birch Hill", "MT", "Lakeshore")


# ------------------------------------------------------------------------------------------------
# The world
# ------------------------------------------------------------------------------------------------


def raw_key(digest: str, caselist: str = CASELIST) -> str:
    return f"raw/caselist/{caselist}/sha256/{digest[:2]}/{digest[2:4]}/{digest}"


def snapshot_key(snapshot: str, caselist: str = CASELIST) -> str:
    """`2026-09-15` or `full/2026-10-03`, as :data:`EXPECTED` names a snapshot, to its manifest key."""
    if snapshot.startswith("full/"):
        return full_archive_manifest_key(caselist, date.fromisoformat(snapshot.removeprefix("full/")))
    return manifest_key(caselist, date.fromisoformat(snapshot))


ALL_SNAPSHOTS: Final = (
    "2026-09-01",
    "full/2026-09-05",
    "2026-09-08",
    "2026-09-15",
    "2026-09-22",
    "2026-09-29",
    "full/2026-10-03",
    "2026-10-06",
)


async def import_revised_path_archives(data_dir: Path, downloads: Path) -> None:
    """Import every weekly in date order, then each complete archive, writing each manifest."""
    weekly = build_weekly_zips(downloads)
    complete = build_complete_archive_zips(downloads)
    importer = CaselistImportService(
        caselists=SqliteCaselistRepository(SqliteDatabase.open(data_dir)),
        blobs=FsSnapshotStore(data_dir),
        suppression=empty_suppression_list(),
    )
    objects = FsEvidenceObjectStore(data_dir)
    for (caselist, week), path in sorted(weekly.items()):
        report = await importer.import_archive(
            read_archive(path, **LIMITS),
            caselist=caselist,
            snapshot=week,
            event=Event.LD,
            archive_sha256=archive_digest(path),
        )
        write_manifest(report, objects.path_for(manifest_key(caselist, week)))
    blobs = FsEvidenceObjectStore(data_dir, subdirectory=Path("blobs"))
    local = LocalEvidence(
        objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
    )
    for (caselist, day), path in sorted(complete.items()):
        previous, earlier = await snapshots_before_full_archive(local, caselist, day)
        report = await importer.import_full_archive(
            read_archive(path, **LIMITS),
            caselist=caselist,
            archive_date=day,
            event=Event.LD,
            archive_sha256=archive_digest(path),
            previous=previous,
            earlier=earlier,
        )
        write_manifest(report, objects.path_for(full_archive_manifest_key(caselist, day)))


def plant_parsed_files(world: RemovalWorld) -> None:
    """A parsed file for two of the later uploads and the caselist's aggregates, here and in the bucket.

    Written at the parsed store's own keys (`v1-e31-t06`), twice in the bucket so each has a
    noncurrent version. Their contents are placeholders: a removal deletes these by key.
    """
    names = [
        *(source_object_key(CASELIST, PARSED_VERSION, one) for one in (LATER_REVISION, LATER_SHARED)),
        *(f"{CASELIST}/{PARSED_VERSION}/{name}" for name in AGGREGATE_NAMES),
    ]
    for name in names:
        local = world.data_dir / "parsed" / name
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_text('{"placeholder": true}\n', encoding="utf-8")
        for body in (b'{"placeholder": 1}\n', b'{"placeholder": 2}\n'):
            world.client.put_object(Bucket=world.bucket_name, Key=f"parsed/{name}", Body=body)


def fill_the_inbox(world: RemovalWorld, downloads: Path) -> None:
    inbox = world.data_dir / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    for name in (IMPORTED_WEEKLY_HOLDING_THE_REVISION, IMPORTED_WEEKLY_HOLDING_THE_EARLIER_VERSION):
        shutil.copyfile(downloads / name, inbox / name)
    write_archive(inbox / WAITING_WEEKLY, WEEKLY_WINDOWS[(CASELIST, date(2026, 10, 6))])


def add_bucket_history(world: RemovalWorld) -> None:
    """A second version of the later revision's raw object and of the manifest that names it.

    Each is the same bytes and metadata put again, so the current version still reads as published
    and `caselist status` has nothing to say about it.
    """
    for key in (raw_key(LATER_REVISION), snapshot_key("2026-09-15")):
        current = world.client.get_object(Bucket=world.bucket_name, Key=key)
        world.client.put_object(
            Bucket=world.bucket_name, Key=key, Body=current["Body"].read(), Metadata=current["Metadata"]
        )


async def revised_path_world(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> RemovalWorld:
    """The fixture's archives imported and published, with history, parsed files and an inbox."""
    data_dir = tmp_path / "evidence"
    await import_revised_path_archives(data_dir, tmp_path / "downloads")
    built = RemovalWorld(data_dir=data_dir, bucket_name=evidence_bucket, client=s3_client)
    for caselist in (CASELIST, OTHER_CASELIST):
        publisher = CaselistPublishService(
            local=built.local, remote=built.bucket, suppression=empty_suppression_list()
        )
        assert (await publisher.execute(await publisher.plan(caselist))).succeeded
    add_bucket_history(built)
    plant_parsed_files(built)
    fill_the_inbox(built, tmp_path / "downloads")
    return built


@pytest.fixture
async def world(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> RemovalWorld:
    return await revised_path_world(tmp_path, s3_client, evidence_bucket)


# ------------------------------------------------------------------------------------------------
# Reading the store
# ------------------------------------------------------------------------------------------------


def versions_of(world: RemovalWorld, key: str) -> list[str]:
    """Every version id and delete marker of exactly `key`."""
    listed = world.client.list_object_versions(Bucket=world.bucket_name, Prefix=key)
    return [
        str(one.get("VersionId"))
        for one in [*listed.get("Versions", []), *listed.get("DeleteMarkers", [])]
        if one.get("Key") == key
    ]


def local_blob(world: RemovalWorld, digest: str) -> Path:
    return FsSnapshotStore(world.data_dir).path_for(digest)


def local_manifest_text(world: RemovalWorld, key: str) -> str:
    return FsEvidenceObjectStore(world.data_dir).path_for(key).read_text(encoding="utf-8")


def bucket_manifest_text(world: RemovalWorld, key: str) -> str:
    return world.client.get_object(Bucket=world.bucket_name, Key=key)["Body"].read().decode("utf-8")


def member_rows(text: str) -> list[dict[str, object]]:
    return [row for row in map(json.loads, text.splitlines()) if row["kind"] == "member"]


def rows_on_both_sides(
    world: RemovalWorld, snapshot: str, caselist: str = CASELIST
) -> list[list[dict[str, object]]]:
    key = snapshot_key(snapshot, caselist)
    return [member_rows(local_manifest_text(world, key)), member_rows(bucket_manifest_text(world, key))]


def held_at(rows: list[dict[str, object]], path: str) -> set[object]:
    """The digests a manifest's stored rows hold at `path` (a `REMOVED` row holds nothing)."""
    return {
        row["sha256"]
        for row in rows
        if row["path"] == path and row["classification"] != str(Classification.REMOVED)
    }


def every_bucket_manifest_version(world: RemovalWorld) -> list[str]:
    """The text of every version, current or not, of every caselist manifest in the bucket."""
    listed = world.client.list_object_versions(Bucket=world.bucket_name, Prefix="manifests/")
    texts: list[str] = []
    for one in listed.get("Versions", []):
        key = str(one.get("Key"))
        if key.startswith("manifests/_suppression/"):
            continue
        body = world.client.get_object(
            Bucket=world.bucket_name, Key=key, VersionId=str(one.get("VersionId"))
        )["Body"]
        texts.append(body.read().decode("utf-8"))
    return texts


def suppression_lines(world: RemovalWorld) -> tuple[list[SuppressionEntry], list[SuppressionEntry]]:
    """The list's entries on this machine and in the bucket."""
    local = local_suppression_list_file(world.data_dir).path.read_text(encoding="utf-8")
    bucket = bucket_manifest_text(world, SUPPRESSION_LIST_KEY)
    return (
        [SuppressionEntry.from_line(line) for line in local.splitlines()],
        [SuppressionEntry.from_line(line) for line in bucket.splitlines()],
    )


def zip_members(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()}


async def remove_the_named_file(world: RemovalWorld) -> None:
    """`caselist remove --source <named-version> --execute`, through the service the command runs."""
    service = world.service()
    plan = await service.plan(SourceSelector(NAMED), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM)
    assert (await service.execute(plan)).completed


# ------------------------------------------------------------------------------------------------
# The fixture is what its docstring says: the preconditions every test below relies on
# ------------------------------------------------------------------------------------------------


async def test_before_the_removal_the_store_holds_each_version_where_the_table_says(
    world: RemovalWorld,
) -> None:
    held = {
        snapshot: [held_at(rows, REVISED_PATH) for rows in rows_on_both_sides(world, snapshot)]
        for snapshot in ALL_SNAPSHOTS
    }

    assert held == {
        "2026-09-01": [{EARLIER}] * 2,
        "full/2026-09-05": [{EARLIER}] * 2,
        "2026-09-08": [{NAMED}] * 2,
        "2026-09-15": [{LATER_REVISION}] * 2,
        "2026-09-22": [set()] * 2,
        "2026-09-29": [{NAMED}] * 2,
        "full/2026-10-03": [{LATER_IN_COMPLETE_ARCHIVE}] * 2,
        "2026-10-06": [{LATER_SHARED}] * 2,
    }
    for rows in rows_on_both_sides(world, "2026-09-15", OTHER_CASELIST):
        assert held_at(rows, REVISED_PATH) == {OTHER_CASELIST_FILE}
    for rows in rows_on_both_sides(world, "2026-09-22"):
        assert [row["classification"] for row in rows if row["path"] == REVISED_PATH] == ["REMOVED"]
    assert len(versions_of(world, raw_key(LATER_REVISION))) == 2
    assert len(versions_of(world, snapshot_key("2026-09-15"))) == 2


# ------------------------------------------------------------------------------------------------
# ac1: the later upload goes through everything the named file goes through
# ------------------------------------------------------------------------------------------------


async def test_the_later_revision_is_deleted_here_and_in_the_bucket_every_version(
    world: RemovalWorld,
) -> None:
    assert local_blob(world, LATER_REVISION).exists()

    await remove_the_named_file(world)

    for digest in (NAMED, LATER_REVISION):
        assert not local_blob(world, digest).exists(), digest
        assert versions_of(world, raw_key(digest)) == [], "every version, and no delete marker left"
        assert await world.repository.find_source(digest) is None
        assert not (await world.repository.list_disclosures(source_sha256=digest, limit=10)).items


async def test_a_revision_only_a_complete_archive_holds_is_removed_too(world: RemovalWorld) -> None:
    await remove_the_named_file(world)

    assert not local_blob(world, LATER_IN_COMPLETE_ARCHIVE).exists()
    assert versions_of(world, raw_key(LATER_IN_COMPLETE_ARCHIVE)) == []
    assert await world.repository.find_source(LATER_IN_COMPLETE_ARCHIVE) is None
    for rows in rows_on_both_sides(world, "full/2026-10-03"):
        assert held_at(rows, REVISED_PATH) == set()
        assert held_at(rows, KEPT_PATH) == {digest_of("kept")}


async def test_each_manifest_loses_the_rows_the_table_says_on_both_sides(world: RemovalWorld) -> None:
    before = {
        snapshot: [len(rows) for rows in rows_on_both_sides(world, snapshot)] for snapshot in ALL_SNAPSHOTS
    }

    await remove_the_named_file(world)

    dropped = {
        snapshot: [
            was - len(rows)
            for was, rows in zip(before[snapshot], rows_on_both_sides(world, snapshot), strict=True)
        ]
        for snapshot in ALL_SNAPSHOTS
    }
    expected = {snapshot: [EXPECTED.rows_dropped.get(snapshot, 0)] * 2 for snapshot in ALL_SNAPSHOTS}
    assert dropped == expected
    for snapshot in EXPECTED.rows_dropped:
        key = snapshot_key(snapshot)
        assert local_manifest_text(world, key) == bucket_manifest_text(world, key)
        assert len(versions_of(world, key)) == 1, "the versions that named it are purged"
    removed = [digest_of(body) for body in EXPECTED.removed_everywhere]
    for text in every_bucket_manifest_version(world):
        assert not [digest for digest in removed if digest in text]


async def test_its_parsed_file_and_the_caselists_aggregates_are_deleted_here_and_in_the_bucket(
    world: RemovalWorld,
) -> None:
    parsed = source_object_key(CASELIST, PARSED_VERSION, LATER_REVISION)
    aggregates = [f"{CASELIST}/{PARSED_VERSION}/{name}" for name in AGGREGATE_NAMES]
    assert len(versions_of(world, f"parsed/{parsed}")) == 2

    await remove_the_named_file(world)

    for name in (parsed, *aggregates):
        assert not (world.data_dir / "parsed" / name).exists(), name
        assert versions_of(world, f"parsed/{name}") == [], name


async def test_the_imported_weekly_in_the_inbox_that_holds_it_is_deleted(world: RemovalWorld) -> None:
    inbox = world.data_dir / "inbox"
    untouched = (inbox / IMPORTED_WEEKLY_HOLDING_THE_EARLIER_VERSION).read_bytes()

    await remove_the_named_file(world)

    assert not (inbox / IMPORTED_WEEKLY_HOLDING_THE_REVISION).exists()
    assert (inbox / IMPORTED_WEEKLY_HOLDING_THE_EARLIER_VERSION).read_bytes() == untouched, (
        "an archive holding only the earlier version holds nothing removed"
    )


async def test_it_is_on_the_suppression_list_in_both_copies(world: RemovalWorld) -> None:
    await remove_the_named_file(world)

    for entries in suppression_lines(world):
        whole = {entry.sha256 for entry in entries if entry.disclosure is None}
        scoped = {(entry.sha256, entry.disclosure) for entry in entries if entry.disclosure is not None}
        assert whole == {NAMED, LATER_REVISION, LATER_IN_COMPLETE_ARCHIVE}
        assert scoped == {(LATER_SHARED, disclosure_digest(CASELIST, REVISED_PATH))}
        assert {entry.request_id for entry in entries} == {REQUEST}


async def test_reimporting_the_weeks_that_held_them_brings_none_of_them_back(
    world: RemovalWorld, tmp_path: Path
) -> None:
    await remove_the_named_file(world)

    importer = CaselistImportService(
        caselists=world.repository,
        blobs=FsSnapshotStore(world.data_dir),
        suppression=RecordedSuppressionList(local_suppression_list_file(world.data_dir)),
    )
    suppressed: dict[str, int] = {}
    for week in (date(2026, 9, 15), date(2026, 10, 6)):
        archive = tmp_path / "downloads" / f"{CASELIST}-weekly-{week.isoformat()}.zip"
        report = await importer.import_archive(
            read_archive(archive, **LIMITS),
            caselist=CASELIST,
            snapshot=week,
            event=Event.LD,
            archive_sha256=archive_digest(archive),
            allow_out_of_order=True,
        )
        suppressed[week.isoformat()] = report.count(Classification.SUPPRESSED)

    # The later revision in the first; the shared revision's copy at the revised path in the second.
    assert suppressed == {"2026-09-15": 1, "2026-10-06": 1}
    assert not local_blob(world, LATER_REVISION).exists()
    remaining = (await world.repository.list_disclosures(source_sha256=LATER_SHARED, limit=10)).items
    assert [one.source_path for one in remaining] == [OTHER_TEAM_PATH]


async def test_the_removal_log_names_every_digest_and_no_one(world: RemovalWorld) -> None:
    await remove_the_named_file(world)

    log = local_removal_log_file(world.data_dir).path.read_text(encoding="utf-8")
    (entry,) = [RemovalLogEntry.from_line(line) for line in log.splitlines()]
    assert set(entry.removed_sha256) == {digest_of(body) for body in EXPECTED.removed_everywhere}
    assert set(entry.withdrawn_sha256) == {
        digest_of(body) for body in EXPECTED.withdrawn_from_the_revised_path
    }
    assert entry.local_records_deleted == EXPECTED.local_records
    listed = local_suppression_list_file(world.data_dir).path.read_text(encoding="utf-8")
    for text in (log, listed):
        assert not [name for name in NAMES if name in text]


# ------------------------------------------------------------------------------------------------
# ac2: what stays
# ------------------------------------------------------------------------------------------------


async def test_a_later_upload_another_path_also_holds_keeps_its_blob_and_that_paths_rows(
    world: RemovalWorld,
) -> None:
    parsed = source_object_key(CASELIST, PARSED_VERSION, LATER_SHARED)

    await remove_the_named_file(world)

    assert local_blob(world, LATER_SHARED).read_bytes() == BODIES["later-also-at-another-path"]
    assert len(versions_of(world, raw_key(LATER_SHARED))) == 1
    assert (world.data_dir / "parsed" / parsed).exists(), "the other path's cards are still its cards"
    assert len(versions_of(world, f"parsed/{parsed}")) == 2
    for rows in rows_on_both_sides(world, "2026-10-06"):
        assert held_at(rows, OTHER_TEAM_PATH) == {LATER_SHARED}
        assert held_at(rows, REVISED_PATH) == set(), "only the removed path's row goes"
    assert await world.repository.find_source(LATER_SHARED) is not None
    kept = (await world.repository.list_disclosures(source_sha256=LATER_SHARED, limit=10)).items
    assert [one.source_path for one in kept] == [OTHER_TEAM_PATH]


async def test_the_waiting_weekly_in_the_inbox_keeps_the_other_paths_copy(world: RemovalWorld) -> None:
    waiting = world.data_dir / "inbox" / WAITING_WEEKLY

    await remove_the_named_file(world)

    assert waiting.exists(), "an archive waiting to be imported is rewritten, never deleted"
    members = zip_members(waiting)
    assert sorted(members) == sorted([OTHER_TEAM_PATH, KEPT_PATH])
    assert members[OTHER_TEAM_PATH] == BODIES["later-also-at-another-path"]


async def test_an_earlier_version_at_the_path_is_left_exactly_as_it_was(world: RemovalWorld) -> None:
    keys = [snapshot_key("2026-09-01"), snapshot_key("full/2026-09-05")]
    manifests = [(local_manifest_text(world, key), bucket_manifest_text(world, key)) for key in keys]
    versions = [versions_of(world, key) for key in keys]
    raw = versions_of(world, raw_key(EARLIER))

    await remove_the_named_file(world)

    assert local_blob(world, EARLIER).read_bytes() == BODIES["earlier-version"]
    assert versions_of(world, raw_key(EARLIER)) == raw and len(raw) == 1
    assert [(local_manifest_text(world, key), bucket_manifest_text(world, key)) for key in keys] == manifests
    assert [versions_of(world, key) for key in keys] == versions
    assert await world.repository.find_source(EARLIER) is not None
    kept = (await world.repository.list_disclosures(source_sha256=EARLIER, limit=10)).items
    assert [(one.snapshot, one.source_path) for one in kept] == [(date(2026, 9, 1), REVISED_PATH)]
    for entries in suppression_lines(world):
        assert EARLIER not in {entry.sha256 for entry in entries}


async def test_the_same_spelling_of_the_path_in_another_caselist_is_another_path(
    world: RemovalWorld,
) -> None:
    key = snapshot_key("2026-09-15", OTHER_CASELIST)
    manifests = (local_manifest_text(world, key), bucket_manifest_text(world, key))
    versions = versions_of(world, key)

    await remove_the_named_file(world)

    assert local_blob(world, OTHER_CASELIST_FILE).read_bytes() == BODIES["other-caselist-same-path"]
    assert len(versions_of(world, raw_key(OTHER_CASELIST_FILE, OTHER_CASELIST))) == 1
    assert (local_manifest_text(world, key), bucket_manifest_text(world, key)) == manifests
    assert versions_of(world, key) == versions
    assert await world.repository.find_source(OTHER_CASELIST_FILE) is not None
    for entries in suppression_lines(world):
        assert OTHER_CASELIST_FILE not in {entry.sha256 for entry in entries}


async def test_everything_else_is_untouched_and_status_is_clean(world: RemovalWorld) -> None:
    await remove_the_named_file(world)

    for body in EXPECTED.untouched:
        assert local_blob(world, digest_of(body)).read_bytes() == BODIES[body], body
    status = await CaselistStatusService(
        local=world.local, remote=world.bucket, suppression=world.suppression()
    ).status()
    assert status.in_sync, [entry for entry in status.snapshots if not entry.in_sync]


# ------------------------------------------------------------------------------------------------
# --team: it already named every version at the team's paths
# ------------------------------------------------------------------------------------------------


async def test_a_team_removal_names_every_version_at_the_teams_paths_from_every_snapshot(
    world: RemovalWorld,
) -> None:
    """`--team` selects by path, so it reaches the earlier version and every later upload itself.

    Alder Point KR's one path held five files across the weekly windows and the complete archives.
    Four are held nowhere else and are removed; the fifth is Birch Hill MT's too, and is withdrawn.
    This asks the planner for nothing `v1-e30-t11` added, and passed before it.
    """
    service = world.service()
    plan = await service.plan(
        parse_team_selector(f"{CASELIST}/Alder Point/KR"),
        request_id=REQUEST,
        reason=ReasonCode.REQUESTED_BY_TEAM,
    )

    assert {source.sha256 for source in plan.of(Disposition.REMOVE)} == {
        EARLIER,
        NAMED,
        LATER_REVISION,
        LATER_IN_COMPLETE_ARCHIVE,
    }
    assert {source.sha256 for source in plan.of(Disposition.WITHDRAW)} == {LATER_SHARED}
    assert len(plan.sources) == 5

    assert (await service.execute(plan)).completed

    for snapshot in ALL_SNAPSHOTS:
        for rows in rows_on_both_sides(world, snapshot):
            assert [row for row in rows if row["path"] == REVISED_PATH] == [], snapshot
    for rows in rows_on_both_sides(world, "2026-10-06"):
        assert held_at(rows, OTHER_TEAM_PATH) == {LATER_SHARED}
    assert local_blob(world, LATER_SHARED).exists() and not local_blob(world, EARLIER).exists()
