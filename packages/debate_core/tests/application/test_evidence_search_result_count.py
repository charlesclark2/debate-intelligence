"""The result count a search page shows: exact up to a cap, "more than" past it (`v1-e39-t11`).

Each index is a real SQLite FTS5 file written by `v1-e39-t02`'s writer under `tmp_path` and read by
the real reader. Every expected count is written by hand from the documents below (working agreement
6): forty-five documents hold `quokka`, the odd-numbered ones disclosed Aff, and documents 41 to 45
are camp cards. The count must be the number of results a student can page through, for the same
query, filters and suppression list, so several tests page through every result and compare.

Every school, team code and card here is invented (data-use policy, rule 5).
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Iterable
from datetime import date
from pathlib import Path
from typing import Any, Final

import pytest

from debate_core.application.evidence_search import EvidenceSearchService, SuppressionPredicate
from debate_core.application.ports.search_index import IndexedOccurrence, SearchDocument
from debate_core.application.ports.search_index_reader import (
    CountBatch,
    CountRequest,
    MatchBatch,
    MatchRequest,
    StoredDocument,
    StoredOccurrence,
)
from debate_core.domain.caselist import Event, Side
from debate_core.domain.evidence_search import (
    DEFAULT_RESULT_COUNT_CAP,
    MAX_CURSOR_OFFSET,
    ResultCount,
    SearchFilters,
    SearchPage,
)
from debate_core.integrations.local.search_index import SqliteSearchIndexWriter
from debate_core.integrations.local.search_index_reader import SqliteSearchIndexReader

INDEX_ID: Final = "0123456789abcdef"
DOCUMENTS: Final = 45
CAMP_DOCUMENTS: Final = range(41, 46)


def source(number: int) -> str:
    return f"{number:064x}"[::-1]


def document(number: int) -> SearchDocument:
    camp = number in CAMP_DOCUMENTS
    caselist = "openev" if camp else ("hsld26" if number <= 30 else "hspf26")
    side = None if camp else ("AFF" if number % 2 else "NEG") if caselist == "hsld26" else "PRO"
    return SearchDocument(
        doc_id=number,
        caselist=caselist,
        cluster_id=f"{number:064x}",
        event="POLICY" if camp else ("LD" if caselist == "hsld26" else "PF"),
        camp="Cascade Institute" if camp else None,
        tag=f"Invented quokka claim {number}",
        cite="Lindqvist 26, Invented Quarterly",
        short_cite="Lindqvist 26",
        read_aloud="",
        text="quokka " * (1 + number % 7) + f"filler{number}",
        completeness="FULL",
        formatting_spans=(),
        font_size_spans=(),
        sides=(side,) if side else (),
        first_seen=None if camp else f"2026-09-{1 + number % 28:02d}",
        last_seen=None if camp else f"2026-09-{1 + number % 28:02d}",
        file_count=1,
        team_count=0 if camp else 1,
        occurrences=(
            IndexedOccurrence(
                ordinal=0,
                caselist=caselist,
                source_sha256=source(number),
                disclosure=None if camp else f"{number:064x}",
                first_element_index=0,
                last_element_index=2,
                snapshot="2026-policy" if camp else "2026-09-01",
                last_snapshot="2026-policy" if camp else "2026-09-08",
                completeness="FULL",
                attributed=True,
                provenance=True,
                side=side,
                school=None if camp else "Maple Grove",
                team_code=None if camp else "QX",
            ),
        ),
    )


def build(directory: Path, documents: Iterable[SearchDocument]) -> Path:
    path = directory / "search-index.sqlite"
    sink = SqliteSearchIndexWriter().create(path)
    for one in documents:
        sink.add(one)
    sink.finish()
    return path


@pytest.fixture(scope="module")
def index_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build(tmp_path_factory.mktemp("counted"), (document(number) for number in range(1, DOCUMENTS + 1)))


def service(path: Path, **options: Any) -> EvidenceSearchService:
    return EvidenceSearchService(SqliteSearchIndexReader(path, index_id=INDEX_ID), **options)


def stopping(*numbers: int) -> SuppressionPredicate:
    stopped = {source(number) for number in numbers}
    return lambda sha256, _disclosure: sha256 in stopped


def every_page(
    searched: EvidenceSearchService,
    query: str,
    filters: SearchFilters | None = None,
    is_suppressed: SuppressionPredicate | None = None,
) -> list[SearchPage]:
    pages = [searched.search(query, filters, is_suppressed=is_suppressed)]
    while pages[-1].next_cursor is not None:
        pages.append(searched.search(query, filters, pages[-1].next_cursor, is_suppressed=is_suppressed))
    return pages


# ------------------------------------------------------------------------------------------------
# Exact up to the cap
# ------------------------------------------------------------------------------------------------


def test_the_default_cap_is_one_thousand() -> None:
    assert DEFAULT_RESULT_COUNT_CAP == 1000


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        (SearchFilters(), 45),
        (SearchFilters(event=Event.LD), 30),
        (SearchFilters(event=Event.PF), 10),
        (SearchFilters(caselist="openev"), 5),
        (SearchFilters(camp="Cascade Institute"), 5),
        (SearchFilters(side=Side.AFF), 15),
        (SearchFilters(side=Side.NEG), 15),
        (SearchFilters(side=Side.PRO), 10),
        (SearchFilters(event=Event.PF, side=Side.AFF), 0),
        (SearchFilters(first_seen_on_or_after=date(2026, 9, 25)), 4),
    ],
)
def test_every_page_carries_the_exact_count_for_its_filters(
    index_path: Path, filters: SearchFilters, expected: int
) -> None:
    """Documents 1 to 30 are LD (odd Aff, even Neg), 31 to 40 PF Pro, 41 to 45 camp cards with no first
    seen. A caselist card is first seen on day `1 + number % 28`, the 25th or later for 24 to 27: four."""
    pages = every_page(service(index_path), "quokka", filters)

    assert {page.count for page in pages} == {ResultCount(expected)}
    assert sum(len(page.hits) for page in pages) == expected


def test_the_count_is_for_the_parsed_query_not_its_spelling(index_path: Path) -> None:
    searched = service(index_path)

    assert searched.search("  QUOKKA ").count == ResultCount(45)
    assert searched.search("quokka -filler7").count == ResultCount(44)
    assert searched.search('"quokka filler12"').count == ResultCount(1)
    assert searched.search("filler12 filler13").count == ResultCount(0)


def test_a_query_with_nothing_to_search_for_has_no_count(index_path: Path) -> None:
    for query in ("-quokka", "", "*** ^"):
        assert service(index_path).search(query).count is None


# ------------------------------------------------------------------------------------------------
# Past the cap
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cap", "expected"),
    [
        (1, ResultCount(1, capped=True)),
        (20, ResultCount(20, capped=True)),
        (44, ResultCount(44, capped=True)),
        (45, ResultCount(45)),
        (46, ResultCount(45)),
    ],
)
def test_the_count_is_exact_up_to_the_cap_and_marked_more_past_it(
    index_path: Path, cap: int, expected: ResultCount
) -> None:
    assert service(index_path, count_cap=cap).search("quokka").count == expected


@pytest.mark.parametrize("cap", [0, -1, MAX_CURSOR_OFFSET + 1])
def test_a_cap_outside_one_to_the_cursor_limit_is_refused(index_path: Path, cap: int) -> None:
    with pytest.raises(ValueError, match="counts up to"):
        service(index_path, count_cap=cap)


# ------------------------------------------------------------------------------------------------
# The suppression list: the count is of what a student can page through
# ------------------------------------------------------------------------------------------------


def test_a_suppressed_representative_is_not_counted_as_it_is_not_shown(index_path: Path) -> None:
    """Every third document suppressed: 45 less 15 is 30, a page of twenty then ten."""
    hidden = [number for number in range(1, DOCUMENTS + 1) if number % 3 == 0]

    pages = every_page(service(index_path), "quokka", is_suppressed=stopping(*hidden))

    assert [len(page.hits) for page in pages] == [20, 10]
    assert {page.count for page in pages} == {ResultCount(30)}


def test_the_count_reads_on_past_suppressed_rows_to_reach_the_cap(index_path: Path) -> None:
    """Documents 1 to 5 suppressed leave forty. The first batch of a cap of ten reads documents 1 to 11 and
    keeps six, so a second batch is needed to find the eleventh survivor."""
    predicate = stopping(1, 2, 3, 4, 5)

    def counted(cap: int) -> ResultCount | None:
        return service(index_path, count_cap=cap).search("quokka", is_suppressed=predicate).count

    assert counted(10) == ResultCount(10, capped=True)
    assert counted(39) == ResultCount(39, capped=True)
    assert counted(40) == ResultCount(40)
    assert counted(DEFAULT_RESULT_COUNT_CAP) == ResultCount(40)


@pytest.mark.parametrize(
    ("query", "filters", "hidden"),
    [
        ("quokka", SearchFilters(), (2, 9, 41)),
        ("quokka", SearchFilters(side=Side.AFF), (1, 3, 5, 7)),
        ("quokka", SearchFilters(caselist="openev"), (41, 42, 43, 44, 45)),
        ("quokka -filler3", SearchFilters(event=Event.LD), ()),
        ("filler33 OR", SearchFilters(), ()),
    ],
)
def test_the_count_equals_the_results_a_student_can_page_through(
    index_path: Path, query: str, filters: SearchFilters, hidden: tuple[int, ...]
) -> None:
    searched = service(index_path, page_size=7)

    pages = every_page(searched, query, filters, stopping(*hidden))

    shown = sum(len(page.hits) for page in pages)
    assert {page.count for page in pages} == {ResultCount(shown)}


# ------------------------------------------------------------------------------------------------
# The time budget
# ------------------------------------------------------------------------------------------------


def spent_after(reads: int) -> Callable[[], float]:
    """A clock at 0 for `reads` reads after the one that sets the deadline, and a minute on after that."""
    counter = itertools.count()
    return lambda: 0.0 if next(counter) <= reads else 60.0


def test_a_count_the_budget_stops_is_no_count_never_a_wrong_one(index_path: Path) -> None:
    """Whenever the budget runs out, the page has the exact count or none: never a part-count."""
    seen: set[ResultCount | None] = set()
    for reads in range(60):
        page = service(index_path, time_budget_seconds=1.0, clock=spent_after(reads)).search("quokka")
        if page.partial:
            assert page.count is None
        seen.add(page.count)
    assert seen <= {None, ResultCount(45)}
    assert seen == {None, ResultCount(45)}, "some budgets stop the count and some let it finish"


class CountStoppedByTheBudget:
    """A reader whose ranking finishes and whose count is stopped by the budget after one row."""

    index_id = INDEX_ID

    def __init__(self, path: Path) -> None:
        self.real = SqliteSearchIndexReader(path, index_id=INDEX_ID)

    def match(self, request: MatchRequest) -> MatchBatch:
        return self.real.match(request)

    def count(self, request: CountRequest) -> CountBatch:
        whole = self.real.count(request)
        return CountBatch(rows=whole.rows[:1], exhausted=False, interrupted=True)

    def document(self, caselist: str, cluster_id: str) -> StoredDocument | None:
        return self.real.document(caselist, cluster_id)

    def occurrences(self, doc_id: int) -> tuple[StoredOccurrence, ...]:
        return self.real.occurrences(doc_id)


def test_a_count_stopped_part_way_is_left_out_while_the_page_is_whole(index_path: Path) -> None:
    page = EvidenceSearchService(CountStoppedByTheBudget(index_path)).search("quokka")

    assert len(page.hits) == 20 and not page.partial
    assert page.count is None


# ------------------------------------------------------------------------------------------------
# The reader's batches
# ------------------------------------------------------------------------------------------------


def count_request(**changes: Any) -> CountRequest:
    fields: dict[str, Any] = {
        "expression": '"quokka"',
        "filters": SearchFilters(),
        "after": 0,
        "limit": 100,
        "expired": lambda: False,
    }
    return CountRequest(**(fields | changes))


def test_the_reader_counts_in_doc_id_order_after_a_doc_id_up_to_a_limit(index_path: Path) -> None:
    with SqliteSearchIndexReader(index_path, index_id=INDEX_ID) as reader:
        first = reader.count(count_request(limit=10))
        rest = reader.count(count_request(after=10))
        camp = reader.count(count_request(filters=SearchFilters(caselist="openev"), after=42))

    assert [row.doc_id for row in first.rows] == list(range(1, 11))
    assert not first.exhausted and not first.interrupted
    assert [row.doc_id for row in rest.rows] == list(range(11, 46))
    assert rest.exhausted
    assert [(row.doc_id, row.source_sha256, row.disclosure) for row in camp.rows] == [
        (43, source(43), None),
        (44, source(44), None),
        (45, source(45), None),
    ]
    assert first.rows[0].disclosure == f"{1:064x}"


def test_the_reader_count_stopped_by_the_budget_is_interrupted_and_not_exhausted(tmp_path: Path) -> None:
    """Over 400 documents: forty-five rows are read inside one progress-handler interval."""
    path = build(tmp_path, (document(number) for number in range(1, 401)))
    with SqliteSearchIndexReader(path, index_id=INDEX_ID) as reader:
        stopped = reader.count(count_request(expired=lambda: True, limit=1000))
        whole = reader.count(count_request(limit=1000))

    assert stopped.interrupted and not stopped.exhausted
    assert len(stopped.rows) < len(whole.rows) == 400
    assert whole.exhausted and not whole.interrupted
