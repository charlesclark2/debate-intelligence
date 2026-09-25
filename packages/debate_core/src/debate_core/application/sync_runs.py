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
  as does a backlog of cap-deferred archives that has grown for two runs in a row.

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
)
from debate_core.application.errors import DomainError, StoreCredentialsExpired, StoreError
from debate_core.application.ports.caselist_source import CaselistAuthExpired
from debate_core.application.ports.evidence_store import EvidenceObjectStore, validate_object_key
from debate_core.application.ports.notifier import Notification, Notifier

__all__ = [
    "BACKLOG_GROWTH_RUNS",
    "PENDING_RECORDS_FILENAME",
    "SYNC_RUN_KEY_PREFIX",
    "SYNC_RUN_LOG_FILENAME",
    "MonitoredRun",
    "RunMode",
    "StageEntry",
    "SyncRunLog",
    "SyncRunMonitor",
    "SyncRunOutcome",
    "SyncRunRecord",
    "notifications_for",
    "read_remote_records",
    "record_for_failure",
    "record_for_summary",
    "redact",
    "sync_run_key",
]

logger = logging.getLogger(__name__)

SYNC_RUN_LOG_FILENAME: Final = "caselist-sync-runs.jsonl"
"""The local run log, one JSON record per line, under the environment's data directory."""

SYNC_RUN_KEY_PREFIX: Final = "reports/sync-runs/"
"""Where records go in the evidence bucket: `reports/sync-runs/<yyyy>/<run-id>.json`."""

PENDING_RECORDS_FILENAME: Final = "caselist-sync-records-pending.json"
"""Run ids whose record is in the local log and not yet in the bucket."""

BACKLOG_GROWTH_RUNS: Final = 2
"""How many consecutive runs a caselist's cap-deferred backlog must grow for before it notifies.

From the spec (ac5): "a backlog that clears itself next week is not a notification, one that
grows for two runs is". Still to be checked against a measured dev run of three caselists; see
the session report's operator follow-ups.
"""

RECORD_SCHEMA_VERSION: Final = 1

_RUN_ID_FORMAT: Final = "%Y%m%dT%H%M%SZ"
"""The run id `CaselistSyncService` gives a run, from its start time in UTC."""

_MAX_MESSAGE_CHARACTERS: Final = 500

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
    """One stage of the run: its name, how it ended, and its (redacted) one-line reason."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: str
    outcome: str
    reason: str | None = None


class SyncRunRecord(BaseModel):
    """One `caselist pull`, as the run log and the bucket keep it.

    Counts, slugs, dates, stage outcomes and error classes. See the module docstring for what may
    never be in one, and :func:`redact` for how messages are made safe.
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


# ------------------------------------------------------------------------------------------------
# Redaction
# ------------------------------------------------------------------------------------------------

REDACTED: Final = "[redacted]"

_COOKIE_VALUE = re.compile(r"(caselist_token\s*[=:]\s*)[^;,\s\"']+", re.IGNORECASE)
_URL_QUERY = re.compile(r"(https?://[^\s\"'?#]+)\?[^\s\"'#]*")
_QUOTED_PATH = re.compile(r"""(['"])[^'"\n]*[/\\][^'"\n]*\1""")
_PATH_TOKEN = re.compile(r"[^\s'\"]*[/\\][^\s'\"]*")


def redact(message: str, *, secrets: Iterable[str] = ()) -> str:
    """`message` with secrets, URL queries and anything path-shaped removed, on one short line.

    A path goes whole, including a quoted one with spaces in it, because a disclosure path names a
    school, a team code and a round, and `OSError` quotes the path it failed on.
    """
    text = message
    for secret in secrets:
        if secret:
            text = text.replace(secret, REDACTED)
    text = _COOKIE_VALUE.sub(lambda match: match.group(1) + REDACTED, text)
    text = _URL_QUERY.sub(lambda match: match.group(1) + "?" + REDACTED, text)
    text = _QUOTED_PATH.sub(REDACTED, text)
    text = _PATH_TOKEN.sub(REDACTED, text)
    text = " ".join(text.split())
    if len(text) > _MAX_MESSAGE_CHARACTERS:
        text = text[: _MAX_MESSAGE_CHARACTERS - 1] + "…"
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
                reason=redact(record.reason, secrets=secrets) if record.reason is not None else None,
            )
            for record in summary.stages
        ),
    )


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


def _outcome_of(summary: RunSummary) -> SyncRunOutcome:
    if not summary.succeeded:
        return SyncRunOutcome.FAILED
    if summary.pending_publish or _stage_is(summary, SyncStage.PUBLISH, StageOutcome.PENDING):
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


def notifications_for(
    record: SyncRunRecord,
    *,
    aws_login_command: str,
    credentials_expired: bool,
) -> list[Notification]:
    """One notification per condition the operator has to act on, each naming its fix.

    Built from the record's counts, stage names and error class only — never from a message — so
    nothing a record could not hold reaches the screen.
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
        sent.append(
            Notification(
                title="caselist pull failed",
                message=f"{where} stopped with {record.error_class}.",
                fix_command=PULL_COMMAND,
            )
        )
    failed = [entry.stage for entry in record.stages if entry.outcome == str(StageOutcome.FAILED)]
    if failed:
        required = {str(stage) for stage in REQUIRED_STAGES}
        only_publish = set(failed) == {str(SyncStage.PUBLISH)}
        sent.append(
            Notification(
                title="caselist pull failed"
                if required.intersection(failed)
                else "caselist pull finished with a failed stage",
                message=f"{where}: the {', '.join(failed)} stage failed. What was captured is kept.",
                fix_command=PUBLISH_PENDING_COMMAND if only_publish else PULL_COMMAND,
            )
        )
    if credentials_expired:
        owed = len(record.pending_publish)
        sent.append(
            Notification(
                title="caselist publish waiting for an AWS login",
                message=(
                    f"{where} kept everything it fetched; {owed} snapshot(s) and the run record "
                    "wait to be published."
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
    infos = await store.list_objects(SYNC_RUN_KEY_PREFIX)
    keys = sorted((info.key for info in infos if info.key.endswith(".json")), reverse=True)[: max(last, 0)]
    records: list[SyncRunRecord] = []
    scratch_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch_dir) as directory:
        for index, key in enumerate(keys):
            destination = Path(directory) / f"{index}.json"
            await store.get_file(key, destination)
            try:
                records.append(SyncRunRecord.model_validate_json(destination.read_text(encoding="utf-8")))
            except ValidationError:
                logger.warning("caselist run log: %s in the bucket is not a valid run record; skipped", key)
    return records


# ------------------------------------------------------------------------------------------------
# The monitor
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MonitoredRun:
    """What a monitored pull produced: the run's own summary, its record, and what was notified."""

    summary: RunSummary
    record: SyncRunRecord
    notifications: tuple[Notification, ...]
    record_published: bool


class SyncRunMonitor:
    """Wraps each `caselist pull` so that it always leaves a record and never fails silently.

    Built by the composition root::

        monitor = SyncRunMonitor(
            state_dir=settings.storage.data_dir,
            environment=settings.environment.value,
            notifier=MacOsNotifier(),
            remote=bucket_or_none,
            aws_login_command="aws sso login --profile debate-dev-evidence",
        )
        monitored = await monitor.watch(lambda: service.run(slugs), caselists=slugs, mode="run")

    Args:
        state_dir: The environment's data directory: the run log and the pending-record file.
        environment: `dev` or `prod`, recorded on every record.
        notifier: Where notifications go.
        remote: The evidence bucket, or `None` for an environment with no bucket.
        aws_login_command: The command that renews this environment's AWS session.
        secrets: Values to scrub from every message, e.g. the caselist_token when it is known.
        clock: For the times of a run that raised before it could report its own.
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
    ) -> None:
        self._state_dir = Path(state_dir)
        self._environment = environment
        self._notifier = notifier
        self._remote = remote
        self._aws_login_command = aws_login_command
        self._secrets = secrets
        self._clock = clock
        self._growth_runs = growth_runs
        self.log = SyncRunLog(self._state_dir / SYNC_RUN_LOG_FILENAME)
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
            record = record_for_failure(
                error,
                run_id=started.astimezone(UTC).strftime(_RUN_ID_FORMAT),
                started_at=started,
                finished_at=self._clock(),
                environment=self._environment,
                mode=mode,
                caselists=caselists,
                secrets=self._secret_values(),
            )
            await self._finish(record, publish_pending_stage=False)
            raise
        record = record_for_summary(
            summary,
            environment=self._environment,
            mode=mode,
            previous=self.log.read(),
            secrets=self._secret_values(),
            growth_runs=self._growth_runs,
        )
        publish_pending = _stage_is(summary, SyncStage.PUBLISH, StageOutcome.PENDING) or _stage_is(
            summary, SyncStage.REPORT, StageOutcome.PENDING
        )
        notifications, published = await self._finish(record, publish_pending_stage=publish_pending)
        return MonitoredRun(
            summary=summary, record=record, notifications=tuple(notifications), record_published=published
        )

    def pending_record_ids(self) -> list[str]:
        """Run ids whose record is still waiting to be published."""
        return self._pending.read()

    async def _finish(
        self, record: SyncRunRecord, *, publish_pending_stage: bool
    ) -> tuple[list[Notification], bool]:
        """Log, publish and notify, in that order: the local record exists before anything can fail."""
        self.log.append(record)
        published, login_hint = await self._publish(record)
        credentials_expired = publish_pending_stage or login_hint is not None
        notifications = notifications_for(
            record,
            aws_login_command=login_hint or self._aws_login_command,
            credentials_expired=credentials_expired,
        )
        for notification in notifications:
            self._notifier.notify(notification)
        return notifications, published

    async def _publish(self, record: SyncRunRecord) -> tuple[bool, str | None]:
        """Publish this record and any still owed. Returns (this one published, login hint if expired)."""
        owed = [run_id for run_id in self._pending.read() if run_id != record.run_id] + [record.run_id]
        if self._remote is None:
            self._pending.write([])
            return False, None
        known = self.log.by_run_id()
        left: list[str] = []
        login_hint: str | None = None
        for index, run_id in enumerate(owed):
            to_publish = known.get(run_id)
            if to_publish is None:
                continue
            try:
                await self._put(self._remote, to_publish)
            except StoreCredentialsExpired as expired:
                login_hint = expired.hint or self._aws_login_command
                left.extend(owed[index:])
                break
            except StoreError as refused:
                logger.warning("caselist run record %s not published: %s", run_id, type(refused).__name__)
                left.append(run_id)
        self._pending.write(left)
        return record.run_id not in left, login_hint

    async def _put(self, remote: EvidenceObjectStore, record: SyncRunRecord) -> None:
        self._state_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self._state_dir, prefix=".sync-run-") as directory:
            body = Path(directory) / f"{record.run_id}.json"
            body.write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8")
            await remote.put_file(record.object_key, body)

    def _secret_values(self) -> list[str]:
        return [value for value in self._secrets() if value]
