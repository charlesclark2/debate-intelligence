"""What status, the publisher and the removal's inbox step do about a held caselist path (`v1-e30-t21`).

`v1-e30-t13` made a whole-file `--source` removal hold the removed file's path, and taught the
importer and the removal plan to ask the hold. It left four loose ends, which this task ties:

* `caselist status` said nothing of an upload held in the download inbox, or of a manifest row at a
  held path, though either means the same removal is owed again;
* the publisher published a manifest with a row at a held path;
* an archive that held only removed or held files stayed in the inbox after its import (the pull's
  half is in `test_held_path_inbox_copies.py`);
* a skipped member named as the removed file stayed in an archive the removal rewrote.

The store is `v1-e30-t11`'s and what arrives is `v1-e30-t13`'s
(`tests/fixtures/caselist/build_held_path_archives.py`, whose docstring works out by hand where each
upload is and what holds it). The removal is `caselist remove --source <named-version> --execute`,
which holds `(testcl26, REVISED_PATH)` for snapshots after `2026-09-08`.

**A row at a held path is what an older build leaves.** This build's importer refuses an upload at a
held path, so the row has to be written the way a build from before `v1-e30-t13` writes it: by an
importer over the suppression list's lines and no path-hold record, which is all those builds read
(:class:`AnOlderBuildsList`; `v1-e30-t13`'s compatibility finding, "knows of path holds: False").
That the real older builds do exactly this is shown by running their own code in the report's
compatibility section.
"""

from __future__ import annotations

import json
import shutil
import stat
import zipfile
from collections.abc import Collection, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_held_path_archives import (
    arriving_digest_of,
    build_arriving_complete_archive_zips,
    build_arriving_weekly_zips,
)
from tests.fixtures.caselist.build_revised_path_archives import (
    BODIES,
    CASELIST,
    KEPT_PATH,
    OTHER_CASELIST,
    REVISED_PATH,
    digest_of,
)

from debate_core.application.caselist.evidence_listing import snapshots_before_full_archive
from debate_core.application.caselist.import_service import CaselistImportService
from debate_core.application.caselist.inbox_purge import CaselistInbox, InboxAction, read_inbox
from debate_core.application.caselist.manifest import full_archive_manifest_key, write_manifest
from debate_core.application.caselist.publish_service import (
    MANIFEST_NAMES_SUPPRESSED_SOURCE,
    CaselistPublishService,
    ManifestOutcome,
    PublishReport,
    SourceResult,
)
from debate_core.application.caselist.removal_plan import SourceSelector
from debate_core.application.caselist.status_service import CaselistStatusReport, CaselistStatusService
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.ports.archive import InventoriedEntry
from debate_core.application.ports.suppression import (
    PathHoldEntry,
    ReasonCode,
    SuppressionAction,
    SuppressionEntry,
    SuppressionList,
    disclosure_digest,
)
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsEvidenceObjectStore, FsSnapshotStore
from debate_core.integrations.local.archive_reader import archive_digest, read_archive
from debate_core.testing.fakes import InMemoryAppendOnlyRecord

from .conftest import REQUEST, RemovalWorld
from .test_removal_covers_later_uploads import (
    LIMITS,
    NAMED,
    NAMES,
    OTHER_CASELIST_FILE,
    remove_the_named_file,
    revised_path_world,
)
from .test_removed_path_holds_later_imports import import_weekly, manifest_rows

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

UPLOADED_AFTER = arriving_digest_of("uploaded-after-the-removal")
UPLOADED_AFTER_IN_A_COMPLETE_ARCHIVE = arriving_digest_of("uploaded-after-in-a-complete-archive")
UPLOADED_AFTER_AT_TWO_PATHS = arriving_digest_of("uploaded-after-at-two-paths")
WEEK_OF_THE_HELD_ROW = date(2026, 10, 8)
HELD_WEEK_MANIFEST = f"manifests/{CASELIST}/2026-10-08.jsonl"

#: A symbolic link named as the removed file, whose body is the file's name, as `v1-e30-t13`'s was.
LINK_BODY = b"Alder Point-KR-Aff-Lakeshore Open-Round 1.docx"


@pytest.fixture
async def world(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> RemovalWorld:
    return await revised_path_world(tmp_path, s3_client, evidence_bucket)


class AnOlderBuildsList:
    """The suppression list as a build from before `v1-e30-t13` reads it: its lines, no path holds.

    It is not a :class:`~debate_core.application.ports.suppression.PathHoldList`, so a service built
    over it reads no hold, which is what those builds' services do.
    """

    def __init__(self, inner: SuppressionList) -> None:
        self._inner = inner

    async def entries(self) -> tuple[SuppressionEntry, ...]:
        return await self._inner.entries()

    async def append(self, entries: Sequence[SuppressionEntry]) -> None:
        await self._inner.append(entries)


async def an_older_build_imports_next_week(
    world: RemovalWorld, scratch: Path, *, publish: bool = True
) -> None:
    """After the removal, the weekly of 2026-10-08 imported, and published, by an older build.

    Its importer stores `uploaded-after-the-removal` at the held path, and its publisher puts the
    manifest in the bucket, as the agent running such a build would.
    """
    older = AnOlderBuildsList(world.suppression())
    importer = CaselistImportService(
        caselists=world.repository, blobs=FsSnapshotStore(world.data_dir), suppression=older
    )
    await import_weekly(world, scratch, CASELIST, WEEK_OF_THE_HELD_ROW, importer=importer)
    rows = manifest_rows(world, HELD_WEEK_MANIFEST)
    assert {row["sha256"] for row in rows if row["path"] == REVISED_PATH} == {UPLOADED_AFTER}, (
        "the precondition: the older build stored the upload at the held path"
    )
    if publish:
        publisher = CaselistPublishService(local=world.local, remote=world.bucket, suppression=older)
        assert (await publisher.execute(await publisher.plan(CASELIST))).succeeded


async def an_older_build_imports_the_next_complete_archive(world: RemovalWorld, scratch: Path) -> None:
    """After the removal, the complete archive of 2026-10-09 imported by an older build, unpublished."""
    day = date(2026, 10, 9)
    archive = build_arriving_complete_archive_zips(scratch / "arriving")[(CASELIST, day)]
    importer = CaselistImportService(
        caselists=world.repository,
        blobs=FsSnapshotStore(world.data_dir),
        suppression=AnOlderBuildsList(world.suppression()),
    )
    previous, earlier = await snapshots_before_full_archive(world.local, CASELIST, day)
    report = await importer.import_full_archive(
        read_archive(archive, **LIMITS),
        caselist=CASELIST,
        archive_date=day,
        event=Event.LD,
        archive_sha256=archive_digest(archive),
        previous=previous,
        earlier=earlier,
    )
    write_manifest(
        report, FsEvidenceObjectStore(world.data_dir).path_for(full_archive_manifest_key(CASELIST, day))
    )


def status_service(world: RemovalWorld) -> CaselistStatusService:
    """The comparison as `caselist status` builds it, with the inbox the pull downloads into."""
    return CaselistStatusService(
        local=world.local, remote=world.bucket, suppression=world.suppression(), inbox=world.inbox
    )


def put_in_the_inbox(world: RemovalWorld, scratch: Path) -> None:
    """Every archive that arrives after the removal, both caselists', downloaded and not imported."""
    inbox = world.data_dir / "inbox"
    built = {
        **build_arriving_weekly_zips(scratch / "arriving"),
        **build_arriving_complete_archive_zips(scratch / "arriving"),
    }
    for path in built.values():
        shutil.copyfile(path, inbox / path.name)


def write_archive_with_a_link(path: Path) -> Path:
    """`KEPT_PATH`'s file, and a symbolic link at the removed path whose body is the file's name."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(zipfile.ZipInfo(KEPT_PATH, date_time=(1980, 1, 1, 0, 0, 0)), BODIES["kept"])
        link = zipfile.ZipInfo(REVISED_PATH, date_time=(1980, 1, 1, 0, 0, 0))
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, LINK_BODY)
    return path


def members_of(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        return sorted(info.filename for info in archive.infolist())


def rows_of(held: Sequence[object]) -> list[tuple[object, ...]]:
    """Each held row as `(sha256, request id)`."""
    return [(row.sha256, row.request_id) for row in held]  # type: ignore[attr-defined]


def uploads_of(held: Sequence[object]) -> list[tuple[object, ...]]:
    """Each held inbox upload as `(caselist, snapshot, sha256, request id)`."""
    return [(one.caselist, one.snapshot, one.sha256, one.request_id) for one in held]  # type: ignore[attr-defined]


def names_no_one(report: CaselistStatusReport) -> None:
    """Nothing the comparison reports about a hold carries a path, a school, a team code or a file name."""
    said = json.dumps(
        [
            [[row.sha256, row.request_id] for one in report.snapshots for row in one.held_rows],
            [[one.caselist, one.snapshot, one.sha256, one.request_id] for one in report.held_in_inbox],
        ]
    )
    assert not [word for word in (*NAMES, REVISED_PATH, ".zip", ".docx") if word in said], said


# ------------------------------------------------------------------------------------------------
# ac1: status reports a row at a held path and an upload held in the inbox; its verdict is unchanged
# ------------------------------------------------------------------------------------------------


async def test_status_reports_a_row_an_older_build_imported_at_a_held_path(
    world: RemovalWorld, tmp_path: Path
) -> None:
    await remove_the_named_file(world)
    await an_older_build_imports_next_week(world, tmp_path)

    report = await status_service(world).status(CASELIST)

    held = {one.snapshot: rows_of(one.held_rows) for one in report.snapshots if one.held_rows}
    assert held == {"2026-10-08": [(UPLOADED_AFTER, REQUEST)]}
    assert report.removals_owed == (REQUEST,)
    names_no_one(report)


async def test_status_and_the_publisher_find_a_held_row_in_a_complete_archive_too(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """`full/2026-10-09` holds `uploaded-after-in-a-complete-archive` at the held path, dated after
    the hold's date: the complete archive's name gives the date the hold is asked with."""
    await remove_the_named_file(world)
    await an_older_build_imports_the_next_complete_archive(world, tmp_path)

    report = await status_service(world).status(CASELIST, "full/2026-10-09")
    plan = await CaselistPublishService(
        local=world.local, remote=world.bucket, suppression=world.suppression()
    ).plan(CASELIST, "full/2026-10-09")

    assert [rows_of(one.held_rows) for one in report.snapshots] == [
        [(UPLOADED_AFTER_IN_A_COMPLETE_ARCHIVE, REQUEST)]
    ]
    assert [one.withholding_rows for one in plan.snapshots] == [(UPLOADED_AFTER_IN_A_COMPLETE_ARCHIVE,)]


async def test_a_held_row_the_list_now_names_is_a_suppressed_row_and_not_a_held_one(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """The same removal run again and stopped after its suppress step: the held upload is on the list
    under the request, and the manifest is not yet rewritten. The row is what a removal did not
    finish, a suppressed row, which is drift; it is not reported twice."""
    await remove_the_named_file(world)
    await an_older_build_imports_next_week(world, tmp_path)
    await world.suppression().append(
        [
            SuppressionEntry(
                action=SuppressionAction.SUPPRESS,
                sha256=UPLOADED_AFTER,
                recorded_at=datetime(2026, 10, 9, 12, 0, tzinfo=UTC),
                reason=ReasonCode.REQUESTED_BY_TEAM,
                request_id=REQUEST,
            )
        ]
    )

    report = await status_service(world).status(CASELIST, "2026-10-08")

    assert [(one.suppressed_rows, one.held_rows) for one in report.snapshots] == [((UPLOADED_AFTER,), ())]


async def test_a_held_row_does_not_change_the_verdict(world: RemovalWorld, tmp_path: Path) -> None:
    """The bucket holds what this machine holds, so the comparison agrees, and `caselist status`
    exits 0 as before. The held row is reported beside the verdict, not in it."""
    await remove_the_named_file(world)
    await an_older_build_imports_next_week(world, tmp_path)

    report = await status_service(world).status(CASELIST)

    assert report.in_sync, report.drifted
    assert report.held_snapshots and not report.drifted


async def test_a_row_at_the_held_path_dated_before_the_hold_is_not_reported(world: RemovalWorld) -> None:
    """`2026-09-01` holds `earlier-version` at the removed path: an earlier version, which a removal
    request does not cover (`v1-e30-t11`), and which the removal left in place."""
    await remove_the_named_file(world)

    report = await status_service(world).status(CASELIST)

    assert [one.snapshot for one in report.held_snapshots] == []
    assert report.removals_owed == ()


async def test_status_reports_each_upload_held_in_the_inbox_by_caselist_snapshot_digest_and_request(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """The three `testcl26` archives each hold an upload at the held path. The other team's copy in
    `2026-10-10` is at another path, and `testclb26`'s file is at the same spelling in another
    caselist: neither is held."""
    await remove_the_named_file(world)
    put_in_the_inbox(world, tmp_path)

    report = await status_service(world).status(held_in_inbox=True)

    assert uploads_of(report.held_in_inbox) == [
        (CASELIST, "2026-10-08", UPLOADED_AFTER, REQUEST),
        (CASELIST, "2026-10-10", UPLOADED_AFTER_AT_TWO_PATHS, REQUEST),
        (CASELIST, "full/2026-10-09", UPLOADED_AFTER_IN_A_COMPLETE_ARCHIVE, REQUEST),
    ]
    assert report.held_in_inbox_of(OTHER_CASELIST) == ()
    assert report.removals_owed == (REQUEST,)
    names_no_one(report)


async def test_an_upload_another_caselist_holds_is_reported_only_for_that_caselist(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """With `testclb26`'s path held too, its upload in the inbox is its own caselist's: a comparison
    of `testcl26` alone does not report it, and one of every caselist does."""
    await remove_the_named_file(world)
    put_in_the_inbox(world, tmp_path)
    await world.suppression().append_path_holds(
        [
            PathHoldEntry(
                caselist=OTHER_CASELIST,
                disclosure=disclosure_digest(OTHER_CASELIST, REVISED_PATH),
                sha256=OTHER_CASELIST_FILE,
                after_snapshot=date(2026, 9, 15),
                recorded_at=datetime(2026, 10, 9, 12, 0, tzinfo=UTC),
                reason=ReasonCode.REQUESTED_BY_TEAM,
                request_id="RM-2026-02",
            )
        ]
    )
    other = (
        OTHER_CASELIST,
        "2026-10-08",
        arriving_digest_of("uploaded-after-in-another-caselist"),
        "RM-2026-02",
    )

    one = await status_service(world).status(CASELIST, held_in_inbox=True)
    every = await status_service(world).status(held_in_inbox=True)

    assert other not in uploads_of(one.held_in_inbox) and len(uploads_of(one.held_in_inbox)) == 3
    assert other in uploads_of(every.held_in_inbox)


async def test_the_removed_file_itself_in_a_later_archive_is_the_lists_and_not_reported_as_held(
    world: RemovalWorld,
) -> None:
    """A complete archive holds the removed file until the team takes it down upstream. At the held
    path, dated after the hold, it is still not a held upload: the list stops it by its bytes, and
    the removal's inbox step is what takes it out."""
    await remove_the_named_file(world)
    later = world.data_dir / "inbox" / f"{CASELIST}-all-2026-10-12.zip"
    with zipfile.ZipFile(later, "w") as archive:
        archive.writestr(REVISED_PATH, BODIES["named-version"])
        archive.writestr(KEPT_PATH, BODIES["kept"])

    report = await status_service(world).status(CASELIST, held_in_inbox=True)

    assert uploads_of(report.held_in_inbox) == []


async def test_an_upload_this_build_refused_at_import_is_still_reported_while_its_archive_waits_in_the_inbox(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """The import refuses it and stores nothing, but the archive stays in the inbox until retention
    or the same removal run again takes it out, and the removal is owed until it does."""
    await remove_the_named_file(world)
    put_in_the_inbox(world, tmp_path)
    await import_weekly(world, tmp_path, CASELIST, WEEK_OF_THE_HELD_ROW)

    report = await status_service(world).status(CASELIST, "2026-10-08", held_in_inbox=True)

    assert uploads_of(report.held_in_inbox) == [(CASELIST, "2026-10-08", UPLOADED_AFTER, REQUEST)]
    assert [one.held_rows for one in report.snapshots] == [()], "the import stored no row"


async def test_running_the_same_removal_again_clears_both(world: RemovalWorld, tmp_path: Path) -> None:
    """The hint's promise: after the re-run, status has nothing held to report."""
    await remove_the_named_file(world)
    await an_older_build_imports_next_week(world, tmp_path)
    put_in_the_inbox(world, tmp_path)
    before = await status_service(world).status(CASELIST, held_in_inbox=True)
    assert before.held_snapshots and before.held_in_inbox

    await remove_the_named_file(world)

    after = await status_service(world).status(CASELIST, held_in_inbox=True)
    assert (after.held_snapshots, after.held_in_inbox, after.removals_owed) == ((), (), ())


async def test_the_inbox_is_read_only_when_asked_and_the_pull_never_asks(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """`caselist pull` compares with the same service and no inbox question, so it reads no archive."""
    await remove_the_named_file(world)
    put_in_the_inbox(world, tmp_path)

    assert (await status_service(world).status(CASELIST)).held_in_inbox == ()
    without = CaselistStatusService(local=world.local, remote=world.bucket, suppression=world.suppression())
    with pytest.raises(ValueError, match="needs the inbox"):
        await without.status(CASELIST, held_in_inbox=True)


class NoArchiveMayBeOpened:
    """An archive reader that fails the test if it is asked to open anything."""

    def inventory(self, source: Path) -> tuple[InventoriedEntry, ...]:
        raise AssertionError(f"an archive was opened: {source.name}")

    def rewrite_without(
        self, source: Path, destination: Path, *, drop: Collection[str], comment: bytes
    ) -> None:
        raise AssertionError("an archive was rewritten")


async def test_with_no_path_held_no_archive_in_the_inbox_is_opened(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """Before any removal nothing is held, so the question is answered without reading the inbox."""
    put_in_the_inbox(world, tmp_path)
    inbox = CaselistInbox(
        directory=world.data_dir / "inbox",
        state_dir=world.data_dir,
        archives=NoArchiveMayBeOpened(),
    )
    service = CaselistStatusService(
        local=world.local, remote=world.bucket, suppression=world.suppression(), inbox=inbox
    )

    report = await service.status(CASELIST, held_in_inbox=True)

    assert report.held_in_inbox == ()


async def test_an_archive_the_inbox_cannot_read_is_passed_over(world: RemovalWorld, tmp_path: Path) -> None:
    await remove_the_named_file(world)
    put_in_the_inbox(world, tmp_path)
    (world.data_dir / "inbox" / f"{CASELIST}-weekly-2026-10-12.zip").write_bytes(b"not a zip")

    report = await status_service(world).status(CASELIST, held_in_inbox=True)

    assert {one.snapshot for one in report.held_in_inbox} == {"2026-10-08", "2026-10-10", "full/2026-10-09"}


# ------------------------------------------------------------------------------------------------
# ac2: the publisher withholds a manifest with a row at a held path, as it does a suppressed row
# ------------------------------------------------------------------------------------------------


def the_row_withdrawn_instead(world_entries: Sequence[SuppressionEntry]) -> RecordedSuppressionList:
    """The same list with the held row stopped by a withdrawn disclosure instead, and no path holds.

    A disclosure-scoped entry is the suppression that, like a hold, stops one path and not the bytes:
    the row's own like for like.
    """
    withdrawn = SuppressionEntry(
        action=SuppressionAction.SUPPRESS,
        sha256=UPLOADED_AFTER,
        disclosure=disclosure_digest(CASELIST, REVISED_PATH),
        recorded_at=datetime(2026, 10, 9, 12, 0, tzinfo=UTC),
        reason=ReasonCode.REQUESTED_BY_TEAM,
        request_id=REQUEST,
    )
    lines = [entry.to_line() for entry in (*world_entries, withdrawn)]
    return RecordedSuppressionList(InMemoryAppendOnlyRecord("the list, the row withdrawn", lines))


def what_the_publish_did(report: PublishReport, *, results: bool = True) -> dict[str, object]:
    """Every outcome and count of a publish, and no message; without `results`, every count but
    the source results."""
    return {
        "succeeded": report.succeeded,
        "failed_sha256": report.failed_sha256,
        "failure_codes": report.failure_codes,
        "snapshots": [
            {
                "snapshot": one.snapshot,
                "manifest": one.manifest,
                "manifest_error_code": one.manifest_error_code,
                "results": {result: len(one.of(result)) for result in SourceResult} if results else None,
                "complete": one.complete,
            }
            for one in report.snapshots
        ],
    }


async def test_the_publisher_withholds_a_manifest_with_a_held_row_as_one_with_a_suppressed_row(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """Two plans of the same snapshot from the same listing: one where the hold stops the row, one
    where a withdrawn disclosure does. Each is planned, dry, and carried out: every outcome, code and
    count is the same but one, and the message says which it was. The older build imported the week
    and did not publish it, so the bucket holds no manifest for it before or after.

    The one difference is `v1-e30-t22`'s, the PM's ruling of 2026-10-16: the held row's bytes, which
    no other row names, are not uploaded, where the withdrawn copy's are. Until then this test had
    every count equal (`v1-e30-t21`'s Decision 2)."""
    await remove_the_named_file(world)
    await an_older_build_imports_next_week(world, tmp_path, publish=False)
    held = CaselistPublishService(local=world.local, remote=world.bucket, suppression=world.suppression())
    withdrawn = CaselistPublishService(
        local=world.local,
        remote=world.bucket,
        suppression=the_row_withdrawn_instead(await world.suppression().entries()),
    )

    by_hold = await held.plan(CASELIST, "2026-10-08")
    by_withdrawal = await withdrawn.plan(CASELIST, "2026-10-08")
    dry_held = PublishReport(plan=by_hold, applied=False)
    dry_withdrawn = PublishReport(plan=by_withdrawal, applied=False)

    done_held = await held.execute(by_hold)
    done_withdrawn = await withdrawn.execute(by_withdrawal)

    assert what_the_publish_did(done_held, results=False) == what_the_publish_did(
        done_withdrawn, results=False
    )
    held_results, withdrawn_results = (
        {result: report.count(result) for result in SourceResult} for report in (done_held, done_withdrawn)
    )
    assert {
        **held_results,
        SourceResult.UPLOADED: held_results[SourceResult.UPLOADED] + 1,
    } == withdrawn_results
    (outcome,) = done_held.snapshots
    assert (outcome.manifest, outcome.manifest_error_code) == (
        ManifestOutcome.WITHHELD,
        MANIFEST_NAMES_SUPPRESSED_SOURCE,
    )
    listed = world.client.list_objects_v2(Bucket=world.bucket_name, Prefix=HELD_WEEK_MANIFEST)
    assert listed.get("KeyCount") == 0, "the withheld manifest went up"
    assert dry_held.succeeded is dry_withdrawn.succeeded is False
    (held_plan,), (withdrawn_plan,) = by_hold.snapshots, by_withdrawal.snapshots
    assert {**held_plan.counts, "upload": held_plan.counts["upload"] + 1} == withdrawn_plan.counts
    assert (held_plan.held_back, withdrawn_plan.held_back) == ((UPLOADED_AFTER,), ())
    assert rows_of(held_plan.held_rows) == [(UPLOADED_AFTER, REQUEST)]
    assert (held_plan.suppressed_rows, withdrawn_plan.held_rows) == ((), ())
    assert withdrawn_plan.suppressed_rows == (UPLOADED_AFTER,)
    assert held_plan.withholding_rows == withdrawn_plan.withholding_rows == (UPLOADED_AFTER,)
    assert outcome.manifest_error is not None
    assert f"1 row(s) at a path a removal holds: {UPLOADED_AFTER} ({REQUEST})" in outcome.manifest_error
    assert "re-run `caselist remove`" in outcome.manifest_error
    assert done_held.held_rows == (UPLOADED_AFTER,) and done_held.suppressed_rows == ()
    assert not [word for word in (*NAMES, REVISED_PATH) if word in outcome.manifest_error]


async def test_after_the_removal_alone_nothing_is_withheld(world: RemovalWorld) -> None:
    """The removal leaves no row at the held path in a snapshot the hold covers, and the earlier
    version at that path in `2026-09-01` is not held: every snapshot publishes."""
    await remove_the_named_file(world)
    publisher = CaselistPublishService(
        local=world.local, remote=world.bucket, suppression=world.suppression()
    )

    plan = await publisher.plan(CASELIST)

    assert [one.snapshot for one in plan.snapshots if one.held_rows] == []
    assert (await publisher.execute(plan)).succeeded


async def test_a_row_at_the_held_path_is_published_once_the_removed_file_is_let_back_in(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """An un-suppress of the removed file lifts its hold (`v1-e30-t13`), so the row withholds nothing."""
    await remove_the_named_file(world)
    await an_older_build_imports_next_week(world, tmp_path)
    await world.suppression().append(
        [
            SuppressionEntry(
                action=SuppressionAction.UNSUPPRESS,
                sha256=NAMED,
                recorded_at=datetime(2026, 10, 9, 12, 0, tzinfo=UTC),
                reason=ReasonCode.REMOVED_IN_ERROR,
            )
        ]
    )
    publisher = CaselistPublishService(
        local=world.local, remote=world.bucket, suppression=world.suppression()
    )

    plan = await publisher.plan(CASELIST, "2026-10-08")

    assert [one.held_rows for one in plan.snapshots] == [()]


# ------------------------------------------------------------------------------------------------
# ac3, the skipped member: a removal's rewrite of a waiting archive leaves no link at the held path
# ------------------------------------------------------------------------------------------------


async def test_the_removal_rewrites_a_waiting_archive_without_a_link_named_as_the_removed_file(
    world: RemovalWorld,
) -> None:
    """Downloaded and not imported, dated after the hold's date. Nothing else in it is removed, so
    before this task the removal left it alone with the link, and the file's name, inside."""
    waiting = write_archive_with_a_link(world.data_dir / "inbox" / f"{CASELIST}-weekly-2026-10-11.zip")

    service = world.service()
    plan = await service.plan(SourceSelector(NAMED), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM)

    planned = [one for one in plan.inbox if one.name == waiting.name]
    assert [(one.action, one.dropped, one.entries_kept) for one in planned] == [
        (InboxAction.REWRITE, (REVISED_PATH,), 1)
    ]
    assert planned[0].removed_sha256 == (), "a link is not a removed file"
    assert (await service.execute(plan)).completed
    assert members_of(waiting) == [KEPT_PATH]
    with zipfile.ZipFile(waiting) as archive:
        assert archive.read(KEPT_PATH) == BODIES["kept"]
    assert digest_of("kept") not in {entry.sha256 for entry in plan.suppression_entries}


async def test_a_link_at_the_held_path_is_not_a_held_upload(world: RemovalWorld) -> None:
    """Status reports uploads, which an import would refuse. A link is skipped, never imported."""
    await remove_the_named_file(world)
    write_archive_with_a_link(world.data_dir / "inbox" / f"{CASELIST}-weekly-2026-10-11.zip")

    report = await status_service(world).status(CASELIST, held_in_inbox=True)

    assert uploads_of(report.held_in_inbox) == []


async def test_a_link_at_the_held_path_in_a_waiting_archive_dated_before_the_hold_is_kept(
    world: RemovalWorld,
) -> None:
    """Never imported, and dated before the removed file first appeared there (`2026-09-08`): an
    earlier version's week, which the hold does not cover."""
    early = write_archive_with_a_link(world.data_dir / "inbox" / f"{CASELIST}-weekly-2026-09-04.zip")
    before = early.read_bytes()

    await remove_the_named_file(world)

    assert early.read_bytes() == before


async def test_an_imported_archive_holding_only_such_a_link_and_other_files_is_not_deleted(
    world: RemovalWorld,
) -> None:
    """The forbidden list: an inbox file that holds anything not removed or held is never removed.
    `2026-09-22` is imported, and an imported archive the removal touches is deleted rather than
    rewritten (`v1-e30-t09`), so this one is left as it is for retention."""
    imported = write_archive_with_a_link(world.data_dir / "inbox" / f"{CASELIST}-weekly-2026-09-22.zip")
    before = imported.read_bytes()

    service = world.service()
    plan = await service.plan(SourceSelector(NAMED), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM)

    assert imported.name not in {one.name for one in plan.inbox}
    assert (await service.execute(plan)).completed
    assert imported.read_bytes() == before


async def test_another_requests_removal_leaves_a_held_upload_in_a_waiting_archive_for_its_own_request(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """Only a skipped member is taken out for the hold alone. A held upload's bytes go on the list,
    under the request that holds its path, when that removal is run again; an unrelated removal
    that took it out of the archive first would leave that request nothing to find."""
    await remove_the_named_file(world)
    put_in_the_inbox(world, tmp_path)
    waiting = world.data_dir / "inbox" / f"{CASELIST}-weekly-2026-10-08.zip"
    before = waiting.read_bytes()

    service = world.service()
    other = await service.plan(
        SourceSelector(OTHER_CASELIST_FILE), request_id="RM-2026-02", reason=ReasonCode.REQUESTED_BY_TEAM
    )

    assert waiting.name not in {one.name for one in other.inbox}
    assert (await service.execute(other)).completed
    assert waiting.read_bytes() == before


async def test_the_link_is_still_read_as_a_skipped_member(world: RemovalWorld) -> None:
    """The fixture's precondition: the reader skips the link, so nothing could put it on the list."""
    write_archive_with_a_link(world.data_dir / "inbox" / f"{CASELIST}-weekly-2026-10-11.zip")

    entries = [
        entry
        for file in read_inbox(world.inbox)
        if file.name == f"{CASELIST}-weekly-2026-10-11.zip"
        for entry in file.entries or ()
    ]

    assert [(entry.path, entry.skip_reason is not None) for entry in entries] == [
        (KEPT_PATH, False),
        (REVISED_PATH, True),
    ]
