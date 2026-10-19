"""`caselist status` names an earlier build's parsed file of a held upload (`v1-e31-t26` ac2).

A build from before `v1-e30-t13` imported an upload at a path a removal holds, and its
`caselist parse --publish` put the upload's parsed file in the bucket under `parsed/<caselist>/`.
This build's parse publishes no such file (`test_caselist_parse_held_uploads.py`), and the one
already there is named by the comparison: by its caselist, its digest and the request holding the
path, never by the path, and beside the verdict, like every other thing a hold says is owed. The
same removal run again takes it, with every version.

The store and the removal are `v1-e30-t21`'s and `v1-e30-t22`'s (`test_held_path_loose_ends.py`,
`test_held_rows_publish_nothing.py`): `caselist remove --source <named-version>` holds
`(testcl26, REVISED_PATH)` for snapshots dated after `2026-09-08`, and an older build imports the
weekly of `2026-10-08`, with `uploaded-after-the-removal` at the held path and nowhere else, and
publishes it. Its parsed file is put where that build's `caselist parse --publish` puts one, here
and in the bucket, twice so that it has a noncurrent version.

Every test runs offline: moto for the bucket, a temporary data directory, and a temporary `HOME`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_revised_path_archives import CASELIST, REVISED_PATH

from debate_core.application.caselist.status_service import CaselistStatusReport, HeldParsedObject
from debate_core.application.ports.parsed_store import source_object_key

from .conftest import REQUEST, RemovalWorld
from .test_held_path_loose_ends import (
    UPLOADED_AFTER,
    UPLOADED_AFTER_AT_TWO_PATHS,
    an_older_build_imports_next_week,
    status_service,
)
from .test_held_rows_publish_nothing import TWO_PATHS_WEEK, an_older_builds_importer
from .test_removal_covers_later_uploads import (
    NAMES,
    PARSED_VERSION,
    remove_the_named_file,
    revised_path_world,
)
from .test_removed_path_holds_later_imports import import_weekly

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def temporary_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A `HOME` of this test's own, so nothing here can read or write the operator's."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


@pytest.fixture
async def world(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> RemovalWorld:
    return await revised_path_world(tmp_path, s3_client, evidence_bucket)


def an_earlier_builds_parse_publishes(world: RemovalWorld, digest: str) -> str:
    """The parsed file of `digest`, here and in the bucket, as an earlier build's `caselist parse
    --publish` leaves it; returns its bucket key. Its contents are a placeholder: status and the
    removal read the key alone."""
    name = source_object_key(CASELIST, PARSED_VERSION, digest)
    local = world.data_dir / "parsed" / name
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text('{"placeholder": true}\n', encoding="utf-8")
    for body in (b'{"placeholder": 1}\n', b'{"placeholder": 2}\n'):
        world.client.put_object(Bucket=world.bucket_name, Key=f"parsed/{name}", Body=body)
    return f"parsed/{name}"


def versions_naming(world: RemovalWorld, digest: str) -> list[str]:
    """Every version of every object under `parsed/` whose key names `digest`."""
    listed = world.client.list_object_versions(Bucket=world.bucket_name, Prefix="parsed/")
    return [str(one.get("Key")) for one in listed.get("Versions", []) if digest in str(one.get("Key"))]


def names_no_one(report: CaselistStatusReport) -> None:
    said = json.dumps([[one.caselist, one.sha256, one.request_id] for one in report.held_parsed_objects])
    assert not [word for word in (*NAMES, REVISED_PATH, ".zip", ".docx") if word in said], said


async def test_status_names_an_earlier_builds_parsed_file_of_a_held_upload(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """By caselist, digest and request, and outside the verdict: the comparison still agrees."""
    await remove_the_named_file(world)
    await an_older_build_imports_next_week(world, tmp_path)
    an_earlier_builds_parse_publishes(world, UPLOADED_AFTER)

    report = await status_service(world).status(CASELIST)

    assert report.held_parsed_objects == (
        HeldParsedObject(caselist=CASELIST, sha256=UPLOADED_AFTER, request_id=REQUEST),
    )
    assert report.held_parsed_objects_of(CASELIST) == report.held_parsed_objects
    assert REQUEST in report.removals_owed
    assert report.in_sync, report.drifted
    names_no_one(report)


async def test_status_does_not_name_a_parsed_file_of_bytes_another_live_path_discloses(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """`2026-10-10`: the same bytes at the held path and at the other team's, which nothing holds."""
    await remove_the_named_file(world)
    await import_weekly(world, tmp_path, CASELIST, TWO_PATHS_WEEK, importer=an_older_builds_importer(world))
    an_earlier_builds_parse_publishes(world, UPLOADED_AFTER_AT_TWO_PATHS)

    report = await status_service(world).status(CASELIST)

    assert report.held_parsed_objects == ()


async def test_running_the_removal_again_takes_the_held_uploads_parsed_file_with_every_version(
    world: RemovalWorld, tmp_path: Path
) -> None:
    await remove_the_named_file(world)
    await an_older_build_imports_next_week(world, tmp_path)
    an_earlier_builds_parse_publishes(world, UPLOADED_AFTER)
    assert len(versions_naming(world, UPLOADED_AFTER)) == 2, "the precondition: two versions"

    await remove_the_named_file(world)

    assert versions_naming(world, UPLOADED_AFTER) == []
    assert not list((world.data_dir / "parsed").rglob(f"{UPLOADED_AFTER}*"))
    report = await status_service(world).status(CASELIST)
    assert (report.held_parsed_objects, report.removals_owed) == ((), ())
