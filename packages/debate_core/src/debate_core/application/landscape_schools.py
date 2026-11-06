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
way, the row shows the spelling most of them use, ties to the first in text order. That spelling is
what the link to the team's openCaselist page is built from, by the view itself
(:meth:`~debate_core.domain.landscape_schools.SchoolView.team_page`, `v1-e32-t18`); a row holds none.

## What is left out

* A round whose path named no school or team code is no team, and a round on no readable side is on
  neither side, so neither is a row: :class:`~debate_core.domain.landscape_schools.SchoolView` counts
  them.
* Nothing but the position id and counts in a row: no label, tag, cite, plan text, path, tournament or
  round (the PM's ruling of 2026-10-24 on `v1-e32-t04`'s question 2). The tournament and round are in
  the round lines alone, below.

## The rounds under each position (`v1-e32-t54`)

Policy 1.23 lets the view show, beside each position a team's disclosures hold, the tournament, round
and side of each disclosure whose file holds it, as disclosed. The view's
:attr:`~debate_core.domain.landscape_schools.SchoolView.round_lines` are those, by the PM's ruling of
2026-11-06:

* **One line per team, position and round**, never per file: a round two of whose files hold the
  position is one line. Its stance is `reads` when the report counts the round as reading the
  position, and `AT` when the round only answers it
  (:attr:`~debate_core.application.landscape_counts.CountedReads.answers`). A round on no readable
  side, or by no named team, is no line, as it is no row.
* **The positions a team reads come first**, in its rows' order, then those it only answers, by how
  many rounds answer them and then by id, each marked `answers_only`. Nothing is cut or capped.
* **Newest first.** Under a position, by the snapshot the round was first seen in, newest first; then
  by tournament, case-folded; then by round, latest first: an elimination round before a prelim
  (finals, semis, quarters, octas, doubles), a higher-numbered prelim before a lower one, and a label
  the platform does not recognise after those it does, in the order of its text. A round whose
  filename gave no tournament, or no round, goes after those that did. Shuffled inputs give the same
  lines, so the page reads the same every week.
* **As disclosed.** The tournament and the round are the filename's own words, the spelling most of
  the round's disclosures in range use, ties to the first in text order, as a team's name is. An
  unrecognised round label shows as written and is not flagged.
* **One file for N rounds.** `rounds_in_file` is how many of this team's rounds disclose the file that
  holds the position, the most of them where several files hold it: a file disclosed for one round is
  `1`, which the page leaves unmarked. Another team's disclosures of the same file are not counted. A
  round whose aff `v1-e32-t09` assigned holds that aff by every file of the round.

No line holds a tag, cite, heading, path or any other text of a card.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from typing import Final

from debate_core.application.landscape_counts import AFF_SIDE, NEG_SIDE, CountedReads, round_id, team_identity
from debate_core.domain.caselist import Disclosure, NormalizedRound
from debate_core.domain.landscape_schools import RoundStance, SchoolRound, SchoolRow, SchoolSide, SchoolView

__all__ = ["school_view"]

_SIDES: Final = {AFF_SIDE: SchoolSide.AFF, NEG_SIDE: SchoolSide.NEG}
_SIDE_ORDER: Final = {SchoolSide.AFF: 0, SchoolSide.NEG: 1}
_LATEST_FIRST: Final = {
    played: rank
    for rank, played in enumerate(
        (
            NormalizedRound.FINALS,
            NormalizedRound.SEMIS,
            NormalizedRound.QUARTERS,
            NormalizedRound.OCTAS,
            NormalizedRound.DOUBLES,
            NormalizedRound.R9,
            NormalizedRound.R8,
            NormalizedRound.R7,
            NormalizedRound.R6,
            NormalizedRound.R5,
            NormalizedRound.R4,
            NormalizedRound.R3,
            NormalizedRound.R2,
            NormalizedRound.R1,
        )
    )
}
"""A recognised round's place in a team's lines: the elimination rounds, then the prelims, latest first."""

type _Team = tuple[str, str]


def school_view(
    *, caselist: str, snapshot: date, disclosures: Iterable[Disclosure], counted: CountedReads
) -> SchoolView:
    """Every team's positions through `snapshot`, from the rounds and reads the report counted."""
    spellings: defaultdict[_Team, Counter[tuple[str, str]]] = defaultdict(Counter)
    disclosed = _Disclosed()
    for disclosure in disclosures:
        if disclosure.caselist != caselist or disclosure.snapshot > snapshot:
            continue
        one = round_id(disclosure)
        if one not in counted.rounds:
            continue
        team = team_identity(disclosure)
        if team is not None:
            spellings[team][(disclosure.school, disclosure.team_code)] += 1
        disclosed.add(one, disclosure)

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
        rows.append(
            SchoolRow(
                school=school,
                team_code=team_code,
                side=side,
                position_id=position_id,
                rounds=len(rounds),
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
        round_lines=_round_lines(
            counted, rows, {team: _commonest(found) for team, found in spellings.items()}, disclosed
        ),
    )


class _Disclosed:
    """What the round lines need of the disclosures in range: each round's spellings and files."""

    def __init__(self) -> None:
        self.labels: defaultdict[str, Counter[tuple[str, str]]] = defaultdict(Counter)
        """Round id to its (tournament, round label) as disclosed, empty where the filename gave none."""
        self.recognised: dict[str, NormalizedRound | None] = {}
        self.files: defaultdict[str, set[str]] = defaultdict(set)
        """Round id to the digests of its files."""
        self.rounds_of: defaultdict[str, set[str]] = defaultdict(set)
        """File digest to the rounds disclosing it."""

    def add(self, one: str, disclosure: Disclosure) -> None:
        label = disclosure.round_label
        self.labels[one][(disclosure.tournament or "", label.raw if label is not None else "")] += 1
        self.recognised.setdefault(one, label.normalized if label is not None else None)
        self.files[one].add(disclosure.source_sha256)
        self.rounds_of[disclosure.source_sha256].add(one)


def _round_lines(
    counted: CountedReads,
    rows: Sequence[SchoolRow],
    shown: Mapping[_Team, tuple[str, str]],
    disclosed: _Disclosed,
) -> tuple[SchoolRound, ...]:
    """Every team's rounds under each position it reads or answers, in the order the module states."""
    stances: defaultdict[_Team, defaultdict[str, dict[str, RoundStance]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    for found, stance in ((counted.reads, RoundStance.READS), (counted.answers, RoundStance.AT)):
        for position_id, rounds in found.items():
            for one in rounds:
                stated = counted.rounds[one]
                if stated.team is not None and stated.side in _SIDES:
                    stances[stated.team][position_id].setdefault(one, stance)
    read_order: defaultdict[_Team, list[str]] = defaultdict(list)
    for row in rows:
        listed = read_order[(row.school.casefold(), row.team_code.casefold())]
        if row.position_id not in listed:
            listed.append(row.position_id)

    def team_order(team: _Team) -> tuple[str, str, str, str]:
        school, code = shown[team]
        return (school.casefold(), school, code.casefold(), code)

    lines: list[SchoolRound] = []
    for team in sorted(stances, key=team_order):
        positions = stances[team]
        read = read_order.get(team, [])
        answered = sorted(
            (position_id for position_id in positions if position_id not in read),
            key=lambda position_id: (-len(positions[position_id]), position_id),
        )
        for position_id in (*read, *answered):
            rounds = positions[position_id]
            for one in sorted(rounds, key=lambda one: _line_order(one, counted, disclosed)):
                lines.append(
                    _line(
                        team,
                        shown[team],
                        position_id,
                        one,
                        rounds[one],
                        position_id not in read,
                        counted,
                        disclosed,
                    )
                )
    return tuple(lines)


def _line(
    team: _Team,
    shown: tuple[str, str],
    position_id: str,
    one: str,
    stance: RoundStance,
    answers_only: bool,
    counted: CountedReads,
    disclosed: _Disclosed,
) -> SchoolRound:
    stated = counted.rounds[one]
    tournament, label = _commonest(disclosed.labels[one])
    holding = counted.holding.get((position_id, one)) or disclosed.files[one]
    in_file = max(
        (sum(counted.rounds[other].team == team for other in disclosed.rounds_of[sha]) for sha in holding),
        default=1,
    )
    return SchoolRound(
        school=shown[0],
        team_code=shown[1],
        position_id=position_id,
        stance=stance,
        side=_SIDES[stated.side],
        tournament=tournament or None,
        round_label=label or None,
        snapshot=stated.first_seen,
        rounds_in_file=max(in_file, 1),
        answers_only=answers_only,
    )


def _line_order(one: str, counted: CountedReads, disclosed: _Disclosed) -> tuple[object, ...]:
    """Newest snapshot first, then the tournament case-folded, then the round latest first."""
    tournament, label = _commonest(disclosed.labels[one])
    recognised = disclosed.recognised.get(one)
    if not label:
        played: tuple[int, int, str, str] = (2, 0, "", "")
    elif recognised is not None:
        played = (0, _LATEST_FIRST[recognised], "", "")
    else:
        played = (1, 0, label.casefold(), label)
    stated = counted.rounds[one]
    return (
        -stated.first_seen.toordinal(),
        not tournament,
        tournament.casefold(),
        tournament,
        played,
        _SIDE_ORDER[_SIDES[stated.side]],
        one,
    )


def _commonest(counts: Counter[tuple[str, str]]) -> tuple[str, str]:
    """The value most often seen, ties to the first in text order."""
    return min(counts, key=lambda value: (-counts[value], value))
