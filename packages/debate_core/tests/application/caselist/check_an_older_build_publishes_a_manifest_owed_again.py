"""An older build's own `caselist pull --publish-pending`, handed the pending-work file this build wrote.

Not collected: its name is not a test module's, and it is only ever run by its path, with an older
build's source first on `PYTHONPATH` and `CHECK_AN_OLDER_BUILD_PUBLISHES` set to the pending-work
file `write_drift_owed_again_files.py` wrote for `drift_owed_again` (`v1-e34-t26`). It writes
nothing outside pytest's temporary directory.

The weekly agent runs the build it was installed with until it is reinstalled. A snapshot this build
owes again for a drifted manifest is written into the pending-work file the agent's build reads
next, so that build has to read the entry and publish it, not merely not refuse it. This does what
the agent does: with the source it is run against, it pulls weeks one and two and publishes them;
the bucket's copy of week one's manifest is then changed under it, as a drift is; this build's
pending-work file is put where that build keeps its own; and that build's `--publish-pending` runs.
It imports nothing this task added, so that every line of it runs on the older source.
"""

from __future__ import annotations

import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_synthetic_archives import build_snapshot_zips

import debate_core
from debate_core.application.caselist.manifest import manifest_key
from debate_core.application.caselist_sync import PENDING_WORK_FILENAME, PendingWork, SyncStage
from debate_core.integrations.s3 import S3EvidenceObjectStore

from . import test_inbox_retention as inbox_retention
from .test_inbox_retention import CASELIST, WEEK_1, WEEK_2, FakeSource, Installation
from .test_pull_stage_failure_codes import pull, stage

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

SECOND_RUN = datetime(2026, 9, 23, 6, 0, tzinfo=UTC)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_this_builds_entry_is_published_by_this_source(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    written = os.environ.get("CHECK_AN_OLDER_BUILD_PUBLISHES")
    if not written:
        pytest.skip("set CHECK_AN_OLDER_BUILD_PUBLISHES to the pending-work file this build wrote")
    source_root = Path(debate_core.__file__).resolve().parents[3]
    print(f"\nreader: the debate_core source at {source_root.name}")
    installation = Installation(
        data_dir=tmp_path / "evidence",
        bucket=S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client),
        archives=build_snapshot_zips(tmp_path / "published"),
    )
    monkeypatch.setattr(inbox_retention, "RUN_CLOCK", datetime(2026, 9, 16, 6, 0, tzinfo=UTC))
    first = await pull(
        installation, installation.sync(FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2]))
    )
    print(f"its own pull: publish {stage(first.summary, SyncStage.PUBLISH)['outcome']}")

    key = manifest_key(CASELIST, WEEK_1)
    s3_client.put_object(Bucket=evidence_bucket, Key=key, Body=b'{"rewritten": "elsewhere"}\n')
    path_for = installation.local.object_path_for
    assert path_for is not None
    local = path_for(key).read_bytes()
    drifted = _in_bucket(s3_client, evidence_bucket, key) == local
    print(f"the bucket's week one manifest, drifted: same as this machine's: {drifted}")

    pending = installation.data_dir / PENDING_WORK_FILENAME
    shutil.copyfile(written, pending)
    print(f"placed: {pending.name}, {pending.stat().st_size} bytes")
    print(f"read by this source: {[(one.caselist, one.snapshot) for one in PendingWork(pending).read()]}")

    monkeypatch.setattr(inbox_retention, "RUN_CLOCK", SECOND_RUN)
    drained = await pull(
        installation, installation.sync(FakeSource(installation.archives, weeks=[])), publish_pending=True
    )
    published = stage(drained.summary, SyncStage.PUBLISH)
    reported = stage(drained.summary, SyncStage.REPORT)
    print(f"--publish-pending: publish {published['outcome']} ({published['reason']})")
    print(f"--publish-pending: report {reported['outcome']} ({reported['reason']})")
    followed = _in_bucket(s3_client, evidence_bucket, key) == local
    print(f"the bucket's week one manifest now the same as this machine's: {followed}")
    print(f"pending-work file left: {pending.exists()}")
    assert published["outcome"] == "completed"
    assert _in_bucket(s3_client, evidence_bucket, key) == local
    assert not pending.exists()


def _in_bucket(s3_client: S3Client, bucket: str, key: str) -> bytes:
    return s3_client.get_object(Bucket=bucket, Key=key)["Body"].read()
