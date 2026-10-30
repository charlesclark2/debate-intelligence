"""A failed pull's notification says whether to wait or to look, and carries the fix (`v1-e34-t19`).

Until this task every failed run notified as "caselist pull failed", whatever it failed on, because
the notification was built from the run record and the record has no error codes. The operator
could not tell a bucket that had not answered, which next week's run retries by itself, from an
archive nobody can read, which is the same next week. And the fix a failed stage gives in its
`hint` (a permission on this machine, a grant the profile lacks, a file to repair, the command
that publishes a parsed store) was in the summary and not on the screen.

The notification is now built from the record and the run's details together:

* **ac4.** A run whose download, import or publish failed, or that stopped on an error, says that
  the next scheduled run should retry it when every code its exit was decided from is one a retry
  may cure, and that a person should look in every other case. It is the command's own rule for
  exit `3`, handed to the monitor, so the two cannot disagree.
* **ac7.** A failed stage's hint is on the notification, as the summary gives it, under either
  wording. No hint names a path.
* **ac8.** A publish left pending names what it found before the session expired, when that is
  something no login fixes.

Every pull here is a scenario of `run_record_scenarios.py` or one built the same way: the real
pipeline against moto, at a fixed clock, so each notification is compared whole with a sentence
written out by hand. What the operator would see is read through `MacOsNotifier.command_for`,
which builds the command and runs nothing.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_synthetic_archives import build_snapshot_zips
from tests.fixtures.caselist.publish_expectations import expected_source_key
from tests.fixtures.parse_pipeline.build_parse_world import build_week_zips
from tests.fixtures.permissions import needs_permissions

from debate_core.application import sync_runs
from debate_core.application.caselist_sync import SyncStage
from debate_core.application.errors import ProviderUnavailable
from debate_core.application.ports.notifier import Notification
from debate_core.integrations.local.macos_notifier import MacOsNotifier
from debate_core.integrations.s3 import S3EvidenceObjectStore

from . import run_record_scenarios
from . import test_inbox_retention as inbox_retention
from .run_record_scenarios import (
    AWS_LOGIN,
    World,
    a_mismatch_and_then_an_expiry,
    a_publish_the_bucket_did_not_take,
    a_publish_the_bucket_refused_with_the_adapters_fix,
    a_run_stopped_by_an_error_nobody_modelled,
    a_run_stopped_by_an_expired_token,
    a_week_that_cannot_be_read,
)
from .test_inbox_retention import (
    CASELIST,
    WEEK_1,
    WEEK_2,
    WEEK_3,
    FakeSource,
    Installation,
    backlog,
    weekly_name,
)
from .test_pending_work_owes_every_unpublished_snapshot import (
    NEW_IN_WEEK_2,
    ONLY_IN_WEEK_1,
    Session,
    answered_503,
    pending_file,
)
from .test_pull_parses_new_sources import parse_stage
from .test_pull_stage_failure_codes import (
    RefusingBucket,
    SourceThatFails,
    outage,
    profile_not_configured,
    stage,
)

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

WHERE = "Run 20260916T060000Z (dev)"

RETRY_TITLE = "caselist pull failed: will be retried"
PERSON_TITLE = "caselist pull failed: needs a person"

RETRY = "The next scheduled run should retry it: every failure here is one a later run may not meet."
PERSON = "A person should look: at least one failure here will be the same on the next scheduled run."
"""The two wordings, written out here and not imported: the runbook quotes the same two."""

KEPT = "What was captured is kept."

FIX_FIRST_TITLE = "caselist pull failed: retried once fixed"
FIX_FIRST = (
    "The next scheduled run retries it, and is refused the same way until the fix that follows is made."
)
"""`v1-e34-t23`'s wording of the first verdict when the failure carries a fix to make first: the same
rule and the same exit `3`, and a retry that is refused until the fix is made."""

THE_BUCKET_LACKS_A_GRANT = (
    "The bucket refused ListObjectsV2: the AWS profile debate-dev-evidence is signed in and lacks a "
    "grant for this; it is not an expired session, and logging in again changes nothing. "
    "docs/runbooks/evidence-store.md lists what each profile is granted."
)
"""The fix the bucket's adapter writes into its refusal (`v1-e29-t07`), as the stage gives it."""
THE_AWS_CONFIG_LACKS_THE_PROFILE = (
    "The bucket was never reached: set storage.s3.aws_profile to a profile this machine's AWS config "
    "defines, or add the profile to it: docs/runbooks/evidence-store.md lists the evidence profiles "
    "and how they are added. It is not an expired session, and logging in changes nothing."
)
"""The fix the adapter writes for a profile the AWS config does not define (`v1-e29-t07`)."""
THIS_MACHINE_REFUSED_THE_MANIFESTS = (
    "This machine refused the manifest directory: check that this user can read and write it, under "
    "the environment's data directory (storage.data_dir). It is a permission on this machine, not "
    "the AWS session."
)
THE_PENDING_WORK_FILE_NEEDS_A_PERSON = (
    "Open the pending-work file under storage.data_dir: it lists the snapshots this machine has "
    "imported and not yet published, and this run left it untouched because it could not be read. "
    "docs/runbooks/caselist-scheduled-sync.md gives its name and its shape, and says what to do when "
    "it cannot be repaired. It is not the AWS session."
)
PUBLISH_THE_PARSED_STORE = (
    f"`debate-research caselist parse --caselist {CASELIST} --publish-only` publishes the parsed store "
    "as this run rebuilt it from every copy of the suppression list, and rebuilds nothing. The next "
    "pull that imports into that caselist does the same; `caselist pull --publish-pending` does not."
)
"""The parse stage's hint when its rebuild read every copy of the list and its publish failed
(`v1-e34-t31`): the caselist by name, and `--publish-only`, since only the publish is owed."""
LIST_WHAT_FAILED_TO_PARSE = (
    "`debate-research caselist parse --caselist <slug> --failures` lists the sources that failed, "
    "with their reasons."
)
"""Each fix as the summary's `hint` gives it, written out by hand."""

A_PATH_ON_A_MACHINE = re.compile(r"(?:^|[\s(\"'`])(?:~/|/)\S")
"""Something starting at `/` or `~/`. `docs/runbooks/…`, which a hint may cite, does not."""


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


def the_one_notification(world: World) -> Notification:
    [notification] = world.notifier.sent
    return notification


def shown(notification: Notification) -> tuple[str, str, str]:
    """What the operator's Mac would be asked to show: the body, the title and the subtitle."""
    *_, body, title, subtitle = MacOsNotifier(executable="osascript").command_for(notification)
    return body, title, subtitle


def assert_names_no_path(world: World, notification: Notification) -> None:
    """No path on this machine, in any field, as written or as shown."""
    everything = " ".join((notification.title, notification.text, *shown(notification)))
    for forbidden in (str(world.installation.data_dir), str(world.scratch), str(Path.home())):
        assert forbidden not in everything
    assert A_PATH_ON_A_MACHINE.search(everything) is None, everything


# ------------------------------------------------------------------------------------------------
# ac4: the two wordings
# ------------------------------------------------------------------------------------------------


async def test_a_run_failed_only_on_what_a_retry_may_cure_says_the_next_scheduled_run_should_retry_it(
    world: World,
) -> None:
    """Every upload was answered 503. The exit is `3`, and the notification says the same."""
    await a_publish_the_bucket_did_not_take(world)

    notification = the_one_notification(world)
    assert notification.title == RETRY_TITLE
    assert notification.message == (f"{WHERE}: the publish stage failed on STORE_UNAVAILABLE. {RETRY} {KEPT}")
    assert notification.hint is None
    assert notification.fix_command == "debate-research caselist pull --publish-pending"
    assert_names_no_path(world, notification)


async def test_a_run_that_met_a_verdict_says_a_person_should_look(world: World) -> None:
    """Week one cannot be read as an archive. The exit is `1`: next week it is the same archive."""
    await a_week_that_cannot_be_read(world)

    notification = the_one_notification(world)
    assert notification.title == PERSON_TITLE
    assert notification.message == (
        f"{WHERE}: the import stage failed on UNREADABLE_ARCHIVE. {PERSON} {KEPT}"
    )
    assert notification.hint is None
    assert notification.fix_command == "debate-research caselist pull"
    assert_names_no_path(world, notification)


async def test_one_verdict_among_failures_a_retry_may_cure_makes_it_a_person(world: World) -> None:
    """Week three's download answers 503 and week one cannot be read. Each stage is named with what
    it failed on, and the one verdict decides, as it decides the exit."""
    unavailable = ProviderUnavailable("opencaselist", "download failed: HTTP 503 (after 4 attempts)")
    source = SourceThatFails(
        world.installation.archives,
        weeks=[WEEK_1, WEEK_2, WEEK_3],
        archive_failures={weekly_name(WEEK_3): unavailable},
    )

    await world.pull(world.installation.sync(source, unreadable=[weekly_name(WEEK_1)]))

    notification = the_one_notification(world)
    assert notification.title == PERSON_TITLE
    assert notification.message == (
        f"{WHERE}: the download stage failed on PROVIDER_UNAVAILABLE; the import stage failed on "
        f"UNREADABLE_ARCHIVE. {PERSON} {KEPT}"
    )


async def test_a_monitor_given_no_rule_never_says_a_failure_will_pass_by_itself(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The wording is the command's decision. A monitor built without it promises nothing: the same
    503 that the command calls transient is, here, something for a person."""
    monkeypatch.setattr(run_record_scenarios, "the_commands_retry_rule", dict)

    await a_publish_the_bucket_did_not_take(world)

    notification = the_one_notification(world)
    assert notification.title == PERSON_TITLE
    assert notification.message == f"{WHERE}: the publish stage failed on STORE_UNAVAILABLE. {PERSON} {KEPT}"


# ------------------------------------------------------------------------------------------------
# ac4: a run that stopped on an error before any stage could record it
# ------------------------------------------------------------------------------------------------


@needs_permissions
async def test_a_run_stopped_by_a_manifest_it_could_not_read_says_retry_and_carries_the_fix(
    world: World,
) -> None:
    """The selection cannot read a week's manifest file and stops the run (exit `3`). Nothing is
    wrong that a later run cannot get past, once the permission is fixed, and the hint says which.
    Since `v1-e34-t23` it says the retry needs the fix first, and what stopped it in words."""
    await backlog(world.installation, WEEK_1)
    (world.installation.data_dir / "objects/manifests/testcl26/2026-09-01.jsonl").chmod(0)

    await world.pull(world.installation.sync(FakeSource(world.installation.archives, weeks=[WEEK_1, WEEK_2])))

    assert [type(one).__name__ for one in world.raised] == ["LocalStoreAccessDenied"]
    notification = the_one_notification(world)
    assert notification.title == FIX_FIRST_TITLE
    assert notification.message == f"{WHERE} stopped: this machine or the bucket refused it. {FIX_FIRST}"
    assert notification.hint == THIS_MACHINE_REFUSED_THE_MANIFESTS
    assert notification.fix_command == "debate-research caselist pull"
    assert_names_no_path(world, notification)


async def test_a_run_stopped_by_an_error_nobody_modelled_says_a_person_should_look(world: World) -> None:
    """A bug, exit 70. Its message quotes a path and never reaches the screen, and since `v1-e34-t23`
    neither does its class: it is said in words."""
    await a_run_stopped_by_an_error_nobody_modelled(world)

    notification = the_one_notification(world)
    assert notification.title == PERSON_TITLE
    assert notification.message == f"{WHERE} stopped: an error nobody modelled, most likely a bug. {PERSON}"
    assert notification.hint is None
    assert_names_no_path(world, notification)


async def test_an_expired_token_keeps_the_notification_it_always_had(world: World) -> None:
    """Unchanged: its own title, and the one command that fixes it."""
    await a_run_stopped_by_an_expired_token(world)

    notification = the_one_notification(world)
    assert notification.title == "caselist pull stopped: OpenCaselist login expired"
    assert notification.message == f"{WHERE} was refused by OpenCaselist and fetched nothing more."
    assert notification.fix_command == "debate-research caselist auth login"


# ------------------------------------------------------------------------------------------------
# ac7: the stage's hint, under either wording
# ------------------------------------------------------------------------------------------------


async def test_a_refusal_by_the_bucket_says_retry_and_carries_the_grant_to_fix_first(world: World) -> None:
    """A refusal exits `3`, so the wording is the first one, in the words `v1-e34-t23` gave it for a
    failure with a fix: the hint is what has to be done before the retry can help."""
    await a_publish_the_bucket_refused_with_the_adapters_fix(world)

    [pulled] = world.pulled
    notification = the_one_notification(world)
    assert notification.title == FIX_FIRST_TITLE
    assert notification.message == (
        f"{WHERE}: the publish stage failed on STORE_ACCESS_DENIED. {FIX_FIRST} {KEPT}"
    )
    assert notification.hint == THE_BUCKET_LACKS_A_GRANT
    assert notification.hint == stage(pulled.summary, SyncStage.PUBLISH)["hint"], "the fix the summary gives"
    assert "aws sso login" not in notification.text
    assert_names_no_path(world, notification)


async def test_a_profile_the_aws_config_lacks_says_a_person_and_carries_the_setting_to_correct(
    world: World,
) -> None:
    """`v1-e29-t07`'s failure, which no later run meets differently: the setting names a profile
    this machine's AWS config does not define. The second wording, with the adapter's own fix."""
    source = FakeSource(world.installation.archives, weeks=[WEEK_1])
    unconfigured = RefusingBucket(profile_not_configured())

    await world.pull(world.installation.sync(source, publish_to=unconfigured))

    [pulled] = world.pulled
    notification = the_one_notification(world)
    assert notification.title == PERSON_TITLE
    assert notification.message == (
        f"{WHERE}: the publish stage failed on STORE_PROFILE_NOT_CONFIGURED. {PERSON} {KEPT}"
    )
    assert notification.hint == THE_AWS_CONFIG_LACKS_THE_PROFILE
    assert notification.hint == stage(pulled.summary, SyncStage.PUBLISH)["hint"], "the fix the summary gives"
    assert "aws sso login" not in notification.text
    assert_names_no_path(world, notification)


@needs_permissions
async def test_a_refusal_by_this_machine_says_retry_and_carries_the_data_directory_fix(world: World) -> None:
    """This machine will not let week two's manifest be written: the import fails on a refusal."""
    await backlog(world.installation, WEEK_1)
    manifests = world.installation.data_dir / "objects" / "manifests" / CASELIST
    manifests.chmod(0o500)
    try:
        await world.pull(
            world.installation.sync(FakeSource(world.installation.archives, weeks=[WEEK_1, WEEK_2]))
        )
    finally:
        manifests.chmod(0o700)

    notification = the_one_notification(world)
    assert notification.title == FIX_FIRST_TITLE
    assert (
        notification.message == f"{WHERE}: the import stage failed on STORE_ACCESS_DENIED. {FIX_FIRST} {KEPT}"
    )
    assert notification.hint == THIS_MACHINE_REFUSED_THE_MANIFESTS
    assert_names_no_path(world, notification)


async def test_a_pending_work_file_nobody_can_read_says_a_person_and_carries_what_to_do(world: World) -> None:
    """The second wording with a hint present. Until this task this notified as "caselist pull
    failed" and the fix was in the summary alone (`v1-e34-t18`)."""
    world.installation.data_dir.mkdir(parents=True)
    pending_file(world.installation).write_bytes(b"{not json at all")

    await world.pull(world.installation.sync(FakeSource(world.installation.archives, weeks=[WEEK_1])))

    notification = the_one_notification(world)
    assert notification.title == PERSON_TITLE
    assert notification.message == (
        f"{WHERE}: the publish stage failed on PENDING_WORK_UNREADABLE. {PERSON} {KEPT}"
    )
    assert notification.hint == THE_PENDING_WORK_FILE_NEEDS_A_PERSON
    assert_names_no_path(world, notification)


async def test_a_failed_parse_stage_carries_its_own_fix_and_neither_wording(world: World) -> None:
    """The parsed store's listing gets a 503. The parse stage is not one that had to finish: the
    run exits `0`, and the next scheduled run does not retry a parse, so the notification promises
    neither thing. It carries the stage's hint, which is the command `v1-e34-t17` added."""
    parsing = Installation(
        data_dir=world.installation.data_dir,
        bucket=world.installation.bucket,
        archives=build_week_zips(world.scratch / "parse-world"),
    )
    source = FakeSource(parsing.archives, weeks=[WEEK_1, WEEK_2])
    refusing = parse_stage(parsing, publish_to=RefusingBucket(outage()))

    await world.pull(parsing.sync(source, parse=refusing))

    notification = the_one_notification(world)
    assert notification.title == "caselist pull finished with a failed stage"
    assert notification.message == f"{WHERE}: the parse stage failed on STORE_UNAVAILABLE. {KEPT}"
    assert notification.hint == PUBLISH_THE_PARSED_STORE
    assert notification.fix_command == f"debate-research caselist parse --caselist {CASELIST} --publish-only"
    assert_names_no_path(world, notification)


async def test_a_parse_over_the_failure_rate_carries_the_command_that_lists_what_failed(world: World) -> None:
    parsing = Installation(
        data_dir=world.installation.data_dir,
        bucket=world.installation.bucket,
        archives=build_week_zips(world.scratch / "parse-world"),
    )
    source = FakeSource(parsing.archives, weeks=[WEEK_1, WEEK_2])

    await world.pull(parsing.sync(source, parse=parse_stage(parsing, threshold=0.2, minimum=4)))

    notification = the_one_notification(world)
    assert notification.title == "caselist pull finished with a failed stage"
    assert notification.message == (f"{WHERE}: the parse stage failed on PARSE_FAILURE_RATE_EXCEEDED. {KEPT}")
    assert notification.hint == LIST_WHAT_FAILED_TO_PARSE


@pytest.mark.parametrize(
    "hint",
    [
        THE_BUCKET_LACKS_A_GRANT,
        THIS_MACHINE_REFUSED_THE_MANIFESTS,
        THE_PENDING_WORK_FILE_NEEDS_A_PERSON,
        f"{LIST_WHAT_FAILED_TO_PARSE} {PUBLISH_THE_PARSED_STORE}",
    ],
    ids=["a grant", "a permission on this machine", "the pending-work file", "both of a parse stage's"],
)
def test_the_operators_mac_is_shown_the_verdict_first_and_the_whole_hint(hint: str) -> None:
    """The title is the verdict, the subtitle the run, and the body the command and then the
    sentence and the hint, whole: the longest a failed stage can give is not cut off. Until
    `v1-e34-t23` the subtitle was the command and the body ended with it, and a banner cut it in
    both (`test_sync_banner_says_what_happened_and_shows_its_fix_whole.py`)."""
    notification = Notification(
        title=PERSON_TITLE,
        message=f"{WHERE}: the publish stage failed on PENDING_WORK_UNREADABLE. {PERSON} {KEPT}",
        fix_command="debate-research caselist pull --publish-pending",
        hint=hint,
        subtitle=WHERE,
    )

    body, title, subtitle = shown(notification)

    assert title == PERSON_TITLE
    assert subtitle == WHERE
    assert body == (
        "Fix: debate-research caselist pull --publish-pending — "
        f"{WHERE}: the publish stage failed on PENDING_WORK_UNREADABLE. {PERSON} {KEPT} {hint}"
    )


def test_the_title_and_the_command_are_still_held_to_a_line_and_the_body_to_its_own_limit() -> None:
    """The body grew to hold a hint; nothing else did, and the body is still not a log."""
    notification = Notification(
        title="t" * 500, message="m" * 5000, fix_command="c" * 500, subtitle="s" * 500
    )

    body, title, subtitle = shown(notification)

    assert (len(title), len(subtitle), len(body)) == (240, 240, 1500)
    assert title.endswith("…") and subtitle.endswith("…") and body.endswith("…")


def test_a_notification_with_no_hint_reads_as_it_always_did() -> None:
    notification = Notification(title="a title", message="A sentence.", fix_command="a command")

    assert notification.hint is None
    assert notification.text == "A sentence. Fix: a command"


# ------------------------------------------------------------------------------------------------
# ac8: what a pending publish found first
# ------------------------------------------------------------------------------------------------


async def test_a_mismatch_before_the_session_expired_is_named_on_the_login_notification_as_needing_a_person(
    world: World,
) -> None:
    """`v1-e34-t18`'s shape. The publish is pending and the exit is `0`, as before. The login
    notification now says that one snapshot will not be finished by logging in, and on what."""
    await a_mismatch_and_then_an_expiry(world)

    [pulled] = world.pulled
    assert stage(pulled.summary, SyncStage.PUBLISH)["outcome"] == "pending"
    assert pulled.summary.succeeded
    notification = the_one_notification(world)
    assert notification.title == "caselist publish waiting for an AWS login"
    assert notification.message == (
        f"{WHERE} kept everything it fetched; 2 snapshot(s) and the run record wait to be published. "
        "A person should look as well: before the session expired a snapshot ended incomplete on "
        "CHECKSUM_MISMATCH, which the login will not fix."
    )
    assert notification.fix_command == f"{AWS_LOGIN} && debate-research caselist pull --publish-pending"
    assert_names_no_path(world, notification)


async def test_an_upload_the_bucket_did_not_take_before_the_session_expired_needs_no_person(
    world: World,
) -> None:
    """The same shape with a 503 in place of the mismatch. The retry after the login cures that by
    itself, so the summary records it as an earlier finding and the notification asks for nobody."""
    session = Session(
        world.installation.bucket,
        answers={expected_source_key(ONLY_IN_WEEK_1): answered_503},
        expires_on=expected_source_key(NEW_IN_WEEK_2),
    )
    source = FakeSource(world.installation.archives, weeks=[WEEK_1, WEEK_2])

    await world.pull(world.installation.sync(source, publish_to=session))
    await session.settle()

    [pulled] = world.pulled
    assert stage(pulled.summary, SyncStage.PUBLISH)["earlier_findings"] == ["STORE_UNAVAILABLE"]
    notification = the_one_notification(world)
    assert notification.title == "caselist publish waiting for an AWS login"
    assert notification.message == (
        f"{WHERE} kept everything it fetched; 2 snapshot(s) and the run record wait to be published."
    )


# ------------------------------------------------------------------------------------------------
# The rule itself, on records and details written by hand
# ------------------------------------------------------------------------------------------------


def a_record(*stages: tuple[str, str]) -> sync_runs.SyncRunRecord:
    return sync_runs.SyncRunRecord(
        run_id="20260916T060000Z",
        environment="dev",
        mode="run",
        started_at=datetime.fromisoformat("2026-09-16T06:00:00+00:00"),
        finished_at=datetime.fromisoformat("2026-09-16T06:00:00+00:00"),
        outcome=sync_runs.SyncRunOutcome.FAILED,
        stages=tuple(sync_runs.StageEntry(stage=name, outcome=outcome) for name, outcome in stages),
    )


def titles(record: sync_runs.SyncRunRecord, details: object, *transient: str) -> list[str]:
    sent = sync_runs.notifications_for(
        record,
        details,  # type: ignore[arg-type]
        aws_login_command=AWS_LOGIN,
        credentials_expired=False,
        may_succeed_on_retry=lambda codes: all(code in transient for code in codes),
    )
    return [one.title for one in sent]


def test_a_failed_required_stage_with_no_code_is_never_called_transient() -> None:
    """Nothing reaches the first wording because nobody classified it: with no code the exit was
    decided from, there is nothing for the rule to call transient."""
    record = a_record(("publish", "failed"))
    details = sync_runs.SyncRunDetails(run_id=record.run_id)

    assert titles(record, details, "STORE_UNAVAILABLE") == [PERSON_TITLE]


def test_the_wording_is_decided_from_the_codes_the_exit_was_decided_from_and_no_others() -> None:
    """The parse stage failed on a verdict and the publish stage on an outage. Only the publish
    stage had to finish, so only its code is asked about: the run exits `3` and says retry."""
    record = a_record(("publish", "failed"), ("parse", "failed"))
    details = sync_runs.SyncRunDetails(
        run_id=record.run_id,
        stages=(
            sync_runs.StageDetails(stage="publish", error_codes=("STORE_UNAVAILABLE",)),
            sync_runs.StageDetails(stage="parse", error_codes=("PARSE_FAILURE_RATE_EXCEEDED",)),
        ),
        failure_codes=("STORE_UNAVAILABLE",),
    )

    assert titles(record, details, "STORE_UNAVAILABLE") == [RETRY_TITLE]
    assert titles(record, details) == [PERSON_TITLE]


# ------------------------------------------------------------------------------------------------
# ac4: the runbook shows both wordings
# ------------------------------------------------------------------------------------------------

RUNBOOK = Path(__file__).resolve().parents[5] / "docs" / "runbooks" / "caselist-scheduled-sync.md"


def test_the_runbook_shows_both_wordings_and_they_are_the_ones_the_notification_uses() -> None:
    """The operator reads the runbook to know what a banner means, so the words there are the
    words on the banner, to the letter. Each is checked against the code and against the page."""
    section = RUNBOOK.read_text(encoding="utf-8").split("\n## What a notification says\n", 1)[1]
    section = " ".join(section.split("\n## ", 1)[0].split())

    assert sync_runs.RETRIED_BY_THE_NEXT_RUN_TITLE == RETRY_TITLE
    assert sync_runs.NEEDS_A_PERSON_TITLE == PERSON_TITLE
    assert sync_runs.RETRIED_BY_THE_NEXT_RUN == RETRY
    assert sync_runs.NEEDS_A_PERSON == PERSON
    for wording in (RETRY_TITLE, PERSON_TITLE, RETRY, PERSON):
        assert wording in section, wording
    assert (
        "A person should look as well: before the session expired a snapshot ended incomplete on "
        "CHECKSUM_MISMATCH, which the login will not fix." in section
    )
    assert (
        THIS_MACHINE_REFUSED_THE_MANIFESTS.replace("the manifest directory", "the blob directory") in section
    )
    assert "debate-research caselist parse --caselist <slug> --publish" in section
    # Each caselist by its own command, and the earlier builds' word for every one (`v1-e34-t31`).
    assert "debate-research caselist parse --caselist <slug> --publish-only" in section
    assert "--publish` for every caselist" in section
