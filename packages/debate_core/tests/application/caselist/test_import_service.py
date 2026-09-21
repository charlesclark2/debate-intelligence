"""Importing the three synthetic archives in order produces exactly the expected summary.

This is ac2 and ac3, and the assertion is `tests/fixtures/caselist/expected_summary.json` — counts
a person worked out from the fixture's own tables, not counts derived from running the importer.
When the two disagree, one of them is wrong and this test says so.

Everything runs against a real `FsSnapshotStore` in `tmp_path` and a real
`SqliteCaselistRepository`, not against fakes. The deduplication only means anything if the blob
store really does write one file per distinct digest, and that is precisely what the fakes would
paper over.
"""

from __future__ import annotations

from collections.abc import Coroutine, Iterable
from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest
from tests.fixtures.caselist.build_synthetic_archives import (
    DOCUMENT_BODIES,
    EXPECTED_SNAPSHOTS,
    SNAPSHOTS,
    SYNTHETIC_CASELIST,
    SYNTHETIC_EVENT,
    build_snapshot_directories,
    build_snapshot_zips,
)

from debate_core.application.caselist.import_service import (
    CaselistImportService,
    Classification,
    ImportReport,
    SnapshotOutOfOrder,
)
from debate_core.application.ports.archive import ArchiveEntry, ArchiveMember, SkipReason
from debate_core.domain.caselist import Disclosure, Event, Side, SourceFormat
from debate_core.integrations.local.archive_reader import archive_digest, read_archive
from debate_core.integrations.local.fs_blob_store import BLOB_DIRECTORY, FsSnapshotStore
from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository
from debate_core.integrations.local.sqlite_db import SqliteDatabase

EVENT = Event(SYNTHETIC_EVENT)
GENEROUS_LIMITS = {"max_archive_bytes": 64 * 1024 * 1024, "max_unpacked_bytes": 64 * 1024 * 1024}


def run[ResultT](coroutine: Coroutine[Any, Any, ResultT]) -> ResultT:
    """Drive one already-synchronous service coroutine to its result.

    Every port it awaits is a local adapter that does its work without awaiting, so the coroutine
    is finished on its first step and needs no event loop.
    """
    try:
        coroutine.send(None)
    except StopIteration as finished:
        return cast("ResultT", finished.value)
    raise AssertionError("the import service awaited something that was not already finished")


class ImportHarness:
    """One data directory, one store, one repository, and the archives to import into them."""

    def __init__(self, root: Path) -> None:
        self.data_dir = root / "data"
        self.database = SqliteDatabase.open(self.data_dir)
        self.caselists = SqliteCaselistRepository(self.database)
        self.blobs = FsSnapshotStore(self.data_dir)
        self.service = CaselistImportService(caselists=self.caselists, blobs=self.blobs)
        self.zips = build_snapshot_zips(root / "zips")
        self.directories = build_snapshot_directories(root / "directories")

    def entries(self, snapshot: date, *, as_directory: bool = False) -> Iterable[ArchiveEntry]:
        source = self.directories[snapshot] if as_directory else self.zips[snapshot]
        return read_archive(source, **GENEROUS_LIMITS)

    def digest(self, snapshot: date, *, as_directory: bool = False) -> str:
        source = self.directories[snapshot] if as_directory else self.zips[snapshot]
        return archive_digest(source)

    def import_one(self, snapshot: date, *, as_directory: bool = False, **options: Any) -> ImportReport:
        return run(
            self.service.import_archive(
                self.entries(snapshot, as_directory=as_directory),
                caselist=SYNTHETIC_CASELIST,
                snapshot=snapshot,
                event=EVENT,
                archive_sha256=self.digest(snapshot, as_directory=as_directory),
                **options,
            )
        )

    def import_all(self, *, as_directory: bool = False) -> list[ImportReport]:
        return [self.import_one(snapshot.snapshot, as_directory=as_directory) for snapshot in SNAPSHOTS]

    @property
    def stored_blob_count(self) -> int:
        blobs = self.data_dir / BLOB_DIRECTORY
        return sum(1 for path in blobs.rglob("*") if path.is_file()) if blobs.exists() else 0


@pytest.fixture
def harness(tmp_path: Path) -> ImportHarness:
    return ImportHarness(tmp_path)


def disclosure_at(harness: ImportHarness, snapshot: date, path: str) -> Disclosure:
    """The disclosure one archive recorded at one path.

    The port filters by caselist, snapshot, school, team and source hash but not by path — a path
    is the *key*, not a facet — so the week is listed and the one row picked out here.
    """
    page = run(harness.caselists.list_disclosures(caselist=SYNTHETIC_CASELIST, snapshot=snapshot, limit=1000))
    matching = [item for item in page.items if item.source_path == path]
    assert matching, f"no disclosure at {path} in {snapshot.isoformat()}"
    return matching[0]


# ------------------------------------------------------------------------------------------------
# ac2: the counts, and one blob per distinct file
# ------------------------------------------------------------------------------------------------


def test_the_three_archives_report_exactly_the_expected_counts(harness: ImportHarness) -> None:
    """ac2. Each week's classification counts, against the committed expected summary."""
    reports = harness.import_all()

    for report, expected in zip(reports, EXPECTED_SNAPSHOTS, strict=True):
        assert dict(report.counts) == {
            classification: count
            for classification, count in {
                Classification.NEW: expected.new,
                Classification.UNCHANGED: expected.unchanged,
                Classification.CHANGED: expected.changed,
                Classification.DUPLICATE: expected.duplicate,
                Classification.REMOVED: expected.removed,
                Classification.SUPPRESSED: expected.suppressed,
            }.items()
            if count
        }, expected.snapshot


def test_each_distinct_file_is_stored_exactly_once(harness: ImportHarness) -> None:
    """ac2's other half: blob count equals distinct SHA-256 count, over all three weeks."""
    harness.import_all()

    assert harness.stored_blob_count == len(DOCUMENT_BODIES)
    assert harness.stored_blob_count == EXPECTED_SNAPSHOTS[-1].distinct_sha256_after


def test_the_store_grows_by_exactly_the_new_bodies_each_week(harness: ImportHarness) -> None:
    for expected in EXPECTED_SNAPSHOTS:
        harness.import_one(expected.snapshot)

        assert harness.stored_blob_count == expected.distinct_sha256_after, expected.snapshot


def test_one_source_document_per_distinct_file_not_one_per_appearance(
    harness: ImportHarness,
) -> None:
    """Three cumulative archives, fourteen files: the whole point of the exercise."""
    harness.import_all()

    sources = run(harness.caselists.list_sources(limit=1000))

    assert len(sources.items) == len(DOCUMENT_BODIES)


def test_a_carried_forward_file_widens_its_seen_range_rather_than_repeating(
    harness: ImportHarness,
) -> None:
    harness.import_all()

    disclosures = disclosure_at(
        harness,
        SNAPSHOTS[0].snapshot,
        "Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1.docx",
    )
    source = run(harness.caselists.get_source(disclosures.source_sha256))

    assert source.first_seen_snapshot == SNAPSHOTS[0].snapshot
    assert source.last_seen_snapshot == SNAPSHOTS[-1].snapshot


def test_a_file_taken_down_keeps_the_range_it_was_up_for(harness: ImportHarness) -> None:
    """REMOVED reports the takedown; it does not rewrite history or delete the bytes."""
    harness.import_all()

    octas = disclosure_at(
        harness,
        SNAPSHOTS[1].snapshot,
        "Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-Negative-Harbor Classic-Octas.docx",
    )
    source = run(harness.caselists.get_source(octas.source_sha256))

    assert source.last_seen_snapshot == SNAPSHOTS[1].snapshot
    assert run(harness.blobs.exists(source.sha256))


def test_the_revised_file_and_its_first_version_are_both_kept(harness: ImportHarness) -> None:
    """CHANGED is two pieces of evidence at one path, not an overwrite."""
    harness.import_all()
    path = "Maple Grove/QX/Maple Grove-QX-Neg-Grove City Invitational-Round 2.docx"

    first = disclosure_at(harness, SNAPSHOTS[0].snapshot, path)
    second = disclosure_at(harness, SNAPSHOTS[1].snapshot, path)

    assert first.source_sha256 != second.source_sha256
    assert run(harness.blobs.exists(first.source_sha256))
    assert run(harness.blobs.exists(second.source_sha256))


def test_one_file_under_three_paths_is_one_source_and_three_disclosures(
    harness: ImportHarness,
) -> None:
    """The DUPLICATE shape: a re-upload and another team's copy of one affirmative."""
    harness.import_all()
    original = "Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1.docx"
    digest = disclosure_at(harness, SNAPSHOTS[-1].snapshot, original).source_sha256

    sharing = run(
        harness.caselists.list_disclosures(snapshot=SNAPSHOTS[-1].snapshot, source_sha256=digest, limit=50)
    )

    assert len(sharing.items) == 3
    assert len({item.source_sha256 for item in sharing.items}) == 1


def test_the_skips_match_the_expected_summary(harness: ImportHarness) -> None:
    """ac5's counts, reported by the importer rather than by the reader."""
    reports = harness.import_all()

    for report, expected in zip(reports, EXPECTED_SNAPSHOTS, strict=True):
        assert sum(report.skipped.values()) == expected.skipped_zip, expected.snapshot


def test_the_parse_warnings_match_the_expected_summary(harness: ImportHarness) -> None:
    """ac1's counts, as the import records them on the disclosures it writes."""
    reports = harness.import_all()

    for report, expected in zip(reports, EXPECTED_SNAPSHOTS, strict=True):
        assert report.warning_count == expected.warnings, expected.snapshot


def test_a_disclosure_is_written_for_every_member_that_was_not_skipped(
    harness: ImportHarness,
) -> None:
    for expected in EXPECTED_SNAPSHOTS:
        harness.import_one(expected.snapshot)

        written = run(
            harness.caselists.list_disclosures(
                caselist=SYNTHETIC_CASELIST, snapshot=expected.snapshot, limit=1000
            )
        )
        assert len(written.items) == expected.disclosures, expected.snapshot


def test_importing_from_a_directory_classifies_exactly_as_importing_from_the_zip(
    tmp_path: Path,
) -> None:
    """Which form the operator had is not allowed to change a single count."""
    from_zip = ImportHarness(tmp_path / "zip-run").import_all()
    from_directory = ImportHarness(tmp_path / "directory-run").import_all(as_directory=True)

    for zipped, unpacked in zip(from_zip, from_directory, strict=True):
        assert dict(zipped.counts) == dict(unpacked.counts)


# ------------------------------------------------------------------------------------------------
# ac3: re-import is a no-op, and order is enforced
# ------------------------------------------------------------------------------------------------


def test_re_importing_the_newest_archive_stores_nothing_new(harness: ImportHarness) -> None:
    """ac3's "zero NEW", in the form that is compatible with "identical manifest bytes".

    The classification counts describe this archive against the week *before* it, and that does
    not change because somebody ran the import twice — which is precisely what makes the manifest
    byte-identical. What is zero on a second run is what the run actually wrote.
    """
    harness.import_all()
    first = harness.import_one(SNAPSHOTS[-1].snapshot)

    again = harness.import_one(SNAPSHOTS[-1].snapshot)

    assert first.newly_stored_blobs == 0, "the third import already stored everything"
    assert again.newly_stored_blobs == 0
    assert dict(again.counts) == dict(first.counts)


def test_the_first_import_of_each_week_reports_what_it_stored(harness: ImportHarness) -> None:
    """The other side of it: a first run's newly-stored count is that week's new bodies."""
    grown = 0
    for expected in EXPECTED_SNAPSHOTS:
        report = harness.import_one(expected.snapshot)

        assert report.newly_stored_blobs == expected.distinct_sha256_after - grown, expected.snapshot
        grown = expected.distinct_sha256_after


def test_re_importing_classifies_every_member_exactly_as_the_first_run_did(
    harness: ImportHarness,
) -> None:
    """The property the identical manifest rests on: same entries, same classifications."""
    harness.import_all()
    first = harness.import_one(SNAPSHOTS[-1].snapshot)

    second = harness.import_one(SNAPSHOTS[-1].snapshot)

    assert [(one.path, one.classification, one.sha256) for one in first.entries] == [
        (one.path, one.classification, one.sha256) for one in second.entries
    ]


def test_re_importing_stores_no_further_blobs(harness: ImportHarness) -> None:
    harness.import_all()
    before = harness.stored_blob_count

    harness.import_one(SNAPSHOTS[-1].snapshot)

    assert harness.stored_blob_count == before


def test_an_archive_older_than_the_latest_imported_is_refused(harness: ImportHarness) -> None:
    """ac3. Applying it would run the deduplication backwards."""
    harness.import_one(SNAPSHOTS[-1].snapshot)

    with pytest.raises(SnapshotOutOfOrder) as raised:
        harness.import_one(SNAPSHOTS[0].snapshot)

    assert raised.value.latest == SNAPSHOTS[-1].snapshot
    assert raised.value.snapshot == SNAPSHOTS[0].snapshot


def test_an_older_archive_is_imported_when_it_is_explicitly_allowed(
    harness: ImportHarness,
) -> None:
    harness.import_one(SNAPSHOTS[-1].snapshot)

    report = harness.import_one(SNAPSHOTS[0].snapshot, allow_out_of_order=True)

    assert report.applied


def test_importing_out_of_order_still_widens_a_seen_range_correctly(
    harness: ImportHarness,
) -> None:
    """The range is a fact about the weeks, not about the order somebody imported them in."""
    harness.import_one(SNAPSHOTS[-1].snapshot)
    harness.import_one(SNAPSHOTS[0].snapshot, allow_out_of_order=True)

    disclosures = disclosure_at(
        harness,
        SNAPSHOTS[0].snapshot,
        "Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1.docx",
    )
    source = run(harness.caselists.get_source(disclosures.source_sha256))

    assert source.first_seen_snapshot == SNAPSHOTS[0].snapshot
    assert source.last_seen_snapshot == SNAPSHOTS[-1].snapshot


def test_re_importing_the_same_archive_is_not_out_of_order(harness: ImportHarness) -> None:
    """Equal is not older. A re-run needs no flag."""
    harness.import_one(SNAPSHOTS[0].snapshot)

    assert harness.import_one(SNAPSHOTS[0].snapshot).applied


# ------------------------------------------------------------------------------------------------
# ac6: a dry run writes nothing
# ------------------------------------------------------------------------------------------------


def test_a_dry_run_reports_the_same_counts_as_a_real_one(tmp_path: Path) -> None:
    planned = ImportHarness(tmp_path / "planned").import_one(SNAPSHOTS[0].snapshot, dry_run=True)
    applied = ImportHarness(tmp_path / "applied").import_one(SNAPSHOTS[0].snapshot)

    assert dict(planned.counts) == dict(applied.counts)
    assert planned.applied is False
    assert applied.applied is True


def test_a_dry_run_writes_no_blob_no_record_and_no_snapshot(harness: ImportHarness) -> None:
    harness.import_one(SNAPSHOTS[0].snapshot, dry_run=True)

    assert harness.stored_blob_count == 0
    assert run(harness.caselists.list_sources(limit=10)).items == ()
    assert run(harness.caselists.list_disclosures(limit=10)).items == ()
    assert run(harness.caselists.list_snapshots(SYNTHETIC_CASELIST)) == ()


def test_a_dry_run_after_a_real_import_still_writes_nothing(harness: ImportHarness) -> None:
    harness.import_all()
    before = harness.stored_blob_count

    harness.import_one(SNAPSHOTS[-1].snapshot, dry_run=True)

    assert harness.stored_blob_count == before
    assert len(run(harness.caselists.list_snapshots(SYNTHETIC_CASELIST))) == len(SNAPSHOTS)


# ------------------------------------------------------------------------------------------------
# The suppression list (v1-e30-t07 owns the list; this task honours it)
# ------------------------------------------------------------------------------------------------


def test_a_suppressed_file_is_counted_and_never_stored(harness: ImportHarness) -> None:
    import hashlib

    suppressed = hashlib.sha256(DOCUMENT_BODIES["grove-round-1-aff"]).hexdigest()

    report = harness.import_one(SNAPSHOTS[0].snapshot, suppressed_hashes=frozenset({suppressed}))

    assert report.count(Classification.SUPPRESSED) == 1
    assert not run(harness.blobs.exists(suppressed))
    assert run(harness.caselists.find_source(suppressed)) is None


def test_a_suppressed_file_stays_out_however_often_the_archives_republish_it(
    harness: ImportHarness,
) -> None:
    """Cumulative archives bring it back every week; the list is what keeps it out every week."""
    import hashlib

    suppressed = frozenset({hashlib.sha256(DOCUMENT_BODIES["grove-round-1-aff"]).hexdigest()})

    for snapshot in SNAPSHOTS:
        harness.import_one(snapshot.snapshot, suppressed_hashes=suppressed)

    assert run(harness.caselists.find_source(next(iter(suppressed)))) is None
    assert harness.stored_blob_count == len(DOCUMENT_BODIES) - 1


def test_no_file_is_suppressed_by_default(harness: ImportHarness) -> None:
    """The list is t07's; an import that is not given one suppresses nothing."""
    report = harness.import_one(SNAPSHOTS[0].snapshot)

    assert report.count(Classification.SUPPRESSED) == 0


# ------------------------------------------------------------------------------------------------
# What the report carries
# ------------------------------------------------------------------------------------------------


def test_entries_are_in_path_order_including_removed_paths(harness: ImportHarness) -> None:
    harness.import_all()

    report = harness.import_one(SNAPSHOTS[-1].snapshot)

    paths = [entry.path for entry in report.entries]
    assert paths == sorted(paths)


def test_a_removed_entry_names_a_path_that_is_not_in_this_archive(
    harness: ImportHarness,
) -> None:
    harness.import_one(SNAPSHOTS[1].snapshot)

    report = harness.import_one(SNAPSHOTS[2].snapshot)

    removed = [one for one in report.entries if one.classification is Classification.REMOVED]
    assert [one.path for one in removed] == [
        "Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-Negative-Harbor Classic-Octas.docx"
    ]
    assert removed[0].sha256 is None


def test_a_skipped_entry_carries_its_reason_and_no_digest(harness: ImportHarness) -> None:
    report = harness.import_one(SNAPSHOTS[-1].snapshot)

    skipped = [one for one in report.entries if one.is_skipped]
    assert {one.skip_reason for one in skipped} >= {
        SkipReason.MACOS_METADATA,
        SkipReason.DESKTOP_SERVICES_STORE,
        SkipReason.WORD_LOCK_FILE,
        SkipReason.SYMLINK,
        SkipReason.PATH_OUTSIDE_ARCHIVE,
    }
    assert all(one.sha256 is None and one.classification is None for one in skipped)


def test_the_report_records_which_archive_it_was_classified_against(
    harness: ImportHarness,
) -> None:
    first = harness.import_one(SNAPSHOTS[0].snapshot)
    second = harness.import_one(SNAPSHOTS[1].snapshot)

    assert first.previous_snapshot is None
    assert second.previous_snapshot == SNAPSHOTS[0].snapshot


def test_the_snapshot_record_counts_the_members_the_archive_held(
    harness: ImportHarness,
) -> None:
    expected = EXPECTED_SNAPSHOTS[0]
    harness.import_one(expected.snapshot)

    stored = run(harness.caselists.get_snapshot(SYNTHETIC_CASELIST, expected.snapshot))

    assert stored.file_count == expected.disclosures + expected.skipped_zip
    assert stored.archive_sha256 == harness.digest(expected.snapshot)


# ------------------------------------------------------------------------------------------------
# The fields that reach a Disclosure
# ------------------------------------------------------------------------------------------------


def test_a_public_forum_side_in_this_caselist_is_recorded_as_unknown_with_a_warning(
    harness: ImportHarness,
) -> None:
    """The domain would refuse `PRO` on an LD disclosure; the import records UNKNOWN and says why."""
    harness.import_one(SNAPSHOTS[1].snapshot)

    disclosure = disclosure_at(
        harness,
        SNAPSHOTS[1].snapshot,
        "Riverbend Academy/MnPr/Riverbend Academy-MnPr-Pro-Seaside Cup-Finals.docx",
    )

    assert disclosure.side is Side.UNKNOWN
    assert disclosure.parse_warnings


def test_a_pdf_and_a_legacy_doc_are_stored_as_unparsed_sources(harness: ImportHarness) -> None:
    harness.import_one(SNAPSHOTS[1].snapshot)

    formats = {source.source_format for source in run(harness.caselists.list_sources(limit=100)).items}

    assert SourceFormat.PDF in formats
    assert SourceFormat.DOC in formats
    assert all(
        not source.is_parsable
        for source in run(harness.caselists.list_sources(limit=100)).items
        if source.source_format in {SourceFormat.PDF, SourceFormat.DOC}
    )


def test_an_unreadable_filename_still_becomes_a_disclosure(harness: ImportHarness) -> None:
    """ac1's floor, end to end: never a dropped file."""
    harness.import_one(SNAPSHOTS[1].snapshot)

    disclosure = disclosure_at(
        harness, SNAPSHOTS[1].snapshot, "Cedar Hollow/ZaLu/notes about the harbor round.docx"
    )

    assert disclosure.side is Side.UNKNOWN
    assert disclosure.tournament is None
    assert disclosure.round_label is None
    assert disclosure.parse_warnings


def test_the_school_and_team_come_from_the_directories_not_the_filename(
    harness: ImportHarness,
) -> None:
    harness.import_one(SNAPSHOTS[1].snapshot)

    disclosure = disclosure_at(
        harness,
        SNAPSHOTS[1].snapshot,
        "Northgate Prep/BeCo/Westfield-XY-Neg-Ridgeline Round Robin-Round 3.docx",
    )

    assert disclosure.school == "Northgate Prep"
    assert disclosure.team_code == "BeCo"
    assert disclosure.parse_warnings


# ------------------------------------------------------------------------------------------------
# Nothing personal reaches a log
# ------------------------------------------------------------------------------------------------


def test_the_import_logs_counts_and_never_a_path_school_or_team_code(
    harness: ImportHarness, caplog: pytest.LogCaptureFixture
) -> None:
    """`docs/policies/caselist-data-use.md` rule 4, checked rather than trusted."""
    with caplog.at_level("DEBUG"):
        harness.import_all()

    logged = "\n".join(
        [record.getMessage() for record in caplog.records]
        + [str(getattr(record, "caselist", "")) for record in caplog.records]
        + [str(record.__dict__) for record in caplog.records]
    )

    for forbidden in (
        "Maple Grove",
        "Cedar Hollow",
        "Northgate Prep",
        "Riverbend Academy",
        "QX",
        "ZaLu",
        "BeCo",
        "MnPr",
        ".docx",
    ):
        assert forbidden not in logged, f"{forbidden!r} reached a log record"


def test_the_import_does_log_the_counts_an_operator_needs(
    harness: ImportHarness, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("INFO"):
        harness.import_one(SNAPSHOTS[0].snapshot)

    record = next(record for record in caplog.records if record.name.endswith("import_service"))
    # Read through `__dict__` because `extra=` fields are exactly the ones `LogRecord` has no
    # declared attribute for; that is what makes them extra.
    logged: dict[str, object] = dict(record.__dict__)

    assert logged["caselist"] == SYNTHETIC_CASELIST
    assert logged["members"] == (EXPECTED_SNAPSHOTS[0].disclosures + EXPECTED_SNAPSHOTS[0].skipped_zip)
    assert logged["counts"] == {"NEW": EXPECTED_SNAPSHOTS[0].new}
    assert logged["newly_stored_blobs"] == EXPECTED_SNAPSHOTS[0].distinct_sha256_after


# ------------------------------------------------------------------------------------------------
# An archive with nothing in it
# ------------------------------------------------------------------------------------------------


def test_an_empty_archive_marks_last_week_entirely_removed(harness: ImportHarness) -> None:
    """Cumulative archives mean an empty one is a real, and alarming, answer — reported, not applied."""
    harness.import_one(SNAPSHOTS[0].snapshot)

    report = run(
        harness.service.import_archive(
            cast("list[ArchiveEntry]", []),
            caselist=SYNTHETIC_CASELIST,
            snapshot=SNAPSHOTS[1].snapshot,
            event=EVENT,
            archive_sha256="0" * 64,
            dry_run=True,
        )
    )

    assert report.count(Classification.REMOVED) == EXPECTED_SNAPSHOTS[0].disclosures
    assert report.count(Classification.NEW) == 0


def test_two_members_with_identical_bytes_in_one_archive_store_one_blob(
    harness: ImportHarness,
) -> None:
    """The first is NEW, the second is a DUPLICATE, and the store holds one file."""
    body = b"one body, two paths"
    import hashlib

    digest = hashlib.sha256(body).hexdigest()
    members: list[ArchiveEntry] = [
        ArchiveMember(path="A/QX/A-QX-Aff-Cup-Round 1.docx", sha256=digest, byte_size=len(body), data=body),
        ArchiveMember(
            path="B/ZaLu/B-ZaLu-Aff-Cup-Round 1.docx", sha256=digest, byte_size=len(body), data=body
        ),
    ]

    report = run(
        harness.service.import_archive(
            members,
            caselist=SYNTHETIC_CASELIST,
            snapshot=SNAPSHOTS[0].snapshot,
            event=EVENT,
            archive_sha256="1" * 64,
        )
    )

    assert report.count(Classification.NEW) == 1
    assert report.count(Classification.DUPLICATE) == 1
    assert harness.stored_blob_count == 1
