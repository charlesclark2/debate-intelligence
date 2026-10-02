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

## Taking members out of an archive that is still waiting to be imported

A removal (`v1-e30-t09`) has to take removed files out of a weekly archive in the sync's inbox
without losing the other teams' disclosures in it. That is the one place an archive is written
rather than read, and it is a Protocol, :class:`ArchiveRewriter`, because it is two operations
that must agree with each other and with the reader: :meth:`ArchiveRewriter.inventory` lists every
entry by the name the archive carries *and* the path the reader would give it, with a digest of its
bytes whether or not the reader would import it; :meth:`ArchiveRewriter.rewrite_without` copies
every entry but the named ones. A zip-slip member is never imported, but it can still hold removed
bytes, which is why the inventory hashes it.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from debate_core.domain import Sha256Hex

__all__ = [
    "ArchiveEntry",
    "ArchiveMember",
    "ArchiveRewriter",
    "InventoriedEntry",
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


@dataclass(frozen=True, slots=True)
class InventoriedEntry:
    """One entry of a zip, as the archive names it and as the reader would read it."""

    name: str
    """The entry's name exactly as the zip carries it: what a rewrite drops entries by."""

    path: str
    """The path the archive reader reports for it, wrapper directory off: what the importer records."""

    skip_reason: SkipReason | None
    """Why the reader would skip it, or `None` for a member it would import."""

    sha256: Sha256Hex | None
    """The digest of its bytes, skipped or not. `None` only for a directory entry, which has none."""

    @property
    def is_directory(self) -> bool:
        return self.sha256 is None


class ArchiveRewriter(Protocol):
    """Lists a zip's entries and writes a copy of it without some of them. See the module docstring."""

    def inventory(self, source: Path) -> tuple[InventoriedEntry, ...]:
        """Every entry of the zip at `source`, in the archive's own order.

        Raises :class:`~debate_core.application.errors.UnreadableArchive` for a file that is not a
        readable zip and :class:`~debate_core.application.errors.ArchiveTooLarge` for one over the
        reader's ceilings, having read nothing.
        """
        ...

    def rewrite_without(
        self, source: Path, destination: Path, *, drop: Collection[str], comment: bytes
    ) -> None:
        """Write to `destination` a zip holding every entry of `source` but those named in `drop`.

        Each kept entry is copied as it was — name, bytes, timestamp, compression, attributes — so
        the reader reads it exactly as before. `comment` replaces the archive's comment. `source`
        is not changed.
        """
        ...
