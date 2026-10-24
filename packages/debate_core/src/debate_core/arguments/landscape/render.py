"""The landscape report's three files: report.md, positions.csv and top_cards.csv (`v1-e32-t03`).

Pure and deterministic: the same :class:`~debate_core.domain.landscape_report.LandscapeReport`
renders to the same bytes, in the report's own order (positions by side, kind, teams, rounds and
id; cards by rank). Nothing here computes a count; the service did.

## The files

* **report.md** is for the weekly prep meeting: what the report was built from and how to read its
  numbers, the positions by side and kind, what is new since the previous snapshot, and what could
  not be counted. `v1-e34-t03`'s stale-data banner goes above it when the data is stale; the service
  puts it there. It lists no cards: the coach's review of 2026-10-24 found the most-read cards of
  every position no help in a prep meeting, so they are in top_cards.csv only.
* **positions.csv** has the positions' rows for a spreadsheet, and **top_cards.csv** each position's
  most-read cards. Each starts with a header block, one `# key=value` line per fact (the staleness
  hook's `stale=` among them), and then an ordinary CSV with a header row.

## What is written exactly, and what is escaped

A card's tag and short cite are written exactly as parsed in the CSV. A position's label in Markdown,
where a `|` would split a table cell and a `*` start emphasis, has those characters escaped with a
backslash and runs of whitespace made one space, so the cell shows the same text. Shares are
fractions to three places in the CSV and percentages to one place in Markdown, both rounded half up;
Markdown writes counts with thousands separators, the CSV without.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable, Mapping, Sequence
from decimal import ROUND_HALF_UP, Decimal
from itertools import groupby
from typing import Final

from debate_core.domain.landscape import PositionKind, PositionSide
from debate_core.domain.landscape_report import (
    PLACED_CARD_METHOD,
    LandscapeReport,
    PositionStats,
)

__all__ = [
    "POSITION_COLUMNS",
    "TOP_CARD_COLUMNS",
    "header_metadata",
    "render_markdown",
    "render_positions_csv",
    "render_top_cards_csv",
]

POSITION_COLUMNS: Final = (
    "position_id",
    "label",
    "kind",
    "rounds",
    "teams",
    "aff_rounds",
    "neg_rounds",
    "first_seen_snapshot",
    "is_new",
    "share_of_teams",
)
"""positions.csv's columns, in order (ac1)."""

TOP_CARD_COLUMNS: Final = (
    "position_id",
    "rank",
    "fingerprint",
    "teams_reading",
    "tag",
    "short_cite",
    "source_object_key",
    "element_index",
    "source_snapshot",
    "provenance_mode",
)
"""top_cards.csv's columns, in order (ac2)."""

_SIDE_HEADINGS: Final = {
    PositionSide.AFF: "Affirmative positions",
    PositionSide.NEG: "Negative positions",
    PositionSide.BOTH: "Positions either side reads",
}
_KIND_HEADINGS: Final = {
    PositionKind.AFF: "Affs",
    PositionKind.ADVANTAGE: "Advantages",
    PositionKind.DA: "Disadvantages",
    PositionKind.CP: "Counterplans",
    PositionKind.K: "Kritiks",
    PositionKind.T: "Topicality",
    PositionKind.THEORY: "Theory",
    PositionKind.VALUE: "Values",
    PositionKind.CRITERION: "Criteria",
    PositionKind.CONTENTION: "Contentions",
    PositionKind.RESPONSE: "Responses",
}
_METHOD_LABELS: Final = {PLACED_CARD_METHOD: "A card in the round placed under the aff"}
_MARKDOWN_SPECIAL: Final = re.compile(r"([\\`*_\[\]<>|])")
_WHITESPACE: Final = re.compile(r"\s+")
_THOUSANDTH: Final = Decimal("0.001")
_TENTH: Final = Decimal("0.1")


def header_metadata(report: LandscapeReport) -> dict[str, str]:
    """The facts every CSV's header block records, in order; the staleness hook adds its own."""
    header = report.header
    return {
        "caselist": header.caselist,
        "snapshot": header.snapshot.isoformat(),
        "previous_snapshot": header.previous_snapshot.isoformat() if header.previous_snapshot else "",
        "topic_id": header.topic_id,
        "taxonomy_version": header.taxonomy_version,
        "overrides_digest": header.overrides_digest,
        "parser_version": header.parser_version,
        "prompt_version": header.prompt_version,
        "review_threshold": f"{header.review_threshold:g}",
        "coverage_cards": f"{header.cards_placed}/{header.cards}",
        "coverage_rounds": f"{header.rounds_with_a_read}/{header.rounds}",
        "share_of_teams_over": (
            f"teams disclosing on the position's side: aff {header.aff_teams}, neg {header.neg_teams}, "
            f"either side {header.teams}"
        ),
        "provenance_mode": header.provenance_mode.value,
    }


def render_positions_csv(report: LandscapeReport, metadata: Mapping[str, str]) -> str:
    """positions.csv: the header block, then one row per position read."""
    return _csv(
        metadata,
        "positions",
        POSITION_COLUMNS,
        (
            (
                stats.position_id,
                stats.label,
                stats.kind.value,
                str(stats.rounds),
                str(stats.teams),
                str(stats.aff_rounds),
                str(stats.neg_rounds),
                stats.first_seen_snapshot.isoformat(),
                "true" if stats.is_new else "false",
                _fraction(*stats.share_of_teams),
            )
            for stats in report.positions
        ),
    )


def render_top_cards_csv(report: LandscapeReport, metadata: Mapping[str, str]) -> str:
    """top_cards.csv: the header block, then each position's most-read cards by rank."""
    return _csv(
        metadata,
        "top_cards",
        TOP_CARD_COLUMNS,
        (
            (
                card.position_id,
                str(card.rank),
                card.fingerprint,
                str(card.teams_reading),
                card.tag or "",
                card.short_cite or "",
                card.source_object_key,
                str(card.element_index),
                card.source_snapshot.isoformat(),
                card.provenance_mode.value,
            )
            for card in report.top_cards
        ),
    )


def _csv(
    metadata: Mapping[str, str], name: str, columns: Sequence[str], rows: Iterable[Sequence[str]]
) -> str:
    out = io.StringIO()
    out.write(f"# report={name}\n")
    for key, value in metadata.items():
        out.write(f"# {key}={_one_line(value)}\n")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return out.getvalue()


def render_markdown(report: LandscapeReport) -> str:
    """report.md, without the stale-data banner: the service passes it through the hook."""
    lines: list[str] = []
    lines += _header_section(report)
    lines += _positions_section(report.positions)
    lines += _new_section(report)
    lines += _unclassified_section(report)
    return "\n".join(lines).rstrip("\n") + "\n"


def _header_section(report: LandscapeReport) -> list[str]:
    header = report.header
    previous = header.previous_snapshot.isoformat() if header.previous_snapshot else "none (the first)"
    freshness = (
        f"Stale: the newest snapshot is {header.newest_snapshot.isoformat()}, "
        f"{header.snapshot_age_days} day(s) old (see the banner above)"
        if header.stale
        else f"Current: the newest snapshot is {header.newest_snapshot.isoformat()}, "
        f"{header.snapshot_age_days} day(s) old"
    )
    prompt = (
        f"{header.prompt_version} (deterministic classification, no model)"
        if header.prompt_version == "none"
        else header.prompt_version
    )
    return [
        f"# Argument landscape: {header.caselist} through {header.snapshot.isoformat()}",
        "",
        "Every count comes from files teams disclosed to the caselist (FILE_IMPORT), not from evidence "
        "the platform has verified. No school, team or debater is named.",
        "",
        "## About this report",
        "",
        "| | |",
        "|---|---|",
        f"| Caselist | {header.caselist} |",
        f"| Snapshot | {header.snapshot.isoformat()} (previous: {previous}) |",
        f"| Topic | {header.topic_id} |",
        f"| Taxonomy version | {header.taxonomy_version} |",
        f"| Coach's overrides | {header.overrides_digest} |",
        f"| Parser version | {header.parser_version} |",
        f"| Prompt version | {prompt} |",
        f"| Classification coverage | {_of(header.cards_placed, header.cards, 'cards')}; "
        f"{_of(header.rounds_with_a_read, header.rounds, 'rounds')} |",
        f"| Review threshold | {header.review_threshold:g} |",
        f"| Disclosures counted | {header.rounds:,} rounds by {header.teams:,} teams: "
        f"{header.aff_rounds:,} aff rounds by {header.aff_teams:,} teams, "
        f"{header.neg_rounds:,} neg rounds by {header.neg_teams:,} teams |",
        f"| Data freshness | {freshness} |",
        "",
        "How to read the numbers:",
        "",
        "* **Rounds** are disclosed rounds: one team, one side, one tournament round. A round reads a "
        "position when one of its cards is placed under it at or above the review threshold.",
        "* **Teams** are distinct teams, on any side.",
        "* **Share of teams** is the teams that read a position on its own side, over the teams that "
        f"disclosed on that side through {header.snapshot.isoformat()}: {header.aff_teams:,} on the "
        f"affirmative, {header.neg_teams:,} on the negative, and all {header.teams:,} for a position either "
        "side reads.",
        "* **New** means first disclosed after the previous snapshot."
        if header.previous_snapshot
        else "* **New** means first disclosed after the previous snapshot; this is the first, so "
        "nothing is marked new.",
        "* A card under an `AT:` heading answers a position and never counts as reading it, and so does "
        "a card placed under a position in a round on the other side: a `Midterms DA` block in an "
        "affirmative file is the 2AC answering it.",
        f"* Each position's {report.header.top_cards_per_position:,} most-read cards are in `top_cards.csv`, "
        "where near-duplicate copies of a card count as one card.",
        "",
    ]


def _positions_section(positions: Sequence[PositionStats]) -> list[str]:
    if not positions:
        return ["## Positions", "", "No position was read in this range.", ""]
    lines: list[str] = []
    for side, on_side in groupby(positions, key=lambda stats: stats.side):
        lines += [f"## {_SIDE_HEADINGS[side]}", ""]
        for kind, of_kind in groupby(on_side, key=lambda stats: stats.kind):
            lines += [
                f"### {_KIND_HEADINGS[kind]}",
                "",
                "| Position | Rounds | Teams | Aff rounds | Neg rounds | Share of teams | First seen | New |",
                "|---|---|---|---|---|---|---|---|",
            ]
            lines += [
                f"| {_cell(stats.label)} (`{stats.position_id}`) | {stats.rounds:,} | {stats.teams:,} | "
                f"{stats.aff_rounds:,} | {stats.neg_rounds:,} | {_percent(*stats.share_of_teams)} | "
                f"{stats.first_seen_snapshot.isoformat()} | {'yes' if stats.is_new else ''} |"
                for stats in of_kind
            ]
            lines.append("")
    return lines


def _new_section(report: LandscapeReport) -> list[str]:
    previous = report.header.previous_snapshot
    lines = ["## New this week", ""]
    if previous is None:
        return [*lines, "This is the caselist's first snapshot, so nothing is marked new.", ""]
    new = [stats for stats in report.positions if stats.is_new]
    if not new:
        return [*lines, f"No position was first disclosed after {previous.isoformat()}.", ""]
    lines += [f"Positions first disclosed after {previous.isoformat()}:", ""]
    lines += [
        f"* {_cell(stats.label)} (`{stats.position_id}`, {stats.kind.value}): "
        f"{_count(stats.rounds, 'round')}, {_count(stats.teams, 'team')}"
        for stats in new
    ]
    return [*lines, ""]


def _unclassified_section(report: LandscapeReport) -> list[str]:
    summary = report.unclassified
    threshold = f"{report.header.review_threshold:g}"
    lines = [
        "## Unclassified",
        "",
        "What this report could not count:",
        "",
        f"* **Cards:** {_of(summary.unclassified_cards, summary.cards)}: "
        f"{summary.unplaced_cards:,} waiting in the review queue, {summary.below_threshold_cards:,} placed "
        f"below the review threshold ({threshold}).",
        f"* **Aff rounds with no identified aff:** "
        f"{_of(summary.aff_rounds_unidentified, summary.aff_rounds)}.",
        f"* **Neg rounds with no placed negative position:** "
        f"{_of(summary.neg_rounds_unplaced, summary.neg_rounds)}.",
    ]
    if summary.other_side_position_rounds:
        lines.append(
            f"* Counted as answers, not reads: {_count(summary.other_side_position_rounds, 'round')} that "
            "placed a card under a position of the other side, counted once per position."
        )
    if summary.decided_no_position_cards:
        lines.append(
            f"* Not counted and not queued: {_count(summary.decided_no_position_cards, 'card')} under "
            "headings the coach ruled name no position."
        )
    lines += [
        "",
        "How affirmative rounds were identified:",
        "",
        "| Method | Aff rounds |",
        "|---|---|",
    ]
    lines += [
        f"| {_METHOD_LABELS.get(one.method, one.method)} (`{one.method}`) | {one.rounds:,} |"
        for one in report.aff_identification
    ]
    lines += [f"| Not identified | {summary.aff_rounds_unidentified:,} |", ""]
    return lines


def _cell(text: str) -> str:
    return _MARKDOWN_SPECIAL.sub(r"\\\1", _WHITESPACE.sub(" ", text).strip())


def _one_line(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number:,} {noun}s"


def _of(part: int, whole: int, noun: str = "") -> str:
    """`31 of 42 cards (73.8%)`, or without a noun `10 of 42 (23.8%)`."""
    counted = f"{whole:,} {noun}" if noun else f"{whole:,}"
    return f"{part:,} of {counted} ({_percent(part, whole)})"


def _percent(part: int, whole: int) -> str:
    if whole == 0:
        return "n/a"
    return f"{(Decimal(100 * part) / Decimal(whole)).quantize(_TENTH, rounding=ROUND_HALF_UP)}%"


def _fraction(part: int, whole: int) -> str:
    if whole == 0:
        return ""
    return str((Decimal(part) / Decimal(whole)).quantize(_THOUSANDTH, rounding=ROUND_HALF_UP))
