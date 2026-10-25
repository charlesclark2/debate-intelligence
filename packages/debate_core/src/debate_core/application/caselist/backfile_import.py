"""One earlier season's complete archive, imported, parsed and published as a backfile (`v1-e34-t34`).

Data-use policy 1.17 keeps earlier seasons' disclosures, from 2021-22 on, as **backfiles**: a
reservoir of evidence for research and team files, never classified into positions or given a
per-school view (Permitted uses 8). A backfile is a caselist named in `caselist.backfile_caselists`
(:meth:`~debate_core.application.settings.CaselistSettings.is_backfile`). That one setting is what
`caselist pull` and the weekly run refuse, what `landscape report` refuses, and what the annual purge
keeps. Removal, the suppression list and path holds need no marker: they act on every manifest, a
backfile's `full/<date>` one included.

`debate-research caselist backfile-import --caselist <slug>` is a dry run; `--execute` imports. The
PM's rulings of 2026-10-25 set what follows.

## What it refuses, before anything is fetched

* a caselist that is not a backfile, or is of a season before 2021-22;
* an environment not in bucket mode, or a bucket that is not seeded: the ledger and the lock are the
  bucket's, so any machine that runs the command, the Mac or a cloud task, reads the same ones;
* **the no-import window**, Tuesday 06:00 to Thursday 00:00 America/Chicago
  (:func:`in_no_import_window`). It covers the 24 hours the weekly run's ledger counts back from
  Wednesday 06:00, the Wednesday 03:00 login, the run itself, and any count by date the site keeps.
  The command refuses to start inside it, and each locked step asks again;
* **the backfile budget**: one complete archive in any rolling 24 hours, counted in its own ledger in
  the bucket (:data:`BACKFILE_LEDGER_KEY`), beside the run's state files and never one of them. The
  weekly run's ledger is never read or written, so its five a day are its own;
* a caselist that lists no complete archive (PF keeps weeklies only; policy 1.17 imports complete
  archives);
* **too little free space**: the estimate for this caselist, its archive in the inbox, its blobs and
  its parsed store (:func:`space_needed`), with 25% headroom, against the data directory's volume.

## The steps, and the lock

The bucket's run lock is the one the weekly run takes, held per step and never through the download
or the parse (the PM's ruling Q5):

1. **Locked**: restore the working copy (the run-state bundle, the state files, the parsed store of
   this caselist), note the bundle's version, check the budget, and record the download's start in
   the backfile ledger before the download, as a pull records its own.
2. **Not locked**: download the complete archive with `v1-e34-t04`'s downloader, import it into its
   `full/<date>` namespace with `v1-e34-t04`'s importer, and parse it.
3. **Locked**: publish the sources and the manifest, then save the run-state bundle, which then holds
   the backfile's manifest. Refused if the bucket's bundle changed since step 1: a removal in between
   rewrote it, and saving this copy over it would bring back what the removal took out.
4. **Locked**: publish the parsed store.

Nothing here touches the search index: backfiles stay out of the student search pilot's index until
`v1-e39-t18` decides. Nothing here classifies or builds a landscape.

**Counts only.** No path, school, team code or file name leaves this module.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Final
from zoneinfo import ZoneInfo

from debate_core.application.errors import DomainError

__all__ = [
    "BACKFILE_DOWNLOADS_PER_DAY",
    "BACKFILE_LEDGER_FILENAME",
    "BACKFILE_LEDGER_KEY",
    "FREE_SPACE_HEADROOM",
    "IMPORT_COMMAND",
    "NO_IMPORT_WINDOW_ZONE",
    "PARSED_STORE_RATIO",
    "BackfileImportRefused",
    "BackfilePlan",
    "BackfileReport",
    "BundleChangedSinceRestore",
    "Refusal",
    "SpaceNeeded",
    "in_no_import_window",
    "no_import_window_ends",
    "space_needed",
]

IMPORT_COMMAND: Final = "caselist backfile-import"

BACKFILE_DOWNLOADS_PER_DAY: Final = 1
"""Complete archives a backfile import may download in any rolling 24 hours (the PM's ruling Q1)."""

BACKFILE_LEDGER_FILENAME: Final = "caselist-backfile-download-starts.json"
BACKFILE_LEDGER_KEY: Final = f"reports/sync/state/{BACKFILE_LEDGER_FILENAME}"
"""Beside the run's state files, and not one of them: a weekly run neither restores nor saves it."""

NO_IMPORT_WINDOW_ZONE: Final = ZoneInfo("America/Chicago")

PARSED_STORE_RATIO: Final = 4.0
"""Parsed-store bytes per source byte: 3.96 for LD and 3.88 for Policy, measured on the dev store on
2026-10-25 (`docs/session-reports/v1-e34-t34-backfile-seasons-import.md`), rounded up."""

FREE_SPACE_HEADROOM: Final = 1.25


class BackfileImportRefused(DomainError):
    """A backfile import refused to start, or to take the lock for a step. Nothing more was done."""

    def __init__(self, refusals: Sequence[Refusal]) -> None:
        self.refusals = tuple(refusals)
        self.codes = tuple(one.code for one in self.refusals)
        super().__init__("; ".join(f"{one.code}: {one.message}" for one in self.refusals))


class BundleChangedSinceRestore(DomainError):
    """The bucket's run-state bundle changed between this import's restore and its publish."""

    def __init__(self) -> None:
        super().__init__(
            "the run-state bundle in the bucket changed since this import restored it, most likely a "
            "removal; nothing was published. Run the import again: it restores the new bundle first"
        )


@dataclass(frozen=True, slots=True)
class Refusal:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class SpaceNeeded:
    """What one import needs on the data directory's volume, and what it has. Bytes."""

    archive_bytes: int
    estimate_bytes: int
    """The archive in the inbox (unless it is there already), its blobs and its parsed store."""
    required_bytes: int
    """The estimate with :data:`FREE_SPACE_HEADROOM`."""
    free_bytes: int

    @property
    def enough(self) -> bool:
        return self.free_bytes >= self.required_bytes


def space_needed(archive_bytes: int, *, free_bytes: int, in_inbox: bool = False) -> SpaceNeeded:
    """The free-space precheck's two numbers for an archive of `archive_bytes` (the PM's ruling Q4)."""
    raise NotImplementedError


def in_no_import_window(now: datetime) -> bool:
    """Whether `now` is inside Tuesday 06:00 to Thursday 00:00, America/Chicago."""
    return False


def no_import_window_ends(now: datetime) -> datetime:
    """When the window `now` is inside closes: the Thursday 00:00 after it, America/Chicago."""
    raise NotImplementedError


@dataclass(frozen=True, slots=True)
class BackfilePlan:
    """What an import of one caselist would do, and every reason it would not. Counts only."""

    caselist: str
    season: str
    archive_date: date | None
    archive_bytes: int | None
    in_inbox: bool
    already_imported: bool
    downloads_left: int
    inside_window: bool
    window_ends: datetime | None
    space: SpaceNeeded | None
    refusals: tuple[Refusal, ...]

    @property
    def refused(self) -> bool:
        return bool(self.refusals)


@dataclass(slots=True)
class BackfileReport:
    """What one import did, step by step. Counts only."""

    plan: BackfilePlan
    downloaded_bytes: int = 0
    members: int = 0
    stored: int = 0
    suppressed: int = 0
    held_by_request: dict[str, int] = field(default_factory=dict[str, int])
    sources_uploaded: int = 0
    sources_skipped: int = 0
    bundle: str | None = None
    parsed: int = 0
    unsupported: int = 0
    failed: int = 0
    cards: int = 0
    parsed_uploaded: int = 0
    archive_left_inbox: bool = False
    steps: dict[str, float] = field(default_factory=dict[str, float])

    @property
    def succeeded(self) -> bool:
        return False


class BackfileImportService:
    """Imports one backfile caselist's complete archive. See the module docstring."""

    def __init__(self, **dependencies: object) -> None:
        self._dependencies = dependencies

    async def plan(self, caselist: str) -> BackfilePlan:
        """The dry run: listings and a `HEAD`, the ledger read, the volume read; nothing written."""
        return BackfilePlan(
            caselist=caselist,
            season="",
            archive_date=None,
            archive_bytes=None,
            in_inbox=False,
            already_imported=False,
            downloads_left=BACKFILE_DOWNLOADS_PER_DAY,
            inside_window=False,
            window_ends=None,
            space=None,
            refusals=(),
        )

    async def run(self, caselist: str) -> BackfileReport:
        """The import. Raises :class:`BackfileImportRefused` for what the plan refuses."""
        return BackfileReport(plan=await self.plan(caselist))


_ = (Callable, Path, timedelta)
