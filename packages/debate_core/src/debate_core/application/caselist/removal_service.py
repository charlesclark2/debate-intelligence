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

Before the first change, :func:`preflight` proves the takedown credential is the takedown's and
can do what the removal needs. It first asks which role the credential is signed in as and stops
unless that is this environment's `EvidenceRemoval` role (`v1-e29-t08`). Then it writes a probe
object under `manifests/_suppression/preflight/`, lists its versions, deletes them, and checks they
are gone. An unset profile, a profile the AWS config lacks, an expired session, or the everyday
profile named by mistake all fail there, with nothing deleted and nothing appended (spec ac6), and
all but a takedown role whose own grants are broken fail before anything is written.

The question comes first because nothing the bucket allows tells the two profiles apart short of a
delete. From `v1-e29-t06`, which let the everyday profile list versions, until `v1-e29-t08`, that
profile named by mistake listed, wrote the probe and was refused only at the delete, leaving the
probe behind. A preflight that passes now deletes every probe it found there before it wrote its
own (`v1-e29-t09`); `docs/runbooks/caselist-removal.md` says when one is still removed by hand.

## The order is the safety

1. **Suppress first.** The entries go on the list — this machine's copy and the bucket's — before
   anything is deleted, so if the run stops part-way, the next weekly import still cannot bring the
   file back. The plan's path entries go with them, to the path-hold record beside each copy of the
   list (`v1-e30-t13`), so the next import cannot store a new upload at a removed path either. Just
   before them, beside the list too, the caselist each withdrawn copy is taken from (`v1-e30-t16`),
   so no suppressed disclosure is on a copy without its caselist beside it.
2. **The bucket**: every version of every `raw/` and `parsed/` object, listed again with the
   takedown credential so nothing the dry run could not see is missed; then each rewritten
   manifest, written and every superseded version of it purged; then the sweep
   (:mod:`~debate_core.application.caselist.manifest_sweep`): every noncurrent version of any other
   manifest of the same caselists that still names what was removed, and of each manifest an
   earlier run of the same request rewrote, every version older than that rewrite (`v1-e30-t19`).
   The dry run counted the same sweep with the everyday credential.
3. **This machine**: blobs and parsed files, then manifests, then the sync's download inbox
   (`v1-e30-t09`: removed camp files and imported archives deleted, archives still waiting to be
   imported rewritten without the removed files; see
   :mod:`~debate_core.application.caselist.inbox_purge`), then — last — the records. The records
   are what a re-run resolves a `--team` from, so they outlive every other step. Every step after
   the first relies on it: the inbox step deletes the copy of a camp file the sync would otherwise
   use to recognise it as removed, which is safe only once the list says it is.
4. **The removal log**, one entry, `COMPLETED` or `INCOMPLETE` with the error's code. An incomplete
   run is finished by running the same command again; nothing is retried behind the operator's back.
   Just before it, beside the log, the run's scope (`v1-e30-t15`): the caselists it touched and each
   manifest it rewrote in the bucket, with the version the rewrite is. `caselist status` compares
   manifest and aggregate versions with the removal's completion by them.

## What it never deletes

Anything under `manifests/_suppression/` but the preflight's probes, its own and those earlier
preflights left (:func:`refuse_protected_versions`): the suppression list and the removal log are
append-only and their versions are the record of what was asked. And nothing under `reports/`,
which IAM would refuse anyway.
"""

from __future__ import annotations

import re
import tempfile
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Protocol

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.inbox_purge import CaselistInbox, InboxPurge, purge_inbox
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
)
from debate_core.application.caselist.run_state import RUN_STATE_BUNDLE_KEY
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
    StoreProfileNotConfigured,
    reported_error_message,
)
from debate_core.application.ports.caller_identity import CallerIdentity
from debate_core.application.ports.caselist import CaselistRepository
from debate_core.application.ports.evidence_store import EvidenceObjectStore, ObjectKey
from debate_core.application.ports.evidence_versions import EvidenceVersionStore, ObjectVersion
from debate_core.application.ports.providers import Clock
from debate_core.application.ports.suppression import (
    REINSTATEMENT_REASONS,
    REQUEST_ID_PATTERN,
    AppendOnlyRecord,
    InboxRewriteRecord,
    ManifestRewriteRecord,
    ReasonCode,
    RemovalLogEntry,
    RemovalLogKind,
    RemovalOutcome,
    RemovalScopeEntry,
    SuppressionAction,
    SuppressionEntry,
    SuppressionList,
)
from debate_core.domain import SHA256_HEX_PATTERN

__all__ = [
    "PREFLIGHT_PREFIX",
    "BundleSaved",
    "CaselistRemovalService",
    "NotSuppressed",
    "NotTheTakedownRole",
    "RemovalIncomplete",
    "RemovalReport",
    "RemovalRunState",
    "RunStateBundleNotRewritten",
    "TakedownAccess",
    "TakedownNotConfigured",
    "TakedownPreflightFailed",
    "on_the_working_copy",
    "UnsuppressPlan",
    "UnsuppressReport",
    "permission_set_of",
    "preflight",
    "refuse_protected_versions",
    "takedown_permission_set",
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


#: The role the account creates for an Identity Center permission set: a fixed prefix, the set's
#: name, and a suffix of letters and digits the account chooses. The suffix is not ours to predict,
#: so it is matched by shape and never by value.
_IDENTITY_CENTER_ROLE: Final = re.compile(r"AWSReservedSSO_(?P<permission_set>.+)_[A-Za-z0-9]+")


def takedown_permission_set(environment: str) -> str:
    """The permission set a takedown runs as in `environment`: `DebateDevEvidenceRemoval` in dev.

    The name `infrastructure/modules/evidence_bucket/operator_access.tf` gives the set
    (`removal_permission_set_name`), which is where it is defined; a test reads that file and fails
    if this function and it part ways. Not a setting: a name an operator could change is a check
    an operator could point at the everyday role.
    """
    return f"Debate{environment.title()}EvidenceRemoval"


def permission_set_of(role_name: str | None) -> str | None:
    """The permission set `role_name` is the role of, or `None` when it is no permission set's role.

    `AWSReservedSSO_DebateDevEvidenceRemoval_0123456789abcdef` is `DebateDevEvidenceRemoval`. A role
    someone made by hand is nobody's, whatever it is called, and so is no role at all.
    """
    named = _IDENTITY_CENTER_ROLE.fullmatch(role_name or "")
    return named.group("permission_set") if named is not None else None


class NotTheTakedownRole(DomainError):
    """The credential named for a takedown is signed in, as some role other than the takedown's.

    The everyday profile named in `DEBATE_REMOVAL_PROFILE` by mistake, most likely: the two
    profiles' names differ by a suffix. Found by asking, before anything is listed or written
    (`v1-e29-t08`). It carries the names of two roles and nothing else of the account.
    """

    def __init__(
        self, profile: str | None, *, role_name: str | None, required: str, environment: str
    ) -> None:
        self.profile = profile
        self.signed_in_as = permission_set_of(role_name) or role_name
        """The permission set the credential holds; the role's own name when it is no set's role;
        `None` when it is not a role."""
        self.required = required
        """The permission set a takedown runs as in this environment."""
        self.hint = (
            f"set DEBATE_REMOVAL_PROFILE to debate-{environment}-evidence-removal, the profile for "
            f"{required}; the one it names is signed in, so logging in again changes nothing. "
            "docs/runbooks/evidence-store.md lists the evidence profiles"
        )
        super().__init__(
            f"{profile or 'the profile DEBATE_REMOVAL_PROFILE names'} is signed in as "
            f"{self.signed_in_as or 'no role at all'}, and a takedown runs only as {required}"
        )


class TakedownPreflightFailed(DomainError):
    """The takedown profile is not the takedown's, or could not write, list or delete its probe.

    Nothing was deleted or appended. `failure`, kept as `__cause__` by the `raise … from`, is what
    the command's exit status is read from: an expired session or a store that did not answer may
    be cured by running the command again, and a profile that is not defined or not the takedown
    role is a setting to correct.

    It carries the cause's code as :attr:`cause_code`, and each of the cause's own facts as an
    attribute named `cause_` and the fact's name (`v1-e29-t09`): `cause_setting` for a profile the
    AWS config does not define, `cause_signed_in_as` and `cause_required` for the wrong role. They
    are what a script reads from the `--json` envelope's `error.details`, which until then held only
    the profile and the step, and the setting to correct was in the message alone. The cause's
    `hint` is not among them: it is this error's own :attr:`hint`.
    """

    def __init__(
        self, profile: str | None, step: str, failure: BaseException, *, left: ObjectKey | None = None
    ) -> None:
        self.profile = profile
        self.step = step
        self.cause_code = error_code_of(failure)
        """The error code of what failed, e.g. `"STORE_PROFILE_NOT_CONFIGURED"`."""
        for name, value in _facts_of(failure).items():
            setattr(self, f"cause_{name}", value)
        self.hint = getattr(failure, "hint", None) or (
            f"aws sso login --profile {profile}" if profile else "set DEBATE_REMOVAL_PROFILE"
        )
        leftover = f"; its probe object was left at {left}" if left else ""
        super().__init__(
            f"the takedown profile {profile or 'named by DEBATE_REMOVAL_PROFILE'} could not {step} "
            f"({error_code_of(failure)}), so it "
            f"cannot carry out a removal: {_what_to_correct(failure)}; nothing was deleted{leftover}"
        )


def _facts_of(failure: BaseException) -> dict[str, str | int | float | bool | None]:
    """The facts a :class:`DomainError` keeps as attributes, as the CLI reports them; none for another.

    Public, single-valued attributes only, and never its `hint`. Anything that is not this
    project's error has no facts this project chose, and its message is not passed on either.
    """
    if not isinstance(failure, DomainError):
        return {}
    return {
        name: value
        for name, value in vars(failure).items()
        if not name.startswith("_") and name != "hint" and isinstance(value, str | int | float | bool | None)
    }


def _what_to_correct(failure: BaseException) -> str:
    """The clause of :class:`TakedownPreflightFailed`'s message that says what to look at.

    Two failures are settings to correct and say so, because the general advice ends by asking
    whether the session is signed in, which sends an operator to a login that cures neither.
    """
    if isinstance(failure, StoreProfileNotConfigured):
        return "DEBATE_REMOVAL_PROFILE must name a profile this machine's AWS config defines"
    if isinstance(failure, NotTheTakedownRole):
        return (
            f"it is signed in as {failure.signed_in_as or 'no role at all'}, so DEBATE_REMOVAL_PROFILE "
            "does not name this environment's EvidenceRemoval profile"
        )
    return (
        "check DEBATE_REMOVAL_PROFILE names this environment's EvidenceRemoval profile and that its "
        "session is signed in"
    )


class RemovalIncomplete(DomainError):
    """A removal stopped part-way. Re-running the same command finishes it.

    The message says what is true of this run: whether the suppression entries reached every copy
    before it stopped (if appending them is what failed, nothing was deleted either), and whether
    the `INCOMPLETE` log entry could be written. `failure` is always the first thing that went wrong.
    It is quoted by :func:`~debate_core.application.errors.reported_error_message`: an `OSError` by
    its class and errno, never by its text, which names the path it failed on (`v1-e29-t09`). The
    same goes for :class:`RemovalCompletedUnlogged`.
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
            f"({error_code_of(unlogged)}): {reported_error_message(unlogged)}."
        )
        super().__init__(
            f"the removal stopped part-way ({self.error_code}): {reported_error_message(failure)}. "
            f"{state}{logged} "
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
        self.inbox_files_deleted = report.inbox_files_deleted
        self.inbox_files_rewritten = report.inbox_files_rewritten
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
            f"{report.manifest_rows_dropped} row(s); {report.inbox_files_deleted} inbox file(s) deleted and "
            f"{report.inbox_files_rewritten} rewritten. Its removal-log entry was not written to "
            f"{self.log_copies_without_entry} ({self.error_code}: {reported_error_message(failure)}).{held} "
            "Record these counts "
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
    caller: CallerIdentity
    """Which role the credential is signed in as: what :func:`preflight` asks before anything else."""
    profile: str | None
    bucket: str


def refuse_protected_versions(versions: Sequence[ObjectVersion]) -> None:
    """Raise before deleting anything under `manifests/_suppression/` but the preflight probe."""
    for version in versions:
        if version.key.startswith(SUPPRESSION_PREFIX) and not version.key.startswith(PREFLIGHT_PREFIX):
            raise DomainError(
                f"refusing to delete {version.key}: the suppression list and removal log are append-only"
            )


async def preflight(access: TakedownAccess, *, environment: str) -> tuple[ObjectVersion, ...]:
    """Prove the credential is the takedown's and can write, list and delete, before any real change.

    First asks which role the credential is signed in as, and stops unless it is the role of
    `environment`'s takedown permission set (:func:`takedown_permission_set`). Then lists versions,
    writes a few bytes under :data:`PREFLIGHT_PREFIX`, lists their versions, deletes every one and
    checks none is left. Raises :class:`TakedownPreflightFailed` naming the step that failed.

    The question is the one step only the takedown role passes that writes nothing (`v1-e29-t08`).
    Until `v1-e29-t06` the first listing was that step: it was the one grant the everyday profile
    lacked. With that grant (dev and prod, 2026-10-08) the everyday profile lists and writes like
    the takedown's and is refused only at the delete, so naming it by mistake left the probe in the
    bucket. Asking needs no grant and is answered for any signed-in credential, so the everyday
    profile is refused by what it is, with nothing listed and nothing written.

    A takedown role whose own delete grant is missing still gets as far as the delete, since nothing
    short of a delete shows that. It leaves its probe, and the error names the key.

    A preflight that passes then deletes every version its first listing found under
    :data:`PREFLIGHT_PREFIX` (`v1-e29-t09`): probes that earlier preflights wrote and were refused
    the delete of. They were there before its own probe was written, so they are older than it, and
    the credential has just shown it may delete there. A probe written after that listing, by a
    preflight running beside this one, is not touched.

    That sweep is housekeeping, and never holds a takedown back (the PM's review of `v1-e29-t09`):
    a takedown withdraws someone's data, and an old probe that cannot be deleted for a reason of
    its own would otherwise stop every takedown after it. Each version is deleted on its own, a
    refusal of one does not stop the others, and the versions that could not be deleted are
    returned, for the run's report to count; they are removed by hand
    (`docs/runbooks/caselist-removal.md`). The preflight's own probe is its proof, and a refused
    delete of that one still fails it.
    """
    required = takedown_permission_set(environment)
    key = f"{PREFLIGHT_PREFIX}{uuid.uuid4().hex}.txt"
    step = f"show it is signed in as {required}"
    written = False
    try:
        role_name = await access.caller.assumed_role_name()
        if permission_set_of(role_name) != required:
            raise NotTheTakedownRole(
                access.profile, role_name=role_name, required=required, environment=environment
            )
        step = "list object versions"
        earlier = tuple(
            version
            for version in await access.versions.list_versions(PREFLIGHT_PREFIX)
            if version.key.startswith(PREFLIGHT_PREFIX)
        )
        refuse_protected_versions(earlier)
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
    return await _sweep_earlier_probes(access, earlier)


async def _sweep_earlier_probes(
    access: TakedownAccess, earlier: Sequence[ObjectVersion]
) -> tuple[ObjectVersion, ...]:
    """Delete each version an earlier preflight left; return the ones the store would not delete.

    Listed before the preflight wrote its own probe, so older than it (`v1-e29-t09`), and deleted
    with the credential that has just shown it may delete there. One at a time, because the store
    stops a batch at its first refusal, and a refusal is counted rather than raised: this is
    housekeeping, and the takedown goes ahead whatever it leaves.
    """
    left: list[ObjectVersion] = []
    for version in earlier:
        try:
            await access.versions.delete_versions((version,))
        except StoreError:
            left.append(version)
    return tuple(left)


@dataclass(slots=True)
class _Counts:
    local_records_deleted: int = 0
    local_files_deleted: int = 0
    manifests_rewritten: int = 0
    manifest_rows_dropped: int = 0
    s3_versions_deleted: int = 0
    inbox: InboxPurge = field(default_factory=InboxPurge)
    rewrites: list[ManifestRewriteRecord] = field(default_factory=lambda: [])
    """Each manifest rewritten in the bucket so far, with the version its rewrite is."""


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
    inbox_files_deleted: int = 0
    inbox_files_rewritten: int = 0
    preflight_probes_left: tuple[ObjectVersion, ...] = ()
    """Versions earlier preflights left under :data:`PREFLIGHT_PREFIX` that this run's preflight
    could not delete (`v1-e29-t09`). Counted in the command's output, and removed by hand; never a
    failure. Empty when the preflight ran in an earlier call of the same service."""

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
    path_holds_released: int = 0
    """How many paths its removal holds now, which the un-suppress releases (`v1-e30-t13`): an
    upload at one is imported again from the next archive that holds it."""


@dataclass(frozen=True, slots=True)
class UnsuppressReport:
    plan: UnsuppressPlan
    log_entry: RemovalLogEntry
    preflight_probes_left: tuple[ObjectVersion, ...] = ()
    """Versions earlier preflights left under :data:`PREFLIGHT_PREFIX` that this run's preflight
    could not delete (`v1-e29-t09`). Counted in the command's output, and removed by hand; never a
    failure. Empty when the preflight ran in an earlier call of the same service."""


class RemovalRunState(Protocol):
    """The run's state in the bucket, as a removal in bucket mode reaches it (`v1-e40-t04`, ADR-0020 (3)).

    :class:`~debate_core.application.caselist.run_state.RunState`, named here by its shape.
    """

    async def restore(self, caselists: Sequence[str], *, parsed_version: str | None) -> object: ...

    async def save_state_files(self) -> None: ...

    async def save_bundle(self) -> BundleSaved: ...


class BundleSaved(Protocol):
    @property
    def saved(self) -> bool: ...

    @property
    def reason(self) -> str: ...

    @property
    def version_id(self) -> str | None: ...


async def on_the_working_copy[T](run_state: RemovalRunState | None, work: Callable[[], Awaitable[T]]) -> T:
    """In bucket mode, restore the working copy, then do `work`, which builds the removal service.

    The restore comes first because it replaces this machine's database whole, and the service opens
    the database when it is built. A removal that executes runs this holding the bucket's run lock, so
    the copy it plans from is the copy it rewrites the bundle from (`v1-e40-t04`). `None`, local mode,
    restores nothing.
    """
    if run_state is not None:
        await run_state.restore((), parsed_version=None)
    return await work()


class RunStateBundleNotRewritten(DomainError):
    """The removal's rewrite of the run-state bundle was not confirmed in the bucket: nothing of it purged."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(
            f"the run-state bundle was not rewritten without the removed files ({reason}), so its earlier "
            "versions were not purged; run the same removal again"
        )


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
    inbox: CaselistInbox
    """The sync's download inbox in this environment. Required, so no removal can forget it."""
    remote: EvidenceObjectStore
    """The bucket through the everyday profile: rewritten manifests are written with it."""
    suppression: SuppressionList
    """The list as every bucket-holding command reads it (local and bucket copies, everyday profile)."""
    local_suppression: AppendOnlyRecord
    local_removal_log: AppendOnlyRecord
    takedown: Callable[[], TakedownAccess]
    clock: Clock
    environment: str
    run_state: RemovalRunState | None = None
    """In bucket mode (`v1-e40-t04`): the run's state, restored before a plan and rewritten after a
    removal, its earlier versions then purged. `None` in local mode, where no bundle exists: a local-mode
    command refuses a bucket that holds one (the PM's ruling 3(a))."""
    _access: TakedownAccess | None = field(default=None, init=False)

    # --------------------------------------------------------------------------------------
    # Removal
    # --------------------------------------------------------------------------------------

    async def plan(
        self,
        selector: RemovalSelector,
        *,
        request_id: str,
        reason: ReasonCode,
        include_shared: bool = False,
        only_named: bool = False,
    ) -> RemovalPlan:
        """The dry run. Reads only, with the everyday profile only.

        The plan includes the later uploads the store holds at each removed path unless
        `only_named` (`v1-e30-t11`); :meth:`execute` carries out whichever plan it is given. In bucket
        mode the service is built on the working copy :func:`on_the_working_copy` restored first.
        """
        return await self.planner.plan(
            selector,
            request_id=request_id,
            reason=reason,
            include_shared=include_shared,
            only_named=only_named,
        )

    async def plan_and_execute(
        self,
        selector: RemovalSelector,
        *,
        request_id: str,
        reason: ReasonCode,
        include_shared: bool = False,
        only_named: bool = False,
    ) -> RemovalReport:
        """:meth:`plan` and :meth:`execute` as one step, for a command that holds the bucket's run lock
        across both: in bucket mode the working copy the plan is made from is the one executed."""
        plan = await self.plan(
            selector,
            request_id=request_id,
            reason=reason,
            include_shared=include_shared,
            only_named=only_named,
        )
        return await self.execute(plan)

    async def execute(self, plan: RemovalPlan) -> RemovalReport:
        """Carry out `plan`. Raises before any change if the takedown credential is missing or refused.

        Raises :class:`RemovalIncomplete` — after appending an `INCOMPLETE` log entry — if a step
        fails part-way; running the same command again finishes the job. Raises
        :class:`RemovalCompletedUnlogged` if every step succeeded and only the log entry could not be
        written to every copy.
        """
        access, probes_left = await self._authorised()
        suppression = RecordedSuppressionList(
            self.local_suppression, self._bucket_record(access, SUPPRESSION_LIST_KEY)
        )
        counts = _Counts()
        failure: BaseException | None = None
        suppressed = False
        try:
            # What this machine's imports held at a held path, given to the bucket's copy, which
            # only the takedown credential writes (v1-e30-t23). Nothing new is appended.
            await suppression.append_held_digests(())
            await suppression.append_withdrawals(plan.withdrawals)
            await suppression.append(plan.suppression_entries)
            await suppression.append_path_holds(plan.path_holds)
            suppressed = True
            await self._delete_bucket_objects(plan, access, counts)
            await self._rewrite_bucket_manifests(plan, access, counts)
            await self._sweep_superseded_manifests(plan, access, counts)
            await self._delete_local_files(plan, counts)
            await self._rewrite_local_manifests(plan, counts)
            await self._purge_inbox(plan, counts)
            await self._delete_records(plan, counts)
            await self._rewrite_run_state(access, counts)
        except (DomainError, OSError) as stopped:
            failure = stopped
        entry = self._log_entry(plan, counts, failure)
        scope = RemovalScopeEntry(
            recorded_at=entry.recorded_at,
            request_id=entry.request_id,
            environment=entry.environment,
            caselists=plan.touched_caselists,
            manifest_rewrites=tuple(sorted(counts.rewrites, key=lambda rewrite: rewrite.key)),
        )
        log = RecordedRemovalLog(self.local_removal_log, self._bucket_record(access, REMOVAL_LOG_KEY))
        unlogged: DomainError | OSError | None = None
        try:
            await log.append([entry], scopes=[scope])
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
            inbox_files_deleted=counts.inbox.deleted,
            inbox_files_rewritten=counts.inbox.rewritten,
            preflight_probes_left=probes_left,
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
            counts.rewrites.append(ManifestRewriteRecord(key=rewrite.key, version_id=written))
            counts.manifests_rewritten += 1
            counts.manifest_rows_dropped += rewrite.rows_dropped

    async def _sweep_superseded_manifests(
        self, plan: RemovalPlan, access: TakedownAccess, counts: _Counts
    ) -> None:
        """The sweep, as the takedown credential lists and reads the versions now.

        The current version of each manifest was checked by the plan; an earlier one may hold a row
        the current one no longer does — a manifest re-published after a re-import, say — and a
        restorable version of a removed row is the row not removed. A version of a key an earlier
        run of this request rewrote, older than that rewrite, is one its purge should have taken.
        """
        swept = await plan.swept_from(access.versions)
        refuse_protected_versions(swept)
        if swept:
            counts.s3_versions_deleted += await access.versions.delete_versions(swept)

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

    async def _purge_inbox(self, plan: RemovalPlan, counts: _Counts) -> None:
        """The sync's inbox, as planned: after this machine's store, before the records."""
        purge_inbox(
            self.inbox,
            plan.inbox,
            request_id=plan.request_id,
            done=counts.inbox,
        )

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

    async def _rewrite_run_state(self, access: TakedownAccess, counts: _Counts) -> None:
        """Bucket mode, after the records: the bundle rewritten, confirmed, then its other versions purged.

        The PM's ruling of 2026-10-23: under the removal credential, after the rewrite is confirmed in
        the bucket. The save confirms it (the bucket's current version is the one written, with the
        digest written), and a save that is not confirmed is :class:`RunStateBundleNotRewritten`,
        with nothing purged: the earlier versions still name the removed files, so the removal is
        incomplete until it is run again.
        """
        if self.run_state is None:
            return
        await self.run_state.save_state_files()
        rewritten = await self.run_state.save_bundle()
        if not rewritten.saved or rewritten.version_id is None:
            raise RunStateBundleNotRewritten(rewritten.reason)
        stale = tuple(
            version
            for version in await access.versions.list_versions(RUN_STATE_BUNDLE_KEY)
            if version.key == RUN_STATE_BUNDLE_KEY and version.version_id != rewritten.version_id
        )
        refuse_protected_versions(stale)
        counts.s3_versions_deleted += await access.versions.delete_versions(stale)

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
            inbox_files_deleted=counts.inbox.deleted,
            inbox_files_rewritten=counts.inbox.rewritten,
            inbox_rewrites=tuple(
                InboxRewriteRecord(from_sha256=one.from_sha256, to_sha256=one.to_sha256)
                for one in counts.inbox.rewrites
            ),
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
            path_holds_released=sum(1 for hold in state.path_holds if hold.sha256 == sha256),
        )

    async def unsuppress(self, plan: UnsuppressPlan) -> UnsuppressReport:
        """Append the un-suppress entry to both copies of the list, and one entry to the removal log.

        Purged data is not restored: the file comes back only when an archive that holds it is
        imported again. The entry also lifts the hold on each path the file's removal took it from,
        with nothing more appended: a hold follows the file it came from.
        """
        access, probes_left = await self._authorised()
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
        return UnsuppressReport(plan=plan, log_entry=entry, preflight_probes_left=probes_left)

    # --------------------------------------------------------------------------------------
    # The takedown credential
    # --------------------------------------------------------------------------------------

    async def _authorised(self) -> tuple[TakedownAccess, tuple[ObjectVersion, ...]]:
        """The takedown credential, proven by :func:`preflight`. Built and checked once per service.

        With it, the earlier probes this call's preflight could not delete: none when the
        credential was proven by an earlier call.
        """
        probes_left: tuple[ObjectVersion, ...] = ()
        if self._access is None:
            try:
                access = self.takedown()
            except (StoreCredentialsExpired, StoreProfileNotConfigured) as refused:
                # A profile the AWS config lacks is the takedown's own refusal too (`v1-e29-t08`):
                # what an operator who typed `--execute` reads first is that nothing was deleted.
                named = refused.profile if isinstance(refused, StoreProfileNotConfigured) else None
                raise TakedownPreflightFailed(named, "start an AWS session", refused) from refused
            probes_left = await preflight(access, environment=self.environment)
            self._access = access
        return self._access, probes_left

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
