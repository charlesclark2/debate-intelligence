"""The in-memory and filesystem blob stores are both held to the `SnapshotStore` contract.

Two bindings, one suite. Whatever this file proves about `InMemorySnapshotStore` it proves about
`FsSnapshotStore` in the same words, which is the property that lets a test wire the fake in and
still be testing the thing production runs.

The adapter-specific halves stay where they belong: where a blob lands on disk, that a write is
atomic, that a stored file is read-only, that a key cannot escape the store — those are in
`packages/debate_core/tests/integrations/local/test_fs_blob_store.py`.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from debate_core.application.ports import BlobKey
from debate_core.integrations.local import BLOB_FILE_MODE, FsSnapshotStore
from debate_core.testing.contracts import BlobCorruptor, SnapshotStoreContract, SnapshotStoreFactory
from debate_core.testing.fakes import InMemorySnapshotStore


class TestInMemorySnapshotStore(SnapshotStoreContract):
    """The fake every other package's tests wire in really is a `SnapshotStore`."""

    @pytest.fixture
    def make_adapter(self) -> SnapshotStoreFactory:
        """One dictionary, handed out as many times as the contract asks for a handle."""
        store = InMemorySnapshotStore()
        return lambda: store

    @pytest.fixture
    def corrupt_blob(self, make_adapter: SnapshotStoreFactory) -> BlobCorruptor:
        """The fake's own tamper hook, which exists for exactly this contract."""
        store = make_adapter()
        assert isinstance(store, InMemorySnapshotStore)
        return store.corrupt


class TestFsSnapshotStore(SnapshotStoreContract):
    """V1's real blob store: one directory under `tmp_path`, nothing else on the machine touched."""

    @pytest.fixture
    def make_adapter(self, tmp_path: Path) -> SnapshotStoreFactory:
        """Fresh handles onto one data directory, so two handles really are two views of one store."""
        return lambda: FsSnapshotStore(tmp_path)

    @pytest.fixture
    def corrupt_blob(self, make_adapter: SnapshotStoreFactory) -> BlobCorruptor:
        """Rewrite a blob's file in place, which is the damage a bad disk or a bad actor does.

        Stored blobs are created read-only (:data:`~debate_core.integrations.local.BLOB_FILE_MODE`),
        so the file has to be made writable first and is put back afterwards — the contract must
        find the store exactly as production leaves it, apart from the altered bytes.
        """
        store = make_adapter()
        assert isinstance(store, FsSnapshotStore)

        def rewrite(key: BlobKey, replacement: bytes) -> None:
            path = store.path_for(key)
            path.chmod(0o644)
            path.write_bytes(replacement)
            os.chmod(path, BLOB_FILE_MODE)

        return rewrite
