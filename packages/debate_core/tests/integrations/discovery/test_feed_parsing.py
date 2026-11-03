"""Reading feeds from strangers: what is refused, what is kept, and how dates and snippets come out.

The feeds are hand-written in `packages/debate_core/tests/fixtures/discovery/feeds/` (see its README),
and every expected value here is written by hand from them (working agreement 6).
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import pytest

from debate_core.integrations.discovery.feed_parsing import (
    MAX_SNIPPET_CHARS,
    FeedUnreadable,
    parse_feed,
    parse_feed_date,
    snippet_from_html,
    trim_snippet,
)

FIXTURES: Final = Path(__file__).resolve().parents[2] / "fixtures" / "discovery" / "feeds"
FULL_TEXT_MARKER: Final = "FULL ARTICLE TEXT"


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


# --------------------------------------------------------------------------------------------
# Hostile XML is refused, not read
# --------------------------------------------------------------------------------------------


def test_an_entity_expansion_attack_is_refused_without_expanding() -> None:
    started = time.perf_counter()
    with pytest.raises(FeedUnreadable, match="refused: EntitiesForbidden"):
        parse_feed(fixture("entity_expansion.xml"))
    assert time.perf_counter() - started < 1.0, "the refusal came after expanding, not before"


def test_an_external_entity_is_refused() -> None:
    with pytest.raises(FeedUnreadable, match="refused: EntitiesForbidden"):
        parse_feed(fixture("external_entity.xml"))


def test_a_single_entity_declaration_is_refused_too() -> None:
    feed = (
        b'<!DOCTYPE rss [<!ENTITY name "x">]>'
        b'<rss version="2.0"><channel><title>&name;</title></channel></rss>'
    )
    with pytest.raises(FeedUnreadable, match="refused"):
        parse_feed(feed)


def test_an_external_dtd_is_never_read(tmp_path: Path) -> None:
    """The DTD at the SYSTEM URL defines `&leak;`; had it been read, the title would carry its text."""
    dtd = tmp_path / "leak.dtd"
    dtd.write_text('<!ENTITY leak "TEXT FROM THE DTD">', encoding="utf-8")
    feed = (
        f'<?xml version="1.0"?><!DOCTYPE rss SYSTEM "{dtd.as_uri()}"><rss version="2.0"><channel>'
        "<item><title>a &leak;</title><link>https://a.example.org/x</link></item></channel></rss>"
    ).encode()
    with pytest.raises(FeedUnreadable):
        parse_feed(feed)


def test_a_doctype_that_declares_nothing_still_parses() -> None:
    feed = (
        b'<?xml version="1.0"?><!DOCTYPE rss PUBLIC "-//Netscape Communications//DTD RSS 0.91//EN" '
        b'"http://my.netscape.com/publish/formats/rss-0.91.dtd">'
        b'<rss version="0.91"><channel><title>Old</title>'
        b"<item><title>An item</title><link>https://old.example.org/1</link></item></channel></rss>"
    )
    parsed = parse_feed(feed)
    assert [entry.title for entry in parsed.entries] == ["An item"]


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(b"", id="empty"),
        pytest.param(b"\x00<<not what this provider sends>>\xff", id="binary"),
        pytest.param(b"<rss><channel><title>cut off", id="truncated"),
        pytest.param(b"<html><body>Not a feed</body></html>", id="html-page"),
        pytest.param(b'<rss version="2.0"></rss>', id="rss-without-channel"),
        pytest.param(b'{"items": []}', id="json"),
    ],
)
def test_anything_but_an_rss_or_atom_document_is_unreadable(body: bytes) -> None:
    with pytest.raises(FeedUnreadable):
        parse_feed(body)


# --------------------------------------------------------------------------------------------
# What an RSS 2.0 feed becomes
# --------------------------------------------------------------------------------------------


def test_an_rss_feed_keeps_every_item_with_a_title_and_a_link_in_feed_order() -> None:
    parsed = parse_feed(fixture("publisher_rss.xml"))
    assert parsed.title == "The Example Courier - Politics"
    assert [entry.entry_id for entry in parsed.entries] == [
        "courier-1001",
        "courier-1002",
        "courier-1003",
        "courier-1004",
        "courier-1005",
        "courier-1001",
        "courier-1007",
        "courier-1008",
        "courier-1009",
        "courier-1011",
        "courier-1012",
    ]


def test_an_rss_item_maps_title_link_date_creator_and_summary() -> None:
    first = parse_feed(fixture("publisher_rss.xml")).entries[0]
    assert first.title == "Senate panel advances health insurance subsidy bill"
    assert first.link == "https://news.example.org/2026/10/20/senate-subsidy-bill"
    assert first.published_at == datetime(2026, 10, 20, 14, 5, tzinfo=UTC)
    assert first.authors == ("Dana Whitfield",)
    assert first.snippet == "The health insurance subsidies would expire in January without a vote."


def test_feed_content_is_never_read_into_an_entry() -> None:
    """`content:encoded` and Atom `<content>` carry full text; nothing of it reaches an entry."""
    for name in ("publisher_rss.xml", "publisher_atom.xml"):
        for entry in parse_feed(fixture(name)).entries:
            assert FULL_TEXT_MARKER not in entry.model_dump_json(), f"{name}: {entry.title}"


def test_an_rss_author_keeps_the_name_and_never_the_address() -> None:
    entry = parse_feed(fixture("publisher_rss.xml")).entries[2]
    assert entry.authors == ("Marcus Bell",)
    bare = (
        b'<rss version="2.0"><channel><item><title>t</title><link>https://a.example.org/1</link>'
        b"<author>someone@example.org</author></item></channel></rss>"
    )
    assert parse_feed(bare).entries[0].authors == ()


def test_a_google_news_item_keeps_its_source_element() -> None:
    first = parse_feed(fixture("google_news_search.xml")).entries[0]
    assert first.source_name == "Example Gazette"
    assert first.source_url == "https://www.example.net"


# --------------------------------------------------------------------------------------------
# What an Atom 1.0 feed becomes
# --------------------------------------------------------------------------------------------


def test_an_atom_feed_maps_entries_by_their_alternate_link() -> None:
    parsed = parse_feed(fixture("publisher_atom.xml"))
    assert parsed.title == "Example Health Ledger"
    assert [entry.link for entry in parsed.entries] == [
        "https://www.example.com/2026/10/20/insurer-mergers",
        "https://www.example.com/2026/10/16/costs-explained",
        "https://www.example.com/glossary",
        "https://www.example.com/2026/10/18/no-offset",
        "https://www.example.com/2026/10/14/employers",
    ]


def test_atom_summaries_and_titles_of_each_type_become_plain_text() -> None:
    entries = parse_feed(fixture("publisher_atom.xml")).entries
    assert entries[0].snippet == "Regulators question two health insurance mergers."
    assert entries[1].snippet == "Why premiums rise."
    assert entries[4].title == "Employers rethink coverage"
    assert entries[4].snippet == "Employer health insurance shifts."


def test_an_atom_entry_without_published_falls_back_to_updated() -> None:
    entries = parse_feed(fixture("publisher_atom.xml")).entries
    assert entries[0].published_at == datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
    assert entries[1].published_at == datetime(2026, 10, 16, 23, 30, tzinfo=UTC)
    assert entries[1].authors == ("Lee Okafor", "Sam Ortiz")
    assert entries[2].published_at is None
    assert entries[3].published_at is None


def test_an_atom_entry_with_only_a_self_link_is_not_an_entry() -> None:
    feed = (
        b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Only self</title>'
        b'<link rel="self" href="https://a.example.org/self.xml"/></entry></feed>'
    )
    assert parse_feed(feed).entries == ()


# --------------------------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Tue, 20 Oct 2026 14:05:00 +0000", datetime(2026, 10, 20, 14, 5, tzinfo=UTC)),
        ("Tue, 20 Oct 2026 14:05:00 GMT", datetime(2026, 10, 20, 14, 5, tzinfo=UTC)),
        ("Mon, 19 Oct 2026 09:30:00 -0000", datetime(2026, 10, 19, 9, 30, tzinfo=UTC)),
        ("Sun, 18 Oct 2026 10:15:00 EDT", datetime(2026, 10, 18, 14, 15, tzinfo=UTC)),
        ("Sat, 17 Oct 2026 19:50:00 +0545", datetime(2026, 10, 17, 14, 5, tzinfo=UTC)),
        ("Thu, 15 Oct 2026 19:35:00 +05:30", datetime(2026, 10, 15, 14, 5, tzinfo=UTC)),
        ("Thu, 15 Oct 2026 01:00:00 -09:30", datetime(2026, 10, 15, 10, 30, tzinfo=UTC)),
        ("Wed, 21 Oct 2026 10:00:00 +1400", datetime(2026, 10, 20, 20, 0, tzinfo=UTC)),
        ("2026-10-20T08:00:00-04:00", datetime(2026, 10, 20, 12, 0, tzinfo=UTC)),
        ("2026-10-16T23:30:00Z", datetime(2026, 10, 16, 23, 30, tzinfo=UTC)),
        ("2026-10-16T23:30:00.250+00:00", datetime(2026, 10, 16, 23, 30, 0, 250000, tzinfo=UTC)),
        ("2026-10-14", datetime(2026, 10, 14, tzinfo=UTC)),
    ],
)
def test_a_feed_date_becomes_utc(text: str, expected: datetime) -> None:
    parsed = parse_feed_date(text)
    assert parsed == expected
    assert parsed is not None
    assert parsed.tzinfo is UTC


@pytest.mark.parametrize(
    "text",
    [
        None,
        "",
        "   ",
        "Fri, 16 Oct 2026 12:00:00 BST",
        "Fri, 16 Oct 2026 12:00:00",
        "Fri, 16 Oct 2026 12:00:00 +25:00",
        "2026-10-18T10:00:00",
        "last Tuesday",
    ],
)
def test_a_date_with_no_zone_or_an_unknown_one_is_none_never_a_guess(text: str | None) -> None:
    assert parse_feed_date(text) is None


# --------------------------------------------------------------------------------------------
# Snippets
# --------------------------------------------------------------------------------------------


def test_a_snippet_is_the_visible_text_of_the_summary() -> None:
    markup = "<p>First&nbsp;paragraph.</p><p>Second <a href='https://x.example.org'>link</a>.</p><script>alert(1)</script>"
    assert snippet_from_html(markup) == "First paragraph. Second link."


def test_a_long_summary_is_cut_at_a_word_to_at_most_500_characters() -> None:
    long = "word " * 300
    snippet = trim_snippet(long.strip())
    assert snippet is not None
    assert len(snippet) <= MAX_SNIPPET_CHARS
    assert snippet.endswith("word…")


def test_a_summary_of_exactly_500_characters_is_kept_whole() -> None:
    exact = "x" * MAX_SNIPPET_CHARS
    assert trim_snippet(exact) == exact
    assert trim_snippet(exact + "y") == "x" * (MAX_SNIPPET_CHARS - 1) + "…"


def test_an_empty_summary_is_no_snippet() -> None:
    assert snippet_from_html("<p> </p>") is None
    assert trim_snippet("") is None
