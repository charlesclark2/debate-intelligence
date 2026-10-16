"""Read what `write_held_path_files.py` wrote, with whichever build's source is first on `PYTHONPATH`.

A plain script, run by its path: `python read_held_path_files.py <written directory> <reader name>`.
It imports nothing from the test suite and only names every build since `v0.1.0-dev.122` has, so it
runs against this task's source, its start commit's and the weekly agent's build alike. Each record
is read by the build's own reader, which refuses the whole record at a line it cannot validate; a
record that build does not know is reported as not read by it. Nothing is written outside a
temporary directory. The session report of `v1-e30-t21` gives the commands and what each printed.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path

import debate_core
from debate_core.application.caselist.import_service import CaselistImportService
from debate_core.application.caselist.publish_plan import sources_in_manifest, stored_rows_in_manifest
from debate_core.application.caselist.suppression import RecordedRemovalLog, RecordedSuppressionList
from debate_core.application.ports.archive import ArchiveMember
from debate_core.application.ports.suppression import SuppressionState
from debate_core.application.sync_runs import SyncRunDetails, SyncRunRecord
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsSnapshotStore, SqliteDatabase
from debate_core.integrations.local.archive_reader import archive_digest, read_archive
from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository
from debate_core.integrations.local.suppression_list import (
    local_removal_log_file,
    local_suppression_list_file,
)
from debate_core.testing.fakes import empty_suppression_list

LIMITS = {"max_archive_bytes": 64 * 1024 * 1024, "max_unpacked_bytes": 64 * 1024 * 1024}


def archives(written: Path, scratch: Path) -> list[str]:
    lines: list[str] = []
    for archive in sorted((written / "archive").iterdir()):
        read = list(read_archive(archive, **LIMITS))
        members = sum(isinstance(entry, ArchiveMember) for entry in read)
        lines.append(f"archive {archive.name}: {members} member(s), {len(read) - members} skipped")
        data_dir = scratch / "import"
        importer = CaselistImportService(
            caselists=SqliteCaselistRepository(SqliteDatabase.open(data_dir)),
            blobs=FsSnapshotStore(data_dir),
            suppression=empty_suppression_list(),
        )
        report = asyncio.run(
            importer.import_archive(
                read_archive(archive, **LIMITS),
                caselist="testcl26",
                snapshot=date(2026, 10, 11),
                event=Event.LD,
                archive_sha256=archive_digest(archive),
                dry_run=True,
            )
        )
        counts = {str(name): count for name, count in sorted(report.counts.items()) if count}
        lines.append(f"  imported dry into an empty store: {counts}, skipped {sum(report.skipped.values())}")
    return lines


def records(written: Path, scratch: Path) -> list[str]:
    data_dir = scratch / "records"
    shutil.copytree(written / "records" / "local", data_dir / "suppression")
    listed = RecordedSuppressionList(local_suppression_list_file(data_dir))
    entries = asyncio.run(listed.entries())
    state = SuppressionState.from_entries(entries)
    lines = [
        f"suppression list: {len(entries)} line(s); {len(state.sources)} whole file(s) and "
        f"{len(state.disclosures)} disclosure(s) suppressed"
    ]
    holds = getattr(listed, "path_holds", None)
    lines.append(
        f"path holds: {len(asyncio.run(holds()))} read"
        if holds is not None
        else "path holds: this source reads no path-hold record"
    )
    log = RecordedRemovalLog(local_removal_log_file(data_dir))
    lines.append(f"removal log: {len(asyncio.run(log.entries()))} entry(ies)")
    scopes = getattr(log, "scopes", None)
    lines.append(
        f"removal scopes: {len(asyncio.run(scopes()))} read"
        if scopes is not None
        else "removal scopes: this source reads no removal-scope record"
    )
    local = sorted(path.name for path in (written / "records" / "local").iterdir())
    bucket = sorted(path.name for path in (written / "records" / "bucket").iterdir())
    lines.append(f"files here: {', '.join(local)}; in the bucket: {', '.join(bucket)}")
    return lines


def manifests(written: Path) -> list[str]:
    lines: list[str] = []
    for manifest in sorted((written / "manifests").rglob("*.jsonl")):
        text = manifest.read_text(encoding="utf-8").splitlines()
        key = f"manifests/testcl26/{manifest.relative_to(written / 'manifests').as_posix()}"
        sources = sources_in_manifest(key, text)
        rows = stored_rows_in_manifest(text)
        summary = next(json.loads(line) for line in text if json.loads(line).get("kind") == "summary")
        lines.append(
            f"manifest {manifest.relative_to(written / 'manifests').as_posix()}: {len(sources)} source(s), "
            f"{len(rows)} stored row(s), classifications {dict(sorted(summary['classifications'].items()))}"
        )
    return lines


def run(written: Path) -> list[str]:
    record = SyncRunRecord.model_validate_json((written / "run" / "record.jsonl").read_text(encoding="utf-8"))
    details = SyncRunDetails.model_validate_json(
        (written / "run" / "details.jsonl").read_text(encoding="utf-8")
    )
    stages = Counter(str(stage.outcome) for stage in record.stages)
    imported = [stage.reason for stage in record.stages if stage.stage == "import"]
    inbox = (written / "run" / "inbox.txt").read_text(encoding="utf-8").split()
    return [
        f"run record: outcome {record.outcome}, stages {dict(sorted(stages.items()))}",
        f"  import stage: {imported[0] if imported else None}",
        f"run details: read, run id {details.run_id == record.run_id and 'matches' or 'differs'}",
        f"inbox after the run: {inbox or 'empty'}",
    ]


def main() -> None:
    written, reader = Path(sys.argv[1]), sys.argv[2]
    print(f"reader: {reader} (debate_core from {Path(debate_core.__file__).parents[4].name})")
    print(f"files written by: {written.name}")
    with tempfile.TemporaryDirectory() as scratch:
        for line in [
            *archives(written, Path(scratch)),
            *records(written, Path(scratch)),
            *manifests(written),
            *run(written),
        ]:
            print(line)


if __name__ == "__main__":
    main()
