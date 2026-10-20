"""A publish that ends pending still says what it found before the session expired (`v1-e34-t19`).

`v1-e34-t18` left this on record: when a snapshot ends incomplete on a code, a checksum mismatch
say, and the session then expires, the stage is `pending`, exit `0`, with no code. The snapshot is
owed, so the retry after the login reports it; until then nothing says that the login alone will
not finish the job. `v1-e34-t13`'s rule is that a pending stage carries no failure code for the
exit, and that rule stands. The code is recorded beside it, as an **earlier finding**: in the
summary, and never among the codes the exit status is decided from.

`v1-e34-t18`'s own shape and installation: two weeks imported, week one's publish incomplete, the
session expiring on week two, against moto. Every expected list is written by hand.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_synthetic_archives import build_snapshot_zips
from tests.fixtures.caselist.publish_expectations import expected_source_key

from debate_core.application.caselist_sync import SyncStage
from debate_core.integrations.s3 import S3EvidenceObjectStore

from .test_inbox_retention import CASELIST, WEEK_1, WEEK_2, ExpiredBucket, FakeSource, Installation
from .test_pending_work_owes_every_unpublished_snapshot import (
    NEW_IN_WEEK_2,
    ONLY_IN_WEEK_1,
    OWED_1,
    OWED_2,
    Session,
    answered_503,
    owed,
)
from .test_pull_stage_failure_codes import stage, stages_of

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio


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


@pytest.mark.parametrize(
    ("other_bytes_under_the_key", "finding"),
    [
        pytest.param(True, "CHECKSUM_MISMATCH", id="a mismatch, then an expiry"),
        pytest.param(False, "STORE_UNAVAILABLE", id="an upload the bucket answered 503, then an expiry"),
    ],
)
async def test_a_publish_left_pending_records_the_code_a_snapshot_ended_incomplete_on_as_an_earlier_finding(
    installation: Installation,
    s3_client: S3Client,
    evidence_bucket: str,
    other_bytes_under_the_key: bool,
    finding: str,
) -> None:
    """Week one ends incomplete on a code, and the session expires on week two. The stage is
    pending and carries no error code, exactly as before; the code is on it as an earlier finding;
    and nothing about the exit changes."""
    week_one_only = expected_source_key(ONLY_IN_WEEK_1)
    if other_bytes_under_the_key:
        s3_client.put_object(Bucket=evidence_bucket, Key=week_one_only, Body=b"other bytes")
    session = Session(
        installation.bucket,
        answers={} if other_bytes_under_the_key else {week_one_only: answered_503},
        expires_on=expected_source_key(NEW_IN_WEEK_2),
    )
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])

    summary = await installation.sync(source, publish_to=session).run([CASELIST])
    await session.settle()

    published = stage(summary, SyncStage.PUBLISH)
    assert published["outcome"] == "pending"
    assert published["error_codes"] == [], "v1-e34-t13: a pending stage carries no failure code"
    assert published["earlier_findings"] == [finding]
    assert summary.failure_codes == (), "an earlier finding decides nothing about the exit"
    assert summary.succeeded
    assert owed(installation) == [OWED_1, OWED_2]
    assert [one["earlier_findings"] for one in stages_of(summary) if one["stage"] != "publish"] == [[]] * 8


async def test_a_publish_pending_from_its_first_call_has_no_earlier_finding(
    installation: Installation,
) -> None:
    source = FakeSource(installation.archives, weeks=[WEEK_1])

    summary = await installation.sync(source, publish_to=ExpiredBucket()).run([CASELIST])

    published = stage(summary, SyncStage.PUBLISH)
    assert published["outcome"] == "pending"
    assert published["earlier_findings"] == []


async def test_a_failed_publish_keeps_its_codes_as_error_codes_and_none_as_earlier_findings(
    installation: Installation, s3_client: S3Client, evidence_bucket: str
) -> None:
    """The mismatch with no expiry after it: a failed stage, whose code is an error code and
    decides the exit. An earlier finding is only ever what a pending stage found first."""
    s3_client.put_object(Bucket=evidence_bucket, Key=expected_source_key(ONLY_IN_WEEK_1), Body=b"other bytes")
    source = FakeSource(installation.archives, weeks=[WEEK_1])

    summary = await installation.sync(source).run([CASELIST])

    published = stage(summary, SyncStage.PUBLISH)
    assert published["outcome"] == "failed"
    assert published["error_codes"] == ["CHECKSUM_MISMATCH"]
    assert published["earlier_findings"] == []
    assert summary.failure_codes == ("CHECKSUM_MISMATCH",)
