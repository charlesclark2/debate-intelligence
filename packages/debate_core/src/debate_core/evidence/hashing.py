"""The two SHA-256 digests a source snapshot is anchored by.

A :class:`~debate_core.domain.SourceSnapshot` records two hashes, and they hash different things on
purpose (architecture proposal §8, steps 1-2):

* :func:`sha256_bytes` hashes **the exact bytes that came back** from a retrieval — the HTML, the
  PDF, whatever the source served. Nothing is decoded, re-encoded or trimmed first. A snapshot's
  `sha256` answers "are these the bytes we received?", and any transformation before hashing would
  make the answer "these are bytes we derived from what we received", which is a different claim.
* :func:`sha256_text` hashes **normalized text** as UTF-8 with no byte-order mark. A snapshot's
  `normalized_text_hash` answers "is this the text cards were cut from?".

Both return lowercase hex, which is the form :data:`~debate_core.domain.Sha256Hex` accepts and the
form every content-addressed key in the platform takes (`debate_core.integrations.local.
fs_blob_store`), so a digest can be compared with a blob key as plain strings.

The functions are deliberately strict about their input types. `sha256_bytes` refuses `str`, so
nobody can hash raw content by encoding a decoded copy of it; `sha256_text` refuses `bytes`, so
nobody can hash a blob and call it a text hash. Python's `"utf-8"` codec never writes a BOM (only
`"utf-8-sig"` does), and it is used with `errors="strict"`, so text that cannot be encoded — a lone
surrogate — raises instead of being hashed as replacement characters.
"""

from __future__ import annotations

import hashlib

from debate_core.domain import Sha256Hex

__all__ = ["TEXT_ENCODING", "sha256_bytes", "sha256_text"]

TEXT_ENCODING = "utf-8"
"""The encoding normalized text is hashed in. Plain UTF-8: no byte-order mark, no other form."""


def sha256_bytes(data: bytes) -> Sha256Hex:
    """Return the lowercase hex SHA-256 of `data`, exactly as given.

    Raises :class:`TypeError` for anything that is not `bytes` — including `str`, which would
    otherwise invite hashing an encoded copy instead of the stored bytes, and `bytearray`, whose
    contents could change between hashing and storing.
    """
    if type(data) is not bytes:  # exact type, checked at run time for untyped callers
        raise TypeError(f"sha256_bytes hashes stored bytes as they are; got {type(data).__name__}")
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> Sha256Hex:
    """Return the lowercase hex SHA-256 of `text` encoded as UTF-8 without a byte-order mark.

    The text is hashed as given. It is not normalized here: the caller hashes the output of
    :func:`~debate_core.evidence.normalization.normalize`, and the digest is only as meaningful as
    the normalizer version recorded beside it.

    Raises :class:`TypeError` for anything that is not `str`, and :class:`UnicodeEncodeError` for
    text containing a lone surrogate, which has no UTF-8 encoding.
    """
    if type(text) is not str:  # exact type, checked at run time for untyped callers
        raise TypeError(f"sha256_text hashes text; got {type(text).__name__}")
    return hashlib.sha256(text.encode(TEXT_ENCODING, errors="strict")).hexdigest()
