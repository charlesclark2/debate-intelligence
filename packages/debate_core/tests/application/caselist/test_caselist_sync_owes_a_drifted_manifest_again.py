"""A snapshot whose bucket manifest drifted is owed again, once (`v1-e34-t26`, item 2).

The report stage compares what the run published with the bucket. Until this task a snapshot it found
there with a manifest other than this machine's was published, so nothing owed it: neither the next
pull nor `--publish-pending` touched it, and the notification sent the operator to
`caselist publish`. The PM's ruling of 2026-10-16 amends `v1-e34-t18`'s rule for what is owed: the
local manifest is the record and the bucket's copy follows it, so the report stage puts such a
snapshot back into the pending-work file and the next run publishes it again.

Three conditions, each a test here:

* **It never loops silently.** A snapshot owed again for drift whose republish the bucket confirmed,
  and that the report stage then finds drifting again, is not owed a third time. The run says a
  person should look, naming it by caselist and date. "Owed again for drift" is read from the run
  log and the details as they are: a run whose report stage found the snapshot's manifest, and
  nothing else, differing, and whose record lists it as owed; and every run since lists it as owed.
* **Drift only.** A manifest mismatch and nothing else. A manifest the bucket lacks, a source with
  other bytes, or either beside a manifest mismatch, is a failed report stage for a person, as
  before, and owes nothing.
* **The exit is untouched** (`v1-e34-t13`): the report stage is not one the exit is decided from.

The comparison is the real one, against moto. What drifts is real too: just before the report stage
compares a snapshot, the test writes other bytes over that snapshot's manifest in the bucket, which
is what a rewritten manifest looks like from there. Every expectation is written by hand.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from tests.fixtures.caselist.build_synthetic_archives import build_snapshot_zips
from tests.fixtures.caselist.publish_expectations import expected_source_key

from debate_core.application.caselist.manifest import manifest_key
from debate_core.application.caselist.status_service import CaselistStatusReport, CaselistStatusService
from debate_core.application.caselist_sync import PENDING_WORK_FILENAME, SyncStage
from debate_core.application.errors import StoreCredentialsExpired
from debate_core.application.sync_runs import (
    DriftFinding,
    StageDetails,
    StageEntry,
    SyncRunDetails,
    SyncRunOutcome,
    SyncRunRecord,
    snapshots_owed_again_for_drift,
)
from debate_core.integrations.s3 import S3EvidenceObjectStore
from debate_core.testing.fakes import empty_suppression_list

from . import test_inbox_retention as inbox_retention
from .test_inbox_retention import CASELIST, WEEK_1, WEEK_2, ExpiredBucket, FakeSource, Installation
from .test_pending_work_owes_every_unpublished_snapshot import NEW_IN_WEEK_2, ONLY_IN_WEEK_1
from .test_pull_stage_failure_codes import Watched, assert_names_nothing_of_this_machine, owed, pull, stage

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

FIRST_RUN = datetime(2026, 9, 16, 6, 0, tzinfo=UTC)
SECOND_RUN = datetime(2026, 9, 23, 6, 0, tzinfo=UTC)
THIRD_RUN = datetime(2026, 9, 30, 6, 0, tzinfo=UTC)

WEEK_ONE = "testcl26 2026-09-01"
WEEK_TWO = "testcl26 2026-09-08"
OTHER_BYTES = b'{"rewritten": "by something that is not this machine"}\n'

OWED_AGAIN_TITLE = "caselist pull: publish a manifest again"
OWED_AGAIN = (
    "The next scheduled run publishes it again: this machine rewrote the manifest after it was "
    "published, and the publish uploads this machine's copy. Nothing here needs a person."
)
DRIFTED_AGAIN_TITLE = "caselist pull: a manifest drifted again"
PUBLISH_PENDING = "debate-research caselist pull --publish-pending"
STATUS_TESTCL26 = "debate-research caselist status --caselist testcl26"
A_SOURCE_ONLY_IN = {WEEK_1: ONLY_IN_WEEK_1, WEEK_2: NEW_IN_WEEK_2}
"""A source each week holds that the other does not, by its name among the invented archives."""


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@dataclass
class Bucket:
    installation: Installation
    s3_client: S3Client
    name: str

    def manifest(self, week: date) -> bytes:
        found = self.s3_client.get_object(Bucket=self.name, Key=manifest_key(CASELIST, week))
        return found["Body"].read()

    def local_manifest(self, week: date) -> bytes:
        path_for = self.installation.local.object_path_for
        assert path_for is not None
        return path_for(manifest_key(CASELIST, week)).read_bytes()

    def rewrite(self, week: date, body: bytes = OTHER_BYTES) -> None:
        self.s3_client.put_object(Bucket=self.name, Key=manifest_key(CASELIST, week), Body=body)

    def delete(self, week: date) -> None:
        self.s3_client.delete_object(Bucket=self.name, Key=manifest_key(CASELIST, week))


@pytest.fixture
def bucket(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> Bucket:
    installation = Installation(
        data_dir=tmp_path / "evidence",
        bucket=S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client),
        archives=build_snapshot_zips(tmp_path / "published"),
    )
    return Bucket(installation=installation, s3_client=s3_client, name=evidence_bucket)


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Any:
    def set_clock(moment: datetime) -> None:
        monkeypatch.setattr(inbox_retention, "RUN_CLOCK", moment)

    set_clock(FIRST_RUN)
    return set_clock


class DriftBeforeTheComparison(CaselistStatusService):
    """The real comparison, after something has changed the bucket under a snapshot the run published.

    Args:
        rewrite: Weeks whose manifest the bucket is to hold with other bytes when they are compared.
        delete: Weeks whose manifest the bucket is to lose when they are compared.
        rewrite_source_of: Weeks one of whose sources the bucket is to hold with other bytes.
    """

    def __init__(
        self,
        bucket: Bucket,
        *,
        rewrite: tuple[date, ...] = (),
        delete: tuple[date, ...] = (),
        rewrite_source_of: tuple[date, ...] = (),
    ) -> None:
        super().__init__(
            local=bucket.installation.local,
            remote=bucket.installation.bucket,
            suppression=empty_suppression_list(),
        )
        self.bucket = bucket
        self._rewrite = rewrite
        self._delete = delete
        self._rewrite_source_of = rewrite_source_of
        self.compared: list[str] = []

    async def status(
        self, caselist: str | None = None, snapshot: str | None = None, **asked: Any
    ) -> CaselistStatusReport:
        if snapshot is not None:
            self.compared.append(snapshot)
            week = date.fromisoformat(snapshot)
            if week in self._rewrite:
                self.bucket.rewrite(week)
            if week in self._delete:
                self.bucket.delete(week)
            if week in self._rewrite_source_of:
                key = expected_source_key(A_SOURCE_ONLY_IN[week])
                self.bucket.s3_client.put_object(Bucket=self.bucket.name, Key=key, Body=b"other bytes")
        return await super().status(caselist, snapshot, **asked)


async def a_pull(bucket: Bucket, *, comparison: CaselistStatusService | None = None, **sync: Any) -> Watched:
    """A weekly pull of weeks one and two: the first imports and publishes both, later ones nothing new."""
    source = FakeSource(bucket.installation.archives, weeks=[WEEK_1, WEEK_2])
    return await pull(bucket.installation, bucket.installation.sync(source, status=comparison, **sync))


def report(watched: Watched) -> dict[str, object]:
    return stage(watched.summary, SyncStage.REPORT)


def publish(watched: Watched) -> dict[str, object]:
    return stage(watched.summary, SyncStage.PUBLISH)


# ------------------------------------------------------------------------------------------------
# The drift is owed again, and the next run publishes it
# ------------------------------------------------------------------------------------------------


async def test_a_manifest_that_drifted_is_owed_again_and_the_next_run_publishes_it(
    bucket: Bucket, clock: Any
) -> None:
    first = await a_pull(bucket, comparison=DriftBeforeTheComparison(bucket, rewrite=(WEEK_1,)))

    assert report(first)["outcome"] == "failed"
    assert report(first)["drift"] == [{"caselist": CASELIST, "snapshot": "2026-09-01", "kinds": ["manifest"]}]
    assert report(first)["reason"] == (
        "1 snapshot(s) confirmed; not in sync: testcl26 2026-09-01 (manifest mismatch); "
        "owed again, for the next run to publish: testcl26 2026-09-01"
    )
    assert owed(bucket.installation) == [WEEK_ONE]
    assert first.summary.as_json()["pending_publish"] == [WEEK_ONE]
    assert first.pulled.record is not None
    assert first.pulled.record.pending_publish == (WEEK_ONE,)
    assert first.summary.succeeded and first.summary.failure_codes == (), "the exit is untouched: 0"
    assert bucket.manifest(WEEK_1) == OTHER_BYTES
    [notification] = first.notifier.sent
    assert notification.title == OWED_AGAIN_TITLE
    assert notification.message == (
        "Run 20260916T060000Z (dev): the report stage found the bucket's manifest of testcl26 "
        f"2026-09-01 differs from this machine's. {OWED_AGAIN}"
    )
    assert notification.fix_command == PUBLISH_PENDING
    assert_names_nothing_of_this_machine(first.summary, bucket.installation)

    clock(SECOND_RUN)
    second = await a_pull(bucket)

    assert publish(second)["outcome"] == "completed"
    # The count is of sources; the manifest it uploads again is not one of them (Follow-up work).
    assert publish(second)["reason"] == "0 object(s) uploaded across 1 snapshot(s)"
    assert report(second)["outcome"] == "completed"
    assert report(second)["reason"] == "1 snapshot(s) confirmed in the bucket"
    assert bucket.manifest(WEEK_1) == bucket.local_manifest(WEEK_1), "the bucket's copy follows"
    assert owed(bucket.installation) == []
    assert not (bucket.installation.data_dir / PENDING_WORK_FILENAME).exists()
    assert second.notifier.sent == []


async def test_publish_pending_publishes_a_manifest_owed_again(bucket: Bucket, clock: Any) -> None:
    """`--publish-pending` reads the file as the next pull does, and publishes it the same way."""
    await a_pull(bucket, comparison=DriftBeforeTheComparison(bucket, rewrite=(WEEK_1,)))

    clock(SECOND_RUN)
    source = FakeSource(bucket.installation.archives, weeks=[])
    drained = await pull(bucket.installation, bucket.installation.sync(source), publish_pending=True)

    assert publish(drained)["outcome"] == "completed"
    assert report(drained)["outcome"] == "completed"
    assert bucket.manifest(WEEK_1) == bucket.local_manifest(WEEK_1)
    assert owed(bucket.installation) == []


async def test_a_drift_found_before_the_session_expired_is_owed_again(bucket: Bucket, clock: Any) -> None:
    """Week one drifts; the session expires at week two's comparison. What was found is found: week
    one is owed again, and the login banner says the publish after the login publishes it."""

    class ThenExpired(DriftBeforeTheComparison):
        async def status(self, caselist: str | None = None, snapshot: str | None = None, **asked: Any):  # type: ignore[override]
            if snapshot == WEEK_2.isoformat():
                raise StoreCredentialsExpired(hint=ExpiredBucket.hint)
            return await super().status(caselist, snapshot, **asked)

    watched = await a_pull(bucket, comparison=ThenExpired(bucket, rewrite=(WEEK_1,)))

    assert report(watched)["outcome"] == "pending"
    assert owed(bucket.installation) == [WEEK_ONE]
    assert watched.pulled.record is not None
    assert watched.pulled.record.pending_publish == (WEEK_ONE,)
    [login] = watched.notifier.sent
    assert login.message.startswith(
        "Run 20260916T060000Z (dev) kept everything it fetched; 1 snapshot(s) and the run record wait "
        "to be published."
    )
    assert (
        " Before the session expired, the bucket's manifest of testcl26 2026-09-01 was found to differ "
        "from this machine's; it is owed again, and the publish after the login uploads this machine's "
        "copy." in login.message
    )
    assert "A person should look" not in login.message


# ------------------------------------------------------------------------------------------------
# It never loops silently
# ------------------------------------------------------------------------------------------------


async def test_a_manifest_that_drifts_again_after_its_republish_is_not_owed_a_third_time(
    bucket: Bucket, clock: Any
) -> None:
    await a_pull(bucket, comparison=DriftBeforeTheComparison(bucket, rewrite=(WEEK_1,)))
    assert owed(bucket.installation) == [WEEK_ONE]

    clock(SECOND_RUN)
    again = DriftBeforeTheComparison(bucket, rewrite=(WEEK_1,))
    second = await a_pull(bucket, comparison=again)

    assert publish(second)["outcome"] == "completed", "the republish was confirmed"
    assert again.compared[0] == "2026-09-01", "the report stage compared it after the republish"
    assert report(second)["outcome"] == "failed"
    assert report(second)["reason"] == (
        "0 snapshot(s) confirmed; not in sync: testcl26 2026-09-01 (manifest mismatch); "
        "drifted again after it was owed again and published, so not owed a third time; "
        "a person should look: testcl26 2026-09-01"
    )
    assert owed(bucket.installation) == []
    assert second.pulled.record is not None
    assert second.pulled.record.pending_publish == ()
    assert second.summary.succeeded and second.summary.failure_codes == (), "the exit is untouched: 0"
    [notification] = second.notifier.sent
    assert notification.title == DRIFTED_AGAIN_TITLE
    assert notification.message == (
        "Run 20260923T060000Z (dev): the bucket's manifest of testcl26 2026-09-01 differs from this "
        "machine's again, after a run published it again and the bucket confirmed it. Publishing it a "
        "third time would not clear it, so it is not owed again: a person should look."
    )
    assert notification.fix_command == STATUS_TESTCL26

    clock(THIRD_RUN)
    third = await a_pull(bucket)

    assert publish(third)["outcome"] == "skipped", "nothing owes it, so nothing publishes it"
    assert third.notifier.sent == []


async def test_the_guard_looks_past_a_run_that_could_not_publish(bucket: Bucket, clock: Any) -> None:
    """Owed again at the first run; the second's session had expired, so it is still owed; the third
    publishes it and it drifts again. That is the drift again, not a first one."""
    await a_pull(bucket, comparison=DriftBeforeTheComparison(bucket, rewrite=(WEEK_1,)))

    clock(SECOND_RUN)
    waiting = await a_pull(bucket, publish_to=ExpiredBucket(), compare_with=ExpiredBucket())
    assert publish(waiting)["outcome"] == "pending"
    assert owed(bucket.installation) == [WEEK_ONE]

    clock(THIRD_RUN)
    third = await a_pull(bucket, comparison=DriftBeforeTheComparison(bucket, rewrite=(WEEK_1,)))

    assert "not owed a third time" in str(report(third)["reason"])
    assert owed(bucket.installation) == []


async def test_a_first_drift_of_a_snapshot_owed_for_another_reason_is_owed_again(
    bucket: Bucket, clock: Any
) -> None:
    """Owed because the session had expired, not for drift: its first drift is owed again. Having been
    owed is not what the guard reads."""
    waiting = await a_pull(bucket, publish_to=ExpiredBucket(), compare_with=ExpiredBucket())
    assert owed(bucket.installation) == [WEEK_ONE, WEEK_TWO]
    assert publish(waiting)["outcome"] == "pending"

    clock(SECOND_RUN)
    second = await a_pull(bucket, comparison=DriftBeforeTheComparison(bucket, rewrite=(WEEK_1,)))

    assert publish(second)["outcome"] == "completed"
    assert "owed again, for the next run to publish: testcl26 2026-09-01" in str(report(second)["reason"])
    assert owed(bucket.installation) == [WEEK_ONE]


async def test_a_snapshot_confirmed_in_sync_between_two_drifts_starts_again(
    bucket: Bucket, clock: Any
) -> None:
    """Owed again, then published and confirmed in sync, then drifting at a later publish: a first drift
    again, because a run in between did not owe it."""
    await a_pull(bucket, comparison=DriftBeforeTheComparison(bucket, rewrite=(WEEK_1,)))
    clock(SECOND_RUN)
    await a_pull(bucket)
    assert owed(bucket.installation) == []

    # The next publish of week one is a person's `caselist pull --publish-pending` after week one
    # was written into the file by hand; it drifts at its comparison.
    (bucket.installation.data_dir / PENDING_WORK_FILENAME).write_text(
        '{"publish": [{"caselist": "testcl26", "snapshot": "2026-09-01"}]}', encoding="utf-8"
    )
    clock(THIRD_RUN)
    source = FakeSource(bucket.installation.archives, weeks=[])
    third = await pull(
        bucket.installation,
        bucket.installation.sync(source, status=DriftBeforeTheComparison(bucket, rewrite=(WEEK_1,))),
        publish_pending=True,
    )

    assert "owed again, for the next run to publish: testcl26 2026-09-01" in str(report(third)["reason"])
    assert owed(bucket.installation) == [WEEK_ONE]


# ------------------------------------------------------------------------------------------------
# Drift only
# ------------------------------------------------------------------------------------------------


async def test_a_manifest_the_bucket_lost_is_not_owed_by_the_report_stage(bucket: Bucket, clock: Any) -> None:
    watched = await a_pull(bucket, comparison=DriftBeforeTheComparison(bucket, delete=(WEEK_1,)))

    assert report(watched)["drift"] == [
        {"caselist": CASELIST, "snapshot": "2026-09-01", "kinds": ["missing"]}
    ]
    assert "owed again" not in str(report(watched)["reason"])
    assert owed(bucket.installation) == []


async def test_a_source_mismatch_is_not_owed(bucket: Bucket, clock: Any) -> None:
    watched = await a_pull(bucket, comparison=DriftBeforeTheComparison(bucket, rewrite_source_of=(WEEK_1,)))

    assert report(watched)["drift"] == [{"caselist": CASELIST, "snapshot": "2026-09-01", "kinds": ["source"]}]
    assert owed(bucket.installation) == []


async def test_a_manifest_mismatch_beside_a_source_mismatch_is_not_owed(bucket: Bucket, clock: Any) -> None:
    watched = await a_pull(
        bucket,
        comparison=DriftBeforeTheComparison(bucket, rewrite=(WEEK_1,), rewrite_source_of=(WEEK_1,)),
    )

    assert report(watched)["drift"] == [
        {"caselist": CASELIST, "snapshot": "2026-09-01", "kinds": ["manifest", "source"]}
    ]
    assert owed(bucket.installation) == []


async def test_only_the_manifest_mismatch_is_owed_when_another_snapshot_has_a_source_mismatch(
    bucket: Bucket, clock: Any
) -> None:
    watched = await a_pull(
        bucket,
        comparison=DriftBeforeTheComparison(bucket, rewrite=(WEEK_1,), rewrite_source_of=(WEEK_2,)),
    )

    assert owed(bucket.installation) == [WEEK_ONE]
    [notification] = watched.notifier.sent
    assert notification.title == "caselist pull finished with a failed stage", "the source needs a person"


# ------------------------------------------------------------------------------------------------
# A pending-work file that cannot be read is never written over
# ------------------------------------------------------------------------------------------------


async def test_a_drift_is_not_written_over_a_pending_work_file_that_cannot_be_read(
    bucket: Bucket, clock: Any
) -> None:
    pending = bucket.installation.data_dir / PENDING_WORK_FILENAME
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_bytes(b"not json")

    watched = await a_pull(bucket, comparison=DriftBeforeTheComparison(bucket, rewrite=(WEEK_1,)))

    assert pending.read_bytes() == b"not json"
    assert report(watched)["reason"] == (
        "1 snapshot(s) confirmed; not in sync: testcl26 2026-09-01 (manifest mismatch); "
        "not recorded as owed, because the pending-work file could not be read: testcl26 2026-09-01"
    )
    assert watched.pulled.record is not None
    assert WEEK_ONE not in watched.pulled.record.pending_publish


# ------------------------------------------------------------------------------------------------
# The rule that tells "drifted again" from a first drift, on records and details written by hand
# ------------------------------------------------------------------------------------------------


def a_run(
    day: int,
    *,
    owed: tuple[str, ...] = (),
    drift: tuple[tuple[str, tuple[str, ...]], ...] | None = None,
    stages: bool = True,
) -> tuple[SyncRunRecord, SyncRunDetails | None]:
    """A run on `day` of September: the record's `pending_publish`, and its report stage's drift as
    (`<caselist> <snapshot>`, kinds) pairs, or no details at all when `drift` is `None`."""
    moment = datetime(2026, 9, day, 6, 0, tzinfo=UTC)
    record = SyncRunRecord(
        run_id=f"{moment:%Y%m%dT%H%M%SZ}",
        environment="dev",
        mode="run",
        started_at=moment,
        finished_at=moment,
        outcome=SyncRunOutcome.INCOMPLETE if stages else SyncRunOutcome.FAILED,
        pending_publish=owed,
        stages=(
            StageEntry(stage="publish", outcome="completed"),
            StageEntry(stage="report", outcome="failed"),
        )
        if stages
        else (),
    )
    if drift is None:
        return record, None
    findings = tuple(
        DriftFinding(caselist=named.split(" ")[0], snapshot=named.split(" ")[1], kinds=kinds)
        for named, kinds in drift
    )
    return record, SyncRunDetails(
        run_id=record.run_id, stages=(StageDetails(stage="report", drift=findings),) if findings else ()
    )


def owed_for_drift(*runs: tuple[SyncRunRecord, SyncRunDetails | None]) -> list[str]:
    records = [record for record, _ in runs]
    details = {record.run_id: one for record, one in runs if one is not None}
    return [f"{one.caselist} {one.snapshot}" for one in snapshots_owed_again_for_drift(records, details)]


MANIFEST = ("manifest",)


def test_no_run_has_owed_anything_again() -> None:
    assert owed_for_drift() == []


def test_a_run_that_found_a_manifest_alone_drifting_and_owed_it_owed_it_again_for_drift() -> None:
    assert owed_for_drift(a_run(16, owed=(WEEK_ONE,), drift=((WEEK_ONE, MANIFEST),))) == [WEEK_ONE]


def test_a_drift_the_run_did_not_owe_was_not_owed_again() -> None:
    """The run that refused a third time, or could not write the file, did not owe it."""
    assert owed_for_drift(a_run(16, owed=(), drift=((WEEK_ONE, MANIFEST),))) == []


def test_a_drift_of_another_kind_beside_the_manifest_was_not_owed_for_drift() -> None:
    """Owed, but for another reason: the report stage never owes a manifest beside a source."""
    assert owed_for_drift(a_run(16, owed=(WEEK_ONE,), drift=((WEEK_ONE, ("manifest", "source")),))) == []


def test_owed_for_drift_lasts_while_every_later_run_owes_it() -> None:
    assert owed_for_drift(
        a_run(16, owed=(WEEK_ONE,), drift=((WEEK_ONE, MANIFEST),)),
        a_run(23, owed=(WEEK_ONE, WEEK_TWO), drift=()),
    ) == [WEEK_ONE]


def test_a_later_run_that_did_not_owe_it_ends_it() -> None:
    assert (
        owed_for_drift(
            a_run(16, owed=(WEEK_ONE,), drift=((WEEK_ONE, MANIFEST),)),
            a_run(23, owed=(), drift=()),
            a_run(30, owed=(WEEK_ONE,), drift=()),
        )
        == []
    )


def test_a_run_with_no_stages_is_passed_over() -> None:
    """The lock, a refused start, an error that escaped: it touched nothing it owed."""
    assert owed_for_drift(
        a_run(16, owed=(WEEK_ONE,), drift=((WEEK_ONE, MANIFEST),)),
        a_run(23, stages=False, drift=()),
    ) == [WEEK_ONE]


def test_a_drift_run_with_no_details_says_nothing_of_drift() -> None:
    """An older build's run, or one whose details were lost: the guard is one run late, never wrong
    the other way."""
    assert owed_for_drift(a_run(16, owed=(WEEK_ONE,), drift=None)) == []


def test_only_the_snapshot_that_drifted_is_owed_for_drift() -> None:
    assert owed_for_drift(
        a_run(16, owed=(WEEK_ONE, WEEK_TWO), drift=((WEEK_ONE, MANIFEST),)),
        a_run(23, owed=(WEEK_ONE, WEEK_TWO), drift=()),
    ) == [WEEK_ONE]
