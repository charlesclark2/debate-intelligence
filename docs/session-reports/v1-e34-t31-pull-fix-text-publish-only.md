# Session report: v1-e34-t31-pull-fix-text-publish-only

| | |
|---|---|
| Task | `v1-e34-t31-pull-fix-text-publish-only` — The weekly run names caselist parse --publish-only where a publish-only finishes the stage |
| Spec | [`plan_specs/v1/e34-caselist-sync/t31-pull-fix-text-publish-only.yaml`](../../plan_specs/v1/e34-caselist-sync/t31-pull-fix-text-publish-only.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t31-pull-fix-text-publish-only` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The weekly run's parse stage now names a command for each caselist whose parsed store it did not
publish complete. It names `caselist parse --caselist <slug> --publish-only` when the stage rebuilt
that caselist's aggregates without the suppression list falling back to the run's own copy, and the
run keeps its working copy. Every other caselist gets `--publish`, which rebuilds first. The stage's
fix text, its reason when pending, the failed-stage banner's command, the login banner's
parsed-store sentence and a new `parsed_stores_owed` list all name the commands per caselist. The
list is in the run summary and, as a key the earlier builds pass over, in the run's details.
Details that name no caselist (every earlier build's) give `PARSE_COMMAND`, the generic `--publish`.
`v1.1.0-dev.155`, the Mac's installed build, and this branch's start commit read every record and
details line this build writes.

**Look at Deviation 1 first.** A bucket-mode run, which is what the cloud weekly run is, names
`--publish` for every caselist. The cloud task's version directory is on ephemeral storage and is
gone when the task stops. A later restore brings back the bucket's parsed store, not the one the
failed publish left. So the directory a later `--publish-only` would publish, wherever it is run, is
not the one the run rebuilt, and the record cannot vouch for how its aggregates were built. As
built, `--publish-only` is named only for local-mode pulls. The question for the PM is at the end of
Deviation 1.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `fix-text` (Parse-stage fix text) | Done | Per-caselist decision in `_parse_stage`, `ParsedStoreOwed`, `parse_command`, the details key, `parse_commands` for the banners, the composition root's `working_copy_outlives_the_run`, docstrings, runbook, a cross-build read, and 19 mutants |

## Acceptance criteria

"dev.155" is the tag `v1.1.0-dev.155` (`76b53e7`). The cutover report names it as the Mac's
installed build, and the run image is that build or a later one. "The start commit" is `b0cf40f`
(after the sync, `fa3bdad`), whose `sync_runs` is the same as dev's head when this task started.
Both were exported with `git archive` into the session's scratch directory and put first on
`PYTHONPATH`. The tag was already local, so nothing was fetched, and no installed build was opened.
"Red" means the tests committed in `c976d52` (`7859506` before the sync), run against a skeleton
whose new fields exist and are never filled.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: a stage whose publish alone failed names `--publish-only` for that caselist, by a test shown failing first | PASS | `test_caselist_sync_names_publish_only_per_caselist.py`. **Red:** 9 failed, 5 passed, over the new file's 13 tests then and the `UnknownSyncEvent` test. The failures: `assert [] == [('testcl26', True)]` for the publish-alone case, the same form for every other run case, and `'…<slug> --publish' == '…testcl26 --publish'` for an entry that does not say. The 5 that passed hold on the skeleton too: the earlier builds' generic command, a completed stage owing nothing, the command builder and the schema refusing a changed key. The ninth failure was the `UnknownSyncEvent` assertion in `test_caselist_sync.py`. **Green:** the weekly's publish refused (`STORE_UNAVAILABLE`) after a rebuild from every copy gives `parsed_stores_owed == [('testcl26', True)]`. Its hint names `` `debate-research caselist parse --caselist testcl26 --publish-only` `` and not `--publish`, the banner's command is exactly that command, and the details line holds `{"caselist": "testcl26", "publish_only": true}`. The same holds for a publish that raised a bug, a refused grant and objects the bucket did not confirm |
| **ac1**: one whose aggregates read only this machine's list names `--publish`, by a test shown failing first | PASS | Same file. **Red:** `assert [] == [('testcl26', False)]`. **Green:** the bucket's copy of the list needs a login during the rebuild. Nothing is offered to the bucket, the stage is `pending`, and `[('testcl26', False)]` is recorded. The reason names `` `…--caselist testcl26 --publish` `` with no `--publish-only` anywhere. The login banner reads `The parsed store waits too; after the login: debate-research caselist parse --caselist testcl26 --publish`. The real-pipeline test `test_aggregates_rebuilt_from_this_machines_copy_of_the_list_alone_are_not_published` asserts the same |
| PM: a run with one of each names each correctly, in the fix text, the banner and the command | PASS | Weekly refused (every copy) plus camp file from the run's own list: a failed stage. The hint is pinned whole, by hand: `` `…testcl26 --publish-only` publishes the parsed store as this run rebuilt it from every copy of the suppression list, and rebuilds nothing. `…openev --publish` publishes a caselist's parsed store: … ``. The banner's command is `…testcl26 --publish-only; …openev --publish`. The other way round (a pending stage) gives the login banner `after the login: …testcl26 --publish; …openev --publish-only`. A crashed rebuild beside a refused publish gives `…testcl26 --publish; …openev --publish-only`. Two caselists both owing only the publish give the plural sentence, pinned by hand. `PARSE_COMMAND` stays only as the can't-tell fallback; `sync_runs.parse_commands(details)` replaces it everywhere a run's own details are read |
| PM: a record with no word on how its aggregates were built names `--publish` | PASS | Details with `parsed_stores_owed` removed (what every earlier build writes) give the failed banner `PARSE_COMMAND` and the login banner `after the login: debate-research caselist parse --caselist <slug> --publish`. An entry `{"caselist": "testcl26"}` with no `publish_only` gives `…testcl26 --publish` |
| **ac1**: the agent's build reads every record this build writes, by test | PASS | **By test:** `test_the_earlier_builds_read_every_record_and_every_details_line_this_build_writes`. The one-of-each run's record line and bucket record validate against `record_schema_of_the_start_commit.json` (`v1-e34-t19`'s, equal to the installed-build one). Its details line and bucket details validate against the new `details_schema_before_parsed_stores_owed.json`, printed by dev.155 and by the start commit, byte for byte the same. The record carries no `parsed_stores_owed` and no stage key beyond `stage`, `outcome` and `reason`. A companion test shows that schema refuses a details line whose `parse` is not counts. `test_pull_run_record_is_read_by_every_build.py`: `67 passed`, with each scenario's pinned details gaining `"parsed_stores_owed": []` and its record lines unchanged. **By each build's own readers:** see [Every build reads this build's files](#every-build-reads-this-builds-files). dev.155 and the start commit exit 0 with `refused or skipped: 0` on three scenarios, and their banners name the generic `--caselist <slug> --publish`. **The check can fail:** see mutant 4a below |
| Node: Sync tests pass (`uv run pytest packages/debate_core/tests/application -k caselist_sync`) | PASS | Run as `.venv/bin/python -m pytest packages/debate_core/tests/application -k caselist_sync -n auto` under a 115 s hard stop, before the docs commit: `234 passed in 59.85s`. After the sync, the files this task touched: `310 passed in 28.74s` |
| Forbidden: a record shape an earlier build refuses to read | PASS | As the ac1 row above. Nothing was added to `SyncRunRecord` or `StageEntry`. The new key is in `SyncRunDetails`, whose models ignore unknown keys in every build since `v1-e34-t19` |
| Forbidden: naming `--publish-only` where the aggregates came from this machine's copy of the list alone | PASS | The second ac1 row, and mutants 1a, 1b, 2a, 2c and 9, each caught. A bucket-mode run names `--publish` for every caselist (Deviation 1) |
| Forbidden: network or AWS access in any test | PASS | Every new test runs against moto under `tmp_path`, with the fake source and a scripted parse stage. The bucket-mode wiring test uses `bucket_mode/conftest.py`'s world (moto, respx). The stored schema was printed offline from local exports |
| PM: mutants (1) to (4), each caught (agreement 8) | PASS | 19 mutants, all caught. See [Mutants](#mutants) |
| PM: `UnknownSyncEvent` names `debate_cli.caselist_events` | PASS | **Red:** the assertion in `test_a_caselist_whose_event_this_build_does_not_know_is_not_imported_under_a_guess` failed on `…the table in debate_cli.commands.caselist`. **Green:** passes. See Deviation 2 |
| PM: runbook sentences that say `--publish` after a failed parse stage name the choice | PASS | `caselist-scheduled-sync.md` changes in three places: what a notification says, the expired-session publish, and `STORE_UNAVAILABLE`/`STORE_ACCESS_DENIED` under `parse: failed`. `test_the_runbook_shows_both_wordings_…` now also holds `…--caselist <slug> --publish-only` and `--publish` for every caselist. The other `--publish` lines (`NEWER_FINGERPRINT_TABLE`, removals, backfiles) are rebuilds and stay |
| Closing checks (working agreement 10) | PASS, with the affected set left to CI | See [Closing checks](#closing-checks) |

### Every build reads this build's files

`write_parsed_stores_owed_files.py` is not collected and runs only when named. It writes what this
build leaves after three scenarios, each a pull through the real run monitor against moto:

* `one_of_each_failed`
* `one_of_each_pending`
* `bucket_mode_publish_refused`

`read_sync_run_files.py` (from `v1-e34-t23`) now also prints, for files that carry
`parsed_stores_owed` and only for those: the key as written and as the reading build kept it, the
record's parse reason, and the reading build's own `notifications_for` banners. `S` is the
scratch directory; `S/dev155` and `S/start` are the two exported sources:

```bash
WRITE_PARSED_STORES_OWED_FILES="${S}/files/this-build" .venv/bin/python -m pytest packages/debate_core/tests/application/caselist/write_parsed_stores_owed_files.py -p no:cacheprovider --no-cov -n 0 -q
.venv/bin/python -I packages/debate_core/tests/application/caselist/read_sync_run_files.py "${S}/files/this-build" this-build
PYTHONPATH="${S}/dev155/packages/debate_core/src" .venv/bin/python packages/debate_core/tests/application/caselist/read_sync_run_files.py "${S}/files/this-build" v1.1.0-dev.155
PYTHONPATH="${S}/start/packages/debate_core/src" .venv/bin/python packages/debate_core/tests/application/caselist/read_sync_run_files.py "${S}/files/this-build" start-commit-b0cf40f
```

All three exited 0. After the first line, dev.155's output and the start commit's are identical.
This build's differs only where it keeps the key and names each caselist. Part of dev.155's output:

```text
one_of_each_failed:
  record 20260916T060000Z: incomplete; select completed, download completed, import completed, publish completed, parse failed, search_index skipped, landscape skipped, report completed, retention completed
  details 20260916T060000Z as written: parsed_stores_owed [{'caselist': 'testcl26', 'publish_only': True}, {'caselist': 'openev', 'publish_only': False}]
    kept by this build: parsed_stores_owed unknown here
  banner 'caselist pull finished with a failed stage': fix 'debate-research caselist parse --caselist <slug> --publish'
  bucket reports/sync-run-details/2026/20260916T060000Z.json: read as SyncRunDetails
  bucket reports/sync-runs/2026/20260916T060000Z.json: read as SyncRunRecord
one_of_each_pending:
  record 20260916T060000Z: publish_pending; ... parse pending, ...
  banner 'caselist publish waiting for an AWS login': fix 'aws sso login && debate-research caselist pull --publish-pending'
    the parsed store waits too; after the login: debate-research caselist parse --caselist <slug> --publish
refused or skipped: 0
```

This build, on the same files: `fix 'debate-research caselist parse --caselist testcl26 --publish-only; debate-research caselist parse --caselist openev --publish'`,
and `after the login: debate-research caselist parse --caselist testcl26 --publish; debate-research caselist parse --caselist openev --publish-only`.

These reads ran before the sync onto `ed332e5`. The rebase had no conflicts, and none of dev's new
commits touches `caselist_sync.py`, `sync_runs.py` or the test files involved.

### Mutants

Each mutant was a one-occurrence replacement in the source. Each ran on seven test files (the new
file, `test_pull_parses_new_sources.py`, the every-build test, the two banner tests, the
newer-fingerprint test and the bucket-mode wiring test) with `-n 4`, a fresh
`HYPOTHESIS_STORAGE_DIRECTORY` each (none of these tests uses Hypothesis), and `git checkout HEAD --`
after each. The tree was checked clean at the end of every batch. 8 to 12 s a mutant.

| # | Mutant | Result | Caught by (first few) |
|---|---|---|---|
| 1a | PM (1): `--publish-only` whatever the list did (`publish_only = working_copy_outlives_the_run`) | CAUGHT, 6 failed | local-list-only stage, one of each, the other way round, crashed rebuild |
| 1b | PM (1): a caselist left unpublished after a fallback recorded as rebuilt from every copy | CAUGHT, 4 failed | local-list-only stage, one of each, the other way round, the real-pipeline fallback test |
| 2a | PM (2): one decision for the run (any fallback in the stage decides every caselist) | CAUGHT, 3 failed | the other way round, crashed rebuild, the newer-fingerprint test |
| 2b | PM (2): the banner names the first caselist's flag for every caselist | CAUGHT, 3 failed | one of each, the other way round, crashed rebuild |
| 2c | PM (2): the banner names `--publish-only` for all when any is | CAUGHT, 3 failed | the same |
| 3a | PM (3): an entry that does not say defaults to `--publish-only` | CAUGHT, 1 failed | an entry that does not say |
| 3b | PM (3): details that name no caselist give `--publish-only` | CAUGHT, 3 failed | earlier build's details (failed and login banners), the failure-rate test |
| 4a | PM (4): the record gains `parsed_stores_owed` | CAUGHT, 43 failed | the earlier-builds schema test, `test_this_builds_record_model_is_the_one_both_older_builds_read_with`, every-build run-log tests |
| 4b | PM (4): a stage entry gains `publish_only` | CAUGHT, 35 failed | the same |
| 5 | bucket mode ignored by the stage | CAUGHT, 1 failed | bucket-mode run names `--publish` |
| 6 | the composition root says every run keeps its working copy | CAUGHT, 1 failed | `test_the_pull_is_told_whether_its_working_copy_outlives_it[bucket-False]` |
| 7 | login banner keeps `PARSE_COMMAND` | CAUGHT, 4 failed | local-list-only stage, the other way round, two real-pipeline session tests |
| 8 | failed banner keeps `PARSE_COMMAND` | CAUGHT, 9 failed | publish-alone, bucket mode, … |
| 9 | a crashed rebuild named `--publish-only` | CAUGHT, 2 failed | crashed rebuild, newer fingerprint table |
| 10 | session expired during the parsed publish named `--publish` | CAUGHT, 1 failed | `test_a_session_that_expires_during_the_parsed_stores_publish_…` |
| 11 | a refused publish named `--publish` | CAUGHT, 7 failed | publish-alone, bucket does not answer, refused grant, … |
| 12 | objects not confirmed named `--publish` | CAUGHT, 1 failed | `test_objects_the_bucket_did_not_take_…` |
| 13 | a publish that raised a bug named `--publish` | CAUGHT, 1 failed | `test_a_publish_that_raised_something_unmodelled_…` |
| 14 | the details drop what the stage recorded | CAUGHT, 12 failed | every run case that reads the details |

Mutants 6, 12 and 13 have catches only because I added assertions before the run. Reading the
branches showed that nothing asserted them: the container wiring test, the hint assertion in
`test_objects_the_bucket_did_not_take_…`, and the bug-in-the-publish test (commit `93c9df3`).

**Mutant 4a against the earlier builds' own readers.** With 4a applied, I wrote the three scenarios'
files again, restored the source, and read them with dev.155: exit 1, `refused or skipped: 9`. Each
scenario printed `REFUSED in the bucket: reports/sync-runs/2026/20260916T060000Z.json: 1 error(s)`,
and the log printed `WARNING: caselist run log: line 1 is not a valid run record; skipped`.

### Closing checks

`uv run scripts/affected_tests.py` chose **268 of 560 test files** (47.9%, after the sync). The 264
before the sync are more than two minutes on this Mac, so under agreement 10 the whole affected set
is left to the pull request's `ci` and was not handed over. What ran, each under a hard stop on the
interpreter:

| Run | Result |
|---|---|
| Always-run list plus the docs checks (`tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py tests/docs tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py`), after the sync | `571 passed, 1 warning in 33.71s` |
| `packages/debate_core/tests/application/caselist` (the test directory of what changed), before the sync | `1640 passed in 113.34s` |
| The twelve files this task touched or that pin its wording, after the sync | `310 passed in 28.74s` |
| `packages/debate_cli/tests/commands/` files in the affected set (25), after the sync | `464 passed in 35.83s` |
| `packages/debate_cli/tests/bucket_mode/` files in the affected set (9), after the sync | **Cut off** by the 110 s alarm at a load average of 22 to 50 (another session's pytest was running). 121 tests passed and none failed before the cut. Left to CI |
| `tests/smoke/test_caselist_pull_in_process.py tests/smoke/test_caselist_pull.py` | `22 passed in 38.54s` |
| `ruff format --check .` / `ruff check .` | `1570 files already formatted` / `All checks passed!` |
| `pyright packages/debate_core packages/debate_cli` | `0 errors, 0 warnings, 0 informations` |
| `lint-imports` / `scripts/check_thin_handlers.py` | `18 kept, 0 broken` / `67 … handlers within 25 statements` |
| `scripts/check_command_blocks.py` | `OK: no # comments in 553 shell code blocks in 195 Markdown files` |
| `uv run scripts/validate_specs.py` | `OK: 492 files, 40 epics, 430 tasks, 22 releases` |

An earlier attempt at the CLI files (34 together, at load 32 rising to 175) passed its 115 s alarm
in the background and left its xdist workers running. I stopped the task and checked that no
process from this worktree remained before going on.

## Files changed

* `packages/debate_core/src/debate_core/application/caselist_sync.py`:
  * `ParsedStoreOwed`, `parse_command`, and `RunSummary.parsed_stores_owed` (an additive summary key).
  * `CaselistSyncService(working_copy_outlives_the_run=False)`.
  * The per-caselist decision in `_parse_stage`, and `_unpublished_parsed_store_fix` in place of the
    generic constant.
  * The module docstring's "Which command finishes each caselist".
  * `UnknownSyncEvent`'s hint.
* `packages/debate_core/src/debate_core/application/sync_runs.py`: `ParsedStoreOwedDetails`,
  `SyncRunDetails.parsed_stores_owed`, the copy in `details_for_summary`, and `parse_commands(details)`
  for the failed banner and the login banner. `PARSE_COMMAND` is now the can't-tell fallback.
* `packages/debate_cli/src/debate_cli/container.py`: `working_copy_outlives_the_run=not self._in_bucket_mode`.
  `commands/caselist_pull.py`: its docstring's parse-stage paragraph.
* `docs/runbooks/caselist-scheduled-sync.md`: the three places above.
* Tests, new:
  * `test_caselist_sync_names_publish_only_per_caselist.py` (15 tests; 13 at red, two added before the mutation run).
  * `bucket_mode/test_bucket_mode_parse_fix_names_publish.py`.
  * `stored_run_records/details_schema_before_parsed_stores_owed.json`, with its README row and the
    commands that printed it.
  * `write_parsed_stores_owed_files.py`, which is not collected.
* Tests, changed:
  * `read_sync_run_files.py`: prints this task's key.
  * `test_inbox_retention.py`: `Installation.sync(working_copy_outlives_the_run=True)`, as the
    composition root's local mode.
  * Pins of whole details lines: the every-build test and the two refused-before-the-bucket tests.
  * `<slug>` wording now naming the caselist: `test_pull_parses_new_sources.py`,
    `test_pull_refuses_a_newer_fingerprint_table.py`, `test_pull_notification_says_retry_or_person.py`.
  * The banner-limits test: one banner more, four caselists' commands at their longest, which it
    shows whole.
  * `test_caselist_sync.py`: the `UnknownSyncEvent` hint.

## Deviations from the spec

1. **A bucket-mode run names `--publish` for every caselist, even where only the publish failed.**
   The PM's context says to read "this Mac's copy of the list" as the run's own local copy, and to
   decide each caselist from what the stage recorded, not from the machine or the environment. I
   did decide from what the run records. But a fact the spec does not mention decides the cloud
   case: `--publish-only` publishes the version directory it finds where it is run. The cloud run's
   directory is on its task's ephemeral storage (`infrastructure/modules/caselist_run/run_task.tf`:
   "The data directory, on the ephemeral volume"). Nothing saves an unpublished one: `run_state.py`
   saves state files, the bundle and held uploads, and its restore brings back the bucket's parsed
   store. So after a failed cloud publish there are three possibilities:
   * `--publish-only` on the Mac publishes the Mac's own directory, whose aggregates the record
     knows nothing about.
   * In a restored copy it publishes what the bucket already holds.
   * After a partial publish it uploads nothing, and the stage looks finished while it is not.

   That is the record not being able to tell, so it fails toward `--publish`. The service takes
   `working_copy_outlives_the_run` (default off), and the composition root sets it to
   `not _in_bucket_mode`. In practice the cloud weekly run will never name `--publish-only`; only a
   local-mode pull will. Question for the PM:

   > **v1-e34-t31, Deviation 1: should a bucket-mode (cloud) run ever name `caselist parse --publish-only`?**
   > The cloud task's version directory dies with the task, and no command restores an unpublished one.
   > (a) **Keep it as built (recommended):** bucket mode names `--publish` for every caselist. It is
   > always safe, and it is what the cloud run names today.
   > (b) Name `--publish-only` in bucket mode too, as the context read literally. This would need a
   > way to keep the unpublished directory (for example, save it under the run lock before the task
   > ends), which is new scope in E40.
   > (c) Name nothing runnable in bucket mode, and point to the next weekly run, which re-parses that
   > caselist and publishes it.
   > Why (a): (b) names a command that cannot finish the stage today, and (c) leaves a hand fix
   > unnamed. Whichever you choose, see Follow-up 1: where the operator runs the `--publish` that a
   > failed cloud parse stage names is not written down anywhere.
2. **`UnknownSyncEvent` now ends "add the slug prefix to the table in debate_cli.caselist_events"**,
   the PM's ruling of 2026-10-28 on `v1-e01-t39`'s question 1. Only its hint changed, the way
   `v1-e01-t39` changed `UnknownCaselistEvent`'s. No test asserted the old location, so the test of
   an unknown event now asserts the new one, shown failing first. The spec's description does not
   say this yet; the PM's next batch adds it.
3. **The spec's "the agent's build"** is read, per the PM's context, as every build that reads a
   run record. The record-compatibility test uses dev.155's and the start commit's schemas, which
   are the same. The test model was `v1-e34-t19`'s every-build test and `v1-e34-t28`'s cross-build
   read; `v1-e40-t09` left no record-compatibility test of its own that I could find.

## Decisions and assumptions

* **What is recorded is the decision, not the facts.** Each entry is `{caselist, publish_only}`, and
  `publish_only` defaults to false. An entry that does not say, details with no list and an older
  build's details all name `--publish`. A boolean cannot gain a third meaning that an earlier
  reader's `Literal` would refuse.
* **"Read every copy"** means the pull's `LocalFallbackSuppressionList` counted no fallback during
  that caselist's rebuild. The count is per read and the list never caches a fallback, so each
  caselist's rebuild is judged on its own reads. Once one caselist falls back, the stage still sends
  nothing more to the bucket, as before. A later caselist whose own rebuild read every copy is then
  named `--publish-only`.
* **A list that is not the fallback list** (the test worlds' plain list) never falls back, so its
  rebuilds read every copy. This is why the existing real-pipeline "session expired overnight" test
  now expects `--publish-only`; a comment there points to the fallback test that expects `--publish`.
* **The banner joins commands with `; `**, so the line can be pasted into zsh. Four caselists at
  their longest fit the Mac's observed ten lines of 45 characters, by the banner-limits test.
* The details key is top-level, beside `parse`, not on each stage. A per-stage key would have
  changed every stage's JSON, which `tests/smoke/` pins whole, outside this task's packages.
* `--publish-only` has no dry run, so the runbook's expired-session block is unchanged (`--publish`
  is never wrong). The prose around it says when the stage names `--publish-only` and that it goes
  in place of the last line.

## Operator follow-ups

None. The affected set (268 files) is left to the pull request's `ci`, per agreement 10.

## Follow-up work

1. **Where a failed cloud parse stage's `--publish` is run (E40).** The banner names
   `caselist parse --caselist <slug> --publish`. Run on the Mac, it rebuilds and publishes the Mac's
   own store to the bucket the cloud run owns. No runbook says to do that, or to do it from a
   restored copy. `caselist-cloud-run.md` and `caselist-run-alerts.md` say nothing about a failed
   parse stage. Until one does, leaving it to the next weekly run that imports into the caselist is
   the only documented cure. This predates this task: it is `PARSE_COMMAND`'s wording in the cloud.
2. The "next pull that imports into that caselist does the same" sentence is singular after a plural
   list of commands. It was kept as the existing wording, which tests and the runbook quote.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-29

**Notes:**

Each caselist now gets the command that finishes it, and the earlier builds still read every line.
1. **ac1 passes, both halves.**
   * Red: 9 failed against a skeleton whose fields exist and are never filled.
   * Green: a publish that alone failed names `--publish-only` for that caselist, in the hint, the
     banner and the details. A stage whose aggregates read only the local list names `--publish`,
     with no `--publish-only` anywhere.
   * One of each, both ways round, is pinned whole by hand. So is the record that does not say.
2. **The earlier builds read everything, shown two ways.** By schema: the record's is unchanged, and
   the details' is printed by dev.155 and the start commit, byte for byte the same. By each build's
   own reader: exit 0, `refused or skipped: 0`. With mutant 4a applied, dev.155 refuses nine files, so
   the check can fail.
3. **Mutants:** the PM's four, each two ways, and eleven more, all caught. Three of them (6, 12, 13)
   are caught only because you found unasserted branches and asserted them first. That is the point
   of the exercise.
4. **Deviation 1: (a), keep it as built.** My context said to decide from what the stage records, not
   from the environment. You found the fact that overrides it: in bucket mode, the directory a later
   `--publish-only` would publish dies with the task, so the record can't vouch for it. That is
   exactly the "can't tell, say `--publish`" case. A cloud run names `--publish` for every caselist.
5. **Follow-up 1 matters more than its place in the report suggests.** In bucket mode the banner names
   `caselist parse --caselist <slug> --publish`. Run on the Mac, that rebuilds the Mac's own working
   copy and publishes it to the bucket the cloud run owns. Nobody should do that. The PM's next batch
   files an E40 p2 task: in bucket mode, the fix text and `caselist-cloud-run.md` name the cloud cure
   (the next weekly run, or a hand-started cloud run), and never a Mac-side publish. Until it ships,
   the cure for a failed cloud parse stage is the next weekly run, and the PM records that rule for
   the operator.
6. **Deviations 2 and 3: accepted.** The `UnknownSyncEvent` hint is the PM's ruling. "The agent's build"
   is read as ruled, with the right models found.
7. **Decisions accepted:**
   * the decision is recorded, not the facts, and a boolean that defaults to false can't gain a third
     meaning;
   * "read every copy" is judged per caselist from the fallback count;
   * commands are joined with `; ` for zsh, within the banner limits;
   * the details key is top-level, so `tests/smoke`'s pinned stage JSON doesn't change;
   * the runbook's expired-session block is unchanged.
8. **Follow-up 2:** no task. The singular sentence is quoted by tests and the runbook, and it is
   harmless.
9. **The affected set** (268 files) is left to the PR's `ci`. The always-run list, the caselist
   application tests, the CLI command files, the two pull smoke tests and the static checks pass.
   Bucket mode was cut off at load 22 to 50 with 121 passed and none failed. That set is CI's.
10. **Merge:** any time. The image deployed on 2026-10-29 is `dev.164`'s; this reaches the cloud run
    with the next image.
