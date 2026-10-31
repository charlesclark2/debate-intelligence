"""The run files this build leaves when its parse stage owes parsed stores (`v1-e34-t31`), for earlier builds.

Not collected: its name is not a test module's, and it runs only when named, with the variable
`WRITE_PARSED_STORES_OWED_FILES` set to the directory to write into. Then `read_sync_run_files.py`
reads what it wrote with each build, the run log, the details and every object under `reports/` in
the bucket, each with that build's own readers. The commands and what they printed are in the
session report of `v1-e34-t31`.

Each scenario is one pull through the real run monitor, with the scripted parse stage of
`test_caselist_sync_names_publish_only_per_caselist.py`, in an installation of its own, against
moto. Written for each, under `<scenario>/`: the run log, the run details, and every object the run
put under `reports/` in the bucket (`bucket.json`, key to body):

* `one_of_each_failed`: the weekly's publish refused after a rebuild from every copy of the list
  (`--publish-only`), and the camp file's rebuild from the run's own copy alone (`--publish`). A
  failed stage.
* `one_of_each_pending`: the other way round, with no failure. A pending stage, and a login banner.
* `bucket_mode_publish_refused`: the weekly's publish refused after a rebuild from every copy, in a
  run whose working copy does not outlive it (`--publish`).

Since `v1-e40-t18`, two runs in bucket mode as the composition root builds it, with the bracket of
`test_caselist_sync_names_the_cloud_cure_in_bucket_mode.py`, whose details record `bucket_run`:

* `cloud_one_of_each_failed`: `one_of_each_failed` in bucket mode. The cloud cure for both.
* `cloud_pending`: the weekly's rebuild read the run's own copy of the list alone. A pending stage,
  and a login banner whose parsed-store sentence is the cloud cure. Since `v1-e40-t22` its fix is
  the cloud run's task role.

Since `v1-e40-t22`, two more in bucket mode, with the scripted parse stage of
`test_caselist_sync_bucket_mode_hints_point_at_the_cloud.py`, one for each of its other hints:

* `cloud_failure_rate`: six of the weekly's ten sources failed, over the threshold. A failed stage
  whose hint names the failures file the cloud run published.
* `cloud_newer_table`: the bucket's occurrence table is stamped by a newer build. A failed stage
  whose hint names a new image.

Since `v1-e40-t25`, three more in bucket mode, through the runs of
`test_caselist_sync_bucket_mode_publish_hints_point_at_the_cloud.py`, one for each banner it moved:

* `cloud_failed_publish`: the bucket did not answer the publish. A failed stage whose banner names
  the next cloud run.
* `cloud_published_again`: the report stage found week one's manifest differs, and owed it again.
* `cloud_login_owed_again`: the same, and the session expired at week two's comparison. A login
  banner.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_synthetic_archives import build_snapshot_zips

from debate_core.application.sync_runs import SYNC_RUN_DETAILS_FILENAME, SYNC_RUN_LOG_FILENAME
from debate_core.integrations.s3 import S3EvidenceObjectStore

from . import test_caselist_sync_bucket_mode_hints_point_at_the_cloud as hints
from . import test_caselist_sync_bucket_mode_publish_hints_point_at_the_cloud as publish_hints
from . import test_caselist_sync_names_the_cloud_cure_in_bucket_mode as cloud
from .test_caselist_sync_names_publish_only_per_caselist import OPENEV, run
from .test_inbox_retention import CASELIST, Installation
from .test_pull_stage_failure_codes import outage

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

REPORTS_PREFIX = "reports/"


def out() -> Path:
    where = os.environ.get("WRITE_PARSED_STORES_OWED_FILES")
    if not where:
        pytest.skip("set WRITE_PARSED_STORES_OWED_FILES to the directory to write into")
    return Path(where)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def installation(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> Installation:
    return Installation(
        data_dir=tmp_path / "evidence",
        bucket=S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client),
        archives=build_snapshot_zips(tmp_path / "published"),
    )


def keep(installation: Installation, s3_client: S3Client, bucket: str, scenario: str) -> None:
    into = out() / scenario
    if into.exists():
        shutil.rmtree(into)
    into.mkdir(parents=True)
    for name in (SYNC_RUN_LOG_FILENAME, SYNC_RUN_DETAILS_FILENAME):
        shutil.copyfile(installation.data_dir / name, into / name)
    listed = s3_client.list_objects_v2(Bucket=bucket, Prefix=REPORTS_PREFIX)
    objects = {
        str(one.get("Key")): s3_client.get_object(Bucket=bucket, Key=str(one.get("Key")))["Body"]
        .read()
        .decode("utf-8")
        for one in listed.get("Contents", [])
    }
    (into / "bucket.json").write_text(json.dumps(objects, indent=2, sort_keys=True) + "\n", encoding="utf-8")


async def test_one_of_each_failed(
    installation: Installation, s3_client: S3Client, evidence_bucket: str
) -> None:
    out()
    await run(installation, with_a_camp_file=True, refused={CASELIST: outage()}, local_list_only=[OPENEV])
    keep(installation, s3_client, evidence_bucket, "one_of_each_failed")


async def test_one_of_each_pending(
    installation: Installation, s3_client: S3Client, evidence_bucket: str
) -> None:
    out()
    await run(installation, with_a_camp_file=True, local_list_only=[CASELIST])
    keep(installation, s3_client, evidence_bucket, "one_of_each_pending")


async def test_bucket_mode_publish_refused(
    installation: Installation, s3_client: S3Client, evidence_bucket: str
) -> None:
    out()
    await run(installation, refused={CASELIST: outage()}, working_copy_outlives_the_run=False)
    keep(installation, s3_client, evidence_bucket, "bucket_mode_publish_refused")


async def test_cloud_one_of_each_failed(
    installation: Installation, s3_client: S3Client, evidence_bucket: str
) -> None:
    out()
    await cloud.run(
        installation,
        bucket_mode=True,
        with_a_camp_file=True,
        refused={CASELIST: outage()},
        local_list_only=[OPENEV],
    )
    keep(installation, s3_client, evidence_bucket, "cloud_one_of_each_failed")


async def test_cloud_pending(installation: Installation, s3_client: S3Client, evidence_bucket: str) -> None:
    out()
    await cloud.run(installation, bucket_mode=True, local_list_only=[CASELIST])
    keep(installation, s3_client, evidence_bucket, "cloud_pending")


async def test_cloud_failure_rate(
    installation: Installation, s3_client: S3Client, evidence_bucket: str
) -> None:
    out()
    await hints.run(installation, bucket_mode=True, over_the_rate=[CASELIST])
    keep(installation, s3_client, evidence_bucket, "cloud_failure_rate")


async def test_cloud_newer_table(
    installation: Installation, s3_client: S3Client, evidence_bucket: str
) -> None:
    out()
    await hints.run(installation, bucket_mode=True, newer_table=[CASELIST])
    keep(installation, s3_client, evidence_bucket, "cloud_newer_table")


async def test_cloud_failed_publish(
    installation: Installation, s3_client: S3Client, evidence_bucket: str
) -> None:
    out()
    await publish_hints.a_publish_the_bucket_refused(installation, bucket_mode=True)
    keep(installation, s3_client, evidence_bucket, "cloud_failed_publish")


async def test_cloud_published_again(
    installation: Installation, s3_client: S3Client, evidence_bucket: str
) -> None:
    out()
    await publish_hints.a_manifest_owed_again(installation, bucket_mode=True)
    keep(installation, s3_client, evidence_bucket, "cloud_published_again")


async def test_cloud_login_owed_again(
    installation: Installation, s3_client: S3Client, evidence_bucket: str
) -> None:
    out()
    await publish_hints.a_manifest_owed_again_and_the_session_expired(installation, bucket_mode=True)
    keep(installation, s3_client, evidence_bucket, "cloud_login_owed_again")
