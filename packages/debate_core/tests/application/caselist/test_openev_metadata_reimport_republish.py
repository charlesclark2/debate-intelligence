"""After a metadata re-import, an ordinary publish brings the bucket back in line (`v1-e30-t08`, ac4).

The re-import rewrites the release manifest's bytes at the same key and changes nothing else. This
follows that through the bucket, on moto with versioning on as the real buckets have it:

* `caselist status` reports the release as drifted on its manifest alone: one checksum mismatch, on
  the manifest's key, with every source present and verified;
* `caselist publish` re-uploads that one manifest and no source, because a manifest is not
  content-addressed and the publisher uploads a listed manifest whose recorded digest differs from
  the local one;
* `status` is clean again, and the superseded manifest stays in the bucket as one noncurrent version.

So the re-import needs no publish of its own, and nothing about publishing was loosened for it.
Invented camps and titles only; nothing reaches AWS.
"""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from tests.fixtures.openev.build_synthetic_openev import CAMP_ALIASES_PATH

from debate_core.application.caselist.camp_metadata import CampAliases, load_camp_aliases
from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.manifest import read_manifest_lines, write_manifest_lines
from debate_core.application.caselist.openev_import_service import OpenEvImportService
from debate_core.application.caselist.openev_manifest import openev_manifest_key
from debate_core.application.caselist.openev_metadata_reimport import OpenEvMetadataReimportService
from debate_core.application.caselist.publish_plan import OPENEV
from debate_core.application.caselist.publish_service import (
    CaselistPublishService,
    ManifestOutcome,
    SourceResult,
)
from debate_core.application.caselist.status_service import CaselistStatusService
from debate_core.application.ports.archive import ArchiveMember
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsEvidenceObjectStore, FsSnapshotStore, SqliteDatabase
from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository
from debate_core.integrations.s3 import S3EvidenceObjectStore
from debate_core.testing.fakes import empty_suppression_list

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

RELEASE = "2026-policy"
KEY = openev_manifest_key(2026, Event.POLICY)
FILES = {
    "Disadvantages/Lantern Shipping DA - TSF 2026 MNOP.docx": b"lantern shipping filler",
    "Counterplans/NEG Orchard Grants CP - QDI 2026 JKT.docx": b"orchard grants filler",
    "Topicality/Saltmarsh T - Zephyr 2026.docx": b"saltmarsh topicality filler",
}


class Store:
    """One data directory as `import-openev` leaves it, and the moto bucket it is published to."""

    def __init__(self, data_dir: Path, bucket: S3EvidenceObjectStore) -> None:
        self.data_dir = data_dir
        self.bucket = bucket
        self.caselists = SqliteCaselistRepository(SqliteDatabase.open(data_dir))
        self.objects = FsEvidenceObjectStore(data_dir)
        blobs = FsEvidenceObjectStore(data_dir, subdirectory=Path("blobs"))
        self.local = LocalEvidence(
            objects=self.objects,
            blobs=blobs,
            object_path_for=self.objects.path_for,
            blob_path_for=blobs.path_for,
        )

    @property
    def manifest_path(self) -> Path:
        return self.objects.path_for(KEY)

    async def import_release(self, aliases: CampAliases) -> None:
        service = OpenEvImportService(
            caselists=self.caselists,
            blobs=FsSnapshotStore(self.data_dir),
            suppression=empty_suppression_list(),
        )
        members = [
            ArchiveMember(path=path, sha256=hashlib.sha256(body).hexdigest(), byte_size=len(body), data=body)
            for path, body in sorted(FILES.items())
        ]
        report = await service.import_release(
            members,
            year=2026,
            event=Event.POLICY,
            imported_on=_imported_on(),
            archive_sha256="b" * 64,
            aliases=aliases,
        )
        write_manifest_lines(report.manifest_lines, self.manifest_path)

    async def reimport_metadata(self, aliases: CampAliases) -> None:
        service = OpenEvMetadataReimportService(
            caselists=self.caselists,
            blobs=FsSnapshotStore(self.data_dir),
            suppression=empty_suppression_list(),
        )
        report = await service.reimport(
            year=2026,
            event=Event.POLICY,
            recorded_manifest=read_manifest_lines(self.manifest_path),
            aliases=aliases,
        )
        assert report.manifest_changed
        write_manifest_lines(report.manifest_lines, self.manifest_path)

    async def publish(self) -> Any:
        service = CaselistPublishService(
            local=self.local, remote=self.bucket, suppression=empty_suppression_list()
        )
        return await service.execute(await service.plan(OPENEV, RELEASE))

    async def status(self) -> Any:
        service = CaselistStatusService(
            local=self.local, remote=self.bucket, suppression=empty_suppression_list()
        )
        return await service.status(OPENEV, RELEASE)


def _imported_on() -> date:
    return date(2026, 9, 26)


@pytest.fixture
async def published(tmp_path: Path, evidence_bucket: str, s3_client: S3Client) -> Store:
    """The release imported with one camp readable of three, published, and in sync."""
    store = Store(tmp_path / "evidence", S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client))
    await store.import_release(CampAliases.from_document({"camps": {"QDI": ["Quillfeather"]}}, source="one"))
    first = await store.publish()
    assert first.succeeded
    assert (await store.status()).in_sync
    return store


def manifest_versions(client: S3Client, bucket: str) -> list[bool]:
    """`IsLatest` for every version of the release manifest, newest first."""
    listed = client.list_object_versions(Bucket=bucket, Prefix=KEY).get("Versions", [])
    return [bool(version.get("IsLatest")) for version in listed if version.get("Key") == KEY]


async def test_reimport_leaves_the_bucket_drifted_on_the_manifest_alone(published: Store) -> None:
    await published.reimport_metadata(load_camp_aliases(CAMP_ALIASES_PATH))

    report = await published.status()

    assert not report.in_sync
    (entry,) = report.snapshots
    # The bucket holds a manifest at the key, with other bytes: one checksum mismatch, on the
    # manifest's own key, and every source present and verified.
    assert entry.manifest_present is True
    assert entry.checksum_mismatches == (KEY,)
    assert (entry.published_sources, entry.sources) == (3, 3)
    assert (entry.missing_sources, entry.missing_local) == ((), ())


async def test_reimport_then_publish_re_uploads_the_manifest_and_no_source(
    published: Store, evidence_bucket: str, s3_client: S3Client
) -> None:
    await published.reimport_metadata(load_camp_aliases(CAMP_ALIASES_PATH))

    second = await published.publish()

    (outcome,) = second.snapshots
    assert outcome.manifest is ManifestOutcome.UPLOADED
    assert len(outcome.of(SourceResult.UPLOADED)) == 0
    assert len(outcome.of(SourceResult.SKIPPED)) == 3
    assert (await published.status()).in_sync
    assert manifest_versions(s3_client, evidence_bucket) == [True, False]


async def test_reimport_then_publish_keeps_one_version_of_every_source(
    published: Store, evidence_bucket: str, s3_client: S3Client
) -> None:
    await published.reimport_metadata(load_camp_aliases(CAMP_ALIASES_PATH))
    await published.publish()

    listed = s3_client.list_object_versions(Bucket=evidence_bucket, Prefix="raw/openev/").get("Versions", [])

    keys = [str(version.get("Key")) for version in listed]
    assert len(keys) == len(set(keys)) == 3
