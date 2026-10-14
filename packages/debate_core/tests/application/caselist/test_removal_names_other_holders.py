"""The removal plan counts only holders other than the one removed (`v1-e30-t16`).

`v1-e30-t10` made a `--source` plan leave one holding team out of `other_teams`. Two counts still
named the holder being removed as another:

* **A later upload at a second path of the same team.** The team whose path a removal takes a later
  upload from is the holder removed. When the same team also holds the upload at another path,
  that path keeps the bytes, but no *other* team holds them. `other_teams` counted the team at the
  live path without leaving out the team at the removed path, and read 1.
* **A camp file named by `--source`.** One release holding the file is the holder removed, as one
  team is for a team's file. `camp_file_holders` counted every release, so a file only one camp
  file holds read "also held by 1 camp file(s)".

Every expected value is worked out by hand beside the test, from the fixture tables below and the
synthetic weeks of `tests/fixtures/caselist/build_synthetic_archives.py` (working agreement 6).

## The fixture: a week after the three synthetic ones

The synthetic team `Maple Grove/QX` discloses the Bayview semifinal negative (`bayview-semis-neg`)
at one path, first in the weekly of `2026-09-15`, and nobody else holds it. The weekly window of
`2026-09-22` holds a revision of it at that path. In :data:`SAME_TEAM_ONLY` the team also uploaded
the revision at a second path of its own; in :data:`SAME_TEAM_AND_ANOTHER` a second team has it
too.

| Path | Whose | `2026-09-15` | `2026-09-22` |
|---|---|---|---|
| :data:`BAYVIEW_PATH` | Maple Grove/QX | `bayview-semis-neg` | the revision |
| :data:`SECOND_PATH` | Maple Grove/QX | — | the revision |
| :data:`ANOTHER_TEAMS_PATH` | Cedar Hollow/ZaLu | — | the revision, in :data:`SAME_TEAM_AND_ANOTHER` only |

`caselist remove --source <bayview-semis-neg>`: the named file is held by one team at one path, so
it is removed whole. The revision is held at the removed path in a snapshot dated after the named
file first appeared there, so it is a later upload; :data:`SECOND_PATH` is a path the removal does
not take it from, so the revision is withdrawn from :data:`BAYVIEW_PATH` only, and its copy in
`testcl26` stays (`kept_in`). The holder removed is Maple Grove/QX. So:

| World | Teams holding the revision at a live path | Other than Maple Grove/QX |
|---|---|---|
| :data:`SAME_TEAM_ONLY` | Maple Grove/QX | none: `other_teams` 0 |
| :data:`SAME_TEAM_AND_ANOTHER` | Maple Grove/QX, Cedar Hollow/ZaLu | one: `other_teams` 1 |
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import date
from pathlib import Path
from typing import Final

import pytest
from tests.fixtures.caselist.build_synthetic_archives import (
    DOCUMENT_BODIES,
    SYNTHETIC_CASELIST,
    _docx,  # pyright: ignore[reportPrivateUsage]
)
from tests.fixtures.openev.build_synthetic_openev import CAMP_ALIASES_PATH, build_download_zips
from tests.fixtures.openev.build_synthetic_openev import DOCUMENT_BODIES as CAMP_BODIES
from tests.fixtures.openev.build_synthetic_openev import DOWNLOADS as OPENEV_DOWNLOADS

from debate_core.application.caselist.camp_metadata import load_camp_aliases
from debate_core.application.caselist.import_service import CaselistImportService
from debate_core.application.caselist.manifest import manifest_key, write_manifest, write_manifest_lines
from debate_core.application.caselist.openev_import_service import OpenEvImportService
from debate_core.application.caselist.publish_plan import OPENEV
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.removal_plan import (
    Disposition,
    Inclusion,
    RemovalPlan,
    SourceSelector,
    parse_team_selector,
)
from debate_core.application.ports.suppression import ReasonCode
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsEvidenceObjectStore, FsSnapshotStore
from debate_core.integrations.local.archive_reader import archive_digest, read_archive
from debate_core.testing.fakes import empty_suppression_list

from .conftest import TEAM, RemovalWorld
from .test_removal_covers_later_uploads import LIMITS

pytestmark = pytest.mark.anyio

REQUEST: Final = "RM-2026-07"
CASELIST: Final = SYNTHETIC_CASELIST
NEXT_WEEK: Final = date(2026, 9, 22)

BAYVIEW_PATH: Final = "Maple Grove/QX/Maple Grove-QX-Neg-Bayview Open [2]-Semis.docx"
"""Where the synthetic weeks hold `bayview-semis-neg`: the 2026-09-15 weekly, and nowhere else."""
SECOND_PATH: Final = "Maple Grove/QX/Maple Grove-QX-Neg-Bayview Open [2]-Semis (1).docx"
"""The same team's second path: a copy number the archive gave a second upload of the file."""
ANOTHER_TEAMS_PATH: Final = "Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-Neg-Bayview Open [2]-Semis.docx"

REVISION_BODY: Final = _docx(
    ("Bayview Open, semifinals, negative.", "Revised the week after, twice uploaded.")
)
NAMED: Final = hashlib.sha256(DOCUMENT_BODIES["bayview-semis-neg"]).hexdigest()
REVISION: Final = hashlib.sha256(REVISION_BODY).hexdigest()

TEAM_REQUEST: Final = "RM-2026-08"
ROUND_1_AFF: Final = hashlib.sha256(DOCUMENT_BODIES["grove-round-1-aff"]).hexdigest()
ROUND_1_AFF_PATHS: Final = (
    "Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1.docx",
    "Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1 (1).docx",
)
"""The team's two paths of the Round 1 affirmative, which Cedar Hollow/ZaLu and a camp file hold too."""

SAME_TEAM_ONLY: Final = (BAYVIEW_PATH, SECOND_PATH)
SAME_TEAM_AND_ANOTHER: Final = (BAYVIEW_PATH, SECOND_PATH, ANOTHER_TEAMS_PATH)


async def import_and_publish_next_week(world: RemovalWorld, scratch: Path, paths: tuple[str, ...]) -> None:
    """The weekly window of 2026-09-22 holding the revision at `paths`, imported here and published."""
    archive = scratch / f"{CASELIST}-weekly-{NEXT_WEEK.isoformat()}.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as written:
        for path in paths:
            written.writestr(path, REVISION_BODY)
    importer = CaselistImportService(
        caselists=world.repository,
        blobs=FsSnapshotStore(world.data_dir),
        suppression=empty_suppression_list(),
    )
    report = await importer.import_archive(
        read_archive(archive, **LIMITS),
        caselist=CASELIST,
        snapshot=NEXT_WEEK,
        event=Event.LD,
        archive_sha256=archive_digest(archive),
    )
    write_manifest(report, FsEvidenceObjectStore(world.data_dir).path_for(manifest_key(CASELIST, NEXT_WEEK)))
    publisher = CaselistPublishService(
        local=world.local, remote=world.bucket, suppression=empty_suppression_list()
    )
    assert (await publisher.execute(await publisher.plan(CASELIST))).succeeded


async def plan_the_named_file(world: RemovalWorld) -> RemovalPlan:
    return await world.planner().plan(
        SourceSelector(NAMED), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM
    )


# ------------------------------------------------------------------------------------------------
# A later upload at a second path of the same team (case 3, ac2)
# ------------------------------------------------------------------------------------------------


class TestALaterUploadTheSameTeamHoldsAtASecondPath:
    async def test_no_other_team_holds_it_though_its_copy_in_the_caselist_stays(
        self, removal_world: RemovalWorld, tmp_path: Path
    ) -> None:
        await import_and_publish_next_week(removal_world, tmp_path / "next-week", SAME_TEAM_ONLY)

        plan = await plan_the_named_file(removal_world)

        named, revision = plan.source(NAMED), plan.source(REVISION)
        assert named is not None and revision is not None
        assert (named.disposition, named.other_teams, named.camp_file_holders) == (Disposition.REMOVE, 0, 0)
        assert (revision.inclusion, revision.disposition) == (Inclusion.LATER_UPLOAD, Disposition.WITHDRAW)
        assert revision.requester_paths == ((CASELIST, BAYVIEW_PATH),)
        assert revision.kept_in == (CASELIST,), "the team's second path still holds it in testcl26"
        assert (revision.other_teams, revision.camp_file_holders) == (0, 0)

    async def test_another_team_at_a_live_path_is_still_counted_once(
        self, removal_world: RemovalWorld, tmp_path: Path
    ) -> None:
        """Leaving out the removed path's team must not leave out a different team beside it."""
        await import_and_publish_next_week(removal_world, tmp_path / "next-week", SAME_TEAM_AND_ANOTHER)

        plan = await plan_the_named_file(removal_world)

        revision = plan.source(REVISION)
        assert revision is not None
        assert revision.disposition is Disposition.WITHDRAW
        assert (revision.other_teams, revision.camp_file_holders) == (1, 0), "Cedar Hollow/ZaLu alone"


# ------------------------------------------------------------------------------------------------
# A camp file named by --source (case 1)
# ------------------------------------------------------------------------------------------------

#: A camp file of the synthetic 2026 Policy download that no team discloses: one release holds it.
CAMP_ONLY: Final = hashlib.sha256(CAMP_BODIES["orchard-kritik"]).hexdigest()


async def import_and_publish_the_download_again_as_another_release(
    world: RemovalWorld, scratch: Path
) -> None:
    """The same synthetic download imported as the 2026 LD release too: each of its files has two releases."""
    service = OpenEvImportService(
        caselists=world.repository,
        blobs=FsSnapshotStore(world.data_dir),
        suppression=empty_suppression_list(),
    )
    download = build_download_zips(scratch)[OPENEV_DOWNLOADS[0].name]
    report = await service.import_release(
        read_archive(download, **LIMITS),
        year=2026,
        event=Event.LD,
        imported_on=date(2026, 9, 14),
        archive_sha256=archive_digest(download),
        aliases=load_camp_aliases(CAMP_ALIASES_PATH),
    )
    write_manifest_lines(
        report.manifest_lines, FsEvidenceObjectStore(world.data_dir).path_for(report.manifest_key)
    )
    publisher = CaselistPublishService(
        local=world.local, remote=world.bucket, suppression=empty_suppression_list()
    )
    assert (await publisher.execute(await publisher.plan(OPENEV))).succeeded


async def plan_the_camp_file(world: RemovalWorld) -> RemovalPlan:
    return await world.planner().plan(
        SourceSelector(CAMP_ONLY), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_CAMP
    )


class TestACampFileNamedBySource:
    async def test_a_file_only_one_camp_file_holds_counts_no_other_holder(
        self, removal_world: RemovalWorld
    ) -> None:
        """The 2026 Policy release alone holds it: it is the holder removed, so there is no other.

        Until `v1-e30-t16` `camp_file_holders` counted it, and the plan said "also held by 1 camp file(s)".
        """
        plan = await plan_the_camp_file(removal_world)

        (source,) = plan.sources
        assert source.disposition is Disposition.REMOVE
        assert len(source.camp_files) == 1, "its one camp-file record goes with it"
        assert (source.other_teams, source.camp_file_holders) == (0, 0)
        assert not source.shared

    async def test_a_file_two_releases_hold_counts_one_other_camp_file(
        self, removal_world: RemovalWorld, tmp_path: Path
    ) -> None:
        """2026 Policy and 2026 LD hold it: two holders, so it is shared and skipped, and one is other."""
        await import_and_publish_the_download_again_as_another_release(removal_world, tmp_path / "again")

        plan = await plan_the_camp_file(removal_world)

        (source,) = plan.sources
        assert source.disposition is Disposition.SKIP_SHARED
        assert (source.other_teams, source.camp_file_holders) == (0, 1)
        assert source.shared


# ------------------------------------------------------------------------------------------------
# A withdrawal records the caselist it took the file from (ac3)
# ------------------------------------------------------------------------------------------------

OTHER_CASELIST: Final = "testclb26"
"""A second invented caselist, which holds the revision at another team's path in one weekly."""
WITHDRAWALS: Final = "withdrawals.jsonl"
#: Every word of the fixture's paths that names a school, a team, a tournament, a round or a file.
NAMES: Final = (
    "Maple Grove",
    "QX",
    "Cedar Hollow",
    "ZaLu",
    "Bayview",
    "Semis",
    "Grove City",
    "Round",
    ".docx",
)


def recorded_withdrawals(world: RemovalWorld) -> dict[str, list[dict[str, object]]]:
    """The withdrawal record beside the list, on this machine and in the bucket, as parsed lines."""
    local = world.data_dir / "suppression" / WITHDRAWALS
    key = f"manifests/_suppression/{WITHDRAWALS}"
    listed = world.client.list_objects_v2(Bucket=world.bucket_name, Prefix=key).get("Contents", [])
    bucket = world.client.get_object(Bucket=world.bucket_name, Key=key)["Body"].read() if listed else b""
    return {
        "local": [
            json.loads(line) for line in (local.read_text("utf-8") if local.exists() else "").splitlines()
        ],
        "bucket": [json.loads(line) for line in bucket.decode("utf-8").splitlines()],
    }


def raw_text(world: RemovalWorld) -> str:
    local = world.data_dir / "suppression" / WITHDRAWALS
    return local.read_text("utf-8") if local.exists() else ""


async def remove_the_named_file(world: RemovalWorld) -> None:
    service = world.service()
    plan = await service.plan(SourceSelector(NAMED), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM)
    assert (await service.execute(plan)).completed


async def import_and_publish_another_caselists_week(world: RemovalWorld, scratch: Path) -> None:
    """`testclb26`'s weekly of 2026-09-22, holding the revision at Cedar Hollow/ZaLu's path."""
    archive = scratch / f"{OTHER_CASELIST}-weekly-{NEXT_WEEK.isoformat()}.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as written:
        written.writestr(ANOTHER_TEAMS_PATH, REVISION_BODY)
    importer = CaselistImportService(
        caselists=world.repository,
        blobs=FsSnapshotStore(world.data_dir),
        suppression=empty_suppression_list(),
    )
    report = await importer.import_archive(
        read_archive(archive, **LIMITS),
        caselist=OTHER_CASELIST,
        snapshot=NEXT_WEEK,
        event=Event.LD,
        archive_sha256=archive_digest(archive),
    )
    write_manifest(
        report, FsEvidenceObjectStore(world.data_dir).path_for(manifest_key(OTHER_CASELIST, NEXT_WEEK))
    )
    publisher = CaselistPublishService(
        local=world.local, remote=world.bucket, suppression=empty_suppression_list()
    )
    assert (await publisher.execute(await publisher.plan(OTHER_CASELIST))).succeeded


class TestAWithdrawalRecordsItsCaselist:
    async def test_beside_the_list_in_both_places_by_slug_and_naming_no_one(
        self, removal_world: RemovalWorld, tmp_path: Path
    ) -> None:
        await import_and_publish_next_week(removal_world, tmp_path / "next-week", SAME_TEAM_ONLY)

        await remove_the_named_file(removal_world)

        # One copy withdrawn: the revision, from the team's Bayview path in testcl26, at the plan's time.
        written = {
            "schema_version": 1,
            "sha256": REVISION,
            "disclosure": hashlib.sha256(f"{CASELIST}/{BAYVIEW_PATH}".encode()).hexdigest(),
            "caselist": CASELIST,
            "recorded_at": "2026-09-30T18:00:00Z",
            "reason": "REQUESTED_BY_TEAM",
            "request_id": REQUEST,
        }
        assert recorded_withdrawals(removal_world) == {"local": [written], "bucket": [written]}
        assert not [name for name in NAMES if name in raw_text(removal_world)]

    async def test_a_file_kept_in_another_caselist_is_attributed_to_the_one_it_was_taken_from(
        self, removal_world: RemovalWorld, tmp_path: Path
    ) -> None:
        """Withdrawn from testcl26 and kept in testclb26: the record says testcl26, and only that."""
        await import_and_publish_next_week(removal_world, tmp_path / "next-week", (BAYVIEW_PATH,))
        await import_and_publish_another_caselists_week(removal_world, tmp_path / "other-caselist")

        plan = await plan_the_named_file(removal_world)
        revision = plan.source(REVISION)
        assert revision is not None
        assert (revision.disposition, revision.kept_in) == (Disposition.WITHDRAW, (OTHER_CASELIST,))
        await remove_the_named_file(removal_world)

        recorded = recorded_withdrawals(removal_world)
        assert [(one["sha256"], one["caselist"]) for one in recorded["local"]] == [(REVISION, CASELIST)]
        assert recorded["bucket"] == recorded["local"]

    async def test_a_team_removal_records_each_path_it_withdraws_a_shared_file_from(
        self, removal_world: RemovalWorld
    ) -> None:
        """The team's Round 1 affirmative, held by Cedar Hollow/ZaLu and a camp file too, at two paths."""
        service = removal_world.service()
        plan = await service.plan(
            parse_team_selector(TEAM), request_id=TEAM_REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM
        )
        assert (await service.execute(plan)).completed

        recorded = recorded_withdrawals(removal_world)
        assert sorted(
            (one["sha256"], one["caselist"], one["disclosure"]) for one in recorded["local"]
        ) == sorted(
            (ROUND_1_AFF, CASELIST, hashlib.sha256(f"{CASELIST}/{path}".encode()).hexdigest())
            for path in ROUND_1_AFF_PATHS
        )
        assert recorded["bucket"] == recorded["local"]
        assert not [name for name in NAMES if name in raw_text(removal_world)]

    async def test_a_removal_that_withdraws_nothing_records_no_withdrawal_and_makes_no_record(
        self, removal_world: RemovalWorld
    ) -> None:
        """The Bayview negative alone, removed whole: nothing is withdrawn, so no record is created."""
        await remove_the_named_file(removal_world)

        assert recorded_withdrawals(removal_world) == {"local": [], "bucket": []}
        assert not (removal_world.data_dir / "suppression" / WITHDRAWALS).exists()

    async def test_the_suppression_entry_and_the_log_entry_are_each_attributed_to_the_caselist(
        self, removal_world: RemovalWorld, tmp_path: Path
    ) -> None:
        """Read back through the list's reader and the log's: each finds the record beside it."""
        from debate_core.application.caselist.suppression import (  # noqa: PLC0415 - red first, see ac3
            caselist_withdrawn_from,
            caselists_withdrawn_by,
        )

        await import_and_publish_next_week(removal_world, tmp_path / "next-week", (BAYVIEW_PATH,))
        await import_and_publish_another_caselists_week(removal_world, tmp_path / "other-caselist")
        await remove_the_named_file(removal_world)

        listed = removal_world.suppression()
        (withdrawn,) = [entry for entry in await listed.entries() if entry.disclosure is not None]
        assert caselist_withdrawn_from(withdrawn, await listed.withdrawals()) == CASELIST
        whole = [entry for entry in await listed.entries() if entry.disclosure is None]
        assert [caselist_withdrawn_from(entry, await listed.withdrawals()) for entry in whole] == [None]

        log = removal_world.removal_log()
        (entry,) = await log.entries()
        assert entry.withdrawn_sha256 == (REVISION,)
        assert caselists_withdrawn_by(entry, await log.withdrawals()) == {REVISION: (CASELIST,)}
        assert await log.withdrawals() == await listed.withdrawals()
