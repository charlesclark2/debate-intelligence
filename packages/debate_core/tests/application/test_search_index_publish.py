"""`tub index publish` against the S3 test double: the pointer last, and nothing on a version mismatch (ac5).

The bucket is moto's, through the real `S3EvidenceObjectStore` (the `evidence_bucket` fixture in
`packages/debate_core/tests/conftest.py`), wrapped so a test can see the order of the writes and make one
fail. The index is a real one, built by `SearchIndexBuildService` from a one-card synthetic store.
Nothing here reaches AWS: moto answers botocore in-process and sockets are disabled.
"""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.errors import NotFound, StoreUnavailable
from debate_core.application.ports.evidence_store import EvidenceObjectStore, ObjectInfo
from debate_core.application.ports.parsed_store import (
    DocumentRecord,
    OccurrenceRecord,
    SourceEntry,
    SourceOutcome,
)
from debate_core.application.ports.suppression import disclosure_digest
from debate_core.application.search_index_build import BuiltSearchIndex, SearchIndexBuildService
from debate_core.application.search_index_publish import (
    SearchIndexFilesDamaged,
    SearchIndexPublishService,
    SearchIndexVersionMismatch,
    UnreadableSearchIndexManifest,
)
from debate_core.domain.card_occurrence import ClusterMembership
from debate_core.domain.caselist import Event, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import CardCompleteness, FileImportProvenance, ParsedCard, ParsedDocument
from debate_core.domain.search_index import (
    SEARCH_INDEX_GZIP_NAME,
    SEARCH_INDEX_MANIFEST_NAME,
    SEARCH_INDEX_POINTER_KEY,
    SearchIndexPointer,
)
from debate_core.domain.style_profile import StyleMatchSource
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION, card_fingerprint
from debate_core.integrations.local.search_index import SqliteSearchIndexWriter
from debate_core.integrations.local.suppression_list import local_suppression_list_file
from debate_core.integrations.s3 import S3EvidenceObjectStore
from debate_core.testing.fakes.caselist import InMemoryCaselistRepository
from debate_core.testing.fakes.parsed_store import InMemoryParsedStore

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

CASELIST: Final = "hsld26"
PARSER: Final = "2026.10.18-docx-5"
PROFILE: Final = "2026.09.20-verbatim-1"
SOURCE: Final = "1" * 64


def build(tmp_path: Path, text: str) -> BuiltSearchIndex:
    """A one-document index of a card with `text`, built the way `tub index build` builds one."""
    card = ParsedCard(
        tag="Invented growth claim",
        full_cite="Okonkwo 26",
        evidence_text=text,
        completeness=CardCompleteness.FULL,
        match_source=StyleMatchSource.HEURISTIC,
        confidence=0.9,
        provenance=FileImportProvenance(
            source_sha256=SOURCE,
            source_path="placeholder.docx",
            origin=SourceOrigin.CASELIST_ARCHIVE,
            caselist=CASELIST,
            snapshot=date(2026, 9, 1),
            first_element_index=0,
            last_element_index=2,
            parser_version=PARSER,
            profile_version=PROFILE,
        ),
    )
    store = InMemoryParsedStore()
    fields = {
        "caselist": CASELIST,
        "snapshot": "2026-09-01",
        "source_sha256": SOURCE,
        "parser_version": PARSER,
        "profile_version": PROFILE,
        "fingerprint_version": FINGERPRINT_VERSION,
    }
    document = ParsedDocument(
        source_sha256=SOURCE,
        source_path="placeholder.docx",
        parser_version=PARSER,
        profile_version=PROFILE,
        cards=(card,),
    )
    asyncio.run(
        store.write_source(
            CASELIST,
            PARSER,
            SourceEntry.model_validate(
                {
                    **fields,
                    "source_format": SourceFormat.DOCX,
                    "byte_size": 1,
                    "outcome": SourceOutcome.PARSED,
                    "cards": 1,
                }
            ),
            DocumentRecord.from_parsed_document(
                document,
                caselist=CASELIST,
                snapshot="2026-09-01",
                fingerprint_version=FINGERPRINT_VERSION,
                camp=None,
            ),
        )
    )
    row = OccurrenceRecord.model_validate(
        {
            **fields,
            "last_snapshot": "2026-09-08",
            "disclosure": disclosure_digest(CASELIST, "Maple Grove/QX/invented.docx"),
            "first_element_index": 0,
            "last_element_index": 2,
            "exact_fingerprint": card_fingerprint(card).exact_fingerprint,
            "cluster_id": card_fingerprint(card).exact_fingerprint,
            "membership": ClusterMembership.NEAR_DUPLICATE,
            "completeness": CardCompleteness.FULL,
        }
    )
    asyncio.run(store.write_aggregates(CASELIST, PARSER, index=(), failures=(), occurrences=(row,)))
    service = SearchIndexBuildService(
        parsed_store=store,
        caselists=InMemoryCaselistRepository(),
        suppression=RecordedSuppressionList(local_suppression_list_file(tmp_path / "data")),
        writer=SqliteSearchIndexWriter(),
        parser_version=PARSER,
        event_for_caselist={CASELIST: Event.LD}.get,
    )
    return asyncio.run(service.build((CASELIST,), tmp_path / "out"))


class RecordingStore:
    """The S3 store, with every write recorded in order and, when asked, one key's write refused."""

    def __init__(self, inner: EvidenceObjectStore, *, refuse: str | None = None) -> None:
        self.inner = inner
        self.refuse = refuse
        self.puts: list[str] = []

    async def list_objects(self, prefix: str) -> tuple[ObjectInfo, ...]:
        return await self.inner.list_objects(prefix)

    async def head(self, key: str) -> ObjectInfo:
        return await self.inner.head(key)

    async def put_file(self, key: str, source: Path) -> ObjectInfo:
        if self.refuse is not None and key.endswith(self.refuse):
            raise StoreUnavailable("PutObject", key, "connection reset")
        self.puts.append(key)
        return await self.inner.put_file(key, source)

    async def get_file(self, key: str, destination: Path) -> ObjectInfo:
        return await self.inner.get_file(key, destination)


@pytest.fixture
def bucket(evidence_bucket: str, s3_client: S3Client) -> S3EvidenceObjectStore:
    return S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client)


def publisher(store: EvidenceObjectStore, *, parser_version: str = PARSER) -> SearchIndexPublishService:
    return SearchIndexPublishService(bucket=store, parser_version=parser_version)


def current_pointer(bucket: S3EvidenceObjectStore, tmp_path: Path) -> SearchIndexPointer:
    landed = tmp_path / "fetched-current.json"
    asyncio.run(bucket.get_file(SEARCH_INDEX_POINTER_KEY, landed))
    return SearchIndexPointer.model_validate_json(landed.read_bytes())


def test_search_index_publish_writes_the_object_then_the_manifest_then_the_pointer(
    tmp_path: Path, bucket: S3EvidenceObjectStore
) -> None:
    built = build(tmp_path, "Invented growth always ends badly")
    recording = RecordingStore(bucket)
    published = asyncio.run(publisher(recording).publish(built.directory))

    index_id = built.manifest.index_id
    assert recording.puts == [
        f"reports/tub/search/{index_id}/search-index.sqlite.gz",
        f"reports/tub/search/{index_id}/manifest.json",
        "reports/tub/search/current.json",
    ]
    pointer = current_pointer(bucket, tmp_path)
    assert pointer == published.pointer
    assert pointer.index_id == index_id
    assert (
        pointer.object_sha256
        == hashlib.sha256((built.directory / SEARCH_INDEX_GZIP_NAME).read_bytes()).hexdigest()
    )
    assert (
        pointer.manifest_sha256
        == hashlib.sha256((built.directory / SEARCH_INDEX_MANIFEST_NAME).read_bytes()).hexdigest()
    )
    assert pointer.sqlite_sha256 == built.manifest.sqlite_file.sha256
    fetched = tmp_path / "fetched.gz"
    asyncio.run(bucket.get_file(pointer.object_key, fetched))
    assert hashlib.sha256(gzip.decompress(fetched.read_bytes())).hexdigest() == pointer.sqlite_sha256


@pytest.mark.parametrize("refused", [SEARCH_INDEX_GZIP_NAME, SEARCH_INDEX_MANIFEST_NAME, "current.json"])
def test_search_index_publish_leaves_the_previous_pointer_when_a_write_fails(
    tmp_path: Path, bucket: S3EvidenceObjectStore, refused: str
) -> None:
    first = build(tmp_path / "first", "Invented growth always ends badly")
    asyncio.run(publisher(bucket).publish(first.directory))
    second = build(tmp_path / "second", "Invented trade collapses without invented tariffs")
    assert second.manifest.index_id != first.manifest.index_id

    with pytest.raises(StoreUnavailable):
        asyncio.run(publisher(RecordingStore(bucket, refuse=refused)).publish(second.directory))

    assert current_pointer(bucket, tmp_path).index_id == first.manifest.index_id


def test_search_index_publish_writes_no_pointer_to_an_empty_bucket_when_the_manifest_fails(
    tmp_path: Path, bucket: S3EvidenceObjectStore
) -> None:
    built = build(tmp_path, "Invented growth always ends badly")
    with pytest.raises(StoreUnavailable):
        asyncio.run(
            publisher(RecordingStore(bucket, refuse=SEARCH_INDEX_MANIFEST_NAME)).publish(built.directory)
        )
    with pytest.raises(NotFound):
        asyncio.run(bucket.head(SEARCH_INDEX_POINTER_KEY))


def test_search_index_publish_refuses_another_parser_version_and_uploads_nothing(
    tmp_path: Path, bucket: S3EvidenceObjectStore
) -> None:
    built = build(tmp_path, "Invented growth always ends badly")
    recording = RecordingStore(bucket)
    with pytest.raises(SearchIndexVersionMismatch) as refused:
        asyncio.run(publisher(recording, parser_version="2026.11.01-docx-6").publish(built.directory))
    assert (refused.value.field, refused.value.built, refused.value.running) == (
        "parser version",
        PARSER,
        "2026.11.01-docx-6",
    )
    assert recording.puts == []


@pytest.mark.parametrize(
    ("field", "edited"),
    [
        ("fingerprint version", {"fingerprint_version": "card-fingerprint-v3"}),
        ("format version", {"format_version": 2}),
    ],
)
def test_search_index_publish_refuses_another_fingerprint_or_format_version(
    tmp_path: Path, bucket: S3EvidenceObjectStore, field: str, edited: dict[str, object]
) -> None:
    built = build(tmp_path, "Invented growth always ends badly")
    manifest_path = built.directory / SEARCH_INDEX_MANIFEST_NAME
    manifest_path.write_bytes(built.manifest.model_copy(update=edited).to_json_bytes())
    recording = RecordingStore(bucket)
    with pytest.raises(SearchIndexVersionMismatch) as refused:
        asyncio.run(publisher(recording).publish(built.directory))
    assert refused.value.field == field
    assert recording.puts == []


def test_search_index_publish_refuses_a_gzip_object_the_manifest_does_not_record(
    tmp_path: Path, bucket: S3EvidenceObjectStore
) -> None:
    built = build(tmp_path, "Invented growth always ends badly")
    other = build(tmp_path / "other", "Invented trade collapses without invented tariffs")
    (built.directory / SEARCH_INDEX_GZIP_NAME).write_bytes(
        (other.directory / SEARCH_INDEX_GZIP_NAME).read_bytes()
    )
    recording = RecordingStore(bucket)
    with pytest.raises(SearchIndexFilesDamaged):
        asyncio.run(publisher(recording).publish(built.directory))
    assert recording.puts == []


def test_search_index_publish_refuses_a_directory_without_a_manifest(
    tmp_path: Path, bucket: S3EvidenceObjectStore
) -> None:
    built = build(tmp_path, "Invented growth always ends badly")
    (built.directory / SEARCH_INDEX_MANIFEST_NAME).write_text(
        json.dumps({"index_id": "nope"}), encoding="utf-8"
    )
    with pytest.raises(UnreadableSearchIndexManifest):
        asyncio.run(publisher(bucket).publish(built.directory))
    (built.directory / SEARCH_INDEX_MANIFEST_NAME).unlink()
    with pytest.raises(UnreadableSearchIndexManifest):
        asyncio.run(publisher(bucket).publish(built.directory))


class MisreportingStore(RecordingStore):
    """A bucket that stores the gzip object and says it holds other bytes, as a damaged write would."""

    async def put_file(self, key: str, source: Path) -> ObjectInfo:
        stored = await super().put_file(key, source)
        if key.endswith(SEARCH_INDEX_GZIP_NAME):
            return ObjectInfo(key=stored.key, size=stored.size, sha256="0" * 64, version_id=stored.version_id)
        return stored


def test_search_index_publish_stops_before_the_pointer_when_the_object_lands_with_another_digest(
    tmp_path: Path, bucket: S3EvidenceObjectStore
) -> None:
    built = build(tmp_path, "Invented growth always ends badly")
    misreporting = MisreportingStore(bucket)
    with pytest.raises(SearchIndexFilesDamaged, match="landed in the bucket with another digest"):
        asyncio.run(publisher(misreporting).publish(built.directory))
    assert misreporting.puts == [f"reports/tub/search/{built.manifest.index_id}/search-index.sqlite.gz"]
    with pytest.raises(NotFound):
        asyncio.run(bucket.head(SEARCH_INDEX_POINTER_KEY))
