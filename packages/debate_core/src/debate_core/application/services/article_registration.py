"""Registering a discovered source as an article — the worked example of the injection pattern.

This is the smallest service that is still a real use case, and it exists to show, in code, what
`docs/architecture/ports-and-adapters.md` describes:

* every dependency arrives in `__init__`, typed as a Protocol from
  :mod:`debate_core.application.ports`;
* time and ids come from the :class:`~debate_core.application.ports.providers.Clock` and
  :class:`~debate_core.application.ports.providers.IdGenerator` ports, so a test can assert on an
  exact record;
* nothing is imported from an adapter, a settings module or a global registry, so the service can
  be constructed against SQLite, DynamoDB or the in-memory fakes without knowing which it got.

The real ArticleService — fetching, extraction, snapshotting, access classification — is
v1-e04-t05-article-service. This one only decides whether a source is already known and records it
if it is not.
"""

from __future__ import annotations

from debate_core.application.ports import ArticleRepository, Clock, IdGenerator
from debate_core.domain import Article, SourceType

__all__ = ["ArticleRegistrationService"]


class ArticleRegistrationService:
    """Records a discovered source as an :class:`~debate_core.domain.Article`, once.

    Registration is deliberately idempotent by canonical URL: search, a pasted link and a caselist
    import can all arrive at the same source, and each of them producing another article record
    would fragment the cards cut from it.
    """

    def __init__(
        self,
        *,
        articles: ArticleRepository,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._articles = articles
        self._clock = clock
        self._id_generator = id_generator

    async def register(
        self,
        *,
        canonical_url: str,
        title: str,
        owner_id: str | None = None,
        organization_id: str | None = None,
        source_type: SourceType = SourceType.OTHER,
    ) -> Article:
        """Return the article already stored for `canonical_url`, or create and store it.

        `canonical_url` is expected to be canonical already: canonicalization is its own step
        (v1-e04-t01-url-canonicalization) and doing it here would hide a URL-rewriting rule inside
        a use case.
        """
        existing = await self._articles.find_by_canonical_url(canonical_url)
        if existing is not None:
            return existing
        now = self._clock.now()
        article = Article(
            article_id=self._id_generator.new_id(),
            owner_id=owner_id,
            organization_id=organization_id,
            canonical_url=canonical_url,
            title=title,
            source_type=source_type,
            created_at=now,
            updated_at=now,
        )
        return await self._articles.save(article)
