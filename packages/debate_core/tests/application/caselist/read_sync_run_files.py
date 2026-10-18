"""Read the run files `write_sync_loose_ends_files.py` wrote, with whichever build is first on the path.

A plain script that imports nothing from the test suite, so that the code reading is the build's own
`debate_core.application.sync_runs` and nothing else (`v1-e34-t23`). Each scenario's run log is
read with the build's `SyncRunLog`, which skips and logs a line it cannot validate; its details with
`SyncRunDetailsLog`, when the build has one; the file of records still owed with the build's own
reader of it; the pending-work file, when a scenario has one, with the build's own `PendingWork`
(`v1-e34-t26`); and every object under `reports/` in the bucket with the model of its kind. Any line
or object the build skips or refuses is counted and printed, and makes the exit status `1`. It also
reads what `write_drift_owed_again_files.py` writes.

    python read_sync_run_files.py <directory written> <label of the reader>
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from pydantic import ValidationError

from debate_core.application import caselist_sync, sync_runs


class Counting(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.warnings: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.warnings.append(record.getMessage())


def main(directory: Path, reader: str) -> int:
    counting = Counting()
    logging.getLogger("debate_core").addHandler(counting)
    print(f"reader: {reader} (sync_runs from {Path(sync_runs.__file__).parents[5]})")
    print(f"files written by: {directory.name}")
    refused = 0
    for scenario in sorted(one for one in directory.iterdir() if one.is_dir()):
        print(f"{scenario.name}:")
        records = sync_runs.SyncRunLog(scenario / sync_runs.SYNC_RUN_LOG_FILENAME).read()
        for record in records:
            stages = ", ".join(f"{one.stage} {one.outcome}" for one in record.stages) or "no stage"
            print(f"  record {record.run_id}: {record.outcome}; {stages}")
            print(f"    error_class {record.error_class}")
            for one in record.stages:
                if one.reason and (
                    "full/" in one.reason
                    or "docs/runbooks/" in one.reason
                    or "refused at a path" in one.reason
                ):
                    print(f"    {one.stage} reason: {one.reason}")
        details_log = getattr(sync_runs, "SyncRunDetailsLog", None)
        if details_log is None:
            print("  details: this build reads none")
        else:
            details = details_log(scenario / sync_runs.SYNC_RUN_DETAILS_FILENAME).read()
            for run_id, one in sorted(details.items()):
                codes = list(one.failure_codes)
                print(f"  details {run_id}: read, failure_codes {codes}, {len(one.stages)} stage(s)")
            missing = sorted({record.run_id for record in records} - set(details))
            if missing:
                print(f"  details missing for: {missing}")
        owed_file = scenario / sync_runs.PENDING_RECORDS_FILENAME
        if owed_file.is_file():
            owed = sync_runs._PendingRecords(owed_file).read()  # pyright: ignore[reportPrivateUsage]
            print(f"  records still owed: {owed}")
            if not owed:
                refused += 1
                print("  REFUSED: the file of records still owed read as nothing")
        pending_work = scenario / caselist_sync.PENDING_WORK_FILENAME
        if pending_work.is_file():
            try:
                owed_snapshots = caselist_sync.PendingWork(pending_work).read()
            except caselist_sync.PendingWorkUnreadable as unreadable:
                refused += 1
                print(f"  REFUSED: the pending-work file: {unreadable}")
            else:
                print(f"  pending-work file: {[f'{one.caselist} {one.snapshot}' for one in owed_snapshots]}")
        for record in records:
            if record.pending_publish:
                print(f"  record {record.run_id} pending_publish: {list(record.pending_publish)}")
        objects: dict[str, str] = json.loads((scenario / "bucket.json").read_text("utf-8"))
        for key, body in sorted(objects.items()):
            model = (
                sync_runs.SyncRunDetails
                if key.startswith("reports/sync-run-details/")
                else sync_runs.SyncRunRecord
            )
            try:
                model.model_validate_json(body)
            except ValidationError as invalid:
                refused += 1
                print(f"  REFUSED in the bucket: {key}: {invalid.error_count()} error(s)")
                continue
            print(f"  bucket {key}: read as {model.__name__}")
    for warning in counting.warnings:
        refused += 1
        print(f"WARNING: {warning}")
    print(f"refused or skipped: {refused}")
    return 1 if refused else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), sys.argv[2]))
