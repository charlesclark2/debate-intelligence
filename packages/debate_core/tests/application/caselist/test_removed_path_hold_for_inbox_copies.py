"""A camp file already in the inbox is held if its path was removed (`v1-e34-t14`).

`v1-e34-t07` holds back a new OpenEv id at the upstream path of a camp file that was removed
(`same_path_as_a_removed_file`): a removal covers a camp's later upload of the same file (PM
decision, `v1-e34-t07` review). Before this task the hold was asked only of a file the run would
fetch. A new id with no delivery entry whose copy was already in the inbox returned before the hold,
so it was imported: the session report keeps that run. The copy can be there only if it was
downloaded before this machine knew of the removal, which is exactly when the hold matters.

Now the hold is asked first, for every listed id the manifest and the delivery record do not know.
An inbox copy changes only whether a download is needed, never whether the file may be imported.
A held copy is left where it is: not imported, not deleted, not renamed. Retention keeps it, since
no manifest came from its bytes, and the next run after `caselist unsuppress` imports it from the
inbox without a download.

Every removal is the real one, through `CaselistRemovalService`, or an entry in the bucket's copy of
the list, which is all a removal made on another machine leaves this one. The camp files are the
synthetic ones from `tests/fixtures/openev/`. Every expected decision, count and name is worked out
by hand from what each test sets up (working agreement 6).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from tests.fixtures.openev.build_synthetic_openev import DOCUMENT_BODIES

from debate_core.application.caselist.import_service import CaselistImportService
from debate_core.application.caselist.openev_import_service import OpenEvImportService
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.status_service import CaselistStatusService
from debate_core.application.caselist.suppression import LocalFallbackSuppressionList
from debate_core.application.caselist_sync import (
    OPENEV_DELIVERIES_FILENAME,
    CaselistSyncService,
    RunSummary,
    SelectionDecision,
    StageOutcome,
    SyncStage,
)
from debate_core.application.ports.caselist_source import OpenEvFile, openev_inbox_name
from debate_core.application.sync_runs import record_for_summary
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsSnapshotStore
from debate_core.integrations.local.archive_reader import read_archive

from .conftest import RemovalWorld
from .test_sync_fetches_revised_camp_files import removed_on_another_machine
from .test_sync_skips_suppressed_downloads import (
    CASELIST,
    ESTUARY,
    ESTUARY_SHA256,
    LIMITS,
    PULLED_AT,
    YEAR,
    FakeOpenEvSource,
    UnreadableSuppressionList,
    build_sync,
    decisions,
    inbox_copy,
    local_only,
    pull,
    release_member_paths,
    remove_source,
    select_reason,
    unsuppress,
)

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

ESTUARY_BODY = DOCUMENT_BODIES["estuary-solvency"]
REVISED_BODY = DOCUMENT_BODIES["canal-counterplan-revised"]
REVISED_SHA256 = hashlib.sha256(REVISED_BODY).hexdigest()

#: The same camp file, uploaded again under a new id at the same path: OpenEv's only way to change one.
REVISION = ESTUARY.model_copy(update={"openev_id": 640})

#: How a summary names 640's copy: its id, and the first twelve hex digits of its bytes' SHA-256.
REVISION_LABEL = f"openev-640 (sha256 {REVISED_SHA256[:12]})"

#: The words of the camp file's path, title and inbox name, none of which a summary may carry.
TITLE_WORDS = ("Tamarack", "TSF", "Estuary", "Solvency", "Advocate", openev_inbox_name(REVISION))

HELD_SENTENCE = "1 held back as a new id at a removed file's path"


@pytest.fixture
def world(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> RemovalWorld:
    """As in `test_sync_skips_suppressed_downloads.py`: a removal never reaches the pull's inbox.

    The pull's inbox is staged by hand here, as a removal made on another machine, or one made here
    before 640 was listed, leaves it.
    """
    return RemovalWorld(
        data_dir=tmp_path / "evidence",
        bucket_name=evidence_bucket,
        client=s3_client,
        removal_inbox=tmp_path / "an-inbox-on-another-machine",
    )


async def pulled_then_uploaded_again(world: RemovalWorld) -> FakeOpenEvSource:
    """512 pulled and imported by the sync, then deleted upstream and uploaded again as 640.

    512's own copy is taken out of the inbox, so that the only camp download there is the one each
    test puts there.
    """
    source = FakeOpenEvSource([(ESTUARY, ESTUARY_BODY)])
    await pull(world, source)
    inbox_copy(world, ESTUARY).unlink()
    source.files = [(REVISION, REVISED_BODY)]
    return source


def already_in_inbox(world: RemovalWorld, file: OpenEvFile, body: bytes) -> Path:
    """A copy of `file` downloaded by an earlier run whose import never ran: no delivery entry for it."""
    path = inbox_copy(world, file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return path


def written_selection(summary: RunSummary) -> dict[str, object]:
    """The summary JSON's one OpenEv selection."""
    (written,) = cast("list[dict[str, object]]", summary.as_json()["openev_selections"])
    return written


def assert_names_no_camp_file(summary: RunSummary) -> None:
    """The summary and what `caselist runs` keeps of it name the camp file by id and digest alone."""
    written = json.dumps(summary.as_json())
    record = record_for_summary(summary, environment="dev", mode="run").model_dump_json()
    for word in TITLE_WORDS:
        assert word not in written, word
        assert word not in record, word


def assert_held(world: RemovalWorld, summary: RunSummary, source: FakeOpenEvSource, copy: Path) -> None:
    """640 held back, not fetched, not imported, its copy where it was with the bytes it had."""
    assert source.openev_fetches == [ESTUARY.openev_id], "the held id was fetched"
    assert (summary.snapshots_imported, summary.blobs_stored) == ((), 0), "the held copy was imported"
    assert decisions(summary) == {640: SelectionDecision.SAME_PATH_AS_A_REMOVED_FILE}
    assert not FsSnapshotStore(world.data_dir).path_for(REVISED_SHA256).exists()
    assert copy.read_bytes() == REVISED_BODY, "the held copy was deleted, renamed or changed"
    (selection,) = summary.openev
    assert selection.revision_of is None
    assert selection.note is not None and "the removal covers it" in selection.note
    assert f"{HELD_SENTENCE} ({REVISION_LABEL})" in select_reason(summary)
    assert written_selection(summary) == {
        "openev_id": 640,
        "inbox_file": f"sha256 {REVISED_SHA256[:12]}",
        "year": YEAR,
        "event": "POLICY",
        "decision": "same_path_as_a_removed_file",
        "note": selection.note,
        "revision_of": None,
    }
    assert_names_no_camp_file(summary)


# ------------------------------------------------------------------------------------------------
# A new id at a removed file's path, its copy already in the inbox, is held (ac1)
# ------------------------------------------------------------------------------------------------


async def test_a_new_id_at_the_path_of_a_file_removed_here_is_held_with_its_copy_already_in_the_inbox(
    world: RemovalWorld,
) -> None:
    """The removal took 512's row out, so the delivery record's entry for 512 at that path says so.

    Before this task 640's copy was imported from the inbox as `already_in_inbox`, and the revised
    bytes stored, undoing the takedown: the session report keeps that run.
    """
    source = await pulled_then_uploaded_again(world)
    await remove_source(world, ESTUARY_SHA256)
    copy = already_in_inbox(world, REVISION, REVISED_BODY)

    summary = await pull(world, source)

    assert_held(world, summary, source, copy)


@pytest.mark.parametrize("record_kept", [True, False], ids=["delivery-record-kept", "delivery-record-lost"])
async def test_a_revision_of_a_file_removed_on_another_machine_is_held_with_its_copy_already_in_the_inbox(
    world: RemovalWorld, record_kept: bool
) -> None:
    """The removal is only in the bucket's copy of the list, so 512's row is still here.

    With the delivery record lost, only that row can say which bytes 512 had: the hold asks the list
    about the old row's own bytes, as `v1-e34-t08` made it, for an inbox copy too.
    """
    source = await pulled_then_uploaded_again(world)
    await removed_on_another_machine(world, ESTUARY_SHA256)
    if not record_kept:
        (world.data_dir / OPENEV_DELIVERIES_FILENAME).unlink()
    copy = already_in_inbox(world, REVISION, REVISED_BODY)

    summary = await pull(world, source)

    assert_held(world, summary, source, copy)
    assert release_member_paths(world) == ["openev-512-TSF-Estuary_Solvency_Advocate.docx"]


@pytest.mark.parametrize("removed_where", ["here", "on-another-machine"])
async def test_after_unsuppress_the_held_copy_is_imported_from_the_inbox_without_a_download(
    world: RemovalWorld, removed_where: str
) -> None:
    """The next run after `caselist unsuppress` imports 640 from where it was held, fetching nothing.

    Removed here, 512's row is gone, so 640 is a new id; removed on another machine, 512's row is
    still here and 512 is listed nowhere, so 640 is its revision (`v1-e34-t08`). Either way the
    summary names it by id and digest alone (`v1-e34-t12`).
    """
    source = await pulled_then_uploaded_again(world)
    if removed_where == "here":
        await remove_source(world, ESTUARY_SHA256)
    else:
        await removed_on_another_machine(world, ESTUARY_SHA256)
    copy = already_in_inbox(world, REVISION, REVISED_BODY)
    held = await pull(world, source)
    assert_held(world, held, source, copy)

    await unsuppress(world, ESTUARY_SHA256)
    released = await pull(world, source)

    assert source.openev_fetches == [ESTUARY.openev_id], "the released copy was downloaded again"
    assert decisions(released) == {640: SelectionDecision.ALREADY_IN_INBOX}
    assert released.blobs_stored == 1 and released.snapshots_imported == ("openev 2026-policy",)
    assert FsSnapshotStore(world.data_dir).path_for(REVISED_SHA256).exists()
    (selection,) = released.openev
    assert selection.revision_of == (None if removed_where == "here" else ESTUARY.openev_id)
    assert selection.label == REVISION_LABEL
    written = written_selection(released)
    assert written["openev_id"] == 640
    assert written["inbox_file"] == f"sha256 {REVISED_SHA256[:12]}"
    assert HELD_SENTENCE not in select_reason(released)
    assert_names_no_camp_file(released)

    settled = await pull(world, source)

    assert decisions(settled) == {640: SelectionDecision.ALREADY_IMPORTED}
    assert source.openev_fetches == [ESTUARY.openev_id]


async def test_with_the_list_unreadable_an_inbox_copy_the_hold_must_ask_about_waits(
    world: RemovalWorld,
) -> None:
    """Nothing was removed, but 512's entry is at 640's path, so the hold has a question for the
    list, and the list cannot be read. 640's copy waits as `suppression_list_unreadable`, as a
    download of it would: it is not imported on a guess.

    The importer here reads a list it can read, and would store 640: only the wait keeps it out.
    """
    source = await pulled_then_uploaded_again(world)
    copy = already_in_inbox(world, REVISION, REVISED_BODY)

    summary = await build_sync(world, source, skip_reads=UnreadableSuppressionList()).run([CASELIST])

    assert decisions(summary) == {640: SelectionDecision.SUPPRESSION_LIST_UNREADABLE}
    assert source.openev_fetches == [ESTUARY.openev_id]
    assert summary.snapshots_imported == () and summary.blobs_stored == 0
    assert copy.read_bytes() == REVISED_BODY
    assert "1 not fetched because the suppression list could not be read" in select_reason(summary)


# ------------------------------------------------------------------------------------------------
# An inbox copy at a path nothing removed is imported as before (ac2)
# ------------------------------------------------------------------------------------------------


async def test_an_inbox_copy_of_a_new_file_at_a_path_nothing_removed_is_imported_as_before(
    world: RemovalWorld,
) -> None:
    """777 has never been seen and nothing is at its path: imported from the inbox, no download."""
    orchard = OpenEvFile(
        openev_id=777, path=f"openev/{YEAR}/Brightwater/Orchard Kritik.docx", year=YEAR, tags=("policy",)
    )
    source = FakeOpenEvSource([(orchard, DOCUMENT_BODIES["orchard-kritik"])])
    already_in_inbox(world, orchard, DOCUMENT_BODIES["orchard-kritik"])

    summary = await pull(world, source)

    assert source.openev_fetches == []
    assert decisions(summary) == {777: SelectionDecision.ALREADY_IN_INBOX}
    assert summary.blobs_stored == 1


async def test_an_inbox_copy_of_a_revision_of_a_file_nothing_removed_is_imported_as_before(
    world: RemovalWorld,
) -> None:
    """512's entry and row are at 640's path, and the list stops neither: the hold asks and lets it
    through, and 640 is imported from the inbox as 512's revision, with no download."""
    source = await pulled_then_uploaded_again(world)
    already_in_inbox(world, REVISION, REVISED_BODY)

    summary = await pull(world, source)

    assert source.openev_fetches == [ESTUARY.openev_id]
    assert decisions(summary) == {640: SelectionDecision.ALREADY_IN_INBOX}
    assert summary.openev[0].revision_of == ESTUARY.openev_id
    assert summary.blobs_stored == 1
    assert HELD_SENTENCE not in select_reason(summary)


# ------------------------------------------------------------------------------------------------
# Retention keeps a held copy: removal and retention own deletion, the hold deletes nothing
# ------------------------------------------------------------------------------------------------


def build_sync_with_retention(world: RemovalWorld, source: FakeOpenEvSource) -> CaselistSyncService:
    """:func:`build_sync` with the status comparison wired in, so the retention stage runs."""
    shared = LocalFallbackSuppressionList(world.suppression(), local=local_only(world))
    repository = world.repository
    blobs = FsSnapshotStore(world.data_dir)
    return CaselistSyncService(
        source=source,
        archive_importer=CaselistImportService(caselists=repository, blobs=blobs, suppression=shared),
        openev_importer=OpenEvImportService(caselists=repository, blobs=blobs, suppression=shared),
        local=world.local,
        read_archive=lambda path: read_archive(path, **LIMITS),
        event_for_caselist=lambda slug: Event.LD,
        inbox=world.data_dir / "inbox",
        state_dir=world.data_dir,
        suppression=shared,
        publisher=CaselistPublishService(
            local=world.local, remote=world.bucket, suppression=world.suppression()
        ),
        status=CaselistStatusService(local=world.local, remote=world.bucket, suppression=world.suppression()),
        clock=lambda: PULLED_AT,
    )


async def test_retention_keeps_a_held_copy_as_not_imported(world: RemovalWorld) -> None:
    """No manifest came from 640's bytes and the record has no entry for it, so retention keeps it,
    named by its digest, and the run after that holds it again rather than fetching it."""
    source = await pulled_then_uploaded_again(world)
    await remove_source(world, ESTUARY_SHA256)
    copy = already_in_inbox(world, REVISION, REVISED_BODY)

    summary = await build_sync_with_retention(world, source).run([CASELIST])

    assert summary.succeeded, summary.stages
    assert_held(world, summary, source, copy)
    retention = summary.stage(SyncStage.RETENTION)
    assert retention is not None and retention.outcome is StageOutcome.COMPLETED
    written = cast("dict[str, object]", summary.as_json()["inbox_retention"])
    assert written["removed"] == []
    assert written["kept"] == [
        {
            "name": f"sha256 {REVISED_SHA256[:12]}",
            "kind": "camp_download",
            "bytes": len(REVISED_BODY),
            "reason": "not_imported",
        }
    ]

    again = await build_sync_with_retention(world, source).run([CASELIST])

    assert_held(world, again, source, copy)
