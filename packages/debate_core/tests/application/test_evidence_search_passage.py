"""Passage search, stems and prefixes over a synthetic index, in format 2 and in format 1 (`v1-e39-t13`).

* **ac1:** a passage finds the card sharing most of its content words in another order, and ranks it
  above cards sharing fewer; a card sharing fewer than the minimum is not found, and the count counts
  what the pages walk.
* **ac2:** a stemmed word and a prefix match.
* **ac4, the service's half:** on a format 1 index a plain search runs and says its words are matched
  as written, and a passage search says it is not available until the next weekly update. The
  holder's half is in `test_search_index_holder_formats.py`, the reader's in
  `tests/integrations/local/test_search_index_reader_sqlite_features.py`.

Each index is a real SQLite FTS5 file written by the running writer under `tmp_path` and read by the
real reader. Every expected value is written by hand from the documents below (working agreement 6).
The words are invented or common English; no card text, school or person is real (data-use policy,
rule 5).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any, Final

import pytest

from debate_core.application.evidence_search import EvidenceSearchService
from debate_core.application.ports.search_index import IndexedOccurrence, SearchDocument
from debate_core.domain.evidence_search import (
    InvalidSearchCursor,
    ResultCount,
    SearchFilters,
    SearchNotice,
    SearchPage,
)
from debate_core.integrations.local.search_index import SqliteSearchIndexWriter
from debate_core.integrations.local.search_index_reader import SqliteSearchIndexReader
from debate_core.testing.search_index import format_one_index

INDEX_ID: Final = "0123456789abcdef"


def source(doc_id: int) -> str:
    return f"{doc_id:064x}"[::-1]


def document(
    doc_id: int, text: str, *, caselist: str = "hsld26", tag: str = "Invented claim"
) -> SearchDocument:
    return SearchDocument(
        doc_id=doc_id,
        caselist=caselist,
        cluster_id=f"{doc_id:064x}",
        event="LD",
        camp=None,
        tag=tag,
        cite="Lindqvist 26, Invented Quarterly",
        short_cite="Lindqvist 26",
        read_aloud="",
        text=text,
        completeness="FULL",
        formatting_spans=(),
        font_size_spans=(),
        sides=("NEG",),
        first_seen="2026-09-01",
        last_seen="2026-09-01",
        file_count=1,
        team_count=1,
        occurrences=(
            IndexedOccurrence(
                ordinal=0,
                caselist=caselist,
                source_sha256=source(doc_id),
                disclosure=f"{doc_id:064x}",
                first_element_index=0,
                last_element_index=2,
                snapshot="2026-09-01",
                last_snapshot="2026-09-08",
                completeness="FULL",
                attributed=True,
                provenance=True,
                side="NEG",
                school="Maple Grove",
                team_code="QX",
            ),
        ),
    )


def build(directory: Path, documents: Iterable[SearchDocument], *, format_one: bool = False) -> Path:
    path = directory / "search-index.sqlite"
    sink = SqliteSearchIndexWriter().create(path)
    for one in documents:
        sink.add(one)
    sink.finish()
    if format_one:
        path.write_bytes(format_one_index(path.read_bytes()))
    return path


def service(path: Path, **options: Any) -> EvidenceSearchService:
    return EvidenceSearchService(SqliteSearchIndexReader(path, index_id=INDEX_ID), **options)


def ids(page: SearchPage) -> list[int]:
    return [int(hit.cluster_id, 16) for hit in page.hits]


# ------------------------------------------------------------------------------------------------
# ac1: a passage, its minimum, its ranking and its count
# ------------------------------------------------------------------------------------------------

#: Seven content words, so a card must share five (66 percent of 7, rounded up). Each document shares
#: the number of them in its comment, in another order than the passage's.
PASSAGE: Final = "The zephyr and the granite, with basalt, quartz, obsidian, marble and slate."
SHARING: Final = (
    document(1, "slate marble obsidian quartz basalt granite zephyr"),  # all seven
    document(2, "obsidian zephyr marble basalt granite quartz"),  # six
    document(3, "quartz zephyr obsidian basalt granite"),  # five
    document(4, "basalt zephyr quartz granite"),  # four: under the minimum
    document(5, "zephyr"),  # one
    document(6, "pumice tuff"),  # none
    document(7, "granite quartz marble slate obsidian", caselist="hspf26"),  # five, in another caselist
)
#: Forty documents of seven other words each. With only the seven above, every passage word is in most
#: documents, and FTS5 floors such a word's IDF to almost nothing, so BM25 would rank by the two rarest
#: words alone. The dev store has fifty thousand documents.
FILLER: Final = tuple(
    document(100 + number, f"pumice tuff scoria pellet loam humus clay{number}") for number in range(40)
)


@pytest.fixture(scope="module")
def sharing(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build(tmp_path_factory.mktemp("sharing"), SHARING + FILLER)


def test_passage_finds_the_cards_sharing_most_of_its_words_best_first(sharing: Path) -> None:
    page = service(sharing).search(PASSAGE, passage=True)
    found = ids(page)
    assert found[0] == 1, "the card sharing all seven first"
    assert set(found) == {1, 2, 3, 7}, "and the cards sharing six and five, the minimum"
    assert found.index(2) < found.index(3), "six of the same words above five of them"
    assert page.count == ResultCount(4)
    assert page.notices == ()


def test_passage_leaves_out_a_card_sharing_fewer_than_the_minimum(sharing: Path) -> None:
    found = set(ids(service(sharing).search(PASSAGE, passage=True)))
    assert {4, 5, 6}.isdisjoint(found)


def test_passage_of_the_same_words_as_plain_words_finds_only_the_card_holding_all(sharing: Path) -> None:
    """The same sentence searched as words is an AND of them: the passage mode is what finds the rest."""
    page = service(sharing).search("zephyr granite basalt quartz obsidian marble slate")
    assert ids(page) == [1]


@pytest.mark.parametrize(
    ("share", "expected"),
    [(100, {1}), (80, {1, 2}), (66, {1, 2, 3, 7}), (50, {1, 2, 3, 4, 7}), (1, {1, 2, 3, 4, 5, 7})],
)
def test_passage_share_is_the_services_setting(sharing: Path, share: int, expected: set[int]) -> None:
    """Of 7 words: 100 percent is 7, 80 is 6, 66 is 5, 50 is 4, 1 is 1."""
    page = service(sharing, passage_share_percent=share).search(PASSAGE, passage=True)
    assert set(ids(page)) == expected
    assert page.count == ResultCount(len(expected))


def test_passage_service_refuses_a_share_outside_one_to_a_hundred(sharing: Path) -> None:
    with pytest.raises(ValueError, match="1 to 100"):
        service(sharing, passage_share_percent=0)


def test_passage_takes_the_filters(sharing: Path) -> None:
    page = service(sharing).search(PASSAGE, SearchFilters(caselist="hspf26"), passage=True)
    assert ids(page) == [7]
    assert page.count == ResultCount(1)


def test_passage_hides_and_counts_without_a_suppressed_card(sharing: Path) -> None:
    def is_suppressed(source_sha256: str, disclosure: str | None) -> bool:
        return source_sha256 == source(2)

    page = service(sharing).search(PASSAGE, passage=True, is_suppressed=is_suppressed)
    assert 2 not in ids(page)
    assert ids(page)[0] == 1
    assert page.count == ResultCount(3)


def test_passage_pages_and_its_cursor_is_refused_by_the_plain_search(sharing: Path) -> None:
    searched = service(sharing, page_size=2)
    first = searched.search(PASSAGE, passage=True)
    assert len(first.hits) == 2
    assert ids(first)[0] == 1
    assert first.next_cursor is not None
    second = searched.search(PASSAGE, cursor=first.next_cursor, passage=True)
    assert set(ids(first) + ids(second)) == {1, 2, 3, 7}
    assert second.next_cursor is None
    with pytest.raises(InvalidSearchCursor):
        searched.search(PASSAGE, cursor=first.next_cursor)
    with pytest.raises(InvalidSearchCursor):
        searched.check_cursor(PASSAGE, None, first.next_cursor)
    searched.check_cursor(PASSAGE, None, first.next_cursor, passage=True)


def test_passage_of_stop_words_alone_has_nothing_to_search(sharing: Path) -> None:
    page = service(sharing).search("It is what it is, and that is that.", passage=True)
    assert page.hits == ()
    assert page.count is None
    assert page.notices == (SearchNotice.NO_SEARCH_TERMS,)


# ------------------------------------------------------------------------------------------------
# ac2: stems and prefixes
# ------------------------------------------------------------------------------------------------

FORMS: Final = (
    document(11, "Invented tariffs escalated the conflict"),
    document(12, "An escalation follows every invented tariff"),
    document(13, "Escalatory rhetoric is common"),
    document(14, "Tariff revenue grows"),
    document(15, "Growing economies trade more"),
    document(16, "Obsidian is volcanic glass"),
)


@pytest.fixture(scope="module")
def forms(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build(tmp_path_factory.mktemp("forms"), FORMS)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("escalating", {11, 12}),
        ("escalation", {11, 12}),
        ("tariff", {11, 12, 14}),
        ("tariffs", {11, 12, 14}),
        ("grow", {14, 15}),
        ("growing economy", {15}),
        ('"invented tariff"', {11, 12}),
        ("escalate -tariff", set[int]()),
    ],
)
def test_stemmed_word_matches_its_other_forms(forms: Path, query: str, expected: set[int]) -> None:
    """Porter stems `escalated`, `escalating` and `escalation` alike, but not `escalatory`."""
    page = service(forms).search(query)
    assert set(ids(page)) == expected
    assert page.notices == ()


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("escal*", {11, 12, 13}),
        ("obsid*", {16}),
        ("tarif*", {11, 12, 14}),
        ("tag:escal*", set[int]()),
        ("econom* -grow*", set[int]()),
        ("trad* econom*", {15}),
    ],
)
def test_prefix_matches_every_word_it_starts(forms: Path, query: str, expected: set[int]) -> None:
    page = service(forms).search(query)
    assert set(ids(page)) == expected
    assert page.count == ResultCount(len(expected))


@pytest.mark.parametrize("query", ["es*", "tariff gr*", "-ob* tariff"])
def test_prefix_under_three_characters_is_refused_and_says_so(forms: Path, query: str) -> None:
    page = service(forms).search(query)
    assert page.hits == ()
    assert page.next_cursor is None
    assert page.count is None
    assert page.notices == (SearchNotice.PREFIX_TOO_SHORT,)


# ------------------------------------------------------------------------------------------------
# ac4: a format 1 index
# ------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def format_one(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build(tmp_path_factory.mktemp("format-one"), FORMS + SHARING, format_one=True)


def test_format_one_reader_says_its_format(format_one: Path, forms: Path) -> None:
    assert SqliteSearchIndexReader(format_one, index_id=INDEX_ID).format_version == 1
    assert SqliteSearchIndexReader(forms, index_id=INDEX_ID).format_version == 3


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("tariffs", {11}),
        ("tariff", {12, 14}),
        ("escalating", set[int]()),
        ("escal*", {11, 12, 13}),
        ('"invented tariff"', {12}),
    ],
)
def test_format_one_plain_search_matches_words_as_written_and_says_so(
    format_one: Path, query: str, expected: set[int]
) -> None:
    page = service(format_one).search(query)
    assert set(ids(page)) == expected
    assert page.notices == (SearchNotice.WORD_FORMS_UNAVAILABLE,)
    assert page.count == ResultCount(len(expected))


def test_format_one_passage_search_is_not_run_and_says_so(format_one: Path) -> None:
    page = service(format_one).search(PASSAGE, passage=True)
    assert page.hits == ()
    assert page.next_cursor is None
    assert page.count is None
    assert page.notices == (SearchNotice.PASSAGE_UNAVAILABLE,)


def test_format_one_short_prefix_says_both(format_one: Path) -> None:
    page = service(format_one).search("es*")
    assert page.hits == ()
    assert page.notices == (SearchNotice.WORD_FORMS_UNAVAILABLE, SearchNotice.PREFIX_TOO_SHORT)
