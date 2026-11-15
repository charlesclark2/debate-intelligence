"""The "Model cost:" line under an auto-cut table, and the report's two costs (v1-e08-t22).

The PM's wording (2026-11-14): when the whole command spent more than its cuts, the line names both
figures and says which one `--max-cost` counts; when the two are the same at the line's precision, or
the command's is unknown, the line is as it was. The figures are the report's, which the application
read; nothing here computes one. The commands' own tests show it end to end; these pin the wording and
the comparison on hand-built reports.
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

FILES: Final = AutoCutFiles(report=Path("bundle.report.json"))


def entry(rank: int, cost_usd: float | None) -> BatchEntry:
    return BatchEntry(
        rank=rank,
        url=f"https://www.example.org/{rank}",
        title=f"Result {rank}",
        status=BatchEntryStatus.FAILED,
        card_status=None,
        access_status=AccessStatus.ACCESSIBLE,
        fetched=True,
        reasons=("PROVIDER_UNAVAILABLE",),
        cost_usd=cost_usd,
    )


def cost_line(*costs: float | None, command_cost_usd: float | None) -> str:
    report = BatchReport(
        wanted=1,
        entries=tuple(entry(rank, cost) for rank, cost in enumerate(costs, start=1)),
        stop_reason=BatchStopReason.CANDIDATES_EXHAUSTED,
        command_cost_usd=command_cost_usd,
    )
    table = batch_report_table(report, [], "Politics DA — Link", FILES, replay_is_the_default=False)
    [line] = [line for line in table.lines_below if line.startswith("Model cost:")]
    return line


def test_an_auto_cut_whose_command_cost_more_than_its_cuts_names_both_costs() -> None:
    assert cost_line(0.0125, 0.0025, command_cost_usd=0.0213) == (
        "Model cost: $0.0150 for the cuts, $0.0213 for the whole command "
        "(the --max-cost limit counts the whole command)"
    )


def test_an_auto_cut_whose_command_cost_its_cuts_keeps_the_cost_line() -> None:
    assert cost_line(0.0125, 0.0025, command_cost_usd=0.015) == "Model cost: $0.0150"


def test_an_auto_cut_cost_differing_below_the_lines_precision_keeps_the_cost_line() -> None:
    """Float sums in another order: the run's total and the entries' differ in the last bits."""
    assert cost_line(0.1, 0.2, command_cost_usd=0.30000000000000004 + 1e-9) == "Model cost: $0.3000"


def test_an_auto_cut_whose_command_cost_is_unknown_keeps_the_cost_line() -> None:
    assert cost_line(0.0125, 0.0025, command_cost_usd=None) == "Model cost: $0.0150"


def test_an_unpriced_auto_cut_cost_keeps_the_cost_line() -> None:
    assert cost_line(0.0125, None, command_cost_usd=None) == "Model cost: unpriced"
