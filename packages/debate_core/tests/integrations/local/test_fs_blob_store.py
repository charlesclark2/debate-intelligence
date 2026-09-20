"""The filesystem blob store really deduplicates, really writes atomically, and really catches tampering.

These are the adapter-specific tests: the things that are true of *this* store because it is made
of files — where a blob lands, that a write leaves nothing half-finished, that a stored blob is
read-only, that a key cannot name a file outside the store. The behaviour every `SnapshotStore`
shares with every other one is checked by the contract suite in v1-e02-t04-repo-contract-tests.

Everything runs under `tmp_path`. Nothing here touches a real data directory, a bucket or the
network.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, cast

import pytest

from debate_core.application.errors import BlobIntegrityError, NotFound
from debate_core.integrations.local import BLOB_DIRECTORY, BLOB_FILE_MODE, FsSnapshotStore
from debate_core.integrations.local.fs_blob_store import TEMPORARY_FILE_PREFIX

RAW_HTML = b"<html><body><p>Arctic methane release is accelerating.</p></body></html>"
OTHER_HTML = b"<html><body><p>A different source entirely.</p></body></html>"


def run[ResultT](coroutine: Coroutine[Any, Any, ResultT]) -> ResultT:
    """Drive one of the store's coroutines to completion without an event loop.

    The same driver `debate_core.testing.fakes`' tests use, and for the same two reasons. This
    adapter does its file I/O synchronously and never awaits, so one `send(None)` runs a call to
    completion; and `asyncio.run` is unavailable here because an event loop builds its self-pipe
    from `socket.socketpair()`, which the suite's `--disable-socket` refuses.

    It doubles as an assertion. If a call ever does suspend, this raises rather than quietly
    returning `None`, which is what would happen if these adapters grew a thread hop without the
    async test plugin that v1-e02-t04-repo-contract-tests is expected to bring.
    """
    try:
        coroutine.send(None)
    except StopIteration as finished:
        return cast("ResultT", finished.value)
    coroutine.close()
    raise AssertionError("a local adapter suspended; it is expected to do its I/O synchronously")


def digest_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def store(tmp_path: Path) -> FsSnapshotStore:
    return FsSnapshotStore(tmp_path)


def temporary_files(root: Path) -> list[Path]:
    """Every leftover partial write under the store, which should always be none."""
    return sorted(root.rglob(f"{TEMPORARY_FILE_PREFIX}*"))


# --------------------------------------------------------------------------------------------
# Keys and layout
# --------------------------------------------------------------------------------------------


def test_put_returns_the_sha256_of_the_content(store: FsSnapshotStore) -> None:
    assert run(store.put(RAW_HTML)) == digest_of(RAW_HTML)


def test_blob_lands_under_the_two_level_sha256_fan_out(store: FsSnapshotStore, tmp_path: Path) -> None:
    key = run(store.put(RAW_HTML))

    expected = tmp_path / BLOB_DIRECTORY / key[0:2] / key[2:4] / key
    assert expected.is_file()
    assert expected.read_bytes() == RAW_HTML
    assert store.path_for(key) == expected


def test_the_store_is_confined_to_the_data_directory(tmp_path: Path) -> None:
    store = FsSnapshotStore(tmp_path / "environment")
    run(store.put(RAW_HTML))

    assert store.root == tmp_path / "environment" / BLOB_DIRECTORY
    assert sorted(path.name for path in tmp_path.iterdir()) == ["environment"]


def test_data_directory_is_created_lazily(tmp_path: Path) -> None:
    unwritten = tmp_path / "never-used"
    FsSnapshotStore(unwritten)

    assert not unwritten.exists()


def test_a_key_that_is_not_a_digest_cannot_name_a_file(store: FsSnapshotStore) -> None:
    for malformed in ("../../etc/passwd", "", "not-hex", digest_of(RAW_HTML).upper()):
        with pytest.raises(ValueError, match="not a blob key"):
            store.path_for(malformed)
        assert run(store.exists(malformed)) is False
        with pytest.raises(NotFound):
            run(store.get(malformed))


# --------------------------------------------------------------------------------------------
# Deduplication and idempotent writes
# --------------------------------------------------------------------------------------------


def test_identical_content_is_stored_once(store: FsSnapshotStore) -> None:
    first = run(store.put(RAW_HTML))
    stored = store.path_for(first).stat()
    tree = _tree_of(store.root)

    second = run(store.put(RAW_HTML))

    assert second == first
    # A rewrite would go through a new temp file and a rename, so the inode would change.
    assert store.path_for(first).stat().st_ino == stored.st_ino
    assert _tree_of(store.root) == tree


def test_different_content_gets_different_keys(store: FsSnapshotStore) -> None:
    first = run(store.put(RAW_HTML))
    second = run(store.put(OTHER_HTML))

    assert first != second
    assert run(store.get(first)) == RAW_HTML
    assert run(store.get(second)) == OTHER_HTML


def test_empty_content_is_a_blob_like_any_other(store: FsSnapshotStore) -> None:
    key = run(store.put(b""))

    assert key == digest_of(b"")
    assert run(store.get(key)) == b""
    assert run(store.exists(key)) is True


def test_bytes_survive_the_round_trip_exactly(store: FsSnapshotStore) -> None:
    awkward = bytes(range(256)) + "text with a BOM ﻿ and \r\n line endings".encode()

    assert run(store.get(run(store.put(awkward)))) == awkward


# --------------------------------------------------------------------------------------------
# Atomicity and immutability
# --------------------------------------------------------------------------------------------


def test_a_completed_write_leaves_no_temporary_file(store: FsSnapshotStore) -> None:
    run(store.put(RAW_HTML))

    assert temporary_files(store.root) == []


def test_a_stored_blob_is_read_only(store: FsSnapshotStore) -> None:
    key = run(store.put(RAW_HTML))

    mode = store.path_for(key).stat().st_mode & 0o777
    assert mode == BLOB_FILE_MODE
    with pytest.raises(PermissionError):
        store.path_for(key).open("wb")


def test_a_failed_rename_stores_nothing_and_cleans_up(
    store: FsSnapshotStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(source: object, destination: object) -> None:
        raise OSError("the disk filled up mid-write")

    monkeypatch.setattr(os, "replace", fail)

    with pytest.raises(OSError, match="the disk filled up"):
        run(store.put(RAW_HTML))

    monkeypatch.undo()
    key = digest_of(RAW_HTML)
    assert run(store.exists(key)) is False
    assert temporary_files(store.root) == []


def test_a_retried_write_after_a_failure_succeeds(
    store: FsSnapshotStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(source: object, destination: object) -> None:
        raise OSError("interrupted")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError, match="interrupted"):
        run(store.put(RAW_HTML))
    monkeypatch.undo()

    assert run(store.get(run(store.put(RAW_HTML)))) == RAW_HTML


# --------------------------------------------------------------------------------------------
# Reading, absence and corruption
# --------------------------------------------------------------------------------------------


def test_get_reports_a_key_that_was_never_written(store: FsSnapshotStore) -> None:
    missing = digest_of(b"never stored")

    with pytest.raises(NotFound) as caught:
        run(store.get(missing))

    assert caught.value.entity == "snapshot blob"
    assert caught.value.key == missing


def test_exists_answers_without_reading_the_blob(store: FsSnapshotStore) -> None:
    key = run(store.put(RAW_HTML))
    _corrupt(store, key, b"tampered")

    assert run(store.exists(key)) is True
    assert run(store.exists(digest_of(b"never stored"))) is False


def test_a_tampered_blob_is_reported_not_returned(store: FsSnapshotStore) -> None:
    key = run(store.put(RAW_HTML))
    tampered = b"<html><body><p>Arctic methane release is slowing.</p></body></html>"
    _corrupt(store, key, tampered)

    with pytest.raises(BlobIntegrityError) as caught:
        run(store.get(key))

    assert caught.value.key == key
    assert caught.value.actual_sha256 == digest_of(tampered)
    # The bytes are never handed back, however plausible they look.
    assert tampered not in str(caught.value).encode()


def test_a_truncated_blob_is_reported(store: FsSnapshotStore) -> None:
    key = run(store.put(RAW_HTML))
    _corrupt(store, key, RAW_HTML[:20])

    with pytest.raises(BlobIntegrityError):
        run(store.get(key))


# --------------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------------


def _corrupt(store: FsSnapshotStore, key: str, replacement: bytes) -> None:
    """Rewrite a stored blob's bytes without changing its key, to prove the check fires.

    Deliberately has to defeat the read-only mode to do it, which is the point: nothing short of
    an operator or a failing disk can put a store into this state.
    """
    path = store.path_for(key)
    path.chmod(0o644)
    path.write_bytes(replacement)
    path.chmod(BLOB_FILE_MODE)


def _tree_of(root: Path) -> list[Path]:
    """Every path under `root`, for asserting that a second write of the same bytes added nothing."""
    return sorted(root.rglob("*"))
