"""The operator's feed check: one line per feed with counts, and nothing from any entry."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Final

import httpx
import pytest

from debate_core.integrations.discovery import feed_check
from debate_core.integrations.discovery.feed_check import FeedCheck, check_feeds, render
from debate_core.integrations.discovery.feed_config import FeedConfig, FeedReview, FeedSource

pytestmark = pytest.mark.anyio

FIXTURES: Final = Path(__file__).resolve().parents[2] / "fixtures" / "discovery" / "feeds"
RSS_URL: Final = "https://news.example.org/rss/politics.xml"
ATOM_URL: Final = "https://www.example.com/atom/health.xml"
GONE_URL: Final = "https://gone.example.net/feed"
HOSTILE_URL: Final = "https://hostile.example.net/feed"
TOPICS: Final = (
    FeedConfig(
        topic="politics",
        description="Politics.",
        feeds=(
            FeedSource(url=RSS_URL, publisher="Example Courier", review=FeedReview.AWAITING_COACH_REVIEW),
            FeedSource(url=GONE_URL, publisher="Gone Gazette", review=FeedReview.AWAITING_COACH_REVIEW),
        ),
    ),
    FeedConfig(
        topic="health-insurance",
        description="Policy.",
        feeds=(
            FeedSource(
                url=ATOM_URL, publisher="Example Health Ledger", review=FeedReview.AWAITING_COACH_REVIEW
            ),
            FeedSource(url=HOSTILE_URL, publisher="Hostile Herald", review=FeedReview.AWAITING_COACH_REVIEW),
        ),
    ),
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def client() -> httpx.AsyncClient:
    answers = {
        RSS_URL: httpx.Response(200, content=(FIXTURES / "publisher_rss.xml").read_bytes()),
        ATOM_URL: httpx.Response(200, content=(FIXTURES / "publisher_atom.xml").read_bytes()),
        GONE_URL: httpx.Response(404),
        HOSTILE_URL: httpx.Response(200, content=(FIXTURES / "entity_expansion.xml").read_bytes()),
    }
    return httpx.AsyncClient(transport=httpx.MockTransport(lambda request: answers[str(request.url)]))


async def test_each_feed_is_fetched_once_and_counted() -> None:
    async with client() as http:
        checks = await check_feeds(TOPICS, http)
    assert checks == [
        FeedCheck("politics", "Example Courier", RSS_URL, "HTTP 200", 11, 9),
        FeedCheck("politics", "Gone Gazette", GONE_URL, "HTTP 404: the provider refused the request", 0, 0),
        FeedCheck("health-insurance", "Example Health Ledger", ATOM_URL, "HTTP 200", 5, 3),
        FeedCheck(
            "health-insurance",
            "Hostile Herald",
            HOSTILE_URL,
            "unreadable feed: refused: EntitiesForbidden",
            0,
            0,
        ),
    ]


async def test_the_report_prints_counts_and_nothing_from_an_entry() -> None:
    async with client() as http:
        checks = await check_feeds(TOPICS, http)
    out = io.StringIO()
    render(checks, out)
    text = out.getvalue()
    lines = text.splitlines()
    assert lines[0].split() == ["topic", "publisher", "status", "entries", "dated", "url"]
    assert lines[1].split() == ["politics", "Example", "Courier", "HTTP", "200", "11", "9", RSS_URL]
    assert lines[-1] == "4 feeds checked, 2 failed"
    for title_word in ("Senate", "Medicaid", "mergers", "premiums", "lol"):
        assert title_word not in text


def test_main_exits_one_when_a_feed_failed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    async def run(feeds_dir: Path) -> list[FeedCheck]:
        assert feeds_dir == tmp_path
        return [FeedCheck("politics", "Gone Gazette", GONE_URL, "HTTP 404", 0, 0)]

    monkeypatch.setattr(feed_check, "_run", run)
    assert feed_check.main(["--feeds-dir", str(tmp_path)]) == 1

    async def all_well(feeds_dir: Path) -> list[FeedCheck]:
        return [FeedCheck("politics", "Example Courier", RSS_URL, "HTTP 200", 3, 3)]

    monkeypatch.setattr(feed_check, "_run", all_well)
    assert feed_check.main(["--feeds-dir", str(tmp_path)]) == 0
