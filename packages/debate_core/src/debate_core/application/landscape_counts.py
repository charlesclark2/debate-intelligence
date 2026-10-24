"""What the landscape report counted, for the views built beside it (`v1-e32-t03`, `v1-e32-t04`).

:class:`~debate_core.application.landscape_report.LandscapeReportService` reads a caselist's
disclosures into rounds and decides which rounds read each position. The trends
(:mod:`debate_core.application.landscape_trends`) and the per-school view
(:mod:`debate_core.application.landscape_schools`) take those same decisions as :class:`CountedReads`
rather than making their own, so a round the report counts as answering a position, or an aff that
`v1-e32-t09` assigned, is the same round to all three.

## A round, and when it was first seen

A round is one team, one side, one tournament and one round, as the filename gave them (the round's
normalized form when it has one): :func:`round_id` names it by a digest of those fields, never by
the path the file was filed under. The per-team sequence number between the side and the tournament
increments as a team adds rounds, so only 60 of one week's 728 paths survive into the next
(`v1-e30-t03`); the path parser keeps that number out of the tournament, and a file carried into a
later window under a new path is the round it was. A file whose name gave no tournament or no round
is a round of its own, named by its team and its content's digest.

A round is first seen in the earliest snapshot that lists one of its files.

## What never leaves memory

A team is a casefolded school and team code, used to tell teams apart. Nothing here is written out.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Final

from debate_core.application.caselist.path_parser import UNKNOWN_SCHOOL, UNKNOWN_TEAM_CODE
from debate_core.domain.caselist import Disclosure, Side

__all__ = [
    "AFF_SIDE",
    "LANDSCAPE_SIDE",
    "NEG_SIDE",
    "CountedReads",
    "CountedRound",
    "round_id",
    "team_identity",
]

AFF_SIDE: Final = "aff"
NEG_SIDE: Final = "neg"
LANDSCAPE_SIDE: Final = {Side.AFF: AFF_SIDE, Side.PRO: AFF_SIDE, Side.NEG: NEG_SIDE, Side.CON: NEG_SIDE}
"""A disclosure's side as the landscape counts it: PF's pro and con are aff and neg."""

_ROUND_ID_DIGITS: Final = 16


def team_identity(disclosure: Disclosure) -> tuple[str, str] | None:
    """The disclosing team as a casefolded (school, team code); None when the path named neither."""
    if disclosure.school == UNKNOWN_SCHOOL or disclosure.team_code == UNKNOWN_TEAM_CODE:
        return None
    return (disclosure.school.casefold(), disclosure.team_code.casefold())


def _round_identity(disclosure: Disclosure) -> tuple[str, ...]:
    team = team_identity(disclosure)
    tournament = disclosure.tournament.casefold() if disclosure.tournament else ""
    label = disclosure.round_label
    played = (label.normalized or label.raw.casefold()) if label is not None else ""
    labelled = team is not None and bool(tournament) and bool(played)
    return (
        disclosure.caselist,
        *(team or ("", "")),
        LANDSCAPE_SIDE.get(disclosure.side, ""),
        tournament,
        played,
        "" if labelled else disclosure.source_sha256,
    )


def round_id(disclosure: Disclosure) -> str:
    """The round a disclosure belongs to, as 16 hex digits that show none of its fields.

    `v1-e32-t09` names a round by this when it assigns the round its aff.
    """
    identity = json.dumps(_round_identity(disclosure), ensure_ascii=False)
    return hashlib.sha256(identity.encode()).hexdigest()[:_ROUND_ID_DIGITS]


@dataclass(frozen=True, slots=True)
class CountedRound:
    """One round in the report's range."""

    side: str
    """`aff`, `neg`, or empty for a round on no readable side."""
    team: tuple[str, str] | None = field(repr=False)
    """The casefolded (school, team code); None for a path that named neither."""
    first_seen: date


@dataclass(frozen=True, slots=True)
class CountedReads:
    """Every round in the report's range, and the rounds the report counted as reading each position."""

    rounds: Mapping[str, CountedRound] = field(repr=False)
    """Round id to the round."""
    reads: Mapping[str, frozenset[str]] = field(repr=False)
    """Position id to the rounds reading it: READS at or above the threshold, on the round's own side
    or on no readable side, with `v1-e32-t09`'s assigned affs in place of the cards' for their rounds."""
