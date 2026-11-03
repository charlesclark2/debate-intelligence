"""The run files this build leaves when its parse stage meets a table a newer build stamped.

Not collected: its name is not a test module's, and it runs only when named, with the variable
`WRITE_NEWER_FINGERPRINT_TABLE_FILES` set to the directory to write into (`v1-e34-t29`). Then
`read_sync_run_files.py` reads what it wrote with each build: the run log, the details, the records
still owed, the pending-work file when there is one, and every object under `reports/` in the
bucket, each with that build's own readers. The commands and what they printed are in the session
report of `v1-e34-t29`.

Each scenario is pulls through the real run monitor, as `test_pull_refuses_a_newer_fingerprint_table.py`
runs them, against moto, with synthetic fingerprint versions. Written for each, under `<scenario>/`:

* `refused_here`: a pull at the newer version, then one at this build's, whose parse stage is
  refused over this machine's table;
* `refused_in_the_bucket`: another machine at the newer version publishes, then this machine's
  pull parses and is refused the publish over the bucket's table;
* `older_rebuilt`: a pull at an older version, then one at this build's, which rebuilds as before.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from debate_core.application.caselist_sync import PENDING_WORK_FILENAME
from debate_core.application.sync_runs import (
    PENDING_RECORDS_FILENAME,
    SYNC_RUN_DETAILS_FILENAME,
    SYNC_RUN_LOG_FILENAME,
)

from .test_inbox_retention import WEEK_1, WEEK_2, WEEK_3, FakeSource, Installation
from .test_pull_parses_new_sources import installation as installation  # noqa: F401 - a fixture
from .test_pull_parses_new_sources import parse_stage
from .test_pull_refuses_a_newer_fingerprint_table import BUILD, NEWER, OLDER
from .test_pull_refuses_a_newer_fingerprint_table import as_build as as_build  # noqa: F401 - a fixture
from .test_pull_stage_failure_codes import pull

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

REPORTS_PREFIX = "reports/"


def out() -> Path:
    where = os.environ.get("WRITE_NEWER_FINGERPRINT_TABLE_FILES")
    if not where:
        pytest.skip("set WRITE_NEWER_FINGERPRINT_TABLE_FILES to the directory to write into")
    return Path(where)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def keep(installation: Installation, s3_client: S3Client, bucket: str, scenario: str) -> None:
    into = out() / scenario
    if into.exists():
        shutil.rmtree(into)
    into.mkdir(parents=True)
    for name in (
        SYNC_RUN_LOG_FILENAME,
        SYNC_RUN_DETAILS_FILENAME,
        PENDING_RECORDS_FILENAME,
        PENDING_WORK_FILENAME,
    ):
        if (installation.data_dir / name).is_file():
            shutil.copyfile(installation.data_dir / name, into / name)
    listed = s3_client.list_objects_v2(Bucket=bucket, Prefix=REPORTS_PREFIX).get("Contents", [])
    objects = {
        str(one.get("Key")): s3_client.get_object(Bucket=bucket, Key=str(one.get("Key")))["Body"]
        .read()
        .decode("utf-8")
        for one in listed
    }
    (into / "bucket.json").write_text(json.dumps(objects, indent=2, sort_keys=True) + "\n", encoding="utf-8")


async def two_pulls(installation: Installation, as_build: Callable[[str], None], first: str) -> None:
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    as_build(first)
    await pull(installation, installation.sync(source, parse=parse_stage(installation)))
    as_build(BUILD)
    source.weeks = [WEEK_1, WEEK_2, WEEK_3]
    await pull(installation, installation.sync(source, parse=parse_stage(installation)))


async def test_refused_here(
    installation: Installation, as_build: Callable[[str], None], s3_client: S3Client, evidence_bucket: str
) -> None:
    out()
    await two_pulls(installation, as_build, NEWER)
    keep(installation, s3_client, evidence_bucket, "refused_here")


async def test_refused_in_the_bucket(
    installation: Installation,
    as_build: Callable[[str], None],
    s3_client: S3Client,
    evidence_bucket: str,
    tmp_path: Path,
) -> None:
    out()
    other = Installation(
        data_dir=tmp_path / "newer-machine", bucket=installation.bucket, archives=installation.archives
    )
    as_build(NEWER)
    await pull(
        other, other.sync(FakeSource(other.archives, weeks=[WEEK_1, WEEK_2]), parse=parse_stage(other))
    )
    as_build(BUILD)
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    await pull(installation, installation.sync(source, parse=parse_stage(installation)))
    keep(installation, s3_client, evidence_bucket, "refused_in_the_bucket")


async def test_older_rebuilt(
    installation: Installation, as_build: Callable[[str], None], s3_client: S3Client, evidence_bucket: str
) -> None:
    out()
    await two_pulls(installation, as_build, OLDER)
    keep(installation, s3_client, evidence_bucket, "older_rebuilt")
