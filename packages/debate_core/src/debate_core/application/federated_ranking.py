"""Skeleton for the red run: real signatures, no behaviour."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Final

import yaml
from pydantic import Field

from debate_core.application.federated_dedupe import MergedCandidate
from debate_core.application.federated_search_types import SearchState
from debate_core.application.ports import Clock
from debate_core.application.settings import ConfigurationError
from debate_core.domain import DomainModel, SearchFilters, SearchResult, Ulid
from debate_core.domain.enums import SourceType

__all__ = [
    "FEDERATED_RANKING_CONFIG_PATH",
    "Bm25Parameters",
    "CitationParameters",
    "ExplanationParameters",
    "FeatureWeights",
    "FederatedRankStage",
    "FederatedRankingConfig",
    "InvalidFederatedRankingConfig",
    "RankedCandidate",
    "RecencyParameters",
    "load_federated_ranking_config",
    "parse_federated_ranking_config",
    "rank_merged_candidates",
    "search_result_for",
]

FEDERATED_RANKING_CONFIG_PATH: Final = Path("config/federated_ranking.yaml")


class InvalidFederatedRankingConfig(ConfigurationError):
    pass


class FeatureWeights(DomainModel):
    bm25: float
    recency: float
    source_type: float
    peer_reviewed: float
    open_access: float
    citations: float
    provider_agreement: float


class Bm25Parameters(DomainModel):
    k1: float
    b: float


class RecencyParameters(DomainModel):
    half_life_days: float


class CitationParameters(DomainModel):
    saturation: int


class ExplanationParameters(DomainModel):
    max_features: int
    strong_term_match: float


class FederatedRankingConfig(DomainModel):
    weights: FeatureWeights
    bm25: Bm25Parameters
    recency: RecencyParameters
    citations: CitationParameters
    source_type_values: dict[SourceType, float]
    explanation: ExplanationParameters


def parse_federated_ranking_config(text: str, *, source: str) -> FederatedRankingConfig:
    document: Any = yaml.safe_load(text)
    return FederatedRankingConfig.model_validate(document)


def load_federated_ranking_config(path: Path) -> FederatedRankingConfig:
    return parse_federated_ranking_config(path.read_text(encoding="utf-8"), source=str(path))


class RankedCandidate(DomainModel):
    candidate: MergedCandidate
    rank: int
    total_score: float
    lexical_score: float | None
    features: dict[str, float | None] = Field(default_factory=dict)
    contributions: dict[str, float] = Field(default_factory=dict)
    explanation: str


def rank_merged_candidates(
    candidates: Sequence[MergedCandidate],
    *,
    queries: Sequence[str],
    filters: SearchFilters,
    answered_providers: int,
    now: datetime,
    config: FederatedRankingConfig,
) -> tuple[RankedCandidate, ...]:
    return tuple(
        RankedCandidate(candidate=candidate, rank=rank, total_score=0.0, lexical_score=None, explanation="")
        for rank, candidate in enumerate(candidates, start=1)
    )


def search_result_for(ranked: RankedCandidate, *, search_id: Ulid, article_id: Ulid) -> SearchResult:
    return SearchResult(search_id=search_id, article_id=article_id, rank=ranked.rank)


class FederatedRankStage:
    def __init__(self, config: FederatedRankingConfig, *, clock: Clock) -> None:
        self._config = config
        self._clock = clock

    async def run(self, state: SearchState) -> SearchState:
        return state
