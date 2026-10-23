"""Search by passage, prefixes and a format 1 index on the search pages, through the real app (`v1-e39-t13`).

Over `conftest.CORPUS`. Every expected value is written by hand from that corpus (working agreement 6):
25 cards hold `zephyr` (20 on the first page, 5 on the second); the featured card alone holds
`granite`, `costs`, `winds`, `raise`, `basalt` and `holds`; none holds `tumble` or `obsidian`.

The passage control is the student's choice: a checkbox on the search form, off by default, and the
search is today's search unless it is ticked. Its keyboard path at 1366 px, on a Chromebook's sizes
and a phone's, is in `browser/test_search_pages_in_chromium.py`.
"""

from __future__ import annotations

import gzip
import html
import logging
import re
from typing import Any, Final
from urllib.parse import parse_qs, urlsplit

import pytest

from debate_api.configuration import ConfigurationMissing, PilotConfiguration
from debate_core.application.tub.audit import AuditAction
from debate_core.testing.search_index import format_one_index, published_index

FEATURED_PASSAGE: Final = "The basalt holds when zephyr winds raise granite costs, and then prices tumble"
"""Nine content words once `the`, `when`, `and` and `then` are left out, so a card must hold six. The
featured card holds seven, every other card at most two, and no card holds `prices` or `tumble`."""

ENVIRONMENT: Final = {
    "TUB_ENVIRONMENT": "dev",
    "TUB_PUBLIC_ORIGIN": "https://tub.dev.example.test",
    "TUB_LOGIN_ORIGIN": "https://auth.tub.dev.example.test",
    "TUB_USER_POOL_ID": "us-east-1_synthetic",
    "TUB_CLIENT_ID": "synthetic-client",
    "TUB_CLIENT_SECRET_PARAMETER": "/debate-dev-tub/client-secret",
    "TUB_COOKIE_KEYS_PARAMETER": "/debate-dev-tub/cookie-keys",
    "TUB_AUDIT_LOG_GROUP": "debate-dev-tub-audit",
    "TUB_EVIDENCE_BUCKET": "debate-dev-evidence-synthetic",
}


@pytest.fixture
def student(world: Any) -> Any:
    world.signed_in_student()
    return world


def hrefs_of(page: str) -> list[str]:
    return [html.unescape(one) for one in re.findall(r'<h3 class="result-tag"><a href="([^"]+)">', page)]


def cards_of(page: str) -> list[int]:
    return [int(urlsplit(href).path.rsplit("/", 1)[1], 16) for href in hrefs_of(page)]


def count_line(page: str) -> str | None:
    found = re.findall(r'<p class="result-count">(.*?)</p>', page)
    return found[0] if found else None


def next_link(page: str) -> str:
    found = re.search(r'<a href="([^"]+)" rel="next">Next results</a>', page)
    assert found is not None
    return html.unescape(found.group(1))


def back_link(page: str) -> str:
    [href] = re.findall(r'<nav class="back-link" aria-label="Back"><a href="([^"]*)">', page)
    return html.unescape(href)


def searched_records(world: Any) -> list[Any]:
    return [record for record in world.audit.records if record.action is AuditAction.SEARCHED]


# ------------------------------------------------------------------------------------------------
# The control
# ------------------------------------------------------------------------------------------------


def test_the_search_form_offers_search_by_passage_unticked_by_default(student: Any) -> None:
    page = student.browser.get("/search").text
    assert (
        '<input id="mode" name="mode" type="checkbox" value="passage" aria-describedby="mode-help">' in page
    )
    assert '<label for="mode">Search by passage</label>' in page
    assert '<p id="mode-help" class="help">' in page
    assert page.index('id="q"') < page.index('id="mode"') < page.index('class="filters"'), (
        "after the words, before the filters: the next stop after the search box"
    )


def test_the_search_form_keeps_search_by_passage_ticked_on_its_results(student: Any) -> None:
    page = student.browser.get("/search?q=zephyr&mode=passage").text
    assert (
        '<input id="mode" name="mode" type="checkbox" value="passage" checked aria-describedby="mode-help">'
        in page
    )


def test_a_mode_no_form_writes_is_refused(student: Any) -> None:
    response = student.browser.get("/search?q=zephyr&mode=everything")
    assert response.status_code == 400
    assert "That search could not be read." in response.text


# ------------------------------------------------------------------------------------------------
# A passage search
# ------------------------------------------------------------------------------------------------


def test_a_passage_finds_the_card_holding_most_of_its_words(student: Any) -> None:
    passage = student.browser.get("/search", params={"q": FEATURED_PASSAGE, "mode": "passage"}).text
    plain = student.browser.get("/search", params={"q": FEATURED_PASSAGE}).text

    assert cards_of(passage) == [student.cards["featured"]]
    assert count_line(passage) == "1 card matched."
    assert cards_of(plain) == [] and "<p>No cards matched.</p>" in plain, "as words, every one must match"


def test_a_passage_search_pages_counts_and_comes_back_in_passage_mode(student: Any) -> None:
    first = student.browser.get("/search?q=zephyr&mode=passage").text
    assert count_line(first) == "25 cards matched."
    assert len(cards_of(first)) == 20
    following = next_link(first)
    assert parse_qs(urlsplit(following).query)["mode"] == ["passage"]
    second = student.browser.get(following).text
    assert len(cards_of(second)) == 5
    assert count_line(second) == "25 cards matched."

    href = hrefs_of(second)[0]
    assert parse_qs(urlsplit(href).query)["mode"] == ["passage"]
    card = student.browser.get(href).text
    back = back_link(card)
    assert back == following, "Back to results is the passage page it came from"
    assert student.browser.get(back).status_code == 200


def test_a_plain_search_cursor_is_refused_in_passage_mode(student: Any) -> None:
    cursor = parse_qs(urlsplit(next_link(student.browser.get("/search?q=zephyr").text)).query)["cursor"][0]
    response = student.browser.get(f"/search?q=zephyr&mode=passage&cursor={cursor}")
    assert response.status_code == 400
    assert "That page of results is out of date." in response.text
    stale = student.browser.get(
        f"/cards/hsld26/{student.cards['featured']:064x}?q=zephyr&mode=passage&cursor={cursor}"
    ).text
    assert back_link(stale) == "/search", "a cursor of the other mode gives New search"


def test_a_passage_search_writes_one_searched_record_with_its_result_count_only(student: Any) -> None:
    student.browser.get("/search", params={"q": FEATURED_PASSAGE, "mode": "passage"})
    [record] = searched_records(student)
    assert record.count == 1
    assert "basalt" not in record.to_json() and "tumble" not in record.to_json()


_STANDARD_RECORD_FIELDS: Final = set(vars(logging.LogRecord("", 0, "", 0, "", None, None)))


def test_a_passage_or_prefix_search_logs_none_of_its_words(
    student: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """As `test_search_pages.py` reads the log: the app's records, their messages and extras. httpx's are
    the test client's own requests, made in this process; the app cannot log through httpx."""
    with caplog.at_level(logging.DEBUG):
        student.browser.get("/search", params={"q": FEATURED_PASSAGE, "mode": "passage"})
        student.browser.get("/search?q=gran*")
        student.browser.get("/search?q=gr*")
    logged = [
        " ".join(
            [record.name, record.getMessage()]
            + [f"{key}={value}" for key, value in vars(record).items() if key not in _STANDARD_RECORD_FIELDS]
        )
        for record in caplog.records
        if not record.name.startswith(("httpx", "httpcore"))
    ]
    assert any(f"search index {student.index.index_id} loaded" in line for line in logged), logged
    for line in logged:
        for word in ("basalt", "tumble", "granite", "gran", "passage", "q="):
            assert word not in line.lower(), (word, line)


# ------------------------------------------------------------------------------------------------
# Prefixes
# ------------------------------------------------------------------------------------------------


def test_a_prefix_finds_every_word_it_starts(student: Any) -> None:
    page = student.browser.get("/search?q=gran*+cost*").text
    assert cards_of(page) == [student.cards["featured"]]


def test_a_prefix_under_three_letters_is_refused_with_a_message_and_no_record(student: Any) -> None:
    page = student.browser.get("/search?q=zephyr+gr*").text
    assert (
        "A word ending in * needs at least 3 letters before the *, like gro*. Nothing was searched." in page
    )
    assert "No cards matched" not in page
    assert count_line(page) is None
    assert searched_records(student) == []


# ------------------------------------------------------------------------------------------------
# A format 1 index: the function deployed before the weekly update builds format 2
# ------------------------------------------------------------------------------------------------


def _publish_format_one(world: Any) -> None:
    """Publish the world's corpus as the format 1 index the function serves until the first format 2."""
    format_one = format_one_index(gzip.decompress(world.index_source.objects[world.index.object_key]))
    world.index_source.publish(
        published_index(
            format_one,
            documents_by_store=dict(world.index.manifest.counts.documents_by_store),
            format_version=1,
        )
    )
    world.services.search_index.close()


def test_on_format_one_a_plain_search_runs_and_says_words_are_matched_as_written(student: Any) -> None:
    _publish_format_one(student)
    page = student.browser.get("/search?q=zephyr").text
    assert count_line(page) == "25 cards matched."
    assert (
        "Until the next weekly update of the search, words are matched exactly as typed: grow does not find "
        "growing." in page
    )
    assert len(searched_records(student)) == 1


def test_on_format_one_a_passage_search_says_it_is_not_available_yet(student: Any) -> None:
    _publish_format_one(student)
    response = student.browser.get("/search", params={"q": FEATURED_PASSAGE, "mode": "passage"})
    assert response.status_code == 200
    assert (
        "Search by passage is not available until the next weekly update of the search. Untick it to search "
        "these words." in response.text
    )
    assert cards_of(response.text) == []
    assert "No cards matched" not in response.text
    assert searched_records(student) == []


# ------------------------------------------------------------------------------------------------
# The share's setting
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("value", "share"), [("", 66), ("100", 100), (" 50 ", 50), ("1", 1)])
def test_the_passage_share_is_an_optional_setting(value: str, share: int) -> None:
    configured = PilotConfiguration.from_environment({**ENVIRONMENT, "TUB_PASSAGE_SHARE_PERCENT": value})
    assert configured.passage_share_percent == share


@pytest.mark.parametrize("value", ["0", "101", "two thirds", "66.6", "-5"])
def test_a_passage_share_outside_one_to_a_hundred_stops_the_app(value: str) -> None:
    with pytest.raises(ConfigurationMissing, match="TUB_PASSAGE_SHARE_PERCENT"):
        PilotConfiguration.from_environment({**ENVIRONMENT, "TUB_PASSAGE_SHARE_PERCENT": value})
