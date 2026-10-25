"""Where a landscape bundle goes, and the files it holds: named once, for the report, its run and a removal.

`v1-e32-t03` and `v1-e32-t04` defined these in :mod:`~debate_core.application.landscape_run` and
:mod:`~debate_core.application.landscape_report`, which still export them under the same names.
`v1-e32-t13` moved the one definition of each here, unchanged, because a removal and `caselist
status` need them too (:mod:`~debate_core.application.caselist.removal_school_views`), and importing
the report from the caselist package closes a cycle through `caselist_sync` back to `caselist status`.
This module imports nothing of the platform, so anything may import it.
"""

from __future__ import annotations

from typing import Final

__all__ = ["CIRCUIT_WIDE_FILES", "REPORTS_PREFIX", "SCHOOL_VIEW_FILES"]

REPORTS_PREFIX: Final = "reports/landscape"
"""Where a landscape bundle goes in the bucket, and under the data directory."""

CIRCUIT_WIDE_FILES: Final = ("report.md", "positions.csv", "top_cards.csv", "impact_cards.csv", "trends.csv")
"""The bundle's files that name no school, team or debater: the circuit-wide report and its trends."""

SCHOOL_VIEW_FILES: Final = ("schools.csv", "schools.md")
"""The bundle's per-school view (`v1-e32-t04`): school and team code as disclosed, never more."""
