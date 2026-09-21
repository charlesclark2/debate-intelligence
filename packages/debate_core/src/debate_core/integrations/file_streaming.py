"""Reading and replacing files without ever holding one whole in memory.

Two operations, wanted by every adapter that moves evidence *files* rather than small blobs — the S3
snapshot store, and both :class:`~debate_core.application.ports.evidence_store.EvidenceObjectStore`
implementations:

* :func:`sha256_of_file` — the digest of a file, read in chunks. A camp archive is measured in
  gigabytes, and `path.read_bytes()` on one is how a sync run gets killed by the kernel.
* :func:`atomic_replacement` — write a file by writing a temporary one beside it and renaming.

They live beside the adapter packages rather than inside one because both `integrations.local` and
`integrations.s3` need them and neither should have to import the other. Nothing here knows about
S3, and nothing here is a port: these are filesystem mechanics.

## Why a download is always a rename

A reader must see either the whole object or no file at all. If a download wrote straight to its
destination, an interrupted sync would leave a truncated file with a plausible name, and the next
run — which decides what to transfer by comparing digests — would have to be careful never to trust
it. Renaming into place makes that situation unrepresentable instead of something later code has to
remember: the temporary file is the only thing that can be half-written, and it is deleted.

The rename is `os.replace`, which is atomic within one filesystem, and the temporary file is created
in the destination's own directory so that the rename never crosses one. The file and then its
directory are flushed, so an object that exists after a power loss is an object that is complete —
the same guarantee, and for the same reasons, as
:class:`~debate_core.integrations.local.FsSnapshotStore`'s blob writes.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

__all__ = [
    "INCOMING_FILE_PREFIX",
    "READ_CHUNK_BYTES",
    "atomic_replacement",
    "sha256_of_file",
]

READ_CHUNK_BYTES = 1024 * 1024
"""How much of a file is read at a time: 1 MiB.

Large enough that hashing a gigabyte is a thousand reads rather than a million, small enough that a
worker thread's memory does not move with the size of the file it happens to be handling.
"""

INCOMING_FILE_PREFIX = ".incoming-"
"""Prefix of the temporary file a download is written to before it is renamed into place.

The same prefix :class:`~debate_core.integrations.local.FsSnapshotStore` uses, and for the same
reason: a leading dot and a distinctive word make a leftover from an interrupted transfer
recognisable, so that anything walking the store can skip partial writes instead of guessing at
them.
"""


def sha256_of_file(path: Path) -> str:
    """Return the lowercase hex SHA-256 of the file's contents, reading it in chunks.

    Raises :class:`FileNotFoundError` if there is no such file: a caller that named a local file
    which is not there has a bug, and no store condition is involved.
    """
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(READ_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


@contextmanager
def atomic_replacement(destination: Path) -> Generator[Path, None, None]:
    """Yield a temporary path to write, and rename it onto `destination` when the block succeeds.

    Used like this, so that what lands at `destination` is either the previous file or the whole new
    one, and never a partial download::

        with atomic_replacement(destination) as incoming:
            client.download_file(bucket, key, str(incoming))
            verify(incoming)          # raising here leaves `destination` untouched

    Missing parent directories of `destination` are created. If the block raises — a failed transfer,
    a digest that did not match — the temporary file is deleted and nothing is renamed, so the
    exception reaches the caller with the store and the destination exactly as they were.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        dir=destination.parent, prefix=INCOMING_FILE_PREFIX, suffix=".tmp"
    )
    os.close(handle)  # the caller opens it by name: a downloader wants the path, not a descriptor.
    incoming = Path(temporary_name)
    try:
        yield incoming
        _flush(incoming)
        os.replace(incoming, destination)
    except BaseException:
        incoming.unlink(missing_ok=True)
        raise
    _flush(destination.parent)


def _flush(path: Path) -> None:
    """`fsync` a file or directory so a completed rename survives an unclean shutdown.

    Best effort. Not every filesystem lets a directory be opened for `fsync`, and a store that cannot
    do it is still correct — only less durable across a power loss, which is a risk an operator can
    answer by running the sync again.
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
