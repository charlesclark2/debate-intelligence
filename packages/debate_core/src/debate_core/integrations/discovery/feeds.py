"""Publisher RSS and Atom feeds as a discovery provider (v1-e07-t05).

:class:`FeedProvider` reads the coach's feed lists (`config/feeds/<topic>.yaml`,
:mod:`~debate_core.integrations.discovery.feed_config`), keeps the entries that match the query and
fall in its date window, and returns them as news
:class:`~debate_core.domain.discovery.CandidateResult` values. It is discovery only: a candidate
carries the entry's title, the publisher, the date, a snippet of the feed's summary and the
publisher's URL, and the article itself is fetched later by ArticleService from that URL, subject to
robots and paywall rules. Nothing here scrapes a page, and a feed's full content (`content:encoded`)
is never read (:mod:`~debate_core.integrations.discovery.feed_parsing`). Like every adapter here it
is wrapped in :class:`~debate_core.integrations.discovery.resilience.ResilientProvider` by the
registry, and it ranks and deduplicates nothing (E08).

**Fetching** (:class:`FeedFetcher`, which the Google News provider shares). Each feed is one `GET`,
never retried here, with redirects followed up to `http.max_redirects` and a body capped at
:data:`MAX_FEED_BYTES`. A feed fetched before is fetched conditionally: its last `ETag` and
`Last-Modified` go out as `If-None-Match` and `If-Modified-Since`, and a `304 Not Modified` answer
returns the entries kept from last time without parsing anything
(:mod:`~debate_core.integrations.discovery.feed_cache`). Refusals map through
:func:`~debate_core.integrations.discovery.http_failures.provider_error_for_status`, so a `429` is
:class:`~debate_core.application.errors.ProviderRateLimited` with its `Retry-After`.

**Several feeds, one answer.** The feeds are fetched concurrently, at most
:data:`CONCURRENT_FETCHES` at a time. When some fail and others answer, the response is partial and
its error names the publishers that failed; when every feed fails, the first one's error is raised,
as a single-request adapter's would be.

**Which entries are kept** (:func:`query_terms`, :func:`matches_terms`, :func:`in_window`):

* every term of the query appears in the entry's title or snippet, ignoring case, as a whole word
  or phrase (`"health insurance"` in quotes is one phrase; unquoted, two words that may appear
  apart). `insurance` does not match `reinsurance`, and there is no stemming;
* when the query has a `since` or `until`, the entry's date is inside it, both ends included. An
  entry with no date this module can place in time cannot be shown to be inside a window, so it is
  dropped when there is one and kept when there is none;
* an entry whose link appeared earlier in the same answer is the same entry listed twice, and is
  dropped. That is the only duplicate this adapter removes: one story at two URLs is E08's to merge.

The kept entries are returned newest first (undated last, otherwise in feed order), which is the
order a feed lists them in, and cut to `max_results`. That is the provider's order, not a ranking.
"""

from __future__ import annotations

import asyncio
import re
import time
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from http.cookiejar import CookieJar, DefaultCookiePolicy
from typing import Final

import httpx
from pydantic import ValidationError

from debate_core.application.errors import ProviderError, ProviderUnavailable
from debate_core.application.ports.providers import Clock
from debate_core.application.settings import HttpSettings, ProviderSettings, SearchProviderName
from debate_core.domain.discovery import CandidateResult, ProviderQuery, ProviderResponse
from debate_core.domain.enums import SourceType
from debate_core.domain.search import SearchFilters
from debate_core.integrations.discovery.feed_cache import CachedFeed, FeedCache
from debate_core.integrations.discovery.feed_config import FeedConfig, FeedSource, feeds_of
from debate_core.integrations.discovery.feed_parsing import FeedEntry, FeedUnreadable, parse_feed
from debate_core.integrations.discovery.http_failures import provider_error_for_status
from debate_core.integrations.discovery.redaction import logger

__all__ = [
    "CONCURRENT_FETCHES",
    "FEED_ACCEPT",
    "MAX_FEED_BYTES",
    "PROVIDER_NAME",
    "FeedFetcher",
    "FeedProvider",
    "FetchedFeed",
    "feed_client",
    "feed_factory",
    "in_window",
    "matches_terms",
    "newest_first",
    "query_terms",
]

PROVIDER_NAME: Final = SearchProviderName.RSS.value
"""The name settings enable this provider by, and every result carries."""

MAX_FEED_BYTES: Final = 5 * 1024 * 1024
"""The largest feed body read; a larger one is abandoned as unreadable, never truncated and parsed."""

CONCURRENT_FETCHES: Final = 4
"""How many feeds are fetched at once."""

FEED_ACCEPT: Final = (
    "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.1"
)
"""The `Accept` header every feed request sends."""

_QUOTED: Final = re.compile(r'"([^"]*)"')


# --------------------------------------------------------------------------------------------
# Which entries are kept
# --------------------------------------------------------------------------------------------


def _fold(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def query_terms(query: str) -> tuple[str, ...]:
    """The terms every kept entry must contain: each quoted phrase, then each other word, folded."""
    phrases = [_fold(phrase) for phrase in _QUOTED.findall(query)]
    words = _fold(_QUOTED.sub(" ", query)).split()
    return tuple(term for term in (*phrases, *words) if term)


def matches_terms(entry: FeedEntry, terms: Sequence[str]) -> bool:
    """Whether every term appears in the entry's title or snippet as a whole word or phrase."""
    haystack = _fold(f"{entry.title} {entry.snippet or ''}")
    return all(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", haystack) for term in terms)


def in_window(published_at: datetime | None, filters: SearchFilters) -> bool:
    """Whether a date is inside the query's window; an undated entry is inside only when there is none."""
    if filters.since is None and filters.until is None:
        return True
    if published_at is None:
        return False
    if filters.since is not None and published_at < filters.since:
        return False
    return not (filters.until is not None and published_at > filters.until)


def newest_first[T](items: Sequence[T], published: Callable[[T], datetime | None]) -> list[T]:
    """`items` newest first, undated last; ties keep their order."""
    return sorted(items, key=lambda item: _age_key(published(item)))


def _age_key(published_at: datetime | None) -> tuple[bool, float]:
    return (published_at is None, -published_at.timestamp() if published_at is not None else 0.0)


# --------------------------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FetchedFeed:
    """One feed's entries, and whether they came from the cache on a `304`."""

    entries: tuple[FeedEntry, ...]
    unchanged: bool


class FeedFetcher:
    """Fetches one feed, conditionally when it has been fetched before, and parses it safely."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        cache: FeedCache,
        clock: Clock,
        provider: str,
        max_bytes: int = MAX_FEED_BYTES,
    ) -> None:
        self._client = client
        self._cache = cache
        self._clock = clock
        self._provider = provider
        self._max_bytes = max_bytes

    async def fetch(self, url: str) -> FetchedFeed:
        """The feed's entries; raises a :class:`ProviderError` for every way it can fail."""
        cached = self._cache.get(url)
        headers = cached.conditional_headers if cached is not None else {}
        try:
            async with self._client.stream("GET", url, headers=headers) as response:
                if response.status_code == 304:
                    if cached is None:
                        raise ProviderUnavailable(self._provider, "HTTP 304 for a feed with nothing cached")
                    return FetchedFeed(cached.entries, unchanged=True)
                failure = provider_error_for_status(
                    self._provider, response.status_code, response.headers, now=self._clock.now()
                )
                if failure is not None:
                    raise failure
                if response.status_code != 200:
                    raise ProviderUnavailable(self._provider, f"HTTP {response.status_code}: not a feed")
                body = await self._read(response)
                etag = response.headers.get("etag")
                last_modified = response.headers.get("last-modified")
        except httpx.TimeoutException as error:
            raise ProviderUnavailable(self._provider, "timed out") from error
        except httpx.HTTPError as error:
            raise ProviderUnavailable(self._provider, f"transport failure: {type(error).__name__}") from error
        try:
            parsed = parse_feed(body)
        except FeedUnreadable as error:
            raise ProviderUnavailable(self._provider, f"unreadable feed: {error}") from error
        self._keep(CachedFeed(url=url, etag=etag, last_modified=last_modified, entries=parsed.entries))
        return FetchedFeed(parsed.entries, unchanged=False)

    async def _read(self, response: httpx.Response) -> bytes:
        declared = response.headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > self._max_bytes:
            raise ProviderUnavailable(self._provider, f"unreadable feed: larger than {self._max_bytes} bytes")
        body = bytearray()
        async for chunk in response.aiter_bytes():
            body.extend(chunk)
            if len(body) > self._max_bytes:
                raise ProviderUnavailable(
                    self._provider, f"unreadable feed: larger than {self._max_bytes} bytes"
                )
        return bytes(body)

    def _keep(self, feed: CachedFeed) -> None:
        """Cache the answer; a cache that cannot be written costs the next fetch its `304`, nothing more."""
        try:
            self._cache.put(feed)
        except OSError as error:
            logger.warning("%s: feed cache not written (%s)", self._provider, type(error).__name__)


# --------------------------------------------------------------------------------------------
# The adapter
# --------------------------------------------------------------------------------------------


def candidate_from_entry(
    entry: FeedEntry, *, provider: str, publication: str | None
) -> CandidateResult | None:
    """One kept entry as a news candidate; `None` if it does not make a valid one."""
    try:
        return CandidateResult(
            provider=provider,
            provider_record_id=entry.entry_id,
            title=entry.title,
            url=entry.link,
            source_type=SourceType.NEWS,
            authors=entry.authors,
            publication=publication,
            published_at=entry.published_at,
            snippet=entry.snippet,
        )
    except ValidationError:
        return None


class FeedProvider:
    """Searches the configured publisher feeds; a discovery `SearchProvider`.

    Owns `client`; close it with :meth:`aclose`.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        topics: Sequence[FeedConfig],
        cache: FeedCache,
        clock: Clock,
        max_bytes: int = MAX_FEED_BYTES,
    ) -> None:
        self._client = client
        self._feeds = feeds_of(topics)
        self._fetcher = FeedFetcher(
            client, cache=cache, clock=clock, provider=PROVIDER_NAME, max_bytes=max_bytes
        )

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    @property
    def feeds(self) -> tuple[FeedSource, ...]:
        """The feeds every search reads, each once."""
        return self._feeds

    def __repr__(self) -> str:
        return f"{type(self).__name__}(feeds={len(self._feeds)})"

    async def aclose(self) -> None:
        """Close the HTTP client and its connections."""
        await self._client.aclose()

    async def search(self, query: ProviderQuery) -> ProviderResponse:
        started = time.perf_counter()
        outcomes = await self._fetch_all()
        failures = [(feed, outcome) for feed, outcome in outcomes if isinstance(outcome, ProviderError)]
        if self._feeds and len(failures) == len(self._feeds):
            raise failures[0][1]
        terms = query_terms(query.query)
        kept: list[CandidateResult] = []
        seen_links: set[str] = set()
        for feed, outcome in outcomes:
            if isinstance(outcome, ProviderError):
                continue
            for entry in outcome.entries:
                if entry.link in seen_links:
                    continue
                seen_links.add(entry.link)
                if not (matches_terms(entry, terms) and in_window(entry.published_at, query.filters)):
                    continue
                candidate = candidate_from_entry(entry, provider=self.name, publication=feed.publisher)
                if candidate is not None:
                    kept.append(candidate)
        results = tuple(newest_first(kept, lambda candidate: candidate.published_at))[
            : query.filters.max_results
        ]
        unchanged = sum(
            1 for _, outcome in outcomes if isinstance(outcome, FetchedFeed) and outcome.unchanged
        )
        logger.info(
            "%s: %d feeds read, %d unchanged, %d failed",
            self.name,
            len(outcomes) - len(failures) - unchanged,
            unchanged,
            len(failures),
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        if failures:
            reasons = "; ".join(f"{feed.publisher}: {_reason(error)}" for feed, error in failures)
            return ProviderResponse(
                provider=self.name,
                results=results,
                elapsed_ms=elapsed_ms,
                partial=True,
                error=f"{len(failures)} of {len(self._feeds)} feeds failed: {reasons}",
            )
        return ProviderResponse(provider=self.name, results=results, elapsed_ms=elapsed_ms)

    async def _fetch_all(self) -> list[tuple[FeedSource, FetchedFeed | ProviderError]]:
        gate = asyncio.Semaphore(CONCURRENT_FETCHES)

        async def one(feed: FeedSource) -> tuple[FeedSource, FetchedFeed | ProviderError]:
            async with gate:
                try:
                    return feed, await self._fetcher.fetch(feed.url)
                except ProviderError as error:
                    return feed, error

        return list(await asyncio.gather(*(one(feed) for feed in self._feeds)))


def _reason(error: ProviderError) -> str:
    """The error's message without the provider name it starts with."""
    prefix = f"{error.provider}: "
    message = str(error)
    return message.removeprefix(prefix)


def feed_client(
    http: HttpSettings, *, version: str, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    """The client the feed providers use: the platform's User-Agent, no cookies, nothing from the environment.

    Redirects are followed, up to `http.max_redirects`, because publishers move their feeds and say
    so with a redirect. `transport` is for tests, which pass a mock.
    """
    return httpx.AsyncClient(
        headers={"User-Agent": http.user_agent(version), "Accept": FEED_ACCEPT},
        timeout=httpx.Timeout(http.request_timeout_seconds, connect=http.connect_timeout_seconds),
        follow_redirects=True,
        max_redirects=http.max_redirects,
        cookies=CookieJar(policy=DefaultCookiePolicy(allowed_domains=[])),
        trust_env=False,
        transport=transport,
    )


def feed_factory(
    http: HttpSettings,
    *,
    version: str,
    clock: Clock,
    topics: Sequence[FeedConfig],
    cache: FeedCache,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Callable[[ProviderSettings], FeedProvider]:
    """The registry's factory for `rss`: the provider over `topics`' feeds, caching in `cache`.

    The composition root reads the topics
    (:func:`~debate_core.integrations.discovery.feed_config.load_feed_directory`) and builds the
    cache on `<storage.data_dir>/feeds/`. The wrapper's `providers.timeout_seconds` bounds the
    whole search, every feed included.
    """

    def build(settings: ProviderSettings) -> FeedProvider:
        del settings
        return FeedProvider(
            feed_client(http, version=version, transport=transport),
            topics=topics,
            cache=cache,
            clock=clock,
            max_bytes=min(http.max_response_bytes, MAX_FEED_BYTES),
        )

    return build
