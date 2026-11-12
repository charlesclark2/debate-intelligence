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

**The request** is `GET /works` (:func:`works_parameters`): `search=` the query, the date window
as `from_publication_date`/`to_publication_date` filters, `per_page` and a `select=` of the fields
mapped here. OpenAlex serves at most 100 works a page, so a query whose `max_results` is above 100
asks for pages (`page=1`, `page=2`, …, 100 works each) until it has `max_results` works or a page
comes back short; OpenAlex pages no further than 10,000 works. Each page is one billed request.

**Every query of a search in one request** (v1-e08-t10; the PM read OpenAlex's searching guide,
2026-11-04). The adapter is a
:class:`~debate_core.application.ports.providers.MultiQuerySearchProvider`. :func:`works_requests`
joins the queries that share their filters into one `search=`, each in parentheses and joined by
`OR`: OpenAlex ANDs the words of a group, as it does a query asked alone, and a query is kept
unquoted, as today. A search over 1,500 characters, or a URL over about 4 KB, is refused with `400`,
so the joined queries are split into the fewest requests whose search stays within
:data:`MAX_SEARCH_CHARS` and whose URL stays within :data:`MAX_URL_CHARS` (v1-e08-t20). A query
that could reach outside its parentheses (:func:`asked_alone`) is sent in a request of its own, as
typed. A joined request OpenAlex still refuses with `400` is split in halves and asked again
(:meth:`OpenAlexProvider._halves`). A result says nothing about which group it matched (only a
relevance score), so :func:`answered_queries` attributes each work by the feeds' rule: a query
answered it when every one of its words is in the work's title or abstract. A work that matches no
query's words answered the joined search, and goes to every query
of its request; one that matches several goes to each of them. When one request of several fails,
the queries it carried get an empty, partial answer naming why; when all fail, the first failure is
raised. A rate limit fails the whole call, so that the wrapper holds OpenAlex off as asked.

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
the `Retry-After` when OpenAlex sends one, and the wrapper's exponential backoff when it does not
(v1-e07-t22): 2 s, then 4 s, and the third 429 in a row opens the breaker for its cool-down.
"""

from __future__ import annotations

import math
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from http.cookiejar import CookieJar, DefaultCookiePolicy
from types import MappingProxyType
from typing import Any, Final, cast
from urllib.parse import urlsplit

import httpx
from pydantic import SecretStr, ValidationError

from debate_core.application.errors import ProviderError, ProviderRateLimited, ProviderUnavailable
from debate_core.application.ports.providers import Clock
from debate_core.application.settings import HttpSettings, ProviderSettings
from debate_core.domain.article import ArticleIdentifiers
from debate_core.domain.discovery import CandidateResult, ProviderQuery, ProviderResponse
from debate_core.domain.enums import SourceType
from debate_core.integrations.discovery.feeds import query_terms, text_matches_terms
from debate_core.integrations.discovery.http_failures import provider_error_for_status
from debate_core.integrations.discovery.redaction import logger, protect_logs

__all__ = [
    "MAX_PAGED_RESULTS",
    "MAX_PER_PAGE",
    "MAX_SEARCH_CHARS",
    "MAX_URL_CHARS",
    "OPENALEX_WORKS_URL",
    "PROVIDER_NAME",
    "SELECTED_FIELDS",
    "SOURCE_TYPE_BY_WORK_TYPE",
    "OpenAlexProvider",
    "WorksRequest",
    "answered_queries",
    "asked_alone",
    "asked_alone_note",
    "candidate_from_work",
    "joined_search",
    "openalex_factory",
    "rebuild_abstract",
    "source_type_for",
    "works_parameters",
    "works_requests",
    "works_url",
]

PROVIDER_NAME: Final = "openalex"
"""The name settings enable this provider by, and every result carries."""

OPENALEX_WORKS_URL: Final = "https://api.openalex.org/works"
"""The works list endpoint."""

MAX_PER_PAGE: Final = 100
"""OpenAlex's largest page (help.openalex.org/api/paging; 200 is deprecated)."""

MAX_PAGED_RESULTS: Final = 10_000
"""The furthest `page=` paging reaches: page × per_page may not pass it (help.openalex.org/api/paging)."""

MAX_SEARCH_CHARS: Final = 1_500
"""The longest `search=` sent, in characters: OpenAlex refuses a longer one with `400`.

Measured by the operator on 2026-11-12 (v1-e08-t20), on v1.1.0-dev.407 with the free key, joining the
first N of the NHI politics DA link search's 37 queries: 24 (a search of 1,473 characters, a URL of
1,835) were answered and 25 (1,536 and 1,902) refused, with "Your search is too long (1536 characters;
the limit is 1500)". The same 25 were refused without the key and on page 2; their words in 13 groups
(1,476 characters) and 25 groups of one word each (338) were answered, so neither the number of OR
groups nor the URL is what OpenAlex refused. OpenAlex says a paid plan takes longer searches. The 37
queries' 2,272 characters, under :data:`MAX_URL_CHARS` at 2,686 of URL, were refused on 2026-11-11."""

MAX_URL_CHARS: Final = 3_500
"""The longest request URL sent. OpenAlex refuses one over about 4 KB with `400` and suggests splitting
an `OR` list into chunks (developers.openalex.org/guides/searching, read by the PM 2026-11-04).

Kept beside :data:`MAX_SEARCH_CHARS`, which binds first on plain text (1,500 characters of search came
to about 1,860 of URL in the measurement of 2026-11-12): a search whose characters encode long, such
as accented letters at six URL characters each, can reach this one first."""

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


def works_parameters(query: ProviderQuery, *, page: int | None = None) -> dict[str, str]:
    """The `/works` query parameters for `query`; see the module docstring for what each one does.

    `page` is sent only when the query pages, that is when its `max_results` is above 100.
    """
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
    if page is not None:
        parameters["page"] = str(page)
    return parameters


def page_count(query: ProviderQuery) -> int:
    """How many pages `query` may ask for: enough for its `max_results`, to OpenAlex's 10,000 at most."""
    return math.ceil(min(query.filters.max_results, MAX_PAGED_RESULTS) / MAX_PER_PAGE)


def works_url(parameters: Mapping[str, str]) -> str:
    """The request URL for `parameters`, encoded as the client sends it."""
    return str(httpx.URL(OPENALEX_WORKS_URL, params=dict(parameters)))


def asked_alone(text: str) -> bool:
    """Whether a query is sent in a request of its own, never joined with others (v1-e08-t20).

    Inside `(q1) OR (q2)` a query's text could reach outside its own parentheses: an unbalanced
    parenthesis (by count, or one closed before it is opened), an odd number of double quotes, or
    an upper-case `AND`, `OR` or `NOT` word outside a quoted phrase (OpenAlex reads only upper case).
    Such a query is asked alone and as typed, so it means what it would mean asked alone, and it
    cannot change or fail the others. A parenthesis inside a quoted phrase still counts: asking a
    query alone is never wrong, only one request dearer.
    """
    if text.count('"') % 2:
        return True
    depth = 0
    for character in text:
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth < 0:
                return True
    if depth:
        return True
    return _OPERATOR_WORD.search(_QUOTED_PHRASE.sub(" ", text)) is not None


_QUOTED_PHRASE: Final = re.compile(r'"[^"]*"')
_OPERATOR_WORD: Final = re.compile(r'(?<![^\s()"])(?:AND|OR|NOT)(?![^\s()"])')
"""An operator as a word of its own: bounded by the text's ends, spaces, parentheses or quotes."""


def asked_alone_note(count: int) -> str:
    """The note each query asked alone carries, which the footer prints once."""
    noun = "query" if count == 1 else "queries"
    return (
        f"{count} {noun} asked alone, not joined: an unbalanced parenthesis or double quote, "
        "or an AND, OR or NOT"
    )


def joined_search(queries: Sequence[ProviderQuery]) -> str:
    """One `search=` for `queries`: a single query as it is, several each in parentheses, joined by `OR`."""
    if len(queries) == 1:
        return queries[0].query
    return " OR ".join(f"({query.query})" for query in queries)


@dataclass(frozen=True, slots=True)
class WorksRequest:
    """One joined search: the query it sends, and the positions of the search's queries it carries."""

    query: ProviderQuery
    answers: tuple[int, ...]


def works_requests(queries: Sequence[ProviderQuery]) -> tuple[WorksRequest, ...]:
    """The fewest joined searches that ask every query: one per filters, split to fit OpenAlex's limits.

    Queries with the same filters (date window, result cap) share a request, in the order they
    first appear; each request's search stays within :data:`MAX_SEARCH_CHARS` and its URL, at its last
    page, within :data:`MAX_URL_CHARS`. The split is greedy in order, so it is the fewest. A query too long to
    fit with any other is a request of its own, as it would be asked alone. A query
    :func:`asked_alone` names is a request of its own, after its filters' joined requests.
    """
    groups: dict[object, list[int]] = {}
    for position, query in enumerate(queries):
        groups.setdefault(query.filters, []).append(position)
    requests: list[WorksRequest] = []
    for positions in groups.values():
        alone = [position for position in positions if asked_alone(queries[position].query)]
        chunk: list[int] = []
        for position in positions:
            if position in alone:
                continue
            trial = [*chunk, position]
            if chunk and not _fits(queries, trial):
                requests.append(_request(queries, chunk))
                chunk = [position]
            else:
                chunk = trial
        if chunk:
            requests.append(_request(queries, chunk))
        requests.extend(_request(queries, (position,)) for position in alone)
    return tuple(requests)


def _request(queries: Sequence[ProviderQuery], positions: Sequence[int]) -> WorksRequest:
    asked = [queries[position] for position in positions]
    return WorksRequest(ProviderQuery(query=joined_search(asked), filters=asked[0].filters), tuple(positions))


def _fits(queries: Sequence[ProviderQuery], positions: Sequence[int]) -> bool:
    """Whether one request may carry the queries at `positions`: its search and its URL within the limits."""
    if len(_request(queries, positions).query.query) > MAX_SEARCH_CHARS:
        return False
    return len(works_url(_last_page_parameters(queries, positions))) <= MAX_URL_CHARS


def _last_page_parameters(queries: Sequence[ProviderQuery], positions: Sequence[int]) -> dict[str, str]:
    query = _request(queries, positions).query
    pages = page_count(query)
    return works_parameters(query, page=pages if pages > 1 else None)


def answered_queries(
    candidate: CandidateResult, queries: Sequence[ProviderQuery], positions: Sequence[int]
) -> tuple[int, ...]:
    """Which of the queries at `positions` a joined search's work answered (see the module docstring).

    The ones whose every word is in the work's title or abstract; when none is, all of them.
    """
    return _matching(candidate, queries, positions) or tuple(positions)


def _matching(
    candidate: CandidateResult, queries: Sequence[ProviderQuery], positions: Sequence[int]
) -> tuple[int, ...]:
    text = f"{candidate.title} {candidate.snippet or ''}"
    return tuple(
        position for position in positions if text_matches_terms(text, query_terms(queries[position].query))
    )


class OpenAlexProvider:
    """Searches OpenAlex's works: a multi-query `SearchProvider` (`MultiQuerySearchProvider`).

    Sends one request per page of each joined search and never retries one: the wrapper decides what
    happens after a failure. Owns `client`; close it with :meth:`aclose`.
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
        (response,) = await self.search_each((query,))
        return response

    async def search_each(self, queries: Sequence[ProviderQuery]) -> tuple[ProviderResponse, ...]:
        """Every query in the fewest joined requests, each work attributed to the queries it answered."""
        started = time.perf_counter()
        requests = works_requests(queries)
        found: list[list[CandidateResult]] = [[] for _ in queries]
        errors: list[str | None] = [None for _ in queries]
        failures: list[ProviderError] = []
        attributed = {"one": 0, "several": 0, "none": 0}
        for request in requests:
            parts = await self._ask(queries, request.answers)
            failed = [part.failure for part in parts if part.failure is not None]
            if len(failed) == len(parts):
                failures.append(failed[0])
            for part in parts:
                if part.failure is not None:
                    for position in part.positions:
                        errors[position] = _reason(part.failure)
                    continue
                for position in part.positions:
                    errors[position] = part.shortfall
                for candidate in part.candidates:
                    matched = _matching(candidate, queries, part.positions)
                    if len(part.positions) > 1:
                        attributed["one" if len(matched) == 1 else "several" if matched else "none"] += 1
                    for position in matched or part.positions:
                        found[position].append(candidate)
        if failures and len(failures) == len(requests):
            raise failures[0]
        if len(queries) > 1:
            logger.info(
                "%s: %d queries in %d requests; works matching one query %d, several %d, none %d",
                self.name,
                len(queries),
                len(requests),
                attributed["one"],
                attributed["several"],
                attributed["none"],
            )
        alone = [len(queries) > 1 and asked_alone(query.query) for query in queries]
        notes = (asked_alone_note(sum(alone)),) if any(alone) else ()
        elapsed_ms = (time.perf_counter() - started) * 1000
        return tuple(
            ProviderResponse(
                provider=self.name,
                results=tuple(found[position])[: query.filters.max_results],
                elapsed_ms=elapsed_ms,
                partial=errors[position] is not None,
                error=errors[position],
                notes=notes if alone[position] else (),
            )
            for position, query in enumerate(queries)
        )

    async def _ask(self, queries: Sequence[ProviderQuery], positions: tuple[int, ...]) -> list[_Asked]:
        """One request for the queries at `positions`; split in halves when OpenAlex refuses a joined
        one's first page with `400` (the PM's ruling on v1-e08-t20), and the split logged once."""
        asked = await self._attempt(queries, positions)
        if not asked.refused or len(positions) == 1:
            return [asked]
        parts, sent = await self._halves(queries, positions)
        answered = sum(len(part.positions) for part in parts if part.failure is None)
        refused = sum(len(part.positions) for part in parts if part.refused)
        logger.info(
            "%s: a joined request of %d queries was refused with HTTP 400 and split in halves: "
            "%d more requests, %d queries answered, %d refused",
            self.name,
            len(positions),
            sent,
            answered,
            refused,
        )
        return parts

    async def _halves(
        self, queries: Sequence[ProviderQuery], positions: tuple[int, ...]
    ) -> tuple[list[_Asked], int]:
        """The two halves of a refused request, each asked, and how many requests that took.

        A half refused beside an answered half is split again, until a single query is refused, which
        fails as it would asked alone. When both halves are refused the refusal is not about size: the
        split stops, and every query of the request fails as a `400`. So one refused query of n costs
        at most 1 + 2 * ceil(log2 n) requests a page, and a refusal that is not about size costs 3.
        """
        middle = (len(positions) + 1) // 2
        first = await self._attempt(queries, positions[:middle])
        second = await self._attempt(queries, positions[middle:])
        if first.refused and second.failure is None and len(first.positions) > 1:
            parts, sent = await self._halves(queries, first.positions)
            return [*parts, second], 2 + sent
        if second.refused and first.failure is None and len(second.positions) > 1:
            parts, sent = await self._halves(queries, second.positions)
            return [first, *parts], 2 + sent
        return [first, second], 2

    async def _attempt(self, queries: Sequence[ProviderQuery], positions: tuple[int, ...]) -> _Asked:
        """Every page of one request for the queries at `positions`; a rate limit is raised."""
        try:
            candidates, shortfall = await self._pages(_request(queries, positions).query)
        except _Refused as refusal:
            return _Asked(positions, failure=refusal.failure, refused=True)
        except ProviderRateLimited:
            raise
        except ProviderError as error:
            return _Asked(positions, failure=error)
        return _Asked(positions, tuple(candidates), shortfall)

    async def _pages(self, query: ProviderQuery) -> tuple[list[CandidateResult], str | None]:
        """Every page `query` asks for, until `max_results` works or a short page.

        A failure on the first page is raised (a `400` as :class:`_Refused`); on a later one, the pages
        already read are kept and the failure is returned as the reason the answer is partial.
        """
        pages = page_count(query)
        candidates: list[CandidateResult] = []
        for page in range(1, pages + 1):
            try:
                works, sent = await self._page(query, page if pages > 1 else None)
            except (ProviderError, _Refused) as error:
                if page == 1:
                    raise
                failure = error.failure if isinstance(error, _Refused) else error
                return candidates, f"page {page} of {pages} failed: {_reason(failure)}"
            candidates.extend(works)
            if len(candidates) >= query.filters.max_results or sent < MAX_PER_PAGE:
                break
        return candidates[: query.filters.max_results], None

    async def _page(self, query: ProviderQuery, page: int | None) -> tuple[list[CandidateResult], int]:
        """One page's candidates, and how many works OpenAlex sent on it."""
        headers = (
            {} if self._api_key is None else {"Authorization": f"Bearer {self._api_key.get_secret_value()}"}
        )
        try:
            response = await self._client.get(
                OPENALEX_WORKS_URL, params=works_parameters(query, page=page), headers=headers
            )
        except httpx.TimeoutException as error:
            raise ProviderUnavailable(self.name, "timed out") from error
        except httpx.HTTPError as error:
            raise ProviderUnavailable(self.name, f"transport failure: {type(error).__name__}") from error
        failure = provider_error_for_status(
            self.name, response.status_code, response.headers, now=self._clock.now()
        )
        if failure is not None and response.status_code == 400:
            raise _Refused(failure)
        if failure is not None:
            raise failure
        return self._read(response)

    def _read(self, response: httpx.Response) -> tuple[list[CandidateResult], int]:
        try:
            document = response.json()
        except ValueError as error:
            raise ProviderUnavailable(self.name, f"unreadable response: {type(error).__name__}") from error
        works = _mapping(document).get("results")
        if not isinstance(works, list) or not all(
            isinstance(work, dict) for work in cast(list[object], works)
        ):
            raise ProviderUnavailable(self.name, "unreadable response: no list of works")
        listed = cast(list[dict[str, Any]], works)
        candidates = (candidate_from_work(work) for work in listed)
        return [candidate for candidate in candidates if candidate is not None], len(listed)


class _Refused(Exception):
    """A request OpenAlex refused with `400`, which a joined request answers by splitting in halves.

    Private to this module: what fails a query is :attr:`failure`, today's `ProviderUnavailable`.
    """

    def __init__(self, failure: ProviderError) -> None:
        super().__init__(str(failure))
        self.failure = failure


@dataclass(frozen=True, slots=True)
class _Asked:
    """What one request, or one half of a split, gave the queries at `positions`."""

    positions: tuple[int, ...]
    candidates: tuple[CandidateResult, ...] = ()
    shortfall: str | None = None
    failure: ProviderError | None = None
    refused: bool = False
    """Whether `failure` is a first page refused with `400`."""


def _reason(error: ProviderError) -> str:
    """The error's message without the provider name it starts with."""
    return str(error).removeprefix(f"{error.provider}: ")


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
