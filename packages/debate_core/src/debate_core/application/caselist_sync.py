"""The weekly caselist pull: list, download, import, publish, and only then the optional stages.

`debate-research caselist pull` is a thin command over :class:`CaselistSyncService`. The service
composes the pieces other tasks built — the OpenCaselist source (`v1-e34-t01`), the archive
importer (`v1-e30-t03`), the OpenEv importer (`v1-e30-t04`), the publisher (`v1-e30-t05`) and the
status check — and the design is entirely about what happens when one of them is missing, slow or
refused.

## Weekly, and that is a policy, not a preference

`docs/policies/caselist-data-use.md` E34 gate 4 permits "weekly cadence at most, no polling faster
than archives are published", agreed with the OpenCaselist maintainer, whose confirmation (clause
12) is scoped to the weekly archives. ADR-0017 records that the daily cadence a superseded decision
record proposed contradicted that policy and was therefore wrong. Nothing in this module polls, and
the schedule it is run on is weekly (`ops/launchd/`).

## Capture first

Three stages are irreversible and therefore mandatory: **download**, **import** and **publish**.
They put the bytes somewhere durable — the inbox, the local evidence store, the bucket — and every
later stage is a derivation that can be recomputed from them. **Parse** (`v1-e31-t06`) and
**landscape** (`v1-e32-t05`) are therefore optional: each runs when its service was wired in and is
otherwise *skipped with a recorded reason*. Neither exists yet, so the skip is the normal path, not
an edge case, and neither a missing stage nor a failing one can fail a run whose bytes are already
safe.

The order is download, import, publish, parse, landscape, report. Goal criterion ac1 lists parsing
before publishing; the spec's own description ("the run still completes download, import and
publish before anything optional") is what is implemented, and the session report records the
difference.

## The daily download budget

OpenCaselist limits each user to **5 bulk downloads per day** (`weeklyLimiter` upstream, found by
`v1-e34-t01`), separately from the 10-file-per-minute limit the transport paces itself against.
That ceiling is budgeted in :meth:`CaselistSyncService.plan` across the configured caselists —
decided before anything is fetched rather than discovered when the server says no — and what a run
spends is recorded in a per-day ledger, so a second run on the same day starts from what is left
rather than from five.

If the server refuses anyway, a :class:`~debate_core.application.errors.ProviderRateLimited`
carrying a wait longer than :data:`SKIP_TODAY_SECONDS` means *skip today*: the remaining archives
are recorded as deferred, the run goes on to import and publish what it already has, and it exits
successfully. Under ADR-0017 the weekly back-catalogue makes a late download equivalent to a timely
one, so a deferred archive is a delay and not a loss.

## What is downloaded, and what is not

The downloads listing carries two archive kinds per caselist
(:class:`~debate_core.application.ports.caselist_source.ArchiveKind`):

* `WEEKLY` — `<slug>-weekly-<date>.zip`, the week's edits. **This is what a weekly sync pulls**,
  and only those dated after the latest snapshot the local manifests already hold.
* `FULL` — `<slug>-all-<date>.zip`, the whole caselist, regenerated rather than retained. A weekly
  run **does not** fetch it. Whether the run should also refresh the full archive periodically, and
  at what interval against a 5-per-day cap, is a question this task raises rather than settles; the
  session report's Deviations section carries it. The one-off back-catalogue fetch of the older
  weeklies is `v1-e30-t06`'s.
* `UNRECOGNISED` — a listed name following neither pattern, which the client refuses to date by
  guesswork. It is **never downloaded**: an archive with no date cannot be filed as a snapshot, and
  the importer's ordering rule is built on snapshot dates. It is counted and named in the run
  summary so that a new naming scheme upstream shows up as a number an operator can see rather than
  as a silently empty run.

## The inbox

Downloads land in one directory, which is what the importer reads. Two rules come from the
`v1-e34-t01` review:

* `<inbox>/.partial/` is skipped. It holds downloads in progress
  (:data:`~debate_core.integrations.opencaselist.inbox_writer.PARTIAL_DIRECTORY`), and a partial
  file is not an archive.
* **An archive whose name is already in the inbox is not downloaded again.** The client reports an
  identical file as `already_present`, but it streams the whole thing first, and every archive
  fetched spends one of the day's five.

## Credentials, and stages that come back later

The local stages need no AWS session. If the operator's SSO session has expired, the S3 adapter
raises :class:`~debate_core.application.errors.StoreCredentialsExpired`; the publish and report
stages are then recorded as **pending** in a small local file, and the next run — or
`caselist pull --publish-pending` — completes them. Nothing that was captured is lost by a login
that timed out overnight.

## One run at a time

A run holds an exclusive lock on `<state_dir>/caselist-sync.lock` for its whole duration. A second
run exits immediately with :class:`SyncRunInProgress` rather than interleaving two imports of the
same caselist.

## What is logged and summarised

Counts, caselist slugs, snapshot dates, archive names and digests. Never the caselist_token, never
a school, a team code, a debater's initials, a disclosure path or a camp file's title
(`docs/policies/caselist-data-use.md` rule 4). The per-run JSON summary obeys the same rule: it is
written for an operator and for `v1-e34-t03`'s run log, and it carries no personal data at all.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from types import TracebackType
from typing import Final, Protocol, Self, cast

from debate_core.application.caselist.evidence_listing import LocalEvidence, read_local_snapshots
from debate_core.application.caselist.import_service import CaselistImportService, ImportReport
from debate_core.application.caselist.manifest import (
    manifest_key,
    read_manifest_lines,
    write_manifest,
    write_manifest_lines,
)
from debate_core.application.caselist.openev_import_service import (
    OpenEvImportReport,
    OpenEvImportService,
)
from debate_core.application.caselist.openev_manifest import openev_manifest_key
from debate_core.application.caselist.pipeline import Classification
from debate_core.application.caselist.publish_service import (
    CaselistPublishService,
    NothingToPublish,
    SourceResult,
)
from debate_core.application.caselist.status_service import CaselistStatusService, NoCaselistEvidence
from debate_core.application.errors import (
    DomainError,
    ProviderRateLimited,
    StoreAccessDenied,
    StoreCredentialsExpired,
)
from debate_core.application.ports.archive import ArchiveEntry, ArchiveMember
from debate_core.application.ports.caselist_source import (
    ArchiveKind,
    ArchiveListing,
    CaselistArchiveSource,
    DownloadedFile,
    OpenEvFile,
    openev_inbox_name,
)
from debate_core.domain.caselist import Acquisition, Event

__all__ = [
    "DEFAULT_BULK_DOWNLOADS_PER_DAY",
    "INBOX_PARTIAL_DIRECTORY",
    "LOCK_FILENAME",
    "PENDING_WORK_FILENAME",
    "SKIP_TODAY_SECONDS",
    "ArchiveReader",
    "ArchiveSelection",
    "CaselistParseStage",
    "CaselistSyncService",
    "DownloadLedger",
    "LandscapeStage",
    "LandscapeStageResult",
    "NoCaselistsConfigured",
    "OpenEvSelection",
    "ParseStageResult",
    "PendingWork",
    "RunSummary",
    "SelectionDecision",
    "StageOutcome",
    "StageRecord",
    "SyncPlan",
    "SyncRunInProgress",
    "SyncStage",
    "UndatedArchive",
    "UnknownSyncEvent",
    "within_daily_budget",
]

logger = logging.getLogger(__name__)

DEFAULT_BULK_DOWNLOADS_PER_DAY: Final = 5
"""OpenCaselist's own ceiling on bulk archive downloads per user per day (`weeklyLimiter`)."""

SKIP_TODAY_SECONDS: Final = 3600.0
"""A `Retry-After` at or above this is the daily limiter, not a burst: stop fetching, run on.

An hour rather than a day, because the transport already sleeps through anything shorter than
`caselist.max_retry_wait_seconds` (300 s by default) and reports the rest. Any wait this long means
no further archive is coming today, whatever number the server chose to state.
"""

INBOX_PARTIAL_DIRECTORY: Final = ".partial"
"""Downloads in progress, written by the client. Never read as an archive (v1-e34-t01 review)."""

LOCK_FILENAME: Final = "caselist-sync.lock"
PENDING_WORK_FILENAME: Final = "caselist-sync-pending.json"
DOWNLOAD_LEDGER_FILENAME: Final = "caselist-sync-downloads.json"
RUN_SUMMARY_DIRECTORY: Final = "caselist-sync-runs"

OPENEV_PUBLISH_TARGET: Final = "openev"
"""What `caselist publish --caselist` takes for camp files (`publish_plan.validate_publish_target`)."""


# ------------------------------------------------------------------------------------------------
# What the run is made of
# ------------------------------------------------------------------------------------------------


class SyncStage(StrEnum):
    """The stages of one run, in the order they are attempted."""

    SELECT = "select"
    """List each caselist's archives and the OpenEv files, and decide what to fetch."""

    DOWNLOAD = "download"
    IMPORT = "import"
    PUBLISH = "publish"
    """Sources and manifests to the evidence bucket. Needs an AWS session."""

    PARSE = "parse"
    """Optional (`v1-e31-t06`). Skipped with a reason when no parse pipeline was wired in."""

    LANDSCAPE = "landscape"
    """Optional (`v1-e32-t05`). Skipped with a reason when no landscape service was wired in."""

    REPORT = "report"
    """Confirm the published snapshots against the bucket. Needs an AWS session, so it can pend."""


#: The stages that put bytes somewhere durable. A run is a failure only if one of these is.
REQUIRED_STAGES: Final = (SyncStage.SELECT, SyncStage.DOWNLOAD, SyncStage.IMPORT, SyncStage.PUBLISH)

#: The stages that need an AWS session and are deferred together when it has expired.
DEFERRABLE_STAGES: Final = (SyncStage.PUBLISH, SyncStage.REPORT)


class StageOutcome(StrEnum):
    """How one stage of a run ended."""

    COMPLETED = "completed"
    PLANNED = "planned"
    """A dry run worked out what the stage would do and did none of it."""

    SKIPPED = "skipped"
    """Not applicable to this run, with a reason: nothing to do, or no service wired in."""

    PENDING = "pending"
    """Deferred to a later run, recorded in the pending-work file. Credentials had expired."""

    FAILED = "failed"
    """Attempted and did not succeed. Fatal only for a stage in :data:`REQUIRED_STAGES`."""


@dataclass(frozen=True, slots=True)
class StageRecord:
    """One stage's outcome, and the one sentence that says why it was that."""

    stage: SyncStage
    outcome: StageOutcome
    reason: str | None = None

    def as_json(self) -> dict[str, object]:
        return {"stage": str(self.stage), "outcome": str(self.outcome), "reason": self.reason}


class SelectionDecision(StrEnum):
    """What the run decided to do about one listed archive or OpenEv file, and why."""

    DOWNLOAD = "download"
    ALREADY_IMPORTED = "already_imported"
    """Its date is not newer than the latest snapshot the local manifests hold."""

    ALREADY_IN_INBOX = "already_in_inbox"
    """A file of that name is in the inbox; fetching it again would spend the day's allowance."""

    FULL_ARCHIVE_NOT_PULLED_WEEKLY = "full_archive_not_pulled_weekly"
    """`<slug>-all-<date>.zip`. A weekly run pulls weeklies; see this module's docstring."""

    UNRECOGNISED_NAME = "unrecognised_name"
    """A listed name matching neither archive pattern, so it has no date to file it under."""

    OVER_DAILY_BUDGET = "over_daily_budget"
    """Beyond the 5-per-day bulk ceiling once this run's share was allocated."""

    DEFERRED_BY_RATE_LIMIT = "deferred_by_rate_limit"
    """The server applied the daily limiter mid-run. Fetched on a later run, not lost."""

    NO_EVENT_CONFIGURED = "no_event_configured"
    """An OpenEv file whose event neither its tags nor the configuration state."""


@dataclass(frozen=True, slots=True)
class ArchiveSelection:
    """One listed archive, and what this run decided about it."""

    caselist: str
    name: str
    kind: ArchiveKind
    archive_date: date | None
    decision: SelectionDecision
    listing: ArchiveListing | None = None
    """The listing itself, for the download stage. Absent from the JSON summary."""

    @property
    def wanted(self) -> bool:
        return self.decision is SelectionDecision.DOWNLOAD

    @property
    def deferred_by_cap(self) -> bool:
        """Wanted, and left for a later run by the daily bulk-download cap (`v1-e34-t03` ac5).

        Both ways the cap shows up count: the budget this run planned against
        (`OVER_DAILY_BUDGET`) and the server's own limiter mid-run (`DEFERRED_BY_RATE_LIMIT`).
        """
        return self.decision in _DEFERRED_BY_CAP

    def deferred(self) -> ArchiveSelection:
        """The same selection, marked as left for a later run by the daily limiter."""
        return ArchiveSelection(
            caselist=self.caselist,
            name=self.name,
            kind=self.kind,
            archive_date=self.archive_date,
            decision=SelectionDecision.DEFERRED_BY_RATE_LIMIT,
            listing=self.listing,
        )

    def as_json(self) -> dict[str, object]:
        return {
            "caselist": self.caselist,
            "archive": self.name,
            "kind": str(self.kind),
            "archive_date": self.archive_date.isoformat() if self.archive_date else None,
            "decision": str(self.decision),
        }


@dataclass(frozen=True, slots=True)
class OpenEvSelection:
    """One listed OpenEv camp file, and what this run decided about it.

    Named by its `openev_id` and the inbox name it downloads to. The file's own upstream path names
    a camp's file and is never carried here (`docs/policies/caselist-data-use.md` rule 4).
    """

    openev_id: int
    inbox_name: str
    year: int
    event: Event | None
    decision: SelectionDecision
    file: OpenEvFile | None = None

    @property
    def wanted(self) -> bool:
        return self.decision is SelectionDecision.DOWNLOAD

    def as_json(self) -> dict[str, object]:
        return {
            "openev_id": self.openev_id,
            "inbox_name": self.inbox_name,
            "year": self.year,
            "event": str(self.event) if self.event is not None else None,
            "decision": str(self.decision),
        }


@dataclass(frozen=True, slots=True)
class SyncPlan:
    """What a run intends to do, worked out from listings alone, before anything is fetched."""

    caselists: tuple[str, ...]
    archives: tuple[ArchiveSelection, ...]
    openev: tuple[OpenEvSelection, ...]
    bulk_downloads_allowed: int
    """What was left of the day's 5 when this plan was made."""

    bulk_downloads_spent_today: int

    @property
    def archives_to_download(self) -> tuple[ArchiveSelection, ...]:
        """The archives to fetch, oldest first, which is the order they must be imported in."""
        return tuple(
            sorted(
                (one for one in self.archives if one.wanted),
                key=lambda one: (one.archive_date or date.min, one.caselist, one.name),
            )
        )

    @property
    def openev_to_download(self) -> tuple[OpenEvSelection, ...]:
        return tuple(sorted((one for one in self.openev if one.wanted), key=lambda one: one.openev_id))

    @property
    def nothing_new(self) -> bool:
        """Nothing to fetch *and* nothing the cap held back: see :attr:`RunSummary.nothing_new`."""
        return (
            not self.archives_to_download
            and not self.openev_to_download
            and not any(one.deferred_by_cap for one in self.archives)
        )


# ------------------------------------------------------------------------------------------------
# The optional stages, as the ports they will be
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ParseStageResult:
    """What an incremental parse of the newly imported sources did (`v1-e31-t06`)."""

    files_parsed: int = 0
    cards_parsed: int = 0
    failures: int = 0


@dataclass(frozen=True, slots=True)
class LandscapeStageResult:
    """What regenerating the argument-landscape reports did (`v1-e32-t05`)."""

    reports_written: int = 0


class CaselistParseStage(Protocol):
    """The parse pipeline, as this run needs it. Implemented by `v1-e31-t06` when it ships."""

    async def parse_new_sources(self, *, caselists: Sequence[str]) -> ParseStageResult: ...


class LandscapeStage(Protocol):
    """Landscape regeneration, as this run needs it. Implemented by `v1-e32-t05` when it ships."""

    async def regenerate(self, *, caselists: Sequence[str]) -> LandscapeStageResult: ...


type ArchiveReader = Callable[[Path], Iterable[ArchiveEntry]]
"""Reads a downloaded `.zip` into importable entries.

The composition root closes `debate_core.integrations.local.archive_reader.read_archive` over this
installation's size ceilings and passes the result; the application layer names no adapter.
"""


# ------------------------------------------------------------------------------------------------
# Failures
# ------------------------------------------------------------------------------------------------


class SyncRunInProgress(DomainError):
    """Another `caselist pull` holds the run lock. This one did nothing at all."""

    def __init__(self, lock_path: Path) -> None:
        self.lock_path = lock_path
        super().__init__(
            f"another caselist sync is already running (lock held at {lock_path}); this run did "
            "nothing. Wait for it to finish, or remove the lock file if no process holds it."
        )


class NoCaselistsConfigured(DomainError):
    """The run was asked to pull nothing: no `--caselist` and none in the profile."""

    def __init__(self) -> None:
        super().__init__(
            "no caselist to pull: pass --caselist <slug> (repeatable), or set caselist.sync_caselists "
            "in this environment's profile"
        )


class ManifestsNotWritable(DomainError):
    """The local evidence store cannot name a file for a manifest, so a run cannot write one."""

    def __init__(self) -> None:
        super().__init__(
            "this local evidence store cannot name a file for an object key, so `caselist pull` "
            "cannot write the manifests it imports; build it with object_path_for set"
        )


# ------------------------------------------------------------------------------------------------
# Small pieces of durable state
# ------------------------------------------------------------------------------------------------


class RunLock:
    """An exclusive, non-blocking lock on one file, held for the length of a run.

    `flock` rather than a lock file whose existence is the lock: a run killed with `SIGKILL` leaves
    the file behind, and an existence check would then refuse every later run until somebody
    noticed. A lock the kernel drops when the process dies is the one an unattended weekly job
    needs.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._descriptor: int | None = None

    def __enter__(self) -> Self:
        import fcntl

        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(descriptor)
            raise SyncRunInProgress(self.path) from None
        os.write(descriptor, f"{os.getpid()}\n".encode())
        self._descriptor = descriptor
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._descriptor is None:
            return
        import fcntl

        with contextlib.suppress(OSError):
            fcntl.flock(self._descriptor, fcntl.LOCK_UN)
        os.close(self._descriptor)
        self._descriptor = None


@dataclass(frozen=True, slots=True)
class PendingSnapshot:
    """One snapshot whose publish is owed, as the pending-work file records it."""

    caselist: str
    snapshot: str

    def as_json(self) -> dict[str, str]:
        return {"caselist": self.caselist, "snapshot": self.snapshot}


class PendingWork:
    """The publishes a run could not do because the AWS session had expired.

    A small JSON file rather than a queue: what is owed is a handful of `(caselist, snapshot)`
    pairs, publishing is idempotent, and a file an operator can read and delete is the right
    weight for something that exists because somebody's SSO session timed out.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def read(self) -> tuple[PendingSnapshot, ...]:
        """What is owed, in the order it was recorded. A malformed file reads as nothing owed."""
        if not self.path.is_file():
            return ()
        body = _read_json_object(self.path)
        if body is None:
            logger.warning("caselist sync: the pending-work file could not be read; treating it as empty")
            return ()
        entries = body.get("publish")
        if not isinstance(entries, list):
            return ()
        owed: list[PendingSnapshot] = []
        for entry in cast("list[object]", entries):
            if not isinstance(entry, dict):
                continue
            caselist = cast("dict[str, object]", entry).get("caselist")
            snapshot = cast("dict[str, object]", entry).get("snapshot")
            if isinstance(caselist, str) and isinstance(snapshot, str):
                owed.append(PendingSnapshot(caselist=caselist, snapshot=snapshot))
        return tuple(owed)

    def write(self, owed: Sequence[PendingSnapshot]) -> None:
        """Record exactly `owed`, removing the file when nothing is left to do."""
        if not owed:
            self.path.unlink(missing_ok=True)
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(self.path, {"publish": [one.as_json() for one in owed]})

    def add(self, owed: Iterable[PendingSnapshot]) -> None:
        """Merge `owed` into what is already recorded, keeping each pair once and in order."""
        merged: list[PendingSnapshot] = list(self.read())
        for one in owed:
            if one not in merged:
                merged.append(one)
        self.write(merged)


class DownloadLedger:
    """How many bulk archive downloads this machine has spent today, against OpenCaselist's five.

    Keyed by the calendar date the run starts on, in local time, because the server's limiter is a
    per-day counter and the operator's day is the one they will compare against. A ledger for any
    other date is replaced rather than accumulated: yesterday's count is not a debt.
    """

    def __init__(self, path: Path, *, limit: int = DEFAULT_BULK_DOWNLOADS_PER_DAY) -> None:
        self.path = Path(path)
        self.limit = limit

    def spent_on(self, day: date) -> int:
        body = _read_json_object(self.path)
        if body is None or body.get("date") != day.isoformat():
            return 0
        spent = body.get("bulk_downloads")
        return spent if isinstance(spent, int) and spent >= 0 else 0

    def remaining_on(self, day: date) -> int:
        return max(self.limit - self.spent_on(day), 0)

    def record(self, day: date, downloads: int) -> None:
        """Add `downloads` to the count for `day`. A dry run never calls this."""
        if downloads <= 0:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(self.path, {"date": day.isoformat(), "bulk_downloads": self.spent_on(day) + downloads})


def _read_json_object(path: Path) -> dict[str, object] | None:
    """The JSON object at `path`, or `None` when there is none, or it is not readable as one.

    A state file this module wrote and something else corrupted is not a reason to fail a run:
    the pending-work file and the download ledger are both recoverable from what the bucket and
    the server say, so an unreadable one is treated as saying nothing.
    """
    if not path.is_file():
        return None
    try:
        body: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return cast("dict[str, object]", body) if isinstance(body, dict) else None


def _write_json(path: Path, body: Mapping[str, object]) -> None:
    """Write `body` to `path` atomically, so a killed run never leaves half a state file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.incoming")
    temporary.write_text(json.dumps(body, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


# ------------------------------------------------------------------------------------------------
# The run summary
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RunSummary:
    """Everything one run did, in the shape the console table and the JSON file both read.

    Numbers, slugs, dates, archive names and digests only. No token, no school, no team code, no
    disclosure path, no camp file title — this file is written to disk and, from `v1-e34-t03`, to
    the bucket, and `docs/policies/caselist-data-use.md` rule 4 governs both.
    """

    run_id: str
    started_at: datetime
    finished_at: datetime
    dry_run: bool
    caselists: tuple[str, ...]
    stages: tuple[StageRecord, ...]
    archives: tuple[ArchiveSelection, ...] = ()
    openev: tuple[OpenEvSelection, ...] = ()
    archives_downloaded: int = 0
    openev_downloaded: int = 0
    files_imported: int = 0
    """Members whose bytes an importer filed: new, carried forward, revised or duplicate."""

    files_duplicate: int = 0
    """Of those, the ones whose bytes the store already held under another path."""

    files_skipped: int = 0
    """Archive members no importer will take: macOS junk, lock files, symlinks, unsafe paths."""

    blobs_stored: int = 0
    """Distinct files the blob store did not already have. Zero on a re-run with nothing new."""
    cards_parsed: int = 0
    parse_failures: int = 0
    objects_published: int = 0
    reports_written: int = 0
    snapshots_imported: tuple[str, ...] = ()
    pending_publish: tuple[str, ...] = ()
    bulk_downloads_allowed: int = 0
    bulk_downloads_spent_today: int = 0

    @property
    def archives_seen(self) -> int:
        return len(self.archives)

    @property
    def archives_deferred(self) -> int:
        """Archives this run wanted and the daily bulk-download cap left for a later run."""
        return sum(1 for one in self.archives if one.deferred_by_cap)

    @property
    def archives_wanted(self) -> int:
        """Archives newer than what this machine held: those fetched plus those the cap deferred.

        The number `archives_downloaded` is to be read against. When the two differ the run was
        truncated by the cap, which a caption reporting only "N downloaded" cannot show
        (`v1-e34-t03` ac5).
        """
        return sum(1 for one in self.archives if one.wanted or one.deferred_by_cap)

    @property
    def duration_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()

    @property
    def succeeded(self) -> bool:
        """True when no stage that puts bytes somewhere durable failed.

        A parse or landscape stage that failed is reported and does not make the run a failure:
        the captured bytes are already safe and the derivation can be recomputed.
        """
        return not any(
            record.outcome is StageOutcome.FAILED and record.stage in REQUIRED_STAGES
            for record in self.stages
        )

    @property
    def nothing_new(self) -> bool:
        """True when there was nothing to fetch and nothing waiting to be published.

        Not true of a run that *was not allowed* to fetch. A run whose every candidate the daily
        cap deferred downloads nothing, imports nothing and owes no publish, and used to report
        "none newer than what this machine already holds" against a store that held none of them
        — measured in dev on 2026-09-24 (`v1-e34-t03` ac6, `docs/data/caselist-sync-runs.md`).
        """
        return (
            self.archives_downloaded == 0
            and self.openev_downloaded == 0
            and self.archives_deferred == 0
            and not self.snapshots_imported
            and not self.pending_publish
        )

    def stage(self, stage: SyncStage) -> StageRecord | None:
        return next((record for record in self.stages if record.stage is stage), None)

    def as_json(self) -> dict[str, object]:
        """The summary as it is written to disk and returned by `caselist pull --json`."""
        return {
            "run_id": self.run_id,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "duration_seconds": round(self.duration_seconds, 3),
            "dry_run": self.dry_run,
            "succeeded": self.succeeded,
            "nothing_new": self.nothing_new,
            "caselists": list(self.caselists),
            "stages": [record.as_json() for record in self.stages],
            "archives_seen": self.archives_seen,
            "archives_wanted": self.archives_wanted,
            "archives_downloaded": self.archives_downloaded,
            "archives_deferred": self.archives_deferred,
            "openev_seen": len(self.openev),
            "openev_downloaded": self.openev_downloaded,
            "files_imported": self.files_imported,
            "files_duplicate": self.files_duplicate,
            "files_skipped": self.files_skipped,
            "blobs_stored": self.blobs_stored,
            "cards_parsed": self.cards_parsed,
            "parse_failures": self.parse_failures,
            "objects_published": self.objects_published,
            "reports_written": self.reports_written,
            "snapshots_imported": list(self.snapshots_imported),
            "pending_publish": list(self.pending_publish),
            "bulk_downloads_allowed": self.bulk_downloads_allowed,
            "bulk_downloads_spent_today": self.bulk_downloads_spent_today,
            "selections": [one.as_json() for one in self.archives],
            "openev_selections": [one.as_json() for one in self.openev],
        }


# ------------------------------------------------------------------------------------------------
# The service
# ------------------------------------------------------------------------------------------------


@dataclass
class _RunTally:
    """What a run has accumulated so far. Mutable, private, and never leaves this module."""

    stages: list[StageRecord] = field(default_factory=lambda: list[StageRecord]())
    archives: tuple[ArchiveSelection, ...] = ()
    openev: tuple[OpenEvSelection, ...] = ()
    downloaded_archives: list[tuple[ArchiveSelection, DownloadedFile]] = field(
        default_factory=lambda: list[tuple[ArchiveSelection, DownloadedFile]]()
    )
    downloaded_openev: list[tuple[OpenEvSelection, DownloadedFile]] = field(
        default_factory=lambda: list[tuple[OpenEvSelection, DownloadedFile]]()
    )
    files_imported: int = 0
    files_duplicate: int = 0
    files_skipped: int = 0
    blobs_stored: int = 0
    cards_parsed: int = 0
    parse_failures: int = 0
    objects_published: int = 0
    reports_written: int = 0
    snapshots_imported: list[str] = field(default_factory=lambda: list[str]())
    publish_targets: list[PendingSnapshot] = field(default_factory=lambda: list[PendingSnapshot]())
    published: list[PendingSnapshot] = field(default_factory=lambda: list[PendingSnapshot]())
    pending_publish: list[PendingSnapshot] = field(default_factory=lambda: list[PendingSnapshot]())
    bulk_downloads_allowed: int = 0
    bulk_downloads_spent_today: int = 0

    def record(self, stage: SyncStage, outcome: StageOutcome, reason: str | None = None) -> None:
        self.stages.append(StageRecord(stage=stage, outcome=outcome, reason=reason))


class CaselistSyncService:
    """Runs one weekly pull: select, download, import, publish, then the optional stages.

    Built by the composition root from the services the other tasks own::

        service = CaselistSyncService(
            source=container.opencaselist_client(),
            archive_importer=container.caselist_import(),
            openev_importer=container.openev_import(),
            local=local_evidence,
            read_archive=reader,
            event_for_caselist=event_for_caselist,
            inbox=settings.caselist.inbox_dir,
            state_dir=settings.storage.data_dir,
            publisher=container.caselist_publish(),   # None when no bucket is configured
        )

    Args:
        source: Where archives and OpenEv files are listed and fetched from (`v1-e34-t01`).
        archive_importer: The weekly-archive importer (`v1-e30-t03`).
        openev_importer: The OpenEv camp-file importer (`v1-e30-t04`).
        local: This machine's evidence store, read for the latest snapshot per caselist and
            written for each import's manifest. Its `object_path_for` must be set.
        read_archive: Reads a downloaded `.zip` into importable entries.
        event_for_caselist: Which event a caselist slug debates, or `None` when this build does
            not know. A caselist whose event is unknown is not imported, because the event decides
            which sides are legal on a disclosure.
        inbox: Where downloads land and where the importer reads them from.
        state_dir: Where the run lock, the pending-work file, the download ledger and the run
            summaries live. The environment's data directory.
        publisher: The S3 publisher (`v1-e30-t05`), or `None` for an environment with no bucket.
        status: The local-against-bucket comparison used by the report stage, or `None`.
        parse: The parse pipeline (`v1-e31-t06`), or `None` — the normal case today.
        landscape: Landscape regeneration (`v1-e32-t05`), or `None` — the normal case today.
        openev_event: The event to file OpenEv files under when their own tags do not say.
        openev_year: The OpenEv release year to list, or `None` for the API's current year.
        bulk_downloads_per_day: The upstream ceiling; never raised above
            :data:`DEFAULT_BULK_DOWNLOADS_PER_DAY`.
        clock: Returns an aware `datetime`; the run's timestamps and the ledger's day come from it.
    """

    def __init__(
        self,
        *,
        source: CaselistArchiveSource,
        archive_importer: CaselistImportService,
        openev_importer: OpenEvImportService,
        local: LocalEvidence,
        read_archive: ArchiveReader,
        event_for_caselist: Callable[[str], Event | None],
        inbox: Path,
        state_dir: Path,
        publisher: CaselistPublishService | None = None,
        status: CaselistStatusService | None = None,
        parse: CaselistParseStage | None = None,
        landscape: LandscapeStage | None = None,
        openev_event: Event | None = None,
        openev_year: int | None = None,
        bulk_downloads_per_day: int = DEFAULT_BULK_DOWNLOADS_PER_DAY,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._source = source
        self._archives = archive_importer
        self._openev_importer = openev_importer
        self._local = local
        self._read_archive = read_archive
        self._event_for_caselist = event_for_caselist
        self._inbox = Path(inbox)
        self._state_dir = Path(state_dir)
        self._publisher = publisher
        self._status = status
        self._parse = parse
        self._landscape = landscape
        self._openev_event = openev_event
        self._openev_year = openev_year
        self._clock = clock
        self._ledger = DownloadLedger(
            self._state_dir / DOWNLOAD_LEDGER_FILENAME,
            limit=min(bulk_downloads_per_day, DEFAULT_BULK_DOWNLOADS_PER_DAY),
        )
        self._pending = PendingWork(self._state_dir / PENDING_WORK_FILENAME)

    # --------------------------------------------------------------------------------------
    # Entry points
    # --------------------------------------------------------------------------------------

    @property
    def pending_work(self) -> PendingWork:
        """The publishes this machine still owes, so a command can report them without a run."""
        return self._pending

    async def plan(self, caselists: Sequence[str]) -> SyncPlan:
        """Decide what a run would fetch, using listing calls only and writing nothing.

        This is the whole of `--dry-run`: no download, no import, no upload, no state file. It is
        also the first stage of a real run, so the two can never disagree about what was selected.
        """
        if not caselists:
            raise NoCaselistsConfigured
        today = self._clock().date()
        allowed = self._ledger.remaining_on(today)
        inbox_names = self._inbox_names()
        selections: list[ArchiveSelection] = []
        for caselist in caselists:
            selections.extend(await self._select_archives(caselist, inbox_names=inbox_names))
        selections = within_daily_budget(selections, allowed=allowed)
        openev = await self._select_openev(inbox_names=inbox_names)
        return SyncPlan(
            caselists=tuple(caselists),
            archives=tuple(selections),
            openev=tuple(openev),
            bulk_downloads_allowed=allowed,
            bulk_downloads_spent_today=self._ledger.spent_on(today),
        )

    async def run(self, caselists: Sequence[str], *, dry_run: bool = False) -> RunSummary:
        """One whole pull. Holds the run lock for its duration.

        Raises :class:`SyncRunInProgress` at once if another run holds the lock, and
        :class:`NoCaselistsConfigured` if asked to pull nothing. Everything else is an outcome in
        the returned :class:`RunSummary` rather than an exception, because a run that got half way
        has captured bytes worth recording — the two exceptions being an expired OpenCaselist token
        (policy E34 gate 5: the run stops and the operator is told) and a store this machine cannot
        write manifests to.
        """
        if not caselists:
            raise NoCaselistsConfigured
        started = self._clock()
        with RunLock(self._state_dir / LOCK_FILENAME):
            tally = _RunTally()
            plan = await self._selection_stage(caselists, tally)
            if dry_run:
                self._plan_remaining_stages(plan, tally)
            else:
                await self._execute(plan, tally)
            summary = self._summarise(started, caselists, tally, dry_run=dry_run)
        if not dry_run:
            self._write_summary(summary)
        _log_summary(summary)
        return summary

    async def publish_pending(self) -> RunSummary:
        """Complete the publishes an earlier run deferred, and nothing else.

        What `caselist pull --publish-pending` runs after `aws sso login`. It takes the same lock,
        so it cannot overlap a scheduled run, and it drains the pending-work file: each snapshot
        that publishes completely is removed from it, and anything that fails stays owed.
        """
        started = self._clock()
        with RunLock(self._state_dir / LOCK_FILENAME):
            tally = _RunTally()
            owed = self._pending.read()
            tally.record(SyncStage.SELECT, StageOutcome.COMPLETED, f"{len(owed)} snapshot(s) owed")
            for stage in (SyncStage.DOWNLOAD, SyncStage.IMPORT):
                tally.record(stage, StageOutcome.SKIPPED, "publish-pending does no fetching or importing")
            tally.publish_targets = list(owed)
            await self._publish_stage(tally, drain_pending=True)
            for stage in (SyncStage.PARSE, SyncStage.LANDSCAPE):
                tally.record(stage, StageOutcome.SKIPPED, "publish-pending runs no derived stages")
            await self._report_stage(tally)
            summary = self._summarise(started, (), tally, dry_run=False)
        self._write_summary(summary)
        _log_summary(summary)
        return summary

    # --------------------------------------------------------------------------------------
    # Selection
    # --------------------------------------------------------------------------------------

    async def _selection_stage(self, caselists: Sequence[str], tally: _RunTally) -> SyncPlan:
        """Run :meth:`plan` as a stage, recording a listing that failed rather than raising it."""
        try:
            plan = await self.plan(caselists)
        except ProviderRateLimited as limited:
            plan = SyncPlan(
                caselists=tuple(caselists),
                archives=(),
                openev=(),
                bulk_downloads_allowed=0,
                bulk_downloads_spent_today=self._ledger.spent_on(self._clock().date()),
            )
            tally.record(SyncStage.SELECT, StageOutcome.SKIPPED, f"OpenCaselist is rate limiting: {limited}")
            tally.archives, tally.openev = plan.archives, plan.openev
            return plan
        tally.archives, tally.openev = plan.archives, plan.openev
        tally.bulk_downloads_allowed = plan.bulk_downloads_allowed
        tally.bulk_downloads_spent_today = plan.bulk_downloads_spent_today
        fetch = len(plan.archives_to_download) + len(plan.openev_to_download)
        deferred = sum(1 for one in plan.archives if one.deferred_by_cap)
        listed = f"{len(plan.archives)} archive(s) and {len(plan.openev)} OpenEv file(s) listed; "
        if deferred:
            wanted = fetch + deferred
            detail = (
                f"{listed}{fetch} to fetch of {wanted} wanted, {deferred} deferred by the daily "
                f"download cap ({plan.bulk_downloads_allowed} of today's allowance left)"
            )
        else:
            detail = f"{listed}{fetch} to fetch"
        tally.record(SyncStage.SELECT, StageOutcome.COMPLETED, detail)
        return plan

    async def _select_archives(self, caselist: str, *, inbox_names: frozenset[str]) -> list[ArchiveSelection]:
        """Decide about every archive one caselist lists, against the manifests and the inbox."""
        latest = await self._latest_imported_snapshot(caselist)
        selections: list[ArchiveSelection] = []
        for listing in await self._source.list_archives(caselist):
            selections.append(
                ArchiveSelection(
                    caselist=caselist,
                    name=listing.name,
                    kind=listing.kind,
                    archive_date=listing.archive_date,
                    decision=_decide_archive(listing, latest=latest, inbox_names=inbox_names),
                    listing=listing,
                )
            )
        return selections

    async def _latest_imported_snapshot(self, caselist: str) -> date | None:
        """The newest snapshot this machine holds a manifest for, or `None` for a first pull.

        Read from the manifests rather than from the repository, because a manifest is what says a
        snapshot was imported *and* is what the publisher and `v1-e34-t03` read. One source of
        truth for "we already have this week".
        """
        snapshots = await read_local_snapshots(self._local, caselist)
        dates = [_parsed_date(one.snapshot) for one in snapshots]
        found = [one for one in dates if one is not None]
        return max(found) if found else None

    async def _select_openev(self, *, inbox_names: frozenset[str]) -> list[OpenEvSelection]:
        """Decide about every OpenEv camp file the API lists for the configured year."""
        files = await self._source.list_openev(year=self._openev_year)
        recorded: dict[tuple[int, Event], frozenset[str]] = {}
        selections: list[OpenEvSelection] = []
        for file in files:
            inbox_name = openev_inbox_name(file)
            event = _openev_event_of(file, self._openev_event)
            year = file.year or self._openev_year or self._clock().year
            if event is None:
                decision = SelectionDecision.NO_EVENT_CONFIGURED
            elif inbox_name in inbox_names:
                decision = SelectionDecision.ALREADY_IN_INBOX
            else:
                if (year, event) not in recorded:
                    recorded[(year, event)] = self._openev_manifest_paths(year, event)
                decision = (
                    SelectionDecision.ALREADY_IMPORTED
                    if inbox_name in recorded[(year, event)]
                    else SelectionDecision.DOWNLOAD
                )
            selections.append(
                OpenEvSelection(
                    openev_id=file.openev_id,
                    inbox_name=inbox_name,
                    year=year,
                    event=event,
                    decision=decision,
                    file=file,
                )
            )
        return selections

    def _openev_manifest_paths(self, year: int, event: Event) -> frozenset[str]:
        """Every member path the release's manifest already records, for the "already imported" check."""
        paths: set[str] = set()
        for line in read_manifest_lines(self._manifest_path(openev_manifest_key(year, event))):
            try:
                row: object = json.loads(line)
            except ValueError:
                continue
            if not isinstance(row, dict):
                continue
            path = cast("dict[str, object]", row).get("path")
            if isinstance(path, str):
                paths.add(path)
        return frozenset(paths)

    def _inbox_names(self) -> frozenset[str]:
        """The files already in the inbox, by name.

        `<inbox>/.partial/` is skipped: it holds downloads in progress, and a `.part` file is not
        an archive (`v1-e34-t01` review). Anything else that is not a regular file is skipped too.
        """
        if not self._inbox.is_dir():
            return frozenset()
        return frozenset(
            entry.name
            for entry in self._inbox.iterdir()
            if entry.is_file() and entry.name != INBOX_PARTIAL_DIRECTORY and not entry.name.startswith(".")
        )

    # --------------------------------------------------------------------------------------
    # A dry run
    # --------------------------------------------------------------------------------------

    def _plan_remaining_stages(self, plan: SyncPlan, tally: _RunTally) -> None:
        """Say what each remaining stage would do, and do none of it (ac2)."""
        fetch = len(plan.archives_to_download) + len(plan.openev_to_download)
        tally.record(
            SyncStage.DOWNLOAD,
            StageOutcome.PLANNED,
            f"would download {fetch} file(s) into {self._inbox}",
        )
        tally.record(
            SyncStage.IMPORT,
            StageOutcome.PLANNED,
            f"would import {fetch} downloaded file(s) and write their manifests",
        )
        tally.record(
            SyncStage.PUBLISH,
            StageOutcome.PLANNED if self._publisher is not None else StageOutcome.SKIPPED,
            "would publish the imported snapshots and their sources"
            if self._publisher is not None
            else _NO_BUCKET,
        )
        tally.record(
            SyncStage.PARSE,
            StageOutcome.PLANNED if self._parse is not None else StageOutcome.SKIPPED,
            "would parse the newly imported sources" if self._parse is not None else _NO_PARSE_PIPELINE,
        )
        tally.record(
            SyncStage.LANDSCAPE,
            StageOutcome.PLANNED if self._landscape is not None else StageOutcome.SKIPPED,
            "would regenerate the landscape reports" if self._landscape is not None else _NO_LANDSCAPE,
        )
        tally.record(
            SyncStage.REPORT,
            StageOutcome.PLANNED if self._status is not None else StageOutcome.SKIPPED,
            "would confirm the published snapshots against the bucket"
            if self._status is not None
            else _NO_BUCKET,
        )

    # --------------------------------------------------------------------------------------
    # A real run
    # --------------------------------------------------------------------------------------

    async def _execute(self, plan: SyncPlan, tally: _RunTally) -> None:
        await self._download_stage(plan, tally)
        await self._import_stage(tally)
        await self._publish_stage(tally, drain_pending=True)
        await self._parse_stage(plan, tally)
        await self._landscape_stage(plan, tally)
        await self._report_stage(tally)

    async def _download_stage(self, plan: SyncPlan, tally: _RunTally) -> None:
        """Fetch the selected archives oldest-first, then the OpenEv files.

        Oldest-first because the archive importer classifies each archive against the week before
        it, and a newer archive imported first would mark this week's files as removed. Three
        things stop the fetching early and none of them is a failure of the run: the daily limiter
        (`skip today`), an expired token (the run stops talking to OpenCaselist, policy gate 5),
        and a store error, each recorded on the stage.
        """
        wanted = list(plan.archives_to_download)
        openev_wanted = list(plan.openev_to_download)
        if not wanted and not openev_wanted:
            deferred = sum(1 for one in plan.archives if one.deferred_by_cap)
            tally.record(
                SyncStage.DOWNLOAD,
                StageOutcome.SKIPPED,
                f"nothing fetched: {deferred} archive(s) deferred by the daily download cap"
                if deferred
                else "nothing new to download",
            )
            return

        deferred_from: int | None = None
        failure: str | None = None
        self._inbox.mkdir(parents=True, exist_ok=True)
        for index, selection in enumerate(wanted):
            listing = selection.listing
            if listing is None:  # pragma: no cover - a selection to download always carries one
                continue
            try:
                downloaded = await self._source.download_archive(listing, self._inbox)
            except ProviderRateLimited as limited:
                if _is_daily_limiter(limited):
                    deferred_from = index
                    failure = f"OpenCaselist's daily download limit was reached: {limited}"
                    break
                failure = str(limited)
                break
            except DomainError as refused:
                failure = f"{selection.name}: {refused}"
                break
            tally.downloaded_archives.append((selection, downloaded))
            if not downloaded.already_present:
                self._ledger.record(self._clock().date(), 1)

        if deferred_from is not None:
            tally.archives = _mark_deferred(tally.archives, wanted[deferred_from:])

        if failure is None:
            for openev_selection in openev_wanted:
                file = openev_selection.file
                if file is None:  # pragma: no cover - a selection to download always carries one
                    continue
                try:
                    downloaded = await self._source.download_openev(file, self._inbox)
                except DomainError as refused:
                    failure = f"openev-{openev_selection.openev_id}: {refused}"
                    break
                tally.downloaded_openev.append((openev_selection, downloaded))

        fetched = len(tally.downloaded_archives) + len(tally.downloaded_openev)
        if failure is not None and deferred_from is None:
            tally.record(SyncStage.DOWNLOAD, StageOutcome.FAILED, f"{fetched} fetched, then: {failure}")
            return
        tally.record(
            SyncStage.DOWNLOAD,
            StageOutcome.COMPLETED,
            f"{fetched} file(s) fetched" + (f"; {failure}" if failure else ""),
        )

    async def _import_stage(self, tally: _RunTally) -> None:
        """Import every file that reached the inbox, archives before camp files, and write manifests."""
        if not tally.downloaded_archives and not tally.downloaded_openev:
            tally.record(SyncStage.IMPORT, StageOutcome.SKIPPED, "nothing was downloaded")
            return
        failures: list[str] = []
        for selection, downloaded in tally.downloaded_archives:
            try:
                await self._import_archive(selection, downloaded, tally)
            except DomainError as refused:
                failures.append(f"{selection.name}: {refused}")
        for openev_selection, downloaded in tally.downloaded_openev:
            try:
                await self._import_openev(openev_selection, downloaded, tally)
            except DomainError as refused:
                failures.append(f"openev-{openev_selection.openev_id}: {refused}")
        if failures:
            tally.record(
                SyncStage.IMPORT,
                StageOutcome.FAILED,
                f"{len(tally.snapshots_imported)} imported; {len(failures)} refused: " + "; ".join(failures),
            )
            return
        tally.record(
            SyncStage.IMPORT,
            StageOutcome.COMPLETED,
            f"{len(tally.snapshots_imported)} snapshot(s) imported, {tally.blobs_stored} new file(s) stored",
        )

    async def _import_archive(
        self, selection: ArchiveSelection, downloaded: DownloadedFile, tally: _RunTally
    ) -> None:
        event = self._event_for_caselist(selection.caselist)
        if event is None:
            raise UnknownSyncEvent(selection.caselist)
        if selection.archive_date is None:  # pragma: no cover - never selected for download
            raise UndatedArchive(selection.name)
        report = await self._archives.import_archive(
            self._read_archive(downloaded.path),
            caselist=selection.caselist,
            snapshot=selection.archive_date,
            event=event,
            archive_sha256=downloaded.sha256,
            acquisition=Acquisition.API,
        )
        write_manifest(report, self._manifest_path(manifest_key(selection.caselist, selection.archive_date)))
        self._count_archive(report, tally)
        tally.snapshots_imported.append(f"{report.caselist} {report.snapshot.isoformat()}")
        tally.publish_targets.append(
            PendingSnapshot(caselist=report.caselist, snapshot=report.snapshot.isoformat())
        )

    async def _import_openev(
        self, selection: OpenEvSelection, downloaded: DownloadedFile, tally: _RunTally
    ) -> None:
        if selection.event is None:  # pragma: no cover - never selected for download
            raise UnknownSyncEvent("openev")
        key = openev_manifest_key(selection.year, selection.event)
        path = self._manifest_path(key)
        report = await self._openev_importer.import_release(
            self._openev_entries(downloaded),
            year=selection.year,
            event=selection.event,
            imported_on=self._clock().date(),
            archive_sha256=downloaded.sha256,
            recorded_manifest=read_manifest_lines(path),
        )
        write_manifest_lines(report.manifest_lines, path)
        self._count_openev(report, tally)
        release = report.release
        if release not in tally.snapshots_imported:
            tally.snapshots_imported.append(f"{OPENEV_PUBLISH_TARGET} {release}")
        target = PendingSnapshot(caselist=OPENEV_PUBLISH_TARGET, snapshot=release)
        if target not in tally.publish_targets:
            tally.publish_targets.append(target)

    def _openev_entries(self, downloaded: DownloadedFile) -> Iterable[ArchiveEntry]:
        """The members of one OpenEv download: a zip's, or the single file it is.

        OpenEv publishes both — a camp's whole release as a `.zip`, and individual documents. A
        single document becomes one member named as it sits in the inbox, which is the name the
        camp-metadata parser already knows to take the `openev-<id>-` prefix off
        (`debate_core.application.caselist.camp_metadata`).
        """
        if downloaded.path.suffix.lower() == ".zip":
            return self._read_archive(downloaded.path)
        return [
            ArchiveMember(
                path=downloaded.path.name,
                sha256=downloaded.sha256,
                byte_size=downloaded.byte_size,
                data=downloaded.path.read_bytes(),
            )
        ]

    async def _publish_stage(self, tally: _RunTally, *, drain_pending: bool) -> None:
        """Publish what was imported, plus anything an earlier run deferred.

        An expired or refused AWS session is not a failure of the run: every target still owed is
        written to the pending-work file, the stage is `PENDING`, and the next run — or
        `caselist pull --publish-pending` — completes it. Everything already captured is on this
        machine either way.
        """
        targets = list(tally.publish_targets)
        if drain_pending:
            for owed in self._pending.read():
                if owed not in targets:
                    targets.append(owed)
        if not targets:
            tally.record(SyncStage.PUBLISH, StageOutcome.SKIPPED, "nothing new to publish")
            return
        if self._publisher is None:
            tally.record(SyncStage.PUBLISH, StageOutcome.SKIPPED, _NO_BUCKET)
            return

        published = 0
        incomplete: list[str] = []
        unfinished: list[PendingSnapshot] = []
        for index, target in enumerate(targets):
            try:
                plan = await self._publisher.plan(target.caselist, target.snapshot)
                report = await self._publisher.execute(plan)
            except (StoreCredentialsExpired, StoreAccessDenied) as expired:
                tally.pending_publish = targets[index:]
                self._pending.add(tally.pending_publish)
                tally.objects_published = published
                tally.record(
                    SyncStage.PUBLISH,
                    StageOutcome.PENDING,
                    f"{published} object(s) published, {len(tally.pending_publish)} snapshot(s) "
                    f"left for a later run: {expired}",
                )
                return
            except NothingToPublish:
                incomplete.append(f"{target.caselist} {target.snapshot}: no local manifest")
                continue
            published += report.count(SourceResult.UPLOADED)
            if report.succeeded:
                tally.published.append(target)
                continue
            incomplete.append(f"{target.caselist} {target.snapshot}: " + ", ".join(report.failed_sha256))
            unfinished.append(target)
        tally.objects_published = published
        # What finished is no longer owed; what did not is owed whether or not it was owed before,
        # so that a snapshot whose upload failed is retried next week rather than quietly dropped.
        still_owed = [owed for owed in self._pending.read() if owed not in tally.published]
        for owed in unfinished:
            if owed not in still_owed:
                still_owed.append(owed)
        self._pending.write(still_owed)
        if incomplete:
            tally.pending_publish = unfinished
            tally.record(
                SyncStage.PUBLISH,
                StageOutcome.FAILED,
                f"{published} object(s) published; incomplete: " + "; ".join(incomplete),
            )
            return
        tally.record(
            SyncStage.PUBLISH,
            StageOutcome.COMPLETED,
            f"{published} object(s) uploaded across {len(targets)} snapshot(s)",
        )

    async def _parse_stage(self, plan: SyncPlan, tally: _RunTally) -> None:
        """Parse the newly imported sources, when a parse pipeline exists. It usually does not."""
        if self._parse is None:
            tally.record(SyncStage.PARSE, StageOutcome.SKIPPED, _NO_PARSE_PIPELINE)
            return
        if not tally.snapshots_imported:
            tally.record(SyncStage.PARSE, StageOutcome.SKIPPED, "nothing new was imported")
            return
        try:
            result = await self._parse.parse_new_sources(caselists=plan.caselists)
        except (DomainError, OSError) as failed:
            tally.record(SyncStage.PARSE, StageOutcome.FAILED, str(failed))
            return
        tally.cards_parsed = result.cards_parsed
        tally.parse_failures = result.failures
        tally.record(
            SyncStage.PARSE,
            StageOutcome.COMPLETED,
            f"{result.files_parsed} file(s) parsed into {result.cards_parsed} card(s), "
            f"{result.failures} failure(s)",
        )

    async def _landscape_stage(self, plan: SyncPlan, tally: _RunTally) -> None:
        """Regenerate the landscape reports, when that service exists. It does not yet."""
        if self._landscape is None:
            tally.record(SyncStage.LANDSCAPE, StageOutcome.SKIPPED, _NO_LANDSCAPE)
            return
        if not tally.snapshots_imported:
            tally.record(SyncStage.LANDSCAPE, StageOutcome.SKIPPED, "nothing new was imported")
            return
        try:
            result = await self._landscape.regenerate(caselists=plan.caselists)
        except (DomainError, OSError) as failed:
            tally.record(SyncStage.LANDSCAPE, StageOutcome.FAILED, str(failed))
            return
        tally.reports_written = result.reports_written
        tally.record(
            SyncStage.LANDSCAPE, StageOutcome.COMPLETED, f"{result.reports_written} report(s) written"
        )

    async def _report_stage(self, tally: _RunTally) -> None:
        """Confirm in the bucket what this run says it published.

        The one stage after publish that still needs an AWS session, so it pends with publish
        rather than claiming a confirmation nobody made.
        """
        if self._status is None:
            tally.record(SyncStage.REPORT, StageOutcome.SKIPPED, _NO_BUCKET)
            return
        if tally.pending_publish:
            tally.record(SyncStage.REPORT, StageOutcome.PENDING, "the publish it would confirm is pending")
            return
        if not tally.published:
            tally.record(SyncStage.REPORT, StageOutcome.SKIPPED, "nothing new was published")
            return
        confirmed = 0
        drifted: list[str] = []
        # Snapshot by snapshot, and only the ones this run published. A caselist-wide check would
        # report an older snapshot somebody imported by hand and never published as drift of this
        # run, which it is not: completing that one is `caselist publish`'s job.
        for target in tally.published:
            try:
                report = await self._status.status(target.caselist, target.snapshot)
            except (StoreCredentialsExpired, StoreAccessDenied) as expired:
                tally.record(SyncStage.REPORT, StageOutcome.PENDING, str(expired))
                return
            except (NoCaselistEvidence, DomainError) as failed:
                drifted.append(f"{target.caselist} {target.snapshot}: {failed}")
                continue
            confirmed += sum(1 for snapshot in report.snapshots if snapshot.in_sync)
            drifted.extend(f"{one.caselist} {one.snapshot}" for one in report.drifted)
        if drifted:
            tally.record(
                SyncStage.REPORT,
                StageOutcome.FAILED,
                f"{confirmed} snapshot(s) confirmed; not in sync: " + ", ".join(drifted),
            )
            return
        tally.record(
            SyncStage.REPORT, StageOutcome.COMPLETED, f"{confirmed} snapshot(s) confirmed in the bucket"
        )

    # --------------------------------------------------------------------------------------
    # Counting, summarising, writing
    # --------------------------------------------------------------------------------------

    def _count_archive(self, report: ImportReport, tally: _RunTally) -> None:
        tally.files_imported += sum(
            report.count(name)
            for name in (
                Classification.NEW,
                Classification.UNCHANGED,
                Classification.CHANGED,
                Classification.DUPLICATE,
            )
        )
        tally.files_duplicate += report.count(Classification.DUPLICATE)
        tally.files_skipped += sum(report.skipped.values())
        tally.blobs_stored += report.newly_stored_blobs

    def _count_openev(self, report: OpenEvImportReport, tally: _RunTally) -> None:
        tally.files_imported += sum(
            report.count(name)
            for name in (
                Classification.NEW,
                Classification.UNCHANGED,
                Classification.CHANGED,
                Classification.DUPLICATE,
            )
        )
        tally.files_duplicate += report.count(Classification.DUPLICATE)
        tally.files_skipped += sum(report.skipped.values())
        tally.blobs_stored += report.newly_stored_blobs

    def _manifest_path(self, key: str) -> Path:
        path_for = self._local.object_path_for
        if path_for is None:
            raise ManifestsNotWritable
        return path_for(key)

    def _summarise(
        self, started: datetime, caselists: Sequence[str], tally: _RunTally, *, dry_run: bool
    ) -> RunSummary:
        finished = self._clock()
        return RunSummary(
            run_id=started.strftime("%Y%m%dT%H%M%SZ"),
            started_at=started,
            finished_at=finished,
            dry_run=dry_run,
            caselists=tuple(caselists),
            stages=tuple(tally.stages),
            archives=tally.archives,
            openev=tally.openev,
            archives_downloaded=len(tally.downloaded_archives),
            openev_downloaded=len(tally.downloaded_openev),
            files_imported=tally.files_imported,
            files_duplicate=tally.files_duplicate,
            files_skipped=tally.files_skipped,
            blobs_stored=tally.blobs_stored,
            cards_parsed=tally.cards_parsed,
            parse_failures=tally.parse_failures,
            objects_published=tally.objects_published,
            reports_written=tally.reports_written,
            snapshots_imported=tuple(tally.snapshots_imported),
            pending_publish=tuple(f"{one.caselist} {one.snapshot}" for one in tally.pending_publish),
            bulk_downloads_allowed=tally.bulk_downloads_allowed,
            bulk_downloads_spent_today=tally.bulk_downloads_spent_today,
        )

    def _write_summary(self, summary: RunSummary) -> Path:
        """Write the run's JSON summary under `<state_dir>/caselist-sync-runs/`, and return it."""
        destination = self._state_dir / RUN_SUMMARY_DIRECTORY / f"{summary.run_id}.json"
        _write_json(destination, summary.as_json())
        return destination

    def summary_path(self, summary: RunSummary) -> Path:
        """Where :meth:`run` wrote (or, for a dry run, would have written) this run's summary."""
        return self._state_dir / RUN_SUMMARY_DIRECTORY / f"{summary.run_id}.json"


# ------------------------------------------------------------------------------------------------
# Selection rules
# ------------------------------------------------------------------------------------------------

_DEFERRED_BY_CAP: Final = frozenset(
    {SelectionDecision.OVER_DAILY_BUDGET, SelectionDecision.DEFERRED_BY_RATE_LIMIT}
)

_NO_BUCKET: Final = "this environment names no evidence bucket, so nothing is published from here"
_NO_PARSE_PIPELINE: Final = "no parse pipeline is installed (v1-e31-t06 has not shipped)"
_NO_LANDSCAPE: Final = "no landscape service is installed (v1-e32-t05 has not shipped)"


def _decide_archive(
    listing: ArchiveListing, *, latest: date | None, inbox_names: frozenset[str]
) -> SelectionDecision:
    """What a weekly run does about one listed archive. See this module's docstring for why."""
    if listing.kind is ArchiveKind.UNRECOGNISED or listing.archive_date is None:
        return SelectionDecision.UNRECOGNISED_NAME
    if listing.kind is ArchiveKind.FULL:
        return SelectionDecision.FULL_ARCHIVE_NOT_PULLED_WEEKLY
    if latest is not None and listing.archive_date <= latest:
        return SelectionDecision.ALREADY_IMPORTED
    if listing.name in inbox_names:
        return SelectionDecision.ALREADY_IN_INBOX
    return SelectionDecision.DOWNLOAD


def within_daily_budget(selections: Sequence[ArchiveSelection], *, allowed: int) -> list[ArchiveSelection]:
    """Keep at most `allowed` downloads, shared round-robin across the caselists.

    Round-robin rather than globally oldest-first, because one caselist with a long back-catalogue
    would otherwise spend the whole day's allowance and the others would get nothing week after
    week. Within a caselist the oldest is always taken first, so what is deferred is always the
    newest — and the newest is the one certain to still be listed next week.
    """
    wanted_by_caselist: dict[str, list[ArchiveSelection]] = {}
    for selection in selections:
        if selection.wanted:
            wanted_by_caselist.setdefault(selection.caselist, []).append(selection)
    for queue in wanted_by_caselist.values():
        queue.sort(key=lambda one: (one.archive_date or date.min, one.name))

    granted: set[int] = set()
    remaining = max(allowed, 0)
    while remaining > 0 and any(wanted_by_caselist.values()):
        for queue in wanted_by_caselist.values():
            if remaining == 0 or not queue:
                continue
            granted.add(id(queue.pop(0)))
            remaining -= 1

    return [
        selection
        if not selection.wanted or id(selection) in granted
        else ArchiveSelection(
            caselist=selection.caselist,
            name=selection.name,
            kind=selection.kind,
            archive_date=selection.archive_date,
            decision=SelectionDecision.OVER_DAILY_BUDGET,
            listing=selection.listing,
        )
        for selection in selections
    ]


def _mark_deferred(
    selections: Sequence[ArchiveSelection], deferred: Sequence[ArchiveSelection]
) -> tuple[ArchiveSelection, ...]:
    """Re-decide the named selections as deferred by the daily limiter, keeping listing order."""
    names = {(one.caselist, one.name) for one in deferred}
    return tuple(one.deferred() if (one.caselist, one.name) in names else one for one in selections)


def _is_daily_limiter(limited: ProviderRateLimited) -> bool:
    """Whether a rate limit means "not today" rather than "in a moment"."""
    wait = limited.retry_after_seconds
    return wait is not None and wait >= SKIP_TODAY_SECONDS


def _openev_event_of(file: OpenEvFile, configured: Event | None) -> Event | None:
    """The event a camp file belongs to: what its own tags say, or what the run was configured with.

    A tag is read only when it is exactly one of the events the domain knows. Anything else is not
    a guess this makes: a camp file filed under the wrong event would be counted in the wrong
    release manifest for the rest of the season.
    """
    for tag in file.tags:
        for event in Event:
            if tag.strip().upper() == str(event).upper():
                return event
    return configured


def _parsed_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


class UnknownSyncEvent(DomainError):
    """A caselist whose event this build does not know, so its archive cannot be imported.

    Not a guess: the event decides whether `Aff` or `Pro` is a legal side, and filing a whole
    archive under the wrong one is worse than importing nothing and saying so.
    """

    def __init__(self, caselist: str) -> None:
        self.caselist = caselist
        super().__init__(
            f"this build does not know which event {caselist!r} debates, so `caselist pull` cannot "
            "import its archive; add the slug prefix to the table in debate_cli.commands.caselist"
        )


class UndatedArchive(DomainError):
    """An archive with no date reached the importer, which files snapshots by date."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"{name} carries no archive date, so it cannot be filed as a snapshot")


def _log_summary(summary: RunSummary) -> None:
    """Counts, slugs and dates. No path, no school, no team code, no token (policy rule 4)."""
    logger.info(
        "caselist sync run",
        extra={
            "run_id": summary.run_id,
            "dry_run": summary.dry_run,
            "succeeded": summary.succeeded,
            "caselists": list(summary.caselists),
            "archives_seen": summary.archives_seen,
            "archives_downloaded": summary.archives_downloaded,
            "openev_downloaded": summary.openev_downloaded,
            "files_imported": summary.files_imported,
            "blobs_stored": summary.blobs_stored,
            "objects_published": summary.objects_published,
            "pending_publish": len(summary.pending_publish),
            "duration_seconds": round(summary.duration_seconds, 3),
            "stages": {str(record.stage): str(record.outcome) for record in summary.stages},
        },
    )
