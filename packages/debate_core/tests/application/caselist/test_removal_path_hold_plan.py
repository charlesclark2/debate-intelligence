"""What a removal plans and writes for a removed path, and what running it again finds (`v1-e30-t13`).

`test_removed_path_holds_later_imports.py` and `test_removal_covers_inbox_revisions.py` check the
store and the inbox, and ask the services for nothing this task added. These tests ask for the rest:
the path entries a plan carries and where they are written, which removals write none, the import
report's count by request, the inbox revisions as the plan lists them, and the two cases only a
second run of the same removal can close:

* an upload **this build refused** at import, which is still in its archive in the inbox;
* an upload **an older build imported**, because a build from before this task reads the list and
  never the path entries beside it.

The store is `v1-e30-t11`'s and what arrives is `tests/fixtures/caselist/build_held_path_archives.py`.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import zipfile
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from tests.fixtures.caselist.build_held_path_archives import (
    ARRIVING_BODIES,
    HELD_FROM,
    arriving_digest_of,
    build_arriving_weekly_zips,
)
from tests.fixtures.caselist.build_revised_path_archives import (
    BODIES,
    CASELIST,
    OTHER_TEAM_PATH,
    REVISED_PATH,
    digest_of,
)

from debate_core.application.caselist import pipeline
from debate_core.application.caselist.import_service import CaselistImportService, Classification
from debate_core.application.caselist.inbox_purge import CaselistInbox, InboxAction, read_inbox
from debate_core.application.caselist.manifest import manifest_key
from debate_core.application.caselist.pipeline import SourceImportPipeline, SuppressedWriteRefused
from debate_core.application.caselist.removal_plan import (
    Disposition,
    Inclusion,
    LaterUploadOutcome,
    RemovalPlan,
    SourceSelector,
    parse_team_selector,
)
from debate_core.application.caselist.status_service import CaselistStatusService
from debate_core.application.caselist.suppression import (
    LocalFallbackSuppressionList,
    ObjectStoreAppendOnlyRecord,
    RecordedSuppressionList,
)
from debate_core.application.errors import StoreCredentialsExpired
from debate_core.application.ports.evidence_store import EvidenceObjectStore, ObjectInfo, ObjectKey
from debate_core.application.ports.suppression import ReasonCode
from debate_core.integrations.local import FsEvidenceObjectStore, FsSnapshotStore
from debate_core.integrations.local.archive_reader import ZipArchiveRewriter
from debate_core.integrations.local.suppression_list import (
    local_path_holds_file,
    local_suppression_list_file,
)
from debate_core.testing.fakes import InMemoryAppendOnlyRecord

from .conftest import REQUEST, RemovalWorld
from .test_removal_covers_inbox_revisions import put_the_arriving_archives_in_the_inbox
from .test_removal_covers_later_uploads import (
    LATER_IN_COMPLETE_ARCHIVE,
    LATER_REVISION,
    LATER_SHARED,
    NAMED,
    NAMES,
    held_at,
    local_blob,
    raw_key,
    remove_the_named_file,
    revised_path_world,
    rows_on_both_sides,
    suppression_lines,
    versions_of,
)
from .test_removed_path_holds_later_imports import (
    import_complete_archive,
    import_weekly,
    manifest_rows,
    offline_importer,
)

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

UPLOADED_AFTER = arriving_digest_of("uploaded-after-the-removal")
UPLOADED_AFTER_IN_A_COMPLETE_ARCHIVE = arriving_digest_of("uploaded-after-in-a-complete-archive")
UPLOADED_AFTER_AT_TWO_PATHS = arriving_digest_of("uploaded-after-at-two-paths")

LOCAL_PATH_HOLDS = Path("suppression") / "path-holds.jsonl"
"""Where this machine keeps the path entries, under the data directory: beside the list."""

BUCKET_PATH_HOLDS = "manifests/_suppression/path-holds.jsonl"
"""Where the bucket keeps them: beside the list, under the one prefix a takedown may write."""

THE_PATH_ENTRY = {
    "schema_version": 1,
    "caselist": "testcl26",
    "disclosure": hashlib.sha256(f"testcl26/{REVISED_PATH}".encode()).hexdigest(),
    "sha256": digest_of("named-version"),
    "after_snapshot": "2026-09-08",
    "recorded_at": "2026-09-30T18:00:00Z",
    "reason": "REQUESTED_BY_TEAM",
    "request_id": "RM-2026-01",
}
"""The one entry `caselist remove --source <named-version>` writes, by hand from the fixture:
`named-version` is held at one path, first in the weekly of `2026-09-08`."""


@pytest.fixture
async def world(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> RemovalWorld:
    return await revised_path_world(tmp_path, s3_client, evidence_bucket)


async def planned(world: RemovalWorld, selector: object = None, **options: bool) -> RemovalPlan:
    return await world.service().plan(
        selector or SourceSelector(NAMED),  # pyright: ignore[reportArgumentType]
        request_id=REQUEST,
        reason=ReasonCode.REQUESTED_BY_TEAM,
        **options,
    )


def local_path_entries(world: RemovalWorld) -> list[dict[str, object]]:
    path = world.data_dir / LOCAL_PATH_HOLDS
    return (
        [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []
    )


def bucket_path_entries(world: RemovalWorld) -> list[dict[str, object]] | None:
    """The bucket's path entries, or `None` when it holds no such object."""
    listed = world.client.list_objects_v2(Bucket=world.bucket_name, Prefix=BUCKET_PATH_HOLDS)
    if not listed.get("Contents"):
        return None
    body = world.client.get_object(Bucket=world.bucket_name, Key=BUCKET_PATH_HOLDS)["Body"].read()
    return [json.loads(line) for line in body.decode("utf-8").splitlines()]


def no_path_entry_anywhere(world: RemovalWorld) -> bool:
    return not (world.data_dir / LOCAL_PATH_HOLDS).exists() and bucket_path_entries(world) is None


# ------------------------------------------------------------------------------------------------
# ac1: a whole-file --source removal writes a path entry
# ------------------------------------------------------------------------------------------------


async def test_the_plan_carries_one_path_entry_for_the_one_path_the_file_is_removed_from(
    world: RemovalWorld,
) -> None:
    plan = await planned(world)

    assert [json.loads(entry.to_line()) for entry in plan.path_holds] == [THE_PATH_ENTRY]
    assert plan.path_holds[0].after_snapshot == HELD_FROM
    assert plan.suppression_after.path_holds == plan.path_holds, "the list as it will read holds the path"
    assert no_path_entry_anywhere(world), "a dry run writes nothing"


async def test_the_hold_is_dated_by_the_first_snapshot_that_held_the_file_whatever_recorded_it(
    world: RemovalWorld,
) -> None:
    """The weekly of `2026-09-08` lost its manifest on both sides; its disclosure record still says
    the file was at the path that week, three weeks before the next snapshot that holds it."""
    key = manifest_key(CASELIST, date(2026, 9, 8))
    FsEvidenceObjectStore(world.data_dir).path_for(key).unlink()
    world.client.delete_object(Bucket=world.bucket_name, Key=key)

    plan = await planned(world)

    assert [entry.after_snapshot for entry in plan.path_holds] == [date(2026, 9, 8)]


async def test_a_copy_of_the_named_file_waiting_in_the_inbox_at_another_path_holds_that_path_too(
    world: RemovalWorld,
) -> None:
    """The team uploaded the same bytes again under a browser's `(1)` name, and the pull has
    downloaded that week and not imported it. The removal takes the file from there as well."""
    second_path = REVISED_PATH.replace(".docx", " (1).docx")
    waiting = world.data_dir / "inbox" / f"{CASELIST}-weekly-2026-10-11.zip"
    with zipfile.ZipFile(waiting, "w") as archive:
        archive.writestr(second_path, BODIES["named-version"])

    plan = await planned(world)

    assert {(entry.disclosure, entry.after_snapshot) for entry in plan.path_holds} == {
        (hashlib.sha256(f"testcl26/{REVISED_PATH}".encode()).hexdigest(), date(2026, 9, 8)),
        (hashlib.sha256(f"testcl26/{second_path}".encode()).hexdigest(), date(2026, 10, 11)),
    }
    assert {entry.sha256 for entry in plan.path_holds} == {NAMED}


async def test_the_executed_removal_writes_it_beside_the_list_here_and_in_the_bucket(
    world: RemovalWorld,
) -> None:
    await remove_the_named_file(world)

    assert local_path_entries(world) == [THE_PATH_ENTRY]
    assert bucket_path_entries(world) == [THE_PATH_ENTRY]
    local = (world.data_dir / LOCAL_PATH_HOLDS).read_text(encoding="utf-8")
    assert not [name for name in NAMES if name in local]
    assert REVISED_PATH not in local


async def test_the_suppression_list_itself_holds_no_line_of_another_shape(world: RemovalWorld) -> None:
    """Every line of the list is a suppression entry as it always was: the path is not in the list."""
    await remove_the_named_file(world)

    for entries in suppression_lines(world):
        assert len(entries) == 4
        assert {entry.sha256 for entry in entries} == {
            NAMED,
            LATER_REVISION,
            LATER_IN_COMPLETE_ARCHIVE,
            LATER_SHARED,
        }
    listed = local_suppression_list_file(world.data_dir).path.read_text(encoding="utf-8")
    assert "after_snapshot" not in listed and "caselist" not in listed


async def test_a_later_upload_the_plan_withdraws_gets_no_path_entry_of_its_own(world: RemovalWorld) -> None:
    """The shared revision stays with the other team, and the path it is withdrawn from is held already."""
    plan = await planned(world)

    assert plan.source(LATER_SHARED) is not None
    assert plan.source(LATER_SHARED).disposition is Disposition.WITHDRAW  # pyright: ignore[reportOptionalMemberAccess]
    assert {entry.sha256 for entry in plan.path_holds} == {NAMED}


async def test_running_the_removal_again_appends_no_second_entry(world: RemovalWorld) -> None:
    await remove_the_named_file(world)

    plan = await planned(world)
    assert plan.path_holds == ()
    assert (await world.service().execute(plan)).completed

    assert local_path_entries(world) == [THE_PATH_ENTRY]
    assert bucket_path_entries(world) == [THE_PATH_ENTRY]


async def test_a_path_a_stopped_run_already_recorded_is_not_recorded_again(world: RemovalWorld) -> None:
    """A run that stopped after the suppress step left the path entry, and the file's rows too. The
    run that finishes it is a day later, so an entry it wrote would be a second line for one path."""
    recorded = {**THE_PATH_ENTRY, "recorded_at": "2026-09-29T09:00:00Z"}
    line = json.dumps(recorded, sort_keys=True, separators=(",", ":"))
    await local_path_holds_file(world.data_dir).append_lines([line])

    plan = await planned(world)

    assert plan.path_holds == ()
    assert [json.loads(hold.to_line()) for hold in plan.suppression_after.path_holds] == [recorded]
    assert (await world.service().execute(plan)).completed
    assert local_path_entries(world) == [recorded] and bucket_path_entries(world) == [recorded]


async def test_status_is_clean_with_the_path_entries_in_the_bucket(world: RemovalWorld) -> None:
    await remove_the_named_file(world)

    status = await CaselistStatusService(
        local=world.local, remote=world.bucket, suppression=world.suppression()
    ).status()

    assert bucket_path_entries(world) == [THE_PATH_ENTRY]
    assert status.in_sync, [entry for entry in status.snapshots if not entry.in_sync]


# ------------------------------------------------------------------------------------------------
# ac3 and the forbidden list: the removals that write no path entry
# ------------------------------------------------------------------------------------------------


async def test_only_named_plans_and_writes_no_path_entry(world: RemovalWorld) -> None:
    plan = await planned(world, only_named=True)
    assert plan.path_holds == ()

    assert (await world.service().execute(plan)).completed

    assert no_path_entry_anywhere(world)


async def test_a_team_removal_writes_no_path_entry(world: RemovalWorld) -> None:
    """`--team` removes four files whole and withdraws one. It holds no path: it finds a team's
    later files by path when it is run again."""
    plan = await planned(world, parse_team_selector(f"{CASELIST}/Alder Point/KR"))
    assert len(plan.of(Disposition.REMOVE)) == 4 and len(plan.of(Disposition.WITHDRAW)) == 1
    assert plan.path_holds == ()

    assert (await world.service().execute(plan)).completed

    assert no_path_entry_anywhere(world)


async def test_a_shared_file_named_by_source_and_skipped_writes_no_path_entry(world: RemovalWorld) -> None:
    """Two teams hold it and nothing is done to it, so nothing is held."""
    plan = await planned(world, SourceSelector(LATER_SHARED))
    assert [source.disposition for source in plan.sources] == [Disposition.SKIP_SHARED]

    assert plan.path_holds == ()


async def test_include_shared_removes_it_for_both_teams_and_holds_both_of_its_paths(
    world: RemovalWorld,
) -> None:
    plan = await planned(world, SourceSelector(LATER_SHARED), include_shared=True)
    assert [source.disposition for source in plan.sources] == [Disposition.REMOVE]

    # The shared revision is held at both teams' paths, first in the weekly of 2026-10-06.
    written = {entry.disclosure: json.loads(entry.to_line()) for entry in plan.path_holds}
    assert len(plan.path_holds) == 2
    assert written == {
        digest: {
            **THE_PATH_ENTRY,
            "disclosure": digest,
            "sha256": digest_of("later-also-at-another-path"),
            "after_snapshot": "2026-10-06",
        }
        for digest in (
            hashlib.sha256(f"testcl26/{REVISED_PATH}".encode()).hexdigest(),
            hashlib.sha256(f"testcl26/{OTHER_TEAM_PATH}".encode()).hexdigest(),
        )
    }


# ------------------------------------------------------------------------------------------------
# ac1: the refused upload is recorded under the removal's request
# ------------------------------------------------------------------------------------------------


async def test_the_import_counts_the_refused_upload_under_the_removals_request(
    world: RemovalWorld, tmp_path: Path
) -> None:
    await remove_the_named_file(world)

    weekly = await import_weekly(world, tmp_path, CASELIST, date(2026, 10, 8))
    complete = await import_complete_archive(world, tmp_path, date(2026, 10, 9))

    assert weekly.held_by_request == {REQUEST: 1} and weekly.held_at_removed_paths == 1
    assert complete.held_by_request == {REQUEST: 1}
    assert weekly.count(Classification.SUPPRESSED) == 1, "it is the one SUPPRESSED member, not a second"


async def test_a_file_the_list_stops_by_its_bytes_is_not_counted_as_held(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """The weekly of `2026-09-15` holds the later revision, which the removal put on the list itself."""
    await remove_the_named_file(world)

    report = await import_weekly(world, tmp_path, CASELIST, date(2026, 9, 15), allow_out_of_order=True)

    assert report.count(Classification.SUPPRESSED) == 1
    assert report.held_by_request == {}


async def test_the_import_appends_nothing_to_the_list_or_beside_it(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """Only `caselist remove` and `caselist unsuppress` write the takedown's records."""
    await remove_the_named_file(world)
    suppression = world.data_dir / "suppression"
    before = {path.name: path.read_bytes() for path in sorted(suppression.iterdir())}

    await import_weekly(world, tmp_path, CASELIST, date(2026, 10, 8))

    assert {path.name: path.read_bytes() for path in sorted(suppression.iterdir())} == before


async def test_if_classification_ever_let_a_held_upload_through_the_write_would_refuse_it(
    world: RemovalWorld, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The check is made again where the bytes are written, as the list's own is (`v1-e30-t07`)."""
    await remove_the_named_file(world)

    def everything_is_new(member: object, **_: object) -> Classification:
        return Classification.NEW

    monkeypatch.setattr(pipeline, "_classify", everything_is_new)

    with pytest.raises(SuppressedWriteRefused):
        await import_weekly(world, tmp_path, CASELIST, date(2026, 10, 8))

    assert not local_blob(world, UPLOADED_AFTER).exists()
    assert await world.repository.find_source(UPLOADED_AFTER) is None


def test_an_import_has_to_say_which_snapshot_it_is_importing() -> None:
    """A default would let an importer leave the date off and ask no hold about anything."""
    parameter = inspect.signature(SourceImportPipeline.run).parameters["snapshot"]

    assert parameter.default is inspect.Parameter.empty
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


# ------------------------------------------------------------------------------------------------
# The weekly pull's importer, and an importer that reads the list alone
# ------------------------------------------------------------------------------------------------


class _BucketNeedingALogin:
    async def get_file(self, key: ObjectKey, destination: Path) -> ObjectInfo:
        raise StoreCredentialsExpired(hint="aws sso login --profile debate-dev-evidence")


def _needing_a_login() -> EvidenceObjectStore:
    """The bucket as the weekly agent finds it once the SSO session has run out: no read answers."""
    return cast("EvidenceObjectStore", _BucketNeedingALogin())


async def test_the_pulls_importer_refuses_it_from_this_machines_copy_when_the_bucket_needs_a_login(
    world: RemovalWorld, tmp_path: Path
) -> None:
    await remove_the_named_file(world)
    local = local_suppression_list_file(world.data_dir)
    suppression = LocalFallbackSuppressionList(
        RecordedSuppressionList(
            local,
            ObjectStoreAppendOnlyRecord(_needing_a_login(), "manifests/_suppression/suppression-list.jsonl"),
        ),
        local=RecordedSuppressionList(local),
    )
    importer = CaselistImportService(
        caselists=world.repository, blobs=FsSnapshotStore(world.data_dir), suppression=suppression
    )

    report = await import_weekly(world, tmp_path, CASELIST, date(2026, 10, 8), importer=importer)

    assert report.held_by_request == {REQUEST: 1}
    assert not local_blob(world, UPLOADED_AFTER).exists()
    assert suppression.fallbacks >= 1


def the_list_alone(world: RemovalWorld) -> RecordedSuppressionList:
    """The list as a build from before this task reads it: its lines, and no record beside it."""
    listed = local_suppression_list_file(world.data_dir).path.read_text(encoding="utf-8").splitlines()
    return RecordedSuppressionList(InMemoryAppendOnlyRecord("the list as an older build reads it", listed))


async def an_older_build_imports_the_week(world: RemovalWorld, scratch: Path) -> None:
    importer = CaselistImportService(
        caselists=world.repository, blobs=FsSnapshotStore(world.data_dir), suppression=the_list_alone(world)
    )
    report = await import_weekly(world, scratch, CASELIST, date(2026, 10, 8), importer=importer)
    assert report.count(Classification.SUPPRESSED) == 0, "an older build applies no hold"


# ------------------------------------------------------------------------------------------------
# ac2: the plan lists a revision the inbox holds
# ------------------------------------------------------------------------------------------------


async def test_the_plan_lists_each_waiting_revision_as_a_later_upload_in_the_inbox(
    world: RemovalWorld, tmp_path: Path
) -> None:
    put_the_arriving_archives_in_the_inbox(world, tmp_path)

    plan = await planned(world)

    waiting = {
        version.sha256: (version.snapshots, version.inbox_snapshots, plan.later_upload_outcome(version))
        for version in plan.later_uploads
        if version.inbox_snapshots
    }
    assert waiting == {
        UPLOADED_AFTER: ((), ("2026-10-08",), LaterUploadOutcome.REMOVED),
        UPLOADED_AFTER_IN_A_COMPLETE_ARCHIVE: ((), ("full/2026-10-09",), LaterUploadOutcome.REMOVED),
        UPLOADED_AFTER_AT_TWO_PATHS: ((), ("2026-10-10",), LaterUploadOutcome.WITHDRAWN_FROM_THE_PATH),
        # The store holds it in the weekly of 2026-10-06, and the archive v1-e30-t11's tests left
        # waiting holds it again.
        LATER_SHARED: (("2026-10-06",), ("2026-10-13",), LaterUploadOutcome.WITHDRAWN_FROM_THE_PATH),
    }
    assert {version.path for version in plan.later_uploads} == {REVISED_PATH}
    assert plan.later_uploads_added == 6, "the three the store holds and the three waiting"
    for digest in (UPLOADED_AFTER, UPLOADED_AFTER_IN_A_COMPLETE_ARCHIVE, UPLOADED_AFTER_AT_TWO_PATHS):
        source = plan.source(digest)
        assert source is not None and source.inclusion is Inclusion.LATER_UPLOAD
        assert not source.local_blob and not source.disclosures, "the store never took it in"


async def test_only_named_lists_the_waiting_revisions_and_plans_nothing_for_them(
    world: RemovalWorld, tmp_path: Path
) -> None:
    put_the_arriving_archives_in_the_inbox(world, tmp_path)

    plan = await planned(world, only_named=True)

    assert {UPLOADED_AFTER, UPLOADED_AFTER_AT_TWO_PATHS} <= {one.sha256 for one in plan.later_uploads}
    assert [source.sha256 for source in plan.sources] == [NAMED]
    assert not [one for one in plan.inbox if one.name.endswith(("2026-10-08.zip", "2026-10-10.zip"))]


async def test_a_waiting_archive_of_another_caselist_holds_no_later_upload(
    world: RemovalWorld, tmp_path: Path
) -> None:
    other = build_arriving_weekly_zips(tmp_path / "arriving")[("testclb26", date(2026, 10, 8))]
    inbox = world.data_dir / "inbox"
    (inbox / other.name).write_bytes(other.read_bytes())

    plan = await planned(world)

    assert arriving_digest_of("uploaded-after-in-another-caselist") not in {
        version.sha256 for version in plan.later_uploads
    }
    assert other.name not in {one.name for one in plan.inbox}


async def test_an_archive_the_inbox_cannot_read_holds_no_later_upload_and_is_still_reported(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """One over the reader's ceilings and one that is not a zip: neither can be asked what is at the
    path, so neither adds a later upload, and the inbox section names both as it did before."""
    put_the_arriving_archives_in_the_inbox(world, tmp_path)
    (world.data_dir / "inbox" / f"{CASELIST}-weekly-2026-10-11.zip").write_bytes(b"not a zip")
    small = CaselistInbox(
        directory=world.data_dir / "inbox",
        state_dir=world.data_dir,
        archives=ZipArchiveRewriter(max_archive_bytes=64 * 1024 * 1024, max_unpacked_bytes=64 * 1024 * 1024),
        full_archives=ZipArchiveRewriter(max_archive_bytes=16, max_unpacked_bytes=16),
    )

    files = {file.name: file for file in read_inbox(small)}
    too_large, broken = files[f"{CASELIST}-all-2026-10-09.zip"], files[f"{CASELIST}-weekly-2026-10-11.zip"]
    assert (too_large.entries, too_large.unreadable) == (None, "over the size ceilings")
    assert broken.entries is None and broken.unreadable is not None
    assert files[f"{CASELIST}-weekly-2026-10-08.zip"].entries is not None

    plan = await planned(world)

    assert UPLOADED_AFTER in {version.sha256 for version in plan.later_uploads}
    unreadable = [one.name for one in plan.inbox if one.action is InboxAction.UNREADABLE]
    assert unreadable == [f"{CASELIST}-weekly-2026-10-11.zip"]


# ------------------------------------------------------------------------------------------------
# Running the same removal again covers what arrived since
# ------------------------------------------------------------------------------------------------


async def test_an_upload_this_build_refused_is_found_in_the_inbox_by_running_the_removal_again(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """The pull downloads the week into the inbox and imports it; the hold refuses the upload, and
    the archive, now imported, still holds it."""
    await remove_the_named_file(world)
    archive = build_arriving_weekly_zips(tmp_path / "arriving")[(CASELIST, date(2026, 10, 8))]
    in_the_inbox = world.data_dir / "inbox" / archive.name
    in_the_inbox.write_bytes(archive.read_bytes())
    await import_weekly(world, tmp_path, CASELIST, date(2026, 10, 8))

    plan = await planned(world)

    (found,) = [version for version in plan.later_uploads if version.sha256 == UPLOADED_AFTER]
    assert (found.snapshots, found.inbox_snapshots, found.of_sha256) == ((), ("2026-10-08",), NAMED)
    assert plan.later_upload_outcome(found) is LaterUploadOutcome.REMOVED
    assert [(one.name, one.action.value) for one in plan.inbox if one.name == archive.name] == [
        (archive.name, "delete")
    ]

    assert (await world.service().execute(plan)).completed

    assert not in_the_inbox.exists(), "an imported archive that holds a removed file is deleted"
    for entries in suppression_lines(world):
        assert (UPLOADED_AFTER, None, REQUEST) in {
            (entry.sha256, entry.disclosure, entry.request_id) for entry in entries
        }
    assert (await planned(world)).nothing_to_do


async def test_an_upload_an_older_build_imported_is_found_in_the_store_by_running_the_removal_again(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """`v1-e30-t11` could not find this: once the removed file's rows are gone, no manifest says
    where it was. The path entry does."""
    await remove_the_named_file(world)
    await an_older_build_imports_the_week(world, tmp_path)
    assert local_blob(world, UPLOADED_AFTER).read_bytes() == ARRIVING_BODIES["uploaded-after-the-removal"]
    key = manifest_key(CASELIST, date(2026, 10, 8))
    assert held_at(manifest_rows(world, key), REVISED_PATH) == {UPLOADED_AFTER}

    plan = await planned(world)

    (found,) = [version for version in plan.later_uploads if version.sha256 == UPLOADED_AFTER]
    assert (found.snapshots, found.inbox_snapshots, found.of_sha256) == (("2026-10-08",), (), NAMED)
    assert (await world.service().execute(plan)).completed

    assert not local_blob(world, UPLOADED_AFTER).exists()
    assert await world.repository.find_source(UPLOADED_AFTER) is None
    assert held_at(manifest_rows(world, key), REVISED_PATH) == set()
    for entries in suppression_lines(world):
        assert (UPLOADED_AFTER, None, REQUEST) in {
            (entry.sha256, entry.disclosure, entry.request_id) for entry in entries
        }


async def test_what_an_older_build_published_is_taken_out_of_the_bucket_too(
    world: RemovalWorld, tmp_path: Path
) -> None:
    from debate_core.application.caselist.publish_service import CaselistPublishService

    await remove_the_named_file(world)
    await an_older_build_imports_the_week(world, tmp_path)
    publisher = CaselistPublishService(
        local=world.local, remote=world.bucket, suppression=the_list_alone(world)
    )
    assert (await publisher.execute(await publisher.plan(CASELIST))).succeeded
    assert len(versions_of(world, raw_key(UPLOADED_AFTER))) == 1

    assert (await world.service().execute(await planned(world))).completed

    assert versions_of(world, raw_key(UPLOADED_AFTER)) == []
    for rows in rows_on_both_sides(world, "2026-10-08"):
        assert held_at(rows, REVISED_PATH) == set()


async def test_running_it_again_with_nothing_new_finds_nothing(world: RemovalWorld) -> None:
    await remove_the_named_file(world)

    plan = await planned(world)

    assert plan.later_uploads == () and plan.nothing_to_do


# ------------------------------------------------------------------------------------------------
# unsuppress releases the hold
# ------------------------------------------------------------------------------------------------


async def test_unsuppressing_the_removed_file_releases_its_path(world: RemovalWorld, tmp_path: Path) -> None:
    await remove_the_named_file(world)
    service = world.service()

    plan = await service.plan_unsuppress(NAMED, reason=ReasonCode.REMOVED_IN_ERROR, request_id=REQUEST)
    assert plan.path_holds_released == 1
    await service.unsuppress(plan)

    report = await import_weekly(
        world, tmp_path, CASELIST, date(2026, 10, 8), importer=offline_importer(world)
    )
    assert report.count(Classification.SUPPRESSED) == 0 and report.held_by_request == {}
    assert local_blob(world, UPLOADED_AFTER).read_bytes() == ARRIVING_BODIES["uploaded-after-the-removal"]
    assert local_path_entries(world) == [THE_PATH_ENTRY], "nothing is appended to release a hold"


async def test_unsuppressing_a_later_upload_releases_no_path(world: RemovalWorld, tmp_path: Path) -> None:
    """The hold follows the file the request named. Letting one later upload back in lifts nothing else."""
    await remove_the_named_file(world)
    service = world.service()

    plan = await service.plan_unsuppress(
        LATER_REVISION, reason=ReasonCode.REMOVED_IN_ERROR, request_id=REQUEST
    )
    assert plan.path_holds_released == 0
    await service.unsuppress(plan)

    report = await import_weekly(world, tmp_path, CASELIST, date(2026, 10, 8))
    assert report.held_by_request == {REQUEST: 1}
