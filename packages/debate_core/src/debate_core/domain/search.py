"""Search-side entities: the request a user made, and the ranked results it produced.

A :class:`Search` is kept as a record rather than thrown away after the results are rendered, so a
piece of research can be reproduced and audited: which query, which filters, which providers, and
whether every provider actually answered.

:class:`SearchResult` carries the ranking features that produced its position. Source quality is
always expressed as named, inspectable features with a human-readable explanation — never as a
hidden "truth" or ideology score (architecture proposal §9).

:class:`SearchExpansion` is how a search's query was expanded by debate argument and need
(v1-e08-t04-argument-need-expansion): every query asked, the template or model suggestion it came
from and the date window it was given. Each provider call's exact query is also in its
`ProviderStatus.query`, but the argument, the need, the template, where a window came from and a
model's rationale are not, and a search that reached no provider has no call to read them from.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import Field, NonNegativeInt, model_validator

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
from debate_core.domain.provenance import GeneratedArtifactMetadata

__all__ = [
    "ExpandedQuery",
    "QueryOrigin",
    "Search",
    "SearchExpansion",
    "SearchFilters",
    "SearchResult",
    "WindowSource",
]


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


class QueryOrigin(StrEnum):
    """Where an expanded query came from."""

    TEMPLATE = "template"
    """Rendered from one of the taxonomy's templates for the argument and need."""

    MODEL = "model"
    """Suggested by a model and validated against its schema (`--expand-llm`)."""


class WindowSource(StrEnum):
    """Which rule set an expanded query's `since`."""

    NEED = "need"
    """The need's default window in the taxonomy."""

    TEMPLATE = "template"
    """The template's own window, which it set instead of the need's."""

    REQUEST = "request"
    """The search's own `since`, which a person set and no default replaces."""


class ExpandedQuery(DomainModel):
    """One query an expanded search asked every provider, and why it was asked."""

    query: NonEmptyText = Field(description="The query text exactly as the providers were asked it.")
    origin: QueryOrigin = Field(description="A template's, or a model's suggestion.")
    template_id: NonEmptyText | None = Field(
        default=None,
        description="`<argument>/<need>/<n>`, the n-th template of the pair; template queries only.",
    )
    template: NonEmptyText | None = Field(
        default=None, description="The template's text, its variables still in braces; template queries only."
    )
    rationale: NonEmptyText | None = Field(
        default=None, description="Why the model suggested the query, in its words; model queries only."
    )
    since: UtcDatetime | None = Field(default=None, description="The `since` the query was asked with.")
    recency_days: NonNegativeInt | None = Field(
        default=None, description="The taxonomy's window in days; None when it accepts any age."
    )
    window: WindowSource = Field(description="Which rule set `since`.")

    @model_validator(mode="after")
    def _check_origin(self) -> Self:
        from_template = self.origin is QueryOrigin.TEMPLATE
        if from_template != (self.template_id is not None and self.template is not None):
            raise ValueError("a template query names its template and id, and a model query names neither")
        if from_template == (self.rationale is not None):
            raise ValueError("a model query carries its rationale, and a template query carries none")
        return self


class SearchExpansion(DomainModel):
    """How one search's query was expanded by argument and need, recorded with the search."""

    taxonomy_version: NonEmptyText = Field(description="The `config/argument_taxonomy.yaml` version used.")
    argument: NonEmptyText = Field(description="The argument's id, after any alias was resolved.")
    need: NonEmptyText = Field(description="The need's id, after any alias was resolved.")
    topic_id: NonEmptyText | None = Field(default=None, description="The topic preset used, if any.")
    variables: dict[str, str] = Field(description="The value every variable was filled with.")
    queries: tuple[ExpandedQuery, ...] = Field(
        min_length=1, description="Every query asked, templates' first and then a model's, in order."
    )
    skipped_templates: tuple[NonEmptyText, ...] = Field(
        default=(), description="Ids of the pair's templates not used because the search lacked a variable."
    )
    model_requested: bool = Field(default=False, description="Whether model expansion was asked for.")
    model: GeneratedArtifactMetadata | None = Field(
        default=None, description="The model call whose suggestions were added; None when none were."
    )
    warning: NonEmptyText | None = Field(
        default=None, description="Why model expansion was asked for and the templates were used alone."
    )

    @model_validator(mode="after")
    def _check_model_queries(self) -> Self:
        suggested = any(query.origin is QueryOrigin.MODEL for query in self.queries)
        if suggested != (self.model is not None):
            raise ValueError("model metadata is recorded exactly when a model's queries were added")
        if self.model is not None and not self.model_requested:
            raise ValueError("a model's queries were added to an expansion that did not ask for them")
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
    expansion: SearchExpansion | None = Field(
        default=None,
        exclude_if=lambda expansion: expansion is None,
        description="How the query was expanded by argument and need; absent when it was not.",
    )


class SearchResult(DomainModel):
    """One article's position in one search, with the features that put it there.

    Identified by the pair (`search_id`, `article_id`) rather than by an id of its own: a result
    only exists as part of a search, and a search holds at most one result per article.

    The scores are all optional because the V1 ranking pipeline is deterministic and lexical;
    `semantic_score` and `rerank_score` are filled in by the embedding and rerank stages that
    arrive with the V2 search index.

    A feature can be unknown, and is then stored as None rather than left out or written as 0: no
    discovery provider says whether a paper was peer-reviewed yet, and 0 would say it was not
    (v1-e08-t03-feature-ranking).
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
    source_quality_features: dict[str, float | None] = Field(
        default_factory=dict,
        description=(
            "Named ranking features and their values, for example recency, peer_reviewed, "
            "open_access, citations, provider_agreement; None where a feature is unknown, which is "
            "not the same as 0. Never a hidden credibility score."
        ),
    )
    explanation: str | None = Field(
        default=None,
        description='Human-readable reason for the rank, e.g. "recent (3 days), peer-reviewed".',
    )
    providers: tuple[NonEmptyText, ...] = Field(
        default=(), description="Providers that returned this article; more than one means agreement."
    )
