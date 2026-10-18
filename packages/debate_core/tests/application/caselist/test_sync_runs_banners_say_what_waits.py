"""The login banner names what waits, and a run's banner words are there for `caselist runs` (`v1-e34-t26`).

* **Item 1.** A run whose only pending stage is the report published what it imported and then lost
  its session while it compared. Its login banner said `0 snapshot(s) and the run record wait to be
  published`. What is outstanding is the run record, and the report stage's check, which
  `--publish-pending` does not make again: it compares only what it publishes itself, and nothing is
  owed. The banner now says so, and where the check is made after the login.
* **Item 3.** `caselist runs` shows the words a banner put beside its verdict: `skipped` for a run
  the lock refused, and `retry once fixed` for a refusal the retry gets past only once its fix is
  made. They are decided where the banner's title is, by :func:`sync_runs.banner_words`, so the two
  cannot say different things.
* **Item 2's banners**, on records and details written by hand: a manifest owed again, and one that
  drifted again after its republish, which needs a person.

Every expectation is written by hand.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_synthetic_archives import build_snapshot_zips

from debate_core.application import sync_runs
from debate_core.application.caselist_sync import SyncStage
from debate_core.application.ports.notifier import Notification
from debate_core.application.sync_runs import (
    DriftFinding,
    StageDetails,
    StageEntry,
    SyncRunDetails,
    SyncRunOutcome,
    SyncRunRecord,
    notifications_for,
)
from debate_core.integrations.s3 import S3EvidenceObjectStore

from .test_inbox_retention import WEEK_1, WEEK_2, FakeSource, Installation
from .test_pull_stage_failure_codes import pull, stage
from .test_sync_report_stage_keeps_what_it_found_and_its_kind import ScriptedComparison

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

WHERE = "Run 20260916T060000Z (dev)"
AWS_LOGIN = "aws sso login --profile debate-dev-evidence"
NO_SNAPSHOT_WAITS = f"{WHERE} kept everything it fetched; no snapshot waits to be published, only the run record."
THE_CHECK_WAS_CUT_SHORT = (
    " The report stage's check that the bucket holds what this run published was cut short; "
    "caselist pull --publish-pending does not make it again, and debate-research caselist status "
    "does, after the login."
)
PARSE_WAITS = " The parsed store waits too; after the login: debate-research caselist parse --caselist <slug> --publish"


def a_retry_may_cure(codes: Sequence[str]) -> bool:
    """The command's rule, as far as these tests need it: the two store failures a retry may cure."""
    return all(code in {"STORE_UNAVAILABLE", "STORE_ACCESS_DENIED"} for code in codes)


def a_record(
    *stages: tuple[str, str],
    pending_publish: tuple[str, ...] = (),
    outcome: SyncRunOutcome = SyncRunOutcome.COMPLETED,
    error_class: str | None = None,
) -> SyncRunRecord:
    moment = datetime.fromisoformat("2026-09-16T06:00:00+00:00")
    return SyncRunRecord(
        run_id="20260916T060000Z",
        environment="dev",
        mode="run",
        started_at=moment,
        finished_at=moment,
        outcome=outcome,
        pending_publish=pending_publish,
        stages=tuple(StageEntry(stage=name, outcome=result) for name, result in stages),
        error_class=error_class,
    )


def the_login_banner(record: SyncRunRecord, details: SyncRunDetails | None = None) -> str:
    sent = notifications_for(
        record,
        details or SyncRunDetails(run_id=record.run_id),
        aws_login_command=AWS_LOGIN,
        credentials_expired=True,
        may_succeed_on_retry=a_retry_may_cure,
    )
    [login] = [one for one in sent if one.title == "caselist publish waiting for an AWS login"]
    assert login.fix_command == f"{AWS_LOGIN} && debate-research caselist pull --publish-pending"
    return login.message


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


# ------------------------------------------------------------------------------------------------
# Item 1: the login banner names what waits
# ------------------------------------------------------------------------------------------------


async def test_a_report_only_pending_run_says_the_run_record_waits_and_the_check_was_cut_short(
    installation: Installation,
) -> None:
    """Both weeks published and confirmed by the publisher; the session expires at the report stage's
    first comparison. Nothing is owed."""
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    watched = await pull(
        installation, installation.sync(source, status=ScriptedComparison(installation, expires_at=1))
    )

    assert stage(watched.summary, SyncStage.PUBLISH)["outcome"] == "completed"
    assert stage(watched.summary, SyncStage.REPORT)["outcome"] == "pending"
    assert watched.summary.as_json()["pending_publish"] == []
    [login] = watched.notifier.sent
    assert login.message == NO_SNAPSHOT_WAITS + THE_CHECK_WAS_CUT_SHORT
    assert "0 snapshot(s)" not in login.message


def test_the_report_alone_pending_says_the_check_was_cut_short() -> None:
    record = a_record(("publish", "completed"), ("parse", "skipped"), ("report", "pending"))

    assert the_login_banner(record) == NO_SNAPSHOT_WAITS + THE_CHECK_WAS_CUT_SHORT


def test_the_parse_alone_pending_says_only_the_run_record_and_the_parsed_store_wait() -> None:
    record = a_record(("publish", "completed"), ("parse", "pending"), ("report", "completed"))

    assert the_login_banner(record) == NO_SNAPSHOT_WAITS + PARSE_WAITS


def test_a_pending_publish_still_counts_its_snapshots_and_the_check_waits_with_them() -> None:
    """The report stage pending with the publish confirms what the publish after the login
    publishes, so nothing is said of a check cut short."""
    record = a_record(
        ("publish", "pending"),
        ("report", "pending"),
        pending_publish=("testcl26 2026-09-01", "testcl26 2026-09-08"),
    )

    assert the_login_banner(record) == (
        f"{WHERE} kept everything it fetched; 2 snapshot(s) and the run record wait to be published."
    )


def test_a_report_pending_after_a_failed_publish_that_left_snapshots_owed_says_both() -> None:
    """The publish failed on one snapshot and published the other; the report stage then lost its
    session. The owed snapshot waits, and the check of the published one was cut short."""
    record = a_record(
        ("publish", "failed"),
        ("report", "pending"),
        pending_publish=("testcl26 2026-09-08",),
        outcome=SyncRunOutcome.FAILED,
    )

    assert the_login_banner(record) == (
        f"{WHERE} kept everything it fetched; 1 snapshot(s) and the run record wait to be published."
        + THE_CHECK_WAS_CUT_SHORT
    )


# ------------------------------------------------------------------------------------------------
# Item 3: the banner's words, for `caselist runs`
# ------------------------------------------------------------------------------------------------


def words(record: SyncRunRecord, details: SyncRunDetails | None) -> str | None:
    return sync_runs.banner_words(record, details, may_succeed_on_retry=a_retry_may_cure)


def test_a_run_the_lock_refused_says_skipped() -> None:
    record = a_record(outcome=SyncRunOutcome.FAILED, error_class="SyncRunInProgress")
    details = SyncRunDetails(run_id=record.run_id, failure_codes=("SYNC_RUN_IN_PROGRESS",))

    assert words(record, details) == "skipped"
    [notification] = notifications_for(
        record, details, aws_login_command=AWS_LOGIN, credentials_expired=False, may_succeed_on_retry=a_retry_may_cure
    )
    assert notification.title == "caselist pull skipped: another was running"


def test_a_failed_stage_refused_with_a_fix_says_retry_once_fixed() -> None:
    record = a_record(("publish", "failed"), outcome=SyncRunOutcome.FAILED)
    details = SyncRunDetails(
        run_id=record.run_id,
        stages=(StageDetails(stage="publish", error_codes=("STORE_ACCESS_DENIED",), hint="Grant it."),),
        failure_codes=("STORE_ACCESS_DENIED",),
    )

    assert words(record, details) == "retry once fixed"
    [notification] = notifications_for(
        record, details, aws_login_command=AWS_LOGIN, credentials_expired=False, may_succeed_on_retry=a_retry_may_cure
    )
    assert notification.title == "caselist pull failed: retried once fixed"


def test_a_run_stopped_with_a_fix_says_retry_once_fixed() -> None:
    record = a_record(outcome=SyncRunOutcome.FAILED, error_class="StoreAccessDenied")
    details = SyncRunDetails(run_id=record.run_id, failure_codes=("STORE_ACCESS_DENIED",), hint="Grant it.")

    assert words(record, details) == "retry once fixed"


def test_a_retry_with_no_fix_and_a_person_have_no_words_of_their_own() -> None:
    retried = a_record(("publish", "failed"), outcome=SyncRunOutcome.FAILED)
    no_fix = SyncRunDetails(
        run_id=retried.run_id,
        stages=(StageDetails(stage="publish", error_codes=("STORE_UNAVAILABLE",)),),
        failure_codes=("STORE_UNAVAILABLE",),
    )
    a_verdict = SyncRunDetails(
        run_id=retried.run_id,
        stages=(StageDetails(stage="publish", error_codes=("CHECKSUM_MISMATCH",), hint="Look at it."),),
        failure_codes=("CHECKSUM_MISMATCH",),
    )

    assert words(retried, no_fix) is None
    assert words(retried, a_verdict) is None, "a fix on a verdict is a person's, not a retry's"
    assert words(a_record(), SyncRunDetails(run_id="20260916T060000Z")) is None


def test_a_fix_on_a_stage_the_exit_is_not_decided_from_is_not_a_retry_once_fixed() -> None:
    """The parse stage's hint names its command, but the parse stage decides nothing about the exit;
    a run that also failed its publish on a cause a retry cures is a retry, with no fix first."""
    record = a_record(("publish", "failed"), ("parse", "failed"), outcome=SyncRunOutcome.FAILED)
    details = SyncRunDetails(
        run_id=record.run_id,
        stages=(
            StageDetails(stage="publish", error_codes=("STORE_UNAVAILABLE",)),
            StageDetails(stage="parse", error_codes=("PARSE_FAILURE_RATE_EXCEEDED",), hint="Parse it."),
        ),
        failure_codes=("STORE_UNAVAILABLE",),
    )

    assert words(record, details) is None


def test_a_run_with_no_details_has_no_words() -> None:
    """A run an older build recorded: the banner it showed then is not known here."""
    record = a_record(outcome=SyncRunOutcome.FAILED, error_class="SyncRunInProgress")

    assert words(record, None) is None


# ------------------------------------------------------------------------------------------------
# Item 2's banners: owed again, and drifted again
# ------------------------------------------------------------------------------------------------


def manifest_drift(*caselists: str) -> SyncRunDetails:
    return SyncRunDetails(
        run_id="20260916T060000Z",
        stages=(
            StageDetails(
                stage="report",
                error_codes=("CASELIST_DRIFT",),
                drift=tuple(
                    DriftFinding(caselist=caselist, snapshot="2026-09-01", kinds=("manifest",))
                    for caselist in caselists
                ),
            ),
        ),
    )


def sent_for(record: SyncRunRecord, details: SyncRunDetails) -> list[Notification]:
    return notifications_for(
        record, details, aws_login_command=AWS_LOGIN, credentials_expired=False, may_succeed_on_retry=a_retry_may_cure
    )


REPORT_FAILED = (("publish", "completed"), ("report", "failed"))


def test_manifests_owed_again_are_announced_as_published_by_the_next_run() -> None:
    record = a_record(
        *REPORT_FAILED,
        outcome=SyncRunOutcome.INCOMPLETE,
        pending_publish=("hsld26 2026-09-01", "hspolicy26 2026-09-01"),
    )

    [notification] = sent_for(record, manifest_drift("hsld26", "hspolicy26"))

    assert notification.title == "caselist pull: publish a manifest again"
    assert notification.message == (
        f"{WHERE}: the report stage found the bucket's manifests of hsld26 2026-09-01, hspolicy26 "
        "2026-09-01 differ from this machine's. The next scheduled run publishes them again: this "
        "machine rewrote the manifests after they were published, and the publish uploads this "
        "machine's copy. Nothing here needs a person."
    )
    assert notification.fix_command == "debate-research caselist pull --publish-pending"


def test_a_manifest_not_owed_again_needs_a_person_named_by_caselist_and_date() -> None:
    record = a_record(*REPORT_FAILED, outcome=SyncRunOutcome.INCOMPLETE)

    [notification] = sent_for(record, manifest_drift("hsld26"))

    assert notification.title == "caselist pull: a manifest drifted again"
    assert notification.message == (
        f"{WHERE}: the bucket's manifest of hsld26 2026-09-01 differs from this machine's again, after "
        "a run published it again and the bucket confirmed it. Publishing it a third time would not "
        "clear it, so it is not owed again: a person should look."
    )
    assert notification.fix_command == "debate-research caselist status --caselist hsld26"


def test_one_owed_again_and_one_drifted_again_says_both_and_asks_for_a_person() -> None:
    record = a_record(*REPORT_FAILED, outcome=SyncRunOutcome.INCOMPLETE, pending_publish=("hsld26 2026-09-01",))

    [notification] = sent_for(record, manifest_drift("hsld26", "hspolicy26"))

    assert notification.title == "caselist pull: a manifest drifted again"
    assert notification.message == (
        f"{WHERE}: the bucket's manifest of hspolicy26 2026-09-01 differs from this machine's again, "
        "after a run published it again and the bucket confirmed it. Publishing it a third time would "
        "not clear it, so it is not owed again: a person should look. The manifest of hsld26 "
        "2026-09-01 is owed again, and the next scheduled run publishes it."
    )
    assert notification.fix_command == "debate-research caselist status --caselist hspolicy26"


def test_a_drift_found_before_the_session_expired_and_not_owed_again_asks_for_a_person() -> None:
    record = a_record(("publish", "completed"), ("report", "pending"))
    details = SyncRunDetails(
        run_id=record.run_id,
        stages=(
            StageDetails(
                stage="report",
                earlier_findings=("CASELIST_DRIFT",),
                drift=(DriftFinding(caselist="hsld26", snapshot="2026-09-01", kinds=("manifest",)),),
            ),
        ),
    )

    message = the_login_banner(record, details)

    assert message == (
        NO_SNAPSHOT_WAITS
        + THE_CHECK_WAS_CUT_SHORT
        + " A person should look as well: before the session expired, the bucket's manifest of hsld26 "
        "2026-09-01 was found to differ from this machine's again, after a run published it again and "
        "the bucket confirmed it; it is not owed again."
    )
