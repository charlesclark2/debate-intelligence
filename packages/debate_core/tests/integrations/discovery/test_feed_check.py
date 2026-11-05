"""The operator's feed check: one line per feed with counts, and nothing from any entry.

A feed that answers but does not parse is diagnosed in counts and statuses (v1-e07-t14). Every body
below is invented, and every expected diagnosis was worked out by hand from the body.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import httpx
import pytest

from debate_core.integrations.discovery import feed_check
from debate_core.integrations.discovery.feed_check import FeedCheck, check_feeds, diagnose, render
from debate_core.integrations.discovery.feed_config import FeedConfig, FeedReview, FeedSource
from debate_core.integrations.discovery.feeds import FeedBody

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
        FeedCheck(
            "politics",
            "Example Courier",
            RSS_URL,
            "HTTP 200",
            11,
            9,
            newest=datetime(2026, 10, 20, 14, 5, tzinfo=UTC),
        ),
        FeedCheck("politics", "Gone Gazette", GONE_URL, "HTTP 404: the provider refused the request", 0, 0),
        FeedCheck(
            "health-insurance",
            "Example Health Ledger",
            ATOM_URL,
            "HTTP 200",
            5,
            3,
            newest=datetime(2026, 10, 20, 12, 0, tzinfo=UTC),
        ),
        FeedCheck(
            "health-insurance",
            "Hostile Herald",
            HOSTILE_URL,
            "unreadable feed: refused: EntitiesForbidden",
            0,
            0,
            diagnosis=(
                "content-type none; content-encoding none; "
                f"{len((FIXTURES / 'entity_expansion.xml').read_bytes())} bytes; "
                "starts with an XML declaration; XML error refused: EntitiesForbidden; "
                "0 forbidden control characters; 0 bare ampersands; UTF-8 yes"
            ),
        ),
    ]


async def test_the_report_prints_counts_and_nothing_from_an_entry() -> None:
    async with client() as http:
        checks = await check_feeds(TOPICS, http)
    out = io.StringIO()
    render(checks, out)
    text = out.getvalue()
    lines = text.splitlines()
    assert lines[0].split() == ["topic", "publisher", "status", "entries", "dated", "newest", "url"]
    assert lines[1].split() == [
        "politics",
        "Example",
        "Courier",
        "HTTP",
        "200",
        "11",
        "9",
        "2026-10-20T14:05Z",
        RSS_URL,
    ]
    assert lines[2].split()[-3:] == ["0", "-", GONE_URL]
    assert lines[3].split()[-2:] == ["2026-10-20T12:00Z", ATOM_URL]
    assert lines[4].split()[-2:] == ["-", HOSTILE_URL]
    assert lines[5].startswith("    why: content-type none; ")
    assert lines[-1] == "4 feeds checked, 2 failed"
    for title_word in ("Senate", "Medicaid", "mergers", "premiums", "lol"):
        assert title_word not in text


def test_main_exits_one_when_a_feed_failed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "politics.yaml").write_text(
        "topic: politics\ndescription: Politics.\nfeeds:\n"
        f"  - url: {GONE_URL}\n    publisher: Gone Gazette\n    review: awaiting_coach_review\n",
        encoding="utf-8",
    )

    async def run(topics: list[FeedConfig]) -> list[FeedCheck]:
        assert [feed.url for topic in topics for feed in topic.feeds] == [GONE_URL]
        return [FeedCheck("politics", "Gone Gazette", GONE_URL, "HTTP 404", 0, 0)]

    monkeypatch.setattr(feed_check, "_run", run)
    assert feed_check.main(["--feeds-dir", str(tmp_path)]) == 1

    async def all_well(topics: list[FeedConfig]) -> list[FeedCheck]:
        return [FeedCheck("politics", "Example Courier", RSS_URL, "HTTP 200", 3, 3)]

    monkeypatch.setattr(feed_check, "_run", all_well)
    assert feed_check.main(["--feeds-dir", str(tmp_path)]) == 0


# --------------------------------------------------------------------------------------------
# Candidate feeds: --url (v1-e07-t14)
# --------------------------------------------------------------------------------------------


def test_url_checks_the_given_feeds_instead_of_the_configured_ones(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    asked: list[FeedConfig] = []

    async def run(topics: list[FeedConfig]) -> list[FeedCheck]:
        asked.extend(topics)
        return []

    monkeypatch.setattr(feed_check, "_run", run)
    missing = tmp_path / "no-such-directory"
    arguments = ["--feeds-dir", str(missing), "--url", RSS_URL, "--url", ATOM_URL, "--url", RSS_URL]
    assert feed_check.main(arguments) == 0
    assert asked == [
        FeedConfig(
            topic="candidate",
            description="Feeds given on the command line.",
            feeds=(
                FeedSource(
                    url=RSS_URL, publisher="news.example.org", review=FeedReview.AWAITING_COACH_REVIEW
                ),
                FeedSource(
                    url=ATOM_URL, publisher="www.example.com", review=FeedReview.AWAITING_COACH_REVIEW
                ),
            ),
        )
    ]


def test_a_url_that_is_not_absolute_http_is_refused_before_anything_is_fetched(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def run(topics: list[FeedConfig]) -> list[FeedCheck]:
        raise AssertionError("nothing may be fetched")

    monkeypatch.setattr(feed_check, "_run", run)
    with pytest.raises(SystemExit) as stopped:
        feed_check.main(["--url", "feeds.example.org/rss"])
    assert stopped.value.code == 2
    assert "--url:" in capsys.readouterr().err


# --------------------------------------------------------------------------------------------
# Why an answered feed did not parse (v1-e07-t14)
# --------------------------------------------------------------------------------------------

WIRE_URL: Final = "https://wire.example.org/feed/"

BLANK_LINE_FIRST: Final = (
    b'\n<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel><title>Example Wire</title>'
    b"<item><title>Invented story</title><link>https://wire.example.org/a</link>"
    b"<pubDate>Mon, 02 Nov 2026 10:00:00 +0000</pubDate></item></channel></rss>\n"
)
"""A WordPress feed with a blank line before its XML declaration, which XML does not allow."""

CHALLENGE_PAGE: Final = (
    b'<!DOCTYPE html>\n<html><head><meta charset="utf-8"><title>One moment</title></head>'
    b"<body><p>Checking your browser.</p></body></html>"
)
"""An HTML page served at the feed's URL with `200`, as a bot check would."""

CONTROL_AND_AMPERSAND: Final = (
    b'<?xml version="1.0"?>\n<rss version="2.0"><channel><title>Wire & Post</title>'
    b"<description><![CDATA[Fish & chips]]></description>"
    b"<item><title>Vote\x0b count</title><link>https://wire.example.org/b</link></item></channel></rss>"
)
"""A bare `&` in a title, another inside CDATA (allowed there), and a vertical tab (never allowed)."""

LATIN_1: Final = b'<?xml version="1.0"?>\n<rss version="2.0"><channel><title>Caf\xe9</title></channel></rss>'
"""A Latin-1 byte in a document that declares no encoding, so is read as UTF-8."""


async def check_one(body: bytes, content_type: str) -> FeedCheck:
    topics = (
        FeedConfig(
            topic="politics",
            description="Politics.",
            feeds=(FeedSource(url=WIRE_URL, publisher="Example Wire", review=FeedReview.COACH_REVIEWED),),
        ),
    )
    answer = httpx.Response(200, content=body, headers={"Content-Type": content_type})
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: answer)) as http:
        (check,) = await check_feeds(topics, http)
    return check


async def test_a_blank_line_before_the_xml_declaration_is_named_and_would_parse_without_it() -> None:
    check = await check_one(BLANK_LINE_FIRST, "application/rss+xml; charset=UTF-8")
    assert check.status == "unreadable feed: not well-formed XML: ParseError"
    assert (check.entries, check.dated, check.newest) == (0, 0, None)
    assert check.diagnosis == (
        "content-type application/rss+xml; charset=UTF-8; content-encoding none; "
        f"{len(BLANK_LINE_FIRST)} bytes; starts with 1 whitespace byte, then an XML declaration; "
        "XML error XML or text declaration not at start of entity: line 2, column 0; "
        "0 forbidden control characters; 0 bare ampersands; UTF-8 yes; "
        "parses with leading whitespace removed: yes"
    )


async def test_an_html_page_where_the_feed_should_be_is_named() -> None:
    check = await check_one(CHALLENGE_PAGE, "text/html; charset=UTF-8")
    assert check.diagnosis == (
        "content-type text/html; charset=UTF-8; content-encoding none; "
        f"{len(CHALLENGE_PAGE)} bytes; starts with an HTML page; "
        "XML error mismatched tag: line 2, column 61; "
        "0 forbidden control characters; 0 bare ampersands; UTF-8 yes"
    )


async def test_forbidden_characters_are_counted_and_an_ampersand_in_cdata_is_not() -> None:
    check = await check_one(CONTROL_AND_AMPERSAND, "application/rss+xml")
    assert check.diagnosis == (
        "content-type application/rss+xml; content-encoding none; "
        f"{len(CONTROL_AND_AMPERSAND)} bytes; starts with an XML declaration; "
        "XML error not well-formed (invalid token): line 2, column 41; "
        "1 forbidden control character; 1 bare ampersand; UTF-8 yes"
    )


async def test_a_body_that_is_not_utf8_says_so() -> None:
    check = await check_one(LATIN_1, "text/xml")
    assert check.diagnosis == (
        "content-type text/xml; content-encoding none; "
        f"{len(LATIN_1)} bytes; starts with an XML declaration; "
        "XML error not well-formed (invalid token): line 2, column 38; "
        "0 forbidden control characters; 0 bare ampersands; UTF-8 no"
    )


@pytest.mark.parametrize(
    ("body", "opening"),
    [
        pytest.param(
            b"\xef\xbb\xbf<?xml version='1.0'?><rss/>",
            "starts with a UTF-8 byte order mark, then an XML declaration",
            id="bom",
        ),
        pytest.param(
            b"\xef\xbb\xbf \r\n<!DOCTYPE HTML><HTML></HTML>",
            "starts with a UTF-8 byte order mark, then 3 whitespace bytes, then an HTML page",
            id="bom-whitespace-html",
        ),
        pytest.param(
            b"<rss version='2.0'><channel>", "starts with a feed element with no XML declaration", id="rss"
        ),
        pytest.param(
            b"ok\n<rss/>", "starts with 3 other bytes, then a feed element with no XML declaration", id="junk"
        ),
        pytest.param(b"<!-- cached --><rss/>", "starts with a comment", id="comment"),
        pytest.param(b"<!DOCTYPE rss><rss/>", "starts with a DOCTYPE", id="doctype"),
        pytest.param(b"<channel/>", "starts with some other element", id="other"),
        pytest.param(b"\x1f\x8b\x08\x00", "starts with no markup at all", id="compressed"),
        pytest.param(b"", "starts with nothing: the body is empty", id="empty"),
    ],
)
def test_the_opening_of_the_body_is_described_by_kind(body: bytes, opening: str) -> None:
    parts = diagnose(FeedBody(body)).split("; ")
    assert parts[3] == opening


def test_a_diagnosis_carries_no_word_of_the_body() -> None:
    words = {
        b"Example",
        b"Wire",
        b"Invented",
        b"story",
        b"moment",
        b"Checking",
        b"browser",
        b"Fish",
        b"chips",
    }
    for body in (BLANK_LINE_FIRST, CHALLENGE_PAGE, CONTROL_AND_AMPERSAND, LATIN_1):
        text = diagnose(FeedBody(body, content_type="text/xml"))
        assert not [word for word in words if word.decode() in text], text


def test_the_report_prints_the_diagnosis_under_its_feed() -> None:
    checks = [
        FeedCheck(
            "politics", "Example Wire", WIRE_URL, "unreadable feed: x", 0, 0, diagnosis="starts with y"
        ),
        FeedCheck("politics", "Example Courier", RSS_URL, "HTTP 200", 2, 1),
    ]
    out = io.StringIO()
    render(checks, out)
    lines = out.getvalue().splitlines()
    assert lines[1].split()[-1] == WIRE_URL
    assert lines[2] == "    why: starts with y"
    assert lines[3].split()[-1] == RSS_URL
    assert lines[4] == "2 feeds checked, 1 failed"
