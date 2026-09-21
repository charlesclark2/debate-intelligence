"""Building the one S3 client the adapters in this package share, and the transfer settings.

Two things live here because both adapters need them and neither should own them: how a client is
built from a region and a profile, and how big a file has to be before it is uploaded in parts.

## Credentials

Nothing in this package reads a key or a token. :func:`build_s3_client` names a profile and a region
and leaves the rest to botocore's standard credential chain, so the same adapter runs against an
AWS SSO session on a laptop (`aws sso login --profile debate-dev-evidence`) and against an instance
or task role in the cloud, with no branch in our code and no long-lived access key anywhere
(`v1-e29-t01-aws-account-baseline`, ADR-0010).

A caller that passes no profile gets the chain's own answer, which is what `AWS_PROFILE` and a role
on an EC2 instance or an ECS task are for.

## Which bucket

:func:`build_s3_client` does not know and must not guess. The bucket name and the KMS key ARN come
from the environment root's Terraform outputs — `evidence_bucket_name` and `evidence_kms_key_arn`
in `infrastructure/envs/<env>/outputs.tf` — and reach an adapter through its constructor;
`v1-e29-t05-evidence-sync-cli` is what resolves them per `DEBATE_ENV` and passes them in. An
adapter with a bucket name compiled into it would be an adapter that writes dev evidence into prod
the first time someone copied a line.

## Thread safety

Both adapters do their blocking S3 work in a worker thread (`asyncio.to_thread`) and share one
client across those threads, which is supported: a botocore client is safe to *call* from several
threads once it has been created. Creating one is not thread-safe, which is why it happens once, in
a constructor, and never inside a request.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import boto3
from boto3.s3.transfer import TransferConfig

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

__all__ = [
    "DEFAULT_MULTIPART_PART_SIZE_BYTES",
    "DEFAULT_MULTIPART_THRESHOLD_BYTES",
    "MINIMUM_PART_SIZE_BYTES",
    "build_s3_client",
    "build_transfer_config",
]

DEFAULT_MULTIPART_THRESHOLD_BYTES = 64 * 1024 * 1024
"""Above this size, an upload or download is split into parts. 64 MiB.

Higher than boto3's own 8 MiB default, deliberately. Almost everything in the evidence store is a
disclosed file of a few hundred kilobytes, where a multipart upload is three requests instead of
one and a composite checksum instead of a plain one. The files that are genuinely big are camp
archives and season dumps, and those are far above 64 MiB. Configurable per adapter because a
future backfill running on a small instance may want smaller parts.
"""

DEFAULT_MULTIPART_PART_SIZE_BYTES = 16 * 1024 * 1024
"""Size of each part of a multipart transfer. 16 MiB.

S3 allows 10,000 parts, so this puts the largest uploadable object at 160 GiB — far beyond anything
the store will hold — while keeping a retried part small enough that losing one is cheap.
"""

MINIMUM_PART_SIZE_BYTES = 5 * 1024 * 1024
"""S3's own floor on every part but the last: 5 MiB.

Checked when an adapter is constructed rather than discovered when an upload fails halfway through a
120-gigabyte archive.
"""


def build_s3_client(*, region: str | None = None, profile: str | None = None) -> S3Client:
    """Return an S3 client for `region`, using `profile` from the shared AWS config when given.

    A new :class:`boto3.session.Session` per call rather than the module-level default session, so
    that two adapters built for two profiles — an everyday one and the takedown one from
    `docs/runbooks/caselist-removal.md` — cannot end up sharing credentials because one of them was
    constructed second.

    Raises :class:`~debate_core.application.errors.StoreCredentialsExpired` through
    :func:`~debate_core.integrations.s3.errors.mapped_s3_errors` at the adapter's first call, not
    here: botocore resolves credentials lazily, so a missing profile or an expired session surfaces
    when something is actually asked of the store.
    """
    session = boto3.session.Session(profile_name=profile, region_name=region)
    return session.client("s3")


def build_transfer_config(
    *,
    multipart_threshold_bytes: int = DEFAULT_MULTIPART_THRESHOLD_BYTES,
    multipart_part_size_bytes: int = DEFAULT_MULTIPART_PART_SIZE_BYTES,
) -> TransferConfig:
    """Return the boto3 transfer settings for one adapter, after checking they are usable.

    Raises :class:`ValueError` when a part size is below S3's own 5 MiB minimum
    (:data:`MINIMUM_PART_SIZE_BYTES`) or when either size is not positive. A threshold *below* the
    part size is allowed and means "use a multipart transfer for anything over the threshold, in one
    part if that is all it takes", which is exactly how the multipart tests keep a fixture small.
    """
    if multipart_threshold_bytes <= 0:
        raise ValueError(f"multipart threshold must be positive: {multipart_threshold_bytes}")
    if multipart_part_size_bytes < MINIMUM_PART_SIZE_BYTES:
        raise ValueError(
            f"multipart part size must be at least S3's minimum of {MINIMUM_PART_SIZE_BYTES} bytes: "
            f"{multipart_part_size_bytes}"
        )
    return TransferConfig(
        multipart_threshold=multipart_threshold_bytes,
        multipart_chunksize=multipart_part_size_bytes,
    )
