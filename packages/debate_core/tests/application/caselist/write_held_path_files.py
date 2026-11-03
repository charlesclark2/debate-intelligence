"""The files a build leaves after `v1-e30-t21`'s scenarios, for another build to read.

Not collected: its name is not a test module's, and it runs only when named, with the variable
`WRITE_HELD_PATH_FILES` set to the directory to write into. Run it with this task's source, and
again with the start commit's first on `PYTHONPATH`; `read_held_path_files.py` then reads each set
with each build. The commands and what they printed are in the session report of `v1-e30-t21`.

Two scenarios, each the one a test of this task runs:

* **The removal.** The revised-path store (`v1-e30-t11`), with a weekly waiting in the download inbox
  that holds `KEPT_PATH`'s file and a symbolic link at the removed path, and the weekly of
  2026-10-08 imported after the removal by this build's importer, which refuses its upload at the
  held path. Written: the waiting archive as the removal left it (`archive/`), the takedown's
  records on this machine and in the bucket (`records/local/`, `records/bucket/`), and every local
  manifest (`manifests/`).
* **The pull.** The three synthetic weeks, the Bayview negative removed by `--source`, and a pull of
  week four, which holds only the re-upload at the held path and the AppleDouble file naming it.
  Written: the run's record and its details, as the run log keeps them (`run/`).

It uses nothing the start commit lacks, so the same file runs against both.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import zipfile
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_revised_path_archives import BODIES, CASELIST, KEPT_PATH, REVISED_PATH
from tests.fixtures.caselist.build_synthetic_archives import (
    DOCUMENT_BODIES,
    _docx,  # pyright: ignore[reportPrivateUsage]
)

from debate_core.application.caselist.removal_plan import SourceSelector
from debate_core.application.ports.suppression import ReasonCode
from debate_core.application.sync_runs import details_for_summary, record_for_summary

from .conftest import REQUEST, RemovalWorld
from .test_inbox_retention import ExpiredBucket, FakeSource, Installation
from .test_removal_covers_later_uploads import remove_the_named_file, revised_path_world
from .test_removed_path_holds_later_imports import import_weekly

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

WAITING = f"{CASELIST}-weekly-2026-10-11.zip"
WEEK_4 = date(2026, 9, 22)
BAYVIEW_PATH = "Maple Grove/QX/Maple Grove-QX-Neg-Bayview Open [2]-Semis.docx"


def out() -> Path:
    written = os.environ.get("WRITE_HELD_PATH_FILES")
    assert written, "run by its path with WRITE_HELD_PATH_FILES naming an empty directory"
    return Path(written)


def a_waiting_archive_with_a_link(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(zipfile.ZipInfo(KEPT_PATH, date_time=(1980, 1, 1, 0, 0, 0)), BODIES["kept"])
        link = zipfile.ZipInfo(REVISED_PATH, date_time=(1980, 1, 1, 0, 0, 0))
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, b"Alder Point-KR-Aff-Lakeshore Open-Round 1.docx")


async def test_write_what_the_removal_leaves(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    world = await revised_path_world(tmp_path, s3_client, evidence_bucket)
    a_waiting_archive_with_a_link(world.data_dir / "inbox" / WAITING)
    await remove_the_named_file(world)
    await import_weekly(world, tmp_path, CASELIST, date(2026, 10, 8))

    target = out()
    (target / "archive").mkdir(parents=True)
    shutil.copyfile(world.data_dir / "inbox" / WAITING, target / "archive" / WAITING)
    shutil.copytree(world.data_dir / "suppression", target / "records" / "local")
    (target / "records" / "bucket").mkdir(parents=True)
    listed = s3_client.list_objects_v2(Bucket=evidence_bucket, Prefix="manifests/_suppression/")
    for item in listed.get("Contents", []):
        key = str(item.get("Key"))
        body = s3_client.get_object(Bucket=evidence_bucket, Key=key)["Body"].read()
        (target / "records" / "bucket" / key.rsplit("/", 1)[1]).write_bytes(body)
    shutil.copytree(world.data_dir / "objects" / "manifests" / CASELIST, target / "manifests")


async def test_write_what_the_pull_leaves(removal_world: RemovalWorld, tmp_path: Path) -> None:
    bayview = hashlib.sha256(DOCUMENT_BODIES["bayview-semis-neg"]).hexdigest()
    service = removal_world.service()
    plan = await service.plan(
        SourceSelector(bayview), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM
    )
    assert (await service.execute(plan)).completed
    week_four = tmp_path / "published" / f"{CASELIST}-weekly-{WEEK_4.isoformat()}.zip"
    week_four.parent.mkdir(parents=True)
    with zipfile.ZipFile(week_four, "w") as archive:
        archive.writestr(f"testcl26-0922/{BAYVIEW_PATH}", _docx(("Bayview Open, semifinal.", "Again.")))
        archive.writestr(
            f"testcl26-0922/__MACOSX/Maple Grove/QX/._{BAYVIEW_PATH.rsplit('/', 1)[1]}", b"\x00\x05\x16\x07"
        )
    installation = Installation(
        data_dir=removal_world.data_dir,
        bucket=removal_world.bucket,
        archives={WEEK_4: week_four},
        suppression=removal_world.suppression(),
    )
    summary = await installation.sync(
        FakeSource(installation.archives, weeks=[WEEK_4]),
        publish_to=ExpiredBucket(),
        compare_with=ExpiredBucket(),
    ).run([CASELIST])

    target = out() / "run"
    target.mkdir(parents=True)
    record = record_for_summary(summary, environment="dev", mode="run")
    (target / "record.jsonl").write_text(record.model_dump_json() + "\n", encoding="utf-8")
    (target / "details.jsonl").write_text(
        details_for_summary(summary).model_dump_json() + "\n", encoding="utf-8"
    )
    (target / "inbox.txt").write_text("\n".join(sorted(installation.inbox_names())) + "\n", encoding="utf-8")
