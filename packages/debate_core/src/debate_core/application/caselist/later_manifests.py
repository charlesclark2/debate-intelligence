"""After a weekly is imported, measure the manifests dated after it again (`v1-e30-t18`).

Interface only; the measuring follows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.withdrawals import WithdrawalCount
from debate_core.application.ports.caselist import CaselistRepository
from debate_core.application.ports.suppression import SuppressionList

__all__ = ["CompleteArchiveRecount", "LaterManifests", "LaterManifestsRemeasured"]


@dataclass(frozen=True, slots=True)
class CompleteArchiveRecount:
    """The newest complete archive's withdrawals, counted again after an earlier-dated weekly."""

    caselist: str
    snapshot: str
    """`full/<date>`."""

    before: WithdrawalCount
    after: WithdrawalCount


@dataclass(frozen=True, slots=True)
class LaterManifestsRemeasured:
    """What measuring the later manifests again rewrote."""

    caselist: str
    weeklies: tuple[str, ...] = ()
    complete_archive: CompleteArchiveRecount | None = None

    @property
    def rewritten(self) -> tuple[str, ...]:
        """Every snapshot whose manifest was rewritten: the weeklies in date order, then `full/<date>`."""
        full = (self.complete_archive.snapshot,) if self.complete_archive is not None else ()
        return (*self.weeklies, *full)


class LaterManifests:
    """Measures again the manifests a weekly imported out of date order leaves stale."""

    def __init__(
        self, *, caselists: CaselistRepository, local: LocalEvidence, suppression: SuppressionList
    ) -> None:
        self._caselists = caselists
        self._local = local
        self._suppression = suppression

    async def after_weekly_import(self, caselist: str, snapshot: date) -> LaterManifestsRemeasured:
        return LaterManifestsRemeasured(caselist=caselist)
