"""Reading the members of a weekly archive, without trusting a single thing it says.

The importer is handed a file somebody downloaded from the internet and asked to write its
contents onto the operator's disk. Every name in it is attacker-controlled in principle and
careless in practice, so this module is the one place that decides what a member *is* before any
of it is believed:

* **Nothing lands outside the archive.** A member whose name is absolute, or that climbs out with
  `..`, is skipped with a counted reason and never opened. This reader does not unpack to a
  staging directory at all — it hands the bytes straight to the caller, which is the strongest
  form of the guarantee: there is no path to escape onto.
* **Symlinks are skipped, never followed.** A zip can carry one, and a directory somebody already
  unpacked certainly can. Following it would read a file the archive does not contain.
* **Size is checked before anything is read.** The archive's own size, and the total its directory
  claims its members unpack to — the second is what stops a small zip that claims to expand to a
  terabyte. Both raise :class:`ArchiveTooLarge` before a single member is extracted (ac5).
* **Junk is skipped with a reason, not silently.** `__MACOSX/`, AppleDouble `._` files,
  `.DS_Store` and `~$` Word lock files are in every archive a Mac made. They are counted, because
  a skip nobody can see is indistinguishable from a bug.

## What a caller gets

One iterator of :data:`ArchiveEntry`, in path order: an :class:`ArchiveMember` with its bytes and
digest, or a :class:`SkippedMember` with the reason. Path order rather than archive order so that
two reads of one archive classify in the same sequence, which is what makes a re-import produce a
byte-identical manifest (ac3).

Members are read one at a time and their bytes are not retained, so a 700 MB archive costs one
member of memory rather than 700 MB.

## Zips and directories are the same thing

An operator has a `.zip` straight from OpenCaselist, or a directory they already unpacked. Both
are read here, and both yield the same relative paths — `<School>/<TeamCode>/<file>` — so a
manifest does not record which form the import happened to run from. A zip wraps its contents in
one directory named after the archive (`hsld26-0915/…`), and :func:`read_archive` takes that
wrapper off; see :func:`common_root_to_strip` for exactly when it will and will not.

## Where this lives

In `integrations.local` rather than in `application`, because it is an adapter: it knows about
`zipfile`, about macOS's metadata conventions and about the filesystem. The importer
(:mod:`debate_core.application.caselist.import_service`) is handed the entries and never opens
anything itself.
"""

from __future__ import annotations

import hashlib
import os
import stat
import zipfile
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

from debate_core.application.errors import ArchiveTooLarge, UnreadableArchive
from debate_core.application.ports.archive import (
    ArchiveEntry,
    ArchiveMember,
    SkippedMember,
    SkipReason,
)

__all__ = [
    "ArchiveEntry",
    "ArchiveMember",
    "ArchiveTooLarge",
    "SkipReason",
    "SkippedMember",
    "UnreadableArchive",
    "archive_digest",
    "common_root_to_strip",
    "read_archive",
]

#: Directory macOS puts a member's resource fork in.
_MACOS_METADATA_DIRECTORY = "__MACOSX"

#: Prefix of an AppleDouble sidecar sitting beside the file it describes.
_APPLEDOUBLE_PREFIX = "._"

#: What the Finder leaves in every directory it has displayed.
_DESKTOP_SERVICES_STORE = ".DS_Store"

#: Prefix of the lock file Word writes beside an open document.
_WORD_LOCK_PREFIX = "~$"

#: How much of a file is read at a time when hashing an archive's own bytes.
_HASH_CHUNK_BYTES = 1024 * 1024

#: Depth every member is expected at once a wrapper directory has been stripped:
#: `<School>/<TeamCode>/<file>`. See :func:`common_root_to_strip`.
_DISCLOSURE_PATH_DEPTH = 3


def read_archive(source: Path, *, max_archive_bytes: int, max_unpacked_bytes: int) -> Iterator[ArchiveEntry]:
    """Yield every member of `source`, in path order, as an import-ready entry or a counted skip.

    `source` is a `.zip` or a directory somebody already unpacked; both yield the same relative
    paths. The two ceilings come from `settings.caselist` and are both checked before anything is
    read, so an archive that is over either of them raises :class:`ArchiveTooLarge` having
    extracted nothing.

    Raises :class:`UnreadableArchive` when `source` is neither, or is a zip that will not open.
    """
    location = Path(source)
    if location.is_dir():
        yield from _read_directory(location, max_unpacked_bytes=max_unpacked_bytes)
        return
    if not location.is_file():
        raise UnreadableArchive(location.name, "no such file or directory")
    yield from _read_zip(location, max_archive_bytes=max_archive_bytes, max_unpacked_bytes=max_unpacked_bytes)


def archive_digest(source: Path) -> str:
    """The SHA-256 of the archive itself, which is how "already imported this exact file" is asked.

    A zip is hashed as the file it is. A directory has no bytes of its own, so its digest is taken
    over its members' paths and digests — the same directory therefore hashes the same way twice,
    and a directory and the zip it came out of do not, which is honest: they are not the same
    download.
    """
    location = Path(source)
    if location.is_file():
        digest = hashlib.sha256()
        with location.open("rb") as stream:
            while chunk := stream.read(_HASH_CHUNK_BYTES):
                digest.update(chunk)
        return digest.hexdigest()
    if not location.is_dir():
        raise UnreadableArchive(location.name, "no such file or directory")
    digest = hashlib.sha256(b"debate-intelligence/unpacked-caselist-archive/v1\n")
    for path, data in sorted(_walk_directory(location)):
        digest.update(f"{path}\n{hashlib.sha256(data).hexdigest()}\n".encode())
    return digest.hexdigest()


def common_root_to_strip(paths: list[str], *, archive_stem: str) -> str | None:
    """The single wrapper directory to take off every path, or `None` to leave them alone.

    A downloaded weekly archive holds one directory named after itself, and every member is inside
    it: `hsld26-0915/Maple Grove/QX/….docx`. Stripping it is what makes a zip import and a
    directory import record the same paths.

    Guessing wrongly would be worse than not guessing, because the directory taken off would be a
    school. So the wrapper is stripped only when the archive says twice over that it is one:

    * every member with a directory in its path shares the same first component, **and**
    * that component is either the archive's own filename stem, or removing it still leaves every
      ordinary member at `<School>/<TeamCode>/<file>` depth.

    A zip of one school's directory — `Maple Grove/QX/….docx`, one shared first component that is
    neither the stem nor deep enough to spare — is therefore left exactly as it is.
    """
    nested = [PurePosixPath(path) for path in paths if len(PurePosixPath(path).parts) > 1]
    if not nested:
        return None
    candidates = {path.parts[0] for path in nested}
    if len(candidates) != 1:
        return None
    root = candidates.pop()
    if root == archive_stem:
        return root
    ordinary = [path for path in nested if _skip_reason_for(path.as_posix()) is None]
    if ordinary and all(len(path.parts) > _DISCLOSURE_PATH_DEPTH for path in ordinary):
        return root
    return None


# ------------------------------------------------------------------------------------------------
# Zips
# ------------------------------------------------------------------------------------------------


def _read_zip(location: Path, *, max_archive_bytes: int, max_unpacked_bytes: int) -> Iterator[ArchiveEntry]:
    """Read a zip, refusing it outright if it is over either ceiling."""
    on_disk = location.stat().st_size
    if on_disk > max_archive_bytes:
        raise ArchiveTooLarge(
            measured="archive",
            actual_bytes=on_disk,
            limit_bytes=max_archive_bytes,
            source=location.name,
        )
    try:
        with zipfile.ZipFile(location) as archive:
            entries = [info for info in archive.infolist() if not info.is_dir()]
            declared = sum(info.file_size for info in entries)
            if declared > max_unpacked_bytes:
                raise ArchiveTooLarge(
                    measured="unpacked",
                    actual_bytes=declared,
                    limit_bytes=max_unpacked_bytes,
                    source=location.name,
                )
            yield from _zip_entries(archive, entries, archive_stem=location.stem)
    except zipfile.BadZipFile as broken:
        raise UnreadableArchive(location.name, "not a readable zip file") from broken


def _zip_entries(
    archive: zipfile.ZipFile, entries: list[zipfile.ZipInfo], *, archive_stem: str
) -> Iterator[ArchiveEntry]:
    """Classify and read a zip's members, in path order.

    Containment is decided on the name the zip actually carries, **before** any wrapper directory
    is stripped. The other way round, `hsld26-0915/../escaped.docx` would normalize back inside
    the archive and pass a check it should fail.
    """
    contained = [info for info in entries if _is_contained(info.filename)]
    root = common_root_to_strip([_normalized(info.filename) for info in contained], archive_stem=archive_stem)

    classified: list[tuple[str, zipfile.ZipInfo, SkipReason | None]] = []
    for info in entries:
        raw = _normalized(info.filename)
        if not _is_contained(info.filename):
            classified.append((raw, info, SkipReason.PATH_OUTSIDE_ARCHIVE))
            continue
        path = _strip_root(raw, root)
        reason = SkipReason.SYMLINK if _is_zip_symlink(info) else _skip_reason_for(path)
        classified.append((path, info, reason))

    for path, info, reason in sorted(classified, key=lambda entry: entry[0]):
        if reason is not None:
            yield SkippedMember(path=path, reason=reason)
            continue
        data = archive.read(info)
        yield ArchiveMember(
            path=path, sha256=hashlib.sha256(data).hexdigest(), byte_size=len(data), data=data
        )


def _is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    """Whether a zip entry is a symlink, from the Unix mode its external attributes carry."""
    return stat.S_ISLNK(info.external_attr >> 16)


# ------------------------------------------------------------------------------------------------
# Directories
# ------------------------------------------------------------------------------------------------


def _read_directory(location: Path, *, max_unpacked_bytes: int) -> Iterator[ArchiveEntry]:
    """Read an already-unpacked archive.

    No wrapper directory is stripped: the directory the operator pointed at *is* the archive root,
    and a caselist with one school in it would otherwise lose the school.
    """
    found: list[tuple[str, Path, bool]] = []
    total = 0
    # followlinks=False so a symlinked directory is never descended into; a link is a member to
    # be skipped, not a door to walk through.
    for directory, _, filenames in os.walk(location, followlinks=False):
        here = Path(directory)
        for filename in filenames:
            path = here / filename
            relative = path.relative_to(location).as_posix()
            is_link = path.is_symlink()
            found.append((relative, path, is_link))
            if not is_link:
                total += path.lstat().st_size
    if total > max_unpacked_bytes:
        raise ArchiveTooLarge(
            measured="unpacked",
            actual_bytes=total,
            limit_bytes=max_unpacked_bytes,
            source=location.name,
        )

    for relative, path, is_link in sorted(found):
        if is_link:
            yield SkippedMember(path=relative, reason=SkipReason.SYMLINK)
            continue
        reason = _skip_reason_for(relative)
        if reason is not None:
            yield SkippedMember(path=relative, reason=reason)
            continue
        data = path.read_bytes()
        yield ArchiveMember(
            path=relative, sha256=hashlib.sha256(data).hexdigest(), byte_size=len(data), data=data
        )


def _walk_directory(location: Path) -> Iterator[tuple[str, bytes]]:
    """Every ordinary file under `location`, for :func:`archive_digest`. Symlinks are not read."""
    for directory, _, filenames in os.walk(location, followlinks=False):
        here = Path(directory)
        for filename in filenames:
            path = here / filename
            if path.is_symlink():
                continue
            yield path.relative_to(location).as_posix(), path.read_bytes()


# ------------------------------------------------------------------------------------------------
# Names
# ------------------------------------------------------------------------------------------------


def _normalized(name: str) -> str:
    """A member name as a `/`-separated path, with a Windows-made zip's backslashes flattened."""
    return name.replace("\\", "/").strip()


def _is_contained(name: str) -> bool:
    """Whether a member name stays inside the archive.

    Refuses an absolute path, a Windows drive letter and any `..` component. Checked on the raw
    name, so nothing can be normalized into safety first.
    """
    normalized = _normalized(name)
    if not normalized:
        return False
    if normalized.startswith("/"):
        return False
    if len(normalized) > 1 and normalized[1] == ":":
        return False
    return ".." not in PurePosixPath(normalized).parts


def _strip_root(path: str, root: str | None) -> str:
    """Take the wrapper directory off a member's path, if there is one to take off."""
    if root is None:
        return path
    parts = PurePosixPath(path).parts
    if len(parts) > 1 and parts[0] == root:
        return PurePosixPath(*parts[1:]).as_posix()
    return path


def _skip_reason_for(path: str) -> SkipReason | None:
    """Why this path is junk rather than evidence, or `None` when it is a real member."""
    pure = PurePosixPath(path)
    if not path or not pure.name:
        return SkipReason.EMPTY_PATH
    if _MACOS_METADATA_DIRECTORY in pure.parts or pure.name.startswith(_APPLEDOUBLE_PREFIX):
        return SkipReason.MACOS_METADATA
    if pure.name == _DESKTOP_SERVICES_STORE:
        return SkipReason.DESKTOP_SERVICES_STORE
    if pure.name.startswith(_WORD_LOCK_PREFIX):
        return SkipReason.WORD_LOCK_FILE
    return None
