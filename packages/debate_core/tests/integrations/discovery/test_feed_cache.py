"""The feed cache: what it keeps, where, and that a broken file only costs a conditional request."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import pytest

from debate_core.integrations.discovery.feed_cache import (
    CachedFeed,
    FeedCache,
    FileFeedCache,
    InMemoryFeedCache,
    cache_file_name,
)
from debate_core.integrations.discovery.feed_parsing import FeedEntry

URL: Final = "https://news.example.org/rss/politics.xml"
ENTRY: Final = FeedEntry(
    title="Senate panel advances health insurance subsidy bill",
    link="https://news.example.org/2026/10/20/senate-subsidy-bill",
    entry_id="courier-1001",
    published_at=datetime(2026, 10, 20, 14, 5, tzinfo=UTC),
    authors=("Dana Whitfield",),
    snippet="The health insurance subsidies would expire in January without a vote.",
)


def a_feed(url: str = URL) -> CachedFeed:
    return CachedFeed(
        url=url, etag='"courier-v1"', last_modified="Tue, 20 Oct 2026 13:00:00 GMT", entries=(ENTRY,)
    )


@pytest.mark.parametrize(
    "make", [InMemoryFeedCache, lambda: FileFeedCache(Path("unused"))], ids=["memory", "file"]
)
def test_both_caches_are_feed_caches(make: object) -> None:
    assert callable(make)
    assert isinstance(make(), FeedCache)


def test_conditional_headers_carry_each_validator_kept() -> None:
    assert a_feed().conditional_headers == {
        "If-None-Match": '"courier-v1"',
        "If-Modified-Since": "Tue, 20 Oct 2026 13:00:00 GMT",
    }
    assert CachedFeed(url=URL, etag='"x"').conditional_headers == {"If-None-Match": '"x"'}
    assert CachedFeed(url=URL).conditional_headers == {}


def test_a_file_cache_round_trips_one_json_file_per_feed_named_by_its_urls_hash(tmp_path: Path) -> None:
    cache = FileFeedCache(tmp_path / "feeds")
    assert cache.get(URL) is None
    cache.put(a_feed())
    assert cache.get(URL) == a_feed()
    files = [path.name for path in (tmp_path / "feeds").iterdir()]
    assert files == ["1583e20557cb8bc5239c7f7602280ca9426c965df1b93945b6bf2262f4e6bb58.json"]


def test_a_later_answer_replaces_the_earlier_one(tmp_path: Path) -> None:
    cache = FileFeedCache(tmp_path)
    cache.put(a_feed())
    cache.put(CachedFeed(url=URL, etag='"courier-v2"'))
    assert cache.get(URL) == CachedFeed(url=URL, etag='"courier-v2"')


def test_a_corrupt_file_is_absent_and_says_so(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    cache = FileFeedCache(tmp_path)
    (tmp_path / cache_file_name(URL)).write_text("{not json", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="debate_core.integrations.discovery"):
        assert cache.get(URL) is None
    assert "fetching afresh" in caplog.text


def test_a_file_written_for_another_url_is_absent(tmp_path: Path) -> None:
    cache = FileFeedCache(tmp_path)
    (tmp_path / cache_file_name(URL)).write_text(
        a_feed("https://other.example.org/feed").model_dump_json(), encoding="utf-8"
    )
    assert cache.get(URL) is None


def test_a_failed_write_leaves_no_temporary_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache = FileFeedCache(tmp_path)

    def refuse(self: Path, target: Path) -> Path:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", refuse)
    with pytest.raises(OSError, match="disk full"):
        cache.put(a_feed())
    assert list(tmp_path.iterdir()) == []
