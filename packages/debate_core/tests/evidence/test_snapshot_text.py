"""The stored form of a snapshot's normalized text: one canonical JSON document, read back strictly.

Expected documents are written out by hand, byte for byte, from the format described in
`debate_core.evidence.snapshot_text`, never captured from the encoder (`docs/process/working-agreements.md`
§6). The text is invented.

Property tests take their example count from `SNAPSHOT_PROPERTY_EXAMPLES` (default 200), so a deep
run is `SNAPSHOT_PROPERTY_EXAMPLES=20000 uv run pytest ...`.
"""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import os
import pkgutil
import re
from collections.abc import Callable, Iterator

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import debate_core
from debate_core.evidence.normalization import NORMALIZER_VERSION, Paragraph, UnknownParagraphError, normalize
from debate_core.evidence.snapshot_text import (
    MalformedSnapshotText,
    SnapshotText,
    SnapshotTextKeyMismatch,
    decode_snapshot_text,
    encode_snapshot_text,
)

V1 = "evidence-normalizer-v1"

PROPERTY_SETTINGS = settings(
    max_examples=int(os.environ.get("SNAPSHOT_PROPERTY_EXAMPLES", "200")),
    deadline=None,  # the first normalize() call builds cached Unicode tables
    suppress_health_check=[HealthCheck.too_slow],
)

#: Raw extracted text with CRLF line breaks, a doubled space and a trailing newline.
EXTRACTED = "Arctic methane is accelerating.\r\n\r\nOcean heat  reached a new high.\n"

#: What EXTRACTED normalizes to, and its document, both written by hand. "Arctic methane is
#: accelerating." is 31 characters, the break takes 31-33, and "Ocean heat reached a new high." is 30.
NORMALIZED = "Arctic methane is accelerating.\n\nOcean heat reached a new high."
DOCUMENT = (
    b'{"format":"debate-snapshot-text/1",'
    b'"normalizer_version":"evidence-normalizer-v1",'
    b'"paragraphs":[{"end":31,"id":"p0001","start":0},{"end":63,"id":"p0002","start":33}],'
    b'"text":"Arctic methane is accelerating.\\n\\nOcean heat reached a new high."}'
)
DOCUMENT_KEY = hashlib.sha256(DOCUMENT).hexdigest()
STORED = SnapshotText(
    text=NORMALIZED,
    normalizer_version=V1,
    paragraphs=(Paragraph("p0001", 0, 31), Paragraph("p0002", 33, 63)),
)


def decode_under_its_own_key(data: bytes) -> SnapshotText:
    """Decode with the key computed from ``data`` itself, which production code must never do.

    It stands in for a blob read from a content-addressed store under its own correct key, so the
    tests that use it exercise the structural and canonical checks rather than the key check. The
    key check has tests of its own, below.
    """
    return decode_snapshot_text(data, expected_key=hashlib.sha256(data).hexdigest())


# ---------------------------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------------------------


def test_a_normalizer_result_encodes_to_the_hand_written_document() -> None:
    assert encode_snapshot_text(SnapshotText.from_normalized(normalize(EXTRACTED, V1))) == DOCUMENT


def test_the_stored_text_takes_the_version_from_the_normalizer_result() -> None:
    stored = SnapshotText.from_normalized(normalize(EXTRACTED, NORMALIZER_VERSION))

    assert stored == STORED


def test_non_ascii_text_is_written_as_utf8_rather_than_escaped() -> None:
    """`Café — “quoted”` is 15 characters; é, the em dash and the curly quotes appear as UTF-8 bytes."""
    stored = SnapshotText("Café — “quoted”", V1, (Paragraph("p0001", 0, 15),))

    assert encode_snapshot_text(stored) == (
        b'{"format":"debate-snapshot-text/1","normalizer_version":"evidence-normalizer-v1",'
        b'"paragraphs":[{"end":15,"id":"p0001","start":0}],'
        b'"text":"Caf\xc3\xa9 \xe2\x80\x94 \xe2\x80\x9cquoted\xe2\x80\x9d"}'
    )


def test_empty_text_encodes_with_no_paragraphs() -> None:
    assert encode_snapshot_text(SnapshotText.from_normalized(normalize(" \n\n ", V1))) == (
        b'{"format":"debate-snapshot-text/1","normalizer_version":"evidence-normalizer-v1",'
        b'"paragraphs":[],"text":""}'
    )


def test_the_offset_map_is_not_stored_so_extractor_whitespace_does_not_change_the_document() -> None:
    """Two extractions differing only in whitespace normalize alike and must share one blob."""
    tidy = normalize("Arctic methane is accelerating.\n\nOcean heat reached a new high.", V1)
    messy = normalize(EXTRACTED, V1)
    assert tidy.offset_map != messy.offset_map

    assert encode_snapshot_text(SnapshotText.from_normalized(tidy)) == encode_snapshot_text(
        SnapshotText.from_normalized(messy)
    )


def test_paragraph_lookups_slice_the_stored_text() -> None:
    assert STORED.paragraph_text("p0002") == "Ocean heat reached a new high."
    with pytest.raises(UnknownParagraphError):
        STORED.paragraph("p0003")


# ---------------------------------------------------------------------------------------------
# Decoding
# ---------------------------------------------------------------------------------------------


def test_the_hand_written_document_decodes_to_the_stored_text() -> None:
    assert decode_snapshot_text(DOCUMENT, expected_key=DOCUMENT_KEY) == STORED


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(b"\xff\xfe", id="not-utf8"),
        pytest.param(b"\xef\xbb\xbf" + DOCUMENT, id="utf8-bom-prefixed"),
        pytest.param(b"{", id="not-json"),
        pytest.param(b"[]", id="array-not-object"),
        pytest.param(DOCUMENT.replace(b'"format":"debate-snapshot-text/1",', b""), id="missing-format"),
        pytest.param(DOCUMENT.replace(b"/1", b"/2"), id="unknown-format"),
        pytest.param(DOCUMENT[:-1] + b',"url":"https://example.org"}', id="extra-key"),
        pytest.param(DOCUMENT.replace(b'"evidence-normalizer-v1"', b'""'), id="empty-version"),
        pytest.param(DOCUMENT.replace(b'"evidence-normalizer-v1"', b"1"), id="numeric-version"),
        pytest.param(
            b'{"format":"debate-snapshot-text/1","normalizer_version":"evidence-normalizer-v1",'
            b'"paragraphs":{},"text":""}',
            id="paragraphs-not-a-list",
        ),
        pytest.param(
            b'{"format":"debate-snapshot-text/1","normalizer_version":"evidence-normalizer-v1",'
            b'"paragraphs":[],"text":1}',
            id="text-not-a-string",
        ),
        pytest.param(DOCUMENT.replace(b'"start":0', b'"start":false'), id="boolean-offset"),
        pytest.param(DOCUMENT.replace(b'"start":0', b'"start":0.0'), id="float-offset"),
        pytest.param(DOCUMENT.replace(b'"start":0', b'"start":-1'), id="negative-start"),
        pytest.param(DOCUMENT.replace(b'"end":63', b'"end":64'), id="end-beyond-text"),
        pytest.param(DOCUMENT.replace(b'"end":31', b'"end":34'), id="overlapping"),
        pytest.param(
            DOCUMENT.replace(
                b'{"end":31,"id":"p0001","start":0},{"end":63,"id":"p0002","start":33}',
                b'{"end":63,"id":"p0002","start":33},{"end":31,"id":"p0001","start":0}',
            ),
            id="out-of-order",
        ),
        pytest.param(DOCUMENT.replace(b'"p0002"', b'"p0001"'), id="duplicate-id"),
        pytest.param(DOCUMENT.replace(b'"p0002"', b'""'), id="empty-id"),
        pytest.param(DOCUMENT.replace(b'"id":"p0002",', b""), id="paragraph-missing-id"),
        pytest.param(DOCUMENT.replace(b'"start":33}', b'"start":33,"kind":"tag"}'), id="paragraph-extra-key"),
        pytest.param(DOCUMENT.replace(b"[{", b"[1,{"), id="paragraph-not-an-object"),
    ],
)
def test_a_document_with_the_wrong_structure_is_refused(data: bytes) -> None:
    with pytest.raises(MalformedSnapshotText):
        decode_under_its_own_key(data)


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(DOCUMENT.replace(b'"format":', b'"format": '), id="added-whitespace"),
        pytest.param(DOCUMENT + b"\n", id="trailing-newline"),
        pytest.param(
            b'{"normalizer_version":"evidence-normalizer-v1","format":"debate-snapshot-text/1",'
            + DOCUMENT[
                len(b'{"format":"debate-snapshot-text/1","normalizer_version":"evidence-normalizer-v1",') :
            ],
            id="keys-reordered",
        ),
        pytest.param(DOCUMENT.replace(b"Arctic", b"\\u0041rctic"), id="ascii-escaped"),
        pytest.param(
            DOCUMENT[:-1] + b',"text":"Arctic methane is accelerating.\\n\\nOcean heat reached a new high."}',
            id="duplicated-key",
        ),
        pytest.param(DOCUMENT.replace(b"Arctic", b"\\ud800rctic"), id="lone-surrogate-escape"),
    ],
)
def test_a_non_canonical_spelling_of_the_document_is_refused(data: bytes) -> None:
    """Any second spelling would be a second blob key for the same content."""
    with pytest.raises(MalformedSnapshotText):
        decode_under_its_own_key(data)


# ---------------------------------------------------------------------------------------------
# The key check
# ---------------------------------------------------------------------------------------------


def test_decoding_requires_the_key_as_a_keyword_with_no_default() -> None:
    """There is no call that turns bytes into a `SnapshotText` without saying which key they belong to."""
    expected_key = inspect.signature(decode_snapshot_text).parameters["expected_key"]

    assert expected_key.kind is inspect.Parameter.KEYWORD_ONLY
    assert expected_key.default is inspect.Parameter.empty


def test_bytes_that_do_not_hash_to_their_key_are_refused_before_they_are_parsed() -> None:
    """`{` is not even JSON; the refusal is still the key mismatch, so nothing unchecked was read."""
    with pytest.raises(SnapshotTextKeyMismatch) as refused:
        decode_snapshot_text(b"{", expected_key=DOCUMENT_KEY)

    assert refused.value.expected_key == DOCUMENT_KEY
    assert refused.value.actual_key == hashlib.sha256(b"{").hexdigest()


def test_a_paragraph_boundary_moved_to_another_valid_offset_is_refused_under_the_original_key() -> None:
    """The edit only the key catches: valid, canonical, same version, same text."""
    moved = DOCUMENT.replace(b'"end":63', b'"end":62')
    assert decode_under_its_own_key(moved).text == STORED.text  # a perfectly good document

    with pytest.raises(SnapshotTextKeyMismatch):
        decode_snapshot_text(moved, expected_key=DOCUMENT_KEY)


#: Parameter annotations that could carry a serialized document.
_SERIALIZED = re.compile(r"\b(bytes|bytearray|memoryview|str|object|Any)\b")
_RETURNS_SNAPSHOT_TEXT = re.compile(r"\bSnapshotText\b")


def _debate_core_callables() -> Iterator[tuple[str, Callable[..., object]]]:
    """Every function, and every method of every class, defined anywhere in `debate_core`."""
    for info in pkgutil.walk_packages(debate_core.__path__, "debate_core."):
        module = importlib.import_module(info.name)
        for name, value in vars(module).items():
            if getattr(value, "__module__", None) != module.__name__:
                continue
            if inspect.isfunction(value):
                yield f"{module.__name__}.{name}", value
            elif inspect.isclass(value):
                for member_name, member in vars(value).items():
                    function = getattr(member, "__func__", member)  # unwrap classmethod/staticmethod
                    if inspect.isfunction(function) and not member_name.startswith("__"):
                        yield f"{module.__name__}.{name}.{member_name}", function


def test_nothing_in_debate_core_turns_serialized_text_into_a_snapshot_text_without_a_key() -> None:
    """Fails if an unkeyed way from bytes (or a string) back to a `SnapshotText` appears anywhere.

    The paragraph map in a `SnapshotText` is trustworthy only when the bytes it came from were
    checked against their key, so every callable that returns one from serialized input must
    require `expected_key`. What this cannot see is a caller that parses the JSON itself and calls
    the `SnapshotText` constructor; that would be deliberate, and is left to review.
    """
    found: list[str] = []
    unkeyed: list[str] = []
    for qualified_name, function in _debate_core_callables():
        signature = inspect.signature(function, eval_str=False)
        if not _RETURNS_SNAPSHOT_TEXT.search(str(signature.return_annotation)):
            continue
        if not any(
            _SERIALIZED.search(str(parameter.annotation)) for parameter in signature.parameters.values()
        ):
            continue
        found.append(qualified_name)
        key = signature.parameters.get("expected_key")
        if (
            key is None
            or key.kind is not inspect.Parameter.KEYWORD_ONLY
            or key.default is not inspect.Parameter.empty
        ):
            unkeyed.append(qualified_name)

    assert "debate_core.evidence.snapshot_text.decode_snapshot_text" in found, "the scan saw nothing"
    assert unkeyed == []


# ---------------------------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------------------------

#: Arbitrary non-surrogate text, enriched with the characters the v1 rules act on.
EXTRACTED_TEXT = st.text(
    alphabet=st.one_of(
        st.characters(exclude_categories=("Cs",)),
        st.sampled_from(list(' \t\n\r\u00a0\u2028\u2029\u00ad\u200b\ufeffe\u0301"\\')),
    ),
    max_size=200,
)


@PROPERTY_SETTINGS
@given(EXTRACTED_TEXT)
def test_every_normalizer_result_round_trips_through_its_document(extracted: str) -> None:
    stored = SnapshotText.from_normalized(normalize(extracted, V1))

    assert decode_under_its_own_key(encode_snapshot_text(stored)) == stored


@PROPERTY_SETTINGS
@given(EXTRACTED_TEXT, st.data())
def test_no_single_byte_change_to_a_document_decodes_to_the_same_content(
    extracted: str, data: st.DataObject
) -> None:
    """A changed byte is refused or reads as different content; it never passes as the original.

    This guards the outcome, not any one check, and mutation testing shows what that means: it
    fails only when two checks are gone together. A changed format identifier is refused by the
    format check and, independently, by the canonical re-encoding, so removing either alone leaves
    this passing. It also cannot exercise the canonical check on its own, because no one-byte
    substitution turns a canonical document into another spelling of the same content; that is
    `test_every_other_json_spelling_of_a_document_is_refused`. A 50,000-example run passed with the
    canonical check removed, which is how that was found.
    """
    stored = SnapshotText.from_normalized(normalize(extracted, V1))
    document = encode_snapshot_text(stored)
    position = data.draw(st.integers(min_value=0, max_value=len(document) - 1), label="position")
    replacement = data.draw(
        st.integers(min_value=0, max_value=255).filter(lambda byte: byte != document[position])
    )
    altered = document[:position] + bytes([replacement]) + document[position + 1 :]

    try:
        decoded = decode_under_its_own_key(altered)
    except MalformedSnapshotText:
        return
    assert decoded != stored


@PROPERTY_SETTINGS
@given(
    EXTRACTED_TEXT,
    st.sampled_from([None, 0, 1]),
    st.sampled_from([(",", ":"), (", ", ": "), (",", ": "), (", ", ":")]),
    st.booleans(),
    st.booleans(),
)
def test_every_other_json_spelling_of_a_document_is_refused(
    extracted: str,
    indent: int | None,
    separators: tuple[str, str],
    ensure_ascii: bool,
    reverse_keys: bool,
) -> None:
    """The same content written any other way JSON allows is refused; only the canonical bytes decode.

    A second accepted spelling would be a second blob key for one normalized text, and the check
    that prevents it is the canonical re-encoding at the end of `decode_snapshot_text`.
    """
    stored = SnapshotText.from_normalized(normalize(extracted, V1))
    canonical = encode_snapshot_text(stored)
    document = json.loads(canonical)
    if reverse_keys:
        document = dict(reversed(document.items()))
    respelled = json.dumps(
        document, indent=indent, separators=separators, ensure_ascii=ensure_ascii, sort_keys=False
    ).encode("utf-8")

    if respelled == canonical:
        assert decode_under_its_own_key(respelled) == stored
    else:
        with pytest.raises(MalformedSnapshotText):
            decode_under_its_own_key(respelled)
