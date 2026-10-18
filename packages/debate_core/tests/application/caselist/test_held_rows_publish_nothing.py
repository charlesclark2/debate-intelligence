"""A held path's bytes and skipped rows never reach the bucket on a held row's account (`v1-e30-t22`).

`v1-e30-t21` left two ways a path a removal holds still reached the bucket:

* **A skipped member's row.** An archive holding a symbolic link at the held path, dated after the
  hold, was imported with a `member` row at that path (`skip_reason` `SYMLINK`), and the publisher
  published it. The link's body is usually the removed file's name, and its path names the school
  and the team. The importer now withholds that row, as it withholds junk beside a suppressed file,
  and the removal's manifest rewrite and `caselist status` follow the same rule.
* **A held row's bytes.** The publisher uploaded the bytes a held row names under their digest before
  it withheld the manifest (`v1-e30-t21`'s Decision 2). The PM's ruling, 2026-10-16: bytes that only
  held rows name are not uploaded; bytes that an unheld row also names are, so another team's copy
  is never held back. The publish's outcome, its code and its held counts are unchanged.

Bytes the publisher no longer uploads are still on this machine, so every comparison of this machine
with the bucket is checked here too: `caselist status` and `store sync` count such a digest neither
as drift nor as something the bucket is owed.

The store and the removal are `v1-e30-t21`'s (`test_held_path_loose_ends.py`): `caselist remove
--source <named-version>` holds `(testcl26, REVISED_PATH)` for snapshots dated after `2026-09-08`. A
row at a held path is written as a build from before `v1-e30-t13` writes one
(:class:`~.test_held_path_loose_ends.AnOlderBuildsList`). For an archive with a link at the held path
and no upload there, every build before this task writes the same manifest: the start commit's
importer reads the hold, refuses no member, and writes the link's row too (the report's red run).

Every test runs offline: moto for the bucket, a temporary data directory, and a temporary `HOME`.
"""

from __future__ import annotations

import functools
import json
import stat
import zipfile
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_held_path_archives import ARRIVING_BODIES, arriving_digest_of
from tests.fixtures.caselist.build_revised_path_archives import (
    BODIES,
    CASELIST,
    KEPT_PATH,
    ONE_WEEK_PATH,
    OTHER_TEAM_PATH,
    REVISED_PATH,
)

from debate_core.application.caselist.import_service import CaselistImportService, ImportReport
from debate_core.application.caselist.manifest import manifest_key, write_manifest
from debate_core.application.caselist.publish_plan import source_key
from debate_core.application.caselist.publish_service import (
    MANIFEST_NAMES_SUPPRESSED_SOURCE,
    CaselistPublishService,
    ManifestOutcome,
    PublishReport,
)
from debate_core.application.caselist.status_service import CaselistStatusReport, SnapshotStatus
from debate_core.application.evidence_sync import (
    EvidenceSyncService,
    SyncAction,
    SyncDirection,
    SyncKeyspace,
    SyncPlan,
)
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsEvidenceObjectStore, FsSnapshotStore
from debate_core.integrations.local.archive_reader import archive_digest, read_archive

from .conftest import REQUEST, RemovalWorld
from .test_held_path_loose_ends import (
    HELD_WEEK_MANIFEST,
    LINK_BODY,
    UPLOADED_AFTER,
    UPLOADED_AFTER_AT_TWO_PATHS,
    AnOlderBuildsList,
    an_older_build_imports_next_week,
    status_service,
)
from .test_removal_covers_later_uploads import (
    LIMITS,
    NAMES,
    local_blob,
    remove_the_named_file,
    revised_path_world,
)
from .test_removed_path_holds_later_imports import import_weekly, manifest_rows, offline_importer

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

#: The other team's file in `2026-10-08`: its only row is at `ONE_WEEK_PATH`, which nothing holds.
UPLOADED_AT_ANOTHER_PATH = arriving_digest_of("uploaded-after-at-another-path")
WEEK_OF_THE_LINK = date(2026, 10, 11)
LINK_WEEK_MANIFEST = f"manifests/{CASELIST}/2026-10-11.jsonl"
TWO_PATHS_WEEK = date(2026, 10, 10)
#: The date the hold is asked from: uploads in snapshots dated after it are held.
HOLD_DATE = date(2026, 9, 8)


@pytest.fixture(autouse=True)
def temporary_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A `HOME` of this test's own, so nothing here can read or write the operator's."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


@pytest.fixture
async def world(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> RemovalWorld:
    return await revised_path_world(tmp_path, s3_client, evidence_bucket)


def write_weekly(path: Path, files: dict[str, bytes], links: tuple[str, ...] = ()) -> Path:
    """A weekly archive holding `files`, and a symbolic link at each of `links` whose body is the
    removed file's name, as `v1-e30-t13`'s was."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, body in files.items():
            archive.writestr(zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)), body)
        for name in links:
            link = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(link, LINK_BODY)
    return path


def a_week_with_a_link(tmp_path: Path, *, at: str = REVISED_PATH, week: date = WEEK_OF_THE_LINK) -> Path:
    """`KEPT_PATH`'s file, and a link at `at`."""
    return write_weekly(
        tmp_path / "arriving" / f"{CASELIST}-weekly-{week.isoformat()}.zip",
        {KEPT_PATH: BODIES["kept"]},
        links=(at,),
    )


async def import_archive(
    world: RemovalWorld,
    archive: Path,
    week: date,
    *,
    importer: CaselistImportService | None = None,
    dry_run: bool = False,
    allow_out_of_order: bool = False,
) -> ImportReport:
    """Import one archive as the weekly of `week` and write its manifest, as `caselist import` does."""
    report = await (importer or offline_importer(world)).import_archive(
        read_archive(archive, **LIMITS),
        caselist=CASELIST,
        snapshot=week,
        event=Event.LD,
        archive_sha256=archive_digest(archive),
        dry_run=dry_run,
        allow_out_of_order=allow_out_of_order,
    )
    if not dry_run:
        write_manifest(report, FsEvidenceObjectStore(world.data_dir).path_for(manifest_key(CASELIST, week)))
    return report


def an_older_builds_importer(world: RemovalWorld) -> CaselistImportService:
    return CaselistImportService(
        caselists=world.repository,
        blobs=FsSnapshotStore(world.data_dir),
        suppression=AnOlderBuildsList(world.suppression()),
    )


def an_older_builds_publisher(world: RemovalWorld) -> CaselistPublishService:
    return CaselistPublishService(
        local=world.local, remote=world.bucket, suppression=AnOlderBuildsList(world.suppression())
    )


def this_builds_publisher(world: RemovalWorld) -> CaselistPublishService:
    return CaselistPublishService(local=world.local, remote=world.bucket, suppression=world.suppression())


def rows_at(world: RemovalWorld, key: str, path: str) -> list[dict[str, object]]:
    return [row for row in manifest_rows(world, key) if row["path"] == path]


def in_the_bucket(world: RemovalWorld, digest: str) -> bool:
    """Whether the bucket holds a current object of `digest` under the caselist's source prefix."""
    key = source_key(CASELIST, "2026-10-08", digest)
    return world.client.list_objects_v2(Bucket=world.bucket_name, Prefix=key).get("KeyCount", 0) == 1


def bucket_manifest(world: RemovalWorld, key: str) -> bytes | None:
    listed = world.client.list_objects_v2(Bucket=world.bucket_name, Prefix=key)
    if listed.get("KeyCount", 0) == 0:
        return None
    return world.client.get_object(Bucket=world.bucket_name, Key=key)["Body"].read()


def delete_from_the_bucket(world: RemovalWorld, digest: str) -> None:
    world.client.delete_object(Bucket=world.bucket_name, Key=source_key(CASELIST, "2026-10-08", digest))


def names_no_one(report: CaselistStatusReport) -> None:
    """What the comparison reports of a hold names no path, school, team code or file name."""
    said = json.dumps(
        [
            [
                one.snapshot,
                list(one.held_skipped_rows),
                [[row.sha256, row.request_id] for row in one.held_rows],
            ]
            for one in report.snapshots
        ]
    )
    assert not [word for word in (*NAMES, REVISED_PATH, ".zip", ".docx") if word in said], said


def of_snapshot(report: CaselistStatusReport, snapshot: str) -> SnapshotStatus:
    (found,) = [one for one in report.snapshots if one.snapshot == snapshot]
    return found


# ------------------------------------------------------------------------------------------------
# ac1: a skipped member at a held path imports with no row there
# ------------------------------------------------------------------------------------------------


async def test_a_link_at_the_held_path_imports_with_no_row_at_that_path(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """Dated after the hold. The link is still counted as skipped, as junk beside a suppressed file
    is: the archive held it. Only its row, which names the path, is left out."""
    await remove_the_named_file(world)

    report = await import_archive(world, a_week_with_a_link(tmp_path), WEEK_OF_THE_LINK)

    assert rows_at(world, LINK_WEEK_MANIFEST, REVISED_PATH) == [], "the link's row names the held path"
    assert [row["path"] for row in manifest_rows(world, LINK_WEEK_MANIFEST) if row["path"] == KEPT_PATH] == [
        KEPT_PATH
    ]
    assert {str(reason): count for reason, count in report.skipped.items()} == {"SYMLINK": 1}
    assert [
        entry.withheld for entry in report.entries if entry.is_skipped and entry.path == REVISED_PATH
    ] == [True]


async def test_a_link_at_a_path_no_removal_holds_keeps_its_row(world: RemovalWorld, tmp_path: Path) -> None:
    """In the other team's directory, beside a file nothing stops: the row names nothing removed."""
    await remove_the_named_file(world)

    await import_archive(world, a_week_with_a_link(tmp_path, at=ONE_WEEK_PATH), WEEK_OF_THE_LINK)

    assert [row["skip_reason"] for row in rows_at(world, LINK_WEEK_MANIFEST, ONE_WEEK_PATH)] == ["SYMLINK"]


async def test_a_link_at_the_held_path_in_the_week_the_hold_dates_from_keeps_its_row(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """The hold covers snapshots dated after `2026-09-08`, the week the removed file first appeared
    there, so a link in that week is not held. A dry run, which writes nothing, shows it."""
    await remove_the_named_file(world)

    report = await import_archive(
        world, a_week_with_a_link(tmp_path, week=HOLD_DATE), HOLD_DATE, dry_run=True, allow_out_of_order=True
    )

    assert [
        entry.withheld for entry in report.entries if entry.is_skipped and entry.path == REVISED_PATH
    ] == [False]


# ------------------------------------------------------------------------------------------------
# ac1 and ac3: an earlier build's row for the link; status names it, and the removal takes it out
# ------------------------------------------------------------------------------------------------


async def an_earlier_build_imports_the_link(world: RemovalWorld, tmp_path: Path) -> Path:
    """After the removal, an earlier build imports the week with the link and publishes it."""
    archive = a_week_with_a_link(tmp_path)
    await import_archive(world, archive, WEEK_OF_THE_LINK, importer=an_older_builds_importer(world))
    assert [row["skip_reason"] for row in rows_at(world, LINK_WEEK_MANIFEST, REVISED_PATH)] == ["SYMLINK"], (
        "the precondition: the earlier build wrote the link's row"
    )
    publisher = an_older_builds_publisher(world)
    assert (await publisher.execute(await publisher.plan(CASELIST, "2026-10-11"))).succeeded
    return archive


async def test_status_names_an_earlier_builds_row_for_a_link_at_the_held_path(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """By the request holding the path, never by the path, and beside the verdict: the bucket holds
    what this machine holds, so the comparison still agrees and `caselist status` exits 0."""
    await remove_the_named_file(world)
    await an_earlier_build_imports_the_link(world, tmp_path)

    report = await status_service(world).status(CASELIST)

    assert of_snapshot(report, "2026-10-11").held_skipped_rows == (REQUEST,)
    assert [one.snapshot for one in report.held_snapshots] == ["2026-10-11"]
    assert report.removals_owed == (REQUEST,)
    assert report.in_sync, report.drifted
    names_no_one(report)


async def test_status_does_not_name_a_link_at_a_path_no_removal_holds(
    world: RemovalWorld, tmp_path: Path
) -> None:
    await remove_the_named_file(world)
    await import_archive(world, a_week_with_a_link(tmp_path, at=ONE_WEEK_PATH), WEEK_OF_THE_LINK)

    report = await status_service(world).status(CASELIST, "2026-10-11")

    assert of_snapshot(report, "2026-10-11").held_skipped_rows == ()
    assert report.removals_owed == ()


async def test_running_the_removal_again_takes_the_links_row_out_here_and_in_the_bucket(
    world: RemovalWorld, tmp_path: Path
) -> None:
    await remove_the_named_file(world)
    await an_earlier_build_imports_the_link(world, tmp_path)

    await remove_the_named_file(world)

    assert rows_at(world, LINK_WEEK_MANIFEST, REVISED_PATH) == []
    assert rows_at(world, LINK_WEEK_MANIFEST, KEPT_PATH), "the rest of the manifest stays"
    in_bucket = bucket_manifest(world, LINK_WEEK_MANIFEST)
    assert in_bucket is not None and REVISED_PATH.encode() not in in_bucket
    report = await status_service(world).status(CASELIST)
    assert (report.held_snapshots, report.removals_owed) == ((), ())
    assert report.in_sync, report.drifted


async def test_the_removals_rewrite_and_this_builds_import_leave_the_same_manifest(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """The two agree byte for byte: the week the removal rewrote, and the same archive imported again
    by this build afterwards, as a re-import writes its own manifest again."""
    await remove_the_named_file(world)
    archive = await an_earlier_build_imports_the_link(world, tmp_path)
    await remove_the_named_file(world)
    local = FsEvidenceObjectStore(world.data_dir).path_for(LINK_WEEK_MANIFEST)
    rewritten = local.read_bytes()

    await import_archive(world, archive, WEEK_OF_THE_LINK)

    assert local.read_bytes() == rewritten


async def test_the_removal_drops_a_links_row_at_the_path_it_holds_the_first_time_it_runs(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """The link's week imported before the removal, so no hold stopped it. The removal holds the
    path from `2026-09-08` on, and rewrites the week with what it is about to hold."""
    await import_archive(world, a_week_with_a_link(tmp_path), WEEK_OF_THE_LINK)
    assert rows_at(world, LINK_WEEK_MANIFEST, REVISED_PATH), "the precondition: no hold stopped it"

    await remove_the_named_file(world)

    assert rows_at(world, LINK_WEEK_MANIFEST, REVISED_PATH) == []


async def test_the_removal_keeps_a_links_row_at_a_path_it_does_not_hold(
    world: RemovalWorld, tmp_path: Path
) -> None:
    await import_archive(world, a_week_with_a_link(tmp_path, at=ONE_WEEK_PATH), WEEK_OF_THE_LINK)

    await remove_the_named_file(world)

    assert [row["skip_reason"] for row in rows_at(world, LINK_WEEK_MANIFEST, ONE_WEEK_PATH)] == ["SYMLINK"]


# ------------------------------------------------------------------------------------------------
# ac2: bytes only held rows name are not uploaded; bytes an unheld row names are
# ------------------------------------------------------------------------------------------------


async def test_bytes_only_a_held_row_names_are_not_uploaded(world: RemovalWorld, tmp_path: Path) -> None:
    """`2026-10-08`, imported by an older build and not published: `uploaded-after-the-removal` is
    at the held path and nowhere else, and `uploaded-after-at-another-path` is the other team's,
    at a path nothing holds. The first stays off the bucket, the second goes up, and the manifest
    is withheld with the same outcome, code and held count as before."""
    await remove_the_named_file(world)
    await an_older_build_imports_next_week(world, tmp_path, publish=False)
    publisher = this_builds_publisher(world)

    plan = await publisher.plan(CASELIST, "2026-10-08")
    report = await publisher.execute(plan)

    assert not in_the_bucket(world, UPLOADED_AFTER), "bytes only a held row names were uploaded"
    assert in_the_bucket(world, UPLOADED_AT_ANOTHER_PATH), "the other team's file was held back"
    assert UPLOADED_AFTER not in {source.sha256 for source in plan.uploads}
    (outcome,) = report.snapshots
    assert (outcome.manifest, outcome.manifest_error_code) == (
        ManifestOutcome.WITHHELD,
        MANIFEST_NAMES_SUPPRESSED_SOURCE,
    )
    assert (report.succeeded, report.failed_sha256, report.failure_codes) == (
        False,
        (),
        (MANIFEST_NAMES_SUPPRESSED_SOURCE,),
    )
    assert (report.held_rows, report.suppressed_rows) == ((UPLOADED_AFTER,), ())
    assert outcome.manifest_error is not None
    assert f"1 row(s) at a path a removal holds: {UPLOADED_AFTER} ({REQUEST})" in outcome.manifest_error
    assert "whose bytes no other row names and were not uploaded (1)" in outcome.manifest_error
    assert not [word for word in (*NAMES, REVISED_PATH) if word in outcome.manifest_error]
    assert bucket_manifest(world, HELD_WEEK_MANIFEST) is None


async def test_a_dry_run_plans_no_upload_of_bytes_only_a_held_row_names(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """The plan is where the rule is: a dry run's planned uploads and bytes leave them out, and its
    verdict is the same as before, because the manifest would still be withheld."""
    await remove_the_named_file(world)
    await an_older_build_imports_next_week(world, tmp_path, publish=False)

    plan = await this_builds_publisher(world).plan(CASELIST, "2026-10-08")

    assert {source.sha256 for source in plan.uploads} == {UPLOADED_AT_ANOTHER_PATH}
    assert plan.bytes_to_upload == len(ARRIVING_BODIES["uploaded-after-at-another-path"])
    assert PublishReport(plan=plan, applied=False).succeeded is False


async def test_bytes_a_held_row_and_another_teams_row_name_are_uploaded(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """`2026-10-10` holds `uploaded-after-at-two-paths` at the held path and at the other team's
    path. The other team's copy is never held back: its bytes go up, and the manifest is withheld
    for the held row as before."""
    await remove_the_named_file(world)
    await import_weekly(world, tmp_path, CASELIST, TWO_PATHS_WEEK, importer=an_older_builds_importer(world))
    assert rows_at(world, f"manifests/{CASELIST}/2026-10-10.jsonl", REVISED_PATH), "the precondition"

    report = await this_builds_publisher(world).execute(
        await this_builds_publisher(world).plan(CASELIST, "2026-10-10")
    )

    assert in_the_bucket(world, UPLOADED_AFTER_AT_TWO_PATHS), "another team's copy was held back"
    (outcome,) = report.snapshots
    assert (outcome.manifest, report.held_rows) == (ManifestOutcome.WITHHELD, (UPLOADED_AFTER_AT_TWO_PATHS,))


async def test_bytes_a_later_week_names_at_another_teams_path_are_uploaded_with_that_week(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """Held only in `2026-10-08`, and the other team's file at its own path in `2026-10-12`: one
    publish of the caselist uploads the bytes for the later week and withholds the earlier one."""
    await remove_the_named_file(world)
    await an_older_build_imports_next_week(world, tmp_path, publish=False)
    later = write_weekly(
        tmp_path / "arriving" / f"{CASELIST}-weekly-2026-10-12.zip",
        {OTHER_TEAM_PATH: ARRIVING_BODIES["uploaded-after-the-removal"], KEPT_PATH: BODIES["kept"]},
    )
    await import_archive(world, later, date(2026, 10, 12))

    report = await this_builds_publisher(world).execute(await this_builds_publisher(world).plan(CASELIST))

    assert in_the_bucket(world, UPLOADED_AFTER), "the later week's copy was held back"
    outcomes = {one.snapshot: one.manifest for one in report.snapshots}
    assert outcomes["2026-10-08"] is ManifestOutcome.WITHHELD
    assert outcomes["2026-10-12"] is ManifestOutcome.UPLOADED


# ------------------------------------------------------------------------------------------------
# Every comparison of this machine with the bucket: such a digest is neither drift nor owed
# ------------------------------------------------------------------------------------------------


async def test_status_does_not_count_bytes_the_publisher_left_out_as_missing(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """After this build's publish of `2026-10-08`. The snapshot still differs, because its manifest
    is withheld, exactly as it did when the held bytes were uploaded; but the bucket is not owed the
    bytes, so they are not among the missing sources."""
    await remove_the_named_file(world)
    await an_older_build_imports_next_week(world, tmp_path, publish=False)
    await this_builds_publisher(world).execute(
        await this_builds_publisher(world).plan(CASELIST, "2026-10-08")
    )

    held_week = of_snapshot(await status_service(world).status(CASELIST), "2026-10-08")

    assert held_week.missing_sources == ()
    assert (held_week.manifest_present, held_week.in_sync) == (False, False)
    assert [(row.sha256, row.request_id) for row in held_week.held_rows] == [(UPLOADED_AFTER, REQUEST)]


async def test_a_bucket_without_bytes_only_a_held_row_names_still_agrees(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """The comparison's rule on its own: with the manifest in the bucket and the held-only bytes not,
    the snapshot is in sync and `caselist status` exits 0. Counting them would make it drift."""
    await remove_the_named_file(world)
    await an_older_build_imports_next_week(world, tmp_path)
    delete_from_the_bucket(world, UPLOADED_AFTER)

    report = await status_service(world).status(CASELIST)

    assert report.in_sync, report.drifted
    assert of_snapshot(report, "2026-10-08").missing_sources == ()


async def test_a_bucket_without_bytes_another_teams_row_names_still_differs(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """`uploaded-after-at-two-paths` is the other team's too, so the bucket owes it: missing is drift."""
    await remove_the_named_file(world)
    await import_weekly(world, tmp_path, CASELIST, TWO_PATHS_WEEK, importer=an_older_builds_importer(world))
    publisher = an_older_builds_publisher(world)
    assert (await publisher.execute(await publisher.plan(CASELIST, "2026-10-10"))).succeeded
    delete_from_the_bucket(world, UPLOADED_AFTER_AT_TWO_PATHS)

    report = await status_service(world).status(CASELIST, "2026-10-10")

    assert of_snapshot(report, "2026-10-10").missing_sources == (UPLOADED_AFTER_AT_TWO_PATHS,)
    assert not report.in_sync


def store_sync(world: RemovalWorld) -> EvidenceSyncService:
    """`store sync --blob-prefix raw/caselist/testcl26`, built as the composition root builds it."""
    # Imported here so that this file collects on a build without it, for the red run.
    from debate_core.application.caselist.evidence_listing import held_back_digests  # noqa: PLC0415

    local = world.local
    return EvidenceSyncService(
        suppression=world.suppression(),
        keyspaces=(
            SyncKeyspace(name="objects", local=local.objects, remote=world.bucket),
            SyncKeyspace(
                name="blobs",
                local=local.blobs,
                remote=world.bucket,
                remote_prefix=f"raw/caselist/{CASELIST}",
                content_addressed=True,
            ),
        ),
        held_back=functools.partial(held_back_digests, local),
    )


def planned_blob(plan: SyncPlan, digest: str) -> tuple[SyncAction, str]:
    (found,) = [one for one in plan.objects if one.keyspace == "blobs" and one.local_key.endswith(digest)]
    return found.action, found.reason


async def test_store_sync_does_not_push_bytes_only_a_held_row_names(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """`store sync` compares every local blob with the bucket. A blob absent there is planned `new`
    and pushed, which would put the held bytes in the bucket after all. It is planned `skipped`."""
    await remove_the_named_file(world)
    await an_older_build_imports_next_week(world, tmp_path, publish=False)
    service = store_sync(world)

    plan = await service.plan(prefix=f"raw/caselist/{CASELIST}/", direction=SyncDirection.PUSH)
    report = await service.execute(plan)

    action, reason = planned_blob(plan, UPLOADED_AFTER)
    assert action is SyncAction.SKIPPED
    assert "a path a removal holds" in reason
    assert not [word for word in (*NAMES, REVISED_PATH) if word in reason]
    assert planned_blob(plan, UPLOADED_AT_ANOTHER_PATH)[0] is SyncAction.NEW
    assert report.succeeded
    assert not in_the_bucket(world, UPLOADED_AFTER)
    assert in_the_bucket(world, UPLOADED_AT_ANOTHER_PATH)


async def test_store_sync_pushes_bytes_another_teams_row_names(world: RemovalWorld, tmp_path: Path) -> None:
    await remove_the_named_file(world)
    await import_weekly(world, tmp_path, CASELIST, TWO_PATHS_WEEK, importer=an_older_builds_importer(world))

    plan = await store_sync(world).plan(prefix=f"raw/caselist/{CASELIST}/", direction=SyncDirection.PUSH)

    assert planned_blob(plan, UPLOADED_AFTER_AT_TWO_PATHS)[0] is SyncAction.NEW


async def test_store_sync_pushes_bytes_another_weeks_row_names_at_a_path_nothing_holds(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """Held only in `2026-10-08`, and the other team's file at its own path in `2026-10-12`. A blob
    names no corpus or snapshot, so another manifest's row is another holder's copy, which a push
    never holds back."""
    await remove_the_named_file(world)
    await an_older_build_imports_next_week(world, tmp_path, publish=False)
    later = write_weekly(
        tmp_path / "arriving" / f"{CASELIST}-weekly-2026-10-12.zip",
        {OTHER_TEAM_PATH: ARRIVING_BODIES["uploaded-after-the-removal"], KEPT_PATH: BODIES["kept"]},
    )
    await import_archive(world, later, date(2026, 10, 12))

    plan = await store_sync(world).plan(prefix=f"raw/caselist/{CASELIST}/", direction=SyncDirection.PUSH)

    assert planned_blob(plan, UPLOADED_AFTER)[0] is SyncAction.NEW


# ------------------------------------------------------------------------------------------------
# The same removal run again: what goes, here and in the bucket
# ------------------------------------------------------------------------------------------------


async def test_running_the_removal_again_takes_the_held_only_bytes_off_this_machine_as_well(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """After this build's publish left them off the bucket. The re-run finds the held row as a later
    upload, held at no other path, and removes it whole: the list names its sha256, the local blob
    goes, the manifest is rewritten, and the next publish completes the week."""
    await remove_the_named_file(world)
    await an_older_build_imports_next_week(world, tmp_path, publish=False)
    await this_builds_publisher(world).execute(
        await this_builds_publisher(world).plan(CASELIST, "2026-10-08")
    )
    assert local_blob(world, UPLOADED_AFTER).exists(), "the precondition: the older build stored it"

    await remove_the_named_file(world)

    assert not local_blob(world, UPLOADED_AFTER).exists()
    listed = {
        (entry.sha256, entry.disclosure, entry.request_id) for entry in await world.suppression().entries()
    }
    assert (UPLOADED_AFTER, None, REQUEST) in listed, "the list does not name it as a whole file"
    assert rows_at(world, HELD_WEEK_MANIFEST, REVISED_PATH) == []
    assert not in_the_bucket(world, UPLOADED_AFTER)
    assert (
        await this_builds_publisher(world).execute(await this_builds_publisher(world).plan(CASELIST))
    ).succeeded
    report = await status_service(world).status(CASELIST)
    assert report.in_sync and report.removals_owed == (), report.drifted


async def test_running_the_removal_again_keeps_bytes_another_teams_row_names(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """`2026-10-10`, imported by an older build: the re-run withdraws the upload from the held path
    only. The other team's copy keeps its row, its blob here and its object in the bucket."""
    await remove_the_named_file(world)
    await import_weekly(world, tmp_path, CASELIST, TWO_PATHS_WEEK, importer=an_older_builds_importer(world))
    await this_builds_publisher(world).execute(
        await this_builds_publisher(world).plan(CASELIST, "2026-10-10")
    )

    await remove_the_named_file(world)

    week = f"manifests/{CASELIST}/2026-10-10.jsonl"
    assert rows_at(world, week, REVISED_PATH) == []
    assert [row["sha256"] for row in rows_at(world, week, OTHER_TEAM_PATH)] == [UPLOADED_AFTER_AT_TWO_PATHS]
    assert local_blob(world, UPLOADED_AFTER_AT_TWO_PATHS).exists()
    assert in_the_bucket(world, UPLOADED_AFTER_AT_TWO_PATHS)
