"""The feed providers: publisher RSS/Atom (`rss`) and Google News RSS, and the contract kit for both.

Every feed is hand-written in `packages/debate_core/tests/fixtures/discovery/feeds/` (its README says
what each one covers), and every expected mapping is written by hand from those bodies (working
agreement 6). Nothing here reaches the network: requests go to a respx router that serves the
recordings and refuses anything else.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import httpx
import pytest
import respx
from pydantic import SecretStr

from debate_core.application.errors import ProviderRateLimited, ProviderUnavailable
from debate_core.application.ports.providers import SearchProvider
from debate_core.application.settings import HttpSettings, ProviderSettings, SearchProviderName
from debate_core.domain.discovery import CandidateResult, ProviderQuery
from debate_core.domain.search import SearchFilters
from debate_core.integrations.discovery import feeds as feeds_module
from debate_core.integrations.discovery.feed_cache import FeedCache, FileFeedCache, InMemoryFeedCache
from debate_core.integrations.discovery.feed_config import FeedConfig, FeedReview, FeedSource
from debate_core.integrations.discovery.feed_parsing import MAX_SNIPPET_CHARS, FeedEntry
from debate_core.integrations.discovery.feeds import (
    PROVIDER_NAME,
    FeedProvider,
    feed_factory,
    in_window,
    matches_terms,
    query_terms,
)
from debate_core.integrations.discovery.redaction import PROTECTED_LOGGERS
from debate_core.integrations.discovery.registry import ProviderRegistry
from debate_core.testing.contracts.search_provider import (
    Recording,
    ReplayedProvider,
    ReplayFactory,
    SearchProviderContract,
    SentRequest,
    TransportFailure,
    load_recording,
)
from debate_core.testing.fakes import FixedClock

pytestmark = pytest.mark.anyio

FIXTURES: Final = Path(__file__).resolve().parents[2] / "fixtures" / "discovery" / "feeds"
VERSION: Final = "0.0.0-test"
CONTACT_EMAIL: Final = "feeds-coach@example.org"
OPENALEX_KEY: Final = "openalex-key-not-for-feeds-7d1a"
RSS_URL: Final = "https://news.example.org/rss/politics.xml"
ATOM_URL: Final = "https://www.example.com/atom/health.xml"
COURIER: Final = FeedSource(url=RSS_URL, publisher="Example Courier", review=FeedReview.AWAITING_COACH_REVIEW)
LEDGER: Final = FeedSource(url=ATOM_URL, publisher="Example Health Ledger", review=FeedReview.COACH_REVIEWED)
TOPIC: Final = FeedConfig(topic="health-insurance", description="The Policy topic.", feeds=(COURIER, LEDGER))
WINDOW: Final = SearchFilters(
    since=datetime(2026, 10, 1, tzinfo=UTC), until=datetime(2026, 10, 21, tzinfo=UTC), max_results=10
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def bare_protected_loggers() -> Iterator[None]:
    """The protected loggers start with no filters, and get theirs back afterwards (working agreement 10)."""
    saved = {name: list(logging.getLogger(name).filters) for name in PROTECTED_LOGGERS}
    for name in PROTECTED_LOGGERS:
        logging.getLogger(name).filters.clear()
    yield
    for name, filters in saved.items():
        logging.getLogger(name).filters[:] = filters


def provider_settings() -> ProviderSettings:
    """`rss` enabled, beside credentials the feed providers are never given and must never surface."""
    return ProviderSettings(
        enabled=(SearchProviderName.RSS,),
        contact_email=SecretStr(CONTACT_EMAIL),
        openalex_api_key=SecretStr(OPENALEX_KEY),
    )


def build_feeds(
    transport: httpx.AsyncBaseTransport,
    *,
    topics: tuple[FeedConfig, ...] = (TOPIC,),
    cache: FeedCache | None = None,
    clock: FixedClock | None = None,
) -> FeedProvider:
    """The feed provider exactly as the registry builds it, over `transport`."""
    factory = feed_factory(
        HttpSettings(),
        version=VERSION,
        clock=clock or FixedClock(),
        topics=topics,
        cache=cache if cache is not None else InMemoryFeedCache(),
        transport=transport,
    )
    return factory(provider_settings())


def replay_with_respx(
    build: Callable[[httpx.AsyncBaseTransport], SearchProvider], seen: list[httpx.Request] | None = None
) -> ReplayFactory:
    """Serve a recording's exchanges through respx, and nothing else.

    A copy of the FakeProvider binding's (`test_fake_provider.py`), as OpenAlex's is: the adapter is
    built from a transport, so that the factory's own client is the one under test, and every
    request is kept in `seen` when given, so that a test can read its headers. Transport failures
    are raised here rather than as respx side effects, because respx re-raises a side effect `from`
    an error that quotes the matched route.
    """

    def replay(recording: Recording) -> ReplayedProvider:
        router = respx.MockRouter(assert_all_called=False, assert_all_mocked=True)
        failures: dict[SentRequest, TransportFailure] = {}
        for exchange in recording.exchanges:
            if exchange.failure is not None:
                failures[SentRequest(exchange.method.upper(), exchange.url)] = exchange.failure
            elif exchange.response is not None:
                answer = exchange.response
                router.route(method=exchange.method, url=exchange.url).return_value = httpx.Response(
                    answer.status, headers=answer.headers, content=answer.body
                )
        sent: list[SentRequest] = []

        async def transport(request: httpx.Request) -> httpx.Response:
            this = SentRequest(request.method, str(request.url))
            sent.append(this)
            if seen is not None:
                seen.append(request)
            failure = failures.get(this)
            if failure is TransportFailure.TIMEOUT:
                raise httpx.ReadTimeout("timed out", request=request)
            if failure is TransportFailure.CONNECTION_ERROR:
                raise httpx.ConnectError("connection refused", request=request)
            return await router.async_handler(request)

        return ReplayedProvider(build(httpx.MockTransport(transport)), lambda: tuple(sent))

    return replay


def recording(name: str) -> Recording:
    return load_recording(FIXTURES / f"{name}.json")


def serving(answers: dict[str, httpx.Response]) -> httpx.MockTransport:
    """A transport that answers each URL in `answers` and fails the test on any other."""

    def handle(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        assert url in answers, f"unexpected request to {url}"
        return answers[url]

    return httpx.MockTransport(handle)


def feed_response(name: str, **headers: str) -> httpx.Response:
    return httpx.Response(200, headers=headers, content=(FIXTURES / name).read_bytes())


def an_entry(title: str, snippet: str | None = None, published_at: datetime | None = None) -> FeedEntry:
    return FeedEntry(title=title, link="https://a.example.org/x", snippet=snippet, published_at=published_at)


async def chunks(*parts: bytes) -> AsyncIterator[bytes]:
    """A body with no declared length, so that only counting it as it arrives can catch its size."""
    for part in parts:
        yield part


def dumped(results: tuple[CandidateResult, ...]) -> list[dict[str, object]]:
    return [result.model_dump(mode="json") for result in results]


# --------------------------------------------------------------------------------------------
# Which feed entries are kept
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "terms"),
    [
        ("health insurance", ("health", "insurance")),
        ('"health insurance" Medicaid', ("health insurance", "medicaid")),
        ("  HEALTH   Insurance ", ("health", "insurance")),
        ('""', ()),
    ],
)
def test_feed_query_terms_are_quoted_phrases_then_words_folded(query: str, terms: tuple[str, ...]) -> None:
    assert query_terms(query) == terms


@pytest.mark.parametrize(
    ("title", "snippet", "query", "kept"),
    [
        ("Health insurance subsidies", None, "health insurance", True),
        ("Subsidies", "Health and dental insurance", "health insurance", True),
        ("Subsidies", "Health and dental insurance", '"health insurance"', False),
        ("Health Insurance, explained", None, '"health insurance"', True),
        ("Reinsurance pool and health costs", "Reinsurance only.", "health insurance", False),
        ("Healthy insurance markets", None, "health insurance", False),
        ("Health insurance", None, "health insurance medicaid", False),
        ("Anything at all", None, '""', True),
    ],
)
def test_a_feed_entry_is_kept_when_every_term_is_a_whole_word_in_title_or_snippet(
    title: str, snippet: str | None, query: str, kept: bool
) -> None:
    assert matches_terms(an_entry(title, snippet), query_terms(query)) is kept


@pytest.mark.parametrize(
    ("published_at", "inside"),
    [
        (datetime(2026, 10, 1, tzinfo=UTC), True),
        (datetime(2026, 10, 21, tzinfo=UTC), True),
        (datetime(2026, 9, 30, 23, 59, 59, tzinfo=UTC), False),
        (datetime(2026, 10, 21, 0, 0, 1, tzinfo=UTC), False),
        (None, False),
    ],
)
def test_a_feed_window_includes_both_ends_and_never_an_undated_entry(
    published_at: datetime | None, inside: bool
) -> None:
    assert in_window(published_at, WINDOW) is inside


def test_with_no_feed_window_every_entry_is_inside_dated_or_not() -> None:
    assert in_window(None, SearchFilters()) is True
    assert in_window(datetime(1999, 1, 1, tzinfo=UTC), SearchFilters()) is True
    assert in_window(None, SearchFilters(since=datetime(2026, 10, 1, tzinfo=UTC))) is False
    assert in_window(None, SearchFilters(until=datetime(2026, 10, 1, tzinfo=UTC))) is False


# --------------------------------------------------------------------------------------------
# The feed provider
# --------------------------------------------------------------------------------------------


async def test_the_feed_recording_maps_to_news_candidates_newest_first() -> None:
    replayed = replay_with_respx(build_feeds)(recording("feeds_search"))
    response = await replayed.provider.search(ProviderQuery(query="health insurance", filters=WINDOW))
    assert dumped(response.results) == dumped(recording("feeds_search").expected)
    assert {result.source_type.value for result in response.results} == {"news"}
    assert all(
        result.published_at is not None and result.published_at.tzinfo is not None
        for result in response.results
    )


async def test_feed_snippets_never_carry_feed_content_and_never_pass_500_characters() -> None:
    long_summary = "<p>" + "Premiums rise in every state. " * 40 + "</p>"
    feed = (
        '<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><item>'
        "<title>Health insurance premiums</title><link>https://a.example.org/premiums</link>"
        f"<description><![CDATA[{long_summary}]]></description>"
        "<content:encoded><![CDATA[FULL ARTICLE TEXT FROM THE FEED]]></content:encoded>"
        "</item></channel></rss>"
    ).encode()
    provider = build_feeds(
        serving({RSS_URL: httpx.Response(200, content=feed)}),
        topics=(FeedConfig(topic="t", description="T.", feeds=(COURIER,)),),
    )
    response = await provider.search(ProviderQuery(query="health insurance"))
    (only,) = response.results
    assert only.snippet is not None
    assert len(only.snippet) <= MAX_SNIPPET_CHARS
    assert only.snippet.startswith("Premiums rise in every state.")
    assert "FULL ARTICLE TEXT" not in only.model_dump_json()


async def test_with_no_feed_window_undated_entries_are_kept_and_listed_last() -> None:
    transport = serving(
        {RSS_URL: feed_response("publisher_rss.xml"), ATOM_URL: feed_response("publisher_atom.xml")}
    )
    response = await build_feeds(transport).search(
        ProviderQuery(query="health insurance", filters=SearchFilters(max_results=50))
    )
    titles = [result.title for result in response.results]
    undated = [result.title for result in response.results if result.published_at is None]
    assert undated == [
        "Undated health insurance explainer",
        "UK health insurance comparison",
        "Health insurance glossary",
        "Health insurance with a date and no offset",
    ]
    assert titles[-len(undated) :] == undated
    assert "Health insurance rules from last year" in titles


async def test_a_feed_listing_one_link_twice_yields_it_once() -> None:
    transport = serving(
        {RSS_URL: feed_response("publisher_rss.xml"), ATOM_URL: feed_response("publisher_atom.xml")}
    )
    response = await build_feeds(transport).search(
        ProviderQuery(query="subsidy", filters=SearchFilters(max_results=50))
    )
    assert [result.provider_record_id for result in response.results] == ["courier-1001"]


async def test_feed_results_are_cut_to_max_results_after_ordering() -> None:
    replayed = replay_with_respx(build_feeds)(recording("feeds_search"))
    filters = WINDOW.model_copy(update={"max_results": 3})
    response = await replayed.provider.search(ProviderQuery(query="health insurance", filters=filters))
    assert [result.provider_record_id for result in response.results] == [
        "courier-1001",
        "tag:example.com,2026:mergers",
        "courier-1002",
    ]


async def test_feed_conditional_get_sends_validators_and_a_304_reuses_the_entries_unparsed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = InMemoryFeedCache()
    seen: list[httpx.Request] = []
    query = ProviderQuery(query="health insurance", filters=WINDOW)
    first = replay_with_respx(lambda transport: build_feeds(transport, cache=cache), seen)(
        recording("feeds_search")
    )
    fresh = await first.provider.search(query)
    assert all("if-none-match" not in request.headers for request in seen)
    assert all("if-modified-since" not in request.headers for request in seen)

    def must_not_parse(body: bytes) -> object:
        raise AssertionError("a 304 must not parse anything")

    monkeypatch.setattr(feeds_module, "parse_feed", must_not_parse)
    seen.clear()
    second = replay_with_respx(lambda transport: build_feeds(transport, cache=cache), seen)(
        recording("feeds_not_modified")
    )
    again = await second.provider.search(query)
    sent = {str(request.url): request.headers for request in seen}
    assert sent[RSS_URL].get("if-none-match") == '"courier-v1"'
    assert "if-modified-since" not in sent[RSS_URL]
    assert sent[ATOM_URL].get("if-modified-since") == "Tue, 20 Oct 2026 13:00:00 GMT"
    assert "if-none-match" not in sent[ATOM_URL]
    assert dumped(again.results) == dumped(fresh.results) == dumped(recording("feeds_not_modified").expected)
    assert not again.partial


async def test_feed_conditional_get_survives_a_new_process_through_the_file_cache(tmp_path: Path) -> None:
    query = ProviderQuery(query="health insurance", filters=WINDOW)
    first = replay_with_respx(lambda transport: build_feeds(transport, cache=FileFeedCache(tmp_path)))
    await first(recording("feeds_search")).provider.search(query)
    seen: list[httpx.Request] = []
    second = replay_with_respx(lambda transport: build_feeds(transport, cache=FileFeedCache(tmp_path)), seen)
    response = await second(recording("feeds_not_modified")).provider.search(query)
    assert dumped(response.results) == dumped(recording("feeds_search").expected)
    assert {request.headers.get("if-none-match") for request in seen} == {'"courier-v1"', None}
    stored = "".join(path.read_text(encoding="utf-8") for path in tmp_path.iterdir())
    assert "FULL ARTICLE TEXT" not in stored


async def test_a_feed_304_with_nothing_cached_is_a_failure_not_an_empty_feed() -> None:
    topics = (FeedConfig(topic="t", description="T.", feeds=(COURIER,)),)
    provider = build_feeds(serving({RSS_URL: httpx.Response(304)}), topics=topics)
    with pytest.raises(ProviderUnavailable, match="nothing cached"):
        await provider.search(ProviderQuery(query="health insurance"))


async def test_one_feed_rate_limited_makes_the_answer_partial_and_names_the_publisher() -> None:
    replayed = replay_with_respx(build_feeds)(recording("feeds_rate_limited"))
    response = await replayed.provider.search(ProviderQuery(query="health insurance", filters=WINDOW))
    assert response.partial
    assert response.error == "1 of 2 feeds failed: Example Courier: HTTP 429 (retry after 600.0s)"
    assert dumped(response.results) == dumped(recording("feeds_rate_limited").expected)
    assert [request.url for request in replayed.sent()].count(RSS_URL) == 1


async def test_the_only_feed_rate_limited_raises_with_its_retry_after() -> None:
    topics = (FeedConfig(topic="t", description="T.", feeds=(COURIER,)),)
    transport = serving({RSS_URL: httpx.Response(429, headers={"Retry-After": "600"})})
    with pytest.raises(ProviderRateLimited) as raised:
        await build_feeds(transport, topics=topics).search(ProviderQuery(query="health insurance"))
    assert raised.value.retry_after_seconds == 600


async def test_when_every_feed_fails_the_first_failure_is_raised() -> None:
    transport = serving({RSS_URL: httpx.Response(503), ATOM_URL: httpx.Response(429)})
    with pytest.raises(ProviderUnavailable, match="HTTP 503"):
        await build_feeds(transport).search(ProviderQuery(query="health insurance"))


@pytest.mark.parametrize("name", ["entity_expansion.xml", "external_entity.xml"])
async def test_a_hostile_feed_is_refused_as_unreadable(name: str) -> None:
    topics = (FeedConfig(topic="t", description="T.", feeds=(COURIER,)),)
    transport = serving({RSS_URL: feed_response(name)})
    with pytest.raises(ProviderUnavailable, match="unreadable feed: refused: EntitiesForbidden"):
        await build_feeds(transport, topics=topics).search(ProviderQuery(query="health insurance"))


async def test_a_hostile_feed_beside_a_good_one_costs_only_itself() -> None:
    transport = serving(
        {RSS_URL: feed_response("entity_expansion.xml"), ATOM_URL: feed_response("publisher_atom.xml")}
    )
    response = await build_feeds(transport).search(ProviderQuery(query="health insurance", filters=WINDOW))
    assert response.partial
    assert (
        response.error == "1 of 2 feeds failed: Example Courier: unreadable feed: refused: EntitiesForbidden"
    )
    assert dumped(response.results) == dumped(recording("feeds_rate_limited").expected)


@pytest.mark.parametrize(
    "response",
    [
        pytest.param(
            lambda: httpx.Response(200, content=chunks(b"<rss>", b" " * 2048)), id="streamed-too-long"
        ),
        pytest.param(
            lambda: httpx.Response(200, headers={"Content-Length": "999999"}, content=b"<rss/>"),
            id="declared-too-long",
        ),
    ],
)
async def test_a_feed_larger_than_the_cap_is_abandoned_not_truncated(
    response: Callable[[], httpx.Response],
) -> None:
    topics = (FeedConfig(topic="t", description="T.", feeds=(COURIER,)),)
    provider = FeedProvider(
        httpx.AsyncClient(transport=serving({RSS_URL: response()})),
        topics=topics,
        cache=InMemoryFeedCache(),
        clock=FixedClock(),
        max_bytes=1024,
    )
    with pytest.raises(ProviderUnavailable, match="larger than 1024 bytes"):
        await provider.search(ProviderQuery(query="health insurance"))


async def test_a_feed_that_redirects_is_followed() -> None:
    moved = "https://news.example.org/rss/politics-v2.xml"
    topics = (FeedConfig(topic="t", description="T.", feeds=(COURIER,)),)
    transport = serving(
        {RSS_URL: httpx.Response(301, headers={"Location": moved}), moved: feed_response("publisher_rss.xml")}
    )
    response = await build_feeds(transport, topics=topics).search(
        ProviderQuery(query="health insurance", filters=WINDOW)
    )
    assert response.results[0].provider_record_id == "courier-1001"


async def test_a_feed_cache_that_cannot_be_written_costs_nothing_but_the_next_304(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    blocked = tmp_path / "feeds"
    blocked.write_text("a file where the directory should be", encoding="utf-8")
    replayed = replay_with_respx(lambda transport: build_feeds(transport, cache=FileFeedCache(blocked)))
    with caplog.at_level(logging.WARNING, logger="debate_core.integrations.discovery"):
        response = await replayed(recording("feeds_search")).provider.search(
            ProviderQuery(query="health insurance", filters=WINDOW)
        )
    assert dumped(response.results) == dumped(recording("feeds_search").expected)
    assert "feed cache not written" in caplog.text


async def test_feed_requests_identify_the_platform_and_ask_for_feeds() -> None:
    seen: list[httpx.Request] = []
    replayed = replay_with_respx(build_feeds, seen)(recording("feeds_search"))
    await replayed.provider.search(ProviderQuery(query="health insurance", filters=WINDOW))
    for request in seen:
        assert request.headers["user-agent"].startswith(f"debate-research/{VERSION} (+")
        assert "application/rss+xml" in request.headers["accept"]
        assert "cookie" not in request.headers


async def test_feed_logs_counts_and_never_a_title(caplog: pytest.LogCaptureFixture) -> None:
    replayed = replay_with_respx(build_feeds)(recording("feeds_search"))
    with caplog.at_level(logging.DEBUG, logger="debate_core.integrations.discovery"):
        await replayed.provider.search(ProviderQuery(query="health insurance", filters=WINDOW))
    lines = [
        record.getMessage()
        for record in caplog.records
        if record.name == "debate_core.integrations.discovery"
    ]
    assert lines == ["rss: 2 feeds read, 0 unchanged, 0 failed"]


async def test_the_feed_registry_builds_rss_wrapped_and_it_answers() -> None:
    def build(transport: httpx.AsyncBaseTransport) -> SearchProvider:
        factory = feed_factory(
            HttpSettings(),
            version=VERSION,
            clock=FixedClock(),
            topics=(TOPIC,),
            cache=InMemoryFeedCache(),
            transport=transport,
        )
        registry = ProviderRegistry.from_settings(
            provider_settings(), {SearchProviderName.RSS: factory}, clock=FixedClock()
        )
        assert registry.names == (PROVIDER_NAME,)
        return registry.get(PROVIDER_NAME)

    replayed = replay_with_respx(build)(recording("feeds_search"))
    assert repr(replayed.provider).startswith("ResilientProvider(name='rss'")
    response = await replayed.provider.search(ProviderQuery(query="health insurance", filters=WINDOW))
    assert dumped(response.results) == dumped(recording("feeds_search").expected)


# --------------------------------------------------------------------------------------------
# The contract kit
# --------------------------------------------------------------------------------------------


@pytest.mark.usefixtures("bare_protected_loggers")
class TestFeedProviderContract(SearchProviderContract):
    """The publisher feed provider on its recorded RSS and Atom feeds."""

    @pytest.fixture
    def replay(self) -> ReplayFactory:
        return replay_with_respx(build_feeds)

    @pytest.fixture
    def recording(self) -> Recording:
        return recording("feeds_search")

    @pytest.fixture
    def secrets(self) -> tuple[str, ...]:
        return (CONTACT_EMAIL, OPENALEX_KEY)

    @pytest.fixture
    def max_attempts(self) -> int:
        return 1
