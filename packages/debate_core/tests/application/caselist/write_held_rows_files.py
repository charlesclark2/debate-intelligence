"""The files a build leaves after `v1-e30-t22`'s scenario, for another build to read.

Not collected: its name is not a test module's, and it runs only when named, with the variable
`WRITE_HELD_ROWS_FILES` set to the directory to write into. Run it with this task's source, and
again with the start commit's first on `PYTHONPATH`. `read_held_path_files.py` (`v1-e30-t21`) then
reads each set with each build, once `write_held_path_files.py`'s pull scenario has written the
`run/` directory it also reads into the same directory. The commands and what they printed are in
the session report of `v1-e30-t22`.

The scenario: the revised-path store (`v1-e30-t11`) and `caselist remove --source <named-version>`.
An earlier build then imports the weekly of 2026-10-08, with its upload at the held path, and a
weekly of 2026-10-11 holding `KEPT_PATH`'s file and a symbolic link at the held path. This build
publishes the caselist, the same removal is run again, and the week with the link is imported
again. Written: that week's archive (`archive/`), the takedown's records on this machine and in the
bucket (`records/local/`, `records/bucket/`), every local manifest (`manifests/`), and the keys of
the bucket's current source objects (`bucket-sources.txt`), which name digests only.

It uses nothing the start commit's source lacks, so the same file runs against both.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_revised_path_archives import CASELIST

from debate_core.application.caselist.publish_service import CaselistPublishService

from .conftest import RemovalWorld
from .test_held_path_loose_ends import an_older_build_imports_next_week
from .test_held_rows_publish_nothing import (
    WEEK_OF_THE_LINK,
    a_week_with_a_link,
    an_older_builds_importer,
    import_archive,
)
from .test_removal_covers_later_uploads import remove_the_named_file, revised_path_world

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio


def out() -> Path:
    written = os.environ.get("WRITE_HELD_ROWS_FILES")
    assert written, "run by its path with WRITE_HELD_ROWS_FILES naming an empty directory"
    return Path(written)


async def test_write_what_the_removal_run_again_leaves(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    world = await revised_path_world(tmp_path, s3_client, evidence_bucket)
    await remove_the_named_file(world)
    await an_older_build_imports_next_week(world, tmp_path, publish=False)
    archive = a_week_with_a_link(tmp_path)
    await import_archive(world, archive, WEEK_OF_THE_LINK, importer=an_older_builds_importer(world))
    publisher = CaselistPublishService(
        local=world.local, remote=world.bucket, suppression=world.suppression()
    )
    await publisher.execute(await publisher.plan(CASELIST))
    target = out()
    target.mkdir(parents=True, exist_ok=True)
    (target / "bucket-sources-after-the-publish.txt").write_text(_source_keys(world), encoding="utf-8")

    await remove_the_named_file(world)
    await import_archive(world, archive, WEEK_OF_THE_LINK)

    (target / "archive").mkdir()
    shutil.copyfile(archive, target / "archive" / archive.name)
    shutil.copytree(world.data_dir / "suppression", target / "records" / "local")
    (target / "records" / "bucket").mkdir(parents=True)
    listed = s3_client.list_objects_v2(Bucket=evidence_bucket, Prefix="manifests/_suppression/")
    for item in listed.get("Contents", []):
        key = str(item.get("Key"))
        body = s3_client.get_object(Bucket=evidence_bucket, Key=key)["Body"].read()
        (target / "records" / "bucket" / key.rsplit("/", 1)[1]).write_bytes(body)
    shutil.copytree(world.data_dir / "objects" / "manifests" / CASELIST, target / "manifests")
    (target / "bucket-sources.txt").write_text(_source_keys(world), encoding="utf-8")


def _source_keys(world: RemovalWorld) -> str:
    """The bucket's current source objects of the caselist, one key a line: digests only."""
    listed = world.client.list_objects_v2(Bucket=world.bucket_name, Prefix=f"raw/caselist/{CASELIST}/")
    return "".join(
        f"{key}\n" for key in sorted(str(item.get("Key", "")) for item in listed.get("Contents", []))
    )
