"""Re-deriving camp and title for a release already imported (`v1-e30-t08`, ac2).

The situation the backfill left: a release imported while the importer could not read the camp out
of the names, so the records and the manifest say `UNKNOWN`. Here that is reproduced honestly, by
importing a synthetic release with the real importer under a table that knows one camp of three,
then re-deriving its metadata with the table that knows all three.

Everything is invented: the camps are the OpenEv fixture's (`tests/fixtures/openev/camp_aliases.yaml`)
plus the deliberately unlisted `Zephyr`, the titles and initials are made up, and the bodies are a
few bytes of filler. Every expected value is written by hand from the table below (working
agreements §6). Real `SqliteCaselistRepository` and `FsSnapshotStore` in `tmp_path`, so "touches no
blob" is a statement about files on disk.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Coroutine
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.openev.build_synthetic_openev import CAMP_ALIASES_PATH

from debate_core.application.caselist.camp_metadata import CampAliases, load_camp_aliases
from debate_core.application.caselist.manifest import SuppressedRowRefused
from debate_core.application.caselist.openev_import_service import OpenEvImportService
from debate_core.application.caselist.openev_manifest import openev_manifest_key
from debate_core.application.caselist.openev_metadata_reimport import (
    NoRecordedRelease,
    OpenEvMetadataReimport,
)
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.ports.archive import ArchiveEntry, ArchiveMember, SkippedMember, SkipReason
from debate_core.application.ports.suppression import ReasonCode, SuppressionAction, SuppressionEntry
from debate_core.domain.caselist import CampFile, Event
from debate_core.integrations.local.fs_blob_store import BLOB_DIRECTORY, FsSnapshotStore
from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository
from debate_core.integrations.local.sqlite_db import SqliteDatabase
from debate_core.testing.fakes import InMemoryAppendOnlyRecord

YEAR = 2026
EVENT = Event.POLICY
IMPORTED_ON = date(2026, 9, 26)
ALL_THREE_CAMPS = load_camp_aliases(CAMP_ALIASES_PATH)
#: What the importer could read when the release went in: one camp of the three.
ONLY_QDI = CampAliases.from_document({"camps": {"QDI": ["Quillfeather"]}}, source="one camp")

LANTERN = "Disadvantages/Lantern Shipping DA - TSF 2026 MNOP.docx"
ORCHARD = "Counterplans/NEG Orchard Grants CP - QDI 2026 JKT.docx"
TIDEWATER = "Kritiks/Tidewater Kritik - Brightwater Workshop 2026.docx"
TIDEWATER_COPY = "Kritiks/Tidewater Kritik copy - Brightwater Workshop 2026.docx"
SALTMARSH = "Topicality/Saltmarsh T - Zephyr 2026.docx"
JUNK = "Topicality/.DS_Store"

BODIES = {
    LANTERN: b"lantern shipping filler",
    ORCHARD: b"orchard grants filler",
    TIDEWATER: b"tidewater kritik filler",
    TIDEWATER_COPY: b"tidewater kritik filler",
    SALTMARSH: b"saltmarsh topicality filler",
}

UNKNOWN_WARNING = (
    "no folder and no word of the filename names a camp in the alias table; camp recorded as UNKNOWN"
)

#: Hand-written: (camp, title, warnings) per path, before and after the re-import.
BEFORE: dict[str, tuple[str, str, list[str]]] = {
    LANTERN: ("UNKNOWN", LANTERN.split("/")[1].removesuffix(".docx"), [UNKNOWN_WARNING]),
    ORCHARD: ("QDI", "NEG Orchard Grants CP", []),
    TIDEWATER: ("UNKNOWN", "Tidewater Kritik - Brightwater Workshop 2026", [UNKNOWN_WARNING]),
    TIDEWATER_COPY: ("UNKNOWN", "Tidewater Kritik copy - Brightwater Workshop 2026", [UNKNOWN_WARNING]),
    SALTMARSH: ("UNKNOWN", "Saltmarsh T - Zephyr 2026", [UNKNOWN_WARNING]),
}
AFTER: dict[str, tuple[str, str, list[str]]] = {
    LANTERN: ("TSF", "Lantern Shipping DA", []),
    ORCHARD: ("QDI", "NEG Orchard Grants CP", []),
    TIDEWATER: ("BWW", "Tidewater Kritik", []),
    TIDEWATER_COPY: ("BWW", "Tidewater Kritik copy", []),
    SALTMARSH: ("UNKNOWN", "Saltmarsh T - Zephyr 2026", [UNKNOWN_WARNING]),
}


def run[ResultT](coroutine: Coroutine[Any, Any, ResultT]) -> ResultT:
    return asyncio.run(coroutine)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def release_entries() -> list[ArchiveEntry]:
    """The synthetic release, in path order, as the archive reader would hand it in."""
    entries: list[ArchiveEntry] = [
        ArchiveMember(path=path, sha256=digest(body), byte_size=len(body), data=body)
        for path, body in BODIES.items()
    ]
    entries.append(SkippedMember(path=JUNK, reason=SkipReason.DESKTOP_SERVICES_STORE))
    return sorted(entries, key=lambda entry: entry.path)


class WritesNoBlob:
    """The local blob store, answering `exists` and refusing everything that would write or read bytes."""

    def __init__(self, inner: FsSnapshotStore) -> None:
        self._inner = inner
        self.asked: list[str] = []

    async def exists(self, key: str) -> bool:
        self.asked.append(key)
        return await self._inner.exists(key)

    async def put(self, data: bytes) -> str:
        raise AssertionError("the metadata re-import wrote a blob")

    async def get(self, key: str) -> bytes:
        raise AssertionError("the metadata re-import read a blob's bytes")


class Harness:
    def __init__(self, root: Path) -> None:
        self.data_dir = root / "data"
        self.caselists = SqliteCaselistRepository(SqliteDatabase.open(self.data_dir))
        self.blobs = FsSnapshotStore(self.data_dir)
        self.suppression_record = InMemoryAppendOnlyRecord("suppression list")
        self.suppression = RecordedSuppressionList(self.suppression_record)
        importer = OpenEvImportService(
            caselists=self.caselists, blobs=self.blobs, suppression=self.suppression
        )
        imported = run(
            importer.import_release(
                release_entries(),
                year=YEAR,
                event=EVENT,
                imported_on=IMPORTED_ON,
                archive_sha256="a" * 64,
                aliases=ONLY_QDI,
            )
        )
        self.recorded = imported.manifest_lines
        self.guarded_blobs = WritesNoBlob(self.blobs)
        self.service = OpenEvImportService(
            caselists=self.caselists, blobs=self.guarded_blobs, suppression=self.suppression
        )

    def reimport(self, lines: tuple[str, ...] | None = None, **options: Any) -> OpenEvMetadataReimport:
        return run(
            self.service.reimport_metadata(
                year=YEAR,
                event=EVENT,
                recorded_manifest=self.recorded if lines is None else lines,
                aliases=options.pop("aliases", ALL_THREE_CAMPS),
                **options,
            )
        )

    def camp_file(self, path: str) -> CampFile:
        page = run(self.caselists.list_camp_files(source_sha256=digest(BODIES[path]), year=YEAR, event=EVENT))
        (record,) = page.items
        return record

    def blob_tree(self) -> dict[str, str]:
        """Every file under the blob directory, by relative path, to the digest of its bytes."""
        root = self.data_dir / BLOB_DIRECTORY
        return {
            str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    return Harness(tmp_path)


def rows_of(lines: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    return {row["path"]: row for row in map(json.loads, lines) if row["kind"] == "member"}


def summary_of(lines: tuple[str, ...]) -> dict[str, Any]:
    (summary,) = [row for row in map(json.loads, lines) if row["kind"] == "summary"]
    return summary


def metadata(row: dict[str, Any]) -> tuple[Any, Any, Any]:
    return (row["camp"], row["file_title"], row["warnings"])


# ------------------------------------------------------------------------------------------------
# The situation before: the release imported with the camps unreadable
# ------------------------------------------------------------------------------------------------


def test_reimport_starts_from_a_release_recorded_with_unreadable_camps(harness: Harness) -> None:
    """The hand-written BEFORE table is what the importer actually recorded."""
    rows = rows_of(harness.recorded)

    assert {path: metadata(rows[path]) for path in BODIES} == BEFORE
    assert harness.camp_file(LANTERN).camp == "UNKNOWN"


# ------------------------------------------------------------------------------------------------
# ac2: camp and title corrected in place
# ------------------------------------------------------------------------------------------------


def test_reimport_corrects_camp_and_title_on_every_row(harness: Harness) -> None:
    report = harness.reimport()

    rows = rows_of(report.manifest_lines)
    assert {path: metadata(rows[path]) for path in BODIES} == AFTER


def test_reimport_corrects_the_camp_file_records_and_keeps_their_identity_and_date(harness: Harness) -> None:
    before = {path: harness.camp_file(path) for path in (LANTERN, ORCHARD, TIDEWATER, SALTMARSH)}

    harness.reimport()

    for path, record in before.items():
        corrected = harness.camp_file(path)
        camp, title, warnings = AFTER[path]
        assert (corrected.camp, corrected.file_title, list(corrected.parse_warnings)) == (
            camp,
            title,
            warnings,
        )
        assert (corrected.source_sha256, corrected.year, corrected.event, corrected.snapshot) == (
            record.source_sha256,
            record.year,
            record.event,
            record.snapshot,
        )


def test_reimport_counts_what_it_changed(harness: Harness) -> None:
    report = harness.reimport()

    assert report.rows == 5
    assert report.camps_before == {"QDI": 1, "UNKNOWN": 4}
    assert report.camps_after == {"BWW": 2, "QDI": 1, "TSF": 1, "UNKNOWN": 1}
    assert (report.unknown_before, report.unknown_after) == (4, 1)
    assert (report.rows_changed, report.titles_changed, report.warnings_changed) == (3, 3, 3)
    # One record per digest: Lantern and Tidewater change; Orchard and Saltmarsh do not, and
    # Tidewater's copy shares Tidewater's record.
    assert (report.camp_files_updated, report.camp_files_missing, report.blobs_missing) == (2, 0, 0)
    assert report.applied is True
    assert report.manifest_changed is True


# ------------------------------------------------------------------------------------------------
# ac2: no sha256, no manifest key, no blob
# ------------------------------------------------------------------------------------------------


def test_reimport_keeps_every_field_but_the_derived_four_byte_for_byte(harness: Harness) -> None:
    before = rows_of(harness.recorded)

    after = rows_of(harness.reimport().manifest_lines)

    assert list(after) == list(before)
    derived = {"camp", "lab", "file_title", "warnings"}
    for path in before:
        assert {k: v for k, v in after[path].items() if k not in derived} == {
            k: v for k, v in before[path].items() if k not in derived
        }, path


def test_reimport_changes_no_sha256(harness: Harness) -> None:
    before = sorted(
        (path, row["sha256"], row["byte_size"]) for path, row in rows_of(harness.recorded).items()
    )

    after = rows_of(harness.reimport().manifest_lines)

    assert sorted((path, row["sha256"], row["byte_size"]) for path, row in after.items()) == before


def test_reimport_keeps_the_release_manifest_key(harness: Harness) -> None:
    report = harness.reimport()

    assert report.manifest_key == openev_manifest_key(YEAR, EVENT) == "manifests/openev/2026-policy.jsonl"


def test_reimport_recounts_only_the_summary_warnings(harness: Harness) -> None:
    before = summary_of(harness.recorded)

    after = summary_of(harness.reimport().manifest_lines)

    assert (before["warnings"], after["warnings"]) == (4, 1)
    assert {k: v for k, v in after.items() if k != "warnings"} == {
        k: v for k, v in before.items() if k != "warnings"
    }


def test_reimport_touches_no_blob(harness: Harness) -> None:
    tree = harness.blob_tree()

    harness.reimport()

    assert harness.blob_tree() == tree
    assert sorted(harness.guarded_blobs.asked) == sorted({digest(body) for body in BODIES.values()})


def test_reimport_reports_a_digest_the_local_store_does_not_hold(harness: Harness) -> None:
    held = digest(BODIES[SALTMARSH])
    (harness.data_dir / BLOB_DIRECTORY / held[:2] / held[2:4] / held).unlink()

    assert harness.reimport().blobs_missing == 1


# ------------------------------------------------------------------------------------------------
# Dry run, a second run, refusals
# ------------------------------------------------------------------------------------------------


def test_reimport_dry_run_writes_no_record_and_reports_the_same_counts(harness: Harness) -> None:
    dry = harness.reimport(dry_run=True)

    assert harness.camp_file(LANTERN).camp == "UNKNOWN"
    assert dry.applied is False
    assert (dry.camp_files_updated, dry.rows_changed, dry.camps_after) == (
        2,
        3,
        {"BWW": 2, "QDI": 1, "TSF": 1, "UNKNOWN": 1},
    )
    assert dry.manifest_lines == harness.reimport().manifest_lines


def test_reimport_a_second_time_changes_nothing(harness: Harness) -> None:
    first = harness.reimport()

    second = harness.reimport(first.manifest_lines)

    assert second.manifest_lines == first.manifest_lines
    assert second.manifest_changed is False
    assert (second.rows_changed, second.titles_changed, second.camp_files_updated) == (0, 0, 0)


def test_reimport_with_the_table_the_release_was_imported_with_returns_the_same_bytes(
    harness: Harness,
) -> None:
    report = harness.reimport(aliases=ONLY_QDI)

    assert report.manifest_lines == harness.recorded
    assert report.manifest_changed is False


def test_reimport_of_a_release_with_no_manifest_is_refused(harness: Harness) -> None:
    with pytest.raises(NoRecordedRelease, match="manifests/openev/2026-policy.jsonl"):
        harness.reimport(())


def test_reimport_refuses_a_manifest_that_still_names_a_suppressed_file_and_writes_nothing(
    harness: Harness,
) -> None:
    from datetime import UTC, datetime

    run(
        harness.suppression.append(
            [
                SuppressionEntry(
                    action=SuppressionAction.SUPPRESS,
                    sha256=digest(BODIES[LANTERN]),
                    recorded_at=datetime(2026, 9, 30, 12, 0, tzinfo=UTC),
                    reason=ReasonCode.REQUESTED_BY_TEAM,
                    request_id="RM-2026-01",
                )
            ]
        )
    )

    with pytest.raises(SuppressedRowRefused):
        harness.reimport()
    assert harness.camp_file(TIDEWATER).camp == "UNKNOWN"
