"""What one retrieval attempt produced: the bytes, the response, and how it fell short (v1-e04-t02).

:class:`FetchResult` is what :class:`~debate_core.application.ports.providers.ArticleFetcher`
returns, every time. The port promises that a refused or failed retrieval is an answer, not an
exception ("we could not read this source, and here is why" is something the platform records), so
a failure is a value on the result: :attr:`FetchResult.error`, one of the :data:`FetchError`
types below. The access classifier (v1-e04-t03) maps each of them, and each HTTP status, to an
:class:`~debate_core.domain.AccessStatus`.

| Error | When | Body |
|---|---|---|
| :class:`Timeout` | connecting, reading a chunk, or the whole request outran its deadline | empty |
| :class:`TooLarge` | the body passed `http.max_response_bytes`, declared or as it streamed | empty |
| :class:`TooManyRedirects` | more than `http.max_redirects` redirects | empty |
| :class:`RobotsDisallowed` | robots.txt refuses the URL or could not be read; nothing was requested | empty |
| :class:`UnsupportedScheme` | a redirect pointed at something other than http or https | empty |
| :class:`NonPublicAddress` | the URL's host is a loopback, private, link-local or reserved address | empty |
| :class:`TransportError` | the connection failed in some other way | empty |
| :class:`HttpStatusError` | the final response was 4xx or 5xx | as the server sent it |

**A body is never partial.** A result whose error is anything but :class:`HttpStatusError` carries
no bytes at all, which the model enforces: a body cut off at the size limit is not the document, and
nothing downstream should be able to hash it into a snapshot. An error response keeps its body
because the classifier reads it: a 403 can be a bot challenge, and that is a different answer from
a plain refusal.

**Messages name hosts, not URLs.** A URL's query string can carry a signed token or an email
address, so a `message` never includes one. The URL is on the result, where it belongs.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from debate_core.domain import AccessStatus, DomainModel, HttpUrlStr, NonEmptyText, UtcDatetime

__all__ = [
    "FetchError",
    "FetchErrorBase",
    "FetchResult",
    "HttpStatusError",
    "NonPublicAddress",
    "RobotsDisallowed",
    "RobotsRefusalReason",
    "Timeout",
    "TimeoutPhase",
    "TooLarge",
    "TooManyRedirects",
    "TransportError",
    "UnsupportedScheme",
]


class FetchErrorBase(DomainModel):
    """What every fetch error carries: where it happened and a sentence saying what went wrong."""

    url: HttpUrlStr = Field(
        description="The URL the failure happened at: the one asked for, or the redirect hop that failed."
    )
    message: NonEmptyText = Field(description="One sentence for a person; names a host, never a full URL.")


class TimeoutPhase(StrEnum):
    """Which deadline ran out."""

    CONNECT = "connect"
    """Establishing the connection took longer than `http.connect_timeout_seconds`."""

    READ = "read"
    """The server went quiet for longer than `http.request_timeout_seconds` between two chunks."""

    TOTAL = "total"
    """The whole request, redirects included, took longer than `http.request_timeout_seconds`."""


class Timeout(FetchErrorBase):
    """A deadline from settings ran out before the response was complete."""

    kind: Literal["timeout"] = "timeout"
    phase: TimeoutPhase = Field(description="Which deadline ran out.")
    limit_seconds: float = Field(gt=0, description="The deadline, from settings.")


class TooLarge(FetchErrorBase):
    """The body is bigger than `http.max_response_bytes`.

    Detected from `Content-Length` before any of the body is read when the server declares it, and
    otherwise while streaming: the read stops as soon as the count passes the limit, so the fetcher
    never holds more than the limit plus one chunk.
    """

    kind: Literal["too_large"] = "too_large"
    limit_bytes: int = Field(gt=0, description="The limit, from settings.")
    declared_bytes: int | None = Field(
        default=None, ge=0, description="The `Content-Length` the server declared, when it declared one."
    )
    received_bytes: int = Field(ge=0, description="How many bytes had arrived when the read stopped.")


class TooManyRedirects(FetchErrorBase):
    """The server redirected more times than `http.max_redirects` allows."""

    kind: Literal["too_many_redirects"] = "too_many_redirects"
    limit: int = Field(ge=0, description="The limit, from settings.")
    redirect_chain: tuple[HttpUrlStr, ...] = Field(
        description="Every URL requested, in order, the first being the one asked for."
    )


class RobotsRefusalReason(StrEnum):
    """Why robots.txt kept the fetcher from a URL."""

    DISALLOWED = "disallowed"
    """The site's rules disallow this path for this crawler."""

    ROBOTS_ACCESS_DENIED = "robots_access_denied"
    """robots.txt itself answered 401 or 403, which `urllib.robotparser` reads as "disallow all"."""

    ROBOTS_UNREACHABLE = "robots_unreachable"
    """robots.txt could not be read: a 5xx, a 429, a timeout or a failed connection, after retries.
    RFC 9309 §2.3.1.4 says to assume complete disallow, and the platform does."""


class RobotsDisallowed(FetchErrorBase):
    """robots.txt refused this URL, so it was never requested.

    The one error the fetcher also records as an access status: a result carrying it has
    `access_status` :attr:`~debate_core.domain.AccessStatus.ROBOTS_DISALLOWED`.
    """

    kind: Literal["robots_disallowed"] = "robots_disallowed"
    robots_url: HttpUrlStr = Field(description="The robots.txt that decided it.")
    reason: RobotsRefusalReason = Field(description="Whether the rules said no, or could not be read.")


class UnsupportedScheme(FetchErrorBase):
    """A redirect pointed at something other than http or https (`ftp:`, `file:`, `javascript:`).

    The target itself is not kept: it is not a valid :data:`~debate_core.domain.HttpUrlStr`, and it
    may carry credentials. `url` is the hop that answered with the redirect.
    """

    kind: Literal["unsupported_scheme"] = "unsupported_scheme"
    scheme: str = Field(description="The scheme the redirect named, lower-cased; empty when it named none.")


class NonPublicAddress(FetchErrorBase):
    """The URL names a loopback, private, link-local or otherwise non-public address.

    Checked for the URL asked for and for every redirect hop, before any request, so a public page
    cannot redirect the fetcher into the machine it runs on or that machine's network. Only literal
    addresses and `localhost` are recognised; a public name that resolves to a private address is
    not (the check would need a resolver of its own).
    """

    kind: Literal["non_public_address"] = "non_public_address"
    host: NonEmptyText = Field(description="The host as the URL spelled it.")


class TransportError(FetchErrorBase):
    """The connection failed for a reason that is not a timeout: refused, reset, TLS, protocol."""

    kind: Literal["transport_error"] = "transport_error"
    reason: NonEmptyText = Field(description="The failure's class, e.g. `ConnectError`; never its text.")


class HttpStatusError(FetchErrorBase):
    """The final response was a 4xx or a 5xx, after any retries the status allowed."""

    kind: Literal["http_status"] = "http_status"
    status_code: int = Field(ge=400, le=599, description="The final response's status.")
    retry_after_seconds: float | None = Field(
        default=None, ge=0, description="What the final response's `Retry-After` asked for, when it had one."
    )
    attempts: int = Field(ge=1, description="Requests made for this URL, the first one included.")


type FetchError = Annotated[
    Timeout
    | TooLarge
    | TooManyRedirects
    | RobotsDisallowed
    | UnsupportedScheme
    | NonPublicAddress
    | TransportError
    | HttpStatusError,
    Field(discriminator="kind"),
]
"""Any one of the fetch errors, told apart by `kind` when read back from JSON."""


class FetchResult(DomainModel):
    """The outcome of one retrieval attempt: the bytes, and everything about the response.

    Carries bytes, not text. Decoding is part of extraction, and the SHA-256 that anchors a
    snapshot is taken over exactly these bytes (architecture proposal §8). They are the body as
    decoded from any `Content-Encoding` (gzip, br), which is the document; never the compressed
    transfer form.

    `access_status` records only what the fetcher itself decided: a refusal under robots rules is
    :attr:`~debate_core.domain.AccessStatus.ROBOTS_DISALLOWED`. Every other outcome is left
    :attr:`~debate_core.domain.AccessStatus.UNKNOWN` for the access classifier (v1-e04-t03), which
    reads `error`, `status_code` and the body, so the status-to-access mapping is written once.
    """

    requested_url: HttpUrlStr = Field(description="The URL the fetch was asked for, exactly as given.")
    final_url: HttpUrlStr = Field(
        description="The URL that answered after any redirects, or the last one tried when none did."
    )
    status_code: int | None = Field(
        default=None, ge=100, le=599, description="HTTP status, or None when no response arrived."
    )
    headers: dict[str, str] = Field(
        default_factory=dict, description="Response headers, lowercased keys, as strings."
    )
    content_type: NonEmptyText | None = Field(
        default=None, description="Content type as reported, parameters included."
    )
    sniffed_content_type: NonEmptyText | None = Field(
        default=None,
        description=(
            "What the first bytes look like (`application/pdf`, `text/html`), whatever the server "
            "declared; None when they match no known signature. Never replaces `content_type`."
        ),
    )
    body: bytes = Field(default=b"", description="Exactly the bytes received, unmodified.")
    redirect_chain: tuple[HttpUrlStr, ...] = Field(
        default=(),
        description="Every URL requested before `final_url`, in order; empty when nothing redirected.",
    )
    elapsed_ms: float = Field(ge=0, description="Wall-clock time the fetch took, in milliseconds.")
    fetched_at: UtcDatetime = Field(description="When the fetch completed, in UTC.")
    access_status: AccessStatus = Field(
        default=AccessStatus.UNKNOWN,
        description="Transport-level outcome only; paywall classification happens downstream.",
    )
    error: FetchError | None = Field(
        default=None, description="Why the fetch fell short, or None when a 1xx-3xx response arrived whole."
    )

    @property
    def byte_size(self) -> int:
        """Number of bytes received."""
        return len(self.body)

    @model_validator(mode="after")
    def _check_failure_is_consistent(self) -> Self:
        if self.error is not None and not isinstance(self.error, HttpStatusError) and self.body:
            raise ValueError(f"a FetchResult carrying a {self.error.kind} error must have an empty body")
        if isinstance(self.error, HttpStatusError) and self.error.status_code != self.status_code:
            raise ValueError("an HttpStatusError must carry the result's own status_code")
        robots_refused = isinstance(self.error, RobotsDisallowed)
        if robots_refused != (self.access_status is AccessStatus.ROBOTS_DISALLOWED):
            raise ValueError("access_status is ROBOTS_DISALLOWED exactly when the error is RobotsDisallowed")
        return self
