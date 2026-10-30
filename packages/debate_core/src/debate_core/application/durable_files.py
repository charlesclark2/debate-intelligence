"""Putting a rename on the disk: the directory fsync every rename-into-place writer ends with.

A writer that must never leave a file half-written writes a temporary file beside it, fsyncs that
file and renames it over the name. The fsync puts the bytes on the disk and the rename makes them
the file, in one step, but the rename itself is an entry in the directory: until the directory is
fsynced too, a power cut can bring back the file the rename replaced, or none. So the order is
file fsync, rename, directory fsync (`v1-e30-t23`, for the manifest writer).

A directory fsync that fails is a write that failed, raised as the operating system's own
`OSError`, as a failed file fsync is. The new file is in place by then, and writing it again is the
fix. :mod:`debate_core.integrations.file_streaming` is the one writer that treats it as best
effort, and says why.

The writers that end here: the manifest writer
(:func:`~debate_core.application.caselist.manifest.write_manifest_text`), and since `v1-e30-t26`
the removal's rewrite of an inbox archive
(:mod:`~debate_core.application.caselist.inbox_purge`), the file token store
(:class:`~debate_core.integrations.opencaselist.token_store.FileTokenBackend`) and the recordings
tool's :func:`~debate_core.integrations.models._recorded_files.write_pretty_json`.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["fsync_directory"]


def fsync_directory(directory: Path) -> None:
    """Put `directory`'s own entries on the disk: the rename that just happened in it."""
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
