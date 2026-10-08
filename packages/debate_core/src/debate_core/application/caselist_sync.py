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

The order is download, import, publish, parse, landscape, report, retention. Goal criterion ac1 lists parsing
before publishing; the spec's own description ("the run still completes download, import and
publish before anything optional") is what is implemented, and the session report records the
difference.

## The daily download budget

OpenCaselist limits each user to **5 bulk downloads per day** (`weeklyLimiter` upstream, found by
`v1-e34-t01`), separately from the 10-file-per-minute limit the transport paces itself against.
That ceiling is budgeted in :meth:`CaselistSyncService.plan` across the configured caselists —
decided before anything is fetched rather than discovered when the server says no — and every
bulk download this machine starts is recorded in a ledger, so a second run starts from what is
left rather than from five.

The budget is a **rolling 24 hours**, not a calendar day (`v1-e34-t06`): a download may start only
if fewer than five started in the 24 hours before it. `v1-e34-t01` established the ceiling but not
which day the server counts, and neither does the data-use policy, so any calendar would be a guess
— and a calendar key hands out a fresh five at its midnight, which is twice the limit across a
boundary. It is :class:`~debate_core.integrations.opencaselist.pacing.RequestPacer`'s rule for the
per-minute limit one scale up, and it is conservative against a limiter counting any calendar in
any timezone. See :class:`DownloadLedger`.

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

## What leaves the inbox

Nothing used to: every weekly and camp download stayed after it was imported, and the weeklies are
cumulative, so the inbox grew by the season's whole caselist every week (`v1-e34-t11`). The last
stage of a run, **retention**, removes a download once nothing can need it again. It runs after the
report stage, under the run lock, on every real run — one that downloaded nothing too, which is how
the first run after it shipped cleared the backlog — and a dry run lists what it would remove and
removes nothing. A file goes only when all of these hold:

* **Imported: a manifest on this machine came from these bytes.** A weekly archive's own week has a
  manifest whose `archive_sha256` is the file's digest; a camp download's digest is the
  `archive_sha256` of a row in an OpenEv release manifest. That is also what holds a download
  waiting for `v1-e34-t06`'s import retry: the retry imports exactly the inbox files no manifest
  came from, so no separate hold is needed, and none is kept.
* **Confirmed: that snapshot is in sync in the bucket, as this run checked it.** The report stage's
  comparison for the snapshots this run published; for a snapshot an earlier run imported, a fresh
  comparison by the retention stage itself (:class:`CaselistStatusService`, the same one), never an
  earlier run's word. An environment with no bucket confirms nothing and removes nothing.
* **A camp download: the delivery record holds its digests.** Once its copy is gone the record is
  what lets the next run recognise a camp release as imported or removed (`v1-e34-t07`); without
  it the next run would download the file again.

Anything else stays, and the summary names it with the reason: a download not imported, a snapshot
not confirmed, a camp download the record does not cover, and any file whose name the pull does
not give a download. Nothing is kept longer, the newest week included. The usual reason to keep a
zip is a free re-import after a failed publish, but a zip is removed only after its publish is
confirmed, and a publish reads the local store, never the inbox. The newest weekly is also the
largest, because the weeklies are cumulative. An imported week is `ALREADY_IMPORTED` whether or not
its zip is here (:func:`_decide_archive`, `v1-e30-t09`), and the site keeps the weekly
back-catalogue (ADR-0017), so a removed zip is never fetched again by a pull and can be fetched by
hand if ever needed.

A removal (`caselist remove`, `v1-e30-t09`) also deletes inbox files, the ones holding removed
bytes, under the same lock. The two cannot interleave, and each counts only the files it deleted:
retention judges the inbox as it finds it, after whatever a removal left.

## What is imported

The import stage works from the inbox against the manifests, not from what this run happened to
download (`v1-e34-t06`). Every weekly newer than a caselist's latest manifest that is in the inbox
is imported, whether this run fetched it or an earlier one did, so an archive whose import failed
is imported by the next run without spending a download on it. The same holds for an OpenEv file
in the inbox that its release manifest does not yet record.

A caselist's weeklies are imported oldest first, because the importer classifies each against the
one before it, and **a caselist stops at its first gap**: an import that fails, or an older week
this run did not obtain (the cap deferred it, or its download failed). Everything newer waits in the
inbox for a later run. Importing past a gap would give the newer week a manifest, the older week
would then no longer be newer than the latest manifest, and no run would ever fetch or import it.

## A camp file that was removed

A removal (`caselist remove`, `v1-e30-t07`) puts the file's sha256 on the suppression list and
takes its rows out of the release manifest, so nothing the manifest says marks the camp file as
handled any more. Left alone, every run would fetch it again — or import it again from the inbox —
for the importer to refuse, spending a download from a budget the site's maintainer sets
(`v1-e34-t07`). The run skips it instead, as :attr:`SelectionDecision.SKIPPED_AS_REMOVED`.

**The suppression list is the only record of what was removed.** The list is keyed by sha256, and
the listing gives an id and a path but no digest, so the run needs to know which bytes an id
delivered. :class:`OpenEvDeliveries` remembers that, per id, when an import of it completes: the
download's digest, the digest of its upstream path, and the digest of every member the importer
classified. It holds no removal state at all. Whether an id is removed is decided on every run, by
reading the list — the union of this machine's copy and the bucket's, when there is a bucket — and
asking whether it suppresses every member that id delivered. A removal made on another machine is
therefore honoured as soon as the bucket's copy says so; an `unsuppress` is honoured the same way,
and the file is fetched again. A remembered id whose bytes are neither recorded in the manifest nor
suppressed is reported in the select stage and fetched, never skipped on the memory's word.

What the memory does not know, it cannot use. A camp file this machine never imported, removed
somewhere else, is fetched once; the importer refuses it, the memory records what it delivered, and
the next run skips it. A file still in the inbox is read there instead, so it costs nothing.

**A camp file changes upstream only under a new id.** OpenCaselist has no route that replaces a
file's bytes: `POST /openev` refuses a path that exists, `DELETE /openev/{id}` is the only other
write, and ids are `AUTO_INCREMENT` (`server/v1/controllers/openev/`, `server/v1/db/caselist.sql`,
upstream). A re-uploaded file therefore arrives as a new id, usually at the same path. A removal
covers a camp's later upload of the same file (PM decision, `v1-e34-t07`): the request was about the
material, and a revised file normally still contains it. Such an id is held back as
:attr:`SelectionDecision.SAME_PATH_AS_A_REMOVED_FILE` and logged. If the data-use policy is read the
other way, that decision becomes a download.

## Credentials, and stages that come back later

The local stages need no AWS session. If the operator's SSO session has expired, the S3 adapter
raises :class:`~debate_core.application.errors.StoreCredentialsExpired`; the publish and report
stages are then recorded as **pending** in a small local file, and the next run — or
`caselist pull --publish-pending` — completes them. Nothing that was captured is lost by a login
that timed out overnight.

The one thing the local stages read from the bucket is the removal suppression list: the importers
and the skip of a removed camp file read both copies when there is a bucket. When the bucket's copy
cannot be read for want of a login — credentials missing or expired, and nothing else — they read
this machine's copy alone, and the run says so: `suppression_list_local_copy_only` in the summary
carries the reason, and the select or import stage that fell back adds a sentence to its own. An
access denial or an unreadable list is not a login that timed out, and still fails the import. See
:class:`~debate_core.application.caselist.suppression.LocalFallbackSuppressionList` for why this is
safe while one machine imports, and the condition for revisiting it.

## Which run a `caselist pull` is

:func:`run_pull` chooses between the three things the command can be asked for — a dry run, a
whole run, or completing the publishes an earlier run deferred — and runs the two that write
anything inside :class:`~debate_core.application.sync_runs.SyncRunMonitor`. It takes a factory for
this service rather than the service itself, because building it is where an API this installation
has not turned on is refused, and that refusal has to be recorded like any other.

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
import hashlib
import json
import logging
import os
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Final, Protocol, Self, cast

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
from debate_core.application.caselist.pipeline import STORED_CLASSIFICATIONS, Classification
from debate_core.application.caselist.publish_plan import manifest_prefix, snapshot_of_manifest_key
from debate_core.application.caselist.publish_service import (
    CaselistPublishService,
    NothingToPublish,
    SourceResult,
)
from debate_core.application.caselist.status_service import CaselistStatusService, NoCaselistEvidence
from debate_core.application.caselist.suppression import LocalFallbackSuppressionList, load_suppression_state
from debate_core.application.errors import (
    DomainError,
    ProviderRateLimited,
    StoreAccessDenied,
    StoreCredentialsExpired,
    UnreadableArchive,
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
from debate_core.application.ports.suppression import SuppressionAction, SuppressionList, SuppressionState
from debate_core.domain.caselist import CASELIST_SLUG_PATTERN, Acquisition, Event

if TYPE_CHECKING:  # pragma: no cover - sync_runs imports this module, so its types are named only
    from debate_core.application.sync_runs import SyncRunMonitor, SyncRunRecord

__all__ = [
    "BULK_DOWNLOAD_WINDOW",
    "DEFAULT_BULK_DOWNLOADS_PER_DAY",
    "INBOX_PARTIAL_DIRECTORY",
    "LEGACY_DOWNLOAD_LEDGER_FILENAME",
    "LOCK_FILENAME",
    "OPENEV_DELIVERIES_FILENAME",
    "PENDING_WORK_FILENAME",
    "RUN_SUMMARY_SCHEMA_VERSION",
    "SKIP_TODAY_SECONDS",
    "ArchiveReader",
    "ArchiveSelection",
    "CaselistParseStage",
    "CaselistSyncService",
    "DownloadLedger",
    "InboxFileKind",
    "InboxFileVerdict",
    "InboxRetention",
    "LandscapeStage",
    "LandscapeStageResult",
    "NoCaselistsConfigured",
    "OpenEvDeliveries",
    "OpenEvDelivery",
    "OpenEvSelection",
    "ParseStageResult",
    "PendingWork",
    "PulledRun",
    "RetentionDecision",
    "RunSummary",
    "SelectionDecision",
    "StageOutcome",
    "StageRecord",
    "SyncPlan",
    "SyncRunInProgress",
    "SyncStage",
    "UndatedArchive",
    "UnknownSyncEvent",
    "inbox_files",
    "openev_id_of_inbox_name",
    "run_pull",
    "weekly_archive_of_inbox_name",
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
DOWNLOAD_LEDGER_FILENAME: Final = "caselist-sync-download-starts.json"
"""When each bulk download started, for the rolling window. See :class:`DownloadLedger`."""

LEGACY_DOWNLOAD_LEDGER_FILENAME: Final = "caselist-sync-downloads.json"
"""The calendar-day ledger builds before `v1-e34-t06` kept: `{"date": ..., "bulk_downloads": N}`.

Read, never written. See :class:`DownloadLedger` for why it is still read, and how.
"""

OPENEV_DELIVERIES_FILENAME: Final = "caselist-sync-openev-deliveries.json"
"""What each OpenEv id delivered when this machine imported it. See :class:`OpenEvDeliveries`."""

OPENEV_DELIVERIES_SCHEMA_VERSION: Final = 1

BULK_DOWNLOAD_WINDOW: Final = timedelta(hours=24)
"""How far back the daily bulk-download ceiling counts: a rolling day, not a calendar one."""

DOWNLOAD_LEDGER_SCHEMA_VERSION: Final = 1

RUN_SUMMARY_SCHEMA_VERSION: Final = 2
"""The shape of :meth:`RunSummary.as_json`.

Version 2 (`v1-e34-t06`) reports the download window as `bulk_download_window_start` and
`bulk_downloads_spent_in_window`. The summaries written before it carry no version and report
`bulk_downloads_spent_today` instead; nothing reads them back, and `caselist runs` reads the run
log (:mod:`debate_core.application.sync_runs`), whose records have neither field.
"""
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

    RETENTION = "retention"
    """Remove imported downloads whose snapshot the bucket confirms from the inbox (`v1-e34-t11`)."""


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
    """In the inbox and not yet in a manifest: imported from there, without fetching it again."""

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

    SKIPPED_AS_REMOVED = "skipped_as_removed"
    """An OpenEv file every member of which the removal suppression list stops.

    Fetching it would only hand the importer bytes it must refuse. Decided from the list on every
    run; see "A camp file that was removed" in this module's docstring.
    """

    SAME_PATH_AS_A_REMOVED_FILE = "same_path_as_a_removed_file"
    """A new OpenEv id at the upstream path of a camp file that was removed.

    How OpenEv re-publishes a file, since nothing upstream replaces bytes under an id. Held back
    rather than fetched: a removal covers a camp's later upload of the same file (PM decision,
    `v1-e34-t07`), and the run says which id it held back.
    """

    SUPPRESSION_LIST_UNREADABLE = "suppression_list_unreadable"
    """Fetched by this machine before, recorded nowhere now, and the list could not be read.

    It may have been removed, and nothing can say until the list can be read, so it is left for a
    run that can read it rather than fetched on a guess.
    """


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
    note: str | None = None
    """Why the decision deserves an operator's eye, when it does. Ids and codes only, never a path."""

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
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class SyncPlan:
    """What a run intends to do, worked out from listings alone, before anything is fetched."""

    caselists: tuple[str, ...]
    archives: tuple[ArchiveSelection, ...]
    openev: tuple[OpenEvSelection, ...]
    bulk_downloads_allowed: int
    """What was left of the five when this plan was made."""

    bulk_downloads_spent_in_window: int
    """Bulk downloads started in the 24 hours before this plan was made."""

    bulk_download_window_start: datetime
    """Where those 24 hours began: the plan's own time less :data:`BULK_DOWNLOAD_WINDOW`."""

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
# What leaves the inbox
# ------------------------------------------------------------------------------------------------


class RetentionDecision(StrEnum):
    """What the retention stage decided about one inbox file. See "What leaves the inbox"."""

    REMOVE = "remove"
    """Imported, its snapshot confirmed in the bucket, and for a camp download, recorded."""

    NOT_IMPORTED = "not_imported"
    """No manifest on this machine came from these bytes: the next pull imports it, or none will."""

    NOT_CONFIRMED = "not_confirmed"
    """Imported, and its snapshot is not in sync in the bucket, or the bucket could not be checked."""

    NO_DELIVERY_RECORD = "no_delivery_record"
    """A camp download the OpenEv delivery record does not hold the digests of."""

    UNCLASSIFIED = "unclassified"
    """A file whose name the pull does not give a download, or one that cannot be read."""


_KEPT_BECAUSE: Final = {
    RetentionDecision.NOT_IMPORTED: "not imported",
    RetentionDecision.NOT_CONFIRMED: "publish not confirmed in the bucket",
    RetentionDecision.NO_DELIVERY_RECORD: "the delivery record does not hold its digests",
    RetentionDecision.UNCLASSIFIED: "not a download the pull names",
}


class InboxFileKind(StrEnum):
    """What an inbox file is, by the name `caselist pull` gave it."""

    WEEKLY_ARCHIVE = "weekly_archive"
    CAMP_DOWNLOAD = "camp_download"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class InboxFileVerdict:
    """One inbox file, as the run summary names it, and what retention decided about it.

    `name` is a weekly archive's caselist and date (`hsld26 2026-09-15`), or for anything else the
    first twelve hex digits of its SHA-256: a camp download's file name is a camp's title, and a
    name somebody gave a file by hand can say anything (`docs/policies/caselist-data-use.md` rule 4).
    """

    name: str
    kind: InboxFileKind
    decision: RetentionDecision
    byte_size: int
    path: Path
    """Where it is. Never in the summary: the inbox's own path is the operator's home directory."""

    def as_json(self) -> dict[str, object]:
        body: dict[str, object] = {"name": self.name, "kind": str(self.kind), "bytes": self.byte_size}
        if self.decision is not RetentionDecision.REMOVE:
            body["reason"] = str(self.decision)
        return body


@dataclass(frozen=True, slots=True)
class InboxRetention:
    """What the retention stage removed and kept, or for a dry run would remove and would keep."""

    dry_run: bool
    removed: tuple[InboxFileVerdict, ...] = ()
    """Removed; for a dry run, what a real run would remove now."""
    kept: tuple[InboxFileVerdict, ...] = ()
    failed: tuple[tuple[InboxFileVerdict, str], ...] = ()
    """Decided removable, and the removal raised: the file and the error's class."""
    once_imported: tuple[str, ...] = ()
    """A dry run only: weeklies this run would import, and so remove once the bucket confirms them."""
    camp_downloads_once_imported: int = 0

    @property
    def bytes_freed(self) -> int:
        return sum(one.byte_size for one in self.removed)

    def as_json(self) -> dict[str, object]:
        gone = [one.as_json() for one in self.removed]
        return {
            "dry_run": self.dry_run,
            "removed": [] if self.dry_run else gone,
            "bytes_freed": 0 if self.dry_run else self.bytes_freed,
            "would_remove": gone if self.dry_run else [],
            "bytes_would_free": self.bytes_freed if self.dry_run else 0,
            "kept": [one.as_json() for one in self.kept],
            "not_removed_after_an_error": [{**one.as_json(), "error": error} for one, error in self.failed],
            "would_remove_once_imported": list(self.once_imported),
            "camp_downloads_would_remove_once_imported": self.camp_downloads_once_imported,
        }

    def sentence(self) -> str:
        """The stage's reason: every file by name, the bytes, and why each kept file stays."""
        if self.dry_run:
            head = f"would remove {len(self.removed)} file(s), {self.bytes_freed} bytes"
        else:
            head = f"{len(self.removed)} file(s) removed, {self.bytes_freed} bytes freed"
        parts = [head + (f": {_named(self.removed)}" if self.removed else "")]
        if self.kept:
            by_reason: dict[RetentionDecision, list[InboxFileVerdict]] = {}
            for one in self.kept:
                by_reason.setdefault(one.decision, []).append(one)
            parts.append(
                f"{len(self.kept)} kept: "
                + "; ".join(
                    f"{_named(group)} ({_KEPT_BECAUSE[reason]})" for reason, group in by_reason.items()
                )
            )
        if self.failed:
            parts.append(
                f"{len(self.failed)} could not be removed: "
                + "; ".join(f"{_named([one])} ({error})" for one, error in self.failed)
            )
        if self.once_imported or self.camp_downloads_once_imported:
            later = list(self.once_imported)
            if self.camp_downloads_once_imported:
                later.append(f"{self.camp_downloads_once_imported} camp download(s)")
            parts.append(
                "once this run has imported them and the bucket confirms their publish, also "
                + ", ".join(later)
            )
        return "; ".join(parts)


_MAX_NAMED: Final = 250
"""Names one retention sentence lists before it says how many more; a whole season is about 120."""


def _named(files: Sequence[InboxFileVerdict]) -> str:
    """Weeklies by caselist and date, camp downloads and other files by count and SHA-256 prefix."""
    weeklies = [one.name for one in files if one.kind is InboxFileKind.WEEKLY_ARCHIVE]
    camp = [one.name for one in files if one.kind is InboxFileKind.CAMP_DOWNLOAD]
    other = [one.name for one in files if one.kind is InboxFileKind.OTHER]
    parts: list[str] = []
    if weeklies:
        parts.append(_listed(weeklies))
    if camp:
        parts.append(f"{len(camp)} camp download(s), {_listed(camp)}")
    if other:
        parts.append(f"{len(other)} other file(s), {_listed(other)}")
    return ", ".join(parts)


def _listed(names: Sequence[str]) -> str:
    shown = ", ".join(names[:_MAX_NAMED])
    return shown if len(names) <= _MAX_NAMED else f"{shown} and {len(names) - _MAX_NAMED} more"


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
    """When this machine started each bulk archive download, counted over a rolling 24 hours.

    A download may start at `now` only if fewer than `limit` started in `(now - 24h, now]`: the
    rule :class:`~debate_core.integrations.opencaselist.pacing.RequestPacer` applies to the
    per-minute limit, one scale up (see this module's docstring). Five at `T` are still counted at
    `T + 23h59m` and released at `T + 24h`. A start later than `now` counts too, so a clock set
    back cannot hand out an allowance.

    The file is `{"schema_version": 1, "bulk_download_starts": [<ISO 8601 UTC>, ...]}`, pruned to
    the window on every write.

    ## Reading what it cannot trust

    An unreadable ledger does not say "nothing spent", because nothing spent means five available.
    A file here that is not a ledger this class wrote is read as `limit` downloads started when
    the file was last written (its mtime): fully spent for 24 hours, then released.

    The calendar-day ledger of the builds before `v1-e34-t06`
    (:data:`LEGACY_DOWNLOAD_LEDGER_FILENAME`) is still read, and never written. Its
    `{"date": ..., "bulk_downloads": N}` becomes `N` downloads started at its mtime: every write
    replaced the file, so each of the `N` started at or before that moment, and counting them there
    keeps them in the window for as long as any of them could be. It is read on every run rather than
    migrated once, because an installed build still on the old format writes it — `v1-e30-t06`'s
    backfill runs from one — and what that build spends must still count against this one. An old
    build does not read this file, so it may spend what this one already has; the server's own
    limiter absorbs that as a deferral (:data:`SKIP_TODAY_SECONDS`), which is a wasted run and not
    a breach.
    """

    def __init__(
        self,
        path: Path,
        *,
        limit: int = DEFAULT_BULK_DOWNLOADS_PER_DAY,
        legacy_path: Path | None = None,
    ) -> None:
        self.path = Path(path)
        self.limit = limit
        self.legacy_path = Path(legacy_path) if legacy_path is not None else None

    @staticmethod
    def window_start(now: datetime) -> datetime:
        """The start of the 24 hours a download at `now` is counted against. Not itself inside it."""
        return now - BULK_DOWNLOAD_WINDOW

    def starts(self) -> tuple[datetime, ...]:
        """Every download start this ledger and the legacy one account for, oldest first."""
        recorded = list(self._own_starts())
        if self.legacy_path is not None:
            recorded.extend(self._legacy_starts(self.legacy_path))
        return tuple(sorted(recorded))

    def spent_in_window(self, now: datetime) -> int:
        """Downloads started in the 24 hours before `now`, or after it."""
        since = self.window_start(now)
        return sum(1 for started in self.starts() if started > since)

    def remaining_at(self, now: datetime) -> int:
        return max(self.limit - self.spent_in_window(now), 0)

    def record(self, started_at: datetime) -> None:
        """Add one download that started at `started_at`. A dry run never calls this."""
        _require_aware(started_at)
        since = self.window_start(started_at)
        kept = [started for started in self._own_starts() if started > since]
        kept.append(started_at)
        _write_json(
            self.path,
            {
                "schema_version": DOWNLOAD_LEDGER_SCHEMA_VERSION,
                "bulk_download_starts": [started.astimezone(UTC).isoformat() for started in sorted(kept)],
            },
        )

    def _own_starts(self) -> tuple[datetime, ...]:
        if not self.path.is_file():
            return ()
        starts = _parsed_starts(_read_json_object(self.path))
        if starts is None:
            logger.warning(
                "caselist sync: the download ledger is not one this build wrote; counting it as spent"
            )
            return self._spent_when_written(self.path, self.limit)
        return starts

    def _legacy_starts(self, path: Path) -> tuple[datetime, ...]:
        if not path.is_file():
            return ()
        body = _read_json_object(path)
        spent = body.get("bulk_downloads") if body is not None else None
        if body is None or not isinstance(body.get("date"), str) or not isinstance(spent, int) or spent < 0:
            logger.warning("caselist sync: the old download ledger is unreadable; counting it as spent")
            return self._spent_when_written(path, self.limit)
        return self._spent_when_written(path, spent)

    @staticmethod
    def _spent_when_written(path: Path, downloads: int) -> tuple[datetime, ...]:
        """`downloads` starts at the moment `path` was last written, the latest any of them can be."""
        try:
            written = datetime.fromtimestamp(path.stat().st_mtime, UTC)
        except OSError:  # gone since it was found: there is nothing left to count
            return ()
        return (written,) * downloads


def _parsed_starts(body: dict[str, object] | None) -> tuple[datetime, ...] | None:
    """The starts a ledger this class wrote records, or `None` if `body` is not one."""
    if body is None or body.get("schema_version") != DOWNLOAD_LEDGER_SCHEMA_VERSION:
        return None
    raw = body.get("bulk_download_starts")
    if not isinstance(raw, list):
        return None
    starts: list[datetime] = []
    for value in cast("list[object]", raw):
        if not isinstance(value, str):
            return None
        try:
            started = datetime.fromisoformat(value)
        except ValueError:
            return None
        if started.tzinfo is None:
            return None
        starts.append(started)
    return tuple(starts)


def _require_aware(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("a download start must be timezone-aware")
    return moment


@dataclass(frozen=True, slots=True)
class OpenEvDelivery:
    """What one OpenEv id's download held when this machine last imported it. Digests only."""

    download_sha256: str
    """The download itself: the single document, or the camp release's zip."""

    path_sha256: str | None
    """The SHA-256 of the file's upstream path (`OpenEvFile.path`), never the path itself."""

    member_sha256: frozenset[str]
    """Every member the importer classified, stored or refused. Junk it skipped has no digest."""

    def as_json(self) -> dict[str, object]:
        return {
            "download_sha256": self.download_sha256,
            "path_sha256": self.path_sha256,
            "member_sha256": sorted(self.member_sha256),
        }


class OpenEvDeliveries:
    """Which bytes each OpenEv id delivered, so a removed one can be recognised before it is fetched.

    The suppression list names digests and the OpenEv listing names ids, and a digest is only known
    once the bytes are in hand. This file joins the two for every id this machine has imported:
    `{"schema_version": 1, "deliveries": {"<openev id>": {"download_sha256": ..., "path_sha256":
    ..., "member_sha256": [...]}}}`.

    **It records no removal.** There is no field here that says an id was removed, suppressed or
    refused, so it cannot disagree with the suppression list about any of those: whether an id is
    removed is asked of the list on every run (:meth:`CaselistSyncService._select_openev`). What it
    records is a fact about upstream — these bytes came from that id — which no removal and no
    un-suppress changes. Like the suppression list it holds no name: digests and ids only.

    Written after each import of an OpenEv download completes, never by a dry run, and by a removal
    that deletes an id's copy from the inbox when this record does not yet know what the id
    delivered (`v1-e30-t09`, :meth:`remember_if_unknown`): the inbox copy was the only other place
    those digests could be read from, and without them the next run would fetch the removed file
    again. A file that cannot be read is treated as empty, with a warning: what it would have said is
    recovered by the next download of each id, which costs that download once and nothing worse,
    since the importer refuses a removed file on its own.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def read(self) -> dict[int, OpenEvDelivery]:
        """Every id this machine has imported, and what it delivered."""
        if not self.path.is_file():
            return {}
        deliveries = _parsed_deliveries(_read_json_object(self.path))
        if deliveries is None:
            logger.warning(
                "caselist sync: the OpenEv delivery record is not one this build wrote; ignoring it, "
                "so a removed camp file this machine cannot recognise may be fetched once more"
            )
            return {}
        return deliveries

    def remember_if_unknown(self, openev_id: int, delivery: OpenEvDelivery) -> bool:
        """Record `delivery` for `openev_id` unless the record already holds that id. True if it wrote.

        What an import recorded is never replaced: it carries the upstream path's digest, which a
        removal reading the bytes off the inbox cannot know.
        """
        if openev_id in self.read():
            return False
        self.record(openev_id, delivery)
        return True

    def record(self, openev_id: int, delivery: OpenEvDelivery) -> None:
        """Remember what `openev_id` delivered, replacing anything remembered for it before."""
        deliveries = self.read()
        deliveries[openev_id] = delivery
        _write_json(
            self.path,
            {
                "schema_version": OPENEV_DELIVERIES_SCHEMA_VERSION,
                "deliveries": {str(one): deliveries[one].as_json() for one in sorted(deliveries)},
            },
        )


_SHA256_HEX: Final = re.compile(r"^[0-9a-f]{64}$")


def _parsed_deliveries(body: dict[str, object] | None) -> dict[int, OpenEvDelivery] | None:
    """The deliveries a record :class:`OpenEvDeliveries` wrote holds, or `None` if `body` is not one."""
    if body is None or body.get("schema_version") != OPENEV_DELIVERIES_SCHEMA_VERSION:
        return None
    raw = body.get("deliveries")
    if not isinstance(raw, dict):
        return None
    deliveries: dict[int, OpenEvDelivery] = {}
    for key, value in cast("dict[str, object]", raw).items():
        if not key.isdigit() or not isinstance(value, dict):
            return None
        fields = cast("dict[str, object]", value)
        download = fields.get("download_sha256")
        path = fields.get("path_sha256")
        members = fields.get("member_sha256")
        if (
            not _is_sha256(download)
            or not (path is None or _is_sha256(path))
            or not isinstance(members, list)
        ):
            return None
        listed = cast("list[object]", members)
        if not all(_is_sha256(one) for one in listed):
            return None
        deliveries[int(key)] = OpenEvDelivery(
            download_sha256=cast("str", download),
            path_sha256=cast("str | None", path),
            member_sha256=frozenset(cast("list[str]", listed)),
        )
    return deliveries


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256_HEX.match(value) is not None


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
    """What was left of the five when the run planned."""

    bulk_downloads_spent_in_window: int = 0
    """Bulk downloads started in the 24 hours before the run planned, by this run's ledger."""

    bulk_download_window_start: datetime | None = None
    """Where those 24 hours began, or `None` when the run never planned (`--publish-pending`)."""

    suppression_list_local_copy_only: str | None = None
    """Why the suppression list was read from this machine's copy alone, or `None` if it was not.

    Set when the bucket's copy needed a login the run did not have; see "Credentials, and stages
    that come back later" in the module docstring.
    """

    inbox_retention: InboxRetention | None = None
    """What the retention stage removed and kept, or `None` when it judged nothing (`v1-e34-t11`)."""

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
    def openev_skipped_as_removed(self) -> int:
        """Camp files not fetched because the suppression list stops everything they deliver."""
        return sum(1 for one in self.openev if one.decision is SelectionDecision.SKIPPED_AS_REMOVED)

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
            "schema_version": RUN_SUMMARY_SCHEMA_VERSION,
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
            "openev_skipped_as_removed": self.openev_skipped_as_removed,
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
            "bulk_downloads_spent_in_window": self.bulk_downloads_spent_in_window,
            "bulk_download_window_start": (
                self.bulk_download_window_start.isoformat() if self.bulk_download_window_start else None
            ),
            "suppression_list_local_copy_only": self.suppression_list_local_copy_only,
            "inbox_retention": self.inbox_retention.as_json() if self.inbox_retention is not None else None,
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
    bulk_downloads_spent_in_window: int = 0
    bulk_download_window_start: datetime | None = None
    suppression_list_local_copy_only: str | None = None
    confirmed: set[PendingSnapshot] = field(default_factory=lambda: set[PendingSnapshot]())
    """Snapshots the report stage found in sync in the bucket this run."""
    inbox_retention: InboxRetention | None = None

    def record(self, stage: SyncStage, outcome: StageOutcome, reason: str | None = None) -> None:
        self.stages.append(StageRecord(stage=stage, outcome=outcome, reason=reason))

    def add_to_reason(self, stage: SyncStage, sentence: str) -> None:
        """Append `sentence` to the reason the latest record of `stage` gives."""
        for index in range(len(self.stages) - 1, -1, -1):
            record = self.stages[index]
            if record.stage is stage:
                reason = f"{record.reason}; {sentence}" if record.reason else sentence
                self.stages[index] = StageRecord(stage=stage, outcome=record.outcome, reason=reason)
                return


@dataclass(frozen=True, slots=True)
class _JudgedLocally:
    """One inbox file after the retention checks that need no bucket. Private to the stage."""

    name: str
    kind: InboxFileKind
    byte_size: int
    path: Path
    kept_because: RetentionDecision | None
    """The first local check it failed, or `None` when only the bucket's confirmation is left."""
    snapshots: frozenset[PendingSnapshot] = frozenset()
    """The snapshots its bytes were imported into, which the bucket must hold in sync."""


@dataclass(frozen=True, slots=True)
class _ImportQueue:
    """One caselist's weeklies for the import stage: those to import in order, and those behind a gap."""

    ready: tuple[tuple[ArchiveSelection, Path], ...]
    waiting: int
    """In the inbox, and newer than a week this run could not import or did not obtain."""


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
            suppression=container.suppression_list(),  # the importers' list: both copies
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
        state_dir: Where the run lock, the pending-work file, the download ledger, the OpenEv
            delivery record and the run summaries live. The environment's data directory.
        suppression: The removal suppression list, read to skip camp files a removal has taken
            out. Required, with no default, and it should be the very list the importers were
            built with — the union of this machine's copy and the bucket's when there is a bucket —
            so the skip and the importers' refusal can never read two different lists.
        publisher: The S3 publisher (`v1-e30-t05`), or `None` for an environment with no bucket.
        status: The local-against-bucket comparison used by the report stage, or `None`.
        parse: The parse pipeline (`v1-e31-t06`), or `None` — the normal case today.
        landscape: Landscape regeneration (`v1-e32-t05`), or `None` — the normal case today.
        openev_event: The event to file OpenEv files under when their own tags do not say.
        openev_year: The OpenEv release year to list, or `None` for the API's current year.
        bulk_downloads_per_day: The upstream ceiling; never raised above
            :data:`DEFAULT_BULK_DOWNLOADS_PER_DAY`.
        clock: Returns an aware `datetime`; the run's timestamps and the download window come from it.
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
        suppression: SuppressionList,
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
            legacy_path=self._state_dir / LEGACY_DOWNLOAD_LEDGER_FILENAME,
        )
        self._pending = PendingWork(self._state_dir / PENDING_WORK_FILENAME)
        self._suppression = suppression
        self._deliveries = OpenEvDeliveries(self._state_dir / OPENEV_DELIVERIES_FILENAME)

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
        now = self._clock()
        allowed = self._ledger.remaining_at(now)
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
            bulk_downloads_spent_in_window=self._ledger.spent_in_window(now),
            bulk_download_window_start=self._ledger.window_start(now),
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
            fallbacks = self._suppression_fallbacks()
            plan = await self._selection_stage(caselists, tally)
            self._note_local_copy_only(tally, SyncStage.SELECT, since=fallbacks)
            if dry_run:
                self._plan_remaining_stages(plan, tally)
            else:
                await self._execute(plan, tally)
            await self._retention_stage(tally, plan=plan, dry_run=dry_run)
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
            tally.record(
                SyncStage.RETENTION,
                StageOutcome.SKIPPED,
                "publish-pending removes nothing from the inbox; the next pull does",
            )
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
            now = self._clock()
            plan = SyncPlan(
                caselists=tuple(caselists),
                archives=(),
                openev=(),
                bulk_downloads_allowed=0,
                bulk_downloads_spent_in_window=self._ledger.spent_in_window(now),
                bulk_download_window_start=self._ledger.window_start(now),
            )
            tally.record(SyncStage.SELECT, StageOutcome.SKIPPED, f"OpenCaselist is rate limiting: {limited}")
            tally.archives, tally.openev = plan.archives, plan.openev
            return plan
        tally.archives, tally.openev = plan.archives, plan.openev
        tally.bulk_downloads_allowed = plan.bulk_downloads_allowed
        tally.bulk_downloads_spent_in_window = plan.bulk_downloads_spent_in_window
        tally.bulk_download_window_start = plan.bulk_download_window_start
        fetch = len(plan.archives_to_download) + len(plan.openev_to_download)
        deferred = sum(1 for one in plan.archives if one.deferred_by_cap)
        listed = f"{len(plan.archives)} archive(s) and {len(plan.openev)} OpenEv file(s) listed; "
        # What the run counted against, so nobody has to open the ledger to see it (ac2b).
        window = (
            f"{plan.bulk_downloads_spent_in_window} of {self._ledger.limit} bulk download(s) spent in "
            f"the 24 hours from {plan.bulk_download_window_start.astimezone(UTC):%Y-%m-%d %H:%M} UTC, "
            f"{plan.bulk_downloads_allowed} left"
        )
        if deferred:
            wanted = fetch + deferred
            detail = (
                f"{listed}{fetch} to fetch of {wanted} wanted, {deferred} deferred by the daily "
                f"download cap; {window}"
            )
        else:
            detail = f"{listed}{fetch} to fetch; {window}"
        tally.record(SyncStage.SELECT, StageOutcome.COMPLETED, detail + _removal_sentence(plan.openev))
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
        """Decide about every OpenEv camp file the API lists for the configured year.

        "Already imported" is decided against what the release manifest records, not against the
        name the sync would give the file (`v1-e34-t06` ac3): a camp file imported by hand through
        `caselist import-openev` is recorded under its own path. See :func:`_held_openev_ids`. A
        file the manifest does not record is then judged against the suppression list before it is
        fetched or imported from the inbox (`v1-e34-t07`): see :meth:`_judge_unrecorded`.
        """
        files = await self._source.list_openev(year=self._openev_year)
        placed: list[tuple[OpenEvFile, int, Event | None]] = []
        by_release: dict[tuple[int, Event], list[OpenEvFile]] = {}
        for file in files:
            event = _openev_event_of(file, self._openev_event)
            year = file.year or self._openev_year or self._clock().year
            placed.append((file, year, event))
            if event is not None:
                by_release.setdefault((year, event), []).append(file)
        recorded = {release: self._recorded_openev(*release) for release in by_release}
        held = {
            release: _held_openev_ids(listed, recorded[release].paths)
            for release, listed in by_release.items()
        }
        remembered = self._deliveries.read()
        suppression = _SuppressionReadOnce(self._suppression)
        selections: list[OpenEvSelection] = []
        for file, year, event in placed:
            inbox_name = openev_inbox_name(file)
            note: str | None = None
            if event is None:
                decision = SelectionDecision.NO_EVENT_CONFIGURED
            elif file.openev_id in held[(year, event)]:
                decision = SelectionDecision.ALREADY_IMPORTED
            else:
                release = recorded[(year, event)]
                in_inbox = inbox_name in inbox_names
                inbox_digest = _digest_of(self._inbox / inbox_name) if in_inbox else None
                if inbox_digest is not None and inbox_digest in release.download_digests:
                    # Imported already: a manifest row came from these very bytes (a camp release
                    # that is a zip records its members, not its own name).
                    decision = SelectionDecision.ALREADY_IMPORTED
                else:
                    judged, note = await self._judge_unrecorded(
                        file,
                        release,
                        remembered,
                        suppression,
                        in_inbox=(self._inbox / inbox_name, inbox_digest) if inbox_digest else None,
                    )
                    # Otherwise in the inbox, its import failed or never ran, and this run imports
                    # it (v1-e34-t06 ac1); or it is new, and this run fetches it.
                    decision = judged or (
                        SelectionDecision.ALREADY_IN_INBOX if in_inbox else SelectionDecision.DOWNLOAD
                    )
            selections.append(
                OpenEvSelection(
                    openev_id=file.openev_id,
                    inbox_name=inbox_name,
                    year=year,
                    event=event,
                    decision=decision,
                    file=file,
                    note=note,
                )
            )
        return selections

    async def _judge_unrecorded(
        self,
        file: OpenEvFile,
        release: _RecordedOpenEv,
        remembered: Mapping[int, OpenEvDelivery],
        suppression: _SuppressionReadOnce,
        *,
        in_inbox: tuple[Path, str] | None,
    ) -> tuple[SelectionDecision | None, str | None]:
        """Whether a camp file the manifest does not record was removed, and so must not be fetched.

        Returns a decision, or `None` to fetch it (or import it from the inbox) as before, and a
        note for the operator. The suppression list decides; the delivery record and the inbox only
        say which digests to ask it about (see "A camp file that was removed" in the module
        docstring):

        * Every member this id delivered is suppressed: `SKIPPED_AS_REMOVED`.
        * Every member is recorded in the release manifest or suppressed — a camp release some of
          whose members were removed: `ALREADY_IMPORTED`.
        * A remembered id whose bytes are neither: fetched, with a note. The usual cause is an
          `unsuppress`, which is why it is fetched rather than skipped on the record's word.
        * An id never seen, at the upstream path of a remembered id whose members are all
          suppressed: `SAME_PATH_AS_A_REMOVED_FILE`, a policy default.

        With a list that cannot be read, nothing here can tell removed from not: a remembered id or
        a re-upload is left for a later run, and a file in the inbox goes on to an import that will
        meet the same unreadable list and fail with its own reason.
        """
        delivery = remembered.get(file.openev_id)
        from_record = delivery is not None
        if delivery is None and in_inbox is not None:
            delivery = self._delivery_in_inbox(*in_inbox)
        if delivery is not None and delivery.member_sha256:
            members = delivery.member_sha256
            state = await suppression.state()
            if state is None:
                if members <= release.stored_digests:
                    return SelectionDecision.ALREADY_IMPORTED, None
                return (SelectionDecision.SUPPRESSION_LIST_UNREADABLE if from_record else None), None
            if all(state.suppresses_source(one) for one in members):
                return SelectionDecision.SKIPPED_AS_REMOVED, None
            recorded = members & release.stored_digests
            if recorded and all(one in recorded or state.suppresses_source(one) for one in members):
                return SelectionDecision.ALREADY_IMPORTED, None
            if not from_record:
                return None, None
            lifted = any(
                (latest := state.latest.get(one)) is not None
                and latest.action is SuppressionAction.UNSUPPRESS
                for one in members
            )
            note = (
                "fetched by this machine before; neither recorded in the release manifest nor "
                "suppressed now" + (", its suppression having been lifted" if lifted else "")
            )
            logger.warning("caselist sync: OpenEv file %d was %s; fetching it again", file.openev_id, note)
            return None, note
        if delivery is None:
            path = _path_digest(file.path)
            earlier = [
                one
                for openev_id, one in remembered.items()
                if openev_id != file.openev_id and one.path_sha256 == path and one.member_sha256
            ]
            if not earlier:
                return None, None
            state = await suppression.state()
            if state is None:
                return SelectionDecision.SUPPRESSION_LIST_UNREADABLE, None
            if any(all(state.suppresses_source(member) for member in one.member_sha256) for one in earlier):
                note = "a new id at the upstream path of a camp file that was removed; the removal covers it"
                logger.warning("caselist sync: OpenEv file %d is %s", file.openev_id, note)
                return SelectionDecision.SAME_PATH_AS_A_REMOVED_FILE, note
        return None, None

    def _delivery_in_inbox(self, path: Path, digest: str) -> OpenEvDelivery | None:
        """What a download still in the inbox delivered, read from its bytes: a zip's members, or itself.

        `None` for a zip that cannot be read, which the import will then refuse with its reason.
        """
        if path.suffix.lower() != ".zip":
            return OpenEvDelivery(download_sha256=digest, path_sha256=None, member_sha256=frozenset({digest}))
        try:
            members = frozenset(
                entry.sha256 for entry in self._read_archive(path) if isinstance(entry, ArchiveMember)
            )
        except (DomainError, OSError):
            return None
        return OpenEvDelivery(download_sha256=digest, path_sha256=None, member_sha256=members)

    def _recorded_openev(self, year: int, event: Event) -> _RecordedOpenEv:
        """What the release's manifest already records, for the "already imported" checks.

        Every row with a classification is a stored member. A member the removal suppression list
        stops has no row at all (`v1-e30-t07`), and a removal takes the rows of the file it removes
        out, so a removed camp file is not recognised from here: it is judged against the list
        (:meth:`_judge_unrecorded`). A skipped member (macOS junk such as `__MACOSX/…/._<name>.docx`)
        has a row with no classification; it is not a camp file, and its name can read like one. Nor
        does its row say the download it came from was imported: a camp release whose every file
        was removed keeps its `.DS_Store` row, and that row alone must not make it "already
        imported".
        """
        return self._recorded_openev_at(openev_manifest_key(year, event))

    def _recorded_openev_at(self, key: str) -> _RecordedOpenEv:
        """:meth:`_recorded_openev` for the release manifest at `key`."""
        paths: set[str] = set()
        stored: set[str] = set()
        digests: set[str] = set()
        for line in read_manifest_lines(self._manifest_path(key)):
            try:
                row: object = json.loads(line)
            except ValueError:
                continue
            if not isinstance(row, dict):
                continue
            fields = cast("dict[str, object]", row)
            if fields.get("classification") is None:
                continue
            path = fields.get("path")
            if isinstance(path, str):
                paths.add(path)
            sha256 = fields.get("sha256")
            if fields.get("classification") in _STORED_CLASSIFICATION_NAMES and isinstance(sha256, str):
                stored.add(sha256)
            download = fields.get("archive_sha256")
            if isinstance(download, str):
                digests.add(download)
        return _RecordedOpenEv(
            paths=frozenset(paths), stored_digests=frozenset(stored), download_digests=frozenset(digests)
        )

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
        in_inbox = sum(
            1 for one in (*plan.archives, *plan.openev) if one.decision is SelectionDecision.ALREADY_IN_INBOX
        )
        tally.record(
            SyncStage.DOWNLOAD,
            StageOutcome.PLANNED,
            f"would download {fetch} file(s) into {self._inbox}",
        )
        tally.record(
            SyncStage.IMPORT,
            StageOutcome.PLANNED,
            f"would import {fetch} downloaded file(s) and {in_inbox} already in the inbox, oldest first, "
            "and write their manifests",
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
        fallbacks = self._suppression_fallbacks()
        await self._import_stage(tally)
        self._note_local_copy_only(tally, SyncStage.IMPORT, since=fallbacks)
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
            started = self._clock()
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
            # Recorded even when the bytes were `already_present`: the client streamed the whole
            # archive before it could tell, and the server counted the download.
            self._ledger.record(started)

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
        """Import what is in the inbox and not yet in a manifest, archives before camp files.

        See "What is imported" in this module's docstring: the inbox rather than this run's
        downloads, oldest first per caselist, and a caselist stops at its first gap.
        """
        archive_queues = self._archive_import_queues(tally)
        openev_queue = self._openev_import_queue(tally)
        if not any(queue.ready for queue in archive_queues) and not openev_queue:
            waiting = sum(queue.waiting for queue in archive_queues)
            tally.record(
                SyncStage.IMPORT,
                StageOutcome.SKIPPED,
                f"nothing to import; {waiting} archive(s) in the inbox wait for an older week"
                if waiting
                else "nothing to import",
            )
            return
        failures: list[str] = []
        held_back = 0
        for queue in archive_queues:
            for position, (selection, path) in enumerate(queue.ready):
                try:
                    await self._import_archive(
                        selection, self._downloaded(tally, selection.name, path), tally
                    )
                except DomainError as refused:
                    failures.append(f"{selection.name}: {refused}")
                    held_back += len(queue.ready) - position - 1 + queue.waiting
                    break
            else:
                held_back += queue.waiting
        for openev_selection, path in openev_queue:
            try:
                await self._import_openev(
                    openev_selection, self._downloaded(tally, openev_selection.inbox_name, path), tally
                )
            except DomainError as refused:
                failures.append(f"openev-{openev_selection.openev_id}: {refused}")
        waiting = (
            f"; {held_back} archive(s) in the inbox held back for a later run, behind an older week"
            if held_back
            else ""
        )
        if failures:
            tally.record(
                SyncStage.IMPORT,
                StageOutcome.FAILED,
                f"{len(tally.snapshots_imported)} imported; {len(failures)} refused: "
                + "; ".join(failures)
                + waiting,
            )
            return
        tally.record(
            SyncStage.IMPORT,
            StageOutcome.COMPLETED,
            f"{len(tally.snapshots_imported)} snapshot(s) imported, {tally.blobs_stored} new file(s) stored"
            + waiting,
        )

    def _archive_import_queues(self, tally: _RunTally) -> list[_ImportQueue]:
        """Per caselist, the weeklies to import in order, up to its first gap, and what waits behind it.

        The candidates are every weekly newer than the caselist's latest manifest, which is exactly
        the selections decided `DOWNLOAD`, `ALREADY_IN_INBOX` or deferred by the cap. One is ready
        when it is in the inbox: fetched by this run, or decided `ALREADY_IN_INBOX`. The first that
        is not — deferred, or its download failed — is a gap, and nothing newer is imported.
        """
        fetched = {selection.name for selection, _ in tally.downloaded_archives}
        by_caselist: dict[str, list[ArchiveSelection]] = {}
        for selection in tally.archives:
            if selection.decision in _NEWER_THAN_HELD and selection.archive_date is not None:
                by_caselist.setdefault(selection.caselist, []).append(selection)
        queues: list[_ImportQueue] = []
        for candidates in by_caselist.values():
            candidates.sort(key=lambda one: (one.archive_date or date.min, one.name))
            ready: list[tuple[ArchiveSelection, Path]] = []
            waiting = 0
            gap = False
            for selection in candidates:
                in_inbox = (
                    selection.name in fetched or selection.decision is SelectionDecision.ALREADY_IN_INBOX
                )
                if in_inbox and not gap:
                    ready.append((selection, self._inbox / selection.name))
                    continue
                gap = True
                waiting += 1 if in_inbox else 0
            queues.append(_ImportQueue(ready=tuple(ready), waiting=waiting))
        return queues

    def _openev_import_queue(self, tally: _RunTally) -> list[tuple[OpenEvSelection, Path]]:
        """The camp files to import: fetched by this run, or already in the inbox and not recorded."""
        fetched = {selection.openev_id for selection, _ in tally.downloaded_openev}
        return [
            (selection, self._inbox / selection.inbox_name)
            for selection in sorted(tally.openev, key=lambda one: one.openev_id)
            if selection.openev_id in fetched or selection.decision is SelectionDecision.ALREADY_IN_INBOX
        ]

    def _downloaded(self, tally: _RunTally, name: str, path: Path) -> DownloadedFile:
        """What this run's download of `name` returned, or the same facts read off the inbox file."""
        for selection, downloaded in tally.downloaded_archives:
            if selection.name == name:
                return downloaded
        for openev_selection, downloaded in tally.downloaded_openev:
            if openev_selection.inbox_name == name:
                return downloaded
        return _inbox_file(path)

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
        # Which bytes this id delivered, so that a later run can ask the suppression list about
        # them before fetching it again. Refused members are included: they are what it delivered.
        self._deliveries.record(
            selection.openev_id,
            OpenEvDelivery(
                download_sha256=downloaded.sha256,
                path_sha256=_path_digest(selection.file.path) if selection.file is not None else None,
                member_sha256=frozenset(
                    entry.sha256
                    for entry in report.entries
                    if entry.sha256 is not None and entry.classification is not None
                ),
            ),
        )
        self._count_openev(report, tally)
        label = f"{OPENEV_PUBLISH_TARGET} {report.release}"
        if label not in tally.snapshots_imported:
            tally.snapshots_imported.append(label)
        target = PendingSnapshot(caselist=OPENEV_PUBLISH_TARGET, snapshot=report.release)
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
            in_sync = [snapshot for snapshot in report.snapshots if snapshot.in_sync]
            confirmed += len(in_sync)
            tally.confirmed.update(PendingSnapshot(one.caselist, one.snapshot) for one in in_sync)
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

    async def _retention_stage(self, tally: _RunTally, *, plan: SyncPlan, dry_run: bool) -> None:
        """Remove what nothing can need again from the inbox; a dry run lists it and removes nothing.

        See "What leaves the inbox" in this module's docstring. Called inside the run lock, after
        the report stage, whatever the stages before it did: a run that fetched nothing still
        clears what earlier runs left.
        """
        if self._status is None:
            tally.record(SyncStage.RETENTION, StageOutcome.SKIPPED, _NOTHING_TO_CONFIRM_AGAINST)
            return
        files = inbox_files(self._inbox)
        if not files:
            tally.record(SyncStage.RETENTION, StageOutcome.SKIPPED, "the inbox holds nothing")
            return
        verdicts = await self._judge_inbox(files, confirmed=frozenset(tally.confirmed))
        removable = tuple(one for one in verdicts if one.decision is RetentionDecision.REMOVE)
        kept = tuple(one for one in verdicts if one.decision is not RetentionDecision.REMOVE)
        if dry_run:
            once_imported, camp_once_imported = _imported_by(plan)
            tally.inbox_retention = InboxRetention(
                dry_run=True,
                removed=removable,
                kept=kept,
                once_imported=once_imported,
                camp_downloads_once_imported=camp_once_imported,
            )
            tally.record(SyncStage.RETENTION, StageOutcome.PLANNED, tally.inbox_retention.sentence())
            return
        removed: list[InboxFileVerdict] = []
        failed: list[tuple[InboxFileVerdict, str]] = []
        for one in removable:
            try:
                one.path.unlink()
            except OSError as refused:
                failed.append((one, type(refused).__name__))
                continue
            removed.append(one)
        tally.inbox_retention = InboxRetention(
            dry_run=False, removed=tuple(removed), kept=kept, failed=tuple(failed)
        )
        tally.record(
            SyncStage.RETENTION,
            StageOutcome.FAILED if failed else StageOutcome.COMPLETED,
            tally.inbox_retention.sentence(),
        )

    async def _judge_inbox(
        self, files: Sequence[Path], *, confirmed: frozenset[PendingSnapshot]
    ) -> list[InboxFileVerdict]:
        """Decide about every inbox file: the local checks first, then one bucket check per caselist."""
        releases = await self._openev_releases_by_download()
        remembered = self._deliveries.read()
        judged = [self._judge_locally(path, releases, remembered) for path in files]
        # Only what passed every local check costs a bucket request, and only what this run's report
        # stage did not already confirm.
        wanted = {snapshot for one in judged if one.kept_because is None for snapshot in one.snapshots}
        in_sync = confirmed | await self._confirm_in_bucket(wanted - confirmed)

        def confirmed_now(one: _JudgedLocally) -> bool:
            # Never vacuously: a file with no snapshot has nothing the bucket could confirm.
            return bool(one.snapshots) and one.snapshots <= in_sync

        return [
            InboxFileVerdict(
                name=one.name,
                kind=one.kind,
                decision=one.kept_because
                or (RetentionDecision.REMOVE if confirmed_now(one) else RetentionDecision.NOT_CONFIRMED),
                byte_size=one.byte_size,
                path=one.path,
            )
            for one in judged
        ]

    def _judge_locally(
        self, path: Path, releases: Mapping[str, frozenset[str]], remembered: Mapping[int, OpenEvDelivery]
    ) -> _JudgedLocally:
        """The checks that need no bucket: what the file is, and whether it is imported and recorded."""
        name = path.relative_to(self._inbox).as_posix()
        size = _size_of(path)
        digest = _digest_of(path)
        if digest is None:
            return _JudgedLocally(
                "a file that could not be read",
                InboxFileKind.OTHER,
                size,
                path,
                RetentionDecision.UNCLASSIFIED,
            )
        weekly = weekly_archive_of_inbox_name(name)
        if weekly is not None:
            caselist, week = weekly
            imported = self._imported_archive_digest(caselist, week) == digest
            return _JudgedLocally(
                f"{caselist} {week.isoformat()}",
                InboxFileKind.WEEKLY_ARCHIVE,
                size,
                path,
                None if imported else RetentionDecision.NOT_IMPORTED,
                frozenset({PendingSnapshot(caselist, week.isoformat())}),
            )
        openev_id = openev_id_of_inbox_name(name)
        if openev_id is None:
            return _JudgedLocally(
                f"sha256 {digest[:12]}", InboxFileKind.OTHER, size, path, RetentionDecision.UNCLASSIFIED
            )
        in_releases = releases.get(digest, frozenset())
        if not in_releases:
            kept_because: RetentionDecision | None = RetentionDecision.NOT_IMPORTED
        # The next run looks the record up by id (`_judge_unrecorded`), so an entry for the id is
        # what lets it recognise the file once the copy is gone.
        elif openev_id not in remembered:
            kept_because = RetentionDecision.NO_DELIVERY_RECORD
        else:
            kept_because = None
        return _JudgedLocally(
            f"sha256 {digest[:12]}",
            InboxFileKind.CAMP_DOWNLOAD,
            size,
            path,
            kept_because,
            frozenset(PendingSnapshot(OPENEV_PUBLISH_TARGET, one) for one in in_releases),
        )

    async def _confirm_in_bucket(self, snapshots: Iterable[PendingSnapshot]) -> frozenset[PendingSnapshot]:
        """Which of `snapshots` the bucket holds in sync now: the status comparison, run afresh.

        One comparison per caselist, of the one snapshot asked about or of the whole caselist when
        more are, because a caselist's weeklies share most of their sources and the comparison
        heads each source once. A bucket that cannot be read confirms nothing; the files wait for
        a run that can read it.
        """
        if self._status is None:  # pragma: no cover - the stage returns before asking
            return frozenset()
        by_caselist: dict[str, set[str]] = {}
        for one in snapshots:
            by_caselist.setdefault(one.caselist, set()).add(one.snapshot)
        found: set[PendingSnapshot] = set()
        for caselist, asked in sorted(by_caselist.items()):
            try:
                report = await self._status.status(caselist, next(iter(asked)) if len(asked) == 1 else None)
            except (DomainError, OSError) as unreadable:
                logger.warning(
                    "caselist sync: the bucket could not be compared for %s (%s), so nothing of it "
                    "leaves the inbox this run",
                    caselist,
                    type(unreadable).__name__,
                )
                continue
            found.update(
                PendingSnapshot(one.caselist, one.snapshot)
                for one in report.snapshots
                if one.in_sync and one.snapshot in asked
            )
        return frozenset(found)

    def _imported_archive_digest(self, caselist: str, week: date) -> str | None:
        """The `archive_sha256` this machine's manifest for a week records: the bytes imported."""
        for line in read_manifest_lines(self._manifest_path(manifest_key(caselist, week))):
            try:
                row: object = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and cast("dict[str, object]", row).get("kind") == "summary":
                digest = cast("dict[str, object]", row).get("archive_sha256")
                return digest if isinstance(digest, str) else None
        return None

    async def _openev_releases_by_download(self) -> dict[str, frozenset[str]]:
        """For every camp download digest a release manifest row came from, the releases it is in."""
        found: dict[str, set[str]] = {}
        for info in await self._local.objects.list_objects(manifest_prefix(OPENEV_PUBLISH_TARGET)):
            release = snapshot_of_manifest_key(OPENEV_PUBLISH_TARGET, info.key)
            if release is None:
                continue
            for digest in self._recorded_openev_at(info.key).download_digests:
                found.setdefault(digest, set()).add(release)
        return {digest: frozenset(releases) for digest, releases in found.items()}

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

    def _suppression_fallbacks(self) -> int:
        """How many reads of the list have fallen back to this machine's copy so far."""
        if isinstance(self._suppression, LocalFallbackSuppressionList):
            return self._suppression.fallbacks
        return 0

    def _note_local_copy_only(self, tally: _RunTally, stage: SyncStage, *, since: int) -> None:
        """Say on `stage`, and in the summary, that it read this machine's copy of the list alone."""
        if not isinstance(self._suppression, LocalFallbackSuppressionList):
            return
        if self._suppression.fallbacks == since:
            return
        reason = self._suppression.local_only_reason
        tally.suppression_list_local_copy_only = reason
        tally.add_to_reason(stage, f"this machine's copy of the suppression list alone was read: {reason}")

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
            bulk_downloads_spent_in_window=tally.bulk_downloads_spent_in_window,
            bulk_download_window_start=tally.bulk_download_window_start,
            suppression_list_local_copy_only=tally.suppression_list_local_copy_only,
            inbox_retention=tally.inbox_retention,
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
# Run modes
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PulledRun:
    """What one `caselist pull` produced, in whichever mode it ran."""

    summary: RunSummary
    record: SyncRunRecord | None
    """The run log's record of this run (`v1-e34-t03`), or `None` for a dry run, which records nothing."""
    summary_path: Path | None
    """Where the run's JSON summary was written, or `None` for a dry run, which writes nothing."""


async def run_pull(
    sync_service: Callable[[], CaselistSyncService],
    caselists: Sequence[str],
    *,
    dry_run: bool,
    publish_pending: bool,
    monitor: Callable[[], SyncRunMonitor],
    progress: Callable[[str], None],
) -> PulledRun:
    """Run one `caselist pull`: a dry run, a whole run, or `--publish-pending`.

    Args:
        sync_service: Builds (or returns the already built) :class:`CaselistSyncService`. Called
            only once the run has started, so that a refusal to build it is part of the run.
        caselists: The slugs to pull; empty for `--publish-pending`.
        dry_run: List what would be fetched, write nothing and record nothing.
        publish_pending: Only complete the publishes an earlier run deferred. Never together with
            `dry_run`; the command refuses that combination before calling this.
        monitor: Builds the run monitor. Not called for a dry run.
        progress: Where a one-line account of what is starting goes (the CLI's `--verbose`).

    Raises :class:`NoCaselistsConfigured` when asked to pull no caselist, and whatever the service
    or the monitor raise; the monitor has recorded and announced it first.
    """
    record: SyncRunRecord | None = None
    if dry_run:
        # A dry run writes nothing (v1-e34-t02 ac2), so it leaves no run record either.
        if not caselists:
            raise NoCaselistsConfigured
        progress(f"pulling {', '.join(caselists)} (dry run)")
        summary = await sync_service().run(caselists, dry_run=True)
    else:

        async def one_run() -> RunSummary:
            # Inside the monitor, so that a refusal — no caselist, the API not turned on, an
            # expired token, another run holding the lock — is recorded and announced too.
            if publish_pending:
                progress("completing the publishes an earlier run deferred")
                return await sync_service().publish_pending()
            if not caselists:
                raise NoCaselistsConfigured
            progress(f"pulling {', '.join(caselists)}")
            return await sync_service().run(caselists)

        monitored = await monitor().watch(
            one_run, caselists=caselists, mode="publish_pending" if publish_pending else "run"
        )
        summary, record = monitored.summary, monitored.record

    written_to = sync_service().summary_path(summary) if not summary.dry_run else None
    return PulledRun(summary=summary, record=record, summary_path=written_to)


# ------------------------------------------------------------------------------------------------
# Selection rules
# ------------------------------------------------------------------------------------------------

_DEFERRED_BY_CAP: Final = frozenset(
    {SelectionDecision.OVER_DAILY_BUDGET, SelectionDecision.DEFERRED_BY_RATE_LIMIT}
)

_NEWER_THAN_HELD: Final = frozenset(
    {
        SelectionDecision.DOWNLOAD,
        SelectionDecision.ALREADY_IN_INBOX,
        SelectionDecision.OVER_DAILY_BUDGET,
        SelectionDecision.DEFERRED_BY_RATE_LIMIT,
    }
)
"""The decisions a weekly newer than the caselist's latest manifest can get: the import candidates."""

_NO_BUCKET: Final = "this environment names no evidence bucket, so nothing is published from here"
_NOTHING_TO_CONFIRM_AGAINST: Final = (
    "this environment names no evidence bucket, so no publish can be confirmed and nothing leaves the inbox"
)
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


def _removal_sentence(openev: Sequence[OpenEvSelection]) -> str:
    """What the removal suppression list did to this run's camp files, for the select stage's reason.

    The run log keeps that reason, so `caselist runs --json` shows a removed file as skipped rather
    than as nothing at all. Counts and ids only.
    """

    def ids(decision: SelectionDecision) -> list[int]:
        return [one.openev_id for one in openev if one.decision is decision]

    parts: list[str] = []
    if skipped := ids(SelectionDecision.SKIPPED_AS_REMOVED):
        parts.append(f"{len(skipped)} OpenEv file(s) skipped as removed")
    if same_path := ids(SelectionDecision.SAME_PATH_AS_A_REMOVED_FILE):
        listed = ", ".join(f"openev-{one}" for one in same_path)
        parts.append(f"{len(same_path)} held back as a new id at a removed file's path ({listed})")
    if unreadable := ids(SelectionDecision.SUPPRESSION_LIST_UNREADABLE):
        parts.append(f"{len(unreadable)} not fetched because the suppression list could not be read")
    taken_again = (SelectionDecision.DOWNLOAD, SelectionDecision.ALREADY_IN_INBOX)
    if noted := [one.openev_id for one in openev if one.decision in taken_again and one.note is not None]:
        listed = ", ".join(f"openev-{one}" for one in noted)
        parts.append(
            f"{len(noted)} fetched before and neither recorded nor suppressed now, so taken again ({listed})"
        )
    return "; " + "; ".join(parts) if parts else ""


def _imported_by(plan: SyncPlan) -> tuple[tuple[str, ...], int]:
    """What a run of `plan` would import: weeklies by caselist and date, and how many camp downloads.

    A dry run says these would leave the inbox too, once imported and confirmed; it cannot say
    whether the import and the publish would succeed, so it does not count them as removed.
    """
    would_import = (SelectionDecision.DOWNLOAD, SelectionDecision.ALREADY_IN_INBOX)
    weeklies = tuple(
        f"{one.caselist} {one.archive_date.isoformat()}"
        for one in sorted(plan.archives, key=lambda one: (one.caselist, one.archive_date or date.min))
        if one.decision in would_import and one.archive_date is not None
    )
    return weeklies, sum(1 for one in plan.openev if one.decision in would_import)


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


@dataclass(frozen=True, slots=True)
class _RecordedOpenEv:
    """What one OpenEv release manifest records: member paths and bytes, and the downloads they came from."""

    paths: frozenset[str]
    stored_digests: frozenset[str]
    download_digests: frozenset[str]


_STORED_CLASSIFICATION_NAMES: Final = frozenset(str(one) for one in STORED_CLASSIFICATIONS)


class _SuppressionReadOnce:
    """The suppression list as one selection reads it: at most once, and only if a decision needs it.

    Most runs list no camp file the manifest has lost track of, and those never read the list. A
    list that cannot be read — the bucket's copy refused, or a torn line; an expired session falls
    back to this machine's copy before it gets here — is `None` here, logged once, and the
    decisions that need it say so (see :meth:`CaselistSyncService._judge_unrecorded`); the
    selection itself does not fail.
    """

    def __init__(self, suppression: SuppressionList) -> None:
        self._suppression = suppression
        self._read = False
        self._state: SuppressionState | None = None

    async def state(self) -> SuppressionState | None:
        if not self._read:
            self._read = True
            try:
                self._state = await load_suppression_state(self._suppression)
            except (DomainError, OSError) as unreadable:
                logger.warning(
                    "caselist sync: the suppression list could not be read (%s), so no camp file "
                    "this machine has fetched before is fetched this run",
                    type(unreadable).__name__,
                )
        return self._state


def _path_digest(path: str) -> str:
    """The SHA-256 of an OpenEv file's upstream path: what the delivery record keeps instead of it."""
    return hashlib.sha256(path.encode("utf-8")).hexdigest()


_OPENEV_INBOX_PREFIX: Final = re.compile(r"^openev-(\d+)-")
"""What the sync puts in front of a camp file's name (`openev_inbox_name`), and which file it was."""


def openev_id_of_inbox_name(name: str) -> int | None:
    """The OpenEv id an inbox file was downloaded as (`openev-<id>-…`), or `None` for any other name."""
    prefixed = _OPENEV_INBOX_PREFIX.match(name)
    return int(prefixed.group(1)) if prefixed is not None else None


_WEEKLY_INBOX_NAME: Final = re.compile(
    r"^(?P<caselist>[a-z]+[0-9]{2})-weekly-(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2})\.zip$"
)
"""`<slug>-weekly-<date>.zip`, as `caselist pull` names a weekly archive (the site's own name)."""

_CASELIST_SLUG: Final = re.compile(CASELIST_SLUG_PATTERN)


def weekly_archive_of_inbox_name(name: str) -> tuple[str, date] | None:
    """The caselist and week an inbox file was downloaded as (`<slug>-weekly-<date>.zip`), or `None`."""
    weekly = _WEEKLY_INBOX_NAME.match(name)
    if weekly is None or _CASELIST_SLUG.match(weekly["caselist"]) is None:
        return None
    try:
        return weekly["caselist"], date.fromisoformat(weekly["date"])
    except ValueError:
        return None


def inbox_files(directory: Path) -> list[Path]:
    """Every regular file under the inbox, by name: not `.partial/`, not dot files, not links.

    What a removal purges (`v1-e30-t09`) and what the retention stage judges, so the two see the
    same files. `.partial/` holds downloads in progress and a dot directory a removal's staged
    rewrite; neither is a download.
    """
    if not directory.is_dir():
        return []
    found: list[Path] = []
    for current, directories, filenames in os.walk(directory, followlinks=False):
        here = Path(current)
        directories[:] = sorted(
            one for one in directories if not one.startswith(".") and one != INBOX_PARTIAL_DIRECTORY
        )
        for filename in sorted(filenames):
            path = here / filename
            if not filename.startswith(".") and path.is_file() and not path.is_symlink():
                found.append(path)
    return found


_PATH_SEPARATORS: Final = re.compile(r"[\\/]+")
_NOT_A_NAME_CHARACTER: Final = re.compile(r"[\W_]+")


def _comparable_components(path: str) -> tuple[str, ...]:
    """A path's components as names rather than spellings: case, spacing and punctuation aside.

    `Tamarack/TSF-Estuary Solvency Advocate.docx`, as imported by hand, and
    `openev-512-TSF-Estuary_Solvency_Advocate.docx`, as the sync names it once its prefix is off,
    end in the same component.
    """
    return tuple(
        comparable
        for part in _PATH_SEPARATORS.split(path)
        if (comparable := _NOT_A_NAME_CHARACTER.sub("_", part.casefold()).strip("_"))
    )


def _held_openev_ids(listed: Sequence[OpenEvFile], recorded_paths: Iterable[str]) -> frozenset[int]:
    """The listed camp files a release manifest already records, however they were imported.

    A recorded path names a listed file in one of two ways:

    * **By id.** A file name starting `openev-<id>-` is one the sync downloaded, or a copy of one,
      and `<id>` says which.
    * **By path.** Compared component by component from the file name up with each listed file's
      own path, the listed file sharing the longest tail is the one recorded — provided no other
      listed file shares a tail as long. A tie decides nothing: two camps' `Topicality.docx`
      imported without its folder could be either, and a wrong guess would leave a camp file the
      store does not hold undownloaded for good. Both are fetched instead, and the one already held
      costs a download and a `DUPLICATE` row.
    """
    ids = {file.openev_id for file in listed}
    by_name: dict[str, list[tuple[int, tuple[str, ...]]]] = {}
    for file in listed:
        components = _comparable_components(file.path)
        if components:
            by_name.setdefault(components[-1], []).append((file.openev_id, components))
    held: set[int] = set()
    for path in recorded_paths:
        *folders, name = _PATH_SEPARATORS.split(path)
        prefixed = _OPENEV_INBOX_PREFIX.match(name)
        if prefixed is not None:
            if int(prefixed.group(1)) in ids:
                held.add(int(prefixed.group(1)))
                continue
            name = name[prefixed.end() :]
        components = _comparable_components("/".join([*folders, name]))
        if not components:
            continue
        shared = [
            (_shared_tail(components, candidate), openev_id)
            for openev_id, candidate in by_name.get(components[-1], [])
        ]
        longest = max((length for length, _ in shared), default=0)
        winners = [openev_id for length, openev_id in shared if length == longest]
        if len(winners) == 1:
            held.add(winners[0])
    return frozenset(held)


def _shared_tail(one: tuple[str, ...], other: tuple[str, ...]) -> int:
    """How many trailing components two paths have in common."""
    shared = 0
    for left, right in zip(reversed(one), reversed(other), strict=False):
        if left != right:
            break
        shared += 1
    return shared


_DIGEST_CHUNK_BYTES: Final = 1024 * 1024


def _digest_of(path: Path) -> str | None:
    """The SHA-256 of a file's bytes, or `None` when it cannot be read."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(_DIGEST_CHUNK_BYTES), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _size_of(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _inbox_file(path: Path) -> DownloadedFile:
    """A file an earlier run left in the inbox, described the way its download was."""
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    digest = _digest_of(path) if size else None
    if digest is None:
        raise UnreadableArchive(path.name, "the file in the inbox is empty or could not be read")
    return DownloadedFile(
        path=path, sha256=digest, byte_size=size, source_name=path.name, already_present=True
    )


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
    retention = summary.inbox_retention if not summary.dry_run else None
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
            "inbox_files_removed": len(retention.removed) if retention is not None else 0,
            "inbox_bytes_freed": retention.bytes_freed if retention is not None else 0,
            "duration_seconds": round(summary.duration_seconds, 3),
            "stages": {str(record.stage): str(record.outcome) for record in summary.stages},
        },
    )
