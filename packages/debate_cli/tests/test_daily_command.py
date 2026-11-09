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
from datetime import UTC, datetime
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

    async def handle(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requests.append(url)
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
        self.override("clock", lambda: NOW)
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
        "Senate vote count on the stopgap spending measure",
        "2026-09-17",
        "https://news.example.org/2026/09/17/senate-vote-count",
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
    "- rss: ok, 3 results from 10 queries\n"
)
"""`daily politics --date 2026-09-17`, by hand from `courier_2026-09-17.xml`: politics x bill keeps B,
politics x Senate keeps A (E is a week old), midterms x Senate keeps C. Ten queries: three politics DA
templates and two midterms DA templates for each of the two queries."""

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
        "Spending bill will not pass the House, leaders say",
        "2026-09-18",
        "https://news.example.org/2026/09/18/spending-bill",
    )
    + "\n## Midterms DA — Uniqueness\n"
    "\n"
    "### 1. "
    + item(
        "Senate midterms polling tightens in three states",
        "2026-09-17",
        "https://news.example.org/2026/09/17/senate-midterms-polling",
    )
    + "\n## Providers\n"
    "\n"
    "Providers: COMPLETE\n"
    "\n"
    "- rss: ok, 5 results from 10 queries\n"
)
"""`daily politics --date 2026-09-18 --window 2d` after the 17th's: B, A and C are in the window again
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
    assert "rss: ok, 3 results from 10 queries" in result.stdout
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
            "https://news.example.org/2026/09/17/senate-vote-count": "2026-09-17",
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
                    "Senate vote count on the stopgap spending measure",
                    "The Example Courier",
                    "2026-09-17",
                    "https://news.example.org/2026/09/17/senate-vote-count",
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
        {"provider": "rss", "outcome": "ok", "queries": 10, "failed": 0, "results": 3, "reasons": []}
    ]
    assert len(data["provider_calls"]) == 10
    assert [(s["query"], s["argument"], s["need"]) for s in data["searches"]] == [
        ("bill", "politics-da", "uniqueness"),
        ("Senate", "politics-da", "uniqueness"),
        ("bill", "midterms-da", "uniqueness"),
        ("Senate", "midterms-da", "uniqueness"),
    ]
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
    assert footer[4].startswith("- rss: partial, 3 results from 10 queries: ")
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


def test_an_nhi_digest_reads_only_the_health_insurance_feeds_and_names_its_unasked_providers(
    seams: Seams, tmp_path: Path
) -> None:
    result = daily("nhi", "--date", "2026-09-17", "--format", "json")

    assert set(seams.feeds.requests) == {HEALTH_URL}
    assert result.exit_code == ExitCode.SEARCH_PARTIAL, result.output
    details = envelope(result)["error"]["details"]
    assert details["topic"] == "policy-2026-27-nhi"
    assert [(p["provider"], p["outcome"]) for p in details["providers"]] == [
        ("openalex", "not configured"),
        ("crossref", "not configured"),
        ("rss", "ok"),
        ("federal_register", "not configured"),
        ("govinfo", "not configured"),
    ]
    assert [(group["heading"], [r["title"] for r in group["results"]]) for group in details["groups"]] == [
        (
            "Spending DA — Uniqueness",
            ["Health insurance subsidies at the center of the federal spending debate in Congress"],
        ),
        ("Federalism DA — Uniqueness", ["States lead on health insurance policy as Washington stalls"]),
        ("Economy DA — Uniqueness", []),
    ]
    assert (tmp_path / "data" / "daily" / "seen" / "nhi.json").is_file()


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
