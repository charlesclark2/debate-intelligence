"""Reading an RSS 2.0 or Atom 1.0 feed from a stranger, safely, into plain entries (v1-e07-t05).

**The parser resolves nothing.** A feed is untrusted XML, so it is parsed with defusedxml over the
standard library's ElementTree with `forbid_entities=True` and `forbid_external=True`
(:func:`parse_feed`): a document that declares an entity (the "billion laughs" expansion) or
points at an external entity or DTD is refused with :class:`FeedUnreadable` before anything is
expanded or fetched. A `<!DOCTYPE>` that declares nothing, as old RSS 0.91 feeds carry, still parses.
Not feedparser: it parses with the bare standard-library SAX parser and, when that fails, falls back
to a loose parser, so a hostile feed is read rather than refused (PM ruling 2026-10-22). Nothing in
this package parses XML any other way.

**What is kept from an entry** (:class:`FeedEntry`) is what a
:class:`~debate_core.domain.discovery.CandidateResult` can carry: the title, the link, the entry's
id, its date, its authors' names (never an email address: RSS's `<author>` is one, and only the
name in brackets after it is kept), a summary snippet and, for a Google News item, the `<source>`
element's name and URL. Full content is never read: RSS's `content:encoded` and Atom's `<content>`
are skipped, because feed text is never evidence text and a snippet is discovery context only. The
snippet is the entry's summary (RSS `<description>`, Atom `<summary>`) with its markup removed,
whitespace collapsed and cut to at most :data:`MAX_SNIPPET_CHARS` characters.

An entry with no title or no absolute http(s) link is not an entry and is skipped.

**Dates** become timezone-aware UTC, or `None` when the feed gives none this module can place in
time (:func:`parse_feed_date`). RSS dates are RFC 822 (`Tue, 20 Oct 2026 14:05:00 +0000`), read
with the standard library; `-0000` is UTC (RFC 5322 §3.3), an ISO-style `+05:30` offset is applied,
and a date with no zone or one the standard library does not know (`BST`) is `None`, never a guess.
Atom dates are RFC 3339; one with no offset is `None`, and a bare `YYYY-MM-DD` is midnight UTC, as
OpenAlex's dates are. An RSS item may give `dc:date` instead of `pubDate`; an Atom entry with no
`<published>` falls back to `<updated>`.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import TYPE_CHECKING, Final
from urllib.parse import urlsplit

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import ParseError, fromstring
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element

__all__ = [
    "MAX_SNIPPET_CHARS",
    "FeedEntry",
    "FeedUnreadable",
    "ParsedFeed",
    "parse_feed",
    "parse_feed_date",
    "snippet_from_html",
    "trim_snippet",
]

MAX_SNIPPET_CHARS: Final = 500
"""The longest snippet a candidate carries (the spec's acceptance criterion 4)."""

ATOM: Final = "{http://www.w3.org/2005/Atom}"
DUBLIN_CORE: Final = "{http://purl.org/dc/elements/1.1/}"
XHTML: Final = "{http://www.w3.org/1999/xhtml}"

_NUMERIC_OFFSET: Final = re.compile(r"^([+-])(\d{2}):(\d{2})$")
_DATE_ONLY: Final = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ADDRESS_WITH_NAME: Final = re.compile(r"^\S+@\S+\s*\((.*)\)$")


class FeedUnreadable(ValueError):
    """The body is not a feed this module reads, or it is XML this module refuses to parse."""


class FeedEntry(BaseModel):
    """One feed item, reduced to what a candidate can carry. Stored in the feed cache as JSON."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1, description="The entry's title, whitespace collapsed.")
    link: str = Field(description="The entry's absolute http(s) link, as the feed gave it.")
    entry_id: str | None = Field(default=None, description="RSS `<guid>` or Atom `<id>`.")
    published_at: datetime | None = Field(default=None, description="When it was published, in UTC.")
    authors: tuple[str, ...] = Field(default=(), description="Author names, in the feed's order.")
    snippet: str | None = Field(
        default=None, description=f"The summary as plain text, at most {MAX_SNIPPET_CHARS} characters."
    )
    source_name: str | None = Field(default=None, description="An RSS `<source>` element's text.")
    source_url: str | None = Field(
        default=None, description="An RSS `<source url>`: the outlet's site, never the article."
    )


class ParsedFeed(BaseModel):
    """A feed's title and its entries, in the feed's order."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str | None = None
    entries: tuple[FeedEntry, ...] = ()


def parse_feed(body: bytes) -> ParsedFeed:
    """Parse an RSS 2.0 or Atom 1.0 document; :class:`FeedUnreadable` for anything else.

    Refuses, rather than reads, a document that declares an entity or refers to an external one.
    """
    try:
        root = fromstring(body, forbid_dtd=False, forbid_entities=True, forbid_external=True)
    except DefusedXmlException as error:
        raise FeedUnreadable(f"refused: {type(error).__name__}") from error
    except (ParseError, ValueError) as error:
        raise FeedUnreadable(f"not well-formed XML: {type(error).__name__}") from error
    if root.tag == "rss":
        channel = root.find("channel")
        if channel is None:
            raise FeedUnreadable("an RSS document with no <channel>")
        entries = (_rss_item(item) for item in channel.iter("item"))
        return ParsedFeed(title=_text(channel.find("title")), entries=_present(entries))
    if root.tag == f"{ATOM}feed":
        entries = (_atom_entry(entry) for entry in root.iter(f"{ATOM}entry"))
        return ParsedFeed(title=_text(root.find(f"{ATOM}title")), entries=_present(entries))
    raise FeedUnreadable("neither an RSS 2.0 nor an Atom 1.0 document")


def _present(entries: Iterable[FeedEntry | None]) -> tuple[FeedEntry, ...]:
    return tuple(entry for entry in entries if entry is not None)


def _rss_item(item: Element) -> FeedEntry | None:
    title = _text(item.find("title"))
    link = _http_url(_text(item.find("link")))
    if title is None or link is None:
        return None
    source = item.find("source")
    authors = [
        *(_rss_author(_text(element)) for element in item.findall("author")),
        *(_text(element) for element in item.findall(f"{DUBLIN_CORE}creator")),
    ]
    date_text = _text(item.find("pubDate")) or _text(item.find(f"{DUBLIN_CORE}date"))
    return FeedEntry(
        title=title,
        link=link,
        entry_id=_text(item.find("guid")),
        published_at=parse_feed_date(date_text),
        authors=tuple(author for author in authors if author is not None),
        snippet=snippet_from_html(_raw_text(item.find("description"))),
        source_name=_text(source),
        source_url=_http_url(source.get("url")) if source is not None else None,
    )


def _rss_author(text: str | None) -> str | None:
    """An RSS `<author>`'s name: `jo@example.org (Jo Smith)` is `Jo Smith`; a bare address is nothing.

    RSS 2.0 makes `<author>` an email address. A candidate carries names, never an address.
    """
    if text is None:
        return None
    named = _ADDRESS_WITH_NAME.match(text)
    if named is not None:
        return _collapse(named.group(1)) or None
    return None if "@" in text else text


def _atom_entry(entry: Element) -> FeedEntry | None:
    title = _atom_text(entry.find(f"{ATOM}title"))
    link = _atom_link(entry)
    if not title or link is None:
        return None
    names = [_text(author.find(f"{ATOM}name")) for author in entry.findall(f"{ATOM}author")]
    date_text = _text(entry.find(f"{ATOM}published")) or _text(entry.find(f"{ATOM}updated"))
    return FeedEntry(
        title=title,
        link=link,
        entry_id=_text(entry.find(f"{ATOM}id")),
        published_at=parse_feed_date(date_text),
        authors=tuple(name for name in names if name is not None),
        snippet=_atom_summary(entry.find(f"{ATOM}summary")),
    )


def _atom_link(entry: Element) -> str | None:
    """The `alternate` link: the one marked so, or the first with no `rel` (RFC 4287 §4.2.7.2)."""
    for link in entry.findall(f"{ATOM}link"):
        if link.get("rel", "alternate") == "alternate":
            found = _http_url(link.get("href"))
            if found is not None:
                return found
    return None


def _atom_summary(summary: Element | None) -> str | None:
    """`<summary>` as a snippet: plain text, trimmed."""
    return trim_snippet(_atom_text(summary))


def _atom_text(element: Element | None) -> str:
    """An Atom text construct as plain text: `text` is text, `html` escaped markup, `xhtml` a `<div>`."""
    if element is None:
        return ""
    kind = element.get("type", "text")
    if kind == "xhtml":
        return _collapse(_element_text(element))
    if kind == "html":
        return _text_of_html(element.text or "")
    return _collapse(element.text or "")


# --------------------------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------------------------


def parse_feed_date(text: str | None) -> datetime | None:
    """A feed date as an aware UTC datetime; `None` when absent, unreadable or of unknown zone."""
    if text is None:
        return None
    value = text.strip()
    if not value:
        return None
    moment = _rfc822_date(value)
    if moment is None:
        moment = _iso_date(value)
    return moment.astimezone(UTC) if moment is not None else None


def _rfc822_date(value: str) -> datetime | None:
    try:
        moment = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if moment.tzinfo is not None:
        return moment
    zone = value.rsplit(maxsplit=1)[-1]
    if zone == "-0000":
        return moment.replace(tzinfo=UTC)
    offset = _NUMERIC_OFFSET.match(zone)
    if offset is None:
        return None
    sign = -1 if offset.group(1) == "-" else 1
    minutes = int(offset.group(2)) * 60 + int(offset.group(3))
    if minutes >= 24 * 60:
        return None
    return moment.replace(tzinfo=timezone(sign * timedelta(minutes=minutes)))


def _iso_date(value: str) -> datetime | None:
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    if moment.tzinfo is not None:
        return moment
    if _DATE_ONLY.match(value):
        return moment.replace(tzinfo=UTC)
    return None


# --------------------------------------------------------------------------------------------
# Snippets
# --------------------------------------------------------------------------------------------

_INLINE_TAGS: Final = frozenset(
    {
        "a",
        "abbr",
        "b",
        "cite",
        "code",
        "em",
        "font",
        "i",
        "mark",
        "q",
        "s",
        "small",
        "span",
        "strong",
        "sub",
        "sup",
        "u",
    }
)
"""Tags that sit inside a run of text; every other tag separates the words either side of it."""

_SKIPPED_TAGS: Final = frozenset({"script", "style", "template", "noscript"})
"""Tags whose content is not text a reader sees."""


class _TextOfHtml(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skipping = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIPPED_TAGS:
            self._skipping += 1
        elif tag not in _INLINE_TAGS:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIPPED_TAGS:
            self._skipping = max(self._skipping - 1, 0)
        elif tag not in _INLINE_TAGS:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self._skipping:
            self.parts.append(data)


def snippet_from_html(markup: str | None) -> str | None:
    """The text a reader would see in `markup`, collapsed and trimmed; `None` when there is none."""
    if markup is None:
        return None
    return trim_snippet(_text_of_html(markup))


def _text_of_html(markup: str) -> str:
    reader = _TextOfHtml()
    reader.feed(markup)
    reader.close()
    return _collapse("".join(reader.parts))


def trim_snippet(text: str, limit: int = MAX_SNIPPET_CHARS) -> str | None:
    """`text` cut to at most `limit` characters, at a word boundary, ending `…` when it was cut."""
    if not text:
        return None
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    space = cut.rfind(" ")
    if space > limit // 2:
        cut = cut[:space]
    return cut.rstrip() + "…"


# --------------------------------------------------------------------------------------------
# Element helpers
# --------------------------------------------------------------------------------------------


def _collapse(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def _element_text(element: Element | None) -> str:
    return "".join(element.itertext()) if element is not None else ""


def _raw_text(element: Element | None) -> str | None:
    return element.text if element is not None else None


def _text(element: Element | None) -> str | None:
    if element is None:
        return None
    collapsed = _collapse(element.text or "")
    return collapsed or None


def _http_url(value: str | None) -> str | None:
    """`value` when it is an absolute http(s) URL with a host and no spaces."""
    if value is None:
        return None
    text = value.strip()
    if not text or any(character.isspace() for character in text):
        return None
    parts = urlsplit(text)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return text
