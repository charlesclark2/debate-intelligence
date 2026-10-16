"""What an import does when weekly windows and complete archives arrive out of date order (`v1-e30-t17`).

A weekly archive is a window of about a week's editing, and the complete archive is the cumulative
copy. The importer's ordering rule was written for cumulative weeklies. These tests record what an
import actually does when the archives arrive in another order, against answers worked out by hand in
`tests/fixtures/caselist/build_window_order_archives.py` before any of them ran
(`docs/process/working-agreements.md` §6).

The importer is the real one over a real data directory, built as the composition root builds it,
with the first-seen reader; each manifest is written as `caselist import` and `caselist pull` write
it, and after each weekly the later manifests are measured again as both commands measure them
(`v1-e30-t18`). The held-path tests make the removal through the removal service against moto, as
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
    BODIES,
    CASELIST,
    EXPECTED_HOLDS,
    EXPECTED_IMPORTS,
    EXPECTED_LATER_UPLOADS,
    EXPECTED_REMEASURED,
    FIRST_WEEK,
    SCENARIOS,
    SECOND_WEEK,
    THIRD_WEEK,
    ExpectedHold,
    ExpectedImport,
    ExpectedRemeasure,
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
from debate_core.application.caselist.later_manifests import LaterManifests, LaterManifestsRemeasured
from debate_core.application.caselist.manifest import full_archive_manifest_key, manifest_key, write_manifest
from debate_core.application.caselist.publish_service import CaselistPublishService, ManifestOutcome
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
        self.remeasured: LaterManifestsRemeasured | None = None
        """What measuring the later manifests again rewrote after the last import, `None` after none."""

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
        """Import one archive and write its manifest, as the command that imports it does.

        After a weekly, the later manifests are measured again, as `caselist import` and `caselist
        pull` measure them (`v1-e30-t18`).
        """
        self.remeasured = None
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
            self.remeasured = await LaterManifests(
                caselists=self.repository,
                local=self.local,
                suppression=suppression or empty_suppression_list(),
            ).after_weekly_import(CASELIST, step.day)
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


def remeasure_of(remeasured: LaterManifestsRemeasured | None) -> ExpectedRemeasure | None:
    """What measuring the later manifests again rewrote, in the fixture's terms."""
    if remeasured is None:
        return None
    recount = remeasured.complete_archive
    return ExpectedRemeasure(
        weeklies=remeasured.weeklies,
        complete_archive=(
            (
                recount.snapshot,
                (recount.before.withdrawn, recount.before.superseded, recount.before.earlier_snapshots),
                (recount.after.withdrawn, recount.after.superseded, recount.after.earlier_snapshots),
            )
            if recount is not None
            else None
        ),
    )


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


@pytest.mark.parametrize("scenario", list(SCENARIOS))
async def test_each_import_rewrites_the_later_manifests_the_fixture_works_out_by_hand(
    scenario: str, tmp_path: Path
) -> None:
    """`v1-e30-t18`: after each weekly, which later manifests were measured again and rewritten."""
    store = OrderedImports(tmp_path)

    rewritten: list[ExpectedRemeasure | None] = []
    for step in SCENARIOS[scenario]:
        await store.outcome(step)
        rewritten.append(remeasure_of(store.remeasured))

    assert rewritten == list(EXPECTED_REMEASURED[scenario])


# ------------------------------------------------------------------------------------------------
# A weekly after a later one
# ------------------------------------------------------------------------------------------------

LATE_ORDERS: dict[str, tuple[tuple[Step, ...], date]] = {
    "the second week after the third": (
        (Step("weekly", FIRST_WEEK), Step("weekly", THIRD_WEEK)),
        SECOND_WEEK,
    ),
    "the first week after the other two": (
        (Step("weekly", SECOND_WEEK), Step("weekly", THIRD_WEEK)),
        FIRST_WEEK,
    ),
}
"""Two weeklies imported, then the one missing from between or before them, allowed out of order."""

WEEKS = ("2026-09-01", "2026-09-08", "2026-09-15")


@pytest.mark.parametrize("order", list(LATE_ORDERS))
async def test_what_is_stored_does_not_depend_on_the_order_the_weeks_arrived_in(
    order: str, tmp_path: Path
) -> None:
    """Bytes, source records, seen ranges and disclosures are facts about the weeks, not the order.

    Measuring the later manifests again (`v1-e30-t18`) reads the store and changes none of it.
    """
    in_order = await imported(tmp_path / "in-order", SCENARIOS["weeklies in date order"])
    earlier, late_week = LATE_ORDERS[order]
    late = await imported(tmp_path / "late", (*earlier, Step("weekly", late_week, True)))

    assert stored(late) == stored(in_order)
    source = await late.repository.get_source(digest_of("from-the-second-week-on"))
    assert (source.first_seen_snapshot, source.last_seen_snapshot) == (SECOND_WEEK, THIRD_WEEK)


def stored(store: OrderedImports) -> tuple[object, ...]:
    """Every blob, source record and disclosure in a store, in a form two stores can be compared by."""
    blobs = sorted(path.name for path in (store.data_dir / "blobs").rglob("*") if path.is_file())
    database = SqliteDatabase.open(store.data_dir)
    records = [
        sorted(row[0] for row in database.connection.execute(f"SELECT document FROM {table}"))  # noqa: S608
        for table in ("caselist_sources", "caselist_disclosures")
    ]
    return (blobs, *records)


@pytest.mark.parametrize("order", list(LATE_ORDERS))
async def test_every_later_week_is_measured_again_with_the_late_one_and_no_archive_is_read(
    order: str, tmp_path: Path
) -> None:
    """ac1: every weekly manifest is the date-order manifest, byte for byte, with the archives gone.

    `v1-e30-t17` found the week after a late one keeping the manifest it was measured with: its
    previous week, its classification counts and its first-seen count. The archives of the weeks
    already imported are deleted before the late one arrives, as retention deletes them, so nothing
    but the store can be read.
    """
    in_order = await imported(tmp_path / "in-order", SCENARIOS["weeklies in date order"])
    earlier, late_week = LATE_ORDERS[order]
    late = await imported(tmp_path / "late", earlier)
    for step in earlier:
        late.weekly[step.day].unlink()

    await late.run(Step("weekly", late_week, allow_out_of_order=True))

    for snapshot in WEEKS:
        assert late.manifest_bytes(snapshot) == in_order.manifest_bytes(snapshot), snapshot


async def test_after_a_late_week_the_first_seen_counts_sum_to_the_distinct_files(tmp_path: Path) -> None:
    """`v1-e30-t17` found them summing to 7, `from-the-second-week-on` counted in two weeks."""
    store = await imported(
        tmp_path, (Step("weekly", FIRST_WEEK), Step("weekly", THIRD_WEEK), Step("weekly", SECOND_WEEK, True))
    )

    counted = [int(str(store.summary(day)["first_seen"])) for day in WEEKS]

    assert counted == [2, 3, 1]
    assert sum(counted) == len(BODIES), "six distinct files, each counted once"


async def test_the_week_after_names_the_late_one_as_its_previous_week(tmp_path: Path) -> None:
    store = await imported(tmp_path, (Step("weekly", FIRST_WEEK), Step("weekly", THIRD_WEEK)))
    assert store.summary("2026-09-15")["previous_snapshot"] == "2026-09-01"

    await store.run(Step("weekly", SECOND_WEEK, allow_out_of_order=True))

    summary = store.summary("2026-09-15")
    assert summary["previous_snapshot"] == "2026-09-08"
    assert summary["classifications"] == {"CHANGED": 1, "REMOVED": 1, "UNCHANGED": 2}
    assert summary["first_seen"] == 1


async def test_importing_the_week_after_again_measures_it_against_the_late_one(tmp_path: Path) -> None:
    """The remedy `v1-e30-t17` named still works: the date-order manifest, byte for byte, no flag."""
    in_order = await imported(tmp_path / "in-order", SCENARIOS["weeklies in date order"])
    late = await imported(
        tmp_path / "late",
        (Step("weekly", FIRST_WEEK), Step("weekly", THIRD_WEEK), Step("weekly", SECOND_WEEK, True)),
    )

    again = await late.run(Step("weekly", THIRD_WEEK))

    assert outcome_of(again) == EXPECTED_IMPORTS["weeklies in date order"][2]
    for snapshot in WEEKS:
        assert late.manifest_bytes(snapshot) == in_order.manifest_bytes(snapshot), snapshot


# ------------------------------------------------------------------------------------------------
# An older week imported again
# ------------------------------------------------------------------------------------------------


async def test_an_older_week_imported_again_needs_no_flag(tmp_path: Path) -> None:
    """ac2 (`v1-e30-t18`): it writes its own manifest and no other, so nothing is refused."""
    store = await imported(tmp_path, SCENARIOS["weeklies in date order"])

    assert await store.outcome(Step("weekly", SECOND_WEEK)) == EXPECTED_IMPORTS["weeklies in date order"][1]


async def test_an_older_week_imported_again_changes_no_manifest(tmp_path: Path) -> None:
    """ac2: classified against the same week as before; no other week's manifest is touched."""
    store = await imported(tmp_path, SCENARIOS["weeklies in date order"])
    before = {snapshot: store.manifest_bytes(snapshot) for snapshot in WEEKS}
    written = {snapshot: store.manifest_path(snapshot).stat().st_mtime_ns for snapshot in WEEKS}

    report = await store.run(Step("weekly", SECOND_WEEK))

    assert outcome_of(report) == EXPECTED_IMPORTS["weeklies in date order"][1]
    assert {snapshot: store.manifest_bytes(snapshot) for snapshot in WEEKS} == before
    assert store.remeasured is not None and store.remeasured.rewritten == ()
    for snapshot in ("2026-09-01", "2026-09-15"):
        assert store.manifest_path(snapshot).stat().st_mtime_ns == written[snapshot], snapshot


# ------------------------------------------------------------------------------------------------
# What the refusal says
# ------------------------------------------------------------------------------------------------


async def test_the_refusal_of_a_week_never_imported_says_what_importing_it_rewrites(
    tmp_path: Path,
) -> None:
    store = await imported(tmp_path, (Step("weekly", FIRST_WEEK), Step("weekly", THIRD_WEEK)))

    with pytest.raises(SnapshotOutOfOrder) as refused:
        await store.run(Step("weekly", SECOND_WEEK))

    assert str(refused.value) == (
        "testcl26 already has the 2026-09-15 weekly imported, and has never imported the 2026-09-08 "
        "one. Importing it classifies it against the week before it, as in date order, and then "
        "measures the weeks after it again from what this machine holds, rewriting their manifests: "
        "the next week's previous week and classification counts, each later week's first-seen count, "
        "and the newest complete archive's withdrawals. Pass --allow-out-of-order to import it, then "
        "publish the caselist, which uploads every rewritten manifest."
    )
    assert "cumulative" not in str(refused.value)


# ------------------------------------------------------------------------------------------------
# A complete archive imported before an earlier-dated weekly
# ------------------------------------------------------------------------------------------------

COMPLETE_ARCHIVE_LATE_ORDERS = (
    "a complete archive imported before an earlier-dated weekly",
    "a complete archive before any weekly, dated after two of them",
)


@pytest.mark.parametrize("scenario", COMPLETE_ARCHIVE_LATE_ORDERS)
async def test_the_newest_complete_archive_is_recounted_to_the_date_order_manifest(
    scenario: str, tmp_path: Path
) -> None:
    """ac3: its withdrawals are counted again, and its manifest is the date-order one, byte for byte."""
    in_order = await imported(
        tmp_path / "in-order", SCENARIOS["a complete archive between two weeklies, in date order"]
    )
    late = await imported(tmp_path / "late", SCENARIOS[scenario])

    for snapshot in (*WEEKS, "full/2026-09-12"):
        assert late.manifest_bytes(snapshot) == in_order.manifest_bytes(snapshot), snapshot
    summary = late.summary("full/2026-09-12")
    assert (summary["withdrawn"], summary["superseded"], summary["earlier_snapshots"]) == (1, 1, 2)
    assert stored(late) == stored(in_order)


async def test_a_complete_archive_dated_before_the_weekly_is_not_recounted(tmp_path: Path) -> None:
    """`full/2026-08-29` is dated before every weekly: its count is the one it was imported with."""
    store = await imported(tmp_path, SCENARIOS["a complete archive before any weekly, dated before them all"])

    summary = store.summary("full/2026-08-29")

    assert (summary["withdrawn"], summary["superseded"], summary["earlier_snapshots"]) == (0, 0, 0)


# ------------------------------------------------------------------------------------------------
# A rewritten manifest is published as a changed one
# ------------------------------------------------------------------------------------------------


async def test_each_rewritten_manifest_publishes_as_a_changed_manifest(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    """ac5: the publisher uploads every rewritten manifest over the one the bucket holds.

    `2026-09-01`, `full/2026-09-12` and `2026-09-15` imported and published; then `2026-09-08`
    arrives late, which rewrites `2026-09-15` and recounts `full/2026-09-12`.
    """
    world = await removal_world(
        tmp_path,
        (Step("weekly", FIRST_WEEK), Step("complete", date(2026, 9, 12)), Step("weekly", THIRD_WEEK)),
        s3_client,
        evidence_bucket,
    )
    store = OrderedImports(tmp_path)
    await store.run(Step("weekly", SECOND_WEEK, allow_out_of_order=True))
    assert store.remeasured is not None
    assert store.remeasured.rewritten == ("2026-09-15", "full/2026-09-12")

    publisher = CaselistPublishService(
        local=world.local, remote=world.bucket, suppression=empty_suppression_list()
    )
    report = await publisher.execute(await publisher.plan(CASELIST))

    assert report.succeeded
    assert {outcome.snapshot: outcome.manifest for outcome in report.snapshots} == {
        "2026-09-01": ManifestOutcome.SKIPPED,
        "2026-09-08": ManifestOutcome.UPLOADED,
        "2026-09-15": ManifestOutcome.UPLOADED,
        "full/2026-09-12": ManifestOutcome.UPLOADED,
    }
    for snapshot in ("2026-09-08", "2026-09-15", "full/2026-09-12"):
        key = store.manifest_path(snapshot).relative_to(store.data_dir / "objects").as_posix()
        remote = s3_client.get_object(Bucket=evidence_bucket, Key=key)["Body"].read()
        assert remote == store.manifest_bytes(snapshot), snapshot


# ------------------------------------------------------------------------------------------------
# A held path, and a weekly that arrives after the removal and out of date order
# ------------------------------------------------------------------------------------------------


async def removal_world(root: Path, steps: tuple[Step, ...], client: S3Client, bucket: str) -> RemovalWorld:
    """The imports made and published, as the operator's store is when a request arrives."""
    store = await imported(root, steps)
    world = RemovalWorld(data_dir=store.data_dir, bucket_name=bucket, client=client)
    publisher = CaselistPublishService(
        local=world.local, remote=world.bucket, suppression=empty_suppression_list()
    )
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

    assert what_the_plan_found(plan) == (
        expected.hold_after,
        expected.later_uploads,
        expected.earlier_versions,
    )
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
