"""A failed stage of a pull says what it failed on, in the CLI's own error codes (`v1-e34-t13`).

`caselist pull` folds a failure inside a stage into a failed `StageRecord`. The record used to carry
a sentence and nothing else, so the command could not tell a store that did not answer from a
refused archive without parsing English, and exited `1` for both (`v1-e01-t20`, Deviation 1). And
the publish and report stages read every `StoreAccessDenied` as an expired login: publish pending,
exit `0`, and a notification naming `aws sso login`, which fixes neither a permission on this
machine's data directory nor a missing grant (Deviation 2).

A failed stage now records the error code of each failure, the code `debate_cli.exit_codes.
error_code_for` gives the same exception; the command decides its exit from them. Only an expired
session is "pending".

Everything is real except the OpenCaselist source and the one thing each test breaks: the importers,
the manifests, the publisher and the status comparison, against moto, in the installation
`test_inbox_retention.py` builds. Every expected code, outcome and count is written by hand from
what the test sets up (working agreement 6).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from tests.fixtures.caselist.build_synthetic_archives import build_snapshot_zips
from tests.fixtures.caselist.interruptible_bucket import ScriptedBucket
from tests.fixtures.caselist.publish_expectations import expected_publish, expected_source_key
from tests.fixtures.permissions import needs_permissions, refused

from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.caselist_sync import (
    PENDING_WORK_FILENAME,
    RUN_SUMMARY_SCHEMA_VERSION,
    CaselistSyncService,
    PendingSnapshot,
    PendingWork,
    PulledRun,
    RunSummary,
    SyncStage,
    run_pull,
)
from debate_core.application.errors import (
    ArchiveTooLarge,
    DomainError,
    ProviderRateLimited,
    ProviderUnavailable,
    StoreAccessDenied,
    StoreCredentialsExpired,
    StoreUnavailable,
)
from debate_core.application.ports.caselist_source import (
    ArchiveListing,
    ArchiveUnavailable,
    CaselistAuthExpired,
    DownloadedFile,
    DownloadIntegrityError,
    OpenEvFile,
    openev_inbox_name,
)
from debate_core.application.ports.evidence_store import ObjectInfo, ObjectKey
from debate_core.application.ports.notifier import RecordingNotifier
from debate_core.application.ports.suppression import SuppressionEntry
from debate_core.application.sync_runs import (
    SYNC_RUN_LOG_FILENAME,
    SyncRunLog,
    SyncRunMonitor,
    SyncRunOutcome,
)
from debate_core.integrations.local.macos_notifier import MacOsNotifier
from debate_core.integrations.local.suppression_list import local_suppression_list_file
from debate_core.integrations.s3 import S3EvidenceObjectStore

from . import test_inbox_retention as inbox_retention
from .test_inbox_retention import (
    CASELIST,
    ESTUARY,
    ESTUARY_BODY,
    WEEK_1,
    WEEK_2,
    WEEK_3,
    ExpiredBucket,
    FakeSource,
    Installation,
    backlog,
    weekly_name,
)

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

AWS_LOGIN = "aws sso login --profile debate-dev-evidence"
BUCKET_KEY = "s3://debate-test-evidence-moto/manifests/testcl26/"

PROBE = "Zqxprobe"
"""In a camp file's title and so its inbox name, as in `test_summary_names_no_camp_file.py`."""

PROBED = OpenEvFile(
    openev_id=777,
    path=f"openev/2026/{PROBE} Institute/{PROBE} Estuary Solvency Advocate.docx",
    filename=f"{PROBE} Estuary Solvency Advocate.docx",
    year=2026,
    tags=("policy",),
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


@pytest.fixture
def empty_bucket(s3_client: S3Client) -> S3EvidenceObjectStore:
    """A second bucket in the same moto account, holding nothing."""
    s3_client.create_bucket(Bucket="debate-test-evidence-moto-empty")
    return S3EvidenceObjectStore(bucket="debate-test-evidence-moto-empty", client=s3_client)


# ------------------------------------------------------------------------------------------------
# What goes wrong, one thing at a time
# ------------------------------------------------------------------------------------------------


class RefusingBucket:
    """An evidence bucket every call to which fails the same way."""

    def __init__(self, failure: DomainError) -> None:
        self._failure = failure

    async def list_objects(self, prefix: str) -> tuple[ObjectInfo, ...]:
        raise self._failure

    async def head(self, key: ObjectKey) -> ObjectInfo:
        raise self._failure

    async def put_file(self, key: ObjectKey, source: Path) -> ObjectInfo:
        raise self._failure

    async def get_file(self, key: ObjectKey, destination: Path) -> ObjectInfo:
        raise self._failure


def outage() -> StoreUnavailable:
    """S3 throttling: the store did not answer."""
    return StoreUnavailable("ListObjectsV2", BUCKET_KEY, "SlowDown")


def missing_grant() -> StoreAccessDenied:
    """What the S3 adapter raises for an `AccessDenied` on a key: valid credentials, no grant."""
    return StoreAccessDenied("ListObjectsV2", BUCKET_KEY)


class UnansweringSuppressionList:
    """The suppression list whose bucket copy does not answer: what stops an import closed."""

    async def entries(self) -> tuple[SuppressionEntry, ...]:
        raise StoreUnavailable("GetObject", "s3://debate-test-evidence-moto/manifests/_suppression/", "503")

    async def append(self, entries: Sequence[SuppressionEntry]) -> None:  # pragma: no cover - never written
        raise AssertionError("a pull never writes the suppression list")


class SourceThatFails(FakeSource):
    """OpenCaselist failing one archive's download, or every camp file's, the way a test says."""

    def __init__(
        self,
        *args: object,
        archive_failures: dict[str, Exception] | None = None,
        openev_failure: Exception | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.archive_failures = archive_failures or {}
        self.openev_failure = openev_failure

    async def download_archive(self, archive: ArchiveListing, inbox: Path) -> DownloadedFile:
        failure = self.archive_failures.get(archive.name)
        if failure is not None:
            raise failure
        return await super().download_archive(archive, inbox)

    async def download_openev(self, file: OpenEvFile, inbox: Path) -> DownloadedFile:
        if self.openev_failure is not None:
            raise self.openev_failure
        return await super().download_openev(file, inbox)


@dataclass
class Watched:
    """One monitored pull, and what it notified."""

    pulled: PulledRun
    notifier: RecordingNotifier

    @property
    def summary(self) -> RunSummary:
        return self.pulled.summary

    @property
    def notified(self) -> str:
        """Every notification as the macOS notifier would post it, one string to search."""
        notifier = MacOsNotifier(executable="osascript")
        return "\n".join(" ".join(notifier.command_for(one)) for one in self.notifier.sent)


async def pull(
    installation: Installation, service: CaselistSyncService, *, publish_pending: bool = False
) -> Watched:
    """`caselist pull` as the command runs it: `run_pull` inside a real run monitor."""
    notifier = RecordingNotifier()
    monitor = SyncRunMonitor(
        state_dir=installation.data_dir,
        environment="dev",
        notifier=notifier,
        remote=installation.bucket,
        aws_login_command=AWS_LOGIN,
    )
    pulled = await run_pull(
        lambda: service,
        [] if publish_pending else [CASELIST],
        dry_run=False,
        publish_pending=publish_pending,
        monitor=lambda: monitor,
        progress=lambda _: None,
    )
    return Watched(pulled=pulled, notifier=notifier)


def stages_of(summary: RunSummary) -> list[dict[str, object]]:
    """Every stage as `caselist pull --json` and the run-summary file carry it."""
    return cast("list[dict[str, object]]", summary.as_json()["stages"])


def stage(summary: RunSummary, name: SyncStage) -> dict[str, object]:
    """One stage as `caselist pull --json` and the run-summary file carry it."""
    [found] = [one for one in stages_of(summary) if one["stage"] == str(name)]
    return found


def owed(installation: Installation) -> list[str]:
    """The snapshots the pending-work file says this machine still has to publish."""
    pending = PendingWork(installation.data_dir / PENDING_WORK_FILENAME).read()
    return [f"{one.caselist} {one.snapshot}" for one in pending]


def assert_names_nothing_of_this_machine(summary: RunSummary, installation: Installation) -> None:
    """No stage's reason, error codes or hint holds a path, a camp title or an inbox file name."""
    forbidden = {
        "the data directory's path": str(installation.data_dir),
        "the temporary directory's path": str(installation.data_dir.parent),
        "the home directory's path": str(Path.home()),
        "a camp file's title": PROBE,
        "a camp download's inbox name": openev_inbox_name(PROBED),
        "a camp download's inbox name (another)": openev_inbox_name(ESTUARY),
    }
    for one in stages_of(summary):
        text = json.dumps([one["reason"], one.get("error_codes"), one.get("hint")])
        found = sorted(what for what, value in forbidden.items() if value.casefold() in text.casefold())
        assert not found, f"the {one['stage']} stage names {found}: {text}"


# ------------------------------------------------------------------------------------------------
# ac1: a store that did not answer, in import and in publish
# ------------------------------------------------------------------------------------------------


async def test_an_import_stopped_by_a_store_that_did_not_answer_records_store_unavailable(
    installation: Installation,
) -> None:
    """The one archive is fetched and its import meets a suppression list the bucket does not serve."""
    installation.suppression = UnansweringSuppressionList()
    source = FakeSource(installation.archives, weeks=[WEEK_1])

    summary = await installation.sync(source).run([CASELIST])

    imported = stage(summary, SyncStage.IMPORT)
    assert imported["outcome"] == "failed"
    assert imported.get("error_codes") == ["STORE_UNAVAILABLE"]
    assert imported.get("hint") is None
    assert summary.failure_codes == ("STORE_UNAVAILABLE",)
    assert not summary.succeeded
    assert_names_nothing_of_this_machine(summary, installation)


async def test_a_publish_the_bucket_did_not_answer_fails_the_stage_and_the_next_run_publishes(
    installation: Installation,
) -> None:
    """The bucket's listing answers 503. The stage fails on that alone, the snapshot stays owed, and
    the following run, with the bucket back, publishes it without importing anything again."""
    source = FakeSource(installation.archives, weeks=[WEEK_1])

    summary = await installation.sync(source, publish_to=RefusingBucket(outage())).run([CASELIST])

    published = stage(summary, SyncStage.PUBLISH)
    assert published["outcome"] == "failed"
    assert published.get("error_codes") == ["STORE_UNAVAILABLE"]
    assert summary.failure_codes == ("STORE_UNAVAILABLE",)
    assert summary.snapshots_imported == ("testcl26 2026-09-01",)
    assert summary.pending_publish == ("testcl26 2026-09-01",)
    assert owed(installation) == ["testcl26 2026-09-01"]
    assert stage(summary, SyncStage.REPORT)["outcome"] == "skipped", "nothing was published to confirm"
    assert_names_nothing_of_this_machine(summary, installation)

    again = await installation.sync(source).run([CASELIST])

    assert again.succeeded, again.stages
    assert source.archive_fetches == [weekly_name(WEEK_1)], "the week is fetched once, not again"
    assert stage(again, SyncStage.PUBLISH)["outcome"] == "completed"
    assert owed(installation) == []


def every_upload_answers_503(key: ObjectKey, _: int) -> None:
    raise StoreUnavailable("PutObject", key, "simulated 503 SlowDown")


WEEK_1_SOURCES = [
    week["sources"] for week in expected_publish()["snapshots"] if week["snapshot"] == "2026-09-01"
][0]
"""The synthetic documents week one stores, by the fixture's names (`expected_publish.json`)."""


async def test_uploads_the_bucket_did_not_take_fail_publish_on_the_store_and_wait_for_no_login(
    installation: Installation,
) -> None:
    """The bucket lists and answers, and every upload gets a 503. The publisher carries on past each
    one, so the stage is failed by its sources, every one of them on the store. The week stays owed.

    Until this task the report stage then read "something is owed" as "waiting for a login", and
    the run notified the operator to `aws sso login`."""
    source = FakeSource(installation.archives, weeks=[WEEK_1])
    assert isinstance(installation.bucket, S3EvidenceObjectStore)
    stuttering = ScriptedBucket(installation.bucket, every_upload_answers_503)

    watched = await pull(installation, installation.sync(source, publish_to=stuttering))

    published = stage(watched.summary, SyncStage.PUBLISH)
    assert published["outcome"] == "failed"
    assert published.get("error_codes") == ["STORE_UNAVAILABLE"]
    assert str(published["reason"]).startswith("0 object(s) published; incomplete: testcl26 2026-09-01: ")
    assert watched.summary.failure_codes == ("STORE_UNAVAILABLE",)
    assert owed(installation) == ["testcl26 2026-09-01"]
    assert stage(watched.summary, SyncStage.REPORT)["outcome"] == "skipped"
    assert [one.title for one in watched.notifier.sent] == ["caselist pull failed"]
    assert "aws sso login" not in watched.notified
    assert_names_nothing_of_this_machine(watched.summary, installation)


async def test_other_bytes_under_a_sources_key_fail_publish_on_a_verdict(
    installation: Installation, s3_client: S3Client, evidence_bucket: str
) -> None:
    """The bucket already holds something else under one of week one's keys. Publishing again gives
    the same answer, so the code is the mismatch's, never the store's."""
    s3_client.put_object(
        Bucket=evidence_bucket, Key=expected_source_key(WEEK_1_SOURCES[0]), Body=b"other bytes"
    )
    source = FakeSource(installation.archives, weeks=[WEEK_1])

    summary = await installation.sync(source).run([CASELIST])

    published = stage(summary, SyncStage.PUBLISH)
    assert published["outcome"] == "failed"
    assert published.get("error_codes") == ["CHECKSUM_MISMATCH"]
    assert summary.failure_codes == ("CHECKSUM_MISMATCH",)
    assert owed(installation) == ["testcl26 2026-09-01"]


async def test_a_mismatch_among_uploads_the_bucket_did_not_take_records_both(
    installation: Installation, s3_client: S3Client, evidence_bucket: str
) -> None:
    """One source's key holds other bytes and every other upload gets a 503: a verdict beside the
    outage, in one publish. Both codes are recorded, so the outage cannot hide the mismatch."""
    s3_client.put_object(
        Bucket=evidence_bucket, Key=expected_source_key(WEEK_1_SOURCES[0]), Body=b"other bytes"
    )
    source = FakeSource(installation.archives, weeks=[WEEK_1])
    assert isinstance(installation.bucket, S3EvidenceObjectStore)
    stuttering = ScriptedBucket(installation.bucket, every_upload_answers_503)

    summary = await installation.sync(source, publish_to=stuttering).run([CASELIST])

    published = stage(summary, SyncStage.PUBLISH)
    assert published["outcome"] == "failed"
    assert sorted(cast("list[str]", published.get("error_codes"))) == [
        "CHECKSUM_MISMATCH",
        "STORE_UNAVAILABLE",
    ]
    assert sorted(summary.failure_codes) == ["CHECKSUM_MISMATCH", "STORE_UNAVAILABLE"]


async def test_an_owed_snapshot_with_no_manifest_fails_publish_on_a_verdict(
    installation: Installation,
) -> None:
    """The pending-work file names a week this machine holds no manifest for. No later run finds one."""
    installation.data_dir.mkdir(parents=True)
    PendingWork(installation.data_dir / PENDING_WORK_FILENAME).write(
        [PendingSnapshot(CASELIST, "2026-08-25")]
    )
    source = FakeSource(installation.archives)

    summary = await installation.sync(source).publish_pending()

    published = stage(summary, SyncStage.PUBLISH)
    assert published["outcome"] == "failed"
    assert published["reason"] == "0 object(s) published; incomplete: testcl26 2026-08-25: no local manifest"
    assert published.get("error_codes") == ["NOTHING_TO_PUBLISH"]
    assert summary.failure_codes == ("NOTHING_TO_PUBLISH",)


# ------------------------------------------------------------------------------------------------
# ac1: OpenCaselist downloads
# ------------------------------------------------------------------------------------------------

WEEK_2_ARCHIVE = weekly_name(WEEK_2)

RETRYABLE_DOWNLOAD_FAILURES = [
    pytest.param(
        ProviderUnavailable("opencaselist", f"download {WEEK_2_ARCHIVE} failed: HTTP 503 (after 4 attempts)"),
        "PROVIDER_UNAVAILABLE",
        id="a 5xx that outlasted the retries",
    ),
    pytest.param(
        ProviderUnavailable(
            "opencaselist", f"download {WEEK_2_ARCHIVE} failed: ReadTimeout (after 4 attempts)"
        ),
        "PROVIDER_UNAVAILABLE",
        id="a timeout",
    ),
    pytest.param(
        ProviderRateLimited(
            "opencaselist",
            f"download {WEEK_2_ARCHIVE} was rate limited (after 4 attempts)",
            retry_after_seconds=30.0,
        ),
        "PROVIDER_RATE_LIMITED",
        id="a 429 that is not the daily cap",
    ),
]

DETERMINISTIC_DOWNLOAD_FAILURES = [
    pytest.param(ArchiveUnavailable(WEEK_2_ARCHIVE, 404), "ARCHIVE_UNAVAILABLE", id="a refused archive"),
    pytest.param(
        ArchiveTooLarge(measured="archive", actual_bytes=9, limit_bytes=8, source=WEEK_2_ARCHIVE),
        "ARCHIVE_TOO_LARGE",
        id="over the size ceiling",
    ),
    pytest.param(
        CaselistAuthExpired(401, f"download {WEEK_2_ARCHIVE}"),
        "CASELIST_AUTH_EXPIRED",
        id="a 401, never retried by policy",
    ),
    pytest.param(
        DownloadIntegrityError(WEEK_2_ARCHIVE, "9 bytes arrived of 12 declared"),
        "DOWNLOAD_INTEGRITY_ERROR",
        id="a download that did not arrive whole",
    ),
]


@pytest.mark.parametrize(
    ("failure", "code"), [*RETRYABLE_DOWNLOAD_FAILURES, *DETERMINISTIC_DOWNLOAD_FAILURES]
)
async def test_a_failed_download_records_the_code_of_what_stopped_it(
    installation: Installation, failure: Exception, code: str
) -> None:
    """Week one arrives and is imported and published; week two's download fails. The download
    stage records that failure's own code and nothing else."""
    source = SourceThatFails(
        installation.archives, weeks=[WEEK_1, WEEK_2], archive_failures={WEEK_2_ARCHIVE: failure}
    )

    summary = await installation.sync(source).run([CASELIST])

    downloaded = stage(summary, SyncStage.DOWNLOAD)
    assert downloaded["outcome"] == "failed"
    assert downloaded.get("error_codes") == [code]
    assert summary.failure_codes == (code,)
    assert summary.snapshots_imported == ("testcl26 2026-09-01",)
    assert stage(summary, SyncStage.PUBLISH)["outcome"] == "completed"
    assert_names_nothing_of_this_machine(summary, installation)


async def test_the_daily_cap_on_an_archive_is_a_deferral_with_no_error_code(
    installation: Installation,
) -> None:
    """Unchanged: a `Retry-After` of a day defers the week, and the stage completes."""
    daily = ProviderRateLimited("opencaselist", "the daily limit was reached", retry_after_seconds=86_400.0)
    source = SourceThatFails(
        installation.archives, weeks=[WEEK_1, WEEK_2], archive_failures={WEEK_2_ARCHIVE: daily}
    )

    summary = await installation.sync(source).run([CASELIST])

    downloaded = stage(summary, SyncStage.DOWNLOAD)
    assert downloaded["outcome"] == "completed"
    assert downloaded.get("error_codes") == []
    assert summary.succeeded
    assert summary.failure_codes == ()


async def test_the_daily_cap_on_a_camp_download_is_never_recorded_as_a_retryable_rate_limit(
    installation: Installation,
) -> None:
    """A camp download has no deferral to fall back on, so the day's verdict fails the stage, under a
    code of its own: the rate-limit code is the one a re-run may cure, and this is not that."""
    daily = ProviderRateLimited(
        "opencaselist", "download OpenEv file 512 was rate limited", retry_after_seconds=86_400.0
    )
    source = SourceThatFails(installation.archives, openev=[(ESTUARY, ESTUARY_BODY)], openev_failure=daily)

    summary = await installation.sync(source).run([CASELIST])

    downloaded = stage(summary, SyncStage.DOWNLOAD)
    assert downloaded["outcome"] == "failed"
    assert downloaded.get("error_codes") == ["DAILY_DOWNLOAD_LIMIT_REACHED"]
    assert summary.failure_codes == ("DAILY_DOWNLOAD_LIMIT_REACHED",)
    assert_names_nothing_of_this_machine(summary, installation)


async def test_an_error_nobody_modelled_is_recorded_as_the_cli_would_report_it(
    installation: Installation,
) -> None:
    """An `OSError` writing a camp download fails the stage (`v1-e34-t12`). It has no code of its
    own, so it is recorded under the one the CLI gives any exception it does not model."""
    refusal = PermissionError(13, "Permission denied", str(installation.inbox / openev_inbox_name(PROBED)))
    source = SourceThatFails(installation.archives, openev=[(PROBED, ESTUARY_BODY)], openev_failure=refusal)

    summary = await installation.sync(source).run([CASELIST])

    downloaded = stage(summary, SyncStage.DOWNLOAD)
    assert downloaded["outcome"] == "failed"
    assert downloaded["reason"] == "0 fetched, then: openev-777: PermissionError"
    assert downloaded.get("error_codes") == ["INTERNAL_ERROR"]
    assert_names_nothing_of_this_machine(summary, installation)


# ------------------------------------------------------------------------------------------------
# ac1: deterministic failures, alone and beside a retryable one
# ------------------------------------------------------------------------------------------------


async def test_an_archive_the_reader_refuses_records_the_refusal_not_a_store_failure(
    installation: Installation,
) -> None:
    source = FakeSource(installation.archives, weeks=[WEEK_1])

    summary = await installation.sync(source, unreadable=[weekly_name(WEEK_1)]).run([CASELIST])

    imported = stage(summary, SyncStage.IMPORT)
    assert imported["outcome"] == "failed"
    assert imported.get("error_codes") == ["UNREADABLE_ARCHIVE"]
    assert summary.failure_codes == ("UNREADABLE_ARCHIVE",)


async def test_a_retryable_and_a_deterministic_failure_in_two_stages_are_both_recorded(
    installation: Installation,
) -> None:
    """Week three's download answers 503 and week one's zip cannot be read. Neither hides the other."""
    unavailable = ProviderUnavailable("opencaselist", "download failed: HTTP 503 (after 4 attempts)")
    source = SourceThatFails(
        installation.archives,
        weeks=[WEEK_1, WEEK_2, WEEK_3],
        archive_failures={weekly_name(WEEK_3): unavailable},
    )

    summary = await installation.sync(source, unreadable=[weekly_name(WEEK_1)]).run([CASELIST])

    assert stage(summary, SyncStage.DOWNLOAD).get("error_codes") == ["PROVIDER_UNAVAILABLE"]
    assert stage(summary, SyncStage.IMPORT).get("error_codes") == ["UNREADABLE_ARCHIVE"]
    assert summary.failure_codes == ("PROVIDER_UNAVAILABLE", "UNREADABLE_ARCHIVE")


async def test_a_retryable_and_a_deterministic_failure_in_one_stage_are_both_recorded(
    installation: Installation,
) -> None:
    """The weekly's zip cannot be read, and the camp file's import meets a suppression list the
    bucket does not serve. The import stage records both, archives first as it imports them."""
    installation.suppression = UnansweringSuppressionList()
    source = FakeSource(installation.archives, weeks=[WEEK_1], openev=[(ESTUARY, ESTUARY_BODY)])

    summary = await installation.sync(source, unreadable=[weekly_name(WEEK_1)]).run([CASELIST])

    imported = stage(summary, SyncStage.IMPORT)
    assert imported["outcome"] == "failed"
    assert imported.get("error_codes") == ["UNREADABLE_ARCHIVE", "STORE_UNAVAILABLE"]
    assert summary.failure_codes == ("UNREADABLE_ARCHIVE", "STORE_UNAVAILABLE")
    assert_names_nothing_of_this_machine(summary, installation)


# ------------------------------------------------------------------------------------------------
# ac2: a refusal is not an expired login
# ------------------------------------------------------------------------------------------------


@needs_permissions
async def test_a_local_refusal_in_publish_fails_the_stage_and_names_the_data_directory(
    installation: Installation,
) -> None:
    """The week is imported while the session is expired, so its publish is owed. When the publish
    is retried, this machine's blob directory cannot be read. That is a failed publish whose fix is
    a permission on this machine, never a publish waiting for an AWS login."""
    source = FakeSource(installation.archives, weeks=[WEEK_1])
    first = await pull(installation, installation.sync(source, publish_to=ExpiredBucket()))
    assert stage(first.summary, SyncStage.PUBLISH)["outcome"] == "pending"

    with refused(installation.data_dir / "blobs"):
        retried = await pull(installation, installation.sync(source), publish_pending=True)

    published = stage(retried.summary, SyncStage.PUBLISH)
    assert published["outcome"] == "failed"
    assert published.get("error_codes") == ["STORE_ACCESS_DENIED"]
    hint = published.get("hint")
    assert isinstance(hint, str)
    assert "the blob directory" in hint
    assert "storage.data_dir" in hint
    assert retried.summary.failure_codes == ("STORE_ACCESS_DENIED",)
    assert owed(installation) == ["testcl26 2026-09-01"], "still owed, for the run after the fix"
    assert stage(retried.summary, SyncStage.REPORT)["outcome"] == "skipped"
    assert [one.title for one in retried.notifier.sent] == ["caselist pull failed"]
    assert "aws sso login" not in json.dumps(stages_of(retried.summary))
    assert "aws sso login" not in retried.notified
    assert_names_nothing_of_this_machine(retried.summary, installation)


async def test_a_missing_grant_in_report_fails_the_stage_and_names_the_grant(
    installation: Installation,
) -> None:
    """Everything publishes; the comparison that confirms it is refused by the bucket. The report
    stage fails with the fix that applies, and nothing waits for a login."""
    source = FakeSource(installation.archives, weeks=[WEEK_1])

    watched = await pull(
        installation, installation.sync(source, compare_with=RefusingBucket(missing_grant()))
    )

    assert stage(watched.summary, SyncStage.PUBLISH)["outcome"] == "completed"
    reported = stage(watched.summary, SyncStage.REPORT)
    assert reported["outcome"] == "failed"
    assert reported.get("error_codes") == ["STORE_ACCESS_DENIED"]
    hint = reported.get("hint")
    assert isinstance(hint, str)
    assert "grant" in hint
    assert "docs/runbooks/evidence-store.md" in hint
    assert "storage.data_dir" not in hint
    # Report is not a stage that puts bytes anywhere, so it decides no exit code.
    assert watched.summary.succeeded
    assert watched.summary.failure_codes == ()
    assert watched.pulled.record is not None
    assert watched.pulled.record.outcome is SyncRunOutcome.INCOMPLETE
    assert [one.title for one in watched.notifier.sent] == ["caselist pull finished with a failed stage"]
    assert "aws sso login" not in json.dumps(stages_of(watched.summary))
    assert "aws sso login" not in watched.notified
    assert installation.inbox_names() == {weekly_name(WEEK_1)}, "nothing unconfirmed leaves the inbox"
    assert_names_nothing_of_this_machine(watched.summary, installation)


async def test_a_missing_grant_in_publish_fails_the_stage_and_names_the_grant(
    installation: Installation,
) -> None:
    source = FakeSource(installation.archives, weeks=[WEEK_1])

    watched = await pull(installation, installation.sync(source, publish_to=RefusingBucket(missing_grant())))

    published = stage(watched.summary, SyncStage.PUBLISH)
    assert published["outcome"] == "failed"
    assert published.get("error_codes") == ["STORE_ACCESS_DENIED"]
    hint = published.get("hint")
    assert isinstance(hint, str)
    assert "grant" in hint
    assert "docs/runbooks/evidence-store.md" in hint
    assert watched.summary.failure_codes == ("STORE_ACCESS_DENIED",)
    assert owed(installation) == ["testcl26 2026-09-01"]
    assert stage(watched.summary, SyncStage.REPORT)["outcome"] == "skipped"
    assert [one.title for one in watched.notifier.sent] == ["caselist pull failed"]
    assert "aws sso login" not in json.dumps(stages_of(watched.summary))
    assert "aws sso login" not in watched.notified
    assert_names_nothing_of_this_machine(watched.summary, installation)


async def test_an_expired_session_still_leaves_publish_pending_and_names_the_login(
    installation: Installation,
) -> None:
    """Unchanged, and the only thing "pending" means: the session expired, log in and drain it."""
    source = FakeSource(installation.archives, weeks=[WEEK_1])
    service = installation.sync(source, publish_to=ExpiredBucket(), compare_with=ExpiredBucket())

    watched = await pull(installation, service)

    published = stage(watched.summary, SyncStage.PUBLISH)
    assert published["outcome"] == "pending"
    assert published.get("error_codes") == []
    assert AWS_LOGIN in str(published["reason"])
    assert stage(watched.summary, SyncStage.REPORT)["outcome"] == "pending"
    assert watched.summary.succeeded
    assert watched.summary.failure_codes == ()
    assert owed(installation) == ["testcl26 2026-09-01"]
    [notification] = watched.notifier.sent
    assert notification.title == "caselist publish waiting for an AWS login"
    assert notification.fix_command == f"{AWS_LOGIN} && debate-research caselist pull --publish-pending"


async def test_a_session_that_expires_at_the_report_stage_still_pends_it(
    installation: Installation,
) -> None:
    source = FakeSource(installation.archives, weeks=[WEEK_1])
    expired = RefusingBucket(StoreCredentialsExpired(hint=AWS_LOGIN))

    watched = await pull(installation, installation.sync(source, compare_with=expired))

    reported = stage(watched.summary, SyncStage.REPORT)
    assert reported["outcome"] == "pending"
    assert reported.get("error_codes") == []
    assert [one.title for one in watched.notifier.sent] == ["caselist publish waiting for an AWS login"]


async def test_a_bucket_that_does_not_answer_the_comparison_fails_report_and_is_not_pending(
    installation: Installation,
) -> None:
    """Published, and the comparison meets a 503. Report fails on the store; nothing waits for a
    login, and the report stage still decides nothing about the run's exit code."""
    source = FakeSource(installation.archives, weeks=[WEEK_1])

    watched = await pull(installation, installation.sync(source, compare_with=RefusingBucket(outage())))

    reported = stage(watched.summary, SyncStage.REPORT)
    assert reported["outcome"] == "failed"
    assert reported.get("error_codes") == ["STORE_UNAVAILABLE"]
    assert reported.get("hint") is None
    assert watched.summary.succeeded
    assert watched.summary.failure_codes == ()
    assert "aws sso login" not in watched.notified


async def test_a_snapshot_the_bucket_does_not_hold_in_sync_fails_report_as_drift(
    installation: Installation, empty_bucket: S3EvidenceObjectStore
) -> None:
    """Published to one bucket and compared with another that holds nothing: drift, under the code
    `caselist status` reports it by."""
    source = FakeSource(installation.archives, weeks=[WEEK_1])

    summary = await installation.sync(source, compare_with=empty_bucket).run([CASELIST])

    reported = stage(summary, SyncStage.REPORT)
    assert reported["outcome"] == "failed"
    assert reported["reason"] == "0 snapshot(s) confirmed; not in sync: testcl26 2026-09-01"
    assert reported.get("error_codes") == ["CASELIST_DRIFT"]
    assert summary.succeeded


@needs_permissions
async def test_an_inbox_file_that_cannot_be_removed_fails_retention_as_an_unmodelled_error(
    installation: Installation,
) -> None:
    """The week is imported and confirmed, and the inbox will not let its zip be deleted. That is
    an `OSError` from the operating system, recorded under the code of an error nobody modelled."""
    source = await backlog(installation, WEEK_1)
    installation.inbox.chmod(0o500)
    try:
        summary = await installation.sync(source).run([CASELIST])
    finally:
        installation.inbox.chmod(0o700)

    retention = stage(summary, SyncStage.RETENTION)
    assert retention["outcome"] == "failed"
    assert retention.get("error_codes") == ["INTERNAL_ERROR"]
    assert installation.inbox_names() == {weekly_name(WEEK_1)}
    assert summary.succeeded
    assert_names_nothing_of_this_machine(summary, installation)


# ------------------------------------------------------------------------------------------------
# ac3: what a refused local directory now does to the stages that list it
# ------------------------------------------------------------------------------------------------


@needs_permissions
async def test_a_refused_manifest_directory_stops_the_run_before_anything_is_fetched(
    installation: Installation,
) -> None:
    """Week one is imported. With the manifest directory unreadable the run can no longer tell what
    it holds. It used to list nothing, take every listed week for new and fetch week one again,
    spending one of the day's five; it now stops at selection, naming the directory by its role."""
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    await backlog(installation, WEEK_1)
    manifests = installation.data_dir / "objects" / "manifests"

    with refused(manifests), pytest.raises(StoreAccessDenied) as stopped:
        await installation.sync(source).run([CASELIST])

    assert source.archive_fetches == []
    assert stopped.value.resource == "the manifest directory"
    assert str(installation.data_dir) not in str(stopped.value)
    assert "aws sso login" not in str(stopped.value)


@needs_permissions
async def test_a_refused_release_manifest_directory_fails_retention_and_removes_nothing(
    installation: Installation,
) -> None:
    """Retention reads the OpenEv release manifests to judge camp downloads. Unreadable, it used to
    find none and judge on that; it now reports the refusal and leaves the inbox as it is. The run's
    own stages are untouched: retention never decides whether a run succeeded."""
    source = await backlog(installation, WEEK_1)
    releases = installation.data_dir / "objects" / "manifests" / "openev"
    releases.mkdir(parents=True)
    before = installation.inbox_state()

    with refused(releases):
        summary = await installation.sync(source).run([CASELIST])

    retention = stage(summary, SyncStage.RETENTION)
    assert retention["outcome"] == "failed"
    assert retention.get("error_codes") == ["STORE_ACCESS_DENIED"]
    hint = retention.get("hint")
    assert isinstance(hint, str)
    assert "the manifest directory" in hint
    assert summary.succeeded
    assert summary.failure_codes == ()
    assert installation.inbox_state() == before
    assert_names_nothing_of_this_machine(summary, installation)


# ------------------------------------------------------------------------------------------------
# Forbidden: a path in a stage reason
# ------------------------------------------------------------------------------------------------


async def test_a_torn_local_suppression_list_fails_the_import_without_naming_its_path(
    installation: Installation,
) -> None:
    """This machine's copy of the list is a file under the data directory, and the error for a line
    nobody can read names the copy it is in. The stage's reason names the file, not where it is."""
    copy = local_suppression_list_file(installation.data_dir)
    copy.path.parent.mkdir(parents=True)
    copy.path.write_bytes(b'{"schema_version":1,"act')
    installation.suppression = RecordedSuppressionList(copy)
    source = FakeSource(installation.archives, weeks=[WEEK_1])

    summary = await installation.sync(source).run([CASELIST])

    imported = stage(summary, SyncStage.IMPORT)
    assert imported["outcome"] == "failed"
    assert imported.get("error_codes") == ["UNREADABLE_APPEND_ONLY_RECORD"]
    assert "suppression-list.jsonl line 1 is not readable" in str(imported["reason"])
    assert summary.failure_codes == ("UNREADABLE_APPEND_ONLY_RECORD",)
    assert_names_nothing_of_this_machine(summary, installation)


# ------------------------------------------------------------------------------------------------
# The run summary's schema, and the records an installed build wrote
# ------------------------------------------------------------------------------------------------

STORED = Path(__file__).parent / "stored_run_records"
"""What a build before this task wrote, kept as written: `caselist pull` failing week three's
download on a burst rate limit, against the synthetic caselist. The installed weekly agent runs
such a build until it is reinstalled, in the data directory a newer build also reads."""


async def test_the_summary_schema_is_version_4_and_every_stage_carries_the_new_fields(
    installation: Installation,
) -> None:
    """`error_codes` and `hint` are new on every stage, so the version moves (PM decision)."""
    source = FakeSource(installation.archives, weeks=[WEEK_1])

    summary = await installation.sync(source).run([CASELIST])

    assert RUN_SUMMARY_SCHEMA_VERSION == 4
    assert summary.as_json()["schema_version"] == 4
    for one in stages_of(summary):
        assert sorted(one) == ["error_codes", "hint", "outcome", "reason", "stage"]
        assert one["error_codes"] == []
        assert one["hint"] is None


def test_the_stored_summary_is_a_schema_3_one() -> None:
    """The fixture is what it says: version 3, whose stages carry neither new field."""
    stored = json.loads((STORED / "run_summary_schema_3.json").read_text(encoding="utf-8"))

    assert stored["schema_version"] == 3
    assert all(sorted(one) == ["outcome", "reason", "stage"] for one in stored["stages"])
    assert [one["outcome"] for one in stored["stages"] if one["stage"] == "download"] == ["failed"]


async def test_the_run_monitor_still_reads_the_run_log_a_schema_3_build_wrote(
    installation: Installation, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The newer build's run monitor reads the log the installed build wrote for the previous run's
    backlog, appends its own record after it, and both read back."""
    # The stored run started at the installation's fixed clock; this one is the week after.
    monkeypatch.setattr(inbox_retention, "RUN_CLOCK", datetime(2026, 9, 23, 6, 0, tzinfo=UTC))
    installation.data_dir.mkdir(parents=True)
    log = installation.data_dir / SYNC_RUN_LOG_FILENAME
    log.write_bytes((STORED / "run_log_written_by_a_schema_3_build.jsonl").read_bytes())

    [stored] = SyncRunLog(log).read()

    assert stored.run_id == "20260916T060000Z"
    assert stored.outcome is SyncRunOutcome.FAILED
    assert (stored.archives_wanted, stored.archives_downloaded, stored.archives_deferred) == (3, 2, 0)
    assert stored.deferred_by_caselist == {"testcl26": 0}
    assert [(one.stage, one.outcome) for one in stored.stages][:2] == [
        ("select", "completed"),
        ("download", "failed"),
    ]

    source = FakeSource(installation.archives, weeks=[WEEK_1])
    watched = await pull(installation, installation.sync(source))

    assert watched.pulled.record is not None
    assert watched.pulled.record.backlog_carried == 0, "read from the stored record's deferred count"
    both = SyncRunLog(log).read()
    assert [one.run_id for one in both] == ["20260916T060000Z", "20260923T060000Z"]
    assert both[0] == stored
