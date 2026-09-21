"""What reading an archive produces, and the boundary the importer reads it across.

The caselist importer is handed the members of a weekly archive. *How* they are got — out of a
zip, out of a directory somebody already unpacked, and in V2 out of an object in a bucket — is an
adapter's business, so the vocabulary lives here and
:mod:`debate_core.integrations.local.archive_reader` is one implementation of it.

There is no `ArchiveReader` Protocol, deliberately. A reader is an iterable of entries and
nothing else: the importer takes `Iterable[ArchiveEntry]`, so a test hands it a list, the CLI
hands it a generator over a zip, and neither needs a class to conform to.

## Skips are values, not absences

A member the reader will not import — junk, a symlink, a name that climbs out of the archive —
becomes a :class:`SkippedMember` carrying its reason, not a silent `continue`. The importer counts
them and the manifest records them, because "1,597 members, 1,592 imported, 5 skipped" is a
sentence an operator can check against the archive and "1,592 imported" is not.

A :class:`SkippedMember` never carries the member's bytes. Nothing was read, and nothing should
be able to act as though it was.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from debate_core.domain import Sha256Hex

__all__ = [
    "ArchiveEntry",
    "ArchiveMember",
    "SkipReason",
    "SkippedMember",
]


class SkipReason(StrEnum):
    """Why a member of an archive was not imported.

    Every one is counted and reported. A skip nobody can see is indistinguishable from a bug.
    """

    MACOS_METADATA = "MACOS_METADATA"
    """`__MACOSX/…` or an AppleDouble `._name` sidecar: the resource fork of a real member."""

    DESKTOP_SERVICES_STORE = "DESKTOP_SERVICES_STORE"
    """`.DS_Store`: how the Finder remembers a folder's icon positions."""

    WORD_LOCK_FILE = "WORD_LOCK_FILE"
    """`~$name.docx`: Word's marker for a document somebody had open when the archive was made."""

    SYMLINK = "SYMLINK"
    """A symbolic link. Never followed: it names a file the archive does not contain."""

    PATH_OUTSIDE_ARCHIVE = "PATH_OUTSIDE_ARCHIVE"
    """A member naming an absolute path or climbing out with `..` — the zip-slip shape."""

    EMPTY_PATH = "EMPTY_PATH"
    """A member with no usable name at all."""


@dataclass(frozen=True, slots=True)
class ArchiveMember:
    """One file from an archive: where it sits, what it weighs, and its bytes."""

    path: str
    """Its path relative to the archive root, `/`-separated and with any wrapper directory off."""

    sha256: Sha256Hex
    """The digest of :attr:`data`. The identity of the source document it becomes."""

    byte_size: int
    data: bytes

    @property
    def is_skipped(self) -> bool:
        """False. Present so a caller can branch on one attribute across the union."""
        return False


@dataclass(frozen=True, slots=True)
class SkippedMember:
    """A member that was not imported, and why. Never carries the member's bytes."""

    path: str
    reason: SkipReason

    @property
    def is_skipped(self) -> bool:
        """True."""
        return True


type ArchiveEntry = ArchiveMember | SkippedMember
"""What reading an archive yields: a member with its bytes, or a skip with its reason."""
