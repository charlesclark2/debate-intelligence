"""The S3 and filesystem object stores are both held to the `EvidenceObjectStore` contract.

Two bindings, one suite. Whatever this file proves about `S3EvidenceObjectStore` against a moto bucket
it proves about `FsEvidenceObjectStore` against a directory, in the same words — which is what lets
`v1-e29-t05-evidence-sync-cli` be one diff over two of these rather than two code paths that have to
be kept in step (`v1-e29-t04` ac4).

Each binding's `make_adapter` is annotated as returning the port's type, and that annotation is where
pyright checks that the adapter really satisfies `EvidenceObjectStore`: the port is a Protocol, so
nothing else in the codebase would notice a signature drifting.

The adapter-specific halves stay where they belong: which S3 key an object lands under, what the local
store does with a leftover download, that a listing skips partial writes. Those are in
`packages/debate_core/tests/integrations/`.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from debate_core.application.ports import EvidenceObjectStore
from debate_core.integrations.local import FsEvidenceObjectStore
from debate_core.integrations.s3 import S3EvidenceObjectStore
from debate_core.testing.contracts import EvidenceObjectStoreContract, EvidenceObjectStoreFactory

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client


class TestS3EvidenceObjectStore(EvidenceObjectStoreContract):
    """The bucket store, against moto. The `evidence_bucket` fixture is in `tests/conftest.py`."""

    @pytest.fixture
    def make_adapter(self, evidence_bucket: str, s3_client: S3Client) -> EvidenceObjectStoreFactory:
        """Fresh handles onto one bucket, so two handles really are two views of one store."""

        def open_store() -> EvidenceObjectStore:
            return S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client)

        return open_store


class TestFsEvidenceObjectStore(EvidenceObjectStoreContract):
    """The local store: one directory under `tmp_path`, nothing else on the machine touched."""

    @pytest.fixture
    def make_adapter(self, tmp_path: Path) -> EvidenceObjectStoreFactory:
        """Fresh handles onto one data directory, which does not exist until something is written."""
        data_dir = tmp_path / "evidence"

        def open_store() -> EvidenceObjectStore:
            return FsEvidenceObjectStore(data_dir)

        return open_store
