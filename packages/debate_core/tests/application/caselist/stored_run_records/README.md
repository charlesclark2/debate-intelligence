# Stored run records

What builds before `v1-e34-t19` say a run record is, and what they wrote. Nothing here is written
by hand, and nothing here is real caselist content: every run is a pull of the invented archives
under `tests/fixtures/`, against moto, at a fixed clock.

`test_pull_run_record_is_read_by_every_build.py` reads these to show that a newer build's records
are ones an installed build reads, and the reverse.

| File | Written by | What it is |
|---|---|---|
| `record_schema_of_the_start_commit.json` | The source at `ccc5153`, the commit `v1-e34-t19` started from (`v1-e34-t17`'s build) | `SyncRunRecord.model_json_schema()`: every field, type and limit, and that no other field is allowed |
| `record_schema_of_the_installed_build.json` | The build the weekly agent ran on 2026-10-11, `0.1.0.dev60`, installed 2026-10-07, before `v1-e34-t12` | The same, printed by that build's own code. Byte for byte the file above |
| `written_by_the_start_commit/<scenario>.run-log.jsonl` | The source at `ccc5153` | The run log that build left after the scenario: one record a line |
| `written_by_the_start_commit/<scenario>.bucket.json` | The source at `ccc5153` | Every object that build put under `reports/sync-runs/`, key to body |
| `run_log_written_by_a_schema_3_build.jsonl`, `run_summary_schema_3.json` | A build before `v1-e34-t13` | Kept by that task; see `test_pull_stage_failure_codes.py` |

The scenarios are the functions of `run_record_scenarios.py`, which gives each build the same
run to record, so the same file runs against either source. Two things keep that true after
`v1-e29-t07`, which merged while this task was in review:

* The refused publish raises the refusal the start commit's tests raised, with no fix written into
  it. The bucket's adapter now writes one, and the start commit's adapter cannot be given it. That
  run is `a_publish_the_bucket_refused_with_the_adapters_fix`: it is not stored, and a test shows
  its record is the stored one but for the words of one stage's reason.
* A test module the scenarios borrow their installation from now imports an error class the start
  commit lacks. `write_stored_run_records.py` supplies that one name before it imports them, in
  memory only. No scenario raises it. Run again on 2026-10-11 after the rebase onto `7a2b869`, the
  command below rewrote all 18 files and changed none.

## How they were written

The two schemas, each by the build it describes. The second line reads the installed build and
writes nothing to it:

```bash
PYTHONPATH="${START}/packages/debate_core/src" uv run --frozen python -c 'import json,sys; from debate_core.application.sync_runs import SyncRunRecord; sys.stdout.write(json.dumps(SyncRunRecord.model_json_schema(), indent=2, sort_keys=True) + "\n")'
~/.local/share/uv/tools/debate-cli/bin/python -B -I -c 'import json,sys; from debate_core.application.sync_runs import SyncRunRecord; sys.stdout.write(json.dumps(SyncRunRecord.model_json_schema(), indent=2, sort_keys=True) + "\n")'
```

The records, by running the scenarios against the start commit's source, exported to a scratch
directory so that no checkout or stash is involved. `START` is that directory:

```bash
git archive ccc5153 packages/debate_core/src packages/debate_cli/src | tar -x -C "${START}"
WRITE_STORED_RUN_RECORDS=from-the-start-commit PYTHONPATH="${START}/packages/debate_core/src:${START}/packages/debate_cli/src" uv run --frozen pytest packages/debate_core/tests/application/caselist/write_stored_run_records.py -p no:cacheprovider --no-cov -n 0
```

`write_stored_run_records.py` is not a test module and is never collected; it runs only when named.
It refuses to run without the variable above, because it overwrites these files.

## When these may change

They may not. They are what those builds wrote, and a build that is installed does not change.
When no machine runs a build older than `v1-e34-t19`, the record may be allowed to change again,
and this directory and the tests that hold the record to it go together.
