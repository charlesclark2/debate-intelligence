"""NEW is week-over-week; first-seen is new to the caselist (`v1-e30-t08`, ac3).

The v1-e30-t06 backfill's first day imported three consecutive weekly windows that reported 25 NEW
and stored 16 files the caselist had never held: a weekly archive is a window of a week's edits, so
a file from an earlier window that is edited again comes back NEW against the week before it. NEW
is right for what it is — not present in the preceding snapshot — and wrong when read as new
evidence. First-seen is the other number: a sha256 appearing for the first time in any snapshot of
the caselist, counted from the caselist's own earlier manifests.

Three consecutive synthetic snapshots reproduce the shape, with every count written by hand from the
tables below (working agreements §6):

| Snapshot | Holds | NEW | First seen |
|---|---|---|---|
| 08-11 | nine files `early-01`..`early-09` | 9 | 9 |
| 08-18 | three new files `middle-01`..`03` | 3 | 3 |
| 08-25 | four new files `late-01`..`04`, all nine early files again, and `middle-01` | 13 | 4 |
| **Total** | | **25** | **16** |

The filenames carry no school, no team code and no name; the bodies are filler. Real
`SqliteCaselistRepository`, `FsSnapshotStore` and `FsEvidenceObjectStore` in `tmp_path`, with each
week's manifest written where `caselist import` writes it.
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import json
from collections.abc import Coroutine
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from debate_core.application.caselist import import_service
from debate_core.application.caselist.evidence_listing import LocalEvidence, digests_in_earlier_manifests
from debate_core.application.caselist.import_service import (
    CaselistImportService,
    Classification,
    ImportReport,
)
from debate_core.application.caselist.manifest import manifest_key, write_manifest
from debate_core.application.caselist.openev_import_service import OpenEvImportService
from debate_core.application.ports.archive import ArchiveMember
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsEvidenceObjectStore, FsSnapshotStore, SqliteDatabase
from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository
from debate_core.testing.fakes import empty_suppression_list

CASELIST = "testcl26"
OTHER_CASELIST = "testcl27"
FIRST, SECOND, THIRD = date(2026, 8, 11), date(2026, 8, 18), date(2026, 8, 25)

EARLY = [f"early-{number:02d}.docx" for number in range(1, 10)]
MIDDLE = [f"middle-{number:02d}.docx" for number in range(1, 4)]
LATE = [f"late-{number:02d}.docx" for number in range(1, 5)]

WEEKS: dict[date, list[str]] = {
    FIRST: EARLY,
    SECOND: MIDDLE,
    THIRD: [*LATE, *EARLY, MIDDLE[0]],
}


def run[ResultT](coroutine: Coroutine[Any, Any, ResultT]) -> ResultT:
    return asyncio.run(coroutine)


def body(name: str) -> bytes:
    return f"filler for {name}".encode()


def member(path: str, data: bytes | None = None) -> ArchiveMember:
    data = body(path) if data is None else data
    return ArchiveMember(path=path, sha256=hashlib.sha256(data).hexdigest(), byte_size=len(data), data=data)


class Weeks:
    """One data directory, the importer as the composition root builds it, and the manifests."""

    def __init__(self, data_dir: Path, *, history: bool = True) -> None:
        self.data_dir = data_dir
        self.caselists = SqliteCaselistRepository(SqliteDatabase.open(data_dir))
        self.blobs = FsSnapshotStore(data_dir)
        self.objects = FsEvidenceObjectStore(data_dir)
        blobs = FsEvidenceObjectStore(data_dir, subdirectory=Path("blobs"))
        self.local = LocalEvidence(
            objects=self.objects,
            blobs=blobs,
            object_path_for=self.objects.path_for,
            blob_path_for=blobs.path_for,
        )
        self.service = CaselistImportService(
            caselists=self.caselists,
            blobs=self.blobs,
            suppression=empty_suppression_list(),
            earlier_manifest_digests=functools.partial(digests_in_earlier_manifests, self.local)
            if history
            else None,
        )

    def import_week(
        self, snapshot: date, members: list[ArchiveMember] | None = None, *, caselist: str = CASELIST
    ) -> ImportReport:
        entries = sorted(members or [member(path) for path in WEEKS[snapshot]], key=lambda one: one.path)
        report = run(
            self.service.import_archive(
                entries, caselist=caselist, snapshot=snapshot, event=Event.LD, archive_sha256="c" * 64
            )
        )
        write_manifest(report, self.objects.path_for(manifest_key(caselist, snapshot)))
        return report

    def summary(self, snapshot: date, caselist: str = CASELIST) -> dict[str, Any]:
        lines = (
            self.objects.path_for(manifest_key(caselist, snapshot)).read_text(encoding="utf-8").splitlines()
        )
        return json.loads(lines[-1])


@pytest.fixture
def weeks(tmp_path: Path) -> Weeks:
    return Weeks(tmp_path / "evidence")


# ------------------------------------------------------------------------------------------------
# The backfill's shape: 25 NEW, 16 first seen
# ------------------------------------------------------------------------------------------------


def test_new_count_over_three_weeks_is_25_because_it_is_week_over_week(weeks: Weeks) -> None:
    reports = [weeks.import_week(week) for week in WEEKS]

    assert [report.count(Classification.NEW) for report in reports] == [9, 3, 13]
    assert sum(report.count(Classification.NEW) for report in reports) == 25


def test_first_seen_over_three_weeks_is_16_where_new_is_25(weeks: Weeks) -> None:
    reports = [weeks.import_week(week) for week in WEEKS]

    assert [report.first_seen for report in reports] == [9, 3, 4]
    assert sum(report.first_seen or 0 for report in reports) == 16
    assert sum(report.count(Classification.NEW) for report in reports) == 25


def test_first_seen_is_in_the_summary_row_beside_new(weeks: Weeks) -> None:
    for week in WEEKS:
        weeks.import_week(week)

    third = weeks.summary(THIRD)

    assert (third["classifications"]["NEW"], third["first_seen"]) == (13, 4)
    assert third["schema_version"] == 1


def test_first_seen_comes_from_this_caselists_manifests_not_from_the_blob_store(weeks: Weeks) -> None:
    """Bytes another caselist already stored are no new blob here, but are first seen here."""
    shared = [member(f"shared-{number}.docx", body(f"shared {number}")) for number in range(1, 3)]
    weeks.import_week(FIRST, shared, caselist=OTHER_CASELIST)

    report = weeks.import_week(FIRST, [*shared, member("own-01.docx")])

    assert (report.count(Classification.NEW), report.first_seen, report.newly_stored_blobs) == (3, 3, 1)


def test_first_seen_counts_a_camp_file_a_team_then_discloses(weeks: Weeks, tmp_path: Path) -> None:
    """The bytes are an OpenEv source already; the caselist has never held them."""
    data = body("camp file")
    openev = OpenEvImportService(
        caselists=weeks.caselists, blobs=weeks.blobs, suppression=empty_suppression_list()
    )
    run(
        openev.import_release(
            [member("Kritiks/Orchard Kritik - QDI 2026.docx", data)],
            year=2026,
            event=Event.POLICY,
            imported_on=FIRST,
            archive_sha256="d" * 64,
        )
    )

    report = weeks.import_week(SECOND, [member("borrowed.docx", data)])

    assert (report.first_seen, report.newly_stored_blobs) == (1, 0)


def test_first_seen_counts_a_revised_file_and_not_one_from_any_earlier_week(weeks: Weeks) -> None:
    weeks.import_week(FIRST, [member("kept.docx"), member("revised.docx", b"first version")])
    weeks.import_week(SECOND, [member("kept.docx")])

    report = weeks.import_week(
        THIRD,
        [
            member("kept.docx"),
            member("revised.docx", b"second version"),
            member("moved.docx", body("kept.docx")),
        ],
    )

    # `revised.docx` is new bytes (NEW against 08-18, which lacks it); `moved.docx` holds `kept.docx`'s
    # bytes under a new path (DUPLICATE). Only the revision is first seen.
    assert (report.count(Classification.NEW), report.count(Classification.DUPLICATE)) == (1, 1)
    assert report.first_seen == 1


def test_re_importing_a_week_reports_the_same_first_seen(weeks: Weeks) -> None:
    for week in WEEKS:
        weeks.import_week(week)
    manifest = weeks.objects.path_for(manifest_key(CASELIST, THIRD)).read_bytes()

    again = weeks.import_week(THIRD)

    assert again.first_seen == 4
    assert weeks.objects.path_for(manifest_key(CASELIST, THIRD)).read_bytes() == manifest


def test_first_seen_never_rewrites_an_earlier_weeks_manifest(weeks: Weeks) -> None:
    weeks.import_week(FIRST)
    first = weeks.objects.path_for(manifest_key(CASELIST, FIRST)).read_bytes()

    weeks.import_week(SECOND)
    weeks.import_week(THIRD)

    assert weeks.objects.path_for(manifest_key(CASELIST, FIRST)).read_bytes() == first


def test_first_seen_reads_an_earlier_manifest_written_before_the_count_existed(weeks: Weeks) -> None:
    """A manifest from before `v1-e30-t08` has no `first_seen` key; its member rows still count."""
    weeks.import_week(FIRST)
    path = weeks.objects.path_for(manifest_key(CASELIST, FIRST))
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    del rows[-1]["first_seen"]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    weeks.import_week(SECOND)

    assert weeks.import_week(THIRD).first_seen == 4


def test_first_seen_is_none_when_the_importer_has_no_manifests_to_read(tmp_path: Path) -> None:
    weeks = Weeks(tmp_path / "evidence", history=False)

    report = weeks.import_week(FIRST)

    assert report.first_seen is None
    assert weeks.summary(FIRST)["first_seen"] is None


# ------------------------------------------------------------------------------------------------
# What NEW is documented as
# ------------------------------------------------------------------------------------------------


def test_new_count_is_documented_as_not_present_in_the_preceding_snapshot() -> None:
    documented = " ".join((import_service.__doc__ or "").split())

    assert "not present in the preceding snapshot" in documented
    assert "have not been seen before, under this path or any other" not in documented
