"""The S3 adapters: the evidence store as the cloud holds it. **The only place boto3 is imported.**

This package is the whole of the platform's AWS surface for evidence. `debate_core.domain` and
`debate_core.application` may not import boto3 or botocore, an import-linter contract in the workspace
root enforces it, and every failure botocore raises is translated at this package's edge
(:mod:`debate_core.integrations.s3.errors`) so that no `ClientError` reaches a use case
(architecture proposal §6, ADR-0003).

Two adapters, matching the two shapes evidence comes in:

* :class:`~debate_core.integrations.s3.snapshot_store.S3SnapshotStore` —
  :class:`~debate_core.application.ports.persistence.SnapshotStore` over content-addressed,
  write-once keys. The system of record, and the bucket-side twin of
  :class:`~debate_core.integrations.local.FsSnapshotStore`.
* :class:`~debate_core.integrations.s3.object_store.S3EvidenceObjectStore` —
  :class:`~debate_core.application.ports.evidence_store.EvidenceObjectStore` over objects with names:
  `manifests/*.jsonl`, `reports/*`.

## Wiring

No adapter here reads settings, resolves `DEBATE_ENV` or knows a bucket name. The composition root
passes the coordinates in, and `v1-e29-t05-evidence-sync-cli` is what reads them per environment from
the environment root's Terraform outputs — `evidence_bucket_name` and `evidence_kms_key_arn` in
`infrastructure/envs/<env>/outputs.tf` — rather than from a name typed into Python::

    client = build_s3_client(region=settings.storage.s3.region, profile=settings.storage.s3.aws_profile)
    blobs = S3SnapshotStore(bucket=bucket, prefix="raw/caselist/hsld26", client=client)
    objects = S3EvidenceObjectStore(bucket=bucket, client=client)

One client shared by both adapters is the usual arrangement: it is one set of credentials, one
connection pool and one profile named in any `aws sso login` hint.

## Installing it

boto3 is an optional dependency of `debate-core`, under the `aws` extra, because the V1 CLI running
against a local evidence directory has no use for an AWS SDK. Importing this package without it raises
immediately, with the command that fixes it.
"""

from __future__ import annotations

import importlib.util

# Checked before the adapters are imported, so that a missing optional dependency arrives as the
# command that installs it rather than as `No module named 'boto3'` from somewhere inside an adapter.
if importlib.util.find_spec("boto3") is None:  # pragma: no cover - depends on how this was installed
    raise ModuleNotFoundError(
        "debate_core.integrations.s3 needs boto3, which is an optional dependency of debate-core: "
        "install it with `uv sync --extra aws` (or `pip install 'debate-core[aws]'`)."
    )

from debate_core.integrations.s3.client import (
    DEFAULT_MULTIPART_PART_SIZE_BYTES,
    DEFAULT_MULTIPART_THRESHOLD_BYTES,
    MINIMUM_PART_SIZE_BYTES,
    build_s3_client,
    build_transfer_config,
)
from debate_core.integrations.s3.errors import S3Call, mapped_s3_errors, translate_s3_error
from debate_core.integrations.s3.object_store import S3EvidenceObjectStore
from debate_core.integrations.s3.snapshot_store import (
    BLOB_KEY_SEGMENT,
    SHA256_METADATA_NAME,
    S3SnapshotStore,
)

__all__ = [
    "BLOB_KEY_SEGMENT",
    "DEFAULT_MULTIPART_PART_SIZE_BYTES",
    "DEFAULT_MULTIPART_THRESHOLD_BYTES",
    "MINIMUM_PART_SIZE_BYTES",
    "SHA256_METADATA_NAME",
    "S3Call",
    "S3EvidenceObjectStore",
    "S3SnapshotStore",
    "build_s3_client",
    "build_transfer_config",
    "mapped_s3_errors",
    "translate_s3_error",
]
