"""What a federated search is asked, what it passes between its stages, and what it answers.

A federated search (E08) is four stages run in a fixed order over one value, :class:`SearchState`:

1. **expand** — turn the request into the queries to ask (argument and need templates, v1-e08-t04);
2. **fan_out** — ask every selected provider every query, concurrently, under one deadline, and
   record how each call ended (:mod:`debate_core.application.federated_search`, this task);
3. **normalize** — collapse what the providers returned into distinct sources, `merged_candidates`
   (:mod:`debate_core.application.federated_dedupe`, v1-e08-t02);
4. **rank** — order them by explainable features, `ranked_candidates`
   (:mod:`debate_core.application.federated_ranking`, v1-e08-t03).

Each stage is a :class:`SearchStage`: it takes the state and returns the next one. The stages that
belong to sibling tasks default to :class:`PassThroughStage`, which returns the state unchanged, so
the pipeline runs end to end today and a later task plugs its stage in rather than editing the
orchestration. A stage that needs to hand something new to the next one (deduplicated candidates,
say) adds a field to :class:`SearchState` with a default; the stages that do not read it are
untouched.

Stages after fan_out leave `provider_statuses` as fan_out wrote them: the search's status and its
stored record are taken from them.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, Self, runtime_checkable

from pydantic import Field, model_validator

from debate_core.domain import (
    DomainModel,
    NonEmptyText,
    Search,
    SearchFilters,
    SearchResult,
    SearchStatus,
    Ulid,
)
from debate_core.domain.base import ORGANIZATION_ID_FIELD, OWNER_ID_FIELD
from debate_core.domain.discovery import CandidateResult, ProviderHealth, ProviderQuery, ProviderStatus

if TYPE_CHECKING:
    from debate_core.application.federated_dedupe import MergedCandidate
    from debate_core.application.federated_ranking import RankedCandidate

__all__ = [
    "PassThroughStage",
    "SearchOutcome",
    "SearchPipeline",
    "SearchRequest",
    "SearchStage",
    "SearchState",
    "StageName",
]


class SearchRequest(DomainModel):
    """One federated search, as a person asked for it."""

    query: NonEmptyText = Field(description="The query text as the user entered it.")
    filters: SearchFilters = Field(
        default_factory=SearchFilters, description="Date window, source types, language and result cap."
    )
    providers: tuple[NonEmptyText, ...] | None = Field(
        default=None,
        description=(
            "The providers to ask, by settings name, in this order; None asks every enabled provider. "
            "A name settings do not enable is reported as not configured, not dropped."
        ),
    )
    owner_id: Ulid | None = Field(default=None, description=OWNER_ID_FIELD)
    organization_id: Ulid | None = Field(default=None, description=ORGANIZATION_ID_FIELD)

    @model_validator(mode="after")
    def _check_providers_name_someone(self) -> Self:
        if self.providers is not None and not self.providers:
            raise ValueError("providers names at least one provider; leave it out to ask every enabled one")
        return self


@dataclass(frozen=True, slots=True)
class SearchState:
    """Everything one search has worked out so far, handed from stage to stage.

    Immutable: a stage returns a new state (:meth:`evolve`) rather than changing the one it was
    given, so what a stage saw is still there to inspect after it ran.
    """

    search_id: Ulid
    """The id the search will be stored under, minted before the first stage runs."""

    request: SearchRequest
    """What was asked."""

    queries: tuple[ProviderQuery, ...]
    """What every provider will be asked. Starts as the request's own query; expand may change it."""

    provider_statuses: tuple[ProviderStatus, ...] = ()
    """How each call ended, query by query and provider by provider. Written by fan_out."""

    candidates: tuple[CandidateResult, ...] = ()
    """What the providers that answered returned, in the order of `provider_statuses`."""

    merged_candidates: tuple[MergedCandidate, ...] = ()
    """`candidates` collapsed into one entry per distinct source, by the normalize stage."""

    ranked_candidates: tuple[RankedCandidate, ...] = ()
    """`merged_candidates` in rank order, each with its features and explanation, by the rank stage."""

    results: tuple[SearchResult, ...] = ()
    """The ranking as stored with the search: one SearchResult per ranked candidate that has an
    Article. Empty until a stage registers ranked candidates as Articles (v1-e08-t05)."""

    @classmethod
    def start(cls, search_id: Ulid, request: SearchRequest) -> SearchState:
        """The state before any stage: one query, the request's own, under its own filters."""
        return cls(
            search_id=search_id,
            request=request,
            queries=(ProviderQuery(query=request.query, filters=request.filters),),
        )

    def evolve(
        self,
        *,
        queries: tuple[ProviderQuery, ...] | None = None,
        provider_statuses: tuple[ProviderStatus, ...] | None = None,
        candidates: tuple[CandidateResult, ...] | None = None,
        merged_candidates: tuple[MergedCandidate, ...] | None = None,
        ranked_candidates: tuple[RankedCandidate, ...] | None = None,
        results: tuple[SearchResult, ...] | None = None,
    ) -> SearchState:
        """A copy with the given fields replaced; `search_id` and `request` never change."""
        return dataclasses.replace(
            self,
            queries=self.queries if queries is None else queries,
            provider_statuses=self.provider_statuses if provider_statuses is None else provider_statuses,
            candidates=self.candidates if candidates is None else candidates,
            merged_candidates=self.merged_candidates if merged_candidates is None else merged_candidates,
            ranked_candidates=self.ranked_candidates if ranked_candidates is None else ranked_candidates,
            results=self.results if results is None else results,
        )


@runtime_checkable
class SearchStage(Protocol):
    """One step of a federated search: takes the state so far and returns the next one."""

    async def run(self, state: SearchState) -> SearchState:
        """Do this stage's work and return the new state."""
        ...


class PassThroughStage:
    """The stage that changes nothing: the default for every stage a sibling task delivers."""

    async def run(self, state: SearchState) -> SearchState:
        return state

    def __repr__(self) -> str:
        return "PassThroughStage()"


class StageName(StrEnum):
    """The four stages, in the order they run."""

    EXPAND = "expand"
    FAN_OUT = "fan_out"
    NORMALIZE = "normalize"
    RANK = "rank"


@dataclass(frozen=True, slots=True, kw_only=True)
class SearchPipeline:
    """The four stages of a federated search, one per :class:`StageName`, run in that order."""

    expand: SearchStage = field(default_factory=PassThroughStage)
    fan_out: SearchStage
    normalize: SearchStage = field(default_factory=PassThroughStage)
    rank: SearchStage = field(default_factory=PassThroughStage)

    @property
    def stages(self) -> tuple[tuple[StageName, SearchStage], ...]:
        """Each stage under its name, in the order they run: expand, fan_out, normalize, rank."""
        return (
            (StageName.EXPAND, self.expand),
            (StageName.FAN_OUT, self.fan_out),
            (StageName.NORMALIZE, self.normalize),
            (StageName.RANK, self.rank),
        )


@dataclass(frozen=True, slots=True)
class SearchOutcome:
    """What a federated search produced: the stored record and what each stage left behind.

    `provider_statuses` names every call and how it ended, so the CLI can say "partial: OpenAlex
    timed out" rather than quietly showing fewer results. `provider_health` is each enabled
    provider's record just after the search, for the status footer.
    """

    search: Search
    provider_statuses: tuple[ProviderStatus, ...]
    candidates: tuple[CandidateResult, ...]
    results: tuple[SearchResult, ...]
    provider_health: tuple[ProviderHealth, ...]

    @property
    def status(self) -> SearchStatus:
        """COMPLETE, PARTIAL or FAILED, as stored on the search."""
        return self.search.status
