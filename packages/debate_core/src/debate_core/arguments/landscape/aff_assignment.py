"""Each affirmative round's aff, and the signal that named it (`v1-e32-t09` ac4).

`v1-e32-t03`'s report counts an affirmative round under the aff `v1-e32-t09` assigns it, with the
method that named it, and otherwise under an aff a card in the round was placed under
(`PLACED_CARD`, t02's matcher). :func:`assign_affs` makes the assignments, by the PM's rulings of
2026-10-24:

1. **`PLAN_TEXT`.** A round whose documents' plan texts name one aff
   (:func:`~debate_core.arguments.landscape.plan_text.document_plan_text`) reads that aff. Two
   documents naming two affs, or one document whose plan texts conflict, leave it unassigned. A
   parent and its child named in one round name the child, as they do in one document.
2. **`TEAM_CARRY`.** A team whose identified rounds all name one aff, by plan text or by a placed
   card (a parent and its child counting as the child), reads it in its other affirmative rounds
   too, but only in a round none of whose documents holds a plan text of its own (verdict `NONE`):
   never into a round whose plan text names something else, conflicts, or could not be read (a
   document with no reading counts as unread). A round t02 placed under an aff is left to the report.
   A team whose rounds name two affs, or hold a conflicting round, carries nothing, and a round
   disclosed by no readable team is never carried into or from.
3. **Otherwise nothing.** A round no signal identifies is not assigned, and the report shows it as
   unidentified. A round t02 placed under an aff and no plan text names is left to the report's
   `PLACED_CARD`.

Rounds are named by the caller's keys (t03's round ids) and teams by opaque identities: this module
never sees a school, a code, a path or a word of any file. Pure and deterministic.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from debate_core.arguments.landscape.plan_text import DocumentPlanText, PlanTextVerdict, PlanTextVocabulary

__all__ = [
    "PLAN_TEXT_METHOD",
    "TEAM_CARRY_METHOD",
    "AffRound",
    "AssignedAff",
    "AssignmentCounts",
    "assign_affs",
]

PLAN_TEXT_METHOD: Final = "PLAN_TEXT"
TEAM_CARRY_METHOD: Final = "TEAM_CARRY"
_UNREAD: Final = DocumentPlanText(PlanTextVerdict.UNREAD)


@dataclass(frozen=True, slots=True)
class AffRound:
    """One affirmative round: its key, its team, and the documents disclosed for it."""

    round_key: str
    team: str | None = field(repr=False)
    """An opaque identity equal for two rounds of one team; None for a round no readable team disclosed."""
    documents: tuple[str, ...]
    """The source digests disclosed for the round."""


@dataclass(frozen=True, slots=True)
class AssignedAff:
    round_key: str
    position_id: str
    method: str


@dataclass(frozen=True, slots=True)
class AssignmentCounts:
    rounds: int
    by_method: dict[str, int]
    placed_only: int
    """Rounds left to the report's `PLACED_CARD`: an aff placed, and no plan text naming one."""
    unidentified: int
    conflicting: int
    """Of the unidentified, rounds whose plan texts name two affs."""
    carry_refused: int
    """Unassigned rounds of a team that carries an aff, refused because of their own plan text."""
    teams_carrying: int
    teams_disagreeing: int


def assign_affs(
    rounds: Sequence[AffRound],
    plan_texts: Mapping[str, DocumentPlanText],
    placed: Mapping[str, frozenset[str]],
    vocabulary: PlanTextVocabulary,
) -> tuple[tuple[AssignedAff, ...], AssignmentCounts]:
    """Each round's aff by plan text, then by its team's other rounds, in round-key order, with counts.

    `plan_texts` holds each document's verdict by source digest, and `placed` the affs t02 placed a
    card of the round under (READS, at or above the review threshold), by round key.
    """
    assigned: dict[str, AssignedAff] = {}
    conflicting: set[str] = set()
    for one in rounds:
        verdicts = [plan_texts.get(document, _UNREAD) for document in one.documents]
        named = vocabulary.narrowest(
            {
                found.position_id
                for found in verdicts
                if found.verdict is PlanTextVerdict.NAMES and found.position_id
            }
        )
        if len(named) > 1 or any(found.verdict is PlanTextVerdict.CONFLICTING for found in verdicts):
            conflicting.add(one.round_key)
        elif named:
            assigned[one.round_key] = AssignedAff(one.round_key, named[0], PLAN_TEXT_METHOD)
    identified: dict[str, set[str]] = defaultdict(set)
    disagreeing: set[str] = set()
    for one in rounds:
        if one.team is None:
            continue
        found = identified[one.team]
        if one.round_key in assigned:
            found.add(assigned[one.round_key].position_id)
        found.update(placed.get(one.round_key, frozenset()))
        if one.round_key in conflicting:
            disagreeing.add(one.team)
    carried_by: dict[str, str] = {}
    for team, found in identified.items():
        narrowed = vocabulary.narrowest(found)
        if len(narrowed) > 1:
            disagreeing.add(team)
        elif narrowed and team not in disagreeing:
            carried_by[team] = narrowed[0]
    carrying: set[str] = set()
    refused = placed_only = unidentified = 0
    for one in rounds:
        if one.round_key in assigned:
            continue
        if placed.get(one.round_key):
            placed_only += 1
            continue
        aff = carried_by.get(one.team) if one.team is not None else None
        if aff is not None and one.round_key not in conflicting:
            if all(
                plan_texts.get(document, _UNREAD).verdict is PlanTextVerdict.NONE
                for document in one.documents
            ):
                assigned[one.round_key] = AssignedAff(one.round_key, aff, TEAM_CARRY_METHOD)
                carrying.add(one.team or "")
                continue
            refused += 1
        unidentified += 1
    ordered = tuple(assigned[key] for key in sorted(assigned))
    return ordered, AssignmentCounts(
        rounds=len(rounds),
        by_method=dict(sorted(Counter(one.method for one in ordered).items())),
        placed_only=placed_only,
        unidentified=unidentified,
        conflicting=len(conflicting),
        carry_refused=refused,
        teams_carrying=len(carrying),
        teams_disagreeing=len(disagreeing),
    )
