"""A feed that keeps failing stops marking every search partial (v1-e07-t14, PM ruling 2026-11-05).

A feed that fails makes the feeds' answer partial while its failure is new. Once it has failed on
every read for three days, with no successful read between, the answer is no longer partial for it:
the feed is named in `notes`, with the day it started failing, and the reason. The day comes from
the injected clock and is kept in the feed's cache file; any successful read, a `304` included,
clears it. The feeds and dates are invented, and every expected value is written by hand.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

import httpx
import pytest
from pydantic import SecretStr

from debate_core.application.errors import ProviderUnavailable
from debate_core.application.settings import HttpSettings, ProviderSettings, SearchProviderName
from debate_core.domain.discovery import ProviderQuery, ProviderResponse
from debate_core.integrations.discovery.feed_cache import (
    CachedFeed,
    FeedCache,
    FileFeedCache,
    InMemoryFeedCache,
)
from debate_core.integrations.discovery.feed_config import FeedConfig, FeedReview, FeedSource
from debate_core.integrations.discovery.feeds import FeedProvider, feed_factory
from debate_core.testing.fakes.clock_and_ids import FixedClock

pytestmark = pytest.mark.anyio

FIXTURES: Final = Path(__file__).resolve().parents[2] / "fixtures" / "discovery" / "feeds"
COURIER_URL: Final = "https://news.example.org/rss/politics.xml"
WIRE_URL: Final = "https://wire.example.org/feed/"
GAZETTE_URL: Final = "https://gazette.example.net/rss"
COURIER: Final = FeedSource(url=COURIER_URL, publisher="Example Courier", review=FeedReview.COACH_REVIEWED)
WIRE: Final = FeedSource(url=WIRE_URL, publisher="Example Wire", review=FeedReview.COACH_REVIEWED)
GAZETTE: Final = FeedSource(url=GAZETTE_URL, publisher="Gone Gazette", review=FeedReview.COACH_REVIEWED)

FIRST_FAILURE: Final = datetime(2026, 11, 2, 9, 30, tzinfo=UTC)
"""When the Wire's feed first fails in these tests."""

UNREADABLE: Final = b"<rss><channel><title>Wire & Post</title></channel></rss>"
"""A bare `&`: not well-formed, so the Wire's feed is unreadable."""

WIRE_UNREADABLE: Final = "Example Wire: unreadable feed: not well-formed XML: ParseError"
STANDING_NOTE: Final = (
    "Example Wire failing since 2026-11-02: unreadable feed: not well-formed XML: ParseError"
)
QUERY: Final = ProviderQuery(query="health insurance")

WIRE_FEED: Final = (
    b'<?xml version="1.0"?><rss version="2.0"><channel><title>Example Wire</title>'
    b"<item><title>Wire health insurance brief</title><link>https://wire.example.org/brief</link>"
    b"<pubDate>Wed, 04 Nov 2026 08:00:00 +0000</pubDate></item></channel></rss>"
)
"""The Wire's feed once it reads again: one invented item."""


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class Feeds:
    """A transport that answers each feed URL with what the test last set for it, and counts asks."""

    def __init__(self, answers: dict[str, httpx.Response]) -> None:
        self.answers = answers
        self.asked: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.asked.append(request)
        answer = self.answers[str(request.url)]
        return httpx.Response(answer.status_code, headers=answer.headers, content=answer.content)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)


def courier() -> httpx.Response:
    return httpx.Response(200, content=(FIXTURES / "publisher_rss.xml").read_bytes())


def provider(feeds: Feeds, clock: FixedClock, cache: FeedCache, *sources: FeedSource) -> FeedProvider:
    topic = FeedConfig(topic="politics", description="Politics.", feeds=sources or (COURIER, WIRE))
    build = feed_factory(
        HttpSettings(),
        version="0.0.0-test",
        clock=clock,
        topics=(topic,),
        cache=cache,
        transport=feeds.transport(),
    )
    return build(
        ProviderSettings(enabled=(SearchProviderName.RSS,), contact_email=SecretStr("c@example.org"))
    )


async def search_at(
    moment: datetime, feeds: Feeds, cache: FeedCache, *sources: FeedSource
) -> ProviderResponse:
    return await provider(feeds, FixedClock(moment), cache, *sources).search(QUERY)


def failing_since(cache: FeedCache, url: str) -> datetime | None:
    kept = cache.get(url)
    return kept.failing_since if kept is not None else None


async def test_a_feed_failing_for_the_first_time_marks_the_answer_partial_and_is_remembered() -> None:
    feeds = Feeds({COURIER_URL: courier(), WIRE_URL: httpx.Response(200, content=UNREADABLE)})
    cache = InMemoryFeedCache()

    response = await search_at(FIRST_FAILURE, feeds, cache)

    assert response.partial
    assert response.error == f"1 of 2 feeds failed: {WIRE_UNREADABLE}"
    assert response.notes == ()
    assert response.results
    assert failing_since(cache, WIRE_URL) == FIRST_FAILURE
    assert failing_since(cache, COURIER_URL) is None


@pytest.mark.parametrize(
    "later", [timedelta(hours=1), timedelta(days=2), timedelta(days=3) - timedelta(seconds=1)]
)
async def test_a_feed_failing_on_every_read_for_under_three_days_still_marks_it_partial(
    later: timedelta,
) -> None:
    feeds = Feeds({COURIER_URL: courier(), WIRE_URL: httpx.Response(200, content=UNREADABLE)})
    cache = InMemoryFeedCache()
    await search_at(FIRST_FAILURE, feeds, cache)

    response = await search_at(FIRST_FAILURE + later, feeds, cache)

    assert response.partial
    assert response.error == f"1 of 2 feeds failed: {WIRE_UNREADABLE}"
    assert response.notes == ()
    assert failing_since(cache, WIRE_URL) == FIRST_FAILURE


@pytest.mark.parametrize("later", [timedelta(days=3), timedelta(days=9, hours=5)])
async def test_a_feed_failing_on_every_read_for_three_days_is_named_but_not_partial(later: timedelta) -> None:
    feeds = Feeds({COURIER_URL: courier(), WIRE_URL: httpx.Response(200, content=UNREADABLE)})
    cache = InMemoryFeedCache()
    await search_at(FIRST_FAILURE, feeds, cache)

    response = await search_at(FIRST_FAILURE + later, feeds, cache)

    assert not response.partial
    assert response.error is None
    assert response.notes == (STANDING_NOTE,)
    assert len(response.results) == 8
    assert failing_since(cache, WIRE_URL) == FIRST_FAILURE


async def test_every_query_of_one_read_carries_the_standing_failure() -> None:
    feeds = Feeds({COURIER_URL: courier(), WIRE_URL: httpx.Response(503)})
    cache = InMemoryFeedCache()
    await search_at(FIRST_FAILURE, feeds, cache)

    later = provider(feeds, FixedClock(FIRST_FAILURE + timedelta(days=4)), cache)
    queries = (QUERY, ProviderQuery(query="Senate"), ProviderQuery(query="no such words anywhere"))
    responses = await later.search_each(queries)

    assert [(response.partial, response.error, response.notes) for response in responses] == [
        (False, None, ("Example Wire failing since 2026-11-02: HTTP 503",))
    ] * 3


async def test_a_successful_read_clears_the_failure_and_the_next_failure_starts_afresh() -> None:
    feeds = Feeds({COURIER_URL: courier(), WIRE_URL: httpx.Response(200, content=UNREADABLE)})
    cache = InMemoryFeedCache()
    await search_at(FIRST_FAILURE, feeds, cache)
    assert (await search_at(FIRST_FAILURE + timedelta(days=3), feeds, cache)).notes == (STANDING_NOTE,)

    feeds.answers[WIRE_URL] = httpx.Response(200, content=WIRE_FEED)
    recovered = await search_at(FIRST_FAILURE + timedelta(days=3, hours=1), feeds, cache)
    assert (recovered.partial, recovered.error, recovered.notes) == (False, None, ())
    assert "Wire health insurance brief" in [result.title for result in recovered.results]
    assert failing_since(cache, WIRE_URL) is None

    feeds.answers[WIRE_URL] = httpx.Response(200, content=UNREADABLE)
    again = FIRST_FAILURE + timedelta(days=4)
    failed_again = await search_at(again, feeds, cache)
    assert failed_again.partial
    assert failed_again.notes == ()
    assert failing_since(cache, WIRE_URL) == again


async def test_a_not_modified_answer_is_a_successful_read_and_clears_the_failure() -> None:
    feeds = Feeds(
        {COURIER_URL: courier(), WIRE_URL: httpx.Response(200, headers={"ETag": '"w1"'}, content=WIRE_FEED)}
    )
    cache = InMemoryFeedCache()
    await search_at(FIRST_FAILURE - timedelta(days=1), feeds, cache)
    feeds.answers[WIRE_URL] = httpx.Response(503)
    await search_at(FIRST_FAILURE, feeds, cache)
    assert failing_since(cache, WIRE_URL) == FIRST_FAILURE

    feeds.answers[WIRE_URL] = httpx.Response(304)
    response = await search_at(FIRST_FAILURE + timedelta(days=5), feeds, cache)

    assert feeds.asked[-1].headers["If-None-Match"] == '"w1"'
    assert (response.partial, response.error, response.notes) == (False, None, ())
    assert "Wire health insurance brief" in [result.title for result in response.results]
    assert failing_since(cache, WIRE_URL) is None
    kept = cache.get(WIRE_URL)
    assert kept is not None and kept.etag == '"w1"' and len(kept.entries) == 1


async def test_a_standing_failure_beside_a_new_one_leaves_the_answer_partial_for_the_new_one() -> None:
    feeds = Feeds(
        {
            COURIER_URL: courier(),
            WIRE_URL: httpx.Response(200, content=UNREADABLE),
            GAZETTE_URL: httpx.Response(503),
        }
    )
    cache = InMemoryFeedCache()
    cache.put(CachedFeed(url=WIRE_URL, failing_since=FIRST_FAILURE))

    response = await search_at(FIRST_FAILURE + timedelta(days=6), feeds, cache, COURIER, WIRE, GAZETTE)

    assert response.partial
    assert response.error == "1 of 3 feeds failed: Gone Gazette: HTTP 503"
    assert response.notes == (STANDING_NOTE,)
    assert failing_since(cache, GAZETTE_URL) == FIRST_FAILURE + timedelta(days=6)


async def test_when_every_feed_fails_the_first_failure_is_raised_however_long_they_have_failed() -> None:
    feeds = Feeds({COURIER_URL: httpx.Response(503), WIRE_URL: httpx.Response(200, content=UNREADABLE)})
    cache = InMemoryFeedCache()
    cache.put(CachedFeed(url=COURIER_URL, failing_since=FIRST_FAILURE))
    cache.put(CachedFeed(url=WIRE_URL, failing_since=FIRST_FAILURE))

    with pytest.raises(ProviderUnavailable, match="HTTP 503"):
        await search_at(FIRST_FAILURE + timedelta(days=10), feeds, cache)


class UnwritableCache(InMemoryFeedCache):
    """A cache whose writes fail, as a full disk's would."""

    def put(self, feed: CachedFeed) -> None:
        raise OSError("no space left on device")


async def test_a_failure_that_cannot_be_remembered_stays_new_and_partial() -> None:
    feeds = Feeds({COURIER_URL: courier(), WIRE_URL: httpx.Response(200, content=UNREADABLE)})
    cache = UnwritableCache()

    await search_at(FIRST_FAILURE, feeds, cache)
    response = await search_at(FIRST_FAILURE + timedelta(days=5), feeds, cache)

    assert response.partial
    assert response.error == f"1 of 2 feeds failed: {WIRE_UNREADABLE}"
    assert response.notes == ()


async def test_the_day_a_feed_started_failing_survives_a_new_process_through_the_file_cache(
    tmp_path: Path,
) -> None:
    feeds = Feeds({COURIER_URL: courier(), WIRE_URL: httpx.Response(200, content=UNREADABLE)})

    await search_at(FIRST_FAILURE, feeds, FileFeedCache(tmp_path))
    response = await search_at(FIRST_FAILURE + timedelta(days=3), feeds, FileFeedCache(tmp_path))

    assert (response.partial, response.notes) == (False, (STANDING_NOTE,))


def test_a_cache_file_written_before_failures_were_kept_reads_with_none() -> None:
    kept = CachedFeed.model_validate_json(f'{{"url": "{WIRE_URL}", "etag": "\\"w1\\"", "entries": []}}')
    assert kept.failing_since is None
