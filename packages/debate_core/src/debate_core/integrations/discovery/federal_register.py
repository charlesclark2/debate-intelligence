"""The Federal Register, rules, proposed rules and notices by full-text search (v1-e07-t07).

:class:`FederalRegisterProvider` asks the Register's `GET /api/v1/documents.json` for a query and maps
each document to a :class:`~debate_core.domain.discovery.CandidateResult`. It is a plain adapter: the
registry wraps it in :class:`~debate_core.integrations.discovery.resilience.ResilientProvider`, which
times it, benches it after repeated failures and holds it through a rate limit. It never downloads a
document's text or its PDF: ArticleService fetches the page when a card is cut from it.

Everything here is from the Register's API spec, https://www.federalregister.gov/api/v1/documentation.json,
read by the PM on 2026-11-02 (the Register's documentation pages send this platform's own reader to a
block page): no API key, no stated rate limit, and only a `200` answer documented.

**The request** is one `GET` (:func:`documents_parameters`): `conditions[term]=` the query (the
Register's full-text search), the date window as `conditions[publication_date][gte]` and `[lte]` (the
UTC dates of `since` and `until`), `conditions[type][]` for rules, proposed rules and notices
(:data:`DOCUMENT_TYPES`; presidential documents are left out), the `fields[]` mapped here
(:data:`FIELDS`), `order=relevance` and `per_page`. A search asks for at most 200 results, under the
Register's 1,000, so one page always holds them. Nothing else is sent: no key, no contact email and no
cookie, whatever the settings hold.

**What is kept from a document**:

* `provider_record_id` is the document number, as the Register prints it (`2025-01234`; older and
  correction numbers have other shapes, such as `E9-1234`, so its shape is not checked). It is the
  Register's own identifier and stable. `ArticleIdentifiers` has no field for it and stays empty.
* `url` is the document's page on federalregister.gov (`html_url`), or its official PDF
  (`pdf_url`) when the Register gives no page. A document with neither, no title or no number is
  not a candidate and is skipped.
* `publication` is the issuing agencies, `agency_names` in the Register's order joined by `; `
  (a sub-agency follows its department: `Health and Human Services Department; Centers for
  Medicare & Medicaid Services`). There are no `authors`.
* `published_at` is the publication date at midnight UTC, precise to the day; a date that is not a
  real `YYYY-MM-DD` day is left out rather than guessed.
* `snippet` is the abstract, for discovery only: card evidence comes from a stored snapshot.
* Every document is `government`, and free to read (`open_access`), with its PDF as the open copy.

**Refusals** go through :func:`~debate_core.integrations.discovery.http_failures.provider_error_for_status`.
A `3xx` is not followed (the client follows no redirect) and is
:class:`~debate_core.application.errors.ProviderUnavailable` naming only the host it points to: the
Register answers a request it takes for scraping with `302` to `unblock.federalregister.gov`, and that
is a provider refusing, not an answer to read. The adapter sends no conditional request, so a `304` is
no exception.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from http.cookiejar import CookieJar, DefaultCookiePolicy
from typing import Any, Final, cast
from urllib.parse import urlsplit

import httpx

from debate_core.application.errors import ProviderUnavailable
from debate_core.application.ports.providers import Clock
from debate_core.application.settings import HttpSettings, ProviderSettings, SearchProviderName
from debate_core.domain.discovery import CandidateResult, DatePrecision, ProviderQuery, ProviderResponse
from debate_core.domain.enums import SourceType
from debate_core.integrations.discovery.http_failures import provider_error_for_status, redirect_failure

__all__ = [
    "DOCUMENT_TYPES",
    "FEDERAL_REGISTER_DOCUMENTS_URL",
    "FIELDS",
    "MAX_PER_PAGE",
    "PROVIDER_NAME",
    "FederalRegisterProvider",
    "candidate_from_document",
    "documents_parameters",
    "federal_register_factory",
]

PROVIDER_NAME: Final = SearchProviderName.FEDERAL_REGISTER.value
"""The name settings enable this provider by, and every result carries."""

FEDERAL_REGISTER_DOCUMENTS_URL: Final = "https://www.federalregister.gov/api/v1/documents.json"
"""The documents search endpoint."""

DOCUMENT_TYPES: Final = ("RULE", "PRORULE", "NOTICE")
"""Rules, proposed rules and notices: the spec's three of the Register's four types (not PRESDOCU)."""

FIELDS: Final = (
    "document_number",
    "title",
    "publication_date",
    "agency_names",
    "abstract",
    "html_url",
    "pdf_url",
)
"""The document fields :func:`candidate_from_document` reads, asked for by `fields[]`."""

MAX_PER_PAGE: Final = 1000
"""The Register's largest page."""

PUBLICATION_SEPARATOR: Final = "; "
"""Between two issuing agencies in `publication`."""


def candidate_from_document(document: Mapping[str, Any]) -> CandidateResult | None:
    """One Register document as a candidate; `None` without a number, a title or a link."""
    number = _text(document.get("document_number"))
    title = _text(document.get("title"))
    pdf_url = _http_url(document.get("pdf_url"))
    url = _http_url(document.get("html_url")) or pdf_url
    if number is None or title is None or url is None:
        return None
    published_at = _publication_date(document.get("publication_date"))
    return CandidateResult(
        provider=PROVIDER_NAME,
        provider_record_id=number,
        title=title,
        url=url,
        source_type=SourceType.GOVERNMENT,
        publication=_agencies(document.get("agency_names")),
        published_at=published_at,
        date_precision=DatePrecision.DAY if published_at is not None else None,
        snippet=_text(document.get("abstract")),
        open_access_url=pdf_url,
        open_access=True,
    )


def _agencies(value: object) -> str | None:
    """The issuing agencies' names in the Register's order, each once, or `None` when it names none."""
    if not isinstance(value, list):
        return None
    names = [name for entry in cast(list[object], value) if (name := _text(entry)) is not None]
    return PUBLICATION_SEPARATOR.join(dict.fromkeys(names)) or None


def _publication_date(value: object) -> datetime | None:
    """Midnight UTC on the Register's `YYYY-MM-DD` publication date; `None` for anything else."""
    text = _text(value)
    if text is None or len(text) != len("YYYY-MM-DD"):
        return None
    try:
        day = date.fromisoformat(text)
    except ValueError:
        return None
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def _http_url(value: object) -> str | None:
    """`value` when it is a URL `CandidateResult` accepts: absolute http(s), with a host, no spaces."""
    text = _text(value)
    if text is None or any(character.isspace() for character in text):
        return None
    parts = urlsplit(text)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return text


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


# --------------------------------------------------------------------------------------------
# The request and the adapter
# --------------------------------------------------------------------------------------------


def documents_parameters(query: ProviderQuery) -> list[tuple[str, str]]:
    """The `documents.json` query parameters for `query`, in order; repeated keys repeat."""
    parameters = [("conditions[term]", query.query)]
    if query.filters.since is not None:
        parameters.append(("conditions[publication_date][gte]", query.filters.since.date().isoformat()))
    if query.filters.until is not None:
        parameters.append(("conditions[publication_date][lte]", query.filters.until.date().isoformat()))
    parameters += [("conditions[type][]", document_type) for document_type in DOCUMENT_TYPES]
    parameters += [("fields[]", field) for field in FIELDS]
    parameters.append(("order", "relevance"))
    parameters.append(("per_page", str(min(query.filters.max_results, MAX_PER_PAGE))))
    return parameters


class FederalRegisterProvider:
    """Searches the Federal Register's documents; a :class:`~debate_core.application.ports.SearchProvider`.

    Sends one request per search and never retries it: the wrapper decides what happens after a
    failure. Holds no credential. Owns `client`; close it with :meth:`aclose`.
    """

    def __init__(self, client: httpx.AsyncClient, *, clock: Clock) -> None:
        self._client = client
        self._clock = clock

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"

    async def aclose(self) -> None:
        """Close the HTTP client and its connections."""
        await self._client.aclose()

    async def search(self, query: ProviderQuery) -> ProviderResponse:
        started = time.perf_counter()
        try:
            response = await self._client.get(
                FEDERAL_REGISTER_DOCUMENTS_URL, params=tuple(documents_parameters(query))
            )
        except httpx.TimeoutException as error:
            raise ProviderUnavailable(self.name, "timed out") from error
        except httpx.HTTPError as error:
            raise ProviderUnavailable(self.name, f"transport failure: {type(error).__name__}") from error
        if 300 <= response.status_code < 400:
            raise redirect_failure(self.name, response.status_code, response.headers)
        failure = provider_error_for_status(
            self.name, response.status_code, response.headers, now=self._clock.now()
        )
        if failure is not None:
            raise failure
        results = self._read(response, query)
        elapsed_ms = (time.perf_counter() - started) * 1000
        return ProviderResponse(provider=self.name, results=results, elapsed_ms=elapsed_ms)

    def _read(self, response: httpx.Response, query: ProviderQuery) -> tuple[CandidateResult, ...]:
        try:
            document = response.json()
        except ValueError as error:
            raise ProviderUnavailable(self.name, f"unreadable response: {type(error).__name__}") from error
        if not isinstance(document, dict):
            raise ProviderUnavailable(self.name, "unreadable response: not a document list")
        envelope = cast(dict[str, Any], document)
        if "results" not in envelope and envelope.get("count") == 0:
            return ()
        documents = envelope.get("results")
        if not isinstance(documents, list) or not all(
            isinstance(entry, dict) for entry in cast(list[object], documents)
        ):
            raise ProviderUnavailable(self.name, "unreadable response: not a document list")
        candidates = (candidate_from_document(entry) for entry in cast(list[dict[str, Any]], documents))
        return tuple(candidate for candidate in candidates if candidate is not None)[
            : query.filters.max_results
        ]


def federal_register_factory(
    http: HttpSettings,
    *,
    version: str,
    clock: Clock,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Callable[[ProviderSettings], FederalRegisterProvider]:
    """The registry's factory for `federal_register`: an adapter over a client built from the HTTP settings.

    The client identifies the platform with the same User-Agent as the article fetcher, follows no
    redirect, keeps no cookies and reads nothing from the environment (no `~/.netrc`, no proxy). Its
    own timeouts are the HTTP settings'; the wrapper's `providers.timeout_seconds` bounds the whole
    call. The provider settings are not read: the Register takes no key. `transport` is for tests,
    which pass a mock.
    """

    def build(settings: ProviderSettings) -> FederalRegisterProvider:
        client = httpx.AsyncClient(
            headers={"User-Agent": http.user_agent(version)},
            timeout=httpx.Timeout(http.request_timeout_seconds, connect=http.connect_timeout_seconds),
            follow_redirects=False,
            cookies=CookieJar(policy=DefaultCookiePolicy(allowed_domains=[])),
            trust_env=False,
            transport=transport,
        )
        return FederalRegisterProvider(client, clock=clock)

    return build
