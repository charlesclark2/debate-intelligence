"""The landscape report's files: report.md, positions.csv, top_cards.csv (`v1-e32-t03`), and the rest.

impact_cards.csv is `v1-e32-t10`'s; trends.csv and the school view's schools.csv and schools.md are
`v1-e32-t04`'s.

Pure and deterministic: the same :class:`~debate_core.domain.landscape_report.LandscapeReport`
renders to the same bytes, in the report's own order (positions by side, kind, teams, rounds and
id; cards by rank). Nothing here computes a count; the service did.

## The files

* **report.md** is for the weekly prep meeting: what the report was built from and how to read its
  numbers, the positions by side and kind, what is new since the previous snapshot, and what could
  not be counted. `v1-e34-t03`'s stale-data banner goes above it when the data is stale; the service
  puts it there. Of the cards, it lists only each advantage's and DA's impact cards, under its kind's
  table (`v1-e32-t10`): the coach's review of 2026-10-24 found the most-read cards of every position
  no help in a prep meeting, so they are in top_cards.csv only, and asked for the impacts instead.
  When the run read the caselist's analytic texts (`v1-e32-t11`), it shows each CP's and K's top texts
  word for word, the teams reading each and what could not be shown, then each position's overview
  count, with no overview text. The texts are in report.md only, never beside a school or team code.
* **positions.csv** has the positions' rows for a spreadsheet, **top_cards.csv** each position's
  most-read cards, and **impact_cards.csv** each advantage's and DA's impact cards, with how many
  documents of each kind carry no labelled impact in its header block. **trends.csv** has each
  position read this week or the week before, with its weekly teams and shares, its delta and its
  label (`v1-e32-t04`). Each starts with a header block, one `# key=value` line per fact (the
  staleness hook's `stale=` among them), and then an ordinary CSV with a header row.
* report.md's **New this week**, **Rising** and **Falling** sections are the trends', and it says on
  its face when its windows span less than a full topic cycle, or when the topic changed.
* **schools.csv** and **schools.md** are the per-school view (`v1-e32-t04`): the only files that name
  a school or a team code, exactly as disclosed, and nothing more (`docs/policies/caselist-data-use.md`,
  "What a report may show"). They show position ids and counts only: no label, tag, cite or text. The
  circuit-wide files above name nobody, so the view is kept out of them. Since policy 1.14 they also
  link each team's public OpenCaselist page (`v1-e32-t18`), schools.csv in its `team_page` column and
  schools.md in its **By position** section, which lists under each position, by kind, the teams that
  read it. No circuit-wide file carries a link.

## What is written exactly, and what is escaped

A card's tag and short cite are written exactly as parsed in the CSV. A position's label, an
impact card's tag and cite, and a quoted CP text, alternative or role of the ballot, in Markdown,
where a `|` would split a table cell and a `*` start emphasis, have those characters escaped with a
backslash and runs of whitespace made one space, so the cell shows the same text. Shares are
fractions to three places in the CSV and percentages to one place in Markdown, both rounded half up;
a delta is percentage points to one place, rounded half up, in both. Markdown writes counts with
thousands separators, the CSV without. A school or team code in schools.md is escaped
as a label is.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from itertools import groupby
from typing import Final

from debate_core.arguments.landscape.aff_assignment import PLAN_TEXT_METHOD, TEAM_CARRY_METHOD
from debate_core.domain.landscape import PositionKind, PositionSide
from debate_core.domain.landscape_report import (
    IMPACT_KINDS,
    PLACED_CARD_METHOD,
    ImpactCoverage,
    LandscapeReport,
    PositionStats,
    TopCard,
)
from debate_core.domain.landscape_schools import SchoolRow, SchoolView
from debate_core.domain.landscape_texts import QUOTED_KINDS, AnalyticTextKind, TextCoverage
from debate_core.domain.landscape_trends import (
    WINDOW_DAYS,
    LandscapeTrends,
    TrendLabel,
    TrendRow,
    WeeklyTeams,
    window_start,
)
from debate_core.domain.search_source_links import NoTeamPage

__all__ = [
    "IMPACT_CARD_COLUMNS",
    "POSITION_COLUMNS",
    "SCHOOL_COLUMNS",
    "TOP_CARD_COLUMNS",
    "TREND_COLUMNS",
    "header_metadata",
    "render_impact_cards_csv",
    "render_markdown",
    "render_positions_csv",
    "render_schools_csv",
    "render_schools_markdown",
    "render_top_cards_csv",
    "render_trends_csv",
    "trend_metadata",
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

IMPACT_CARD_COLUMNS: Final = TOP_CARD_COLUMNS
"""impact_cards.csv's columns: a top card's, of the cluster's labelled copies (`v1-e32-t10`)."""

TREND_COLUMNS: Final = (
    "position_id",
    "label",
    "kind",
    "weekly_teams",
    "weekly_share",
    "previous_teams",
    "previous_share",
    "delta_points",
    "trend_label",
    "held_back_by_team_floor",
)
"""trends.csv's columns, in order (`v1-e32-t04` ac1)."""

SCHOOL_COLUMNS: Final = ("school", "team_code", "side", "position_id", "rounds", "team_page")
"""schools.csv's columns, in order (`v1-e32-t04` ac4, as the PM's ruling of 2026-10-24 amended it, and
`v1-e32-t18`'s `team_page`: the team's openCaselist page, or empty)."""

_SCHOOL_VIEW_SHOWS: Final = (
    "school and team code as disclosed, and the team's public openCaselist page, never more "
    "(docs/policies/caselist-data-use.md, version 1.14); for the team only"
)
_NO_TEAM_PAGE: Final = {
    NoTeamPage.UNREAD: "whose school or team code could not be read",
    NoTeamPage.CASELIST: "whose caselist is no address word",
    NoTeamPage.SCHOOL: "whose school is not one address word",
    NoTeamPage.TEAM_CODE: "whose team code is not one address word",
}
"""Why a team has no page link, as the school view counts it, in the order the rule checks."""
_BY_POSITION_SIDES: Final = (PositionSide.NEG, PositionSide.AFF, PositionSide.BOTH)
"""The by-position section's order (`v1-e32-t18`): the negative's DAs, CPs, Ks and Ts, then the aff's."""
_BY_POSITION_SIDE_PREFIXES: Final = {
    PositionSide.NEG: "",
    PositionSide.AFF: "Affirmative side: ",
    PositionSide.BOTH: "Either side: ",
}

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
_IMPACT_NOUNS: Final = {PositionKind.ADVANTAGE: "Advantage", PositionKind.DA: "DA"}
"""How the line on documents with no labelled impact names each kind's documents."""
_METHOD_LABELS: Final = {
    PLACED_CARD_METHOD: "A card in the round placed under the aff",
    PLAN_TEXT_METHOD: "The round's plan text names the aff",
    TEAM_CARRY_METHOD: "The team's other rounds name the aff",
}
_TEXT_KINDS: Final = {
    AnalyticTextKind.CP_TEXT: (
        "Counterplan texts",
        "a CP-text label (`Text:`, `CP Text`) or as the first `should` analytic of a block placed under a CP",
        "a CP",
    ),
    AnalyticTextKind.K_ALTERNATIVE: (
        "Kritik alternatives",
        "an alternative label (`Alt`, `The alternative is`)",
        "a K",
    ),
    AnalyticTextKind.ROLE_OF_THE_BALLOT: (
        "Roles of the ballot",
        "a role-of-the-ballot label (`Role of the ballot`, `ROB`, `The role of the ballot is`)",
        "a K",
    ),
}
"""Each quoted kind's heading, what finds it, and what it must be placed under (`v1-e32-t11`)."""
_TEXT_NOUNS: Final = {
    AnalyticTextKind.CP_TEXT: "CP text",
    AnalyticTextKind.K_ALTERNATIVE: "alternative",
    AnalyticTextKind.ROLE_OF_THE_BALLOT: "role of the ballot",
}
_TITLES_NOT_READ: Final = "The caselist's own round titles and cite entries are not read this season."
"""The PM's ruling of 2026-10-24 (`v1-e32-t09`): the site's round and cite titles are not taken."""
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
    return _csv(metadata, "top_cards", TOP_CARD_COLUMNS, map(_card_row, report.top_cards))


def render_impact_cards_csv(report: LandscapeReport, metadata: Mapping[str, str]) -> str:
    """impact_cards.csv: the header block with each kind's unlabelled documents, then the impact cards."""
    impacts = {
        "impact_cards_per_position": str(report.header.impact_cards_per_position),
        **{
            f"no_labelled_impact_{one.kind.value}": f"{one.unlabelled_documents}/{one.documents}"
            for one in report.impact_coverage
        },
    }
    return _csv(
        {**metadata, **impacts}, "impact_cards", IMPACT_CARD_COLUMNS, map(_card_row, report.impact_cards)
    )


def _card_row(card: TopCard) -> tuple[str, ...]:
    return (
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


def render_markdown(report: LandscapeReport, trends: LandscapeTrends | None = None) -> str:
    """report.md, without the stale-data banner: the service passes it through the hook.

    With `trends`, its new, rising and falling sections are theirs (`v1-e32-t04`); without, the new
    section is `v1-e32-t03`'s.
    """
    lines: list[str] = []
    lines += _header_section(report, trends)
    lines += _positions_section(report)
    lines += _texts_sections(report)
    lines += _new_section(report) if trends is None else _trend_sections(trends)
    lines += _unclassified_section(report)
    return "\n".join(lines).rstrip("\n") + "\n"


def _header_section(report: LandscapeReport, trends: LandscapeTrends | None = None) -> list[str]:
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
        *_short_history(trends),
        "## About this report",
        "",
        "| | |",
        "|---|---|",
        f"| Caselist | {header.caselist} |",
        f"| Snapshot | {header.snapshot.isoformat()} (previous: {previous}) |",
        *([f"| Weekly windows | {_windows_cell(trends)} |"] if trends is not None else []),
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
        f"* **Impact cards**, under each advantage and DA, are up to {header.impact_cards_per_position:,} "
        "of its cards labelled as an impact, ranked by the teams reading them: a heading over the card says "
        "`impact` or `impacts` (not `no impact`, `impact defense` or `impact turn`) or `turns case`, or its "
        "tag opens with an impact word such as `extinction`, `existential` or `the impact`. Only the "
        "labelled copies of a card count. An impact nobody labelled is not found, so each kind says how "
        "many of its documents carry no labelled impact. They are also in `impact_cards.csv`.",
        *([_trends_bullet(trends)] if trends is not None else []),
        "",
    ]


def _positions_section(report: LandscapeReport) -> list[str]:
    positions = report.positions
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
            listed = list(of_kind)
            lines += [
                f"| {_cell(stats.label)} (`{stats.position_id}`) | {stats.rounds:,} | {stats.teams:,} | "
                f"{stats.aff_rounds:,} | {stats.neg_rounds:,} | {_percent(*stats.share_of_teams)} | "
                f"{stats.first_seen_snapshot.isoformat()} | {'yes' if stats.is_new else ''} |"
                for stats in listed
            ]
            lines.append("")
            if kind in IMPACT_KINDS:
                lines += _impact_block(report, kind, listed)
    return lines


def _impact_block(
    report: LandscapeReport, kind: PositionKind, positions: Sequence[PositionStats]
) -> list[str]:
    """Under an advantages or DAs table: its documents with no labelled impact, then each one's cards."""
    coverage = next(
        (one for one in report.impact_coverage if one.kind is kind),
        ImpactCoverage(kind=kind, documents=0, labelled_documents=0),
    )
    lines = [
        f"#### {_KIND_HEADINGS[kind]}: impact cards",
        "",
        f"{_IMPACT_NOUNS[kind]} documents with no labelled impact: "
        f"{_of(coverage.unlabelled_documents, coverage.documents)}.",
        "",
    ]
    for stats in positions:
        cards = [card for card in report.impact_cards if card.position_id == stats.position_id]
        named = f"**{_cell(stats.label)}** (`{stats.position_id}`)"
        if not cards:
            lines += [f"{named}: no labelled impact card.", ""]
            continue
        lines += [named, "", "| Rank | Teams | Tag | Cite |", "|---|---|---|---|"]
        lines += [
            f"| {card.rank} | {card.teams_reading:,} | {_cell(card.tag or '')} | "
            f"{_cell(card.short_cite or '')} |"
            for card in cards
        ]
        lines.append("")
    return lines


def _texts_sections(report: LandscapeReport) -> list[str]:
    """`v1-e32-t11`'s sections: each CP's and K's top texts word for word, and the overviews' counts."""
    texts = report.texts
    if texts is None:
        return []
    coverage = {one.kind: one for one in texts.coverage}
    lines = [
        "## Counterplan texts, alternatives and roles of the ballot",
        "",
        "The teams' own words, quoted as their files hold them (data-use policy 1.13), never beside a "
        "school or team code. A text belongs to the position its section is placed under: the nearest "
        "placed heading over its label, as a card is placed. A label under no placed heading is counted "
        "here and never placed by a guess. Texts worded alike are one text. Each CP and K shows the "
        f"{texts.texts_per_position:,} texts the most teams read, and how many more there are. A text naming "
        "a school of the caselist is withheld.",
        "",
    ]
    for kind in QUOTED_KINDS:
        heading, found_by, under = _TEXT_KINDS[kind]
        one = coverage[kind]
        lines += [
            f"### {heading}",
            "",
            f"Found by {found_by}: {one.labels:,} in {one.documents:,} files.",
            "",
            f"* Placed under {under} the team reads, and counted: {one.counted:,}.",
            _not_placed(one),
            "* Placed under another kind of position, as an answer, or in a round on the other side: "
            f"{one.elsewhere:,}.",
        ]
        if kind is AnalyticTextKind.CP_TEXT:
            lines.append(
                "* Left out by the actor guard (no actor in the 12 words before `should`): "
                f"{one.refused_by_guard:,}."
            )
        if one.withheld_texts:
            lines.append(f"* Withheld for naming a school: {_count(one.withheld_texts, 'text')}.")
        if one.unread:
            lines.append(f"* Could not be read again as they were read: {one.unread:,}.")
        lines.append("")
        shown = [position for position in texts.positions if position.kind is kind]
        if not shown:
            lines += [f"No {_TEXT_NOUNS[kind]} was placed under {under} the team reads.", ""]
        for position in shown:
            lines += [
                f"**{_cell(position.label)}** (`{position.position_id}`)",
                "",
                "| Rank | Teams | Text |",
                "|---|---|---|",
            ]
            lines += [f"| {row.rank} | {row.teams:,} | {_cell(row.text)} |" for row in position.texts]
            lines.append("")
            if position.more is not None:
                more = position.more
                noun = "text" if more.texts == 1 else "texts"
                lines += [f"And {more.texts:,} more {noun}, read by {_count(more.teams, 'team')}.", ""]
    overview = coverage[AnalyticTextKind.OVERVIEW]
    lines += [
        "## Overviews",
        "",
        "Counted, never quoted: data-use policy 1.13 does not list overviews, and the coach keeps it so "
        "(2026-10-24). Per position, the teams whose files hold an overview label (`Overview`, `O/V`, `OV`) "
        "under it, on each side.",
        "",
        f"Found: {overview.labels:,} in {overview.documents:,} files.",
        "",
        f"* Placed under a position the team reads, and counted: {overview.counted:,}.",
        _not_placed(overview),
        f"* Placed under an answer to a position: {overview.elsewhere:,}.",
        "",
    ]
    if not texts.overviews:
        return [*lines, "No overview was placed under a position the team reads.", ""]
    lines += ["| Position | Kind | Teams | Aff teams | Neg teams |", "|---|---|---|---|---|"]
    lines += [
        f"| {_cell(one.label)} (`{one.position_id}`) | {one.position_kind.value} | {one.teams:,} | "
        f"{one.aff_teams:,} | {one.neg_teams:,} |"
        for one in texts.overviews
    ]
    return [*lines, ""]


def _not_placed(coverage: TextCoverage) -> str:
    return (
        f"* Not placed: {coverage.unplaced:,} ({coverage.headings_place_nothing:,} under headings that place "
        f"nothing, such as `1NC` or `OFF`; {coverage.no_heading:,} under no heading)."
    )


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


def _short_history(trends: LandscapeTrends | None) -> list[str]:
    """The notice on the report's face when its windows span less than a full topic cycle (ADR-0016)."""
    if trends is None or trends.covers_full_topic_cycle:
        return []
    count = _count(len(trends.windows), "weekly window")
    span = f"{window_start(trends.windows[0]).isoformat()} to {trends.snapshot.isoformat()}"
    if trends.topic_from is None or trends.topic_to is None:
        cycle = "and the topic's dates are not known here, so it may cover less than a full topic cycle"
    else:
        cycle = (
            f"of a topic that runs {trends.topic_from.isoformat()} to {trends.topic_to.isoformat()}: less "
            "than a full topic cycle"
        )
    return [
        f"**Short history.** The data covers {count} on this topic, {span}, {cycle}. A trend here is one "
        "week's change against the week before, not a season's.",
        "",
    ]


def _windows_cell(trends: LandscapeTrends) -> str:
    first = _window(trends.windows[0])
    on_topic = f"{len(trends.windows):,} on this topic, the first {first}"
    this_week = _window(trends.snapshot)
    if trends.topic_change is not None:
        change = trends.topic_change
        return (
            f"{on_topic}; this week's {this_week}. The snapshot before, "
            f"{change.previous_snapshot.isoformat()}, is on {change.previous_topic_id}, so no trend is drawn"
        )
    if trends.previous_snapshot is None:
        return f"{on_topic}; no earlier window to compare with"
    days = (trends.snapshot - trends.previous_snapshot).days
    gap = (
        ""
        if days == WINDOW_DAYS
        else f" (not the week before: {days - WINDOW_DAYS:,} day(s) between them are in no window)"
    )
    return f"{on_topic}; this week's {this_week}, compared with {_window(trends.previous_snapshot)}{gap}"


def _window(snapshot: date) -> str:
    return f"{window_start(snapshot).isoformat()} to {snapshot.isoformat()}"


def _trends_bullet(trends: LandscapeTrends) -> str:
    previous = trends.previous
    weekly = (
        f"this week {trends.weekly.aff_teams:,} on the affirmative and {trends.weekly.neg_teams:,} on the "
        "negative"
    )
    if previous is not None:
        weekly += f", the previous {previous.aff_teams:,} and {previous.neg_teams:,}"
    return (
        "* **Trends** compare this week's window with the previous one. A round counts in the week its file "
        "was first disclosed, whatever path it was later filed under, and a position's share is the teams "
        "that read it that week on its own side over the week's teams disclosing on that side: "
        f"{weekly}. **NEW** is read for the first time on this topic; **RISING** and **FALLING** moved by "
        f"at least {_points_text(trends.threshold_points)} points with at least "
        f"{_count(trends.minimum_teams, 'team')} reading it in one of the two weeks; everything else is "
        "**STEADY**. Every position's row is in `trends.csv`."
    )


def _trend_sections(trends: LandscapeTrends) -> list[str]:
    lines = ["## New this week", ""]
    new = trends.labelled(TrendLabel.NEW)
    if trends.topic_change is not None:
        change = trends.topic_change
        lines += [
            f"The topic changed: the previous snapshot, {change.previous_snapshot.isoformat()}, is on "
            f"{change.previous_topic_id}. A trend never compares two topics, so this is the first window "
            f"of {trends.topic_id} here: every position read is NEW and none has a delta.",
            "",
        ]
    elif trends.previous_snapshot is None:
        lines += [
            "This is the caselist's first weekly window on this topic: every position read is NEW and none "
            "has a delta.",
            "",
        ]
    if new:
        lines += [
            f"Positions first read on this topic in this week's window, {_window(trends.snapshot)}:",
            "",
        ]
        lines += [
            f"* {_cell(row.label)} (`{row.position_id}`, {row.kind.value}): "
            f"{_count(row.weekly_teams, 'team')}, {_percent(row.weekly_teams, row.weekly_disclosing)} of the "
            f"week's {_side_teams(row)}"
            for row in new
        ]
        lines.append("")
    else:
        lines += ["No position was first read on this topic in this week's window.", ""]
    for heading, label, direction in (
        ("Rising", TrendLabel.RISING, "rose"),
        ("Falling", TrendLabel.FALLING, "fell"),
    ):
        lines += [f"## {heading}", ""]
        if trends.previous_snapshot is None:
            lines += ["No trend is drawn: there is no earlier window on this topic to compare with.", ""]
            continue
        rows = sorted(trends.labelled(label), key=lambda row: (-abs(row.delta_points or 0), row.position_id))
        rule = (
            f"by at least {_points_text(trends.threshold_points)} points of the week's teams on its side, "
            f"with at least {_count(trends.minimum_teams, 'team')} reading it in one of the two weeks"
        )
        if not rows:
            lines += [f"No position {direction} {rule}.", ""]
        else:
            lines += [f"Positions that {direction} {rule}:", ""]
            lines += [f"* {_trend_line(row)}" for row in rows]
            lines.append("")
    if trends.held_back:
        lines += [
            f"Held back by the team floor: {_count(trends.held_back, 'position')} moved by "
            f"{_points_text(trends.threshold_points)} points or more, but fewer than "
            f"{_count(trends.minimum_teams, 'team')} read them in either week, so they are STEADY. Every "
            "position's row is in `trends.csv`.",
            "",
        ]
    return lines


def _trend_line(row: TrendRow) -> str:
    previous_teams = row.previous_teams or 0
    return (
        f"{_cell(row.label)} (`{row.position_id}`, {row.kind.value}): "
        f"{_percent(previous_teams, row.previous_disclosing or 0)} to "
        f"{_percent(row.weekly_teams, row.weekly_disclosing)} of the week's {_side_teams(row)} "
        f"({_signed_points(row.delta_points)} points), "
        f"{_count(previous_teams, 'team')} to {row.weekly_teams:,}"
    )


def _side_teams(row: TrendRow) -> str:
    if row.side is PositionSide.AFF:
        return "affirmative teams"
    if row.side is PositionSide.NEG:
        return "negative teams"
    return "teams"


def trend_metadata(trends: LandscapeTrends) -> dict[str, str]:
    """The facts trends.csv's header block adds to the report's, in order."""
    previous = trends.previous_snapshot
    full = trends.covers_full_topic_cycle
    return {
        "window": f"{window_start(trends.snapshot).isoformat()}/{trends.snapshot.isoformat()}",
        "previous_window": f"{window_start(previous).isoformat()}/{previous.isoformat()}" if previous else "",
        "windows_on_topic": str(len(trends.windows)),
        "first_window": f"{window_start(trends.windows[0]).isoformat()}/{trends.windows[0].isoformat()}",
        "topic_cycle": (
            f"{trends.topic_from.isoformat()}/{trends.topic_to.isoformat()}"
            if trends.topic_from and trends.topic_to
            else "unknown"
        ),
        "full_topic_cycle": "unknown" if full is None else ("true" if full else "false"),
        "topic_changed_from": (
            f"{trends.topic_change.previous_topic_id} on {trends.topic_change.previous_snapshot.isoformat()}"
            if trends.topic_change
            else ""
        ),
        "trend_threshold_points": _points_text(trends.threshold_points),
        "trend_minimum_teams": str(trends.minimum_teams),
        "weekly_share_over": _weekly_over(trends.weekly),
        "previous_share_over": _weekly_over(trends.previous) if trends.previous else "",
        "held_back_by_team_floor": str(trends.held_back),
    }


def _weekly_over(weekly: WeeklyTeams) -> str:
    return (
        "teams with a round first seen in the window, on the position's side: "
        f"aff {weekly.aff_teams}, neg {weekly.neg_teams}, either side {weekly.teams}"
    )


def render_trends_csv(trends: LandscapeTrends, metadata: Mapping[str, str]) -> str:
    """trends.csv: the report's header block and the trends', then one row per position (ac1)."""
    return _csv(
        {**metadata, **trend_metadata(trends)},
        "trends",
        TREND_COLUMNS,
        (
            (
                row.position_id,
                row.label,
                row.kind.value,
                str(row.weekly_teams),
                _fraction(row.weekly_teams, row.weekly_disclosing),
                "" if row.previous_teams is None else str(row.previous_teams),
                ""
                if row.previous_teams is None
                else _fraction(row.previous_teams, row.previous_disclosing or 0),
                _points_csv(row.delta_points),
                row.trend.value,
                "true" if row.held_back_by_team_floor else "false",
            )
            for row in trends.rows
        ),
    )


def render_schools_csv(view: SchoolView, metadata: Mapping[str, str]) -> str:
    """schools.csv: the header block, then one row per team, side and position (ac4)."""
    extra = {
        "shows": _SCHOOL_VIEW_SHOWS,
        "rounds_on_no_side": str(view.rounds_on_no_side),
        "rounds_with_no_team": str(view.rounds_with_no_team),
        "team_pages": _team_pages(view),
    }
    return _csv(
        {**metadata, **extra},
        "schools",
        SCHOOL_COLUMNS,
        (
            (
                row.school,
                row.team_code,
                row.side.value,
                row.position_id,
                str(row.rounds),
                view.team_page(row) or "",
            )
            for row in view.rows
        ),
    )


def render_schools_markdown(view: SchoolView, report: LandscapeReport) -> str:
    """schools.md, without the stale-data banner: the per-school view, by school (ac4), then by position."""
    header = report.header
    left_out = (
        f"{_count(view.rounds_on_no_side, 'round')} on no readable side; "
        f"{_count(view.rounds_with_no_team, 'round')} whose path named no school or team code"
    )
    lines = [
        f"# Positions by school: {view.caselist} through {view.snapshot.isoformat()}",
        "",
        "This page names schools and team codes exactly as they were disclosed, and links each team's "
        "public openCaselist page, and nothing more: no debater, and no text from anyone's files. It is for "
        "the team only, and stays on this machine and in the private bucket.",
        "",
        "Every count comes from files teams disclosed to the caselist (FILE_IMPORT), not from evidence the "
        "platform has verified. A row is a team's rounds on one side that the landscape report counts as "
        "reading the position.",
        "",
        "| | |",
        "|---|---|",
        f"| Caselist | {view.caselist} |",
        f"| Snapshot | {view.snapshot.isoformat()} |",
        f"| Topic | {header.topic_id} |",
        f"| Taxonomy version | {header.taxonomy_version} |",
        f"| Coach's overrides | {header.overrides_digest} |",
        f"| Schools | {view.schools:,}, with {_count(view.teams, 'team code')} |",
        f"| Team pages | {_team_pages(view)} |",
        f"| Left out | {left_out} |",
        "",
        "## By school",
        "",
    ]
    if not view.rows:
        lines += ["No team read a counted position in this range.", ""]
    for _, rows in groupby(view.rows, key=lambda row: row.school.casefold()):
        listed = list(rows)
        lines += [
            f"### {_cell(listed[0].school)}",
            "",
            "| Team code | Side | Position | Rounds |",
            "|---|---|---|---|",
        ]
        lines += [
            f"| {_cell(row.team_code)} | {row.side.value} | `{row.position_id}` | {row.rounds:,} |"
            for row in listed
        ]
        lines.append("")
    lines += _by_position_section(view, report)
    return "\n".join(lines).rstrip("\n") + "\n"


def _team_pages(view: SchoolView) -> str:
    """How many teams link to their page, and why the rest do not."""
    without = view.teams_without_team_page
    text = (
        f"{view.teams_with_team_page:,} of {_count(view.teams, 'team code')} link to their openCaselist page"
    )
    if not without:
        return text
    reasons = ", ".join(
        f"{without[reason]:,} {_NO_TEAM_PAGE[reason]}" for reason in NoTeamPage if without[reason]
    )
    return f"{text}; {without.total():,} do not: {reasons}"


def _by_position_section(view: SchoolView, report: LandscapeReport) -> list[str]:
    """Each position the view's teams read, by side and kind in the report's order, its teams by rounds."""
    lines = [
        "## By position",
        "",
        "The negative's positions by kind, then the affirmative side's, in the report's order. Under each, "
        "every team that read it, by rounds. A team's openCaselist page lists the rounds it disclosed, with "
        "their files; it is linked when the school and the team code are each one word of the page's "
        "address.",
        "",
    ]
    by_position: dict[str, list[SchoolRow]] = {}
    for row in view.rows:
        by_position.setdefault(row.position_id, []).append(row)
    read = [stats for stats in report.positions if stats.position_id in by_position]
    if not read:
        return [*lines, "No team read a counted position in this range.", ""]
    for side in _BY_POSITION_SIDES:
        for kind, of_kind in groupby(
            (stats for stats in read if stats.side is side), key=lambda one: one.kind
        ):
            lines += [f"### {_BY_POSITION_SIDE_PREFIXES[side]}{_KIND_HEADINGS[kind]}", ""]
            for stats in of_kind:
                rows = sorted(
                    by_position[stats.position_id],
                    key=lambda row: (
                        -row.rounds,
                        row.school.casefold(),
                        row.school,
                        row.team_code.casefold(),
                        row.team_code,
                        row.side.value,
                    ),
                )
                lines += [
                    f"#### `{stats.position_id}`",
                    "",
                    "| School | Team code | Side | Rounds | Team page |",
                    "|---|---|---|---|---|",
                ]
                lines += [
                    f"| {_cell(row.school)} | {_cell(row.team_code)} | {row.side.value} | {row.rounds:,} | "
                    f"{_team_page_cell(view.team_page(row))} |"
                    for row in rows
                ]
                lines.append("")
    return lines


def _team_page_cell(url: str | None) -> str:
    return "none" if url is None else f"[openCaselist]({url})"


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
    lines += [f"| Not identified | {summary.aff_rounds_unidentified:,} |", "", _TITLES_NOT_READ, ""]
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


def _points(delta: Fraction) -> Decimal:
    """A delta in points to one place, rounded half up; never `-0.0`."""
    rounded = (Decimal(delta.numerator) / Decimal(delta.denominator)).quantize(_TENTH, rounding=ROUND_HALF_UP)
    return rounded if rounded else Decimal("0.0")


def _points_csv(delta: Fraction | None) -> str:
    return "" if delta is None else str(_points(delta))


def _signed_points(delta: Fraction | None) -> str:
    if delta is None:
        return "n/a"
    rounded = _points(delta)
    return f"+{rounded}" if rounded > 0 else str(rounded)


def _points_text(points: Decimal) -> str:
    """A threshold as written: `5`, or `2.5`."""
    return f"{points.normalize():f}"


def _fraction(part: int, whole: int) -> str:
    if whole == 0:
        return ""
    return str((Decimal(part) / Decimal(whole)).quantize(_THOUSANDTH, rounding=ROUND_HALF_UP))
