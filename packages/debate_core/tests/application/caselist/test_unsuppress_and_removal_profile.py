"""Reversing a mistaken removal, and refusing to start one without the takedown credential.

`caselist unsuppress` appends an un-suppress entry — the list is never edited — after which the next
import of an archive that holds the file stores it again; data the removal purged is not restored.
`caselist remove --execute` needs the `EvidenceRemoval` profile named by `DEBATE_REMOVAL_PROFILE`, and
when it is unset, signed out or not the takedown profile at all, the run stops before the first
change: nothing deleted, nothing appended (spec ac6).

Moto does not enforce IAM, so the refusals are made by the stores themselves: a version store that
answers the way AWS answers the everyday profile, or a takedown factory that raises the way an unset
profile does.
"""

from __future__ import annotations

import hashlib
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

from debate_core.application.caselist.import_service import CaselistImportService, Classification
from debate_core.application.caselist.removal_plan import SourceSelector
from debate_core.application.caselist.removal_service import (
    NotSuppressed,
    TakedownAccess,
    TakedownNotConfigured,
    TakedownPreflightFailed,
)
from debate_core.application.caselist.suppression import SUPPRESSION_LIST_KEY, RecordedSuppressionList
from debate_core.application.errors import StoreAccessDenied, StoreCredentialsExpired
from debate_core.application.ports.evidence_versions import ObjectVersion
from debate_core.application.ports.suppression import (
    ReasonCode,
    RemovalLogEntry,
    RemovalLogKind,
    SuppressionAction,
    SuppressionEntry,
    SuppressionState,
)
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsSnapshotStore
from debate_core.integrations.local.archive_reader import archive_digest, read_archive
from debate_core.integrations.local.suppression_list import (
    local_removal_log_file,
    local_suppression_list_file,
)
from debate_core.integrations.s3 import S3EvidenceVersionStore

from .conftest import RemovalWorld

pytestmark = pytest.mark.anyio

LIMITS = {"max_archive_bytes": 64 * 1024 * 1024, "max_unpacked_bytes": 64 * 1024 * 1024}
BAYVIEW = hashlib.sha256(DOCUMENT_BODIES["bayview-semis-neg"]).hexdigest()


async def remove_bayview(world: RemovalWorld) -> None:
    remover = world.service()
    await remover.execute(
        await remover.plan(
            SourceSelector(BAYVIEW), request_id="RM-2026-03", reason=ReasonCode.REQUESTED_BY_TEAM
        )
    )


async def import_third_week_again(world: RemovalWorld, tmp_path: Path) -> Any:
    week = SNAPSHOTS[-1].snapshot
    archive = build_snapshot_zips(tmp_path / "again")[week]
    importer = CaselistImportService(
        caselists=world.repository,
        blobs=FsSnapshotStore(world.data_dir),
        suppression=RecordedSuppressionList(local_suppression_list_file(world.data_dir)),
    )
    return await importer.import_archive(
        read_archive(archive, **LIMITS),
        caselist=SYNTHETIC_CASELIST,
        snapshot=date(2026, 9, 22),
        event=Event(SYNTHETIC_EVENT),
        archive_sha256=archive_digest(archive),
    )


# ------------------------------------------------------------------------------------------------
# caselist unsuppress
# ------------------------------------------------------------------------------------------------


class TestUnsuppress:
    async def test_unsuppress_appends_an_entry_and_a_log_entry_and_the_next_import_stores_the_file(
        self, removal_world: RemovalWorld, tmp_path: Path
    ) -> None:
        await remove_bayview(removal_world)
        assert (await import_third_week_again(removal_world, tmp_path / "before")).count(
            Classification.SUPPRESSED
        ) == 1
        listed = local_suppression_list_file(removal_world.data_dir).path
        before = listed.read_bytes()

        service = removal_world.service()
        plan = await service.plan_unsuppress(
            BAYVIEW, reason=ReasonCode.REMOVED_IN_ERROR, request_id="RM-2026-03"
        )
        report = await service.unsuppress(plan)

        assert listed.read_bytes().startswith(before), "the list was appended to, not rewritten"
        last = SuppressionEntry.from_line(listed.read_text().splitlines()[-1])
        assert last.action is SuppressionAction.UNSUPPRESS and last.sha256 == BAYVIEW
        log = [
            RemovalLogEntry.from_line(line)
            for line in local_removal_log_file(removal_world.data_dir).path.read_text().splitlines()
        ]
        assert [entry.kind for entry in log] == [RemovalLogKind.REMOVAL, RemovalLogKind.UNSUPPRESS]
        assert log[-1] == report.log_entry and log[-1].unsuppressed_sha256 == (BAYVIEW,)

        again = await import_third_week_again(removal_world, tmp_path / "after")
        assert again.count(Classification.SUPPRESSED) == 0
        assert await FsSnapshotStore(removal_world.data_dir).exists(BAYVIEW), "stored again"
        assert (await removal_world.repository.list_disclosures(source_sha256=BAYVIEW, limit=5)).items

    async def test_unsuppress_reaches_the_buckets_copy_too(self, removal_world: RemovalWorld) -> None:
        await remove_bayview(removal_world)
        service = removal_world.service()
        await service.unsuppress(await service.plan_unsuppress(BAYVIEW, reason=ReasonCode.REQUEST_WITHDRAWN))

        bucket_copy = removal_world.client.get_object(
            Bucket=removal_world.bucket_name, Key=SUPPRESSION_LIST_KEY
        )
        entries = [
            SuppressionEntry.from_line(line) for line in bucket_copy["Body"].read().decode().splitlines()
        ]
        assert [entry.action for entry in entries if entry.sha256 == BAYVIEW] == [
            SuppressionAction.SUPPRESS,
            SuppressionAction.UNSUPPRESS,
        ]
        assert not SuppressionState.from_entries(entries).is_suppressed(BAYVIEW)

    async def test_unsuppress_refuses_a_file_that_is_not_suppressed(
        self, removal_world: RemovalWorld
    ) -> None:
        with pytest.raises(NotSuppressed):
            await removal_world.service().plan_unsuppress(BAYVIEW, reason=ReasonCode.REMOVED_IN_ERROR)

    async def test_unsuppress_is_not_a_reason_to_suppress(self, removal_world: RemovalWorld) -> None:
        await remove_bayview(removal_world)
        with pytest.raises(Exception, match="--reason"):
            await removal_world.service().plan_unsuppress(BAYVIEW, reason=ReasonCode.REQUESTED_BY_TEAM)


# ------------------------------------------------------------------------------------------------
# The removal profile
# ------------------------------------------------------------------------------------------------


class EverydayProfileVersions:
    """What AWS answers the EvidenceOperator profile: no ListBucketVersions, no DeleteObjectVersion."""

    def __init__(self, bucket: str) -> None:
        self.location = f"s3://{bucket}"

    async def list_versions(self, prefix: str) -> tuple[ObjectVersion, ...]:
        raise StoreAccessDenied("ListObjectVersions", f"{self.location}/{prefix}")

    async def get_version_file(self, version: ObjectVersion, destination: Path) -> None:
        raise StoreAccessDenied("GetObject", version.key)

    async def delete_versions(self, versions: Sequence[ObjectVersion]) -> int:
        raise StoreAccessDenied("DeleteObject", self.location)


class ListsButCannotDelete(EverydayProfileVersions):
    """A profile that may list versions and may not delete them."""

    def __init__(self, inner: S3EvidenceVersionStore, bucket: str) -> None:
        super().__init__(bucket)
        self._inner = inner

    async def list_versions(self, prefix: str) -> tuple[ObjectVersion, ...]:
        return await self._inner.list_versions(prefix)


def unchanged(world: RemovalWorld) -> tuple[Any, ...]:
    return world.tree(), world.versions(), world.records()


class TestTheRemovalProfile:
    async def test_removal_profile_unset_stops_the_run_before_any_change(
        self, removal_world: RemovalWorld
    ) -> None:
        before = unchanged(removal_world)

        def unset() -> TakedownAccess:
            raise TakedownNotConfigured

        service = removal_world.service(takedown=unset)
        plan = await service.plan(SourceSelector(BAYVIEW), request_id="RM-2026-03", reason=ReasonCode.POLICY)
        with pytest.raises(TakedownNotConfigured, match="DEBATE_REMOVAL_PROFILE"):
            await service.execute(plan)

        assert unchanged(removal_world) == before
        assert not (removal_world.data_dir / "suppression").exists(), "nothing appended either"

    @pytest.mark.parametrize("profile", ["everyday", "cannot_delete"])
    async def test_removal_profile_without_delete_rights_fails_preflight_with_nothing_deleted(
        self, removal_world: RemovalWorld, profile: str
    ) -> None:
        tree, _, records = unchanged(removal_world)
        evidence_before = [
            key for key in removal_world.versions() if not key[0].startswith("manifests/_suppression/")
        ]
        real = removal_world.takedown()
        versions = (
            EverydayProfileVersions(removal_world.bucket_name)
            if profile == "everyday"
            else ListsButCannotDelete(
                S3EvidenceVersionStore(bucket=removal_world.bucket_name, client=removal_world.client),
                removal_world.bucket_name,
            )
        )

        def refusing() -> TakedownAccess:
            return TakedownAccess(
                versions=versions, objects=real.objects, profile="debate-dev-evidence", bucket=real.bucket
            )  # type: ignore[arg-type]

        service = removal_world.service(takedown=refusing)
        plan = await service.plan(SourceSelector(BAYVIEW), request_id="RM-2026-03", reason=ReasonCode.POLICY)
        with pytest.raises(TakedownPreflightFailed) as refused:
            await service.execute(plan)

        message = str(refused.value)
        assert "debate-dev-evidence" in message and "nothing was deleted" in message
        assert "probe object was left at manifests/_suppression/preflight/" in message
        assert [
            key for key in removal_world.versions() if not key[0].startswith("manifests/_suppression/")
        ] == evidence_before
        assert removal_world.tree() == tree and removal_world.records() == records
        assert not (removal_world.data_dir / "suppression").exists()

    async def test_removal_profile_signed_out_is_reported_with_the_login_command(
        self, removal_world: RemovalWorld
    ) -> None:
        def expired() -> TakedownAccess:
            raise StoreCredentialsExpired(
                "the AWS session has expired", hint="aws sso login --profile debate-dev-evidence-removal"
            )

        service = removal_world.service(takedown=expired)
        plan = await service.plan(SourceSelector(BAYVIEW), request_id="RM-2026-03", reason=ReasonCode.POLICY)
        with pytest.raises(TakedownPreflightFailed) as refused:
            await service.execute(plan)

        assert refused.value.hint == "aws sso login --profile debate-dev-evidence-removal"

    async def test_removal_profile_preflight_leaves_no_probe_behind_when_it_succeeds(
        self, removal_world: RemovalWorld
    ) -> None:
        await remove_bayview(removal_world)

        probes = [
            key for key, _ in removal_world.versions() if key.startswith("manifests/_suppression/preflight/")
        ]
        assert probes == []

    async def test_unsuppress_needs_the_removal_profile_too(self, removal_world: RemovalWorld) -> None:
        await remove_bayview(removal_world)
        before = local_suppression_list_file(removal_world.data_dir).path.read_bytes()

        def unset() -> TakedownAccess:
            raise TakedownNotConfigured

        service = removal_world.service(takedown=unset)
        plan = await service.plan_unsuppress(BAYVIEW, reason=ReasonCode.REMOVED_IN_ERROR)
        with pytest.raises(TakedownNotConfigured):
            await service.unsuppress(plan)
        assert local_suppression_list_file(removal_world.data_dir).path.read_bytes() == before
