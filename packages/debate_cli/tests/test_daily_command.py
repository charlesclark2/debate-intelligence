"""`debate-research daily`, offline, through Typer's runner, the real app and the real composition root.

Everything below the HTTP is the production wiring (`v1-e08-t07`): the committed
`config/daily_presets.yaml`, checked on load; the container's DigestService over `search`'s federated
search, with the expansion over the committed taxonomy, dedupe, ranking and Article matching; the real
feed provider, built by the container for the preset's feed topics; the seen-set in the data
directory. The test gives the container its own feed lists (`FEED_LISTS`, under `topic_feed_lists`)
so the URLs are the fixtures', and the transport (`discovery_transport`) answers them from
`fixtures/daily/` and records every request; anything else it is asked is refused and named by the
fixture's last check. The clock is the container's, overridden.

Expected digests are written by hand from the fixtures (working agreement 6; `fixtures/daily/README.md`
says what each feed holds). The one value not written by hand is each result's "Why", the ranking's
explanation (v1-e08-t03), which the Markdown is checked to carry exactly as the JSON gives it.
"""

from __future__ import annotations

import gc
import json
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

import docx
import httpx
import pytest
import yaml
from pydantic import BaseModel
from tests.fixtures.card.every_page_router import EVERY_PAGE_TAG, EveryPageRouter
from tests.fixtures.citation.citation_world import CrossrefAnswers
from tests.fixtures.http.cassettes import ReplayTransport, cassette_names, load_cassette
from typer.testing import CliRunner, Result

from debate_cli import container as container_module
from debate_cli.app import create_app
from debate_cli.container import ServiceContainer
from debate_cli.exit_codes import ExitCode
from debate_core.application.settings import SearchProviderName
from debate_core.domain.model_contracts import ModelParams, ModelPrompt, ModelResponse, TaskClass
from debate_core.evidence.selection_contract import CARD_SELECT_PROMPT_ID

# Imported before pytest-socket is armed: urllib3 (through trafilatura) probes for IPv6 with a socket
# when it is first imported, which `--auto-cut`'s article fetch would otherwise do inside a test.
from debate_core.integrations import html_extractor as html_extractor
from debate_core.integrations.discovery.feed_config import FeedConfig, FeedReview, FeedSource

runner = CliRunner()

FIXTURES: Final = Path(__file__).resolve().parent / "fixtures" / "daily"
NOW: Final = datetime(2026, 9, 17, 22, 0, tzinfo=UTC)
"""The container's clock: the evening of 17 September, so `daily politics` with no `--date` is that day."""

COURIER_URL: Final = "https://news.example.org/rss/politics.xml"
LEDGER_URL: Final = "https://ledger.example.com/feeds/politics.xml"
HEALTH_URL: Final = "https://health.example.net/feed.xml"
FEED_LISTS: Final = (
    FeedConfig(
        topic="health-insurance",
        description="The test's health-insurance topic.",
        feeds=(
            FeedSource(url=HEALTH_URL, publisher="The Example Health Wire", review=FeedReview.COACH_REVIEWED),
        ),
        search_topics=("policy-2026-27-nhi",),
        government_providers=(SearchProviderName.FEDERAL_REGISTER, SearchProviderName.GOVINFO),
    ),
    FeedConfig(
        topic="politics",
        description="The test's politics topic.",
        feeds=(
            FeedSource(
                url=COURIER_URL, publisher="The Example Courier", review=FeedReview.AWAITING_COACH_REVIEW
            ),
            FeedSource(url=LEDGER_URL, publisher="The Example Ledger", review=FeedReview.COACH_REVIEWED),
        ),
    ),
)
"""The committed presets' two feed topics, at the fixtures' URLs; one politics feed awaits review."""

NOTHING_FOUND: Final = {
    ("api.openalex.org", "/works"): {"meta": {"count": 0}, "results": []},
    ("api.crossref.org", "/works"): {"status": "ok", "message-type": "work-list", "message": {"items": []}},
    ("www.federalregister.gov", "/api/v1/documents.json"): {"count": 0, "results": []},
}
"""An answer with nothing in it from each of the NHI preset's other providers, written by hand."""
GOVINFO_HOST: Final = "api.govinfo.gov"

DIGESTS: Final = Path("digests")
SENTINEL: Final = "SNIPPETSENTINEL"


@dataclass
class Feeds:
    """What each feed URL answers, and every request the providers and the article fetcher sent."""

    courier: str = "courier_2026-09-17.xml"
    courier_status: int = 200
    ledger_status: int = 200
    requests: list[str] = field(default_factory=list[str])
    unrecorded: list[str] = field(default_factory=list[str])
    scholarly_and_register: bool = False
    """Answer OpenAlex, Crossref and the Federal Register too, each with nothing found."""

    async def handle(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requests.append(url)
        if self.scholarly_and_register and (request.url.host, request.url.path) in NOTHING_FOUND:
            return httpx.Response(200, json=NOTHING_FOUND[(request.url.host, request.url.path)])
        answers = {
            COURIER_URL: (self.courier_status, self.courier),
            LEDGER_URL: (self.ledger_status, "ledger_2026-09-17.xml"),
            HEALTH_URL: (200, "health_wire_2026-09-17.xml"),
        }
        if url not in answers:
            self.unrecorded.append(url)
            return httpx.Response(599)
        status, name = answers[url]
        if status != 200:
            return httpx.Response(status)
        body = (FIXTURES / name).read_bytes()
        return httpx.Response(200, headers={"content-type": "application/rss+xml"}, content=body)


class NeedRecordingRouter(EveryPageRouter):
    """:class:`EveryPageRouter`, keeping the research need each `card.select` call was asked for."""

    def __init__(self) -> None:
        super().__init__()
        self.research_needs: list[str] = []

    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        if prompt.prompt_id == CARD_SELECT_PROMPT_ID:
            self.research_needs.append(str(prompt.variables["research_need"]))
        return await super().generate_structured(task_class, prompt, schema, params)


@dataclass
class Seams:
    feeds: Feeds = field(default_factory=Feeds)
    articles: ReplayTransport | None = None
    card_router: NeedRecordingRouter | None = None
    crossref: CrossrefAnswers = field(default_factory=CrossrefAnswers)
    now: datetime = NOW
    """The container's fixed clock, unless `stepping_clock`."""
    stepping_clock: bool = False
    """A container clock that moves 0.4 s each time it is read, from NOW, in place of the fixed one:
    Crossref's pacer waits on it, and waits for ever on a clock that never moves."""


class SteppingClock:
    """NOW, then 0.4 s later at every read: time passes for a pacer, and no test waits for real."""

    def __init__(self) -> None:
        self._reads = 0

    def __call__(self) -> datetime:
        self._reads += 1
        return NOW + timedelta(seconds=0.4 * self._reads)


@pytest.fixture
def seams(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Seams]:
    for name in [name for name in os.environ if name.startswith("DEBATE_")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("DEBATE_ENV", "test")
    monkeypatch.setenv("DEBATE_STORAGE__DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DEBATE_PROVIDERS__ENABLED", '["rss"]')
    monkeypatch.setenv("DEBATE_HTTP__PER_HOST_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("COLUMNS", "250")
    monkeypatch.chdir(tmp_path)
    seams = Seams()
    build = ServiceContainer.__init__

    def with_seams(self: ServiceContainer, **arguments: Any) -> None:
        build(self, **arguments)
        self.override("clock", SteppingClock() if seams.stepping_clock else lambda: seams.now)
        self.override("topic_feed_lists", FEED_LISTS)
        transport = httpx.MockTransport(seams.feeds.handle)
        self.override("discovery_transport", transport)
        self.override("article_fetch_transport", seams.articles or transport)
        if seams.card_router is not None:
            self.override("card_model_router", seams.card_router)
            self.override("crossref_transport", httpx.MockTransport(seams.crossref.handle))

    monkeypatch.setattr(ServiceContainer, "__init__", with_seams)
    yield seams
    assert seams.feeds.unrecorded == [], "a request no fixture recorded"
    if seams.articles is not None:
        assert seams.articles.unrecorded == [], "an article fetch no cassette recorded"


def daily(*arguments: str, json_output: bool = False) -> Result:
    return runner.invoke(create_app(), [*(["--json"] if json_output else []), "daily", *arguments])


def envelope(result: Result) -> dict[str, Any]:
    lines = result.stdout.splitlines()
    assert len(lines) == 1, f"JSON output must be exactly one line on stdout, got: {result.stdout!r}"
    document: dict[str, Any] = json.loads(lines[0])
    return document


def seen_set(tmp_path: Path) -> dict[str, Any] | None:
    path = tmp_path / "data" / "daily" / "seen" / "politics.json"
    if not path.exists():
        return None
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return document


WHY: Final = re.compile(r"^- Why: (.+)$", re.MULTILINE)


def without_why(markdown: str) -> tuple[str, list[str]]:
    """The Markdown with each "Why" line's text replaced by `<why>`, and those texts, unescaped."""
    whys = [re.sub(r"\\(.)", r"\1", found) for found in WHY.findall(markdown)]
    return WHY.sub("- Why: <why>", markdown), whys


def item(title: str, date: str, url: str) -> str:
    return f"{title}\n\n- Publisher: The Example Courier\n- Date: {date}\n- Why: <why>\n- URL: <{url}>\n"


REVIEW_NOTE: Final = (
    "> Feed topic politics was read with 1 feed still awaiting the coach's review: The Example Courier.\n"
)

SEPTEMBER_17_MARKDOWN: Final = (
    "# Politics daily digest: 2026-09-17\n"
    "\n"
    "- Preset: politics\n"
    "- Window: 2026-09-17 (1 day, UTC)\n"
    "- 3 new results; 0 left out as listed in an earlier digest\n"
    "- Status: COMPLETE\n"
    "\n"
    f"{REVIEW_NOTE}"
    "\n"
    "## Politics DA — Uniqueness\n"
    "\n"
    "### 1. "
    + item(
        "Farm bill likely to pass Congress before the recess",
        "2026-09-17",
        "https://news.example.org/2026/09/17/farm-bill",
    )
    + "\n### 2. "
    + item(
        "Senate Republicans block the stopgap spending measure",
        "2026-09-17",
        "https://news.example.org/2026/09/17/senate-republicans",
    )
    + "\n## Midterms DA — Uniqueness\n"
    "\n"
    "### 1. "
    + item(
        "Senate election forecast: Democrats favored to hold the chamber",
        "2026-09-17",
        "https://news.example.org/2026/09/17/senate-forecast",
    )
    + "\n## Providers\n"
    "\n"
    "Providers: COMPLETE\n"
    "\n"
    "- rss: ok, 3 results from 4 queries\n"
)
"""`daily politics --date 2026-09-17`, by hand from `courier_2026-09-17.xml` and the committed
`config/daily_templates.yaml` (v1-e08-t25): politics x bill asks `bill Congress` and keeps B; politics
x Senate asks `Senate Congress` and `Senate Republicans` and keeps I; midterms x Senate asks `Senate
election` and keeps C; midterms x bill is not searched, no template being for `bill`. Four queries.
A, which the taxonomy's `Senate vote count Senate` would keep, is not listed."""

SEPTEMBER_18_MARKDOWN: Final = (
    "# Politics daily digest: 2026-09-18\n"
    "\n"
    "- Preset: politics\n"
    "- Window: 2026-09-17 to 2026-09-18 (2 days, UTC)\n"
    "- 2 new results; 3 left out as listed in an earlier digest\n"
    "- Status: COMPLETE\n"
    "\n"
    f"{REVIEW_NOTE}"
    "\n"
    "## Politics DA — Uniqueness\n"
    "\n"
    "### 1. "
    + item(
        "Spending bill heads back to Congress, leaders say",
        "2026-09-18",
        "https://news.example.org/2026/09/18/spending-bill",
    )
    + "\n## Midterms DA — Uniqueness\n"
    "\n"
    "### 1. "
    + item(
        "Senate election polling tightens in three states",
        "2026-09-17",
        "https://news.example.org/2026/09/17/senate-election-polling",
    )
    + "\n## Providers\n"
    "\n"
    "Providers: COMPLETE\n"
    "\n"
    "- rss: ok, 5 results from 4 queries\n"
)
"""`daily politics --date 2026-09-18 --window 2d` after the 17th's: B, I and C are in the window again
and were listed on the 17th, so they are left out; G is new, and so is H, dated the 17th but first in
the feed on the 18th."""


# ------------------------------------------------------------------------------------------------
# ac1: the digest file, grouped by argument and need
# ------------------------------------------------------------------------------------------------


def test_daily_politics_writes_the_dated_digest_grouped_by_argument_and_need(
    seams: Seams, tmp_path: Path
) -> None:
    result = daily("politics", "--date", "2026-09-17")

    assert result.exit_code == ExitCode.OK, result.output
    markdown = (tmp_path / DIGESTS / "politics-2026-09-17.md").read_text(encoding="utf-8")
    shape, whys = without_why(markdown)
    assert shape == SEPTEMBER_17_MARKDOWN
    assert all(why.strip() for why in whys)
    assert sorted(path.name for path in (tmp_path / DIGESTS).iterdir()) == ["politics-2026-09-17.md"]
    assert "Digest: digests/politics-2026-09-17.md" in result.stdout
    assert "Providers: COMPLETE" in result.stdout
    assert "rss: ok, 3 results from 4 queries" in result.stdout
    assert SENTINEL not in markdown + result.output


def test_each_why_is_the_rankings_explanation_and_a_second_run_of_the_date_lists_it_again(
    seams: Seams, tmp_path: Path
) -> None:
    assert daily("politics", "--date", "2026-09-17").exit_code == ExitCode.OK
    _, whys = without_why((tmp_path / DIGESTS / "politics-2026-09-17.md").read_text(encoding="utf-8"))

    again = daily("politics", "--date", "2026-09-17", "--format", "json")

    assert again.exit_code == ExitCode.OK, again.output
    data = envelope(again)["data"]
    assert [result["explanation"] for group in data["groups"] for result in group["results"]] == whys
    assert data["new_results"] == 3
    assert data["listed_before"] == 0


def test_with_no_date_the_digest_is_for_today_by_the_clock(seams: Seams, tmp_path: Path) -> None:
    result = daily("politics")

    assert result.exit_code == ExitCode.OK, result.output
    assert (tmp_path / DIGESTS / "politics-2026-09-17.md").is_file()


# ------------------------------------------------------------------------------------------------
# The digest templates, never the taxonomy's (v1-e08-t25's ac2, the PM's ruling of 2026-11-12)
# ------------------------------------------------------------------------------------------------

DIGEST_QUERIES: Final = ["bill Congress", "Senate Congress", "Senate Republicans", "Senate election"]
"""What the committed `config/daily_templates.yaml` asks of the politics preset: the ruling's four."""

UNIQUENESS_QUERIES: Final = [
    "bill vote count Senate",
    "bill likely to pass Congress",
    "bill will not pass",
    "Senate vote count Senate",
    "Senate likely to pass Congress",
    "Senate will not pass",
    "bill midterms polling",
    "bill election forecast",
    "Senate midterms polling",
    "Senate election forecast",
]
"""The ten queries the taxonomy's politics DA and midterms DA uniqueness templates fill for the preset."""


def test_daily_asks_the_digest_templates_and_none_of_the_taxonomys_uniqueness_templates(seams: Seams) -> None:
    result = daily("politics", "--date", "2026-09-17", "--format", "json", json_output=True)

    assert result.exit_code == ExitCode.OK, result.output
    data = envelope(result)["data"]
    asked = [call["query"] for call in data["provider_calls"]]
    assert asked == DIGEST_QUERIES
    assert not set(asked) & set(UNIQUENESS_QUERIES)
    titles = {result["title"] for group in data["groups"] for result in group["results"]}
    assert "Senate vote count on the stopgap spending measure" not in titles


def test_search_still_asks_the_taxonomys_uniqueness_templates(seams: Seams) -> None:
    result = runner.invoke(
        create_app(), ["--json", "search", "Senate", "--argument", "politics-da", "--need", "uniqueness"]
    )

    document = envelope(result)
    data = document["data"] if document["data"] is not None else document["error"]["details"]
    assert [query["query"] for query in data["expansion"]["queries"]] == UNIQUENESS_QUERIES[3:6]
    assert [query["template_id"] for query in data["expansion"]["queries"]] == [
        "politics-da/uniqueness/1",
        "politics-da/uniqueness/2",
        "politics-da/uniqueness/3",
    ]


def test_the_two_groups_list_what_their_own_templates_found_and_nothing_twice(seams: Seams) -> None:
    result = daily("politics", "--date", "2026-09-17", "--format", "json", json_output=True)

    data = envelope(result)["data"]
    found = {group["heading"]: [r["url"] for r in group["results"]] for group in data["groups"]}
    assert found == {
        "Politics DA — Uniqueness": [
            "https://news.example.org/2026/09/17/farm-bill?utm_source=feed",
            "https://news.example.org/2026/09/17/senate-republicans",
        ],
        "Midterms DA — Uniqueness": ["https://news.example.org/2026/09/17/senate-forecast"],
    }


def test_an_nhi_pair_with_no_digest_templates_asks_the_taxonomys_templates_as_on_dev_and_says_so(
    seams: Seams, tmp_path: Path
) -> None:
    """The PM's ruling C (2026-11-12): a pair with no digest templates asks the taxonomy's uniqueness
    templates exactly as before this task, keeps its groups apart, and the digest names it."""
    result = daily("nhi", "--date", "2026-09-17", "--format", "json", json_output=True)

    assert result.exit_code == ExitCode.OK, result.output
    data = envelope(result)["data"]
    assert [
        call["query"] for call in data["provider_calls"] if call["provider"] == "rss"
    ] == NHI_QUERIES_ON_DEV
    assert nhi_groups(data) == NHI_GROUPS
    assert daily("nhi", "--date", "2026-09-17").exit_code == ExitCode.OK
    markdown = (tmp_path / DIGESTS / "nhi-2026-09-17.md").read_text(encoding="utf-8")
    for heading in ("Spending DA — Uniqueness", "Federalism DA — Uniqueness", "Economy DA — Uniqueness"):
        assert f"## {heading}\n\n{TAXONOMY_NOTE}\n" in markdown


def test_a_politics_digest_carries_no_such_line(seams: Seams, tmp_path: Path) -> None:
    assert daily("politics", "--date", "2026-09-17").exit_code == ExitCode.OK

    markdown = (tmp_path / DIGESTS / "politics-2026-09-17.md").read_text(encoding="utf-8")
    assert "No digest templates" not in markdown


@pytest.mark.parametrize(
    ("change", "named"),
    [
        (
            lambda document: document["groups"][0]["templates"].append({"text": "{query} vote count"}),
            "a digest template is the query and one word",
        ),
        (
            lambda document: document["groups"][1].update(argument="elections"),
            "group elections/uniqueness: the taxonomy has no argument with the id 'elections'; did you "
            "mean 'midterms-da'",
        ),
        (
            lambda document: document["groups"][1]["templates"][0].update(queries=["Senate", "House"]),
            "is for the query 'House', which no preset with this pair asks",
        ),
    ],
    ids=["a three-word template", "an alias for the argument", "a query no preset asks"],
)
def test_a_digest_templates_file_that_does_not_load_stops_every_run_naming_it(
    seams: Seams, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: Any, named: str
) -> None:
    repository = Path(__file__).resolve().parents[3]
    document = yaml.safe_load((repository / "config" / "daily_templates.yaml").read_text(encoding="utf-8"))
    change(document)
    templates = tmp_path / "daily_templates.yaml"
    templates.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    monkeypatch.setattr(container_module, "DAILY_TEMPLATES_PATH", templates)

    result = daily("politics", "--date", "2026-09-17", json_output=True)

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    error = envelope(result)["error"]
    assert named in " ".join(error["message"].split())
    assert str(templates) in error["message"]
    assert seams.feeds.requests == []


# ------------------------------------------------------------------------------------------------
# With no --date: the 24 hours before the run, dated in daily.time_zone (v1-e08-t25's ac3)
#
# The fixtures' items are on 17 and 18 September, when Chicago is UTC-5 and Los Angeles UTC-7. A run
# at 23:00 Chicago on the 17th is 04:00Z on the 18th: the case of 2026-11-11, when the UTC date sent
# the evening's digest to the next day with only the hours since UTC midnight in it.
# ------------------------------------------------------------------------------------------------


def window_line(markdown: str) -> str:
    return next(line for line in markdown.splitlines() if line.startswith("- Window: "))


def test_with_no_date_a_run_at_23_00_in_chicago_is_that_evenings_digest_of_its_24_hours(
    seams: Seams, tmp_path: Path
) -> None:
    seams.now = datetime(2026, 9, 18, 4, 0, tzinfo=UTC)

    result = daily("politics", "--format", "json", json_output=True)

    assert result.exit_code == ExitCode.OK, result.output
    data = envelope(result)["data"]
    assert (data["date"], data["file"], data["new_results"]) == (
        "2026-09-17",
        "digests/politics-2026-09-17.json",
        3,
    )
    assert data["window"] == {
        "days": 1,
        "since": "2026-09-17T04:00:00+00:00",
        "until": "2026-09-18T04:00:00+00:00",
    }
    assert sorted(path.name for path in (tmp_path / DIGESTS).iterdir()) == ["politics-2026-09-17.json"]
    seen = seen_set(tmp_path)
    assert seen is not None
    assert set(seen["urls"].values()) == {"2026-09-17"}


def test_with_no_date_a_run_at_07_00_in_chicago_reaches_into_the_evening_before(
    seams: Seams, tmp_path: Path
) -> None:
    """07:00 Chicago on the 18th is 12:00Z: the window opens at 12:00Z on the 17th, after B (09:30Z)
    and I (11:00Z) and before C and H; G is the 18th's. Each search's own order is the ranking's."""
    seams.now = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)
    seams.feeds.courier = "courier_2026-09-18.xml"

    result = daily("politics")

    assert result.exit_code == ExitCode.OK, result.output
    markdown = (tmp_path / DIGESTS / "politics-2026-09-18.md").read_text(encoding="utf-8")
    assert window_line(markdown) == (
        "- Window: 2026-09-17 07:00 to 2026-09-18 07:00 America/Chicago (the 24 hours before the run)"
    )
    sections = markdown.split("\n## ")
    assert [section.splitlines()[0] for section in sections[1:]] == [
        "Politics DA — Uniqueness",
        "Midterms DA — Uniqueness",
        "Providers",
    ]
    assert set(re.findall(r"^### \d\. (.+)$", sections[1], re.MULTILINE)) == {
        "Spending bill heads back to Congress, leaders say",
    }
    assert set(re.findall(r"^### \d\. (.+)$", sections[2], re.MULTILINE)) == {
        "Senate election polling tightens in three states",
        "Senate election forecast: Democrats favored to hold the chamber",
    }


def test_with_no_date_and_a_wider_window_it_is_that_many_days_of_24_hours(
    seams: Seams, tmp_path: Path
) -> None:
    seams.now = datetime(2026, 9, 18, 4, 0, tzinfo=UTC)

    result = daily("politics", "--window", "3d")

    assert result.exit_code == ExitCode.OK, result.output
    assert sorted(path.name for path in (tmp_path / DIGESTS).iterdir()) == ["politics-2026-09-17.md"]
    markdown = (tmp_path / DIGESTS / "politics-2026-09-17.md").read_text(encoding="utf-8")
    assert window_line(markdown) == (
        "- Window: 2026-09-14 23:00 to 2026-09-17 23:00 America/Chicago (the 72 hours before the run)"
    )


@pytest.mark.parametrize(
    ("zone", "named"),
    [(None, "politics-2026-09-18.md"), ("America/Los_Angeles", "politics-2026-09-17.md")],
    ids=["chicago by default, 00:30 on the 18th", "los angeles, 22:30 on the 17th"],
)
def test_with_no_date_the_digest_is_dated_in_the_configured_zone(
    seams: Seams, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, zone: str | None, named: str
) -> None:
    """05:30Z on the 18th. Either way the window is 05:30Z on the 17th to 05:30Z on the 18th, which
    holds B, I and C."""
    if zone is not None:
        monkeypatch.setenv("DEBATE_DAILY__TIME_ZONE", zone)
    seams.now = datetime(2026, 9, 18, 5, 30, tzinfo=UTC)

    result = daily("politics", "--format", "json", json_output=True)

    assert result.exit_code == ExitCode.OK, result.output
    data = envelope(result)["data"]
    assert sorted(path.name for path in (tmp_path / DIGESTS).iterdir()) == [named.replace(".md", ".json")]
    assert (data["window"]["since"], data["window"]["until"], data["new_results"]) == (
        "2026-09-17T05:30:00+00:00",
        "2026-09-18T05:30:00+00:00",
        3,
    )


def test_a_time_zone_the_database_does_not_know_stops_the_run_naming_the_setting(
    seams: Seams, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_DAILY__TIME_ZONE", "America/Springfield")

    result = daily("politics", "--date", "2026-09-17", json_output=True)

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    error = envelope(result)["error"]
    assert error["details"]["field"] == "daily.time_zone"
    assert "daily.time_zone" in error["message"]
    assert seams.feeds.requests == []
    assert not (tmp_path / DIGESTS).exists()


def test_a_date_keeps_its_whole_utc_day_whatever_the_clock_says(seams: Seams, tmp_path: Path) -> None:
    seams.now = datetime(2026, 9, 19, 4, 0, tzinfo=UTC)

    result = daily("politics", "--date", "2026-09-17")

    assert result.exit_code == ExitCode.OK, result.output
    shape, _ = without_why((tmp_path / DIGESTS / "politics-2026-09-17.md").read_text(encoding="utf-8"))
    assert shape == SEPTEMBER_17_MARKDOWN


# ------------------------------------------------------------------------------------------------
# ac2: the next date omits what the previous day listed
# ------------------------------------------------------------------------------------------------


def test_the_next_date_omits_results_the_previous_day_listed(seams: Seams, tmp_path: Path) -> None:
    assert daily("politics", "--date", "2026-09-17").exit_code == ExitCode.OK
    first = (tmp_path / DIGESTS / "politics-2026-09-17.md").read_bytes()
    seams.feeds.courier = "courier_2026-09-18.xml"

    result = daily("politics", "--date", "2026-09-18", "--window", "2d")

    assert result.exit_code == ExitCode.OK, result.output
    shape, _ = without_why((tmp_path / DIGESTS / "politics-2026-09-18.md").read_text(encoding="utf-8"))
    assert shape == SEPTEMBER_18_MARKDOWN
    assert (tmp_path / DIGESTS / "politics-2026-09-17.md").read_bytes() == first


def test_the_seen_set_is_in_the_data_directory_by_canonical_url_and_never_beside_the_digests(
    seams: Seams, tmp_path: Path
) -> None:
    assert daily("politics", "--date", "2026-09-17").exit_code == ExitCode.OK

    assert seen_set(tmp_path) == {
        "schema_version": 1,
        "preset": "politics",
        "urls": {
            "https://news.example.org/2026/09/17/farm-bill": "2026-09-17",
            "https://news.example.org/2026/09/17/senate-forecast": "2026-09-17",
            "https://news.example.org/2026/09/17/senate-republicans": "2026-09-17",
        },
        "dois": {},
    }
    gc.collect()
    outside_data = [
        path.relative_to(tmp_path).as_posix()
        for path in tmp_path.rglob("*")
        if path.is_file() and not path.is_relative_to(tmp_path / "data")
    ]
    assert outside_data == ["digests/politics-2026-09-17.md"]


def test_a_run_that_cannot_write_its_digest_marks_nothing_seen(seams: Seams, tmp_path: Path) -> None:
    (tmp_path / DIGESTS).mkdir()
    (tmp_path / DIGESTS).chmod(0o500)
    try:
        failed = daily("politics", "--date", "2026-09-17")
    finally:
        (tmp_path / DIGESTS).chmod(0o700)

    assert failed.exit_code != ExitCode.OK
    assert not (tmp_path / DIGESTS / "politics-2026-09-17.md").exists()
    assert seen_set(tmp_path) is None
    again = daily("politics", "--date", "2026-09-18", "--window", "2d", json_output=True)
    assert again.exit_code == ExitCode.OK, again.output
    assert envelope(again)["data"]["new_results"] == 3


def test_a_digest_no_provider_answered_is_not_written_and_marks_nothing(seams: Seams, tmp_path: Path) -> None:
    seams.feeds.courier_status = 503
    seams.feeds.ledger_status = 503

    result = daily("politics", "--date", "2026-09-17", json_output=True)

    assert result.exit_code == ExitCode.RETRIEVAL_FAILURE, result.output
    error = envelope(result)["error"]
    assert (error["code"], error["exit_code"]) == ("SEARCH_FAILED", 3)
    assert error["details"]["file"] is None
    assert not (tmp_path / DIGESTS).exists()
    assert seen_set(tmp_path) is None


# ------------------------------------------------------------------------------------------------
# ac3: presets validate on load, and an unknown one exits 2 listing them
# ------------------------------------------------------------------------------------------------


def test_an_unknown_preset_exits_2_listing_the_presets_and_searches_nothing(
    seams: Seams, tmp_path: Path
) -> None:
    result = daily("data-centers", "--date", "2026-09-17")

    assert result.exit_code == ExitCode.USAGE_ERROR, result.output
    assert "no daily preset named 'data-centers'; the presets are politics, nhi" in " ".join(
        result.stderr.split()
    )
    assert seams.feeds.requests == []
    assert not (tmp_path / DIGESTS).exists()


def test_an_invented_preset_in_the_file_runs_with_no_code_change(
    seams: Seams, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = Path(__file__).resolve().parents[3]
    document = yaml.safe_load((repository / "config" / "daily_presets.yaml").read_text(encoding="utf-8"))
    document["presets"].append(
        {
            "name": "senate-watch",
            "label": "Senate watch",
            "description": "An invented preset the coach might add.",
            "queries": ["Senate"],
            "pairs": [{"argument": "midterms-da", "need": "uniqueness"}],
            "providers": ["rss"],
            "feed_topics": ["politics"],
        }
    )
    presets = tmp_path / "presets.yaml"
    presets.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    monkeypatch.setattr(container_module, "DAILY_PRESETS_PATH", presets)

    result = daily("senate-watch", "--date", "2026-09-17", json_output=True)

    assert result.exit_code == ExitCode.OK, result.output
    data = envelope(result)["data"]
    assert [group["heading"] for group in data["groups"]] == ["Midterms DA — Uniqueness"]
    assert [result["title"] for result in data["groups"][0]["results"]] == [
        "Senate election forecast: Democrats favored to hold the chamber"
    ]
    assert (tmp_path / DIGESTS / "senate-watch-2026-09-17.md").is_file()


def test_a_preset_file_that_names_a_missing_feed_topic_stops_every_run_naming_it(
    seams: Seams, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = Path(__file__).resolve().parents[3]
    document = yaml.safe_load((repository / "config" / "daily_presets.yaml").read_text(encoding="utf-8"))
    document["presets"][1]["feed_topics"] = ["space"]
    presets = tmp_path / "presets.yaml"
    presets.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    monkeypatch.setattr(container_module, "DAILY_PRESETS_PATH", presets)

    result = daily("politics", "--date", "2026-09-17", json_output=True)

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    error = envelope(result)["error"]
    assert "preset 'nhi': no feed topic 'space' in config/feeds/" in error["message"]
    assert seams.feeds.requests == []


@pytest.mark.parametrize("window", ["0d", "32d", "1w", "yesterday"])
def test_a_window_that_is_not_1d_to_31d_exits_2(seams: Seams, window: str) -> None:
    result = daily("politics", "--window", window)

    assert result.exit_code == ExitCode.USAGE_ERROR, result.output
    assert "--window" in result.stderr
    assert seams.feeds.requests == []


# ------------------------------------------------------------------------------------------------
# ac4: --format json, and the provider footer reports partial results
# ------------------------------------------------------------------------------------------------


def test_format_json_writes_the_digest_as_json_and_prints_it(seams: Seams, tmp_path: Path) -> None:
    result = daily("politics", "--date", "2026-09-17", "--format", "json")

    assert result.exit_code == ExitCode.OK, result.output
    document = envelope(result)
    assert (document["status"], document["command"]) == ("ok", "daily")
    data = document["data"]
    written = json.loads((tmp_path / DIGESTS / "politics-2026-09-17.json").read_text(encoding="utf-8"))
    assert {**written, "file": "digests/politics-2026-09-17.json"} == data
    assert not (tmp_path / DIGESTS / "politics-2026-09-17.md").exists()
    assert (data["preset"], data["date"], data["status"], data["topic"]) == (
        "politics",
        "2026-09-17",
        "COMPLETE",
        None,
    )
    assert data["window"] == {
        "days": 1,
        "since": "2026-09-17T00:00:00+00:00",
        "until": "2026-09-17T23:59:59.999999+00:00",
    }
    assert [
        (group["heading"], [(r["title"], r["publisher"], r["date"], r["url"]) for r in group["results"]])
        for group in data["groups"]
    ] == [
        (
            "Politics DA — Uniqueness",
            [
                (
                    "Farm bill likely to pass Congress before the recess",
                    "The Example Courier",
                    "2026-09-17",
                    "https://news.example.org/2026/09/17/farm-bill?utm_source=feed",
                ),
                (
                    "Senate Republicans block the stopgap spending measure",
                    "The Example Courier",
                    "2026-09-17",
                    "https://news.example.org/2026/09/17/senate-republicans",
                ),
            ],
        ),
        (
            "Midterms DA — Uniqueness",
            [
                (
                    "Senate election forecast: Democrats favored to hold the chamber",
                    "The Example Courier",
                    "2026-09-17",
                    "https://news.example.org/2026/09/17/senate-forecast",
                )
            ],
        ),
    ]
    assert data["feed_topics"] == [{"topic": "politics", "awaiting_coach_review": ["The Example Courier"]}]
    assert data["providers"] == [
        {"provider": "rss", "outcome": "ok", "queries": 4, "failed": 0, "results": 3, "reasons": []}
    ]
    assert len(data["provider_calls"]) == 4
    assert [(s["query"], s["argument"], s["need"]) for s in data["searches"]] == [
        ("bill", "politics-da", "uniqueness"),
        ("Senate", "politics-da", "uniqueness"),
        ("Senate", "midterms-da", "uniqueness"),
    ]
    assert [group["asked_taxonomy_templates"] for group in data["groups"]] == [False, False]
    assert SENTINEL not in result.stdout


def test_a_feed_that_fails_makes_the_digest_partial_and_the_footer_says_so(
    seams: Seams, tmp_path: Path
) -> None:
    seams.feeds.ledger_status = 503

    result = daily("politics", "--date", "2026-09-17")

    assert result.exit_code == ExitCode.SEARCH_PARTIAL, result.output
    assert "SEARCH_PARTIAL" in result.stderr
    markdown = (tmp_path / DIGESTS / "politics-2026-09-17.md").read_text(encoding="utf-8")
    footer = markdown[markdown.index("## Providers") :].splitlines()
    assert footer[2] == "Providers: PARTIAL, results may be missing"
    assert footer[4].startswith("- rss: partial, 3 results from 4 queries: ")
    assert "The Example Ledger" in footer[4]
    assert "- Status: PARTIAL" in markdown
    assert "Providers: PARTIAL, results may be missing" in result.stdout
    assert seen_set(tmp_path) is not None, "a partial digest is written, so its results count as listed"


def test_a_partial_digest_in_json_carries_the_same_statuses(seams: Seams) -> None:
    seams.feeds.ledger_status = 503

    result = daily("politics", "--date", "2026-09-17", "--format", "json")

    assert result.exit_code == ExitCode.SEARCH_PARTIAL, result.output
    error = envelope(result)["error"]
    assert (error["code"], error["exit_code"]) == ("SEARCH_PARTIAL", 6)
    details = error["details"]
    assert details["status"] == "PARTIAL"
    assert details["file"] == "digests/politics-2026-09-17.json"
    [rss] = details["providers"]
    assert (rss["provider"], rss["outcome"], rss["results"]) == ("rss", "partial", 3)
    assert any("The Example Ledger" in reason for reason in rss["reasons"])
    assert {call["partial"] for call in details["provider_calls"]} == {True}


# ------------------------------------------------------------------------------------------------
# Feed topics: each preset reads its own
# ------------------------------------------------------------------------------------------------


def test_a_politics_digest_reads_only_the_politics_feeds(seams: Seams) -> None:
    assert daily("politics", "--date", "2026-09-17").exit_code == ExitCode.OK

    assert set(seams.feeds.requests) == {COURIER_URL, LEDGER_URL}


NOT_ENABLED_UNCOUNTED: Final = (
    "not counted as partial: not enabled in settings (providers.enabled); enable it in providers.enabled"
)
"""A preset provider the profile does not enable, on every query (v1-e07-t23, the PM's ruling on
v1-e07-t15's follow-up 1)."""


NHI_GROUPS: Final = [
    (
        "Spending DA — Uniqueness",
        True,
        ["Health insurance subsidies at the center of the federal spending debate in Congress"],
    ),
    ("Federalism DA — Uniqueness", True, ["States lead on health insurance policy as Washington stalls"]),
    ("Economy DA — Uniqueness", True, []),
]
"""The nhi preset's pairs have no digest templates, so each asks the taxonomy's uniqueness templates as
before v1-e08-t25 (the PM's ruling C of 2026-11-12), and the digest names each. The groups are dev's
own, as `test_daily_command.py` pinned them on dev at 5c71e42."""

NHI_QUERIES_ON_DEV: Final = [
    "health insurance federal spending debate Congress",
    "Congress spending restraint health insurance",
    "states lead health insurance policy",
    "health insurance state innovation federalism",
    "health insurance clean federal and state separation now",
    "health insurance federalism healthy now",
    "health insurance economic growth forecast",
    "health insurance recession risk",
]
"""What `daily nhi --date 2026-09-17` asked the feeds on dev at 5c71e42, before this task: recorded by
running dev's own code in a scratch worktree on 2026-11-12, not from this branch's output."""

TAXONOMY_NOTE: Final = (
    "> No digest templates for this pair in config/daily_templates.yaml: its searches asked the "
    "taxonomy's templates."
)


def nhi_groups(data: dict[str, Any]) -> list[tuple[str, bool | None, list[str]]]:
    return [
        (
            group["heading"],
            group.get("asked_taxonomy_templates"),
            [result["title"] for result in group["results"]],
        )
        for group in data["groups"]
    ]


def test_an_nhi_digest_reads_only_the_health_insurance_feeds_and_names_its_uncounted_providers(
    seams: Seams, tmp_path: Path
) -> None:
    """The test profile enables only `rss`. The preset's other four providers are configuration the
    profile leaves off: named with `enable it in providers.enabled`, not counted, so the digest is
    COMPLETE (it was PARTIAL until v1-e07-t23)."""
    result = daily("nhi", "--date", "2026-09-17", "--format", "json")

    assert set(seams.feeds.requests) == {HEALTH_URL}
    assert result.exit_code == ExitCode.OK, result.output
    details = envelope(result)["data"]
    assert (details["topic"], details["status"]) == ("policy-2026-27-nhi", "COMPLETE")
    assert [(p["provider"], p["outcome"], p["reasons"]) for p in details["providers"]] == [
        ("openalex", "not configured", [NOT_ENABLED_UNCOUNTED]),
        ("crossref", "not configured", [NOT_ENABLED_UNCOUNTED]),
        ("rss", "ok", []),
        ("federal_register", "not configured", [NOT_ENABLED_UNCOUNTED]),
        ("govinfo", "not configured", [NOT_ENABLED_UNCOUNTED]),
    ]
    assert nhi_groups(details) == NHI_GROUPS
    assert (tmp_path / "data" / "daily" / "seen" / "nhi.json").is_file()


GOVINFO_NOT_COUNTED: Final = (
    "govinfo: not configured on 8 of 8 queries: not counted as partial: no api.data.gov key "
    "(DEBATE_PROVIDERS__API_DATA_GOV_KEY); get a free key at api.data.gov/signup to ask GovInfo"
)


def test_an_nhi_digest_without_the_api_data_gov_key_names_govinfo_not_configured_and_is_complete(
    seams: Seams, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The coach's preset is configuration, not a request by name (the PM's ruling 3 on v1-e07-t15):
    GovInfo, enabled with no key, is named with its cure and does not make the digest partial. Every
    other provider of the preset is enabled and answers. The contact email is an invented one, so that
    Crossref's pace is not what this test is about."""
    seams.feeds.scholarly_and_register = True
    seams.stepping_clock = True
    monkeypatch.setenv(
        "DEBATE_PROVIDERS__ENABLED", '["openalex", "crossref", "rss", "federal_register", "govinfo"]'
    )
    monkeypatch.setenv("DEBATE_PROVIDERS__CONTACT_EMAIL", "invented-t15@example.org")

    result = daily("nhi", "--date", "2026-09-17", "--format", "json")

    assert result.exit_code == ExitCode.OK, result.output
    data = envelope(result)["data"]
    assert data["status"] == "COMPLETE"
    assert [(p["provider"], p["outcome"], p["reasons"]) for p in data["providers"]] == [
        ("openalex", "ok", []),
        ("crossref", "ok", []),
        ("rss", "ok", []),
        ("federal_register", "ok", []),
        ("govinfo", "not configured", [GOVINFO_NOT_COUNTED.split(": ", 2)[2]]),
    ]
    assert nhi_groups(data) == NHI_GROUPS
    again = daily("nhi", "--date", "2026-09-17")
    assert again.exit_code == ExitCode.OK, again.output
    markdown = (tmp_path / DIGESTS / "nhi-2026-09-17.md").read_text(encoding="utf-8")
    assert "- Status: COMPLETE\n" in markdown
    assert markdown.endswith(f"- {GOVINFO_NOT_COUNTED}\n")
    assert GOVINFO_HOST not in {httpx.URL(url).host for url in seams.feeds.requests}


# ------------------------------------------------------------------------------------------------
# --auto-cut N
# ------------------------------------------------------------------------------------------------

NEWS_PAGE: Final = (
    "https://www.dailymeridian.example/science/2026/09/14/mammoth-revival-years-away?utm_source=newsletter"
)
THINK_TANK_PAGE: Final = "https://www.harwell-institute.example/research/opportunity-cost-of-de-extinction"
PAYWALLED_PAGE: Final = "https://www.harborreview.example/politics/2026/10/inside-the-tariff-talks"


@pytest.fixture
def cutting(seams: Seams) -> Seams:
    """`seams` for `--auto-cut`: the courier's items are at the HTTP cassettes' pages."""
    seams.feeds.courier = "courier_auto_cut.xml"
    seams.articles = ReplayTransport(load_cassette(name) for name in cassette_names())
    seams.card_router = NeedRecordingRouter()
    return seams


def test_auto_cut_hands_the_new_results_to_the_batch_each_groups_first_then_the_next(
    cutting: Seams, tmp_path: Path
) -> None:
    result = daily("politics", "--date", "2026-09-17", "--auto-cut", "2")

    assert result.exit_code == ExitCode.OK, result.output
    report = json.loads((tmp_path / DIGESTS / "report.json").read_text(encoding="utf-8"))
    assert [(entry["rank"], entry["url"], entry["status"]) for entry in report["entries"]] == [
        (1, NEWS_PAGE, "VERIFIED"),
        (2, PAYWALLED_PAGE, "SKIPPED"),
        (3, THINK_TANK_PAGE, "VERIFIED"),
    ]
    assert (report["preset"], report["date"], report["digest"]) == (
        "politics",
        "2026-09-17",
        "digests/politics-2026-09-17.md",
    )
    assert (report["wanted"], report["verified"], report["complete"]) == (2, 2, True)
    assert report["block"] == "Politics daily digest: 2026-09-17"
    bundle = tmp_path / DIGESTS / "politics-2026-09-17.docx"
    paragraphs = [paragraph.text for paragraph in docx.Document(str(bundle)).paragraphs]
    assert paragraphs[0] == "Politics daily digest: 2026-09-17"
    assert paragraphs.count(EVERY_PAGE_TAG) == 2
    assert (tmp_path / DIGESTS / "politics-2026-09-17.manifest.json").is_file()
    assert (tmp_path / DIGESTS / "politics-2026-09-17.md").is_file()
    assert "Digest: digests/politics-2026-09-17.md" in result.stdout
    assert "2 of 2 cards VERIFIED for Politics daily digest: 2026-09-17" in result.stdout


def test_each_auto_cut_card_is_cut_for_the_need_its_search_was_for(cutting: Seams) -> None:
    result = daily("politics", "--date", "2026-09-17", "--auto-cut", "2")

    assert result.exit_code == ExitCode.OK, result.output
    router = cutting.card_router
    assert router is not None
    assert sorted(router.research_needs) == [
        "Politics DA: Uniqueness for Senate: Where things stand now, before the plan or action.",
        "Politics DA: Uniqueness for bill: Where things stand now, before the plan or action.",
    ]


def test_auto_cut_with_no_new_results_is_short_and_writes_no_bundle(cutting: Seams, tmp_path: Path) -> None:
    assert daily("politics", "--date", "2026-09-17").exit_code == ExitCode.OK

    result = daily("politics", "--date", "2026-09-18", "--window", "2d", "--auto-cut", "1")

    assert result.exit_code == ExitCode.AUTO_CUT_SHORT, result.output
    assert not (tmp_path / DIGESTS / "politics-2026-09-18.docx").exists()
    report = json.loads((tmp_path / DIGESTS / "report.json").read_text(encoding="utf-8"))
    assert report["entries"] == []


# ------------------------------------------------------------------------------------------------
# Help
# ------------------------------------------------------------------------------------------------


def test_daily_help_documents_every_flag_and_exit_code(seams: Seams) -> None:
    result = runner.invoke(create_app(), ["daily", "--help"])

    assert result.exit_code == 0, result.output
    for text in ("--date", "--window", "--format", "--auto-cut", "--digest-dir", "0  complete", "6  partial"):
        assert text in result.stdout
