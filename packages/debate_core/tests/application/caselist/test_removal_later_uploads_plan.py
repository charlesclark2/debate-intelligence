"""The removal plan's account of later uploads, the limiting option, and a run that stops (`v1-e30-t11`).

`test_removal_covers_later_uploads.py` checks the store after a removal. This module checks the plan
the operator confirms: what it lists as later uploads and as earlier versions, what `only_named`
leaves, what a `--team` removal with `--include-shared` reaches, and what a re-run finishes. The
world is the same one, `tests/fixtures/caselist/build_revised_path_archives.py`, and every expected
value is from the hand-written tables there or is worked out beside the assertion.
"""

from __future__ import annotations

import hashlib
import logging
import zipfile
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from tests.fixtures.caselist.build_revised_path_archives import (
    CASELIST,
    EXPECTED,
    OTHER_TEAM_PATH,
    REVISED_PATH,
    digest_of,
)
from tests.fixtures.caselist.build_synthetic_archives import (
    DOCUMENT_BODIES,
    _docx,  # pyright: ignore[reportPrivateUsage]
)

from debate_core.application.caselist.import_service import CaselistImportService
from debate_core.application.caselist.manifest import manifest_key, write_manifest
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.removal_path_versions import VersionRelation
from debate_core.application.caselist.removal_plan import (
    Disposition,
    Inclusion,
    LaterUploadOutcome,
    RemovalPlan,
    Side,
    SourceSelector,
    parse_team_selector,
)
from debate_core.application.caselist.removal_service import RemovalIncomplete
from debate_core.application.ports.suppression import ReasonCode, RemovalLogEntry, RemovalOutcome
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsEvidenceObjectStore, FsSnapshotStore
from debate_core.integrations.local.archive_reader import archive_digest, read_archive
from debate_core.integrations.local.suppression_list import local_removal_log_file
from debate_core.integrations.s3 import S3EvidenceVersionStore
from debate_core.testing.fakes import empty_suppression_list

from .conftest import REQUEST, TEAM, RemovalWorld
from .test_removal_covers_later_uploads import (
    ALL_SNAPSHOTS,
    EARLIER,
    LATER_IN_COMPLETE_ARCHIVE,
    LATER_REVISION,
    LATER_SHARED,
    LIMITS,
    NAMED,
    held_at,
    local_blob,
    raw_key,
    revised_path_world,
    rows_on_both_sides,
    snapshot_key,
    suppression_lines,
    versions_of,
)
from .test_removal_service import VersionsThatFailAfter

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio


@pytest.fixture
async def world(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> RemovalWorld:
    return await revised_path_world(tmp_path, s3_client, evidence_bucket)


async def plan_the_named_file(world: RemovalWorld, **options: bool) -> RemovalPlan:
    return await world.service().plan(
        SourceSelector(NAMED), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM, **options
    )


def log_entries(world: RemovalWorld) -> list[RemovalLogEntry]:
    text = local_removal_log_file(world.data_dir).path.read_text(encoding="utf-8")
    return [RemovalLogEntry.from_line(line) for line in text.splitlines()]


# ------------------------------------------------------------------------------------------------
# What the dry run lists
# ------------------------------------------------------------------------------------------------


async def test_the_plan_lists_each_later_upload_by_digest_caselist_and_snapshot(
    world: RemovalWorld,
) -> None:
    plan = await plan_the_named_file(world)

    listed = {
        one.sha256: (one.caselist, list(one.snapshots), plan.later_upload_outcome(one))
        for one in plan.later_uploads
    }
    assert listed == {
        LATER_REVISION: (CASELIST, ["2026-09-15"], LaterUploadOutcome.REMOVED),
        LATER_IN_COMPLETE_ARCHIVE: (CASELIST, ["full/2026-10-03"], LaterUploadOutcome.REMOVED),
        LATER_SHARED: (CASELIST, ["2026-10-06"], LaterUploadOutcome.WITHDRAWN_FROM_THE_PATH),
    }
    assert {digest: where[1] for digest, where in listed.items()} == {
        digest_of(body): snapshots for body, snapshots in EXPECTED.later_uploads.items()
    }
    assert {one.of_sha256 for one in plan.later_uploads} == {NAMED}
    assert (plan.later_uploads_found, plan.later_uploads_added) == (3, 3)


async def test_the_earlier_version_is_listed_and_is_not_in_the_plan(world: RemovalWorld) -> None:
    plan = await plan_the_named_file(world)

    (earlier,) = plan.earlier_versions
    assert (earlier.sha256, earlier.caselist, earlier.relation) == (
        EARLIER,
        CASELIST,
        VersionRelation.EARLIER,
    )
    assert list(earlier.snapshots) == EXPECTED.earlier_versions["earlier-version"]
    assert plan.source(EARLIER) is None
    assert EARLIER not in {planned.sha256 for planned in plan.objects}
    assert EARLIER not in {entry.sha256 for entry in plan.suppression_entries}


async def test_each_source_says_why_it_is_in_the_plan_and_what_happens_to_it(world: RemovalWorld) -> None:
    plan = await plan_the_named_file(world)

    assert {source.sha256: (source.inclusion, source.disposition) for source in plan.sources} == {
        NAMED: (Inclusion.NAMED, Disposition.REMOVE),
        LATER_REVISION: (Inclusion.LATER_UPLOAD, Disposition.REMOVE),
        LATER_IN_COMPLETE_ARCHIVE: (Inclusion.LATER_UPLOAD, Disposition.REMOVE),
        LATER_SHARED: (Inclusion.LATER_UPLOAD, Disposition.WITHDRAW),
    }
    shared = plan.source(LATER_SHARED)
    assert shared is not None
    assert shared.requester_paths == ((CASELIST, REVISED_PATH),)
    assert shared.kept_in == (CASELIST,), "Birch Hill MT still holds it there, so its raw copy stays"
    assert (shared.other_teams, shared.camp_file_holders, shared.local_blob) == (1, 0, False)
    assert [ref.source_path for ref in shared.disclosures] == [REVISED_PATH]
    assert plan.local_records == EXPECTED.local_records
    entries = plan.suppression_entries
    assert sum(1 for entry in entries if entry.disclosure is None) == EXPECTED.whole_file_suppressions
    assert sum(1 for entry in entries if entry.disclosure is not None) == EXPECTED.one_path_suppressions


async def test_the_plans_manifest_rewrites_are_the_fixtures_table(world: RemovalWorld) -> None:
    plan = await plan_the_named_file(world)

    dropped = {(rewrite.key, rewrite.side): rewrite.rows_dropped for rewrite in plan.manifests}
    assert dropped == {
        (snapshot_key(snapshot), side): count
        for snapshot, count in EXPECTED.rows_dropped.items()
        for side in (Side.LOCAL, Side.BUCKET)
    }


async def test_a_dry_run_with_later_uploads_changes_nothing_anywhere(world: RemovalWorld) -> None:
    tree, versions, records = world.tree(), world.versions(), world.records()

    await plan_the_named_file(world)
    await plan_the_named_file(world, only_named=True)

    assert (world.tree(), world.versions(), world.records()) == (tree, versions, records)


async def test_nothing_logged_at_info_or_above_names_a_path_a_school_or_a_team(
    world: RemovalWorld, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    service = world.service()

    assert (await service.execute(await plan_the_named_file(world))).completed

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert not [
        name for name in ("Alder Point", "Birch Hill", "Lakeshore", "Round 2", ".docx") if name in logged
    ]


# ------------------------------------------------------------------------------------------------
# ac3: the limiting option
# ------------------------------------------------------------------------------------------------


async def test_only_named_plans_the_named_file_alone_and_still_lists_what_it_leaves(
    world: RemovalWorld,
) -> None:
    plan = await plan_the_named_file(world, only_named=True)

    assert plan.only_named
    assert [(source.sha256, source.inclusion) for source in plan.sources] == [(NAMED, Inclusion.NAMED)]
    assert {one.sha256 for one in plan.later_uploads} == {
        LATER_REVISION,
        LATER_IN_COMPLETE_ARCHIVE,
        LATER_SHARED,
    }
    assert {plan.later_upload_outcome(one) for one in plan.later_uploads} == {
        LaterUploadOutcome.LEFT_IN_PLACE
    }
    assert (plan.later_uploads_found, plan.later_uploads_added) == (3, 0)
    assert {entry.sha256 for entry in plan.suppression_entries} == {NAMED}
    # The named file's two rows, and the REMOVED row at its path in the week between them.
    assert {(rewrite.key, rewrite.rows_dropped) for rewrite in plan.manifests} == {
        (snapshot_key("2026-09-08"), 1),
        (snapshot_key("2026-09-22"), 1),
        (snapshot_key("2026-09-29"), 1),
    }


async def test_only_named_removes_the_named_file_and_leaves_every_later_upload_as_it_was(
    world: RemovalWorld,
) -> None:
    service = world.service()

    assert (await service.execute(await plan_the_named_file(world, only_named=True))).completed

    assert not local_blob(world, NAMED).exists()
    assert versions_of(world, raw_key(NAMED)) == []
    for digest, versions in ((LATER_REVISION, 2), (LATER_IN_COMPLETE_ARCHIVE, 1), (LATER_SHARED, 1)):
        assert local_blob(world, digest).exists(), digest
        assert len(versions_of(world, raw_key(digest))) == versions, digest
        assert await world.repository.find_source(digest) is not None
    held = {
        snapshot: [held_at(rows, REVISED_PATH) for rows in rows_on_both_sides(world, snapshot)]
        for snapshot in ALL_SNAPSHOTS
    }
    assert held == {
        "2026-09-01": [{EARLIER}] * 2,
        "full/2026-09-05": [{EARLIER}] * 2,
        "2026-09-08": [set()] * 2,
        "2026-09-15": [{LATER_REVISION}] * 2,
        "2026-09-22": [set()] * 2,
        "2026-09-29": [set()] * 2,
        "full/2026-10-03": [{LATER_IN_COMPLETE_ARCHIVE}] * 2,
        "2026-10-06": [{LATER_SHARED}] * 2,
    }
    for entries in suppression_lines(world):
        assert {entry.sha256 for entry in entries} == {NAMED}
    (entry,) = log_entries(world)
    assert (entry.removed_sha256, entry.withdrawn_sha256) == ((NAMED,), ())


async def test_include_shared_is_about_the_named_file_and_does_not_widen_a_later_upload(
    world: RemovalWorld,
) -> None:
    """The shared revision is still only withdrawn from the removed path: the other team keeps it."""
    plan = await plan_the_named_file(world, include_shared=True)

    shared = plan.source(LATER_SHARED)
    assert shared is not None and shared.disposition is Disposition.WITHDRAW
    assert shared.requester_paths == ((CASELIST, REVISED_PATH),)
    assert not [
        planned
        for planned in plan.objects
        if planned.sha256 == LATER_SHARED and planned.key.startswith("raw/")
    ]


# ------------------------------------------------------------------------------------------------
# Re-running
# ------------------------------------------------------------------------------------------------


async def test_a_run_cut_short_in_the_bucket_is_finished_by_the_same_command_later_uploads_included(
    world: RemovalWorld,
) -> None:
    def flaky() -> Any:
        access = world.takedown()
        return type(access)(
            versions=VersionsThatFailAfter(
                S3EvidenceVersionStore(bucket=world.bucket_name, client=world.client), 1
            ),  # type: ignore[arg-type]
            objects=access.objects,
            caller=access.caller,
            profile=access.profile,
            bucket=access.bucket,
        )

    stopped = world.service(takedown=flaky)
    with pytest.raises(RemovalIncomplete):
        await stopped.execute(await plan_the_named_file(world))
    assert local_blob(world, LATER_REVISION).exists(), "it stopped before this machine's files"

    again = await plan_the_named_file(world)
    assert (await world.service().execute(again)).completed

    assert {source.sha256: source.inclusion for source in again.sources} == {
        NAMED: Inclusion.NAMED,
        LATER_REVISION: Inclusion.LATER_UPLOAD,
        LATER_IN_COMPLETE_ARCHIVE: Inclusion.LATER_UPLOAD,
        LATER_SHARED: Inclusion.LATER_UPLOAD,
    }
    assert all(source.already_suppressed for source in again.sources)
    assert again.suppression_entries == (), "every entry went on the list before anything was deleted"
    for digest in (NAMED, LATER_REVISION, LATER_IN_COMPLETE_ARCHIVE):
        assert not local_blob(world, digest).exists()
        assert versions_of(world, raw_key(digest)) == []
    assert [entry.outcome for entry in log_entries(world)] == [
        RemovalOutcome.INCOMPLETE,
        RemovalOutcome.COMPLETED,
    ]


class RecordsThatFailAfter:
    """This machine's records, refusing a delete after `allowed` of them: a run stopped at its last step."""

    def __init__(self, inner: Any, allowed: int) -> None:
        self._inner = inner
        self._allowed = allowed

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def _count(self) -> None:
        if self._allowed <= 0:
            raise OSError("the disk went away")
        self._allowed -= 1

    async def delete_disclosure(self, *arguments: Any) -> bool:
        self._count()
        return await self._inner.delete_disclosure(*arguments)

    async def delete_camp_file(self, *arguments: Any) -> bool:
        self._count()
        return await self._inner.delete_camp_file(*arguments)

    async def delete_source(self, *arguments: Any) -> bool:
        self._count()
        return await self._inner.delete_source(*arguments)


@pytest.mark.parametrize("only_named", [False, True])
async def test_a_run_stopped_among_the_records_is_finished_though_no_manifest_shows_the_later_uploads(
    world: RemovalWorld, only_named: bool
) -> None:
    """Every manifest is rewritten by then, so nothing shows what was at the removed path.

    The named file's three records are deleted, then the disk goes away: the later revision's
    disclosure and source document, the complete archive's revision's source document, and the
    shared revision's disclosure at the removed path are left. The list says this request
    suppressed all three, so the same command plans them again, with or without `--only-named`.
    """
    stopped = world.service()
    stopped.caselists = RecordsThatFailAfter(world.repository, 3)  # type: ignore[assignment]
    with pytest.raises(RemovalIncomplete):
        await stopped.execute(await plan_the_named_file(world))
    assert await world.repository.find_source(LATER_REVISION) is not None

    again = await plan_the_named_file(world, only_named=only_named)

    assert again.later_uploads == (), "no manifest holds anything at the removed path any more"
    assert {source.sha256: (source.inclusion, source.disposition) for source in again.sources} == {
        NAMED: (Inclusion.NAMED, Disposition.REMOVE),
        LATER_REVISION: (Inclusion.UNFINISHED, Disposition.REMOVE),
        LATER_IN_COMPLETE_ARCHIVE: (Inclusion.UNFINISHED, Disposition.REMOVE),
        LATER_SHARED: (Inclusion.UNFINISHED, Disposition.WITHDRAW),
    }
    assert again.local_records == 2 + 1 + 1
    assert again.suppression_entries == () and again.manifests == ()

    assert (await world.service().execute(again)).completed

    for digest in (LATER_REVISION, LATER_IN_COMPLETE_ARCHIVE):
        assert await world.repository.find_source(digest) is None
        assert not (await world.repository.list_disclosures(source_sha256=digest, limit=10)).items
    kept = (await world.repository.list_disclosures(source_sha256=LATER_SHARED, limit=10)).items
    assert [one.source_path for one in kept] == [OTHER_TEAM_PATH]
    assert await world.repository.find_source(LATER_SHARED) is not None


async def test_a_second_source_under_the_same_request_does_not_plan_the_first_again(
    world: RemovalWorld,
) -> None:
    """One request id, two `--source` commands: what the first finished is not the second's."""
    assert (await world.service().execute(await plan_the_named_file(world))).completed

    second = await world.service().plan(
        SourceSelector(EARLIER), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM
    )

    assert [(source.sha256, source.inclusion) for source in second.sources] == [(EARLIER, Inclusion.NAMED)]
    assert second.later_uploads == () and second.earlier_versions == ()


# ------------------------------------------------------------------------------------------------
# --team with --include-shared: the one place a team removal has later uploads
# ------------------------------------------------------------------------------------------------

ZALU_ROUND_3 = "Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-Aff-Grove City Invitational-Round 3.docx"
ZALU_REVISION = _docx(("Grove City Invitational, Round 3, affirmative.", "Cedar Hollow's own revision."))
ZALU_REVISION_SHA256 = hashlib.sha256(ZALU_REVISION).hexdigest()
SHARED = hashlib.sha256(DOCUMENT_BODIES["grove-round-1-aff"]).hexdigest()


async def import_a_fourth_week_revising_the_other_teams_copy(world: RemovalWorld, scratch: Path) -> None:
    """A weekly of `2026-09-22` holding one member: other bytes at Cedar Hollow ZaLu's Round 3 path.

    That path held the shared Round 1 affirmative's bytes in `2026-09-08` and `2026-09-15`.
    """
    archive = scratch / "testcl26-weekly-2026-09-22.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w") as built:
        built.writestr(zipfile.ZipInfo(ZALU_ROUND_3, date_time=(1980, 1, 1, 0, 0, 0)), ZALU_REVISION)
    week = date(2026, 9, 22)
    report = await CaselistImportService(
        caselists=world.repository,
        blobs=FsSnapshotStore(world.data_dir),
        suppression=empty_suppression_list(),
    ).import_archive(
        read_archive(archive, **LIMITS),
        caselist="testcl26",
        snapshot=week,
        event=Event.LD,
        archive_sha256=archive_digest(archive),
    )
    write_manifest(report, FsEvidenceObjectStore(world.data_dir).path_for(manifest_key("testcl26", week)))
    publisher = CaselistPublishService(
        local=world.local, remote=world.bucket, suppression=empty_suppression_list()
    )
    assert (await publisher.execute(await publisher.plan("testcl26"))).succeeded


async def test_a_team_removal_withdrawing_a_shared_file_has_no_later_uploads(
    removal_world: RemovalWorld, tmp_path: Path
) -> None:
    """Without `--include-shared` the shared file leaves the team's paths only, which the team names."""
    await import_a_fourth_week_revising_the_other_teams_copy(removal_world, tmp_path / "week-four")

    plan = await removal_world.service().plan(
        parse_team_selector(TEAM), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM
    )

    assert plan.later_uploads == () and plan.earlier_versions == ()
    assert plan.source(ZALU_REVISION_SHA256) is None
    assert {source.inclusion for source in plan.sources} == {Inclusion.NAMED}


async def test_a_shared_file_named_by_source_and_skipped_has_no_later_uploads(
    removal_world: RemovalWorld, tmp_path: Path
) -> None:
    """`--source` on a shared file without `--include-shared` does nothing to it, so nothing follows it."""
    await import_a_fourth_week_revising_the_other_teams_copy(removal_world, tmp_path / "week-four")

    plan = await removal_world.service().plan(
        SourceSelector(SHARED), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_SITE_ADMIN
    )

    assert [(source.sha256, source.disposition) for source in plan.sources] == [
        (SHARED, Disposition.SKIP_SHARED)
    ]
    assert plan.later_uploads == () and plan.earlier_versions == ()
    assert plan.nothing_to_do


async def test_a_team_removal_with_include_shared_adds_the_later_upload_at_the_other_holders_path(
    removal_world: RemovalWorld, tmp_path: Path
) -> None:
    """With it the shared file goes from Cedar Hollow ZaLu's path too, and so does what followed it there."""
    await import_a_fourth_week_revising_the_other_teams_copy(removal_world, tmp_path / "week-four")
    service = removal_world.service()

    plan = await service.plan(
        parse_team_selector(TEAM),
        request_id=REQUEST,
        reason=ReasonCode.REQUESTED_BY_TEAM,
        include_shared=True,
    )

    assert [(one.sha256, one.of_sha256, one.snapshots) for one in plan.later_uploads] == [
        (ZALU_REVISION_SHA256, SHARED, ("2026-09-22",))
    ]
    added = plan.source(ZALU_REVISION_SHA256)
    assert added is not None
    assert (added.inclusion, added.disposition) == (Inclusion.LATER_UPLOAD, Disposition.REMOVE)

    assert (await service.execute(plan)).completed

    assert not FsSnapshotStore(removal_world.data_dir).path_for(ZALU_REVISION_SHA256).exists()
    assert versions_of(removal_world, raw_key(ZALU_REVISION_SHA256)) == []
