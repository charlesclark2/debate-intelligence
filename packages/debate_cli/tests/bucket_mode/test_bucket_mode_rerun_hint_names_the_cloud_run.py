"""In bucket mode the command's own "run the same command again" names the next cloud run (`v1-e40-t28`).

`caselist pull` ends a run with a failed stage with a hint of its own, under the panel and in the
`--json` envelope's error. After a stage's own fix it said "Then run the same command again: what was
captured is kept.", and after a failed download or any other stage "Run the same command again". In a
cloud run the command is the task's, which has ended, and what it captured and did not publish ended
with it (ADR-0020 (3), "What is not saved"). In bucket mode, as the composition root's bracket says,
each names the next cloud run instead, in the words the banners use. Local mode keeps every word.
`v1-e40-t25`'s publish hint is `test_bucket_mode_publish_hint_names_the_cloud_run.py`'s; the banners
are `test_caselist_sync_bucket_mode_banners_name_the_next_cloud_run.py`'s, under
`packages/debate_core/tests/application/caselist/`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

import pytest
from tests.fixtures.parse_pipeline.build_parse_world import CASELIST

from debate_cli.commands.caselist_pull import _pull_failure  # pyright: ignore[reportPrivateUsage]
from debate_core.application.caselist_sync import RunSummary, StageOutcome, StageRecord, SyncStage

TRANSIENT: Final = (
    "Transient: every failure here is one a later run may not meet, and the next scheduled run retries it. "
)
THE_UNFINISHED_RUN_CURE: Final = (
    "the next cloud run takes up what this run did not finish, from the run state saved in the bucket: "
    'the weekly run, or one started by hand (caselist-cloud-run.md, "A failed or stopped run"); never a '
    "publish from the operator's Mac"
)
A_STAGES_OWN_FIX: Final = (
    "This machine refused the inbox directory: check that this user can read and write it, under the "
    "environment's data directory (storage.data_dir)."
)
"""A fix as a refused stage carries it; any sentence of this project's own would do."""

NEXT_STEPS: Final = {
    "after_a_stages_own_fix": (
        StageRecord(
            SyncStage.IMPORT,
            StageOutcome.FAILED,
            "a sentence",
            error_codes=("STORE_ACCESS_DENIED",),
            hint=A_STAGES_OWN_FIX,
        ),
        f"{A_STAGES_OWN_FIX} Then in bucket mode {THE_UNFINISHED_RUN_CURE}.",
        f"{A_STAGES_OWN_FIX} Then run the same command again: what was captured is kept.",
    ),
    "a_failed_download": (
        StageRecord(
            SyncStage.DOWNLOAD, StageOutcome.FAILED, "a sentence", error_codes=("PROVIDER_UNAVAILABLE",)
        ),
        f"{TRANSIENT}In bucket mode {THE_UNFINISHED_RUN_CURE}.",
        f"{TRANSIENT}Nothing that did download was lost: it is in the inbox and imported. Run the same "
        "command again — an archive already held is not fetched twice.",
    ),
    "any_other_stage": (
        StageRecord(SyncStage.IMPORT, StageOutcome.FAILED, "a sentence", error_codes=("UNREADABLE_ARCHIVE",)),
        f"In bucket mode {THE_UNFINISHED_RUN_CURE}.",
        "Run the same command again; every stage is idempotent.",
    ),
}
"""Each: the failed stage, the next step in bucket mode, and in local mode (as before, word for word)."""


def a_run_that_failed(stage: StageRecord) -> RunSummary:
    started = datetime(2026, 9, 16, 6, 0, tzinfo=UTC)
    return RunSummary(
        run_id="20260916T060000Z",
        started_at=started,
        finished_at=started,
        dry_run=False,
        caselists=(CASELIST,),
        stages=(stage,),
    )


@pytest.mark.parametrize("case", list(NEXT_STEPS))
def test_a_bucket_mode_next_step_names_the_next_cloud_run(case: str) -> None:
    stage, in_the_cloud, _ = NEXT_STEPS[case]

    hint = _pull_failure(a_run_that_failed(stage), {}, bucket_mode=True).hint

    assert hint == in_the_cloud
    assert hint is not None
    for on_this_machine in (
        "same command again",
        "caselist pull",
        "what was captured is kept",
        "in the inbox",
    ):
        assert on_this_machine not in hint


@pytest.mark.parametrize("case", list(NEXT_STEPS))
def test_a_local_mode_next_step_is_unchanged(case: str) -> None:
    stage, _, on_the_mac = NEXT_STEPS[case]

    hint = _pull_failure(a_run_that_failed(stage), {}, bucket_mode=False).hint

    assert hint == on_the_mac
