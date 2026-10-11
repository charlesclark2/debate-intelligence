"""The pulls whose run records are compared across builds (`v1-e34-t19`).

Each scenario is one or two `caselist pull` runs in the installation `test_inbox_retention.py`
builds, against moto, at a fixed clock, so the same scenario run by two builds describes the same
run: the same run id, the same times, the same stages. `write_stored_run_records.py` runs them
against the start commit's source and keeps what that build wrote; `test_pull_run_record_is_read_
by_every_build.py` runs them against this build and compares.

Nothing here names anything this task adds, so the module imports under either source.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from tests.fixtures.caselist.interruptible_bucket import ScriptedBucket
from tests.fixtures.caselist.publish_expectations import expected_source_key
from tests.fixtures.parse_pipeline.build_parse_world import build_week_zips

from debate_core.application.caselist_sync import CaselistSyncService, PulledRun, run_pull
from debate_core.application.ports.caselist_source import ArchiveListing, CaselistAuthExpired
from debate_core.application.ports.notifier import RecordingNotifier
from debate_core.application.sync_runs import SYNC_RUN_LOG_FILENAME, SyncRunMonitor
from debate_core.integrations.s3 import S3EvidenceObjectStore

from . import test_inbox_retention as inbox_retention
from .test_inbox_retention import CASELIST, WEEK_1, WEEK_2, ExpiredBucket, FakeSource, Installation
from .test_pending_work_owes_every_unpublished_snapshot import NEW_IN_WEEK_2, ONLY_IN_WEEK_1, Session
from .test_pull_parses_new_sources import parse_stage
from .test_pull_stage_failure_codes import RefusingBucket, every_upload_answers_503, missing_grant

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

AWS_LOGIN = "aws sso login --profile debate-dev-evidence"

FIRST_RUN = datetime(2026, 9, 16, 6, 0, tzinfo=UTC)
"""The installation's own fixed clock: every scenario's first run starts and ends here."""

SECOND_RUN = datetime(2026, 9, 23, 6, 0, tzinfo=UTC)
"""A scenario's second run, the week after, so that the two have different run ids."""

RECORDS_PREFIX = "reports/sync-runs/"
"""Where every build puts a run's record in the bucket, and the one prefix an older build lists."""


@dataclass
class World:
    """What a scenario runs in: the installation, its bucket, and the two clocks it may run at."""

    installation: Installation
    s3_client: S3Client
    bucket_name: str
    scratch: Path
    set_clock: Callable[[datetime], None]
    """Moves the installation's clock, and with it the monitor's: `monkeypatch` in a test."""

    notifier: RecordingNotifier = field(default_factory=RecordingNotifier)
    pulled: list[PulledRun] = field(default_factory=lambda: list[PulledRun]())
    raised: list[BaseException] = field(default_factory=lambda: list[BaseException]())

    async def pull(self, service: CaselistSyncService, *, publish_pending: bool = False) -> None:
        """`caselist pull` as the command runs it: `run_pull` inside a real run monitor.

        A run that raises is recorded by the monitor and raised again, as in the command; the
        error is kept here so that the scenario can go on.
        """
        monitor = SyncRunMonitor(
            state_dir=self.installation.data_dir,
            environment="dev",
            notifier=self.notifier,
            remote=self.installation.bucket,
            aws_login_command=AWS_LOGIN,
            clock=lambda: inbox_retention.RUN_CLOCK,
        )
        try:
            self.pulled.append(
                await run_pull(
                    lambda: service,
                    [] if publish_pending else [CASELIST],
                    dry_run=False,
                    publish_pending=publish_pending,
                    monitor=lambda: monitor,
                    progress=lambda _: None,
                )
            )
        except Exception as stopped:
            self.raised.append(stopped)

    def run_log(self) -> bytes:
        """The run log as this build left it: one record a line."""
        return (self.installation.data_dir / SYNC_RUN_LOG_FILENAME).read_bytes()

    def records_in_the_bucket(self) -> dict[str, str]:
        """Every object under the prefix an older build lists for records, by key."""
        listed = self.s3_client.list_objects_v2(Bucket=self.bucket_name, Prefix=RECORDS_PREFIX)
        return {
            str(one.get("Key")): self.s3_client.get_object(Bucket=self.bucket_name, Key=str(one.get("Key")))[
                "Body"
            ]
            .read()
            .decode("utf-8")
            for one in listed.get("Contents", [])
        }


class TokenExpired(FakeSource):
    """OpenCaselist refusing the listing: the `caselist_token` has expired."""

    async def list_archives(self, caselist: str) -> list[ArchiveListing]:
        raise CaselistAuthExpired(401, f"list the downloads of {caselist}")


class Broken(FakeSource):
    """A source that fails in a way nobody modelled, with a path in what it says."""

    async def list_archives(self, caselist: str) -> list[ArchiveListing]:
        raise RuntimeError("could not open /Users/someone/.debate-research/dev/inbox/Maple Grove-QX.docx")


async def a_week_imported_and_published(world: World) -> None:
    source = FakeSource(world.installation.archives, weeks=[WEEK_1])
    await world.pull(world.installation.sync(source))


async def a_publish_the_bucket_did_not_take(world: World) -> None:
    """Every upload is answered 503: a failed publish, on a cause a retry may cure."""
    source = FakeSource(world.installation.archives, weeks=[WEEK_1])
    assert isinstance(world.installation.bucket, S3EvidenceObjectStore)
    stuttering = ScriptedBucket(world.installation.bucket, every_upload_answers_503)
    await world.pull(world.installation.sync(source, publish_to=stuttering))


async def a_publish_the_bucket_refused(world: World) -> None:
    """The profile lacks a grant: a failed publish whose stage carries a hint."""
    source = FakeSource(world.installation.archives, weeks=[WEEK_1])
    await world.pull(world.installation.sync(source, publish_to=RefusingBucket(missing_grant())))


async def a_week_that_cannot_be_read(world: World) -> None:
    """The archive reader refuses week one: a failed import, on a verdict."""
    source = FakeSource(world.installation.archives, weeks=[WEEK_1])
    await world.pull(world.installation.sync(source, unreadable=[inbox_retention.weekly_name(WEEK_1)]))


async def a_publish_left_for_a_login_and_then_drained(world: World) -> None:
    """The session had expired: publish pending. The week after, `--publish-pending` drains it."""
    source = FakeSource(world.installation.archives, weeks=[WEEK_1])
    expired = world.installation.sync(source, publish_to=ExpiredBucket(), compare_with=ExpiredBucket())
    await world.pull(expired)
    world.set_clock(SECOND_RUN)
    await world.pull(world.installation.sync(source), publish_pending=True)


async def a_mismatch_and_then_an_expiry(world: World) -> None:
    """`v1-e34-t18`'s shape: week one incomplete on other bytes under a key, the session expiring
    on week two. Publish is pending."""
    world.s3_client.put_object(
        Bucket=world.bucket_name, Key=expected_source_key(ONLY_IN_WEEK_1), Body=b"other bytes"
    )
    session = Session(world.installation.bucket, expires_on=expected_source_key(NEW_IN_WEEK_2))
    source = FakeSource(world.installation.archives, weeks=[WEEK_1, WEEK_2])
    await world.pull(world.installation.sync(source, publish_to=session))
    await session.settle()


async def a_run_stopped_by_an_expired_token(world: World) -> None:
    await world.pull(world.installation.sync(TokenExpired(world.installation.archives)))


async def a_run_stopped_by_an_error_nobody_modelled(world: World) -> None:
    await world.pull(world.installation.sync(Broken(world.installation.archives)))


async def two_weeks_imported_and_parsed(world: World) -> None:
    """The parse stage of `v1-e34-t17`, over the fictional caselist the parse tests serve."""
    parsing = Installation(
        data_dir=world.installation.data_dir,
        bucket=world.installation.bucket,
        archives=build_week_zips(world.scratch / "parse-world"),
    )
    source = FakeSource(parsing.archives, weeks=[WEEK_1, WEEK_2])
    await world.pull(parsing.sync(source, parse=parse_stage(parsing)))


SCENARIOS: dict[str, Callable[[World], Awaitable[None]]] = {
    one.__name__: one
    for one in (
        a_week_imported_and_published,
        a_publish_the_bucket_did_not_take,
        a_publish_the_bucket_refused,
        a_week_that_cannot_be_read,
        a_publish_left_for_a_login_and_then_drained,
        a_mismatch_and_then_an_expiry,
        a_run_stopped_by_an_expired_token,
        a_run_stopped_by_an_error_nobody_modelled,
        two_weeks_imported_and_parsed,
    )
}


def stored_bucket_text(objects: dict[str, str]) -> str:
    """How a scenario's bucket objects are kept in one file: key to body, in key order."""
    return json.dumps(dict(sorted(objects.items())), indent=2) + "\n"
