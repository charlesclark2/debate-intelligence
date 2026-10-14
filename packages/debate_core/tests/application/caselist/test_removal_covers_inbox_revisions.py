"""A removal covers a revision that is waiting in the download inbox (`v1-e30-t13`).

`v1-e30-t11`'s plan found a later upload at a removed path among the manifests, so one the store
had not imported yet was not in it: an archive `caselist pull` had downloaded and not imported kept
its revision, and the next pull imported it. The plan now reads the inbox's archives as snapshots
too, so a revision waiting there is a later upload like any other, and is covered as one: on the
suppression list under the request, and out of the inbox.

Everything here is checked on the inbox and the store after `caselist remove --source
<named-version> --execute`, through the service the command runs, against moto and a local data
directory. No test asks the planner for anything this task added, so every one also runs against the
source as it was before the task, where the ones about a waiting revision fail on what was left in
the inbox.

The store is `v1-e30-t11`'s, and the inbox holds, as well as what that task's tests put there, the
three `testcl26` archives of `tests/fixtures/caselist/build_held_path_archives.py`, none of them
imported. :data:`LEFT_IN_THE_INBOX` there, written by hand, is what these tests assert.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_held_path_archives import (
    ARRIVING_BODIES,
    LEFT_IN_THE_INBOX,
    arriving_digest_of,
    build_arriving_complete_archive_zips,
    build_arriving_weekly_zips,
)
from tests.fixtures.caselist.build_revised_path_archives import (
    BODIES,
    CASELIST,
    KEPT_PATH,
    OTHER_TEAM_PATH,
    REVISED_PATH,
)

from debate_core.application.caselist.import_service import Classification
from debate_core.application.caselist.manifest import manifest_key
from debate_core.application.caselist.removal_plan import SourceSelector
from debate_core.application.ports.suppression import ReasonCode, disclosure_digest
from debate_core.integrations.local.suppression_list import local_suppression_list_file

from .conftest import REQUEST, RemovalWorld
from .test_removal_covers_later_uploads import (
    NAMED,
    held_at,
    local_blob,
    remove_the_named_file,
    revised_path_world,
    suppression_lines,
    zip_members,
)
from .test_removed_path_holds_later_imports import import_weekly, manifest_rows

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

WAITING_IN_THE_INBOX = arriving_digest_of("uploaded-after-the-removal")
WAITING_IN_A_COMPLETE_ARCHIVE = arriving_digest_of("uploaded-after-in-a-complete-archive")
WAITING_AT_TWO_PATHS = arriving_digest_of("uploaded-after-at-two-paths")

#: The documents waiting at the removed path, which no archive in the inbox may hold afterwards.
AT_THE_REMOVED_PATH = (
    "uploaded-after-the-removal",
    "uploaded-after-in-a-complete-archive",
    "uploaded-after-at-two-paths",
)


def put_the_arriving_archives_in_the_inbox(world: RemovalWorld, scratch: Path) -> None:
    """The three `testcl26` archives, downloaded and not imported: each dated after the newest import."""
    inbox = world.data_dir / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    built = {
        **build_arriving_weekly_zips(scratch / "arriving"),
        **build_arriving_complete_archive_zips(scratch / "arriving"),
    }
    for (caselist, _), path in built.items():
        if caselist == CASELIST:
            shutil.copyfile(path, inbox / path.name)


@pytest.fixture
async def world(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> RemovalWorld:
    built = await revised_path_world(tmp_path, s3_client, evidence_bucket)
    put_the_arriving_archives_in_the_inbox(built, tmp_path)
    return built


def copies_left_in_the_inbox(world: RemovalWorld) -> list[str]:
    """Every copy of a document waiting at the removed path that an inbox archive still holds there."""
    wanted = {ARRIVING_BODIES[name]: name for name in AT_THE_REMOVED_PATH}
    return sorted(
        f"{wanted[body]} in {archive.name}"
        for archive in sorted((world.data_dir / "inbox").glob("*.zip"))
        for member, body in zip_members(archive).items()
        if member == REVISED_PATH and body in wanted
    )


# ------------------------------------------------------------------------------------------------
# ac2: the executed removal leaves no copy of a waiting revision in the inbox
# ------------------------------------------------------------------------------------------------


async def test_before_the_removal_each_waiting_archive_holds_a_revision_at_the_path(
    world: RemovalWorld,
) -> None:
    assert copies_left_in_the_inbox(world) == [
        f"uploaded-after-at-two-paths in {CASELIST}-weekly-2026-10-10.zip",
        f"uploaded-after-in-a-complete-archive in {CASELIST}-all-2026-10-09.zip",
        f"uploaded-after-the-removal in {CASELIST}-weekly-2026-10-08.zip",
    ]


async def test_the_executed_removal_leaves_no_copy_of_a_waiting_revision_in_the_inbox(
    world: RemovalWorld,
) -> None:
    await remove_the_named_file(world)

    assert copies_left_in_the_inbox(world) == []
    inbox = world.data_dir / "inbox"
    left = {name: sorted(zip_members(inbox / name)) for name in LEFT_IN_THE_INBOX}
    assert left == LEFT_IN_THE_INBOX, "a waiting archive is rewritten without the revision, never deleted"


async def test_the_other_teams_copy_of_a_waiting_revision_stays_in_its_archive(world: RemovalWorld) -> None:
    await remove_the_named_file(world)

    members = zip_members(world.data_dir / "inbox" / f"{CASELIST}-weekly-2026-10-10.zip")
    assert members[OTHER_TEAM_PATH] == ARRIVING_BODIES["uploaded-after-at-two-paths"]
    assert members[KEPT_PATH] == BODIES["kept"]


async def test_each_waiting_revision_is_on_the_suppression_list_under_the_request(
    world: RemovalWorld,
) -> None:
    await remove_the_named_file(world)

    for entries in suppression_lines(world):
        whole = {entry.sha256 for entry in entries if entry.disclosure is None}
        scoped = {(entry.sha256, entry.disclosure) for entry in entries if entry.disclosure is not None}
        assert {WAITING_IN_THE_INBOX, WAITING_IN_A_COMPLETE_ARCHIVE} <= whole
        assert WAITING_AT_TWO_PATHS not in whole, "another team discloses it too: its bytes are theirs"
        assert (WAITING_AT_TWO_PATHS, disclosure_digest(CASELIST, REVISED_PATH)) in scoped
        assert {entry.request_id for entry in entries} == {REQUEST}


async def test_importing_that_week_as_it_was_published_stores_nothing_at_the_path(
    world: RemovalWorld, tmp_path: Path
) -> None:
    await remove_the_named_file(world)

    report = await import_weekly(world, tmp_path, CASELIST, date(2026, 10, 8))

    assert not local_blob(world, WAITING_IN_THE_INBOX).exists()
    rows = manifest_rows(world, manifest_key(CASELIST, date(2026, 10, 8)))
    assert held_at(rows, REVISED_PATH) == set()
    assert report.count(Classification.SUPPRESSED) == 1, "the archive as published still holds it"


async def test_only_named_leaves_the_waiting_revisions_where_they_are(world: RemovalWorld) -> None:
    inbox = world.data_dir / "inbox"
    before = {name: (inbox / name).read_bytes() for name in LEFT_IN_THE_INBOX}
    service = world.service()
    plan = await service.plan(
        SourceSelector(NAMED), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM, only_named=True
    )

    assert (await service.execute(plan)).completed

    assert {name: (inbox / name).read_bytes() for name in LEFT_IN_THE_INBOX} == before
    listed = local_suppression_list_file(world.data_dir).path.read_text(encoding="utf-8")
    assert not [digest for digest in (WAITING_IN_THE_INBOX, WAITING_AT_TWO_PATHS) if digest in listed]
