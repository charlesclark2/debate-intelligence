"""A card page's "Back to results" asks whether its cursor is still the search's (`v1-e39-t11`).

:meth:`EvidenceSearchService.check_cursor` refuses exactly what :meth:`EvidenceSearchService.search`
refuses: a cursor from another query, other filters or another index, or one that was changed. Each
case is checked against both, so the back link can never accept a page the search would refuse.

The index is a real SQLite FTS5 file of invented documents (data-use policy, rule 5).
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest

from debate_core.application.evidence_search import EvidenceSearchService
from debate_core.application.ports.search_index import IndexedOccurrence, SearchDocument
from debate_core.domain.caselist import Side
from debate_core.domain.evidence_search import InvalidSearchCursor, SearchFilters
from debate_core.integrations.local.search_index import SqliteSearchIndexWriter
from debate_core.integrations.local.search_index_reader import SqliteSearchIndexReader

INDEX_ID: Final = "0123456789abcdef"
OTHER_INDEX_ID: Final = "fedcba9876543210"


def document(number: int) -> SearchDocument:
    return SearchDocument(
        doc_id=number,
        caselist="hsld26",
        cluster_id=f"{number:064x}",
        event="LD",
        camp=None,
        tag=f"Invented wombat claim {number}",
        cite="Lindqvist 26, Invented Quarterly",
        short_cite="Lindqvist 26",
        read_aloud="",
        text=f"wombat filler{number}",
        completeness="FULL",
        formatting_spans=(),
        font_size_spans=(),
        sides=("AFF",) if number % 2 else ("NEG",),
        first_seen="2026-09-01",
        last_seen="2026-09-01",
        file_count=1,
        team_count=1,
        occurrences=(
            IndexedOccurrence(
                ordinal=0,
                caselist="hsld26",
                source_sha256=f"{number:064x}"[::-1],
                disclosure=f"{number:064x}",
                first_element_index=0,
                last_element_index=2,
                snapshot="2026-09-01",
                last_snapshot="2026-09-01",
                completeness="FULL",
                attributed=True,
                provenance=False,
            ),
        ),
    )


@pytest.fixture(scope="module")
def index_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("cursors") / "search-index.sqlite"
    sink = SqliteSearchIndexWriter().create(path)
    for number in range(1, 51):
        sink.add(document(number))
    sink.finish()
    return path


def service(path: Path, index_id: str = INDEX_ID) -> EvidenceSearchService:
    return EvidenceSearchService(SqliteSearchIndexReader(path, index_id=index_id))


@pytest.fixture(scope="module")
def cursor(index_path: Path) -> str:
    made = service(index_path).search("wombat", SearchFilters(side=Side.AFF)).next_cursor
    assert made is not None, "twenty-five Aff documents run to a second page"
    return made


def test_a_cursor_the_search_wrote_is_accepted_for_its_query_and_filters(
    index_path: Path, cursor: str
) -> None:
    searched = service(index_path)

    searched.check_cursor("wombat", SearchFilters(side=Side.AFF), cursor)
    searched.check_cursor("  WOMBAT ", SearchFilters(side=Side.AFF), cursor)
    assert len(searched.search("wombat", SearchFilters(side=Side.AFF), cursor).hits) == 5


def tampered(cursor: str) -> str:
    return cursor[:-2] + ("A" if cursor[-2] != "A" else "B") + cursor[-1]


@pytest.mark.parametrize(
    ("query", "filters", "changed", "index_id"),
    [
        ("filler1", SearchFilters(side=Side.AFF), False, INDEX_ID),
        ("wombat", SearchFilters(), False, INDEX_ID),
        ("wombat", SearchFilters(side=Side.NEG), False, INDEX_ID),
        ("wombat", None, False, INDEX_ID),
        ("wombat", SearchFilters(side=Side.AFF), True, INDEX_ID),
        ("wombat", SearchFilters(side=Side.AFF), False, OTHER_INDEX_ID),
    ],
    ids=["another query", "no filters", "other filters", "filters left out", "changed", "another index"],
)
def test_a_cursor_the_search_refuses_is_refused_by_the_check_too(
    index_path: Path,
    cursor: str,
    query: str,
    filters: SearchFilters | None,
    changed: bool,
    index_id: str,
) -> None:
    searched = service(index_path, index_id)
    given = tampered(cursor) if changed else cursor

    with pytest.raises(InvalidSearchCursor):
        searched.search(query, filters, given)
    with pytest.raises(InvalidSearchCursor):
        searched.check_cursor(query, filters, given)


@pytest.mark.parametrize(
    "given", ["", "not a cursor", "=" * 8, "A" * 65, "../../search", "https://example.test"]
)
def test_text_that_is_no_cursor_is_refused(index_path: Path, given: str) -> None:
    with pytest.raises(InvalidSearchCursor):
        service(index_path).check_cursor("wombat", SearchFilters(side=Side.AFF), given)
