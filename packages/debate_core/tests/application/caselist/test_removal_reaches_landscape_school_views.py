"""A removal reaches the landscape bundles' school views, and nothing else of them (`v1-e32-t13`).

The plan lists, and `--execute` deletes, the `schools.csv` and `schools.md` of every landscape
bundle of the caselist the removal touches, on this machine and in the bucket, every version
included; every circuit-wide file and every other caselist's bundle stay byte for byte (ac1). And
`caselist status` reports a school view a removal should have deleted as residue, until it is gone
(ac2).

Every bucket is moto's, versioned, and every removal is the real one, with its clock fixed at
:data:`~.conftest.REMOVAL_TIME`. The bundles are written here by hand beside the synthetic store,
each with the seven files `v1-e32-t04` names, spelled out below rather than read from the code
(working agreements §6):

* `testcl26` 2026-09-15 and 2026-09-29: the synthetic caselist, which every removal here touches;
* `othercl26` 2026-09-29: another caselist's bundle;
* `testcl26b` 2026-09-29: a directory whose name begins with `testcl26`. No real caselist slug can be
  a prefix of another (`^[a-z]+[0-9]{2}$`), so this stands in for one, as the PM asked.

In the bucket each school view has two versions and each circuit-wide file one, `testcl26`'s
`report.md` excepted, which has two, so a noncurrent circuit-wide version is there to be left. All
of them are backdated before the removal (:func:`backdate`, as `v1-e30-t15`'s tests do), and every
local file's modification time is set before it too, as a bundle a weekly run wrote would be.

The file removed is the Seaside Cup round 5 affirmative: in the `testcl26` week of 2026-09-15 only,
no camp file, no other holder (the fixture facts `test_manifest_and_aggregate_residue.py` rests on).
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from moto.core.models import DEFAULT_ACCOUNT_ID
from moto.s3.models import FakeKey, s3_backends
from tests.fixtures.caselist.build_synthetic_archives import SYNTHETIC_CASELIST
from tests.fixtures.caselist.publish_expectations import digest_of_body

from debate_core.application.caselist.removal_plan import RemovalPlan, Side, SourceSelector
from debate_core.application.caselist.removal_residue import OlderVersions, RemovalCompletion
from debate_core.application.caselist.removal_school_views import SchoolViewReach, UnknownLandscapeFile
from debate_core.application.caselist.status_service import CaselistStatusService
from debate_core.application.errors import StoreAccessDenied
from debate_core.application.ports.evidence_versions import EvidenceVersionStore, ObjectVersion
from debate_core.application.ports.suppression import ReasonCode
from debate_core.integrations.local.fs_version_store import FsEvidenceVersionStore
from debate_core.integrations.s3 import S3EvidenceVersionStore

from .conftest import REMOVAL_TIME, REQUEST, RemovalWorld

pytestmark = pytest.mark.anyio

REMOVED = digest_of_body("seaside-round-5-aff")
WRITTEN = REMOVAL_TIME - timedelta(days=1)
"""When every bundle file's current version was written: well before the removal."""
FIRST_WRITTEN = WRITTEN - timedelta(days=7)
"""When a school view's first, now noncurrent, version was written."""

SCHOOL_VIEW_FILES = ("schools.csv", "schools.md")
CIRCUIT_WIDE_FILES = ("report.md", "positions.csv", "top_cards.csv", "impact_cards.csv", "trends.csv")
BUNDLES = (
    ("testcl26", "2026-09-15"),
    ("testcl26", "2026-09-29"),
    ("othercl26", "2026-09-29"),
    ("testcl26b", "2026-09-29"),
)

REMOVED_VIEWS = (
    "reports/landscape/testcl26/2026-09-15/schools.csv",
    "reports/landscape/testcl26/2026-09-15/schools.md",
    "reports/landscape/testcl26/2026-09-29/schools.csv",
    "reports/landscape/testcl26/2026-09-29/schools.md",
)
"""What every removal here reaches: written by hand from the bundles above."""


# ------------------------------------------------------------------------------------------------
# The bundles
# ------------------------------------------------------------------------------------------------


def backdate(world: RemovalWorld, key: str, version_id: str, when: datetime) -> None:
    """Set the `LastModified` moto lists for one version, keeping the key's versions in time order.

    The helper `test_manifest_and_aggregate_residue.py` documents, for the same reason: moto stamps
    what it writes with the time the test runs, which is after the removal's fixed clock.
    """
    stored: list[FakeKey] = (
        s3_backends[DEFAULT_ACCOUNT_ID]["aws"].get_bucket(world.bucket_name).keys.getlist(key)
    )
    (matching,) = [one for one in stored if one.version_id == version_id]
    matching.last_modified = when.astimezone(UTC).replace(tzinfo=None)
    stored.sort(key=lambda one: one.last_modified)


def put(world: RemovalWorld, key: str, body: bytes, *, written: datetime | None = None) -> str:
    version_id = str(world.client.put_object(Bucket=world.bucket_name, Key=key, Body=body)["VersionId"])
    if written is not None:
        backdate(world, key, version_id, written)
    return version_id


def write_local(world: RemovalWorld, key: str, body: bytes, *, written: datetime | None = None) -> Path:
    path = world.data_dir / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    if written is not None:
        os.utime(path, (written.timestamp(), written.timestamp()))
    return path


def body(key: str, version: int = 2) -> bytes:
    """Synthetic bytes, different for every key and version, so a swapped file would show."""
    return f"synthetic {key} version {version}\nMaple Grove,QX\n".encode()


def write_bundle_file(world: RemovalWorld, key: str, *, versions: int) -> None:
    write_local(world, key, body(key), written=WRITTEN)
    if versions == 2:
        put(world, key, body(key, 1), written=FIRST_WRITTEN)
    put(world, key, body(key), written=WRITTEN)


def write_school_views(
    world: RemovalWorld, caselist: str, snapshot: str, *, written: datetime | None
) -> None:
    """One bundle's school views again, on both sides: one version each, at `written` (now if `None`)."""
    for name in SCHOOL_VIEW_FILES:
        key = f"reports/landscape/{caselist}/{snapshot}/{name}"
        write_local(world, key, body(key, 3), written=written)
        put(world, key, body(key, 3), written=written)


@pytest.fixture
async def bundles(removal_world: RemovalWorld) -> RemovalWorld:
    for caselist, snapshot in BUNDLES:
        for name in (*SCHOOL_VIEW_FILES, *CIRCUIT_WIDE_FILES):
            key = f"reports/landscape/{caselist}/{snapshot}/{name}"
            two = name in SCHOOL_VIEW_FILES or (caselist, snapshot, name) == (
                "testcl26",
                "2026-09-15",
                "report.md",
            )
            write_bundle_file(removal_world, key, versions=2 if two else 1)
    return removal_world


def bucket_reports(world: RemovalWorld) -> dict[tuple[str, str], bytes]:
    """Every version under `reports/`, delete markers as empty bytes, by (key, version id)."""
    listed = world.client.list_object_versions(Bucket=world.bucket_name, Prefix="reports/")
    found: dict[tuple[str, str], bytes] = {}
    for version in listed.get("Versions", []):
        key, version_id = str(version.get("Key")), str(version.get("VersionId"))
        found[(key, version_id)] = world.client.get_object(
            Bucket=world.bucket_name, Key=key, VersionId=version_id
        )["Body"].read()
    for marker in listed.get("DeleteMarkers", []):
        found[(str(marker.get("Key")), str(marker.get("VersionId")))] = b""
    return found


def local_reports(world: RemovalWorld) -> dict[str, bytes]:
    root = world.data_dir / "reports"
    return {
        path.relative_to(world.data_dir).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


async def plan_of(world: RemovalWorld, *, versions: EvidenceVersionStore | None = None) -> RemovalPlan:
    return await world.planner(versions=versions).plan(
        SourceSelector(REMOVED), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM
    )


async def removed(world: RemovalWorld) -> None:
    """`caselist remove --source <the round 5 affirmative> --request RM-2026-01 --execute`."""
    service = world.service()
    report = await service.execute(await service.plan(SourceSelector(REMOVED), **_asked()))
    assert report.completed


def _asked() -> dict[str, object]:
    return {"request_id": REQUEST, "reason": ReasonCode.REQUESTED_BY_TEAM}


class ReportsVersionsRefused:
    """The bucket's versions as the everyday profile sees them in dev and prod: listed under the
    evidence prefixes, refused under `reports/` (`operator_access.tf`)."""

    def __init__(self, inner: EvidenceVersionStore) -> None:
        self._inner = inner

    @property
    def location(self) -> str:
        return self._inner.location

    async def list_versions(self, prefix: str) -> tuple[ObjectVersion, ...]:
        if prefix.startswith("reports/"):
            raise StoreAccessDenied("ListObjectVersions", f"s3://bucket/{prefix}")
        return await self._inner.list_versions(prefix)

    async def get_version_file(self, version: ObjectVersion, destination: Path) -> None:
        await self._inner.get_version_file(version, destination)

    async def delete_versions(self, versions: object) -> int:
        raise AssertionError("the everyday profile deletes nothing")


def everyday(world: RemovalWorld) -> ReportsVersionsRefused:
    return ReportsVersionsRefused(S3EvidenceVersionStore(bucket=world.bucket_name, client=world.client))


# ------------------------------------------------------------------------------------------------
# The plan (ac1)
# ------------------------------------------------------------------------------------------------


class TestThePlan:
    async def test_it_lists_exactly_the_removed_caselists_school_views_here_and_in_the_bucket(
        self, bundles: RemovalWorld
    ) -> None:
        plan = await plan_of(bundles)

        assert [(one.side, one.key) for one in plan.school_views] == [
            *((Side.LOCAL, key) for key in REMOVED_VIEWS),
            *((Side.BUCKET, key) for key in REMOVED_VIEWS),
        ]
        assert [len(one.versions or ()) for one in plan.school_views] == [1, 1, 1, 1, 2, 2, 2, 2]
        assert plan.school_view_reach == (SchoolViewReach(SYNTHETIC_CASELIST),)
        assert plan.school_view_versions_counted
        assert not plan.nothing_to_do

    async def test_it_names_the_newest_snapshots_bundle_to_republish_and_republishes_nothing(
        self, bundles: RemovalWorld
    ) -> None:
        before = bucket_reports(bundles), local_reports(bundles)

        plan = await plan_of(bundles)

        assert plan.republish == ((SYNTHETIC_CASELIST, date(2026, 9, 29)),)
        assert (bucket_reports(bundles), local_reports(bundles)) == before

    async def test_where_the_everyday_profile_lists_no_versions_it_lists_the_current_files_uncounted(
        self, bundles: RemovalWorld
    ) -> None:
        plan = await plan_of(bundles, versions=everyday(bundles))

        assert [
            (one.side, one.key, one.versions) for one in plan.school_views if one.side is Side.BUCKET
        ] == [(Side.BUCKET, key, None) for key in REMOVED_VIEWS]
        assert not plan.school_view_versions_counted
        assert plan.versions_counted, "the evidence prefixes' versions are still counted"

    async def test_a_file_in_neither_list_in_the_removed_caselists_bundle_stops_the_plan(
        self, bundles: RemovalWorld
    ) -> None:
        write_local(bundles, "reports/landscape/testcl26/2026-09-29/notes.txt", b"stray\n")

        with pytest.raises(UnknownLandscapeFile) as refused:
            await plan_of(bundles)

        assert refused.value.key == "reports/landscape/testcl26/2026-09-29/notes.txt"

    async def test_one_in_the_bucket_stops_it_too(self, bundles: RemovalWorld) -> None:
        put(bundles, "reports/landscape/testcl26/schools.csv", b"not in a snapshot\n")

        with pytest.raises(UnknownLandscapeFile):
            await plan_of(bundles)

    async def test_a_file_in_neither_list_in_another_caselists_bundle_is_left_alone(
        self, bundles: RemovalWorld
    ) -> None:
        write_local(bundles, "reports/landscape/othercl26/2026-09-29/notes.txt", b"stray\n")
        put(bundles, "reports/landscape/testcl26b/2026-09-29/notes.txt", b"stray\n")

        plan = await plan_of(bundles)

        assert len(plan.school_views) == 8


# ------------------------------------------------------------------------------------------------
# The execution (ac1)
# ------------------------------------------------------------------------------------------------


class TestTheExecution:
    async def test_it_deletes_them_and_their_noncurrent_versions_and_leaves_everything_else_byte_for_byte(
        self, bundles: RemovalWorld
    ) -> None:
        bucket_before, local_before = bucket_reports(bundles), local_reports(bundles)
        service = bundles.service()

        report = await service.execute(await service.plan(SourceSelector(REMOVED), **_asked()))

        assert report.completed
        assert bucket_reports(bundles) == {
            (key, version): data for (key, version), data in bucket_before.items() if key not in REMOVED_VIEWS
        }
        assert local_reports(bundles) == {
            key: data for key, data in local_before.items() if key not in REMOVED_VIEWS
        }
        assert (report.school_view_files_deleted, report.school_view_versions_deleted) == (4, 8)

    async def test_a_version_the_dry_run_could_not_see_goes_by_the_same_rule(
        self, bundles: RemovalWorld
    ) -> None:
        """A delete made without a version id hides a view under a marker: the everyday listing shows
        nothing of it, and the removal profile's listing shows every version and the marker."""
        hidden = "reports/landscape/testcl26/2026-09-15/schools.md"
        bundles.client.delete_object(Bucket=bundles.bucket_name, Key=hidden)
        bucket_before = bucket_reports(bundles)
        plan = await plan_of(bundles, versions=everyday(bundles))
        assert hidden not in {one.key for one in plan.school_views if one.side is Side.BUCKET}

        report = await bundles.service().execute(plan)

        assert report.completed
        assert bucket_reports(bundles) == {
            (key, version): data for (key, version), data in bucket_before.items() if key not in REMOVED_VIEWS
        }
        assert report.school_view_versions_deleted == 9, "eight versions and the marker"

    async def test_the_log_and_the_scope_beside_it_hold_counts_and_no_key(
        self, bundles: RemovalWorld
    ) -> None:
        await removed(bundles)

        lines = [line for record in (bundles.removal_log().records) for line in await record.read_lines()]
        scopes = [scope.to_line() for scope in await bundles.removal_log().scopes()]
        assert lines and scopes
        for line in (*lines, *scopes):
            assert "reports/" not in line
            assert "schools" not in line
            assert "Maple Grove" not in line


# ------------------------------------------------------------------------------------------------
# The same removal run again
# ------------------------------------------------------------------------------------------------


class TestARerun:
    async def test_it_leaves_a_view_written_after_the_removal_such_as_the_republished_one(
        self, bundles: RemovalWorld
    ) -> None:
        await removed(bundles)
        write_school_views(bundles, SYNTHETIC_CASELIST, "2026-09-29", written=None)

        plan = await plan_of(bundles)

        assert plan.school_view_reach == (
            SchoolViewReach(SYNTHETIC_CASELIST, older_than=RemovalCompletion(REQUEST, REMOVAL_TIME)),
        )
        assert plan.school_views == ()
        assert plan.nothing_to_do

    async def test_it_takes_a_view_older_than_the_run_that_left_it(self, bundles: RemovalWorld) -> None:
        """What a build from before this one left: the run completed and never reached the views."""
        await removed(bundles)
        write_school_views(bundles, SYNTHETIC_CASELIST, "2026-09-15", written=WRITTEN)

        plan = await plan_of(bundles)
        report = await bundles.service().execute(plan)

        assert [(one.side, one.key) for one in plan.school_views] == [
            (Side.LOCAL, REMOVED_VIEWS[0]),
            (Side.LOCAL, REMOVED_VIEWS[1]),
            (Side.BUCKET, REMOVED_VIEWS[0]),
            (Side.BUCKET, REMOVED_VIEWS[1]),
        ]
        assert (report.school_view_files_deleted, report.school_view_versions_deleted) == (2, 2)
        assert not [key for key in local_reports(bundles) if key in REMOVED_VIEWS]
        assert not [key for key, _ in bucket_reports(bundles) if key in REMOVED_VIEWS]


# ------------------------------------------------------------------------------------------------
# `caselist status` (ac2)
# ------------------------------------------------------------------------------------------------


def status_of(world: RemovalWorld) -> CaselistStatusService:
    return CaselistStatusService(
        local=world.local,
        remote=world.bucket,
        suppression=world.suppression(),
        versions=S3EvidenceVersionStore(bucket=world.bucket_name, client=world.client),
        removal_log=world.removal_log(),
        environment="dev",
        local_reports=FsEvidenceVersionStore(world.data_dir),
    )


class TestStatus:
    async def test_it_reports_views_a_removal_should_have_deleted_as_residue_and_clears_once_they_are_gone(
        self, bundles: RemovalWorld
    ) -> None:
        await removed(bundles)
        for snapshot in ("2026-09-15", "2026-09-29"):
            write_school_views(bundles, SYNTHETIC_CASELIST, snapshot, written=WRITTEN)

        report = await status_of(bundles).status(residue=True)

        (residue,) = [one for one in report.residue if one.caselist == SYNTHETIC_CASELIST]
        assert residue.school_views == (
            OlderVersions(role="school view", versions=4),
            OlderVersions(role="local school view", versions=4),
        )
        assert residue.school_views_older_than == RemovalCompletion(REQUEST, REMOVAL_TIME)
        assert residue.found and not report.in_sync

        await removed(bundles)
        report = await status_of(bundles).status(residue=True)

        (residue,) = [one for one in report.residue if one.caselist == SYNTHETIC_CASELIST]
        assert residue.school_views == ()

    async def test_a_view_written_after_the_removal_is_not_residue(self, bundles: RemovalWorld) -> None:
        await removed(bundles)
        write_school_views(bundles, SYNTHETIC_CASELIST, "2026-09-29", written=None)

        report = await status_of(bundles).status(residue=True)

        (residue,) = [one for one in report.residue if one.caselist == SYNTHETIC_CASELIST]
        assert residue.school_views == ()

    async def test_a_caselist_no_removal_touched_reports_none_however_old_its_views(
        self, bundles: RemovalWorld
    ) -> None:
        """Before any removal, every view is older than nothing."""
        report = await status_of(bundles).status(residue=True)

        assert all(one.school_views == () for one in report.residue)
