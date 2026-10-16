"""The report stage keeps the drift it found before a session expired, and says which kind it was.

`v1-e34-t23`, items 1 and 11.

* **Item 1.** The report stage compares, snapshot by snapshot, what this run published. When the
  session expired part-way it was recorded as pending and nothing more, and what it had already
  found out of sync was lost: the retry after the login, `--publish-pending`, compares only what it
  publishes itself, and the snapshot that drifted was published already. The publish stage had the
  same defect until `v1-e34-t19`'s ac8. The stage now keeps it as an earlier finding, as the publish
  stage does, and the login notification says so.
* **Item 11.** A snapshot not in sync was recorded as `CASELIST_DRIFT` and nothing else.
  `v1-e30-t12` told two kinds of checksum mismatch apart: a source, filed under the digest of its
  bytes, which needs a person; and the snapshot's manifest, which this machine rewrites in place
  and `caselist publish` uploads again. The stage's finding now carries the kind, in the summary
  and in the run's details, and a run whose only drift is a manifest mismatch is announced with
  the publish command, as something publishing again clears, and not as needing a person.

The comparison is the real one, against moto, with one thing scripted on top of it: a mismatch on
a snapshot, or the session expiring at a given comparison. Every expectation is written by hand.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from tests.fixtures.caselist.build_synthetic_archives import build_snapshot_zips
from tests.fixtures.caselist.publish_expectations import expected_source_key

from debate_core.application.caselist.status_service import (
    CaselistStatusReport,
    CaselistStatusService,
    SnapshotStatus,
)
from debate_core.application.caselist_sync import SyncStage
from debate_core.application.errors import StoreCredentialsExpired
from debate_core.integrations.s3 import S3EvidenceObjectStore
from debate_core.testing.fakes import empty_suppression_list

from .test_inbox_retention import CASELIST, WEEK_1, WEEK_2, FakeSource, Installation
from .test_pending_work_owes_every_unpublished_snapshot import ONLY_IN_WEEK_1
from .test_pull_stage_failure_codes import AWS_LOGIN, Watched, pull, stage

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

WHERE = "Run 20260916T060000Z (dev)"
LOGIN_TITLE = "caselist publish waiting for an AWS login"
PUBLISH_AGAIN_TITLE = "caselist pull: publish a manifest again"
PUBLISH_TESTCL26 = "debate-research caselist publish --caselist testcl26"
PUBLISH_AGAIN = (
    "Publishing again should clear it: this machine rewrote the manifest after it was published, "
    "and the publish uploads this machine's copy. Nothing here needs a person."
)


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


class ScriptedComparison(CaselistStatusService):
    """The real comparison, and then what the test says differs, or a session that expires.

    Args:
        manifest_differs: Snapshots whose manifest the bucket is to hold with other bytes.
        source_differs: Snapshots one of whose sources the bucket is to hold with other bytes.
        expires_at: The comparison, counting from one, at which the session has expired, and every
            one after it. The report stage compares each published snapshot in turn; retention
            asks again after it.
    """

    def __init__(
        self,
        installation: Installation,
        *,
        manifest_differs: tuple[date, ...] = (),
        source_differs: tuple[date, ...] = (),
        expires_at: int | None = None,
    ) -> None:
        super().__init__(
            local=installation.local, remote=installation.bucket, suppression=empty_suppression_list()
        )
        self._manifest_differs = {one.isoformat() for one in manifest_differs}
        self._source_differs = {one.isoformat() for one in source_differs}
        self._expires_at = expires_at
        self.comparisons = 0

    async def status(
        self, caselist: str | None = None, snapshot: str | None = None, **asked: Any
    ) -> CaselistStatusReport:
        self.comparisons += 1
        if self._expires_at is not None and self.comparisons >= self._expires_at:
            raise StoreCredentialsExpired(hint=AWS_LOGIN)
        report = await super().status(caselist, snapshot, **asked)
        return replace(report, snapshots=tuple(self._scripted(one) for one in report.snapshots))

    def _scripted(self, one: SnapshotStatus) -> SnapshotStatus:
        if one.snapshot in self._manifest_differs:
            return replace(one, checksum_mismatches=(one.manifest_key,))
        if one.snapshot in self._source_differs:
            return replace(one, checksum_mismatches=(expected_source_key(ONLY_IN_WEEK_1),))
        return one


async def two_weeks_compared(installation: Installation, comparison: ScriptedComparison) -> Watched:
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    return await pull(installation, installation.sync(source, status=comparison))


def report_details(watched: Watched) -> dict[str, object]:
    details = watched.pulled.details
    assert details is not None
    found = details.stage(str(SyncStage.REPORT))
    assert found is not None, details
    return found.model_dump(mode="json")


# ------------------------------------------------------------------------------------------------
# Item 1: what the report stage found before the session expired
# ------------------------------------------------------------------------------------------------


async def test_a_source_mismatch_found_before_the_session_expired_is_kept_and_needs_a_person(
    installation: Installation,
) -> None:
    """Week one's comparison finds a source the bucket holds with other bytes; the session expires
    at week two's. The stage is pending, as it always was, and no exit code reads it. What it found
    is kept as an earlier finding with its kind, and the login banner says a login will not fix it."""
    watched = await two_weeks_compared(
        installation, ScriptedComparison(installation, source_differs=(WEEK_1,), expires_at=2)
    )

    report = stage(watched.summary, SyncStage.REPORT)
    assert report["outcome"] == "pending"
    assert report["error_codes"] == []
    assert report["earlier_findings"] == ["CASELIST_DRIFT"]
    assert report["drift"] == [{"caselist": CASELIST, "snapshot": "2026-09-01", "kinds": ["source"]}]
    assert "not in sync before the session expired: testcl26 2026-09-01 (source mismatch)" in str(
        report["reason"]
    )
    assert watched.summary.failure_codes == ()
    assert report_details(watched) == {
        "stage": "report",
        "error_codes": [],
        "hint": None,
        "earlier_findings": ["CASELIST_DRIFT"],
        "drift": [{"caselist": CASELIST, "snapshot": "2026-09-01", "kinds": ["source"]}],
    }
    [login] = watched.notifier.sent
    assert login.title == LOGIN_TITLE
    assert (
        "A person should look as well: before the session expired a snapshot ended incomplete on "
        "CASELIST_DRIFT, which the login will not fix." in login.message
    )


async def test_a_manifest_mismatch_found_before_the_session_expired_is_kept_and_needs_only_a_publish(
    installation: Installation,
) -> None:
    watched = await two_weeks_compared(
        installation, ScriptedComparison(installation, manifest_differs=(WEEK_1,), expires_at=2)
    )

    report = stage(watched.summary, SyncStage.REPORT)
    assert report["outcome"] == "pending"
    assert report["earlier_findings"] == ["CASELIST_DRIFT"]
    assert report["drift"] == [{"caselist": CASELIST, "snapshot": "2026-09-01", "kinds": ["manifest"]}]
    [login] = watched.notifier.sent
    assert login.title == LOGIN_TITLE
    assert "A person should look" not in login.message
    assert login.message.endswith(
        " Before the session expired, the bucket's manifest of testcl26 2026-09-01 was found to differ "
        f"from this machine's; after the login, publishing it again clears it: {PUBLISH_TESTCL26}"
    )


async def test_an_expiry_at_the_first_comparison_found_nothing_and_says_nothing_more(
    installation: Installation,
) -> None:
    watched = await two_weeks_compared(installation, ScriptedComparison(installation, expires_at=1))

    report = stage(watched.summary, SyncStage.REPORT)
    assert report["outcome"] == "pending"
    assert report["earlier_findings"] == []
    assert report["drift"] == []
    [login] = watched.notifier.sent
    assert "A person should look" not in login.message
    assert "publishing it again" not in login.message


# ------------------------------------------------------------------------------------------------
# Item 11: the kind, and a manifest mismatch announced with the publish command
# ------------------------------------------------------------------------------------------------


async def test_a_manifest_mismatch_alone_is_announced_with_the_publish_command_and_not_as_a_person(
    installation: Installation,
) -> None:
    watched = await two_weeks_compared(
        installation, ScriptedComparison(installation, manifest_differs=(WEEK_1,))
    )

    summary = watched.summary
    report = stage(summary, SyncStage.REPORT)
    assert report["outcome"] == "failed"
    assert report["error_codes"] == ["CASELIST_DRIFT"]
    assert report["drift"] == [{"caselist": CASELIST, "snapshot": "2026-09-01", "kinds": ["manifest"]}]
    assert report["reason"] == "1 snapshot(s) confirmed; not in sync: testcl26 2026-09-01 (manifest mismatch)"
    assert summary.succeeded and summary.failure_codes == (), "the exit is untouched: 0"
    assert report_details(watched)["drift"] == [
        {"caselist": CASELIST, "snapshot": "2026-09-01", "kinds": ["manifest"]}
    ]
    [notification] = watched.notifier.sent
    assert notification.title == PUBLISH_AGAIN_TITLE
    assert notification.message == (
        f"{WHERE}: the report stage found the bucket's manifest of testcl26 2026-09-01 differs from "
        f"this machine's. {PUBLISH_AGAIN}"
    )
    assert notification.fix_command == PUBLISH_TESTCL26
    assert "person should look" not in notification.text


async def test_a_source_mismatch_is_still_a_failed_stage_with_its_kind(installation: Installation) -> None:
    watched = await two_weeks_compared(
        installation, ScriptedComparison(installation, source_differs=(WEEK_1,))
    )

    report = stage(watched.summary, SyncStage.REPORT)
    assert report["outcome"] == "failed"
    assert report["drift"] == [{"caselist": CASELIST, "snapshot": "2026-09-01", "kinds": ["source"]}]
    [notification] = watched.notifier.sent
    assert notification.title == "caselist pull finished with a failed stage"
    assert notification.message == (
        f"{WHERE}: the report stage failed on CASELIST_DRIFT. What was captured is kept."
    )


async def test_a_manifest_mismatch_beside_a_source_mismatch_is_not_announced_as_a_publish_alone(
    installation: Installation,
) -> None:
    watched = await two_weeks_compared(
        installation,
        ScriptedComparison(installation, manifest_differs=(WEEK_1,), source_differs=(WEEK_2,)),
    )

    report = stage(watched.summary, SyncStage.REPORT)
    assert report["drift"] == [
        {"caselist": CASELIST, "snapshot": "2026-09-01", "kinds": ["manifest"]},
        {"caselist": CASELIST, "snapshot": "2026-09-08", "kinds": ["source"]},
    ]
    [notification] = watched.notifier.sent
    assert notification.title == "caselist pull finished with a failed stage"
