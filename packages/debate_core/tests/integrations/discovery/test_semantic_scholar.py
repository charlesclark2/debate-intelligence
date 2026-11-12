"""SemanticScholarProvider: the request and its key, the pace, how papers map, and the contract kit.

Every Semantic Scholar answer here is hand-written from the Academic Graph API's documented
`/paper/search` response and lives in `packages/debate_core/tests/fixtures/discovery/semantic_scholar/`;
every expected mapping is written by hand from those bodies (working agreement 6). Nothing here
reaches the network.

The pace is tested on the event loop's virtual time (:func:`run_in_virtual_time` with
:class:`EventLoopClock`), so the pacer's sleeps, the wrapper's timeout and the search's deadline read
one clock, a search of eleven queries at one a second runs in milliseconds, and every start time is
exact.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Coroutine, Iterator
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Final

import httpx
import pytest
import respx
from pydantic import SecretStr

from debate_core.application.errors import ProviderError, ProviderRateLimited, ProviderUnavailable
from debate_core.application.federated_search import FanOutStage, FederatedSearchService, search_status
from debate_core.application.federated_search_types import SearchRequest, SearchState
from debate_core.application.ports.providers import Clock, SearchProvider
from debate_core.application.settings import HttpSettings, ProviderSettings, SearchProviderName
from debate_core.domain import SearchStatus
from debate_core.domain.discovery import (
    BreakerState,
    CandidateResult,
    DatePrecision,
    ProviderHealth,
    ProviderOutcome,
    ProviderQuery,
)
from debate_core.domain.enums import SourceType
from debate_core.domain.search import SearchFilters
from debate_core.integrations.discovery.pace import Pace
from debate_core.integrations.discovery.redaction import PROTECTED_LOGGERS, logger
from debate_core.integrations.discovery.registry import (
    ProviderNotConfigured,
    ProviderRegistry,
    configured_secrets,
    policy_from_settings,
)
from debate_core.integrations.discovery.resilience import ResilientProvider
from debate_core.integrations.discovery.semantic_scholar import (
    API_KEY_HEADER,
    KEYED_PACE,
    KEYLESS_PACE,
    MAX_PER_REQUEST,
    PAPER_SEARCH_URL,
    REQUESTED_FIELDS,
    SemanticScholarProvider,
    candidate_from_paper,
    paper_search_parameters,
    searchable_query,
    semantic_scholar_factory,
    source_type_for,
)
from debate_core.testing.builders import build_candidate_result
from debate_core.testing.contracts.search_provider import (
    Recording,
    ReplayedProvider,
    ReplayFactory,
    SearchProviderContract,
    SentRequest,
    TransportFailure,
    load_recording,
)
from debate_core.testing.fakes.clock_and_ids import FixedClock, SequentialIdGenerator
from debate_core.testing.fakes.persistence import InMemorySearchRepository
from debate_core.testing.fakes.providers import FakeSearchProvider
from debate_core.testing.virtual_time import EventLoopClock, run_in_virtual_time

pytestmark = pytest.mark.anyio

FIXTURES: Final = Path(__file__).resolve().parents[2] / "fixtures" / "discovery" / "semantic_scholar"
API_KEY: Final = "s2key-8RvQ3x"
"""A made-up key: short, so that no message shortens it out of sight (pydantic truncates long ones)."""
VERSION: Final = "0.0.0-test"
NOW: Final = datetime(2024, 1, 1, tzinfo=UTC)
FIELDS: Final = (
    "title,authors,year,publicationDate,venue,externalIds,citationCount,influentialCitationCount,"
    "isOpenAccess,openAccessPdf,publicationTypes,abstract"
)
NOT_ASKED_WITH_A_KEY: Final = "semantic_scholar: not asked: the pace is 1 query a second"
NOT_ASKED_WITHOUT_A_KEY: Final = (
    "semantic_scholar: not asked: the pace is 1 query a second; "
    "an API key would identify this caller but raises nothing today"
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def bare_protected_loggers() -> Iterator[None]:
    """The protected loggers start with no filters, and get theirs back afterwards.

    Their filters are shared by the whole process: a test that ran earlier in this worker (the
    OpenCaselist client's, the fetcher's, another adapter's) may have left one that hides a leak
    (working agreement 10).
    """
    saved = {name: list(logging.getLogger(name).filters) for name in PROTECTED_LOGGERS}
    for name in PROTECTED_LOGGERS:
        logging.getLogger(name).filters.clear()
    yield
    for name, filters in saved.items():
        logging.getLogger(name).filters[:] = filters


# --------------------------------------------------------------------------------------------
# Building the adapter
# --------------------------------------------------------------------------------------------


def instant_sleep(clock: FixedClock) -> Callable[[float], Awaitable[None]]:
    """A sleep that moves `clock` on at once, for tests that are not about the pace."""

    async def sleep(seconds: float) -> None:
        if seconds > 0:
            clock.advance(timedelta(seconds=seconds))
        await asyncio.sleep(0)

    return sleep


def provider_settings(*, api_key: str | None = API_KEY, **overrides: Any) -> ProviderSettings:
    """Semantic Scholar enabled, with an API key unless `api_key` is `None`."""
    return ProviderSettings(
        enabled=(SearchProviderName.SEMANTIC_SCHOLAR,),
        semantic_scholar_api_key=SecretStr(api_key) if api_key is not None else None,
        **overrides,
    )


def keyless_adapter(
    transport: httpx.AsyncBaseTransport,
    settings: ProviderSettings,
    *,
    clock: Clock,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> SemanticScholarProvider:
    """The adapter's own keyless mode, built directly over a client like the factory's.

    Since v1-e07-t20 the factory builds nothing without a key (the registry reports Semantic Scholar not
    configured), so a test of what the adapter itself does without one builds it here.
    """
    client = httpx.AsyncClient(
        headers={"User-Agent": HttpSettings().user_agent(VERSION)},
        follow_redirects=False,
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


def adapter_factory(
    *,
    clock: Clock,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    transport: httpx.AsyncBaseTransport,
) -> Callable[[ProviderSettings], SemanticScholarProvider]:
    """The registry's factory when the settings carry a key, and :func:`keyless_adapter` when they do not."""
    factory = semantic_scholar_factory(
        HttpSettings(), version=VERSION, clock=clock, sleep=sleep, transport=transport
    )

    def build(settings: ProviderSettings) -> SemanticScholarProvider:
        key = settings.semantic_scholar_api_key
        if key is None or not key.get_secret_value().strip():
            return keyless_adapter(transport, settings, clock=clock, sleep=sleep)
        return factory(settings)

    return build


def build_over(
    transport: httpx.AsyncBaseTransport, *, api_key: str | None = API_KEY, **overrides: Any
) -> SemanticScholarProvider:
    """The adapter as the registry builds it, over `transport`, on a clock its sleep moves; without a key,
    the adapter's keyless mode, which the factory no longer builds (:func:`adapter_factory`)."""
    clock = FixedClock(NOW)
    factory = adapter_factory(clock=clock, sleep=instant_sleep(clock), transport=transport)
    return factory(provider_settings(api_key=api_key, **overrides))


def replay_with_respx(
    build: Callable[[httpx.AsyncBaseTransport], SearchProvider], seen: list[httpx.Request] | None = None
) -> ReplayFactory:
    """Serve a recording's exchanges through respx, and nothing else.

    A copy of the FakeProvider binding's (`test_fake_provider.py`), as OpenAlex's and Crossref's are:
    the adapter is built from a transport, so that the factory's own client is the one under test,
    and every request is kept in `seen` when given. Transport failures are raised here rather than as
    respx side effects, because respx re-raises a side effect `from` an error that quotes the
    matched route.
    """

    def replay(recording: Recording) -> ReplayedProvider:
        router = respx.MockRouter(assert_all_called=False, assert_all_mocked=True)
        failures: dict[SentRequest, TransportFailure] = {}
        for exchange in recording.exchanges:
            if exchange.failure is not None:
                failures[SentRequest(exchange.method.upper(), exchange.url)] = exchange.failure
            elif exchange.response is not None:
                answer = exchange.response
                router.route(method=exchange.method, url=exchange.url).return_value = httpx.Response(
                    answer.status, headers=answer.headers, content=answer.body
                )
        sent: list[SentRequest] = []

        async def transport(request: httpx.Request) -> httpx.Response:
            this = SentRequest(request.method, str(request.url))
            sent.append(this)
            if seen is not None:
                seen.append(request)
            failure = failures.get(this)
            if failure is TransportFailure.TIMEOUT:
                raise httpx.ReadTimeout("timed out", request=request)
            if failure is TransportFailure.CONNECTION_ERROR:
                raise httpx.ConnectError("connection refused", request=request)
            return await router.async_handler(request)

        return ReplayedProvider(build(httpx.MockTransport(transport)), lambda: tuple(sent))

    return replay


def recording(name: str) -> Recording:
    return load_recording(FIXTURES / f"{name}.json")


def body(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def a_paper(**fields: Any) -> dict[str, Any]:
    """A minimal mappable paper, with `fields` laid over it."""
    return {"paperId": "ab" * 20, "title": "A title", **fields}


def candidate(**fields: Any) -> CandidateResult:
    mapped = candidate_from_paper(a_paper(**fields))
    assert mapped is not None
    return mapped


def papers(*data: dict[str, Any]) -> dict[str, Any]:
    """A `/paper/search` answer around `data`."""
    return {"total": len(data), "offset": 0, "data": list(data)}


CARBON_CAPTURE: Final = ProviderQuery(
    query="carbon capture subsidies",
    filters=SearchFilters(
        since=datetime(2020, 1, 1, tzinfo=UTC), until=datetime(2024, 12, 31, tzinfo=UTC), max_results=6
    ),
)
CARBON_CAPTURE_URL: Final = (
    "https://api.semanticscholar.org/graph/v1/paper/search?query=carbon+capture+subsidies"
    "&publicationDateOrYear=2020-01-01%3A2024-12-31&limit=6"
    "&fields=title%2Cauthors%2Cyear%2CpublicationDate%2Cvenue%2CexternalIds%2CcitationCount"
    "%2CinfluentialCitationCount%2CisOpenAccess%2CopenAccessPdf%2CpublicationTypes%2Cabstract"
)


# --------------------------------------------------------------------------------------------
# Mapping a paper
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("page", ["paper_search", "paper_search_without_pdfs"])
def test_the_recorded_papers_map_to_the_hand_written_candidates(page: str) -> None:
    mapped = [candidate_from_paper(paper) for paper in body(f"{page}.body.json")["data"]]
    expected = json.loads((FIXTURES / f"{page}.expected.json").read_text(encoding="utf-8"))
    assert [result.model_dump(mode="json") for result in mapped if result is not None] == [
        CandidateResult.model_validate(item).model_dump(mode="json") for item in expected
    ]


def test_every_external_id_kind_is_read_and_the_others_are_ignored() -> None:
    mapped = candidate(
        externalIds={
            "DOI": "10.5555/Every.Kind",
            "ArXiv": "2401.00001",
            "PubMed": "38123456",
            "PubMedCentral": "10812345",
            "MAG": "4390000001",
            "DBLP": "journals/corr/abs-2401-00001",
            "ACL": "2024.acl-long.1",
            "CorpusId": 266000001,
        }
    )
    assert mapped.identifiers.model_dump() == {
        "doi": "10.5555/every.kind",
        "arxiv_id": "2401.00001",
        "pmid": "38123456",
        "openalex_id": None,
        "semantic_scholar_id": "ab" * 20,
    }
    assert mapped.provider_record_id == "ab" * 20


@pytest.mark.parametrize(
    ("doi", "expected"),
    [
        ("10.5555/ABC.1", "10.5555/abc.1"),
        ("https://doi.org/10.5555/abc.1", "10.5555/abc.1"),
        (" 10.5555/abc.1 ", "10.5555/abc.1"),
        ("not a doi", None),
        ("", None),
        (1055551, None),
        (None, None),
    ],
    ids=["upper case", "a resolver URL", "spaces", "not a DOI", "empty", "a number", "null"],
)
def test_the_doi_is_normalized_once_or_dropped(doi: object, expected: str | None) -> None:
    mapped = candidate(externalIds={"DOI": doi})
    assert mapped.identifiers.doi == expected
    assert mapped.url == (
        f"https://doi.org/{expected}" if expected else f"https://www.semanticscholar.org/paper/{'ab' * 20}"
    )


@pytest.mark.parametrize(
    ("pubmed", "expected"),
    [
        ("31234567", "31234567"),
        (" 31234567 ", "31234567"),
        ("PMC31234567", None),
        ("", None),
        (31234567, None),
    ],
    ids=["digits", "spaces", "not digits", "empty", "a number"],
)
def test_a_pubmed_id_is_kept_only_as_digits(pubmed: object, expected: str | None) -> None:
    assert candidate(externalIds={"PubMed": pubmed}).identifiers.pmid == expected


@pytest.mark.parametrize(
    ("arxiv", "expected"),
    [("2203.01234", "2203.01234"), (" hep-th/9901001 ", "hep-th/9901001"), ("  ", None), (2203.01234, None)],
    ids=["new style", "old style with spaces", "blank", "a number"],
)
def test_an_arxiv_id_is_kept_as_given(arxiv: object, expected: str | None) -> None:
    assert candidate(externalIds={"ArXiv": arxiv}).identifiers.arxiv_id == expected


@pytest.mark.parametrize(
    "external_ids", [None, [], "DOI:10.5555/x", {}], ids=["null", "a list", "text", "empty"]
)
def test_external_ids_in_another_shape_leave_only_the_paper_id(external_ids: object) -> None:
    mapped = candidate(externalIds=external_ids)
    assert (mapped.identifiers.doi, mapped.identifiers.arxiv_id, mapped.identifiers.pmid) == (
        None,
        None,
        None,
    )
    assert mapped.identifiers.semantic_scholar_id == "ab" * 20


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        (
            {"publicationDate": "2022-05-17", "year": 2022},
            (datetime(2022, 5, 17, tzinfo=UTC), DatePrecision.DAY),
        ),
        ({"publicationDate": "2022-05-17"}, (datetime(2022, 5, 17, tzinfo=UTC), DatePrecision.DAY)),
        ({"publicationDate": None, "year": 2021}, (datetime(2021, 1, 1, tzinfo=UTC), DatePrecision.YEAR)),
        ({"year": 2021}, (datetime(2021, 1, 1, tzinfo=UTC), DatePrecision.YEAR)),
        (
            {"publicationDate": "2022-02-30", "year": 2022},
            (datetime(2022, 1, 1, tzinfo=UTC), DatePrecision.YEAR),
        ),
        (
            {"publicationDate": "2022-05", "year": 2022},
            (datetime(2022, 1, 1, tzinfo=UTC), DatePrecision.YEAR),
        ),
        (
            {"publicationDate": "May 2022", "year": 2022},
            (datetime(2022, 1, 1, tzinfo=UTC), DatePrecision.YEAR),
        ),
        ({"publicationDate": None, "year": None}, (None, None)),
        ({"year": "2021"}, (None, None)),
        ({"year": True}, (None, None)),
        ({"year": 0}, (None, None)),
        ({}, (None, None)),
    ],
    ids=[
        "a date and its year",
        "a date alone",
        "a null date and a year",
        "a year alone",
        "an impossible day",
        "a month",
        "words",
        "neither",
        "a year as text",
        "a year as true",
        "year zero",
        "nothing",
    ],
)
def test_the_date_is_the_publication_date_to_the_day_or_else_the_year_at_year_precision(
    fields: dict[str, Any], expected: tuple[datetime | None, DatePrecision | None]
) -> None:
    mapped = candidate(**fields)
    assert (mapped.published_at, mapped.date_precision) == expected


def test_a_year_only_date_is_never_given_a_day() -> None:
    mapped = candidate(publicationDate=None, year=2021)
    assert mapped.date_precision is DatePrecision.YEAR
    assert mapped.date_precision is not DatePrecision.DAY
    assert mapped.published_at == datetime(2021, 1, 1, tzinfo=UTC)


@pytest.mark.parametrize(
    ("publication_types", "expected"),
    [
        (["JournalArticle"], SourceType.SCHOLARLY),
        (["Review"], SourceType.SCHOLARLY),
        (["CaseReport"], SourceType.SCHOLARLY),
        (["ClinicalTrial"], SourceType.SCHOLARLY),
        (["Conference"], SourceType.SCHOLARLY),
        (["Editorial"], SourceType.SCHOLARLY),
        (["LettersAndComments"], SourceType.SCHOLARLY),
        (["MetaAnalysis"], SourceType.SCHOLARLY),
        (["Study"], SourceType.SCHOLARLY),
        (["Book"], SourceType.SCHOLARLY),
        (["BookSection"], SourceType.SCHOLARLY),
        (["News"], SourceType.NEWS),
        (["Dataset"], SourceType.OTHER),
        (["Journal Article", "Review"], SourceType.SCHOLARLY),
        (["Dataset", "JournalArticle"], SourceType.SCHOLARLY),
        (["News", "Dataset"], SourceType.NEWS),
        (["Patent"], SourceType.OTHER),
        (["Dataset", "Patent"], SourceType.OTHER),
        (None, SourceType.SCHOLARLY),
        ([], SourceType.SCHOLARLY),
        ("JournalArticle", SourceType.SCHOLARLY),
        ([None, 3], SourceType.SCHOLARLY),
    ],
    ids=[
        "JournalArticle",
        "Review",
        "CaseReport",
        "ClinicalTrial",
        "Conference",
        "Editorial",
        "LettersAndComments",
        "MetaAnalysis",
        "Study",
        "Book",
        "BookSection",
        "News",
        "Dataset",
        "the documentation's spaced spelling",
        "a dataset that is also an article",
        "news that is also a dataset",
        "a type not documented",
        "a dataset and an undocumented type",
        "none given",
        "an empty list",
        "a bare string",
        "no readable type",
    ],
)
def test_the_publication_types_map_to_a_source_type(publication_types: object, expected: SourceType) -> None:
    """Every documented type, by the rule: scholarly if any type is, else news if any is, else other;
    and a paper with no readable type is scholarly, because Semantic Scholar indexes papers."""
    assert source_type_for(publication_types) is expected
    assert candidate(publicationTypes=publication_types).source_type is expected


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        (
            {
                "isOpenAccess": True,
                "openAccessPdf": {"url": "https://arxiv.org/pdf/2203.01234", "status": "GREEN"},
            },
            ("https://arxiv.org/pdf/2203.01234", True),
        ),
        ({"isOpenAccess": True, "openAccessPdf": {"url": "", "status": "BRONZE"}}, (None, True)),
        ({"isOpenAccess": True, "openAccessPdf": {"url": "ftp://example.org/a.pdf"}}, (None, True)),
        ({"isOpenAccess": True, "openAccessPdf": {"url": "https://example.org/a b.pdf"}}, (None, True)),
        ({"isOpenAccess": True, "openAccessPdf": {"url": "/pdf/a.pdf"}}, (None, True)),
        ({"isOpenAccess": True, "openAccessPdf": "https://example.org/a.pdf"}, (None, True)),
        ({"isOpenAccess": False, "openAccessPdf": None}, (None, False)),
        ({"openAccessPdf": {"url": "https://example.org/a.pdf"}}, ("https://example.org/a.pdf", None)),
        ({"isOpenAccess": "yes"}, (None, None)),
        ({}, (None, None)),
    ],
    ids=[
        "a PDF",
        "an empty url",
        "not http",
        "a space",
        "relative",
        "not an object",
        "closed",
        "no isOpenAccess",
        "isOpenAccess as text",
        "neither",
    ],
)
def test_the_open_copy_is_the_pdf_link_and_open_access_is_what_semantic_scholar_says(
    fields: dict[str, Any], expected: tuple[str | None, bool | None]
) -> None:
    mapped = candidate(**fields)
    assert (mapped.open_access_url, mapped.open_access) == expected


@pytest.mark.parametrize(
    ("count", "expected"),
    [(57, 57), (0, 0), (-1, None), (True, None), ("57", None), (5.0, None), (None, None)],
    ids=["a count", "zero", "negative", "true", "text", "a float", "null"],
)
def test_the_citation_count_is_citation_count(count: object, expected: int | None) -> None:
    assert candidate(citationCount=count, influentialCitationCount=3).citation_count == expected


@pytest.mark.parametrize(
    "paper",
    [
        {"paperId": "ab" * 20, "title": None},
        {"paperId": "ab" * 20, "title": "   "},
        {"paperId": "ab" * 20},
        {"paperId": None, "title": "A title"},
        {"paperId": "  ", "title": "A title"},
        {"title": "A title"},
        {"paperId": 42, "title": "A title"},
    ],
    ids=["null title", "blank title", "no title", "null id", "blank id", "no id", "a number for an id"],
)
def test_a_paper_with_no_title_or_no_paper_id_is_not_a_candidate(paper: dict[str, Any]) -> None:
    assert candidate_from_paper(paper) is None


def test_the_url_is_the_doi_resolver_or_else_the_semantic_scholar_paper_page() -> None:
    assert candidate(externalIds={"DOI": "10.5555/x.1"}).url == "https://doi.org/10.5555/x.1"
    assert (
        candidate(externalIds={"ArXiv": "2203.01234"}).url
        == f"https://www.semanticscholar.org/paper/{'ab' * 20}"
    )
    odd = candidate_from_paper(a_paper(paperId="a b/c?d"))
    assert odd is not None
    assert odd.url == "https://www.semanticscholar.org/paper/a%20b%2Fc%3Fd"
    assert odd.identifiers.semantic_scholar_id == "a b/c?d"


def test_names_titles_venues_and_abstracts_lose_their_extra_whitespace() -> None:
    mapped = candidate(
        title="  Capture \n subsidies  ",
        authors=[
            {"authorId": "1", "name": "  Ilse   Marrowby "},
            {"authorId": "2", "name": ""},
            {"authorId": "3"},
            {"name": None},
            "Not An Author Object",
            {"authorId": None, "name": "Tomas Underhill"},
        ],
        venue="  Journal of\tInvented Energy  ",
        abstract="Line one.\n\nLine   two.",
    )
    assert mapped.title == "Capture subsidies"
    assert mapped.authors == ("Ilse Marrowby", "Tomas Underhill")
    assert mapped.publication == "Journal of Invented Energy"
    assert mapped.snippet == "Line one. Line two."


@pytest.mark.parametrize("venue", ["", "   ", None, 7], ids=["empty", "blank", "null", "a number"])
def test_an_empty_venue_is_none(venue: object) -> None:
    assert candidate(venue=venue).publication is None


@pytest.mark.parametrize(
    "authors", [None, "Ilse Marrowby", {"name": "Ilse Marrowby"}], ids=["null", "text", "an object"]
)
def test_authors_in_another_shape_are_none(authors: object) -> None:
    assert candidate(authors=authors).authors == ()


# --------------------------------------------------------------------------------------------
# The request and the key
# --------------------------------------------------------------------------------------------


def transport_for(router: respx.MockRouter, seen: list[httpx.Request]) -> httpx.MockTransport:
    async def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return await router.async_handler(request)

    return httpx.MockTransport(handle)


def routed(
    *, headers: dict[str, str] | None = None
) -> tuple[respx.MockRouter, respx.Route, list[httpx.Request]]:
    """A router whose one route matches the carbon capture search, and the `headers` asked for."""
    router = respx.MockRouter(assert_all_called=False, assert_all_mocked=True)
    route = router.get(
        PAPER_SEARCH_URL,
        params={
            "query": "carbon capture subsidies",
            "publicationDateOrYear": "2020-01-01:2024-12-31",
            "limit": "6",
            "fields": FIELDS,
        },
        headers=headers or {},
    )
    route.return_value = httpx.Response(200, json=papers())
    return router, route, []


async def test_a_request_carries_the_query_the_date_window_the_limit_and_the_fields() -> None:
    router, route, seen = routed()
    answer = await build_over(transport_for(router, seen)).search(CARBON_CAPTURE)

    assert route.call_count == 1
    assert (answer.provider, answer.results, answer.partial, answer.error) == (
        "semantic_scholar",
        (),
        False,
        None,
    )
    assert [(request.method, str(request.url)) for request in seen] == [("GET", CARBON_CAPTURE_URL)]


def test_the_requested_fields_are_the_specs_list() -> None:
    assert ",".join(REQUESTED_FIELDS) == FIELDS


async def test_a_request_with_a_key_sends_it_as_the_x_api_key_header() -> None:
    router, route, seen = routed(headers={"x-api-key": API_KEY})
    provider = build_over(transport_for(router, seen))
    await provider.search(CARBON_CAPTURE)
    await provider.search(CARBON_CAPTURE)

    assert route.call_count == 2
    assert API_KEY_HEADER == "x-api-key"
    assert [request.headers.get_list("x-api-key") for request in seen] == [[API_KEY], [API_KEY]]
    assert all(API_KEY not in str(request.url) for request in seen)


@pytest.mark.parametrize("api_key", [None, "", "   "], ids=["none", "empty", "spaces"])
async def test_a_request_without_a_key_sends_no_key_header(api_key: str | None) -> None:
    router, route, seen = routed()
    provider = build_over(transport_for(router, seen), api_key=api_key)
    await provider.search(CARBON_CAPTURE)

    assert route.call_count == 1
    assert "x-api-key" not in seen[0].headers
    assert repr(provider) == "SemanticScholarProvider(api_key=none)"


async def test_a_request_identifies_the_platform_and_keeps_no_cookies() -> None:
    router, route, seen = routed()
    route.return_value = httpx.Response(200, json=papers(), headers={"set-cookie": "s2=abc; Path=/"})
    provider = build_over(transport_for(router, seen))
    await provider.search(CARBON_CAPTURE)
    await provider.search(CARBON_CAPTURE)

    assert {request.headers["user-agent"] for request in seen} == {HttpSettings().user_agent(VERSION)}
    assert all("cookie" not in request.headers for request in seen)


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        (SearchFilters(max_results=20), {"query": "methane leakage", "limit": "20", "fields": FIELDS}),
        (
            SearchFilters(since=datetime(2021, 3, 4, tzinfo=UTC), max_results=5),
            {
                "query": "methane leakage",
                "publicationDateOrYear": "2021-03-04:",
                "limit": "5",
                "fields": FIELDS,
            },
        ),
        (
            SearchFilters(until=datetime(2023, 6, 30, tzinfo=UTC), max_results=5),
            {
                "query": "methane leakage",
                "publicationDateOrYear": ":2023-06-30",
                "limit": "5",
                "fields": FIELDS,
            },
        ),
        (
            SearchFilters(since=datetime(2021, 3, 4, tzinfo=UTC), until=datetime(2023, 6, 30, tzinfo=UTC)),
            {
                "query": "methane leakage",
                "publicationDateOrYear": "2021-03-04:2023-06-30",
                "limit": "20",
                "fields": FIELDS,
            },
        ),
        (SearchFilters(max_results=100), {"query": "methane leakage", "limit": "100", "fields": FIELDS}),
        (SearchFilters(max_results=101), {"query": "methane leakage", "limit": "100", "fields": FIELDS}),
        (SearchFilters(max_results=200), {"query": "methane leakage", "limit": "100", "fields": FIELDS}),
    ],
    ids=["no window", "since", "until", "both", "a hundred", "a hundred and one", "two hundred"],
)
def test_the_request_parameters_carry_the_window_and_at_most_a_hundred(
    filters: SearchFilters, expected: dict[str, str]
) -> None:
    parameters = paper_search_parameters(ProviderQuery(query="methane leakage", filters=filters))
    assert list(parameters.items()) == list(expected.items())
    assert MAX_PER_REQUEST == 100


def test_the_request_date_window_is_the_utc_date() -> None:
    late_evening_in_new_york = datetime(2021, 3, 4, 23, 30, tzinfo=timezone(timedelta(hours=-5)))
    query = ProviderQuery(query="x", filters=SearchFilters(since=late_evening_in_new_york))
    assert paper_search_parameters(query)["publicationDateOrYear"] == "2021-03-05:"


@pytest.mark.parametrize(
    ("query", "sent"),
    [
        ("direct air-capture costs", "direct air capture costs"),
        ("us-china trade-war", "us china trade war"),
        ("co2 - removal", "co2 removal"),
        ("carbon capture subsidies", "carbon capture subsidies"),
        ("  carbon \t capture  ", "carbon capture"),
        ("-", "-"),
    ],
    ids=["one hyphen", "two hyphens", "a spaced hyphen", "none", "extra spaces", "nothing but a hyphen"],
)
def test_a_request_sends_hyphens_as_spaces_because_hyphenated_terms_match_nothing(
    query: str, sent: str
) -> None:
    assert searchable_query(query) == sent
    assert paper_search_parameters(ProviderQuery(query=query))["query"] == sent


async def test_the_answer_keeps_to_max_results_and_skips_untitled_papers() -> None:
    answer_body = papers(
        a_paper(paperId="01" * 20, title=None),
        *(a_paper(paperId=f"{number:040x}", title=f"Paper {number}") for number in range(1, 9)),
    )
    router = respx.MockRouter(assert_all_mocked=True)
    router.get(PAPER_SEARCH_URL).return_value = httpx.Response(200, json=answer_body)
    query = ProviderQuery(query="x", filters=SearchFilters(max_results=3))

    answer = await build_over(httpx.MockTransport(router.async_handler)).search(query)

    assert [result.title for result in answer.results] == ["Paper 1", "Paper 2", "Paper 3"]


@pytest.mark.parametrize(
    "document",
    [{"total": 0, "offset": 0}, {"total": 0, "offset": 0, "data": []}],
    ids=["no data at all", "an empty data list"],
)
async def test_a_search_with_no_results_is_an_empty_answer(document: dict[str, Any]) -> None:
    router = respx.MockRouter(assert_all_mocked=True)
    router.get(PAPER_SEARCH_URL).return_value = httpx.Response(200, json=document)
    answer = await build_over(httpx.MockTransport(router.async_handler)).search(CARBON_CAPTURE)
    assert (answer.results, answer.partial, answer.error) == ((), False, None)


# --------------------------------------------------------------------------------------------
# Without a key Semantic Scholar is not configured; with one it is built and asked (v1-e07-t20)
# --------------------------------------------------------------------------------------------

MISSING_KEY: Final = "semantic_scholar: no Semantic Scholar key (DEBATE_PROVIDERS__SEMANTIC_SCHOLAR_API_KEY)"
"""The registry's reason when no key is set: the setting to set, never a value (the PM's ruling 1 of
2026-11-12 on v1-e07-t20)."""
CURE: Final = "request one through the form on Semantic Scholar's API page, semanticscholar.org/product/api"
"""What a search says after the reason, as `provider_credentials` words it."""


def counting_transport() -> tuple[httpx.MockTransport, list[httpx.Request]]:
    """A transport that answers every request with an empty paper list and keeps each one."""
    sent: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json=papers())

    return httpx.MockTransport(answer), sent


def the_factory(transport: httpx.AsyncBaseTransport) -> Callable[[ProviderSettings], SearchProvider]:
    clock = FixedClock(NOW)
    return semantic_scholar_factory(
        HttpSettings(), version=VERSION, clock=clock, sleep=instant_sleep(clock), transport=transport
    )


@pytest.mark.parametrize("api_key", [None, "", "   "], ids=["none", "empty", "spaces"])
def test_without_a_key_the_factory_builds_nothing_and_names_the_setting_to_set(api_key: str | None) -> None:
    transport, sent = counting_transport()

    with pytest.raises(ProviderNotConfigured) as missing:
        the_factory(transport)(provider_settings(api_key=api_key))

    assert (missing.value.provider, missing.value.reason) == ("semantic_scholar", MISSING_KEY)
    assert sent == []


def test_without_a_key_the_registry_reports_semantic_scholar_not_configured_and_builds_nothing() -> None:
    transport, sent = counting_transport()

    registry = ProviderRegistry.from_settings(
        provider_settings(api_key=None),
        {SearchProviderName.SEMANTIC_SCHOLAR: the_factory(transport)},
        clock=FixedClock(NOW),
    )

    assert registry.providers == ()
    assert dict(registry.not_configured) == {"semantic_scholar": MISSING_KEY}
    assert registry.health() == ()
    assert sent == []


def test_without_a_key_a_search_names_semantic_scholar_with_its_cure_and_does_not_count_it() -> None:
    """The ruling of v1-e07-t15 for a profile-enabled provider that is not configured: named in the record
    with its cure, never asked, and left out of the status, so OpenAlex's answer makes the search COMPLETE."""
    transport, sent = counting_transport()
    clock = FixedClock(NOW)
    found = build_candidate_result(provider="openalex")
    registry = ProviderRegistry.from_settings(
        ProviderSettings(enabled=(SearchProviderName.OPENALEX, SearchProviderName.SEMANTIC_SCHOLAR)),
        {
            SearchProviderName.OPENALEX: lambda settings: FakeSearchProvider(
                "openalex", default_results=(found,)
            ),
            SearchProviderName.SEMANTIC_SCHOLAR: the_factory(transport),
        },
        clock=clock,
    )
    service = FederatedSearchService(
        registry, InMemorySearchRepository(), clock=clock, ids=SequentialIdGenerator("SRCH")
    )

    outcome = run_in_virtual_time(service.search(SearchRequest(query="carbon capture subsidies")))

    assert [(status.provider, status.outcome, status.error) for status in outcome.provider_statuses] == [
        ("openalex", ProviderOutcome.OK, None),
        ("semantic_scholar", ProviderOutcome.NOT_CONFIGURED, f"{MISSING_KEY}; {CURE}"),
    ]
    assert outcome.uncounted == ("semantic_scholar",)
    assert outcome.status is SearchStatus.COMPLETE
    assert sent == []


def test_with_a_key_the_registry_builds_semantic_scholar_at_the_keyed_pace_and_asks_it() -> None:
    transport, sent = counting_transport()

    registry = ProviderRegistry.from_settings(
        provider_settings(),
        {SearchProviderName.SEMANTIC_SCHOLAR: the_factory(transport)},
        clock=FixedClock(NOW),
    )
    answer = run_in_virtual_time(registry.get("semantic_scholar").search(CARBON_CAPTURE))

    assert dict(registry.not_configured) == {}
    assert [provider.name for provider in registry.providers] == ["semantic_scholar"]
    assert (answer.results, answer.partial) == ((), False)
    [request] = sent
    assert request.headers["x-api-key"] == API_KEY


# --------------------------------------------------------------------------------------------
# The pace, with a key and without one
# --------------------------------------------------------------------------------------------


def test_the_pace_with_a_key_and_without_one_is_the_published_one_request_a_second() -> None:
    """semanticscholar.org/product/api (read by the PM 2026-11-09): a key's rate is 1 request a second;
    keyless callers share one pool and no stricter per-user figure is published (PM ruling 1)."""
    one_a_second_one_at_a_time = Pace(requests=1, interval_seconds=1.0, concurrency=1)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=papers()))

    assert one_a_second_one_at_a_time == KEYED_PACE
    assert one_a_second_one_at_a_time == KEYLESS_PACE
    assert build_over(transport).pace == one_a_second_one_at_a_time
    assert build_over(transport, api_key=None).pace == one_a_second_one_at_a_time


def queries(count: int) -> tuple[ProviderQuery, ...]:
    return tuple(ProviderQuery(query=f"capture query {number}") for number in range(1, count + 1))


def started_at(
    count: int, *, api_key: str | None, answer_seconds: float, timeout_seconds: float = 10.0
) -> Coroutine[Any, Any, list[tuple[str, float]]]:
    """`count` queries sent to one adapter at once: each query and the second it reached Semantic Scholar."""

    async def search() -> list[tuple[str, float]]:
        clock = EventLoopClock(NOW)
        started: list[tuple[str, float]] = []

        async def answer(request: httpx.Request) -> httpx.Response:
            started.append((request.url.params["query"], (clock.now() - NOW).total_seconds()))
            await asyncio.sleep(answer_seconds)
            return httpx.Response(200, json=papers())

        factory = adapter_factory(clock=clock, transport=httpx.MockTransport(answer))
        provider = factory(provider_settings(api_key=api_key, timeout_seconds=timeout_seconds))
        await asyncio.gather(*(provider.search(query) for query in queries(count)))
        return started

    return search()


@pytest.mark.parametrize("api_key", [API_KEY, None], ids=["with a key", "without a key"])
@pytest.mark.parametrize(
    ("answer_seconds", "starts"),
    [(0.2, [0.0, 1.0, 2.0, 3.0]), (1.5, [0.0, 1.5, 3.0, 4.5])],
    ids=["fast answers: one a second", "slow answers: one at a time"],
)
def test_queries_with_a_key_or_without_are_sent_one_a_second_and_one_at_a_time(
    api_key: str | None, answer_seconds: float, starts: list[float]
) -> None:
    """Four queries at once: a second apart while answers are quick, and each after the one before
    is answered while they are slow, so never two at once."""
    started = run_in_virtual_time(started_at(4, api_key=api_key, answer_seconds=answer_seconds))
    assert started == [(f"capture query {number}", start) for number, start in enumerate(starts, start=1)]


def paced_search(
    *, api_key: str | None, answer_seconds: float, asked: list[str]
) -> Coroutine[Any, Any, tuple[SearchState, ProviderHealth]]:
    """Eleven queries through the registry's wrapper and the fan-out, every clock the loop's own."""

    async def search() -> tuple[SearchState, ProviderHealth]:
        clock = EventLoopClock(NOW)

        async def answer(request: httpx.Request) -> httpx.Response:
            asked.append(request.url.params["query"])
            await asyncio.sleep(answer_seconds)
            return httpx.Response(200, json=papers(a_paper(paperId=f"{len(asked):040x}")))

        factory = adapter_factory(clock=clock, transport=httpx.MockTransport(answer))
        registry = ProviderRegistry.from_settings(
            provider_settings(api_key=api_key), {SearchProviderName.SEMANTIC_SCHOLAR: factory}, clock=clock
        )
        stage = FanOutStage(registry, clock=clock, deadline_seconds=15.0)
        state = SearchState(
            search_id="01JBX3V5Q8R2T6V0W4X7Y1Z3A5",
            request=SearchRequest(query="heg answers"),
            queries=queries(11),
        )
        searched = await stage.run(state)
        (health,) = registry.health()
        return searched, health

    return search()


@pytest.mark.parametrize(
    ("api_key", "not_asked"),
    [(API_KEY, NOT_ASKED_WITH_A_KEY), (None, NOT_ASKED_WITHOUT_A_KEY)],
    ids=["with a key", "without a key"],
)
def test_eleven_queries_send_what_fits_and_answer_the_rest_not_asked_with_the_breaker_closed(
    api_key: str | None, not_asked: str
) -> None:
    """Written by hand. Answers take 1.5 s and only one query is out at a time, so the queries start
    at 0, 1.5, 3, 4.5, 6 and 7.5 s and are answered 1.5 s later. A query is sent only while its answer
    could come back within the 10 s timeout: before 10 s less the reserve, the median answer time
    (1.5 s), so before 8.5 s. The seventh's turn would be 9 s, so it and the four after it are
    answered "not asked" at 8.5 s, never sent, and counted apart from answers and failures."""
    asked: list[str] = []
    state, health = run_in_virtual_time(paced_search(api_key=api_key, answer_seconds=1.5, asked=asked))

    assert asked == [f"capture query {number}" for number in range(1, 7)]
    statuses = state.provider_statuses
    assert [(status.provider, status.outcome, status.error) for status in statuses] == [
        ("semantic_scholar", ProviderOutcome.OK, None)
    ] * 11
    assert [
        (response.partial, response.error, [result.provider_record_id for result in response.results])
        for status in statuses
        if (response := status.response) is not None
    ] == [(False, None, [f"{number:040x}"]) for number in range(1, 7)] + [(True, not_asked, [])] * 5
    assert [round(status.elapsed_ms) for status in statuses] == [1500, 3000, 4500, 6000, 7500, 9000] + [
        8500
    ] * 5
    assert search_status(statuses) is SearchStatus.PARTIAL
    assert health.state is BreakerState.CLOSED
    assert (health.success_count, health.not_asked_count, health.error_count) == (6, 5, 0)
    assert (health.consecutive_failures, health.last_error) == (0, None)


@pytest.mark.parametrize(
    ("answers", "expected"),
    [((), 2.0), ((0.2,), 1.0), ((1.5,), 1.5), ((0.5, 3.0, 4.0), 3.0), ((7.0,), 5.0)],
    ids=["before any answer", "at least 1 s", "the answer seen", "the median", "at most half the timeout"],
)
def test_the_reserve_is_the_median_answer_time_clamped(answers: tuple[float, ...], expected: float) -> None:
    async def answered() -> float:
        clock = EventLoopClock(NOW)
        times = iter(answers)

        async def answer(request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(next(times))
            return httpx.Response(200, json=papers())

        factory = semantic_scholar_factory(
            HttpSettings(), version=VERSION, clock=clock, transport=httpx.MockTransport(answer)
        )
        provider = factory(provider_settings(timeout_seconds=10.0))
        for _ in answers:
            await provider.search(CARBON_CAPTURE)
        return provider.reserve_seconds

    assert run_in_virtual_time(answered()) == expected


# --------------------------------------------------------------------------------------------
# Refusals and failures
# --------------------------------------------------------------------------------------------


async def test_a_429_with_retry_after_is_rate_limited_for_that_long() -> None:
    replayed = replay_with_respx(build_over)(recording("paper_search_rate_limited"))
    with pytest.raises(ProviderRateLimited) as caught:
        await replayed.provider.search(CARBON_CAPTURE)
    assert caught.value.retry_after_seconds == 30
    assert str(caught.value) == "semantic_scholar: HTTP 429 (retry after 30.0s)"
    assert len(replayed.sent()) == 1


async def test_a_403_for_a_refused_key_is_a_refusal_that_names_no_key() -> None:
    router = respx.MockRouter(assert_all_mocked=True)
    router.get(PAPER_SEARCH_URL).return_value = httpx.Response(
        403, json={"message": f"Forbidden: key {API_KEY} is not valid"}
    )
    with pytest.raises(ProviderUnavailable) as caught:
        await build_over(httpx.MockTransport(router.async_handler)).search(CARBON_CAPTURE)
    assert type(caught.value) is ProviderUnavailable
    assert str(caught.value) == "semantic_scholar: HTTP 403: the provider refused the request"


async def test_a_redirect_is_a_refusal_that_names_only_the_host() -> None:
    router = respx.MockRouter(assert_all_mocked=True)
    router.get(PAPER_SEARCH_URL).return_value = httpx.Response(
        301, headers={"location": f"https://elsewhere.example.org/search?key={API_KEY}"}
    )
    with pytest.raises(ProviderUnavailable) as caught:
        await build_over(httpx.MockTransport(router.async_handler)).search(CARBON_CAPTURE)
    assert str(caught.value) == "semantic_scholar: HTTP 301: redirected to elsewhere.example.org"


@pytest.mark.parametrize(
    "document",
    [
        {"total": 3, "offset": 0},
        {"total": 0, "offset": 0, "data": None},
        {"total": 1, "offset": 0, "data": "paper"},
        {"total": 1, "offset": 0, "data": ["3f1c0a9e2b7d4c6e8a0b1c2d3e4f5a6b7c8d9e0f"]},
        {"data": {"paperId": "ab"}},
        ["data"],
        {"error": "Unacceptable query params: [limit]"},
    ],
    ids=[
        "data missing with results",
        "null data",
        "data text",
        "a paper not an object",
        "data an object",
        "a list",
        "an error",
    ],
)
async def test_a_body_that_is_not_a_paper_list_is_unavailable(document: object) -> None:
    router = respx.MockRouter(assert_all_mocked=True)
    router.get(PAPER_SEARCH_URL).return_value = httpx.Response(200, json=document)
    with pytest.raises(
        ProviderUnavailable, match=r"^semantic_scholar: unreadable response: not a paper list$"
    ):
        await build_over(httpx.MockTransport(router.async_handler)).search(CARBON_CAPTURE)


async def test_a_body_that_is_not_json_is_unavailable() -> None:
    router = respx.MockRouter(assert_all_mocked=True)
    router.get(PAPER_SEARCH_URL).return_value = httpx.Response(200, content=b'{"total": 3, "da')
    with pytest.raises(ProviderUnavailable, match="semantic_scholar: unreadable response: JSONDecodeError"):
        await build_over(httpx.MockTransport(router.async_handler)).search(CARBON_CAPTURE)


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        (httpx.ReadTimeout("timed out"), "semantic_scholar: timed out"),
        (httpx.ConnectError("refused"), "semantic_scholar: transport failure: ConnectError"),
    ],
    ids=["timeout", "connection refused"],
)
async def test_a_transport_failure_is_unavailable_and_keeps_its_cause(
    failure: httpx.HTTPError, message: str
) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise failure

    with pytest.raises(ProviderUnavailable) as caught:
        await build_over(httpx.MockTransport(fail)).search(CARBON_CAPTURE)
    assert str(caught.value) == message
    assert caught.value.__cause__ is failure


def registry_over(
    name: str, clock: FixedClock, **overrides: Any
) -> tuple[ProviderRegistry, ReplayedProvider]:
    """The registry's semantic_scholar provider over the named recording, and the registry itself."""
    registries: list[ProviderRegistry] = []

    def build(transport: httpx.AsyncBaseTransport) -> SearchProvider:
        factory = semantic_scholar_factory(
            HttpSettings(), version=VERSION, clock=clock, sleep=instant_sleep(clock), transport=transport
        )
        registry = ProviderRegistry.from_settings(
            provider_settings(**overrides), {SearchProviderName.SEMANTIC_SCHOLAR: factory}, clock=clock
        )
        registries.append(registry)
        return registry.get("semantic_scholar")

    replayed = replay_with_respx(build)(recording(name))
    return registries[0], replayed


async def test_a_429_holds_semantic_scholar_for_its_retry_after_and_sends_nothing_meanwhile() -> None:
    clock = FixedClock(NOW)
    registry, replayed = registry_over("paper_search_rate_limited", clock)
    with pytest.raises(ProviderRateLimited):
        await replayed.provider.search(CARBON_CAPTURE)
    (health,) = registry.health()
    assert health.rate_limited_until == clock.now() + timedelta(seconds=30)

    with pytest.raises(ProviderRateLimited):
        await replayed.provider.search(CARBON_CAPTURE)
    assert len(replayed.sent()) == 1


# --------------------------------------------------------------------------------------------
# The night of 2026-11-11: every keyless request answered 429 (v1-e07-t22)
# --------------------------------------------------------------------------------------------


def no_draw() -> float:
    raise AssertionError("a 429 with a Retry-After drew a random fraction")


ANSWER_SECONDS: Final = 0.25
"""How long each refusal takes to come back, so the queries behind the first have joined its queue."""


def every_answer_refused(
    *,
    status: int = 429,
    retry_after: str | None = None,
    draw: Callable[[], float],
    then_at: float | None = None,
) -> Coroutine[Any, Any, tuple[list[float], list[tuple[str, float]], ProviderHealth]]:
    """Eight queries at once to the keyless adapter in the registry's wrapper, every answer `status`.

    When each request reached Semantic Scholar, how each query ended (the error's type) and when, on
    the loop's virtual time, and the health after; with `then_at`, a ninth query asked at that second.
    """

    async def search() -> tuple[list[float], list[tuple[str, float]], ProviderHealth]:
        clock = EventLoopClock(NOW)
        sent: list[float] = []

        async def answer(request: httpx.Request) -> httpx.Response:
            sent.append((clock.now() - NOW).total_seconds())
            await asyncio.sleep(ANSWER_SECONDS)
            headers = {} if retry_after is None else {"Retry-After": retry_after}
            return httpx.Response(status, headers=headers)

        factory = adapter_factory(clock=clock, transport=httpx.MockTransport(answer))
        settings = provider_settings(api_key=None)
        provider = ResilientProvider(
            factory(settings),
            policy_from_settings(settings),
            clock=clock,
            secrets=configured_secrets(settings),
            random_fraction=draw,
        )

        async def one(query: ProviderQuery) -> tuple[str, float]:
            try:
                await provider.search(query)
            except ProviderError as error:
                return type(error).__name__, (clock.now() - NOW).total_seconds()
            return "answer", (clock.now() - NOW).total_seconds()

        ended = list(await asyncio.gather(*(one(query) for query in queries(8))))
        if then_at is not None:
            await asyncio.sleep(then_at - (clock.now() - NOW).total_seconds())
            ended.append(await one(CARBON_CAPTURE))
        return sent, ended, provider.health()

    return search()


def test_the_nights_case_sends_one_request_and_none_inside_its_hold() -> None:
    """Written by hand. Eight queries at once at one a second, every answer a 429 with no Retry-After
    a quarter second after its request, the default 10 s timeout. The first is sent at 0 s and
    refused at 0.25 s: held 2 s lengthened by a quarter (draw 0.5), until 2.75 s. The second's turn
    comes at 1 s, inside the hold: refused, never sent, and the six behind it get their turns at once
    and are refused at 1 s too. One failure, seven skips, the breaker closed. On 2026-11-11 all of
    them were sent, a second apart. A ninth query asked when the hold ends, at 2.75 s, is sent then;
    its 429 at 3 s is the second in a row, held 4 s lengthened by a quarter, until 8 s."""
    sent, ended, health = run_in_virtual_time(every_answer_refused(draw=lambda: 0.5, then_at=2.75))
    assert sent == [0.0, 2.75]
    assert ended == [("ProviderRateLimited", 0.25)] + [("ProviderRateLimited", 1.0)] * 7 + [
        ("ProviderRateLimited", 3.0)
    ]
    assert (health.error_count, health.skipped_count, health.success_count) == (2, 7, 0)
    assert (health.consecutive_failures, health.state) == (2, BreakerState.CLOSED)
    assert health.rate_limited_until == NOW + timedelta(seconds=8)


def test_the_nights_shape_of_failures_sends_nothing_once_the_breaker_opens() -> None:
    """Written by hand. The same eight queries, every answer a 503 a quarter second after its request,
    so nothing is held. Requests go at 0, 1 and 2 s, and the third failure opens the breaker at
    2.25 s. The fourth query's turn comes at 3 s with the breaker open: refused as the breaker refuses
    a call, and the four behind it at once. On 2026-11-11 the four after the breaker opened were sent."""
    sent, ended, health = run_in_virtual_time(every_answer_refused(status=503, draw=no_draw))
    assert sent == [0.0, 1.0, 2.0]
    assert (
        ended
        == [
            ("ProviderUnavailable", 0.25),
            ("ProviderUnavailable", 1.25),
            ("ProviderUnavailable", 2.25),
        ]
        + [("ProviderCircuitOpen", 3.0)] * 5
    )
    assert (health.error_count, health.skipped_count, health.state) == (3, 5, BreakerState.OPEN)
    assert health.open_until == NOW + timedelta(seconds=2.25 + 60)


def test_a_retry_after_holds_semantic_scholar_for_its_seconds_and_its_queue_is_refused_meanwhile() -> None:
    """Written by hand. Retry-After: 30 on the first answer, at 0.25 s: held until 30.25 s whatever the
    draw (none is drawn), so the seven queued queries are refused at 1 s and nothing more is sent."""
    sent, ended, health = run_in_virtual_time(every_answer_refused(retry_after="30", draw=no_draw))
    assert sent == [0.0]
    assert ended == [("ProviderRateLimited", 0.25)] + [("ProviderRateLimited", 1.0)] * 7
    assert health.rate_limited_until == NOW + timedelta(seconds=30.25)
    assert (health.error_count, health.skipped_count) == (1, 7)


def test_the_nights_search_names_semantic_scholar_rate_limited_on_every_query() -> None:
    """Through the registry and the fan-out, every answer a 429 with no Retry-After: one request, and
    every one of the eight queries is recorded `rate_limited`, so the footer names the provider rate
    limited and a search with no other provider fails. The first hold is at least 2 s, so the count
    does not depend on the draw."""

    async def search() -> tuple[list[str], SearchState]:
        clock = EventLoopClock(NOW)
        asked: list[str] = []

        async def answer(request: httpx.Request) -> httpx.Response:
            asked.append(request.url.params["query"])
            await asyncio.sleep(ANSWER_SECONDS)
            return httpx.Response(429)

        factory = adapter_factory(clock=clock, transport=httpx.MockTransport(answer))
        registry = ProviderRegistry.from_settings(
            provider_settings(api_key=None), {SearchProviderName.SEMANTIC_SCHOLAR: factory}, clock=clock
        )
        stage = FanOutStage(registry, clock=clock, deadline_seconds=15.0)
        state = SearchState(
            search_id="01JBX3V5Q8R2T6V0W4X7Y1Z3A5",
            request=SearchRequest(query="heg answers"),
            queries=queries(8),
        )
        return asked, await stage.run(state)

    asked, searched = run_in_virtual_time(search())
    assert asked == ["capture query 1"]
    statuses = searched.provider_statuses
    assert [status.outcome for status in statuses] == [ProviderOutcome.RATE_LIMITED] * 8
    assert search_status(statuses) is SearchStatus.FAILED


async def test_the_registry_answers_the_recorded_search_through_the_wrapper() -> None:
    _, replayed = registry_over("paper_search", FixedClock(NOW))
    answer = await replayed.provider.search(recording("paper_search").query)
    assert [result.provider_record_id for result in answer.results] == [
        "3f1c0a9e2b7d4c6e8a0b1c2d3e4f5a6b7c8d9e0f",
        "7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b",
        "c0ffee00c0ffee00c0ffee00c0ffee00c0ffee00",
    ]


# --------------------------------------------------------------------------------------------
# The key never surfaces
# --------------------------------------------------------------------------------------------


@pytest.mark.usefixtures("bare_protected_loggers")
async def test_no_key_reaches_a_log_line_an_error_a_repr_or_a_health_snapshot(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Through the wrapper, on the recorded search, the 429 with Retry-After, a 403 and a transport
    failure whose message quotes the key, and a query the pace answers "not asked"."""
    caplog.set_level(logging.DEBUG)
    clock = FixedClock(NOW)
    surfaces: list[str] = []
    for name in ("paper_search", "paper_search_rate_limited", "paper_search_empty"):
        registry, replayed = registry_over(name, clock)
        surfaces += [repr(registry), repr(replayed.provider), repr(registry.providers[0])]
        try:
            await replayed.provider.search(recording(name).query)
        except ProviderRateLimited as error:
            surfaces += [str(error), repr(error), str(error.__cause__), repr(error.__cause__)]
        surfaces += [snapshot.model_dump_json() for snapshot in registry.health()]

    def refuse(request: httpx.Request) -> httpx.Response:
        if request.url.params["query"] == "quoting":
            raise httpx.ConnectError(
                f"refused for x-api-key: {request.headers['x-api-key']}", request=request
            )
        return httpx.Response(403, text=f"key {request.headers['x-api-key']} refused")

    def refusing_registry(timeout_seconds: float) -> ProviderRegistry:
        factory = semantic_scholar_factory(
            HttpSettings(),
            version=VERSION,
            clock=clock,
            sleep=instant_sleep(clock),
            transport=httpx.MockTransport(refuse),
        )
        return ProviderRegistry.from_settings(
            provider_settings(timeout_seconds=timeout_seconds),
            {SearchProviderName.SEMANTIC_SCHOLAR: factory},
            clock=clock,
        )

    refusing = refusing_registry(10.0)
    for text in ("refused", "quoting"):
        with pytest.raises(ProviderUnavailable) as caught:
            await refusing.get("semantic_scholar").search(ProviderQuery(query=text))
        surfaces += [
            str(caught.value),
            repr(caught.value),
            str(caught.value.__cause__),
            repr(caught.value.__cause__),
        ]
    surfaces += [snapshot.model_dump_json() for snapshot in refusing.health()]
    # A 1 s timeout keeps half a second for the answer, so a second query, due a second after the
    # first, is never sent.
    hurried = refusing_registry(1.0)
    with pytest.raises(ProviderUnavailable):
        await hurried.get("semantic_scholar").search(ProviderQuery(query="refused"))
    not_asked = await hurried.get("semantic_scholar").search(ProviderQuery(query="too late"))
    surfaces += [not_asked.model_dump_json(), *(snapshot.model_dump_json() for snapshot in hurried.health())]
    logger.warning("adapter state: key=%s", API_KEY)
    surfaces += [record.getMessage() for record in caplog.records]

    assert any(
        "HTTP Request: GET https://api.semanticscholar.org/graph/v1/paper/search" in text for text in surfaces
    )
    assert any("refused for x-api-key: ***" in text for text in surfaces)
    assert any("adapter state: key=***" in text for text in surfaces)
    assert not_asked.partial
    assert not [text for text in surfaces if API_KEY in text]


@pytest.mark.usefixtures("bare_protected_loggers")
@pytest.mark.parametrize("logger_name", PROTECTED_LOGGERS)
def test_the_adapter_alone_protects_the_logs_from_its_key(
    logger_name: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Unwrapped, as the kit runs it: the constructor registers the key, so no log line carries it."""
    caplog.set_level(logging.DEBUG)
    key = "s2key-unwrap7"
    build_over(httpx.MockTransport(lambda request: httpx.Response(200)), api_key=f"  {key} ")

    logging.getLogger(logger_name).warning("headers {'x-api-key': '%s'}", key)

    assert [record.getMessage() for record in caplog.records] == ["headers {'x-api-key': '***'}"]


def test_the_repr_says_whether_a_key_is_configured_and_nothing_more() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200))
    assert repr(build_over(transport)) == "SemanticScholarProvider(api_key=configured)"
    assert repr(build_over(transport, api_key=None)) == "SemanticScholarProvider(api_key=none)"


# --------------------------------------------------------------------------------------------
# The shared contract kit
# --------------------------------------------------------------------------------------------


class TestSemanticScholarProviderWithAKey(SearchProviderContract):
    """Semantic Scholar with an API key, on the recorded carbon capture search."""

    @pytest.fixture
    def recording(self) -> Recording:
        return recording("paper_search")

    @pytest.fixture
    def replay(self) -> ReplayFactory:
        return replay_with_respx(build_over)

    @pytest.fixture
    def secrets(self) -> tuple[str, ...]:
        return (API_KEY,)

    @pytest.fixture
    def max_attempts(self) -> int:
        """The adapter never retries: one request per search."""
        return 1


class TestSemanticScholarProviderWithoutAKey(TestSemanticScholarProviderWithAKey):
    """No key: the same request (a key is a header, never in the URL) and the same answer."""

    @pytest.fixture
    def replay(self) -> ReplayFactory:
        return replay_with_respx(lambda transport: build_over(transport, api_key=None))

    @pytest.fixture
    def secrets(self) -> tuple[str, ...]:
        return ()


class TestSemanticScholarProviderOnAPageWithoutPdfs(TestSemanticScholarProviderWithAKey):
    """A page with no open-access PDF, from a hyphenated query sent with a space."""

    @pytest.fixture
    def recording(self) -> Recording:
        return recording("paper_search_without_pdfs")


class TestSemanticScholarProviderOnAnEmptyResult(TestSemanticScholarProviderWithAKey):
    """A search Semantic Scholar has nothing for."""

    @pytest.fixture
    def recording(self) -> Recording:
        return recording("paper_search_empty")


def test_every_recorded_request_carries_its_key_only_in_the_header() -> None:
    """The binding replays by URL alone, so this pins the header on the recorded requests too."""
    seen: list[httpx.Request] = []
    for name in ("paper_search", "paper_search_without_pdfs", "paper_search_empty"):
        replayed = replay_with_respx(build_over, seen)(recording(name))
        asyncio.run(replayed.provider.search(recording(name).query))
    assert [request.headers.get("x-api-key") for request in seen] == [API_KEY] * 3
    assert not [request for request in seen if API_KEY in str(request.url)]
    assert [json.loads(path.read_text(encoding="utf-8")) for path in FIXTURES.glob("*.json")]
    assert not [path.name for path in FIXTURES.iterdir() if API_KEY in path.read_text(encoding="utf-8")]
