"""The shared base every OpenCaselist resource module sends through: auth, pacing, backoff, errors.

A resource module (`caselists`, `downloads`, `openev`, `auth`, and in V3 `schools`, `teams`,
`rounds`, `cites` — v3-e24-t02) says *what* to ask for. This module decides *how*, identically for
all of them, so a new endpoint cannot forget a rule:

* **One request at a time.** A lock is held across every attempt, including a whole streamed
  download; nothing here runs two requests concurrently (policy E34 gate 4).
* **Paced.** :class:`~debate_core.integrations.opencaselist.pacing.RequestPacer` spaces every
  request start and counts every download attempt against the maintainer's per-minute limit.
* **Authenticated only where it belongs.** The `caselist_token` cookie is attached per request, and
  only to requests for the API's own host. Archives are served from the site's object store at
  another host, and those requests carry no cookie at all. httpx's cookie jar is cleared after every
  response, so a `Set-Cookie` from `/login` is never replayed anywhere by accident, and redirects are
  not followed, so a cookie cannot be carried to wherever a redirect points.
* **Bounded backoff.** 429, 502, 503 and 504, and connection-level failures, are retried up to
  `caselist.max_attempts` attempts in total. A `Retry-After` is honoured exactly; without one the
  wait doubles from `caselist.backoff_base_seconds`. A `Retry-After` longer than
  `caselist.max_retry_wait_seconds` is not slept on: it is reported at once, because a client that
  sits silent for a day is indistinguishable from one that has hung.
* **401 and 403 stop everything.** From the API host they are
  :class:`~debate_core.application.ports.caselist_source.CaselistAuthExpired` after exactly one
  request, never retried (policy E34 gate 5 and prohibited use 4).
* **Typed errors, scrubbed.** Every httpx exception is translated at this edge into the port's
  errors and raised `from None`: httpx's own messages quote the request URL, and the URL of a
  `/download?path=` request names the file. What an error does carry is an *operation* — a phrase
  the resource module chose, such as `list archives for hsld26` — and a status code.
"""

from __future__ import annotations

import asyncio
import email.utils
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, NoReturn
from urllib.parse import urlsplit

import httpx
from pydantic import SecretStr

from debate_core.application.errors import (
    ArchiveTooLarge,
    DomainError,
    NotFound,
    ProviderRateLimited,
    ProviderUnavailable,
)
from debate_core.application.ports.caselist_source import (
    OPENCASELIST_PROVIDER,
    ArchiveUnavailable,
    CaselistAuthExpired,
    DownloadedFile,
    DownloadIntegrityError,
    UnexpectedCaselistResponse,
)
from debate_core.integrations.opencaselist.inbox_writer import write_into_inbox
from debate_core.integrations.opencaselist.pacing import RequestPacer
from debate_core.integrations.opencaselist.redaction import install_redaction, logger

__all__ = [
    "RETRYABLE_STATUS_CODES",
    "TOKEN_COOKIE",
    "JsonResponse",
    "OpenCaselistTransport",
    "TransportPolicy",
]

TOKEN_COOKIE: Final = "caselist_token"
"""The cookie the API authenticates with (the OpenAPI `cookie` security scheme)."""

RETRYABLE_STATUS_CODES: Final = frozenset({429, 502, 503, 504})
"""Answers that mean "not now" rather than "no"."""

_AUTH_REFUSALS: Final = frozenset({401, 403})
_GONE: Final = frozenset({403, 404, 410})

type TokenSource = Callable[[], SecretStr]
"""Returns the token for an authenticated request; raises when there is none."""

type AuthRefusal = Callable[[int], DomainError]
"""Builds the error a 401/403 from the API host becomes. Login overrides it."""


@dataclass(frozen=True, slots=True)
class TransportPolicy:
    """The politeness settings the transport enforces, from `settings.caselist`."""

    min_interval_seconds: float
    downloads_per_minute: int
    max_attempts: int
    backoff_base_seconds: float
    max_retry_wait_seconds: float
    max_download_bytes: int


@dataclass(frozen=True, slots=True)
class JsonResponse:
    """A decoded JSON answer and the headers it came with."""

    status_code: int
    body: Any
    headers: Mapping[str, str]


class _Retryable(Exception):
    """An attempt failed in a way worth another attempt."""

    def __init__(self, status_code: int | None, retry_after: float | None, reason: str) -> None:
        self.status_code = status_code
        self.retry_after = retry_after
        self.reason = reason
        super().__init__(reason)


class OpenCaselistTransport:
    """Sends requests to OpenCaselist and its file host, politely and one at a time."""

    def __init__(
        self,
        *,
        base_url: str,
        user_agent: str,
        policy: TransportPolicy,
        token_source: TokenSource,
        timeout: httpx.Timeout,
        on_authenticated_success: Callable[[], None] | None = None,
        http_client: httpx.AsyncClient | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        install_redaction()
        self._base_url = base_url.rstrip("/")
        self._api_host = urlsplit(self._base_url).netloc
        self._policy = policy
        self._token_source = token_source
        self._on_authenticated_success = on_authenticated_success
        self._validated = False
        self._sleep = sleep
        self._pacer = RequestPacer(
            min_interval_seconds=policy.min_interval_seconds,
            downloads_per_minute=policy.downloads_per_minute,
            clock=clock,
            sleep=sleep,
        )
        self._lock = asyncio.Lock()
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(timeout=timeout)
        self._client.follow_redirects = False
        self._client.headers["User-Agent"] = user_agent
        self._client.event_hooks = {"request": [_log_request], "response": [_log_response]}

    @property
    def pacer(self) -> RequestPacer:
        return self._pacer

    def api_url(self, route: str) -> str:
        """The absolute URL of an API route such as `/caselists`."""
        return f"{self._base_url}/{route.lstrip('/')}"

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # --------------------------------------------------------------------------------------------
    # Requests
    # --------------------------------------------------------------------------------------------

    async def get_json(
        self,
        route: str,
        *,
        operation: str,
        params: Mapping[str, str | int | bool] | None = None,
    ) -> JsonResponse:
        """An authenticated GET of an API route, decoded as JSON."""
        return await self._json_request("GET", route, operation=operation, params=params)

    async def post_json(
        self,
        route: str,
        *,
        operation: str,
        body: Mapping[str, Any],
        authenticated: bool,
        on_auth_refusal: AuthRefusal | None = None,
    ) -> JsonResponse:
        """A POST of a JSON body to an API route, decoded as JSON. Login posts unauthenticated."""
        return await self._json_request(
            "POST",
            route,
            operation=operation,
            body=body,
            authenticated=authenticated,
            on_auth_refusal=on_auth_refusal,
        )

    async def download(
        self,
        url: str,
        *,
        operation: str,
        source_name: str,
        inbox: Path,
        inbox_name: str,
        params: Mapping[str, str] | None = None,
        expected_size: int | None = None,
    ) -> DownloadedFile:
        """Stream a file into the inbox, counted against the download limit on every attempt.

        `url` may be the API's own `/download` route, which is authenticated, or the file host an
        archive listing names, which is not and never receives the token.
        """
        if urlsplit(url).scheme != "https":
            raise UnexpectedCaselistResponse(operation, "the file is not offered over https")
        authenticated = self._is_api_url(url)

        async def attempt() -> DownloadedFile:
            request = self._build_request("GET", url, params=params, authenticated=authenticated)
            request.headers["Accept-Encoding"] = "identity"
            response = await self._client.send(request, stream=True)
            try:
                self._raise_for_status(response, operation, authenticated, source_name=source_name)
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise DownloadIntegrityError(
                        source_name, "the server encoded the body, so its length cannot be checked"
                    )
                declared = _content_length(response)
                if declared is not None and declared > self._policy.max_download_bytes:
                    raise ArchiveTooLarge(
                        measured="archive",
                        actual_bytes=declared,
                        limit_bytes=self._policy.max_download_bytes,
                        source=source_name,
                    )
                return await write_into_inbox(
                    _raw_chunks(response),
                    inbox=inbox,
                    name=inbox_name,
                    source_name=source_name,
                    declared_length=declared,
                    expected_size=expected_size,
                )
            finally:
                await response.aclose()
                self._client.cookies.clear()

        return await self._with_retries(operation, attempt, download=True)

    # --------------------------------------------------------------------------------------------
    # The retry loop, shared by every request
    # --------------------------------------------------------------------------------------------

    async def _json_request(
        self,
        method: str,
        route: str,
        *,
        operation: str,
        params: Mapping[str, str | int | bool] | None = None,
        body: Mapping[str, Any] | None = None,
        authenticated: bool = True,
        on_auth_refusal: AuthRefusal | None = None,
    ) -> JsonResponse:
        url = self.api_url(route)

        async def attempt() -> JsonResponse:
            request = self._build_request(method, url, params=params, body=body, authenticated=authenticated)
            response = await self._client.send(request)
            try:
                self._raise_for_status(response, operation, authenticated, on_auth_refusal=on_auth_refusal)
                try:
                    decoded = response.json()
                except ValueError:
                    raise UnexpectedCaselistResponse(operation, "the body is not JSON") from None
                return JsonResponse(response.status_code, decoded, dict(response.headers))
            finally:
                await response.aclose()
                self._client.cookies.clear()

        return await self._with_retries(operation, attempt, download=False)

    async def _with_retries[T](
        self, operation: str, attempt: Callable[[], Awaitable[T]], *, download: bool
    ) -> T:
        policy = self._policy
        async with self._lock:
            for number in range(1, policy.max_attempts + 1):
                await self._pacer.slot(download=download)
                try:
                    try:
                        return await attempt()
                    except httpx.TransportError as dropped:
                        # A timeout, a refused connection, a reset. Its message quotes the URL.
                        raise _Retryable(None, None, f"{type(dropped).__name__}") from None
                    except httpx.HTTPError as broken:
                        raise ProviderUnavailable(
                            OPENCASELIST_PROVIDER, f"{operation} failed: {type(broken).__name__}"
                        ) from None
                except _Retryable as failure:
                    wait = self._wait_before_retry(operation, failure, number)
                    logger.warning(
                        "OpenCaselist: %s failed (%s); retrying in %.1fs, attempt %d of %d",
                        operation,
                        failure.reason,
                        wait,
                        number + 1,
                        policy.max_attempts,
                    )
                    await self._sleep(wait)
            raise AssertionError("unreachable: the last attempt raises")  # pragma: no cover

    def _wait_before_retry(self, operation: str, failure: _Retryable, number: int) -> float:
        """How long to wait before attempt `number + 1`, or raise when there is to be none."""
        policy = self._policy
        if number >= policy.max_attempts:
            self._give_up(operation, failure, f"after {number} attempts")
        if failure.retry_after is not None and failure.retry_after > policy.max_retry_wait_seconds:
            self._give_up(
                operation,
                failure,
                f"the server asked for {failure.retry_after:.0f}s, longer than "
                f"caselist.max_retry_wait_seconds ({policy.max_retry_wait_seconds:.0f}s)",
            )
        if failure.retry_after is not None:
            return max(failure.retry_after, 0.0)
        return min(policy.backoff_base_seconds * 2 ** (number - 1), policy.max_retry_wait_seconds)

    def _give_up(self, operation: str, failure: _Retryable, why: str) -> NoReturn:
        logger.error("OpenCaselist: %s abandoned (%s): %s", operation, failure.reason, why)
        if failure.status_code == 429:
            raise ProviderRateLimited(
                OPENCASELIST_PROVIDER,
                f"{operation} was rate limited ({why})",
                retry_after_seconds=failure.retry_after,
            ) from None
        raise ProviderUnavailable(
            OPENCASELIST_PROVIDER, f"{operation} failed: {failure.reason} ({why})"
        ) from None

    # --------------------------------------------------------------------------------------------
    # One attempt
    # --------------------------------------------------------------------------------------------

    def _build_request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, str | int | bool] | Mapping[str, str] | None,
        authenticated: bool,
        body: Mapping[str, Any] | None = None,
    ) -> httpx.Request:
        headers: dict[str, str] = {"Accept": "application/json"}
        if authenticated:
            if not self._is_api_url(url):
                raise AssertionError("the caselist_token is only ever sent to the API host")
            token = self._token_source()
            headers["Cookie"] = f"{TOKEN_COOKIE}={token.get_secret_value()}"
        query = {key: _query_value(value) for key, value in (params or {}).items()}
        return self._client.build_request(method, url, params=query or None, json=body, headers=headers)

    def _raise_for_status(
        self,
        response: httpx.Response,
        operation: str,
        authenticated: bool,
        *,
        source_name: str | None = None,
        on_auth_refusal: AuthRefusal | None = None,
    ) -> None:
        status = response.status_code
        from_api = self._is_api_url(str(response.request.url))
        if 200 <= status < 300:
            if authenticated and not self._validated:
                self._validated = True
                if self._on_authenticated_success is not None:
                    self._on_authenticated_success()
            return
        if status in RETRYABLE_STATUS_CODES:
            raise _Retryable(status, _retry_after(response), f"HTTP {status}")
        if from_api and status in _AUTH_REFUSALS:
            logger.error("OpenCaselist: %s refused with HTTP %d; not retried", operation, status)
            if on_auth_refusal is not None:
                raise on_auth_refusal(status)
            raise CaselistAuthExpired(status, operation)
        if source_name is not None and status in _GONE:
            raise ArchiveUnavailable(source_name, status)
        if from_api and status == 404:
            raise NotFound("OpenCaselist resource", operation)
        if 300 <= status < 400:
            raise UnexpectedCaselistResponse(operation, f"HTTP {status} redirect, which is never followed")
        raise ProviderUnavailable(OPENCASELIST_PROVIDER, f"{operation} failed with HTTP {status}")

    def _is_api_url(self, url: str) -> bool:
        parts = urlsplit(url)
        return parts.scheme == "https" and parts.netloc == self._api_host


# ------------------------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------------------------


def _query_value(value: str | int | bool) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _content_length(response: httpx.Response) -> int | None:
    raw = response.headers.get("Content-Length")
    if raw is None:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value >= 0 else None


async def _raw_chunks(response: httpx.Response) -> AsyncIterator[bytes]:
    """The body as sent, translating a dropped connection into a retryable failure."""
    try:
        async for chunk in response.aiter_raw():
            yield chunk
    except (httpx.TransportError, httpx.StreamError) as failure:
        raise _Retryable(
            None, None, f"the connection failed mid-download ({type(failure).__name__})"
        ) from None


def _retry_after(response: httpx.Response) -> float | None:
    """`Retry-After` as seconds, from either of its two forms; `None` when absent or unreadable."""
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    raw = raw.strip()
    try:
        return max(float(raw), 0.0)
    except ValueError:
        pass
    try:
        when = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max((when - datetime.now(UTC)).total_seconds(), 0.0)


async def _log_request(request: httpx.Request) -> None:
    """httpx event hook. The method and the route only: no headers, no query string."""
    logger.debug("OpenCaselist request: %s %s%s", request.method, request.url.host, request.url.path)


async def _log_response(response: httpx.Response) -> None:
    """httpx event hook. The status only."""
    logger.debug("OpenCaselist response: HTTP %d", response.status_code)
