"""The filesystem blob store: immutable snapshot bytes under the SHA-256 of their own content.

This is V1's evidence system of record and the local analogue of the S3 store that replaces it in
V2 (`v1-e29-t04-s3-blob-store`). Both build the same key from the same bytes, so a store synced
from a laptop to a bucket is the same store, and a card cut against a blob here re-verifies
against the same blob there.

## Layout

::

    <data_dir>/blobs/sha256/ab/cd/abcd1234…def0

The two-level fan-out repeats the first two byte pairs of the digest, exactly as
`docs/architecture/evidence-store-layout.md` specifies for S3. It is there for everything that
*lists* the store: a single directory holding 60,000 entries is slow to page through and
unreadable in a file browser.

A key is the digest and nothing else — no extension, no filename, no team or school name. The
original filename and content type belong on the `SourceSnapshot` record, never in a key, because
a key is quoted in logs and error messages (`docs/policies/caselist-data-use.md`).

## The three properties content addressing has to keep

**Deduplication.** Identical bytes produce one key and therefore one file, whether they arrive
once or a hundred times.

**Idempotent writes.** :meth:`FsSnapshotStore.put` of bytes already stored writes nothing and
returns the same key. It does not rewrite the file, and the stored file is created read-only
(:data:`BLOB_FILE_MODE`), so "immutable once written" is something the filesystem enforces rather
than something this module promises.

**Detectable corruption.** :meth:`FsSnapshotStore.get` re-hashes what it read and raises
:class:`~debate_core.application.errors.BlobIntegrityError` when the bytes no longer hash to the
key they are filed under. It never repairs and never returns the bytes anyway: a card "verified"
against silently altered text is the one failure this platform exists to prevent (architecture
proposal §8).

## Writes are atomic

A blob is written to a temporary file in its final directory, flushed, `fsync`-ed, made read-only
and then `os.replace`-d into place; the containing directory is `fsync`-ed afterwards so the
rename survives a power loss. A reader therefore sees either no file or the whole file, never a
half-written one. An interrupted write leaves a `.incoming-*.tmp` file and no blob, which is the
correct outcome: the snapshot is simply not stored, and the retrieval is repeated.

There is no `delete` and no overwrite, because :class:`~debate_core.application.ports.persistence.
SnapshotStore` has neither. Removing a source under `docs/runbooks/caselist-removal.md` is an
operator procedure against this directory, not something a use case can reach.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path

from debate_core.application.errors import BlobIntegrityError, NotFound
from debate_core.domain import SHA256_HEX_PATTERN, Sha256Hex

__all__ = [
    "BLOB_DIRECTORY",
    "BLOB_FILE_MODE",
    "TEMPORARY_FILE_PREFIX",
    "FsSnapshotStore",
]

BLOB_DIRECTORY = Path("blobs") / "sha256"
"""Where blobs live inside the data directory, mirroring the S3 store's `…/sha256/` segment."""

BLOB_FILE_MODE = 0o444
"""Mode a stored blob is created with: readable by its owner and no one may write it.

Immutability is the point. A blob whose bytes change is a blob that fails its integrity check, so
making the file read-only turns "must not be rewritten" from a rule in a docstring into a rule the
operating system applies. Deleting is unaffected — that depends on the directory's mode — which is
what keeps the removal runbook workable.
"""

TEMPORARY_FILE_PREFIX = ".incoming-"
"""Prefix of the temp file a write goes to before it is renamed into place.

Leading dot and a distinctive word so that a leftover from an interrupted write is recognisable,
and so that anything walking the store can skip partial writes without guessing.
"""

#: What a blob key must look like. Also the traversal guard — see :meth:`FsSnapshotStore.path_for`.
_BLOB_KEY_PATTERN = re.compile(SHA256_HEX_PATTERN)

#: The name `NotFound` and `BlobIntegrityError` report, matching the in-memory store's wording.
_ENTITY = "snapshot blob"


class FsSnapshotStore:
    """A :class:`~debate_core.application.ports.persistence.SnapshotStore` on the local filesystem.

    Takes the data directory as a constructor argument and derives every path from it, so one
    environment is one directory and nothing escapes it. It does not read settings; the composition
    root passes `settings.storage.data_dir` (v1-e02-t05-settings-config).

    The directory is created lazily, on the first :meth:`put`, so constructing a store — which the
    CLI does on every command — never creates a tree for an environment that is only being
    inspected.
    """

    def __init__(self, data_dir: Path) -> None:
        self._root = Path(data_dir) / BLOB_DIRECTORY

    @property
    def root(self) -> Path:
        """The directory blobs are stored under: `<data_dir>/blobs/sha256`."""
        return self._root

    def path_for(self, key: Sha256Hex) -> Path:
        """Return the path the blob with this key is (or would be) stored at.

        Public because an operator procedure and a test both need to name a blob's file — the
        removal runbook deletes one, and this task's tests corrupt one to prove the integrity check
        fires. It is not part of the port: no use case may reach a blob by path.

        Raises :class:`ValueError` when `key` is not 64 lowercase hex characters. That check is
        also the traversal guard: a key can never contain `/` or `..`, so no key can name a file
        outside the store.
        """
        if _BLOB_KEY_PATTERN.match(key) is None:
            raise ValueError(f"not a blob key (expected 64 lowercase hex characters): {key!r}")
        return self._root / key[0:2] / key[2:4] / key

    async def put(self, data: bytes) -> Sha256Hex:
        """Store `data` under the SHA-256 of its own bytes and return that key.

        Storing bytes that are already stored is a no-op: the existing file is left exactly as it
        is, and its key is returned.
        """
        key = hashlib.sha256(data).hexdigest()
        destination = self.path_for(key)
        if destination.exists():
            return key
        destination.parent.mkdir(parents=True, exist_ok=True)
        _write_atomically(destination, data)
        return key

    async def get(self, key: Sha256Hex) -> bytes:
        """Return the bytes stored under `key`, after checking they still hash to it.

        Raises :class:`~debate_core.application.errors.NotFound` when nothing is stored under the
        key — including when `key` is not a digest at all, because such a key can never have been
        minted by :meth:`put` — and
        :class:`~debate_core.application.errors.BlobIntegrityError` when the stored bytes have
        changed.
        """
        try:
            path = self.path_for(key)
        except ValueError as malformed:
            raise NotFound(_ENTITY, key) from malformed
        try:
            data = path.read_bytes()
        except FileNotFoundError as missing:
            raise NotFound(_ENTITY, key) from missing
        actual = hashlib.sha256(data).hexdigest()
        if actual != key:
            raise BlobIntegrityError(key, actual)
        return data

    async def exists(self, key: Sha256Hex) -> bool:
        """True when a blob is filed under `key`. Does not read or verify it."""
        try:
            path = self.path_for(key)
        except ValueError:
            return False
        return path.is_file()


def _write_atomically(destination: Path, data: bytes) -> None:
    """Write `data` to a temp file beside `destination` and rename it into place.

    The temp file is created in the destination's own directory so that the rename is within one
    filesystem, which is what makes it atomic. Everything is flushed to disk before the rename and
    the directory is flushed after it, so a blob that exists is a blob that is complete.
    """
    handle, temporary_name = tempfile.mkstemp(
        dir=destination.parent, prefix=TEMPORARY_FILE_PREFIX, suffix=".tmp"
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.chmod(BLOB_FILE_MODE)
        os.replace(temporary_path, destination)
    except BaseException:
        # An interrupted write leaves nothing behind but is never half a blob.
        temporary_path.unlink(missing_ok=True)
        raise
    _sync_directory(destination.parent)


def _sync_directory(directory: Path) -> None:
    """Flush a directory entry so a completed rename survives a power loss.

    Best effort: not every filesystem lets a directory be opened for `fsync`, and a store that
    cannot do it is still correct — it is only less durable across an unclean shutdown.
    """
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)
