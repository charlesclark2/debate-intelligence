"""What the end-to-end suite puts at every boundary the CLI crosses, and how it runs the CLI (`v1-e09-t05`).

The suite drives `debate_cli.app.create_app()`, the entry point the console script calls, through
Typer's runner, with the production composition root. Nothing below the CLI is replaced but the
boundaries, each by its container seam, and each from a recording committed under `tests/fixtures/`
or `packages/debate_cli/tests/fixtures/search/` (reused, not copied: v1-e08-t06 recorded them):

* publisher pages: `article_fetch_transport`, the HTTP cassettes in `tests/fixtures/http/cassettes/`
  through :class:`ReplayTransport`;
* OpenAlex and the publisher feeds: `discovery_providers`, the real adapters over
  :class:`RecordedProviders`;
* Crossref: `crossref_transport`, the answer in `tests/fixtures/citation/crossref/` through
  `CrossrefAnswers`;
* `card.select` and `card.markup`: `card_model_router`,
  :class:`~tests.fixtures.card.every_page_router.EveryPageRouter`;
* `search.expand`: `search_model_router`, a scripted router with no answer, so a call fails;
* the clock: `clock`, :data:`NOW`.

A request no recording answers is never sent: it is kept, refused, and turned into
:class:`~debate_core.integrations.models.errors.MissingFixtureError` when the test ends
(:meth:`Boundaries.missing_fixtures`), so a scenario whose recording is missing fails rather than
skipping. A cassette a scenario names that is not committed raises the same error before anything
runs (:func:`recorded_cassettes`).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import httpx
from tests.fixtures.card.every_page_router import EveryPageRouter
from tests.fixtures.citation.citation_world import JOURNAL_DOI, CrossrefAnswers
from tests.fixtures.http.cassettes import CASSETTE_DIRECTORY, ReplayTransport, cassette_names, load_cassette
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_core.application.ports.model_router import ModelRouter
from debate_core.application.settings import HttpSettings, ProviderSettings, SearchProviderName
from debate_core.integrations.discovery.feed_cache import InMemoryFeedCache
from debate_core.integrations.discovery.feed_config import FeedConfig, FeedReview, FeedSource
from debate_core.integrations.discovery.feeds import feed_factory
from debate_core.integrations.discovery.openalex import openalex_factory
from debate_core.integrations.discovery.registry import ProviderRegistry
from debate_core.integrations.models.errors import MissingFixtureError
from debate_core.testing.fakes.model_router import ScriptedModelRouter

__all__ = [
    "NOW",
    "SEARCH_FIXTURES",
    "Boundaries",
    "Cli",
    "RecordedProviders",
    "recorded_cassettes",
]

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
SEARCH_FIXTURES: Final = REPOSITORY_ROOT / "packages" / "debate_cli" / "tests" / "fixtures" / "search"
"""v1-e08-t06's recorded OpenAlex answers and publisher feed (its README says what each holds)."""

NOW: Final = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
"""Every container's clock: after every recorded item, so recency counts from it; the accessed date."""

OPENALEX_HOST: Final = "api.openalex.org"
FEED_URL: Final = "https://news.example.org/rss/politics.xml"
TOPICS: Final = (
    FeedConfig(
        topic="politics",
        description="The suite's one topic.",
        feeds=(
            FeedSource(
                url=FEED_URL, publisher="The Example Courier", review=FeedReview.AWAITING_COACH_REVIEW
            ),
        ),
    ),
)
CROSSREF_ANSWER: Final = "works-10.5555-jscs.2026.0012.json"
"""Crossref's recorded answer for the open-access journal article's DOI, the one DOI a cassette carries."""


def _missing(*, call: str, key: str, location: Path, hint: str) -> MissingFixtureError:
    return MissingFixtureError(call=call, key=key, location=location, hint=hint)


def recorded_cassettes(names: Iterable[str] | None = None) -> ReplayTransport:
    """A replay of the named HTTP cassettes, every committed one by default.

    A name with no committed cassette raises MissingFixtureError here, before the scenario runs.
    """
    wanted = list(cassette_names() if names is None else names)
    for name in wanted:
        path = CASSETTE_DIRECTORY / f"{name}.json"
        if not path.is_file():
            raise _missing(
                call="http cassette",
                key=name,
                location=path,
                hint="build it with tests/fixtures/http/build_cassettes.py; the suite never skips a scenario",
            )
    return ReplayTransport(load_cassette(name) for name in wanted)


@dataclass
class RecordedProviders:
    """OpenAlex's and the publisher feed's recorded answers, and every request the providers sent."""

    works_body: str = "openalex_auto_cut.body.json"
    openalex_status: int = 200
    feed_status: int = 200
    requests: list[httpx.Request] = field(default_factory=list[httpx.Request])
    unrecorded: list[str] = field(default_factory=list[str])
    transport: httpx.MockTransport = field(init=False)

    def __post_init__(self) -> None:
        self.transport = httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host == OPENALEX_HOST and request.url.path == "/works":
            if self.openalex_status != 200:
                return httpx.Response(self.openalex_status)
            body = (SEARCH_FIXTURES / self.works_body).read_bytes()
            return httpx.Response(200, headers={"content-type": "application/json"}, content=body)
        if str(request.url) == FEED_URL:
            if self.feed_status != 200:
                return httpx.Response(self.feed_status)
            body = (SEARCH_FIXTURES / "courier_politics.xml").read_bytes()
            return httpx.Response(200, headers={"content-type": "application/rss+xml"}, content=body)
        self.unrecorded.append(str(request.url))
        raise httpx.ConnectError(f"no recording answers {request.method} {request.url}", request=request)

    def registry(self, clock_now: datetime) -> ProviderRegistry:
        """The real OpenAlex and feed adapters over this transport, each wrapped as production wraps it."""
        clock = _FixedNow(clock_now)
        http = HttpSettings(max_retries=0)
        factories = {
            SearchProviderName.OPENALEX: openalex_factory(
                http, version="e2e", clock=clock, transport=self.transport
            ),
            SearchProviderName.RSS: feed_factory(
                http,
                version="e2e",
                clock=clock,
                topics=TOPICS,
                cache=InMemoryFeedCache(),
                transport=self.transport,
            ),
        }
        settings = ProviderSettings(enabled=(SearchProviderName.OPENALEX, SearchProviderName.RSS))
        return ProviderRegistry.from_settings(settings, factories, clock=clock)


@dataclass(frozen=True)
class _FixedNow:
    instant: datetime

    def now(self) -> datetime:
        return self.instant


@dataclass
class Boundaries:
    """What every container the app builds is given in place of the network and the models."""

    pages: ReplayTransport = field(default_factory=recorded_cassettes)
    providers: RecordedProviders = field(default_factory=RecordedProviders)
    card_router: ModelRouter = field(default_factory=EveryPageRouter)
    search_router: ScriptedModelRouter = field(default_factory=ScriptedModelRouter)
    crossref: CrossrefAnswers = field(default_factory=CrossrefAnswers)

    def __post_init__(self) -> None:
        self.crossref.serve(JOURNAL_DOI, CROSSREF_ANSWER)

    def seams(self) -> Iterator[tuple[str, object]]:
        """Each container seam and what it is given."""
        yield "clock", lambda: NOW
        yield "article_fetch_transport", self.pages
        yield "discovery_providers", self.providers.registry(NOW)
        yield "crossref_transport", httpx.MockTransport(self.crossref.handle)
        yield "card_model_router", self.card_router
        yield "search_model_router", self.search_router

    def missing_fixtures(self) -> list[MissingFixtureError]:
        """One error for every request no recording answered, in the order they were asked."""
        found = [
            _missing(
                call="http page",
                key=url,
                location=CASSETTE_DIRECTORY,
                hint="no cassette recorded this URL; nothing was sent",
            )
            for url in self.pages.unrecorded
        ]
        found += [
            _missing(
                call="search provider",
                key=url,
                location=SEARCH_FIXTURES,
                hint="no recorded provider answer for this URL; nothing was sent",
            )
            for url in self.providers.unrecorded
        ]
        found += [
            _missing(
                call="crossref",
                key=str(request.url),
                location=REPOSITORY_ROOT / "tests" / "fixtures" / "citation" / "crossref",
                hint="Crossref was asked about a DOI no recorded answer covers",
            )
            for request in self.crossref.requests
            if JOURNAL_DOI not in str(request.url).lower()
        ]
        return found


class Cli:
    """`debate-research`, run in this process through the entry point the console script calls."""

    def __init__(self) -> None:
        self._runner = CliRunner()

    def run(self, *arguments: str, json_output: bool = False) -> Result:
        return self._runner.invoke(create_app(), [*(["--json"] if json_output else []), *arguments])

    def envelope(self, *arguments: str) -> tuple[Result, dict[str, Any]]:
        """Run with `--json`, and the one JSON object it must print."""
        result = self.run(*arguments, json_output=True)
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        assert len(lines) == 1, (
            f"--json must print one line on stdout, got {result.stdout!r}\n{result.stderr}"
        )
        document: dict[str, Any] = json.loads(lines[0])
        return result, document
