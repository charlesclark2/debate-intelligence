"""The raw sources a restored copy's manifests name, fetched into the copy (`v1-e40-t10`).

`caselist restore-run-state --with-sources` (:mod:`debate_core.application.caselist.run_state_restore`)
restores the run's working copy and then this: every source the restored manifests name, from `raw/`
in the bucket, into the copy's blob tree. What a hand publish to prod needs, since a copy restored
under the dev lock holds manifests and no bytes (the PM's ruling (a) on `v1-e40-t06`'s question 2).

**Which sources.** Exactly those the copy's manifests name, each at its own key: a manifest's stored
rows give each digest, and :func:`~debate_core.application.caselist.publish_plan.source_key` the key
the publisher filed it under. Nothing lists `raw/` to find them. `--caselist` and `--snapshot` narrow
the manifests read, never widen them. A digest several manifests name is fetched once, since the blob
tree is keyed by digest alone.

**What is skipped.** A source the copy's suppression list stops (the list reconciled with the
bucket's just before), and a digest only rows at a held path name: the publisher never uploads either
(:func:`~debate_core.application.caselist.publish_plan.build_publish_plan`), so they are not asked for
and are counted as `suppressed`. Every other named source is fetched.

**A missing source is never skipped silently.** One the bucket does not hold stops the command,
non-zero, with the count, after the others have been tried so that the count is whole. S3 answers a
read of a missing key with `403` to a caller whose listing grant is scoped by prefix, as the everyday
operator's is, so a refused read is a missing source only when a listing of that one key shows
nothing; a refusal of a key that is there stays a refusal. That listing names the key as its prefix,
so it can show nothing but that key.

**Each fetch** lands in a temporary file beside its final place, inside the copy, and is hashed. Bytes
whose SHA-256 is not the digest the manifest names are deleted and refused, and no further fetch
starts. Bytes that match are `fsync`-ed, renamed into place, and the directory `fsync`-ed, as the blob
store's own writer does. Every path is checked to be inside the copy before anything is written there.

**Room.** Before the first fetch the count and the bytes the manifests give are announced, and the
command refuses when the copy's filesystem has less free than those bytes and
:data:`FREE_SPACE_MARGIN_BYTES` more.

**What is logged** is counts and bytes: no key, digest, school, team, path or file name.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import secrets
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from debate_core.application.caselist.evidence_listing import LocalEvidence, read_local_manifest
from debate_core.application.caselist.manifest import MANIFEST_DIRECTORY
from debate_core.application.caselist.publish_plan import (
    LocalSnapshot,
    held_only_digests,
    local_blob_key,
    source_key,
)
from debate_core.application.errors import BlobIntegrityError, DomainError, NotFound, StoreAccessDenied
from debate_core.application.ports.evidence_store import EvidenceObjectStore, ObjectKey
from debate_core.application.ports.suppression import SuppressionState
from debate_core.domain import Sha256Hex

__all__ = [
    "FREE_SPACE_MARGIN_BYTES",
    "NamedSource",
    "RestoredSources",
    "RestoredSourcesIncomplete",
    "SnapshotsNotRestored",
    "SourceSelection",
    "SourcesFetched",
    "SourcesPlan",
    "TooLittleRoomForSources",
]

logger = logging.getLogger(__name__)

FREE_SPACE_MARGIN_BYTES: Final = 1024**3
"""Free space asked for beyond the sources' own bytes: 1 GiB, for the filesystem's blocks and
directories over some tens of thousands of files, and for whatever else writes to the disk meanwhile."""

_PARALLEL_DOWNLOADS: Final = 16
_LANDING_PREFIX: Final = ".raw-"


@dataclass(frozen=True, slots=True)
class SourceSelection:
    """Which restored manifests' sources to fetch. Empty means every one.

    Args:
        caselists: Only manifests of these caselists (`openev` for camp releases).
        snapshots: Only manifests of these snapshots, of any caselist selected.
    """

    caselists: tuple[str, ...] = ()
    snapshots: tuple[str, ...] = ()

    def selects(self, snapshot: LocalSnapshot) -> bool:
        return (not self.caselists or snapshot.caselist in self.caselists) and (
            not self.snapshots or snapshot.snapshot in self.snapshots
        )


@dataclass(frozen=True, slots=True, order=True)
class NamedSource:
    """One source to fetch: its digest, the size its manifest gives, and the key it is filed under."""

    sha256: Sha256Hex
    size: int
    key: ObjectKey


@dataclass(frozen=True, slots=True)
class SourcesPlan:
    """What the selected manifests name. Counts and bytes are all anything outside reads."""

    manifests: int
    named: int
    """Distinct digests the selected manifests name."""
    to_fetch: tuple[NamedSource, ...]
    suppressed: int
    """Named digests not asked for: the suppression list stops them, or only held rows name them."""

    @property
    def bytes_to_fetch(self) -> int:
        return sum(source.size for source in self.to_fetch)


@dataclass(frozen=True, slots=True)
class SourcesFetched:
    """What :meth:`RestoredSources.fetch` put into the copy."""

    manifests: int
    named: int
    fetched: int
    fetched_bytes: int
    suppressed: int


class SnapshotsNotRestored(DomainError):
    """A snapshot named with `--snapshot` has no manifest in the restored copy. Nothing was fetched."""

    def __init__(self, missing: int) -> None:
        self.snapshots_not_restored = missing
        super().__init__(
            f"no source was fetched: {missing} snapshot(s) named have no manifest of a caselist selected "
            "in the restored copy. The directory holds the restored copy without its sources; delete it "
            "before restoring again"
        )


class TooLittleRoomForSources(DomainError):
    """The copy's filesystem cannot hold the sources and the margin. Nothing was fetched."""

    def __init__(self, *, needed_bytes: int, free_bytes: int) -> None:
        self.needed_bytes = needed_bytes
        self.free_bytes = free_bytes
        self.margin_bytes = FREE_SPACE_MARGIN_BYTES
        super().__init__(
            f"no source was fetched: the sources need {needed_bytes} bytes and {FREE_SPACE_MARGIN_BYTES} "
            f"bytes more, and the directory's filesystem has {free_bytes} free. The directory holds the "
            "restored copy without its sources; delete it, make room, and restore again"
        )
        self.hint = "Free space on the disk that holds the directory, or name a directory on another disk."


class RestoredSourcesIncomplete(DomainError):
    """A named source the bucket does not hold, or bytes that are not the digest named. Not complete."""

    def __init__(self, *, named: int, fetched: int, missing: int, mismatched: int, suppressed: int) -> None:
        self.named = named
        self.fetched = fetched
        self.missing = missing
        self.mismatched = mismatched
        self.suppressed = suppressed
        said: list[str] = []
        if missing:
            said.append(f"{missing} named source(s) are not in the bucket and not on the suppression list")
        if mismatched:
            said.append(
                f"{mismatched} fetched source(s) did not hash to the digest their manifest names, and were "
                "deleted"
            )
        super().__init__(
            f"the restored copy's sources are not complete: {'; '.join(said)}. The directory holds the "
            f"restored copy and {fetched} of the {named - suppressed} sources to fetch, and is not a copy "
            "to publish from; delete it"
        )


class RestoredSources:
    """The sources of one restored copy. See the module docstring.

    Args:
        bucket: The bucket the copy was restored from.
        local: The copy's evidence store: its manifests, and the blob tree the sources go into.
        directory: The copy's directory. Nothing is written outside it.
        free_bytes: Free space on the filesystem holding a directory; a test's to override.
    """

    def __init__(
        self,
        *,
        bucket: EvidenceObjectStore,
        local: LocalEvidence,
        directory: Path,
        free_bytes: Callable[[Path], int] | None = None,
    ) -> None:
        self._bucket = bucket
        self._local = local
        self._directory = Path(directory).resolve()
        self._free_bytes = free_bytes or _free_bytes

    async def plan(self, selection: SourceSelection, suppression: SuppressionState) -> SourcesPlan:
        """What the selected manifests of the copy name, and which of it to fetch. Reads, never writes.

        Raises :class:`SnapshotsNotRestored` when a snapshot selected has no manifest selected.
        """
        selected: list[LocalSnapshot] = []
        for info in await self._local.objects.list_objects(f"{MANIFEST_DIRECTORY}/"):
            snapshot = await read_local_manifest(self._local, info)
            if snapshot is not None and selection.selects(snapshot):
                selected.append(snapshot)
        unmatched = set(selection.snapshots) - {snapshot.snapshot for snapshot in selected}
        if unmatched:
            raise SnapshotsNotRestored(len(unmatched))
        named: set[Sha256Hex] = set()
        wanted: dict[Sha256Hex, NamedSource] = {}
        for snapshot in sorted(selected, key=lambda each: (each.caselist, each.snapshot)):
            held_back = held_only_digests(snapshot, suppression)
            for source in snapshot.sources:
                named.add(source.sha256)
                if source.sha256 in wanted or source.sha256 in held_back:
                    continue
                if suppression.suppresses_source(source.sha256):
                    continue
                wanted[source.sha256] = NamedSource(
                    sha256=source.sha256,
                    size=source.size,
                    key=source_key(snapshot.caselist, snapshot.snapshot, source.sha256),
                )
        return SourcesPlan(
            manifests=len(selected),
            named=len(named),
            to_fetch=tuple(sorted(wanted.values())),
            suppressed=len(named) - len(wanted),
        )

    def refuse_too_little_room(self, plan: SourcesPlan) -> None:
        """Raise :class:`TooLittleRoomForSources` when the copy's filesystem cannot hold the plan."""
        free = self._free_bytes(self._directory)
        if free < plan.bytes_to_fetch + FREE_SPACE_MARGIN_BYTES:
            raise TooLittleRoomForSources(needed_bytes=plan.bytes_to_fetch, free_bytes=free)

    async def fetch(self, plan: SourcesPlan) -> SourcesFetched:
        """Fetch every source the plan names into the copy's blob tree, each checked.

        Raises :class:`RestoredSourcesIncomplete` when one is missing or mismatched, and otherwise
        what the bucket raises, once every fetch started has finished.
        """
        path_for = self._local.blob_path_for
        if path_for is None:  # pragma: no cover - the composition root always gives one
            raise ValueError("the restored copy's blob tree names no files")
        limit = asyncio.Semaphore(_PARALLEL_DOWNLOADS)
        counts = {"fetched": 0, "bytes": 0, "missing": 0, "mismatched": 0}
        stopped = False

        async def one(source: NamedSource) -> None:
            nonlocal stopped
            async with limit:
                if stopped:
                    return
                try:
                    outcome = await self._fetch_one(source, path_for(local_blob_key(source.sha256)))
                except BaseException:
                    stopped = True
                    raise
                if outcome == "mismatched":
                    stopped = True
                counts[outcome] += 1
                if outcome == "fetched":
                    counts["bytes"] += source.size

        results = await asyncio.gather(*(one(source) for source in plan.to_fetch), return_exceptions=True)
        failures = [result for result in results if isinstance(result, BaseException)]
        if failures:
            raise failures[0]
        logger.info(
            "restored copy's sources fetched",
            extra={
                "manifests": plan.manifests,
                "named": plan.named,
                "fetched": counts["fetched"],
                "fetched_bytes": counts["bytes"],
                "suppressed": plan.suppressed,
                "missing": counts["missing"],
                "mismatched": counts["mismatched"],
            },
        )
        if counts["missing"] or counts["mismatched"]:
            raise RestoredSourcesIncomplete(
                named=plan.named,
                fetched=counts["fetched"],
                missing=counts["missing"],
                mismatched=counts["mismatched"],
                suppressed=plan.suppressed,
            )
        return SourcesFetched(
            manifests=plan.manifests,
            named=plan.named,
            fetched=counts["fetched"],
            fetched_bytes=counts["bytes"],
            suppressed=plan.suppressed,
        )

    async def _fetch_one(self, source: NamedSource, path: Path) -> str:
        """`fetched`, `missing` or `mismatched`: one source into `path`, by way of a checked landing file."""
        self._refuse_outside(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        landed = path.parent / f"{_LANDING_PREFIX}{secrets.token_hex(8)}"
        try:
            await self._bucket.get_file(source.key, landed)
        except NotFound:
            landed.unlink(missing_ok=True)
            return "missing"
        except StoreAccessDenied:
            landed.unlink(missing_ok=True)
            if not await self._listed(source.key):
                return "missing"
            raise
        except BlobIntegrityError:
            # The bucket's own recorded digest disagreed; the store renamed nothing into place.
            landed.unlink(missing_ok=True)
            return "mismatched"
        except BaseException:
            landed.unlink(missing_ok=True)
            raise
        if _sha256_of(landed) != source.sha256:
            landed.unlink()
            return "mismatched"
        _flush(landed)
        os.replace(landed, path)
        _flush(path.parent)
        return "fetched"

    async def _listed(self, key: ObjectKey) -> bool:
        return any(info.key == key for info in await self._bucket.list_objects(key))

    def _refuse_outside(self, path: Path) -> None:
        if self._directory not in path.resolve().parents:
            raise ValueError("a restored copy's source would be written outside the copy's directory")


def _free_bytes(directory: Path) -> int:
    return shutil.disk_usage(directory).free


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _flush(path: Path) -> None:
    """`fsync` a file or directory so a completed rename survives an unclean shutdown. Best effort.

    Not every filesystem lets a directory be opened for `fsync`; a copy that cannot be made as
    durable is restored again.
    """
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)
