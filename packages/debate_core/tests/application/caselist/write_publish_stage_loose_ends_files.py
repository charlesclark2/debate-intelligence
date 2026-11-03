"""The run files this build leaves after the publish-stage loose ends of `v1-e34-t28`.

Not collected: its name is not a test module's, and it runs only when named, with the variable
`WRITE_PUBLISH_STAGE_LOOSE_ENDS_FILES` set to the directory to write into. Then
`read_sync_run_files.py` reads what it wrote with each build, the run log, the details, the records
still owed and the pending-work file, each with that build's own readers. The commands and what
they printed are in the session report of `v1-e34-t28`.

Each scenario is pulls through the real run monitor, as the command runs them, in an installation
of its own, against moto. Written for each, under `<scenario>/`: the run log, the run details, the
file of records still owed when there is one, the pending-work file when there is one, and every
object the runs put under `reports/` in the bucket (`bucket.json`, key to body):

* `report_cut_short`: two weeks published; the session expires at the report stage's first
  comparison. The record is `publish_pending`, and the details name both weeks as not compared.
* `report_cut_short_then_drained`: the same, cut short at the second comparison, and then
  `--publish-pending`, which compares week two.
* `publish_cut_short`: the session expires on week two's manifest. Week one is owed a comparison
  in the details, and week two a publish in the pending-work file.
* `manifest_alone_republished`: week one's manifest drifts at the report stage and is owed again;
  the next pull uploads that manifest and nothing else, and counts it.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from debate_core.application.caselist_sync import PENDING_WORK_FILENAME
from debate_core.application.sync_runs import (
    PENDING_RECORDS_FILENAME,
    SYNC_RUN_DETAILS_FILENAME,
    SYNC_RUN_LOG_FILENAME,
)

from . import test_inbox_retention as inbox_retention
from .test_caselist_sync_owes_a_drifted_manifest_again import Bucket, DriftBeforeTheComparison, a_bucket
from .test_caselist_sync_publish_stage_loose_ends import (
    FIRST_RUN,
    SECOND_RUN,
    RecordingComparison,
    publish_pending,
    two_weeks_with_the_check_cut_short,
)
from .test_inbox_retention import WEEK_1, WEEK_2, FakeSource
from .test_pending_work_owes_every_unpublished_snapshot import MANIFEST, Session
from .test_pull_stage_failure_codes import pull

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

REPORTS_PREFIX = "reports/"


def out() -> Path:
    where = os.environ.get("WRITE_PUBLISH_STAGE_LOOSE_ENDS_FILES")
    if not where:
        pytest.skip("set WRITE_PUBLISH_STAGE_LOOSE_ENDS_FILES to the directory to write into")
    return Path(where)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def bucket(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> Bucket:
    return a_bucket(tmp_path, s3_client, evidence_bucket)


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Any:
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


async def test_report_cut_short(bucket: Bucket, clock: Any) -> None:
    out()
    await two_weeks_with_the_check_cut_short(bucket.installation, expires_at=1)
    keep(bucket, "report_cut_short")


async def test_report_cut_short_then_drained(bucket: Bucket, clock: Any) -> None:
    out()
    await two_weeks_with_the_check_cut_short(bucket.installation, expires_at=2)
    clock(SECOND_RUN)
    await publish_pending(bucket.installation, RecordingComparison(bucket.installation))
    keep(bucket, "report_cut_short_then_drained")


async def test_publish_cut_short(bucket: Bucket, clock: Any) -> None:
    out()
    session = Session(bucket.installation.bucket, expires_on=MANIFEST[WEEK_2])
    source = FakeSource(bucket.installation.archives, weeks=[WEEK_1, WEEK_2])
    await pull(bucket.installation, bucket.installation.sync(source, publish_to=session))
    await session.settle()
    keep(bucket, "publish_cut_short")


async def test_manifest_alone_republished(bucket: Bucket, clock: Any) -> None:
    out()
    source = FakeSource(bucket.installation.archives, weeks=[WEEK_1, WEEK_2])
    drifting = DriftBeforeTheComparison(bucket, rewrite=(WEEK_1,))
    await pull(bucket.installation, bucket.installation.sync(source, status=drifting))
    clock(SECOND_RUN)
    await pull(bucket.installation, bucket.installation.sync(source))
    keep(bucket, "manifest_alone_republished")
