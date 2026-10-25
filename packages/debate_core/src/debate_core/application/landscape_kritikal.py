"""The kritikal affirmatives, for report.md (`v1-e32-t17`, the PM's rulings of 2026-10-25).

A pure count over what the landscape report already decided and what the run read
(:class:`~debate_core.arguments.landscape.kritikal_aff.KritikalAffInputs`):

* **A K-aff round** is one `v1-e32-t09`'s assignment names the topic's K aff, by a marker in the round's
  own file (`KRITIKAL_AFF_MARKER`) or carried from the team's other rounds (`KRITIKAL_AFF_CARRY`). The
  assignment is the only source; nothing here identifies a round.
* **Refused by the advantage guard** are the affirmative rounds the K aff was not carried into because
  their own file reads an advantage, as the assignment reported them. They stay unidentified.
* **The K families** are counted in the headings of the K-aff rounds' files only: per family, the files
  naming it and the distinct teams of the K-aff rounds disclosing them. A count of words, never a
  placement, and nothing from a tag. Ordered by files, then teams, then the config's order.
* **The control** is the files holding a K-aff marker in affirmative rounds another method identifies
  (a plan text, a team's carry, a placed card), with those rounds: how often a marker sits where an aff
  is already known. Negative rounds are never counted.

Teams are opaque here: only their number leaves this module.
"""

from __future__ import annotations

from collections.abc import Mapping, Set

from debate_core.application.landscape_counts import AFF_SIDE, CountedReads
from debate_core.arguments.landscape.aff_assignment import (
    KRITIKAL_AFF_CARRY_METHOD,
    KRITIKAL_AFF_MARKER_METHOD,
)
from debate_core.arguments.landscape.kritikal_aff import KritikalAffInputs
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_report import KritikalAffs, KritikalFamilyCount

__all__ = ["kritikal_affs"]


def kritikal_affs(
    *,
    inputs: KritikalAffInputs,
    taxonomy: Taxonomy,
    counted: CountedReads,
    by_source: Mapping[str, Set[str]],
    assigned: Mapping[str, tuple[str, str]],
    placed_card_rounds: Set[str],
) -> KritikalAffs:
    """The K-aff group: its rounds by method, the advantage guard's refusals, the families and the control.

    `by_source` is each source digest's rounds in range, `assigned` round id to its assigned aff
    (resolved) and method, and `placed_card_rounds` the affirmative rounds only a placed card identifies.
    """
    position = taxonomy.resolve(inputs.position_id)
    rounds = counted.rounds
    affirmative = {one for one, found in rounds.items() if found.side == AFF_SIDE}
    methods = {
        one: method
        for one, (position_id, method) in assigned.items()
        if position_id == position.id and method in (KRITIKAL_AFF_MARKER_METHOD, KRITIKAL_AFF_CARRY_METHOD)
    }
    kritikal = set(methods)

    def teams(of: Set[str]) -> set[tuple[str, str]]:
        return {team for one in of if (team := rounds[one].team) is not None}

    files = {sha: set(found) & kritikal for sha, found in by_source.items() if set(found) & kritikal}
    order = {family: index for index, family in enumerate(inputs.families)}
    families: list[KritikalFamilyCount] = []
    for family, label in inputs.families.items():
        naming = [sha for sha in files if family in inputs.heading_families.get(sha, ())]
        if naming:
            families.append(
                KritikalFamilyCount(
                    family_id=family,
                    label=label,
                    files=len(naming),
                    teams=len(teams({one for sha in naming for one in files[sha]})),
                )
            )
    families.sort(key=lambda one: (-one.files, -one.teams, order[one.family_id]))
    otherwise = {
        one for one in affirmative if one in placed_card_rounds or (one in assigned and one not in kritikal)
    }
    control = {
        sha: set(by_source.get(sha, ())) & otherwise
        for sha in inputs.marker_sources
        if set(by_source.get(sha, ())) & otherwise
    }
    unidentified = affirmative - set(assigned) - set(placed_card_rounds)
    return KritikalAffs(
        position_id=position.id,
        label=position.label,
        rounds=len(kritikal),
        teams=len(teams(kritikal)),
        by_marker=sum(1 for method in methods.values() if method == KRITIKAL_AFF_MARKER_METHOD),
        by_carry=sum(1 for method in methods.values() if method == KRITIKAL_AFF_CARRY_METHOD),
        refused_by_advantage=len(inputs.refused_by_advantage & unidentified),
        families=tuple(families),
        control_files=len(control),
        control_rounds=len({one for found in control.values() for one in found}),
    )
