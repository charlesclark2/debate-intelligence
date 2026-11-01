"""An older build's own code, reading a weekly run's details with this build's memory figures (`v1-e40-t31`).

Not collected: its name is not a test module's. It is run by its path with an earlier build's Python,
so that `debate_core` is that build's, as `run_memory_figures/README.md` says, and prints what that
build's readers made of the details. It writes nothing outside a temporary directory, and needs no
network: the bucket is the filesystem object store, behind the same port as S3's.

The details are `run_memory_figures/details_this_build_writes.json`, which this build's tests show is
what it writes for that run (`test_caselist_sync_memory_figures.py`). The record beside them is a
record an older build wrote (`stored_run_records/written_by_the_start_commit/`), given this run's id
and times. The build's readers are:

* its details file, `SyncRunDetailsLog.read`, which `caselist runs` reads on the machine that ran;
* the bucket, `read_remote_runs`, which `caselist runs --remote` reads.

Each must return the run with its details, every stage's entry with its stage and times as written.
A path given as the one argument is read in place of that file: details a changed build wrote, to see
whether the older builds still read them.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import debate_core
from debate_core.application.sync_runs import (
    StageTiming,
    SyncRunDetailsLog,
    read_remote_runs,
    sync_run_details_key,
    sync_run_key,
)
from debate_core.integrations.local import FsEvidenceObjectStore

HERE = Path(__file__).parent
DETAILS = HERE / "run_memory_figures" / "details_this_build_writes.json"
OLDER_RECORD = HERE / "stored_run_records" / "written_by_the_start_commit" / "a_week_imported_and_published.bucket.json"


def this_runs_record(details: dict[str, Any]) -> dict[str, Any]:
    [body] = json.loads(OLDER_RECORD.read_text(encoding="utf-8")).values()
    record: dict[str, Any] = json.loads(body)
    times = details["stage_times"]
    record |= {"run_id": details["run_id"], "started_at": times[0]["started_at"], "finished_at": times[-1]["finished_at"]}
    return record


def as_written(details: dict[str, Any]) -> list[tuple[str, str, str]]:
    return [(one["stage"], one["started_at"], one["finished_at"]) for one in details["stage_times"]]


def as_read(entries: tuple[StageTiming, ...]) -> list[tuple[str, str, str]]:
    def iso(moment: Any) -> str:
        return moment.isoformat().replace("+00:00", "Z")

    return [(one.stage, iso(one.started_at), iso(one.finished_at)) for one in entries]


async def main() -> int:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else DETAILS
    details: dict[str, Any] = json.loads(source.read_text(encoding="utf-8"))
    line = json.dumps(details, separators=(",", ":"))
    run_id = details["run_id"]
    expected = as_written(details)
    print(f"reader: the debate_core source at {Path(debate_core.__file__).parent}")
    print(f"its stage entry keeps the figures: {'memory' in StageTiming.model_fields}")
    failures = 0
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)

        log = root / "caselist-sync-run-details.jsonl"
        log.write_text(line + "\n", encoding="utf-8")
        found = SyncRunDetailsLog(log).read().get(run_id)
        same = found is not None and as_read(found.stage_times) == expected
        print(f"details file: the run read {found is not None}; {len(found.stage_times) if found else 0} stage(s), as written: {same}")
        failures += not same

        bucket = FsEvidenceObjectStore(root / "bucket")
        record = this_runs_record(details)
        record_key = sync_run_key(run_id, datetime.fromisoformat(record["started_at"]))
        (root / "record.json").write_text(json.dumps(record), encoding="utf-8")
        (root / "details.json").write_text(line, encoding="utf-8")
        await bucket.put_file(record_key, root / "record.json")
        await bucket.put_file(sync_run_details_key(record_key), root / "details.json")
        runs = await read_remote_runs(bucket, last=5, scratch_dir=root / "scratch")
        read = runs[0].details if len(runs) == 1 and runs[0].record.run_id == run_id else None
        same = read is not None and as_read(read.stage_times) == expected
        print(f"bucket: {len(runs)} run(s), its details read {read is not None}; stages as written: {same}")
        failures += not same
    print("PASS" if not failures else f"FAIL: {failures} reader(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
