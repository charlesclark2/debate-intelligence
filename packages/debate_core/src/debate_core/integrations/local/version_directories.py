"""The parsed store's version directories on this machine, where retiring one deletes it (`v1-e31-t16`).

The filesystem implementation of
:class:`~debate_core.application.ports.version_directories.VersionDirectoryPlace`, over
`<data_dir>/parsed/<caselist>/<version>/`. :mod:`debate_core.application.caselist.version_retention`
decides what may be retired; this adapter also refuses, on its own account, to delete the newest
directory a caselist has, whatever it was asked, and any name that is not one directory's name.

A directory the operating system will not let this user list or delete stops the run with
:class:`~debate_core.application.errors.LocalStoreAccessDenied`, naming "the parsed card store" and
never the path (`refusals.py`). A refused listing is never taken for an empty one.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Final

from debate_core.application.ports.parsed_store import PARSED_PREFIX, parse_version_directory
from debate_core.application.ports.version_directories import DirectoryContents, RetirementMethod
from debate_core.integrations.local.refusals import (
    directories_in,
    files_under,
    refused_as_access_denied,
    role_of,
)

__all__ = ["LocalVersionDirectories"]

_ROLE: Final = role_of(PARSED_PREFIX)


class LocalVersionDirectories:
    """`<data_dir>/parsed/`, as a place whose superseded version directories are deleted."""

    def __init__(self, data_dir: Path) -> None:
        self._root = Path(data_dir) / PARSED_PREFIX

    @property
    def location(self) -> str:
        return "this machine"

    @property
    def method(self) -> RetirementMethod:
        return RetirementMethod.DELETE

    async def caselists(self) -> tuple[str, ...]:
        with refused_as_access_denied("list", _ROLE):
            return directories_in(self._root)

    async def version_directories(self, caselist: str) -> tuple[str, ...]:
        with refused_as_access_denied("list", _ROLE):
            return directories_in(self._directory(caselist))

    async def contents(self, caselist: str, version: str, *, count_tagged: bool) -> DirectoryContents:
        directory = self._directory(caselist, version)
        with refused_as_access_denied("list", _ROLE):
            sizes = [path.stat().st_size for path in files_under(directory)]
        return DirectoryContents(objects=len(sizes), bytes=sum(sizes), tagged=None)

    async def retire(self, caselist: str, version: str) -> int:
        newest = max(await self.version_directories(caselist), key=parse_version_directory, default=None)
        if version == newest:
            raise ValueError(
                f"{caselist}/{version} is the newest version directory {caselist} has; never deleted"
            )
        return await asyncio.to_thread(self._delete_tree, self._directory(caselist, version))

    async def restore(self, caselist: str, version: str) -> int:
        raise NotImplementedError(
            "a version directory retired on this machine was deleted; nothing to restore"
        )

    # -- helpers ------------------------------------------------------------------------------

    def _directory(self, *names: str) -> Path:
        for name in names:
            if not name or name in {".", ".."} or "/" in name or os.sep in name:
                raise ValueError(f"not a caselist or version directory name: {name!r}")
        return self._root.joinpath(*names)

    def _delete_tree(self, directory: Path) -> int:
        """Delete every file under `directory`, then the directories, deepest first. Counts the files.

        A link is deleted as a link, never followed: `files_under` looks through a link to a file,
        but deleting the link leaves what it names alone.
        """
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError(f"{directory.name} is not a version directory")
        deleted = 0
        with refused_as_access_denied("delete", _ROLE):
            for parent, directories, names in os.walk(directory, topdown=False):
                for name in names:
                    (Path(parent) / name).unlink()
                    deleted += 1
                for name in directories:
                    path = Path(parent) / name
                    if path.is_symlink():
                        path.unlink()
                    else:
                        path.rmdir()
            directory.rmdir()
        return deleted
