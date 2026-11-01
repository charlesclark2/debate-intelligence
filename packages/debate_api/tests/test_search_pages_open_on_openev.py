"""Open on OpenEv: a camp card's page links to its file, from the index's stored OpenEv id (`v1-e39-t16`).

Through the real app, over `conftest.search_corpus`, whose one camp card (card 3) has no OpenEv id.
Each test that needs one publishes the same corpus again with that card's occurrence holding the
invented id 4021, as the weekly update would, and lets the holder swap to it. Every expected value is
written by hand (working agreement 6); every id, camp and title is invented (data-use policy, rule 5).
"""

from __future__ import annotations

import re
import tempfile
from collections.abc import Sequence
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any, Final

import pytest

from debate_core.application.ports.search_index import SearchDocument
from debate_core.integrations.local.search_index import SqliteSearchIndexWriter
from debate_core.testing.search_index import format_two_index, published_index

OPENEV_ID: Final = 4021
OPENEV_URL: Final = "https://opencaselist.com/openev/4021"
CAMP_CARD: Final = 3


@pytest.fixture
def world(search_world: Any) -> Any:
    """This file's world: sign-in and the search pages (`v1-e39-t20`)."""
    return search_world


@pytest.fixture
def student(world: Any) -> Any:
    world.signed_in_student()
    return world


def source_links(page: str) -> list[str]:
    return re.findall(r'<p class="source-link">(.*?)</p>', page)


def with_openev_id(corpus: Sequence[SearchDocument], openev_id: int) -> tuple[SearchDocument, ...]:
    """The corpus, its camp card's occurrence holding `openev_id`, as a format 3 build writes it."""
    return tuple(
        replace(one, occurrences=tuple(replace(o, openev_id=openev_id) for o in one.occurrences))
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


def test_a_camp_card_links_to_its_file_on_openev_in_a_new_tab_with_no_referrer(student: Any) -> None:
    publish(student, with_openev_id(student.corpus, OPENEV_ID))

    page = student.browser.get(student.card_path("camp")).text

    assert source_links(page) == [
        f'<a href="{OPENEV_URL}" target="_blank" rel="noopener noreferrer">Open on OpenEv'
        '<span class="new-tab"> (opens in a new tab)</span></a>'
    ]
    head = page.split("<!--card-body-->")[0]
    line = "[OpenEv: Cascade Institute 2026 — Policy, Invented Adv CP]"
    assert head.index(f'<p class="provenance">{line}</p>') < head.index('<p class="source-link">')


def test_the_link_is_the_stored_ids_whatever_the_title_says(student: Any) -> None:
    """Another id, the same camp and title: another address. The title is never read for one."""
    publish(student, with_openev_id(student.corpus, 777))

    page = student.browser.get(student.card_path("camp")).text

    assert [re.findall(r'href="([^"]+)"', one) for one in source_links(page)] == [
        ["https://opencaselist.com/openev/777"]
    ]
    assert OPENEV_URL not in page


def test_a_camp_card_whose_index_row_has_no_openev_id_shows_no_link(student: Any) -> None:
    """The corpus as published: its camp card has a camp, year, event and title, and no OpenEv id."""
    page = student.browser.get(student.card_path("camp")).text

    assert source_links(page) == []
    assert "Open on" not in page
    assert "opencaselist.com/openev" not in page


def test_on_a_format_two_index_no_camp_card_links(student: Any) -> None:
    """Before the first format 3 index is published, the function serves format 2, which has no ids."""
    publish(student, with_openev_id(student.corpus, OPENEV_ID), format_two=True)

    page = student.browser.get(student.card_path("camp")).text

    assert source_links(page) == []
    assert "Open on" not in page


def test_a_disclosed_card_still_links_to_its_teams_page_and_never_to_openev(student: Any) -> None:
    publish(student, with_openev_id(student.corpus, OPENEV_ID))

    page = student.browser.get(student.card_path("linked")).text

    assert source_links(page) == [
        '<a href="https://opencaselist.com/hsld26/Cedarbrook/LM" target="_blank" rel="noopener noreferrer">'
        'Open on openCaselist<span class="new-tab"> (opens in a new tab)</span></a>'
    ]
    assert "Open on OpenEv" not in page and "opencaselist.com/openev" not in page


def test_the_results_page_links_to_no_openev_file(student: Any) -> None:
    """The link is the card page's; a result names its card and leaves the platform nowhere."""
    publish(student, with_openev_id(student.corpus, OPENEV_ID))

    page = student.browser.get("/search?q=zephyr&event=POLICY").text

    assert "Cascade Institute" in page
    assert "opencaselist.com/openev" not in page and "Open on OpenEv" not in page


def test_the_link_out_writes_nothing_and_its_id_is_in_no_record(student: Any) -> None:
    publish(student, with_openev_id(student.corpus, OPENEV_ID))
    before = len(student.audit.records)

    page = student.browser.get(student.card_path("camp")).text

    assert OPENEV_URL in page
    assert [one.action.value for one in student.audit.records[before:]] == ["card-viewed"]
    assert str(OPENEV_ID) not in student.audit.records[-1].to_json()
