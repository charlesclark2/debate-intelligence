"""The caselist sync run log: one validated record per run, locally and in the bucket (ac1).

`debate_core.application.sync_runs`. The summaries here are built by hand rather than by running
the pipeline — `test_caselist_sync.py` does that — so each expected number is read straight off the
summary a test wrote (`docs/process/working-agreements.md` §6). The bucket is moto's.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from debate_core.application.caselist_sync import (
    ArchiveSelection,
    RunSummary,
    SelectionDecision,
    StageOutcome,
    StageRecord,
    SyncStage,
)
from debate_core.application.errors import StoreCredentialsExpired
from debate_core.application.ports.caselist_source import ArchiveKind
from debate_core.application.ports.evidence_store import ObjectInfo, ObjectKey
from debate_core.application.ports.notifier import RecordingNotifier
from debate_core.application.sync_runs import (
    PENDING_RECORDS_FILENAME,
    SYNC_RUN_LOG_FILENAME,
    SyncRunLog,
    SyncRunMonitor,
    SyncRunOutcome,
    SyncRunRecord,
    read_remote_records,
    record_for_summary,
    redact,
    sync_run_key,
)
from debate_core.integrations.s3 import S3EvidenceObjectStore

if TYPE_CHECKING:  # pragma: no cover - imported for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

STARTED = datetime(2026, 9, 24, 4, 23, 0, tzinfo=UTC)
LOGIN = "aws sso login --profile debate-dev-evidence"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def bucket(evidence_bucket: str, s3_client: S3Client) -> S3EvidenceObjectStore:
    return S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client)


def weekly(caselist: str, day: date, decision: SelectionDecision) -> ArchiveSelection:
    return ArchiveSelection(
        caselist=caselist,
        name=f"{caselist}-weekly-{day.isoformat()}.zip",
        kind=ArchiveKind.WEEKLY,
        archive_date=day,
        decision=decision,
    )


def summary(
    *,
    started: datetime = STARTED,
    archives: Sequence[ArchiveSelection] = (),
    downloaded: int = 0,
    stages: Sequence[StageRecord] = (),
    pending_publish: tuple[str, ...] = (),
) -> RunSummary:
    return RunSummary(
        run_id=started.strftime("%Y%m%dT%H%M%SZ"),
        started_at=started,
        finished_at=started + timedelta(seconds=34),
        dry_run=False,
        caselists=tuple(sorted({one.caselist for one in archives})) or ("hsld26",),
        stages=tuple(stages)
        or tuple(StageRecord(stage=stage, outcome=StageOutcome.COMPLETED) for stage in SyncStage),
        archives=tuple(archives),
        archives_downloaded=downloaded,
        snapshots_imported=tuple(f"{one.caselist} {one.archive_date}" for one in archives[:downloaded]),
        pending_publish=pending_publish,
    )


def the_first_dev_run(started: datetime = STARTED, *, fetched: int = 5, wanted: int = 12) -> RunSummary:
    """2026-09-24's first run, as docs/data/caselist-sync-runs.md records it: 5 of 12, 7 deferred."""
    days = [date(2026, 6, 30) + timedelta(weeks=week) for week in range(wanted)]
    return summary(
        started=started,
        archives=[
            weekly(
                "hsld26",
                day,
                SelectionDecision.DOWNLOAD if index < fetched else SelectionDecision.OVER_DAILY_BUDGET,
            )
            for index, day in enumerate(days)
        ],
        downloaded=fetched,
    )


def monitor(
    tmp_path: Path, *, remote: object | None = None, notifier: RecordingNotifier | None = None
) -> SyncRunMonitor:
    return SyncRunMonitor(
        state_dir=tmp_path,
        environment="dev",
        notifier=notifier or RecordingNotifier(),
        remote=remote,  # type: ignore[arg-type]
        aws_login_command=LOGIN,
        clock=lambda: STARTED,
    )


async def returning(value: RunSummary) -> RunSummary:
    return value


# ------------------------------------------------------------------------------------------------
# The record
# ------------------------------------------------------------------------------------------------


def test_a_record_states_wanted_downloaded_and_deferred() -> None:
    """The measured run: 12 wanted, 5 downloaded, 7 deferred — and so not a clean week."""
    record = record_for_summary(the_first_dev_run(), environment="dev", mode="run")

    assert record.archives_wanted == 12
    assert record.archives_downloaded == 5
    assert record.archives_deferred == 7
    assert record.deferred_by_caselist == {"hsld26": 7}
    assert record.outcome is SyncRunOutcome.CAP_DEFERRED
    assert record.backlog_carried is None, "a first run has no backlog to carry"


def test_the_record_schema_refuses_a_field_it_does_not_define() -> None:
    body = json.loads(
        record_for_summary(the_first_dev_run(), environment="dev", mode="run").model_dump_json()
    )
    body["caselist_token"] = "never"

    with pytest.raises(ValidationError):
        SyncRunRecord.model_validate(body)


def test_the_bucket_key_is_the_year_and_the_run_id() -> None:
    assert sync_run_key("20260924T042300Z", STARTED) == "reports/sync-runs/2026/20260924T042300Z.json"


def test_the_backlog_is_carried_into_the_next_run_and_reported() -> None:
    """Next day: the 7 deferred become the 7 wanted, 5 fetched, 2 still waiting."""
    first = record_for_summary(the_first_dev_run(), environment="dev", mode="run")
    next_day = record_for_summary(
        the_first_dev_run(STARTED + timedelta(days=1), fetched=5, wanted=7),
        environment="dev",
        mode="run",
        previous=[first],
    )

    assert next_day.backlog_carried == 7
    assert next_day.archives_deferred == 2
    assert next_day.backlog_growing == ()


def test_a_backlog_that_grows_for_two_runs_is_flagged_and_one_that_clears_is_not() -> None:
    """Deferred 1, then 3, then 5: grown twice. Deferred 7, 7, 7 (the dev day's reruns): not."""
    growing: list[SyncRunRecord] = []
    for day, wanted in enumerate((6, 8, 10)):
        growing.append(
            record_for_summary(
                the_first_dev_run(STARTED + timedelta(weeks=day), fetched=5, wanted=wanted),
                environment="dev",
                mode="run",
                previous=growing,
            )
        )
    assert [one.archives_deferred for one in growing] == [1, 3, 5]
    assert [one.backlog_growing for one in growing] == [(), (), ("hsld26",)]

    steady: list[SyncRunRecord] = []
    for rerun in range(3):
        steady.append(
            record_for_summary(
                the_first_dev_run(STARTED + timedelta(minutes=rerun), fetched=0, wanted=7),
                environment="dev",
                mode="run",
                previous=steady,
            )
        )
    assert [one.backlog_growing for one in steady] == [(), (), ()]


# ------------------------------------------------------------------------------------------------
# Redaction
# ------------------------------------------------------------------------------------------------


def test_redaction_removes_tokens_urls_and_paths_quoted_or_not() -> None:
    message = (
        "caselist_token=fixture-token-5f1e refused; GET https://api.example.invalid/download?path=x "
        "then [Errno 2] No such file: 'inbox/Maple Grove/ZaLu/Juniper Okafor-Aff.docx' and Cedar/QX-Neg"
    )

    cleaned = redact(message, secrets=["fixture-token-5f1e"])

    for forbidden in ("fixture-token-5f1e", "path=x", "Juniper", "Okafor", "ZaLu", "Maple Grove", "QX-Neg"):
        assert forbidden not in cleaned


# ------------------------------------------------------------------------------------------------
# Persistence: the local log and the bucket
# ------------------------------------------------------------------------------------------------


async def test_a_run_leaves_exactly_one_record_in_the_local_log(tmp_path: Path) -> None:
    watched = monitor(tmp_path)

    await watched.watch(lambda: returning(the_first_dev_run()), caselists=["hsld26"], mode="run")

    records = SyncRunLog(tmp_path / SYNC_RUN_LOG_FILENAME).read()
    assert [one.run_id for one in records] == ["20260924T042300Z"]
    lines = (tmp_path / SYNC_RUN_LOG_FILENAME).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    SyncRunRecord.model_validate_json(lines[0])


async def test_a_run_that_raises_still_leaves_exactly_one_record(tmp_path: Path) -> None:
    watched = monitor(tmp_path)

    async def broken() -> RunSummary:
        raise RuntimeError("something this project did not write")

    with pytest.raises(RuntimeError):
        await watched.watch(broken, caselists=["hsld26"], mode="run")

    [record] = SyncRunLog(tmp_path / SYNC_RUN_LOG_FILENAME).read()
    assert record.outcome is SyncRunOutcome.FAILED
    assert record.error_class == "RuntimeError"
    assert record.error_message is None, "a message this project did not write is not recorded"


async def test_the_record_is_published_under_reports_sync_runs(
    tmp_path: Path, bucket: S3EvidenceObjectStore
) -> None:
    watched = monitor(tmp_path, remote=bucket)

    run = await watched.watch(lambda: returning(the_first_dev_run()), caselists=["hsld26"], mode="run")

    assert run.record_published
    destination = tmp_path / "fetched.json"
    await bucket.get_file("reports/sync-runs/2026/20260924T042300Z.json", destination)
    assert SyncRunRecord.model_validate_json(destination.read_text(encoding="utf-8")) == run.record
    assert not (tmp_path / PENDING_RECORDS_FILENAME).exists()


class ExpiredBucket:
    async def list_objects(self, prefix: str) -> tuple[ObjectInfo, ...]:
        raise StoreCredentialsExpired(hint=LOGIN)

    async def head(self, key: ObjectKey) -> ObjectInfo:
        raise StoreCredentialsExpired(hint=LOGIN)

    async def put_file(self, key: ObjectKey, source: Path) -> ObjectInfo:
        raise StoreCredentialsExpired(hint=LOGIN)

    async def get_file(self, key: ObjectKey, destination: Path) -> ObjectInfo:
        raise StoreCredentialsExpired(hint=LOGIN)


async def test_an_expired_session_defers_the_record_and_the_next_run_publishes_both(
    tmp_path: Path, bucket: S3EvidenceObjectStore
) -> None:
    notifier = RecordingNotifier()
    expired = monitor(tmp_path, remote=ExpiredBucket(), notifier=notifier)
    first = await expired.watch(lambda: returning(the_first_dev_run()), caselists=["hsld26"], mode="run")

    assert not first.record_published
    assert expired.pending_record_ids() == ["20260924T042300Z"]
    assert [one.title for one in notifier.sent] == ["caselist publish waiting for an AWS login"]

    logged_in = monitor(tmp_path, remote=bucket)
    later = the_first_dev_run(STARTED + timedelta(days=1), fetched=5, wanted=7)
    second = await logged_in.watch(lambda: returning(later), caselists=["hsld26"], mode="run")

    assert second.record_published
    assert logged_in.pending_record_ids() == []
    records = await read_remote_records(bucket, last=5, scratch_dir=tmp_path)
    assert [one.run_id for one in records] == ["20260925T042300Z", "20260924T042300Z"]
    assert len(SyncRunLog(tmp_path / SYNC_RUN_LOG_FILENAME).read()) == 2, "still one record per run"


async def test_the_log_skips_a_line_that_is_not_a_record(tmp_path: Path) -> None:
    log = SyncRunLog(tmp_path / SYNC_RUN_LOG_FILENAME)
    log.append(record_for_summary(the_first_dev_run(), environment="dev", mode="run"))
    with (tmp_path / SYNC_RUN_LOG_FILENAME).open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")

    assert len(log.read()) == 1
    assert log.last(5)[0].run_id == "20260924T042300Z"
