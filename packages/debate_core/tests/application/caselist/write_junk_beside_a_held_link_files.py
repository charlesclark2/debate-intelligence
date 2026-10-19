"""The files a build leaves after `v1-e30-t25`'s scenario, for another build to read.

Not collected: its name is not a test module's, and it runs only when named, with the variable
`WRITE_JUNK_BESIDE_A_HELD_LINK_FILES` set to the directory to write into. Run it with this task's
source, and again with the start commit's first on `PYTHONPATH`. `read_held_path_files.py`
(`v1-e30-t21`) then reads each set with each build, once `write_held_path_files.py`'s pull scenario
has written the `run/` directory it also reads into the same directory. The commands and what they
printed are in the session report of `v1-e30-t25`.

The scenario: the revised-path store (`v1-e30-t11`) and `caselist remove --source <named-version>`.
An earlier build then imports a weekly of 2026-10-11 holding `KEPT_PATH`'s file, a symbolic link at
the held path and the AppleDouble junk macOS writes beside it, and a weekly of 2026-10-12 with the
same members waits in the inbox. This build publishes the caselist and pushes `manifests/` with
`store sync --apply`; the same removal is run again, which rewrites the waiting archive, and the
first week is imported again. Written: both archives (`archive/`), the takedown's records on this
machine and in the bucket (`records/local/`, `records/bucket/`), every local manifest
(`manifests/`), and the keys of the bucket's manifests and current source objects
(`bucket-manifests.txt`, `bucket-sources.txt`), which name caselists, dates and digests only.

It uses nothing the start commit's source lacks, so the same file runs against both.
"""

from __future__ import annotations

import functools
import os
import shutil
from inspect import signature
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from tests.fixtures.caselist.build_revised_path_archives import CASELIST, REVISED_PATH

from debate_core.application.caselist import publish_service
from debate_core.application.caselist.evidence_listing import held_back_digests
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.evidence_sync import EvidenceSyncService, SyncDirection, SyncKeyspace

from .conftest import RemovalWorld
from .test_held_rows_publish_nothing import WEEK_OF_THE_LINK, an_older_builds_importer, import_archive
from .test_junk_beside_a_held_link import JUNK_OF_THE_HELD_PATH, write_archive
from .test_removal_covers_later_uploads import remove_the_named_file, revised_path_world

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio


def out() -> Path:
    written = os.environ.get("WRITE_JUNK_BESIDE_A_HELD_LINK_FILES")
    assert written, "run by its path with WRITE_JUNK_BESIDE_A_HELD_LINK_FILES naming an empty directory"
    return Path(written)


def store_sync(world: RemovalWorld) -> EvidenceSyncService:
    """`store sync` as the build's own composition root builds it: with the question where it has one."""
    extra: dict[str, Any] = {"held_back": functools.partial(held_back_digests, world.local)}
    ask = getattr(publish_service, "withheld_manifest_reason", None)
    if ask is not None and "withheld_manifests" in signature(EvidenceSyncService).parameters:
        extra["withheld_manifests"] = functools.partial(ask, world.local)
    return EvidenceSyncService(
        suppression=world.suppression(),
        keyspaces=(SyncKeyspace(name="objects", local=world.local.objects, remote=world.bucket),),
        **extra,
    )


async def test_write_what_the_removal_run_again_leaves(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    world = await revised_path_world(tmp_path, s3_client, evidence_bucket)
    await remove_the_named_file(world)
    members = {"links": (REVISED_PATH,), "junk": (JUNK_OF_THE_HELD_PATH,)}
    archive = write_archive(tmp_path / "arriving" / f"{CASELIST}-weekly-2026-10-11.zip", **members)
    await import_archive(world, archive, WEEK_OF_THE_LINK, importer=an_older_builds_importer(world))
    waiting = write_archive(world.data_dir / "inbox" / f"{CASELIST}-weekly-2026-10-12.zip", **members)
    publisher = CaselistPublishService(
        local=world.local, remote=world.bucket, suppression=world.suppression()
    )
    await publisher.execute(await publisher.plan(CASELIST))
    sync = store_sync(world)
    await sync.execute(await sync.plan(prefix=f"manifests/{CASELIST}/", direction=SyncDirection.PUSH))

    await remove_the_named_file(world)
    await import_archive(world, archive, WEEK_OF_THE_LINK)

    target = out()
    (target / "archive").mkdir(parents=True)
    shutil.copyfile(archive, target / "archive" / archive.name)
    shutil.copyfile(waiting, target / "archive" / waiting.name)
    shutil.copytree(world.data_dir / "suppression", target / "records" / "local")
    (target / "records" / "bucket").mkdir(parents=True)
    listed = s3_client.list_objects_v2(Bucket=evidence_bucket, Prefix="manifests/_suppression/")
    for item in listed.get("Contents", []):
        key = str(item.get("Key"))
        body = s3_client.get_object(Bucket=evidence_bucket, Key=key)["Body"].read()
        (target / "records" / "bucket" / key.rsplit("/", 1)[1]).write_bytes(body)
    shutil.copytree(world.data_dir / "objects" / "manifests" / CASELIST, target / "manifests")
    (target / "bucket-manifests.txt").write_text(_keys(world, f"manifests/{CASELIST}/"), encoding="utf-8")
    (target / "bucket-sources.txt").write_text(_keys(world, f"raw/caselist/{CASELIST}/"), encoding="utf-8")


def _keys(world: RemovalWorld, prefix: str) -> str:
    """The bucket's current objects under `prefix`, one key a line: caselists, dates and digests only."""
    listed = world.client.list_objects_v2(Bucket=world.bucket_name, Prefix=prefix)
    return "".join(
        f"{key}\n" for key in sorted(str(item.get("Key", "")) for item in listed.get("Contents", []))
    )
