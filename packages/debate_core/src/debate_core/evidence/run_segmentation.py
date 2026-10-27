"""Where a rendered card's evidence changes formatting, and where its cuts go (`v1-e06-t04`).

The DOCX renderer writes a card's evidence as a sequence of runs, and every run boundary is decided
here, from offsets alone. Nothing in this module reads or writes text: a run is a pair of offsets
into `Card.evidence_text` and a set of styles, so the only evidence the renderer can emit is a slice
of `evidence_text` (architecture proposal §8, step 7: render from CardSpan).

## Runs from spans

:func:`segment_runs` splits `[0, len(evidence_text))` into runs. A character's styles are the
:class:`~debate_core.domain.SpanStyle` of every span that covers it; underline and highlight spans
may overlap each other, so a run can carry both. A run with no style is text that is not read, which
the format profile condenses. Runs are as long as they can be: a boundary is a place where the
styles change, or a *break* the caller names. Two touching spans of one style are therefore one run.

## Cuts and interpolations

A card records what it omitted as snapshot ranges (ADR-0018) and its interpolations as anchors into
`evidence_text` (`v1-e03-t05`). Neither is text in `evidence_text`, and both are drawn by the
renderer at a place in it:

* an omission sits where the kept text before it ends: after the last character quoted before the
  cut (:func:`omission_offsets`);
* an interpolation sits before the character at its anchor, or after the last one when the anchor
  is the text's length.

:func:`lay_out_evidence` gives the renderer the whole paragraph in reading order: runs, with an
:class:`OmissionMark` and an :class:`InterpolationMark` between them where they belong, each of
those places a run boundary. Where an omission and an interpolation share a place, the cut comes
first, because an interpolation is read with the text that follows it.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from debate_core.domain import Card, CardSpan, Interpolation, SpanStyle

__all__ = [
    "EvidencePiece",
    "EvidenceRun",
    "InterpolationMark",
    "OmissionMark",
    "lay_out_evidence",
    "omission_offsets",
    "segment_runs",
]


@dataclass(frozen=True, slots=True)
class EvidenceRun:
    """`evidence_text[start:end]`, carrying the styles of every span that covers it."""

    start: int
    end: int
    styles: frozenset[SpanStyle]

    @property
    def condensed(self) -> bool:
        """True for text no span marks: the text that is not read, which a profile may condense."""
        return not self.styles


@dataclass(frozen=True, slots=True)
class OmissionMark:
    """A cut: the renderer's omission marker, between `evidence_text[offset - 1]` and `[offset]`."""

    offset: int


@dataclass(frozen=True, slots=True)
class InterpolationMark:
    """An interpolation, drawn before `evidence_text[offset]` (after the last character at the end)."""

    offset: int
    interpolation: Interpolation


type EvidencePiece = EvidenceRun | OmissionMark | InterpolationMark


def segment_runs(
    evidence_length: int, spans: Iterable[CardSpan], *, breaks: Iterable[int] = ()
) -> tuple[EvidenceRun, ...]:
    """`[0, evidence_length)` as runs: split where the covering spans' styles change, and at each break.

    Raises :class:`ValueError` for a span that runs past the end of the evidence, or a break outside
    `[0, evidence_length]`.
    """
    spans = tuple(spans)
    breaks = frozenset(breaks)
    for marked in spans:
        if marked.end_offset > evidence_length:
            raise ValueError(
                f"span {marked.start_offset}-{marked.end_offset} runs past the end of the evidence "
                f"({evidence_length} characters)"
            )
    for place in breaks:
        if not 0 <= place <= evidence_length:
            raise ValueError(f"break {place} is outside the evidence (0-{evidence_length})")
    edges = sorted(
        {0, evidence_length}
        | {marked.start_offset for marked in spans}
        | {marked.end_offset for marked in spans}
        | breaks
    )
    runs: list[EvidenceRun] = []
    for start, end in zip(edges, edges[1:], strict=False):
        styles = frozenset(
            marked.style for marked in spans if marked.start_offset <= start < marked.end_offset
        )
        if runs and runs[-1].styles == styles and start not in breaks:
            runs[-1] = EvidenceRun(runs[-1].start, end, styles)
        else:
            runs.append(EvidenceRun(start, end, styles))
    return tuple(runs)


def omission_offsets(card: Card) -> tuple[int, ...]:
    """Where each of `card.omitted_ranges` sits in `evidence_text`, in order.

    Each is the length of the quoted text before the cut, which is strictly inside the evidence:
    an omission never touches the envelope's ends, and a kept character separates two of them.
    """
    offsets: list[int] = []
    for start, end in card.quoted_ranges[:-1]:
        offsets.append((offsets[-1] if offsets else 0) + (end - start))
    return tuple(offsets)


def lay_out_evidence(card: Card) -> tuple[EvidencePiece, ...]:
    """`card`'s evidence paragraph in reading order: its runs, its cuts and its interpolations."""
    cuts = omission_offsets(card)
    anchors = {interpolation.anchor: interpolation for interpolation in card.interpolations}
    runs = segment_runs(len(card.evidence_text), card.spans, breaks=(*cuts, *anchors))
    pieces: list[EvidencePiece] = []

    def marks_at(offset: int) -> None:
        if offset in cuts:
            pieces.append(OmissionMark(offset))
        if offset in anchors:
            pieces.append(InterpolationMark(offset, anchors[offset]))

    for evidence_run in runs:
        marks_at(evidence_run.start)
        pieces.append(evidence_run)
    if runs:
        marks_at(runs[-1].end)
    return tuple(pieces)
