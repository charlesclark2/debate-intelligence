"""Read the run files `write_sync_loose_ends_files.py` wrote, with whichever build is first on the path.

A plain script that imports nothing from the test suite, so that the code reading is the build's own
`debate_core.application.sync_runs` and nothing else (`v1-e34-t23`). Each scenario's run log is
read with the build's `SyncRunLog`, which skips and logs a line it cannot validate; its details with
`SyncRunDetailsLog`, when the build has one; the file of records still owed with the build's own
reader of it; the pending-work file, when a scenario has one, with the build's own `PendingWork`
(`v1-e34-t26`); and every object under `reports/` in the bucket with the model of its kind. Any line
or object the build skips or refuses is counted and printed, and makes the exit status `1`. It also
reads what `write_drift_owed_again_files.py` and `write_newer_fingerprint_table_files.py` write,
printing a refused parse stage's reason and its details' hint (`v1-e34-t29`).

For files that carry the keys `v1-e34-t28` added to the details (`not_compared` on a stage,
`manifests_published`), and only for those, so that what it prints of earlier tasks' files is as
those tasks recorded it, it also prints each key as written and as the build's model kept it, a
publish stage's reason, and what the build's own readers of a whole history make of the scenario:
the snapshots owed again for drift, and `caselist runs`' runs with their banner words, when the
build has them.

For files that carry the key `v1-e34-t31` added to the details (`parsed_stores_owed`), and only for
those, it also prints the key as written and as the build's model kept it, the parse stage's reason
in the record, and the notifications the build's own `notifications_for` makes of the record and the
details it kept: each title and command, and the parsed store's sentence of a login banner. Since
`v1-e40-t18` it also prints, for the same files, whether the build kept the details' `bucket_run` and
the parse stage's hint as it kept it, which is the cloud cure in a bucket-mode run. Since `v1-e40-t22`
it also prints each banner's hint, which is where the failure-rate and newer-table hints reach one.

    python read_sync_run_files.py <directory written> <label of the reader>
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import tempfile
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
                    or "occurrence table" in one.reason
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
                for told in one.stages:
                    if "NEWER_FINGERPRINT_TABLE" in told.error_codes:
                        print(f"    {told.stage} error_codes {list(told.error_codes)}; hint: {told.hint}")
            missing = sorted({record.run_id for record in records} - set(details))
            if missing:
                print(f"  details missing for: {missing}")
            _print_what_t28_added(scenario, records, details)
            _print_what_t31_added(scenario, records, details)
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


def _print_what_t28_added(
    scenario: Path, records: list[sync_runs.SyncRunRecord], details: dict[str, sync_runs.SyncRunDetails]
) -> None:
    """The keys `v1-e34-t28` added, as written and as this build kept them; nothing for older files."""
    path = scenario / sync_runs.SYNC_RUN_DETAILS_FILENAME
    written = [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]
    if not any("manifests_published" in one for one in written):
        return
    for raw in written:
        kept = details.get(raw["run_id"])
        kept_count = getattr(kept, "manifests_published", "unknown here")
        print(f"  details {raw['run_id']} as written: manifests_published {raw.get('manifests_published')}")
        print(f"    kept by this build: manifests_published {kept_count}")
        report = next((one for one in raw["stages"] if one["stage"] == "report"), None)
        if report is not None:
            kept_report = kept.stage("report") if kept is not None else None
            print(f"    report not_compared as written: {report.get('not_compared')}")
            print(f"    kept by this build: {getattr(kept_report, 'not_compared', 'unknown here')}")
    for record in records:
        for one in record.stages:
            if one.stage == "publish":
                print(f"  record {record.run_id} publish reason: {one.reason}")
                print(f"    objects_published {record.objects_published}")
    owed_again = getattr(sync_runs, "snapshots_owed_again_for_drift", None)
    if owed_again is not None:
        found = sorted(f"{one.caselist} {one.snapshot}" for one in owed_again(records, details))
        print(f"  owed again for drift, by this build's reader: {found}")
    history = getattr(sync_runs, "SyncRunHistory", None)
    words = getattr(sync_runs, "banner_words", None)
    if history is None:
        return
    with tempfile.TemporaryDirectory() as scratch:
        runs = asyncio.run(
            history(
                log=sync_runs.SyncRunLog(scenario / sync_runs.SYNC_RUN_LOG_FILENAME),
                remote=None,
                scratch_dir=Path(scratch),
                overdue_after_days=8,
            ).recent_runs(10)
        )
    for one in runs:
        banner = words(one.record, one.details) if words is not None else "no banner words in this build"
        read = "read" if one.details is not None else "none"
        print(f"  caselist runs: {one.record.run_id} {one.record.outcome}, details {read}, banner {banner}")


def _print_what_t31_added(
    scenario: Path, records: list[sync_runs.SyncRunRecord], details: dict[str, sync_runs.SyncRunDetails]
) -> None:
    """The key `v1-e34-t31` added, as written and as this build kept it, and this build's banners."""
    path = scenario / sync_runs.SYNC_RUN_DETAILS_FILENAME
    written = [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]
    if not any("parsed_stores_owed" in one for one in written):
        return
    for raw in written:
        kept = details.get(raw["run_id"])
        print(f"  details {raw['run_id']} as written: parsed_stores_owed {raw.get('parsed_stores_owed')}")
        owed = getattr(kept, "parsed_stores_owed", "unknown here")
        if not isinstance(owed, str):
            owed = [(one.caselist, one.publish_only) for one in owed]
        print(f"    kept by this build: parsed_stores_owed {owed}")
        if kept is not None:
            bucket_run = "kept" if getattr(kept, "bucket_run", None) is not None else "none"
            parse = kept.stage("parse")
            hint = parse.hint if parse is not None else None
            print(f"    kept by this build: bucket_run {bucket_run}; parse hint {hint!r}")
    for record in records:
        for one in record.stages:
            if one.stage == "parse":
                print(f"  record {record.run_id} parse {one.outcome}: {one.reason}")
        kept = details.get(record.run_id)
        if kept is None:
            continue
        sent = sync_runs.notifications_for(
            record,
            kept,
            aws_login_command="aws sso login",
            credentials_expired=record.outcome == "publish_pending",
        )
        for notification in sent:
            print(f"  banner {notification.title!r}: fix {notification.fix_command!r}")
            if notification.hint:
                print(f"    hint {notification.hint!r}")
            waits = notification.message.partition(" The parsed store waits too")[2]
            if waits:
                print(f"    the parsed store waits too{waits}")


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), sys.argv[2]))
