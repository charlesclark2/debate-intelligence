"""The debate season a date falls in: 1 August to 31 July.

Moved here from `debate_cli.commands.caselist_backfile` (`v1-e39-t28`), which still reads it
unchanged, so that the search pilot's camp link (:mod:`debate_core.domain.search_source_links`) and
the backfile survey count seasons by the same rule.
"""

from __future__ import annotations

from datetime import date
from typing import Final

__all__ = ["SEASON_STARTS_IN_MONTH", "current_season_start"]

SEASON_STARTS_IN_MONTH: Final = 8
"""A season runs 1 August to 31 July (docs/policies/caselist-data-use.md, Retention)."""


def current_season_start(today: date) -> int:
    """The year the season `today` falls in started: 2026 from 1 August 2026 to 31 July 2027."""
    return today.year if today.month >= SEASON_STARTS_IN_MONTH else today.year - 1
