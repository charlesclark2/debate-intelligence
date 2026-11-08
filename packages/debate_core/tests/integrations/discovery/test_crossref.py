"""CrossrefProvider: the request it sends, its pace, how items map to candidates, and the contract kit.

Every Crossref answer here is hand-written from Crossref's documented `/works` response and lives in
`packages/debate_core/tests/fixtures/discovery/crossref/`, beside OpenAlex's; every expected mapping
is written by hand from those bodies (working agreement 6). Nothing here reaches the network.

The pace is tested on :class:`VirtualTime`, a clock and a sleep on one timeline that moves only when
every task is waiting, so a search of eleven queries at a public pool's one a second runs in
milliseconds and every start time is exact.
"""

from __future__ import annotations

import asyncio
import heapq
import itertools
import json
import logging
import re
from collections.abc import Awaitable, Callable, Coroutine, Iterator, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Final

import httpx
import pytest
import respx
from pydantic import SecretStr

from debate_core.application.errors import ProviderRateLimited, ProviderTimedOut, ProviderUnavailable
from debate_core.application.federated_search import FanOutStage, search_status
from debate_core.application.federated_search_types import SearchRequest, SearchState
from debate_core.application.ports.providers import SearchProvider
from debate_core.application.settings import HttpSettings, ProviderSettings, SearchProviderName
from debate_core.domain import SearchStatus
from debate_core.domain.discovery import (
    BreakerState,
    CandidateResult,
    DatePrecision,
    ProviderHealth,
    ProviderOutcome,
    ProviderQuery,
    ProviderResponse,
)
from debate_core.domain.enums import SourceType
from debate_core.domain.search import SearchFilters
from debate_core.integrations.discovery.crossref import (
    CROSSREF_WORKS_URL,
    POLITE_POOL,
    PUBLIC_POOL,
    CrossrefProvider,
    PoolLimits,
    advertised_limits,
    answer_reserve_seconds,
    candidate_from_item,
    crossref_factory,
    source_type_for,
    strip_jats,
    works_parameters,
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
    load_recording,
)
from debate_core.testing.fakes.clock_and_ids import FixedClock
from debate_core.testing.virtual_time import EventLoopClock, run_in_virtual_time

pytestmark = pytest.mark.anyio

FIXTURES: Final = Path(__file__).resolve().parents[2] / "fixtures" / "discovery" / "crossref"
CONTACT_EMAIL: Final = "crossref-coach@example.org"
VERSION: Final = "0.0.0-test"
NOW: Final = datetime(2024, 1, 1, tzinfo=UTC)
"""The test clock's start (FixedClock's default): licences are judged in force against it."""
SELECT: Final = (
    "DOI,title,container-title,author,issued,published-online,published-print,type,"
    "is-referenced-by-count,license,link,abstract"
)
NOT_ASKED_PUBLIC: Final = (
    "crossref: not asked: the public pool allows 1 query a second; set a contact email for the polite pool"
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def bare_protected_loggers() -> Iterator[None]:
    """The protected loggers start with no filters, and get theirs back afterwards.

    Their filters are shared by the whole process: a test that ran earlier in this worker (the
    OpenCaselist client's, the fetcher's, the DOI client's) may have left one that hides a leak
    (working agreement 10).
    """
    saved = {name: list(logging.getLogger(name).filters) for name in PROTECTED_LOGGERS}
    for name in PROTECTED_LOGGERS:
        logging.getLogger(name).filters.clear()
    yield
    for name, filters in saved.items():
        logging.getLogger(name).filters[:] = filters


# --------------------------------------------------------------------------------------------
# Virtual time
# --------------------------------------------------------------------------------------------


class VirtualTime:
    """A clock and a sleep on one timeline that moves only when every task is waiting.

    :meth:`sleep` parks the caller until the timeline reaches its wake time; :meth:`run` drives a
    coroutine to completion, letting every runnable task run and then jumping the clock to the next
    sleeper's wake time. A sleep cancelled before it wakes is dropped.
    """

    def __init__(self, start: datetime = NOW) -> None:
        self.clock = FixedClock(start)
        self._timers: list[tuple[datetime, int, asyncio.Future[None]]] = []
        self._order = itertools.count()

    async def sleep(self, seconds: float) -> None:
        if seconds <= 0:
            await asyncio.sleep(0)
            return
        wake: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        heapq.heappush(self._timers, (self.clock.now() + timedelta(seconds=seconds), next(self._order), wake))
        await wake

    def seconds_since(self, start: datetime = NOW) -> float:
        return (self.clock.now() - start).total_seconds()

    async def run[T](self, work: Awaitable[T]) -> T:
        task = asyncio.ensure_future(work)
        while True:
            for _ in range(200):
                await asyncio.sleep(0)
            if task.done():
                return task.result()
            while self._timers and self._timers[0][2].done():
                heapq.heappop(self._timers)
            if not self._timers:
                task.cancel()
                raise AssertionError("every task is waiting and no sleeper will wake one")
            wake_at, _, wake = heapq.heappop(self._timers)
            self.clock.set(max(wake_at, self.clock.now()))
            wake.set_result(None)


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


def provider_settings(*, contact_email: str | None = CONTACT_EMAIL, **overrides: Any) -> ProviderSettings:
    """Crossref enabled, with a contact email (unless `None`) for the polite pool."""
    return ProviderSettings(
        enabled=(SearchProviderName.CROSSREF,),
        contact_email=SecretStr(contact_email) if contact_email is not None else None,
        **overrides,
    )


def build_over(
    transport: httpx.AsyncBaseTransport,
    *,
    contact_email: str | None = CONTACT_EMAIL,
    time: VirtualTime | None = None,
    **overrides: Any,
) -> CrossrefProvider:
    """The adapter exactly as the registry builds it, over `transport`; on `time` when given."""
    clock = time.clock if time is not None else FixedClock()
    factory = crossref_factory(
        HttpSettings(),
        version=VERSION,
        clock=clock,
        sleep=time.sleep if time is not None else instant_sleep(clock),
        transport=transport,
    )
    return factory(provider_settings(contact_email=contact_email, **overrides))


def replay_with_respx(
    build: Callable[[httpx.AsyncBaseTransport], SearchProvider], seen: list[httpx.Request] | None = None
) -> ReplayFactory:
    """Serve a recording's exchanges through respx, and nothing else.

    A copy of the FakeProvider binding's (`test_fake_provider.py`), as OpenAlex's is: the adapter is
    built from a transport, so that the factory's own client is the one under test, and every
    request is kept in `seen` when given. Transport failures are raised here rather than as respx
    side effects, because respx re-raises a side effect `from` an error that quotes the matched
    route, and with it the `mailto=` address.
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


def without_mailto(recorded: Recording) -> Recording:
    """`recorded` as the public pool sends it: every URL without its `mailto=`."""
    return replace(
        recorded,
        exchanges=tuple(
            replace(exchange, url=re.sub(r"&mailto=[^&]*", "", exchange.url))
            for exchange in recorded.exchanges
        ),
    )


def body(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def an_item(**fields: Any) -> dict[str, Any]:
    """A minimal mappable item, with `fields` laid over it."""
    return {"DOI": "10.5555/x.1", "title": ["A title"], **fields}


def candidate(**fields: Any) -> CandidateResult:
    mapped = candidate_from_item(an_item(**fields), now=NOW)
    assert mapped is not None
    return mapped


def works(*items: dict[str, Any]) -> dict[str, Any]:
    """A `/works` answer around `items`."""
    return {"status": "ok", "message-type": "work-list", "message": {"items": list(items)}}


# --------------------------------------------------------------------------------------------
# Work type to source type
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("work_type", "expected"),
    [
        ("journal-article", SourceType.SCHOLARLY),
        ("proceedings-article", SourceType.SCHOLARLY),
        ("posted-content", SourceType.SCHOLARLY),
        ("book", SourceType.SCHOLARLY),
        ("monograph", SourceType.SCHOLARLY),
        ("edited-book", SourceType.SCHOLARLY),
        ("reference-book", SourceType.SCHOLARLY),
        ("book-chapter", SourceType.SCHOLARLY),
        ("book-section", SourceType.SCHOLARLY),
        ("book-part", SourceType.SCHOLARLY),
        ("book-track", SourceType.SCHOLARLY),
        ("reference-entry", SourceType.SCHOLARLY),
        ("dissertation", SourceType.SCHOLARLY),
        ("peer-review", SourceType.SCHOLARLY),
        ("report", SourceType.OTHER),
        ("report-component", SourceType.OTHER),
        ("standard", SourceType.OTHER),
        ("dataset", SourceType.OTHER),
        ("database", SourceType.OTHER),
        ("component", SourceType.OTHER),
        ("grant", SourceType.OTHER),
        ("other", SourceType.OTHER),
        ("journal", SourceType.OTHER),
        ("journal-volume", SourceType.OTHER),
        ("journal-issue", SourceType.OTHER),
        ("proceedings", SourceType.OTHER),
        ("proceedings-series", SourceType.OTHER),
        ("book-series", SourceType.OTHER),
        ("book-set", SourceType.OTHER),
        ("report-series", SourceType.OTHER),
    ],
)
def test_each_documented_work_type_maps_to_its_source_type(work_type: str, expected: SourceType) -> None:
    assert source_type_for(work_type) is expected


@pytest.mark.parametrize(
    "work_type",
    ["article", "Journal-Article", "preprint", "journal article", "", None, 7, ["journal-article"]],
    ids=repr,
)
def test_an_unknown_or_missing_work_type_maps_to_other(work_type: object) -> None:
    assert source_type_for(work_type) is SourceType.OTHER


# --------------------------------------------------------------------------------------------
# The abstract
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("abstract", "expected"),
    [
        ("<jats:p>Subsidies matter.</jats:p>", "Subsidies matter."),
        ("<jats:title>Abstract</jats:title><jats:p>Subsidies matter.</jats:p>", "Subsidies matter."),
        ("<jats:sec><jats:title>Background</jats:title><jats:p>One.</jats:p></jats:sec>", "One."),
        ("<jats:p>Costs <jats:italic>fall</jats:italic>   &amp; rise.</jats:p>", "Costs fall & rise."),
        ("<jats:p>One.</jats:p><jats:p>Two.</jats:p>", "One. Two."),
        ("Plain text with no markup.", "Plain text with no markup."),
        ("<jats:title>Abstract</jats:title>", None),
        ("   ", None),
        (None, None),
        (["<jats:p>x</jats:p>"], None),
    ],
    ids=[
        "a paragraph",
        "an Abstract heading dropped",
        "a section heading dropped",
        "inline markup, an entity and spaces",
        "two paragraphs",
        "no markup",
        "a heading alone",
        "blank",
        "null",
        "not text",
    ],
)
def test_the_abstract_loses_its_jats_markup_and_headings(abstract: object, expected: str | None) -> None:
    assert strip_jats(abstract) == expected


# --------------------------------------------------------------------------------------------
# Item to CandidateResult mapping
# --------------------------------------------------------------------------------------------


def test_the_recorded_items_map_to_the_hand_written_candidates() -> None:
    items = body("works_query.body.json")["message"]["items"]
    expected = json.loads((FIXTURES / "works_query.expected.json").read_text(encoding="utf-8"))
    mapped = [found for item in items if (found := candidate_from_item(item, now=NOW)) is not None]
    assert mapped == [CandidateResult.model_validate(entry) for entry in expected]


def test_the_mapping_keeps_no_affiliation_orcid_or_markup() -> None:
    items = body("works_query.body.json")["message"]["items"]
    stored = json.dumps(
        [found.model_dump(mode="json") for item in items if (found := candidate_from_item(item, now=NOW))]
    )
    for absent in (
        "orcid",
        "0000-0000-0000-0002",
        "University of Nowhere",
        "Department of Invented Economics",
        "<i>",
        "jats",
        "&amp;",
        "similarity",
    ):
        assert absent not in stored


@pytest.mark.parametrize(
    "item",
    [
        {"DOI": "10.5555/x.1"},
        an_item(title=[]),
        an_item(title=["   "]),
        an_item(title="A title, not a list"),
        an_item(DOI=None),
        {"title": ["A title"]},
        an_item(DOI="not-a-doi"),
    ],
    ids=[
        "no title",
        "empty title list",
        "blank title",
        "title not a list",
        "null DOI",
        "no DOI",
        "not a DOI",
    ],
)
def test_an_item_with_no_title_or_no_doi_is_not_a_candidate(item: dict[str, Any]) -> None:
    assert candidate_from_item(item, now=NOW) is None


def test_the_doi_is_normalized_once_and_names_the_record_and_the_url() -> None:
    found = candidate(DOI="https://doi.org/10.5555/MIXED.Case.7")
    assert found.identifiers.doi == "10.5555/mixed.case.7"
    assert found.provider_record_id == "10.5555/mixed.case.7"
    assert found.url == "https://doi.org/10.5555/mixed.case.7"


@pytest.mark.parametrize(
    ("dates", "published_at", "precision"),
    [
        ({"issued": {"date-parts": [[2022, 5, 17]]}}, datetime(2022, 5, 17, tzinfo=UTC), DatePrecision.DAY),
        ({"issued": {"date-parts": [[2023, 3]]}}, datetime(2023, 3, 1, tzinfo=UTC), DatePrecision.MONTH),
        ({"issued": {"date-parts": [[2021]]}}, datetime(2021, 1, 1, tzinfo=UTC), DatePrecision.YEAR),
        (
            {"issued": {"date-parts": [[2021]]}, "published-online": {"date-parts": [[2021, 6, 4]]}},
            datetime(2021, 1, 1, tzinfo=UTC),
            DatePrecision.YEAR,
        ),
        (
            {"issued": {"date-parts": [[None]]}, "published-online": {"date-parts": [[2020, 11, 2]]}},
            datetime(2020, 11, 2, tzinfo=UTC),
            DatePrecision.DAY,
        ),
        (
            {
                "published-print": {"date-parts": [[2019, 8]]},
                "published-online": {"date-parts": [[2019, 7, 1]]},
            },
            datetime(2019, 7, 1, tzinfo=UTC),
            DatePrecision.DAY,
        ),
        (
            {"published-print": {"date-parts": [[2019, 8]]}},
            datetime(2019, 8, 1, tzinfo=UTC),
            DatePrecision.MONTH,
        ),
        (
            {"issued": {"date-parts": [[2024, 2, 30]]}, "published-print": {"date-parts": [[2024, 3]]}},
            datetime(2024, 3, 1, tzinfo=UTC),
            DatePrecision.MONTH,
        ),
        ({"issued": {"date-parts": [["2022", "5"]]}}, None, None),
        ({"issued": {"date-parts": []}}, None, None),
        ({"issued": "2022-05-17"}, None, None),
        ({}, None, None),
    ],
    ids=[
        "issued, full",
        "issued, year and month",
        "issued, year alone",
        "issued before a more precise online date",
        "issued null, online date",
        "online before print",
        "print alone",
        "an impossible day skipped",
        "strings",
        "no parts",
        "not date parts",
        "no dates",
    ],
)
def test_the_date_is_issued_then_online_then_print_at_its_deposited_precision(
    dates: dict[str, Any], published_at: datetime | None, precision: DatePrecision | None
) -> None:
    found = candidate(**dates)
    assert (found.published_at, found.date_precision) == (published_at, precision)


def test_a_year_only_date_is_never_given_a_day() -> None:
    found = candidate(issued={"date-parts": [[2021]]})
    assert found.date_precision is DatePrecision.YEAR
    assert found.date_precision is not DatePrecision.DAY


def test_authors_are_given_and_family_names_or_a_whole_name_in_byline_order() -> None:
    found = candidate(
        author=[
            {"given": " Ilse ", "family": "Marrowby", "sequence": "first"},
            {"family": "Oddleigh"},
            {"name": "Invented Energy Institute"},
            {"given": "Only-Given"},
            {"affiliation": [{"name": "Somewhere"}]},
            "not an author",
            {"given": "Last", "family": "Person", "ORCID": "https://orcid.org/0000-0000-0000-0009"},
        ]
    )
    assert found.authors == ("Ilse Marrowby", "Oddleigh", "Invented Energy Institute", "Last Person")


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        (
            {"container-title": ["Journal of Invented Economics", "J. Inv. Econ."]},
            "Journal of Invented Economics",
        ),
        ({"container-title": ["<i>Invented</i>  Review"]}, "Invented Review"),
        ({"container-title": []}, None),
        ({}, None),
    ],
    ids=["first of several", "markup removed", "empty", "absent"],
)
def test_the_venue_is_the_first_container_title(fields: dict[str, Any], expected: str | None) -> None:
    assert candidate(**fields).publication == expected


@pytest.mark.parametrize(
    ("count", "expected"),
    [(17, 17), (0, 0), (-1, None), ("12", None), (3.0, None), (True, None), (None, None)],
    ids=["a count", "zero", "negative", "a string", "a float", "a bool", "null"],
)
def test_the_citation_count_is_is_referenced_by_count(count: object, expected: int | None) -> None:
    assert candidate(**{"is-referenced-by-count": count}).citation_count == expected


CC_BY: Final = {
    "URL": "https://creativecommons.org/licenses/by/4.0/",
    "start": {"date-parts": [[2022, 5, 17]], "date-time": "2022-05-17T00:00:00Z"},
    "delay-in-days": 0,
    "content-version": "vor",
}
PDF_LINK: Final = {
    "URL": "https://publisher.example.org/a.pdf",
    "content-type": "application/pdf",
    "content-version": "vor",
    "intended-application": "text-mining",
}


@pytest.mark.parametrize(
    ("fields", "open_access", "url"),
    [
        ({"license": [CC_BY], "link": [PDF_LINK]}, True, "https://publisher.example.org/a.pdf"),
        ({"license": [CC_BY]}, True, None),
        ({"link": [PDF_LINK]}, None, None),
        (
            {
                "license": [{**CC_BY, "URL": "https://www.publisher.example.org/tdm/userlicense/1.0/"}],
                "link": [PDF_LINK],
            },
            None,
            None,
        ),
        ({"license": [{**CC_BY, "URL": "http://creativecommons.org/licenses/by-nc-nd/3.0/"}]}, True, None),
        ({"license": [{**CC_BY, "URL": "https://creativecommons.org/publicdomain/zero/1.0/"}]}, True, None),
        (
            {"license": [{**CC_BY, "URL": "https://creativecommons.org.example.org/licenses/by/4.0/"}]},
            None,
            None,
        ),
        ({"license": [{**CC_BY, "URL": "https://notcreativecommons.org/licenses/by/4.0/"}]}, None, None),
        ({"license": [{**CC_BY, "URL": "https://creativecommons.org/about/"}]}, None, None),
        (
            {
                "license": [
                    {**CC_BY, "start": {"date-parts": [[2027, 1, 1]], "date-time": "2027-01-01T00:00:00Z"}}
                ]
            },
            None,
            None,
        ),
        ({"license": [{**CC_BY, "start": {}}]}, None, None),
        ({"license": [{**CC_BY, "content-version": "tdm"}]}, None, None),
        ({"license": [{**CC_BY, "content-version": "am"}], "link": [PDF_LINK]}, True, None),
        (
            {"license": [CC_BY], "link": [{**PDF_LINK, "intended-application": "similarity-checking"}]},
            True,
            None,
        ),
        (
            {
                "license": [CC_BY],
                "link": [
                    {**PDF_LINK, "URL": "https://publisher.example.org/a.xml", "content-type": "text/xml"},
                    PDF_LINK,
                ],
            },
            True,
            "https://publisher.example.org/a.pdf",
        ),
        (
            {
                "license": [CC_BY],
                "link": [
                    {**PDF_LINK, "URL": "https://publisher.example.org/a.xml", "content-type": "text/xml"}
                ],
            },
            True,
            "https://publisher.example.org/a.xml",
        ),
        (
            {"license": [CC_BY], "link": [{**PDF_LINK, "URL": "ftp://publisher.example.org/a.pdf"}]},
            True,
            None,
        ),
        ({"license": "CC-BY"}, None, None),
        ({}, None, None),
    ],
    ids=[
        "CC BY with a PDF",
        "CC BY without a link",
        "a link alone",
        "a publisher licence",
        "CC over http",
        "public domain",
        "a look-alike host",
        "a host that ends like it",
        "not a licence path",
        "embargoed until 2027",
        "no start",
        "a CC licence for text mining only",
        "CC on the accepted manuscript, a link to the version of record",
        "a similarity-checking link",
        "the PDF before the XML",
        "an XML when there is no PDF",
        "not an http link",
        "not a list",
        "nothing said",
    ],
)
def test_open_access_comes_only_from_a_creative_commons_licence_in_force(
    fields: dict[str, Any], open_access: bool | None, url: str | None
) -> None:
    found = candidate(**fields)
    assert (found.open_access, found.open_access_url) == (open_access, url)


def test_a_link_entry_is_never_read_as_open_access_on_its_own() -> None:
    found = candidate(link=[PDF_LINK, {**PDF_LINK, "intended-application": "unspecified"}])
    assert found.open_access is None
    assert found.open_access_url is None


# --------------------------------------------------------------------------------------------
# The request
# --------------------------------------------------------------------------------------------

CARBON_CAPTURE: Final = ProviderQuery(
    query="carbon capture subsidies",
    filters=SearchFilters(
        since=datetime(2020, 1, 1, tzinfo=UTC), until=datetime(2024, 12, 31, tzinfo=UTC), max_results=6
    ),
)


def routed(
    *, params: dict[str, str] | None = None, headers: dict[str, str] | None = None
) -> tuple[respx.MockRouter, respx.Route, list[httpx.Request]]:
    """A router whose one route matches the carbon capture search, sent by the polite pool."""
    router = respx.MockRouter(assert_all_called=False, assert_all_mocked=True)
    route = router.get(
        CROSSREF_WORKS_URL,
        params=params
        if params is not None
        else {
            "query.bibliographic": "carbon capture subsidies",
            "filter": "from-pub-date:2020-01-01,until-pub-date:2024-12-31",
            "rows": "6",
            "select": SELECT,
            "mailto": CONTACT_EMAIL,
        },
        headers=headers or {},
    )
    route.return_value = httpx.Response(200, json=works())
    return router, route, []


def transport_for(router: respx.MockRouter, seen: list[httpx.Request]) -> httpx.MockTransport:
    async def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return await router.async_handler(request)

    return httpx.MockTransport(handle)


async def test_a_request_carries_the_query_the_date_filters_rows_select_and_mailto() -> None:
    router, route, seen = routed()
    answer = await build_over(transport_for(router, seen)).search(CARBON_CAPTURE)

    assert route.call_count == 1
    assert answer == ProviderResponse(provider="crossref", results=(), elapsed_ms=answer.elapsed_ms)
    assert str(seen[0].url) == (
        "https://api.crossref.org/works?query.bibliographic=carbon+capture+subsidies"
        "&filter=from-pub-date%3A2020-01-01%2Cuntil-pub-date%3A2024-12-31&rows=6"
        "&select=DOI%2Ctitle%2Ccontainer-title%2Cauthor%2Cissued%2Cpublished-online%2Cpublished-print"
        "%2Ctype%2Cis-referenced-by-count%2Clicense%2Clink%2Cabstract"
        "&mailto=crossref-coach%40example.org"
    )


async def test_a_request_with_a_contact_email_names_it_in_the_user_agent() -> None:
    router, _, seen = routed(
        headers={
            "User-Agent": f"debate-research/{VERSION} (+{HttpSettings().contact_url}; mailto:{CONTACT_EMAIL})"
        }
    )
    provider = build_over(transport_for(router, seen))
    await provider.search(CARBON_CAPTURE)
    await provider.search(CARBON_CAPTURE)

    http = HttpSettings()
    assert {request.headers["user-agent"] for request in seen} == {
        f"{http.user_agent_product}/{VERSION} (+{http.contact_url}; mailto:{CONTACT_EMAIL})"
    }
    assert all("cookie" not in request.headers for request in seen)


@pytest.mark.parametrize("contact_email", [None, "", "   "], ids=["none", "empty", "spaces"])
async def test_a_request_without_a_contact_email_goes_to_the_public_pool(contact_email: str | None) -> None:
    router, route, seen = routed(
        params={
            "query.bibliographic": "carbon capture subsidies",
            "filter": "from-pub-date:2020-01-01,until-pub-date:2024-12-31",
            "rows": "6",
            "select": SELECT,
        }
    )
    provider = build_over(transport_for(router, seen), contact_email=contact_email)
    await provider.search(CARBON_CAPTURE)

    assert route.call_count == 1
    assert "mailto" not in str(seen[0].url)
    assert seen[0].headers["user-agent"] == HttpSettings().user_agent(VERSION)
    assert repr(provider) == "CrossrefProvider(contact_email=none, pool=public)"
    assert provider.limits == PUBLIC_POOL


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        (
            SearchFilters(max_results=20),
            {"query.bibliographic": "methane leakage", "rows": "20", "select": SELECT},
        ),
        (
            SearchFilters(since=datetime(2021, 3, 4, tzinfo=UTC), max_results=5),
            {
                "query.bibliographic": "methane leakage",
                "filter": "from-pub-date:2021-03-04",
                "rows": "5",
                "select": SELECT,
            },
        ),
        (
            SearchFilters(until=datetime(2022, 7, 8, 23, 59, tzinfo=UTC), max_results=200),
            {
                "query.bibliographic": "methane leakage",
                "filter": "until-pub-date:2022-07-08",
                "rows": "200",
                "select": SELECT,
            },
        ),
        (
            SearchFilters(max_results=1),
            {"query.bibliographic": "methane leakage", "rows": "1", "select": SELECT},
        ),
    ],
    ids=["no window", "since only", "until only, 200 rows", "one row"],
)
def test_the_request_parameters_of_the_public_pool(filters: SearchFilters, expected: dict[str, str]) -> None:
    query = ProviderQuery(query="methane leakage", filters=filters)
    assert works_parameters(query, contact_email=None) == expected


def test_the_request_parameters_of_the_polite_pool_end_with_mailto() -> None:
    query = ProviderQuery(query="methane leakage", filters=SearchFilters(max_results=2))
    assert works_parameters(query, contact_email=CONTACT_EMAIL) == {
        "query.bibliographic": "methane leakage",
        "rows": "2",
        "select": SELECT,
        "mailto": CONTACT_EMAIL,
    }


def test_the_request_date_window_is_the_utc_date() -> None:
    eastern = timezone(timedelta(hours=-5))
    query = ProviderQuery(
        query="x",
        filters=SearchFilters(
            since=datetime(2020, 1, 1, 21, 30, tzinfo=eastern).astimezone(UTC),
            until=datetime(2020, 1, 3, 12, 0, tzinfo=UTC),
        ),
    )
    assert (
        works_parameters(query, contact_email=None)["filter"]
        == "from-pub-date:2020-01-02,until-pub-date:2020-01-03"
    )


async def test_the_answer_keeps_to_max_results_and_skips_untitled_items() -> None:
    items = [an_item(DOI=f"10.5555/x.{number}", title=[f"Work {number}"]) for number in range(1, 6)]
    items.insert(0, an_item(DOI="10.5555/x.0", title=[]))
    router = respx.MockRouter(assert_all_mocked=True)
    router.get(CROSSREF_WORKS_URL).return_value = httpx.Response(200, json=works(*items))
    query = ProviderQuery(query="x", filters=SearchFilters(max_results=2))

    answer = await build_over(httpx.MockTransport(router.async_handler)).search(query)

    assert [result.provider_record_id for result in answer.results] == ["10.5555/x.1", "10.5555/x.2"]


# --------------------------------------------------------------------------------------------
# The pace: the pool's documented limits, tightened by what each answer advertises
# --------------------------------------------------------------------------------------------


def test_the_documented_list_limits_are_each_pools_starting_pace() -> None:
    assert (
        PUBLIC_POOL.pool,
        PUBLIC_POOL.requests,
        PUBLIC_POOL.interval_seconds,
        PUBLIC_POOL.concurrency,
    ) == (
        "public",
        1,
        1.0,
        1,
    )
    assert (
        POLITE_POOL.pool,
        POLITE_POOL.requests,
        POLITE_POOL.interval_seconds,
        POLITE_POOL.concurrency,
    ) == (
        "polite",
        3,
        1.0,
        3,
    )
    assert PUBLIC_POOL.rate_phrase() == "1 query a second"
    assert POLITE_POOL.rate_phrase() == "3 queries a second"
    assert replace(PUBLIC_POOL, interval_seconds=2.0).rate_phrase() == "1 query every 2 seconds"
    assert replace(POLITE_POOL, interval_seconds=2.5).rate_phrase() == "3 queries every 2.5 seconds"


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"x-rate-limit-limit": "3", "x-rate-limit-interval": "1s", "x-concurrency-limit": "3"}, POLITE_POOL),
        (
            {"X-Rate-Limit-Limit": "1", "X-Rate-Limit-Interval": "2s", "X-Concurrency-Limit": "1"},
            PoolLimits(pool="polite", requests=1, interval_seconds=2.0, concurrency=1),
        ),
        (
            {"x-rate-limit-limit": "10", "x-rate-limit-interval": "1s", "x-concurrency-limit": "5"},
            POLITE_POOL,
        ),
        ({"x-rate-limit-limit": "50", "x-rate-limit-interval": "1"}, POLITE_POOL),
        (
            {"x-rate-limit-limit": "6", "x-rate-limit-interval": "4s"},
            PoolLimits(pool="polite", requests=6, interval_seconds=4.0, concurrency=3),
        ),
        ({"x-concurrency-limit": "2"}, replace(POLITE_POOL, concurrency=2)),
        ({"x-rate-limit-limit": "1"}, POLITE_POOL),
        ({"x-rate-limit-interval": "60s"}, POLITE_POOL),
        ({"x-rate-limit-limit": "0", "x-rate-limit-interval": "1s", "x-concurrency-limit": "0"}, POLITE_POOL),
        (
            {"x-rate-limit-limit": "lots", "x-rate-limit-interval": "1m", "x-concurrency-limit": "-1"},
            POLITE_POOL,
        ),
        ({}, POLITE_POOL),
    ],
    ids=[
        "the documented limits",
        "tighter, case aside",
        "looser is ignored",
        "50 a second is ignored",
        "6 every 4 seconds tightens",
        "concurrency alone",
        "a limit without an interval",
        "an interval without a limit",
        "zeroes are ignored",
        "unreadable values are ignored",
        "no headers",
    ],
)
def test_each_requests_rate_limit_headers_tighten_the_pace_and_never_loosen_it(
    headers: dict[str, str], expected: PoolLimits
) -> None:
    assert advertised_limits(POLITE_POOL, headers) == expected


async def test_a_request_after_an_answer_advertising_one_every_two_seconds_waits_two_seconds() -> None:
    time = VirtualTime()
    starts: list[float] = []

    async def answer(request: httpx.Request) -> httpx.Response:
        starts.append(time.seconds_since())
        return httpx.Response(
            200,
            json=works(),
            headers={"x-rate-limit-limit": "1", "x-rate-limit-interval": "2s", "x-concurrency-limit": "1"},
        )

    provider = build_over(httpx.MockTransport(answer), time=time)
    for _ in range(3):
        await time.run(provider.search(CARBON_CAPTURE))

    assert starts == [0.0, 2.0, 4.0]
    assert provider.limits == PoolLimits(pool="polite", requests=1, interval_seconds=2.0, concurrency=1)


async def test_a_429_advertising_a_tighter_limit_tightens_the_pace() -> None:
    replayed = replay_with_respx(build_over)(recording("works_rate_limited"))
    with pytest.raises(ProviderRateLimited):
        await replayed.provider.search(CARBON_CAPTURE)
    assert isinstance(replayed.provider, CrossrefProvider)
    assert replayed.provider.limits == PoolLimits(
        pool="polite", requests=1, interval_seconds=2.0, concurrency=1
    )


async def test_the_public_pool_sends_one_request_at_a_time_and_one_a_second() -> None:
    time = VirtualTime()
    starts: list[float] = []

    async def answer(request: httpx.Request) -> httpx.Response:
        starts.append(time.seconds_since())
        await time.sleep(1.5)
        return httpx.Response(200, json=works())

    provider = build_over(httpx.MockTransport(answer), contact_email=None, time=time)
    await time.run(asyncio.gather(*(provider.search(CARBON_CAPTURE) for _ in range(3))))

    assert starts == [0.0, 1.5, 3.0]


async def test_the_polite_pool_sends_three_at_a_time_a_third_of_a_second_apart() -> None:
    time = VirtualTime()
    starts: list[float] = []

    async def answer(request: httpx.Request) -> httpx.Response:
        starts.append(round(time.seconds_since(), 3))
        await time.sleep(1.5)
        return httpx.Response(200, json=works())

    provider = build_over(httpx.MockTransport(answer), time=time)
    await time.run(asyncio.gather(*(provider.search(CARBON_CAPTURE) for _ in range(5))))

    assert starts == [0.0, 0.333, 0.667, 1.5, 1.833]


@pytest.mark.parametrize(
    ("median", "timeout", "expected"),
    [
        (None, 10.0, 2.0),
        (1.5, 10.0, 1.5),
        (0.5, 10.0, 1.0),
        (0.0, 10.0, 1.0),
        (7.0, 10.0, 5.0),
        (5.0, 10.0, 5.0),
        (None, 3.0, 1.5),
        (0.2, 1.5, 0.75),
    ],
    ids=[
        "2 s before any answer",
        "the median",
        "at least 1 s",
        "at least 1 s from zero",
        "at most half the timeout",
        "exactly half the timeout",
        "2 s capped at half a 3 s timeout",
        "half a short timeout wins over 1 s",
    ],
)
def test_the_reserve_is_the_median_answer_time_clamped(
    median: float | None, timeout: float, expected: float
) -> None:
    assert answer_reserve_seconds(median, timeout) == expected


async def test_the_reserve_follows_the_median_of_the_answers_seen() -> None:
    time = VirtualTime()
    delays = iter([0.5, 3.0, 3.5])

    async def answer(request: httpx.Request) -> httpx.Response:
        await time.sleep(next(delays))
        return httpx.Response(200, json=works())

    provider = build_over(httpx.MockTransport(answer), contact_email=None, time=time)
    assert provider.reserve_seconds == 2.0
    for expected in (1.0, 1.75, 3.0):
        await time.run(provider.search(CARBON_CAPTURE))
        assert provider.reserve_seconds == expected


async def test_a_query_cancelled_while_waiting_gives_up_its_turn() -> None:
    time = VirtualTime()
    starts: list[float] = []

    async def answer(request: httpx.Request) -> httpx.Response:
        starts.append(time.seconds_since())
        await time.sleep(1.5)
        return httpx.Response(200, json=works())

    provider = build_over(httpx.MockTransport(answer), contact_email=None, time=time)

    async def scenario() -> None:
        first = asyncio.ensure_future(provider.search(CARBON_CAPTURE))
        doomed = asyncio.ensure_future(provider.search(CARBON_CAPTURE))
        await time.sleep(0.5)
        doomed.cancel()
        await asyncio.gather(first, provider.search(CARBON_CAPTURE), return_exceptions=True)

    await time.run(scenario())
    assert starts == [0.0, 1.5]


# --------------------------------------------------------------------------------------------
# The largest search: eleven queries at once, through the wrapper (PM ruling 2026-11-02)
# --------------------------------------------------------------------------------------------

ELEVEN: Final = tuple(
    ProviderQuery(query=f"heg answers query {number}", filters=SearchFilters(max_results=5))
    for number in range(1, 12)
)
"""As many queries as one search sends today: `heg`/`answers`'s 8 templates and 3 from a model."""


def wrapped_over(
    time: VirtualTime, answer_seconds: float, *, contact_email: str | None, asked: list[str]
) -> ProviderRegistry:
    """The registry's crossref provider over a transport that answers in `answer_seconds`."""

    async def answer(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.params["query.bibliographic"])
        await time.sleep(answer_seconds)
        return httpx.Response(200, json=works(an_item(DOI=f"10.5555/q.{len(asked)}")))

    factory = crossref_factory(
        HttpSettings(),
        version=VERSION,
        clock=time.clock,
        sleep=time.sleep,
        transport=httpx.MockTransport(answer),
    )
    return ProviderRegistry.from_settings(
        provider_settings(contact_email=contact_email),
        {SearchProviderName.CROSSREF: factory},
        clock=time.clock,
    )


def fan_out(
    registry: ProviderRegistry, time: VirtualTime, queries: Sequence[ProviderQuery]
) -> Awaitable[SearchState]:
    stage = FanOutStage(registry, clock=time.clock, deadline_seconds=15.0)
    state = SearchState(
        search_id="01JBX3V5Q8R2T6V0W4X7Y1Z3A5",
        request=SearchRequest(query="heg answers"),
        queries=tuple(queries),
    )
    return stage.run(state)


@pytest.mark.parametrize(
    ("answer_seconds", "asked_count"),
    [(0.5, 9), (1.5, 6), (2.5, 3)],
    ids=["answers in 0.5 s", "answers in 1.5 s", "answers in 2.5 s"],
)
async def test_eleven_queries_on_the_public_pool_send_what_fits_and_leave_the_breaker_closed(
    answer_seconds: float, asked_count: int
) -> None:
    """Every query starts its 10 s at once; one a second, one at a time, each sent only while its
    answer can still come back in time (the reserve), and the rest answered "not asked" in order."""
    time = VirtualTime()
    asked: list[str] = []
    registry = wrapped_over(time, answer_seconds, contact_email=None, asked=asked)

    state = await time.run(fan_out(registry, time, ELEVEN))

    assert asked == [query.query for query in ELEVEN[:asked_count]]
    statuses = state.provider_statuses
    assert [status.outcome for status in statuses] == [ProviderOutcome.OK] * 11
    answered = [status for status in statuses if status.response is not None and not status.response.partial]
    not_asked = [status for status in statuses if status.response is not None and status.response.partial]
    assert [status.query for status in answered] == list(ELEVEN[:asked_count])
    assert [status.query for status in not_asked] == list(ELEVEN[asked_count:])
    assert {status.response.error for status in not_asked if status.response} == {NOT_ASKED_PUBLIC}
    assert len(state.candidates) == asked_count
    assert search_status(statuses) is SearchStatus.PARTIAL
    (health,) = registry.health()
    assert health.state is BreakerState.CLOSED
    assert (health.error_count, health.consecutive_failures, health.last_error) == (0, 0, None)
    assert health.success_count == 11


def on_the_loops_virtual_time(
    answer_seconds: float, *, asked: list[str]
) -> Coroutine[Any, Any, tuple[SearchState, ProviderHealth]]:
    """The eleven queries through the registry's wrapper and the fan-out, every clock the loop's own.

    Run under :func:`run_in_virtual_time`, so the pacer's sleeps, the wrapper's timeout and the
    search's deadline all read one virtual clock, and an answer takes `answer_seconds` of it. Gives
    the search and Crossref's health afterwards.
    """

    async def search() -> tuple[SearchState, ProviderHealth]:
        clock = EventLoopClock(NOW)

        async def answer(request: httpx.Request) -> httpx.Response:
            asked.append(request.url.params["query.bibliographic"])
            await asyncio.sleep(answer_seconds)
            return httpx.Response(200, json=works(an_item(DOI=f"10.5555/q.{len(asked)}")))

        factory = crossref_factory(
            HttpSettings(), version=VERSION, clock=clock, transport=httpx.MockTransport(answer)
        )
        registry = ProviderRegistry.from_settings(
            provider_settings(contact_email=None), {SearchProviderName.CROSSREF: factory}, clock=clock
        )
        stage = FanOutStage(registry, clock=clock, deadline_seconds=15.0)
        state = SearchState(
            search_id="01JBX3V5Q8R2T6V0W4X7Y1Z3A5", request=SearchRequest(query="heg answers"), queries=ELEVEN
        )
        searched = await stage.run(state)
        (health,) = registry.health()
        return searched, health

    return search()


@pytest.mark.parametrize(
    ("answer_seconds", "answered_at", "not_asked_at"),
    [
        (0.5, [500, 1500, 2500, 3500, 4500, 5500, 6500, 7500, 8500], 9000),
        (1.5, [1500, 3000, 4500, 6000, 7500, 9000], 8500),
        (2.5, [2500, 5000, 7500], 7500),
    ],
    ids=["answers in 0.5 s", "answers in 1.5 s", "answers in 2.5 s"],
)
def test_the_public_pool_case_on_the_loops_virtual_time_keeps_its_results_footer_and_not_asked_answers(
    answer_seconds: float, answered_at: list[int], not_asked_at: int
) -> None:
    """The eleven-query public-pool case, pinned before the pace moved into the shared pacer.

    Written by hand: one start a second, one at a time, so query k starts when the one before it is
    answered or a second after the one before it started, whichever is later. A query is sent only
    before the timeout less the reserve, and the reserve is the median answer time clamped to at
    least 1 s, so the deadline is 9 s, 8.5 s and 7.5 s. Every query still waiting is answered "not
    asked" at that deadline. The footer is made from exactly these statuses: each one's outcome,
    whether it is partial, its error and its results.
    """
    asked: list[str] = []
    state, health = run_in_virtual_time(on_the_loops_virtual_time(answer_seconds, asked=asked))

    sent = len(answered_at)
    assert asked == [query.query for query in ELEVEN[:sent]]
    statuses = state.provider_statuses
    assert [status.query for status in statuses] == list(ELEVEN)
    assert [(status.provider, status.outcome, status.error) for status in statuses] == [
        ("crossref", ProviderOutcome.OK, None)
    ] * 11
    responses = [status.response for status in statuses]
    assert [
        (response.partial, response.error, [result.provider_record_id for result in response.results])
        for response in responses
        if response is not None
    ] == [(False, None, [f"10.5555/q.{number}"]) for number in range(1, sent + 1)] + [
        (True, NOT_ASKED_PUBLIC, [])
    ] * (11 - sent)
    assert [round(status.elapsed_ms) for status in statuses] == answered_at + [not_asked_at] * (11 - sent)
    assert [candidate.provider_record_id for candidate in state.candidates] == [
        f"10.5555/q.{number}" for number in range(1, sent + 1)
    ]
    assert search_status(statuses) is SearchStatus.PARTIAL
    assert health.state is BreakerState.CLOSED
    assert (health.error_count, health.consecutive_failures, health.last_error) == (0, 0, None)


@pytest.mark.parametrize(
    ("answer_seconds", "sent"), [(0.5, 9), (1.5, 6), (2.5, 3)], ids=["0.5 s", "1.5 s", "2.5 s"]
)
def test_the_public_pool_case_counts_not_asked_answers_apart_and_its_latency_from_answers_only(
    answer_seconds: float, sent: int
) -> None:
    """Every query sent is answered `answer_seconds` after the pace released it, so that is the
    median latency, however long the query was queued; the queries never sent are counted apart."""
    _, health = run_in_virtual_time(on_the_loops_virtual_time(answer_seconds, asked=[]))
    assert (health.success_count, health.not_asked_count, health.error_count) == (sent, 11 - sent, 0)
    assert health.p50_latency_ms == pytest.approx(answer_seconds * 1000, abs=0.01)


async def test_eleven_queries_on_the_polite_pool_are_all_answered_at_one_and_a_half_seconds() -> None:
    time = VirtualTime()
    asked: list[str] = []
    registry = wrapped_over(time, 1.5, contact_email=CONTACT_EMAIL, asked=asked)

    state = await time.run(fan_out(registry, time, ELEVEN))

    assert asked == [query.query for query in ELEVEN]
    assert all(
        status.response is not None and not status.response.partial for status in state.provider_statuses
    )
    assert search_status(state.provider_statuses) is SearchStatus.COMPLETE
    assert time.seconds_since() == pytest.approx(6.333, abs=0.001)


async def test_a_query_not_asked_on_the_polite_pool_names_its_rate_and_no_cure() -> None:
    time = VirtualTime()
    asked: list[str] = []
    registry = wrapped_over(time, 4.0, contact_email=CONTACT_EMAIL, asked=asked)

    state = await time.run(fan_out(registry, time, ELEVEN))

    errors = {
        status.response.error
        for status in state.provider_statuses
        if status.response and status.response.partial
    }
    assert errors == {"crossref: not asked: the polite pool allows 3 queries a second"}
    assert CONTACT_EMAIL not in json.dumps(
        [status.model_dump(mode="json") for status in state.provider_statuses]
    )


async def test_a_sent_query_that_runs_slow_still_times_out() -> None:
    async def never(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200, json=works())

    factory = crossref_factory(
        HttpSettings(), version=VERSION, clock=FixedClock(), transport=httpx.MockTransport(never)
    )
    registry = ProviderRegistry.from_settings(
        provider_settings(timeout_seconds=0.05), {SearchProviderName.CROSSREF: factory}, clock=FixedClock()
    )
    with pytest.raises(ProviderTimedOut):
        await registry.get("crossref").search(CARBON_CAPTURE)
    (health,) = registry.health()
    assert health.error_count == 1


# --------------------------------------------------------------------------------------------
# Refusals and failures
# --------------------------------------------------------------------------------------------


async def test_a_429_with_retry_after_is_rate_limited_for_that_long() -> None:
    replayed = replay_with_respx(build_over)(recording("works_rate_limited"))
    with pytest.raises(ProviderRateLimited) as caught:
        await replayed.provider.search(CARBON_CAPTURE)
    assert caught.value.retry_after_seconds == 30
    assert len(replayed.sent()) == 1


async def test_a_429_without_retry_after_is_rate_limited_with_no_stated_wait() -> None:
    replayed = replay_with_respx(build_over)(recording("works_rate_limited_without_retry_after"))
    with pytest.raises(ProviderRateLimited) as caught:
        await replayed.provider.search(CARBON_CAPTURE)
    assert caught.value.retry_after_seconds is None
    assert len(replayed.sent()) == 1


async def test_a_403_block_is_a_refusal_that_is_not_retried() -> None:
    replayed = replay_with_respx(build_over)(recording("works_blocked"))
    with pytest.raises(ProviderUnavailable) as caught:
        await replayed.provider.search(CARBON_CAPTURE)
    assert type(caught.value) is ProviderUnavailable
    assert str(caught.value) == "crossref: HTTP 403: the provider refused the request"
    assert len(replayed.sent()) == 1


@pytest.mark.parametrize(
    "document",
    [
        {"status": "ok", "message-type": "work-list", "message": {}},
        {"status": "ok", "message-type": "work-list", "message": {"items": None}},
        {"status": "ok", "message-type": "work-list", "message": {"items": ["10.5555/x"]}},
        {"status": "ok", "message-type": "work", "message": {"items": []}},
        {"status": "failed", "message-type": "work-list", "message": {"items": []}},
        {"status": "ok", "message-type": "work-list", "message": []},
        ["items"],
    ],
    ids=["no items", "null items", "an item not an object", "one work", "not ok", "message a list", "a list"],
)
async def test_a_body_that_is_not_a_work_list_is_unavailable(document: object) -> None:
    router = respx.MockRouter(assert_all_mocked=True)
    router.get(CROSSREF_WORKS_URL).return_value = httpx.Response(200, json=document)
    with pytest.raises(ProviderUnavailable, match="crossref: unreadable response: not a work list"):
        await build_over(httpx.MockTransport(router.async_handler)).search(CARBON_CAPTURE)


async def test_a_body_that_is_not_json_is_unavailable() -> None:
    router = respx.MockRouter(assert_all_mocked=True)
    router.get(CROSSREF_WORKS_URL).return_value = httpx.Response(200, content=b'{"status": "ok", "mess')
    with pytest.raises(ProviderUnavailable, match="crossref: unreadable response: JSONDecodeError"):
        await build_over(httpx.MockTransport(router.async_handler)).search(CARBON_CAPTURE)


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        (httpx.ReadTimeout("timed out"), "crossref: timed out"),
        (httpx.ConnectError("refused"), "crossref: transport failure: ConnectError"),
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
    """The registry's crossref provider, over the named recording, and the registry itself."""
    registries: list[ProviderRegistry] = []

    def build(transport: httpx.AsyncBaseTransport) -> SearchProvider:
        factory = crossref_factory(
            HttpSettings(), version=VERSION, clock=clock, sleep=instant_sleep(clock), transport=transport
        )
        registry = ProviderRegistry.from_settings(
            provider_settings(**overrides), {SearchProviderName.CROSSREF: factory}, clock=clock
        )
        registries.append(registry)
        return registry.get("crossref")

    replayed = replay_with_respx(build)(recording(name))
    return registries[0], replayed


async def test_a_429_holds_crossref_for_its_retry_after_and_one_without_for_the_cooldown() -> None:
    clock = FixedClock()
    held, replayed = registry_over("works_rate_limited", clock)
    with pytest.raises(ProviderRateLimited):
        await replayed.provider.search(CARBON_CAPTURE)
    (health,) = held.health()
    assert health.rate_limited_until == clock.now() + timedelta(seconds=30)

    cooled, replayed = registry_over(
        "works_rate_limited_without_retry_after", clock, breaker_cooldown_seconds=600
    )
    with pytest.raises(ProviderRateLimited):
        await replayed.provider.search(CARBON_CAPTURE)
    (health,) = cooled.health()
    assert health.rate_limited_until == clock.now() + timedelta(seconds=600)


async def test_the_registry_answers_the_recorded_search_through_the_wrapper() -> None:
    _, replayed = registry_over("works_query", FixedClock())
    answer = await replayed.provider.search(recording("works_query").query)
    assert [result.provider_record_id for result in answer.results] == [
        "10.5555/invented.2022.0417",
        "10.5555/invented.report.2021",
        "10.5555/invented.book.2023.ch4",
        "10.5555/invented.preprint.0109",
        "10.5555/invented.proc.2020.11",
    ]


# --------------------------------------------------------------------------------------------
# The contact email never surfaces
# --------------------------------------------------------------------------------------------


@pytest.mark.usefixtures("bare_protected_loggers")
async def test_no_contact_email_reaches_a_log_line_an_error_a_repr_or_a_health_snapshot(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    clock = FixedClock()
    surfaces: list[str] = []
    for name in ("works_query", "works_rate_limited", "works_blocked", "works_empty"):
        registry, replayed = registry_over(name, clock)
        surfaces += [repr(registry), repr(replayed.provider), repr(registry.providers[0])]
        try:
            await replayed.provider.search(recording(name).query)
        except (ProviderRateLimited, ProviderUnavailable) as error:
            surfaces += [str(error), repr(error), str(error.__cause__), repr(error.__cause__)]
        surfaces += [snapshot.model_dump_json() for snapshot in registry.health()]
    logger.warning("adapter state: contact=%s", CONTACT_EMAIL)
    surfaces += [record.getMessage() for record in caplog.records]

    encoded = CONTACT_EMAIL.replace("@", "%40")
    assert any("HTTP Request: GET https://api.crossref.org/works" in text for text in surfaces)
    assert any("adapter state: contact=***" in text for text in surfaces)
    assert not [text for text in surfaces if CONTACT_EMAIL in text or encoded in text]


@pytest.mark.usefixtures("bare_protected_loggers")
@pytest.mark.parametrize("logger_name", PROTECTED_LOGGERS)
def test_the_adapter_alone_protects_the_logs_from_its_contact_email(
    logger_name: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Unwrapped, as the kit runs it: the constructor registers the address, so no log line carries it."""
    caplog.set_level(logging.DEBUG)
    address = "crossref-unwrapped@example.org"
    build_over(httpx.MockTransport(lambda request: httpx.Response(200)), contact_email=address)

    logging.getLogger(logger_name).warning("GET /works?mailto=%s User-Agent mailto:%s", address, address)

    assert [record.getMessage() for record in caplog.records] == [
        "GET /works?mailto=*** User-Agent mailto:***"
    ]


def test_the_repr_says_which_pool_and_whether_an_address_is_configured() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200))
    assert repr(build_over(transport)) == "CrossrefProvider(contact_email=configured, pool=polite)"
    assert (
        repr(build_over(transport, contact_email=None)) == "CrossrefProvider(contact_email=none, pool=public)"
    )


# --------------------------------------------------------------------------------------------
# The shared contract kit
# --------------------------------------------------------------------------------------------


class TestCrossrefProviderOnThePolitePool(SearchProviderContract):
    """Crossref with a contact email, on the recorded carbon capture search."""

    @pytest.fixture
    def recording(self) -> Recording:
        return recording("works_query")

    @pytest.fixture
    def replay(self) -> ReplayFactory:
        return replay_with_respx(build_over)

    @pytest.fixture
    def secrets(self) -> tuple[str, ...]:
        return (CONTACT_EMAIL,)

    @pytest.fixture
    def max_attempts(self) -> int:
        """The adapter never retries: one request per search."""
        return 1


class TestCrossrefProviderOnThePublicPool(TestCrossrefProviderOnThePolitePool):
    """No contact email: the same answer to the same search sent without `mailto=`."""

    @pytest.fixture
    def recording(self) -> Recording:
        return without_mailto(recording("works_query"))

    @pytest.fixture
    def replay(self) -> ReplayFactory:
        return replay_with_respx(lambda transport: build_over(transport, contact_email=None))

    @pytest.fixture
    def secrets(self) -> tuple[str, ...]:
        return ()


class TestCrossrefProviderOnAnEmptyResult(TestCrossrefProviderOnThePolitePool):
    """A search Crossref has nothing for."""

    @pytest.fixture
    def recording(self) -> Recording:
        return recording("works_empty")
