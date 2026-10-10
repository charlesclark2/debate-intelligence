"""This machine's copy of the suppression list and the removal log: two append-only JSONL files.

::

    <data_dir>/suppression/suppression-list.jsonl   sha256 values that must never be re-imported
    <data_dir>/suppression/removal-log.jsonl        one line per removal or un-suppress

A sibling of `objects/` and `blobs/`, not a file inside either, for the same reason the sync
journal is (`debate_core.application.evidence_sync.JOURNAL_DIRECTORY`): `store sync` moves what is
under those two trees, and a sync that overwrote the bucket's list with this machine's would be a
rewrite of an append-only record. The bucket's copy is `manifests/_suppression/`, which `store
sync` refuses to touch in either direction, and the two copies are merged by the commands that
hold both (:mod:`debate_core.application.caselist.suppression`).

## Append-only, enforced by how the file is opened

:class:`LocalAppendOnlyFile` opens its file with `O_APPEND` and never with anything that can
truncate or seek: every write lands after the last byte, whatever else has the file open. One
append is one `write` of whole lines followed by an `fsync`, so an append is either there or not;
a crash in the middle of one leaves an unfinished last line, which the next read refuses rather
than repairs (:class:`~debate_core.application.ports.suppression.UnreadableAppendOnlyRecord`).
Nothing in this module can remove a line, and nothing else in the platform writes these files.

Reading a list that does not exist yet is an empty list, and creates nothing: `caselist import`
reads it on every run and must leave no new directory behind in an environment that has never had
a removal.

A suppression directory the operating system refuses is
:class:`~debate_core.application.errors.LocalStoreAccessDenied` naming "the suppression directory",
never a raw `PermissionError` and never the file's path
(:mod:`debate_core.integrations.local.refusals`, `v1-e34-t13`). A list that cannot be read is not an
empty one: nothing may be imported or published against it.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from debate_core.application.ports.suppression import AppendOnlyViolation, UnreadableAppendOnlyRecord
from debate_core.integrations.local.refusals import refused_as_access_denied, role_of

__all__ = [
    "REMOVAL_LOG_FILENAME",
    "SUPPRESSION_DIRECTORY",
    "SUPPRESSION_FILE_MODE",
    "SUPPRESSION_LIST_FILENAME",
    "LocalAppendOnlyFile",
    "local_removal_log_file",
    "local_suppression_list_file",
]

SUPPRESSION_DIRECTORY: Final = Path("suppression")
SUPPRESSION_LIST_FILENAME: Final = "suppression-list.jsonl"
REMOVAL_LOG_FILENAME: Final = "removal-log.jsonl"

SUPPRESSION_FILE_MODE: Final = 0o600
"""Owner read and write. The list names no one, but it is the operator's record and nobody else's."""

_APPEND_FLAGS: Final = os.O_WRONLY | os.O_APPEND | os.O_CREAT

#: What a refusal names instead of the file's path.
_ROLE: Final = role_of(SUPPRESSION_DIRECTORY.name)


def local_suppression_list_file(data_dir: Path) -> LocalAppendOnlyFile:
    """This environment's copy of the suppression list."""
    return LocalAppendOnlyFile(Path(data_dir) / SUPPRESSION_DIRECTORY / SUPPRESSION_LIST_FILENAME)


def local_removal_log_file(data_dir: Path) -> LocalAppendOnlyFile:
    """This environment's copy of the removal log."""
    return LocalAppendOnlyFile(Path(data_dir) / SUPPRESSION_DIRECTORY / REMOVAL_LOG_FILENAME)


class LocalAppendOnlyFile:
    """An :class:`~debate_core.application.ports.suppression.AppendOnlyRecord` on a local file."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def location(self) -> str:
        return str(self._path)

    async def read_lines(self) -> tuple[str, ...]:
        with refused_as_access_denied("read", _ROLE):
            if not self._path.is_file():
                return ()
            data = self._path.read_bytes()
        if not data:
            return ()
        if not data.endswith(b"\n"):
            raise UnreadableAppendOnlyRecord(
                self.location, data.count(b"\n") + 1, "the last line has no newline (a write was interrupted)"
            )
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise UnreadableAppendOnlyRecord(self.location, 0, "not UTF-8") from None
        return tuple(text.split("\n")[:-1])

    async def append_lines(self, lines: Sequence[str]) -> None:
        if not lines:
            return
        for line in lines:
            if "\n" in line or "\r" in line:
                raise AppendOnlyViolation(self.location, "a line to append contains a line break")
        await self.read_lines()  # refuses a torn last line before anything is added after it
        payload = "".join(f"{line}\n" for line in lines).encode("utf-8")
        with refused_as_access_denied("write", _ROLE):
            created = not self._path.exists()
            self._path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(self._path, _APPEND_FLAGS, SUPPRESSION_FILE_MODE)
            try:
                written = 0
                while written < len(payload):
                    written += os.write(descriptor, payload[written:])
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            if created:
                _sync_directory(self._path.parent)


def _sync_directory(directory: Path) -> None:
    """Flush the directory entry of a newly created file. Best effort, as in the blob store."""
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
