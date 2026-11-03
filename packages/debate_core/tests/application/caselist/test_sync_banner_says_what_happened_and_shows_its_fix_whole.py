"""A banner says what happened in words of its own, and shows its fix command whole (`v1-e34-t23`).

Four loose ends in what the weekly sync puts on the operator's screen:

* **Item 6, a run refused because another holds the run lock.** It notified as "needs a person",
  which is true by the exit-code rule (it exits `1`) and wants words of its own: another pull is
  running, and that one records and announces itself.
* **Item 8, a refusal a retry cannot get past until its fix is made.** `STORE_ACCESS_DENIED` exits
  `3`, and its banner said it "will be retried", though the retry is refused the same way until the
  permission or the grant in its hint is fixed. It says so now, in a wording of its own.
* **Item 9, an exception's class.** A run that stopped before any stage said `stopped with
  StoreProfileNotConfigured`. It says what is wrong in words now, and no banner names a class.
* **Item 12, the banner's limits.** On 2026-10-15 the operator's Mac showed the title, a subtitle cut
  at about forty characters, and about ten lines of about forty-five characters of body. The fix
  command was the subtitle, and the end of the body, and was cut in both. The subtitle is now the run
  and its environment, which fits, and the body starts with the fix.

The exit-code rule is untouched (`v1-e34-t13`): every wording is decided from the same codes by the
same rule as before, and only the words differ. Every wording is written out here by hand, and the
runbook's section on what a notification says is held to the same words.

Each banner is read the way the operator's Mac shows it: through `MacOsNotifier.command_for`, which
builds the command and runs nothing, with the observed limits applied to what it would show.
"""

from __future__ import annotations

import inspect
import textwrap
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_synthetic_archives import build_snapshot_zips
from tests.fixtures.permissions import needs_permissions

import debate_core
from debate_core.application import sync_runs
from debate_core.application.caselist_sync import LOCK_FILENAME, RunLock
from debate_core.application.ports.notifier import Notification
from debate_core.application.sync_runs import (
    DriftFinding,
    ParsedStoreOwedDetails,
    StageDetails,
    StageEntry,
    SyncRunDetails,
    SyncRunOutcome,
    SyncRunRecord,
    notifications_for,
)
from debate_core.integrations.local.macos_notifier import MacOsNotifier
from debate_core.integrations.s3 import S3EvidenceObjectStore

from . import run_record_scenarios
from . import test_inbox_retention as inbox_retention
from .retry_rule import a_retry_may_cure
from .run_record_scenarios import (
    SCENARIOS,
    World,
    a_publish_the_bucket_did_not_take,
    a_publish_the_bucket_refused_with_the_adapters_fix,
    a_run_stopped_by_an_error_nobody_modelled,
)
from .test_inbox_retention import WEEK_1, FakeSource, Installation, backlog

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

WHERE = "Run 20260916T060000Z (dev)"
THE_RUN = "Run 20260916T060000Z (dev)"
"""The subtitle: the run and its environment, which fits in forty characters."""

RETRY_TITLE = "caselist pull failed: will be retried"
PERSON_TITLE = "caselist pull failed: needs a person"
FIX_FIRST_TITLE = "caselist pull failed: retried once fixed"
LOCK_TITLE = "caselist pull skipped: another was running"

RETRY = "The next scheduled run should retry it: every failure here is one a later run may not meet."
PERSON = "A person should look: at least one failure here will be the same on the next scheduled run."
FIX_FIRST = (
    "The next scheduled run retries it, and is refused the same way until the fix that follows is made."
)
LOCK = (
    "Another caselist pull held the run lock, so this one did nothing. That run records and "
    "announces its own outcome."
)
KEPT = "What was captured is kept."

SUBTITLE_CHARACTERS = 40
BODY_LINES = 10
BODY_LINE_CHARACTERS = 45
"""What the operator's Mac showed of a banner on 2026-10-15 (`v1-e34-t19`'s banner check)."""


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def world(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str, monkeypatch: pytest.MonkeyPatch
) -> World:
    def set_clock(moment: datetime) -> None:
        monkeypatch.setattr(inbox_retention, "RUN_CLOCK", moment)

    return World(
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


def as_the_banner_shows(notification: Notification) -> tuple[str, str, list[str]]:
    """The title, the subtitle and the body's lines, as far as the operator's Mac shows them: the
    subtitle to forty characters, and the body wrapped at the spaces into lines of forty-five, of
    which ten are shown. A word longer than a line is broken where the line ends."""
    *_, body, title, subtitle = MacOsNotifier(executable="osascript").command_for(notification)
    lines = textwrap.wrap(body, BODY_LINE_CHARACTERS, break_on_hyphens=False)
    return title, subtitle[:SUBTITLE_CHARACTERS], lines[:BODY_LINES]


def assert_the_fix_is_shown_whole(notification: Notification) -> None:
    title, subtitle, lines = as_the_banner_shows(notification)
    *_, body, _, whole_subtitle = MacOsNotifier(executable="osascript").command_for(notification)
    assert notification.fix_command in " ".join(lines), lines
    assert body.startswith(f"Fix: {notification.fix_command} "), body
    assert whole_subtitle == subtitle, "the subtitle is shown whole"
    assert notification.fix_command not in whole_subtitle or len(whole_subtitle) <= SUBTITLE_CHARACTERS
    assert title == notification.title


def exception_classes() -> set[str]:
    """Every exception class this project defines, and the operating system's own."""
    found: set[str] = set()

    def walk(cls: type[BaseException]) -> Iterator[type[BaseException]]:
        for sub in cls.__subclasses__():
            yield sub
            yield from walk(sub)

    for cls in walk(BaseException):
        module = inspect.getmodule(cls)
        if (module is not None and module.__name__.startswith(debate_core.__name__)) or issubclass(
            cls, OSError
        ):
            found.add(cls.__name__)
    return found


def assert_names_no_exception_class(notification: Notification) -> None:
    shown = " ".join(
        (*as_the_banner_shows(notification)[:2], *MacOsNotifier().command_for(notification)[-3:])
    )
    words = set(shown.replace(".", " ").replace(":", " ").replace(",", " ").split())
    assert not words & exception_classes(), words & exception_classes()


# ------------------------------------------------------------------------------------------------
# Item 6: another run holds the lock
# ------------------------------------------------------------------------------------------------


async def test_a_run_refused_by_the_lock_has_a_banner_of_its_own(world: World) -> None:
    source = FakeSource(world.installation.archives, weeks=[WEEK_1])
    world.installation.data_dir.mkdir(parents=True)
    with RunLock(world.installation.data_dir / LOCK_FILENAME):
        await world.pull(world.installation.sync(source))

    [refused] = world.raised
    assert type(refused).__name__ == "SyncRunInProgress", "the command still ends on the refusal, exit 1"
    [notification] = world.notifier.sent
    assert notification.title == LOCK_TITLE
    assert notification.message == f"{WHERE}: {LOCK}"
    assert notification.fix_command == "debate-research caselist runs"
    assert notification.hint is None
    assert "person" not in notification.text
    assert source.archive_fetches == []
    assert_the_fix_is_shown_whole(notification)
    assert_names_no_exception_class(notification)


# ------------------------------------------------------------------------------------------------
# Item 8: retried, once the fix is made
# ------------------------------------------------------------------------------------------------


async def test_a_refusal_that_needs_its_fix_before_a_retry_says_so(world: World) -> None:
    """The bucket refuses a profile that lacks a grant. The exit is `3`, as before; the banner says
    the retry is refused the same way until the grant is fixed, and carries the fix."""
    await a_publish_the_bucket_refused_with_the_adapters_fix(world)

    [notification] = world.notifier.sent
    assert notification.title == FIX_FIRST_TITLE
    assert (
        notification.message
        == f"{WHERE}: the publish stage failed on STORE_ACCESS_DENIED. {FIX_FIRST} {KEPT}"
    )
    assert notification.hint is not None and "lacks a grant" in notification.hint
    assert_the_fix_is_shown_whole(notification)


async def test_a_failure_a_retry_may_cure_with_no_fix_to_make_still_says_it_will_be_retried(
    world: World,
) -> None:
    await a_publish_the_bucket_did_not_take(world)

    [notification] = world.notifier.sent
    assert notification.title == RETRY_TITLE
    assert notification.message == f"{WHERE}: the publish stage failed on STORE_UNAVAILABLE. {RETRY} {KEPT}"


@needs_permissions
async def test_a_run_stopped_by_a_refusal_with_a_fix_says_so_in_words(world: World) -> None:
    """The selection cannot open a week's manifest file: this machine refused it (exit `3`)."""
    await backlog(world.installation, WEEK_1)
    manifest = world.installation.data_dir / "objects/manifests/testcl26/2026-09-01.jsonl"
    manifest.chmod(0)
    try:
        await world.pull(world.installation.sync(FakeSource(world.installation.archives, weeks=[WEEK_1])))
    finally:
        manifest.chmod(0o600)

    [notification] = world.notifier.sent
    assert notification.title == FIX_FIRST_TITLE
    assert notification.message == f"{WHERE} stopped: this machine or the bucket refused it. {FIX_FIRST}"
    assert notification.hint is not None and "the manifest directory" in notification.hint
    assert_names_no_exception_class(notification)


# ------------------------------------------------------------------------------------------------
# Item 9: words, not a class
# ------------------------------------------------------------------------------------------------


async def test_a_profile_the_aws_config_lacks_is_said_in_words(world: World) -> None:
    await world.pull_with_no_bucket()

    [notification] = world.notifier.sent
    assert notification.title == PERSON_TITLE
    assert notification.message == (
        f"{WHERE} stopped: the AWS profile it publishes with is not one this machine's AWS config "
        f"defines. {PERSON}"
    )
    assert "StoreProfileNotConfigured" not in notification.text
    assert_names_no_exception_class(notification)


async def test_a_bug_is_said_in_words(world: World) -> None:
    await a_run_stopped_by_an_error_nobody_modelled(world)

    [notification] = world.notifier.sent
    assert notification.message == f"{WHERE} stopped: an error nobody modelled, most likely a bug. {PERSON}"
    assert_names_no_exception_class(notification)


def test_an_error_code_without_words_of_its_own_is_named_by_its_code() -> None:
    record = SyncRunRecord(
        run_id="20260916T060000Z",
        environment="dev",
        mode="run",
        started_at=datetime(2026, 9, 16, 6, 0, tzinfo=UTC),
        finished_at=datetime(2026, 9, 16, 6, 0, tzinfo=UTC),
        outcome=SyncRunOutcome.FAILED,
        error_class="SomeErrorNobodyNamed",
    )
    details = SyncRunDetails(run_id=record.run_id, failure_codes=("SOME_ERROR_NOBODY_NAMED",))

    [notification] = notifications_for(
        record, details, aws_login_command="aws sso login", credentials_expired=False
    )

    assert notification.message == f"{WHERE} stopped: an error recorded as SOME_ERROR_NOBODY_NAMED. {PERSON}"
    assert "SomeErrorNobodyNamed" not in notification.text


@pytest.mark.parametrize("name", sorted(SCENARIOS))
async def test_no_scenarios_banner_names_an_exception_class_or_hides_its_fix(name: str, world: World) -> None:
    await SCENARIOS[name](world)

    assert world.notifier.sent or name in {
        "a_week_imported_and_published",
        "two_weeks_imported_and_parsed",
        "a_publish_left_for_a_login_and_then_drained",
    }
    for notification in world.notifier.sent:
        assert_names_no_exception_class(notification)
        assert_the_fix_is_shown_whole(notification)


# ------------------------------------------------------------------------------------------------
# Item 12: the fix command, whole, within what the banner shows
# ------------------------------------------------------------------------------------------------


def a_record(
    *stages: tuple[str, str], pending: tuple[str, ...] = (), growing: tuple[str, ...] = ()
) -> SyncRunRecord:
    moment = datetime(2026, 9, 16, 6, 0, tzinfo=UTC)
    return SyncRunRecord(
        run_id="20260916T060000Z",
        environment="dev",
        mode="run",
        started_at=moment,
        finished_at=moment,
        outcome=SyncRunOutcome.FAILED,
        stages=tuple(StageEntry(stage=stage, outcome=outcome) for stage, outcome in stages),
        pending_publish=pending,
        deferred_by_caselist={one: 3 for one in growing},
        backlog_growing=growing,
    )


THE_LONGEST_HINTS = (
    "The bucket refused ListObjectsV2: the AWS profile debate-prod-evidence is signed in and lacks a "
    "grant for this; it is not an expired session, and logging in again changes nothing. "
    "docs/runbooks/evidence-store.md lists what each profile is granted. "
    "`debate-research caselist parse --caselist <slug> --failures` lists the sources that failed, with "
    "their reasons. `debate-research caselist parse --caselist hsld26 --publish-only` and "
    "`debate-research caselist parse --caselist hspolicy26 --publish-only` each publish the parsed "
    "store as this run rebuilt it from every copy of the suppression list, and rebuild nothing. "
    "`debate-research caselist parse --caselist hspf26 --publish` and "
    "`debate-research caselist parse --caselist openev --publish` each publish a caselist's parsed "
    "store: each parses nothing already parsed, rebuilds the aggregates and uploads what the bucket "
    "lacks. The next pull does the same; "
    "`caselist pull --publish-pending` does not."
)
"""Since `v1-e34-t31` the parse stage's fix names each caselist owed with its own command."""


def every_kind_of_banner() -> list[Notification]:
    """One notification of every kind the monitor sends, each at its longest: every stage failed
    with the longest hints together, a login banner with both its added sentences and the longest
    login command, the backlog, a held upload and a manifest to publish again. Since `v1-e34-t26`
    also three manifests that drifted again after their republish, and a report-only login banner
    with every sentence it can carry: the check cut short, a manifest that drifted again, and the
    parsed store. Since `v1-e34-t31` also a parse stage that failed with four caselists owed, each
    named by its own command, at the longest, `--publish-only`."""
    login = "aws sso login --profile debate-prod-evidence"
    failed_everywhere = a_record(
        ("select", "failed"),
        ("download", "failed"),
        ("import", "failed"),
        ("publish", "failed"),
        ("parse", "failed"),
        ("report", "failed"),
        ("retention", "failed"),
    )
    loud = SyncRunDetails(
        run_id=failed_everywhere.run_id,
        stages=tuple(
            StageDetails(
                stage=stage, error_codes=("STORE_ACCESS_DENIED", "UNREADABLE_ARCHIVE"), hint=THE_LONGEST_HINTS
            )
            for stage in ("select", "download", "import", "publish", "parse", "report", "retention")
        ),
        failure_codes=("STORE_ACCESS_DENIED",),
    )
    waiting = a_record(
        ("publish", "pending"),
        ("parse", "pending"),
        ("report", "pending"),
        pending=("testcl26 2026-09-01",) * 9,
    )
    found_first = SyncRunDetails(
        run_id=waiting.run_id,
        stages=(
            StageDetails(stage="publish", earlier_findings=("CHECKSUM_MISMATCH", "UNREADABLE_MANIFEST")),
            StageDetails(
                stage="report",
                earlier_findings=("CASELIST_DRIFT",),
                drift=(DriftFinding(caselist="testcl26", snapshot="2026-09-01", kinds=("manifest",)),),
            ),
        ),
    )
    manifest = a_record(("report", "failed"))
    manifest_details = SyncRunDetails(
        run_id=manifest.run_id,
        stages=(
            StageDetails(
                stage="report",
                error_codes=("CASELIST_DRIFT",),
                drift=tuple(
                    DriftFinding(caselist=caselist, snapshot="2026-09-01", kinds=("manifest",))
                    for caselist in ("hsld26", "hspolicy26", "ndtceda26")
                ),
            ),
        ),
    )
    owed_again = a_record(
        ("report", "failed"), pending=("hsld26 2026-09-01", "hspolicy26 2026-09-01", "ndtceda26 2026-09-01")
    )
    report_alone = a_record(("publish", "completed"), ("parse", "pending"), ("report", "pending"))
    report_alone_found = SyncRunDetails(
        run_id=report_alone.run_id,
        stages=(
            StageDetails(
                stage="report",
                earlier_findings=("CASELIST_DRIFT",),
                drift=tuple(
                    DriftFinding(caselist=caselist, snapshot="2026-09-01", kinds=("manifest",))
                    for caselist in ("hsld26", "hspolicy26", "ndtceda26")
                ),
            ),
        ),
    )
    parse_alone = a_record(("publish", "completed"), ("parse", "failed"))
    four_owed = SyncRunDetails(
        run_id=parse_alone.run_id,
        stages=(StageDetails(stage="parse", error_codes=("STORE_UNAVAILABLE",), hint=THE_LONGEST_HINTS),),
        parsed_stores_owed=tuple(
            ParsedStoreOwedDetails(caselist=caselist, publish_only=True)
            for caselist in ("hsld26", "hspolicy26", "hspf26", "openev")
        ),
    )
    backlog_and_held = a_record(growing=("hsld26", "hspolicy26", "ndtceda26"))
    held = SyncRunDetails(
        run_id=backlog_and_held.run_id, held_by_request={"RM-2026-01": 2, "RM-2026-02": 1, "RM-2026-03": 4}
    )
    sent: list[Notification] = []
    for record, details, expired in (
        (failed_everywhere, loud, False),
        (waiting, found_first, True),
        (manifest, manifest_details, False),
        (owed_again, manifest_details, False),
        (report_alone, report_alone_found, True),
        (parse_alone, four_owed, False),
        (backlog_and_held, held, False),
    ):
        sent.extend(
            notifications_for(
                record,
                details,
                aws_login_command=login,
                credentials_expired=expired,
                may_succeed_on_retry=a_retry_may_cure,
            )
        )
    return sent


def test_every_kind_of_banner_shows_its_fix_whole_within_the_observed_limits() -> None:
    sent = every_kind_of_banner()

    assert len(sent) == 8
    assert {one.title for one in sent} >= {
        "caselist pull: a manifest drifted again",
        "caselist pull: publish a manifest again",
    }
    for notification in sent:
        _, subtitle, _ = as_the_banner_shows(notification)
        assert subtitle == THE_RUN
        assert_the_fix_is_shown_whole(notification)
        assert_names_no_exception_class(notification)


def test_the_body_starts_with_the_fix_and_the_subtitle_is_the_run() -> None:
    notification = Notification(
        title=PERSON_TITLE,
        message=f"{WHERE}: the publish stage failed on PENDING_WORK_UNREADABLE. {PERSON} {KEPT}",
        fix_command="debate-research caselist pull --publish-pending",
        hint="Open the pending-work file under storage.data_dir.",
        subtitle=THE_RUN,
    )

    *_, body, title, subtitle = MacOsNotifier(executable="osascript").command_for(notification)

    assert (title, subtitle) == (PERSON_TITLE, THE_RUN)
    assert body == (
        "Fix: debate-research caselist pull --publish-pending — "
        f"{WHERE}: the publish stage failed on PENDING_WORK_UNREADABLE. {PERSON} {KEPT} "
        "Open the pending-work file under storage.data_dir."
    )
    assert notification.text == (
        f"{WHERE}: the publish stage failed on PENDING_WORK_UNREADABLE. {PERSON} {KEPT} Open the "
        "pending-work file under storage.data_dir. Fix: debate-research caselist pull --publish-pending"
    ), "an adapter with a single text field reads it as before"


THE_BLOB_DIRECTORY_FIX = (
    "This machine refused the blob directory: check that this user can read and write it, under the "
    "environment's data directory (storage.data_dir). It is a permission on this machine, not the AWS "
    "session."
)


def test_the_banner_the_operator_saw_hid_its_command_and_now_shows_it() -> None:
    """The banner of `v1-e34-t19`'s check on 2026-10-15, rebuilt: a publish this machine refused,
    with its fix. In the old layout the subtitle was the command, cut at `--publish-` as the operator
    saw it, and the command ended a body whose ten lines stop before it, at the hint. Now the
    subtitle is the run and the body starts with the command."""
    notification = Notification(
        title=RETRY_TITLE,
        message=f"{WHERE}: the publish stage failed on STORE_ACCESS_DENIED. {RETRY} {KEPT}",
        fix_command="debate-research caselist pull --publish-pending",
        hint=THE_BLOB_DIRECTORY_FIX,
        subtitle=THE_RUN,
    )
    old_subtitle = notification.fix_command[:SUBTITLE_CHARACTERS]
    old_body = textwrap.wrap(notification.text, BODY_LINE_CHARACTERS, break_on_hyphens=False)[:BODY_LINES]

    assert old_subtitle == "debate-research caselist pull --publish-"
    assert notification.fix_command not in " ".join(old_body)
    assert "blob directory" in " ".join(old_body), "the sentence the check asked about was shown"
    assert_the_fix_is_shown_whole(notification)


# ------------------------------------------------------------------------------------------------
# ac4: the runbook's section on what a notification says
# ------------------------------------------------------------------------------------------------

RUNBOOK = Path(__file__).resolve().parents[5] / "docs" / "runbooks" / "caselist-scheduled-sync.md"


def test_the_runbook_shows_the_lock_and_the_fix_first_wordings_and_they_are_the_ones_used() -> None:
    section = RUNBOOK.read_text(encoding="utf-8").split("\n## What a notification says\n", 1)[1]
    section = " ".join(section.split("\n## ", 1)[0].split())

    assert sync_runs.RETRIED_AFTER_ITS_FIX_TITLE == FIX_FIRST_TITLE
    assert sync_runs.RETRIED_AFTER_ITS_FIX == FIX_FIRST
    assert sync_runs.ANOTHER_RUN_HELD_THE_LOCK_TITLE == LOCK_TITLE
    assert sync_runs.ANOTHER_RUN_HELD_THE_LOCK == LOCK
    for wording in (FIX_FIRST_TITLE, FIX_FIRST, LOCK_TITLE, LOCK):
        assert wording in section, wording
    assert (
        f"> {WHERE.replace('20260916T060000Z', '20261014T100000Z').replace('dev', 'prod')}: {LOCK}" in section
    )
    assert "stopped with" not in section, "no banner names a class any more"
    assert sync_runs.MANIFEST_PUBLISHED_AGAIN_TITLE in section
    assert sync_runs.MANIFEST_PUBLISHED_AGAIN in section
    assert sync_runs.HELD_BY_A_REMOVAL_TITLE in section
    # `v1-e34-t26`: a manifest that drifted again, and what waits for the login, as the banners say them.
    assert sync_runs.DRIFTED_AGAIN_TITLE in section
    assert sync_runs.THE_CHECK_WAS_CUT_SHORT.strip() in section
    prod = WHERE.replace("20260916T060000Z", "20261014T100000Z").replace("dev", "prod")
    [drifted_again] = notifications_for(
        a_record(("report", "failed")),
        SyncRunDetails(
            run_id="20260916T060000Z",
            stages=(
                StageDetails(
                    stage="report",
                    error_codes=("CASELIST_DRIFT",),
                    drift=(DriftFinding(caselist="hsld26", snapshot="2026-10-13", kinds=("manifest",)),),
                ),
            ),
        ),
        aws_login_command="aws sso login --profile debate-prod-evidence",
        credentials_expired=False,
        may_succeed_on_retry=a_retry_may_cure,
    )
    assert f"> {drifted_again.message.replace(WHERE, prod)}" in section


def test_nothing_here_was_given_a_retry_rule_of_its_own() -> None:
    """The wording is decided by the command's rule, handed in, as before (`v1-e34-t13`)."""
    assert run_record_scenarios.the_commands_retry_rule() == {"may_succeed_on_retry": a_retry_may_cure}
