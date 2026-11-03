"""Fetch every configured feed once and say whether it answers: the operator's feed check.

Operator-run, on the live network, never in a test or in CI (v1-e07-t05). A feed listed in
`config/feeds/` is a starting point until this check has shown it answers::

    uv run python -m debate_core.integrations.discovery.feed_check --feeds-dir config/feeds

Each feed is fetched once, one after another, unconditionally and with no cache, by the same fetcher
and the same safe parser the feed provider uses. One line per feed gives its topic, publisher and URL
(all from the config file), then the status (`HTTP 200`, or why it failed), how many entries it
carried and how many of those had a date the parser could place in time. Nothing from an entry is
printed: no title, no link, no summary. The exit status is 1 when any feed failed, 0 otherwise.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Final, TextIO

import httpx

from debate_core.application.errors import ProviderError
from debate_core.application.settings import HttpSettings
from debate_core.integrations.discovery.feed_cache import InMemoryFeedCache
from debate_core.integrations.discovery.feed_config import FeedConfig, load_feed_directory
from debate_core.integrations.discovery.feeds import FeedFetcher, feed_client

__all__ = ["FeedCheck", "check_feeds", "main", "render"]

CHECK_NAME: Final = "feed check"
"""The name failures are reported under."""


class _SystemClock:
    """The wall clock, for the one thing the fetcher asks it: when a `Retry-After` date ends."""

    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class FeedCheck:
    """One feed's answer: whether it answered, and how many entries, dated and not."""

    topic: str
    publisher: str
    url: str
    status: str
    entries: int
    dated: int

    @property
    def ok(self) -> bool:
        return self.status == "HTTP 200"


async def check_feeds(topics: Sequence[FeedConfig], client: httpx.AsyncClient) -> list[FeedCheck]:
    """Fetch each feed on `topics` once, in order, and count what came back."""
    fetcher = FeedFetcher(client, cache=InMemoryFeedCache(), clock=_SystemClock(), provider=CHECK_NAME)
    checks: list[FeedCheck] = []
    for topic in topics:
        for feed in topic.feeds:
            try:
                fetched = await fetcher.fetch(feed.url)
            except ProviderError as error:
                status = str(error).removeprefix(f"{CHECK_NAME}: ")
                checks.append(FeedCheck(topic.topic, feed.publisher, feed.url, status, 0, 0))
                continue
            dated = sum(1 for entry in fetched.entries if entry.published_at is not None)
            checks.append(
                FeedCheck(topic.topic, feed.publisher, feed.url, "HTTP 200", len(fetched.entries), dated)
            )
    return checks


def render(checks: Sequence[FeedCheck], out: TextIO) -> None:
    """One line per feed: topic, publisher, status, entries, dated, URL; then a count of failures."""
    rows = [("topic", "publisher", "status", "entries", "dated", "url")]
    rows += [(c.topic, c.publisher, c.status, str(c.entries), str(c.dated), c.url) for c in checks]
    widths = [max(len(row[column]) for row in rows) for column in range(5)]
    for row in rows:
        cells = [cell.ljust(width) for cell, width in zip(row[:5], widths, strict=True)]
        print("  ".join((*cells, row[5])), file=out)
    failed = sum(1 for check in checks if not check.ok)
    print(f"{len(checks)} feeds checked, {failed} failed", file=out)


def _version() -> str:
    try:
        return version("debate-core")
    except PackageNotFoundError:
        return "0.0.0"


async def _run(feeds_dir: Path) -> list[FeedCheck]:
    topics = load_feed_directory(feeds_dir)
    async with feed_client(HttpSettings(), version=_version()) as client:
        return await check_feeds(topics, client)


def main(argv: Sequence[str] | None = None) -> int:
    """Check every feed in `--feeds-dir`; exit 1 when any failed."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--feeds-dir", type=Path, default=Path("config/feeds"), help="the topic feed lists")
    arguments = parser.parse_args(argv)
    checks = asyncio.run(_run(arguments.feeds_dir))
    render(checks, sys.stdout)
    return 0 if all(check.ok for check in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
