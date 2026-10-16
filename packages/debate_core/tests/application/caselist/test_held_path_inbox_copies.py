"""The inbox copy of an archive the pull imported when a hold refused an upload in it (`v1-e30-t21`).

`v1-e30-t13`'s importer refuses an upload at a held path and stores nothing of it, but the archive
that carried it stayed in the download inbox until retention or the same removal run again took it
out. Retention waits for the snapshot's publish to be confirmed, because the rest of an archive is
other teams' disclosures, which a failed publish may need to import again. An archive whose every
member was removed or held needs nothing: its import stored nothing. So the pull now takes it out as
soon as the import that met the hold has finished, whether or not the bucket answers. An archive
holding anything else stays for retention, as every imported archive does (the forbidden list:
never remove an inbox file that holds anything not removed or held), and `caselist status` reports
its held upload meanwhile.

The world is the three synthetic weeks, imported and published (`conftest.removal_world`), and the
pull is the retention tests' (`test_inbox_retention.Installation`). The removal is `caselist remove
--source` of the Bayview semifinal negative, new in `2026-09-15`, which holds its path for snapshots
after that date. Week four, `2026-09-22`, is built here; what its import must count is worked out by
hand in each test's docstring.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import date
from pathlib import Path
from typing import Final

import pytest
from tests.fixtures.caselist.build_synthetic_archives import (
    DOCUMENT_BODIES,
    _docx,  # pyright: ignore[reportPrivateUsage]
)

from debate_core.application.caselist.inbox_purge import CaselistInbox
from debate_core.application.caselist.removal_plan import SourceSelector
from debate_core.application.caselist.status_service import CaselistStatusService
from debate_core.application.caselist_sync import RunSummary, StageOutcome, SyncStage
from debate_core.application.ports.suppression import ReasonCode
from debate_core.integrations.local import FsEvidenceObjectStore
from debate_core.integrations.local.archive_reader import ZipArchiveRewriter

from .conftest import REQUEST, RemovalWorld
from .test_inbox_retention import (
    CASELIST,
    LIMITS,
    ExpiredBucket,
    FakeSource,
    Installation,
    kept,
    label,
    outcome,
    removed,
    stage_reason,
    weekly_name,
)

pytestmark = pytest.mark.anyio

WEEK_4: Final = date(2026, 9, 22)
BAYVIEW_PATH: Final = "Maple Grove/QX/Maple Grove-QX-Neg-Bayview Open [2]-Semis.docx"
"""The removed file's path, as the reader gives it with the archive's own directory taken off."""
BAYVIEW: Final = hashlib.sha256(DOCUMENT_BODIES["bayview-semis-neg"]).hexdigest()
REUPLOADED: Final = _docx(("Bayview Open, semifinal, negative.", "Uploaded again after the removal."))
REUPLOADED_SHA256: Final = hashlib.sha256(REUPLOADED).hexdigest()
ANOTHER_TEAMS: Final = _docx(("Harbor Classic, round four, affirmative.", "Another team's file that week."))
APPLE_DOUBLE: Final = "__MACOSX/Maple Grove/QX/._Maple Grove-QX-Neg-Bayview Open [2]-Semis.docx"

TAKEN_OUT: Final = (
    "1 archive(s) taken out of the inbox, which held only files removed or held at a removed path"
)


def week_four(destination: Path, *, another_teams_file: bool) -> Path:
    """`testcl26-weekly-2026-09-22.zip`: the re-upload at the removed path, macOS's metadata file
    beside it, and, when asked, another team's new file."""
    members: list[tuple[str, bytes]] = [
        (BAYVIEW_PATH, REUPLOADED),
        (APPLE_DOUBLE, b"\x00\x05\x16\x07 invented AppleDouble metadata"),
    ]
    if another_teams_file:
        members.append(("Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-Aff-Harbor Classic-Round 4.docx", ANOTHER_TEAMS))
    path = destination / weekly_name(WEEK_4)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body in sorted(members):
            info = zipfile.ZipInfo(f"testcl26-0922/{name}", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, body)
    return path


async def remove_bayview(world: RemovalWorld) -> None:
    """`caselist remove --source <bayview> --execute`: the path is held after 2026-09-15."""
    service = world.service()
    plan = await service.plan(
        SourceSelector(BAYVIEW), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM
    )
    assert [hold.after_snapshot for hold in plan.path_holds] == [date(2026, 9, 15)]
    assert (await service.execute(plan)).completed


def installation_of(world: RemovalWorld, archive: Path) -> Installation:
    return Installation(
        data_dir=world.data_dir,
        bucket=world.bucket,
        archives={WEEK_4: archive},
        suppression=world.suppression(),
    )


def week_four_counts(world: RemovalWorld) -> dict[str, int]:
    """The classification counts week four's manifest records."""
    path = FsEvidenceObjectStore(world.data_dir).path_for(f"manifests/{CASELIST}/{WEEK_4.isoformat()}.jsonl")
    (summary,) = [
        row
        for row in map(json.loads, path.read_text(encoding="utf-8").splitlines())
        if row["kind"] == "summary"
    ]
    return summary["classifications"]


async def held_in_inbox_now(world: RemovalWorld) -> list[tuple[str, str, str, str]]:
    """What `caselist status` says is held in the inbox: `(caselist, snapshot, sha256, request id)`."""
    inbox = CaselistInbox(
        directory=world.data_dir / "inbox", state_dir=world.data_dir, archives=ZipArchiveRewriter(**LIMITS)
    )
    service = CaselistStatusService(
        local=world.local, remote=world.bucket, suppression=world.suppression(), inbox=inbox
    )
    held = (await service.status(CASELIST, held_in_inbox=True)).held_in_inbox
    return [(one.caselist, one.snapshot, one.sha256, one.request_id) for one in held]


def import_reason(summary: RunSummary) -> str:
    return stage_reason(summary, SyncStage.IMPORT)


# ------------------------------------------------------------------------------------------------
# An archive holding only the held upload and its junk leaves when its import finishes
# ------------------------------------------------------------------------------------------------


async def test_an_archive_holding_only_the_held_upload_leaves_the_inbox_when_its_import_finishes(
    removal_world: RemovalWorld, tmp_path: Path
) -> None:
    """Week four holds the re-upload at the held path and the AppleDouble file that names it.

    Its import, against `2026-09-15`: the re-upload `SUPPRESSED` (held), the AppleDouble skipped and
    withheld with it, and every file of 09-15 `REMOVED` from the window, so it stores nothing. The
    bucket's session has expired, so nothing is published or confirmed, and retention could not take
    it out; the import stage does, and says so.
    """
    await remove_bayview(removal_world)
    archive = week_four(tmp_path / "published", another_teams_file=False)
    installation = installation_of(removal_world, archive)

    summary = await installation.sync(
        FakeSource(installation.archives, weeks=[WEEK_4]),
        publish_to=ExpiredBucket(),
        compare_with=ExpiredBucket(),
    ).run([CASELIST])

    assert outcome(summary, SyncStage.IMPORT) is StageOutcome.COMPLETED, summary.stages
    assert week_four_counts(removal_world).get("SUPPRESSED") == 1
    assert not set(week_four_counts(removal_world)) & {"NEW", "CHANGED", "UNCHANGED", "DUPLICATE"}
    assert installation.inbox_names() == set(), "the archive stayed in the inbox"
    assert TAKEN_OUT in import_reason(summary)
    assert outcome(summary, SyncStage.PUBLISH) is StageOutcome.PENDING
    assert stage_reason(summary, SyncStage.RETENTION) == "the inbox holds nothing", "retention saw it"
    assert REUPLOADED_SHA256[:12] not in import_reason(summary) and BAYVIEW_PATH not in import_reason(summary)


async def test_the_next_pull_does_not_fetch_it_again(removal_world: RemovalWorld, tmp_path: Path) -> None:
    """An imported week is `already_imported` whether or not its zip is in the inbox (`v1-e30-t09`)."""
    await remove_bayview(removal_world)
    archive = week_four(tmp_path / "published", another_teams_file=False)
    installation = installation_of(removal_world, archive)
    source = FakeSource(installation.archives, weeks=[WEEK_4])
    await installation.sync(source).run([CASELIST])

    again = await installation.sync(source).run([CASELIST])

    assert source.archive_fetches == [weekly_name(WEEK_4)]
    assert {one.name: str(one.decision) for one in again.archives} == {
        weekly_name(WEEK_4): "already_imported"
    }


async def test_a_copy_that_changed_after_its_import_is_left_for_retention(
    removal_world: RemovalWorld, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the bytes imported are taken out. Here the inbox copy is replaced as the import ends."""
    await remove_bayview(removal_world)
    archive = week_four(tmp_path / "published", another_teams_file=False)
    installation = installation_of(removal_world, archive)
    sync = installation.sync(FakeSource(installation.archives, weeks=[WEEK_4]), bucket=False)
    real = sync._later_manifests.after_weekly_import  # pyright: ignore[reportPrivateUsage]

    async def then_the_copy_changes(report: object) -> object:
        done = await real(report)  # type: ignore[arg-type]
        (installation.inbox / weekly_name(WEEK_4)).write_bytes(b"other bytes under the same name")
        return done

    monkeypatch.setattr(sync._later_manifests, "after_weekly_import", then_the_copy_changes)  # pyright: ignore[reportPrivateUsage]

    summary = await sync.run([CASELIST])

    assert installation.inbox_names() == {weekly_name(WEEK_4)}
    assert TAKEN_OUT not in import_reason(summary)


async def test_an_archive_holding_only_the_removed_file_itself_is_left_for_retention(
    removal_world: RemovalWorld, tmp_path: Path
) -> None:
    """The Bayview file's own bytes at its own path, the week after: the list stops it, the hold
    refuses nothing (`SUPPRESSED` 1, none held), so the import met no hold and leaves the archive to
    retention, which removes it once the publish is confirmed, as it always has."""
    await remove_bayview(removal_world)
    path = tmp_path / "published" / weekly_name(WEEK_4)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"testcl26-0922/{BAYVIEW_PATH}", DOCUMENT_BODIES["bayview-semis-neg"])
    installation = installation_of(removal_world, path)

    summary = await installation.sync(
        FakeSource(installation.archives, weeks=[WEEK_4]),
        publish_to=ExpiredBucket(),
        compare_with=ExpiredBucket(),
    ).run([CASELIST])

    assert week_four_counts(removal_world).get("SUPPRESSED") == 1
    assert installation.inbox_names() == {weekly_name(WEEK_4)}
    assert "taken out of the inbox" not in import_reason(summary)
    assert kept(summary) == {label(WEEK_4): "not_confirmed"}


# ------------------------------------------------------------------------------------------------
# An archive that also holds another team's file stays for retention, and status reports it
# ------------------------------------------------------------------------------------------------


async def test_an_archive_that_also_holds_another_teams_file_stays_until_its_publish_is_confirmed(
    removal_world: RemovalWorld, tmp_path: Path
) -> None:
    """The same week with another team's new file: `SUPPRESSED` 1 and `NEW` 1. The other file is
    someone's disclosure, so the archive is not removed, and with the bucket's session expired its
    publish is not confirmed and retention keeps it. `caselist status` names the held upload in it
    by digest and request. Logged in, the next pull confirms the publish and retention removes it."""
    await remove_bayview(removal_world)
    archive = week_four(tmp_path / "published", another_teams_file=True)
    installation = installation_of(removal_world, archive)
    source = FakeSource(installation.archives, weeks=[WEEK_4])

    expired = await installation.sync(source, publish_to=ExpiredBucket(), compare_with=ExpiredBucket()).run(
        [CASELIST]
    )

    assert week_four_counts(removal_world).get("SUPPRESSED") == 1
    assert week_four_counts(removal_world).get("NEW") == 1
    assert installation.inbox_names() == {weekly_name(WEEK_4)}
    assert "taken out of the inbox" not in import_reason(expired)
    assert kept(expired) == {label(WEEK_4): "not_confirmed"}
    assert await held_in_inbox_now(removal_world) == [
        (CASELIST, WEEK_4.isoformat(), REUPLOADED_SHA256, REQUEST)
    ]

    logged_in = await installation.sync(source).run([CASELIST])

    assert removed(logged_in) == [label(WEEK_4)]
    assert installation.inbox_names() == set()
    assert await held_in_inbox_now(removal_world) == []
