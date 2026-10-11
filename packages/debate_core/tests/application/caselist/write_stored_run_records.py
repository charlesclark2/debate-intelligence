"""Writes `stored_run_records/written_by_the_start_commit/`: what a build before `v1-e34-t19` wrote.

Not collected: its name is not a test module's, and it is only ever run by its path, against the
source of the commit this task started from (`ccc5153`), so that what it stores was written by that
build's code and not by this one's. `stored_run_records/README.md` gives the command.

For each scenario in `run_record_scenarios.py` it keeps two things, byte for byte: the run log the
build left on this machine, and every object it put under the bucket prefix records live under.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_synthetic_archives import build_snapshot_zips

from debate_core.integrations.s3 import S3EvidenceObjectStore

from . import test_inbox_retention as inbox_retention
from .run_record_scenarios import SCENARIOS, World, stored_bucket_text
from .test_inbox_retention import Installation

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

STORED = Path(__file__).parent / "stored_run_records" / "written_by_the_start_commit"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.parametrize("name", sorted(SCENARIOS))
async def test_write_what_this_source_writes(
    name: str, tmp_path: Path, s3_client: S3Client, evidence_bucket: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert os.environ.get("WRITE_STORED_RUN_RECORDS") == "from-the-start-commit", (
        "this rewrites the stored records; see stored_run_records/README.md"
    )

    def set_clock(moment: datetime) -> None:
        monkeypatch.setattr(inbox_retention, "RUN_CLOCK", moment)

    world = World(
        installation=Installation(
            data_dir=tmp_path / "evidence",
            bucket=S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client),
            archives=build_snapshot_zips(tmp_path / "published"),
        ),
        s3_client=s3_client,
        bucket_name=evidence_bucket,
        scratch=tmp_path,
        set_clock=set_clock,
    )

    await SCENARIOS[name](world)

    STORED.mkdir(parents=True, exist_ok=True)
    (STORED / f"{name}.run-log.jsonl").write_bytes(world.run_log())
    (STORED / f"{name}.bucket.json").write_text(
        stored_bucket_text(world.records_in_the_bucket()), encoding="utf-8"
    )
