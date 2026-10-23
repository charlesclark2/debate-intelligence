# Session report: v1-e34-t28-publish-stage-loose-ends

| | |
|---|---|
| Task | `v1-e34-t28-publish-stage-loose-ends` — Publish-stage loose ends: a cut-short report check, the manifest count, and a report-only outcome |
| Spec | [`plan_specs/v1/e34-caselist-sync/t28-publish-stage-loose-ends.yaml`](../../plan_specs/v1/e34-caselist-sync/t28-publish-stage-loose-ends.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t28-publish-stage-loose-ends` |
| Session status | COMPLETE |

## Summary

All three loose ends are fixed, and the run record's shape is unchanged.

1. **The cut-short check.** When an expired session cuts the report stage short, the stage now
   names the snapshots it published and did not compare, as `not_compared` on its entry in the
   run's details. `caselist pull --publish-pending` reads that list from the newest run's details
   and gives it back to the same `_report_stage`, which compares exactly those snapshots after
   whatever the drain publishes. Details written by an older build have no such list, so they owe
   nothing.
2. **The manifest count.** The publish stage now counts each manifest it uploads, in
   `objects_published` and in its reason (`1 object(s) uploaded across 1 snapshot(s): 0 source(s)
   and 1 manifest(s)`). The summary and the details also carry `manifests_published`.
3. **The report-only outcome.** A run whose only pending stage is the report is now
   `publish_pending`. That is an existing value, and dev85's reader accepts it.

Each item was shown failing first. The agent's build, `v1.1.0-dev.85`, read every file this
build writes, using its own readers.

**What to look at first:**
* The login banner's sentence about the cut-short check changed. It used to say
  `--publish-pending does not make it again`; that is no longer true.
* Three stored-record scenarios in the every-build compatibility test are now compared through a
  documented count transformation (Decision 4).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `publish-loose-ends` (Publish-stage loose ends) | Done | All three items, the runbook, a cross-build read by dev85 and the start commit, 19 mutants |

## Acceptance criteria

"dev85" is the tag `v1.1.0-dev.85` (`31782a8`), which the PM named as the agent's build. It was
present locally, so nothing was fetched. "The start commit" is `41c375e`, this branch's first
commit. I exported each one with `git archive` into the session's scratch directory and put it
first on `PYTHONPATH`. I did not open or run any installed build. "Red" means the tests committed
alone in `1856dd2`, run against unchanged source.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1 (1)**: a cut-short report check, by a test shown failing first | PASS | `test_caselist_sync_publish_stage_loose_ends.py`, sections (1). **Red:** for example `KeyError: 'not_compared'`; `assert [] == [('testcl26', '2026-09-08')]` ("week two, and week two alone"); `assert None == [{'caselist': 'testcl26', 'snapshot': '2026-09-01'}]` for the publish the session cut short; and the drift found by a check made again gave `assert 'skipped' == 'failed'`. **Green:** the check is cut short at the first comparison, so the details name both weeks; cut short at the second, they name week two only. When the publish itself pends after confirming week one, week one is owed a comparison and week two a publish. `--publish-pending` then asks the comparison for exactly `[('testcl26', '2026-09-08')]`, and the report reads `1 snapshot(s) confirmed in the bucket`. After a pending publish, it compares what it published and then what was owed: `[('testcl26', '2026-09-08'), ('testcl26', '2026-09-01')]`. A second drain compares nothing. Details stripped to what an older build writes compare nothing: the report is `skipped`, `nothing new was published`. A later pull settles the list (only the newest run counts). A run the lock refused is passed over. A check made again and cut short again is owed by that run. A check made again that finds a manifest mismatch owes it again, as the report stage does. The run log carries neither new key |
| **ac1 (2)**: the manifest count, by a test shown failing first | PASS | **Red:** `'4 object(s) … 1 snapshot(s)' == '5 object(s) … 1 manifest(s)'`, and for a republish of a manifest alone `'0 object(s) uploaded across 1 snapshot(s)'`. **Green:** a first publish of week one reads `5 object(s) uploaded across 1 snapshot(s): 4 source(s) and 1 manifest(s)`, with `objects_published` 5 in the summary and the record and `manifests_published` 1 in the details. The manifest-only republish reads `1 object(s) uploaded across 1 snapshot(s): 0 source(s) and 1 manifest(s)`. A publish left for a login reads `5 object(s) published, 1 snapshot(s) left for a later run: …` |
| **ac1 (3)**: a report-only pending run's outcome, by a test shown failing first | PASS | **Red:** `assert 'completed' == 'publish_pending'`, both end to end and in the outcome table; with a failed parse beside it, `'incomplete' == 'publish_pending'`. **Green:** the record line is `publish_pending` and `summary.succeeded` is still true. The table of seven stage combinations holds the existing outcomes: a failed publish is `failed`, a failed report is `incomplete`, a pending parse is `publish_pending` |
| **ac1**: the agent's build reads every record this build writes | PASS | No field was added to the record. `test_this_builds_record_model_is_the_one_both_older_builds_read_with` passes. **dev85 by its own readers:** see [Every build reads this build's files](#every-build-reads-this-builds-files). Exit 0, `refused or skipped: 0`, and four scenarios: the two `publish_pending` records, both details files with `not_compared` and `manifests_published`, and every bucket object. dev85's `SyncRunLog`, `SyncRunDetailsLog`, `PendingWork`, `snapshots_owed_again_for_drift` and `SyncRunHistory.recent_runs` with `banner_words` all read them, and its models report the new keys as `unknown here`, that is, passed over. **The check can fail:** the same files with the outcome `report_pending` in place of `publish_pending` make dev85 print `WARNING: caselist run log: line 1 is not a valid run record; skipped` and exit 1. That is why item (3) reuses the existing value |
| Node: Sync tests pass (`pytest packages/debate_core/tests/application -k "caselist_sync or publish"`) | PASS | Run as `.venv/bin/python -m pytest … -n auto` under a 115 s hard stop: `538 passed in 22.42s` |
| Forbidden: a record shape an earlier build refuses to read | PASS | As ac1 above. The every-build test passes: `67 passed` |
| Forbidden: network or AWS access in any test | PASS | Every new test runs against moto under `tmp_path`, with the fake source. The cross-build files were written the same way. Nothing was fetched: dev85's tag was already local |
| PM: mutation-check the owed-snapshot selection and the outcome choice | PASS | 19 mutants, every one caught. See [Mutants](#mutants) |
| Closing checks (working agreement 10) | PASS, with the affected set left to CI | See [Closing checks](#closing-checks) |

### Mutants

Each mutant was applied to the source file, run against the new test file and
`test_sync_report_stage_keeps_what_it_found_and_its_kind.py` with `-x`, and restored. The restore
was checked byte for byte, and `git status` was empty afterwards. Each run set
`HYPOTHESIS_STORAGE_DIRECTORY` to a new empty directory; no property tests are involved. The driver
was a scratch script, not committed, run in three batches of about 30 s each. "Caught by" is the
first test that failed. No mutant errored.

| Mutant | Caught by |
|---|---|
| Not compared: everything the stage was to compare, compared or not | `test_a_check_cut_short_at_its_second_comparison_saves_only_the_week_it_did_not_reach` |
| Not compared: off by one, leaving out the snapshot it expired on | `test_a_check_cut_short_at_its_first_comparison_saves_both_weeks_in_the_details` |
| Not compared: nothing, when no drift was found first | the same |
| Not compared: nothing, when drift was found first | `test_a_source_mismatch_found_before_the_session_expired_is_kept_and_needs_a_person` |
| Not compared: nothing, when the publish pended | `test_a_publish_the_session_cut_short_leaves_what_it_confirmed_owed_a_comparison` |
| Compare only what this run published, ignoring the owed list | `test_publish_pending_compares_exactly_the_weeks_the_cut_short_check_did_not` |
| Compare the owed list first, then what this run published | `test_publish_pending_publishes_what_is_owed_and_then_compares_it_and_the_check_owed` |
| Details leave out a report stage whose only content is `not_compared` | `test_a_check_cut_short_at_its_first_comparison_saves_both_weeks_in_the_details` |
| `run_pull` does not pass the owed comparisons | `test_publish_pending_compares_exactly_the_weeks_the_cut_short_check_did_not` |
| Reader: the oldest run's list | `test_the_check_made_again_is_owed_by_nothing_after_it` |
| Reader: a run with no stages is not passed over | `test_a_run_the_lock_refused_is_passed_over` |
| Reader: every run's list, not only the newest's | `test_the_check_made_again_is_owed_by_nothing_after_it` |
| Reader: a name with no place in the store is owed | `test_a_name_with_no_place_in_the_store_is_passed_over_and_the_rest_are_owed` |
| Reader: names not made unique | the same |
| Outcome: a pending report stage is not `publish_pending` | `test_a_report_only_pending_run_is_recorded_publish_pending` |
| Outcome: a failed stage beside it wins over a pending report stage | `test_the_outcome_of_a_run_by_how_its_stages_ended[the report pending beside a failed parse]` |
| Outcome: a pending report stage wins over a failed publish | `…[a failed publish is failed, as before]` |
| Outcome: a failed report stage counts as pending | `…[a failed report, as before]` |
| Outcome: the old value, `completed`, for a report-only pending run | `test_a_report_only_pending_run_is_recorded_publish_pending` |

The three reader tests on hand-written records (in commit `aab01f3`) were written after the
implementation, not before it. The mutants above are what show they test something.

### Every build reads this build's files

`write_publish_stage_loose_ends_files.py` is not collected; it runs only when its path is given.
It writes what this build leaves after four scenarios, each run through the real run monitor
against moto:

* `report_cut_short`
* `report_cut_short_then_drained`
* `publish_cut_short`
* `manifest_alone_republished`

`read_sync_run_files.py` is t23's and t26's reader. For files that carry this task's keys, and only
for those, it now also prints:

* each new key as written, and as the reading build's model kept it;
* the publish stage's reason;
* the reading build's own drift-history reader and `caselist runs` reader.

Earlier tasks' files print exactly as before. The commands were run from the worktree. `S` is the
session's scratch directory, and `S/agent` and `S/start` are the two exported sources:

```bash
WRITE_PUBLISH_STAGE_LOOSE_ENDS_FILES="${S}/files/this-build" .venv/bin/python -m pytest packages/debate_core/tests/application/caselist/write_publish_stage_loose_ends_files.py -p no:cacheprovider --no-cov -n 0 -q
uv run --frozen python -I packages/debate_core/tests/application/caselist/read_sync_run_files.py "${S}/files/this-build" this-build
PYTHONPATH="${S}/agent/packages/debate_core/src" uv run --frozen python packages/debate_core/tests/application/caselist/read_sync_run_files.py "${S}/files/this-build" agent-build-dev85
PYTHONPATH="${S}/start/packages/debate_core/src" uv run --frozen python packages/debate_core/tests/application/caselist/read_sync_run_files.py "${S}/files/this-build" start-commit
```

All three reads exited 0. After the first line, the outputs of dev85 and the start commit are
identical. This build's output differs from theirs only on the `kept by this build` lines. Part of
dev85's output:

```text
report_cut_short:
  record 20260916T060000Z: publish_pending; select completed, download completed, import completed, publish completed, parse skipped, search_index skipped, landscape skipped, report pending, retention completed
  details 20260916T060000Z: read, failure_codes [], 1 stage(s)
  details 20260916T060000Z as written: manifests_published 2
    kept by this build: manifests_published unknown here
    report not_compared as written: [{'caselist': 'testcl26', 'snapshot': '2026-09-01'}, {'caselist': 'testcl26', 'snapshot': '2026-09-08'}]
    kept by this build: unknown here
  record 20260916T060000Z publish reason: 14 object(s) uploaded across 2 snapshot(s): 12 source(s) and 2 manifest(s)
  owed again for drift, by this build's reader: []
  caselist runs: 20260916T060000Z publish_pending, details read, banner None
  bucket reports/sync-run-details/2026/20260916T060000Z.json: read as SyncRunDetails
  bucket reports/sync-runs/2026/20260916T060000Z.json: read as SyncRunRecord
manifest_alone_republished:
  record 20260916T090000Z publish reason: 1 object(s) uploaded across 1 snapshot(s): 0 source(s) and 1 manifest(s)
    objects_published 1
refused or skipped: 0
```

dev85's `sync_runs.py` is byte for byte this branch's start (`git diff v1.1.0-dev.85 41c375e`
prints nothing for it). Its `caselist_sync.py` differs only by the two search-index helpers that
`v1-e34-t30` added. So dev85's `SyncRunOutcome` is the one this build writes.

### Closing checks

* **The affected set** (`scripts/affected_tests.py`) lists 206 of 390 test files from 17 changed
  files. Run whole under a 115 s hard stop (`perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m
  pytest -n auto -m "not slow and not live" …`), it was stopped at about 80%. It is past the
  two-minute line, so under agreement 10 the rest is left to the pull request's `ci`, with no
  hand-off. What I did run of it, in pieces, each under the same hard stop:
  * The first 103 files: 3 failed and 1967 passed in 70 s. The three were CLI tests holding a
    stage entry or the details to the old keys. I updated them by hand (`d6edba6`).
  * Files 104 to 155: `1252 passed` in 28 s.
  * The last 51 files (19 under `tests/scripts`, 18 under `tests/smoke`) were stopped at 115 s;
    they are left to CI.
* **The changed test directories and the always-run list**, after the last change:
  * `packages/debate_cli/tests`, `tests/architecture`, `tests/specs`: `1072 passed` in 38 s.
  * `packages/debate_core/tests/application/caselist`, `test_caselist_sync.py`,
    `tests/smoke/test_caselist_pull.py`, `tests/smoke/test_caselist_runs.py`: `1648 passed` in 76 s.
* **The other checks:**
  * `ruff format --check .`: `1085 files already formatted`. `ruff check .`: all passed.
    `check-merge-conflict`: passed.
  * `uv run --frozen pyright` (project-wide, after the last format): `0 errors, 0 warnings, 0
    informations`.
  * `lint-imports`: `15 kept, 0 broken`. `check_thin_handlers.py`: 46 handlers within 25
    statements.
  * `docs_index.py --check-descriptions`: 42 described. `check_command_blocks.py --base
    origin/dev`: 339 blocks, no `#`. `check_links.py`: 1958 links OK.
  * `validate_specs.py`: `OK: 404 files, 39 epics, 344 tasks, 21 releases`.

## Files changed

* `packages/debate_core/src/debate_core/application/caselist_sync.py`:
  * `StageRecord.not_compared`.
  * The report stage compares what was published, then the owed list, and names what it did not
    reach.
  * `publish_pending(comparisons_owed=…)`, plus a sentence in its select stage.
  * `run_pull` hands over the newest run's list.
  * The manifest count: `RunSummary.manifests_published`, and the publish reason.
  * The module docstring.
* `packages/debate_core/src/debate_core/application/sync_runs.py`:
  * `PublishedSnapshot`, `StageDetails.not_compared` and `SyncRunDetails.manifests_published`.
  * `comparisons_owed_by_the_newest_run` and `SyncRunMonitor.comparisons_owed`.
  * `_outcome_of` for a pending report stage.
  * The banner sentence `THE_CHECK_WAS_CUT_SHORT`.
* `packages/debate_core/tests/application/caselist/test_caselist_sync_publish_stage_loose_ends.py`
  (new): the tests for all three items.
* `write_publish_stage_loose_ends_files.py` (new) and `read_sync_run_files.py` (extended), both
  beside it: the cross-build read.
* Existing tests that held the old count, keys or wording, each updated by hand with the reason
  beside it:
  * the every-build compatibility test (expected details, and the stored records' count; see
    Decision 4);
  * the drift, report-stage, banner, pending-work, parse, stage-codes and refused-start tests in
    `packages/debate_core/tests/application/caselist/`;
  * `test_caselist_sync.py`;
  * three CLI tests.
* `tests/smoke/test_caselist_pull.py`: the publish count now includes five manifests. See
  Deviation 1.
* `docs/runbooks/caselist-scheduled-sync.md`:
  * the 06:00 run's outcomes;
  * the details table and the summary fields (`objects_published`, `manifests_published`,
    `not_compared`);
  * "What waits for the login", with the new banner and how the drain makes the check;
  * the report-stage paragraph under "A login that will not be enough";
  * a new entry under "When something goes wrong".
* `plan_specs/…/t28-publish-stage-loose-ends.yaml`: Goal `Succeeded`.

## Deviations from the spec

1. **`tests/smoke/test_caselist_pull.py` is outside `constraints.packages`.** It asserted
   `objects_published` as the sources alone (14 + 1 for the camp file). With the manifests counted
   it is 20, five more: the three weeks, the camp release and the complete archive. I updated it by
   hand and ran it: `1 passed in 14.54s`. Leaving it would have failed `validate-dev`. Working
   agreement 5 asks a task that changes a user-facing surface to keep its smoke checks current, as
   `v1-e34-t30` did with `tests/smoke`.

## Decisions and assumptions

1. **What "published but not confirmed" holds.** It holds the snapshots the report stage had not
   compared when the session expired: what this run published plus anything owed, from the first
   one it did not reach. A snapshot it had already compared is not included, whatever the
   comparison found. A drift it found is already the stage's `drift` and earlier finding. A
   manifest mismatch alone is owed again through the pending-work file. Any other drift is a
   person's, and comparing it again would announce it twice.
2. **When the publish itself pends,** the report stage pends without comparing anything. Its
   `not_compared` is then everything the publish confirmed before the session expired. Nothing
   compared those snapshots either; the PM's wording covers them, and the drain compares them
   after it publishes the rest.
3. **"The newest run" passes over a run with no stages,** as `snapshots_owed_again_for_drift`
   already does. A run the lock refused, or one that stopped before any stage, compared nothing.
   Without this, a `--publish-pending` that the scheduled run's lock refused would throw the list
   away. Any run that did run a stage settles the list, a scheduled pull included. That pull does
   not compare the list, because only `--publish-pending` is handed it (Follow-up 1).
4. **The stored start-commit records are compared through a documented transformation.**
   `objects_published` now counts manifests too, which the runbook already said it did. In the
   three stored scenarios with a completed publish, the start commit's reason and count are
   therefore one manifest per snapshot lower. `as_this_build_counts_it` in the compatibility test
   rewrites only those (`N object(s) uploaded across M snapshot(s)` becomes N+M, with the
   breakdown) and asserts that the stored count was the sources. Every other field is compared as
   before. `v1-e39-t09`'s search-index stage entry is handled the same way. The record's shape is
   unchanged: every written record still validates against both stored schemas. The stored files
   are untouched.
5. **No digests in the list.** The PM allowed slugs, snapshot names and digests. A comparison is
   asked for by caselist and snapshot, so nothing needed a digest, and the list holds only those
   two. Each entry is checked with `validate_publish_target` when it is read back. An entry that
   fails is passed over with a warning that names no path.
6. **The banner's words.** The login banner now ends `caselist pull --publish-pending makes it
   again after the login, if no other pull runs first.` The runbook gives `caselist status` for
   the case where a pull ran first.
7. **Only an expired session leaves comparisons owed.** A comparison the bucket refused
   (`StoreAccessDenied`) fails the stage as before. Logging in does not fix that, and the stage's
   reason and hint already ask for a person.
8. **v1-e01-t30 (your message mid-session).** The local `origin/dev` (fetched 20:21 today, at
   `2d5a718`) does not contain it, so there was nothing to sync. Its branch's report (Decision 10)
   maps imports by name to module. At the sync, one line of this task's files changes:
   `from debate_core.testing.fakes import empty_suppression_list` in
   `test_caselist_sync_publish_stage_loose_ends.py` becomes
   `from debate_core.testing.fakes.suppression import empty_suppression_list`. No new source line
   imports from `application.ports`; the lines this task touched around existing `ports` imports
   are not those imports.

## Operator follow-ups

None. For information: the weekly agent keeps the old behaviour until it is reinstalled. It
records a report-only pending run as `completed`, writes no `not_compared`, and its banner still
names `caselist status`. A drain run by dev85 compares nothing extra. The reinstall the PM has
already planned brings this in.

## Follow-up work

1. **A scheduled pull before the drain settles the owed check without making it** (E34). Only
   `--publish-pending` is handed the list, as the ruling says. `run()` could be handed it too, and
   the report stage would compare it the same way. It would cost one comparison per snapshot,
   once.
2. **The module docstring's sentence** "the publish and report stages are then recorded as pending
   in a small local file" was inexact before this task: the report stage was never in that file.
   The new paragraph "A check cut short is made again" says where its owed work is kept. The old
   sentence could be reworded when that docstring is next edited.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-22

**Notes:**

Accepted, on three conditions closed in this session before the pull request. Record them under
"PM conditions", keep the phase `Succeeded`, and open the pull request with no `--partial`. If
anything comes out differently from what is written here, stop and ask for another review.

**What the PM checked.** The branch is clean, 7 commits on origin/dev at `ffbfb2c`, and the diff
is the 20 files listed. Since then dev has gained v1-e01-t30 (#403) and the PM batch (#405), so the
sync in condition 3 is required. `publish_pending` is an existing outcome value. The cross-build
read uses dev85's own readers, exported from its tag, and it was shown able to fail: `report_pending`
made dev85 exit 1.

**Rulings.**

1. **Items (1) to (3), and the record's unchanged shape, are accepted.** Two things are exactly
   the evidence the spec's forbidden entry needed: dev85's readers on this build's files, and the
   failing run with a value dev85 does not know.
2. **Decision 4 is accepted.** `objects_published` now means what the runbook always said, and the
   stored records are left untouched. The transformation is documented and asserts that the stored
   count was the sources.
3. **Deviation 1 is accepted** under working agreement 5, as for v1-e34-t30.
4. **Decisions 1, 2, 5 and 7 are accepted.** Decision 6's banner changes with condition 1.
5. **Follow-up 1 is brought into this task (condition 1).** As built, a scheduled pull that runs
   before the operator drains settles the owed list without making the check. On a Wednesday after
   an expired session, that is the likeliest order, and the owed comparisons would be lost without
   a word. That is the very gap item (1) exists to close. The cost is one comparison per owed
   snapshot, once.

**Conditions, all closed in this session:**

1. **Hand the newest run's owed list to `run()` too.** A scheduled or hand-run pull's report stage
   compares the owed snapshots after what it published, exactly as `--publish-pending` does,
   through the same `_report_stage`. A pull cut short again owes what it did not reach.
   * **Tests, red first:** an expired session's run, then a scheduled pull, which compares the owed
     week; and a scheduled pull cut short again, which owes it again.
   * **Mutate:** a run that ignores the list.
   * **Banner:** it then says the next pull, or `caselist pull --publish-pending` after the login,
     makes the check again. Update the runbook to match.
   * **Agent compatibility:** the cross-build read stays green. Re-run it if any written key
     changes; none should.
2. **Reword the docstring's inexact sentence now (Follow-up 2).** You are editing that docstring
   in this task, so say that the pending-work file holds the publish's owed work and the details
   hold the report stage's.
3. **Sync onto origin/dev** (`scripts/task sync`). Rewrite the one fakes import by v1-e01-t30's
   mapping (`debate_core.testing.fakes.suppression`). Then re-run:
   * the new test file and the every-build compatibility test;
   * the changed test directories and the always-run list;
   * pyright, `lint-imports`, ruff, `validate_specs.py` and the docs checks.

   Record the results.

**Operator follow-up:** none, as you say. The agent keeps its old behaviour until the planned
reinstall, which the PM sequences after this merges.
