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
3. **`KRITIKAL_AFF_MARKER`** (`v1-e32-t17`, the PM's rulings of 2026-10-25, given
   :class:`KritikalSignals`). A round the two above leave unassigned, not conflicting and not placed,
   none of whose documents holds a plan text (`NONE`) and one of which holds a K-aff marker, reads the
   topic's K aff. The assignments above are never changed by it.
4. **`KRITIKAL_AFF_CARRY`.** A team whose only identified aff is the K aff (no plan text or placed
   card names another, and its rounds do not disagree) carries it into its other open rounds by step
   2's guard, every document `NONE`, and never into a round whose own file reads an advantage (a card
   t02 placed under one, READS, at or above the review threshold: t15's placement). Such a round stays
   unidentified and its key is counted (:attr:`AssignmentCounts.refused_by_advantage`). Given transition
   readings (`v1-e32-t24`, the PM's ruling 3 of 2026-10-26), never into a round whose own file holds a
   plan text under a transition label naming a policy aff either: that round is left to step 5, and its
   key is counted (:attr:`AssignmentCounts.refused_by_transition_plan`).
5. **`TRANSITION_PLAN_TEXT`** (`v1-e32-t24`, given each document's verdict over its plan texts under
   `Thus the plan`, `Thus plan` or `Thus`). A round the steps above leave open, not conflicting and not
   placed, every document of which has no plan text t09 reads (`NONE`), reads the aff those plan texts
   name. Two affs named, or a document whose own such plan texts conflict, are a conflict: nothing is
   assigned.
6. **`TRANSITION_PLAN_CARRY`.** A team with a round step 5 identified, whose assigned and placed affs
   narrow to one and whose rounds neither disagree nor conflict, carries it into its other open rounds by
   step 2's guard, every document `NONE`, and only where no document holds a plan text under a transition
   label either. Rounds another step identified against their own such plan text naming another aff are
   kept as they are and counted (:attr:`AssignmentCounts.transition_control`).
7. **Otherwise nothing.** A round no signal identifies is not assigned, and the report shows it as
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
    "KRITIKAL_AFF_CARRY_METHOD",
    "KRITIKAL_AFF_MARKER_METHOD",
    "PLAN_TEXT_METHOD",
    "TEAM_CARRY_METHOD",
    "TRANSITION_PLAN_CARRY_METHOD",
    "TRANSITION_PLAN_TEXT_METHOD",
    "AffRound",
    "AssignedAff",
    "AssignmentCounts",
    "KritikalSignals",
    "assign_affs",
]

PLAN_TEXT_METHOD: Final = "PLAN_TEXT"
TEAM_CARRY_METHOD: Final = "TEAM_CARRY"
KRITIKAL_AFF_MARKER_METHOD: Final = "KRITIKAL_AFF_MARKER"
KRITIKAL_AFF_CARRY_METHOD: Final = "KRITIKAL_AFF_CARRY"
TRANSITION_PLAN_TEXT_METHOD: Final = "TRANSITION_PLAN_TEXT"
TRANSITION_PLAN_CARRY_METHOD: Final = "TRANSITION_PLAN_CARRY"
_UNREAD: Final = DocumentPlanText(PlanTextVerdict.UNREAD)
_NO_PLAN_TEXT: Final = DocumentPlanText(PlanTextVerdict.NONE)


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
class KritikalSignals:
    """What names a round's kritikal affirmative (`v1-e32-t17`): its id, the files with a marker, and the
    rounds reading an advantage, which a K aff is never carried into."""

    position_id: str
    marker_documents: frozenset[str] = field(repr=False)
    """Source digests holding a K-aff marker."""
    advantage_rounds: frozenset[str] = field(repr=False)
    """Round keys whose own files carry a card t02 placed under an advantage (READS, at or above the
    review threshold): t15's placement."""


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
    refused_by_advantage: tuple[str, ...] = ()
    """Round keys a K aff was not carried into because their own file reads an advantage, sorted."""
    refused_by_transition_plan: tuple[str, ...] = ()
    """Round keys a K aff was not carried into because their own file holds a plan text under a transition
    label naming a policy aff (`v1-e32-t24`), sorted."""
    transition_conflicting: int = 0
    """Open rounds whose plan texts under a transition label name two affs, left unassigned (`v1-e32-t24`)."""
    transition_carry_refused: int = 0
    """Open rounds of a team carrying a transition plan's aff, refused because of their own plan text."""
    transition_control: tuple[str, ...] = ()
    """Round keys another method identifies whose own file holds a plan text under a transition label
    naming another aff (`v1-e32-t24`): kept as they are, and counted. Sorted."""


def assign_affs(
    rounds: Sequence[AffRound],
    plan_texts: Mapping[str, DocumentPlanText],
    placed: Mapping[str, frozenset[str]],
    vocabulary: PlanTextVocabulary,
    kritikal: KritikalSignals | None = None,
    transition: Mapping[str, DocumentPlanText] | None = None,
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
    refused = placed_only = 0

    def no_plan_text(one: AffRound) -> bool:
        return all(
            plan_texts.get(document, _UNREAD).verdict is PlanTextVerdict.NONE for document in one.documents
        )

    for one in rounds:
        if one.round_key in assigned:
            continue
        if placed.get(one.round_key):
            placed_only += 1
            continue
        aff = carried_by.get(one.team) if one.team is not None else None
        if aff is not None and one.round_key not in conflicting:
            if no_plan_text(one):
                assigned[one.round_key] = AssignedAff(one.round_key, aff, TEAM_CARRY_METHOD)
                carrying.add(one.team or "")
                continue
            refused += 1
    transition_readings = transition or {}

    def transition_of(one: AffRound) -> list[DocumentPlanText]:
        return [transition_readings.get(document, _NO_PLAN_TEXT) for document in one.documents]

    refused_by_advantage: list[str] = []
    refused_by_transition: list[str] = []
    if kritikal is not None:
        open_rounds = [
            one
            for one in rounds
            if one.round_key not in assigned
            and not placed.get(one.round_key)
            and one.round_key not in conflicting
        ]
        marked: set[str] = set()
        for one in open_rounds:
            if no_plan_text(one) and any(document in kritikal.marker_documents for document in one.documents):
                assigned[one.round_key] = AssignedAff(
                    one.round_key, kritikal.position_id, KRITIKAL_AFF_MARKER_METHOD
                )
                if one.team is not None:
                    marked.add(one.team)
        for one in open_rounds:
            if one.round_key in assigned or one.team is None or one.team not in marked:
                continue
            # A team with another aff carried it into every open round with no plan text first, so it
            # has no marker round here; a team whose rounds disagree carries nothing.
            if one.team in disagreeing:
                continue
            if not no_plan_text(one):
                refused += 1
            elif one.round_key in kritikal.advantage_rounds:
                refused_by_advantage.append(one.round_key)
            elif transition is not None and _names_an_aff(transition_of(one)):
                refused_by_transition.append(one.round_key)
            else:
                assigned[one.round_key] = AssignedAff(
                    one.round_key, kritikal.position_id, KRITIKAL_AFF_CARRY_METHOD
                )
    transition_conflicting: set[str] = set()
    transition_refused = 0
    control: list[str] = []
    if transition is not None:
        open_rounds = [
            one
            for one in rounds
            if one.round_key not in assigned
            and not placed.get(one.round_key)
            and one.round_key not in conflicting
        ]
        reading: set[str] = set()
        for one in open_rounds:
            if not no_plan_text(one):
                continue
            found = transition_of(one)
            named = vocabulary.narrowest(_named(found))
            if len(named) > 1 or any(each.verdict is PlanTextVerdict.CONFLICTING for each in found):
                transition_conflicting.add(one.round_key)
            elif named:
                assigned[one.round_key] = AssignedAff(one.round_key, named[0], TRANSITION_PLAN_TEXT_METHOD)
                if one.team is not None:
                    reading.add(one.team)
        team_affs: defaultdict[str, set[str]] = defaultdict(set)
        split = set(disagreeing)
        for one in rounds:
            if one.team is None:
                continue
            if one.round_key in assigned:
                team_affs[one.team].add(assigned[one.round_key].position_id)
            team_affs[one.team].update(placed.get(one.round_key, frozenset()))
            if one.round_key in transition_conflicting:
                split.add(one.team)
        carried_transition = {
            team: narrowed[0]
            for team in reading
            if team not in split and len(narrowed := vocabulary.narrowest(team_affs[team])) == 1
        }
        for one in open_rounds:
            if (
                one.round_key in assigned
                or one.round_key in transition_conflicting
                or one.team not in carried_transition
            ):
                continue
            if not no_plan_text(one) or any(
                each.verdict is not PlanTextVerdict.NONE for each in transition_of(one)
            ):
                transition_refused += 1
                continue
            assigned[one.round_key] = AssignedAff(
                one.round_key, carried_transition[one.team], TRANSITION_PLAN_CARRY_METHOD
            )

        def known_otherwise(one: AffRound) -> set[str]:
            """The round's aff as another method identified it: its assignment, or its placed cards."""
            found = assigned.get(one.round_key)
            if found is None:
                return set(placed.get(one.round_key, frozenset[str]()))
            if found.method in (TRANSITION_PLAN_TEXT_METHOD, TRANSITION_PLAN_CARRY_METHOD):
                return set()
            return {found.position_id}

        for one in rounds:
            known = known_otherwise(one)
            if not known:
                continue
            found = transition_of(one)
            named = _named(found)
            if any(each.verdict is PlanTextVerdict.CONFLICTING for each in found) or (
                named and len(vocabulary.narrowest(known | named)) > len(vocabulary.narrowest(known))
            ):
                control.append(one.round_key)
    ordered = tuple(assigned[key] for key in sorted(assigned))
    return ordered, AssignmentCounts(
        rounds=len(rounds),
        by_method=dict(sorted(Counter(one.method for one in ordered).items())),
        placed_only=placed_only,
        unidentified=len(rounds) - len(ordered) - placed_only,
        conflicting=len(conflicting),
        carry_refused=refused,
        teams_carrying=len(carrying),
        teams_disagreeing=len(disagreeing),
        refused_by_advantage=tuple(sorted(refused_by_advantage)),
        refused_by_transition_plan=tuple(sorted(refused_by_transition)),
        transition_conflicting=len(transition_conflicting),
        transition_carry_refused=transition_refused,
        transition_control=tuple(sorted(control)),
    )


def _named(found: Sequence[DocumentPlanText]) -> set[str]:
    return {each.position_id for each in found if each.verdict is PlanTextVerdict.NAMES and each.position_id}


def _names_an_aff(found: Sequence[DocumentPlanText]) -> bool:
    return any(each.verdict in (PlanTextVerdict.NAMES, PlanTextVerdict.CONFLICTING) for each in found)
