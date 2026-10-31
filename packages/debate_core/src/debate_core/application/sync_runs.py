"""The caselist sync run log: one record per run, kept locally and in the bucket, and read back.

`v1-e34-t03-sync-monitoring`. The weekly `caselist pull` (`v1-e34-t02`) runs unattended under
launchd, and an unattended job fails silently unless something makes it loud. This module is that
something:

* every real pull — successful, failed, refused, or cut short by the daily cap — produces exactly
  one :class:`SyncRunRecord`, validated by its Pydantic schema;
* the record is appended to a JSONL log in the environment's data directory
  (:data:`SYNC_RUN_LOG_FILENAME`) and published to `reports/sync-runs/<yyyy>/<run-id>.json` in the
  evidence bucket (:func:`sync_run_key`) — deferred, like every other publish, if the AWS session
  has expired, and published by the next run;
* a failed stage, an expired caselist_token and an expired SSO session each post one
  :class:`~debate_core.application.ports.notifier.Notification` naming the command that fixes it,
  as does a backlog of cap-deferred archives that has grown for two runs in a row. A failed run's
  says whether the next scheduled run should retry it or a person should look, and carries the fix
  the failed stage's hint gives (`v1-e34-t19`; see :func:`notifications_for`).

:class:`SyncRunMonitor` wraps a pull from the outside. It does not reach into
:class:`~debate_core.application.caselist_sync.CaselistSyncService`: the run produces its
:class:`~debate_core.application.caselist_sync.RunSummary` or raises, and the monitor turns either
into a record. That is what makes "exactly one record, whatever happened" true without a second
code path through the pipeline — and why a dry run, which writes nothing (`v1-e34-t02` ac2), is
never given to it.

## What a record may hold

Counts, caselist slugs, snapshot dates, archive names, stage names and outcomes, error *class*
names, and messages that have been through :func:`redact`. **Never** a token, a credential, a
file's contents, card text, a school, a team code or a student's name
(`docs/policies/caselist-data-use.md` rule 4, and this task's forbidden list).

Messages are where such a thing could hide, so they get two treatments:

* An exception that is not a :class:`~debate_core.application.errors.DomainError` — a bug, or a
  library's error — records its class and **no message at all**. Its text was not written by this
  project and nothing guarantees what is in it.
* A `DomainError`'s message is this project's own and is written without paths or tokens (see the
  error classes' docstrings); :func:`redact` is the backstop. It removes the caselist_token and any
  other registered secret, URL query strings, and anything path-shaped — quoted or not — because a
  disclosure's path is exactly `School/TeamCode/School-TeamCode-Side-Tournament-Round.docx`.

## What the record cannot hold: a run's details (`v1-e34-t19`)

**The record's shape is frozen.** :class:`SyncRunRecord` and :class:`StageEntry` forbid a field
they do not define, and `schema_version` is the literal `1`. That was a safeguard when it was
written, and it is now a contract with every build already installed: the weekly agent runs the
build it was installed with until someone reinstalls it, in the data directory and against the
bucket a newer build also uses. A record with one more key is a line such a build skips, and a
skipped line is a run that is missing from `caselist runs`, from the backlog history, and from the
list of records still owed to the bucket, where it would never be published. So nothing is added
to the record, not even a field left out when it is empty: a failed stage's codes and the parse
stage's counts are what a record would carry on exactly the runs that matter.

What a newer build knows beyond the record is kept **beside** it, keyed by run id, in
:class:`SyncRunDetails`:

* each failed stage's error codes and its hint, and a pending stage's earlier findings;
* the codes the command's exit status was decided from, for a run that returned a summary and for
  one that stopped on an error;
* the parse stage's nine counts, or nothing when the stage did not run;
* the search index stage's index id, sizes and warnings (`v1-e39-t09`), or nothing when it reached
  no index. The stage itself is a :class:`StageEntry` like any other, by its name, which every
  build reads: `stage` is a string, never a list of the names a build knew;
* how many of the objects the publish stage uploaded were manifests (`v1-e34-t28`);
* what a report stage cut short by an expired session had not compared yet, by caselist and
  snapshot (`v1-e34-t28`), which the next pull or `caselist pull --publish-pending` compares
  (:func:`comparisons_owed_by_the_newest_run`). Details an older build wrote have no such list,
  and owe no comparison;
* when each stage the run carried out started and ended, and, where the run reads its data volume,
  the fullest that volume got and the warning past `storage.volume_warning_percent`
  (`v1-e40-t03`, ADR-0020 (1) 2).

One line a run in :data:`SYNC_RUN_DETAILS_FILENAME`, next to the run log, and one object a run
under :data:`SYNC_RUN_DETAILS_KEY_PREFIX`, next to the records' prefix and not under it: an older
build's `caselist runs --remote` lists the records' prefix and reads every `.json` there, so an
object of another kind under it would be skipped with a warning and would take a record's place
among the last few. No older build opens either.

**The details are read by the rule the record never had: a reader ignores a key it does not
know.** A later build adds to the details without a second file. Their `schema_version` moves only
for a change that alters what an existing key means, and a build that does not know the version
reads those details as absent, never as a lost run: the run is the record.

The record is written first and is what a run is. Details that cannot be written cost a run its
codes in `caselist runs`, never its record or its notification; a record with no details is one an
older build wrote, or one whose details were lost, and is shown as such. In the bucket a run's
details go up before its record, so a record there is never waiting for its details. The one
exception is a record an *older* build publishes from the list of records still owed: it knows
nothing of details, and that run's stay on this machine.

## A run that cannot build its bucket (`v1-e34-t22`)

The monitor is handed its bucket to build, not a bucket: `build_remote`, called when a record is
first to be published and never before. The difference is one failure. A profile setting that
names a profile the AWS config does not define makes boto3 refuse a session, so the bucket's
adapter cannot be built at all (`v1-e29-t07`). While the monitor took the adapter built, the
monitor could not be built either, and the weekly run ended with no record and no notification:
the one failure this module exists to make loud was silent.

Now that refusal is a run that stopped on an error, like an expired `caselist_token`. The pull is
refused its service inside :meth:`SyncRunMonitor.watch`, which writes the record and its details
on this machine first, as always. Publishing then asks for the bucket, is refused in turn, and
leaves the record **owed**: its run id joins the ids still to publish, behind any already there,
and the next run that can build the bucket publishes it with its details. One notification says
a person should look and carries the adapter's fix, which names the setting. Nothing is added to
the record for any of this: it is the record a failed run has always had.

## The backlog (ac5)

A cap-deferred archive is a delay, not a loss (ADR-0017), and one that clears itself on the next
run is not worth a notification. What is worth one is a backlog that is *growing*: more deferred
this run than last, and more last run than the one before — the configured caselists publishing
faster than five a day can fetch. Each record carries the deferred count per caselist, the
backlog it inherited from the previous run of the same caselists, and the caselists whose backlog
has grown for :data:`BACKLOG_GROWTH_RUNS` runs in a row.
"""

from __future__ import annotations

import json
import logging
import re
import tempfile
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Final, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from debate_core.application.caselist.publish_plan import InvalidPublishTarget, validate_publish_target
from debate_core.application.caselist.run_lock import RunLockHeld, RunLockLost
from debate_core.application.caselist.status_service import CASELIST_DRIFT
from debate_core.application.caselist_sync import (
    CLOUD_FAILURE_RATE_RUNBOOK,
    REQUIRED_STAGES,
    DriftKind,
    PendingSnapshot,
    RunSummary,
    StageOutcome,
    SyncRunInProgress,
    SyncStage,
    append_state_line,
    cloud_parse_cure,
    fix_for,
    parse_command,
    remove_state_file,
    write_state_file,
)
from debate_core.application.errors import (
    UNMODELLED_ERROR_CODE,
    DomainError,
    NotFound,
    StoreCredentialsExpired,
    StoreError,
    reported_error_code,
)
from debate_core.application.ports.caselist_source import CaselistAuthExpired
from debate_core.application.ports.evidence_store import EvidenceObjectStore, validate_object_key
from debate_core.application.ports.notifier import Notification, Notifier

__all__ = [
    "ANOTHER_RUN_HELD_THE_LOCK",
    "ANOTHER_RUN_HELD_THE_LOCK_TITLE",
    "BACKLOG_GROWTH_RUNS",
    "CLOUD_NO_SESSION_CURE",
    "CLOUD_NO_SESSION_RUNBOOK",
    "RUN_LOCK_LOST",
    "RUN_LOCK_LOST_TITLE",
    "TOOK_OVER_THE_LOCK",
    "TOOK_OVER_THE_LOCK_TITLE",
    "BucketRunDetails",
    "RestoreDetails",
    "DRIFTED_AGAIN_TITLE",
    "FIX_FIRST_BANNER_WORDS",
    "HELD_BY_A_REMOVAL_TITLE",
    "LOCK_BANNER_WORDS",
    "MANIFEST_PUBLISHED_AGAIN",
    "MANIFEST_PUBLISHED_AGAIN_TITLE",
    "NEEDS_A_PERSON",
    "NEEDS_A_PERSON_TITLE",
    "PENDING_RECORDS_FILENAME",
    "SEARCH_INDEX_PUBLISH_COMMAND",
    "RETRIED_AFTER_ITS_FIX",
    "RETRIED_AFTER_ITS_FIX_TITLE",
    "RETRIED_BY_THE_NEXT_RUN",
    "RETRIED_BY_THE_NEXT_RUN_TITLE",
    "SYNC_RUN_DETAILS_FILENAME",
    "SYNC_RUN_DETAILS_KEY_PREFIX",
    "SYNC_RUN_KEY_PREFIX",
    "SYNC_RUN_LOG_FILENAME",
    "DataVolume",
    "DriftFinding",
    "MonitoredRun",
    "NoRemoteRunLog",
    "ParseCounts",
    "ParsedStoreOwedDetails",
    "PublishedSnapshot",
    "RecordedRun",
    "RetryRule",
    "RunMode",
    "SearchIndexCounts",
    "StageDetails",
    "StageTiming",
    "StageEntry",
    "SyncRunDetails",
    "SyncRunDetailsLog",
    "SyncRunHistory",
    "SyncRunLog",
    "SyncRunMonitor",
    "SyncRunOutcome",
    "SyncRunRecord",
    "banner_words",
    "comparisons_owed_by_the_newest_run",
    "details_for_failure",
    "details_for_summary",
    "hint_for_a_record",
    "notifications_for",
    "parse_commands",
    "read_remote_records",
    "read_remote_runs",
    "record_for_failure",
    "record_for_summary",
    "redact",
    "snapshots_owed_again_for_drift",
    "sync_run_details_key",
    "sync_run_key",
]

logger = logging.getLogger(__name__)

SYNC_RUN_LOG_FILENAME: Final = "caselist-sync-runs.jsonl"
"""The local run log, one JSON record per line, under the environment's data directory."""

SYNC_RUN_KEY_PREFIX: Final = "reports/sync-runs/"
"""Where records go in the evidence bucket: `reports/sync-runs/<yyyy>/<run-id>.json`."""

SYNC_RUN_DETAILS_FILENAME: Final = "caselist-sync-run-details.jsonl"
"""A run's details, one JSON object per line, beside the run log. See :class:`SyncRunDetails`."""

SYNC_RUN_DETAILS_KEY_PREFIX: Final = "reports/sync-run-details/"
"""Where details go in the evidence bucket: `reports/sync-run-details/<yyyy>/<run-id>.json`.

Beside :data:`SYNC_RUN_KEY_PREFIX` and deliberately not under it. See "What the record cannot
hold" in the module docstring.
"""

PENDING_RECORDS_FILENAME: Final = "caselist-sync-records-pending.json"
"""Run ids whose record is in the local log and not yet in the bucket."""

BACKLOG_GROWTH_RUNS: Final = 2
"""How many consecutive runs a caselist's cap-deferred backlog must grow for before it notifies.

From the spec (ac5): "a backlog that clears itself next week is not a notification, one that
grows for two runs is". Still to be checked against a measured dev run of three caselists; see
the session report's operator follow-ups.
"""

RECORD_SCHEMA_VERSION: Final = 1

DETAILS_SCHEMA_VERSION: Final = 1
"""The meaning of the keys of :class:`SyncRunDetails`. A key added leaves it as it is."""

_RUN_ID_FORMAT: Final = "%Y%m%dT%H%M%SZ"
"""The run id `CaselistSyncService` gives a run, from its start time in UTC."""

_MAX_MESSAGE_CHARACTERS: Final = 500

_MAX_RETENTION_REASON_CHARACTERS: Final = 8000
"""The retention stage's reason names every file it removed and kept (`v1-e34-t11`), by caselist and
date or by SHA-256 prefix, and a first run clearing a backlog names a season's weeklies. It goes
through :func:`redact` like every reason; only the length allowed is longer. `StageEntry.reason`
has no length limit, so a record carrying one is still a record every earlier build reads."""

RunMode = Literal["run", "publish_pending"]


# ------------------------------------------------------------------------------------------------
# The record
# ------------------------------------------------------------------------------------------------


class SyncRunOutcome(StrEnum):
    """How one run ended, as a single word for `caselist runs`. The fields hold the detail."""

    COMPLETED = "completed"
    """Everything wanted was fetched, imported and published."""

    NOTHING_NEW = "nothing_new"
    """Nothing was wanted and nothing was owed. Never a run the cap held back (ac6)."""

    CAP_DEFERRED = "cap_deferred"
    """Succeeded, and the daily bulk-download cap left archives for a later run (ac5)."""

    PUBLISH_PENDING = "publish_pending"
    """Captured locally; publishing, or the report stage's check of what was published, waits for an
    AWS login."""

    INCOMPLETE = "incomplete"
    """Captured and published; a later stage (parse, landscape, the bucket check) failed."""

    FAILED = "failed"
    """A download, import or publish failed, or the run stopped with an error."""


class StageEntry(BaseModel):
    """One stage of the run: its name, how it ended, and its (redacted) one-line reason.

    **No field is ever added here**, and none to :class:`SyncRunRecord`: every installed build
    refuses a record with a key it does not define. What else a stage has to say is in
    :class:`StageDetails`. See "What the record cannot hold" in the module docstring.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: str
    outcome: str
    reason: str | None = None


class SyncRunRecord(BaseModel):
    """One `caselist pull`, as the run log and the bucket keep it.

    Counts, slugs, dates, stage outcomes and error classes. See the module docstring for what may
    never be in one, and :func:`redact` for how messages are made safe.

    **Its fields are frozen** at what the builds already installed read
    (`v1-e34-t19`): `test_pull_run_record_is_read_by_every_build.py` holds this model to the schema
    those builds printed. A run's :class:`SyncRunDetails` are where anything new goes.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = RECORD_SCHEMA_VERSION
    run_id: str = Field(pattern=r"^\d{8}T\d{6}Z$")
    environment: str
    mode: RunMode
    started_at: datetime
    finished_at: datetime
    outcome: SyncRunOutcome
    caselists: tuple[str, ...] = ()

    archives_seen: int = Field(default=0, ge=0)
    archives_wanted: int = Field(default=0, ge=0)
    """Newer than what this machine held: fetched plus deferred by the cap."""
    archives_downloaded: int = Field(default=0, ge=0)
    archives_deferred: int = Field(default=0, ge=0)
    """Wanted and left for a later run by the daily bulk-download cap."""
    deferred_by_caselist: dict[str, int] = Field(default_factory=lambda: dict[str, int]())
    """The deferred count for every caselist this run selected for, zeros included."""

    backlog_carried: int | None = None
    """What the previous run of these caselists had deferred, or `None` for a first run."""
    backlog_growing: tuple[str, ...] = ()
    """Caselists whose deferred count has grown for :data:`BACKLOG_GROWTH_RUNS` runs in a row."""

    openev_downloaded: int = Field(default=0, ge=0)
    files_imported: int = Field(default=0, ge=0)
    snapshots_imported: tuple[str, ...] = ()
    objects_published: int = Field(default=0, ge=0)
    pending_publish: tuple[str, ...] = ()
    """`<caselist> <snapshot>` pairs whose publish waits for a later run."""

    stages: tuple[StageEntry, ...] = ()
    error_class: str | None = None
    error_message: str | None = None
    """Redacted, and only for a `DomainError`. See the module docstring."""

    @property
    def object_key(self) -> str:
        return sync_run_key(self.run_id, self.started_at)

    @property
    def succeeded(self) -> bool:
        return self.outcome is not SyncRunOutcome.FAILED


def sync_run_key(run_id: str, started_at: datetime) -> str:
    """`reports/sync-runs/<yyyy>/<run-id>.json`, validated as an object key."""
    return validate_object_key(f"{SYNC_RUN_KEY_PREFIX}{started_at.astimezone(UTC):%Y}/{run_id}.json")


def sync_run_details_key(record_key: str) -> str:
    """The key of the details of the run whose record is at `record_key`: the same year and run id.

    `reports/sync-run-details/<yyyy>/<run-id>.json`. From the record's own key, so that a record
    and its details can never be filed under two different years.
    """
    return validate_object_key(SYNC_RUN_DETAILS_KEY_PREFIX + record_key.removeprefix(SYNC_RUN_KEY_PREFIX))


# ------------------------------------------------------------------------------------------------
# Beside the record: a run's details
# ------------------------------------------------------------------------------------------------


class DriftFinding(BaseModel):
    """One snapshot the report stage found not in sync, and what differs (`v1-e34-t23`).

    `kinds` are :class:`~debate_core.application.caselist_sync.DriftKind` values: `manifest`,
    `source`, `missing`, `suppressed_rows`. A caselist slug, a snapshot name and words: nothing a
    record may not hold.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    caselist: str
    snapshot: str
    kinds: tuple[str, ...] = ()


class PublishedSnapshot(BaseModel):
    """A snapshot a run published, by caselist slug and snapshot name: nothing a record may not hold."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    caselist: str
    snapshot: str


class StageDetails(BaseModel):
    """What one stage has to say that its :class:`StageEntry` has no field for."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    stage: str
    error_codes: tuple[str, ...] = ()
    """The error code of each failure behind a failed stage
    (:attr:`~debate_core.application.caselist_sync.StageRecord.error_codes`)."""

    hint: str | None = None
    """The fix the summary gives for it, when it has one. A directory by its role, never its path."""

    earlier_findings: tuple[str, ...] = ()
    """What a pending stage had found before the session expired
    (:attr:`~debate_core.application.caselist_sync.StageRecord.earlier_findings`)."""

    drift: tuple[DriftFinding, ...] = ()
    """The report stage's findings, each snapshot with what differs, failed or pending
    (:attr:`~debate_core.application.caselist_sync.StageRecord.drift`, `v1-e34-t23`). A key a
    build from before it passes over."""

    not_compared: tuple[PublishedSnapshot, ...] = ()
    """What a report stage pending on an expired session had not compared yet
    (:attr:`~debate_core.application.caselist_sync.StageRecord.not_compared`, `v1-e34-t28`): what
    the next pull or `caselist pull --publish-pending` compares. A key a build from before it passes over,
    and its absence, in details such a build wrote, owes nothing."""


class ParseCounts(BaseModel):
    """The parse stage's counts: the nine integers of a run summary's `parse`, and nothing else
    (:class:`~debate_core.application.caselist_sync.ParseStageCounts`)."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    caselists: int = Field(ge=0)
    full_parses: int = Field(ge=0)
    attempted: int = Field(ge=0)
    skipped: int = Field(ge=0)
    unsupported: int = Field(ge=0)
    failed: int = Field(ge=0)
    cards: int = Field(ge=0)
    uploaded: int = Field(ge=0)
    not_published: int = Field(ge=0)


class ParsedStoreOwedDetails(BaseModel):
    """A caselist whose parsed store the parse stage left unpublished, and whether `--publish-only`
    finishes it (:class:`~debate_core.application.caselist_sync.ParsedStoreOwed`, `v1-e34-t31`).

    `publish_only` defaults to false, so an entry that does not say is named with `--publish`, which
    rebuilds first: failing toward the command that never publishes aggregates rebuilt from the
    run's own copy of the suppression list alone.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    caselist: str
    publish_only: bool = False


class SearchIndexCounts(BaseModel):
    """The search index stage's index and its size: a run summary's `search_index`, and nothing else
    (:class:`~debate_core.application.caselist_sync.SearchIndexStageCounts`, `v1-e39-t09`)."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    index_id: str
    built: bool
    published: bool
    documents: int = Field(ge=0)
    sqlite_bytes: int = Field(ge=0)
    gzip_bytes: int = Field(ge=0)
    bytes_per_document: int | None = Field(default=None, ge=0)
    warnings: tuple[str, ...] = ()
    removed: int = Field(default=0, ge=0)
    bytes_freed: int = Field(default=0, ge=0)
    previous_index_id: str | None = None
    """What the growth is against: the index `current.json` named before (`v1-e39-t14`). Added keys,
    so details a build from before it wrote read as no growth recorded."""

    documents_growth: int | None = None
    sqlite_bytes_growth: int | None = None
    gzip_bytes_growth: int | None = None
    not_cards_by_store: dict[str, dict[str, int]] | None = None
    """Documents the build left out as no card, by store and why, when the stage built (`v1-e39-t12`).
    An added key, so details a build from before it wrote read as none recorded."""


class StageTiming(BaseModel):
    """When one stage started and ended: a summary's
    :class:`~debate_core.application.caselist_sync.StageTime` (`v1-e40-t03`)."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    stage: str
    started_at: datetime
    finished_at: datetime


class DataVolume(BaseModel):
    """The fullest the data directory's volume got, in bytes and as a share: a summary's
    :class:`~debate_core.application.caselist_sync.DataVolumeUsage` (`v1-e40-t03`). No path."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    total_bytes: int = Field(ge=0)
    peak_used_bytes: int = Field(ge=0)
    peak_percent: float = Field(ge=0)
    peak_after: str
    warning_percent: int
    warning: str | None = None
    """The summary's sentence when the volume passed `warning_percent`, else `None`."""


class RestoreDetails(BaseModel):
    """What a bucket-mode run restored before it started (`v1-e40-t04`): counts and ids, no path."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    started_at: datetime
    finished_at: datetime
    state_files: int = Field(default=0, ge=0)
    parsed_version: str | None = None
    parsed_objects: int = Field(default=0, ge=0)
    parsed_bytes: int = Field(default=0, ge=0)
    parsed_kept: int = Field(default=0, ge=0)
    index_id: str | None = None


class BucketRunDetails(BaseModel):
    """What a bucket-mode run (`caselist.run_state = "bucket"`) did with the bucket's run lock and state.

    `v1-e40-t04`, ADR-0020 (3) and (4). The record's shape is frozen, so all of it is here.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    held_by: str | None = None
    """For a run another runner's live lease refused: that runner, as its lock names it."""
    held_until: datetime | None = None
    """And when its lease runs out."""
    took_over: str | None = None
    """For a run that took over an expired lease: whose, and when it expired, in one sentence."""
    lock_lost: bool = False
    """The lease was taken over while the run ran: it wrote nothing more, and ended `RUN_LOCK_LOST`."""
    restore: RestoreDetails | None = None
    bundle: str | None = None
    """What became of the run-state bundle at the run's last save: saved, or why not."""


class SyncRunDetails(BaseModel):
    """What one run has to say that its :class:`SyncRunRecord` cannot hold, keyed by its run id.

    See "What the record cannot hold" in the module docstring. Codes, counts and hints: the same
    rule as the record about what may never be in one.

    `extra="ignore"` is the point of the class. A key this build does not know is one a later build
    added, and is passed over, so adding to the details never needs another file.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    schema_version: Literal[1] = DETAILS_SCHEMA_VERSION
    run_id: str = Field(pattern=r"^\d{8}T\d{6}Z$")

    stages: tuple[StageDetails, ...] = ()
    """One entry for each stage that has something to say, in the run's order; the others are left
    out, and a stage left out has no codes, no hint and no earlier finding."""

    failure_codes: tuple[str, ...] = ()
    """The error codes the command's exit status was decided from: those of the failed stages that
    had to finish (:attr:`~debate_core.application.caselist_sync.RunSummary.failure_codes`), or the
    code of the error that ended the run. Empty for a run that did not fail."""

    hint: str | None = None
    """The fix for an error that ended the run before any stage recorded it, when it has one."""

    parse: ParseCounts | None = None
    """The parse stage's counts, or `None` when the stage did not run."""

    parsed_stores_owed: tuple[ParsedStoreOwedDetails, ...] = ()
    """Each caselist whose parsed store the parse stage did not publish complete, and whether
    `caselist parse --publish-only` finishes it (`v1-e34-t31`). A key a build from before it passes
    over; details such a build wrote have none, and their parse stage is named with `--publish`, or
    with the cloud cure in bucket mode (`v1-e40-t18`)."""

    search_index: SearchIndexCounts | None = None
    """The search index stage's index and size, or `None` when it reached no index (`v1-e39-t09`).
    A key a build from before it passes over."""

    held_by_request: dict[str, int] = Field(default_factory=lambda: dict[str, int]())
    """Uploads the run's imports refused because a removal holds their path, by request id
    (:attr:`~debate_core.application.caselist_sync.RunSummary.held_by_request`, `v1-e34-t23`).
    Request ids and counts, never a path. A key a build from before it passes over."""

    manifests_published: int = Field(default=0, ge=0)
    """Of the record's `objects_published`, the manifests
    (:attr:`~debate_core.application.caselist_sync.RunSummary.manifests_published`, `v1-e34-t28`).
    A key a build from before it passes over."""

    stage_times: tuple[StageTiming, ...] = ()
    """When each stage the run carried out started and ended, in the run's order (`v1-e40-t03`).
    Empty for a run that raised before returning a summary, and in details a build from before it
    wrote."""

    data_volume: DataVolume | None = None
    """The fullest the data directory's volume got, or `None` when the run read none (`v1-e40-t03`)."""

    bucket_run: BucketRunDetails | None = None
    """What a bucket-mode run did with the bucket's run lock and state, or `None` in local mode
    (`v1-e40-t04`). A key a build from before it passes over."""

    def stage(self, name: str) -> StageDetails | None:
        return next((one for one in self.stages if one.stage == name), None)


@dataclass(frozen=True, slots=True)
class RecordedRun:
    """One run as it is read back: its record, and its details when this machine or the bucket
    holds them. `details` is `None` for a run an older build recorded."""

    record: SyncRunRecord
    details: SyncRunDetails | None


# ------------------------------------------------------------------------------------------------
# Redaction
# ------------------------------------------------------------------------------------------------

REDACTED: Final = "[redacted]"

_COOKIE_VALUE = re.compile(r"(caselist_token\s*[=:]\s*)[^;,\s\"']+", re.IGNORECASE)
_URL_QUERY = re.compile(r"(https?://[^\s\"'?#]+)\?[^\s\"'#]*")
_QUOTED_PATH = re.compile(r"""(['"])[^'"\n]*[/\\][^'"\n]*\1""")
_PATH_TOKEN = re.compile(r"[^\s'\"]*[/\\][^\s'\"]*")

_NOT_A_PATH = re.compile(
    r"[(\[]?(?:full/\d{4}-\d{2}-\d{2}|docs/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.md)[)\]:;,.]*"
)
"""The two things with a `/` in them that a record's reason names and that are no path (`v1-e34-t23`):
a complete archive's snapshot name, `full/<date>`, and a runbook of this repository, `docs/....md`,
which a refusal's fix points at. Matched against the whole token, brackets and trailing punctuation
allowed: a path on a machine starts at `/` or `~/`, and a disclosure's path is neither of these."""


def _redacted_unless_not_a_path(match: re.Match[str]) -> str:
    token = match.group(0)
    return token if _NOT_A_PATH.fullmatch(token) else REDACTED


def redact(message: str, *, secrets: Iterable[str] = (), limit: int = _MAX_MESSAGE_CHARACTERS) -> str:
    """`message` with secrets, URL queries and anything path-shaped removed, on one short line.

    A path goes whole, including a quoted one with spaces in it, because a disclosure path names a
    school, a team code and a round, and `OSError` quotes the path it failed on. A complete
    archive's snapshot name and a runbook of this repository stay (:data:`_NOT_A_PATH`): until
    `v1-e34-t23` both went too, and a refusal's reason said "[redacted] lists what each profile is
    granted".
    """
    text = message
    for secret in secrets:
        if secret:
            text = text.replace(secret, REDACTED)
    text = _COOKIE_VALUE.sub(lambda match: match.group(1) + REDACTED, text)
    text = _URL_QUERY.sub(lambda match: match.group(1) + "?" + REDACTED, text)
    text = _QUOTED_PATH.sub(REDACTED, text)
    text = _PATH_TOKEN.sub(_redacted_unless_not_a_path, text)
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


_ABSOLUTE_PATH = re.compile(r"""(?<![\w.<>`/~])(?:~/|/)[^\s'"`<>]+""")
"""Something that starts at `/` or `~/`: a path on a machine, and never the `docs/...` a hint cites."""

_MAX_HINT_CHARACTERS: Final = 1200


def hint_for_a_record(hint: str, *, secrets: Iterable[str] = ()) -> str:
    """`hint` as the details and a notification carry it: as written, less a secret or a machine's path.

    A hint is this project's own sentence and names a directory by its role
    (:func:`~debate_core.application.caselist_sync.fix_for`), so there is normally nothing to take
    out. It is not put through :func:`redact`, which removes anything path-shaped and would take
    the runbook a hint points at with it. This removes the registered secrets and any *absolute*
    path, which is the only kind that says where something is on the operator's machine.
    """
    text = hint
    for secret in secrets:
        if secret:
            text = text.replace(secret, REDACTED)
    text = _ABSOLUTE_PATH.sub(REDACTED, text)
    text = " ".join(text.split())
    if len(text) > _MAX_HINT_CHARACTERS:
        text = text[: _MAX_HINT_CHARACTERS - 1] + "…"
    return text


def _error_message(error: BaseException, secrets: Sequence[str]) -> str | None:
    """A `DomainError`'s message, redacted; nothing at all for any other exception."""
    if isinstance(error, DomainError):
        return redact(str(error), secrets=secrets)
    return None


# ------------------------------------------------------------------------------------------------
# Building a record
# ------------------------------------------------------------------------------------------------


def record_for_summary(
    summary: RunSummary,
    *,
    environment: str,
    mode: RunMode,
    previous: Sequence[SyncRunRecord] = (),
    secrets: Sequence[str] = (),
    growth_runs: int = BACKLOG_GROWTH_RUNS,
) -> SyncRunRecord:
    """The record of a run that returned a summary. `previous` is the log so far, oldest first."""
    deferred = _deferred_by_caselist(summary)
    return SyncRunRecord(
        run_id=summary.run_id,
        environment=environment,
        mode=mode,
        started_at=summary.started_at,
        finished_at=summary.finished_at,
        outcome=_outcome_of(summary),
        caselists=summary.caselists,
        archives_seen=summary.archives_seen,
        archives_wanted=summary.archives_wanted,
        archives_downloaded=summary.archives_downloaded,
        archives_deferred=summary.archives_deferred,
        deferred_by_caselist=deferred,
        backlog_carried=_backlog_carried(deferred, previous),
        backlog_growing=_backlog_growing(deferred, previous, growth_runs=growth_runs),
        openev_downloaded=summary.openev_downloaded,
        files_imported=summary.files_imported,
        snapshots_imported=summary.snapshots_imported,
        objects_published=summary.objects_published,
        pending_publish=summary.pending_publish,
        stages=tuple(
            StageEntry(
                stage=str(record.stage),
                outcome=str(record.outcome),
                reason=redact(record.reason, secrets=secrets, limit=_reason_limit(record.stage))
                if record.reason is not None
                else None,
            )
            for record in summary.stages
        ),
    )


_MAX_SELECT_REASON_CHARACTERS: Final = 2000
"""The select stage's reason carries the complete-archive rotation's decision and each caselist's
state (`v1-e34-t04`) after the download window, and with three caselists that passes 500
characters. Like retention's, only the length allowed is longer: every earlier build reads it."""


_MAX_PARSE_REASON_CHARACTERS: Final = 2000
"""The parse stage's reason is where its counts reach an older build's `caselist runs`
(`v1-e34-t17`): the record has no field for them, and adding one would be a record an older build
refuses. This build keeps the counts themselves beside the record (:class:`ParseCounts`,
`v1-e34-t19`) and still writes the sentence, for those builds and for the caption. After the counts
it names each caselist that failed and why, and what publishes a parsed store that was not. As for
the select stage, only the length allowed is longer."""


def _reason_limit(stage: SyncStage) -> int:
    if stage is SyncStage.RETENTION:
        return _MAX_RETENTION_REASON_CHARACTERS
    if stage is SyncStage.SELECT:
        return _MAX_SELECT_REASON_CHARACTERS
    if stage in (SyncStage.PARSE, SyncStage.SEARCH_INDEX):
        # The search index stage's sizes and warnings reach `caselist runs` the same way.
        return _MAX_PARSE_REASON_CHARACTERS
    return _MAX_MESSAGE_CHARACTERS


def record_for_failure(
    error: BaseException,
    *,
    run_id: str,
    started_at: datetime,
    finished_at: datetime,
    environment: str,
    mode: RunMode,
    caselists: Sequence[str] = (),
    secrets: Sequence[str] = (),
) -> SyncRunRecord:
    """The record of a run that raised instead of returning a summary."""
    return SyncRunRecord(
        run_id=run_id,
        environment=environment,
        mode=mode,
        started_at=started_at,
        finished_at=finished_at,
        outcome=SyncRunOutcome.FAILED,
        caselists=tuple(caselists),
        error_class=type(error).__name__,
        error_message=_error_message(error, secrets),
    )


def details_for_summary(summary: RunSummary, *, secrets: Sequence[str] = ()) -> SyncRunDetails:
    """The details of a run that returned a summary: what its record has no field for."""
    return SyncRunDetails(
        run_id=summary.run_id,
        stages=tuple(
            StageDetails(
                stage=str(record.stage),
                error_codes=record.error_codes,
                hint=hint_for_a_record(record.hint, secrets=secrets) if record.hint else None,
                earlier_findings=record.earlier_findings,
                drift=tuple(
                    DriftFinding(
                        caselist=one.caselist,
                        snapshot=one.snapshot,
                        kinds=tuple(str(kind) for kind in one.kinds),
                    )
                    for one in record.drift
                ),
                not_compared=tuple(
                    PublishedSnapshot(caselist=one.caselist, snapshot=one.snapshot)
                    for one in record.not_compared
                ),
            )
            for record in summary.stages
            if record.error_codes
            or record.hint
            or record.earlier_findings
            or record.drift
            or record.not_compared
        ),
        failure_codes=summary.failure_codes,
        parse=ParseCounts(**summary.parse.as_json()) if summary.parse is not None else None,
        parsed_stores_owed=tuple(
            ParsedStoreOwedDetails(caselist=one.caselist, publish_only=one.publish_only)
            for one in summary.parsed_stores_owed
        ),
        search_index=SearchIndexCounts.model_validate(summary.search_index.as_json())
        if summary.search_index is not None
        else None,
        held_by_request=dict(summary.held_by_request),
        manifests_published=summary.manifests_published,
        stage_times=tuple(
            StageTiming(stage=str(one.stage), started_at=one.started_at, finished_at=one.finished_at)
            for one in summary.stage_times
        ),
        data_volume=DataVolume.model_validate(summary.data_volume.as_json())
        if summary.data_volume is not None
        else None,
    )


def details_for_failure(
    error: BaseException, *, run_id: str, secrets: Sequence[str] = (), bucket_mode: bool = False
) -> SyncRunDetails:
    """The details of a run that raised instead of returning a summary.

    Its one failure code is the code the CLI reports the error under, and its hint the fix a stage
    would have given the same error, in the same mode (`bucket_mode`, `v1-e40-t22`).
    """
    hint = fix_for(error, bucket_mode=bucket_mode)
    return SyncRunDetails(
        run_id=run_id,
        failure_codes=(reported_error_code(error),),
        hint=hint_for_a_record(hint, secrets=secrets) if hint else None,
    )


def _outcome_of(summary: RunSummary) -> SyncRunOutcome:
    if not summary.succeeded:
        return SyncRunOutcome.FAILED
    # Pending on the publish stage itself, not on `pending_publish`: a publish that did not pend
    # and did not fail leaves something owed only when the report stage owed a drifted manifest
    # again (`v1-e34-t26`), which waits for the next run and not for a login. Before that the two
    # tests were the same, so no run's outcome moves.
    if _stage_is(summary, SyncStage.PUBLISH, StageOutcome.PENDING):
        return SyncRunOutcome.PUBLISH_PENDING
    if any(
        _stage_is(summary, stage, StageOutcome.PENDING)
        for stage in (SyncStage.PARSE, SyncStage.SEARCH_INDEX, SyncStage.REPORT)
    ):
        # The parsed store's publish is a publish, and it waits for the same login (`v1-e34-t17`);
        # so does the search index's (`v1-e39-t09`), and so does the report stage's check of what was
        # published, which the next pull or `--publish-pending` makes (`v1-e34-t28`). Every installed build
        # reads this value; a run whose only pending stage was the report was `completed` before.
        return SyncRunOutcome.PUBLISH_PENDING
    if any(record.outcome is StageOutcome.FAILED for record in summary.stages):
        return SyncRunOutcome.INCOMPLETE
    if summary.archives_deferred:
        return SyncRunOutcome.CAP_DEFERRED
    if summary.nothing_new:
        return SyncRunOutcome.NOTHING_NEW
    return SyncRunOutcome.COMPLETED


def _stage_is(summary: RunSummary, stage: SyncStage, outcome: StageOutcome) -> bool:
    record = summary.stage(stage)
    return record is not None and record.outcome is outcome


def _deferred_by_caselist(summary: RunSummary) -> dict[str, int]:
    """Deferred counts for every caselist the run listed archives for, zeros included.

    Zeros matter: they are what says a backlog *cleared*, and a caselist absent from the map is
    one this run knows nothing about (it failed before listing, or did not cover it).
    """
    counts: dict[str, int] = {}
    for selection in summary.archives:
        counts.setdefault(selection.caselist, 0)
        if selection.deferred_by_cap:
            counts[selection.caselist] += 1
    return counts


def _history(caselist: str, previous: Sequence[SyncRunRecord]) -> list[int]:
    """This caselist's deferred counts in earlier runs that listed it, oldest first."""
    return [
        record.deferred_by_caselist[caselist]
        for record in previous
        if caselist in record.deferred_by_caselist
    ]


def _backlog_carried(deferred: Mapping[str, int], previous: Sequence[SyncRunRecord]) -> int | None:
    """What the last run of each of these caselists had deferred, summed; `None` if none ran."""
    carried = [history[-1] for history in (_history(caselist, previous) for caselist in deferred) if history]
    return sum(carried) if carried else None


def _backlog_growing(
    deferred: Mapping[str, int], previous: Sequence[SyncRunRecord], *, growth_runs: int
) -> tuple[str, ...]:
    """Caselists whose deferred count rose at each of the last `growth_runs` runs, this one included."""
    growing: list[str] = []
    for caselist, now in deferred.items():
        series = [*_history(caselist, previous), now][-(growth_runs + 1) :]
        if len(series) == growth_runs + 1 and all(
            later > earlier for earlier, later in zip(series, series[1:], strict=False)
        ):
            growing.append(caselist)
    return tuple(sorted(growing))


# ------------------------------------------------------------------------------------------------
# Notifications
# ------------------------------------------------------------------------------------------------

AUTH_LOGIN_COMMAND: Final = "debate-research caselist auth login"
PULL_COMMAND: Final = "debate-research caselist pull"
PUBLISH_PENDING_COMMAND: Final = "debate-research caselist pull --publish-pending"
PARSE_COMMAND: Final = "debate-research caselist parse --caselist <slug> --publish"
"""What finishes a local-mode parse stage that failed (`v1-e34-t17`), when the run's details do not
name each caselist's own command (:func:`parse_commands`): details an earlier build wrote, or a stage
that owes no parsed store, whose failure the hint names. Running the pull again does not: a pull that
imports nothing parses nothing. The stage's reason in `caselist runs` names the caselists. Never a
bucket-mode run's (`v1-e40-t18`)."""
SEARCH_INDEX_PUBLISH_COMMAND: Final = (
    "DEBATE_ENV={environment} debate-research tub index publish --env {environment} --newest"
)
"""What publishes an index whose publish pended (`v1-e39-t09`), by hand; the next run with a session
does it too. `--publish-pending` does not."""


RETRIED_BY_THE_NEXT_RUN_TITLE: Final = "caselist pull failed: will be retried"
NEEDS_A_PERSON_TITLE: Final = "caselist pull failed: needs a person"
"""The two titles of a failed run's notification: the verdict is the first thing a banner shows."""

RETRIED_BY_THE_NEXT_RUN: Final = (
    "The next scheduled run should retry it: every failure here is one a later run may not meet."
)
"""A failed run's verdict when every code its exit was decided from is one a retry may cure
(exit 3). `docs/runbooks/caselist-scheduled-sync.md` quotes it."""

NEEDS_A_PERSON: Final = (
    "A person should look: at least one failure here will be the same on the next scheduled run."
)
"""The verdict in every other case (exit 1, and a bug). The runbook quotes this one too."""

RETRIED_AFTER_ITS_FIX_TITLE: Final = "caselist pull failed: retried once fixed"
RETRIED_AFTER_ITS_FIX: Final = (
    "The next scheduled run retries it, and is refused the same way until the fix that follows is made."
)
"""The first verdict's wording when a failed stage that had to finish carries a fix, or the error that
stopped the run does (`v1-e34-t23`): a refusal exits `3` like an outage, and is refused again until
the permission or the grant in its hint is fixed. The same rule decides it, and the exit code is
unchanged. The runbook quotes both."""

ANOTHER_RUN_HELD_THE_LOCK_TITLE: Final = "caselist pull skipped: another was running"
ANOTHER_RUN_HELD_THE_LOCK: Final = (
    "Another caselist pull held the run lock, so this one did nothing. That run records and "
    "announces its own outcome."
)
"""A run refused because another holds the run lock (`v1-e34-t23`). It exits `1`, as before, and a
person's look is not what it asks for: the run holding the lock is the one that says how it went.
The runbook quotes both."""

RUNS_COMMAND: Final = "debate-research caselist runs"

RUN_LOCK_LOST_TITLE: Final = "caselist pull lost the bucket's run lock"
RUN_LOCK_LOST: Final = (
    "Another runner took this run's lease on the bucket's run lock over after it expired, so this run "
    "wrote nothing more to the bucket and ended RUN_LOCK_LOST. Its record is on this machine only; the "
    "run that took over records and announces its own outcome."
)
"""A bucket-mode run whose lease was taken (`v1-e40-t04`, ADR-0020 (4) 4 and (6))."""

TOOK_OVER_THE_LOCK_TITLE: Final = "caselist pull took over an expired run lock"
TOOK_OVER_THE_LOCK: Final = (
    "The run that held it ended without releasing it: killed, stopped, or out of its deadline. This run "
    "carried on from the last state that run saved."
)
"""A bucket-mode run that took over an expired lease (`v1-e40-t04`, ADR-0020 (4) 6 and (6))."""


def _bucket_lock_held(bucket: BucketRunDetails | None) -> str:
    """What a run refused by another runner's live lease says: that runner and its lease, from the details."""
    if bucket is None or bucket.held_by is None:
        return (
            "Another runner held the bucket's run lock, so this one did nothing. That run records and "
            "announces its own outcome."
        )
    until = (
        f", its lease until {bucket.held_until.astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')}"
        if bucket.held_until is not None
        else ""
    )
    return (
        f"Another runner held the bucket's run lock ({bucket.held_by}{until}), so this one did nothing. "
        "That run records and announces its own outcome."
    )


_WHAT_STOPPED_A_RUN: Final = {
    "STORE_PROFILE_NOT_CONFIGURED": (
        "the AWS profile it publishes with is not one this machine's AWS config defines"
    ),
    "STORE_ACCESS_DENIED": "this machine or the bucket refused it",
    "STORE_UNAVAILABLE": "a store did not answer",
    "STORE_CREDENTIALS_EXPIRED": "the AWS session had expired",
    "PROVIDER_UNAVAILABLE": "OpenCaselist did not answer",
    "PROVIDER_RATE_LIMITED": "OpenCaselist was limiting its requests",
    "NO_CASELISTS_CONFIGURED": "it was given no caselist to pull",
    "FULL_ARCHIVE_REFUSED": "the complete archive it was asked for cannot be fetched this run",
    "MANIFESTS_NOT_WRITABLE": "this build's local store cannot write manifests",
    "UNREADABLE_MANIFEST": "a manifest on this machine has a line nobody can read",
    UNMODELLED_ERROR_CODE: "an error nobody modelled, most likely a bug",
}
"""What a run that stopped before a stage could record it says it stopped on, by the error's code
(`v1-e34-t23`): in words, never the exception's class, which `v1-e34-t19` showed. A code with no
words here is named by its code; the run's details hold the hint, and `caselist runs` the class."""


def _what_stopped_it(codes: Sequence[str]) -> str:
    if not codes:
        return "an error with no code"
    return "; ".join(_WHAT_STOPPED_A_RUN.get(code, f"an error recorded as {code}") for code in codes)


_WHAT_WAS_CAPTURED_IS_KEPT: Final = "What was captured is kept."

STATUS_COMMAND: Final = "debate-research caselist status"
"""What says whether a removal is owed again: a held upload in the inbox, or a row at a held path
(`v1-e30-t21`)."""

HELD_BY_A_REMOVAL_TITLE: Final = "caselist pull: uploads held by a removal"
"""The title of a run whose imports refused an upload at a path a removal holds (`v1-e34-t23`)."""

PUBLISH_A_CASELIST_COMMAND: Final = "debate-research caselist publish --caselist"
"""What uploads a caselist's manifests this machine rewrote since they were published (`v1-e30-t12`)."""

MANIFEST_PUBLISHED_AGAIN_TITLE: Final = "caselist pull: publish a manifest again"
"""The title of a run whose only failed stage is the report, on a manifest mismatch alone that the
run owed again (`v1-e34-t23`, `v1-e34-t26`)."""


def _published_again(count: int) -> str:
    them, were = ("them", "manifests after they were") if count > 1 else ("it", "manifest after it was")
    return (
        f"The next scheduled run publishes {them} again: this machine rewrote the {were} published, "
        "and the publish uploads this machine's copy. Nothing here needs a person."
    )


MANIFEST_PUBLISHED_AGAIN: Final = _published_again(1)
"""What such a run says instead of a verdict. Since `v1-e34-t26` the report stage owes the snapshot
again, so the next scheduled run, or `--publish-pending` before it, is the retry that clears it.
Before, nothing owed it, and this sent the operator to `caselist publish`. The runbook quotes it."""

DRIFTED_AGAIN_TITLE: Final = "caselist pull: a manifest drifted again"
"""The title of a run whose report stage found a manifest drifting again after the run that owed it
again published it and the bucket confirmed it (`v1-e34-t26`). It is not owed a third time, and the
banner asks for a person, naming each snapshot by caselist and date. The runbook quotes it."""

LOCK_BANNER_WORDS: Final = "skipped"
"""What `caselist runs` shows beside the verdict of a run the lock refused (`v1-e34-t26`): the word
:data:`ANOTHER_RUN_HELD_THE_LOCK_TITLE` puts beside `caselist pull`."""

FIX_FIRST_BANNER_WORDS: Final = "retry once fixed"
"""What `caselist runs` shows beside the verdict of a refusal a retry gets past only once its fix is
made (`v1-e34-t26`): the run :data:`RETRIED_AFTER_ITS_FIX_TITLE` is the title of."""

THE_CHECK_WAS_CUT_SHORT: Final = (
    " The report stage's check that the bucket holds what this run published was cut short; "
    "the next pull, or caselist pull --publish-pending after the login, makes it again."
)
_THE_CLOUD_CHECK_WAS_CUT_SHORT: Final = (
    " The report stage's check that the bucket holds what this run published was cut short."
)
""":data:`THE_CHECK_WAS_CUT_SHORT` in bucket mode (`v1-e40-t22`), which names no command: the login
and the publish it names are the operator's Mac's, and the cloud run's are its task role's."""

CLOUD_NO_SESSION_RUNBOOK: Final = 'caselist-cloud-run.md, "A run that found no AWS session"'
"""The runbook section a bucket-mode login banner points to (`v1-e40-t22`)."""

CLOUD_NO_SESSION_CURE: Final = (
    "the PM looks into the cloud run's task role, which gave the run no AWS session "
    f"({CLOUD_NO_SESSION_RUNBOOK}); never a login and a publish from the operator's Mac"
)
"""The login banner's fix in bucket mode (`v1-e40-t22`), as its details' `bucket_run` says it was.

A cloud run's AWS session is its task role's, which ECS renews, so a run that found none points at the
role and goes to the PM. `aws sso login && caselist pull --publish-pending`, local mode's fix, would
publish snapshots from the working copy of the machine it was run on, never the cloud run's, which
ended with its task."""
"""What the login banner adds when the report stage is pending and the publish is not (`v1-e34-t26`).

The publish confirmed what it published, and the session then expired while the report stage
compared it with the bucket. Since `v1-e34-t28` the run's details name what the stage did not
compare, and the next pull, scheduled or by hand, or `--publish-pending` compares exactly that
(:func:`comparisons_owed_by_the_newest_run`). Before, nothing made the check but `caselist status`
by hand, and this sentence said so."""

type RetryRule = Callable[[Sequence[str]], bool]
"""Whether a run that failed on exactly these error codes may succeed on a retry.

The command's rule, handed in by the composition root: `debate_cli.exit_codes` decides which codes
a retry may cure, for the exit status, and the notification asks the same function so that the two
can never disagree. This package never names a code as retryable (`v1-e34-t13`).
"""


def _no_failure_is_known_to_be_transient(codes: Sequence[str]) -> bool:
    """The rule of a monitor that was given none: nothing is promised to pass by itself."""
    return False


def notifications_for(
    record: SyncRunRecord,
    details: SyncRunDetails,
    *,
    aws_login_command: str,
    credentials_expired: bool,
    may_succeed_on_retry: RetryRule = _no_failure_is_known_to_be_transient,
) -> list[Notification]:
    """One notification per condition the operator has to act on, each naming its fix.

    Built from the record's counts, stage names and error class and from the details' codes and
    hints only, never from a message, so nothing a record could not hold reaches the screen.

    **A failed run says which kind of failure it was** (`v1-e34-t19`). When a download, an import or
    a publish failed, or the run stopped on an error, the title and the message say either that the
    next scheduled run should retry it (:data:`RETRIED_BY_THE_NEXT_RUN`) or that a person should
    look (:data:`NEEDS_A_PERSON`). The first only when `may_succeed_on_retry` says so of the codes
    the exit status was decided from (:attr:`SyncRunDetails.failure_codes`), which is the command's
    own rule for exit `3`: the notification and the exit code are one decision. A stage outside
    those that had to finish, the parse stage for one, decides nothing about the exit and gets
    neither wording: the next scheduled run does not retry it.

    **A failed stage's hint is on the notification** (:attr:`Notification.hint`), as the summary
    gives it: the permission to fix on this machine, the grant the profile lacks, the file a person
    has to repair, the command that publishes a parsed store. Either verdict holds with a hint
    present; with the first, the hint is what has to be done before the retry helps.

    **A pending publish says what it found first.** A snapshot that ended incomplete on a code the
    rule does not call transient, before the session expired, is named on the login notification
    as needing a person: logging in will not publish it.

    **Words of their own** (`v1-e34-t23`). A run another held the lock against says so, and not that
    a person should look (:data:`ANOTHER_RUN_HELD_THE_LOCK`). The first verdict with a fix to make
    first says the retry is refused until it is made (:data:`RETRIED_AFTER_ITS_FIX`). A run that
    stopped says on what in words (:data:`_WHAT_STOPPED_A_RUN`), and no notification names an
    exception's class. Every notification's subtitle is the run and its environment, which a banner
    shows whole; the command is the first thing in its body (:attr:`Notification.body`).

    **The login banner names what waits** (`v1-e34-t26`): the snapshots owed, when there are any,
    and the run record; and, when the report stage was cut short with the publish already done, the
    check the next pull or `--publish-pending` makes again (:data:`THE_CHECK_WAS_CUT_SHORT`, `v1-e34-t28`).
    **In bucket mode it names no command** (`v1-e40-t22`), as the details' `bucket_run` says it was:
    its fix is the cloud run's task role, the PM's (:data:`CLOUD_NO_SESSION_CURE`), and what waits is
    said without the login and the publishes the operator's Mac would make.

    **A manifest owed again, and one that drifted again** (`v1-e34-t26`). A report stage's manifest
    mismatch alone is announced as published again by the next run when the record lists it as
    owed (:data:`MANIFEST_PUBLISHED_AGAIN`). One it does not list was not owed again, because it had
    been owed again already, published and confirmed, and drifted again: that run asks for a
    person (:data:`DRIFTED_AGAIN_TITLE`). Whether `caselist runs` shows words of a banner's own
    beside its verdict is :func:`banner_words`, which this function's titles agree with.
    """
    where = f"Run {record.run_id} ({record.environment})"
    sent: list[Notification] = []
    bucket = details.bucket_run
    if record.error_class == SyncRunInProgress.__name__:
        sent.append(
            Notification(
                title=ANOTHER_RUN_HELD_THE_LOCK_TITLE,
                message=f"{where}: {ANOTHER_RUN_HELD_THE_LOCK}",
                fix_command=RUNS_COMMAND,
            )
        )
    elif record.error_class == RunLockHeld.__name__:
        sent.append(
            Notification(
                title=ANOTHER_RUN_HELD_THE_LOCK_TITLE,
                message=f"{where}: {_bucket_lock_held(bucket)}",
                fix_command=RUNS_COMMAND,
            )
        )
    elif record.error_class == RunLockLost.__name__:
        sent.append(
            Notification(
                title=RUN_LOCK_LOST_TITLE, message=f"{where}: {RUN_LOCK_LOST}", fix_command=RUNS_COMMAND
            )
        )
    elif record.error_class == CaselistAuthExpired.__name__:
        sent.append(
            Notification(
                title="caselist pull stopped: OpenCaselist login expired",
                message=f"{where} was refused by OpenCaselist and fetched nothing more.",
                fix_command=AUTH_LOGIN_COMMAND,
            )
        )
    elif record.error_class is not None:
        retried = _retried_by_the_next_run(details.failure_codes, may_succeed_on_retry)
        title, verdict = _verdict(retried, fix_first=_a_fix_comes_first(record, details))
        sent.append(
            Notification(
                title=title,
                message=f"{where} stopped: {_what_stopped_it(details.failure_codes)}. {verdict}",
                fix_command=PULL_COMMAND,
                hint=details.hint,
            )
        )
    failed = [entry.stage for entry in record.stages if entry.outcome == str(StageOutcome.FAILED)]
    owed_again, drifted_again = _owed_again_or_not(
        _manifest_mismatches_alone(details.stage(str(SyncStage.REPORT)))
        if failed == [str(SyncStage.REPORT)]
        else (),
        record,
    )
    if drifted_again:
        # Owed again once already, published and confirmed, and drifting again: never a third time
        # by itself, and never silently (`v1-e34-t26`).
        sent.append(
            Notification(
                title=DRIFTED_AGAIN_TITLE,
                message=f"{where}: {_drifted_again(drifted_again)}"
                + (f" {_also_owed_again(owed_again)}" if owed_again else ""),
                fix_command=_status_commands(drifted_again),
            )
        )
    elif owed_again:
        # A manifest this machine rewrote is owed again, and the next run uploads it (`v1-e34-t26`).
        sent.append(
            Notification(
                title=MANIFEST_PUBLISHED_AGAIN_TITLE,
                message=(
                    f"{where}: the report stage found the bucket's {_manifests_of(owed_again)} "
                    f"{'differ' if len(owed_again) > 1 else 'differs'} from this machine's. "
                    f"{_published_again(len(owed_again))}"
                ),
                fix_command=PUBLISH_PENDING_COMMAND,
            )
        )
    elif failed:
        required = {str(stage) for stage in REQUIRED_STAGES}
        only_publish = set(failed) == {str(SyncStage.PUBLISH)}
        only_parse = set(failed) == {str(SyncStage.PARSE)}
        said = [details.stage(stage) for stage in failed]
        named = "; ".join(
            f"the {stage} stage failed"
            + (f" on {', '.join(one.error_codes)}" if one and one.error_codes else "")
            for stage, one in zip(failed, said, strict=True)
        )
        hints = list(dict.fromkeys(one.hint for one in said if one is not None and one.hint))
        if required.intersection(failed):
            retried = _retried_by_the_next_run(details.failure_codes, may_succeed_on_retry)
            title, verdict = _verdict(retried, fix_first=_a_fix_comes_first(record, details))
            verdict += " "
        else:
            title = "caselist pull finished with a failed stage"
            verdict = ""
        sent.append(
            Notification(
                title=title,
                message=f"{where}: {named}. {verdict}{_WHAT_WAS_CAPTURED_IS_KEPT}",
                fix_command=PUBLISH_PENDING_COMMAND
                if only_publish
                else parse_commands(details)
                if only_parse
                else PULL_COMMAND,
                hint=" ".join(hints) or None,
            )
        )
    if bucket is not None and bucket.took_over is not None:
        sent.append(
            Notification(
                title=TOOK_OVER_THE_LOCK_TITLE,
                message=f"{where} {bucket.took_over}. {TOOK_OVER_THE_LOCK}",
                fix_command=RUNS_COMMAND,
            )
        )
    if credentials_expired:
        owed = len(record.pending_publish)
        # `--publish-pending` publishes snapshots and run records, never a parsed store, so a parse
        # stage waiting on the same login is named with the command that does (`v1-e34-t17`).
        parse_waits = any(
            entry.stage == str(SyncStage.PARSE) and entry.outcome == str(StageOutcome.PENDING)
            for entry in record.stages
        )
        # Nor a search index: the next run with a session publishes it, or this by hand (`v1-e39-t09`).
        index_waits = (
            details.search_index
            if details.search_index is not None
            and _stage_outcome(record, SyncStage.SEARCH_INDEX) == str(StageOutcome.PENDING)
            else None
        )
        # What a stage had already found when the session expired that no later run cures by
        # itself. Only a pending stage records an earlier finding, so there is no outcome to ask.
        # A manifest the report found rewritten is the exception: it is owed again, and the publish
        # after the login uploads it (`v1-e34-t23`, `v1-e34-t26`); or it drifted again after it was,
        # and it is said so on its own.
        found_before = _manifest_mismatches_alone(details.stage(str(SyncStage.REPORT)))
        owed_again, drifted_again = _owed_again_or_not(found_before, record)
        found_first = dict.fromkeys(
            code
            for one in details.stages
            if not (found_before and one.stage == str(SyncStage.REPORT))
            for code in one.earlier_findings
            if not may_succeed_on_retry([code])
        )
        # The report stage cut short after a publish that was not: the next pull or
        # `--publish-pending` redoes its check, from this run's details (`v1-e34-t28`).
        report_alone = _stage_outcome(record, SyncStage.REPORT) == str(StageOutcome.PENDING) and (
            _stage_outcome(record, SyncStage.PUBLISH) != str(StageOutcome.PENDING)
        )
        sent.append(
            Notification(
                title="caselist publish waiting for an AWS login",
                message=(
                    f"{where} kept everything it fetched; "
                    + (
                        f"{owed} snapshot(s) and the run record wait to be published."
                        if owed
                        else "no snapshot waits to be published, only the run record."
                    )
                    + (
                        (_THE_CLOUD_CHECK_WAS_CUT_SHORT if bucket else THE_CHECK_WAS_CUT_SHORT)
                        if report_alone
                        else ""
                    )
                    + (
                        " A person should look as well: before the session expired a snapshot ended "
                        f"incomplete on {', '.join(found_first)}, which the login will not fix."
                        if found_first
                        else ""
                    )
                    + (
                        f" Before the session expired, the bucket's {_manifests_of(owed_again)} "
                        f"{'were' if len(owed_again) > 1 else 'was'} found to differ from this "
                        f"machine's; {'they are' if len(owed_again) > 1 else 'it is'} owed again, and "
                        "the publish after the login uploads this machine's copy."
                        if owed_again
                        else ""
                    )
                    + (
                        " A person should look as well: before the session expired, the bucket's "
                        f"{_manifests_of(drifted_again)} {'were' if len(drifted_again) > 1 else 'was'} "
                        "found to differ from this machine's again, after a run published "
                        f"{_them_or_it(drifted_again)} again and the bucket confirmed "
                        f"{_them_or_it(drifted_again)}; "
                        f"{'they are' if len(drifted_again) > 1 else 'it is'} not owed again."
                        if drifted_again
                        else ""
                    )
                    + (_the_parsed_store_waits_too(details) if parse_waits else "")
                    + (
                        f" The search index {index_waits.index_id} waits too."
                        if index_waits is not None and bucket is not None
                        else f" The search index {index_waits.index_id} waits too; the next run with a "
                        "session publishes it, or after the login: "
                        + SEARCH_INDEX_PUBLISH_COMMAND.format(environment=record.environment)
                        if index_waits is not None
                        else ""
                    )
                ),
                fix_command=CLOUD_NO_SESSION_CURE
                if bucket is not None
                else f"{aws_login_command} && {PUBLISH_PENDING_COMMAND}",
            )
        )
    if details.held_by_request:
        # A hold that refused an upload did its job; whether the removal is owed again is what
        # `caselist status` says (`v1-e30-t21`). By request id and count only (`v1-e34-t23`).
        held = ", ".join(
            f"{request_id} {count}" for request_id, count in sorted(details.held_by_request.items())
        )
        sent.append(
            Notification(
                title=HELD_BY_A_REMOVAL_TITLE,
                message=(
                    f"{where}: the import refused {sum(details.held_by_request.values())} upload(s) at a "
                    f"path a removal holds, by request: {held}. Nothing of them was stored."
                ),
                fix_command=STATUS_COMMAND,
            )
        )
    if record.backlog_growing:
        counts = ", ".join(
            f"{caselist} {record.deferred_by_caselist[caselist]}" for caselist in record.backlog_growing
        )
        sent.append(
            Notification(
                title="caselist backlog growing",
                message=(
                    f"{where}: archives deferred by the daily download cap have grown for "
                    f"{BACKLOG_GROWTH_RUNS} runs in a row ({counts})."
                ),
                fix_command=f"{PULL_COMMAND} (again tomorrow, when the day's downloads reset)",
            )
        )
    # Under the title, the run: short enough that a banner shows it whole (`v1-e34-t23`).
    return [replace(one, subtitle=where) for one in sent]


NOTHING_OWED_FOR_THE_PARSED_STORE: Final = (
    f"none owed: the parsed store was published ({CLOUD_FAILURE_RATE_RUNBOOK})"
)
"""A bucket-mode parse stage's fix line when its details say no parsed store is owed (`v1-e40-t08`):
a stage over its failure rate that published, whose failures are the PM's to look into."""


def parse_commands(details: SyncRunDetails) -> str:
    """What finishes a run's parse stage: each caselist owed, by its own command (`v1-e34-t31`).

    `caselist parse --caselist <slug> --publish-only` for a caselist whose details say the publish
    alone is owed, and `--publish` for every other, an entry that does not say included. Details
    that name no caselist, every earlier build's among them, give :data:`PARSE_COMMAND`, which
    rebuilds first: what cannot be told is never named `--publish-only`.

    **A bucket-mode run names no command** (`v1-e40-t18`), as its details' `bucket_run` says it was:
    the cloud run owns the parsed store, and a command run on the operator's Mac would publish the
    Mac's own working copy over it. Its cure is the next cloud run, which parses and publishes what
    is owed whether or not it imports into the caselist
    (:func:`~debate_core.application.caselist_sync.cloud_parse_cure`), whether or not the details
    name the caselists. **Details that say nothing is owed name no cure** (`v1-e40-t08`): a stage
    over its failure rate whose parsed store was published, whose fix line says so instead. Details
    with no `parsed_stores_owed` at all, which the cloud image before `v1-e34-t31` writes, cannot say
    that, and keep the cure.
    """
    if details.bucket_run is not None:
        if not details.parsed_stores_owed and "parsed_stores_owed" in details.model_fields_set:
            return NOTHING_OWED_FOR_THE_PARSED_STORE
        return cloud_parse_cure([one.caselist for one in details.parsed_stores_owed])
    if not details.parsed_stores_owed:
        return PARSE_COMMAND
    return "; ".join(
        parse_command(one.caselist, publish_only=one.publish_only) for one in details.parsed_stores_owed
    )


def _the_parsed_store_waits_too(details: SyncRunDetails) -> str:
    """The login banner's sentence for a parse stage pending on the same login (`v1-e34-t17`).

    In local mode, the commands to run after the login. In bucket mode, the cloud cure, which no
    login on the operator's Mac brings about (`v1-e40-t18`).
    """
    if details.bucket_run is not None:
        return f" The parsed store waits too: {parse_commands(details)}."
    return f" The parsed store waits too; after the login: {parse_commands(details)}"


def _verdict(retried: bool, *, fix_first: bool) -> tuple[str, str]:
    """A failed run's title and verdict sentence. `retried` is the command's rule, as ever."""
    if not retried:
        return NEEDS_A_PERSON_TITLE, NEEDS_A_PERSON
    if fix_first:
        return RETRIED_AFTER_ITS_FIX_TITLE, RETRIED_AFTER_ITS_FIX
    return RETRIED_BY_THE_NEXT_RUN_TITLE, RETRIED_BY_THE_NEXT_RUN


def _a_fix_comes_first(record: SyncRunRecord, details: SyncRunDetails) -> bool:
    """Whether the failure behind a failed run's verdict carries a fix to make before a retry helps.

    For a run that stopped on an error, the error's own hint; for one that recorded its stages, a
    hint on a failed stage the exit is decided from. One answer for the banner's title and for the
    words `caselist runs` shows beside the verdict (`v1-e34-t23`, `v1-e34-t26`).
    """
    if record.error_class is not None:
        return details.hint is not None
    required = {str(stage) for stage in REQUIRED_STAGES}
    for entry in record.stages:
        if entry.outcome != str(StageOutcome.FAILED) or entry.stage not in required:
            continue
        said = details.stage(entry.stage)
        if said is not None and said.hint:
            return True
    return False


def banner_words(
    record: SyncRunRecord,
    details: SyncRunDetails | None,
    *,
    may_succeed_on_retry: RetryRule = _no_failure_is_known_to_be_transient,
) -> str | None:
    """The words a run's banner put beside its verdict, for `caselist runs` (`v1-e34-t26`); else `None`.

    :data:`LOCK_BANNER_WORDS` for a run the lock refused, whose title is
    :data:`ANOTHER_RUN_HELD_THE_LOCK_TITLE`, and :data:`FIX_FIRST_BANNER_WORDS` for a failure the
    next run retries once its fix is made, whose title is :data:`RETRIED_AFTER_ITS_FIX_TITLE`. Decided
    as :func:`notifications_for` decides those titles, from the same record, details and rule. `None`
    for a run with no details: an older build recorded it, and the banner it showed is not known.
    """
    if details is None:
        return None
    if record.error_class in (SyncRunInProgress.__name__, RunLockHeld.__name__):
        return LOCK_BANNER_WORDS
    if record.error_class == CaselistAuthExpired.__name__:
        return None
    retried = _retried_by_the_next_run(details.failure_codes, may_succeed_on_retry)
    return FIX_FIRST_BANNER_WORDS if retried and _a_fix_comes_first(record, details) else None


def _stage_outcome(record: SyncRunRecord, stage: SyncStage) -> str | None:
    return next((entry.outcome for entry in record.stages if entry.stage == str(stage)), None)


def _owed_again_or_not(
    findings: Sequence[DriftFinding], record: SyncRunRecord
) -> tuple[tuple[DriftFinding, ...], tuple[DriftFinding, ...]]:
    """`findings` split into those the record lists as owed and those it does not (`v1-e34-t26`).

    A manifest mismatch alone that the record does not list was not owed again by the report stage:
    it had been owed again already and drifted again after its republish, or the pending-work file
    could not be read. A person should look either way.
    """
    owed = set(record.pending_publish)
    listed = tuple(one for one in findings if f"{one.caselist} {one.snapshot}" in owed)
    return listed, tuple(one for one in findings if one not in listed)


def _them_or_it(findings: Sequence[DriftFinding]) -> str:
    return "them" if len(findings) > 1 else "it"


def _drifted_again(findings: Sequence[DriftFinding]) -> str:
    many = len(findings) > 1
    it = _them_or_it(findings)
    return (
        f"the bucket's {_manifests_of(findings)} {'differ' if many else 'differs'} from this machine's "
        f"again, after a run published {it} again and the bucket confirmed {it}. Publishing {it} a "
        f"third time would not clear it, so {'they are' if many else 'it is'} not owed again: a person "
        "should look."
    )


def _also_owed_again(findings: Sequence[DriftFinding]) -> str:
    many = len(findings) > 1
    named = ", ".join(f"{one.caselist} {one.snapshot}" for one in findings)
    return (
        f"The manifest{'s' if many else ''} of {named} {'are' if many else 'is'} owed again, and the "
        f"next scheduled run publishes {_them_or_it(findings)}."
    )


def _status_commands(findings: Sequence[DriftFinding]) -> str:
    """One `caselist status --caselist <slug>` for each caselist named, in order, joined by `&&`."""
    return " && ".join(
        f"{STATUS_COMMAND} --caselist {caselist}"
        for caselist in dict.fromkeys(one.caselist for one in findings)
    )


def _manifest_mismatches_alone(report: StageDetails | None) -> tuple[DriftFinding, ...]:
    """The report stage's findings when each is a manifest mismatch and nothing else; else none.

    "Nothing else" is the stage's every code being `CASELIST_DRIFT`, failed or found before an
    expiry, and every snapshot's only kind being `manifest`: one snapshot with a source mismatch, a
    missing source, or a comparison that failed outright, and a person is still asked to look.
    """
    if report is None or not report.drift:
        return ()
    if {*report.error_codes, *report.earlier_findings} != {CASELIST_DRIFT}:
        return ()
    if any(one.kinds != (str(DriftKind.MANIFEST),) for one in report.drift):
        return ()
    return report.drift


def _manifests_of(findings: Sequence[DriftFinding]) -> str:
    """`manifest of <caselist> <snapshot>`, or `manifests of …, …` for more than one."""
    named = ", ".join(f"{one.caselist} {one.snapshot}" for one in findings)
    return f"manifest{'s' if len(findings) > 1 else ''} of {named}"


def _retried_by_the_next_run(codes: Sequence[str], may_succeed_on_retry: RetryRule) -> bool:
    """Whether a run that failed on `codes` is one the next scheduled run should retry.

    Never for a failure with no code at all: nothing reaches the first wording because nobody
    classified it.
    """
    return bool(codes) and may_succeed_on_retry(codes)


# ------------------------------------------------------------------------------------------------
# What earlier runs owed again for drift (`v1-e34-t26`)
# ------------------------------------------------------------------------------------------------


def snapshots_owed_again_for_drift(
    records: Sequence[SyncRunRecord], details: Mapping[str, SyncRunDetails]
) -> frozenset[PendingSnapshot]:
    """What an earlier run owed again because its manifest drifted, and every run since still owed.

    The report stage owes again a snapshot whose bucket manifest no longer matches this machine's,
    once (:class:`~debate_core.application.caselist_sync.CaselistSyncService`'s
    `_owe_drifted_manifests_again`). This is how it tells "drifted again" from a first drift, from
    the run log and the details as they are, with nothing added to either:

    * **Owed again for drift** at a run whose details say its report stage found the snapshot's
      manifest, and nothing else, differing from the bucket's (:attr:`StageDetails.drift`, kind
      `manifest` alone), and whose record lists the snapshot as owed (`pending_publish`, which is
      what the pending-work file held after the run).
    * **Still owed for that reason** while every later run's record lists it as owed too. A run in
      between that waited for a login keeps it so; one that confirmed it, or never owed it, ends it:
      the snapshot's next drift is a first one again.
    * **A run with no stages is passed over.** It stopped before any stage (the lock, a refused
      start, an error that escaped the run), so it touched nothing it owed, and its record lists
      nothing.

    A run whose details are missing, one an older build recorded or whose details could not be
    written, says nothing of drift. The guard is then one run late: it owes the snapshot a third
    time, and the run after it, whose details say, stops it.

    Args:
        records: The run log, oldest first (:meth:`SyncRunLog.read`).
        details: Each run's details, by run id (:meth:`SyncRunDetailsLog.read`).
    """
    report = str(SyncStage.REPORT)
    manifest_alone = (str(DriftKind.MANIFEST),)
    chain: set[str] | None = None
    found: set[str] = set()
    for record in reversed(records):
        if not record.stages:
            continue
        owed_here = set(record.pending_publish)
        chain = owed_here if chain is None else chain & owed_here
        beside = details.get(record.run_id)
        said = beside.stage(report) if beside is not None else None
        drifted_here = {
            f"{one.caselist} {one.snapshot}"
            for one in (said.drift if said is not None else ())
            if one.kinds == manifest_alone
        }
        settled = chain & drifted_here
        found |= settled
        chain -= settled
        if not chain:
            break
    return frozenset(PendingSnapshot(*one.split(" ", 1)) for one in sorted(found))


def comparisons_owed_by_the_newest_run(
    records: Sequence[SyncRunRecord], details: Mapping[str, SyncRunDetails]
) -> tuple[PendingSnapshot, ...]:
    """What the newest run published and its report stage did not compare: what the next run compares.

    The PM's ruling of 2026-10-22 (`v1-e34-t28`). A report stage that an expired session cut short
    names, in the run's details, what it had not compared yet (:attr:`StageDetails.not_compared`);
    the next pull, scheduled or by hand, or `--publish-pending` compares exactly those, through the
    report stage, and a run cut short again names what it did not reach. Only the newest run's:

    * **A run with no stages is passed over**, as :func:`snapshots_owed_again_for_drift` passes it
      over. It stopped before any stage (the lock, a refused start, an error that escaped the run),
      so it compared nothing and settled nothing. The run before it is the newest that ran.
    * **Any other run settles it**: it was handed the list, and compared it or named again what it
      did not reach. One that ran without a bucket compares nothing and settles it all the same.
    * **Details without the list** owe nothing: an older build wrote them, or they are missing.

    An entry that is not a target a publish would accept is passed over with a warning: the details
    are a file on this machine, and a name that has no place in the store is compared with nothing.

    Args:
        records: The run log, oldest first (:meth:`SyncRunLog.read`).
        details: Each run's details, by run id (:meth:`SyncRunDetailsLog.read`).
    """
    newest = next((record for record in reversed(records) if record.stages), None)
    beside = details.get(newest.run_id) if newest is not None else None
    said = beside.stage(str(SyncStage.REPORT)) if beside is not None else None
    owed: list[PendingSnapshot] = []
    for one in said.not_compared if said is not None else ():
        try:
            validate_publish_target(one.caselist, one.snapshot)
        except InvalidPublishTarget:
            logger.warning(
                "caselist run details: a snapshot owed a comparison has no place in the store; skipped"
            )
            continue
        owed.append(PendingSnapshot(caselist=one.caselist, snapshot=one.snapshot))
    return tuple(dict.fromkeys(owed))


# ------------------------------------------------------------------------------------------------
# The local log
# ------------------------------------------------------------------------------------------------


class SyncRunLog:
    """The JSONL run log: append one record per run, read them back oldest first."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def append(self, record: SyncRunRecord) -> None:
        """Add `record` as one line, in a single append so concurrent writers cannot interleave, and
        on the disk before this returns (`v1-e34-t23`; :func:`~debate_core.application.caselist_sync.
        append_state_line`)."""
        append_state_line(self.path, (record.model_dump_json() + "\n").encode("utf-8"))

    def read(self) -> list[SyncRunRecord]:
        """Every record, oldest first. A line that is not a valid record is skipped and logged."""
        if not self.path.is_file():
            return []
        records: list[SyncRunRecord] = []
        for number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                records.append(SyncRunRecord.model_validate_json(line))
            except ValidationError:
                logger.warning("caselist run log: line %d is not a valid run record; skipped", number)
        return records

    def last(self, count: int) -> list[SyncRunRecord]:
        """The `count` most recent records, newest first."""
        return list(reversed(self.read()))[: max(count, 0)]

    def by_run_id(self) -> dict[str, SyncRunRecord]:
        return {record.run_id: record for record in self.read()}

    def latest_listing(self, caselist: str) -> SyncRunRecord | None:
        """The most recent run that listed `caselist`'s archives, which is what knows its backlog."""
        for record in reversed(self.read()):
            if caselist in record.deferred_by_caselist:
                return record
        return None


class SyncRunDetailsLog:
    """The details file beside the run log: one :class:`SyncRunDetails` a line, read back by run id.

    Written like the run log and read more forgivingly, because it is the lesser file: a line this
    build cannot read, or a file it cannot open, is details that are absent, never a run that is.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def append(self, details: SyncRunDetails) -> None:
        """Add `details` as one line, written as the run log is (:meth:`SyncRunLog.append`)."""
        append_state_line(self.path, (details.model_dump_json() + "\n").encode("utf-8"))

    def read(self) -> dict[str, SyncRunDetails]:
        """Every run's details, by run id; the last line for a run id is the one kept."""
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return {}
        except (OSError, UnicodeDecodeError) as unreadable:
            logger.warning("caselist run details: could not be read (%s)", type(unreadable).__name__)
            return {}
        found: dict[str, SyncRunDetails] = {}
        for number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                details = SyncRunDetails.model_validate_json(line)
            except ValidationError:
                logger.warning(
                    "caselist run details: line %d is not details this build reads; skipped", number
                )
                continue
            found[details.run_id] = details
        return found


class _PendingRecords:
    """Run ids whose record the bucket does not have yet. A small JSON file, like `PendingWork`."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def read(self) -> list[str]:
        try:
            body: object = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if not isinstance(body, dict):
            return []
        run_ids = cast("dict[str, object]", body).get("run_ids")
        if not isinstance(run_ids, list):
            return []
        return [one for one in cast("list[object]", run_ids) if isinstance(one, str)]

    def write(self, run_ids: Sequence[str]) -> None:
        """Record exactly `run_ids`, on the disk as every state file of the sync is (`v1-e34-t23`).

        The same bytes as before: a JSON object of one key, so `sort_keys` changes nothing an older
        build reads.
        """
        if not run_ids:
            remove_state_file(self.path)
            return
        write_state_file(self.path, {"run_ids": list(run_ids)})


# ------------------------------------------------------------------------------------------------
# Reading records from the bucket
# ------------------------------------------------------------------------------------------------


async def read_remote_records(
    store: EvidenceObjectStore, *, last: int, scratch_dir: Path
) -> list[SyncRunRecord]:
    """The `last` most recent records in the bucket, newest first.

    Run ids sort as their start times do, and so do the keys, so the newest are the last keys.
    """
    return [
        one.record for one in await _read_remote(store, last=last, scratch_dir=scratch_dir, details=False)
    ]


async def read_remote_runs(store: EvidenceObjectStore, *, last: int, scratch_dir: Path) -> list[RecordedRun]:
    """The `last` most recent runs in the bucket, newest first, each with its details if it has any.

    One more listing than :func:`read_remote_records`, of the details' own prefix, so that a run
    an older build recorded costs no request for details it never had.
    """
    return await _read_remote(store, last=last, scratch_dir=scratch_dir, details=True)


async def _read_remote(
    store: EvidenceObjectStore, *, last: int, scratch_dir: Path, details: bool
) -> list[RecordedRun]:
    infos = await store.list_objects(SYNC_RUN_KEY_PREFIX)
    keys = sorted((info.key for info in infos if info.key.endswith(".json")), reverse=True)[: max(last, 0)]
    with_details = (
        {info.key for info in await store.list_objects(SYNC_RUN_DETAILS_KEY_PREFIX)}
        if details and keys
        else frozenset[str]()
    )
    runs: list[RecordedRun] = []
    scratch_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch_dir) as directory:
        for index, key in enumerate(keys):
            destination = Path(directory) / f"{index}.json"
            await store.get_file(key, destination)
            try:
                record = SyncRunRecord.model_validate_json(destination.read_text(encoding="utf-8"))
            except ValidationError:
                logger.warning("caselist run log: %s in the bucket is not a valid run record; skipped", key)
                continue
            beside = sync_run_details_key(key)
            found = (
                await _remote_details(store, beside, Path(directory) / f"{index}.details.json")
                if beside in with_details
                else None
            )
            runs.append(RecordedRun(record=record, details=found))
    return runs


async def _remote_details(store: EvidenceObjectStore, key: str, destination: Path) -> SyncRunDetails | None:
    """The details at `key`, or `None` when they are gone or are not details this build reads."""
    try:
        await store.get_file(key, destination)
    except NotFound:  # listed a moment ago and gone now: absent, as for a run that never had any
        return None
    try:
        return SyncRunDetails.model_validate_json(destination.read_text(encoding="utf-8"))
    except ValidationError:
        logger.warning("caselist run details: %s in the bucket is not details this build reads; skipped", key)
        return None


# ------------------------------------------------------------------------------------------------
# The monitor
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MonitoredRun:
    """What a monitored pull produced: the run's own summary, its record, and what was notified."""

    summary: RunSummary
    record: SyncRunRecord
    details: SyncRunDetails
    notifications: tuple[Notification, ...]
    record_published: bool


class SyncRunMonitor:
    """Wraps each `caselist pull` so that it always leaves a record and never fails silently.

    Built by the composition root::

        monitor = SyncRunMonitor(
            state_dir=settings.storage.data_dir,
            environment=settings.environment.value,
            notifier=MacOsNotifier(),
            remote=None,
            build_remote=build_the_bucket_or_none,
            aws_login_command="aws sso login --profile debate-dev-evidence",
        )
        monitored = await monitor.watch(lambda: service.run(slugs), caselists=slugs, mode="run")

    Args:
        state_dir: The environment's data directory: the run log and the pending-record file.
        environment: `dev` or `prod`, recorded on every record.
        notifier: Where notifications go.
        remote: The evidence bucket, already built, or `None`. What a test with a bucket in hand
            passes. Never together with `build_remote`.
        build_remote: Builds the evidence bucket, and is called when a record is first to be
            published: what the composition root passes, so that a bucket that cannot be built
            is a failure of the run the monitor records and not of building the monitor
            (`v1-e34-t22`). Whatever it raises leaves every record owed. `None`, with `remote`
            `None` too, is an environment with no bucket.
        aws_login_command: The command that renews this environment's AWS session.
        secrets: Values to scrub from every message, e.g. the caselist_token when it is known.
        clock: For the times of a run that raised before it could report its own.
        may_succeed_on_retry: The command's rule for which error codes a retry may cure
            (:data:`RetryRule`), which decides a failed run's wording in its notification. Left
            out, no failure is called transient.
    """

    def __init__(
        self,
        *,
        state_dir: Path,
        environment: str,
        notifier: Notifier,
        remote: EvidenceObjectStore | None,
        aws_login_command: str,
        secrets: Callable[[], Sequence[str]] = tuple,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        growth_runs: int = BACKLOG_GROWTH_RUNS,
        may_succeed_on_retry: RetryRule = _no_failure_is_known_to_be_transient,
        build_remote: Callable[[], EvidenceObjectStore] | None = None,
    ) -> None:
        if remote is not None and build_remote is not None:
            raise ValueError("a run monitor is given remote or build_remote, never both")
        self._may_succeed_on_retry = may_succeed_on_retry
        self._state_dir = Path(state_dir)
        self._environment = environment
        self._notifier = notifier
        # One way to the bucket, whether it was handed over built or to be built. `None` is an
        # environment with no bucket.
        self._build_remote: Callable[[], EvidenceObjectStore] | None = (
            build_remote if remote is None else lambda: remote
        )
        self._aws_login_command = aws_login_command
        self._secrets = secrets
        self._clock = clock
        self._growth_runs = growth_runs
        self.log = SyncRunLog(self._state_dir / SYNC_RUN_LOG_FILENAME)
        self.details = SyncRunDetailsLog(self._state_dir / SYNC_RUN_DETAILS_FILENAME)
        self._pending = _PendingRecords(self._state_dir / PENDING_RECORDS_FILENAME)

    async def watch(
        self,
        pull: Callable[[], Awaitable[RunSummary]],
        *,
        caselists: Sequence[str],
        mode: RunMode,
        bucket_run: Callable[[], BucketRunDetails | None] = lambda: None,
    ) -> MonitoredRun:
        """Run `pull` and record it. An exception is recorded, notified, and raised again.

        `bucket_run` is what a bucket-mode run has to add to its details (`v1-e40-t04`), asked once the
        run has ended. An error whose class says its record stays local (`record_stays_local`, a run
        that never held the bucket's run lock or lost it) is recorded on this machine and announced,
        and never published or owed to the bucket: it did not hold the lock (ADR-0020 (4)).
        """
        started = self._clock()
        try:
            summary = await pull()
        except Exception as error:
            run_id = started.astimezone(UTC).strftime(_RUN_ID_FORMAT)
            record = record_for_failure(
                error,
                run_id=run_id,
                started_at=started,
                finished_at=self._clock(),
                environment=self._environment,
                mode=mode,
                caselists=caselists,
                secrets=self._secret_values(),
            )
            bucket = bucket_run()
            stopped = details_for_failure(
                error, run_id=run_id, secrets=self._secret_values(), bucket_mode=bucket is not None
            )
            stopped = stopped.model_copy(update={"bucket_run": bucket})
            await self._finish(
                record,
                stopped,
                publish_pending_stage=False,
                local_only=bool(getattr(error, "record_stays_local", False)),
            )
            raise
        record = record_for_summary(
            summary,
            environment=self._environment,
            mode=mode,
            previous=self.log.read(),
            secrets=self._secret_values(),
            growth_runs=self._growth_runs,
        )
        publish_pending = any(
            _stage_is(summary, stage, StageOutcome.PENDING)
            for stage in (SyncStage.PUBLISH, SyncStage.REPORT, SyncStage.PARSE, SyncStage.SEARCH_INDEX)
        )
        details = details_for_summary(summary, secrets=self._secret_values())
        details = details.model_copy(update={"bucket_run": bucket_run()})
        notifications, published = await self._finish(record, details, publish_pending_stage=publish_pending)
        return MonitoredRun(
            summary=summary,
            record=record,
            details=details,
            notifications=tuple(notifications),
            record_published=published,
        )

    def pending_record_ids(self) -> list[str]:
        """Run ids whose record is still waiting to be published."""
        return self._pending.read()

    def snapshots_owed_again_for_drift(self) -> frozenset[PendingSnapshot]:
        """:func:`snapshots_owed_again_for_drift` over this machine's run log and details.

        A log this user cannot read says nothing, rather than stopping the run: the guard is then
        late, never the run (`v1-e34-t26`).
        """
        try:
            records = self.log.read()
        except (OSError, UnicodeDecodeError) as unreadable:
            logger.warning("caselist run log: could not be read (%s)", type(unreadable).__name__)
            return frozenset()
        return snapshots_owed_again_for_drift(records, self.details.read())

    def comparisons_owed(self) -> tuple[PendingSnapshot, ...]:
        """:func:`comparisons_owed_by_the_newest_run` over this machine's run log and details.

        A log this user cannot read owes nothing, rather than stopping the run, as for
        :meth:`snapshots_owed_again_for_drift` (`v1-e34-t28`).
        """
        try:
            records = self.log.read()
        except (OSError, UnicodeDecodeError) as unreadable:
            logger.warning("caselist run log: could not be read (%s)", type(unreadable).__name__)
            return ()
        return comparisons_owed_by_the_newest_run(records, self.details.read())

    async def _finish(
        self,
        record: SyncRunRecord,
        details: SyncRunDetails,
        *,
        publish_pending_stage: bool,
        local_only: bool = False,
    ) -> tuple[list[Notification], bool]:
        """Log, publish and notify, in that order: the local record exists before anything can fail."""
        self.log.append(record)
        self._keep(details)
        published, login_hint = (False, None) if local_only else await self._publish(record)
        credentials_expired = publish_pending_stage or login_hint is not None
        notifications = notifications_for(
            record,
            details,
            aws_login_command=login_hint or self._aws_login_command,
            credentials_expired=credentials_expired,
            may_succeed_on_retry=self._may_succeed_on_retry,
        )
        for notification in notifications:
            self._notifier.notify(notification)
        return notifications, published

    def _keep(self, details: SyncRunDetails) -> None:
        """Write the run's details beside its record. The record is already written, and stands
        whatever happens here: the details are the lesser file."""
        try:
            self.details.append(details)
        except OSError as refused:
            logger.warning(
                "caselist run details for %s not written: %s", details.run_id, type(refused).__name__
            )

    async def _publish(self, record: SyncRunRecord) -> tuple[bool, str | None]:
        """Publish this record and any still owed. Returns (this one published, login hint if expired).

        Each with its details, when this machine holds them, and the details first.
        """
        owed = [run_id for run_id in self._pending.read() if run_id != record.run_id] + [record.run_id]
        if self._build_remote is None:
            self._pending.write([])
            return False, None
        try:
            remote = self._build_remote()
        except Exception as unbuilt:
            # The bucket's adapter cannot be built: a profile the AWS config does not define, most
            # likely (`v1-e34-t22`). There is a bucket, so everything owed stays owed, this run's
            # record with it, for the next run that can build one. By its class and no more: the
            # message may be a library's.
            logger.warning(
                "caselist run record %s not published: the bucket's adapter could not be built (%s)",
                record.run_id,
                type(unbuilt).__name__,
            )
            self._pending.write(owed)
            return False, None
        known = self.log.by_run_id()
        beside = self.details.read()
        left: list[str] = []
        login_hint: str | None = None
        for index, run_id in enumerate(owed):
            to_publish = known.get(run_id)
            if to_publish is None:
                continue
            try:
                await self._put(remote, to_publish, beside.get(run_id))
            except StoreCredentialsExpired as expired:
                login_hint = expired.hint or self._aws_login_command
                left.extend(owed[index:])
                break
            except StoreError as refused:
                logger.warning("caselist run record %s not published: %s", run_id, type(refused).__name__)
                left.append(run_id)
        self._pending.write(left)
        return record.run_id not in left, login_hint

    async def _put(
        self, remote: EvidenceObjectStore, record: SyncRunRecord, details: SyncRunDetails | None
    ) -> None:
        """The record, and its details before it: a record in the bucket never waits for them, and
        a run whose details did not go up is still owed as a whole."""
        self._state_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self._state_dir, prefix=".sync-run-") as directory:
            if details is not None:
                beside = Path(directory) / f"{record.run_id}.details.json"
                beside.write_text(details.model_dump_json(indent=2) + "\n", encoding="utf-8")
                await remote.put_file(sync_run_details_key(record.object_key), beside)
            body = Path(directory) / f"{record.run_id}.json"
            body.write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8")
            await remote.put_file(record.object_key, body)

    def _secret_values(self) -> list[str]:
        return [value for value in self._secrets() if value]


# ------------------------------------------------------------------------------------------------
# Reading the history back: `caselist runs`
# ------------------------------------------------------------------------------------------------


class SyncRunHistory:
    """Recent runs from the local log or the bucket, and whether the schedule has gone quiet.

    The second half is what makes a run that *did not happen* visible. A run that failed leaves a
    record and a notification; a launchd agent that stopped firing leaves nothing, and the only
    sign is that the newest record keeps getting older.
    """

    def __init__(
        self,
        *,
        log: SyncRunLog,
        remote: Callable[[], EvidenceObjectStore] | None,
        scratch_dir: Path,
        overdue_after_days: int,
        details: SyncRunDetailsLog | None = None,
    ) -> None:
        self._log = log
        # Beside the run log unless told otherwise: the two files are one run's two halves.
        self._details = details or SyncRunDetailsLog(log.path.with_name(SYNC_RUN_DETAILS_FILENAME))
        self._remote = remote
        self._scratch_dir = Path(scratch_dir)
        self.overdue_after_days = overdue_after_days

    async def recent(self, last: int, *, remote: bool = False) -> list[SyncRunRecord]:
        """The `last` most recent records, newest first, from the log or (`remote`) the bucket."""
        if not remote:
            return self._log.last(last)
        if self._remote is None:
            raise NoRemoteRunLog
        return await read_remote_records(self._remote(), last=last, scratch_dir=self._scratch_dir)

    async def recent_runs(self, last: int, *, remote: bool = False) -> list[RecordedRun]:
        """:meth:`recent`, each record with the details of the same run id when there are any.

        What `caselist runs` shows (`v1-e34-t19`). A run an older build recorded has no details.
        """
        if not remote:
            beside = self._details.read()
            return [
                RecordedRun(record=record, details=beside.get(record.run_id))
                for record in self._log.last(last)
            ]
        if self._remote is None:
            raise NoRemoteRunLog
        return await read_remote_runs(self._remote(), last=last, scratch_dir=self._scratch_dir)

    def days_since_last_run(self, records: Sequence[SyncRunRecord], now: datetime) -> int | None:
        """Whole days since the newest of `records` started, or `None` when there are none."""
        if not records:
            return None
        newest = max(record.started_at for record in records)
        return (now - newest).days

    def overdue(self, records: Sequence[SyncRunRecord], now: datetime) -> bool:
        """No run at all, or none for longer than a weekly schedule plus a day of grace."""
        days = self.days_since_last_run(records, now)
        return days is None or days > self.overdue_after_days


class NoRemoteRunLog(DomainError):
    """`--remote` was asked for in an environment that names no evidence bucket."""

    def __init__(self) -> None:
        super().__init__(
            "this environment names no evidence bucket, so there is no remote run log to read; "
            "drop --remote to read this machine's log"
        )
