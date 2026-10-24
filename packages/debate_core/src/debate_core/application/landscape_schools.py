"""The per-school view: each disclosing team's positions by side, from what the report counted (`v1-e32-t04`).

A pure grouping over :class:`~debate_core.application.landscape_counts.CountedReads`: it reads
nothing, writes nothing and calls no model. A row is one team, one side and one position, with the
team's rounds on that side that the report counted as reading it, so it holds exactly the report's
reads: no ANSWERS item, nothing below the review threshold or waiting in the review queue, no
placement in a round on the other side, and `v1-e32-t09`'s assigned aff, not a card's, for a round
it assigned. Affs are never read from headings here.

## Names as disclosed

The school and team code are shown exactly as the caselist's paths disclosed them
(`docs/policies/caselist-data-use.md`: school plus team code, as disclosed, never more). A team is
told apart without regard to case, as the report tells it; when its disclosures spell it more than one
way, the row shows the spelling most of them use, ties to the first in text order. A round's
tournament is shown the same way.

## What is left out

* A round whose path named no school or team code is no team, and a round on no readable side is on
  neither side, so neither is a row: :class:`~debate_core.domain.landscape_schools.SchoolView` counts
  them.
* Nothing but the position id and counts: no label, tag, cite, plan text or path.

## Last tournament

The tournament of the row's latest round, latest by the snapshot it was first seen in; among rounds
first seen in that same snapshot, the tournament most of them name, ties to the first in text order. A
row none of whose rounds named a tournament has none.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import date
from typing import Final

from debate_core.application.landscape_counts import AFF_SIDE, NEG_SIDE, CountedReads, round_id, team_identity
from debate_core.domain.caselist import Disclosure
from debate_core.domain.landscape_schools import SchoolRow, SchoolSide, SchoolView

__all__ = ["school_view"]

_SIDES: Final = {AFF_SIDE: SchoolSide.AFF, NEG_SIDE: SchoolSide.NEG}
_SIDE_ORDER: Final = {SchoolSide.AFF: 0, SchoolSide.NEG: 1}


def school_view(
    *, caselist: str, snapshot: date, disclosures: Iterable[Disclosure], counted: CountedReads
) -> SchoolView:
    """Every team's positions through `snapshot`, from the rounds and reads the report counted."""
    spellings: defaultdict[tuple[str, str], Counter[tuple[str, str]]] = defaultdict(Counter)
    tournaments: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for disclosure in disclosures:
        if disclosure.caselist != caselist or disclosure.snapshot > snapshot:
            continue
        one = round_id(disclosure)
        if one not in counted.rounds:
            continue
        team = team_identity(disclosure)
        if team is not None:
            spellings[team][(disclosure.school, disclosure.team_code)] += 1
        if disclosure.tournament:
            tournaments[one][disclosure.tournament] += 1

    groups: defaultdict[tuple[tuple[str, str], SchoolSide, str], set[str]] = defaultdict(set)
    no_team: set[str] = set()
    no_side: set[str] = set()
    for position_id, read in counted.reads.items():
        for one in read:
            stated = counted.rounds[one]
            side = _SIDES.get(stated.side)
            if stated.team is None:
                no_team.add(one)
            elif side is None:
                no_side.add(one)
            else:
                groups[(stated.team, side, position_id)].add(one)

    rows: list[SchoolRow] = []
    for (team, side, position_id), rounds in groups.items():
        school, team_code = _commonest(spellings[team])
        with_a_tournament = [one for one in rounds if one in tournaments]
        latest = max((counted.rounds[one].first_seen for one in with_a_tournament), default=None)
        named = Counter(
            _commonest(tournaments[one])
            for one in with_a_tournament
            if counted.rounds[one].first_seen == latest
        )
        rows.append(
            SchoolRow(
                school=school,
                team_code=team_code,
                side=side,
                position_id=position_id,
                rounds=len(rounds),
                last_tournament=_commonest(named) if named else None,
            )
        )
    rows.sort(
        key=lambda row: (
            row.school.casefold(),
            row.school,
            row.team_code.casefold(),
            row.team_code,
            _SIDE_ORDER[row.side],
            -row.rounds,
            row.position_id,
        )
    )
    return SchoolView(
        caselist=caselist,
        snapshot=snapshot,
        rows=tuple(rows),
        rounds_with_no_team=len(no_team),
        rounds_on_no_side=len(no_side),
    )


def _commonest[KeyT: str | tuple[str, str]](counts: Counter[KeyT]) -> KeyT:
    """The value most often seen, ties to the first in text order."""
    return min(counts, key=lambda value: (-counts[value], value))
