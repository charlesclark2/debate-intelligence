"""Reading the two sides of a publish: this machine's evidence store, and the bucket.

:mod:`~debate_core.application.caselist.publish_service` and
:mod:`~debate_core.application.caselist.status_service` ask the same three questions before they
do anything — which snapshots does this machine hold, which blobs, and what does the bucket list
under this caselist — and this module answers them once, through the
:class:`~debate_core.application.ports.evidence_store.EvidenceObjectStore` port only.

The local store is two trees, the same two `store sync` works with (`debate_core.
application.evidence_sync`): named objects under `<data_dir>/objects/`, where manifests live, and
content-addressed blobs under `<data_dir>/blobs/`, keyed `sha256/ab/cd/<digest>`. The blob tree is
shared by every caselist on the machine. That is why publishing selects blobs *by manifest* rather
than by walking the tree: a blob's key does not say which caselist it came from, and only a
snapshot's manifest can say which blobs are that snapshot's.
"""

from __future__ import annotations

import tempfile
from collections.abc import AsyncIterator, Callable, Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from debate_core.application.caselist.manifest import MANIFEST_DIRECTORY
from debate_core.application.caselist.publish_plan import (
    InvalidPublishTarget,
    LocalSnapshot,
    digest_of_local_blob_key,
    manifest_prefix,
    remote_source_prefix,
    snapshot_of_manifest_key,
    sources_in_manifest,
    validate_publish_target,
)
from debate_core.application.ports.evidence_store import EvidenceObjectStore, ObjectKey
from debate_core.domain import Sha256Hex

__all__ = [
    "LocalEvidence",
    "list_local_caselists",
    "list_remote_caselists",
    "list_remote_evidence",
    "local_blob_sizes",
    "local_file",
    "read_local_snapshots",
]

@dataclass(frozen=True, slots=True)
class LocalEvidence:
    """This machine's evidence store, as the two trees a publish reads from.

    Args:
        objects: Named objects, keyed as in the bucket: `manifests/hsld26/2026-09-15.jsonl`.
        blobs: Content-addressed blobs, keyed `sha256/ab/cd/<digest>`.
        object_path_for: Optional. The file a named object is stored at, so a manifest is read and
            uploaded in place. The filesystem store's `path_for` is what this is.
        blob_path_for: Optional. The same for a blob.

    A store that cannot name a file for a key leaves the path function `None`, and the object is
    staged through a temporary file instead — the same arrangement `store sync` has, for the same
    reason: the port is what the services depend on, not the filesystem adapter.
    """

    objects: EvidenceObjectStore
    blobs: EvidenceObjectStore
    object_path_for: Callable[[ObjectKey], Path] | None = None
    blob_path_for: Callable[[ObjectKey], Path] | None = None


async def read_local_snapshots(
    local: LocalEvidence, caselist: str, snapshot: str | None = None
) -> tuple[LocalSnapshot, ...]:
    """Every snapshot of `caselist` this machine holds a manifest for, in snapshot order.

    With `snapshot`, only that one — or nothing, when there is no manifest for it; the caller
    decides whether that is an error.
    """
    validate_publish_target(caselist, snapshot)
    found: list[LocalSnapshot] = []
    for info in await local.objects.list_objects(manifest_prefix(caselist)):
        named = snapshot_of_manifest_key(caselist, info.key)
        if named is None or (snapshot is not None and named != snapshot):
            continue
        async with local_file(local.objects, local.object_path_for, info.key) as path:
            lines = path.read_text(encoding="utf-8").splitlines()
        found.append(
            LocalSnapshot(
                caselist=caselist,
                snapshot=named,
                sources=sources_in_manifest(info.key, lines),
                manifest_size=info.size,
            )
        )
    return tuple(sorted(found, key=lambda local_snapshot: local_snapshot.snapshot))


async def local_blob_sizes(local: LocalEvidence) -> dict[Sha256Hex, int]:
    """Every blob the local store holds, digest to size. Other files in the tree are ignored."""
    sizes: dict[Sha256Hex, int] = {}
    for info in await local.blobs.list_objects(""):
        digest = digest_of_local_blob_key(info.key)
        if digest is not None:
            sizes[digest] = info.size
    return sizes


async def list_remote_evidence(remote: EvidenceObjectStore, caselist: str) -> dict[ObjectKey, int]:
    """What the bucket holds for `caselist`: its sources and its manifests, key to size.

    Two listings, each under a documented prefix (`raw/`, `manifests/`), because the operator's
    `ListBucket` grant is scoped prefix by prefix and the bucket root is not listable
    (`debate_core.application.evidence_sync.EVIDENCE_PREFIXES`).
    """
    listed: dict[ObjectKey, int] = {}
    for prefix in (remote_source_prefix(caselist), manifest_prefix(caselist)):
        for info in await remote.list_objects(prefix):
            listed[info.key] = info.size
    return listed


async def list_local_caselists(local: LocalEvidence) -> tuple[str, ...]:
    """Every caselist this machine holds at least one manifest for, sorted."""
    return _caselists_in(info.key for info in await local.objects.list_objects(f"{MANIFEST_DIRECTORY}/"))


async def list_remote_caselists(remote: EvidenceObjectStore) -> tuple[str, ...]:
    """Every caselist the bucket holds at least one manifest for, sorted."""
    return _caselists_in(info.key for info in await remote.list_objects(f"{MANIFEST_DIRECTORY}/"))


def _caselists_in(keys: Iterable[ObjectKey]) -> tuple[str, ...]:
    """The caselists named by `manifests/<caselist>/<snapshot>.jsonl` keys among `keys`.

    Anything else under `manifests/` — t07's `_suppression/` directory, a stray file — is not a
    caselist and is left out rather than refused.
    """
    found: set[str] = set()
    for key in keys:
        parts = key.split("/")
        if len(parts) != 3:
            continue
        try:
            if snapshot_of_manifest_key(parts[1], key) is not None:
                found.add(parts[1])
        except InvalidPublishTarget:
            continue
    return tuple(sorted(found))


@asynccontextmanager
async def local_file(
    store: EvidenceObjectStore, path_for: Callable[[ObjectKey], Path] | None, key: ObjectKey
) -> AsyncIterator[Path]:
    """The file holding one local object: the store's own, or a staged copy that is cleaned up."""
    if path_for is not None:
        yield path_for(key)
        return
    with tempfile.TemporaryDirectory(prefix="debate-publish-") as directory:
        staged = Path(directory) / "object"
        await store.get_file(key, staged)
        yield staged
