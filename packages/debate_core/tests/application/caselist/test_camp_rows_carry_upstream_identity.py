"""A camp file's manifest row carries its upstream identity, and prod's plan matches by it (`v1-e30-t14` ac1).

OpenEv changes a camp file only by deleting it and uploading it again under a new id, at the same
upstream path (`v1-e34-t08`). A removal takes such a later upload down with the file it follows
(`v1-e30-t11`), and needs to know which rows of a release are at one camp path. A release row keeps
no camp folder, so two camps' files of one name read alike. Dev could tell them apart from this
machine's delivery record, which keeps each id's upstream path as a digest. Prod never pulls, so it
has no delivery record, and its plan said *matched by file name alone* and listed the other camp's
file too.

Now every row the pull writes carries the OpenEv id it was downloaded as and the SHA-256 of that
id's upstream path, never the path. Prod's manifests are published from the dev data directory, so
the same rows reach prod's bucket, and a plan made there, with no delivery record and no manifest of
its own, matches by them.

Each world is built by the real pull, through the helpers of the `v1-e34-t07`, `t08` and `v1-e30-t11`
tests, on the synthetic camp files of `tests/fixtures/openev/`. Every expected value is written out
from what each test lists upstream:

| OpenEv id | Upstream path |
|---|---|
| 512 | `openev/2026/Tamarack/TSF-Estuary Solvency Advocate.docx` |
| 640 | the same path, uploaded again |
| 700 | `openev/2026/Quillfeather/TSF-Estuary Solvency Advocate.docx` |

Each is a row of `2026-policy` named `openev-<id>-TSF-Estuary_Solvency_Advocate.docx`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from debate_core.application.caselist.manifest import read_manifest_lines, write_manifest_lines
from debate_core.application.caselist.openev_import_service import OpenEvImportService
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.removal_path_versions import SamePathEvidence
from debate_core.application.caselist.removal_plan import RemovalPlan, SourceSelector
from debate_core.application.caselist.status_service import CaselistStatusService
from debate_core.application.caselist_sync import OPENEV_DELIVERIES_FILENAME, OpenEvDeliveries
from debate_core.application.ports.suppression import ReasonCode
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsEvidenceObjectStore, FsSnapshotStore
from debate_core.integrations.s3 import S3EvidenceObjectStore

from .conftest import REQUEST, RemovalWorld
from .test_removal_covers_later_camp_uploads import (
    NEW_ROW,
    OTHER_CAMP,
    OTHER_CAMP_BODY,
    OTHER_CAMP_ROW,
    OTHER_CAMP_SHA256,
    RELEASE,
    RELEASE_KEY,
    REVISED_SHA256,
    pulled_then_revised,
)
from .test_sync_fetches_revised_camp_files import OLD_ROW, TITLE_WORDS
from .test_sync_skips_suppressed_downloads import ESTUARY, ESTUARY_SHA256

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

PROD_BUCKET = "debate-prod-evidence-identity-moto"

#: The SHA-256 of each upstream path, as `GET /openev` listed it: 512 and 640 share one.
TAMARACK_PATH_SHA256 = hashlib.sha256(b"openev/2026/Tamarack/TSF-Estuary Solvency Advocate.docx").hexdigest()
QUILLFEATHER_PATH_SHA256 = hashlib.sha256(
    b"openev/2026/Quillfeather/TSF-Estuary Solvency Advocate.docx"
).hexdigest()

#: What each row of the release says it is upstream: `(openev_id, upstream_path_sha256)`.
EXPECTED_IDENTITY = {
    OLD_ROW: (512, TAMARACK_PATH_SHA256),
    NEW_ROW: (640, TAMARACK_PATH_SHA256),
    OTHER_CAMP_ROW: (700, QUILLFEATHER_PATH_SHA256),
}


@pytest.fixture
def world(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> RemovalWorld:
    """Dev: this machine's data directory, which the pull imports into, and the dev bucket."""
    return RemovalWorld(data_dir=tmp_path / "evidence", bucket_name=evidence_bucket, client=s3_client)


@pytest.fixture
def prod(tmp_path: Path, s3_client: S3Client) -> RemovalWorld:
    """Prod: its own, empty, data directory and its own bucket. Prod never pulls."""
    s3_client.create_bucket(Bucket=PROD_BUCKET)
    s3_client.put_bucket_versioning(Bucket=PROD_BUCKET, VersioningConfiguration={"Status": "Enabled"})
    return RemovalWorld(data_dir=tmp_path / "prod-evidence", bucket_name=PROD_BUCKET, client=s3_client)


def identities(lines: list[str]) -> dict[str, tuple[object, object]]:
    """Each member row's `(openev_id, upstream_path_sha256)`, by its path. Absent keys read as `None`."""
    rows = [json.loads(line) for line in lines]
    return {
        row["path"]: (row.get("openev_id"), row.get("upstream_path_sha256"))
        for row in rows
        if row["kind"] == "member"
    }


def bucket_lines(client: S3Client, bucket: str) -> list[str]:
    return client.get_object(Bucket=bucket, Key=RELEASE_KEY)["Body"].read().decode().splitlines()


async def published_to_prod_from_the_dev_data_directory(world: RemovalWorld, prod: RemovalWorld) -> None:
    """`DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR=<dev> caselist publish --caselist openev --snapshot …`."""
    publisher = CaselistPublishService(
        local=world.local,
        remote=S3EvidenceObjectStore(bucket=prod.bucket_name, client=prod.client),
        suppression=world.suppression(),
    )
    assert (await publisher.execute(await publisher.plan("openev", RELEASE))).succeeded


async def plan_in(environment: RemovalWorld) -> RemovalPlan:
    return await environment.service().plan(
        SourceSelector(ESTUARY_SHA256), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_CAMP
    )


# ------------------------------------------------------------------------------------------------
# The rows
# ------------------------------------------------------------------------------------------------


async def test_each_row_the_pull_writes_carries_its_openev_id_and_upstream_path_digest_here_and_in_dev(
    world: RemovalWorld,
) -> None:
    await pulled_then_revised(world, (OTHER_CAMP, OTHER_CAMP_BODY))

    local = read_manifest_lines(FsEvidenceObjectStore(world.data_dir).path_for(RELEASE_KEY))
    assert identities(local) == EXPECTED_IDENTITY
    assert identities(bucket_lines(world.client, world.bucket_name)) == EXPECTED_IDENTITY


async def test_prod_published_from_the_dev_data_directory_carries_the_same_rows(
    world: RemovalWorld, prod: RemovalWorld
) -> None:
    await pulled_then_revised(world, (OTHER_CAMP, OTHER_CAMP_BODY))

    await published_to_prod_from_the_dev_data_directory(world, prod)

    assert identities(bucket_lines(prod.client, prod.bucket_name)) == EXPECTED_IDENTITY


async def test_the_identity_names_no_camp_title_or_file(world: RemovalWorld) -> None:
    """An id and a digest: neither the upstream path nor any word of it is in the two values."""
    await pulled_then_revised(world, (OTHER_CAMP, OTHER_CAMP_BODY))

    local = read_manifest_lines(FsEvidenceObjectStore(world.data_dir).path_for(RELEASE_KEY))
    values = json.dumps(sorted(identities(local).values()))
    assert ESTUARY.path not in values and OTHER_CAMP.path not in values
    assert not [word for word in (*TITLE_WORDS, "Quillfeather", "docx") if word in values]


# ------------------------------------------------------------------------------------------------
# The prod plan
# ------------------------------------------------------------------------------------------------


async def test_the_prod_plan_matches_the_later_upload_by_its_upstream_identity(
    world: RemovalWorld, prod: RemovalWorld
) -> None:
    """No delivery record and no manifest of its own: what prod knows is the bucket's rows."""
    await pulled_then_revised(world, (OTHER_CAMP, OTHER_CAMP_BODY))
    await published_to_prod_from_the_dev_data_directory(world, prod)
    assert not prod.data_dir.exists() or not any(prod.data_dir.rglob("*.json"))

    plan = await plan_in(prod)

    assert {one.sha256: (one.openev_ids, one.evidence) for one in plan.later_uploads} == {
        REVISED_SHA256: ((640,), SamePathEvidence.UPSTREAM_PATH_DIGEST)
    }
    assert OTHER_CAMP_SHA256 not in {one.sha256 for one in (*plan.later_uploads, *plan.earlier_versions)}
    assert plan.source(OTHER_CAMP_SHA256) is None


async def test_the_prod_plan_matches_what_the_dev_plan_matches(
    world: RemovalWorld, prod: RemovalWorld
) -> None:
    """The comparison the runbook's step 7 asked the operator to make by hand, made by the two plans."""
    await pulled_then_revised(world, (OTHER_CAMP, OTHER_CAMP_BODY))
    await published_to_prod_from_the_dev_data_directory(world, prod)

    in_dev, in_prod = await plan_in(world), await plan_in(prod)

    def matched(plan: RemovalPlan) -> list[tuple[str, tuple[int, ...], SamePathEvidence]]:
        return sorted((one.sha256, one.openev_ids, one.evidence) for one in plan.later_uploads)

    assert (
        matched(in_prod)
        == matched(in_dev)
        == [(REVISED_SHA256, (640,), SamePathEvidence.UPSTREAM_PATH_DIGEST)]
    )


async def test_executed_in_prod_it_leaves_the_other_camps_file_of_the_same_name(
    world: RemovalWorld, prod: RemovalWorld
) -> None:
    await pulled_then_revised(world, (OTHER_CAMP, OTHER_CAMP_BODY))
    await published_to_prod_from_the_dev_data_directory(world, prod)
    service = prod.service()

    assert (await service.execute(await plan_in(prod))).completed

    rows = [json.loads(line) for line in bucket_lines(prod.client, prod.bucket_name)]
    assert {row["path"]: row["sha256"] for row in rows if row["kind"] == "member"} == {
        OTHER_CAMP_ROW: OTHER_CAMP_SHA256
    }


# ------------------------------------------------------------------------------------------------
# Rows an older build wrote: how prod's camp rows get their identity
# ------------------------------------------------------------------------------------------------


def as_an_older_build_wrote_them(world: RemovalWorld, *buckets: str) -> None:
    """The release manifest without the two keys, here and in each bucket: what prod holds today."""
    path = FsEvidenceObjectStore(world.data_dir).path_for(RELEASE_KEY)
    rows = [json.loads(line) for line in read_manifest_lines(path)]
    older = [
        json.dumps(
            {key: value for key, value in row.items() if key not in ("openev_id", "upstream_path_sha256")},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        for row in rows
    ]
    write_manifest_lines(older, path)
    for bucket in buckets:
        world.client.put_object(Bucket=bucket, Key=RELEASE_KEY, Body=path.read_bytes())


async def test_re_deriving_the_release_gives_older_rows_their_identity_and_a_publish_takes_it_to_prod(
    world: RemovalWorld, prod: RemovalWorld
) -> None:
    """The operator's follow-up, in order: re-derive in dev's data directory, see status ask for a
    publish, publish to dev, then to prod from the same directory. Prod's plan then matches by it."""
    await pulled_then_revised(world, (OTHER_CAMP, OTHER_CAMP_BODY))
    as_an_older_build_wrote_them(world, world.bucket_name, prod.bucket_name)
    before = await plan_in(prod)
    assert {one.sha256: one.evidence for one in before.later_uploads} == {
        REVISED_SHA256: SamePathEvidence.ROW_NAME,
        OTHER_CAMP_SHA256: SamePathEvidence.ROW_NAME,
    }, "prod today: matched by file name alone, and the other camp's file with it"

    path = FsEvidenceObjectStore(world.data_dir).path_for(RELEASE_KEY)
    importer = OpenEvImportService(
        caselists=world.repository, blobs=FsSnapshotStore(world.data_dir), suppression=world.suppression()
    )
    report = await importer.reimport_metadata(
        year=2026,
        event=Event.POLICY,
        recorded_manifest=read_manifest_lines(path),
        upstream_paths=OpenEvDeliveries(world.data_dir / OPENEV_DELIVERIES_FILENAME).upstream_paths(),
    )
    write_manifest_lines(report.manifest_lines, path)

    assert (report.identities_added, report.rows_changed, report.camp_files_updated) == (3, 0, 0)
    assert identities(read_manifest_lines(path)) == EXPECTED_IDENTITY
    status = await CaselistStatusService(
        local=world.local, remote=world.bucket, suppression=world.suppression()
    ).status("openev")
    (snapshot,) = status.snapshots
    assert (snapshot.snapshot, snapshot.manifest_mismatched, snapshot.source_mismatches) == (
        RELEASE,
        True,
        (),
    )

    publisher = CaselistPublishService(
        local=world.local, remote=world.bucket, suppression=world.suppression()
    )
    assert (await publisher.execute(await publisher.plan("openev", RELEASE))).succeeded
    assert (
        await CaselistStatusService(
            local=world.local, remote=world.bucket, suppression=world.suppression()
        ).status("openev")
    ).in_sync
    await published_to_prod_from_the_dev_data_directory(world, prod)

    after = await plan_in(prod)
    assert {one.sha256: one.evidence for one in after.later_uploads} == {
        REVISED_SHA256: SamePathEvidence.UPSTREAM_PATH_DIGEST
    }


async def test_re_deriving_again_changes_nothing(world: RemovalWorld) -> None:
    """Rows the pull wrote already carry it: a re-derive gives none, and writes the same lines."""
    await pulled_then_revised(world, (OTHER_CAMP, OTHER_CAMP_BODY))
    path = FsEvidenceObjectStore(world.data_dir).path_for(RELEASE_KEY)
    importer = OpenEvImportService(
        caselists=world.repository, blobs=FsSnapshotStore(world.data_dir), suppression=world.suppression()
    )

    report = await importer.reimport_metadata(
        year=2026,
        event=Event.POLICY,
        recorded_manifest=read_manifest_lines(path),
        upstream_paths=OpenEvDeliveries(world.data_dir / OPENEV_DELIVERIES_FILENAME).upstream_paths(),
    )

    assert report.identities_added == 0 and not report.manifest_changed


async def test_a_row_the_delivery_record_does_not_know_keeps_null(world: RemovalWorld) -> None:
    """A re-derive on a machine whose record has lost an id: the id from the name, no digest invented."""
    await pulled_then_revised(world, (OTHER_CAMP, OTHER_CAMP_BODY))
    as_an_older_build_wrote_them(world)
    path = FsEvidenceObjectStore(world.data_dir).path_for(RELEASE_KEY)
    importer = OpenEvImportService(
        caselists=world.repository, blobs=FsSnapshotStore(world.data_dir), suppression=world.suppression()
    )

    report = await importer.reimport_metadata(
        year=2026,
        event=Event.POLICY,
        recorded_manifest=read_manifest_lines(path),
        upstream_paths={512: TAMARACK_PATH_SHA256},
    )

    assert identities(list(report.manifest_lines)) == {
        OLD_ROW: (512, TAMARACK_PATH_SHA256),
        NEW_ROW: (640, None),
        OTHER_CAMP_ROW: (700, None),
    }


async def test_a_row_whose_upstream_digest_is_not_one_carries_no_identity(world: RemovalWorld) -> None:
    """Rows saying `""` for every path would otherwise all be at one upstream path, the other camp's too."""
    await pulled_then_revised(world, (OTHER_CAMP, OTHER_CAMP_BODY))
    (world.data_dir / OPENEV_DELIVERIES_FILENAME).unlink()
    path = FsEvidenceObjectStore(world.data_dir).path_for(RELEASE_KEY)
    rows = [json.loads(line) for line in read_manifest_lines(path)]
    lines = [
        json.dumps(
            {**row, "upstream_path_sha256": ""} if row["kind"] == "member" else row,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        for row in rows
    ]
    write_manifest_lines(lines, path)
    world.client.put_object(Bucket=world.bucket_name, Key=RELEASE_KEY, Body=path.read_bytes())

    plan = await plan_in(world)

    assert {one.sha256: one.evidence for one in plan.later_uploads} == {
        REVISED_SHA256: SamePathEvidence.ROW_NAME,
        OTHER_CAMP_SHA256: SamePathEvidence.ROW_NAME,
    }
