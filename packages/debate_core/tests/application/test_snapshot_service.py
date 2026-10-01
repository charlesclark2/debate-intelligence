"""SnapshotService: creating a snapshot records and stores exactly what it should; loading refuses damage.

Tests are named so the plan's criteria can select them: `-k create` runs snapshot creation (ac1,
ac3), `-k integrity` runs integrity-checked loading (ac2).

Every expected hash is SHA-256 of a byte string written out by hand in this file: the raw response,
the UTF-8 of the normalized text and the canonical JSON document. None is taken from the service, so
a service that hashed the wrong thing cannot agree with its own expectation
(`docs/process/working-agreements.md` §6). The source is invented.

Property tests read their example count from `SNAPSHOT_PROPERTY_EXAMPLES` (default 200).
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, cast

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from debate_core.application import snapshot_service as snapshot_service_module
from debate_core.application.errors import (
    BlobIntegrityError,
    NotFound,
    SnapshotIntegrityCheck,
    SnapshotIntegrityError,
)
from debate_core.application.ports import BlobKey
from debate_core.application.snapshot_service import SnapshotService
from debate_core.domain import AccessStatus, ProvenanceMode, SourceSnapshot
from debate_core.evidence.normalization import InvalidTextError, NormalizedText, Paragraph, normalize
from debate_core.evidence.snapshot_text import SnapshotText, decode_snapshot_text, encode_snapshot_text
from debate_core.testing import FAKE_EPOCH, FixedClock, InMemorySnapshotStore, SequentialIdGenerator

PROPERTY_SETTINGS = settings(
    max_examples=int(os.environ.get("SNAPSHOT_PROPERTY_EXAMPLES", "200")),
    deadline=None,  # the first normalize() call builds cached Unicode tables
    suppress_health_check=[HealthCheck.too_slow],
)

ARTICLE_ID = "0ART0000000000000000000001"
URL = "https://example.org/climate/arctic-methane"
EXTRACTOR = "fake-extractor/1.0"
#: 14:05 at UTC+2 is 12:05 UTC.
RETRIEVED_AT_PLUS_TWO = datetime(2026, 9, 30, 14, 5, tzinfo=timezone(timedelta(hours=2)))
RETRIEVED_AT_UTC = datetime(2026, 9, 30, 12, 5, tzinfo=UTC)

#: The response exactly as served: a UTF-8 byte-order mark, CRLF line endings and an em dash.
RAW = (
    b"\xef\xbb\xbf<html>\r\n<body><p>Arctic methane release is accelerating.</p>\r\n"
    b"<p>Ocean heat reached a record \xe2\x80\x94 again.</p></body></html>\r\n"
)
#: What an extractor made of RAW: a no-break space and CRLF breaks, which normalization tidies.
EXTRACTED = "Arctic methane release is\u00a0accelerating.\r\n\r\nOcean heat reached a record — again.\r\n"

#: The normalized text as UTF-8, by hand. Paragraph one is 39 characters, the break takes 39-41, and
#: "Ocean heat reached a record — again." is 36 characters (the em dash is one), so it ends at 77.
NORMALIZED_UTF8 = (
    b"Arctic methane release is accelerating.\n\nOcean heat reached a record \xe2\x80\x94 again."
)
DOCUMENT = (
    b'{"format":"debate-snapshot-text/1","normalizer_version":"evidence-normalizer-v1",'
    b'"paragraphs":[{"end":39,"id":"p0001","start":0},{"end":77,"id":"p0002","start":41}],'
    b'"text":"Arctic methane release is accelerating.\\n\\nOcean heat reached a record \xe2\x80\x94 again."}'
)

RAW_SHA256 = hashlib.sha256(RAW).hexdigest()
NORMALIZED_TEXT_SHA256 = hashlib.sha256(NORMALIZED_UTF8).hexdigest()
DOCUMENT_SHA256 = hashlib.sha256(DOCUMENT).hexdigest()


def run[ResultT](coroutine: Coroutine[Any, Any, ResultT]) -> ResultT:
    """Drive one coroutine to completion; the in-memory stores never suspend."""
    try:
        coroutine.send(None)
    except StopIteration as stopped:
        return cast("ResultT", stopped.value)
    coroutine.close()
    raise AssertionError("an in-memory store suspended; fakes must not perform real I/O")


class TrustingSnapshotStore:
    """A content-addressed store whose read check is missing: it serves whatever it holds.

    Stands in for a store with a broken or absent integrity check, so a test can show that
    `SnapshotService.load` catches altered bytes by its own hashing rather than by the store's.
    """

    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}

    async def put(self, data: bytes) -> BlobKey:
        key = hashlib.sha256(data).hexdigest()
        self.blobs.setdefault(key, data)
        return key

    async def get(self, key: BlobKey) -> bytes:
        if key not in self.blobs:
            raise NotFound("snapshot blob", key)
        return self.blobs[key]

    async def exists(self, key: BlobKey) -> bool:
        return key in self.blobs


class MisfilingSnapshotStore(TrustingSnapshotStore):
    """A store that breaks content addressing: chosen blobs are filed under the digest of something else."""

    def __init__(self, misfile: Callable[[bytes], bool]) -> None:
        super().__init__()
        self._misfile = misfile

    async def put(self, data: bytes) -> BlobKey:
        key = hashlib.sha256(data + b"!" if self._misfile(data) else data).hexdigest()
        self.blobs.setdefault(key, data)
        return key


class UnreadableSnapshotStore(TrustingSnapshotStore):
    """A store that fails the test if anything is read from it."""

    async def get(self, key: BlobKey) -> bytes:
        raise AssertionError("nothing should have been read")


def build_service(
    blobs: InMemorySnapshotStore | TrustingSnapshotStore | None = None,
) -> tuple[SnapshotService, Any]:
    store = InMemorySnapshotStore() if blobs is None else blobs
    service = SnapshotService(
        blobs=store,
        clock=FixedClock(step=timedelta(minutes=1)),
        id_generator=SequentialIdGenerator("SNAP"),
    )
    return service, store


def create(
    service: SnapshotService, raw: bytes = RAW, extracted: str = EXTRACTED, **overrides: Any
) -> SourceSnapshot:
    arguments: dict[str, Any] = {
        "article_id": ARTICLE_ID,
        "raw_bytes": raw,
        "extracted_text": extracted,
        "canonical_url": URL,
        "retrieved_at": RETRIEVED_AT_PLUS_TWO,
        "extractor_version": EXTRACTOR,
        "provenance_mode": ProvenanceMode.PUBLISHER_RETRIEVED,
        "access_status": AccessStatus.ACCESSIBLE,
        "content_type": "text/html; charset=utf-8",
    }
    arguments.update(overrides)
    return run(service.create(**arguments))


def stored_keys(store: InMemorySnapshotStore | TrustingSnapshotStore) -> frozenset[str]:
    if isinstance(store, InMemorySnapshotStore):
        return store.stored_keys()
    return frozenset(store.blobs)


# =============================================================================================
# Creating a snapshot (ac1, ac3)
# =============================================================================================


def test_create_records_both_hashes_both_versions_the_provenance_and_both_blob_keys() -> None:
    """ac1, field by field, against values written by hand."""
    service, _ = build_service()

    snapshot = create(service)

    assert snapshot.model_dump() == {
        "snapshot_id": "0SNAP000000000000000000001",
        "owner_id": None,
        "organization_id": None,
        "article_id": ARTICLE_ID,
        "canonical_url": URL,
        "retrieved_at": RETRIEVED_AT_UTC,
        "access_status": AccessStatus.ACCESSIBLE,
        "provenance_mode": ProvenanceMode.PUBLISHER_RETRIEVED,
        "raw_blob_key": RAW_SHA256,
        "normalized_blob_key": DOCUMENT_SHA256,
        "sha256": RAW_SHA256,
        "normalized_text_hash": NORMALIZED_TEXT_SHA256,
        "extractor_version": EXTRACTOR,
        "normalizer_version": "evidence-normalizer-v1",
        "content_type": "text/html; charset=utf-8",
        "byte_size": len(RAW),
        "created_at": FAKE_EPOCH,
        "updated_at": FAKE_EPOCH,
        "revision": 1,
    }


def test_create_records_retrieved_at_in_utc() -> None:
    service, _ = build_service()

    snapshot = create(service)

    assert snapshot.retrieved_at == RETRIEVED_AT_UTC
    assert snapshot.retrieved_at.utcoffset() == timedelta(0)


def test_create_refuses_a_naive_retrieved_at_before_writing_any_blob() -> None:
    """A timestamp of unknown zone is not provenance. Nothing is stored for a refused snapshot."""
    service, store = build_service()

    with pytest.raises(ValidationError, match="timezone-aware"):
        create(service, retrieved_at=datetime(2026, 9, 30, 12, 5))  # noqa: DTZ001 - the point of the test

    assert stored_keys(store) == frozenset()


def test_create_refuses_text_the_normalizer_rejects_before_writing_any_blob() -> None:
    service, store = build_service()

    with pytest.raises(InvalidTextError):
        create(service, extracted="lone \ud800 surrogate")

    assert stored_keys(store) == frozenset()


def test_create_stores_the_raw_bytes_exactly_as_received() -> None:
    """Byte-order mark and CRLFs included: nothing is decoded, trimmed or re-encoded first."""
    service, store = build_service()

    snapshot = create(service)

    assert run(store.get(snapshot.raw_blob_key)) == RAW
    assert snapshot.sha256 != hashlib.sha256(RAW.removeprefix(b"\xef\xbb\xbf")).hexdigest()


def test_create_stores_the_hand_written_normalized_document() -> None:
    service, store = build_service()

    snapshot = create(service)

    assert run(store.get(snapshot.normalized_blob_key)) == DOCUMENT


def test_create_twice_from_identical_inputs_yields_identical_hashes_and_one_copy_of_each_blob() -> None:
    """ac3. Two records, because each retrieval is its own event; two blobs, not four."""
    service, store = build_service()

    first = create(service)
    second = create(service)

    assert first.snapshot_id != second.snapshot_id
    assert (first.sha256, first.normalized_text_hash) == (second.sha256, second.normalized_text_hash)
    assert (first.raw_blob_key, first.normalized_blob_key) == (
        second.raw_blob_key,
        second.normalized_blob_key,
    )
    assert stored_keys(store) == {RAW_SHA256, DOCUMENT_SHA256}


def test_create_from_a_page_re_served_with_different_markup_shares_the_normalized_blob() -> None:
    """New raw bytes are a new raw blob; the same normalized text is not a new normalized blob."""
    service, store = build_service()
    reserved = RAW.replace(b"<body>", b'<body class="dark">')

    first = create(service)
    second = create(service, raw=reserved, extracted=EXTRACTED.replace("\r\n", "\n"))

    assert second.sha256 == hashlib.sha256(reserved).hexdigest() != first.sha256
    assert second.normalized_text_hash == first.normalized_text_hash == NORMALIZED_TEXT_SHA256
    assert second.normalized_blob_key == first.normalized_blob_key == DOCUMENT_SHA256
    assert stored_keys(store) == {RAW_SHA256, hashlib.sha256(reserved).hexdigest(), DOCUMENT_SHA256}


def test_create_records_the_normalizer_version_that_normalize_reports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The record's version comes from the normalizer's result, never from a constant beside the call.

    Only one version exists today, so the two cannot be told apart by output; this stands in a
    normalizer that reports another version and checks the record and the document follow it.
    """

    def normalize_and_report_another_version(text: str, version: str) -> NormalizedText:
        result = normalize(text, version)
        return NormalizedText(
            result.text, "evidence-normalizer-v1-reported", result.paragraphs, result.offset_map
        )

    monkeypatch.setattr(snapshot_service_module, "normalize", normalize_and_report_another_version)
    service, store = build_service()

    snapshot = create(service)

    assert snapshot.normalizer_version == "evidence-normalizer-v1-reported"
    assert b'"normalizer_version":"evidence-normalizer-v1-reported"' in run(
        store.get(snapshot.normalized_blob_key)
    )


def test_create_of_an_empty_retrieval_hashes_the_empty_string() -> None:
    """An empty body is a legitimate retrieval (a blocked page); its hashes are SHA-256 of nothing."""
    service, store = build_service()
    empty_sha256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    empty_document = (
        b'{"format":"debate-snapshot-text/1","normalizer_version":"evidence-normalizer-v1",'
        b'"paragraphs":[],"text":""}'
    )

    snapshot = create(service, raw=b"", extracted="")

    assert (snapshot.sha256, snapshot.normalized_text_hash, snapshot.byte_size) == (
        empty_sha256,
        empty_sha256,
        0,
    )
    assert run(store.get(snapshot.normalized_blob_key)) == empty_document


def test_create_returns_an_immutable_record() -> None:
    service, _ = build_service()
    snapshot = create(service)

    with pytest.raises(ValidationError):
        snapshot.sha256 = "0" * 64  # type: ignore[misc]


@pytest.mark.parametrize(
    ("misfiled", "expected_check", "expected_key"),
    [
        pytest.param(RAW, SnapshotIntegrityCheck.RAW_BYTES_HASH, RAW_SHA256, id="raw"),
        pytest.param(DOCUMENT, SnapshotIntegrityCheck.NORMALIZED_BLOB_HASH, DOCUMENT_SHA256, id="normalized"),
    ],
)
def test_create_refuses_a_store_that_breaks_content_addressing_as_an_integrity_failure(
    misfiled: bytes, expected_check: SnapshotIntegrityCheck, expected_key: str
) -> None:
    """A store filing a blob under a key that is not its digest would make every load fail later."""
    service, _ = build_service(MisfilingSnapshotStore(lambda data: data == misfiled))

    with pytest.raises(SnapshotIntegrityError) as refused:
        create(service)

    assert refused.value.check is expected_check
    assert refused.value.expected == expected_key


@PROPERTY_SETTINGS
@given(
    raw=st.binary(max_size=300),
    extracted=st.text(alphabet=st.characters(exclude_categories=("Cs",)), max_size=200),
)
def test_create_from_identical_inputs_always_yields_identical_hashes_and_one_copy(
    raw: bytes, extracted: str
) -> None:
    service, store = build_service()

    first = create(service, raw=raw, extracted=extracted)
    second = create(service, raw=raw, extracted=extracted)

    assert first.sha256 == second.sha256 == hashlib.sha256(raw).hexdigest()
    assert first.normalized_text_hash == second.normalized_text_hash
    assert (
        first.normalized_text_hash
        == hashlib.sha256(normalize(extracted, "evidence-normalizer-v1").text.encode()).hexdigest()
    )
    assert first.normalized_blob_key == second.normalized_blob_key
    assert stored_keys(store) == {first.raw_blob_key, first.normalized_blob_key}


# =============================================================================================
# Loading a snapshot with its integrity checked (ac2)
# =============================================================================================


def test_integrity_checked_load_returns_exactly_what_create_stored() -> None:
    service, _ = build_service()
    snapshot = create(service)

    loaded = run(service.load(snapshot))

    assert loaded.snapshot == snapshot
    assert loaded.raw_bytes == RAW
    assert loaded.normalized.text.encode("utf-8") == NORMALIZED_UTF8
    assert loaded.normalized.normalizer_version == "evidence-normalizer-v1"
    assert loaded.normalized.paragraph_text("p0002") == "Ocean heat reached a record — again."


@pytest.mark.parametrize(
    ("which_blob", "expected_check"),
    [
        pytest.param("raw_blob_key", SnapshotIntegrityCheck.RAW_BYTES_HASH, id="raw"),
        pytest.param("normalized_blob_key", SnapshotIntegrityCheck.NORMALIZED_BLOB_HASH, id="normalized"),
    ],
)
def test_integrity_a_blob_the_store_finds_damaged_is_reported_as_this_snapshots_failure(
    which_blob: str, expected_check: SnapshotIntegrityCheck
) -> None:
    service, store = build_service()
    snapshot = create(service)
    key = getattr(snapshot, which_blob)
    store.corrupt(key, b"something else entirely")

    with pytest.raises(SnapshotIntegrityError) as refused:
        run(service.load(snapshot))

    assert refused.value.check is expected_check
    assert refused.value.snapshot_id == snapshot.snapshot_id
    assert isinstance(refused.value.__cause__, BlobIntegrityError)


def _flip_one_bit(data: bytes) -> bytes:
    return data[:-2] + bytes([data[-2] ^ 0x01]) + data[-1:]


def _final_crlf_to_lf(data: bytes) -> bytes:
    return data.removesuffix(b"\r\n") + b"\n"


def _strip_byte_order_mark(data: bytes) -> bytes:
    return data.removeprefix(b"\xef\xbb\xbf")


def _accelerating_to_decelerating(data: bytes) -> bytes:
    return data.replace(b"accelerating", b"decelerating")


@pytest.mark.parametrize(
    ("which_blob", "damage", "expected_check"),
    [
        pytest.param("raw_blob_key", _flip_one_bit, SnapshotIntegrityCheck.RAW_BYTES_HASH, id="raw-bit-flip"),
        pytest.param(
            "raw_blob_key", _final_crlf_to_lf, SnapshotIntegrityCheck.RAW_BYTES_HASH, id="raw-crlf-to-lf"
        ),
        pytest.param(
            "raw_blob_key",
            _strip_byte_order_mark,
            SnapshotIntegrityCheck.RAW_BYTES_HASH,
            id="raw-bom-stripped",
        ),
        pytest.param(
            "normalized_blob_key",
            _accelerating_to_decelerating,
            SnapshotIntegrityCheck.NORMALIZED_BLOB_HASH,
            id="normalized-word-changed",
        ),
        pytest.param(
            "normalized_blob_key",
            _flip_one_bit,
            SnapshotIntegrityCheck.NORMALIZED_BLOB_HASH,
            id="normalized-bit-flip",
        ),
    ],
)
def test_integrity_altered_bytes_are_caught_by_the_service_even_when_the_store_serves_them(
    which_blob: str, damage: Callable[[bytes], bytes], expected_check: SnapshotIntegrityCheck
) -> None:
    """The store here never checks what it serves; `load` must not depend on it doing so."""
    store = TrustingSnapshotStore()
    service, _ = build_service(store)
    snapshot = create(service)
    key = getattr(snapshot, which_blob)
    store.blobs[key] = damage(store.blobs[key])

    with pytest.raises(SnapshotIntegrityError) as refused:
        run(service.load(snapshot))

    assert refused.value.check is expected_check
    assert refused.value.expected == key


def test_integrity_a_record_pointing_at_another_snapshots_raw_blob_is_refused() -> None:
    """Both blobs are intact; the record's key and its sha256 just do not belong together."""
    service, _ = build_service()
    snapshot = create(service)
    other = create(service, raw=b"<p>An unrelated page.</p>", extracted="An unrelated page.")

    with pytest.raises(SnapshotIntegrityError) as refused:
        run(service.load(snapshot.evolve(raw_blob_key=other.raw_blob_key)))

    assert refused.value.check is SnapshotIntegrityCheck.RAW_BYTES_HASH
    assert (refused.value.expected, refused.value.actual) == (RAW_SHA256, other.sha256)


def test_integrity_a_record_pointing_at_another_snapshots_normalized_blob_is_refused() -> None:
    service, _ = build_service()
    snapshot = create(service)
    other = create(service, raw=b"<p>An unrelated page.</p>", extracted="An unrelated page.")

    with pytest.raises(SnapshotIntegrityError) as refused:
        run(service.load(snapshot.evolve(normalized_blob_key=other.normalized_blob_key)))

    assert refused.value.check is SnapshotIntegrityCheck.NORMALIZED_TEXT_HASH
    assert (refused.value.expected, refused.value.actual) == (
        NORMALIZED_TEXT_SHA256,
        other.normalized_text_hash,
    )


@pytest.mark.parametrize(
    ("change", "expected_check"),
    [
        pytest.param({"sha256": "0" * 64}, SnapshotIntegrityCheck.RAW_BYTES_HASH, id="sha256"),
        pytest.param(
            {"normalized_text_hash": "0" * 64}, SnapshotIntegrityCheck.NORMALIZED_TEXT_HASH, id="text-hash"
        ),
        pytest.param({"byte_size": len(RAW) + 1}, SnapshotIntegrityCheck.RAW_BYTE_SIZE, id="byte-size"),
        pytest.param(
            {"normalizer_version": "evidence-normalizer-v9"},
            SnapshotIntegrityCheck.UNKNOWN_NORMALIZER_VERSION,
            id="unknown-normalizer-version",
        ),
    ],
)
def test_integrity_a_record_whose_hashes_or_versions_were_changed_is_refused(
    change: dict[str, Any], expected_check: SnapshotIntegrityCheck
) -> None:
    service, _ = build_service()
    snapshot = create(service)

    with pytest.raises(SnapshotIntegrityError) as refused:
        run(service.load(snapshot.evolve(**change)))

    assert refused.value.check is expected_check


def test_integrity_an_unknown_normalizer_version_is_refused_before_anything_is_read() -> None:
    service, _ = build_service(UnreadableSnapshotStore())
    snapshot = SourceSnapshot(
        article_id=ARTICLE_ID,
        canonical_url=URL,
        retrieved_at=RETRIEVED_AT_UTC,
        access_status=AccessStatus.ACCESSIBLE,
        provenance_mode=ProvenanceMode.USER_SUPPLIED,
        raw_blob_key=RAW_SHA256,
        normalized_blob_key=DOCUMENT_SHA256,
        sha256=RAW_SHA256,
        normalized_text_hash=NORMALIZED_TEXT_SHA256,
        extractor_version=EXTRACTOR,
        normalizer_version="evidence-normalizer-v0",
    )

    with pytest.raises(SnapshotIntegrityError) as refused:
        run(service.load(snapshot))

    assert refused.value.check is SnapshotIntegrityCheck.UNKNOWN_NORMALIZER_VERSION
    assert refused.value.actual == "evidence-normalizer-v0"


def test_integrity_a_non_canonical_normalized_document_is_refused_as_malformed() -> None:
    """Same text, same hash, but spelled with a space: a second key for the same content is refused."""
    service, store = build_service()
    snapshot = create(service)
    respelled = DOCUMENT.replace(b'"format":', b'"format": ')
    respelled_key = run(store.put(respelled))

    with pytest.raises(SnapshotIntegrityError) as refused:
        run(service.load(snapshot.evolve(normalized_blob_key=respelled_key)))

    assert refused.value.check is SnapshotIntegrityCheck.NORMALIZED_BLOB_MALFORMED


def test_integrity_a_document_written_under_another_normalizer_version_is_refused() -> None:
    service, store = build_service()
    snapshot = create(service)
    other_version = DOCUMENT.replace(b'"evidence-normalizer-v1"', b'"evidence-normalizer-v0"')
    other_key = run(store.put(other_version))

    with pytest.raises(SnapshotIntegrityError) as refused:
        run(service.load(snapshot.evolve(normalized_blob_key=other_key)))

    assert refused.value.check is SnapshotIntegrityCheck.NORMALIZER_VERSION_MISMATCH
    assert (refused.value.expected, refused.value.actual) == (
        "evidence-normalizer-v1",
        "evidence-normalizer-v0",
    )


def test_integrity_a_missing_blob_is_not_found_rather_than_damaged() -> None:
    """Missing and damaged are different findings for the verifier, so they are different errors."""
    snapshot = create(build_service()[0])
    service_over_an_empty_store, _ = build_service()

    with pytest.raises(NotFound):
        run(service_over_an_empty_store.load(snapshot))


def test_integrity_a_paragraph_map_altered_into_another_valid_document_is_refused() -> None:
    """Only the normalized blob's own hash catches this edit; the text and its hash are untouched.

    The altered document is valid and canonical, names the same version and holds the same text, so
    every other check passes. Span extraction resolves paragraph IDs through this map
    (`v1-e03-t03`), so a nudged boundary would quietly move a card's evidence.
    """
    store = TrustingSnapshotStore()
    service, _ = build_service(store)
    snapshot = create(service)
    altered = DOCUMENT.replace(b'"end":77', b'"end":76')
    altered_key = hashlib.sha256(altered).hexdigest()  # a valid document under its own key
    assert decode_snapshot_text(altered, expected_key=altered_key).text.encode("utf-8") == NORMALIZED_UTF8
    store.blobs[snapshot.normalized_blob_key] = altered

    with pytest.raises(SnapshotIntegrityError) as refused:
        run(service.load(snapshot))

    assert refused.value.check is SnapshotIntegrityCheck.NORMALIZED_BLOB_HASH


def _with_last_paragraph_moved(document: bytes) -> bytes | None:
    """The same text with its last paragraph boundary moved: a valid, canonical, different document."""
    stored = decode_snapshot_text(document, expected_key=hashlib.sha256(document).hexdigest())
    if not stored.paragraphs:
        return None
    last = stored.paragraphs[-1]
    moved = (
        Paragraph(last.paragraph_id, last.start, last.end - 1)
        if last.end > last.start
        else Paragraph("p9999", last.start, last.end)
    )
    return encode_snapshot_text(
        SnapshotText(stored.text, stored.normalizer_version, (*stored.paragraphs[:-1], moved))
    )


@PROPERTY_SETTINGS
@given(
    raw=st.binary(min_size=1, max_size=300),
    extracted=st.text(alphabet=st.characters(exclude_categories=("Cs",)), max_size=200),
    data=st.data(),
)
def test_integrity_any_change_to_either_blob_is_refused(
    raw: bytes, extracted: str, data: st.DataObject
) -> None:
    """Against a store that does not check, so every refusal here is the service's own.

    Two kinds of change: one substituted byte in either blob, and a paragraph map rewritten into
    another valid document with the same text. Random bytes alone almost never produce the second,
    and a deep run of the byte-only version passed with the normalized blob's re-hash removed.
    """
    store = TrustingSnapshotStore()
    service, _ = build_service(store)
    snapshot = create(service, raw=raw, extracted=extracted)
    change = data.draw(st.sampled_from(["byte", "paragraph map"]), label="change")
    altered_document = _with_last_paragraph_moved(store.blobs[snapshot.normalized_blob_key])
    if change == "paragraph map" and altered_document is not None:
        store.blobs[snapshot.normalized_blob_key] = altered_document
    else:
        key = data.draw(st.sampled_from([snapshot.raw_blob_key, snapshot.normalized_blob_key]), label="blob")
        stored = store.blobs[key]
        position = data.draw(st.integers(min_value=0, max_value=len(stored) - 1), label="position")
        replacement = data.draw(
            st.integers(min_value=0, max_value=255).filter(lambda byte: byte != stored[position])
        )
        store.blobs[key] = stored[:position] + bytes([replacement]) + stored[position + 1 :]

    with pytest.raises(SnapshotIntegrityError):
        run(service.load(snapshot))


@PROPERTY_SETTINGS
@given(
    raw=st.binary(max_size=300),
    extracted=st.text(alphabet=st.characters(exclude_categories=("Cs",)), max_size=200),
)
def test_integrity_checked_load_round_trips_any_retrieval(raw: bytes, extracted: str) -> None:
    service, _ = build_service()
    snapshot = create(service, raw=raw, extracted=extracted)
    expected = normalize(extracted, "evidence-normalizer-v1")

    loaded = run(service.load(snapshot))

    assert loaded.raw_bytes == raw
    assert (loaded.normalized.text, loaded.normalized.paragraphs) == (expected.text, expected.paragraphs)
