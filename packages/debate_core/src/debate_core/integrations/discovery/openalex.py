"""OpenAlex, the primary scholarly discovery provider (v1-e07-t02).

:class:`OpenAlexProvider` asks OpenAlex's `/works` endpoint for a query and maps each work to a
:class:`~debate_core.domain.discovery.CandidateResult`. It is a plain adapter: the registry wraps it
in :class:`~debate_core.integrations.discovery.resilience.ResilientProvider`, which times it,
benches it after repeated failures and holds it through a rate limit. It never ranks, deduplicates
(E08) or downloads full text (ArticleService fetches an open-access URL when it wants one).

**What is kept from a work** is what `CandidateResult` defines and no more: the DOI and the OpenAlex
id, the title, the authors' display names (never their affiliations or ORCIDs), the venue, the
publication date, the work's type as a :class:`~debate_core.domain.enums.SourceType`, the abstract,
the best open-access URL, whether OpenAlex says the work is open (`open_access.is_oa`) and its
citation count (`cited_by_count`). A work with no title or no OpenAlex id is not a candidate and is
skipped; any other field OpenAlex leaves out, or sends in a shape this module does not read, is left
empty rather than failing the search.

**The abstract** arrives as an inverted index, word to positions, because OpenAlex does not ship
plain-text abstracts. :func:`rebuild_abstract` puts each word back at its positions. It is a
snippet for discovery only: card evidence comes from a stored snapshot, never from here.

**The venue** is `primary_location.source.display_name`. OpenAlex removed `host_venue`.

**The request** is one `GET /works` (:func:`works_parameters`): `search=` the query, the date window
as `from_publication_date`/`to_publication_date` filters, `per_page` and a `select=` of the fields
mapped here. OpenAlex serves at most 100 works a page and this adapter asks for one page, so a query
whose `max_results` is above 100 returns at most 100 results.

**Authentication** (PM ruling 2026-10-21). OpenAlex retired its `mailto` polite pool in February
2026 and now ignores `mailto`; a free API key replaced it (help.openalex.org/api/deprecations and
/api/authentication, read 2026-10-21). When `providers.openalex_api_key` is set it is sent as
`Authorization: Bearer <key>`, a header rather than the documented `api_key=` parameter so that it
never appears in a URL, and httpx's request log line never carries it. Without a key the request
goes out bare and OpenAlex still answers, on a smaller budget: about 100 searches a day rather than
1,000. The contact email is never sent to OpenAlex.

**Refusals** go through :func:`~debate_core.integrations.discovery.http_failures.provider_error_for_status`.
OpenAlex answers `429` both to more requests a second than the plan allows and to a spent daily
budget, so a spent budget looks like any other rate limit: :class:`ProviderRateLimited`, carrying
the `Retry-After` when OpenAlex sends one, and the wrapper's cool-down when it does not.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from http.cookiejar import CookieJar, DefaultCookiePolicy
from types import MappingProxyType
from typing import Any, Final, cast
from urllib.parse import urlsplit

import httpx
from pydantic import SecretStr, ValidationError

from debate_core.application.errors import ProviderUnavailable
from debate_core.application.ports.providers import Clock
from debate_core.application.settings import HttpSettings, ProviderSettings
from debate_core.domain.article import ArticleIdentifiers
from debate_core.domain.discovery import CandidateResult, ProviderQuery, ProviderResponse
from debate_core.domain.enums import SourceType
from debate_core.integrations.discovery.http_failures import provider_error_for_status
from debate_core.integrations.discovery.redaction import protect_logs

__all__ = [
    "MAX_PER_PAGE",
    "OPENALEX_WORKS_URL",
    "PROVIDER_NAME",
    "SELECTED_FIELDS",
    "SOURCE_TYPE_BY_WORK_TYPE",
    "OpenAlexProvider",
    "candidate_from_work",
    "openalex_factory",
    "rebuild_abstract",
    "source_type_for",
    "works_parameters",
]

PROVIDER_NAME: Final = "openalex"
"""The name settings enable this provider by, and every result carries."""

OPENALEX_WORKS_URL: Final = "https://api.openalex.org/works"
"""The works list endpoint."""

MAX_PER_PAGE: Final = 100
"""OpenAlex's largest page (help.openalex.org/api/paging; 200 is deprecated)."""

SELECTED_FIELDS: Final = (
    "id",
    "doi",
    "display_name",
    "publication_date",
    "type",
    "cited_by_count",
    "open_access",
    "best_oa_location",
    "primary_location",
    "authorships",
    "abstract_inverted_index",
)
"""The root-level work fields :func:`candidate_from_work` reads; `select=` takes nothing nested."""

SOURCE_TYPE_BY_WORK_TYPE: Final[Mapping[str, SourceType]] = MappingProxyType(
    {
        "article": SourceType.SCHOLARLY,
        "book": SourceType.SCHOLARLY,
        "book-chapter": SourceType.SCHOLARLY,
        "book-review": SourceType.SCHOLARLY,
        "conference-abstract": SourceType.SCHOLARLY,
        "conference-paper": SourceType.SCHOLARLY,
        "data-paper": SourceType.SCHOLARLY,
        "dissertation": SourceType.SCHOLARLY,
        "editorial": SourceType.SCHOLARLY,
        "erratum": SourceType.SCHOLARLY,
        "letter": SourceType.SCHOLARLY,
        "peer-review": SourceType.SCHOLARLY,
        "preprint": SourceType.SCHOLARLY,
        "reference-entry": SourceType.SCHOLARLY,
        "retraction": SourceType.SCHOLARLY,
        "review": SourceType.SCHOLARLY,
        "software-paper": SourceType.SCHOLARLY,
        "report": SourceType.OTHER,
        "standard": SourceType.OTHER,
        "dataset": SourceType.OTHER,
        "libguides": SourceType.OTHER,
        "other": SourceType.OTHER,
        "paratext": SourceType.OTHER,
        "software": SourceType.OTHER,
        "supplementary-materials": SourceType.OTHER,
    }
)
"""OpenAlex's work types (help.openalex.org/data/work-types, read 2026-10-21) as source types.

Journal, book, conference and thesis content is scholarly. A `report` or a `standard` is `other`,
because its issuer may be a government, a think tank or a company and the work type does not say
which; data, code, front matter and library guides are not publications at all. A type OpenAlex adds
later is `other` until it is added here (:func:`source_type_for`).
"""


def source_type_for(work_type: object) -> SourceType:
    """The source type for an OpenAlex work type; `other` for any type not in the table."""
    if not isinstance(work_type, str):
        return SourceType.OTHER
    return SOURCE_TYPE_BY_WORK_TYPE.get(work_type, SourceType.OTHER)


def rebuild_abstract(inverted_index: object) -> str | None:
    """The abstract an OpenAlex `abstract_inverted_index` encodes, words in order; `None` when empty.

    The index maps each word to the positions it occupies (`{"in": [3, 57]}`). Every word goes back
    at each of its positions and the words are joined by single spaces in position order, which is
    how OpenAlex itself documents reading it. Entries that are not a word with a list of
    non-negative integer positions are ignored.
    """
    if not isinstance(inverted_index, Mapping):
        return None
    placed: dict[int, str] = {}
    for word, positions in cast(Mapping[object, object], inverted_index).items():
        if not isinstance(word, str) or not isinstance(positions, list):
            continue
        for position in cast(list[object], positions):
            if isinstance(position, int) and not isinstance(position, bool) and position >= 0:
                placed[position] = word
    text = " ".join(placed[position] for position in sorted(placed)).strip()
    return text or None


def candidate_from_work(work: Mapping[str, Any]) -> CandidateResult | None:
    """One OpenAlex work as a candidate; `None` for a work with no title or no OpenAlex id."""
    openalex_id = _openalex_id(work.get("id"))
    title = _text(work.get("display_name"))
    if openalex_id is None or title is None:
        return None
    doi = _doi(work.get("doi"))
    primary = _mapping(work.get("primary_location"))
    url = _http_url(primary.get("landing_page_url")) or (f"https://doi.org/{doi}" if doi else None)
    return CandidateResult(
        provider=PROVIDER_NAME,
        provider_record_id=openalex_id,
        title=title,
        url=url or f"https://openalex.org/{openalex_id}",
        identifiers=ArticleIdentifiers(doi=doi, openalex_id=openalex_id),
        source_type=source_type_for(work.get("type")),
        authors=_author_names(work.get("authorships")),
        publication=_text(_mapping(primary.get("source")).get("display_name")),
        published_at=_publication_date(work.get("publication_date")),
        snippet=rebuild_abstract(work.get("abstract_inverted_index")),
        open_access_url=_open_access_url(work),
        open_access=_is_open_access(work),
        citation_count=_citation_count(work.get("cited_by_count")),
    )


def _open_access_url(work: Mapping[str, Any]) -> str | None:
    """The best open copy: OpenAlex's best OA location, its PDF before its landing page.

    Falls back to `open_access.oa_url`, OpenAlex's own pick, when the work is open but carries no
    best location. A location that is not itself open is never used.
    """
    best = _mapping(work.get("best_oa_location"))
    if best.get("is_oa") is True:
        found = _http_url(best.get("pdf_url")) or _http_url(best.get("landing_page_url"))
        if found is not None:
            return found
    status = _mapping(work.get("open_access"))
    if status.get("is_oa") is True:
        return _http_url(status.get("oa_url"))
    return None


def _is_open_access(work: Mapping[str, Any]) -> bool | None:
    """OpenAlex's `open_access.is_oa`: open even when no usable link is known; `None` when unsaid."""
    is_oa = _mapping(work.get("open_access")).get("is_oa")
    return is_oa if isinstance(is_oa, bool) else None


def _citation_count(value: object) -> int | None:
    """`cited_by_count` when it is a non-negative integer; anything else is unknown, not a failure."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _author_names(authorships: object) -> tuple[str, ...]:
    """The display names of the disambiguated authors, in byline order; nothing else of theirs."""
    if not isinstance(authorships, list):
        return ()
    names: list[str] = []
    for authorship in cast(list[object], authorships):
        name = _text(_mapping(_mapping(authorship).get("author")).get("display_name"))
        if name is not None:
            names.append(name)
    return tuple(names)


def _openalex_id(value: object) -> str | None:
    """`W2741809807` from `https://openalex.org/W2741809807` (or from the bare id)."""
    text = _text(value)
    if text is None:
        return None
    short = text.rstrip("/").rsplit("/", 1)[-1]
    if len(short) < 2 or short[0] != "W" or not short[1:].isdigit():
        return None
    return short


def _doi(value: object) -> str | None:
    """The bare lowercase DOI, or `None` when OpenAlex sent none or one that is not a DOI."""
    text = _text(value)
    if text is None:
        return None
    try:
        return ArticleIdentifiers(doi=text).doi
    except ValidationError:
        return None


def _publication_date(value: object) -> datetime | None:
    """Midnight UTC on OpenAlex's `YYYY-MM-DD` publication date."""
    text = _text(value)
    if text is None:
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


def _mapping(value: object) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], value) if isinstance(value, Mapping) else {}


# --------------------------------------------------------------------------------------------
# The request and the adapter
# --------------------------------------------------------------------------------------------


def works_parameters(query: ProviderQuery) -> dict[str, str]:
    """The `/works` query parameters for `query`; see the module docstring for what each one does."""
    parameters = {"search": query.query}
    window: list[str] = []
    if query.filters.since is not None:
        window.append(f"from_publication_date:{query.filters.since.date().isoformat()}")
    if query.filters.until is not None:
        window.append(f"to_publication_date:{query.filters.until.date().isoformat()}")
    if window:
        parameters["filter"] = ",".join(window)
    parameters["per_page"] = str(min(query.filters.max_results, MAX_PER_PAGE))
    parameters["select"] = ",".join(SELECTED_FIELDS)
    return parameters


class OpenAlexProvider:
    """Searches OpenAlex's works; a :class:`~debate_core.application.ports.providers.SearchProvider`.

    Sends one request per search and never retries it: the wrapper decides what happens after a
    failure. Owns `client`; close it with :meth:`aclose`.
    """

    def __init__(self, client: httpx.AsyncClient, *, api_key: SecretStr | None, clock: Clock) -> None:
        self._client = client
        self._api_key = api_key if api_key is not None and api_key.get_secret_value().strip() else None
        """The key, or `None` when none is set: an empty `DEBATE_PROVIDERS__OPENALEX_API_KEY=` is no key."""
        self._clock = clock
        if self._api_key is not None:
            protect_logs((self._api_key.get_secret_value(),))

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    def __repr__(self) -> str:
        key = "configured" if self._api_key is not None else "none"
        return f"{type(self).__name__}(api_key={key})"

    async def aclose(self) -> None:
        """Close the HTTP client and its connections."""
        await self._client.aclose()

    async def search(self, query: ProviderQuery) -> ProviderResponse:
        started = time.perf_counter()
        headers = (
            {} if self._api_key is None else {"Authorization": f"Bearer {self._api_key.get_secret_value()}"}
        )
        try:
            response = await self._client.get(
                OPENALEX_WORKS_URL, params=works_parameters(query), headers=headers
            )
        except httpx.TimeoutException as error:
            raise ProviderUnavailable(self.name, "timed out") from error
        except httpx.HTTPError as error:
            raise ProviderUnavailable(self.name, f"transport failure: {type(error).__name__}") from error
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
        works = _mapping(document).get("results")
        if not isinstance(works, list) or not all(
            isinstance(work, dict) for work in cast(list[object], works)
        ):
            raise ProviderUnavailable(self.name, "unreadable response: no list of works")
        candidates = (candidate_from_work(work) for work in cast(list[dict[str, Any]], works))
        return tuple(candidate for candidate in candidates if candidate is not None)[
            : query.filters.max_results
        ]


def openalex_factory(
    http: HttpSettings,
    *,
    version: str,
    clock: Clock,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Callable[[ProviderSettings], OpenAlexProvider]:
    """The registry's factory for `openalex`: an adapter over a client built from the HTTP settings.

    The client identifies the platform with the same User-Agent as the article fetcher, keeps no
    cookies and reads nothing from the environment (no `~/.netrc`, no proxy). Its own timeouts are
    the HTTP settings'; the wrapper's `providers.timeout_seconds` bounds the whole call. `transport`
    is for tests, which pass a mock.
    """

    def build(settings: ProviderSettings) -> OpenAlexProvider:
        client = httpx.AsyncClient(
            headers={"User-Agent": http.user_agent(version)},
            timeout=httpx.Timeout(http.request_timeout_seconds, connect=http.connect_timeout_seconds),
            follow_redirects=False,
            cookies=CookieJar(policy=DefaultCookiePolicy(allowed_domains=[])),
            trust_env=False,
            transport=transport,
        )
        return OpenAlexProvider(client, api_key=settings.openalex_api_key, clock=clock)

    return build
