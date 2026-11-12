"""The government discovery providers: Federal Register and GovInfo (v1-e07-t07).

For each adapter: the request it sends, how a result maps to a candidate, how failures are reported,
the wrapper's handling of them, and the shared contract kit. Then the api.data.gov key and the topic
enablement that decides which government providers a search asks.

Every answer here is hand-written from the provider's documented response and lives in
`packages/debate_core/tests/fixtures/discovery/<provider>/`; every expected mapping is written by
hand from those bodies (working agreement 6). Nothing here reaches the network.

Test names carry `federal_register`, `govinfo` or `key`, so each plan node's `-k` selects its own.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterator
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
from debate_core.application.federated_search import (
    FanOutStage,
    FederatedSearchService,
    SearchTopics,
    selected_providers,
)
from debate_core.application.federated_search_types import ExpansionRequest, SearchRequest, SearchState
from debate_core.application.ports.providers import SearchProvider
from debate_core.application.query_expansion import UnknownExpansionChoice
from debate_core.application.settings import HttpSettings, ProviderSettings, SearchProviderName
from debate_core.domain.base import new_id
from debate_core.domain.discovery import (
    BreakerState,
    CandidateResult,
    DatePrecision,
    ProviderOutcome,
    ProviderQuery,
    ProviderResponse,
)
from debate_core.domain.enums import SourceType
from debate_core.domain.search import SearchFilters
from debate_core.integrations.discovery.data_gov import require_api_data_gov_key
from debate_core.integrations.discovery.federal_register import (
    FEDERAL_REGISTER_DOCUMENTS_URL,
    FederalRegisterProvider,
    candidate_from_document,
    documents_parameters,
    federal_register_factory,
)
from debate_core.integrations.discovery.feed_config import (
    FeedConfig,
    FeedConfigError,
    load_feed_config,
    load_feed_directory,
    search_topic_ids,
    topic_providers,
)
from debate_core.integrations.discovery.govinfo import (
    BillNumber,
    GovInfoProvider,
    bill_number,
    candidate_from_result,
    govinfo_factory,
    search_body,
)
from debate_core.integrations.discovery.redaction import PROTECTED_LOGGERS, logger
from debate_core.integrations.discovery.registry import ProviderNotConfigured, ProviderRegistry
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

pytestmark = pytest.mark.anyio

DISCOVERY_FIXTURES: Final = Path(__file__).resolve().parents[2] / "fixtures" / "discovery"
FEDERAL_REGISTER_FIXTURES: Final = DISCOVERY_FIXTURES / "federal_register"
API_DATA_GOV_KEY: Final = "datagov-k7Qm2x"
"""A made-up api.data.gov key, short so that no error message shortens it out of sight."""
CONTACT_EMAIL: Final = "gov-coach@example.org"
VERSION: Final = "0.0.0-test"


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


def provider_settings(
    *enabled: SearchProviderName, api_data_gov_key: str | None = API_DATA_GOV_KEY, **overrides: Any
) -> ProviderSettings:
    """The named providers enabled, with the api.data.gov key (unless `None`) and a contact email."""
    return ProviderSettings(
        enabled=enabled,
        api_data_gov_key=SecretStr(api_data_gov_key) if api_data_gov_key is not None else None,
        contact_email=SecretStr(CONTACT_EMAIL),
        **overrides,
    )


def replay_with_respx(
    build: Callable[[httpx.AsyncBaseTransport], SearchProvider], seen: list[httpx.Request] | None = None
) -> ReplayFactory:
    """Serve a recording's exchanges through respx, and nothing else.

    A copy of the FakeProvider binding's (`test_fake_provider.py`), as OpenAlex's is: the adapter is
    built from a transport, so the factory's own client is the one under test, and every request is
    kept in `seen` when given. Transport failures are raised here rather than as respx side effects,
    because respx re-raises a side effect `from` an error that quotes the matched route.
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


def answering(response: httpx.Response, seen: list[httpx.Request] | None = None) -> httpx.MockTransport:
    """A transport that answers every request with `response`, keeping each request in `seen`."""

    def handle(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return response

    return httpx.MockTransport(handle)


# ============================================================================================
# Federal Register
# ============================================================================================


def federal_register_recording(name: str) -> Recording:
    return load_recording(FEDERAL_REGISTER_FIXTURES / f"{name}.json")


def federal_register_over(
    transport: httpx.AsyncBaseTransport, *, clock: FixedClock | None = None
) -> FederalRegisterProvider:
    """The adapter exactly as the registry builds it, over `transport`, with every credential set."""
    factory = federal_register_factory(
        HttpSettings(), version=VERSION, clock=clock or FixedClock(), transport=transport
    )
    return factory(provider_settings(SearchProviderName.FEDERAL_REGISTER))


def a_document(**fields: Any) -> dict[str, Any]:
    """A minimal mappable Federal Register document, with `fields` laid over it."""
    return {
        "document_number": "2025-90199",
        "title": "A title",
        "html_url": "https://www.federalregister.gov/documents/2025/01/02/2025-90199/a-title",
        **fields,
    }


MARKETPLACE: Final = ProviderQuery(
    query="health insurance marketplace",
    filters=SearchFilters(
        since=datetime(2025, 1, 1, tzinfo=UTC), until=datetime(2026, 6, 30, tzinfo=UTC), max_results=5
    ),
)
MARKETPLACE_URL: Final = (
    "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bterm%5D=health+insurance+marketplace"
    "&conditions%5Bpublication_date%5D%5Bgte%5D=2025-01-01&conditions%5Bpublication_date%5D%5Blte%5D=2026-06-30"
    "&conditions%5Btype%5D%5B%5D=RULE&conditions%5Btype%5D%5B%5D=PRORULE&conditions%5Btype%5D%5B%5D=NOTICE"
    "&fields%5B%5D=document_number&fields%5B%5D=title&fields%5B%5D=publication_date&fields%5B%5D=agency_names"
    "&fields%5B%5D=abstract&fields%5B%5D=html_url&fields%5B%5D=pdf_url&order=relevance&per_page=5"
)
"""The marketplace search's URL, written out by hand from the API spec the PM read on 2026-11-02."""

EMPTY_RESULTS: Final = httpx.Response(200, json={"count": 0, "results": []})


# --------------------------------------------------------------------------------------------
# Federal Register: document to CandidateResult
# --------------------------------------------------------------------------------------------


def test_federal_register_recorded_documents_map_to_the_hand_written_candidates() -> None:
    documents = json.loads((FEDERAL_REGISTER_FIXTURES / "documents_search.body.json").read_text())["results"]
    expected = json.loads((FEDERAL_REGISTER_FIXTURES / "documents_search.expected.json").read_text())
    mapped = [candidate_from_document(document) for document in documents]
    assert [candidate for candidate in mapped if candidate is not None] == [
        CandidateResult.model_validate(item) for item in expected
    ]


@pytest.mark.parametrize(
    "document",
    [
        a_document(title=None),
        a_document(title="   "),
        a_document(document_number=None),
        a_document(document_number=""),
        a_document(document_number=2025),
        a_document(html_url=None, pdf_url=None),
        a_document(html_url="ftp://example.org/x", pdf_url="not a url"),
    ],
    ids=[
        "no-title",
        "blank-title",
        "no-number",
        "blank-number",
        "number-not-text",
        "no-link",
        "no-http-link",
    ],
)
def test_federal_register_document_without_a_title_a_number_or_a_link_is_not_a_candidate(
    document: dict[str, Any],
) -> None:
    assert candidate_from_document(document) is None


def test_federal_register_document_number_is_the_record_id_as_the_register_prints_it() -> None:
    candidate = candidate_from_document(a_document(document_number=" E9-01234 "))
    assert candidate is not None
    assert candidate.provider_record_id == "E9-01234"
    assert candidate.identifiers.model_dump(exclude_none=True) == {}


def test_federal_register_url_is_the_html_page_then_the_pdf() -> None:
    html = "https://www.federalregister.gov/documents/2025/01/02/2025-90199/a-title"
    pdf = "https://www.govinfo.gov/content/pkg/FR-2025-01-02/pdf/2025-90199.pdf"
    both = candidate_from_document(a_document(html_url=html, pdf_url=pdf))
    pdf_only = candidate_from_document(a_document(html_url=None, pdf_url=pdf))
    assert both is not None and (both.url, both.open_access_url) == (html, pdf)
    assert pdf_only is not None and (pdf_only.url, pdf_only.open_access_url) == (pdf, pdf)


@pytest.mark.parametrize(
    ("agency_names", "expected"),
    [
        (["Treasury Department"], "Treasury Department"),
        (
            ["Health and Human Services Department", " Centers for Medicare & Medicaid Services "],
            "Health and Human Services Department; Centers for Medicare & Medicaid Services",
        ),
        (
            ["Treasury Department", None, 7, "  ", "Internal Revenue Service"],
            "Treasury Department; Internal Revenue Service",
        ),
        (["Treasury Department", "Treasury Department"], "Treasury Department"),
        ([], None),
        (None, None),
        ("Treasury Department", None),
    ],
    ids=["one", "two-in-order", "non-text-skipped", "repeat-once", "empty", "missing", "not-a-list"],
)
def test_federal_register_issuing_agencies_are_the_publication(
    agency_names: object, expected: str | None
) -> None:
    candidate = candidate_from_document(a_document(agency_names=agency_names))
    assert candidate is not None
    assert candidate.publication == expected
    assert candidate.authors == ()


@pytest.mark.parametrize(
    ("publication_date", "expected"),
    [
        ("2025-03-14", datetime(2025, 3, 14, tzinfo=UTC)),
        ("2026-02-30", None),
        ("2025", None),
        ("14 March 2025", None),
        (None, None),
        (20250314, None),
    ],
    ids=["day", "impossible-day", "year-only", "prose", "missing", "number"],
)
def test_federal_register_publication_date_is_a_day_at_midnight_utc_or_none(
    publication_date: object, expected: datetime | None
) -> None:
    candidate = candidate_from_document(a_document(publication_date=publication_date))
    assert candidate is not None
    assert candidate.published_at == expected
    assert candidate.date_precision == (DatePrecision.DAY if expected is not None else None)


def test_federal_register_every_document_is_a_free_to_read_government_source() -> None:
    candidate = candidate_from_document(a_document())
    assert candidate is not None
    assert candidate.source_type is SourceType.GOVERNMENT
    assert candidate.open_access is True
    assert candidate.provider == "federal_register"


@pytest.mark.parametrize(
    ("abstract", "expected"), [(" An abstract. ", "An abstract."), ("  ", None), (None, None), (3, None)]
)
def test_federal_register_abstract_is_the_snippet(abstract: object, expected: str | None) -> None:
    candidate = candidate_from_document(a_document(abstract=abstract))
    assert candidate is not None
    assert candidate.snippet == expected


# --------------------------------------------------------------------------------------------
# Federal Register: the request
# --------------------------------------------------------------------------------------------


async def test_federal_register_request_carries_the_term_window_types_fields_order_and_page_size() -> None:
    seen: list[httpx.Request] = []
    await federal_register_over(answering(EMPTY_RESULTS, seen)).search(MARKETPLACE)

    (request,) = seen
    assert request.method == "GET"
    assert str(request.url) == MARKETPLACE_URL


def test_federal_register_request_parameters_without_a_window_name_no_date() -> None:
    parameters = documents_parameters(
        ProviderQuery(query="data center moratorium", filters=SearchFilters(max_results=7))
    )
    assert parameters == [
        ("conditions[term]", "data center moratorium"),
        ("conditions[type][]", "RULE"),
        ("conditions[type][]", "PRORULE"),
        ("conditions[type][]", "NOTICE"),
        ("fields[]", "document_number"),
        ("fields[]", "title"),
        ("fields[]", "publication_date"),
        ("fields[]", "agency_names"),
        ("fields[]", "abstract"),
        ("fields[]", "html_url"),
        ("fields[]", "pdf_url"),
        ("order", "relevance"),
        ("per_page", "7"),
    ]


def test_federal_register_request_date_window_is_the_utc_date() -> None:
    eastern = timezone(timedelta(hours=-5))
    query = ProviderQuery(
        query="q",
        filters=SearchFilters(
            since=datetime(2025, 1, 1, 22, tzinfo=eastern), until=datetime(2025, 2, 1, 1, tzinfo=eastern)
        ),
    )
    parameters = dict(documents_parameters(query))
    assert parameters["conditions[publication_date][gte]"] == "2025-01-02"
    assert parameters["conditions[publication_date][lte]"] == "2025-02-01"


async def test_federal_register_request_sends_no_key_no_contact_email_and_no_cookie() -> None:
    seen: list[httpx.Request] = []
    await federal_register_over(answering(EMPTY_RESULTS, seen)).search(MARKETPLACE)

    (request,) = seen
    sent = str(request.url) + "".join(f"{name}: {value}\n" for name, value in request.headers.items())
    assert API_DATA_GOV_KEY not in sent
    assert CONTACT_EMAIL not in sent
    assert "api_key" not in sent.lower() and "x-api-key" not in sent.lower()
    assert "cookie" not in request.headers
    assert request.headers["user-agent"] == HttpSettings().user_agent(VERSION)


async def test_federal_register_answer_keeps_to_max_results_when_the_register_sends_more() -> None:
    documents = [a_document(document_number=f"2025-9020{index}") for index in range(4)]
    provider = federal_register_over(answering(httpx.Response(200, json={"count": 4, "results": documents})))

    answer = await provider.search(ProviderQuery(query="q", filters=SearchFilters(max_results=2)))

    assert [result.provider_record_id for result in answer.results] == ["2025-90200", "2025-90201"]


async def test_federal_register_answer_with_no_documents_and_no_results_list_is_empty() -> None:
    """A zero count may leave `results` out; that is an empty answer, not an unreadable one."""
    provider = federal_register_over(answering(httpx.Response(200, json={"count": 0, "total_pages": 0})))
    answer = await provider.search(MARKETPLACE)
    assert answer == ProviderResponse(provider="federal_register", results=(), elapsed_ms=answer.elapsed_ms)


async def test_federal_register_document_with_no_title_is_skipped_and_the_rest_are_answered() -> None:
    documents = [a_document(title=None), a_document(document_number="2025-90300")]
    provider = federal_register_over(answering(httpx.Response(200, json={"count": 2, "results": documents})))
    answer = await provider.search(MARKETPLACE)
    assert [result.provider_record_id for result in answer.results] == ["2025-90300"]


# --------------------------------------------------------------------------------------------
# Federal Register: failures
# --------------------------------------------------------------------------------------------


async def test_federal_register_429_is_rate_limited_for_its_retry_after() -> None:
    replayed = replay_with_respx(federal_register_over)(federal_register_recording("documents_rate_limited"))
    with pytest.raises(ProviderRateLimited) as raised:
        await replayed.provider.search(MARKETPLACE)
    assert raised.value.retry_after_seconds == 30


async def test_federal_register_redirect_is_unavailable_and_names_only_the_host() -> None:
    replayed = replay_with_respx(federal_register_over)(federal_register_recording("documents_redirected"))
    with pytest.raises(ProviderUnavailable) as raised:
        await replayed.provider.search(MARKETPLACE)
    assert str(raised.value) == "federal_register: HTTP 302: redirected to unblock.federalregister.gov"
    assert len(replayed.sent()) == 1


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({}, "federal_register: HTTP 301: redirected"),
        ({"location": "/api/v1/documents.json?page=2"}, "federal_register: HTTP 301: redirected"),
        (
            {"location": "https://user:secret@mirror.example.org:8443/x?api_key=1"},
            "federal_register: HTTP 301: redirected to mirror.example.org",
        ),
    ],
    ids=["no-location", "relative", "with-credentials"],
)
async def test_federal_register_redirect_names_a_host_only_when_there_is_one(
    headers: dict[str, str], expected: str
) -> None:
    provider = federal_register_over(answering(httpx.Response(301, headers=headers)))
    with pytest.raises(ProviderUnavailable) as raised:
        await provider.search(MARKETPLACE)
    assert str(raised.value) == expected


async def test_federal_register_304_is_unavailable_too() -> None:
    """The adapter never sends a conditional request, so any 3xx is a redirect it will not follow."""
    provider = federal_register_over(answering(httpx.Response(304)))
    with pytest.raises(ProviderUnavailable, match="HTTP 304"):
        await provider.search(MARKETPLACE)


async def test_federal_register_html_page_instead_of_json_is_unavailable() -> None:
    replayed = replay_with_respx(federal_register_over)(federal_register_recording("documents_malformed"))
    with pytest.raises(ProviderUnavailable, match="unreadable response"):
        await replayed.provider.search(MARKETPLACE)


@pytest.mark.parametrize(
    "document",
    [
        [],
        "text",
        {"count": 3},
        {"count": 1, "results": "x"},
        {"count": 1, "results": [1, 2]},
        {"results": None},
    ],
    ids=[
        "list",
        "string",
        "count-without-results",
        "results-not-list",
        "results-not-objects",
        "results-null",
    ],
)
async def test_federal_register_body_without_a_list_of_documents_is_unavailable(document: object) -> None:
    provider = federal_register_over(answering(httpx.Response(200, json=document)))
    with pytest.raises(ProviderUnavailable, match="unreadable response"):
        await provider.search(MARKETPLACE)


@pytest.mark.parametrize(
    "error", [httpx.ReadTimeout("timed out"), httpx.ConnectError("refused")], ids=["timeout", "connection"]
)
async def test_federal_register_transport_failure_is_unavailable_and_keeps_its_cause(
    error: httpx.HTTPError,
) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise error

    provider = federal_register_over(httpx.MockTransport(fail))
    with pytest.raises(ProviderUnavailable) as raised:
        await provider.search(MARKETPLACE)
    assert raised.value.__cause__ is error


# --------------------------------------------------------------------------------------------
# Federal Register: wrapped by the registry, keyless
# --------------------------------------------------------------------------------------------


def federal_register_registry_over(
    name: str, clock: FixedClock, **settings: Any
) -> tuple[ProviderRegistry, ReplayedProvider]:
    """The registry's federal_register provider, over the named recording, and the registry itself."""
    registries: list[ProviderRegistry] = []

    def build(transport: httpx.AsyncBaseTransport) -> SearchProvider:
        factory = federal_register_factory(HttpSettings(), version=VERSION, clock=clock, transport=transport)
        registry = ProviderRegistry.from_settings(
            provider_settings(SearchProviderName.FEDERAL_REGISTER, **settings),
            {SearchProviderName.FEDERAL_REGISTER: factory},
            clock=clock,
        )
        registries.append(registry)
        return registry.get("federal_register")

    replayed = replay_with_respx(build)(federal_register_recording(name))
    return registries[0], replayed


async def test_federal_register_is_built_and_answers_with_no_key_configured() -> None:
    _, replayed = federal_register_registry_over("documents_search", FixedClock(), api_data_gov_key=None)
    answer = await replayed.provider.search(MARKETPLACE)
    assert [result.provider_record_id for result in answer.results] == [
        "2025-90101",
        "2025-90102",
        "2026-90104",
    ]


async def test_federal_register_redirects_open_the_breaker_and_the_open_breaker_sends_nothing() -> None:
    registry, replayed = federal_register_registry_over(
        "documents_redirected", FixedClock(), breaker_failure_threshold=2
    )
    for _ in range(2):
        with pytest.raises(ProviderUnavailable):
            await replayed.provider.search(MARKETPLACE)
    with pytest.raises(ProviderCircuitOpen):
        await replayed.provider.search(MARKETPLACE)

    assert len(replayed.sent()) == 2
    (health,) = registry.health()
    assert health.state is BreakerState.OPEN
    assert health.last_error == "federal_register: HTTP 302: redirected to unblock.federalregister.gov"


@pytest.mark.usefixtures("bare_protected_loggers")
async def test_federal_register_no_configured_secret_reaches_a_log_line_an_error_or_a_snapshot(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    clock = FixedClock()
    surfaces: list[str] = []
    for name in (
        "documents_search",
        "documents_rate_limited",
        "documents_unavailable",
        "documents_redirected",
    ):
        registry, replayed = federal_register_registry_over(name, clock)
        surfaces += [repr(registry), repr(replayed.provider), repr(registry.providers[0])]
        try:
            await replayed.provider.search(MARKETPLACE)
        except (ProviderRateLimited, ProviderUnavailable) as error:
            surfaces += [str(error), repr(error), str(error.__cause__), repr(error.__cause__)]
        surfaces += [snapshot.model_dump_json() for snapshot in registry.health()]
    surfaces += [record.getMessage() for record in caplog.records]

    assert any(
        "HTTP Request: GET https://www.federalregister.gov/api/v1/documents.json" in text for text in surfaces
    )
    assert not [text for text in surfaces if API_DATA_GOV_KEY in text or CONTACT_EMAIL in text]


def test_federal_register_repr_names_the_adapter_and_nothing_else() -> None:
    assert repr(federal_register_over(answering(EMPTY_RESULTS))) == "FederalRegisterProvider()"


def test_federal_register_documents_url_is_the_api_v1_documents_endpoint() -> None:
    assert FEDERAL_REGISTER_DOCUMENTS_URL == "https://www.federalregister.gov/api/v1/documents.json"
    assert logger.name == "debate_core.integrations.discovery"


# --------------------------------------------------------------------------------------------
# Federal Register: the shared contract kit
# --------------------------------------------------------------------------------------------


class TestFederalRegisterProvider(SearchProviderContract):
    """The Federal Register on the recorded marketplace search, with every credential configured."""

    @pytest.fixture
    def recording(self) -> Recording:
        return federal_register_recording("documents_search")

    @pytest.fixture
    def replay(self) -> ReplayFactory:
        return replay_with_respx(federal_register_over)

    @pytest.fixture
    def secrets(self) -> tuple[str, ...]:
        """Neither is the Register's, and neither may be sent to it or surface anywhere."""
        return (API_DATA_GOV_KEY, CONTACT_EMAIL)

    @pytest.fixture
    def max_attempts(self) -> int:
        """The adapter never retries: one request per search."""
        return 1


class TestFederalRegisterProviderOnAnEmptyResult(TestFederalRegisterProvider):
    """A search the Register has nothing for."""

    @pytest.fixture
    def recording(self) -> Recording:
        return federal_register_recording("documents_empty")


# ============================================================================================
# The api.data.gov key
# ============================================================================================

MISSING_KEY: Final = "govinfo: no api.data.gov key (DEBATE_PROVIDERS__API_DATA_GOV_KEY)"


def keyed_stand_in_factory(built: list[str]) -> Callable[[ProviderSettings], SearchProvider]:
    """A stand-in for GovInfo's factory: it needs the key exactly as GovInfo's does, and answers nothing."""

    def build(settings: ProviderSettings) -> SearchProvider:
        built.append(require_api_data_gov_key(settings, "govinfo"))
        return FakeSearchProvider("govinfo")

    return build


@pytest.mark.parametrize("key", [None, "", "   "], ids=["unset", "empty", "spaces"])
def test_key_missing_leaves_govinfo_unbuilt_and_recorded_not_configured(key: str | None) -> None:
    built: list[str] = []
    registry = ProviderRegistry.from_settings(
        provider_settings(SearchProviderName.GOVINFO, api_data_gov_key=key),
        {SearchProviderName.GOVINFO: keyed_stand_in_factory(built)},
        clock=FixedClock(),
    )

    assert built == []
    assert registry.names == ()
    assert registry.health() == ()
    assert dict(registry.not_configured) == {"govinfo": MISSING_KEY}


def test_key_present_builds_govinfo_with_that_key_and_no_other() -> None:
    built: list[str] = []
    registry = ProviderRegistry.from_settings(
        provider_settings(SearchProviderName.GOVINFO),
        {SearchProviderName.GOVINFO: keyed_stand_in_factory(built)},
        clock=FixedClock(),
    )

    assert built == [API_DATA_GOV_KEY]
    assert registry.names == ("govinfo",)
    assert dict(registry.not_configured) == {}


def test_key_is_never_the_shared_demo_key() -> None:
    with pytest.raises(ProviderNotConfigured) as raised:
        require_api_data_gov_key(provider_settings(api_data_gov_key=None), "govinfo")
    assert raised.value.reason == MISSING_KEY
    assert "DEMO_KEY" not in str(raised.value)


async def test_key_missing_is_reported_not_configured_for_every_query_not_as_an_error() -> None:
    registry = ProviderRegistry.from_settings(
        provider_settings(
            SearchProviderName.FEDERAL_REGISTER, SearchProviderName.GOVINFO, api_data_gov_key=None
        ),
        {
            SearchProviderName.FEDERAL_REGISTER: lambda _: FakeSearchProvider("federal_register"),
            SearchProviderName.GOVINFO: keyed_stand_in_factory([]),
        },
        clock=FixedClock(),
    )
    stage = FanOutStage(registry, clock=FixedClock(), deadline_seconds=5, topics=NHI_TOPICS)
    request = SearchRequest(query="single payer", topic_id=NHI)

    state = await stage.run(
        SearchState.start(new_id(), request).evolve(
            queries=(ProviderQuery(query="a"), ProviderQuery(query="b"))
        )
    )

    outcomes = [
        (status.provider, status.query.query, status.outcome, status.error)
        for status in state.provider_statuses
    ]
    with_cure = f"{MISSING_KEY}; get a free key at api.data.gov/signup to ask GovInfo"
    assert outcomes == [
        ("federal_register", "a", ProviderOutcome.OK, None),
        ("govinfo", "a", ProviderOutcome.NOT_CONFIGURED, with_cure),
        ("federal_register", "b", ProviderOutcome.OK, None),
        ("govinfo", "b", ProviderOutcome.NOT_CONFIGURED, with_cure),
    ]
    assert registry.health()[0].provider == "federal_register" and len(registry.health()) == 1


@pytest.mark.usefixtures("bare_protected_loggers")
def test_key_is_masked_in_every_protected_log_line_once_govinfo_is_built(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    key = "datagov-unwrapped-Z3"
    require_api_data_gov_key(provider_settings(api_data_gov_key=key), "govinfo")

    for name in PROTECTED_LOGGERS:
        logging.getLogger(name).warning("X-Api-Key: %s", key)

    assert [record.getMessage() for record in caplog.records] == ["X-Api-Key: ***"] * len(PROTECTED_LOGGERS)


# ============================================================================================
# Topic enablement: a government provider runs only for a search whose topic lists it
# ============================================================================================

NHI: Final = "policy-2026-27-nhi"
NHI_TOPICS: Final = SearchTopics(
    known=(NHI, "pf-test-topic"),
    providers={NHI: frozenset({"federal_register", "govinfo"}), "pf-test-topic": frozenset({"govinfo"})},
)
COMMITTED_FEEDS: Final = Path(__file__).resolve().parents[5] / "config" / "feeds"


def topic_registry(*enabled: SearchProviderName) -> ProviderRegistry:
    """Every named provider enabled and built as a stand-in that answers one result."""
    return ProviderRegistry.from_settings(
        provider_settings(*enabled),
        {name: stand_in(name.value) for name in enabled},
        clock=FixedClock(),
    )


def stand_in(name: str) -> Callable[[ProviderSettings], SearchProvider]:
    result = CandidateResult(
        provider=name, title=f"From {name}", url=f"https://{name.replace('_', '-')}.example.org/1"
    )
    return lambda _: FakeSearchProvider(name, default_results=(result,))


async def fan_out(
    registry: ProviderRegistry, request: SearchRequest, topics: SearchTopics = NHI_TOPICS
) -> list[tuple[str, ProviderOutcome, str | None]]:
    stage = FanOutStage(registry, clock=FixedClock(), deadline_seconds=5, topics=topics)
    state = await stage.run(SearchState.start(new_id(), request))
    return [(status.provider, status.outcome, status.error) for status in state.provider_statuses]


ALL_FOUR: Final = (
    SearchProviderName.OPENALEX,
    SearchProviderName.FEDERAL_REGISTER,
    SearchProviderName.RSS,
    SearchProviderName.GOVINFO,
)


async def test_topic_that_lists_the_government_providers_asks_them_beside_the_others() -> None:
    outcomes = await fan_out(topic_registry(*ALL_FOUR), SearchRequest(query="q", topic_id=NHI))
    assert outcomes == [
        ("openalex", ProviderOutcome.OK, None),
        ("federal_register", ProviderOutcome.OK, None),
        ("rss", ProviderOutcome.OK, None),
        ("govinfo", ProviderOutcome.OK, None),
    ]


async def test_topic_absent_leaves_the_government_providers_neither_asked_nor_reported() -> None:
    outcomes = await fan_out(topic_registry(*ALL_FOUR), SearchRequest(query="q"))
    assert outcomes == [("openalex", ProviderOutcome.OK, None), ("rss", ProviderOutcome.OK, None)]


async def test_topic_that_lists_only_govinfo_does_not_ask_the_federal_register() -> None:
    outcomes = await fan_out(topic_registry(*ALL_FOUR), SearchRequest(query="q", topic_id="pf-test-topic"))
    assert [name for name, _, _ in outcomes] == ["openalex", "rss", "govinfo"]


async def test_topic_lists_a_provider_settings_do_not_enable_so_it_is_not_asked() -> None:
    """Enabled AND on the topic: the topic alone never switches a provider on."""
    registry = topic_registry(SearchProviderName.OPENALEX, SearchProviderName.GOVINFO)
    outcomes = await fan_out(registry, SearchRequest(query="q", topic_id=NHI))
    assert [name for name, _, _ in outcomes] == ["openalex", "govinfo"]


async def test_topic_known_with_no_government_providers_asks_none_of_them() -> None:
    topics = SearchTopics(known=(NHI,), providers={})
    outcomes = await fan_out(topic_registry(*ALL_FOUR), SearchRequest(query="q", topic_id=NHI), topics)
    assert [name for name, _, _ in outcomes] == ["openalex", "rss"]


@pytest.mark.parametrize(
    ("topic", "reason"),
    [
        (
            None,
            "federal_register: asked only for a search on a topic that lists it, "
            "and this search names no topic",
        ),
        (
            "pf-test-topic",
            "federal_register: asked only for a search on a topic that lists it, and pf-test-topic does not",
        ),
    ],
    ids=["no-topic", "topic-without-it"],
)
async def test_topic_gate_reports_a_government_provider_named_by_providers_as_not_configured(
    topic: str | None, reason: str
) -> None:
    request = SearchRequest(query="q", topic_id=topic, providers=("federal_register", "openalex"))
    outcomes = await fan_out(topic_registry(*ALL_FOUR), request)
    assert outcomes == [
        ("federal_register", ProviderOutcome.NOT_CONFIGURED, reason),
        ("openalex", ProviderOutcome.OK, None),
    ]


def test_topic_selection_is_the_providers_the_stored_search_records() -> None:
    registry = topic_registry(*ALL_FOUR)
    assert selected_providers(SearchRequest(query="q"), registry.names, topics=NHI_TOPICS) == (
        "openalex",
        "rss",
    )
    assert selected_providers(SearchRequest(query="q", topic_id=NHI), registry.names, topics=NHI_TOPICS) == (
        "openalex",
        "federal_register",
        "rss",
        "govinfo",
    )
    assert selected_providers(
        SearchRequest(query="q", topic_id=NHI), ("openalex",), not_configured=("govinfo",), topics=NHI_TOPICS
    ) == ("openalex", "govinfo")


async def test_topic_unknown_is_refused_with_the_valid_ones_before_any_provider_is_asked() -> None:
    fakes = {name: FakeSearchProvider(name.value) for name in ALL_FOUR}
    registry = ProviderRegistry.from_settings(
        provider_settings(*ALL_FOUR),
        {name: (lambda _, f=fake: f) for name, fake in fakes.items()},
        clock=FixedClock(),
    )
    service = FederatedSearchService(
        registry,
        InMemorySearchRepository(),
        clock=FixedClock(),
        ids=SequentialIdGenerator(),
        topics=NHI_TOPICS,
    )
    with pytest.raises(UnknownExpansionChoice) as raised:
        await service.search(SearchRequest(query="q", topic_id="policy-2025-26-nhi"))
    assert (
        str(raised.value)
        == "unknown topic 'policy-2025-26-nhi'; the topics are: policy-2026-27-nhi, pf-test-topic"
    )
    assert [fake.queries for fake in fakes.values()] == [[], [], [], []]


def test_topic_id_is_left_out_of_a_requests_json_when_none() -> None:
    assert "topic_id" not in SearchRequest(query="q").model_dump(mode="json")
    assert SearchRequest(query="q", topic_id=NHI).model_dump(mode="json")["topic_id"] == NHI


def test_topic_of_the_request_and_of_its_expansion_cannot_disagree() -> None:
    with pytest.raises(ValueError, match="topic"):
        SearchRequest(
            query="q",
            topic_id=NHI,
            expansion=ExpansionRequest(argument="politics-da", need="link", topic_id="pf-test-topic"),
        )


# --------------------------------------------------------------------------------------------
# Topic enablement: the feed files say which topics enable which government providers
# --------------------------------------------------------------------------------------------

FEED_FILE: Final = """\
topic: health-insurance
description: A test topic.
feeds: []
search_topics: [policy-2026-27-nhi]
government_providers: [federal_register, govinfo]
"""


def test_topic_committed_feed_files_enable_both_government_providers_for_nhi_only() -> None:
    configs = load_feed_directory(COMMITTED_FEEDS)
    assert topic_providers(configs) == {NHI: frozenset({"federal_register", "govinfo"})}
    assert search_topic_ids(configs) == (NHI,)


def test_topic_feed_file_reads_its_search_topics_and_government_providers(tmp_path: Path) -> None:
    path = tmp_path / "health-insurance.yaml"
    path.write_text(FEED_FILE, encoding="utf-8")
    config = load_feed_config(path)
    assert config.search_topics == (NHI,)
    assert config.government_providers == (SearchProviderName.FEDERAL_REGISTER, SearchProviderName.GOVINFO)


@pytest.mark.parametrize(
    ("text", "complaint"),
    [
        (FEED_FILE.replace("[federal_register, govinfo]", "[rss]"), "only government providers"),
        (
            FEED_FILE.replace("[federal_register, govinfo]", "[openalex, govinfo]"),
            "only government providers",
        ),
        (FEED_FILE.replace("[federal_register, govinfo]", "[congress_gov]"), "government_providers"),
        (FEED_FILE.replace("[federal_register, govinfo]", "[govinfo, govinfo]"), "twice"),
        (FEED_FILE.replace("search_topics: [policy-2026-27-nhi]\n", ""), "no search_topics"),
        (FEED_FILE.replace("[policy-2026-27-nhi]", "[Policy 2026]"), "search_topics"),
    ],
    ids=[
        "a-news-provider",
        "a-scholarly-provider",
        "unknown-name",
        "twice",
        "no-topic-for-them",
        "bad-topic-id",
    ],
)
def test_topic_feed_file_mistake_fails_the_load(tmp_path: Path, text: str, complaint: str) -> None:
    path = tmp_path / "health-insurance.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(FeedConfigError, match=complaint):
        load_feed_config(path)


def test_topic_providers_of_two_files_naming_one_topic_are_joined() -> None:
    first = FeedConfig(
        topic="one",
        description="One.",
        search_topics=(NHI,),
        government_providers=(SearchProviderName.GOVINFO,),
    )
    second = FeedConfig(
        topic="two",
        description="Two.",
        search_topics=(NHI, "pf-test-topic"),
        government_providers=(SearchProviderName.FEDERAL_REGISTER,),
    )
    plain = FeedConfig(topic="three", description="Three.", search_topics=("ld-test-topic",))
    assert topic_providers((first, second, plain)) == {
        NHI: frozenset({"govinfo", "federal_register"}),
        "pf-test-topic": frozenset({"federal_register"}),
        "ld-test-topic": frozenset(),
    }
    assert search_topic_ids((first, second, plain)) == (NHI, "pf-test-topic", "ld-test-topic")


# ============================================================================================
# GovInfo
# ============================================================================================

GOVINFO_FIXTURES: Final = DISCOVERY_FIXTURES / "govinfo"


def govinfo_recording(name: str) -> Recording:
    return load_recording(GOVINFO_FIXTURES / f"{name}.json")


def govinfo_over(
    transport: httpx.AsyncBaseTransport, *, api_data_gov_key: str | None = API_DATA_GOV_KEY
) -> GovInfoProvider:
    """The adapter exactly as the registry builds it, over `transport`, with every credential set."""
    factory = govinfo_factory(HttpSettings(), version=VERSION, clock=FixedClock(), transport=transport)
    return factory(provider_settings(SearchProviderName.GOVINFO, api_data_gov_key=api_data_gov_key))


def a_result(**fields: Any) -> dict[str, Any]:
    """A minimal mappable GovInfo search result, with `fields` laid over it."""
    return {"title": "A title", "packageId": "CRPT-119hrpt900", "collectionCode": "CRPT", **fields}


SINGLE_PAYER: Final = ProviderQuery(
    query="single payer health insurance",
    filters=SearchFilters(
        since=datetime(2025, 1, 1, tzinfo=UTC), until=datetime(2026, 6, 30, tzinfo=UTC), max_results=6
    ),
)
GOVINFO_EMPTY: Final = httpx.Response(200, json={"count": 0, "offsetMark": None, "results": []})


# --------------------------------------------------------------------------------------------
# GovInfo: package ids and bills
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("package_id", "expected"),
    [
        ("BILLS-119hr4821ih", BillNumber(congress=119, bill_type="hr", number=4821, version="ih")),
        ("BILLS-118hres55eh", BillNumber(congress=118, bill_type="hres", number=55, version="eh")),
        ("BILLS-119sjres3enr", BillNumber(congress=119, bill_type="sjres", number=3, version="enr")),
        ("BILLS-119hconres12rds", BillNumber(congress=119, bill_type="hconres", number=12, version="rds")),
        ("BILLS-119s77is", BillNumber(congress=119, bill_type="s", number=77, version="is")),
        ("BILLS-119sres1ats", BillNumber(congress=119, bill_type="sres", number=1, version="ats")),
    ],
)
def test_govinfo_bill_congress_type_and_number_are_read_from_its_package_id(
    package_id: str, expected: BillNumber
) -> None:
    assert bill_number(package_id) == expected


@pytest.mark.parametrize(
    "package_id",
    [
        "BILLS-s77is",
        "BILLS-119xx12ih",
        "BILLS-119hr",
        "BILLS-119hr12",
        "BILLS-119hr012ih",
        "CRPT-119hrpt212",
        "bills-119hr4821ih",
        "",
    ],
    ids=[
        "no-congress",
        "unknown-type",
        "no-number",
        "no-version",
        "zero-padded",
        "not-a-bill",
        "lower-case",
        "empty",
    ],
)
def test_govinfo_package_id_that_is_not_a_bills_one_gives_no_bill(package_id: str) -> None:
    assert bill_number(package_id) is None


def test_govinfo_bill_whose_package_id_names_no_bill_is_not_a_candidate() -> None:
    assert candidate_from_result(a_result(packageId="BILLS-s77is", collectionCode="BILLS")) is None
    kept = candidate_from_result(a_result(packageId="BILLS-119s77is", collectionCode="BILLS"))
    assert kept is not None and kept.provider_record_id == "BILLS-119s77is"


# --------------------------------------------------------------------------------------------
# GovInfo: result to CandidateResult
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "result",
    [
        a_result(title=None),
        a_result(title="  "),
        a_result(packageId=None),
        a_result(packageId=" "),
        a_result(packageId="CRPT 119 hrpt 212"),
        a_result(packageId="CRPT-119hrpt212/../x"),
    ],
    ids=["no-title", "blank-title", "no-package", "blank-package", "spaces-in-package", "path-in-package"],
)
def test_govinfo_result_without_a_title_or_a_package_id_is_not_a_candidate(result: dict[str, Any]) -> None:
    assert candidate_from_result(result) is None


def test_govinfo_url_is_the_package_details_page_and_no_api_link_is_offered() -> None:
    result = a_result(download={"pdfLink": "https://api.govinfo.gov/packages/CRPT-119hrpt900/pdf"})
    candidate = candidate_from_result(result)
    assert candidate is not None
    assert candidate.url == "https://www.govinfo.gov/app/details/CRPT-119hrpt900"
    assert candidate.open_access_url is None
    assert candidate.open_access is True
    assert candidate.source_type is SourceType.GOVERNMENT
    assert (candidate.provider, candidate.authors, candidate.snippet) == ("govinfo", (), None)


@pytest.mark.parametrize(
    ("date_issued", "published_at", "precision"),
    [
        ("2025-07-22", datetime(2025, 7, 22, tzinfo=UTC), DatePrecision.DAY),
        ("2025-07-22T00:00:00Z", datetime(2025, 7, 22, tzinfo=UTC), DatePrecision.DAY),
        ("2025-09", datetime(2025, 9, 1, tzinfo=UTC), DatePrecision.MONTH),
        ("2026", datetime(2026, 1, 1, tzinfo=UTC), DatePrecision.YEAR),
        ("2025-02-30", None, None),
        ("2025-13", None, None),
        ("0000", None, None),
        ("July 2025", None, None),
        ("2025-7-2", None, None),
        (None, None, None),
        (2025, None, None),
    ],
    ids=[
        "day",
        "timestamp",
        "month",
        "year",
        "impossible-day",
        "impossible-month",
        "year-zero",
        "prose",
        "unpadded",
        "missing",
        "number",
    ],
)
def test_govinfo_date_issued_keeps_its_precision_and_never_gains_a_day(
    date_issued: object, published_at: datetime | None, precision: DatePrecision | None
) -> None:
    candidate = candidate_from_result(a_result(dateIssued=date_issued))
    assert candidate is not None
    assert (candidate.published_at, candidate.date_precision) == (published_at, precision)


@pytest.mark.parametrize(
    ("government_author", "expected"),
    [
        (["Congress. Senate. Committee on Finance"], "Congress. Senate. Committee on Finance"),
        (
            ["Congress. House. Committee on Ways and Means", " Congress. House "],
            "Congress. House. Committee on Ways and Means; Congress. House",
        ),
        (["Congress. House", None, 3, "", "Congress. House"], "Congress. House"),
        ([], None),
        (None, None),
        ("Congress. House", None),
    ],
    ids=["one", "two-in-order", "non-text-and-repeat", "empty", "missing", "not-a-list"],
)
def test_govinfo_issuing_committee_is_the_publication(
    government_author: object, expected: str | None
) -> None:
    candidate = candidate_from_result(a_result(governmentAuthor=government_author))
    assert candidate is not None
    assert candidate.publication == expected


# --------------------------------------------------------------------------------------------
# GovInfo: the request
# --------------------------------------------------------------------------------------------


async def test_govinfo_request_is_one_post_with_the_key_in_its_header_and_nowhere_else() -> None:
    seen: list[httpx.Request] = []
    await govinfo_over(answering(GOVINFO_EMPTY, seen)).search(SINGLE_PAYER)

    (request,) = seen
    assert (request.method, str(request.url)) == ("POST", "https://api.govinfo.gov/search")
    assert request.headers["x-api-key"] == API_DATA_GOV_KEY
    assert request.headers["content-type"] == "application/json"
    assert request.headers["user-agent"] == HttpSettings().user_agent(VERSION)
    assert "cookie" not in request.headers
    assert API_DATA_GOV_KEY not in str(request.url) + request.content.decode("utf-8")
    assert CONTACT_EMAIL not in str(request.url) + request.content.decode("utf-8") + str(request.headers)


async def test_govinfo_request_body_searches_the_four_collections_in_the_window_by_relevance() -> None:
    seen: list[httpx.Request] = []
    await govinfo_over(answering(GOVINFO_EMPTY, seen)).search(SINGLE_PAYER)

    assert json.loads(seen[0].content) == {
        "query": (
            "(single payer health insurance) AND collection:(BILLS OR CRPT OR CHRG OR CPRT)"
            " AND publishdate:range(2025-01-01,2026-06-30)"
        ),
        "pageSize": 6,
        "offsetMark": "*",
        "sorts": [{"field": "score", "sortOrder": "DESC"}],
    }


@pytest.mark.parametrize(
    ("filters", "query"),
    [
        (SearchFilters(), "(medicaid) AND collection:(BILLS OR CRPT OR CHRG OR CPRT)"),
        (
            SearchFilters(since=datetime(2025, 1, 1, tzinfo=UTC)),
            "(medicaid) AND collection:(BILLS OR CRPT OR CHRG OR CPRT) AND publishdate:range(2025-01-01,)",
        ),
        (
            SearchFilters(until=datetime(2026, 6, 30, 23, 59, tzinfo=UTC)),
            "(medicaid) AND collection:(BILLS OR CRPT OR CHRG OR CPRT) AND publishdate:range(,2026-06-30)",
        ),
        (
            SearchFilters(since=datetime(2025, 1, 1, 22, tzinfo=timezone(timedelta(hours=-5)))),
            "(medicaid) AND collection:(BILLS OR CRPT OR CHRG OR CPRT) AND publishdate:range(2025-01-02,)",
        ),
    ],
    ids=["no-window", "since-only", "until-only", "utc-date"],
)
def test_govinfo_request_query_carries_the_window_it_was_given(filters: SearchFilters, query: str) -> None:
    assert search_body(ProviderQuery(query="medicaid", filters=filters))["query"] == query


@pytest.mark.parametrize(
    ("typed", "searched"),
    [
        ("insurance (single:payer)", "insurance single payer"),
        ('"single payer" mandate', '"single payer" mandate'),
        ('"single payer mandate', "single payer mandate"),
        ("collection:(USCOURTS) medicaid", "collection USCOURTS medicaid"),
        ("  medicaid   expansion ", "medicaid expansion"),
    ],
    ids=["brackets-and-colon", "balanced-quotes-kept", "odd-quote-dropped", "field-syntax", "spaces"],
)
def test_govinfo_query_words_that_would_read_as_search_syntax_are_cleared(typed: str, searched: str) -> None:
    query = str(search_body(ProviderQuery(query=typed))["query"])
    assert query == f"({searched}) AND collection:(BILLS OR CRPT OR CHRG OR CPRT)"


async def test_govinfo_query_of_nothing_but_search_syntax_asks_nothing_and_answers_empty() -> None:
    seen: list[httpx.Request] = []
    answer = await govinfo_over(answering(GOVINFO_EMPTY, seen)).search(ProviderQuery(query='():"'))
    assert seen == []
    assert answer.results == () and not answer.partial


async def test_govinfo_answer_keeps_one_candidate_per_package_and_to_max_results() -> None:
    results = [
        a_result(packageId="CRPT-119hrpt901", granuleId="CRPT-119hrpt901-1"),
        a_result(packageId="CRPT-119hrpt901", granuleId="CRPT-119hrpt901-2", title="Part two"),
        a_result(packageId="CRPT-119hrpt902"),
        a_result(packageId="CRPT-119hrpt903"),
    ]
    provider = govinfo_over(answering(httpx.Response(200, json={"count": 4, "results": results})))

    answer = await provider.search(ProviderQuery(query="q", filters=SearchFilters(max_results=2)))

    assert [(result.provider_record_id, result.title) for result in answer.results] == [
        ("CRPT-119hrpt901", "A title"),
        ("CRPT-119hrpt902", "A title"),
    ]


# --------------------------------------------------------------------------------------------
# GovInfo: failures
# --------------------------------------------------------------------------------------------


async def test_govinfo_429_without_retry_after_is_rate_limited_for_no_stated_time() -> None:
    replayed = replay_with_respx(govinfo_over)(govinfo_recording("search_rate_limited"))
    with pytest.raises(ProviderRateLimited) as raised:
        await replayed.provider.search(SINGLE_PAYER)
    assert raised.value.retry_after_seconds is None


async def test_govinfo_refused_key_is_unavailable_and_never_names_the_key() -> None:
    replayed = replay_with_respx(govinfo_over)(govinfo_recording("search_key_refused"))
    with pytest.raises(ProviderUnavailable) as raised:
        await replayed.provider.search(SINGLE_PAYER)
    assert str(raised.value) == "govinfo: HTTP 403: the provider refused the request"


async def test_govinfo_redirect_is_unavailable_and_names_only_the_host() -> None:
    redirect = httpx.Response(302, headers={"location": "https://api.data.gov/blocked?api_key=x"})
    with pytest.raises(ProviderUnavailable) as raised:
        await govinfo_over(answering(redirect)).search(SINGLE_PAYER)
    assert str(raised.value) == "govinfo: HTTP 302: redirected to api.data.gov"


async def test_govinfo_html_page_instead_of_json_is_unavailable() -> None:
    replayed = replay_with_respx(govinfo_over)(govinfo_recording("search_malformed"))
    with pytest.raises(ProviderUnavailable, match="unreadable response"):
        await replayed.provider.search(SINGLE_PAYER)


@pytest.mark.parametrize(
    "document",
    [[], "text", {"count": 3}, {"count": 1, "results": "x"}, {"count": 1, "results": [1]}, {"results": None}],
    ids=[
        "list",
        "string",
        "count-without-results",
        "results-not-list",
        "results-not-objects",
        "results-null",
    ],
)
async def test_govinfo_body_without_a_list_of_results_is_unavailable(document: object) -> None:
    with pytest.raises(ProviderUnavailable, match="unreadable response"):
        await govinfo_over(answering(httpx.Response(200, json=document))).search(SINGLE_PAYER)


@pytest.mark.parametrize(
    "error", [httpx.ReadTimeout("timed out"), httpx.ConnectError("refused")], ids=["timeout", "connection"]
)
async def test_govinfo_transport_failure_is_unavailable_and_keeps_its_cause(error: httpx.HTTPError) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise error

    with pytest.raises(ProviderUnavailable) as raised:
        await govinfo_over(httpx.MockTransport(fail)).search(SINGLE_PAYER)
    assert raised.value.__cause__ is error


# --------------------------------------------------------------------------------------------
# GovInfo: wrapped by the registry, with and without the key
# --------------------------------------------------------------------------------------------


def govinfo_registry_over(
    name: str, clock: FixedClock, **settings: Any
) -> tuple[ProviderRegistry, ReplayedProvider]:
    """The registry's govinfo provider, over the named recording, and the registry itself."""
    registries: list[ProviderRegistry] = []

    def build(transport: httpx.AsyncBaseTransport) -> SearchProvider:
        factory = govinfo_factory(HttpSettings(), version=VERSION, clock=clock, transport=transport)
        registry = ProviderRegistry.from_settings(
            provider_settings(SearchProviderName.GOVINFO, **settings),
            {SearchProviderName.GOVINFO: factory},
            clock=clock,
        )
        registries.append(registry)
        return registry.get("govinfo")

    replayed = replay_with_respx(build)(govinfo_recording(name))
    return registries[0], replayed


@pytest.mark.parametrize("key", [None, "", "  "], ids=["unset", "empty", "spaces"])
def test_govinfo_key_missing_builds_no_adapter_and_records_it_not_configured(key: str | None) -> None:
    factory = govinfo_factory(
        HttpSettings(), version=VERSION, clock=FixedClock(), transport=answering(GOVINFO_EMPTY)
    )
    registry = ProviderRegistry.from_settings(
        provider_settings(SearchProviderName.GOVINFO, api_data_gov_key=key),
        {SearchProviderName.GOVINFO: factory},
        clock=FixedClock(),
    )
    assert (registry.names, dict(registry.not_configured)) == ((), {"govinfo": MISSING_KEY})


async def test_govinfo_429_holds_it_for_the_first_backoff_without_sending_again() -> None:
    clock = FixedClock()
    registry, replayed = govinfo_registry_over("search_rate_limited", clock, breaker_cooldown_seconds=600)
    for _ in range(2):
        with pytest.raises(ProviderRateLimited):
            await replayed.provider.search(SINGLE_PAYER)
    assert len(replayed.sent()) == 1
    (health,) = registry.health()
    assert health.rate_limited_until is not None
    held_for = health.rate_limited_until - clock.now()
    assert timedelta(seconds=2) <= held_for < timedelta(seconds=3), "the first backoff: 2 s, up to half longer"


@pytest.mark.usefixtures("bare_protected_loggers")
async def test_govinfo_key_reaches_no_log_line_error_repr_or_snapshot(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    clock = FixedClock()
    surfaces: list[str] = []
    for name in (
        "search_results",
        "search_rate_limited",
        "search_key_refused",
        "search_unavailable",
        "search_malformed",
    ):
        registry, replayed = govinfo_registry_over(name, clock)
        surfaces += [repr(registry), repr(replayed.provider), repr(registry.providers[0])]
        try:
            await replayed.provider.search(SINGLE_PAYER)
        except (ProviderRateLimited, ProviderUnavailable) as error:
            surfaces += [str(error), repr(error), str(error.__cause__), repr(error.__cause__)]
        surfaces += [snapshot.model_dump_json() for snapshot in registry.health()]
    logger.warning("adapter state: key=%s", API_DATA_GOV_KEY)
    surfaces += [record.getMessage() for record in caplog.records]

    assert any("HTTP Request: POST https://api.govinfo.gov/search" in text for text in surfaces)
    assert any("adapter state: key=***" in text for text in surfaces)
    assert not [text for text in surfaces if API_DATA_GOV_KEY in text or CONTACT_EMAIL in text]


def test_govinfo_repr_says_a_key_is_configured_and_nothing_more() -> None:
    assert repr(govinfo_over(answering(GOVINFO_EMPTY))) == "GovInfoProvider(api_key=configured)"


# --------------------------------------------------------------------------------------------
# GovInfo: the shared contract kit
# --------------------------------------------------------------------------------------------


class TestGovInfoProvider(SearchProviderContract):
    """GovInfo on the recorded single-payer search, with the api.data.gov key and a contact email."""

    @pytest.fixture
    def recording(self) -> Recording:
        return govinfo_recording("search_results")

    @pytest.fixture
    def replay(self) -> ReplayFactory:
        return replay_with_respx(govinfo_over)

    @pytest.fixture
    def secrets(self) -> tuple[str, ...]:
        return (API_DATA_GOV_KEY, CONTACT_EMAIL)

    @pytest.fixture
    def max_attempts(self) -> int:
        """The adapter never retries; a POST is sent once whatever this says."""
        return 1


class TestGovInfoProviderOnAnEmptyResult(TestGovInfoProvider):
    """A search GovInfo has nothing for."""

    @pytest.fixture
    def recording(self) -> Recording:
        return govinfo_recording("search_empty")
