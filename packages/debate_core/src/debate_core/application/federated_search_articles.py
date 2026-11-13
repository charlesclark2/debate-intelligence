"""Ranked candidates become stored results: each one matched to an Article, never fetched (v1-e08-t05).

The last step of the search command's rank slot (:class:`ArticleMatchingStage`, run after
:class:`~debate_core.application.federated_ranking.FederatedRankStage`). A stored
:class:`~debate_core.domain.SearchResult` names an Article, so every ranked candidate needs one:

1. its canonical URL (:attr:`MergedCandidate.canonical_url`, the canonical form v1-e04-t01 gives the
   merged URL) is looked up with
   :meth:`~debate_core.application.ports.persistence.ArticleRepository.find_by_canonical_url`;
2. a stored Article answers it as it stands: nothing about it is rewritten, because its access status
   and metadata may come from a retrieval, which knows more than a search result does;
3. otherwise a **discovery-only** Article is saved from the candidate's metadata, with access
   `UNKNOWN`. Nothing is fetched here: this stage has no fetcher, and an Article's access is only
   ever measured by `fetch` or `cut` (v1-e04-t05). A date known only to its year or month (a
   Crossref deposit's, v1-e07-t03) is stored at that precision (:attr:`~debate_core.domain.Article.
   date_precision`, `v1-e06-t13`), never as a day; until then it was not stored at all.

The result is :func:`~debate_core.application.federated_ranking.search_result_for` for that Article.
A candidate with no canonical form keeps its place in the ranking and stores no result; nor does a
second candidate that names an Article already holding a place, because a stored ranking holds each
Article once (:meth:`~debate_core.application.ports.persistence.SearchRepository.save_results`).

## A canonical URL is the platform's, not an owner's

The lookup is by canonical URL alone, whoever saved the Article, and a discovery-only Article is
saved with the request's owner and organization (None in V1's CLI, as every fetched Article is).
That is the rule :class:`~debate_core.application.article_service.ArticleService` already follows,
so the Article a search registers is the one a later `fetch` of the same URL finds and fills in,
rather than a second record of the same public source. An Article is a shared description of a
public source (the port's `save` is last-writer-wins for that reason); what is private is the search
and the cards, which carry their owner. V2's accounts may partition this, and then the rule changes
in one place, the lookup.
"""

from __future__ import annotations

from debate_core.application.federated_ranking import RankedCandidate, search_result_for
from debate_core.application.federated_search_types import SearchState
from debate_core.application.ports.persistence import ArticleRepository
from debate_core.application.ports.providers import Clock, IdGenerator
from debate_core.domain import AccessStatus, Article, SearchResult
from debate_core.domain.discovery import DatePrecision

__all__ = ["ArticleMatchingStage", "discovery_article"]


def discovery_article(
    ranked: RankedCandidate,
    *,
    canonical_url: str,
    article_id: str,
    owner_id: str | None,
    organization_id: str | None,
    clock: Clock,
) -> Article:
    """The Article a search registers for a source no Article has yet: its metadata, access UNKNOWN."""
    candidate = ranked.candidate
    now = clock.now()
    return Article(
        article_id=article_id,
        owner_id=owner_id,
        organization_id=organization_id,
        canonical_url=canonical_url,
        title=candidate.title,
        authors=candidate.authors,
        publication=candidate.publication,
        published_at=candidate.published_at,
        date_precision=candidate.date_precision or DatePrecision.DAY,
        source_type=candidate.source_type,
        access_status=AccessStatus.UNKNOWN,
        identifiers=candidate.identifiers,
        created_at=now,
        updated_at=now,
    )


class ArticleMatchingStage:
    """Matches each ranked candidate to an Article, registering a discovery-only one where none exists."""

    def __init__(self, articles: ArticleRepository, *, clock: Clock, ids: IdGenerator) -> None:
        self._articles = articles
        self._clock = clock
        self._ids = ids

    def __repr__(self) -> str:
        return "ArticleMatchingStage()"

    async def run(self, state: SearchState) -> SearchState:
        """`results`, one per ranked candidate that has an Article, in rank order, and their `articles`."""
        results: list[SearchResult] = []
        articles: list[Article] = []
        for ranked in state.ranked_candidates:
            article = await self._article_for(ranked, state)
            if article is None or any(placed.article_id == article.article_id for placed in articles):
                continue
            articles.append(article)
            results.append(
                search_result_for(ranked, search_id=state.search_id, article_id=article.article_id)
            )
        return state.evolve(results=tuple(results), articles=tuple(articles))

    async def _article_for(self, ranked: RankedCandidate, state: SearchState) -> Article | None:
        canonical_url = ranked.candidate.canonical_url
        if canonical_url is None:
            return None
        known = await self._articles.find_by_canonical_url(canonical_url)
        if known is not None:
            return known
        article = discovery_article(
            ranked,
            canonical_url=canonical_url,
            article_id=self._ids.new_id(),
            owner_id=state.request.owner_id,
            organization_id=state.request.organization_id,
            clock=self._clock,
        )
        return await self._articles.save(article)
