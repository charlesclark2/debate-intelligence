"""What an import does when weekly windows and complete archives arrive out of date order (`v1-e30-t17`).

A weekly archive is a window of about a week's editing, and the complete archive is the cumulative
copy. The importer's ordering rule was written for cumulative weeklies. These tests record what an
import actually does when the archives arrive in another order, against answers worked out by hand in
`tests/fixtures/caselist/build_window_order_archives.py` before any of them ran
(`docs/process/working-agreements.md` §6).

The importer is the real one over a real data directory, built as the composition root builds it,
with the first-seen reader; each manifest is written as `caselist import` and `caselist pull` write
it. The held-path tests make the removal through the removal service against moto, as
`caselist remove` does, so the hold's date is the one a removal computes from the manifests it finds.
"""

from __future__ import annotations

import functools
import json
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_window_order_archives import (
    CASELIST,
    EXPECTED_HOLDS,
    EXPECTED_IMPORTS,
    EXPECTED_LATER_UPLOADS,
    FIRST_WEEK,
    SCENARIOS,
    SECOND_WEEK,
    THIRD_WEEK,
    ExpectedHold,
    ExpectedImport,
    Step,
    build_complete_archive_zips,
    build_weekly_zips,
    digest_of,
)

from debate_core.application.caselist.evidence_listing import (
    LocalEvidence,
    digests_in_earlier_manifests,
    snapshots_before_full_archive,
)
from debate_core.application.caselist.import_service import (
    CaselistImportService,
    Classification,
    ImportReport,
    SnapshotOutOfOrder,
)
from debate_core.application.caselist.manifest import full_archive_manifest_key, manifest_key, write_manifest
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.removal_path_versions import VersionRelation
from debate_core.application.caselist.removal_plan import RemovalPlan, SourceSelector
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.ports.suppression import ReasonCode, SuppressionList
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsEvidenceObjectStore, FsSnapshotStore, SqliteDatabase
from debate_core.integrations.local.archive_reader import archive_digest, read_archive
from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository
from debate_core.integrations.local.suppression_list import local_suppression_list_file
from debate_core.testing.fakes import empty_suppression_list

from .conftest import REQUEST, RemovalWorld

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

LIMITS = {"max_archive_bytes": 64 * 1024 * 1024, "max_unpacked_bytes": 64 * 1024 * 1024}


class OrderedImports:
    """One data directory, the fixture's archives, and the imports `caselist import` and `pull` make."""

    def __init__(self, root: Path) -> None:
        self.data_dir = root / "evidence"
        self.weekly = build_weekly_zips(root / "downloads")
        self.complete = build_complete_archive_zips(root / "downloads")

    @property
    def local(self) -> LocalEvidence:
        objects = FsEvidenceObjectStore(self.data_dir)
        blobs = FsEvidenceObjectStore(self.data_dir, subdirectory=Path("blobs"))
        return LocalEvidence(
            objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
        )

    @property
    def repository(self) -> SqliteCaselistRepository:
        return SqliteCaselistRepository(SqliteDatabase.open(self.data_dir))

    def importer(self, suppression: SuppressionList | None = None) -> CaselistImportService:
        """The importer as the composition root builds it, first-seen reader included."""
        return CaselistImportService(
            caselists=self.repository,
            blobs=FsSnapshotStore(self.data_dir),
            suppression=suppression or empty_suppression_list(),
            earlier_manifest_digests=functools.partial(digests_in_earlier_manifests, self.local),
        )

    async def run(self, step: Step, suppression: SuppressionList | None = None) -> ImportReport:
        """Import one archive and write its manifest, as the command that imports it does."""
        if step.kind == "weekly":
            archive = self.weekly[step.day]
            report = await self.importer(suppression).import_archive(
                read_archive(archive, **LIMITS),
                caselist=CASELIST,
                snapshot=step.day,
                event=Event.LD,
                archive_sha256=archive_digest(archive),
                allow_out_of_order=step.allow_out_of_order,
            )
            write_manifest(report, self.manifest_path(step.snapshot))
            return report
        archive = self.complete[step.day]
        previous, earlier = await snapshots_before_full_archive(self.local, CASELIST, step.day)
        report = await self.importer(suppression).import_full_archive(
            read_archive(archive, **LIMITS),
            caselist=CASELIST,
            archive_date=step.day,
            event=Event.LD,
            archive_sha256=archive_digest(archive),
            previous=previous,
            earlier=earlier,
        )
        write_manifest(report, self.manifest_path(step.snapshot))
        return report

    async def outcome(self, step: Step, suppression: SuppressionList | None = None) -> ExpectedImport:
        """What one import reported, in the fixture's terms; a refusal is an outcome too."""
        try:
            report = await self.run(step, suppression)
        except SnapshotOutOfOrder as refused:
            return ExpectedImport(step.snapshot, None, {}, refused_by=refused.latest.isoformat())
        return outcome_of(report)

    def manifest_path(self, snapshot: str) -> Path:
        full = snapshot.removeprefix("full/")
        key = (
            full_archive_manifest_key(CASELIST, date.fromisoformat(full))
            if full != snapshot
            else manifest_key(CASELIST, date.fromisoformat(snapshot))
        )
        return FsEvidenceObjectStore(self.data_dir).path_for(key)

    def manifest_bytes(self, snapshot: str) -> bytes:
        return self.manifest_path(snapshot).read_bytes()

    def summary(self, snapshot: str) -> dict[str, object]:
        rows = [json.loads(line) for line in self.manifest_bytes(snapshot).decode("utf-8").splitlines()]
        (summary,) = [row for row in rows if row["kind"] == "summary"]
        return summary


def outcome_of(report: ImportReport) -> ExpectedImport:
    def named(day: date) -> str:
        return f"full/{day.isoformat()}" if report.full_archive else day.isoformat()

    withdrawals = report.withdrawals
    return ExpectedImport(
        snapshot=named(report.snapshot),
        previous=named(report.previous_snapshot) if report.previous_snapshot is not None else None,
        counts={str(name): report.count(name) for name in Classification if report.count(name)},
        first_seen=report.first_seen,
        withdrawals=(
            (withdrawals.withdrawn, withdrawals.superseded, withdrawals.earlier_snapshots)
            if withdrawals is not None
            else None
        ),
        held=report.held_at_removed_paths,
    )


async def imported(root: Path, steps: tuple[Step, ...]) -> OrderedImports:
    store = OrderedImports(root)
    for step in steps:
        await store.run(step)
    return store


# ------------------------------------------------------------------------------------------------
# Every scenario, against the answers worked out by hand
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", list(SCENARIOS))
async def test_each_import_reports_what_the_fixture_works_out_by_hand(scenario: str, tmp_path: Path) -> None:
    store = OrderedImports(tmp_path)

    outcomes = [await store.outcome(step) for step in SCENARIOS[scenario]]

    assert outcomes == list(EXPECTED_IMPORTS[scenario])


# ------------------------------------------------------------------------------------------------
# A weekly after a later one
# ------------------------------------------------------------------------------------------------


async def test_what_is_stored_does_not_depend_on_the_order_the_weeks_arrived_in(tmp_path: Path) -> None:
    """Bytes, source records, seen ranges and disclosures are facts about the weeks, not the order."""
    in_order = await imported(tmp_path / "in-order", SCENARIOS["weeklies in date order"])
    late = await imported(
        tmp_path / "late", (Step("weekly", FIRST_WEEK), Step("weekly", THIRD_WEEK), Step("weekly", SECOND_WEEK, True))
    )

    def stored(store: OrderedImports) -> tuple[object, ...]:
        blobs = sorted(path.name for path in (store.data_dir / "blobs").rglob("*") if path.is_file())
        database = SqliteDatabase.open(store.data_dir)
        records = [
            sorted(row[0] for row in database.connection.execute(f"SELECT document FROM {table}"))  # noqa: S608
            for table in ("caselist_sources", "caselist_disclosures")
        ]
        return (blobs, *records)

    assert stored(late) == stored(in_order)
    source = await late.repository.get_source(digest_of("from-the-second-week-on"))
    assert (source.first_seen_snapshot, source.last_seen_snapshot) == (SECOND_WEEK, THIRD_WEEK)


async def test_the_week_after_a_late_one_keeps_the_manifest_it_was_measured_with(tmp_path: Path) -> None:
    """Its manifest is not written again: it still names the week before the late one, and its counts."""
    store = await imported(tmp_path, (Step("weekly", FIRST_WEEK), Step("weekly", THIRD_WEEK)))
    before = store.manifest_bytes("2026-09-15")

    await store.run(Step("weekly", SECOND_WEEK, allow_out_of_order=True))

    assert store.manifest_bytes("2026-09-15") == before
    summary = store.summary("2026-09-15")
    assert summary["previous_snapshot"] == "2026-09-01"
    assert summary["first_seen"] == 2


async def test_a_late_week_makes_the_first_seen_counts_sum_past_the_distinct_files(tmp_path: Path) -> None:
    """`from-the-second-week-on` is first seen in the late week and in the week after it."""
    store = await imported(
        tmp_path, (Step("weekly", FIRST_WEEK), Step("weekly", THIRD_WEEK), Step("weekly", SECOND_WEEK, True))
    )

    counted = [store.summary(snapshot)["first_seen"] for snapshot in ("2026-09-01", "2026-09-08", "2026-09-15")]

    assert counted == [2, 3, 2]
    assert sum(counted) == 7, "six distinct files, one of them counted twice"


async def test_importing_the_week_after_again_measures_it_against_the_late_one(tmp_path: Path) -> None:
    """The remedy the refusal names: the manifest the date-order run writes, byte for byte, no flag."""
    in_order = await imported(tmp_path / "in-order", SCENARIOS["weeklies in date order"])
    late = await imported(
        tmp_path / "late", (Step("weekly", FIRST_WEEK), Step("weekly", THIRD_WEEK), Step("weekly", SECOND_WEEK, True))
    )

    again = await late.run(Step("weekly", THIRD_WEEK))

    assert outcome_of(again) == EXPECTED_IMPORTS["weeklies in date order"][2]
    for snapshot in ("2026-09-01", "2026-09-08", "2026-09-15"):
        assert late.manifest_bytes(snapshot) == in_order.manifest_bytes(snapshot), snapshot


# ------------------------------------------------------------------------------------------------
# An older week imported again
# ------------------------------------------------------------------------------------------------


async def test_an_older_week_imported_again_is_refused_without_the_flag(tmp_path: Path) -> None:
    store = await imported(tmp_path, SCENARIOS["weeklies in date order"])

    assert await store.outcome(Step("weekly", SECOND_WEEK)) == ExpectedImport(
        "2026-09-08", None, {}, refused_by="2026-09-15"
    )


async def test_an_older_week_imported_again_changes_no_manifest(tmp_path: Path) -> None:
    """With the flag it is classified against the same week as before; the week after is not touched."""
    store = await imported(tmp_path, SCENARIOS["weeklies in date order"])
    before = {snapshot: store.manifest_bytes(snapshot) for snapshot in ("2026-09-08", "2026-09-15")}

    report = await store.run(Step("weekly", SECOND_WEEK, allow_out_of_order=True))

    assert outcome_of(report) == EXPECTED_IMPORTS["weeklies in date order"][1]
    assert {snapshot: store.manifest_bytes(snapshot) for snapshot in before} == before


# ------------------------------------------------------------------------------------------------
# What the refusal says
# ------------------------------------------------------------------------------------------------


async def test_the_refusal_of_a_week_never_imported_says_what_importing_it_leaves_behind(
    tmp_path: Path,
) -> None:
    store = await imported(tmp_path, (Step("weekly", FIRST_WEEK), Step("weekly", THIRD_WEEK)))

    with pytest.raises(SnapshotOutOfOrder) as refused:
        await store.run(Step("weekly", SECOND_WEEK))

    assert str(refused.value) == (
        "testcl26 already has the 2026-09-15 weekly imported. The 2026-09-08 weekly would be classified "
        "against the week before it, as it would be in date order, but the weeks after it were measured "
        "without it and their manifests are not written again: the next week's previous week and "
        "classification counts, and each later week's first-seen count, stay as they were. Pass "
        "--allow-out-of-order to import it, then import each later week again to measure it with this one."
    )
    assert "cumulative" not in str(refused.value)


async def test_the_refusal_of_a_week_already_imported_says_importing_it_again_changes_no_other_week(
    tmp_path: Path,
) -> None:
    store = await imported(tmp_path, SCENARIOS["weeklies in date order"])

    with pytest.raises(SnapshotOutOfOrder) as refused:
        await store.run(Step("weekly", SECOND_WEEK))

    assert str(refused.value) == (
        "testcl26 already has the 2026-09-15 weekly imported, which is newer than 2026-09-08. The "
        "2026-09-08 weekly is already imported too: importing it again classifies it against the week "
        "before it and writes its own manifest again, and no other week's. Pass --allow-out-of-order to "
        "import it again."
    )


# ------------------------------------------------------------------------------------------------
# A held path, and a weekly that arrives after the removal and out of date order
# ------------------------------------------------------------------------------------------------


async def removal_world(root: Path, steps: tuple[Step, ...], client: S3Client, bucket: str) -> RemovalWorld:
    """The imports made and published, as the operator's store is when a request arrives."""
    store = await imported(root, steps)
    world = RemovalWorld(data_dir=store.data_dir, bucket_name=bucket, client=client)
    publisher = CaselistPublishService(local=world.local, remote=world.bucket, suppression=empty_suppression_list())
    assert (await publisher.execute(await publisher.plan(CASELIST))).succeeded
    return world


async def remove(world: RemovalWorld, body: str) -> RemovalPlan:
    """`caselist remove --source <body> --execute`, through the service the command runs."""
    service = world.service()
    plan = await service.plan(
        SourceSelector(digest_of(body)), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM
    )
    assert (await service.execute(plan)).completed
    return plan


def what_the_plan_found(plan: RemovalPlan) -> tuple[str, dict[str, list[str]], list[str]]:
    """The hold's date, the later uploads by body and snapshot, and the earlier versions by body."""
    names = {digest_of(body): body for body in ("first-version", "second-version", "third-version")}
    (hold,) = plan.path_holds
    later = {names[one.sha256]: list(one.snapshots) for one in plan.later_uploads}
    earlier = [names[one.sha256] for one in plan.earlier_versions if one.relation is VersionRelation.EARLIER]
    return hold.after_snapshot.isoformat(), later, earlier


@pytest.mark.parametrize("case", list(EXPECTED_HOLDS))
async def test_a_weekly_imported_out_of_order_after_a_removal_is_held_by_its_date(
    case: str, tmp_path: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    expected: ExpectedHold = EXPECTED_HOLDS[case]
    world = await removal_world(
        tmp_path, (Step("weekly", FIRST_WEEK), Step("weekly", THIRD_WEEK)), s3_client, evidence_bucket
    )

    plan = await remove(world, expected.named)
    late = await OrderedImports(tmp_path).outcome(
        Step("weekly", SECOND_WEEK, allow_out_of_order=True),
        RecordedSuppressionList(local_suppression_list_file(world.data_dir)),
    )

    assert what_the_plan_found(plan) == (expected.hold_after, expected.later_uploads, expected.earlier_versions)
    assert late == expected.late_week


async def test_a_removal_after_a_late_week_finds_the_later_uploads_by_date(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    world = await removal_world(
        tmp_path,
        (Step("weekly", FIRST_WEEK), Step("weekly", THIRD_WEEK), Step("weekly", SECOND_WEEK, True)),
        s3_client,
        evidence_bucket,
    )

    plan = await remove(world, EXPECTED_LATER_UPLOADS.named)

    assert what_the_plan_found(plan) == (
        EXPECTED_LATER_UPLOADS.hold_after,
        EXPECTED_LATER_UPLOADS.later_uploads,
        EXPECTED_LATER_UPLOADS.earlier_versions,
    )
