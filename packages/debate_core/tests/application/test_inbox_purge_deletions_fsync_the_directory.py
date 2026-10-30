"""A removal's deletions from the inbox survive a power cut: the inbox directory is fsynced after each.

A delete is an entry taken out of a directory, and until the directory itself is on the disk a
power cut can bring the file back. For an inbox archive that held removed bytes that is a takedown
that did not hold. `v1-e30-t26` gave the inbox rewrite the directory fsync after its rename;
`v1-e30-t30` gives the same to the two deletions the purge makes:

* `inbox_purge._carry_out`'s delete of a planned file, followed by a fsync of the inbox;
* the rewrite's removal of its staging directory, made before the fsync that follows the rename, so
  the one fsync puts both down.

A directory fsync that fails raises the operating system's own `OSError`, and the removal stops
`INCOMPLETE` at that file. That file is gone, but not durably, and a re-run plans nothing for it, so
every purge ends with one more fsync of the inbox, under the sync's run lock, even with nothing
planned: the re-run is what puts the earlier delete down (the PM's condition on `v1-e30-t30`).

No power is cut here. `os.unlink`, `os.rmdir`, `os.replace`, `os.open` and `os.fsync` are wrapped
to record what each did, in order, as `test_rename_into_place_writers_fsync_their_directory.py`
does for the rename.
"""

from __future__ import annotations

import hashlib
import io
import os
import stat
import zipfile
from pathlib import Path
from typing import Final

import pytest

from debate_core.application.caselist.inbox_purge import (
    CaselistInbox,
    InboxAction,
    InboxFileKind,
    InboxFilePlan,
    InboxInUse,
    InboxPurge,
    InboxReason,
    purge_inbox,
)
from debate_core.application.caselist_sync import LOCK_FILENAME, OPENEV_DELIVERIES_FILENAME, RunLock
from debate_core.integrations.local.archive_reader import ZipArchiveRewriter

type Event = tuple[str, str]

_LIMIT: Final = 64 * 1024 * 1024
FIRST_WEEK: Final = "testcl30-weekly-2026-09-28.zip"
SECOND_WEEK: Final = "testcl30-weekly-2026-10-05.zip"
CAMP_DOWNLOAD: Final = "openev-3030-Lantern Institute Affirmative.docx"
KEPT: Final = "testcl30-weekly/Riverbend Academy/MnPr/Riverbend Academy-MnPr-Aff-Seaside Cup-Round 1.docx"
DROPPED: Final = "testcl30-weekly/Riverbend Academy/MnPr/Riverbend Academy-MnPr-Neg-Seaside Cup-Round 2.docx"
STAGING: Final = "the rewrite's staging directory"


def _zip(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body in members.items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            archive.writestr(info, body)
    return buffer.getvalue()


@pytest.fixture
def inbox(tmp_path: Path) -> CaselistInbox:
    directory = tmp_path / "inbox"
    directory.mkdir()
    state = tmp_path / "state"
    state.mkdir()
    return CaselistInbox(
        directory=directory,
        state_dir=state,
        archives=ZipArchiveRewriter(max_archive_bytes=_LIMIT, max_unpacked_bytes=_LIMIT),
    )


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch, inbox: CaselistInbox) -> list[Event]:
    """Every delete, rename, directory open and directory fsync made in the inbox, in order.

    Recorded once the call has succeeded, so a delete of something already gone is not one. The
    run lock and the OpenEv delivery record live in the state directory and are left out; a
    staging directory, whose name is a fresh uuid, is named :data:`STAGING`. A fsynced directory is
    known by its inode, not by its descriptor's number, which the operating system hands out again
    once it is closed.
    """
    events: list[Event] = []
    real_open, real_fsync = os.open, os.fsync
    real_unlink, real_rmdir, real_replace = os.unlink, os.rmdir, os.replace

    def named(path: str | os.PathLike[str]) -> str | None:
        where = Path(path)
        if where.parent == inbox.directory and where.name.startswith("."):
            return STAGING
        if where == inbox.directory or where.parent == inbox.directory:
            return str(where)
        return None

    def note(what: str, path: str | os.PathLike[str]) -> None:
        if (name := named(path)) is not None:
            events.append((what, name))

    def recording_open(path: str | os.PathLike[str], flags: int, *args: int, **kwargs: int) -> int:
        descriptor = real_open(path, flags, *args, **kwargs)
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            note("open", path)
        return descriptor

    def recording_fsync(descriptor: int) -> None:
        real_fsync(descriptor)
        if os.path.samestat(os.fstat(descriptor), os.stat(inbox.directory)):
            note("fsync directory", inbox.directory)

    def recording_unlink(path: str | os.PathLike[str], *args: object, **kwargs: object) -> None:
        real_unlink(path, *args, **kwargs)
        note("unlink", path)

    def recording_rmdir(path: str | os.PathLike[str], *args: object, **kwargs: object) -> None:
        real_rmdir(path, *args, **kwargs)
        note("rmdir", path)

    def recording_replace(source: str | os.PathLike[str], destination: str | os.PathLike[str]) -> None:
        real_replace(source, destination)
        note("replace", destination)

    monkeypatch.setattr(os, "open", recording_open)
    monkeypatch.setattr(os, "fsync", recording_fsync)
    monkeypatch.setattr(os, "unlink", recording_unlink)
    monkeypatch.setattr(os, "rmdir", recording_rmdir)
    monkeypatch.setattr(os, "replace", recording_replace)
    return events


class RefusingDisk:
    """A disk that refuses to put a directory's entries down, `EIO`, the first `refusals` times."""

    def __init__(self, refusals: int) -> None:
        self.refusals = refusals


def refuse_directory_fsyncs(monkeypatch: pytest.MonkeyPatch, refusals: int) -> RefusingDisk:
    """Wraps whatever `os.fsync` is by now, so a recorder installed first sees only what succeeds."""
    disk = RefusingDisk(refusals=refusals)
    real_fsync = os.fsync

    def fsync(descriptor: int) -> None:
        if disk.refusals and stat.S_ISDIR(os.fstat(descriptor).st_mode):
            disk.refusals -= 1
            raise OSError(5, "Input/output error")
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fsync)
    return disk


@pytest.fixture
def directory_fsync_fails_once(monkeypatch: pytest.MonkeyPatch) -> RefusingDisk:
    return refuse_directory_fsyncs(monkeypatch, refusals=1)


def an_imported_week(inbox: CaselistInbox, name: str) -> InboxFilePlan:
    """A weekly archive this machine already imported, holding a removed file: deleted whole."""
    path = inbox.directory / name
    path.write_bytes(
        _zip({KEPT: f"{name}: round 1\n".encode(), DROPPED: f"{name}: removed round 2\n".encode()})
    )
    return InboxFilePlan(
        name=name,
        kind=InboxFileKind.WEEKLY_ARCHIVE,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        action=InboxAction.DELETE,
        reason=InboxReason.IMPORTED,
        entries_dropped=1,
        entries_kept=1,
    )


def a_removed_camp_download(inbox: CaselistInbox) -> InboxFilePlan:
    """A camp document that is itself removed, which the delivery record learns of first."""
    path = inbox.directory / CAMP_DOWNLOAD
    path.write_bytes(b"a synthetic camp affirmative that was removed\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return InboxFilePlan(
        name=CAMP_DOWNLOAD,
        kind=InboxFileKind.OPENEV,
        sha256=digest,
        action=InboxAction.DELETE,
        reason=InboxReason.THE_FILE_IS_REMOVED,
        removed_sha256=(digest,),
        openev_id=3030,
        delivered=frozenset({digest}),
    )


def a_waiting_week(inbox: CaselistInbox) -> InboxFilePlan:
    """A weekly archive waiting to be imported: rewritten without the removed file."""
    path = inbox.directory / SECOND_WEEK
    path.write_bytes(_zip({KEPT: b"the round 1 affirmative\n", DROPPED: b"the removed round 2 negative\n"}))
    return InboxFilePlan(
        name=SECOND_WEEK,
        kind=InboxFileKind.WEEKLY_ARCHIVE,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        action=InboxAction.REWRITE,
        reason=InboxReason.WAITING_TO_BE_IMPORTED,
        dropped=(DROPPED,),
        entries_dropped=1,
        entries_kept=1,
    )


def purge(inbox: CaselistInbox, planned: list[InboxFilePlan]) -> InboxPurge:
    done = InboxPurge()
    purge_inbox(inbox, planned, request_id="RM-2026-30", done=done)
    return done


def test_each_deleted_file_is_followed_by_a_fsync_of_the_inbox(
    inbox: CaselistInbox, recorded: list[Event]
) -> None:
    planned = [
        an_imported_week(inbox, FIRST_WEEK),
        an_imported_week(inbox, SECOND_WEEK),
        a_removed_camp_download(inbox),
    ]
    directory = str(inbox.directory)

    done = purge(inbox, planned)

    assert recorded == [
        ("unlink", str(inbox.directory / FIRST_WEEK)),
        ("open", directory),
        ("fsync directory", directory),
        ("unlink", str(inbox.directory / SECOND_WEEK)),
        ("open", directory),
        ("fsync directory", directory),
        ("unlink", str(inbox.directory / CAMP_DOWNLOAD)),
        ("open", directory),
        ("fsync directory", directory),
        ("open", directory),
        ("fsync directory", directory),
    ]
    assert sorted(os.listdir(inbox.directory)) == []
    assert (done.deleted, done.deliveries_recorded) == (3, 1)
    assert (inbox.state_dir / OPENEV_DELIVERIES_FILENAME).is_file()


def test_the_rewrite_removes_its_staging_directory_before_the_inbox_is_fsynced(
    inbox: CaselistInbox, recorded: list[Event]
) -> None:
    """The rename and the staging directory's removal are both entries in the inbox: one fsync after
    both, then the purge's own closing fsync."""
    planned = [a_waiting_week(inbox)]
    path = inbox.directory / SECOND_WEEK

    done = purge(inbox, planned)

    assert recorded == [
        ("replace", str(path)),
        ("rmdir", STAGING),
        ("open", str(path.parent)),
        ("fsync directory", str(path.parent)),
        ("open", str(path.parent)),
        ("fsync directory", str(path.parent)),
    ]
    assert sorted(os.listdir(inbox.directory)) == [SECOND_WEEK]
    with zipfile.ZipFile(path) as archive:
        assert archive.namelist() == [KEPT]
    assert done.rewritten == 1


def test_a_failed_fsync_after_a_delete_stops_the_purge_and_running_it_again_finishes_it(
    inbox: CaselistInbox, directory_fsync_fails_once: RefusingDisk
) -> None:
    """The first file is gone but not durably, so it is not counted; the second is left as it was.

    A re-run plans from what is in the inbox, which by then is the second file alone.
    """
    first, second = an_imported_week(inbox, FIRST_WEEK), an_imported_week(inbox, SECOND_WEEK)
    second_bytes = (inbox.directory / SECOND_WEEK).read_bytes()
    done = InboxPurge()

    with pytest.raises(OSError, match="Input/output error"):
        purge_inbox(inbox, [first, second], request_id="RM-2026-30", done=done)

    assert sorted(os.listdir(inbox.directory)) == [SECOND_WEEK]
    assert (inbox.directory / SECOND_WEEK).read_bytes() == second_bytes
    assert done.deleted == 0

    again = purge(inbox, [second])

    assert sorted(os.listdir(inbox.directory)) == []
    assert again.deleted == 1


def test_a_rerun_with_nothing_planned_puts_the_earlier_delete_down(
    inbox: CaselistInbox, recorded: list[Event], monkeypatch: pytest.MonkeyPatch
) -> None:
    """After the `EIO` stop the file is gone, so the re-run plans nothing, and still fsyncs the inbox."""
    first = an_imported_week(inbox, FIRST_WEEK)
    directory = str(inbox.directory)
    refuse_directory_fsyncs(monkeypatch, refusals=1)

    with pytest.raises(OSError, match="Input/output error"):
        purge(inbox, [first])

    assert recorded == [("unlink", str(inbox.directory / FIRST_WEEK)), ("open", directory)]
    assert sorted(os.listdir(inbox.directory)) == []
    recorded.clear()

    again = purge(inbox, [])

    assert recorded == [("open", directory), ("fsync directory", directory)]
    assert again == InboxPurge()


def test_nothing_planned_is_still_done_under_the_run_lock(
    inbox: CaselistInbox, recorded: list[Event]
) -> None:
    """A pull holding the lock stops even an empty purge, before its fsync."""
    with RunLock(inbox.state_dir / LOCK_FILENAME), pytest.raises(InboxInUse):
        purge(inbox, [])

    assert recorded == []


def test_nothing_planned_and_no_inbox_yet_does_nothing(tmp_path: Path) -> None:
    """An environment that does not pull has no inbox: nothing to fsync, and neither an inbox nor the
    lock file is made (`v1-e30-t09` pins the same for a whole removal on prod)."""
    never_pulled = CaselistInbox(
        directory=tmp_path / "inbox",
        state_dir=tmp_path,
        archives=ZipArchiveRewriter(max_archive_bytes=_LIMIT, max_unpacked_bytes=_LIMIT),
    )

    assert purge(never_pulled, []) == InboxPurge()
    assert not never_pulled.directory.exists()
    assert not (tmp_path / LOCK_FILENAME).exists()
