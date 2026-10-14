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

from debate_core.application.caselist.import_service import CaselistImportService
from debate_core.application.caselist.manifest import manifest_key, write_manifest
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.removal_plan import (
    Disposition,
    Inclusion,
    RemovalPlan,
    SourceSelector,
)
from debate_core.application.ports.suppression import ReasonCode
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsEvidenceObjectStore, FsSnapshotStore
from debate_core.integrations.local.archive_reader import archive_digest, read_archive
from debate_core.testing.fakes import empty_suppression_list

from .conftest import RemovalWorld
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
