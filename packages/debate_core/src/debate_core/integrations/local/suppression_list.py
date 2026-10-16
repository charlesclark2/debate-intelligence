"""This machine's copy of the suppression list and the removal log: two append-only JSONL files.

::

    <data_dir>/suppression/suppression-list.jsonl   sha256 values that must never be re-imported
    <data_dir>/suppression/removal-log.jsonl        one line per removal or un-suppress
    <data_dir>/suppression/path-holds.jsonl         the paths whole-file removals hold (`v1-e30-t13`)
    <data_dir>/suppression/removal-scopes.jsonl     what each removal reached (`v1-e30-t15`)
    <data_dir>/suppression/withdrawals.jsonl        the caselist each withdrawn copy left (`v1-e30-t16`)

The last three are neighbours of the first two: a build from before each never opens it, and reads
the list and the log beside it exactly as before (:mod:`debate_core.application.ports.suppression`).

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

## A copy is named by its role

:attr:`LocalAppendOnlyFile.location` is what an error calls this copy, and it is "the local
suppression list under storage.data_dir", not the file's path (`v1-e30-t10`). A data directory is
under the operator's home, and
:class:`~debate_core.application.ports.suppression.UnreadableAppendOnlyRecord` puts the location in
its message and in the `--json` envelope's details. The setting names where to look; the two file
names are at the top of this docstring. :attr:`LocalAppendOnlyFile.path` is still the path, for the
code that opens the file.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from debate_core.application.ports.suppression import (
    PATH_HOLDS_FILENAME,
    AppendOnlyViolation,
    UnreadableAppendOnlyRecord,
)
from debate_core.integrations.local.refusals import refused_as_access_denied, role_of

__all__ = [
    "REMOVAL_LOG_FILENAME",
    "SUPPRESSION_DIRECTORY",
    "SUPPRESSION_FILE_MODE",
    "SUPPRESSION_LIST_FILENAME",
    "LocalAppendOnlyFile",
    "local_path_holds_file",
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

#: What an error calls each copy: what it is and the setting it is under, never its path.
_SUPPRESSION_LIST_ROLE: Final = "the local suppression list under storage.data_dir"
_REMOVAL_LOG_ROLE: Final = "the local removal log under storage.data_dir"
_PATH_HOLDS_CALLED: Final = "path-hold list"


def local_suppression_list_file(data_dir: Path) -> LocalAppendOnlyFile:
    """This environment's copy of the suppression list."""
    return LocalAppendOnlyFile(
        Path(data_dir) / SUPPRESSION_DIRECTORY / SUPPRESSION_LIST_FILENAME, role=_SUPPRESSION_LIST_ROLE
    )


def local_removal_log_file(data_dir: Path) -> LocalAppendOnlyFile:
    """This environment's copy of the removal log."""
    return LocalAppendOnlyFile(
        Path(data_dir) / SUPPRESSION_DIRECTORY / REMOVAL_LOG_FILENAME, role=_REMOVAL_LOG_ROLE
    )


def local_path_holds_file(data_dir: Path) -> LocalAppendOnlyFile:
    """This environment's copy of the path-hold record: the file beside its suppression list."""
    return local_suppression_list_file(data_dir).beside(PATH_HOLDS_FILENAME, called=_PATH_HOLDS_CALLED)


class LocalAppendOnlyFile:
    """An :class:`~debate_core.application.ports.suppression.AppendOnlyRecord` on a local file.

    Args:
        path: The file.
        role: What an error calls this copy. Without one it is called by its file name alone, which
            carries no directory.
    """

    def __init__(self, path: Path, *, role: str | None = None) -> None:
        self._path = Path(path)
        self._named_by_role = role is not None
        self._role = role or f"the local record {self._path.name}"

    def beside(self, filename: str, *, called: str) -> LocalAppendOnlyFile:
        """The file named `filename` in this one's directory, named in messages as this one is.

        A copy named by its role names its neighbour by one: "the local path-hold list under
        storage.data_dir". A copy named by its file name names its neighbour by its file name.
        """
        role = f"the local {called} under storage.data_dir" if self._named_by_role else None
        return LocalAppendOnlyFile(self._path.parent / filename, role=role)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def location(self) -> str:
        """This copy's role, for messages. Never :attr:`path`: see the module docstring."""
        return self._role

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
