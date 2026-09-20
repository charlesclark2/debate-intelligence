"""The in-memory CaselistRepository really behaves the way the port says it does.

The point of these tests is the cumulative-archive arithmetic. OpenCaselist republishes every
disclosed file every week, so an importer asks the repository the same questions over and over —
have I seen this hash, which snapshots was it up in, what is the latest archive I have — and a
fake that answered them loosely would let v1-e30-t03's dedupe counts pass here and be wrong in
production. The SQLite adapter in t03 is held to the same expectations.
"""

from __future__ import annotations

from collections.abc import Coroutine
from datetime import date
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
from debate_core.testing import InMemoryCaselistRepository, build_fake_caselist_repository

SEPTEMBER_FIRST = date(2026, 9, 1)
SEPTEMBER_EIGHTH = date(2026, 9, 8)
SEPTEMBER_FIFTEENTH = date(2026, 9, 15)

ARCHIVE_SHA256 = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"


def run[ResultT](coroutine: Coroutine[Any, Any, ResultT]) -> ResultT:
    """Drive one coroutine to completion without an event loop.

    The same helper the other fake tests use: the fakes never await anything, so a single
    `send(None)` runs one to completion, and a fake that suspended would be doing real I/O.
    `asyncio.run` is avoided because it opens a socket pair and the suite runs `--disable-socket`.
    """
    try:
        coroutine.send(None)
    except StopIteration as stopped:
        return cast("ResultT", stopped.value)
    coroutine.close()
    raise AssertionError("an in-memory fake suspended; fakes must not perform real I/O")


def hash_for(label: str) -> str:
    """A distinct, readable 64-character hex digest, so a failure names the file it is about."""
    stem = "".join(character for character in label.lower() if character in "0123456789abcdef")
    if not stem:
        stem = "a"
    return (stem * 64)[:64]


AFF_HASH = hash_for("aff")
NEG_HASH = hash_for("be")
CAMP_HASH = hash_for("cafe")


def make_snapshot(snapshot: date = SEPTEMBER_FIRST, **overrides: object) -> ArchiveSnapshot:
    fields: dict[str, object] = {
        "caselist": "hsld26",
        "snapshot": snapshot,
        "archive_sha256": ARCHIVE_SHA256,
        "acquisition": Acquisition.MANUAL_DOWNLOAD,
        "file_count": 100,
    }
    fields.update(overrides)
    return ArchiveSnapshot.model_validate(fields)


def make_source(
    sha256: str = AFF_HASH, snapshot: date = SEPTEMBER_FIRST, **overrides: object
) -> SourceDocument:
    fields: dict[str, object] = {
        "sha256": sha256,
        "byte_size": 1024,
        "source_format": SourceFormat.DOCX,
        "origin": SourceOrigin.CASELIST_ARCHIVE,
        "caselist": "hsld26",
        "first_seen_snapshot": snapshot,
        "last_seen_snapshot": snapshot,
    }
    fields.update(overrides)
    return SourceDocument.model_validate(fields)


def make_disclosure(
    *,
    sha256: str = AFF_HASH,
    snapshot: date = SEPTEMBER_FIRST,
    school: str = "Northside Academy",
    team_code: str = "RiOs",
    side: Side = Side.AFF,
    source_path: str | None = None,
    **overrides: object,
) -> Disclosure:
    fields: dict[str, object] = {
        "source_sha256": sha256,
        "caselist": "hsld26",
        "snapshot": snapshot,
        "event": Event.LD,
        "school": school,
        "team_code": team_code,
        "side": side,
        "tournament": "Glenbrooks",
        "round_label": RoundLabel.from_raw("R3"),
        "source_path": source_path or f"{school}/{team_code}/{school}-{team_code}-{side}-Glenbrooks-R3.docx",
    }
    fields.update(overrides)
    return Disclosure.model_validate(fields)


def make_camp_file(
    *, sha256: str = CAMP_HASH, title: str = "Water Infrastructure Aff", **overrides: object
) -> CampFile:
    fields: dict[str, object] = {
        "source_sha256": sha256,
        "camp": "DDI",
        "year": 2026,
        "event": Event.POLICY,
        "file_title": title,
        "snapshot": SEPTEMBER_FIRST,
    }
    fields.update(overrides)
    return CampFile.model_validate(fields)


@pytest.fixture
def repository() -> InMemoryCaselistRepository:
    return InMemoryCaselistRepository()


# --------------------------------------------------------------------------------------------
# Conformance
# --------------------------------------------------------------------------------------------


def test_the_fake_satisfies_the_port_at_runtime_and_statically() -> None:
    """`build_fake_caselist_repository` is annotated as the Protocol, so pyright checks it too."""
    port: CaselistRepository = build_fake_caselist_repository()
    assert isinstance(port, CaselistRepository)


def test_the_port_is_a_runtime_checkable_protocol() -> None:
    assert getattr(CaselistRepository, "_is_protocol", False)
    assert getattr(CaselistRepository, "_is_runtime_protocol", False)


# --------------------------------------------------------------------------------------------
# Archive snapshots
# --------------------------------------------------------------------------------------------


def test_a_snapshot_is_stored_and_read_back(repository: InMemoryCaselistRepository) -> None:
    stored = run(repository.upsert_snapshot(make_snapshot()))
    assert stored == run(repository.get_snapshot("hsld26", SEPTEMBER_FIRST))


def test_upserting_the_same_snapshot_replaces_it_rather_than_duplicating_it(
    repository: InMemoryCaselistRepository,
) -> None:
    run(repository.upsert_snapshot(make_snapshot(file_count=100)))
    run(repository.upsert_snapshot(make_snapshot(file_count=101)))
    assert run(repository.get_snapshot("hsld26", SEPTEMBER_FIRST)).file_count == 101
    assert len(run(repository.list_snapshots("hsld26"))) == 1


def test_getting_a_snapshot_that_was_never_imported_raises_not_found(
    repository: InMemoryCaselistRepository,
) -> None:
    with pytest.raises(NotFound) as raised:
        run(repository.get_snapshot("hsld26", SEPTEMBER_FIRST))
    assert raised.value.entity == "ArchiveSnapshot"
    assert raised.value.key == "hsld26/2026-09-01"


def test_finding_a_snapshot_that_was_never_imported_returns_none(
    repository: InMemoryCaselistRepository,
) -> None:
    assert run(repository.find_snapshot("hsld26", SEPTEMBER_FIRST)) is None


def test_the_latest_snapshot_is_the_newest_by_date_not_by_insertion_order(
    repository: InMemoryCaselistRepository,
) -> None:
    run(repository.upsert_snapshot(make_snapshot(SEPTEMBER_EIGHTH)))
    run(repository.upsert_snapshot(make_snapshot(SEPTEMBER_FIRST)))
    run(repository.upsert_snapshot(make_snapshot(SEPTEMBER_FIFTEENTH)))
    latest = run(repository.latest_snapshot("hsld26"))
    assert latest is not None
    assert latest.snapshot == SEPTEMBER_FIFTEENTH


def test_the_latest_snapshot_of_an_unimported_caselist_is_none(
    repository: InMemoryCaselistRepository,
) -> None:
    run(repository.upsert_snapshot(make_snapshot()))
    assert run(repository.latest_snapshot("hspf26")) is None


def test_snapshots_list_newest_first_and_only_for_their_own_caselist(
    repository: InMemoryCaselistRepository,
) -> None:
    run(repository.upsert_snapshot(make_snapshot(SEPTEMBER_FIRST)))
    run(repository.upsert_snapshot(make_snapshot(SEPTEMBER_FIFTEENTH)))
    run(repository.upsert_snapshot(make_snapshot(SEPTEMBER_EIGHTH, caselist="hspf26")))
    assert [stored.snapshot for stored in run(repository.list_snapshots("hsld26"))] == [
        SEPTEMBER_FIFTEENTH,
        SEPTEMBER_FIRST,
    ]


# --------------------------------------------------------------------------------------------
# Source documents: the cumulative-archive arithmetic
# --------------------------------------------------------------------------------------------


def test_a_source_is_stored_and_found_by_its_hash(repository: InMemoryCaselistRepository) -> None:
    stored = run(repository.put_source(make_source()))
    assert run(repository.get_source(AFF_HASH)) == stored
    assert run(repository.find_source(AFF_HASH)) == stored


def test_an_unknown_hash_is_not_found_and_finding_it_returns_none(
    repository: InMemoryCaselistRepository,
) -> None:
    with pytest.raises(NotFound) as raised:
        run(repository.get_source(AFF_HASH))
    assert raised.value.entity == "SourceDocument"
    assert run(repository.find_source(AFF_HASH)) is None


def test_a_file_seen_in_a_later_archive_widens_its_snapshot_range(
    repository: InMemoryCaselistRepository,
) -> None:
    run(repository.put_source(make_source(snapshot=SEPTEMBER_FIRST)))
    run(repository.put_source(make_source(snapshot=SEPTEMBER_EIGHTH)))
    widened = run(repository.put_source(make_source(snapshot=SEPTEMBER_FIFTEENTH)))
    assert widened.first_seen_snapshot == SEPTEMBER_FIRST
    assert widened.last_seen_snapshot == SEPTEMBER_FIFTEENTH


def test_an_archive_imported_out_of_order_widens_the_range_backwards(
    repository: InMemoryCaselistRepository,
) -> None:
    run(repository.put_source(make_source(snapshot=SEPTEMBER_EIGHTH)))
    widened = run(repository.put_source(make_source(snapshot=SEPTEMBER_FIRST)))
    assert widened.first_seen_snapshot == SEPTEMBER_FIRST
    assert widened.last_seen_snapshot == SEPTEMBER_EIGHTH


def test_storing_the_same_source_twice_stores_one_record(
    repository: InMemoryCaselistRepository,
) -> None:
    run(repository.put_source(make_source()))
    run(repository.put_source(make_source()))
    assert len(run(repository.list_sources()).items) == 1


def test_two_different_files_cannot_be_filed_under_one_hash(
    repository: InMemoryCaselistRepository,
) -> None:
    run(repository.put_source(make_source(byte_size=1024)))
    with pytest.raises(Conflict, match="already stored"):
        run(repository.put_source(make_source(byte_size=2048)))


def test_a_changed_format_is_a_conflict_not_an_overwrite(
    repository: InMemoryCaselistRepository,
) -> None:
    run(repository.put_source(make_source()))
    with pytest.raises(Conflict):
        run(repository.put_source(make_source(source_format=SourceFormat.PDF)))


def test_a_changed_origin_is_a_conflict_not_an_overwrite(
    repository: InMemoryCaselistRepository,
) -> None:
    run(repository.put_source(make_source()))
    with pytest.raises(Conflict):
        run(repository.put_source(make_source(origin=SourceOrigin.OPENEV, caselist=None)))


def test_sources_are_listed_for_the_snapshot_they_were_present_in(
    repository: InMemoryCaselistRepository,
) -> None:
    run(
        repository.put_source(
            make_source(sha256=AFF_HASH, snapshot=SEPTEMBER_FIRST).evolve(
                last_seen_snapshot=SEPTEMBER_FIFTEENTH
            )
        )
    )
    run(repository.put_source(make_source(sha256=NEG_HASH, snapshot=SEPTEMBER_FIRST)))
    present_later = run(repository.list_sources(snapshot=SEPTEMBER_FIFTEENTH))
    assert [source.sha256 for source in present_later.items] == [AFF_HASH]
    present_at_first = run(repository.list_sources(snapshot=SEPTEMBER_FIRST))
    assert {source.sha256 for source in present_at_first.items} == {AFF_HASH, NEG_HASH}


def test_sources_can_be_listed_for_one_caselist(repository: InMemoryCaselistRepository) -> None:
    run(repository.put_source(make_source(sha256=AFF_HASH)))
    run(repository.put_source(make_source(sha256=NEG_HASH, caselist="hspf26")))
    listed = run(repository.list_sources(caselist="hspf26"))
    assert [source.sha256 for source in listed.items] == [NEG_HASH]


def test_sources_list_newest_snapshot_first_then_by_hash(
    repository: InMemoryCaselistRepository,
) -> None:
    run(repository.put_source(make_source(sha256=AFF_HASH, snapshot=SEPTEMBER_FIRST)))
    run(repository.put_source(make_source(sha256=NEG_HASH, snapshot=SEPTEMBER_FIFTEENTH)))
    listed = run(repository.list_sources())
    assert [source.sha256 for source in listed.items] == [NEG_HASH, AFF_HASH]


# --------------------------------------------------------------------------------------------
# Disclosures
# --------------------------------------------------------------------------------------------


def test_a_disclosure_is_recorded_and_listed(repository: InMemoryCaselistRepository) -> None:
    recorded = run(repository.record_disclosure(make_disclosure()))
    assert run(repository.list_disclosures()).items == (recorded,)


def test_recording_the_same_disclosure_twice_records_one(
    repository: InMemoryCaselistRepository,
) -> None:
    run(repository.record_disclosure(make_disclosure()))
    run(repository.record_disclosure(make_disclosure()))
    assert len(run(repository.list_disclosures()).items) == 1


def test_one_file_disclosed_under_two_paths_is_two_disclosures(
    repository: InMemoryCaselistRepository,
) -> None:
    run(repository.record_disclosure(make_disclosure(source_path="Northside/RiOs/a.docx")))
    run(repository.record_disclosure(make_disclosure(source_path="Northside/RiOs/a (1).docx")))
    listed = run(repository.list_disclosures(source_sha256=AFF_HASH))
    assert len(listed.items) == 2


def test_disclosures_can_be_listed_by_caselist_snapshot_school_and_team(
    repository: InMemoryCaselistRepository,
) -> None:
    run(repository.record_disclosure(make_disclosure()))
    run(repository.record_disclosure(make_disclosure(school="Eastview", team_code="LeCh")))
    run(repository.record_disclosure(make_disclosure(snapshot=SEPTEMBER_EIGHTH)))

    assert len(run(repository.list_disclosures(caselist="hsld26")).items) == 3
    assert len(run(repository.list_disclosures(caselist="hspf26")).items) == 0
    assert len(run(repository.list_disclosures(snapshot=SEPTEMBER_EIGHTH)).items) == 1
    assert len(run(repository.list_disclosures(school="Eastview")).items) == 1
    assert len(run(repository.list_disclosures(team_code="RiOs")).items) == 2
    assert len(run(repository.list_disclosures(school="Eastview", team_code="RiOs")).items) == 0


def test_disclosures_list_newest_snapshot_first_then_by_path(
    repository: InMemoryCaselistRepository,
) -> None:
    run(repository.record_disclosure(make_disclosure(source_path="b.docx")))
    run(repository.record_disclosure(make_disclosure(source_path="a.docx")))
    run(repository.record_disclosure(make_disclosure(snapshot=SEPTEMBER_EIGHTH, source_path="z.docx")))
    listed = run(repository.list_disclosures())
    assert [item.source_path for item in listed.items] == ["z.docx", "a.docx", "b.docx"]


# --------------------------------------------------------------------------------------------
# Camp files
# --------------------------------------------------------------------------------------------


def test_a_camp_file_is_recorded_and_listed(repository: InMemoryCaselistRepository) -> None:
    recorded = run(repository.record_camp_file(make_camp_file()))
    assert run(repository.list_camp_files()).items == (recorded,)


def test_recording_the_same_camp_file_twice_records_one(
    repository: InMemoryCaselistRepository,
) -> None:
    run(repository.record_camp_file(make_camp_file()))
    run(repository.record_camp_file(make_camp_file(title="Water Infrastructure Aff")))
    assert len(run(repository.list_camp_files()).items) == 1


def test_camp_files_can_be_filtered_by_camp_year_event_and_hash(
    repository: InMemoryCaselistRepository,
) -> None:
    run(repository.record_camp_file(make_camp_file()))
    run(repository.record_camp_file(make_camp_file(sha256=AFF_HASH, camp="Michigan", title="Cap K")))
    run(repository.record_camp_file(make_camp_file(sha256=NEG_HASH, year=2025, title="Old File")))

    assert len(run(repository.list_camp_files(camp="Michigan")).items) == 1
    assert len(run(repository.list_camp_files(year=2026)).items) == 2
    assert len(run(repository.list_camp_files(event=Event.POLICY)).items) == 3
    assert len(run(repository.list_camp_files(event=Event.LD)).items) == 0
    assert len(run(repository.list_camp_files(source_sha256=AFF_HASH)).items) == 1


def test_a_file_in_both_a_caselist_and_a_camp_release_keeps_one_source_document(
    repository: InMemoryCaselistRepository,
) -> None:
    """Cross-origin dedupe: the bytes are stored once, and both records point at the same hash."""
    run(repository.put_source(make_source(sha256=AFF_HASH)))
    run(repository.record_disclosure(make_disclosure(sha256=AFF_HASH)))
    run(repository.record_camp_file(make_camp_file(sha256=AFF_HASH)))
    assert len(run(repository.list_sources()).items) == 1
    assert len(run(repository.list_disclosures(source_sha256=AFF_HASH)).items) == 1
    assert len(run(repository.list_camp_files(source_sha256=AFF_HASH)).items) == 1


# --------------------------------------------------------------------------------------------
# Pagination
# --------------------------------------------------------------------------------------------


def test_a_listing_pages_through_every_record_once(repository: InMemoryCaselistRepository) -> None:
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


def test_the_last_page_carries_no_cursor(repository: InMemoryCaselistRepository) -> None:
    run(repository.record_disclosure(make_disclosure()))
    page = run(repository.list_disclosures(limit=10))
    assert page.next_cursor is None
    assert not page.has_more


def test_a_cursor_from_another_listing_is_rejected(repository: InMemoryCaselistRepository) -> None:
    run(repository.record_disclosure(make_disclosure()))
    run(repository.put_source(make_source()))
    source_page = run(repository.list_sources(limit=1))
    with pytest.raises(InvalidCursor):
        run(repository.list_disclosures(cursor=f"caselist-source:{AFF_HASH}"))
    assert source_page.items


def test_a_limit_below_one_is_refused(repository: InMemoryCaselistRepository) -> None:
    with pytest.raises(ValueError, match="limit must be at least 1"):
        run(repository.list_disclosures(limit=0))
