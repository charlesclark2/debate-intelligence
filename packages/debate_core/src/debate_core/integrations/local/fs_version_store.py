"""This machine's evidence trees as the takedown sees them: one version per file, deleted by unlinking.

The local twin of :class:`~debate_core.integrations.s3.version_store.S3EvidenceVersionStore`, so a
removal deletes a local blob, a parsed file and a bucket object through one port
(:mod:`debate_core.application.ports.evidence_versions`). Rooted at one directory inside the data
directory — `blobs/`, `objects/` or `parsed/` — and keyed relative to it, exactly as
:class:`~debate_core.integrations.local.FsEvidenceObjectStore` keys the same files.
"""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from pathlib import Path

from debate_core.application.errors import NotFound
from debate_core.application.ports.evidence_store import validate_object_key
from debate_core.application.ports.evidence_versions import ObjectVersion
from debate_core.integrations.file_streaming import INCOMING_FILE_PREFIX

__all__ = ["FsEvidenceVersionStore"]


class FsEvidenceVersionStore:
    """An :class:`~debate_core.application.ports.evidence_versions.EvidenceVersionStore` on a directory."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    @property
    def root(self) -> Path:
        return self._root

    @property
    def location(self) -> str:
        return str(self._root)

    async def list_versions(self, prefix: str) -> tuple[ObjectVersion, ...]:
        """Every file under the root whose key starts with `prefix`.

        Only the directory the prefix names is walked — `sha256/ab/cd/<digest>` looks in one fan-out
        directory, not the whole blob tree — so a removal of sixty sources does not walk a
        2,000-file tree sixty times.
        """
        directory = prefix.rsplit("/", 1)[0] if "/" in prefix else ""
        start = self._root / directory if directory else self._root
        if not start.is_dir() or not start.resolve().is_relative_to(self._root.resolve()):
            return ()
        found = [
            ObjectVersion(key=key, version_id=None, size=path.stat().st_size)
            for path in start.rglob("*")
            if path.is_file()
            and not path.name.startswith(INCOMING_FILE_PREFIX)
            and (key := path.relative_to(self._root).as_posix()).startswith(prefix)
        ]
        return tuple(sorted(found))

    async def get_version_file(self, version: ObjectVersion, destination: Path) -> None:
        source = self._path_for(version.key)
        if not source.is_file():
            raise NotFound("evidence object", version.key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

    async def delete_versions(self, versions: Sequence[ObjectVersion]) -> int:
        for version in versions:
            path = self._path_for(version.key)
            path.unlink(missing_ok=True)
            self._prune_empty_directories(path.parent)
        return len(versions)

    def _path_for(self, key: str) -> Path:
        candidate = self._root / validate_object_key(key)
        if not candidate.resolve().is_relative_to(self._root.resolve()):
            raise ValueError(f"evidence object key resolves outside the store: {key!r}")
        return candidate

    def _prune_empty_directories(self, directory: Path) -> None:
        """Remove the fan-out directories a deletion emptied, up to (not including) the root."""
        root = self._root.resolve()
        current = directory
        while current.resolve() != root and current.is_dir() and not any(current.iterdir()):
            current.rmdir()
            current = current.parent
