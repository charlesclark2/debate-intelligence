"""The HTTPS requests the pilot makes to managed login and to the pool's key set, through `urllib`.

The OAuth endpoints (`/oauth2/token`, `/oauth2/revoke`) and the JSON Web Key Set are plain HTTPS,
not AWS APIs, so boto3 does not reach them. The standard library does, which keeps httpx inside
`debate_core.integrations.opencaselist` where its import contract holds it. Tests hand the
adapters a fake :class:`HttpTransport` and reach no network.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Protocol
from urllib.parse import urlencode

from debate_core.application.errors import StoreUnavailable

__all__ = ["HttpResponse", "HttpTransport", "UrllibTransport"]

_TIMEOUT_SECONDS: Final = 10.0
_MAX_BODY_BYTES: Final = 256 * 1024


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    body: bytes


class HttpTransport(Protocol):
    def post_form(self, url: str, fields: Mapping[str, str], *, headers: Mapping[str, str]) -> HttpResponse:
        """POST `fields` as `application/x-www-form-urlencoded`; any status comes back, none raises."""
        ...

    def get(self, url: str) -> HttpResponse: ...


class UrllibTransport(HttpTransport):
    """:class:`HttpTransport` over `urllib.request`, HTTPS only, with a timeout and a size limit."""

    def post_form(self, url: str, fields: Mapping[str, str], *, headers: Mapping[str, str]) -> HttpResponse:
        request = urllib.request.Request(
            url,
            data=urlencode(fields).encode("ascii"),
            headers={"Content-Type": "application/x-www-form-urlencoded", **headers},
            method="POST",
        )
        return self._send(request)

    def get(self, url: str) -> HttpResponse:
        return self._send(urllib.request.Request(url, method="GET"))

    def _send(self, request: urllib.request.Request) -> HttpResponse:
        if not request.full_url.startswith("https://"):
            raise ValueError("the pilot only speaks HTTPS to managed login")
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310
                return HttpResponse(status=response.status, body=response.read(_MAX_BODY_BYTES))
        except urllib.error.HTTPError as error:
            return HttpResponse(status=error.code, body=error.read(_MAX_BODY_BYTES))
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise StoreUnavailable(request.get_method(), "managed login", type(error).__name__) from error
