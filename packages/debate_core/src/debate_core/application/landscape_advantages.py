"""The advantages each affirmative's teams read, for report.md (`v1-e32-t15`).

A pure count over what the landscape report already decided
(:class:`~debate_core.application.landscape_counts.CountedReads`), so a read here is the report's:

* **A round reads an advantage** when the report counts it as reading one (`v1-e32-t03`'s rule: a card
  of one of the files the round discloses, placed under the advantage, READS, at or above the review
  threshold, the round not on the other side). Only affirmative rounds are counted. Nothing is taken
  from an advantage's name or its taxonomy `parent`.
* **A round's aff** is `v1-e32-t09`'s assignment, the only source (the PM's ruling of 2026-10-24). An
  advantage read in a round assigned to another aff is never counted under this one. A round whose aff
  only a placed card identifies (`PLACED_CARD`) has no assigned aff, and is counted with those.
* **A mechanism** is an aff whose parent is an aff. A round assigned to one counts under it and once
  under its top-level aff: an aff's rounds are a set, so a team reading an advantage under the aff
  itself and under a mechanism is one team there.
* **An aff's advantages** rank by distinct teams, then by id, and the first `limit` are shown. The rest
  are counted with the distinct teams reading any of them, never a sum, which would count a team once
  per advantage it reads.

Teams are opaque here: only their number leaves this module.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator, Mapping, Set
from dataclasses import dataclass, field

from debate_core.application.landscape_counts import AFF_SIDE, CountedReads
from debate_core.domain.landscape import Position, PositionKind, Taxonomy
from debate_core.domain.landscape_report import (
    AdvantagesByAff,
    AffAdvantage,
    AffAdvantages,
    AffWithoutAdvantages,
    UnassignedAdvantageReads,
)

__all__ = ["advantages_by_aff"]


def advantages_by_aff(
    *,
    taxonomy: Taxonomy,
    counted: CountedReads,
    assigned: Mapping[str, str],
    placed_card_rounds: Set[str],
    limit: int,
) -> AdvantagesByAff | None:
    """Each assigned aff's and mechanism's advantages, and the advantage reads with no assigned aff.

    `assigned` is round id to the aff `v1-e32-t09` assigned it, resolved; `placed_card_rounds` the
    affirmative rounds the report identified by a placed card alone. None when the taxonomy has no
    advantage.
    """
    advantages = [one.id for one in taxonomy.active_positions if one.kind is PositionKind.ADVANTAGE]
    if not advantages:
        return None
    rounds = counted.rounds
    read: defaultdict[str, set[str]] = defaultdict(set)
    """Affirmative round to the advantages the report counts it as reading."""
    for advantage in advantages:
        for one in counted.reads.get(advantage, ()):
            if rounds[one].side == AFF_SIDE:
                read[one].add(advantage)
    sections: dict[str, _Section] = {}
    for one, aff in sorted(assigned.items()):
        line = list(_aff_line(taxonomy, aff))
        for position in line:
            sections.setdefault(position.id, _Section(position, line[-1])).rounds.add(one)

    def order(section: _Section) -> tuple[int, int, str]:
        return (-len(section.teams(counted)), -len(section.rounds), section.position.id)

    ordered: list[_Section] = []
    for top in sorted((one for one in sections.values() if one.mechanism_of is None), key=order):
        ordered.append(top)
        ordered += sorted(
            (
                one
                for one in sections.values()
                if one.mechanism_of is not None and one.top.id == top.position.id
            ),
            key=order,
        )
    affs: list[AffAdvantages] = []
    without: list[AffWithoutAdvantages] = []
    for section in ordered:
        shown = section.shown(read, counted, limit, taxonomy)
        if shown is not None:
            affs.append(shown)
            continue
        without.append(
            AffWithoutAdvantages(
                position_id=section.position.id,
                label=section.position.label,
                mechanism_of=section.mechanism_of,
                mechanism_of_label=None if section.mechanism_of is None else section.top.label,
                rounds=len(section.rounds),
            )
        )
    unassigned = [one for one in sorted(read) if one not in assigned]
    return AdvantagesByAff(
        advantages_per_aff=limit,
        affs=tuple(affs),
        without_advantages=tuple(without),
        unassigned=UnassignedAdvantageReads(
            reads=sum(len(read[one]) for one in unassigned),
            rounds=len(unassigned),
            teams=len({team for one in unassigned if (team := rounds[one].team) is not None}),
            placed_card_rounds=sum(one in placed_card_rounds for one in unassigned),
        ),
    )


@dataclass(slots=True)
class _Section:
    """One aff's or mechanism's assigned rounds: its own, and for a top-level aff its mechanisms'."""

    position: Position
    top: Position
    """The top-level aff it is listed under; itself for that aff."""
    rounds: set[str] = field(default_factory=set[str])

    @property
    def mechanism_of(self) -> str | None:
        return None if self.top.id == self.position.id else self.top.id

    def teams(self, counted: CountedReads, rounds: Set[str] | None = None) -> set[tuple[str, str]]:
        """The distinct teams of the section's rounds, or of `rounds` among them."""
        return {
            team
            for one in (self.rounds if rounds is None else rounds)
            if (team := counted.rounds[one].team) is not None
        }

    def shown(
        self, read: Mapping[str, set[str]], counted: CountedReads, limit: int, taxonomy: Taxonomy
    ) -> AffAdvantages | None:
        """The section's top `limit` advantages and what they hide; None when its rounds read none."""
        teams: defaultdict[str, set[tuple[str, str]]] = defaultdict(set)
        reading: set[str] = set()
        for one in self.rounds:
            for advantage in read.get(one, ()):
                reading.add(one)
                teams[advantage] |= self.teams(counted, {one})
        if not reading:
            return None
        ranked = sorted(teams, key=lambda advantage: (-len(teams[advantage]), advantage))
        hidden = ranked[limit:]
        return AffAdvantages(
            position_id=self.position.id,
            label=self.position.label,
            mechanism_of=self.mechanism_of,
            mechanism_of_label=None if self.mechanism_of is None else self.top.label,
            rounds=len(self.rounds),
            teams=len(self.teams(counted)),
            advantage_teams=len(self.teams(counted, reading)),
            advantages=tuple(
                AffAdvantage(
                    position_id=advantage,
                    label=taxonomy.position(advantage).label,
                    teams=len(teams[advantage]),
                )
                for advantage in ranked[:limit]
            ),
            more=len(hidden),
            more_teams=len({team for advantage in hidden for team in teams[advantage]}),
        )


def _aff_line(taxonomy: Taxonomy, aff_id: str) -> Iterator[Position]:
    """The assigned aff, then each aff above it, ending at its top-level aff.

    A parent that is not an active aff ends the line, so the aff below it is its top level.
    """
    position = taxonomy.resolve(aff_id)
    yield position
    while position.parent is not None:
        parent = taxonomy.resolve(position.parent)
        if parent.kind is not PositionKind.AFF or parent.deprecated:
            return
        position = parent
        yield position
