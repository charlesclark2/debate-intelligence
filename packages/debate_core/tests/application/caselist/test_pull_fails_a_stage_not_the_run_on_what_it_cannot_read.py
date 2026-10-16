"""What a pull cannot read fails a stage under the code that says so, never the run (`v1-e34-t23`).

Two loose ends `v1-e34-t19` left:

* **A camp download that cannot be read** (item 4). A weekly or a complete archive in the inbox
  that the operating system will not open is `UNREADABLE_ARCHIVE` (`v1-e34-t19`). A camp download
  that this run fetched and then could not read was still recorded by its class: the import read
  its bytes, or handed the zip to the reader, outside that translation, so the `OSError` reached
  the stage as itself and was recorded as `INTERNAL_ERROR`, "a bug". It is now the same
  `UNREADABLE_ARCHIVE` as a weekly's, named by its OpenEv id and digest and never by its title.
* **A weekly manifest with a torn line** (item 5). The selection read every weekly manifest whole,
  every row of it, to learn one thing: the newest week this machine holds, which the manifest's
  name already says. A row cut short stopped the run there, before any stage, exit `1`. The
  selection now reads the name, and the stage that needs the rows is the one that fails on them:
  the publish of the week the manifest describes, and the import of a week after it, whose
  first-seen count is measured against it. A manifest this user may not open still stops the
  selection, as before (`v1-e34-t19`): what is held cannot be known without opening it.

Every expected code and sentence is written by hand from what each test sets up.
"""

from __future__ import annotations

import errno
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_synthetic_archives import build_snapshot_zips
from tests.fixtures.permissions import needs_permissions

from debate_core.application.caselist_sync import SyncStage
from debate_core.application.ports.caselist_source import DownloadedFile, OpenEvFile, openev_inbox_name
from debate_core.integrations.s3 import S3EvidenceObjectStore

from .test_inbox_retention import (
    CASELIST,
    ESTUARY,
    ESTUARY_BODY,
    RELEASE,
    RELEASE_BODY,
    WEEK_1,
    WEEK_2,
    ExpiredBucket,
    FakeSource,
    Installation,
    backlog,
    sha256_label,
    weekly_name,
)
from .test_pending_work_owes_every_unpublished_snapshot import confirmed_in, owed
from .test_pull_contains_unreadable_local_files import A_LINE_NOBODY_CAN_READ, WEEK_1_MANIFEST, tear
from .test_pull_stage_failure_codes import assert_names_nothing_of_this_machine, pull, stage

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def installation(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> Installation:
    return Installation(
        data_dir=tmp_path / "evidence",
        bucket=S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client),
        archives=build_snapshot_zips(tmp_path / "published"),
    )


# ------------------------------------------------------------------------------------------------
# Item 4: a camp download that cannot be read
# ------------------------------------------------------------------------------------------------


class LandsUnreadable(FakeSource):
    """OpenCaselist delivers the camp file whole, and this machine then will not let it be read:
    the download is fetched and hashed, and the import cannot open it."""

    async def download_openev(self, file: OpenEvFile, inbox: Path) -> DownloadedFile:
        downloaded = await super().download_openev(file, inbox)
        downloaded.path.chmod(0)
        return downloaded


@needs_permissions
@pytest.mark.parametrize(
    ("camp_file", "body"),
    [
        pytest.param(ESTUARY, ESTUARY_BODY, id="a single document"),
        pytest.param(RELEASE, RELEASE_BODY, id="a release zip"),
    ],
)
async def test_a_camp_download_that_cannot_be_read_fails_its_import_as_unreadable_and_not_as_a_bug(
    installation: Installation, camp_file: OpenEvFile, body: bytes
) -> None:
    source = LandsUnreadable(installation.archives, weeks=[WEEK_1], openev=[(camp_file, body)])
    try:
        watched = await pull(installation, installation.sync(source))
    finally:
        (installation.inbox / openev_inbox_name(camp_file)).chmod(0o600)

    summary = watched.summary
    imported = stage(summary, SyncStage.IMPORT)
    assert imported["outcome"] == "failed"
    assert imported["error_codes"] == ["UNREADABLE_ARCHIVE"]
    assert imported["reason"] == (
        f"1 imported; 1 refused: openev-{camp_file.openev_id} ({sha256_label(body)}): the download "
        f"cannot be read as an archive: the file in the inbox could not be read "
        f"(PermissionError (errno {errno.EACCES}))"
    )
    assert summary.failure_codes == ("UNREADABLE_ARCHIVE",)
    assert summary.snapshots_imported == (f"{CASELIST} {WEEK_1.isoformat()}",), "the week is imported"
    assert camp_file.filename is not None and camp_file.filename not in str(imported["reason"])
    assert_names_nothing_of_this_machine(summary, installation)


# ------------------------------------------------------------------------------------------------
# Item 5: a weekly manifest with a torn line
# ------------------------------------------------------------------------------------------------


async def test_a_torn_manifest_of_a_week_still_owed_fails_its_publish_and_the_run_goes_on(
    installation: Installation, s3_client: S3Client, evidence_bucket: str
) -> None:
    """Week one is owed from a run whose session had expired, and its manifest then gains a line
    nobody can read. The whole run used to stop at the selection, exit `1`, before week two was
    fetched. Now the selection knows week one is held by its manifest's name, week two is fetched,
    imported and published, and the publish stage fails on week one alone, which stays owed."""
    first = FakeSource(installation.archives, weeks=[WEEK_1])
    await installation.sync(first, publish_to=ExpiredBucket()).run([CASELIST])
    assert owed(installation) == [f"{CASELIST} {WEEK_1.isoformat()}"]
    tear(installation.data_dir / WEEK_1_MANIFEST)
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])

    watched = await pull(installation, installation.sync(source))

    summary = watched.summary
    assert stage(summary, SyncStage.SELECT)["outcome"] == "completed"
    assert source.archive_fetches == [weekly_name(WEEK_2)], "week one is held: it is not fetched again"
    assert summary.snapshots_imported == (f"{CASELIST} {WEEK_2.isoformat()}",)
    published = stage(summary, SyncStage.PUBLISH)
    assert published["outcome"] == "failed"
    assert published["error_codes"] == ["UNREADABLE_MANIFEST"]
    assert A_LINE_NOBODY_CAN_READ not in str(published["reason"]), "the row itself is never quoted"
    assert summary.failure_codes == ("UNREADABLE_MANIFEST",)
    assert confirmed_in(s3_client, evidence_bucket) == [f"{CASELIST} {WEEK_2.isoformat()}"]
    assert owed(installation) == [f"{CASELIST} {WEEK_1.isoformat()}"]
    record = watched.pulled.record
    assert record is not None
    assert (record.outcome, record.error_class) == ("failed", None), "a failed stage, not a stopped run"
    assert_names_nothing_of_this_machine(summary, installation)


async def test_a_torn_manifest_of_the_newest_week_fails_the_import_of_the_week_after_it(
    installation: Installation,
) -> None:
    """Week one is imported and published, and its manifest then gains a line nobody can read.
    The importer the composition root builds measures week two's first-seen count against week
    one's manifest, so that import fails on it, under its own code. The selection used to fail on
    it first, with no stage at all."""
    await backlog(installation, WEEK_1)
    tear(installation.data_dir / WEEK_1_MANIFEST)
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])

    watched = await pull(installation, installation.sync(source, measure_first_seen=True))

    summary = watched.summary
    assert stage(summary, SyncStage.SELECT)["outcome"] == "completed"
    assert source.archive_fetches == [weekly_name(WEEK_2)]
    imported = stage(summary, SyncStage.IMPORT)
    assert imported["outcome"] == "failed"
    assert imported["error_codes"] == ["UNREADABLE_MANIFEST"]
    assert summary.failure_codes == ("UNREADABLE_MANIFEST",)
    assert summary.snapshots_imported == ()
    assert weekly_name(WEEK_2) in installation.inbox_names(), "kept for the run after the repair"
    assert_names_nothing_of_this_machine(summary, installation)


@needs_permissions
async def test_a_manifest_this_user_cannot_open_still_stops_the_selection(installation: Installation) -> None:
    """Unchanged (`v1-e34-t19`): a refusal is not a torn line. Without opening the file nobody can
    say what this machine holds, so the run stops before anything is fetched."""
    await backlog(installation, WEEK_1)
    source = FakeSource(installation.archives, weeks=[WEEK_1, WEEK_2])
    manifest = installation.data_dir / WEEK_1_MANIFEST
    manifest.chmod(0)
    try:
        with pytest.raises(Exception) as stopped:
            await installation.sync(source).run([CASELIST])
    finally:
        manifest.chmod(0o600)

    assert type(stopped.value).__name__ == "LocalStoreAccessDenied"
    assert source.archive_fetches == []
