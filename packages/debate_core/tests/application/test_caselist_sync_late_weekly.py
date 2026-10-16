"""A pull that imports a weekly dated before a complete archive it imported earlier (`v1-e30-t18`).

The pull imports a complete archive even when a weekly queue stopped at a gap (`v1-e34-t19`), and it
imports the weekly once the gap closes, on a later run. `v1-e30-t17` found the complete archive's
withdrawals then counted without that weekly, in its manifest summary and in the run record, and
never counted again. Since `v1-e30-t18` the run that imports the weekly counts them again.

Over `v1-e30-t17`'s window-order archives (`tests/fixtures/caselist/build_window_order_archives.py`),
served by the fake OpenCaselist of `test_caselist_sync_full_archive`. Worked out by hand there: the
complete archive of `2026-09-12` counted against `2026-09-01` alone is withdrawn 0, superseded 1, 1
compared; against `2026-09-01` and `2026-09-08` it is withdrawn 1 (`second-week-only`), superseded 1
(`first-version`), 2 compared, the date-order count.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_window_order_archives import (
    BODIES,
    CASELIST,
    COMPLETE_ARCHIVES,
    FIRST_WEEK,
    FULL_AFTER_TWO_WEEKS,
    SECOND_WEEK,
    THIRD_WEEK,
    WEEKLY_WINDOWS,
)

from debate_core.application.caselist.manifest import full_archive_manifest_key, manifest_key
from debate_core.application.caselist_sync import RunSummary, SyncStage
from debate_core.application.sync_runs import record_for_summary
from debate_core.integrations.local import FsEvidenceObjectStore
from debate_core.integrations.s3 import S3EvidenceObjectStore

from .test_caselist_sync_full_archive import RUN_CLOCK, Site, build_service, summary_row

if TYPE_CHECKING:  # pragma: no cover - imported for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

RECOUNTED = (
    "complete archive testcl26 full/2026-09-12 recounted after an earlier-dated weekly: "
    "1 withdrawn, 1 superseded against 2 earlier snapshot(s)"
)
RECORDED = "recounted after an earlier-dated weekly: 1 withdrawn, 1 superseded against 2 earlier snapshot(s)"
"""What the run record keeps of it: the record redacts a `full/<date>` name, as it does an import's."""


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def bucket(evidence_bucket: str, s3_client: S3Client) -> S3EvidenceObjectStore:
    return S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client)


def list_weekly(site: Site, week: date) -> None:
    site.weekly(week, members={path: BODIES[body] for path, body in WEEKLY_WINDOWS[week].items()})


def list_complete(site: Site, day: date) -> None:
    site.full(day, members={path: BODIES[body] for path, body in COMPLETE_ARCHIVES[day].items()})


async def in_date_order(root: Path) -> tuple[Path, RunSummary]:
    """`2026-09-01`, `2026-09-08` and the complete archive in one run, then `2026-09-15`."""
    data_dir = root / "evidence"
    site = Site(root / "site")
    list_weekly(site, FIRST_WEEK)
    list_weekly(site, SECOND_WEEK)
    list_complete(site, FULL_AFTER_TWO_WEEKS)
    first = await build_service(site, data_dir).run([CASELIST])
    assert first.succeeded, first.stages
    assert summary_row(data_dir, full_archive_manifest_key(CASELIST, FULL_AFTER_TWO_WEEKS))["withdrawn"] == 1
    list_weekly(site, THIRD_WEEK)
    last = await build_service(site, data_dir, rotation=None, clock=RUN_CLOCK + timedelta(days=1)).run(
        [CASELIST]
    )
    assert last.succeeded, last.stages
    return data_dir, last


async def with_the_second_week_late(
    root: Path, bucket: S3EvidenceObjectStore | None = None
) -> tuple[Path, RunSummary]:
    """`2026-09-01`; then the complete archive alone, as when the weekly queue stopped; then the rest."""
    data_dir = root / "evidence"
    site = Site(root / "site")
    list_weekly(site, FIRST_WEEK)
    first = build_service(site, data_dir, rotation=None, clock=RUN_CLOCK - timedelta(days=2), bucket=bucket)
    await first.run([CASELIST])
    site.unlist()
    list_complete(site, FULL_AFTER_TWO_WEEKS)
    complete = await build_service(site, data_dir, clock=RUN_CLOCK - timedelta(days=1), bucket=bucket).run(
        [CASELIST]
    )
    assert complete.succeeded, complete.stages
    (imported,) = complete.full_archive_imports
    assert (imported.withdrawn, imported.superseded, imported.earlier_snapshots) == (0, 1, 1)
    site.unlist()
    list_weekly(site, SECOND_WEEK)
    list_weekly(site, THIRD_WEEK)
    late = await build_service(site, data_dir, rotation=None, bucket=bucket).run([CASELIST])
    assert late.succeeded, late.stages
    return data_dir, late


async def test_the_run_that_imports_the_earlier_weekly_recounts_the_complete_archive(tmp_path: Path) -> None:
    """ac3: the manifest summary and the run record carry the date-order count."""
    data_dir, late = await with_the_second_week_late(tmp_path)

    row = summary_row(data_dir, full_archive_manifest_key(CASELIST, FULL_AFTER_TWO_WEEKS))
    assert (row["withdrawn"], row["superseded"], row["earlier_snapshots"]) == (1, 1, 2)
    imported = late.stage(SyncStage.IMPORT)
    assert imported is not None and RECOUNTED in (imported.reason or "")
    record = record_for_summary(late, environment="dev", mode="run")
    (recorded,) = [stage for stage in record.stages if stage.stage == str(SyncStage.IMPORT)]
    assert RECORDED in (recorded.reason or "")
    assert late.as_json()["full_archive_recounted"] == [
        {
            "caselist": CASELIST,
            "snapshot": "full/2026-09-12",
            "withdrawn": 1,
            "superseded": 1,
            "earlier_snapshots": 2,
        }
    ]
    assert late.full_archive_imports == ()


async def test_after_the_late_weekly_every_manifest_is_the_date_order_one_and_is_published(
    tmp_path: Path, bucket: S3EvidenceObjectStore
) -> None:
    """The complete archive's manifest and every weekly's, byte for byte, in this store and the bucket."""
    ordered, _ = await in_date_order(tmp_path / "in-order")
    late, summary = await with_the_second_week_late(tmp_path / "late", bucket)

    for key in (
        full_archive_manifest_key(CASELIST, FULL_AFTER_TWO_WEEKS),
        *(manifest_key(CASELIST, week) for week in (FIRST_WEEK, SECOND_WEEK, THIRD_WEEK)),
    ):
        expected = FsEvidenceObjectStore(ordered).path_for(key).read_bytes()
        assert FsEvidenceObjectStore(late).path_for(key).read_bytes() == expected, key
        published = tmp_path / "published" / key
        await bucket.get_file(key, published)
        assert published.read_bytes() == expected, key
    assert summary.pending_publish == ()


async def test_a_weekly_dated_after_the_complete_archive_recounts_nothing(tmp_path: Path) -> None:
    """`2026-09-15` is imported after `full/2026-09-12` and dated after it: not an earlier snapshot."""
    _, last = await in_date_order(tmp_path)

    assert last.snapshots_imported == (f"{CASELIST} 2026-09-15",)
    assert last.full_archive_recounts == ()
    assert last.as_json()["full_archive_recounted"] == []
