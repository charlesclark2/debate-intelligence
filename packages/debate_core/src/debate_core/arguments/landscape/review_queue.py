"""The review queue: headings the matcher cannot place, and the coach's decisions (`v1-e32-t02` ac4).

An item goes to the queue when nothing placed it, or when what placed it is less sure than the
review threshold (0.6 by default, so only a card placed by its tag alone, at 0.5). The queue is not a
list of items. It is a list of **headings**: each normalized heading an unplaced item sits under that
no alias or override decides, with how many documents, teams and cards are under it and up to three
candidate positions, because a decision on a heading is what places every item under it next run. A
row's candidates are its own heading's (positions an alias of which shares a word with it), then the
positions whose tag keywords the cards under it carry; never another heading's on the same path.

## What the queue's CSV holds

Normalized headings, counts and candidate position ids, and an empty `decision` column for the coach.
Nothing else: no path, file name, school, team code or tag. A heading fewer than `minimum_teams`
teams use (two by default, the rule seeding follows) is left out and only counted, since such a
heading can point at the one team that wrote it. The file is written to the local data directory,
never to the repository.

## A decision

The coach fills `decision` with a position id, or `none` for a heading that names no position (a
block label such as `link`), and leaves the rest blank. :func:`read_decisions_csv` reads the filled
rows and :func:`apply_decisions` turns them into the topic's
:class:`~debate_core.domain.landscape_classification.OverrideRules`: a new heading is added, a
changed decision replaces the old one, and a decision naming no position of the taxonomy is refused
before anything is written. From the next run the matcher reads the override before any alias.

Pure: streams and values in, values out.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Final, TextIO

from pydantic import ValidationError

from debate_core.arguments.landscape.headings import NormalizedHeading
from debate_core.arguments.landscape.seeding import SeedTeam
from debate_core.domain.caselist import Side
from debate_core.domain.landscape import ALIAS_PATTERN, Taxonomy
from debate_core.domain.landscape_classification import (
    ClassificationResult,
    HeadingOverride,
    ItemKind,
    OverrideRules,
)

__all__ = [
    "DECISION_NO_POSITION",
    "DEFAULT_MINIMUM_REVIEW_TEAMS",
    "DEFAULT_REVIEW_THRESHOLD",
    "REVIEW_QUEUE_COLUMNS",
    "AppliedDecisions",
    "Decision",
    "QueuedItem",
    "ReviewQueue",
    "ReviewQueueCounts",
    "ReviewRow",
    "apply_decisions",
    "build_review_queue",
    "needs_review",
    "read_decisions_csv",
    "write_review_queue_csv",
]

DEFAULT_REVIEW_THRESHOLD: Final = 0.6
"""A placed item less sure than this goes to the review queue (ac4)."""

DEFAULT_MINIMUM_REVIEW_TEAMS: Final = 2
"""A heading fewer teams use than this is counted but left out of the CSV, as seeding leaves it out."""

DECISION_NO_POSITION: Final = "none"
"""What the coach writes in `decision` for a heading that names no position."""

_CANDIDATE_LIMIT: Final = 3

REVIEW_QUEUE_COLUMNS: Final = (
    "normalized_heading",
    "answer",
    "documents",
    "teams",
    "aff_teams",
    "neg_teams",
    "cards",
    "candidate_positions",
    "decision",
)


def needs_review(result: ClassificationResult, threshold: float = DEFAULT_REVIEW_THRESHOLD) -> bool:
    """True when nothing placed the item, or the position it was placed under is below `threshold`.

    An item the coach ruled names no position (OVERRIDE with no position) is decided, not queued.
    """
    if result.method is None:
        return True
    return result.position_id is not None and result.confidence < threshold


@dataclass(frozen=True, slots=True)
class QueuedItem:
    """One item for the queue: where it is, who disclosed it, and the headings over it left undecided."""

    source_sha256: str
    kind: ItemKind
    teams: tuple[SeedTeam, ...] = field(repr=False)
    headings: tuple[NormalizedHeading, ...] = field(repr=False)
    """The headings over the item that no alias or override decides."""
    tag_candidates: tuple[str, ...] = ()
    """Positions whose tag keywords the card's tag holds."""


@dataclass(frozen=True, slots=True)
class ReviewRow:
    """One normalized heading in the queue, and what sits under it."""

    normalized_heading: str
    answer: bool
    documents: int
    teams: int
    aff_teams: int
    neg_teams: int
    cards: int
    candidate_positions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReviewQueueCounts:
    queued_items: int
    queued_cards: int
    without_heading: int
    """Queued items under no heading at all, so with nothing for the coach to decide."""
    headings: int
    """Distinct (heading, answer) pairs over the queued items, those left out included."""
    rows: int
    left_out_below_minimum_teams: int


@dataclass(frozen=True, slots=True)
class ReviewQueue:
    rows: tuple[ReviewRow, ...]
    counts: ReviewQueueCounts


@dataclass(slots=True)
class _Tally:
    documents: set[str] = field(default_factory=lambda: set[str]())
    teams: set[str] = field(default_factory=lambda: set[str]())
    aff: set[str] = field(default_factory=lambda: set[str]())
    neg: set[str] = field(default_factory=lambda: set[str]())
    cards: int = 0
    candidates: Counter[str] = field(default_factory=lambda: Counter[str]())


def build_review_queue(
    items: Iterable[QueuedItem],
    *,
    heading_candidates: Callable[[str], Sequence[str]] | None = None,
    minimum_teams: int = DEFAULT_MINIMUM_REVIEW_TEAMS,
) -> ReviewQueue:
    """The queued items counted by heading, most teams first, with the rare headings left out.

    `heading_candidates` gives a heading's own candidate positions, best first.
    """
    if minimum_teams < 1:
        raise ValueError(f"the minimum number of teams is at least 1; got {minimum_teams}")
    tallies: dict[tuple[str, bool], _Tally] = defaultdict(_Tally)
    queued = queued_cards = without_heading = 0
    for item in items:
        queued += 1
        card = item.kind is ItemKind.CARD
        queued_cards += card
        if not item.headings:
            without_heading += 1
            continue
        known = [team for team in item.teams if team.identity]
        for heading in {(one.text, one.answer) for one in item.headings}:
            tally = tallies[heading]
            tally.documents.add(item.source_sha256)
            tally.cards += card
            tally.candidates.update(item.tag_candidates)
            for team in known:
                tally.teams.add(team.identity)
                if team.side in (Side.AFF, Side.PRO):
                    tally.aff.add(team.identity)
                elif team.side in (Side.NEG, Side.CON):
                    tally.neg.add(team.identity)
    rows = [
        ReviewRow(
            normalized_heading=heading,
            answer=answer,
            documents=len(tally.documents),
            teams=len(tally.teams),
            aff_teams=len(tally.aff),
            neg_teams=len(tally.neg),
            cards=tally.cards,
            candidate_positions=_candidates(
                heading_candidates(heading) if heading_candidates is not None else (), tally.candidates
            ),
        )
        for (heading, answer), tally in tallies.items()
        if len(tally.teams) >= minimum_teams
    ]
    rows.sort(key=lambda row: (-row.teams, -row.documents, -row.cards, row.normalized_heading, row.answer))
    return ReviewQueue(
        rows=tuple(rows),
        counts=ReviewQueueCounts(
            queued_items=queued,
            queued_cards=queued_cards,
            without_heading=without_heading,
            headings=len(tallies),
            rows=len(rows),
            left_out_below_minimum_teams=len(tallies) - len(rows),
        ),
    )


def _candidates(own: Sequence[str], from_tags: Counter[str]) -> tuple[str, ...]:
    ranked = [*own, *sorted(from_tags, key=lambda one: (-from_tags[one], one))]
    return tuple(dict.fromkeys(ranked))[:_CANDIDATE_LIMIT]


def write_review_queue_csv(rows: Iterable[ReviewRow], stream: TextIO) -> None:
    """The rows under a header of :data:`REVIEW_QUEUE_COLUMNS`, each with an empty `decision`."""
    writer = csv.writer(stream)
    writer.writerow(REVIEW_QUEUE_COLUMNS)
    for row in rows:
        writer.writerow(
            [
                row.normalized_heading,
                "true" if row.answer else "false",
                row.documents,
                row.teams,
                row.aff_teams,
                row.neg_teams,
                row.cards,
                ";".join(row.candidate_positions),
                "",
            ]
        )


# ------------------------------------------------------------------------------------------------
# The coach's decisions
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Decision:
    """One filled row of a decisions CSV: a normalized heading and a position id or None."""

    heading: str
    position_id: str | None


def read_decisions_csv(stream: TextIO) -> tuple[Decision, ...]:
    """The rows of a review queue CSV whose `decision` the coach filled, one per heading.

    `ValueError` for a file without the queue's `normalized_heading` and `decision` columns, a heading
    not written as a normalized heading, or one heading given two different decisions (its reading
    and its answer row, say).
    """
    reader = csv.DictReader(stream)
    columns = set(reader.fieldnames or ())
    if not {"normalized_heading", "decision"} <= columns:
        raise ValueError("a decisions file is a review queue CSV with its decision column filled")
    decided: dict[str, Decision] = {}
    for number, line in enumerate(reader, start=2):
        value = (line["decision"] or "").strip()
        if not value:
            continue
        heading = (line["normalized_heading"] or "").strip()
        if ALIAS_PATTERN.match(heading) is None:
            raise ValueError(f"line {number}: {heading!r} is not written as a normalized heading")
        decision = Decision(heading, None if value.casefold() == DECISION_NO_POSITION else value)
        earlier = decided.get(heading)
        if earlier is not None and earlier != decision:
            raise ValueError(f"line {number}: {heading!r} is given two decisions")
        decided[heading] = decision
    return tuple(decided.values())


@dataclass(frozen=True, slots=True)
class AppliedDecisions:
    rules: OverrideRules
    added: int
    changed: int
    unchanged: int


def apply_decisions(
    current: OverrideRules, decisions: Sequence[Decision], taxonomy: Taxonomy, *, decided: date
) -> AppliedDecisions:
    """`current` with `decisions` applied: new headings added, changed ones replaced, all checked.

    The existing rules keep their order and new ones follow by heading, so the file's diff is the
    decisions. Raises `ValueError` naming the first decision `taxonomy` cannot count under.
    """
    rules = current.rules_by_heading()
    added = changed = unchanged = 0
    for decision in decisions:
        before = rules.get(decision.heading)
        if before is not None and before.position_id == decision.position_id:
            unchanged += 1
            continue
        if before is None:
            added += 1
        else:
            changed += 1
        rules[decision.heading] = HeadingOverride(
            heading=decision.heading, position_id=decision.position_id, decided=decided
        )
    order = [one.heading for one in current.overrides]
    order += sorted(heading for heading in rules if heading not in set(order))
    try:
        updated = OverrideRules(
            topic_id=current.topic_id, overrides=tuple(rules[heading] for heading in order)
        )
    except ValidationError as error:
        raise ValueError(str(error)) from error
    updated.check_against(taxonomy)
    return AppliedDecisions(rules=updated, added=added, changed=changed, unchanged=unchanged)
