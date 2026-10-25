"""The run-state bundle's files in this machine's data directory (`v1-e40-t04`, ADR-0020 (3)).

:class:`~debate_core.application.ports.run_state.RunStateFiles` over `<data_dir>`:

* **pack**: the database is copied with `VACUUM INTO` into a scratch directory under the data
  directory, never tarred as it lies. The weekly run's database is in WAL mode, so its file alone is
  not the database while a writer is open; and a row a removal deleted stays in the file's free pages
  until they are reused, which an online backup copies too. `VACUUM INTO` writes a consistent,
  compacted copy that holds neither, so a removal's rewrite of the bundle holds no removed row. The tar holds
  `objects/manifests/<key>` for every manifest and `debate.sqlite3`, gzipped.
* **unpack**: every member is checked before anything is written: a regular file or a directory,
  named under `objects/manifests/` or exactly `debate.sqlite3`, with no absolute path and no `..`.
  Anything else refuses the whole bundle. Extraction then uses `tarfile`'s `data` filter as well.
* **install**: the manifests directory and the database are each replaced whole, by rename. The
  database's `-wal` and `-shm` files are removed first: they belong to the file being replaced, and
  SQLite would apply an old write-ahead log to the new file.

Scratch directories start with a dot, inside the data directory, so the copy of the database never
leaves the place the policy already allows it.
"""

from __future__ import annotations

import gzip
import os
import shutil
import sqlite3
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import Final

from debate_core.application.ports.run_state import (
    BUNDLE_DATABASE_NAME,
    BUNDLE_MANIFESTS_DIRECTORY,
    RunStateBundleUnreadable,
)
from debate_core.integrations.local.sqlite_db import DATABASE_FILENAME

__all__ = ["LocalRunStateFiles"]

_SIDE_FILES: Final = ("-wal", "-shm", "-journal")


class LocalRunStateFiles:
    """The data directory's manifests and database, packed into a bundle and installed from one."""

    def __init__(self, data_dir: Path, *, database_filename: str = DATABASE_FILENAME) -> None:
        self._data_dir = Path(data_dir)
        self._database = self._data_dir / database_filename

    def pack(self, destination: Path) -> None:
        manifests = self._data_dir / BUNDLE_MANIFESTS_DIRECTORY
        self._data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self._data_dir, prefix=".run-state-pack-") as scratch:
            copy = Path(scratch) / BUNDLE_DATABASE_NAME
            if self._database.is_file():
                _backup(self._database, copy)
            with tarfile.open(destination, "w:gz") as bundle:
                if manifests.is_dir():
                    for path in sorted(manifests.rglob("*")):
                        if path.is_file():
                            bundle.add(
                                path, arcname=path.relative_to(self._data_dir).as_posix(), recursive=False
                            )
                if copy.is_file():
                    bundle.add(copy, arcname=BUNDLE_DATABASE_NAME, recursive=False)

    def unpack(self, bundle: Path, staging: Path) -> None:
        try:
            with tarfile.open(bundle, "r:gz") as archive:
                members = archive.getmembers()
                for member in members:
                    _check(member)
                archive.extractall(staging, members=members, filter="data")
        except (tarfile.TarError, EOFError, gzip.BadGzipFile) as unreadable:
            raise RunStateBundleUnreadable(f"it is not a gzipped tar ({type(unreadable).__name__})") from None
        if not (staging / BUNDLE_DATABASE_NAME).is_file():
            raise RunStateBundleUnreadable("it holds no database")

    def install(self, staging: Path) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        staged_manifests = staging / BUNDLE_MANIFESTS_DIRECTORY
        manifests = self._data_dir / BUNDLE_MANIFESTS_DIRECTORY
        manifests.parent.mkdir(parents=True, exist_ok=True)
        if staged_manifests.is_dir():
            if manifests.exists():
                retired = Path(tempfile.mkdtemp(dir=self._data_dir, prefix=".run-state-replaced-"))
                manifests.rename(retired / "manifests")
                staged_manifests.rename(manifests)
                shutil.rmtree(retired)
            else:
                staged_manifests.rename(manifests)
        elif manifests.exists():
            shutil.rmtree(manifests)
        for suffix in _SIDE_FILES:
            Path(f"{self._database}{suffix}").unlink(missing_ok=True)
        os.replace(staging / BUNDLE_DATABASE_NAME, self._database)


def _backup(source: Path, destination: Path) -> None:
    """A consistent, compacted copy of the database at `source`: `VACUUM INTO`, read-only."""
    reading = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    try:
        reading.execute("VACUUM INTO ?", (str(destination),))
    finally:
        reading.close()


def _check(member: tarfile.TarInfo) -> None:
    """Refuse a member that is not one of the bundle's own. Names nothing from the archive."""
    name = PurePosixPath(member.name)
    if name.is_absolute() or ".." in name.parts:
        raise RunStateBundleUnreadable("a member names a path outside the data directory")
    if not (member.isfile() or member.isdir()):
        raise RunStateBundleUnreadable("a member is neither a file nor a directory")
    if member.name == BUNDLE_DATABASE_NAME and member.isfile():
        return
    manifests = PurePosixPath(BUNDLE_MANIFESTS_DIRECTORY)
    if name == manifests or manifests in name.parents:
        return
    raise RunStateBundleUnreadable("a member is neither a manifest nor the database")
