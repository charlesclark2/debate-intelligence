"""ArticleService: from a URL to a stored, hashed snapshot, or to the reason there is none (v1-e04-t05).

The service composes what E04's earlier tasks built, through ports and pure procedures only. It
imports no HTTP client, no extraction library and no filesystem code: the fetcher, the extractor and
storage arrive in its constructor (architecture proposal §6), and the composition root chooses them
(v1-e04-t06).

## retrieve(url)

1. **Canonicalize** the URL (:func:`~debate_core.retrieval.canonicalize_url`, v1-e04-t01). The
   canonical form is the article's identity key, never a fetch target.
2. **Re-fetch policy.** An article already stored under that key whose last retrieval was readable,
   less than `articles.refetch_after_hours` ago, and which has a publisher snapshot, is answered from
   that snapshot with no fetch at all. `refresh=True` (the CLI's `--refresh`) skips this step.
3. **Fetch** the URL as given, or the destination a link wrapper literally carries
   (:func:`~debate_core.retrieval.fetch_target_url`), through the
   :class:`~debate_core.application.ports.providers.ArticleFetcher` port (v1-e04-t02). Never a host
   the canonicalizer guessed, such as an AMP page's `www.` host (PM amendment 2026-10-19).
4. **Extract**, for a 2xx response, through the
   :class:`~debate_core.application.ports.providers.ContentExtractor` port (v1-e04-t04). A refusal
   is caught as the :class:`~debate_core.retrieval.extraction.ExtractionError` it is.
5. **Classify** with :class:`~debate_core.retrieval.access.AccessClassifier` (v1-e04-t03), from the
   fetch result and what extraction made of it, under thresholds built from settings.
6. **Anything but ACCESSIBLE ends here**, UNSUPPORTED_TYPE included: the article records the status,
   and the outcome carries the status, the classifier's reason and its rules version. No snapshot is
   made, no blob is written, and no text is kept. A metered page is PAYWALLED even when the whole
   text was served.
7. **Apply the page's rel=canonical** (:func:`~debate_core.retrieval.apply_rel_canonical`) to the URL
   that answered. A same-site canonical becomes the identity key; a cross-site one, or the site's
   root page named by a deeper page, is refused and the fetched URL's canonical form stands.
8. **Snapshot.** When the article's newest publisher snapshot has the same normalized-text hash
   under the current normalizer, it is reused: unchanged content makes no new snapshot, whatever
   bytes around it changed. Otherwise :class:`~debate_core.application.snapshot_service.SnapshotService`
   (v1-e03-t02) hashes and stores a new one, `provenance_mode` PUBLISHER_RETRIEVED.
9. **Upsert the article** under the identity key, with `access_status` ACCESSIBLE and the
   identifiers its URLs state.

**Both URLs are kept.** The article's `canonical_url` is the identity key; the snapshot's
`canonical_url` is, as its field says, the URL actually retrieved, after redirects. The outcome
carries the URL as given, the URL fetched and the URL that answered as well.

**Last readable retrieval** is the article's `updated_at` while its `access_status` is ACCESSIBLE:
this service sets both on every readable retrieval, including one that reused a snapshot, so a
source re-fetched once after the age limit is not fetched again on every later call.

## ingest_user_text(source_url, text, attested=True)

The lawful path for a metered or paywalled article the coach can read, for example through a
subscription (architecture proposal §19). The caller must name the source URL and attest that they
have the right to the text; without the attestation nothing is stored. The text is snapshotted with
`provenance_mode` USER_SUPPLIED and the `access_status` the caller reports, so every card cut from it
shows where it came from. Nothing is fetched. The text passes the same bar as a fetched page: at
least `articles.access_minimum_characters` characters and at most `http.max_response_bytes` bytes of
UTF-8. Identical text supplied again for the same article reuses its snapshot.

## Logging

Every outcome, of either method, emits one `INFO` event from this module's logger, `article
retrieval` or `user text ingested`, whose `extra` fields are the correlation id, the canonical URL,
the access status, the elapsed time by the injected clock, whether a fetch was made, the snapshot id
and whether it was reused, the provenance mode, and the classifier's reason and rules version. A
reason holds status codes, counts, marker ids and the platform's own messages (v1-e04-t03), never a
word of the page. No event carries page text, extracted text or user-supplied text.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Final

from debate_core.application.errors import DomainError
from debate_core.application.ports.persistence import ArticleRepository
from debate_core.application.ports.providers import ArticleFetcher, Clock, ContentExtractor, IdGenerator
from debate_core.application.settings import ArticleSettings
from debate_core.application.snapshot_service import SnapshotService
from debate_core.domain import AccessStatus, Article, ArticleIdentifiers, ProvenanceMode, SourceSnapshot
from debate_core.evidence.hashing import sha256_text
from debate_core.evidence.normalization import NORMALIZER_VERSION, normalize
from debate_core.retrieval import (
    InvalidUrlError,
    RelCanonicalDecision,
    apply_rel_canonical,
    canonicalize_url,
    detect_identifiers,
    fetch_target_url,
)
from debate_core.retrieval.access import AccessClassifier, AccessDecision, AccessThresholds
from debate_core.retrieval.extraction import ExtractedContent, ExtractionError
from debate_core.retrieval.fetch_types import FetchResult

__all__ = [
    "USER_TEXT_CONTENT_TYPE",
    "USER_TEXT_EXTRACTOR_VERSION",
    "ArticleService",
    "InvalidSourceUrl",
    "RetrievalOutcome",
    "UserTextNotAttested",
    "UserTextRejected",
    "access_thresholds",
]

logger = logging.getLogger(__name__)

USER_TEXT_EXTRACTOR_VERSION: Final = "user-supplied-text-1"
"""Recorded as a user-supplied snapshot's `extractor_version`: no extractor ran, the text is as given."""

USER_TEXT_CONTENT_TYPE: Final = "text/plain; charset=utf-8"
"""A user-supplied snapshot's raw blob is the text as given, in UTF-8."""


class InvalidSourceUrl(DomainError):
    """The URL is not an absolute http(s) URL with a usable host, so it names no source."""

    def __init__(self, url: str, reason: str) -> None:
        self.url = url
        self.reason = reason
        super().__init__(f"not a source URL: {reason}")


class UserTextNotAttested(DomainError):
    """User-supplied text arrived without the caller attesting lawful access to it; nothing was stored."""

    def __init__(self) -> None:
        super().__init__(
            "user-supplied text is stored only when the caller attests they have the right to it"
        )


class UserTextRejected(DomainError):
    """User-supplied text failed a quality gate (blank, too short or too large); nothing was stored."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"user-supplied text was not stored: {reason}")


def access_thresholds(settings: ArticleSettings) -> AccessThresholds:
    """The access classifier's truncation heuristic, from settings."""
    return AccessThresholds(
        minimum_characters=settings.access_minimum_characters,
        truncation_ratio=settings.access_truncation_ratio,
    )


@dataclass(frozen=True, slots=True)
class RetrievalOutcome:
    """What one call to the service produced: the article, its snapshot or the reason there is none.

    `snapshot` is a publisher snapshot only when `access_status` is ACCESSIBLE, which construction
    checks: there is no partly readable outcome. `decision` is the classifier's, and None when
    nothing was fetched (a fresh stored snapshot answered, or the text was user-supplied).
    """

    correlation_id: str
    article: Article
    snapshot: SourceSnapshot | None
    access_status: AccessStatus
    reason: str
    """One sentence for a person: the classifier's reason, or why no fetch was needed."""
    rules_version: str | None
    """The paywall marker rules the classifier used; None when nothing was classified."""
    decision: AccessDecision | None
    fetched: bool
    """Whether the fetcher was called."""
    snapshot_reused: bool
    """Whether `snapshot` was already stored before this call."""
    requested_url: str
    """The URL as the caller gave it."""
    canonical_url: str
    """The identity key the article is stored under."""
    fetch_url: str | None
    """The URL the fetcher was asked for: the one given, or a wrapper's literal destination."""
    final_url: str | None
    """The URL that answered, after redirects."""
    rel_canonical: RelCanonicalDecision | None
    """What was made of the page's rel=canonical, for a readable page."""
    elapsed_ms: float

    def __post_init__(self) -> None:
        if (
            self.snapshot is not None
            and self.snapshot.provenance_mode is ProvenanceMode.PUBLISHER_RETRIEVED
            and self.access_status is not AccessStatus.ACCESSIBLE
        ):
            raise ValueError(f"a {self.access_status.value} outcome cannot carry a publisher snapshot")


class ArticleService:
    """Retrieves sources into snapshots, and stores text a user lawfully supplies, by the module's rules."""

    def __init__(
        self,
        *,
        articles: ArticleRepository,
        snapshots: SnapshotService,
        fetcher: ArticleFetcher,
        extractor: ContentExtractor,
        clock: Clock,
        id_generator: IdGenerator,
        settings: ArticleSettings,
        max_user_text_bytes: int,
    ) -> None:
        """`max_user_text_bytes` is `http.max_response_bytes`: no more text than a fetch would accept."""
        self._articles = articles
        self._snapshots = snapshots
        self._fetcher = fetcher
        self._extractor = extractor
        self._clock = clock
        self._id_generator = id_generator
        self._settings = settings
        self._max_user_text_bytes = max_user_text_bytes
        self._classifier = AccessClassifier(thresholds=access_thresholds(settings))

    # ----------------------------------------------------------------------------------------
    # retrieve
    # ----------------------------------------------------------------------------------------

    async def retrieve(
        self, url: str, *, refresh: bool = False, correlation_id: str | None = None
    ) -> RetrievalOutcome:
        """Retrieve `url` into an article and a snapshot, or into an explicit non-ACCESSIBLE status.

        Raises :class:`InvalidSourceUrl` for a URL with no canonical form. A refused or failed fetch
        is an outcome, not an exception.
        """
        started = self._clock.now()
        correlation = correlation_id if correlation_id is not None else self._id_generator.new_id()
        key = _canonical(url)
        known = await self._articles.find_by_canonical_url(key)

        if known is not None and not refresh:
            fresh = await self._fresh_snapshot(known, started)
            if fresh is not None:
                age_hours = (started - known.updated_at).total_seconds() / 3600
                return self._finish(
                    started,
                    RetrievalOutcome(
                        correlation_id=correlation,
                        article=known,
                        snapshot=fresh,
                        access_status=AccessStatus.ACCESSIBLE,
                        reason=(
                            f"Last read {age_hours:.1f} hours ago, within the "
                            f"{self._settings.refetch_after_hours:g}-hour re-fetch age; the stored "
                            "snapshot is the answer"
                        ),
                        rules_version=None,
                        decision=None,
                        fetched=False,
                        snapshot_reused=True,
                        requested_url=url,
                        canonical_url=key,
                        fetch_url=None,
                        final_url=None,
                        rel_canonical=None,
                        elapsed_ms=0.0,
                    ),
                )

        target = _fetch_target(url)
        fetched = await self._fetcher.fetch(target)
        extraction = self._extract(fetched)
        decision = self._classifier.classify(fetched, extraction)
        content = extraction if isinstance(extraction, ExtractedContent) else None

        if decision.status is not AccessStatus.ACCESSIBLE or content is None:
            article = await self._record_status(
                known, key, decision.status, content, urls=(url, target, fetched.final_url)
            )
            return self._finish(
                started,
                RetrievalOutcome(
                    correlation_id=correlation,
                    article=article,
                    snapshot=None,
                    access_status=decision.status,
                    reason=decision.reason,
                    rules_version=decision.rules_version,
                    decision=decision,
                    fetched=True,
                    snapshot_reused=False,
                    requested_url=url,
                    canonical_url=key,
                    fetch_url=target,
                    final_url=fetched.final_url,
                    rel_canonical=None,
                    elapsed_ms=0.0,
                ),
            )

        rel_canonical = _rel_canonical(fetched.final_url, content.metadata_hints.canonical_url)
        identity = rel_canonical.canonical_url if rel_canonical is not None else key
        stored = known if identity == key else await self._articles.find_by_canonical_url(identity)
        article_id = stored.article_id if stored is not None else self._id_generator.new_id()
        snapshot, reused = await self._publisher_snapshot(article_id, fetched, content, identity)
        article = await self._save_readable(
            stored, article_id, identity, content, urls=(url, target, fetched.final_url, identity)
        )
        if not reused:
            snapshot = await self._articles.save_snapshot(snapshot)
        return self._finish(
            started,
            RetrievalOutcome(
                correlation_id=correlation,
                article=article,
                snapshot=snapshot,
                access_status=AccessStatus.ACCESSIBLE,
                reason=decision.reason,
                rules_version=decision.rules_version,
                decision=decision,
                fetched=True,
                snapshot_reused=reused,
                requested_url=url,
                canonical_url=identity,
                fetch_url=target,
                final_url=fetched.final_url,
                rel_canonical=rel_canonical,
                elapsed_ms=0.0,
            ),
        )

    def _extract(self, fetched: FetchResult) -> ExtractedContent | ExtractionError | None:
        """What the extractor made of a 2xx document, or its refusal; None for any other response."""
        if fetched.error is not None or fetched.status_code is None or not 200 <= fetched.status_code < 300:
            return None
        try:
            return self._extractor.extract(fetched)
        except ExtractionError as refusal:
            return refusal

    async def _fresh_snapshot(self, article: Article, now: datetime) -> SourceSnapshot | None:
        """The newest publisher snapshot, when the last readable retrieval is within the re-fetch age."""
        if article.access_status is not AccessStatus.ACCESSIBLE:
            return None
        if now - article.updated_at >= self._settings.refetch_after:
            return None
        return await self._newest(article.article_id, ProvenanceMode.PUBLISHER_RETRIEVED)

    async def _newest(self, article_id: str, provenance: ProvenanceMode) -> SourceSnapshot | None:
        snapshots = await self._articles.list_snapshots(article_id)
        return next((snapshot for snapshot in snapshots if snapshot.provenance_mode is provenance), None)

    async def _publisher_snapshot(
        self, article_id: str, fetched: FetchResult, content: ExtractedContent, identity: str
    ) -> tuple[SourceSnapshot, bool]:
        """The newest publisher snapshot when its text is unchanged, else a new one (not yet saved)."""
        newest = await self._newest(article_id, ProvenanceMode.PUBLISHER_RETRIEVED)
        if newest is not None and _same_text(newest, content.text):
            return newest, True
        created = await self._snapshots.create(
            article_id=article_id,
            raw_bytes=fetched.body,
            extracted_text=content.text,
            canonical_url=identity,
            retrieved_at=fetched.fetched_at,
            extractor_version=f"{content.extractor_name}/{content.extractor_version}",
            provenance_mode=ProvenanceMode.PUBLISHER_RETRIEVED,
            access_status=AccessStatus.ACCESSIBLE,
            content_type=fetched.content_type,
        )
        return created, False

    async def _record_status(
        self,
        known: Article | None,
        key: str,
        status: AccessStatus,
        content: ExtractedContent | None,
        *,
        urls: tuple[str, ...],
    ) -> Article:
        """Record a non-ACCESSIBLE answer on the article: the latest retrieval outcome, and nothing else."""
        now = self._clock.now()
        found = _identifiers(urls)
        if known is not None:
            return await self._articles.save(
                known.evolve(
                    access_status=status,
                    identifiers=_merged(known.identifiers, found),
                    updated_at=now,
                )
            )
        title = _hinted_title(content) or key
        return await self._articles.save(
            Article(
                article_id=self._id_generator.new_id(),
                canonical_url=key,
                title=title,
                access_status=status,
                identifiers=found,
                created_at=now,
                updated_at=now,
            )
        )

    async def _save_readable(
        self,
        stored: Article | None,
        article_id: str,
        identity: str,
        content: ExtractedContent,
        *,
        urls: tuple[str, ...],
    ) -> Article:
        now = self._clock.now()
        found = _identifiers(urls)
        hinted = _hinted_title(content)
        if stored is not None:
            # A title that was only the URL, from a failed retrieval, gives way to the page's own.
            title = hinted if hinted and stored.title == stored.canonical_url else stored.title
            return await self._articles.save(
                stored.evolve(
                    title=title,
                    access_status=AccessStatus.ACCESSIBLE,
                    identifiers=_merged(stored.identifiers, found),
                    updated_at=now,
                )
            )
        return await self._articles.save(
            Article(
                article_id=article_id,
                canonical_url=identity,
                title=hinted or identity,
                access_status=AccessStatus.ACCESSIBLE,
                identifiers=found,
                created_at=now,
                updated_at=now,
            )
        )

    # ----------------------------------------------------------------------------------------
    # ingest_user_text
    # ----------------------------------------------------------------------------------------

    async def ingest_user_text(
        self,
        *,
        source_url: str,
        text: str,
        attested: bool,
        reported_access_status: AccessStatus = AccessStatus.UNKNOWN,
        title: str | None = None,
        owner_id: str | None = None,
        correlation_id: str | None = None,
    ) -> RetrievalOutcome:
        """Snapshot text the caller lawfully has, as USER_SUPPLIED, under the article for `source_url`.

        `attested` must be True: the caller states they have the right to this text (a subscription,
        a library copy). `reported_access_status` is recorded on the snapshot as the caller reports
        it, and on the article only when this call creates it; a status the platform measured is not
        overwritten by a report. Raises :class:`UserTextNotAttested`, :class:`InvalidSourceUrl` or
        :class:`UserTextRejected`, and then stores nothing.
        """
        started = self._clock.now()
        if attested is not True:
            raise UserTextNotAttested()
        key = _canonical(source_url)
        self._check_user_text(text)
        correlation = correlation_id if correlation_id is not None else self._id_generator.new_id()

        known = await self._articles.find_by_canonical_url(key)
        if known is None:
            now = self._clock.now()
            known = await self._articles.save(
                Article(
                    article_id=self._id_generator.new_id(),
                    owner_id=owner_id,
                    canonical_url=key,
                    title=(title or "").strip() or key,
                    access_status=reported_access_status,
                    identifiers=_identifiers((source_url, key)),
                    created_at=now,
                    updated_at=now,
                )
            )
        newest = await self._newest(known.article_id, ProvenanceMode.USER_SUPPLIED)
        reused = newest is not None and _same_text(newest, text)
        if newest is not None and reused:
            snapshot = newest
        else:
            snapshot = await self._articles.save_snapshot(
                await self._snapshots.create(
                    article_id=known.article_id,
                    raw_bytes=text.encode("utf-8"),
                    extracted_text=text,
                    canonical_url=key,
                    retrieved_at=started,
                    extractor_version=USER_TEXT_EXTRACTOR_VERSION,
                    provenance_mode=ProvenanceMode.USER_SUPPLIED,
                    access_status=reported_access_status,
                    content_type=USER_TEXT_CONTENT_TYPE,
                    owner_id=owner_id,
                )
            )
        return self._finish(
            started,
            RetrievalOutcome(
                correlation_id=correlation,
                article=known,
                snapshot=snapshot,
                access_status=snapshot.access_status,
                reason="Text supplied by a user who attests the right to it; access status as reported",
                rules_version=None,
                decision=None,
                fetched=False,
                snapshot_reused=reused,
                requested_url=source_url,
                canonical_url=key,
                fetch_url=None,
                final_url=None,
                rel_canonical=None,
                elapsed_ms=0.0,
            ),
            message="user text ingested",
        )

    def _check_user_text(self, text: str) -> None:
        minimum = self._settings.access_minimum_characters
        if not text.strip():
            raise UserTextRejected("the text is blank")
        if len(text.strip()) < minimum:
            raise UserTextRejected(f"the text is under the {minimum}-character minimum for an article")
        size = len(text.encode("utf-8"))
        if size > self._max_user_text_bytes:
            raise UserTextRejected(
                f"the text is {size} bytes, over the {self._max_user_text_bytes}-byte limit"
            )

    # ----------------------------------------------------------------------------------------
    # The log event
    # ----------------------------------------------------------------------------------------

    def _finish(
        self, started: datetime, outcome: RetrievalOutcome, *, message: str = "article retrieval"
    ) -> RetrievalOutcome:
        elapsed_ms = (self._clock.now() - started).total_seconds() * 1000
        finished = replace(outcome, elapsed_ms=elapsed_ms)
        snapshot = finished.snapshot
        logger.info(
            message,
            extra={
                "correlation_id": finished.correlation_id,
                "canonical_url": finished.canonical_url,
                "access_status": finished.access_status.value,
                "elapsed_ms": elapsed_ms,
                "fetched": finished.fetched,
                "snapshot_id": snapshot.snapshot_id if snapshot is not None else None,
                "snapshot_reused": finished.snapshot_reused,
                "provenance_mode": snapshot.provenance_mode.value if snapshot is not None else None,
                "reason": finished.reason,
                "rules_version": finished.rules_version,
            },
        )
        return finished


# --------------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------------


def _canonical(url: str) -> str:
    try:
        return canonicalize_url(url)
    except InvalidUrlError as error:
        raise InvalidSourceUrl(url, str(error)) from error


def _fetch_target(url: str) -> str:
    try:
        return fetch_target_url(url)
    except InvalidUrlError as error:
        raise InvalidSourceUrl(url, str(error)) from error


def _rel_canonical(final_url: str, declared: str | None) -> RelCanonicalDecision | None:
    """The rel=canonical decision for the URL that answered; None when that URL has no canonical form."""
    try:
        return apply_rel_canonical(final_url, declared)
    except InvalidUrlError:
        return None


def _same_text(snapshot: SourceSnapshot, text: str) -> bool:
    """Whether `text` normalizes, under the snapshot's own normalizer version, to the text it holds."""
    if snapshot.normalizer_version != NORMALIZER_VERSION:
        return False
    return sha256_text(normalize(text, NORMALIZER_VERSION).text) == snapshot.normalized_text_hash


def _identifiers(urls: tuple[str, ...]) -> ArticleIdentifiers:
    """The DOI, arXiv id and PMID the URLs state; never the page's text, whose references name others."""
    return detect_identifiers(" ".join(urls)).as_article_identifiers()


def _merged(known: ArticleIdentifiers, found: ArticleIdentifiers) -> ArticleIdentifiers:
    """`known`, with any identifier it lacks taken from `found`; a known identifier is never replaced."""
    additions = {name: value for name, value in found if value is not None and getattr(known, name) is None}
    return known.evolve(**additions) if additions else known


def _hinted_title(content: ExtractedContent | None) -> str | None:
    if content is None or content.metadata_hints.title is None:
        return None
    return content.metadata_hints.title.strip() or None
