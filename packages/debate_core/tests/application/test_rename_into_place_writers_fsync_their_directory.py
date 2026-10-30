"""Three more rename-into-place writers survive a power cut: the directory is fsynced after the rename.

`v1-e30-t23` gave the manifest writer this order: fsync the temporary file, rename it into place,
fsync the directory, and raise when the directory fsync fails. The rename is an entry in the
directory, and until the directory itself is on the disk a power cut can bring back the file the
rename replaced, or none. Its Follow-up work 1 named three writers that stopped at the rename, and
`v1-e30-t26` gives each the same order:

* `caselist/inbox_purge.py`'s rewrite of an inbox archive, where a lost rename brings back the
  entries a removal took out;
* `integrations/opencaselist/token_store.py`'s file token store, `FileTokenBackend.write`;
* `integrations/models/_recorded_files.py`'s `write_pretty_json`, the recordings tool's writer,
  which fsynced nothing before.

No power is cut here. `os.fsync`, `os.open` and `os.replace` are wrapped to record what each was
asked to do, in order, and then do it, as `caselist/test_manifest_write_fsyncs_its_directory.py`
does for the manifest.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Final

import pytest

from debate_core.application.caselist.inbox_purge import (
    CaselistInbox,
    InboxAction,
    InboxFileKind,
    InboxFilePlan,
    InboxPurge,
    InboxReason,
    purge_inbox,
)
from debate_core.integrations.local.archive_reader import ZipArchiveRewriter
from debate_core.integrations.models._recorded_files import write_pretty_json
from debate_core.integrations.opencaselist.token_store import FileTokenBackend

type Event = tuple[str, ...]

_LIMIT: Final = 64 * 1024 * 1024
WEEKLY: Final = "testcl26-weekly-2026-10-05.zip"
KEPT: Final = "testcl26-weekly/Riverbend Academy/MnPr/Riverbend Academy-MnPr-Aff-Seaside Cup-Round 1.docx"
DROPPED: Final = "testcl26-weekly/Riverbend Academy/MnPr/Riverbend Academy-MnPr-Neg-Seaside Cup-Round 2.docx"


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> list[Event]:
    """Every fsync, directory open and rename made while a test runs, as `(what, of what)`.

    A file is named by its inode, which the rename keeps: a temporary file's name is the writer's
    own business. A directory is named by the path it was opened by.
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


@pytest.fixture
def directory_fsync_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """A disk that refuses to put a directory's entries down: `EIO`, as the operating system says it."""
    real_fsync = os.fsync

    def fsync(descriptor: int) -> None:
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError(5, "Input/output error")
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fsync)


# ------------------------------------------------------------------------------------------------
# The writers, each run through its own public entry point. Each returns the file it put in place.
# ------------------------------------------------------------------------------------------------


def write_a_recorded_answer(root: Path) -> Path:
    path = root / "recorded" / "landscape.position" / "answer.json"
    write_pretty_json(path, {"answer": "Lantern Classic", "calls": 1})
    return path


def write_the_token_file(root: Path) -> Path:
    path = root / "opencaselist" / "token"
    FileTokenBackend(path).write("synthetic-token-value")
    return path


def _zip(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body in members.items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            archive.writestr(info, body)
    return buffer.getvalue()


def rewrite_an_inbox_archive(root: Path) -> Path:
    """A removal's rewrite of a weekly archive waiting in the inbox, without one of its two files."""
    inbox = root / "inbox"
    inbox.mkdir(parents=True)
    state = root / "state"
    state.mkdir()
    path = inbox / WEEKLY
    path.write_bytes(_zip({KEPT: b"the round 1 affirmative\n", DROPPED: b"the removed round 2 negative\n"}))
    plan = InboxFilePlan(
        name=WEEKLY,
        kind=InboxFileKind.WEEKLY_ARCHIVE,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        action=InboxAction.REWRITE,
        reason=InboxReason.WAITING_TO_BE_IMPORTED,
        dropped=(DROPPED,),
        entries_dropped=1,
        entries_kept=1,
    )
    done = InboxPurge()
    purge_inbox(
        CaselistInbox(
            directory=inbox,
            state_dir=state,
            archives=ZipArchiveRewriter(max_archive_bytes=_LIMIT, max_unpacked_bytes=_LIMIT),
        ),
        [plan],
        request_id="RM-2026-26",
        done=done,
    )
    assert done.rewritten == 1
    return path


WRITERS: Final[dict[str, Callable[[Path], Path]]] = {
    "inbox_purge rewrite": rewrite_an_inbox_archive,
    "token_store FileTokenBackend.write": write_the_token_file,
    "write_pretty_json": write_a_recorded_answer,
}


def what_it_holds(writer: str, path: Path) -> object:
    """What each writer was asked to put there, read back by hand."""
    if writer == "inbox_purge rewrite":
        with zipfile.ZipFile(path) as archive:
            return sorted(archive.namelist())
    if writer == "write_pretty_json":
        return json.loads(path.read_text(encoding="utf-8"))
    return path.read_text(encoding="utf-8")


EXPECTED_CONTENT: Final[dict[str, object]] = {
    "inbox_purge rewrite": [KEPT],
    "token_store FileTokenBackend.write": "synthetic-token-value",
    "write_pretty_json": {"answer": "Lantern Classic", "calls": 1},
}


@pytest.mark.parametrize("writer", list(WRITERS))
def test_the_file_is_fsynced_then_renamed_then_its_directory_is_fsynced(
    writer: str, recorded: list[Event], tmp_path: Path
) -> None:
    path = WRITERS[writer](tmp_path)

    assert recorded == [
        ("fsync file", f"inode {os.stat(path).st_ino}"),
        ("replace", str(path)),
        ("open", str(path.parent)),
        ("fsync directory", str(path.parent)),
    ]
    assert what_it_holds(writer, path) == EXPECTED_CONTENT[writer]


@pytest.mark.parametrize("writer", list(WRITERS))
def test_a_rewrite_over_an_earlier_file_fsyncs_its_directory_too(
    writer: str, recorded: list[Event], tmp_path: Path
) -> None:
    """A rewrite is a rename over the old file: the case a lost rename brings the old one back.

    The inbox rewrite is always one; the other two are run twice, and the second run is the one read.
    """
    if writer != "inbox_purge rewrite":
        WRITERS[writer](tmp_path)
        recorded.clear()

    path = WRITERS[writer](tmp_path)

    assert recorded[-3:] == [
        ("replace", str(path)),
        ("open", str(path.parent)),
        ("fsync directory", str(path.parent)),
    ]


@pytest.mark.parametrize("writer", list(WRITERS))
def test_a_directory_fsync_that_fails_is_a_write_that_failed(
    writer: str, directory_fsync_fails: None, tmp_path: Path
) -> None:
    """Raised as the operating system's own `OSError`; the new file is in place by then."""
    with pytest.raises(OSError, match="Input/output error"):
        WRITERS[writer](tmp_path)
