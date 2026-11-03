"""Google News RSS search as a discovery provider, resolved to publisher URLs offline (v1-e07-t05).

:class:`GoogleNewsRssProvider` asks Google News's RSS search for the query, in the edition each
enabled topic names (`google_news:` in `config/feeds/<topic>.yaml`, off unless a topic turns it on),
and returns news :class:`~debate_core.domain.discovery.CandidateResult` values that point at the
publisher's own article, never at Google. Like the publisher feed provider it is discovery only and
is wrapped in :class:`~debate_core.integrations.discovery.resilience.ResilientProvider`; it fetches
and parses through :class:`~debate_core.integrations.discovery.feeds.FeedFetcher`, so conditional
GET, the size cap and the safe parser are the same.

**The request** (:func:`search_url`) is one `GET https://news.google.com/rss/search` per edition:
`q` is the query with `after:` the day before `since` and `before:` the day after `until`, because
Google reads those operators by whole days in an unstated time zone; `hl`, `gl` and `ceid` are the
edition. The exact window is then applied here, as the feed provider applies it. The query terms
are not matched again: Google matched them against the article, and the feed carries only titles.

**Resolving an item to its publisher** (PM ruling 2026-10-22). An item's `<link>` is a
`news.google.com/rss/articles/<id>` URL, and nothing may be asked of Google beyond the search feed
itself: no `batchexecute` call, no request for the article's page.
:func:`publisher_url_from_google_link` therefore decodes the id offline. Until late 2024 the id was
base64url of a small protobuf message whose field 4 held the publisher URL, and such an id still
decodes. The current ids hold an opaque token instead, and an item with one is dropped. So is an
item whose decoded URL is Google's own. Each search logs how many it dropped. The `<source url>` an
item carries is the outlet's home page, never the article, and is never a candidate's URL: one
outlet's every story would share it, and E08 would merge them all. In practice most items today
are dropped, which is why the topics' templates leave Google News off.

**What a candidate keeps**: the title without the ` - Publisher` suffix Google appends, the
`<source>` name as the publication, the date, and Google's id for the item. The item's
`<description>` is only the headline and the outlet again, linked to Google, so there is no
snippet.
"""

from __future__ import annotations

import binascii
import time
from base64 import urlsafe_b64decode
from collections.abc import Callable, Sequence
from datetime import timedelta
from typing import Final
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from debate_core.application.errors import ProviderError
from debate_core.application.ports.providers import Clock
from debate_core.application.settings import HttpSettings, ProviderSettings, SearchProviderName
from debate_core.domain.discovery import CandidateResult, ProviderQuery, ProviderResponse
from debate_core.domain.enums import SourceType
from debate_core.integrations.discovery.feed_cache import FeedCache
from debate_core.integrations.discovery.feed_config import FeedConfig, GoogleNewsConfig
from debate_core.integrations.discovery.feed_parsing import FeedEntry
from debate_core.integrations.discovery.feeds import (
    MAX_FEED_BYTES,
    FeedFetcher,
    FetchedFeed,
    feed_client,
    in_window,
    newest_first,
)
from debate_core.integrations.discovery.redaction import logger

__all__ = [
    "GOOGLE_NEWS_SEARCH_URL",
    "PROVIDER_NAME",
    "GoogleNewsRssProvider",
    "candidate_from_item",
    "google_news_factory",
    "is_google_hosted",
    "publisher_url_from_google_link",
    "search_url",
]

PROVIDER_NAME: Final = SearchProviderName.GOOGLE_NEWS.value
"""The name settings enable this provider by, and every result carries."""

GOOGLE_NEWS_SEARCH_URL: Final = "https://news.google.com/rss/search"
"""Google News's RSS search endpoint."""

_URL_FIELD_WIRE_TYPE: Final = 2
"""Protobuf's length-delimited wire type, the one a string field such as the URL is sent in."""


# --------------------------------------------------------------------------------------------
# Resolving an item to its publisher
# --------------------------------------------------------------------------------------------


def is_google_hosted(url: str) -> bool:
    """Whether `url` is on google.com or one of its subdomains (news.google.com included)."""
    host = (urlsplit(url).hostname or "").lower()
    return host == "google.com" or host.endswith(".google.com")


def publisher_url_from_google_link(link: str) -> str | None:
    """The publisher's URL for a Google News item link, decoded offline; `None` when it cannot be.

    A link that is not Google-hosted is already the publisher's. A `news.google.com` article link is
    decoded from its id (see the module docstring); anything else Google-hosted, or an id that holds
    no http(s) URL, or one that holds a Google URL, is `None`.
    """
    if not is_google_hosted(link):
        return _http_url(link)
    segments = [segment for segment in urlsplit(link).path.split("/") if segment]
    if "articles" not in segments[:-1]:
        return None
    article_id = segments[segments.index("articles") + 1]
    try:
        payload = urlsafe_b64decode(article_id + "=" * (-len(article_id) % 4))
    except (binascii.Error, ValueError):
        return None
    for value in _length_delimited_fields(payload):
        if not value.startswith((b"http://", b"https://")):
            continue
        try:
            url = _http_url(value.decode("ascii"))
        except UnicodeDecodeError:
            continue
        if url is not None and not is_google_hosted(url):
            return url
    return None


def _length_delimited_fields(payload: bytes) -> list[bytes]:
    """The values of the top-level length-delimited fields of a protobuf message, until it stops parsing."""
    values: list[bytes] = []
    position = 0
    while position < len(payload):
        key, position = _varint(payload, position)
        if key is None:
            break
        wire_type = key & 0x07
        if wire_type == 0:
            value, position = _varint(payload, position)
            if value is None:
                break
        elif wire_type == _URL_FIELD_WIRE_TYPE:
            length, position = _varint(payload, position)
            if length is None or position + length > len(payload):
                break
            values.append(payload[position : position + length])
            position += length
        elif wire_type == 1:
            position += 8
        elif wire_type == 5:
            position += 4
        else:
            break
    return values


def _varint(payload: bytes, position: int) -> tuple[int | None, int]:
    value = 0
    for shift in range(0, 64, 7):
        if position >= len(payload):
            return None, position
        byte = payload[position]
        position += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, position
    return None, position


def _http_url(value: str) -> str | None:
    if not value or any(character.isspace() for character in value):
        return None
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return value


def candidate_from_item(entry: FeedEntry) -> CandidateResult | None:
    """One Google News item as a news candidate at its publisher's URL; `None` when that cannot be found."""
    url = publisher_url_from_google_link(entry.link)
    if url is None:
        return None
    title = entry.title
    suffix = f" - {entry.source_name}" if entry.source_name else None
    if suffix is not None and title.endswith(suffix) and len(title) > len(suffix):
        title = title.removesuffix(suffix)
    try:
        return CandidateResult(
            provider=PROVIDER_NAME,
            provider_record_id=entry.entry_id,
            title=title,
            url=url,
            source_type=SourceType.NEWS,
            publication=entry.source_name,
            published_at=entry.published_at,
        )
    except ValidationError:
        return None


# --------------------------------------------------------------------------------------------
# The request and the adapter
# --------------------------------------------------------------------------------------------


def search_url(query: ProviderQuery, edition: GoogleNewsConfig) -> str:
    """The RSS search URL for `query` in `edition`; see the module docstring for the date operators."""
    terms = [query.query]
    if query.filters.since is not None:
        terms.append(f"after:{(query.filters.since.date() - timedelta(days=1)).isoformat()}")
    if query.filters.until is not None:
        terms.append(f"before:{(query.filters.until.date() + timedelta(days=1)).isoformat()}")
    parameters = {
        "q": " ".join(terms),
        "hl": edition.language,
        "gl": edition.country,
        "ceid": edition.edition,
    }
    return str(httpx.URL(GOOGLE_NEWS_SEARCH_URL, params=parameters))


def _editions(topics: Sequence[FeedConfig]) -> tuple[GoogleNewsConfig, ...]:
    """The distinct editions of the topics that enable Google News, in topic order."""
    seen: dict[tuple[str, str, str], GoogleNewsConfig] = {}
    for topic in topics:
        config = topic.google_news
        if config.enabled:
            seen.setdefault((config.language, config.country, config.edition), config)
    return tuple(seen.values())


class GoogleNewsRssProvider:
    """Searches Google News's RSS search for the enabled topics; a discovery `SearchProvider`.

    With no topic enabling Google News it answers every search with nothing and sends no request.
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
        self._editions = _editions(topics)
        self._fetcher = FeedFetcher(
            client, cache=cache, clock=clock, provider=PROVIDER_NAME, max_bytes=max_bytes
        )

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    @property
    def editions(self) -> tuple[GoogleNewsConfig, ...]:
        """The editions every search asks, one request each."""
        return self._editions

    def __repr__(self) -> str:
        return f"{type(self).__name__}(editions={len(self._editions)})"

    async def aclose(self) -> None:
        """Close the HTTP client and its connections."""
        await self._client.aclose()

    async def search(self, query: ProviderQuery) -> ProviderResponse:
        started = time.perf_counter()
        outcomes: list[tuple[GoogleNewsConfig, FetchedFeed | ProviderError]] = []
        for edition in self._editions:
            try:
                outcomes.append((edition, await self._fetcher.fetch(search_url(query, edition))))
            except ProviderError as error:
                outcomes.append((edition, error))
        failures = [(edition, outcome) for edition, outcome in outcomes if isinstance(outcome, ProviderError)]
        if self._editions and len(failures) == len(self._editions):
            raise failures[0][1]
        kept: list[CandidateResult] = []
        seen_urls: set[str] = set()
        items = dropped = 0
        for _, outcome in outcomes:
            if isinstance(outcome, ProviderError):
                continue
            for entry in outcome.entries:
                items += 1
                candidate = candidate_from_item(entry)
                if candidate is None:
                    dropped += 1
                    continue
                if candidate.url in seen_urls or not in_window(candidate.published_at, query.filters):
                    continue
                seen_urls.add(candidate.url)
                kept.append(candidate)
        if outcomes:
            logger.info(
                "%s: %d of %d items dropped, publisher URL not resolvable without asking Google",
                self.name,
                dropped,
                items,
            )
        results = tuple(newest_first(kept, lambda candidate: candidate.published_at))[
            : query.filters.max_results
        ]
        elapsed_ms = (time.perf_counter() - started) * 1000
        if failures:
            reasons = "; ".join(
                f"{edition.edition}: {str(error).removeprefix(f'{error.provider}: ')}"
                for edition, error in failures
            )
            return ProviderResponse(
                provider=self.name,
                results=results,
                elapsed_ms=elapsed_ms,
                partial=True,
                error=f"{len(failures)} of {len(self._editions)} editions failed: {reasons}",
            )
        return ProviderResponse(provider=self.name, results=results, elapsed_ms=elapsed_ms)


def google_news_factory(
    http: HttpSettings,
    *,
    version: str,
    clock: Clock,
    topics: Sequence[FeedConfig],
    cache: FeedCache,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Callable[[ProviderSettings], GoogleNewsRssProvider]:
    """The registry's factory for `google_news`, over the same topics and cache as `rss`'s."""

    def build(settings: ProviderSettings) -> GoogleNewsRssProvider:
        del settings
        return GoogleNewsRssProvider(
            feed_client(http, version=version, transport=transport),
            topics=topics,
            cache=cache,
            clock=clock,
            max_bytes=min(http.max_response_bytes, MAX_FEED_BYTES),
        )

    return build
