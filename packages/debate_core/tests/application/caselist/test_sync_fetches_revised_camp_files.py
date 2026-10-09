"""A camp file uploaded again upstream is fetched, and nothing the earlier rules held is (`v1-e34-t08`).

OpenEv changes a camp file only one way: an admin deletes it and someone uploads it again, which
gives it a new id, normally at the same path (`v1-e34-t07`'s reading of upstream at `fb2903e`).
`v1-e34-t06` matched "already imported" by path, so the old row held the new id and a revised camp
file was never fetched. A listed id the sync has not seen is now a **revision** when a row of the
release manifest at the same path names its own OpenEv id (`openev-<id>-…`, the name the sync gives
a download) and that id is no longer listed anywhere upstream. Everything else is as before:

* a row naming no id, a hand import, still holds the file at its path (`v1-e34-t06`);
* a row whose id is still listed is still that id's;
* a new id at the path of a removed file is still held back, and the hold is decided before the
  revision rule (`v1-e34-t07`, PM decision), including a removal this machine only knows from the
  bucket's copy of the list, whose old row is still here.

Also here, because it is the same `_judge_unrecorded` path (`v1-e30-t09` Follow-up 4): a camp release
holding only junk is imported once, and not again.

Every removal is the real one, through `CaselistRemovalService`, or an entry in the bucket's copy of
the list, which is all a removal made on another machine leaves this one. The camp files are the
synthetic ones from `tests/fixtures/openev/`. Every expected decision is worked out by hand from what
each test lists.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.openev.build_synthetic_openev import DOCUMENT_BODIES, build_download_zips

from debate_core.application.caselist.manifest import read_manifest_lines, write_manifest_lines
from debate_core.application.caselist.openev_import_service import OpenEvImportService
from debate_core.application.caselist.openev_manifest import openev_manifest_key
from debate_core.application.caselist.suppression import (
    SUPPRESSION_LIST_KEY,
    ObjectStoreAppendOnlyRecord,
    RecordedSuppressionList,
)
from debate_core.application.caselist_sync import OPENEV_DELIVERIES_FILENAME, SelectionDecision
from debate_core.application.ports.caselist_source import OpenEvFile
from debate_core.application.sync_runs import record_for_summary
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsSnapshotStore
from debate_core.integrations.local.archive_reader import archive_digest, read_archive
from debate_core.testing.fakes import empty_suppression_list

from .conftest import RemovalWorld
from .test_sync_skips_suppressed_downloads import (
    CASELIST,
    ESTUARY,
    ESTUARY_SHA256,
    LIMITS,
    YEAR,
    FakeOpenEvSource,
    UnreadableSuppressionList,
    build_sync,
    decisions,
    inbox_copy,
    pull,
    release_member_paths,
    remove_source,
    select_reason,
    suppression_entry,
    unsuppress,
)

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

ESTUARY_BODY = DOCUMENT_BODIES["estuary-solvency"]
REVISED_BODY = DOCUMENT_BODIES["canal-counterplan-revised"]

#: The same camp file, uploaded again: OpenEv's only way to change one.
REVISION = ESTUARY.model_copy(update={"openev_id": 640})

#: How the sync names 512's download, and so the path of its row in the release manifest.
OLD_ROW = "openev-512-TSF-Estuary_Solvency_Advocate.docx"

#: The words of the camp file's path and title, none of which a summary may carry.
TITLE_WORDS = ("Tamarack", "TSF", "Estuary", "Solvency", "Advocate")


@pytest.fixture
def world(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> RemovalWorld:
    """As in `test_sync_skips_suppressed_downloads.py`: a removal never reaches the pull's inbox."""
    return RemovalWorld(
        data_dir=tmp_path / "evidence",
        bucket_name=evidence_bucket,
        client=s3_client,
        removal_inbox=tmp_path / "an-inbox-on-another-machine",
    )


async def pulled_then_uploaded_again(world: RemovalWorld) -> FakeOpenEvSource:
    """512 pulled and imported by the sync, then deleted upstream and uploaded again as 640."""
    source = FakeOpenEvSource([(ESTUARY, ESTUARY_BODY)])
    await pull(world, source)
    assert release_member_paths(world) == [OLD_ROW]
    source.files = [(REVISION, REVISED_BODY)]
    return source


async def removed_on_another_machine(world: RemovalWorld, sha: str) -> None:
    """What a removal made elsewhere leaves this machine: an entry in the bucket's copy of the list.

    Its manifest rows, its delivery record and this machine's copy of the list are all as they were.
    """
    await RecordedSuppressionList(ObjectStoreAppendOnlyRecord(world.bucket, SUPPRESSION_LIST_KEY)).append(
        [suppression_entry(sha)]
    )


async def import_by_hand(world: RemovalWorld, download: Path) -> None:
    """`caselist import-openev <download> --year 2026 --event policy`, into the world's store."""
    service = OpenEvImportService(
        caselists=world.repository,
        blobs=FsSnapshotStore(world.data_dir),
        suppression=empty_suppression_list(),
    )
    manifest = world.local.object_path_for(openev_manifest_key(YEAR, Event.POLICY))  # type: ignore[misc]
    report = await service.import_release(
        read_archive(download, **LIMITS),
        year=YEAR,
        event=Event.POLICY,
        imported_on=date(2026, 9, 10),
        archive_sha256=archive_digest(download),
        recorded_manifest=read_manifest_lines(manifest),
    )
    write_manifest_lines(report.manifest_lines, manifest)


# ------------------------------------------------------------------------------------------------
# A revision is fetched, and named by ids alone (ac1)
# ------------------------------------------------------------------------------------------------


async def test_a_revision_is_named_by_openev_ids_alone_in_the_summary_and_the_run_log(
    world: RemovalWorld,
) -> None:
    """Old to new, by id. The selection's `inbox_name` already carries a title (`v1-e34-t12` removes
    it); nothing this task adds may carry one."""
    source = await pulled_then_uploaded_again(world)

    summary = await pull(world, source)

    reason = select_reason(summary)
    assert "1 taken as a revision of an id no longer listed (openev-512 -> openev-640)" in reason
    (written,) = summary.as_json()["openev_selections"]  # type: ignore[misc]
    assert written["revision_of"] == 512 and written["note"] is None  # type: ignore[index]
    record = record_for_summary(summary, environment="dev", mode="run").model_dump_json()
    assert "openev-512 -> openev-640" in record
    for word in TITLE_WORDS:
        assert word not in reason and word not in record


async def test_a_revision_leaves_the_old_versions_row_and_delivery_entry_as_they_were(
    world: RemovalWorld,
) -> None:
    """Nothing about 512 is deleted or rewritten: its row, its blob and its delivery entry stay."""
    source = await pulled_then_uploaded_again(world)
    manifest = world.local.object_path_for(openev_manifest_key(YEAR, Event.POLICY))  # type: ignore[misc]
    old_row = next(line for line in read_manifest_lines(manifest) if OLD_ROW in line)
    record = world.data_dir / OPENEV_DELIVERIES_FILENAME
    old_entry = json.loads(record.read_text(encoding="utf-8"))["deliveries"]["512"]

    await pull(world, source)

    assert old_row in read_manifest_lines(manifest)
    assert FsSnapshotStore(world.data_dir).path_for(ESTUARY_SHA256).exists()
    deliveries = json.loads(record.read_text(encoding="utf-8"))["deliveries"]
    assert deliveries["512"] == old_entry
    assert sorted(deliveries) == ["512", "640"]


# ------------------------------------------------------------------------------------------------
# What v1-e34-t06 protected still holds (ac2)
# ------------------------------------------------------------------------------------------------


async def test_revision_rule_leaves_a_hand_imported_file_still_listed_under_its_id_held(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """`Tamarack/TSF-Estuary Solvency Advocate.docx`, imported by hand, is 512, still listed."""
    await import_by_hand(world, build_download_zips(tmp_path / "camp")["openev-2026-policy-addendum"])
    source = FakeOpenEvSource([(ESTUARY, ESTUARY_BODY)])

    summary = await pull(world, source)

    assert source.openev_fetches == [], "a camp file imported by hand was fetched again"
    assert decisions(summary) == {512: SelectionDecision.ALREADY_IMPORTED}
    assert summary.openev[0].revision_of is None


async def test_revision_rule_needs_a_row_naming_its_own_id_and_a_hand_import_names_none(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """The hand-imported row names no OpenEv id, so nothing says which upload it came from.

    640 at its path may be the very file the coach imported by hand, so the row holds it as before
    (PM decision): nothing is re-downloaded on a guess.
    """
    await import_by_hand(world, build_download_zips(tmp_path / "camp")["openev-2026-policy-addendum"])
    source = FakeOpenEvSource([(REVISION, REVISED_BODY)])

    summary = await pull(world, source)

    assert source.openev_fetches == []
    assert decisions(summary) == {640: SelectionDecision.ALREADY_IMPORTED}


async def test_revision_rule_needs_the_old_id_gone_from_the_whole_listing_not_only_its_release(
    world: RemovalWorld,
) -> None:
    """512 still listed, its tags no longer naming an event, so it is in no release this run reads.

    The release's own listing no longer holds 512, but upstream does: 512 was not deleted, so 640 is
    not its revision, and today's behaviour stands (PM decision): held by the old row, not fetched.
    """
    source = await pulled_then_uploaded_again(world)
    source.files = [(ESTUARY.model_copy(update={"tags": ()}), ESTUARY_BODY), (REVISION, REVISED_BODY)]

    summary = await pull(world, source)

    assert source.openev_fetches == [512]
    assert decisions(summary) == {
        512: SelectionDecision.NO_EVENT_CONFIGURED,
        640: SelectionDecision.ALREADY_IMPORTED,
    }


# ------------------------------------------------------------------------------------------------
# The removed-path hold survives, and comes first (ac3)
# ------------------------------------------------------------------------------------------------


async def test_a_revision_of_a_file_removed_on_another_machine_is_held_back_as_removed(
    world: RemovalWorld,
) -> None:
    """The removal is only in the bucket's copy of the list, so 512's row is still in this machine's
    manifest, and it would make 640 a revision. The removed-path hold is decided first, and wins."""
    source = await pulled_then_uploaded_again(world)
    await removed_on_another_machine(world, ESTUARY_SHA256)

    summary = await pull(world, source)

    assert source.openev_fetches == [512], "a new id at the path of a removed file was fetched"
    assert decisions(summary) == {640: SelectionDecision.SAME_PATH_AS_A_REMOVED_FILE}
    assert summary.openev[0].revision_of is None
    assert "1 held back as a new id at a removed file's path (openev-640)" in select_reason(summary)


async def test_a_revision_of_a_removed_file_the_delivery_record_forgot_is_held_back_by_its_old_row(
    world: RemovalWorld,
) -> None:
    """With no delivery entry for 512 (lost, or imported before `v1-e34-t07`), the record cannot say
    which path 512 had. Its row can: the row's own digest is on the list, so 640 is held back."""
    source = await pulled_then_uploaded_again(world)
    await removed_on_another_machine(world, ESTUARY_SHA256)
    (world.data_dir / OPENEV_DELIVERIES_FILENAME).unlink()

    summary = await pull(world, source)

    assert source.openev_fetches == [512], "a new id at the path of a removed file was fetched"
    assert decisions(summary) == {640: SelectionDecision.SAME_PATH_AS_A_REMOVED_FILE}


async def test_after_unsuppress_a_revision_of_a_file_removed_on_another_machine_is_fetched(
    world: RemovalWorld,
) -> None:
    source = await pulled_then_uploaded_again(world)
    await removed_on_another_machine(world, ESTUARY_SHA256)
    held = await pull(world, source)
    assert decisions(held) == {640: SelectionDecision.SAME_PATH_AS_A_REMOVED_FILE}

    await unsuppress(world, ESTUARY_SHA256)
    fetched = await pull(world, source)

    assert source.openev_fetches == [512, 640]
    assert decisions(fetched) == {640: SelectionDecision.DOWNLOAD}
    assert fetched.openev[0].revision_of == 512
    assert fetched.blobs_stored == 1


async def test_after_unsuppress_a_new_id_at_the_path_of_a_file_removed_here_is_fetched(
    world: RemovalWorld,
) -> None:
    """A removal on this machine takes 512's row out, so 640 is no revision, only a new id at the
    path of a removed file: held back, and once the removal is lifted, fetched like any new file."""
    source = await pulled_then_uploaded_again(world)
    await remove_source(world, ESTUARY_SHA256)
    inbox_copy(world, ESTUARY).unlink()
    held = await pull(world, source)
    assert decisions(held) == {640: SelectionDecision.SAME_PATH_AS_A_REMOVED_FILE}

    await unsuppress(world, ESTUARY_SHA256)
    fetched = await pull(world, source)

    assert source.openev_fetches == [512, 640]
    assert decisions(fetched) == {640: SelectionDecision.DOWNLOAD}
    assert fetched.openev[0].revision_of is None
    assert fetched.blobs_stored == 1


async def test_with_the_list_unreadable_a_revision_waits_rather_than_being_removed_or_fetched_on_a_guess(
    world: RemovalWorld,
) -> None:
    """Whether 512 was removed on another machine cannot be known, so 640 is not fetched yet."""
    source = await pulled_then_uploaded_again(world)

    plan = await build_sync(world, source, skip_reads=UnreadableSuppressionList()).plan([CASELIST])

    assert {one.openev_id: one.decision for one in plan.openev} == {
        640: SelectionDecision.SUPPRESSION_LIST_UNREADABLE
    }


# ------------------------------------------------------------------------------------------------
# A camp release holding only junk is handled once (ac5)
# ------------------------------------------------------------------------------------------------


#: A camp release whose every member the importer skips: no camp file at all.
JUNK_RELEASE = OpenEvFile(
    openev_id=950,
    path=f"openev/{YEAR}/Quillfeather/QDI Empty Release.zip",
    filename="QDI Empty Release.zip",
    year=YEAR,
    tags=("policy",),
)


def junk_release_zip() -> bytes:
    """`.DS_Store` and an AppleDouble file, byte-identically every time."""
    members = (
        ("QDI Empty Release/.DS_Store", b"\x00\x05\x16\x07 invented macOS metadata"),
        ("__MACOSX/QDI Empty Release/._QDI - Harbor Tariffs Aff.docx", b"\x00\x05\x16\x07 invented"),
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, body in members:
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, body)
    return buffer.getvalue()


@pytest.mark.parametrize("inbox_kept", [False, True], ids=["inbox-copy-gone", "inbox-copy-kept"])
async def test_a_camp_release_of_junk_alone_is_imported_once_and_not_again(
    world: RemovalWorld, inbox_kept: bool
) -> None:
    """Its delivery entry names no member, which used to mean "never imported": with its copy kept
    it was imported again on every run, and with the copy gone it was downloaded again."""
    source = FakeOpenEvSource([(JUNK_RELEASE, junk_release_zip())])
    first = await pull(world, source)
    assert decisions(first) == {950: SelectionDecision.DOWNLOAD}
    assert first.files_skipped == 2 and first.files_imported == 0
    if not inbox_kept:
        inbox_copy(world, JUNK_RELEASE).unlink()

    again = await pull(world, source)

    assert source.openev_fetches == [950], "the junk-only release was downloaded again"
    assert again.snapshots_imported == (), "the junk-only release was imported again"
    assert decisions(again) == {950: SelectionDecision.ALREADY_IMPORTED}
    assert again.nothing_new
