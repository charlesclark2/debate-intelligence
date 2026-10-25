"""The backfile marker's two refusals: a pull and a landscape never take a backfile (`v1-e34-t34`).

A backfile is a caselist named in `caselist.backfile_caselists` (data-use policy 1.17, Permitted uses
8). The weekly run never pulls one, and none is classified into positions or given a per-school view.
:class:`~debate_core.application.caselist_sync.CaselistSyncService` and
:class:`~debate_core.application.landscape_run.LandscapeRunService` each refuse one here, before they
list, fetch or read anything. Kept apart from
:mod:`~debate_core.application.caselist.backfile_import`, which imports the sync service.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from debate_core.application.errors import DomainError

__all__ = ["BackfileHasNoLandscape", "BackfileIsNotPulled", "refuse_a_landscape", "refuse_backfiles"]


class BackfileIsNotPulled(DomainError):
    """`caselist pull` was asked for a backfile caselist. Nothing was listed or fetched."""

    def __init__(self, caselists: Sequence[str]) -> None:
        self.caselists = tuple(caselists)
        super().__init__(
            f"{', '.join(self.caselists)} is a backfile (caselist.backfile_caselists): the weekly pull "
            "never takes one. Import it with `caselist backfile-import`"
        )


class BackfileHasNoLandscape(DomainError):
    """`landscape report` was asked for a backfile caselist, which is never classified (policy 1.17)."""

    def __init__(self, caselist: str) -> None:
        self.caselist = caselist
        super().__init__(
            f"{caselist} is a backfile (caselist.backfile_caselists): data-use policy 1.17 never "
            "classifies one into positions or gives it a per-school view, so it has no landscape report"
        )

def refuse_backfiles(caselists: Iterable[str | None], backfiles: Sequence[str]) -> None:
    """Raise :class:`BackfileIsNotPulled` when any of `caselists` is a backfile."""


def refuse_a_landscape(caselist: str, backfiles: Sequence[str]) -> None:
    """Raise :class:`BackfileHasNoLandscape` when `caselist` is a backfile."""
