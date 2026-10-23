"""What `caselist status` reports after a removal can be cleared, and says whose it is (`v1-e30-t19`).

Four gaps `v1-e30-t15`, `v1-e30-t12` and `v1-e30-t16` left, each built here against moto with the
real planner, executor and status:

1. **A rewritten manifest's older version that names nothing removed.** Status counts it, and the
   re-run's sweep kept it, because the sweep deleted only versions that name a removed file. The
   sweep now also deletes a noncurrent version of a key an earlier run of the *same request*
   rewrote, when it is older than that rewrite. Nothing else: not the current version, not the
   rewrite, not a version newer than it, and not a version of a key no run of the request rewrote.
2. **A request that only withdrew shared files.** Its first run deleted the team's records and
   rows, so its re-run found no path of the team's and planned no aggregates. The withdrawal record
   (`withdrawals.jsonl`, `v1-e30-t16`) still says which caselist each copy was taken from, and the
   re-run reads it.
3. **The dry run's line.** A plan whose execution would sweep a manifest version counts it, and is
   never "nothing left".
4. **A withdrawn copy's residue.** What the bucket still holds of a copy withdrawn from a caselist
   that keeps no holder of it, named by that caselist and the request, from the withdrawal record; a
   withdrawal an earlier build made, with no record, is *not attributed*.

Every expected count is worked out by hand beside the step that causes it (working agreement 6).

## The fixtures

* Gaps 1 and 3 use `v1-e30-t15`'s: `--source` the Seaside Cup round 5 affirmative under
  `RM-2026-01`, which is in the week of 2026-09-15 only and which no other team holds, so its
  removal rewrites `manifests/testcl26/2026-09-15.jsonl` alone.
* Gap 2: a team that only ever disclosed a shared file. The weekly window of 2026-09-22 holds the
  Grove City round 1 affirmative's bytes at an invented team's path, :data:`OAK_RIDGE_PATH`. Maple
  Grove/QX and Cedar Hollow/ZaLu hold the same bytes in `testcl26`, and a camp file does too, so
  `--team testcl26/Oak Ridge/LmNo` withdraws it and removes nothing.
* Gap 4 uses `v1-e30-t16`'s: `--source` the Bayview semifinal negative under `RM-2026-07`, with its
  revision at the same path in `testcl26`'s 2026-09-22 window and at Cedar Hollow/ZaLu's path in
  `testclb26`'s. The revision is withdrawn from `testcl26`, where no one else holds it, so its copy
  there is deleted, and kept in `testclb26`.
"""

from __future__ import annotations

import hashlib
import zipfile
from collections.abc import Sequence
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest
from tests.fixtures.caselist.build_synthetic_archives import DOCUMENT_BODIES, SYNTHETIC_CASELIST

from debate_core.application.caselist.import_service import CaselistImportService
from debate_core.application.caselist.manifest import manifest_key, write_manifest
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.removal_plan import (
    Disposition,
    ObjectKind,
    RemovalPlan,
    Side,
    SourceSelector,
    parse_team_selector,
)
from debate_core.application.caselist.removal_residue import OlderVersions, RemovalCompletion
from debate_core.application.caselist.removal_service import TakedownAccess
from debate_core.application.ports.evidence_versions import EvidenceVersionStore, ObjectVersion
from debate_core.application.ports.suppression import (
    ManifestRewriteRecord,
    ReasonCode,
    RemovalLogEntry,
    RemovalLogKind,
    RemovalOutcome,
    RemovalScopeEntry,
    RemovalSelectorKind,
    SuppressionAction,
    SuppressionEntry,
    WithdrawalEntry,
    disclosure_digest,
)
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsEvidenceObjectStore, FsSnapshotStore
from debate_core.integrations.local.archive_reader import archive_digest, read_archive
from debate_core.integrations.s3 import S3EvidenceVersionStore
from debate_core.testing.fakes.suppression import empty_suppression_list

from .conftest import REMOVAL_TIME, REQUEST, RemovalWorld
from .test_manifest_and_aggregate_residue import (
    LONG_BEFORE,
    NOT_REWRITTEN,
    OPENEV_MANIFEST,
    PARSER_VERSIONS,
    REMOVED,
    REWRITTEN,
    RefusesUnder,
    aggregate_key,
    backdate,
    current_bytes,
    of,
    put,
    remove,
    status,
    versions_of,
)
from .test_removal_covers_later_camp_uploads import (
    REVISED_SHA256,
    a_team_discloses_the_revised_camp_file,
    pulled_then_revised,
)
from .test_removal_covers_later_camp_uploads import raw_key as camp_raw_key
from .test_removal_covers_later_uploads import LIMITS
from .test_removal_names_other_holders import (
    ANOTHER_TEAMS_PATH,
    BAYVIEW_PATH,
    NAMED,
    NEXT_WEEK,
    OTHER_CASELIST,
    REVISION,
    import_and_publish_another_caselists_week,
    import_and_publish_next_week,
    remove_the_named_file,
)
from .test_removal_names_other_holders import REQUEST as BAYVIEW_REQUEST
from .test_removal_withdraws_one_camp_path import remove as remove_the_camp_file
from .test_sync_skips_suppressed_downloads import CASELIST as CAMP_CASELIST

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

COMPLETED: Final = REMOVAL_TIME
"""Every run's completion: the removal's clock is fixed there, the re-run's too."""
INSIDE_THE_RUN: Final = COMPLETED - timedelta(minutes=2)
"""When a real run writes its rewrite: during the run, before its log entry."""
REWRITTEN_KEY: Final = REWRITTEN[0]
AN_OLD_BODY: Final = b'{"kind":"summary","note":"the manifest as it was, naming nothing removed"}\n'
"""A version of a manifest from before the removal that names no file at all."""


def a_member_row_of(sha256: str) -> bytes:
    return b'{"kind":"member","path":"a path","sha256":"' + sha256.encode() + b'"}\n'


@pytest.fixture
async def removed(removal_world: RemovalWorld) -> RemovalWorld:
    """`RM-2026-01` removed the round 5 affirmative, its rewrite put back inside the run."""
    await remove(removal_world)
    (rewrite,) = versions_of(removal_world, REWRITTEN_KEY)
    backdate(removal_world, REWRITTEN_KEY, rewrite, INSIDE_THE_RUN)
    return removal_world


def rewrite_of(world: RemovalWorld) -> str:
    """The version id `RM-2026-01`'s scope records as its rewrite of the one manifest."""
    return versions_of(world, REWRITTEN_KEY)[-1]


async def plan_again(world: RemovalWorld, *, versions: EvidenceVersionStore | None = None) -> RemovalPlan:
    return await world.planner(versions=versions).plan(
        SourceSelector(REMOVED), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM
    )


# ------------------------------------------------------------------------------------------------
# Gap 1: a rewritten manifest's older version that names nothing removed
# ------------------------------------------------------------------------------------------------


class TestARewrittenManifestsOlderVersion:
    async def test_one_that_names_nothing_removed_is_cleared_by_the_same_removal_run_again(
        self, removed: RemovalWorld
    ) -> None:
        """Status counts it; the re-run deletes it, because the request rewrote its key after it."""
        world = removed
        rewrite = rewrite_of(world)
        old = put(world, REWRITTEN_KEY, AN_OLD_BODY, written=LONG_BEFORE)
        assert of(await status(world), SYNTHETIC_CASELIST).older_versions == (
            OlderVersions(role="manifest", versions=1),
        )

        await remove(world)

        assert old not in versions_of(world, REWRITTEN_KEY)
        assert versions_of(world, REWRITTEN_KEY) == [rewrite]
        cleared = await status(world)
        assert of(cleared, SYNTHETIC_CASELIST).older_versions == ()
        assert cleared.in_sync

    async def test_only_versions_older_than_the_rewrite_of_a_key_the_removal_rewrote_go(
        self, removed: RemovalWorld, tmp_path: Path
    ) -> None:
        """One version goes; five stay, each for its own reason.

        | Version | Stays because |
        |---|---|
        | the rewritten key's, a day before | it goes: older than the rewrite |
        | the rewrite itself, now noncurrent | it is the rewrite |
        | the key re-published after the removal, then again | newer than the rewrite; the second is current |
        | the week the removal never rewrote, a day before | no run of the request rewrote its key |
        | the camp release's manifest, a day before | the same, in another caselist |

        None of them names the removed file, so the sweep's other rule takes none of them.
        """
        world = removed
        rewrite = rewrite_of(world)
        old = put(world, REWRITTEN_KEY, AN_OLD_BODY, written=LONG_BEFORE)
        same_bytes = tmp_path / "republished.jsonl"
        same_bytes.write_bytes(current_bytes(world, REWRITTEN_KEY))
        newer = (await world.bucket.put_file(REWRITTEN_KEY, same_bytes)).version_id
        current = (await world.bucket.put_file(REWRITTEN_KEY, same_bytes)).version_id
        never_rewritten = put(world, NOT_REWRITTEN, current_bytes(world, NOT_REWRITTEN), written=LONG_BEFORE)
        camp = put(world, OPENEV_MANIFEST, current_bytes(world, OPENEV_MANIFEST), written=LONG_BEFORE)
        others_before = {key: versions_of(world, key) for key in (NOT_REWRITTEN, OPENEV_MANIFEST)}

        await remove(world)

        assert set(versions_of(world, REWRITTEN_KEY)) == {current, newer, rewrite}
        assert old not in versions_of(world, REWRITTEN_KEY)
        assert {key: versions_of(world, key) for key in (NOT_REWRITTEN, OPENEV_MANIFEST)} == others_before
        assert never_rewritten in versions_of(world, NOT_REWRITTEN)
        assert camp in versions_of(world, OPENEV_MANIFEST)

    async def test_a_version_the_store_lists_as_current_is_kept_whatever_its_time(
        self, removed: RemovalWorld
    ) -> None:
        """S3 states times to the second; the current version is never the sweep's, by either rule.

        The takedown's listing here says the old version is current, as a store whose times and
        order disagree would.
        """
        world = removed
        old = put(world, REWRITTEN_KEY, AN_OLD_BODY, written=LONG_BEFORE)
        inner = S3EvidenceVersionStore(bucket=world.bucket_name, client=world.client)

        class ListsTheOldVersionAsCurrent(RefusesUnder):
            async def list_versions(self, prefix: str) -> tuple[ObjectVersion, ...]:
                listed = await inner.list_versions(prefix)
                return tuple(
                    replace(version, is_latest=version.version_id == old)
                    if version.key == REWRITTEN_KEY
                    else version
                    for version in listed
                )

            async def get_version_file(self, version: ObjectVersion, destination: Path) -> None:
                await inner.get_version_file(version, destination)

            async def delete_versions(self, versions: Sequence[ObjectVersion]) -> int:
                return await inner.delete_versions(versions)

        listing = ListsTheOldVersionAsCurrent(inner, "nothing/")

        def takedown() -> TakedownAccess:
            return replace(world.takedown(), versions=listing)

        service = world.service(takedown=takedown)
        await service.execute(
            await service.plan(
                SourceSelector(REMOVED), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM
            )
        )

        assert old in versions_of(world, REWRITTEN_KEY)

    async def test_a_rewrite_the_bucket_no_longer_holds_leaves_what_status_counts_to_be_cleared(
        self, removed: RemovalWorld, tmp_path: Path
    ) -> None:
        """`v1-e30-t24` changed this from "sweeps nothing of its key". The run completed, and a
        completed run's versions are held to its completion, which the log records, and not to the
        rewrite: status counts the old version without the rewrite, so the re-run takes it. A run
        that stopped is still held to its rewrite, and without it nothing of the key is taken
        (`test_status_and_the_sweep_share_one_rule.py`, `TestARunThatStopped`)."""
        world = removed
        rewrite = rewrite_of(world)
        old = put(world, REWRITTEN_KEY, AN_OLD_BODY, written=LONG_BEFORE)
        same_bytes = tmp_path / "republished.jsonl"
        same_bytes.write_bytes(current_bytes(world, REWRITTEN_KEY))
        republished = (await world.bucket.put_file(REWRITTEN_KEY, same_bytes)).version_id
        world.client.delete_object(Bucket=world.bucket_name, Key=REWRITTEN_KEY, VersionId=rewrite)
        assert of(await status(world), SYNTHETIC_CASELIST).older_versions == (
            OlderVersions(role="manifest", versions=1),
        )

        await remove(world)

        assert old not in versions_of(world, REWRITTEN_KEY)
        assert versions_of(world, REWRITTEN_KEY) == [republished]
        assert of(await status(world), SYNTHETIC_CASELIST).older_versions == ()

    async def test_a_version_stamped_in_the_same_moment_as_the_rewrite_is_not_older_than_it(
        self, removed: RemovalWorld, tmp_path: Path
    ) -> None:
        """S3 states a version's time to the second. Two versions of one second are not ordered by it,
        so the sweep keeps both: the rewrite, and one put in the same moment. A re-publish sits on top
        of them, so neither is current."""
        world = removed
        rewrite = rewrite_of(world)
        same_moment = put(world, REWRITTEN_KEY, AN_OLD_BODY, written=INSIDE_THE_RUN)
        same_bytes = tmp_path / "republished.jsonl"
        same_bytes.write_bytes(current_bytes(world, REWRITTEN_KEY))
        await world.bucket.put_file(REWRITTEN_KEY, same_bytes)

        await remove(world)

        assert {same_moment, rewrite} <= set(versions_of(world, REWRITTEN_KEY))

    async def test_a_key_that_only_begins_with_the_rewritten_one_is_another_key(
        self, removed: RemovalWorld
    ) -> None:
        """The rewritten key is listed by its own name as a prefix. A key that starts with it, such as
        a copy someone saved beside it, is another key, and no removal reached it."""
        world = removed
        beside = f"{REWRITTEN_KEY}.bak"
        put(world, beside, AN_OLD_BODY, written=LONG_BEFORE)
        kept = put(world, beside, AN_OLD_BODY, written=LONG_BEFORE + timedelta(hours=1))

        await remove(world)

        assert len(versions_of(world, beside)) == 2
        assert kept in versions_of(world, beside)

    async def test_a_delete_marker_older_than_the_rewrite_is_left(self, removed: RemovalWorld) -> None:
        """A marker holds nothing, and is no version the purge should have taken."""
        world = removed
        marker = str(world.client.delete_object(Bucket=world.bucket_name, Key=REWRITTEN_KEY)["VersionId"])
        backdate(world, REWRITTEN_KEY, marker, LONG_BEFORE)

        await remove(world)

        assert (REWRITTEN_KEY, marker) in world.versions()

    @pytest.mark.parametrize(
        ("request_id", "environment"),
        [("RM-2026-12", "dev"), (REQUEST, "prod")],
        ids=["another request", "another environment"],
    )
    async def test_a_key_only_another_requests_or_environments_run_rewrote_is_not_this_requests(
        self, removed: RemovalWorld, request_id: str, environment: str
    ) -> None:
        """The week the round 5 affirmative was never in, rewritten by a run that is not this one's."""
        world = removed
        (published,) = versions_of(world, NOT_REWRITTEN)
        old = put(world, NOT_REWRITTEN, AN_OLD_BODY, written=LONG_BEFORE)
        elsewhere = RemovalLogEntry(
            kind=RemovalLogKind.REMOVAL,
            recorded_at=COMPLETED - timedelta(hours=1),
            request_id=request_id,
            reason=ReasonCode.REQUESTED_BY_TEAM,
            environment=environment,
            outcome=RemovalOutcome.COMPLETED,
            selector=RemovalSelectorKind.SOURCE,
        )
        await world.removal_log().append(
            [elsewhere],
            scopes=[
                RemovalScopeEntry(
                    recorded_at=elsewhere.recorded_at,
                    request_id=request_id,
                    environment=environment,
                    caselists=(SYNTHETIC_CASELIST,),
                    manifest_rewrites=(ManifestRewriteRecord(key=NOT_REWRITTEN, version_id=published),),
                )
            ],
        )

        await remove(world)

        assert old in versions_of(world, NOT_REWRITTEN)


# ------------------------------------------------------------------------------------------------
# Gap 2: a request that only withdrew shared files
# ------------------------------------------------------------------------------------------------

OAK_RIDGE: Final = f"{SYNTHETIC_CASELIST}/Oak Ridge/LmNo"
OAK_RIDGE_PATH: Final = "Oak Ridge/LmNo/Oak Ridge-LmNo-Aff-Grove City Invitational-Round 4.docx"
"""An invented team's path, holding bytes two other teams and a camp file hold too."""
SHARED: Final = hashlib.sha256(DOCUMENT_BODIES["grove-round-1-aff"]).hexdigest()
WITHDRAWAL_ONLY: Final = "RM-2026-11"
WINDOW: Final = date(2026, 9, 22)
AGGREGATE: Final = aggregate_key(SYNTHETIC_CASELIST, PARSER_VERSIONS[0], "index.jsonl")
WITHDRAWALS_KEY: Final = "manifests/_suppression/withdrawals.jsonl"


async def import_and_publish_oak_ridges_week(world: RemovalWorld, scratch: Path) -> None:
    """`testcl26`'s weekly window of 2026-09-22: the shared bytes at :data:`OAK_RIDGE_PATH`."""
    archive = scratch / f"{SYNTHETIC_CASELIST}-weekly-{WINDOW.isoformat()}.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as written:
        written.writestr(OAK_RIDGE_PATH, DOCUMENT_BODIES["grove-round-1-aff"])
    importer = CaselistImportService(
        caselists=world.repository,
        blobs=FsSnapshotStore(world.data_dir),
        suppression=empty_suppression_list(),
    )
    week = await importer.import_archive(
        read_archive(archive, **LIMITS),
        caselist=SYNTHETIC_CASELIST,
        snapshot=WINDOW,
        event=Event.LD,
        archive_sha256=archive_digest(archive),
    )
    write_manifest(
        week, FsEvidenceObjectStore(world.data_dir).path_for(manifest_key(SYNTHETIC_CASELIST, WINDOW))
    )
    publisher = CaselistPublishService(
        local=world.local, remote=world.bucket, suppression=empty_suppression_list()
    )
    assert (await publisher.execute(await publisher.plan(SYNTHETIC_CASELIST))).succeeded


async def withdraw_oak_ridge(world: RemovalWorld) -> RemovalPlan:
    """`caselist remove --team testcl26/Oak Ridge/LmNo --request RM-2026-11`, executed."""
    service = world.service()
    plan = await service.plan(
        parse_team_selector(OAK_RIDGE), request_id=WITHDRAWAL_ONLY, reason=ReasonCode.REQUESTED_BY_TEAM
    )
    assert (await service.execute(plan)).completed
    return plan


def aggregates_planned(plan: RemovalPlan) -> list[str]:
    return [one.key for one in plan.objects_on(Side.BUCKET) if one.kind is ObjectKind.PARSED_AGGREGATE]


def shared_copy_in_the_caselist() -> str:
    return f"raw/caselist/{SYNTHETIC_CASELIST}/sha256/{SHARED[:2]}/{SHARED[2:4]}/{SHARED}"


@pytest.fixture
async def withdrawn_only(removal_world: RemovalWorld, tmp_path: Path) -> RemovalWorld:
    """Oak Ridge's request ran once and completed; then an index older than it is in the bucket.

    What a run that stopped before the aggregates, or a version put back, leaves. The first run's
    own plan withdraws the one file and removes nothing.
    """
    world = removal_world
    await import_and_publish_oak_ridges_week(world, tmp_path / "oak-ridge")
    first = await withdraw_oak_ridge(world)
    assert first.of(Disposition.REMOVE) == ()
    assert [one.sha256 for one in first.of(Disposition.WITHDRAW)] == [SHARED]
    put(world, AGGREGATE, b"a withdrawn card's row\n", written=LONG_BEFORE)
    return world


class TestAWithdrawalOnlyRequest:
    async def test_its_aggregate_residue_is_cleared_by_the_same_removal_run_again(
        self, withdrawn_only: RemovalWorld
    ) -> None:
        world = withdrawn_only
        residue = of(await status(world), SYNTHETIC_CASELIST)
        assert residue.older_versions == (OlderVersions(role="index.jsonl", versions=1),)
        assert residue.older_than == RemovalCompletion(request_id=WITHDRAWAL_ONLY, completed_at=COMPLETED)

        rerun = await withdraw_oak_ridge(world)

        assert aggregates_planned(rerun) == [AGGREGATE]
        cleared = await status(world)
        assert of(cleared, SYNTHETIC_CASELIST).older_versions == ()
        assert cleared.in_sync
        # Maple Grove/QX and Cedar Hollow/ZaLu still hold it in testcl26: its copy there stays.
        assert world.client.head_object(Bucket=world.bucket_name, Key=shared_copy_in_the_caselist())

    async def test_without_a_withdrawal_record_the_rerun_has_no_caselist_to_plan_aggregates_for(
        self, withdrawn_only: RemovalWorld
    ) -> None:
        """What a first run by a build from before `v1-e30-t16` leaves: the list's disclosure entry,
        with no record beside it of the caselist the copy was taken from."""
        world = withdrawn_only
        (world.data_dir / "suppression" / "withdrawals.jsonl").unlink()
        world.client.delete_object(Bucket=world.bucket_name, Key=WITHDRAWALS_KEY)

        rerun = await world.planner().plan(
            parse_team_selector(OAK_RIDGE), request_id=WITHDRAWAL_ONLY, reason=ReasonCode.REQUESTED_BY_TEAM
        )

        assert aggregates_planned(rerun) == []
        assert [one.sha256 for one in rerun.of(Disposition.WITHDRAW)] == [SHARED]

    async def test_another_requests_withdrawal_of_the_same_file_is_not_this_requests(
        self, withdrawn_only: RemovalWorld
    ) -> None:
        """`RM-2026-12` withdrew the same bytes from `testclb26`, before Oak Ridge's request: its
        caselist is no caselist `RM-2026-11` reached, and the re-run plans nothing there."""
        world = withdrawn_only
        elsewhere = disclosure_digest(OTHER_CASELIST, ANOTHER_TEAMS_PATH)
        earlier = COMPLETED - timedelta(days=1)
        await world.suppression().append_withdrawals(
            [
                WithdrawalEntry(
                    sha256=SHARED,
                    disclosure=elsewhere,
                    caselist=OTHER_CASELIST,
                    recorded_at=earlier,
                    reason=ReasonCode.REQUESTED_BY_TEAM,
                    request_id="RM-2026-12",
                )
            ]
        )
        await world.suppression().append(
            [
                SuppressionEntry(
                    action=SuppressionAction.SUPPRESS,
                    sha256=SHARED,
                    disclosure=elsewhere,
                    recorded_at=earlier,
                    reason=ReasonCode.REQUESTED_BY_TEAM,
                    request_id="RM-2026-12",
                )
            ]
        )

        rerun = await world.planner().plan(
            parse_team_selector(OAK_RIDGE), request_id=WITHDRAWAL_ONLY, reason=ReasonCode.REQUESTED_BY_TEAM
        )

        replanned = rerun.source(SHARED)
        assert replanned is not None
        assert replanned.withdrawn_earlier_from == (SYNTHETIC_CASELIST,)


# ------------------------------------------------------------------------------------------------
# Gap 3: the dry run says what the execution's sweep will delete
# ------------------------------------------------------------------------------------------------


class TestTheDryRun:
    async def test_a_plan_whose_execution_would_sweep_a_version_is_not_nothing_left(
        self, removed: RemovalWorld
    ) -> None:
        """Two versions, one by each rule: the rewritten key's older one, and a version of the week
        the removal never rewrote that names the removed file, as a re-import's publish leaves."""
        world = removed
        older = put(world, REWRITTEN_KEY, AN_OLD_BODY, written=LONG_BEFORE)
        naming = put(world, NOT_REWRITTEN, a_member_row_of(REMOVED), written=LONG_BEFORE)
        put(world, NOT_REWRITTEN, current_bytes(world, NOT_REWRITTEN))

        plan = await plan_again(world)

        assert not plan.nothing_to_do
        assert plan.manifests == ()
        assert sorted((one.key, one.version_id) for one in plan.superseded_versions or ()) == sorted(
            [(REWRITTEN_KEY, older), (NOT_REWRITTEN, naming)]
        )

    async def test_a_manifest_the_plan_rewrites_again_is_counted_as_rewritten_and_not_swept(
        self, removed: RemovalWorld, tmp_path: Path
    ) -> None:
        """A version naming the removed file published over the rewrite: the re-run rewrites the
        key again and purges every other version of it, which the plan counts there. Its older
        versions are not counted a second time as swept."""
        world = removed
        put(world, REWRITTEN_KEY, AN_OLD_BODY, written=LONG_BEFORE)
        *rows, summary = current_bytes(world, REWRITTEN_KEY).decode().splitlines()
        naming = tmp_path / "naming.jsonl"
        lines = [*rows, a_member_row_of(REMOVED).decode().strip(), summary]
        naming.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
        await world.bucket.put_file(REWRITTEN_KEY, naming)

        plan = await plan_again(world)

        assert [(rewrite.key, rewrite.side) for rewrite in plan.manifests] == [(REWRITTEN_KEY, Side.BUCKET)]
        assert plan.superseded_versions == ()

    async def test_the_execution_deletes_the_versions_its_dry_run_counted(
        self, removed: RemovalWorld
    ) -> None:
        world = removed
        put(world, REWRITTEN_KEY, AN_OLD_BODY, written=LONG_BEFORE)
        put(world, NOT_REWRITTEN, a_member_row_of(REMOVED), written=LONG_BEFORE)
        put(world, NOT_REWRITTEN, current_bytes(world, NOT_REWRITTEN))
        before = set(world.versions())
        counted = {(one.key, one.version_id) for one in (await plan_again(world)).superseded_versions or ()}

        await remove(world)

        assert before - set(world.versions()) == counted

    async def test_a_plan_with_nothing_to_sweep_is_still_nothing_left(self, removed: RemovalWorld) -> None:
        plan = await plan_again(removed)

        assert plan.superseded_versions == ()
        assert plan.nothing_to_do

    async def test_a_sweep_the_profile_may_not_list_is_not_counted_and_never_nothing_left(
        self, removed: RemovalWorld
    ) -> None:
        everyday = S3EvidenceVersionStore(bucket=removed.bucket_name, client=removed.client)

        plan = await plan_again(removed, versions=RefusesUnder(everyday, "manifests/"))

        assert plan.superseded_versions is None
        assert not plan.nothing_to_do


# ------------------------------------------------------------------------------------------------
# Gap 4: a withdrawn copy's residue, attributed to the caselist it was withdrawn from
# ------------------------------------------------------------------------------------------------


def revision_copy_in(caselist: str) -> str:
    return f"raw/caselist/{caselist}/sha256/{REVISION[:2]}/{REVISION[2:4]}/{REVISION}"


@pytest.fixture
async def withdrawn_from_one_caselist(removal_world: RemovalWorld, tmp_path: Path) -> RemovalWorld:
    """`RM-2026-07` removed the Bayview negative and withdrew its revision from `testcl26`; then a
    current object of the revision is back under `testcl26`, as a takedown that stopped leaves one."""
    world = removal_world
    await import_and_publish_next_week(world, tmp_path / "next-week", (BAYVIEW_PATH,))
    await import_and_publish_another_caselists_week(world, tmp_path / "other-caselist")
    await remove_the_named_file(world)
    assert versions_of(world, revision_copy_in(SYNTHETIC_CASELIST)) == []
    world.client.put_object(Bucket=world.bucket_name, Key=revision_copy_in(SYNTHETIC_CASELIST), Body=b"left")
    return world


class TestAWithdrawnCopysResidue:
    async def test_the_same_removal_run_again_takes_it(
        self, withdrawn_from_one_caselist: RemovalWorld
    ) -> None:
        world = withdrawn_from_one_caselist

        await remove_the_named_file(world)

        assert versions_of(world, revision_copy_in(SYNTHETIC_CASELIST)) == []
        assert versions_of(world, revision_copy_in(OTHER_CASELIST)), "testclb26's copy is its holder's"

    async def test_status_names_the_caselist_it_was_withdrawn_from_and_the_request(
        self, withdrawn_from_one_caselist: RemovalWorld
    ) -> None:
        from debate_core.application.caselist.removal_residue import WithdrawnCopy

        report = await status(withdrawn_from_one_caselist)

        assert of(report, SYNTHETIC_CASELIST).withdrawn_copies == (
            WithdrawnCopy(sha256=REVISION, request_id=BAYVIEW_REQUEST, current_objects=1),
        )
        assert of(report, OTHER_CASELIST).withdrawn_copies == ()
        assert report.withdrawals_not_attributed == ()
        # Since v1-e30-t24 (the PM's ruling on this task's question 1) it fails the comparison, as a
        # removed file's residue does: `test_withdrawn_copies_fail_status.py`.
        assert not report.in_sync

    async def test_a_withdrawal_an_earlier_build_made_is_not_attributed(
        self, withdrawn_from_one_caselist: RemovalWorld
    ) -> None:
        world = withdrawn_from_one_caselist
        (world.data_dir / "suppression" / "withdrawals.jsonl").unlink()
        world.client.delete_object(Bucket=world.bucket_name, Key=WITHDRAWALS_KEY)

        report = await status(world)

        assert report.withdrawals_not_attributed == (BAYVIEW_REQUEST,)
        assert of(report, SYNTHETIC_CASELIST).withdrawn_copies == ()

    async def test_a_copy_withdrawn_from_a_caselist_another_holder_keeps_is_not_reported(
        self, withdrawn_only: RemovalWorld
    ) -> None:
        """Oak Ridge's copy was withdrawn from `testcl26`, where Maple Grove/QX and Cedar Hollow/ZaLu
        still hold the same bytes: the current object there is theirs."""
        report = await status(withdrawn_only)

        assert of(report, SYNTHETIC_CASELIST).withdrawn_copies == ()
        assert report.withdrawals_not_attributed == ()


class TestWhatTheWithdrawalRecordDoesNotDo:
    async def test_a_withdrawn_row_still_on_this_machine_is_no_holder_of_the_copy(
        self, removal_world: RemovalWorld, tmp_path: Path
    ) -> None:
        """A run that stopped before this machine's manifests: `testcl26`'s 2026-09-22 still has the
        revision's row at the withdrawn path. The list stops that row, so the caselist keeps no
        holder of the file, and the copy left there is still the withdrawal's."""
        world = removal_world
        await import_and_publish_next_week(world, tmp_path / "next-week", (BAYVIEW_PATH,))
        await import_and_publish_another_caselists_week(world, tmp_path / "other-caselist")
        local_manifest = FsEvidenceObjectStore(world.data_dir).path_for(
            manifest_key(SYNTHETIC_CASELIST, NEXT_WEEK)
        )
        before = local_manifest.read_bytes()
        await remove_the_named_file(world)
        local_manifest.write_bytes(before)
        world.client.put_object(
            Bucket=world.bucket_name, Key=revision_copy_in(SYNTHETIC_CASELIST), Body=b"left"
        )

        report = await status(world)

        assert [copy.sha256 for copy in of(report, SYNTHETIC_CASELIST).withdrawn_copies] == [REVISION]

    async def test_a_withdrawal_since_unsuppressed_is_not_reported(
        self, withdrawn_from_one_caselist: RemovalWorld
    ) -> None:
        """`caselist unsuppress` lifts every suppression of the file: its copy may come back."""
        world = withdrawn_from_one_caselist
        lifted = SuppressionEntry(
            action=SuppressionAction.UNSUPPRESS,
            sha256=REVISION,
            recorded_at=COMPLETED + timedelta(days=1),
            reason=ReasonCode.REMOVED_IN_ERROR,
            request_id=BAYVIEW_REQUEST,
        )
        await world.suppression().append([lifted])

        report = await status(world)

        assert of(report, SYNTHETIC_CASELIST).withdrawn_copies == ()
        assert report.withdrawals_not_attributed == ()

    async def test_it_never_has_a_file_removed_whole(self, withdrawn_from_one_caselist: RemovalWorld) -> None:
        """`testclb26`'s holder gone as well, by hand: planned on the record's account, the revision
        would now be held nowhere and removed whole. It is not planned at all."""
        world = withdrawn_from_one_caselist
        assert await world.repository.delete_disclosure(OTHER_CASELIST, NEXT_WEEK, ANOTHER_TEAMS_PATH)
        FsEvidenceObjectStore(world.data_dir).path_for(manifest_key(OTHER_CASELIST, NEXT_WEEK)).unlink()
        world.client.delete_object(Bucket=world.bucket_name, Key=manifest_key(OTHER_CASELIST, NEXT_WEEK))

        plan = await world.planner().plan(
            SourceSelector(NAMED), request_id=BAYVIEW_REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM
        )

        assert plan.source(REVISION) is None


@pytest.fixture
def camp_world(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> RemovalWorld:
    return RemovalWorld(data_dir=tmp_path / "evidence", bucket_name=evidence_bucket, client=s3_client)


class TestACampPathsWithdrawnCopy:
    """`v1-e30-t14`'s world: camp file 640 is a later upload at a removed camp path, and a team
    disclosed the same bytes too, so it is withdrawn from its camp path and kept for the team, and
    no release holds it any more. A copy left under `raw/openev/` is the withdrawal's."""

    async def test_status_names_it_under_openev_and_the_same_removal_run_again_takes_it(
        self, camp_world: RemovalWorld, tmp_path: Path
    ) -> None:
        world = camp_world
        await pulled_then_revised(world)
        await a_team_discloses_the_revised_camp_file(world, tmp_path / "weekly")
        await remove_the_camp_file(world)
        team_copy = (
            f"raw/caselist/{CAMP_CASELIST}/sha256/{REVISED_SHA256[:2]}/{REVISED_SHA256[2:4]}/{REVISED_SHA256}"
        )
        assert versions_of(world, camp_raw_key(REVISED_SHA256)) == []
        world.client.put_object(Bucket=world.bucket_name, Key=camp_raw_key(REVISED_SHA256), Body=b"left")

        before = await status(world)
        await remove_the_camp_file(world)
        after = await status(world)

        assert [copy.sha256 for copy in of(before, "openev").withdrawn_copies] == [REVISED_SHA256]
        assert versions_of(world, camp_raw_key(REVISED_SHA256)) == []
        assert len(versions_of(world, team_copy)) == 1, "the team's copy is its holder's"
        assert of(after, "openev").withdrawn_copies == ()
