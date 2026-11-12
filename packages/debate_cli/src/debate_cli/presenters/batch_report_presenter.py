"""What `search --auto-cut N` prints and writes: the per-result table and report.json (`v1-e08-t06`).

Rendering only. Which results were cut, skipped or failed, and why the run ended, are
:class:`~debate_core.application.batch_cut_service.BatchCutService`'s, read off its
:class:`~debate_core.application.batch_cut_service.BatchReport`; nothing here decides a status.

## The table

One row per result the batch tried, in rank order: its rank, URL, access status, card status, the
reason codes and the cost of its model calls. Below it, the search's provider footer (so a partial
search is never silent, even when N cards were verified), then where the bundle, its manifest and
report.json were written.

## report.json

:func:`report_payload`: the run's settings, why it ended, the providers that did not answer in full,
the total cost, the files, and every entry with its `section`, `verified` or `unverified`, which is
where its card is in the bundle. It is also the `auto_cut` object of the `--json` output. Like the
table it holds ranks, URLs, titles, statuses, codes, ids and costs: never evidence text, a tag or a
cite, which are the bundle's.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from debate_cli.exit_codes import ExitCode
from debate_cli.output import CommandFailure, JsonValue, TableSpec
from debate_cli.presenters.search_presenter import footer_lines
from debate_core.application.batch_cut_service import (
    BatchEntry,
    BatchNeed,
    BatchReport,
    BatchStopReason,
)
from debate_core.application.federated_search import partial_providers
from debate_core.application.federated_search_types import SearchOutcome

__all__ = [
    "AUTO_CUT_SHORT_CODE",
    "BUDGET_EXCEEDED_CODE",
    "AutoCutFiles",
    "AutoCutSettings",
    "batch_report_table",
    "entry_json",
    "exit_code_for_batch",
    "report_failure",
    "report_payload",
    "report_table",
]

AUTO_CUT_SHORT_CODE = "AUTO_CUT_SHORT"
BUDGET_EXCEEDED_CODE = "BUDGET_EXCEEDED"

_STOP_WORDS = {
    BatchStopReason.COMPLETE: "every card wanted is VERIFIED",
    BatchStopReason.CANDIDATES_EXHAUSTED: "every result was tried",
    BatchStopReason.ALL_REMAINING_INACCESSIBLE: "every other result was inaccessible",
    BatchStopReason.BUDGET_EXCEEDED: "the budget guard refused a model call",
}


@dataclass(frozen=True, slots=True)
class AutoCutSettings:
    """What the command line asked of the batch, as report.json records it."""

    wanted: int
    concurrency: int
    card_format: str
    max_cost_usd: float | None


@dataclass(frozen=True, slots=True)
class AutoCutFiles:
    """Where the batch wrote: the bundle and its manifest only when a card was cut, and report.json."""

    report: Path
    bundle: Path | None = None
    manifest: Path | None = None


def exit_code_for_batch(report: BatchReport) -> ExitCode:
    """0 only when N cards are VERIFIED; 9 when the budget stopped it short; 8 when the results ran out."""
    if report.complete:
        return ExitCode.OK
    if report.stop_reason is BatchStopReason.BUDGET_EXCEEDED:
        return ExitCode.BUDGET_EXCEEDED
    return ExitCode.AUTO_CUT_SHORT


def _cost(value: float | None) -> str:
    return "unpriced" if value is None else f"${value:.4f}"


def _partial_providers(outcome: SearchOutcome) -> list[str]:
    return list(partial_providers(outcome.provider_statuses, uncounted=outcome.uncounted))


def _section(entry: BatchEntry) -> str | None:
    """Where the entry's card is in the bundle: the verified block, the UNVERIFIED section, or nowhere."""
    if entry.result is None:
        return None
    return "verified" if entry.is_verified else "unverified"


def entry_json(entry: BatchEntry) -> dict[str, JsonValue]:
    """One entry of report.json: what became of one result the batch tried."""
    return {
        "rank": entry.rank,
        "url": entry.url,
        "title": entry.title,
        "status": entry.verdict,
        "section": _section(entry),
        "access_status": entry.access_status.value if entry.access_status is not None else None,
        "fetched": entry.fetched,
        "reasons": list(entry.reasons),
        "details": list(entry.details),
        "card_id": entry.card_id,
        "snapshot_id": entry.snapshot_id,
        "cost_usd": entry.cost_usd,
    }


def report_payload(
    report: BatchReport,
    outcome: SearchOutcome,
    need: BatchNeed,
    settings: AutoCutSettings,
    files: AutoCutFiles,
) -> dict[str, JsonValue]:
    """report.json, and the `auto_cut` object of the `--json` output."""
    return {
        "search_id": outcome.search.search_id,
        "query": outcome.search.query,
        "block": need.heading,
        "argument": need.argument,
        "need": need.need,
        "wanted": settings.wanted,
        "concurrency": settings.concurrency,
        "card_format": settings.card_format,
        "max_cost_usd": settings.max_cost_usd,
        "verified": len(report.verified),
        "unverified": len(report.unverified),
        "complete": report.complete,
        "stop_reason": report.stop_reason.value,
        "search_status": outcome.status.value,
        "partial_providers": list[JsonValue](_partial_providers(outcome)),
        "cost_usd": report.cost_usd,
        "bundle": str(files.bundle) if files.bundle is not None else None,
        "manifest": str(files.manifest) if files.manifest is not None else None,
        "report": str(files.report),
        "entries": [entry_json(entry) for entry in report.entries],
    }


def _title(report: BatchReport, heading: str) -> str:
    title = f"{len(report.verified)} of {report.wanted} cards VERIFIED for {heading}"
    return title if report.complete else f"SHORT: {title}"


def report_table(
    report: BatchReport, outcome: SearchOutcome, need: BatchNeed, files: AutoCutFiles
) -> TableSpec:
    """The per-result table, then the provider footer, the files and the total cost."""
    return batch_report_table(report, footer_lines(outcome), need.heading, files)


def batch_report_table(
    report: BatchReport, footer: list[str], heading: str, files: AutoCutFiles
) -> TableSpec:
    """:func:`report_table` over any footer: a search's, or a daily digest's (v1-e08-t07)."""
    rows = [
        (
            str(entry.rank),
            entry.url,
            entry.access_status.value if entry.access_status is not None else "",
            entry.verdict,
            ", ".join(entry.reasons),
            _cost(entry.cost_usd),
        )
        for entry in report.entries
    ]
    below = [*footer]
    if report.unverified:
        below.append(
            f"{len(report.unverified)} UNVERIFIED card(s) are in the bundle's own section, "
            '"UNVERIFIED — not finished cards", and count toward nothing.'
        )
    if files.bundle is not None and files.manifest is not None:
        below += [f"Bundle: {files.bundle}", f"Manifest: {files.manifest}"]
    below += [f"Report: {files.report}", f"Model cost: {_cost(report.cost_usd)}"]
    return TableSpec(
        columns=("Rank", "URL", "Access", "Card", "Reasons", "Cost"),
        rows=rows,
        title=_title(report, heading),
        caption=f"Stopped: {_STOP_WORDS[report.stop_reason]}.",
        lines_below=below,
    )


def report_failure(report: BatchReport, payload: dict[str, JsonValue], exit_code: ExitCode) -> CommandFailure:
    """The failure a batch short of N reports (8 or 9), carrying the whole result as its details."""
    verified = f"{len(report.verified)} of {report.wanted} cards VERIFIED"
    if exit_code is ExitCode.BUDGET_EXCEEDED:
        return CommandFailure(
            code=BUDGET_EXCEEDED_CODE,
            message=f"{verified}: the budget guard refused a model call, so the run stopped",
            exit_code=exit_code,
            details=payload,
            panel_details={"stop_reason": report.stop_reason.value, "cost_usd": report.cost_usd},
            hint="The cards already cut are in the bundle. A higher --max-cost, or another day, may "
            "finish it.",
        )
    return CommandFailure(
        code=AUTO_CUT_SHORT_CODE,
        message=f"{verified}: {_STOP_WORDS[report.stop_reason]}",
        exit_code=exit_code,
        details=payload,
        panel_details={"stop_reason": report.stop_reason.value, "cost_usd": report.cost_usd},
        hint="Try a broader query, a larger --max-results, or cut a paywalled source from your own copy "
        "with fetch --paste and cut --from-paste.",
    )
