"""A camp release manifest this build writes is read by older builds, and theirs by it (`v1-e30-t14` ac3).

`stored_camp_manifests/` holds the release manifest the same history leaves, written by each build's
own pull: the build the weekly agent is installed from (`v0.1.0-dev.122`), this task's start commit,
and this build. What an older build's code does with this build's file is
`check_an_older_build_reads_this_builds_camp_manifests.py`'s, run by its path against that build's
source; its output is in the README. This module holds the other direction, and the stored files to
what they say they are:

* the older builds wrote the same rows, byte for byte once the two keys are taken off, and the same
  summary row, so the two keys are the whole difference, with the listing's camp word
  (`v1-e30-t31`), which this build's rows carry as a third;
* this build's pull, removal plan, re-derive, publish and status read an older build's manifest, and
  keep its rows byte for byte where they kept them before;
* the stored file of this build is what its pull writes now.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from debate_core.application.caselist.openev_import_service import OpenEvImportService
from debate_core.application.caselist.openev_metadata_reimport import DERIVED_FIELDS
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.removal_path_versions import SamePathEvidence
from debate_core.application.caselist.removal_plan import RemovalPlan, SourceSelector
from debate_core.application.caselist.status_service import CaselistStatusService
from debate_core.application.caselist.suppression import caselist_withdrawn_from
from debate_core.application.caselist_sync import (
    OPENEV_DELIVERIES_FILENAME,
    OpenEvDeliveries,
    SelectionDecision,
)
from debate_core.application.ports.suppression import ReasonCode, SuppressionEntry, WithdrawalEntry
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsSnapshotStore

from .camp_manifest_scenario import (
    MANIFEST_NAME,
    NEXT_WEEK,
    NEXT_WEEK_BODY,
    NEXT_WEEK_ROW,
    OTHER_CAMP,
    OTHER_CAMP_BODY,
    RELEASE_KEY,
    REVISED_BODY,
    REVISION,
    ROWS,
    STORED,
    release_lines,
    release_manifest,
    two_pulls,
)
from .conftest import REQUEST, RemovalWorld
from .test_camp_rows_carry_upstream_identity import QUILLFEATHER_PATH_SHA256, TAMARACK_PATH_SHA256
from .test_sync_skips_suppressed_downloads import ESTUARY_SHA256, FakeOpenEvSource, decisions, pull

pytestmark = pytest.mark.anyio

IDENTITY = ("openev_id", "upstream_path_sha256")
CAMP_WORD = "openev_camp_word"
#: Every key this build's rows carry and the older builds' rows do not.
ADDED = (*IDENTITY, CAMP_WORD)
OLDER_BUILDS = ("written_by_the_installed_build", "written_by_the_start_commit")
THIS_BUILD = STORED / "written_by_this_build" / MANIFEST_NAME

#: The identity each row of this build's stored file carries, written out from the history: the
#: three pulled rows, the hand-imported file the fixture names `openev-417-…`, and `null` for the rest.
PULLED_IDENTITY = {
    ROWS[0]: (512, TAMARACK_PATH_SHA256),
    ROWS[1]: (640, TAMARACK_PATH_SHA256),
    ROWS[2]: (700, QUILLFEATHER_PATH_SHA256),
    "openev-417-TSF-Spillway Advantage.docx": (417, None),
}

#: The camp word each pulled row of this build's stored file carries, from the history's listings:
#: their upstream paths' camp folders. The hand-imported rows carry `null`.
PULLED_WORDS = {ROWS[0]: "Tamarack", ROWS[1]: "Tamarack", ROWS[2]: "Quillfeather"}


def rows(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def without_the_keys(row: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in row.items() if key not in ADDED}


def by_path(lines: list[str]) -> dict[str, str]:
    return {json.loads(line)["path"]: line for line in lines if json.loads(line)["kind"] == "member"}


async def placed(world: RemovalWorld, written_by: str) -> list[str]:
    """This build's history, then an older build's manifest of it in its place, here and in the bucket."""
    await two_pulls(world)
    body = (STORED / written_by / MANIFEST_NAME).read_bytes()
    release_manifest(world).write_bytes(body)
    world.client.put_object(Bucket=world.bucket_name, Key=RELEASE_KEY, Body=body)
    return release_lines(world)


async def plan_512(world: RemovalWorld) -> RemovalPlan:
    return await world.service().plan(
        SourceSelector(ESTUARY_SHA256), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_CAMP
    )


# ------------------------------------------------------------------------------------------------
# The stored files
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("written_by", OLDER_BUILDS)
def test_an_older_build_wrote_the_same_rows_and_summary_without_the_two_keys(written_by: str) -> None:
    theirs, mine = rows(STORED / written_by / MANIFEST_NAME), rows(THIS_BUILD)

    assert [without_the_keys(row) for row in mine] == theirs
    assert not [row for row in theirs if set(ADDED) & set(row)]
    assert mine[-1] == theirs[-1] and mine[-1]["kind"] == "summary", "the summary row is unchanged"


def test_every_member_row_this_build_wrote_carries_the_keys_and_the_pulled_ones_their_values() -> None:
    members = [row for row in rows(THIS_BUILD) if row["kind"] == "member"]

    assert all(set(ADDED) <= set(row) for row in members)
    assert {str(row["path"]): row[CAMP_WORD] for row in members if row[CAMP_WORD] is not None} == PULLED_WORDS
    assert {
        str(row["path"]): (row["openev_id"], row["upstream_path_sha256"])
        for row in members
        if row["openev_id"] is not None or row["upstream_path_sha256"] is not None
    } == PULLED_IDENTITY


async def test_the_stored_file_is_what_this_builds_pull_writes_now(removal_world: RemovalWorld) -> None:
    await two_pulls(removal_world)

    assert release_manifest(removal_world).read_bytes() == THIS_BUILD.read_bytes()


def test_the_stored_withdrawal_records_attribute_the_camp_path_to_openev() -> None:
    """What a camp path's withdrawal leaves, which the check script gives to the older builds."""
    stored = STORED / "written_by_this_build" / "suppression"
    entries = [
        SuppressionEntry.from_line(line) for line in (stored / "suppression-list.jsonl").read_text().split()
    ]
    withdrawals = [
        WithdrawalEntry.from_line(line) for line in (stored / "withdrawals.jsonl").read_text().split()
    ]

    (scoped,) = [entry for entry in entries if entry.disclosure is not None]
    assert caselist_withdrawn_from(scoped, withdrawals) == "openev"
    assert [entry.sha256 for entry in entries if entry.disclosure is None] == [ESTUARY_SHA256]


# ------------------------------------------------------------------------------------------------
# This build, reading an older build's manifest
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("written_by", OLDER_BUILDS)
async def test_this_builds_pull_reads_it_and_keeps_its_rows_byte_for_byte(
    removal_world: RemovalWorld, written_by: str
) -> None:
    world = removal_world
    theirs = by_path(await placed(world, written_by))
    source = next_weeks_listing()

    summary = await pull(world, source)

    assert decisions(summary) == {
        640: SelectionDecision.ALREADY_IMPORTED,
        700: SelectionDecision.ALREADY_IMPORTED,
        900: SelectionDecision.DOWNLOAD,
    }
    merged = by_path(release_lines(world))
    assert {path: merged[path] for path in theirs} == theirs
    new_row = json.loads(merged[NEXT_WEEK_ROW])
    assert (new_row["openev_id"], new_row.get(CAMP_WORD), len(merged)) == (900, "Juniper", len(theirs) + 1)


def next_weeks_listing() -> FakeOpenEvSource:
    """The listing the history's source gives next week: what was there, and 900."""
    return FakeOpenEvSource(
        [(REVISION, REVISED_BODY), (OTHER_CAMP, OTHER_CAMP_BODY), (NEXT_WEEK, NEXT_WEEK_BODY)]
    )


@pytest.mark.parametrize("written_by", OLDER_BUILDS)
async def test_this_builds_plan_reads_it_by_the_delivery_record_here_and_by_name_with_none(
    removal_world: RemovalWorld, written_by: str
) -> None:
    """As before this task: the rows carry nothing, so the record decides, and without it the names."""
    world = removal_world
    await placed(world, written_by)

    here = await plan_512(world)
    (world.data_dir / OPENEV_DELIVERIES_FILENAME).unlink()
    elsewhere = await plan_512(world)

    assert {one.openev_ids: one.evidence for one in here.later_uploads} == {
        (640,): SamePathEvidence.UPSTREAM_PATH_DIGEST
    }
    assert {one.openev_ids: one.evidence for one in elsewhere.later_uploads} == {
        (640,): SamePathEvidence.ROW_NAME,
        (700,): SamePathEvidence.ROW_NAME,
    }


@pytest.mark.parametrize("written_by", OLDER_BUILDS)
async def test_this_builds_removal_rewrites_it_keeping_the_other_rows_byte_for_byte(
    removal_world: RemovalWorld, written_by: str
) -> None:
    world = removal_world
    theirs = by_path(await placed(world, written_by))

    assert (await world.service().execute(await plan_512(world))).completed

    after = by_path(release_lines(world))
    assert after == {path: line for path, line in theirs.items() if path not in ROWS[:2]}


@pytest.mark.parametrize("written_by", OLDER_BUILDS)
async def test_this_builds_re_derive_gives_every_row_the_keys_and_changes_nothing_else(
    removal_world: RemovalWorld, written_by: str
) -> None:
    world = removal_world
    theirs = await placed(world, written_by)
    importer = OpenEvImportService(
        caselists=world.repository, blobs=FsSnapshotStore(world.data_dir), suppression=world.suppression()
    )
    report = await importer.reimport_metadata(
        year=2026,
        event=Event.POLICY,
        recorded_manifest=theirs,
        upstream_paths=OpenEvDeliveries(world.data_dir / OPENEV_DELIVERIES_FILENAME).upstream_paths(),
    )

    assert report.identities_added == len(by_path(theirs))
    rederived = [json.loads(line) for line in report.manifest_lines]
    assert not [row for row in rederived if CAMP_WORD in row], "no delivery record knows a camp word"
    untouched = (*IDENTITY, *DERIVED_FIELDS)
    assert [{key: value for key, value in row.items() if key not in untouched} for row in rederived[:-1]] == [
        {key: value for key, value in json.loads(line).items() if key not in DERIVED_FIELDS}
        for line in theirs[:-1]
    ], "every field but the keys and the four a re-derive owns (v1-e30-t08) is as the older build wrote it"
    assert {
        str(row["path"]): (row["openev_id"], row["upstream_path_sha256"])
        for row in rederived
        if row["kind"] == "member"
        and (row["openev_id"] is not None or row["upstream_path_sha256"] is not None)
    } == PULLED_IDENTITY


@pytest.mark.parametrize("written_by", OLDER_BUILDS)
async def test_this_builds_publish_and_status_read_it(removal_world: RemovalWorld, written_by: str) -> None:
    world = removal_world
    await placed(world, written_by)
    publisher = CaselistPublishService(
        local=world.local, remote=world.bucket, suppression=world.suppression()
    )

    assert (await publisher.execute(await publisher.plan("openev", "2026-policy"))).succeeded
    status = await CaselistStatusService(
        local=world.local, remote=world.bucket, suppression=world.suppression()
    ).status("openev")
    assert status.in_sync
