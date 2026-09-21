"""Named evidence objects in S3: manifests, reports, built files.

The bucket implementation of
:class:`~debate_core.application.ports.evidence_store.EvidenceObjectStore`, the smaller and less
careful of the two evidence ports — see that module for why a manifest is named rather than
content-addressed, and why this one is allowed to overwrite while
:class:`~debate_core.integrations.s3.S3SnapshotStore` is not.

An object's key here is the key, unchanged: `manifests/hsld26/2026-09-15.jsonl` is that key in the
bucket and that path under the local evidence directory
(:class:`~debate_core.integrations.local.FsEvidenceObjectStore`). There is no prefix argument and no
rewriting, because `v1-e29-t05-evidence-sync-cli` diffs the two stores by key: a store that quietly
prepended something would make every key on one side look new on the other.

## Digests

Every upload records the full-object SHA-256 in object metadata
(:data:`~debate_core.integrations.s3.snapshot_store.SHA256_METADATA_NAME`) and carries S3's own
SHA-256 checksum so that S3 refuses bytes that arrived damaged. A `HeadObject` can then state the
digest without downloading the object, which is what makes a sync diff affordable.

An object with no recorded digest heads as `sha256=None` rather than as an error. Something else put
it there — a console upload, an earlier tool — and the honest answer is "you will have to read it to
find out", which `v1-e29-t05` treats as changed.

## Blocking calls in `async def`

As in the snapshot store, every S3 call runs in a worker thread through :func:`asyncio.to_thread`, so
a network round trip does not block the event loop. `list_objects` walks every page of the listing
inside one such call: the caller asked for the whole listing, and paging it across threads would not
make it arrive sooner.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

from debate_core.application.errors import BlobIntegrityError, NotFound
from debate_core.application.ports.evidence_store import (
    ObjectInfo,
    ObjectKey,
    validate_object_key,
)
from debate_core.domain import Sha256Hex
from debate_core.integrations.file_streaming import atomic_replacement, sha256_of_file
from debate_core.integrations.s3.client import (
    DEFAULT_MULTIPART_PART_SIZE_BYTES,
    DEFAULT_MULTIPART_THRESHOLD_BYTES,
    build_s3_client,
    build_transfer_config,
)
from debate_core.integrations.s3.errors import S3Call, mapped_s3_errors
from debate_core.integrations.s3.snapshot_store import SHA256_METADATA_NAME

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

__all__ = ["S3EvidenceObjectStore"]

#: The name `NotFound` reports, matching the filesystem implementation's wording.
_ENTITY = "evidence object"


class S3EvidenceObjectStore:
    """An :class:`~debate_core.application.ports.evidence_store.EvidenceObjectStore` on an S3 bucket.

    Conforms structurally and does not subclass the port, like every other adapter in this codebase:
    a :class:`~typing.Protocol` an adapter inherits from is a dependency the adapter has taken on, and
    the whole arrangement is built so it has none (`debate_core.application.ports`). That the
    signatures really do line up is checked where the contract binding assigns one of these to the
    port's type, which pyright reads.

    ::

        objects = S3EvidenceObjectStore(
            bucket=settings.storage.s3.bucket,          # from Terraform's evidence_bucket_name
            region=settings.storage.s3.region,
            profile=settings.storage.s3.aws_profile,
        )

    Args:
        bucket: The evidence bucket for one environment. Read from the environment root's
            `evidence_bucket_name` Terraform output, never compiled in.
        region: AWS region, or `None` to take it from the profile or the environment.
        profile: A profile in the shared AWS config — this environment's evidence profile.
        client: An already-built client, so that this store and a snapshot store over the same bucket
            share one. The tests pass moto's.
        kms_key_id: The environment's `evidence_kms_key_arn`, to state the key on each upload instead
            of inheriting the bucket's default encryption.
        multipart_threshold_bytes: Size above which a transfer is split into parts.
        multipart_part_size_bytes: Size of each part. Must be at least S3's 5 MiB minimum.
    """

    def __init__(
        self,
        *,
        bucket: str,
        region: str | None = None,
        profile: str | None = None,
        client: S3Client | None = None,
        kms_key_id: str | None = None,
        multipart_threshold_bytes: int = DEFAULT_MULTIPART_THRESHOLD_BYTES,
        multipart_part_size_bytes: int = DEFAULT_MULTIPART_PART_SIZE_BYTES,
    ) -> None:
        self._bucket = bucket
        self._profile = profile
        self._kms_key_id = kms_key_id
        self._transfer_config = build_transfer_config(
            multipart_threshold_bytes=multipart_threshold_bytes,
            multipart_part_size_bytes=multipart_part_size_bytes,
        )
        self._client = client if client is not None else build_s3_client(region=region, profile=profile)

    @property
    def bucket(self) -> str:
        """The bucket this store reads and writes."""
        return self._bucket

    async def list_objects(self, prefix: str) -> tuple[ObjectInfo, ...]:
        """Every object whose key starts with `prefix`, sorted by key, with no digests.

        Walks every page of the listing. S3 returns keys in lexicographic order already, so the sort
        is cheap and is done anyway: the port promises the order, and a caller must not have to know
        which implementation happens to provide it for free.
        """
        return await asyncio.to_thread(self._list_objects, prefix)

    async def head(self, key: ObjectKey) -> ObjectInfo:
        """What the store knows about one object. `NotFound` when there is none."""
        return await asyncio.to_thread(self._head_or_raise, validate_object_key(key))

    async def put_file(self, key: ObjectKey, source: Path) -> ObjectInfo:
        """Upload `source` to `key`, in parts when it is large, and return the stored object."""
        return await asyncio.to_thread(self._put_file, validate_object_key(key), source)

    async def get_file(self, key: ObjectKey, destination: Path) -> ObjectInfo:
        """Download `key` to `destination` atomically, verifying any digest the store recorded."""
        return await asyncio.to_thread(self._get_file, validate_object_key(key), destination)

    # ------------------------------------------------------------------------------------------
    # The blocking implementations, each run in a worker thread by the methods above
    # ------------------------------------------------------------------------------------------

    def _list_objects(self, prefix: str) -> tuple[ObjectInfo, ...]:
        found: list[ObjectInfo] = []
        with mapped_s3_errors(self._call("ListObjectsV2", prefix)):
            pages = self._client.get_paginator("list_objects_v2").paginate(Bucket=self._bucket, Prefix=prefix)
            for page in pages:
                for stored in page.get("Contents", []):
                    key = stored.get("Key")
                    size = stored.get("Size")
                    if key is None or size is None:
                        # Both are optional in the API's schema and always present in practice. An
                        # entry missing either is not something a sync could transfer, so it is left
                        # out of the listing rather than turned into an ObjectInfo that lies.
                        continue
                    found.append(ObjectInfo(key=key, size=size))
        return tuple(sorted(found, key=lambda info: info.key))

    def _head_or_raise(self, key: ObjectKey) -> ObjectInfo:
        found = self._head(key)
        if found is None:
            raise NotFound(_ENTITY, key)
        return found

    def _head(self, key: ObjectKey) -> ObjectInfo | None:
        """The object's details, or `None` when there is no such object.

        A `NotFound` naming something other than an evidence object — `NoSuchBucket` maps to one — is
        re-raised: a store pointed at a bucket that does not exist must say so rather than report
        every key in it as absent.
        """
        try:
            with mapped_s3_errors(self._call("HeadObject", key)):
                response = self._client.head_object(Bucket=self._bucket, Key=key)
        except NotFound as absent:
            if absent.entity != _ENTITY:
                raise
            return None
        return ObjectInfo(
            key=key,
            size=response["ContentLength"],
            sha256=_recorded_digest(dict(response)),
            version_id=response.get("VersionId"),
        )

    def _put_file(self, key: ObjectKey, source: Path) -> ObjectInfo:
        digest = sha256_of_file(source)
        extra_arguments: dict[str, Any] = {
            "ChecksumAlgorithm": "SHA256",
            "Metadata": {SHA256_METADATA_NAME: digest},
            **self._encryption_arguments(),
        }
        with mapped_s3_errors(self._call("PutObject", key)):
            self._client.upload_file(
                Filename=str(source),
                Bucket=self._bucket,
                Key=key,
                ExtraArgs=extra_arguments,
                Config=self._transfer_config,
            )
        stored = self._head_or_raise(key)
        # The digest is this call's own, not the one just read back: what was uploaded is what the
        # caller is owed, and `_head` would report `None` for a bucket that dropped the metadata.
        return ObjectInfo(key=key, size=source.stat().st_size, sha256=digest, version_id=stored.version_id)

    def _get_file(self, key: ObjectKey, destination: Path) -> ObjectInfo:
        recorded = self._head_or_raise(key)
        with atomic_replacement(destination) as incoming:
            with mapped_s3_errors(self._call("GetObject", key)):
                self._client.download_file(
                    Bucket=self._bucket,
                    Key=key,
                    Filename=str(incoming),
                    Config=self._transfer_config,
                )
            landed = sha256_of_file(incoming)
            if recorded.sha256 is not None and landed != recorded.sha256:
                # Raising inside the block discards the download: nothing is renamed into place.
                raise BlobIntegrityError(key, landed)
            size = incoming.stat().st_size
        return ObjectInfo(key=key, size=size, sha256=landed, version_id=recorded.version_id)

    # ------------------------------------------------------------------------------------------
    # Shared pieces
    # ------------------------------------------------------------------------------------------

    def _encryption_arguments(self) -> dict[str, str]:
        """`SSEKMSKeyId` when a key was given, nothing when the bucket's default encryption applies."""
        if self._kms_key_id is None:
            return {}
        return {"ServerSideEncryption": "aws:kms", "SSEKMSKeyId": self._kms_key_id}

    def _call(self, operation: str, key: str) -> S3Call:
        """The context an error message is built from — see :class:`S3Call`. Never a credential."""
        return S3Call(
            operation=operation,
            bucket=self._bucket,
            entity=_ENTITY,
            key=key,
            s3_key=key or None,
            profile=self._profile,
        )


def _recorded_digest(head: dict[str, Any]) -> Sha256Hex | None:
    """The full-object digest the store recorded for an object, or `None` when it holds none.

    Only object metadata is consulted. S3's own `ChecksumSHA256` is not the SHA-256 of a multipart
    object — it is a composite of the part digests — so reading it here would make a large object's
    digest silently mean something different from a small one's.
    """
    return head.get("Metadata", {}).get(SHA256_METADATA_NAME)
