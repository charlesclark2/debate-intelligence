"""`debate-research search`, offline, through Typer's runner, the real app and the real composition root.

Everything below the providers is the production wiring (`v1-e08-t05`): the container's
FederatedSearchService with the expansion stage over the committed taxonomy, DedupeStage, the rank
stage over the committed weight table, Article matching, and the SQLite file in a data directory of
each test's own. The providers are the real OpenAlex and feed adapters, each wrapped in the real
ResilientProvider, in a ProviderRegistry the test registers under `discovery_providers` (the
registry override): their HTTP goes to :class:`RecordedProviders`, which answers from the recorded
bodies in `fixtures/search/` and sends nothing. One test instead registers only the transport, under
`discovery_transport`, so that the container builds the registry itself from settings. The same
transport is the article fetcher's (`article_fetch_transport`), so a fetch that should never happen
would be recorded and refused rather than reach the network.

Expected rows, footers and queries are written by hand from the fixtures (working agreement 6;
`fixtures/search/README.md` says what each body holds).
"""

from __future__ import annotations

import asyncio
import gc
import heapq
import io
import itertools
import json
import os
import sqlite3
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

import docx
import httpx
import pytest
from pydantic import BaseModel
from tests.fixtures.card.every_page_router import EVERY_PAGE_TAG, EveryPageRouter
from tests.fixtures.citation.citation_world import JOURNAL_DOI, CrossrefAnswers
from tests.fixtures.http.cassettes import ReplayTransport, cassette_names, load_cassette
from tests.fixtures.model_routing import EXAMPLE_ROUTING_FILE
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.commands import search as search_command
from debate_cli.container import ServiceContainer
from debate_cli.exit_codes import ExitCode, exit_code_for, exit_code_for_search
from debate_core.application.budget import BudgetExceededError, UnpricedModelError
from debate_core.application.errors import ProviderUnavailable
from debate_core.application.federated_search_types import SearchOutcome
from debate_core.application.ports.model_router import ModelRouter
from debate_core.application.query_expansion import EXPAND_PROMPT_ID, UnknownExpansionChoice
from debate_core.application.settings import HttpSettings, ProviderSettings, SearchProviderName, Settings
from debate_core.domain import AccessStatus, Article, Search, SearchStatus
from debate_core.domain.model_contracts import (
    EmbeddingResponse,
    ModelParams,
    ModelPrompt,
    ModelProvider,
    ModelResponse,
    ModelUsage,
    RerankResponse,
    TaskClass,
)
from debate_core.evidence.docx_manifest_part import read_embedded_manifest_bytes

# Imported here, before pytest-socket is armed: urllib3 (through trafilatura) probes for IPv6 with a
# socket when it is first imported, which `--auto-cut`'s article fetch would otherwise do inside a test.
# The Bedrock module (boto3) likewise, whose router factory the one-limit tests stand in for.
from debate_core.integrations import bedrock
from debate_core.integrations import html_extractor as html_extractor
from debate_core.integrations.discovery import crossref as crossref_discovery
from debate_core.integrations.discovery.feed_cache import InMemoryFeedCache
from debate_core.integrations.discovery.feed_config import FeedConfig, FeedReview, FeedSource
from debate_core.integrations.discovery.feeds import feed_factory
from debate_core.integrations.discovery.openalex import openalex_factory
from debate_core.integrations.discovery.registry import ProviderRegistry
from debate_core.integrations.local import SqliteArticleRepository, SqliteDatabase
from debate_core.integrations.models.factory import RealRouterFactory
from debate_core.integrations.models.prompt_registry import PromptRegistry
from debate_core.integrations.models.routing_policy import RoutingPolicy
from debate_core.retrieval import canonicalize_url
from debate_core.testing.fakes.clock_and_ids import FixedClock
from debate_core.testing.fakes.model_router import ScriptedModelRouter
from debate_core.testing.virtual_time import run_in_virtual_time

runner = CliRunner()

FIXTURES: Final = Path(__file__).resolve().parent / "fixtures" / "search"

NOW: Final = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
"""The container's clock, and the providers': after every fixture item, so recency is counted from it."""

OPENALEX_HOST: Final = "api.openalex.org"
CROSSREF_HOST: Final = "api.crossref.org"
CROSSREF_WORKS: Final = {
    "status": "ok",
    "message-type": "work-list",
    "message": {
        "items": [
            {
                "DOI": "10.5555/invented.report.2021",
                "type": "report",
                "title": ["Subsidy design for capture plants"],
                "author": [{"name": "Invented Energy Institute", "sequence": "first"}],
                "issued": {"date-parts": [[2021]]},
            }
        ]
    },
}
"""One Crossref item, written by hand: a report dated by its year alone (v1-e07-t03)."""
SEMANTIC_SCHOLAR_HOST: Final = "api.semanticscholar.org"
SEMANTIC_SCHOLAR_PAPERS: Final = {
    "total": 1,
    "offset": 0,
    "data": [
        {
            "paperId": "c0ffee00c0ffee00c0ffee00c0ffee00c0ffee00",
            "title": "Who captures the subsidy?",
            "authors": [{"authorId": None, "name": "Rasmus Kettleby"}],
            "year": 2021,
            "publicationDate": None,
            "externalIds": {"ArXiv": "2111.04567", "CorpusId": 244012345},
            "isOpenAccess": True,
            "openAccessPdf": {"url": "https://arxiv.org/pdf/2111.04567", "status": "GREEN"},
            "publicationTypes": None,
        }
    ],
}
"""One Semantic Scholar paper, written by hand: no DOI, dated by its year alone (v1-e07-t04)."""
SEMANTIC_SCHOLAR_KEY: Final = "ss-K3y-7Qd2"
FEDERAL_REGISTER_HOST: Final = "www.federalregister.gov"
FEDERAL_REGISTER_DOCUMENTS: Final = {
    "count": 1,
    "results": [
        {
            "document_number": "2026-90401",
            "title": "Invented Coverage Standards for Marketplace Plans",
            "publication_date": "2026-05-04",
            "agency_names": ["Centers for Medicare & Medicaid Services"],
            "html_url": "https://www.federalregister.gov/documents/2026/05/04/2026-90401/invented-coverage-standards",
        }
    ],
}
"""One Federal Register document, written by hand with an invented number (v1-e07-t07)."""
GOVINFO_HOST: Final = "api.govinfo.gov"
GOVINFO_RESULTS: Final = {
    "count": 1,
    "offsetMark": None,
    "results": [
        {
            "title": "Invented Hearing on Coverage for Rural Families",
            "packageId": "CHRG-119shrg58999",
            "governmentAuthor": ["Congress. Senate. Committee on Finance"],
            "dateIssued": "2026-03",
            "collectionCode": "CHRG",
        }
    ],
}
"""One GovInfo hearing, written by hand with an invented package id (v1-e07-t07)."""
DATA_GOV_KEY: Final = "datagov-cli-K1"
FEED_URL: Final = "https://news.example.org/rss/politics.xml"
TOPICS: Final = (
    FeedConfig(
        topic="politics",
        description="The test's one topic.",
        feeds=(
            FeedSource(
                url=FEED_URL, publisher="The Example Courier", review=FeedReview.AWAITING_COACH_REVIEW
            ),
        ),
    ),
)

MIDTERM_ROWS: Final = {
    "Midterm elections and the partisan fight over health insurance",
    "Turnout in the 2026 midterm elections",
    "Political capital and health insurance reform",
    "Midterm elections tighten as health insurance costs rise",
}
"""`midterm elections --since 2026-09-14`: OpenAlex's three works, and the two Courier items that match
inside the window, of which the turnout item is the second work's URL: four sources."""

NOT_SHOWN: Final = ("summer primaries", "Weekend weather", "fight costs the president")
"""Courier items the `midterm elections` search must not show: before the window, or not matching."""

POLITICS_LINK_QUERIES: Final = [
    "health insurance political capital",
    "health insurance partisan fight Congress",
    "health insurance unpopular with voters",
    "health insurance popular with Republicans",
    "health insurance unpopular with Republicans",
    "health insurance popular with Democrats",
    "health insurance unpopular with Democrats",
]
"""The politics DA's seven link templates in `config/argument_taxonomy.yaml` 1.1.0, for `health insurance`."""

FEATURES: Final = [
    "bm25",
    "recency",
    "source_type",
    "peer_reviewed",
    "open_access",
    "citations",
    "provider_agreement",
]

TURNOUT_URL: Final = "https://www.policycenter.example/research/midterm-turnout-2026"

SENTINELS: Final = ("ABSTRACTSENTINEL", "SNIPPETSENTINEL")
"""Words only in an abstract and a feed item's description: text a search never prints."""

EVERY_FLAG: Final = [
    "--since",
    "--until",
    "--max-results",
    "--argument",
    "--need",
    "--topic",
    "--var",
    "--providers",
    "--expand-llm",
    "--format",
    "--save",
    "--json",
]


class _NowClock:
    def now(self) -> datetime:
        return NOW


class CountingTransport(httpx.MockTransport):
    """A mock transport that counts how often a client closes it: once per provider's client."""

    def __init__(self, handler: Any) -> None:
        super().__init__(handler)
        self.closed = 0

    async def aclose(self) -> None:
        self.closed += 1


@dataclass
class RecordedProviders:
    """The recorded answers every provider's HTTP gets, and every request it sent."""

    works_body: str = "openalex_works.body.json"
    openalex_status: int = 200
    openalex_delay_seconds: float = 0.0
    feed_status: int = 200
    any_feed_url: bool = False
    """Serve the Courier feed for every non-OpenAlex URL: the committed `config/feeds/` lists."""
    timeout_seconds: float = 10.0
    requests: list[httpx.Request] = field(default_factory=list[httpx.Request])
    unrecorded: list[str] = field(default_factory=list[str])
    transport: CountingTransport = field(init=False)

    def __post_init__(self) -> None:
        self.transport = CountingTransport(self.handle)

    async def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host == OPENALEX_HOST and request.url.path == "/works":
            if self.openalex_delay_seconds:
                await asyncio.sleep(self.openalex_delay_seconds)
            if self.openalex_status != 200:
                return httpx.Response(self.openalex_status)
            body = (FIXTURES / self.works_body).read_bytes()
            return httpx.Response(200, headers={"content-type": "application/json"}, content=body)
        if request.url.host == CROSSREF_HOST and request.url.path == "/works":
            return httpx.Response(200, json=CROSSREF_WORKS)
        if request.url.host == SEMANTIC_SCHOLAR_HOST and request.url.path == "/graph/v1/paper/search":
            return httpx.Response(200, json=SEMANTIC_SCHOLAR_PAPERS)
        if request.url.host == FEDERAL_REGISTER_HOST and request.url.path == "/api/v1/documents.json":
            return httpx.Response(200, json=FEDERAL_REGISTER_DOCUMENTS)
        if request.url.host == GOVINFO_HOST and request.url.path == "/search" and request.method == "POST":
            return httpx.Response(200, json=GOVINFO_RESULTS)
        if str(request.url) == FEED_URL or (self.any_feed_url and request.url.host != OPENALEX_HOST):
            if self.feed_status != 200:
                return httpx.Response(self.feed_status)
            body = (FIXTURES / "courier_politics.xml").read_bytes()
            return httpx.Response(200, headers={"content-type": "application/rss+xml"}, content=body)
        self.unrecorded.append(str(request.url))
        return httpx.Response(599)

    def openalex_queries(self) -> list[str]:
        return [
            request.url.params["search"] for request in self.requests if request.url.host == OPENALEX_HOST
        ]

    def registry(self) -> ProviderRegistry:
        """OpenAlex and the Courier feed: real adapters over this transport, wrapped, as in production."""
        clock = _NowClock()
        http = HttpSettings()
        factories = {
            SearchProviderName.OPENALEX: openalex_factory(
                http, version="test", clock=clock, transport=self.transport
            ),
            SearchProviderName.RSS: feed_factory(
                http,
                version="test",
                clock=clock,
                topics=TOPICS,
                cache=InMemoryFeedCache(),
                transport=self.transport,
            ),
        }
        settings = ProviderSettings(
            enabled=(SearchProviderName.OPENALEX, SearchProviderName.RSS),
            timeout_seconds=self.timeout_seconds,
        )
        return ProviderRegistry.from_settings(settings, factories, clock=clock)


@dataclass
class Seams:
    """What every container the app builds is given in place of the network and the model."""

    providers: RecordedProviders = field(default_factory=RecordedProviders)
    registry_override: bool = True
    """Register a whole registry (`discovery_providers`); otherwise only the transport."""
    router: ScriptedModelRouter = field(default_factory=ScriptedModelRouter)
    """The `search.expand` router: no scripted answer, so a call it was not given one for fails."""
    articles: ReplayTransport | None = None
    """`--auto-cut`'s article fetches, from the HTTP cassettes; otherwise the providers' transport,
    which refuses them."""
    card_router: ModelRouter | None = None
    """`--auto-cut`'s `card.select` and `card.markup` calls; with it, Crossref is answered too."""
    live_models: Callable[[Settings], Settings] | None = None
    """Turns the profile's settings into a live run's: then the container builds every model router
    itself, through the budget guard and the usage log, over the `bedrock_router_factory` a test
    stands in for; Crossref is answered too."""
    crossref: CrossrefAnswers = field(default_factory=CrossrefAnswers)
    containers: list[ServiceContainer] = field(default_factory=list[ServiceContainer])
    """Every container the app built, for a test that reads the settings a command left in one."""


@pytest.fixture
def seams(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Seams]:
    for name in [name for name in os.environ if name.startswith("DEBATE_")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("DEBATE_ENV", "test")
    monkeypatch.setenv("DEBATE_STORAGE__DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("COLUMNS", "250")
    monkeypatch.setenv("DEBATE_HTTP__PER_HOST_INTERVAL_SECONDS", "0")
    seams = Seams()
    build = ServiceContainer.__init__

    def with_seams(self: ServiceContainer, **arguments: Any) -> None:
        build(self, **arguments)
        self.override("clock", lambda: NOW)
        if seams.live_models is None:
            self.override("search_model_router", seams.router)
        else:
            self.override("settings", seams.live_models(self.settings))
        # Nothing a search does fetches an article; if anything tried, its request would land here,
        # be refused and be named by the fixture's last check.
        self.override("article_fetch_transport", seams.articles or seams.providers.transport)
        if seams.card_router is not None:
            self.override("card_model_router", seams.card_router)
        if seams.card_router is not None or seams.live_models is not None:
            self.override("crossref_transport", httpx.MockTransport(seams.crossref.handle))
        seams.containers.append(self)
        if seams.registry_override:
            self.override("discovery_providers", seams.providers.registry())
        else:
            self.override("discovery_transport", seams.providers.transport)

    monkeypatch.setattr(ServiceContainer, "__init__", with_seams)
    yield seams
    assert seams.providers.unrecorded == [], "a request no fixture recorded"
    if seams.articles is not None:
        assert seams.articles.unrecorded == [], "an article fetch no cassette recorded"


@pytest.fixture
def on_virtual_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the command's event loop on virtual time (`VirtualTimeEventLoop`), through the command's own
    `_run`: the providers' timeouts, the search's deadline and any `asyncio.sleep` a recorded answer takes
    are measured on a clock that moves only while every task waits, so a busy runner cannot spend them."""
    monkeypatch.setattr(search_command, "_run", run_in_virtual_time)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


def search(*arguments: str, json_output: bool = False) -> Result:
    return runner.invoke(create_app(), [*(["--json"] if json_output else []), "search", *arguments])


def envelope(result: Result) -> dict[str, Any]:
    lines = result.stdout.splitlines()
    assert len(lines) == 1, f"JSON output must be exactly one line on stdout, got: {result.stdout!r}"
    document: dict[str, Any] = json.loads(lines[0])
    return document


def footer(result: Result, *, stream: str = "stdout") -> list[str]:
    """The provider status footer: every line from `Providers:` on, on stdout below the table, or on
    stderr above the failure panel when there are no rows to show."""
    lines = (result.stdout if stream == "stdout" else result.stderr).splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith("Providers:"))
    return lines[start:]


def rows(data: dict[str, Any]) -> list[str]:
    return [item["title"] for item in data["results"]]


def stored(data_dir: Path, sql: str) -> list[tuple[Any, ...]]:
    gc.collect()
    database = data_dir / "debate.sqlite3"
    if not database.exists():
        return []
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        return list(connection.execute(sql))


def seed_article(data_dir: Path, url: str, status: AccessStatus) -> str:
    """Store an Article for `url` before the search, as an earlier `fetch` would have."""
    article = Article(
        article_id="01JSEEDEDART00000000000001",
        canonical_url=canonicalize_url(url),
        title="An earlier fetch's title",
        access_status=status,
        created_at=NOW,
        updated_at=NOW,
    )

    async def save() -> None:
        await SqliteArticleRepository(SqliteDatabase.open(data_dir)).save(article)

    asyncio.run(save())
    gc.collect()
    return article.article_id


# ------------------------------------------------------------------------------------------------
# Presenters: the table, the footer and the JSON
# ------------------------------------------------------------------------------------------------


def test_presenter_table_shows_ranked_deduplicated_rows_and_the_provider_footer(seams: Seams) -> None:
    result = search("midterm elections", "--since", "2026-09-14", "--max-results", "20")

    assert result.exit_code == ExitCode.OK, result.output
    shown = [title for title in MIDTERM_ROWS if title in result.stdout]
    assert sorted(shown) == sorted(MIDTERM_ROWS)
    assert result.stdout.count("Turnout in the 2026 midterm elections") == 1
    assert not [text for text in NOT_SHOWN if text in result.stdout]
    assert '4 results for "midterm elections"' in result.stdout
    for column in ("Rank", "Title", "Publisher / venue", "Date", "Type", "Access", "Why"):
        assert column in result.stdout
    assert footer(result) == ["Providers: COMPLETE", "  openalex: ok, 3 results", "  rss: ok, 2 results"]


def test_presenter_max_results_caps_the_rows(seams: Seams) -> None:
    result = search("midterm elections", "--since", "2026-09-14", "--max-results", "2", "--format", "json")

    assert result.exit_code == ExitCode.OK, result.output
    data = envelope(result)["data"]
    assert [item["rank"] for item in data["results"]] == [1, 2]


def test_presenter_json_items_carry_rank_score_features_explanation_identifiers_and_sources(
    seams: Seams,
) -> None:
    result = search("health insurance", "--argument", "politics-da", "--need", "link", "--format", "json")

    assert result.exit_code == ExitCode.OK, result.output
    document = envelope(result)
    assert (document["status"], document["command"]) == ("ok", "search")
    data = document["data"]
    assert sorted(rows(data)) == sorted(
        [
            "Midterm elections and the partisan fight over health insurance",
            "Turnout in the 2026 midterm elections",
            "Political capital and health insurance reform",
            "Health insurance fight costs the president political capital",
        ]
    )
    for position, item in enumerate(data["results"], start=1):
        assert item["rank"] == position
        assert isinstance(item["score"], float)
        assert list(item["features"]) == FEATURES
        assert item["explanation"]
        assert set(item["identifiers"]) >= {"doi", "openalex_id"}
        assert item["providers"]
    by_title = {item["title"]: item for item in data["results"]}
    assert by_title["Turnout in the 2026 midterm elections"]["identifiers"]["openalex_id"] == "W4410000002"
    assert by_title["Health insurance fight costs the president political capital"]["providers"] == ["rss"]
    assert by_title["Midterm elections and the partisan fight over health insurance"]["identifiers"][
        "doi"
    ] == ("10.5555/ipr.2026.0031")
    assert data["expansion"]["argument"] == "politics-da"
    assert data["expansion"]["need"] == "link"
    assert [query["query"] for query in data["expansion"]["queries"]] == POLITICS_LINK_QUERIES
    assert seams.providers.openalex_queries() == [joined(*POLITICS_LINK_QUERIES)]
    assert [(entry["provider"], entry["outcome"]) for entry in data["providers"]] == [
        ("openalex", "ok"),
        ("rss", "ok"),
    ]


def test_an_expanded_search_reads_each_feed_once_however_many_queries_it_asks(seams: Seams) -> None:
    """v1-e08-t10: the politics DA's seven link queries make one OpenAlex request and read the Courier
    feed once, not seven times each, and
    each query still has its own record: only the first template's words are all in the one item that
    matches ("Health insurance fight costs the president political capital")."""
    result = search("health insurance", "--argument", "politics-da", "--need", "link", "--format", "json")

    assert result.exit_code == ExitCode.OK, result.output
    assert [str(request.url) for request in seams.providers.requests].count(FEED_URL) == 1
    assert seams.providers.openalex_queries() == [joined(*POLITICS_LINK_QUERIES)]
    data = envelope(result)["data"]
    rss_calls = [call for call in data["provider_calls"] if call["provider"] == "rss"]
    assert [(call["query"], call["outcome"], call["results"]) for call in rss_calls] == [
        (query, "ok", 1 if position == 0 else 0) for position, query in enumerate(POLITICS_LINK_QUERIES)
    ]
    assert footer_of(data, "rss") == {"outcome": "ok", "queries": 7, "failed": 0, "results": 1}


def joined(*queries: str) -> str:
    """One OpenAlex search for several queries: each in parentheses, joined by OR (v1-e08-t10)."""
    return " OR ".join(f"({query})" for query in queries)


def footer_of(data: dict[str, Any], provider: str) -> dict[str, Any]:
    [entry] = [entry for entry in data["providers"] if entry["provider"] == provider]
    return {key: entry[key] for key in ("outcome", "queries", "failed", "results")}


def test_presenter_json_gives_each_result_its_place_in_raw_provider_order(seams: Seams) -> None:
    result = search("midterm elections", "--since", "2026-09-14", "--format", "json")

    assert result.exit_code == ExitCode.OK, result.output
    places = {item["title"]: item["provider_order"] for item in envelope(result)["data"]["results"]}
    # Fan-out order is OpenAlex's three works, then the Courier's two matching items, of which the
    # turnout item is the second work: it keeps the work's place.
    assert places == {
        "Midterm elections and the partisan fight over health insurance": 1,
        "Turnout in the 2026 midterm elections": 2,
        "Political capital and health insurance reform": 3,
        "Midterm elections tighten as health insurance costs rise": 4,
    }


def test_presenter_json_puts_only_the_envelope_on_stdout_and_progress_on_stderr(seams: Seams) -> None:
    result = search("midterm elections", "--since", "2026-09-14", "--json")

    assert result.exit_code == ExitCode.OK, result.output
    assert envelope(result)["status"] == "ok"
    events = [json.loads(line)["event"] for line in result.stderr.splitlines() if line.startswith("{")]
    assert events == ["searching", "searched"]


def test_presenter_never_prints_an_abstract_or_a_feed_description(seams: Seams) -> None:
    table = search("midterm elections", "--since", "2026-09-14")
    as_json = search("midterm elections", "--since", "2026-09-14", "--format", "json")

    for result in (table, as_json):
        assert result.exit_code == ExitCode.OK, result.output
        assert not [word for word in SENTINELS if word in result.stdout + result.stderr]
    assert all("snippet" not in item for item in envelope(as_json)["data"]["results"])


# ------------------------------------------------------------------------------------------------
# Partial, empty and failed searches
# ------------------------------------------------------------------------------------------------


def test_a_provider_that_times_out_makes_the_results_partial_and_exits_6(
    seams: Seams, on_virtual_time: None
) -> None:
    """OpenAlex answers after 5 seconds and the providers' timeout is 0.2, so OpenAlex times out and the
    feed, which answers at once, is the search's two results. On virtual time: on the wall clock a runner
    busy for 0.2 seconds timed the feed out too, and the search failed with exit 3 (v1-e07-t16)."""
    seams.providers.timeout_seconds = 0.2
    seams.providers.openalex_delay_seconds = 5.0

    result = search("midterm elections", "--since", "2026-09-14")

    assert result.exit_code == ExitCode.SEARCH_PARTIAL == 6, result.output
    assert 'PARTIAL: 2 results for "midterm elections"' in result.stdout
    assert footer(result) == [
        "Providers: PARTIAL, results may be missing",
        "  openalex: timeout: no answer within 0.2s",
        "  rss: ok, 2 results",
    ]
    assert "SEARCH_PARTIAL" in result.stderr


def test_a_partial_search_in_json_carries_its_results_and_the_failed_provider(
    seams: Seams, on_virtual_time: None
) -> None:
    """The timeout above, in JSON, on virtual time for the same reason."""
    seams.providers.timeout_seconds = 0.2
    seams.providers.openalex_delay_seconds = 5.0

    result = search("midterm elections", "--since", "2026-09-14", "--format", "json")

    assert result.exit_code == ExitCode.SEARCH_PARTIAL, result.output
    error = envelope(result)["error"]
    assert (error["code"], error["exit_code"]) == ("SEARCH_PARTIAL", 6)
    assert sorted(rows(error["details"])) == [
        "Midterm elections tighten as health insurance costs rise",
        "Policy Center: turnout in the 2026 midterm elections",
    ]
    openalex = next(entry for entry in error["details"]["providers"] if entry["provider"] == "openalex")
    assert (openalex["outcome"], openalex["reasons"]) == ("timeout", ["no answer within 0.2s"])


def test_every_provider_answering_with_nothing_exits_7(seams: Seams) -> None:
    seams.providers.works_body = "openalex_empty.body.json"

    result = search("zebra migration", "--format", "json")

    assert result.exit_code == ExitCode.NO_RESULTS == 7, result.output
    error = envelope(result)["error"]
    assert (error["code"], error["exit_code"], error["details"]["results"]) == ("NO_RESULTS", 7, [])


def test_every_provider_failing_exits_3(seams: Seams) -> None:
    seams.providers.openalex_status = 503
    seams.providers.feed_status = 503

    result = search("midterm elections")

    assert result.exit_code == ExitCode.RETRIEVAL_FAILURE == 3, result.output
    assert "SEARCH_FAILED" in result.stderr
    lines = footer(result, stream="stderr")
    assert lines[:3] == ["Providers: FAILED", "  openalex: error: HTTP 503", "  rss: error: HTTP 503"]


def test_a_provider_that_is_not_enabled_is_named_in_the_footer_and_the_search_is_partial(
    seams: Seams,
) -> None:
    result = search("midterm elections", "--since", "2026-09-14", "--providers", "openalex,semantic_scholar")

    assert result.exit_code == ExitCode.SEARCH_PARTIAL, result.output
    assert footer(result) == [
        "Providers: PARTIAL, results may be missing",
        "  openalex: ok, 3 results",
        "  semantic_scholar: not configured: not enabled in settings (providers.enabled)",
    ]


def test_a_search_that_asks_no_enabled_provider_exits_1(seams: Seams) -> None:
    result = search("midterm elections", "--providers", "semantic_scholar", "--format", "json")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    assert envelope(result)["error"]["code"] == "NO_PROVIDER_ENABLED"
    assert seams.providers.requests == []


# ------------------------------------------------------------------------------------------------
# Usage errors and --help
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("arguments", "listed"),
    [
        (["--argument", "nonsense-da", "--need", "link"], "politics-da"),
        (["--argument", "politics-da", "--need", "evidence"], "internal-link"),
        (["--argument", "politics-da", "--need", "link", "--topic", "no-such-topic"], "policy-2026-27-nhi"),
        (["--argument", "politics-da", "--need", "link", "--var", "senator=Smith"], "bill"),
    ],
)
def test_an_unknown_expansion_choice_exits_2_listing_the_valid_ones(
    seams: Seams, arguments: list[str], listed: str
) -> None:
    result = search("health insurance", *arguments)

    assert result.exit_code == ExitCode.USAGE_ERROR == 2, result.output
    assert listed in result.stderr
    assert seams.providers.requests == []


@pytest.mark.parametrize(
    ("argument", "need", "listed", "not_listed"),
    [
        ("util", "uniqueness", ["framework-good", "answers"], "internal-link"),
        ("theory", "impact", ["interpretation", "standards", "voters", "answers"], "uniqueness"),
        ("process-cp", "link", ["solvency", "net-benefit", "competition", "answers"], "uniqueness"),
        ("cap-k", "solvency", ["link", "impact", "alternative", "framework", "answers"], "net-benefit"),
        (
            "politics-da",
            "alternative",
            ["uniqueness", "link", "internal-link", "impact", "answers"],
            "solvency",
        ),
    ],
)
def test_a_need_outside_the_arguments_family_exits_2_listing_that_arguments_needs(
    seams: Seams, argument: str, need: str, listed: list[str], not_listed: str
) -> None:
    """v1-e08-t08: each argument family has its own needs, and `--need` is read within its argument's."""
    result = search("health insurance", "--argument", argument, "--need", need)

    assert result.exit_code == ExitCode.USAGE_ERROR == 2, result.output
    said = " ".join(result.stderr.replace("│", " ").split())
    assert f"{argument} has no need '{need}'; its needs are: {', '.join(listed)}" in said
    assert not_listed not in said
    assert seams.providers.requests == []


@pytest.mark.parametrize(
    ("argument", "need", "expanded_need", "windowed"),
    [
        ("util", "framework good", "framework-good", False),
        ("states-cp", "NB", "net-benefit", True),
        ("cap-k", "alt", "alternative", False),
    ],
)
def test_each_familys_own_need_expands_before_any_provider_is_asked(
    seams: Seams, argument: str, need: str, expanded_need: str, windowed: bool
) -> None:
    """Asked only of a provider that is not enabled, the search stops after expanding: exit 1 with the
    expansion under `error.details`, and no request sent."""
    result = search(
        "health insurance",
        "--argument",
        argument,
        "--need",
        need,
        "--providers",
        "semantic_scholar",
        json_output=True,
    )

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    expansion = envelope(result)["error"]["details"]["expansion"]
    assert (expansion["argument"], expansion["need"]) == (argument, expanded_need)
    assert expansion["queries"]
    assert all((query["since"] is not None) is windowed for query in expansion["queries"])
    assert seams.providers.requests == []


@pytest.mark.parametrize(
    ("arguments", "said"),
    [
        (["--since", "2026-10-01", "--until", "2026-09-01"], "after --until"),
        (["--need", "link"], "--argument"),
        (["--argument", "politics-da"], "--need"),
        (["--expand-llm"], "--argument"),
        (["--argument", "politics-da", "--need", "link", "--var", "bill"], "NAME=VALUE"),
        (["--argument", "politics-da", "--need", "link", "--var", "query=x"], "query"),
        (["--providers", "openalex,bing"], "semantic_scholar"),
        (["--since", "October 1"], "--since"),
        (["--max-results", "0"], "--max-results"),
    ],
)
def test_a_wrong_command_line_exits_2_and_searches_nothing(
    seams: Seams, arguments: list[str], said: str
) -> None:
    result = search("health insurance", *arguments)

    assert result.exit_code == ExitCode.USAGE_ERROR, result.output
    assert said in " ".join(result.stderr.split())
    assert seams.providers.requests == []


def test_help_documents_every_flag() -> None:
    result = runner.invoke(create_app(), ["search", "--help"], env={"COLUMNS": "250"})

    assert result.exit_code == ExitCode.OK, result.output
    assert [flag for flag in EVERY_FLAG if flag not in result.stdout] == []


# ------------------------------------------------------------------------------------------------
# Article matching and what is stored
# ------------------------------------------------------------------------------------------------


def test_ranked_candidates_become_stored_results_through_articles_without_a_fetch(
    seams: Seams, data_dir: Path
) -> None:
    seeded = seed_article(data_dir, TURNOUT_URL, AccessStatus.ACCESSIBLE)

    result = search("midterm elections", "--since", "2026-09-14", "--format", "json")

    assert result.exit_code == ExitCode.OK, result.output
    data = envelope(result)["data"]
    by_title = {item["title"]: item for item in data["results"]}
    turnout = by_title["Turnout in the 2026 midterm elections"]
    assert (turnout["article_id"], turnout["access_status"]) == (seeded, "ACCESSIBLE")
    assert turnout["providers"] == ["openalex", "rss"]
    others = [item for title, item in by_title.items() if title != "Turnout in the 2026 midterm elections"]
    assert [item["access_status"] for item in others] == ["UNKNOWN"] * 3

    articles = stored(data_dir, "SELECT article_id, document FROM articles")
    assert len(articles) == 4
    statuses = {article_id: json.loads(document)["access_status"] for article_id, document in articles}
    assert statuses[seeded] == "ACCESSIBLE"
    assert (
        sorted(status for article_id, status in statuses.items() if article_id != seeded) == ["UNKNOWN"] * 3
    )
    assert stored(data_dir, "SELECT count(*) FROM source_snapshots") == [(0,)]

    results = stored(data_dir, "SELECT article_id, rank FROM search_results ORDER BY rank")
    assert [rank for _, rank in results] == [item["rank"] for item in data["results"]]
    assert [article_id for article_id, _ in results] == [item["article_id"] for item in data["results"]]
    fetched = {request.url.host for request in seams.providers.requests}
    assert fetched == {OPENALEX_HOST, "news.example.org"}


def test_the_stored_search_records_its_expansion(seams: Seams, data_dir: Path) -> None:
    result = search("health insurance", "--argument", "ptx", "--need", "l", "--format", "json")

    assert result.exit_code == ExitCode.OK, result.output
    search_id = envelope(result)["data"]["search_id"]
    [(document,)] = stored(data_dir, f"SELECT document FROM searches WHERE search_id = '{search_id}'")  # noqa: S608
    expansion = json.loads(document)["expansion"]
    assert (expansion["argument"], expansion["need"], expansion["model_requested"]) == (
        "politics-da",
        "link",
        False,
    )


def test_a_da_link_search_on_the_nhi_topic_asks_openalex_its_links_then_the_chosen_crossing(
    seams: Seams,
) -> None:
    """v1-e08-t16, the PM's ruling after the coach's answers: the politics DA's seven reviewed link
    queries as they are, then the coach's own wording and templates 2, 4, 5, 6 and 7, each on the
    resolution's words and each of the four mechanisms, naming the United States. The 37 go to OpenAlex
    joined (v1-e08-t10) in two requests: OpenAlex refuses a search over 1,500 characters, and the first 24
    are 1,473 of them, the first 25 1,536 (the operator's measurement, v1-e08-t20, 2026-11-12)."""
    result = search(
        "national health insurance",
        "--argument",
        "politics-da",
        "--need",
        "link",
        "--topic",
        "policy-2026-27-nhi",
        "--format",
        "json",
    )

    assert result.exit_code == ExitCode.OK, result.output
    assert seams.providers.openalex_queries() == [
        joined(
            "national health insurance political capital",
            "national health insurance partisan fight Congress",
            "national health insurance unpopular with voters",
            "national health insurance popular with Republicans",
            "national health insurance unpopular with Republicans",
            "national health insurance popular with Democrats",
            "national health insurance unpopular with Democrats",
            "national health insurance costs political capital Congress United States",
            "single payer costs political capital Congress United States",
            "Medicare for All costs political capital Congress United States",
            "public option costs political capital Congress United States",
            "Affordable Care Act costs political capital Congress United States",
            "national health insurance partisan fight Congress United States",
            "single payer partisan fight Congress United States",
            "Medicare for All partisan fight Congress United States",
            "public option partisan fight Congress United States",
            "Affordable Care Act partisan fight Congress United States",
            "national health insurance popular with Republicans United States",
            "single payer popular with Republicans United States",
            "Medicare for All popular with Republicans United States",
            "public option popular with Republicans United States",
            "Affordable Care Act popular with Republicans United States",
            "national health insurance unpopular with Republicans United States",
            "single payer unpopular with Republicans United States",
        ),
        joined(
            "Medicare for All unpopular with Republicans United States",
            "public option unpopular with Republicans United States",
            "Affordable Care Act unpopular with Republicans United States",
            "national health insurance popular with Democrats United States",
            "single payer popular with Democrats United States",
            "Medicare for All popular with Democrats United States",
            "public option popular with Democrats United States",
            "Affordable Care Act popular with Democrats United States",
            "national health insurance unpopular with Democrats United States",
            "single payer unpopular with Democrats United States",
            "Medicare for All unpopular with Democrats United States",
            "public option unpopular with Democrats United States",
            "Affordable Care Act unpopular with Democrats United States",
        )
    ]
    queries = envelope(result)["data"]["expansion"]["queries"]
    assert [query["template_id"] for query in queries][7:] == [
        "politics-da/link/policy-2026-27-nhi-1/resolution",
        "politics-da/link/policy-2026-27-nhi-1/single-payer-aff",
        "politics-da/link/policy-2026-27-nhi-1/medicare-for-all-aff",
        "politics-da/link/policy-2026-27-nhi-1/public-option-aff",
        "politics-da/link/policy-2026-27-nhi-1/aca-reform-aff",
        "politics-da/link/2/resolution",
        "politics-da/link/2/single-payer-aff",
        "politics-da/link/2/medicare-for-all-aff",
        "politics-da/link/2/public-option-aff",
        "politics-da/link/2/aca-reform-aff",
        "politics-da/link/4/resolution",
        "politics-da/link/4/single-payer-aff",
        "politics-da/link/4/medicare-for-all-aff",
        "politics-da/link/4/public-option-aff",
        "politics-da/link/4/aca-reform-aff",
        "politics-da/link/5/resolution",
        "politics-da/link/5/single-payer-aff",
        "politics-da/link/5/medicare-for-all-aff",
        "politics-da/link/5/public-option-aff",
        "politics-da/link/5/aca-reform-aff",
        "politics-da/link/6/resolution",
        "politics-da/link/6/single-payer-aff",
        "politics-da/link/6/medicare-for-all-aff",
        "politics-da/link/6/public-option-aff",
        "politics-da/link/6/aca-reform-aff",
        "politics-da/link/7/resolution",
        "politics-da/link/7/single-payer-aff",
        "politics-da/link/7/medicare-for-all-aff",
        "politics-da/link/7/public-option-aff",
        "politics-da/link/7/aca-reform-aff",
    ]


def test_the_container_registers_openalex_feeds_and_google_news_and_closes_them(
    seams: Seams, monkeypatch: pytest.MonkeyPatch
) -> None:
    seams.registry_override = False
    seams.providers.any_feed_url = True
    monkeypatch.setenv("DEBATE_PROVIDERS__ENABLED", '["openalex", "rss", "google_news"]')

    result = search("midterm elections", "--since", "2026-09-14", "--format", "json")

    assert result.exit_code == ExitCode.OK, result.output
    providers = [entry["provider"] for entry in envelope(result)["data"]["providers"]]
    assert providers == ["openalex", "rss", "google_news"]
    assert seams.providers.transport.closed == 3


def test_the_container_builds_crossref_when_providers_enabled_names_it(
    seams: Seams, monkeypatch: pytest.MonkeyPatch
) -> None:
    seams.registry_override = False
    monkeypatch.setenv("DEBATE_PROVIDERS__ENABLED", '["crossref"]')

    result = search("carbon capture subsidies", "--format", "json")

    assert result.exit_code == ExitCode.OK, result.output
    data = envelope(result)["data"]
    assert [(entry["provider"], entry["outcome"]) for entry in data["providers"]] == [("crossref", "ok")]
    [item] = data["results"]
    assert (item["title"], item["identifiers"]["doi"], item["source_type"]) == (
        "Subsidy design for capture plants",
        "10.5555/invented.report.2021",
        "other",
    )
    assert item["published_at"] == "2021-01-01T00:00:00+00:00"
    [request] = [request for request in seams.providers.requests if request.url.host == CROSSREF_HOST]
    assert request.url.params["query.bibliographic"] == "carbon capture subsidies"
    assert "mailto" not in request.url.params
    assert seams.providers.transport.closed == 1


def test_the_container_builds_semantic_scholar_with_its_key_when_providers_enabled_names_it(
    seams: Seams, monkeypatch: pytest.MonkeyPatch
) -> None:
    seams.registry_override = False
    monkeypatch.setenv("DEBATE_PROVIDERS__ENABLED", '["semantic_scholar"]')
    monkeypatch.setenv("DEBATE_PROVIDERS__SEMANTIC_SCHOLAR_API_KEY", SEMANTIC_SCHOLAR_KEY)

    result = search("carbon-capture subsidies", "--format", "json")

    assert result.exit_code == ExitCode.OK, result.output
    data = envelope(result)["data"]
    assert [(entry["provider"], entry["outcome"]) for entry in data["providers"]] == [
        ("semantic_scholar", "ok")
    ]
    [item] = data["results"]
    assert (item["title"], item["source_type"], item["published_at"]) == (
        "Who captures the subsidy?",
        "scholarly",
        "2021-01-01T00:00:00+00:00",
    )
    assert (item["identifiers"]["semantic_scholar_id"], item["identifiers"]["arxiv_id"]) == (
        "c0ffee00c0ffee00c0ffee00c0ffee00c0ffee00",
        "2111.04567",
    )
    [request] = [request for request in seams.providers.requests if request.url.host == SEMANTIC_SCHOLAR_HOST]
    assert request.url.params["query"] == "carbon capture subsidies"
    assert request.headers["x-api-key"] == SEMANTIC_SCHOLAR_KEY
    assert SEMANTIC_SCHOLAR_KEY not in result.stdout + result.stderr
    assert seams.providers.transport.closed == 1


def test_the_federal_register_is_asked_only_by_a_search_on_a_topic_that_lists_it(
    seams: Seams, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Enabled in settings AND on the topic (v1-e07-t07): `config/feeds/health-insurance.yaml` lists it
    for NHI."""
    seams.registry_override = False
    monkeypatch.setenv("DEBATE_PROVIDERS__ENABLED", '["openalex", "federal_register"]')

    without = search("health insurance", "--format", "json")
    hosts_without = {request.url.host for request in seams.providers.requests}
    with_topic = search("health insurance", "--topic", "policy-2026-27-nhi", "--format", "json")

    assert without.exit_code == ExitCode.OK, without.output
    assert [entry["provider"] for entry in envelope(without)["data"]["providers"]] == ["openalex"]
    assert FEDERAL_REGISTER_HOST not in hosts_without
    assert with_topic.exit_code == ExitCode.OK, with_topic.output
    data = envelope(with_topic)["data"]
    assert [(entry["provider"], entry["outcome"]) for entry in data["providers"]] == [
        ("openalex", "ok"),
        ("federal_register", "ok"),
    ]
    [rule] = [item for item in data["results"] if item["providers"] == ["federal_register"]]
    assert (rule["title"], rule["publication"], rule["source_type"]) == (
        "Invented Coverage Standards for Marketplace Plans",
        "Centers for Medicare & Medicaid Services",
        "government",
    )
    [request] = [request for request in seams.providers.requests if request.url.host == FEDERAL_REGISTER_HOST]
    assert request.url.params["conditions[term]"] == "health insurance"


GOVINFO_NOT_COUNTED: Final = (
    "  govinfo: not configured: not counted as partial: no api.data.gov key "
    "(DEBATE_PROVIDERS__API_DATA_GOV_KEY); get a free key at api.data.gov/signup to ask GovInfo"
)
"""GovInfo enabled without its key, on a search that did not name it: named with its cure, and not
counted as partial (the PM's ruling 1 on v1-e07-t15)."""


def test_govinfo_without_an_api_data_gov_key_is_reported_not_configured_on_its_topic(
    seams: Seams, monkeypatch: pytest.MonkeyPatch
) -> None:
    seams.registry_override = False
    monkeypatch.setenv("DEBATE_PROVIDERS__ENABLED", '["openalex", "govinfo"]')

    without_topic = search("health insurance")
    on_topic = search("health insurance", "--topic", "policy-2026-27-nhi")

    assert without_topic.exit_code == ExitCode.OK, without_topic.output
    assert footer(without_topic) == ["Providers: COMPLETE", "  openalex: ok, 3 results"]
    assert on_topic.exit_code == ExitCode.OK, on_topic.output
    assert footer(on_topic) == ["Providers: COMPLETE", "  openalex: ok, 3 results", GOVINFO_NOT_COUNTED]
    assert GOVINFO_HOST not in {request.url.host for request in seams.providers.requests}


def test_govinfo_named_with_providers_and_not_configured_keeps_the_search_partial(
    seams: Seams, monkeypatch: pytest.MonkeyPatch
) -> None:
    seams.registry_override = False
    monkeypatch.setenv("DEBATE_PROVIDERS__ENABLED", '["openalex", "govinfo"]')

    result = search(
        "health insurance",
        "--topic",
        "policy-2026-27-nhi",
        "--providers",
        "openalex,govinfo",
        "--format",
        "json",
    )

    assert result.exit_code == ExitCode.SEARCH_PARTIAL, result.output
    error = envelope(result)["error"]
    assert error["code"] == "SEARCH_PARTIAL"
    assert error["details"]["status"] == "PARTIAL"
    assert [
        (entry["provider"], entry["outcome"], entry["reasons"]) for entry in error["details"]["providers"]
    ] == [
        ("openalex", "ok", []),
        ("govinfo", "not configured", ["no api.data.gov key (DEBATE_PROVIDERS__API_DATA_GOV_KEY)"]),
    ]
    assert GOVINFO_HOST not in {request.url.host for request in seams.providers.requests}


def test_govinfo_not_configured_beside_a_provider_that_failed_is_still_a_failed_search(
    seams: Seams, monkeypatch: pytest.MonkeyPatch
) -> None:
    seams.registry_override = False
    seams.providers.openalex_status = 503
    monkeypatch.setenv("DEBATE_PROVIDERS__ENABLED", '["openalex", "govinfo"]')

    result = search("health insurance", "--topic", "policy-2026-27-nhi")

    assert result.exit_code == ExitCode.RETRIEVAL_FAILURE, result.output
    lines = footer(result, stream="stderr")
    assert lines[0] == "Providers: FAILED"
    assert GOVINFO_NOT_COUNTED in lines


def test_govinfo_with_its_key_is_asked_on_its_topic_with_the_key_in_a_header_only(
    seams: Seams, monkeypatch: pytest.MonkeyPatch
) -> None:
    seams.registry_override = False
    monkeypatch.setenv("DEBATE_PROVIDERS__ENABLED", '["govinfo"]')
    monkeypatch.setenv("DEBATE_PROVIDERS__API_DATA_GOV_KEY", DATA_GOV_KEY)

    result = search("health insurance", "--topic", "policy-2026-27-nhi", "--format", "json")

    assert result.exit_code == ExitCode.OK, result.output
    data = envelope(result)["data"]
    assert [(entry["provider"], entry["outcome"]) for entry in data["providers"]] == [("govinfo", "ok")]
    [item] = data["results"]
    assert (item["title"], item["publication"], item["published_at"]) == (
        "Invented Hearing on Coverage for Rural Families",
        "Congress. Senate. Committee on Finance",
        "2026-03-01T00:00:00+00:00",
    )
    [request] = [request for request in seams.providers.requests if request.url.host == GOVINFO_HOST]
    assert request.headers["x-api-key"] == DATA_GOV_KEY
    assert DATA_GOV_KEY not in str(request.url)
    assert DATA_GOV_KEY not in result.stdout + result.stderr


# ------------------------------------------------------------------------------------------------
# The committed dev and prod profiles: what a student's machine asks (v1-e07-t13)
# ------------------------------------------------------------------------------------------------

INVENTED_CONTACT_EMAIL: Final = "invented-t13@example.org"
"""An address of no one's, for the polite pool."""

PUBLIC_POOL_NOT_ASKED: Final = (
    "not asked: the public pool allows 1 query a second; set a contact email for the polite pool"
)
"""Crossref's reason for a query its public pool could not send in time (v1-e07-t03)."""


@pytest.fixture(params=["dev", "prod"])
def committed_profile(
    request: pytest.FixtureRequest, seams: Seams, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Seams:
    """A search under the committed dev or prod profile, the container building every provider it enables
    over the recorded answers, with no contact email and no api.data.gov key: a student's machine before
    they set either. Run from a folder of the test's own, so no `.env` can supply one."""
    from debate_core.application.settings import find_repository_root

    root = find_repository_root(Path(__file__).parent)
    assert root is not None
    seams.registry_override = False
    seams.providers.any_feed_url = True
    monkeypatch.setenv("DEBATE_ENV", request.param)
    monkeypatch.setenv("DEBATE_PROFILE_DIR", str(root / "config" / "profiles"))
    monkeypatch.chdir(tmp_path)
    return seams


def hosts_asked(seams: Seams) -> dict[str, int]:
    counts: dict[str, int] = {}
    for request in seams.providers.requests:
        counts[request.url.host] = counts.get(request.url.host, 0) + 1
    return counts


def test_on_the_committed_profile_a_search_with_no_topic_asks_crossref_publicly_and_no_government_source(
    committed_profile: Seams,
) -> None:
    result = search("midterm elections", "--since", "2026-09-14")

    assert result.exit_code == ExitCode.OK, result.output
    assert footer(result) == [
        "Providers: COMPLETE",
        "  openalex: ok, 3 results",
        "  crossref: ok, 1 result",
        "  rss: ok, 2 results",
    ]
    [request] = [r for r in committed_profile.providers.requests if r.url.host == CROSSREF_HOST]
    assert "mailto" not in request.url.params
    assert "mailto" not in request.headers["user-agent"]
    assert FEDERAL_REGISTER_HOST not in hosts_asked(committed_profile)
    assert GOVINFO_HOST not in hosts_asked(committed_profile)


def test_on_the_committed_profile_a_contact_email_puts_crossref_in_the_polite_pool_and_is_never_printed(
    committed_profile: Seams, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_PROVIDERS__CONTACT_EMAIL", INVENTED_CONTACT_EMAIL)

    result = search("midterm elections", "--since", "2026-09-14")

    assert result.exit_code == ExitCode.OK, result.output
    assert "  crossref: ok, 1 result" in footer(result)
    [request] = [r for r in committed_profile.providers.requests if r.url.host == CROSSREF_HOST]
    assert request.url.params["mailto"] == INVENTED_CONTACT_EMAIL
    assert f"mailto:{INVENTED_CONTACT_EMAIL}" in request.headers["user-agent"]
    assert INVENTED_CONTACT_EMAIL not in result.stdout + result.stderr


def test_on_the_committed_profile_an_nhi_search_without_a_key_names_govinfo_not_configured_and_is_complete(
    committed_profile: Seams,
) -> None:
    """The Federal Register takes no key and answers; GovInfo has none and is never asked. The topic's
    feed file lists both (`config/feeds/health-insurance.yaml`); enabling them in the profile adds no
    topic."""
    result = search("health insurance", "--topic", "policy-2026-27-nhi")

    assert result.exit_code == ExitCode.OK, result.output
    assert footer(result) == [
        "Providers: COMPLETE",
        "  openalex: ok, 3 results",
        "  crossref: ok, 1 result",
        "  rss: ok, 2 results",
        "  federal_register: ok, 1 result",
        GOVINFO_NOT_COUNTED,
    ]
    assert hosts_asked(committed_profile)[FEDERAL_REGISTER_HOST] == 1
    assert GOVINFO_HOST not in hosts_asked(committed_profile)


def test_on_the_committed_profile_a_search_on_the_nhi_topic_with_a_key_asks_govinfo_and_is_complete(
    committed_profile: Seams, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_PROVIDERS__API_DATA_GOV_KEY", DATA_GOV_KEY)

    result = search("health insurance", "--topic", "policy-2026-27-nhi")

    assert result.exit_code == ExitCode.OK, result.output
    assert footer(result)[0] == "Providers: COMPLETE"
    assert footer(result)[-2:] == ["  federal_register: ok, 1 result", "  govinfo: ok, 1 result"]
    assert DATA_GOV_KEY not in result.stdout + result.stderr


class PacerTime:
    """A clock and a sleep for Crossref's pacer, on one timeline that moves only when every task is waiting,
    for the public-pool footer test below; the wall clock is never read.

    The command runs its own event loop, so the timeline drives itself from inside it: the first sleep
    starts a driver task that lets every runnable task run (200 turns of the loop, as `VirtualTime` in
    `debate_core`'s `test_crossref.py` does), then jumps the clock to the earliest sleeper's wake time and
    wakes it, until no sleeper is left. A sleep cancelled before it wakes is dropped.
    """

    def __init__(self, start: datetime) -> None:
        self.clock = FixedClock(start)
        self._timers: list[tuple[datetime, int, asyncio.Future[None]]] = []
        self._order = itertools.count()
        self._driver: asyncio.Task[None] | None = None

    async def sleep(self, seconds: float) -> None:
        if seconds <= 0:
            await asyncio.sleep(0)
            return
        loop = asyncio.get_running_loop()
        wake: asyncio.Future[None] = loop.create_future()
        heapq.heappush(self._timers, (self.clock.now() + timedelta(seconds=seconds), next(self._order), wake))
        if self._driver is None or self._driver.done():
            self._driver = loop.create_task(self._drive())
        await wake

    async def _drive(self) -> None:
        while True:
            for _ in range(200):
                await asyncio.sleep(0)
            while self._timers and self._timers[0][2].done():
                heapq.heappop(self._timers)
            if not self._timers:
                return
            wake_at, _, wake = heapq.heappop(self._timers)
            self.clock.set(max(wake_at, self.clock.now()))
            wake.set_result(None)


def test_on_the_committed_profile_without_a_contact_email_crossref_names_the_public_pool_in_the_footer(
    committed_profile: Seams, monkeypatch: pytest.MonkeyPatch, on_virtual_time: None
) -> None:
    """An expanded search's queries all reach Crossref at once, and the public pool sends one a second, so
    the ones it cannot send before their timeout less a reserve come back not asked, named in the footer
    with the cure (v1-e07-t03). With the profiles' 10 seconds, the same search sends nine (the
    before-and-after measurement in v1-e07-t13's report).

    The pacer runs on the test's time (:class:`PacerTime`), handed to it through `crossref_factory`'s own
    `clock` and `sleep`, which the container leaves at the wall clock and `asyncio.sleep`. On the wall
    clock a busy runner let the second query arrive after the first was sent, and then its turn came
    inside its deadline: two requests (`v1-e32-t49`, PM ruling of 2026-11-05). The command's own loop runs on
    virtual time too (`on_virtual_time`), so the wrapper's 2-second timeout and the search's deadline are not
    the wall clock's either: a runner busy for 2 seconds while the queries waited timed one out
    (`v1-e07-t16`, PM ruling of 2026-11-05).

    Worked by hand, the same under the dev and the prod profile (neither sets a contact email, so both
    are on the public pool, and the environment's 2 seconds replace both profiles' timeout):

    * The public pool sends 1 query a second, 1 at a time, so a query's turn is 1 second after the one
      before it started.
    * The reserve is the median answer time clamped to at least 1 second and at most half the timeout:
      half of 2 is 1, so it is 1 whatever Crossref's answers take.
    * All 37 NHI link queries (v1-e08-t16's crossing) arrive at the start, before the timeline moves,
      so every query's deadline is the start plus 2 less 1: the start plus 1 second.
    * The first is sent at the start. The second's turn is at the start plus 1 second, its deadline:
      too late, not asked. The third to the 37th come after it, past the same deadline: not asked.

    One request, its one recorded result, 36 not asked; the timeline moves once, by the second's
    one-second wait.
    """
    monkeypatch.setenv("DEBATE_PROVIDERS__TIMEOUT_SECONDS", "2")
    pacer_time = PacerTime(NOW)
    build = crossref_discovery.crossref_factory

    def on_the_test_s_time(
        http: HttpSettings,
        *,
        version: str,
        clock: object,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> Callable[[ProviderSettings], crossref_discovery.CrossrefProvider]:
        del clock
        return build(
            http, version=version, clock=pacer_time.clock, sleep=pacer_time.sleep, transport=transport
        )

    monkeypatch.setattr(crossref_discovery, "crossref_factory", on_the_test_s_time)

    result = search(
        "national health insurance",
        "--argument",
        "politics-da",
        "--need",
        "link",
        "--topic",
        "policy-2026-27-nhi",
        "--providers",
        "crossref",
    )

    assert result.exit_code == ExitCode.SEARCH_PARTIAL, result.output
    assert footer(result) == [
        "Providers: PARTIAL, results may be missing",
        f"  crossref: partial, 1 result from 37 queries: {PUBLIC_POOL_NOT_ASKED}",
    ]
    assert hosts_asked(committed_profile) == {CROSSREF_HOST: 1}
    assert pacer_time.clock.now() == NOW + timedelta(seconds=1)


def test_a_topic_alone_searches_the_query_as_typed(seams: Seams) -> None:
    result = search("midterm elections", "--since", "2026-09-14", "--topic", "policy-2026-27-nhi")

    assert result.exit_code == ExitCode.OK, result.output
    assert seams.providers.openalex_queries() == ["midterm elections"]


def test_an_unknown_topic_alone_exits_2_listing_the_topics_and_searches_nothing(seams: Seams) -> None:
    result = search("health insurance", "--topic", "policy-2025-26-nhi")

    assert result.exit_code == ExitCode.USAGE_ERROR, result.output
    assert "unknown topic 'policy-2025-26-nhi'; the topics are: policy-2026-27-nhi" in " ".join(
        result.stderr.split()
    )
    assert seams.providers.requests == []


def test_the_test_profile_refuses_an_enabled_provider_without_a_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in [name for name in os.environ if name.startswith("DEBATE_")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("DEBATE_ENV", "test")
    monkeypatch.setenv("DEBATE_PROVIDERS__ENABLED", '["openalex"]')

    result = search("midterm elections", "--format", "json")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    assert envelope(result)["error"]["details"]["field"] == "allow_network"


# ------------------------------------------------------------------------------------------------
# --expand-llm and --save
# ------------------------------------------------------------------------------------------------


def test_no_model_is_asked_without_expand_llm(seams: Seams) -> None:
    result = search("health insurance", "--argument", "politics-da", "--need", "link", "--format", "json")

    assert result.exit_code == ExitCode.OK, result.output
    assert seams.router.calls == []
    assert envelope(result)["data"]["expansion"]["model_requested"] is False


def test_expand_llm_adds_the_models_validated_queries(seams: Seams) -> None:
    seams.router.enqueue(
        {
            "queries": [
                {"query": "health insurance midterm stakes", "rationale": "What the midterms mean for it."}
            ]
        }
    )

    result = search(
        "health insurance", "--argument", "politics-da", "--need", "link", "--expand-llm", "--format", "json"
    )

    assert result.exit_code == ExitCode.OK, result.output
    [call] = seams.router.calls
    assert call.task_class.value == "high_volume"
    expansion = envelope(result)["data"]["expansion"]
    assert expansion["model_requested"] is True
    assert expansion["queries"][-1]["query"] == "health insurance midterm stakes"
    assert seams.providers.openalex_queries() == [
        joined(*POLITICS_LINK_QUERIES, "health insurance midterm stakes")
    ]


ASKED_ALONE_REASON: Final = (
    "not counted as partial: {count} asked alone, not joined: an unbalanced parenthesis or double quote, "
    "or an AND, OR or NOT"
)
"""The footer's OpenAlex reason for queries asked alone (v1-e08-t20, the PM's ruling 4)."""


def test_a_typed_query_with_an_open_parenthesis_asks_openalex_each_query_alone_and_says_so(
    seams: Seams,
) -> None:
    """Every politics link template carries the typed query, so each of the seven goes alone, as typed;
    the feed is read once, as before. Each lone query gets all three works of the fixture: 21."""
    typed = "health insurance (reform"
    alone = [query.replace("health insurance", typed) for query in POLITICS_LINK_QUERIES]

    result = search(typed, "--argument", "politics-da", "--need", "link", "--format", "json")

    assert result.exit_code == ExitCode.OK, result.output
    assert sorted(seams.providers.openalex_queries()) == sorted(alone)
    assert [str(request.url) for request in seams.providers.requests].count(FEED_URL) == 1
    [openalex] = [entry for entry in envelope(result)["data"]["providers"] if entry["provider"] == "openalex"]
    assert (openalex["outcome"], openalex["results"], openalex["reasons"]) == (
        "ok",
        21,
        [ASKED_ALONE_REASON.format(count="7 queries")],
    )

    shown = search(typed, "--argument", "politics-da", "--need", "link")

    assert (
        "openalex: ok, 21 results from 7 queries: " + ASKED_ALONE_REASON.format(count="7 queries")
        in " ".join(shown.stdout.split())
    )


def test_a_model_query_with_a_bare_or_is_asked_alone_and_the_template_queries_joined(seams: Seams) -> None:
    model_query = "health insurance OR Medicaid midterm stakes"
    seams.router.enqueue({"queries": [{"query": model_query, "rationale": "What the midterms mean for it."}]})

    result = search(
        "health insurance", "--argument", "politics-da", "--need", "link", "--expand-llm", "--format", "json"
    )

    assert result.exit_code == ExitCode.OK, result.output
    assert seams.providers.openalex_queries() == [joined(*POLITICS_LINK_QUERIES), model_query]
    [openalex] = [entry for entry in envelope(result)["data"]["providers"] if entry["provider"] == "openalex"]
    assert openalex["reasons"] == [ASKED_ALONE_REASON.format(count="1 query")]


def test_expand_llm_that_cannot_reach_a_model_prints_the_expansions_warning(seams: Seams) -> None:
    seams.router.enqueue(ProviderUnavailable("bedrock", "unreachable"))

    result = search("health insurance", "--argument", "politics-da", "--need", "link", "--expand-llm")

    assert result.exit_code == ExitCode.OK, result.output
    assert "searched with the template queries alone" in " ".join(result.stderr.split())
    assert seams.providers.openalex_queries() == [joined(*POLITICS_LINK_QUERIES)]


def test_save_writes_the_search_object_to_a_file(seams: Seams, tmp_path: Path) -> None:
    saved = tmp_path / "midterms.json"

    result = search("midterm elections", "--since", "2026-09-14", "--save", str(saved), "--format", "json")

    assert result.exit_code == ExitCode.OK, result.output
    assert json.loads(saved.read_text(encoding="utf-8")) == envelope(result)["data"]


# ------------------------------------------------------------------------------------------------
# The exit code rule, where the fixtures cannot reach it
# ------------------------------------------------------------------------------------------------


def test_a_partial_search_with_no_rows_is_still_partial_not_no_results() -> None:
    search_record = Search(
        query="midterm elections", status=SearchStatus.PARTIAL, created_at=NOW, updated_at=NOW
    )
    outcome = SearchOutcome(
        search=search_record, provider_statuses=(), candidates=(), results=(), provider_health=()
    )

    assert exit_code_for_search(outcome) is ExitCode.SEARCH_PARTIAL


def test_an_unknown_expansion_choice_is_a_usage_error_wherever_it_is_raised() -> None:
    assert (
        exit_code_for(UnknownExpansionChoice("argument", "nonsense-da", ["politics-da"]))
        is ExitCode.USAGE_ERROR
    )


# ------------------------------------------------------------------------------------------------
# --auto-cut N (v1-e08-t06)
# ------------------------------------------------------------------------------------------------

NEWS_PAGE: Final = (
    "https://www.dailymeridian.example/science/2026/09/14/mammoth-revival-years-away?utm_source=newsletter"
)
THINK_TANK_PAGE: Final = "https://www.harwell-institute.example/research/opportunity-cost-of-de-extinction"
JOURNAL_PDF: Final = "https://journal.synthetic-conservation.example/doi/pdf/10.5555/jscs.2026.0012"
PRESS_RELEASE: Final = "https://www.fosw.example.gov/news/2026/06/agency-announces-grants"
PAYWALLED_PAGE: Final = "https://www.harborreview.example/politics/2026/10/inside-the-tariff-talks"
ROBOTS_PAGE: Final = "https://www.closed-stacks.example/archive/2026/water-rights-ruling"
VERIFYING_PAGES: Final = {NEWS_PAGE, THINK_TANK_PAGE, JOURNAL_PDF}
"""The three of `openalex_auto_cut.body.json`'s pages whose cards verify (fixtures/search/README.md)."""
BLOCK: Final = "Politics DA — Link: health insurance"
SECTION: Final = "UNVERIFIED — not finished cards"
EVIDENCE_WORD: Final = "surrogate"
"""A word of the news article's second paragraph, the evidence its card is cut from: printed nowhere."""


@pytest.fixture
def cutting(seams: Seams) -> Seams:
    """`seams` for `--auto-cut`: OpenAlex answers with the cassettes' pages, which the fetch replays."""
    seams.providers.works_body = "openalex_auto_cut.body.json"
    seams.articles = ReplayTransport(load_cassette(name) for name in cassette_names())
    seams.card_router = EveryPageRouter()
    seams.crossref.serve(JOURNAL_DOI, "works-10.5555-jscs.2026.0012.json")
    return seams


def auto_cut(out: Path, *options: str, wanted: int = 3, json_output: bool = False) -> Result:
    return search(
        "health insurance",
        "--argument",
        "politics-da",
        "--need",
        "link",
        "--providers",
        "openalex",
        "--auto-cut",
        str(wanted),
        "--output",
        str(out),
        *options,
        json_output=json_output,
    )


def bundle_paragraphs(path: Path) -> list[str]:
    return [paragraph.text for paragraph in docx.Document(io.BytesIO(path.read_bytes())).paragraphs]


def report_json(directory: Path) -> dict[str, Any]:
    document: dict[str, Any] = json.loads((directory / "report.json").read_text(encoding="utf-8"))
    return document


def by_url(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {entry["url"]: entry for entry in report["entries"]}


def test_auto_cut_writes_three_verified_cards_under_one_block_heading_and_a_matching_manifest(
    cutting: Seams, tmp_path: Path
) -> None:
    out = tmp_path / "bundle.docx"

    result = auto_cut(out)

    assert result.exit_code == ExitCode.OK, result.output
    paragraphs = bundle_paragraphs(out)
    assert paragraphs[0] == BLOCK
    end = paragraphs.index(SECTION) if SECTION in paragraphs else len(paragraphs)
    assert paragraphs[:end].count(EVERY_PAGE_TAG) == 3
    assert BLOCK not in paragraphs[1:]
    manifest = (tmp_path / "bundle.manifest.json").read_bytes()
    assert read_embedded_manifest_bytes(out) == manifest
    cards = json.loads(manifest)["cards"]
    report = report_json(tmp_path)
    verified = [entry for entry in report["entries"] if entry["status"] == "VERIFIED"]
    assert {entry["url"] for entry in verified} == VERIFYING_PAGES
    assert [card["card_id"] for card in cards[:3]] == [entry["card_id"] for entry in verified]
    assert [card["verification_status"] for card in cards[:3]] == ["VERIFIED"] * 3
    assert all(card["verification_status"] == "UNVERIFIED" for card in cards[3:])
    assert (report["wanted"], report["verified"], report["complete"], report["stop_reason"]) == (
        3,
        3,
        True,
        "COMPLETE",
    )
    assert report["block"] == BLOCK
    assert EVIDENCE_WORD not in result.stdout
    assert EVIDENCE_WORD not in (tmp_path / "report.json").read_text(encoding="utf-8")


def test_auto_cut_skips_paywalled_and_robots_disallowed_results_lists_them_and_goes_on(
    cutting: Seams, tmp_path: Path
) -> None:
    out = tmp_path / "bundle.docx"

    result = auto_cut(out, wanted=4)

    assert result.exit_code == ExitCode.AUTO_CUT_SHORT, result.output
    entries = by_url(report_json(tmp_path))
    assert set(entries) == {*VERIFYING_PAGES, PRESS_RELEASE, PAYWALLED_PAGE, ROBOTS_PAGE}
    assert [entries[PAYWALLED_PAGE][key] for key in ("status", "access_status", "reasons", "card_id")] == [
        "SKIPPED",
        "PAYWALLED",
        ["SOURCE_NOT_ACCESSIBLE"],
        None,
    ]
    assert [entries[ROBOTS_PAGE][key] for key in ("status", "access_status", "reasons", "card_id")] == [
        "SKIPPED",
        "ROBOTS_DISALLOWED",
        ["SOURCE_NOT_ACCESSIBLE"],
        None,
    ]
    assert entries[PRESS_RELEASE]["status"] == "UNVERIFIED"
    assert entries[PRESS_RELEASE]["section"] == "unverified"
    assert entries[PRESS_RELEASE]["reasons"] == ["CITATION_UNVERIFIED"]
    assert {entries[url]["status"] for url in VERIFYING_PAGES} == {"VERIFIED"}
    assert report_json(tmp_path)["stop_reason"] == "CANDIDATES_EXHAUSTED"
    for shown in ("PAYWALLED", "ROBOTS_DISALLOWED", "SKIPPED", "SOURCE_NOT_ACCESSIBLE", PAYWALLED_PAGE):
        assert shown in result.stdout
    assert "AUTO_CUT_SHORT" in result.stderr
    paragraphs = bundle_paragraphs(out)
    section = paragraphs.index(SECTION)
    assert paragraphs[:section].count(EVERY_PAGE_TAG) == 3
    assert paragraphs[section + 1 :].count(EVERY_PAGE_TAG) == 1
    assert paragraphs[section + 2] == "UNVERIFIED — not a finished card: CITATION_UNVERIFIED"


def test_auto_cut_does_not_fetch_a_result_an_earlier_fetch_found_paywalled(
    cutting: Seams, tmp_path: Path, data_dir: Path
) -> None:
    seed_article(data_dir, NEWS_PAGE, AccessStatus.PAYWALLED)

    result = auto_cut(tmp_path / "bundle.docx", wanted=4)

    assert result.exit_code == ExitCode.AUTO_CUT_SHORT, result.output
    news = by_url(report_json(tmp_path))[NEWS_PAGE]
    assert (news["status"], news["access_status"], news["fetched"]) == ("SKIPPED", "PAYWALLED", False)
    assert cutting.articles is not None
    assert not [url for url in cutting.articles.requested if "dailymeridian" in url]


def test_auto_cut_report_prints_as_a_table_and_is_report_json_beside_the_bundle(
    cutting: Seams, tmp_path: Path
) -> None:
    out = tmp_path / "bundle.docx"

    result = auto_cut(out, "--concurrency", "3", "--card-format", "flow")

    assert result.exit_code == ExitCode.OK, result.output
    for column in ("Rank", "URL", "Access", "Card", "Reasons", "Cost"):
        assert column in result.stdout
    assert f"3 of 3 cards VERIFIED for {BLOCK}" in result.stdout
    assert f"Report: {tmp_path / 'report.json'}" in result.stdout
    assert "Providers: COMPLETE" in result.stdout
    report = report_json(tmp_path)
    assert (report["concurrency"], report["card_format"], report["max_cost_usd"]) == (3, "flow", None)
    assert (report["bundle"], report["manifest"]) == (str(out), str(tmp_path / "bundle.manifest.json"))
    assert report["cost_usd"] == 0.0
    assert all(entry["cost_usd"] == 0.0 for entry in report["entries"])


def test_auto_cut_json_output_carries_the_search_and_the_report(cutting: Seams, tmp_path: Path) -> None:
    result = auto_cut(tmp_path / "bundle.docx", json_output=True)

    assert result.exit_code == ExitCode.OK, result.output
    data = envelope(result)["data"]
    assert data["auto_cut"] == report_json(tmp_path)
    assert data["search"]["query"] == "health insurance"


def test_auto_cut_short_of_n_exits_8_in_json_with_the_report_as_details(
    cutting: Seams, tmp_path: Path
) -> None:
    result = auto_cut(tmp_path / "bundle.docx", wanted=5, json_output=True)

    assert result.exit_code == ExitCode.AUTO_CUT_SHORT, result.output
    error = envelope(result)["error"]
    assert (error["code"], error["exit_code"]) == ("AUTO_CUT_SHORT", 8)
    assert error["details"]["auto_cut"] == report_json(tmp_path)
    assert error["details"]["auto_cut"]["verified"] == 3


def test_auto_cut_exits_0_with_n_verified_when_the_search_was_partial_and_names_the_provider(
    cutting: Seams, tmp_path: Path
) -> None:
    cutting.providers.feed_status = 500

    result = search(
        "health insurance",
        "--argument",
        "politics-da",
        "--need",
        "link",
        "--providers",
        "openalex,rss",
        "--auto-cut",
        "3",
        "--output",
        str(tmp_path / "bundle.docx"),
    )

    assert result.exit_code == ExitCode.OK, result.output
    report = report_json(tmp_path)
    assert (report["search_status"], report["partial_providers"]) == ("PARTIAL", ["rss"])
    assert "Providers: PARTIAL, results may be missing" in result.stdout
    assert "rss: error" in result.stdout


def test_auto_cut_stops_at_the_budget_guard_exits_9_and_keeps_the_verified_card(
    cutting: Seams, tmp_path: Path
) -> None:
    cutting.card_router = EveryPageRouter(
        refuse={
            2: BudgetExceededError(
                limit_name="per-run",
                limit_usd=0.05,
                spent_usd=0.04,
                ceiling_usd=0.02,
                model_id="model-under-test",
            )
        }
    )
    out = tmp_path / "bundle.docx"

    result = auto_cut(out, "--concurrency", "1", "--max-cost", "0.05")

    assert result.exit_code == ExitCode.BUDGET_EXCEEDED, result.output
    report = report_json(tmp_path)
    statuses = [entry["status"] for entry in report["entries"]]
    assert statuses[-1] == "BUDGET_EXCEEDED"
    assert report["entries"][-1]["reasons"] == ["BUDGET_EXCEEDED"]
    assert report["stop_reason"] == "BUDGET_EXCEEDED"
    kept = [entry for entry in report["entries"] if entry["status"] == "VERIFIED"]
    assert len(kept) == 1
    assert bundle_paragraphs(out).count(EVERY_PAGE_TAG) == 1
    assert report["max_cost_usd"] == 0.05
    assert "BUDGET_EXCEEDED" in result.stderr


def test_auto_cut_max_cost_is_the_commands_per_run_budget(cutting: Seams, tmp_path: Path) -> None:
    result = auto_cut(tmp_path / "bundle.docx", "--max-cost", "0.25")

    assert result.exit_code == ExitCode.OK, result.output
    (container,) = cutting.containers
    assert container.settings.models.budget_usd_per_run == 0.25


def test_auto_cut_under_max_cost_ends_on_a_model_with_no_price(cutting: Seams, tmp_path: Path) -> None:
    cutting.card_router = EveryPageRouter(refuse={1: UnpricedModelError("model-without-a-price", "no price")})

    result = auto_cut(tmp_path / "bundle.docx", "--concurrency", "1", "--max-cost", "0.05")

    assert result.exit_code == ExitCode.BUDGET_EXCEEDED, result.output
    report = report_json(tmp_path)
    *before, last = [(entry["status"], entry["reasons"]) for entry in report["entries"]]
    assert last == ("BUDGET_EXCEEDED", ["UNPRICED_MODEL_ERROR"])
    assert {status for status, _ in before} <= {"SKIPPED"}
    assert report["stop_reason"] == "BUDGET_EXCEEDED"
    assert not (tmp_path / "bundle.docx").exists()
    assert report["bundle"] is None


# ------------------------------------------------------------------------------------------------
# One limit for the whole command, whatever routers it builds (v1-e08-t17)
#
# `--expand-llm` asks the search's router for `search.expand`, and `--auto-cut` asks the card router
# for `card.select` and `card.markup`. Here the container builds both itself, live, through the usage
# log and the budget guard, over a stand-in for Bedrock whose every call costs the most it could: its
# guard ceiling, at the committed prices. What the three cuts cost on their own is measured by a run
# with no limit, in a data directory of its own; the limit under test is that, so the cuts alone fit
# it exactly and the expansion's call, made first, does not.
# ------------------------------------------------------------------------------------------------

MODEL_EXPANSION: Final = {
    "queries": [{"query": "health insurance midterm stakes", "rationale": "What the midterms mean for it."}]
}
TO_THE_LAST_CENT: Final = 1e-9
"""A limit this much over a total, relatively, is that total to within float sums' rounding."""


class SpendsItsCeiling:
    """Bedrock's stand-in for one router: answers as `EveryPageRouter` and the scripted expansion do,
    and reports every call as the most it could cost on its route: its prompt variables' bytes in, its
    route's whole output cap out, on its route's model, which is the budget guard's ceiling of it."""

    def __init__(self, policy: RoutingPolicy) -> None:
        self._policy = policy
        self._cards = EveryPageRouter()
        self._expansions = ScriptedModelRouter()

    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        if prompt.prompt_id == EXPAND_PROMPT_ID:
            self._expansions.enqueue(MODEL_EXPANSION)
            answered = await self._expansions.generate_structured(task_class, prompt, schema, params)
        else:
            answered = await self._cards.generate_structured(task_class, prompt, schema, params)
        route = self._policy.resolve(task_class, params)
        variables = json.dumps(prompt.variables, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        usage = ModelUsage(
            input_tokens=len(variables.encode("utf-8")), output_tokens=route.max_tokens, latency_ms=1.0
        )
        return answered.model_copy(update={"route": route, "usage": usage})

    async def embed(self, texts: Sequence[str]) -> EmbeddingResponse:
        raise AssertionError("a search and its cuts embed nothing")

    async def rerank(self, query: str, documents: Sequence[str]) -> RerankResponse:
        raise AssertionError("a search and its cuts rerank nothing")


def bedrock_stand_in(registry: PromptRegistry) -> RealRouterFactory:
    def factory(policy: RoutingPolicy, *, aws_profile: str | None) -> ModelRouter:
        return SpendsItsCeiling(policy)

    return factory


def live(per_run_usd: float | None = None) -> Callable[[Settings], Settings]:
    """The profile's settings for a live run on the example routing file, with no daily limit, so
    `per_run_usd` (`models.budget_usd_per_run`) and `--max-cost` are the only limits."""

    def settings_for(settings: Settings) -> Settings:
        models = settings.models.model_copy(
            update={
                "provider": ModelProvider.BEDROCK,
                "routing_file": EXAMPLE_ROUTING_FILE,
                "budget_usd_daily": None,
                "budget_usd_per_run": per_run_usd,
            }
        )
        return settings.model_copy(update={"models": models})

    return settings_for


@pytest.fixture
def live_cutting(cutting: Seams, monkeypatch: pytest.MonkeyPatch) -> Seams:
    """`cutting`, with every model router built by the container, live, over the stand-in."""
    cutting.card_router = None
    cutting.live_models = live()
    monkeypatch.setenv("DEBATE_MODEL_MODE", "live")
    monkeypatch.setattr(bedrock, "bedrock_router_factory", bedrock_stand_in)
    return cutting


def usage_records(data_dir: Path) -> list[dict[str, Any]]:
    """Every call the usage log under `data_dir` recorded, in the order it recorded them."""
    return [
        json.loads(line)
        for path in sorted((data_dir / "usage").glob("*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def cuts_alone(seams: Seams, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """What each call of the four cuts costs, measured by a run with no limit and no `--expand-llm`, in
    a data directory of its own so the run under test fetches and cuts everything afresh.

    Four cuts for three verified cards: since v1-e08-t24 the politics DA's link search, whose queries
    all ask five years, ranks by no recency, so the fixture's government grant notice (whose citation
    does not verify) comes before the newer magazine story and is cut third."""
    measured = tmp_path / "measured"
    (measured / "out").mkdir(parents=True)
    monkeypatch.setenv("DEBATE_STORAGE__DATA_DIR", str(measured / "data"))
    result = auto_cut(measured / "out" / "bundle.docx", "--concurrency", "1")
    monkeypatch.setenv("DEBATE_STORAGE__DATA_DIR", str(tmp_path / "data"))
    assert result.exit_code == ExitCode.OK, result.output
    records = usage_records(measured / "data")
    assert [record["prompt_id"] for record in records] == ["card.select", "card.markup"] * 4
    return [record["estimated_cost_usd"] for record in records]


def refusal(report: dict[str, Any]) -> str:
    """The budget guard's words for the call it refused: the last entry's one detail."""
    *_, refused = report["entries"]
    assert (refused["status"], refused["reasons"]) == ("BUDGET_EXCEEDED", ["BUDGET_EXCEEDED"])
    [detail] = refused["details"]
    return " ".join(detail.split())


@pytest.mark.parametrize("limit_from", ["--max-cost", "models.budget_usd_per_run"])
def test_expand_llm_and_auto_cut_stop_at_one_budget_for_the_whole_command(
    live_cutting: Seams, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, limit_from: str
) -> None:
    cuts = cuts_alone(live_cutting, tmp_path, monkeypatch)
    limit = sum(cuts) * (1 + TO_THE_LAST_CENT)
    if limit_from == "--max-cost":
        options = ["--max-cost", repr(limit)]
    else:
        live_cutting.live_models = live(per_run_usd=limit)
        options = []
    out = tmp_path / "bundle.docx"

    result = auto_cut(out, "--expand-llm", "--concurrency", "1", *options)

    records = usage_records(tmp_path / "data")
    spent = sum(record["estimated_cost_usd"] for record in records)
    assert spent <= limit, f"the command spent ${spent:.6f} under a ${limit:.6f} limit"
    assert result.exit_code == ExitCode.BUDGET_EXCEEDED, result.output
    assert len({record["run_id"] for record in records}) == 1
    expansion, *card_calls = records
    assert expansion["prompt_id"] == EXPAND_PROMPT_ID
    # The fourth cut's markup call, which would have taken the command past the limit, was refused;
    # the third cut is the unverified one, so two cards are verified.
    assert [record["prompt_id"] for record in card_calls] == ["card.select", "card.markup"] * 3 + [
        "card.select"
    ]
    report = report_json(tmp_path)
    assert report["stop_reason"] == "BUDGET_EXCEEDED"
    assert report["verified"] == 2
    assert f"the per-run budget is ${limit:.4f}, ${spent:.4f} is already spent or held" in refusal(report)


def test_two_commands_in_one_process_are_two_budget_runs(live_cutting: Seams, tmp_path: Path) -> None:
    expand = ("health insurance", "--argument", "politics-da", "--need", "link", "--expand-llm")

    first, second = search(*expand), search(*expand)

    assert (first.exit_code, second.exit_code) == (ExitCode.OK, ExitCode.OK), first.output + second.output
    records = usage_records(tmp_path / "data")
    assert [record["prompt_id"] for record in records] == [EXPAND_PROMPT_ID] * 2
    assert len({record["run_id"] for record in records}) == 2


def test_a_one_router_auto_cut_spends_up_to_its_max_cost_as_before(
    live_cutting: Seams, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cuts = cuts_alone(live_cutting, tmp_path, monkeypatch)
    out = tmp_path / "bundle.docx"

    result = auto_cut(out, "--concurrency", "1", "--max-cost", repr(sum(cuts) * (1 + TO_THE_LAST_CENT)))

    assert result.exit_code == ExitCode.OK, result.output
    records = usage_records(tmp_path / "data")
    assert [record["estimated_cost_usd"] for record in records] == cuts
    report = report_json(tmp_path)
    assert report["verified"] == 3
    # v1-e08-t06's attribution: each cut's entry costs its own two calls, and the report their sum.
    # The third cut (calls 5 and 6) is the unverified one.
    verified = [entry for entry in report["entries"] if entry["status"] == "VERIFIED"]
    assert [entry["cost_usd"] for entry in verified] == pytest.approx(
        [cuts[0] + cuts[1], cuts[2] + cuts[3], cuts[6] + cuts[7]]
    )
    assert report["cost_usd"] == pytest.approx(sum(cuts))


def test_a_one_router_auto_cut_a_cent_short_of_its_max_cost_is_refused_as_before(
    live_cutting: Seams, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cuts = cuts_alone(live_cutting, tmp_path, monkeypatch)
    limit = sum(cuts) * (1 - TO_THE_LAST_CENT)

    result = auto_cut(tmp_path / "bundle.docx", "--concurrency", "1", "--max-cost", repr(limit))

    assert result.exit_code == ExitCode.BUDGET_EXCEEDED, result.output
    spent = sum(cuts[:7])
    assert [record["estimated_cost_usd"] for record in usage_records(tmp_path / "data")] == cuts[:7]
    assert refusal(report_json(tmp_path)) == (
        f"model call to anthropic.claude-sonnet-5-5 refused: the per-run budget is ${limit:.4f}, "
        f"${spent:.4f} is already spent or held, ${limit - spent:.4f} remains, and this call could cost "
        f"up to ${cuts[7]:.4f}"
    )


@pytest.mark.parametrize(
    ("options", "message"),
    [
        (["--auto-cut", "3", "--output", "OUT"], "--auto-cut needs --argument and --need"),
        (["--argument", "politics-da", "--need", "link", "--auto-cut", "3"], "--auto-cut needs --output"),
        (["--output", "OUT"], "--output go with --auto-cut"),
        (["--max-cost", "1", "--concurrency", "2"], "--concurrency and --max-cost go with --auto-cut"),
        (
            [
                "--argument",
                "politics-da",
                "--need",
                "link",
                "--auto-cut",
                "3",
                "--output",
                "OUT",
                "--card-format",
                "x",
            ],
            "no format profile named 'x'",
        ),
        (
            [
                "--argument",
                "politics-da",
                "--need",
                "link",
                "--auto-cut",
                "3",
                "--output",
                "OUT",
                "--concurrency",
                "9",
            ],
            "9",
        ),
        (["--argument", "politics-da", "--need", "link", "--auto-cut", "0", "--output", "OUT"], "0"),
    ],
)
def test_auto_cut_options_that_do_not_go_together_exit_2_and_search_nothing(
    cutting: Seams, tmp_path: Path, options: list[str], message: str
) -> None:
    out = str(tmp_path / "bundle.docx")

    result = search(
        "health insurance", "--providers", "openalex", *[out if o == "OUT" else o for o in options]
    )

    assert result.exit_code == ExitCode.USAGE_ERROR, result.output
    assert message in " ".join(result.output.split()).replace("│", "")
    assert cutting.providers.openalex_queries() == []
    assert not (tmp_path / "report.json").exists()


def test_auto_cut_after_a_search_no_provider_answered_ends_as_search_does_and_cuts_nothing(
    cutting: Seams, tmp_path: Path
) -> None:
    cutting.providers.openalex_status = 500

    result = auto_cut(tmp_path / "bundle.docx")

    assert result.exit_code == ExitCode.RETRIEVAL_FAILURE, result.output
    assert not (tmp_path / "report.json").exists()
    assert not (tmp_path / "bundle.docx").exists()
    assert cutting.articles is not None
    assert cutting.articles.requested == []


def test_auto_cut_help_documents_its_options_and_exit_codes() -> None:
    result = runner.invoke(create_app(), ["search", "--help"], env={"COLUMNS": "200"})

    assert result.exit_code == ExitCode.OK
    for text in (
        "--auto-cut",
        "--output",
        "--card-format",
        "--concurrency",
        "--max-cost",
        "8  auto-cut short",
        "9  budget exceeded",
        "with --auto-cut, N cards are VERIFIED",
    ):
        assert text in result.stdout


def test_max_cost_help_says_it_is_one_limit_for_the_whole_command() -> None:
    result = runner.invoke(create_app(), ["search", "--help"], env={"COLUMNS": "200"})

    assert result.exit_code == ExitCode.OK
    help_text = " ".join(result.stdout.replace("│", " ").split())
    assert "one limit for the whole command, whatever models it asks" in help_text
