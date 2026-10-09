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
from collections.abc import AsyncGenerator, Callable, Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from debate_core.application.caselist.import_service import FullArchiveBaseline
from debate_core.application.caselist.manifest import MANIFEST_DIRECTORY
from debate_core.application.caselist.publish_plan import (
    InvalidPublishTarget,
    LocalSnapshot,
    digest_of_local_blob_key,
    full_archive_date,
    manifest_prefix,
    remote_source_prefix,
    snapshot_of_manifest_key,
    sources_in_manifest,
    stored_rows_in_manifest,
    validate_publish_target,
)
from debate_core.application.caselist.withdrawals import EarlierSnapshots
from debate_core.application.ports.evidence_store import EvidenceObjectStore, ObjectKey
from debate_core.domain import Sha256Hex

__all__ = [
    "LocalEvidence",
    "digests_in_earlier_manifests",
    "list_local_caselists",
    "list_remote_caselists",
    "list_remote_evidence",
    "local_blob_sizes",
    "local_file",
    "read_local_snapshots",
    "snapshots_before_full_archive",
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
    local: LocalEvidence, caselist: str, snapshot: str | None = None, *, full_archives: bool = False
) -> tuple[LocalSnapshot, ...]:
    """Every snapshot of `caselist` this machine holds a manifest for, in snapshot order.

    With `snapshot`, only that one — or nothing, when there is no manifest for it; the caller
    decides whether that is an error.

    The weekly series alone unless `full_archives` is set, or `snapshot` names a complete archive
    (`full/<date>`, `v1-e34-t04`): see
    :func:`~debate_core.application.caselist.publish_plan.snapshot_of_manifest_key`. A complete
    archive sorts after every weekly, since `full/` sorts after a date.
    """
    validate_publish_target(caselist, snapshot)
    with_full = full_archives or (snapshot is not None and full_archive_date(snapshot) is not None)
    found: list[LocalSnapshot] = []
    for info in await local.objects.list_objects(manifest_prefix(caselist)):
        named = snapshot_of_manifest_key(caselist, info.key, full_archives=with_full)
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
                stored_rows=stored_rows_in_manifest(lines),
            )
        )
    return tuple(sorted(found, key=lambda local_snapshot: local_snapshot.snapshot))


async def digests_in_earlier_manifests(
    local: LocalEvidence, caselist: str, snapshot: date
) -> frozenset[Sha256Hex]:
    """Every digest a stored row names in `caselist`'s manifests for snapshots strictly before `snapshot`.

    What a weekly import's first-seen count is measured against (`v1-e30-t08`): a digest is first
    seen in a snapshot when no earlier snapshot *of the same caselist* held it. Read from this
    caselist's manifests and nothing else — not the blob store, which also holds every other
    caselist's files and every camp file, so a digest it holds may still be new to this caselist.
    Strictly before, as the importer's previous snapshot is, so re-importing a week reports the same
    count. Raises :class:`~debate_core.application.caselist.publish_plan.UnreadableManifest` for a
    manifest it cannot read rather than counting around it.

    **The weekly series only** (PM decision, `v1-e34-t04`). First-seen means new evidence over
    time, which is what the weeklies record; a complete archive is the whole caselist at once, so
    counting it as "earlier" would make every weekly after it report almost nothing first seen. A
    complete archive's manifest (`manifests/<slug>/full/<date>.jsonl`) is never read here. What a
    complete archive is measured for is the opposite question, what is no longer there: its
    withdrawn and superseded counts
    (:func:`~debate_core.application.caselist.withdrawals.count_withdrawals`), which read every
    earlier snapshot, weekly and complete alike.
    """
    before = snapshot.isoformat()
    return frozenset(
        source.sha256
        for held in await read_local_snapshots(local, caselist, full_archives=False)
        if held.snapshot < before
        for source in held.sources
    )


async def snapshots_before_full_archive(
    local: LocalEvidence, caselist: str, archive_date: date
) -> tuple[FullArchiveBaseline | None, EarlierSnapshots]:
    """What a complete archive of `archive_date` is measured against, read from this machine's manifests.

    The baseline is the newest complete archive dated before it, which it is classified against,
    or `None` for the first. The earlier snapshots are every snapshot of `caselist` dated before it,
    **weekly and complete alike**, which its withdrawals are counted against (`v1-e34-t04`): a
    disclosure that a weekly carried and the complete archive does not is exactly a withdrawal.
    Strictly before, as every baseline here is, so importing the same archive again counts the same.
    """
    previous: LocalSnapshot | None = None
    previous_date: date | None = None
    rows: list[tuple[str, str]] = []
    count = 0
    for held in await read_local_snapshots(local, caselist, full_archives=True):
        full = full_archive_date(held.snapshot)
        held_date = full if full is not None else date.fromisoformat(held.snapshot)
        if held_date >= archive_date:
            continue
        count += 1
        rows.extend(held.stored_rows)
        if full is not None and (previous_date is None or full > previous_date):
            previous, previous_date = held, full
    baseline = (
        FullArchiveBaseline(
            snapshot=previous_date, paths={path: digest for digest, path in previous.stored_rows}
        )
        if previous is not None and previous_date is not None
        else None
    )
    return baseline, EarlierSnapshots(rows=tuple(rows), count=count)


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

    A complete archive's `manifests/<caselist>/full/<date>.jsonl` names its caselist too, so a
    caselist this store knows only from a complete archive is still listed (`v1-e34-t04`).
    Anything else under `manifests/` — t07's `_suppression/` directory, a stray file — is not a
    caselist and is left out rather than refused.
    """
    found: set[str] = set()
    for key in keys:
        parts = key.split("/")
        if len(parts) not in (3, 4):
            continue
        try:
            if snapshot_of_manifest_key(parts[1], key, full_archives=True) is not None:
                found.add(parts[1])
        except InvalidPublishTarget:
            continue
    return tuple(sorted(found))


@asynccontextmanager
async def local_file(
    store: EvidenceObjectStore, path_for: Callable[[ObjectKey], Path] | None, key: ObjectKey
) -> AsyncGenerator[Path]:
    """The file holding one local object: the store's own, or a staged copy that is cleaned up."""
    if path_for is not None:
        yield path_for(key)
        return
    with tempfile.TemporaryDirectory(prefix="debate-publish-") as directory:
        staged = Path(directory) / "object"
        await store.get_file(key, staged)
        yield staged
