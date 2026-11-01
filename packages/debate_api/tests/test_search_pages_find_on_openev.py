"""Find on OpenEv: a camp card's page links to its camp's page on OpenEv (`v1-e39-t28`).

The address is `https://opencaselist.com/openev/<year>/<word>`: the card's stored camp through the
alias table's OpenEv word, and its year. Until `v1-e39-t28` the link was built from a stored OpenEv id
(`v1-e39-t16`), at an address the operator found was OpenEv's page for a year.

Through the real app, over `conftest.search_corpus`, whose one camp card (card 3) is from the invented
`Cascade Institute`, 2026. This file's world gives that camp the invented word `CASCADE`, as
`camp_aliases.yaml`'s `openev` section would. Every expected value is written by hand (working
agreement 6); every camp, word, id and title is invented (data-use policy, rule 5).
"""

from __future__ import annotations

import re
import tempfile
from collections.abc import Callable, Iterator, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

import pytest

from debate_core.application.ports.search_index import SearchDocument
from debate_core.integrations.local.search_index import SqliteSearchIndexWriter
from debate_core.testing.search_index import format_two_index, published_index

WORDS: Final = {"Cascade Institute": "CASCADE"}
CAMP_URL: Final = "https://opencaselist.com/openev/2026/CASCADE"
CAMP_LINK: Final = (
    f'<a href="{CAMP_URL}" target="_blank" rel="noopener noreferrer">'
    'Find on OpenEv: Cascade Institute 2026 camp page<span class="new-tab"> (opens in a new tab)</span></a>'
)
CAMP_CARD: Final = 3


@pytest.fixture
def world(make_search_world: Callable[..., Any]) -> Iterator[Any]:
    """The search world, its table giving the corpus's camp an OpenEv word."""
    made = make_search_world(openev_camp_words=WORDS)
    yield made
    made.services.search_index.close()


@pytest.fixture
def student(world: Any) -> Any:
    world.signed_in_student()
    return world


def source_links(page: str) -> list[str]:
    return re.findall(r'<p class="source-link">(.*?)</p>', page)


def with_camp_changes(corpus: Sequence[SearchDocument], **changes: Any) -> tuple[SearchDocument, ...]:
    """The corpus, its camp card's occurrences changed as the build could have written them."""
    return tuple(
        replace(one, occurrences=tuple(replace(o, **changes) for o in one.occurrences))
        if one.doc_id == CAMP_CARD
        else one
        for one in corpus
    )


def publish(world: Any, corpus: Sequence[SearchDocument], *, format_two: bool = False) -> None:
    """`corpus` as the next weekly index, written by this build's writer, and the holder swapped to it."""
    with tempfile.TemporaryDirectory() as scratch:
        path = Path(scratch) / "search-index.sqlite"
        sink = SqliteSearchIndexWriter().create(path)
        for document in corpus:
            sink.add(document)
        sink.finish()
        sqlite = path.read_bytes()
    stores: dict[str, int] = {}
    for document in corpus:
        stores[document.caselist] = stores.get(document.caselist, 0) + 1
    index = (
        published_index(format_two_index(sqlite), documents_by_store=stores, format_version=2)
        if format_two
        else published_index(sqlite, documents_by_store=stores)
    )
    world.index_source.publish(index)
    world.clock.advance(timedelta(minutes=5))
    world.browser.get("/search?q=zephyr")
    assert world.services.search_index.loaded_index_id == index.index_id


def test_a_camp_card_links_to_its_camps_page_in_a_new_tab_with_no_referrer(student: Any) -> None:
    page = student.browser.get(student.card_path("camp")).text

    assert source_links(page) == [CAMP_LINK]
    head = page.split("<!--card-body-->")[0]
    line = "[OpenEv: Cascade Institute 2026 — Policy, Invented Adv CP]"
    assert head.index(f'<p class="provenance">{line}</p>') < head.index('<p class="source-link">')


def test_the_link_is_the_camps_word_and_year_whatever_the_title_or_stored_id_say(student: Any) -> None:
    """A stored OpenEv id and another title: the same address. Neither is ever read for one."""
    publish(student, with_camp_changes(student.corpus, openev_id=4021, camp_file_title="CASC2 Adv CP"))

    page = student.browser.get(student.card_path("camp")).text

    assert source_links(page) == [CAMP_LINK]
    assert "openev/4021" not in page and "CASC2" not in "".join(source_links(page))


def test_a_camp_card_whose_camp_has_no_word_in_the_table_shows_no_link(make_search_world: Any) -> None:
    """The table has a word for another camp only: the stored camp is never the address itself."""
    world = make_search_world(openev_camp_words={"Ridgeline": "RDI7"})
    try:
        world.signed_in_student()
        page = world.browser.get(world.card_path("camp")).text
    finally:
        world.services.search_index.close()

    assert source_links(page) == []
    assert "opencaselist.com/openev" not in page and "Find on OpenEv" not in page


def test_a_camp_card_from_unknown_shows_no_link_whatever_the_table_says(make_search_world: Any) -> None:
    world = make_search_world(openev_camp_words={"UNKNOWN": "CASCADE"})
    try:
        world.signed_in_student()
        publish(world, with_camp_changes(world.corpus, camp="UNKNOWN"))
        page = world.browser.get(world.card_path("camp")).text
    finally:
        world.services.search_index.close()

    assert source_links(page) == []
    assert "opencaselist.com/openev" not in page


def test_the_years_upper_bound_is_the_apps_own_clocks_season_plus_one(student: Any) -> None:
    """2028 is past the season of 2 November 2026 plus one, and inside it from 1 August 2027."""
    publish(student, with_camp_changes(student.corpus, camp_year=2028))
    before = student.browser.get(student.card_path("camp")).text

    student.clock.now = datetime(2027, 8, 1, 15, 0, tzinfo=UTC)
    student.signed_in_student()
    after = student.browser.get(student.card_path("camp")).text

    assert source_links(before) == []
    assert [re.findall(r'href="([^"]+)"', one) for one in source_links(after)] == [
        ["https://opencaselist.com/openev/2028/CASCADE"]
    ]


def test_on_a_format_two_index_the_camp_card_links_too(student: Any) -> None:
    """Changed in `v1-e39-t28`: camp and year are in every format, so format 2 needs no OpenEv id."""
    publish(student, student.corpus, format_two=True)

    page = student.browser.get(student.card_path("camp")).text

    assert source_links(page) == [CAMP_LINK]


def test_a_disclosed_card_still_links_to_its_teams_page_and_never_to_openev(student: Any) -> None:
    page = student.browser.get(student.card_path("linked")).text

    assert source_links(page) == [
        '<a href="https://opencaselist.com/hsld26/Cedarbrook/LM" target="_blank" rel="noopener noreferrer">'
        'Open on openCaselist<span class="new-tab"> (opens in a new tab)</span></a>'
    ]
    assert "Find on OpenEv" not in page and "opencaselist.com/openev" not in page


def test_the_results_page_links_to_no_camp_page(student: Any) -> None:
    """The link is the card page's; a result names its card and leaves the platform nowhere."""
    page = student.browser.get("/search?q=zephyr&event=POLICY").text

    assert "Cascade Institute" in page
    assert "opencaselist.com/openev" not in page and "Find on OpenEv" not in page


def test_the_link_out_writes_nothing_and_its_address_is_in_no_record(student: Any) -> None:
    before = len(student.audit.records)

    page = student.browser.get(student.card_path("camp")).text

    assert CAMP_URL in page
    assert [one.action.value for one in student.audit.records[before:]] == ["card-viewed"]
    assert "CASCADE" not in student.audit.records[-1].to_json()
