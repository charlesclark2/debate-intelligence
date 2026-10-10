"""The operating system refusing a directory, translated at this package's edge (`v1-e01-t20`).

:class:`~debate_core.application.errors.StoreError` promises that a filesystem store raises
:class:`~debate_core.application.errors.StoreAccessDenied` when the operating system refuses a
directory, so that a `PermissionError` never reaches a service, and through it the CLI, as an
unmodelled exception: `verify` against an unreadable blob directory used to end as exit 70, "a
bug", when the honest answer is "the store could not be read" (exit 3).

Every store in this package raises it through :func:`refused_as_access_denied`, as
:class:`~debate_core.application.errors.LocalStoreAccessDenied` (`v1-e34-t13`): the subclass is how
a caller knows the refusal came from this machine and not from a bucket, whose fix is a grant
rather than a permission on the data directory.

The error names the directory's *role* — the blob directory, the manifest directory — and never
its absolute path. A path under the data directory carries the operator's home directory, and an
error message is copied into logs, a terminal and the `--json` envelope; the role is what tells an
operator which permission to fix. The original `PermissionError` stays on `__cause__` for a
traceback, exactly as the S3 adapter keeps its `ClientError`.

Only `PermissionError` is translated. A missing file is still :class:`NotFound` where a store
says so, and any other `OSError` (a full disk, an I/O error) is left as it is: it is not a refusal,
and this task does not decide what it is.

## A listing that is refused is not an empty one

`Path.rglob` skips a directory it may not read and carries on, so a store listed with it reports an
unreadable tree as holding nothing, and every caller then acts on "nothing is here": a publish
finds every source missing, a pull finds no week imported and fetches them all again, a removal
finds no local copy to take out. :func:`files_under` walks a tree and raises the refusal instead,
for the stores to translate like any other.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Callable, Generator, Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Final

from debate_core.application.errors import LocalStoreAccessDenied

__all__ = ["ACCESS_DENIED_HINT", "files_under", "refused_as_access_denied", "role_of"]

ACCESS_DENIED_HINT: Final = (
    "the operating system refused it; check that this user can read and write the environment's "
    "data directory (storage.data_dir)"
)
"""The one line a CLI prints under the refusal. It names the setting, not the path it holds."""

#: What each directory under the data directory is for, as an operator would name it.
_ROLES: Final = {
    "blobs": "the blob directory",
    "objects": "the evidence object directory",
    "parsed": "the parsed-file directory",
    "manifests": "the manifest directory",
    "reports": "the report directory",
    "suppression": "the suppression directory",
}


def role_of(root_name: str, key: str = "") -> str:
    """The role of the directory a store rooted at `root_name` reaches for `key`.

    A named object's first key segment says more than the store's root does — `manifests/…` is the
    manifest directory, wherever the object tree is — so it wins when it is a known one. Nothing
    from the key past its first segment is used: the rest can carry a caselist slug or a filename.
    """
    first = PurePosixPath(key).parts[0] if key else ""
    return _ROLES.get(first) or _ROLES.get(root_name) or f"the {root_name} directory"


@contextmanager
def refused_as_access_denied(operation: str, role: str) -> Generator[None]:
    """Raise :class:`LocalStoreAccessDenied` naming `role` for any `PermissionError` in the body."""
    try:
        yield
    except PermissionError as refused:
        raise LocalStoreAccessDenied(operation, role, hint=ACCESS_DENIED_HINT) from refused


def files_under(directory: Path, *, descend: Callable[[Path], bool] | None = None) -> Iterator[Path]:
    """Every regular file under `directory`, at any depth; nothing when it does not exist.

    Raises `PermissionError` for the directory, or any directory or entry inside it, that the
    operating system will not let this user list or look at. Symbolic links are looked through to
    what they name, as `Path.is_file` does, and a link to a directory is not descended into. Any
    other error listing a directory skips that directory, as it always has: a directory removed
    while the walk is in progress is not a refusal.

    `descend`, when given, says which directories below `directory` to enter. One it turns down is
    never opened, so it cannot refuse the walk: a listing of one prefix is not stopped by an
    unreadable directory that could hold none of its keys.
    """
    if not _is_directory(directory):
        return

    def refuse(failed: OSError) -> None:
        if isinstance(failed, PermissionError):
            raise failed

    for parent, directories, names in os.walk(directory, onerror=refuse):
        if descend is not None:
            directories[:] = [name for name in directories if descend(Path(parent) / name)]
        for name in names:
            path = Path(parent) / name
            if _is_regular_file(path):
                yield path


def _is_directory(path: Path) -> bool:
    mode = _mode_of(path)
    return mode is not None and stat.S_ISDIR(mode)


def _is_regular_file(path: Path) -> bool:
    mode = _mode_of(path)
    return mode is not None and stat.S_ISREG(mode)


def _mode_of(path: Path) -> int | None:
    """The mode of what `path` names, or `None` when nothing is there.

    `os.stat` rather than `Path.is_dir`: what the latter does with a refusal has changed between
    Python versions, and "refused" must never read as "not there".
    """
    try:
        return os.stat(path).st_mode
    except (FileNotFoundError, NotADirectoryError):
        return None
