"""In bucket mode the failed-publish banners point at the cloud run, not a Mac-side publish (`v1-e40-t25`).

`v1-e40-t18` and `v1-e40-t22` moved the parse stage's hints and the login banner's fix to the cloud
run. Three hints in bucket mode still named `caselist pull --publish-pending`, which publishes from
the working copy of the machine it is run on, and the cloud run's working copy ends with its task:

* **A failed publish stage's banner.** Its fix is now the next cloud run, from the run state saved in
  the bucket, and its last sentence says what is kept: what the bucket confirmed. "What was captured
  is kept" was the Mac's working copy.
* **The "manifest published again" banner.** Its fix and its last sentences say the same of what is
  owed again, and no longer that "the publish uploads this machine's copy".
* **The login banner's two sentences.** It no longer says the run "kept everything it fetched", nor
  that "the publish after the login uploads this machine's copy".

(The CLI's own next step for a failed publish stage is the third hint; its tests are
`packages/debate_cli/tests/bucket_mode/test_bucket_mode_publish_hint_names_the_cloud_run.py`.)

Bucket mode is decided as `v1-e40-t22` decides it: the details' `bucket_run` for the banners. Local
mode keeps every word, and every record and details line a bucket-mode run writes is one the cloud
image (`v1.1.0-dev.164`) and the Mac's installed build (`v1.1.0-dev.200`) read. Every expected
sentence is written out by hand.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import jsonschema
import pytest
from tests.fixtures.caselist.build_synthetic_archives import build_snapshot_zips

from debate_core.application.ports.evidence_store import EvidenceObjectStore
from debate_core.application.ports.notifier import Notification
from debate_core.application.sync_runs import (
    BucketRunDetails,
    DriftFinding,
    StageDetails,
    StageEntry,
    SyncRunDetails,
    SyncRunOutcome,
    SyncRunRecord,
    notifications_for,
)
from debate_core.integrations.s3 import S3EvidenceObjectStore

from .test_caselist_sync_names_publish_only_per_caselist import bucket_objects, details_line, stored_schema
from .test_caselist_sync_names_the_cloud_cure_in_bucket_mode import BucketModeBracket, pull, record_line
from .test_inbox_retention import CASELIST, WEEK_1, WEEK_2, FakeSource, Installation
from .test_pull_stage_failure_codes import AWS_LOGIN, RefusingBucket, Watched, outage
from .test_sync_report_stage_keeps_what_it_found_and_its_kind import ScriptedComparison

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

    from debate_core.application.caselist.status_service import CaselistStatusService

pytestmark = pytest.mark.anyio

REPO_ROOT: Final = Path(__file__).resolve().parents[5]
CLOUD_RUNBOOK: Final = REPO_ROOT / "docs" / "runbooks" / "caselist-cloud-run.md"

WHERE: Final = "Run 20260916T060000Z (dev)"
LOGIN_TITLE: Final = "caselist publish waiting for an AWS login"
RETRIED: Final = "caselist pull failed: will be retried"
PUBLISHED_AGAIN_TITLE: Final = "caselist pull: publish a manifest again"

# ------------------------------------------------------------------------------------------------
# What each hint says, by hand
# ------------------------------------------------------------------------------------------------

THE_FAILED_PUBLISH_CURE_IN_THE_CLOUD: Final = (
    "the next cloud run takes up what this run did not publish, from the run state saved in the "
    'bucket: the weekly run, or one started by hand (caselist-cloud-run.md, "A failed publish stage"); '
    "never a publish from the operator's Mac"
)
THE_FAILED_PUBLISH_CURE_ON_THE_MAC: Final = "debate-research caselist pull --publish-pending"

THE_FAILED_PUBLISH_IN_THE_CLOUD: Final = (
    ": the publish stage failed on STORE_UNAVAILABLE. The next scheduled run should retry it: every "
    "failure here is one a later run may not meet. What the bucket confirmed is kept; the cloud run's "
    "working copy ends with its task."
)
"""The banner's message after `Run <id> (<environment>)`."""
THE_FAILED_PUBLISH_ON_THE_MAC: Final = (
    ": the publish stage failed on STORE_UNAVAILABLE. The next scheduled run should retry it: every "
    "failure here is one a later run may not meet. What was captured is kept."
)

THE_PUBLISHED_AGAIN_CURE_IN_THE_CLOUD: Final = (
    "the next cloud run takes up what is owed again, from the run state saved in the bucket: the "
    'weekly run, or one started by hand (caselist-cloud-run.md, "A manifest published again"); never a '
    "publish from the operator's Mac"
)
THE_PUBLISHED_AGAIN_CURE_ON_THE_MAC: Final = "debate-research caselist pull --publish-pending"

ONE_PUBLISHED_AGAIN_IN_THE_CLOUD: Final = (
    f"{WHERE}: the report stage found the bucket's manifest of hsld26 2026-09-01 differs from this "
    "machine's. The next cloud run takes it up from the run state saved in the bucket. Nothing here "
    "needs a person."
)
TWO_PUBLISHED_AGAIN_IN_THE_CLOUD: Final = (
    f"{WHERE}: the report stage found the bucket's manifests of hsld26 2026-09-01, hspolicy26 "
    "2026-09-01 differ from this machine's. The next cloud run takes them up from the run state saved "
    "in the bucket. Nothing here needs a person."
)
ONE_PUBLISHED_AGAIN_ON_THE_MAC: Final = (
    f"{WHERE}: the report stage found the bucket's manifest of hsld26 2026-09-01 differs from this "
    "machine's. The next scheduled run publishes it again: this machine rewrote the manifest after it "
    "was published, and the publish uploads this machine's copy. Nothing here needs a person."
)

THE_LOGIN_BANNERS_CLOUD_FIX: Final = (
    "the PM looks into the cloud run's task role, which gave the run no AWS session "
    '(caselist-cloud-run.md, "A run that found no AWS session"); never a login and a publish from the '
    "operator's Mac"
)
"""`v1-e40-t22`'s, unchanged."""
THE_LOGIN_BANNERS_LOCAL_FIX: Final = f"{AWS_LOGIN} && debate-research caselist pull --publish-pending"

THE_LOGIN_BANNER_OWED_AGAIN_IN_THE_CLOUD: Final = (
    f"{WHERE} was left without an AWS session, and its working copy ends with its task; 1 snapshot(s) "
    "and the run record wait to be published. The report stage's check that the bucket holds what this "
    "run published was cut short. Before the session expired, the bucket's manifest of testcl26 "
    "2026-09-01 was found to differ from this machine's; it is owed again."
)
THE_LOGIN_BANNER_OWED_AGAIN_ON_THE_MAC: Final = (
    f"{WHERE} kept everything it fetched; 1 snapshot(s) and the run record wait to be published. "
    "The report stage's check that the bucket holds what this run published was cut short; the next "
    "pull, or caselist pull --publish-pending after the login, makes it again. Before the session "
    "expired, the bucket's manifest of testcl26 2026-09-01 was found to differ from this machine's; it "
    "is owed again, and the publish after the login uploads this machine's copy."
)
THE_LOGIN_BANNER_TWO_OWED_IN_THE_CLOUD: Final = (
    f"{WHERE} was left without an AWS session, and its working copy ends with its task; 2 snapshot(s) "
    "and the run record wait to be published. Before the session expired, the bucket's manifests of "
    "hsld26 2026-09-01, hspolicy26 2026-09-01 were found to differ from this machine's; they are owed "
    "again."
)

POINTS_AT_THE_MAC: Final = (
    "--publish",
    "--publish-pending",
    "caselist pull",
    "aws sso login",
    "imports into",
    "this machine's copy",
    "kept everything it fetched",
    "What was captured is kept",
)
"""Nothing a bucket-mode banner may say: a Mac-side publish or login, and what only the Mac keeps."""


def points_at_the_mac(text: str) -> list[str]:
    return [word for word in POINTS_AT_THE_MAC if word in text]


# ------------------------------------------------------------------------------------------------
# Records and details by hand
# ------------------------------------------------------------------------------------------------

THE_CLOUD_RUN: Final = BucketRunDetails(
    bundle="not saved: 1 manifest(s) on this machine are not yet confirmed in the bucket, so the bucket "
    "keeps the previous bundle"
)
"""What a bucket-mode run's details hold of the lock and the state (`v1-e40-t04`): `None` in local mode."""


def a_retry_may_cure(codes: Sequence[str]) -> bool:
    return all(code in {"STORE_UNAVAILABLE", "STORE_ACCESS_DENIED"} for code in codes)


def a_record(
    *stages: tuple[str, str],
    pending_publish: tuple[str, ...] = (),
    outcome: SyncRunOutcome = SyncRunOutcome.INCOMPLETE,
) -> SyncRunRecord:
    moment = datetime(2026, 9, 16, 6, 0, tzinfo=UTC)
    return SyncRunRecord(
        run_id="20260916T060000Z",
        environment="dev",
        mode="run",
        started_at=moment,
        finished_at=moment,
        outcome=outcome,
        pending_publish=pending_publish,
        stages=tuple(StageEntry(stage=name, outcome=result) for name, result in stages),
    )


def details_of(*stages: StageDetails, bucket: bool, failure_codes: tuple[str, ...] = ()) -> SyncRunDetails:
    return SyncRunDetails(
        run_id="20260916T060000Z",
        stages=stages,
        failure_codes=failure_codes,
        bucket_run=THE_CLOUD_RUN if bucket else None,
    )


def manifest_drift(*caselists: str, error_codes: tuple[str, ...] = ("CASELIST_DRIFT",)) -> StageDetails:
    return StageDetails(
        stage="report",
        error_codes=error_codes,
        earlier_findings=() if error_codes else ("CASELIST_DRIFT",),
        drift=tuple(
            DriftFinding(caselist=caselist, snapshot="2026-09-01", kinds=("manifest",))
            for caselist in caselists
        ),
    )


def sent_for(
    record: SyncRunRecord, details: SyncRunDetails, *, credentials_expired: bool = False
) -> list[Notification]:
    return notifications_for(
        record,
        details,
        aws_login_command=AWS_LOGIN,
        credentials_expired=credentials_expired,
        may_succeed_on_retry=a_retry_may_cure,
    )


def titled(sent: Sequence[Notification], title: str) -> Notification:
    [one] = [one for one in sent if one.title == title]
    return one


PUBLISH_FAILED: Final = (("download", "completed"), ("import", "completed"), ("publish", "failed"))


def a_failed_publish(*, bucket: bool) -> Notification:
    record = a_record(
        *PUBLISH_FAILED, pending_publish=("testcl26 2026-09-01",), outcome=SyncRunOutcome.FAILED
    )
    details = details_of(
        StageDetails(stage="publish", error_codes=("STORE_UNAVAILABLE",)),
        bucket=bucket,
        failure_codes=("STORE_UNAVAILABLE",),
    )
    return titled(sent_for(record, details), RETRIED)


# ------------------------------------------------------------------------------------------------
# A failed publish stage's banner
# ------------------------------------------------------------------------------------------------


def test_a_bucket_mode_failed_publish_names_the_next_cloud_run_and_no_mac_side_publish() -> None:
    banner = a_failed_publish(bucket=True)

    assert banner.message == WHERE + THE_FAILED_PUBLISH_IN_THE_CLOUD
    assert banner.fix_command == THE_FAILED_PUBLISH_CURE_IN_THE_CLOUD
    assert points_at_the_mac(banner.text) == []


def test_a_local_mode_failed_publish_is_unchanged() -> None:
    banner = a_failed_publish(bucket=False)

    assert banner.message == WHERE + THE_FAILED_PUBLISH_ON_THE_MAC
    assert banner.fix_command == THE_FAILED_PUBLISH_CURE_ON_THE_MAC
    assert "cloud" not in banner.text


def test_a_bucket_mode_publish_that_failed_beside_another_stage_keeps_its_fix() -> None:
    """Only a failed publish alone named `--publish-pending`; a failed import beside it names the pull,
    which this task leaves as it is (the report's Follow-up work)."""
    record = a_record(
        ("download", "completed"), ("import", "failed"), ("publish", "failed"), outcome=SyncRunOutcome.FAILED
    )
    details = details_of(
        StageDetails(stage="import", error_codes=("STORE_UNAVAILABLE",)),
        StageDetails(stage="publish", error_codes=("STORE_UNAVAILABLE",)),
        bucket=True,
        failure_codes=("STORE_UNAVAILABLE",),
    )

    banner = titled(sent_for(record, details), RETRIED)

    assert banner.fix_command == "debate-research caselist pull"
    assert banner.message.endswith(" What was captured is kept.")


# ------------------------------------------------------------------------------------------------
# The "manifest published again" banner
# ------------------------------------------------------------------------------------------------

REPORT_FAILED: Final = (("publish", "completed"), ("report", "failed"))


@pytest.mark.parametrize(
    ("caselists", "message"),
    [
        (("hsld26",), ONE_PUBLISHED_AGAIN_IN_THE_CLOUD),
        (("hsld26", "hspolicy26"), TWO_PUBLISHED_AGAIN_IN_THE_CLOUD),
    ],
    ids=["one", "two"],
)
def test_a_bucket_mode_manifest_owed_again_is_taken_up_by_the_next_cloud_run(
    caselists: tuple[str, ...], message: str
) -> None:
    record = a_record(*REPORT_FAILED, pending_publish=tuple(f"{one} 2026-09-01" for one in caselists))

    [banner] = sent_for(record, details_of(manifest_drift(*caselists), bucket=True))

    assert banner.title == PUBLISHED_AGAIN_TITLE
    assert banner.message == message
    assert banner.fix_command == THE_PUBLISHED_AGAIN_CURE_IN_THE_CLOUD
    assert points_at_the_mac(banner.text) == []


def test_a_local_mode_manifest_owed_again_is_unchanged() -> None:
    record = a_record(*REPORT_FAILED, pending_publish=("hsld26 2026-09-01",))

    [banner] = sent_for(record, details_of(manifest_drift("hsld26"), bucket=False))

    assert banner.title == PUBLISHED_AGAIN_TITLE
    assert banner.message == ONE_PUBLISHED_AGAIN_ON_THE_MAC
    assert banner.fix_command == THE_PUBLISHED_AGAIN_CURE_ON_THE_MAC
    assert "cloud" not in banner.text


# ------------------------------------------------------------------------------------------------
# The login banner's two sentences
# ------------------------------------------------------------------------------------------------


def test_a_bucket_mode_login_banner_with_two_manifests_owed_again_says_neither_sentence() -> None:
    record = a_record(
        ("publish", "pending"),
        ("report", "pending"),
        pending_publish=("hsld26 2026-09-01", "hspolicy26 2026-09-01"),
        outcome=SyncRunOutcome.PUBLISH_PENDING,
    )
    details = details_of(manifest_drift("hsld26", "hspolicy26", error_codes=()), bucket=True)

    banner = titled(sent_for(record, details, credentials_expired=True), LOGIN_TITLE)

    assert banner.message == THE_LOGIN_BANNER_TWO_OWED_IN_THE_CLOUD
    assert banner.fix_command == THE_LOGIN_BANNERS_CLOUD_FIX
    assert points_at_the_mac(banner.text) == []


# ------------------------------------------------------------------------------------------------
# The same, through a run
# ------------------------------------------------------------------------------------------------


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


async def run(
    installation: Installation,
    *,
    bucket_mode: bool,
    weeks: Sequence[date] = (WEEK_1,),
    publish_to: EvidenceObjectStore | None = None,
    comparison: CaselistStatusService | None = None,
) -> Watched:
    """One weekly pull, in bucket mode as the composition root builds it, or in local mode."""
    service = installation.sync(
        FakeSource(installation.archives, weeks=list(weeks)),
        publish_to=publish_to,
        status=comparison,
        working_copy_outlives_the_run=not bucket_mode,
        bucket_mode=bucket_mode,
    )
    return await pull(installation, service, bracket=BucketModeBracket() if bucket_mode else None)


async def a_publish_the_bucket_refused(installation: Installation, *, bucket_mode: bool) -> Watched:
    return await run(installation, bucket_mode=bucket_mode, publish_to=RefusingBucket(outage()))


async def a_manifest_owed_again(installation: Installation, *, bucket_mode: bool) -> Watched:
    return await run(
        installation,
        bucket_mode=bucket_mode,
        weeks=(WEEK_1, WEEK_2),
        comparison=ScriptedComparison(installation, manifest_differs=(WEEK_1,)),
    )


async def a_manifest_owed_again_and_the_session_expired(
    installation: Installation, *, bucket_mode: bool
) -> Watched:
    return await run(
        installation,
        bucket_mode=bucket_mode,
        weeks=(WEEK_1, WEEK_2),
        comparison=ScriptedComparison(installation, manifest_differs=(WEEK_1,), expires_at=2),
    )


@pytest.mark.parametrize(
    ("bucket_mode", "message", "fix"),
    [
        (True, THE_FAILED_PUBLISH_IN_THE_CLOUD, THE_FAILED_PUBLISH_CURE_IN_THE_CLOUD),
        (False, THE_FAILED_PUBLISH_ON_THE_MAC, THE_FAILED_PUBLISH_CURE_ON_THE_MAC),
    ],
    ids=["bucket", "local"],
)
async def test_a_run_whose_publish_the_bucket_refused_gives_its_modes_banner(
    installation: Installation, bucket_mode: bool, message: str, fix: str
) -> None:
    watched = await a_publish_the_bucket_refused(installation, bucket_mode=bucket_mode)

    assert (details_line(installation)["bucket_run"] is not None) is bucket_mode, "the premise"
    banner = titled(watched.notifier.sent, RETRIED)
    assert banner.message == WHERE + message
    assert banner.fix_command == fix
    if bucket_mode:
        assert points_at_the_mac(banner.text) == []


async def test_a_bucket_mode_run_that_owes_a_manifest_again_names_the_next_cloud_run(
    installation: Installation,
) -> None:
    watched = await a_manifest_owed_again(installation, bucket_mode=True)

    banner = titled(watched.notifier.sent, PUBLISHED_AGAIN_TITLE)
    assert banner.message == (
        f"{WHERE}: the report stage found the bucket's manifest of {CASELIST} 2026-09-01 differs from this "
        "machine's. The next cloud run takes it up from the run state saved in the bucket. Nothing here "
        "needs a person."
    )
    assert banner.fix_command == THE_PUBLISHED_AGAIN_CURE_IN_THE_CLOUD
    assert points_at_the_mac(banner.text) == []


@pytest.mark.parametrize(
    ("bucket_mode", "message", "fix"),
    [
        (True, THE_LOGIN_BANNER_OWED_AGAIN_IN_THE_CLOUD, THE_LOGIN_BANNERS_CLOUD_FIX),
        (False, THE_LOGIN_BANNER_OWED_AGAIN_ON_THE_MAC, THE_LOGIN_BANNERS_LOCAL_FIX),
    ],
    ids=["bucket", "local"],
)
async def test_a_login_banner_with_a_manifest_owed_again_gives_its_modes_sentences(
    installation: Installation, bucket_mode: bool, message: str, fix: str
) -> None:
    """Week one's comparison finds its manifest differs; the session expires at week two's."""
    watched = await a_manifest_owed_again_and_the_session_expired(installation, bucket_mode=bucket_mode)

    banner = titled(watched.notifier.sent, LOGIN_TITLE)
    assert banner.message == message
    assert banner.fix_command == fix
    if bucket_mode:
        assert points_at_the_mac(banner.text) == []
    else:
        assert "cloud" not in banner.text


# ------------------------------------------------------------------------------------------------
# The runbook sections the hints name are there, and keep the rule
# ------------------------------------------------------------------------------------------------


def section(heading: str) -> str:
    text = CLOUD_RUNBOOK.read_text(encoding="utf-8")
    assert f"\n## {heading}\n" in text, f"the section a hint names: {heading}"
    return " ".join(text.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0].split())


def test_the_runbook_sections_the_hints_name_are_there_and_keep_the_rule() -> None:
    failed_publish = section("A failed publish stage")
    assert f"> Fix: {THE_FAILED_PUBLISH_CURE_IN_THE_CLOUD}" in failed_publish
    assert "Never run `caselist pull --publish-pending` on the operator's Mac" in failed_publish

    published_again = section("A manifest published again")
    assert f"> Fix: {THE_PUBLISHED_AGAIN_CURE_IN_THE_CLOUD}" in published_again
    assert "Never run `caselist pull --publish-pending` on the operator's Mac" in published_again

    no_session = section("A run that found no AWS session")
    assert "was left without an AWS session, and its working copy ends with its task" in no_session


def test_the_runbook_says_the_newer_table_cure_without_an_import() -> None:
    """The PM's amendment of 2026-11-01: since `v1-e40-t08` the next run parses what is owed whatever
    it imports, so the paragraph that says the newer-table hint drops "that imports into" with it."""
    new_image = section("A new image, later")
    assert "that imports into" not in new_image
    assert (
        "says the next cloud run on an image whose fingerprint version is the table's or later rebuilds "
        "and publishes it"
    ) in new_image


# ------------------------------------------------------------------------------------------------
# The earlier builds read every record and details line these runs write
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scenario",
    [a_publish_the_bucket_refused, a_manifest_owed_again, a_manifest_owed_again_and_the_session_expired],
    ids=["failed_publish", "published_again", "login_owed_again"],
)
async def test_the_cloud_image_and_the_macs_build_read_every_record_and_details_line_these_runs_write(
    installation: Installation, s3_client: S3Client, evidence_bucket: str, scenario: Any
) -> None:
    """Against what those builds validate with, each printed by its own code (`stored_run_records/`),
    as `v1-e40-t22`'s are. A run that lost its session publishes neither, and leaves them local."""
    watched = await scenario(installation, bucket_mode=True)

    record = record_line(installation)
    details = details_line(installation)
    if watched.pulled.record is not None and watched.pulled.record.outcome != SyncRunOutcome.PUBLISH_PENDING:
        assert bucket_objects(s3_client, evidence_bucket, "reports/sync-runs/") == [record]
        assert bucket_objects(s3_client, evidence_bucket, "reports/sync-run-details/") == [details]
    jsonschema.validate(record, stored_schema("record_schema_of_the_cloud_image.json"))
    assert all(set(one) == {"stage", "outcome", "reason"} for one in record["stages"])
    for name in (
        "details_schema_before_parsed_stores_owed.json",
        "details_schema_of_the_macs_installed_build.json",
    ):
        jsonschema.validate(details, stored_schema(name))
    assert set(details) <= set(
        stored_schema("details_schema_of_the_macs_installed_build.json")["properties"]
    ), "no details key the Mac's installed build does not define"
