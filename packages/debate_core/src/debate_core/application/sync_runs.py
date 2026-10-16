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
* the parse stage's nine counts, or nothing when the stage did not run.

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
import os
import re
import tempfile
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Final, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from debate_core.application.caselist_sync import (
    REQUIRED_STAGES,
    RunSummary,
    StageOutcome,
    SyncStage,
    fix_for,
)
from debate_core.application.errors import (
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
    "BACKLOG_GROWTH_RUNS",
    "NEEDS_A_PERSON",
    "NEEDS_A_PERSON_TITLE",
    "PENDING_RECORDS_FILENAME",
    "RETRIED_BY_THE_NEXT_RUN",
    "RETRIED_BY_THE_NEXT_RUN_TITLE",
    "SYNC_RUN_DETAILS_FILENAME",
    "SYNC_RUN_DETAILS_KEY_PREFIX",
    "SYNC_RUN_KEY_PREFIX",
    "SYNC_RUN_LOG_FILENAME",
    "MonitoredRun",
    "NoRemoteRunLog",
    "ParseCounts",
    "RecordedRun",
    "RetryRule",
    "RunMode",
    "StageDetails",
    "StageEntry",
    "SyncRunDetails",
    "SyncRunDetailsLog",
    "SyncRunHistory",
    "SyncRunLog",
    "SyncRunMonitor",
    "SyncRunOutcome",
    "SyncRunRecord",
    "details_for_failure",
    "details_for_summary",
    "hint_for_a_record",
    "notifications_for",
    "read_remote_records",
    "read_remote_runs",
    "record_for_failure",
    "record_for_summary",
    "redact",
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
    """Captured locally; publishing waits for an AWS login."""

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
    if stage is SyncStage.PARSE:
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
            )
            for record in summary.stages
            if record.error_codes or record.hint or record.earlier_findings
        ),
        failure_codes=summary.failure_codes,
        parse=ParseCounts(**summary.parse.as_json()) if summary.parse is not None else None,
    )


def details_for_failure(error: BaseException, *, run_id: str, secrets: Sequence[str] = ()) -> SyncRunDetails:
    """The details of a run that raised instead of returning a summary.

    Its one failure code is the code the CLI reports the error under, and its hint the fix a stage
    would have given the same error.
    """
    hint = fix_for(error)
    return SyncRunDetails(
        run_id=run_id,
        failure_codes=(reported_error_code(error),),
        hint=hint_for_a_record(hint, secrets=secrets) if hint else None,
    )


def _outcome_of(summary: RunSummary) -> SyncRunOutcome:
    if not summary.succeeded:
        return SyncRunOutcome.FAILED
    if summary.pending_publish or _stage_is(summary, SyncStage.PUBLISH, StageOutcome.PENDING):
        return SyncRunOutcome.PUBLISH_PENDING
    if _stage_is(summary, SyncStage.PARSE, StageOutcome.PENDING):
        # The parsed store's publish is a publish, and it waits for the same login (`v1-e34-t17`).
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
"""What finishes a parse stage that failed (`v1-e34-t17`). Running the pull again does not: a pull
that imports nothing parses nothing. The stage's reason in `caselist runs` names the caselists."""


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

_WHAT_WAS_CAPTURED_IS_KEPT: Final = "What was captured is kept."

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
    """
    where = f"Run {record.run_id} ({record.environment})"
    sent: list[Notification] = []
    if record.error_class == CaselistAuthExpired.__name__:
        sent.append(
            Notification(
                title="caselist pull stopped: OpenCaselist login expired",
                message=f"{where} was refused by OpenCaselist and fetched nothing more.",
                fix_command=AUTH_LOGIN_COMMAND,
            )
        )
    elif record.error_class is not None:
        retried = _retried_by_the_next_run(details.failure_codes, may_succeed_on_retry)
        sent.append(
            Notification(
                title=RETRIED_BY_THE_NEXT_RUN_TITLE if retried else NEEDS_A_PERSON_TITLE,
                message=(
                    f"{where} stopped with {record.error_class}. "
                    f"{RETRIED_BY_THE_NEXT_RUN if retried else NEEDS_A_PERSON}"
                ),
                fix_command=PULL_COMMAND,
                hint=details.hint,
            )
        )
    failed = [entry.stage for entry in record.stages if entry.outcome == str(StageOutcome.FAILED)]
    if failed:
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
            title = RETRIED_BY_THE_NEXT_RUN_TITLE if retried else NEEDS_A_PERSON_TITLE
            verdict = f"{RETRIED_BY_THE_NEXT_RUN if retried else NEEDS_A_PERSON} "
        else:
            title = "caselist pull finished with a failed stage"
            verdict = ""
        sent.append(
            Notification(
                title=title,
                message=f"{where}: {named}. {verdict}{_WHAT_WAS_CAPTURED_IS_KEPT}",
                fix_command=PUBLISH_PENDING_COMMAND
                if only_publish
                else PARSE_COMMAND
                if only_parse
                else PULL_COMMAND,
                hint=" ".join(hints) or None,
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
        # What a stage had already found when the session expired that no later run cures by
        # itself. Only a pending stage records an earlier finding, so there is no outcome to ask.
        found_first = dict.fromkeys(
            code
            for one in details.stages
            for code in one.earlier_findings
            if not may_succeed_on_retry([code])
        )
        sent.append(
            Notification(
                title="caselist publish waiting for an AWS login",
                message=(
                    f"{where} kept everything it fetched; {owed} snapshot(s) and the run record "
                    "wait to be published."
                    + (
                        " A person should look as well: before the session expired a snapshot ended "
                        f"incomplete on {', '.join(found_first)}, which the login will not fix."
                        if found_first
                        else ""
                    )
                    + (
                        f" The parsed store waits too; after the login: {PARSE_COMMAND}"
                        if parse_waits
                        else ""
                    )
                ),
                fix_command=f"{aws_login_command} && {PUBLISH_PENDING_COMMAND}",
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
    return sent


def _retried_by_the_next_run(codes: Sequence[str], may_succeed_on_retry: RetryRule) -> bool:
    """Whether a run that failed on `codes` is one the next scheduled run should retry.

    Never for a failure with no code at all: nothing reaches the first wording because nobody
    classified it.
    """
    return bool(codes) and may_succeed_on_retry(codes)


# ------------------------------------------------------------------------------------------------
# The local log
# ------------------------------------------------------------------------------------------------


class SyncRunLog:
    """The JSONL run log: append one record per run, read them back oldest first."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def append(self, record: SyncRunRecord) -> None:
        """Add `record` as one line, in a single append so concurrent writers cannot interleave."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = (record.model_dump_json() + "\n").encode("utf-8")
        descriptor = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(descriptor, line)
        finally:
            os.close(descriptor)

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
        """Add `details` as one line, in a single append so concurrent writers cannot interleave."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = (details.model_dump_json() + "\n").encode("utf-8")
        descriptor = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(descriptor, line)
        finally:
            os.close(descriptor)

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
        if not run_ids:
            self.path.unlink(missing_ok=True)
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.incoming")
        temporary.write_text(json.dumps({"run_ids": list(run_ids)}, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self.path)


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
    ) -> MonitoredRun:
        """Run `pull` and record it. An exception is recorded, notified, and raised again."""
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
            stopped = details_for_failure(error, run_id=run_id, secrets=self._secret_values())
            await self._finish(record, stopped, publish_pending_stage=False)
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
            for stage in (SyncStage.PUBLISH, SyncStage.REPORT, SyncStage.PARSE)
        )
        details = details_for_summary(summary, secrets=self._secret_values())
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

    async def _finish(
        self, record: SyncRunRecord, details: SyncRunDetails, *, publish_pending_stage: bool
    ) -> tuple[list[Notification], bool]:
        """Log, publish and notify, in that order: the local record exists before anything can fail."""
        self.log.append(record)
        self._keep(details)
        published, login_hint = await self._publish(record)
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
