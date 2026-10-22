"""The polite HTTP fetcher behind the ArticleFetcher port (v1-e04-t02).

:class:`HttpArticleFetcher` retrieves the bytes at a URL for ArticleService (v1-e04-t05) and
returns a :class:`~debate_core.retrieval.fetch_types.FetchResult` every time: a refusal, a timeout or
an error status is a result carrying a :data:`~debate_core.retrieval.fetch_types.FetchError`, never
an exception out of httpx. It owns transport only. Whether a 200 is a paywall is the access
classifier's question (v1-e04-t03), and the text is the extractor's (v1-e04-t04).

**The URL is fetched as given.** Its canonical form (`debate_core.retrieval.canonical_url`) is an
identity key, never a fetch target (PM amendment from v1-e04-t01's review): nothing here
canonicalizes, upgrades http to https, or adds `www.`.

**Every request, and every redirect hop, goes through the same four gates, in order:**

1. *A public address.* A host that is a loopback, private, link-local or reserved literal address,
   or `localhost`, is refused with `NonPublicAddress` before anything is sent. Without this a public
   page could redirect the fetcher to `http://169.254.169.254/` or a router's admin page and have
   the answer stored as a source.
2. *robots.txt.* The rules for the hop's origin are read once and cached for the fetcher's lifetime
   (:class:`~debate_core.retrieval.robots_rules.RobotsRules` documents what each answer means). A
   refusal is `RobotsDisallowed`, recorded as `ROBOTS_DISALLOWED`, and nothing is requested from the
   URL it refused.
3. *The per-host interval.* :class:`HostRateLimiter` spaces the starts of any two requests to one
   host by `http.per_host_interval_seconds`, robots.txt requests and retries included.
4. *Bounded retries.* A failed connection and a 429, 502, 503 or 504 are retried, up to
   `http.max_retries` times. A 429 or 503 that says `Retry-After` is waited out exactly, unless it
   asks for more than `http.max_retry_wait_seconds`, in which case the fetch ends with that answer.
   Otherwise the wait is exponential from `http.backoff_base_seconds`, jittered, and never more than
   `http.backoff_max_seconds`. Nothing else is retried: a 404 or a 403 is an answer, and a read
   timeout means the server already had the request.

A redirect is followed by hand, never by httpx, so that each hop passes the gates. It counts against
`http.max_redirects`, and a hop to anything but http or https is `UnsupportedScheme`.

**Limits.** `http.connect_timeout_seconds` bounds connecting; `http.request_timeout_seconds` bounds
each read and, checked against the injected clock as the body streams, one request from sending to
its last byte. The body is streamed and abandoned with `TooLarge` the moment it passes
`http.max_response_bytes` (or at once, when `Content-Length` declares more), so no more than the
limit and one chunk is ever held.

**Nothing to bypass with.** The client keeps no cookies (its jar refuses every domain) and does not
read the environment (`trust_env=False`), so a `~/.netrc` login or a proxy set for something else
is never used. It sends one header of its own, the identifying User-Agent from settings,
`debate-research/<version> (+<contact_url>)`, and nothing that impersonates a browser.

**Time is injected.** The :class:`~debate_core.application.ports.providers.Clock` stamps
`fetched_at` and measures every interval, and `sleep` is the only way the fetcher waits, so a test
drives backoff and spacing with a fake clock and never really sleeps.

**What it says about a URL.** Log lines and error messages name the host, never the path or query,
which can carry a signed token or an email address. httpx logs every request's full URL at INFO on
its own logger, so :class:`RequestUrlLogFilter` cuts the fetcher's records there down to the
origin. It acts only while the fetcher is sending (a context variable says so), so another
adapter's httpx lines, and whatever filters it installs, are left exactly as they were.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import random
import re
import socket
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import datetime
from http.cookiejar import CookieJar, DefaultCookiePolicy
from types import TracebackType
from typing import Final, Self
from urllib.parse import urlsplit

import httpx

from debate_core.application.ports.providers import Clock
from debate_core.application.settings import HttpSettings
from debate_core.domain import AccessStatus
from debate_core.integrations.discovery.http_failures import retry_after_seconds
from debate_core.retrieval.content_sniffing import sniff_content_type
from debate_core.retrieval.fetch_types import (
    FetchError,
    FetchErrorBase,
    FetchResult,
    HttpStatusError,
    NonPublicAddress,
    RobotsDisallowed,
    Timeout,
    TimeoutPhase,
    TooLarge,
    TooManyRedirects,
    TransportError,
    UnsupportedScheme,
)
from debate_core.retrieval.robots_rules import ROBOTS_MAX_BYTES, RobotsRules

__all__ = [
    "HTTP_CLIENT_LOGGERS",
    "REDIRECT_STATUSES",
    "RETRYABLE_STATUSES",
    "RETRY_AFTER_STATUSES",
    "HostRateLimiter",
    "HttpArticleFetcher",
    "RequestUrlLogFilter",
    "Sleep",
    "install_request_url_filter",
]

logger = logging.getLogger(__name__)

HTTP_CLIENT_LOGGERS: Final = (
    "httpx",
    "httpcore",
    "httpcore.connection",
    "httpcore.http11",
    "httpcore.http2",
    "httpcore.proxy",
)
"""The loggers httpx and httpcore write request details to. A filter sees only records logged on its
own logger, not its children's, so httpcore's are named one by one."""

_SENDING: ContextVar[bool] = ContextVar("debate_core_http_fetcher_sending", default=False)
"""True inside the fetcher's own request, so the log filter touches nothing else."""

_URL_TAIL: Final = re.compile(r"(https?://[^/\s\"'?#]+)[^\s\"']*")
"""A URL, with its origin as group 1 and everything after it (path, query, fragment) matched."""

type Sleep = Callable[[float], Awaitable[None]]
"""Waits the given number of seconds. `asyncio.sleep` in production; a clock-advancing fake in tests."""

RETRYABLE_STATUSES: Final = frozenset({429, 502, 503, 504})
"""Statuses that say "not now" rather than "no": retried, up to `http.max_retries` times."""

RETRY_AFTER_STATUSES: Final = frozenset({429, 503})
"""Statuses whose `Retry-After` is waited out instead of the fetcher's own backoff (RFC 9110 §10.2.3)."""

REDIRECT_STATUSES: Final = frozenset({301, 302, 303, 307, 308})
"""Statuses followed to their `Location`, each hop a new request."""

_HTTP_SCHEMES: Final = frozenset({"http", "https"})

_SET_ASIDE_LOCATION: Final = "debate_core.redirect_location"
"""Response extension the redirect `Location` is moved to; see :func:`_set_location_aside`."""


class RequestUrlLogFilter(logging.Filter):
    """Cuts every URL in a record logged during the fetcher's own request down to its origin.

    Outside a request it passes records through untouched. One shared instance is attached to the
    httpx and httpcore loggers by :func:`install_request_url_filter`.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if _SENDING.get():
            record.msg = _URL_TAIL.sub(r"\1", record.getMessage())
            record.args = ()
        return True


_REQUEST_URL_FILTER: Final = RequestUrlLogFilter()


def install_request_url_filter() -> None:
    """Attach the shared :class:`RequestUrlLogFilter` to each httpx and httpcore logger, once."""
    for name in HTTP_CLIENT_LOGGERS:
        target = logging.getLogger(name)
        if not any(isinstance(existing, RequestUrlLogFilter) for existing in target.filters):
            target.addFilter(_REQUEST_URL_FILTER)


class HostRateLimiter:
    """Spaces the starts of any two requests to one host by at least `interval_seconds`.

    One lock per host, so requests to different hosts never wait for each other, and concurrent
    requests to one host take their turns in order. Hosts are compared lower-cased and without a
    port: two ports on one host are one server to be polite to.
    """

    def __init__(self, interval_seconds: float, *, clock: Clock, sleep: Sleep) -> None:
        self._interval = interval_seconds
        self._clock = clock
        self._sleep = sleep
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_start: dict[str, datetime] = {}

    async def wait_turn(self, host: str) -> None:
        """Return once a request to `host` may start, and record that it did."""
        key = host.lower()
        async with self._locks.setdefault(key, asyncio.Lock()):
            last = self._last_start.get(key)
            if last is not None:
                wait = self._interval - (self._clock.now() - last).total_seconds()
                if wait > 0:
                    await self._sleep(wait)
            self._last_start[key] = self._clock.now()


@dataclass(frozen=True, slots=True)
class _Answer:
    """A response that arrived whole: a redirect (no body read), or any other status with its body."""

    url: str
    status_code: int
    headers: dict[str, str]
    body: bytes
    retry_after: float | None
    location: str | None
    attempts: int = 1


@dataclass(frozen=True, slots=True)
class _ConnectFailed:
    """A connection that could not be made: retried, and `error` if the retries run out."""

    error: FetchError


class HttpArticleFetcher:
    """Retrieves the bytes behind a URL, politely; implements the ArticleFetcher port.

    Owns one `httpx.AsyncClient`; close it with :meth:`aclose`, or use the fetcher as an async
    context manager. `transport` is for tests, which pass a mock; production leaves it `None`.
    """

    def __init__(
        self,
        settings: HttpSettings,
        *,
        version: str,
        clock: Clock,
        sleep: Sleep = asyncio.sleep,
        jitter: Callable[[], float] = random.random,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._user_agent = settings.user_agent(version)
        self._clock = clock
        self._sleep = sleep
        self._jitter = jitter
        self._limiter = HostRateLimiter(settings.per_host_interval_seconds, clock=clock, sleep=sleep)
        self._robots: dict[tuple[str, str, int], RobotsRules] = {}
        self._robots_locks: dict[tuple[str, str, int], asyncio.Lock] = {}
        install_request_url_filter()
        self._client = httpx.AsyncClient(
            headers={"User-Agent": self._user_agent},
            timeout=httpx.Timeout(settings.request_timeout_seconds, connect=settings.connect_timeout_seconds),
            follow_redirects=False,
            cookies=CookieJar(policy=DefaultCookiePolicy(allowed_domains=[])),
            trust_env=False,
            transport=transport,
            event_hooks={"response": [_set_location_aside]},
        )

    def __repr__(self) -> str:
        return f"{type(self).__name__}(user_agent={self._user_agent!r})"

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the HTTP client and its connections."""
        await self._client.aclose()

    async def fetch(self, url: str) -> FetchResult:
        """Retrieve `url`, exactly as given, through every gate in the module docstring."""
        started = self._clock.now()
        outcome, final_url, chain = await self._follow(url, for_robots=False)
        fetched_at = self._clock.now()
        elapsed_ms = max((fetched_at - started).total_seconds() * 1000, 0.0)
        if isinstance(outcome, FetchErrorBase):
            logger.info("Fetch from %s ended with %s", _host(final_url), outcome.kind)
            return FetchResult(
                requested_url=url,
                final_url=final_url,
                redirect_chain=tuple(chain),
                elapsed_ms=elapsed_ms,
                fetched_at=fetched_at,
                access_status=(
                    AccessStatus.ROBOTS_DISALLOWED
                    if isinstance(outcome, RobotsDisallowed)
                    else AccessStatus.UNKNOWN
                ),
                error=outcome,
            )
        status_error = None
        if outcome.status_code >= 400:
            status_error = HttpStatusError(
                url=outcome.url,
                message=f"{_host(outcome.url)} answered HTTP {outcome.status_code}",
                status_code=outcome.status_code,
                retry_after_seconds=outcome.retry_after,
                attempts=outcome.attempts,
            )
        return FetchResult(
            requested_url=url,
            final_url=outcome.url,
            status_code=outcome.status_code,
            headers=outcome.headers,
            content_type=outcome.headers.get("content-type") or None,
            sniffed_content_type=sniff_content_type(outcome.body),
            body=outcome.body,
            redirect_chain=tuple(chain),
            elapsed_ms=elapsed_ms,
            fetched_at=fetched_at,
            error=status_error,
        )

    # ----------------------------------------------------------------------------------------
    # Redirects: every hop through every gate
    # ----------------------------------------------------------------------------------------

    async def _follow(self, url: str, *, for_robots: bool) -> tuple[_Answer | FetchError, str, list[str]]:
        """Request `url` and each redirect after it; the outcome, the last URL tried, and the hops before it.

        robots.txt is fetched with `for_robots=True`: its own hops are not checked against robots
        rules (that would ask robots.txt about itself), and a body past the limit is cut rather than
        refused, since RFC 9309 lets a crawler ignore the rest.
        """
        chain: list[str] = []
        current = url
        while True:
            refused = _non_public_host(current)
            if refused is not None:
                return (
                    NonPublicAddress(
                        url=current,
                        message=f"{refused} is not a public address; the fetcher does not request it",
                        host=refused,
                    ),
                    current,
                    chain,
                )
            if not for_robots:
                robots_refusal = await self._robots_refusal(current)
                if robots_refusal is not None:
                    return robots_refusal, current, chain
            limit = ROBOTS_MAX_BYTES if for_robots else self._settings.max_response_bytes
            outcome = await self._send(current, body_limit=limit, cut_at_limit=for_robots)
            if isinstance(outcome, FetchErrorBase) or outcome.location is None:
                return outcome, current, chain
            target, scheme = _redirect_target(current, outcome.location)
            if target is None:
                return (
                    UnsupportedScheme(
                        url=current,
                        message=f"{_host(current)} redirected to a {scheme or 'scheme-less'} URL",
                        scheme=scheme,
                    ),
                    current,
                    chain,
                )
            chain.append(current)
            if len(chain) > self._settings.max_redirects:
                return (
                    TooManyRedirects(
                        url=current,
                        message=(
                            f"{_host(url)} redirected more than {self._settings.max_redirects} times; "
                            "the last redirect was not followed"
                        ),
                        limit=self._settings.max_redirects,
                        redirect_chain=tuple(chain),
                    ),
                    current,
                    chain[:-1],
                )
            current = target

    # ----------------------------------------------------------------------------------------
    # robots.txt
    # ----------------------------------------------------------------------------------------

    async def _robots_refusal(self, url: str) -> RobotsDisallowed | None:
        """The refusal robots.txt makes for `url`, reading and caching its origin's rules first."""
        parsed = httpx.URL(url)
        key = (parsed.scheme, parsed.host, parsed.port or (443 if parsed.scheme == "https" else 80))
        robots_url = str(
            httpx.URL(scheme=parsed.scheme, host=parsed.host, port=parsed.port, path="/robots.txt")
        )
        async with self._robots_locks.setdefault(key, asyncio.Lock()):
            rules = self._robots.get(key)
            if rules is None:
                rules = await self._read_robots(robots_url)
                self._robots[key] = rules
        reason = rules.refusal_for(
            url, user_agent=self._user_agent, product_token=self._settings.user_agent_product
        )
        if reason is None:
            return None
        logger.info("robots.txt on %s refuses a URL (%s)", parsed.host, reason.value)
        return RobotsDisallowed(
            url=url,
            message=f"robots.txt on {parsed.host} refuses this URL ({reason.value})",
            robots_url=robots_url,
            reason=reason,
        )

    async def _read_robots(self, robots_url: str) -> RobotsRules:
        outcome, _, _ = await self._follow(robots_url, for_robots=True)
        if isinstance(outcome, FetchErrorBase):
            return RobotsRules.unreachable()
        return RobotsRules.from_response(outcome.status_code, outcome.body)

    # ----------------------------------------------------------------------------------------
    # One URL: spacing and retries
    # ----------------------------------------------------------------------------------------

    async def _send(self, url: str, *, body_limit: int, cut_at_limit: bool) -> _Answer | FetchError:
        """Request `url` until it answers for good: spaced per host, retried within the bounds."""
        host = _host(url)
        attempts = 0
        while True:
            attempts += 1
            await self._limiter.wait_turn(host)
            outcome = await self._attempt(url, body_limit=body_limit, cut_at_limit=cut_at_limit)
            wait = self._retry_wait(outcome, attempts)
            if wait is None:
                if isinstance(outcome, _ConnectFailed):
                    return outcome.error
                if isinstance(outcome, _Answer):
                    return replace(outcome, attempts=attempts)
                return outcome
            logger.info("Retrying %s in %.1fs (attempt %d)", host, wait, attempts + 1)
            await self._sleep(wait)

    def _retry_wait(self, outcome: _Answer | _ConnectFailed | FetchError, attempts: int) -> float | None:
        """How long to wait before trying again, or `None` when `outcome` is final."""
        if attempts > self._settings.max_retries:
            return None
        if isinstance(outcome, _ConnectFailed):
            return self._backoff(attempts)
        if not isinstance(outcome, _Answer) or outcome.status_code not in RETRYABLE_STATUSES:
            return None
        if outcome.status_code in RETRY_AFTER_STATUSES and outcome.retry_after is not None:
            if outcome.retry_after > self._settings.max_retry_wait_seconds:
                return None
            return outcome.retry_after
        return self._backoff(attempts)

    def _backoff(self, attempts: int) -> float:
        """Exponential from the base, capped, then jittered into the upper half: in [cap/2, cap]."""
        ceiling = min(
            self._settings.backoff_max_seconds, self._settings.backoff_base_seconds * 2 ** (attempts - 1)
        )
        return ceiling * (0.5 + 0.5 * self._jitter())

    # ----------------------------------------------------------------------------------------
    # One request
    # ----------------------------------------------------------------------------------------

    async def _attempt(
        self, url: str, *, body_limit: int, cut_at_limit: bool
    ) -> _Answer | _ConnectFailed | FetchError:
        """One request and, unless it is a redirect, its body: translated, never raising httpx's errors."""
        sending = _SENDING.set(True)
        try:
            return await self._attempt_marked(url, body_limit=body_limit, cut_at_limit=cut_at_limit)
        finally:
            _SENDING.reset(sending)

    async def _attempt_marked(
        self, url: str, *, body_limit: int, cut_at_limit: bool
    ) -> _Answer | _ConnectFailed | FetchError:
        started = self._clock.now()
        host = _host(url)
        logger.debug("GET %s", host)
        try:
            response = await self._client.send(self._client.build_request("GET", url), stream=True)
        except (httpx.ConnectTimeout, httpx.PoolTimeout):
            return _ConnectFailed(self._timeout(url, TimeoutPhase.CONNECT))
        except httpx.ConnectError:
            return _ConnectFailed(_transport_error(url, "ConnectError"))
        except httpx.TimeoutException:
            return self._timeout(url, TimeoutPhase.READ)
        except (httpx.HTTPError, httpx.InvalidURL, httpx.StreamError) as failure:
            return _transport_error(url, type(failure).__name__)
        try:
            headers = {name.lower(): value for name, value in response.headers.items()}
            retry_after = retry_after_seconds(headers.get("retry-after"), now=self._clock.now())
            logger.debug("%s answered HTTP %d", host, response.status_code)
            location = response.extensions.get(_SET_ASIDE_LOCATION)
            if isinstance(location, str):
                headers["location"] = location
                return _Answer(url, response.status_code, headers, b"", retry_after, location)
            body = await self._read_body(response, url, started, body_limit, cut_at_limit, headers)
            if isinstance(body, FetchErrorBase):
                return body
            return _Answer(url, response.status_code, headers, body, retry_after, None)
        finally:
            await response.aclose()

    async def _read_body(
        self,
        response: httpx.Response,
        url: str,
        started: datetime,
        limit: int,
        cut_at_limit: bool,
        headers: dict[str, str],
    ) -> bytes | FetchError:
        """The decoded body, streamed and abandoned the moment it passes `limit` or the deadline."""
        declared = _content_length(headers)
        if declared is not None and declared > limit and not cut_at_limit:
            return self._too_large(url, declared=declared, received=0)
        received = bytearray()
        deadline = self._settings.request_timeout_seconds
        try:
            async for chunk in response.aiter_bytes():
                received += chunk
                if len(received) > limit:
                    if cut_at_limit:
                        break
                    return self._too_large(url, declared=declared, received=len(received))
                if (self._clock.now() - started).total_seconds() > deadline:
                    return self._timeout(url, TimeoutPhase.TOTAL)
        except httpx.TimeoutException:
            return self._timeout(url, TimeoutPhase.READ)
        except (httpx.HTTPError, httpx.StreamError) as failure:
            return _transport_error(url, type(failure).__name__)
        return bytes(received)

    def _timeout(self, url: str, phase: TimeoutPhase) -> Timeout:
        limit = (
            self._settings.connect_timeout_seconds
            if phase is TimeoutPhase.CONNECT
            else self._settings.request_timeout_seconds
        )
        return Timeout(
            url=url,
            message=f"{_host(url)} did not answer within {limit:g}s ({phase.value})",
            phase=phase,
            limit_seconds=limit,
        )

    def _too_large(self, url: str, *, declared: int | None, received: int) -> TooLarge:
        limit = self._settings.max_response_bytes
        return TooLarge(
            url=url,
            message=f"{_host(url)} sent a body larger than the {limit}-byte limit; it was not kept",
            limit_bytes=limit,
            declared_bytes=declared,
            received_bytes=received,
        )


async def _set_location_aside(response: httpx.Response) -> None:
    """Move a redirect's `Location` out of httpx's sight, into a response extension.

    With `follow_redirects=False` httpx still builds the request a redirect would make, inside
    `send`, and raises on a `Location` it cannot turn into one (`javascript:alert(1)`), before the
    fetcher has seen the status. Without the header, httpx returns the response as it is, and the
    fetcher judges the target itself (:func:`_redirect_target`), as `UnsupportedScheme` when need be.
    """
    if response.status_code in REDIRECT_STATUSES and "location" in response.headers:
        response.extensions[_SET_ASIDE_LOCATION] = response.headers["location"]
        del response.headers["location"]


def _transport_error(url: str, reason: str) -> TransportError:
    return TransportError(url=url, message=f"the connection to {_host(url)} failed ({reason})", reason=reason)


def _host(url: str) -> str:
    """The URL's host, lower-cased, for spacing, logs and messages; never its path or query."""
    return urlsplit(url).hostname or "an unnamed host"


def _content_length(headers: dict[str, str]) -> int | None:
    value = headers.get("content-length", "").strip()
    return int(value) if value.isdigit() else None


def _redirect_target(current: str, location: str) -> tuple[str | None, str]:
    """The absolute URL a `Location` names and its scheme; `None` for the URL unless http or https."""
    try:
        target = httpx.URL(current).join(location.strip())
    except httpx.InvalidURL:
        return None, ""
    scheme = target.scheme.lower()
    if scheme not in _HTTP_SCHEMES or not target.host:
        return None, scheme
    return str(target), scheme


def _non_public_host(url: str) -> str | None:
    """The host, when it is `localhost` or a literal address outside the public internet; else None.

    `socket.inet_aton` is a parser, not a lookup: it reads the legacy spellings an OS resolver also
    accepts (`127.1`, `0x7f000001`, `2130706433`), which `ipaddress` alone would take for names.
    """
    host = urlsplit(url).hostname
    if host is None:
        return None
    if host == "localhost" or host.endswith(".localhost"):
        return host
    try:
        address: ipaddress.IPv4Address | ipaddress.IPv6Address = ipaddress.ip_address(host)
    except ValueError:
        try:
            address = ipaddress.IPv4Address(socket.inet_aton(host))
        except OSError:
            return None
    return None if address.is_global else host
