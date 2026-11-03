"""The per-school view: which positions each disclosing team read, on each side (`v1-e32-t04`).

To seed later scouting, the view lists for each school and team code, exactly as the caselist's
paths disclosed them, the positions its rounds read on the affirmative and on the negative, with how
many rounds. It counts what the circuit-wide report counts
(:mod:`debate_core.application.landscape_report`): reads only, at or above the review threshold, on
the round's own side, with `v1-e32-t09`'s aff assignments where they are given.

## What it may show, and what it never does

`docs/policies/caselist-data-use.md`, "What a report may show": the per-school and trend views may
show **school plus team code, as disclosed, never more**. So a row is a school, a team code, a side,
a position id and counts:

* no debater name: a team is the :class:`~debate_core.domain.caselist.TeamCodeText` its directory
  disclosed, never a name parsed from anywhere;
* no plan, counterplan or alternative text, `v1-e32-t09`'s verbatim texts included: policy 1.13 lets
  a team's own text be quoted only where no school or team code is beside it;
* no Tabroom result, rating or anything else beyond the caselist's disclosures, and no prediction of
  what a school will run.

## The team's page (`v1-e32-t18`)

Policy 1.14 adds exactly one thing to the row: a link to the team's public OpenCaselist page, built
from the caselist, the school and the team code alone. The view does not store it: it is
:meth:`SchoolView.team_page`, the search pilot's rule
(:func:`~debate_core.domain.search_source_links.team_page_url`) over the view's own caselist and the
row's school and team code, so no other link can be in a row. A team whose school or team code is not
one address word has none, and :attr:`SchoolView.teams_without_team_page` counts them by reason.

The view is written beside the circuit-wide report in its own files, `schools.csv` and `schools.md`,
so `report.md` and its CSVs still name nobody. It stays on the operator's machine and in the private
bucket's `reports/` prefix.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from enum import StrEnum
from typing import Final

from pydantic import Field

from debate_core.domain.base import DomainModel, NonEmptyText
from debate_core.domain.caselist import CaselistSlug, TeamCodeText
from debate_core.domain.landscape import PositionId
from debate_core.domain.search_source_links import NoTeamPage, team_page_url, why_no_team_page

__all__ = [
    "SCHOOL_VIEW_SIDES",
    "SchoolRow",
    "SchoolSide",
    "SchoolView",
]


class SchoolSide(StrEnum):
    """The side a school view row's rounds were on. PF's pro and con count as aff and neg."""

    AFF = "aff"
    NEG = "neg"


SCHOOL_VIEW_SIDES: Final = (SchoolSide.AFF, SchoolSide.NEG)
"""The sides in the view's order."""


class SchoolRow(DomainModel):
    """One team's reads of one position on one side: a row of schools.csv (ac4)."""

    school: NonEmptyText = Field(description="The school exactly as the caselist's path disclosed it.")
    team_code: TeamCodeText = Field(description="The team code exactly as disclosed, e.g. QX.")
    side: SchoolSide
    position_id: PositionId
    rounds: int = Field(ge=1, description="The team's rounds on this side that read the position.")


class SchoolView(DomainModel):
    """Every disclosing team's positions, through one snapshot."""

    caselist: CaselistSlug
    snapshot: date
    rows: tuple[SchoolRow, ...] = Field(description="By school, team code, side, then rounds and position.")
    rounds_with_no_team: int = Field(
        ge=0, description="Rounds reading a position whose path named no school or team code: left out."
    )
    rounds_on_no_side: int = Field(
        ge=0, description="Rounds reading a position by a known team on no readable side: left out."
    )

    @property
    def schools(self) -> int:
        return len({row.school.casefold() for row in self.rows})

    @property
    def teams(self) -> int:
        return len({(row.school.casefold(), row.team_code.casefold()) for row in self.rows})

    def team_page(self, row: SchoolRow) -> str | None:
        """The row's team's public OpenCaselist page, or `None` when the rule refuses it."""
        return team_page_url(self.caselist, row.school, row.team_code)

    @property
    def teams_without_team_page(self) -> Counter[NoTeamPage]:
        """The teams with no page, by why: each team once, by the spelling its rows show."""
        teams = {(row.school.casefold(), row.team_code.casefold()): row for row in self.rows}
        reasons = (why_no_team_page(self.caselist, row.school, row.team_code) for row in teams.values())
        return Counter(reason for reason in reasons if reason is not None)

    @property
    def teams_with_team_page(self) -> int:
        return self.teams - self.teams_without_team_page.total()
