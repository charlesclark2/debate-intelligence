"""The function's index holder: fetch, check, swap, recheck (`v1-e39-t06`, the PM's ruling of 2026-10-20).

Every index is a real SQLite FTS5 file written by `v1-e39-t02`'s writer and published in memory by
:mod:`debate_core.testing.search_index`, which serves it as the bucket does; nothing reaches a
network. The clock is a test's own, so "five minutes later" is a line of code.

Every value is synthetic: invented tags, cites, words and the caselist slug `hsld26`.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import stat
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

import pytest

from debate_core.application.errors import NotFound, StoreUnavailable
from debate_core.application.ports.search_index import IndexedOccurrence, SearchDocument
from debate_core.application.search_index_holder import (
    POINTER_RECHECK_INTERVAL,
    SearchIndexHolder,
    SearchIndexRefusal,
    SearchIndexRefused,
    SearchIndexUnavailable,
)
from debate_core.domain.search_index import SEARCH_INDEX_POINTER_KEY
from debate_core.integrations.local.search_index import SqliteSearchIndexWriter
from debate_core.integrations.local.search_index_reader import SqliteSearchIndexReader
from debate_core.testing.search_index import InMemorySearchIndexSource, PublishedIndex, published_index

START: Final = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)


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
                tournament="Invented Invitational",
                round="Round 4",
            ),
        ),
    )


def built(directory: Path, *documents: SearchDocument) -> bytes:
    path = directory / "search-index.sqlite"
    sink = SqliteSearchIndexWriter().create(path)
    for one in documents:
        sink.add(one)
    sink.finish()
    return path.read_bytes()


@pytest.fixture(scope="module")
def first_index(tmp_path_factory: pytest.TempPathFactory) -> PublishedIndex:
    sqlite = built(tmp_path_factory.mktemp("first"), document(1, "zephyr granite"))
    return published_index(sqlite, documents_by_store={"hsld26": 1})


@pytest.fixture(scope="module")
def second_index(tmp_path_factory: pytest.TempPathFactory) -> PublishedIndex:
    sqlite = built(
        tmp_path_factory.mktemp("second"), document(1, "zephyr granite"), document(2, "zephyr basalt")
    )
    return published_index(sqlite, documents_by_store={"hsld26": 2})


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


def files_in(holder_directory: Path) -> list[Path]:
    return sorted(holder_directory.iterdir())


def found(holder: SearchIndexHolder, query: str = "zephyr") -> list[int]:
    with holder.lease() as search:
        return [int(hit.cluster_id, 16) for hit in search.search(query).hits]


def refusal_of(holder: SearchIndexHolder) -> SearchIndexRefusal:
    with pytest.raises(SearchIndexUnavailable) as raised, holder.lease():
        pass
    cause = raised.value.__cause__
    assert isinstance(cause, SearchIndexRefused), repr(cause)
    return cause.refusal


def repointed(index: PublishedIndex, **changes: object) -> bytes:
    pointer = json.loads(index.pointer)
    pointer.update(changes)
    return json.dumps(pointer).encode()


# ------------------------------------------------------------------------------------------------
# The first request that needs the index
# ------------------------------------------------------------------------------------------------


def test_the_first_lease_reads_the_pointer_then_the_manifest_then_streams_the_object(
    make_holder: Callable[[], SearchIndexHolder],
    bucket: InMemorySearchIndexSource,
    first_index: PublishedIndex,
) -> None:
    bucket.publish(first_index)
    holder = make_holder()
    assert bucket.reads == []
    assert holder.loaded_index_id is None

    assert found(holder) == [1]

    assert bucket.reads == [SEARCH_INDEX_POINTER_KEY, first_index.manifest_key, first_index.object_key]
    assert holder.loaded_index_id == first_index.index_id
    assert holder.loaded_caselists() == ("hsld26",)


def test_the_checked_file_is_read_only_and_opened_read_only_and_immutable(
    tmp_path: Path, bucket: InMemorySearchIndexSource, clock: Clock, first_index: PublishedIndex
) -> None:
    bucket.publish(first_index)
    opened: list[tuple[Path, str]] = []

    def open_reader(path: Path, index_id: str) -> SqliteSearchIndexReader:
        opened.append((path, index_id))
        return SqliteSearchIndexReader(path, index_id=index_id)

    holder = SearchIndexHolder(bucket, directory=tmp_path / "tub-index", open_reader=open_reader, clock=clock)
    try:
        found(holder)
        [(path, index_id)] = opened
        assert index_id == first_index.index_id
        assert path.parent == tmp_path / "tub-index" and path.name.startswith(first_index.index_id)
        assert stat.S_IMODE(path.stat().st_mode) == 0o444
        assert hashlib.sha256(path.read_bytes()).hexdigest() == first_index.manifest.sqlite_file.sha256
    finally:
        holder.close()


def test_loaded_caselists_never_fetches_so_the_empty_search_page_never_waits(
    make_holder: Callable[[], SearchIndexHolder],
    bucket: InMemorySearchIndexSource,
    first_index: PublishedIndex,
) -> None:
    bucket.publish(first_index)
    holder = make_holder()

    assert holder.loaded_caselists() == ()
    assert bucket.reads == []


def test_with_nothing_published_a_lease_is_refused_as_unavailable(
    make_holder: Callable[[], SearchIndexHolder], bucket: InMemorySearchIndexSource
) -> None:
    holder = make_holder()

    with pytest.raises(SearchIndexUnavailable) as raised, holder.lease():
        pass

    assert isinstance(raised.value.__cause__, NotFound)


def test_with_no_index_loaded_every_lease_tries_again(
    make_holder: Callable[[], SearchIndexHolder],
    bucket: InMemorySearchIndexSource,
    first_index: PublishedIndex,
) -> None:
    holder = make_holder()
    with pytest.raises(SearchIndexUnavailable), holder.lease():
        pass

    bucket.publish(first_index)

    assert found(holder) == [1]


# ------------------------------------------------------------------------------------------------
# Refusals: digests, the format version, the manifest, the gzip stream
# ------------------------------------------------------------------------------------------------


def test_an_object_whose_digest_is_not_the_pointers_is_refused_and_deleted(
    make_holder: Callable[[], SearchIndexHolder],
    bucket: InMemorySearchIndexSource,
    first_index: PublishedIndex,
    tmp_path: Path,
) -> None:
    damaged = bytearray(first_index.objects[first_index.object_key])
    damaged[len(damaged) // 2] ^= 0x01
    bucket.publish(first_index.with_object(bytes(damaged)))
    holder = make_holder()

    assert refusal_of(holder) in {
        SearchIndexRefusal.OBJECT_DIGEST_MISMATCH,
        SearchIndexRefusal.UNREADABLE_OBJECT,
    }
    assert files_in(tmp_path / "tub-index") == []


def test_an_object_that_inflates_to_another_file_is_refused_on_the_sqlite_digest(
    make_holder: Callable[[], SearchIndexHolder],
    bucket: InMemorySearchIndexSource,
    first_index: PublishedIndex,
    second_index: PublishedIndex,
    tmp_path: Path,
) -> None:
    """The object's own digest matches (the pointer is re-signed for it); what it inflates to does not."""
    other = second_index.objects[second_index.object_key]
    sqlite_size = len(gzip.decompress(other))
    manifest = first_index.manifest.model_copy(
        update={
            "gzip_object": first_index.manifest.gzip_object.model_copy(
                update={"bytes": len(other), "sha256": hashlib.sha256(other).hexdigest()}
            ),
            "sqlite_file": first_index.manifest.sqlite_file.model_copy(update={"bytes": sqlite_size}),
        }
    )
    manifest_bytes = manifest.to_json_bytes()
    bucket.objects[first_index.manifest_key] = manifest_bytes
    bucket.objects[first_index.object_key] = other
    bucket.write_pointer(
        repointed(
            first_index,
            manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
            object_sha256=hashlib.sha256(other).hexdigest(),
        )
    )
    holder = make_holder()

    assert refusal_of(holder) is SearchIndexRefusal.INDEX_DIGEST_MISMATCH
    assert files_in(tmp_path / "tub-index") == []


def test_a_manifest_whose_digest_is_not_the_pointers_is_refused_before_the_object_is_fetched(
    make_holder: Callable[[], SearchIndexHolder],
    bucket: InMemorySearchIndexSource,
    first_index: PublishedIndex,
) -> None:
    bucket.publish(first_index)
    bucket.objects[first_index.manifest_key] += b" "
    holder = make_holder()

    assert refusal_of(holder) is SearchIndexRefusal.MANIFEST_DIGEST_MISMATCH
    assert first_index.object_key not in bucket.reads


def test_a_pointer_of_an_unknown_format_version_is_refused_before_anything_else_is_read(
    make_holder: Callable[[], SearchIndexHolder], bucket: InMemorySearchIndexSource, tmp_path: Path
) -> None:
    sqlite = built(tmp_path, document(1, "zephyr granite"))
    bucket.publish(published_index(sqlite, documents_by_store={"hsld26": 1}, format_version=3))
    holder = make_holder()

    assert refusal_of(holder) is SearchIndexRefusal.UNKNOWN_FORMAT_VERSION
    assert bucket.reads == [SEARCH_INDEX_POINTER_KEY]


def test_a_manifest_of_an_unknown_format_version_is_refused(
    make_holder: Callable[[], SearchIndexHolder], bucket: InMemorySearchIndexSource, tmp_path: Path
) -> None:
    sqlite = built(tmp_path, document(1, "zephyr granite"))
    index = published_index(sqlite, documents_by_store={"hsld26": 1}, manifest_format_version=3)
    bucket.publish(index)
    holder = make_holder()

    assert refusal_of(holder) is SearchIndexRefusal.UNKNOWN_FORMAT_VERSION
    assert index.object_key not in bucket.reads


def test_a_manifest_that_names_another_object_than_the_pointer_is_refused(
    make_holder: Callable[[], SearchIndexHolder],
    bucket: InMemorySearchIndexSource,
    first_index: PublishedIndex,
    second_index: PublishedIndex,
) -> None:
    bucket.publish(first_index)
    bucket.write_pointer(repointed(first_index, object_sha256=second_index.manifest.gzip_object.sha256))
    holder = make_holder()

    assert refusal_of(holder) is SearchIndexRefusal.MANIFEST_DISAGREES


@pytest.mark.parametrize(
    "changes",
    [
        {"object_key": "reports/tub/search/elsewhere/search-index.sqlite.gz"},
        {"manifest_key": "manifests/_suppression/suppression-list.jsonl"},
        {"index_id": "not-an-index-id"},
        {"sqlite_sha256": "f" * 64},
    ],
    ids=["object elsewhere", "manifest elsewhere", "malformed index id", "id is not the digest's start"],
)
def test_a_pointer_naming_keys_outside_its_own_index_is_refused_unread(
    make_holder: Callable[[], SearchIndexHolder],
    bucket: InMemorySearchIndexSource,
    first_index: PublishedIndex,
    changes: dict[str, object],
) -> None:
    bucket.publish(first_index)
    bucket.write_pointer(repointed(first_index, **changes))
    holder = make_holder()

    assert refusal_of(holder) is SearchIndexRefusal.UNREADABLE_POINTER
    assert bucket.reads == [SEARCH_INDEX_POINTER_KEY]


def test_a_pointer_that_is_not_a_pointer_is_refused(
    make_holder: Callable[[], SearchIndexHolder], bucket: InMemorySearchIndexSource
) -> None:
    bucket.write_pointer(b"{not json")
    holder = make_holder()

    assert refusal_of(holder) is SearchIndexRefusal.UNREADABLE_POINTER


def test_an_object_cut_short_is_refused(
    make_holder: Callable[[], SearchIndexHolder],
    bucket: InMemorySearchIndexSource,
    first_index: PublishedIndex,
    tmp_path: Path,
) -> None:
    whole = first_index.objects[first_index.object_key]
    bucket.publish(first_index.with_object(whole[: len(whole) // 2]))
    holder = make_holder()

    assert refusal_of(holder) is SearchIndexRefusal.UNREADABLE_OBJECT
    assert files_in(tmp_path / "tub-index") == []


def test_bytes_after_the_gzip_stream_are_refused(
    make_holder: Callable[[], SearchIndexHolder],
    bucket: InMemorySearchIndexSource,
    first_index: PublishedIndex,
    tmp_path: Path,
) -> None:
    """The object's size is the manifest's, so the count check alone would not catch it."""
    whole = first_index.objects[first_index.object_key]
    sqlite = gzip.decompress(whole)
    shorter = gzip.compress(sqlite, compresslevel=9, mtime=0)
    assert len(shorter) < len(whole)
    padded = shorter + b"\x00" * (len(whole) - len(shorter))
    bucket.publish(first_index.with_object(padded))
    holder = make_holder()

    assert refusal_of(holder) is SearchIndexRefusal.UNREADABLE_OBJECT
    assert files_in(tmp_path / "tub-index") == []


def test_an_object_that_inflates_past_the_manifests_size_stops_there(
    make_holder: Callable[[], SearchIndexHolder],
    bucket: InMemorySearchIndexSource,
    first_index: PublishedIndex,
    tmp_path: Path,
) -> None:
    """A small object of zeros that inflates far beyond the file the manifest names is cut off."""
    bomb = gzip.compress(b"\x00" * (8 * 1024 * 1024), compresslevel=9, mtime=0)
    manifest = first_index.manifest.model_copy(
        update={
            "gzip_object": first_index.manifest.gzip_object.model_copy(
                update={"bytes": len(bomb), "sha256": hashlib.sha256(bomb).hexdigest()}
            )
        }
    )
    manifest_bytes = manifest.to_json_bytes()
    bucket.objects[first_index.manifest_key] = manifest_bytes
    bucket.objects[first_index.object_key] = bomb
    bucket.write_pointer(
        repointed(
            first_index,
            manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
            object_sha256=hashlib.sha256(bomb).hexdigest(),
        )
    )
    holder = make_holder()

    assert refusal_of(holder) is SearchIndexRefusal.INDEX_DIGEST_MISMATCH
    assert files_in(tmp_path / "tub-index") == []


def test_a_file_that_checks_out_but_is_no_index_is_refused_by_the_reader(
    make_holder: Callable[[], SearchIndexHolder], bucket: InMemorySearchIndexSource, tmp_path: Path
) -> None:
    bucket.publish(published_index(b"SQLite format 3\x00 but not really", documents_by_store={"hsld26": 1}))
    holder = make_holder()

    assert refusal_of(holder) is SearchIndexRefusal.UNREADABLE_INDEX
    assert files_in(tmp_path / "tub-index") == []


def test_a_refused_pointer_is_not_fetched_again_until_it_changes(
    make_holder: Callable[[], SearchIndexHolder],
    bucket: InMemorySearchIndexSource,
    first_index: PublishedIndex,
    clock: Clock,
) -> None:
    damaged = bytearray(first_index.objects[first_index.object_key])
    damaged[-12] ^= 0x01
    bucket.publish(first_index.with_object(bytes(damaged)))
    holder = make_holder()
    refusal_of(holder)
    fetched = bucket.reads.count(first_index.object_key)

    clock.advance(POINTER_RECHECK_INTERVAL)
    refusal_of(holder)

    assert bucket.reads.count(first_index.object_key) == fetched
    assert bucket.not_modified == 1

    bucket.publish(first_index)
    assert found(holder) == [1]


# ------------------------------------------------------------------------------------------------
# Freshness: the conditional GET, the five minutes, the swap
# ------------------------------------------------------------------------------------------------


def test_within_five_minutes_no_request_reads_the_pointer_again(
    make_holder: Callable[[], SearchIndexHolder],
    bucket: InMemorySearchIndexSource,
    first_index: PublishedIndex,
    clock: Clock,
) -> None:
    bucket.publish(first_index)
    holder = make_holder()
    found(holder)

    clock.advance(POINTER_RECHECK_INTERVAL - timedelta(seconds=1))
    found(holder)

    assert bucket.reads.count(SEARCH_INDEX_POINTER_KEY) == 1


def test_five_minutes_on_the_pointer_is_read_by_conditional_get_and_an_unchanged_one_costs_no_body(
    make_holder: Callable[[], SearchIndexHolder],
    bucket: InMemorySearchIndexSource,
    first_index: PublishedIndex,
    clock: Clock,
) -> None:
    bucket.publish(first_index)
    holder = make_holder()
    found(holder)

    clock.advance(POINTER_RECHECK_INTERVAL)
    found(holder)

    assert bucket.reads == [
        SEARCH_INDEX_POINTER_KEY,
        first_index.manifest_key,
        first_index.object_key,
        SEARCH_INDEX_POINTER_KEY,
    ]
    assert bucket.not_modified == 1


def test_an_environment_frozen_past_five_minutes_rechecks_before_it_answers(
    make_holder: Callable[[], SearchIndexHolder],
    bucket: InMemorySearchIndexSource,
    first_index: PublishedIndex,
    second_index: PublishedIndex,
    clock: Clock,
) -> None:
    """A new index published while the environment was frozen answers its first request after it."""
    bucket.publish(first_index)
    holder = make_holder()
    assert found(holder) == [1]

    bucket.publish(second_index)
    clock.advance(timedelta(hours=3))

    assert sorted(found(holder)) == [1, 2]
    assert holder.loaded_index_id == second_index.index_id


def test_a_new_pointer_is_fetched_to_a_new_path_swapped_in_and_the_old_file_deleted(
    make_holder: Callable[[], SearchIndexHolder],
    bucket: InMemorySearchIndexSource,
    first_index: PublishedIndex,
    second_index: PublishedIndex,
    clock: Clock,
    tmp_path: Path,
) -> None:
    bucket.publish(first_index)
    holder = make_holder()
    found(holder)
    [old_file] = files_in(tmp_path / "tub-index")
    old_bytes = old_file.read_bytes()

    bucket.publish(second_index)
    clock.advance(POINTER_RECHECK_INTERVAL)
    assert sorted(found(holder)) == [1, 2]

    [new_file] = files_in(tmp_path / "tub-index")
    assert new_file != old_file and not old_file.exists()
    assert new_file.name.startswith(second_index.index_id)
    assert hashlib.sha256(old_bytes).hexdigest() == first_index.manifest.sqlite_file.sha256


def test_an_index_swapped_out_under_a_request_is_deleted_when_that_request_ends(
    make_holder: Callable[[], SearchIndexHolder],
    bucket: InMemorySearchIndexSource,
    first_index: PublishedIndex,
    second_index: PublishedIndex,
    clock: Clock,
    tmp_path: Path,
) -> None:
    bucket.publish(first_index)
    holder = make_holder()
    with holder.lease() as before:
        [old_file] = files_in(tmp_path / "tub-index")
        bucket.publish(second_index)
        clock.advance(POINTER_RECHECK_INTERVAL)
        with holder.lease() as after:
            assert len(files_in(tmp_path / "tub-index")) == 2
            assert [hit.cluster_id for hit in before.search("basalt").hits] == []
            assert len(after.search("basalt").hits) == 1
        assert old_file.exists()
    assert not old_file.exists()
    assert len(files_in(tmp_path / "tub-index")) == 1


def test_a_failed_recheck_keeps_the_current_index_serving_and_waits_an_interval(
    make_holder: Callable[[], SearchIndexHolder],
    bucket: InMemorySearchIndexSource,
    first_index: PublishedIndex,
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bucket.publish(first_index)
    holder = make_holder()
    found(holder)

    def unavailable(*, if_none_match: str | None) -> object:
        bucket.reads.append("pointer refused")
        raise StoreUnavailable("GetObject", "s3://synthetic/reports/tub/search/current.json", "synthetic")

    monkeypatch.setattr(bucket, "read_pointer", unavailable)
    clock.advance(POINTER_RECHECK_INTERVAL)
    assert found(holder) == [1]
    clock.advance(timedelta(minutes=1))
    assert found(holder) == [1]

    assert bucket.reads.count("pointer refused") == 1


def test_a_refused_new_index_leaves_the_current_one_serving(
    make_holder: Callable[[], SearchIndexHolder],
    bucket: InMemorySearchIndexSource,
    first_index: PublishedIndex,
    second_index: PublishedIndex,
    clock: Clock,
    tmp_path: Path,
) -> None:
    bucket.publish(first_index)
    holder = make_holder()
    found(holder)
    [current_file] = files_in(tmp_path / "tub-index")

    bucket.publish(second_index.with_object(first_index.objects[first_index.object_key]))
    clock.advance(POINTER_RECHECK_INTERVAL)

    assert found(holder) == [1]
    assert holder.loaded_index_id == first_index.index_id
    assert files_in(tmp_path / "tub-index") == [current_file]


def test_the_same_index_republished_is_not_fetched_again(
    make_holder: Callable[[], SearchIndexHolder],
    bucket: InMemorySearchIndexSource,
    first_index: PublishedIndex,
    clock: Clock,
) -> None:
    bucket.publish(first_index)
    holder = make_holder()
    found(holder)

    bucket.publish(first_index)
    clock.advance(POINTER_RECHECK_INTERVAL)
    found(holder)

    assert bucket.reads.count(first_index.object_key) == 1


def test_a_clock_that_runs_backwards_rechecks_rather_than_trusting_the_last_check(
    make_holder: Callable[[], SearchIndexHolder],
    bucket: InMemorySearchIndexSource,
    first_index: PublishedIndex,
    clock: Clock,
) -> None:
    bucket.publish(first_index)
    holder = make_holder()
    found(holder)

    clock.advance(-timedelta(minutes=1))
    found(holder)

    assert bucket.reads.count(SEARCH_INDEX_POINTER_KEY) == 2


def test_files_a_previous_process_left_are_deleted_when_a_holder_starts(
    tmp_path: Path, bucket: InMemorySearchIndexSource, clock: Clock
) -> None:
    directory = tmp_path / "tub-index"
    directory.mkdir()
    (directory / "0123456789abcdef-old.sqlite").write_bytes(b"left over")
    (directory / "0123456789abcdef-old.part").write_bytes(b"left over")
    (directory / "unrelated.txt").write_bytes(b"kept")

    SearchIndexHolder(
        bucket,
        directory=directory,
        open_reader=lambda path, index_id: SqliteSearchIndexReader(path, index_id=index_id),
        clock=clock,
    )

    assert [path.name for path in files_in(directory)] == ["unrelated.txt"]


def test_the_recheck_comes_five_minutes_on_as_adr_0019_sets_it(
    make_holder: Callable[[], SearchIndexHolder],
    bucket: InMemorySearchIndexSource,
    first_index: PublishedIndex,
    clock: Clock,
) -> None:
    """Written in minutes, not through the constant, so a changed interval fails here."""
    bucket.publish(first_index)
    holder = make_holder()
    found(holder)

    clock.advance(timedelta(minutes=4, seconds=59))
    found(holder)
    assert bucket.reads.count(SEARCH_INDEX_POINTER_KEY) == 1

    clock.advance(timedelta(seconds=1))
    found(holder)
    assert bucket.reads.count(SEARCH_INDEX_POINTER_KEY) == 2
