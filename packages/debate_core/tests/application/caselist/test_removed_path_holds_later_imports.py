"""A removed caselist path holds the uploads that are imported after the removal (`v1-e30-t13`).

`v1-e30-t11` takes down the later uploads the store already holds at a removed file's path. A
revision that reaches the store afterwards was covered by nothing: the importer asked the
suppression list about a member's bytes and its withdrawn disclosures, and a new sha256 at the
removed path is neither. A whole-file removal by `--source` now records the path, and the importer
refuses a new sha256 there.

Everything here is checked on the store after `caselist remove --source <named-version> --execute`
and an import of an archive that arrives afterwards, through the services the commands run, against
moto and a local data directory. The importer is built as `caselist import` builds it: over this
machine's copy of the suppression list, and nothing else. No test asks either service for anything
this task added, so every one also runs against the source as it was before the task, where the
ones about a held upload fail on what that importer stored.

The store is `v1-e30-t11`'s (`tests/fixtures/caselist/build_revised_path_archives.py`), and what
arrives is `tests/fixtures/caselist/build_held_path_archives.py`, whose docstring works each import's
answer out by hand. :data:`EXPECTED_COUNTS` there is what these tests assert.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_held_path_archives import (
    ARRIVING_BODIES,
    EXPECTED_COUNTS,
    arriving_digest_of,
    build_arriving_complete_archive_zips,
    build_arriving_weekly_zips,
)
from tests.fixtures.caselist.build_revised_path_archives import (
    BODIES,
    CASELIST,
    KEPT_PATH,
    ONE_WEEK_PATH,
    OTHER_CASELIST,
    OTHER_TEAM_PATH,
    REVISED_PATH,
    digest_of,
)

from debate_core.application.caselist.evidence_listing import snapshots_before_full_archive
from debate_core.application.caselist.import_service import (
    CaselistImportService,
    Classification,
    ImportReport,
)
from debate_core.application.caselist.manifest import (
    full_archive_manifest_key,
    manifest_key,
    write_manifest,
)
from debate_core.application.caselist.removal_plan import SourceSelector
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.ports.suppression import ReasonCode
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsEvidenceObjectStore, FsSnapshotStore
from debate_core.integrations.local.archive_reader import archive_digest, read_archive
from debate_core.integrations.local.suppression_list import local_suppression_list_file

from .conftest import REQUEST, RemovalWorld
from .test_removal_covers_later_uploads import (
    LIMITS,
    NAMED,
    held_at,
    local_blob,
    member_rows,
    remove_the_named_file,
    revised_path_world,
)

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

UPLOADED_AFTER = arriving_digest_of("uploaded-after-the-removal")
UPLOADED_AFTER_IN_A_COMPLETE_ARCHIVE = arriving_digest_of("uploaded-after-in-a-complete-archive")
UPLOADED_AFTER_AT_TWO_PATHS = arriving_digest_of("uploaded-after-at-two-paths")
UPLOADED_AFTER_AT_ANOTHER_PATH = arriving_digest_of("uploaded-after-at-another-path")
UPLOADED_AFTER_IN_ANOTHER_CASELIST = arriving_digest_of("uploaded-after-in-another-caselist")


@pytest.fixture
async def world(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> RemovalWorld:
    return await revised_path_world(tmp_path, s3_client, evidence_bucket)


# ------------------------------------------------------------------------------------------------
# Importing what arrives
# ------------------------------------------------------------------------------------------------


def offline_importer(world: RemovalWorld) -> CaselistImportService:
    """The importer as `caselist import` builds it: this machine's copy of the list, and no bucket."""
    return CaselistImportService(
        caselists=world.repository,
        blobs=FsSnapshotStore(world.data_dir),
        suppression=RecordedSuppressionList(local_suppression_list_file(world.data_dir)),
    )


async def import_weekly(
    world: RemovalWorld,
    scratch: Path,
    caselist: str,
    week: date,
    *,
    dry_run: bool = False,
    allow_out_of_order: bool = False,
    importer: CaselistImportService | None = None,
) -> ImportReport:
    """Import one weekly archive and write its manifest, as `caselist import` does."""
    built = {**_revised(scratch), **build_arriving_weekly_zips(scratch / "arriving")}
    archive = built[(caselist, week)]
    report = await (importer or offline_importer(world)).import_archive(
        read_archive(archive, **LIMITS),
        caselist=caselist,
        snapshot=week,
        event=Event.LD,
        archive_sha256=archive_digest(archive),
        dry_run=dry_run,
        allow_out_of_order=allow_out_of_order,
    )
    if not dry_run:
        write_manifest(report, FsEvidenceObjectStore(world.data_dir).path_for(manifest_key(caselist, week)))
    return report


def _revised(scratch: Path) -> dict[tuple[str, date], Path]:
    """The archives the store was built from, where `revised_path_world` put them."""
    downloads = scratch / "downloads"
    return {
        (caselist, date.fromisoformat(path.stem.rsplit("-weekly-", 1)[1])): path
        for path in sorted(downloads.glob("*-weekly-*.zip"))
        for caselist in [path.stem.rsplit("-weekly-", 1)[0]]
    }


async def import_complete_archive(world: RemovalWorld, scratch: Path, day: date) -> ImportReport:
    """Import the arriving complete archive and write its manifest, as `caselist import --full` does."""
    archive = build_arriving_complete_archive_zips(scratch / "arriving")[(CASELIST, day)]
    previous, earlier = await snapshots_before_full_archive(world.local, CASELIST, day)
    report = await offline_importer(world).import_full_archive(
        read_archive(archive, **LIMITS),
        caselist=CASELIST,
        archive_date=day,
        event=Event.LD,
        archive_sha256=archive_digest(archive),
        previous=previous,
        earlier=earlier,
    )
    write_manifest(
        report, FsEvidenceObjectStore(world.data_dir).path_for(full_archive_manifest_key(CASELIST, day))
    )
    return report


def counts(report: ImportReport) -> dict[str, int]:
    """Every classification the import counted at least once."""
    return {str(name): report.count(name) for name in Classification if report.count(name)}


def manifest_rows(world: RemovalWorld, key: str) -> list[dict[str, object]]:
    return member_rows(FsEvidenceObjectStore(world.data_dir).path_for(key).read_text(encoding="utf-8"))


def manifest_summary(world: RemovalWorld, key: str) -> dict[str, object]:
    lines = FsEvidenceObjectStore(world.data_dir).path_for(key).read_text(encoding="utf-8").splitlines()
    (summary,) = [row for row in map(json.loads, lines) if row["kind"] == "summary"]
    return summary


async def nothing_of_it_is_stored(world: RemovalWorld, digest: str) -> None:
    assert not local_blob(world, digest).exists(), "its bytes were stored"
    assert await world.repository.find_source(digest) is None, "a source document was filed for it"
    assert not (await world.repository.list_disclosures(source_sha256=digest, limit=10)).items


# ------------------------------------------------------------------------------------------------
# ac1: a new sha256 at the removed path is refused, in a weekly and in a complete archive
# ------------------------------------------------------------------------------------------------


async def test_a_new_upload_at_the_removed_path_in_a_later_weekly_is_refused(
    world: RemovalWorld, tmp_path: Path
) -> None:
    await remove_the_named_file(world)

    report = await import_weekly(world, tmp_path, CASELIST, date(2026, 10, 8))

    assert counts(report) == EXPECTED_COUNTS["testcl26 weekly 2026-10-08"]
    await nothing_of_it_is_stored(world, UPLOADED_AFTER)
    key = manifest_key(CASELIST, date(2026, 10, 8))
    assert held_at(manifest_rows(world, key), REVISED_PATH) == set(), "a row would name the removed path"
    assert manifest_summary(world, key)["classifications"] == EXPECTED_COUNTS["testcl26 weekly 2026-10-08"]


async def test_a_new_upload_at_the_removed_path_in_a_later_complete_archive_is_refused(
    world: RemovalWorld, tmp_path: Path
) -> None:
    await remove_the_named_file(world)

    report = await import_complete_archive(world, tmp_path, date(2026, 10, 9))

    assert counts(report) == EXPECTED_COUNTS["testcl26 complete 2026-10-09"]
    await nothing_of_it_is_stored(world, UPLOADED_AFTER_IN_A_COMPLETE_ARCHIVE)
    key = full_archive_manifest_key(CASELIST, date(2026, 10, 9))
    assert held_at(manifest_rows(world, key), REVISED_PATH) == set()
    assert held_at(manifest_rows(world, key), KEPT_PATH) == {digest_of("kept")}


async def test_a_dry_run_counts_the_held_upload_and_writes_nothing(
    world: RemovalWorld, tmp_path: Path
) -> None:
    await remove_the_named_file(world)
    before = world.tree()

    report = await import_weekly(world, tmp_path, CASELIST, date(2026, 10, 8), dry_run=True)

    assert counts(report) == EXPECTED_COUNTS["testcl26 weekly 2026-10-08"]
    assert world.tree() == before


# ------------------------------------------------------------------------------------------------
# The hold is one caselist's one path, for uploads dated after the removed file first appeared
# ------------------------------------------------------------------------------------------------


async def test_an_upload_at_another_path_the_same_week_is_stored(world: RemovalWorld, tmp_path: Path) -> None:
    await remove_the_named_file(world)

    await import_weekly(world, tmp_path, CASELIST, date(2026, 10, 8))

    stored = local_blob(world, UPLOADED_AFTER_AT_ANOTHER_PATH).read_bytes()
    assert stored == ARRIVING_BODIES["uploaded-after-at-another-path"]
    rows = manifest_rows(world, manifest_key(CASELIST, date(2026, 10, 8)))
    assert held_at(rows, ONE_WEEK_PATH) == {UPLOADED_AFTER_AT_ANOTHER_PATH}


async def test_the_same_bytes_at_another_teams_path_are_stored_and_only_the_held_path_is_refused(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """The hold is on the path, not on the bytes: another team's disclosure of them is theirs."""
    await remove_the_named_file(world)
    await import_weekly(world, tmp_path, CASELIST, date(2026, 10, 8))

    report = await import_weekly(world, tmp_path, CASELIST, date(2026, 10, 10))

    assert counts(report) == EXPECTED_COUNTS["testcl26 weekly 2026-10-10"]
    stored = local_blob(world, UPLOADED_AFTER_AT_TWO_PATHS).read_bytes()
    assert stored == ARRIVING_BODIES["uploaded-after-at-two-paths"]
    rows = manifest_rows(world, manifest_key(CASELIST, date(2026, 10, 10)))
    assert held_at(rows, OTHER_TEAM_PATH) == {UPLOADED_AFTER_AT_TWO_PATHS}
    assert held_at(rows, REVISED_PATH) == set()
    disclosed = (
        await world.repository.list_disclosures(source_sha256=UPLOADED_AFTER_AT_TWO_PATHS, limit=10)
    ).items
    assert [one.source_path for one in disclosed] == [OTHER_TEAM_PATH]


async def test_the_same_spelling_of_the_path_in_another_caselist_is_not_held(
    world: RemovalWorld, tmp_path: Path
) -> None:
    await remove_the_named_file(world)

    report = await import_weekly(world, tmp_path, OTHER_CASELIST, date(2026, 10, 8))

    assert counts(report) == EXPECTED_COUNTS["testclb26 weekly 2026-10-08"]
    stored = local_blob(world, UPLOADED_AFTER_IN_ANOTHER_CASELIST).read_bytes()
    assert stored == ARRIVING_BODIES["uploaded-after-in-another-caselist"]
    rows = manifest_rows(world, manifest_key(OTHER_CASELIST, date(2026, 10, 8)))
    assert held_at(rows, REVISED_PATH) == {UPLOADED_AFTER_IN_ANOTHER_CASELIST}


async def test_an_archive_dated_before_the_removed_file_first_appeared_imports_as_it_did(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """The weekly of `2026-09-01` holds the earlier version at the path, which no request covers.

    Importing it again must leave its manifest byte for byte as it was (`v1-e30-t03` ac3).
    """
    key = manifest_key(CASELIST, date(2026, 9, 1))
    manifest = FsEvidenceObjectStore(world.data_dir).path_for(key)
    await remove_the_named_file(world)
    before = manifest.read_bytes()

    report = await import_weekly(world, tmp_path, CASELIST, date(2026, 9, 1), allow_out_of_order=True)

    assert report.count(Classification.SUPPRESSED) == 0
    assert manifest.read_bytes() == before
    assert held_at(manifest_rows(world, key), REVISED_PATH) == {digest_of("earlier-version")}
    assert local_blob(world, digest_of("earlier-version")).read_bytes() == BODIES["earlier-version"]


# ------------------------------------------------------------------------------------------------
# ac3: --only-named writes no hold, and so does a removal that removes nothing whole
# ------------------------------------------------------------------------------------------------


async def test_after_only_named_a_later_upload_at_the_path_imports(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """A request explicitly about one version: what the team uploads at the path afterwards is theirs."""
    service = world.service()
    plan = await service.plan(
        SourceSelector(NAMED), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM, only_named=True
    )
    assert (await service.execute(plan)).completed

    report = await import_weekly(world, tmp_path, CASELIST, date(2026, 10, 8))

    assert report.count(Classification.SUPPRESSED) == 0
    assert local_blob(world, UPLOADED_AFTER).read_bytes() == ARRIVING_BODIES["uploaded-after-the-removal"]
    rows = manifest_rows(world, manifest_key(CASELIST, date(2026, 10, 8)))
    assert held_at(rows, REVISED_PATH) == {UPLOADED_AFTER}
    disclosed = (await world.repository.list_disclosures(source_sha256=UPLOADED_AFTER, limit=10)).items
    assert [one.source_path for one in disclosed] == [REVISED_PATH]
