"""Importing the synthetic OpenEv downloads produces exactly the hand-written expectations.

The assertions are `tests/fixtures/openev/expected_openev_import.json`, worked out by a person from
the fixture's tables (`docs/process/working-agreements.md` §6). Everything runs against a real
`SqliteCaselistRepository` and a real `FsSnapshotStore` in `tmp_path`, because cross-origin
deduplication only means something if one blob really is one file on disk and one source
document really is one row.

The caselist side is the real `CaselistImportService` over the synthetic caselist archives, which
is how the fixture's borrowed file comes to be a disclosed source before the camp file arrives.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Coroutine
from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest
from tests.fixtures.caselist.build_synthetic_archives import (
    DOCUMENT_BODIES as CASELIST_BODIES,
)
from tests.fixtures.caselist.build_synthetic_archives import (
    SNAPSHOTS,
    SYNTHETIC_CASELIST,
    SYNTHETIC_EVENT,
    build_snapshot_zips,
    written_expected_summary,
)
from tests.fixtures.openev.build_synthetic_openev import (
    CAMP_ALIASES_PATH,
    DOCUMENT_BODIES,
    DOWNLOADS,
    build_download_directories,
    build_download_zips,
    expected,
)

from debate_core.application.caselist.camp_metadata import load_camp_aliases
from debate_core.application.caselist.import_service import CaselistImportService, Classification
from debate_core.application.caselist.manifest import manifest_lines
from debate_core.application.caselist.openev_import_service import (
    OpenEvImportReport,
    OpenEvImportService,
    UnrecordableImportDate,
)
from debate_core.application.caselist.openev_manifest import CAMP_FIELDS
from debate_core.application.caselist.publish_plan import (
    LocalSnapshot,
    UnreadableManifest,
    build_publish_plan,
    sources_in_manifest,
)
from debate_core.domain.caselist import CampFile, Event, SourceDocument, SourceOrigin
from debate_core.integrations.local.archive_reader import archive_digest, read_archive
from debate_core.integrations.local.fs_blob_store import BLOB_DIRECTORY, FsSnapshotStore
from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository
from debate_core.integrations.local.sqlite_db import SqliteDatabase

EXPECTED = expected()
YEAR = EXPECTED["year"]
EVENT = Event(EXPECTED["event"])
FIRST, ADDENDUM = (download.name for download in DOWNLOADS)
#: Past dates only: a SnapshotDate in the future is refused by the domain.
IMPORTED_ON = date(2026, 9, 14)
ADDENDUM_ON = date(2026, 9, 18)
LIMITS = {"max_archive_bytes": 64 * 1024 * 1024, "max_unpacked_bytes": 64 * 1024 * 1024}
ALIASES = load_camp_aliases(CAMP_ALIASES_PATH)


def run[ResultT](coroutine: Coroutine[Any, Any, ResultT]) -> ResultT:
    return asyncio.run(coroutine)


class Harness:
    """One data directory with both importers over it, and the downloads to feed them."""

    def __init__(self, root: Path) -> None:
        self.data_dir = root / "data"
        self.caselists = SqliteCaselistRepository(SqliteDatabase.open(self.data_dir))
        self.blobs = FsSnapshotStore(self.data_dir)
        self.openev = OpenEvImportService(caselists=self.caselists, blobs=self.blobs)
        self.archives = CaselistImportService(caselists=self.caselists, blobs=self.blobs)
        self.zips = build_download_zips(root / "openev")
        self.directories = build_download_directories(root / "openev-unpacked")
        self.caselist_zips = build_snapshot_zips(root / "caselist")
        self.manifest: tuple[str, ...] = ()

    def import_caselist_week(self, snapshot: date) -> None:
        run(
            self.archives.import_archive(
                read_archive(self.caselist_zips[snapshot], **LIMITS),
                caselist=SYNTHETIC_CASELIST,
                snapshot=snapshot,
                event=Event(SYNTHETIC_EVENT),
                archive_sha256=archive_digest(self.caselist_zips[snapshot]),
            )
        )

    def import_openev(
        self, name: str, *, as_directory: bool = False, imported_on: date = IMPORTED_ON, **options: Any
    ) -> OpenEvImportReport:
        """Import one download, carrying the release manifest forward exactly as the command does."""
        source = self.directories[name] if as_directory else self.zips[name]
        report = run(
            self.openev.import_release(
                read_archive(source, **LIMITS),
                year=YEAR,
                event=EVENT,
                imported_on=imported_on,
                archive_sha256=archive_digest(source),
                recorded_manifest=self.manifest,
                aliases=ALIASES,
                **options,
            )
        )
        if report.applied:
            self.manifest = report.manifest_lines
        return report

    @property
    def blob_count(self) -> int:
        blobs = self.data_dir / BLOB_DIRECTORY
        return sum(1 for path in blobs.rglob("*") if path.is_file()) if blobs.exists() else 0

    def camp_files(self) -> list[CampFile]:
        return list(run(self.caselists.list_camp_files(limit=1000)).items)

    def sources(self) -> list[SourceDocument]:
        return list(run(self.caselists.list_sources(limit=1000)).items)


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    return Harness(tmp_path)


@pytest.fixture
def after_caselist(harness: Harness) -> Harness:
    """The synthetic caselist's first week imported, so the borrowed file is already disclosed."""
    harness.import_caselist_week(SNAPSHOTS[0].snapshot)
    return harness


def manifest_rows(lines: tuple[str, ...]) -> list[dict[str, Any]]:
    return [json.loads(line) for line in lines]


def counts_of(report: OpenEvImportReport) -> dict[str, int]:
    return {str(name): report.count(name) for name in Classification}


GROVE_SHA256 = __import__("hashlib").sha256(CASELIST_BODIES["grove-round-1-aff"]).hexdigest()


# ------------------------------------------------------------------------------------------------
# ac1: a CampFile per file, with camp, year, event and title; UNKNOWN is a warning, not a failure
# ------------------------------------------------------------------------------------------------


def test_every_member_is_read_exactly_as_the_expectations_say(after_caselist: Harness) -> None:
    report = after_caselist.import_openev(FIRST)

    wanted = EXPECTED["first_download"]["members"]
    assert [entry.path for entry in report.entries] == [member["path"] for member in wanted]
    for entry, member in zip(report.entries, wanted, strict=True):
        if "skip_reason" in member:
            assert str(entry.skip_reason) == member["skip_reason"], entry.path
            continue
        assert entry.parsed is not None
        assert str(entry.classification) == member["classification"], entry.path
        assert entry.parsed.camp == member["camp"], entry.path
        assert entry.parsed.lab == member["lab"], entry.path
        assert entry.parsed.file_title == member["file_title"], entry.path
        assert str(entry.source_format) == member["format"], entry.path
        assert len(entry.parsed.warnings) == member["warnings"], entry.path


def test_the_counts_match_the_expectations(after_caselist: Harness) -> None:
    report = after_caselist.import_openev(FIRST)

    wanted = EXPECTED["first_download"]["after_caselist"]
    assert counts_of(report) == wanted["counts"]
    assert {str(reason): count for reason, count in report.skipped.items()} == wanted["skipped"]
    assert report.member_count == wanted["members"]
    assert report.distinct_digests == wanted["distinct_sha256"]
    assert report.newly_stored_blobs == wanted["newly_stored_blobs"]
    assert report.warning_count == wanted["warnings"]
    assert report.unknown_camp_count == wanted["unknown_camps"]
    assert report.caselist_duplicate_count == wanted["caselist_duplicates"]


def test_one_camp_file_is_recorded_per_distinct_file_with_camp_year_event_and_title(
    after_caselist: Harness,
) -> None:
    after_caselist.import_openev(FIRST)

    recorded = after_caselist.camp_files()
    assert sorted((one.camp, one.file_title) for one in recorded) == sorted(
        (one["camp"], one["file_title"]) for one in EXPECTED["first_download"]["camp_files"]
    )
    assert {(one.year, one.event, one.snapshot) for one in recorded} == {(YEAR, EVENT, IMPORTED_ON)}


def test_an_unresolved_camp_is_recorded_as_unknown_with_its_warning(harness: Harness) -> None:
    harness.import_openev(FIRST)

    unknown = [one for one in harness.camp_files() if one.camp == "UNKNOWN"]
    assert [one.file_title for one in unknown] == ["Zephyr Scholars - Glacier Case Neg"]
    assert unknown[0].parse_warnings == (
        "no folder and no filename prefix names a camp in the alias table; camp recorded as UNKNOWN",
    )


def test_without_a_caselist_first_the_borrowed_file_is_simply_new(harness: Harness) -> None:
    report = harness.import_openev(FIRST)

    wanted = EXPECTED["first_download"]["without_caselist"]
    assert counts_of(report) == wanted["counts"]
    assert report.newly_stored_blobs == wanted["newly_stored_blobs"]
    assert report.caselist_duplicate_count == wanted["caselist_duplicates"]
    assert run(harness.caselists.get_source(GROVE_SHA256)).origin is SourceOrigin.OPENEV


def test_a_directory_is_classified_exactly_as_the_zip(tmp_path: Path) -> None:
    from_zip = Harness(tmp_path / "zip").import_openev(FIRST)
    from_directory = Harness(tmp_path / "directory").import_openev(FIRST, as_directory=True)

    assert [(one.path, one.classification, one.skip_reason) for one in from_zip.entries] == [
        (one.path, one.classification, one.skip_reason) for one in from_directory.entries
    ]


# ------------------------------------------------------------------------------------------------
# ac2: a camp file identical to a caselist source is one blob, a DUPLICATE, and linked from both
# ------------------------------------------------------------------------------------------------


def test_a_camp_file_already_disclosed_creates_no_second_blob(after_caselist: Harness) -> None:
    before = after_caselist.blob_count

    after_caselist.import_openev(FIRST)

    # Eleven camp files, ten distinct bodies, one of them already stored by the caselist.
    assert after_caselist.blob_count == before + 9


def test_it_is_a_duplicate_carrying_the_existing_caselist_source(after_caselist: Harness) -> None:
    existing = run(after_caselist.caselists.get_source(GROVE_SHA256))

    report = after_caselist.import_openev(FIRST)

    borrowed = next(entry for entry in report.entries if entry.path == "Tamarack/TSF-Borrowed Grove Aff.docx")
    assert borrowed.classification is Classification.DUPLICATE
    assert borrowed.sha256 == GROVE_SHA256
    assert borrowed.existing_source == existing
    assert existing.origin is SourceOrigin.CASELIST_ARCHIVE
    assert existing.caselist == SYNTHETIC_CASELIST


def test_the_existing_source_document_is_left_exactly_as_it_was(after_caselist: Harness) -> None:
    existing = run(after_caselist.caselists.get_source(GROVE_SHA256))

    after_caselist.import_openev(FIRST)

    assert run(after_caselist.caselists.get_source(GROVE_SHA256)) == existing


def test_one_source_is_linked_from_both_a_disclosure_and_a_camp_file(after_caselist: Harness) -> None:
    after_caselist.import_openev(FIRST)

    disclosures = run(after_caselist.caselists.list_disclosures(source_sha256=GROVE_SHA256, limit=100)).items
    camp_files = run(after_caselist.caselists.list_camp_files(source_sha256=GROVE_SHA256, limit=100)).items
    assert disclosures
    assert [(one.camp, one.file_title) for one in camp_files] == [("TSF", "Borrowed Grove Aff")]
    assert len([one for one in after_caselist.sources() if one.sha256 == GROVE_SHA256]) == 1


def test_the_manifest_row_names_the_source_it_duplicates(after_caselist: Harness) -> None:
    report = after_caselist.import_openev(FIRST)

    rows = {row["path"]: row for row in manifest_rows(report.manifest_lines) if row["kind"] == "member"}
    for member in EXPECTED["first_download"]["members"]:
        if "existing_origin" in member:
            row = rows[member["path"]]
            assert (row["existing_origin"], row["existing_caselist"]) == (
                member["existing_origin"],
                member["existing_caselist"],
            ), member["path"]


def test_a_caselist_disclosing_a_camp_file_later_links_to_it_rather_than_conflicting(
    harness: Harness,
) -> None:
    """The other direction: camp files first, then every caselist week, with t03's own counts."""
    harness.import_openev(FIRST)

    written: list[dict[str, Any]] = cast("list[dict[str, Any]]", written_expected_summary()["snapshots"])
    weeks = {week["snapshot"]: week for week in written}
    for snapshot in SNAPSHOTS:
        report = run(
            harness.archives.import_archive(
                read_archive(harness.caselist_zips[snapshot.snapshot], **LIMITS),
                caselist=SYNTHETIC_CASELIST,
                snapshot=snapshot.snapshot,
                event=Event(SYNTHETIC_EVENT),
                archive_sha256=archive_digest(harness.caselist_zips[snapshot.snapshot]),
            )
        )
        assert {str(name): report.count(name) for name in Classification} == (
            weeks[snapshot.snapshot.isoformat()]["classifications"]
        )

    source = run(harness.caselists.get_source(GROVE_SHA256))
    assert source.origin is SourceOrigin.OPENEV
    assert run(harness.caselists.list_disclosures(source_sha256=GROVE_SHA256, limit=100)).items


# ------------------------------------------------------------------------------------------------
# ac3: manifests/openev/<year>-<event>.jsonl, the caselist row layout plus camp fields, idempotent
# ------------------------------------------------------------------------------------------------


def test_the_manifest_is_filed_under_the_release_key(harness: Harness) -> None:
    report = harness.import_openev(FIRST)

    assert report.manifest_key == EXPECTED["manifest_key"]
    assert report.release == EXPECTED["release"]


def test_every_row_has_the_caselist_row_layout_plus_the_camp_fields(tmp_path: Path) -> None:
    caselist = CaselistImportService(
        caselists=SqliteCaselistRepository(SqliteDatabase.open(tmp_path / "caselist")),
        blobs=FsSnapshotStore(tmp_path / "caselist"),
    )
    zips = build_snapshot_zips(tmp_path / "zips")
    week = SNAPSHOTS[0].snapshot
    caselist_rows = [
        json.loads(line)
        for line in manifest_lines(
            run(
                caselist.import_archive(
                    read_archive(zips[week], **LIMITS),
                    caselist=SYNTHETIC_CASELIST,
                    snapshot=week,
                    event=Event(SYNTHETIC_EVENT),
                    archive_sha256=archive_digest(zips[week]),
                )
            )
        )
    ]
    caselist_member_keys = {key for row in caselist_rows if row["kind"] == "member" for key in row}
    camp_fields = {
        "camp",
        "lab",
        "file_title",
        "year",
        "imported_on",
        "archive_sha256",
        "existing_origin",
        "existing_caselist",
    }

    rows = manifest_rows(Harness(tmp_path / "openev").import_openev(FIRST).manifest_lines)

    assert set(CAMP_FIELDS) == camp_fields
    assert {row["schema_version"] for row in rows} == {caselist_rows[0]["schema_version"]}
    for row in rows[:-1]:
        assert set(row) == caselist_member_keys | camp_fields, row["path"]
    assert set(rows[-1]) >= {key for key in caselist_rows[-1] if key != "kind"} | {"kind"}


def test_the_manifest_summary_matches_the_expectations(after_caselist: Harness) -> None:
    report = after_caselist.import_openev(FIRST)

    summary = manifest_rows(report.manifest_lines)[-1]
    wanted = EXPECTED["first_download"]["manifest_summary"]
    assert summary["kind"] == "summary"
    assert (summary["caselist"], summary["snapshot"], summary["event"], summary["year"]) == (
        "openev",
        EXPECTED["release"],
        EXPECTED["event"],
        YEAR,
    )
    assert summary["members"] == wanted["members"]
    assert summary["distinct_sha256"] == wanted["distinct_sha256"]
    assert summary["warnings"] == wanted["warnings"]
    assert summary["classifications"] == wanted["classifications"]
    assert summary["skipped"] == wanted["skipped"]
    assert len(summary["archives"]) == wanted["archives"]


def test_the_manifest_rows_carry_the_parsed_camp_fields(after_caselist: Harness) -> None:
    report = after_caselist.import_openev(FIRST)

    rows = {row["path"]: row for row in manifest_rows(report.manifest_lines) if row["kind"] == "member"}
    for member in EXPECTED["first_download"]["members"]:
        row = rows[member["path"]]
        if "skip_reason" in member:
            assert (row["skip_reason"], row["camp"], row["file_title"]) == (member["skip_reason"], None, None)
            continue
        assert (row["classification"], row["camp"], row["lab"], row["file_title"], row["format"]) == (
            member["classification"],
            member["camp"],
            member["lab"],
            member["file_title"],
            member["format"],
        ), member["path"]
        assert (row["year"], row["imported_on"]) == (YEAR, IMPORTED_ON.isoformat())
        assert row["school"] is None and row["side"] is None


def test_re_importing_the_same_download_is_a_no_op(after_caselist: Harness) -> None:
    first = after_caselist.import_openev(FIRST)
    blobs, camp_files, sources = (
        after_caselist.blob_count,
        after_caselist.camp_files(),
        after_caselist.sources(),
    )

    again = after_caselist.import_openev(FIRST)

    wanted = EXPECTED["first_download"]["re_import"]
    assert counts_of(again) == wanted["counts"]
    assert again.newly_stored_blobs == wanted["newly_stored_blobs"]
    assert again.manifest_lines == first.manifest_lines
    assert after_caselist.blob_count == blobs
    assert after_caselist.camp_files() == camp_files
    assert after_caselist.sources() == sources


def test_re_importing_on_a_later_day_changes_nothing_either(after_caselist: Harness) -> None:
    first = after_caselist.import_openev(FIRST)
    camp_files, sources = after_caselist.camp_files(), after_caselist.sources()

    again = after_caselist.import_openev(FIRST, imported_on=date(2026, 9, 20))

    assert again.manifest_lines == first.manifest_lines
    assert after_caselist.camp_files() == camp_files
    assert after_caselist.sources() == sources


# ------------------------------------------------------------------------------------------------
# A later, partial download merges into the release manifest rather than replacing it
# ------------------------------------------------------------------------------------------------


def test_the_addendum_classifies_against_what_the_release_already_recorded(after_caselist: Harness) -> None:
    after_caselist.import_openev(FIRST)

    report = after_caselist.import_openev(ADDENDUM, imported_on=ADDENDUM_ON)

    wanted = EXPECTED["addendum"]
    assert [(entry.path, str(entry.classification or entry.skip_reason)) for entry in report.entries] == [
        (member["path"], member.get("classification") or member["skip_reason"])
        for member in wanted["members"]
    ]
    assert counts_of(report) == wanted["counts"]
    assert report.member_count == wanted["members_count"]
    assert report.newly_stored_blobs == wanted["newly_stored_blobs"]
    assert len(after_caselist.camp_files()) == wanted["camp_files_after"]


def test_the_merged_manifest_keeps_every_earlier_row_and_counts_the_whole_release(
    after_caselist: Harness,
) -> None:
    first = after_caselist.import_openev(FIRST)

    report = after_caselist.import_openev(ADDENDUM, imported_on=ADDENDUM_ON)

    summary = manifest_rows(report.manifest_lines)[-1]
    wanted = EXPECTED["addendum"]["manifest_summary"]
    assert {
        key: summary[key] for key in ("members", "distinct_sha256", "warnings", "classifications", "skipped")
    } == {
        key: wanted[key] for key in ("members", "distinct_sha256", "warnings", "classifications", "skipped")
    }
    assert len(summary["archives"]) == wanted["archives"]
    earlier = {json.loads(line)["path"]: line for line in first.manifest_lines[:-1]}
    merged = {json.loads(line)["path"]: line for line in report.manifest_lines[:-1]}
    for path in EXPECTED["addendum"]["rows_kept_from_first_download"]:
        assert merged[path] == earlier[path], path
    assert set(earlier) <= set(merged)


# ------------------------------------------------------------------------------------------------
# Dry runs, suppression, publishing and logs
# ------------------------------------------------------------------------------------------------


def test_a_dry_run_writes_nothing_and_plans_the_manifest_a_real_run_writes(tmp_path: Path) -> None:
    dry = Harness(tmp_path / "dry")
    planned = dry.import_openev(FIRST, dry_run=True)

    assert not planned.applied
    assert dry.blob_count == 0
    assert dry.camp_files() == []
    assert dry.sources() == []
    assert planned.manifest_lines == Harness(tmp_path / "real").import_openev(FIRST).manifest_lines


def test_a_suppressed_file_is_counted_and_never_stored(harness: Harness) -> None:
    suppressed = __import__("hashlib").sha256(DOCUMENT_BODIES["orchard-kritik"]).hexdigest()

    report = harness.import_openev(FIRST, suppressed_hashes=frozenset({suppressed}))

    assert report.count(Classification.SUPPRESSED) == 1
    assert not run(harness.caselists.list_camp_files(source_sha256=suppressed, limit=10)).items
    assert run(harness.caselists.find_source(suppressed)) is None


def test_the_publisher_reads_the_manifest_and_files_its_sources_under_raw_openev_year(
    after_caselist: Harness,
) -> None:
    report = after_caselist.import_openev(FIRST)

    sources = sources_in_manifest(report.manifest_key, report.manifest_lines)
    plan = build_publish_plan(
        "openev",
        [LocalSnapshot("openev", report.release, sources, manifest_size=1)],
        local_blobs={source.sha256 for source in sources},
        remote={},
    )

    assert len(sources) == EXPECTED["first_download"]["manifest_summary"]["distinct_sha256"]
    assert {source.key.rsplit("/", 4)[0] for source in plan.uploads} == {"raw/openev/2026"}
    assert plan.snapshots[0].manifest_key == EXPECTED["manifest_key"]


def test_the_import_logs_counts_and_never_a_path_title_or_camp(
    harness: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        harness.import_openev(FIRST)

    logged = " ".join(
        f"{record.getMessage()} {record.__dict__}"
        for record in caplog.records
        if record.name.startswith("debate_core")
    )
    assert "imported OpenEv release" in logged
    for member in EXPECTED["first_download"]["members"]:
        assert member["path"] not in logged
        if member.get("file_title"):
            assert member["file_title"] not in logged
    for camp in ("QDI", "TSF", "BWW", "Quillfeather", "Tamarack", "Brightwater", "Zephyr"):
        assert camp not in logged


def test_a_recorded_manifest_that_cannot_be_read_is_refused_not_overwritten(harness: Harness) -> None:
    harness.manifest = ('{"schema_version": 1, "kind": "member", "path": "a.docx"}', "not json")

    with pytest.raises(UnreadableManifest, match="line 2"):
        harness.import_openev(FIRST)


def test_a_future_import_date_is_refused_before_anything_is_written(harness: Harness) -> None:
    with pytest.raises(UnrecordableImportDate, match="in the future"):
        harness.import_openev(FIRST, imported_on=date(2999, 1, 1))

    assert harness.blob_count == 0
    assert harness.camp_files() == []
