"""`debate-research tub index publish`: one built index to an environment's evidence bucket (`v1-e39-t02`).

:class:`SearchIndexPublishService` takes a directory `tub index build` wrote and puts it under
`reports/tub/search/<index id>/` in the bucket, through the
:class:`~debate_core.application.ports.evidence_store.EvidenceObjectStore` port the rest of the CLI
publishes through. The pilot's function reads `reports/tub/search/current.json` and follows it
(ADR-0019 (c) 3), so the order of the three writes is the whole safety argument:

1. the gzip object, `search-index.sqlite.gz`, checked against the manifest's digest as it lands;
2. the manifest, `manifest.json`, checked the same way;
3. the pointer, `current.json`, **last**, naming both by key and digest.

A failure at any step leaves the pointer where it was, so a reader that follows it finds the
previous index whole, and never this one half-written. The SQLite file itself is not uploaded:
the gzip object is what the function downloads, and the pointer carries the SQLite file's digest so
the function can check what it decompressed.

## What it refuses

Before anything is uploaded:

* **A version mismatch** (:class:`SearchIndexVersionMismatch`): a manifest whose parser or fingerprint
  version is not the running build's, or whose format version this build does not write. An index
  built by another build would hold card offsets and cluster ids this build's file builder and
  pages do not agree with.
* **Files that are not the manifest's** (:class:`SearchIndexFilesDamaged`): a gzip object whose size or
  digest is not the one the manifest records, or that does not decompress to the SQLite file the
  manifest records.

Nothing here deletes. Pruning superseded versions is `v1-e39-t07`'s, under the removal credential.
"""

from __future__ import annotations

import gzip
import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from debate_core.application.errors import DomainError
from debate_core.application.ports.evidence_store import EvidenceObjectStore, ObjectInfo
from debate_core.domain.search_index import (
    SEARCH_INDEX_FORMAT_VERSION,
    SEARCH_INDEX_GZIP_NAME,
    SEARCH_INDEX_MANIFEST_NAME,
    SEARCH_INDEX_POINTER_KEY,
    SearchIndexManifest,
    SearchIndexPointer,
    index_object_key,
)
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION

__all__ = [
    "PublishedSearchIndex",
    "SearchIndexFilesDamaged",
    "SearchIndexPublishService",
    "SearchIndexVersionMismatch",
    "UnreadableSearchIndexManifest",
    "read_search_index_manifest",
]

_CHUNK: Final = 1024 * 1024


class SearchIndexVersionMismatch(DomainError):
    """An index built under a parser, fingerprint or format version the running build does not run."""

    def __init__(self, index_id: str, field: str, built: str, running: str) -> None:
        self.index_id = index_id
        self.field = field
        self.built = built
        self.running = running
        super().__init__(
            f"index {index_id} was built with {field} {built}, and this build runs {running}; "
            "rebuild it with `debate-research tub index build` from a store parsed by this build"
        )


class SearchIndexFilesDamaged(DomainError):
    """A file of a built index, or the object as the bucket stored it, is not the one its manifest records."""

    def __init__(self, index_id: str, name: str, reason: str) -> None:
        self.index_id = index_id
        self.name = name
        self.reason = reason
        super().__init__(f"index {index_id}'s {name} {reason}; nothing past it was published")


class UnreadableSearchIndexManifest(DomainError):
    """A directory with no manifest, or one that is not a search index manifest."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"not a built search index: {reason}")


@dataclass(frozen=True, slots=True)
class PublishedSearchIndex:
    """What a publish wrote, in the order it wrote it."""

    index_id: str
    object_key: str
    manifest_key: str
    pointer_key: str
    pointer: SearchIndexPointer


def read_search_index_manifest(directory: Path) -> SearchIndexManifest:
    """The manifest of the index built in `directory`. Raises :class:`UnreadableSearchIndexManifest`."""
    path = directory / SEARCH_INDEX_MANIFEST_NAME
    if not path.is_file():
        raise UnreadableSearchIndexManifest(f"{SEARCH_INDEX_MANIFEST_NAME} is missing")
    try:
        return SearchIndexManifest.model_validate_json(path.read_bytes())
    except ValidationError as error:
        raise UnreadableSearchIndexManifest(
            f"{SEARCH_INDEX_MANIFEST_NAME} does not validate ({error.error_count()} error(s))"
        ) from None


class SearchIndexPublishService:
    """Publishes a built index to one bucket, the pointer last."""

    def __init__(
        self,
        *,
        bucket: EvidenceObjectStore,
        parser_version: str,
        fingerprint_version: str = FINGERPRINT_VERSION,
        format_version: int = SEARCH_INDEX_FORMAT_VERSION,
    ) -> None:
        """`parser_version` and `fingerprint_version` are the running build's: an index must match both."""
        self._bucket = bucket
        self._running = {
            "parser version": parser_version,
            "fingerprint version": fingerprint_version,
            "format version": str(format_version),
        }

    def check(self, directory: Path) -> SearchIndexManifest:
        """Everything :meth:`publish` refuses on, asked without touching the bucket."""
        manifest = read_search_index_manifest(directory)
        built = {
            "parser version": manifest.parser_version,
            "fingerprint version": manifest.fingerprint_version,
            "format version": str(manifest.format_version),
        }
        for field, running in self._running.items():
            if built[field] != running:
                raise SearchIndexVersionMismatch(manifest.index_id, field, built[field], running)
        _check_gzip_object(directory / SEARCH_INDEX_GZIP_NAME, manifest)
        return manifest

    async def publish(self, directory: Path) -> PublishedSearchIndex:
        """Upload the gzip object, then the manifest, then the pointer; each checked as it lands."""
        manifest = self.check(directory)
        manifest_path = directory / SEARCH_INDEX_MANIFEST_NAME
        manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        object_key = index_object_key(manifest.index_id, SEARCH_INDEX_GZIP_NAME)
        manifest_key = index_object_key(manifest.index_id, SEARCH_INDEX_MANIFEST_NAME)

        _landed(
            manifest.index_id,
            SEARCH_INDEX_GZIP_NAME,
            await self._bucket.put_file(object_key, directory / SEARCH_INDEX_GZIP_NAME),
            manifest.gzip_object.sha256,
        )
        _landed(
            manifest.index_id,
            SEARCH_INDEX_MANIFEST_NAME,
            await self._bucket.put_file(manifest_key, manifest_path),
            manifest_sha256,
        )

        pointer = SearchIndexPointer(
            format_version=manifest.format_version,
            index_id=manifest.index_id,
            manifest_key=manifest_key,
            manifest_sha256=manifest_sha256,
            object_key=object_key,
            object_sha256=manifest.gzip_object.sha256,
            sqlite_sha256=manifest.sqlite_file.sha256,
        )
        with tempfile.TemporaryDirectory(prefix="tub-index-pointer-") as scratch:
            pointer_path = Path(scratch) / "current.json"
            pointer_path.write_bytes(pointer.to_json_bytes())
            _landed(
                manifest.index_id,
                "current.json",
                await self._bucket.put_file(SEARCH_INDEX_POINTER_KEY, pointer_path),
                hashlib.sha256(pointer.to_json_bytes()).hexdigest(),
            )
        return PublishedSearchIndex(
            index_id=manifest.index_id,
            object_key=object_key,
            manifest_key=manifest_key,
            pointer_key=SEARCH_INDEX_POINTER_KEY,
            pointer=pointer,
        )


def _check_gzip_object(path: Path, manifest: SearchIndexManifest) -> None:
    """The gzip object is the manifest's, and decompresses to the manifest's SQLite file."""
    name = manifest.gzip_object.name
    if not path.is_file():
        raise SearchIndexFilesDamaged(manifest.index_id, name, "is missing")
    if path.stat().st_size != manifest.gzip_object.bytes or _sha256_of(path) != manifest.gzip_object.sha256:
        raise SearchIndexFilesDamaged(manifest.index_id, name, "is not the file its manifest records")
    inner = hashlib.sha256()
    size = 0
    try:
        with gzip.open(path, "rb") as unzipped:
            for chunk in iter(lambda: unzipped.read(_CHUNK), b""):
                inner.update(chunk)
                size += len(chunk)
    except (OSError, EOFError):
        raise SearchIndexFilesDamaged(manifest.index_id, name, "does not decompress") from None
    if size != manifest.sqlite_file.bytes or inner.hexdigest() != manifest.sqlite_file.sha256:
        raise SearchIndexFilesDamaged(
            manifest.index_id, name, "does not decompress to the SQLite file its manifest records"
        )


def _landed(index_id: str, name: str, stored: ObjectInfo, expected: str) -> None:
    if stored.sha256 != expected:
        raise SearchIndexFilesDamaged(index_id, name, "landed in the bucket with another digest")


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()
