"""Semantic Scholar, scholarly discovery by relevance search (v1-e07-t04).

:class:`SemanticScholarProvider` asks the Academic Graph API's paper search for a query and maps each
paper to a :class:`~debate_core.domain.discovery.CandidateResult`. It is a plain adapter: the registry
wraps it in :class:`~debate_core.integrations.discovery.resilience.ResilientProvider`, which times it,
benches it after repeated failures and holds it through a rate limit. It searches only: it follows no
citation and downloads no PDF.

**The request** is one `GET /graph/v1/paper/search` (:func:`paper_search_parameters`): `query=` the
query, `publicationDateOrYear=` the date window as `<start>:<end>` with either end open, `limit=` the
results wanted, at most :data:`MAX_PER_REQUEST` (the endpoint's own limit, so a query asks for at
most 100 even when `max_results` allows 200), and `fields=` :data:`REQUESTED_FIELDS`. The
documentation says the search takes plain text only and that "hyphenated query terms yield no
matches", so a hyphen is sent as a space (:func:`searchable_query`). This and the answer's shape
(`total`, `offset`, `next`, `data`) are from the OpenAPI description behind
api.semanticscholar.org/api-docs/graph, read 2026-11-09.

**The key.** When `providers.semantic_scholar_api_key` is set it is sent as the `x-api-key` header,
never in a URL, so httpx's request log line never carries it. The constructor still registers it
with :func:`~debate_core.integrations.discovery.redaction.protect_logs`, and no message this module
writes names it. Without a key the request goes out with no such header.

**The pace** (PM ruling of 2026-11-09). Semantic Scholar's API page (semanticscholar.org/product/api,
read by the PM 2026-11-09) gives a key 1 request a second on every endpoint, and keyless callers one
shared pool of 1,000 a second among all of them, which may be throttled under heavy use; it
publishes no stricter figure for one keyless caller. So the adapter keeps one request a second, one
at a time, with a key and without (:data:`KEYED_PACE`, :data:`KEYLESS_PACE`), on the shared
:class:`~debate_core.integrations.discovery.pace.Pacer` of v1-e07-t10. A query waits for its turn
only while its answer could still come back within `providers.timeout_seconds` of when it was
asked: until the timeout less the reserve, Crossref's rule
(:class:`~debate_core.integrations.discovery.pace.AnswerTimes`). A query still waiting then is
never sent. It is answered at its deadline with no results, marked partial, and an error naming the
pace and, without a key, what a key would and would not do. The wrapper hears from the pacer that
it was never sent and counts it "not asked", neither a failure nor a latency sample. A query whose
turn comes while the wrapper holds Semantic Scholar after a 429, or after its breaker has opened, is
refused at its turn and never sent (v1-e07-t22): on 2026-11-11 every keyless request was answered 429
and the queries behind the first were sent anyway.

**Refusals** go through :func:`~debate_core.integrations.discovery.http_failures.provider_error_for_status`:
a `429` is :class:`~debate_core.application.errors.ProviderRateLimited`, held for its `Retry-After`
when one is sent and for the wrapper's exponential backoff when not (v1-e07-t22); a `403` (a key
Semantic Scholar refuses) or any other `4xx` is a refusal; a `3xx` is a refusal naming only the host
it points to. No request is ever retried here.

**The mapping** (:func:`candidate_from_paper`):

* **the ids**: the paper id is the record id and `identifiers.semantic_scholar_id`; of `externalIds`,
  the `DOI` (normalized by :class:`~debate_core.domain.article.ArticleIdentifiers`, dropped if it is
  not a DOI), `ArXiv` and `PubMed` (digits only) are kept, and the rest (`MAG`, `DBLP`, `ACL`,
  `PubMedCentral`, `CorpusId`) are not;
* **the URL** is the DOI resolver's when there is a DOI, as for OpenAlex and Crossref, and the
  paper's Semantic Scholar page otherwise;
* **the date** is `publicationDate` to the day when it is a real `YYYY-MM-DD` date, otherwise the
  `year` at year precision, never an invented day
  (:class:`~debate_core.domain.discovery.DatePrecision`);
* **the type** is a :class:`~debate_core.domain.enums.SourceType` by
  :data:`SOURCE_TYPE_BY_PUBLICATION_TYPE` (:func:`source_type_for`);
* **open access** is `isOpenAccess` as stated, and the open copy is `openAccessPdf.url` when it is
  an absolute http(s) URL (Semantic Scholar sends an empty one for an open paper it knows no PDF
  for);
* **the abstract** is a snippet for discovery only: card evidence comes from a stored snapshot,
  never from here;
* `citationCount` is the citation count. `influentialCitationCount` is asked for, as the spec lists
  it, but `CandidateResult` has no field for it, so it is read nowhere.

Titles, names, venues and abstracts lose their extra whitespace. A paper with no title or no paper
id is not a candidate and is skipped; any other field in a shape this module does not read is left
empty rather than failing the search.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from http.cookiejar import CookieJar, DefaultCookiePolicy
from types import MappingProxyType
from typing import Any, Final, cast
from urllib.parse import quote, urlsplit

import httpx
from pydantic import SecretStr, ValidationError

from debate_core.application.errors import ProviderUnavailable
from debate_core.application.ports.providers import Clock
from debate_core.application.settings import HttpSettings, ProviderSettings
from debate_core.domain.article import ArticleIdentifiers
from debate_core.domain.discovery import CandidateResult, DatePrecision, ProviderQuery, ProviderResponse
from debate_core.domain.enums import SourceType
from debate_core.integrations.discovery.http_failures import provider_error_for_status, redirect_failure
from debate_core.integrations.discovery.pace import AnswerTimes, Pace, Pacer, Sleep
from debate_core.integrations.discovery.redaction import logger, protect_logs

__all__ = [
    "API_KEY_HEADER",
    "KEYED_PACE",
    "KEYLESS_PACE",
    "MAX_PER_REQUEST",
    "PAPER_SEARCH_URL",
    "PROVIDER_NAME",
    "REQUESTED_FIELDS",
    "SOURCE_TYPE_BY_PUBLICATION_TYPE",
    "SemanticScholarProvider",
    "candidate_from_paper",
    "paper_search_parameters",
    "searchable_query",
    "semantic_scholar_factory",
    "source_type_for",
]

PROVIDER_NAME: Final = "semantic_scholar"
"""The name settings enable this provider by, and every result carries."""

PAPER_SEARCH_URL: Final = "https://api.semanticscholar.org/graph/v1/paper/search"
"""The relevance search endpoint (not `/paper/search/bulk`)."""

PAPER_PAGE_URL: Final = "https://www.semanticscholar.org/paper/"
"""A paper's page on Semantic Scholar's site, before its paper id."""

REQUESTED_FIELDS: Final = (
    "title",
    "authors",
    "year",
    "publicationDate",
    "venue",
    "externalIds",
    "citationCount",
    "influentialCitationCount",
    "isOpenAccess",
    "openAccessPdf",
    "publicationTypes",
    "abstract",
)
"""The spec's fields list; `paperId` comes back whatever is asked."""

MAX_PER_REQUEST: Final = 100
"""The documented most `limit=` may ask for."""

API_KEY_HEADER: Final = "x-api-key"
"""The header a key travels in."""

# semanticscholar.org/product/api, read by the PM 2026-11-09: an API key's introductory rate is 1
# request a second on all endpoints; unauthenticated callers share 1,000 a second among all of them
# and may be throttled further, with no stricter per-caller figure published (PM ruling 1).
KEYED_PACE: Final = Pace(requests=1, interval_seconds=1.0, concurrency=1)
"""One request a second, one at a time: the published rate of an API key."""

KEYLESS_PACE: Final = Pace(requests=1, interval_seconds=1.0, concurrency=1)
"""The same without a key: the shared pool publishes no per-caller figure, so the keyed one is kept."""

SOURCE_TYPE_BY_PUBLICATION_TYPE: Final[Mapping[str, SourceType]] = MappingProxyType(
    {
        "review": SourceType.SCHOLARLY,
        "journalarticle": SourceType.SCHOLARLY,
        "casereport": SourceType.SCHOLARLY,
        "clinicaltrial": SourceType.SCHOLARLY,
        "conference": SourceType.SCHOLARLY,
        "editorial": SourceType.SCHOLARLY,
        "lettersandcomments": SourceType.SCHOLARLY,
        "metaanalysis": SourceType.SCHOLARLY,
        "study": SourceType.SCHOLARLY,
        "book": SourceType.SCHOLARLY,
        "booksection": SourceType.SCHOLARLY,
        "news": SourceType.NEWS,
        "dataset": SourceType.OTHER,
    }
)
"""The thirteen documented `publicationTypes` (the search's filter list), keyed without spaces or case.

The documentation spells the filter's `JournalArticle` as `Journal Article` in the field's example,
so both spellings are read. A paper is scholarly when any of its types is; otherwise news when any
is; otherwise other, a dataset or a type added later. A paper with no type at all is scholarly,
because Semantic Scholar indexes papers and leaves many untyped.
"""

_DAY: Final = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_HYPHENS: Final = re.compile(r"-+")


def source_type_for(publication_types: object) -> SourceType:
    """The source type for a paper's `publicationTypes`: :data:`SOURCE_TYPE_BY_PUBLICATION_TYPE`'s rule."""
    named = [publication_types] if isinstance(publication_types, str) else publication_types
    if not isinstance(named, list):
        return SourceType.SCHOLARLY
    kinds = [
        SOURCE_TYPE_BY_PUBLICATION_TYPE.get("".join(entry.split()).lower(), SourceType.OTHER)
        for entry in cast(list[object], named)
        if isinstance(entry, str) and entry.strip()
    ]
    if not kinds:
        return SourceType.SCHOLARLY
    for kind in (SourceType.SCHOLARLY, SourceType.NEWS):
        if kind in kinds:
            return kind
    return SourceType.OTHER


# --------------------------------------------------------------------------------------------
# Mapping a paper
# --------------------------------------------------------------------------------------------


def candidate_from_paper(paper: Mapping[str, Any]) -> CandidateResult | None:
    """One paper as a candidate; `None` for a paper with no title or no paper id."""
    paper_id = _text(paper.get("paperId"))
    title = _text(paper.get("title"))
    if paper_id is None or title is None:
        return None
    ids = _mapping(paper.get("externalIds"))
    doi = _doi(ids.get("DOI"))
    published_at, precision = _publication_date(paper.get("publicationDate"), paper.get("year"))
    pdf = _mapping(paper.get("openAccessPdf"))
    is_open = paper.get("isOpenAccess")
    return CandidateResult(
        provider=PROVIDER_NAME,
        provider_record_id=paper_id,
        title=title,
        url=f"https://doi.org/{doi}" if doi else PAPER_PAGE_URL + quote(paper_id, safe=""),
        identifiers=ArticleIdentifiers(
            doi=doi,
            arxiv_id=_text(ids.get("ArXiv")),
            pmid=_pmid(ids.get("PubMed")),
            semantic_scholar_id=paper_id,
        ),
        source_type=source_type_for(paper.get("publicationTypes")),
        authors=_author_names(paper.get("authors")),
        publication=_text(paper.get("venue")),
        published_at=published_at,
        date_precision=precision,
        snippet=_text(paper.get("abstract")),
        open_access_url=_http_url(pdf.get("url")),
        open_access=is_open if isinstance(is_open, bool) else None,
        citation_count=_citation_count(paper.get("citationCount")),
    )


def _doi(value: object) -> str | None:
    """The bare lowercase DOI, by ArticleIdentifiers' rule; `None` when it is missing or not a DOI."""
    if not isinstance(value, str):
        return None
    try:
        return ArticleIdentifiers(doi=value).doi
    except ValidationError:
        return None


def _pmid(value: object) -> str | None:
    text = _text(value)
    return text if text is not None and text.isascii() and text.isdigit() else None


def _publication_date(stated: object, year: object) -> tuple[datetime | None, DatePrecision | None]:
    """`publicationDate` to the day when it is a real date; otherwise `year` at year precision."""
    matched = _DAY.fullmatch(stated) if isinstance(stated, str) else None
    if matched is not None:
        try:
            day = date(int(matched.group(1)), int(matched.group(2)), int(matched.group(3)))
        except ValueError:
            day = None
        if day is not None:
            return datetime(day.year, day.month, day.day, tzinfo=UTC), DatePrecision.DAY
    if isinstance(year, int) and not isinstance(year, bool) and 1 <= year <= 9999:
        return datetime(year, 1, 1, tzinfo=UTC), DatePrecision.YEAR
    return None, None


def _author_names(authors: object) -> tuple[str, ...]:
    if not isinstance(authors, list):
        return ()
    names = (_text(_mapping(author).get("name")) for author in cast(list[object], authors))
    return tuple(name for name in names if name is not None)


def _citation_count(value: object) -> int | None:
    """`citationCount` when it is a non-negative integer; anything else is unknown."""
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


def _text(value: object) -> str | None:
    """A string with its whitespace runs made single spaces; `None` for anything else or nothing left."""
    if not isinstance(value, str):
        return None
    return " ".join(value.split()) or None


def _mapping(value: object) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], value) if isinstance(value, Mapping) else {}


# --------------------------------------------------------------------------------------------
# The request
# --------------------------------------------------------------------------------------------


def searchable_query(text: str) -> str:
    """`text` with each hyphen a space and whitespace runs single spaces; `text` if nothing is left."""
    return " ".join(_HYPHENS.sub(" ", text).split()) or text


def paper_search_parameters(query: ProviderQuery) -> dict[str, str]:
    """The `/paper/search` query parameters for `query`, in a fixed order."""
    parameters = {"query": searchable_query(query.query)}
    since, until = query.filters.since, query.filters.until
    if since is not None or until is not None:
        start = since.date().isoformat() if since is not None else ""
        end = until.date().isoformat() if until is not None else ""
        parameters["publicationDateOrYear"] = f"{start}:{end}"
    parameters["limit"] = str(min(query.filters.max_results, MAX_PER_REQUEST))
    parameters["fields"] = ",".join(REQUESTED_FIELDS)
    return parameters


def _rate_phrase(pace: Pace) -> str:
    """`1 query a second`, `3 queries a second`, `1 query every 2 seconds`."""
    noun = "query" if pace.requests == 1 else "queries"
    every = "a second" if pace.interval_seconds == 1 else f"every {pace.interval_seconds:g} seconds"
    return f"{pace.requests} {noun} {every}"


# --------------------------------------------------------------------------------------------
# The adapter
# --------------------------------------------------------------------------------------------


class SemanticScholarProvider:
    """Searches Semantic Scholar's papers; a :class:`~debate_core.application.ports.providers.SearchProvider`.

    Sends at most one request per search, at its pace, and never retries it: the wrapper decides what
    happens after a failure. Owns `client`; close it with :meth:`aclose`.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        api_key: SecretStr | None,
        timeout_seconds: float,
        clock: Clock,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._client = client
        key = api_key.get_secret_value().strip() if api_key is not None else ""
        self._api_key = key or None
        """The key, or `None`: a blank `DEBATE_PROVIDERS__SEMANTIC_SCHOLAR_API_KEY=` is no key."""
        if self._api_key is not None:
            protect_logs((self._api_key,))
        self._clock = clock
        self._timeout_seconds = timeout_seconds
        self._pace = KEYED_PACE if self._api_key is not None else KEYLESS_PACE
        self._pacer = Pacer(self._pace, clock=clock, sleep=sleep)
        self._answer_times = AnswerTimes()

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    @property
    def pace(self) -> Pace:
        """The pace its queries are sent at."""
        return self._pace

    @property
    def reserve_seconds(self) -> float:
        """The time a query keeps back for its answer when deciding whether it is too late to send."""
        return self._answer_times.reserve_seconds(self._timeout_seconds)

    def __repr__(self) -> str:
        key = "configured" if self._api_key is not None else "none"
        return f"{type(self).__name__}(api_key={key})"

    async def aclose(self) -> None:
        """Close the HTTP client and its connections."""
        await self._client.aclose()

    async def search(self, query: ProviderQuery) -> ProviderResponse:
        started = time.perf_counter()
        headers = {API_KEY_HEADER: self._api_key} if self._api_key is not None else {}
        async with self._pacer.turn(within=self._send_within) as sent:
            if not sent:
                return self._not_asked(started)
            sent_at = self._clock.now()
            try:
                response = await self._client.get(
                    PAPER_SEARCH_URL, params=paper_search_parameters(query), headers=headers
                )
            except httpx.TimeoutException as error:
                raise ProviderUnavailable(self.name, "timed out") from error
            except httpx.HTTPError as error:
                raise ProviderUnavailable(self.name, f"transport failure: {type(error).__name__}") from error
            self._answer_times.answered((self._clock.now() - sent_at).total_seconds())
        failure = provider_error_for_status(
            self.name, response.status_code, response.headers, now=self._clock.now()
        )
        if failure is not None:
            raise failure
        if response.is_redirect:
            raise redirect_failure(self.name, response.status_code, response.headers)
        results = self._read(response)[: query.filters.max_results]
        elapsed_ms = (time.perf_counter() - started) * 1000
        return ProviderResponse(provider=self.name, results=results, elapsed_ms=elapsed_ms)

    def _send_within(self) -> float:
        """How long after a query arrives it may still be sent: the timeout less the reserve."""
        return self._timeout_seconds - self.reserve_seconds

    def _not_asked(self, started: float) -> ProviderResponse:
        reason = f"{self.name}: not asked: the pace is {_rate_phrase(self._pace)}"
        if self._api_key is None:
            reason += "; an API key would identify this caller but raises nothing today"
        logger.info("discovery provider %s did not send a query: %s", self.name, reason)
        elapsed_ms = (time.perf_counter() - started) * 1000
        return ProviderResponse(provider=self.name, elapsed_ms=elapsed_ms, partial=True, error=reason)

    def _read(self, response: httpx.Response) -> tuple[CandidateResult, ...]:
        try:
            document = response.json()
        except ValueError as error:
            raise ProviderUnavailable(self.name, f"unreadable response: {type(error).__name__}") from error
        envelope = _mapping(document)
        data = envelope.get("data")
        if data is None and "data" not in envelope and envelope.get("total") == 0:
            return ()
        if not isinstance(data, list) or not all(
            isinstance(paper, dict) for paper in cast(list[object], data)
        ):
            raise ProviderUnavailable(self.name, "unreadable response: not a paper list")
        candidates = (candidate_from_paper(paper) for paper in cast(list[dict[str, Any]], data))
        return tuple(candidate for candidate in candidates if candidate is not None)


def semantic_scholar_factory(
    http: HttpSettings,
    *,
    version: str,
    clock: Clock,
    sleep: Sleep = asyncio.sleep,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Callable[[ProviderSettings], SemanticScholarProvider]:
    """The registry's factory for `semantic_scholar`: an adapter over a client built from the HTTP settings.

    The client identifies the platform with the article fetcher's User-Agent, keeps no cookies,
    follows no redirect and reads nothing from the environment (no `~/.netrc`, no proxy). Its own
    timeouts are the HTTP settings'; the wrapper's `providers.timeout_seconds` bounds the whole call,
    and the pacer reads it to know when a query is too late to send. `sleep` and `transport` are for
    tests, which pass virtual time and a mock.
    """

    def build(settings: ProviderSettings) -> SemanticScholarProvider:
        client = httpx.AsyncClient(
            headers={"User-Agent": http.user_agent(version)},
            timeout=httpx.Timeout(http.request_timeout_seconds, connect=http.connect_timeout_seconds),
            follow_redirects=False,
            cookies=CookieJar(policy=DefaultCookiePolicy(allowed_domains=[])),
            trust_env=False,
            transport=transport,
        )
        return SemanticScholarProvider(
            client,
            api_key=settings.semantic_scholar_api_key,
            timeout_seconds=settings.timeout_seconds,
            clock=clock,
            sleep=sleep,
        )

    return build
