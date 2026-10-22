"""`HttpArticleFetcher` against respx, offline, on a simulated clock (v1-e04-t02).

Every response comes from a respx route serving the synthetic files in
`tests/fixtures/http_fetcher/`; a route nobody declared fails the test, and the workspace's
`--disable-socket` would stop any request that escaped respx. Connection failures are raised by
this module's own transport function rather than a respx side effect, because respx wraps those in
an error that quotes the route.

Time never really passes. The fetcher's clock is a
:class:`~debate_core.testing.fakes.FixedClock` that moves only when the fetcher sleeps (through
:class:`SimulatedTime`) or when a test's transport says a request took a while, so every interval
and backoff below is asserted exactly.

Test names carry the spec's `-k` filters: `limits` for the http-client node, `retry` for the retry
policy, and `robots` or `rate` for robots.txt and the per-host limiter.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from debate_core.application.ports.providers import ArticleFetcher
from debate_core.application.settings import HttpSettings
from debate_core.domain import AccessStatus
from debate_core.integrations.http_fetcher import (
    HTTP_CLIENT_LOGGERS,
    HostRateLimiter,
    HttpArticleFetcher,
    RequestUrlLogFilter,
)
from debate_core.retrieval.canonical_url import canonicalize_url
from debate_core.retrieval.fetch_types import (
    FetchResult,
    HttpStatusError,
    NonPublicAddress,
    RobotsDisallowed,
    RobotsRefusalReason,
    Timeout,
    TimeoutPhase,
    TooLarge,
    TooManyRedirects,
    TransportError,
    UnsupportedScheme,
)
from debate_core.testing.fakes import FixedClock

pytestmark = pytest.mark.anyio

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "http_fetcher"
START = datetime(2026, 10, 21, 9, 0, 0, tzinfo=UTC)
VERSION = "1.3.0"
CONTACT = "https://example.org/debate-contact"
USER_AGENT = f"debate-research/{VERSION} (+{CONTACT})"

SITE = "https://news.example.org"
ARTICLE = f"{SITE}/2026/10/grid-storage"
ROBOTS = f"{SITE}/robots.txt"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class SimulatedTime:
    """The fetcher's clock and sleep: sleeping moves the clock, and nothing else waits."""

    def __init__(self) -> None:
        self.clock = FixedClock(START)
        self.sleeps: list[float] = []

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.clock.advance(timedelta(seconds=seconds))

    def seconds_since_start(self, moment: datetime) -> float:
        return (moment - START).total_seconds()


class Web:
    """respx routes behind a transport that can also fail a connection or take time to answer."""

    def __init__(self, time: SimulatedTime) -> None:
        self.time = time
        self.router = respx.MockRouter(assert_all_called=False, assert_all_mocked=True)
        self.failures: dict[str, list[Exception]] = {}
        """URL → exceptions to raise for its next requests, in order, before respx answers."""
        self.latency = timedelta(0)
        """How far the clock moves while each request is answered."""
        self.requests: list[httpx.Request] = []
        self.started_at: list[datetime] = []

    def fail(self, url: str, *failures: Exception) -> None:
        self.failures.setdefault(url, []).extend(failures)

    async def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        self.started_at.append(self.time.clock.now())
        self.time.clock.advance(self.latency)
        queue = self.failures.get(str(request.url))
        if queue:
            raise queue.pop(0)
        return await self.router.async_handler(request)

    @property
    def requested(self) -> list[str]:
        return [str(request.url) for request in self.requests]

    def allow_everything(self, site: str = SITE) -> respx.Route:
        return self.router.get(f"{site}/robots.txt").respond(404)


def make_settings(**overrides: Any) -> HttpSettings:
    values: dict[str, Any] = {
        "contact_url": CONTACT,
        "per_host_interval_seconds": 0.0,
        "max_retries": 2,
        "backoff_base_seconds": 1.0,
        "backoff_max_seconds": 30.0,
        "max_retry_wait_seconds": 120.0,
        "max_response_bytes": 64 * 1024,
        "max_redirects": 3,
        "request_timeout_seconds": 30.0,
        "connect_timeout_seconds": 10.0,
    }
    values.update(overrides)
    return HttpSettings(**values)


@pytest.fixture
def time() -> SimulatedTime:
    return SimulatedTime()


@pytest.fixture
def web(time: SimulatedTime) -> Web:
    return Web(time)


@pytest.fixture
def build(web: Web, time: SimulatedTime) -> Callable[..., HttpArticleFetcher]:
    """Builds a fetcher on `web` and `time`; `jitter` defaults to the top of its range.

    The tests close what they build with `async with`.
    """

    def factory(jitter: Callable[[], float] = lambda: 1.0, **overrides: Any) -> HttpArticleFetcher:
        fetcher = HttpArticleFetcher(
            make_settings(**overrides),
            version=VERSION,
            clock=time.clock,
            sleep=time.sleep,
            jitter=jitter,
            transport=httpx.MockTransport(web.handle),
        )
        return fetcher

    return factory


@pytest.fixture
async def fetcher(build: Callable[..., HttpArticleFetcher]) -> AsyncIterator[HttpArticleFetcher]:
    async with build() as built:
        yield built


class DrippingBody(httpx.AsyncByteStream):
    """A body sent in chunks, counting how many the fetcher pulled; can advance the clock per chunk."""

    def __init__(
        self,
        chunks: int,
        chunk_size: int,
        *,
        time: SimulatedTime | None = None,
        per_chunk: timedelta = timedelta(0),
        fail_after: int | None = None,
    ) -> None:
        self.chunks = chunks
        self.chunk_size = chunk_size
        self.time = time
        self.per_chunk = per_chunk
        self.fail_after = fail_after
        self.pulled = 0

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for index in range(self.chunks):
            if self.fail_after is not None and index == self.fail_after:
                raise httpx.ReadError("the peer reset the connection")
            self.pulled += 1
            if self.time is not None:
                self.time.clock.advance(self.per_chunk)
            yield b"x" * self.chunk_size


# --------------------------------------------------------------------------------------------
# ac1: the port, and what a result carries
# --------------------------------------------------------------------------------------------


async def test_the_fetcher_implements_the_article_fetcher_port(fetcher: HttpArticleFetcher) -> None:
    port: ArticleFetcher = fetcher
    assert isinstance(port, ArticleFetcher)


async def test_a_page_comes_back_with_its_bytes_and_everything_about_the_response(
    build: Callable[..., HttpArticleFetcher], web: Web, time: SimulatedTime
) -> None:
    web.latency = timedelta(milliseconds=250)
    web.allow_everything()
    page = fixture_bytes("article.html")
    web.router.get(ARTICLE).respond(
        200, content=page, headers={"Content-Type": "text/html; charset=utf-8", "X-Served-By": "edge-7"}
    )

    async with build() as fetcher:
        result = await fetcher.fetch(ARTICLE)

    assert result.error is None
    assert result.requested_url == ARTICLE
    assert result.final_url == ARTICLE
    assert result.redirect_chain == ()
    assert result.status_code == 200
    assert result.headers["x-served-by"] == "edge-7"
    assert result.headers["content-type"] == "text/html; charset=utf-8"
    assert result.content_type == "text/html; charset=utf-8"
    assert result.sniffed_content_type == "text/html"
    assert result.body == page
    assert result.byte_size == len(page)
    assert result.elapsed_ms == 500.0  # robots.txt, then the page, 250 ms each
    assert result.fetched_at == START + timedelta(milliseconds=500)
    assert result.access_status is AccessStatus.UNKNOWN


async def test_a_mislabelled_pdf_is_sniffed_and_its_declared_type_kept(
    fetcher: HttpArticleFetcher, web: Web
) -> None:
    web.allow_everything()
    pdf = fixture_bytes("paper.pdf")
    web.router.get(f"{SITE}/paper").respond(
        200, content=pdf, headers={"Content-Type": "application/octet-stream"}
    )

    result = await fetcher.fetch(f"{SITE}/paper")

    assert result.content_type == "application/octet-stream"
    assert result.sniffed_content_type == "application/pdf"
    assert result.body == pdf


async def test_the_url_is_fetched_as_given_and_its_canonical_form_is_never_requested(
    fetcher: HttpArticleFetcher, web: Web
) -> None:
    given = "https://News.Example.org/2026/10/grid-storage/amp?utm_source=feed&id=7"
    canonical = canonicalize_url(given)
    assert canonical != given
    web.allow_everything()
    web.router.get(given).respond(200, content=b"<html></html>")

    result = await fetcher.fetch(given)

    assert result.requested_url == given
    assert web.requested == [ROBOTS, "https://news.example.org/2026/10/grid-storage/amp?utm_source=feed&id=7"]
    assert canonical not in web.requested


async def test_a_redirect_reports_the_final_url_and_the_hops_before_it(
    fetcher: HttpArticleFetcher, web: Web
) -> None:
    web.allow_everything()
    web.router.get(f"{SITE}/short").respond(301, headers={"Location": "/2026/10/grid-storage"})
    web.router.get(ARTICLE).respond(200, content=b"<html>moved</html>")

    result = await fetcher.fetch(f"{SITE}/short")

    assert result.status_code == 200
    assert result.final_url == ARTICLE
    assert result.redirect_chain == (f"{SITE}/short",)
    assert result.body == b"<html>moved</html>"


async def test_an_error_status_keeps_its_body_for_the_classifier(
    fetcher: HttpArticleFetcher, web: Web
) -> None:
    web.allow_everything()
    web.router.get(ARTICLE).respond(403, content=b"<html>checking your browser</html>")

    result = await fetcher.fetch(ARTICLE)

    assert result.status_code == 403
    assert result.body == b"<html>checking your browser</html>"
    assert isinstance(result.error, HttpStatusError)
    assert (result.error.status_code, result.error.attempts) == (403, 1)
    assert result.access_status is AccessStatus.UNKNOWN


async def test_a_result_round_trips_through_json_with_its_error(
    fetcher: HttpArticleFetcher, web: Web
) -> None:
    web.router.get(ROBOTS).respond(200, content=fixture_bytes("robots_disallow_private.txt"))

    result = await fetcher.fetch(f"{SITE}/private/memo")

    assert FetchResult.model_validate_json(result.model_dump_json()) == result


# --------------------------------------------------------------------------------------------
# ac2: timeouts, size and redirects, from settings, as typed errors
# --------------------------------------------------------------------------------------------


async def test_limits_a_connect_timeout_is_a_typed_timeout(
    build: Callable[..., HttpArticleFetcher], web: Web
) -> None:
    web.allow_everything()
    web.fail(ARTICLE, httpx.ConnectTimeout("timed out"))

    async with build(max_retries=0, connect_timeout_seconds=4.0) as fetcher:
        result = await fetcher.fetch(ARTICLE)

    assert isinstance(result.error, Timeout)
    assert (result.error.phase, result.error.limit_seconds) == (TimeoutPhase.CONNECT, 4.0)
    assert result.status_code is None
    assert result.body == b""


async def test_limits_a_read_timeout_is_a_typed_timeout_and_is_not_retried(
    build: Callable[..., HttpArticleFetcher], web: Web, time: SimulatedTime
) -> None:
    web.allow_everything()
    web.fail(ARTICLE, httpx.ReadTimeout("timed out"))

    async with build(request_timeout_seconds=12.0) as fetcher:
        result = await fetcher.fetch(ARTICLE)

    assert isinstance(result.error, Timeout)
    assert (result.error.phase, result.error.limit_seconds) == (TimeoutPhase.READ, 12.0)
    assert web.requested.count(ARTICLE) == 1
    assert time.sleeps == []


async def test_limits_a_body_that_drips_past_the_request_deadline_is_a_total_timeout(
    build: Callable[..., HttpArticleFetcher], web: Web, time: SimulatedTime
) -> None:
    web.allow_everything()
    body = DrippingBody(10, 100, time=time, per_chunk=timedelta(seconds=4))
    web.router.get(ARTICLE).mock(return_value=httpx.Response(200, stream=body))

    async with build(request_timeout_seconds=10.0) as fetcher:
        result = await fetcher.fetch(ARTICLE)

    assert isinstance(result.error, Timeout)
    assert result.error.phase is TimeoutPhase.TOTAL
    assert body.pulled == 3  # 12 s had passed after the third chunk
    assert result.body == b""


async def test_limits_a_declared_length_over_the_limit_is_too_large_before_any_body_is_read(
    build: Callable[..., HttpArticleFetcher], web: Web
) -> None:
    web.allow_everything()
    body = DrippingBody(10, 1024)
    web.router.get(ARTICLE).mock(
        return_value=httpx.Response(200, headers={"Content-Length": "10240"}, stream=body)
    )

    async with build(max_response_bytes=4096) as fetcher:
        result = await fetcher.fetch(ARTICLE)

    assert isinstance(result.error, TooLarge)
    assert (result.error.limit_bytes, result.error.declared_bytes, result.error.received_bytes) == (
        4096,
        10240,
        0,
    )
    assert body.pulled == 0
    assert result.body == b""


async def test_limits_an_undeclared_body_is_abandoned_as_soon_as_it_passes_the_limit(
    build: Callable[..., HttpArticleFetcher], web: Web
) -> None:
    web.allow_everything()
    body = DrippingBody(1000, 1024)
    web.router.get(ARTICLE).mock(return_value=httpx.Response(200, stream=body))

    async with build(max_response_bytes=4096) as fetcher:
        result = await fetcher.fetch(ARTICLE)

    assert isinstance(result.error, TooLarge)
    assert result.error.declared_bytes is None
    assert result.error.received_bytes == 5 * 1024
    assert body.pulled == 5  # the limit and one chunk, not the 1000 the server had
    assert result.body == b""


async def test_limits_a_body_exactly_at_the_limit_is_kept_whole(
    build: Callable[..., HttpArticleFetcher], web: Web
) -> None:
    web.allow_everything()
    web.router.get(ARTICLE).mock(return_value=httpx.Response(200, stream=DrippingBody(4, 1024)))

    async with build(max_response_bytes=4096) as fetcher:
        result = await fetcher.fetch(ARTICLE)

    assert result.error is None
    assert result.byte_size == 4096


async def test_limits_redirects_up_to_the_limit_are_followed(
    build: Callable[..., HttpArticleFetcher], web: Web
) -> None:
    web.allow_everything()
    for hop in range(2):
        web.router.get(f"{SITE}/hop{hop}").respond(302, headers={"Location": f"/hop{hop + 1}"})
    web.router.get(f"{SITE}/hop2").respond(200, content=b"<html>arrived</html>")

    async with build(max_redirects=2) as fetcher:
        result = await fetcher.fetch(f"{SITE}/hop0")

    assert result.error is None
    assert result.final_url == f"{SITE}/hop2"
    assert result.redirect_chain == (f"{SITE}/hop0", f"{SITE}/hop1")


async def test_limits_one_redirect_too_many_is_refused_without_requesting_its_target(
    build: Callable[..., HttpArticleFetcher], web: Web
) -> None:
    web.allow_everything()
    for hop in range(3):
        web.router.get(f"{SITE}/hop{hop}").respond(302, headers={"Location": f"/hop{hop + 1}"})
    beyond = web.router.get(f"{SITE}/hop3").respond(200)

    async with build(max_redirects=2) as fetcher:
        result = await fetcher.fetch(f"{SITE}/hop0")

    assert isinstance(result.error, TooManyRedirects)
    assert result.error.limit == 2
    assert result.error.redirect_chain == (f"{SITE}/hop0", f"{SITE}/hop1", f"{SITE}/hop2")
    assert not beyond.called
    assert result.final_url == f"{SITE}/hop2"
    assert result.redirect_chain == (f"{SITE}/hop0", f"{SITE}/hop1")


async def test_limits_no_redirect_is_followed_when_the_limit_is_zero(
    build: Callable[..., HttpArticleFetcher], web: Web
) -> None:
    web.allow_everything()
    web.router.get(f"{SITE}/short").respond(301, headers={"Location": "/long"})
    target = web.router.get(f"{SITE}/long").respond(200)

    async with build(max_redirects=0) as fetcher:
        result = await fetcher.fetch(f"{SITE}/short")

    assert isinstance(result.error, TooManyRedirects)
    assert not target.called


@pytest.mark.parametrize(
    "location", ["ftp://files.example.org/a.pdf", "file:///etc/passwd", "javascript:alert(1)"]
)
async def test_limits_a_redirect_to_anything_but_http_or_https_is_refused(
    fetcher: HttpArticleFetcher, web: Web, location: str
) -> None:
    web.allow_everything()
    web.router.get(ARTICLE).respond(302, headers={"Location": location})

    result = await fetcher.fetch(ARTICLE)

    assert isinstance(result.error, UnsupportedScheme)
    assert result.error.scheme == location.split(":", 1)[0]
    assert result.error.url == ARTICLE
    assert result.final_url == ARTICLE
    assert result.redirect_chain == ()
    assert web.requested == [ROBOTS, ARTICLE]


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://localhost:8080/",
        "http://api.localhost/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://2130706433/",
        "http://127.1/",
        "http://0x7f000001/",
        "http://100.64.0.1/",
    ],
)
async def test_limits_a_non_public_address_is_refused_before_anything_is_sent(
    fetcher: HttpArticleFetcher, web: Web, url: str
) -> None:
    result = await fetcher.fetch(url)

    assert isinstance(result.error, NonPublicAddress)
    assert web.requested == []


async def test_limits_a_redirect_into_a_private_address_is_refused_before_it_is_requested(
    fetcher: HttpArticleFetcher, web: Web
) -> None:
    web.allow_everything()
    web.router.get(ARTICLE).respond(302, headers={"Location": "http://169.254.169.254/latest/meta-data/"})

    result = await fetcher.fetch(ARTICLE)

    assert isinstance(result.error, NonPublicAddress)
    assert result.error.host == "169.254.169.254"
    assert result.redirect_chain == (ARTICLE,)
    assert web.requested == [ROBOTS, ARTICLE]


async def test_limits_a_public_address_is_fetched(fetcher: HttpArticleFetcher, web: Web) -> None:
    web.router.get("http://93.184.215.14/robots.txt").respond(404)
    web.router.get("http://93.184.215.14/report").respond(200, content=b"ok")

    result = await fetcher.fetch("http://93.184.215.14/report")

    assert result.error is None


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        (httpx.ReadError("reset"), "ReadError"),
        (httpx.RemoteProtocolError("garbled"), "RemoteProtocolError"),
        (httpx.UnsupportedProtocol("no"), "UnsupportedProtocol"),
    ],
)
async def test_limits_any_other_transport_failure_is_a_typed_error_not_an_exception(
    build: Callable[..., HttpArticleFetcher], web: Web, failure: Exception, reason: str
) -> None:
    web.allow_everything()
    web.fail(ARTICLE, failure)

    async with build() as fetcher:
        result = await fetcher.fetch(ARTICLE)

    assert isinstance(result.error, TransportError)
    assert result.error.reason == reason
    assert web.requested.count(ARTICLE) == 1


async def test_limits_a_connection_dropped_mid_body_is_a_transport_error_with_no_partial_body(
    fetcher: HttpArticleFetcher, web: Web
) -> None:
    web.allow_everything()
    web.router.get(ARTICLE).mock(return_value=httpx.Response(200, stream=DrippingBody(5, 100, fail_after=2)))

    result = await fetcher.fetch(ARTICLE)

    assert isinstance(result.error, TransportError)
    assert result.error.reason == "ReadError"
    assert result.body == b""


# --------------------------------------------------------------------------------------------
# ac3: bounded retries, only for idempotent failures, honouring Retry-After
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("status", [429, 502, 503, 504])
async def test_retry_a_retryable_status_is_tried_again(
    fetcher: HttpArticleFetcher, web: Web, time: SimulatedTime, status: int
) -> None:
    web.allow_everything()
    web.router.get(ARTICLE).mock(side_effect=[httpx.Response(status), httpx.Response(200, content=b"ok")])

    result = await fetcher.fetch(ARTICLE)

    assert result.error is None
    assert result.body == b"ok"
    assert web.requested.count(ARTICLE) == 2
    assert time.sleeps == [1.0]


@pytest.mark.parametrize("status", [400, 401, 402, 403, 404, 408, 410, 451, 500, 501, 505])
async def test_retry_never_happens_for_any_other_error_status(
    fetcher: HttpArticleFetcher, web: Web, time: SimulatedTime, status: int
) -> None:
    web.allow_everything()
    web.router.get(ARTICLE).respond(status, headers={"Retry-After": "1"})

    result = await fetcher.fetch(ARTICLE)

    assert isinstance(result.error, HttpStatusError)
    assert (result.error.status_code, result.error.attempts) == (status, 1)
    assert web.requested.count(ARTICLE) == 1
    assert time.sleeps == []


async def test_retry_a_failed_connection_is_tried_again(
    fetcher: HttpArticleFetcher, web: Web, time: SimulatedTime
) -> None:
    web.allow_everything()
    web.fail(ARTICLE, httpx.ConnectError("refused"), httpx.ConnectTimeout("slow"))
    web.router.get(ARTICLE).respond(200, content=b"ok")

    result = await fetcher.fetch(ARTICLE)

    assert result.error is None
    assert web.requested.count(ARTICLE) == 3
    assert time.sleeps == [1.0, 2.0]


async def test_retry_a_connection_that_never_succeeds_ends_as_a_transport_error(
    fetcher: HttpArticleFetcher, web: Web
) -> None:
    web.allow_everything()
    web.fail(ARTICLE, *(httpx.ConnectError("refused") for _ in range(3)))

    result = await fetcher.fetch(ARTICLE)

    assert isinstance(result.error, TransportError)
    assert result.error.reason == "ConnectError"
    assert web.requested.count(ARTICLE) == 3


@pytest.mark.parametrize("max_retries", [0, 1, 4])
async def test_retry_attempts_are_bounded_by_max_retries(
    build: Callable[..., HttpArticleFetcher], web: Web, max_retries: int
) -> None:
    web.allow_everything()
    web.router.get(ARTICLE).respond(503, content=b"<html>down</html>")

    async with build(max_retries=max_retries) as fetcher:
        result = await fetcher.fetch(ARTICLE)

    assert web.requested.count(ARTICLE) == max_retries + 1
    assert isinstance(result.error, HttpStatusError)
    assert (result.error.status_code, result.error.attempts) == (503, max_retries + 1)
    assert result.body == b"<html>down</html>"


@pytest.mark.parametrize(
    ("jitter", "waits"), [(1.0, [1.0, 2.0, 4.0, 5.0, 5.0]), (0.0, [0.5, 1.0, 2.0, 2.5, 2.5])]
)
async def test_retry_backoff_doubles_is_jittered_into_its_upper_half_and_is_capped(
    build: Callable[..., HttpArticleFetcher], web: Web, time: SimulatedTime, jitter: float, waits: list[float]
) -> None:
    web.allow_everything()
    web.router.get(ARTICLE).respond(502)

    async with build(
        jitter=lambda: jitter, max_retries=5, backoff_base_seconds=1.0, backoff_max_seconds=5.0
    ) as fetcher:
        await fetcher.fetch(ARTICLE)

    assert time.sleeps == waits


@pytest.mark.parametrize("status", [429, 503])
async def test_retry_after_in_seconds_is_waited_out_exactly(
    build: Callable[..., HttpArticleFetcher], web: Web, time: SimulatedTime, status: int
) -> None:
    web.allow_everything()
    web.router.get(ARTICLE).mock(
        side_effect=[httpx.Response(status, headers={"Retry-After": "37"}), httpx.Response(200)]
    )

    async with build(jitter=lambda: 0.0) as fetcher:
        result = await fetcher.fetch(ARTICLE)

    assert result.error is None
    assert time.sleeps == [37.0]


async def test_retry_after_as_an_http_date_is_read_against_the_injected_clock(
    fetcher: HttpArticleFetcher, web: Web, time: SimulatedTime
) -> None:
    web.allow_everything()
    web.router.get(ARTICLE).mock(
        side_effect=[
            httpx.Response(503, headers={"Retry-After": "Wed, 21 Oct 2026 09:01:30 GMT"}),
            httpx.Response(200),
        ]
    )

    await fetcher.fetch(ARTICLE)

    assert time.sleeps == [90.0]


@pytest.mark.parametrize("status", [502, 504])
async def test_retry_after_on_a_gateway_error_is_ignored_for_the_fetchers_own_backoff(
    fetcher: HttpArticleFetcher, web: Web, time: SimulatedTime, status: int
) -> None:
    web.allow_everything()
    web.router.get(ARTICLE).mock(
        side_effect=[httpx.Response(status, headers={"Retry-After": "37"}), httpx.Response(200)]
    )

    await fetcher.fetch(ARTICLE)

    assert time.sleeps == [1.0]


async def test_retry_after_longer_than_the_ceiling_ends_the_fetch_without_sleeping(
    build: Callable[..., HttpArticleFetcher], web: Web, time: SimulatedTime
) -> None:
    web.allow_everything()
    web.router.get(ARTICLE).respond(429, headers={"Retry-After": "86400"})

    async with build(max_retry_wait_seconds=120.0) as fetcher:
        result = await fetcher.fetch(ARTICLE)

    assert isinstance(result.error, HttpStatusError)
    assert (result.error.status_code, result.error.retry_after_seconds, result.error.attempts) == (
        429,
        86400.0,
        1,
    )
    assert web.requested.count(ARTICLE) == 1
    assert time.sleeps == []


async def test_retry_after_exactly_at_the_ceiling_is_waited_out(
    build: Callable[..., HttpArticleFetcher], web: Web, time: SimulatedTime
) -> None:
    web.allow_everything()
    web.router.get(ARTICLE).mock(
        side_effect=[httpx.Response(429, headers={"Retry-After": "120"}), httpx.Response(200)]
    )

    async with build(max_retry_wait_seconds=120.0) as fetcher:
        result = await fetcher.fetch(ARTICLE)

    assert result.error is None
    assert time.sleeps == [120.0]


async def test_retry_waits_also_respect_the_per_host_interval(
    build: Callable[..., HttpArticleFetcher], web: Web, time: SimulatedTime
) -> None:
    web.allow_everything()
    web.router.get(ARTICLE).mock(side_effect=[httpx.Response(503), httpx.Response(200)])

    async with build(per_host_interval_seconds=5.0, backoff_base_seconds=1.0) as fetcher:
        await fetcher.fetch(ARTICLE)

    gaps = [
        (later - earlier).total_seconds()
        for earlier, later in zip(web.started_at, web.started_at[1:], strict=False)
    ]
    assert gaps == [5.0, 5.0]


# --------------------------------------------------------------------------------------------
# ac4: robots.txt, read through the same client, cached per origin
# --------------------------------------------------------------------------------------------


async def test_robots_a_disallowed_path_is_refused_and_never_requested(
    fetcher: HttpArticleFetcher, web: Web
) -> None:
    web.router.get(ROBOTS).respond(200, content=fixture_bytes("robots_disallow_private.txt"))
    target = web.router.get(f"{SITE}/private/memo").respond(200, content=b"secret")

    result = await fetcher.fetch(f"{SITE}/private/memo")

    assert result.access_status is AccessStatus.ROBOTS_DISALLOWED
    assert isinstance(result.error, RobotsDisallowed)
    assert result.error.reason is RobotsRefusalReason.DISALLOWED
    assert result.error.robots_url == ROBOTS
    assert not target.called
    assert web.requested == [ROBOTS]
    assert (result.status_code, result.body) == (None, b"")


async def test_robots_an_allowed_path_is_fetched(fetcher: HttpArticleFetcher, web: Web) -> None:
    web.router.get(ROBOTS).respond(200, content=fixture_bytes("robots_disallow_private.txt"))
    web.router.get(ARTICLE).respond(200, content=b"ok")

    result = await fetcher.fetch(ARTICLE)

    assert result.error is None
    assert web.requested == [ROBOTS, ARTICLE]


async def test_robots_a_group_naming_this_crawler_is_the_one_applied(
    fetcher: HttpArticleFetcher, web: Web
) -> None:
    web.router.get(ROBOTS).respond(200, content=fixture_bytes("robots_named_group.txt"))
    web.router.get(ARTICLE).respond(200, content=b"ok")
    drafts = web.router.get(f"{SITE}/drafts/x").respond(200)

    allowed = await fetcher.fetch(ARTICLE)
    refused = await fetcher.fetch(f"{SITE}/drafts/x")

    assert allowed.error is None
    assert isinstance(refused.error, RobotsDisallowed)
    assert not drafts.called


@pytest.mark.parametrize("path", ["/archive/2026/budget", "/reports/annual.pdf"])
async def test_robots_rules_the_stdlib_would_miss_still_refuse(
    fetcher: HttpArticleFetcher, web: Web, path: str
) -> None:
    web.router.get(ROBOTS).respond(200, content=fixture_bytes("robots_longest_match.txt"))
    target = web.router.get(f"{SITE}{path}").respond(200)

    result = await fetcher.fetch(f"{SITE}{path}")

    assert isinstance(result.error, RobotsDisallowed)
    assert not target.called


async def test_robots_is_read_once_per_origin_and_cached(fetcher: HttpArticleFetcher, web: Web) -> None:
    robots = web.router.get(ROBOTS).respond(200, content=fixture_bytes("robots_disallow_private.txt"))
    other_robots = web.allow_everything("https://journal.example.net")
    web.router.get(ARTICLE).respond(200)
    web.router.get(f"{SITE}/2026/10/other").respond(200)
    web.router.get("https://journal.example.net/paper").respond(200)

    await fetcher.fetch(ARTICLE)
    await fetcher.fetch(f"{SITE}/2026/10/other")
    await fetcher.fetch(f"{SITE}/private/memo")
    await fetcher.fetch("https://journal.example.net/paper")

    assert robots.call_count == 1
    assert other_robots.call_count == 1


async def test_robots_rules_are_read_again_once_they_are_24_hours_old(
    fetcher: HttpArticleFetcher, web: Web, time: SimulatedTime
) -> None:
    robots = web.router.get(ROBOTS).mock(
        side_effect=[
            httpx.Response(404),
            httpx.Response(200, content=b"User-agent: *\nDisallow: /2026/\n"),
        ]
    )
    target = web.router.get(ARTICLE).respond(200)

    first = await fetcher.fetch(ARTICLE)
    time.clock.advance(timedelta(hours=23, minutes=59, seconds=59))
    still_cached = await fetcher.fetch(ARTICLE)
    time.clock.advance(timedelta(seconds=1))
    read_again = await fetcher.fetch(ARTICLE)

    assert (first.error, still_cached.error) == (None, None)
    assert isinstance(read_again.error, RobotsDisallowed)
    assert robots.call_count == 2
    assert target.call_count == 2


async def test_robots_an_allow_list_written_disallow_first_lets_the_allowed_page_through(
    fetcher: HttpArticleFetcher, web: Web
) -> None:
    web.router.get(ROBOTS).respond(200, content=b"User-agent: *\nDisallow: /\nAllow: /2026/\n")
    web.router.get(ARTICLE).respond(200)
    other = web.router.get(f"{SITE}/drafts/x").respond(200)

    allowed = await fetcher.fetch(ARTICLE)
    refused = await fetcher.fetch(f"{SITE}/drafts/x")

    assert allowed.error is None
    assert isinstance(refused.error, RobotsDisallowed)
    assert not other.called


async def test_robots_concurrent_fetches_on_one_host_share_one_robots_request(
    fetcher: HttpArticleFetcher, web: Web
) -> None:
    robots = web.allow_everything()
    web.router.get(ARTICLE).respond(200)
    web.router.get(f"{SITE}/2026/10/other").respond(200)

    await asyncio.gather(fetcher.fetch(ARTICLE), fetcher.fetch(f"{SITE}/2026/10/other"))

    assert robots.call_count == 1


@pytest.mark.parametrize("status", [404, 410, 400])
async def test_robots_missing_robots_txt_allows_everything(
    fetcher: HttpArticleFetcher, web: Web, status: int
) -> None:
    web.router.get(ROBOTS).respond(status)
    web.router.get(ARTICLE).respond(200)

    result = await fetcher.fetch(ARTICLE)

    assert result.error is None


@pytest.mark.parametrize("status", [401, 403])
async def test_robots_access_denied_to_robots_txt_refuses_everything(
    fetcher: HttpArticleFetcher, web: Web, status: int
) -> None:
    web.router.get(ROBOTS).respond(status)
    target = web.router.get(ARTICLE).respond(200)

    result = await fetcher.fetch(ARTICLE)

    assert isinstance(result.error, RobotsDisallowed)
    assert result.error.reason is RobotsRefusalReason.ROBOTS_ACCESS_DENIED
    assert not target.called


@pytest.mark.parametrize("status", [500, 503, 429])
async def test_robots_an_unreachable_robots_txt_refuses_everything_after_its_retries(
    build: Callable[..., HttpArticleFetcher], web: Web, status: int
) -> None:
    robots = web.router.get(ROBOTS).respond(status)
    target = web.router.get(ARTICLE).respond(200)

    async with build(max_retries=1) as fetcher:
        result = await fetcher.fetch(ARTICLE)

    assert isinstance(result.error, RobotsDisallowed)
    assert result.error.reason is RobotsRefusalReason.ROBOTS_UNREACHABLE
    assert result.access_status is AccessStatus.ROBOTS_DISALLOWED
    assert robots.call_count == (2 if status in (429, 503) else 1)
    assert not target.called


@pytest.mark.parametrize(
    "failure",
    [httpx.ConnectError("refused"), httpx.ReadTimeout("slow"), httpx.RemoteProtocolError("garbled")],
)
async def test_robots_a_robots_txt_that_cannot_be_read_refuses_everything(
    build: Callable[..., HttpArticleFetcher], web: Web, failure: Exception
) -> None:
    web.fail(ROBOTS, failure)
    target = web.router.get(ARTICLE).respond(200)

    async with build(max_retries=0) as fetcher:
        result = await fetcher.fetch(ARTICLE)

    assert isinstance(result.error, RobotsDisallowed)
    assert result.error.reason is RobotsRefusalReason.ROBOTS_UNREACHABLE
    assert not target.called


async def test_robots_a_robots_txt_redirect_is_followed(fetcher: HttpArticleFetcher, web: Web) -> None:
    web.router.get(ROBOTS).respond(301, headers={"Location": "https://www.example.org/robots.txt"})
    web.router.get("https://www.example.org/robots.txt").respond(
        200, content=fixture_bytes("robots_disallow_private.txt")
    )
    target = web.router.get(f"{SITE}/private/memo").respond(200)

    result = await fetcher.fetch(f"{SITE}/private/memo")

    assert isinstance(result.error, RobotsDisallowed)
    assert not target.called


async def test_robots_a_robots_txt_redirecting_in_a_loop_is_unreachable(
    fetcher: HttpArticleFetcher, web: Web
) -> None:
    web.router.get(ROBOTS).respond(302, headers={"Location": "/robots.txt"})
    target = web.router.get(ARTICLE).respond(200)

    result = await fetcher.fetch(ARTICLE)

    assert isinstance(result.error, RobotsDisallowed)
    assert result.error.reason is RobotsRefusalReason.ROBOTS_UNREACHABLE
    assert not target.called


async def test_robots_each_redirect_hop_is_checked_against_its_own_hosts_robots_txt(
    fetcher: HttpArticleFetcher, web: Web
) -> None:
    web.allow_everything()
    web.router.get(ARTICLE).respond(302, headers={"Location": "https://mirror.example.com/private/memo"})
    web.router.get("https://mirror.example.com/robots.txt").respond(
        200, content=fixture_bytes("robots_disallow_private.txt")
    )
    hop = web.router.get("https://mirror.example.com/private/memo").respond(200)

    result = await fetcher.fetch(ARTICLE)

    assert isinstance(result.error, RobotsDisallowed)
    assert result.error.url == "https://mirror.example.com/private/memo"
    assert result.final_url == "https://mirror.example.com/private/memo"
    assert result.redirect_chain == (ARTICLE,)
    assert not hop.called


async def test_robots_a_robots_txt_past_500_kib_is_read_up_to_its_last_whole_line(
    fetcher: HttpArticleFetcher, web: Web
) -> None:
    rules = b"User-agent: *\nDisallow: /private/\n"
    padding = b"# padding\n" * (600 * 1024 // 10)
    web.router.get(ROBOTS).mock(
        return_value=httpx.Response(200, stream=_once(rules + padding + b"Disallow: /\n"))
    )
    web.router.get(ARTICLE).respond(200)

    allowed = await fetcher.fetch(ARTICLE)
    refused = await fetcher.fetch(f"{SITE}/private/memo")

    assert allowed.error is None  # the final "Disallow: /" lies past the cut
    assert isinstance(refused.error, RobotsDisallowed)


# --------------------------------------------------------------------------------------------
# ac5: per-host spacing and an identifying User-Agent
# --------------------------------------------------------------------------------------------


async def test_rate_limit_spaces_every_request_to_one_host_by_the_interval(
    build: Callable[..., HttpArticleFetcher], web: Web, time: SimulatedTime
) -> None:
    web.allow_everything()
    web.router.get(ARTICLE).respond(200)
    web.router.get(f"{SITE}/2026/10/other").respond(200)

    async with build(per_host_interval_seconds=2.5) as fetcher:
        await fetcher.fetch(ARTICLE)
        await fetcher.fetch(f"{SITE}/2026/10/other")

    assert [time.seconds_since_start(moment) for moment in web.started_at] == [0.0, 2.5, 5.0]
    assert time.sleeps == [2.5, 2.5]


async def test_rate_limit_counts_time_already_spent_since_the_last_request(
    build: Callable[..., HttpArticleFetcher], web: Web, time: SimulatedTime
) -> None:
    web.latency = timedelta(seconds=1)
    web.allow_everything()
    web.router.get(ARTICLE).respond(200)

    async with build(per_host_interval_seconds=2.5) as fetcher:
        await fetcher.fetch(ARTICLE)

    assert time.sleeps == [1.5]


async def test_rate_limit_does_not_hold_requests_to_another_host(
    build: Callable[..., HttpArticleFetcher], web: Web, time: SimulatedTime
) -> None:
    other = "https://journal.example.net"
    web.allow_everything()
    web.allow_everything(other)
    web.router.get(ARTICLE).respond(200)
    web.router.get(f"{other}/paper").respond(200)

    async with build(per_host_interval_seconds=10.0) as fetcher:
        await fetcher.fetch(ARTICLE)
        clock_before = time.clock.now()
        await fetcher.fetch(f"{other}/paper")

    assert web.started_at[2] == clock_before  # robots.txt on the other host went straight out


async def test_rate_limit_applies_to_each_redirect_hop(
    build: Callable[..., HttpArticleFetcher], web: Web, time: SimulatedTime
) -> None:
    web.allow_everything()
    web.router.get(f"{SITE}/short").respond(301, headers={"Location": "/2026/10/grid-storage"})
    web.router.get(ARTICLE).respond(200)

    async with build(per_host_interval_seconds=3.0) as fetcher:
        await fetcher.fetch(f"{SITE}/short")

    assert [time.seconds_since_start(moment) for moment in web.started_at] == [0.0, 3.0, 6.0]


async def test_rate_limit_interval_of_zero_never_sleeps(
    fetcher: HttpArticleFetcher, web: Web, time: SimulatedTime
) -> None:
    web.allow_everything()
    web.router.get(ARTICLE).respond(200)

    await fetcher.fetch(ARTICLE)
    await fetcher.fetch(ARTICLE)

    assert time.sleeps == []


async def test_rate_limiter_lets_concurrent_requests_to_one_host_out_one_interval_apart(
    time: SimulatedTime,
) -> None:
    limiter = HostRateLimiter(4.0, clock=time.clock, sleep=time.sleep)
    starts: list[float] = []

    async def take_turn() -> None:
        await limiter.wait_turn("News.Example.org")
        starts.append(time.seconds_since_start(time.clock.now()))

    await asyncio.gather(take_turn(), take_turn(), take_turn())

    assert starts == [0.0, 4.0, 8.0]


async def test_every_request_including_robots_and_redirects_sends_the_identifying_user_agent(
    fetcher: HttpArticleFetcher, web: Web
) -> None:
    web.allow_everything()
    web.router.get(f"{SITE}/short").respond(301, headers={"Location": "/2026/10/grid-storage"})
    web.router.get(ARTICLE).mock(side_effect=[httpx.Response(503), httpx.Response(200)])

    await fetcher.fetch(f"{SITE}/short")

    assert len(web.requests) == 4
    assert {request.headers["User-Agent"] for request in web.requests} == {USER_AGENT}
    assert CONTACT in USER_AGENT


async def test_robots_rules_are_matched_against_the_product_token_from_settings(
    build: Callable[..., HttpArticleFetcher], web: Web
) -> None:
    web.router.get(ROBOTS).respond(200, content=b"User-agent: classroom-bot\nDisallow: /\n")
    target = web.router.get(ARTICLE).respond(200)

    async with build(user_agent_product="classroom-bot") as fetcher:
        result = await fetcher.fetch(ARTICLE)

    assert isinstance(result.error, RobotsDisallowed)
    assert not target.called
    assert web.requests[0].headers["User-Agent"].startswith("classroom-bot/")


# --------------------------------------------------------------------------------------------
# Nothing to bypass with, and nothing to leak
# --------------------------------------------------------------------------------------------


async def test_requests_carry_no_cookie_and_no_credentials_even_after_a_set_cookie(
    fetcher: HttpArticleFetcher, web: Web
) -> None:
    web.router.get(ROBOTS).respond(404, headers={"Set-Cookie": "session=abc; Path=/"})
    web.router.get(ARTICLE).respond(200, headers={"Set-Cookie": "meter=1; Path=/"})

    await fetcher.fetch(ARTICLE)
    await fetcher.fetch(ARTICLE)

    for request in web.requests:
        assert "cookie" not in request.headers
        assert "authorization" not in request.headers


@pytest.fixture
def bare_http_client_loggers() -> Iterator[None]:
    """httpx's and httpcore's loggers start with no filters, and get theirs back afterwards.

    Their filters are shared by the whole process: OpenCaselist's `install_redaction` adds one that
    strips every query string, and if a test that ran earlier in this worker left it there, it
    would hide a leak from the test below (PM note, 2026-10-21, from v1-e07-t01's CI).
    """
    saved = {name: list(logging.getLogger(name).filters) for name in HTTP_CLIENT_LOGGERS}
    for name in HTTP_CLIENT_LOGGERS:
        logging.getLogger(name).filters.clear()
    yield
    for name, filters in saved.items():
        logging.getLogger(name).filters[:] = filters


@pytest.mark.usefixtures("bare_http_client_loggers")
async def test_no_url_path_or_query_reaches_a_log_an_error_or_the_repr(
    build: Callable[..., HttpArticleFetcher], web: Web, caplog: pytest.LogCaptureFixture
) -> None:
    token = f"signed-{secrets.token_hex(12)}"
    path_secret = f"share-{secrets.token_hex(12)}"
    caplog.set_level(logging.DEBUG)
    web.router.get(ROBOTS).respond(200, content=b"User-agent: *\nDisallow: /private/\n")
    web.router.get(f"{SITE}/{path_secret}/a?token={token}").mock(
        side_effect=[httpx.Response(503), httpx.Response(404)]
    )
    web.fail(
        f"{SITE}/{path_secret}/b?token={token}", *(httpx.ConnectError(f"refused {token}") for _ in range(2))
    )

    async with build(max_retries=1) as fetcher:
        results = [
            await fetcher.fetch(f"{SITE}/{path_secret}/a?token={token}"),
            await fetcher.fetch(f"{SITE}/{path_secret}/b?token={token}"),
            await fetcher.fetch(f"{SITE}/private/{path_secret}?token={token}"),
        ]
        shown = repr(fetcher)

    messages = [result.error.message for result in results if result.error is not None]
    assert len(messages) == 3
    assert "HTTP Request: GET https://news.example.org " in caplog.text  # httpx's line, cut to the origin
    for text in [*messages, caplog.text, shown]:
        assert token not in text
        assert path_secret not in text


@pytest.mark.usefixtures("bare_http_client_loggers")
async def test_the_log_filter_leaves_other_clients_httpx_lines_alone(
    fetcher: HttpArticleFetcher, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="httpx")
    assert sum(isinstance(found, RequestUrlLogFilter) for found in logging.getLogger("httpx").filters) == 1

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200))) as other:
        await other.get("https://api.example.org/v1/works?page=2")

    assert "https://api.example.org/v1/works?page=2" in caplog.text


async def test_the_fetcher_never_raises_for_a_url_it_cannot_reach(
    fetcher: HttpArticleFetcher, web: Web
) -> None:
    web.allow_everything()
    web.fail(ARTICLE, *(httpx.ConnectError("refused") for _ in range(3)))

    result = await fetcher.fetch(ARTICLE)

    assert isinstance(result, FetchResult)


def _once(body: bytes) -> httpx.AsyncByteStream:
    class Once(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            for start in range(0, len(body), 64 * 1024):
                yield body[start : start + 64 * 1024]

    return Once()
