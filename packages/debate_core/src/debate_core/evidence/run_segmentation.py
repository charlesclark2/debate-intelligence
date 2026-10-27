"""Skeleton for the red run of `v1-e06-t04`: every name the tests import, and no rules."""

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
    start: int
    end: int
    styles: frozenset[SpanStyle]

    @property
    def condensed(self) -> bool:
        return not self.styles


@dataclass(frozen=True, slots=True)
class OmissionMark:
    offset: int


@dataclass(frozen=True, slots=True)
class InterpolationMark:
    offset: int
    interpolation: Interpolation


type EvidencePiece = EvidenceRun | OmissionMark | InterpolationMark


def segment_runs(
    evidence_length: int, spans: Iterable[CardSpan], *, breaks: Iterable[int] = ()
) -> tuple[EvidenceRun, ...]:
    del spans, breaks
    return (EvidenceRun(0, evidence_length, frozenset()),) if evidence_length else ()


def omission_offsets(card: Card) -> tuple[int, ...]:
    del card
    return ()


def lay_out_evidence(card: Card) -> tuple[EvidencePiece, ...]:
    return segment_runs(len(card.evidence_text), card.spans)
