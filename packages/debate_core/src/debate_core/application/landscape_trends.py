"""Weekly trends: each position's share of the week's disclosing teams, against the week before.

`v1-e32-t04`. A pure computation over what the report counted
(:class:`~debate_core.application.landscape_counts.CountedReads`): it reads nothing, writes nothing
and calls no model.

## Weeks come from first-seen rounds, not from one archive

An archive holds seven days of edits, so its team list is the teams who edited something that week,
not the teams who competed (ADR-0016), and a file carried into the next archive under a new path is
not a new disclosure. So a **week's disclosures** are the rounds first seen in that snapshot's window,
across the whole accumulated store: a round is its team, side, tournament and round, never its path
(:func:`~debate_core.application.landscape_counts.round_id`), and it is first seen in the earliest
snapshot that lists it. A **week's disclosing teams**, on a side, are the teams of those rounds on
that side.

A position's **weekly teams** are the teams of the week's rounds the report counted as reading it, on
its own side (any side, for a position either side reads), and its **weekly share** those over the
week's teams disclosing on that side. Its **delta** is this week's share less the previous week's, in
percentage points, exactly; it is rounded only when written.

## The previous week, and topics

The previous week is the caselist's snapshot just before this one. When `snapshot_topics` puts it on
another topic, there is none: trends never compare two topics (the LD and PF topics rotate), and the
result names the change. A round first seen in a snapshot `snapshot_topics` puts on another topic is
refused with :class:`TrendsCrossTopics`: it would carry one topic's reads into the other's weeks.

## Labels

NEW when no earlier window on the topic read the position, and for every position when there is no
previous week; otherwise RISING or FALLING when the delta is at least the threshold either way and at
least the minimum of teams read it in one of the two weeks, and STEADY when not. A delta of the
threshold that too few teams make is STEADY and held back by the team floor; the threshold and the
floor are never relaxed to make a row appear. With no team disclosing on its side in one of the two
weeks a position has no delta and is STEADY.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from fractions import Fraction
from typing import Final

from debate_core.application.errors import DomainError
from debate_core.application.landscape_counts import AFF_SIDE, NEG_SIDE, CountedReads, CountedRound
from debate_core.domain.landscape import Position, PositionKind, PositionSide, Taxonomy
from debate_core.domain.landscape_trends import (
    DEFAULT_TREND_MINIMUM_TEAMS,
    DEFAULT_TREND_THRESHOLD_POINTS,
    LandscapeTrends,
    TopicChange,
    TrendLabel,
    TrendRow,
    WeeklyTeams,
)

__all__ = ["TrendsCrossTopics", "landscape_trends"]

_SIDE_ORDER: Final = {PositionSide.AFF: 0, PositionSide.NEG: 1, PositionSide.BOTH: 2}
_KIND_ORDER: Final = {kind: index for index, kind in enumerate(PositionKind)}


class TrendsCrossTopics(DomainError):
    """A round counted for the trends was first seen in a snapshot on another topic."""


def landscape_trends(
    *,
    caselist: str,
    taxonomy: Taxonomy,
    counted: CountedReads,
    snapshot: date,
    snapshot_topics: Mapping[date, str] | None = None,
    topic_range: tuple[date, date] | None = None,
    threshold_points: Decimal = DEFAULT_TREND_THRESHOLD_POINTS,
    minimum_teams: int = DEFAULT_TREND_MINIMUM_TEAMS,
) -> LandscapeTrends:
    """The trends of `snapshot`'s window, from the rounds and reads the report counted.

    `snapshot_topics` is each snapshot of the caselist through `snapshot` the store holds, with the
    topic `topics.yaml` puts it on; None takes every round's snapshot to be on the taxonomy's topic.
    `topic_range` is the first and last snapshot date `topics.yaml` gives the topic in this caselist.
    """
    if threshold_points <= 0:
        raise ValueError(f"the trend threshold is above 0 points; got {threshold_points}")
    if minimum_teams < 1:
        raise ValueError(f"the team floor is at least one team; got {minimum_teams}")
    topic = taxonomy.topic_id
    topics = dict(snapshot_topics or {})
    for stated in counted.rounds.values():
        other = topics.get(stated.first_seen, topic)
        if other != topic:
            raise TrendsCrossTopics(
                f"a round counted under {topic} was first seen on {stated.first_seen.isoformat()}, which "
                f"topics.yaml puts on {other}; a trend never compares two topics"
            )
    rounds = {one: stated for one, stated in counted.rounds.items() if stated.first_seen <= snapshot}
    windows = sorted(
        {stated.first_seen for stated in rounds.values()}
        | {day for day, on in topics.items() if on == topic and day <= snapshot}
        | {snapshot}
    )
    earlier = sorted(day for day in {*topics, *windows} if day < snapshot)
    before = earlier[-1] if earlier else None
    change = None
    if before is not None and topics.get(before, topic) != topic:
        change = TopicChange(previous_snapshot=before, previous_topic_id=topics[before])
        before = None

    weekly = _weekly_teams(rounds, snapshot)
    previous = _weekly_teams(rounds, before) if before is not None else None
    threshold = Fraction(threshold_points)
    rows: list[TrendRow] = []
    for position_id, read in counted.reads.items():
        reading = {one: rounds[one] for one in read if one in rounds}
        if not reading:
            continue
        seen = {stated.first_seen for stated in reading.values()}
        if snapshot not in seen and (before is None or before not in seen):
            continue
        position = taxonomy.position(position_id)
        weekly_teams = _teams_reading(position, reading, snapshot)
        if previous is None or before is None:
            rows.append(_row(position, weekly_teams, weekly, None, None, TrendLabel.NEW, held_back=False))
            continue
        previous_teams = _teams_reading(position, reading, before)
        row = _row(
            position, weekly_teams, weekly, previous_teams, previous, TrendLabel.STEADY, held_back=False
        )
        delta = row.delta_points
        if min(seen) == snapshot:
            trend, held_back = TrendLabel.NEW, False
        elif delta is None or abs(delta) < threshold:
            trend, held_back = TrendLabel.STEADY, False
        elif max(weekly_teams, previous_teams) < minimum_teams:
            trend, held_back = TrendLabel.STEADY, True
        else:
            trend, held_back = (TrendLabel.RISING if delta > 0 else TrendLabel.FALLING), False
        rows.append(row.evolve(trend=trend, held_back_by_team_floor=held_back))
    rows.sort(key=lambda row: (_SIDE_ORDER[row.side], _KIND_ORDER[row.kind], row.position_id))
    return LandscapeTrends(
        caselist=caselist,
        topic_id=topic,
        snapshot=snapshot,
        previous_snapshot=before,
        topic_change=change,
        windows=tuple(day for day in windows if topics.get(day, topic) == topic),
        topic_from=topic_range[0] if topic_range else None,
        topic_to=topic_range[1] if topic_range else None,
        threshold_points=threshold_points,
        minimum_teams=minimum_teams,
        weekly=weekly,
        previous=previous,
        rows=tuple(rows),
    )


def _weekly_teams(rounds: Mapping[str, CountedRound], window: date) -> WeeklyTeams:
    """The teams with a round first seen in `window`, by side."""
    first_seen = [stated for stated in rounds.values() if stated.first_seen == window]
    return WeeklyTeams(
        snapshot=window,
        aff_teams=len({one.team for one in first_seen if one.team is not None and one.side == AFF_SIDE}),
        neg_teams=len({one.team for one in first_seen if one.team is not None and one.side == NEG_SIDE}),
        teams=len({one.team for one in first_seen if one.team is not None}),
    )


def _teams_reading(position: Position, reading: Mapping[str, CountedRound], window: date) -> int:
    """The teams of `window`'s rounds reading `position` on its own side, or on any side for `both`."""
    own_side = None if position.side is PositionSide.BOTH else position.side.value
    return len(
        {
            stated.team
            for stated in reading.values()
            if stated.first_seen == window
            and stated.team is not None
            and (own_side is None or stated.side == own_side)
        }
    )


def _row(
    position: Position,
    weekly_teams: int,
    weekly: WeeklyTeams,
    previous_teams: int | None,
    previous: WeeklyTeams | None,
    trend: TrendLabel,
    *,
    held_back: bool,
) -> TrendRow:
    return TrendRow(
        position_id=position.id,
        label=position.label,
        kind=position.kind,
        side=position.side,
        weekly_teams=weekly_teams,
        weekly_disclosing=weekly.over(position.side),
        previous_teams=previous_teams,
        previous_disclosing=previous.over(position.side) if previous is not None else None,
        trend=trend,
        held_back_by_team_floor=held_back,
    )
