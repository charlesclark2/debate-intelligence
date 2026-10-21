"""The search pages over the synthetic index, through the real app (`v1-e39-t06`).

The index is `conftest.CORPUS`, fetched by the real holder. Every expected value is written by hand
from that corpus (working agreement 6): 25 cards hold `zephyr` (the five named cards and twenty
fillers), so a search for it runs to a page of 20 and a page of 5; the featured card was disclosed
by two teams in three files; the public forum card is the only PF card; the camp card is the only
`openev` card.

The browser half (Chromium, the edge's CSP, keyboard, axe, Copy card's paste) is in
`browser/test_search_pages_in_chromium.py`.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from debate_api.app import PRIVATE_NO_STORE
from debate_api.search_pages import CAMP_LABEL
from debate_core.application.search_index_holder import SearchIndexHolder
from debate_core.domain.evidence_search import SearchHit, SearchPage, SnippetSegment
from debate_core.domain.search_index import SEARCH_INDEX_POINTER_KEY

PAGE_BUDGET = 150 * 1024
"""ADR-0019 (b) 1: a page weighs under 150 KB before the card body, its script and stylesheet included."""

FEATURED_LINE = "[Disclosed: hsld26 2026-09-15 — Maple Grove QX, Neg vs. Invented Invitational Round 4]"
OTHER_LINE = "[Disclosed: hsld26 2026-09-15 — Riverbend ZT, Aff vs. Invented Invitational Round 4]"
CAMP_LINE = "[OpenEv: Cascade Institute 2026 — Policy, Invented Adv CP]"


@pytest.fixture
def student(world: Any) -> Any:
    world.signed_in_student()
    return world


def results_of(page: str) -> list[str]:
    """The card paths a results page links to, in order."""
    return re.findall(r'<h3 class="result-tag"><a href="([^"]+)">', page)


def card_path(world: Any, doc_id: int, caselist: str = "hsld26") -> str:
    return f"/cards/{caselist}/{doc_id:064x}"


def without_card_body(page: str) -> str:
    before, rest = page.split("<!--card-body-->", 1)
    return before + rest.split("<!--/card-body-->", 1)[1]


def weight(world: Any, page: str) -> int:
    state = world.app.state.pilot
    return len(page.encode()) + len(state.app_script.content) + len(state.app_stylesheet.content)


# ------------------------------------------------------------------------------------------------
# The empty search page never waits for the index
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/", "/search", "/search?q=", "/search?q=%20%20&event=LD"])
def test_the_empty_search_page_answers_without_the_index(student: Any, path: str) -> None:
    response = student.browser.get(path)

    assert response.status_code == 200
    assert '<form class="search-form" method="get" action="/search" role="search">' in response.text
    assert 'id="results-heading"' not in response.text
    assert student.index_source.reads == []


def test_before_the_index_loads_the_caselist_filter_offers_any_caselist_only(student: Any) -> None:
    page = student.browser.get("/").text

    options = re.findall(r'<option value="([^"]*)"', page.split('id="caselist"')[1].split("</select>")[0])
    assert options == [""]


def test_once_the_index_is_loaded_the_caselist_filter_offers_its_stores(student: Any) -> None:
    student.browser.get("/search?q=zephyr")

    page = student.browser.get("/").text

    caselists = page.split('id="caselist"')[1].split("</select>")[0]
    assert re.findall(r'<option value="([^"]*)"', caselists) == ["", "hsld26", "hspf26", "openev"]
    assert f">{CAMP_LABEL}<" in caselists


# ------------------------------------------------------------------------------------------------
# Results, pages and filters
# ------------------------------------------------------------------------------------------------


def test_a_search_answers_twenty_results_and_a_link_to_the_next_five(student: Any) -> None:
    first = student.browser.get("/search?q=zephyr")

    assert first.status_code == 200
    assert len(results_of(first.text)) == 20
    next_link = re.search(r'<a href="([^"]+)" rel="next">Next results</a>', first.text)
    assert next_link is not None
    assert "First page" not in first.text

    second = student.browser.get(next_link.group(1).replace("&amp;", "&"))

    assert second.status_code == 200
    assert len(results_of(second.text)) == 5
    assert 'rel="next"' not in second.text
    assert '<a href="/search?q=zephyr">First page</a>' in second.text
    assert set(results_of(first.text)).isdisjoint(results_of(second.text))
    assert len(set(results_of(first.text) + results_of(second.text))) == 25


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("event=PF", [(2, "hspf26")]),
        ("caselist=openev", [(3, "openev")]),
        ("caselist=hspf26", [(2, "hspf26")]),
        ("side=PRO", [(2, "hspf26")]),
        ("side=AFF", [(1, "hsld26")]),
    ],
)
def test_each_filter_narrows_the_results(student: Any, query: str, expected: list[tuple[int, str]]) -> None:
    page = student.browser.get(f"/search?q=zephyr&{query}").text

    assert results_of(page) == [card_path(student, doc_id, caselist) for doc_id, caselist in expected]


def test_the_filters_keep_their_values_on_the_results_page(student: Any) -> None:
    page = student.browser.get("/search?q=zephyr&event=LD&side=NEG&since=2026-09-01&caselist=hsld26").text

    assert '<option value="LD" selected>' in page
    assert '<option value="NEG" selected>' in page
    assert '<option value="hsld26" selected>' in page
    assert 'name="since" type="date" value="2026-09-01"' in page
    assert 'value="zephyr"' in page


def test_a_side_filter_is_labelled_caselist_cards_only_next_to_it_and_leaves_camp_cards_out(
    student: Any,
) -> None:
    page = student.browser.get("/search?q=zephyr&side=NEG").text

    side = page.split('id="side"')[1].split('<div class="filter">')[0]
    assert 'class="filter-note filter-note-applied">Caselist cards only: camp cards have no side' in side
    assert card_path(student, 3, "openev") not in results_of(page)
    since = page.split('id="since"')[1]
    assert 'class="filter-note">Caselist cards only' in since


def test_a_date_filter_is_labelled_caselist_cards_only_next_to_it_and_leaves_camp_cards_out(
    student: Any,
) -> None:
    page = student.browser.get("/search?q=zephyr&since=2026-09-01").text

    since = page.split('id="since"')[1].split("</fieldset>")[0]
    assert (
        'class="filter-note filter-note-applied">Caselist cards only: camp cards have no first-seen' in since
    )
    assert card_path(student, 3, "openev") not in results_of(page)
    assert len(results_of(page)) == 20
    side = page.split('id="side"')[1].split('<div class="filter">')[0]
    assert 'class="filter-note">Caselist cards only' in side


def test_without_those_filters_the_camp_card_is_found_and_neither_note_is_applied(student: Any) -> None:
    page = student.browser.get("/search?q=camp").text

    assert results_of(page) == [card_path(student, 3, "openev")]
    assert "filter-note-applied" not in page


def test_a_result_shows_its_tag_short_cite_snippet_counts_and_provenance_line(student: Any) -> None:
    page = student.browser.get("/search?q=granite+costs").text

    [result] = re.findall(r'<li class="result">(.*?)</li>', page, re.DOTALL)
    assert f'<a href="{card_path(student, 1)}">Zephyr winds raise granite costs</a>' in result
    assert '<p class="result-cite">Lindqvist 26</p>' in result
    assert "<mark>granite</mark>" in result and "<mark>costs</mark>" in result
    assert '<p class="result-counts">In 3 files from 2 teams.</p>' in result
    assert f'<p class="provenance">{FEATURED_LINE}</p>' in result


def test_a_camp_result_counts_its_files_and_names_no_team(student: Any) -> None:
    page = student.browser.get("/search?q=camp").text

    assert '<p class="result-counts">In 1 file.</p>' in page
    assert f'<p class="provenance">{CAMP_LINE}</p>' in page


@contextmanager
def answering(world: Any, page: SearchPage) -> Iterator[None]:
    """The holder's search answers `page`, whatever is asked: a team count no corpus card has."""

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


def test_a_missing_team_count_is_shown_without_a_number(student: Any) -> None:
    hit = SearchHit(
        caselist="hsld26",
        cluster_id=f"{1:064x}",
        event="LD",
        camp=None,
        tag="Zephyr winds raise granite costs",
        short_cite="Lindqvist 26",
        snippet=(SnippetSegment("zephyr", True),),
        file_count=2,
        team_count=None,
        provenance_line=FEATURED_LINE,
    )
    with answering(student, SearchPage(hits=(hit,), next_cursor=None)):
        page = student.browser.get("/search?q=zephyr").text

    [counts] = re.findall(r'<p class="result-counts">(.*?)</p>', page)
    assert counts == "In 2 files. The number of teams is not known until the next weekly update."
    assert re.search(r"\d+ teams?", counts) is None


def test_a_query_with_only_excluded_words_says_there_is_nothing_to_search_for(student: Any) -> None:
    page = student.browser.get("/search?q=-zephyr").text

    assert "There is no word to search for." in page
    assert results_of(page) == []
    assert "No cards matched" not in page


def test_a_long_query_says_only_its_first_part_was_used(student: Any) -> None:
    page = student.browser.get("/search?q=" + "+".join(["zephyr"] * 40)).text

    assert "Your search was long, so only its first part was used." in page


def test_a_search_with_no_match_says_so(student: Any) -> None:
    page = student.browser.get("/search?q=obsidian").text

    assert "<p>No cards matched.</p>" in page


@pytest.mark.parametrize(
    "query",
    [
        "event=COLLEGE",
        "event=lD",
        "side=UNKNOWN",
        "caselist=..%2Fraw",
        "since=yesterday",
        "cursor=" + "A" * 65,
    ],
)
def test_a_filter_no_form_writes_is_refused_with_a_message(student: Any, query: str) -> None:
    response = student.browser.get(f"/search?q=zephyr&{query}")

    assert response.status_code == 400
    assert "That search could not be read. Choose the filters again." in response.text
    assert results_of(response.text) == []


def test_a_cursor_from_another_search_is_refused_with_a_link_back_to_the_first_page(student: Any) -> None:
    first = student.browser.get("/search?q=zephyr").text
    cursor = re.search(r'cursor=([A-Za-z0-9_-]+)" rel="next"', first)
    assert cursor is not None

    response = student.browser.get(f"/search?q=granite&cursor={cursor.group(1)}")

    assert response.status_code == 400
    assert "That page of results is out of date." in response.text
    assert 'value="granite"' in response.text


def test_a_search_rechecks_the_pointer_by_conditional_get_five_minutes_on(student: Any) -> None:
    from datetime import timedelta

    student.browser.get("/search?q=zephyr")
    student.clock.advance(timedelta(minutes=5))

    student.browser.get("/search?q=zephyr")

    assert student.index_source.reads.count(SEARCH_INDEX_POINTER_KEY) == 2
    assert student.index_source.not_modified == 1


def test_with_no_index_published_a_search_says_search_is_unavailable(world: Any) -> None:
    world.signed_in_student()
    del world.index_source.objects[SEARCH_INDEX_POINTER_KEY]

    response = world.browser.get("/search?q=zephyr")

    assert response.status_code == 503
    assert "Search is not available right now" in response.text
    assert world.browser.get("/").status_code == 200
    assert world.browser.get(world.card_path("featured")).status_code == 503


# ------------------------------------------------------------------------------------------------
# The card page
# ------------------------------------------------------------------------------------------------


def test_the_card_page_shows_the_label_tag_cite_line_counts_copy_card_and_every_occurrence(
    student: Any,
) -> None:
    response = student.browser.get(student.card_path("featured"))
    page = response.text

    assert response.status_code == 200
    assert response.headers["cache-control"] == PRIVATE_NO_STORE
    assert '<p class="card-label">Disclosed evidence, not platform-verified</p>' in page
    assert '<h1 id="card-tag" class="card-tag">Zephyr winds raise granite costs</h1>' in page
    assert '<p class="card-cite-line">Lindqvist 26, Invented Quarterly, 2026</p>' in page
    head = page.split("<!--card-body-->")[0]
    assert f'<p class="provenance">{FEATURED_LINE}</p>' in head
    assert '<p class="card-counts">In 3 files from 2 teams.</p>' in head
    copy = f'<button type="button" data-tub-copy="{student.card_path("featured")}/copy">Copy card</button>'
    assert copy in head
    occurrences = page.split('<ul class="occurrences">')[1].split("</ul>")[0]
    assert re.findall(r'<li class="provenance">(.*?)</li>', occurrences) == [FEATURED_LINE, OTHER_LINE]
    assert "1 more file. The search keeps who disclosed a card for its first five files only." in occurrences


def test_the_card_page_renders_the_card_through_the_escaping_renderer(student: Any) -> None:
    body = student.browser.get(student.card_path("featured")).text.split("<!--card-body-->")[1]
    body = body.split("<!--/card-body-->")[0]

    assert (
        '<span class="card-underline card-highlight card-highlight-cyan card-size-22">winds raise</span>'
        in body
    )
    assert "<br>" in body
    assert "<details" not in body


def test_hostile_card_text_is_escaped_on_the_results_and_card_pages(student: Any) -> None:
    results = student.browser.get("/search?q=hostile").text
    card = student.browser.get(student.card_path("hostile")).text

    for page in (results, card):
        assert "<script>alert" not in page and "<img src=x" not in page and "<style>body" not in page
        assert re.search(
            r"&lt;script&gt;alert\((&#39;|&#x27;)tag(&#39;|&#x27;)\)&lt;/script&gt; zephyr hostile", page
        )
    assert "&lt;img src=x onerror=alert(1)&gt;" in card
    assert re.search(r"(&#34;|&quot;)onerror=alert\(1\)(&#34;|&quot;) &lt;b&gt;Quarterly&lt;/b&gt;", card)
    assert '<span class="card-highlight card-highlight-other">zephyr</span>' in card
    assert "chartreuse" not in card


@pytest.mark.parametrize(
    "path",
    [
        f"/cards/hsld26/{999:064x}",
        f"/cards/hspf26/{1:064x}",
        "/cards/hsld26/not-a-cluster-id",
        f"/cards/HSLD26/{1:064x}",
        f"/cards/hsld26/{0xABC:064X}",
    ],
)
def test_a_card_that_is_not_in_the_index_is_not_found(student: Any, path: str) -> None:
    response = student.browser.get(path)

    assert response.status_code == 404
    assert "That card is not in the search" in response.text


def test_a_malformed_card_address_is_not_found_without_touching_the_index(student: Any) -> None:
    assert student.browser.get("/cards/hsld26/not-a-cluster-id").status_code == 404

    assert student.index_source.reads == []


# ------------------------------------------------------------------------------------------------
# A card over 3,000 words (ac5)
# ------------------------------------------------------------------------------------------------


def test_a_card_over_three_thousand_words_leads_with_its_read_aloud_text_and_the_rest_in_details(
    student: Any,
) -> None:
    page = student.browser.get(student.card_path("long")).text
    body = page.split("<!--card-body-->")[1].split("<!--/card-body-->")[0]

    read_aloud, whole = body.split('<details class="card-whole">')
    assert "<h2>Read aloud</h2>" in read_aloud
    assert "This card is 3,200 words long" in read_aloud
    assert '<div class="card-text card-read-aloud">Zephyr read aloud stretch</div>' in read_aloud
    assert "granite basalt" not in read_aloud
    assert whole.startswith("\n<summary>Show the whole card</summary>")
    assert whole.count("feldspar") > 300
    assert "<details open" not in page


def test_a_card_of_three_thousand_words_or_fewer_is_shown_whole(student: Any) -> None:
    page = student.browser.get(student.card_path("featured")).text

    assert "Read aloud" not in page and "<details" not in page


def test_a_long_cards_result_carries_a_snippet_not_the_card_and_its_page_keeps_the_budget(
    student: Any,
) -> None:
    page = student.browser.get("/search?q=feldspar").text

    [snippet] = re.findall(r'<p class="result-snippet">(.*?)</p>', page)
    assert len(re.sub(r"<[^>]+>", "", snippet).split()) <= 24
    assert page.count("feldspar") < 10
    assert weight(student, page) < PAGE_BUDGET


def test_the_long_card_page_keeps_the_budget_before_its_card_body(student: Any) -> None:
    page = student.browser.get(student.card_path("long")).text

    assert len(page.encode()) > PAGE_BUDGET // 8
    assert weight(student, without_card_body(page)) < PAGE_BUDGET


# ------------------------------------------------------------------------------------------------
# Every page: no inline script or style, nothing from another origin, the weight budget (ac3)
# ------------------------------------------------------------------------------------------------


EVERY_PAGE = [
    "/",
    "/search?q=zephyr",
    "/search?q=zephyr&side=NEG&since=2026-09-01",
    "/search?q=-zephyr",
    "/search?q=zephyr&event=COLLEGE",
    "<card featured>",
    "<card long>",
    "<card hostile>",
    "<card camp>",
    f"/cards/hsld26/{999:064x}",
    "/account",
    "/coach",
]


@pytest.fixture
def every_page(world: Any) -> dict[str, str]:
    world.login.add_account("coach.one", "coach")
    world.use_session(world.session_for("coach.one"))
    pages: dict[str, str] = {}
    for path in EVERY_PAGE:
        if path.startswith("<card "):
            path = world.card_path(path.removeprefix("<card ").removesuffix(">"))
        response = world.browser.get(path)
        assert response.headers["content-type"].startswith("text/html"), path
        pages[path] = response.text
    return pages


def tags_of(page: str) -> list[str]:
    """Every tag the page writes. Card text is escaped, so a `<` in it is never one."""
    return re.findall(r"<[a-zA-Z][^>]*>", page)


def test_every_search_page_loads_only_the_first_party_script_and_stylesheet_and_nothing_inline(
    world: Any, every_page: dict[str, str]
) -> None:
    state = world.app.state.pilot
    for path, page in every_page.items():
        assert re.findall(r"<script\b[^>]*>", page) == [f'<script src="{state.app_script.path}" defer>'], path
        assert re.findall(r"<script\b[^>]*>(.*?)</script>", page, re.DOTALL) == [""], path
        assert re.findall(r"<link\b[^>]*>", page) == [
            f'<link rel="stylesheet" href="{state.app_stylesheet.path}">'
        ]
        assert "<style" not in page.lower(), path
        for tag in tags_of(page):
            assert re.search(r"\sstyle=", tag, re.IGNORECASE) is None, (path, tag)
            assert re.search(r"\son[a-z]+=", tag, re.IGNORECASE) is None, (path, tag)
            assert "javascript:" not in tag.lower(), (path, tag)


def test_no_search_page_names_another_origin(every_page: dict[str, str]) -> None:
    for path, page in every_page.items():
        for tag in tags_of(page):
            for attribute in re.findall(r'\s(?:src|href|action|data-tub-copy)="([^"]*)"', tag):
                own = attribute.startswith("/") and not attribute.startswith("//")
                assert own or attribute.startswith("#"), (path, attribute)


def test_every_search_page_keeps_the_weight_budget_before_its_card_body(
    world: Any, every_page: dict[str, str]
) -> None:
    for path, page in every_page.items():
        kept = without_card_body(page) if "<!--card-body-->" in page else page
        assert weight(world, kept) < PAGE_BUDGET, (path, weight(world, kept))


def test_the_stylesheet_is_served_at_its_hash_and_cached_for_a_year(world: Any) -> None:
    from debate_api.pages import IMMUTABLE

    stylesheet = world.app.state.pilot.app_stylesheet

    response = world.browser.get(stylesheet.path)

    assert response.status_code == 200
    assert response.headers["cache-control"] == IMMUTABLE
    assert response.headers["content-type"].startswith("text/css")
    assert world.browser.get(f"/static/{stylesheet.digest}/app.js").status_code == 404
    assert world.browser.get(f"/static/{stylesheet.digest}/other.css").status_code == 404


def test_the_stylesheet_loads_nothing_from_anywhere(world: Any) -> None:
    css = world.app.state.pilot.app_stylesheet.content.decode()

    assert "url(" not in css and "@import" not in css and "@font-face" not in css
    assert re.search(r"[a-z]+://", css) is None


def test_the_stylesheet_styles_every_class_the_card_renderer_can_write(world: Any) -> None:
    from debate_core.domain.search_card_html import EMPHASIS_CLASSES, HIGHLIGHT_COLOURS, OTHER_HIGHLIGHT_CLASS

    css = world.app.state.pilot.app_stylesheet.content.decode()
    classes = [
        *EMPHASIS_CLASSES.values(),
        OTHER_HIGHLIGHT_CLASS,
        *(f"card-highlight-{c}" for c in HIGHLIGHT_COLOURS),
    ]
    unstyled = [name for name in classes if f".{name} " not in css and f".{name}{{" not in css]

    assert unstyled == ["card-highlight"]
    assert all(f".card-size-{size}{{" in css for size in range(8, 73))


# ------------------------------------------------------------------------------------------------
# Nothing logged carries the query, a card id with a user, or card text
# ------------------------------------------------------------------------------------------------

_STANDARD_RECORD_FIELDS = set(vars(logging.LogRecord("", 0, "", 0, "", None, None)))


def test_the_app_logs_no_query_card_id_or_card_text_for_a_search_a_card_view_and_a_copy(
    world: Any, caplog: pytest.LogCaptureFixture
) -> None:
    world.signed_in_student("debater.private")
    featured = world.card_path("featured")
    with caplog.at_level(logging.DEBUG):
        assert world.browser.get("/search?q=zephyr+granite&event=LD&side=NEG").status_code == 200
        assert world.browser.get(featured).status_code == 200
        assert world.browser.get(featured + "/copy").status_code == 200
        assert world.browser.get("/search?q=obsidian+quartz&cursor=bogus").status_code == 400

    # httpx's own records are the test client's requests, made in this process: the app cannot log
    # through httpx, which an import contract keeps out of debate_api.
    logged = [
        " ".join(
            [record.name, record.getMessage()]
            + [f"{key}={value}" for key, value in vars(record).items() if key not in _STANDARD_RECORD_FIELDS]
        )
        for record in caplog.records
        if not record.name.startswith(("httpx", "httpcore"))
    ]
    assert any(f"search index {world.index.index_id} loaded" in line for line in logged), logged
    forbidden = [
        "zephyr",
        "granite",
        "obsidian",
        "quartz",
        f"{1:064x}",
        "Lindqvist",
        "Maple Grove",
        "QX",
        "Riverbend",
        "debater.private",
        "q=",
        "cursor",
    ]
    for line in logged:
        for word in forbidden:
            assert word.lower() not in line.lower(), (word, line)
