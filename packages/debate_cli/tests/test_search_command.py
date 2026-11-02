"""`debate-research search`, offline, through Typer's runner, the real app and the real composition root.

Everything below the providers is the production wiring (`v1-e08-t05`): the container's
FederatedSearchService with the expansion stage over the committed taxonomy, DedupeStage, the rank
stage over the committed weight table, Article matching, and the SQLite file in a data directory of
each test's own. The providers are the real OpenAlex and feed adapters, each wrapped in the real
ResilientProvider, in a ProviderRegistry the test registers under `discovery_providers` (the
registry override): their HTTP goes to :class:`RecordedProviders`, which answers from the recorded
bodies in `fixtures/search/` and sends nothing. One test instead registers only the transport, under
`discovery_transport`, so that the container builds the registry itself from settings.

Expected rows, footers and queries are written by hand from the fixtures (working agreement 6;
`fixtures/search/README.md` says what each body holds).
"""

from __future__ import annotations

import asyncio
import gc
import json
import os
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import httpx
import pytest
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.container import ServiceContainer
from debate_cli.exit_codes import ExitCode
from debate_core.application.errors import ProviderUnavailable
from debate_core.application.settings import HttpSettings, ProviderSettings, SearchProviderName
from debate_core.domain import AccessStatus, Article
from debate_core.integrations.discovery.feed_cache import InMemoryFeedCache
from debate_core.integrations.discovery.feed_config import FeedConfig, FeedReview, FeedSource
from debate_core.integrations.discovery.feeds import feed_factory
from debate_core.integrations.discovery.openalex import openalex_factory
from debate_core.integrations.discovery.registry import ProviderRegistry
from debate_core.integrations.local import SqliteArticleRepository, SqliteDatabase
from debate_core.retrieval import canonicalize_url
from debate_core.testing.fakes.model_router import ScriptedModelRouter

runner = CliRunner()

FIXTURES: Final = Path(__file__).resolve().parent / "fixtures" / "search"

NOW: Final = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
"""The container's clock, and the providers': after every fixture item, so recency is counted from it."""

OPENALEX_HOST: Final = "api.openalex.org"
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


@pytest.fixture
def seams(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Seams]:
    for name in [name for name in os.environ if name.startswith("DEBATE_")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("DEBATE_ENV", "test")
    monkeypatch.setenv("DEBATE_STORAGE__DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("COLUMNS", "250")
    seams = Seams()
    build = ServiceContainer.__init__

    def with_seams(self: ServiceContainer, **arguments: Any) -> None:
        build(self, **arguments)
        self.override("clock", lambda: NOW)
        self.override("search_model_router", seams.router)
        if seams.registry_override:
            self.override("discovery_providers", seams.providers.registry())
        else:
            self.override("discovery_transport", seams.providers.transport)

    monkeypatch.setattr(ServiceContainer, "__init__", with_seams)
    yield seams
    assert seams.providers.unrecorded == [], "a request no fixture recorded"


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
    assert seams.providers.openalex_queries() == POLITICS_LINK_QUERIES
    assert [(entry["provider"], entry["outcome"]) for entry in data["providers"]] == [
        ("openalex", "ok"),
        ("rss", "ok"),
    ]


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


def test_a_provider_that_times_out_makes_the_results_partial_and_exits_6(seams: Seams) -> None:
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


def test_a_partial_search_in_json_carries_its_results_and_the_failed_provider(seams: Seams) -> None:
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
    ("arguments", "said"),
    [
        (["--since", "2026-10-01", "--until", "2026-09-01"], "after --until"),
        (["--need", "link"], "--argument"),
        (["--argument", "politics-da"], "--need"),
        (["--topic", "policy-2026-27-nhi"], "--argument"),
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
    assert seams.providers.openalex_queries() == [*POLITICS_LINK_QUERIES, "health insurance midterm stakes"]


def test_expand_llm_that_cannot_reach_a_model_prints_the_expansions_warning(seams: Seams) -> None:
    seams.router.enqueue(ProviderUnavailable("bedrock", "unreachable"))

    result = search("health insurance", "--argument", "politics-da", "--need", "link", "--expand-llm")

    assert result.exit_code == ExitCode.OK, result.output
    assert "searched with the template queries alone" in " ".join(result.stderr.split())
    assert seams.providers.openalex_queries() == POLITICS_LINK_QUERIES


def test_save_writes_the_search_object_to_a_file(seams: Seams, tmp_path: Path) -> None:
    saved = tmp_path / "midterms.json"

    result = search("midterm elections", "--since", "2026-09-14", "--save", str(saved), "--format", "json")

    assert result.exit_code == ExitCode.OK, result.output
    assert json.loads(saved.read_text(encoding="utf-8")) == envelope(result)["data"]
