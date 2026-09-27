"""The stale-data banner for argument-landscape reports (`v1-e34-t03-sync-monitoring` ac3, ac6).

A landscape report tells debaters what the field is running. Built from a caselist the sync has
stopped refreshing, it tells them what the field *was* running, and nothing on the page says so.
This module decides whether a report is stale and supplies the two things a stale report carries:

* a **banner** that starts the Markdown report, naming the newest snapshot's date;
* **`stale=true`** in the CSV metadata header block.

The report itself — its sections, its tables, its header block — is `v1-e32-t03`'s, and the command
that writes it is `v1-e32-t05`'s; neither exists yet. This is the hook they call: they ask
:class:`LandscapeStalenessCheck` about the caselist and the report date, pass the Markdown through
:func:`with_stale_banner`, and merge :meth:`LandscapeStaleness.csv_metadata` into their header
block. Nothing else about a report changes (the task spec forbids it).

## When a report is stale

Either of two things, per caselist:

1. **The newest snapshot is too old.** More than `caselist.stale_after_days` (8 by default) older
   than the report date. The sync is weekly, so a current store is at most seven days behind, and
   a day of grace covers a run that went late. Nine days old is stale; seven is not; eight is not.
   A caselist with no snapshot at all is stale.

2. **The last run was held back by the daily download cap.** A run that the 5-per-day bulk cap cut
   short reports success and leaves the newest snapshot where it was. That snapshot can still be
   under eight days old — but the cap defers the *newest* archives of a caselist (oldest are
   fetched first), and nothing newer than the newest held snapshot is ever wanted, so every
   deferred archive is a week the site has published and the report does not contain. A cap-bound
   run is therefore **not current**, whatever the snapshot's age (ac6). It is decided from the run
   log: the latest run that listed this caselist, and how many of its archives it deferred. A later
   run that fetched them clears it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Final

from debate_core.application.caselist.publish_plan import manifest_prefix, snapshot_of_manifest_key
from debate_core.application.ports.evidence_store import EvidenceObjectStore
from debate_core.application.sync_runs import SyncRunLog

__all__ = [
    "DEFAULT_STALE_AFTER_DAYS",
    "STALE_BANNER_HEADING",
    "LandscapeStaleness",
    "LandscapeStalenessCheck",
    "assess_staleness",
    "with_stale_banner",
    "with_staleness_metadata",
]

DEFAULT_STALE_AFTER_DAYS: Final = 8
"""One weekly archive, plus a day of grace. `caselist.stale_after_days` overrides it."""

STALE_BANNER_HEADING: Final = "> **Stale data.**"
"""How the banner starts, so a reader — or a test — can find it as the report's first line."""


@dataclass(frozen=True, slots=True)
class LandscapeStaleness:
    """Whether one caselist's landscape report, dated `report_date`, is built on stale data."""

    caselist: str
    report_date: date
    newest_snapshot: date | None
    stale_after_days: int = DEFAULT_STALE_AFTER_DAYS
    archives_awaiting_download: int = 0
    """Deferred by the daily cap at the latest run that listed this caselist."""

    @property
    def age_days(self) -> int | None:
        """Days between the newest snapshot and the report, or `None` when there is no snapshot."""
        if self.newest_snapshot is None:
            return None
        return (self.report_date - self.newest_snapshot).days

    @property
    def too_old(self) -> bool:
        age = self.age_days
        return age is None or age > self.stale_after_days

    @property
    def cap_bound(self) -> bool:
        return self.archives_awaiting_download > 0

    @property
    def stale(self) -> bool:
        return self.too_old or self.cap_bound

    def banner(self) -> str | None:
        """The Markdown banner for a stale report, or `None` for a current one."""
        if not self.stale:
            return None
        if self.newest_snapshot is None:
            said = (
                f"No snapshot of {self.caselist} has been imported, so this report reflects no disclosures."
            )
        else:
            said = (
                f"The newest snapshot of {self.caselist} is from {self.newest_snapshot.isoformat()}, "
                f"{self.age_days} day(s) before this report ({self.report_date.isoformat()})."
            )
        if self.cap_bound:
            said += (
                f" {self.archives_awaiting_download} newer weekly archive(s) are published but not yet "
                "downloaded (the daily download limit held them back)."
            )
        return (
            f"{STALE_BANNER_HEADING} {said} Rounds disclosed since then are missing; check the "
            "caselist before prepping against this landscape."
        )

    def csv_metadata(self) -> dict[str, str]:
        """What the CSV header block carries: `stale`, and the facts it was decided on."""
        return {
            "stale": "true" if self.stale else "false",
            "newest_snapshot": self.newest_snapshot.isoformat() if self.newest_snapshot else "",
            "snapshot_age_days": str(self.age_days) if self.age_days is not None else "",
            "archives_awaiting_download": str(self.archives_awaiting_download),
        }


def assess_staleness(
    caselist: str,
    *,
    report_date: date,
    newest_snapshot: date | None,
    archives_awaiting_download: int = 0,
    stale_after_days: int = DEFAULT_STALE_AFTER_DAYS,
) -> LandscapeStaleness:
    """The pure decision, for a caller that already knows the newest snapshot."""
    return LandscapeStaleness(
        caselist=caselist,
        report_date=report_date,
        newest_snapshot=newest_snapshot,
        stale_after_days=stale_after_days,
        archives_awaiting_download=archives_awaiting_download,
    )


def with_stale_banner(markdown: str, staleness: LandscapeStaleness) -> str:
    """`markdown` with the banner as its first lines when stale; unchanged when current."""
    banner = staleness.banner()
    if banner is None:
        return markdown
    return f"{banner}\n\n{markdown}"


def with_staleness_metadata(metadata: Mapping[str, str], staleness: LandscapeStaleness) -> dict[str, str]:
    """A report's CSV header metadata with the staleness fields merged in."""
    return {**metadata, **staleness.csv_metadata()}


class LandscapeStalenessCheck:
    """Reads the newest snapshot from the manifests and the backlog from the run log.

    Args:
        objects: The local evidence object store, where `manifests/<caselist>/<date>.jsonl` live.
        run_log: The sync run log, or `None` where no sync runs (then only snapshot age counts).
        stale_after_days: `caselist.stale_after_days`.
    """

    def __init__(
        self,
        *,
        objects: EvidenceObjectStore,
        run_log: SyncRunLog | None,
        stale_after_days: int = DEFAULT_STALE_AFTER_DAYS,
    ) -> None:
        self._objects = objects
        self._run_log = run_log
        self._stale_after_days = stale_after_days

    async def check(self, caselist: str, *, report_date: date) -> LandscapeStaleness:
        return assess_staleness(
            caselist,
            report_date=report_date,
            newest_snapshot=await self.newest_snapshot(caselist),
            archives_awaiting_download=self._awaiting(caselist),
            stale_after_days=self._stale_after_days,
        )

    async def newest_snapshot(self, caselist: str) -> date | None:
        """The latest snapshot date with a manifest, read from key names alone."""
        dates: list[date] = []
        for info in await self._objects.list_objects(manifest_prefix(caselist)):
            named = snapshot_of_manifest_key(caselist, info.key)
            if named is None:
                continue
            try:
                dates.append(date.fromisoformat(named))
            except ValueError:
                continue
        return max(dates) if dates else None

    def _awaiting(self, caselist: str) -> int:
        if self._run_log is None:
            return 0
        latest = self._run_log.latest_listing(caselist)
        return latest.deferred_by_caselist.get(caselist, 0) if latest is not None else 0
