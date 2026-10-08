"""Creating a source snapshot, and loading one back only when it is still what it claims to be.

A :class:`~debate_core.domain.SourceSnapshot` is the anchor every card's quotation is checked
against (architecture proposal §8, steps 1-2). :class:`SnapshotService` is the one place one is made:

* :meth:`SnapshotService.create` normalizes the extracted text, hashes the raw bytes and the
  normalized text, stores both through the :class:`~debate_core.application.ports.SnapshotStore`
  port and returns the record.
* :meth:`SnapshotService.load` reads both blobs back, re-hashes them against the record and refuses
  with :class:`~debate_core.application.errors.SnapshotIntegrityError` on any disagreement.

Fetching and extraction happen before this (E04); cutting spans and verifying them after it
(`v1-e03-t03`, `v1-e03-t04`). The service stores blobs and returns the record; saving the record
with :meth:`~debate_core.application.ports.ArticleRepository.save_snapshot` is the caller's step,
because the caller is the one that owns the article it belongs to.

## Storage

Two blobs per snapshot, both content-addressed by the port, so storing identical content twice
stores it once:

* the **raw blob** is the response bytes exactly as received, and its key is their SHA-256;
* the **normalized blob** is the canonical ``debate-snapshot-text/1`` JSON document
  (:mod:`debate_core.evidence.snapshot_text`, specified in `docs/evidence/snapshot-text-format.md`):
  normalized text, normalizer version and paragraph map. Its encoding depends on nothing but the
  normalized text, so two retrievals that normalize to the same text share it even when their raw
  bytes differ.

## Integrity on load is always on

:meth:`~SnapshotService.load` re-hashes both blobs every time, and there is no switch to turn that
off. An integrity check that callers can skip is one they will skip on the hot path, which is the
path that matters. Measured against the filesystem store on an Apple M3 Pro (task
`v1-e03-t02-hashing-provenance`), a load costs about 0.3 ms for a 150 KB web page, 8 ms for a 5 MB
PDF and 170 ms for a 50 MB one: roughly two and a half times the bare reads, most of it the
service's own re-hash of the raw bytes and the strict decode of the normalized document. A caller
that checks many cards against one source loads the snapshot once and reuses the
:class:`LoadedSnapshot`; it does not skip the check.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from debate_core.application.errors import (
    BlobIntegrityError,
    SnapshotIntegrityCheck,
    SnapshotIntegrityError,
)
from debate_core.application.ports import Clock, IdGenerator, SnapshotStore
from debate_core.domain import AccessStatus, ProvenanceMode, SourceSnapshot
from debate_core.evidence.hashing import sha256_bytes, sha256_text
from debate_core.evidence.normalization import (
    NORMALIZER_VERSION,
    SUPPORTED_NORMALIZER_VERSIONS,
    normalize,
)
from debate_core.evidence.snapshot_text import (
    MalformedSnapshotText,
    SnapshotText,
    SnapshotTextKeyMismatch,
    decode_snapshot_text,
    encode_snapshot_text,
)

__all__ = ["LoadedSnapshot", "SnapshotService"]


@dataclass(frozen=True, slots=True)
class LoadedSnapshot:
    """A snapshot record together with the content it describes, all of it checked.

    Only :meth:`SnapshotService.load` builds one, and only after every check has passed, so holding
    a `LoadedSnapshot` means the raw bytes hash to `snapshot.sha256` and the text hashes to
    `snapshot.normalized_text_hash`.
    """

    snapshot: SourceSnapshot
    raw_bytes: bytes
    """The response bytes exactly as stored."""
    normalized: SnapshotText
    """The normalized text, its normalizer version and its paragraph map."""


class SnapshotService:
    """Creates :class:`~debate_core.domain.SourceSnapshot` records and loads them back, checked.

    Reaches storage only through the :class:`~debate_core.application.ports.SnapshotStore` port; the
    composition root chooses the adapter.
    """

    def __init__(self, *, blobs: SnapshotStore, clock: Clock, id_generator: IdGenerator) -> None:
        self._blobs = blobs
        self._clock = clock
        self._id_generator = id_generator

    async def create(
        self,
        *,
        article_id: str,
        raw_bytes: bytes,
        extracted_text: str,
        canonical_url: str,
        retrieved_at: datetime,
        extractor_version: str,
        provenance_mode: ProvenanceMode,
        access_status: AccessStatus,
        content_type: str | None = None,
        owner_id: str | None = None,
        organization_id: str | None = None,
    ) -> SourceSnapshot:
        """Normalize, hash and store one retrieval, and return its snapshot record.

        `raw_bytes` are the response body exactly as received and are hashed and stored as they are.
        `extracted_text` is the extractor's output for them, which is normalized under the current
        normalizer version. `retrieved_at` must be timezone-aware and is recorded in UTC.

        Everything that can be refused is refused before a blob is written: text the normalizer
        rejects (a lone surrogate, the wrong Unicode database) and provenance the
        :class:`~debate_core.domain.SourceSnapshot` model rejects (a naive timestamp, a non-http
        URL). If the store fails between the two writes, the raw blob is left without a snapshot;
        it is immutable and content-addressed, so retrying the call reuses it.
        """
        normalized = normalize(extracted_text, NORMALIZER_VERSION)
        stored_text = SnapshotText.from_normalized(normalized)
        normalized_blob = encode_snapshot_text(stored_text)

        raw_sha256 = sha256_bytes(raw_bytes)
        normalized_blob_sha256 = sha256_bytes(normalized_blob)
        # This digest is a function of three things, not one: the extracted text, the normalizer
        # version and the Unicode database NFC is computed from. "Identical inputs give identical
        # hashes" (v1-e03-t02 ac3) holds across machines and Python upgrades only because
        # `normalize` refuses to run against any Unicode database but the one its version pins
        # (UnicodeDatabaseMismatchError; `debate_core`'s requires-python admits only Pythons that
        # ship that database, for that reason). The
        # version recorded below is the one `normalize` reports it used, never a constant kept
        # beside it, so the record cannot claim rules other than the ones that produced the text.
        normalized_text_hash = sha256_text(normalized.text)

        now = self._clock.now()
        snapshot = SourceSnapshot(
            snapshot_id=self._id_generator.new_id(),
            owner_id=owner_id,
            organization_id=organization_id,
            article_id=article_id,
            canonical_url=canonical_url,
            retrieved_at=retrieved_at,
            access_status=access_status,
            provenance_mode=provenance_mode,
            raw_blob_key=raw_sha256,
            normalized_blob_key=normalized_blob_sha256,
            sha256=raw_sha256,
            normalized_text_hash=normalized_text_hash,
            extractor_version=extractor_version,
            normalizer_version=normalized.normalizer_version,
            content_type=content_type,
            byte_size=len(raw_bytes),
            created_at=now,
            updated_at=now,
        )

        raw_key = await self._blobs.put(raw_bytes)
        if raw_key != raw_sha256:
            raise SnapshotIntegrityError(
                snapshot.snapshot_id,
                SnapshotIntegrityCheck.RAW_BYTES_HASH,
                expected=raw_sha256,
                actual=raw_key,
            )
        normalized_key = await self._blobs.put(normalized_blob)
        if normalized_key != normalized_blob_sha256:
            raise SnapshotIntegrityError(
                snapshot.snapshot_id,
                SnapshotIntegrityCheck.NORMALIZED_BLOB_HASH,
                expected=normalized_blob_sha256,
                actual=normalized_key,
            )
        return snapshot

    async def load(self, snapshot: SourceSnapshot) -> LoadedSnapshot:
        """Read a snapshot's blobs, re-hash both against the record, and return them.

        Raises :class:`~debate_core.application.errors.SnapshotIntegrityError` naming the first check
        that fails — an unknown normalizer version, raw bytes that do not hash to `sha256` (or are
        not `byte_size` long), a normalized blob that does not hash to its key or is not a canonical
        document, or text that does not hash to `normalized_text_hash`. Raises
        :class:`~debate_core.application.errors.NotFound` when a blob is missing altogether.

        The hashes are computed here, from the bytes the store returned, and do not rely on the
        store's own read check: a store that served altered bytes without noticing is still caught.
        """
        snapshot_id = snapshot.snapshot_id
        if snapshot.normalizer_version not in SUPPORTED_NORMALIZER_VERSIONS:
            raise SnapshotIntegrityError(
                snapshot_id,
                SnapshotIntegrityCheck.UNKNOWN_NORMALIZER_VERSION,
                expected=", ".join(SUPPORTED_NORMALIZER_VERSIONS),
                actual=snapshot.normalizer_version,
            )

        raw_bytes = await self._read(
            snapshot_id, snapshot.raw_blob_key, SnapshotIntegrityCheck.RAW_BYTES_HASH
        )
        raw_sha256 = sha256_bytes(raw_bytes)
        for recorded in (snapshot.sha256, snapshot.raw_blob_key):
            if raw_sha256 != recorded:
                raise SnapshotIntegrityError(
                    snapshot_id, SnapshotIntegrityCheck.RAW_BYTES_HASH, expected=recorded, actual=raw_sha256
                )
        if snapshot.byte_size is not None and len(raw_bytes) != snapshot.byte_size:
            raise SnapshotIntegrityError(
                snapshot_id,
                SnapshotIntegrityCheck.RAW_BYTE_SIZE,
                expected=str(snapshot.byte_size),
                actual=str(len(raw_bytes)),
            )

        normalized_blob = await self._read(
            snapshot_id, snapshot.normalized_blob_key, SnapshotIntegrityCheck.NORMALIZED_BLOB_HASH
        )
        try:
            # The re-hash of this blob happens inside the decode, which cannot be called without the
            # key. It is the only check that protects the paragraph map: see `snapshot_text`.
            stored_text = decode_snapshot_text(normalized_blob, expected_key=snapshot.normalized_blob_key)
        except SnapshotTextKeyMismatch as mismatch:
            raise SnapshotIntegrityError(
                snapshot_id,
                SnapshotIntegrityCheck.NORMALIZED_BLOB_HASH,
                expected=mismatch.expected_key,
                actual=mismatch.actual_key,
            ) from mismatch
        except MalformedSnapshotText as malformed:
            raise SnapshotIntegrityError(
                snapshot_id, SnapshotIntegrityCheck.NORMALIZED_BLOB_MALFORMED
            ) from malformed
        if stored_text.normalizer_version != snapshot.normalizer_version:
            raise SnapshotIntegrityError(
                snapshot_id,
                SnapshotIntegrityCheck.NORMALIZER_VERSION_MISMATCH,
                expected=snapshot.normalizer_version,
                actual=stored_text.normalizer_version,
            )
        normalized_text_hash = sha256_text(stored_text.text)
        if normalized_text_hash != snapshot.normalized_text_hash:
            raise SnapshotIntegrityError(
                snapshot_id,
                SnapshotIntegrityCheck.NORMALIZED_TEXT_HASH,
                expected=snapshot.normalized_text_hash,
                actual=normalized_text_hash,
            )
        return LoadedSnapshot(snapshot=snapshot, raw_bytes=raw_bytes, normalized=stored_text)

    async def _read(self, snapshot_id: str, key: str, check: SnapshotIntegrityCheck) -> bytes:
        """Read one blob, reporting the store's own integrity refusal as this snapshot's failure."""
        try:
            return await self._blobs.get(key)
        except BlobIntegrityError as damaged:
            raise SnapshotIntegrityError(
                snapshot_id, check, expected=key, actual=damaged.actual_sha256
            ) from damaged
