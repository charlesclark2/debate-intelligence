"""Crossref, scholarly discovery by bibliographic query (v1-e07-t03).

:class:`CrossrefProvider` asks Crossref's `/works` endpoint for a query and maps each item to a
:class:`~debate_core.domain.discovery.CandidateResult`. It is a plain adapter: the registry wraps it
in :class:`~debate_core.integrations.discovery.resilience.ResilientProvider`, which times it,
benches it after repeated failures and holds it through a rate limit. Looking a DOI up for a cite
is not this module's: that is :mod:`debate_core.integrations.crossref_doi`, behind CitationService.

**The request** is one `GET /works` (:func:`works_parameters`): `query.bibliographic=` the query,
the date window as `from-pub-date`/`until-pub-date` filters, `rows` (a search asks for at most 200,
under Crossref's 1,000) and a `select=` of the fields mapped here.

**The polite pool.** When `providers.contact_email` is set it goes to Crossref twice, as Crossref
asks: as `mailto=` and in the User-Agent, `debate-research/<version> (+<project URL>; mailto:<address>)`.
Without one the request goes to the public pool, and the adapter's `repr` says so. The address is a
person's (§14): the constructor registers it with
:func:`~debate_core.integrations.discovery.redaction.protect_logs`, so httpx's request log line
carries it masked, and no message this module writes names it.

**The pace.** Crossref limits list and query requests per pool, and since 2025-12-01 the limits
are 1 a second with 1 at a time on the public pool and 3 a second with 3 at a time on the polite
pool (crossref.org/blog/announcing-changes-to-rest-api-rate-limits, read 2026-11-02; the older
figures of 5 and 10 on
crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication are its
single-record limits). Each answer also states limits in `x-rate-limit-limit`,
`x-rate-limit-interval` and `x-concurrency-limit` (the same access page), and
:func:`advertised_limits` tightens the pace to them, never loosening it past the documented ones.
The adapter queues its queries on the shared
:class:`~debate_core.integrations.discovery.pace.Pacer` (v1-e07-t10), at the pool's :attr:`PoolLimits.pace`:
first come, first served, one interval/limit apart and no more at once than the concurrency allows.

A federated search sends every query at once, so on the public pool a search of eleven queries
cannot send its eleventh before ten seconds. A query therefore waits for its turn only while its
answer could still come back within `providers.timeout_seconds` of when it was asked: until the
timeout less a **reserve**, the median time Crossref has taken to answer in this process, clamped
to at least 1 second and at most half the timeout, and 2 seconds before any answer
(:func:`~debate_core.integrations.discovery.pace.answer_reserve_seconds`, shared with Semantic
Scholar since v1-e07-t04; this module still exports it and its two constants by name). A query
still waiting then is never sent. It is answered at its deadline with no results, marked partial,
and an error naming the pool's rate (and, on the public pool, the cure: a contact email). The
search is PARTIAL and says why (PM rulings of 2026-11-02). The wrapper hears from the pacer that
the query was queued and never sent, so it counts the answer as "not asked", neither a failure nor
a latency sample, and counts no queued time towards a sent query's timeout or latency: a query that
was sent and runs slow still times out `providers.timeout_seconds` after its pace released it. A
query whose turn comes while the wrapper holds Crossref after a 429, or after its breaker has opened,
is refused at its turn and never sent (v1-e07-t22).

**Refusals** go through :func:`~debate_core.integrations.discovery.http_failures.provider_error_for_status`:
a `429` is :class:`~debate_core.application.errors.ProviderRateLimited`, held for its `Retry-After`
when Crossref sends one and for the wrapper's exponential backoff when it does not (Crossref
documents none; v1-e07-t22);
a `403`, Crossref's answer to a caller it has blocked by hand, is a refusal, `ProviderUnavailable`,
and like every request here is never retried.

**The mapping** reads an item through the DOI client's own mapping,
:func:`~debate_core.integrations.crossref_doi.work_from_message`, so titles, venues, names and date
parts are read one way in this codebase, and normalizes the DOI with
:class:`~debate_core.domain.article.ArticleIdentifiers`, the one DOI rule:

* **the date** is the first of `issued`, `published-online` and `published-print` that is a real
  date, at the precision deposited. A year or a year and month is stored at the first instant of
  that period with :class:`~debate_core.domain.discovery.DatePrecision` saying so; no day is ever
  invented;
* **authors** are "Given Family", the family name alone, or a name deposited whole (an
  organisation), in byline order; never an affiliation or an ORCID iD;
* **open access** comes only from a Creative Commons licence (a `creativecommons.org/licenses/` or
  `/publicdomain/` URL) in force on the clock's date, for any version but text mining; otherwise it
  is unknown (`None`), never inferred from a `link` entry, because those are often a publisher's
  text-mining links. The open copy is then a `link` to the licensed version, for text mining or
  unspecified use, its PDF first;
* **the abstract**, with its JATS markup and headings stripped, is a snippet for discovery only:
  card evidence comes from a stored snapshot, never from here;
* the work's **type** is a :class:`~debate_core.domain.enums.SourceType` by
  :data:`SOURCE_TYPE_BY_WORK_TYPE`, and `is-referenced-by-count` its citation count.

An item with no title or no DOI is not a candidate and is skipped; any other field in a shape this
module does not read is left empty rather than failing the search.
"""

from __future__ import annotations

import asyncio
import html
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from http.cookiejar import CookieJar, DefaultCookiePolicy
from types import MappingProxyType
from typing import Any, Final, cast
from urllib.parse import urlsplit

import httpx
from pydantic import SecretStr, ValidationError

from debate_core.application.errors import ProviderUnavailable
from debate_core.application.ports.doi_metadata import DoiDate
from debate_core.application.ports.providers import Clock
from debate_core.application.settings import HttpSettings, ProviderSettings
from debate_core.domain.article import ArticleIdentifiers
from debate_core.domain.discovery import CandidateResult, DatePrecision, ProviderQuery, ProviderResponse
from debate_core.domain.enums import SourceType
from debate_core.integrations.crossref_doi import work_from_message
from debate_core.integrations.discovery.http_failures import provider_error_for_status
from debate_core.integrations.discovery.pace import (
    DEFAULT_RESERVE_SECONDS,
    MIN_RESERVE_SECONDS,
    AnswerTimes,
    Pace,
    Pacer,
    Sleep,
    answer_reserve_seconds,
)
from debate_core.integrations.discovery.redaction import logger, protect_logs

__all__ = [
    "CROSSREF_WORKS_URL",
    "DEFAULT_RESERVE_SECONDS",
    "MIN_RESERVE_SECONDS",
    "POLITE_POOL",
    "PROVIDER_NAME",
    "PUBLIC_POOL",
    "SELECTED_FIELDS",
    "SOURCE_TYPE_BY_WORK_TYPE",
    "CrossrefProvider",
    "PoolLimits",
    "Sleep",
    "advertised_limits",
    "answer_reserve_seconds",
    "candidate_from_item",
    "crossref_factory",
    "source_type_for",
    "strip_jats",
    "user_agent",
    "works_parameters",
]

PROVIDER_NAME: Final = "crossref"
"""The name settings enable this provider by, and every result carries."""

CROSSREF_WORKS_URL: Final = "https://api.crossref.org/works"
"""The works list endpoint."""

SELECTED_FIELDS: Final = (
    "DOI",
    "title",
    "container-title",
    "author",
    "issued",
    "published-online",
    "published-print",
    "type",
    "is-referenced-by-count",
    "license",
    "link",
    "abstract",
)
"""The work fields :func:`candidate_from_item` reads."""

SOURCE_TYPE_BY_WORK_TYPE: Final[Mapping[str, SourceType]] = MappingProxyType(
    {
        "journal-article": SourceType.SCHOLARLY,
        "proceedings-article": SourceType.SCHOLARLY,
        "posted-content": SourceType.SCHOLARLY,
        "book": SourceType.SCHOLARLY,
        "monograph": SourceType.SCHOLARLY,
        "edited-book": SourceType.SCHOLARLY,
        "reference-book": SourceType.SCHOLARLY,
        "book-chapter": SourceType.SCHOLARLY,
        "book-section": SourceType.SCHOLARLY,
        "book-part": SourceType.SCHOLARLY,
        "book-track": SourceType.SCHOLARLY,
        "reference-entry": SourceType.SCHOLARLY,
        "dissertation": SourceType.SCHOLARLY,
        "peer-review": SourceType.SCHOLARLY,
        "report": SourceType.OTHER,
        "report-component": SourceType.OTHER,
        "standard": SourceType.OTHER,
        "dataset": SourceType.OTHER,
        "database": SourceType.OTHER,
        "component": SourceType.OTHER,
        "grant": SourceType.OTHER,
        "other": SourceType.OTHER,
        "journal": SourceType.OTHER,
        "journal-volume": SourceType.OTHER,
        "journal-issue": SourceType.OTHER,
        "proceedings": SourceType.OTHER,
        "proceedings-series": SourceType.OTHER,
        "book-series": SourceType.OTHER,
        "book-set": SourceType.OTHER,
        "report-series": SourceType.OTHER,
    }
)
"""Crossref's thirty work types (its `/types` list, as Crossref staff gave it on
community.crossref.org/t/api-filter-exclude-type/4285, 2023-11-03) as source types.

Articles, chapters, books, preprints (`posted-content`), theses and published peer reviews are
scholarly. A `report` or a `standard` is `other`, because its issuer may be a government, a think
tank or a company and the type does not say which, as for OpenAlex. Data, grants, components and
the records of whole journals, issues, proceedings and series are not sources to cut from. A type
Crossref adds later is `other` until it is added here (:func:`source_type_for`).
"""

_DATE_KINDS: Final = ("issued", "published-online", "published-print")
_CREATIVE_COMMONS_HOSTS: Final = frozenset({"creativecommons.org", "www.creativecommons.org"})
_CREATIVE_COMMONS_PATHS: Final = ("/licenses/", "/publicdomain/")
_OPEN_COPY_USES: Final = frozenset({"text-mining", "unspecified"})
_JATS_HEADING: Final = re.compile(r"<jats:title\b[^>]*>.*?</jats:title>", re.IGNORECASE | re.DOTALL)
_JATS_BLOCK: Final = re.compile(r"</?jats:(?:p|sec|list|list-item|disp-quote)\b[^>]*>", re.IGNORECASE)
_ANY_TAG: Final = re.compile(r"<[^>]+>")
_INTERVAL: Final = re.compile(r"(\d+(?:\.\d+)?)s?")


def source_type_for(work_type: object) -> SourceType:
    """The source type for a Crossref work type; `other` for any type not in the table."""
    if not isinstance(work_type, str):
        return SourceType.OTHER
    return SOURCE_TYPE_BY_WORK_TYPE.get(work_type, SourceType.OTHER)


def strip_jats(abstract: object) -> str | None:
    """A JATS abstract as plain text, without its headings; `None` when nothing is left.

    Headings (`<jats:title>`, "Abstract" itself among them) are dropped with their text, a block
    element's edge becomes a space, any other tag goes, entities are decoded and whitespace runs
    become one space.
    """
    if not isinstance(abstract, str):
        return None
    text = _ANY_TAG.sub("", _JATS_BLOCK.sub(" ", _JATS_HEADING.sub(" ", abstract)))
    return " ".join(html.unescape(text).split()) or None


# --------------------------------------------------------------------------------------------
# Mapping an item
# --------------------------------------------------------------------------------------------


def candidate_from_item(item: Mapping[str, Any], *, now: datetime) -> CandidateResult | None:
    """One Crossref item as a candidate; `None` for an item with no title or no DOI.

    `now` decides whether a licence is in force yet.
    """
    doi = _doi(item.get("DOI"))
    if doi is None:
        return None
    work = work_from_message(item, requested_doi=doi)
    if work.title is None:
        return None
    published_at, precision = _publication_date(work.dates)
    licensed = _open_licence_versions(item.get("license"), now=now)
    return CandidateResult(
        provider=PROVIDER_NAME,
        provider_record_id=doi,
        title=work.title,
        url=f"https://doi.org/{doi}",
        identifiers=ArticleIdentifiers(doi=doi),
        source_type=source_type_for(item.get("type")),
        authors=tuple(name for author in work.authors if (name := author.display_name) is not None),
        publication=work.container_title,
        published_at=published_at,
        date_precision=precision,
        snippet=strip_jats(item.get("abstract")),
        open_access_url=_open_copy(item.get("link"), licensed) if licensed else None,
        open_access=True if licensed else None,
        citation_count=_citation_count(item.get("is-referenced-by-count")),
    )


def _doi(value: object) -> str | None:
    """The bare lowercase DOI, by ArticleIdentifiers' rule; `None` when it is missing or not a DOI."""
    if not isinstance(value, str):
        return None
    try:
        return ArticleIdentifiers(doi=value).doi
    except ValidationError:
        return None


def _publication_date(dates: tuple[DoiDate, ...]) -> tuple[datetime | None, DatePrecision | None]:
    """The first of issued, online and print that is a real date, at its start, with its precision."""
    by_kind = {stated.kind: stated for stated in dates}
    for kind in _DATE_KINDS:
        stated = by_kind.get(kind)
        if stated is None:
            continue
        if stated.month is None:
            return datetime(stated.year, 1, 1, tzinfo=UTC), DatePrecision.YEAR
        if stated.day is None:
            return datetime(stated.year, stated.month, 1, tzinfo=UTC), DatePrecision.MONTH
        day = stated.whole_date
        if day is not None:
            return datetime(day.year, day.month, day.day, tzinfo=UTC), DatePrecision.DAY
    return None, None


def _open_licence_versions(licences: object, *, now: datetime) -> frozenset[str]:
    """The content versions a Creative Commons licence in force at `now` covers; empty for none."""
    versions: set[str] = set()
    for entry in _list(licences):
        licence = _mapping(entry)
        version = licence.get("content-version")
        if (
            isinstance(version, str)
            and version != "tdm"
            and _is_creative_commons(licence.get("URL"))
            and (start := _licence_start(licence.get("start"))) is not None
            and start <= now
        ):
            versions.add(version)
    return frozenset(versions)


def _is_creative_commons(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parts = urlsplit(value.strip())
    return (
        parts.scheme in ("http", "https")
        and parts.hostname in _CREATIVE_COMMONS_HOSTS
        and parts.path.startswith(_CREATIVE_COMMONS_PATHS)
    )


def _licence_start(value: object) -> datetime | None:
    stated = _mapping(value).get("date-time")
    if not isinstance(stated, str):
        return None
    try:
        start = datetime.fromisoformat(stated)
    except ValueError:
        return None
    return start if start.tzinfo is not None else None


def _open_copy(links: object, versions: frozenset[str]) -> str | None:
    """A link to a licensed version for text mining or unspecified use, its PDF first."""
    usable: list[tuple[bool, str]] = []
    for entry in _list(links):
        link = _mapping(entry)
        url = _http_url(link.get("URL"))
        if url is None or link.get("content-version") not in versions:
            continue
        if link.get("intended-application") not in _OPEN_COPY_USES:
            continue
        usable.append((link.get("content-type") != "application/pdf", url))
    return min(usable)[1] if usable else None


def _citation_count(value: object) -> int | None:
    """`is-referenced-by-count` when it is a non-negative integer; anything else is unknown."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _http_url(value: object) -> str | None:
    """`value` when it is a URL `CandidateResult` accepts: absolute http(s), with a host, no spaces."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or any(character.isspace() for character in text):
        return None
    parts = urlsplit(text)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return text


def _mapping(value: object) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], value) if isinstance(value, Mapping) else {}


def _list(value: object) -> list[object]:
    return cast(list[object], value) if isinstance(value, list) else []


# --------------------------------------------------------------------------------------------
# The request
# --------------------------------------------------------------------------------------------


def works_parameters(query: ProviderQuery, *, contact_email: str | None) -> dict[str, str]:
    """The `/works` query parameters for `query`, with `mailto=` last when an address is set."""
    parameters = {"query.bibliographic": query.query}
    window: list[str] = []
    if query.filters.since is not None:
        window.append(f"from-pub-date:{query.filters.since.date().isoformat()}")
    if query.filters.until is not None:
        window.append(f"until-pub-date:{query.filters.until.date().isoformat()}")
    if window:
        parameters["filter"] = ",".join(window)
    parameters["rows"] = str(query.filters.max_results)
    parameters["select"] = ",".join(SELECTED_FIELDS)
    if contact_email is not None:
        parameters["mailto"] = contact_email
    return parameters


def user_agent(http: HttpSettings, version: str, *, contact_email: str | None) -> str:
    """The article fetcher's User-Agent, with `; mailto:<address>` inside its comment when one is set."""
    if contact_email is None:
        return http.user_agent(version)
    return f"{http.user_agent_product}/{version} (+{http.contact_url}; mailto:{contact_email})"


# --------------------------------------------------------------------------------------------
# The pace
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PoolLimits:
    """How fast one pool may be asked: `requests` per `interval_seconds`, `concurrency` at a time."""

    pool: str
    requests: int
    interval_seconds: float
    concurrency: int

    @property
    def pace(self) -> Pace:
        """These limits as the shared pacer keeps them: evenly spaced starts, `concurrency` at a time."""
        return Pace(
            requests=self.requests, interval_seconds=self.interval_seconds, concurrency=self.concurrency
        )

    def rate_phrase(self) -> str:
        """`1 query a second`, `3 queries a second`, `1 query every 2 seconds`."""
        noun = "query" if self.requests == 1 else "queries"
        every = "a second" if self.interval_seconds == 1 else f"every {self.interval_seconds:g} seconds"
        return f"{self.requests} {noun} {every}"


PUBLIC_POOL: Final = PoolLimits(pool="public", requests=1, interval_seconds=1.0, concurrency=1)
"""Crossref's documented list-request limits without a contact email, since 2025-12-01."""

POLITE_POOL: Final = PoolLimits(pool="polite", requests=3, interval_seconds=1.0, concurrency=3)
"""Crossref's documented list-request limits with a contact email, since 2025-12-01."""


def advertised_limits(documented: PoolLimits, headers: Mapping[str, str]) -> PoolLimits:
    """`documented`, tightened to what an answer's rate-limit headers state; never loosened.

    The rate counts only when both `x-rate-limit-limit` and `x-rate-limit-interval` are readable
    (a positive whole number, and positive seconds, `1s` or `1`) and slower than the documented
    one; `x-concurrency-limit` counts when it is a positive whole number below the documented one.
    """
    found = {key.lower(): value.strip() for key, value in headers.items()}
    limits = documented
    requests = _positive_int(found.get("x-rate-limit-limit"))
    interval = _interval_seconds(found.get("x-rate-limit-interval"))
    slower = (
        requests is not None
        and interval is not None
        and requests / interval < documented.requests / documented.interval_seconds
    )
    if slower:
        limits = replace(limits, requests=requests, interval_seconds=interval)
    concurrency = _positive_int(found.get("x-concurrency-limit"))
    if concurrency is not None and concurrency < documented.concurrency:
        limits = replace(limits, concurrency=concurrency)
    return limits


def _positive_int(value: str | None) -> int | None:
    if value is None or not value.isdigit() or int(value) < 1:
        return None
    return int(value)


def _interval_seconds(value: str | None) -> float | None:
    matched = _INTERVAL.fullmatch(value) if value is not None else None
    if matched is None or float(matched.group(1)) <= 0:
        return None
    return float(matched.group(1))


# --------------------------------------------------------------------------------------------
# The adapter
# --------------------------------------------------------------------------------------------


class CrossrefProvider:
    """Searches Crossref's works; a :class:`~debate_core.application.ports.providers.SearchProvider`.

    Sends at most one request per search, at the pool's pace, and never retries it: the wrapper
    decides what happens after a failure. Owns `client`; close it with :meth:`aclose`.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        contact_email: SecretStr | None,
        timeout_seconds: float,
        clock: Clock,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._client = client
        email = contact_email.get_secret_value().strip() if contact_email is not None else ""
        self._contact_email = email or None
        """The address, or `None` when none is set: an empty `DEBATE_PROVIDERS__CONTACT_EMAIL=` is none."""
        self._clock = clock
        if self._contact_email is not None:
            protect_logs((self._contact_email,))
        self._documented = POLITE_POOL if self._contact_email is not None else PUBLIC_POOL
        self._limits = self._documented
        self._timeout_seconds = timeout_seconds
        self._pacer = Pacer(self._documented.pace, clock=clock, sleep=sleep)
        self._answer_times = AnswerTimes()

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    @property
    def limits(self) -> PoolLimits:
        """The pace now: the pool's documented limits, tightened by the last answer's headers."""
        return self._limits

    @property
    def reserve_seconds(self) -> float:
        """The time a query keeps back for its answer when deciding whether it is too late to send."""
        return self._answer_times.reserve_seconds(self._timeout_seconds)

    def __repr__(self) -> str:
        contact = "configured" if self._contact_email is not None else "none"
        return f"{type(self).__name__}(contact_email={contact}, pool={self._limits.pool})"

    async def aclose(self) -> None:
        """Close the HTTP client and its connections."""
        await self._client.aclose()

    async def search(self, query: ProviderQuery) -> ProviderResponse:
        started = time.perf_counter()
        async with self._pacer.turn(within=self._send_within) as sent:
            if not sent:
                return self._not_asked(started)
            sent_at = self._clock.now()
            try:
                response = await self._client.get(
                    CROSSREF_WORKS_URL, params=works_parameters(query, contact_email=self._contact_email)
                )
            except httpx.TimeoutException as error:
                raise ProviderUnavailable(self.name, "timed out") from error
            except httpx.HTTPError as error:
                raise ProviderUnavailable(self.name, f"transport failure: {type(error).__name__}") from error
            self._answered((self._clock.now() - sent_at).total_seconds(), response.headers)
        failure = provider_error_for_status(
            self.name, response.status_code, response.headers, now=self._clock.now()
        )
        if failure is not None:
            raise failure
        results = self._read(response, query)
        elapsed_ms = (time.perf_counter() - started) * 1000
        return ProviderResponse(provider=self.name, results=results, elapsed_ms=elapsed_ms)

    def _send_within(self) -> float:
        """How long after a query arrives it may still be sent: the timeout less the reserve."""
        return self._timeout_seconds - self.reserve_seconds

    def _answered(self, seconds: float, headers: Mapping[str, str]) -> None:
        """An answer came back after `seconds`: keep its time, and pace to the limits it advertised."""
        self._answer_times.answered(seconds)
        self._limits = advertised_limits(self._documented, headers)
        self._pacer.retune(self._limits.pace)

    def _not_asked(self, started: float) -> ProviderResponse:
        limits = self._limits
        reason = f"{self.name}: not asked: the {limits.pool} pool allows {limits.rate_phrase()}"
        if limits.pool == PUBLIC_POOL.pool:
            reason += "; set a contact email for the polite pool"
        logger.info("discovery provider %s did not send a query: %s", self.name, reason)
        elapsed_ms = (time.perf_counter() - started) * 1000
        return ProviderResponse(provider=self.name, elapsed_ms=elapsed_ms, partial=True, error=reason)

    def _read(self, response: httpx.Response, query: ProviderQuery) -> tuple[CandidateResult, ...]:
        try:
            document = response.json()
        except ValueError as error:
            raise ProviderUnavailable(self.name, f"unreadable response: {type(error).__name__}") from error
        envelope = _mapping(document)
        items = _mapping(envelope.get("message")).get("items")
        if (
            envelope.get("status") != "ok"
            or envelope.get("message-type") != "work-list"
            or not isinstance(items, list)
            or not all(isinstance(item, dict) for item in cast(list[object], items))
        ):
            raise ProviderUnavailable(self.name, "unreadable response: not a work list")
        now = self._clock.now()
        candidates = (candidate_from_item(item, now=now) for item in cast(list[dict[str, Any]], items))
        return tuple(candidate for candidate in candidates if candidate is not None)[
            : query.filters.max_results
        ]


def crossref_factory(
    http: HttpSettings,
    *,
    version: str,
    clock: Clock,
    sleep: Sleep = asyncio.sleep,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Callable[[ProviderSettings], CrossrefProvider]:
    """The registry's factory for `crossref`: an adapter over a client built from the HTTP settings.

    The client identifies the platform as the article fetcher does, with the contact email added
    when one is set, keeps no cookies and reads nothing from the environment (no `~/.netrc`, no
    proxy). Its own timeouts are the HTTP settings'; the wrapper's `providers.timeout_seconds`
    bounds the whole call, and the pacer reads it to know when a query is too late to send.
    `sleep` and `transport` are for tests, which pass virtual time and a mock.
    """

    def build(settings: ProviderSettings) -> CrossrefProvider:
        email = (
            settings.contact_email.get_secret_value().strip() if settings.contact_email is not None else ""
        )
        client = httpx.AsyncClient(
            headers={"User-Agent": user_agent(http, version, contact_email=email or None)},
            timeout=httpx.Timeout(http.request_timeout_seconds, connect=http.connect_timeout_seconds),
            follow_redirects=False,
            cookies=CookieJar(policy=DefaultCookiePolicy(allowed_domains=[])),
            trust_env=False,
            transport=transport,
        )
        return CrossrefProvider(
            client,
            contact_email=settings.contact_email,
            timeout_seconds=settings.timeout_seconds,
            clock=clock,
            sleep=sleep,
        )

    return build
