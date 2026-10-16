"""Every state file the sync writes is on the disk before it takes its name (`v1-e34-t19`).

`v1-e34-t18` made each state file a write to a second file and a rename, so that a run killed while
writing never leaves half a file. A rename orders the name, not the bytes: after a power cut the
name can point at a file whose contents never reached the disk, which is the cut-short file
`PendingWork.read` refuses. So the second file is flushed and fsynced before the rename, and the
directory is fsynced after it, so that the rename itself is on the disk.

What these tests record is the calls the operating system was given and their order: each `fsync`
with what the descriptor named and how many bytes the file held *as the operating system saw it at
that moment*, and each rename. A file that was fsynced before its bytes left Python's buffer shows
here as a file of no bytes.

The four state files are the four things `write_state_file` writes: the pending-work file, the download
ledger, the OpenEv delivery record, and a run's summary.

`v1-e34-t23` (item 2) holds the rest of what the sync writes to the same rule: the run monitor's
file of records still owed to the bucket, which was renamed into place with nothing fsynced, and
the two logs, the run log and the run details, which are appended to and were never fsynced. An
append has no second file to rename: the line goes to the end of the file, the file goes to the
disk, and the directory goes to the disk after it, for the append that created the file. And a
state file removed because nothing is owed any more is a write too: its directory is fsynced
after the name goes.
"""

from __future__ import annotations

import errno
import os
import stat
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from debate_core.application import sync_runs
from debate_core.application.caselist_sync import (
    DownloadLedger,
    OpenEvDeliveries,
    OpenEvDelivery,
    PendingSnapshot,
    PendingWork,
    RunSummary,
    StageOutcome,
    StageRecord,
    SyncStage,
)
from debate_core.application.sync_runs import SyncRunDetails, SyncRunDetailsLog, SyncRunLog, SyncRunRecord

from .test_inbox_retention import ExpiredBucket, FakeSource, Installation

STARTED = datetime(2026, 9, 16, 6, 0, tzinfo=UTC)


def write_the_pending_work_file(directory: Path) -> Path:
    path = directory / "caselist-sync-pending.json"
    PendingWork(path).write([PendingSnapshot("testcl26", "2026-09-01")])
    return path


def write_the_download_ledger(directory: Path) -> Path:
    path = directory / "caselist-sync-download-starts.json"
    DownloadLedger(path).record(STARTED)
    return path


def write_the_delivery_record(directory: Path) -> Path:
    path = directory / "caselist-sync-openev-deliveries.json"
    OpenEvDeliveries(path).record(
        512,
        OpenEvDelivery(download_sha256="a" * 64, path_sha256=None, member_sha256=frozenset({"b" * 64})),
    )
    return path


def write_a_run_summary(directory: Path) -> Path:
    """The summary file, written by the pull itself: its writer is the service's own."""
    installation = Installation(data_dir=directory, bucket=ExpiredBucket(), archives={})
    service = installation.sync(FakeSource({}), bucket=False)
    summary = RunSummary(
        run_id="20260916T060000Z",
        started_at=STARTED,
        finished_at=STARTED,
        dry_run=False,
        caselists=("testcl26",),
        stages=(StageRecord(stage=SyncStage.SELECT, outcome=StageOutcome.COMPLETED),),
    )
    return service._write_summary(summary)  # pyright: ignore[reportPrivateUsage]


def write_the_owed_records_file(directory: Path) -> Path:
    """The run monitor's list of records not yet in the bucket (`v1-e34-t23`)."""
    path = directory / "caselist-sync-records-pending.json"
    sync_runs._PendingRecords(path).write(["20260916T060000Z"])  # pyright: ignore[reportPrivateUsage]
    return path


STATE_FILES = [
    pytest.param(write_the_pending_work_file, id="the pending-work file"),
    pytest.param(write_the_download_ledger, id="the download ledger"),
    pytest.param(write_the_delivery_record, id="the OpenEv delivery record"),
    pytest.param(write_a_run_summary, id="a run summary"),
    pytest.param(write_the_owed_records_file, id="the records still owed to the bucket"),
]


def record_what_the_operating_system_is_asked(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every `fsync` and every rename from here on, in order, as one line each."""
    asked: list[str] = []
    fsync, replace = os.fsync, os.replace

    def recording_fsync(descriptor: int) -> None:
        described = os.fstat(descriptor)
        if stat.S_ISDIR(described.st_mode):
            asked.append(f"fsync the directory {inode_of_directory(described.st_ino)}")
        else:
            asked.append(f"fsync a file of {described.st_size} bytes")
        fsync(descriptor)

    directories: dict[int, str] = {}

    def inode_of_directory(inode: int) -> str:
        return directories.get(inode, "<another directory>")

    def recording_replace(source: Path, destination: Path) -> None:
        source, destination = Path(source), Path(destination)
        directories[destination.parent.stat().st_ino] = "of the renamed file"
        where = "" if source.parent == destination.parent else " from another directory"
        asked.append(f"rename {source.name} to {destination.name}{where}")
        replace(source, destination)

    monkeypatch.setattr(os, "fsync", recording_fsync)
    monkeypatch.setattr(os, "replace", recording_replace)
    return asked


@pytest.mark.parametrize("write", STATE_FILES)
def test_a_state_file_is_flushed_and_fsynced_then_renamed_then_its_directory_is_fsynced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, write: Callable[[Path], Path]
) -> None:
    """Three calls, in this order and no other: the complete second file to the disk, the rename,
    the directory to the disk."""
    asked = record_what_the_operating_system_is_asked(monkeypatch)

    written = write(tmp_path)
    monkeypatch.undo()

    size = written.stat().st_size
    assert size > 0
    assert asked == [
        f"fsync a file of {size} bytes",
        f"rename .{written.name}.incoming to {written.name}",
        "fsync the directory of the renamed file",
    ]


def test_a_file_fsync_that_fails_surfaces_as_the_write_failing_and_the_file_keeps_what_it_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The disk will not take the second file. The error is the operating system's own, the same
    `OSError` a write that failed has always raised here, and the rename never happens: the
    pending-work file still says what it said."""
    path = write_the_pending_work_file(tmp_path)
    as_written = path.read_bytes()

    def no_fsync(_: int) -> None:
        raise OSError(errno.EIO, "Input/output error")

    monkeypatch.setattr(os, "fsync", no_fsync)
    with pytest.raises(OSError, match="Input/output error") as failed:
        PendingWork(path).write([PendingSnapshot("testcl26", "2026-09-08")])
    monkeypatch.undo()

    assert type(failed.value) is OSError
    assert failed.value.errno == errno.EIO
    assert path.read_bytes() == as_written
    assert PendingWork(path).read() == (PendingSnapshot("testcl26", "2026-09-01"),)


def test_a_directory_fsync_that_fails_surfaces_as_the_write_failing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second file is on the disk and has its name, and the directory will not be synced. That
    is still a write nobody can vouch for, so it is still the operating system's error."""
    path = write_the_pending_work_file(tmp_path)
    fsync = os.fsync

    def no_fsync_of_a_directory(descriptor: int) -> None:
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError(errno.EIO, "Input/output error")
        fsync(descriptor)

    monkeypatch.setattr(os, "fsync", no_fsync_of_a_directory)
    with pytest.raises(OSError, match="Input/output error") as failed:
        PendingWork(path).write([PendingSnapshot("testcl26", "2026-09-08")])
    monkeypatch.undo()

    assert type(failed.value) is OSError
    assert failed.value.errno == errno.EIO
    assert PendingWork(path).read() == (PendingSnapshot("testcl26", "2026-09-08"),)


# ------------------------------------------------------------------------------------------------
# `v1-e34-t23`: the two logs, and a state file removed
# ------------------------------------------------------------------------------------------------


def a_record(run_id: str) -> SyncRunRecord:
    return SyncRunRecord(
        run_id=run_id,
        environment="dev",
        mode="run",
        started_at=STARTED,
        finished_at=STARTED,
        outcome=sync_runs.SyncRunOutcome.COMPLETED,
    )


def append_to_the_run_log(directory: Path, run_id: str) -> Path:
    log = SyncRunLog(directory / "caselist-sync-runs.jsonl")
    log.append(a_record(run_id))
    return log.path


def append_to_the_run_details(directory: Path, run_id: str) -> Path:
    log = SyncRunDetailsLog(directory / "caselist-sync-run-details.jsonl")
    log.append(SyncRunDetails(run_id=run_id))
    return log.path


LOGS = [
    pytest.param(append_to_the_run_log, id="the run log"),
    pytest.param(append_to_the_run_details, id="the run details"),
]


def record_the_fsyncs_in(monkeypatch: pytest.MonkeyPatch, directory: Path) -> list[str]:
    """Every `fsync` from here on, in order: a file by the bytes it held then, `directory` by name."""
    asked: list[str] = []
    fsync = os.fsync
    directory_inode = directory.stat().st_ino

    def recording_fsync(descriptor: int) -> None:
        described = os.fstat(descriptor)
        if stat.S_ISDIR(described.st_mode):
            named = "its directory" if described.st_ino == directory_inode else "<another directory>"
            asked.append(f"fsync {named}")
        else:
            asked.append(f"fsync a file of {described.st_size} bytes")
        fsync(descriptor)

    monkeypatch.setattr(os, "fsync", recording_fsync)
    return asked


@pytest.mark.parametrize("append", LOGS)
def test_each_append_to_a_log_is_fsynced_and_then_its_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, append: Callable[[Path, str], Path]
) -> None:
    """Two runs, two lines. Each line is on the disk before the append returns: the file is fsynced
    holding it, and then the directory, which holds the file's name from the first append on."""
    asked = record_the_fsyncs_in(monkeypatch, tmp_path)

    log = append(tmp_path, "20260916T060000Z")
    after_one = log.stat().st_size
    append(tmp_path, "20260923T060000Z")
    monkeypatch.undo()

    after_two = log.stat().st_size
    assert 0 < after_one < after_two
    assert asked == [
        f"fsync a file of {after_one} bytes",
        "fsync its directory",
        f"fsync a file of {after_two} bytes",
        "fsync its directory",
    ]
    assert len(log.read_text("utf-8").splitlines()) == 2


@pytest.mark.parametrize("append", LOGS)
def test_an_append_whose_fsync_fails_surfaces_as_the_append_failing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, append: Callable[[Path, str], Path]
) -> None:
    """The disk will not take the line. The append raises the operating system's own error, as a
    write that failed always did here; the run monitor decides what that costs."""

    def no_fsync(_: int) -> None:
        raise OSError(errno.EIO, "Input/output error")

    monkeypatch.setattr(os, "fsync", no_fsync)
    with pytest.raises(OSError, match="Input/output error") as failed:
        append(tmp_path, "20260916T060000Z")
    monkeypatch.undo()

    assert type(failed.value) is OSError
    assert failed.value.errno == errno.EIO


def remove_the_pending_work_file(directory: Path) -> Path:
    path = write_the_pending_work_file(directory)
    PendingWork(path).write([])
    return path


def remove_the_owed_records_file(directory: Path) -> Path:
    path = write_the_owed_records_file(directory)
    sync_runs._PendingRecords(path).write([])  # pyright: ignore[reportPrivateUsage]
    return path


@pytest.mark.parametrize(
    "remove",
    [
        pytest.param(remove_the_pending_work_file, id="the pending-work file"),
        pytest.param(remove_the_owed_records_file, id="the records still owed to the bucket"),
    ],
)
def test_a_state_file_removed_because_nothing_is_owed_has_its_directory_fsynced_after(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, remove: Callable[[Path], Path]
) -> None:
    """Nothing owed any more: the file goes. Its name going is on the disk too, or a power cut
    brings back a file that owes what was published."""
    asked: list[str] = []
    fsync, unlink = os.fsync, Path.unlink

    def recording_fsync(descriptor: int) -> None:
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            asked.append("fsync the directory")
        fsync(descriptor)

    def recording_unlink(path: Path, missing_ok: bool = False) -> None:
        asked.append(f"remove {path.name}")
        unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(os, "fsync", recording_fsync)
    monkeypatch.setattr(Path, "unlink", recording_unlink)
    written = remove(tmp_path)
    monkeypatch.undo()

    # The write before the removal fsyncs its directory too; what matters is how the removal ends.
    assert not written.exists()
    assert asked[-2:] == [f"remove {written.name}", "fsync the directory"]
