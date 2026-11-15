"""The line under an auto-cut table that counts the results refused under the replay default.

The PM's ruling of 2026-11-14 on v1-e06-t09. The presenter is told by the command, from the container,
whether replay is only the default; it counts the FAILED entries whose reason is MISSING_FIXTURE_ERROR,
and says nothing when there are none. The commands' own tests show it end to end; these pin the count
and the wording on hand-built reports.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from debate_cli.presenters.batch_report_presenter import AutoCutFiles, batch_report_table
from debate_core.application.batch_cut_service import (
    BatchEntry,
    BatchEntryStatus,
    BatchReport,
    BatchStopReason,
)
from debate_core.domain import AccessStatus

from .model_mode_hints import REFUSED_UNDER_THE_DEFAULT_WORDS, refused_under_the_default_line

FILES: Final = AutoCutFiles(report=Path("bundle.report.json"))


def entry(rank: int, status: BatchEntryStatus, *reasons: str) -> BatchEntry:
    return BatchEntry(
        rank=rank,
        url=f"https://www.example.org/{rank}",
        title=f"Result {rank}",
        status=status,
        card_status=None,
        access_status=AccessStatus.ACCESSIBLE,
        fetched=True,
        reasons=reasons,
    )


REPORT: Final = BatchReport(
    wanted=2,
    entries=(
        entry(1, BatchEntryStatus.FAILED, "MISSING_FIXTURE_ERROR"),
        entry(2, BatchEntryStatus.FAILED, "PROVIDER_UNAVAILABLE"),
        entry(3, BatchEntryStatus.SKIPPED, "SOURCE_NOT_ACCESSIBLE"),
    ),
    stop_reason=BatchStopReason.CANDIDATES_EXHAUSTED,
)
"""One result refused for want of a recording, one for a provider that did not answer, one skipped."""


def test_one_refused_result_is_counted_in_the_singular_and_the_other_failures_are_not_counted() -> None:
    table = batch_report_table(REPORT, [], "Politics DA — Link", FILES, replay_is_the_default=True)

    refused = [line for line in table.lines_below if REFUSED_UNDER_THE_DEFAULT_WORDS in line]
    assert refused == [refused_under_the_default_line(1)]
    assert table.lines_below[-1] == refused_under_the_default_line(1), "the last line under the table"


def test_a_chosen_mode_prints_no_refused_line() -> None:
    table = batch_report_table(REPORT, [], "Politics DA — Link", FILES, replay_is_the_default=False)

    assert not any(REFUSED_UNDER_THE_DEFAULT_WORDS in line for line in table.lines_below)


def test_no_refused_result_prints_no_refused_line_under_the_default() -> None:
    report = BatchReport(
        wanted=1,
        entries=(entry(1, BatchEntryStatus.FAILED, "PROVIDER_UNAVAILABLE"),),
        stop_reason=BatchStopReason.CANDIDATES_EXHAUSTED,
    )

    table = batch_report_table(report, [], "Politics DA — Link", FILES, replay_is_the_default=True)

    assert not any(REFUSED_UNDER_THE_DEFAULT_WORDS in line for line in table.lines_below)
