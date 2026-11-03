"""A manifest with a skipped member's row at a held path is withheld (`v1-e30-t23`, PM amendment 2026-10-18).

`v1-e30-t22` stopped this build's importer writing a row for a skipped member, a symbolic link, at a
path a removal holds. A build from before it writes one, and its publisher publishes it: the row's
path names the school and the team, and the link's body is often the removed file's name. `t22`'s
publisher published it too (its Decision 5). The PM's ruling on `t22`'s question 1 (b): the publisher
withholds such a manifest exactly as it withholds one with a held stored row, with the same outcome
and the same code, `MANIFEST_NAMES_SUPPRESSED_SOURCE`. A publish that succeeded over it now fails,
which is intended, and its message names the fix, the removal run again.

`caselist status` asks the publisher's own rule for the hint it gives a manifest the publisher
withholds (`v1-e30-t19`), so the same change moves the hint: see
`packages/debate_cli/tests/test_caselist_publish.py`, whose `BESIDE_THE_REWRITE["a held skipped
row"]` is now `True`, and :func:`test_status_says_the_publisher_withholds_it` here.

The store, the removal and the link are `t22`'s (`test_held_rows_publish_nothing.py`). No test
imports a name this task adds, so each runs against the start commit's source too.

Every test runs offline: moto for the bucket, a temporary data directory, and a temporary `HOME`.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_revised_path_archives import CASELIST, ONE_WEEK_PATH, REVISED_PATH

from debate_core.application.caselist.publish_service import (
    MANIFEST_NAMES_SUPPRESSED_SOURCE,
    ManifestOutcome,
    PublishReport,
)

from .conftest import REQUEST, RemovalWorld
from .test_held_path_loose_ends import status_service
from .test_held_rows_publish_nothing import (
    LINK_WEEK_MANIFEST,
    WEEK_OF_THE_LINK,
    a_week_with_a_link,
    an_older_builds_importer,
    bucket_manifest,
    import_archive,
    rows_at,
    this_builds_publisher,
)
from .test_removal_covers_later_uploads import NAMES, remove_the_named_file, revised_path_world

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

LINK_WEEK = WEEK_OF_THE_LINK.isoformat()


@pytest.fixture(autouse=True)
def temporary_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A `HOME` of this test's own, so nothing here can read or write the operator's."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


@pytest.fixture
async def world(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> RemovalWorld:
    built = await revised_path_world(tmp_path, s3_client, evidence_bucket)
    await remove_the_named_file(built)
    return built


async def an_earlier_build_imports_the_link_and_does_not_publish(world: RemovalWorld, tmp_path: Path) -> None:
    """After the removal, a build from before `v1-e30-t22` imports the week with the link."""
    await import_archive(
        world, a_week_with_a_link(tmp_path), WEEK_OF_THE_LINK, importer=an_older_builds_importer(world)
    )
    assert [row["skip_reason"] for row in rows_at(world, LINK_WEEK_MANIFEST, REVISED_PATH)] == ["SYMLINK"], (
        "the precondition: the earlier build wrote the link's row"
    )


async def test_the_publisher_withholds_a_manifest_with_a_links_row_at_the_held_path(
    world: RemovalWorld, tmp_path: Path
) -> None:
    await an_earlier_build_imports_the_link_and_does_not_publish(world, tmp_path)
    before = world.versions()

    publisher = this_builds_publisher(world)
    report = await publisher.execute(await publisher.plan(CASELIST, LINK_WEEK))

    (snapshot,) = report.snapshots
    assert snapshot.manifest is ManifestOutcome.WITHHELD
    assert snapshot.manifest_error_code == MANIFEST_NAMES_SUPPRESSED_SOURCE
    assert report.failure_codes == (MANIFEST_NAMES_SUPPRESSED_SOURCE,)
    assert report.succeeded is False
    assert bucket_manifest(world, LINK_WEEK_MANIFEST) is None
    assert world.versions() == before, "nothing of the manifest's week reached the bucket"


async def test_its_message_names_the_request_and_the_fix_and_no_one(
    world: RemovalWorld, tmp_path: Path
) -> None:
    await an_earlier_build_imports_the_link_and_does_not_publish(world, tmp_path)

    publisher = this_builds_publisher(world)
    report = await publisher.execute(await publisher.plan(CASELIST, LINK_WEEK))

    message = report.snapshots[0].manifest_error or ""
    assert f"1 skipped member row(s) at a path a removal holds ({REQUEST})" in message
    assert "re-run `caselist remove`" in message
    for name in (*NAMES, *REVISED_PATH.split("/"), ".docx"):
        assert name not in message


async def test_a_dry_run_says_the_manifest_would_be_withheld(world: RemovalWorld, tmp_path: Path) -> None:
    await an_earlier_build_imports_the_link_and_does_not_publish(world, tmp_path)

    plan = await this_builds_publisher(world).plan(CASELIST, LINK_WEEK)

    assert PublishReport(plan=plan, applied=False).succeeded is False


async def test_a_manifest_with_a_links_row_at_a_path_no_removal_holds_is_published(
    world: RemovalWorld, tmp_path: Path
) -> None:
    archive = a_week_with_a_link(tmp_path, at=ONE_WEEK_PATH)
    await import_archive(world, archive, WEEK_OF_THE_LINK, importer=an_older_builds_importer(world))

    publisher = this_builds_publisher(world)
    report = await publisher.execute(await publisher.plan(CASELIST, LINK_WEEK))

    assert report.succeeded
    assert bucket_manifest(world, LINK_WEEK_MANIFEST) is not None


async def test_running_the_removal_again_lets_the_week_publish(world: RemovalWorld, tmp_path: Path) -> None:
    """The fix the message names: the re-run drops the row (`v1-e30-t22`), and the publish succeeds."""
    await an_earlier_build_imports_the_link_and_does_not_publish(world, tmp_path)
    await remove_the_named_file(world)

    publisher = this_builds_publisher(world)
    report = await publisher.execute(await publisher.plan(CASELIST, LINK_WEEK))

    assert report.succeeded
    published = bucket_manifest(world, LINK_WEEK_MANIFEST)
    assert published is not None and REVISED_PATH.encode() not in published


async def test_status_says_the_publisher_withholds_it(world: RemovalWorld, tmp_path: Path) -> None:
    """The hint follows the publisher's rule: status asks it, and restates nothing (`v1-e30-t19`)."""
    await an_earlier_build_imports_the_link_and_does_not_publish(world, tmp_path)

    report = await status_service(world).status(CASELIST, LINK_WEEK)

    (snapshot,) = report.snapshots
    assert snapshot.held_skipped_rows == (REQUEST,)
    assert snapshot.manifest_withheld is True
