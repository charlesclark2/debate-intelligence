"""The index holder through the move from index format 1 to format 2 (`v1-e39-t13` ac4).

The PM's ruling of 2026-10-23: the function is deployed before the first format 2 index is published,
so it reads both. On format 1 a plain search runs and says its words are matched as written, and a
passage search says it is unavailable until the next weekly update; any other format is refused with
a message, never by failing queries. So deploying the function first cannot take search down.

Each index is a real SQLite file built by the running writer, and `format_one_index` turns it into
the format 1 file of the same rows. Expected values are written by hand. Every value is synthetic.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

import pytest

from debate_core.application.ports.search_index import IndexedOccurrence, SearchDocument
from debate_core.application.search_index_holder import (
    POINTER_RECHECK_INTERVAL,
    SearchIndexHolder,
    SearchIndexRefusal,
    SearchIndexRefused,
    SearchIndexUnavailable,
)
from debate_core.domain.evidence_search import SearchNotice
from debate_core.integrations.local.search_index import SqliteSearchIndexWriter
from debate_core.integrations.local.search_index_reader import SqliteSearchIndexReader
from debate_core.testing.search_index import (
    InMemorySearchIndexSource,
    PublishedIndex,
    format_one_index,
    published_index,
)

START: Final = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)
PASSAGE: Final = "The granite tariffs, and the zephyr"
"""Three content words, so a card must hold two."""


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


def document(doc_id: int, words: str) -> SearchDocument:
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
        file_count=1,
        team_count=1,
        occurrences=(
            IndexedOccurrence(
                ordinal=0,
                caselist="hsld26",
                source_sha256=f"{doc_id:064x}"[::-1],
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


def built(directory: Path) -> bytes:
    path = directory / "search-index.sqlite"
    sink = SqliteSearchIndexWriter().create(path)
    for one in (
        document(1, "zephyr granite tariff"),
        document(2, "zephyr granite tariffs"),
        document(3, "x y"),
    ):
        sink.add(one)
    sink.finish()
    return path.read_bytes()


@pytest.fixture(scope="module")
def format_two_sqlite(tmp_path_factory: pytest.TempPathFactory) -> bytes:
    return built(tmp_path_factory.mktemp("format-two"))


@pytest.fixture(scope="module")
def format_two(format_two_sqlite: bytes) -> PublishedIndex:
    return published_index(format_two_sqlite, documents_by_store={"hsld26": 3})


@pytest.fixture(scope="module")
def format_one(format_two_sqlite: bytes) -> PublishedIndex:
    return published_index(
        format_one_index(format_two_sqlite), documents_by_store={"hsld26": 3}, format_version=1
    )


@pytest.fixture
def bucket() -> InMemorySearchIndexSource:
    return InMemorySearchIndexSource()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def make_holder(
    tmp_path: Path, bucket: InMemorySearchIndexSource, clock: Clock
) -> Iterator[Callable[[], SearchIndexHolder]]:
    made: list[SearchIndexHolder] = []

    def make() -> SearchIndexHolder:
        holder = SearchIndexHolder(
            bucket,
            directory=tmp_path / "tub-index",
            open_reader=lambda path, index_id: SqliteSearchIndexReader(path, index_id=index_id),
            clock=clock,
        )
        made.append(holder)
        return holder

    yield make
    for holder in made:
        holder.close()


def search(
    holder: SearchIndexHolder, query: str, *, passage: bool = False
) -> tuple[list[int], tuple[SearchNotice, ...]]:
    with holder.lease() as screened:
        page = screened.search(query, passage=passage)
    return [int(hit.cluster_id, 16) for hit in page.hits], page.notices


def refused(holder: SearchIndexHolder) -> SearchIndexRefused:
    with pytest.raises(SearchIndexUnavailable) as raised, holder.lease():
        pass
    cause = raised.value.__cause__
    assert isinstance(cause, SearchIndexRefused), repr(cause)
    return cause


def test_holder_serves_a_format_one_index_and_says_what_it_cannot_do(
    make_holder: Callable[[], SearchIndexHolder],
    bucket: InMemorySearchIndexSource,
    format_one: PublishedIndex,
) -> None:
    bucket.publish(format_one)
    holder = make_holder()

    assert search(holder, "tariff") == ([1], (SearchNotice.WORD_FORMS_UNAVAILABLE,))
    assert search(holder, PASSAGE, passage=True) == ([], (SearchNotice.PASSAGE_UNAVAILABLE,))
    assert holder.loaded_index_id == format_one.index_id


def test_holder_serves_a_format_two_index_with_stems_and_passages(
    make_holder: Callable[[], SearchIndexHolder],
    bucket: InMemorySearchIndexSource,
    format_two: PublishedIndex,
) -> None:
    bucket.publish(format_two)
    holder = make_holder()

    hits, notices = search(holder, "tariff")
    assert (sorted(hits), notices) == ([1, 2], ())
    hits, notices = search(holder, PASSAGE, passage=True)
    assert (sorted(hits), notices) == ([1, 2], ())


def test_holder_moves_from_format_one_to_format_two_when_the_weekly_update_publishes_it(
    make_holder: Callable[[], SearchIndexHolder],
    bucket: InMemorySearchIndexSource,
    clock: Clock,
    format_one: PublishedIndex,
    format_two: PublishedIndex,
) -> None:
    bucket.publish(format_one)
    holder = make_holder()
    assert search(holder, PASSAGE, passage=True) == ([], (SearchNotice.PASSAGE_UNAVAILABLE,))

    bucket.publish(format_two)
    clock.advance(POINTER_RECHECK_INTERVAL)
    hits, notices = search(holder, PASSAGE, passage=True)
    assert (sorted(hits), notices) == ([1, 2], ())
    assert holder.loaded_index_id == format_two.index_id


def test_holder_refuses_a_format_it_does_not_read_with_a_message(
    make_holder: Callable[[], SearchIndexHolder], bucket: InMemorySearchIndexSource, format_two_sqlite: bytes
) -> None:
    bucket.publish(published_index(format_two_sqlite, documents_by_store={"hsld26": 3}, format_version=3))
    holder = make_holder()

    refusal = refused(holder)
    assert refusal.refusal is SearchIndexRefusal.UNKNOWN_FORMAT_VERSION
    assert str(refusal).endswith("was refused: its format version is not one this build reads, 1 or 2")


def test_holder_keeps_serving_when_a_format_it_does_not_read_is_published(
    make_holder: Callable[[], SearchIndexHolder],
    bucket: InMemorySearchIndexSource,
    clock: Clock,
    format_two: PublishedIndex,
    format_two_sqlite: bytes,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A newer format published before the function that reads it: the loaded index goes on serving."""
    bucket.publish(format_two)
    holder = make_holder()
    assert sorted(search(holder, "tariff")[0]) == [1, 2]

    bucket.publish(published_index(format_two_sqlite, documents_by_store={"hsld26": 3}, format_version=3))
    clock.advance(POINTER_RECHECK_INTERVAL)
    with caplog.at_level(logging.WARNING, logger="debate_core.application.search_index_holder"):
        hits, notices = search(holder, "tariff")
    assert (sorted(hits), notices) == ([1, 2], ())
    assert holder.loaded_index_id == format_two.index_id
    assert any(
        "its format version is not one this build reads, 1 or 2" in one.getMessage() for one in caplog.records
    )
    assert all("tariff" not in one.getMessage() for one in caplog.records), "no query text in any log line"


@pytest.mark.parametrize(("pointer", "manifest"), [(1, 2), (2, 1)])
def test_holder_refuses_a_pointer_and_manifest_that_name_different_formats(
    make_holder: Callable[[], SearchIndexHolder],
    bucket: InMemorySearchIndexSource,
    format_two_sqlite: bytes,
    pointer: int,
    manifest: int,
) -> None:
    bucket.publish(
        published_index(
            format_two_sqlite,
            documents_by_store={"hsld26": 3},
            format_version=pointer,
            manifest_format_version=manifest,
        )
    )
    assert refused(make_holder()).refusal is SearchIndexRefusal.MANIFEST_DISAGREES


def test_holder_refuses_a_file_of_another_format_than_its_manifest_names(
    make_holder: Callable[[], SearchIndexHolder],
    bucket: InMemorySearchIndexSource,
    format_two_sqlite: bytes,
    tmp_path: Path,
) -> None:
    """A format 2 file published as format 1: the digests check out and the file's own version does not."""
    bucket.publish(published_index(format_two_sqlite, documents_by_store={"hsld26": 3}, format_version=1))
    holder = make_holder()

    assert refused(holder).refusal is SearchIndexRefusal.UNREADABLE_INDEX
    assert list((tmp_path / "tub-index").iterdir()) == [], "the refused file is deleted"
