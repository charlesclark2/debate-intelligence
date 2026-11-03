"""What the index holder tells the app log: load times, sizes on `/tmp`, search times (`v1-e39-t10`).

ac5: the operator reads the cold-start index load, the query time (p50, p95) and the peak `/tmp` use
across one index replacement from the app log. These tests hold the two `INFO` lines those numbers
come from, word for word, since a CloudWatch Logs Insights `parse` reads them by their words. The
timer is a test's own, so a time is a line of code; the sizes are read from the published fixture's
own bytes, never from the holder.

Every value is synthetic: invented tags, cites, words and the caselist slug `hsld26`.
"""

from __future__ import annotations

import gzip
import logging
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import pytest

from debate_core.application.ports.search_index import IndexedOccurrence, SearchDocument
from debate_core.application.search_index_holder import POINTER_RECHECK_INTERVAL, SearchIndexHolder
from debate_core.integrations.local.search_index import SqliteSearchIndexWriter
from debate_core.integrations.local.search_index_reader import SqliteSearchIndexReader
from debate_core.testing.search_index import InMemorySearchIndexSource, PublishedIndex, published_index

HOLDER_LOGGER: Final = "debate_core.application.search_index_holder"
START: Final = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)
QUERY_WORD: Final = "zephyr"


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


class ScriptedTimer:
    """`time.perf_counter` as a test writes it: each call answers the next reading."""

    def __init__(self, *readings: float) -> None:
        self._readings = list(readings)

    def __call__(self) -> float:
        return self._readings.pop(0)

    @property
    def unread(self) -> int:
        return len(self._readings)


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
                tournament="Invented Invitational",
                round="Round 4",
            ),
        ),
    )


def published(directory: Path, *documents: SearchDocument) -> tuple[PublishedIndex, int]:
    """An index of `documents`, published in memory, and its SQLite file's size as written."""
    directory.mkdir()
    path = directory / "search-index.sqlite"
    sink = SqliteSearchIndexWriter().create(path)
    for one in documents:
        sink.add(one)
    sink.finish()
    sqlite = path.read_bytes()
    return published_index(sqlite, documents_by_store={"hsld26": len(documents)}), len(sqlite)


@pytest.fixture
def bucket() -> InMemorySearchIndexSource:
    return InMemorySearchIndexSource()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def make_holder(
    tmp_path: Path, bucket: InMemorySearchIndexSource, clock: Clock
) -> Iterator[Callable[[ScriptedTimer], SearchIndexHolder]]:
    made: list[SearchIndexHolder] = []

    def make(timer: ScriptedTimer) -> SearchIndexHolder:
        holder = SearchIndexHolder(
            bucket,
            directory=tmp_path / "tub-index",
            open_reader=lambda path, index_id: SqliteSearchIndexReader(path, index_id=index_id),
            clock=clock,
            timer=timer,
        )
        made.append(holder)
        return holder

    yield make
    for holder in made:
        holder.close()


def holder_lines(caplog: pytest.LogCaptureFixture) -> list[tuple[int, str]]:
    return [
        (record.levelno, record.getMessage()) for record in caplog.records if record.name == HOLDER_LOGGER
    ]


def test_a_cold_load_logs_its_time_its_file_and_object_bytes_and_the_directory_total(
    make_holder: Callable[[ScriptedTimer], SearchIndexHolder],
    bucket: InMemorySearchIndexSource,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    index, sqlite_bytes = published(tmp_path / "first", document(1, "zephyr granite"))
    object_bytes = len(index.objects[index.object_key])
    assert len(gzip.decompress(index.objects[index.object_key])) == sqlite_bytes
    bucket.publish(index)
    timer = ScriptedTimer(100.0, 101.25, 200.0, 200.042)
    holder = make_holder(timer)

    with caplog.at_level(logging.INFO, logger=HOLDER_LOGGER), holder.lease() as search:
        search.search(QUERY_WORD)

    assert holder_lines(caplog) == [
        (
            logging.INFO,
            f"search index {index.index_id} loaded in 1.25 s: {sqlite_bytes} bytes from a "
            f"{object_bytes}-byte object; {sqlite_bytes} bytes in its directory",
        ),
        (logging.INFO, "search answered in 42 ms"),
    ]
    assert timer.unread == 0


def test_at_a_replacement_the_directory_total_is_the_peak_both_files_before_the_old_one_goes(
    make_holder: Callable[[ScriptedTimer], SearchIndexHolder],
    bucket: InMemorySearchIndexSource,
    clock: Clock,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """ac5's peak `/tmp` use across one index replacement: A's SQLite file plus B's (v1-e39-t14's working)."""
    first, first_bytes = published(tmp_path / "first", document(1, "zephyr granite"))
    second, second_bytes = published(
        tmp_path / "second", document(1, "zephyr granite"), document(2, "zephyr basalt")
    )
    second_object_bytes = len(second.objects[second.object_key])
    bucket.publish(first)
    holder = make_holder(ScriptedTimer(0.0, 0.5, 1.0, 1.003, 10.0, 12.0, 20.0, 20.0101))
    with holder.lease() as search:
        search.search(QUERY_WORD)

    bucket.publish(second)
    clock.now += POINTER_RECHECK_INTERVAL
    with caplog.at_level(logging.INFO, logger=HOLDER_LOGGER), holder.lease() as search:
        search.search(QUERY_WORD)

    assert holder_lines(caplog) == [
        (
            logging.INFO,
            f"search index {second.index_id} loaded in 2.00 s: {second_bytes} bytes from a "
            f"{second_object_bytes}-byte object; {first_bytes + second_bytes} bytes in its directory",
        ),
        (logging.INFO, f"search index {first.index_id} closed and deleted"),
        (logging.INFO, "search answered in 10 ms"),
    ]
    assert sum(path.stat().st_size for path in (tmp_path / "tub-index").iterdir()) == second_bytes


def test_a_passage_search_logs_its_time_alone_and_no_line_holds_the_query(
    make_holder: Callable[[ScriptedTimer], SearchIndexHolder],
    bucket: InMemorySearchIndexSource,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    index, _ = published(tmp_path / "first", document(1, "zephyr granite basalt"))
    bucket.publish(index)
    holder = make_holder(ScriptedTimer(0.0, 0.1, 5.0, 5.2))

    with caplog.at_level(logging.DEBUG), holder.lease() as search:
        search.search("zephyr granite basalt", passage=True)

    assert holder_lines(caplog)[-1] == (logging.INFO, "search answered in 200 ms")
    logged = " ".join(record.getMessage() for record in caplog.records)
    for word in ("zephyr", "granite", "basalt", "passage", "Maple Grove", "QX", "Lindqvist"):
        assert word not in logged, word


def test_a_lease_that_only_reads_a_card_logs_no_search_time(
    make_holder: Callable[[ScriptedTimer], SearchIndexHolder],
    bucket: InMemorySearchIndexSource,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A card page is not a query, so it is not among the times p50 and p95 are read from."""
    index, _ = published(tmp_path / "first", document(1, "zephyr granite"))
    bucket.publish(index)
    holder = make_holder(ScriptedTimer(0.0, 0.1))
    with holder.lease():
        pass

    with caplog.at_level(logging.INFO, logger=HOLDER_LOGGER), holder.lease() as search:
        assert search.card("hsld26", f"{1:064x}") is not None

    assert holder_lines(caplog) == []
