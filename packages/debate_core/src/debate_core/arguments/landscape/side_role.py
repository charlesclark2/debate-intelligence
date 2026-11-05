"""A placement's role by the side its file was disclosed on: a card defending its own side's position reads it
(`v1-e32-t49`).

A team discloses a file on the side it read it on. A card placed under a position, in a file disclosed only on
that position's own side, is that side's card: when it sits under an answer heading, or the model says it
answers, it is defending the position against the other side's answers to it (a negative's card answering the
affirmative's no-link or permutation, under `AT: No Link` in the disadvantage's own file), so it **reads** the
position. :func:`side_role` gives it READS whatever its heading or the model's stance says.

Only that half is decided here. A placement in a file disclosed only on the other side is left as it is: the
landscape report counts such a round apart, per round, as the other side's (`other_side_position_rounds`),
and the evaluation scores it as answering
(:func:`~debate_core.arguments.landscape.evaluation_breakdown.scored_stance`, `v1-e32-t46`), so both read
their half from the file's side on top of this one. A file disclosed on both sides
or on no readable side, and a position either side reads, keep the role they have.

Not in the matcher: stage one's results are cached by a card's fingerprint (its headings and tag), which cards
in files on different sides share, and the model is asked once per fingerprint. The rule is applied where a
result meets its own card's file:
:meth:`~debate_core.application.position_classification.PositionClassificationService.classify`.

Pure: values in, values out.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Final

from debate_core.domain.landscape import PositionSide, Taxonomy
from debate_core.domain.landscape_classification import RATIONALE_LIMIT, ClassificationResult, PositionRole

__all__ = [
    "OPPOSITE_SIDES",
    "OWN_SIDE_NOTE",
    "READABLE_SIDES",
    "on_own_side",
    "readable_sides",
    "side_role",
]

READABLE_SIDES: Final = {
    "AFF": PositionSide.AFF,
    "PRO": PositionSide.AFF,
    "NEG": PositionSide.NEG,
    "CON": PositionSide.NEG,
}
"""A disclosed file's side as a position's side: PF's pro and con count as aff and neg, as the report counts
them; `UNKNOWN` is no readable side."""

OPPOSITE_SIDES: Final = {PositionSide.AFF: PositionSide.NEG, PositionSide.NEG: PositionSide.AFF}

OWN_SIDE_NOTE: Final = "; its file was disclosed only on the position's own side, so it reads it"
"""What a rationale gains when :func:`on_own_side` changes its role to READS."""


def readable_sides(file_sides: Collection[str]) -> frozenset[PositionSide]:
    """The positions' sides of a file's disclosures (:class:`~debate_core.domain.caselist.Side` values)."""
    return frozenset(READABLE_SIDES[side] for side in file_sides if side in READABLE_SIDES)


def side_role(
    taxonomy: Taxonomy, position_id: str, role: PositionRole | None, file_sides: Collection[str]
) -> PositionRole | None:
    """`role` for a placement of `position_id` in a file disclosed on `file_sides`: READS when every readable
    side is the position's own, the role it has otherwise."""
    side = taxonomy.resolve(position_id).side
    if readable_sides(file_sides) == frozenset({side}):
        return PositionRole.READS
    return role


def on_own_side(
    taxonomy: Taxonomy, result: ClassificationResult, file_sides: Collection[str]
) -> ClassificationResult:
    """`result` for a card in a file disclosed on `file_sides`, its role by :func:`side_role`.

    A result whose role changes says so at the end of its rationale (:data:`OWN_SIDE_NOTE`), kept within the
    rationale limit; any other result is returned as it is.
    """
    if result.position_id is None:
        return result
    role = side_role(taxonomy, result.position_id, result.role, file_sides)
    if role is result.role:
        return result
    rationale = result.rationale[: RATIONALE_LIMIT - len(OWN_SIDE_NOTE)] + OWN_SIDE_NOTE
    return result.model_copy(update={"role": role, "rationale": rationale})
