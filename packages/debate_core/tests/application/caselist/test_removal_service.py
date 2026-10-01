"""Executing a removal against moto, and then trying to undo it the ways the world would.

The easy half is that a removed file is removed. The half that matters is that it stays removed:
the weekly archives are cumulative, so every one of them still holds it, and the next import, the
OpenEv import, a publish, a `store sync` and a renamed copy are each a way it could come back. Each
is tried here after a removal, and each must fail to bring it back.

Counts are worked out by hand from the fixture tables; see `test_removal_plan.py` for the team's
files, week by week.
"""

from __future__ import annotations

import hashlib
import zipfile
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.caselist.build_synthetic_archives import (
    DOCUMENT_BODIES,
    SNAPSHOTS,
    SYNTHETIC_CASELIST,
    SYNTHETIC_EVENT,
    build_snapshot_zips,
)
from tests.fixtures.openev.build_synthetic_openev import DOWNLOADS as OPENEV_DOWNLOADS
from tests.fixtures.openev.build_synthetic_openev import build_download_zips

from debate_core.application.caselist.camp_metadata import load_camp_aliases
from debate_core.application.caselist.import_service import (
    CaselistImportService,
    Classification,
    ImportReport,
)
from debate_core.application.caselist.manifest import manifest_key, manifest_lines, write_manifest
from debate_core.application.caselist.openev_import_service import OpenEvImportService
from debate_core.application.caselist.publish_service import CaselistPublishService, SourceResult
from debate_core.application.caselist.removal_plan import (
    Disposition,
    RemovalPlan,
    Side,
    SourceSelector,
    parse_team_selector,
)
from debate_core.application.caselist.removal_service import (
    CaselistRemovalService,
    RemovalIncomplete,
    refuse_protected_versions,
)
from debate_core.application.caselist.status_service import CaselistStatusService
from debate_core.application.caselist.suppression import (
    REMOVAL_LOG_KEY,
    SUPPRESSION_LIST_KEY,
    RecordedSuppressionList,
)
from debate_core.application.errors import DomainError, StoreUnavailable
from debate_core.application.ports.evidence_versions import ObjectVersion
from debate_core.application.ports.suppression import ReasonCode, RemovalLogEntry, RemovalOutcome
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsEvidenceObjectStore, FsSnapshotStore
from debate_core.integrations.local.archive_reader import archive_digest, read_archive
from debate_core.integrations.local.suppression_list import (
    local_removal_log_file,
    local_suppression_list_file,
)
from debate_core.integrations.s3 import S3EvidenceVersionStore

from .conftest import REQUEST, TEAM, RemovalWorld

pytestmark = pytest.mark.anyio

LIMITS = {"max_archive_bytes": 64 * 1024 * 1024, "max_unpacked_bytes": 64 * 1024 * 1024}
NEXT_MONDAY = date(2026, 9, 22)
NAMES = ("Maple Grove", "QX", "Cedar Hollow", "ZaLu", "Grove City", "Bayview", "Tamarack")


def digest(body: str) -> str:
    return hashlib.sha256(DOCUMENT_BODIES[body]).hexdigest()


SHARED = digest("grove-round-1-aff")
EXCLUSIVE = {
    digest("grove-round-2-neg-first"),
    digest("grove-round-2-neg-revised"),
    digest("bayview-semis-neg"),
}


async def remove_team(
    world: RemovalWorld, *, include_shared: bool = False, service: CaselistRemovalService | None = None
) -> RemovalPlan:
    remover = service or world.service()
    plan = await remover.plan(
        parse_team_selector(TEAM),
        request_id=REQUEST,
        reason=ReasonCode.REQUESTED_BY_TEAM,
        include_shared=include_shared,
    )
    await remover.execute(plan)
    return plan


def all_versions_under(world: RemovalWorld, prefix: str) -> list[str]:
    listed = world.client.list_object_versions(Bucket=world.bucket_name, Prefix=prefix)
    return [str(v.get("VersionId")) for v in [*listed.get("Versions", []), *listed.get("DeleteMarkers", [])]]


async def reimport_weeks(world: RemovalWorld, tmp_path: Path) -> list[ImportReport]:
    """Import the three archives again, then next Monday's: the 09-15 archive arriving as 09-22.

    The old weeks need `allow_out_of_order`, as they would for an operator re-importing them. The
    new week is the attack that matters: a cumulative archive, in order, that still holds every
    file the team asked to have removed.
    """
    importer = CaselistImportService(
        caselists=world.repository,
        blobs=FsSnapshotStore(world.data_dir),
        suppression=RecordedSuppressionList(local_suppression_list_file(world.data_dir)),
    )
    zips = build_snapshot_zips(tmp_path / "reimport")
    weeks = [(week.snapshot, zips[week.snapshot]) for week in SNAPSHOTS]
    weeks.append((NEXT_MONDAY, zips[SNAPSHOTS[-1].snapshot]))
    reports: list[ImportReport] = []
    objects = FsEvidenceObjectStore(world.data_dir)
    for snapshot, archive in weeks:
        report = await importer.import_archive(
            read_archive(archive, **LIMITS),
            caselist=SYNTHETIC_CASELIST,
            snapshot=snapshot,
            event=Event(SYNTHETIC_EVENT),
            archive_sha256=archive_digest(archive),
            allow_out_of_order=True,
        )
        write_manifest(report, objects.path_for(manifest_key(SYNTHETIC_CASELIST, snapshot)))
        reports.append(report)
    return reports


async def status_of(world: RemovalWorld) -> Any:
    return await CaselistStatusService(
        local=world.local, remote=world.bucket, suppression=world.suppression()
    ).status()


def log_entries(world: RemovalWorld) -> list[RemovalLogEntry]:
    path = local_removal_log_file(world.data_dir).path
    return [RemovalLogEntry.from_line(line) for line in path.read_text(encoding="utf-8").splitlines()]


# ------------------------------------------------------------------------------------------------
# ac1: everything listed, every version, is gone, and status is clean
# ------------------------------------------------------------------------------------------------


class TestExecution:
    async def test_every_listed_object_and_every_version_is_gone_and_status_is_clean(
        self, removal_world: RemovalWorld
    ) -> None:
        # Give the bucket history to purge: a second version of a removed source, and of a manifest.
        bayview = digest("bayview-semis-neg")
        raw_key = f"raw/caselist/{SYNTHETIC_CASELIST}/sha256/{bayview[0:2]}/{bayview[2:4]}/{bayview}"
        removal_world.client.put_object(
            Bucket=removal_world.bucket_name, Key=raw_key, Body=DOCUMENT_BODIES["bayview-semis-neg"]
        )
        week3 = manifest_key(SYNTHETIC_CASELIST, date(2026, 9, 15))
        old = removal_world.client.get_object(Bucket=removal_world.bucket_name, Key=week3)["Body"].read()
        removal_world.client.put_object(Bucket=removal_world.bucket_name, Key=week3, Body=old)
        removal_world.client.put_object(Bucket=removal_world.bucket_name, Key=week3, Body=old)
        assert len(all_versions_under(removal_world, raw_key)) == 2
        assert len(all_versions_under(removal_world, week3)) == 3

        plan = await remove_team(removal_world)

        for planned in plan.objects_on(Side.BUCKET):
            assert all_versions_under(removal_world, planned.key) == [], planned.key
        for planned in plan.objects_on(Side.LOCAL):
            assert not (removal_world.data_dir / "blobs" / planned.key).exists()
        for rewrite in plan.manifests_on(Side.BUCKET):
            assert len(all_versions_under(removal_world, rewrite.key)) == 1, "superseded versions purged"
            body = removal_world.client.get_object(Bucket=removal_world.bucket_name, Key=rewrite.key)[
                "Body"
            ].read()
            assert body.decode().splitlines() == list(rewrite.lines)
        status = await status_of(removal_world)
        assert status.in_sync, [entry for entry in status.snapshots if not entry.in_sync]

    async def test_the_records_go_last_and_only_the_teams(self, removal_world: RemovalWorld) -> None:
        await remove_team(removal_world)

        repository = removal_world.repository
        for sha in EXCLUSIVE:
            assert await repository.find_source(sha) is None
        assert await repository.find_source(SHARED) is not None
        kept = (await repository.list_disclosures(source_sha256=SHARED, limit=50)).items
        assert {(d.school, d.team_code) for d in kept} == {("Cedar Hollow", "ZaLu")}
        assert not (await repository.list_disclosures(school="Maple Grove", limit=50)).items
        assert (await repository.list_camp_files(source_sha256=SHARED, limit=5)).items

    async def test_with_include_shared_the_shared_file_goes_for_everyone(
        self, removal_world: RemovalWorld
    ) -> None:
        await remove_team(removal_world, include_shared=True)

        assert await removal_world.repository.find_source(SHARED) is None
        assert not (await removal_world.repository.list_camp_files(source_sha256=SHARED, limit=5)).items
        assert (
            all_versions_under(removal_world, f"raw/openev/2026/sha256/{SHARED[0:2]}/{SHARED[2:4]}/{SHARED}")
            == []
        )
        assert (await status_of(removal_world)).in_sync


# ------------------------------------------------------------------------------------------------
# ac2: trying to bring it back
# ------------------------------------------------------------------------------------------------


class TestItDoesNotComeBack:
    async def test_the_cumulative_archives_reimported_bring_back_nothing(
        self, removal_world: RemovalWorld, tmp_path: Path
    ) -> None:
        await remove_team(removal_world)

        reports = await reimport_weeks(removal_world, tmp_path)

        # 09-01: Round 1 (withdrawn) and Round 2 (removed). 09-08: Round 1, (1), Round 2 revised.
        # 09-15: those three and Bayview.
        # 09-22 is the 09-15 archive again, in order: the same four.
        assert [report.count(Classification.SUPPRESSED) for report in reports] == [2, 3, 4, 4]
        for sha in EXCLUSIVE:
            assert not await FsSnapshotStore(removal_world.data_dir).exists(sha)
            assert await removal_world.repository.find_source(sha) is None
        assert not (await removal_world.repository.list_disclosures(school="Maple Grove", limit=50)).items
        for report in reports:
            text = "\n".join(manifest_lines(report))
            assert "Maple Grove" not in text, "not even a junk row"
            assert not any(sha in text for sha in EXCLUSIVE)

    async def test_a_publish_after_the_reimport_uploads_none_of_it(
        self, removal_world: RemovalWorld, tmp_path: Path
    ) -> None:
        await remove_team(removal_world)
        await reimport_weeks(removal_world, tmp_path)

        publisher = CaselistPublishService(
            local=removal_world.local, remote=removal_world.bucket, suppression=removal_world.suppression()
        )
        report = await publisher.execute(await publisher.plan(SYNTHETIC_CASELIST))

        assert report.succeeded
        uploaded = {
            outcome.sha256 for snapshot in report.snapshots for outcome in snapshot.of(SourceResult.UPLOADED)
        }
        assert not uploaded & EXCLUSIVE
        for sha in EXCLUSIVE:
            assert (
                all_versions_under(
                    removal_world, f"raw/caselist/{SYNTHETIC_CASELIST}/sha256/{sha[0:2]}/{sha[2:4]}/{sha}"
                )
                == []
            )
        assert (await status_of(removal_world)).in_sync

    async def test_the_same_bytes_renamed_and_filed_by_another_team_are_still_refused(
        self, removal_world: RemovalWorld, tmp_path: Path
    ) -> None:
        await remove_team(removal_world)
        archive = tmp_path / "testcl26-0922.zip"
        with zipfile.ZipFile(archive, "w") as written:
            written.writestr(
                "Northgate Prep/BeCo/Northgate Prep-BeCo-Neg-Bayview Open-Finals.docx",
                DOCUMENT_BODIES["bayview-semis-neg"],
            )
            written.writestr(
                "Northgate Prep/BeCo/Northgate Prep-BeCo-Aff-Bayview Open-Finals.docx", b"genuinely new bytes"
            )
        importer = CaselistImportService(
            caselists=removal_world.repository,
            blobs=FsSnapshotStore(removal_world.data_dir),
            suppression=RecordedSuppressionList(local_suppression_list_file(removal_world.data_dir)),
        )

        report = await importer.import_archive(
            read_archive(archive, **LIMITS),
            caselist=SYNTHETIC_CASELIST,
            snapshot=date(2026, 9, 22),
            event=Event(SYNTHETIC_EVENT),
            archive_sha256=archive_digest(archive),
        )

        assert report.count(Classification.SUPPRESSED) == 1
        assert not await FsSnapshotStore(removal_world.data_dir).exists(digest("bayview-semis-neg"))

    async def test_the_openev_import_brings_back_none_of_it(
        self, removal_world: RemovalWorld, tmp_path: Path
    ) -> None:
        """The camp file's bytes are the shared Round 1: removed for everyone with --include-shared."""
        from tests.fixtures.openev.build_synthetic_openev import CAMP_ALIASES_PATH

        await remove_team(removal_world, include_shared=True)
        download = build_download_zips(tmp_path / "openev")[OPENEV_DOWNLOADS[0].name]
        importer = OpenEvImportService(
            caselists=removal_world.repository,
            blobs=FsSnapshotStore(removal_world.data_dir),
            suppression=RecordedSuppressionList(local_suppression_list_file(removal_world.data_dir)),
        )

        report = await importer.import_release(
            read_archive(download, **LIMITS),
            year=2026,
            event=Event.POLICY,
            imported_on=date(2026, 9, 30),
            archive_sha256=archive_digest(download),
            aliases=load_camp_aliases(CAMP_ALIASES_PATH),
        )

        assert report.count(Classification.SUPPRESSED) == 1
        assert await removal_world.repository.find_source(SHARED) is None
        assert not any(SHARED in line for line in report.manifest_lines)

    async def test_the_withdrawn_teams_copy_of_a_shared_file_is_refused_and_the_other_teams_kept(
        self, removal_world: RemovalWorld, tmp_path: Path
    ) -> None:
        await remove_team(removal_world)

        reports = await reimport_weeks(removal_world, tmp_path)

        third = {entry.path: entry.classification for entry in reports[-1].entries}
        assert (
            third["Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1.docx"]
            is Classification.SUPPRESSED
        )
        assert third["Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-Aff-Grove City Invitational-Round 3.docx"] in {
            Classification.UNCHANGED,
            Classification.NEW,
            Classification.DUPLICATE,
        }
        assert await FsSnapshotStore(removal_world.data_dir).exists(SHARED)


# ------------------------------------------------------------------------------------------------
# ac4 / ac5: the list and the log
# ------------------------------------------------------------------------------------------------


class TestTheRecordsItLeaves:
    async def test_one_log_entry_per_execution_in_both_copies_and_no_names(
        self, removal_world: RemovalWorld
    ) -> None:
        await remove_team(removal_world)

        (entry,) = log_entries(removal_world)
        assert entry.outcome is RemovalOutcome.COMPLETED
        assert entry.request_id == REQUEST and entry.environment == "dev"
        assert set(entry.removed_sha256) == EXCLUSIVE and entry.withdrawn_sha256 == (SHARED,)
        assert entry.local_records_deleted == 12, "nine disclosures and three source documents"
        assert entry.manifest_rows_dropped == 2 * (4 + 5 + 6), "fifteen rows, from both copies"
        bucket_log = removal_world.client.get_object(Bucket=removal_world.bucket_name, Key=REMOVAL_LOG_KEY)[
            "Body"
        ].read()
        assert bucket_log.decode().splitlines() == [entry.to_line()]
        for text in (
            bucket_log.decode(),
            local_suppression_list_file(removal_world.data_dir).path.read_text(),
        ):
            for name in NAMES:
                assert name not in text

    async def test_the_list_is_only_ever_appended_to_on_both_copies(
        self, removal_world: RemovalWorld
    ) -> None:
        await remove_team(removal_world)
        local = local_suppression_list_file(removal_world.data_dir).path
        local_before = local.read_bytes()
        bucket_before = removal_world.client.get_object(
            Bucket=removal_world.bucket_name, Key=SUPPRESSION_LIST_KEY
        )["Body"].read()

        remover = removal_world.service()
        await remover.execute(
            await remover.plan(
                SourceSelector(digest("ridgeline-round-6-neg")),
                request_id="RM-2026-02",
                reason=ReasonCode.POLICY,
            )
        )

        assert local.read_bytes().startswith(local_before) and local.read_bytes() != local_before
        listed = removal_world.client.list_object_versions(
            Bucket=removal_world.bucket_name, Prefix=SUPPRESSION_LIST_KEY
        )
        # Ordered by length, not by time: moto's timestamps can tie within one second.
        bodies = sorted(
            (
                removal_world.client.get_object(
                    Bucket=removal_world.bucket_name,
                    Key=SUPPRESSION_LIST_KEY,
                    VersionId=str(v.get("VersionId")),
                )["Body"].read()
                for v in listed.get("Versions", [])
            ),
            key=len,
        )
        assert len(bodies) == 2, "one version per execution that appended"
        assert bodies[0] == bucket_before
        assert bodies[1].startswith(bodies[0]), "the second version kept every byte of the first"

    def test_nothing_under_the_suppression_prefix_but_the_probe_may_be_deleted(self) -> None:
        for key in (SUPPRESSION_LIST_KEY, REMOVAL_LOG_KEY):
            with pytest.raises(DomainError, match="append-only"):
                refuse_protected_versions([ObjectVersion(key=key, version_id="v1")])
        refuse_protected_versions(
            [ObjectVersion(key="manifests/_suppression/preflight/abc.txt", version_id="v1")]
        )


# ------------------------------------------------------------------------------------------------
# Re-running
# ------------------------------------------------------------------------------------------------


class VersionsThatFailAfter:
    """The takedown's version store, refusing to delete after `allowed` deletes: a run cut short."""

    def __init__(self, inner: S3EvidenceVersionStore, allowed: int) -> None:
        self._inner = inner
        self._allowed = allowed
        self.location = inner.location

    async def list_versions(self, prefix: str) -> tuple[ObjectVersion, ...]:
        return await self._inner.list_versions(prefix)

    async def get_version_file(self, version: ObjectVersion, destination: Path) -> None:
        await self._inner.get_version_file(version, destination)

    async def delete_versions(self, versions: Sequence[ObjectVersion]) -> int:
        if self._allowed <= 0 and not all(
            v.key.startswith("manifests/_suppression/preflight/") for v in versions
        ):
            raise StoreUnavailable("DeleteObject", "s3://moto", "the connection dropped")
        self._allowed -= len(versions)
        return await self._inner.delete_versions(versions)


class TestRerunning:
    async def test_a_run_cut_short_is_logged_incomplete_and_the_same_command_finishes_it(
        self, removal_world: RemovalWorld, tmp_path: Path
    ) -> None:
        def flaky() -> Any:
            access = removal_world.takedown()
            return type(access)(
                versions=VersionsThatFailAfter(
                    S3EvidenceVersionStore(bucket=removal_world.bucket_name, client=removal_world.client), 2
                ),  # type: ignore[arg-type]
                objects=access.objects,
                profile=access.profile,
                bucket=access.bucket,
            )

        with pytest.raises(RemovalIncomplete):
            await remove_team(removal_world, service=removal_world.service(takedown=flaky))

        (first,) = log_entries(removal_world)
        assert first.outcome is RemovalOutcome.INCOMPLETE and first.error_code == "STORE_UNAVAILABLE"
        assert local_suppression_list_file(removal_world.data_dir).path.exists(), (
            "suppressed before anything else"
        )
        reports = await reimport_weeks(removal_world, tmp_path / "between")
        assert [report.count(Classification.SUPPRESSED) for report in reports] == [2, 3, 4, 4], "already safe"

        await remove_team(removal_world)

        assert [entry.outcome for entry in log_entries(removal_world)] == [
            RemovalOutcome.INCOMPLETE,
            RemovalOutcome.COMPLETED,
        ]
        for sha in EXCLUSIVE:
            assert (
                all_versions_under(
                    removal_world, f"raw/caselist/{SYNTHETIC_CASELIST}/sha256/{sha[0:2]}/{sha[2:4]}/{sha}"
                )
                == []
            )
        assert not (await removal_world.repository.list_disclosures(school="Maple Grove", limit=50)).items

    async def test_running_it_again_after_it_finished_finds_nothing_left(
        self, removal_world: RemovalWorld
    ) -> None:
        await remove_team(removal_world)

        remover = removal_world.service()
        again = await remover.plan(
            parse_team_selector(TEAM), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM
        )

        assert again.nothing_to_do
        assert {source.disposition for source in again.sources} <= {Disposition.REMOVE, Disposition.WITHDRAW}
        report = await remover.execute(again)
        assert report.s3_versions_deleted == 0 and report.local_records_deleted == 0
        assert len(log_entries(removal_world)) == 2
        lines = local_suppression_list_file(removal_world.data_dir).path.read_text().splitlines()
        assert len(lines) == len(set(lines)) == 5, "no entry appended twice"

    async def test_a_removal_made_on_another_machine_is_merged_into_this_ones_list(
        self, removal_world: RemovalWorld
    ) -> None:
        """The bucket's copy reaches this machine's on the next write; the bucket's alone already counts."""
        await remove_team(removal_world)
        local = local_suppression_list_file(removal_world.data_dir).path
        local.unlink()  # this machine never saw the removal

        state = await removal_world.suppression().entries()

        assert {entry.sha256 for entry in state} == EXCLUSIVE | {SHARED}
        await removal_world.suppression().reconcile()
        assert len(local.read_text().splitlines()) == 5


class TestSupersededManifestVersions:
    async def test_an_older_version_of_an_untouched_manifest_that_names_the_file_is_purged(
        self, removal_world: RemovalWorld
    ) -> None:
        """The current 09-01 manifest never named Bayview; a version re-published before it did.

        A restorable version of a removed row is the row not removed, so the sweep reads every
        noncurrent version of the caselist's manifests and purges the ones that name it.
        """
        week1 = manifest_key(SYNTHETIC_CASELIST, date(2026, 9, 1))
        current = removal_world.client.get_object(Bucket=removal_world.bucket_name, Key=week1)["Body"].read()
        bayview = digest("bayview-semis-neg")
        stale_row = (
            '{"classification":"NEW","kind":"member","path":"Maple Grove/QX/Bayview.docx",'
            f'"schema_version":1,"sha256":"{bayview}"}}\n'
        )
        removal_world.client.put_object(
            Bucket=removal_world.bucket_name, Key=week1, Body=stale_row.encode() + current
        )
        removal_world.client.put_object(Bucket=removal_world.bucket_name, Key=week1, Body=current)
        assert len(all_versions_under(removal_world, week1)) == 3

        remover = removal_world.service()
        plan = await remover.plan(
            SourceSelector(bayview), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM
        )
        assert week1 not in {rewrite.key for rewrite in plan.manifests}, "its current version is clean"
        await remover.execute(plan)

        remaining = removal_world.client.list_object_versions(Bucket=removal_world.bucket_name, Prefix=week1)
        bodies = [
            removal_world.client.get_object(
                Bucket=removal_world.bucket_name, Key=week1, VersionId=str(v.get("VersionId"))
            )["Body"].read()
            for v in remaining.get("Versions", [])
        ]
        assert len(bodies) == 2, "the original and the current version stay; the one naming Bayview goes"
        assert not any(bayview.encode() in body for body in bodies)

    async def test_a_rerun_after_a_stop_during_the_sweep_still_sweeps(
        self, removal_world: RemovalWorld
    ) -> None:
        """The first run cleans the current manifests then stops; the second rewrites nothing and sweeps."""
        week1 = manifest_key(SYNTHETIC_CASELIST, date(2026, 9, 1))
        current = removal_world.client.get_object(Bucket=removal_world.bucket_name, Key=week1)["Body"].read()
        bayview = digest("bayview-semis-neg")
        stale = (
            '{"classification":"NEW","kind":"member","path":"x.docx","schema_version":1,'
            + f'"sha256":"{bayview}"}}\n'
        )
        removal_world.client.put_object(
            Bucket=removal_world.bucket_name, Key=week1, Body=stale.encode() + current
        )
        removal_world.client.put_object(Bucket=removal_world.bucket_name, Key=week1, Body=current)

        class StopsBeforeReadingVersions(S3EvidenceVersionStore):
            async def get_version_file(self, version: ObjectVersion, destination: Path) -> None:
                raise StoreUnavailable("GetObject", version.key, "the connection dropped")

        def stopping() -> Any:
            access = removal_world.takedown()
            return type(access)(
                versions=StopsBeforeReadingVersions(
                    bucket=removal_world.bucket_name, client=removal_world.client
                ),
                objects=access.objects,
                profile=access.profile,
                bucket=access.bucket,
            )

        first = removal_world.service(takedown=stopping)
        with pytest.raises(RemovalIncomplete):
            await first.execute(
                await first.plan(
                    SourceSelector(bayview), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM
                )
            )
        second = removal_world.service()
        plan = await second.plan(
            SourceSelector(bayview), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM
        )
        assert not plan.manifests_on(Side.BUCKET), "the current manifests were cleaned the first time"
        await second.execute(plan)

        remaining = removal_world.client.list_object_versions(Bucket=removal_world.bucket_name, Prefix=week1)
        for version in remaining.get("Versions", []):
            body = removal_world.client.get_object(
                Bucket=removal_world.bucket_name, Key=week1, VersionId=str(version.get("VersionId"))
            )["Body"].read()
            assert bayview.encode() not in body
