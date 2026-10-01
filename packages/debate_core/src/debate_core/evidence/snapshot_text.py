"""The stored form of a snapshot's normalized text: one canonical JSON document per text.

A :class:`~debate_core.domain.SourceSnapshot` keeps two blobs. The raw blob is the bytes a source
served. The normalized blob is this document: the normalized text, the normalizer version that
produced it, and its paragraph map, which is what span extraction (`v1-e03-t03`) resolves paragraph
IDs against.

## Format ``debate-snapshot-text/1``

UTF-8 JSON, no byte-order mark, keys sorted, no insignificant whitespace, non-ASCII characters
written as themselves rather than ``\\u`` escapes::

    {"format":"debate-snapshot-text/1",
     "normalizer_version":"evidence-normalizer-v1",
     "paragraphs":[{"end":31,"id":"p0001","start":0},{"end":63,"id":"p0002","start":33}],
     "text":"Arctic methane is accelerating.\\n\\nOcean heat reached a new high."}

(shown wrapped; the stored bytes are one line).

**The encoding is canonical, so it is a function of the normalized text alone.** Equal normalized
text under the same version always encodes to the same bytes, and therefore to the same
content-addressed blob key. That is what makes a second snapshot of an unchanged source store no
second copy (`v1-e03-t02` ac3), even when the raw bytes differ — a page re-served with different
markup around the same text shares its normalized blob with the first retrieval.

For the same reason the document does **not** contain the normalizer's offset map. That map relates
normalized offsets to offsets in the extractor's output, which is not stored, so it could not be
used; and it differs whenever the extractor's whitespace differs, so it would split one normalized
text across many blobs.

:func:`decode_snapshot_text` is strict. It accepts exactly the bytes :func:`encode_snapshot_text`
writes: any other spelling of the same JSON — reordered keys, added whitespace, escaped characters,
a duplicated key — is refused as :class:`MalformedSnapshotText`. A document that could be written
two ways would have two blob keys, and a reader that accepted both would hide which one a snapshot
actually recorded.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Final, cast

from debate_core.evidence.normalization import NormalizedText, Paragraph, UnknownParagraphError

__all__ = [
    "SNAPSHOT_TEXT_FORMAT",
    "MalformedSnapshotText",
    "SnapshotText",
    "decode_snapshot_text",
    "encode_snapshot_text",
]

SNAPSHOT_TEXT_FORMAT: Final = "debate-snapshot-text/1"
"""The format identifier written into every document. A format change gets a new identifier."""

_DOCUMENT_KEYS: Final = frozenset({"format", "normalizer_version", "paragraphs", "text"})
_PARAGRAPH_KEYS: Final = frozenset({"end", "id", "start"})


class MalformedSnapshotText(ValueError):
    """Bytes that are not a canonical ``debate-snapshot-text/1`` document."""


@dataclass(frozen=True, slots=True)
class SnapshotText:
    """A snapshot's normalized text as stored: the text, its normalizer version and its paragraphs.

    It is :class:`~debate_core.evidence.normalization.NormalizedText` without the offset map, which
    is not stored (see the module docstring).
    """

    text: str
    normalizer_version: str
    paragraphs: tuple[Paragraph, ...]

    @classmethod
    def from_normalized(cls, normalized: NormalizedText) -> SnapshotText:
        """The part of a normalizer result that is stored. The version is the result's own."""
        return cls(
            text=normalized.text,
            normalizer_version=normalized.normalizer_version,
            paragraphs=normalized.paragraphs,
        )

    def paragraph(self, paragraph_id: str) -> Paragraph:
        """The paragraph with ``paragraph_id``, or :class:`UnknownParagraphError`."""
        for paragraph in self.paragraphs:
            if paragraph.paragraph_id == paragraph_id:
                return paragraph
        raise UnknownParagraphError(paragraph_id)

    def paragraph_text(self, paragraph_id: str) -> str:
        """The text of one paragraph, sliced from the stored normalized text."""
        paragraph = self.paragraph(paragraph_id)
        return self.text[paragraph.start : paragraph.end]


def encode_snapshot_text(snapshot_text: SnapshotText) -> bytes:
    """Encode ``snapshot_text`` as its one canonical ``debate-snapshot-text/1`` document.

    Raises :class:`UnicodeEncodeError` for text containing a lone surrogate. The normalizer refuses
    such text before it gets here, so in practice this cannot happen to a normalizer result.
    """
    document = {
        "format": SNAPSHOT_TEXT_FORMAT,
        "normalizer_version": snapshot_text.normalizer_version,
        "paragraphs": [
            {"end": paragraph.end, "id": paragraph.paragraph_id, "start": paragraph.start}
            for paragraph in snapshot_text.paragraphs
        ],
        "text": snapshot_text.text,
    }
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def decode_snapshot_text(data: bytes) -> SnapshotText:
    """Decode a document written by :func:`encode_snapshot_text`, or raise :class:`MalformedSnapshotText`.

    Checks the structure (keys, types, format identifier), that every paragraph lies inside the
    text, in order and without overlap, with unique IDs, and finally that ``data`` is exactly the
    canonical encoding of what it decoded to.

    It does not check that the paragraph map is the one the recorded normalizer version would
    produce for this text. The map is inside the blob, so the blob's content hash already binds it
    to what was written; re-deriving it would mean re-running the normalizer on every load.
    """
    try:
        document: object = json.loads(data.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as unreadable:
        raise MalformedSnapshotText(f"not UTF-8 JSON: {unreadable}") from unreadable
    if not isinstance(document, dict):
        raise MalformedSnapshotText("the document is not a JSON object")
    fields = cast("dict[str, object]", document)  # JSON object keys are always strings
    if frozenset(fields) != _DOCUMENT_KEYS:
        raise MalformedSnapshotText(
            f"expected exactly the keys {sorted(_DOCUMENT_KEYS)}, got {sorted(fields)}"
        )
    if fields["format"] != SNAPSHOT_TEXT_FORMAT:
        raise MalformedSnapshotText(f"unknown format {fields['format']!r}; expected {SNAPSHOT_TEXT_FORMAT!r}")
    text = fields["text"]
    normalizer_version = fields["normalizer_version"]
    raw_paragraphs = fields["paragraphs"]
    if type(text) is not str or type(normalizer_version) is not str or not normalizer_version:
        raise MalformedSnapshotText("text and normalizer_version must be strings, the version non-empty")
    if not isinstance(raw_paragraphs, list):
        raise MalformedSnapshotText("paragraphs must be a list")
    snapshot_text = SnapshotText(
        text=text,
        normalizer_version=normalizer_version,
        paragraphs=_paragraphs(cast("list[object]", raw_paragraphs), len(text)),
    )
    try:
        canonical = encode_snapshot_text(snapshot_text)
    except UnicodeEncodeError as unencodable:
        raise MalformedSnapshotText("the text contains a lone surrogate") from unencodable
    if canonical != data:
        raise MalformedSnapshotText("the bytes are not the canonical encoding of the document they hold")
    return snapshot_text


def _paragraphs(raw_paragraphs: list[object], text_length: int) -> tuple[Paragraph, ...]:
    paragraphs: list[Paragraph] = []
    seen_ids: set[str] = set()
    previous_end = 0
    for position, raw in enumerate(raw_paragraphs):
        if not isinstance(raw, dict):
            raise MalformedSnapshotText(f"paragraph {position} is not a JSON object")
        fields = cast("dict[str, object]", raw)
        if frozenset(fields) != _PARAGRAPH_KEYS:
            raise MalformedSnapshotText(
                f"paragraph {position} must have exactly the keys {sorted(_PARAGRAPH_KEYS)}"
            )
        paragraph_id, start, end = fields["id"], fields["start"], fields["end"]
        if (
            type(paragraph_id) is not str
            or not paragraph_id
            or type(start) is not int
            or type(end) is not int
        ):
            raise MalformedSnapshotText(
                f"paragraph {position} needs a non-empty string id and integer offsets"
            )
        if paragraph_id in seen_ids:
            raise MalformedSnapshotText(f"paragraph id {paragraph_id!r} appears twice")
        if not previous_end <= start <= end <= text_length:
            raise MalformedSnapshotText(
                f"paragraph {paragraph_id!r} [{start}, {end}) is out of order, overlapping or outside "
                f"the text (length {text_length})"
            )
        seen_ids.add(paragraph_id)
        previous_end = end
        paragraphs.append(Paragraph(paragraph_id, start, end))
    return tuple(paragraphs)
