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
this machine cannot vouch for. Suppressed sources (`v1-e30-t07`) are expected to be absent from both
sides and are counted, not missed.

Checksums are the bucket's *recorded* digests, read with one `HeadObject` per listed source — the
listing states none (`debate_core.application.ports.evidence_store`). Nothing is downloaded: a
manifest's digest is compared, and its body is never read back from the bucket.

## What it reports

Counts, digests and keys — which are digests, or a caselist and a date. The school, team code and
filename in a manifest row never leave the manifest (`docs/policies/caselist-data-use.md`, rule 4).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Collection
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
    snapshot_manifest_key,
    snapshot_of_manifest_key,
    source_key,
    validate_publish_target,
)
from debate_core.application.errors import DomainError, NotFound
from debate_core.application.ports.evidence_store import EvidenceObjectStore, ObjectInfo, ObjectKey
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

    @property
    def in_sync(self) -> bool:
        return (
            self.local_manifest
            and self.manifest_present
            and not self.missing_sources
            and not self.missing_local
            and not self.checksum_mismatches
        )


@dataclass(frozen=True, slots=True)
class CaselistStatusReport:
    """Every snapshot compared, in caselist and snapshot order."""

    snapshots: tuple[SnapshotStatus, ...]

    @property
    def in_sync(self) -> bool:
        """True only when every snapshot agrees; what `caselist status` exits 0 on."""
        return all(snapshot.in_sync for snapshot in self.snapshots)

    @property
    def drifted(self) -> tuple[SnapshotStatus, ...]:
        return tuple(snapshot for snapshot in self.snapshots if not snapshot.in_sync)


class CaselistStatusService:
    """Compares this machine's caselist snapshots with the environment's bucket. Writes nothing.

    Args:
        local: This machine's manifests and blobs.
        remote: The environment's evidence bucket.
        suppressed: Digests on the removal suppression list, expected to be absent everywhere.
        concurrency: `HeadObject` calls in flight at once.
    """

    def __init__(
        self,
        *,
        local: LocalEvidence,
        remote: EvidenceObjectStore,
        suppressed: Collection[Sha256Hex] = frozenset(),
        concurrency: int = _DEFAULT_CONCURRENCY,
    ) -> None:
        if concurrency < 1:
            raise ValueError("concurrency must be at least 1")
        self._local = local
        self._remote = remote
        self._suppressed = frozenset(suppressed)
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

        local_blobs = await local_blob_sizes(self._local)
        semaphore = asyncio.Semaphore(self._semaphore_size)
        compared: list[SnapshotStatus] = []
        for name in caselists:
            compared.extend(await self._caselist_status(name, snapshot, local_blobs, semaphore))
        if not compared:
            raise NoCaselistEvidence(caselist, snapshot)
        return CaselistStatusReport(snapshots=tuple(compared))

    async def _caselist_status(
        self,
        caselist: str,
        snapshot: str | None,
        local_blobs: dict[Sha256Hex, int],
        semaphore: asyncio.Semaphore,
    ) -> list[SnapshotStatus]:
        local_snapshots = await read_local_snapshots(self._local, caselist, snapshot)
        remote = await list_remote_evidence(self._remote, caselist)
        heads: dict[ObjectKey, asyncio.Task[ObjectInfo | None]] = {}

        def head(key: ObjectKey) -> asyncio.Task[ObjectInfo | None]:
            # One head per key per run, however many snapshots name it.
            if key not in heads:
                heads[key] = asyncio.ensure_future(self._head(key, semaphore))
            return heads[key]

        statuses = list(
            await asyncio.gather(
                *(self._snapshot_status(local, local_blobs, remote, head) for local in local_snapshots)
            )
        )

        held = {local.snapshot for local in local_snapshots}
        for key in sorted(remote):
            named = snapshot_of_manifest_key(caselist, key)
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
        return sorted(statuses, key=lambda status: status.snapshot)

    async def _snapshot_status(
        self,
        local: LocalSnapshot,
        local_blobs: dict[Sha256Hex, int],
        remote: dict[ObjectKey, int],
        head: Callable[[ObjectKey], Awaitable[ObjectInfo | None]],
    ) -> SnapshotStatus:
        sources = [source for source in local.sources if source.sha256 not in self._suppressed]
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
        )

    async def _head(self, key: ObjectKey, semaphore: asyncio.Semaphore) -> ObjectInfo | None:
        async with semaphore:
            try:
                return await self._remote.head(key)
            except NotFound:
                # Listed a moment ago and gone now.
                return None
