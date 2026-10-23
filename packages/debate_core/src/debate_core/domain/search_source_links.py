"""Where a card on the search pilot's card page came from, as a link out of the platform (`v1-e39-t11`).

The card page offers "Open on openCaselist" for a disclosed card, built only from what the index
already stores of the card's representative occurrence: its caselist, school and team code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from debate_core.domain.evidence_search import OccurrenceProvenance

__all__ = ["OPENCASELIST_ORIGIN", "SourceLink", "source_link"]

OPENCASELIST_ORIGIN: Final = "https://opencaselist.com"
"""The site a disclosed card's team page is on. A fixed origin: no part of a link is ever the request's."""


@dataclass(frozen=True, slots=True)
class SourceLink:
    """A link out to where a card was published: the words to show, and the address."""

    label: str
    url: str


def source_link(occurrence: OccurrenceProvenance) -> SourceLink | None:
    """The link to the page that publishes `occurrence`'s file, or `None` when none can be built."""
    return None
