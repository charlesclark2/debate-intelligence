"""Federated ranking: one transparent score per source, and the reasons for it (v1-e08-t03).

The rank stage of a federated search (:class:`FederatedRankStage`) orders `merged_candidates` into
`ranked_candidates`. Each :class:`RankedCandidate` carries its seven features
(:mod:`debate_core.application.federated_ranking_features`), how much each contributed, the total
and a sentence a debater can read. No model is called and nothing is fetched: the order is a pure
function of what the providers returned, the query and the weight table.

## The weight table

`config/federated_ranking.yaml` (:data:`FEDERATED_RANKING_CONFIG_PATH`), loaded by
:func:`load_federated_ranking_config`. Every number that decides an order is in it: the seven
weights, BM25's `k1` and `b`, the recency half-life, the citation saturation, the value of each
source type and the explanation's two settings. The table names categories of source, never an
outlet, and there is no list of publishers: the only thing that removes a result is the user's own
filter. A table that is missing a key, has one it does not know, or holds a value the ranking
cannot use (a negative weight, `b` above 1, every weight 0) is refused when it is loaded, naming
the key.

## The score

`total = sum(weight[f] * value[f])` over the features whose value is known. An unknown feature
contributes 0 and is not mentioned in the explanation: "no provider said" is not "no".

## The order

1. The user's filters first: `source_types` (when it names any), then BM25 is scaled over what is
   left, so a filtered-out result never sets the scale.
2. Total score, highest first.
3. Ties: `published_at`, newest first, undated last; then `canonical_url`, or `url` for a source
   with no canonical form, ascending.
4. The first `max_results` are kept and numbered from 1.

Identical inputs and table give an identical order, whatever order the candidates came in.
The date window is not applied again here: the adapters pass it to the providers. An undated result
stays in, with its recency unknown.

## The explanation

The largest contributions, largest first, at most `explanation.max_features` of them; a tie between
two goes to the one earlier in :data:`~debate_core.application.federated_ranking_features.FEATURE_NAMES`.
Each feature has one phrase:

| Feature | Phrase |
|---|---|
| bm25 | "strong term match" at or above `strong_term_match`, "some term match" below it |
| recency | "recent (3 days)" under 60 days, "published 4 months ago" under two years, then years |
| source_type | "scholarly source", "government source", "think-tank source", "news source", "other source" |
| peer_reviewed | none: it is always unknown; the task that reads a provider's field adds one |
| open_access | "open access" |
| citations | "cited once", "cited 1,204 times" |
| provider_agreement | "found by 3 providers" |

A result to which no feature contributed reads "no feature contributed to the score".

## What is stored

:func:`search_result_for` builds the :class:`~debate_core.domain.SearchResult` a search stores for a
ranked candidate once it has an Article: the rank, the total, the raw BM25 as `lexical_score`, all
seven features (an unknown one as None) and the explanation. Registering ranked candidates as
Articles, without fetching them, is v1-e08-t05's (PM ruling 2026-10-22), so this stage leaves
`results` empty.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Annotated, Final, Self

import yaml
from pydantic import Field, ValidationError, field_validator, model_validator

from debate_core.application.federated_dedupe import MergedCandidate
from debate_core.application.federated_ranking_features import (
    FEATURE_NAMES,
    FeatureVector,
    age_in_days,
    bm25_scores,
    citations,
    document_tokens,
    open_access,
    peer_reviewed,
    provider_agreement,
    query_terms,
    recency,
    source_type_value,
)
from debate_core.application.federated_search_types import SearchState
from debate_core.application.ports.providers import Clock
from debate_core.application.settings import ConfigurationError
from debate_core.domain import DomainModel, SearchFilters, SearchResult, Ulid
from debate_core.domain.discovery import ProviderOutcome
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
"""The committed weight table, relative to the repository root (and to an installed build's
bundled `config/`, which `scripts/stamp_build.py` copies whole)."""


class InvalidFederatedRankingConfig(ConfigurationError):
    """The weight table could not be read, or holds a value the ranking cannot use."""


# ---------------------------------------------------------------------------------------------
# The weight table
# ---------------------------------------------------------------------------------------------


class FeatureWeights(DomainModel):
    """How much each feature counts. Any non-negative number; at least one must be above 0."""

    bm25: float = Field(ge=0)
    recency: float = Field(ge=0)
    source_type: float = Field(ge=0)
    peer_reviewed: float = Field(ge=0)
    open_access: float = Field(ge=0)
    citations: float = Field(ge=0)
    provider_agreement: float = Field(ge=0)

    @model_validator(mode="after")
    def _check_something_counts(self) -> Self:
        if not any(self.weight_of(name) for name in FEATURE_NAMES):
            raise ValueError("every weight is 0, so every result would score the same")
        return self

    def weight_of(self, feature: str) -> float:
        """The weight of one of :data:`FEATURE_NAMES`."""
        weight: float = getattr(self, feature)
        return weight


class Bm25Parameters(DomainModel):
    """Okapi BM25's term-frequency saturation `k1` and length normalization `b`."""

    k1: float = Field(ge=0)
    b: float = Field(ge=0, le=1)


class RecencyParameters(DomainModel):
    """Recency without a date window: the age at which a result scores 0.5."""

    half_life_days: float = Field(gt=0)


class CitationParameters(DomainModel):
    """The citation count at which the citations feature reaches 1."""

    saturation: int = Field(ge=1)


class ExplanationParameters(DomainModel):
    """How many contributions an explanation names, and what counts as a strong term match."""

    max_features: int = Field(ge=1)
    strong_term_match: float = Field(gt=0, le=1)


class FederatedRankingConfig(DomainModel):
    """The whole weight table, as `config/federated_ranking.yaml` writes it."""

    weights: FeatureWeights
    bm25: Bm25Parameters
    recency: RecencyParameters
    citations: CitationParameters
    source_type_values: dict[SourceType, Annotated[float, Field(ge=0, le=1)]]
    explanation: ExplanationParameters

    @field_validator("source_type_values")
    @classmethod
    def _check_every_category_has_a_value(cls, values: dict[SourceType, float]) -> dict[SourceType, float]:
        missing = [source_type.value for source_type in SourceType if source_type not in values]
        if missing:
            raise ValueError(f"every source type needs a value; missing: {', '.join(missing)}")
        return values


def _field_of(error: ValidationError) -> str:
    """The dotted key of the first problem pydantic found, as the table spells it."""
    return ".".join(str(part) for part in error.errors()[0]["loc"] if part != "[key]")


def parse_federated_ranking_config(text: str, *, source: str) -> FederatedRankingConfig:
    """Read a weight table from YAML text; `source` names it in a refusal."""
    try:
        document: object = yaml.safe_load(text)
    except yaml.YAMLError:
        raise InvalidFederatedRankingConfig(f"{source} is not valid YAML", source=source) from None
    if not isinstance(document, dict):
        raise InvalidFederatedRankingConfig(f"{source} must be a mapping of sections", source=source)
    try:
        return FederatedRankingConfig.model_validate(document)
    except ValidationError as invalid:
        field = _field_of(invalid)
        reason = invalid.errors()[0]["msg"]
        raise InvalidFederatedRankingConfig(
            f"{source}: {field}: {reason}", field=field, source=source
        ) from None


def load_federated_ranking_config(path: Path) -> FederatedRankingConfig:
    """Load the weight table at `path` (the committed one is :data:`FEDERATED_RANKING_CONFIG_PATH`)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as unreadable:
        raise InvalidFederatedRankingConfig(
            f"{path} could not be read: {unreadable.strerror}", source=str(path)
        ) from None
    return parse_federated_ranking_config(text, source=str(path))


# ---------------------------------------------------------------------------------------------
# Ranked candidates
# ---------------------------------------------------------------------------------------------


class RankedCandidate(DomainModel):
    """One source in its place in a ranking, with every number that put it there."""

    candidate: MergedCandidate = Field(description="The source, as deduplication merged it.")
    rank: int = Field(ge=1, description="1-based position in the ranking.")
    total_score: float = Field(description="The sum of the contributions.")
    lexical_score: float | None = Field(
        description="Raw BM25 against the query terms, before scaling; None when the query has no terms."
    )
    features: dict[str, float | None] = Field(
        description="The seven features by name, each between 0 and 1, or None when unknown."
    )
    contributions: dict[str, float] = Field(
        description="Each feature's weight times its value; 0 for an unknown feature."
    )
    explanation: str = Field(description="The largest contributions, in words.")

    @model_validator(mode="after")
    def _check_the_seven_features_are_named(self) -> Self:
        if list(self.features) != list(FEATURE_NAMES):
            raise ValueError(f"features must name {FEATURE_NAMES} in order, not {tuple(self.features)}")
        if list(self.contributions) != list(FEATURE_NAMES):
            raise ValueError(
                f"contributions must name {FEATURE_NAMES} in order, not {tuple(self.contributions)}"
            )
        return self


def search_result_for(ranked: RankedCandidate, *, search_id: Ulid, article_id: Ulid) -> SearchResult:
    """The record a search stores for a ranked candidate, once `article_id` names its Article."""
    return SearchResult(
        search_id=search_id,
        article_id=article_id,
        rank=ranked.rank,
        total_score=ranked.total_score,
        lexical_score=ranked.lexical_score,
        source_quality_features=dict(ranked.features),
        explanation=ranked.explanation,
        providers=ranked.candidate.providers,
    )


# ---------------------------------------------------------------------------------------------
# Explanations
# ---------------------------------------------------------------------------------------------

_SOURCE_TYPE_PHRASES: Final[Mapping[SourceType, str]] = {
    SourceType.SCHOLARLY: "scholarly source",
    SourceType.GOVERNMENT: "government source",
    SourceType.THINK_TANK: "think-tank source",
    SourceType.NEWS: "news source",
    SourceType.OTHER: "other source",
}

_RECENT_DAYS: Final = 60
_MONTHS_UNTIL_DAYS: Final = 730
_DAYS_PER_MONTH: Final = 30
_DAYS_PER_YEAR: Final = 365

NOTHING_CONTRIBUTED: Final = "no feature contributed to the score"


def _recency_phrase(days: int) -> str:
    if days == 0:
        return "recent (today)"
    if days < _RECENT_DAYS:
        return f"recent ({days} day{'' if days == 1 else 's'})"
    if days < _MONTHS_UNTIL_DAYS:
        return f"published {days // _DAYS_PER_MONTH} months ago"
    return f"published {days // _DAYS_PER_YEAR} years ago"


def _phrase(
    feature: str,
    value: float,
    candidate: MergedCandidate,
    *,
    reference: datetime,
    config: FederatedRankingConfig,
) -> str:
    """The words for one feature that contributed. Only called for a known, positive contribution."""
    match feature:
        case "bm25":
            return "strong term match" if value >= config.explanation.strong_term_match else "some term match"
        case "recency":
            return _recency_phrase(age_in_days(candidate.published_at, reference) or 0)
        case "source_type":
            return _SOURCE_TYPE_PHRASES[candidate.source_type]
        case "open_access":
            return "open access"
        case "citations":
            count = candidate.citation_count or 0
            return "cited once" if count == 1 else f"cited {count:,} times"
        case "provider_agreement":
            return f"found by {len(candidate.providers)} providers"
        case _:
            raise ValueError(f"no phrase for feature {feature!r}")


def _explanation(
    candidate: MergedCandidate,
    vector: FeatureVector,
    contributions: Mapping[str, float],
    *,
    reference: datetime,
    config: FederatedRankingConfig,
) -> str:
    values = vector.as_dict()
    contributing = sorted(
        (name for name in FEATURE_NAMES if contributions[name] > 0),
        key=lambda name: (-contributions[name], FEATURE_NAMES.index(name)),
    )[: config.explanation.max_features]
    phrases = [
        _phrase(name, values[name] or 0.0, candidate, reference=reference, config=config)
        for name in contributing
    ]
    return ", ".join(phrases) if phrases else NOTHING_CONTRIBUTED


# ---------------------------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------------------------


def _order_key(candidate: MergedCandidate, total: float) -> tuple[float, bool, float, str]:
    """Highest total first; then newest first, undated last; then canonical URL, or URL, ascending."""
    published = candidate.published_at
    return (
        -total,
        published is None,
        -published.timestamp() if published is not None else 0.0,
        candidate.canonical_url or candidate.url,
    )


def rank_merged_candidates(
    candidates: Sequence[MergedCandidate],
    *,
    queries: Sequence[str],
    filters: SearchFilters,
    answered_providers: int,
    now: datetime,
    config: FederatedRankingConfig,
) -> tuple[RankedCandidate, ...]:
    """Score, order, cap and explain `candidates` (see the module docstring).

    `queries` is every query asked (the expanded ones too), `answered_providers` the number of
    distinct providers that answered, and `now` the time recency is measured from when the
    filters set no `until`.
    """
    kept = [
        candidate
        for candidate in candidates
        if not filters.source_types or candidate.source_type in filters.source_types
    ]
    terms = query_terms(queries)
    raw_bm25 = bm25_scores(
        [document_tokens(candidate) for candidate in kept], terms, k1=config.bm25.k1, b=config.bm25.b
    )
    best = max(raw_bm25, default=0.0)
    reference = filters.until if filters.until is not None else now

    scored: list[tuple[MergedCandidate, float, float | None, FeatureVector, dict[str, float]]] = []
    for candidate, raw in zip(kept, raw_bm25, strict=True):
        vector = FeatureVector(
            bm25=(raw / best if best > 0 else 0.0) if terms else None,
            recency=recency(
                candidate.published_at,
                reference=reference,
                since=filters.since,
                half_life_days=config.recency.half_life_days,
            ),
            source_type=source_type_value(candidate.source_type, config.source_type_values),
            peer_reviewed=peer_reviewed(candidate),
            open_access=open_access(candidate),
            citations=citations(candidate, saturation=config.citations.saturation),
            provider_agreement=provider_agreement(candidate, answered=answered_providers),
        )
        contributions = {
            name: config.weights.weight_of(name) * value if value is not None else 0.0
            for name, value in vector.as_dict().items()
        }
        total = sum(contributions[name] for name in FEATURE_NAMES)
        scored.append((candidate, total, raw if terms else None, vector, contributions))

    ordered = sorted(scored, key=lambda entry: _order_key(entry[0], entry[1]))[: filters.max_results]
    return tuple(
        RankedCandidate(
            candidate=candidate,
            rank=position,
            total_score=total,
            lexical_score=lexical,
            features=vector.as_dict(),
            contributions=contributions,
            explanation=_explanation(candidate, vector, contributions, reference=reference, config=config),
        )
        for position, (candidate, total, lexical, vector, contributions) in enumerate(ordered, start=1)
    )


class FederatedRankStage:
    """The rank stage: `merged_candidates` ordered into `ranked_candidates`, nothing else changed."""

    def __init__(self, config: FederatedRankingConfig, *, clock: Clock) -> None:
        self._config = config
        self._clock = clock

    def __repr__(self) -> str:
        return "FederatedRankStage()"

    async def run(self, state: SearchState) -> SearchState:
        """Rank under the request's own filters, counting the distinct providers that answered."""
        answered = {
            status.provider for status in state.provider_statuses if status.outcome is ProviderOutcome.OK
        }
        ranked = rank_merged_candidates(
            state.merged_candidates,
            queries=[query.query for query in state.queries],
            filters=state.request.filters,
            answered_providers=len(answered),
            now=self._clock.now(),
            config=self._config,
        )
        return state.evolve(ranked_candidates=ranked)
