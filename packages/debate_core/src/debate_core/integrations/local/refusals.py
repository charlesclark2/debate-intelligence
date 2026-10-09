"""The operating system refusing a directory, translated at this package's edge (`v1-e01-t20`).

:class:`~debate_core.application.errors.StoreError` promises that a filesystem store raises
:class:`~debate_core.application.errors.StoreAccessDenied` when the operating system refuses a
directory, so that a `PermissionError` never reaches a service, and through it the CLI, as an
unmodelled exception: `verify` against an unreadable blob directory used to end as exit 70, "a
bug", when the honest answer is "the store could not be read" (exit 3).

The error names the directory's *role* — the blob directory, the manifest directory — and never
its absolute path. A path under the data directory carries the operator's home directory, and an
error message is copied into logs, a terminal and the `--json` envelope; the role is what tells an
operator which permission to fix. The original `PermissionError` stays on `__cause__` for a
traceback, exactly as the S3 adapter keeps its `ClientError`.

Only `PermissionError` is translated. A missing file is still :class:`NotFound` where a store
says so, and any other `OSError` (a full disk, an I/O error) is left as it is: it is not a refusal,
and this task does not decide what it is.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import PurePosixPath
from typing import Final

from debate_core.application.errors import StoreAccessDenied

__all__ = ["ACCESS_DENIED_HINT", "refused_as_access_denied", "role_of"]

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
    """Raise :class:`StoreAccessDenied` naming `role` for any `PermissionError` in the body."""
    try:
        yield
    except PermissionError as refused:
        raise StoreAccessDenied(operation, role, hint=ACCESS_DENIED_HINT) from refused
