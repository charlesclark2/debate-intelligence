"""The evidence system of record in S3: immutable blobs under the SHA-256 of their own content.

The bucket-side twin of :class:`~debate_core.integrations.local.FsSnapshotStore`, satisfying the same
:class:`~debate_core.application.ports.persistence.SnapshotStore` port and held to the same shared
contract (:mod:`debate_core.testing.contracts.snapshot_store`). A card cut against a blob in a local
evidence directory re-verifies against the same blob in the bucket, because both stores build the
same key from the same bytes and neither will hand back bytes that do not hash to it (architecture
proposal §7, §8, ADR-0003).

## Keys

::

    raw/caselist/hsld26/sha256/ab/cd/abcd1234…def0
    <────── prefix ────>        ^^ ^^ first two byte pairs of the hex digest

`docs/architecture/evidence-store-layout.md` is the contract for that shape and for which prefixes
exist; the prefix is a constructor argument, so one bucket holds a store per prefix and this class
does not decide which. The fan-out is the same two levels as the local store, for the same reason: a
flat prefix with 60,000 members under it is slow to page and unreadable in a console.

The key carries the digest and nothing else — no extension, no caselist, no team, no original
filename. That is a rule of `docs/policies/caselist-data-use.md`, because a key is quoted in logs, in
error messages and in CloudTrail.

## The three properties, and how S3 keeps them

**Deduplication** is free: identical bytes produce the same digest, so the same file disclosed by
four teams is one object.

**Idempotent writes.** :meth:`S3SnapshotStore.put` heads the key first and returns without issuing a
`PutObject` when an object is already there. That matters more here than on a laptop: the bucket is
versioned, so a blind re-`PutObject` of identical bytes would add a version to the history of a
content-addressed key — and in a content-addressed store, a key with two versions is the signal that
something went wrong, not routine noise (`v1-e29-t03`).

**Detectable corruption.** :meth:`S3SnapshotStore.get` re-hashes what it downloaded and raises
:class:`~debate_core.application.errors.BlobIntegrityError` rather than returning bytes that do not
match their key. Every upload also carries S3's own SHA-256 checksum
(`ChecksumAlgorithm="SHA256"`), so S3 rejects a part that arrived damaged instead of storing it, and
the full-object digest goes into the object's metadata under
:data:`SHA256_METADATA_NAME` so that a `HeadObject` can state it without downloading the object.

There is no `delete` and no overwrite, because the port has neither. Removing a source is an operator
procedure with its own credential (`docs/runbooks/caselist-removal.md`).

## Blocking calls in `async def`

Every S3 call runs in a worker thread through :func:`asyncio.to_thread`, so a real network round trip
does not block the event loop the CLI, the API and the workers share. This is the difference from the
local adapters, which do their work inline because a local read is tens of microseconds
(:mod:`debate_core.integrations.local`). One client is shared across those threads, which botocore
supports for calls; it is built once in the constructor.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from debate_core.application.errors import BlobIntegrityError, NotFound
from debate_core.application.ports import BlobKey
from debate_core.application.ports.evidence_store import validate_object_key
from debate_core.domain import SHA256_HEX_PATTERN
from debate_core.integrations.file_streaming import atomic_replacement, sha256_of_file
from debate_core.integrations.s3.client import (
    DEFAULT_MULTIPART_PART_SIZE_BYTES,
    DEFAULT_MULTIPART_THRESHOLD_BYTES,
    build_s3_client,
    build_transfer_config,
)
from debate_core.integrations.s3.errors import S3Call, mapped_s3_errors

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

__all__ = [
    "BLOB_KEY_SEGMENT",
    "SHA256_METADATA_NAME",
    "S3SnapshotStore",
]

BLOB_KEY_SEGMENT = "sha256"
"""The segment between the prefix and the fan-out, naming the digest the key is built from.

Written out rather than implied so that a second content-addressing scheme — were one ever needed —
would be a sibling segment and not a silent reinterpretation of every key already in the bucket.
"""

SHA256_METADATA_NAME = "sha256"
"""The object-metadata entry the full-object digest is stored under (`x-amz-meta-sha256`).

S3's own `ChecksumSHA256` cannot be used for this. For a single-part upload it is the digest of the
object, but for a multipart upload it is a *composite* checksum — the digest of the concatenated part
digests, with a `-N` suffix — which is not the SHA-256 of the file and cannot be compared to a blob
key. So the digest that means "this is the content" is recorded here, by us, in the one place that
reads the same for a 40-kilobyte disclosure and a 40-gigabyte archive.
"""

#: What a blob key must look like, and the guard that keeps a key from naming anything unintended.
_BLOB_KEY_PATTERN: Final = re.compile(SHA256_HEX_PATTERN)

#: The name `NotFound` and `BlobIntegrityError` report, matching the local and in-memory stores.
_ENTITY: Final = "snapshot blob"


class S3SnapshotStore:
    """A :class:`~debate_core.application.ports.persistence.SnapshotStore` on an S3 bucket.

    Takes the bucket, the prefix and the AWS coordinates and derives every key from them, so one
    environment is one bucket and nothing this store writes can land in another. It reads no settings
    and resolves no environment itself: `v1-e29-t05-evidence-sync-cli` reads the bucket name from the
    environment root's `evidence_bucket_name` Terraform output for `DEBATE_ENV` and passes it here,
    which is what keeps a dev session from writing into `debate-prod-evidence-…`.

    ::

        store = S3SnapshotStore(
            bucket=settings.storage.s3.bucket,          # from Terraform's evidence_bucket_name
            prefix="raw/caselist/hsld26",
            region=settings.storage.s3.region,
            profile=settings.storage.s3.aws_profile,    # the SSO profile, locally
        )

    Args:
        bucket: The evidence bucket for one environment.
        prefix: Where this store's blobs live inside it, e.g. `raw/caselist/hsld26`. Validated as an
            object key, so it cannot contain `..` or a leading or trailing `/`.
        region: AWS region, or `None` to take it from the profile or the environment.
        profile: A profile in the shared AWS config — the SSO profile for this environment's evidence.
            `None` uses botocore's standard chain, which is what a role on an instance or a task is.
        client: An already-built S3 client to use instead of building one. Two adapters over one
            bucket share a client this way, and the tests pass moto's. `region` is then unused, while
            `profile` is still worth passing: it is what the `aws sso login` hint names.
        kms_key_id: The customer-managed key to encrypt uploads with — the environment root's
            `evidence_kms_key_arn` output. `None`, the default, relies on the bucket's own default
            encryption, which `v1-e29-t03` configures with exactly that key; pass it when a caller
            wants the request to state the key rather than inherit it.
        multipart_threshold_bytes: Size above which an upload or download is split into parts.
        multipart_part_size_bytes: Size of each part. Must be at least S3's 5 MiB minimum.

    Raises:
        ValueError: If `prefix` is not a usable key prefix, or the multipart sizes are not usable.
    """

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str,
        region: str | None = None,
        profile: str | None = None,
        client: S3Client | None = None,
        kms_key_id: str | None = None,
        multipart_threshold_bytes: int = DEFAULT_MULTIPART_THRESHOLD_BYTES,
        multipart_part_size_bytes: int = DEFAULT_MULTIPART_PART_SIZE_BYTES,
    ) -> None:
        self._bucket = bucket
        self._prefix = validate_object_key(prefix)
        self._profile = profile
        self._kms_key_id = kms_key_id
        self._transfer_config = build_transfer_config(
            multipart_threshold_bytes=multipart_threshold_bytes,
            multipart_part_size_bytes=multipart_part_size_bytes,
        )
        self._client = client if client is not None else build_s3_client(region=region, profile=profile)

    @property
    def bucket(self) -> str:
        """The bucket this store writes to."""
        return self._bucket

    @property
    def prefix(self) -> str:
        """The key prefix this store's blobs live under, without a trailing `/`."""
        return self._prefix

    def s3_key_for(self, key: BlobKey) -> str:
        """Return the full key in the bucket that the blob with this key is (or would be) stored at.

        Public for the same reasons as
        :meth:`~debate_core.integrations.local.FsSnapshotStore.path_for`: the removal runbook has to
        name an object's versions, and this task's tests have to write a damaged object to prove the
        integrity check fires. It is not part of the port — no use case may reach a blob by its S3
        key.

        Raises :class:`ValueError` when `key` is not 64 lowercase hex characters. That check is also
        the containment guard: a key can never contain `/` or `..`, so no key can name an object
        outside this store's prefix.
        """
        if _BLOB_KEY_PATTERN.match(key) is None:
            raise ValueError(f"not a blob key (expected 64 lowercase hex characters): {key!r}")
        return f"{self._prefix}/{BLOB_KEY_SEGMENT}/{key[0:2]}/{key[2:4]}/{key}"

    # ------------------------------------------------------------------------------------------
    # The port
    # ------------------------------------------------------------------------------------------

    async def put(self, data: bytes) -> BlobKey:
        """Store `data` under the SHA-256 of its own bytes and return that key.

        Bytes already stored are a no-op: the existing object is left alone, no `PutObject` is issued
        and the bucket gains no version. Raises
        :class:`~debate_core.application.errors.BlobIntegrityError` when an object is already stored
        at the key and records a *different* digest, which is the one way the store can be asked to
        file two different contents under one content-addressed key.

        For anything large enough that its bytes should not be in memory in the first place, use
        :meth:`put_file`.
        """
        return await asyncio.to_thread(self._put_bytes, data)

    async def get(self, key: BlobKey) -> bytes:
        """Return the bytes stored under `key`, after checking they still hash to it.

        Raises :class:`~debate_core.application.errors.NotFound` when nothing is stored under the key
        — including when `key` is not a digest at all, since no such key can have been minted by
        :meth:`put` — and :class:`~debate_core.application.errors.BlobIntegrityError` when what came
        back does not hash to the key it is filed under.
        """
        return await asyncio.to_thread(self._get_bytes, key)

    async def exists(self, key: BlobKey) -> bool:
        """True when an object is stored under `key`. One `HeadObject`; it reads nothing."""
        return await asyncio.to_thread(self._exists, key)

    # ------------------------------------------------------------------------------------------
    # Beyond the port: the same store, for files too big to be `bytes`
    # ------------------------------------------------------------------------------------------

    async def put_file(self, source: Path) -> BlobKey:
        """Store the file at `source` under the SHA-256 of its contents and return that key.

        The same store and the same keys as :meth:`put`, reached without holding the object in
        memory: the file is hashed in chunks and then streamed to S3, in parts when it is above the
        multipart threshold. This is how a camp archive or a season dump is published
        (`v1-e29-t05-evidence-sync-cli`, `v1-e30-t06`), and it is deliberately *not* part of the
        :class:`~debate_core.application.ports.persistence.SnapshotStore` port: the port is about
        bytes a use case is holding, and a local path means nothing to a store that might not be on
        this machine.

        Idempotent and integrity-checked exactly as :meth:`put` is. Raises
        :class:`FileNotFoundError` when `source` does not exist.
        """
        return await asyncio.to_thread(self._put_file, source)

    async def get_file(self, key: BlobKey, destination: Path) -> Path:
        """Download the blob at `key` to `destination`, verify it, and return `destination`.

        The counterpart of :meth:`put_file`, for reading a large object without holding it in memory.
        The bytes are hashed as they land and the file is renamed into place only once the digest
        matches the key, so a caller never sees a damaged or partial file — a mismatch raises
        :class:`~debate_core.application.errors.BlobIntegrityError` and leaves `destination` as it
        was. Raises :class:`~debate_core.application.errors.NotFound` when there is no such blob.
        """
        return await asyncio.to_thread(self._get_file, key, destination)

    # ------------------------------------------------------------------------------------------
    # The blocking implementations, each run in a worker thread by the methods above
    # ------------------------------------------------------------------------------------------

    def _put_bytes(self, data: bytes) -> BlobKey:
        key = hashlib.sha256(data).hexdigest()
        s3_key = self.s3_key_for(key)
        if self._stored_digest_matches(key, s3_key):
            return key
        with mapped_s3_errors(self._call("PutObject", key, s3_key)):
            self._client.put_object(
                Bucket=self._bucket,
                Key=s3_key,
                Body=data,
                ChecksumAlgorithm="SHA256",
                Metadata={SHA256_METADATA_NAME: key},
                **self._encryption_arguments(),
            )
        return key

    def _put_file(self, source: Path) -> BlobKey:
        key = sha256_of_file(source)
        s3_key = self.s3_key_for(key)
        if self._stored_digest_matches(key, s3_key):
            return key
        extra_arguments: dict[str, Any] = {
            "ChecksumAlgorithm": "SHA256",
            "Metadata": {SHA256_METADATA_NAME: key},
            **self._encryption_arguments(),
        }
        with mapped_s3_errors(self._call("PutObject", key, s3_key)):
            self._client.upload_file(
                Filename=str(source),
                Bucket=self._bucket,
                Key=s3_key,
                ExtraArgs=extra_arguments,
                Config=self._transfer_config,
            )
        return key

    def _get_bytes(self, key: BlobKey) -> bytes:
        try:
            s3_key = self.s3_key_for(key)
        except ValueError as malformed:
            raise NotFound(_ENTITY, key) from malformed
        with mapped_s3_errors(self._call("GetObject", key, s3_key)):
            response = self._client.get_object(Bucket=self._bucket, Key=s3_key)
            data = response["Body"].read()
        actual = hashlib.sha256(data).hexdigest()
        if actual != key:
            raise BlobIntegrityError(key, actual)
        return data

    def _get_file(self, key: BlobKey, destination: Path) -> Path:
        try:
            s3_key = self.s3_key_for(key)
        except ValueError as malformed:
            raise NotFound(_ENTITY, key) from malformed
        with atomic_replacement(destination) as incoming:
            with mapped_s3_errors(self._call("GetObject", key, s3_key)):
                self._client.download_file(
                    Bucket=self._bucket,
                    Key=s3_key,
                    Filename=str(incoming),
                    Config=self._transfer_config,
                )
            actual = sha256_of_file(incoming)
            if actual != key:
                # Raising inside the block is what discards the download: nothing is renamed.
                raise BlobIntegrityError(key, actual)
        return destination

    def _exists(self, key: BlobKey) -> bool:
        try:
            s3_key = self.s3_key_for(key)
        except ValueError:
            return False
        return self._head(key, s3_key) is not None

    # ------------------------------------------------------------------------------------------
    # Shared pieces of the blocking implementations
    # ------------------------------------------------------------------------------------------

    def _head(self, key: BlobKey, s3_key: str) -> dict[str, Any] | None:
        """The `HeadObject` response for this key, or `None` when there is no such object.

        Absence is an answer to a `head`, not a failure of it, so S3's 404 — already translated to
        :class:`~debate_core.application.errors.NotFound` on the way out of `mapped_s3_errors` —
        becomes `None` and the callers decide what it means. A `NotFound` naming something *other*
        than a blob is re-raised: `NoSuchBucket` maps to one of those, and a store pointed at a
        bucket that does not exist must say so rather than report every key as absent.
        """
        try:
            with mapped_s3_errors(self._call("HeadObject", key, s3_key)):
                return dict(self._client.head_object(Bucket=self._bucket, Key=s3_key))
        except NotFound as absent:
            if absent.entity != _ENTITY:
                raise
            return None

    def _stored_digest_matches(self, key: BlobKey, s3_key: str) -> bool:
        """True when an object is already stored at `s3_key` and may be left exactly as it is.

        This is the whole of the store's idempotency, and the one place a content-addressed key can
        be caught holding the wrong content. Three outcomes:

        * Nothing stored — `False`, and the caller uploads.
        * Stored, recording this digest — `True`, and the caller returns without a `PutObject`.
        * Stored, recording a *different* digest —
          :class:`~debate_core.application.errors.BlobIntegrityError`. Nothing in this platform can
          produce that object, so the store is not in a state to be written to: either the metadata
          was rewritten or the object was filed under a key that is not its content's digest.

        An object with *no* recorded digest is treated as a match, and the upload is skipped. That is
        something else's object — a `cp` from a console, an earlier tool — and re-uploading over it
        would replace evidence this store cannot vouch for with evidence it can, silently, in a
        versioned bucket. Skipping leaves it exactly as it is, and the mismatch surfaces at
        :meth:`get`, which re-hashes every read and refuses the bytes instead of guessing here.
        """
        head = self._head(key, s3_key)
        if head is None:
            return False
        recorded = head.get("Metadata", {}).get(SHA256_METADATA_NAME)
        if recorded is not None and recorded != key:
            raise BlobIntegrityError(key, recorded)
        return True

    def _encryption_arguments(self) -> dict[str, str]:
        """`SSEKMSKeyId` when a key was given, nothing when the bucket's default encryption applies."""
        if self._kms_key_id is None:
            return {}
        return {"ServerSideEncryption": "aws:kms", "SSEKMSKeyId": self._kms_key_id}

    def _call(self, operation: str, key: BlobKey, s3_key: str) -> S3Call:
        """The context an error message is built from — see :class:`S3Call`. Never a credential."""
        return S3Call(
            operation=operation,
            bucket=self._bucket,
            entity=_ENTITY,
            key=key,
            s3_key=s3_key,
            profile=self._profile,
        )
