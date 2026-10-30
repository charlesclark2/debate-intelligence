# Stored run records

What builds before `v1-e34-t19` say a run record is, and what they wrote. Nothing here is written
by hand, and nothing here is real caselist content: every run is a pull of the invented archives
under `tests/fixtures/`, against moto, at a fixed clock.

`test_pull_run_record_is_read_by_every_build.py` reads these to show that a newer build's records
are ones an installed build reads, and the reverse.

| File | Written by | What it is |
|---|---|---|
| `record_schema_of_the_start_commit.json` | The source at `0a9c1e6`, the commit on `dev` that `v1-e34-t19` started from (`v1-e34-t17`'s build) | `SyncRunRecord.model_json_schema()`: every field, type and limit, and that no other field is allowed |
| `record_schema_of_the_installed_build.json` | The build the weekly agent ran on 2026-10-11, `0.1.0.dev60`, installed 2026-10-07, before `v1-e34-t12` | The same, printed by that build's own code. Byte for byte the file above |
| `written_by_the_start_commit/<scenario>.run-log.jsonl` | The source at `0a9c1e6` | The run log that build left after the scenario: one record a line. Ten scenarios; the tenth is [the refusal to start](#the-refusal-to-start-v1-e34-t22) |
| `written_by_the_start_commit/<scenario>.bucket.json` | The source at `0a9c1e6` | Every object that build put under `reports/sync-runs/`, key to body |
| `run_log_written_by_a_schema_3_build.jsonl`, `run_summary_schema_3.json` | A build before `v1-e34-t13` | Kept by that task; see `test_pull_stage_failure_codes.py` |
| `details_schema_before_parsed_stores_owed.json` | `v1.1.0-dev.155` (`76b53e7`), the Mac's installed build at the cutover, and `b0cf40f`, the commit on `dev` that `v1-e34-t31` started from | `SyncRunDetails.model_json_schema()`, byte for byte the same from both: what those builds read a run's details with. It allows a key it does not define and refuses one of its own keys with another type. `test_caselist_sync_names_publish_only_per_caselist.py` holds the details this build writes to it |

The scenarios are the functions of `run_record_scenarios.py`, which gives each build the same
run to record, so the same file runs against either source. Two things keep that true after
`v1-e29-t07`, which merged while this task was in review:

* The refused publish raises the refusal the start commit's tests raised, with no fix written into
  it. The bucket's adapter now writes one, and the start commit's adapter cannot be given it. That
  run is `a_publish_the_bucket_refused_with_the_adapters_fix`: it is not stored, and a test shows
  its record is the stored one but for the words of one stage's reason.
* A test module the scenarios borrow their installation from now imports an error class the start
  commit lacks. `write_stored_run_records.py` supplies that one name before it imports them, in
  memory only. None of the first nine scenarios raises it. Run again on 2026-10-11 after the rebase
  onto `7a2b869`, the command below rewrote all 18 files and changed none.

## The refusal to start (`v1-e34-t22`)

`a_refusal_to_start_published_by_the_next_run` is the tenth scenario: the profile setting names a
profile the AWS config lacks, the bucket's adapter cannot be built, and the run is refused before
any stage; the week after, a pull publishes that run's record with its own. No build before
`v1-e34-t22` ever recorded such a run, because its run monitor needed the adapter built and could
not be built without it. So the start commit's code is given the nearest thing it can be given,
and two things are supplied to it that its source lacks:

* **The bucket.** Its monitor takes a bucket that is already built, and is handed one whose every
  call raises the refusal. This build's monitor is handed the bucket to build, and building it
  raises the refusal. `World.pull_with_no_bucket` chooses by what the monitor's signature takes.
* **The error.** The start commit predates `StoreProfileNotConfigured` (`v1-e29-t07`).
  `write_stored_run_records.py` defines a class of that name whose message is this build's,
  copied out by hand, and hands the scenario an instance of it. Against a source that has the
  error, the scenario uses the S3 adapter's own translation of botocore's `ProfileNotFound`.

What is stored is therefore what the start commit's **recording** code wrote when handed this
failure: the record model, the redaction, the run log and the publish of what is owed are all
that build's. The record it wrote is an ordinary failed one, with the error's class and message
and no stage, which is why this build's record for the refusal is one every build reads. The
comparison is exact, the message included, so a change to that error's wording fails
`test_the_run_log_this_build_writes_is_read_by_the_older_builds` for this scenario; compare the
records but for those words then, as the refused publish above is compared, and leave these files
as they are. A test of the CLI checks that the command, with boto3 refusing a real session, writes
the stored line byte for byte
(`packages/debate_cli/tests/test_pull_refused_before_the_bucket_is_built.py`).

Run on 2026-10-12, the command below wrote this scenario's two files and rewrote the other 18,
changing none of them.

**Those words, since `v1-e34-t23`.** The start commit's redaction took the runbook the error's
message points at, `docs/runbooks/evidence-store.md`, for a path, and its record says
`[redacted] lists the evidence profiles`. This build's redaction keeps the runbook. The stored
files are left as that build wrote them; the comparison reads them with that one phrase in place
of the other (`WORDS_THIS_BUILD_KEEPS` in the test) and requires everything else to be equal.

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
git archive 0a9c1e6 packages/debate_core/src packages/debate_cli/src | tar -x -C "${START}"
WRITE_STORED_RUN_RECORDS=from-the-start-commit PYTHONPATH="${START}/packages/debate_core/src:${START}/packages/debate_cli/src" uv run --frozen pytest packages/debate_core/tests/application/caselist/write_stored_run_records.py -p no:cacheprovider --no-cov -n 0
```

`write_stored_run_records.py` is not a test module and is never collected; it runs only when named.
It refuses to run without the variable above, because it overwrites these files.

The details schema (`v1-e34-t31`), by each of the two builds, each exported the same way. `DEV155`
and `START31` are the two directories and `CHECKOUT` is the worktree. The last two lines ran from
the scratch directory, with the worktree's interpreter and without `-I`, which would set
`PYTHONPATH` aside and read the worktree's own source:

```bash
git archive v1.1.0-dev.155 packages/debate_core/src | tar -x -C "${DEV155}"
git archive b0cf40f packages/debate_core/src | tar -x -C "${START31}"
PYTHONPATH="${DEV155}/packages/debate_core/src" "${CHECKOUT}/.venv/bin/python" -c 'import json,sys; from debate_core.application.sync_runs import SyncRunDetails; sys.stdout.write(json.dumps(SyncRunDetails.model_json_schema(), indent=2, sort_keys=True) + "\n")'
PYTHONPATH="${START31}/packages/debate_core/src" "${CHECKOUT}/.venv/bin/python" -c 'import json,sys; from debate_core.application.sync_runs import SyncRunDetails; sys.stdout.write(json.dumps(SyncRunDetails.model_json_schema(), indent=2, sort_keys=True) + "\n")'
```

## When these may change

They may not. They are what those builds wrote, and a build that is installed does not change.
When no machine runs a build older than `v1-e34-t19`, the record may be allowed to change again,
and this directory and the tests that hold the record to it go together.
