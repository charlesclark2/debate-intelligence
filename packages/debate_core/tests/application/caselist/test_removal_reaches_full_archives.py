"""A removal reaches the complete archive's snapshot too (`v1-e34-t04`), on this machine and in moto.

A complete archive is filed apart from the weekly series — its manifest at
`manifests/testcl26/full/<date>.jsonl` — and a removal that read the weekly series alone would
leave the removed file's row, school and team code in it, locally and in the bucket. That is the
worst failure the complete archive could bring, so this module builds the case a takedown meets:
the three synthetic weeks and the complete archive of 09-15 imported and published, the complete
archive also in the sync's inbox, and a file of the requesting team that **only** the complete
archive holds, as one disclosed before the weekly back-catalogue begins would be.

The complete archive holds every real member of the 09-15 weekly plus two files no weekly has:

| Path | Bytes |
|---|---|
| `QX_SUMMER` (`Maple Grove/QX/…`, the requesting team's) | `maple summer only` |
| `ZALU_SUMMER` (`Cedar Hollow/ZaLu/…`, another team's) | `zalu summer only` |

Nothing here is real caselist content.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from datetime import date
from pathlib import Path

import pytest
from tests.fixtures.caselist.build_synthetic_archives import SNAPSHOTS, SYNTHETIC_CASELIST

from debate_core.application.caselist.evidence_listing import snapshots_before_full_archive
from debate_core.application.caselist.import_service import CaselistImportService
from debate_core.application.caselist.manifest import (
    full_archive_manifest_key,
    read_manifest_lines,
    write_manifest,
)
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.removal_plan import (
    RemovalPlan,
    Side,
    SourceSelector,
    parse_team_selector,
)
from debate_core.application.ports.suppression import ReasonCode
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsEvidenceObjectStore, FsSnapshotStore
from debate_core.integrations.local.archive_reader import ZipArchiveRewriter, archive_digest, read_archive
from debate_core.testing.fakes import empty_suppression_list

from .conftest import REQUEST, TEAM, RemovalWorld

pytestmark = pytest.mark.anyio

LIMITS = {"max_archive_bytes": 64 * 1024 * 1024, "max_unpacked_bytes": 64 * 1024 * 1024}
FULL_DATE = date(2026, 9, 15)
FULL_KEY = full_archive_manifest_key(SYNTHETIC_CASELIST, FULL_DATE)
FULL_INBOX_NAME = f"{SYNTHETIC_CASELIST}-all-{FULL_DATE.isoformat()}.zip"

QX_SUMMER = "Maple Grove/QX/Maple Grove-QX-Aff-Summer Open-Round 1.docx"
QX_SUMMER_BODY = b"maple summer only"
QX_SUMMER_SHA256 = hashlib.sha256(QX_SUMMER_BODY).hexdigest()
ZALU_SUMMER = "Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-Neg-Summer Open-Round 2.docx"
ZALU_SUMMER_BODY = b"zalu summer only"


def write_full_archive(path: Path) -> Path:
    """The 09-15 weekly's real members, plus the two files only the complete archive holds."""
    members = {
        member.path: member.content for member in SNAPSHOTS[-1].members_for(zip_form=True) if not member.junk
    }
    members[QX_SUMMER] = QX_SUMMER_BODY
    members[ZALU_SUMMER] = ZALU_SUMMER_BODY
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            archive.writestr(info, members[name])
    return path


async def add_complete_archive(world: RemovalWorld, scratch: Path, *, imported: bool = True) -> Path:
    """Import, publish and leave in the inbox the complete archive of 09-15, as a pull would have.

    With `imported` false it is only in the inbox, waiting: a pull downloaded it and has not yet
    imported it.
    """
    zipped = write_full_archive(scratch / FULL_INBOX_NAME)
    inbox = world.data_dir / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(zipped, inbox / FULL_INBOX_NAME)
    if not imported:
        return inbox / FULL_INBOX_NAME
    previous, earlier = await snapshots_before_full_archive(world.local, SYNTHETIC_CASELIST, FULL_DATE)
    report = await CaselistImportService(
        caselists=world.repository,
        blobs=FsSnapshotStore(world.data_dir),
        suppression=empty_suppression_list(),
    ).import_full_archive(
        read_archive(zipped, **LIMITS),
        caselist=SYNTHETIC_CASELIST,
        archive_date=FULL_DATE,
        event=Event.LD,
        archive_sha256=archive_digest(zipped),
        previous=previous,
        earlier=earlier,
    )
    write_manifest(report, FsEvidenceObjectStore(world.data_dir).path_for(FULL_KEY))
    publisher = CaselistPublishService(
        local=world.local, remote=world.bucket, suppression=empty_suppression_list()
    )
    published = await publisher.execute(
        await publisher.plan(SYNTHETIC_CASELIST, f"full/{FULL_DATE.isoformat()}")
    )
    assert published.succeeded
    return inbox / FULL_INBOX_NAME


def local_rows(world: RemovalWorld) -> list[dict[str, object]]:
    lines = read_manifest_lines(FsEvidenceObjectStore(world.data_dir).path_for(FULL_KEY))
    return [row for row in map(json.loads, lines) if row["kind"] == "member"]


def bucket_rows(world: RemovalWorld) -> list[dict[str, object]]:
    body = world.client.get_object(Bucket=world.bucket_name, Key=FULL_KEY)["Body"].read().decode("utf-8")
    return [row for row in map(json.loads, body.splitlines()) if row["kind"] == "member"]


def inbox_digests(path: Path) -> set[str]:
    return {
        entry.sha256 for entry in ZipArchiveRewriter(**LIMITS).inventory(path) if entry.sha256 is not None
    }


def raw_key(digest: str) -> str:
    return f"raw/caselist/{SYNTHETIC_CASELIST}/sha256/{digest[:2]}/{digest[2:4]}/{digest}"


def bucket_keys(world: RemovalWorld) -> set[str]:
    listed = world.client.list_objects_v2(Bucket=world.bucket_name)
    return {str(one.get("Key")) for one in listed.get("Contents", [])}


async def remove(world: RemovalWorld, selector: SourceSelector | object) -> RemovalPlan:
    service = world.service()
    plan = await service.plan(selector, request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM)  # type: ignore[arg-type]
    report = await service.execute(plan)
    assert report.completed
    return plan


async def test_a_source_only_the_complete_archive_holds_is_removed_from_it_everywhere(
    removal_world: RemovalWorld, tmp_path: Path
) -> None:
    inbox_copy = await add_complete_archive(removal_world, tmp_path / "pulled")
    assert QX_SUMMER_SHA256 in {row["sha256"] for row in bucket_rows(removal_world)}
    assert raw_key(QX_SUMMER_SHA256) in bucket_keys(removal_world)

    plan = await remove(removal_world, SourceSelector(QX_SUMMER_SHA256))

    assert {(one.key, one.side) for one in plan.manifests} == {
        (FULL_KEY, Side.LOCAL),
        (FULL_KEY, Side.BUCKET),
    }
    assert QX_SUMMER_SHA256 not in {row["sha256"] for row in local_rows(removal_world)}
    assert QX_SUMMER_SHA256 not in {row["sha256"] for row in bucket_rows(removal_world)}
    assert raw_key(QX_SUMMER_SHA256) not in bucket_keys(removal_world)
    assert await removal_world.repository.find_source(QX_SUMMER_SHA256) is None
    assert not inbox_copy.exists(), "an imported complete archive holding a removed file is deleted"


async def test_a_team_removal_drops_the_teams_rows_from_the_complete_archive_on_both_sides(
    removal_world: RemovalWorld, tmp_path: Path
) -> None:
    await add_complete_archive(removal_world, tmp_path / "pulled")

    await remove(removal_world, parse_team_selector(TEAM))

    for rows in (local_rows(removal_world), bucket_rows(removal_world)):
        paths = {str(row["path"]) for row in rows}
        assert not any(path.startswith("Maple Grove/QX/") for path in paths), sorted(paths)
        assert ZALU_SUMMER in paths, "another team's file stays"
    assert QX_SUMMER_SHA256 not in {row["sha256"] for row in bucket_rows(removal_world)}
    assert raw_key(QX_SUMMER_SHA256) not in bucket_keys(removal_world)


async def test_a_complete_archive_waiting_in_the_inbox_is_rewritten_without_the_teams_files(
    removal_world: RemovalWorld, tmp_path: Path
) -> None:
    """Not yet imported: rewritten, not deleted, as a waiting weekly is (`v1-e30-t09`).

    The team's files the store knows go, its copy of a shared file included. `QX_SUMMER` has never
    been imported, so nothing can know its digest: the plan names the archive as holding one file
    of the team it could not resolve, which is what it says of a waiting weekly too.
    """
    waiting = await add_complete_archive(removal_world, tmp_path / "pulled", imported=False)
    grove_round_1 = hashlib.sha256(
        next(member.content for member in SNAPSHOTS[-1].members if member.body == "grove-round-1-aff")
    ).hexdigest()

    plan = await remove(removal_world, parse_team_selector(TEAM))

    (planned,) = [one for one in plan.inbox if one.name == FULL_INBOX_NAME]
    assert str(planned.action) == "rewrite"
    assert [(left.name, left.files) for left in plan.inbox_team_files_left] == [(FULL_INBOX_NAME, 1)]
    entries = {entry.path for entry in ZipArchiveRewriter(**LIMITS).inventory(waiting)}
    assert {path for path in entries if path.startswith("Maple Grove/QX/")} == {QX_SUMMER}
    assert grove_round_1 in inbox_digests(waiting), "the other team's copy of the shared file stays"
