"""Skeleton for the red run: real signatures, no behaviour."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from debate_core.application.federated_dedupe import MergedCandidate
from debate_core.domain.enums import SourceType

__all__ = [
    "FEATURE_NAMES",
    "FeatureVector",
    "age_in_days",
    "bm25_scores",
    "citations",
    "document_tokens",
    "open_access",
    "peer_reviewed",
    "provider_agreement",
    "query_terms",
    "ranking_tokens",
    "recency",
    "source_type_value",
]

FEATURE_NAMES: Final = (
    "bm25",
    "recency",
    "source_type",
    "peer_reviewed",
    "open_access",
    "citations",
    "provider_agreement",
)


@dataclass(frozen=True, slots=True, kw_only=True)
class FeatureVector:
    bm25: float | None
    recency: float | None
    source_type: float | None
    peer_reviewed: float | None
    open_access: float | None
    citations: float | None
    provider_agreement: float | None

    def as_dict(self) -> dict[str, float | None]:
        return {}


def ranking_tokens(text: str) -> tuple[str, ...]:
    return ()


def document_tokens(candidate: MergedCandidate) -> tuple[str, ...]:
    return ()


def query_terms(queries: Iterable[str]) -> tuple[str, ...]:
    return ()


def bm25_scores(
    documents: Sequence[Sequence[str]], terms: Sequence[str], *, k1: float, b: float
) -> tuple[float, ...]:
    return tuple(0.0 for _ in documents)


def age_in_days(published_at: datetime | None, reference: datetime) -> int | None:
    return None


def recency(
    published_at: datetime | None, *, reference: datetime, since: datetime | None, half_life_days: float
) -> float | None:
    return None


def source_type_value(source_type: SourceType, values: Mapping[SourceType, float]) -> float:
    return 0.0


def peer_reviewed(candidate: MergedCandidate) -> float | None:
    return None


def open_access(candidate: MergedCandidate) -> float | None:
    return None


def citations(candidate: MergedCandidate, *, saturation: int) -> float | None:
    return None


def provider_agreement(candidate: MergedCandidate, *, answered: int) -> float | None:
    return None
