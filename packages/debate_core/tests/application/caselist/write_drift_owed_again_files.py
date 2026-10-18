"""The run files and the pending-work file this build leaves when it owes a drifted manifest again.

Not collected: its name is not a test module's, and it runs only when named, with the variable
`WRITE_DRIFT_OWED_AGAIN_FILES` set to the directory to write into (`v1-e34-t26`). Then:

* `read_sync_run_files.py` reads what it wrote with each build, the run log, the details, the
  records still owed and the pending-work file, each with that build's own readers;
* `check_an_older_build_publishes_a_manifest_owed_again.py` hands the pending-work file to an older
  build's own `caselist pull --publish-pending`, which has to publish it.

The commands and what they printed are in the session report of `v1-e34-t26`.

Each scenario is pulls through the real run monitor, as the command runs them, in an installation
of its own, against moto. Written for each, under `<scenario>/`: the run log, the run details, the
file of records still owed when there is one, the pending-work file when there is one, and every
object the runs put under `reports/` in the bucket (`bucket.json`, key to body):

* `drift_owed_again`: week one's manifest drifts at the report stage, and is owed again.
* `drifted_again`: the same, and the next pull publishes it again and it drifts again: it is not
  owed a third time.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from debate_core.application.caselist_sync import PENDING_WORK_FILENAME
from debate_core.application.sync_runs import (
    PENDING_RECORDS_FILENAME,
    SYNC_RUN_DETAILS_FILENAME,
    SYNC_RUN_LOG_FILENAME,
)

from . import test_inbox_retention as inbox_retention
from .test_caselist_sync_owes_a_drifted_manifest_again import (
    FIRST_RUN,
    SECOND_RUN,
    Bucket,
    DriftBeforeTheComparison,
    a_bucket,
    a_pull,
)
from .test_inbox_retention import WEEK_1

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

REPORTS_PREFIX = "reports/"


def out() -> Path:
    where = os.environ.get("WRITE_DRIFT_OWED_AGAIN_FILES")
    if not where:
        pytest.skip("set WRITE_DRIFT_OWED_AGAIN_FILES to the directory to write into")
    return Path(where)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def bucket(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> Bucket:
    return a_bucket(tmp_path, s3_client, evidence_bucket)


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Callable[[datetime], None]:
    def set_clock(moment: datetime) -> None:
        monkeypatch.setattr(inbox_retention, "RUN_CLOCK", moment)

    set_clock(FIRST_RUN)
    return set_clock


def keep(written: Bucket, scenario: str) -> None:
    into = out() / scenario
    if into.exists():
        shutil.rmtree(into)
    into.mkdir(parents=True)
    data_dir = written.installation.data_dir
    for name in (
        SYNC_RUN_LOG_FILENAME,
        SYNC_RUN_DETAILS_FILENAME,
        PENDING_RECORDS_FILENAME,
        PENDING_WORK_FILENAME,
    ):
        if (data_dir / name).is_file():
            shutil.copyfile(data_dir / name, into / name)
    listed = written.s3_client.list_objects_v2(Bucket=written.name, Prefix=REPORTS_PREFIX)
    objects = {
        str(one.get("Key")): written.s3_client.get_object(Bucket=written.name, Key=str(one.get("Key")))[
            "Body"
        ]
        .read()
        .decode("utf-8")
        for one in listed.get("Contents", [])
    }
    (into / "bucket.json").write_text(json.dumps(objects, indent=2, sort_keys=True) + "\n", encoding="utf-8")


async def test_drift_owed_again(bucket: Bucket, clock: Callable[[datetime], None]) -> None:
    out()
    await a_pull(bucket, comparison=DriftBeforeTheComparison(bucket, rewrite=(WEEK_1,)))
    keep(bucket, "drift_owed_again")


async def test_drifted_again(bucket: Bucket, clock: Callable[[datetime], None]) -> None:
    out()
    await a_pull(bucket, comparison=DriftBeforeTheComparison(bucket, rewrite=(WEEK_1,)))
    clock(SECOND_RUN)
    await a_pull(bucket, comparison=DriftBeforeTheComparison(bucket, rewrite=(WEEK_1,)))
    keep(bucket, "drifted_again")
