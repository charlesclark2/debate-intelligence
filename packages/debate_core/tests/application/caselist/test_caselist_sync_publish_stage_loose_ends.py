"""Publish-stage loose ends (`v1-e34-t28`): a cut-short check, the manifest count, a report-only outcome.

* **(1) A report-stage check an expired session cut short is made again.** The report stage compares
  what the run published with the bucket, snapshot by snapshot. When the session expired part-way,
  what it had not compared yet was named nowhere: `--publish-pending` compares only what it
  publishes, and the publish had already confirmed them. The PM's ruling of 2026-10-22: the
  snapshots the newest run published and did not compare are saved in that run's details, beside
  the report stage, and `caselist pull --publish-pending` compares exactly those, through the report
  stage itself. Details an older build wrote have no such list, and owe nothing.
* **(2) The publish stage counts the manifest it uploads.** A republish that uploaded only a
  manifest said `0 object(s) uploaded across 1 snapshot(s)`. The count, the summary's
  `objects_published` and the details now include it, and the reason says how many were manifests.
* **(3) A run whose only pending stage is the report is `publish_pending`**, as every other run
  waiting for a login is, and no longer `completed`. The value is one every installed build reads.

The comparison is the real one, against moto, with one thing scripted on top of it where a test
needs it: the session expiring at a given comparison. Every expectation is written by hand.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from tests.fixtures.caselist.build_synthetic_archives import build_snapshot_zips

from debate_core.application.caselist.status_service import CaselistStatusReport, CaselistStatusService
from debate_core.application.caselist_sync import (
    LOCK_FILENAME,
    RunLock,
    RunSummary,
    StageOutcome,
    StageRecord,
    SyncRunInProgress,
    SyncStage,
)
from debate_core.application.sync_runs import record_for_summary
from debate_core.integrations.s3 import S3EvidenceObjectStore
from debate_core.testing.fakes import empty_suppression_list

from . import test_inbox_retention as inbox_retention
from .test_caselist_sync_owes_a_drifted_manifest_again import Bucket, DriftBeforeTheComparison
from .test_inbox_retention import WEEK_1, WEEK_2, FakeSource, Installation
from .test_pending_work_owes_every_unpublished_snapshot import MANIFEST, Session
from .test_pull_stage_failure_codes import Watched, owed, pull, stage
from .test_sync_report_stage_keeps_what_it_found_and_its_kind import ScriptedComparison

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

FIRST_RUN = datetime(2026, 9, 16, 6, 0, tzinfo=UTC)
SECOND_RUN = datetime(2026, 9, 16, 9, 0, tzinfo=UTC)
THIRD_RUN = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
FOURTH_RUN = datetime(2026, 9, 16, 15, 0, tzinfo=UTC)
FIRST_RUN_ID, SECOND_RUN_ID = "20260916T060000Z", "20260916T090000Z"

RUN_LOG_FILE = "caselist-sync-runs.jsonl"
DETAILS_FILE = "caselist-sync-run-details.jsonl"
"""The two files' names as the runbook gives them, written out and not imported."""

WEEK_ONE = {"caselist": "testcl26", "snapshot": "2026-09-01"}
WEEK_TWO = {"caselist": "testcl26", "snapshot": "2026-09-08"}


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


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Any:
    def set_clock(moment: datetime) -> None:
        monkeypatch.setattr(inbox_retention, "RUN_CLOCK", moment)

    set_clock(FIRST_RUN)
    return set_clock


class RecordingComparison(CaselistStatusService):
    """The real comparison over the installation's bucket, recording every snapshot it is asked about."""

    def __init__(self, installation: Installation) -> None:
        super().__init__(
            local=installation.local, remote=installation.bucket, suppression=empty_suppression_list()
        )
        self.asked: list[tuple[str | None, str | None]] = []

    async def status(
        self, caselist: str | None = None, snapshot: str | None = None, **asked: Any
    ) -> CaselistStatusReport:
        self.asked.append((caselist, snapshot))
        return await super().status(caselist, snapshot, **asked)


def run_log(installation: Installation) -> list[dict[str, Any]]:
    """The run log as JSON, a line a run, read by its name and not through the code under test."""
    text = (installation.data_dir / RUN_LOG_FILE).read_text("utf-8")
    return [json.loads(line) for line in text.splitlines()]


def details_lines(installation: Installation) -> list[dict[str, Any]]:
    """The details file as JSON, a line a run, read by its name and not through the code under test."""
    text = (installation.data_dir / DETAILS_FILE).read_text("utf-8")
    return [json.loads(line) for line in text.splitlines()]


def report_details_of(details: dict[str, Any]) -> dict[str, Any] | None:
    return next((one for one in details["stages"] if one["stage"] == "report"), None)


def not_compared_in_the_details(installation: Installation, run_id: str) -> object:
    """What the details of `run_id` say its report stage did not compare; `None` when they say nothing."""
    [details] = [one for one in details_lines(installation) if one["run_id"] == run_id]
    found = report_details_of(details)
    return None if found is None else found.get("not_compared")


async def two_weeks_with_the_check_cut_short(installation: Installation, *, expires_at: int) -> Watched:
    """Both weeks imported and published; the session expires at the report stage's `expires_at`th
    comparison, counting from one."""
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    comparison = ScriptedComparison(installation, expires_at=expires_at)
    return await pull(installation, installation.sync(source, status=comparison))


async def publish_pending(installation: Installation, comparison: CaselistStatusService) -> Watched:
    """`caselist pull --publish-pending`, with nothing new upstream, comparing with `comparison`."""
    source = FakeSource(installation.archives, weeks=[])
    return await pull(installation, installation.sync(source, status=comparison), publish_pending=True)


# ------------------------------------------------------------------------------------------------
# (1) What a cut-short check did not compare is in the run's details
# ------------------------------------------------------------------------------------------------


async def test_a_check_cut_short_at_its_first_comparison_saves_both_weeks_in_the_details(
    installation: Installation,
) -> None:
    watched = await two_weeks_with_the_check_cut_short(installation, expires_at=1)

    assert stage(watched.summary, SyncStage.PUBLISH)["outcome"] == "completed"
    report = stage(watched.summary, SyncStage.REPORT)
    assert report["outcome"] == "pending"
    assert report["not_compared"] == [WEEK_ONE, WEEK_TWO]
    assert not_compared_in_the_details(installation, FIRST_RUN_ID) == [WEEK_ONE, WEEK_TWO]
    assert owed(installation) == [], "a comparison owed is not a publish owed"


async def test_a_check_cut_short_at_its_second_comparison_saves_only_the_week_it_did_not_reach(
    installation: Installation,
) -> None:
    await two_weeks_with_the_check_cut_short(installation, expires_at=2)

    assert not_compared_in_the_details(installation, FIRST_RUN_ID) == [WEEK_TWO]


async def test_the_run_record_carries_nothing_new(installation: Installation) -> None:
    """The record is the shape every installed build reads: the list is in the details alone."""
    await two_weeks_with_the_check_cut_short(installation, expires_at=1)

    [record] = run_log(installation)
    assert "not_compared" not in json.dumps(record)
    assert "manifests_published" not in json.dumps(record)


async def test_a_publish_the_session_cut_short_leaves_what_it_confirmed_owed_a_comparison(
    installation: Installation,
) -> None:
    """Week one is published and confirmed; the session expires on week two's manifest. The report
    stage pends without comparing anything, so week one is owed a comparison, and week two a publish."""
    session = Session(installation.bucket, expires_on=MANIFEST[WEEK_2])
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    watched = await pull(installation, installation.sync(source, publish_to=session))
    await session.settle()

    assert stage(watched.summary, SyncStage.PUBLISH)["outcome"] == "pending"
    assert stage(watched.summary, SyncStage.REPORT)["outcome"] == "pending"
    assert not_compared_in_the_details(installation, FIRST_RUN_ID) == [WEEK_ONE]
    assert owed(installation) == ["testcl26 2026-09-08"]


async def test_a_check_that_completes_saves_nothing(installation: Installation) -> None:
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    watched = await pull(installation, installation.sync(source))

    assert stage(watched.summary, SyncStage.REPORT)["outcome"] == "completed"
    assert stage(watched.summary, SyncStage.REPORT)["not_compared"] == []
    assert not_compared_in_the_details(installation, FIRST_RUN_ID) is None, "no report stage entry at all"


# ------------------------------------------------------------------------------------------------
# (1) `--publish-pending` compares exactly those, through the report stage
# ------------------------------------------------------------------------------------------------


async def test_publish_pending_compares_exactly_the_weeks_the_cut_short_check_did_not(
    installation: Installation, clock: Any
) -> None:
    await two_weeks_with_the_check_cut_short(installation, expires_at=2)

    clock(SECOND_RUN)
    comparison = RecordingComparison(installation)
    drained = await publish_pending(installation, comparison)

    assert comparison.asked == [("testcl26", "2026-09-08")], "week two, and week two alone"
    assert stage(drained.summary, SyncStage.PUBLISH) == {
        **stage(drained.summary, SyncStage.PUBLISH),
        "outcome": "skipped",
        "reason": "nothing new to publish",
    }
    report = stage(drained.summary, SyncStage.REPORT)
    assert report["outcome"] == "completed"
    assert report["reason"] == "1 snapshot(s) confirmed in the bucket"
    assert report["not_compared"] == []
    assert stage(drained.summary, SyncStage.SELECT)["reason"] == (
        "0 snapshot(s) owed; the report stage's check of 1 snapshot(s) an earlier run published "
        "was cut short, and is made again"
    )


async def test_the_check_made_again_is_owed_by_nothing_after_it(
    installation: Installation, clock: Any
) -> None:
    await two_weeks_with_the_check_cut_short(installation, expires_at=1)
    clock(SECOND_RUN)
    await publish_pending(installation, RecordingComparison(installation))

    clock(THIRD_RUN)
    comparison = RecordingComparison(installation)
    again = await publish_pending(installation, comparison)

    assert comparison.asked == []
    assert stage(again.summary, SyncStage.REPORT)["outcome"] == "skipped"
    assert stage(again.summary, SyncStage.SELECT)["reason"] == "0 snapshot(s) owed"


async def test_publish_pending_publishes_what_is_owed_and_then_compares_it_and_the_check_owed(
    installation: Installation, clock: Any
) -> None:
    session = Session(installation.bucket, expires_on=MANIFEST[WEEK_2])
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    await pull(installation, installation.sync(source, publish_to=session))
    await session.settle()

    clock(SECOND_RUN)
    comparison = RecordingComparison(installation)
    drained = await publish_pending(installation, comparison)

    assert stage(drained.summary, SyncStage.PUBLISH)["outcome"] == "completed"
    assert comparison.asked == [("testcl26", "2026-09-08"), ("testcl26", "2026-09-01")], (
        "what this run published, then what the cut-short check owed"
    )
    assert stage(drained.summary, SyncStage.REPORT)["reason"] == "2 snapshot(s) confirmed in the bucket"
    assert owed(installation) == []


async def test_a_details_file_an_older_build_wrote_owes_no_comparison(
    installation: Installation, clock: Any
) -> None:
    """The cut-short run, as a build from before this task records it: its details have no list."""
    await two_weeks_with_the_check_cut_short(installation, expires_at=1)
    older = []
    for line in details_lines(installation):
        for one in line["stages"]:
            one.pop("not_compared", None)
        line.pop("manifests_published", None)
        older.append(json.dumps(line))
    (installation.data_dir / DETAILS_FILE).write_text("\n".join(older) + "\n", encoding="utf-8")

    clock(SECOND_RUN)
    comparison = RecordingComparison(installation)
    drained = await publish_pending(installation, comparison)

    assert comparison.asked == []
    assert stage(drained.summary, SyncStage.REPORT) == {
        **stage(drained.summary, SyncStage.REPORT),
        "outcome": "skipped",
        "reason": "nothing new was published",
    }


async def test_only_the_newest_run_owes_a_comparison(installation: Installation, clock: Any) -> None:
    """A pull after the cut-short run, with nothing new, is the newest run, and owes nothing."""
    await two_weeks_with_the_check_cut_short(installation, expires_at=1)
    clock(SECOND_RUN)
    await pull(installation, installation.sync(FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])))

    clock(THIRD_RUN)
    comparison = RecordingComparison(installation)
    await publish_pending(installation, comparison)

    assert comparison.asked == []


async def test_a_run_the_lock_refused_is_passed_over(installation: Installation, clock: Any) -> None:
    """A run that stopped before any stage touched nothing, so the run before it is still the newest."""
    await two_weeks_with_the_check_cut_short(installation, expires_at=1)
    clock(SECOND_RUN)
    with RunLock(installation.data_dir / LOCK_FILENAME), pytest.raises(SyncRunInProgress):
        await publish_pending(installation, RecordingComparison(installation))
    assert [one["stages"] for one in run_log(installation)][1] == []

    clock(THIRD_RUN)
    comparison = RecordingComparison(installation)
    await publish_pending(installation, comparison)

    assert comparison.asked == [("testcl26", "2026-09-01"), ("testcl26", "2026-09-08")]


async def test_a_check_made_again_and_cut_short_again_is_owed_by_the_run_that_cut_it_short(
    installation: Installation, clock: Any
) -> None:
    await two_weeks_with_the_check_cut_short(installation, expires_at=1)

    clock(SECOND_RUN)
    await publish_pending(installation, ScriptedComparison(installation, expires_at=2))
    assert not_compared_in_the_details(installation, SECOND_RUN_ID) == [WEEK_TWO]

    clock(THIRD_RUN)
    comparison = RecordingComparison(installation)
    await publish_pending(installation, comparison)
    assert comparison.asked == [("testcl26", "2026-09-08")]


async def test_a_check_made_again_finds_a_drifted_manifest_as_the_report_stage_does(
    installation: Installation, clock: Any, s3_client: S3Client, evidence_bucket: str
) -> None:
    """The same stage: a manifest mismatch alone is owed again, and the next publish uploads it."""
    await two_weeks_with_the_check_cut_short(installation, expires_at=1)

    clock(SECOND_RUN)
    bucket = Bucket(installation=installation, s3_client=s3_client, name=evidence_bucket)
    drained = await publish_pending(installation, DriftBeforeTheComparison(bucket, rewrite=(WEEK_1,)))

    report = stage(drained.summary, SyncStage.REPORT)
    assert report["outcome"] == "failed"
    assert report["error_codes"] == ["CASELIST_DRIFT"]
    assert report["drift"] == [{**WEEK_ONE, "kinds": ["manifest"]}]
    assert str(report["reason"]).startswith("1 snapshot(s) confirmed; not in sync: testcl26 2026-09-01")
    assert owed(installation) == ["testcl26 2026-09-01"]


# ------------------------------------------------------------------------------------------------
# (2) The publish stage counts the manifest it uploads
# ------------------------------------------------------------------------------------------------


async def test_a_first_publish_counts_its_manifest_beside_its_sources(installation: Installation) -> None:
    """Week one is four sources (`expected_publish.json`) and its manifest."""
    source = FakeSource(installation.archives, weeks=[WEEK_1])
    watched = await pull(installation, installation.sync(source))

    assert stage(watched.summary, SyncStage.PUBLISH)["reason"] == (
        "5 object(s) uploaded across 1 snapshot(s): 4 source(s) and 1 manifest(s)"
    )
    assert watched.summary.as_json()["objects_published"] == 5
    assert watched.summary.as_json()["manifests_published"] == 1
    [record] = run_log(installation)
    assert record["objects_published"] == 5
    [details] = details_lines(installation)
    assert details["manifests_published"] == 1


async def test_a_republish_of_a_manifest_alone_says_it_uploaded_the_manifest(
    installation: Installation, clock: Any, s3_client: S3Client, evidence_bucket: str
) -> None:
    """Week one's manifest drifts at the report stage and is owed again; the next pull uploads it and
    nothing else, because the bucket holds every source already."""
    bucket = Bucket(installation=installation, s3_client=s3_client, name=evidence_bucket)
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    await pull(
        installation, installation.sync(source, status=DriftBeforeTheComparison(bucket, rewrite=(WEEK_1,)))
    )
    assert owed(installation) == ["testcl26 2026-09-01"]

    clock(SECOND_RUN)
    again = await pull(installation, installation.sync(source))

    assert stage(again.summary, SyncStage.PUBLISH)["reason"] == (
        "1 object(s) uploaded across 1 snapshot(s): 0 source(s) and 1 manifest(s)"
    )
    assert again.summary.as_json()["objects_published"] == 1
    assert run_log(installation)[1]["objects_published"] == 1
    assert details_lines(installation)[1]["manifests_published"] == 1


async def test_a_publish_left_for_a_login_counts_the_manifest_it_did_upload(
    installation: Installation,
) -> None:
    """Week one's four sources and its manifest are confirmed; the session expires on week two's."""
    session = Session(installation.bucket, expires_on=MANIFEST[WEEK_2])
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    watched = await pull(installation, installation.sync(source, publish_to=session))
    await session.settle()

    assert str(stage(watched.summary, SyncStage.PUBLISH)["reason"]).startswith(
        "5 object(s) published, 1 snapshot(s) left for a later run: "
    )
    assert details_lines(installation)[0]["manifests_published"] == 1


# ------------------------------------------------------------------------------------------------
# (3) A report-only pending run is `publish_pending`
# ------------------------------------------------------------------------------------------------


async def test_a_report_only_pending_run_is_recorded_publish_pending(installation: Installation) -> None:
    watched = await two_weeks_with_the_check_cut_short(installation, expires_at=1)

    [record] = run_log(installation)
    assert record["outcome"] == "publish_pending"
    assert watched.summary.succeeded, "the exit is decided as before: nothing that had to finish failed"


def a_summary(*stages: tuple[SyncStage, StageOutcome]) -> RunSummary:
    moment = datetime(2026, 9, 16, 6, 0, tzinfo=UTC)
    return RunSummary(
        run_id=FIRST_RUN_ID,
        started_at=moment,
        finished_at=moment,
        dry_run=False,
        caselists=("testcl26",),
        stages=tuple(StageRecord(stage=name, outcome=outcome) for name, outcome in stages),
        snapshots_imported=("testcl26 2026-09-01",),
    )


DONE, SKIPPED, PENDING, FAILED = (
    StageOutcome.COMPLETED,
    StageOutcome.SKIPPED,
    StageOutcome.PENDING,
    StageOutcome.FAILED,
)


@pytest.mark.parametrize(
    ("publish", "parse", "report", "outcome"),
    [
        pytest.param(DONE, SKIPPED, PENDING, "publish_pending", id="the report alone pending"),
        pytest.param(DONE, FAILED, PENDING, "publish_pending", id="the report pending beside a failed parse"),
        pytest.param(PENDING, SKIPPED, PENDING, "publish_pending", id="the publish pending, as before"),
        pytest.param(FAILED, SKIPPED, PENDING, "failed", id="a failed publish is failed, as before"),
        pytest.param(DONE, SKIPPED, DONE, "completed", id="nothing pending, as before"),
        pytest.param(DONE, SKIPPED, FAILED, "incomplete", id="a failed report, as before"),
        pytest.param(DONE, PENDING, DONE, "publish_pending", id="the parse pending, as before"),
    ],
)
def test_the_outcome_of_a_run_by_how_its_stages_ended(
    publish: StageOutcome, parse: StageOutcome, report: StageOutcome, outcome: str
) -> None:
    summary = a_summary(
        (SyncStage.SELECT, DONE),
        (SyncStage.DOWNLOAD, DONE),
        (SyncStage.IMPORT, DONE),
        (SyncStage.PUBLISH, publish),
        (SyncStage.PARSE, parse),
        (SyncStage.REPORT, report),
    )

    assert str(record_for_summary(summary, environment="dev", mode="run").outcome) == outcome
