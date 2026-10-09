"""The complete-archive refresh (`v1-e34-t04`): its own snapshot, the rotation, and withdrawals.

The service under test is `CaselistSyncService`, with everything real but the OpenCaselist source,
which is `test_caselist_sync.FakeCaselistSource` over the small archives built here.

## The archives

One invented caselist, `testcl26` (and a second, `testclb26`, where two must be due at once).
Each document is a few bytes this module writes; nothing is real caselist content. Paths are
`<School>/<Team>/<file>`, as OpenCaselist lays an archive out, with invented schools.

| Archive | Date | Members (path: bytes) |
|---|---|---|
| weekly W1 | 09-08 | `ALDER_ONE`: `a-one`, `BIRCH_ONE`: `b-one` |
| weekly W2 | 09-15 | `ALDER_ONE`: `a-one`, `BIRCH_ONE`: `b-one`, `CEDAR_ONE`: `c-one` |
| weekly W3 | 09-22 | `ALDER_ONE`: `a-one`, `CEDAR_ONE`: `c-one`, `DOGWOOD_ONE`: `d-one` |
| complete F | 09-15 | `ALDER_ONE`: `a-one`, `BIRCH_ONE`: `b-one`, `CEDAR_ONE`: `c-one`, `ELM_OLD`: `e-old` |
| complete F2 | 09-22 | `ALDER_ONE`: `a-two`, `CEDAR_ONE`: `c-one`, `DOGWOOD_ONE`: `d-one`, `ELM_OLD`: same |

All dated 2026.

What each weekly is against the one before it, worked out from the table:

* W1, the first: 2 NEW. first_seen 2.
* W2 against W1: `ALDER_ONE` and `BIRCH_ONE` UNCHANGED, `CEDAR_ONE` NEW. first_seen 1 (`c-one`).
* W3 against W2: `ALDER_ONE` and `CEDAR_ONE` UNCHANGED, `DOGWOOD_ONE` NEW, `BIRCH_ONE` REMOVED.
  first_seen 1 (`d-one`).

F holds `c-one`, so a first-seen count that read F as an earlier snapshot would give W2 zero.

F2 against the snapshots dated before 09-22, which are W1, W2 and F (W3 is dated 09-22, not
before): the digests they held are `a-one`, `b-one`, `c-one` and `e-old`. F2 lacks `a-one` and
`b-one`. `a-one` was held at `ALDER_ONE`, which F2 has with other
bytes: **superseded 1**. `b-one` was held only at `BIRCH_ONE`, which F2 lacks: **withdrawn 1**.
Earlier snapshots compared: W1, W2, F = **3**.
"""

from __future__ import annotations

import functools
import hashlib
import json
import zipfile
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from debate_core.application.caselist.evidence_listing import LocalEvidence, digests_in_earlier_manifests
from debate_core.application.caselist.import_service import CaselistImportService
from debate_core.application.caselist.manifest import (
    full_archive_manifest_key,
    manifest_key,
    read_manifest_lines,
)
from debate_core.application.caselist.openev_import_service import OpenEvImportService
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.status_service import CaselistStatusService
from debate_core.application.caselist_sync import (
    DOWNLOAD_LEDGER_FILENAME,
    CaselistSyncService,
    DownloadLedger,
    FullArchiveRefused,
    FullArchiveRotation,
    RunSummary,
    SelectionDecision,
    SyncStage,
    decide_full_archives,
)
from debate_core.application.ports.caselist_source import ArchiveKind, ArchiveListing
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsEvidenceObjectStore, FsSnapshotStore, SqliteDatabase
from debate_core.integrations.local.archive_reader import read_archive
from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository
from debate_core.integrations.s3 import S3EvidenceObjectStore
from debate_core.testing.fakes import empty_suppression_list

from .test_caselist_sync import FakeCaselistSource

if TYPE_CHECKING:  # pragma: no cover - imported for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

CASELIST = "testcl26"
SECOND = "testclb26"
_LIMITS = {"max_archive_bytes": 1024 * 1024, "max_unpacked_bytes": 1024 * 1024}

ALDER_ONE = "Alder/QX/Alder-QX-Aff-Pine Open-Round 1.docx"
BIRCH_ONE = "Birch/ZL/Birch-ZL-Neg-Pine Open-Round 2.docx"
CEDAR_ONE = "Cedar/MN/Cedar-MN-Aff-Pine Open-Round 3.docx"
DOGWOOD_ONE = "Dogwood/PR/Dogwood-PR-Neg-Pine Open-Round 4.docx"
ELM_OLD = "Elm/OL/Elm-OL-Aff-Summer Open-Round 1.docx"

W1, W2, W3 = date(2026, 9, 8), date(2026, 9, 15), date(2026, 9, 22)

WEEKLIES: dict[date, dict[str, bytes]] = {
    W1: {ALDER_ONE: b"a-one", BIRCH_ONE: b"b-one"},
    W2: {ALDER_ONE: b"a-one", BIRCH_ONE: b"b-one", CEDAR_ONE: b"c-one"},
    W3: {ALDER_ONE: b"a-one", CEDAR_ONE: b"c-one", DOGWOOD_ONE: b"d-one"},
}
FULL: dict[date, dict[str, bytes]] = {
    W2: {ALDER_ONE: b"a-one", BIRCH_ONE: b"b-one", CEDAR_ONE: b"c-one", ELM_OLD: b"e-old"},
    W3: {ALDER_ONE: b"a-two", CEDAR_ONE: b"c-one", DOGWOOD_ONE: b"d-one", ELM_OLD: b"e-old"},
}

RUN_CLOCK = datetime(2026, 9, 24, 6, 0, tzinfo=UTC)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ------------------------------------------------------------------------------------------------
# Building archives, listings and the service
# ------------------------------------------------------------------------------------------------


def write_zip(path: Path, members: Mapping[str, bytes]) -> Path:
    """A zip of `members`, deterministic, with no wrapper directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            archive.writestr(info, members[name])
    return path


def weekly_name(caselist: str, day: date) -> str:
    return f"{caselist}-weekly-{day.isoformat()}.zip"


def full_name(caselist: str, day: date) -> str:
    return f"{caselist}-all-{day.isoformat()}.zip"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Site:
    """What the fake OpenCaselist lists, built archive by archive."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.source = FakeCaselistSource()

    def weekly(self, day: date, caselist: str = CASELIST, members: Mapping[str, bytes] | None = None) -> Path:
        name = weekly_name(caselist, day)
        path = write_zip(self.root / caselist / name, members if members is not None else WEEKLIES[day])
        self._list(caselist, name, ArchiveKind.WEEKLY, day, path)
        return path

    def full(self, day: date, caselist: str = CASELIST, members: Mapping[str, bytes] | None = None) -> Path:
        name = full_name(caselist, day)
        path = write_zip(self.root / caselist / name, members if members is not None else FULL[day])
        self._list(caselist, name, ArchiveKind.FULL, day, path)
        return path

    def unlist(self, caselist: str = CASELIST) -> None:
        self.source.archives[caselist] = []

    def _list(self, caselist: str, name: str, kind: ArchiveKind, day: date, path: Path) -> None:
        listing = ArchiveListing(
            caselist=caselist,
            name=name,
            kind=kind,
            archive_date=day,
            url=f"https://files.example.invalid/{name}",
        )
        listed = [one for one in self.source.archives.get(caselist, []) if one[0].name != name]
        self.source.archives[caselist] = [*listed, (listing, path)]


def local_evidence(data_dir: Path) -> LocalEvidence:
    objects = FsEvidenceObjectStore(data_dir)
    blobs = FsEvidenceObjectStore(data_dir, subdirectory=Path("blobs"))
    return LocalEvidence(
        objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
    )


def importer(data_dir: Path) -> CaselistImportService:
    """The archive importer as the composition root builds it: with t08's first-seen reader."""
    return CaselistImportService(
        suppression=empty_suppression_list(),
        caselists=SqliteCaselistRepository(SqliteDatabase.open(data_dir)),
        blobs=FsSnapshotStore(data_dir),
        earlier_manifest_digests=functools.partial(digests_in_earlier_manifests, local_evidence(data_dir)),
    )


def build_service(
    site: Site,
    data_dir: Path,
    *,
    rotation: FullArchiveRotation | None = FullArchiveRotation(),  # noqa: B008 - frozen, shared safely
    clock: datetime = RUN_CLOCK,
    bucket: S3EvidenceObjectStore | None = None,
) -> CaselistSyncService:
    database = SqliteDatabase.open(data_dir)
    repository = SqliteCaselistRepository(database)
    blobs = FsSnapshotStore(data_dir)
    return CaselistSyncService(
        source=site.source,
        archive_importer=importer(data_dir),
        openev_importer=OpenEvImportService(
            suppression=empty_suppression_list(), caselists=repository, blobs=blobs
        ),
        local=local_evidence(data_dir),
        read_archive=lambda path: read_archive(path, **_LIMITS),
        event_for_caselist=lambda slug: Event.LD if slug.startswith("testcl") else None,
        inbox=data_dir / "inbox",
        state_dir=data_dir,
        suppression=empty_suppression_list(),
        clock=lambda: clock,
        full_archive_rotation=rotation,
        publisher=CaselistPublishService(
            suppression=empty_suppression_list(), local=local_evidence(data_dir), remote=bucket
        )
        if bucket is not None
        else None,
        status=CaselistStatusService(
            suppression=empty_suppression_list(), local=local_evidence(data_dir), remote=bucket
        )
        if bucket is not None
        else None,
    )


def summary_row(data_dir: Path, key: str) -> dict[str, object]:
    lines = read_manifest_lines(FsEvidenceObjectStore(data_dir).path_for(key))
    rows = [json.loads(line) for line in lines]
    (summary,) = [row for row in rows if row["kind"] == "summary"]
    return summary


def member_paths(data_dir: Path, key: str) -> set[str]:
    lines = read_manifest_lines(FsEvidenceObjectStore(data_dir).path_for(key))
    return {row["path"] for row in map(json.loads, lines) if row["kind"] == "member"}


def decision_of(summary: RunSummary, name: str) -> SelectionDecision:
    (one,) = [selection for selection in summary.archives if selection.name == name]
    return one.decision


def spend(data_dir: Path, downloads: int, *, at: datetime = RUN_CLOCK - timedelta(hours=1)) -> None:
    """Record `downloads` bulk downloads an hour before the run, as an earlier run would have."""
    ledger = DownloadLedger(data_dir / DOWNLOAD_LEDGER_FILENAME)
    for _ in range(downloads):
        ledger.record(at)


# ------------------------------------------------------------------------------------------------
# ac0: a snapshot namespace of its own
# ------------------------------------------------------------------------------------------------


async def test_a_complete_archive_dated_with_a_weekly_collides_with_nothing(tmp_path: Path) -> None:
    """W2 and F are both dated 09-15. Each keeps its own manifest; the repository holds W2 alone."""
    data_dir = tmp_path / "evidence"
    site = Site(tmp_path / "site")
    site.weekly(W1)
    await build_service(site, data_dir, rotation=None).run([CASELIST])
    weekly = site.weekly(W2)
    full = site.full(W2)

    summary = await build_service(site, data_dir).run([CASELIST])

    assert summary.succeeded, summary.stages
    assert site.source.archive_fetches[-2:] == [weekly_name(CASELIST, W2), full_name(CASELIST, W2)]
    weekly_summary = summary_row(data_dir, manifest_key(CASELIST, W2))
    assert weekly_summary["archive_sha256"] == digest(weekly)
    assert weekly_summary["members"] == 3
    assert weekly_summary["previous_snapshot"] == "2026-09-08"
    assert member_paths(data_dir, manifest_key(CASELIST, W2)) == {ALDER_ONE, BIRCH_ONE, CEDAR_ONE}
    full_summary = summary_row(data_dir, full_archive_manifest_key(CASELIST, W2))
    assert full_summary["archive_sha256"] == digest(full)
    assert full_summary["snapshot"] == "full/2026-09-15"
    assert full_summary["members"] == 4
    assert member_paths(data_dir, full_archive_manifest_key(CASELIST, W2)) == {
        ALDER_ONE,
        BIRCH_ONE,
        CEDAR_ONE,
        ELM_OLD,
    }
    repository = SqliteCaselistRepository(SqliteDatabase.open(data_dir))
    snapshots = await repository.list_snapshots(CASELIST)
    assert [(one.snapshot, one.archive_sha256) for one in snapshots] == [
        (W2, digest(weekly)),
        (W1, summary_row(data_dir, manifest_key(CASELIST, W1))["archive_sha256"]),
    ]
    disclosed = await repository.list_disclosures(caselist=CASELIST, snapshot=W2, limit=50)
    assert sorted(one.source_path for one in disclosed.items) == sorted([ALDER_ONE, BIRCH_ONE, CEDAR_ONE])


async def test_a_current_complete_archive_does_not_strand_the_weekly_back_catalogue(tmp_path: Path) -> None:
    """F2 (09-22) is imported while only W1 is held. W2 and W3 are still fetched and imported."""
    data_dir = tmp_path / "evidence"
    site = Site(tmp_path / "site")
    site.weekly(W1)
    await build_service(site, data_dir, rotation=None).run([CASELIST])
    site.unlist()
    site.full(W3)
    first = await build_service(site, data_dir).run([CASELIST])
    assert first.succeeded, first.stages
    assert site.source.archive_fetches[-1] == full_name(CASELIST, W3)

    site.weekly(W2)
    site.weekly(W3)
    second = await build_service(site, data_dir).run([CASELIST])

    assert second.succeeded, second.stages
    assert decision_of(second, weekly_name(CASELIST, W2)) is SelectionDecision.DOWNLOAD
    assert decision_of(second, weekly_name(CASELIST, W3)) is SelectionDecision.DOWNLOAD
    assert decision_of(second, full_name(CASELIST, W3)) is SelectionDecision.ALREADY_IMPORTED
    assert summary_row(data_dir, manifest_key(CASELIST, W2))["previous_snapshot"] == "2026-09-08"
    assert summary_row(data_dir, manifest_key(CASELIST, W3))["previous_snapshot"] == "2026-09-15"


async def test_neither_baseline_reader_ever_returns_a_complete_archive(tmp_path: Path) -> None:
    """`_latest_imported_snapshot` and the importer's `_previous_snapshot`, after F2 (09-22)."""
    data_dir = tmp_path / "evidence"
    site = Site(tmp_path / "site")
    site.weekly(W1)
    await build_service(site, data_dir, rotation=None).run([CASELIST])
    site.unlist()
    site.full(W3)
    service = build_service(site, data_dir)
    await service.run([CASELIST])

    assert await service._latest_imported_snapshot(CASELIST) == W1  # pyright: ignore[reportPrivateUsage]
    previous = await importer(data_dir)._previous_snapshot(  # pyright: ignore[reportPrivateUsage]
        CASELIST, date(2026, 9, 30), allow_out_of_order=False
    )
    assert previous == W1


async def _weekly_manifests(tmp_path: Path, *, with_full_archive: bool) -> dict[date, list[str]]:
    """Import W1, then (optionally) F, then W2 and W3; return each weekly's manifest lines."""
    data_dir = tmp_path / ("with" if with_full_archive else "without")
    site = Site(tmp_path / f"site-{with_full_archive}")
    site.weekly(W1)
    await build_service(site, data_dir, rotation=None).run([CASELIST])
    if with_full_archive:
        site.unlist()
        site.full(W2)
        between = await build_service(site, data_dir).run([CASELIST])
        assert between.succeeded, between.stages
        assert site.source.archive_fetches[-1] == full_name(CASELIST, W2)
        site.unlist()
        site.weekly(W1)
    site.weekly(W2)
    site.weekly(W3)
    after = await build_service(site, data_dir, rotation=None).run([CASELIST])
    assert after.succeeded, after.stages
    objects = FsEvidenceObjectStore(data_dir)
    return {day: read_manifest_lines(objects.path_for(manifest_key(CASELIST, day))) for day in (W1, W2, W3)}


async def test_importing_a_complete_archive_leaves_every_weekly_diff_unchanged(tmp_path: Path) -> None:
    """Every weekly manifest is byte for byte what it is without F, and says what the table says."""
    without = await _weekly_manifests(tmp_path, with_full_archive=False)
    with_full = await _weekly_manifests(tmp_path, with_full_archive=True)

    assert with_full == without
    w2 = next(json.loads(line) for line in with_full[W2] if json.loads(line)["kind"] == "summary")
    w3 = next(json.loads(line) for line in with_full[W3] if json.loads(line)["kind"] == "summary")
    assert (w2["previous_snapshot"], w2["classifications"]) == ("2026-09-08", {"NEW": 1, "UNCHANGED": 2})
    assert (w3["previous_snapshot"], w3["classifications"]) == (
        "2026-09-15",
        {"NEW": 1, "REMOVED": 1, "UNCHANGED": 2},
    )


async def test_first_seen_is_not_lowered_by_a_complete_archive_imported_before_the_weekly(
    tmp_path: Path,
) -> None:
    """F holds `c-one`; W2's first_seen is still 1, and W3's still 1 (PM decision, t08)."""
    with_full = await _weekly_manifests(tmp_path, with_full_archive=True)

    first_seen = {
        day: next(json.loads(line) for line in lines if json.loads(line)["kind"] == "summary")["first_seen"]
        for day, lines in with_full.items()
    }
    assert first_seen == {W1: 2, W2: 1, W3: 1}


# ------------------------------------------------------------------------------------------------
# ac1, ac2, ac3: the rotation, one per run, after the weeklies
# ------------------------------------------------------------------------------------------------


def listing(caselist: str, day: date) -> ArchiveListing:
    name = full_name(caselist, day)
    return ArchiveListing(
        caselist=caselist, name=name, kind=ArchiveKind.FULL, archive_date=day, url=f"https://x.invalid/{name}"
    )


def decide(
    listings: Sequence[ArchiveListing],
    last_refreshed: Mapping[str, date | None],
    *,
    allowance: int = 5,
    interval_days: int = 30,
    today: date = date(2026, 9, 24),
    requested: str | None = None,
) -> dict[str, SelectionDecision]:
    selections, _ = decide_full_archives(
        listings,
        caselists=list(last_refreshed),
        last_refreshed=last_refreshed,
        inbox_names=frozenset(),
        allowance=allowance,
        today=today,
        rotation=FullArchiveRotation(interval=timedelta(days=interval_days)),
        requested=requested,
    )
    return {one.caselist: one.decision for one in selections}


def test_a_caselist_refreshed_more_than_the_interval_ago_is_due_and_one_inside_it_is_not() -> None:
    """31 days is more than 30; 30 is not. Both listed archives are newer than what is held."""
    today = date(2026, 9, 24)
    assert decide([listing(CASELIST, W3)], {CASELIST: today - timedelta(days=31)}, today=today) == {
        CASELIST: SelectionDecision.DOWNLOAD
    }
    assert decide([listing(CASELIST, W3)], {CASELIST: today - timedelta(days=30)}, today=today) == {
        CASELIST: SelectionDecision.FULL_ARCHIVE_NOT_DUE
    }


def test_the_interval_is_a_setting() -> None:
    today = date(2026, 9, 24)
    held = {CASELIST: today - timedelta(days=12)}
    assert (
        decide([listing(CASELIST, W3)], held, interval_days=30)[CASELIST]
        is SelectionDecision.FULL_ARCHIVE_NOT_DUE
    )
    assert decide([listing(CASELIST, W3)], held, interval_days=10)[CASELIST] is SelectionDecision.DOWNLOAD


async def test_the_reason_is_in_the_run_summary_whether_or_not_one_is_fetched(tmp_path: Path) -> None:
    data_dir = tmp_path / "evidence"
    site = Site(tmp_path / "site")
    site.full(W2)
    fetched = await build_service(site, data_dir).run([CASELIST])
    site.full(W3)
    not_due = await build_service(site, data_dir).run([CASELIST])

    fetched_json = json.loads(json.dumps(fetched.as_json()))["full_archive"]
    not_due_json = json.loads(json.dumps(not_due.as_json()))["full_archive"]
    assert fetched_json["fetch"] == CASELIST
    assert "testcl26's is fetched this run" in fetched_json["reason"]
    assert "testcl26: fetched this run (never refreshed)" in fetched_json["reason"]
    assert not_due_json["fetch"] is None
    assert "testcl26: not due (last refreshed 2026-09-15, 9 days ago)" in not_due_json["reason"]
    for summary in (fetched, not_due):
        select = summary.stage(SyncStage.SELECT)
        assert select is not None and "complete archive:" in (select.reason or "")
    assert decision_of(not_due, full_name(CASELIST, W3)) is SelectionDecision.FULL_ARCHIVE_NOT_DUE


async def test_with_the_rotation_off_none_is_fetched_and_the_summary_says_so(tmp_path: Path) -> None:
    data_dir = tmp_path / "evidence"
    site = Site(tmp_path / "site")
    site.full(W3)

    summary = await build_service(site, data_dir, rotation=None).run([CASELIST])

    assert site.source.archive_fetches == []
    assert decision_of(summary, full_name(CASELIST, W3)) is SelectionDecision.FULL_ARCHIVE_ROTATION_OFF
    assert "the rotation is off" in (summary.full_archive.reason if summary.full_archive else "")


async def test_two_caselists_due_at_once_fetch_only_the_least_recently_refreshed(tmp_path: Path) -> None:
    """testcl26 last refreshed 09-01, testclb26 never: on 10-08 both are due, and testclb26 goes first.

    Only one is fetched. The next run, a week on, with testclb26 refreshed, takes testcl26.
    """
    data_dir = tmp_path / "evidence"
    site = Site(tmp_path / "site")
    september = date(2026, 9, 1)
    site.full(september, members=FULL[W2])
    await build_service(site, data_dir, clock=datetime(2026, 9, 2, 6, 0, tzinfo=UTC)).run([CASELIST])
    site.full(W3)
    site.full(W3, caselist=SECOND)
    later = datetime(2026, 10, 8, 6, 0, tzinfo=UTC)

    first = await build_service(site, data_dir, clock=later).run([CASELIST, SECOND])

    assert site.source.archive_fetches[1:] == [full_name(SECOND, W3)]
    assert decision_of(first, full_name(CASELIST, W3)) is SelectionDecision.FULL_ARCHIVE_WAITS_ITS_TURN
    assert first.full_archive is not None and first.full_archive.fetch == SECOND

    second = await build_service(site, data_dir, clock=later + timedelta(days=7)).run([CASELIST, SECOND])

    assert site.source.archive_fetches[2:] == [full_name(CASELIST, W3)]
    assert second.full_archive is not None and second.full_archive.fetch == CASELIST


def test_of_two_never_refreshed_the_first_configured_goes_first_and_never_refreshed_beats_old() -> None:
    today = date(2026, 10, 31)
    both_new = decide(
        [listing(CASELIST, W3), listing(SECOND, W3)], {SECOND: None, CASELIST: None}, today=today
    )
    assert both_new == {
        SECOND: SelectionDecision.DOWNLOAD,
        CASELIST: SelectionDecision.FULL_ARCHIVE_WAITS_ITS_TURN,
    }
    old_and_new = decide(
        [listing(CASELIST, W3), listing(SECOND, W3)],
        {CASELIST: date(2026, 9, 1), SECOND: None},
        today=today,
    )
    assert old_and_new == {
        CASELIST: SelectionDecision.FULL_ARCHIVE_WAITS_ITS_TURN,
        SECOND: SelectionDecision.DOWNLOAD,
    }
    two_old = decide(
        [listing(CASELIST, W3), listing(SECOND, W3)],
        {CASELIST: date(2026, 9, 1), SECOND: date(2026, 8, 25)},
        today=today,
    )
    assert two_old[SECOND] is SelectionDecision.DOWNLOAD


async def test_weeklies_that_use_up_the_allowance_exactly_defer_the_complete_archive(tmp_path: Path) -> None:
    """Three spent in the last 24 hours, two weeklies new: 5 - 3 = 2, all of it the weeklies'.

    W1 was fetched three days before the run, outside the 24-hour window, so it is not one of them.
    """
    data_dir = tmp_path / "evidence"
    site = Site(tmp_path / "site")
    site.weekly(W1)
    await build_service(site, data_dir, rotation=None, clock=RUN_CLOCK - timedelta(days=3)).run([CASELIST])
    site.weekly(W2)
    site.weekly(W3)
    site.full(W3)
    spend(data_dir, 3)

    summary = await build_service(site, data_dir).run([CASELIST])

    assert site.source.archive_fetches[1:] == [weekly_name(CASELIST, W2), weekly_name(CASELIST, W3)]
    assert (
        decision_of(summary, full_name(CASELIST, W3)) is SelectionDecision.FULL_ARCHIVE_DEFERRED_FOR_WEEKLIES
    )
    assert summary.full_archive is not None
    assert summary.full_archive.fetch is None
    assert summary.full_archive.allowance_after_weeklies == 0
    assert "testcl26 is first in turn" in summary.full_archive.reason
    assert "deferred: the weeklies left no bulk download" in summary.full_archive.reason
    assert summary.archives_deferred == 0, "a deferred complete archive is not weekly backlog"


async def test_one_download_left_after_the_weeklies_buys_the_complete_archive(tmp_path: Path) -> None:
    data_dir = tmp_path / "evidence"
    site = Site(tmp_path / "site")
    site.weekly(W1)
    await build_service(site, data_dir, rotation=None, clock=RUN_CLOCK - timedelta(days=3)).run([CASELIST])
    site.weekly(W2)
    site.weekly(W3)
    site.full(W3)
    spend(data_dir, 2)

    summary = await build_service(site, data_dir).run([CASELIST])

    assert site.source.archive_fetches[1:] == [
        weekly_name(CASELIST, W2),
        weekly_name(CASELIST, W3),
        full_name(CASELIST, W3),
    ]
    assert summary.full_archive is not None and summary.full_archive.allowance_after_weeklies == 1


# ------------------------------------------------------------------------------------------------
# The readers that opt in: publish, status and retention, against moto
# ------------------------------------------------------------------------------------------------


@pytest.fixture
def bucket(evidence_bucket: str, s3_client: S3Client) -> S3EvidenceObjectStore:
    return S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client)


def inbox_names(data_dir: Path) -> set[str]:
    inbox = data_dir / "inbox"
    return {one.name for one in inbox.iterdir()} if inbox.is_dir() else set()


async def test_a_complete_archive_is_published_confirmed_and_then_leaves_the_inbox(
    tmp_path: Path, bucket: S3EvidenceObjectStore
) -> None:
    """Imported and confirmed, on t11's conditions: then, and only then, its zip goes."""
    data_dir = tmp_path / "evidence"
    site = Site(tmp_path / "site")
    site.weekly(W1)
    site.full(W2)

    summary = await build_service(site, data_dir, bucket=bucket).run([CASELIST])

    assert summary.succeeded, summary.stages
    report = summary.stage(SyncStage.REPORT)
    assert report is not None and report.reason == "2 snapshot(s) confirmed in the bucket"
    keys = {info.key for info in await bucket.list_objects("manifests/")}
    assert full_archive_manifest_key(CASELIST, W2) in keys
    assert summary.inbox_retention is not None
    assert {one.name for one in summary.inbox_retention.removed} == {
        f"{CASELIST} 2026-09-08",
        f"{CASELIST} full/2026-09-15",
    }
    assert inbox_names(data_dir) == set()
    status = await CaselistStatusService(
        suppression=empty_suppression_list(), local=local_evidence(data_dir), remote=bucket
    ).status(CASELIST)
    assert {(one.snapshot, one.in_sync) for one in status.snapshots} == {
        ("2026-09-08", True),
        ("full/2026-09-15", True),
    }


async def test_a_complete_archive_not_imported_stays_in_the_inbox(
    tmp_path: Path, bucket: S3EvidenceObjectStore
) -> None:
    """In the inbox, and no `manifests/<slug>/full/<date>.jsonl` names its bytes: kept, not_imported."""
    data_dir = tmp_path / "evidence"
    site = Site(tmp_path / "site")
    site.weekly(W1)
    stray = write_zip(data_dir / "inbox" / full_name(CASELIST, W2), FULL[W2])

    summary = await build_service(site, data_dir, bucket=bucket).run([CASELIST])

    assert stray.exists()
    assert summary.inbox_retention is not None
    kept = {one.name: one.decision for one in summary.inbox_retention.kept}
    assert str(kept[f"{CASELIST} full/2026-09-15"]) == "not_imported"


async def test_a_complete_archive_whose_publish_is_not_confirmed_stays_in_the_inbox(
    tmp_path: Path, bucket: S3EvidenceObjectStore, s3_client: S3Client, evidence_bucket: str
) -> None:
    """Imported, but its manifest is gone from the bucket: not confirmed, so kept."""
    data_dir = tmp_path / "evidence"
    site = Site(tmp_path / "site")
    site.full(W2)
    first = await build_service(site, data_dir, bucket=bucket).run([CASELIST])
    assert first.succeeded and inbox_names(data_dir) == set()
    s3_client.delete_object(Bucket=evidence_bucket, Key=full_archive_manifest_key(CASELIST, W2))
    copy = (tmp_path / "site" / CASELIST / full_name(CASELIST, W2)).read_bytes()
    (data_dir / "inbox" / full_name(CASELIST, W2)).write_bytes(copy)

    second = await build_service(site, data_dir, bucket=bucket).run([CASELIST])

    assert (data_dir / "inbox" / full_name(CASELIST, W2)).exists()
    assert second.inbox_retention is not None
    kept = {one.name: one.decision for one in second.inbox_retention.kept}
    assert str(kept[f"{CASELIST} full/2026-09-15"]) == "not_confirmed"


# ------------------------------------------------------------------------------------------------
# ac4: withdrawals
# ------------------------------------------------------------------------------------------------


async def _store_with_f_and_weeklies(tmp_path: Path) -> tuple[Path, Site]:
    """W1, W2 and F (09-15) imported; W3 and F2 (09-22) listed. See the module docstring."""
    data_dir = tmp_path / "evidence"
    site = Site(tmp_path / "site")
    site.weekly(W1)
    site.weekly(W2)
    site.full(W2)
    await build_service(site, data_dir, clock=RUN_CLOCK - timedelta(days=2)).run([CASELIST])
    site.weekly(W3)
    site.full(W3)
    return data_dir, site


async def test_withdrawal_counts_split_withdrawn_from_superseded(tmp_path: Path) -> None:
    """Withdrawn 1 (`b-one`), superseded 1 (`a-one`), against 3 earlier snapshots (the docstring)."""
    data_dir, site = await _store_with_f_and_weeklies(tmp_path)
    later = RUN_CLOCK + timedelta(days=40)

    summary = await build_service(site, data_dir, clock=later).run([CASELIST])

    assert summary.succeeded, summary.stages
    (imported,) = summary.full_archive_imports
    assert (imported.caselist, imported.snapshot) == (CASELIST, "full/2026-09-22")
    assert (imported.withdrawn, imported.superseded, imported.earlier_snapshots) == (1, 1, 3)
    row = summary_row(data_dir, full_archive_manifest_key(CASELIST, W3))
    assert (row["withdrawn"], row["superseded"], row["earlier_snapshots"]) == (1, 1, 3)
    assert "first_seen" not in row
    assert row["previous_snapshot"] == "full/2026-09-15"


async def test_withdrawals_are_reported_apart_from_the_weekly_path_level_removed(tmp_path: Path) -> None:
    """W3's REMOVED (`BIRCH_ONE`) is in its manifest only; the run summary's withdrawals are their own."""
    data_dir, site = await _store_with_f_and_weeklies(tmp_path)

    summary = await build_service(site, data_dir, clock=RUN_CLOCK + timedelta(days=40)).run([CASELIST])

    body = summary.as_json()
    full = body["full_archive"]
    assert isinstance(full, dict)
    assert full["imported"] == [
        {
            "caselist": CASELIST,
            "snapshot": "full/2026-09-22",
            "bytes": (tmp_path / "site" / CASELIST / full_name(CASELIST, W3)).stat().st_size,
            "withdrawn": 1,
            "superseded": 1,
            "earlier_snapshots": 3,
        }
    ]
    assert summary_row(data_dir, manifest_key(CASELIST, W3))["classifications"] == {
        "NEW": 1,
        "REMOVED": 1,
        "UNCHANGED": 2,
    }
    imported = summary.stage(SyncStage.IMPORT)
    assert imported is not None
    assert "complete archive testcl26 full/2026-09-22: 1 withdrawn, 1 superseded" in (imported.reason or "")


async def test_withdrawal_summary_names_no_path_school_team_or_file(tmp_path: Path) -> None:
    data_dir, site = await _store_with_f_and_weeklies(tmp_path)

    summary = await build_service(site, data_dir, clock=RUN_CLOCK + timedelta(days=40)).run([CASELIST])

    written = json.dumps(summary.as_json())
    for name in ("Alder", "Birch", "Cedar", "Dogwood", "Elm", "QX", "ZL", "MN", "PR", "OL", "Pine Open"):
        assert name not in written


# ------------------------------------------------------------------------------------------------
# ac5: on demand
# ------------------------------------------------------------------------------------------------


async def test_full_archive_on_demand_ignores_the_interval_and_the_rotation_setting(tmp_path: Path) -> None:
    data_dir = tmp_path / "evidence"
    site = Site(tmp_path / "site")
    site.full(W2)
    await build_service(site, data_dir).run([CASELIST])
    site.full(W3)

    summary = await build_service(site, data_dir, rotation=None).run([CASELIST], full_archive=CASELIST)

    assert site.source.archive_fetches == [full_name(CASELIST, W2), full_name(CASELIST, W3)]
    assert summary.full_archive is not None and summary.full_archive.requested == CASELIST
    assert "as --full-archive asked" in summary.full_archive.reason


async def test_full_archive_on_demand_refuses_when_the_allowance_is_gone(tmp_path: Path) -> None:
    data_dir = tmp_path / "evidence"
    site = Site(tmp_path / "site")
    site.full(W3)
    spend(data_dir, 5)

    with pytest.raises(FullArchiveRefused, match="first in turn"):
        await build_service(site, data_dir).run([CASELIST], full_archive=CASELIST)

    assert site.source.archive_fetches == []


async def test_full_archive_on_demand_dry_run_reports_and_fetches_nothing(tmp_path: Path) -> None:
    data_dir = tmp_path / "evidence"
    site = Site(tmp_path / "site")
    site.full(W3)
    spend(data_dir, 5)

    summary = await build_service(site, data_dir).run([CASELIST], dry_run=True, full_archive=CASELIST)

    assert site.source.archive_fetches == []
    assert summary.dry_run
    assert (
        decision_of(summary, full_name(CASELIST, W3)) is SelectionDecision.FULL_ARCHIVE_DEFERRED_FOR_WEEKLIES
    )
    assert summary.full_archive is not None and summary.full_archive.allowance_after_weeklies == 0
