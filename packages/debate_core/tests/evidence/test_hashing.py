"""The snapshot hash helpers match published SHA-256 vectors and hash text as BOM-less UTF-8.

Every expected digest below is copied from the SHA-256 examples published with FIPS 180-2 (NIST's
"SHA-256 example" vectors) and every expected byte string is UTF-8 written out by hand, so no
expectation was produced by the code under test or by `hashlib` (`docs/process/working-agreements.md`
§6).
"""

from __future__ import annotations

import re

import pytest

from debate_core.evidence.hashing import sha256_bytes, sha256_text

#: (message, digest) pairs from the FIPS 180-2 SHA-256 examples, plus the empty message.
FIPS_180_2_VECTORS = [
    pytest.param(b"", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", id="empty"),
    pytest.param(b"abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", id="abc"),
    pytest.param(
        b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq",
        "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1",
        id="448-bit",
    ),
    pytest.param(
        b"abcdefghbcdefghicdefghijdefghijkefghijklfghijklmghijklmnhijklmnoijklmnopjklmnopqklmnopqrlmnopqrs"
        b"mnopqrstnopqrstu",
        "cf5b16a778af8380036ce59e7b0492370b249b11e8f07a51afac45037afee9d1",
        id="896-bit",
    ),
    pytest.param(
        b"a" * 1_000_000,
        "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0",
        id="one-million-a",
    ),
]

LOWERCASE_HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")

BYTE_ORDER_MARK_UTF8 = b"\xef\xbb\xbf"


# ---------------------------------------------------------------------------------------------
# Raw bytes
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("message", "digest"), FIPS_180_2_VECTORS)
def test_sha256_bytes_matches_the_published_vectors(message: bytes, digest: str) -> None:
    assert sha256_bytes(message) == digest


@pytest.mark.parametrize(("message", "digest"), FIPS_180_2_VECTORS)
def test_digests_are_64_lowercase_hex_characters(message: bytes, digest: str) -> None:
    """The form `Sha256Hex` accepts and blob keys take, so the two compare as plain strings."""
    assert LOWERCASE_HEX_DIGEST.match(sha256_bytes(message))
    assert LOWERCASE_HEX_DIGEST.match(sha256_text(message.decode("ascii")))


def test_sha256_bytes_hashes_bytes_that_are_not_text_without_touching_them() -> None:
    """Raw content is often not UTF-8 at all. It is hashed as it came, not decoded and re-encoded.

    `b"\\xff\\xfe"` is not valid UTF-8 and `b"\\r\\n"` is the line ending a decode-and-normalize
    step would most likely rewrite; the digest must change when either is touched.
    """
    raw = b"\xff\xfe<p>caf\xe9</p>\r\n"

    digest = sha256_bytes(raw)

    assert digest != sha256_bytes(raw.replace(b"\r\n", b"\n"))
    assert digest != sha256_bytes(raw.decode("latin-1").encode("utf-8"))
    assert digest == sha256_bytes(bytes(raw))


@pytest.mark.parametrize(
    "not_bytes",
    [
        pytest.param("abc", id="str"),
        pytest.param(bytearray(b"abc"), id="bytearray"),
        pytest.param(memoryview(b"abc"), id="memoryview"),
    ],
)
def test_sha256_bytes_refuses_anything_but_bytes(not_bytes: object) -> None:
    """A `str` would have to be encoded first, which is hashing a copy rather than stored bytes."""
    with pytest.raises(TypeError):
        sha256_bytes(not_bytes)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------------------------
# Normalized text
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("message", "digest"), FIPS_180_2_VECTORS)
def test_sha256_text_of_ascii_text_matches_the_published_vectors(message: bytes, digest: str) -> None:
    assert sha256_text(message.decode("ascii")) == digest


@pytest.mark.parametrize(
    ("text", "utf8"),
    [
        pytest.param("café", b"caf\xc3\xa9", id="two-byte"),
        pytest.param("café", b"cafe\xcc\x81", id="combining-mark-not-composed"),
        pytest.param("“quoted” — dash", b"\xe2\x80\x9cquoted\xe2\x80\x9d \xe2\x80\x94 dash", id="three-byte"),
        pytest.param("\U0001f30a", b"\xf0\x9f\x8c\x8a", id="four-byte"),
        pytest.param("ماء", b"\xd9\x85\xd8\xa7\xd8\xa1", id="arabic"),
    ],
)
def test_sha256_text_hashes_the_utf8_encoding(text: str, utf8: bytes) -> None:
    """The UTF-8 bytes are written out by hand; the text hash is the hash of exactly those bytes."""
    assert sha256_text(text) == sha256_bytes(utf8)


@pytest.mark.parametrize(
    "wrong_encoding",
    [
        pytest.param(BYTE_ORDER_MARK_UTF8 + b"caf\xc3\xa9", id="utf-8-with-bom"),
        pytest.param(b"caf\xe9", id="latin-1"),
        pytest.param(b"\xff\xfec\x00a\x00f\x00\xe9\x00", id="utf-16-with-bom"),
        pytest.param(b"c\x00a\x00f\x00\xe9\x00", id="utf-16-le"),
        pytest.param(b"cafe\xcc\x81", id="decomposed"),
    ],
)
def test_sha256_text_is_not_the_hash_of_any_other_encoding(wrong_encoding: bytes) -> None:
    """In particular not UTF-8 with a byte-order mark, which `"utf-8-sig"` would write."""
    assert sha256_text("café") != sha256_bytes(wrong_encoding)


def test_sha256_text_does_not_normalize_the_text_it_is_given() -> None:
    """Normalization is the caller's step, recorded with its version; the hash adds no rules of its own."""
    assert sha256_text("café") != sha256_text("café")
    assert sha256_text("a  b") != sha256_text("a b")
    assert sha256_text("A") != sha256_text("a")


def test_a_leading_feff_in_the_text_is_hashed_as_content_and_not_stripped() -> None:
    """The helper adds no BOM and removes none. The v1 normalizer has already deleted U+FEFF, so in a
    snapshot it never reaches the hash; here it is hashed as the three bytes it encodes to."""
    assert sha256_text("﻿abc") == sha256_bytes(BYTE_ORDER_MARK_UTF8 + b"abc")
    assert sha256_text("﻿abc") != sha256_text("abc")


def test_sha256_text_refuses_text_with_a_lone_surrogate() -> None:
    """It has no UTF-8 encoding; hashing a replacement character instead would hash other text."""
    with pytest.raises(UnicodeEncodeError):
        sha256_text("before \ud800 after")


@pytest.mark.parametrize("not_text", [pytest.param(b"abc", id="bytes"), pytest.param(None, id="none")])
def test_sha256_text_refuses_anything_but_str(not_text: object) -> None:
    """Hashing a blob's bytes is not hashing its text, and must not pass for it."""
    with pytest.raises(TypeError):
        sha256_text(not_text)  # type: ignore[arg-type]
