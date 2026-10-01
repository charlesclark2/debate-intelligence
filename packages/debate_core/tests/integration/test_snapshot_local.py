"""SnapshotService over V1's real blob store: deduplication and tamper detection on actual files.

The unit tests in `tests/application/test_snapshot_service.py` use in-memory stores. These run the
same service against `FsSnapshotStore` in `tmp_path`, so "one stored copy" is counted in files on
disk and "tampering" is a rewritten file, which is what a bad disk or a bad actor would produce. No
directory outside `tmp_path` is touched.

The source is invented. Expected hashes are SHA-256 of byte strings written out by hand.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Coroutine
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

from debate_core.application.errors import (
    BlobIntegrityError,
    NotFound,
    SnapshotIntegrityCheck,
    SnapshotIntegrityError,
)
from debate_core.application.snapshot_service import SnapshotService
from debate_core.domain import AccessStatus, ProvenanceMode, SourceSnapshot
from debate_core.integrations.local import BLOB_FILE_MODE, FsSnapshotStore
from debate_core.testing import FixedClock, SequentialIdGenerator

RAW = b"<html><body><p>Glacier retreat doubled.</p>\r\n<p>Sea ice\xc2\xa0thinned.</p></body></html>"
EXTRACTED = "Glacier retreat doubled.\r\n\r\nSea ice\u00a0thinned."
#: "Glacier retreat doubled." is 24 characters; the break takes 24-26; "Sea ice thinned." is 16.
DOCUMENT = (
    b'{"format":"debate-snapshot-text/1","normalizer_version":"evidence-normalizer-v1",'
    b'"paragraphs":[{"end":24,"id":"p0001","start":0},{"end":42,"id":"p0002","start":26}],'
    b'"text":"Glacier retreat doubled.\\n\\nSea ice thinned."}'
)
NORMALIZED_TEXT_SHA256 = hashlib.sha256(b"Glacier retreat doubled.\n\nSea ice thinned.").hexdigest()


def run[ResultT](coroutine: Coroutine[Any, Any, ResultT]) -> ResultT:
    """Drive one coroutine to completion; the filesystem store does its I/O synchronously."""
    try:
        coroutine.send(None)
    except StopIteration as stopped:
        return cast("ResultT", stopped.value)
    coroutine.close()
    raise AssertionError("the filesystem store suspended; it is expected to complete synchronously")


def service_over(data_dir: Path) -> SnapshotService:
    """A service over a fresh store handle on `data_dir`, as a new process would build one."""
    return SnapshotService(
        blobs=FsSnapshotStore(data_dir),
        clock=FixedClock(step=timedelta(minutes=1)),
        id_generator=SequentialIdGenerator("SNAP"),
    )


def create(service: SnapshotService, raw: bytes = RAW) -> SourceSnapshot:
    return run(
        service.create(
            article_id="0ART0000000000000000000001",
            raw_bytes=raw,
            extracted_text=EXTRACTED,
            canonical_url="https://example.org/climate/glaciers",
            retrieved_at=datetime(2026, 9, 30, 12, 0, tzinfo=UTC),
            extractor_version="fake-extractor/1.0",
            provenance_mode=ProvenanceMode.PUBLISHER_RETRIEVED,
            access_status=AccessStatus.ACCESSIBLE,
        )
    )


def stored_files(data_dir: Path) -> list[Path]:
    """Every regular file the store holds, leftover temp files included."""
    return sorted(path for path in FsSnapshotStore(data_dir).root.rglob("*") if path.is_file())


def rewrite_blob_file(data_dir: Path, key: str, replacement: bytes) -> None:
    """Change a stored blob's bytes in place, past its read-only mode, and put the mode back."""
    path = FsSnapshotStore(data_dir).path_for(key)
    path.chmod(0o644)
    path.write_bytes(replacement)
    os.chmod(path, BLOB_FILE_MODE)


def test_a_snapshot_created_on_disk_loads_back_through_a_fresh_store_handle(tmp_path: Path) -> None:
    snapshot = create(service_over(tmp_path))

    loaded = run(service_over(tmp_path).load(snapshot))

    assert loaded.raw_bytes == RAW
    assert loaded.normalized.text == "Glacier retreat doubled.\n\nSea ice thinned."
    assert snapshot.normalized_text_hash == NORMALIZED_TEXT_SHA256


def test_the_two_blob_files_hold_the_raw_bytes_and_the_hand_written_document(tmp_path: Path) -> None:
    snapshot = create(service_over(tmp_path))
    store = FsSnapshotStore(tmp_path)

    assert store.path_for(snapshot.raw_blob_key).read_bytes() == RAW
    assert store.path_for(snapshot.normalized_blob_key).read_bytes() == DOCUMENT
    assert snapshot.normalized_blob_key == hashlib.sha256(DOCUMENT).hexdigest()
    assert stored_files(tmp_path) == sorted(
        [store.path_for(snapshot.raw_blob_key), store.path_for(snapshot.normalized_blob_key)]
    )


def test_creating_the_same_snapshot_twice_writes_two_files_once_and_never_rewrites_them(
    tmp_path: Path,
) -> None:
    """ac3 on disk: identical hashes, one file per blob, and the second create leaves both untouched."""
    first = create(service_over(tmp_path))
    before = {path: (path.stat().st_ino, path.stat().st_mtime_ns) for path in stored_files(tmp_path)}

    second = create(service_over(tmp_path))

    assert (first.sha256, first.normalized_text_hash) == (second.sha256, second.normalized_text_hash)
    assert len(before) == 2
    assert {path: (path.stat().st_ino, path.stat().st_mtime_ns) for path in stored_files(tmp_path)} == before
    assert all(path.stat().st_mode & 0o777 == BLOB_FILE_MODE for path in before)


def test_a_re_served_page_adds_one_raw_file_and_shares_the_normalized_file(tmp_path: Path) -> None:
    create(service_over(tmp_path))
    create(service_over(tmp_path), raw=RAW.replace(b"<body>", b"<body><!-- cached -->"))

    assert len(stored_files(tmp_path)) == 3


@pytest.mark.parametrize(
    ("which_blob", "expected_check"),
    [
        pytest.param("raw_blob_key", SnapshotIntegrityCheck.RAW_BYTES_HASH, id="raw"),
        pytest.param("normalized_blob_key", SnapshotIntegrityCheck.NORMALIZED_BLOB_HASH, id="normalized"),
    ],
)
def test_a_blob_file_rewritten_on_disk_fails_its_integrity_check_on_load(
    tmp_path: Path, which_blob: str, expected_check: SnapshotIntegrityCheck
) -> None:
    snapshot = create(service_over(tmp_path))
    key = getattr(snapshot, which_blob)
    original = FsSnapshotStore(tmp_path).path_for(key).read_bytes()
    rewrite_blob_file(tmp_path, key, original.replace(b"doubled", b"halved."))

    with pytest.raises(SnapshotIntegrityError) as refused:
        run(service_over(tmp_path).load(snapshot))

    assert refused.value.check is expected_check
    assert isinstance(refused.value.__cause__, BlobIntegrityError)


def test_a_blob_file_swapped_for_another_valid_blob_fails_its_integrity_check(tmp_path: Path) -> None:
    """The replacement is a perfectly good blob, just not the one this key names."""
    snapshot = create(service_over(tmp_path))
    rewrite_blob_file(tmp_path, snapshot.raw_blob_key, b"<p>An unrelated page.</p>")

    with pytest.raises(SnapshotIntegrityError) as refused:
        run(service_over(tmp_path).load(snapshot))

    assert refused.value.check is SnapshotIntegrityCheck.RAW_BYTES_HASH


def test_a_deleted_blob_file_is_reported_missing_not_damaged(tmp_path: Path) -> None:
    snapshot = create(service_over(tmp_path))
    FsSnapshotStore(tmp_path).path_for(snapshot.normalized_blob_key).unlink()

    with pytest.raises(NotFound):
        run(service_over(tmp_path).load(snapshot))
