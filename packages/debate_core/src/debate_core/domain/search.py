"""Search-side entities: the request a user made, and the ranked results it produced.

A :class:`Search` is kept as a record rather than thrown away after the results are rendered, so a
piece of research can be reproduced and audited: which query, which filters, which providers, and
whether every provider actually answered.

:class:`SearchResult` carries the ranking features that produced its position. Source quality is
always expressed as named, inspectable features with a human-readable explanation — never as a
hidden "truth" or ideology score (architecture proposal §9).
"""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from debate_core.domain.base import (
    ORGANIZATION_ID_FIELD,
    OWNER_ID_FIELD,
    DomainEntity,
    DomainModel,
    NonEmptyText,
    Ulid,
    UtcDatetime,
    new_id,
)
from debate_core.domain.enums import SearchStatus, SourceType

__all__ = ["Search", "SearchFilters", "SearchResult"]


class SearchFilters(DomainModel):
    """The constraints a user put on a search, stored with the search so it can be replayed."""

    since: UtcDatetime | None = Field(
        default=None, description="Only results published at or after this UTC instant."
    )
    until: UtcDatetime | None = Field(
        default=None, description="Only results published at or before this UTC instant."
    )
    source_types: tuple[SourceType, ...] = Field(
        default=(), description="Restrict to these source types; empty means no restriction."
    )
    max_results: int = Field(default=20, ge=1, le=200, description="Maximum results to return.")
    language: NonEmptyText | None = Field(
        default=None, description="BCP 47 language tag to restrict results to, if any."
    )

    @model_validator(mode="after")
    def _check_window(self) -> Self:
        if self.since is not None and self.until is not None and self.since > self.until:
            raise ValueError(f"since ({self.since.isoformat()}) is after until ({self.until.isoformat()})")
        return self


class Search(DomainEntity):
    """One federated search across the enabled discovery providers.

    `provider_set` records which providers were actually selected for this search, and `status`
    records whether they all answered. Together they are what lets the CLI say "these results are
    partial because OpenAlex timed out" instead of quietly returning less.
    """

    search_id: Ulid = Field(default_factory=new_id, description="ULID primary key.")
    owner_id: Ulid | None = Field(default=None, description=OWNER_ID_FIELD)
    organization_id: Ulid | None = Field(default=None, description=ORGANIZATION_ID_FIELD)
    query: NonEmptyText = Field(description="The query text as the user entered it.")
    filters: SearchFilters = Field(default_factory=SearchFilters, description="Constraints applied.")
    provider_set: tuple[NonEmptyText, ...] = Field(
        default=(), description="Names of the providers selected for this search."
    )
    status: SearchStatus = Field(description="Whether every selected provider answered.")


class SearchResult(DomainModel):
    """One article's position in one search, with the features that put it there.

    Identified by the pair (`search_id`, `article_id`) rather than by an id of its own: a result
    only exists as part of a search, and a search holds at most one result per article.

    The scores are all optional because the V1 ranking pipeline is deterministic and lexical;
    `semantic_score` and `rerank_score` are filled in by the embedding and rerank stages that
    arrive with the V2 search index.
    """

    search_id: Ulid = Field(description="The search this result belongs to.")
    article_id: Ulid = Field(description="The article that was returned.")
    rank: int = Field(ge=1, description="1-based position in the final ordering.")
    total_score: float | None = Field(
        default=None, description="Combined score from the configured ranking weights."
    )
    lexical_score: float | None = Field(default=None, description="BM25 relevance of title and snippet.")
    semantic_score: float | None = Field(default=None, description="Embedding similarity to the query.")
    rerank_score: float | None = Field(default=None, description="Cross-encoder rerank score, when run.")
    source_quality_features: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Named ranking features and their values, for example recency, peer_reviewed, "
            "open_access, citations, provider_agreement. Never a hidden credibility score."
        ),
    )
    explanation: str | None = Field(
        default=None,
        description='Human-readable reason for the rank, e.g. "recent (3 days), peer-reviewed".',
    )
    providers: tuple[NonEmptyText, ...] = Field(
        default=(), description="Providers that returned this article; more than one means agreement."
    )
