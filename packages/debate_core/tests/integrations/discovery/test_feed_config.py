"""The coach's feed lists: the committed starter set loads, and a mistake fails naming the file."""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest

from debate_core.integrations.discovery.feed_config import (
    FeedConfig,
    FeedConfigError,
    FeedReview,
    FeedSource,
    feeds_of,
    load_feed_config,
    load_feed_directory,
)

REPOSITORY: Final = Path(__file__).resolve().parents[5]
CONFIG_FEEDS: Final = REPOSITORY / "config" / "feeds"


def write(directory: Path, name: str, text: str) -> Path:
    path = directory / name
    path.write_text(text, encoding="utf-8")
    return path


VALID: Final = """\
topic: politics
description: A test topic.
feeds:
  - url: https://news.example.org/rss/politics.xml
    publisher: Example Courier
    review: awaiting_coach_review
"""


def test_every_committed_feed_list_loads() -> None:
    topics = load_feed_directory(CONFIG_FEEDS)
    assert {topic.topic for topic in topics} >= {"politics", "health-insurance"}


COACH_REVIEWED_2026_11_04: Final = {
    ("politics", "https://feeds.npr.org/1014/rss.xml", "NPR"),
    ("politics", "https://www.pbs.org/newshour/feeds/rss/politics", "PBS NewsHour"),
    ("politics", "https://rss.politico.com/politics-news.xml", "Politico"),
    ("politics", "https://thehill.com/homenews/feed/", "The Hill"),
    ("politics", "https://rollcall.com/feed/", "Roll Call"),
    ("health-insurance", "https://kffhealthnews.org/feed/", "KFF Health News"),
    ("health-insurance", "https://feeds.npr.org/1128/rss.xml", "NPR"),
    ("health-insurance", "https://www.statnews.com/feed/", "STAT"),
}
"""The eight starter feeds the coach reviewed and kept on 2026-11-04 (v1-e07-t14's PM context)."""


def test_the_coach_reviewed_every_committed_feed_and_google_news_is_off() -> None:
    """Every committed feed is one the coach kept; nothing claims a review the coach has not given."""
    committed: set[tuple[str, str, str]] = set()
    for topic in load_feed_directory(CONFIG_FEEDS):
        assert topic.feeds, f"{topic.topic} lists no feeds"
        assert all(feed.review is FeedReview.COACH_REVIEWED for feed in topic.feeds), topic.topic
        assert topic.google_news.enabled is False, topic.topic
        committed |= {(topic.topic, feed.url, feed.publisher) for feed in topic.feeds}
    assert committed == COACH_REVIEWED_2026_11_04


def test_a_valid_file_loads(tmp_path: Path) -> None:
    config = load_feed_config(write(tmp_path, "politics.yaml", VALID))
    assert config.feeds == (
        FeedSource(
            url="https://news.example.org/rss/politics.xml",
            publisher="Example Courier",
            review=FeedReview.AWAITING_COACH_REVIEW,
        ),
    )
    assert config.google_news.enabled is False
    assert (config.google_news.language, config.google_news.country, config.google_news.edition) == (
        "en-US",
        "US",
        "US:en",
    )


@pytest.mark.parametrize(
    ("text", "complaint"),
    [
        pytest.param(VALID + "goggle_news:\n  enabled: true\n", "goggle_news", id="unknown-key"),
        pytest.param(VALID.replace("https://news", "ftp://news"), "absolute http", id="not-http"),
        pytest.param(
            VALID.replace("https://news.example.org/rss/politics.xml", "/rss/politics.xml"),
            "absolute http",
            id="relative",
        ),
        pytest.param(VALID.replace("awaiting_coach_review", "verified"), "review", id="unknown-review"),
        pytest.param(
            VALID.replace("topic: politics", "topic: health-insurance"), "does not match", id="topic-not-file"
        ),
        pytest.param(
            VALID
            + "  - url: https://news.example.org/rss/politics.xml\n"
            + "    publisher: Again\n    review: coach_reviewed\n",
            "listed twice",
            id="duplicate",
        ),
        pytest.param("topic: [unclosed\n", "cannot be read", id="not-yaml"),
    ],
)
def test_a_mistake_fails_the_load_naming_the_file(tmp_path: Path, text: str, complaint: str) -> None:
    path = write(tmp_path, "politics.yaml", text)
    with pytest.raises(FeedConfigError, match=complaint) as raised:
        load_feed_config(path)
    assert str(path) in str(raised.value)


def test_a_missing_directory_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(FeedConfigError, match="no such feed directory"):
        load_feed_directory(tmp_path / "absent")


def test_a_feed_on_two_topics_is_read_once() -> None:
    shared = FeedSource(url="https://a.example.org/feed", publisher="A", review=FeedReview.COACH_REVIEWED)
    other = FeedSource(url="https://b.example.org/feed", publisher="B", review=FeedReview.COACH_REVIEWED)
    first = FeedConfig(topic="one", description="One.", feeds=(shared,))
    second = FeedConfig(topic="two", description="Two.", feeds=(other, shared))
    assert feeds_of((first, second)) == (shared, other)
