"""A manifest written to this machine survives a power cut: the directory is fsynced after the rename.

`write_manifest_text` writes a temporary file beside the manifest, fsyncs it and renames it into
place. The rename is an entry in the directory, and until the directory itself is fsynced a power
cut can lose it: the old manifest, or none, comes back. `v1-e34-t23`'s Follow-up work 1 found the
missing step, and `v1-e30-t23` adds it. Every manifest writer on this machine goes through
`write_manifest_text`: `write_manifest` (an import's), and `write_manifest_lines` (a camp release's,
the pull's, and the measuring of a later manifest again), so each gains it.

No power is cut here. `os.fsync`, `os.open` and `os.replace` are wrapped to record what each was
asked to do, in order, and then do it.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Callable
from pathlib import Path

import pytest

from debate_core.application.caselist.manifest import write_manifest_lines, write_manifest_text

LINES = ('{"kind":"member","path":"a"}', '{"kind":"summary"}')

type Event = tuple[str, ...]


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> list[Event]:
    """Every fsync, directory open and rename made while a test runs, as `(what, of what)`.

    A file is named by its inode, which the rename keeps: the temporary file `mkstemp` opens has a
    name no test knows in advance. A directory is named by the path it was opened by.
    """
    events: list[Event] = []
    opened: dict[int, str] = {}
    real_open, real_fsync, real_replace = os.open, os.fsync, os.replace

    def recording_open(path: str | os.PathLike[str], flags: int, *args: int, **kwargs: int) -> int:
        descriptor = real_open(path, flags, *args, **kwargs)
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            opened[descriptor] = str(path)
            events.append(("open", str(path)))
        return descriptor

    def recording_fsync(descriptor: int) -> None:
        status = os.fstat(descriptor)
        if stat.S_ISDIR(status.st_mode):
            events.append(("fsync directory", opened.get(descriptor, "a directory opened elsewhere")))
        else:
            events.append(("fsync file", f"inode {status.st_ino}"))
        real_fsync(descriptor)

    def recording_replace(source: str | os.PathLike[str], destination: str | os.PathLike[str]) -> None:
        events.append(("replace", str(destination)))
        real_replace(source, destination)

    monkeypatch.setattr(os, "open", recording_open)
    monkeypatch.setattr(os, "fsync", recording_fsync)
    monkeypatch.setattr(os, "replace", recording_replace)
    return events


WRITERS: dict[str, Callable[[Path], Path]] = {
    "write_manifest_lines": lambda path: write_manifest_lines(LINES, path),
    "write_manifest_text": lambda path: write_manifest_text("".join(f"{line}\n" for line in LINES), path),
}


@pytest.mark.parametrize("writer", list(WRITERS))
def test_the_file_is_fsynced_then_renamed_then_its_directory_is_fsynced(
    writer: str, recorded: list[Event], tmp_path: Path
) -> None:
    destination = tmp_path / "manifests" / "testcl26" / "2026-10-08.jsonl"

    WRITERS[writer](destination)

    file = f"inode {os.stat(destination).st_ino}"
    assert recorded == [
        ("fsync file", file),
        ("replace", str(destination)),
        ("open", str(destination.parent)),
        ("fsync directory", str(destination.parent)),
    ]
    assert destination.read_text(encoding="utf-8") == "".join(f"{line}\n" for line in LINES)


def test_rewriting_a_manifest_fsyncs_its_directory_too(recorded: list[Event], tmp_path: Path) -> None:
    """A rewrite is a rename over the old file: the case a lost rename brings the old rows back."""
    destination = tmp_path / "2026-10-08.jsonl"
    destination.write_text("the old manifest\n", encoding="utf-8")

    write_manifest_lines(LINES, destination)

    assert recorded[-2:] == [("open", str(tmp_path)), ("fsync directory", str(tmp_path))]
    assert [event[0] for event in recorded].index("replace") < len(recorded) - 2


def test_a_directory_fsync_that_fails_is_a_write_that_failed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Raised as the operating system's own `OSError`, as a failed file fsync already was."""
    real_fsync = os.fsync

    def fsync(descriptor: int) -> None:
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError(5, "Input/output error")
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fsync)

    with pytest.raises(OSError, match="Input/output error"):
        write_manifest_lines(LINES, tmp_path / "2026-10-08.jsonl")
