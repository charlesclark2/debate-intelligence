"""Getting a streamed download into the importer's inbox whole, or not at all.

The inbox is what the importer (v1-e30-t03) reads, so anything that appears there under its final
name is taken to be a complete file. This module is what makes that true:

1. Bytes are streamed into `<inbox>/.partial/<name>.<random>.part`, on the same filesystem as the
   inbox, while their SHA-256 and their count are taken.
2. The count is checked against the `Content-Length` the server declared (and against a size the
   listing gave, when there is one). A short or long file is a
   :class:`~debate_core.application.ports.caselist_source.DownloadIntegrityError`. An empty file is
   one too.
3. The file is fsynced and then *linked* to its final name, which fails if that name exists — so a
   file already in the inbox is never overwritten. An identical one is reported as already present;
   a different one is a :class:`~debate_core.application.ports.caselist_source.DownloadConflict`,
   and both files are left for the operator.
4. Whatever happens — a network error, a failed check, Ctrl-C, a cancelled task — the partial file
   is removed before the exception leaves this module.

A process killed outright cannot clean up after itself, so each new download first sweeps `.part`
files older than an hour out of `.partial/`. A stray partial is not harmless: an importer that
mistook it for a week's archive would record a truncated window as the archive of record, and
nothing downstream could tell. The scheduled sync (`v1-e34-t02`) skips this directory for the same
reason.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import secrets
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Final

from debate_core.application.ports.caselist_source import (
    DownloadConflict,
    DownloadedFile,
    DownloadIntegrityError,
    UnsafeDownloadName,
)

__all__ = ["PARTIAL_DIRECTORY", "STALE_PARTIAL_SECONDS", "safe_inbox_name", "write_into_inbox"]

PARTIAL_DIRECTORY: Final = ".partial"
"""Where downloads in progress live, inside the inbox. Whatever reads the inbox skips it (v1-e34-t02)."""

STALE_PARTIAL_SECONDS: Final = 3600.0
"""A `.part` file older than this belongs to a process that is gone."""

_CHUNK: Final = 1024 * 1024


def safe_inbox_name(name: str, *, source_name: str) -> str:
    """`name` if it is a plain file name that stays inside the inbox; refused otherwise."""
    if (
        not name
        or name in {".", ".."}
        or name.startswith(".")
        or "/" in name
        or "\\" in name
        or "\x00" in name
        or Path(name).name != name
    ):
        raise UnsafeDownloadName(source_name)
    return name


async def write_into_inbox(
    chunks: AsyncIterator[bytes],
    *,
    inbox: Path,
    name: str,
    source_name: str,
    declared_length: int | None,
    expected_size: int | None = None,
) -> DownloadedFile:
    """Stream `chunks` into `inbox/name` atomically, checked against the declared length."""
    safe_inbox_name(name, source_name=source_name)
    if declared_length is None:
        raise DownloadIntegrityError(
            source_name, "the server declared no Content-Length, so completeness cannot be checked"
        )
    partial_directory = inbox / PARTIAL_DIRECTORY
    partial_directory.mkdir(parents=True, exist_ok=True)
    _sweep_stale_partials(partial_directory)

    destination = inbox / name
    partial = partial_directory / f"{name}.{secrets.token_hex(6)}.part"
    digest = hashlib.sha256()
    received = 0
    try:
        with partial.open("xb") as handle:
            async for chunk in chunks:
                handle.write(chunk)
                digest.update(chunk)
                received += len(chunk)
                if received > declared_length:
                    raise DownloadIntegrityError(
                        source_name, f"more than the declared {declared_length} bytes arrived"
                    )
            handle.flush()
            os.fsync(handle.fileno())

        _check_length(source_name, received, declared_length, expected_size)
        sha256 = digest.hexdigest()
        already_present = _link_into_place(partial, destination, sha256, source_name)
        _fsync_directory(inbox)
        return DownloadedFile(
            path=destination,
            sha256=sha256,
            byte_size=received,
            source_name=source_name,
            already_present=already_present,
        )
    finally:
        # Reached on success too: by then the bytes are linked at `destination` (or were a
        # duplicate), and the partial name is only a second link to discard.
        with contextlib.suppress(FileNotFoundError):
            partial.unlink()


def _check_length(source_name: str, received: int, declared: int, expected: int | None) -> None:
    if received == 0:
        raise DownloadIntegrityError(source_name, "the file arrived empty")
    if received != declared:
        raise DownloadIntegrityError(
            source_name, f"{received} bytes arrived of the {declared} the server declared"
        )
    if expected is not None and received != expected:
        raise DownloadIntegrityError(
            source_name, f"{received} bytes arrived but the listing gave the size as {expected}"
        )


def _link_into_place(partial: Path, destination: Path, sha256: str, source_name: str) -> bool:
    """Give the partial file its final name without ever replacing one. True if it was already there."""
    try:
        os.link(partial, destination)
    except FileExistsError:
        if _sha256_of(destination) == sha256:
            return True
        raise DownloadConflict(source_name, destination) from None
    return False


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(_CHUNK):
            digest.update(block)
    return digest.hexdigest()


def _fsync_directory(directory: Path) -> None:
    """Make the new directory entry durable, so a crash cannot un-rename a finished download."""
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _sweep_stale_partials(partial_directory: Path) -> None:
    cutoff = time.time() - STALE_PARTIAL_SECONDS
    for leftover in partial_directory.glob("*.part"):
        with contextlib.suppress(FileNotFoundError):
            if leftover.stat().st_mtime < cutoff:
                leftover.unlink()
