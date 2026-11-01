"""How much memory a long command has used so far, for its log lines (`v1-e40-t32`, the PM's amendment).

The first cloud backfile import was killed for memory at 71 minutes with nothing in its log
(`v1-e40-t30`). Each of the import's step-end and progress lines now carries two high-water marks, in
bytes, so that a reader can tell how close the task came to its 32 GB and what grew:

* **the container's**, read from its cgroup: `memory.peak` on cgroup v2, else v1's
  `memory/memory.max_usage_in_bytes`. Every process in the container is in it: the main process,
  the parse pool's workers, anything they started. AWS's documentation for Fargate platform 1.4.0
  does not say which cgroup version a task sees, so both are read, v2 first, and the line names the
  one it found;
* **the main process's own**, from `getrusage`, so that a main process that grows can be told from
  workers that grow: the container's peak less this one is, at most, everything else.

A figure that cannot be read is left out, never zero: on the Mac there is no cgroup, and a cgroup v2
kernel older than 5.19 has no `memory.peak`.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

__all__ = ["CGROUP_ROOT", "MemoryHighWater", "read_memory_high_water"]

CGROUP_ROOT: Final = Path("/sys/fs/cgroup")
"""Where a container sees its own cgroup. A test points it at a stand-in."""

_CGROUP_PEAKS: Final = (("v2", "memory.peak"), ("v1", "memory/memory.max_usage_in_bytes"))


@dataclass(frozen=True, slots=True)
class MemoryHighWater:
    """The high-water marks so far, in bytes; `None` where this machine cannot say."""

    container_peak_bytes: int | None = None
    cgroup: str | None = None
    """`v2` or `v1`: which cgroup the container's figure came from."""
    main_process_peak_bytes: int | None = None


def read_memory_high_water(cgroup_root: Path | None = None) -> MemoryHighWater:
    """The container's peak from its cgroup and the main process's from `getrusage`, as far as each reads."""
    root = CGROUP_ROOT if cgroup_root is None else cgroup_root
    container, cgroup = None, None
    for version, name in _CGROUP_PEAKS:
        container = _bytes_in(root / name)
        if container is not None:
            cgroup = version
            break
    return MemoryHighWater(
        container_peak_bytes=container, cgroup=cgroup, main_process_peak_bytes=_main_process_peak()
    )


def _bytes_in(path: Path) -> int | None:
    try:
        text = path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError):
        return None
    return int(text) if text.isdigit() else None


def _main_process_peak() -> int | None:
    try:
        import resource
    except ImportError:  # pragma: no cover - not a Unix
        return None
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Linux counts kibibytes, macOS bytes.
    return int(peak) if sys.platform == "darwin" else int(peak) * 1024
