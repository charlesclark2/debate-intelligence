"""What a card's evidence is selected by, and the pieces extraction cuts it into.

A selection names *where* the evidence is, never *what it says*. It is a list of parts, each either a
run of whole paragraphs (by paragraph ID) or a ``[start, end)`` range of character offsets into the
snapshot's normalized text. Nothing in this module takes evidence text: paragraph IDs are typed as
:data:`ParagraphId`, offsets are integers, and the text of an :class:`EvidenceSegment` is read from
the :class:`~debate_core.evidence.snapshot_text.SnapshotText` it was cut from, at its own offsets,
every time it is asked for. There is no constructor that accepts the text instead.

What the extractor (:mod:`debate_core.evidence.extractor`) makes of a selection:

* every selected character is in exactly one :class:`EvidenceSegment`, and no character that was not
  selected is in any of them. Parts that touch are one segment; nothing is clamped, widened or
  trimmed to make a selection fit;
* the text between two segments is an :class:`OmittedRange`: its offsets, and no text. A renderer
  shows it as an ellipsis marker. It is never filled in.

Everything that is wrong with a selection raises :class:`InvalidSelection` with a
:class:`SelectionProblem`, so callers (the card service in `v1-e06-t02`) can turn it into a reason
code on an UNVERIFIED card rather than parse a message.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import NewType

from debate_core.evidence._runtime_checks import is_instance
from debate_core.evidence.snapshot_text import SnapshotText

__all__ = [
    "EvidenceSegment",
    "EvidenceSelection",
    "InvalidSelection",
    "OffsetRange",
    "OmittedRange",
    "ParagraphId",
    "ParagraphRun",
    "SelectionPart",
    "SelectionProblem",
]

ParagraphId = NewType("ParagraphId", str)
"""The ID of one paragraph in a snapshot's paragraph map, such as ``p0003``.

A distinct type rather than ``str`` so the signature test in ``tests/evidence/test_extractor.py``
can tell an ID from a string that might be evidence. It resolves only through the paragraph map, so
whatever string is passed, the text that comes out is the snapshot's.
"""


class SelectionProblem(StrEnum):
    """Why a selection was refused."""

    NO_PARTS = "no_parts"
    """The selection selects nothing."""

    NOT_A_PART = "not_a_part"
    """A part is neither an :class:`OffsetRange` nor a :class:`ParagraphRun`."""

    NOT_AN_OFFSET = "not_an_offset"
    """An offset is not a non-negative ``int`` (``bool`` and ``float`` are refused too)."""

    EMPTY_RANGE = "empty_range"
    """A range selects no characters (``start == end``), or a paragraph it names is empty."""

    REVERSED_RANGE = "reversed_range"
    """A range ends before it starts, or a paragraph run's last paragraph comes before its first."""

    NOT_A_PARAGRAPH_ID = "not_a_paragraph_id"
    """A paragraph ID is not a non-empty string."""

    UNKNOWN_PARAGRAPH = "unknown_paragraph"
    """A paragraph ID is not in the snapshot's paragraph map."""

    OUT_OF_BOUNDS = "out_of_bounds"
    """A range ends past the end of the snapshot's normalized text."""

    OVERLAPPING = "overlapping"
    """Two parts select a character in common, or two segments do."""

    SEGMENTS_TOUCH = "segments_touch"
    """Two segments built directly meet with nothing omitted between them; they are one segment."""


class InvalidSelection(ValueError):
    """A selection that does not describe evidence in this snapshot. It is never repaired."""

    def __init__(self, problem: SelectionProblem, detail: str) -> None:
        self.problem = problem
        """What was wrong, for a caller that maps refusals to reason codes."""
        super().__init__(f"{problem.value}: {detail}")


def _check_offset(value: object, name: str) -> int:
    # bool is an int subclass; True is not an offset.
    if type(value) is not int or value < 0:
        raise InvalidSelection(
            SelectionProblem.NOT_AN_OFFSET, f"{name} must be a non-negative int, got {value!r}"
        )
    return value


def _check_range(start: object, end: object) -> None:
    start = _check_offset(start, "start")
    end = _check_offset(end, "end")
    if end < start:
        raise InvalidSelection(
            SelectionProblem.REVERSED_RANGE, f"range [{start}, {end}) ends before it starts"
        )
    if end == start:
        raise InvalidSelection(SelectionProblem.EMPTY_RANGE, f"range [{start}, {end}) selects nothing")


def _check_paragraph_id(value: object) -> None:
    if not isinstance(value, str) or not value:
        raise InvalidSelection(
            SelectionProblem.NOT_A_PARAGRAPH_ID, f"a paragraph ID must be a non-empty string, got {value!r}"
        )


# ---------------------------------------------------------------------------------------------
# What a caller selects
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OffsetRange:
    """Characters ``[start, end)`` of the snapshot's normalized text. Never empty, never reversed."""

    start: int
    end: int

    def __post_init__(self) -> None:
        _check_range(self.start, self.end)


@dataclass(frozen=True, slots=True)
class ParagraphRun:
    """Whole paragraphs ``first`` through ``last`` inclusive, and the breaks between them.

    One paragraph is a run whose ``first`` and ``last`` are the same. A run is one contiguous range
    of the normalized text, so it extracts as one segment. Listing consecutive paragraphs as
    separate runs is a different selection: it leaves out the paragraph break between them, which
    becomes an :class:`OmittedRange`.
    """

    first: ParagraphId
    last: ParagraphId

    def __post_init__(self) -> None:
        _check_paragraph_id(self.first)
        _check_paragraph_id(self.last)


SelectionPart = OffsetRange | ParagraphRun


@dataclass(frozen=True, slots=True)
class EvidenceSelection:
    """The parts of a snapshot a card's evidence is cut from, in any order.

    The extractor puts them in source order. It never reorders the text inside a part, and it never
    reorders one part's text ahead of another's that precedes it in the source, so a selection cannot
    splice a source's sentences into an order it did not write them in.
    """

    parts: tuple[SelectionPart, ...]

    def __post_init__(self) -> None:
        if not is_instance(self.parts, tuple):
            raise InvalidSelection(
                SelectionProblem.NOT_A_PART, f"parts must be a tuple, got {type(self.parts)!r}"
            )
        if not self.parts:
            raise InvalidSelection(SelectionProblem.NO_PARTS, "a selection needs at least one part")
        for part in self.parts:
            if not is_instance(part, OffsetRange | ParagraphRun):
                raise InvalidSelection(
                    SelectionProblem.NOT_A_PART, f"{part!r} is not an OffsetRange or ParagraphRun"
                )

    @classmethod
    def of_offsets(cls, *ranges: tuple[int, int]) -> EvidenceSelection:
        """A selection of ``(start, end)`` offset ranges."""
        return cls(tuple(OffsetRange(start, end) for start, end in ranges))

    @classmethod
    def of_paragraphs(cls, *paragraph_ids: ParagraphId) -> EvidenceSelection:
        """A selection of single whole paragraphs, each its own part."""
        return cls(tuple(ParagraphRun(paragraph_id, paragraph_id) for paragraph_id in paragraph_ids))


# ---------------------------------------------------------------------------------------------
# What extraction produces
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EvidenceSegment:
    """One contiguous piece of a card's evidence: ``source.text[start:end]``.

    The segment holds the text it was cut from and its offsets, and :attr:`text` slices it on every
    read. That is what makes "segment text equals the snapshot text at the recorded offsets" true by
    construction rather than by checking: there is nowhere else for the text to come from.
    """

    source: SnapshotText = field(repr=False)
    start: int
    end: int

    def __post_init__(self) -> None:
        if not is_instance(self.source, SnapshotText):
            raise TypeError(f"source must be a SnapshotText, got {type(self.source)!r}")
        _check_range(self.start, self.end)
        if self.end > len(self.source.text):
            raise InvalidSelection(
                SelectionProblem.OUT_OF_BOUNDS,
                f"range [{self.start}, {self.end}) runs past the end of the normalized text "
                f"({len(self.source.text)} characters)",
            )

    @property
    def text(self) -> str:
        """The evidence, sliced from the snapshot's normalized text at this segment's offsets."""
        return self.source.text[self.start : self.end]


@dataclass(frozen=True, slots=True)
class OmittedRange:
    """Characters ``[start, end)`` of the snapshot left out between two segments.

    It deliberately has no text. A renderer marks the cut with an ellipsis; anyone auditing the card
    reads exactly what was removed from the snapshot at these offsets.
    """

    start: int
    end: int

    def __post_init__(self) -> None:
        _check_range(self.start, self.end)
