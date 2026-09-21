"""What `FsEvidenceObjectStore` does that the shared contract does not ask about.

The contract (`tests/contracts/test_evidence_object_store_contract.py`) covers what a caller may assume
of either implementation. This module covers the directory-shaped half: where a file lands, that the
store is contained inside its data directory, that a leftover from an interrupted download is not
mistaken for an object, and that named objects and content-addressed blobs share a data directory
without sharing keys.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from debate_core.integrations.file_streaming import INCOMING_FILE_PREFIX
from debate_core.integrations.local import (
    BLOB_DIRECTORY,
    OBJECT_DIRECTORY,
    FsEvidenceObjectStore,
    FsSnapshotStore,
)

pytestmark = pytest.mark.anyio

MANIFEST_KEY = "manifests/hsld26/2026-09-15.jsonl"
MANIFEST_ROW = b'{"sha256":"5e88489","bytes":48213,"content_type":"application/pdf"}\n'


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "evidence"


@pytest.fixture
def store(data_dir: Path) -> FsEvidenceObjectStore:
    return FsEvidenceObjectStore(data_dir)


@pytest.fixture
def manifest_file(tmp_path: Path) -> Path:
    source = tmp_path / "2026-09-15.jsonl"
    source.write_bytes(MANIFEST_ROW)
    return source


class TestWhereAnObjectLandsOnDisk:
    async def test_the_key_becomes_a_path_under_the_object_directory(
        self, store: FsEvidenceObjectStore, manifest_file: Path, data_dir: Path
    ) -> None:
        """The key is the path, so a synced directory and a synced bucket look the same."""
        await store.put_file(MANIFEST_KEY, manifest_file)

        assert (data_dir / OBJECT_DIRECTORY / "manifests/hsld26/2026-09-15.jsonl").read_bytes() == (
            MANIFEST_ROW
        )
        assert store.path_for(MANIFEST_KEY) == data_dir / OBJECT_DIRECTORY / MANIFEST_KEY

    async def test_the_store_creates_nothing_until_something_is_written(self, data_dir: Path) -> None:
        """A CLI command builds a store whether or not it writes; inspecting must not make a tree."""
        store = FsEvidenceObjectStore(data_dir)

        assert await store.list_objects("") == ()
        assert not data_dir.exists()

    async def test_named_objects_and_content_addressed_blobs_do_not_share_keys(
        self, data_dir: Path, manifest_file: Path
    ) -> None:
        """One data directory holds both stores, and neither can reach into the other's keys."""
        objects = FsEvidenceObjectStore(data_dir)
        blobs = FsSnapshotStore(data_dir)

        await objects.put_file(MANIFEST_KEY, manifest_file)
        blob_key = await blobs.put(MANIFEST_ROW)

        assert objects.root == data_dir / OBJECT_DIRECTORY
        assert blobs.root == data_dir / BLOB_DIRECTORY
        assert blobs.path_for(blob_key).is_relative_to(data_dir / BLOB_DIRECTORY)
        assert await objects.list_objects("") == (await objects.list_objects("manifests/"))


class TestContainment:
    @pytest.mark.parametrize(
        "escaping_key",
        ["../outside.jsonl", "manifests/../../outside.jsonl", "/etc/passwd", "manifests/./x.jsonl"],
        ids=["parent", "parent-mid-key", "absolute", "dot-segment"],
    )
    async def test_a_key_that_could_name_a_file_outside_the_store_is_refused(
        self, store: FsEvidenceObjectStore, escaping_key: str
    ) -> None:
        """The traversal guard, checked before a path is built rather than after."""
        with pytest.raises(ValueError):
            store.path_for(escaping_key)

    async def test_a_symlink_out_of_the_store_is_not_followed(
        self, store: FsEvidenceObjectStore, data_dir: Path, tmp_path: Path
    ) -> None:
        """A validated key cannot escape, but a symlinked directory inside the store could.

        So the resolved path is checked against the root as well, and a key whose directory leads
        outside is refused rather than written through.
        """
        outside = tmp_path / "outside"
        outside.mkdir()
        escape = data_dir / OBJECT_DIRECTORY / "manifests"
        escape.parent.mkdir(parents=True, exist_ok=True)
        escape.symlink_to(outside, target_is_directory=True)

        with pytest.raises(ValueError, match="outside the store"):
            store.path_for(MANIFEST_KEY)


class TestWhatALeftoverDownloadLooksLike:
    async def test_a_partial_download_is_not_listed_as_an_object(
        self, store: FsEvidenceObjectStore, manifest_file: Path, data_dir: Path
    ) -> None:
        """A sync that treated one as an object would try to upload half a file."""
        await store.put_file(MANIFEST_KEY, manifest_file)
        leftover = data_dir / OBJECT_DIRECTORY / "manifests" / f"{INCOMING_FILE_PREFIX}abc123.tmp"
        leftover.write_bytes(b"half a manifest")

        listed = await store.list_objects("")

        assert [found.key for found in listed] == [MANIFEST_KEY]

    async def test_a_directory_is_not_listed_as_an_object(
        self, store: FsEvidenceObjectStore, manifest_file: Path, data_dir: Path
    ) -> None:
        await store.put_file(MANIFEST_KEY, manifest_file)
        (data_dir / OBJECT_DIRECTORY / "reports").mkdir(parents=True, exist_ok=True)

        assert [found.key for found in await store.list_objects("")] == [MANIFEST_KEY]


class TestWritesAreAtomic:
    async def test_a_replaced_object_leaves_no_temporary_file_behind(
        self, store: FsEvidenceObjectStore, manifest_file: Path, data_dir: Path
    ) -> None:
        await store.put_file(MANIFEST_KEY, manifest_file)
        await store.put_file(MANIFEST_KEY, manifest_file)

        directory = data_dir / OBJECT_DIRECTORY / "manifests" / "hsld26"
        assert [path.name for path in directory.iterdir()] == ["2026-09-15.jsonl"]

    async def test_a_download_to_a_path_inside_the_store_is_still_atomic(
        self, store: FsEvidenceObjectStore, manifest_file: Path, tmp_path: Path
    ) -> None:
        """`get_file` is how a sync pulls from the bucket into this directory; it must not litter."""
        await store.put_file(MANIFEST_KEY, manifest_file)
        destination = tmp_path / "pulled" / "2026-09-15.jsonl"

        got = await store.get_file(MANIFEST_KEY, destination)

        assert got.size == len(MANIFEST_ROW)
        assert [path.name for path in destination.parent.iterdir()] == ["2026-09-15.jsonl"]
