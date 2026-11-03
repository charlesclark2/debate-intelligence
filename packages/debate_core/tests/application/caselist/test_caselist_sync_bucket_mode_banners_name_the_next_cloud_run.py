"""In bucket mode the last banners that named `caselist pull` name the next cloud run (`v1-e40-t28`).

`v1-e40-t18`, `v1-e40-t22` and `v1-e40-t25` moved the parse stage's, the login banner's and the
publish's hints to the cloud run. Three banners of a bucket-mode run's email still named a run of
`debate-research caselist pull` on this machine for a cloud run's problem:

* **A run that stopped on an error.** Its fix was the pull.
* **A failed-stage banner whose failed stages are more than the publish alone or the parse alone**: a
  failed import beside a failed publish, a failed download, a failed report stage. Its fix was the
  pull, and its last sentence "What was captured is kept.", which in a cloud run is not so: an archive
  downloaded and not imported, and a snapshot captured and not published, end with the task
  (ADR-0020 (3), "What is not saved").
* **The backlog banner.** Its fix was the pull "again tomorrow, when the day's downloads reset".

In bucket mode each names the next cloud run, in the words every bucket-mode cure shares
(:func:`~debate_core.application.caselist_sync.next_cloud_run`), and a failed-stage banner ends with
`v1-e40-t25`'s "What the bucket confirmed is kept; the cloud run's working copy ends with its task."
Local mode keeps every word. (The CLI's own next steps are
`packages/debate_cli/tests/bucket_mode/test_bucket_mode_rerun_hint_names_the_cloud_run.py`'s, and the
login hint in a cloud run's record reasons is
`packages/debate_cli/tests/bucket_mode/test_bucket_mode_login_hint_names_the_task_role.py`'s.)

Bucket mode is decided as before: the details' `bucket_run`. No record or details model changes, so
every build reads what these runs write as it did. Every expected sentence is written out by hand.
"""

from __future__ import annotations

from typing import Final

import pytest

from debate_core.application.ports.notifier import Notification
from debate_core.application.sync_runs import StageDetails, SyncRunOutcome

from .test_caselist_sync_bucket_mode_publish_hints_point_at_the_cloud import (
    RETRIED,
    WHERE,
    a_record,
    details_of,
    points_at_the_mac,
    section,
    sent_for,
    titled,
)

# ------------------------------------------------------------------------------------------------
# What each banner says, by hand
# ------------------------------------------------------------------------------------------------

THE_UNFINISHED_RUN_CURE_IN_THE_CLOUD: Final = (
    "the next cloud run takes up what this run did not finish, from the run state saved in the bucket: "
    'the weekly run, or one started by hand (caselist-cloud-run.md, "A failed or stopped run"); never a '
    "publish from the operator's Mac"
)
THE_UNFINISHED_RUN_CURE_ON_THE_MAC: Final = "debate-research caselist pull"

THE_BACKLOG_CURE_IN_THE_CLOUD: Final = (
    "the next cloud run fetches more of what the daily download cap deferred, once the day's downloads "
    'reset: the weekly run, or one started by hand (caselist-cloud-run.md, "A backlog growing"); never '
    "a publish from the operator's Mac"
)
THE_BACKLOG_CURE_ON_THE_MAC: Final = (
    "debate-research caselist pull (again tomorrow, when the day's downloads reset)"
)

THE_STOPPED_RUN: Final = (
    f"{WHERE} stopped: a store did not answer. The next scheduled run should retry it: every failure "
    "here is one a later run may not meet."
)
"""The same in both modes: only its fix changes."""

THE_BACKLOG: Final = (
    f"{WHERE}: archives deferred by the daily download cap have grown for 2 runs in a row (hsld26 3)."
)
"""The same in both modes: only its fix changes."""

KEPT_IN_THE_CLOUD: Final = (
    " What the bucket confirmed is kept; the cloud run's working copy ends with its task."
)
KEPT_ON_THE_MAC: Final = " What was captured is kept."

FINISHED_WITH_A_FAILED_STAGE: Final = "caselist pull finished with a failed stage"


# ------------------------------------------------------------------------------------------------
# Records and details by hand
# ------------------------------------------------------------------------------------------------


def a_stopped_run(*, bucket: bool) -> Notification:
    """A run that stopped on a store that did not answer, before any stage recorded it."""
    record = a_record(outcome=SyncRunOutcome.FAILED).model_copy(update={"error_class": "StoreUnavailable"})
    details = details_of(bucket=bucket, failure_codes=("STORE_UNAVAILABLE",))
    return titled(sent_for(record, details), RETRIED)


def a_growing_backlog(*, bucket: bool) -> Notification:
    record = a_record(("download", "completed"), outcome=SyncRunOutcome.COMPLETED).model_copy(
        update={"deferred_by_caselist": {"hsld26": 3}, "backlog_growing": ("hsld26",)}
    )
    return titled(sent_for(record, details_of(bucket=bucket)), "caselist backlog growing")


MIXED_FAILURES: Final = {
    "import_beside_publish": (
        (("download", "completed"), ("import", "failed"), ("publish", "failed")),
        ("import", "publish"),
        RETRIED,
        ": the import stage failed on STORE_UNAVAILABLE; the publish stage failed on STORE_UNAVAILABLE. "
        "The next scheduled run should retry it: every failure here is one a later run may not meet.",
    ),
    "download_alone": (
        (("download", "failed"), ("import", "completed"), ("publish", "completed")),
        ("download",),
        RETRIED,
        ": the download stage failed on STORE_UNAVAILABLE. The next scheduled run should retry it: every "
        "failure here is one a later run may not meet.",
    ),
    "report_alone": (
        (("publish", "completed"), ("report", "failed")),
        ("report",),
        FINISHED_WITH_A_FAILED_STAGE,
        ": the report stage failed on STORE_UNAVAILABLE.",
    ),
    "parse_beside_publish": (
        (("publish", "failed"), ("parse", "failed")),
        ("publish", "parse"),
        RETRIED,
        ": the publish stage failed on STORE_UNAVAILABLE; the parse stage failed on STORE_UNAVAILABLE. "
        "The next scheduled run should retry it: every failure here is one a later run may not meet.",
    ),
}
"""Every failed-stage banner whose fix was the pull: more than the publish alone or the parse alone.
Each: the record's stages, the stages that failed (each on `STORE_UNAVAILABLE`), the banner's title
and its message after `Run <id> (<environment>)` up to its last sentence."""


def a_failed_stage(case: str, *, bucket: bool) -> Notification:
    stages, failed, title, _ = MIXED_FAILURES[case]
    record = a_record(*stages, outcome=SyncRunOutcome.FAILED)
    details = details_of(
        *(StageDetails(stage=stage, error_codes=("STORE_UNAVAILABLE",)) for stage in failed),
        bucket=bucket,
        failure_codes=("STORE_UNAVAILABLE",),
    )
    return titled(sent_for(record, details), title)


# ------------------------------------------------------------------------------------------------
# A run that stopped on an error
# ------------------------------------------------------------------------------------------------


def test_a_bucket_mode_run_that_stopped_names_the_next_cloud_run() -> None:
    banner = a_stopped_run(bucket=True)

    assert banner.message == THE_STOPPED_RUN
    assert banner.fix_command == THE_UNFINISHED_RUN_CURE_IN_THE_CLOUD
    assert points_at_the_mac(banner.text) == []


def test_a_local_mode_run_that_stopped_is_unchanged() -> None:
    banner = a_stopped_run(bucket=False)

    assert banner.message == THE_STOPPED_RUN
    assert banner.fix_command == THE_UNFINISHED_RUN_CURE_ON_THE_MAC
    assert "cloud" not in banner.text


# ------------------------------------------------------------------------------------------------
# A failed-stage banner whose failed stages are more than the publish alone
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("case", list(MIXED_FAILURES))
def test_a_bucket_mode_failed_stage_beyond_the_publish_names_the_next_cloud_run(case: str) -> None:
    """`v1-e40-t25`'s `test_a_bucket_mode_publish_that_failed_beside_another_stage_keeps_its_fix` pinned
    the first case's pull and "What was captured is kept."; this task changes both, deliberately."""
    banner = a_failed_stage(case, bucket=True)

    assert banner.message == WHERE + MIXED_FAILURES[case][3] + KEPT_IN_THE_CLOUD
    assert banner.fix_command == THE_UNFINISHED_RUN_CURE_IN_THE_CLOUD
    assert points_at_the_mac(banner.text) == []


@pytest.mark.parametrize("case", list(MIXED_FAILURES))
def test_a_local_mode_failed_stage_beyond_the_publish_is_unchanged(case: str) -> None:
    banner = a_failed_stage(case, bucket=False)

    assert banner.message == WHERE + MIXED_FAILURES[case][3] + KEPT_ON_THE_MAC
    assert banner.fix_command == THE_UNFINISHED_RUN_CURE_ON_THE_MAC
    assert "cloud" not in banner.text


def test_a_bucket_mode_parse_stage_that_failed_alone_keeps_its_cure_and_its_sentence() -> None:
    """The parse alone has its own cure (`v1-e40-t18`), and what it captured is in the bucket: only the
    parsed store waits. Neither changes here."""
    record = a_record(("publish", "completed"), ("parse", "failed"), outcome=SyncRunOutcome.COMPLETED)
    details = details_of(StageDetails(stage="parse", error_codes=("STORE_UNAVAILABLE",)), bucket=True)

    banner = titled(sent_for(record, details), FINISHED_WITH_A_FAILED_STAGE)

    assert banner.message == f"{WHERE}: the parse stage failed on STORE_UNAVAILABLE.{KEPT_ON_THE_MAC}"
    assert banner.fix_command == (
        "the next cloud run publishes the parsed store of each caselist the parse stage names: the "
        'weekly run, or one started by hand (caselist-cloud-run.md, "A failed parse stage"); never a '
        "publish from the operator's Mac"
    )


# ------------------------------------------------------------------------------------------------
# The backlog banner
# ------------------------------------------------------------------------------------------------


def test_a_bucket_mode_growing_backlog_names_the_next_cloud_run() -> None:
    banner = a_growing_backlog(bucket=True)

    assert banner.message == THE_BACKLOG
    assert banner.fix_command == THE_BACKLOG_CURE_IN_THE_CLOUD
    assert points_at_the_mac(banner.text) == []


def test_a_local_mode_growing_backlog_is_unchanged() -> None:
    banner = a_growing_backlog(bucket=False)

    assert banner.message == THE_BACKLOG
    assert banner.fix_command == THE_BACKLOG_CURE_ON_THE_MAC
    assert "cloud" not in banner.text


# ------------------------------------------------------------------------------------------------
# No bucket-mode banner names the pull
# ------------------------------------------------------------------------------------------------


def every_bucket_mode_banner() -> list[Notification]:
    """One of each banner this file and `v1-e40-t25`'s cover, built in bucket mode."""
    return [
        a_stopped_run(bucket=True),
        a_growing_backlog(bucket=True),
        *(a_failed_stage(case, bucket=True) for case in MIXED_FAILURES),
    ]


def test_no_bucket_mode_banner_here_names_a_command_on_this_machine() -> None:
    """Below its title, which names the command whose run it is, a banner's whole text."""
    named = {banner.title: points_at_the_mac(banner.text) for banner in every_bucket_mode_banner()}

    assert named == {banner.title: [] for banner in every_bucket_mode_banner()}
    assert all("debate-research" not in banner.text for banner in every_bucket_mode_banner())


# ------------------------------------------------------------------------------------------------
# The runbook sections the banners name are there
# ------------------------------------------------------------------------------------------------


def test_the_runbook_sections_the_new_cures_name_are_there_and_quote_them() -> None:
    failed_or_stopped = section("A failed or stopped run")
    assert f"> Fix: {THE_UNFINISHED_RUN_CURE_IN_THE_CLOUD}" in failed_or_stopped
    assert KEPT_IN_THE_CLOUD.strip() in failed_or_stopped

    backlog = section("A backlog growing")
    assert f"> Fix: {THE_BACKLOG_CURE_IN_THE_CLOUD}" in backlog
