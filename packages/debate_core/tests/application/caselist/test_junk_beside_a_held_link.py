"""Junk that shadows a link at a held path is held with the link (`v1-e30-t25`, item 2).

`v1-e30-t22` gave a skipped member at a path a removal holds no manifest row
(:func:`~debate_core.application.caselist.pipeline.hold_on_skipped_member`): a symbolic link named as
the removed file. macOS puts an AppleDouble file beside it when it zips the folder,
`__MACOSX/<dir>/._<name>`, which names the same file, and until this task that member kept its row,
because neither held-path rule read it as the link (`v1-e30-t22`'s Decision 4). The one shared rule
now asks the hold of the file such junk shadows as well as of its own path, so the importer, the
removal's manifest rewrite, its inbox rewrite (`v1-e30-t21`) and `caselist status` agree with no
change of their own.

Junk shadows the file its name gives whether or not the archive holds that file, so junk alone at a
held path is held too (the report's Decision on junk without the link).

The store and the removal are `v1-e30-t21`'s and `v1-e30-t22`'s: `caselist remove --source
<named-version>` holds `(testcl26, REVISED_PATH)` for snapshots dated after `2026-09-08`. Every test
runs offline: moto for the bucket, a temporary data directory, and a temporary `HOME`.
"""

from __future__ import annotations

import stat
import zipfile
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_revised_path_archives import (
    BODIES,
    CASELIST,
    KEPT_PATH,
    ONE_WEEK_PATH,
    REVISED_PATH,
)

from debate_core.application.caselist.import_service import ImportReport
from debate_core.application.caselist.inbox_purge import InboxAction
from debate_core.application.caselist.publish_service import ManifestOutcome
from debate_core.application.caselist.removal_plan import SourceSelector
from debate_core.application.ports.suppression import ReasonCode
from debate_core.integrations.local import FsEvidenceObjectStore

from .conftest import REQUEST, RemovalWorld
from .test_held_path_loose_ends import LINK_BODY, members_of, status_service
from .test_held_rows_publish_nothing import (
    HOLD_DATE,
    LINK_WEEK_MANIFEST,
    WEEK_OF_THE_LINK,
    an_older_builds_importer,
    an_older_builds_publisher,
    import_archive,
    of_snapshot,
    rows_at,
    this_builds_publisher,
)
from .test_removal_covers_later_uploads import NAMED, NAMES, remove_the_named_file, revised_path_world

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

#: What macOS's resource-fork sidecar begins with; the rest of its body does not matter here.
APPLE_DOUBLE_BODY = b"\x00\x05\x16\x07\x00\x02\x00\x00Mac OS X        "


def apple_double_of(path: str) -> str:
    """`__MACOSX/<dir>/._<name>`: the AppleDouble member macOS writes beside `<dir>/<name>`."""
    directory, name = path.rsplit("/", 1)
    return f"__MACOSX/{directory}/._{name}"


JUNK_OF_THE_HELD_PATH = apple_double_of(REVISED_PATH)
JUNK_OF_A_PATH_NOTHING_HOLDS = apple_double_of(ONE_WEEK_PATH)


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


def write_archive(path: Path, *, links: tuple[str, ...] = (), junk: tuple[str, ...] = ()) -> Path:
    """`KEPT_PATH`'s file, a symbolic link at each of `links` whose body is the removed file's name,
    and an AppleDouble member at each of `junk`, as the Finder's Compress writes them."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(zipfile.ZipInfo(KEPT_PATH, date_time=(1980, 1, 1, 0, 0, 0)), BODIES["kept"])
        for name in links:
            link = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(link, LINK_BODY)
        for name in junk:
            archive.writestr(zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)), APPLE_DOUBLE_BODY)
    return path


def arriving(tmp_path: Path, week: date = WEEK_OF_THE_LINK) -> Path:
    return tmp_path / "arriving" / f"{CASELIST}-weekly-{week.isoformat()}.zip"


def a_link_and_its_junk(tmp_path: Path, *, at: str = REVISED_PATH, week: date = WEEK_OF_THE_LINK) -> Path:
    return write_archive(arriving(tmp_path, week), links=(at,), junk=(apple_double_of(at),))


def skipped_of(report: ImportReport) -> dict[str, int]:
    return {str(reason): count for reason, count in report.skipped.items()}


def withheld_of(report: ImportReport, path: str) -> list[bool]:
    return [entry.withheld for entry in report.entries if entry.is_skipped and entry.path == path]


# ------------------------------------------------------------------------------------------------
# The importer
# ------------------------------------------------------------------------------------------------


async def test_junk_beside_a_link_at_the_held_path_imports_with_no_row_at_either_path(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """Dated after the hold. Both are still counted as skipped, as junk beside a suppressed file is;
    only their rows, which name the held path, are left out."""
    await remove_the_named_file(world)

    report = await import_archive(world, a_link_and_its_junk(tmp_path), WEEK_OF_THE_LINK)

    assert rows_at(world, LINK_WEEK_MANIFEST, JUNK_OF_THE_HELD_PATH) == [], (
        "the junk's row names the held path"
    )
    assert rows_at(world, LINK_WEEK_MANIFEST, REVISED_PATH) == []
    assert rows_at(world, LINK_WEEK_MANIFEST, KEPT_PATH), "the rest of the archive keeps its rows"
    assert skipped_of(report) == {"SYMLINK": 1, "MACOS_METADATA": 1}
    assert withheld_of(report, JUNK_OF_THE_HELD_PATH) == [True]


async def test_junk_beside_a_link_at_a_path_nothing_holds_keeps_its_row(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """In the other team's directory: neither row names anything removed."""
    await remove_the_named_file(world)

    await import_archive(world, a_link_and_its_junk(tmp_path, at=ONE_WEEK_PATH), WEEK_OF_THE_LINK)

    assert [
        row["skip_reason"] for row in rows_at(world, LINK_WEEK_MANIFEST, JUNK_OF_A_PATH_NOTHING_HOLDS)
    ] == ["MACOS_METADATA"]
    assert [row["skip_reason"] for row in rows_at(world, LINK_WEEK_MANIFEST, ONE_WEEK_PATH)] == ["SYMLINK"]


async def test_junk_beside_a_link_at_the_held_path_in_the_week_the_hold_dates_from_keeps_its_row(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """The hold covers snapshots dated after `2026-09-08`, so the junk is asked with the snapshot's
    date, as the link is. A dry run, which writes nothing, shows it."""
    await remove_the_named_file(world)

    report = await import_archive(
        world,
        a_link_and_its_junk(tmp_path, week=HOLD_DATE),
        HOLD_DATE,
        dry_run=True,
        allow_out_of_order=True,
    )

    assert withheld_of(report, JUNK_OF_THE_HELD_PATH) == [False]


async def test_junk_alone_at_the_held_path_imports_with_no_row(world: RemovalWorld, tmp_path: Path) -> None:
    """With no link and no file beside it: its name still gives the held path, so it is held."""
    await remove_the_named_file(world)

    report = await import_archive(
        world, write_archive(arriving(tmp_path), junk=(JUNK_OF_THE_HELD_PATH,)), WEEK_OF_THE_LINK
    )

    assert rows_at(world, LINK_WEEK_MANIFEST, JUNK_OF_THE_HELD_PATH) == []
    assert skipped_of(report) == {"MACOS_METADATA": 1}


# ------------------------------------------------------------------------------------------------
# The removal's inbox rewrite (`v1-e30-t21`)
# ------------------------------------------------------------------------------------------------


async def test_the_removal_rewrites_a_waiting_archive_without_the_junk_beside_a_link_at_the_held_path(
    world: RemovalWorld,
) -> None:
    """Downloaded and not imported, dated after the hold's date: both go, and the file beside them
    stays."""
    waiting = write_archive(
        world.data_dir / "inbox" / f"{CASELIST}-weekly-2026-10-11.zip",
        links=(REVISED_PATH,),
        junk=(JUNK_OF_THE_HELD_PATH,),
    )

    service = world.service()
    plan = await service.plan(SourceSelector(NAMED), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM)

    planned = [one for one in plan.inbox if one.name == waiting.name]
    assert [(one.action, sorted(one.dropped), one.entries_kept) for one in planned] == [
        (InboxAction.REWRITE, sorted((REVISED_PATH, JUNK_OF_THE_HELD_PATH)), 1)
    ]
    assert (await service.execute(plan)).completed
    assert members_of(waiting) == [KEPT_PATH]


async def test_the_removal_leaves_a_waiting_archive_with_junk_beside_a_link_at_a_path_nothing_holds(
    world: RemovalWorld,
) -> None:
    waiting = write_archive(
        world.data_dir / "inbox" / f"{CASELIST}-weekly-2026-10-11.zip",
        links=(ONE_WEEK_PATH,),
        junk=(JUNK_OF_A_PATH_NOTHING_HOLDS,),
    )
    before = waiting.read_bytes()

    await remove_the_named_file(world)

    assert waiting.read_bytes() == before


# ------------------------------------------------------------------------------------------------
# An earlier build's junk row: status, the publisher and the manifest rewrite agree with the importer
# ------------------------------------------------------------------------------------------------


async def an_earlier_build_imports_the_link_and_its_junk(world: RemovalWorld, tmp_path: Path) -> Path:
    """After the removal, a build from before this task imports the week with both, unpublished."""
    archive = a_link_and_its_junk(tmp_path)
    await import_archive(world, archive, WEEK_OF_THE_LINK, importer=an_older_builds_importer(world))
    assert [row["skip_reason"] for row in rows_at(world, LINK_WEEK_MANIFEST, JUNK_OF_THE_HELD_PATH)] == [
        "MACOS_METADATA"
    ], "the precondition: the earlier build wrote the junk's row"
    return archive


async def test_status_and_the_publisher_count_an_earlier_builds_junk_row_as_a_held_skipped_row(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """One held skipped row each for the link and its junk, by the request holding the path; the
    publisher withholds the manifest for both, and its message names neither path."""
    await remove_the_named_file(world)
    await an_earlier_build_imports_the_link_and_its_junk(world, tmp_path)

    report = await status_service(world).status(CASELIST, "2026-10-11")
    publish = await this_builds_publisher(world).execute(
        await this_builds_publisher(world).plan(CASELIST, "2026-10-11")
    )

    assert of_snapshot(report, "2026-10-11").held_skipped_rows == (REQUEST, REQUEST)
    (outcome,) = publish.snapshots
    assert outcome.manifest is ManifestOutcome.WITHHELD
    assert outcome.manifest_error is not None
    assert f"2 skipped member row(s) at a path a removal holds ({REQUEST})" in outcome.manifest_error
    assert not [word for word in (*NAMES, REVISED_PATH, "__MACOSX") if word in outcome.manifest_error]


async def test_running_the_removal_again_takes_the_junk_row_out_and_agrees_with_this_builds_import(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """The week the removal rewrote, and the same archive imported again by this build afterwards,
    are the same file byte for byte; and the publisher then publishes the week."""
    await remove_the_named_file(world)
    archive = await an_earlier_build_imports_the_link_and_its_junk(world, tmp_path)

    await remove_the_named_file(world)

    assert rows_at(world, LINK_WEEK_MANIFEST, JUNK_OF_THE_HELD_PATH) == []
    local = FsEvidenceObjectStore(world.data_dir).path_for(LINK_WEEK_MANIFEST)
    rewritten = local.read_bytes()
    await import_archive(world, archive, WEEK_OF_THE_LINK)
    assert local.read_bytes() == rewritten
    report = await this_builds_publisher(world).execute(
        await this_builds_publisher(world).plan(CASELIST, "2026-10-11")
    )
    assert report.succeeded


async def test_an_earlier_builds_junk_row_beside_a_link_at_a_path_nothing_holds_publishes(
    world: RemovalWorld, tmp_path: Path
) -> None:
    await remove_the_named_file(world)
    await import_archive(
        world,
        a_link_and_its_junk(tmp_path, at=ONE_WEEK_PATH),
        WEEK_OF_THE_LINK,
        importer=an_older_builds_importer(world),
    )

    report = await status_service(world).status(CASELIST, "2026-10-11")

    assert of_snapshot(report, "2026-10-11").held_skipped_rows == ()
    publisher = an_older_builds_publisher(world)
    assert (await publisher.execute(await publisher.plan(CASELIST, "2026-10-11"))).succeeded
    assert (
        await this_builds_publisher(world).execute(
            await this_builds_publisher(world).plan(CASELIST, "2026-10-11")
        )
    ).succeeded
