"""Named evidence objects in a local directory: the other side of every sync.

The filesystem implementation of
:class:`~debate_core.application.ports.evidence_store.EvidenceObjectStore`, and the reason that port
has two: `v1-e29-t05-evidence-sync-cli` moves manifests and reports between *this* store and
:class:`~debate_core.integrations.s3.S3EvidenceObjectStore` by diffing two of the same thing. Without a
local implementation the sync would be a bucket on one side and a pile of `os.walk` on the other, and
half its rules would have nowhere to live.

## Layout

An object's key is its path under the store's root, with `/` meaning `/`:

::

    <evidence_dir>/manifests/hsld26/2026-09-15.jsonl   <- key "manifests/hsld26/2026-09-15.jsonl"
    <evidence_dir>/reports/sync/2026-09-15T06-00Z.json <- key "reports/sync/2026-09-15T06-00Z.json"

Identical to the key in the bucket, so the two stores can be compared key for key. That is also why
this store is separate from :class:`~debate_core.integrations.local.FsSnapshotStore`, which puts its
content-addressed blobs under `blobs/sha256/…` and answers a different port: one directory holds both,
and neither reaches into the other's keys.

## Digests are computed, never stored

There is no metadata on a file, so `head` hashes the file to answer. A local store is on a local disk
and a manifest is measured in megabytes, so that is the right trade — but it is why a listing states
no digests (the port's rule, and here it is not a cheap answer for 60,000 files), and why nothing here
records a digest anywhere: a sidecar file holding one would be a second thing that can be wrong about
the first.

The consequence for :meth:`FsEvidenceObjectStore.get_file` is that the digest it verifies against is
the one it just computed from the source file, which means a local-to-local copy detects a disk that
changed the bytes in between and nothing else. That is all this side can honestly claim; the
verification that matters for a sync is on the S3 side, where a digest recorded at upload is compared
with what arrived.

## Containment

Every key goes through :func:`~debate_core.application.ports.evidence_store.validate_object_key`
before it becomes a path, so no key can contain `..` or a leading `/`, and the resolved path is checked
against the root as well — belt and braces, because the cost of being wrong here is writing outside the
evidence directory. Symlinks are not followed out of the store: a resolved path that leaves the root is
refused.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from debate_core.application.errors import BlobIntegrityError, NotFound
from debate_core.application.ports.evidence_store import (
    ObjectInfo,
    ObjectKey,
    validate_object_key,
)
from debate_core.integrations.file_streaming import (
    INCOMING_FILE_PREFIX,
    atomic_replacement,
    sha256_of_file,
)

__all__ = ["OBJECT_DIRECTORY", "FsEvidenceObjectStore"]

OBJECT_DIRECTORY = Path("objects")
"""Where named objects live inside the data directory: `<data_dir>/objects/<key>`.

One level of separation from `blobs/`, so that a key like `manifests/hsld26/2026-09-15.jsonl` can
never collide with the content-addressed tree, and so that "everything that syncs to the bucket by
name" is one directory an operator can point at.
"""

#: The name `NotFound` reports, matching the S3 implementation's wording.
_ENTITY = "evidence object"


class FsEvidenceObjectStore:
    """An :class:`~debate_core.application.ports.evidence_store.EvidenceObjectStore` on local disk.

    Takes the data directory and derives every path from it, like every other adapter in
    :mod:`debate_core.integrations.local`: one environment is one directory, and it reads no settings.
    The directory is created lazily, on the first write, so constructing a store — which a CLI command
    does whether or not it writes anything — never creates a tree for an environment that is only
    being inspected.

    Args:
        data_dir: The environment's data directory. Objects go under `<data_dir>/objects/`.
    """

    def __init__(self, data_dir: Path) -> None:
        self._root = Path(data_dir) / OBJECT_DIRECTORY

    @property
    def root(self) -> Path:
        """The directory named objects are stored under: `<data_dir>/objects`."""
        return self._root

    def path_for(self, key: ObjectKey) -> Path:
        """Return the path the object with this key is (or would be) stored at.

        Public because an operator procedure and a test both need to name an object's file. It is not
        part of the port: no use case may reach an object by path.

        Raises :class:`ValueError` when `key` is not a usable object key, or when the path it resolves
        to is outside the store — which a validated key cannot produce on its own, but a symlinked
        directory inside the store can.

        The second check is why this does not simply join the key onto the root. `Path.resolve` follows
        every symlink in the path and leaves the parts that do not exist yet as they are, so a
        `manifests/` inside the store that points somewhere else entirely resolves out of the root and
        is caught here — before a manifest is written through it to a directory nobody meant to touch.
        """
        candidate = self._root / validate_object_key(key)
        if not candidate.resolve().is_relative_to(self._root.resolve()):
            raise ValueError(f"evidence object key resolves outside the store: {key!r}")
        return candidate

    async def list_objects(self, prefix: str) -> tuple[ObjectInfo, ...]:
        """Every object whose key starts with `prefix`, sorted by key, with no digests.

        `prefix` is matched against the key as a string, exactly as S3 matches it, so `manifests/hs`
        finds `manifests/hsld26/…`. Temporary files from an interrupted download
        (:data:`~debate_core.integrations.file_streaming.INCOMING_FILE_PREFIX`) are skipped: they are
        not objects, and a sync that treated one as an object would try to upload half a file.

        Directories are not entries — only files are — and a store whose root does not exist yet lists
        nothing rather than failing.
        """
        if not self._root.is_dir():
            return ()
        found: list[ObjectInfo] = []
        for path in self._root.rglob("*"):
            if not path.is_file() or path.name.startswith(INCOMING_FILE_PREFIX):
                continue
            key = path.relative_to(self._root).as_posix()
            if key.startswith(prefix):
                found.append(ObjectInfo(key=key, size=path.stat().st_size))
        return tuple(sorted(found, key=lambda info: info.key))

    async def head(self, key: ObjectKey) -> ObjectInfo:
        """The object's size and the digest of its current contents, which this store computes."""
        path = self.path_for(key)
        if not path.is_file():
            raise NotFound(_ENTITY, key)
        return ObjectInfo(key=key, size=path.stat().st_size, sha256=sha256_of_file(path))

    async def put_file(self, key: ObjectKey, source: Path) -> ObjectInfo:
        """Copy `source` to `key`, atomically, and return the stored object.

        The copy goes to a temporary file in the destination's directory and is renamed into place, so
        a reader — including a sync running at the same time — sees the whole object or the previous
        one. Raises :class:`FileNotFoundError` when `source` does not exist.
        """
        digest = sha256_of_file(source)
        destination = self.path_for(key)
        with atomic_replacement(destination) as incoming:
            shutil.copyfile(source, incoming)
        return ObjectInfo(key=key, size=destination.stat().st_size, sha256=digest)

    async def get_file(self, key: ObjectKey, destination: Path) -> ObjectInfo:
        """Copy the object at `key` to `destination`, atomically, and return what landed there.

        Raises :class:`~debate_core.application.errors.NotFound` when there is no such object, and
        :class:`~debate_core.application.errors.BlobIntegrityError` when the bytes that landed do not
        hash to what the source file hashed to a moment earlier — which on one disk means the file
        changed underneath the copy. Nothing is renamed into place when that happens.
        """
        source = self.path_for(key)
        if not source.is_file():
            raise NotFound(_ENTITY, key)
        expected = sha256_of_file(source)
        with atomic_replacement(destination) as incoming:
            shutil.copyfile(source, incoming)
            landed = sha256_of_file(incoming)
            if landed != expected:
                raise BlobIntegrityError(key, landed)
            size = incoming.stat().st_size
        return ObjectInfo(key=key, size=size, sha256=landed)
