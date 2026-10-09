"""A directory the operating system refuses, for tests that a store says so rather than crashing.

`chmod 000` is how a test makes a directory unreadable without touching anything outside
`tmp_path`. It proves nothing when the suite runs as root, which ignores the mode bits, so every
test that uses :func:`refused` carries :data:`needs_permissions` and is skipped there instead of
passing without having been refused anything.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest

__all__ = ["needs_permissions", "refused"]

needs_permissions = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root ignores directory modes, so nothing would be refused",
)


@contextmanager
def refused(directory: Path) -> Generator[None]:
    """Make `directory` unreadable and untraversable for the body, then restore its mode.

    The mode is restored even when the body fails, so `tmp_path` can still be cleaned up.
    """
    mode = directory.stat().st_mode & 0o777
    directory.chmod(0)
    try:
        yield
    finally:
        directory.chmod(mode)
