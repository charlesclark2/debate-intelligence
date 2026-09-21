"""The SQLite CaselistRepository behaves exactly as the port and the in-memory fake do.

`packages/debate_core/tests/application/test_caselist_fake_repository.py` says the adapter in
this task "is held to the same expectations", so the cases there are the cases here: the
cumulative-archive arithmetic, the contradictions that are refused, the listing orders and the
cursors. What is added on top is what only a real database can get wrong — that the schema
migrates, that a widening write is one transaction, and that a row which no longer validates is
reported rather than half-built.
"""

from __future__ import annotations

from collections.abc import Coroutine
from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest

from debate_core.application.errors import Conflict, InvalidCursor, NotFound
from debate_core.application.ports import CaselistRepository
from debate_core.domain.caselist import (
    Acquisition,
    ArchiveSnapshot,
    CampFile,
    Disclosure,
    Event,
    RoundLabel,
    Side,
    SourceDocument,
    SourceFormat,
    SourceOrigin,
)
from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository
from debate_core.integrations.local.sqlite_db import SqliteDatabase
from debate_core.integrations.local.sqlite_repos import CorruptRecordError

CASELIST = "testcl26"
OTHER_CASELIST = "testpf26"

SEPTEMBER_FIRST = date(2026, 9, 1)
SEPTEMBER_EIGHTH = date(2026, 9, 8)
SEPTEMBER_FIFTEENTH = date(2026, 9, 15)


def run[ResultT](coroutine: Coroutine[Any, Any, ResultT]) -> ResultT:
    """Drive one already-synchronous adapter coroutine to its result.

    The adapter does its SQLite work without awaiting, exactly as the other local repositories do,
    so a coroutine here is always finished on its first step and needs no event loop.
    """
    try:
        coroutine.send(None)
    except StopIteration as finished:
        return cast("ResultT", finished.value)
    raise AssertionError("the SQLite adapter awaited something; it is not supposed to")


def hash_for(label: str) -> str:
    """A digest-shaped identifier a test can name, e.g. `hash_for("aff")`."""
    import hashlib

    return hashlib.sha256(label.encode()).hexdigest()


AFF_HASH = hash_for("aff")
NEG_HASH = hash_for("neg")
THIRD_HASH = hash_for("third")


@pytest.fixture
def repository(tmp_path: Path) -> SqliteCaselistRepository:
    """A repository on a freshly migrated database in this test's own directory."""
    return SqliteCaselistRepository(SqliteDatabase.open(tmp_path / "store"))


def make_snapshot(snapshot: date = SEPTEMBER_FIRST, **overrides: object) -> ArchiveSnapshot:
    fields: dict[str, object] = {
        "caselist": CASELIST,
        "snapshot": snapshot,
        "archive_sha256": hash_for(f"archive-{snapshot.isoformat()}"),
        "acquisition": Acquisition.MANUAL_DOWNLOAD,
        "file_count": 4,
    }
    fields.update(overrides)
    return ArchiveSnapshot.model_validate(fields)


def make_source(sha256: str = AFF_HASH, **overrides: object) -> SourceDocument:
    fields: dict[str, object] = {
        "sha256": sha256,
        "byte_size": 1024,
        "source_format": SourceFormat.DOCX,
        "origin": SourceOrigin.CASELIST_ARCHIVE,
        "caselist": CASELIST,
        "first_seen_snapshot": SEPTEMBER_FIRST,
        "last_seen_snapshot": SEPTEMBER_FIRST,
    }
    fields.update(overrides)
    return SourceDocument.model_validate(fields)


def make_disclosure(**overrides: object) -> Disclosure:
    fields: dict[str, object] = {
        "source_sha256": AFF_HASH,
        "caselist": CASELIST,
        "snapshot": SEPTEMBER_FIRST,
        "event": Event.LD,
        "school": "Maple Grove",
        "team_code": "QX",
        "side": Side.AFF,
        "tournament": "Grove City Invitational",
        "round_label": RoundLabel.from_raw("Round 1"),
        "source_path": "Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1.docx",
    }
    fields.update(overrides)
    return Disclosure.model_validate(fields)


def make_camp_file(**overrides: object) -> CampFile:
    fields: dict[str, object] = {
        "source_sha256": AFF_HASH,
        "camp": "Northgate Institute",
        "year": 2026,
        "event": Event.LD,
        "file_title": "Autonomy Affirmative",
        "snapshot": SEPTEMBER_FIRST,
    }
    fields.update(overrides)
    return CampFile.model_validate(fields)


# ------------------------------------------------------------------------------------------------
# It is the port
# ------------------------------------------------------------------------------------------------


def test_the_adapter_satisfies_the_port_at_runtime_and_statically(
    repository: SqliteCaselistRepository,
) -> None:
    port: CaselistRepository = repository

    assert isinstance(repository, CaselistRepository)
    assert port is repository


def test_opening_a_database_migrates_the_caselist_schema(tmp_path: Path) -> None:
    """Migration 2 is applied by the same `SqliteDatabase.open` every command already calls."""
    with SqliteDatabase.open(tmp_path / "store") as database:
        tables = {
            cast("str", row["name"])
            for row in database.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

        assert {
            "caselist_snapshots",
            "caselist_sources",
            "caselist_disclosures",
            "caselist_camp_files",
        } <= tables
        assert database.schema_version() >= 2


def test_opening_the_same_database_twice_applies_nothing_the_second_time(tmp_path: Path) -> None:
    with SqliteDatabase.open(tmp_path / "store") as first:
        version = first.schema_version()
    with SqliteDatabase.open(tmp_path / "store") as second:
        assert second.schema_version() == version


# ------------------------------------------------------------------------------------------------
# Archive snapshots
# ------------------------------------------------------------------------------------------------


def test_a_snapshot_is_stored_and_read_back(repository: SqliteCaselistRepository) -> None:
    stored = run(repository.upsert_snapshot(make_snapshot()))

    assert run(repository.get_snapshot(CASELIST, SEPTEMBER_FIRST)) == stored


def test_upserting_the_same_snapshot_replaces_it_rather_than_duplicating_it(
    repository: SqliteCaselistRepository,
) -> None:
    """What makes an interrupted import safe to run again."""
    run(repository.upsert_snapshot(make_snapshot(file_count=4)))
    run(repository.upsert_snapshot(make_snapshot(file_count=9)))

    assert len(run(repository.list_snapshots(CASELIST))) == 1
    assert run(repository.get_snapshot(CASELIST, SEPTEMBER_FIRST)).file_count == 9


def test_getting_a_snapshot_that_was_never_imported_raises_not_found(
    repository: SqliteCaselistRepository,
) -> None:
    with pytest.raises(NotFound):
        run(repository.get_snapshot(CASELIST, SEPTEMBER_FIRST))


def test_finding_a_snapshot_that_was_never_imported_returns_none(
    repository: SqliteCaselistRepository,
) -> None:
    assert run(repository.find_snapshot(CASELIST, SEPTEMBER_FIRST)) is None


def test_the_latest_snapshot_is_the_newest_by_date_not_by_insertion_order(
    repository: SqliteCaselistRepository,
) -> None:
    """The importer refuses an older archive by reading this, so insertion order must not decide."""
    run(repository.upsert_snapshot(make_snapshot(SEPTEMBER_FIFTEENTH)))
    run(repository.upsert_snapshot(make_snapshot(SEPTEMBER_FIRST)))

    latest = run(repository.latest_snapshot(CASELIST))

    assert latest is not None
    assert latest.snapshot == SEPTEMBER_FIFTEENTH


def test_the_latest_snapshot_of_an_unimported_caselist_is_none(
    repository: SqliteCaselistRepository,
) -> None:
    assert run(repository.latest_snapshot(CASELIST)) is None


def test_snapshots_list_newest_first_and_only_for_their_own_caselist(
    repository: SqliteCaselistRepository,
) -> None:
    run(repository.upsert_snapshot(make_snapshot(SEPTEMBER_FIRST)))
    run(repository.upsert_snapshot(make_snapshot(SEPTEMBER_FIFTEENTH)))
    run(repository.upsert_snapshot(make_snapshot(SEPTEMBER_EIGHTH, caselist=OTHER_CASELIST)))

    listed = run(repository.list_snapshots(CASELIST))

    assert [stored.snapshot for stored in listed] == [SEPTEMBER_FIFTEENTH, SEPTEMBER_FIRST]


# ------------------------------------------------------------------------------------------------
# Source documents: the cumulative-archive arithmetic
# ------------------------------------------------------------------------------------------------


def test_a_source_is_stored_and_found_by_its_hash(repository: SqliteCaselistRepository) -> None:
    stored = run(repository.put_source(make_source()))

    assert run(repository.find_source(AFF_HASH)) == stored
    assert run(repository.get_source(AFF_HASH)) == stored


def test_an_unknown_hash_is_not_found_and_finding_it_returns_none(
    repository: SqliteCaselistRepository,
) -> None:
    assert run(repository.find_source(AFF_HASH)) is None
    with pytest.raises(NotFound):
        run(repository.get_source(AFF_HASH))


def test_a_file_seen_in_a_later_archive_widens_its_snapshot_range(
    repository: SqliteCaselistRepository,
) -> None:
    run(repository.put_source(make_source()))

    widened = run(
        repository.put_source(
            make_source(first_seen_snapshot=SEPTEMBER_EIGHTH, last_seen_snapshot=SEPTEMBER_EIGHTH)
        )
    )

    assert widened.first_seen_snapshot == SEPTEMBER_FIRST
    assert widened.last_seen_snapshot == SEPTEMBER_EIGHTH


def test_an_archive_imported_out_of_order_widens_the_range_backwards(
    repository: SqliteCaselistRepository,
) -> None:
    """The range is the answer to "which weeks was this up?", so it must not depend on write order."""
    run(
        repository.put_source(
            make_source(first_seen_snapshot=SEPTEMBER_EIGHTH, last_seen_snapshot=SEPTEMBER_EIGHTH)
        )
    )

    widened = run(repository.put_source(make_source()))

    assert widened.first_seen_snapshot == SEPTEMBER_FIRST
    assert widened.last_seen_snapshot == SEPTEMBER_EIGHTH


def test_storing_the_same_source_twice_stores_one_record(
    repository: SqliteCaselistRepository,
) -> None:
    run(repository.put_source(make_source()))
    run(repository.put_source(make_source()))

    assert len(run(repository.list_sources()).items) == 1


def test_two_different_files_cannot_be_filed_under_one_hash(
    repository: SqliteCaselistRepository,
) -> None:
    run(repository.put_source(make_source()))

    with pytest.raises(Conflict):
        run(repository.put_source(make_source(byte_size=2048)))


def test_a_changed_format_is_a_conflict_not_an_overwrite(
    repository: SqliteCaselistRepository,
) -> None:
    run(repository.put_source(make_source()))

    with pytest.raises(Conflict):
        run(repository.put_source(make_source(source_format=SourceFormat.PDF)))


def test_a_changed_origin_is_a_conflict_not_an_overwrite(
    repository: SqliteCaselistRepository,
) -> None:
    run(repository.put_source(make_source()))

    with pytest.raises(Conflict):
        run(repository.put_source(make_source(origin=SourceOrigin.OPENEV, caselist=None)))


def test_a_refused_contradiction_leaves_the_stored_record_exactly_as_it_was(
    repository: SqliteCaselistRepository,
) -> None:
    """The widening read and write are one transaction, so a refusal writes nothing."""
    original = run(repository.put_source(make_source()))

    with pytest.raises(Conflict):
        run(repository.put_source(make_source(byte_size=2048, last_seen_snapshot=SEPTEMBER_FIFTEENTH)))

    assert run(repository.get_source(AFF_HASH)) == original


def test_sources_are_listed_for_the_snapshot_they_were_present_in(
    repository: SqliteCaselistRepository,
) -> None:
    """Present means the seen range covers that week, not that the week is an endpoint."""
    run(repository.put_source(make_source(last_seen_snapshot=SEPTEMBER_FIFTEENTH)))
    run(
        repository.put_source(
            make_source(
                NEG_HASH,
                first_seen_snapshot=SEPTEMBER_FIFTEENTH,
                last_seen_snapshot=SEPTEMBER_FIFTEENTH,
            )
        )
    )

    middle = run(repository.list_sources(snapshot=SEPTEMBER_EIGHTH))

    assert [source.sha256 for source in middle.items] == [AFF_HASH]


def test_sources_can_be_listed_for_one_caselist(repository: SqliteCaselistRepository) -> None:
    run(repository.put_source(make_source()))
    run(repository.put_source(make_source(NEG_HASH, caselist=OTHER_CASELIST)))

    assert [source.sha256 for source in run(repository.list_sources(caselist=CASELIST)).items] == [AFF_HASH]


def test_sources_list_newest_snapshot_first_then_by_hash(
    repository: SqliteCaselistRepository,
) -> None:
    run(repository.put_source(make_source(AFF_HASH)))
    run(repository.put_source(make_source(NEG_HASH, last_seen_snapshot=SEPTEMBER_FIFTEENTH)))
    run(repository.put_source(make_source(THIRD_HASH, last_seen_snapshot=SEPTEMBER_FIFTEENTH)))

    listed = [source.sha256 for source in run(repository.list_sources()).items]

    assert listed[0] in {NEG_HASH, THIRD_HASH}
    assert listed[-1] == AFF_HASH
    assert listed[:2] == sorted([NEG_HASH, THIRD_HASH])


# ------------------------------------------------------------------------------------------------
# Disclosures
# ------------------------------------------------------------------------------------------------


def test_a_disclosure_is_recorded_and_listed(repository: SqliteCaselistRepository) -> None:
    recorded = run(repository.record_disclosure(make_disclosure()))

    assert run(repository.list_disclosures()).items == (recorded,)


def test_recording_the_same_disclosure_twice_records_one(
    repository: SqliteCaselistRepository,
) -> None:
    run(repository.record_disclosure(make_disclosure()))
    run(repository.record_disclosure(make_disclosure()))

    assert len(run(repository.list_disclosures()).items) == 1


def test_one_file_disclosed_under_two_paths_is_two_disclosures(
    repository: SqliteCaselistRepository,
) -> None:
    """The shape a re-upload takes: one source document, two things said about it."""
    run(repository.record_disclosure(make_disclosure()))
    run(repository.record_disclosure(make_disclosure(source_path="Maple Grove/QX/copy (1).docx")))

    listed = run(repository.list_disclosures(source_sha256=AFF_HASH))

    assert len(listed.items) == 2
    assert {item.source_sha256 for item in listed.items} == {AFF_HASH}


def test_disclosures_can_be_listed_by_caselist_snapshot_school_and_team(
    repository: SqliteCaselistRepository,
) -> None:
    run(repository.record_disclosure(make_disclosure()))
    run(
        repository.record_disclosure(
            make_disclosure(
                school="Cedar Hollow",
                team_code="ZaLu",
                source_path="Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-Aff-Harbor Classic.docx",
            )
        )
    )

    assert len(run(repository.list_disclosures(school="Maple Grove")).items) == 1
    assert len(run(repository.list_disclosures(team_code="ZaLu")).items) == 1
    assert len(run(repository.list_disclosures(snapshot=SEPTEMBER_FIRST)).items) == 2
    assert len(run(repository.list_disclosures(caselist=OTHER_CASELIST)).items) == 0
    assert len(run(repository.list_disclosures(school="Maple Grove", team_code="ZaLu")).items) == 0


def test_disclosures_list_newest_snapshot_first_then_by_path(
    repository: SqliteCaselistRepository,
) -> None:
    run(repository.record_disclosure(make_disclosure(source_path="b.docx")))
    run(repository.record_disclosure(make_disclosure(source_path="a.docx")))
    run(repository.record_disclosure(make_disclosure(snapshot=SEPTEMBER_FIFTEENTH, source_path="z.docx")))

    listed = [item.source_path for item in run(repository.list_disclosures()).items]

    assert listed == ["z.docx", "a.docx", "b.docx"]


# ------------------------------------------------------------------------------------------------
# Camp files
# ------------------------------------------------------------------------------------------------


def test_a_camp_file_is_recorded_and_listed(repository: SqliteCaselistRepository) -> None:
    recorded = run(repository.record_camp_file(make_camp_file()))

    assert run(repository.list_camp_files()).items == (recorded,)


def test_recording_the_same_camp_file_twice_records_one(
    repository: SqliteCaselistRepository,
) -> None:
    run(repository.record_camp_file(make_camp_file()))
    run(repository.record_camp_file(make_camp_file(camp="Cedar Hollow Institute")))

    listed = run(repository.list_camp_files()).items

    assert len(listed) == 1
    assert listed[0].camp == "Cedar Hollow Institute"


def test_camp_files_can_be_filtered_by_camp_year_event_and_hash(
    repository: SqliteCaselistRepository,
) -> None:
    run(repository.record_camp_file(make_camp_file()))
    run(
        repository.record_camp_file(
            make_camp_file(
                source_sha256=NEG_HASH,
                event=Event.PF,
                camp="Cedar Hollow Institute",
                file_title="Grid Negative",
            )
        )
    )

    assert len(run(repository.list_camp_files(event=Event.LD)).items) == 1
    assert len(run(repository.list_camp_files(year=2026)).items) == 2
    assert len(run(repository.list_camp_files(camp="Northgate Institute")).items) == 1
    assert len(run(repository.list_camp_files(source_sha256=NEG_HASH)).items) == 1


def test_a_file_in_both_a_caselist_and_a_camp_release_keeps_one_source_document(
    repository: SqliteCaselistRepository,
) -> None:
    """How E31 and E32 can see that a disclosed card came out of a camp file."""
    run(repository.put_source(make_source()))
    run(repository.record_disclosure(make_disclosure()))
    run(repository.record_camp_file(make_camp_file()))

    assert len(run(repository.list_sources()).items) == 1
    assert run(repository.list_disclosures(source_sha256=AFF_HASH)).items
    assert run(repository.list_camp_files(source_sha256=AFF_HASH)).items


# ------------------------------------------------------------------------------------------------
# Paging
# ------------------------------------------------------------------------------------------------


def test_a_listing_pages_through_every_record_once(repository: SqliteCaselistRepository) -> None:
    for index in range(5):
        run(repository.record_disclosure(make_disclosure(source_path=f"file-{index}.docx")))

    seen: list[str] = []
    cursor: str | None = None
    while True:
        page = run(repository.list_disclosures(limit=2, cursor=cursor))
        seen.extend(item.source_path for item in page.items)
        if not page.has_more:
            break
        cursor = page.next_cursor

    assert seen == [f"file-{index}.docx" for index in range(5)]


def test_the_last_page_carries_no_cursor(repository: SqliteCaselistRepository) -> None:
    run(repository.record_disclosure(make_disclosure()))

    page = run(repository.list_disclosures(limit=10))

    assert page.next_cursor is None
    assert not page.has_more


def test_a_cursor_from_another_listing_is_rejected(repository: SqliteCaselistRepository) -> None:
    """Rejected, not silently treated as "start from the beginning" — the fake's rule exactly."""
    run(repository.record_disclosure(make_disclosure()))
    run(repository.put_source(make_source()))

    with pytest.raises(InvalidCursor):
        run(repository.list_disclosures(cursor=f"caselist-source:{AFF_HASH}"))


def test_a_cursor_naming_a_row_that_is_gone_is_rejected(
    repository: SqliteCaselistRepository,
) -> None:
    with pytest.raises(InvalidCursor):
        run(repository.list_disclosures(cursor="disclosure:testcl26|2026-09-01|vanished.docx"))


def test_sources_page_with_their_own_cursor_kind(repository: SqliteCaselistRepository) -> None:
    for index in range(3):
        run(repository.put_source(make_source(hash_for(f"source-{index}"))))

    first = run(repository.list_sources(limit=2))

    assert first.next_cursor is not None
    assert first.next_cursor.startswith("caselist-source:")
    assert len(run(repository.list_sources(limit=2, cursor=first.next_cursor)).items) == 1


@pytest.mark.parametrize("limit", [0, -1])
def test_a_limit_below_one_is_refused(repository: SqliteCaselistRepository, limit: int) -> None:
    with pytest.raises(ValueError, match="limit must be at least 1"):
        run(repository.list_disclosures(limit=limit))


# ------------------------------------------------------------------------------------------------
# A row that is no longer readable
# ------------------------------------------------------------------------------------------------


def test_a_stored_row_that_no_longer_validates_is_reported_rather_than_half_built(
    tmp_path: Path,
) -> None:
    """Only reachable by hand-editing or a failing disk, and reported either way.

    The same rule the article and card repositories follow: a record the platform cannot read is
    raised as :class:`CorruptRecordError`, never returned as a partly-populated object that a
    manifest or a report would then be built from.
    """
    database = SqliteDatabase.open(tmp_path / "store")
    repository = SqliteCaselistRepository(database)
    run(repository.put_source(make_source()))
    with database.transaction() as connection:
        connection.execute(
            "UPDATE caselist_sources SET document = ? WHERE sha256 = ?",
            ('{"sha256": "not-a-digest"}', AFF_HASH),
        )

    with pytest.raises(CorruptRecordError):
        run(repository.get_source(AFF_HASH))
