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
Noncurrent versions are not visible to the everyday credential's listing; `caselist remove` lists
and deletes those itself.

Checksums are the bucket's *recorded* digests, read with one `HeadObject` per listed source — the
listing states none (`debate_core.application.ports.evidence_store`). Nothing is downloaded: a
manifest's digest is compared, and its body is never read back from the bucket.

## What it reports

Counts, digests and keys — which are digests, or a caselist and a date. The school, team code and
filename in a manifest row never leave the manifest (`docs/policies/caselist-data-use.md`, rule 4).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Final

from debate_core.application.caselist.evidence_listing import (
    LocalEvidence,
    list_local_caselists,
    list_remote_caselists,
    list_remote_evidence,
    local_blob_sizes,
    read_local_snapshots,
)
from debate_core.application.caselist.publish_plan import (
    LocalSnapshot,
    digest_of_local_blob_key,
    remote_source_prefix,
    snapshot_manifest_key,
    snapshot_of_manifest_key,
    source_key,
    suppressed_rows,
    validate_publish_target,
)
from debate_core.application.caselist.suppression import load_suppression_state
from debate_core.application.errors import DomainError, NotFound
from debate_core.application.ports.evidence_store import EvidenceObjectStore, ObjectInfo, ObjectKey
from debate_core.application.ports.suppression import SuppressionList, SuppressionState
from debate_core.domain import Sha256Hex

__all__ = [
    "CaselistStatusReport",
    "CaselistStatusService",
    "NoCaselistEvidence",
    "SnapshotStatus",
]

_DEFAULT_CONCURRENCY: Final = 8


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
    """Distinct sources the local manifest names, suppressed ones excluded. 0 with no local manifest."""
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


@dataclass(frozen=True, slots=True)
class CaselistStatusReport:
    """Every snapshot compared, in caselist and snapshot order."""

    snapshots: tuple[SnapshotStatus, ...]
    suppressed_objects: tuple[ObjectKey, ...] = ()
    """Current source objects in the bucket whose digest is suppressed. A removal leftover."""

    @property
    def in_sync(self) -> bool:
        """True only when every snapshot agrees and nothing suppressed is left; what exits 0."""
        return all(snapshot.in_sync for snapshot in self.snapshots) and not self.suppressed_objects

    @property
    def drifted(self) -> tuple[SnapshotStatus, ...]:
        return tuple(snapshot for snapshot in self.snapshots if not snapshot.in_sync)


class CaselistStatusService:
    """Compares this machine's caselist snapshots with the environment's bucket. Writes nothing.

    Args:
        local: This machine's manifests and blobs.
        remote: The environment's evidence bucket.
        suppression: The removal suppression list. Required.
        concurrency: `HeadObject` calls in flight at once.
    """

    def __init__(
        self,
        *,
        local: LocalEvidence,
        remote: EvidenceObjectStore,
        suppression: SuppressionList,
        concurrency: int = _DEFAULT_CONCURRENCY,
    ) -> None:
        if concurrency < 1:
            raise ValueError("concurrency must be at least 1")
        self._local = local
        self._remote = remote
        self._suppression = suppression
        self._semaphore_size = concurrency

    async def status(self, caselist: str | None = None, snapshot: str | None = None) -> CaselistStatusReport:
        """Compare one caselist, or every caselist either side holds a manifest for.

        Raises :class:`NoCaselistEvidence` when neither side holds anything that was asked about.
        """
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
            statuses, residue = await self._caselist_status(
                name, snapshot, local_blobs, semaphore, suppression
            )
            compared.extend(statuses)
            leftovers.extend(residue)
        if not compared:
            raise NoCaselistEvidence(caselist, snapshot)
        return CaselistStatusReport(
            snapshots=tuple(compared), suppressed_objects=tuple(sorted(set(leftovers)))
        )

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
        sources = [source for source in local.sources if not suppression.suppresses_source(source.sha256)]
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
            suppressed=len(local.sources) - len(sources),
            suppressed_rows=suppressed_rows(local, suppression),
        )

    async def _head(self, key: ObjectKey, semaphore: asyncio.Semaphore) -> ObjectInfo | None:
        async with semaphore:
            try:
                return await self._remote.head(key)
            except NotFound:
                # Listed a moment ago and gone now.
                return None


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
