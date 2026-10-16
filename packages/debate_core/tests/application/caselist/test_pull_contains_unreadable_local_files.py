"""A file this machine cannot read fails one stage or one import of a pull, never the run (`v1-e34-t19`).

Three loose ends `v1-e34-t13`, `v1-e34-t12` and `v1-e34-t18` left, each of which ended a run on a
raw exception with no summary, no run record worth reading and exit 70, "a bug":

* **A manifest file.** `v1-e34-t13` translated the stores, and a manifest is also read and written
  by its path. An unreadable manifest *file* in a readable directory, or a manifest directory this
  user may not write to, was a `PermissionError`. It is now `LocalStoreAccessDenied` naming the
  manifest directory's role, like any other refusal by this machine.
* **A weekly archive.** An archive in the inbox that could not be read ended the run. It now fails
  that archive's import, and the rest of the run's archives are imported.
* **The publisher.** An error it raises before its per-object loop, such as a local manifest with
  a line nobody can read, ended the run. It now fails the publish stage on that error's own code,
  and the other snapshots are published.

Everything is real except the OpenCaselist source and the one thing each test breaks: the importers,
the manifests, the publisher and the status comparison, against moto, in the installation
`test_inbox_retention.py` builds, with real `chmod`. Every expected code, outcome and list is
written by hand from what the test sets up (working agreement 6).

A name this task adds is looked up when a test runs, never imported at the top, so that every test
here is collected and run against the source as it was before the change.
"""

from __future__ import annotations

import errno
import hashlib
import os
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from tests.fixtures.caselist.build_synthetic_archives import DOCUMENT_BODIES, build_snapshot_zips
from tests.fixtures.permissions import needs_permissions

from debate_core.application import caselist_sync as sync_module
from debate_core.application import errors
from debate_core.application.caselist import manifest as manifest_module
from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.parse_sources import enumerate_sources
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.removal_plan import SourceSelector
from debate_core.application.caselist_sync import CaselistSyncService, SyncStage
from debate_core.application.errors import StoreAccessDenied
from debate_core.application.ports.caselist_source import (
    ArchiveKind,
    ArchiveListing,
    DownloadedFile,
    OpenEvFile,
)
from debate_core.application.ports.suppression import ReasonCode
from debate_core.domain.caselist import Event
from debate_core.integrations.s3 import S3EvidenceObjectStore
from debate_core.testing.fakes import empty_suppression_list

from .conftest import REQUEST, RemovalWorld
from .test_inbox_retention import (
    CASELIST,
    ESTUARY,
    ESTUARY_BODY,
    RELEASE,
    RELEASE_BODY,
    WEEK_1,
    WEEK_2,
    ExpiredBucket,
    FakeSource,
    Installation,
    backlog,
    weekly_name,
)
from .test_pending_work_owes_every_unpublished_snapshot import confirmed_in, owed, pending_file
from .test_pull_stage_failure_codes import assert_names_nothing_of_this_machine, pull, stage, stages_of

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

MANIFEST_DIRECTORY_ROLE = "the manifest directory"
"""How a refusal names where manifests are kept: by what it is for, never by its path."""

OTHER = "othercl26"
"""A second caselist the run pulls, served the same invented archives under its own name."""

RELEASE_MANIFEST = "objects/manifests/openev/2026-policy.jsonl"
WEEK_1_MANIFEST = "objects/manifests/testcl26/2026-09-01.jsonl"

A_SECOND_CAMP_FILE = OpenEvFile(
    openev_id=640,
    path="openev/2026/Tamarack/TSF-Harbor Dredging Neg.docx",
    filename="TSF-Harbor Dredging Neg.docx",
    year=2026,
    tags=("policy",),
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def installation(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> Installation:
    return Installation(
        data_dir=tmp_path / "evidence",
        bucket=S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client),
        archives=build_snapshot_zips(tmp_path / "published"),
    )


def assert_refused_by_this_machine(refusal: BaseException, data_dir: Path) -> None:
    """A refusal by this machine, naming the manifest directory by its role and nothing by its path."""
    assert type(refusal) is errors.LocalStoreAccessDenied
    assert refusal.resource == MANIFEST_DIRECTORY_ROLE
    assert "storage.data_dir" in str(refusal)
    assert str(data_dir) not in str(refusal)
    assert str(data_dir.parent) not in str(refusal)
    assert "aws sso login" not in str(refusal)


def assert_the_data_directory_hint(failed: Mapping[str, object]) -> None:
    """A failed stage's fix for a refusal by this machine: a permission, by role, and not a login."""
    assert failed.get("error_codes") == ["STORE_ACCESS_DENIED"]
    hint = failed.get("hint")
    assert isinstance(hint, str)
    assert MANIFEST_DIRECTORY_ROLE in hint
    assert "storage.data_dir" in hint
    assert "aws sso login" not in hint


# ------------------------------------------------------------------------------------------------
# ac1: a manifest file, read and written by its path
# ------------------------------------------------------------------------------------------------


@needs_permissions
def test_an_unreadable_manifest_file_is_a_refusal_naming_the_manifest_directory(tmp_path: Path) -> None:
    """The directory can be listed and the file is there; the operating system will not open it."""
    manifests = tmp_path / "evidence" / "objects" / "manifests" / "testcl26"
    manifests.mkdir(parents=True)
    manifest = manifests / "2026-09-01.jsonl"
    manifest.write_text('{"kind": "summary"}\n', encoding="utf-8")
    manifest.chmod(0)

    with pytest.raises(StoreAccessDenied) as refusal:
        manifest_module.read_manifest_lines(manifest)

    assert_refused_by_this_machine(refusal.value, tmp_path / "evidence")
    assert refusal.value.operation == "read"


@needs_permissions
def test_a_manifest_in_a_directory_that_cannot_be_looked_into_is_refused_and_never_read_as_absent(
    tmp_path: Path,
) -> None:
    """No manifest reads as "nothing imported", and a run that believed it would fetch a camp
    release again. A directory this user may not look into is a refusal, not an empty answer."""
    manifests = tmp_path / "evidence" / "objects" / "manifests" / "openev"
    manifests.mkdir(parents=True)
    manifest = manifests / "2026-policy.jsonl"
    manifest.write_text('{"kind": "summary"}\n', encoding="utf-8")
    manifests.chmod(0)
    try:
        with pytest.raises(StoreAccessDenied) as refusal:
            manifest_module.read_manifest_lines(manifest)
    finally:
        manifests.chmod(0o700)

    assert_refused_by_this_machine(refusal.value, tmp_path / "evidence")


def test_a_manifest_that_is_not_there_still_reads_as_no_lines(tmp_path: Path) -> None:
    """Unchanged: absent is an answer."""
    assert manifest_module.read_manifest_lines(tmp_path / "manifests" / "testcl26" / "nothing.jsonl") == []


@needs_permissions
def test_a_manifest_this_machine_will_not_let_be_written_is_a_refusal_naming_the_manifest_directory(
    tmp_path: Path,
) -> None:
    """A manifest is written to a second file beside it and renamed. A directory that can be read
    and not written refuses the second file."""
    manifests = tmp_path / "evidence" / "objects" / "manifests" / "testcl26"
    manifests.mkdir(parents=True)
    held = manifests / "2026-09-01.jsonl"
    held.write_text('{"kind": "summary"}\n', encoding="utf-8")
    manifests.chmod(0o500)
    try:
        with pytest.raises(StoreAccessDenied) as refusal:
            manifest_module.write_manifest_lines(['{"kind": "summary", "rewritten": true}'], held)
        left = sorted(one.name for one in manifests.iterdir())
    finally:
        manifests.chmod(0o700)

    assert_refused_by_this_machine(refusal.value, tmp_path / "evidence")
    assert refusal.value.operation == "write"
    assert held.read_text(encoding="utf-8") == '{"kind": "summary"}\n', "the manifest held is untouched"
    assert left == ["2026-09-01.jsonl"]


@needs_permissions
async def test_a_pull_that_cannot_write_a_manifest_fails_the_import_on_the_store_with_the_data_directory_fix(
    installation: Installation,
) -> None:
    """Week one is imported and published. Week two is fetched, and this machine will not let its
    manifest be written. That fails the import stage on a refusal by this machine, the code a retry
    may cure once the permission is fixed, with the fix in the stage's hint. It used to end the run
    on a `PermissionError`, exit 70. After the fix the next run imports week two from the inbox."""
    await backlog(installation, WEEK_1)
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    manifests = installation.data_dir / "objects" / "manifests" / CASELIST
    manifests.chmod(0o500)
    try:
        watched = await pull(installation, installation.sync(source))
    finally:
        manifests.chmod(0o700)

    summary = watched.summary
    imported = stage(summary, SyncStage.IMPORT)
    assert imported["outcome"] == "failed"
    assert_the_data_directory_hint(imported)
    assert str(imported["reason"]).startswith(f"0 imported; 1 refused: {weekly_name(WEEK_2)}: ")
    assert summary.failure_codes == ("STORE_ACCESS_DENIED",), "every failure is one a retry may cure: exit 3"
    assert summary.snapshots_imported == ()
    assert watched.pulled.record is not None, "the run was recorded, not ended"
    assert_names_nothing_of_this_machine(summary, installation)

    again = await installation.sync(source).run([CASELIST])

    assert again.succeeded, again.stages
    assert again.snapshots_imported == ("testcl26 2026-09-08",)
    assert source.archive_fetches == [weekly_name(WEEK_2)], (
        "the week is imported from the inbox, not fetched twice"
    )


@needs_permissions
async def test_a_pull_that_cannot_read_a_weekly_manifest_file_stops_before_fetching_naming_the_role(
    installation: Installation,
) -> None:
    """The selection reads each week's manifest to know what this machine holds. One it cannot open
    stops the run before anything is fetched, as an unreadable manifest directory does
    (`v1-e34-t13`), and by the same error, which the command exits 3 on."""
    await backlog(installation, WEEK_1)
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    manifest = installation.data_dir / WEEK_1_MANIFEST
    manifest.chmod(0)

    with pytest.raises(StoreAccessDenied) as stopped:
        await installation.sync(source).run([CASELIST])

    assert_refused_by_this_machine(stopped.value, installation.data_dir)
    assert source.archive_fetches == []


@needs_permissions
async def test_a_pull_that_cannot_read_a_release_manifest_file_stops_before_fetching_a_camp_file_again(
    installation: Installation,
) -> None:
    """The release manifest says which camp files are imported. Unreadable, it must not read as
    "none are": the run would fetch the one it holds again."""
    first = FakeSource(installation.archives, openev=[(ESTUARY, ESTUARY_BODY)])
    assert (await installation.sync(first).run([CASELIST])).succeeded
    (installation.data_dir / RELEASE_MANIFEST).chmod(0)
    source = FakeSource(
        installation.archives,
        openev=[(ESTUARY, ESTUARY_BODY), (A_SECOND_CAMP_FILE, DOCUMENT_BODIES["grove-round-1-aff"])],
    )

    with pytest.raises(StoreAccessDenied) as stopped:
        await installation.sync(source).run([CASELIST])

    assert_refused_by_this_machine(stopped.value, installation.data_dir)
    assert source.openev_fetches == []


@needs_permissions
async def test_a_release_manifest_file_retention_cannot_read_fails_retention_and_removes_nothing(
    installation: Installation,
) -> None:
    """Retention reads every release manifest to judge the camp downloads in the inbox, including
    the releases this run listed no file of. One it cannot open used to end the run on a
    `PermissionError`, after every other stage had finished. It now fails retention, which decides
    nothing about the run, and the inbox is left as it is."""
    first = FakeSource(installation.archives, weeks=[WEEK_1], openev=[(ESTUARY, ESTUARY_BODY)])
    assert (await installation.sync(first, bucket=False).run([CASELIST])).succeeded
    await installation.publish()
    await installation.publish("openev")
    before = installation.inbox_state()
    assert len(before) == 2
    (installation.data_dir / RELEASE_MANIFEST).chmod(0)

    summary = await installation.sync(FakeSource(installation.archives, weeks=[WEEK_1])).run([CASELIST])

    retention = stage(summary, SyncStage.RETENTION)
    assert retention["outcome"] == "failed"
    assert_the_data_directory_hint(retention)
    assert summary.succeeded
    assert summary.failure_codes == ()
    assert installation.inbox_state() == before
    assert_names_nothing_of_this_machine(summary, installation)


def test_a_manifest_write_that_fails_for_another_reason_is_left_as_the_error_it_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only a refusal is translated. A disk that fills as the manifest takes its name is not one:
    the `OSError` is raised as it is, the second file is cleaned up, and the manifest held stays."""
    held = tmp_path / "manifests" / "testcl26" / "2026-09-01.jsonl"
    manifest_module.write_manifest_lines(['{"kind": "summary"}'], held)

    def disk_full(source: object, destination: object) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(os, "replace", disk_full)
    with pytest.raises(OSError, match="No space left on device") as failed:
        manifest_module.write_manifest_lines(['{"kind": "summary", "rewritten": true}'], held)
    monkeypatch.undo()

    assert type(failed.value) is OSError
    assert held.read_text(encoding="utf-8") == '{"kind": "summary"}\n'
    assert sorted(one.name for one in held.parent.iterdir()) == ["2026-09-01.jsonl"]


# ------------------------------------------------------------------------------------------------
# ac1: every other reader of a manifest file by its path
# ------------------------------------------------------------------------------------------------


@needs_permissions
async def test_a_publish_that_cannot_read_a_manifest_file_is_refused_by_this_machine(
    imported_data_dir: Path, local: LocalEvidence, bucket: S3EvidenceObjectStore
) -> None:
    (imported_data_dir / WEEK_1_MANIFEST).chmod(0)
    service = CaselistPublishService(local=local, remote=bucket, suppression=empty_suppression_list())

    with pytest.raises(StoreAccessDenied) as refusal:
        await service.plan(CASELIST)

    assert_refused_by_this_machine(refusal.value, imported_data_dir)


@needs_permissions
async def test_the_parse_pipeline_that_cannot_read_a_manifest_file_is_refused_by_this_machine(
    imported_data_dir: Path, local: LocalEvidence
) -> None:
    (imported_data_dir / WEEK_1_MANIFEST).chmod(0)

    with pytest.raises(StoreAccessDenied) as refusal:
        await enumerate_sources(local, CASELIST)

    assert_refused_by_this_machine(refusal.value, imported_data_dir)


@needs_permissions
async def test_a_removal_that_cannot_read_a_manifest_file_is_refused_by_this_machine(
    removal_world: RemovalWorld,
) -> None:
    digest = hashlib.sha256(DOCUMENT_BODIES["grove-round-1-aff"]).hexdigest()
    (removal_world.data_dir / WEEK_1_MANIFEST).chmod(0)

    with pytest.raises(StoreAccessDenied) as refusal:
        await removal_world.planner().plan(
            SourceSelector(digest), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM
        )

    assert_refused_by_this_machine(refusal.value, removal_world.data_dir)


# ------------------------------------------------------------------------------------------------
# ac2: a weekly archive that cannot be read fails its own import
# ------------------------------------------------------------------------------------------------


class TwoCaselists(FakeSource):
    """OpenCaselist listing weeklies for two caselists, and able to hand over a download nobody can read.

    Args:
        weeks_of: The weeks each caselist lists. Both are served the same invented archives.
        unreadable: Archive names whose download lands in the inbox with no permission to read it.
        complete: Caselists that also list a complete archive, dated with week one.
    """

    def __init__(
        self,
        archives: dict[date, Path],
        *,
        weeks_of: Mapping[str, Sequence[date]],
        unreadable: Sequence[str] = (),
        vanishing: Sequence[str] = (),
        complete: Sequence[str] = (),
        openev: Sequence[tuple[OpenEvFile, bytes]] = (),
    ) -> None:
        super().__init__(archives, openev=openev)
        self.weeks_of = {caselist: list(weeks) for caselist, weeks in weeks_of.items()}
        self.unreadable = set(unreadable)
        self.vanishing = set(vanishing)
        self.complete = set(complete)

    async def list_archives(self, caselist: str) -> list[ArchiveListing]:
        listed = [
            ArchiveListing(
                caselist=caselist,
                name=archive_name(caselist, day),
                kind=ArchiveKind.WEEKLY,
                archive_date=day,
                url=f"https://files.example.invalid/{archive_name(caselist, day)}",
            )
            for day in self.weeks_of.get(caselist, ())
        ]
        if caselist in self.complete:
            name = complete_archive_name(caselist)
            listed.append(
                ArchiveListing(
                    caselist=caselist,
                    name=name,
                    kind=ArchiveKind.FULL,
                    archive_date=WEEK_1,
                    url=f"https://files.example.invalid/{name}",
                )
            )
        return listed

    async def download_archive(self, archive: ArchiveListing, inbox: Path) -> DownloadedFile:
        self.archive_fetches.append(archive.name)
        assert archive.archive_date is not None
        body = self.archives[archive.archive_date].read_bytes()
        destination = inbox / archive.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(body)
        if archive.name in self.unreadable:
            destination.chmod(0)
        if archive.name in self.vanishing:
            destination.unlink()
        return DownloadedFile(
            path=destination,
            sha256=hashlib.sha256(body).hexdigest(),
            byte_size=len(body),
            source_name=archive.name,
        )


def archive_name(caselist: str, day: date) -> str:
    return f"{caselist}-weekly-{day.isoformat()}.zip"


def complete_archive_name(caselist: str) -> str:
    return f"{caselist}-all-{WEEK_1.isoformat()}.zip"


def pulling_two_caselists(installation: Installation, source: FakeSource) -> CaselistSyncService:
    """The installation's pull, knowing the event of the second caselist as well as the first."""
    service = installation.sync(source)
    # The installation builds the pull for its one caselist; this is the same pull with the
    # composition root's table one slug longer.
    service._event_for_caselist = every_caselist_debates_ld  # pyright: ignore[reportPrivateUsage]
    return service


def every_caselist_debates_ld(caselist: str) -> Event:
    return Event.LD


@needs_permissions
async def test_a_weekly_archive_that_cannot_be_read_fails_its_own_import_and_the_others_are_imported(
    installation: Installation, s3_client: S3Client, evidence_bucket: str
) -> None:
    """Two caselists and a camp release in one run. The first caselist's week one arrives and cannot
    be opened. That used to end the run on a `PermissionError`. It now fails that archive's import
    under the code of an archive that cannot be read; the same caselist's week two waits behind it,
    as behind any gap; the other caselist's week and the camp release are imported and published."""
    source = TwoCaselists(
        installation.archives,
        weeks_of={CASELIST: [WEEK_1, WEEK_2], OTHER: [WEEK_1]},
        unreadable=[archive_name(CASELIST, WEEK_1)],
        openev=[(RELEASE, RELEASE_BODY)],
    )

    summary = await pulling_two_caselists(installation, source).run([CASELIST, OTHER])

    imported = stage(summary, SyncStage.IMPORT)
    assert imported["outcome"] == "failed"
    assert imported.get("error_codes") == ["UNREADABLE_ARCHIVE"]
    assert imported.get("hint") is None
    reason = str(imported["reason"])
    assert reason.startswith(
        "2 imported; 1 refused: testcl26-weekly-2026-09-01.zip: testcl26-weekly-2026-09-01.zip "
        "cannot be read as an archive: "
    )
    assert "PermissionError" in reason
    assert reason.endswith("1 archive(s) in the inbox held back for a later run, behind an older week")
    assert summary.snapshots_imported == ("othercl26 2026-09-01", "openev 2026-policy")
    assert summary.failure_codes == ("UNREADABLE_ARCHIVE",), "a verdict: exit 1 by v1-e34-t13's rule"
    assert not summary.succeeded
    assert stage(summary, SyncStage.PUBLISH)["outcome"] == "completed"
    published = s3_client.list_objects_v2(Bucket=evidence_bucket, Prefix="manifests/")
    assert sorted(str(one.get("Key")) for one in published.get("Contents", [])) == [
        "manifests/openev/2026-policy.jsonl",
        "manifests/othercl26/2026-09-01.jsonl",
    ]
    assert source.archive_fetches == [
        "othercl26-weekly-2026-09-01.zip",
        "testcl26-weekly-2026-09-01.zip",
        "testcl26-weekly-2026-09-08.zip",
    ]
    assert_names_nothing_of_this_machine(summary, installation)

    (installation.inbox / archive_name(CASELIST, WEEK_1)).chmod(0o600)
    again = await pulling_two_caselists(installation, source).run([CASELIST, OTHER])

    assert again.succeeded, again.stages
    assert again.snapshots_imported == ("testcl26 2026-09-01", "testcl26 2026-09-08")
    assert len(source.archive_fetches) == 3, "both weeks are imported from the inbox, neither fetched again"


async def test_a_weekly_archive_gone_from_the_inbox_before_its_import_fails_its_own_import(
    installation: Installation,
) -> None:
    """The other half of "unreadable or vanished". The archive reader already said so by name, so
    this never ended a run; it is here so that it never does."""
    source = TwoCaselists(
        installation.archives,
        weeks_of={CASELIST: [WEEK_1], OTHER: [WEEK_1]},
        vanishing=[archive_name(CASELIST, WEEK_1)],
    )

    summary = await pulling_two_caselists(installation, source).run([CASELIST, OTHER])

    imported = stage(summary, SyncStage.IMPORT)
    assert imported["outcome"] == "failed"
    assert imported.get("error_codes") == ["UNREADABLE_ARCHIVE"]
    assert summary.snapshots_imported == ("othercl26 2026-09-01",)


@needs_permissions
async def test_a_complete_archive_that_cannot_be_read_fails_its_own_import_after_the_weeklies(
    installation: Installation,
) -> None:
    """`--full-archive` fetches the caselist's complete archive after its weekly. The weekly is
    imported; the complete archive cannot be opened and fails its own import."""
    source = TwoCaselists(
        installation.archives,
        weeks_of={CASELIST: [WEEK_1]},
        complete=[CASELIST],
        unreadable=[complete_archive_name(CASELIST)],
    )

    summary = await installation.sync(source).run([CASELIST], full_archive=CASELIST)

    imported = stage(summary, SyncStage.IMPORT)
    assert imported["outcome"] == "failed"
    assert imported.get("error_codes") == ["UNREADABLE_ARCHIVE"]
    assert str(imported["reason"]).startswith("1 imported; 1 refused: testcl26-all-2026-09-01.zip: ")
    assert summary.snapshots_imported == ("testcl26 2026-09-01",)
    assert stage(summary, SyncStage.PUBLISH)["outcome"] == "completed"
    assert_names_nothing_of_this_machine(summary, installation)


async def test_an_operating_system_error_that_is_not_the_archives_fails_its_import_by_its_class_alone(
    installation: Installation, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The disk fills while one caselist's manifest is written. That is not an archive that cannot
    be read, and it is not a refusal: nobody modelled it, so it is recorded as the CLI reports any
    such error, by its class and never by its message, which quotes the path. The run goes on."""
    write_manifest = manifest_module.write_manifest

    def disk_full_for_one(report: Any, destination: Path) -> Path:
        if report.caselist == CASELIST:
            raise OSError(errno.ENOSPC, "No space left on device", str(destination))
        return write_manifest(report, destination)

    monkeypatch.setattr(sync_module, "write_manifest", disk_full_for_one)
    source = TwoCaselists(installation.archives, weeks_of={CASELIST: [WEEK_1], OTHER: [WEEK_1]})

    summary = await pulling_two_caselists(installation, source).run([CASELIST, OTHER])

    imported = stage(summary, SyncStage.IMPORT)
    assert imported["outcome"] == "failed"
    assert imported["reason"] == "1 imported; 1 refused: testcl26-weekly-2026-09-01.zip: OSError"
    assert imported.get("error_codes") == ["INTERNAL_ERROR"]
    assert summary.snapshots_imported == ("othercl26 2026-09-01",)
    assert summary.failure_codes == ("INTERNAL_ERROR",)
    assert_names_nothing_of_this_machine(summary, installation)


def test_only_an_operating_system_error_from_the_reader_itself_is_the_archive_being_unreadable(
    tmp_path: Path,
) -> None:
    """The translation is around the reader and nothing else, whether the reader fails when it is
    called or part-way through. An error of this project's own passes through as it is, and so does
    an archive that reads cleanly."""
    archive = tmp_path / "testcl26-weekly-2026-09-01.zip"
    entries_of = sync_module._entries_of  # pyright: ignore[reportPrivateUsage]

    def refuses_when_called(path: Path) -> Any:
        raise PermissionError(13, "Permission denied", str(path))

    def fails_part_way(path: Path) -> Any:
        yield "one entry"
        raise OSError(errno.EIO, "Input/output error", str(path))

    def refuses_by_name(path: Path) -> Any:
        raise errors.ArchiveTooLarge(measured="archive", actual_bytes=9, limit_bytes=8, source=path.name)

    with pytest.raises(errors.UnreadableArchive) as at_the_call:
        entries_of(refuses_when_called, archive)
    read: list[object] = []
    with pytest.raises(errors.UnreadableArchive) as part_way:
        for entry in entries_of(fails_part_way, archive):
            read.append(entry)
    with pytest.raises(errors.ArchiveTooLarge):
        entries_of(refuses_by_name, archive)

    assert str(at_the_call.value) == (
        "testcl26-weekly-2026-09-01.zip cannot be read as an archive: the file in the inbox could "
        "not be read (PermissionError (errno 13))"
    )
    assert read == ["one entry"]
    assert str(part_way.value).endswith("the file in the inbox could not be read (OSError (errno 5))")
    assert str(tmp_path) not in str(at_the_call.value) + str(part_way.value)
    assert list(entries_of(lambda _: iter(["a", "b"]), archive)) == ["a", "b"]  # pyright: ignore[reportArgumentType]


async def test_an_operating_system_error_that_is_not_a_complete_archives_fails_its_import_alone(
    installation: Installation, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same for the complete archive, which has a loop of its own: the disk fills as its
    manifest is written, after the weekly's was. The weekly is imported and published, and the
    complete archive's import fails by the error's class."""
    write_manifest = manifest_module.write_manifest

    def disk_full_for_the_complete_archive(report: Any, destination: Path) -> Path:
        if report.full_archive:
            raise OSError(errno.ENOSPC, "No space left on device", str(destination))
        return write_manifest(report, destination)

    monkeypatch.setattr(sync_module, "write_manifest", disk_full_for_the_complete_archive)
    source = TwoCaselists(installation.archives, weeks_of={CASELIST: [WEEK_1]}, complete=[CASELIST])

    summary = await installation.sync(source).run([CASELIST], full_archive=CASELIST)

    imported = stage(summary, SyncStage.IMPORT)
    assert imported["outcome"] == "failed"
    assert imported["reason"] == "1 imported; 1 refused: testcl26-all-2026-09-01.zip: OSError"
    assert imported.get("error_codes") == ["INTERNAL_ERROR"]
    assert summary.snapshots_imported == ("testcl26 2026-09-01",)
    assert stage(summary, SyncStage.PUBLISH)["outcome"] == "completed"
    assert_names_nothing_of_this_machine(summary, installation)


# ------------------------------------------------------------------------------------------------
# ac5: an error the publisher raises outside its per-object loop
# ------------------------------------------------------------------------------------------------

A_LINE_NOBODY_CAN_READ = '{"kind": "member", "classification": "NEW", "sha2'
"""A manifest row cut short: the publisher refuses the whole manifest (`UnreadableManifest`)."""


def tear(manifest: Path) -> None:
    with manifest.open("a", encoding="utf-8") as stream:
        stream.write(A_LINE_NOBODY_CAN_READ + "\n")


async def test_a_manifest_the_publisher_cannot_read_fails_publish_on_its_own_code_and_the_run_finishes(
    installation: Installation, s3_client: S3Client, evidence_bucket: str
) -> None:
    """Two weeks are owed from a run whose session had expired. Week one's manifest then gains a
    line nobody can read. `--publish-pending` used to end on `UnreadableManifest` when it planned
    week one, with no summary and week two unpublished. The stage now fails on that error's own
    code, the one `caselist publish` exits on; week two is published and confirmed; and the file
    holds exactly what the bucket did not confirm, as `v1-e34-t18` settled it."""
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    await installation.sync(source, publish_to=ExpiredBucket()).run([CASELIST])
    assert owed(installation) == ["testcl26 2026-09-01", "testcl26 2026-09-08"]
    tear(installation.data_dir / WEEK_1_MANIFEST)

    watched = await pull(installation, installation.sync(source), publish_pending=True)

    summary = watched.summary
    published = stage(summary, SyncStage.PUBLISH)
    assert published["outcome"] == "failed"
    assert published.get("error_codes") == ["UNREADABLE_MANIFEST"]
    assert "incomplete: testcl26 2026-09-01: manifests/testcl26/2026-09-01.jsonl line " in str(
        published["reason"]
    )
    assert A_LINE_NOBODY_CAN_READ not in str(published["reason"]), "the row itself is never quoted"
    assert summary.failure_codes == ("UNREADABLE_MANIFEST",)
    assert confirmed_in(s3_client, evidence_bucket) == ["testcl26 2026-09-08"]
    assert owed(installation) == ["testcl26 2026-09-01"]
    assert summary.pending_publish == ("testcl26 2026-09-01",)
    assert stage(summary, SyncStage.REPORT)["outcome"] == "completed"
    assert (installation.data_dir / "caselist-sync-runs" / f"{summary.run_id}.json").is_file()
    record = watched.pulled.record
    assert record is not None
    assert record.outcome == "failed"
    assert record.error_class is None, "a failed stage, not a run that stopped on an exception"
    assert [one.title.split(":")[0] for one in watched.notifier.sent] == ["caselist pull failed"]
    assert "aws sso login" not in watched.notified
    assert_names_nothing_of_this_machine(summary, installation)


async def test_a_release_manifest_the_publisher_cannot_read_fails_publish_in_a_whole_run_too(
    installation: Installation, s3_client: S3Client, evidence_bucket: str
) -> None:
    """A whole run this time. The camp release is owed and its manifest has a torn line, which the
    selection reads past and the publisher refuses. The week this run imports is published; the
    release stays owed; every later stage runs."""
    first = FakeSource(installation.archives, openev=[(ESTUARY, ESTUARY_BODY)])
    await installation.sync(first, publish_to=ExpiredBucket()).run([CASELIST])
    assert owed(installation) == ["openev 2026-policy"]
    tear(installation.data_dir / RELEASE_MANIFEST)
    source = FakeSource(installation.archives, weeks=[WEEK_1], openev=[(ESTUARY, ESTUARY_BODY)])

    summary = await installation.sync(source).run([CASELIST])

    published = stage(summary, SyncStage.PUBLISH)
    assert published["outcome"] == "failed"
    assert published.get("error_codes") == ["UNREADABLE_MANIFEST"]
    assert summary.snapshots_imported == ("testcl26 2026-09-01",)
    assert confirmed_in(s3_client, evidence_bucket) == ["testcl26 2026-09-01"]
    assert owed(installation) == ["openev 2026-policy"]
    assert pending_file(installation).is_file()
    assert [one["stage"] for one in stages_of(summary)] == [
        "select",
        "download",
        "import",
        "publish",
        "parse",
        "landscape",
        "report",
        "retention",
    ]
    assert stage(summary, SyncStage.REPORT)["outcome"] == "completed"
    assert_names_nothing_of_this_machine(summary, installation)
