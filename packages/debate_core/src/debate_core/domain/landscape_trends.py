"""What a landscape report's trends say: each position's change from one weekly window to the next.

`v1-e32-t04-trend-and-school-views` compares a caselist's snapshot with the one before it on the same
topic. A weekly archive holds about seven days of edits, not a running total (`v1-e30-t17`,
ADR-0016), so each snapshot is a **window**: the seven days up to and including its date. A week's
disclosures are the rounds first seen in its window, a week's disclosing teams the teams of those
rounds, and a position's weekly share the teams that read it on its own side over the week's teams
disclosing on that side (every team, for a position either side reads). This module is the trends as
values; `debate_core.application.landscape_trends` computes them and the renderer writes them out.

## Labels

* **NEW**: read in this window and in no earlier window on the topic. A caselist's first window, or
  the first after a topic change, is all NEW, with no previous share and no delta.
* **RISING** / **FALLING**: the share moved by at least the threshold (5 points by default), and at
  least the minimum of teams (3 by default) read it in one of the two weeks.
* **STEADY**: anything else. A row that moved by the threshold but that too few teams read is
  STEADY and :attr:`TrendRow.held_back_by_team_floor`, so one team does not make a trend.

A trend never compares two topics: when the window before this one is on another topic, the trends
start again here and :attr:`LandscapeTrends.topic_change` says so.

## What trends never hold

No school, team code or debater name: a team is a count, as in the circuit-wide report.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction
from typing import Final, Self

from pydantic import Field, model_validator

from debate_core.domain.base import DomainModel, NonEmptyText
from debate_core.domain.caselist import CaselistSlug
from debate_core.domain.landscape import PositionId, PositionKind, PositionSide

__all__ = [
    "DEFAULT_TREND_MINIMUM_TEAMS",
    "DEFAULT_TREND_THRESHOLD_POINTS",
    "WINDOW_DAYS",
    "LandscapeTrends",
    "TopicChange",
    "TrendLabel",
    "TrendRow",
    "WeeklyTeams",
    "window_start",
]

DEFAULT_TREND_THRESHOLD_POINTS: Final = Decimal(5)
"""The change in share, in percentage points, that RISING and FALLING need (ac2)."""

DEFAULT_TREND_MINIMUM_TEAMS: Final = 3
"""The teams that must read a position in one of the two weeks for it to rise or fall (ac2)."""

WINDOW_DAYS: Final = 7
"""A snapshot's window: the seven days up to and including its date (ADR-0016)."""


def window_start(snapshot: date) -> date:
    """The first day of `snapshot`'s window."""
    return snapshot - timedelta(days=WINDOW_DAYS - 1)


class TrendLabel(StrEnum):
    """A position's trend from the previous window to this one, in report order."""

    NEW = "NEW"
    RISING = "RISING"
    FALLING = "FALLING"
    STEADY = "STEADY"


class WeeklyTeams(DomainModel):
    """The teams disclosing in one window, by side: the denominators of its shares."""

    snapshot: date
    aff_teams: int = Field(
        ge=0, description="Distinct teams with a round first seen in it, on the affirmative."
    )
    neg_teams: int = Field(ge=0, description="Distinct teams with a round first seen in it, on the negative.")
    teams: int = Field(ge=0, description="Distinct teams with a round first seen in it, on any side.")

    def over(self, side: PositionSide) -> int:
        """The teams a share of a position of `side` is taken over."""
        if side is PositionSide.AFF:
            return self.aff_teams
        if side is PositionSide.NEG:
            return self.neg_teams
        return self.teams


class TrendRow(DomainModel):
    """One position read in this window or the previous one: a row of trends.csv (ac1)."""

    position_id: PositionId
    label: NonEmptyText
    kind: PositionKind
    side: PositionSide
    weekly_teams: int = Field(ge=0, description="Teams of this window's rounds reading it on its side.")
    weekly_disclosing: int = Field(ge=0, description="This window's teams disclosing on its side.")
    previous_teams: int | None = Field(
        ge=0, description="The same in the previous window; None when there is none on the topic."
    )
    previous_disclosing: int | None = Field(ge=0)
    trend: TrendLabel
    held_back_by_team_floor: bool = Field(
        description="It moved by the threshold, but fewer than the minimum of teams read it in either week."
    )

    @model_validator(mode="after")
    def _check_counts(self) -> Self:
        if self.weekly_teams > self.weekly_disclosing:
            raise ValueError("a position's weekly teams are among the week's disclosing teams")
        if (self.previous_teams is None) != (self.previous_disclosing is None):
            raise ValueError("a previous window has both its teams and its disclosing teams")
        if self.previous_teams is not None and self.previous_teams > (self.previous_disclosing or 0):
            raise ValueError("a position's previous teams are among that week's disclosing teams")
        if self.held_back_by_team_floor and self.trend is not TrendLabel.STEADY:
            raise ValueError("a row the team floor holds back is STEADY")
        return self

    @property
    def weekly_share(self) -> Fraction | None:
        """Its teams over the week's disclosing teams on its side; None when nobody disclosed there."""
        return _share(self.weekly_teams, self.weekly_disclosing)

    @property
    def previous_share(self) -> Fraction | None:
        if self.previous_teams is None or self.previous_disclosing is None:
            return None
        return _share(self.previous_teams, self.previous_disclosing)

    @property
    def delta_points(self) -> Fraction | None:
        """The change in share, in percentage points, exactly; None with no share on either side."""
        weekly, previous = self.weekly_share, self.previous_share
        if weekly is None or previous is None:
            return None
        return (weekly - previous) * 100


class TopicChange(DomainModel):
    """The window before this one is on another topic, so no trend crosses into this one (ac3)."""

    previous_snapshot: date
    previous_topic_id: PositionId


class LandscapeTrends(DomainModel):
    """One caselist's trends at one snapshot, on one topic."""

    caselist: CaselistSlug
    topic_id: PositionId
    snapshot: date = Field(description="This window's snapshot: the report's.")
    previous_snapshot: date | None = Field(
        description="The window before it on the same topic; None for the topic's first in the caselist."
    )
    topic_change: TopicChange | None = Field(
        description="When the caselist's snapshot before this one is on another topic."
    )
    windows: tuple[date, ...] = Field(
        min_length=1, description="Every window on the topic through this one, in date order."
    )
    topic_from: date | None = Field(description="The first snapshot date topics.yaml gives the topic here.")
    topic_to: date | None = Field(description="The last snapshot date topics.yaml gives the topic here.")
    threshold_points: Decimal = Field(gt=0)
    minimum_teams: int = Field(ge=1)
    weekly: WeeklyTeams
    previous: WeeklyTeams | None
    rows: tuple[TrendRow, ...] = Field(description="Every position read in either window, in report order.")

    @model_validator(mode="after")
    def _check_windows(self) -> Self:
        if self.windows[-1] != self.snapshot or list(self.windows) != sorted(set(self.windows)):
            raise ValueError("the windows are distinct, in date order, and end with the snapshot")
        if (self.previous_snapshot is None) != (self.previous is None):
            raise ValueError("a previous window has its disclosing teams")
        if self.previous_snapshot is not None and self.previous_snapshot not in self.windows[:-1]:
            raise ValueError("the previous window is one of the topic's earlier windows")
        if self.previous_snapshot is not None and self.topic_change is not None:
            raise ValueError("a topic change leaves no previous window on the topic")
        if (self.topic_from is None) != (self.topic_to is None):
            raise ValueError("the topic's range has both ends or neither")
        return self

    @property
    def covers_full_topic_cycle(self) -> bool | None:
        """Whether the windows run from the topic's start to its end; None when its range is unknown.

        The first window must open on or before the topic's first date, and the next window, a week
        after this one, would be past its last.
        """
        if self.topic_from is None or self.topic_to is None:
            return None
        return (
            window_start(self.windows[0]) <= self.topic_from
            and self.snapshot + timedelta(days=WINDOW_DAYS) > self.topic_to
        )

    @property
    def held_back(self) -> int:
        """The rows the team floor held back."""
        return sum(row.held_back_by_team_floor for row in self.rows)

    def labelled(self, trend: TrendLabel) -> tuple[TrendRow, ...]:
        return tuple(row for row in self.rows if row.trend is trend)


def _share(part: int, whole: int) -> Fraction | None:
    return Fraction(part, whole) if whole else None
