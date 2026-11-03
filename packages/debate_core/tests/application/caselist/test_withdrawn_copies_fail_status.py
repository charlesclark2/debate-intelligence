"""A copy withdrawn from a caselist that keeps no holder of it fails `caselist status` (`v1-e30-t24`, item 1).

`v1-e30-t19` named what is left of such a copy (*WITHDRAWN COPIES LEFT*) and kept it out of the
verdict, because its spec forbade changing any exit code. The PM ruled on t19's question 1 that it
is an unfinished removal, the same as a removed file's residue, and this task lifts that one
forbidden entry: the report is not in sync, and the command exits 1 as `REMOVAL_RESIDUE`. A
withdrawal no record attributes (*NOT ATTRIBUTED*) is still reported beside the verdict and not in
it, like *NOT CHECKED*: it says what was not looked at, not that something was found.

The worlds are t19's, against moto with the real planner, executor and status: `RM-2026-07` removed
the Bayview negative and withdrew its revision from `testcl26`, where no other holder keeps it, and
kept it in `testclb26`; then a current object of the revision is back under `testcl26`, as a
takedown that stopped leaves one. The command's exit code is shown through the installed build in
`tests/smoke/test_caselist_remove_smoke.py`.

No test imports a name this task adds, so each runs against the start commit's source too.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.fixtures.caselist.build_synthetic_archives import SYNTHETIC_CASELIST

from .conftest import RemovalWorld
from .test_manifest_and_aggregate_residue import of, status, versions_of
from .test_removal_names_other_holders import (
    BAYVIEW_PATH,
    OTHER_CASELIST,
    REVISION,
    import_and_publish_another_caselists_week,
    import_and_publish_next_week,
    remove_the_named_file,
)
from .test_residue_clearing_gaps import WITHDRAWALS_KEY, revision_copy_in

pytestmark = pytest.mark.anyio


@pytest.fixture
async def withdrawn_from_one_caselist(removal_world: RemovalWorld, tmp_path: Path) -> RemovalWorld:
    """t19's world of the same name: `RM-2026-07` withdrew the revision from `testcl26` and kept it in
    `testclb26`, and a current object of it is back under `testcl26`."""
    world = removal_world
    await import_and_publish_next_week(world, tmp_path / "next-week", (BAYVIEW_PATH,))
    await import_and_publish_another_caselists_week(world, tmp_path / "other-caselist")
    await remove_the_named_file(world)
    assert versions_of(world, revision_copy_in(SYNTHETIC_CASELIST)) == []
    world.client.put_object(Bucket=world.bucket_name, Key=revision_copy_in(SYNTHETIC_CASELIST), Body=b"left")
    return world


async def test_a_withdrawn_copy_left_in_a_caselist_that_keeps_no_holder_is_not_in_sync(
    withdrawn_from_one_caselist: RemovalWorld,
) -> None:
    report = await status(withdrawn_from_one_caselist)

    assert [copy.sha256 for copy in of(report, SYNTHETIC_CASELIST).withdrawn_copies] == [REVISION]
    assert report.drifted == (), "every snapshot agrees: what is left is the removal's"
    assert of(report, SYNTHETIC_CASELIST).found
    assert report.residue_found
    assert not report.in_sync


async def test_a_noncurrent_version_of_the_copy_alone_fails_it_too(
    withdrawn_from_one_caselist: RemovalWorld,
) -> None:
    """The copy deleted without a version id: a delete marker over the version put back. Nothing
    current is left, and the version under the marker is still a copy that can be restored."""
    world = withdrawn_from_one_caselist
    world.client.delete_object(Bucket=world.bucket_name, Key=revision_copy_in(SYNTHETIC_CASELIST))

    report = await status(world)

    (copy,) = of(report, SYNTHETIC_CASELIST).withdrawn_copies
    assert (copy.current_objects, copy.noncurrent_versions, copy.delete_markers) == (0, 1, 1)
    assert not report.in_sync


async def test_the_same_removal_run_again_clears_it_and_status_is_in_sync(
    withdrawn_from_one_caselist: RemovalWorld,
) -> None:
    world = withdrawn_from_one_caselist

    await remove_the_named_file(world)

    report = await status(world)
    assert of(report, SYNTHETIC_CASELIST).withdrawn_copies == ()
    assert report.in_sync
    assert versions_of(world, revision_copy_in(OTHER_CASELIST)), "testclb26's copy is its holder's"


async def test_a_withdrawal_no_record_attributes_is_reported_and_does_not_fail_it(
    withdrawn_from_one_caselist: RemovalWorld,
) -> None:
    """What an earlier build's withdrawal leaves: the list's entry and no record of its caselist. The
    copy left under `testcl26` is then not looked at, and that is said, not counted as found."""
    world = withdrawn_from_one_caselist
    (world.data_dir / "suppression" / "withdrawals.jsonl").unlink()
    world.client.delete_object(Bucket=world.bucket_name, Key=WITHDRAWALS_KEY)

    report = await status(world)

    assert report.withdrawals_not_attributed == ("RM-2026-07",)
    assert of(report, SYNTHETIC_CASELIST).withdrawn_copies == ()
    assert not report.residue_found
    assert report.in_sync
