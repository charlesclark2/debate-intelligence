"""Each affirmative round's aff for the landscape report, by plan text and by the team's other rounds.

`v1-e32-t09` ac4, through `v1-e32-t03`'s seam. :func:`build_aff_assignments` turns a caselist's
on-topic disclosures, `v1-e32-t02`'s classifications and each affirmative file's plan-text verdict
(:class:`~debate_core.application.plan_texts.PlanTextService`) into the
:class:`~debate_core.domain.landscape_report.AffAssignment` values the report counts:

* **a round** is t03's: :func:`~debate_core.application.landscape_report.round_id` of its
  disclosures, so the report and this module always mean the same round; only affirmative (or pro)
  rounds dated on or before `through` are assigned;
* **a placed aff** is t03's `PLACED_CARD` rule: a card of the round's files `v1-e32-t02` placed under
  an aff (through its `merged_into` links), READS, at or above the review threshold;
* **the assignment** is :func:`~debate_core.arguments.landscape.aff_assignment.assign_affs`':
  `PLAN_TEXT`, then `TEAM_CARRY`, and a round no signal identifies is not assigned.

A team is the round's school and team code, compared without case, and is only ever an opaque key
here. Nothing is written or logged.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Final

from debate_core.application.caselist.path_parser import UNKNOWN_SCHOOL, UNKNOWN_TEAM_CODE
from debate_core.application.landscape_report import round_id
from debate_core.arguments.landscape.aff_assignment import AffRound, AssignmentCounts, assign_affs
from debate_core.arguments.landscape.plan_text import DocumentPlanText, PlanTextVocabulary
from debate_core.arguments.landscape.review_queue import DEFAULT_REVIEW_THRESHOLD, needs_review
from debate_core.domain.caselist import Disclosure, Side
from debate_core.domain.landscape import PositionKind, Taxonomy
from debate_core.domain.landscape_classification import ItemKind, PositionClassification, PositionRole
from debate_core.domain.landscape_report import AffAssignment

_AFFIRMATIVE: Final = frozenset({Side.AFF, Side.PRO})

__all__ = ["AffAssignmentRun", "build_aff_assignments"]


@dataclass(frozen=True, slots=True)
class AffAssignmentRun:
    assignments: tuple[AffAssignment, ...] = field(repr=False)
    counts: AssignmentCounts
    aff_teams: int
    """Distinct teams with an affirmative round in range."""
    identified_teams: int
    """Of those, teams with a round assigned an aff or left to a placed card."""


def build_aff_assignments(
    *,
    disclosures: Sequence[Disclosure],
    through: date,
    classifications: Sequence[PositionClassification],
    plan_texts: Mapping[str, DocumentPlanText],
    taxonomy: Taxonomy,
    review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
) -> AffAssignmentRun:
    """Every affirmative round in range assigned its aff where a signal names one, with counts."""
    documents: defaultdict[str, set[str]] = defaultdict(set)
    teams: dict[str, str | None] = {}
    by_source: defaultdict[str, set[str]] = defaultdict(set)
    for disclosure in disclosures:
        if disclosure.side not in _AFFIRMATIVE or disclosure.snapshot > through:
            continue
        one = round_id(disclosure)
        documents[one].add(disclosure.source_sha256)
        teams[one] = _team(disclosure)
        by_source[disclosure.source_sha256].add(one)
    placed: defaultdict[str, set[str]] = defaultdict(set)
    for item in classifications:
        if (
            item.item_kind is not ItemKind.CARD
            or item.position_id is None
            or item.role is not PositionRole.READS
            or needs_review(item, review_threshold)
        ):
            continue
        position = taxonomy.resolve(item.position_id)
        if position.kind is PositionKind.AFF and not position.deprecated:
            for one in by_source.get(item.source_sha256, ()):
                placed[one].add(position.id)
    rounds = [
        AffRound(round_key=one, team=teams[one], documents=tuple(sorted(documents[one])))
        for one in sorted(documents)
    ]
    assigned, counts = assign_affs(
        rounds,
        plan_texts,
        {one: frozenset(found) for one, found in placed.items()},
        PlanTextVocabulary(taxonomy),
    )
    keys = {one.round_key for one in assigned} | set(placed)
    return AffAssignmentRun(
        assignments=tuple(
            AffAssignment(round_id=one.round_key, position_id=one.position_id, method=one.method)
            for one in assigned
        ),
        counts=counts,
        aff_teams=len({team for team in teams.values() if team is not None}),
        identified_teams=len({teams[one] for one in keys if teams.get(one) is not None}),
    )


def _team(disclosure: Disclosure) -> str | None:
    if disclosure.school == UNKNOWN_SCHOOL or disclosure.team_code == UNKNOWN_TEAM_CODE:
        return None
    return f"{disclosure.school.casefold()}/{disclosure.team_code.casefold()}"
