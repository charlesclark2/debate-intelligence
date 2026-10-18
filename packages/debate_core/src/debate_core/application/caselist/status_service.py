"""Whether this machine's caselist snapshots and the bucket's agree, snapshot by snapshot.

`debate-research caselist status` is a thin command over :class:`CaselistStatusService`. It answers
the question an operator asks after a publish, and the one the scheduled sync (`v1-e34`) asks
before trusting a manifest: is every snapshot this machine holds in the bucket, whole?

## What "agree" means

For each snapshot, all of:

* this machine holds its manifest, and every source that manifest names;
* the bucket holds the same manifest — the same bytes, by the digest the bucket recorded;
* the bucket holds every source the manifest names, each with its own digest recorded under it.

A snapshot the bucket holds a manifest for and this machine does not is drift too: it is a snapshot
this machine cannot vouch for.

A caselist's snapshots include its complete archives, `full/<date>` (`v1-e34-t04`), compared the
same way: the sync's retention stage asks this whether a complete archive's publish is confirmed
before its zip leaves the inbox, and a complete archive's manifest the bucket holds unaccounted for
would be drift like any other.

## Suppressed sources

The suppression list (`v1-e30-t07`) is a required argument. A suppressed source is expected to be
absent from both sides and is counted, not missed. What *is* drift is anything a removal should
have taken and did not: a local manifest with a stored row the list stops
(:attr:`SnapshotStatus.suppressed_rows`), or a current object in the bucket under this caselist's
source prefix whose digest is suppressed (:attr:`CaselistStatusReport.suppressed_objects`). That
makes `caselist status` the check an operator runs after a removal (`caselist-removal.md`, step 6):
clean means every manifest and every current source object agrees, and nothing suppressed is left.

## What a removal left behind

A plain listing shows current objects only. Asked to (`residue=True`, which the command does), the
service also lists object versions and reports, per caselist, what the bucket still holds of files
the list says were removed whole: current objects, noncurrent versions and delete markers
(:attr:`CaselistStatusReport.residue`, :mod:`debate_core.application.caselist.removal_residue`,
`v1-e30-t10`). The everyday `EvidenceOperator` profile may list versions under `raw/` and `parsed/`
(`v1-e29-t06`, applied in dev and prod on 2026-10-08), so this needs no takedown profile, and it
deletes nothing. Anything found is drift. In an environment where that grant is not applied the
listing is refused, and the caselist is reported as *not checked*, which is not a finding of none
and does not by itself make the comparison fail. `caselist pull` asks for the comparison alone, so
its runs list no versions.

The same check reports, per caselist one of this environment's completed removals touched, the
manifest and aggregate versions older than that removal (`v1-e30-t15`), from the listing and the
removal log, which it reads as it reads the suppression list: this machine's copy and the bucket's,
as one, with the scopes beside them. Only entries recorded in this environment are compared: in
prod the command runs against the dev data directory, whose copy holds dev's removals.

## What a removal's hold says is owed

A removal by `--source` holds the removed file's path (`v1-e30-t13`), and the importer of this build
refuses an upload there. Two things still say the same removal has to be run again, and the
comparison reports both (`v1-e30-t21`):

* a stored row at a held path, in a snapshot the hold covers (:attr:`SnapshotStatus.held_rows`):
  an import by a build from before `v1-e30-t13`, which reads no hold, wrote it;
* a skipped member's row at a held path, in a snapshot the hold covers
  (:attr:`SnapshotStatus.held_skipped_rows`, `v1-e30-t22`): a symbolic link named as the removed
  file, which every build before `v1-e30-t22` gave a row and this build's importer withholds;
* an upload at a held path in an archive in the download inbox (:attr:`CaselistStatusReport.held_in_inbox`),
  asked for with `held_in_inbox=True` from a service built with the inbox: refused at import, or
  waiting to be.

None is a difference between this machine and the bucket, so none changes
:attr:`CaselistStatusReport.in_sync` or the command's exit status. Each is named by the request that
holds its path, and a file by its digest too, never by the path. The inbox is read only when asked, because it
means reading every archive in it: `caselist status` asks, and `caselist pull` does not. An archive
there that cannot be read is passed over; a removal's dry run names it.

## Bytes the publisher does not upload

Bytes that only held rows of a manifest name are never uploaded (`v1-e30-t22`; `publish_plan`,
"Bytes only held rows name are not uploaded"), so the comparison does not expect them in the bucket:
they are not among a snapshot's :attr:`SnapshotStatus.sources`, and neither the bucket nor this
machine lacking them is drift or owed. The build that imported the held row stored them on this
machine; running the same removal again deletes them here, and a re-run is what the held row already
says is owed.

## A manifest mismatch and a source mismatch

A checksum mismatch is one of two kinds (:class:`MismatchKind`, `v1-e30-t12`), told apart by
comparing the key with that snapshot's own :attr:`SnapshotStatus.manifest_key`, never by a prefix:
`manifests/` also holds the suppression records, and a complete archive's manifest is one level
further down. A **source** is filed under the digest of its bytes, so other bytes under its key are
never expected, and that needs a person. A **manifest** is not content-addressed: this machine
rewrites one in place after a camp metadata re-import (`v1-e30-t08`) or a removal, and the bucket's
copy differs until the next `caselist publish`, which uploads a manifest whose recorded digest
differs. Both kinds are drift, as they always were.

Unless the publisher withholds that manifest (`v1-e30-t19`): a manifest with a row a removal stops
or holds is never uploaded, so a publish does not clear its mismatch, and the removal run again
does. Whether it does is the publisher's own rule, asked of the snapshot's publish plan
(:attr:`~debate_core.application.caselist.publish_plan.SnapshotPlan.withholding_rows`) rather than
restated here, so the two cannot part ways: :attr:`SnapshotStatus.manifest_withheld`.

## A withdrawn copy's residue (`v1-e30-t19`)

With the residue check, the withdrawal record beside the list (`withdrawals.jsonl`, `v1-e30-t16`)
says which caselist each copy a removal withdrew was taken from. For a caselist that no longer
holds the file (no manifest of it on this machine names the file at a path the list does not stop)
what is left of that caselist's copy is counted, and named by the caselist and the request
(:mod:`~debate_core.application.caselist.removal_residue`, "A copy withdrawn from a caselist"). A
withdrawal an earlier build made has no record, and its request is named as not attributed
(:attr:`CaselistStatusReport.withdrawals_not_attributed`). Neither is part of
:attr:`CaselistStatusReport.in_sync`: they are new findings, and the command's exit status is as it
was.

Checksums are the bucket's *recorded* digests, read with one `HeadObject` per listed source — the
listing states none (`debate_core.application.ports.evidence_store`). Nothing is downloaded: a
manifest's digest is compared, and its body is never read back from the bucket.

## What it reports

Counts, digests and keys — which are digests, or a caselist and a date — and the request ids of the
removals a hold says are owed. The school, team code and filename in a manifest row never leave the
manifest (`docs/policies/caselist-data-use.md`, rule 4), and neither does an inbox archive's name.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Protocol

from debate_core.application.caselist.evidence_listing import (
    LocalEvidence,
    list_local_caselists,
    list_remote_caselists,
    list_remote_evidence,
    local_blob_sizes,
    read_local_snapshots,
)
from debate_core.application.caselist.publish_plan import (
    OPENEV,
    HeldRow,
    LocalSnapshot,
    build_publish_plan,
    digest_of_local_blob_key,
    held_only_digests,
    held_rows,
    held_skipped_rows,
    remote_source_prefix,
    snapshot_manifest_key,
    snapshot_of_manifest_key,
    source_key,
    suppressed_rows,
    validate_publish_target,
)
from debate_core.application.caselist.removal_residue import (
    CaselistResidue,
    CompletedRemovals,
    completed_removals,
    removal_residue,
)
from debate_core.application.caselist.suppression import (
    caselist_withdrawn_from,
    load_suppression_state,
    read_withdrawals,
)
from debate_core.application.errors import DomainError, NotFound
from debate_core.application.ports.evidence_store import EvidenceObjectStore, ObjectInfo, ObjectKey
from debate_core.application.ports.evidence_versions import EvidenceVersionStore
from debate_core.application.ports.suppression import (
    RemovalLog,
    RemovalScopeLog,
    SuppressionAction,
    SuppressionList,
    SuppressionState,
    camp_path_scope,
    disclosure_digest,
)
from debate_core.domain import Sha256Hex

__all__ = [
    "CASELIST_DRIFT",
    "REMOVAL_RESIDUE",
    "CaselistStatusReport",
    "CaselistStatusService",
    "HeldInboxUpload",
    "InboxHolds",
    "MismatchKind",
    "NoCaselistEvidence",
    "SnapshotStatus",
]

CASELIST_DRIFT: Final = "CASELIST_DRIFT"
"""The code of a comparison that found the two sides differ: `caselist status`'s `error.code`, and
what the report stage of `caselist pull` records for a snapshot not in sync (`v1-e34-t13`). An
outcome's code, not an exception's: the comparison ran, and running it again gives the same answer."""

REMOVAL_RESIDUE: Final = "REMOVAL_RESIDUE"
"""The code of a comparison in which every snapshot agrees and the bucket still holds versions of a
file the suppression list says was removed: `caselist status`'s `error.code` then. An outcome's
code, like :data:`CASELIST_DRIFT`, and as deterministic: only a removal run again changes it."""

_DEFAULT_CONCURRENCY: Final = 8


class MismatchKind(StrEnum):
    """What a checksum mismatch is on: see "A manifest mismatch and a source mismatch" above."""

    MANIFEST = "manifest"
    """The snapshot's own manifest. `caselist publish` uploads this machine's copy."""
    SOURCE = "source"
    """A source, filed by the digest of its bytes. A person finds out why the bucket holds others."""


@dataclass(frozen=True, slots=True, order=True)
class HeldInboxUpload:
    """An upload at a path a removal holds, in an archive in the download inbox (`v1-e30-t21`).

    Its caselist, the snapshot its archive is (`2026-10-08`, or `full/2026-10-09`), its digest and
    the request holding the path. Never the archive's file name or the path.
    """

    caselist: str
    snapshot: str
    sha256: Sha256Hex
    request_id: str


class InboxHolds(Protocol):
    """The download inbox, asked which of its uploads a removal's hold covers.

    :class:`~debate_core.application.caselist.inbox_purge.CaselistInbox` is one. A protocol, because
    the inbox module imports the pull, and the pull imports this comparison.
    """

    def held_uploads(self, suppression: SuppressionState) -> tuple[HeldInboxUpload, ...]:
        """Every real member of a weekly or complete archive there at a held path, in a snapshot the
        hold covers, that the list does not already stop. Reads only."""
        ...


class NoCaselistEvidence(DomainError):
    """Neither this machine nor the bucket holds a manifest for what was asked about.

    A refusal rather than an empty report that reads as "in sync": a mistyped slug would otherwise
    exit 0.
    """

    def __init__(self, caselist: str | None, snapshot: str | None) -> None:
        what = "any caselist" if caselist is None else caselist + (f" {snapshot}" if snapshot else "")
        super().__init__(f"no manifest for {what} on this machine or in the bucket")


@dataclass(frozen=True, slots=True)
class SnapshotStatus:
    """One snapshot, compared across this machine and the bucket."""

    caselist: str
    snapshot: str
    manifest_key: ObjectKey
    local_manifest: bool
    """False for a snapshot only the bucket holds a manifest for."""
    manifest_present: bool
    """Whether the bucket holds a manifest at :attr:`manifest_key`."""
    sources: int
    """Distinct sources the local manifest names, less suppressed ones and those only held rows name
    (`v1-e30-t22`), which are never uploaded. 0 with no local manifest."""
    local_files: int
    """How many of :attr:`sources` this machine's blob store holds."""
    published_sources: int
    """How many of :attr:`sources` the bucket holds with their own digest recorded."""
    missing_sources: tuple[Sha256Hex, ...] = ()
    """Sources the manifest names and the bucket does not hold."""
    missing_local: tuple[Sha256Hex, ...] = ()
    """Sources the manifest names and this machine does not hold."""
    checksum_mismatches: tuple[ObjectKey, ...] = ()
    """Keys the bucket holds with other bytes, or no recorded digest: sources, or the manifest."""
    suppressed: int = 0
    suppressed_rows: tuple[Sha256Hex, ...] = ()
    """Digests of stored rows in the local manifest the suppression list stops. A removal leftover."""
    held_rows: tuple[HeldRow, ...] = ()
    """Stored rows in the local manifest at a path a removal holds (`v1-e30-t21`): the same removal is
    owed again. Not a difference from the bucket, so not part of :attr:`in_sync`."""
    held_skipped_rows: tuple[str, ...] = ()
    """The request holding the path of each skipped member's row at a held path (`v1-e30-t22`), which
    an earlier build wrote: the same removal is owed again. Not part of :attr:`in_sync` either."""
    manifest_withheld: bool = False
    """Whether the publisher withholds this snapshot's manifest for its rows, by its own rule
    (`v1-e30-t19`): a publish then does not clear a mismatch of it, and the removal must be
    finished first. False for a snapshot this machine holds no manifest of."""

    @property
    def in_sync(self) -> bool:
        return (
            self.local_manifest
            and self.manifest_present
            and not self.missing_sources
            and not self.missing_local
            and not self.checksum_mismatches
            and not self.suppressed_rows
        )

    def mismatch_kind(self, key: ObjectKey) -> MismatchKind:
        """The kind of a key in :attr:`checksum_mismatches`: this snapshot's manifest, or a source."""
        return MismatchKind.MANIFEST if key == self.manifest_key else MismatchKind.SOURCE

    @property
    def manifest_mismatched(self) -> bool:
        """Whether the bucket's manifest differs from this machine's: a publish uploads it."""
        return self.manifest_key in self.checksum_mismatches

    @property
    def source_mismatches(self) -> tuple[ObjectKey, ...]:
        """The source keys the bucket holds with other bytes, or no recorded digest."""
        return tuple(key for key in self.checksum_mismatches if key != self.manifest_key)

    @property
    def incomplete(self) -> bool:
        """Whether something is missing: a manifest on either side, or a source on either side."""
        return (
            not self.local_manifest
            or not self.manifest_present
            or bool(self.missing_sources)
            or bool(self.missing_local)
        )


@dataclass(frozen=True, slots=True)
class CaselistStatusReport:
    """Every snapshot compared, in caselist and snapshot order."""

    snapshots: tuple[SnapshotStatus, ...]
    suppressed_objects: tuple[ObjectKey, ...] = ()
    """Current source objects in the bucket whose digest is suppressed. A removal leftover."""
    residue: tuple[CaselistResidue, ...] = ()
    """Per caselist compared, what a version listing shows of its removed files. Empty when the
    caller did not ask for the check."""
    removals_not_checked: tuple[str, ...] = ()
    """Request ids of completed removals whose log entries do not say which caselists they touched,
    so that no manifest or aggregate version is checked against them (`v1-e30-t15`)."""
    held_in_inbox: tuple[HeldInboxUpload, ...] = ()
    """Uploads at a held path in the download inbox's archives, of the caselists compared
    (`v1-e30-t21`). Empty when the caller did not ask. Not part of :attr:`in_sync`."""
    withdrawals_not_attributed: tuple[str, ...] = ()
    """Request ids of withdrawals the list still suppresses that no withdrawal record attributes to
    a caselist: made by a build from before `v1-e30-t16`, so what is left of their copies is not
    checked (`v1-e30-t19`). Empty when the caller did not ask for the residue check."""

    @property
    def in_sync(self) -> bool:
        """True only when every snapshot agrees and nothing suppressed is left; what exits 0.

        A caselist whose residue could not be checked does not make this false: it is reported as
        not checked (:attr:`residue_not_checked`).
        """
        return (
            all(snapshot.in_sync for snapshot in self.snapshots)
            and not self.suppressed_objects
            and not self.residue_found
        )

    @property
    def drifted(self) -> tuple[SnapshotStatus, ...]:
        return tuple(snapshot for snapshot in self.snapshots if not snapshot.in_sync)

    @property
    def manifest_mismatched(self) -> tuple[SnapshotStatus, ...]:
        """The snapshots whose manifest the bucket holds with other bytes."""
        return tuple(snapshot for snapshot in self.snapshots if snapshot.manifest_mismatched)

    @property
    def source_mismatched(self) -> tuple[SnapshotStatus, ...]:
        """The snapshots with a source the bucket holds with other bytes."""
        return tuple(snapshot for snapshot in self.snapshots if snapshot.source_mismatches)

    @property
    def caselists(self) -> tuple[str, ...]:
        """The caselists compared, in order: each holds at least one snapshot on one side."""
        return tuple(dict.fromkeys(snapshot.caselist for snapshot in self.snapshots))

    def suppressed_objects_of(self, caselist: str) -> tuple[ObjectKey, ...]:
        """The :attr:`suppressed_objects` among `caselist`'s sources.

        Per caselist, because that is how they are found: one listing of the caselist's source
        prefix, which every snapshot of it shares. A source object belongs to no one snapshot.
        """
        prefix = remote_source_prefix(caselist)
        return tuple(key for key in self.suppressed_objects if key.startswith(prefix))

    @property
    def held_snapshots(self) -> tuple[SnapshotStatus, ...]:
        """The snapshots with a row at a held path: a stored row, or a skipped member's."""
        return tuple(
            snapshot for snapshot in self.snapshots if snapshot.held_rows or snapshot.held_skipped_rows
        )

    @property
    def removals_owed(self) -> tuple[str, ...]:
        """The request ids whose removal a held row or a held inbox upload says to run again, sorted."""
        rows = {row.request_id for snapshot in self.snapshots for row in snapshot.held_rows}
        skipped = {request for snapshot in self.snapshots for request in snapshot.held_skipped_rows}
        return tuple(sorted(rows | skipped | {upload.request_id for upload in self.held_in_inbox}))

    def held_in_inbox_of(self, caselist: str) -> tuple[HeldInboxUpload, ...]:
        """The :attr:`held_in_inbox` uploads of `caselist`."""
        return tuple(upload for upload in self.held_in_inbox if upload.caselist == caselist)

    @property
    def residue_found(self) -> bool:
        """Whether a version listing showed anything left of a removed file."""
        return any(one.found for one in self.residue)

    @property
    def withdrawn_copies_left(self) -> bool:
        """Whether a version listing showed anything left of a copy withdrawn from a caselist
        (`v1-e30-t19`). Not part of :attr:`in_sync`."""
        return any(one.withdrawn_copies for one in self.residue)

    @property
    def residue_not_checked(self) -> tuple[str, ...]:
        """The caselists whose version listing was refused."""
        return tuple(one.caselist for one in self.residue if not one.checked)


class CaselistStatusService:
    """Compares this machine's caselist snapshots with the environment's bucket. Writes nothing.

    Args:
        local: This machine's manifests and blobs.
        remote: The environment's evidence bucket.
        suppression: The removal suppression list. Required.
        versions: The bucket's object versions through the everyday profile, for the residue check.
            Listed only, and only when :meth:`status` is asked for residue.
        removal_log: The removal log, this machine's copy and the bucket's read as one, for the
            manifest and aggregate versions older than a removal (`v1-e30-t15`). Read only when
            :meth:`status` is asked for residue. Without one, no removal is known.
        environment: This environment, `dev` or `prod`. Only its own removals are compared.
        inbox: The download inbox, for the uploads a removal's hold covers there (`v1-e30-t21`).
            Read only when :meth:`status` is asked for them.
        concurrency: `HeadObject` calls in flight at once.
    """

    def __init__(
        self,
        *,
        local: LocalEvidence,
        remote: EvidenceObjectStore,
        suppression: SuppressionList,
        versions: EvidenceVersionStore | None = None,
        removal_log: RemovalLog | None = None,
        environment: str | None = None,
        inbox: InboxHolds | None = None,
        concurrency: int = _DEFAULT_CONCURRENCY,
    ) -> None:
        if concurrency < 1:
            raise ValueError("concurrency must be at least 1")
        if removal_log is not None and environment is None:
            raise ValueError("a removal log is compared only with its own environment's removals; name it")
        self._local = local
        self._remote = remote
        self._suppression = suppression
        self._versions = versions
        self._removal_log = removal_log
        self._environment = environment
        self._inbox = inbox
        self._semaphore_size = concurrency

    async def status(
        self,
        caselist: str | None = None,
        snapshot: str | None = None,
        *,
        residue: bool = False,
        held_in_inbox: bool = False,
    ) -> CaselistStatusReport:
        """Compare one caselist, or every caselist either side holds a manifest for.

        With `residue`, also list object versions and report what is left of each compared
        caselist's removed files, whichever snapshot was asked about: see "What a removal left
        behind" in the module docstring. With `held_in_inbox`, also read the download inbox for
        uploads a removal's hold covers, of the caselists compared and the snapshot asked about:
        see "What a removal's hold says is owed".

        Raises :class:`NoCaselistEvidence` when neither side holds anything that was asked about.
        """
        if residue and self._versions is None:
            raise ValueError("the residue check needs a version store; this service was built without one")
        if held_in_inbox and self._inbox is None:
            raise ValueError("the inbox check needs the inbox; this service was built without one")
        if caselist is None:
            if snapshot is not None:
                raise ValueError("a snapshot is only meaningful with a caselist")
            caselists = sorted(
                set(await list_local_caselists(self._local)) | set(await list_remote_caselists(self._remote))
            )
        else:
            validate_publish_target(caselist, snapshot)
            caselists = [caselist]

        suppression = await load_suppression_state(self._suppression)
        local_blobs = await local_blob_sizes(self._local)
        semaphore = asyncio.Semaphore(self._semaphore_size)
        compared: list[SnapshotStatus] = []
        leftovers: list[ObjectKey] = []
        for name in caselists:
            statuses, suppressed_objects = await self._caselist_status(
                name, snapshot, local_blobs, semaphore, suppression
            )
            compared.extend(statuses)
            leftovers.extend(suppressed_objects)
        if not compared:
            raise NoCaselistEvidence(caselist, snapshot)
        left: list[CaselistResidue] = []
        removals = CompletedRemovals()
        not_attributed: tuple[str, ...] = ()
        if residue and self._versions is not None:
            removals = await self._completed_removals()
            withdrawn, not_attributed = await self._withdrawn_copies(suppression, caselists)
            left = [
                await removal_residue(self._versions, name, suppression, removals, withdrawn.get(name))
                for name in caselists
            ]
        inbox: tuple[HeldInboxUpload, ...] = ()
        if held_in_inbox and self._inbox is not None:
            inbox = tuple(
                sorted(
                    upload
                    for upload in self._inbox.held_uploads(suppression)
                    if upload.caselist in caselists and snapshot in (None, upload.snapshot)
                )
            )
        return CaselistStatusReport(
            snapshots=tuple(compared),
            suppressed_objects=tuple(sorted(set(leftovers))),
            residue=tuple(left),
            removals_not_checked=removals.not_checked,
            held_in_inbox=inbox,
            withdrawals_not_attributed=not_attributed,
        )

    async def _withdrawn_copies(
        self, suppression: SuppressionState, caselists: Sequence[str]
    ) -> tuple[dict[str, dict[Sha256Hex, str]], tuple[str, ...]]:
        """Per caselist, the files withdrawn from it that it keeps no holder of, with the request that
        withdrew each; and the requests of withdrawals no record attributes (`v1-e30-t19`).

        Each withdrawal the list still suppresses, whole files apart (the residue check counts those
        as removed), is attributed by the withdrawal record. A caselist still holds a file where a
        manifest of it on this machine names the file at a path the list does not stop; its copy
        is then that holder's, as the removal itself leaves it (`kept_in`).
        """
        attributed: dict[str, dict[Sha256Hex, str]] = {}
        not_attributed: set[str] = set()
        withdrawals = await read_withdrawals(self._suppression)
        for entry in await self._suppression.entries():
            # A whole file's entry is the residue check's own; one since lifted is no longer withdrawn.
            if (
                entry.action is not SuppressionAction.SUPPRESS
                or suppression.suppresses_source(entry.sha256)
                or not suppression.suppresses(entry.sha256, disclosure=entry.disclosure)
            ):
                continue
            caselist = caselist_withdrawn_from(entry, withdrawals)
            if caselist is None:
                not_attributed.add(entry.request_id or "a removal with no request id")
            elif caselist in caselists and entry.request_id is not None:
                attributed.setdefault(caselist, {}).setdefault(entry.sha256, entry.request_id)
        for caselist, digests in attributed.items():
            held = await self._held_in(caselist, suppression)
            attributed[caselist] = {
                digest: request for digest, request in digests.items() if digest not in held
            }
        return attributed, tuple(sorted(not_attributed))

    async def _held_in(self, caselist: str, suppression: SuppressionState) -> frozenset[Sha256Hex]:
        """The files a manifest of `caselist` on this machine names at a path the list does not stop."""
        held: set[Sha256Hex] = set()
        for local in await read_local_snapshots(self._local, caselist, None, full_archives=True):
            scope = camp_path_scope(local.snapshot) if caselist == OPENEV else caselist
            held.update(
                digest
                for digest, path in local.stored_rows
                if not suppression.suppresses(digest, disclosure=disclosure_digest(scope, path))
            )
        return frozenset(held)

    async def _completed_removals(self) -> CompletedRemovals:
        """This environment's completed removals, from both copies of the log and of its scopes."""
        if self._removal_log is None or self._environment is None:
            return CompletedRemovals()
        log = self._removal_log
        scopes = await log.scopes() if isinstance(log, RemovalScopeLog) else ()
        return completed_removals(await log.entries(), scopes, self._environment)

    async def _caselist_status(
        self,
        caselist: str,
        snapshot: str | None,
        local_blobs: dict[Sha256Hex, int],
        semaphore: asyncio.Semaphore,
        suppression: SuppressionState,
    ) -> tuple[list[SnapshotStatus], list[ObjectKey]]:
        local_snapshots = await read_local_snapshots(self._local, caselist, snapshot, full_archives=True)
        remote = await list_remote_evidence(self._remote, caselist)
        residue = [key for key in remote if _suppressed_source_key(caselist, key, suppression)]
        heads: dict[ObjectKey, asyncio.Task[ObjectInfo | None]] = {}

        def head(key: ObjectKey) -> asyncio.Task[ObjectInfo | None]:
            # One head per key per run, however many snapshots name it.
            if key not in heads:
                heads[key] = asyncio.ensure_future(self._head(key, semaphore))
            return heads[key]

        statuses = list(
            await asyncio.gather(
                *(
                    self._snapshot_status(local, local_blobs, remote, head, suppression)
                    for local in local_snapshots
                )
            )
        )

        held = {local.snapshot for local in local_snapshots}
        for key in sorted(remote):
            named = snapshot_of_manifest_key(caselist, key, full_archives=True)
            if named is None or named in held or (snapshot is not None and named != snapshot):
                continue
            statuses.append(
                SnapshotStatus(
                    caselist=caselist,
                    snapshot=named,
                    manifest_key=key,
                    local_manifest=False,
                    manifest_present=True,
                    sources=0,
                    local_files=0,
                    published_sources=0,
                )
            )
        return sorted(statuses, key=lambda status: status.snapshot), residue

    async def _snapshot_status(
        self,
        local: LocalSnapshot,
        local_blobs: dict[Sha256Hex, int],
        remote: dict[ObjectKey, int],
        head: Callable[[ObjectKey], Awaitable[ObjectInfo | None]],
        suppression: SuppressionState,
    ) -> SnapshotStatus:
        suppressed = [source for source in local.sources if suppression.suppresses_source(source.sha256)]
        held_back = held_only_digests(local, suppression)
        sources = [
            source for source in local.sources if source not in suppressed and source.sha256 not in held_back
        ]
        missing_local = tuple(
            source.sha256 for source in sources if local_blobs.get(source.sha256) != source.size
        )

        manifest_key = snapshot_manifest_key(local.caselist, local.snapshot)
        keyed = [(source, source_key(local.caselist, local.snapshot, source.sha256)) for source in sources]
        # Every head is started before any is awaited, so they run `concurrency` at a time.
        pending = {key: head(key) for _, key in keyed if key in remote}
        if manifest_key in remote:
            pending[manifest_key] = head(manifest_key)

        missing_remote: list[Sha256Hex] = []
        mismatched: list[ObjectKey] = []
        published = 0
        for source, key in keyed:
            if key not in pending:
                missing_remote.append(source.sha256)
                continue
            info = await pending[key]
            if info is None:
                missing_remote.append(source.sha256)
            elif info.sha256 == source.sha256 and info.size == source.size:
                published += 1
            else:
                mismatched.append(key)

        manifest_present = manifest_key in pending
        if manifest_present:
            remote_manifest = await pending[manifest_key]
            local_manifest = await self._local.objects.head(manifest_key)
            if remote_manifest is None:
                manifest_present = False
            elif remote_manifest.sha256 is None or remote_manifest.sha256 != local_manifest.sha256:
                mismatched.append(manifest_key)

        return SnapshotStatus(
            caselist=local.caselist,
            snapshot=local.snapshot,
            manifest_key=manifest_key,
            local_manifest=True,
            manifest_present=manifest_present,
            sources=len(sources),
            local_files=len(sources) - len(missing_local),
            published_sources=published,
            missing_sources=tuple(sorted(missing_remote)),
            missing_local=tuple(sorted(missing_local)),
            checksum_mismatches=tuple(sorted(mismatched)),
            suppressed=len(suppressed),
            suppressed_rows=suppressed_rows(local, suppression),
            held_rows=held_rows(local, suppression),
            held_skipped_rows=held_skipped_rows(local, suppression),
            manifest_withheld=_publisher_withholds(local, local_blobs, remote, suppression),
        )

    async def _head(self, key: ObjectKey, semaphore: asyncio.Semaphore) -> ObjectInfo | None:
        async with semaphore:
            try:
                return await self._remote.head(key)
            except NotFound:
                # Listed a moment ago and gone now.
                return None


def _publisher_withholds(
    local: LocalSnapshot,
    local_blobs: dict[Sha256Hex, int],
    remote: dict[ObjectKey, int],
    suppression: SuppressionState,
) -> bool:
    """Whether the publisher withholds `local`'s manifest for its rows: asked of its own plan
    (:attr:`~debate_core.application.caselist.publish_plan.SnapshotPlan.withholding_rows`)."""
    (plan,) = build_publish_plan(
        local.caselist, [local], local_blobs=local_blobs, remote=remote, suppression=suppression
    ).snapshots
    return bool(plan.withholding_rows)


def _suppressed_source_key(caselist: str, key: ObjectKey, suppression: SuppressionState) -> bool:
    """Whether `key` is a source object of `caselist` whose whole source is suppressed."""
    prefix = remote_source_prefix(caselist)
    if not key.startswith(prefix):
        return False
    tail = key[len(prefix) :]
    # `raw/openev/` holds every year below it: `2026/sha256/ab/cd/<digest>`.
    if "/" in tail and not tail.startswith("sha256/"):
        tail = tail.split("/", 1)[1]
    digest = digest_of_local_blob_key(tail)
    return digest is not None and suppression.suppresses_source(digest)
