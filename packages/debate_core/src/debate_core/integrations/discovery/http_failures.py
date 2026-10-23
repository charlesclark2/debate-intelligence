"""One mapping from an HTTP answer to the port's error types, for every discovery adapter.

Each adapter talks to a different API, but they all refuse in HTTP, and the circuit breaker and
the rate-limit hold in :mod:`~debate_core.integrations.discovery.resilience` only work if every
adapter says "rate limited" and "unavailable" the same way. An adapter calls
:func:`provider_error_for_status` with the status and headers of a response it is not going to
read, and raises what comes back:

| Status | Error |
|---|---|
| 1xx, 2xx, 3xx | none: the adapter reads the response (a 304 is how a conditional `GET` says "unchanged") |
| 429 | :class:`~debate_core.application.errors.ProviderRateLimited`, with the `Retry-After` it stated |
| 408, 5xx | :class:`~debate_core.application.errors.ProviderUnavailable` |
| any other 4xx | :class:`~debate_core.application.errors.ProviderUnavailable`, "refused the request" |

Plain values in, so this module has no HTTP library of its own: `response.status_code` and
`response.headers` from httpx are what an adapter passes. The messages carry the status and
nothing from the request, because a request URL can carry a key or a contact email.

The `Retry-After` itself is read by :func:`~debate_core.integrations.retry_after.retry_after_seconds`,
the one reader every HTTP adapter shares (`v1-e07-t08`). This module still answers to the name,
because the discovery tests have always imported it from here.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from debate_core.application.errors import ProviderError, ProviderRateLimited, ProviderUnavailable
from debate_core.integrations.retry_after import retry_after_seconds

__all__ = ["provider_error_for_status", "retry_after_seconds"]


def provider_error_for_status(
    provider: str, status: int, headers: Mapping[str, str], *, now: datetime
) -> ProviderError | None:
    """The error a response with this status means, or `None` when the adapter should read it.

    `headers` is looked up without regard to case, so a plain `dict` works as well as httpx's
    case-insensitive headers.
    """
    if status < 400:
        return None
    if status == 429:
        wait = retry_after_seconds(_header(headers, "retry-after"), now=now)
        return ProviderRateLimited(provider, "HTTP 429", retry_after_seconds=wait)
    if status == 408 or status >= 500:
        return ProviderUnavailable(provider, f"HTTP {status}")
    return ProviderUnavailable(provider, f"HTTP {status}: the provider refused the request")


def _header(headers: Mapping[str, str], name: str) -> str | None:
    for key, value in headers.items():
        if key.lower() == name:
            return value
    return None
