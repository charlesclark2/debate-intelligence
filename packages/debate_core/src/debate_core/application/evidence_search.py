"""Search and card lookup over the student search pilot's index (`v1-e39-t03`).

:class:`EvidenceSearchService` is what the pilot's pages (`v1-e39-t06`) call. It parses a student's
query (:func:`~debate_core.domain.evidence_search.parse_query`), asks a
:class:`~debate_core.application.ports.search_index_reader.SearchIndexReader` for a window of the
weighted BM25 ranking, and turns the rows into a :class:`~debate_core.domain.evidence_search.SearchPage`
or a :class:`~debate_core.domain.evidence_search.Card`. It keeps no state between calls: a page's
cursor carries where the next one starts.

## The suppression seam

The index is rebuilt weekly, and a removal can land between builds. Search and card lookup take an
optional predicate, ``is_suppressed(source_sha256, disclosure_digest)``, over the digests the index
keeps for every surviving occurrence (a camp occurrence's disclosure digest is `None`). `v1-e39-t07`
wires it to the live suppression list; without one, nothing is hidden. With one:

* a card whose representative occurrence is suppressed is hidden from results and answers card
  lookup as not found, until the next build chooses another representative (the PM's ruling for
  `v1-e39-t07`). A card whose every occurrence is suppressed has its representative suppressed, so it
  is not found either;
* any other suppressed occurrence is left out of the card's occurrences, and the card's file and team
  counts are counted again over the survivors (:func:`surviving_counts`); when the survivors cannot
  say which teams are left, the card gives no team count (the PM's ruling of 2026-10-20).

## The time budget

A search that runs past its budget stops where it is and returns what it has fetched, with
`partial` set and a cursor that resumes where it stopped. The budget is checked inside SQLite while a
statement runs, through the reader, against the service's clock. FTS5's ranking sort cannot be
stopped (:meth:`EvidenceSearchService.search` says why and how long it takes).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from typing import Final

from debate_core.application.ports.search_index_reader import (
    CountRequest,
    MatchRequest,
    SearchIndexReader,
    StoredHit,
    StoredOccurrence,
)
from debate_core.domain.evidence_search import (
    DEFAULT_RESULT_COUNT_CAP,
    MAX_CURSOR_OFFSET,
    RANKING_WEIGHTS,
    SEARCH_PAGE_SIZE,
    Card,
    OccurrenceProvenance,
    RankingWeights,
    ResultCount,
    SearchFilters,
    SearchHit,
    SearchNotice,
    SearchPage,
    card_runs,
    decode_search_cursor,
    encode_search_cursor,
    occurrence_provenance_line,
    parse_query,
    search_binding,
    snippet_segments,
)

__all__ = [
    "DEFAULT_SEARCH_TIME_BUDGET_SECONDS",
    "EvidenceSearchService",
    "SuppressionPredicate",
    "surviving_counts",
]

DEFAULT_SEARCH_TIME_BUDGET_SECONDS: Final = 2.0
"""How long a search may run before it returns what it has, flagged partial."""

SuppressionPredicate = Callable[[str, str | None], bool]
"""``is_suppressed(source_sha256, disclosure_digest)``: whether the live list stops an occurrence."""


def _line(occurrence: StoredOccurrence) -> str | None:
    return occurrence_provenance_line(
        caselist=occurrence.caselist,
        snapshot=occurrence.snapshot,
        provenance=occurrence.provenance,
        side=occurrence.side,
        school=occurrence.school,
        team_code=occurrence.team_code,
        tournament=occurrence.tournament,
        round_label=occurrence.round_label,
        camp=occurrence.camp,
        camp_year=occurrence.camp_year,
        camp_event=occurrence.camp_event,
        camp_file_title=occurrence.camp_file_title,
    )


def _suppressed(occurrence: StoredOccurrence, is_suppressed: SuppressionPredicate | None) -> bool:
    return is_suppressed is not None and is_suppressed(occurrence.source_sha256, occurrence.disclosure)


def surviving_counts(
    stored_files: int,
    stored_teams: int,
    occurrences: Sequence[StoredOccurrence],
    survivors: Sequence[StoredOccurrence],
) -> tuple[int, int | None]:
    """A card's file and team counts once some of its occurrences are suppressed.

    Nothing suppressed: the counts the build stored. Otherwise files are the distinct sources among
    the survivors, exactly. Teams are the distinct school and team code pairs among them when every
    survivor kept its provenance. When some did not (they are past the build's provenance limit), the
    index cannot say which teams disclosed them, and the stored count may include the hidden team, so
    the team count is `None` (the PM's ruling of 2026-10-20: a count above the truth right after a
    removal is the wrong way to err). That lasts until the next build. `v1-e39-t07` changes it here.
    """
    if len(survivors) == len(occurrences):
        return stored_files, stored_teams
    files = len({one.source_sha256 for one in survivors})
    if not all(one.provenance for one in survivors):
        return files, None
    return files, len({(one.school, one.team_code) for one in survivors if one.school is not None})


class EvidenceSearchService:
    """Searches one index and looks cards up in it."""

    def __init__(
        self,
        reader: SearchIndexReader,
        *,
        time_budget_seconds: float = DEFAULT_SEARCH_TIME_BUDGET_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        page_size: int = SEARCH_PAGE_SIZE,
        weights: RankingWeights = RANKING_WEIGHTS,
        count_cap: int = DEFAULT_RESULT_COUNT_CAP,
    ) -> None:
        if page_size < 1:
            raise ValueError("a page holds at least one result")
        if not 1 <= count_cap <= MAX_CURSOR_OFFSET:
            raise ValueError(f"a search counts up to between 1 and {MAX_CURSOR_OFFSET} results")
        self._reader = reader
        self._count_cap = count_cap
        self._budget = time_budget_seconds
        self._clock = clock
        self._page_size = page_size
        self._rank = weights.bm25()

    def search(
        self,
        query: str,
        filters: SearchFilters | None = None,
        cursor: str | None = None,
        *,
        is_suppressed: SuppressionPredicate | None = None,
    ) -> SearchPage:
        """One page of results for `query` under `filters`, from `cursor` or the first.

        Raises :class:`~debate_core.domain.evidence_search.InvalidSearchCursor` for a cursor that is
        not this query's, these filters' and this index's.

        **A known limit of the time budget** (accepted by the PM, 2026-10-20). The budget is checked by
        SQLite's progress handler, which runs between virtual-machine instructions. FTS5 ranks every
        match and sorts them inside one instruction, before the first row comes back, and nothing in
        SQLite 3.40.0 (the Lambda image's) can interrupt that sort. So a search can overrun its budget
        by the length of that sort. Measured on the operator's Mac, not on the function: on the dev
        index of 46,658 documents, twenty generic queries ran at a warm p50 under 4 ms, p95 12.1 ms
        and max 207 ms (`the`, which matches 45,948 documents); on a synthetic index of 250,000
        documents, p95 341 ms and max 421 ms. `v1-e39-t10` measures query time on the Lambda function
        itself.
        """
        filters = filters if filters is not None else SearchFilters()
        parsed = parse_query(query)
        notices: list[SearchNotice] = []
        if parsed.shortened:
            notices.append(SearchNotice.QUERY_SHORTENED)
        if filters.first_seen_on_or_after is not None:
            notices.append(SearchNotice.FIRST_SEEN_CASELIST_CARDS_ONLY)
        if filters.side is not None:
            notices.append(SearchNotice.SIDE_CASELIST_CARDS_ONLY)
        binding = search_binding(self._reader.index_id, parsed, filters)
        offset = decode_search_cursor(cursor, binding) if cursor is not None else 0
        expression = parsed.fts5_expression()
        if expression is None:
            notices.append(SearchNotice.NO_SEARCH_TERMS)
            return SearchPage(hits=(), next_cursor=None, notices=tuple(notices))

        deadline = self._clock() + self._budget

        def expired() -> bool:
            return self._clock() >= deadline

        kept: list[StoredHit] = []
        next_position: int | None = None
        partial = False
        while next_position is None:
            batch = self._reader.match(
                MatchRequest(
                    expression=expression,
                    rank=self._rank,
                    filters=filters,
                    offset=offset,
                    limit=self._page_size + 1,
                    expired=expired,
                )
            )
            for hit in batch.hits:
                if _suppressed(hit.representative, is_suppressed):
                    continue
                if len(kept) == self._page_size:
                    next_position = hit.position
                    break
                kept.append(hit)
            offset += len(batch.hits)
            if batch.interrupted:
                partial = True
                next_position = offset if next_position is None else next_position
            if batch.exhausted:
                break
        return SearchPage(
            hits=tuple(self._hit(hit, is_suppressed) for hit in kept),
            next_cursor=(
                encode_search_cursor(binding, next_position)
                if next_position is not None and next_position <= MAX_CURSOR_OFFSET
                else None
            ),
            partial=partial,
            notices=tuple(notices),
            count=None,
        )

    def check_cursor(self, query: str, filters: SearchFilters | None, cursor: str) -> None:
        """Refuse a cursor :meth:`search` would refuse for this query and these filters, as it would."""

    def _hit(self, hit: StoredHit, is_suppressed: SuppressionPredicate | None) -> SearchHit:
        files, teams = hit.file_count, hit.team_count
        if is_suppressed is not None:
            occurrences = self._reader.occurrences(hit.doc_id)
            survivors = [one for one in occurrences if not _suppressed(one, is_suppressed)]
            files, teams = surviving_counts(files, teams, occurrences, survivors)
        return SearchHit(
            caselist=hit.caselist,
            cluster_id=hit.cluster_id,
            event=hit.event,
            camp=hit.camp,
            tag=hit.tag,
            short_cite=hit.short_cite,
            snippet=snippet_segments(hit.snippet),
            file_count=files,
            team_count=teams,
            provenance_line=_line(hit.representative),
        )

    def card(
        self, caselist: str, cluster_id: str, *, is_suppressed: SuppressionPredicate | None = None
    ) -> Card | None:
        """The card for one cluster, or `None`: not in the index, or its representative suppressed."""
        document = self._reader.document(caselist, cluster_id)
        if document is None:
            return None
        occurrences = self._reader.occurrences(document.doc_id)
        stopped = [_suppressed(one, is_suppressed) for one in occurrences]
        if not occurrences or occurrences[0].ordinal != 0 or stopped[0]:
            return None
        survivors = [one for one, out in zip(occurrences, stopped, strict=True) if not out]
        files, teams = surviving_counts(document.file_count, document.team_count, occurrences, survivors)
        return Card(
            caselist=document.caselist,
            cluster_id=document.cluster_id,
            event=document.event,
            camp=document.camp,
            tag=document.tag,
            cite=document.cite,
            short_cite=document.short_cite,
            completeness=document.completeness,
            text=document.text,
            read_aloud=document.read_aloud,
            runs=card_runs(document.text, document.formatting_spans, document.font_size_spans),
            sides=document.sides,
            first_seen=document.first_seen,
            last_seen=document.last_seen,
            file_count=files,
            team_count=teams,
            occurrences=tuple(
                OccurrenceProvenance(
                    ordinal=one.ordinal,
                    caselist=one.caselist,
                    snapshot=one.snapshot,
                    last_snapshot=one.last_snapshot,
                    completeness=one.completeness,
                    attributed=one.attributed,
                    provenance=one.provenance,
                    side=one.side,
                    school=one.school,
                    team_code=one.team_code,
                    tournament=one.tournament,
                    round_label=one.round_label,
                    camp=one.camp,
                    camp_year=one.camp_year,
                    camp_event=one.camp_event,
                    camp_file_title=one.camp_file_title,
                    provenance_line=_line(one),
                )
                for one in survivors
            ),
        )
