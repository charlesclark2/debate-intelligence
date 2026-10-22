"""The holder re-reads the suppression list in its refresh, at most five minutes apart (`v1-e39-t07`).

ADR-0019 (c) 5 and the data-use policy's E39 gate item 5: an occurrence suppressed after the index
was built is hidden by the running function within five minutes, and an environment frozen longer
rechecks before it answers. The clock is the test's own, so "five minutes later" is a line of code;
the index is a real SQLite file published in memory, and the list is served beside it as the bucket
serves it, entity tags and `304`s included.

Every value is synthetic: invented digests, words, request ids and the caselist slug `hsld26`.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

import pytest

from debate_core.application.caselist.suppression import SUPPRESSION_LIST_KEY
from debate_core.application.errors import StoreUnavailable
from debate_core.application.ports.search_index import IndexedOccurrence, SearchDocument
from debate_core.application.ports.suppression import ReasonCode, SuppressionAction, SuppressionEntry
from debate_core.application.search_index_holder import (
    POINTER_RECHECK_INTERVAL,
    SearchIndexHolder,
    SearchIndexUnavailable,
    SuppressionListUnavailable,
)
from debate_core.domain.search_index import SEARCH_INDEX_POINTER_KEY
from debate_core.integrations.local.search_index import SqliteSearchIndexWriter
from debate_core.integrations.local.search_index_reader import SqliteSearchIndexReader
from debate_core.testing.search_index import InMemorySearchIndexSource, PublishedIndex, published_index

START: Final = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)
JUST_UNDER: Final = POINTER_RECHECK_INTERVAL - timedelta(seconds=1)
OUTAGE: Final = StoreUnavailable(
    "GetObject", "s3://synthetic/manifests/_suppression/suppression-list.jsonl", "synthetic"
)


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


def source_of(doc_id: int, ordinal: int) -> str:
    return f"{doc_id:032x}{ordinal:032x}"


def disclosure_of(doc_id: int, ordinal: int) -> str:
    return f"{ordinal:032x}{doc_id:032x}"


def occurrence(doc_id: int, ordinal: int, *, school: str, team: str) -> IndexedOccurrence:
    return IndexedOccurrence(
        ordinal=ordinal,
        caselist="hsld26",
        source_sha256=source_of(doc_id, ordinal),
        disclosure=disclosure_of(doc_id, ordinal),
        first_element_index=0,
        last_element_index=2,
        snapshot="2026-09-01",
        last_snapshot="2026-09-08",
        completeness="FULL",
        attributed=True,
        provenance=True,
        side="NEG",
        school=school,
        team_code=team,
        tournament="Invented Invitational",
        round="Round 4",
    )


def document(doc_id: int, words: str, *occurrences: IndexedOccurrence, team_count: int = 1) -> SearchDocument:
    return SearchDocument(
        doc_id=doc_id,
        caselist="hsld26",
        cluster_id=f"{doc_id:064x}",
        event="LD",
        camp=None,
        tag="Invented claim",
        cite="Lindqvist 26, Invented Quarterly",
        short_cite="Lindqvist 26",
        read_aloud="",
        text=words,
        completeness="FULL",
        formatting_spans=(),
        font_size_spans=(),
        sides=("NEG",),
        first_seen="2026-09-01",
        last_seen="2026-09-08",
        file_count=len(occurrences),
        team_count=team_count,
        occurrences=occurrences,
    )


SHARED: Final = 1
"""Card 1: disclosed by two invented teams, in two files; the first is its representative."""
ALONE: Final = 2
"""Card 2: one occurrence."""


@pytest.fixture(scope="module")
def index(tmp_path_factory: pytest.TempPathFactory) -> PublishedIndex:
    path = tmp_path_factory.mktemp("index") / "search-index.sqlite"
    sink = SqliteSearchIndexWriter().create(path)
    sink.add(
        document(
            SHARED,
            "zephyr granite",
            occurrence(SHARED, 0, school="Maple Grove", team="QX"),
            occurrence(SHARED, 1, school="Riverbend", team="ZT"),
            team_count=2,
        )
    )
    sink.add(document(ALONE, "zephyr basalt", occurrence(ALONE, 0, school="Maple Grove", team="QX")))
    sink.finish()
    return published_index(path.read_bytes(), documents_by_store={"hsld26": 2})


@pytest.fixture
def bucket(index: PublishedIndex) -> InMemorySearchIndexSource:
    source = InMemorySearchIndexSource()
    source.publish(index)
    return source


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def holder(tmp_path: Path, bucket: InMemorySearchIndexSource, clock: Clock) -> Iterator[SearchIndexHolder]:
    made = SearchIndexHolder(
        bucket,
        directory=tmp_path / "tub-index",
        open_reader=lambda path, index_id: SqliteSearchIndexReader(path, index_id=index_id),
        clock=clock,
        suppression_list=bucket,
    )
    yield made
    made.close()


def suppression(source: str, *, disclosure: str | None = None, minute: int = 0) -> SuppressionEntry:
    return SuppressionEntry(
        action=SuppressionAction.SUPPRESS,
        sha256=source,
        disclosure=disclosure,
        recorded_at=START + timedelta(minutes=minute),
        reason=ReasonCode.REQUESTED_BY_TEAM,
        request_id="RM-2026-01",
    )


def found(holder: SearchIndexHolder) -> list[int]:
    with holder.lease() as search:
        return sorted(int(hit.cluster_id, 16) for hit in search.search("zephyr").hits)


def card_files(holder: SearchIndexHolder, doc_id: int) -> int | None:
    """How many files the card's page would say it is in, or `None` when it is not found."""
    with holder.lease() as search:
        card = search.card("hsld26", f"{doc_id:064x}")
    return None if card is None else card.file_count


def unavailable_because(holder: SearchIndexHolder) -> BaseException | None:
    with pytest.raises(SearchIndexUnavailable) as raised, holder.lease():
        pass
    return raised.value.__cause__


# ------------------------------------------------------------------------------------------------
# Within five minutes of a removal
# ------------------------------------------------------------------------------------------------


def test_a_card_removed_whole_is_gone_from_results_and_its_page_at_five_minutes_and_not_before(
    holder: SearchIndexHolder, bucket: InMemorySearchIndexSource, clock: Clock
) -> None:
    assert found(holder) == [SHARED, ALONE]

    bucket.append_suppression(suppression(source_of(ALONE, 0)))
    clock.advance(JUST_UNDER)
    assert found(holder) == [SHARED, ALONE]
    assert card_files(holder, ALONE) == 1

    clock.advance(timedelta(seconds=1))
    assert found(holder) == [SHARED]
    assert card_files(holder, ALONE) is None


def test_a_withdrawn_disclosure_leaves_the_card_with_the_other_teams_file(
    holder: SearchIndexHolder, bucket: InMemorySearchIndexSource, clock: Clock
) -> None:
    """Card 1's second file is withdrawn: the card stays, in one file instead of two."""
    assert card_files(holder, SHARED) == 2

    bucket.append_suppression(suppression(source_of(SHARED, 1), disclosure=disclosure_of(SHARED, 1)))
    clock.advance(POINTER_RECHECK_INTERVAL)

    assert card_files(holder, SHARED) == 1
    assert found(holder) == [SHARED, ALONE]


def test_a_withdrawal_of_another_disclosure_of_the_same_bytes_hides_nothing(
    holder: SearchIndexHolder, bucket: InMemorySearchIndexSource, clock: Clock
) -> None:
    found(holder)
    bucket.append_suppression(suppression(source_of(SHARED, 1), disclosure=disclosure_of(ALONE, 7)))
    clock.advance(POINTER_RECHECK_INTERVAL)

    assert card_files(holder, SHARED) == 2


def test_a_card_whose_representative_is_withdrawn_is_not_found_until_the_next_build(
    holder: SearchIndexHolder, bucket: InMemorySearchIndexSource, clock: Clock
) -> None:
    found(holder)
    bucket.append_suppression(suppression(source_of(SHARED, 0), disclosure=disclosure_of(SHARED, 0)))
    clock.advance(POINTER_RECHECK_INTERVAL)

    assert found(holder) == [ALONE]
    assert card_files(holder, SHARED) is None


def test_an_unsuppress_brings_the_card_back_at_the_next_reread(
    holder: SearchIndexHolder, bucket: InMemorySearchIndexSource, clock: Clock
) -> None:
    bucket.append_suppression(suppression(source_of(ALONE, 0)))
    assert found(holder) == [SHARED]

    bucket.append_suppression(
        SuppressionEntry(
            action=SuppressionAction.UNSUPPRESS,
            sha256=source_of(ALONE, 0),
            recorded_at=START + timedelta(minutes=1),
            reason=ReasonCode.REMOVED_IN_ERROR,
        )
    )
    clock.advance(POINTER_RECHECK_INTERVAL)

    assert found(holder) == [SHARED, ALONE]


def test_an_environment_frozen_past_five_minutes_rereads_the_list_before_it_answers(
    holder: SearchIndexHolder, bucket: InMemorySearchIndexSource, clock: Clock
) -> None:
    assert found(holder) == [SHARED, ALONE]

    bucket.append_suppression(suppression(source_of(ALONE, 0)))
    clock.advance(timedelta(hours=3))

    assert found(holder) == [SHARED]


# ------------------------------------------------------------------------------------------------
# How it is read
# ------------------------------------------------------------------------------------------------


def test_the_list_is_read_before_the_pointer_and_not_again_within_five_minutes(
    holder: SearchIndexHolder, bucket: InMemorySearchIndexSource, index: PublishedIndex, clock: Clock
) -> None:
    found(holder)
    clock.advance(JUST_UNDER)
    found(holder)

    assert bucket.reads == [SUPPRESSION_LIST_KEY, SEARCH_INDEX_POINTER_KEY, index.manifest_key, index.object_key]


def test_five_minutes_on_an_unchanged_list_costs_a_conditional_get_and_no_body(
    holder: SearchIndexHolder, bucket: InMemorySearchIndexSource, clock: Clock
) -> None:
    bucket.append_suppression(suppression(source_of(ALONE, 0)))
    found(holder)
    clock.advance(POINTER_RECHECK_INTERVAL)
    found(holder)

    assert bucket.reads.count(SUPPRESSION_LIST_KEY) == 2
    assert bucket.suppression_not_modified == 1
    assert found(holder) == [SHARED]


def test_with_no_list_in_the_bucket_nothing_is_hidden(holder: SearchIndexHolder) -> None:
    assert found(holder) == [SHARED, ALONE]


# ------------------------------------------------------------------------------------------------
# A list that cannot be read is never served stale
# ------------------------------------------------------------------------------------------------


def test_a_list_that_cannot_be_read_refuses_the_request_and_the_next_one_tries_again(
    holder: SearchIndexHolder, bucket: InMemorySearchIndexSource, clock: Clock
) -> None:
    assert found(holder) == [SHARED, ALONE]
    bucket.append_suppression(suppression(source_of(ALONE, 0)))
    bucket.suppression_list_failure = OUTAGE
    clock.advance(POINTER_RECHECK_INTERVAL)

    assert isinstance(unavailable_because(holder), SuppressionListUnavailable)
    assert isinstance(unavailable_because(holder), SuppressionListUnavailable)
    assert bucket.reads.count(SUPPRESSION_LIST_KEY) == 3

    bucket.suppression_list_failure = None
    assert found(holder) == [SHARED]


def test_a_list_that_cannot_be_read_at_the_first_request_loads_no_index(
    holder: SearchIndexHolder, bucket: InMemorySearchIndexSource
) -> None:
    bucket.suppression_list_failure = OUTAGE

    assert isinstance(unavailable_because(holder), SuppressionListUnavailable)
    assert holder.loaded_index_id is None


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(b'{"schema_version":1,"action":"SUPPRESS"}\n', id="a line that is not an entry"),
        pytest.param(suppression("ab" * 32).to_line().encode(), id="a last line with no newline"),
        pytest.param(b"\xff\xfe\n", id="bytes that are not UTF-8"),
    ],
)
def test_a_list_holding_a_line_this_build_cannot_read_is_refused_whole(
    holder: SearchIndexHolder,
    bucket: InMemorySearchIndexSource,
    clock: Clock,
    body: bytes,
    caplog: pytest.LogCaptureFixture,
) -> None:
    found(holder)
    bucket.write_suppression_list(suppression(source_of(ALONE, 0)).to_line().encode() + b"\n" + body)
    clock.advance(POINTER_RECHECK_INTERVAL)

    with caplog.at_level(logging.WARNING, logger="debate_core.application.search_index_holder"):
        assert isinstance(unavailable_because(holder), SuppressionListUnavailable)

    logged = " ".join(record.getMessage() for record in caplog.records)
    assert "suppression list was not read" in logged
    assert source_of(ALONE, 0) not in logged
    assert "RM-2026-01" not in logged


def test_closing_the_holder_forgets_the_list_so_the_next_lease_reads_it_whole(
    holder: SearchIndexHolder, bucket: InMemorySearchIndexSource
) -> None:
    bucket.append_suppression(suppression(source_of(ALONE, 0)))
    found(holder)
    holder.close()

    assert found(holder) == [SHARED]
    assert bucket.suppression_not_modified == 0


def test_the_interval_is_the_pointers_five_minutes() -> None:
    assert POINTER_RECHECK_INTERVAL == timedelta(minutes=5)
