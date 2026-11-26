"""The placements listing: every heading that places cards, so the coach can correct it (`v1-e32-t64`).

The review queue (:mod:`~debate_core.arguments.landscape.review_queue`) lists only the headings nothing
placed. A heading an alias placed confidently but wrongly never reaches the coach there, so every run also
writes this listing beside the queue: one row per normalized heading that places something, with how it
places it and under what, and one per heading the coach ruled names no position. A decision written in
its `decision` column is read back by the queue's own reader and applied by the same apply step, so it
becomes an :class:`~debate_core.domain.landscape_classification.OverrideRules` entry that the matcher reads
before any alias from the next run.

## What a row is

A row is a normalized heading with its answer flag, as a queue row is:

* **`alias` or `override`**: the heading that places an item, the nearest alias or override naming a
  position (:meth:`~debate_core.arguments.landscape.matcher.PositionMatcher.heading_placement`). Its items
  are the ones it places, directly or from further up. `position` is the heading's own position, before a
  tag keyword moves a card to a child of it.
* **`none`**: a heading the coach ruled names no position. Its items are the ones under it that no nearer
  heading places, so the ones a changed decision on it would place. `position`, `cards_inherited` and
  `cards_tag_names_another` are blank.

`cards_inherited` counts the cards it places from further up. `cards_tag_names_another` counts the cards
whose tag holds a keyword of a position outside the placement's line (the position, its ancestors and its
descendants): how the coach finds a heading that is right as a heading but wrong for some of its cards. The
candidates are the heading's own (positions an alias of which shares a word with it) and then those the
cards' tags name, the current position's line left out of both.

Placed rows come first, most cards first, then the none rows, most cards first. A heading fewer than
`minimum_teams` teams use is left out and counted, as the queue leaves it out, since it can point at the
one team that wrote it. The file holds headings, counts and position ids only: no path, file name, school,
team code or tag.

## What a decision does, before it is written (:func:`placement_changes`)

The apply step shows, for each decision that changes the rules, where the cards it moves go. Each card of
the caselist is placed under today's rules and under the rules with the decisions applied. A card placed
differently is counted under the nearest heading over it whose decision changed, by where it goes: under
the decision's own position, under a heading above (the position it had, or another), to its tag keyword
alone (under the review threshold, so to the queue), to the queue, or decided (every heading over it ruled
none).

Pure: values in, values out.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from collections.abc import Callable, Collection, Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final, TextIO

from debate_core.arguments.landscape.headings import NormalizedHeading
from debate_core.arguments.landscape.matcher import HeadingRule, MatchItem, PositionMatcher, read_items
from debate_core.arguments.landscape.review_queue import (
    DEFAULT_MINIMUM_REVIEW_TEAMS,
    DEFAULT_REVIEW_THRESHOLD,
    needs_review,
)
from debate_core.arguments.landscape.seeding import SeedSource, SeedTeam
from debate_core.arguments.landscape.source_headings import CaselistNames
from debate_core.domain.caselist import Side
from debate_core.domain.landscape_classification import ClassificationResult, ItemKind

__all__ = [
    "PLACEMENT_COLUMNS",
    "DecisionEffect",
    "Destination",
    "PlacedBy",
    "PlacedItem",
    "PlacementCounts",
    "PlacementListing",
    "PlacementRow",
    "build_placement_listing",
    "placed_item",
    "placement_changes",
    "write_placements_csv",
]

_CANDIDATE_LIMIT: Final = 3

PLACEMENT_COLUMNS: Final = (
    "normalized_heading",
    "answer",
    "placed_by",
    "position",
    "documents",
    "teams",
    "aff_teams",
    "neg_teams",
    "cards",
    "cards_inherited",
    "cards_tag_names_another",
    "candidate_positions",
    "decision",
)
"""The review queue's columns, with how the heading places and under what, and two card counts."""


class PlacedBy(StrEnum):
    """How a row's heading places what is under it."""

    ALIAS = "alias"
    OVERRIDE = "override"
    NONE = "none"
    """The coach ruled the heading names no position."""


@dataclass(frozen=True, slots=True)
class PlacedItem:
    """One item as the listing counts it: who disclosed it, what places it, the none rulings over it."""

    source_sha256: str
    kind: ItemKind
    teams: tuple[SeedTeam, ...] = field(repr=False)
    placing: NormalizedHeading | None = field(repr=False)
    """The heading that places the item; None when no heading does."""
    placed_by: PlacedBy | None
    position_id: str | None
    """The placing heading's own position."""
    inherited: bool
    """Placed from further up than the heading directly over it."""
    tag_names_another: bool
    """A card whose tag holds a keyword of a position outside its placement's line."""
    ruled_none: tuple[NormalizedHeading, ...] = field(repr=False)
    """The headings over the item ruled none that no nearer heading overrules: the none rows it is under."""
    tag_candidates: tuple[str, ...] = ()
    """Positions the card's tag names, the placement's line left out."""


def placed_item(
    matcher: PositionMatcher, item: MatchItem, result: ClassificationResult, teams: tuple[SeedTeam, ...]
) -> PlacedItem:
    """`item`, placed as `result` under `matcher`'s rules, as the listing counts it."""
    placement = matcher.heading_placement(item.headings)
    nearest = -1 if placement is None else placement.index
    ruled_none = tuple(
        heading
        for index, heading in enumerate(item.headings)
        if index > nearest and matcher.ruled_none(heading.text)
    )
    named = matcher.tag_candidates(item) if item.kind is ItemKind.CARD else ()
    if placement is None:
        return PlacedItem(
            source_sha256=item.source_sha256,
            kind=item.kind,
            teams=teams,
            placing=None,
            placed_by=None,
            position_id=None,
            inherited=False,
            tag_names_another=False,
            ruled_none=ruled_none,
            tag_candidates=named,
        )
    line = matcher.lineage(result.position_id or placement.position_id) | {placement.position_id}
    other = tuple(one for one in named if one not in line)
    return PlacedItem(
        source_sha256=item.source_sha256,
        kind=item.kind,
        teams=teams,
        placing=item.headings[placement.index],
        placed_by=PlacedBy.OVERRIDE if placement.by_override else PlacedBy.ALIAS,
        position_id=placement.position_id,
        inherited=placement.index < len(item.headings) - 1,
        tag_names_another=bool(other),
        ruled_none=ruled_none,
        tag_candidates=other,
    )


@dataclass(frozen=True, slots=True)
class PlacementRow:
    """One normalized heading of the listing, and what it places."""

    normalized_heading: str
    answer: bool
    placed_by: PlacedBy
    position: str | None
    documents: int
    teams: int
    aff_teams: int
    neg_teams: int
    cards: int
    cards_inherited: int | None
    """None for a none row."""
    cards_tag_names_another: int | None
    """None for a none row."""
    candidate_positions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PlacementCounts:
    headings: int
    """Distinct (heading, answer) pairs that place something or are ruled none, those left out included."""
    rows: int
    placed_rows: int
    none_rows: int
    left_out_below_minimum_teams: int


@dataclass(frozen=True, slots=True)
class PlacementListing:
    rows: tuple[PlacementRow, ...]
    counts: PlacementCounts


@dataclass(slots=True)
class _Tally:
    placed_by: PlacedBy
    position: str | None
    documents: set[str] = field(default_factory=lambda: set[str]())
    teams: set[str] = field(default_factory=lambda: set[str]())
    aff: set[str] = field(default_factory=lambda: set[str]())
    neg: set[str] = field(default_factory=lambda: set[str]())
    cards: int = 0
    inherited: int = 0
    tag_names_another: int = 0
    candidates: Counter[str] = field(default_factory=lambda: Counter[str]())

    def add(self, item: PlacedItem) -> None:
        card = item.kind is ItemKind.CARD
        self.documents.add(item.source_sha256)
        self.cards += card
        self.candidates.update(item.tag_candidates)
        for team in item.teams:
            if not team.identity:
                continue
            self.teams.add(team.identity)
            if team.side in (Side.AFF, Side.PRO):
                self.aff.add(team.identity)
            elif team.side in (Side.NEG, Side.CON):
                self.neg.add(team.identity)


def build_placement_listing(
    items: Iterable[PlacedItem],
    *,
    heading_candidates: Callable[[str], Sequence[str]] | None = None,
    minimum_teams: int = DEFAULT_MINIMUM_REVIEW_TEAMS,
) -> PlacementListing:
    """The placing and ruled-none headings counted by row, placed rows first, the rare ones left out."""
    if minimum_teams < 1:
        raise ValueError(f"the minimum number of teams is at least 1; got {minimum_teams}")
    tallies: dict[tuple[str, bool], _Tally] = {}
    for item in items:
        if item.placing is not None and item.placed_by is not None:
            key = (item.placing.text, item.placing.answer)
            tally = tallies.get(key)
            if tally is None:
                tally = tallies[key] = _Tally(item.placed_by, item.position_id)
            tally.add(item)
            if item.kind is ItemKind.CARD:
                tally.inherited += item.inherited
                tally.tag_names_another += item.tag_names_another
        for heading in {(one.text, one.answer) for one in item.ruled_none}:
            tally = tallies.get(heading)
            if tally is None:
                tally = tallies[heading] = _Tally(PlacedBy.NONE, None)
            tally.add(item)
    rows: list[PlacementRow] = []
    for (heading, answer), tally in tallies.items():
        if len(tally.teams) < minimum_teams:
            continue
        none = tally.placed_by is PlacedBy.NONE
        own = heading_candidates(heading) if heading_candidates is not None else ()
        named = tally.candidates
        ranked = [
            *(one for one in own if one != tally.position),
            *sorted(named, key=lambda one: (-named[one], one)),
        ]
        rows.append(
            PlacementRow(
                normalized_heading=heading,
                answer=answer,
                placed_by=tally.placed_by,
                position=tally.position,
                documents=len(tally.documents),
                teams=len(tally.teams),
                aff_teams=len(tally.aff),
                neg_teams=len(tally.neg),
                cards=tally.cards,
                cards_inherited=None if none else tally.inherited,
                cards_tag_names_another=None if none else tally.tag_names_another,
                candidate_positions=tuple(dict.fromkeys(ranked))[:_CANDIDATE_LIMIT],
            )
        )
    rows.sort(
        key=lambda row: (
            row.placed_by is PlacedBy.NONE,
            -row.cards,
            -row.teams,
            -row.documents,
            row.normalized_heading,
            row.answer,
        )
    )
    none_rows = sum(1 for row in rows if row.placed_by is PlacedBy.NONE)
    return PlacementListing(
        rows=tuple(rows),
        counts=PlacementCounts(
            headings=len(tallies),
            rows=len(rows),
            placed_rows=len(rows) - none_rows,
            none_rows=none_rows,
            left_out_below_minimum_teams=len(tallies) - len(rows),
        ),
    )


def write_placements_csv(rows: Iterable[PlacementRow], stream: TextIO) -> None:
    """The rows under a header of :data:`PLACEMENT_COLUMNS`, each with an empty `decision`."""
    writer = csv.writer(stream)
    writer.writerow(PLACEMENT_COLUMNS)
    for row in rows:
        writer.writerow(
            [
                row.normalized_heading,
                "true" if row.answer else "false",
                row.placed_by.value,
                row.position or "",
                row.documents,
                row.teams,
                row.aff_teams,
                row.neg_teams,
                row.cards,
                "" if row.cards_inherited is None else row.cards_inherited,
                "" if row.cards_tag_names_another is None else row.cards_tag_names_another,
                ";".join(row.candidate_positions),
                "",
            ]
        )


# ------------------------------------------------------------------------------------------------
# What a decision does, before it is written
# ------------------------------------------------------------------------------------------------


class Destination(StrEnum):
    """Where a card a decision moves goes."""

    DECISION = "decision"
    """Under the decision's own position (or a child of it its tag names)."""
    HEADING_ABOVE_SAME_POSITION = "heading_above_same_position"
    HEADING_ABOVE_OTHER_POSITION = "heading_above_other_position"
    TAG_KEYWORD = "tag_keyword"
    """Placed by its tag keyword alone, under the review threshold: to the queue."""
    QUEUE = "queue"
    DECIDED = "decided"
    """Every heading over it ruled none."""


@dataclass(frozen=True, slots=True)
class DecisionEffect:
    """One changed decision: what decided its heading before, what it names now, and the cards it moves."""

    heading: str
    before: HeadingRule
    after: str | None
    """The position the decision names; None for `none`."""
    cards: int
    moves: dict[Destination, int]


def placement_changes(
    sources: Iterable[SeedSource],
    names: CaselistNames,
    before: PositionMatcher,
    after: PositionMatcher,
    changed: Collection[str],
    *,
    threshold: float = DEFAULT_REVIEW_THRESHOLD,
) -> tuple[DecisionEffect, ...]:
    """Each heading of `changed` with the cards of `sources` its decision moves, most cards first.

    `before` holds today's rules and `after` the rules with the decisions applied. A card is moved when the
    two place it differently; it is counted under the nearest heading over it in `changed`. A decision that
    moves no card is listed with none.
    """
    moves: dict[str, Counter[Destination]] = defaultdict(Counter)
    for source in sources:
        for item in read_items(source, names):
            if item.kind is not ItemKind.CARD:
                continue
            was, now = before.place(item), after.place(item)
            if (was.position_id, was.method, was.confidence) == (now.position_id, now.method, now.confidence):
                continue
            decided = next(
                (one.text for one in reversed(item.headings) if one.text in changed),
                None,
            )
            if decided is None:
                continue
            moves[decided][_destination(after, item, was, now, decided, threshold)] += 1
    effects = [
        DecisionEffect(
            heading=heading,
            before=before.heading_rule(heading),
            after=after.heading_rule(heading).position_id,
            cards=sum(moves[heading].values()),
            moves={
                destination: moves[heading][destination]
                for destination in Destination
                if moves[heading][destination]
            },
        )
        for heading in dict.fromkeys(changed)
    ]
    effects.sort(key=lambda one: (-one.cards, one.heading))
    return tuple(effects)


def _destination(
    after: PositionMatcher,
    item: MatchItem,
    was: ClassificationResult,
    now: ClassificationResult,
    decided: str,
    threshold: float,
) -> Destination:
    if now.position_id is None:
        return Destination.QUEUE if now.method is None else Destination.DECIDED
    if needs_review(now, threshold):
        return Destination.TAG_KEYWORD
    placement = after.heading_placement(item.headings)
    if placement is not None and item.headings[placement.index].text == decided:
        return Destination.DECISION
    if now.position_id == was.position_id:
        return Destination.HEADING_ABOVE_SAME_POSITION
    return Destination.HEADING_ABOVE_OTHER_POSITION
