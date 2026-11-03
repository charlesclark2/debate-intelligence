"""A removal withdraws one camp path, and the release still holding the bytes keeps them (`v1-e30-t14` ac2).

A camp file's later upload at a removed camp path is in the plan (`v1-e30-t11`). When another holder
has the same bytes, a caselist path is withdrawn: its rows and records go, and one disclosure-scoped
suppression entry stops that path while the other holder keeps the blob. A camp path could not be
withdrawn that way, because no entry of the list stopped one camp path of a file, so the later
upload was kept whole (t11's Decision 6). Now it is withdrawn as a caselist path is:

* its row in the release manifest goes, here and in the bucket, and so does that release's
  camp-file record when no other row of the release holds the bytes;
* the release's year's `raw/openev/<year>/` copy goes when no other release of that year holds them,
  every version;
* the list gains one entry, the file's sha256 with the digest of `openev/<release>/<row path>` as its
  disclosure: the scope `disclosure_digest(caselist, path)` gives a caselist path, with the release
  in the path because a release manifest is the camp's caselist;
* the withdrawal record says `openev` (`v1-e30-t16`), joined to that entry as any withdrawal is;
* the blob, the source record, and the other holder's row, record and objects stay.

The OpenEv importer and the pull then honour the entry: the same download is refused at that camp
path, and the pull does not fetch it again, while the other release imports the same bytes as before.

The worlds are built by the real pull, through the helpers of the `v1-e34-t07`, `t08` and
`v1-e30-t11` tests, on the synthetic camp files of `tests/fixtures/openev/`:

| OpenEv id | Release | Upstream path | Bytes |
|---|---|---|---|
| 512 | 2026-policy | `openev/2026/Tamarack/TSF-Estuary Solvency Advocate.docx` | `estuary-solvency` |
| 640 | 2026-policy | the same path, uploaded again | `canal-counterplan-revised` |
| 800 | 2027-policy | `openev/2027/Juniper/JDI-Canal Counterplan.docx` | `canal-counterplan-revised` |

Removing 512's bytes takes 640 down as a later upload. 800 holds the same bytes in another
release, so 640 is withdrawn from its camp path in 2026-policy and 2027-policy keeps them. Every
expected value is written out from that table.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from tests.fixtures.openev.build_synthetic_openev import DOCUMENT_BODIES

from debate_core.application.caselist.manifest import read_manifest_lines, write_manifest_lines
from debate_core.application.caselist.openev_import_service import OpenEvImportService
from debate_core.application.caselist.openev_manifest import openev_manifest_key
from debate_core.application.caselist.pipeline import Classification
from debate_core.application.caselist.removal_plan import (
    Disposition,
    Inclusion,
    LaterUploadOutcome,
    RemovalPlan,
    SourceSelector,
)
from debate_core.application.caselist.removal_service import RemovalIncomplete
from debate_core.application.caselist.status_service import CaselistStatusService
from debate_core.application.caselist.suppression import caselist_withdrawn_from, caselists_withdrawn_by
from debate_core.application.caselist_sync import OPENEV_DELIVERIES_FILENAME, SelectionDecision
from debate_core.application.ports.archive import ArchiveMember
from debate_core.application.ports.caselist_source import OpenEvFile
from debate_core.application.ports.suppression import ReasonCode, RemovalLogEntry, WithdrawalEntry
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsEvidenceObjectStore, FsSnapshotStore
from debate_core.testing.fakes.suppression import empty_suppression_list

from .conftest import REQUEST, RemovalWorld
from .test_removal_covers_later_camp_uploads import (
    NEW_ROW,
    RELEASE,
    RELEASE_KEY,
    REVISED_SHA256,
    TEAM_PATH,
    a_team_discloses_the_revised_camp_file,
    pulled_then_revised,
    raw_key,
    release_rows,
)
from .test_removal_covers_later_uploads import suppression_lines, versions_of
from .test_removal_later_uploads_plan import RecordsThatFailAfter
from .test_sync_fetches_revised_camp_files import REVISED_BODY, REVISION
from .test_sync_skips_suppressed_downloads import CASELIST, ESTUARY_SHA256, PULLED_AT, decisions, pull

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

#: The same bytes as 640, released the next year by another camp: the release that keeps them.
NEXT_YEAR = OpenEvFile(
    openev_id=800,
    path="openev/2027/Juniper/JDI-Canal Counterplan.docx",
    filename="JDI-Canal Counterplan.docx",
    year=2027,
    tags=("policy",),
)
NEXT_YEAR_ROW = "openev-800-JDI-Canal_Counterplan.docx"
NEXT_RELEASE_KEY = openev_manifest_key(2027, Event.POLICY)

#: The suppression entry's disclosure for 640's camp path: `disclosure_digest("openev", "<release>/<row>")`.
CAMP_PATH_DISCLOSURE = hashlib.sha256(f"openev/{RELEASE}/{NEW_ROW}".encode()).hexdigest()


@pytest.fixture
def world(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> RemovalWorld:
    return RemovalWorld(data_dir=tmp_path / "evidence", bucket_name=evidence_bucket, client=s3_client)


def rows_of(world: RemovalWorld, key: str) -> list[dict[str, str]]:
    """A release manifest's member rows, `{path: sha256}`, on this machine and in the bucket."""
    local = read_manifest_lines(FsEvidenceObjectStore(world.data_dir).path_for(key))
    bucket = world.client.get_object(Bucket=world.bucket_name, Key=key)["Body"].read().decode()
    return [
        {row["path"]: row["sha256"] for row in map(json.loads, lines) if row["kind"] == "member"}
        for lines in (local, bucket.splitlines())
    ]


def openev_raw_key(year: int, digest: str) -> str:
    return f"raw/openev/{year}/sha256/{digest[:2]}/{digest[2:4]}/{digest}"


async def camp_releases_of(world: RemovalWorld, digest: str) -> list[tuple[int, Event]]:
    page = await world.repository.list_camp_files(source_sha256=digest, limit=10)
    return sorted((one.year, one.event) for one in page.items)


def withdrawal_lines(world: RemovalWorld) -> list[list[dict[str, object]]]:
    """The withdrawal record on this machine and in the bucket, each line as written."""
    local = world.data_dir / "suppression" / "withdrawals.jsonl"
    key = "manifests/_suppression/withdrawals.jsonl"
    copies = [local.read_text() if local.exists() else ""]
    listed = world.client.list_objects_v2(Bucket=world.bucket_name, Prefix=key).get("Contents", [])
    copies.append(
        world.client.get_object(Bucket=world.bucket_name, Key=key)["Body"].read().decode() if listed else ""
    )
    return [[json.loads(line) for line in copy.splitlines() if line.strip()] for copy in copies]


async def plan_removal(world: RemovalWorld) -> RemovalPlan:
    return await world.service().plan(
        SourceSelector(ESTUARY_SHA256), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_CAMP
    )


async def remove(world: RemovalWorld) -> RemovalPlan:
    plan = await plan_removal(world)
    assert (await world.service().execute(plan)).completed
    return plan


async def another_release_holds_the_later_upload(world: RemovalWorld) -> Any:
    """512 pulled; then 640 at its camp path and 800 in 2027-policy, holding 640's bytes. The fake source."""
    source = await pulled_then_revised(world, (NEXT_YEAR, REVISED_BODY))
    assert rows_of(world, NEXT_RELEASE_KEY) == [{NEXT_YEAR_ROW: REVISED_SHA256}] * 2
    assert await camp_releases_of(world, REVISED_SHA256) == [(2026, Event.POLICY), (2027, Event.POLICY)]
    return source


# ------------------------------------------------------------------------------------------------
# What the removal does
# ------------------------------------------------------------------------------------------------


async def test_the_later_upload_another_release_holds_is_withdrawn_from_its_camp_path_only(
    world: RemovalWorld,
) -> None:
    await another_release_holds_the_later_upload(world)
    kept_release = read_manifest_lines(FsEvidenceObjectStore(world.data_dir).path_for(NEXT_RELEASE_KEY))
    world.client.put_object(
        Bucket=world.bucket_name, Key=openev_raw_key(2026, REVISED_SHA256), Body=REVISED_BODY
    )
    assert len(versions_of(world, openev_raw_key(2026, REVISED_SHA256))) == 2

    await remove(world)

    assert release_rows(world) == [{}, {}], "512 removed, and 640's row withdrawn, on both sides"
    assert rows_of(world, NEXT_RELEASE_KEY) == [{NEXT_YEAR_ROW: REVISED_SHA256}] * 2
    assert (
        read_manifest_lines(FsEvidenceObjectStore(world.data_dir).path_for(NEXT_RELEASE_KEY)) == kept_release
    ), "the release that keeps it is not rewritten"
    assert await camp_releases_of(world, REVISED_SHA256) == [(2027, Event.POLICY)]
    assert await world.repository.find_source(REVISED_SHA256) is not None
    assert FsSnapshotStore(world.data_dir).path_for(REVISED_SHA256).read_bytes() == REVISED_BODY
    assert versions_of(world, openev_raw_key(2026, REVISED_SHA256)) == [], "every version of 2026's copy"
    assert len(versions_of(world, openev_raw_key(2027, REVISED_SHA256))) == 1


async def test_its_suppression_entry_is_scoped_to_the_camp_path_as_a_caselist_paths_withdrawal_is(
    world: RemovalWorld,
) -> None:
    await another_release_holds_the_later_upload(world)

    await remove(world)

    for entries in suppression_lines(world):
        assert {(entry.sha256, entry.disclosure) for entry in entries} == {
            (ESTUARY_SHA256, None),
            (REVISED_SHA256, CAMP_PATH_DISCLOSURE),
        }


async def test_the_withdrawal_record_says_openev_and_joins_the_entry_and_the_log_as_t16s_do(
    world: RemovalWorld,
) -> None:
    await another_release_holds_the_later_upload(world)

    await remove(world)

    for lines in withdrawal_lines(world):
        assert [
            (line["sha256"], line["disclosure"], line["caselist"], line["request_id"], line["reason"])
            for line in lines
        ] == [(REVISED_SHA256, CAMP_PATH_DISCLOSURE, "openev", REQUEST, "REQUESTED_BY_CAMP")]
    withdrawals = await world.suppression().withdrawals()
    (scoped,) = [entry for entry in await world.suppression().entries() if entry.disclosure is not None]
    assert caselist_withdrawn_from(scoped, withdrawals) == "openev"
    log = world.data_dir / "suppression" / "removal-log.jsonl"
    (entry,) = [RemovalLogEntry.from_line(line) for line in log.read_text().splitlines()]
    assert entry.withdrawn_sha256 == (REVISED_SHA256,) and entry.removed_sha256 == (ESTUARY_SHA256,)
    assert caselists_withdrawn_by(entry, withdrawals) == {REVISED_SHA256: ("openev",)}
    assert all(isinstance(one, WithdrawalEntry) for one in withdrawals)


async def test_the_next_pull_neither_fetches_nor_imports_it_at_that_camp_path_again(
    world: RemovalWorld,
) -> None:
    source = await another_release_holds_the_later_upload(world)
    assert source.openev_fetches == [512, 640, 800]
    await remove(world)

    summary = await pull(world, source)

    assert source.openev_fetches == [512, 640, 800], "640 was fetched again"
    assert decisions(summary)[640] is SelectionDecision.SKIPPED_AS_REMOVED
    assert release_rows(world) == [{}, {}]
    assert rows_of(world, NEXT_RELEASE_KEY) == [{NEXT_YEAR_ROW: REVISED_SHA256}] * 2


async def test_its_download_imported_again_is_refused_at_that_camp_path_and_imports_in_the_other_release(
    world: RemovalWorld,
) -> None:
    """The scope is the camp path: the same bytes at the other release's row still import there."""
    await another_release_holds_the_later_upload(world)
    await remove(world)
    importer = OpenEvImportService(
        caselists=world.repository, blobs=FsSnapshotStore(world.data_dir), suppression=world.suppression()
    )

    def download(path: str) -> list[ArchiveMember]:
        body = REVISED_BODY
        return [ArchiveMember(path=path, sha256=REVISED_SHA256, byte_size=len(body), data=body)]

    here = await importer.import_release(
        download(NEW_ROW),
        year=2026,
        event=Event.POLICY,
        imported_on=PULLED_AT.date(),
        archive_sha256=REVISED_SHA256,
        recorded_manifest=read_manifest_lines(FsEvidenceObjectStore(world.data_dir).path_for(RELEASE_KEY)),
        dry_run=True,
    )
    there = await importer.import_release(
        download(NEXT_YEAR_ROW),
        year=2027,
        event=Event.POLICY,
        imported_on=PULLED_AT.date(),
        archive_sha256=REVISED_SHA256,
        recorded_manifest=read_manifest_lines(
            FsEvidenceObjectStore(world.data_dir).path_for(NEXT_RELEASE_KEY)
        ),
        dry_run=True,
    )

    assert (here.count(Classification.SUPPRESSED), _member_paths(here.manifest_lines)) == (1, [])
    assert (there.count(Classification.UNCHANGED), _member_paths(there.manifest_lines)) == (
        1,
        [NEXT_YEAR_ROW],
    )


def _member_paths(lines: tuple[str, ...]) -> list[str]:
    return [row["path"] for row in map(json.loads, lines) if row["kind"] == "member"]


async def test_a_later_upload_a_team_disclosed_too_is_withdrawn_from_its_camp_path_and_kept_for_the_team(
    world: RemovalWorld, tmp_path: Path
) -> None:
    await pulled_then_revised(world)
    await a_team_discloses_the_revised_camp_file(world, tmp_path / "weekly")
    team_raw = f"raw/caselist/{CASELIST}/sha256/{REVISED_SHA256[:2]}/{REVISED_SHA256[2:4]}/{REVISED_SHA256}"

    await remove(world)

    assert release_rows(world) == [{}, {}]
    assert await camp_releases_of(world, REVISED_SHA256) == []
    kept = (await world.repository.list_disclosures(source_sha256=REVISED_SHA256, limit=5)).items
    assert [one.source_path for one in kept] == [TEAM_PATH]
    assert FsSnapshotStore(world.data_dir).path_for(REVISED_SHA256).read_bytes() == REVISED_BODY
    assert versions_of(world, raw_key(REVISED_SHA256)) == []
    assert len(versions_of(world, team_raw)) == 1
    for entries in suppression_lines(world):
        assert {(entry.sha256, entry.disclosure) for entry in entries} == {
            (ESTUARY_SHA256, None),
            (REVISED_SHA256, CAMP_PATH_DISCLOSURE),
        }


# ------------------------------------------------------------------------------------------------
# What the plan says
# ------------------------------------------------------------------------------------------------


async def test_the_plan_withdraws_it_from_the_camp_path_and_says_the_other_release_keeps_it(
    world: RemovalWorld,
) -> None:
    await another_release_holds_the_later_upload(world)

    plan = await plan_removal(world)

    (later,) = plan.later_uploads
    assert plan.later_upload_outcome(later) is LaterUploadOutcome.WITHDRAWN_FROM_THE_PATH
    withdrawn = plan.source(REVISED_SHA256)
    assert withdrawn is not None
    assert (withdrawn.inclusion, withdrawn.disposition) == (Inclusion.LATER_UPLOAD, Disposition.WITHDRAW)
    assert (withdrawn.kept_in, withdrawn.camp_file_holders, withdrawn.other_teams) == (("openev",), 1, 0)
    assert [(ref.year, ref.event) for ref in withdrawn.camp_files] == [(2026, Event.POLICY)]
    assert [(entry.sha256, entry.disclosure) for entry in withdrawn.suppression] == [
        (REVISED_SHA256, CAMP_PATH_DISCLOSURE)
    ]
    assert [(one.caselist, one.disclosure) for one in plan.withdrawals] == [("openev", CAMP_PATH_DISCLOSURE)]
    assert (plan.later_uploads_found, plan.later_uploads_added) == (1, 1)
    assert plan.path_holds == (), "a camp path is held by the pull, not by a path entry"


async def test_only_named_still_leaves_the_later_upload_where_it_is(world: RemovalWorld) -> None:
    await another_release_holds_the_later_upload(world)

    plan = await world.service().plan(
        SourceSelector(ESTUARY_SHA256),
        request_id=REQUEST,
        reason=ReasonCode.REQUESTED_BY_CAMP,
        only_named=True,
    )
    assert (await world.service().execute(plan)).completed

    assert plan.source(REVISED_SHA256) is None and plan.withdrawals == ()
    assert release_rows(world) == [{NEW_ROW: REVISED_SHA256}] * 2
    assert await camp_releases_of(world, REVISED_SHA256) == [(2026, Event.POLICY), (2027, Event.POLICY)]


async def test_a_run_stopped_among_the_records_leaves_the_camp_file_record_and_a_rerun_takes_it(
    world: RemovalWorld,
) -> None:
    """The manifests are rewritten by then, so only the list and the record say what was left.

    The removal deletes records last: 512's camp-file record and source document, then 640's
    camp-file record for 2026-policy. Stopped after the first two, the third is left, and no row
    shows 640 at its camp path any more. The same command plans it again and takes it.
    """
    await another_release_holds_the_later_upload(world)
    stopped = world.service()
    stopped.caselists = RecordsThatFailAfter(world.repository, 2)  # type: ignore[assignment]
    with pytest.raises(RemovalIncomplete):
        await stopped.execute(await plan_removal(world))
    assert await camp_releases_of(world, REVISED_SHA256) == [(2026, Event.POLICY), (2027, Event.POLICY)]

    again = await plan_removal(world)

    assert again.later_uploads == ()
    unfinished = again.source(REVISED_SHA256)
    assert unfinished is not None
    assert (unfinished.inclusion, unfinished.disposition) == (Inclusion.UNFINISHED, Disposition.WITHDRAW)
    assert [(ref.year, ref.event) for ref in unfinished.camp_files] == [(2026, Event.POLICY)]
    assert again.suppression_entries == () and again.withdrawals == ()
    assert (await world.service().execute(again)).completed
    assert await camp_releases_of(world, REVISED_SHA256) == [(2027, Event.POLICY)]
    assert await world.repository.find_source(REVISED_SHA256) is not None


async def test_an_import_with_no_list_entry_still_imports_it_at_that_camp_path(world: RemovalWorld) -> None:
    """The control: what the importer refuses above is refused because of the entry, not the bytes."""
    await another_release_holds_the_later_upload(world)
    importer = OpenEvImportService(
        caselists=world.repository,
        blobs=FsSnapshotStore(world.data_dir),
        suppression=empty_suppression_list(),
    )
    body = REVISED_BODY
    report = await importer.import_release(
        [ArchiveMember(path=NEW_ROW, sha256=REVISED_SHA256, byte_size=len(body), data=body)],
        year=2026,
        event=Event.POLICY,
        imported_on=PULLED_AT.date(),
        archive_sha256=REVISED_SHA256,
        dry_run=True,
    )
    assert report.count(Classification.SUPPRESSED) == 0
    assert _member_paths(report.manifest_lines) == [NEW_ROW]


async def test_a_row_an_older_build_records_again_is_taken_by_running_the_same_removal_again(
    world: RemovalWorld,
) -> None:
    """Until the weekly agent runs this build, its pull may record the withdrawn id at its camp path
    again: a build from before `v1-e30-t14` asks the list about the whole file only. Here that import
    is made with no list at all, which is what such a build's importer sees of a camp-path entry.
    The same removal, run again, finds the row by its entry and takes it, its record and its copy.
    """
    await another_release_holds_the_later_upload(world)
    await remove(world)
    older = OpenEvImportService(
        caselists=world.repository,
        blobs=FsSnapshotStore(world.data_dir),
        suppression=empty_suppression_list(),
    )
    path = FsEvidenceObjectStore(world.data_dir).path_for(RELEASE_KEY)
    body = REVISED_BODY
    report = await older.import_release(
        [ArchiveMember(path=NEW_ROW, sha256=REVISED_SHA256, byte_size=len(body), data=body)],
        year=2026,
        event=Event.POLICY,
        imported_on=PULLED_AT.date(),
        archive_sha256=REVISED_SHA256,
        recorded_manifest=read_manifest_lines(path),
    )
    write_manifest_lines(report.manifest_lines, path)
    world.client.put_object(Bucket=world.bucket_name, Key=RELEASE_KEY, Body=path.read_bytes())
    world.client.put_object(
        Bucket=world.bucket_name, Key=openev_raw_key(2026, REVISED_SHA256), Body=REVISED_BODY
    )
    assert release_rows(world) == [{NEW_ROW: REVISED_SHA256}] * 2
    assert await camp_releases_of(world, REVISED_SHA256) == [(2026, Event.POLICY), (2027, Event.POLICY)]
    status = await CaselistStatusService(
        local=world.local, remote=world.bucket, suppression=world.suppression()
    ).status("openev")
    assert {one.snapshot: one.suppressed_rows for one in status.snapshots}[RELEASE] == (REVISED_SHA256,), (
        "status names the row at the withdrawn camp path, and the publisher refuses it"
    )

    again = await plan_removal(world)

    unfinished = again.source(REVISED_SHA256)
    assert unfinished is not None
    assert (unfinished.inclusion, unfinished.disposition) == (Inclusion.UNFINISHED, Disposition.WITHDRAW)
    assert again.suppression_entries == ()
    assert (await world.service().execute(again)).completed
    assert release_rows(world) == [{}, {}]
    assert await camp_releases_of(world, REVISED_SHA256) == [(2027, Event.POLICY)]
    assert versions_of(world, openev_raw_key(2026, REVISED_SHA256)) == []
    assert rows_of(world, NEXT_RELEASE_KEY) == [{NEXT_YEAR_ROW: REVISED_SHA256}] * 2


async def test_its_download_is_taken_out_of_the_inbox_and_the_record_of_what_it_delivered_stays(
    world: RemovalWorld,
) -> None:
    """The withdrawn copy leaves the inbox as a removed one does; 800's download is another file."""
    await another_release_holds_the_later_upload(world)
    inbox = world.data_dir / "inbox"
    assert sorted(path.name for path in inbox.iterdir() if path.is_file()) == [
        "openev-512-TSF-Estuary_Solvency_Advocate.docx",
        NEW_ROW,
        NEXT_YEAR_ROW,
    ]

    plan = await remove(world)

    assert sorted((one.name, one.action.value, str(one.reason)) for one in plan.inbox) == [
        ("openev-512-TSF-Estuary_Solvency_Advocate.docx", "delete", "the file itself is removed"),
        (NEW_ROW, "delete", "its camp path is withdrawn: another holder keeps the bytes"),
    ]
    assert sorted(path.name for path in inbox.iterdir() if path.is_file()) == [NEXT_YEAR_ROW]
    deliveries = json.loads((world.data_dir / OPENEV_DELIVERIES_FILENAME).read_text())["deliveries"]
    assert deliveries["640"]["member_sha256"] == [REVISED_SHA256]


# ------------------------------------------------------------------------------------------------
# What the mutation run called for
# ------------------------------------------------------------------------------------------------

#: 640's bytes at another camp's path in the same release: the release keeps them.
SAME_RELEASE = OpenEvFile(
    openev_id=701,
    path="openev/2026/Quillfeather/QDI-Canal Counterplan.docx",
    filename="QDI-Canal Counterplan.docx",
    year=2026,
    tags=("policy",),
)
SAME_RELEASE_ROW = "openev-701-QDI-Canal_Counterplan.docx"


async def test_a_camp_path_withdrawn_where_another_row_of_its_release_holds_the_file_keeps_record_and_copy(
    world: RemovalWorld,
) -> None:
    """One camp-file record and one `raw/openev/2026/` copy serve both rows: the other row keeps them."""
    await pulled_then_revised(world, (SAME_RELEASE, REVISED_BODY))
    assert (
        release_rows(world)
        == [
            {
                "openev-512-TSF-Estuary_Solvency_Advocate.docx": ESTUARY_SHA256,
                NEW_ROW: REVISED_SHA256,
                SAME_RELEASE_ROW: REVISED_SHA256,
            }
        ]
        * 2
    )

    plan = await remove(world)

    withdrawn = plan.source(REVISED_SHA256)
    assert withdrawn is not None and (withdrawn.disposition, withdrawn.camp_files) == (
        Disposition.WITHDRAW,
        (),
    )
    assert release_rows(world) == [{SAME_RELEASE_ROW: REVISED_SHA256}] * 2
    assert await camp_releases_of(world, REVISED_SHA256) == [(2026, Event.POLICY)]
    assert len(versions_of(world, openev_raw_key(2026, REVISED_SHA256))) == 1
    for entries in suppression_lines(world):
        assert {(entry.sha256, entry.disclosure) for entry in entries} == {
            (ESTUARY_SHA256, None),
            (REVISED_SHA256, CAMP_PATH_DISCLOSURE),
        }


async def test_a_row_carried_forward_at_a_withdrawn_camp_path_is_dropped_and_a_rerun_sweeps_its_old_version(
    world: RemovalWorld,
) -> None:
    """An older build records the row again and publishes it; this build's next import of the release
    drops it rather than refusing to write the manifest, and publishes. The version with the row is
    then noncurrent, and the same removal run again deletes it with the record the older import made."""
    await another_release_holds_the_later_upload(world)
    await remove(world)
    path = FsEvidenceObjectStore(world.data_dir).path_for(RELEASE_KEY)
    body = REVISED_BODY
    older = await OpenEvImportService(
        caselists=world.repository,
        blobs=FsSnapshotStore(world.data_dir),
        suppression=empty_suppression_list(),
    ).import_release(
        [ArchiveMember(path=NEW_ROW, sha256=REVISED_SHA256, byte_size=len(body), data=body)],
        year=2026,
        event=Event.POLICY,
        imported_on=PULLED_AT.date(),
        archive_sha256=REVISED_SHA256,
        recorded_manifest=read_manifest_lines(path),
    )
    write_manifest_lines(older.manifest_lines, path)
    world.client.put_object(Bucket=world.bucket_name, Key=RELEASE_KEY, Body=path.read_bytes())

    other = DOCUMENT_BODIES["harbor-tariffs-neg"]
    other_sha256 = hashlib.sha256(other).hexdigest()
    report = await OpenEvImportService(
        caselists=world.repository, blobs=FsSnapshotStore(world.data_dir), suppression=world.suppression()
    ).import_release(
        [
            ArchiveMember(
                path="openev-900-JDI-Harbor_Tariffs_Neg.docx",
                sha256=other_sha256,
                byte_size=len(other),
                data=other,
            )
        ],
        year=2026,
        event=Event.POLICY,
        imported_on=PULLED_AT.date(),
        archive_sha256=other_sha256,
        recorded_manifest=read_manifest_lines(path),
    )
    write_manifest_lines(report.manifest_lines, path)
    world.client.put_object(Bucket=world.bucket_name, Key=RELEASE_KEY, Body=path.read_bytes())
    assert release_rows(world) == [{"openev-900-JDI-Harbor_Tariffs_Neg.docx": other_sha256}] * 2
    assert sum(NEW_ROW in body for body in manifest_versions(world)) == 1, "the older build's version"

    again = await plan_removal(world)
    assert (await world.service().execute(again)).completed

    assert not [body for body in manifest_versions(world) if NEW_ROW in body]
    assert await camp_releases_of(world, REVISED_SHA256) == [(2027, Event.POLICY)]


def manifest_versions(world: RemovalWorld) -> list[str]:
    """Every version of the 2026 release manifest in the bucket, current and noncurrent."""
    listed = world.client.list_object_versions(Bucket=world.bucket_name, Prefix=RELEASE_KEY).get(
        "Versions", []
    )
    return [
        world.client.get_object(
            Bucket=world.bucket_name, Key=RELEASE_KEY, VersionId=str(one.get("VersionId"))
        )["Body"]
        .read()
        .decode()
        for one in listed
        if one.get("Key") == RELEASE_KEY
    ]


async def test_a_file_at_the_withdrawn_downloads_name_with_other_bytes_stays_in_the_inbox(
    world: RemovalWorld,
) -> None:
    """The inbox step takes the copy by its name and its bytes, so it never deletes what it did not plan."""
    await another_release_holds_the_later_upload(world)
    inbox = world.data_dir / "inbox"
    (inbox / NEW_ROW).write_bytes(b"not the bytes the removal withdrew")

    plan = await remove(world)

    assert NEW_ROW not in [one.name for one in plan.inbox]
    assert (inbox / NEW_ROW).read_bytes() == b"not the bytes the removal withdrew"


async def test_a_new_id_at_the_withdrawn_camp_path_is_held_by_the_pulls_hold_on_the_removed_files_path(
    world: RemovalWorld,
) -> None:
    """A camp path is withdrawn only as a later upload of a file removed whole, at that file's upstream
    path. The pull's hold (`v1-e34-t14`) already holds a new id there, so a third upload is not fetched."""
    source = await another_release_holds_the_later_upload(world)
    await remove(world)
    third = REVISION.model_copy(update={"openev_id": 641})
    source.files = [*source.files, (third, DOCUMENT_BODIES["harbor-tariffs-neg"])]

    summary = await pull(world, source)

    assert decisions(summary)[641] is SelectionDecision.SAME_PATH_AS_A_REMOVED_FILE
    assert 641 not in source.openev_fetches
