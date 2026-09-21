"""A local evidence store holding the three synthetic weeks, as `caselist import` leaves one.

The publish, plan and status tests all start from the same place an operator does: three weekly
archives imported in order, blobs under `<data_dir>/blobs/` and one manifest per week under
`<data_dir>/objects/manifests/testcl26/`. The importer is the real one, run over the synthetic
archives from `tests/fixtures/caselist/`; it is set-up here, not the thing under test, and what the
tests assert against is `expected_publish.json`, which a person wrote from the fixture's tables.

Nothing in these archives is real caselist content (`docs/policies/caselist-data-use.md`).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.fixtures.caselist.build_synthetic_archives import (
    SNAPSHOTS,
    SYNTHETIC_CASELIST,
    SYNTHETIC_EVENT,
    build_snapshot_zips,
)

from debate_core.application.caselist.import_service import CaselistImportService
from debate_core.application.caselist.manifest import manifest_key, write_manifest
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsEvidenceObjectStore, FsSnapshotStore, SqliteDatabase
from debate_core.integrations.local.archive_reader import archive_digest, read_archive
from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository

_LIMITS = {"max_archive_bytes": 64 * 1024 * 1024, "max_unpacked_bytes": 64 * 1024 * 1024}


async def import_synthetic_weeks(data_dir: Path, zips_dir: Path) -> None:
    """Import all three synthetic weeks into `data_dir`, writing each week's manifest."""
    database = SqliteDatabase.open(data_dir)
    service = CaselistImportService(
        caselists=SqliteCaselistRepository(database),
        blobs=FsSnapshotStore(data_dir),
    )
    objects = FsEvidenceObjectStore(data_dir)
    zips = build_snapshot_zips(zips_dir)
    for week in SNAPSHOTS:
        report = await service.import_archive(
            read_archive(zips[week.snapshot], **_LIMITS),
            caselist=SYNTHETIC_CASELIST,
            snapshot=week.snapshot,
            event=Event(SYNTHETIC_EVENT),
            archive_sha256=archive_digest(zips[week.snapshot]),
        )
        write_manifest(report, objects.path_for(manifest_key(SYNTHETIC_CASELIST, week.snapshot)))


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def imported_data_dir(tmp_path: Path) -> Path:
    """A data directory holding the three imported synthetic weeks."""
    data_dir = tmp_path / "evidence"
    await import_synthetic_weeks(data_dir, tmp_path / "downloads")
    return data_dir
