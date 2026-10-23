"""The coach's follow-ups on the search pages, through the real app (`v1-e39-t11`).

The result count above the results, "Back to results" on a card page, the link out to openCaselist,
over `conftest.CORPUS`. Every expected value is written by hand from that corpus (working agreement
6): 25 cards hold `zephyr` (20 on the first page, 5 on the second), and of them one, the public forum
card, is PF and one is a camp card; one card holds `granite costs`; none holds `obsidian`. The linked
card, which holds `tundra`, is the only one whose school and team code are in the form an openCaselist
address takes. Copy card without its provenance line is in `test_copy_card.py`.
"""

from __future__ import annotations

import html
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, Final
from urllib.parse import parse_qs, urlsplit

import pytest

from debate_api.configuration import ConfigurationMissing, PilotConfiguration
from debate_core.application.search_index_holder import SearchIndexHolder
from debate_core.domain.evidence_search import ResultCount, SearchHit, SearchPage, SnippetSegment
from debate_core.integrations.local.search_index import SqliteSearchIndexWriter
from debate_core.testing.search_index import published_index

LINKED_URL: Final = "https://opencaselist.com/hsld26/Cedarbrook/LM"


@pytest.fixture
def student(world: Any) -> Any:
    world.signed_in_student()
    return world


def hrefs_of(page: str) -> list[str]:
    """The result links of a results page, as the browser reads them."""
    return [html.unescape(one) for one in re.findall(r'<h3 class="result-tag"><a href="([^"]+)">', page)]


def count_line(page: str) -> str | None:
    found = re.findall(r'<p class="result-count">(.*?)</p>', page)
    assert len(found) <= 1
    return found[0] if found else None


def back_link(page: str) -> tuple[str, str]:
    """The card page's way back: its address, as the browser reads it, and its words."""
    [(href, words)] = re.findall(
        r'<nav class="back-link" aria-label="Back"><a href="([^"]*)">([^<]*)</a></nav>', page
    )
    return html.unescape(href), words


def next_link(page: str) -> str:
    found = re.search(r'<a href="([^"]+)" rel="next">Next results</a>', page)
    assert found is not None
    return html.unescape(found.group(1))


# ------------------------------------------------------------------------------------------------
# The count
# ------------------------------------------------------------------------------------------------


def test_a_search_shows_how_many_cards_matched_above_the_results_on_every_page(student: Any) -> None:
    first = student.browser.get("/search?q=zephyr").text
    second = student.browser.get(next_link(first)).text

    assert count_line(first) == count_line(second) == "25 cards matched."
    assert first.index('class="result-count"') < first.index('class="result-list"')
    assert first.index('id="results-heading"') < first.index('class="result-count"')


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("granite+costs", "1 card matched."),
        ("zephyr&event=PF", "1 card matched."),
        ("zephyr&event=LD", "23 cards matched."),
        ("zephyr&caselist=openev", "1 card matched."),
        ("zephyr&side=NEG", "23 cards matched."),
        ("tundra", "1 card matched."),
    ],
)
def test_the_count_is_for_the_query_and_its_filters(student: Any, query: str, expected: str) -> None:
    """Of the 25 `zephyr` cards one is PF (Pro) and one a camp card (POLICY, no side). The other 23 are
    LD, and each was disclosed Neg: the featured card on both sides, the rest Neg alone."""
    assert count_line(student.browser.get(f"/search?q={query}").text) == expected


def test_a_search_with_no_match_or_nothing_to_search_for_shows_no_count(student: Any) -> None:
    nothing = student.browser.get("/search?q=obsidian").text
    excluded = student.browser.get("/search?q=-zephyr").text

    assert count_line(nothing) is None and "<p>No cards matched.</p>" in nothing
    assert count_line(excluded) is None


@pytest.fixture
def capped(make_world: Callable[..., Any]) -> Iterator[Any]:
    """A world whose searches count no further than ten."""
    made = make_world(count_cap=10)
    made.signed_in_student()
    yield made
    made.services.search_index.close()


def test_past_the_cap_the_count_says_more_than_the_cap(capped: Any) -> None:
    first = capped.browser.get("/search?q=zephyr").text

    assert count_line(first) == "10+ cards matched."
    assert len(hrefs_of(first)) == 20
    assert count_line(capped.browser.get("/search?q=zephyr&event=PF").text) == "1 card matched."


@contextmanager
def answering(world: Any, page: SearchPage) -> Iterator[None]:
    """The holder's search answers `page`, whatever is asked."""

    class Answer:
        def search(self, *_: object, **__: object) -> SearchPage:
            return page

    holder: SearchIndexHolder = world.services.search_index

    @contextmanager
    def lease() -> Iterator[Any]:
        yield Answer()

    original = holder.lease
    holder.lease = lease  # type: ignore[method-assign]
    try:
        yield
    finally:
        holder.lease = original  # type: ignore[method-assign]


HIT: Final = SearchHit(
    caselist="hsld26",
    cluster_id=f"{1:064x}",
    event="LD",
    camp=None,
    tag="Zephyr winds raise granite costs",
    short_cite="Lindqvist 26",
    snippet=(SnippetSegment("zephyr", True),),
    file_count=1,
    team_count=1,
    provenance_line=None,
)


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (ResultCount(1000, capped=True), "1,000+ cards matched."),
        (ResultCount(1000), "1,000 cards matched."),
        (ResultCount(1234), "1,234 cards matched."),
        (ResultCount(2), "2 cards matched."),
        (None, None),
    ],
)
def test_the_count_is_written_with_thousands_separated(
    student: Any, count: ResultCount | None, expected: str | None
) -> None:
    with answering(student, SearchPage(hits=(HIT,), next_cursor=None, count=count)):
        page = student.browser.get("/search?q=zephyr").text

    assert count_line(page) == expected


def test_the_searched_audit_record_still_counts_the_first_pages_results_not_the_total(student: Any) -> None:
    """`v1-e39-t07` defined the searched record's count as the results on the first page."""
    page = student.browser.get("/search?q=zephyr").text

    assert count_line(page) == "25 cards matched."
    [record] = [one for one in student.audit.records if one.action.value == "searched"]
    assert record.count == 20


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, 1000), ("250", 250), (" 40 ", 40), ("1", 1), ("100000", 100_000)],
)
def test_the_count_cap_is_read_from_the_environment(value: str | None, expected: int) -> None:
    environ = dict(REQUIRED_ENVIRONMENT)
    if value is not None:
        environ["TUB_RESULT_COUNT_CAP"] = value

    assert PilotConfiguration.from_environment(environ).result_count_cap == expected


@pytest.mark.parametrize("value", ["0", "-5", "100001", "1e3", "a thousand", "1,000"])
def test_a_count_cap_that_is_not_a_whole_number_from_one_to_the_cursor_limit_is_refused(value: str) -> None:
    with pytest.raises(ConfigurationMissing, match="TUB_RESULT_COUNT_CAP"):
        PilotConfiguration.from_environment({**REQUIRED_ENVIRONMENT, "TUB_RESULT_COUNT_CAP": value})


REQUIRED_ENVIRONMENT: Final = {
    "TUB_ENVIRONMENT": "dev",
    "TUB_PUBLIC_ORIGIN": "https://tub.example.test",
    "TUB_LOGIN_ORIGIN": "https://auth.tub.example.test",
    "TUB_USER_POOL_ID": "us-east-1_SyntheticPool",
    "TUB_CLIENT_ID": "synthetic-client-id",
    "TUB_CLIENT_SECRET_PARAMETER": "/debate-dev-tub/client-secret",
    "TUB_COOKIE_KEYS_PARAMETER": "/debate-dev-tub/cookie-keys",
    "TUB_AUDIT_LOG_GROUP": "debate-dev-tub-audit",
    "TUB_EVIDENCE_BUCKET": "debate-dev-evidence-synthetic",
}


# ------------------------------------------------------------------------------------------------
# Back to results
# ------------------------------------------------------------------------------------------------


def test_each_result_links_to_its_card_with_the_searchs_words_filters_and_page(student: Any) -> None:
    first = student.browser.get("/search?q=zephyr+winds&event=LD&side=NEG&since=2026-09-01").text
    zephyr = student.browser.get("/search?q=zephyr").text
    second = student.browser.get(next_link(zephyr)).text
    cursor = parse_qs(urlsplit(next_link(zephyr)).query)["cursor"][0]

    assert hrefs_of(first) == [
        f"{student.card_path('featured')}?q=zephyr+winds&event=LD&side=NEG&since=2026-09-01"
    ]
    assert all(href.endswith("?q=zephyr") for href in hrefs_of(zephyr))
    assert hrefs_of(second) and all(href.endswith(f"?q=zephyr&cursor={cursor}") for href in hrefs_of(second))


def test_a_card_opened_from_a_results_page_links_back_to_that_page(student: Any) -> None:
    zephyr = student.browser.get("/search?q=zephyr&event=LD").text
    second_page = next_link(zephyr)
    second = student.browser.get(second_page).text

    card = student.browser.get(hrefs_of(second)[0])
    href, words = back_link(card.text)

    assert card.status_code == 200
    assert (href, words) == (second_page, "Back to results")
    returned = student.browser.get(href)
    assert returned.status_code == 200
    assert hrefs_of(returned.text) == hrefs_of(second)


def test_a_card_opened_from_the_first_page_links_back_to_the_first_page(student: Any) -> None:
    card = student.browser.get(hrefs_of(student.browser.get("/search?q=granite+costs").text)[0]).text

    assert back_link(card) == ("/search?q=granite+costs", "Back to results")


def test_a_card_opened_without_a_search_links_to_a_new_search(student: Any) -> None:
    assert back_link(student.browser.get(student.card_path("featured")).text) == ("/search", "New search")


def cursor_of_the_second_page(world: Any) -> str:
    return parse_qs(urlsplit(next_link(world.browser.get("/search?q=zephyr").text)).query)["cursor"][0]


@pytest.mark.parametrize(
    "query",
    [
        "event=LD",
        "q=",
        "q=%20%20",
        "q=zephyr&event=COLLEGE",
        "q=zephyr&event=lD",
        "q=zephyr&side=UNKNOWN",
        "q=zephyr&caselist=..%2Fraw",
        "q=zephyr&caselist=HSLD26",
        "q=zephyr&since=yesterday",
        "q=zephyr&since=2026-02-30",
        "q=zephyr&cursor=" + "A" * 65,
        "q=zephyr&cursor=not-a-cursor",
        "q=zephyr&cursor=https%3A%2F%2Fevil.example.test%2F",
        "q=zephyr&caselist=https%3A%2F%2Fevil.example.test",
        "q=zephyr&event=PF&event=https%3A%2F%2Fevil.example.test",
    ],
)
def test_a_tampered_or_missing_search_lands_on_a_new_search(student: Any, query: str) -> None:
    response = student.browser.get(f"{student.card_path('featured')}?{query}")

    assert response.status_code == 200
    assert back_link(response.text) == ("/search", "New search")
    assert "evil.example.test" not in response.text


def test_a_cursor_from_another_search_lands_on_a_new_search(student: Any) -> None:
    cursor = cursor_of_the_second_page(student)

    for query in (f"q=granite&cursor={cursor}", f"q=zephyr&event=LD&cursor={cursor}"):
        page = student.browser.get(f"{student.card_path('featured')}?{query}").text
        assert back_link(page) == ("/search", "New search"), query
    tampered = cursor[:-2] + ("A" if cursor[-2] != "A" else "B") + cursor[-1]
    page = student.browser.get(f"{student.card_path('featured')}?q=zephyr&cursor={tampered}").text
    assert back_link(page) == ("/search", "New search")
    page = student.browser.get(f"{student.card_path('featured')}?q=zephyr&cursor={cursor}").text
    assert back_link(page) == (f"/search?q=zephyr&cursor={cursor}", "Back to results")


def test_a_cursor_from_an_index_since_replaced_lands_on_a_new_search(student: Any, tmp_path: Any) -> None:
    """The weekly refresh publishes a new index; a page's cursor from the old one is stale."""
    from datetime import timedelta

    cursor = cursor_of_the_second_page(student)
    path = tmp_path / "search-index.sqlite"
    sink = SqliteSearchIndexWriter().create(path)
    for document in student.corpus[:-1]:
        sink.add(document)
    sink.finish()
    replacement = published_index(
        path.read_bytes(), documents_by_store={"hsld26": 23, "hspf26": 1, "openev": 1}
    )
    student.index_source.publish(replacement)
    student.clock.advance(timedelta(minutes=5))

    page = student.browser.get(f"{student.card_path('featured')}?q=zephyr&cursor={cursor}").text

    assert student.services.search_index.loaded_index_id == replacement.index_id != student.index.index_id
    assert back_link(page) == ("/search", "New search")


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("q=zephyr&next=https%3A%2F%2Fevil.example.test", "/search?q=zephyr"),
        ("q=zephyr&return_to=%2F%2Fevil.example.test", "/search?q=zephyr"),
        ("q=%2F%2Fevil.example.test", "/search?q=%2F%2Fevil.example.test"),
        ("q=https%3A%2F%2Fevil.example.test", "/search?q=https%3A%2F%2Fevil.example.test"),
        (
            "q=zephyr%0D%0ALocation%3A+https%3A%2F%2Fevil",
            "/search?q=zephyr%0D%0ALocation%3A+https%3A%2F%2Fevil",
        ),
        (
            'q=zephyr"><script>alert(1)</script>',
            "/search?q=zephyr%22%3E%3Cscript%3Ealert%281%29%3C%2Fscript%3E",
        ),
    ],
)
def test_a_parameter_that_points_outside_the_pilot_never_becomes_the_link(
    student: Any, query: str, expected: str
) -> None:
    """The way back is the pilot's own `/search`, built from the validated words and filters alone."""
    page = student.browser.get(f"{student.card_path('featured')}?{query}").text

    href, words = back_link(page)
    assert (href, words) == (expected, "Back to results")
    assert href.startswith("/search") and not href.startswith("//")
    assert "<script>alert" not in page


def test_the_back_link_is_the_validated_search_in_one_order_whatever_order_it_came_in(student: Any) -> None:
    page = student.browser.get(
        f"{student.card_path('featured')}?since=2026-09-01&side=NEG&q=zephyr&event=LD"
    ).text

    assert back_link(page)[0] == "/search?q=zephyr&event=LD&side=NEG&since=2026-09-01"


def test_a_card_page_with_its_search_still_writes_only_its_card_viewed_record(student: Any) -> None:
    href = hrefs_of(student.browser.get("/search?q=granite+costs&event=LD").text)[0]
    before = len(student.audit.records)

    assert student.browser.get(href).status_code == 200

    [record] = student.audit.records[before:]
    assert record.action.value == "card-viewed"
    assert "granite" not in record.to_json() and "q=" not in record.to_json()


def test_the_copy_route_answers_the_same_with_or_without_a_search(student: Any) -> None:
    path = student.card_path("featured") + "/copy"

    assert student.browser.get(path + "?q=zephyr&cursor=junk").json() == student.browser.get(path).json()


# ------------------------------------------------------------------------------------------------
# Open on openCaselist
# ------------------------------------------------------------------------------------------------


def source_links(page: str) -> list[str]:
    return re.findall(r'<p class="source-link">(.*?)</p>', page)


def test_a_disclosed_card_links_to_its_teams_page_on_opencaselist_in_a_new_tab_with_no_referrer(
    student: Any,
) -> None:
    page = student.browser.get(student.card_path("linked")).text

    assert source_links(page) == [
        f'<a href="{LINKED_URL}" target="_blank" rel="noopener noreferrer">Open on openCaselist'
        '<span class="new-tab"> (opens in a new tab)</span></a>'
    ]
    head = page.split("<!--card-body-->")[0]
    line = "[Disclosed: hsld26 2026-09-15 — Cedarbrook LM, Neg vs. Invented Invitational Round 4]"
    assert head.index(f'<p class="provenance">{line}</p>') < head.index('<p class="source-link">')


def test_a_card_whose_school_is_not_in_the_urls_form_shows_no_link(student: Any) -> None:
    """The featured card's school, Maple Grove, has a space: no openCaselist address spells it so."""
    page = student.browser.get(student.card_path("featured")).text

    assert source_links(page) == []
    assert "opencaselist.com" not in page


def test_a_camp_card_shows_no_link_because_the_index_has_no_openev_address(student: Any) -> None:
    page = student.browser.get(student.card_path("camp")).text

    assert source_links(page) == []
    assert "Open on" not in page


def test_the_link_out_writes_nothing_and_the_card_page_writes_its_one_record(student: Any) -> None:
    """The link leaves the platform, so it is no route of the pilot's and has no record of its own."""
    before = len(student.audit.records)

    page = student.browser.get(student.card_path("linked")).text

    assert [one.action.value for one in student.audit.records[before:]] == ["card-viewed"]
    assert LINKED_URL in page and "Cedarbrook" not in student.audit.records[-1].to_json()
    assert "LM" not in student.audit.records[-1].to_json()
