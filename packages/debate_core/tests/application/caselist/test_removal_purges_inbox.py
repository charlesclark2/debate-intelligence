"""A completed removal leaves no removed bytes in the sync's inbox, and loses nothing pending (`v1-e30-t09`).

`caselist pull` downloads into an inbox (`caselist.inbox_dir`, or `<data_dir>/inbox`) and never
clears it, so after the three synthetic weeks and the OpenEv release have been pulled, the inbox
holds each weekly archive and the camp release as downloaded. A removal that cleans the store and
the bucket but not the inbox leaves the removed bytes on this machine.

The inbox is scanned here by :func:`removed_bytes_in_inbox`, which shares no code with the removal:
it opens every file with `zipfile` directly, reads every entry — junk and zip-slip names included —
and hashes it. What it looks for is the removal's own record of what it removed, the log entry's
`removed_sha256`.

Every expectation is worked out by hand from the fixture tables (`tests/fixtures/caselist/` and
`tests/fixtures/openev/`), which hold no real caselist or camp content. The team removed is
`testcl26/Maple Grove/QX`. Its files, week by week:

* 09-01: the Round 1 affirmative (`grove-round-1-aff`) and the Round 2 negative as first filed.
* 09-08: Round 1, its `(1)` re-upload (same bytes), and Round 2 revised.
* 09-15: those three and the Bayview semifinal.

The Round 1 bytes are shared: `Cedar Hollow/ZaLu` disclosed them as its Round 3 from 09-08, and
the camp release holds them as `Tamarack/TSF-Borrowed Grove Aff.docx`. Every week also carries two
pieces of junk that name the team's Round 1: `__MACOSX/Maple Grove/QX/._…Round 1.docx` and the
Word lock file `Maple Grove/QX/~$ple Grove-QX-Aff-…Round 1.docx`.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import zipfile
from collections.abc import Collection, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_synthetic_archives import (
    DOCUMENT_BODIES,
    SNAPSHOTS,
    SYNTHETIC_CASELIST,
    SyntheticMember,
    _docx,  # pyright: ignore[reportPrivateUsage]
    build_snapshot_zips,
)
from tests.fixtures.openev.build_synthetic_openev import DOCUMENT_BODIES as OPENEV_BODIES
from tests.fixtures.openev.build_synthetic_openev import DOWNLOADS as OPENEV_DOWNLOADS
from tests.fixtures.openev.build_synthetic_openev import build_download_zips

from debate_core.application.caselist.import_service import CaselistImportService
from debate_core.application.caselist.inbox_purge import CaselistInbox, InboxAction, InboxReason
from debate_core.application.caselist.manifest import manifest_key, read_manifest_lines
from debate_core.application.caselist.openev_import_service import OpenEvImportService
from debate_core.application.caselist.removal_plan import RemovalPlan, SourceSelector, parse_team_selector
from debate_core.application.caselist.removal_service import (
    CaselistRemovalService,
    RemovalIncomplete,
    RemovalReport,
)
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.caselist_sync import (
    LOCK_FILENAME,
    OPENEV_DELIVERIES_FILENAME,
    CaselistSyncService,
    RunLock,
    SelectionDecision,
    StageOutcome,
    SyncStage,
)
from debate_core.application.ports.archive import InventoriedEntry
from debate_core.application.ports.caselist_source import (
    ArchiveKind,
    ArchiveListing,
    CaselistInfo,
    DownloadedFile,
    OpenEvFile,
    openev_inbox_name,
)
from debate_core.application.ports.suppression import ReasonCode, RemovalLogEntry, RemovalOutcome
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsSnapshotStore
from debate_core.integrations.local.archive_reader import ZipArchiveRewriter, read_archive
from debate_core.integrations.local.suppression_list import (
    local_removal_log_file,
    local_suppression_list_file,
)
from debate_core.testing.fakes import InMemoryAppendOnlyRecord

from .conftest import REQUEST, TEAM, RemovalWorld

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

LIMITS = {"max_archive_bytes": 64 * 1024 * 1024, "max_unpacked_bytes": 64 * 1024 * 1024}
PULLED_AT = datetime(2026, 9, 28, 6, 0, tzinfo=UTC)
NEXT_MONDAY = date(2026, 9, 22)
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def digest(body: str) -> str:
    return hashlib.sha256(DOCUMENT_BODIES[body]).hexdigest()


GROVE_ROUND_1 = digest("grove-round-1-aff")
"""The team's Round 1 affirmative, shared with another team and a camp file."""
ROUND_2_FIRST = digest("grove-round-2-neg-first")
ROUND_2_REVISED = digest("grove-round-2-neg-revised")
BAYVIEW = digest("bayview-semis-neg")

#: The OpenEv id the sync gave the camp release it downloaded, and so the name it sits under.
CAMP_RELEASE_ID = 701

#: Paths, inside every weekly archive's `testcl26-<mmdd>/` wrapper, of the team's entries.
QX_ROUND_1 = "Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1.docx"
QX_ROUND_1_REUPLOAD = "Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1 (1).docx"
QX_ROUND_2 = "Maple Grove/QX/Maple Grove-QX-Neg-Grove City Invitational-Round 2.docx"
QX_BAYVIEW = "Maple Grove/QX/Maple Grove-QX-Neg-Bayview Open [2]-Semis.docx"
QX_APPLEDOUBLE = "__MACOSX/Maple Grove/QX/._Maple Grove-QX-Aff-Grove City Invitational-Round 1.docx"
QX_LOCK_FILE = "Maple Grove/QX/~$ple Grove-QX-Aff-Grove City Invitational-Round 1.docx"
ZALU_ROUND_3 = "Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-Aff-Grove City Invitational-Round 3.docx"

#: Directory entries in the 09-22 archive (see :func:`next_mondays_archive`).
WRAPPER_DIRECTORY_ENTRY = "testcl26-0922/"
QX_DIRECTORY_ENTRY = "testcl26-0922/Maple Grove/QX/"
ZALU_DIRECTORY_ENTRY = "testcl26-0922/Cedar Hollow/ZaLu/"

#: A file another team discloses for the first time in the week that has not been imported yet.
ZALU_LAKESHORE = "Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-Neg-Lakeshore Open-Round 4.docx"
ZALU_LAKESHORE_BODY = _docx(("Lakeshore Open, round four, negative.", "Filed in the week not yet imported."))

#: A file the team discloses for the first time in that week: bytes the store has never seen.
QX_LAKESHORE = "Maple Grove/QX/Maple Grove-QX-Aff-Lakeshore Open-Round 4.docx"
QX_LAKESHORE_BODY = _docx(("Lakeshore Open, round four, affirmative.", "Never imported anywhere."))


# ------------------------------------------------------------------------------------------------
# The inbox a machine that pulls has
# ------------------------------------------------------------------------------------------------


def weekly_inbox_name(snapshot: date) -> str:
    """The name `caselist pull` gives a weekly archive: `<slug>-weekly-<date>.zip`."""
    return f"{SYNTHETIC_CASELIST}-weekly-{snapshot.isoformat()}.zip"


def camp_release_inbox_name() -> str:
    """`openev-<id>-<file name>`, as `openev_inbox_name` names a camp release the sync fetched."""
    return f"openev-{CAMP_RELEASE_ID}-{OPENEV_DOWNLOADS[0].name}.zip"


def stock_inbox(world: RemovalWorld, scratch: Path) -> Path:
    """The inbox of a machine that pulled the three weeks and the camp release the world imported.

    The very bytes the world imported, under the names the sync gives them.
    """
    inbox = world.data_dir / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    weeks = build_snapshot_zips(scratch / "weeks")
    for week in SNAPSHOTS:
        shutil.copyfile(weeks[week.snapshot], inbox / weekly_inbox_name(week.snapshot))
    release = build_download_zips(scratch / "openev")[OPENEV_DOWNLOADS[0].name]
    shutil.copyfile(release, inbox / camp_release_inbox_name())
    return inbox


def next_mondays_archive(*, with_a_new_file_of_the_team: bool = False) -> bytes:
    """The 09-22 weekly as the site serves it: the 09-15 archive, plus ZaLu's new Lakeshore negative.

    Written the way `build_snapshot_zips` writes a week: under a `testcl26-0922/` wrapper, the
    zip-slip entry at the top level, fixed timestamps. It also carries directory entries for the
    wrapper, the team's directory and ZaLu's, as zips made by some tools do: the reader ignores
    them, and a rewrite has to drop the team's, which names it and holds nothing else, and keep the
    wrapper, which holds the team's files and everyone else's, and ZaLu's.
    """
    members = [
        *SNAPSHOTS[-1].members_for(zip_form=True),
        SyntheticMember(path=ZALU_LAKESHORE, body=None),
    ]
    if with_a_new_file_of_the_team:
        members.append(SyntheticMember(path=QX_LAKESHORE, body=None))
    bodies = {ZALU_LAKESHORE: ZALU_LAKESHORE_BODY, QX_LAKESHORE: QX_LAKESHORE_BODY}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for directory in (WRAPPER_DIRECTORY_ENTRY, QX_DIRECTORY_ENTRY, ZALU_DIRECTORY_ENTRY):
            archive.writestr(zipfile.ZipInfo(directory, date_time=_ZIP_TIMESTAMP), b"")
        for member in sorted(members, key=lambda one: one.path):
            name = member.path if member.path.startswith("../") else f"testcl26-0922/{member.path}"
            info = zipfile.ZipInfo(name, date_time=_ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o120777 << 16) if member.symlink_target is not None else 0o644 << 16
            archive.writestr(info, bodies.get(member.path, member.content))
    return buffer.getvalue()


def add_next_mondays_archive(inbox: Path, **options: bool) -> Path:
    """Next Monday's weekly, downloaded but not yet imported: an earlier pull's import never ran."""
    path = inbox / weekly_inbox_name(NEXT_MONDAY)
    path.write_bytes(next_mondays_archive(**options))
    return path


def removed_bytes_in_inbox(inbox: Path, removed: set[str]) -> list[str]:
    """Every file in the inbox that holds a removed sha256, as itself or as any entry of a zip.

    Independent of the code under test: every regular file under the inbox, dot files and
    `.partial/` included, hashed whole; every zip opened with `zipfile` and every entry hashed,
    whatever its name.
    """
    found: list[str] = []
    for path in sorted(inbox.rglob("*")):
        if not path.is_file():
            continue
        name = path.relative_to(inbox).as_posix()
        if hashlib.sha256(path.read_bytes()).hexdigest() in removed:
            found.append(name)
        if zipfile.is_zipfile(path) and path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as archive:
                for info in archive.infolist():
                    if not info.is_dir() and hashlib.sha256(archive.read(info)).hexdigest() in removed:
                        found.append(f"{name} :: {info.filename}")
    return found


def entries(path: Path) -> dict[str, bytes]:
    """Every entry of a zip, by the name it carries, with its bytes."""
    with zipfile.ZipFile(path) as archive:
        return {info.filename: archive.read(info) for info in archive.infolist()}


def inbox_state(inbox: Path) -> dict[str, tuple[bytes, int]]:
    """Every file under the inbox with its bytes and modification time: what "changed nothing" means."""
    return {
        path.relative_to(inbox).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in sorted(inbox.rglob("*"))
        if path.is_file()
    }


def log_entries(world: RemovalWorld) -> list[RemovalLogEntry]:
    path = local_removal_log_file(world.data_dir).path
    return [RemovalLogEntry.from_line(line) for line in path.read_text(encoding="utf-8").splitlines()]


async def plan_team(
    world: RemovalWorld, *, include_shared: bool = False, service: CaselistRemovalService | None = None
) -> tuple[CaselistRemovalService, RemovalPlan]:
    remover = service or world.service()
    plan = await remover.plan(
        parse_team_selector(TEAM),
        request_id=REQUEST,
        reason=ReasonCode.REQUESTED_BY_TEAM,
        include_shared=include_shared,
    )
    return remover, plan


async def remove_team(
    world: RemovalWorld, *, include_shared: bool = False, service: CaselistRemovalService | None = None
) -> RemovalReport:
    """`caselist remove --team 'testcl26/Maple Grove/QX' [--include-shared] --execute`."""
    remover, plan = await plan_team(world, include_shared=include_shared, service=service)
    report = await remover.execute(plan)
    assert report.completed
    return report


# ------------------------------------------------------------------------------------------------
# The pull, against an OpenCaselist that lists what the test says and counts every download
# ------------------------------------------------------------------------------------------------


class FakeOpenCaselist:
    """Lists weekly archives and OpenEv files; records every download, which is a request to the site."""

    def __init__(
        self,
        *,
        archives: Sequence[tuple[date, bytes]] = (),
        openev: Sequence[tuple[OpenEvFile, bytes]] = (),
    ) -> None:
        self.archives = {weekly_inbox_name(day): (day, body) for day, body in archives}
        self.openev = list(openev)
        self.archive_fetches: list[str] = []
        self.openev_fetches: list[int] = []

    async def list_caselists(self, *, archived: bool | None = None) -> list[CaselistInfo]:
        return [CaselistInfo(slug=SYNTHETIC_CASELIST)]

    async def get_caselist(self, caselist: str) -> CaselistInfo:
        return CaselistInfo(slug=caselist)

    async def list_archives(self, caselist: str) -> list[ArchiveListing]:
        return [
            ArchiveListing(
                caselist=caselist,
                name=name,
                kind=ArchiveKind.WEEKLY,
                archive_date=day,
                url=f"https://archives.invalid/{name}",
            )
            for name, (day, _) in sorted(self.archives.items())
        ]

    async def list_openev(self, *, year: int | None = None) -> list[OpenEvFile]:
        return [file for file, _ in self.openev]

    async def download_archive(self, archive: ArchiveListing, inbox: Path) -> DownloadedFile:
        self.archive_fetches.append(archive.name)
        return _write(inbox / archive.name, self.archives[archive.name][1], archive.name)

    async def download_openev(self, file: OpenEvFile, inbox: Path) -> DownloadedFile:
        self.openev_fetches.append(file.openev_id)
        body = next(body for listed, body in self.openev if listed.openev_id == file.openev_id)
        return _write(inbox / openev_inbox_name(file), body, f"openev-{file.openev_id}")


def _write(destination: Path, body: bytes, source_name: str) -> DownloadedFile:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(body)
    return DownloadedFile(
        path=destination,
        sha256=hashlib.sha256(body).hexdigest(),
        byte_size=len(body),
        source_name=source_name,
    )


def build_pull(world: RemovalWorld, source: FakeOpenCaselist) -> CaselistSyncService:
    """`caselist pull` as the composition root builds it, reading this machine's copy of the list."""
    suppression = RecordedSuppressionList(local_suppression_list_file(world.data_dir))
    blobs = FsSnapshotStore(world.data_dir)
    return CaselistSyncService(
        source=source,
        archive_importer=CaselistImportService(
            caselists=world.repository, blobs=blobs, suppression=suppression
        ),
        openev_importer=OpenEvImportService(caselists=world.repository, blobs=blobs, suppression=suppression),
        local=world.local,
        read_archive=lambda path: read_archive(path, **LIMITS),
        event_for_caselist=lambda slug: Event.LD,
        inbox=world.data_dir / "inbox",
        state_dir=world.data_dir,
        suppression=suppression,
        clock=lambda: PULLED_AT,
    )


def manifest_rows(world: RemovalWorld, snapshot: date) -> list[dict[str, object]]:
    path = world.local.object_path_for(manifest_key(SYNTHETIC_CASELIST, snapshot))  # type: ignore[misc]
    return [json.loads(line) for line in read_manifest_lines(path)]


# ------------------------------------------------------------------------------------------------
# ac2: after a COMPLETED removal, no inbox file holds a removed sha256
# ------------------------------------------------------------------------------------------------


class TestNoRemovedBytesAreLeftInTheInbox:
    async def test_after_a_completed_removal_no_inbox_file_holds_a_removed_sha256(
        self, removal_world: RemovalWorld, tmp_path: Path
    ) -> None:
        """The team's Round 1 is in one camp download and three weekly archives; `--include-shared`
        removes it for everyone. Shown failing first against the removal as v1-e30-t07 left it."""
        inbox = stock_inbox(removal_world, tmp_path / "pulled")
        before = removed_bytes_in_inbox(inbox, {GROVE_ROUND_1})
        assert sorted({hit.split(" :: ")[0] for hit in before}) == [
            camp_release_inbox_name(),
            *(weekly_inbox_name(week.snapshot) for week in SNAPSHOTS),
        ], "the fixture: the file is in one camp download and three weekly archives"

        report = await remove_team(removal_world, include_shared=True)

        removed = set(report.log_entry.removed_sha256)
        assert removed == {GROVE_ROUND_1, ROUND_2_FIRST, ROUND_2_REVISED, BAYVIEW}
        assert removed_bytes_in_inbox(inbox, removed) == []

    async def test_a_rewritten_archive_waiting_to_be_imported_holds_none_of_it_either(
        self, removal_world: RemovalWorld, tmp_path: Path
    ) -> None:
        inbox = stock_inbox(removal_world, tmp_path / "pulled")
        add_next_mondays_archive(inbox)

        report = await remove_team(removal_world, include_shared=True)

        assert (inbox / weekly_inbox_name(NEXT_MONDAY)).exists(), "rewritten, never deleted"
        assert removed_bytes_in_inbox(inbox, set(report.log_entry.removed_sha256)) == []
        assert report.inbox_files_deleted == 4 and report.inbox_files_rewritten == 1

    async def test_a_removed_camp_document_is_deleted_from_the_inbox_and_not_fetched_again(
        self, s3_client: S3Client, evidence_bucket: str, tmp_path: Path
    ) -> None:
        """A camp file the pull imported before the delivery record existed (or whose record was lost).

        Its inbox copy is then the only place the pull can learn its digest from, so the removal
        writes the record before deleting the copy; the next pull skips it without a request.
        """
        world = RemovalWorld(data_dir=tmp_path / "evidence", bucket_name=evidence_bucket, client=s3_client)
        estuary = OpenEvFile(
            openev_id=512,
            path="openev/2026/Tamarack/TSF-Estuary Solvency Advocate.docx",
            filename="TSF-Estuary Solvency Advocate.docx",
            year=2026,
            tags=("policy",),
        )
        body = OPENEV_BODIES["estuary-solvency"]
        estuary_sha256 = hashlib.sha256(body).hexdigest()
        site = FakeOpenCaselist(openev=[(estuary, body)])
        await build_pull(world, site).run([SYNTHETIC_CASELIST])
        (world.data_dir / OPENEV_DELIVERIES_FILENAME).unlink()  # imported before v1-e34-t07 kept one
        copy = world.data_dir / "inbox" / openev_inbox_name(estuary)
        assert copy.exists()

        service = world.service()
        plan = await service.plan(
            SourceSelector(estuary_sha256), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_CAMP
        )
        assert [(one.name, one.action, one.reason) for one in plan.inbox] == [
            (copy.name, InboxAction.DELETE, InboxReason.THE_FILE_IS_REMOVED)
        ]
        assert (await service.execute(plan)).completed

        assert not copy.exists()
        again = await build_pull(world, site).run([SYNTHETIC_CASELIST])
        assert site.openev_fetches == [512], "the removed camp file was requested again"
        assert {one.openev_id: one.decision for one in again.openev} == {
            512: SelectionDecision.SKIPPED_AS_REMOVED
        }
        assert removed_bytes_in_inbox(world.data_dir / "inbox", {estuary_sha256}) == []


# ------------------------------------------------------------------------------------------------
# ac1: the plan lists every affected inbox file and what happens to it; the dry run changes nothing
# ------------------------------------------------------------------------------------------------


class TestTheDryRun:
    async def test_the_plan_lists_every_inbox_file_holding_a_removed_file_and_what_happens_to_it(
        self, removal_world: RemovalWorld, tmp_path: Path
    ) -> None:
        """`--team` without `--include-shared`: the Round 1 bytes stay for ZaLu and the camp file.

        So the camp release holds nothing the list stops and is not listed. Each weekly loses the
        team's files and its two pieces of junk; 09-01 to 09-15 are imported, 09-22 is not:

        * 09-01: Round 1, Round 2 (first), 2 junk out; ZaLu's two Harbor files and `.DS_Store` kept.
        * 09-08: Round 1, its re-upload, Round 2 (revised), 2 junk out; 11 of 16 kept.
        * 09-15: those and Bayview, 2 junk out; 13 of 19 kept.
        * 09-22: as 09-15, plus ZaLu's new Lakeshore file kept: 14 of 20.
        """
        inbox = stock_inbox(removal_world, tmp_path / "pulled")
        add_next_mondays_archive(inbox)

        _, plan = await plan_team(removal_world)

        listed = [
            (one.name, one.action, one.reason, set(one.removed_sha256), one.entries_dropped, one.entries_kept)
            for one in plan.inbox
        ]
        assert listed == [
            (
                weekly_inbox_name(date(2026, 9, 1)),
                InboxAction.DELETE,
                InboxReason.IMPORTED,
                {GROVE_ROUND_1, ROUND_2_FIRST},
                4,
                3,
            ),
            (
                weekly_inbox_name(date(2026, 9, 8)),
                InboxAction.DELETE,
                InboxReason.IMPORTED,
                {GROVE_ROUND_1, ROUND_2_REVISED},
                5,
                11,
            ),
            (
                weekly_inbox_name(date(2026, 9, 15)),
                InboxAction.DELETE,
                InboxReason.IMPORTED,
                {GROVE_ROUND_1, ROUND_2_REVISED, BAYVIEW},
                6,
                13,
            ),
            (
                weekly_inbox_name(NEXT_MONDAY),
                InboxAction.REWRITE,
                InboxReason.WAITING_TO_BE_IMPORTED,
                {GROVE_ROUND_1, ROUND_2_REVISED, BAYVIEW},
                6,
                14,
            ),
        ]
        assert plan.inbox_directory == str(inbox)
        assert not plan.nothing_to_do

    async def test_the_dry_run_changes_nothing_in_the_inbox_or_the_sync_state(
        self, removal_world: RemovalWorld, tmp_path: Path
    ) -> None:
        inbox = stock_inbox(removal_world, tmp_path / "pulled")
        add_next_mondays_archive(inbox)
        inbox_before = inbox_state(inbox)
        tree_before = removal_world.tree()

        for include_shared in (False, True):
            _, plan = await plan_team(removal_world, include_shared=include_shared)
            assert plan.inbox, "something to change, so changing nothing means something"

        assert inbox_state(inbox) == inbox_before
        assert removal_world.tree() == tree_before
        assert not (removal_world.data_dir / OPENEV_DELIVERIES_FILENAME).exists()

    async def test_the_plan_reports_the_teams_files_a_waiting_archive_holds_that_it_cannot_resolve(
        self, removal_world: RemovalWorld, tmp_path: Path
    ) -> None:
        """A file the team filed for the first time in a week not yet imported is unknown to the store,
        so nothing selects it. The plan says so; the list does not stop it, so it is not deleted."""
        inbox = stock_inbox(removal_world, tmp_path / "pulled")
        waiting = add_next_mondays_archive(inbox, with_a_new_file_of_the_team=True)

        _, plan = await plan_team(removal_world)
        assert [(left.name, left.files) for left in plan.inbox_team_files_left] == [(waiting.name, 1)]
        await removal_world.service().execute(plan)

        assert f"testcl26-0922/{QX_LAKESHORE}" in entries(waiting)


# ------------------------------------------------------------------------------------------------
# ac3: nothing still needed is lost
# ------------------------------------------------------------------------------------------------


class TestNothingPendingIsLost:
    async def test_an_archive_waiting_in_the_inbox_imports_exactly_its_other_members_afterwards(
        self, removal_world: RemovalWorld, tmp_path: Path
    ) -> None:
        """The 09-22 archive is rewritten, then the next pull imports it from the inbox.

        Hand-derived: the 09-15 archive's eleven real files less the team's four, plus ZaLu's new
        Lakeshore file, against a 09-15 baseline the removal left without the team's paths. ZaLu's
        copy of the Round 1 bytes stays: only the team's paths to it were withdrawn.
        """
        inbox = stock_inbox(removal_world, tmp_path / "pulled")
        waiting = add_next_mondays_archive(inbox)
        upstream = waiting.read_bytes()
        site = FakeOpenCaselist(
            archives=[*((week.snapshot, b"") for week in SNAPSHOTS), (NEXT_MONDAY, upstream)]
        )

        report = await remove_team(removal_world)
        summary = await build_pull(removal_world, site).run([SYNTHETIC_CASELIST])

        assert site.archive_fetches == [], "nothing re-downloaded: imported weeks deleted, 09-22 kept"
        assert {one.name: one.decision for one in summary.archives} == {
            weekly_inbox_name(date(2026, 9, 1)): SelectionDecision.ALREADY_IMPORTED,
            weekly_inbox_name(date(2026, 9, 8)): SelectionDecision.ALREADY_IMPORTED,
            weekly_inbox_name(date(2026, 9, 15)): SelectionDecision.ALREADY_IMPORTED,
            weekly_inbox_name(NEXT_MONDAY): SelectionDecision.ALREADY_IN_INBOX,
        }
        import_stage = summary.stage(SyncStage.IMPORT)
        assert import_stage is not None and import_stage.outcome is StageOutcome.COMPLETED
        rows = manifest_rows(removal_world, NEXT_MONDAY)
        members = {
            str(row["path"]): row["classification"] or row["skip_reason"]
            for row in rows
            if row["kind"] == "member"
        }
        BECO = "Northgate Prep/BeCo"  # noqa: N806 - a path prefix, read as one
        assert members == {
            "Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-AFF-Harbor Classic.docx": "UNCHANGED",
            ZALU_ROUND_3: "UNCHANGED",
            "Cedar Hollow/ZaLu/notes about the harbor round.docx": "UNCHANGED",
            ZALU_LAKESHORE: "NEW",
            "Cedar Hollow/ZaLu/latest-aff.docx": "SYMLINK",
            f"{BECO}/Northgate Prep-BeCo-Affirmative-Ridgeline Round Robin--Doubles.docx": "UNCHANGED",
            f"{BECO}/Northgate Prep-BeCo-Neg-02----Ridgeline Round Robin-Round 6.docx": "UNCHANGED",
            f"{BECO}/Westfield-XY-Neg-Ridgeline Round Robin-Round 3.docx": "UNCHANGED",
            "Riverbend Academy/MnPr/Riverbend Academy-MnPr-Pro-Seaside Cup-Finals.docx": "UNCHANGED",
            "Riverbend Academy/MnPr/Riverbend Academy-MnPr-Aff-Seaside Cup-Quarters.pdf": "UNCHANGED",
            "Riverbend Academy/MnPr/Riverbend Academy-MnPr-Neg-Seaside Cup-Quarters.doc": "UNCHANGED",
            "Riverbend Academy/MnPr/Riverbend Academy-MnPr-Aff-Seaside Cup—Round 5.docx": "UNCHANGED",
            "../escaped.docx": "PATH_OUTSIDE_ARCHIVE",
            ".DS_Store": "DESKTOP_SERVICES_STORE",
        }
        disclosures = (
            await removal_world.repository.list_disclosures(
                caselist=SYNTHETIC_CASELIST, snapshot=NEXT_MONDAY, limit=100
            )
        ).items
        assert sorted(one.source_path for one in disclosures) == sorted(
            path for path, outcome in members.items() if outcome in {"NEW", "UNCHANGED"}
        )
        stored = await removal_world.repository.find_source(hashlib.sha256(ZALU_LAKESHORE_BODY).hexdigest())
        assert stored is not None, "the other team's new disclosure is in the store"

        # What the manifest records for it: the digest of the file it imported, which the removal log
        # ties back to the archive as downloaded.
        (summary_row,) = [row for row in rows if row["kind"] == "summary"]
        rewritten = hashlib.sha256(waiting.read_bytes()).hexdigest()
        assert summary_row["archive_sha256"] == rewritten
        upstream_sha256 = hashlib.sha256(upstream).hexdigest()
        assert [(one.from_sha256, one.to_sha256) for one in report.log_entry.inbox_rewrites] == [
            (upstream_sha256, rewritten)
        ]
        comment = json.loads(zipfile.ZipFile(waiting).comment)
        assert comment["rewritten_from_sha256"] == upstream_sha256 and comment["request_id"] == REQUEST

    async def test_a_camp_download_waiting_in_the_inbox_imports_exactly_its_other_members_afterwards(
        self, removal_world: RemovalWorld, tmp_path: Path
    ) -> None:
        """A camp release downloaded but never imported holds the removed Round 1 bytes and one new
        camp file. It is rewritten, not deleted, and the next pull imports the new file from it."""
        inbox = stock_inbox(removal_world, tmp_path / "pulled")
        late = OpenEvFile(
            openev_id=702,
            path="openev/2026/Quillfeather/QDI Late Release.zip",
            filename="QDI Late Release.zip",
            year=2026,
            tags=("policy",),
        )
        breakwater = _docx(("Breakwater affirmative.", "A camp file released after the first download."))
        upstream = io.BytesIO()
        with zipfile.ZipFile(upstream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, body in (
                ("QDI Late Release/Quillfeather/QDI - Breakwater Aff.docx", breakwater),
                (
                    "QDI Late Release/Tamarack/TSF-Borrowed Grove Aff.docx",
                    DOCUMENT_BODIES["grove-round-1-aff"],
                ),
            ):
                archive.writestr(zipfile.ZipInfo(name, date_time=_ZIP_TIMESTAMP), body)
        waiting = inbox / openev_inbox_name(late)
        waiting.write_bytes(upstream.getvalue())

        _, plan = await plan_team(removal_world, include_shared=True)
        (planned,) = [one for one in plan.inbox if one.name == waiting.name]
        assert (planned.action, planned.reason) == (InboxAction.REWRITE, InboxReason.WAITING_TO_BE_IMPORTED)
        await removal_world.service().execute(plan)
        site = FakeOpenCaselist(openev=[(late, upstream.getvalue())])
        summary = await build_pull(removal_world, site).run([SYNTHETIC_CASELIST])

        assert site.openev_fetches == []
        assert {one.openev_id: one.decision for one in summary.openev} == {
            702: SelectionDecision.ALREADY_IN_INBOX
        }
        assert await removal_world.repository.find_source(hashlib.sha256(breakwater).hexdigest()) is not None
        assert await removal_world.repository.find_source(GROVE_ROUND_1) is None
        assert list(entries(waiting)) == ["QDI Late Release/Quillfeather/QDI - Breakwater Aff.docx"]

    async def test_the_rewrite_takes_out_only_what_the_list_stops_and_keeps_every_other_byte(
        self, removal_world: RemovalWorld, tmp_path: Path
    ) -> None:
        """ZaLu's copy of the withdrawn Round 1 bytes, the camp release that holds them too, and every
        file of every other team stay exactly as they were."""
        inbox = stock_inbox(removal_world, tmp_path / "pulled")
        waiting = add_next_mondays_archive(inbox)
        original = entries(waiting)
        release_before = (inbox / camp_release_inbox_name()).read_bytes()

        await remove_team(removal_world)

        taken_out = {
            f"testcl26-0922/{path}"
            for path in (
                QX_ROUND_1,
                QX_ROUND_1_REUPLOAD,
                QX_ROUND_2,
                QX_BAYVIEW,
                QX_APPLEDOUBLE,
                QX_LOCK_FILE,
            )
        }
        taken_out.add(QX_DIRECTORY_ENTRY)
        assert taken_out <= set(original) and {WRAPPER_DIRECTORY_ENTRY, ZALU_DIRECTORY_ENTRY} <= set(original)
        assert entries(waiting) == {name: data for name, data in original.items() if name not in taken_out}
        assert (inbox / camp_release_inbox_name()).read_bytes() == release_before
        assert sorted(path.name for path in inbox.iterdir()) == [
            camp_release_inbox_name(),
            weekly_inbox_name(NEXT_MONDAY),
        ]


# ------------------------------------------------------------------------------------------------
# The ordering, and a run cut short
# ------------------------------------------------------------------------------------------------


class TestTheOrder:
    async def test_an_append_that_fails_leaves_the_inbox_untouched(
        self, removal_world: RemovalWorld, tmp_path: Path
    ) -> None:
        """The suppression entries go first: a camp copy deleted before the list says it is removed is
        the copy the pull would otherwise have recognised it by."""
        inbox = stock_inbox(removal_world, tmp_path / "pulled")
        add_next_mondays_archive(inbox)
        before = inbox_state(inbox)
        refusing = InMemoryAppendOnlyRecord("this machine's copy")
        refusing.fail_next_append = OSError("disk full")
        service = removal_world.service()
        service.local_suppression = refusing

        with pytest.raises(RemovalIncomplete):
            await remove_team(removal_world, include_shared=True, service=service)

        assert inbox_state(inbox) == before
        (entry,) = log_entries(removal_world)
        assert entry.outcome is RemovalOutcome.INCOMPLETE and entry.inbox_files_deleted == 0

    async def test_a_run_cut_short_between_inbox_deletions_is_logged_incomplete_and_rerunning_finishes_it(
        self, removal_world: RemovalWorld, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        inbox = stock_inbox(removal_world, tmp_path / "pulled")
        add_next_mondays_archive(inbox)
        unlink = Path.unlink
        deletions: list[str] = []

        def second_deletion_fails(self: Path, missing_ok: bool = False) -> None:
            if self.parent == inbox:
                deletions.append(self.name)
                if len(deletions) == 2:
                    raise OSError("the machine went to sleep")
            unlink(self, missing_ok=missing_ok)

        monkeypatch.setattr(Path, "unlink", second_deletion_fails)
        with pytest.raises(RemovalIncomplete):
            await remove_team(removal_world)
        monkeypatch.setattr(Path, "unlink", unlink)

        (first,) = log_entries(removal_world)
        assert first.outcome is RemovalOutcome.INCOMPLETE
        assert (first.inbox_files_deleted, first.inbox_files_rewritten) == (1, 0)
        assert not (inbox / weekly_inbox_name(date(2026, 9, 1))).exists()
        assert (inbox / weekly_inbox_name(date(2026, 9, 8))).exists(), "the deletion that failed"

        report = await remove_team(removal_world)

        assert [entry.outcome for entry in log_entries(removal_world)] == [
            RemovalOutcome.INCOMPLETE,
            RemovalOutcome.COMPLETED,
        ]
        assert (report.inbox_files_deleted, report.inbox_files_rewritten) == (2, 1)
        assert removed_bytes_in_inbox(inbox, {ROUND_2_FIRST, ROUND_2_REVISED, BAYVIEW}) == []
        assert sorted(path.name for path in inbox.iterdir()) == [
            camp_release_inbox_name(),
            weekly_inbox_name(NEXT_MONDAY),
        ]

    async def test_a_pull_holding_the_inbox_stops_the_run_incomplete_with_the_inbox_untouched(
        self, removal_world: RemovalWorld, tmp_path: Path
    ) -> None:
        inbox = stock_inbox(removal_world, tmp_path / "pulled")
        before = inbox_state(inbox)

        with RunLock(removal_world.data_dir / LOCK_FILENAME), pytest.raises(RemovalIncomplete) as stopped:
            await remove_team(removal_world)

        assert "a caselist pull is running" in str(stopped.value)
        assert inbox_state(inbox) == before
        await remove_team(removal_world)
        assert len(list(inbox.iterdir())) == 1, "only the camp release, which holds nothing removed"


# ------------------------------------------------------------------------------------------------
# What a removal made before this step existed left behind, and what cannot be checked
# ------------------------------------------------------------------------------------------------


class TestLeftovers:
    async def test_running_an_earlier_removal_again_clears_what_it_left_in_the_inbox(
        self, removal_world: RemovalWorld, tmp_path: Path
    ) -> None:
        inbox = stock_inbox(removal_world, tmp_path / "pulled")
        removal_world.removal_inbox = tmp_path / "an-inbox-the-old-removal-never-touched"
        await remove_team(removal_world)
        assert removed_bytes_in_inbox(inbox, {ROUND_2_FIRST, ROUND_2_REVISED, BAYVIEW}), "left behind"
        removal_world.removal_inbox = None

        _, again = await plan_team(removal_world)
        assert not again.nothing_to_do and not again.suppression_entries
        assert [one.name for one in again.inbox] == [weekly_inbox_name(week.snapshot) for week in SNAPSHOTS]
        report = await removal_world.service().execute(again)

        assert report.completed and report.inbox_files_deleted == 3
        assert removed_bytes_in_inbox(inbox, {ROUND_2_FIRST, ROUND_2_REVISED, BAYVIEW}) == []

    async def test_a_zip_that_cannot_be_read_is_reported_and_the_removal_does_not_call_itself_complete(
        self, removal_world: RemovalWorld, tmp_path: Path
    ) -> None:
        inbox = stock_inbox(removal_world, tmp_path / "pulled")
        broken = inbox / weekly_inbox_name(date(2026, 9, 29))
        broken.write_bytes(b"PK\x03\x04 not really a zip")

        _, plan = await plan_team(removal_world)
        (unreadable,) = [one for one in plan.inbox if one.action is InboxAction.UNREADABLE]
        assert unreadable.name == broken.name and unreadable.reason is InboxReason.CANNOT_BE_READ

        with pytest.raises(RemovalIncomplete) as stopped:
            await removal_world.service().execute(plan)
        assert broken.name in str(stopped.value) and broken.exists()

        broken.unlink()  # the operator moves it out, as the message says
        await remove_team(removal_world)
        assert [entry.outcome for entry in log_entries(removal_world)] == [
            RemovalOutcome.INCOMPLETE,
            RemovalOutcome.COMPLETED,
        ]


def test_the_inbox_is_a_required_argument_with_no_default() -> None:
    """No removal can be built that forgets the inbox, as no import can forget the list (v1-e30-t07)."""
    import inspect

    from debate_core.application.caselist.removal_plan import RemovalPlanner

    planner = inspect.signature(RemovalPlanner).parameters["inbox"]
    assert planner.default is inspect.Parameter.empty
    service = inspect.signature(CaselistRemovalService).parameters["inbox"]
    assert service.default is inspect.Parameter.empty


# ------------------------------------------------------------------------------------------------
# The checks before a file is changed
# ------------------------------------------------------------------------------------------------


class RewriterThatKeepsTooMuch:
    """A rewriter with a bug: it writes every entry, the removed ones included."""

    def __init__(self) -> None:
        self._real = ZipArchiveRewriter(**LIMITS)

    def inventory(self, source: Path) -> tuple[InventoriedEntry, ...]:
        return self._real.inventory(source)

    def rewrite_without(
        self, source: Path, destination: Path, *, drop: Collection[str], comment: bytes
    ) -> None:
        self._real.rewrite_without(source, destination, drop=(), comment=comment)


class TestTheChecksBeforeAFileIsChanged:
    async def test_a_rewrite_that_does_not_read_back_as_planned_is_not_put_in_place(
        self, removal_world: RemovalWorld, tmp_path: Path
    ) -> None:
        inbox = stock_inbox(removal_world, tmp_path / "pulled")
        waiting = add_next_mondays_archive(inbox)
        before = waiting.read_bytes()
        service = removal_world.service()
        service.inbox = CaselistInbox(
            directory=inbox, state_dir=removal_world.data_dir, archives=RewriterThatKeepsTooMuch()
        )

        with pytest.raises(RemovalIncomplete) as stopped:
            await remove_team(removal_world, service=service)

        assert "could not be rewritten" in str(stopped.value)
        assert waiting.read_bytes() == before
        assert [path.name for path in inbox.iterdir() if path.name.startswith(".")] == [], "no staging left"

    async def test_a_file_that_changed_after_the_plan_is_not_touched(
        self, removal_world: RemovalWorld, tmp_path: Path
    ) -> None:
        inbox = stock_inbox(removal_world, tmp_path / "pulled")
        remover, plan = await plan_team(removal_world)
        changed = inbox / weekly_inbox_name(date(2026, 9, 8))
        changed.write_bytes(next_mondays_archive())  # a different archive under the planned name

        with pytest.raises(RemovalIncomplete) as stopped:
            await remover.execute(plan)

        assert changed.name in str(stopped.value)
        assert changed.read_bytes() == next_mondays_archive()
