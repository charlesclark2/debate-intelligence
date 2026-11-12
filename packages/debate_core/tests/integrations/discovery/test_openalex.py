"""OpenAlexProvider: the request it sends, how works map to candidates, and the contract kit.

Every OpenAlex answer here is hand-written from OpenAlex's documented response shape and lives in
`packages/debate_core/tests/fixtures/discovery/openalex/`, beside the fake provider's; every
expected mapping is written by hand from those bodies (working agreement 6). Nothing here reaches
the network.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Collection, Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Final

import httpx
import pytest
import respx
from pydantic import SecretStr

from debate_core.application.errors import (
    ProviderCircuitOpen,
    ProviderRateLimited,
    ProviderUnavailable,
)
from debate_core.application.ports.providers import MultiQuerySearchProvider, SearchProvider
from debate_core.application.settings import HttpSettings, ProviderSettings, SearchProviderName
from debate_core.domain.discovery import BreakerState, CandidateResult, ProviderQuery, ProviderResponse
from debate_core.domain.enums import SourceType
from debate_core.domain.search import SearchFilters
from debate_core.integrations.discovery.openalex import (
    MAX_URL_CHARS,
    OPENALEX_WORKS_URL,
    OpenAlexProvider,
    asked_alone,
    candidate_from_work,
    joined_search,
    openalex_factory,
    rebuild_abstract,
    source_type_for,
    works_parameters,
    works_url,
)
from debate_core.integrations.discovery.redaction import PROTECTED_LOGGERS, logger
from debate_core.integrations.discovery.registry import ProviderRegistry
from debate_core.testing.contracts.search_provider import (
    Recording,
    ReplayedProvider,
    ReplayFactory,
    SearchProviderContract,
    SentRequest,
    TransportFailure,
    assert_no_secret_surfaces,
    load_recording,
)
from debate_core.testing.fakes.clock_and_ids import FixedClock

pytestmark = pytest.mark.anyio

FIXTURES: Final = Path(__file__).resolve().parents[2] / "fixtures" / "discovery" / "openalex"
API_KEY: Final = "openalex-test-key-5f2c9e81"
CONTACT_EMAIL: Final = "openalex-coach@example.org"
VERSION: Final = "0.0.0-test"
SELECT: Final = (
    "id,doi,display_name,publication_date,type,cited_by_count,open_access,best_oa_location,primary_location,"
    "authorships,abstract_inverted_index"
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def bare_protected_loggers() -> Iterator[None]:
    """The protected loggers start with no filters, and get theirs back afterwards.

    Their filters are shared by the whole process: a test that ran earlier in this worker (the
    OpenCaselist client's, the fetcher's) may have left one that hides a leak (working agreement 10).
    """
    saved = {name: list(logging.getLogger(name).filters) for name in PROTECTED_LOGGERS}
    for name in PROTECTED_LOGGERS:
        logging.getLogger(name).filters.clear()
    yield
    for name, filters in saved.items():
        logging.getLogger(name).filters[:] = filters


def provider_settings(*, api_key: str | None = API_KEY, **overrides: Any) -> ProviderSettings:
    """OpenAlex enabled, with a key (unless `None`) and a contact email it must never be sent."""
    return ProviderSettings(
        enabled=(SearchProviderName.OPENALEX,),
        openalex_api_key=SecretStr(api_key) if api_key is not None else None,
        contact_email=SecretStr(CONTACT_EMAIL),
        **overrides,
    )


def build_over(
    transport: httpx.AsyncBaseTransport, *, api_key: str | None = API_KEY, clock: FixedClock | None = None
) -> OpenAlexProvider:
    """The adapter exactly as the registry builds it, over `transport`."""
    factory = openalex_factory(
        HttpSettings(), version=VERSION, clock=clock or FixedClock(), transport=transport
    )
    return factory(provider_settings(api_key=api_key))


def replay_with_respx(
    build: Callable[[httpx.AsyncBaseTransport], SearchProvider], seen: list[httpx.Request] | None = None
) -> ReplayFactory:
    """Serve a recording's exchanges through respx, and nothing else.

    A copy of the FakeProvider binding's (`test_fake_provider.py`), with two changes: the adapter is
    built from a transport, so that the factory's own client is the one under test, and every
    request is kept in `seen` when given, so that a test can read its headers. Transport failures
    are raised here rather than as respx side effects, because respx re-raises a side effect `from`
    an error that quotes the matched route.
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


def a_work(**fields: Any) -> dict[str, Any]:
    """A minimal mappable work, with `fields` laid over it."""
    return {"id": "https://openalex.org/W100", "display_name": "A title", **fields}


# --------------------------------------------------------------------------------------------
# Work type to source type
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("work_type", "expected"),
    [
        ("article", SourceType.SCHOLARLY),
        ("book", SourceType.SCHOLARLY),
        ("book-chapter", SourceType.SCHOLARLY),
        ("book-review", SourceType.SCHOLARLY),
        ("conference-abstract", SourceType.SCHOLARLY),
        ("conference-paper", SourceType.SCHOLARLY),
        ("data-paper", SourceType.SCHOLARLY),
        ("dissertation", SourceType.SCHOLARLY),
        ("editorial", SourceType.SCHOLARLY),
        ("erratum", SourceType.SCHOLARLY),
        ("letter", SourceType.SCHOLARLY),
        ("peer-review", SourceType.SCHOLARLY),
        ("preprint", SourceType.SCHOLARLY),
        ("reference-entry", SourceType.SCHOLARLY),
        ("retraction", SourceType.SCHOLARLY),
        ("review", SourceType.SCHOLARLY),
        ("software-paper", SourceType.SCHOLARLY),
        ("report", SourceType.OTHER),
        ("standard", SourceType.OTHER),
        ("dataset", SourceType.OTHER),
        ("libguides", SourceType.OTHER),
        ("other", SourceType.OTHER),
        ("paratext", SourceType.OTHER),
        ("software", SourceType.OTHER),
        ("supplementary-materials", SourceType.OTHER),
    ],
)
def test_each_documented_work_type_maps_to_its_source_type(work_type: str, expected: SourceType) -> None:
    assert source_type_for(work_type) is expected


@pytest.mark.parametrize(
    "work_type",
    ["journal-article", "posted-content", "Article", "book-section", "", None, 7, ["article"]],
    ids=repr,
)
def test_an_unknown_or_missing_work_type_maps_to_other(work_type: object) -> None:
    assert source_type_for(work_type) is SourceType.OTHER


# --------------------------------------------------------------------------------------------
# Abstract rebuild
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("inverted_index", "expected"),
    [
        ({"Despite": [0], "growing": [1], "interest": [2]}, "Despite growing interest"),
        ({"interest": [2], "Despite": [0], "growing": [1]}, "Despite growing interest"),
        ({"the": [0, 3], "cat": [1], "saw": [2], "dog.": [4]}, "the cat saw the dog."),
        ({"later": [9], "first": [0]}, "first later"),
        ({"only": [0], "skipped": [], "bool": [True], "negative": [-1], "text": ["1"]}, "only"),
        ({"kept": [0], "not a list": 1, "also": [1]}, "kept also"),
        ({}, None),
        ({"ghost": []}, None),
        (None, None),
        ("Despite growing interest", None),
        ([["Despite", [0]]], None),
    ],
    ids=[
        "in order",
        "keys out of order",
        "a word at two positions",
        "a gap in the positions",
        "unreadable positions ignored",
        "unreadable entries ignored",
        "empty index",
        "no positions at all",
        "null",
        "plain text instead of an index",
        "a list instead of an index",
    ],
)
def test_the_abstract_is_rebuilt_in_word_order(inverted_index: object, expected: str | None) -> None:
    assert rebuild_abstract(inverted_index) == expected


# --------------------------------------------------------------------------------------------
# Work to CandidateResult mapping
# --------------------------------------------------------------------------------------------


def test_the_recorded_works_map_to_the_hand_written_candidates() -> None:
    works = body("works_search.body.json")["results"]
    expected = json.loads((FIXTURES / "works_search.expected.json").read_text(encoding="utf-8"))
    mapped = [candidate_from_work(work) for work in works]
    assert mapped == [CandidateResult.model_validate(item) for item in expected]


def test_the_mapping_keeps_no_affiliation_orcid_or_raw_author_name() -> None:
    works = body("works_search.body.json")["results"]
    stored = json.dumps(
        [candidate.model_dump(mode="json") for work in works if (candidate := candidate_from_work(work))]
    )
    for absent in (
        "orcid",
        "0000-0000-0000-0001",
        "University of Nowhere",
        "Example Policy Institute",
        "Department of Invented Economics",
        "A. Placeholder",
        "Q. Unmatched",
        "openalex.org/A5000000001",
    ):
        assert absent not in stored


@pytest.mark.parametrize(
    "work",
    [
        {"id": "https://openalex.org/W100"},
        a_work(display_name=None),
        a_work(display_name="   "),
        a_work(id=None),
        a_work(id="https://openalex.org/A100"),
        a_work(id="https://openalex.org/W"),
        a_work(id="https://openalex.org/W12x"),
    ],
    ids=["no title", "null title", "blank title", "no id", "an author id", "a bare W", "not digits"],
)
def test_a_work_with_no_title_or_no_work_id_is_not_a_candidate(work: dict[str, Any]) -> None:
    assert candidate_from_work(work) is None


def test_the_work_id_is_read_from_the_url_or_bare() -> None:
    for spelling in ("https://openalex.org/W2741809807", "https://openalex.org/W2741809807/", "W2741809807"):
        candidate = candidate_from_work(a_work(id=spelling))
        assert candidate is not None
        assert candidate.provider_record_id == "W2741809807"
        assert candidate.identifiers.openalex_id == "W2741809807"


def test_the_url_is_the_landing_page_then_the_doi_then_the_openalex_record() -> None:
    landing = a_work(
        doi="https://doi.org/10.5555/x.1",
        primary_location={"landing_page_url": "https://publisher.example.org/x1"},
    )
    doi_only = a_work(doi="https://doi.org/10.5555/X.2", primary_location={"landing_page_url": "ftp://x"})
    neither = a_work(primary_location=None)
    assert [candidate_from_work(work).url for work in (landing, doi_only, neither)] == [  # type: ignore[union-attr]
        "https://publisher.example.org/x1",
        "https://doi.org/10.5555/x.2",
        "https://openalex.org/W100",
    ]


def test_a_doi_that_is_not_a_doi_is_dropped_rather_than_failing_the_work() -> None:
    candidate = candidate_from_work(a_work(doi="https://doi.org/not-a-doi"))
    assert candidate is not None
    assert candidate.identifiers.doi is None
    assert candidate.url == "https://openalex.org/W100"


@pytest.mark.parametrize(
    ("work", "expected"),
    [
        (
            a_work(
                best_oa_location={
                    "is_oa": True,
                    "pdf_url": "https://a.example.org/p.pdf",
                    "landing_page_url": "https://a.example.org/p",
                }
            ),
            "https://a.example.org/p.pdf",
        ),
        (
            a_work(
                best_oa_location={
                    "is_oa": True,
                    "pdf_url": None,
                    "landing_page_url": "https://a.example.org/p",
                }
            ),
            "https://a.example.org/p",
        ),
        (
            a_work(
                best_oa_location={"is_oa": False, "pdf_url": "https://a.example.org/closed.pdf"},
                open_access={"is_oa": True, "oa_url": "https://b.example.org/open"},
            ),
            "https://b.example.org/open",
        ),
        (
            a_work(
                best_oa_location=None, open_access={"is_oa": True, "oa_url": "https://b.example.org/open"}
            ),
            "https://b.example.org/open",
        ),
        (
            a_work(best_oa_location=None, open_access={"is_oa": False, "oa_url": "https://b.example.org/x"}),
            None,
        ),
        (a_work(best_oa_location={"is_oa": True, "pdf_url": "not a url"}), None),
        (a_work(), None),
    ],
    ids=[
        "best location pdf",
        "best location landing page",
        "closed best location falls back to oa_url",
        "no best location falls back to oa_url",
        "closed work",
        "unusable url",
        "nothing said",
    ],
)
def test_the_open_access_url_is_the_best_open_copy(work: dict[str, Any], expected: str | None) -> None:
    candidate = candidate_from_work(work)
    assert candidate is not None
    assert candidate.open_access_url == expected


@pytest.mark.parametrize(
    ("publication_date", "expected"),
    [
        ("2024-02-29", "2024-02-29T00:00:00+00:00"),
        ("2024-02-30", None),
        ("2024", None),
        (None, None),
        (20240229, None),
    ],
)
def test_the_publication_date_is_midnight_utc(publication_date: object, expected: str | None) -> None:
    candidate = candidate_from_work(a_work(publication_date=publication_date))
    assert candidate is not None
    assert (candidate.published_at.isoformat() if candidate.published_at else None) == expected


def test_authors_are_display_names_in_byline_order_and_unnamed_authors_are_left_out() -> None:
    work = a_work(
        authorships=[
            {"author": {"display_name": " First Person "}},
            {"author": {"display_name": None}, "raw_author_name": "Raw Name"},
            {"author": None},
            "not an authorship",
            {"author": {"display_name": "Last Person"}},
        ]
    )
    candidate = candidate_from_work(work)
    assert candidate is not None
    assert candidate.authors == ("First Person", "Last Person")


def test_the_venue_is_the_primary_locations_source_and_absent_without_one() -> None:
    named = candidate_from_work(a_work(primary_location={"source": {"display_name": "Invented Review"}}))
    unnamed = candidate_from_work(a_work(primary_location={"source": None}))
    assert named is not None and named.publication == "Invented Review"
    assert unnamed is not None and unnamed.publication is None


@pytest.mark.parametrize(
    ("cited_by_count", "expected"),
    [(42, 42), (0, 0), (-1, None), ("12", None), (3.0, None), (True, None), (None, None)],
    ids=["a count", "zero", "negative", "a string", "a float", "a bool", "null"],
)
def test_the_citation_count_is_a_non_negative_integer_or_none(
    cited_by_count: object, expected: int | None
) -> None:
    candidate = candidate_from_work(a_work(cited_by_count=cited_by_count))
    assert candidate is not None
    assert candidate.citation_count == expected


def test_a_work_without_a_citation_count_has_none() -> None:
    candidate = candidate_from_work(a_work())
    assert candidate is not None
    assert candidate.citation_count is None


@pytest.mark.parametrize(
    ("open_access", "expected"),
    [
        ({"is_oa": True, "oa_url": None}, True),
        ({"is_oa": False}, False),
        ({"is_oa": None}, None),
        ({"is_oa": "true"}, None),
        ({"is_oa": 1}, None),
        ({}, None),
        (None, None),
        (True, None),
    ],
    ids=[
        "open without a link",
        "closed",
        "null",
        "a string",
        "an int",
        "no is_oa",
        "null object",
        "not an object",
    ],
)
def test_open_access_is_openalexs_is_oa_or_none(open_access: object, expected: bool | None) -> None:
    candidate = candidate_from_work(a_work(open_access=open_access))
    assert candidate is not None
    assert candidate.open_access is expected


def test_a_work_without_open_access_has_none() -> None:
    candidate = candidate_from_work(a_work())
    assert candidate is not None
    assert candidate.open_access is None


# --------------------------------------------------------------------------------------------
# The request
# --------------------------------------------------------------------------------------------

HEALTH_INSURANCE: Final = ProviderQuery(
    query="health insurance",
    filters=SearchFilters(
        since=datetime(2020, 1, 1, tzinfo=UTC), until=datetime(2024, 12, 31, tzinfo=UTC), max_results=3
    ),
)


def routed(
    *, headers: dict[str, str] | None = None
) -> tuple[respx.MockRouter, respx.Route, list[httpx.Request]]:
    """A router whose one route matches the health insurance search, with `headers` if given."""
    router = respx.MockRouter(assert_all_called=False, assert_all_mocked=True)
    route = router.get(
        OPENALEX_WORKS_URL,
        params={
            "search": "health insurance",
            "filter": "from_publication_date:2020-01-01,to_publication_date:2024-12-31",
            "per_page": "3",
            "select": SELECT,
        },
        headers=headers or {},
    )
    route.return_value = httpx.Response(200, json={"meta": {"count": 0}, "results": []})
    return router, route, []


def transport_for(router: respx.MockRouter, seen: list[httpx.Request]) -> httpx.MockTransport:
    async def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return await router.async_handler(request)

    return httpx.MockTransport(handle)


async def test_a_request_with_since_and_until_carries_the_date_filters_and_the_key_header() -> None:
    router, route, seen = routed(headers={"Authorization": f"Bearer {API_KEY}"})
    provider = build_over(transport_for(router, seen))

    answer = await provider.search(HEALTH_INSURANCE)

    assert route.call_count == 1
    assert answer == ProviderResponse(provider="openalex", results=(), elapsed_ms=answer.elapsed_ms)
    assert str(seen[0].url) == (
        "https://api.openalex.org/works?search=health+insurance"
        "&filter=from_publication_date%3A2020-01-01%2Cto_publication_date%3A2024-12-31&per_page=3"
        "&select=id%2Cdoi%2Cdisplay_name%2Cpublication_date%2Ctype%2Ccited_by_count%2Copen_access"
        "%2Cbest_oa_location"
        "%2Cprimary_location%2Cauthorships%2Cabstract_inverted_index"
    )


async def test_a_request_with_a_key_sends_it_only_in_the_authorization_header() -> None:
    router, _, seen = routed()
    await build_over(transport_for(router, seen)).search(HEALTH_INSURANCE)

    request = seen[0]
    assert request.headers["authorization"] == f"Bearer {API_KEY}"
    assert API_KEY not in str(request.url)
    assert "api_key" not in str(request.url)


async def test_a_request_without_a_key_has_no_authorization_header_and_no_mailto() -> None:
    router, route, seen = routed()
    await build_over(transport_for(router, seen), api_key=None).search(HEALTH_INSURANCE)

    request = seen[0]
    assert route.call_count == 1
    assert "authorization" not in request.headers
    assert "mailto" not in str(request.url)


@pytest.mark.parametrize("blank", ["", "   "], ids=["empty", "spaces"])
async def test_a_request_with_a_blank_key_is_sent_keyless(blank: str) -> None:
    router, _, seen = routed()
    provider = build_over(transport_for(router, seen), api_key=blank)
    await provider.search(HEALTH_INSURANCE)

    assert "authorization" not in seen[0].headers
    assert repr(provider) == "OpenAlexProvider(api_key=none)"


async def test_a_request_never_carries_the_contact_email_anywhere() -> None:
    router, _, seen = routed()
    await build_over(transport_for(router, seen)).search(HEALTH_INSURANCE)

    request = seen[0]
    encoded = CONTACT_EMAIL.replace("@", "%40")
    assert CONTACT_EMAIL not in str(request.url) and encoded not in str(request.url)
    assert not [name for name, value in request.headers.items() if CONTACT_EMAIL in value]


async def test_a_request_identifies_the_platform_and_sends_no_cookie() -> None:
    router, _, seen = routed()
    provider = build_over(transport_for(router, seen))
    await provider.search(HEALTH_INSURANCE)
    await provider.search(HEALTH_INSURANCE)

    assert {request.headers["user-agent"] for request in seen} == {HttpSettings().user_agent(VERSION)}
    assert all("cookie" not in request.headers for request in seen)


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        (
            SearchFilters(max_results=20),
            {"search": "methane leakage", "per_page": "20", "select": SELECT},
        ),
        (
            SearchFilters(since=datetime(2021, 3, 4, tzinfo=UTC), max_results=5),
            {
                "search": "methane leakage",
                "filter": "from_publication_date:2021-03-04",
                "per_page": "5",
                "select": SELECT,
            },
        ),
        (
            SearchFilters(until=datetime(2022, 7, 8, 23, 59, tzinfo=UTC), max_results=100),
            {
                "search": "methane leakage",
                "filter": "to_publication_date:2022-07-08",
                "per_page": "100",
                "select": SELECT,
            },
        ),
        (
            SearchFilters(max_results=101),
            {"search": "methane leakage", "per_page": "100", "select": SELECT},
        ),
        (
            SearchFilters(max_results=200),
            {"search": "methane leakage", "per_page": "100", "select": SELECT},
        ),
        (
            SearchFilters(max_results=1),
            {"search": "methane leakage", "per_page": "1", "select": SELECT},
        ),
    ],
    ids=["no window", "since only", "until only", "101 asks for 100", "200 asks for 100", "one"],
)
def test_the_request_parameters(filters: SearchFilters, expected: dict[str, str]) -> None:
    assert works_parameters(ProviderQuery(query="methane leakage", filters=filters)) == expected


def test_the_request_date_window_is_the_utc_date() -> None:
    eastern = timezone(timedelta(hours=-5))
    query = ProviderQuery(
        query="x",
        filters=SearchFilters(
            since=datetime(2020, 1, 1, 21, 30, tzinfo=eastern).astimezone(UTC),
            until=datetime(2020, 1, 3, 12, 0, tzinfo=UTC),
        ),
    )
    assert works_parameters(query)["filter"] == (
        "from_publication_date:2020-01-02,to_publication_date:2020-01-03"
    )


def numbered_works(first: int, count: int) -> list[dict[str, Any]]:
    return [
        {"id": f"https://openalex.org/W{number}", "display_name": f"Work {number}"}
        for number in range(first, first + count)
    ]


class PagedWorks:
    """Answers `/works` page by page from `pages` (page number to works, or a status), keeping every
    request; a page not in `pages` is an HTTP 599, so asking for one fails at the test's assertions."""

    def __init__(self, pages: dict[int, list[dict[str, Any]] | int]) -> None:
        self._pages = pages
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        answer = self._pages.get(int(request.url.params.get("page", "1")), 599)
        if isinstance(answer, int):
            return httpx.Response(answer)
        return httpx.Response(200, json={"results": answer})


async def test_a_request_above_100_results_asks_for_pages_of_100_until_it_has_them() -> None:
    """v1-e08-t10, the PM's ruling: pages up to `max_results`; 150 is two pages, the second cut to 50."""
    served = PagedWorks({1: numbered_works(1, 100), 2: numbered_works(101, 100)})
    query = ProviderQuery(query="x", filters=SearchFilters(max_results=150))

    answer = await build_over(httpx.MockTransport(served.handle)).search(query)

    assert [(request.url.params["page"], request.url.params["per_page"]) for request in served.requests] == [
        ("1", "100"),
        ("2", "100"),
    ]
    assert len(answer.results) == 150
    assert (answer.results[0].provider_record_id, answer.results[-1].provider_record_id) == ("W1", "W150")


async def test_paging_stops_at_a_short_page() -> None:
    served = PagedWorks({1: numbered_works(1, 60)})
    query = ProviderQuery(query="x", filters=SearchFilters(max_results=200))

    answer = await build_over(httpx.MockTransport(served.handle)).search(query)

    assert [request.url.params["page"] for request in served.requests] == ["1"]
    assert len(answer.results) == 60


async def test_a_later_page_failing_keeps_the_pages_read_and_says_the_answer_is_partial() -> None:
    served = PagedWorks({1: numbered_works(1, 100), 2: 503})
    query = ProviderQuery(query="x", filters=SearchFilters(max_results=200))

    answer = await build_over(httpx.MockTransport(served.handle)).search(query)

    assert len(answer.results) == 100
    assert (answer.partial, answer.error) == (True, "page 2 of 2 failed: HTTP 503")


# --------------------------------------------------------------------------------------------
# Every query of a search in one joined request (v1-e08-t10)
# --------------------------------------------------------------------------------------------

CARBON_WINDOW: Final = SearchFilters(since=datetime(2022, 1, 1, tzinfo=UTC), max_results=20)
CARBON_QUERIES: Final = tuple(
    ProviderQuery(query=text, filters=CARBON_WINDOW)
    for text in ("carbon tax revenue", "carbon tax unpopular voters", "border adjustment")
)


class JoinedWorks:
    """Answers every `/works` request with `works_joined.body.json` and keeps each request."""

    def __init__(self, status: dict[str, int] | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self._status = status or {}

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        status = self._status.get(request.url.params["search"])
        if status is not None:
            return httpx.Response(status)
        return httpx.Response(200, content=(FIXTURES / "works_joined.body.json").read_bytes())


async def test_every_query_of_a_search_goes_to_openalex_in_one_joined_request() -> None:
    served = JoinedWorks()

    await build_over(httpx.MockTransport(served.handle)).search_each(CARBON_QUERIES)

    [request] = served.requests
    assert dict(request.url.params) == {
        "search": "(carbon tax revenue) OR (carbon tax unpopular voters) OR (border adjustment)",
        "filter": "from_publication_date:2022-01-01",
        "per_page": "20",
        "select": SELECT,
    }


async def test_each_work_of_a_joined_search_goes_to_the_queries_whose_words_it_carries_or_to_all(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """By hand from the fixture (its README): one work per case of attribution."""
    provider = build_over(httpx.MockTransport(JoinedWorks().handle))
    with caplog.at_level(logging.INFO, logger="debate_core.integrations.discovery"):
        answers = await provider.search_each(CARBON_QUERIES)

    assert [[result.provider_record_id for result in answer.results] for answer in answers] == [
        ["W5550000001", "W5550000002", "W5550000004"],
        ["W5550000002", "W5550000004"],
        ["W5550000003", "W5550000004"],
    ]
    assert [answer.partial for answer in answers] == [False, False, False]
    assert "openalex: 3 queries in 1 requests; works matching one query 2, several 1, none 1" in [
        record.getMessage() for record in caplog.records
    ]


async def test_queries_with_different_windows_are_joined_per_window() -> None:
    """By hand: in the first request "Border adjustment…" matches neither query, so it goes to both
    (4 and 3 works); the third query is asked alone, so every work answered it (4)."""
    other = SearchFilters(since=datetime(2025, 6, 1, tzinfo=UTC), max_results=20)
    queries = (*CARBON_QUERIES[:2], ProviderQuery(query="border adjustment", filters=other))
    served = JoinedWorks()

    answers = await build_over(httpx.MockTransport(served.handle)).search_each(queries)

    assert [(request.url.params["search"], request.url.params["filter"]) for request in served.requests] == [
        ("(carbon tax revenue) OR (carbon tax unpopular voters)", "from_publication_date:2022-01-01"),
        ("border adjustment", "from_publication_date:2025-06-01"),
    ]
    assert [len(answer.results) for answer in answers] == [4, 3, 4]


async def test_one_joined_request_failing_leaves_its_queries_partial_and_answers_the_others() -> None:
    other = SearchFilters(since=datetime(2025, 6, 1, tzinfo=UTC), max_results=20)
    queries = (*CARBON_QUERIES[:2], ProviderQuery(query="border adjustment", filters=other))
    served = JoinedWorks(status={"border adjustment": 503})

    answers = await build_over(httpx.MockTransport(served.handle)).search_each(queries)

    assert [(len(answer.results), answer.partial, answer.error) for answer in answers] == [
        (4, False, None),
        (3, False, None),
        (0, True, "HTTP 503"),
    ]


async def test_every_joined_request_failing_raises_the_first_failure() -> None:
    served = JoinedWorks(
        status={"(carbon tax revenue) OR (carbon tax unpopular voters) OR (border adjustment)": 503}
    )
    with pytest.raises(ProviderUnavailable, match="openalex: HTTP 503"):
        await build_over(httpx.MockTransport(served.handle)).search_each(CARBON_QUERIES)


async def test_a_rate_limited_joined_request_fails_the_whole_call() -> None:
    other = SearchFilters(since=datetime(2025, 6, 1, tzinfo=UTC), max_results=20)
    queries = (CARBON_QUERIES[0], ProviderQuery(query="border adjustment", filters=other))
    served = JoinedWorks(status={"carbon tax revenue": 429})
    with pytest.raises(ProviderRateLimited):
        await build_over(httpx.MockTransport(served.handle)).search_each(queries)
    assert len(served.requests) == 1


NHI_LINK_QUERIES: Final = (
    "national health insurance political capital",
    "national health insurance partisan fight Congress",
    "national health insurance unpopular with voters",
    "national health insurance popular with Republicans",
    "national health insurance unpopular with Republicans",
    "national health insurance popular with Democrats",
    "national health insurance unpopular with Democrats",
    "national health insurance political capital United States",
    "single payer political capital United States",
    "Medicare for All political capital United States",
    "public option political capital United States",
    "Affordable Care Act political capital United States",
)
"""The politics DA's twelve link queries on the NHI topic (v1-e08-t14)."""

PARTY_TAILS: Final = (
    "popular with Republicans",
    "unpopular with Republicans",
    "popular with Democrats",
    "unpopular with Democrats",
)
MECHANISMS: Final = (
    "national health insurance",
    "single payer",
    "Medicare for All",
    "public option",
    "Affordable Care Act",
)
THIRTY_TWO: Final = (*NHI_LINK_QUERIES, *(f"{m} {t} United States" for m in MECHANISMS for t in PARTY_TAILS))
"""Today's twelve, then each mechanism crossed with the party-popularity templates: 32 queries."""

AC6_WINDOW: Final = SearchFilters(since=datetime(2021, 11, 3, tzinfo=UTC), max_results=200)


@pytest.mark.parametrize("texts", [NHI_LINK_QUERIES, THIRTY_TWO], ids=["12 queries", "32 queries"])
async def test_a_12_or_32_query_search_is_one_request_per_page(texts: tuple[str, ...]) -> None:
    """The PM's figures: both fit under 3,500 characters, so each is one request per page (two pages
    for `--max-results 200`)."""
    assert len(texts) in (12, 32)
    served = PagedWorks({1: numbered_works(1, 100), 2: numbered_works(101, 100)})
    queries = [ProviderQuery(query=text, filters=AC6_WINDOW) for text in texts]

    await build_over(httpx.MockTransport(served.handle)).search_each(queries)

    assert [request.url.params["page"] for request in served.requests] == ["1", "2"]
    assert {request.url.params["search"].count(") OR (") for request in served.requests} == {len(texts) - 1}
    assert max(len(str(request.url)) for request in served.requests) <= MAX_URL_CHARS


async def test_a_joined_search_too_long_for_one_url_is_split_into_the_fewest_requests_that_fit() -> None:
    """96 queries do not fit in one 3,500-character URL. Each request fits, and none could have taken the
    next request's first query: the split is greedy, so it is the fewest, and keeps the queries' order."""
    texts = [f"{text} survey {number}" for number in range(8) for text in NHI_LINK_QUERIES]
    queries = [ProviderQuery(query=text, filters=AC6_WINDOW) for text in texts]
    served = PagedWorks({1: [], 2: []})

    await build_over(httpx.MockTransport(served.handle)).search_each(queries)

    joined = [request.url.params["search"] for request in served.requests]
    assert len(joined) >= 2
    carried = [search.removeprefix("(").removesuffix(")").split(") OR (") for search in joined]
    assert [text for chunk in carried for text in chunk] == texts
    assert all(len(str(request.url)) <= MAX_URL_CHARS for request in served.requests)
    for chunk, following in zip(carried, carried[1:], strict=False):
        grown = [ProviderQuery(query=text, filters=AC6_WINDOW) for text in [*chunk, following[0]]]
        joined = ProviderQuery(query=joined_search(grown), filters=AC6_WINDOW)
        assert len(works_url(works_parameters(joined, page=2))) > MAX_URL_CHARS


# --------------------------------------------------------------------------------------------
# A query that could break a joined search is asked alone (v1-e08-t20, the PM's rulings of 2026-11-12)
# --------------------------------------------------------------------------------------------

ASKED_ALONE: Final = (
    "health insurance (reform",
    "health insurance reform)",
    "health) insurance (reform",
    'single "payer',
    '"single payer" "public option',
    "Medicare OR Medicaid",
    "AND health insurance",
    "health insurance NOT",
    "NOT",
    "(Medicare OR Medicaid)",
    '"public option" OR Medicaid',
    "Medicare OR(Medicaid)",
    '"single payer"AND Medicaid',
)
"""Each sends its query alone: an unbalanced parenthesis (by count, or one closed before it opens), an
odd number of double quotes, or an upper-case AND, OR or NOT outside a quoted phrase."""

JOINED: Final = (
    "health insurance",
    "Medicare or Medicaid",
    "and not or",
    "Oregon ANDROID NOTICE ORBIT",
    '"Medicare OR Medicaid"',
    '"single payer" health insurance',
    "(health insurance) reform",
    "Medicaid's not-for-profit plans",
)
"""None of these can reach outside its group: lower-case words, operators inside other words or inside a
quoted phrase, and balanced parentheses."""

ONE_ASKED_ALONE: Final = "1 query asked alone, not joined: an unbalanced parenthesis or double quote, or an AND, OR or NOT"
TWO_ASKED_ALONE: Final = "2 queries asked alone, not joined: an unbalanced parenthesis or double quote, or an AND, OR or NOT"


@pytest.mark.parametrize("text", ASKED_ALONE)
def test_a_query_that_could_reach_outside_its_group_is_asked_alone(text: str) -> None:
    assert asked_alone(text) is True


@pytest.mark.parametrize("text", JOINED)
def test_a_query_that_stays_inside_its_group_is_joined(text: str) -> None:
    assert asked_alone(text) is False


async def test_a_query_with_an_open_parenthesis_is_sent_alone_as_typed_and_the_others_joined() -> None:
    """By hand from the fixture (its README): without the second query, "W…2" matches only the first, and
    "W…4" neither, so it goes to both; the query asked alone gets every work of its own request."""
    lone = ProviderQuery(query="carbon tax (unpopular", filters=CARBON_WINDOW)
    queries = (CARBON_QUERIES[0], lone, CARBON_QUERIES[2])
    served = JoinedWorks()

    answers = await build_over(httpx.MockTransport(served.handle)).search_each(queries)

    assert [request.url.params["search"] for request in served.requests] == [
        "(carbon tax revenue) OR (border adjustment)",
        "carbon tax (unpopular",
    ]
    assert dict(served.requests[1].url.params) == {
        "search": "carbon tax (unpopular",
        "filter": "from_publication_date:2022-01-01",
        "per_page": "20",
        "select": SELECT,
    }
    assert [[result.provider_record_id for result in answer.results] for answer in answers] == [
        ["W5550000001", "W5550000002", "W5550000004"],
        ["W5550000001", "W5550000002", "W5550000003", "W5550000004"],
        ["W5550000003", "W5550000004"],
    ]
    assert [(answer.partial, answer.notes) for answer in answers] == [
        (False, ()),
        (False, (ONE_ASKED_ALONE,)),
        (False, ()),
    ]


async def test_queries_with_a_bare_operator_or_a_lone_quote_are_each_sent_alone_and_never_rewritten() -> None:
    texts = ("carbon tax OR levy", 'carbon "border adjustment', "carbon tax revenue")
    queries = tuple(ProviderQuery(query=text, filters=CARBON_WINDOW) for text in texts)
    served = JoinedWorks()

    answers = await build_over(httpx.MockTransport(served.handle)).search_each(queries)

    assert sorted(request.url.params["search"] for request in served.requests) == sorted(texts)
    assert [answer.notes for answer in answers] == [(TWO_ASKED_ALONE,), (TWO_ASKED_ALONE,), ()]


async def test_a_search_of_one_query_with_an_open_parenthesis_is_sent_as_typed_with_no_note() -> None:
    served = JoinedWorks()

    answer = await build_over(httpx.MockTransport(served.handle)).search(
        ProviderQuery(query="carbon tax (unpopular", filters=CARBON_WINDOW)
    )

    assert [request.url.params["search"] for request in served.requests] == ["carbon tax (unpopular"]
    assert (answer.partial, answer.notes) == (False, ())


# --------------------------------------------------------------------------------------------
# A joined request OpenAlex refuses with 400 is split in halves (v1-e08-t20, the PM's ruling Q4)
# --------------------------------------------------------------------------------------------

REFUSED: Final = "HTTP 400: the provider refused the request"
ONE_PAGE: Final = SearchFilters(max_results=20)


class RefusingWorks:
    """Answers `/works` with `status_for(search)` when it gives one, and otherwise with one work named
    after the request's number; keeps every request."""

    def __init__(self, status_for: Callable[[list[str]], int | None]) -> None:
        self._status_for = status_for
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        status = self._status_for(carried(request.url.params["search"]))
        if status is not None:
            return httpx.Response(status)
        number = len(self.requests)
        return httpx.Response(
            200, json={"results": [{"id": f"https://openalex.org/W{number}", "display_name": f"Work {number}"}]}
        )

    def carried(self) -> list[list[int]]:
        """The number of each query every request carried, in the order sent."""
        return [
            [int(text.rsplit(" ", 1)[1]) for text in carried(request.url.params["search"])]
            for request in self.requests
        ]


def carried(search: str) -> list[str]:
    """The queries a `search=` carries: one as it is, or several parenthesised and joined by OR."""
    if search.startswith("(") and search.endswith(")"):
        return search.removeprefix("(").removesuffix(")").split(") OR (")
    return [search]


def numbered_queries(count: int, refused: Collection[int] = ()) -> tuple[ProviderQuery, ...]:
    """`count` queries of one window, each ending in its number; those in `refused` carry "zzrefused"."""
    return tuple(
        ProviderQuery(query=f"carbon tax {'zzrefused' if number in refused else 'survey'} {number}", filters=ONE_PAGE)
        for number in range(count)
    )


def refusing(*numbers: int) -> Callable[[list[str]], int | None]:
    """400 to any request that carries one of the queries `numbers`."""
    return lambda texts: 400 if any(int(text.rsplit(" ", 1)[1]) in numbers for text in texts) else None


async def test_a_refused_joined_request_is_split_in_halves_until_the_one_refused_query_is_found() -> None:
    """By hand: 8 queries, the first refused. Each split asks the first half and then the second, and goes
    on only into the half refused beside one answered: 1 + 2 * 3 = 7 requests."""
    served = RefusingWorks(refusing(0))

    answers = await build_over(httpx.MockTransport(served.handle)).search_each(numbered_queries(8, refused=(0,)))

    assert served.carried() == [
        [0, 1, 2, 3, 4, 5, 6, 7],
        [0, 1, 2, 3],
        [4, 5, 6, 7],
        [0, 1],
        [2, 3],
        [0],
        [1],
    ]
    assert [(len(answer.results), answer.partial, answer.error) for answer in answers] == [
        (0, True, REFUSED),
        *[(1, False, None)] * 7,
    ]
    assert [[result.provider_record_id for result in answer.results] for answer in answers[1:]] == [
        ["W7"],
        ["W5"],
        ["W5"],
        ["W3"],
        ["W3"],
        ["W3"],
        ["W3"],
    ]


@pytest.mark.parametrize(("count", "most"), [(2, 3), (3, 5), (8, 7), (37, 13)])
async def test_finding_one_refused_query_costs_at_most_one_plus_two_per_halving(count: int, most: int) -> None:
    """The PM's bound: 1 + 2 * ceil(log2 n) requests a page for a request of n queries, reached by the
    query that is halved the most times. Written by hand: ceil(log2) of 2, 3, 8 and 37 is 1, 2, 3, 6."""
    costs = []
    for bad in range(count):
        served = RefusingWorks(refusing(bad))
        answers = await build_over(httpx.MockTransport(served.handle)).search_each(
            numbered_queries(count, refused=(bad,))
        )
        assert [answer.error for answer in answers] == [REFUSED if n == bad else None for n in range(count)]
        costs.append(len(served.requests))
    assert max(costs) == most


@pytest.mark.parametrize("count", [2, 8, 37])
async def test_a_request_whose_two_halves_are_both_refused_stops_there_and_fails_as_a_400(count: int) -> None:
    """The PM's ruling: when both halves are refused the refusal is not about size, so three requests and no
    more; the request's every query fails, and as the search's only request it raises, as today."""
    served = RefusingWorks(lambda texts: 400)

    with pytest.raises(ProviderUnavailable, match=f"^openalex: {REFUSED}$"):
        await build_over(httpx.MockTransport(served.handle)).search_each(numbered_queries(count))

    assert len(served.requests) == 3


async def test_two_refused_halves_deeper_in_the_split_stop_there_and_fail_their_queries() -> None:
    """By hand: queries 0 and 2 refused. The first half is refused beside an answered second, so it is
    split; both its halves are refused, so the split stops and queries 0 to 3 fail. Five requests."""
    served = RefusingWorks(refusing(0, 2))

    answers = await build_over(httpx.MockTransport(served.handle)).search_each(
        numbered_queries(8, refused=(0, 2))
    )

    assert served.carried() == [[0, 1, 2, 3, 4, 5, 6, 7], [0, 1, 2, 3], [4, 5, 6, 7], [0, 1], [2, 3]]
    assert [answer.error for answer in answers] == [REFUSED] * 4 + [None] * 4


async def test_a_refused_half_beside_a_half_that_failed_otherwise_is_not_split_further() -> None:
    """Only a half refused beside an answered one is split again. Here the other half answers 503, so the
    refused half's queries fail as a 400 and the other's as a 503; a query in another window answers."""
    other = ProviderQuery(query="border adjustment 9", filters=CARBON_WINDOW)

    def status_for(texts: list[str]) -> int | None:
        if "carbon tax zzrefused 0" in texts:
            return 400
        return 503 if "carbon tax survey 3" in texts else None

    served = RefusingWorks(status_for)

    answers = await build_over(httpx.MockTransport(served.handle)).search_each(
        (*numbered_queries(4, refused=(0,)), other)
    )

    assert len(served.requests) == 4
    assert [(answer.partial, answer.error) for answer in answers] == [
        (True, REFUSED),
        (True, REFUSED),
        (True, "HTTP 503"),
        (True, "HTTP 503"),
        (False, None),
    ]


async def test_a_single_query_refused_with_400_fails_as_today_in_one_request() -> None:
    served = RefusingWorks(lambda texts: 400)

    with pytest.raises(ProviderUnavailable, match=f"^openalex: {REFUSED}$"):
        await build_over(httpx.MockTransport(served.handle)).search(numbered_queries(1)[0])

    assert len(served.requests) == 1


async def test_a_joined_request_refused_otherwise_than_with_400_is_not_split() -> None:
    served = RefusingWorks(lambda texts: 403)

    with pytest.raises(ProviderUnavailable, match="^openalex: HTTP 403: the provider refused the request$"):
        await build_over(httpx.MockTransport(served.handle)).search_each(numbered_queries(4))

    assert len(served.requests) == 1


async def test_a_400_on_a_later_page_keeps_the_pages_read_and_is_not_split() -> None:
    served = PagedWorks({1: numbered_works(1, 100), 2: 400})
    queries = [ProviderQuery(query=f"carbon tax survey {number}", filters=AC6_WINDOW) for number in range(2)]

    answers = await build_over(httpx.MockTransport(served.handle)).search_each(queries)

    assert [request.url.params["page"] for request in served.requests] == ["1", "2"]
    assert [(len(answer.results), answer.error) for answer in answers] == [
        (100, f"page 2 of 2 failed: {REFUSED}"),
        (100, f"page 2 of 2 failed: {REFUSED}"),
    ]


async def test_a_rate_limit_while_splitting_fails_the_whole_call() -> None:
    def status_for(texts: list[str]) -> int | None:
        return 400 if len(texts) == 4 else 429

    served = RefusingWorks(status_for)

    with pytest.raises(ProviderRateLimited):
        await build_over(httpx.MockTransport(served.handle)).search_each(numbered_queries(4))

    assert len(served.requests) == 2


async def test_a_split_is_logged_once_with_counts_only(caplog: pytest.LogCaptureFixture) -> None:
    served = RefusingWorks(refusing(0))
    with caplog.at_level(logging.INFO, logger="debate_core.integrations.discovery"):
        await build_over(httpx.MockTransport(served.handle)).search_each(numbered_queries(8, refused=(0,)))

    split = [record for record in caplog.records if "split" in record.getMessage()]
    assert [record.getMessage() for record in split] == [
        "openalex: a joined request of 8 queries was refused with HTTP 400 and split in halves: "
        "6 more requests, 7 queries answered, 1 refused"
    ]
    assert split[0].name == logger.name
    assert not any("carbon" in record.getMessage() for record in caplog.records)


def test_the_openalex_provider_answers_several_queries_at_once() -> None:
    assert isinstance(build_over(httpx.MockTransport(JoinedWorks().handle)), MultiQuerySearchProvider)


async def test_the_answer_keeps_to_max_results_when_openalex_sends_more() -> None:
    works = [
        {"id": f"https://openalex.org/W{number}", "display_name": f"Work {number}"} for number in range(1, 6)
    ]
    router = respx.MockRouter(assert_all_mocked=True)
    router.get(OPENALEX_WORKS_URL).return_value = httpx.Response(200, json={"results": works})
    query = ProviderQuery(query="x", filters=SearchFilters(max_results=2))

    answer = await build_over(httpx.MockTransport(router.async_handler)).search(query)

    assert [result.provider_record_id for result in answer.results] == ["W1", "W2"]


async def test_a_work_with_no_title_is_skipped_and_the_rest_are_answered() -> None:
    works = [
        {"id": "https://openalex.org/W1", "display_name": None},
        {"id": "https://openalex.org/W2", "display_name": "Kept"},
    ]
    router = respx.MockRouter(assert_all_mocked=True)
    router.get(OPENALEX_WORKS_URL).return_value = httpx.Response(200, json={"results": works})

    answer = await build_over(httpx.MockTransport(router.async_handler)).search(HEALTH_INSURANCE)

    assert [result.provider_record_id for result in answer.results] == ["W2"]


# --------------------------------------------------------------------------------------------
# Refusals and failures
# --------------------------------------------------------------------------------------------


async def test_a_429_with_retry_after_is_rate_limited_for_that_long() -> None:
    replayed = replay_with_respx(build_over)(recording("works_rate_limited"))
    with pytest.raises(ProviderRateLimited) as caught:
        await replayed.provider.search(HEALTH_INSURANCE)
    assert caught.value.retry_after_seconds == 30
    assert len(replayed.sent()) == 1


async def test_a_spent_daily_budget_is_a_rate_limit_with_no_stated_wait() -> None:
    replayed = replay_with_respx(build_over)(recording("works_daily_budget_spent"))
    with pytest.raises(ProviderRateLimited) as caught:
        await replayed.provider.search(HEALTH_INSURANCE)
    assert caught.value.retry_after_seconds is None
    assert len(replayed.sent()) == 1


async def test_a_retry_after_given_as_a_date_is_read_against_the_injected_clock() -> None:
    clock = FixedClock(datetime(2026, 10, 21, 7, 0, tzinfo=UTC))
    router = respx.MockRouter(assert_all_mocked=True)
    router.get(OPENALEX_WORKS_URL).return_value = httpx.Response(
        429, headers={"Retry-After": "Wed, 21 Oct 2026 07:01:30 GMT"}
    )
    with pytest.raises(ProviderRateLimited) as caught:
        await build_over(httpx.MockTransport(router.async_handler), clock=clock).search(HEALTH_INSURANCE)
    assert caught.value.retry_after_seconds == 90


async def test_a_503_with_retry_after_is_unavailable_not_rate_limited() -> None:
    replayed = replay_with_respx(build_over)(recording("works_unavailable"))
    with pytest.raises(ProviderUnavailable) as caught:
        await replayed.provider.search(HEALTH_INSURANCE)
    assert type(caught.value) is ProviderUnavailable
    assert str(caught.value) == "openalex: HTTP 503"
    assert len(replayed.sent()) == 1


async def test_a_malformed_body_is_unavailable() -> None:
    replayed = replay_with_respx(build_over)(recording("works_malformed"))
    with pytest.raises(ProviderUnavailable, match="openalex: unreadable response: JSONDecodeError"):
        await replayed.provider.search(HEALTH_INSURANCE)


@pytest.mark.parametrize(
    "document",
    [{"meta": {}}, {"results": None}, {"results": {"id": "W1"}}, {"results": ["W1"]}, ["results"], "results"],
    ids=["no results", "null results", "results not a list", "a work not an object", "a list", "a string"],
)
async def test_a_body_without_a_list_of_works_is_unavailable(document: object) -> None:
    router = respx.MockRouter(assert_all_mocked=True)
    router.get(OPENALEX_WORKS_URL).return_value = httpx.Response(200, json=document)
    with pytest.raises(ProviderUnavailable, match="openalex: unreadable response: no list of works"):
        await build_over(httpx.MockTransport(router.async_handler)).search(HEALTH_INSURANCE)


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        (httpx.ReadTimeout("timed out"), "openalex: timed out"),
        (httpx.ConnectError("refused"), "openalex: transport failure: ConnectError"),
        (httpx.RemoteProtocolError("dropped"), "openalex: transport failure: RemoteProtocolError"),
    ],
    ids=["timeout", "connection refused", "connection dropped"],
)
async def test_a_transport_failure_is_unavailable_and_keeps_its_cause(
    failure: httpx.HTTPError, message: str
) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise failure

    with pytest.raises(ProviderUnavailable) as caught:
        await build_over(httpx.MockTransport(fail)).search(HEALTH_INSURANCE)
    assert str(caught.value) == message
    assert caught.value.__cause__ is failure


# --------------------------------------------------------------------------------------------
# Wrapped by the registry: the breaker and the rate-limit hold consume the errors
# --------------------------------------------------------------------------------------------


def registry_over(
    name: str, clock: FixedClock, *, api_key: str | None = API_KEY, **overrides: Any
) -> tuple[ProviderRegistry, ReplayedProvider]:
    """The registry's openalex provider, over the named recording, and the registry itself."""
    registries: list[ProviderRegistry] = []

    def build(transport: httpx.AsyncBaseTransport) -> SearchProvider:
        factory = openalex_factory(HttpSettings(), version=VERSION, clock=clock, transport=transport)
        registry = ProviderRegistry.from_settings(
            provider_settings(api_key=api_key, **overrides),
            {SearchProviderName.OPENALEX: factory},
            clock=clock,
        )
        registries.append(registry)
        return registry.get("openalex")

    replayed = replay_with_respx(build)(recording(name))
    return registries[0], replayed


async def test_server_errors_open_the_breaker_and_the_open_breaker_sends_nothing() -> None:
    clock = FixedClock()
    registry, replayed = registry_over("works_unavailable", clock, breaker_failure_threshold=2)

    for _ in range(2):
        with pytest.raises(ProviderUnavailable):
            await replayed.provider.search(HEALTH_INSURANCE)
    with pytest.raises(ProviderCircuitOpen):
        await replayed.provider.search(HEALTH_INSURANCE)

    assert len(replayed.sent()) == 2
    (health,) = registry.health()
    assert health.state is BreakerState.OPEN
    assert health.error_count == 2 and health.skipped_count == 1
    assert health.last_error == "openalex: HTTP 503"


async def test_a_429_holds_openalex_for_its_retry_after_without_sending() -> None:
    clock = FixedClock()
    registry, replayed = registry_over("works_rate_limited", clock)

    with pytest.raises(ProviderRateLimited):
        await replayed.provider.search(HEALTH_INSURANCE)
    with pytest.raises(ProviderRateLimited):
        await replayed.provider.search(HEALTH_INSURANCE)

    assert len(replayed.sent()) == 1
    (health,) = registry.health()
    assert health.rate_limited_until == clock.now() + timedelta(seconds=30)
    clock.advance(timedelta(seconds=31))
    with pytest.raises(ProviderRateLimited):
        await replayed.provider.search(HEALTH_INSURANCE)
    assert len(replayed.sent()) == 2


async def test_a_spent_daily_budget_holds_openalex_for_the_first_backoff() -> None:
    clock = FixedClock()
    registry, replayed = registry_over("works_daily_budget_spent", clock, breaker_cooldown_seconds=600)

    with pytest.raises(ProviderRateLimited):
        await replayed.provider.search(HEALTH_INSURANCE)

    (health,) = registry.health()
    assert health.rate_limited_until is not None
    held_for = health.rate_limited_until - clock.now()
    assert timedelta(seconds=2) <= held_for < timedelta(seconds=3), (
        "the first backoff: 2 s, up to half longer"
    )


async def test_the_registry_answers_the_recorded_search_through_the_wrapper() -> None:
    clock = FixedClock()
    _, replayed = registry_over("works_search", clock)
    answer = await replayed.provider.search(recording("works_search").query)
    assert [result.provider_record_id for result in answer.results] == [
        "W4390000001",
        "W4390000002",
        "W4390000003",
    ]


# --------------------------------------------------------------------------------------------
# The key and the contact email never surface
# --------------------------------------------------------------------------------------------


@pytest.mark.usefixtures("bare_protected_loggers")
async def test_no_secret_reaches_a_log_line_an_error_a_repr_or_a_health_snapshot(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    clock = FixedClock()
    surfaces: list[str] = []
    for name in ("works_search", "works_rate_limited", "works_unavailable", "works_malformed"):
        registry, replayed = registry_over(name, clock)
        surfaces += [repr(registry), repr(replayed.provider), repr(registry.providers[0])]
        try:
            await replayed.provider.search(HEALTH_INSURANCE)
        except (ProviderRateLimited, ProviderUnavailable) as error:
            surfaces += [str(error), repr(error), str(error.__cause__), repr(error.__cause__)]
        surfaces += [snapshot.model_dump_json() for snapshot in registry.health()]
    logger.warning("adapter state: key=%s contact=%s", API_KEY, CONTACT_EMAIL)
    surfaces += [record.getMessage() for record in caplog.records]

    assert any("HTTP Request: GET https://api.openalex.org/works" in text for text in surfaces)
    assert any("adapter state: key=***" in text for text in surfaces)
    leaked = [text for text in surfaces if API_KEY in text or CONTACT_EMAIL in text]
    assert not leaked


@pytest.mark.usefixtures("bare_protected_loggers")
@pytest.mark.parametrize("logger_name", PROTECTED_LOGGERS)
def test_the_adapter_alone_protects_the_logs_from_its_key(
    logger_name: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Unwrapped, as the kit runs it: the constructor registers the key, so no log line carries it."""
    caplog.set_level(logging.DEBUG)
    key = "openalex-unwrapped-key-7d41"
    build_over(httpx.MockTransport(lambda request: httpx.Response(200)), api_key=key)

    logging.getLogger(logger_name).warning("Authorization: Bearer %s", key)

    assert [record.getMessage() for record in caplog.records] == ["Authorization: Bearer ***"]


def test_the_repr_says_whether_a_key_is_configured_and_nothing_more() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200))
    assert repr(build_over(transport)) == "OpenAlexProvider(api_key=configured)"
    assert repr(build_over(transport, api_key=None)) == "OpenAlexProvider(api_key=none)"


class SendsTheKeyInTheUrl(OpenAlexProvider):
    """Uses OpenAlex's documented `api_key=` parameter and never protects the logs: what the header avoids."""

    def __init__(self, client: httpx.AsyncClient, **_: Any) -> None:
        self._client = client
        self._api_key = SecretStr(API_KEY)
        self._clock = FixedClock()

    async def search(self, query: ProviderQuery) -> ProviderResponse:
        response = await self._client.get(
            OPENALEX_WORKS_URL, params={**works_parameters(query), "api_key": API_KEY}
        )
        works, _ = self._read(response)
        return ProviderResponse(
            provider=self.name, results=tuple(works)[: query.filters.max_results], elapsed_ms=1.0
        )


async def test_the_kits_secrets_check_catches_a_key_sent_in_the_url() -> None:
    search = recording("works_search")
    exchange = search.exchanges[0]
    keyed = replace(search, exchanges=(replace(exchange, url=f"{exchange.url}&api_key={API_KEY}"),))

    def build(transport: httpx.AsyncBaseTransport) -> SearchProvider:
        return SendsTheKeyInTheUrl(httpx.AsyncClient(transport=transport))

    with pytest.raises(AssertionError, match="a configured secret surfaced in") as caught:
        await assert_no_secret_surfaces(replay_with_respx(build), keyed, (API_KEY,))
    assert "log record on httpx: HTTP Request: GET" in str(caught.value)


# --------------------------------------------------------------------------------------------
# The shared contract kit
# --------------------------------------------------------------------------------------------


class TestOpenAlexProviderWithAKey(SearchProviderContract):
    """OpenAlex with a key and a contact email configured, on the recorded health insurance search."""

    @pytest.fixture
    def recording(self) -> Recording:
        return recording("works_search")

    @pytest.fixture
    def replay(self) -> ReplayFactory:
        return replay_with_respx(build_over)

    @pytest.fixture
    def secrets(self) -> tuple[str, ...]:
        return (API_KEY, CONTACT_EMAIL)

    @pytest.fixture
    def max_attempts(self) -> int:
        """The adapter never retries: one request per search."""
        return 1


class TestOpenAlexProviderWithoutAKey(TestOpenAlexProviderWithAKey):
    """Keyless OpenAlex: the same recording answers, since the key travels in a header."""

    @pytest.fixture
    def replay(self) -> ReplayFactory:
        return replay_with_respx(lambda transport: build_over(transport, api_key=None))

    @pytest.fixture
    def secrets(self) -> tuple[str, ...]:
        return (CONTACT_EMAIL,)


class TestOpenAlexProviderOnAnEmptyResult(TestOpenAlexProviderWithAKey):
    """A search OpenAlex has nothing for."""

    @pytest.fixture
    def recording(self) -> Recording:
        return recording("works_empty")
