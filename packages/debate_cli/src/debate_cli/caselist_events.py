"""Which event a caselist slug debates, for the commands that import, pull, backfile and index it.

It lived in :mod:`debate_cli.commands.caselist` until v1-e01-t32, and `caselist pull`,
`caselist backfile-import` and `tub index build` imported that command's module to reach it.
"""

from __future__ import annotations

from typing import Final

from debate_core.domain.caselist import Event

__all__ = ["EVENTS_BY_SLUG_PREFIX", "event_for_caselist"]

EVENTS_BY_SLUG_PREFIX: Final[dict[str, Event]] = {
    "hsld": Event.LD,
    "hspolicy": Event.POLICY,
    "hspf": Event.PF,
    "ndtceda": Event.POLICY,
    "nfald": Event.LD,
    # The synthetic caselist the test archives are built under (`tests/fixtures/caselist/`).
    # Named here rather than special-cased in a test so that the smoke check runs the same code
    # path an operator runs.
    "testcl": Event.LD,
}
"""Which event each published caselist slug debates, by the letters before its season year.

A table rather than a rule, because a slug is data (`CaselistSlug` is a validated string, not an
enum) and next season's slugs are rows somebody adds here. A slug that is not in it is a refusal
naming `--event`, never a guess: guessing wrong would file every disclosure in the archive under
a side the event does not debate.
"""


def event_for_caselist(caselist: str) -> Event | None:
    """The event a caselist slug implies, or `None` when this build does not know the slug."""
    prefix = caselist.rstrip("0123456789")
    return EVENTS_BY_SLUG_PREFIX.get(prefix)
