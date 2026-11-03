"""Search and card lookup over a synthetic index: filters, pages, cursors, suppression, budget (`v1-e39-t03`).

Each index is a real SQLite FTS5 file written by `v1-e39-t02`'s writer under `tmp_path` and read by
the real reader; nothing is mocked but the clock. Every expected value is written by hand from the
documents below (working agreement 6): which documents each filter keeps, how many results each page
holds, which occurrences survive a suppression and what the counts become.

Every school, team code, tournament, round, camp, file title and card is invented (data-use policy,
rule 5): Maple Grove, Riverbend, `QX`, `ZT`, the Invented Invitational, Cascade Institute.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Iterable, Sequence
from datetime import date
from pathlib import Path
from typing import Any, Final

import pytest

from debate_core.application.evidence_search import (
    EvidenceSearchService,
    SuppressionPredicate,
    surviving_counts,
)
from debate_core.application.ports.search_index import IndexedOccurrence, SearchDocument
from debate_core.application.ports.search_index_reader import (
    CountBatch,
    CountRequest,
    MatchBatch,
    MatchRequest,
    StoredDocument,
    StoredHit,
    StoredOccurrence,
)
from debate_core.domain.caselist import Event, Side
from debate_core.domain.debate_files import FontSizeSpan, FormattingSpan
from debate_core.domain.evidence_search import (
    InvalidSearchCursor,
    SearchFilters,
    SearchNotice,
    SearchPage,
    card_runs,
)
from debate_core.domain.file_provenance import formatting_sha256
from debate_core.domain.search_card_html import render_card_html
from debate_core.domain.search_index import (
    SEARCH_INDEX_FORMAT_VERSION,
    IndexedFontSizeSpan,
    IndexedFormattingSpan,
    read_aloud_text,
)
from debate_core.domain.style_profile import RunEmphasis, StyleMatchSource
from debate_core.integrations.local.search_index import SqliteSearchIndexWriter
from debate_core.integrations.local.search_index_reader import SqliteSearchIndexReader

INDEX_ID: Final = "0123456789abcdef"
OTHER_INDEX_ID: Final = "fedcba9876543210"

SCHOOL, TEAM = "Maple Grove", "QX"
OTHER_SCHOOL, OTHER_TEAM = "Riverbend", "ZT"
TOURNAMENT, ROUND = "Invented Invitational", "Round 4"
CAMP, CAMP_TITLE = "Cascade Institute", "Invented Adv CP"


def cluster(doc_id: int) -> str:
    return f"{doc_id:064x}"


def source(number: int) -> str:
    return f"{number:064x}"[::-1]


def occurrence(
    ordinal: int,
    *,
    caselist: str = "hsld26",
    source_number: int = 1,
    disclosure: str | None = None,
    school: str | None = SCHOOL,
    team: str | None = TEAM,
    side: str | None = "NEG",
    provenance: bool = True,
    snapshot: str = "2026-09-01",
) -> IndexedOccurrence:
    camp = caselist == "openev"
    kept = provenance and not camp
    return IndexedOccurrence(
        ordinal=ordinal,
        caselist=caselist,
        source_sha256=source(source_number),
        disclosure=None if camp else (disclosure or f"{source_number:064x}"),
        first_element_index=0,
        last_element_index=2,
        snapshot="2026-policy" if camp else snapshot,
        last_snapshot="2026-policy" if camp else "2026-09-08",
        completeness="FULL",
        attributed=True,
        provenance=provenance,
        side=side if kept else None,
        school=school if kept else None,
        team_code=team if kept else None,
        tournament=TOURNAMENT if kept else None,
        round=ROUND if kept else None,
        camp=CAMP if camp and provenance else None,
        camp_year=2026 if camp and provenance else None,
        camp_event="POLICY" if camp and provenance else None,
        camp_file_title=CAMP_TITLE if camp and provenance else None,
    )


def parser_span(emphasis: RunEmphasis, start: int, end: int, colour: str | None = None) -> FormattingSpan:
    return FormattingSpan(
        emphasis=emphasis,
        start_offset=start,
        end_offset=end,
        highlight_color=colour,
        rule_id="synthetic",
        match_source=StyleMatchSource.VERBATIM,
    )


def document(
    doc_id: int,
    *,
    text: str = "",
    tag: str | None = "Invented claim",
    cite: str = "Lindqvist 26, Invented Quarterly",
    caselist: str = "hsld26",
    event: str = "LD",
    camp: str | None = None,
    sides: tuple[str, ...] = ("NEG",),
    first_seen: str | None = "2026-09-01",
    spans: Sequence[FormattingSpan] = (),
    sizes: Sequence[FontSizeSpan] = (),
    occurrences: Sequence[IndexedOccurrence] | None = None,
    file_count: int | None = None,
    team_count: int | None = None,
) -> SearchDocument:
    held = (
        tuple(occurrences)
        if occurrences is not None
        else (occurrence(0, caselist=caselist, source_number=doc_id),)
    )
    return SearchDocument(
        doc_id=doc_id,
        caselist=caselist,
        cluster_id=cluster(doc_id),
        event=event,
        camp=camp,
        tag=tag,
        cite=cite,
        short_cite=cite.split(",")[0],
        read_aloud=read_aloud_text(text, spans),
        text=text,
        completeness="FULL",
        formatting_spans=tuple(spans),
        font_size_spans=tuple(sizes),
        sides=sides,
        first_seen=None if caselist == "openev" else first_seen,
        last_seen=None if caselist == "openev" else first_seen,
        file_count=file_count if file_count is not None else len({one.source_sha256 for one in held}),
        team_count=team_count if team_count is not None else 1,
        occurrences=held,
    )


def build(directory: Path, documents: Iterable[SearchDocument]) -> Path:
    path = directory / "search-index.sqlite"
    sink = SqliteSearchIndexWriter().create(path)
    for one in documents:
        sink.add(one)
    sink.finish()
    return path


def service(path: Path, *, index_id: str = INDEX_ID, **options: Any) -> EvidenceSearchService:
    return EvidenceSearchService(SqliteSearchIndexReader(path, index_id=index_id), **options)


def ids(page: SearchPage) -> list[int]:
    return [int(hit.cluster_id, 16) for hit in page.hits]


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
# Filters: eight documents, each holding the word "zephyr"
# ------------------------------------------------------------------------------------------------

FILTERED: Final = (
    document(1, text="zephyr one", caselist="hsld26", event="LD", sides=("AFF",), first_seen="2026-09-01"),
    document(2, text="zephyr two", caselist="hsld26", event="LD", sides=("NEG",), first_seen="2026-09-20"),
    document(
        3, text="zephyr three", caselist="hsld26", event="LD", sides=("AFF", "NEG"), first_seen="2026-10-05"
    ),
    document(4, text="zephyr four", caselist="hspf26", event="PF", sides=("PRO",), first_seen="2026-09-10"),
    document(5, text="zephyr five", caselist="hspf26", event="PF", sides=("CON",), first_seen="2026-10-01"),
    document(
        6, text="zephyr six", caselist="hspolicy26", event="POLICY", sides=("AFF",), first_seen="2026-09-15"
    ),
    document(7, text="zephyr seven", caselist="openev", event="POLICY", camp=CAMP, sides=()),
    document(8, text="zephyr eight", caselist="openev", event="LD", camp="Summit Workshop", sides=()),
)


@pytest.fixture(scope="module")
def filtered(tmp_path_factory: pytest.TempPathFactory) -> EvidenceSearchService:
    return service(build(tmp_path_factory.mktemp("filtered"), FILTERED))


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        (SearchFilters(), {1, 2, 3, 4, 5, 6, 7, 8}),
        (SearchFilters(event=Event.LD), {1, 2, 3, 8}),
        (SearchFilters(event=Event.POLICY), {6, 7}),
        (SearchFilters(event=Event.PF), {4, 5}),
        (SearchFilters(caselist="hsld26"), {1, 2, 3}),
        (SearchFilters(caselist="openev"), {7, 8}),
        (SearchFilters(camp=CAMP), {7}),
        (SearchFilters(caselist="openev", camp="Summit Workshop"), {8}),
        (SearchFilters(side=Side.AFF), {1, 3, 6}),
        (SearchFilters(side=Side.NEG), {2, 3}),
        (SearchFilters(side=Side.PRO), {4}),
        (SearchFilters(side=Side.CON), {5}),
        (SearchFilters(first_seen_on_or_after=date(2026, 9, 20)), {2, 3, 5}),
        (SearchFilters(first_seen_on_or_after=date(2026, 9, 20), side=Side.AFF), {3}),
        (SearchFilters(event=Event.LD, caselist="openev"), {8}),
        (SearchFilters(event=Event.PF, side=Side.AFF), set[int]()),
        (SearchFilters(caselist="hsld99"), set[int]()),
    ],
)
def test_evidence_search_filters_keep_the_documents_written_by_hand(
    filtered: EvidenceSearchService, filters: SearchFilters, expected: set[int]
) -> None:
    """ac2: each filter, and some together, over the eight documents above."""
    page = filtered.search("zephyr", filters)
    assert set(ids(page)) == expected
    assert len(ids(page)) == len(expected)
    assert page.next_cursor is None


def test_evidence_search_first_seen_leaves_camp_cards_out_and_says_so(
    filtered: EvidenceSearchService,
) -> None:
    """PM amendment 2026-10-20 (v1-e39-t02 follow-up 2): camp cards have no first seen."""
    page = filtered.search("zephyr", SearchFilters(first_seen_on_or_after=date(2026, 1, 1)))
    assert set(ids(page)) == {1, 2, 3, 4, 5, 6}
    assert page.notices == (SearchNotice.FIRST_SEEN_CASELIST_CARDS_ONLY,)
    assert filtered.search("zephyr").notices == ()
    assert filtered.search("zephyr", SearchFilters(caselist="openev")).notices == ()


@pytest.mark.parametrize("side", [Side.AFF, Side.NEG, Side.PRO, Side.CON])
def test_evidence_search_side_filter_leaves_camp_cards_out_and_says_so(
    filtered: EvidenceSearchService, side: Side
) -> None:
    """PM ruling 2026-10-20 (v1-e39-t03 Decision 5): camp cards have no side, as they have no first seen."""
    page = filtered.search("zephyr", SearchFilters(side=side))
    assert not {7, 8} & set(ids(page))
    assert page.notices == (SearchNotice.SIDE_CASELIST_CARDS_ONLY,)


def test_evidence_search_side_and_first_seen_filters_each_say_so(filtered: EvidenceSearchService) -> None:
    page = filtered.search("zephyr", SearchFilters(side=Side.AFF, first_seen_on_or_after=date(2026, 9, 20)))
    assert set(ids(page)) == {3}
    assert page.notices == (
        SearchNotice.FIRST_SEEN_CASELIST_CARDS_ONLY,
        SearchNotice.SIDE_CASELIST_CARDS_ONLY,
    )
    assert filtered.search("zephyr", SearchFilters(event=Event.LD, caselist="hsld26")).notices == ()


def test_evidence_search_with_nothing_to_search_for_returns_no_results_and_says_so(
    filtered: EvidenceSearchService,
) -> None:
    for query in ("-zephyr", "", "   ", "*** ^ ()"):
        page = filtered.search(query)
        assert page.hits == ()
        assert page.next_cursor is None
        assert page.notices == (SearchNotice.NO_SEARCH_TERMS,)


def test_evidence_search_hit_carries_what_a_results_page_shows(filtered: EvidenceSearchService) -> None:
    (hit,) = filtered.search("seven").hits
    assert (hit.caselist, hit.cluster_id, hit.event, hit.camp) == ("openev", cluster(7), "POLICY", CAMP)
    assert (hit.tag, hit.short_cite, hit.file_count, hit.team_count) == (
        "Invented claim",
        "Lindqvist 26",
        1,
        1,
    )
    assert [(segment.text, segment.marked) for segment in hit.snippet] == [
        ("zephyr ", False),
        ("seven", True),
    ]
    assert hit.provenance_line == f"[OpenEv: {CAMP} 2026 — Policy, {CAMP_TITLE}]"
    (disclosed,) = filtered.search("two").hits
    assert (
        disclosed.provenance_line
        == f"[Disclosed: hsld26 2026-09-01 — {SCHOOL} {TEAM}, Neg vs. {TOURNAMENT} {ROUND}]"
    )


# ------------------------------------------------------------------------------------------------
# Pages and cursors: forty-five documents holding "quokka", the odd ones disclosed Aff
# ------------------------------------------------------------------------------------------------

PAGED: Final = tuple(
    document(
        number,
        text="quokka " * (1 + number % 7) + f"filler{number}",
        sides=("AFF",) if number % 2 else ("NEG",),
    )
    for number in range(1, 46)
)


@pytest.fixture(scope="module")
def paged_index(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build(tmp_path_factory.mktemp("paged"), PAGED)


def test_evidence_search_pages_hold_twenty_then_twenty_then_five_in_ranking_order(paged_index: Path) -> None:
    """ac2: the pages, concatenated, are the whole ranking once, in order."""
    pages = every_page(service(paged_index), "quokka")
    assert [len(page.hits) for page in pages] == [20, 20, 5]
    assert pages[-1].next_cursor is None
    whole = ids(service(paged_index, page_size=100).search("quokka"))
    assert sorted(whole) == list(range(1, 46))
    assert [number for page in pages for number in ids(page)] == whole


def test_evidence_search_pages_under_a_filter(paged_index: Path) -> None:
    """ac2: twenty-three odd documents are Aff: a page of twenty, then three."""
    pages = every_page(service(paged_index), "quokka", SearchFilters(side=Side.AFF))
    assert [len(page.hits) for page in pages] == [20, 3]
    assert sorted(number for page in pages for number in ids(page)) == list(range(1, 46, 2))


def test_evidence_search_cursor_from_another_query_filters_or_index_is_refused(paged_index: Path) -> None:
    """ac2: a cursor is good only for the query, filters and index that made it."""
    searched = service(paged_index)
    cursor = searched.search("quokka").next_cursor
    assert cursor is not None
    assert (
        ids(searched.search("quokka", cursor=cursor))
        == ids(service(paged_index, page_size=100).search("quokka"))[20:40]
    )
    assert ids(searched.search("  quokka ", cursor=cursor)) == ids(searched.search("quokka", cursor=cursor))
    with pytest.raises(InvalidSearchCursor):
        searched.search("filler1", cursor=cursor)
    with pytest.raises(InvalidSearchCursor):
        searched.search("quokka", SearchFilters(side=Side.NEG), cursor)
    with pytest.raises(InvalidSearchCursor):
        service(paged_index, index_id=OTHER_INDEX_ID).search("quokka", cursor=cursor)
    with pytest.raises(InvalidSearchCursor):
        searched.search("quokka", cursor=cursor[:-2] + ("A" if cursor[-2] != "A" else "B") + cursor[-1])


# ------------------------------------------------------------------------------------------------
# Who is never searchable
# ------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def people(tmp_path_factory: pytest.TempPathFactory) -> EvidenceSearchService:
    documents = (
        document(1, text="wombat in the text only", tag="Invented claim", cite="Lindqvist 26"),
        document(2, text="nothing here", tag="Invented wombat claim", cite="Lindqvist 26"),
        document(3, text="nothing here", tag="Invented claim", cite="Wombat 26, Invented Quarterly"),
        document(
            4,
            text="a read wombat card",
            spans=(parser_span(RunEmphasis.UNDERLINE, 7, 13),),
            tag="Invented claim",
            cite="Lindqvist 26",
        ),
        document(
            5,
            text="disclosed card",
            occurrences=(
                occurrence(0, source_number=5, school=SCHOOL, team=TEAM),
                occurrence(1, source_number=6, school=OTHER_SCHOOL, team=OTHER_TEAM),
            ),
        ),
        document(6, text="camp card", caselist="openev", event="POLICY", camp=CAMP, sides=()),
        document(
            7, text="nothing here", tag="Invented text wombat and read aloud wombat", cite="Lindqvist 26"
        ),
    )
    return service(build(tmp_path_factory.mktemp("people"), documents))


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("wombat", {1, 2, 3, 4, 7}),
        ("tag:wombat", {2, 7}),
        ("author:wombat", {3}),
        ("TAG:wombat", {2, 7}),
        ("Author:Wombat", {3}),
        ("wombat -tag:wombat", {1, 3, 4}),
        ("wombat -author:wombat", {1, 2, 4, 7}),
        ("tag:lindqvist", set[int]()),
        ("author:invented", {3, 5, 6}),
        ("text:wombat", {7}),
        ("read_aloud:wombat", {7}),
    ],
)
def test_evidence_search_prefix_searches_only_the_field_it_names(
    people: EvidenceSearchService, query: str, expected: set[int]
) -> None:
    """ac1: `tag:` the tag, `author:` the cite; any other `name:` is a word like any other.

    `text:wombat` is the phrase "text wombat", which only document 7's tag holds: not a column filter.
    """
    assert set(ids(people.search(query))) == expected


@pytest.mark.parametrize(
    "query",
    [
        "maple",
        '"Maple Grove"',
        "school:maple",
        "team:QX",
        "QX",
        "ZT",
        "riverbend",
        "debater:riverbend",
        "author:maple",
        "tag:QX",
        "invitational",
        '"Round 4"',
        "cascade",
        "author:cascade",
        "adv",
        '"Invented Adv CP"',
    ],
)
def test_evidence_search_never_matches_a_school_team_tournament_round_camp_or_title(
    people: EvidenceSearchService, query: str
) -> None:
    """The forbidden "search by school, team code or debater": every one of them matches nothing."""
    assert people.search(query).hits == ()


# ------------------------------------------------------------------------------------------------
# The suppression seam
# ------------------------------------------------------------------------------------------------

SHARED: Final = document(
    1,
    text="pangolin shared card",
    occurrences=(
        occurrence(0, source_number=11, school=SCHOOL, team=TEAM),
        occurrence(1, source_number=12, school=OTHER_SCHOOL, team=OTHER_TEAM, side="AFF"),
        occurrence(2, source_number=13, school="Invented Hills", team="AB"),
    ),
    file_count=3,
    team_count=3,
)
LONG_TAIL: Final = document(
    2,
    text="pangolin long tail card",
    occurrences=tuple(
        occurrence(
            ordinal,
            source_number=20 + ordinal,
            school=f"Invented School {ordinal}",
            team="CD",
            provenance=ordinal < 5,
        )
        for ordinal in range(7)
    ),
    file_count=7,
    team_count=7,
)
CAMP_CARD: Final = document(
    3, text="pangolin camp card", caselist="openev", event="POLICY", camp=CAMP, sides=()
)


@pytest.fixture(scope="module")
def suppressible(tmp_path_factory: pytest.TempPathFactory) -> EvidenceSearchService:
    return service(build(tmp_path_factory.mktemp("suppressible"), (SHARED, LONG_TAIL, CAMP_CARD)))


def stopping(*sources: int) -> SuppressionPredicate:
    stopped = {source(number) for number in sources}
    return lambda sha256, _disclosure: sha256 in stopped


def test_evidence_search_without_a_predicate_hides_nothing(suppressible: EvidenceSearchService) -> None:
    assert set(ids(suppressible.search("pangolin"))) == {1, 2, 3}
    card = suppressible.card("hsld26", cluster(1))
    assert card is not None
    assert [one.ordinal for one in card.occurrences] == [0, 1, 2]
    assert (card.file_count, card.team_count) == (3, 3)


def test_evidence_search_hides_a_card_whose_representative_is_suppressed(
    suppressible: EvidenceSearchService,
) -> None:
    """The PM's ruling for t07: hidden until the next build chooses another representative."""
    predicate = stopping(11)
    assert set(ids(suppressible.search("pangolin", is_suppressed=predicate))) == {2, 3}
    assert suppressible.card("hsld26", cluster(1), is_suppressed=predicate) is None


def test_evidence_search_answers_not_found_when_every_occurrence_is_suppressed(
    suppressible: EvidenceSearchService,
) -> None:
    predicate = stopping(11, 12, 13)
    assert suppressible.card("hsld26", cluster(1), is_suppressed=predicate) is None
    assert 1 not in ids(suppressible.search("pangolin", is_suppressed=predicate))


def test_evidence_search_leaves_out_a_suppressed_occurrence_and_counts_again(
    suppressible: EvidenceSearchService,
) -> None:
    predicate = stopping(12)
    card = suppressible.card("hsld26", cluster(1), is_suppressed=predicate)
    assert card is not None
    assert [one.ordinal for one in card.occurrences] == [0, 2]
    assert OTHER_SCHOOL not in " ".join(one.provenance_line or "" for one in card.occurrences)
    assert (card.file_count, card.team_count) == (2, 2)
    (hit,) = [
        hit
        for hit in suppressible.search("pangolin", is_suppressed=predicate).hits
        if hit.cluster_id == cluster(1)
    ]
    assert (hit.file_count, hit.team_count) == (2, 2)


def test_evidence_search_gives_no_team_count_when_a_survivor_kept_no_provenance(
    suppressible: EvidenceSearchService,
) -> None:
    """PM ruling 2026-10-20: seven occurrences, five with provenance, one suppressed.

    Six files survive, exactly. Two survivors are past the provenance limit, so nobody can say which
    teams are left: the stored seven would count the hidden team, and the card gives no team count.
    """
    card = suppressible.card("hsld26", cluster(2), is_suppressed=stopping(21))
    assert card is not None
    assert [one.ordinal for one in card.occurrences] == [0, 2, 3, 4, 5, 6]
    assert [one.provenance_line is not None for one in card.occurrences] == [
        True,
        True,
        True,
        True,
        False,
        False,
    ]
    assert (card.file_count, card.team_count) == (6, None)
    (hit,) = [
        hit
        for hit in suppressible.search("pangolin", is_suppressed=stopping(21)).hits
        if hit.cluster_id == cluster(2)
    ]
    assert (hit.file_count, hit.team_count) == (6, None)


def test_evidence_search_keeps_the_stored_counts_when_nothing_is_suppressed_past_the_limit(
    suppressible: EvidenceSearchService,
) -> None:
    """With nothing suppressed the build's counts stand, survivors past the provenance limit or not."""
    card = suppressible.card("hsld26", cluster(2), is_suppressed=stopping(99))
    assert card is not None
    assert (card.file_count, card.team_count) == (7, 7)


def occurrence_row(ordinal: int, school: str | None, *, provenance: bool = True) -> StoredOccurrence:
    return StoredOccurrence(
        doc_id=1,
        ordinal=ordinal,
        caselist="hsld26",
        source_sha256=source(ordinal),
        disclosure=None,
        snapshot="2026-09-01",
        last_snapshot="2026-09-01",
        completeness="FULL",
        attributed=school is not None,
        provenance=provenance,
        school=school,
        team_code="QX" if school else None,
    )


@pytest.mark.parametrize(
    ("survivor_ordinals", "expected"),
    [
        ((0, 1, 2, 3, 4), (5, 3)),
        ((0, 2, 3), (3, 2)),
        ((0, 1, 3), (3, 1)),
        ((0, 3), (2, 1)),
        ((0, 1, 2, 4), (4, None)),
        ((0, 4), (2, None)),
    ],
    ids=[
        "nothing-suppressed-the-stored-counts",
        "every-survivor-kept-provenance-exact",
        "one-team-twice-counted-once",
        "an-unattributed-survivor-names-no-team",
        "a-survivor-past-the-limit-no-team-count",
        "only-the-representative-and-one-past-the-limit",
    ],
)
def test_evidence_search_surviving_counts_are_the_pms_rule(
    survivor_ordinals: tuple[int, ...], expected: tuple[int, int | None]
) -> None:
    """PM ruling 2026-10-20, written by hand. Occurrences 0 and 1 are Maple Grove's, 2 Riverbend's, 3
    attributed to nobody, and 4 past the provenance limit, from five sources; the build stored 5 files
    and 3 teams. Files are always the survivors' sources; teams are exact only when every survivor kept
    its provenance, and `None` otherwise."""
    occurrences = [
        occurrence_row(0, SCHOOL),
        occurrence_row(1, SCHOOL),
        occurrence_row(2, OTHER_SCHOOL),
        occurrence_row(3, None),
        occurrence_row(4, None, provenance=False),
    ]
    survivors = [occurrences[one] for one in survivor_ordinals]
    assert surviving_counts(5, 3, occurrences, survivors) == expected


def test_evidence_search_asks_about_a_camp_occurrence_with_no_disclosure_digest(
    suppressible: EvidenceSearchService,
) -> None:
    asked: list[tuple[str, str | None]] = []

    def predicate(sha256: str, disclosure: str | None) -> bool:
        asked.append((sha256, disclosure))
        return False

    assert suppressible.card("openev", cluster(3), is_suppressed=predicate) is not None
    assert asked == [(source(3), None)]


def test_evidence_search_fills_a_page_past_hidden_cards_and_skips_none(paged_index: Path) -> None:
    """Every third of the forty-five representatives suppressed: thirty left, a page of twenty then ten."""
    hidden = {number for number in range(1, 46) if number % 3 == 0}
    predicate = stopping(*hidden)
    searched = service(paged_index)
    pages = every_page(searched, "quokka", is_suppressed=predicate)
    assert [len(page.hits) for page in pages] == [20, 10]
    whole = ids(service(paged_index, page_size=100).search("quokka"))
    assert [number for page in pages for number in ids(page)] == [
        number for number in whole if number not in hidden
    ]


# ------------------------------------------------------------------------------------------------
# The time budget
# ------------------------------------------------------------------------------------------------


def spent_after(reads: int) -> Callable[[], float]:
    """A clock at 0 for `reads` reads after the one that sets the deadline, and a minute on after that."""
    counter = itertools.count()
    return lambda: 0.0 if next(counter) <= reads else 60.0


@pytest.fixture(scope="module")
def large_index(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build(
        tmp_path_factory.mktemp("large"),
        (
            document(number, text="numbat " * (1 + number % 11) + f"filler{number}")
            for number in range(1, 301)
        ),
    )


def test_evidence_search_past_its_budget_returns_what_it_has_flagged_partial(large_index: Path) -> None:
    """Whenever the budget runs out, the page is a prefix of the ranking and its cursor resumes after it."""
    whole = ids(service(large_index).search("numbat"))
    fetched: set[int] = set()
    for reads in range(40):
        page = service(large_index, time_budget_seconds=1.0, clock=spent_after(reads)).search("numbat")
        if not page.partial:
            assert ids(page) == whole
            break
        assert ids(page) == whole[: len(page.hits)]
        assert page.next_cursor is not None
        rest = service(large_index).search("numbat", cursor=page.next_cursor)
        assert (ids(page) + ids(rest))[:20] == whole
        fetched.add(len(page.hits))
    assert 0 in fetched, "a budget spent at once returns nothing, flagged partial"
    assert any(0 < count < 20 for count in fetched), (
        "a budget spent part-way returns the rows fetched by then"
    )


class InterruptedAfterAFullBatch:
    """A reader whose one batch holds a whole page and the next hit, and was stopped by the budget anyway."""

    index_id = INDEX_ID
    format_version = SEARCH_INDEX_FORMAT_VERSION

    def __init__(self, hits: Sequence[StoredHit]) -> None:
        self.hits = tuple(hits)

    def match(self, request: MatchRequest) -> MatchBatch:
        return MatchBatch(
            hits=self.hits[request.offset : request.offset + request.limit], exhausted=False, interrupted=True
        )

    def count(self, request: CountRequest) -> CountBatch:
        raise AssertionError("not asked: a search the budget stopped is not counted (v1-e39-t11)")

    def document(self, caselist: str, cluster_id: str) -> StoredDocument | None:
        raise AssertionError("not asked")

    def occurrences(self, doc_id: int) -> tuple[StoredOccurrence, ...]:
        raise AssertionError("not asked")


def stored_hit(position: int) -> StoredHit:
    return StoredHit(
        position=position,
        doc_id=position + 1,
        caselist="hsld26",
        cluster_id=cluster(position + 1),
        event="LD",
        camp=None,
        tag=None,
        short_cite=None,
        snippet="",
        file_count=1,
        team_count=1,
        representative=StoredOccurrence(
            doc_id=position + 1,
            ordinal=0,
            caselist="hsld26",
            source_sha256=source(position + 1),
            disclosure=None,
            snapshot="2026-09-01",
            last_snapshot="2026-09-01",
            completeness="FULL",
            attributed=False,
            provenance=True,
        ),
    )


def test_evidence_search_stopped_after_finding_the_next_hit_resumes_at_that_hit() -> None:
    """The budget can run out after the twenty-first row: the cursor points at row twenty, not past it."""
    searched = EvidenceSearchService(
        InterruptedAfterAFullBatch([stored_hit(position) for position in range(30)])
    )
    page = searched.search("numbat")
    assert page.partial
    assert len(page.hits) == 20
    resumed = searched.search("numbat", cursor=page.next_cursor)
    assert ids(resumed)[0] == 21


def test_evidence_search_within_its_budget_is_not_partial(large_index: Path) -> None:
    page = service(large_index, time_budget_seconds=60.0).search("numbat")
    assert not page.partial
    assert len(page.hits) == 20


# ------------------------------------------------------------------------------------------------
# A card through the index
# ------------------------------------------------------------------------------------------------

CARD_TEXT: Final = 'Invented growth <script>alert("x")</script> ends <a href="javascript:x">badly</a>'
CARD_SPANS: Final = (
    parser_span(RunEmphasis.UNDERLINE, 9, 15),
    parser_span(RunEmphasis.HIGHLIGHT, 9, 15, "cyan"),
    parser_span(RunEmphasis.BOLD, 16, 24),
)
CARD_SIZES: Final = (FontSizeSpan(start_offset=0, end_offset=len(CARD_TEXT), half_points=22),)


@pytest.fixture(scope="module")
def carded(tmp_path_factory: pytest.TempPathFactory) -> EvidenceSearchService:
    return service(
        build(
            tmp_path_factory.mktemp("carded"),
            (
                document(
                    1,
                    text=CARD_TEXT,
                    spans=CARD_SPANS,
                    sizes=CARD_SIZES,
                    tag="Invented tag <b>",
                    sides=("AFF", "NEG"),
                ),
            ),
        )
    )


def test_evidence_search_card_returns_its_text_runs_and_provenance(carded: EvidenceSearchService) -> None:
    card = carded.card("hsld26", cluster(1))
    assert card is not None
    assert (card.tag, card.cite, card.short_cite, card.event, card.sides) == (
        "Invented tag <b>",
        "Lindqvist 26, Invented Quarterly",
        "Lindqvist 26",
        "LD",
        ("AFF", "NEG"),
    )
    assert card.text == CARD_TEXT
    assert card.read_aloud == "growth"
    assert "".join(run.text for run in card.runs) == CARD_TEXT
    assert [one.provenance_line for one in card.occurrences] == [
        f"[Disclosed: hsld26 2026-09-01 — {SCHOOL} {TEAM}, Neg vs. {TOURNAMENT} {ROUND}]"
    ]
    assert carded.card("hsld26", cluster(2)) is None
    assert carded.card("hspf26", cluster(1)) is None


def test_evidence_search_card_renders_inert_with_the_stored_spans_coverage(
    carded: EvidenceSearchService,
) -> None:
    """ac3 and ac4 through the index: the stored spans render as the fixture's do, escaped."""
    card = carded.card("hsld26", cluster(1))
    assert card is not None
    rendered = render_card_html(card.runs)
    indexed = [
        IndexedFormattingSpan(s.emphasis, s.start_offset, s.end_offset, s.highlight_color) for s in CARD_SPANS
    ]
    sizes = [IndexedFontSizeSpan(s.start_offset, s.end_offset, s.half_points) for s in CARD_SIZES]
    assert rendered == render_card_html(card_runs(CARD_TEXT, indexed, sizes))
    assert formatting_sha256(CARD_SPANS, CARD_SIZES) == formatting_sha256(
        [parser_span(s.emphasis, s.start_offset, s.end_offset, s.highlight_color) for s in indexed],
        CARD_SIZES,
    )
    assert rendered == (
        '<span class="card-size-22">Invented </span>'
        '<span class="card-underline card-highlight card-highlight-cyan card-size-22">growth</span>'
        '<span class="card-size-22"> </span>'
        '<span class="card-bold card-size-22">&lt;script&gt;</span>'
        '<span class="card-size-22">alert(&quot;x&quot;)&lt;/script&gt; ends '
        "&lt;a href=&quot;javascript:x&quot;&gt;"
        "badly&lt;/a&gt;</span>"
    )
