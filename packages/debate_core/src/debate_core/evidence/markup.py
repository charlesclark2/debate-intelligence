"""Underlining and highlighting over extracted evidence, recorded in snapshot offsets.

A :class:`CardMarkup` is a set of :class:`EvidenceMarkupSpan` records checked against one
:class:`~debate_core.evidence.extractor.ExtractedEvidence`. Once built, it is known that:

* every span marks at least one character, and lies wholly inside a single evidence segment. A span
  that reaches past the evidence, or across a cut into the omitted text, would underline words the
  card does not contain. It is refused, never trimmed to fit;
* no two spans of the same style share a character (an underline and a highlight may, and must);
* every highlighted character is also underlined, the debate convention that what is read aloud is
  a subset of what is underlined.

Offsets are into the snapshot's normalized text, like the evidence's own, so a span means the same
characters however the card's evidence is later cut further (`v1-e03-t05`).

This is not :class:`debate_core.domain.CardSpan`. The domain record's offsets are relative to a card's
``evidence_text``, and a :class:`~debate_core.domain.Card` has no place yet for the cuts in
non-contiguous evidence. Mapping a ``CardMarkup`` onto a card is the card service's step
(`v1-e06-t02`); see the `v1-e03-t03` session report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from debate_core.domain import SpanPurpose, SpanStyle
from debate_core.evidence._runtime_checks import is_instance, is_tuple_of
from debate_core.evidence.extractor import ExtractedEvidence

__all__ = [
    "CardMarkup",
    "EvidenceMarkupSpan",
    "InvalidMarkup",
    "MarkupProblem",
]


class MarkupProblem(StrEnum):
    """Why markup was refused."""

    NOT_AN_OFFSET = "not_an_offset"
    """An offset is not a non-negative ``int``."""

    EMPTY_SPAN = "empty_span"
    """A span marks no characters (``start == end``)."""

    REVERSED_SPAN = "reversed_span"
    """A span ends before it starts."""

    NOT_A_STYLE = "not_a_style"
    """The style is not a :class:`~debate_core.domain.SpanStyle`."""

    NOT_A_PURPOSE = "not_a_purpose"
    """The purpose is neither ``None`` nor a :class:`~debate_core.domain.SpanPurpose`."""

    NOT_A_SPAN = "not_a_span"
    """The spans are not a tuple of :class:`EvidenceMarkupSpan`."""

    OUTSIDE_EVIDENCE = "outside_evidence"
    """A span reaches before the evidence starts or past where it ends."""

    CROSSES_OMITTED_TEXT = "crosses_omitted_text"
    """A span lies inside the evidence's extent but takes in text a cut left out."""

    OVERLAPS_SAME_STYLE = "overlaps_same_style"
    """Two spans of the same style share a character."""

    HIGHLIGHT_NOT_UNDERLINED = "highlight_not_underlined"
    """A highlighted character is not underlined."""


class InvalidMarkup(ValueError):
    """Markup that does not fit the evidence it is for. It is never trimmed or merged to fit."""

    def __init__(self, problem: MarkupProblem, detail: str) -> None:
        self.problem = problem
        """What was wrong, for a caller that maps refusals to reason codes."""
        super().__init__(f"{problem.value}: {detail}")


@dataclass(frozen=True, slots=True)
class EvidenceMarkupSpan:
    """Characters ``[start, end)`` of the snapshot's normalized text, underlined or highlighted.

    ``purpose`` says what argumentative work the marked words do, when that is known.
    """

    start: int
    end: int
    style: SpanStyle
    purpose: SpanPurpose | None = None

    def __post_init__(self) -> None:
        for name, value in (("start", self.start), ("end", self.end)):
            # bool is an int subclass; True is not an offset.
            if type(value) is not int or value < 0:
                raise InvalidMarkup(
                    MarkupProblem.NOT_AN_OFFSET, f"{name} must be a non-negative int, got {value!r}"
                )
        if self.end < self.start:
            raise InvalidMarkup(
                MarkupProblem.REVERSED_SPAN, f"span [{self.start}, {self.end}) ends before it starts"
            )
        if self.end == self.start:
            raise InvalidMarkup(MarkupProblem.EMPTY_SPAN, f"span [{self.start}, {self.end}) marks nothing")
        if not is_instance(self.style, SpanStyle):
            raise InvalidMarkup(MarkupProblem.NOT_A_STYLE, f"{self.style!r} is not a SpanStyle")
        if self.purpose is not None and not is_instance(self.purpose, SpanPurpose):
            raise InvalidMarkup(MarkupProblem.NOT_A_PURPOSE, f"{self.purpose!r} is not a SpanPurpose")

    @classmethod
    def underline(cls, start: int, end: int, purpose: SpanPurpose | None = None) -> EvidenceMarkupSpan:
        """An underline over ``[start, end)``."""
        return cls(start, end, SpanStyle.UNDERLINE, purpose)

    @classmethod
    def highlight(cls, start: int, end: int, purpose: SpanPurpose | None = None) -> EvidenceMarkupSpan:
        """A highlight over ``[start, end)``."""
        return cls(start, end, SpanStyle.HIGHLIGHT, purpose)


@dataclass(frozen=True, slots=True)
class CardMarkup:
    """The underlines and highlights of one piece of evidence, checked against it.

    Valid by construction: see the module docstring for what holding one guarantees.
    """

    evidence: ExtractedEvidence = field(repr=False)
    spans: tuple[EvidenceMarkupSpan, ...]

    def __post_init__(self) -> None:
        if not is_instance(self.evidence, ExtractedEvidence):
            raise TypeError(f"evidence must be ExtractedEvidence, got {type(self.evidence)!r}")
        if not is_tuple_of(self.spans, EvidenceMarkupSpan):
            raise InvalidMarkup(MarkupProblem.NOT_A_SPAN, "spans must be a tuple of EvidenceMarkupSpan")
        for span in self.spans:
            _check_inside(span, self.evidence)
        for style in SpanStyle:
            _check_no_overlap(self.of_style(style))
        underlines = self.of_style(SpanStyle.UNDERLINE)
        for highlight in self.of_style(SpanStyle.HIGHLIGHT):
            _check_underlined(highlight, underlines)

    def of_style(self, style: SpanStyle) -> tuple[EvidenceMarkupSpan, ...]:
        """The spans of one style, in source order."""
        return tuple(
            sorted((span for span in self.spans if span.style is style), key=lambda span: span.start)
        )


def _check_inside(span: EvidenceMarkupSpan, evidence: ExtractedEvidence) -> None:
    if evidence.segment_containing(span.start, span.end) is not None:
        return
    if span.start < evidence.start or span.end > evidence.end:
        raise InvalidMarkup(
            MarkupProblem.OUTSIDE_EVIDENCE,
            f"span [{span.start}, {span.end}) is not inside the evidence [{evidence.start}, {evidence.end})",
        )
    raise InvalidMarkup(
        MarkupProblem.CROSSES_OMITTED_TEXT,
        f"span [{span.start}, {span.end}) takes in text the evidence omits; mark each segment separately",
    )


def _check_no_overlap(spans_in_order: tuple[EvidenceMarkupSpan, ...]) -> None:
    # Sorted by start, any overlap shows up between neighbours.
    for previous, span in zip(spans_in_order, spans_in_order[1:], strict=False):
        if span.start < previous.end:
            raise InvalidMarkup(
                MarkupProblem.OVERLAPS_SAME_STYLE,
                f"{span.style.value} spans [{previous.start}, {previous.end}) and [{span.start}, {span.end}) "
                "overlap; merge them instead",
            )


def _check_underlined(highlight: EvidenceMarkupSpan, underlines: tuple[EvidenceMarkupSpan, ...]) -> None:
    # Underlines are in order and do not overlap, so walk them, extending the covered prefix.
    covered_to = highlight.start
    for underline in underlines:
        if underline.end <= covered_to:
            continue
        if underline.start > covered_to:
            break
        covered_to = underline.end
        if covered_to >= highlight.end:
            return
    raise InvalidMarkup(
        MarkupProblem.HIGHLIGHT_NOT_UNDERLINED,
        f"highlight [{highlight.start}, {highlight.end}) is not underlined from {covered_to}",
    )
