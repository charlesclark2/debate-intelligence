"""Federated deduplication: one entry per source, whichever providers found it (v1-e08-t02).

SKELETON: merges nothing yet. Every candidate is its own MergedCandidate.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from pydantic import Field

from debate_core.application.federated_search_types import SearchState
from debate_core.domain import DomainModel, NonEmptyText
from debate_core.domain.article import ArticleIdentifiers
from debate_core.domain.base import HttpUrlStr, UtcDatetime
from debate_core.domain.discovery import CandidateResult
from debate_core.domain.enums import SourceType

__all__ = [
    "FIELD_PRECEDENCE",
    "MERGED_FIELDS",
    "MIN_TITLE_TOKENS",
    "DedupeStage",
    "MatchRule",
    "MergedCandidate",
    "candidate_canonical_url",
    "merge_candidates",
    "merge_group",
    "surname_key",
    "title_tokens",
    "titles_agree",
]

MIN_TITLE_TOKENS: Final = 3


class MatchRule(StrEnum):
    DOI = "doi"
    CANONICAL_URL = "canonical_url"
    PROVIDER_ID = "provider_id"
    TITLE = "title"


MERGED_FIELDS: Final = (
    "title",
    "url",
    "canonical_url",
    "identifiers.doi",
    "identifiers.arxiv_id",
    "identifiers.pmid",
    "identifiers.openalex_id",
    "identifiers.semantic_scholar_id",
    "source_type",
    "authors",
    "publication",
    "published_at",
    "snippet",
    "open_access_url",
)


class MergedCandidate(DomainModel):
    title: NonEmptyText
    url: HttpUrlStr
    canonical_url: HttpUrlStr | None = None
    identifiers: ArticleIdentifiers = Field(default_factory=ArticleIdentifiers)
    source_type: SourceType = SourceType.OTHER
    authors: tuple[NonEmptyText, ...] = ()
    publication: NonEmptyText | None = None
    published_at: UtcDatetime | None = None
    snippet: str | None = None
    open_access_url: HttpUrlStr | None = None
    providers: tuple[NonEmptyText, ...]
    members: tuple[CandidateResult, ...]
    matched_on: tuple[MatchRule, ...] = ()
    field_sources: dict[str, NonEmptyText]


FIELD_PRECEDENCE: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType({})


def surname_key(name: str) -> str | None:
    return None


def title_tokens(title: str) -> tuple[str, ...]:
    return ()


def titles_agree(left: str, right: str) -> bool:
    return False


def candidate_canonical_url(candidate: CandidateResult) -> str | None:
    return candidate.canonical_url


def merge_candidates(candidates: Sequence[CandidateResult]) -> tuple[MergedCandidate, ...]:
    return tuple(_alone(candidate) for candidate in candidates)


def merge_group(members: Sequence[CandidateResult], matched_on: Sequence[MatchRule] = ()) -> MergedCandidate:
    first = _alone(members[0])
    providers = tuple(dict.fromkeys(member.provider for member in members))
    return first.evolve(members=tuple(members), providers=providers, matched_on=tuple(matched_on))


def _alone(candidate: CandidateResult) -> MergedCandidate:
    values: dict[str, object] = {
        "title": candidate.title,
        "url": candidate.url,
        "canonical_url": candidate.canonical_url,
        "identifiers.doi": candidate.identifiers.doi,
        "identifiers.arxiv_id": candidate.identifiers.arxiv_id,
        "identifiers.pmid": candidate.identifiers.pmid,
        "identifiers.openalex_id": candidate.identifiers.openalex_id,
        "identifiers.semantic_scholar_id": candidate.identifiers.semantic_scholar_id,
        "source_type": candidate.source_type,
        "authors": candidate.authors,
        "publication": candidate.publication,
        "published_at": candidate.published_at,
        "snippet": candidate.snippet,
        "open_access_url": candidate.open_access_url,
    }
    return MergedCandidate(
        title=candidate.title,
        url=candidate.url,
        canonical_url=candidate.canonical_url,
        identifiers=candidate.identifiers,
        source_type=candidate.source_type,
        authors=candidate.authors,
        publication=candidate.publication,
        published_at=candidate.published_at,
        snippet=candidate.snippet,
        open_access_url=candidate.open_access_url,
        providers=(candidate.provider,),
        members=(candidate,),
        field_sources={name: candidate.provider for name, value in values.items() if value not in (None, ())},
    )


class DedupeStage:
    async def run(self, state: SearchState) -> SearchState:
        return state.evolve(merged_candidates=merge_candidates(state.candidates))
