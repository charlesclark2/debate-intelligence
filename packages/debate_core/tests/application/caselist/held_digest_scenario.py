"""The takedown history of `suppression_list_scenario.py`, then an upload held at the removed path.

`write_held_digest_files.py` runs it to store what this build writes to the held-digest record
(`v1-e30-t23`), and `test_removal_held_digest_files_are_this_builds.py` runs it to show this build
still writes exactly that. It needs this build: no build before `v1-e30-t23` writes the record, so
the older builds are never given it. They are given its files instead, by
`check_an_older_build_reads_this_builds_files.py`.

## The history

1. to 3. are `suppression_list_scenario.py`'s. Step 2, `caselist remove --source
   <seaside-finals-pro>` under `RM-2026-02`, holds `REMOVED_BY_SOURCE_PATH` for snapshots dated after
   `2026-09-08`.
4. `caselist import` of the weekly of `2026-09-22`, which holds one new upload at that path. The
   import refuses it, stores nothing of it, and writes one line to this machine's held-digest record.
5. The same `--source` removal under `RM-2026-02`, run again and executed. It lists the upload whole,
   since nothing else holds its bytes, and gives the bucket's copy of the record the line.
"""

from __future__ import annotations

import hashlib
import zipfile
from datetime import date
from pathlib import Path
from typing import Final

from tests.fixtures.caselist.build_synthetic_archives import (
    SYNTHETIC_CASELIST,
    _docx,  # pyright: ignore[reportPrivateUsage]
)

from debate_core.application.caselist.import_service import CaselistImportService
from debate_core.application.caselist.manifest import manifest_key, write_manifest
from debate_core.application.caselist.removal_plan import SourceSelector
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.ports.suppression import ReasonCode
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsEvidenceObjectStore, FsSnapshotStore
from debate_core.integrations.local.archive_reader import archive_digest, read_archive
from debate_core.integrations.local.suppression_list import local_suppression_list_file

from .conftest import RemovalWorld
from .suppression_list_scenario import (
    REMOVED_BY_SOURCE,
    REMOVED_BY_SOURCE_PATH,
    SECOND_REQUEST,
    SUPPRESSION_PREFIX,
    a_team_removal_a_source_removal_and_an_unsuppress,
)

HELD_WEEK: Final = date(2026, 9, 22)
HELD_UPLOAD_BODY: Final = _docx(("Seaside Cup, finals, pro.", "Uploaded again at the removed path."))
HELD_UPLOAD: Final = hashlib.sha256(HELD_UPLOAD_BODY).hexdigest()
RECORD: Final = "held-digests.jsonl"
LIMITS: Final = {"max_archive_bytes": 64 * 1024 * 1024, "max_unpacked_bytes": 64 * 1024 * 1024}


def the_held_week(scratch: Path) -> Path:
    """`testcl26-weekly-2026-09-22.zip`, holding the new upload at the removed path and nothing else."""
    path = scratch / f"{SYNTHETIC_CASELIST}-weekly-{HELD_WEEK.isoformat()}.zip"
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        info = zipfile.ZipInfo(
            f"{SYNTHETIC_CASELIST}-0922/{REMOVED_BY_SOURCE_PATH}", date_time=(1980, 1, 1, 0, 0, 0)
        )
        archive.writestr(info, HELD_UPLOAD_BODY)
    return path


async def an_upload_held_and_the_removal_run_again(world: RemovalWorld, scratch: Path) -> None:
    """Carry out the history in the module docstring, through the services the commands run."""
    await a_team_removal_a_source_removal_and_an_unsuppress(world)
    archive = the_held_week(scratch)
    importer = CaselistImportService(
        caselists=world.repository,
        blobs=FsSnapshotStore(world.data_dir),
        suppression=RecordedSuppressionList(local_suppression_list_file(world.data_dir)),
    )
    report = await importer.import_archive(
        read_archive(archive, **LIMITS),
        caselist=SYNTHETIC_CASELIST,
        snapshot=HELD_WEEK,
        event=Event.LD,
        archive_sha256=archive_digest(archive),
    )
    assert report.held_by_request == {SECOND_REQUEST: 1}, "the precondition: the upload was held"
    write_manifest(
        report, FsEvidenceObjectStore(world.data_dir).path_for(manifest_key(SYNTHETIC_CASELIST, HELD_WEEK))
    )
    service = world.service()
    again = await service.plan(
        SourceSelector(REMOVED_BY_SOURCE), request_id=SECOND_REQUEST, reason=ReasonCode.REQUESTED_BY_SCHOOL
    )
    assert again.source(HELD_UPLOAD) is not None, "the precondition: the re-run lists the held upload"
    assert (await service.execute(again)).completed


def held_digest_records(world: RemovalWorld) -> dict[str, bytes]:
    """The record on this machine and in the bucket, keyed `local/<name>` and `bucket/<name>`."""
    local = (world.data_dir / "suppression" / RECORD).read_bytes()
    bucket = world.client.get_object(Bucket=world.bucket_name, Key=f"{SUPPRESSION_PREFIX}{RECORD}")[
        "Body"
    ].read()
    return {f"local/{RECORD}": local, f"bucket/{RECORD}": bucket}
