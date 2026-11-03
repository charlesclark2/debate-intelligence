"""What a feed said last time, so the next fetch can ask "has it changed?" (v1-e07-t05).

Conditional GET is how the feed providers stay polite: a feed fetched before is asked for again
with `If-None-Match` (its last `ETag`) and `If-Modified-Since` (its last `Last-Modified`), and a
publisher that answers `304 Not Modified` sends no body. The provider then needs the entries it
read last time, so a :class:`CachedFeed` keeps both: the validators and the entries already reduced
to :class:`~debate_core.integrations.discovery.feed_parsing.FeedEntry` (snippets trimmed to 500
characters, never a feed's full content).

**On disk** (PM ruling 2026-10-22): :class:`FileFeedCache` keeps one JSON file per feed under
`<storage.data_dir>/feeds/`, named by the SHA-256 of the feed's URL. The CLI is one process per
command, so a cache that lived only in memory would almost never send a conditional request.
:class:`InMemoryFeedCache` is the same thing for tests.

A cache file that cannot be read, or that was written for a different URL, is treated as absent:
the next fetch is unconditional, and its answer replaces the file. A cache is never a reason a
search fails.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Final, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from debate_core.integrations.discovery.feed_parsing import FeedEntry
from debate_core.integrations.discovery.redaction import logger

__all__ = [
    "FEED_CACHE_DIRECTORY",
    "CachedFeed",
    "FeedCache",
    "FileFeedCache",
    "InMemoryFeedCache",
    "cache_file_name",
]

FEED_CACHE_DIRECTORY: Final = "feeds"
"""The directory inside `storage.data_dir` the composition root gives :class:`FileFeedCache`."""


class CachedFeed(BaseModel):
    """One feed's last answer: its validators and its entries."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    url: str = Field(description="The feed URL this was fetched from.")
    etag: str | None = Field(default=None, description="The `ETag` the feed sent, verbatim.")
    last_modified: str | None = Field(default=None, description="The `Last-Modified` it sent, verbatim.")
    entries: tuple[FeedEntry, ...] = Field(default=(), description="Its entries, already reduced.")

    @property
    def conditional_headers(self) -> dict[str, str]:
        """The headers that ask whether the feed has changed since this answer."""
        headers: dict[str, str] = {}
        if self.etag is not None:
            headers["If-None-Match"] = self.etag
        if self.last_modified is not None:
            headers["If-Modified-Since"] = self.last_modified
        return headers


@runtime_checkable
class FeedCache(Protocol):
    """Where the feed providers keep each feed's last answer."""

    def get(self, url: str) -> CachedFeed | None:
        """The last answer kept for `url`, or `None`."""
        ...

    def put(self, feed: CachedFeed) -> None:
        """Keep `feed` as the last answer for its URL, replacing any earlier one."""
        ...


class InMemoryFeedCache:
    """A :class:`FeedCache` that lasts as long as the object: for tests."""

    def __init__(self) -> None:
        self._feeds: dict[str, CachedFeed] = {}

    def get(self, url: str) -> CachedFeed | None:
        return self._feeds.get(url)

    def put(self, feed: CachedFeed) -> None:
        self._feeds[feed.url] = feed


def cache_file_name(url: str) -> str:
    """The file a feed's answer is kept in: the SHA-256 of its URL, in hex, with `.json`."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest() + ".json"


class FileFeedCache:
    """A :class:`FeedCache` of JSON files in one directory, created on first write."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    @property
    def directory(self) -> Path:
        return self._directory

    def __repr__(self) -> str:
        return f"{type(self).__name__}({str(self._directory)!r})"

    def get(self, url: str) -> CachedFeed | None:
        path = self._directory / cache_file_name(url)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except (OSError, UnicodeDecodeError) as error:
            logger.warning(
                "feed cache file %s unreadable (%s); fetching afresh", path.name, type(error).__name__
            )
            return None
        try:
            feed = CachedFeed.model_validate_json(text)
        except ValidationError:
            logger.warning("feed cache file %s is not a cached feed; fetching afresh", path.name)
            return None
        return feed if feed.url == url else None

    def put(self, feed: CachedFeed) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._directory / cache_file_name(feed.url)
        handle, temporary = tempfile.mkstemp(dir=self._directory, prefix=".", suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(feed.model_dump_json())
            Path(temporary).replace(path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
