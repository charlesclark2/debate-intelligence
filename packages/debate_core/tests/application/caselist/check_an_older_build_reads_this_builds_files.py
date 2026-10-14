"""An older build's own code, reading the takedown's records as this build writes them.

Not collected: its name is not a test module's, and it is only ever run by its path, with an older
build's source first on `PYTHONPATH`. `stored_suppression_lists/README.md` gives the commands and
what each printed. It writes nothing outside pytest's temporary directory.

It carries out the stored history with the source it is run against, then puts
`stored_suppression_lists/written_by_this_build/` where that build keeps the records, on this
machine and in the bucket, the path entries included. Then it does what the weekly agent does with
a suppression list: reads it, imports next Monday's archive against it, publishes, and asks for the
status.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import pytest
from tests.fixtures.caselist.build_synthetic_archives import (
    SNAPSHOTS,
    SYNTHETIC_CASELIST,
    build_snapshot_zips,
)

from debate_core.application.caselist.import_service import CaselistImportService, Classification
from debate_core.application.caselist.manifest import manifest_key, write_manifest
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.status_service import CaselistStatusService
from debate_core.application.caselist.suppression import RecordedSuppressionList, load_suppression_state
from debate_core.application.ports.suppression import UnreadableAppendOnlyRecord
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsEvidenceObjectStore, FsSnapshotStore, SqliteDatabase
from debate_core.integrations.local.archive_reader import archive_digest, read_archive
from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository
from debate_core.integrations.local.suppression_list import local_suppression_list_file

from .conftest import RemovalWorld
from .suppression_list_scenario import (
    REMOVED_BY_SOURCE,
    REMOVED_WITH_THE_TEAM,
    SUPPRESSION_PREFIX,
    UNSUPPRESSED,
    WITHDRAWN_FROM_THE_TEAM,
    a_team_removal_a_source_removal_and_an_unsuppress,
)

pytestmark = pytest.mark.anyio

WRITTEN_BY_THIS_BUILD = Path(__file__).parent / "stored_suppression_lists" / "written_by_this_build"
LIMITS = {"max_archive_bytes": 64 * 1024 * 1024, "max_unpacked_bytes": 64 * 1024 * 1024}


def put_this_builds_files_where_the_records_are_kept(world: RemovalWorld) -> list[str]:
    placed: list[str] = []
    for stored in sorted((WRITTEN_BY_THIS_BUILD / "local").iterdir()):
        (world.data_dir / "suppression" / stored.name).write_bytes(stored.read_bytes())
        placed.append(f"suppression/{stored.name}")
    for stored in sorted((WRITTEN_BY_THIS_BUILD / "bucket").iterdir()):
        key = f"{SUPPRESSION_PREFIX}{stored.name}"
        world.client.put_object(Bucket=world.bucket_name, Key=key, Body=stored.read_bytes())
        placed.append(f"s3://<bucket>/{key}")
    return placed


async def test_this_source_reads_the_records_as_this_task_writes_them(
    removal_world: RemovalWorld, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert os.environ.get("CHECK_AN_OLDER_BUILD_READS") == "this-builds-files", (
        "run by its path against an older build's source; see stored_suppression_lists/README.md"
    )
    world = removal_world
    await a_team_removal_a_source_removal_and_an_unsuppress(world)
    placed = put_this_builds_files_where_the_records_are_kept(world)

    state = await load_suppression_state(world.suppression())
    assert state.sources == {*REMOVED_WITH_THE_TEAM, REMOVED_BY_SOURCE} - {UNSUPPRESSED}
    assert len(state.disclosures) == 2

    # Next Monday: the third week's archive again, against this machine's copy of the list.
    archive = build_snapshot_zips(tmp_path / "next-monday")[SNAPSHOTS[-1].snapshot]
    importer = CaselistImportService(
        caselists=world.repository,
        blobs=FsSnapshotStore(world.data_dir),
        suppression=RecordedSuppressionList(local_suppression_list_file(world.data_dir)),
    )
    report = await importer.import_archive(
        read_archive(archive, **LIMITS),
        caselist=SYNTHETIC_CASELIST,
        snapshot=date(2026, 9, 22),
        event=Event.LD,
        archive_sha256=archive_digest(archive),
    )
    write_manifest(
        report,
        FsEvidenceObjectStore(world.data_dir).path_for(manifest_key(SYNTHETIC_CASELIST, date(2026, 9, 22))),
    )
    # The revised Round 2 negative, the Round 1 affirmative at the team's two paths, and the file
    # removed by --source. The file that was un-suppressed is stored again.
    assert report.count(Classification.SUPPRESSED) == 4

    publisher = CaselistPublishService(
        local=world.local, remote=world.bucket, suppression=world.suppression()
    )
    published = await publisher.execute(await publisher.plan(SYNTHETIC_CASELIST))
    assert published.succeeded
    status = await CaselistStatusService(
        local=world.local, remote=world.bucket, suppression=world.suppression()
    ).status()
    assert status.in_sync

    with capsys.disabled():
        print()
        print(f"reader: the debate_core source at {_source()}")
        print(f"placed: {', '.join(placed)}")
        whole, scoped = len(state.sources), len(state.disclosures)
        print(f"list read: {whole} whole file(s) and {scoped} disclosure(s) suppressed")
        print(f"knows of path holds: {hasattr(state, 'held_paths')}")
        print(f"import of the next week: SUPPRESSED {report.count(Classification.SUPPRESSED)}, completed")
        print(f"publish: succeeded {published.succeeded}; status in sync: {status.in_sync}")


async def test_this_source_refuses_the_whole_list_if_a_path_entry_is_written_into_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Why the path entries are not lines of the list: what a build does with a line it does not know."""
    assert os.environ.get("CHECK_AN_OLDER_BUILD_READS") == "this-builds-files", (
        "run by its path against an older build's source; see stored_suppression_lists/README.md"
    )
    data_dir = tmp_path / "evidence"
    listed = (WRITTEN_BY_THIS_BUILD / "local" / "suppression-list.jsonl").read_text(encoding="utf-8")
    (path_entry,) = (WRITTEN_BY_THIS_BUILD / "local" / "path-holds.jsonl").read_text(encoding="utf-8").split()
    record = local_suppression_list_file(data_dir)
    await record.append_lines([*listed.splitlines(), path_entry])

    with pytest.raises(UnreadableAppendOnlyRecord) as refused:
        await load_suppression_state(RecordedSuppressionList(record))
    importer = CaselistImportService(
        caselists=SqliteCaselistRepository(SqliteDatabase.open(data_dir)),
        blobs=FsSnapshotStore(data_dir),
        suppression=RecordedSuppressionList(record),
    )
    archive = build_snapshot_zips(tmp_path / "a-week")[SNAPSHOTS[0].snapshot]
    with pytest.raises(UnreadableAppendOnlyRecord):
        await importer.import_archive(
            read_archive(archive, **LIMITS),
            caselist=SYNTHETIC_CASELIST,
            snapshot=SNAPSHOTS[0].snapshot,
            event=Event.LD,
            archive_sha256=archive_digest(archive),
        )
    assert not (data_dir / "blobs").exists(), "nothing was imported"

    with capsys.disabled():
        print()
        print(f"reader: the debate_core source at {_source()}")
        error, line = type(refused.value).__name__, refused.value.line_number
        print(f"a path entry written into the list: {error} at line {line}")
        print("the whole list is refused, and an import against it fails with nothing stored")


def _source() -> str:
    import debate_core

    return Path(debate_core.__file__).parents[4].name


async def test_this_source_refuses_the_removal_scopes_if_a_scope_line_carries_a_withdrawals_caselist(
    removal_world: RemovalWorld, capsys: pytest.CaptureFixture[str]
) -> None:
    """Why a withdrawal's caselist is not in `removal-scopes.jsonl` (`v1-e30-t16`).

    The scope record is `v1-e30-t15`'s, and the build at `v1-e30-t16`'s start commit reads it on every
    `caselist status`. This carries out the history with the source it is run against, writes the
    last scope line that source wrote again with one more field, the caselist of a withdrawal, and
    then instead a line of a new kind holding only that, and each time asks that source's own log
    reader and its status for the scopes. A source from before `v1-e30-t15` reads no scope record.
    """
    assert os.environ.get("CHECK_AN_OLDER_BUILD_READS") == "this-builds-files", (
        "run by its path against an older build's source; see stored_suppression_lists/README.md"
    )
    from debate_core.application.caselist.suppression import RecordedRemovalLog
    from debate_core.integrations.local.suppression_list import local_removal_log_file

    with capsys.disabled():
        print()
        print(f"reader: the debate_core source at {_source()}")
    if not hasattr(RecordedRemovalLog, "scopes"):
        with capsys.disabled():
            print(
                "removal scopes: this source reads no removal-scope record, so nothing added to one is read"
            )
        return
    from debate_core.integrations.s3 import S3EvidenceVersionStore

    world = removal_world
    await a_team_removal_a_source_removal_and_an_unsuppress(world)
    scopes = world.data_dir / "suppression" / "removal-scopes.jsonl"
    written = scopes.read_text(encoding="utf-8").splitlines()
    carried = json.loads(written[-1]) | {"withdrawn_from": {WITHDRAWN_FROM_THE_TEAM: [SYNTHETIC_CASELIST]}}
    alone = {"schema_version": 1, "sha256": WITHDRAWN_FROM_THE_TEAM, "caselist": SYNTHETIC_CASELIST}
    for shape, line in (("one more field of its line", carried), ("a line of its own", alone)):
        added = json.dumps(line, sort_keys=True, separators=(",", ":"))
        scopes.write_text("".join(f"{one}\n" for one in (*written, added)), encoding="utf-8")
        log = RecordedRemovalLog(local_removal_log_file(world.data_dir))
        with pytest.raises(UnreadableAppendOnlyRecord) as refused:
            await log.scopes()
        status = CaselistStatusService(
            local=world.local,
            remote=world.bucket,
            suppression=world.suppression(),
            versions=S3EvidenceVersionStore(bucket=world.bucket_name, client=world.client),
            removal_log=log,
            environment="dev",
        )
        with pytest.raises(UnreadableAppendOnlyRecord):
            await status.status(residue=True)
        with capsys.disabled():
            error, number = type(refused.value).__name__, refused.value.line_number
            print(f"a withdrawal's caselist in the scope record, as {shape}: {error} at line {number}")
    with capsys.disabled():
        print("so `caselist status` with the residue check fails on every run until the line is gone")
