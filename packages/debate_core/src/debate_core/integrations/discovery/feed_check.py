"""Fetch every configured feed once and say whether it answers: the operator's feed check.

Operator-run, on the live network, never in a test or in CI (v1-e07-t05). A feed listed in
`config/feeds/` is a starting point until this check has shown it answers::

    uv run python -m debate_core.integrations.discovery.feed_check --feeds-dir config/feeds

Each feed is fetched once, one after another, unconditionally and with no cache, by the same fetcher
and the same safe parser the feed provider uses. One line per feed gives its topic, publisher and URL
(all from the config file), then the status (`HTTP 200`, or why it failed), how many entries it
carried, how many of those had a date the parser could place in time, and the newest of those dates.
Nothing from an entry is printed: no title, no link, no summary. The exit status is 1 when any feed
failed, 0 otherwise.

A feed that answers but cannot be parsed gets a second line saying why, in counts and statuses only
(v1-e07-t14, :func:`diagnose`): the declared content type and encoding, the body's size, what comes
before its first markup and what that markup is, the XML parser's own error and position, how many
control characters XML forbids and bare `&` the body holds, whether it is UTF-8, and whether it
would parse with leading whitespace removed. That is enough to tell a publisher that
serves broken XML, or an HTML page, from a parser that refuses a valid feed.

`--url` checks the URLs given instead of the configured feeds, so a candidate feed can be checked
before it is added; its rows give `candidate` as the topic and the URL's host as the publisher::

    uv run python -m debate_core.integrations.discovery.feed_check --url https://example.org/feed
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Final, TextIO
from urllib.parse import urlsplit

import httpx
from defusedxml.ElementTree import ParseError

from debate_core.application.errors import ProviderError
from debate_core.application.settings import HttpSettings
from debate_core.integrations.discovery.feed_cache import InMemoryFeedCache
from debate_core.integrations.discovery.feed_config import (
    FeedConfig,
    FeedReview,
    FeedSource,
    load_feed_directory,
)
from debate_core.integrations.discovery.feed_parsing import FeedUnreadable, parse_feed
from debate_core.integrations.discovery.feeds import FeedBody, FeedFetcher, feed_client

__all__ = ["FeedCheck", "candidate_topic", "check_feeds", "diagnose", "main", "render"]

CHECK_NAME: Final = "feed check"
"""The name failures are reported under."""

CANDIDATE_TOPIC: Final = "candidate"
"""The topic `--url` rows are listed under."""

_XML_DECLARATION: Final = b"<?xml"
_UTF8_BOM: Final = b"\xef\xbb\xbf"
_XML_WHITESPACE: Final = b" \t\r\n"
_FORBIDDEN_CONTROLS: Final = re.compile(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]")
"""The C0 control characters XML 1.0 does not allow anywhere in a document (§2.2)."""
_BARE_AMPERSAND: Final = re.compile(rb"&(?!#[0-9]+;|#x[0-9A-Fa-f]+;|[A-Za-z_][\w.-]*;)")
"""An `&` that starts no character or entity reference, which XML refuses (§2.4)."""
_CDATA_OR_COMMENT: Final = re.compile(rb"<!\[CDATA\[.*?\]\]>|<!--.*?-->", re.DOTALL)
"""Where an `&` is only text: counting bare ones leaves these out."""


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
    newest: datetime | None = None
    diagnosis: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "HTTP 200"


async def check_feeds(topics: Sequence[FeedConfig], client: httpx.AsyncClient) -> list[FeedCheck]:
    """Fetch each feed on `topics` once, in order, and count what came back."""
    fetcher = FeedFetcher(client, cache=InMemoryFeedCache(), clock=_SystemClock(), provider=CHECK_NAME)
    checks: list[FeedCheck] = []
    for topic in topics:
        for feed in topic.feeds:
            checks.append(await _check(fetcher, topic.topic, feed))
    return checks


async def _check(fetcher: FeedFetcher, topic: str, feed: FeedSource) -> FeedCheck:
    try:
        answer = await fetcher.fetch_body(feed.url)
    except ProviderError as error:
        return FeedCheck(topic, feed.publisher, feed.url, _status(error), 0, 0)
    try:
        parsed = fetcher.read(answer)
    except ProviderError as error:
        return FeedCheck(topic, feed.publisher, feed.url, _status(error), 0, 0, diagnosis=diagnose(answer))
    dates = [entry.published_at for entry in parsed.entries if entry.published_at is not None]
    return FeedCheck(
        topic,
        feed.publisher,
        feed.url,
        "HTTP 200",
        len(parsed.entries),
        len(dates),
        newest=max(dates, default=None),
    )


def _status(error: ProviderError) -> str:
    return str(error).removeprefix(f"{CHECK_NAME}: ")


def candidate_topic(urls: Sequence[str]) -> FeedConfig:
    """The `--url` feeds as one topic, each published under its URL's host."""
    feeds = tuple(
        FeedSource(url=url, publisher=urlsplit(url).hostname or url, review=FeedReview.AWAITING_COACH_REVIEW)
        for url in dict.fromkeys(urls)
    )
    return FeedConfig(topic=CANDIDATE_TOPIC, description="Feeds given on the command line.", feeds=feeds)


# --------------------------------------------------------------------------------------------
# Why a feed that answered could not be read
# --------------------------------------------------------------------------------------------


def diagnose(answer: FeedBody) -> str:
    """Why `answer` did not parse, in counts and statuses: never a word of the body.

    Names the declared type and encoding, the size, what precedes the first markup and what that
    markup is, the XML parser's error and position, how many forbidden control characters and bare
    ampersands the body holds, whether it is UTF-8, and whether it parses once leading whitespace is
    removed. The parser's position counts characters, not bytes, so it is given as the parser said it.
    """
    body = answer.body
    parts = [
        f"content-type {answer.content_type or 'none'}",
        f"content-encoding {answer.content_encoding or 'none'}",
        _count(len(body), "byte"),
        f"starts with {_opening(body)}",
    ]
    error = _xml_error(body)
    if error is not None:
        parts.append(f"XML error {error}")
    parts.append(_count(len(_FORBIDDEN_CONTROLS.findall(body)), "forbidden control character"))
    parts.append(_count(len(_BARE_AMPERSAND.findall(_CDATA_OR_COMMENT.sub(b"", body))), "bare ampersand"))
    parts.append(f"UTF-8 {'yes' if _is_utf8(body) else 'no'}")
    stripped = body.lstrip(_XML_WHITESPACE)
    if stripped != body:
        parts.append(f"parses with leading whitespace removed: {'yes' if _parses(stripped) else 'no'}")
    return "; ".join(parts)


def _opening(body: bytes) -> str:
    """What precedes the first `<` (a BOM, whitespace, other bytes) and what kind of markup it opens."""
    rest = body
    before: list[str] = []
    if rest.startswith(_UTF8_BOM):
        before.append("a UTF-8 byte order mark")
        rest = rest.removeprefix(_UTF8_BOM)
    stripped = rest.lstrip(_XML_WHITESPACE)
    if len(stripped) != len(rest):
        before.append(_count(len(rest) - len(stripped), "whitespace byte"))
    rest = stripped
    first = rest.find(b"<")
    if first == -1:
        return ", then ".join([*before, "no markup at all"]) if body else "nothing: the body is empty"
    if first > 0:
        before.append(_count(first, "other byte"))
    return ", then ".join([*before, _markup_kind(rest[first:])])


def _markup_kind(markup: bytes) -> str:
    folded = markup[:64].lower()
    if folded.startswith(_XML_DECLARATION):
        return "an XML declaration"
    if folded.startswith((b"<!doctype html", b"<html")):
        return "an HTML page"
    if folded.startswith(b"<!doctype"):
        return "a DOCTYPE"
    if folded.startswith((b"<rss", b"<feed", b"<rdf:rdf")):
        return "a feed element with no XML declaration"
    if folded.startswith(b"<!--"):
        return "a comment"
    return "some other element"


def _xml_error(body: bytes) -> str | None:
    """The XML parser's own message, ending with the line and column it stopped at; `None` if it parses."""
    try:
        parse_feed(body)
    except FeedUnreadable as unreadable:
        cause = unreadable.__cause__
        if not isinstance(cause, ParseError):
            return str(unreadable)
        return str(cause)
    return None


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" + ("" if number == 1 else "s")


def _is_utf8(body: bytes) -> bool:
    try:
        body.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _parses(body: bytes) -> bool:
    try:
        parse_feed(body)
    except FeedUnreadable:
        return False
    return True


# --------------------------------------------------------------------------------------------
# The report
# --------------------------------------------------------------------------------------------


def render(checks: Sequence[FeedCheck], out: TextIO) -> None:
    """One line per feed: topic, publisher, status, entries, dated, newest, URL; then a count of failures.

    A feed that answered but could not be parsed has a second, indented line saying why.
    """
    rows = [("topic", "publisher", "status", "entries", "dated", "newest", "url")]
    rows += [
        (c.topic, c.publisher, c.status, str(c.entries), str(c.dated), _date(c.newest), c.url) for c in checks
    ]
    widths = [max(len(row[column]) for row in rows) for column in range(6)]
    for index, row in enumerate(rows):
        cells = [cell.ljust(width) for cell, width in zip(row[:6], widths, strict=True)]
        print("  ".join((*cells, row[6])), file=out)
        diagnosis = checks[index - 1].diagnosis if index else None
        if diagnosis is not None:
            print(f"    why: {diagnosis}", file=out)
    failed = sum(1 for check in checks if not check.ok)
    print(f"{len(checks)} feeds checked, {failed} failed", file=out)


def _date(moment: datetime | None) -> str:
    return moment.strftime("%Y-%m-%dT%H:%MZ") if moment is not None else "-"


def _version() -> str:
    try:
        return version("debate-core")
    except PackageNotFoundError:
        return "0.0.0"


async def _run(topics: Sequence[FeedConfig]) -> list[FeedCheck]:
    async with feed_client(HttpSettings(), version=_version()) as client:
        return await check_feeds(topics, client)


def main(argv: Sequence[str] | None = None) -> int:
    """Check every feed in `--feeds-dir`, or each `--url` instead; exit 1 when any failed."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--feeds-dir", type=Path, default=Path("config/feeds"), help="the topic feed lists")
    parser.add_argument(
        "--url",
        action="append",
        default=[],
        help="check this feed instead of the configured ones (repeatable)",
    )
    arguments = parser.parse_args(argv)
    if arguments.url:
        try:
            topics = [candidate_topic(arguments.url)]
        except ValueError as error:
            parser.error(f"--url: {error}")
    else:
        topics = load_feed_directory(arguments.feeds_dir)
    checks = asyncio.run(_run(topics))
    render(checks, sys.stdout)
    return 0 if all(check.ok for check in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
