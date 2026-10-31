# Session report: v1-e40-t08-parse-owed

| | |
|---|---|
| Task | `v1-e40-t08-parse-owed` — A week a killed run published is parsed by the next run, not left for the next import |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t08-parse-owed.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t08-parse-owed.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t08-parse-owed` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

A publish now records a parse owed, per caselist and snapshot, in a new state file,
`caselist-sync-parse-owed.json`. It sits in the data directory, and in bucket mode it is also saved
to `reports/sync/state/` each time it is written. An entry clears only when that caselist's parsed
store is published complete. A run that starts with entries owed parses and publishes those
caselists first, even when it imports nothing. A parser version the store has no directory of owes a
full parse of every caselist the run follows, `openev` included, before the index stage.
`caselist runs` (local, and `--remote` from the bucket) and `caselist status` say what is owed. A
removal clears the entry of each snapshot it reaches. The cloud cure no longer says "that imports
into", and a stage over its failure rate that published its store names no cure. All three criteria
pass by test. The ac1 and ac3 tests use v1-e40-t04's kill harness, and every one was red first. The
kill harness now requires that nothing is left late, at all 21 kill points.

**Please look at these first:**

1. **Compatibility.** The entries are a new file, not a key of the pending-work file. An older build
   rewrites the pending-work file with the one key it knows, so a new key there would be dropped
   the next Wednesday. dev.164 and dev.200, each run with its own code, restore the five state files
   they know and never the sixth. They read every file this build writes (`caselist runs --remote`
   included), and their save leaves the parse-owed object byte for byte as it was. See
   [Every build reads this build's files](#every-build-reads-this-builds-files).
2. **The full parse after a bump fits one cloud run, by estimate.** It is about 40 minutes on the Mac,
   and 40 minutes to 2 hours on the task if the task is one to three times slower. The deadline is 6
   hours. See [The full parse's time cost](#the-full-parses-time-cost).
3. **Deviations 1 and 2.** The local-mode and newer-table hints still say "imports into", which I
   left alone because you asked me to keep hint changes to the cure lines the spec names. I also
   added no smoke check.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `parse-owed` — Parse owed | Done | Order of work: red tests (12 new, plus the kill harness tightened), the record, the publish and parse stages, the bump check, the removal, `runs` and `status`, the cure lines, runbooks, a cross-build read, then 12 mutants, two of which prompted new tests |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — a run killed after its publish and before its parse leaves a parse-owed entry, and the next run parses that snapshot first though it imports nothing, in local and bucket mode; a completed parse clears it; red first, with v1-e40-t04's kill harness | PASS | `test_parse_owed.py`: in local mode, `test_a_local_run_killed_after_its_publish_owes_the_parse_and_the_next_run_parses_it`. In bucket mode, `test_a_bucket_mode_run_killed_after_its_publish_owes_the_parse_in_the_bucket_and_the_next_run_parses_it` (the bucket then equals an uninterrupted week's, key by key and ETag by ETag). The owed caselists come first: `test_owed_caselists_are_parsed_before_the_ones_the_run_imports_into`. `test_bucket_mode_kills.py`: `the_next_run_finishes_the_week` now asserts that nothing is late and that no by-hand catch-up is needed, at 8 stage kills, 7 write kills, the end and 5 SIGTERMs. Red runs below |
| ac2 — `caselist runs` and `caselist status` say a parse is owed, and a removal that reaches the snapshot clears the entry, by test | PASS | `test_caselist_runs_and_caselist_status_say_a_parse_is_owed` (`--json` `parses_owed` and the caption's sentence), `test_caselist_runs_remote_says_what_the_cloud_run_owes` (the bucket's copy), `test_nothing_owed_is_said_as_nothing`, `test_a_removal_that_reaches_a_snapshot_clears_its_entry_and_no_other` (the camp release's entry stays), `test_a_bucket_mode_removal_clears_the_entry_in_the_bucket`; and in `test_parse_owed_record.py`, `test_a_removal_clears_the_snapshots_it_reached_and_nothing_else` |
| ac3 — a parse stage whose parsed-store publish fails leaves the entry, and the next run parses and publishes that snapshot though it imports nothing; the cloud cure's hint no longer says "that imports into"; red first | PASS | `test_a_parse_whose_publish_failed_stays_owed_and_the_next_run_publishes_it_though_it_imports_nothing[raised]` and `[reported]`: a publish that raises `STORE_UNAVAILABLE`, and one that reports `CHECKSUM_MISMATCH`. Each asserts the hint and the banner's fix line, hand-written, with no "that imports into". The core tests and the runbook test in `test_caselist_sync_names_the_cloud_cure_in_bucket_mode.py` hold the new wording |
| Node `parse-owed`: `uv run pytest packages/debate_cli/tests/bucket_mode` | PASS | `152 passed in 78.88s`, run as written under a process-group hard stop of 118 s |
| PM amendment of 2026-11-01: a stage over its failure rate that published names no cure | PASS | `test_a_bucket_mode_parse_stage_over_its_failure_rate_points_at_the_cloud_runs_failures` now asserts the fix line `none owed: the parsed store was published (caselist-cloud-run.md, "A parse stage over its failure rate")`, red first (below) |
| PM amendment of 2026-10-27: a parser version the store has no directory of owes a full parse of every caselist followed, `openev` included, before the index stage | PASS | `test_a_parser_version_the_store_has_no_directory_of_owes_a_full_parse_of_every_caselist_followed`: a week with nothing new on a relabelled parser version parses `testcl26` and `openev` in full, publishes both, and builds the index from them. Before the change the index stage failed. `test_a_full_parse_cut_short_is_still_owed_by_the_next_run`: the first run is killed after part of the new version is in the bucket, and the next run finishes it |
| Forbidden: a school, team code or path in the state files | PASS | `test_the_parse_owed_file_holds_caselist_slugs_snapshot_names_and_a_parser_version_alone` compares the whole file with a hand-written body. The writer refuses a path, a team code or a non-version before it writes anything, and the reader refuses an extra key (`test_parse_owed_record.py`, 17 tests). Mutants 5a and 5b |
| Forbidden: network or AWS access in any test | PASS | moto and respx under `tmp_path`, as in the rest of `bucket_mode/`. The cross-build read used a local directory as the bucket. Nothing was fetched |

### The red runs

Every new test was first run against the code at `e50599b`, before any change. The tests name the
new file and its JSON keys as literals and import nothing new, so collection succeeded and every
failure is an assertion or a missing file or key. The commands were run under the process-group
hard stop with `-p no:randomly --tb=no -rf`:

```text
test_parse_owed.py: 12 failed in 18.00s   (every test; e.g. owed file None, NoSuchKey for the
                                           bucket's state key, KeyError 'parses_owed')
test_bucket_mode_kills.py: 3 failed, 18 passed in 34.47s
  FAILED ...[parse]                    (killed at the parse stage)
  FAILED ...nth_bucket_write...[16]    (killed among the parsed store's writes)
  FAILED ...sigterm...[parse]          (SIGTERM at the parse stage)
test_caselist_sync_bucket_mode_hints_point_at_the_cloud.py -k failure_rate: 1 failed, 2 passed
  assert "the next cloud run publishes the parsed store of a caselist the parse stage names: ..."
      == 'none owed: the parsed store was published (caselist-cloud-run.md, "A parse stage over its failure rate")'
```

The failure-rate test was red against the code with the cure's wording already changed and the
banner's rule not yet changed, which is why its output shows the new wording.

### Every build reads this build's files

dev.164 is `v1.1.0-dev.164` (`03b23e2`), the cloud image. dev.200 is `v1.1.0-dev.200` (`761b571`),
the Mac's build. Both tags were in this clone. Each build's `packages/debate_core/src` was exported
with `git archive v1.1.0-dev.<n> packages/debate_core/src | tar -x -C $S/build-<n>`, and nothing was
fetched. This build wrote the files with a throwaway test that was not committed. It ran a
bucket-mode week whose parsed-store publish failed, then copied every object under
`reports/sync/state/`, `reports/sync-runs/` and `reports/sync-run-details/` into scratch. A scratch
script (`read_with_an_older_build.py`), run with each build first on `sys.path`, then used that
build's own code on the copy. It restored the state files as a bucket-mode run does
(`RunState._restore_state_files` over `FsEvidenceObjectStore`), read each file with that build's
reader, read the runs as `caselist runs --remote` does, and then saved the state files as that
build's run would. Identical for both builds:

```text
this build's STATE_FILES: 5 ['caselist-sync-runs.jsonl', 'caselist-sync-run-details.jsonl', 'caselist-sync-download-starts.json', 'caselist-sync-openev-deliveries.json', 'caselist-sync-pending.json']
restored: [the same five]
parse-owed file restored into the data directory: False
pending-work: ()
download ledger starts: 1
openev deliveries: 1
run log: [('20261014T110005Z', 'completed'), ('20261021T110005Z', 'incomplete')]
details 20261021T110005Z parse: ('STORE_UNAVAILABLE',) hint: The cloud run publishes the parsed store of testcl26, never the operator's Mac, whose work…
remote runs: [('20261021T110005Z', True), ('20261014T110005Z', True)]
after this build's save, parse-owed object unchanged: True
```

Neither build refuses anything or loses anything. This task changes no record or details model,
and the stored-schema tests (`details_schema_before_parsed_stores_owed.json` and the others) pass
unchanged. After an older build runs, the bucket's parse-owed file can be stale, because it never
clears it. The next run of this build then parses that caselist, finds nothing to parse, publishes
nothing it lacks, and clears the file. That costs one aggregate rebuild and loses nothing.

### The full parse's time cost

No cloud run has done a full parse, so the estimate comes from the Mac's figures. The 2026-10-11
full parse under `2026.10.10-docx-2` took 1,465 s for 11,126 sources, counting parse, rebuild and
publish ([caselist-parse-report.md](../data/caselist-parse-report.md)). On 2026-10-30 hspolicy26
took 981 s for 4,342 sources. That is 1.63 times its 2,657 sources and 1.61 times its 611 s, so time
grows with sources. If every caselist grew the same way, a full parse is about 2,400 s, roughly 40
minutes, on the Mac. The task's 8 vCPU have not been measured against the Mac; at one to three times
slower, the parse takes 40 minutes to 2 hours. To that add the restore (499 s for 15,342 parsed
objects in `v1-e40-t06`'s comparison), the raw sources the parse fetches from `raw/`, and the index
build. The total is well inside the 6-hour deadline. A run that records itself, a stopped run
included, counts toward the late-run alarm's seven days, so the alarm is not near.

**If one run cannot finish it**, the owed entries split the work across runs:

* Each caselist's full parse is written down before it starts.
* It is published as soon as its parse ends, and only then cleared.
* A run stopped by the deadline, or by hand, leaves every caselist it did not publish owed, and the
  next run parses those first.
* In bucket mode, a caselist whose parse was cut short starts over, because its working copy left
  with the task.
* The old index stays current until a run parses everything owed without a failure.

The largest caselist takes about 16 minutes on the Mac, so no single caselist comes near the
deadline. `caselist-cloud-run.md` gains "A new image with a new parser version", which says all of
this.

### Mutants

Each mutant was applied to the committed source by `$S/mutants.py`, run against the test files that
cover it under the process-group hard stop with a new empty `HYPOTHESIS_STORAGE_DIRECTORY`, and then
restored with `git checkout HEAD --`. 12 mutants, all caught. "Caught" means a named test failed on
an assertion. The file-shape test failed on its own assertion under 5a and 5b.

| Mutant | Caught by |
|---|---|
| (1) The entry cleared at the parse, not at the publish | `..._publish_failed_stays_owed...[raised]`, `test_a_full_parse_cut_short_is_still_owed_by_the_next_run`, kill at write 20 |
| (2) Entries owed, nothing imported: nothing parsed | 9 tests: both ac1 tests, the order test, ac3, the kill harness at `parse` |
| (3) A removal leaving the entry | both removal tests |
| (4) The parser-version check missing `openev` (`plan.caselists` for `search_index_stores`) | both bump tests |
| (5a) The entry written with the manifest's path beside it | the file-shape test, 3 record tests and 11 more |
| (5b) The writer's check removed and the manifest's path written as the snapshot | the file-shape test, the record's refusal tests and 14 more |
| (6) The publish owes nothing | 12 tests |
| (7) Cleared even though the bucket did not confirm every object of the parsed store | It **survived** at first: every test failed the publish by raising. `[reported]` was added to ac3 (`62312fd`) and catches it |
| (8) A full parse not written down before it starts | `test_a_full_parse_cut_short_is_still_owed_by_the_next_run` |
| (9) A removal clearing its caselists whole | `test_a_removal_clears_the_snapshots_it_reached_and_nothing_else` |
| (10) The banner's nothing-owed check removed | the failure-rate test |
| (11) Owed caselists the run does not follow parsed all the same | It **survived** at first. `test_a_parse_owed_for_a_caselist_the_run_does_not_follow_is_left_owed_and_said` was added (`1911b1a`) and catches it |

### What was run, and what was left to CI

`uv run --frozen python scripts/affected_tests.py` chose **296 of 587 test files (50.4%)** from 22
changed files in 15.5 s. Most of that comes from `caselist_sync.py` and `container.py`. That is well
past two minutes, so under working agreement 10 the full affected set is left to the pull request's
`ci` check and not handed to the operator. Within two minutes, each under the process-group hard
stop, with no leftover worker after any run:

| Run | Result |
|---|---|
| The always-run list: `tests/architecture`, `tests/specs`, `test_app.py`, `test_help_rendering.py`, `test_container_factories.py` | `369 passed in 17.56s` |
| `packages/debate_cli/tests/bucket_mode` (the node criterion) | `152 passed in 78.88s` |
| `packages/debate_core/tests/application/caselist` (95 files) | `1699 passed in 67.10s` |
| `test_caselist_sync*`, `test_caselist_parse*`, `test_sync_runs*`, `test_search_index_stage*`, `test_restored_copy_marker` under `packages/debate_core/tests/application` | `318 passed in 6.64s` |
| CLI: `commands/test_caselist_runs*`, `test_caselist_status*`, `test_caselist_remove*`, `test_caselist_pull*`, `test_doctor`, `test_installation`, `test_output`, `test_recorded_failure_codes` | `356 passed in 22.12s` |
| Tests that read the edited runbooks: `test_runbook_reinstall_runs_the_profile_check`, `test_caselist_pull_names_no_path`, `tests/smoke/test_caselist_pull_in_process.py`, `tests/docs`, `tests/scripts/test_caselist_run_image_plan_check.py` | `240 passed in 30.66s` |
| `uv run --frozen ruff format --check .` / `ruff check .` | `1642 files already formatted` / `All checks passed!` |
| `.venv/bin/pyright packages/debate_core packages/debate_cli` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` / `scripts/check_thin_handlers.py` | `Contracts: 19 kept, 0 broken.` / `OK: 68 CLI command and API route handlers within 25 statements` |
| `uv run scripts/validate_specs.py` | `OK: 524 files, 41 epics, 461 tasks, 22 releases` |
| `docs_index.py --check-descriptions` / `check_command_blocks.py --base origin/dev` / `check_links.py` | `All 59 indexed documents under docs/ have a description` / and the two below, after this report |

**One run broke agreement 10, and I am reporting it.** One run's file list came from a zsh glob
that matched nothing, so the list was empty and `pytest` started on its default paths: the whole
selection. The 115 s process-group hard stop killed it, with no result and no leftover worker. I
built every list after that with `NULL_GLOB` and checked it was not empty first.

**CI time.** The new end-to-end tests in `bucket_mode/test_parse_owed.py` add about 20
test-seconds at `-n 4`.

## Files changed

* **`debate_core.application`**:
  * `caselist_sync.py`: `ParseOwed`, `ParsesOwed`, `FullParseOwed`, `ParseOwedUnreadable`,
    `parses_owed_sentence` and `PARSE_OWED_FILENAME`. The publish stage owes a parse for each
    snapshot it confirms. The parse stage parses what is owed first, writes down full parses owed,
    and clears an entry at a complete publish. The `full_parse_owed` parameter is new, the cure's
    wording changed, and the module docstring was updated.
  * `caselist_parse.py`: `CaselistParseService.full_parse_owed`.
  * `caselist_pull_parse.py`: the pass-through.
  * `caselist/run_state.py`: the new file joins `STATE_FILES` (it is restored, saved and seeded),
    and `RunState.parses_owed` reads the bucket's copy.
  * `caselist/removal_service.py`: clears the entries of the snapshots a removal reaches.
  * `sync_runs.py`: `parse_commands` names no cure when the details say nothing is owed.
* **`debate_cli`**:
  * `container.py`: the bump check, `parse_owed()`, and the removal's record.
  * `parses_owed.py` (new): what `runs` and `status` say.
  * `commands/caselist_runs.py` and `commands/caselist.py` (`status`): `parses_owed` in `--json`,
    and a sentence in the caption.
* **Tests**:
  * `bucket_mode/test_parse_owed.py` (new): 14 tests.
  * `test_bucket_mode_kills.py`: nothing may be late.
  * `test_bucket_mode_restore.py`: six state files; a bucket with no parsed store now owes `openev`
    its full parse too.
  * `test_bucket_mode_parse_fix_names_the_cloud_run.py` and `test_restore_run_state.py`: wording.
  * Core: `test_parse_owed_record.py` (new, 17 tests), the cure wording and runbook test in
    `test_caselist_sync_names_the_cloud_cure_in_bucket_mode.py`, and the failure-rate fix line in
    `test_caselist_sync_bucket_mode_hints_point_at_the_cloud.py`.
* **Runbooks**:
  * `caselist-cloud-run.md`: "A failed parse stage" rewritten, and a new section, "A new image with
    a new parser version".
  * `caselist-scheduled-sync.md`: "The parse stage", "After a release that bumps the parser
    version", and four sentences that described the parse stage's old rule.
* **Spec**: the Goal's phase, set to `Succeeded`.

## Deviations from the spec

1. **Two hints still say "imports into".** You asked me to keep hint changes to the cure lines the
   spec names, so I left these alone:
   * Local mode's `_unpublished_parsed_store_fix` ends "The next pull that imports into that
     caselist does the same". This is now understated: the next pull does it either way.
   * `v1-e40-t22`'s newer-fingerprint-table hint says "the next cloud run that imports into the
     caselist, on an image whose fingerprint version is the table's or later".

   Both are true but narrower than the behaviour. The PM ruled on 2026-11-01 that `v1-e40-t25`
   changes them (Follow-up 1). The runbook sentences that described the old rule as fact are
   corrected.
2. **No smoke check was added.** Working agreement 5 asks for smoke checks when a user-facing
   surface changes. `caselist runs` and `caselist status` gain a `parses_owed` key and a caption
   sentence, and `caselist pull` parses more. The spec has no smoke node, and `tests/smoke/` is not
   in its packages. The existing in-process pull smoke check passes. See Follow-up 2.

## Decisions and assumptions

* **A separate file, not a key of the pending-work file.** An older build reads the pending-work
  file's `publish` key and writes the file back with that key alone, so dev.164's next Wednesday
  would have dropped a `parse` key. An older build never lists a new file.
* **Owed at the publish's confirmation, before the pending-work file lets the snapshot go.** A run
  killed between the two writes owes the parse; it never owes neither. A complete archive owes
  nothing, because it names nothing to parse. `--publish-pending`'s publish stage owes too, and the
  next pull parses what it owes.
* **Cleared per caselist.** The parse plans over the whole caselist, so publishing a caselist's
  store complete covers every snapshot of it that is owed. A removal clears per snapshot, as the
  spec says, and leaves full parses owed.
* **Only an environment that publishes owes anything.** Without a bucket, nothing could ever clear
  an entry. There the bump check still adds the caselists to the parse but writes no entry.
* **The bump check skips caselists that will be parsed anyway** (imported into, or already owed).
  Without that, a first pull read as "parsed in full, as the store held no directory of …" for a
  caselist it had imported. This was caught by `test_caselist_runs.py`'s pinned caption.
* **A caselist owed that the run does not follow is left owed, and the stage says so.** In bucket
  mode its parsed store is not restored, and a retired caselist is not the run's to publish.
* **The bump test's index keeps its id.** A relabelled parser reads the same cards, so the rebuilt
  index is the published one's twin, and the stage correctly does not publish it again. The test
  asserts that the index was built from the new version, where before the stage failed. A real
  bump's index is a different one.
* **The no-cure fix line.** `Notification.fix_command` is a required string, so "names no cure"
  became `none owed: the parsed store was published (caselist-cloud-run.md, "A parse stage over its
  failure rate")`, not a change to the notifier port. Details without `parsed_stores_owed` (dev.164)
  cannot say that nothing is owed, so they keep the cure. This is told apart by `model_fields_set`.
* **The cure names caselists with "and"**, `testcl26 and openev`, because the next run publishes
  each of them. Before, "or" matched "imports into either".
* **A parse-owed file that cannot be read** is never written over and never taken as empty. The
  parse stage fails on it, with the file named by its role. A removal leaves it alone and is not
  stopped by it.
* **A drift republish owes a parse too.** That costs one aggregate rebuild in a rare week and was
  simpler than telling republishes apart.

## Operator follow-ups

None to run. After the merge, the next image apply puts this on the cloud run, and the runbook's
usual plan and apply are the PM's call. Until then dev.164 runs each Wednesday as before and writes
no parse-owed file. On that new image, the first run parses every caselist it follows in full under
docx-7, so dev's docx-7 re-parse becomes that run's. Whether prod's (`v1-e40-t16`) still needs the
restored-copy steps depends on whether a run publishes to prod, which is the PM's to rule.

## Follow-up work

1. **The two remaining "imports into" hints** (Deviation 1). **PM ruling, 2026-11-01: (a).** They
   drop "imports into" in `v1-e40-t25`, whose spec the PM amends in the next batch; this task does
   not change them. Their exact current text and where they live, at this branch's head:
   * **Local mode's parse fix**: `_unpublished_parsed_store_fix` in
     `packages/debate_core/src/debate_core/application/caselist_sync.py` (the last sentence it
     appends, used when `bucket_mode` is off):

     > The next pull that imports into that caselist does the same; `caselist pull --publish-pending` does not.

     Its tests pin it whole: `PUBLISH_ONLY_FIX` in `test_pull_parses_new_sources.py`, and the fix
     texts in `test_caselist_sync_names_publish_only_per_caselist.py`,
     `test_pull_notification_says_retry_or_person.py` and
     `test_sync_banner_says_what_happened_and_shows_its_fix_whole.py`, all under
     `packages/debate_core/tests/application/caselist/`.
   * **The newer-table hint in bucket mode**: `NewerFingerprintTable.cloud_fix` in
     `packages/debate_core/src/debate_core/application/caselist/occurrence_table_guard.py`, with its
     docstring ("the next cloud run that imports into the caselist on it"):

     > The occurrence table of `<caselist>` `<version>` in `<store>` is stamped `<stamped>`, and the cloud run's image's fingerprint version is `<build>`. The next cloud run that imports into `<caselist>` on an image whose fingerprint version is `<stamped>` or later rebuilds and publishes it: a new image is built and applied as `<CLOUD_NEW_IMAGE_RUNBOOK>` says, after the PM's word; never a rebuild or a publish from the operator's Mac.

     Pinned in `test_caselist_sync_bucket_mode_hints_point_at_the_cloud.py`, and its runbook
     paragraph, "A parse stage refused a newer occurrence table" in `caselist-cloud-run.md`, says the
     same.

   The behaviour behind both is this task's: a caselist whose parse raised, or whose parsed store
   was not published, stays owed, and the next pull parses it whether or not it imports anything.
2. **A smoke check for `parses_owed`** in `caselist runs --json` and `caselist status --json`
   (Deviation 2), for the PM to file.
3. **Clearing on a by-hand `caselist parse --publish`.** Only the pull's parse stage clears an
   entry. After a hand parse, the next pull rebuilds the caselist's aggregates once more, publishes
   nothing new, and then clears it. That is minutes, not a loss.
4. **A cloud full-parse timing.** The first run on a new parser version records `stage_times`. The
   parse stage's duration there replaces this report's estimate in `caselist-cloud-run.md`.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
