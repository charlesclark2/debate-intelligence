"""Span-addressed evidence extraction: the only code path that puts quoted text on a card.

:meth:`EvidenceExtractor.extract` takes a snapshot record, the snapshot's normalized text and an
:class:`~debate_core.evidence.selection.EvidenceSelection` (paragraph IDs and offsets, never text),
and returns :class:`ExtractedEvidence`: segments sliced from that text, with the cuts between them
recorded as :class:`~debate_core.evidence.selection.OmittedRange` offsets. No parameter anywhere in
this module, :mod:`~debate_core.evidence.selection` or :mod:`~debate_core.evidence.markup` accepts
evidence text, and ``tests/evidence/test_extractor.py`` fails if one is added (`v1-e03-t03` ac4).

## The text must come from a verified load. This module cannot check that; the caller must.

The ``SnapshotText`` passed in is trusted to be the snapshot's real normalized text. The only way to
get one that deserves that trust is
:meth:`~debate_core.application.snapshot_service.SnapshotService.load`, which re-hashes both blobs
against the record before it returns. The evidence layer sits below the application layer, so this
module cannot ask for a ``LoadedSnapshot`` and cannot tell a loaded ``SnapshotText`` from one built
by hand: ``SnapshotText(text=...)`` is an ordinary constructor. **Keeping that guarantee is the
caller's job.** Code that builds a ``SnapshotText`` from anything but a ``load`` and passes it here
has severed the chain from card text back to the bytes a source served, and nothing downstream can
tell.

What this module does check, on every extraction, narrows that hole without closing it:

* **The text belongs to the record.** The text's SHA-256 must equal the record's
  ``normalized_text_hash`` and its normalizer version the record's, or :class:`SnapshotTextMismatch`
  is raised. This catches the text of one snapshot paired with the record of another, so evidence
  cannot be stamped with a snapshot it was not cut from. It does not catch a record and a text
  invented together.
* **The paragraph map is the one the text has.** Before a paragraph ID is resolved, the map is
  compared with the paragraphs the text's normalizer version divides that text into
  (:func:`~debate_core.evidence.normalization.paragraph_map`). `v1-e03-t02` found that a paragraph
  boundary moved to another valid offset is invisible to every check but the normalized blob's own
  hash; this comparison catches it again at the point of use, so a moved boundary cannot silently
  point a card at different words of the same source, whatever route the ``SnapshotText`` took.

## Why both the record and the text

The spec's ``extract(snapshot, selection)`` names a ``SourceSnapshot``, but a record holds hashes,
versions and blob keys, not text; the text is in the normalized blob. Taking only the text would
lose the snapshot ID, hash and version a card needs in order to be re-verified, and leave the caller
to pair them up again later, which is where text from one snapshot gets the ID of another. Taking
both lets the result carry its own provenance and lets the pairing be checked here, once.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from debate_core.domain import SourceSnapshot
from debate_core.evidence._runtime_checks import is_instance, is_tuple_of
from debate_core.evidence.hashing import sha256_text
from debate_core.evidence.normalization import paragraph_map
from debate_core.evidence.selection import (
    EvidenceSegment,
    EvidenceSelection,
    InvalidSelection,
    OffsetRange,
    OmittedRange,
    ParagraphRun,
    SelectionProblem,
)
from debate_core.evidence.snapshot_text import SnapshotText

__all__ = [
    "EvidenceExtractor",
    "ExtractedEvidence",
    "SnapshotTextCheck",
    "SnapshotTextMismatch",
]


class SnapshotTextCheck(StrEnum):
    """Which consistency check between a ``SnapshotText`` and its record failed."""

    TEXT_HASH = "text_hash"
    """The text does not hash to the record's ``normalized_text_hash``."""

    NORMALIZER_VERSION = "normalizer_version"
    """The text's normalizer version is not the record's."""

    PARAGRAPH_MAP = "paragraph_map"
    """The paragraph map is not the one the text's normalizer version gives the text."""


class SnapshotTextMismatch(ValueError):
    """The normalized text handed to extraction is not the snapshot's, or not intact."""

    def __init__(self, check: SnapshotTextCheck, snapshot_id: str, detail: str) -> None:
        self.check = check
        """Which check failed."""
        self.snapshot_id = snapshot_id
        """The snapshot the text was presented as belonging to."""
        super().__init__(f"snapshot {snapshot_id}: {check.value}: {detail}")


def _check_text_belongs_to(snapshot: SourceSnapshot, source: SnapshotText) -> None:
    if source.normalizer_version != snapshot.normalizer_version:
        raise SnapshotTextMismatch(
            SnapshotTextCheck.NORMALIZER_VERSION,
            snapshot.snapshot_id,
            f"text is {source.normalizer_version!r}, record is {snapshot.normalizer_version!r}",
        )
    actual = sha256_text(source.text)
    if actual != snapshot.normalized_text_hash:
        raise SnapshotTextMismatch(
            SnapshotTextCheck.TEXT_HASH,
            snapshot.snapshot_id,
            f"text hashes to {actual}, record says {snapshot.normalized_text_hash}",
        )


@dataclass(frozen=True, slots=True)
class ExtractedEvidence:
    """A card's evidence: ordered segments of one snapshot's text, and the cuts between them.

    Valid by construction, however it was built: the segments are non-empty, in source order,
    separated by at least one omitted character, all cut from the same ``SnapshotText``, and that
    text belongs to ``snapshot`` (see the module docstring for what that does and does not prove).
    """

    snapshot: SourceSnapshot = field(repr=False)
    segments: tuple[EvidenceSegment, ...]

    def __post_init__(self) -> None:
        if not is_instance(self.snapshot, SourceSnapshot):
            raise TypeError(f"snapshot must be a SourceSnapshot, got {type(self.snapshot)!r}")
        if not is_tuple_of(self.segments, EvidenceSegment):
            raise TypeError("segments must be a tuple of EvidenceSegment")
        if not self.segments:
            raise InvalidSelection(SelectionProblem.NO_PARTS, "evidence needs at least one segment")
        source = self.segments[0].source
        for previous, segment in zip(self.segments, self.segments[1:], strict=False):
            if segment.source is not source:
                raise ValueError(
                    "every segment of one piece of evidence must be cut from the same SnapshotText"
                )
            if segment.start < previous.end:
                raise InvalidSelection(
                    SelectionProblem.OVERLAPPING,
                    f"segment [{segment.start}, {segment.end}) starts before "
                    f"[{previous.start}, {previous.end}) ends",
                )
            if segment.start == previous.end:
                raise InvalidSelection(
                    SelectionProblem.SEGMENTS_TOUCH,
                    f"segments [{previous.start}, {previous.end}) and [{segment.start}, {segment.end}) "
                    "touch; with nothing omitted between them they are one segment",
                )
        _check_text_belongs_to(self.snapshot, source)

    @property
    def snapshot_id(self) -> str:
        """The snapshot the evidence was cut from."""
        return self.snapshot.snapshot_id

    @property
    def normalized_text_hash(self) -> str:
        """SHA-256 of the normalized text the offsets refer to."""
        return self.snapshot.normalized_text_hash

    @property
    def normalizer_version(self) -> str:
        """The normalizer version the offsets were taken under."""
        return self.snapshot.normalizer_version

    @property
    def start(self) -> int:
        """Offset in the normalized text where the evidence begins."""
        return self.segments[0].start

    @property
    def end(self) -> int:
        """Offset in the normalized text just past the end of the evidence."""
        return self.segments[-1].end

    @property
    def omitted_ranges(self) -> tuple[OmittedRange, ...]:
        """The cuts, in order: ``omitted_ranges[i]`` lies between ``segments[i]`` and ``segments[i + 1]``."""
        return tuple(
            OmittedRange(previous.end, segment.start)
            for previous, segment in zip(self.segments, self.segments[1:], strict=False)
        )

    def pieces(self) -> tuple[EvidenceSegment | OmittedRange, ...]:
        """Segments and cuts interleaved in source order, starting and ending with a segment.

        This is the order a renderer emits: each segment's text, and an ellipsis marker for each cut.
        """
        pieces: list[EvidenceSegment | OmittedRange] = [self.segments[0]]
        for omitted, segment in zip(self.omitted_ranges, self.segments[1:], strict=True):
            pieces.extend((omitted, segment))
        return tuple(pieces)

    def segment_containing(self, start: int, end: int) -> EvidenceSegment | None:
        """The segment that holds all of ``[start, end)``, or ``None`` if no single one does."""
        for segment in self.segments:
            if segment.start <= start and end <= segment.end:
                return segment
        return None


class EvidenceExtractor:
    """Cuts evidence out of a snapshot's normalized text by paragraph IDs and offsets.

    Stateless. Every refusal is an exception: :class:`~debate_core.evidence.selection.InvalidSelection`
    for a selection that does not fit the snapshot, :class:`SnapshotTextMismatch` for text that is not
    the snapshot's, and
    :class:`~debate_core.evidence.normalization.UnknownNormalizerVersionError` when a paragraph is
    selected from text under a normalizer version that does not exist. Nothing is clamped or trimmed.
    """

    def extract(
        self,
        snapshot: SourceSnapshot,
        snapshot_text: SnapshotText,
        selection: EvidenceSelection,
    ) -> ExtractedEvidence:
        """Slice ``selection`` out of ``snapshot_text``, which must come from loading ``snapshot``.

        Parts are resolved to offset ranges and put in source order. Ranges that overlap are refused
        (by :class:`ExtractedEvidence`); ranges that touch become one segment, since nothing lies
        between them to omit. A range past the end of the text is refused, never shortened.
        """
        if not is_instance(snapshot_text, SnapshotText):
            raise TypeError(f"snapshot_text must be a SnapshotText, got {type(snapshot_text)!r}")
        if not is_instance(selection, EvidenceSelection):
            raise TypeError(f"selection must be an EvidenceSelection, got {type(selection)!r}")
        if any(isinstance(part, ParagraphRun) for part in selection.parts):
            _check_paragraph_map(snapshot, snapshot_text)
        positions = {
            paragraph.paragraph_id: index for index, paragraph in enumerate(snapshot_text.paragraphs)
        }
        ranges = sorted(_resolve(part, snapshot_text, positions) for part in selection.parts)

        # Touching ranges join; nothing lies between them to omit. Overlapping ones are left apart
        # for ExtractedEvidence to refuse, the one place that refusal is made. A reversed range
        # never gets here: joined to a neighbour it would silently shorten the selection.
        merged: list[tuple[int, int]] = []
        for start, end in ranges:
            if merged and start == merged[-1][1]:
                merged[-1] = (merged[-1][0], end)
            else:
                merged.append((start, end))
        return ExtractedEvidence(
            snapshot=snapshot,
            segments=tuple(EvidenceSegment(snapshot_text, start, end) for start, end in merged),
        )


def _check_paragraph_map(snapshot: SourceSnapshot, snapshot_text: SnapshotText) -> None:
    expected = paragraph_map(snapshot_text.text, snapshot_text.normalizer_version)
    if snapshot_text.paragraphs != expected:
        raise SnapshotTextMismatch(
            SnapshotTextCheck.PARAGRAPH_MAP,
            snapshot.snapshot_id,
            f"the paragraph map is not the one {snapshot_text.normalizer_version} gives this text",
        )


def _resolve(
    part: OffsetRange | ParagraphRun, source: SnapshotText, positions: dict[str, int]
) -> tuple[int, int]:
    if isinstance(part, OffsetRange):
        return part.start, part.end
    first = _position(part.first, positions)
    last = _position(part.last, positions)
    if last < first:
        raise InvalidSelection(
            SelectionProblem.REVERSED_RANGE,
            f"paragraph run {part.first!r}..{part.last!r} ends before it starts",
        )
    start, end = source.paragraphs[first].start, source.paragraphs[last].end
    if start == end:
        # An empty range could otherwise vanish into a touching neighbour when ranges are merged.
        raise InvalidSelection(
            SelectionProblem.EMPTY_RANGE, f"paragraph run {part.first!r}..{part.last!r} is empty"
        )
    return start, end


def _position(paragraph_id: str, positions: dict[str, int]) -> int:
    position = positions.get(paragraph_id)
    if position is None:
        raise InvalidSelection(
            SelectionProblem.UNKNOWN_PARAGRAPH, f"no paragraph {paragraph_id!r} in this snapshot"
        )
    return position
