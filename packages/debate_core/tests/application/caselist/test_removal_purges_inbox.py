"""A completed removal leaves no removed bytes in the sync's inbox (`v1-e30-t09`).

`caselist pull` downloads into an inbox (`caselist.inbox_dir`, or `<data_dir>/inbox`) and never
clears it, so after the three synthetic weeks and the OpenEv release have been pulled, the inbox
holds each weekly archive and the camp release as downloaded. A removal that cleans the store and
the bucket but not the inbox leaves the removed bytes on this machine.

The inbox is scanned here by :func:`removed_bytes_in_inbox`, which shares no code with the removal:
it opens every file with `zipfile` directly, reads every entry — junk and zip-slip names included —
and hashes it. What it is looking for is the removal's own record of what it removed, the log
entry's `removed_sha256`.

Every expectation is worked out by hand from the fixture tables (`tests/fixtures/caselist/` and
`tests/fixtures/openev/`), which hold no real caselist or camp content.
"""

from __future__ import annotations

import hashlib
import shutil
import zipfile
from pathlib import Path

import pytest
from tests.fixtures.caselist.build_synthetic_archives import (
    DOCUMENT_BODIES,
    SNAPSHOTS,
    SYNTHETIC_CASELIST,
    build_snapshot_zips,
)
from tests.fixtures.openev.build_synthetic_openev import DOWNLOADS as OPENEV_DOWNLOADS
from tests.fixtures.openev.build_synthetic_openev import build_download_zips

from debate_core.application.caselist.removal_plan import parse_team_selector
from debate_core.application.caselist.removal_service import RemovalReport
from debate_core.application.ports.suppression import ReasonCode

from .conftest import REQUEST, TEAM, RemovalWorld

pytestmark = pytest.mark.anyio


def digest(body: str) -> str:
    return hashlib.sha256(DOCUMENT_BODIES[body]).hexdigest()


#: The team's Round 1 affirmative: in all three weekly archives, and in the camp release as
#: `Tamarack/TSF-Borrowed Grove Aff.docx`.
GROVE_ROUND_1 = digest("grove-round-1-aff")

#: The OpenEv id the sync gave the camp release it downloaded, and so the name it sits under.
CAMP_RELEASE_ID = 701


def weekly_inbox_name(snapshot: object) -> str:
    """The name `caselist pull` gives a weekly archive: `<slug>-weekly-<date>.zip`."""
    return f"{SYNTHETIC_CASELIST}-weekly-{snapshot}.zip"


def camp_release_inbox_name() -> str:
    """`openev-<id>-<file name>`, as `openev_inbox_name` names a camp release the sync fetched."""
    return f"openev-{CAMP_RELEASE_ID}-{OPENEV_DOWNLOADS[0].name}.zip"


def stock_inbox(world: RemovalWorld, scratch: Path) -> Path:
    """The inbox of a machine that pulled the three weeks and the camp release the world imported.

    The very bytes the world imported, under the names the sync gives them.
    """
    inbox = world.data_dir / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    for week in SNAPSHOTS:
        archive = build_snapshot_zips(scratch / "weeks")[week.snapshot]
        shutil.copyfile(archive, inbox / weekly_inbox_name(week.snapshot))
    release = build_download_zips(scratch / "openev")[OPENEV_DOWNLOADS[0].name]
    shutil.copyfile(release, inbox / camp_release_inbox_name())
    return inbox


def removed_bytes_in_inbox(inbox: Path, removed: set[str]) -> list[str]:
    """Every file in the inbox that holds a removed sha256, as itself or as any entry of a zip.

    Independent of the code under test: every regular file under the inbox, dot files and
    `.partial/` included, hashed whole; every zip opened with `zipfile` and every entry hashed,
    whatever its name.
    """
    found: list[str] = []
    for path in sorted(inbox.rglob("*")):
        if not path.is_file():
            continue
        name = path.relative_to(inbox).as_posix()
        if hashlib.sha256(path.read_bytes()).hexdigest() in removed:
            found.append(name)
        if zipfile.is_zipfile(path) and path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as archive:
                for info in archive.infolist():
                    if not info.is_dir() and hashlib.sha256(archive.read(info)).hexdigest() in removed:
                        found.append(f"{name} :: {info.filename}")
    return found


async def remove_team_everywhere(world: RemovalWorld) -> RemovalReport:
    """`caselist remove --team 'testcl26/Maple Grove/QX' --include-shared --execute`.

    With `--include-shared` the Round 1 affirmative, which another team and a camp file also hold,
    goes for everyone: the file that is in one camp download and three weekly archives.
    """
    service = world.service()
    plan = await service.plan(
        parse_team_selector(TEAM),
        request_id=REQUEST,
        reason=ReasonCode.REQUESTED_BY_TEAM,
        include_shared=True,
    )
    report = await service.execute(plan)
    assert report.completed
    return report


class TestNoRemovedBytesAreLeftInTheInbox:
    async def test_after_a_completed_removal_no_inbox_file_holds_a_removed_sha256(
        self, removal_world: RemovalWorld, tmp_path: Path
    ) -> None:
        inbox = stock_inbox(removal_world, tmp_path / "pulled")
        assert GROVE_ROUND_1 in {
            hashlib.sha256(zipfile.ZipFile(path).read(info)).hexdigest()
            for path in inbox.iterdir()
            for info in zipfile.ZipFile(path).infolist()
        }, "the fixture: the removed file is in the inbox before the removal"

        report = await remove_team_everywhere(removal_world)

        removed = set(report.log_entry.removed_sha256)
        assert GROVE_ROUND_1 in removed
        assert removed_bytes_in_inbox(inbox, removed) == []
