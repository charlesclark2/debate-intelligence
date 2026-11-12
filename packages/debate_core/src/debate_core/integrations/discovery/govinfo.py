"""GovInfo: bills, committee reports, hearings and committee prints by search (v1-e07-t07).

:class:`GovInfoProvider` asks GovInfo's search service for a query and maps each result to a
:class:`~debate_core.domain.discovery.CandidateResult`. It is a plain adapter: the registry wraps it
in :class:`~debate_core.integrations.discovery.resilience.ResilientProvider`, which times it, benches
it after repeated failures and holds it through a rate limit. It never downloads a package's text
or its PDF: ArticleService fetches the page when a card is cut from it.

GovInfo is also where bills are searched. Congress.gov's API has no keyword search (its
`openapi.yaml` gives `/bill` only paging and update dates, read 2026-11-02), so a bill comes from
GovInfo's `BILLS` collection, and its Congress, type and number are read from the package id
(:func:`bill_number`).

What is here is from GovInfo's documentation, read 2026-11-02: the search service overview
(govinfo.gov/features/search-service-overview, published 2023-08-15), github.com/usgpo/api, and the
search help (govinfo.gov/help/finding-info and /help/chrg).

**The request** is one `POST https://api.govinfo.gov/search` (:func:`search_body`) with a JSON body:
`query`, `pageSize` (a search asks for at most 200, under GovInfo's 1,000), `offsetMark` `*` for the
first page, and `sorts` by relevance (`score`, descending, the only order `score` takes). The query is
the search's words in brackets, then `collection:(BILLS OR CRPT OR CHRG OR CPRT)` (:data:`COLLECTIONS`)
and, for a date window, `publishdate:range(<since>,<until>)` on the UTC dates, either end left open.
Brackets, colons and an unpaired double quote in the words are cleared first, so what the person
typed is searched as words and never read as GovInfo's field syntax; balanced quotes still search a
phrase. Words that clear to nothing are not sent: the answer is empty.

**The key.** GovInfo needs an api.data.gov key (:mod:`~debate_core.integrations.discovery.data_gov`).
It is sent as the `X-Api-Key` header, never in the URL or the body, and the factory registers it
with the log protection. Without one the factory builds nothing and the provider is reported not
configured. api.data.gov allows a key 1,000 requests an hour (GovInfo states 36,000, 1,200 a minute
and 40 a second for its own); past that it answers `429` with no `Retry-After`, and the wrapper holds
GovInfo for its exponential backoff (v1-e07-t22). A refused key is a `403`, reported as a refusal
that names no key.

**What is kept from a result**:

* `provider_record_id` is the package id as GovInfo prints it (`BILLS-119hr4821ih`, `CRPT-119hrpt212`,
  `CHRG-119shrg58210`, `CPRT-119HPRT61022`): GovInfo's own identifier, and stable. A bill's names its
  Congress, type, number and version (`119`, `hr`, `4821`, `ih` for introduced in the House), and a
  `BILLS` result whose id does not is skipped. `ArticleIdentifiers` has no field for either and stays
  empty. A result for a part of a package (a `granuleId`) is its package: the first result of each
  package is kept and the rest left out.
* `url` is the package's page on govinfo.gov, `https://www.govinfo.gov/app/details/<package id>`. The
  `download` links are not used: they are API URLs that need the key, which must never be handed to
  the fetcher or written into a stored URL. There is no open-access link, but every package is free
  to read (`open_access`).
* `publication` is the issuing body, `governmentAuthor` in GovInfo's order joined by `; `
  (`Congress. Senate. Committee on Finance`). There are no `authors` and no snippet.
* `published_at` is `dateIssued` at its own precision: a day, a month or a year
  (:class:`~debate_core.domain.discovery.DatePrecision`), stored at the start of that period and never
  given a day it does not have. A date that is none of those is left out.
* Every result is `government`.

**Refusals** go through :func:`~debate_core.integrations.discovery.http_failures.provider_error_for_status`.
A `3xx` is not followed and is :func:`~debate_core.integrations.discovery.http_failures.redirect_failure`.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from http.cookiejar import CookieJar, DefaultCookiePolicy
from typing import Any, Final, cast

import httpx

from debate_core.application.errors import ProviderUnavailable
from debate_core.application.ports.providers import Clock
from debate_core.application.settings import HttpSettings, ProviderSettings, SearchProviderName
from debate_core.domain.discovery import CandidateResult, DatePrecision, ProviderQuery, ProviderResponse
from debate_core.domain.enums import SourceType
from debate_core.integrations.discovery.data_gov import API_KEY_HEADER, require_api_data_gov_key
from debate_core.integrations.discovery.http_failures import provider_error_for_status, redirect_failure

__all__ = [
    "COLLECTIONS",
    "DETAILS_URL",
    "GOVINFO_SEARCH_URL",
    "MAX_PAGE_SIZE",
    "PROVIDER_NAME",
    "BillNumber",
    "GovInfoProvider",
    "bill_number",
    "candidate_from_result",
    "govinfo_factory",
    "search_body",
    "search_words",
]

PROVIDER_NAME: Final = SearchProviderName.GOVINFO.value
"""The name settings enable this provider by, and every result carries."""

GOVINFO_SEARCH_URL: Final = "https://api.govinfo.gov/search"
"""The search service."""

DETAILS_URL: Final = "https://www.govinfo.gov/app/details/"
"""A package's public page, with its package id appended."""

COLLECTIONS: Final = ("BILLS", "CRPT", "CHRG", "CPRT")
"""Bills, committee reports, hearings and committee prints (PM ruling 2026-11-02).

GAO reports are left out: GovInfo's `GAOREPORTS` stops in September 2008 (govinfo.gov/help/gaoreports).
CRS reports are not on GovInfo at all.
"""

MAX_PAGE_SIZE: Final = 1000
"""GovInfo's largest `pageSize`."""

PUBLICATION_SEPARATOR: Final = "; "
"""Between two issuing bodies in `publication`."""

BILL_TYPES: Final = ("hconres", "sconres", "hjres", "sjres", "hres", "sres", "hr", "s")
"""The bill and resolution types, as a `BILLS` package id spells them (Congress.gov's list, in lower case)."""

_BILL_PACKAGE: Final = re.compile(
    rf"^BILLS-(?P<congress>[1-9][0-9]{{0,2}})(?P<type>{'|'.join(BILL_TYPES)})"
    r"(?P<number>[1-9][0-9]*)(?P<version>[a-z]+)$"
)
_PACKAGE_ID: Final = re.compile(r"^[A-Z]+-[A-Za-z0-9-]+$")
"""GovInfo's package id shape: a collection code, a hyphen, then letters, digits and hyphens."""
_SYNTAX: Final = re.compile(r"[():]")
_DAY: Final = re.compile(r"^\d{4}-\d{2}-\d{2}(T.*)?$")
_MONTH: Final = re.compile(r"^(\d{4})-(\d{2})$")
_YEAR: Final = re.compile(r"^(\d{4})$")


@dataclass(frozen=True, slots=True)
class BillNumber:
    """A bill as its `BILLS` package id names it: `BILLS-119hr4821ih` is H.R. 4821 of the 119th Congress."""

    congress: int
    """The Congress, `119`."""
    bill_type: str
    """`hr`, `s`, `hjres`, `sjres`, `hconres`, `sconres`, `hres` or `sres`."""
    number: int
    """The bill's number within its type and Congress."""
    version: str
    """The text's version: `ih` introduced in the House, `rs` reported in the Senate, `enr` enrolled."""


def bill_number(package_id: str) -> BillNumber | None:
    """The bill a `BILLS` package id names; `None` for any other id, or one that names no bill."""
    match = _BILL_PACKAGE.match(package_id)
    if match is None:
        return None
    return BillNumber(
        congress=int(match["congress"]),
        bill_type=match["type"],
        number=int(match["number"]),
        version=match["version"],
    )


def candidate_from_result(result: Mapping[str, Any]) -> CandidateResult | None:
    """One GovInfo result as a candidate; `None` without a title, a package id, or a bill's number."""
    package_id = _text(result.get("packageId"))
    title = _text(result.get("title"))
    if package_id is None or title is None or _PACKAGE_ID.match(package_id) is None:
        return None
    if package_id.startswith("BILLS-") and bill_number(package_id) is None:
        return None
    published_at, precision = _date_issued(result.get("dateIssued"))
    return CandidateResult(
        provider=PROVIDER_NAME,
        provider_record_id=package_id,
        title=title,
        url=f"{DETAILS_URL}{package_id}",
        source_type=SourceType.GOVERNMENT,
        publication=_authors(result.get("governmentAuthor")),
        published_at=published_at,
        date_precision=precision,
        open_access=True,
    )


def _authors(value: object) -> str | None:
    """The issuing bodies in GovInfo's order, each once, or `None` when it names none."""
    if not isinstance(value, list):
        return None
    names = [name for entry in cast(list[object], value) if (name := _text(entry)) is not None]
    return PUBLICATION_SEPARATOR.join(dict.fromkeys(names)) or None


def _date_issued(value: object) -> tuple[datetime | None, DatePrecision | None]:
    """`dateIssued` at the start of the day, month or year it names, with that precision."""
    text = _text(value)
    if text is None:
        return None, None
    try:
        if _DAY.match(text):
            day = date.fromisoformat(text[: len("YYYY-MM-DD")])
            return datetime(day.year, day.month, day.day, tzinfo=UTC), DatePrecision.DAY
        if month := _MONTH.match(text):
            return datetime(int(month[1]), int(month[2]), 1, tzinfo=UTC), DatePrecision.MONTH
        if year := _YEAR.match(text):
            return datetime(int(year[1]), 1, 1, tzinfo=UTC), DatePrecision.YEAR
    except ValueError:
        return None, None
    return None, None


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


# --------------------------------------------------------------------------------------------
# The request and the adapter
# --------------------------------------------------------------------------------------------


def search_words(typed: str) -> str:
    """The words to search: brackets and colons cleared, an unpaired double quote dropped, spaces single."""
    words = _SYNTAX.sub(" ", typed)
    if words.count('"') % 2:
        words = words.replace('"', " ")
    return " ".join(words.split())


def search_body(query: ProviderQuery) -> dict[str, object]:
    """The search service's JSON body for `query`; see the module docstring for each part."""
    parts = [f"({search_words(query.query)})", f"collection:({' OR '.join(COLLECTIONS)})"]
    since, until = query.filters.since, query.filters.until
    if since is not None or until is not None:
        start = since.date().isoformat() if since is not None else ""
        end = until.date().isoformat() if until is not None else ""
        parts.append(f"publishdate:range({start},{end})")
    return {
        "query": " AND ".join(parts),
        "pageSize": min(query.filters.max_results, MAX_PAGE_SIZE),
        "offsetMark": "*",
        "sorts": [{"field": "score", "sortOrder": "DESC"}],
    }


class GovInfoProvider:
    """Searches GovInfo; a :class:`~debate_core.application.ports.SearchProvider`.

    Sends at most one request per search and never retries it: the wrapper decides what happens after
    a failure. Owns `client`; close it with :meth:`aclose`.
    """

    def __init__(self, client: httpx.AsyncClient, *, api_key: str, clock: Clock) -> None:
        self._client = client
        self._api_key = api_key
        self._clock = clock

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    def __repr__(self) -> str:
        return f"{type(self).__name__}(api_key=configured)"

    async def aclose(self) -> None:
        """Close the HTTP client and its connections."""
        await self._client.aclose()

    async def search(self, query: ProviderQuery) -> ProviderResponse:
        started = time.perf_counter()
        if not search_words(query.query):
            elapsed_ms = (time.perf_counter() - started) * 1000
            return ProviderResponse(provider=self.name, elapsed_ms=elapsed_ms)
        try:
            response = await self._client.post(
                GOVINFO_SEARCH_URL, json=search_body(query), headers={API_KEY_HEADER: self._api_key}
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
        results = cast(dict[str, Any], document).get("results") if isinstance(document, dict) else None
        if not isinstance(results, list) or not all(
            isinstance(entry, dict) for entry in cast(list[object], results)
        ):
            raise ProviderUnavailable(self.name, "unreadable response: not a result list")
        by_package: dict[str, CandidateResult] = {}
        for entry in cast(list[dict[str, Any]], results):
            candidate = candidate_from_result(entry)
            if candidate is not None and candidate.provider_record_id is not None:
                by_package.setdefault(candidate.provider_record_id, candidate)
        return tuple(by_package.values())[: query.filters.max_results]


def govinfo_factory(
    http: HttpSettings,
    *,
    version: str,
    clock: Clock,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Callable[[ProviderSettings], GovInfoProvider]:
    """The registry's factory for `govinfo`: an adapter over a client built from the HTTP settings.

    Raises :class:`~debate_core.integrations.discovery.registry.ProviderNotConfigured` when no
    api.data.gov key is set, so the registry records GovInfo as not configured and builds nothing.
    The client identifies the platform with the same User-Agent as the article fetcher, follows no
    redirect, keeps no cookies and reads nothing from the environment (no `~/.netrc`, no proxy). Its
    own timeouts are the HTTP settings'; the wrapper's `providers.timeout_seconds` bounds the whole
    call. `transport` is for tests, which pass a mock.
    """

    def build(settings: ProviderSettings) -> GovInfoProvider:
        api_key = require_api_data_gov_key(settings, PROVIDER_NAME)
        client = httpx.AsyncClient(
            headers={"User-Agent": http.user_agent(version)},
            timeout=httpx.Timeout(http.request_timeout_seconds, connect=http.connect_timeout_seconds),
            follow_redirects=False,
            cookies=CookieJar(policy=DefaultCookiePolicy(allowed_domains=[])),
            trust_env=False,
            transport=transport,
        )
        return GovInfoProvider(client, api_key=api_key, clock=clock)

    return build
