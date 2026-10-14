# Session report: v1-e30-t13-removed-path-holds-caselist-uploads

| | |
|---|---|
| Task | `v1-e30-t13-removed-path-holds-caselist-uploads` — A removed caselist path holds the uploads that arrive after the removal |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t13-removed-path-holds-caselist-uploads.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t13-removed-path-holds-caselist-uploads.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t13-removed-path-holds-caselist-uploads` |
| Session status | COMPLETE. The Goal is left `InProgress`: ac5's policy clause is the PM's to write (Summary, Deviation 1) |

## Summary

A whole-file `caselist remove --source` now appends a path entry for each caselist path it takes
the file from. From then on `caselist import` and `caselist pull` refuse a new sha256 at that path,
in a weekly or a complete archive, and count it as `SUPPRESSED` under the removal's request. The
removal plan reads the archives in the download inbox as snapshots, so a revision waiting there is
a later upload like one in a manifest, and the executed removal takes it out. Running the same
removal again finds what arrived afterwards. `--only-named` writes no path entry, and neither does
a file the plan withdraws or skips.

**The compatibility finding decided the shape.** Both older builds refuse the whole suppression
list at a line they cannot validate, and an import against that list fails. So the path entries are
not lines of the list. They are in `path-holds.jsonl`, beside the list on this machine and in the
bucket, which neither older build opens. The list and the removal log this build writes are byte
for byte what both older builds wrote for the same removals.

**Three things to look at first:**

1. **The phase is `InProgress`.** ac5 asks the data-use policy to name the hold. You told me the
   policy is yours to change, so I changed only the runbook. The sentence I propose is under
   Follow-up work 1. With it in, the phase is one command:
   `uv run scripts/task_helper.py set-phase v1-e30-t13-removed-path-holds-caselist-uploads Succeeded`.
2. **Deviation 2 is a reading of ac1.** The import counts the refused upload under the removal's
   request and appends nothing to the suppression list. The list entry for it is appended when the
   same removal is run again.
3. **The older builds do not apply the hold** (Decision 9). Until the weekly agent runs a build with
   this task, it imports a new upload at a held path, and nothing fails. Running the same removal
   again finds it, and the runbook says to do that after each pull until then.

42 mutations were run: 40 caught, and two that survived until I added the test each showed was
missing. One of the two found a real defect, which is fixed.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `path-hold`: A removed path holds later caselist uploads | Done | The path entry, the importer's check, the inbox in the plan, the compatibility evidence and the runbook. Its criterion passes: 507 tests. |

## Acceptance criteria

Commit ids are on `origin/dev` at `50eae0d`. `dev` moved once during the session
(`v1-e01-t27-ci-test-job-within-budget`, #235), so I ran
`scripts/task sync v1-e30-t13-removed-path-holds-caselist-uploads`. The branch was not on origin,
so it rebased and pushed nothing, and the rebase was clean: the two sides have no file in common.
Everything below was run again after it. `git ls-remote origin dev` still gave `50eae0d` when this
was written.

"The start commit" is `7efe8c6`, tag `v0.1.0-dev.119`. "The installed build" is `0.1.0.dev60`, tag
`v0.1.0-dev.60` (`ec7b95e`). I did not open or run the installed build: its source is the tag its
version names, exported with `git archive` into a scratch directory.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: a whole-file `--source` removal writes a path entry, and an import of a new sha256 at that path in that caselist, in a later weekly or complete archive, is refused and recorded as suppressed under the removal's request; shown failing first | PASS, with a reading of "recorded as suppressed under the removal's request" (Deviation 2) | Fixture `tests/fixtures/caselist/build_held_path_archives.py`: four archives that arrive after the removal, with each import's counts worked out by hand in its docstring. **Red first**, against the start commit's source put first on `PYTHONPATH`: `test_removed_path_holds_later_imports.py` and `test_removal_covers_inbox_revisions.py` ask the services for nothing this task added → **7 failed, 7 passed**, every failure an assertion. The weekly: `{'NEW': 2, …} == {'SUPPRESSED': 1, 'NEW': 1, …}`. The complete archive: `{'NEW': 1, 'UNCHANGED': 1} == {'SUPPRESSED': 1, 'UNCHANGED': 1}`. **Green** on `3b94313`: 14 passed. The entry itself: `test_the_plan_carries_one_path_entry_for_the_one_path_the_file_is_removed_from` and `test_the_executed_removal_writes_it_beside_the_list_here_and_in_the_bucket` compare it with a dict written by hand. Under the request: `test_the_import_counts_the_refused_upload_under_the_removals_request` (`held_by_request == {"RM-2026-01": 1}`, weekly and complete). Through the commands: `tests/smoke/test_caselist_remove_smoke.py::test_a_removed_path_holds_next_weeks_upload_and_the_same_removal_run_again_finishes_it`. |
| **ac2**: a revision at the removed path held in an archive in the download inbox is in the plan, and the executed removal leaves no copy of it in the inbox, by test | PASS | Three archives waiting in the inbox, each holding a revision at the removed path. Red on the start commit: `assert ['… in …-weekly-2026-10-08.zip', …] == []`, and the revisions missing from the list. Green: `test_the_executed_removal_leaves_no_copy_of_a_waiting_revision_in_the_inbox` (each archive's members equal the hand-written list), `test_each_waiting_revision_is_on_the_suppression_list_under_the_request`, `test_the_other_teams_copy_of_a_waiting_revision_stays_in_its_archive`. In the plan: `test_the_plan_lists_each_waiting_revision_as_a_later_upload_in_the_inbox` (digest, inbox snapshot and outcome for each, by hand). |
| **ac3**: `--only-named` writes no path entry, and a later upload at that path imports, by test | PASS | `test_only_named_plans_and_writes_no_path_entry` (no file on this machine, no object in the bucket), `test_after_only_named_a_later_upload_at_the_path_imports`, and through the commands `test_after_only_named_no_path_is_held_and_next_weeks_upload_is_imported`. The forbidden list's other half: `test_a_team_removal_writes_no_path_entry`, `test_a_shared_file_named_by_source_and_skipped_writes_no_path_entry`, `test_a_later_upload_the_plan_withdraws_gets_no_path_entry_of_its_own`. These cannot fail against the start commit, where nothing writes a path entry. What shows them biting is mutants 15 to 17. |
| **ac4**: a suppression list written by this build is read by the build at the start commit, and the reverse, with stored files from each | PASS | `stored_suppression_lists/` holds the takedown's records as three builds left them after the same three removals, and each older build's line schemas printed by its own code. `test_suppression_list_is_read_by_every_build.py`, 21 tests: this build's list and removal log are byte for byte each older build's, on this machine and in the bucket; every line validates against each older build's schema; what this build adds is one file in each place; each older build's list reads back to a state written out by hand, with no path held, and serialises to the same bytes. An older build's own code over this build's files: see "The compatibility finding" below. |
| **ac5**: `docs/runbooks/caselist-removal.md` replaces the manual check `v1-e30-t11` left for a caselist revision with what the path entry does, and the data-use policy's `What removal does` names the hold | **Runbook: PASS. Policy: NOT RUN**, by instruction (Deviation 1) | Step 9's `jq` check is gone. In its place: what the import says when the hold refuses an upload, and the re-run that finishes it. Steps 3, 4, 5 and 8 and the un-suppress section say what a path entry is, which removals write none, where the file is, and which build applies the hold. `uv run scripts/check_command_blocks.py --base origin/dev` → OK. The policy is unchanged. |
| Node `path-hold`: `uv run pytest packages/debate_core/tests/application -k "removal or suppress or import"` | PASS | `507 passed in 25.05s` |

### The compatibility finding

What each older build does with a suppression-list line it does not know. I gave each build's own
reader, from its tagged source, a list with one known entry and one unknown line, four ways:

| The unknown line | `0.1.0.dev60` | `v0.1.0-dev.119` |
|---|---|---|
| A known entry with one more key | refuses the whole list | refuses the whole list |
| A new `action` value | refuses the whole list | refuses the whole list |
| `schema_version` 2 | refuses the whole list | refuses the whole list |
| A line with no `sha256`, in a shape of its own | refuses the whole list | refuses the whole list |

In every case the error is `UnreadableAppendOnlyRecord`, and `caselist import` against that list
fails with it, having stored nothing. Neither build skips a line. A line's model forbids unknown
keys and pins `schema_version` to `1`, and the two builds' models are the same schema, byte for
byte. So any new kind of line in the list stops an import on both builds, which for the weekly
agent is a run that stops.

**The shape I chose.** The path entries are a second append-only record, `path-holds.jsonl`, kept
beside the list: `<data_dir>/suppression/path-holds.jsonl` on this machine and
`manifests/_suppression/path-holds.jsonl` in the bucket. The takedown's grant already covers that
prefix. Neither older build opens it. One line is a caselist slug, the digest of the caselist and
path that the plan already uses, the removed file's sha256, the date of the first snapshot that
held the file there, the time, the reason code and the request id. The model forbids any other key.

A suppression list finds the record from its own copies: each copy can name the file beside it.
So no constructor changed, and no command can hold the list without the holds.

**An older build's own code over this build's files.**
`check_an_older_build_reads_this_builds_files.py` is run by its path against an older build's
source. It carries out the removals with that source, puts this build's stored files where that
build keeps the records, the path entries included, and then reads the list, imports the next
week, publishes and asks for the status. Against each build it printed the same lines but for the
source's name:

```text
reader: the debate_core source at dev60
placed: suppression/path-holds.jsonl, suppression/removal-log.jsonl, suppression/suppression-list.jsonl, s3://<bucket>/manifests/_suppression/path-holds.jsonl, s3://<bucket>/manifests/_suppression/removal-log.jsonl, s3://<bucket>/manifests/_suppression/suppression-list.jsonl
list read: 3 whole file(s) and 2 disclosure(s) suppressed
knows of path holds: False
import of the next week: SUPPRESSED 4, completed
publish: succeeded True; status in sync: True
```

Its second check writes the path entry into the list as a line, the design not taken:

```text
reader: the debate_core source at dev60
a path entry written into the list: UnreadableAppendOnlyRecord at line 8
the whole list is refused, and an import against it fails with nothing stored
```

**Two read-only checks against the real buckets**, with the everyday profiles, 2026-10-12:

- `aws s3api head-object` on `manifests/_suppression/path-holds.jsonl` → `404 Not Found` in dev and
  in prod. This build reads that key on every import, and a read the bucket refused would stop the
  import. A 404 is "no path is held". Prod's suppression list itself is also a 404: prod has never
  had a removal, so the agent already reads a missing key there every week.
- The dev bucket's own suppression list, 1,239 bytes, last written 2026-10-01: this build read all
  5 lines, 3 whole files and 2 disclosures, and each line serialised back to itself. I downloaded
  it to the scratch directory, printed those counts, and deleted it.

### Mutation runs

Each run applied one textual change to committed source, ran 303 to 305 tests (the six new test
files and eleven existing ones on removal, the list, the commands and the smoke check) with
`-n auto --no-cov -p no:randomly`, and restored the file from a byte copy, checking the sha256 and
`git diff --quiet`. The driver refuses a mutant whose target text is not there exactly once. Each
run set `HYPOTHESIS_STORAGE_DIRECTORY` to a new directory made with `mkdtemp` and checked empty
(working agreement 8). None of these tests is a Hypothesis property. Each run took 20 to 36 s,
three or four to a command. Every catch is a failing test and none errored at collection. Rows 1 to
17 ran on `ab7ed84`, 18 to 22 and 25 to 41 on `0a00a9c`, 23 and 24 on `786877f`, 42 on `3b94313`.

The four kinds the brief named:

| # | Mutation | Result | What caught it (first of the failing tests) |
|---|---|---|---|
| 1 | **Path match, another caselist.** A hold is matched under its own caselist, whatever caselist the upload is in | CAUGHT, 2 failed | `test_the_same_spelling_of_the_path_in_another_caselist_is_not_held` |
| 2 | **Path match, another path.** A hold stops every path of its caselist | CAUGHT, 15 failed | `test_an_upload_at_another_path_the_same_week_is_stored` and 14 more |
| 3 | **Path match, the same sha256.** Only the removed file's own bytes are held at the path | CAUGHT, 11 failed | `test_a_new_upload_at_the_removed_path_in_a_later_weekly_is_refused` |
| 4 | **Path match, the same sha256.** A held upload's bytes are refused at every other path too | CAUGHT, 1 failed | `test_the_same_bytes_at_another_teams_path_are_stored_and_only_the_held_path_is_refused` |
| 5 | The date: every snapshot is held, an earlier version's included | CAUGHT, 2 failed | `test_an_archive_dated_before_the_removed_file_first_appeared_imports_as_it_did` |
| 6 | The date: a snapshot of the same date is held | CAUGHT, 1 failed | `test_a_snapshot_of_the_same_date_or_earlier_is_not_held` |
| 7 | **The importer's check.** Classification ignores the hold | CAUGHT, 11 failed | `test_a_new_upload_at_the_removed_path_in_a_later_weekly_is_refused` |
| 8 | **The importer's check.** The check at the write ignores the hold | CAUGHT, 1 failed | `test_if_classification_ever_let_a_held_upload_through_the_write_would_refuse_it` |
| 9 | **The importer's check.** Neither asks the hold | CAUGHT, 10 failed | the ac1 tests |
| 10 | A complete archive's import passes no snapshot date | CAUGHT, 2 failed | `test_a_new_upload_at_the_removed_path_in_a_later_complete_archive_is_refused` |
| 11 | A weekly import passes no snapshot date | CAUGHT, 9 failed | the ac1 tests |
| 15 | **`--only-named`** writes path entries | CAUGHT, 3 failed | `test_only_named_plans_and_writes_no_path_entry`; `test_after_only_named_a_later_upload_at_the_path_imports`; the smoke check |
| 16 | `--team` writes path entries | CAUGHT, 2 failed | `test_a_team_removal_writes_no_path_entry` |
| 17 | A file the plan skips or withdraws gets a path entry | CAUGHT, 3 failed | `test_a_shared_file_named_by_source_and_skipped_writes_no_path_entry` |
| 23 | **The inbox sweep.** The inbox's archives are not read as snapshots | CAUGHT, 8 failed | `test_the_executed_removal_leaves_no_copy_of_a_waiting_revision_in_the_inbox` |
| 24 | A complete archive in the inbox is read as a weekly of its date | CAUGHT, 1 failed | `test_the_plan_lists_each_waiting_revision_as_a_later_upload_in_the_inbox` |
| 25 | An inbox member is reported as a stored row | CAUGHT, 4 failed | the same test |
| 26 | A re-run does not use the recorded path | CAUGHT, 4 failed | `test_an_upload_an_older_build_imported_is_found_in_the_store_by_running_the_removal_again` |
| 27 | The recorded path stands in at a date after everything | CAUGHT, 4 failed | the same test |
| 28 | A stored snapshot is listed among the inbox's | CAUGHT, 1 failed | `test_the_plan_lists_each_waiting_revision_as_a_later_upload_in_the_inbox` |
| 29 | An inbox snapshot is listed among the store's | CAUGHT, 4 failed | the same test |
| 42 | A member the importer would skip is read as held at its path | **SURVIVED, then CAUGHT** after a test was added | `test_a_member_the_importer_would_skip_is_not_a_later_upload` |

The rest, one per rule the task adds:

| # | Mutation | Result | What caught it |
|---|---|---|---|
| 12 | A file the list stops by its bytes is counted as held too | CAUGHT, 1 failed | `test_a_file_the_list_stops_by_its_bytes_is_not_counted_as_held` |
| 13 | The weekly import's report drops the count by request | CAUGHT, 4 failed | `test_the_import_counts_the_refused_upload_under_the_removals_request` |
| 14 | The complete archive's report drops it | CAUGHT, 1 failed | the same test |
| 18 | A path already held is given a second entry on a re-run | **SURVIVED, then CAUGHT** after a test was added | `test_a_path_a_stopped_run_already_recorded_is_not_recorded_again` |
| 19 | The hold is dated by the latest snapshot holding the file | CAUGHT, 10 failed | `test_include_shared_removes_it_for_both_teams_and_holds_both_of_its_paths` and nine more |
| 20 | The hold's date ignores the disclosure records | CAUGHT, 1 failed | `test_the_hold_is_dated_by_the_first_snapshot_that_held_the_file_whatever_recorded_it` |
| 21 | The executor does not append the path entries | CAUGHT, 18 failed | the ac1 tests |
| 22 | The plan's list-as-it-will-read leaves out the new entries | CAUGHT, 1 failed | `test_the_plan_carries_one_path_entry_for_the_one_path_the_file_is_removed_from` |
| 30 | An un-suppress does not lift a hold | CAUGHT, 6 failed | `test_unsuppressing_the_removed_file_releases_its_path`, and two of `v1-e30-t07`'s |
| 31 | An un-suppress at the same instant does not lift it | CAUGHT, 3 failed | `test_an_unsuppress_at_the_same_instant_lifts_the_hold_as_it_lifts_the_suppression` |
| 32 | An un-suppress lifts a hold recorded after it | CAUGHT, 1 failed | `test_a_hold_recorded_after_an_unsuppress_is_in_force_because_the_file_was_removed_again` |
| 33 | The list reads no path entries | CAUGHT, 19 failed | the ac1 tests |
| 34 | Reading the list's state leaves out the path entries | CAUGHT, 14 failed | the ac1 tests |
| 35 | The pull's list does not fall back for the path entries | CAUGHT, 2 failed | `test_the_pulls_importer_refuses_it_from_this_machines_copy_when_the_bucket_needs_a_login` |
| 36 | The bucket's record is read with the writing credential | CAUGHT, 2 failed | `test_the_bucket_copy_is_read_and_written_with_the_credentials_the_list_is`, and one of `v1-e30-t07`'s |
| 37 | Un-suppress reports no released path | CAUGHT, 2 failed | `test_unsuppressing_the_removed_file_releases_its_path` |
| 38 | The plan's JSON leaves out the path entries | CAUGHT, 2 failed | `test_the_json_carries_the_path_entries_as_written_and_names_no_one` |
| 39 | The plan's JSON leaves out the inbox snapshots | CAUGHT, 2 failed | `test_the_json_gives_the_inbox_snapshots_of_each_later_upload` |
| 40 | A later upload's line names its path where it says it is in the inbox | CAUGHT, 1 failed | `test_a_later_upload_only_the_inbox_holds_is_listed_as_in_the_inbox_and_not_in_the_store` |
| 41 | The import's JSON leaves out the held count | CAUGHT, 2 failed | `test_the_import_summary_counts_held_uploads_by_request` |

Two survivors:

- **Mutant 18 found a defect.** No test had a path already recorded when a removal was planned, so
  the check that stops a second entry was never exercised. Writing that test showed something
  worse. A run that stops after the suppress step can leave the path entry on this machine and not
  in the bucket. The run that finishes it plans no new entry, and it appended nothing, so the
  bucket's copy stayed without it. A finishing run now gives each copy what the other holds, as the
  list's own append does (`0a00a9c`).
- **Mutant 42 found a missing test.** No archive in the fixtures held, at the removed path, a
  member the importer skips. A symbolic link named as the removed file is one. The test now has it.

Mutant 24 was first run as "a complete archive in the inbox is not read" and caught, 3 failed. I
then simplified that branch, and the row above is the mutant of the code as it is.

### Checks CI runs

On `3b94313`. `v1-e01-t27` merged during the session, so the suite is run in parts with its
`--part` option and without coverage, as CI now runs it.

| Command | Result |
|---|---|
| `uv run --frozen pytest -n auto -m "not slow and not live" --part 1/3` | `1962 passed in 50.38s` |
| The same, `--part 2/3` | `1983 passed, 1 skipped in 45.49s`. The skip is the parser eval waiting on human corrections |
| The same, `--part 3/3` | `1986 passed, 1 warning in 44.22s`. The warning is `pytest_socket`'s, from the smoke harness test that tries the network on purpose |
| `uv run --frozen pyright` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen ruff check .` / `ruff format --check .` | `All checks passed!` / `634 files already formatted` |
| `uv run --frozen lint-imports` | `Contracts: 12 kept, 0 broken.` |
| `uv run scripts/check_thin_handlers.py` | `OK: 21 CLI command and API route handlers within 25 statements` |
| `uv run scripts/docs_index.py --check-descriptions` | `All 34 indexed documents under docs/ have a description` |
| `uv run scripts/validate_specs.py` | `OK: 347 files, 38 epics, 289 tasks, 20 releases` |

5,931 passed and 1 skipped in all. The first whole run after the sync was three commands of 35, 42
and 41 s. The last one, above, I chained into one command, which took 143 s. That is over the
two-minute line and I should have kept them apart.

Coverage of the changed modules under the caselist, command and smoke tests, with branches:
`ports/suppression.py`, `pipeline.py` and `removal_path_versions.py` 100%, `import_service.py`
98%, `removal_plan.py` 97%, `removal_service.py` and `inbox_purge.py` 96%, `caselist_remove.py`
94%, `caselist/suppression.py` 93%, `local/suppression_list.py` 92%. I read the uncovered lines.
None is a line this task wrote except three refusals I then covered or removed.

## Files changed

- **`debate_core.application`**
  - `ports/suppression.py`: `PathHoldEntry`, one line of the record. `SuppressionState` holds the
    path holds in force and answers `path_hold(caselist, path, snapshot)`. `PathHoldList` and
    `KeepsRecordsBesideIt`, the two protocols. The suppression entry and the removal log entry are
    unchanged.
  - `caselist/suppression.py`: `RecordedSuppressionList` finds the path-hold record beside each of
    its copies and reads and appends it by the list's own set-union rule.
    `LocalFallbackSuppressionList` reads this machine's copy alone when the bucket needs a login.
    `load_suppression_state` reads both, and every reader of the list calls it.
  - `caselist/pipeline.py`, `import_service.py`: the importer asks the hold with the snapshot's
    date, which a caller now has to pass. A held member is `SUPPRESSED` and is counted by request
    (`held_by_request`). The check is made again at the write.
  - `caselist/removal_plan.py`: the plan's path entries, the inbox's archives as holdings, and the
    recorded path standing in for a removed file on a re-run. `RemovalPlan.path_holds`.
  - `caselist/removal_path_versions.py`: a holding can be an inbox member, and a version says
    which snapshots only the inbox shows it in.
  - `caselist/inbox_purge.py`: `read_inbox` reads and hashes the inbox once, for the plan's two uses
    of it. What is deleted or rewritten is decided as before.
  - `caselist/removal_service.py`: the executor appends the path entries with the suppression
    entries. An un-suppress plan counts the paths it releases.
  - `caselist/openev_import_service.py`: passes no snapshot date. A camp path's hold is the pull's.
- **`debate_core.integrations.local`**: `suppression_list.py`, the local file beside the list.
- **`debate_cli.commands`**: `caselist_remove.py` prints the path entries or why there are none,
  marks a later upload that is in the inbox, and says how many paths an un-suppress releases.
  `caselist.py` reports the uploads a hold refused, by request.
- **Tests**
  - `packages/debate_core/tests/application/caselist/`: `test_removed_path_holds_later_imports.py`
    (8) and `test_removal_covers_inbox_revisions.py` (6), which check the store and the inbox and
    use only what existed before; `test_removal_path_hold_plan.py` (30);
    `test_suppression_path_holds.py` (21); `test_suppression_list_is_read_by_every_build.py` (21)
    with `stored_suppression_lists/`, `suppression_list_scenario.py` and the two scripts that are
    run by path.
  - `packages/debate_cli/tests/commands/test_caselist_path_hold_output.py` (14).
  - `tests/smoke/test_caselist_remove_smoke.py`: two checks through the commands, and its row in
    `tests/smoke/README.md`.
  - `tests/fixtures/caselist/build_held_path_archives.py` (new).
- **Docs**: `docs/runbooks/caselist-removal.md`.

## Deviations from the spec

1. **ac5's policy clause is not done, by instruction.** The brief says the policy is the PM's to
   change, at version 1.8 in the next close-out, and to change only the runbook. So ac5 is half
   met, the phase stays `InProgress`, and the sentence I propose is Follow-up work 1.
2. **The import records the refused upload by count and request, not by a line in the list.** ac1
   says the import is "recorded as suppressed under the removal's request". What the import does:
   it counts the upload as `SUPPRESSED`, as it counts any member the list stops, and counts it under
   the request id in its report, its `--json` (`held_at_removed_paths`) and the line under its
   table. It appends nothing. The upload's own sha256 goes on the list, under the same request,
   when the same removal is run again: the plan finds it in the inbox archive.

   The alternative is for the import to append an entry itself. I did not, for three reasons. Only
   `caselist remove` and `caselist unsuppress` write the takedown's records, and they write the
   bucket's copy with the takedown credential. The weekly agent imports with the everyday profile,
   often with an expired session, and an append has to read the bucket's copy first, so it would
   fail the import stage. And an entry appended to this machine's copy alone is the disagreement
   between copies that `v1-e34-t07` ruled out. If you want the entry at import, it needs a ruling
   on who may write the list.
3. **Two hand-written expectations of `v1-e30-t11`'s gained one key.** Each later upload in the
   plan's JSON now carries `inbox_snapshots`. The two tests that write a later upload's JSON out in
   full, one in the command tests and one smoke check, have the new key added, empty. Nothing else
   in them changed.
4. **`tests/fixtures/caselist/` is outside `constraints.packages`**, as it was for `v1-e30-t11`
   (its Deviation 4, accepted). The fixture is used from two packages' tests.

## Decisions and assumptions

1. **A hold has a date.** It covers uploads in snapshots dated after the earliest snapshot that
   held the removed file at the path, which is `v1-e30-t11`'s meaning of "later". An archive dated
   on or before it holds an earlier version, which a request does not cover, and importing it again
   leaves its manifest byte for byte as it was. Without the date, re-importing an old week would
   drop the earlier version's row. Alternative: hold every sha256 at the path whatever the date.
2. **A hold follows the file it came from.** An un-suppress of the removed file, recorded at or
   after the hold, lifts it. Nothing is appended to release one, as `v1-e34-t14`'s hold is released
   by `unsuppress`. A later upload that a removal put on the list itself stays suppressed until it
   is un-suppressed by its own sha256.
3. **`--team` writes no path entry.** The spec gives the entry to "a whole-file removal by
   `--source`". A team's later files are at new paths as often as old ones, so a path would not
   hold them. Follow-up 4.
4. **`--source --include-shared` holds every path of the file**, the other team's included. It is
   a whole-file removal, and `v1-e30-t11` already takes down later uploads at the other holders'
   paths in that case.
5. **A path is anywhere the named file is held**: a manifest row, a disclosure record, or a copy
   waiting in an inbox archive at another path.
6. **A waiting revision another path also holds is withdrawn, not removed.** The inbox's archives
   are read as holdings, so a revision two teams uploaded in one archive is taken from the removed
   path only, and the other team's copy stays in the rewritten archive. The same goes for a later
   upload in the store that a waiting archive holds at another path. I chose to keep the other
   holder's copy: the other choice suppresses a file a second team disclosed.
7. **Running the same removal again finds what arrived since.** After a removal, no manifest row
   says where the removed file was, which is why `v1-e30-t11` could not find a later revision by
   `--source`. The path entry says it. For each hold of a file the selector names, whatever is at
   the held path stands in for the removed file there, dated by the hold. This closes that gap for
   an upload this build refused and for one an older build imported.
8. **The record is found beside each copy of the list.** I first meant to pass it to each service.
   That would have changed the constructor of every importer and the removal service, and a
   composition root could have left it off. A copy naming its neighbour needs neither.
9. **The older builds read the list and apply no hold.** That is the cost of the shape. A build
   from before this task imports a new upload at a held path, as it did before there was a hold.
   The agent runs `0.1.0.dev60` today and `v0.1.0-dev.119` after Wednesday. The runbook says to
   run the same removal again after each pull until the agent is updated (Follow-up 6).
10. **Only the importer and the removal plan ask the hold.** The publisher, `caselist status` and
    the parser check the list by bytes and by withdrawn disclosure, as before. A row an older build
    imported at a held path is found by the re-run, not by them (Follow-up 5).
11. **The removal log is unchanged.** Its line forbids unknown keys too, and older builds read it.
    A later upload the re-run covers is in `removed_sha256` like any other. The log does not say
    which paths are held; the record beside the list does.
12. **A member the importer would skip is not a later upload.** A symbolic link or junk named as
    the removed file is never stored, so the plan does not put its digest on the list.
13. **The fixture's archives are dated within a week of the store's newest.** The domain refuses a
    snapshot date in the future, and the dates have to stay valid on any day the tests run.
14. **The installed build was not opened.** Its version names tag `v0.1.0-dev.60`, and the report
    of `v1-e34-t10` records the commit it prints, `ec7b95e`, which is that tag's.
15. **I read the two buckets, read-only.** A `head-object` in each for the new key, and one
    download of the dev list to the scratch directory, deleted after its lines were counted. I
    did not touch the installed agent, the launchd job, the AWS config or the data directory.
16. **Coordination.** I did not edit `caselist_sync.py`, `sync_runs.py`, doctor, `ops/launchd`,
    `.github/workflows` or `pyproject.toml`. The pull's list is `LocalFallbackSuppressionList`,
    which is in `caselist/suppression.py`, so the pull applies the hold without a change to the
    sync.

## Operator follow-ups

None. No command here needs a credential that changes anything, and nothing was run against the
real data directory.

## Follow-up work

1. **The policy sentence** (the PM's; `docs/policies/caselist-data-use.md`, "What removal does",
   version 1.8). In the bullet *Covers later uploads at the removed path*, replace its last
   sentence, which says a caselist revision not yet imported is not yet held, with:

   > A caselist file removed whole by its sha256 also has its path held: a new upload at that path
   > is refused when it is imported, and one already downloaded and waiting is taken out with the
   > removal. Removing a team's disclosures holds no path, so the same removal is run again after
   > the next import. A request that is about one version holds nothing.

   The third bullet from the end, on the suppression list, could add: "A removed caselist path is
   recorded beside the list in the same way."
2. **A pull does not say that a hold refused an upload** (E34, `v1-e34-t22`'s area). The import
   report carries the count by request, and `caselist import` prints it. The pull's run record and
   its notification do not, and I was asked not to edit them. Until they do, the operator learns of
   a held upload by running the removal's dry run after a pull.
3. **`caselist status` does not report an upload held in the inbox, or a row at a held path** (E30).
   Either would tell the operator a re-run is owed without their asking.
4. **A `--team` removal holds nothing** (E30; a ruling first). A new file of the team's is imported
   until the same `--team` removal is run again. Holding it needs a hold on a team's directories,
   which is a different record from a path's.
5. **The publisher does not refuse a manifest row at a held path** (E30). It matters only where an
   older build imported one. The re-run removes it.
6. **The weekly agent should run a build with this task** (the operator's; E34). Until then the
   hold is applied only by imports run by hand with a newer build.
7. **An imported archive that holds a refused upload stays in the inbox until the removal is run
   again or retention deletes it** (E30). The upload is not in the store or the bucket.
8. **A skipped member named as the removed file stays in its inbox archive** (E30). Nothing imports
   it, and the junk rule takes out only junk beside a suppressed file. Retention deletes the
   archive.
9. **`ports/suppression.py` and one runbook line still call a weekly archive cumulative**
   (`v1-e30-t17` owns that wording). I left them.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-13

**Notes:**

Accepted in full. I have written ac5's policy clause in this branch as data-use policy 1.8, from
your proposed sentence plus one more: until the agent runs a build that applies the hold, the
removal is run again after each pull. With that in, the phase is `Succeeded`. 1.8 tightens the
policy, so it takes effect when this merges.

**The compatibility finding is the review.** You gave each older build's own reader four kinds of
unknown line, and each build refused the whole list each time. That means any new line in the
list would have stopped the weekly agent's import. A record beside the list, which older builds
never open, is therefore the only safe shape. This build's list and removal log are byte for byte
what the older builds wrote. Running an older build's code over this build's files shows it reads
the list, imports, publishes and reports in sync.

**The work itself:**

* **The date on a hold (Decision 1)** keeps a re-import of an old week from dropping an earlier
  version's row. That is the subtle case.
* **Recording the hold beside each copy of the list (Decision 8)** means no composition root can
  build the list without its holds.
* **Running the same removal again now finds later revisions (Decision 7).** That closes the gap
  `v1-e30-t11` could not reach.
* **Mutant 18 found a real defect.** A run stopped after the suppress step left the path entry on
  one copy and not the other. The fix gives each copy what the other holds, as the list itself
  does.

**Rulings:**

* **Deviation 2, the import counts a refused upload and appends nothing:** accepted. Only the
  takedown writes the takedown's records, with its credential. An append from the weekly import
  would fail on an expired session, and an append to one copy only would split the copies, which
  is what `v1-e34-t07` ruled out.
* **Deviations 1, 3 and 4:** accepted. Deviation 1 is closed by policy 1.8.
* **Decisions 1 to 16:** accepted.
* **Your follow-up 4, a team removal holding nothing:** no team hold in V1. A team's new files land
  at new paths as often as old ones. Running the removal again after the next import, as the
  runbook says, is the procedure. No task.
* **Decision 15, the reads against both buckets:** accepted for what they showed. Prod's missing
  key reads as "no hold", which is evidence worth having. But this is the second session to make
  credentialed calls itself. From now on, a call that uses the operator's AWS profiles goes to the
  operator as a command, however read-only it is. That will be in future briefs.
* **The 143 s chained run:** noted, as you did.

**Follow-up work, filed by the PM in the next spec batch:**

* **Your 2, the pull not reporting a held upload:** added to `v1-e34-t23`. The run's details can
  carry the count by request.
* **One E30 p3 task, "held-path loose ends", for your 3, 5, 7 and 8:**
  * `caselist status` reporting an upload held in the inbox, or a row at a held path;
  * the publisher refusing a row at a held path;
  * an imported archive holding a refused upload;
  * a skipped member named as the removed file.
* **Your 6:** the agent gets the hold with the build after the combined `v1-e31-t11` and
  `v1-e31-t12` re-parse. It is installed `v0.1.0-dev.122` tomorrow, which predates this task. Dev
  has had one removal (the RM-2026-90 exercise) and prod none, so nothing is exposed meanwhile.
* **Your 9:** `v1-e30-t17` owns it.
