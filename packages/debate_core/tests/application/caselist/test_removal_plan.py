"""The removal plan: what `caselist remove` would do, worked out before anything is deleted.

Every count asserted here was worked out by hand from the fixture's own tables
(`tests/fixtures/caselist/build_synthetic_archives.py`, `tests/fixtures/caselist/expected_summary.json`)
and is written beside the reasoning, never read back from a run (working agreements §6).

The synthetic team removed throughout is `Maple Grove/QX`, which across the three weeks disclosed:

| Body | 09-01 | 09-08 | 09-15 | Also held by |
|---|---|---|---|---|
| grove-round-1-aff | Round 1 | Round 1, (1) | Round 1, (1) | ZaLu's Round 3 (09-08 on); a camp file |
| grove-round-2-neg-first | Round 2 | — | — | nobody |
| grove-round-2-neg-revised | — | Round 2 | Round 2 | nobody |
| bayview-semis-neg | — | — | Bayview Semis | nobody |

and in every week two junk members under its directories: the `__MACOSX/…/._` AppleDouble twin and
the `~$` Word lock file of the Round 1 affirmative.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any

import pytest
from tests.fixtures.caselist.build_synthetic_archives import DOCUMENT_BODIES, SYNTHETIC_CASELIST

from debate_core.application.caselist.removal_plan import (
    Disposition,
    InvalidRemovalRequest,
    ObjectKind,
    RemovalPlan,
    Side,
    SourceSelector,
    TeamSelector,
    parse_team_selector,
)
from debate_core.application.errors import StoreAccessDenied
from debate_core.application.ports.evidence_versions import ObjectVersion
from debate_core.application.ports.suppression import ReasonCode, SuppressionAction

from .conftest import REQUEST, TEAM, RemovalWorld

pytestmark = pytest.mark.anyio

ROUND_1 = "Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1.docx"
ROUND_1_COPY = "Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1 (1).docx"


def digest(body: str) -> str:
    return hashlib.sha256(DOCUMENT_BODIES[body]).hexdigest()


SHARED = digest("grove-round-1-aff")
EXCLUSIVE = {
    digest("grove-round-2-neg-first"),
    digest("grove-round-2-neg-revised"),
    digest("bayview-semis-neg"),
}


async def plan_team(world: RemovalWorld, *, include_shared: bool = False, **planner: Any) -> RemovalPlan:
    return await world.planner(**planner).plan(
        parse_team_selector(TEAM),
        request_id=REQUEST,
        reason=ReasonCode.REQUESTED_BY_TEAM,
        include_shared=include_shared,
    )


def manifest(snapshot: str) -> str:
    return f"manifests/{SYNTHETIC_CASELIST}/{snapshot}.jsonl"


# ------------------------------------------------------------------------------------------------
# --team, without --include-shared
# ------------------------------------------------------------------------------------------------


class TestATeamRemoval:
    async def test_the_teams_own_files_are_removed_and_the_shared_one_withdrawn(
        self, removal_world: RemovalWorld
    ) -> None:
        plan = await plan_team(removal_world)

        assert {source.sha256 for source in plan.of(Disposition.REMOVE)} == EXCLUSIVE
        (withdrawn,) = plan.of(Disposition.WITHDRAW)
        assert withdrawn.sha256 == SHARED
        assert withdrawn.other_teams == 1, "Cedar Hollow/ZaLu"
        assert withdrawn.camp_file_holders == 1, "the Tamarack camp file"
        assert not withdrawn.local_blob, "the other holders still need the bytes"

    async def test_every_disclosure_record_of_the_team_is_listed_and_no_one_elses(
        self, removal_world: RemovalWorld
    ) -> None:
        plan = await plan_team(removal_world)

        records = [ref for source in plan.sources for ref in source.disclosures]
        # 2 in the first week, 3 in the second, 4 in the third.
        assert len(records) == 9
        assert {(ref.school, ref.team_code) for ref in records} == {("Maple Grove", "QX")}
        by_week = {
            week: sum(1 for ref in records if ref.snapshot == week)
            for week in {ref.snapshot for ref in records}
        }
        assert by_week == {date(2026, 9, 1): 2, date(2026, 9, 8): 3, date(2026, 9, 15): 4}
        assert plan.local_records == 9 + 3, "nine disclosures and three source documents"

    async def test_the_suppression_entries_are_three_whole_files_and_two_withdrawn_paths(
        self, removal_world: RemovalWorld
    ) -> None:
        plan = await plan_team(removal_world)

        entries = plan.suppression_entries
        assert {entry.sha256 for entry in entries if entry.disclosure is None} == EXCLUSIVE
        scoped = [entry for entry in entries if entry.disclosure is not None]
        assert len(scoped) == 2, "the Round 1 path and its (1) re-upload"
        assert {entry.sha256 for entry in scoped} == {SHARED}
        assert all(
            entry.request_id == REQUEST and entry.action is SuppressionAction.SUPPRESS for entry in entries
        )
        for entry in entries:
            assert "Maple Grove" not in entry.to_line() and "QX" not in entry.to_line()

    async def test_every_row_of_the_team_comes_out_of_every_copy_of_every_manifest(
        self, removal_world: RemovalWorld
    ) -> None:
        plan = await plan_team(removal_world)

        dropped = {(rewrite.key, rewrite.side): rewrite.rows_dropped for rewrite in plan.manifests}
        # Two files and two junk entries; three files and two junk; four files and two junk.
        expected = {manifest("2026-09-01"): 4, manifest("2026-09-08"): 5, manifest("2026-09-15"): 6}
        assert dropped == {
            (key, side): count for key, count in expected.items() for side in (Side.LOCAL, Side.BUCKET)
        }
        for rewrite in plan.manifests:
            assert not [
                line for line in rewrite.lines if "Maple Grove/QX" in line or "Maple Grove-QX" in line
            ]
            assert rewrite.lines[-1].startswith('{"archive_sha256"'), "the summary row is last"

    async def test_the_summary_moves_each_dropped_member_to_suppressed(
        self, removal_world: RemovalWorld
    ) -> None:
        plan = await plan_team(removal_world)
        summaries = {
            rewrite.key: json.loads(rewrite.lines[-1])
            for rewrite in plan.manifests
            if rewrite.side is Side.LOCAL
        }

        # 09-01: NEW 4, of which the team's Round 1 and Round 2. Members are a fact about the archive.
        first = summaries[manifest("2026-09-01")]
        assert first["classifications"] == {"NEW": 2, "SUPPRESSED": 2}
        assert first["members"] == 4 + 3, "four files and the three junk members of the zip build"
        assert first["distinct_sha256"] == 2
        # 09-15: NEW 2 UNCHANGED 12 REMOVED 1. The team's three UNCHANGED and Bayview's NEW go.
        third = summaries[manifest("2026-09-15")]
        assert third["classifications"] == {"NEW": 1, "REMOVED": 1, "SUPPRESSED": 4, "UNCHANGED": 9}
        assert third["distinct_sha256"] == 10, "12 bodies, less the revised Round 2 and Bayview"

    async def test_the_local_blobs_and_bucket_copies_of_the_teams_files_are_listed_with_versions(
        self, removal_world: RemovalWorld
    ) -> None:
        plan = await plan_team(removal_world)

        local = {planned.sha256 for planned in plan.objects_on(Side.LOCAL) if planned.kind is ObjectKind.BLOB}
        assert local == EXCLUSIVE
        bucket = plan.objects_on(Side.BUCKET)
        assert {planned.key for planned in bucket} == {
            f"raw/caselist/{SYNTHETIC_CASELIST}/sha256/{sha[0:2]}/{sha[2:4]}/{sha}" for sha in EXCLUSIVE
        }, "the shared file's caselist copy stays: Cedar Hollow/ZaLu still holds it there"
        assert plan.versions_counted
        assert all(planned.versions is not None and len(planned.versions) == 1 for planned in bucket)
        for rewrite in plan.manifests_on(Side.BUCKET):
            assert rewrite.versions == 1

    async def test_a_dry_run_changes_nothing_anywhere(self, removal_world: RemovalWorld) -> None:
        tree, versions, records = removal_world.tree(), removal_world.versions(), removal_world.records()

        await plan_team(removal_world)
        await plan_team(removal_world, include_shared=True)

        assert removal_world.tree() == tree
        assert removal_world.versions() == versions
        assert removal_world.records() == records
        assert not (removal_world.data_dir / "suppression").exists()


# ------------------------------------------------------------------------------------------------
# --include-shared, and --source
# ------------------------------------------------------------------------------------------------


class TestSharedFiles:
    async def test_with_include_shared_the_shared_file_goes_for_everyone(
        self, removal_world: RemovalWorld
    ) -> None:
        plan = await plan_team(removal_world, include_shared=True)

        assert {source.sha256 for source in plan.of(Disposition.REMOVE)} == EXCLUSIVE | {SHARED}
        (shared,) = [source for source in plan.sources if source.sha256 == SHARED]
        assert {(ref.school, ref.team_code) for ref in shared.disclosures} == {
            ("Maple Grove", "QX"),
            ("Cedar Hollow", "ZaLu"),
        }
        assert len(shared.camp_files) == 1
        assert shared.local_blob
        keys = {planned.key for planned in plan.objects_on(Side.BUCKET)}
        assert f"raw/caselist/{SYNTHETIC_CASELIST}/sha256/{SHARED[0:2]}/{SHARED[2:4]}/{SHARED}" in keys
        assert f"raw/openev/2026/sha256/{SHARED[0:2]}/{SHARED[2:4]}/{SHARED}" in keys
        assert "manifests/openev/2026-policy.jsonl" in {rewrite.key for rewrite in plan.manifests}

    async def test_a_shared_file_named_by_source_is_skipped_without_include_shared(
        self, removal_world: RemovalWorld
    ) -> None:
        plan = await removal_world.planner().plan(
            SourceSelector(SHARED), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_SITE_ADMIN
        )

        (skipped,) = plan.sources
        assert skipped.disposition is Disposition.SKIP_SHARED
        assert skipped.other_teams == 2 and skipped.camp_file_holders == 1
        assert plan.nothing_to_do

    async def test_junk_that_shadows_a_removed_file_goes_even_when_its_team_stays(
        self, removal_world: RemovalWorld
    ) -> None:
        """`--source` leaves the team's other files, but the Finder and Word junk naming this one goes.

        09-01 holds the Round 1 affirmative once, with its `__MACOSX/…/._` twin and its `~$` lock file:
        three rows. 09-08 and 09-15 add the (1) re-upload and Cedar Hollow/ZaLu's Round 3: five each.
        """
        plan = await removal_world.planner().plan(
            SourceSelector(SHARED),
            request_id=REQUEST,
            reason=ReasonCode.REQUESTED_BY_SITE_ADMIN,
            include_shared=True,
        )

        dropped = {
            rewrite.key: rewrite.rows_dropped for rewrite in plan.manifests if rewrite.side is Side.LOCAL
        }
        assert dropped[manifest("2026-09-01")] == 3
        assert dropped[manifest("2026-09-08")] == 5
        for rewrite in plan.manifests:
            assert not [line for line in rewrite.lines if "Grove City Invitational-Round 1" in line]
            if rewrite.key == manifest("2026-09-15"):
                assert [line for line in rewrite.lines if "Maple Grove/QX" in line], (
                    "the team's other files stay"
                )

    async def test_a_file_only_one_team_holds_is_removed_by_source(self, removal_world: RemovalWorld) -> None:
        bayview = digest("bayview-semis-neg")

        plan = await removal_world.planner().plan(
            SourceSelector(bayview), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM
        )

        (removed,) = plan.sources
        assert removed.disposition is Disposition.REMOVE
        assert {(rewrite.key, rewrite.rows_dropped) for rewrite in plan.manifests} == {
            (manifest("2026-09-15"), 1)
        }


# ------------------------------------------------------------------------------------------------
# What the plan can and cannot see
# ------------------------------------------------------------------------------------------------


class OperatorCredentialVersions:
    """The everyday profile's view of versions: `s3:ListBucketVersions` is not granted."""

    location = "s3://denied"

    async def list_versions(self, prefix: str) -> tuple[ObjectVersion, ...]:
        raise StoreAccessDenied("ListObjectVersions", f"s3://denied/{prefix}")

    async def get_version_file(self, version: ObjectVersion, destination: Any) -> None:  # pragma: no cover
        raise StoreAccessDenied("GetObject", version.key)

    async def delete_versions(self, versions: Any) -> int:  # pragma: no cover - a plan never deletes
        raise AssertionError("a plan deleted something")


class TestWithOnlyTheEverydayProfile:
    async def test_versions_are_reported_as_not_counted_and_everything_else_is_planned(
        self, removal_world: RemovalWorld
    ) -> None:
        counted = await plan_team(removal_world)
        uncounted = await plan_team(removal_world, versions=OperatorCredentialVersions())

        assert not uncounted.versions_counted
        assert {planned.key for planned in uncounted.objects} == {planned.key for planned in counted.objects}
        assert all(planned.versions is None for planned in uncounted.objects_on(Side.BUCKET))
        assert [rewrite.lines for rewrite in uncounted.manifests] == [
            rewrite.lines for rewrite in counted.manifests
        ]

    async def test_a_team_is_resolved_from_the_bucket_when_this_machine_has_nothing(
        self, removal_world: RemovalWorld, tmp_path: Any
    ) -> None:
        """A second machine, or prod after its own local store was purged: the manifests still say."""
        from .conftest import RemovalWorld as World

        empty = World(
            data_dir=tmp_path / "empty", bucket_name=removal_world.bucket_name, client=removal_world.client
        )
        plan = await plan_team(empty)

        assert {source.sha256 for source in plan.of(Disposition.REMOVE)} == EXCLUSIVE
        assert {source.sha256 for source in plan.of(Disposition.WITHDRAW)} == {SHARED}
        assert {rewrite.side for rewrite in plan.manifests} == {Side.BUCKET}
        assert len(plan.objects_on(Side.BUCKET)) == 3


class TestSelectors:
    @pytest.mark.parametrize(
        "text",
        ["testcl26/Maple Grove", "Maple Grove/QX/extra/parts", "TESTCL/Maple Grove/QX", "testcl26//QX"],
    )
    def test_a_malformed_team_is_refused_without_repeating_it(self, text: str) -> None:
        with pytest.raises(InvalidRemovalRequest) as refused:
            parse_team_selector(text)
        assert "Maple Grove" not in str(refused.value)

    def test_a_team_selector_reads_the_directories_the_archive_uses(self) -> None:
        team = parse_team_selector(TEAM)
        assert team == TeamSelector(caselist="testcl26", school="Maple Grove", team_code="QX")
        assert team.holds("testcl26", ROUND_1)
        assert team.holds("testcl26", "__MACOSX/Maple Grove/QX/._Maple Grove-QX-Aff.docx")
        assert not team.holds("testcl26", "Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-AFF-Harbor Classic.docx")
        assert not team.holds("hsld26", ROUND_1)

    def test_a_source_must_be_a_digest(self) -> None:
        with pytest.raises(InvalidRemovalRequest):
            SourceSelector("not-a-digest")

    async def test_a_request_id_must_be_a_register_id(self, removal_world: RemovalWorld) -> None:
        with pytest.raises(InvalidRemovalRequest, match="RM-"):
            await removal_world.planner().plan(
                parse_team_selector(TEAM), request_id="Maple Grove asked", reason=ReasonCode.REQUESTED_BY_TEAM
            )
