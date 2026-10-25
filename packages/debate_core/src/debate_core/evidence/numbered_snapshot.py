"""A snapshot's normalized text as a model reads it, ``[P1]``, ``[P2]``, ..., and the way back to offsets.

A model is shown each paragraph of a snapshot's normalized text on its own, labelled with its
number::

    [P1] First paragraph's text.

    [P2] Second paragraph's text.

and answers with paragraph numbers and offsets into one paragraph's text
(:mod:`debate_core.evidence.selection_contract`). :class:`NumberedSnapshot` renders that text and
is the offset map back: paragraph ``N`` is the Nth paragraph of the snapshot's paragraph map, and an
offset into it is the paragraph's ``start`` plus the offset, in the snapshot's normalized text. So
what the model counts after a label is exactly the paragraph's text, character for character, and
the label itself never shifts an offset.

Offsets are Python ``str`` indices, which count code points, in both directions: the unit of the
normalizer's offset map and of span extraction (`v1-e03-t03`). An offset that is not inside the
paragraph it names is refused with :class:`NumberedOffsetError`, never carried into the next
paragraph or clamped: paragraph 2, offset 500 in a 40-character paragraph is not a way of saying
paragraph 3.

Nothing here reads text a model wrote. The rendering is built from the snapshot alone, and the
conversions take numbers.
"""

from __future__ import annotations

import bisect
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from debate_core.evidence._runtime_checks import is_instance
from debate_core.evidence.markup import EvidenceMarkupSpan
from debate_core.evidence.normalization import Paragraph
from debate_core.evidence.selection import EvidenceSelection, OffsetRange, ParagraphId
from debate_core.evidence.selection_contract import (
    CardSelection,
    MarkupSpan,
    MarkupSuggestion,
    SelectedPassage,
)
from debate_core.evidence.snapshot_text import SnapshotText

__all__ = [
    "PARAGRAPH_SEPARATOR",
    "NumberedOffsetError",
    "NumberedSnapshot",
    "OffsetProblem",
    "paragraph_label",
]

PARAGRAPH_SEPARATOR: Final = "\n\n"
"""What separates two numbered paragraphs in the rendering."""


def paragraph_label(number: int) -> str:
    """The label paragraph ``number`` is shown with, such as ``[P3]``."""
    return f"[P{number}]"


class OffsetProblem(StrEnum):
    """Why a paragraph number or offset does not name characters of this snapshot."""

    PARAGRAPH_OUT_OF_BOUNDS = "paragraph_out_of_bounds"
    """The snapshot has no paragraph with this number."""

    OFFSET_OUT_OF_BOUNDS = "offset_out_of_bounds"
    """An offset lies outside the paragraph it names, or between two paragraphs."""

    REVERSED_RANGE = "reversed_range"
    """A range ends before it starts."""

    EMPTY_RANGE = "empty_range"
    """A range selects no characters."""


class NumberedOffsetError(ValueError):
    """A paragraph number or offset that names no characters of the snapshot. Never clamped to fit.

    The message holds numbers only, never text.
    """

    def __init__(self, problem: OffsetProblem, detail: str) -> None:
        self.problem = problem
        """What was wrong, for the guard, which turns it into a named problem."""
        self.detail = detail
        """The numbers involved, in a sentence."""
        super().__init__(f"{problem.value}: {detail}")


@dataclass(frozen=True, slots=True)
class NumberedSnapshot:
    """A snapshot's normalized text, numbered by paragraph, and the map between its offsets."""

    source: SnapshotText = field(repr=False)
    _starts: tuple[int, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not is_instance(self.source, SnapshotText):
            raise TypeError(f"source must be a SnapshotText, got {type(self.source)!r}")
        object.__setattr__(self, "_starts", tuple(paragraph.start for paragraph in self.source.paragraphs))

    @property
    def paragraph_count(self) -> int:
        """How many paragraphs the snapshot has: the highest ``[PN]`` there is."""
        return len(self.source.paragraphs)

    def paragraph(self, number: int) -> Paragraph:
        """Paragraph ``number``, counted from 1, or :class:`NumberedOffsetError`."""
        # bool is an int subclass; True is not a paragraph number.
        if type(number) is not int or not 1 <= number <= self.paragraph_count:
            raise NumberedOffsetError(
                OffsetProblem.PARAGRAPH_OUT_OF_BOUNDS,
                f"paragraph {number!r} is not one of the snapshot's {self.paragraph_count} paragraphs",
            )
        return self.source.paragraphs[number - 1]

    def paragraph_id(self, number: int) -> ParagraphId:
        """The paragraph map's ID for paragraph ``number``, such as ``p0003``."""
        return ParagraphId(self.paragraph(number).paragraph_id)

    def paragraph_length(self, number: int) -> int:
        """How many characters paragraph ``number`` has."""
        paragraph = self.paragraph(number)
        return paragraph.end - paragraph.start

    def render(self, numbers: Iterable[int] | None = None) -> str:
        """The text a prompt shows: each paragraph after its ``[PN]`` label, a blank line between.

        ``numbers`` limits it to those paragraphs, in snapshot order, each keeping its own number,
        so offsets into a partial rendering mean what they mean in the whole one.
        """
        if numbers is None:
            chosen = range(1, self.paragraph_count + 1)
        else:
            chosen = sorted(set(numbers))
            for number in chosen:
                self.paragraph(number)
        return PARAGRAPH_SEPARATOR.join(
            f"{paragraph_label(number)} {self.source.paragraph_text(self.paragraph(number).paragraph_id)}"
            for number in chosen
        )

    # -----------------------------------------------------------------------------------------
    # The offset map
    # -----------------------------------------------------------------------------------------

    def to_snapshot_offset(self, number: int, offset: int) -> int:
        """Offset ``offset`` of paragraph ``number`` as an offset into the snapshot's normalized text.

        ``offset`` may be anything from 0 to the paragraph's length inclusive (the length being the
        position just past its last character, where an exclusive end points).
        """
        paragraph = self.paragraph(number)
        if type(offset) is not int or not 0 <= offset <= paragraph.end - paragraph.start:
            raise NumberedOffsetError(
                OffsetProblem.OFFSET_OUT_OF_BOUNDS,
                f"offset {offset!r} is outside paragraph {number}, which has "
                f"{paragraph.end - paragraph.start} characters",
            )
        return paragraph.start + offset

    def to_paragraph_offset(self, snapshot_offset: int) -> tuple[int, int]:
        """Snapshot offset ``snapshot_offset`` as ``(paragraph number, offset into that paragraph)``.

        The inverse of :meth:`to_snapshot_offset`. An offset inside the break between two
        paragraphs belongs to neither and is refused.
        """
        if type(snapshot_offset) is int:
            position = bisect.bisect_right(self._starts, snapshot_offset) - 1
            if position >= 0 and snapshot_offset <= self.source.paragraphs[position].end:
                return position + 1, snapshot_offset - self.source.paragraphs[position].start
        raise NumberedOffsetError(
            OffsetProblem.OFFSET_OUT_OF_BOUNDS,
            f"snapshot offset {snapshot_offset!r} is not inside any of the snapshot's "
            f"{self.paragraph_count} paragraphs",
        )

    def passage_range(self, passage: SelectedPassage) -> tuple[int, int]:
        """The ``[start, end)`` snapshot offsets ``passage`` selects, or :class:`NumberedOffsetError`."""
        first = self.paragraph(passage.first_paragraph)
        self.paragraph(passage.last_paragraph)
        if passage.last_paragraph < passage.first_paragraph:
            raise NumberedOffsetError(
                OffsetProblem.REVERSED_RANGE,
                f"the passage ends in paragraph {passage.last_paragraph}, before it starts in "
                f"paragraph {passage.first_paragraph}",
            )
        if passage.start_offset >= first.end - first.start:
            # A passage cannot start at its paragraph's end: what follows is a paragraph break.
            raise NumberedOffsetError(
                OffsetProblem.OFFSET_OUT_OF_BOUNDS,
                f"start offset {passage.start_offset} is not before the end of paragraph "
                f"{passage.first_paragraph}, which has {first.end - first.start} characters",
            )
        start = self.to_snapshot_offset(passage.first_paragraph, passage.start_offset)
        end_offset = (
            passage.end_offset
            if passage.end_offset is not None
            else self.paragraph_length(passage.last_paragraph)
        )
        end = self.to_snapshot_offset(passage.last_paragraph, end_offset)
        return _checked_range(start, end, f"passage from paragraph {passage.first_paragraph}")

    def span_range(self, span: MarkupSpan) -> tuple[int, int]:
        """The ``[start, end)`` snapshot offsets ``span`` marks, or :class:`NumberedOffsetError`."""
        start = self.to_snapshot_offset(span.paragraph, span.start_offset)
        end = self.to_snapshot_offset(span.paragraph, span.end_offset)
        return _checked_range(start, end, f"span in paragraph {span.paragraph}")

    def evidence_selection(self, selection: CardSelection) -> EvidenceSelection:
        """``selection`` as the offset ranges span extraction takes (`v1-e03-t03`)."""
        return EvidenceSelection(
            tuple(OffsetRange(*self.passage_range(passage)) for passage in selection.passages)
        )

    def markup_spans(self, markup: MarkupSuggestion) -> tuple[EvidenceMarkupSpan, ...]:
        """``markup`` as snapshot-offset spans, for :class:`~debate_core.evidence.markup.CardMarkup`."""
        return tuple(
            EvidenceMarkupSpan(*self.span_range(span), style=span.style, purpose=span.purpose)
            for span in markup.spans
        )


def _checked_range(start: int, end: int, what: str) -> tuple[int, int]:
    if end < start:
        raise NumberedOffsetError(OffsetProblem.REVERSED_RANGE, f"the {what} ends before it starts")
    if end == start:
        raise NumberedOffsetError(OffsetProblem.EMPTY_RANGE, f"the {what} selects no characters")
    return start, end
