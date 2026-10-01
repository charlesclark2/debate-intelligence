"""Carrying out a removal, and reversing a mistaken one: `caselist remove --execute` and `unsuppress`.

:class:`CaselistRemovalService` executes a
:class:`~debate_core.application.caselist.removal_plan.RemovalPlan` — the plan the operator read in
the dry run, worked out again at the moment of execution — and nothing else. Every manifest it
writes is the text the plan already holds; every object it deletes is one the plan names.

## Two credentials, and why the second is checked before anything happens

Deleting evidence is the `EvidenceRemoval` permission set's alone (`DEBATE_REMOVAL_PROFILE`, from
`v1-e29-t03`); the everyday `EvidenceOperator` profile cannot delete at all, by design. So execution
holds both: the takedown credential to list and delete versions and to append the suppression list
and the removal log under `manifests/_suppression/`, and the everyday one to write rewritten
manifests, because `EvidenceRemoval` may write nowhere but `manifests/_suppression/`. The everyday
one also reads the bucket's copies of the list and the log before each append: `EvidenceRemoval`
has no `s3:ListBucket`, so S3 answers its read of a copy that does not exist yet with 403 rather
than 404, which is how the first real-dev `--execute` stopped (2026-10-01).

Before the first change, :func:`preflight` proves the takedown credential can do what the removal
needs: it writes a probe object under `manifests/_suppression/preflight/`, lists its versions,
deletes them, and checks they are gone. An unset profile, an expired session, or the everyday profile
named by mistake all fail there, with nothing deleted and nothing appended (spec ac6).

## The order is the safety

1. **Suppress first.** The entries go on the list — this machine's copy and the bucket's — before
   anything is deleted, so if the run stops part-way, the next weekly import still cannot bring the
   file back.
2. **The bucket**: every version of every `raw/` and `parsed/` object, listed again with the
   takedown credential so nothing the dry run could not see is missed; then each rewritten
   manifest, written and every superseded version of it purged; then every noncurrent version of
   any other manifest of the same caselists that still names what was removed.
3. **This machine**: blobs and parsed files, then manifests, then — last — the records. The
   records are what a re-run resolves a `--team` from, so they outlive every other step.
4. **The removal log**, one entry, `COMPLETED` or `INCOMPLETE` with the error's code. An incomplete
   run is finished by running the same command again; nothing is retried behind the operator's back.

## What it never deletes

Anything under `manifests/_suppression/` but its own preflight probe
(:func:`refuse_protected_versions`): the suppression list and the removal log are append-only and
their versions are the record of what was asked. And nothing under `reports/`, which IAM would refuse
anyway.
"""

from __future__ import annotations

import json
import re
import tempfile
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.publish_service import error_code_of
from debate_core.application.caselist.removal_plan import (
    Disposition,
    InvalidRemovalRequest,
    ManifestRewrite,
    ObjectKind,
    RemovalPlan,
    RemovalPlanner,
    RemovalSelector,
    Side,
    TeamSelector,
)
from debate_core.application.caselist.suppression import (
    REMOVAL_LOG_KEY,
    SUPPRESSION_LIST_KEY,
    SUPPRESSION_PREFIX,
    ObjectStoreAppendOnlyRecord,
    RecordedRemovalLog,
    RecordedSuppressionList,
    load_suppression_state,
)
from debate_core.application.errors import (
    DomainError,
    StoreAccessDenied,
    StoreCredentialsExpired,
    StoreError,
)
from debate_core.application.ports.caselist import CaselistRepository
from debate_core.application.ports.evidence_store import EvidenceObjectStore, ObjectKey
from debate_core.application.ports.evidence_versions import EvidenceVersionStore, ObjectVersion
from debate_core.application.ports.providers import Clock
from debate_core.application.ports.suppression import (
    REINSTATEMENT_REASONS,
    REQUEST_ID_PATTERN,
    AppendOnlyRecord,
    ReasonCode,
    RemovalLogEntry,
    RemovalLogKind,
    RemovalOutcome,
    SuppressionAction,
    SuppressionEntry,
    SuppressionList,
    SuppressionState,
    disclosure_digest,
)
from debate_core.domain import SHA256_HEX_PATTERN

__all__ = [
    "PREFLIGHT_PREFIX",
    "CaselistRemovalService",
    "NotSuppressed",
    "RemovalIncomplete",
    "RemovalReport",
    "TakedownAccess",
    "TakedownNotConfigured",
    "TakedownPreflightFailed",
    "UnsuppressPlan",
    "UnsuppressReport",
    "preflight",
    "refuse_protected_versions",
]

PREFLIGHT_PREFIX: Final = f"{SUPPRESSION_PREFIX}preflight/"
"""Where :func:`preflight` writes and deletes its probe: the one place the takedown credential may write."""


class TakedownNotConfigured(DomainError):
    """`DEBATE_REMOVAL_PROFILE` is not set, so there is no credential that may delete. Nothing was changed."""

    def __init__(self) -> None:
        super().__init__(
            "--execute needs the takedown profile: set DEBATE_REMOVAL_PROFILE to this environment's "
            "EvidenceRemoval profile (debate-dev-evidence-removal or debate-prod-evidence-removal) and sign "
            "in to it; nothing was deleted"
        )


class TakedownPreflightFailed(DomainError):
    """The takedown profile could not write, list or delete its probe. Nothing was deleted or appended."""

    def __init__(
        self, profile: str | None, step: str, failure: BaseException, *, left: ObjectKey | None = None
    ) -> None:
        self.profile = profile
        self.step = step
        self.hint = getattr(failure, "hint", None) or (
            f"aws sso login --profile {profile}" if profile else "set DEBATE_REMOVAL_PROFILE"
        )
        leftover = f"; its probe object was left at {left}" if left else ""
        super().__init__(
            f"the takedown profile {profile or 'named by DEBATE_REMOVAL_PROFILE'} could not {step} "
            f"({error_code_of(failure)}), so it "
            f"cannot carry out a removal: check DEBATE_REMOVAL_PROFILE names this environment's "
            f"EvidenceRemoval profile and that its session is signed in; nothing was deleted{leftover}"
        )


class RemovalIncomplete(DomainError):
    """A removal stopped part-way. Re-running the same command finishes it.

    The message says what is true of this run: whether the suppression entries reached every copy
    before it stopped (if appending them is what failed, nothing was deleted either), and whether
    the `INCOMPLETE` log entry could be written. `failure` is always the first thing that went wrong.
    """

    def __init__(
        self,
        report: RemovalReport,
        failure: BaseException,
        *,
        suppressed: bool,
        unlogged: BaseException | None = None,
    ) -> None:
        self.report = report
        self.error_code = error_code_of(failure)
        if suppressed:
            state = "Every suppression entry was appended first, so nothing removed can be re-imported."
        else:
            state = (
                "It stopped appending the suppression entries, before anything was deleted: nothing "
                "was deleted, and the entries may be on some copies of the list but not all."
            )
        logged = (
            ""
            if unlogged is None
            else f" The removal log entry could not be written either "
            f"({error_code_of(unlogged)}): {unlogged}."
        )
        super().__init__(
            f"the removal stopped part-way ({self.error_code}): {failure}. {state}{logged} "
            "Re-run the same command to finish."
        )


class RemovalCompletedUnlogged(DomainError):
    """Every step of a removal succeeded; only its removal-log entry is missing from some copy.

    Not :class:`RemovalIncomplete`: nothing is left to delete, and the operator must not tell the
    requester otherwise. What is at risk is the record. Running the command again finds nothing left
    and logs a `COMPLETED` entry with zero counts, so the counts are in this message for the operator
    to put in the register. A copy that did take the entry passes it to the others on the next
    removal-log write, because every append writes each copy the union's lines it lacks.
    """

    def __init__(
        self,
        report: RemovalReport,
        failure: BaseException,
        *,
        holding: Sequence[str],
        missing: Sequence[str],
    ) -> None:
        self.report = report
        self.error_code = error_code_of(failure)
        self.local_records_deleted = report.local_records_deleted
        self.local_files_deleted = report.local_files_deleted
        self.s3_versions_deleted = report.s3_versions_deleted
        self.manifests_rewritten = report.manifests_rewritten
        self.manifest_rows_dropped = report.manifest_rows_dropped
        self.log_copies_without_entry = ", ".join(missing)
        held = (
            f" {', '.join(holding)} holds it, and the next removal-log write copies it across."
            if holding
            else " No copy of the log has it."
        )
        self.hint = (
            "Nothing needs removing again. Put the counts above in the register entry for this request, "
            "then fix what refused the log write."
        )
        super().__init__(
            f"the removal completed: {report.local_records_deleted} record(s), "
            f"{report.local_files_deleted} local file(s) and {report.s3_versions_deleted} bucket object "
            f"version(s) deleted; {report.manifests_rewritten} manifest(s) rewritten without "
            f"{report.manifest_rows_dropped} row(s). Its removal-log entry was not written to "
            f"{self.log_copies_without_entry} ({self.error_code}: {failure}).{held} Record these counts "
            "in the register from this output: running the command again finds nothing left to remove "
            "and would log zero counts."
        )


class NotSuppressed(DomainError):
    """`unsuppress` was asked to lift a suppression that is not in force."""

    def __init__(self, sha256: str) -> None:
        super().__init__(f"{sha256} is not on the suppression list; there is nothing to lift")


@dataclass(frozen=True, slots=True)
class TakedownAccess:
    """What the `EvidenceRemoval` credential reaches in this environment's bucket."""

    versions: EvidenceVersionStore
    """Every version, listed and deleted."""
    objects: EvidenceObjectStore
    """The same bucket by name, for appending under `manifests/_suppression/`."""
    profile: str | None
    bucket: str


def refuse_protected_versions(versions: Sequence[ObjectVersion]) -> None:
    """Raise before deleting anything under `manifests/_suppression/` but the preflight probe."""
    for version in versions:
        if version.key.startswith(SUPPRESSION_PREFIX) and not version.key.startswith(PREFLIGHT_PREFIX):
            raise DomainError(
                f"refusing to delete {version.key}: the suppression list and removal log are append-only"
            )


async def preflight(access: TakedownAccess) -> None:
    """Prove the takedown credential can write, list and delete versions, before any real change.

    Lists versions first — the one grant the everyday profile lacks, so the commonest mistake, naming
    that profile, fails before anything is written — then writes a few bytes under
    :data:`PREFLIGHT_PREFIX`, lists their versions, deletes every one and checks none is left. Raises
    :class:`TakedownPreflightFailed` naming the step that failed.
    """
    key = f"{PREFLIGHT_PREFIX}{uuid.uuid4().hex}.txt"
    step = "list object versions"
    written = False
    try:
        await access.versions.list_versions(PREFLIGHT_PREFIX)
        step = "write a probe under manifests/_suppression/"
        with tempfile.TemporaryDirectory(prefix="debate-preflight-") as directory:
            probe = Path(directory) / "probe.txt"
            probe.write_text("caselist remove preflight\n", encoding="utf-8")
            await access.objects.put_file(key, probe)
        written = True
        step = "list object versions"
        listed = tuple(version for version in await access.versions.list_versions(key) if version.key == key)
        if not listed:
            raise StoreAccessDenied(
                "ListObjectVersions", f"s3://{access.bucket}/{key}", hint="the probe was not listed"
            )
        step = "delete an object version"
        refuse_protected_versions(listed)
        await access.versions.delete_versions(listed)
        if [version for version in await access.versions.list_versions(key) if version.key == key]:
            raise StoreAccessDenied(
                "DeleteObject", f"s3://{access.bucket}/{key}", hint="a version survived the delete"
            )
    except (StoreError, DomainError) as failure:
        raise TakedownPreflightFailed(
            access.profile, step, failure, left=key if written else None
        ) from failure


@dataclass(slots=True)
class _Counts:
    local_records_deleted: int = 0
    local_files_deleted: int = 0
    manifests_rewritten: int = 0
    manifest_rows_dropped: int = 0
    s3_versions_deleted: int = 0


@dataclass(frozen=True, slots=True)
class RemovalReport:
    """What an execution did, for the command's summary. The log entry is the durable record."""

    plan: RemovalPlan
    log_entry: RemovalLogEntry
    local_records_deleted: int
    local_files_deleted: int
    manifests_rewritten: int
    manifest_rows_dropped: int
    s3_versions_deleted: int

    @property
    def completed(self) -> bool:
        return self.log_entry.outcome is RemovalOutcome.COMPLETED


@dataclass(frozen=True, slots=True)
class UnsuppressPlan:
    """What `caselist unsuppress` would append, and what it would lift."""

    sha256: str
    reason: ReasonCode
    request_id: str | None
    environment: str
    entry: SuppressionEntry
    whole_source: bool
    """Whether the file is suppressed as a whole source now."""
    disclosures: int
    """How many disclosure-scoped suppressions of it are in force now."""
    previous: SuppressionEntry


@dataclass(frozen=True, slots=True)
class UnsuppressReport:
    plan: UnsuppressPlan
    log_entry: RemovalLogEntry


@dataclass
class CaselistRemovalService:
    """Executes removal plans and un-suppress requests for one environment.

    Built by the composition root. `takedown` is a factory, called only by :meth:`execute` and
    :meth:`unsuppress`, so that a dry run never builds — or needs — the takedown credential.
    """

    planner: RemovalPlanner
    caselists: CaselistRepository
    local: LocalEvidence
    local_blobs: EvidenceVersionStore
    local_parsed: EvidenceVersionStore
    remote: EvidenceObjectStore
    """The bucket through the everyday profile: rewritten manifests are written with it."""
    suppression: SuppressionList
    """The list as every bucket-holding command reads it (local and bucket copies, everyday profile)."""
    local_suppression: AppendOnlyRecord
    local_removal_log: AppendOnlyRecord
    takedown: Callable[[], TakedownAccess]
    clock: Clock
    environment: str
    _access: TakedownAccess | None = field(default=None, init=False)

    # --------------------------------------------------------------------------------------
    # Removal
    # --------------------------------------------------------------------------------------

    async def plan(
        self, selector: RemovalSelector, *, request_id: str, reason: ReasonCode, include_shared: bool = False
    ) -> RemovalPlan:
        """The dry run. Reads only, with the everyday profile only."""
        return await self.planner.plan(
            selector, request_id=request_id, reason=reason, include_shared=include_shared
        )

    async def execute(self, plan: RemovalPlan) -> RemovalReport:
        """Carry out `plan`. Raises before any change if the takedown credential is missing or refused.

        Raises :class:`RemovalIncomplete` — after appending an `INCOMPLETE` log entry — if a step
        fails part-way; running the same command again finishes the job. Raises
        :class:`RemovalCompletedUnlogged` if every step succeeded and only the log entry could not be
        written to every copy.
        """
        access = await self._authorised()
        suppression = RecordedSuppressionList(
            self.local_suppression, self._bucket_record(access, SUPPRESSION_LIST_KEY)
        )
        counts = _Counts()
        failure: BaseException | None = None
        suppressed = False
        try:
            await suppression.append(plan.suppression_entries)
            suppressed = True
            await self._delete_bucket_objects(plan, access, counts)
            await self._rewrite_bucket_manifests(plan, access, counts)
            await self._sweep_superseded_manifests(plan, access, counts)
            await self._delete_local_files(plan, counts)
            await self._rewrite_local_manifests(plan, counts)
            await self._delete_records(plan, counts)
        except (DomainError, OSError) as stopped:
            failure = stopped
        entry = self._log_entry(plan, counts, failure)
        log = RecordedRemovalLog(self.local_removal_log, self._bucket_record(access, REMOVAL_LOG_KEY))
        unlogged: DomainError | OSError | None = None
        try:
            await log.append([entry])
        except (DomainError, OSError) as refused:
            unlogged = refused  # reported with the run's own failure, or as a completed removal unlogged
        report = RemovalReport(
            plan=plan,
            log_entry=entry,
            local_records_deleted=counts.local_records_deleted,
            local_files_deleted=counts.local_files_deleted,
            manifests_rewritten=counts.manifests_rewritten,
            manifest_rows_dropped=counts.manifest_rows_dropped,
            s3_versions_deleted=counts.s3_versions_deleted,
        )
        if failure is not None:
            raise RemovalIncomplete(report, failure, suppressed=suppressed, unlogged=unlogged) from failure
        if unlogged is not None:
            holding, missing = await _copies_holding(log.records, entry.to_line())
            raise RemovalCompletedUnlogged(report, unlogged, holding=holding, missing=missing) from unlogged
        return report

    async def _delete_bucket_objects(
        self, plan: RemovalPlan, access: TakedownAccess, counts: _Counts
    ) -> None:
        """Every version of every `raw/` and `parsed/` object, as the takedown credential lists them now."""
        for planned in plan.objects_on(Side.BUCKET):
            versions = tuple(
                version
                for version in await access.versions.list_versions(planned.key)
                if version.key == planned.key
            )
            refuse_protected_versions(versions)
            counts.s3_versions_deleted += await access.versions.delete_versions(versions)

    async def _rewrite_bucket_manifests(
        self, plan: RemovalPlan, access: TakedownAccess, counts: _Counts
    ) -> None:
        """Write each rewritten manifest, then purge every other version of it."""
        for rewrite in plan.manifests_on(Side.BUCKET):
            written = await self._put_lines(self.remote, rewrite)
            stale = tuple(
                version
                for version in await access.versions.list_versions(rewrite.key)
                if version.key == rewrite.key and version.version_id != written
            )
            refuse_protected_versions(stale)
            counts.s3_versions_deleted += await access.versions.delete_versions(stale)
            counts.manifests_rewritten += 1
            counts.manifest_rows_dropped += rewrite.rows_dropped

    async def _sweep_superseded_manifests(
        self, plan: RemovalPlan, access: TakedownAccess, counts: _Counts
    ) -> None:
        """Noncurrent versions of the affected caselists' other manifests that still name what was removed.

        The current version of each was checked by the plan; an earlier one may hold a row the
        current one no longer does — a manifest re-published after a re-import, say — and a
        restorable version of a removed row is the row not removed.
        """
        rewritten = {rewrite.key for rewrite in plan.manifests_on(Side.BUCKET)}
        for caselist in plan.affected_caselists:
            for version in await access.versions.list_versions(f"manifests/{caselist}/"):
                if version.is_latest or version.is_delete_marker or version.key in rewritten:
                    continue
                if await self._version_names_removed(plan, access, caselist, version):
                    refuse_protected_versions([version])
                    counts.s3_versions_deleted += await access.versions.delete_versions([version])

    async def _version_names_removed(
        self, plan: RemovalPlan, access: TakedownAccess, caselist: str, version: ObjectVersion
    ) -> bool:
        with tempfile.TemporaryDirectory(prefix="debate-removal-") as directory:
            staged = Path(directory) / "version.jsonl"
            await access.versions.get_version_file(version, staged)
            lines = staged.read_text(encoding="utf-8").splitlines()
        return any(_names_removed(plan, caselist, line) for line in lines if line.strip())

    async def _delete_local_files(self, plan: RemovalPlan, counts: _Counts) -> None:
        for planned in plan.objects_on(Side.LOCAL):
            store = self.local_blobs if planned.kind is ObjectKind.BLOB else self.local_parsed
            versions = tuple(
                version for version in await store.list_versions(planned.key) if version.key == planned.key
            )
            counts.local_files_deleted += await store.delete_versions(versions)

    async def _rewrite_local_manifests(self, plan: RemovalPlan, counts: _Counts) -> None:
        for rewrite in plan.manifests_on(Side.LOCAL):
            await self._put_lines(self.local.objects, rewrite)
            counts.manifests_rewritten += 1
            counts.manifest_rows_dropped += rewrite.rows_dropped

    async def _delete_records(self, plan: RemovalPlan, counts: _Counts) -> None:
        """Last, because a re-run of a `--team` removal resolves the team from these."""
        for source in plan.sources:
            for ref in source.disclosures:
                counts.local_records_deleted += int(
                    await self.caselists.delete_disclosure(ref.caselist, ref.snapshot, ref.source_path)
                )
            for camp_file in source.camp_files:
                counts.local_records_deleted += int(
                    await self.caselists.delete_camp_file(source.sha256, camp_file.year, camp_file.event)
                )
            if source.delete_source_record:
                counts.local_records_deleted += int(await self.caselists.delete_source(source.sha256))

    @staticmethod
    async def _put_lines(store: EvidenceObjectStore, rewrite: ManifestRewrite) -> str | None:
        with tempfile.TemporaryDirectory(prefix="debate-removal-") as directory:
            staged = Path(directory) / "manifest.jsonl"
            staged.write_text("".join(f"{line}\n" for line in rewrite.lines), encoding="utf-8")
            return (await store.put_file(rewrite.key, staged)).version_id

    def _log_entry(
        self, plan: RemovalPlan, counts: _Counts, failure: BaseException | None
    ) -> RemovalLogEntry:
        return RemovalLogEntry(
            kind=RemovalLogKind.REMOVAL,
            recorded_at=self.clock.now(),
            request_id=plan.request_id,
            reason=plan.reason,
            environment=self.environment,
            outcome=RemovalOutcome.COMPLETED if failure is None else RemovalOutcome.INCOMPLETE,
            selector=plan.selector.kind,
            include_shared=plan.include_shared,
            removed_sha256=tuple(sorted(source.sha256 for source in plan.of(Disposition.REMOVE))),
            withdrawn_sha256=tuple(sorted(source.sha256 for source in plan.of(Disposition.WITHDRAW))),
            local_records_deleted=counts.local_records_deleted,
            local_files_deleted=counts.local_files_deleted,
            manifests_rewritten=counts.manifests_rewritten,
            manifest_rows_dropped=counts.manifest_rows_dropped,
            s3_versions_deleted=counts.s3_versions_deleted,
            error_code=None if failure is None else error_code_of(failure),
        )

    # --------------------------------------------------------------------------------------
    # Un-suppress
    # --------------------------------------------------------------------------------------

    async def plan_unsuppress(
        self, sha256: str, *, reason: ReasonCode, request_id: str | None = None
    ) -> UnsuppressPlan:
        """What lifting `sha256` would append. Reads only. :class:`NotSuppressed` if nothing is in force."""
        if re.match(SHA256_HEX_PATTERN, sha256) is None:
            raise InvalidRemovalRequest("--sha256 must be a file's sha256: 64 lowercase hex characters")
        if reason not in REINSTATEMENT_REASONS:
            raise InvalidRemovalRequest(f"--reason must be one of {', '.join(sorted(REINSTATEMENT_REASONS))}")
        if request_id is not None and re.match(REQUEST_ID_PATTERN, request_id) is None:
            raise InvalidRemovalRequest(
                "--request must be the register id, RM-<year>-<number>, e.g. RM-2026-01"
            )
        state = await load_suppression_state(self.suppression)
        if not state.is_suppressed(sha256):
            raise NotSuppressed(sha256)
        return UnsuppressPlan(
            sha256=sha256,
            reason=reason,
            request_id=request_id,
            environment=self.environment,
            entry=SuppressionEntry(
                action=SuppressionAction.UNSUPPRESS,
                sha256=sha256,
                recorded_at=self.clock.now(),
                reason=reason,
                request_id=request_id,
            ),
            whole_source=state.suppresses_source(sha256),
            disclosures=sum(1 for digest, _ in state.disclosures if digest == sha256),
            previous=state.latest[sha256],
        )

    async def unsuppress(self, plan: UnsuppressPlan) -> UnsuppressReport:
        """Append the un-suppress entry to both copies of the list, and one entry to the removal log.

        Purged data is not restored: the file comes back only when an archive that holds it is
        imported again.
        """
        access = await self._authorised()
        suppression = RecordedSuppressionList(
            self.local_suppression, self._bucket_record(access, SUPPRESSION_LIST_KEY)
        )
        await suppression.append([plan.entry])
        entry = RemovalLogEntry(
            kind=RemovalLogKind.UNSUPPRESS,
            recorded_at=self.clock.now(),
            request_id=plan.request_id,
            reason=plan.reason,
            environment=self.environment,
            outcome=RemovalOutcome.COMPLETED,
            unsuppressed_sha256=(plan.sha256,),
        )
        await RecordedRemovalLog(self.local_removal_log, self._bucket_record(access, REMOVAL_LOG_KEY)).append(
            [entry]
        )
        return UnsuppressReport(plan=plan, log_entry=entry)

    # --------------------------------------------------------------------------------------
    # The takedown credential
    # --------------------------------------------------------------------------------------

    async def _authorised(self) -> TakedownAccess:
        """The takedown credential, proven by :func:`preflight`. Built and checked once per service."""
        if self._access is None:
            try:
                access = self.takedown()
            except StoreCredentialsExpired as expired:
                raise TakedownPreflightFailed(None, "start an AWS session", expired) from expired
            await preflight(access)
            self._access = access
        return self._access

    def _bucket_record(self, access: TakedownAccess, key: ObjectKey) -> ObjectStoreAppendOnlyRecord:
        """The bucket's copy: appended with the takedown credential, read with the everyday one."""
        return ObjectStoreAppendOnlyRecord(
            access.objects, key, location=f"s3://{access.bucket}/{key}", reader=self.remote
        )


async def _copies_holding(
    records: Sequence[AppendOnlyRecord], line: str
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The locations of the copies that hold `line`, and of those that do not or cannot be read."""
    holding: list[str] = []
    missing: list[str] = []
    for record in records:
        try:
            present = line in await record.read_lines()
        except (DomainError, OSError):
            present = False
        (holding if present else missing).append(record.location)
    return tuple(holding), tuple(missing)


def _names_removed(plan: RemovalPlan, caselist: str, line: str) -> bool:
    """Whether one manifest line names something this removal took out: what the sweep looks for."""
    try:
        row: object = json.loads(line)
    except json.JSONDecodeError:
        return False
    if not isinstance(row, dict) or row.get("kind") != "member":  # pyright: ignore[reportUnknownMemberType]
        return False
    fields: dict[str, object] = row  # pyright: ignore[reportUnknownVariableType]
    path, digest = fields.get("path"), fields.get("sha256")
    if (
        isinstance(plan.selector, TeamSelector)
        and isinstance(path, str)
        and plan.selector.holds(caselist, path)
    ):
        return True
    if isinstance(digest, str):
        scope = None if caselist == "openev" else caselist
        after: SuppressionState = plan.suppression_after
        return after.suppresses(
            digest, disclosure=disclosure_digest(scope, path) if scope and isinstance(path, str) else None
        )
    return False
