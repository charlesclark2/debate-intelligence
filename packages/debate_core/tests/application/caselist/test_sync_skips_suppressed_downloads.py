"""The weekly pull does not download a camp file it has been told to remove (`v1-e34-t07`).

Before this task, a camp file removed under the removal procedure was fetched again by every pull
whose inbox no longer held it, and imported again from the inbox by every pull whose inbox did; the
importer refused it each time. The removal held, and a download from the maintainer's budget was
spent for nothing, every week. The session report keeps both failing runs.

Every removal here is the real one: `CaselistRemovalService`, the service `caselist remove` runs,
against moto, so the manifest a pull reads afterwards is the one a removal leaves. The pull is built
the way the composition root builds it when there is a bucket — the importers and the skip reading
one list, the union of this machine's copy and the bucket's — except where a test says otherwise.

The camp files are the synthetic ones from `tests/fixtures/openev/` (no real camp content,
`docs/policies/caselist-data-use.md`). Every expected count is worked out by hand from the
documents each test lists, not read off a run.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import zipfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.openev.build_synthetic_openev import DOCUMENT_BODIES

from debate_core.application.caselist.import_service import CaselistImportService
from debate_core.application.caselist.manifest import read_manifest_lines
from debate_core.application.caselist.openev_import_service import OpenEvImportService
from debate_core.application.caselist.openev_manifest import openev_manifest_key
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.removal_plan import SourceSelector
from debate_core.application.caselist.suppression import (
    SUPPRESSION_LIST_KEY,
    LocalFallbackSuppressionList,
    ObjectStoreAppendOnlyRecord,
    RecordedSuppressionList,
)
from debate_core.application.caselist_sync import (
    OPENEV_DELIVERIES_FILENAME,
    CaselistSyncService,
    OpenEvDeliveries,
    OpenEvDelivery,
    RunSummary,
    SelectionDecision,
    SyncStage,
)
from debate_core.application.errors import StoreAccessDenied, StoreCredentialsExpired
from debate_core.application.ports.caselist_source import (
    ArchiveListing,
    CaselistInfo,
    DownloadedFile,
    OpenEvFile,
    openev_inbox_name,
)
from debate_core.application.ports.evidence_store import ObjectInfo, ObjectKey
from debate_core.application.ports.suppression import (
    ReasonCode,
    SuppressionAction,
    SuppressionEntry,
    SuppressionList,
    UnreadableAppendOnlyRecord,
)
from debate_core.application.sync_runs import record_for_summary
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsSnapshotStore
from debate_core.integrations.local.archive_reader import read_archive
from debate_core.integrations.local.suppression_list import local_suppression_list_file
from debate_core.testing.fakes import InMemoryAppendOnlyRecord, empty_suppression_list

from .conftest import REQUEST, RemovalWorld

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

CASELIST = "testcl26"
YEAR = 2026
PULLED_AT = datetime(2026, 9, 28, 6, 0, tzinfo=UTC)
LIMITS = {"max_archive_bytes": 64 * 1024 * 1024, "max_unpacked_bytes": 64 * 1024 * 1024}


def sha256(body: str) -> str:
    return hashlib.sha256(DOCUMENT_BODIES[body]).hexdigest()


#: A camp file published as a single document.
ESTUARY = OpenEvFile(
    openev_id=512,
    path=f"openev/{YEAR}/Tamarack/TSF-Estuary Solvency Advocate.docx",
    filename="TSF-Estuary Solvency Advocate.docx",
    year=YEAR,
    tags=("policy",),
)
ESTUARY_SHA256 = sha256("estuary-solvency")

#: A camp release published as a zip: two camp files and one piece of macOS junk.
RELEASE = OpenEvFile(
    openev_id=901,
    path=f"openev/{YEAR}/Quillfeather/QDI Release.zip",
    filename="QDI Release.zip",
    year=YEAR,
    tags=("policy",),
)
AFF_SHA256 = sha256("harbor-tariffs-aff")
NEG_SHA256 = sha256("harbor-tariffs-neg")


def release_zip() -> bytes:
    """The release, byte-identically every time: fixed timestamps, members in path order."""
    members = (
        ("QDI Release/.DS_Store", b"\x00\x05\x16\x07 invented macOS metadata"),
        ("QDI Release/Quillfeather/QDI - Harbor Tariffs Aff.docx", DOCUMENT_BODIES["harbor-tariffs-aff"]),
        ("QDI Release/Quillfeather/QDI - Harbor Tariffs Neg.docx", DOCUMENT_BODIES["harbor-tariffs-neg"]),
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, body in members:
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, body)
    return buffer.getvalue()


class FakeOpenEvSource:
    """OpenCaselist listing OpenEv camp files and no archives, recording every download asked of it.

    A download is a request to OpenCaselist: `openev_fetches` is what reached the site.
    """

    def __init__(self, files: Sequence[tuple[OpenEvFile, bytes]]) -> None:
        self.files = list(files)
        self.openev_fetches: list[int] = []

    async def list_caselists(self, *, archived: bool | None = None) -> list[CaselistInfo]:
        return [CaselistInfo(slug=CASELIST)]

    async def get_caselist(self, caselist: str) -> CaselistInfo:
        return CaselistInfo(slug=caselist)

    async def list_archives(self, caselist: str) -> list[ArchiveListing]:
        return []

    async def list_openev(self, *, year: int | None = None) -> list[OpenEvFile]:
        return [file for file, _ in self.files]

    async def download_archive(self, archive: ArchiveListing, inbox: Path) -> DownloadedFile:
        raise AssertionError("no archive is listed, so none may be downloaded")

    async def download_openev(self, file: OpenEvFile, inbox: Path) -> DownloadedFile:
        self.openev_fetches.append(file.openev_id)
        body = next(body for listed, body in self.files if listed.openev_id == file.openev_id)
        destination = inbox / openev_inbox_name(file)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(body)
        return DownloadedFile(
            path=destination,
            sha256=hashlib.sha256(body).hexdigest(),
            byte_size=len(body),
            source_name=f"openev-{file.openev_id}",
        )


class UnreadableSuppressionList:
    """A list whose bucket copy cannot be read: the SSO session behind it has expired."""

    async def entries(self) -> tuple[SuppressionEntry, ...]:
        raise StoreCredentialsExpired(hint="aws sso login --profile debate-dev-evidence")

    async def append(self, entries: Sequence[SuppressionEntry]) -> None:
        raise StoreCredentialsExpired(hint="aws sso login --profile debate-dev-evidence")


@pytest.fixture
def world(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> RemovalWorld:
    return RemovalWorld(data_dir=tmp_path / "evidence", bucket_name=evidence_bucket, client=s3_client)


def build_sync(
    world: RemovalWorld,
    source: FakeOpenEvSource,
    *,
    skip_reads: SuppressionList | None = None,
    pull_list: SuppressionList | None = None,
) -> CaselistSyncService:
    """The pull as the composition root builds it when the environment names a bucket.

    One list object, shared by the importers and the run's skip: both copies, falling back to this
    machine's when the bucket's needs a login. `pull_list` replaces that shared object.
    `skip_reads` replaces only the list the skip reads, so a test can blind the skip and watch the
    importer stand alone.
    """
    shared = pull_list or LocalFallbackSuppressionList(world.suppression(), local=local_only(world))
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
        suppression=skip_reads if skip_reads is not None else shared,
        publisher=CaselistPublishService(
            local=world.local, remote=world.bucket, suppression=world.suppression()
        ),
        clock=lambda: PULLED_AT,
    )


def local_only(world: RemovalWorld) -> RecordedSuppressionList:
    """This machine's copy of the list, and nothing else."""
    return RecordedSuppressionList(local_suppression_list_file(world.data_dir))


async def pull(
    world: RemovalWorld, source: FakeOpenEvSource, **options: SuppressionList | None
) -> RunSummary:
    summary = await build_sync(world, source, **options).run([CASELIST])
    assert summary.succeeded, summary.stages
    return summary


async def remove_source(world: RemovalWorld, sha: str) -> None:
    """`caselist remove --source <sha256> --execute`, through the removal service the command runs."""
    service = world.service()
    plan = await service.plan(SourceSelector(sha), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_CAMP)
    assert (await service.execute(plan)).completed


async def unsuppress(world: RemovalWorld, sha: str) -> None:
    """`caselist unsuppress --sha256 <sha256> --execute`."""
    service = world.service()
    await service.unsuppress(await service.plan_unsuppress(sha, reason=ReasonCode.REMOVED_IN_ERROR))


def inbox_copy(world: RemovalWorld, file: OpenEvFile) -> Path:
    return world.data_dir / "inbox" / openev_inbox_name(file)


def decisions(summary: RunSummary) -> dict[int, SelectionDecision]:
    return {one.openev_id: one.decision for one in summary.openev}


def release_classifications(world: RemovalWorld) -> dict[str, int]:
    path = world.local.object_path_for(openev_manifest_key(YEAR, Event.POLICY))  # type: ignore[misc]
    rows = [json.loads(line) for line in read_manifest_lines(path)]
    return next(row for row in rows if row["kind"] == "summary")["classifications"]


def select_reason(summary: RunSummary) -> str:
    record = summary.stage(SyncStage.SELECT)
    assert record is not None and record.reason is not None
    return record.reason


# ------------------------------------------------------------------------------------------------
# The five cases (ac1)
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("inbox_kept", [False, True], ids=["inbox-copy-gone", "inbox-copy-kept"])
async def test_a_removed_single_file_camp_release_is_skipped_as_removed(
    world: RemovalWorld, inbox_kept: bool
) -> None:
    """No request for it reaches OpenCaselist, nothing is imported, and the run says why.

    Gone from the inbox it used to be downloaded and refused; kept, imported from there and refused,
    and the run reported `openev 2026-policy` imported (both shown failing in the session report).
    """
    source = FakeOpenEvSource([(ESTUARY, DOCUMENT_BODIES["estuary-solvency"])])
    await pull(world, source)
    await remove_source(world, ESTUARY_SHA256)
    if not inbox_kept:
        inbox_copy(world, ESTUARY).unlink()

    again = await pull(world, source)

    assert source.openev_fetches == [ESTUARY.openev_id], "the removed file was requested again"
    assert decisions(again) == {ESTUARY.openev_id: SelectionDecision.SKIPPED_AS_REMOVED}
    assert again.openev_downloaded == 0 and again.snapshots_imported == ()
    assert again.nothing_new
    written = again.as_json()
    assert written["openev_skipped_as_removed"] == 1
    assert written["openev_selections"][0]["decision"] == "skipped_as_removed"  # type: ignore[index]
    assert "1 OpenEv file(s) skipped as removed" in select_reason(again)
    # What `caselist runs` keeps of the run says so too, not "downloaded and refused".
    record = record_for_summary(again, environment="dev", mode="run")
    assert record.openev_downloaded == 0
    assert any("skipped as removed" in (stage.reason or "") for stage in record.stages)


@pytest.mark.parametrize("inbox_kept", [False, True], ids=["inbox-copy-gone", "inbox-copy-kept"])
async def test_a_zip_release_with_one_member_removed_is_already_imported_through_its_other_rows(
    world: RemovalWorld, inbox_kept: bool
) -> None:
    """Two camp files and junk; the Aff removed, the Neg still recorded: there is nothing to fetch.

    With the inbox copy kept, the Neg's row names the zip's digest. With it gone, the delivery
    record says the zip delivered the Aff and the Neg: one suppressed, one recorded.
    """
    source = FakeOpenEvSource([(RELEASE, release_zip())])
    await pull(world, source)
    await remove_source(world, AFF_SHA256)
    if not inbox_kept:
        inbox_copy(world, RELEASE).unlink()

    again = await pull(world, source)

    assert source.openev_fetches == [RELEASE.openev_id]
    assert decisions(again) == {RELEASE.openev_id: SelectionDecision.ALREADY_IMPORTED}
    assert again.nothing_new and again.openev_skipped_as_removed == 0


@pytest.mark.parametrize("inbox_kept", [False, True], ids=["inbox-copy-gone", "inbox-copy-kept"])
async def test_a_zip_release_with_every_member_removed_is_skipped_as_removed(
    world: RemovalWorld, inbox_kept: bool
) -> None:
    """Both camp files removed. The junk member has no digest, so it does not keep the zip wanted."""
    source = FakeOpenEvSource([(RELEASE, release_zip())])
    await pull(world, source)
    await remove_source(world, AFF_SHA256)
    await remove_source(world, NEG_SHA256)
    if not inbox_kept:
        inbox_copy(world, RELEASE).unlink()

    again = await pull(world, source)

    assert source.openev_fetches == [RELEASE.openev_id]
    assert decisions(again) == {RELEASE.openev_id: SelectionDecision.SKIPPED_AS_REMOVED}
    assert again.snapshots_imported == ()


async def test_after_unsuppress_the_next_pull_downloads_it_again_and_says_why(world: RemovalWorld) -> None:
    """The delivery record still names the file; the list no longer stops it; the list wins."""
    source = FakeOpenEvSource([(ESTUARY, DOCUMENT_BODIES["estuary-solvency"])])
    await pull(world, source)
    await remove_source(world, ESTUARY_SHA256)
    inbox_copy(world, ESTUARY).unlink()
    skipped = await pull(world, source)
    assert decisions(skipped) == {ESTUARY.openev_id: SelectionDecision.SKIPPED_AS_REMOVED}

    await unsuppress(world, ESTUARY_SHA256)
    restored = await pull(world, source)

    assert source.openev_fetches == [ESTUARY.openev_id, ESTUARY.openev_id]
    assert decisions(restored) == {ESTUARY.openev_id: SelectionDecision.DOWNLOAD}
    assert restored.blobs_stored == 1, "the file was fetched but not stored again"
    (selection,) = restored.openev
    assert selection.note is not None and "suppression having been lifted" in selection.note
    assert "1 fetched before and neither recorded nor suppressed now" in select_reason(restored)

    settled = await pull(world, source)
    assert decisions(settled) == {ESTUARY.openev_id: SelectionDecision.ALREADY_IMPORTED}
    assert settled.openev[0].note is None


async def test_a_removal_recorded_only_in_the_buckets_copy_is_honoured(world: RemovalWorld) -> None:
    """This machine's copy of the list has no entry for it — as on a machine that did not make the
    removal — and the bucket's does. The pull reads both, so it is not fetched."""
    source = FakeOpenEvSource([(ESTUARY, DOCUMENT_BODIES["estuary-solvency"])])
    await pull(world, source)
    await remove_source(world, ESTUARY_SHA256)
    local_copy = local_suppression_list_file(world.data_dir)
    Path(local_copy.location).unlink()
    assert await local_copy.read_lines() == ()
    inbox_copy(world, ESTUARY).unlink()

    again = await pull(world, source)

    assert source.openev_fetches == [ESTUARY.openev_id]
    assert decisions(again) == {ESTUARY.openev_id: SelectionDecision.SKIPPED_AS_REMOVED}


# ------------------------------------------------------------------------------------------------
# The two defences stand alone (ac3)
# ------------------------------------------------------------------------------------------------


async def test_with_the_skip_blind_the_importer_still_refuses_the_removed_file(world: RemovalWorld) -> None:
    """The run's skip given an empty list, the importers the real one: downloaded, and refused."""
    source = FakeOpenEvSource([(ESTUARY, DOCUMENT_BODIES["estuary-solvency"])])
    await pull(world, source)
    await remove_source(world, ESTUARY_SHA256)
    inbox_copy(world, ESTUARY).unlink()

    again = await pull(world, source, skip_reads=empty_suppression_list())

    assert source.openev_fetches == [ESTUARY.openev_id, ESTUARY.openev_id]
    assert decisions(again) == {ESTUARY.openev_id: SelectionDecision.DOWNLOAD}
    assert again.blobs_stored == 0 and again.files_imported == 0
    assert release_classifications(world) == {"SUPPRESSED": 1}
    assert not world.local.blob_path_for(ESTUARY_SHA256).exists()  # type: ignore[misc]


# ------------------------------------------------------------------------------------------------
# The delivery record is never the authority (ac4)
# ------------------------------------------------------------------------------------------------


async def test_a_removal_the_delivery_record_does_not_know_is_read_from_the_inbox_copy(
    world: RemovalWorld,
) -> None:
    """The record lost, the file still in the inbox: its bytes are read there and the list asked."""
    source = FakeOpenEvSource([(ESTUARY, DOCUMENT_BODIES["estuary-solvency"])])
    await pull(world, source)
    await remove_source(world, ESTUARY_SHA256)
    (world.data_dir / OPENEV_DELIVERIES_FILENAME).unlink()

    again = await pull(world, source)

    assert source.openev_fetches == [ESTUARY.openev_id]
    assert decisions(again) == {ESTUARY.openev_id: SelectionDecision.SKIPPED_AS_REMOVED}


async def test_a_removal_nothing_on_this_machine_can_recognise_costs_one_download_and_no_more(
    world: RemovalWorld,
) -> None:
    """The record and the inbox copy both gone: the listing gives no digest, so this is what is left.

    Fetched once and refused by the importer; the record learns what the id delivered; the next
    run skips it. This pins the limit the session report states rather than hiding it.
    """
    source = FakeOpenEvSource([(ESTUARY, DOCUMENT_BODIES["estuary-solvency"])])
    await pull(world, source)
    await remove_source(world, ESTUARY_SHA256)
    (world.data_dir / OPENEV_DELIVERIES_FILENAME).unlink()
    inbox_copy(world, ESTUARY).unlink()

    unknown = await pull(world, source)
    assert decisions(unknown) == {ESTUARY.openev_id: SelectionDecision.DOWNLOAD}
    assert unknown.blobs_stored == 0
    inbox_copy(world, ESTUARY).unlink()

    known = await pull(world, source)

    assert source.openev_fetches == [ESTUARY.openev_id, ESTUARY.openev_id]
    assert decisions(known) == {ESTUARY.openev_id: SelectionDecision.SKIPPED_AS_REMOVED}


async def test_a_remembered_id_the_list_does_not_suppress_is_reported_and_fetched_not_skipped(
    world: RemovalWorld, caplog: pytest.LogCaptureFixture
) -> None:
    """A delivery record saying 512 was fetched, no manifest row for it, and no suppression entry.

    The record has nothing to say about removal, so it is not trusted to skip anything: the file is
    fetched, and the select stage and the log say this machine had it before.
    """
    OpenEvDeliveries(world.data_dir / OPENEV_DELIVERIES_FILENAME).record(
        ESTUARY.openev_id,
        OpenEvDelivery(
            download_sha256=ESTUARY_SHA256, path_sha256=None, member_sha256=frozenset({ESTUARY_SHA256})
        ),
    )
    source = FakeOpenEvSource([(ESTUARY, DOCUMENT_BODIES["estuary-solvency"])])

    with caplog.at_level(logging.WARNING, logger="debate_core.application.caselist_sync"):
        summary = await pull(world, source)

    assert source.openev_fetches == [ESTUARY.openev_id]
    assert summary.blobs_stored == 1
    (selection,) = summary.openev
    assert selection.note is not None and "lifted" not in selection.note
    assert (
        "1 fetched before and neither recorded nor suppressed now, so taken again (openev-512)"
        in select_reason(summary)
    )
    assert any("OpenEv file 512" in message for message in caplog.messages)


async def test_a_delivery_record_this_build_did_not_write_is_ignored_with_a_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    record = tmp_path / OPENEV_DELIVERIES_FILENAME
    record.write_text('{"schema_version": 1, "deliveries": {"512": {"removed": true}}}\n', encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="debate_core.application.caselist_sync"):
        assert OpenEvDeliveries(record).read() == {}

    assert any("not one this build wrote" in message for message in caplog.messages)


# ------------------------------------------------------------------------------------------------
# A camp file changed upstream, and a list that cannot be read
# ------------------------------------------------------------------------------------------------


async def test_a_removed_file_uploaded_again_under_a_new_id_is_held_back(
    world: RemovalWorld, caplog: pytest.LogCaptureFixture
) -> None:
    """OpenEv changes a file only by deleting it and uploading again: a new id at the same path.

    The new bytes have a new sha256 that no entry names, so the importer would store them. A
    removal covers a camp's later upload of the same file (PM decision), so the run holds it back,
    says which id, and logs it. `v1-e34-t08` must keep this hold when it changes the rule below.
    """
    source = FakeOpenEvSource([(ESTUARY, DOCUMENT_BODIES["estuary-solvency"])])
    await pull(world, source)
    await remove_source(world, ESTUARY_SHA256)
    reuploaded = ESTUARY.model_copy(update={"openev_id": 640})
    source.files = [(reuploaded, DOCUMENT_BODIES["canal-counterplan-revised"])]

    with caplog.at_level(logging.WARNING, logger="debate_core.application.caselist_sync"):
        again = await pull(world, source)

    assert source.openev_fetches == [ESTUARY.openev_id]
    assert decisions(again) == {640: SelectionDecision.SAME_PATH_AS_A_REMOVED_FILE}
    assert "1 held back as a new id at a removed file's path (openev-640)" in select_reason(again)
    assert any("OpenEv file 640" in message for message in caplog.messages)


async def test_a_file_uploaded_again_where_nothing_was_removed_is_held_by_its_old_row_as_before(
    world: RemovalWorld,
) -> None:
    """Not this task's rule, pinned so the report's account of it stays true. A known defect.

    512's row, `openev-512-…`, names an id no longer listed, so `v1-e34-t06`'s matching reads it by
    path, and the re-upload at that path counts as already imported: its revised bytes are never
    fetched. `v1-e34-t08` fixes it, and must invert this test — the re-upload fetched — rather than
    delete it.
    """
    source = FakeOpenEvSource([(ESTUARY, DOCUMENT_BODIES["estuary-solvency"])])
    await pull(world, source)
    reuploaded = ESTUARY.model_copy(update={"openev_id": 640})
    source.files = [(reuploaded, DOCUMENT_BODIES["canal-counterplan-revised"])]

    again = await pull(world, source)

    assert source.openev_fetches == [ESTUARY.openev_id]
    assert decisions(again) == {640: SelectionDecision.ALREADY_IMPORTED}


async def test_with_the_list_unreadable_a_remembered_file_waits_and_a_new_one_is_fetched(
    world: RemovalWorld,
) -> None:
    """An expired SSO session: whether 512 was removed cannot be known, so it is not fetched on a
    guess. 777 was never seen here, so nothing about it depends on the list, and it is fetched."""
    source = FakeOpenEvSource([(ESTUARY, DOCUMENT_BODIES["estuary-solvency"])])
    await pull(world, source)
    await remove_source(world, ESTUARY_SHA256)
    inbox_copy(world, ESTUARY).unlink()
    new = OpenEvFile(
        openev_id=777, path=f"openev/{YEAR}/Brightwater/Orchard Kritik.docx", year=YEAR, tags=("policy",)
    )
    source.files.append((new, DOCUMENT_BODIES["orchard-kritik"]))

    plan = await build_sync(world, source, skip_reads=UnreadableSuppressionList()).plan([CASELIST])

    assert {one.openev_id: one.decision for one in plan.openev} == {
        ESTUARY.openev_id: SelectionDecision.SUPPRESSION_LIST_UNREADABLE,
        777: SelectionDecision.DOWNLOAD,
    }


async def test_a_dry_run_shows_the_skip_and_writes_no_delivery_record(world: RemovalWorld) -> None:
    source = FakeOpenEvSource([(ESTUARY, DOCUMENT_BODIES["estuary-solvency"])])
    await pull(world, source)
    await remove_source(world, ESTUARY_SHA256)
    inbox_copy(world, ESTUARY).unlink()
    record = world.data_dir / OPENEV_DELIVERIES_FILENAME
    before = record.read_bytes()

    planned = await build_sync(world, source).run([CASELIST], dry_run=True)

    assert decisions(planned) == {ESTUARY.openev_id: SelectionDecision.SKIPPED_AS_REMOVED}
    assert source.openev_fetches == [ESTUARY.openev_id]
    assert record.read_bytes() == before


async def test_the_delivery_record_holds_digests_and_ids_and_nothing_a_name_could_be_in(
    world: RemovalWorld,
) -> None:
    """The record a pull of the zip release writes, checked by hand against the release's members."""
    source = FakeOpenEvSource([(RELEASE, release_zip())])
    await pull(world, source)

    written = json.loads((world.data_dir / OPENEV_DELIVERIES_FILENAME).read_text(encoding="utf-8"))

    assert written == {
        "schema_version": 1,
        "deliveries": {
            "901": {
                "download_sha256": hashlib.sha256(release_zip()).hexdigest(),
                "path_sha256": hashlib.sha256(RELEASE.path.encode()).hexdigest(),
                "member_sha256": sorted([AFF_SHA256, NEG_SHA256]),
            }
        },
    }
    text = json.dumps(written)
    assert "Quillfeather" not in text and "Harbor" not in text and "QDI" not in text


# ------------------------------------------------------------------------------------------------
# An expired AWS session (after PM review): the pull's list falls back to this machine's copy
# ------------------------------------------------------------------------------------------------


class RefusingStore:
    """The bucket as the everyday profile reaches it, refusing every read the same way."""

    def __init__(self, error: Exception | None = None, *, body: bytes = b"") -> None:
        self.error = error
        self.body = body

    async def get_file(self, key: ObjectKey, destination: Path) -> ObjectInfo:
        if self.error is not None:
            raise self.error
        destination.write_bytes(self.body)
        return ObjectInfo(key=key, size=len(self.body))

    async def put_file(self, key: ObjectKey, source: Path) -> ObjectInfo:
        raise self.error or AssertionError("nothing may be appended")

    async def head(self, key: ObjectKey) -> ObjectInfo:
        raise AssertionError("not used")

    async def list_objects(self, prefix: str) -> tuple[ObjectInfo, ...]:
        raise AssertionError("not used")


EXPIRED = StoreCredentialsExpired(hint="aws sso login --profile debate-dev-evidence")


def suppression_entry(sha: str) -> SuppressionEntry:
    return SuppressionEntry(
        action=SuppressionAction.SUPPRESS,
        sha256=sha,
        recorded_at=PULLED_AT,
        reason=ReasonCode.REQUESTED_BY_CAMP,
        request_id=REQUEST,
    )


def pull_list_over(local: InMemoryAppendOnlyRecord, bucket: RefusingStore) -> LocalFallbackSuppressionList:
    """The container's pull list, with the bucket's copy behind `bucket`."""
    return LocalFallbackSuppressionList(
        RecordedSuppressionList(local, ObjectStoreAppendOnlyRecord(bucket, SUPPRESSION_LIST_KEY)),  # type: ignore[arg-type]
        local=RecordedSuppressionList(local),
    )


async def test_missing_or_expired_credentials_read_this_machines_copy_and_say_why() -> None:
    local = InMemoryAppendOnlyRecord(lines=[suppression_entry(ESTUARY_SHA256).to_line()])
    pull_list = pull_list_over(local, RefusingStore(EXPIRED))

    entries = await pull_list.entries()

    assert [entry.sha256 for entry in entries] == [ESTUARY_SHA256]
    assert pull_list.fallbacks == 1
    assert pull_list.local_only_reason is not None and "aws sso login" in pull_list.local_only_reason


@pytest.mark.parametrize(
    "bucket",
    [
        pytest.param(RefusingStore(StoreAccessDenied("GetObject", SUPPRESSION_LIST_KEY)), id="access-denied"),
        pytest.param(RefusingStore(body=b'{"schema_version":1,"act'), id="torn-line"),
    ],
)
async def test_any_other_failure_to_read_the_buckets_copy_still_fails_closed(bucket: RefusingStore) -> None:
    pull_list = pull_list_over(InMemoryAppendOnlyRecord(), bucket)

    with pytest.raises((StoreAccessDenied, UnreadableAppendOnlyRecord)):
        await pull_list.entries()

    assert pull_list.fallbacks == 0 and pull_list.local_only_reason is None


async def test_an_append_never_falls_back_to_one_copy() -> None:
    local = InMemoryAppendOnlyRecord()
    pull_list = pull_list_over(local, RefusingStore(EXPIRED))

    with pytest.raises(StoreCredentialsExpired):
        await pull_list.append([suppression_entry(ESTUARY_SHA256)])

    assert await local.read_lines() == ()


async def test_an_expired_session_imports_skips_and_records_that_the_local_copy_alone_was_read(
    world: RemovalWorld,
) -> None:
    """512 removed on this machine; the session then expires and 514 is listed.

    The import completes, 512 is still skipped as removed, and the summary and both stages that
    read the list say this machine's copy alone was read, and why.
    """
    source = FakeOpenEvSource([(ESTUARY, DOCUMENT_BODIES["estuary-solvency"])])
    await pull(world, source)
    await remove_source(world, ESTUARY_SHA256)
    orchard = OpenEvFile(
        openev_id=514, path=f"openev/{YEAR}/Brightwater/Orchard Kritik.docx", year=YEAR, tags=("policy",)
    )
    source.files.append((orchard, DOCUMENT_BODIES["orchard-kritik"]))
    expired = LocalFallbackSuppressionList(
        RecordedSuppressionList(
            local_suppression_list_file(world.data_dir),
            ObjectStoreAppendOnlyRecord(RefusingStore(EXPIRED), SUPPRESSION_LIST_KEY),  # type: ignore[arg-type]
        ),
        local=local_only(world),
    )

    summary = await build_sync(world, source, pull_list=expired).run([CASELIST])

    assert summary.succeeded, summary.stages
    assert decisions(summary) == {
        ESTUARY.openev_id: SelectionDecision.SKIPPED_AS_REMOVED,
        514: SelectionDecision.DOWNLOAD,
    }
    assert summary.blobs_stored == 1
    reason = summary.suppression_list_local_copy_only
    assert reason is not None and "aws sso login" in reason
    assert summary.as_json()["suppression_list_local_copy_only"] == reason
    for stage in (SyncStage.SELECT, SyncStage.IMPORT):
        record = summary.stage(stage)
        assert record is not None and "this machine's copy of the suppression list alone was read" in (
            record.reason or ""
        ), stage


async def test_a_run_that_never_needed_the_list_does_not_report_an_earlier_runs_fallback(
    world: RemovalWorld,
) -> None:
    """The record is per run: the second run reads no list (512 is held by its row) and says nothing."""
    source = FakeOpenEvSource([(ESTUARY, DOCUMENT_BODIES["estuary-solvency"])])
    expired = LocalFallbackSuppressionList(
        RecordedSuppressionList(
            local_suppression_list_file(world.data_dir),
            ObjectStoreAppendOnlyRecord(RefusingStore(EXPIRED), SUPPRESSION_LIST_KEY),  # type: ignore[arg-type]
        ),
        local=local_only(world),
    )
    service = build_sync(world, source, pull_list=expired)

    first = await service.run([CASELIST])
    second = await service.run([CASELIST])

    assert first.suppression_list_local_copy_only is not None
    assert second.suppression_list_local_copy_only is None
    assert decisions(second) == {ESTUARY.openev_id: SelectionDecision.ALREADY_IMPORTED}
