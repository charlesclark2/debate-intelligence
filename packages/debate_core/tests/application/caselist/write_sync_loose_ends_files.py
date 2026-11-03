"""The run records and details this build leaves after `v1-e34-t23`'s scenarios, for older builds to read.

Not collected: its name is not a test module's, and it runs only when named, with the variable
`WRITE_SYNC_LOOSE_ENDS_FILES` set to the directory to write into. `read_sync_run_files.py` then
reads what it wrote with each build: this one, the start commit's, and the agent's installed build,
each from its own source exported with `git archive` and put first on `PYTHONPATH`. The commands
and what they printed are in the session report of `v1-e34-t23`.

Each scenario is a pull through the real run monitor, as the command runs it, in an installation of
its own. Written for each, under `<scenario>/`: the run log, the run's details, the file of records
still owed to the bucket when there is one, and every object the run put under `reports/` in the
bucket (`bucket.json`, key to body). The scenarios are the ones whose records and details this task
changed:

* `report_drift_before_an_expiry`: the report stage pending, with an earlier finding and its drift.
* `manifest_mismatch_alone`: the report stage failed on a manifest mismatch, with its drift.
* `held_upload_refused`: an import that met a removal's hold, counted by request in the details.
* `lock_held_by_another_run`: a run refused by the run lock, with no stage.
* `publish_refused_with_its_runbook`: a refused publish whose reason keeps its runbook pointer.
* `complete_archive_imported`: an import stage's reason naming a complete archive, `full/<date>`.
* `bucket_not_built`: a run refused before any stage whose record is owed to the bucket.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_synthetic_archives import build_snapshot_zips

from debate_core.application.caselist_sync import LOCK_FILENAME, RunLock
from debate_core.application.sync_runs import (
    PENDING_RECORDS_FILENAME,
    SYNC_RUN_DETAILS_FILENAME,
    SYNC_RUN_LOG_FILENAME,
)
from debate_core.integrations.s3 import S3EvidenceObjectStore

from . import test_inbox_retention as inbox_retention
from .conftest import RemovalWorld
from .run_record_scenarios import World, a_publish_the_bucket_refused_with_the_adapters_fix
from .test_held_path_inbox_copies import WEEK_4, installation_of, remove_bayview, week_four
from .test_inbox_retention import CASELIST, WEEK_1, WEEK_2, FakeSource, Installation
from .test_pull_contains_unreadable_local_files import TwoCaselists, complete_archive_name
from .test_sync_report_stage_keeps_what_it_found_and_its_kind import ScriptedComparison

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

REPORTS_PREFIX = "reports/"


def out() -> Path:
    where = os.environ.get("WRITE_SYNC_LOOSE_ENDS_FILES")
    if not where:
        pytest.skip("set WRITE_SYNC_LOOSE_ENDS_FILES to the directory to write into")
    return Path(where)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def world(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str, monkeypatch: pytest.MonkeyPatch
) -> World:
    def set_clock(moment: datetime) -> None:
        monkeypatch.setattr(inbox_retention, "RUN_CLOCK", moment)

    return World(
        installation=Installation(
            data_dir=tmp_path / "evidence",
            bucket=S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client),
            archives=build_snapshot_zips(tmp_path / "published"),
        ),
        s3_client=s3_client,
        bucket_name=evidence_bucket,
        scratch=tmp_path,
        set_clock=set_clock,
    )


def keep(name: str, data_dir: Path, s3_client: S3Client, bucket: str) -> None:
    """Copy what the run left, as it left it, into `<out>/<name>/`."""
    destination = out() / name
    shutil.rmtree(destination, ignore_errors=True)
    destination.mkdir(parents=True)
    for filename in (SYNC_RUN_LOG_FILENAME, SYNC_RUN_DETAILS_FILENAME, PENDING_RECORDS_FILENAME):
        if (data_dir / filename).is_file():
            shutil.copyfile(data_dir / filename, destination / filename)
    listed = s3_client.list_objects_v2(Bucket=bucket, Prefix=REPORTS_PREFIX).get("Contents", [])
    objects = {
        str(one.get("Key")): s3_client.get_object(Bucket=bucket, Key=str(one.get("Key")))["Body"]
        .read()
        .decode()
        for one in listed
    }
    (destination / "bucket.json").write_text(json.dumps(objects, indent=2, sort_keys=True) + "\n", "utf-8")


async def test_report_drift_before_an_expiry(world: World) -> None:
    out()
    comparison = ScriptedComparison(world.installation, source_differs=(WEEK_1,), expires_at=2)
    source = FakeSource(world.installation.archives, weeks=[WEEK_1, WEEK_2])
    await world.pull(world.installation.sync(source, status=comparison))
    keep("report_drift_before_an_expiry", world.installation.data_dir, world.s3_client, world.bucket_name)


async def test_manifest_mismatch_alone(world: World) -> None:
    out()
    comparison = ScriptedComparison(world.installation, manifest_differs=(WEEK_1,))
    source = FakeSource(world.installation.archives, weeks=[WEEK_1, WEEK_2])
    await world.pull(world.installation.sync(source, status=comparison))
    keep("manifest_mismatch_alone", world.installation.data_dir, world.s3_client, world.bucket_name)


async def test_held_upload_refused(
    removal_world: RemovalWorld, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out()
    await remove_bayview(removal_world)
    installation = installation_of(removal_world, week_four(tmp_path / "published", another_teams_file=True))
    assert isinstance(removal_world.bucket, S3EvidenceObjectStore)
    world = World(
        installation=installation,
        s3_client=removal_world.bucket._client,  # pyright: ignore[reportPrivateUsage]
        bucket_name=removal_world.bucket._bucket,  # pyright: ignore[reportPrivateUsage]
        scratch=tmp_path,
        set_clock=lambda moment: monkeypatch.setattr(inbox_retention, "RUN_CLOCK", moment),
    )
    await world.pull(installation.sync(FakeSource(installation.archives, weeks=[WEEK_4])))
    keep("held_upload_refused", installation.data_dir, world.s3_client, world.bucket_name)


async def test_lock_held_by_another_run(world: World) -> None:
    out()
    world.installation.data_dir.mkdir(parents=True)
    with RunLock(world.installation.data_dir / LOCK_FILENAME):
        await world.pull(world.installation.sync(FakeSource(world.installation.archives, weeks=[WEEK_1])))
    keep("lock_held_by_another_run", world.installation.data_dir, world.s3_client, world.bucket_name)


async def test_publish_refused_with_its_runbook(world: World) -> None:
    out()
    await a_publish_the_bucket_refused_with_the_adapters_fix(world)
    keep("publish_refused_with_its_runbook", world.installation.data_dir, world.s3_client, world.bucket_name)


async def test_complete_archive_imported(world: World) -> None:
    """A complete archive already in the inbox is imported from there with the rotation off."""
    out()
    world.installation.inbox.mkdir(parents=True)
    shutil.copyfile(
        world.installation.archives[WEEK_1], world.installation.inbox / complete_archive_name(CASELIST)
    )
    source = TwoCaselists(world.installation.archives, weeks_of={CASELIST: [WEEK_1]}, complete=[CASELIST])
    await world.pull(world.installation.sync(source))
    keep("complete_archive_imported", world.installation.data_dir, world.s3_client, world.bucket_name)


async def test_bucket_not_built(world: World) -> None:
    out()
    await world.pull_with_no_bucket()
    keep("bucket_not_built", world.installation.data_dir, world.s3_client, world.bucket_name)
