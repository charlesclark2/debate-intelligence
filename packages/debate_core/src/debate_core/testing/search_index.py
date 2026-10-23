"""A published search index in memory, for tests of the pilot's index holder and pages (`v1-e39-t06`).

:func:`published_index` turns the bytes of an index file a test built (with `v1-e39-t02`'s writer)
into what `tub index publish` would put in the bucket: the gzip object, the manifest and the
pointer, each with the digests the real ones carry. :class:`InMemorySearchIndexSource` serves them
the way the bucket does, entity tags and `304`s included, and records every read, so a test can see
that an unchanged pointer cost no body and that nothing but the three keys was asked for. It also
serves the suppression list beside them, the fourth key the function reads (`v1-e39-t07`), from
:meth:`InMemorySearchIndexSource.write_suppression_list`.

:func:`format_one_index` turns an index the running writer wrote into the format 1 file the writer
wrote before `v1-e39-t13`, so a test can show what the function does while it serves one.

Every value here is synthetic: invented caselist slugs, versions and counts.
"""

from __future__ import annotations

import gzip
import hashlib
import sqlite3
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field, replace
from typing import Final

from debate_core.application.caselist.suppression import SUPPRESSION_LIST_KEY
from debate_core.application.errors import NotFound, StoreError
from debate_core.application.ports.search_index_source import SUPPRESSION_LIST_MAX_BYTES, PointerRead
from debate_core.application.ports.suppression import SuppressionEntry
from debate_core.domain.search_index import (
    INDEX_ID_LENGTH,
    SEARCH_INDEX_FORMAT_VERSION,
    SEARCH_INDEX_GZIP_NAME,
    SEARCH_INDEX_MANIFEST_NAME,
    SEARCH_INDEX_POINTER_KEY,
    SEARCH_INDEX_SQLITE_NAME,
    SQLITE_FEATURE_CEILING,
    IndexCounts,
    IndexFile,
    SearchIndexManifest,
    SearchIndexPointer,
    StoreState,
    SuppressionListState,
    index_object_key,
)

__all__ = [
    "FORMAT_ONE_TOKENIZER",
    "InMemorySearchIndexSource",
    "PublishedIndex",
    "format_one_index",
    "published_index",
]

FORMAT_ONE_TOKENIZER: Final = "unicode61 remove_diacritics 2"
"""Format 1's full-text tokenizer: format 2's without the `porter` stemmer in front."""

_ZERO_DIGEST: Final = "0" * 64
_CHUNK: Final = 4096


@dataclass(frozen=True, slots=True)
class PublishedIndex:
    """One index as the bucket holds it: three objects by key."""

    index_id: str
    pointer: bytes
    objects: Mapping[str, bytes] = field(repr=False)

    @property
    def manifest(self) -> SearchIndexManifest:
        return SearchIndexManifest.model_validate_json(self.objects[self.manifest_key])

    @property
    def manifest_key(self) -> str:
        return index_object_key(self.index_id, SEARCH_INDEX_MANIFEST_NAME)

    @property
    def object_key(self) -> str:
        return index_object_key(self.index_id, SEARCH_INDEX_GZIP_NAME)

    def with_object(self, compressed: bytes) -> PublishedIndex:
        """This index with another gzip object in place of its own, the pointer and manifest unchanged."""
        return replace(self, objects={**self.objects, self.object_key: compressed})

    def with_pointer(self, pointer: bytes) -> PublishedIndex:
        return replace(self, pointer=pointer)


def published_index(
    sqlite: bytes,
    *,
    documents_by_store: Mapping[str, int],
    format_version: int = SEARCH_INDEX_FORMAT_VERSION,
    manifest_format_version: int | None = None,
    parser_version: str = "2026.10.18-docx-5",
) -> PublishedIndex:
    """`sqlite`, gzipped and described as `tub index publish` describes an index it uploads.

    `format_version` is written into the pointer and `manifest_format_version` (the same, unless
    given) into the manifest, so a test can publish an index of a format this build does not read.
    `parser_version` is the manifest's: a download test publishes the running parser's
    (`v1-e39-t08`).
    """
    sqlite_sha256 = hashlib.sha256(sqlite).hexdigest()
    index_id = sqlite_sha256[:INDEX_ID_LENGTH]
    compressed = gzip.compress(sqlite, compresslevel=6, mtime=0)
    stores = tuple(
        StoreState(
            caselist=caselist,
            version_directory=parser_version,
            latest_snapshot="2026-policy" if caselist == "openev" else "2026-10-13",
            occurrence_rows=count,
            occurrences_sha256=_ZERO_DIGEST,
        )
        for caselist, count in sorted(documents_by_store.items())
    )
    documents = sum(documents_by_store.values())
    manifest = SearchIndexManifest(
        format_version=manifest_format_version if manifest_format_version is not None else format_version,
        index_id=index_id,
        parser_version=parser_version,
        fingerprint_version="card-fingerprint-v4",
        sqlite_version="3.50.4",
        sqlite_feature_ceiling=SQLITE_FEATURE_CEILING,
        provenance_limit=5,
        stores=stores,
        snapshot="2026-10-13",
        suppression=SuppressionListState(entries=0, path_holds=0, sha256=_ZERO_DIGEST),
        counts=IndexCounts(
            documents=documents,
            documents_by_store=dict(documents_by_store),
            occurrences=documents,
            provenance_rows=documents,
            occurrence_rows_read=documents,
            suppressed_occurrences=0,
            clusters_left_out=0,
            unattributed_representatives=0,
        ),
        sqlite_file=IndexFile(name=SEARCH_INDEX_SQLITE_NAME, bytes=len(sqlite), sha256=sqlite_sha256),
        gzip_object=IndexFile(
            name=SEARCH_INDEX_GZIP_NAME,
            bytes=len(compressed),
            sha256=hashlib.sha256(compressed).hexdigest(),
        ),
    )
    manifest_bytes = manifest.to_json_bytes()
    pointer = SearchIndexPointer(
        format_version=format_version,
        index_id=index_id,
        manifest_key=index_object_key(index_id, SEARCH_INDEX_MANIFEST_NAME),
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        object_key=index_object_key(index_id, SEARCH_INDEX_GZIP_NAME),
        object_sha256=manifest.gzip_object.sha256,
        sqlite_sha256=sqlite_sha256,
    )
    return PublishedIndex(
        index_id=index_id,
        pointer=pointer.to_json_bytes(),
        objects={
            index_object_key(index_id, SEARCH_INDEX_MANIFEST_NAME): manifest_bytes,
            index_object_key(index_id, SEARCH_INDEX_GZIP_NAME): compressed,
        },
    )


def format_one_index(sqlite: bytes) -> bytes:
    """The format 1 file of the same rows as `sqlite`: its full-text table unstemmed, its version 1.

    In memory, from bytes to bytes. The writer of `v1-e39-t02` to `v1-e39-t12` wrote the same
    `documents` and `occurrences`, so only the `search` table, `index_info` and `user_version` differ.
    """
    connection = sqlite3.connect(":memory:", isolation_level=None)
    try:
        connection.deserialize(sqlite)
        for statement in (
            "BEGIN",
            "DROP TABLE search",
            "CREATE VIRTUAL TABLE search USING fts5(tag, cite, read_aloud, text, content='documents', "
            f"content_rowid='doc_id', tokenize='{FORMAT_ONE_TOKENIZER}')",
            "INSERT INTO search (search) VALUES ('rebuild')",
            "INSERT INTO search (search) VALUES ('optimize')",
            "UPDATE index_info SET value = '1' WHERE key = 'format_version'",
            "PRAGMA user_version = 1",
            "COMMIT",
            "VACUUM",
        ):
            connection.execute(statement)
        return connection.serialize()
    finally:
        connection.close()


class InMemorySearchIndexSource:
    """The bucket's `reports/tub/search/` as the function's role reads it, in memory.

    :meth:`publish` writes an index's objects and then its pointer, as `tub index publish` does.
    Each pointer write gets a new entity tag. `reads` lists every key read, in order, and
    `not_modified` counts the pointer reads answered `304`; `suppression_not_modified` counts the
    suppression list's. A list never written has no lines; `suppression_list_failure`, when set, is
    raised by every read of it, as an unreachable bucket would.
    """

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.etag: str | None = None
        self.reads: list[str] = []
        self.not_modified = 0
        self.suppression_etag: str | None = None
        self.suppression_not_modified = 0
        self.suppression_list_failure: StoreError | None = None
        self._writes = 0
        self._suppression_writes = 0

    def publish(self, index: PublishedIndex) -> None:
        self.objects.update(index.objects)
        self.write_pointer(index.pointer)

    def write_pointer(self, pointer: bytes) -> None:
        self._writes += 1
        self.objects[SEARCH_INDEX_POINTER_KEY] = pointer
        self.etag = f'"pointer-{self._writes}"'

    def read_pointer(self, *, if_none_match: str | None) -> PointerRead:
        self.reads.append(SEARCH_INDEX_POINTER_KEY)
        if SEARCH_INDEX_POINTER_KEY not in self.objects:
            raise NotFound("search index object", SEARCH_INDEX_POINTER_KEY)
        if if_none_match is not None and if_none_match == self.etag:
            self.not_modified += 1
            return PointerRead(body=None, etag=if_none_match)
        return PointerRead(body=self.objects[SEARCH_INDEX_POINTER_KEY], etag=self.etag)

    def write_suppression_list(self, body: bytes) -> None:
        """Replace the list's bytes, with a new entity tag."""
        self._suppression_writes += 1
        self.objects[SUPPRESSION_LIST_KEY] = body
        self.suppression_etag = f'"suppression-{self._suppression_writes}"'

    def append_suppression(self, *entries: SuppressionEntry) -> None:
        """Append entries as `caselist remove` does: one canonical line each, newline-terminated."""
        lines = "".join(entry.to_line() + "\n" for entry in entries).encode()
        self.write_suppression_list(self.objects.get(SUPPRESSION_LIST_KEY, b"") + lines)

    def read_suppression_list(self, *, if_none_match: str | None) -> PointerRead:
        self.reads.append(SUPPRESSION_LIST_KEY)
        if self.suppression_list_failure is not None:
            raise self.suppression_list_failure
        if SUPPRESSION_LIST_KEY not in self.objects:
            return PointerRead(body=b"", etag=None)
        if if_none_match is not None and if_none_match == self.suppression_etag:
            self.suppression_not_modified += 1
            return PointerRead(body=None, etag=if_none_match)
        body = self.objects[SUPPRESSION_LIST_KEY]
        if len(body) > SUPPRESSION_LIST_MAX_BYTES:
            raise ValueError(f"the object is longer than {SUPPRESSION_LIST_MAX_BYTES} bytes")
        return PointerRead(body=body, etag=self.suppression_etag)

    def read_object(self, key: str, *, max_bytes: int) -> bytes:
        data = self._get(key)
        if len(data) > max_bytes:
            raise ValueError(f"the object is longer than {max_bytes} bytes")
        return data

    def stream_object(self, key: str) -> Iterator[bytes]:
        data = self._get(key)
        for start in range(0, len(data), _CHUNK):
            yield data[start : start + _CHUNK]

    def _get(self, key: str) -> bytes:
        self.reads.append(key)
        if key not in self.objects:
            raise NotFound("search index object", key)
        return self.objects[key]
